---
name: vo-project-authoring
description: 当用户明确调用 `$vo-project-authoring`，或用自然语言要求在当前本地 Virtual Office 中创建、复用、周期化项目，或维护已有 VO 项目时使用；创建或修改前必须先用自然语言展示完整方案并等待用户明确确认，再调用真实接口。不负责项目执行、review、验收、取消或 artifact 读取。
---

# Virtual Office 项目创作

## 目标

把用户意图整理成可读的自然语言项目方案。只有用户明确确认当前版本后，才把它转换成结构化数据并直接创建真实项目。不要把方案提交成后台草稿；创建后也不要自动启动 Project Execution。

项目执行、review、验收、取消和 artifact 读取切换到本地 `/skills/vo-project-workflow/SKILL.md`。

## 强制流程门禁

必须按下面状态机顺序执行，不得跳步、合并步骤或用“我已理解用户意图”替代确认：

| 阶段 | 允许动作 | 禁止动作 | 进入下一阶段条件 |
| --- | --- | --- | --- |
| S0 读取指南 | 读取 `/skills/index.md` 和 `/skills/vo-project-authoring/SKILL.md` | 调项目列表、创建、维护、执行、review 接口 | 已拿到当前本地权威 skill |
| S1 获取角色 | 只读 `GET /api/agents` 获取 roster | 内联 Python、导入 `app.server`、`GET /api/projects`、任何写接口 | 已确认负责人、执行人、reviewer 候选存在且可分配 |
| S2 输出方案 | 只用固定 Markdown 模板展示完整项目方案；维护已有项目时先读取目标项目现状并做相似功能检查 | 调创建接口、把草稿写入后台、生成 `confirmed=true`、重复新增已有能力 | 已把完整方案发给用户，或已向用户提示已有类似能力并等待是否仍要新增 |
| S3 等待用户确认 | 等待用户明确确认当前完整方案 | 把沉默、讨论、问题、局部认可当作确认 | 用户明确表达“确认/同意/按以上方案创建”等等价语义 |
| S4 构造请求 | 计算已确认方案原文 digest，构造 `summaryText`、`summaryDigest`、完整 project payload | 修改方案后不重新确认、遗漏任务/角色/reviewer 决策 | payload 与已确认方案语义一致 |
| S5 创建项目 | 调 `POST /api/agent/project-authoring/projects` | 自动启动项目、任务、review、验收、取消或会议 | 返回真实 project id 后向用户报告未运行状态 |

维护已有项目时也必须遵守同样的确认门禁：确认前只允许读取 skill、Agent roster、目标项目详情和该项目必要的定时配置；确认前不得调用维护写接口。用户确认维护方案后，才可调用 `POST /api/agent/projects/PROJECT_ID/maintenance`。

如果任一阶段发现信息缺失或用户修改语义，必须回到 S2 重新展示完整方案并等待确认。创建新项目时，S3 之前不得调用项目列表、项目详情或项目写接口；维护已有项目时，S3 之前只可读取目标项目和必要配置，不得调用任何写接口；S5 之前不得提交 `confirmed=true`。

## 1. 确认本地 VO 与角色

先读取本地 `/skills/vo-operating-guidelines/SKILL.md`，按其规则确定地址，不猜测或传播外部地址。

用户确认前只允许读取本地 skill 和 Agent roster：

- `GET /skills/index.md`
- `GET /skills/vo-project-authoring/SKILL.md`
- `GET /api/agents`

创建新项目时，不要在确认前调用项目列表、项目详情、项目创建、维护、执行或 review 相关接口。尤其不要用 `GET /api/projects` 做预检查；除非用户确认方案后需要复用或查重，否则不要读取真实项目状态。

维护已有项目时，如果用户已经给出项目 ID，或必须判断“往哪个已有项目修改”，确认前可以读取目标项目现状和该项目必要配置：

