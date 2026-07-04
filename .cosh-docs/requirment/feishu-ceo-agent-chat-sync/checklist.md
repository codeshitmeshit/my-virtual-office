# Checklist

确认状态：已确认

真实飞书端到端人工验收步骤见 `manual-acceptance.md`。

当前 checklist 覆盖状态和剩余真实验收缺口见 `acceptance-audit.md`。

## 验收标准

### CHK-001 CEO assignment can be configured from a VO agent

- 关联需求点：VO 侧指定一个 agent 承担 CEO 身份。
- 验证方法：在 VO 配置中选择一个现有 agent 作为 CEO，并读取保存后的配置。
- 预期结果：配置保存成功，引用的是有效 VO agent，VO 能显示当前 CEO 身份和实际承接 agent。

### CHK-002 Feishu notification app and chat app are configured separately

- 关联需求点：配置项里有两个飞书应用，一个用于通知，一个用于聊天。
- 验证方法：查看配置读取、保存和脱敏展示，分别配置 notification app 与 chat app。
- 预期结果：通知应用配置保持原能力；聊天应用有独立 appId/appSecret/long connection 状态；两者不会互相覆盖或被默认混用。

### CHK-003 Feishu display includes role and underlying agent

- 关联需求点：飞书显示为 `CEO (by <Agent Name>)` 或等价本地化文案。
- 验证方法：触发一次 CEO 私聊回复或状态提示，检查飞书侧展示文案。
- 预期结果：用户能同时识别正在对话的是 CEO 角色，以及当前由哪个 VO agent 承担。

### CHK-004 Bound Feishu user can start CEO private chat

- 关联需求点：只有绑定 VO 账号的飞书用户可以和 CEO 对话。
- 验证方法：通过飞书长连接事件模拟或触发已绑定 Feishu sender ID 的私聊文本消息。
- 预期结果：VO 识别到对应 VO 用户，创建或复用该用户当前 CEO 会话，并写入用户消息。

### CHK-005 Unbound Feishu user is rejected clearly

- 关联需求点：未绑定用户不能创建正常 CEO 对话。
- 验证方法：通过飞书长连接事件模拟或触发未绑定 Feishu sender ID 的私聊文本消息。
- 预期结果：飞书收到清晰的绑定要求提示；VO 不创建正常 CEO conversation，不触发 CEO agent 回复。

### CHK-006 Feishu channel uses chat-app long connection only

- 关联需求点：第一版只支持飞书长连接能力，不支持其他接收模式。
- 验证方法：检查配置和入站消息处理路径，确认飞书私聊消息只通过 chat app 的 long connection event handler 进入。
- 预期结果：没有新增 webhook receiving、polling、log tailing 作为该功能的产品接收路径；未启用 chat app 长连接时该 channel 明确不可用或提示配置不足。

### CHK-007 Feishu messages use the existing message module

- 关联需求点：复用原消息模块，在其基础上支持飞书 channel 输入输出。
- 验证方法：从飞书发送私聊消息，然后检查消息模块收到的 normalized payload 和对应 VO 会话历史。
- 预期结果：飞书消息按现有消息模块格式写入，带有 `channel/sourceApp/sourceSurface/sourceMessageId/feishuChatId/representativeAgentId` 等来源字段。

### CHK-008 CEO response is persisted in VO and delivered to Feishu

- 关联需求点：VO 是唯一主记录，飞书作为入口和回复通道。
- 验证方法：从飞书发送一条消息并等待 CEO agent 回复。
- 预期结果：user 消息和 assistant 回复都写入 VO 消息记录，并成功发送回同一 Feishu 私聊；不存在关闭 VO 记录的配置项。

### CHK-009 VO can inspect Feishu-channel messages through existing history

- 关联需求点：VO 侧复用现有聊天/历史逻辑展示飞书 channel 消息。
- 验证方法：打开相关 VO 消息历史，检查飞书输入和 Agent 回复的展示。
- 预期结果：消息展示复用现有聊天/历史逻辑，且能看出消息来源于飞书 channel。

### CHK-010 Existing message UI and send pipeline are reused

