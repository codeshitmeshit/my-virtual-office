---
name: vo-project-workflow
description: Virtual Office 中任意 CLI 或 agent 需要读取项目/任务、启动或推进 Project Execution、处理 review/验收/阻塞、取消执行、查看项目 artifact 时使用；必须遵守当前 VO 项目执行 API、workspace/dirty/reviewer/user acceptance 安全门禁，不覆盖 cron、archive、普通 agent 通信或会议申请。
---

# Virtual Office 项目工作流

## 目标

通过当前 `my-virtual-office` 项目 API 安全推进项目任务执行、review、验收、阻塞和 artifact 查看。只覆盖日常项目执行闭环，不处理项目 cron、Archive Room、会议申请或跨 agent 普通通信。

如果任务是在判断是否处于 VO、选择哪个 VO skill，先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。

## 地址和身份

优先使用当前运行环境或 `start.sh` 启动配置中的端口：

```bash
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f /home/wo/code/my-virtual-office/.env ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' /home/wo/code/my-virtual-office/.env)"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

执行写操作前查询 `/api/agents`，确认 `agentId`、`providerKind` 和当前调用方身份。不要冒用其他 agent。

## 工作流

### 1. 读取项目和任务

```bash
curl -sS "$VO_BASE_URL/api/projects"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/project-execution/status"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/status"
```

先确认项目存在、任务存在、当前没有其他 active task，且任务适合进入 Project Execution。

### 2. 校验 workspace

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/project-execution/workspace/validate" \
  -H 'Content-Type: application/json' \
  -d '{"workspacePath":"/path/to/workspace"}'
```

失败时停止并报告真实错误。不要绕过 workspace 校验，也不要把 artifacts 当作通用文件浏览器。

### 3. 启动执行

项目级执行：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/project-execution/start" \
  -H 'Content-Type: application/json' \
  -d '{"mode":"continuous","skipReviewConfirmed":false}'
```

单任务执行：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start" \
  -H 'Content-Type: application/json' \
  -d '{"skipReviewConfirmed":false}'
```

如果响应包含 `confirmationRequired`：

- `code=dirty_worktree_confirmation_required`：向用户展示 `dirtyFiles`、`dirtyFingerprint`，获得明确确认后才用同一 `dirtyFingerprint` 重试。
- reviewer 缺失或要求跳过 review：必须获得用户明确确认后才设置 `skipReviewConfirmed:true`。
- `task_completed_repeat_disabled`：不要重启已完成任务，除非用户启用 repeat 或明确要求调整任务。

### 4. Review、验收和返工

启动独立 review：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/review/start" \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

用户验收：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/accept" \
  -H 'Content-Type: application/json' \
  -d '{"action":"accept","attemptId":"ATTEMPT_ID"}'
```

`accept` 只能在 `executionState=awaiting_user_acceptance` 且 reviewer `pass` 或 `skipped` 后执行。`reject_and_rework` 和 `mark_blocked` 必须带 `feedback`，不要替用户编造验收意见。

### 5. 取消和会议阻塞

取消 active attempt：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/cancel" \
  -H 'Content-Type: application/json' \
  -d '{"attemptId":"ATTEMPT_ID"}'
```

取消不会回滚 workspace 变更。任务等待会议结果时，可用：

```bash
curl -sS -X POST "$VO_BASE_URL/api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/meeting-blocker" \
  -H 'Content-Type: application/json' \
  -d '{"action":"continue_execution","reason":"User approved continuing"}'
```

支持 `continue_execution`、`mark_blocked`、`reopen_meeting`。这些都是用户决策面；没有明确用户意图时只报告状态。

### 6. Artifact 查看

```bash
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/artifacts"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/artifacts/read?path=RELATIVE_MARKDOWN_PATH"
```

inline read 当前只适合 Markdown/text artifact，路径必须位于项目 workspace 内。不要用 artifacts 读取任意本地文件。

## 安全规则

- 不删除、归档、重排项目数据，除非用户明确要求。
- 不绕过 dirty workspace、skip reviewer、user acceptance、active task 门禁。
- 不直接调用 provider 私有 CLI 来替代 Project Execution。
- 需要跨 agent 普通沟通时使用 本地 `/skills/vo-agent-communication/SKILL.md` 或 本地 `/skills/vo-codex-communication/SKILL.md`。
- 需要申请会议时回到 本地 `/skills/vo-operating-guidelines/SKILL.md` 和 `meeting-requests.md`。

## 质量检查

- 已确认 VO 地址、项目、任务、agent 身份和 provider。
- 启动前已检查 workspace、active task、reviewer、dirty 状态和用户确认要求。
- 对 `409`、`confirmationRequired`、`busy/active task`、`awaiting_user_acceptance` 没有伪造成成功。
- 写操作后重新读取 status 验证结果。
- 输出中包含项目、任务、attemptId、当前状态和下一步。
