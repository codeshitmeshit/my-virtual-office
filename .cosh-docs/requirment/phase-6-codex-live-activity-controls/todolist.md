# Phase 6 Codex Live Activity and Controls Todo List

执行状态：实现完成，等待最终人工验收与 live OpenClaw/Hermes 环境回归确认。

- TODO-001 至 TODO-016：已完成。
- TODO-017：自动化、HTTP E2E、浏览器 E2E、真实 Codex 和项目 CRUD 回归已完成；live OpenClaw/Hermes 回归及用户确认待完成。
- TODO-018：实现与验证记录已更新；`tested` 和 `done` 仍等待人工确认。

## 执行规则

- 按 Phase 6A、6B、6C 顺序实施；每一阶段完成自动化和真实环境验证后再进入下一阶段。
- 每个执行 plan 步骤必须引用一个或多个 `TODO-*`，代码和测试结果必须能回溯到关联的 `CHK-*`。
- deterministic fixtures 可用于自动化测试，但真实 Codex 验证必须显式设置 `_VO_INT=1` 并确认 `/api/license` 返回 `demo: false`，避免把 demo 响应误判为真实 bridge 行为。
- 不实现 VO conversation 级授权、授权摘要、手动撤销或 reset 清权；`acceptForSession` 仅表达 Codex 原生 runtime session 语义。

## Phase 6A：实时活动可见

### TODO-001 定义活动事件和运行状态模型

- 目标：建立 provider-neutral 的 Codex 活动、关联 ID、序列号和终态模型。
- 涉及区域：`app/providers/codex_bridge.py`、`app/providers/codex.py`，必要时新增同目录模型模块。
- 输入：Codex app-server item/turn/progress 通知、现有 Phase 5 execute 结果、Phase 6 状态设计。
- 输出：覆盖 command、file change、read/search、MCP、error 和未知 item 的标准事件结构，以及 running/terminal 状态转换。
- 依赖：无。
- 完成标准：事件含 conversation/thread/turn/item/sequence 标识；同一 item 增量更新不重复；未知类型安全降级；单元测试覆盖顺序、重复和终态。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-024。

### TODO-002 实现实时事件采集与桥接回调

- 目标：让持久 app-server client 在 turn 执行期间持续输出标准活动事件，而不只返回最终回复。
- 涉及区域：`app/providers/codex_bridge.py`、`app/providers/codex.py`、`tests/test_codex_bridge.py`、`tests/test_codex_provider.py`。
- 输入：TODO-001 事件模型、app-server JSON-RPC 通知和输出 delta。
- 输出：事件 callback/subscriber 接口、批处理增量输出、最终结果与活动轨迹一致性处理。
- 依赖：TODO-001。
- 完成标准：fake app-server 可稳定产生各类事件；高频 delta 被合并；完成、失败和协议错误只产生一个终态。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-024、CHK-025。

### TODO-003 实现脱敏、截断与安全存储边界

- 目标：所有实时和持久化工具数据在离开 bridge 前完成递归脱敏和有界化。
- 涉及区域：Codex provider/bridge 安全辅助模块、`tests/` 安全测试。
- 输入：事件参数、输出、错误、URL、headers、环境变量式数据和嵌套对象。
- 输出：统一 redaction/truncation API、截断元数据、可观测统计。
- 依赖：TODO-001。
- 完成标准：测试 token、API key、Authorization、Cookie、凭据 URL 等不会出现在事件、历史或日志；大 payload 保留身份和状态并明确标记截断。
- 关联 checklist：CHK-006、CHK-007、CHK-008。

### TODO-004 持久化活动轨迹并提供历史接口

