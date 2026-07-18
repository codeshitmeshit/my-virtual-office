# 聊天斜杠命令运维指南

Virtual Office 支持两个完整控制消息：`/new` 新建干净上下文，`/compact` 压缩当前上下文。功能默认关闭。

## 配置与精确语法

```bash
export VO_CHAT_SLASH_COMMANDS_ENABLED=true
export VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED=false
./start.sh
```

- 仅当去除首尾空白后的整条文本严格等于 `/new` 或 `/compact`，且消息不带附件/资源时，才识别为命令。
- 区分大小写。`/New`、`/new now`、未知 `/status` 和带附件的 `/new` 都走原普通消息路径。
- VO 与飞书均不提供 `/help`、参数、别名、补全或命令菜单。
- `VO_CHAT_SLASH_COMMANDS_ENABLED` 是总开关；飞书还要求 `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED=true`。任一相关开关关闭时，命令文本保持原普通消息行为。

## Provider 能力

| Provider | `/new` | `/compact` |
| --- | --- | --- |
| Codex | VO 创建新 conversation；飞书重置当前固定 scope | 使用 Codex 原生压缩；无上下文时返回 no-op |
| Hermes | VO 创建新 conversation；飞书重置当前固定 scope | 不支持，不修改上下文 |
| Claude Code | VO 创建新 conversation；飞书重置当前固定 scope | 不支持，不修改上下文 |
| OpenClaw | VO 创建 Agent 所属的新 session；飞书重置当前固定 scope | 不支持，不修改上下文 |

VO `/new` 不删除旧会话或历史；浏览器仅在服务端成功返回后切换缓存和 SSE identity。飞书沿用现有隔离维度：私聊按绑定用户与 `chat_id` 派生 scope；群聊按当前 `chat_id` 共享 scope，同群所有已准入成员都会受到 `/new` 的上下文重置影响，不同群互不影响。群聊仍要求符合现有人工发送者规则并明确提及机器人。

命令若遇到正在执行的普通 turn 或控制操作，会立即返回 busy，不排队等待。失败、busy、unsupported 与 indeterminate 都不会声称成功；`/compact` 只在 Codex 上可改变上下文。

## 灰度顺序

1. 部署代码但保持两个开关关闭，验证 `/new` 仍作为普通消息送达。
2. 仅启用 `VO_CHAT_SLASH_COMMANDS_ENABLED`，在本地/小范围 VO 中验证四个 Provider 的 `/new` 与 Codex `/compact`。
3. 再启用 `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED`，先验收飞书私聊。
4. 若已启用群聊，再在一次性可信群中验收明确提及、同群共享影响、跨群隔离和重复投递。

## 状态与观测

`GET /api/feishu-chat/config` 及安全 `vo-config` 投影中的 `chatCommands` 包含：

- `enabled`、`feishuEnabled`：两个开关的有效状态；
- `reservations.scopes`、`reservations.locked`：有界 scope reservation 状态；
- `metrics`：按固定 surface、Provider、command、status 维度聚合的计数。状态包括 recognized、success、no_op、busy、unsupported、failed、stale、indeterminate、duplicate 和 feedback_failed。

指标不包含消息正文、原始用户/群标识、凭证或 Provider 原始输出。飞书审计使用 `command_started` / `command_completed`；命令不会进入 Agent prompt。若进程在副作用之后、终态落盘之前退出，重启恢复会把结果标为 indeterminate，且不会自动重复执行。应结合 Provider/session 证据和 `VO_STATUS_DIR/feishu-source-message-index` 人工对账。

## 回滚

先设置 `VO_FEISHU_CHAT_SLASH_COMMANDS_ENABLED=false` 并重启，确认飞书命令恢复普通消息行为；再设置 `VO_CHAT_SLASH_COMMANDS_ENABLED=false` 并重启。回滚不删除历史、审计或已创建的 conversation，也不会逆转此前已经成功提交的 reset/compact。对 indeterminate 项先完成对账，不要通过删除 source index 强制重放。
