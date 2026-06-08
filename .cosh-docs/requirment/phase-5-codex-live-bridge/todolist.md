# Phase 5 Codex Live Bridge Todo List

## TODO-001 Define the normalized bridge contract

- 目标：定义 Virtual Office 与 Codex bridge 之间稳定、可测试的请求、响应和错误模型。
- 涉及区域：`app/providers/`、Codex provider 文档、测试 fixtures。
- 输入：已确认的 app-server 线程/turn/compaction能力，现有 `CodexProvider.send_message` 返回结构。
- 输出：包含 conversation/thread/turn、terminal status、reply、modified files、intervention、timing 和 structured error 的内部契约。
- 依赖：无。
- 完成标准：正常、busy、timeout、approval-required、bridge-unavailable、execution-failed 和 compaction 均有明确稳定字段；现有 demo mode 可映射到同一结果模型。
- 关联 checklist：CHK-001、CHK-002、CHK-009、CHK-010、CHK-012、CHK-013、CHK-017、CHK-018、CHK-019。

## TODO-002 Implement the Codex app-server bridge client

- 目标：通过 app-server JSONL 协议初始化 Codex、创建/恢复 thread、启动 turn、收集终态和文件事件，并执行 thread compaction。
- 涉及区域：新增 `app/providers/` bridge 模块或相邻专用模块、进程管理测试。
- 输入：TODO-001 契约、本机 app-server schema、`VO_CODEX_WORKSPACE`、模型和超时配置。
- 输出：可启动本地 `codex app-server` 的 bridge client，并支持 `VO_CODEX_BRIDGE_URL` 外部覆盖。
- 依赖：TODO-001。
- 完成标准：完成初始化握手；支持 `thread/start`、`thread/resume`、`turn/start`、`thread/compact/start`；能可靠关联 response/notification；进程退出和畸形协议转成结构化错误。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-006、CHK-012、CHK-013、CHK-020。

## TODO-003 Enforce sandbox and approval termination

- 目标：限制 Codex 在绑定工作区内执行，并在出现审批请求时 fail closed。
- 涉及区域：bridge 启动/turn 参数、approval notification 处理、错误分类测试。
- 输入：正常 workspace sandbox 策略、Phase 5 不提供审批交互的边界。
- 输出：workspace-write 范围配置、approval-required 到 `needs_human_intervention` 的终态转换。
- 依赖：TODO-002。
- 完成标准：不自动批准；工作区外或网络等受限操作明确终止；错误文本不泄露凭据或敏感配置。
- 关联 checklist：CHK-010、CHK-016、CHK-017。

## TODO-004 Add durable conversation-to-thread storage

- 目标：持久化办公室 `conversationId` 与 Codex thread ID 的映射，并提供读取、写入、失效和损坏恢复能力。
- 涉及区域：`VO_STATUS_DIR` 状态文件、server/provider session helper、单元测试。
- 输入：现有 conversation ID 生成规则和 app-server thread ID。
- 输出：原子写入的持久化映射及 reset API helper。
- 依赖：TODO-001。
- 完成标准：刷新和服务重启后恢复同一 thread；不同会话不串线；损坏数据安全失败；reset 后下一请求创建新 thread。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-015。

## TODO-005 Add the single-active-operation guard

- 目标：保证一个 Codex collaborator 同时最多执行一个 turn 或 compaction。
- 涉及区域：Codex provider/server lifecycle、并发测试、presence 清理。
- 输入：send、compact 两类操作及现有 gateway presence API。
- 输出：原子 busy guard、稳定 busy response、所有终态的 lock/presence cleanup。
- 依赖：TODO-001。
- 完成标准：后发消息或压缩立即被拒绝且不排队；异常和超时后锁可再次获取；presence 不残留 working。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-012。

## TODO-006 Integrate live execution into CodexProvider and office routing

- 目标：把 live bridge 接入现有 Codex adapter 和 `/api/agent-platform-communications/send`，保持其他 provider 行为不变。
- 涉及区域：`app/providers/codex.py`、`app/server.py`、配置加载和 endpoint 测试。
- 输入：TODO-002 bridge、TODO-004 mapping、TODO-005 busy guard。
- 输出：真实 send path、终态 HTTP/JSON 映射、兼容的 demo/no-bridge path。
- 依赖：TODO-002、TODO-003、TODO-004、TODO-005。
- 完成标准：真人、OpenClaw 和 Hermes 发往 Codex 都复用 live path；非法输入有稳定错误；OpenClaw/Hermes 非 Codex 路由无变化。
- 关联 checklist：CHK-001、CHK-007、CHK-009、CHK-011、CHK-014、CHK-019、CHK-020、CHK-021、CHK-022。