- 目标：按 conversation 保存不可变序列事件，使刷新后可以恢复已完成和运行中的轨迹。
- 涉及区域：`app/server.py`、`VO_STATUS_DIR` 状态文件、`tests/test_codex_server.py`。
- 输入：TODO-002 安全标准事件、现有 Codex conversation/thread 映射和 history 结构。
- 输出：原子持久化、历史读取、事件去重、运行中快照和兼容旧 history 的 API。
- 依赖：TODO-002、TODO-003。
- 完成标准：刷新读取顺序稳定且无重复；旧 Phase 5 history 正常渲染；损坏或缺失状态安全降级。
- 关联 checklist：CHK-005、CHK-019、CHK-021、CHK-026。

### TODO-005 建立 Codex 实时浏览器传输

- 目标：把活动事件实时推送到正确 conversation，并支持断线后的序列补偿。
- 涉及区域：`app/server.py` 的实时接口、`app/chat.js` 的订阅和重连逻辑。
- 输入：TODO-004 事件存储、现有办公室 realtime/WebSocket 能力。
- 输出：带 sequence/correlation ID 的订阅协议、重连补拉和跨 conversation 过滤。
- 依赖：TODO-004。
- 完成标准：事件只进入目标聊天；断线重连不丢失、不重复；传输失败不会破坏最终同步回复。
- 关联 checklist：CHK-002、CHK-019、CHK-022、CHK-024。

### TODO-006 实现可展开 Codex 工具卡片

- 目标：复用既有工具卡片视觉模型展示 Codex 实时活动和安全详情。
- 涉及区域：`app/chat.js`、`app/style.css`、`app/index.html`、`app/i18n.js`、`app/locales/*.json`。
- 输入：TODO-005 浏览器事件、OpenClaw/Hermes 现有工具卡片交互。
- 输出：运行/完成/失败卡片、展开详情、旧卡片折叠、截断和数据可见性提示。
- 依赖：TODO-005。
- 完成标准：当前活动优先展开，旧活动可折叠恢复；大轨迹保持响应；OpenClaw/Hermes 卡片无回归。
- 关联 checklist：CHK-004、CHK-005、CHK-007、CHK-008、CHK-027。

### TODO-007 完成 Phase 6A 自动化与真实验收

- 目标：独立验证只读实时活动阶段并记录结果。
- 涉及区域：`tests/`、浏览器/E2E 测试、`checklist.md` 阶段确认记录。
- 输入：TODO-001 至 TODO-006、deterministic fixtures、真实 Codex 短任务。
- 输出：单元/集成/UI 测试结果、Phase 5 回归结果、真实浏览器证据和 6A 阶段验收记录。
- 依赖：TODO-001 至 TODO-006。
- 完成标准：CHK-001 至 CHK-008、CHK-019、CHK-025、CHK-026 及 CHK-027 对应部分通过；真实测试显式设置 `_VO_INT=1` 并确认 `demo: false`；无泄密、重复事件或缺失终态。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-019、CHK-025、CHK-026、CHK-027。

## Phase 6B：人工介入控制

### TODO-008 实现可恢复的 pending interaction broker

- 目标：在 app-server 请求等待期间保存审批或问题状态，并把人类响应送回原 JSON-RPC 请求和原 turn。
- 涉及区域：`app/providers/codex_bridge.py`、`app/providers/codex.py`、`app/server.py`、对应单元测试。
- 输入：approval request、tool user-input request、conversation/thread/turn/item ID。
- 输出：pending interaction 状态机、唯一 action token、超时/重复提交保护和原 turn 续跑。
- 依赖：TODO-001 至 TODO-005、Phase 6A 通过。
- 完成标准：pending 状态先持久化再展示；只接受 owning human 的一次有效响应；普通消息不能被误当作回答。
- 关联 checklist：CHK-009、CHK-010、CHK-012、CHK-013、CHK-014、CHK-024。

### TODO-009 实现审批 API 与真实授权语义

