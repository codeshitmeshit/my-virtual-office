---
name: vo-project-authoring
description: 仅当用户明确调用 `$vo-project-authoring` 并要求在当前本地 Virtual Office 中起草、创建、复用或周期化项目，指定任务负责人/执行人、按需推荐 reviewer，查询确认状态，或按已授权策略维护该项目时使用；不得隐式触发，也不负责项目执行、review、验收、取消或 artifact 读取。
---

# Virtual Office 项目创作

## 目标

把用户意图整理为一个完整、可校验但尚未落地的项目草稿，提交给当前本地 VO，并等待用户在可信管理界面编辑、确认或拒绝。一次确认必须创建包含全部初始任务、角色、模板/周期设置的完整项目，但不得自动启动 Project Execution。

项目落地后的执行、review、验收、取消和 artifact 读取切换到本地 `/skills/vo-project-workflow/SKILL.md`。

## 1. 确认本地 VO 和调用身份

先读取本地 `/skills/vo-operating-guidelines/SKILL.md`，按其规则确定地址。不得猜测或传播外部地址。

```bash
vo_authoring_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
vo_authoring_port="${VO_PORT:-$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_authoring_root/.env" 2>/dev/null)}"
vo_authoring_url="${VO_BASE_URL:-http://127.0.0.1:${vo_authoring_port:-8090}}"
curl -sS "$vo_authoring_url/skills/index.md"
curl -sS "$vo_authoring_url/api/agents"
```

从 roster 确认当前调用 Agent、候选负责人、执行人和 reviewer 均存在且可分配。不得冒用其他 Agent；档案管理员等排除角色不能承担普通项目工作。

## 2. 构造完整草稿

仅在信息足够时提交。信息不明确时，先向用户展示候选角色映射并请求确认，不猜测人员 ID。

每个草稿必须包含：

- `title`、可选 `description`。
- `projectType`：`one_time`、`reusable` 或 `recurring`。
- 至少一个 column 和一个初始 task；column id 唯一，task 指向有效 `columnId`。
- 每个 task 恰好一个 `responsibleActor` 和一个 `executorActor`；二者可以相同。
- actor 使用 `{"type":"agent","id":"AGENT_ID"}` 或当前本地用户 `{"type":"user","id":"user:local"}`。
- 可选 `reviewerActor` 只能由用户确认后的编辑配置指定；Agent 草稿不要直接分配 reviewer。
- 每个 task 必须有显式 `reviewerRecommendation`，即使结论是不推荐。
- `agentMaintenanceMode`：默认 `strict_confirmation`；只有用户明确授权日常自治更新时才建议 `autonomous`。
- `template` 和 `recurrence` 必须与项目类型一致。

负责人或执行人为本地用户时，任务可以被跟踪，但不能作为自动 Project Execution 的可执行 Agent。

### Reviewer 推荐

默认不推荐 reviewer：

```json
{"recommended":false,"triggers":[]}
```

出现以下任一风险时推荐 reviewer，但仍不替用户完成最终分配：

- `high_risk`：高风险或难以回滚。
- `cross_team`：跨团队或跨职责边界。
- `critical_delivery`：关键交付或强验收要求。

推荐时填写 `triggers`、具体 `rationale` 和 Agent `candidate`：

```json
{
  "recommended": true,
  "triggers": ["critical_delivery"],
  "rationale": "上线前需要独立检查验收证据和回滚条件",
  "candidate": {"type": "agent", "id": "reviewer-agent-id"}
}
```

### 模板与周期

- 一次性项目：通常使用 `"template":{"mode":"none"}`。
- 可复用项目：使用 `create` 新建版本化模板，或用 `reference` 固定引用 `templateId` 和正整数 `version`。
- 周期项目：必须创建或引用模板，并设置 `recurrence.enabled=true`。
- schedule 支持 `cron`（5–7 段表达式）或 `every`（`everyMs >= 60000`），并给出有效 IANA `timezone`。
- 每次周期触发创建独立项目实例；不要把它描述成重开同一个项目的任务。

## 3. 提交非物化草稿

生成 8–128 位安全幂等键。网络重试必须复用同一个 key；不要为同一意图生成新 key。

