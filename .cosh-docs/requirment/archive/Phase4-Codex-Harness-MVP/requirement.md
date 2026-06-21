# Phase4 Codex Harness MVP 需求

## 背景

Virtual Office 当前已经具备 OpenClaw 原生运行体验，并已实现 Hermes adapter 的 first implementation。根据 `docs/UNIVERSAL-AGENT-HARNESS-SPEC.md`，Phase 4 的目标是建立 generic harness provider framework，让没有 OpenClaw Gateway 的 agent 也能作为办公室中的一等协作者出现。

经过产品澄清，本期 Phase 4 不追求完整项目自动化，而是先以 Codex 作为第一个非 Gateway agent MVP，验证“可见、可对话、可追踪”的产品价值。

## 目标用户

- 主要用户：高级用户/自用场景用户。
- 用户目标：把 Codex、OpenClaw、Hermes 等不同来源的 agent 放进同一个 Virtual Office，并能看到它们的身份、状态、协作事件和关键输出。
- 使用者与决策者通常是同一人：自托管 Virtual Office 的高级用户或开发者。

## 产品目标

1. Codex 作为非 Gateway agent 能在办公室中作为可对话协作者出现。
2. 用户或其他 agent 能通过办公室向 Codex 发起协作消息，并看到 Codex 的回复或关键输出。
3. 协作过程形成可追踪事件流，至少覆盖消息、状态变化、任务意图和关键输出。
4. Phase 4 明确建立可扩展的 harness 产品形态，为后续 Claude Code、更多 Codex worker、以及 Phase 7 的 universal projects/automations 做准备。

## 范围

### 本期必须包含

- Codex 作为首个非 Gateway agent 的 MVP 接入对象。
- Codex 在办公室中具备稳定身份，可被用户理解为“可对话协作者”。
- Codex 的状态可见，至少能表达 idle、working、error/needs attention 等关键状态。
- 用户或其他 agent 能通过办公室与 Codex 发生一次可追踪协作。
- 协作事件流进入统一活动记录或可等价追踪的 office surface。
- 事件流至少包含：发起方、接收方、消息/任务意图、状态变化、关键输出、时间。
- 不影响现有 OpenClaw 与 Hermes 行为。

### 本期非目标

- 不做完整项目自动化。
- 不接入 live Codex CLI/session；真实驱动 Codex 执行任务归入 Phase5 Codex Live Bridge。
- 不要求 Codex 自动接项目板任务、跑 workflow、进入 review 或完成项目交付闭环。
- 不做多 agent 调度策略。
- 不承诺统一代理所有工具能力，例如浏览器、文件、命令、审批等深度控制。
- 不把 Phase 4 做成完整第三方平台生态或插件市场。

## 关键约束

- Phase 4 的第一性目标是“可见性 + 可对话协作 + 可追踪事件流”。
- Codex 应被包装为可对话协作者，而不是完整项目 worker。
- 协作事件流必须能被用户理解和审计，不能只是隐藏在后端日志里。
- 现有 OpenClaw 原生体验、Hermes adapter、AgentPlatform 通信、项目板和聊天面板不能被破坏。
- 任何敏感信息、原始私密日志或授权凭据都不应被暴露到办公室 UI。

## 已澄清结论

- 目标用户：高级用户/自用场景。
- 核心价值：看见所有 agent。
- MVP 对象：Codex。
- MVP 身份：可对话协作者。
- 可追踪标准：协作事件流，包含消息、状态变化、任务意图和关键输出。
- 成功标准：非 OpenClaw Codex agent 能与 OpenClaw/Hermes agent 完成一次可追踪协作。
- 明确排除：完整项目任务自动化。

## 成功标准

Phase 4 MVP 可以被认为成功，当且仅当：

1. 用户能在 Virtual Office 中看到一个 Codex 协作者。
2. 用户能识别 Codex 当前是否空闲、工作中或需要注意。
3. 用户或现有 agent 能向 Codex 发起协作消息。
4. Codex 的回复或关键输出能被办公室记录并呈现。
5. 一次 OpenClaw/Hermes 与 Codex 的协作能通过事件流追踪完整上下文。
6. 现有 OpenClaw/Hermes 功能没有发生回归。