- 目标：支持允许一次、Codex runtime session 允许和拒绝，并准确呈现权限范围。
- 涉及区域：`app/server.py` Codex API、`app/providers/codex_bridge.py`、服务端测试。
- 输入：TODO-008 pending approval、协议 `accept`、`acceptForSession`、`decline/cancel` 决策。
- 输出：审批提交端点、权限类别校验、决策审计信息和 fail-closed 错误处理。
- 依赖：TODO-008。
- 完成标准：决策续跑或终止原 turn；`acceptForSession` 不与 VO conversation 绑定；无授权摘要、撤销或 reset 清权的虚假 API。
- 关联 checklist：CHK-009、CHK-010、CHK-012、CHK-024。

### TODO-010 实现用户补充回答与 Agent fail-closed

- 目标：让真人提交结构化或自由文本答案，同时阻止 OpenClaw/Hermes 自动处理交互请求。
- 涉及区域：`app/server.py`、Codex provider/bridge、agent communication 路由和测试。
- 输入：TODO-008 pending question、question IDs/options、消息来源身份。
- 输出：answer API、来源权限校验、`needs_human_intervention` Agent 终态。
- 依赖：TODO-008。
- 完成标准：答案关联原问题并续跑原 turn；普通消息被明确拒绝；Agent 来源不进入无限等待也不能批准/回答。
- 关联 checklist：CHK-013、CHK-014、CHK-015、CHK-024、CHK-027。

### TODO-011 实现运行中与等待中取消

- 目标：统一取消 running、waiting approval 和 waiting input 的活动 turn。
- 涉及区域：`app/providers/codex_bridge.py`、`app/server.py`、状态持久化和测试。
- 输入：active operation、pending interaction、app-server `turn/interrupt`。
- 输出：cancel API、cancelling 状态、幂等终态清理和已修改文件证据。
- 依赖：TODO-008。
- 完成标准：重复取消安全；挂起 action 失效；锁和 presence 最终释放；界面和历史明确取消不回滚文件。
- 关联 checklist：CHK-016、CHK-017、CHK-018、CHK-024。

### TODO-012 实现审批、回答和取消 UI

- 目标：在聊天工具卡片内提供人类可操作控件和明确状态反馈。
- 涉及区域：`app/chat.js`、`app/style.css`、`app/index.html`、本地化文件、浏览器测试。
- 输入：TODO-009 至 TODO-011 API 和 pending 事件。
- 输出：审批按钮、问题表单、取消按钮、waiting/cancelling/terminal 展示和重复操作禁用。
- 依赖：TODO-009、TODO-010、TODO-011。
- 完成标准：两种允许语义清晰；操作作用于原卡片和原 turn；等待期间发送框行为无歧义；取消后显示遗留修改提示。
- 关联 checklist：CHK-009、CHK-010、CHK-012、CHK-013、CHK-014、CHK-016、CHK-017、CHK-018、CHK-028。

### TODO-013 完成 Phase 6B 自动化与真实验收

- 目标：独立验证人工介入控制并记录阶段结果。
- 涉及区域：fake app-server、服务端和浏览器测试、`checklist.md` 阶段确认记录。
- 输入：TODO-008 至 TODO-012、真实命令/文件审批、真实问题和可取消任务。
- 输出：审批/回答/取消竞态测试、真实 Codex 验证和 6B 阶段验收记录。
- 依赖：TODO-008 至 TODO-012。
- 完成标准：Phase 6B 必过项通过；所有交互作用于原 turn；真实测试显式设置 `_VO_INT=1` 并确认 `demo: false`；锁、presence 和 pending 状态在所有终态正确清理。
- 关联 checklist：CHK-009、CHK-010、CHK-012、CHK-013、CHK-014、CHK-015、CHK-016、CHK-017、CHK-018、CHK-024、CHK-025、CHK-026、CHK-027。

## Phase 6C：恢复与生产加固

### TODO-014 实现刷新和服务重启后的状态对账