## TODO-007 Persist structured execution and compaction events

- 目标：让办公室历史可追溯 Codex 的 thread、turn、终态、修改文件、人工介入和压缩结果。
- 涉及区域：communication event metadata、history API、agent-chat 合并兼容性。
- 输入：TODO-001 结果模型、现有 JSONL communication log。
- 输出：向后兼容的结构化 metadata 和 operation events。
- 依赖：TODO-006。
- 完成标准：历史文本渲染不回归；成功和各类失败可结构化区分；日志包含关联 ID 且不含凭据。
- 关联 checklist：CHK-001、CHK-002、CHK-006、CHK-010、CHK-012、CHK-017、CHK-018。

## TODO-008 Add reset and compact server endpoints

- 目标：提供明确的会话重置与上下文压缩操作，复用映射和忙碌规则。
- 涉及区域：`app/server.py` HTTP handlers、Codex provider API、endpoint tests。
- 输入：TODO-002 compaction、TODO-004 reset helper、TODO-005 guard。
- 输出：reset/clear integration 和 compact endpoint，包含 working/success/failure 响应。
- 依赖：TODO-002、TODO-004、TODO-005、TODO-007。
- 完成标准：reset 失效映射但不产生隐藏旧上下文；compact 保留 conversation/thread/visible history；busy 时两类操作行为确定。
- 关联 checklist：CHK-005、CHK-006、CHK-008、CHK-018。

## TODO-009 Add the Codex conversation controls to the UI

- 目标：在人类用户的 Codex 聊天界面提供可理解的 busy、修改文件、人工介入、重置和压缩体验。
- 涉及区域：`app/game.js` 及相关 HTML/CSS，浏览器交互测试。
- 输入：TODO-006/007/008 endpoints 和 metadata。
- 输出：压缩上下文操作、clear/new conversation 联动、状态与结果呈现。
- 依赖：TODO-006、TODO-007、TODO-008。
- 完成标准：用户能识别 working/terminal 状态；busy 时不能误发；文件清单可见；压缩不清空聊天；reset 后开始新上下文。
- 关联 checklist：CHK-002、CHK-005、CHK-006、CHK-007、CHK-009、CHK-010、CHK-023。

## TODO-010 Build focused unit and integration coverage

- 目标：用 fake app-server/bridge 覆盖协议、并发、持久化、错误分类和兼容路径。
- 涉及区域：`tests/`、现有 `tests/test_codex_provider.py`、测试辅助进程/fixtures。
- 输入：TODO-001 至 TODO-009 的行为。
- 输出：可重复、无需真实账号的自动化测试组。
- 依赖：TODO-006、TODO-007、TODO-008、TODO-009。
- 完成标准：自动覆盖 checklist 中可自动化的正常、边界、错误、安全和回归场景；测试运行不修改用户真实 Codex 状态。
- 关联 checklist：CHK-001 至 CHK-022。

## TODO-011 Run live and browser acceptance

- 目标：在本机真实 Codex 环境完成端到端验证，并执行浏览器人工验收流程。
- 涉及区域：运行中的 Virtual Office、Codex app-server、测试工作区、浏览器 UI。
- 输入：已完成实现、已确认 checklist。
- 输出：逐项测试结果、失败证据和修复回归记录。
- 依赖：TODO-010。
- 完成标准：CHK-001 至 CHK-023 均记录通过或明确阻塞原因；未通过项修复后重新验证；不得提前标记 tested。
- 关联 checklist：CHK-001 至 CHK-023。

## TODO-012 Update operator and provider documentation

- 目标：记录 Phase 5 配置、启动模式、安全边界、会话生命周期、压缩、错误分类和排障方式。
- 涉及区域：`docs/CODEX_PROVIDER_ADAPTER.md`、`docs/AGENT_PLATFORM_COMMUNICATIONS.md`、`.env.example`、必要的 README/配置说明。
- 输入：最终实现与测试结论。
- 输出：与实际代码一致的部署和使用文档。
- 依赖：TODO-011。
- 完成标准：本地自动 bridge、外部 URL override、demo mode、workspace/approval 限制、reset/compact 行为和已知 Phase 6 边界均有说明。
- 关联 checklist：CHK-019、CHK-020、CHK-021、CHK-022、CHK-023。