- `GET /api/projects/PROJECT_ID`
- `GET /api/projects/PROJECT_ID/scheduled-cron`（仅当修改涉及定时运行或重复触发）

不要用全量项目列表扩大范围；如果用户没有给出明确项目 ID，只能请求用户选择项目，或在确认方案后按用户授权做查重/复用检查。

```bash
vo_authoring_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
vo_authoring_port="${VO_PORT:-$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_authoring_root/.env" 2>/dev/null)}"
vo_authoring_url="${VO_BASE_URL:-http://127.0.0.1:${vo_authoring_port:-8090}}"
curl -sS "$vo_authoring_url/skills/index.md"
curl -sS "$vo_authoring_url/skills/vo-project-authoring/SKILL.md"
curl -sS "$vo_authoring_url/api/agents"
# 仅维护已有项目且已明确 PROJECT_ID 时：
curl -sS "$vo_authoring_url/api/projects/PROJECT_ID"
curl -sS "$vo_authoring_url/api/projects/PROJECT_ID/scheduled-cron"
```

只用这些只读 HTTP GET 获取 roster。不要运行内联 Python、不要导入 `app.server`、不要调用 `_office_agent_lookup` 等内部函数来探测角色；那会触发不必要的本地命令审批，且容易让用户误以为正在创建项目。

从 roster 确认调用 Agent、负责人、执行人和 reviewer 候选均存在且可分配。不要冒用其他 Agent；排除角色不能承担普通项目工作。

## 2. 展示自然语言方案

在对话中清楚展示，必须使用下面的 Markdown 模板和字段顺序，不要省略字段；未知项写“待确认”，不要自行补全：

```markdown
我准备创建这个 VO 项目，请确认：

项目名称：...
项目类型：one_time | reusable | recurring
项目目标：...
维护模式：strict_confirmation | autonomous
创建后状态：确认后会创建真实项目，但不会开始执行。
Reviewer 默认策略：不指定；如有建议，仅作为建议，确认分配前不会写入 reviewer。

任务清单：

| # | 任务名称 | 所属列 | 任务细节 | 验收标准 | 负责人 | 执行人 | Reviewer |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | ... | Backlog | ... | ... | agent-id | agent-id | 不指定 |

模板/复用配置：无 | 创建模板：... | 复用模板：templateId@version
周期配置：无 | cron/every + timezone + 触发范围
需要你确认的点：...

请确认是否按以上方案创建真实项目。
```

字段要求：

- 项目名称、目标和 `one_time`、`reusable` 或 `recurring` 类型。
- 全部初始任务及所属 column。
- 每个任务唯一的负责人和执行人；二者可以相同。
- reviewer 决定，默认“不指定”。
- `strict_confirmation` 或 `autonomous` 维护模式；默认 strict。
- 可复用模板或周期 schedule、timezone。
- 明确说明“确认后会创建真实项目，但不会开始执行”。
- “需要你确认的点”只列真正会影响创建结果的未决事项；如果没有，写“无”。

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

对用户确认的精确方案 UTF-8 文本计算 SHA-256 hex，不把方案写入临时文件。创建请求必须同时携带该精确文本和 digest；后端会拒绝缺少 `summaryText`、未使用固定确认模板或 digest 不匹配的请求：

```bash
vo_proposal_digest="$(printf %s "$vo_confirmed_proposal" | shasum -a 256 | awk '{print $1}')"
```

## 4. 构造并提交完整项目

只有在用户确认当前自然语言方案后，才进入本阶段。此时可以按确认后的意图调用真实项目接口，例如查重、复用检查或直接创建；如果查重结果会改变项目语义、任务拆分、负责人、执行人、reviewer、模板或周期配置，必须回到第 2 步重新展示完整方案并再次等待确认。

结构化 `project` 必须包含完整 columns/tasks、角色、显式 reviewer recommendation、维护模式以及一致的模板/周期配置：

