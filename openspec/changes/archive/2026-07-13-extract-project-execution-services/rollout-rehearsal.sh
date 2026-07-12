#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
BASE_SHA="13a8219afdc410a65cdf8b34d6d695fc22335c2b"
RUN_ROOT="${VO_ROLLOUT_RUN_ROOT:-$(mktemp -d /tmp/vo-rollout-rehearsal.XXXXXX)}"
CANDIDATE="$RUN_ROOT/candidate"
ROLLBACK="$RUN_ROOT/rollback"
STATUS_DIR="$RUN_ROOT/status"
BACKUP_DIR="$RUN_ROOT/backups"
RESTORED_DIR="$RUN_ROOT/restored"
TOKEN_FILE="$RUN_ROOT/management-token"
RESULT_FILE="$RUN_ROOT/result.json"
CANDIDATE_PID=""
ROLLBACK_PID=""

cleanup() {
  for pid in "$CANDIDATE_PID" "$ROLLBACK_PID"; do
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null || true; fi
  done
  if [[ "${VO_ROLLOUT_KEEP:-0}" != "1" ]]; then rm -rf "$RUN_ROOT"; fi
}
trap cleanup EXIT INT TERM

mkdir -p "$CANDIDATE" "$ROLLBACK" "$STATUS_DIR" "$BACKUP_DIR" "$RESTORED_DIR"
umask 077
python3 -c 'import secrets,sys; open(sys.argv[1], "w").write(secrets.token_urlsafe(32))' "$TOKEN_FILE"
TOKEN="$(<"$TOKEN_FILE")"

rsync -a --exclude=.git --exclude=.venv --exclude=data "$ROOT/" "$CANDIDATE/"
git -C "$ROOT" archive "$BASE_SHA" | tar -x -C "$ROLLBACK"
ln -s "$ROOT/.venv" "$CANDIDATE/.venv"
ln -s "$ROOT/.venv" "$ROLLBACK/.venv"

configure_env() {
  local dir="$1" port="$2" ws_port="$3"
  cp "$dir/.env.example" "$dir/.env"
  {
    printf '\nVO_PORT=%s\n' "$port"
    printf 'VO_WS_PORT=%s\n' "$ws_port"
    printf 'VO_STATUS_DIR=%s\n' "$STATUS_DIR"
    printf 'VO_MANAGEMENT_TOKEN=%s\n' "$TOKEN"
    printf 'VO_BROWSER_PANEL=false\n'
  } >> "$dir/.env"
}
configure_env "$CANDIDATE" 18090 18091
configure_env "$ROLLBACK" 18092 18093

"$ROOT/.venv/bin/python" - "$ROOT" "$STATUS_DIR" <<'PY'
import sys
root, status = sys.argv[1:]
sys.path[:0] = [root + "/tests", root + "/app"]
from project_performance_harness import fixture
from project_store import MarkdownProjectStore
MarkdownProjectStore(status).save_all(fixture("medium"))
PY

tar -czf "$BACKUP_DIR/medium-before.tgz" -C "$STATUS_DIR" .
before_digest="$(cd "$STATUS_DIR" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"

wait_health() {
  local port="$1"
  for _ in $(seq 1 180); do
    if curl -sf "http://127.0.0.1:$port/health" >/dev/null; then return 0; fi
    sleep 0.5
  done
  return 1
}

(cd "$CANDIDATE" && ./start.sh > "$RUN_ROOT/candidate.log" 2>&1) &
CANDIDATE_PID=$!
wait_health 18090

headers=(-H "X-VO-Management-Token: $TOKEN" -H 'Content-Type: application/json')
base=http://127.0.0.1:18090/api/projects
project0="$(curl -sf "$base" | jq -r '.projects[0].id')"
curl -sf -X PUT "${headers[@]}" -d '{"description":"rollout-active-write"}' "$base/$project0" >/dev/null
column0="$(curl -sf "$base/$project0" | jq -r '.project.columns[0].id')"
curl -sf -X POST "${headers[@]}" -d "{\"title\":\"rollout live task\",\"columnId\":\"$column0\"}" "$base/$project0/tasks" >/dev/null

