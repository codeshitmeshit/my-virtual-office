# Phase4 Codex Harness MVP 方案评审

## 评审结论

当前需求已经完成必要的产品澄清，可以进入 checklist 确认阶段。没有发现必须阻塞 checklist 生成的产品问题或技术问题。

建议将 Phase 4 严格限定为 Codex Harness MVP：让 Codex 作为非 Gateway agent 在办公室里可见、可对话、可追踪。完整项目自动化应留到 Phase 7，避免 Phase 4 范围失控。

## 产品评审

### 清晰点

- 目标用户清晰：高级用户/自用场景。
- MVP 对象清晰：Codex。
- 产品身份清晰：Codex 是可对话协作者，不是完整项目 worker。
- 核心价值清晰：看见所有 agent，并让协作可追踪。
- 范围边界清晰：不做完整项目自动化，不要求 Codex 自动接项目板任务。

### 仍需注意

- “可追踪事件流”的 UI/信息层级需要保持克制，避免把用户淹没在低层日志中。
- Codex 的能力边界需要在 UI 文案中明确，避免用户误以为它已经能自动执行完整项目工作流。
- 如果后续把 Codex 接入项目任务，必须重新评审并重新生成 checklist。

## 技术评审

### 架构边界

当前代码已存在以下基础：

- OpenClaw 原生 agent 路径。
- Hermes provider adapter。
- AgentPlatform-to-AgentPlatform communications。
- Presence/status surfaces。
- Skills Library 与 agent-facing tool index。
- Browser/status/project 等 office-owned surfaces。

Phase 4 应在这些基础上补齐通用 harness provider 的最小产品能力，不应把 Codex 硬塞进 OpenClaw 或 Hermes 的特殊路径。

### 接口与状态流

需要保证 Codex 的身份、状态、消息和事件能被统一 office surface 消费。状态流至少需要覆盖：

- idle：可被发起协作。
- working：正在处理协作请求。
- needs attention/error：需要用户注意或发生失败。

事件流至少需要记录：

- 发起方与接收方。
- 协作意图或消息摘要。
- 状态变化。
- 关键输出。
- 时间戳。

### 数据与持久化

事件需要可追踪、可恢复、可被 UI 或状态接口读取。实现时应避免依赖临时内存作为唯一事实来源。具体存储形态可在技术设计中细化，但产品验收必须关注可追踪性和重启后的合理表现。

### 权限与安全

Phase 4 不应暴露 Codex 的原始凭据、私密配置或完整敏感日志。协作事件流应展示用户需要理解的高层信息和关键输出，而不是无过滤地公开底层执行细节。

### 兼容性与迁移

必须保持：

- OpenClaw agent discovery/chat/status 不回归。
- Hermes discovery/chat/create/delete 不回归。
- 现有项目板 workflow 不被误改成依赖 Codex。
- Demo/license feature gate 行为不被意外绕过。

### 可观测性

需要可从 UI 或 API 判断：

- Codex 是否可用。
- Codex 当前状态。
- 最近协作事件。
- 失败原因或不可用原因。

### 测试可行性

Phase 4 可以通过以下方式验证：

- API/状态接口验证 Codex 身份和状态。
- UI 验证 Codex 可见、禁用/错误状态有提示。
- 一次用户到 Codex 的协作验证。
- 一次 OpenClaw/Hermes 到 Codex 的协作验证。
- 回归验证 OpenClaw/Hermes 原有路径。

## 阻塞问题

暂无阻塞问题。

## 非阻塞建议

1. MVP 首屏文案应避免“自动工作者”表述，优先使用“协作者”“可对话”“可追踪”。
2. 事件流建议按用户可理解的协作事件组织，而不是按底层日志原样展示。
3. 如果实现中发现 Codex 无法稳定被动接收消息，应优先保留“用户发起协作 -> Codex 响应 -> 事件可追踪”的 MVP 闭环，而不是扩展到项目自动化。