- 目标：恢复活动与 pending 卡片，并安全终止无法在新进程中续接的协议请求。
- 涉及区域：`app/server.py`、`app/providers/codex_bridge.py`、状态文件、浏览器恢复逻辑和测试。
- 输入：持久事件、active operation、pending interaction、`thread/read(includeTurns=true)`。
- 输出：启动对账、序列去重、可恢复/不可恢复分类和无效 action 清理。
- 依赖：Phase 6B 通过。
- 完成标准：刷新可继续操作原 pending 请求；服务重启不展示虚假按钮或永久 busy；历史和 thread 状态一致。
- 关联 checklist：CHK-019、CHK-020、CHK-021、CHK-024。

### TODO-015 完善 presence、单活动任务和跨窗口定位

- 目标：区分 running 与 waiting-for-user，并让其他窗口定位活动 conversation。
- 涉及区域：`app/server.py` active-operation/presence、`app/chat.js`、`app/game.js`、浏览器测试。
- 输入：全局 Codex 活动记录、conversation ID、多窗口发送请求。
- 输出：waiting presence、busy 响应中的活动会话信息、跳转/聚焦操作。
- 依赖：TODO-014。
- 完成标准：第二个请求不创建并行 turn；所有窗口显示一致 owner；终态后锁和 presence 无残留。
- 关联 checklist：CHK-020、CHK-022、CHK-024、CHK-028。

### TODO-016 加固终态、竞态和可观测性

- 目标：覆盖协议异常、超时、取消竞争、断线和重复事件，形成可诊断的稳定生命周期。
- 涉及区域：bridge/server 状态机、日志与指标、故障注入测试。
- 输入：completed、failed、timeout、cancelled、rejected、bridge unavailable、协议错误和 delivery gap。
- 输出：唯一终态规则、correlation 日志、gap/duplicate/redaction/truncation/latency 指标。
- 依赖：TODO-014、TODO-015。
- 完成标准：终态矩阵全部释放资源；日志不含敏感 payload；重复或迟到事件不能改变已确定终态。
- 关联 checklist：CHK-006、CHK-007、CHK-024。

### TODO-017 完成全量回归与浏览器验收

- 目标：执行 Phase 6C、Phase 6A/6B 回归和 Phase 5/provider 全链路验收。
- 涉及区域：全部自动化测试、启动脚本、真实服务、浏览器 E2E、`checklist.md` 测试记录。
- 输入：TODO-001 至 TODO-016、deterministic fixtures、真实 Codex/OpenClaw/Hermes 环境。
- 输出：完整测试报告、失败证据与修复回归、CHK-028 人工验收准备结果。
- 依赖：TODO-001 至 TODO-016。
- 完成标准：26 项 checklist 全部通过或记录用户接受的限制；真实 Codex 场景显式设置 `_VO_INT=1` 并确认 `demo: false`；Phase 5、OpenClaw、Hermes、demo、刷新、重启和多窗口无回归。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008、CHK-009、CHK-010、CHK-012、CHK-013、CHK-014、CHK-015、CHK-016、CHK-017、CHK-018、CHK-019、CHK-020、CHK-021、CHK-022、CHK-024、CHK-025、CHK-026、CHK-027、CHK-028。

### TODO-018 更新交付文档并完成阶段确认

- 目标：把实际协议、限制、启动验证步骤和三阶段测试结果写入需求归档及项目文档。
- 涉及区域：本需求 `requirement.md`、`review.md`、`checklist.md`、`status.json`，以及项目现有用户/开发文档。
- 输入：实现结果、测试报告、已知限制和用户阶段确认。
- 输出：准确文档、6A/6B/6C 阶段确认记录、最终测试确认入口。
- 依赖：TODO-017。
- 完成标准：文档不宣称 conversation 授权、撤销或自动回滚；所有 TODO/CHK 可追溯；等待用户确认测试通过后才推进 `tested`，等待最终确认后才推进 `done`。
- 关联 checklist：CHK-008、CHK-010、CHK-018、CHK-026、CHK-027、CHK-028。
