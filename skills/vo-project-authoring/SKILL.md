---
name: vo-project-authoring
description: 仅当用户明确调用 `$vo-project-authoring` 并要求在当前本地 Virtual Office 中创建、复用、周期化或受控维护项目时使用；先用自然语言展示完整项目方案并等待用户明确确认，再直接创建真实但未运行的项目。不得隐式触发，不负责项目执行、review、验收、取消或 artifact 读取。
---

# Virtual Office 项目创作

## 目标

把用户意图整理成可读的自然语言项目方案。只有用户明确确认当前版本后，才把它转换成结构化数据并直接创建真实项目。不要把方案提交成后台草稿；创建后也不要自动启动 Project Execution。

项目执行、review、验收、取消和 artifact 读取切换到本地 `/skills/vo-project-workflow/SKILL.md`。

## 1. 确认本地 VO 与角色

先读取本地 `/skills/vo-operating-guidelines/SKILL.md`，按其规则确定地址，不猜测或传播外部地址。

用户确认前只允许读取本地 skill 和 Agent roster：

- `GET /skills/index.md`
- `GET /skills/vo-project-authoring/SKILL.md`
- `GET /api/agents`

不要在确认前调用项目列表、项目详情、项目创建、维护、执行或 review 相关接口。尤其不要用 `GET /api/projects` 做预检查；除非用户确认方案后需要复用或查重，否则不要读取真实项目状态。

```bash
vo_authoring_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
vo_authoring_port="${VO_PORT:-$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_authoring_root/.env" 2>/dev/null)}"
vo_authoring_url="${VO_BASE_URL:-http://127.0.0.1:${vo_authoring_port:-8090}}"
curl -sS "$vo_authoring_url/skills/index.md"
curl -sS "$vo_authoring_url/skills/vo-project-authoring/SKILL.md"
curl -sS "$vo_authoring_url/api/agents"
```

只用这些只读 HTTP GET 获取 roster。不要运行内联 Python、不要导入 `app.server`、不要调用 `_office_agent_lookup` 等内部函数来探测角色；那会触发不必要的本地命令审批，且容易让用户误以为正在创建项目。

从 roster 确认调用 Agent、负责人、执行人和 reviewer 候选均存在且可分配。不要冒用其他 Agent；排除角色不能承担普通项目工作。

## 2. 展示自然语言方案

在对话中清楚展示：

- 项目名称、目标和 `one_time`、`reusable` 或 `recurring` 类型。
- 全部初始任务及所属 column。
- 每个任务唯一的负责人和执行人；二者可以相同。
- reviewer 决定，默认“不指定”。
- `strict_confirmation` 或 `autonomous` 维护模式；默认 strict。
- 可复用模板或周期 schedule、timezone。
- 明确说明“确认后会创建真实项目，但不会开始执行”。

actor 使用注册 Agent 或本地 `user:local`。本地用户可以负责或执行可跟踪任务，但不能作为自动 Project Execution 的执行 Agent。

### Reviewer

普通任务写“Reviewer：不指定”。出现以下风险时给出建议和理由，但默认仍不分配：

- `high_risk`：高风险或难以回滚。
- `cross_team`：跨团队或跨职责边界。
- `critical_delivery`：关键交付或强验收要求。

只有方案明确写出“Reviewer：某 Agent（将分配）”且用户确认该版本时，结构化请求才包含 `reviewerActor`。仅写“建议某 Agent”时仍省略 `reviewerActor`，但保留 `reviewerRecommendation`。

## 3. 等待明确确认

展示方案后停止，不调用创建 API。只有用户明确表示确认、同意创建或意思等价时才继续。

- 用户修改任何项目、任务、角色、reviewer、维护、模板或周期语义时，重新展示完整方案并再次等待确认。
- 用户拒绝、未确认或只是继续讨论时，不调用 API。
- 后端无法验证聊天消息的用户签名；不得伪造 `confirmed=true`。它只表示本 skill 已实际获得当前方案的对话确认。

对用户确认的精确方案 UTF-8 文本计算 SHA-256 hex，不把方案写入临时文件：