- 关联需求点：不新增独立 CEO 私聊面板或独立消息模块。
- 验证方法：检查飞书 channel 消息的保存、展示、Agent 调用、回复记录是否走现有消息/Agent pipeline。
- 预期结果：实现只扩展 channel adapter 和代表 Agent 路由；普通聊天 UI、消息列表、发送态和错误态逻辑保持复用。

### CHK-011 CEO assignment change affects future Feishu messages

- 关联需求点：切换 CEO 承担 agent 后，后续飞书消息由新的代表 Agent 处理。
- 验证方法：配置 Agent A 为 CEO 并发送一条飞书消息；切换到 Agent B 后再发送一条飞书消息。
- 预期结果：第二条飞书消息由 Agent B 处理；旧会话不需要特殊迁移、归档或生命周期处理。

### CHK-012 Old representative chats require no special lifecycle handling

- 关联需求点：旧 CEO 标识会话可以不特别处理。
- 验证方法：切换 CEO 后检查旧会话状态。
- 预期结果：旧会话不会阻塞新代表 Agent 生效；系统不要求执行额外归档、关闭或迁移动作。

### CHK-013 Feishu inbound messages are idempotent

- 关联需求点：同步存储在 VO 侧且不能重复写入。
- 验证方法：重复投递或重复解析同一个 Feishu message ID。
- 预期结果：VO 消息模块只保存一条用户消息，不重复触发代表 Agent 回复。

### CHK-014 Concurrent messages keep stable ordering

- 关联需求点：飞书和可选 VO 侧继续发送都能进入可追踪会话。
- 验证方法：近同时从 Feishu 和 VO 发送消息，或模拟两个快速连续消息。
- 预期结果：消息有稳定排序；系统不会丢消息、覆盖消息或把回复写入错误会话。

### CHK-015 Missing CEO assignment has clear behavior

- 关联需求点：CEO 由 VO 侧指定 agent 承担。
- 验证方法：清空 CEO assignment 后，从 Feishu 和 VO 侧尝试发送 CEO 消息。
- 预期结果：用户看到清晰的未配置提示；系统不创建误导性的正常 CEO 回复。

### CHK-016 Unavailable assigned agent is handled safely

- 关联需求点：指定 VO agent 承担 CEO 身份。
- 验证方法：将 CEO 指向不可用、禁用或无法执行的 agent 后发送消息。
- 预期结果：用户收到失败提示；用户消息和失败状态按产品定义记录，系统不无限重试或写入错误 agent 回复。

### CHK-017 Private-chat scope is enforced

- 关联需求点：第一版只支持 Feishu 私聊，不支持群聊。
- 验证方法：模拟 Feishu 群聊消息、私聊消息和未知 chat type。
- 预期结果：只有私聊进入 CEO 对话；群聊不进入 CEO 一对一会话，并按产品定义忽略或提示不支持。

### CHK-018 Message metadata is auditable

- 关联需求点：消息需要记录发送方、渠道、时间和代表 Agent。
- 验证方法：检查持久化的 CEO conversation/message 记录。
- 预期结果：每条消息包含用户/assistant 身份、来源渠道、时间、Feishu source ID、Feishu chat ID、representativeAgentId 等必要审计字段，并沿用现有消息模块字段风格。

### CHK-019 Feishu-channel recording is mandatory

- 关联需求点：飞书 channel 的消息必须同步到 VO，不允许关闭记录。
- 验证方法：检查飞书 channel 配置项和消息处理路径，并模拟成功回复、失败回复、重复投递等场景。
- 预期结果：配置中不存在 `recordMessages=false` 或等价关闭项；所有有效飞书输入和输出结果都能在 VO 侧追踪。

### CHK-020 Existing Feishu notification and card-action flows are not regressed

- 关联需求点：新 CEO 私聊能力不能破坏已有飞书集成。
- 验证方法：运行既有 Feishu notification、card action、Project Execution/Meeting 飞书相关测试或等价回归，并同时启用独立 chat app 配置。
- 预期结果：现有飞书通知配置、发送记录、卡片动作和工作流通知行为保持不变，chat app 配置不会破坏 notification app。

### CHK-021 Existing VO chat, agent, and project flows are not regressed

