# Frontend Action Dedup Guard Review

## 产品评审

### 用户问题

当前用户点击项目侧按钮后，UI 可能需要等待接口、刷新或轮询才展示状态变化。这个窗口期内重复点击会造成重复请求。用户感知上表现为：

- 启动、继续执行、验收等按钮点击后不确定是否生效。
- 网络慢时容易双击或多次点击。
- 弹窗确认按钮点击后如果弹窗未立即消失，可能再次提交。
- 后端即使拒绝重复请求，前端也可能出现多条 toast 或状态跳变。

### 产品目标是否清晰

目标清晰：给关键写操作增加前端防重和处理中反馈，减少重复请求，提升项目侧状态机体验稳定性。

### 产品澄清结论

无需继续产品澄清。当前需求不涉及新业务规则，只是交互和状态保护增强。

## 技术评审

### 建议方案

在 `ProjMgr` 内增加轻量 action guard：

```text
state.pendingActions: Map<string, { startedAt, label }>
runActionOnce(key, fn, opts)
```

核心行为：

- 同一 key 已在执行时直接忽略，并可 toast “处理中，请稍候”。
- action 开始时同步设置触发按钮 disabled、`aria-busy=true` 和可选 loading 文案。
- action 结束后在 `finally` 释放锁并恢复按钮状态。
- 支持递归确认流程使用同一业务 key，例如 dirty worktree 二次确认后继续启动，仍属于同一启动动作。
- 对话框提交动作也使用 guard，避免一个弹窗内重复提交。

### 防重 key 粒度

建议按业务动作区分：

- `project-exec-start:${projectId}:${taskId}`
- `project-exec-project-start:${projectId}`
- `project-exec-project-restart:${projectId}`
- `project-exec-cancel:${projectId}:${taskId}:${attemptId}`
- `meeting-blocker:${projectId}:${taskId}:${action}`
- `project-exec-review-start:${projectId}:${taskId}:${attemptId}`
- `project-exec-accept:${projectId}:${taskId}:${attemptId}:${action}`
- `workflow-start:${projectId}`
- `workflow-stop:${projectId}`
- `cron-submit:${projectId}:${cronId|new}`
- `cron-run:${projectId}:${cronId}`
- `cron-toggle:${projectId}:${cronId}`
- `cron-delete:${projectId}:${cronId}`

### 交互要求

- 被点击按钮立即进入 disabled 状态。
- 按钮可显示 `处理中...` 或保持原文但加 `aria-busy=true`。
- 重复点击同一 action 时不再发请求；高风险操作给出轻量 toast，普通重复点击保持安静。
- 非同一 key 的操作不互相阻塞。
- 弹窗确认按钮在提交后 disabled，直到请求返回或弹窗关闭。
- 操作锁至少持续到请求返回并完成页面状态刷新，避免刷新前旧按钮再次触发。

### 架构与接口影响

- 前端：主要修改 `app/projects.js`。
- 后端：不需要新增接口。
- 数据：不需要迁移。
- 权限：不改变权限模型。
- 状态机：不改变后端状态，只减少前端重复请求。
- 兼容性：保持 inline `onclick` 结构可用，优先通过 optional `event` 传入触发按钮；无法传 event 的入口仍可通过 action key 防重。

### 异常处理

- action 抛异常时必须释放锁并恢复按钮。
- 用户取消确认弹窗时必须释放锁。
- 需要二次确认的流程应避免释放后再递归导致双击窗口；推荐外层 action 保持同一 key，确认完成后继续执行真实请求。
- 如果请求成功后刷新失败，需要释放锁并 toast 刷新失败，不应卡死按钮。
- 失败后按错误类型区分：网络或后端普通错误允许恢复重试；状态冲突类错误应优先刷新状态，避免用户原地重复点击。

### 可观测性

- 开发期可在重复点击被拦截时打印低噪日志，例如 `[PROJECTS] duplicate action ignored key=...`。
- 生产 UI 可只 toast 一次或静默忽略，避免重复点击造成更多噪音。

### 测试可行性

可通过静态 Node 测试和现有 Chrome/CDP 测试覆盖：

- 静态检查 `runActionOnce` 存在，关键 action 使用 guard。
- 单元式 JS harness 模拟同一 key 并发调用只执行一次。
- Chrome/CDP 可注入快速双击，断言对应 API POST 只发一次。

## 阻塞问题

暂无阻塞问题。

## 风险

- 如果 key 粒度过粗，会误阻塞无关操作。
- 如果 key 粒度过细，仍可能漏掉重复提交。
- 如果按钮状态恢复逻辑只依赖 DOM 引用，重渲染后可能恢复不到旧按钮；需要允许重渲染自然清理旧状态。
- 如果确认流程里外层和内层使用不同 key，二次确认后仍可能重复启动。

## 评审结论

可以进入 checklist。建议第一阶段覆盖项目执行关键链路、scheduled cron 和相关弹窗提交按钮，不做全 UI 事件体系重构。
