# Chat Provider SSE Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Codex、Hermes、Claude Code 聊天运行进度、工具、审批和终态收敛到每个聊天窗口的一条 provider SSE，并移除前端常驻轮询。

**Architecture:** 扩展现有 `ProviderRunBridge` 为带全局递增事件 ID、短窗口事件日志和条件变量的广播桥，使每个事件可以被多个订阅者读取而不会互相抢占。新增 `/api/provider/events`，按 provider、agentId、conversationId 过滤并发送 snapshot、run 事件、approval 事件与 heartbeat；前端 `ChatWindow` 持有一条会随当前 provider 选择更新的 `EventSource`，run Promise 由统一流中的终态事件结算。

**Tech Stack:** Python `ThreadingHTTPServer`、SSE、浏览器 `EventSource`、原生 JavaScript、Node 静态回归测试。

---

### Task 1: 统一 SSE 协议回归测试

**Files:**
- Create: `tests/check_provider_chat_sse.mjs`
- Modify: `tests/check_frontend_performance_static.mjs`

- [ ] 写静态契约测试，要求 `/api/provider/events`、广播事件日志、`provider.snapshot`、`provider.heartbeat`、前端单一 `providerEventSource` 和 run waiter 存在。
- [ ] 写反向断言，禁止 provider history、approval 和 Codex activity 使用 `setInterval` 常驻轮询。
- [ ] 运行测试并确认因统一 SSE 尚不存在而失败。

### Task 2: 后端广播桥和 conversation SSE

**Files:**
- Modify: `app/server.py`
- Test: `tests/check_provider_chat_sse.mjs`

- [ ] 将 `ProviderRunBridge.emit()` 写入有界广播日志，并用 `Condition` 唤醒所有订阅者。
- [ ] 保留旧的 per-run SSE 路由兼容性，但改为游标读取，避免多个客户端抢同一个 `queue.Queue`。
- [ ] 新增 provider conversation stream，初始发送 `provider.snapshot`，随后转发匹配事件并发送 `provider.heartbeat`。
- [ ] 为审批初始状态和审批响应发布 `approval.request` / `approval.resolved`，事件携带 providerKind、agentId、conversationId、runId 和 eventId。
- [ ] 添加 GET 路由 `/api/provider/events` 并运行静态测试。

### Task 3: 前端单连接订阅和 run 结算

**Files:**
- Modify: `app/chat.js`
- Test: `tests/check_provider_chat_sse.mjs`

- [ ] 新增 `updateProviderEventSource()`，仅在聊天窗打开且选中 Codex/Hermes/Claude Code 时连接当前 conversation。
- [ ] 统一分发 provider 事件到现有 `handleCodexNativeEvent`、`handleHermesNativeEvent`、`handleClaudeCodeNativeEvent`，并由 run waiter 在终态结算发送流程。
- [ ] 将三个 `stream*RunEvents()` 改为等待统一 SSE 的 run 终态，不再创建 per-run `EventSource`。
- [ ] 删除前端 provider history、approval、Codex activity 的常驻 `setInterval`；断线时仅执行一次 history/activity/approval 补偿，并依赖 `EventSource` 自动重连。
- [ ] 在 provider 切换、聊天窗开关、新会话和销毁路径更新或关闭统一连接。

### Task 4: 验证与收口

**Files:**
- Test: `tests/check_provider_chat_sse.mjs`
- Test: `tests/check_codex_runs_bridge.mjs`
- Test: `tests/check_codex_approval_ui.mjs`
- Test: `tests/check_claude_code_runs_sse.mjs`
- Test: `tests/check_chat_bug_regressions.mjs`

- [ ] 运行 Node 静态回归、`python3 -m py_compile app/server.py` 和 `node --check app/chat.js`。
- [ ] 启动本地服务，用浏览器验证 provider SSE 能连接、heartbeat 持续、页面无控制台错误和长任务。
- [ ] 搜索确认聊天 provider 不再存在 500ms/1s 常驻 `setInterval`，并审计旧 per-run SSE 仅作为后端兼容路由保留。