- 一次性项目通常使用 `"template":{"mode":"none"}` 和 `"recurrence":{"enabled":false}`。
- 可复用是项目属性，不是模板属性；可复用项目可以使用 `"projectType":"reusable"` 与 `"template":{"mode":"none"}` 直接创建，不要求创建或引用模板。
- 周期也是项目属性；需要自动生成独立项目实例时才创建或引用模板。只想让已有项目按固定时间运行时，不要使用模板 recurrence，改用下文的项目 scheduled-cron。
- schedule 支持 `cron`（5–7 段）或 `every`（`everyMs >= 60000`），并使用有效 IANA timezone。

生成 8–128 位安全幂等键。同一确认意图的网络重试必须复用同一 key；语义变化必须重新确认并使用新 key。

```bash
curl -sS -X POST "$vo_authoring_url/api/agent/project-authoring/projects" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{
    "idempotencyKey":"agent-id:project:stable-key",
    "confirmation":{
      "confirmed":true,
      "summaryDigest":"64_HEX_DIGEST",
      "summaryText":"EXACT_CONFIRMED_MARKDOWN_PROPOSAL"
    },
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

成功响应直接包含真实 `project.id`。如果响应里包含兼容旧流程的 `projectGrantSecret` 或其他 secret 字段，不要读取、缓存、复述或用于后续维护；维护已有项目统一使用下文的“用户确认方案”路径。

创建成功后向用户报告项目 ID，并明确说明项目尚未运行。

## 5. 受控维护

维护已有项目时，安全边界是“用户先确认自然语言维护方案”，不是项目创建时返回的 grant secret。任意 Agent 只要知道项目 ID，都可以在确认后请求维护该项目；但确认前不得调用维护写接口。

### 修改前相似功能检查

在展示维护方案前，必须先读取目标项目现状，检查用户要求新增或修改的内容是否已经存在类似能力：

- 任务：检查 `tasks[].title`、`description`、`checklist`、`evidence`、负责人/执行人/reviewer 是否已有相同或高度相似任务。
- 定时运行：检查目标项目的 `/scheduled-cron` 是否已有相同 `targetType`、`taskId`、`schedule.expr/everyMs/at`、`timezone` 或相近周期。
- 项目属性：检查 `projectType`、`longTermProject`、`agentMaintenanceMode`、`workspacePath`、`projectExecutionEnabled` 是否已经是目标值。
- recurrence：检查 `recurrence.enabled`、`recurrence.schedule` 和 `paused` 是否已经满足用户目标。

如果已存在类似功能，不要直接新增或重复配置。先向用户提示：

```markdown
我检查了当前项目，发现已经有类似配置/任务：

| 已有项 | 相似点 | 当前状态 | 与你要求的差异 |
| --- | --- | --- | --- |
| ... | ... | ... | ... |

看起来不需要重复新增。你希望我：
1. 不做修改；
2. 修改已有项；
3. 仍然新增一个独立项。
```

只有用户明确选择“修改已有项”或“仍然新增”后，才进入维护方案确认；如果用户选择不做修改，停止并报告未调用写接口。

确认前先展示固定模板，字段顺序不要省略：

```markdown
我准备修改这个 VO 项目，请确认：

项目 ID：...
项目名称：...
修改目标：...
修改内容：

| # | 类型 | 对象 | 当前值 | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | update_recurrence | 周期配置 | 无 | 每天 10:00 Asia/Shanghai | 项目会按该周期生成/运行 |

不会修改的内容：...
风险/注意事项：...
需要你确认的点：...

请确认是否按以上方案修改真实项目。
```

只有用户明确确认当前维护方案后，才计算该方案文本的 SHA-256 digest 并调用维护接口：

```bash
vo_maintenance_digest="$(printf %s "$vo_confirmed_maintenance_proposal" | shasum -a 256 | awk '{print $1}')"
curl -sS -X POST "$vo_authoring_url/api/agent/projects/PROJECT_ID/maintenance" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{
    "idempotencyKey":"agent-id:maintenance:stable-key",
    "confirmation":{
      "confirmed":true,
      "summaryDigest":"64_HEX_DIGEST",
      "summaryText":"EXACT_CONFIRMED_MAINTENANCE_PROPOSAL"
    },
    "mutation":{
      "operation":"update_recurrence",
      "changes":{"schedule":{"kind":"cron","expr":"0 10 * * *","timezone":"Asia/Shanghai"}}
    }
  }'