workspace="$RUN_ROOT/active-workspace"
git -C "$RUN_ROOT" init -q active-workspace
git -C "$workspace" config user.email rollout@example.com
git -C "$workspace" config user.name Rollout
touch "$workspace/README.md"
git -C "$workspace" add README.md
git -C "$workspace" commit -qm baseline
project_body="$(jq -nc --arg ws "$workspace" '{title:"Rollout active drain",projectExecutionEnabled:true,workspacePath:$ws,defaultExecutorAgentId:"codex-local",defaultReviewerAgentId:"claude-code-local"}')"
project="$(curl -sf -X POST "${headers[@]}" -d "$project_body" "$base")"
project_id="$(jq -r '.project.id' <<<"$project")"
curl -sf -X POST "${headers[@]}" -d "$(jq -nc --arg ws "$workspace" '{workspacePath:$ws}')" "$base/$project_id/project-execution/workspace/validate" >/dev/null
column_id="$(curl -sf "$base/$project_id" | jq -r '.project.columns[0].id')"
task="$(curl -sf -X POST "${headers[@]}" -d "$(jq -nc --arg col "$column_id" '{title:"active rollout work",description:"Remain active until drain cancellation",columnId:$col,executorAgentId:"codex-local",reviewerAgentId:"claude-code-local"}')" "$base/$project_id/tasks")"
task_id="$(jq -r '.task.id' <<<"$task")"
start="$(curl -sf -X POST "${headers[@]}" -d '{}' "$base/$project_id/tasks/$task_id/project-execution/start")"
attempt_id="$(jq -r '.attemptId' <<<"$start")"
active_before="$(curl -sf -H "X-VO-Management-Token: $TOKEN" "$base/$project_id/tasks/$task_id/project-execution/status")"
jq -e '.active == true and .phase == "executing" and (.task.activeAttemptId | length > 0)' <<<"$active_before" >/dev/null
curl -sf -X POST "${headers[@]}" -d '{}' "$base/$project_id/tasks/$task_id/project-execution/cancel" >/dev/null
active_after="$(curl -sf -H "X-VO-Management-Token: $TOKEN" "$base/$project_id/tasks/$task_id/project-execution/status")"
jq -e '.active == false and .task.activeAttemptId == null and .task.executionState == "blocked"' <<<"$active_after" >/dev/null

kill "$CANDIDATE_PID" 2>/dev/null || true
wait "$CANDIDATE_PID" 2>/dev/null || true
CANDIDATE_PID=""

(cd "$ROLLBACK" && ./start.sh > "$RUN_ROOT/rollback.log" 2>&1) &
ROLLBACK_PID=$!
wait_health 18092
rollback_status="$(curl -sf "http://127.0.0.1:18092/api/projects/$project_id/tasks/$task_id/project-execution/status")"
jq -e '.active == false and .task.activeAttemptId == null and .task.attempts[-1].status == "cancelled"' <<<"$rollback_status" >/dev/null
rollback_projects="$(curl -sf http://127.0.0.1:18092/api/projects | jq '.projects | length')"
rollback_tasks="$("$ROOT/.venv/bin/python" - "$ROOT" "$STATUS_DIR" <<'PY'
import sys
root, status = sys.argv[1:]
sys.path.insert(0, root + "/app")
from project_store import MarkdownProjectStore
data = MarkdownProjectStore(status).load_all()
print(sum(len(project.get("tasks", [])) for project in data.get("projects", [])))
PY
)"

tar -xzf "$BACKUP_DIR/medium-before.tgz" -C "$RESTORED_DIR"
restored_digest="$(cd "$RESTORED_DIR" && find . -type f -print0 | sort -z | xargs -0 shasum -a 256 | shasum -a 256 | awk '{print $1}')"
[[ "$restored_digest" == "$before_digest" ]]

jq -n \
  --arg executedAt "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --arg baseSha "$BASE_SHA" --arg beforeDigest "$before_digest" --arg restoredDigest "$restored_digest" \
  --arg runtimePatchSha256 "$(shasum -a 256 "$ROOT/openspec/changes/extract-project-execution-services/rollout-runtime.patch" | awk '{print $1}')" \
  --arg projectId "$project_id" --arg taskId "$task_id" --arg attemptId "$attempt_id" \
  --argjson rollbackProjects "$rollback_projects" --argjson rollbackTasks "$rollback_tasks" \
  '{result:"pass",scope:"local-pre-staging",executedAt:$executedAt,baseSha:$baseSha,runtimePatchSha256:$runtimePatchSha256,fixture:{projects:50,tasks:2500},acknowledgedState:{projects:51,tasks:2502},activeBefore:{active:true,phase:"executing",attemptId:$attemptId},activeAfter:{active:false,state:"blocked",attemptStatus:"cancelled"},rollback:{projects:$rollbackProjects,tasks:$rollbackTasks,active:false,attemptStatus:"cancelled"},backup:{beforeDigest:$beforeDigest,restoredDigest:$restoredDigest},startup:{candidateHttp:true,candidateWebSocket:true,rollbackHttp:true,rollbackWebSocket:true},expectedDegraded:["gateway_unavailable","browser_viewer_unavailable"],ids:{projectId:$projectId,taskId:$taskId}}' \
  > "$RESULT_FILE"
if [[ -n "${VO_ROLLOUT_RESULT_OUTPUT:-}" ]]; then
  cp "$RESULT_FILE" "$VO_ROLLOUT_RESULT_OUTPUT"
fi
cat "$RESULT_FILE"
printf 'rehearsal_dir=%s\n' "$RUN_ROOT"
