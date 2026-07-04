# Todolist

## TODO-001 Split Feishu Notification App And Chat App Configuration

- 目标：将现有飞书通知应用配置与新的飞书聊天应用配置拆开，避免通知能力和聊天 channel 共用同一组 app 凭证。
- 涉及区域：`app/server.py` 配置读写、setup/config API、前端配置页、配置脱敏展示。
- 输入：现有 `notifications.feishu*` 配置、需求中的 `notificationApp` 与 `chatApp` 双应用模型。
- 输出：独立的 notification app 配置保持兼容；新增 chat app 配置包含 `enabled`、`appId`、`appSecret`、`receiveMode=long_connection`、long connection 状态。
- 依赖：无。
- 完成标准：通知 app 和 chat app 可分别保存、读取、脱敏展示；chat app 不默认复用 notification app；旧通知配置不丢失。
- 关联 checklist：CHK-002、CHK-006、CHK-020。

## TODO-002 Add Feishu Representative Agent Setting

- 目标：新增“当前 CEO Agent / 飞书代表 Agent”配置项，用于决定飞书私聊 channel 的默认接待 Agent。
- 涉及区域：`app/server.py` 配置 API、agent roster 校验、前端配置页 agent 选择器、i18n 文案。
- 输入：现有 VO agent roster、用户选择的 `representativeAgentId`。
- 输出：可保存并读取的 `representativeAgentId`；配置保存时校验目标 Agent 存在；展示当前 CEO 角色和承接 Agent。
- 依赖：TODO-001。
- 完成标准：可选择任意有效 VO agent 作为代表；缺失或无效 agent 有清晰错误；切换配置后后续飞书消息使用新 agent。
- 关联 checklist：CHK-001、CHK-003、CHK-011、CHK-015、CHK-016。

## TODO-003 Extend Feishu Long Connection Receiver For Chat App Events

- 目标：让新的 chat app 通过飞书长连接接收私聊文本消息，并与现有通知/card-action long connection 能力隔离。
- 涉及区域：`app/feishu_long_connection.py`、`app/server.py` long connection 启停与状态、测试替身。
- 输入：chat app `appId/appSecret`、飞书私聊消息事件 payload。
- 输出：chat app long connection receiver 能接收 p2p 文本事件并调用统一 Feishu channel adapter；非 p2p 或非文本消息按范围规则拒绝或忽略。
- 依赖：TODO-001。
- 完成标准：只支持 chat app long connection；不新增 webhook receiving、polling、log tailing 产品路径；notification app long connection/card action 不回归。
- 关联 checklist：CHK-004、CHK-005、CHK-006、CHK-017、CHK-020。

## TODO-004 Implement Feishu User Binding Lookup For Channel Input

- 目标：在飞书消息进入消息模块前校验 Feishu sender 与 VO 用户绑定关系。
- 涉及区域：配置/状态存储、`app/server.py` binding API 或绑定读取逻辑、Feishu channel adapter。
- 输入：Feishu `sender_id/open_id/union_id`、`chat_id`、VO user identity。
- 输出：绑定用户可继续进入消息模块；未绑定用户收到绑定提示并不触发代表 Agent。
- 依赖：TODO-003。
- 完成标准：已绑定 sender 可通过；未绑定 sender 不创建正常 Agent 对话、不调用 Agent，并有可排查记录或返回提示。
- 关联 checklist：CHK-004、CHK-005。

## TODO-005 Add Feishu Channel Adapter On Existing Message Module

- 目标：将飞书私聊事件 normalized 成现有消息模块的输入 payload，而不是直接走 CEO 专用链路。
- 涉及区域：现有 chat/message send handlers、provider dispatch helpers、Feishu channel adapter。
- 输入：飞书私聊文本、绑定 VO 用户、代表 Agent 配置、source message metadata。
- 输出：标准消息 payload，包含 `channel=feishu`、`sourceApp=feishu`、`sourceSurface=feishu-dm`、`fromType=human`、`sourceMessageId`、`feishuChatId`、`representativeAgentId`。
- 依赖：TODO-002、TODO-004。
- 完成标准：飞书输入复用现有消息/Agent pipeline；普通 VO chat 输入不受影响；来源 metadata 沿用现有字段风格。
- 关联 checklist：CHK-007、CHK-009、CHK-010、CHK-018、CHK-021。

## TODO-006 Persist Mandatory Feishu-Channel Message Records