- 关联需求点：CEO 是由现有 VO agent 承担的身份，并复用现有聊天逻辑。
- 验证方法：运行普通聊天、agent roster、Project Execution agent assignment、provider execution 相关聚焦回归。
- 预期结果：普通聊天、普通 agent 列表、项目任务分配和 provider 执行行为不受 CEO assignment 影响。

### CHK-022 Manual end-to-end verification

- 关联需求点：用户可以在飞书和 VO 两侧连续对话。
- 验证方法：用真实或可替代的 Feishu 私聊环境完成一次端到端验证：绑定用户、配置 CEO、飞书发消息、消息模块记录飞书 channel 输入、Agent 回复输出到飞书、切换 CEO 后再发消息。
- 预期结果：整条路径符合产品预期，VO 记录完整，飞书回复正确，切换 CEO 后未来飞书 channel 消息由新代表 Agent 处理。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-07-04T18:23:13+08:00
- 用户确认摘要：用户回复“可以出 todolist 了”，视为确认当前 checklist 并继续生成 todolist。

## 测试执行记录

- 执行时间：2026-07-04T18:38:26+08:00
- CHK-001/002/006：通过 `tests/test_feishu_notifications.py` 覆盖 chat app 与 notification app 分离配置、chat app long connection 状态、密钥脱敏和旧 notification app 配置保留。
- CHK-004/005/007/008/013/018/019：通过 `test_feishu_channel_adapter_records_and_dedupes` 和 `test_feishu_channel_unbound_user_does_not_dispatch_agent` 覆盖绑定用户入站、未绑定拒绝、不触发 Agent、复用 normalized payload、强制 JSONL 记录、assistant 回复输出和 sourceMessageId 幂等。
- CHK-006/017：通过 `test_feishu_long_connection_message_event_conversion` 覆盖 long connection 私聊消息事件转换；产品接收路径只新增 chat app long connection。
- CHK-020：通过 `tests/test_meeting_request_blocks_task.py` 与 Project Execution Feishu 聚焦用例验证既有 Feishu notification、card action、Project Execution 通知仍可运行。
- CHK-021：通过 `node --check app/game.js app/feishu-panel.js` 和 Python py_compile 验证前后端语法；普通聊天/provider 深度端到端未在本轮启动真实服务验证。
- CHK-022：未执行真实飞书环境人工端到端；当前使用 simulated long connection event 和 fake Feishu sender 覆盖核心链路。

已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/feishu_long_connection.py app/feishu_notifications.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
node --check app/game.js
node --check app/feishu-panel.js
```

## 补充测试执行记录

- 执行时间：2026-07-04T18:45:48+08:00
- CHK-004/005：新增并通过 `test_feishu_chat_bindings_config_is_persisted_and_lookupable`，覆盖 Feishu sender 绑定配置保存、清洗和 lookup。
- CHK-006/015/019：新增并通过 `test_feishu_channel_missing_chat_credentials_rejects_before_dispatch`，覆盖 chat app 启用但缺少 `appId/appSecret` 时提前拒绝、记录拒绝原因、不发送飞书回复、不触发代表 Agent。
- CHK-020：重新通过 `tests/test_feishu_notifications.py`、`tests/test_feishu_sync.py`、`tests/test_meeting_for_ai_phase4.py::test_phase4_request_quality_gate_and_pending_safety` 和 Project Execution Feishu 聚焦用例，确认 notification app、Feishu sync 与本需求 chat app 配置分离。
- 全量回归：执行 `PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py`，结果为 `292 passed, 22 failed, 1 warning`。失败集中在 Archive Room、Claude/Codex provider、Meeting/Project Cron 等既有模块；其中 `tests/test_feishu_notifications.py` 与 `tests/test_feishu_sync.py` 在全量过程中通过。由于全量基线仍有非本需求失败，不能据此声明全仓库回归全部通过。

补充已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/feishu_long_connection.py app/feishu_notifications.py tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests --ignore=tests/test_workflow_e2e.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_meeting_for_ai_phase4.py::test_phase4_request_quality_gate_and_pending_safety -q
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_feishu_notifications.py tests/test_feishu_sync.py -q
```

## 追加测试执行记录

