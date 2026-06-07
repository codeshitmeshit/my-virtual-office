# Phase4 Codex Harness MVP Todolist

## TODO-001 定义 Codex 协作者的产品身份与展示规则

- 目标：让 Codex 在办公室中以“可对话协作者”身份稳定出现，且用户能区分它不是 OpenClaw/Hermes agent。
- 涉及区域：agent roster、provider metadata、办公室 UI、agent workspace/详情展示、i18n 文案。
- 输入：`requirement.md` 中的身份定义；现有 OpenClaw/Hermes agent 展示规则；CHK-001、CHK-006、CHK-013。
- 输出：Codex agent 的显示名称、providerKind/provider label、状态标签、提示文案和中英文描述规则。
- 依赖：无。
- 完成标准：Codex 可见且身份清楚；不会被误解为完整项目 worker。
- 关联 checklist：CHK-001、CHK-006、CHK-013。

## TODO-002 设计 Codex 可用性与状态模型

- 目标：定义 Codex 的可用性判断和状态表达，覆盖 idle、working、error/needs attention。
- 涉及区域：provider status surface、presence/status 映射、不可用提示、活动日志。
- 输入：Phase 4 状态要求；现有 `/status`、`/api/presence`、Hermes/OpenClaw 状态模式；CHK-002、CHK-010。
- 输出：Codex 状态枚举、状态转换规则、不可用原因分类和用户可见提示规则。
- 依赖：TODO-001。
- 完成标准：用户能理解 Codex 当前是否可用、是否工作中、是否需要注意。
- 关联 checklist：CHK-002、CHK-010。

## TODO-003 定义 Codex 协作入口与消息流

- 目标：让用户可以通过办公室向 Codex 发起一次协作消息或任务意图。
- 涉及区域：聊天入口、agent-platform communication、Codex provider/harness入口、用户反馈。
- 输入：现有 chat/communication surfaces；Phase 4 “可对话协作者”范围；CHK-003。
- 输出：用户到 Codex 的协作发起路径、成功反馈、失败反馈和最低消息字段定义。
- 依赖：TODO-001、TODO-002。
- 完成标准：用户能发起协作，Codex 能产生回复、关键输出或明确失败原因。
- 关联 checklist：CHK-003、CHK-010。

## TODO-004 定义 OpenClaw/Hermes 到 Codex 的协作路径

- 目标：支持现有 OpenClaw/Hermes agent 通过办公室与 Codex 发生一次可追踪协作。
- 涉及区域：AgentPlatform-to-AgentPlatform Communications、provider routing、history/活动记录。
- 输入：`docs/AGENT_PLATFORM_COMMUNICATIONS.md`、`docs/VIRTUAL_OFFICE_AGENT_TOOLS.md`、现有 Hermes/OpenClaw 通信路径；CHK-004。
- 输出：OpenClaw/Hermes -> Codex 的发送、接收、回复或失败路径定义。
- 依赖：TODO-003。
- 完成标准：至少一次 OpenClaw 或 Hermes 到 Codex 的协作能被完整追踪。
- 关联 checklist：CHK-004、CHK-005。

## TODO-005 定义协作事件流数据契约

- 目标：保证协作事件流覆盖发起方、接收方、消息/任务意图、状态变化、关键输出和时间。
- 涉及区域：事件存储、history endpoint、活动日志、聊天气泡或等价追踪 surface。
- 输入：CHK-005；现有 `agent-platform-communications.jsonl` 约定；Hermes/OpenClaw history 形态。
- 输出：协作事件字段、事件类型、展示摘要、持久化与读取规则。
- 依赖：TODO-003、TODO-004。
- 完成标准：用户无需读底层日志即可理解一次协作上下文和结果。
- 关联 checklist：CHK-005、CHK-012。

## TODO-006 明确 Phase 4 与项目自动化边界