- 目标：确保所有有效飞书 channel 输入和输出都强制同步到 VO 消息记录，不提供关闭记录的配置。
- 涉及区域：现有 provider/chat history 保存逻辑、Feishu channel adapter、错误记录路径。
- 输入：normalized Feishu user message、assistant reply、失败状态、source metadata。
- 输出：VO 侧可追踪的 user/assistant 消息记录；记录包含渠道、飞书 message/chat ID、代表 Agent ID、时间和角色。
- 依赖：TODO-005。
- 完成标准：不存在 `recordMessages=false` 或等价关闭项；成功、失败、重复投递场景都可在 VO 侧追踪有效处理结果。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-018、CHK-019。

## TODO-007 Add Feishu Output Adapter For Assistant Replies

- 目标：当现有消息 pipeline 的输入 channel 为 Feishu 时，将 assistant reply 发送回同一个飞书私聊。
- 涉及区域：Feishu chat app client/send helper、message pipeline completion hook、错误处理。
- 输入：assistant reply、`feishuChatId`、chat app credentials、原始 message metadata。
- 输出：回复发送到同一 Feishu p2p chat；发送成功/失败结果写入 VO 记录。
- 依赖：TODO-003、TODO-006。
- 完成标准：Agent 回复成功发回飞书；发送失败不丢 VO 记录；只使用 chat app 发送聊天回复。
- 关联 checklist：CHK-008、CHK-018、CHK-019、CHK-022。

## TODO-008 Add Idempotency And Per-Conversation Ordering

- 目标：避免飞书重复投递或快速连续消息导致重复写入、重复触发 Agent 或上下文乱序。
- 涉及区域：Feishu channel adapter、消息存储、in-memory/file lock 或现有并发控制。
- 输入：Feishu `sourceMessageId`、`feishuChatId`、representative conversation key。
- 输出：基于 `sourceMessageId` 的幂等处理；同一 Feishu chat 或对应 VO conversation 的串行处理。
- 依赖：TODO-005、TODO-006。
- 完成标准：重复投递只产生一条用户消息且不重复触发 Agent；快速连续消息稳定排序，不覆盖或丢失。
- 关联 checklist：CHK-013、CHK-014。

## TODO-009 Surface Feishu Channel Messages In Existing VO History/UI

- 目标：让 VO 侧通过现有聊天/历史逻辑看到飞书 channel 输入和 Agent 回复，不新增独立 CEO 私聊面板。
- 涉及区域：`app/chat.js`、相关历史 API、消息渲染、来源标签显示。
- 输入：带 Feishu channel metadata 的消息记录。
- 输出：现有 VO 历史/聊天展示可识别 Feishu 来源，并显示当前代表 Agent 信息或来源标签。
- 依赖：TODO-006。
- 完成标准：消息展示复用现有 UI；用户能看出消息来自 Feishu channel；普通聊天 UI 不回归。
- 关联 checklist：CHK-003、CHK-009、CHK-010、CHK-021。

## TODO-010 Add Focused Automated Tests For Feishu Channel

- 目标：覆盖配置、长连接事件适配、绑定、消息模块复用、强制记录、幂等、代表 Agent 切换和回归。
- 涉及区域：`tests/` 中 Feishu、server、project/chat/provider 相关测试。
- 输入：可模拟的 chat app long connection event payload、fake representative Agent、fake Feishu send client。
- 输出：聚焦测试用例和必要测试 fixture。
- 依赖：TODO-001 至 TODO-009 的核心实现。
- 完成标准：自动测试覆盖 CHK-001 到 CHK-021 的可自动化部分；既有 Feishu notification/card-action 测试继续通过。
- 关联 checklist：CHK-001、CHK-002、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-011、CHK-013、CHK-014、CHK-015、CHK-016、CHK-017、CHK-018、CHK-019、CHK-020、CHK-021。

## TODO-011 Run Manual Or Simulated End-To-End Verification

- 目标：完成飞书私聊 channel 的端到端验收，确认真实或近真实链路符合产品预期。
- 涉及区域：Feishu chat app 配置、VO 设置页、飞书私聊、VO 消息历史。
- 输入：已绑定用户、有效 chat app、配置好的代表 Agent。
- 输出：端到端验证记录，包含绑定用户消息、未绑定用户消息、代表 Agent 切换后的未来消息、VO 记录检查。
- 依赖：TODO-010。
- 完成标准：飞书消息进入 VO 消息模块、Agent 回复回飞书、VO 记录完整、切换代表 Agent 后未来消息使用新 Agent。
- 关联 checklist：CHK-022。
