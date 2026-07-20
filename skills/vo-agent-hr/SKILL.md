---
name: vo-agent-hr
description: Virtual Office Agent 需要查询 HR 名册、区分 Agent 职责与可用性、读取另一 Agent 被允许公开的工作信息，或查看谁访问过自己的公开信息时使用；这是当前 VO 实例统一暴露的内置 skill，默认信任 VO 内部 Agent 自报的稳定 AI ID，禁止直接读取 HR 存储、原始日报、评估证据或人类管理接口。
---

# Virtual Office Agent HR

通过 Human Resources 的受控 Agent API 查询安全名册、公开工作信息和自己的访问记录。VO 内部交互采用可信模式：调用方先从当前 VO Agent 列表确认自己的稳定 AI ID，再将该 ID 放入请求头；不需要独立 bearer grant。

## 确定服务地址与身份

本 skill 只从当前 VO 实例的 `/skills/vo-agent-hr/SKILL.md` 读取；不要复制、安装或维护 Agent workspace 私有副本。

从当前 VO 运行环境获取 `VO_BASE_URL`；未配置时，根据当前 VO 的 `VO_PORT` 组成 `http://127.0.0.1:<port>`。不要猜测远程主机地址。

先调用 `GET /api/agents` 查询当前 VO Agent 列表，找到调用方自己的稳定 AI ID。所有受控请求必须携带：

```text
X-VO-Agent-Action: human-resources
X-VO-Agent-Id: <caller-ai-id>
```

不要发送浏览器 `Origin`。VO 会确认该 AI ID 已登记且当前有效，然后按此身份记录访问。不要填写 HR、人类用户或另一 Agent 的 ID。

## 查询安全 Agent 名册

调用：

```text
GET /api/agent-human-resources/directory
```

使用服务端分页与筛选参数。名册项只应包含：

- `name`
- `introduction`
- `ai_id`
- `availability`
- `readiness`

根据当前返回值选择协作者。不要从旧会话猜测 Agent 身份、职责或可用性。`readiness` 表示介绍信息是否完整，不是接口授权或绩效结论。

## 查询一个 Agent 的公开工作信息

先从安全名册取得准确的 `ai_id`，再调用：

```text
GET /api/agent-human-resources/agents/{ai_id}
```

该接口仅返回服务端允许的公开视图。一次成功的跨 Agent 查看会按调用方自报 AI ID 记录一条访问日志。不要重复请求来绕过分页、权限或审计，也不要把公开摘要扩写成未返回的事实。

若目标不存在、不可用或请求被拒绝，原样报告状态；不要改查人类管理接口或直接读取存储。

## 查看自己的访问记录

调用：

```text
GET /api/agent-human-resources/access-log/self
```

此接口只返回当前自报 Agent 是被查看目标的记录。不要请求或推断无关 Agent 的访问历史。

## 禁止行为

- 不得读取 `human-resources/hr.sqlite3`、SQLite 备份、导出文件或其他 HR 存储。
- 不得调用 `/api/human-resources/*` 人类管理接口。
- 不得请求原始日报、完整评估、详细证据、敏感改进反馈或内部 HR 元数据。
- 不得填写其他 Agent 的 `X-VO-Agent-Id`，也不得绕过指定接口访问其他 Agent。
- 不得把 HR、人类查看或名册浏览错误地描述为跨 Agent 绩效评价。

## 处理结果

- `2xx`：只使用实际返回的允许字段，并遵循 `nextCursor` 继续分页。
- `403`：停止并报告来源、Agent 身份或状态校验失败；不要改用人类管理接口。
- `404`：报告目标不存在，不自动替换为同名 Agent。
- `409`：报告审计或状态冲突，结果未成功披露。
- `429`：遵循返回的重试信息，避免并发放大。
- `5xx` 或超时：报告结果未知或服务暂不可用，不使用缓存内容冒充当前 HR 数据。

返回给调用方时，区分名册事实、公开工作摘要和访问审计事实；不要补写未由接口返回的介绍、工作内容或评价。