```bash
curl -sS -X POST "$vo_authoring_url/api/agent/project-authoring/requests" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{
    "idempotencyKey":"agent-id:project:stable-key",
    "draft":{
      "title":"发布准备",
      "description":"完成发布前准备并沉淀证据",
      "projectType":"one_time",
      "agentMaintenanceMode":"strict_confirmation",
      "columns":[{"id":"backlog","title":"Backlog"},{"id":"done","title":"Done"}],
      "tasks":[{
        "title":"准备发布材料",
        "description":"整理变更、测试和回滚说明",
        "columnId":"backlog",
        "responsibleActor":{"type":"agent","id":"owner-agent-id"},
        "executorActor":{"type":"agent","id":"builder-agent-id"},
        "reviewerRecommendation":{"recommended":false,"triggers":[]}
      }],
      "template":{"mode":"none"},
      "recurrence":{"enabled":false}
    }
  }'
```

成功响应包含 `request.id`。仅首次创建时返回一次 `requestSecret`：

- 只保存在当前运行内存中。
- 不写入文件、日志、项目、聊天消息或命令输出摘要。
- 不与其他 request、Agent 或项目混用。
- 丢失后不要猜测；向用户说明无法继续 Agent 侧轮询，用户仍可在可信管理界面处理草稿。

提交成功不代表项目已创建。明确告诉用户：草稿正在等待其在“Agent 项目草稿”界面编辑和确认。

## 4. 查询确认结果

使用原请求的 Agent ID 和一次性 secret：

```bash
curl -sS "$vo_authoring_url/api/agent/project-authoring/requests/REQUEST_ID" \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -H "Authorization: Bearer $vo_request_secret"
```

低频轮询并设置总等待上限；不要高频无限轮询。

- `pending`：等待用户编辑、确认或拒绝。
- `materializing`：正在创建 workspace/项目。
- `failed`：报告真实 `code/error`，用户可修正后重试确认。
- `confirmed`：返回 `projectId`；项目已完整创建，但尚未启动执行。
- `rejected`：报告拒绝结果，不重新提交等价草稿规避用户决定。

确认后如需执行，读取 `vo-project-workflow` 并重新检查 workspace、执行人、reviewer 和验收门禁。

## 5. 受控维护

确认后的 request secret 作为该项目、该创作 Agent 的 scoped grant 使用。先查询 grant：

```bash
curl -sS "$vo_authoring_url/api/agent/projects/PROJECT_ID/grant-status" \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -H "Authorization: Bearer $vo_project_grant_secret"
```

所有维护都走同一入口：

```bash
curl -sS -X POST "$vo_authoring_url/api/agent/projects/PROJECT_ID/maintenance" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -H "Authorization: Bearer $vo_project_grant_secret" \
  -d '{"idempotencyKey":"agent-id:maintenance:stable-key","mutation":{"operation":"update_project","changes":{"description":"更新后的说明"}}}'
```

- `strict_confirmation`：所有变更生成待用户确认的 maintenance request。
- `autonomous`：只有分配给当前 Agent 的任务可直接更新 `executionState`、`description`、`checklist`、`evidence`、`dueDate`，operation 使用 `routine_task_update` 并携带 `taskId`。
- 创建/删除任务、角色或 reviewer 调整、周期变更、归档、workspace 变更、维护模式变更始终需要用户确认。
- grant 缺失、失效、撤销、跨项目或跨 Agent 时立即停止；不要尝试管理端 rotate/revoke 接口。

## 安全边界

- 不索取、读取、缓存或传递 `X-VO-Management-Token`。
- 不调用管理端 edit/confirm/reject、模板直接实例化、grant rotate/revoke 或周期 pause/resume 接口。
- 不把草稿提交当作用户确认，不宣称项目已创建直到状态为 `confirmed`。
- 不自动启动项目、任务、review、验收、取消或会议。
- 不绕过 reviewer 推荐、用户验收、workspace、dirty worktree 或角色可执行性门禁。
- 不在 Agent 草稿中自行指定 reviewer；只推荐候选和理由，最终分配由用户确认。

## 完成检查

- 已读取当前本地 VO skill 总入口和 Agent roster。
- 草稿包含全部任务、负责人、执行人和显式 reviewer 推荐决定。
- 模板、周期、维护模式与项目类型一致。
- 同一请求/维护重试复用了幂等键。
- secret 未持久化或输出。
- 已向用户区分 `pending`、`confirmed`、`failed` 和 `rejected`。
- confirmed 后没有自动开始执行，并已把执行类需求路由到 `vo-project-workflow`。
