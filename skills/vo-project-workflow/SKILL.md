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
vo_project_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f "$vo_project_root/.env" ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_project_root/.env")"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

执行写操作前查询 `/api/agents`，确认 `agentId`、`providerKind` 和当前调用方身份。不要冒用其他 agent。

Agent 自己启动 Project Execution 时优先使用 `/api/agent/projects/.../project-execution/start`，并带上 `X-VO-Agent-Action: project-execution` 与 `X-VO-Agent-Id`。该入口不需要 `X-VO-Management-Token`，但后端会校验调用方必须是项目 authoring agent、默认执行人，或项目/任务里的负责人/执行人。

`/api/projects/...` 下的 project mutation POST/PUT/DELETE 属于用户/管理控制面，通常需要 VO management token 或 UI 代发；Agent 不要索取 token，也不要在没有可信管理面授权时直接调用这些管理面写接口。

## 创建项目确认门禁

当用户要求创建项目、模板、任务链路、工作流或可复用流程时，如果包含以下任一情况，必须先输出草案并等待用户明确确认，不得直接创建：

- 涉及多个 Agent 分工或跨 Agent 协作。
- 涉及 AI 会议、review、验收、返工、自动推进等流程门禁。
- 涉及可复用模板、长期项目、定时项目或项目执行策略。
- 任务数量超过 3 个，或需要为任务指定 executor/reviewer。
- 用户表达的是“我们可以拆分/形成链路/设计流程/起一个项目”这类规划语气。

确认草案至少包含：项目名称、目标、任务列表、每个任务的 assignee/executor/reviewer、会议触发点、是否创建模板、是否立即启动执行。只有用户明确说“确认创建/可以创建/按这个建”等等价语义后，才能调用项目写接口。

如果意图是新建或维护项目结构，优先切换到 本地 `/skills/vo-project-authoring/SKILL.md` 的确认流程；本节是防止 workflow 场景误把规划语气当作执行授权的兜底门禁。

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

这是管理面 workspace 校验接口，适合 UI 或有管理面授权的用户控制面调用。普通 Agent 如果没有管理面授权，不要为了校验 workspace 去索取 `X-VO-Management-Token`；可以在启动接口返回的 `confirmationRequired` / `workspace` 错误中处理真实阻塞。不要绕过 workspace 校验，也不要把 artifacts 当作通用文件浏览器。

### 3. 启动执行

Agent 项目级执行：

```bash
curl -sS -X POST "$VO_BASE_URL/api/agent/projects/PROJECT_ID/project-execution/start" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-execution' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{"mode":"continuous","skipReviewConfirmed":false}'
```

Agent 单任务执行：

```bash
curl -sS -X POST "$VO_BASE_URL/api/agent/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-execution' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{"skipReviewConfirmed":false}'
```

用户/管理控制面也保留兼容入口 `POST /api/projects/PROJECT_ID/project-execution/start` 和 `POST /api/projects/PROJECT_ID/tasks/TASK_ID/project-execution/start`，但它们属于 management-gated 项目写操作；Agent 默认不要使用这些入口。

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

review、验收和返工属于 reviewer/用户控制面，当前公开接口在 `/api/projects/...` 下，通常需要管理面授权或 UI 代发。Agent 可以读取状态、报告下一步和请求用户处理；不要为了这些动作索取、读取或传递 management token。

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

取消和会议阻塞处理也属于用户决策面。当前公开接口在 `/api/projects/...` 下，普通 Agent 不要在没有管理面授权或明确用户控制面代发时调用。

### 6. Artifact 查看

```bash
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/artifacts"
curl -sS "$VO_BASE_URL/api/projects/PROJECT_ID/artifacts/read?path=RELATIVE_MARKDOWN_PATH"
```

inline read 当前只适合 Markdown/text artifact，路径必须位于项目 workspace 内。不要用 artifacts 读取任意本地文件。

## 安全规则

- 不删除、归档、重排项目数据，除非用户明确要求。
- 不把“规划/拆分/设计项目链路”的讨论当作创建授权；命中创建项目确认门禁时必须先给草案并等待确认。
- 不绕过 dirty workspace、skip reviewer、user acceptance、active task 门禁。
- Agent 启动执行使用 `/api/agent/projects/.../project-execution/start`；用户/管理控制面动作才使用 `/api/projects/...` 写接口。
- 不索取、读取、缓存或传递 `X-VO-Management-Token`。
- 不直接调用 provider 私有 CLI 来替代 Project Execution。
- 需要跨 agent 普通沟通时使用 本地 `/skills/vo-agent-communication/SKILL.md` 或 本地 `/skills/vo-codex-communication/SKILL.md`。
- 需要申请会议时回到 本地 `/skills/vo-operating-guidelines/SKILL.md` 和 `meeting-requests.md`。

## 质量检查

- 已确认 VO 地址、项目、任务、agent 身份和 provider。
- 启动前已检查 workspace、active task、reviewer、dirty 状态和用户确认要求。
- 对 `409`、`confirmationRequired`、`busy/active task`、`awaiting_user_acceptance` 没有伪造成成功。
- 写操作后重新读取 status 验证结果。
- 输出中包含项目、任务、attemptId、当前状态和下一步。