- 目标：确保 Phase 4 不引入 Codex 自动项目执行，也不让 UI 文案误导用户。
- 涉及区域：项目板、workflow 自动模式、agent workspace、帮助文案、禁用提示。
- 输入：非目标定义；CHK-006、CHK-007。
- 输出：Codex 在项目相关入口中的限制规则、禁用提示或隐藏策略。
- 依赖：TODO-001。
- 完成标准：Codex 不会被误认为可自动接项目任务；项目 workflow 不被 Codex MVP 改写。
- 关联 checklist：CHK-006、CHK-007。

## TODO-007 梳理敏感信息与日志展示边界

- 目标：避免 Codex 协作事件流暴露凭据、私密配置、环境变量或无过滤底层日志。
- 涉及区域：事件捕获、日志摘要、UI 展示、history API。
- 输入：安全约束；现有 Hermes “不读私密文件”原则；CHK-011。
- 输出：可展示信息白名单、需要过滤的信息类型、失败输出截断/摘要规则。
- 依赖：TODO-005。
- 完成标准：协作事件只展示用户需要理解的高层信息和关键输出。
- 关联 checklist：CHK-011。

## TODO-008 实现或调整 Codex 可见性与状态 surface

- 目标：把 TODO-001 和 TODO-002 的定义落到产品 surface 中。
- 涉及区域：server/provider discovery、presence/status API、前端 agent 渲染、状态提示。
- 输入：TODO-001、TODO-002 的输出。
- 输出：Codex agent 可见、状态可读、不可用提示可见的实际行为。
- 依赖：TODO-001、TODO-002、TODO-007。
- 完成标准：通过 CHK-001、CHK-002、CHK-010、CHK-013。
- 关联 checklist：CHK-001、CHK-002、CHK-010、CHK-013。

## TODO-009 实现或调整 Codex 协作消息与事件追踪

- 目标：完成用户/OpenClaw/Hermes 到 Codex 的 MVP 协作闭环，并记录事件流。
- 涉及区域：communication endpoint、Codex harness/provider bridge、event persistence、UI activity/history。
- 输入：TODO-003、TODO-004、TODO-005、TODO-007 的输出。
- 输出：一次可执行的 Codex 协作路径和可查看事件流。
- 依赖：TODO-003、TODO-004、TODO-005、TODO-007、TODO-008。
- 完成标准：通过 CHK-003、CHK-004、CHK-005、CHK-011、CHK-012。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-011、CHK-012。

## TODO-010 执行 OpenClaw 与 Hermes 回归验证

- 目标：确认 Phase 4 不破坏现有 OpenClaw/Hermes 行为。
- 涉及区域：OpenClaw discovery/chat/status/project workflow；Hermes discovery/chat/history/create/delete。
- 输入：现有测试脚本、手工验证路径、CHK-008、CHK-009。
- 输出：回归验证记录和发现问题清单。
- 依赖：TODO-008、TODO-009。
- 完成标准：OpenClaw/Hermes 核心路径保持可用，或已记录明确回归并修复。
- 关联 checklist：CHK-008、CHK-009。
- 环境说明：该任务依赖用户届时安装或提供 OpenClaw/Hermes 最小可用环境。进入 TODO-010 前必须提醒用户补齐环境；未补齐时只能记录为待验证，不能判定通过。
- 2026-06-08 回归记录：已在用户补齐环境后执行。OpenClaw discovery/workspace/files/heartbeat/modelEditable 通过；通信路径失败但错误明确记录为 `openclaw CLI not found in PATH`，且 18789 gateway 返回非有效 WebSocket/HTTP 响应。Hermes discovery/platform 可用，通信路径走到 Hermes CLI/session，但默认 profile 模型为 `anthropic/claude-opus-4.6`，当前后端只支持 `deepseek-v4-pro` 或 `deepseek-v4-flash`，因此真实回复失败；失败事件已写入 history 和 `/agent-chat`。本轮还修复了 OpenClaw providerKind 默认值误判导致 workspace 能力被隐藏的问题。
- 2026-06-08 Chrome E2E 复测：使用 Chrome DevTools 打开 `http://127.0.0.1:8097/`，页面渲染成功，三类 agent 均可见。页面内 fetch E2E 验证 `/api/agents`、`/status`、`/api/agent-platforms`、workspace、communication send、history 和 `/agent-chat`。Codex 通信成功；OpenClaw 通信失败原因为 `openclaw: Node.js v22.19+ is required (current: v22.17.1)`；Hermes 通信仍失败于默认 profile 模型 `anthropic/claude-opus-4.6` 不被当前后端接受。截图：`/tmp/virtual-office-chrome-e2e.png`，结果 JSON：`/tmp/chrome-e2e-result.json`。
- 2026-06-08 修复后回归：已将本机默认 Node 切到 v22.22.3，OpenClaw 2026.6.1 可执行；18789 被 Cursor NodeService 占用，因此将 OpenClaw gateway 配置、安装并重启到 18790，VO 回归环境显式连接 18790；Hermes 默认模型改为 `deepseek/deepseek-v4-flash`。最终 HTTP 回归验证 Codex、OpenClaw、Hermes 三条 communication/history/`/agent-chat` 路径均成功，回复分别包含 `codex fixed regression ack`、`openclaw fixed ack`、`hermes fixed ack 2`。

