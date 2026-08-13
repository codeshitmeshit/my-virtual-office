# HUMAN DECISIONS 运维说明

> 状态：当前运维说明；已按 2026-08-10 代码核对。

HUMAN DECISIONS 是需要用户明确选择时的统一暂停与恢复边界。它覆盖普通聊天、项目执行、会议和个人资产敏感信息授权；业务模块创建决策请求，但不能自行猜测用户选择。

## 当前行为

- 决策会持久化，浏览器关闭或服务重启后仍可继续处理。
- Chat 来源的决策完成后，以稳定 source message id 唤醒原 Agent 和原 conversation，最多恢复一次。
- Project 来源的决策写回对应任务评论并恢复项目执行状态。
- Meeting 来源的决策写入原讨论轮次，后续参会 Agent 会把它视为权威上下文。
- Personal Assets 的敏感读取通过决策选项授予一次性或当前任务范围访问；缺少有效授权时 fail closed。
- 飞书投递与同步只展示经过裁剪的选项和上下文，不泄露敏感值或 Provider envelope。

## HTTP 边界

管理界面使用：

- `GET /api/human-decisions`
- `POST /api/human-decisions`
- `POST /api/human-decisions/<decisionId>/resolve`
- `POST /api/human-decisions/<decisionId>/reopen`

Agent 使用：

- `POST /api/agent/human-decisions`
- `POST /api/agent/human-decisions/<decisionId>/execution-started`

Agent 请求必须通过受信任的 `X-VO-Agent-Id` 身份头解析，不能接受 body 中自报的 Agent 身份。管理端 `resolve` 提交用户选择，`reopen` 重新打开允许重试的决策；Agent 端 `execution-started` 只标记已开始继续执行。

## 安全与幂等

- 决策绑定来源 surface、Agent、conversation，以及可选 project/task/meeting 上下文。
- 只有 pending 决策可以解决；重复 callback、重复点击和重放不会再次恢复工作流。
- 选项值、补充输入和决策结果按各业务边界裁剪后传递。
- 无来源绑定、绑定过期、Agent 不匹配或恢复目标不存在时停止处理，不回退到其他聊天、项目或固定收件人。

## 验证

```bash
.venv/bin/python -m pytest -q \
  tests/test_human_decisions.py \
  tests/test_human_decision_delivery.py \
  tests/test_human_decision_runtime_pause.py \
  tests/test_human_decision_chat_continuation.py \
  tests/test_human_decision_feishu_sync.py \
  tests/test_human_decision_skill.py
node tests/check_human_decision_center.mjs
node tests/check_meeting_human_decision_record.mjs
node tests/check_project_human_decision_comment.mjs
```