```bash
vo_proposal_digest="$(printf %s "$vo_confirmed_proposal" | shasum -a 256 | awk '{print $1}')"
```

## 4. 构造并提交完整项目

只有在用户确认当前自然语言方案后，才进入本阶段。此时可以按确认后的意图调用真实项目接口，例如查重、复用检查或直接创建；如果查重结果会改变项目语义、任务拆分、负责人、执行人、reviewer、模板或周期配置，必须回到第 2 步重新展示完整方案并再次等待确认。

结构化 `project` 必须包含完整 columns/tasks、角色、显式 reviewer recommendation、维护模式以及一致的模板/周期配置：

- 一次性项目通常使用 `"template":{"mode":"none"}` 和 `"recurrence":{"enabled":false}`。
- 可复用项目使用 `create`，或用 `reference` 固定引用 `templateId` 与正整数 `version`。
- 周期项目必须创建或引用模板，并设置 `recurrence.enabled=true`。
- schedule 支持 `cron`（5–7 段）或 `every`（`everyMs >= 60000`），并使用有效 IANA timezone。

生成 8–128 位安全幂等键。同一确认意图的网络重试必须复用同一 key；语义变化必须重新确认并使用新 key。

```bash
curl -sS -X POST "$vo_authoring_url/api/agent/project-authoring/projects" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{
    "idempotencyKey":"agent-id:project:stable-key",
    "confirmation":{"confirmed":true,"summaryDigest":"64_HEX_DIGEST"},
    "project":{
      "title":"发布准备",
      "description":"完成发布前准备并沉淀证据",
      "projectType":"one_time",
      "agentMaintenanceMode":"strict_confirmation",
      "columns":[{"id":"backlog","title":"Backlog"}],
      "tasks":[{
        "title":"准备发布材料",
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

成功响应直接包含真实 `project.id`。`projectGrantSecret` 只在首次创建响应中出现：

- 只保存在当前运行内存中。
- 不写入文件、日志、项目、聊天消息或命令输出摘要。
- 不与其他 Agent 或项目混用。
- 相同幂等键重试返回同一项目，但不会再次返回 secret。
- 首次响应丢失时，不重复创建；报告项目已创建，并让用户通过可信管理面 rotate grant。

创建成功后向用户报告项目 ID，并明确说明项目尚未运行。

## 5. 受控维护

先用 scoped grant 查询状态：

```bash
curl -sS "$vo_authoring_url/api/agent/projects/PROJECT_ID/grant-status" \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -H "Authorization: Bearer $vo_project_grant_secret"
```

维护统一走 `POST /api/agent/projects/PROJECT_ID/maintenance`。

- `strict_confirmation`：所有变更生成待用户确认的 maintenance request。
- `autonomous`：只有分配给当前 Agent 的任务可用 `routine_task_update` 直接更新 `executionState`、`description`、`checklist`、`evidence`、`dueDate`。
- 创建/删除任务、角色或 reviewer 调整、周期变更、归档、workspace 变更和维护模式变更始终需要用户确认。
- grant 缺失、撤销、轮换、跨项目或跨 Agent 时立即停止，不尝试管理端 rotate/revoke。

## 安全边界

- 不索取、读取、缓存或传递 `X-VO-Management-Token`。
- 不调用已移除的 project-authoring request/status/confirm/edit/reject 路由。
- 不把“展示方案”当作确认，不在用户确认前提交 `confirmed=true`。
- 不自动启动项目、任务、review、验收、取消或会议。
- 不绕过 reviewer、workspace、dirty worktree、执行角色或用户验收门禁。

## 完成检查

- 已读取本地 VO 总入口和 Agent roster。
- 已展示完整自然语言方案并获得当前版本的明确确认。
- 语义变化后已重新确认，并计算精确方案 digest。
- 请求包含全部任务、负责人、执行人和 reviewer 决定。
- 幂等重试复用同一 key，secret 未持久化或输出。
- 已返回真实项目 ID，并明确说明没有自动开始执行。