- 执行时间：2026-07-04T18:48:38+08:00
- CHK-004/005：在设置页新增 Feishu chat bindings 输入和保存入口，支持一行一个 `open_id:ou_xxx=user-1`、`union_id:on_xxx=user-1` 等绑定，便于验收绑定/未绑定用户分支。
- CHK-006/017/019：新增并通过 `test_feishu_channel_empty_text_is_ignored_before_dispatch`，覆盖飞书 text 事件为空文本时只记录 `empty_text` 并忽略，不触发代表 Agent、不发送回复。
- CHK-020/021：重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

追加已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py app/feishu_long_connection.py app/feishu_notifications.py tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## HTTP Route 验证记录

- 执行时间：2026-07-04T18:51:05+08:00
- CHK-004/005：新增并通过 `test_feishu_chat_bindings_http_routes_persist_and_read`，直接覆盖 `/api/feishu-chat/bindings` 的 POST/GET route 分支，验证设置页调用的绑定接口会写入 `vo-config.json` 并可读回。
- CHK-020/021：重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

HTTP route 验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile tests/test_feishu_notifications.py app/server.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 历史审计字段验证记录

- 执行时间：2026-07-04T18:54:09+08:00
- CHK-007/009/018/021：补齐现有 provider 历史/comm event 的 Feishu source metadata 写入，确保 Feishu channel 消息进入既有 VO history 时保留 `channel/sourceMessageId/feishuChatId/representativeAgentId` 等审计字段。
- 新增并通过 `test_feishu_channel_metadata_is_written_to_hermes_history`，验证 Hermes 现有聊天历史中可读回 Feishu 来源字段。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

历史审计字段验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 长连接回调验证记录

- 执行时间：2026-07-04T18:56:06+08:00
- CHK-006/017：将 Feishu long connection receiver 的 card action/message event 处理拆为可测试实例方法；SDK 注册路径仍调用同一处理方法。
- 新增并通过 `test_feishu_long_connection_message_handler_is_invoked`，验证 chat app 长连接消息事件会被 normalized 并调用 `message_handler`，receiver 状态更新为 `running`。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

长连接回调验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/feishu_long_connection.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## Inbound Route 验证记录

- 执行时间：2026-07-04T18:58:17+08:00
- CHK-004/005/007/008/013/018/019：新增并通过 `test_feishu_chat_inbound_test_route_dispatches_and_records`，直接覆盖 `/api/feishu-chat/inbound-test` route，验证模拟 Feishu 私聊 payload 经 HTTP route 进入后会完成绑定用户识别、代表 Agent dispatch、飞书回复发送适配和 VO channel 记录落盘。
- 将测试中的 OfficeHandler 调用抽成无 socket 的 route harness，避免沙箱端口限制，同时覆盖真实 handler 分支。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

Inbound route 验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile tests/test_feishu_notifications.py app/server.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 飞书回复展示验证记录

- 执行时间：2026-07-04T19:00:59+08:00
- CHK-003/008/018：成功的 Feishu channel 回复现在通过输出 adapter 包装为 `CEO (by <Agent>):\n<reply>`，飞书侧能识别 CEO 角色和底层代表 Agent；VO 记录保留原始 `reply`，并额外记录实际发送到飞书的 `feishuReply`。
- 更新并通过 Feishu channel adapter 与 inbound route 测试，验证飞书发送文本包含 CEO/Agent 标识，VO channel 记录包含 `feishuReply`。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

飞书回复展示验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 代表 Agent 切换验证记录

- 执行时间：2026-07-04T19:04:29+08:00
- CHK-011/012/018：新增并通过 `test_feishu_channel_representative_agent_change_affects_future_messages`，验证同一飞书私聊在切换 `representativeAgentId` 后，后续不同 `message_id` 的消息会调用新的代表 Agent，并在 `turn_completed` 记录中写入新的 `representativeAgentId`。
- 测试同时确认旧记录无需迁移或关闭，Agent A 和 Agent B 的两条消息都保留各自的 source message 与代表 Agent 审计字段。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

代表 Agent 切换验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 不可用代表 Agent 验证记录