## TODO-010A 执行当前环境可立即完成的回归验证

- 目标：在无需 OpenClaw/Hermes 的情况下，先验证 Phase 4 可执行的 Codex MVP 与通用 UI/事件流行为。
- 涉及区域：Codex 协作者展示、状态提示、不可用提示、事件流结构、中英文文案、敏感信息展示边界。
- 输入：当前 Codex/开发环境；CHK-001、CHK-002、CHK-003、CHK-005、CHK-010、CHK-011、CHK-013。
- 输出：当前环境测试记录、失败项、待 OpenClaw/Hermes 环境补齐项。
- 依赖：TODO-008、TODO-009。
- 完成标准：不依赖 OpenClaw/Hermes 的 checklist 项完成验证，并明确剩余待环境补齐项。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-005、CHK-010、CHK-011、CHK-013。
- 2026-06-08 回归记录：`VO_CODEX_ENABLED=1` 下 `/api/agents`、`/agents-list`、`/status`、`/api/agent-workspace/codex-local`、`/api/codex/test` 通过；`/api/agent-platform-communications/send` 对 `codex-local` 返回确定性 demo reply；history endpoint 和 `/agent-chat` 均能展示 Codex request/reply。

## TODO-011 执行 Phase 4 人工验收闭环

- 目标：按 checklist 执行一次完整人工验收，确认 Phase 4 核心价值成立。
- 涉及区域：办公室 UI、Codex 协作者、协作入口、状态变化、事件流。
- 输入：已实现功能；完整 checklist。
- 输出：验收记录、截图或说明、失败项修复建议。
- 依赖：TODO-008、TODO-009、TODO-010A；完整验收依赖 TODO-010。
- 完成标准：看到 Codex -> 发起协作 -> 观察状态变化 -> 查看关键输出 -> 查看事件流的闭环成立。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-014。

## TODO-012 更新文档与阶段状态

- 目标：把 Phase 4 的产品范围、使用说明、非目标和验收方式同步到项目文档。
- 涉及区域：`docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`、agent tool docs、README 或 `.cosh-docs` 归档。
- 输入：最终实现行为、验收结果、已确认需求。
- 输出：文档更新、需求归档状态更新建议、后续 Phase 5/6/7 边界说明。
- 依赖：TODO-011。
- 完成标准：后续开发者能理解 Phase 4 已做什么、没做什么、下一阶段该做什么。
- 关联 checklist：CHK-006、CHK-007、CHK-013、CHK-014。
- 2026-06-08 更新：新增 `docs/CODEX_PROVIDER_ADAPTER.md`，更新 `docs/AGENT_PLATFORM_COMMUNICATIONS.md` 和 `docs/VIRTUAL_OFFICE_AGENT_TOOLS.md`，记录 Codex harness 启动变量、当前边界和回归方式。
- 2026-06-08 Phase5 补充：已将 live Codex CLI/session bridge 明确归入 Phase5，新增 `.cosh-docs/requirment/Phase5-Codex-Live-Bridge/requirement.md`，并更新 `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md` 与 `docs/CODEX_PROVIDER_ADAPTER.md`。