```

维护操作约束：

- 创建/删除任务、角色或 reviewer 调整、周期变更、归档、workspace 变更和维护模式变更始终需要用户确认。
- 用户修改维护语义后，必须重新展示完整维护方案并再次等待确认。
- 维护接口仍会校验 `summaryText`、`summaryDigest` 和固定确认模板；不要伪造 `confirmed=true`。
- 把项目设为可复用时，使用 `update_project` 修改 `projectType=reusable`；不要创建模板。
- 修改项目的 recurrence 属性时，使用 `update_recurrence`，它会直接写到项目自身。
- 让已有项目每天/每周自动开始执行时，使用确认后的项目 scheduled-cron 入口；不要使用管理面 `/api/projects/PROJECT_ID/scheduled-cron`，也不要索取 `X-VO-Management-Token`：

### 维护接口调用样例

下面样例只展示 `mutation` 部分；外层都必须使用同一个维护接口和确认字段：

```json
{
  "idempotencyKey": "agent-id:maintenance:stable-key",
  "confirmation": {
    "confirmed": true,
    "summaryDigest": "64_HEX_DIGEST",
    "summaryText": "EXACT_CONFIRMED_MAINTENANCE_PROPOSAL"
  },
  "mutation": {}
}
```

修改项目属性（标题、描述、优先级、截止时间、标签、可复用属性、项目类型）：

```json
{
  "operation": "update_project",
  "changes": {
    "title": "新项目名称",
    "description": "新的项目描述",
    "priority": "medium",
    "dueDate": "2026-07-31",
    "tags": ["daily", "ai"],
    "longTermProject": true,
    "projectType": "reusable"
  }
}
```

新增任务：

```json
{
  "operation": "create_task",
  "task": {
    "title": "生成日报",
    "description": "汇总 VO 中 AI 的工作并生成日报。",
    "columnId": "backlog",
    "priority": "medium",
    "responsibleActor": {"type": "agent", "id": "codex-local"},
    "executorActor": {"type": "agent", "id": "codex-local"},
    "reviewerRecommendation": {"recommended": false, "triggers": []}
  }
}
```

修改任务内容或状态：

```json
{
  "operation": "update_task",
  "taskId": "TASK_ID",
  "changes": {
    "title": "新的任务标题",
    "description": "新的任务说明",
    "priority": "high",
    "dueDate": "2026-07-31",
    "checklist": [{"text": "完成日报正文", "done": false}],
    "evidence": {"summary": "更新原因"},
    "executionState": "backlog"
  }
}
```

调整任务负责人、执行人或 reviewer：

```json
{
  "operation": "reassign_roles",
  "taskId": "TASK_ID",
  "changes": {
    "responsibleActor": {"type": "agent", "id": "owner-agent-id"},
    "executorActor": {"type": "agent", "id": "executor-agent-id"},
    "reviewerActor": null,
    "reviewerRecommendation": {"recommended": false, "triggers": []}
  }
}
```

删除任务：

```json
{
  "operation": "delete_task",
  "taskId": "TASK_ID"
}
```

归档项目：

```json
{
  "operation": "archive_project"
}
```

修改 Project Execution workspace 或启用状态：

```json
{
  "operation": "workspace_change",
  "changes": {
    "workspacePath": "/absolute/path/to/workspace",
    "workspaceKind": "git",
    "workspaceStatus": {"ok": true},
    "projectExecutionEnabled": true
  }
}
```

修改维护模式：

```json
{
  "operation": "maintenance_mode_change",
  "changes": {
    "agentMaintenanceMode": "strict_confirmation"
  }
}
```

修改项目 recurrence 属性：

```json
{
  "operation": "update_recurrence",
  "changes": {
    "schedule": {"kind": "cron", "expr": "0 10 * * *", "timezone": "Asia/Shanghai"},
    "paused": false
  }
}
```

scheduled-cron 也属于“修改真实项目”的维护动作。调用前必须先把完整维护方案发给用户确认，且 `confirmation.summaryText` 必须原样使用下面的固定维护确认模板；至少包含这些固定标记：

- `我准备修改这个 VO 项目，请确认：`
- `项目 ID：`
- `修改内容：`
- `请确认是否按以上方案修改真实项目。`

示例确认文本：

```markdown
我准备修改这个 VO 项目，请确认：