- 执行时间：2026-07-04T19:06:22+08:00
- CHK-016/018/019：新增并通过 `test_feishu_channel_unavailable_representative_agent_records_failure`，验证 `representativeAgentId` 指向不存在 Agent 时不会无限重试，会返回 `agent_failed`，把失败文本通过 Feishu output adapter 发回用户，并在 `turn_completed` 中记录 `agentResult.ok=false`、`_status=404`、`sendResult` 和 `representativeAgentId`。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

不可用代表 Agent 验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 私聊文本范围验证记录

- 执行时间：2026-07-04T19:08:05+08:00
- CHK-017/019：新增并通过 `test_feishu_channel_unsupported_chat_or_message_type_is_ignored`，验证群聊消息记录 `unsupported_chat_type`、非 text 消息记录 `unsupported_message_type`，两者均不触发代表 Agent、不发送飞书回复，只写 VO channel ignored 记录。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

私聊文本范围验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 强制记录验证记录

- 执行时间：2026-07-04T19:09:49+08:00
- CHK-019：新增并通过 `test_feishu_channel_recording_is_mandatory_even_if_disabled_in_config`，验证即使 chat app 配置中被人为塞入 `recordMessages=false`，Feishu channel 仍强制写入 `user_message` 和 `turn_completed` 记录。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

强制记录验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 代表 Agent 缺失配置验证记录

- 执行时间：2026-07-04T19:11:40+08:00
- CHK-002/015/016：新增并通过 `test_feishu_chat_config_rejects_unknown_representative_agent`，验证保存 chat app 配置时如果指定不存在的 `representativeAgentId` 会返回 `agent_not_found`。
- CHK-015/018/019：新增并通过 `test_feishu_channel_missing_representative_agent_does_not_dispatch`，验证已绑定用户入站但未配置代表 Agent 时，会发送清晰提示、不触发 Agent，并记录 `reason=missing_representative_agent` 和 `voUserId`。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

代表 Agent 缺失配置验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 连续消息顺序验证记录

- 执行时间：2026-07-04T19:13:42+08:00
- CHK-014/018：新增并通过 `test_feishu_channel_consecutive_messages_keep_order_and_conversation`，验证同一个飞书私聊连续两条不同 `message_id` 消息会按顺序 dispatch，使用同一个 `conversationId`，并按 `user_message/turn_completed/user_message/turn_completed` 顺序写入 VO channel 记录。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

连续消息顺序验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## 飞书文本发送验证记录

- 执行时间：2026-07-04T19:17:00+08:00
- CHK-008/020：新增并通过 `test_text_sender_uses_chat_app_credentials_without_leaking_secret`，验证 Feishu chat output helper 使用 chat app `appId/appSecret` 获取 tenant token，并调用 `/im/v1/messages?receive_id_type=chat_id` 发送 `msg_type=text` 文本消息。
- 测试同时验证返回结果不泄露 app secret 或 tenant token。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

飞书文本发送验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/feishu_notifications.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```

## VO 记录读取 API 验证记录

- 执行时间：2026-07-04T19:20:52+08:00
- CHK-009/018/019/022：新增只读 `GET /api/feishu-chat/records?limit=`，用于真实验收时从 VO 侧读取最近 Feishu channel 记录；新增并通过 `test_feishu_chat_records_route_reads_recent_channel_records`，验证 route 会按 limit 返回最近记录。
- `manual-acceptance.md` 已补充可用该 records API 检查真实端到端记录。
- 重新通过 Feishu channel 聚焦测试、Feishu sync、自执行 meeting request 回归和 Project Execution Feishu 聚焦回归。

VO 记录读取 API 验证已运行命令：

```bash
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m py_compile app/server.py tests/test_feishu_notifications.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_notifications.py
node --check app/game.js
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_feishu_sync.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python tests/test_meeting_request_blocks_task.py
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python - <<'PY'
import tests.test_project_execution as t
for name in [
 'test_feishu_start_failure_notification_dedupes_after_persisted_reload',
 'test_feishu_acceptance_notification_and_card_actions',
 'test_feishu_acceptance_rework_uses_default_feedback',
 'test_feishu_acceptance_rework_uses_card_feedback_input',
]:
    getattr(t, name)()
print('project feishu focused tests passed')
PY
git diff --check
```
