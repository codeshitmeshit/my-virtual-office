# Phase5 Codex Live Bridge 需求草案

## 背景

Phase4 已完成 Codex Harness MVP：Codex 可以作为 Virtual Office 中的可见协作者出现，消息能进入统一 communication 路由，并被 history、`/agent-chat` 和活动事件流追踪。但当前实现仍是 harness/demo reply 模式，不会真实驱动一个 live Codex CLI 会话执行任务。

Phase5 的目标是在 Phase4 harness 基础上接入 live Codex bridge，让办公室消息可以被真实 Codex 会话接收、执行，并把结果回传到既有 office surface。

## 产品目标

1. 用户能从 Virtual Office 向 Codex 发送一条真实协作消息。
2. OpenClaw 或 Hermes agent 能通过 agent-platform communication 向 Codex 发起一次真实协作。
3. Codex bridge 能启动或复用一个 live Codex CLI/session，并返回真实最终回复。
4. Codex 的执行状态、成功回复、失败原因、超时结果能进入统一事件流。
5. Phase5 不破坏 Phase4 已有的可见性、状态、消息路由和 demo regression 能力。

## 本期范围

- 在现有 Codex provider adapter 后接入 live bridge。
- 定义 Virtual Office 到 live Codex bridge 的最小请求/响应协议。
- 支持单轮消息执行：发送消息、等待最终回复、记录结果。
- 支持基础会话标识，避免所有消息混成不可追踪的一条链路。
- 支持明确错误：bridge 未启动、Codex CLI 不可用、执行失败、执行超时。
- 保留 `VO_CODEX_REPLY_TEXT` 作为 deterministic regression fallback。
- 更新回归测试，覆盖 demo reply 与 live bridge 两种模式。

## 非目标

- 不要求 Codex 自动接项目板任务。
- 不实现完整 workflow/project automation。
- 不要求长任务编排、任务取消、权限弹窗、审批流。
- 不要求流式展示所有 tool call、文件 diff 或命令输出。
- 不要求多 Codex worker 调度。

## 验收标准

1. `VO_CODEX_ENABLED=1` 且 live bridge 配置可用时，用户发给 Codex 的消息会由真实 Codex 会话处理。
2. `/api/agent-platform-communications/send` 对 `codex-local` 返回真实 Codex 回复，而不是固定 demo reply。
3. history 和 `/agent-chat` 能展示请求、状态、最终回复或失败原因。
4. bridge 不可用时，用户看到明确错误，不会误以为 Codex 已执行。
5. OpenClaw/Hermes/Codex 三类 agent 的基础回归仍通过。

## 后续阶段候选

- 流式状态和工具事件展示。
- 取消、超时续跑、权限确认。
- Codex 工作区文件变更追踪。
- 多 Codex worker 和调度策略。
- Codex 参与项目板任务、review 和交付闭环。