项目 ID：PROJECT_ID
项目名称：日报
修改目标：设置为可复用并每天 10:00 运行
修改内容：

| # | 类型 | 对象 | 当前值 | 目标值 | 影响 |
| --- | --- | --- | --- | --- | --- |
| 1 | update_project | 项目属性 | 当前值以项目现状为准 | projectType=reusable, longTermProject=true | 项目会被标记为可复用项目 |
| 2 | scheduled_cron | 项目级定时运行 | 无 | 每天 10:00 Asia/Shanghai | VO 会保存并启用项目级定时配置；到点后复用项目执行入口启动项目，不会在保存时立即启动执行 |

不会修改的内容：任务、角色、reviewer、执行状态
风险/注意事项：保存定时配置不会立即运行项目；到点触发后仍遵守原项目执行、reviewer、workspace、dirty worktree 和用户验收门禁。
需要你确认的点：无

请确认是否按以上方案修改真实项目。
```

```bash
curl -sS -X POST "$vo_authoring_url/api/agent/projects/PROJECT_ID/scheduled-cron" \
  -H 'Content-Type: application/json' \
  -H 'X-VO-Agent-Action: project-authoring' \
  -H 'X-VO-Agent-Id: CURRENT_AGENT_ID' \
  -d '{
    "idempotencyKey":"agent-id:schedule:stable-key",
    "confirmation":{
      "confirmed":true,
      "summaryDigest":"64_HEX_DIGEST",
      "summaryText":"EXACT_CONFIRMED_MAINTENANCE_PROPOSAL"
    },
    "projectType":"reusable",
    "longTermProject":true,
    "cron":{
      "name":"日报每日执行",
      "schedule":{"kind":"cron","expr":"0 10 * * *","timezone":"Asia/Shanghai"},
      "targetType":"projectWorkflow",
      "enabled":true
    }
  }'
```

- 修改项目周期配置时，不要把 `GET /api/projects/scheduled-cron` 作为必需前置；该列表依赖 Gateway，仅用于可选观测。已确认的周期维护应直接走 `/api/agent/projects/PROJECT_ID/maintenance` 或 `/api/agent/projects/PROJECT_ID/scheduled-cron`。如果 cron 列表返回 `gatewayAvailable:false` 或 warning，只报告 Gateway 状态，不要因此停止已确认的项目维护流程。
- 对用户说明时，把 scheduled-cron 表述为“VO 已保存并启用项目级定时配置”；不要把 Gateway token、Gateway registration、`pending_gateway_registration` 或 `reconciliationRequired` 当作用户需要处理的事项。Gateway 只是实现细节；项目定时运行到点后应复用原 Project Execution 启动入口。

## 安全边界

- 不索取、读取、缓存或传递 `X-VO-Management-Token`。
- 不索取、读取、缓存或传递 project grant secret；维护已有项目使用确认方案路径。
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
- 对已有项目保存 scheduled-cron 时，已说明“定时配置已保存并启用；不会立即执行；到点后复用原 Project Execution 启动入口”，未把 Gateway 注册状态当作用户前置事项。
