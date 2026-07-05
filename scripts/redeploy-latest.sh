#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
ENV_FILE="$REPO_DIR/.env"
LOG_FILE="${VO_REDEPLOY_LOG:-/tmp/vo-main.log}"
REMOTE="${VO_REDEPLOY_REMOTE:-origin}"
BRANCH="${VO_REDEPLOY_BRANCH:-main}"

cd "$REPO_DIR"

info() {
    printf '[redeploy] %s\n' "$*"
}

warn() {
    printf '[redeploy] WARN: %s\n' "$*" >&2
}

fail() {
    printf '[redeploy] ERROR: %s\n' "$*" >&2
    exit 1
}

env_value() {
    local key="$1"
    [ -f "$ENV_FILE" ] || return 1
    awk -F= -v k="$key" '$1 == k { print substr($0, length(k) + 2); exit }' "$ENV_FILE"
}

port="${VO_PORT:-$(env_value VO_PORT || true)}"
port="${port:-8090}"
health_url="http://127.0.0.1:${port}/health"
gateway_url="http://127.0.0.1:${port}/api/gateway/test"
browser_status_url="http://127.0.0.1:${port}/browser-status"

info "fetching ${REMOTE}/${BRANCH}"
git fetch "$REMOTE"

info "resetting worktree to ${REMOTE}/${BRANCH}"
git reset --hard "${REMOTE}/${BRANCH}"

stop_matches() {
    local pattern="$1"
    local label="$2"
    local pids
    pids="$(pgrep -f "$pattern" || true)"
    if [ -z "$pids" ]; then
        return 0
    fi
    info "stopping ${label}: ${pids//$'\n'/ }"
    # shellcheck disable=SC2086
    kill $pids || true
}

stop_matches 'bash \./start\.sh|bash .*/start\.sh|(^|/)\./start\.sh' 'start.sh'
sleep 3
stop_matches 'python3 server\.py|python .*server\.py|\.venv/bin/python server\.py' 'server.py'

info "starting service; log: ${LOG_FILE}"
setsid bash ./start.sh > "$LOG_FILE" 2>&1 < /dev/null &

info "waiting for health: ${health_url}"
ready=0
for _ in $(seq 1 45); do
    if curl -fsS "$health_url" >/dev/null 2>&1; then
        ready=1
        break
    fi
    sleep 1
done

if [ "$ready" -ne 1 ]; then
    tail -120 "$LOG_FILE" >&2 || true
    fail "service did not become healthy"
fi

info "health ok"
curl -fsS "$gateway_url" >/dev/null || fail "gateway check failed"
info "gateway ok"
browser_status="$(curl -fsS "$browser_status_url")" || fail "browser status check failed"
printf '%s' "$browser_status" | grep -q '"cdpAvailable": true' || fail "browser CDP is not available: $browser_status"
info "browser CDP ok"

if ! git diff --quiet -- app/index.html; then
    info "discarding start.sh cache-bust change in app/index.html"
    git checkout -- app/index.html
fi

head_sha="$(git rev-parse HEAD)"
origin_sha="$(git rev-parse "${REMOTE}/${BRANCH}")"
if [ "$head_sha" != "$origin_sha" ]; then
    fail "HEAD does not match ${REMOTE}/${BRANCH}: $head_sha != $origin_sha"
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
    git status -sb >&2
    fail "worktree is not clean"
fi

info "running processes:"
pgrep -af 'python3 server.py|python .*server.py|bash \./start\.sh|bash .*/start\.sh|\.venv/bin/python server\.py' || true
info "done: $(git log --oneline -1 HEAD)"
