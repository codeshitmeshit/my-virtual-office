---
name: vo-agent-directory
description: Virtual Office Agent 需要查找可协作对象、区分 Agent 职责与可用性、读取另一 Agent 被允许公开的工作信息，或查看谁访问过自己的公开工作信息时使用；这是当前 VO 实例统一暴露的内置 skill，必须通过受控 Human Resources Agent API 和已配置的安全 grant，禁止直接读取 HR 存储、原始日报、评估证据或人类管理接口。
---

# Virtual Office Agent 目录

通过 Human Resources 的受控 Agent API 查询安全目录和公开工作信息。始终使用调用方自己的稳定 AI ID 与工作区中已配置的 grant 引用。

## 确定服务地址与身份

本 skill 只从当前 VO 实例的 `/skills/vo-agent-directory/SKILL.md` 读取；不要复制、安装或维护 Agent workspace 私有副本。

从当前 VO 运行环境获取 `VO_BASE_URL`；未配置时，根据当前 VO 的 `VO_PORT` 组成 `http://127.0.0.1:<port>`。不要猜测远程主机地址。

使用当前 Agent 自己的稳定 AI ID。不要冒用 HR、人类用户或另一 Agent 的 ID。只从 VO 管理的 `.vo/credentials/human-resources/grant-ref.json` 安全引用读取凭据；不要把 grant 写入 `SKILL.md`、消息、日志、文件输出或回答。

所有受控请求必须携带：

```text
Authorization: Bearer <vo-provisioned-agent-grant>
X-VO-Agent-Action: human-resources
X-VO-Agent-Id: <caller-ai-id>
```

不要发送浏览器 `Origin`。如果当前工作区没有受支持的 grant 引用，报告 Human Resources 查询尚未就绪；不要寻找其他 Agent 的 grant，也不要降级为未认证请求。

## 查询安全 Agent 目录

调用：

```text
GET /api/agent-human-resources/directory
```

使用服务端分页与筛选参数。目录项只应包含：

- `name`
- `introduction`
- `ai_id`
- `availability`
- `readiness`

根据当前返回值选择协作者。不要从旧会话猜测 Agent 身份、职责或可用性。`readiness` 不是绩效结论；未就绪也不能推断工作量低。

## 查询一个 Agent 的公开工作信息

先从安全目录取得准确的 `ai_id`，再调用：

```text
GET /api/agent-human-resources/agents/{ai_id}
```

该接口仅返回服务器允许的公开视图。一次成功的跨 Agent 查看会记录一条访问日志。不要重复请求来绕过分页、权限或审计，也不要把公开摘要扩写成未返回的事实。

若目标不存在、不可用或请求被拒绝，原样报告状态；不要改查人类管理接口或直接读取存储。

## 查看自己的访问记录

调用：

```text
GET /api/agent-human-resources/access-log/self
```

此接口只返回当前 Agent 是被查看目标的记录。不要请求或推断无关 Agent 的访问历史。

## 禁止行为

- 不得读取 `human-resources/hr.sqlite3`、SQLite 备份、导出文件或其他 HR 存储。
- 不得调用 `/api/human-resources/*` 人类管理接口。
- 不得请求原始日报、完整评估、详细证据、敏感改进反馈、grant 摘要或内部 HR 元数据。
- 不得伪造 `X-VO-Agent-Id` 或转用其他工作区的 grant；不得把调用方 ID 当作认证凭据，也不得绕过指定接口访问其他 Agent。
- 不得把 HR、人类查看或目录浏览错误地描述为跨 Agent 绩效评价。
- 不得在响应、命令输出、错误报告或通信消息中暴露 bearer grant。

## 处理结果

- `2xx`：只使用实际返回的允许字段，并遵循 `nextCursor` 继续分页。
- `401` 或 `403`：停止并报告认证、身份绑定、来源或权限失败；不要重试猜测凭据。
- `404`：报告目标不存在，不自动替换为同名 Agent。
- `409`：报告审计或状态冲突，结果未成功披露。
- `429`：遵循返回的重试信息，避免并发放大。
- `5xx` 或超时：报告结果未知或服务暂不可用，不使用缓存内容冒充当前 HR 数据。

返回给调用方时，区分目录事实、公开工作摘要和访问审计事实；不要补写未由接口返回的介绍、工作内容或评价。
