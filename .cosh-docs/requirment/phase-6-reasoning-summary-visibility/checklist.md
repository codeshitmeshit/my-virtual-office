# Phase 6 Reasoning Summary Visibility Test Checklist

确认状态：已确认

## Checklist 确认记录

- 确认项：Phase 6 reasoning summary visibility 补测 checklist（10 项）。
- 确认时间：2026-06-09T23:30:28+08:00。
- 用户确认摘要：用户要求继续执行，确认进入 todolist 与实现阶段。

## 补测指标

### CHK-RS-001 Reasoning event normalization

- 验证方法：向 bridge 注入 `summaryTextDelta`、`summaryPartAdded` 和 `textDelta` 通知。
- 量化指标：三类通知 100% 被识别；reasoning 事件不进入 command/tool 类型；未知字段不会导致异常。
- 预期结果：输出包含稳定 operation、thread、turn、item、sequence 和 section 关联信息。

### CHK-RS-002 Incremental aggregation

- 验证方法：对同一 item 连续发送 20 个 delta，包含至少 3 个 summary section。
- 量化指标：界面只生成 1 张 Thinking 卡；20 个 delta 顺序完整；3 个 section 边界可辨识；重复卡数量为 0。
- 预期结果：卡片增量更新，不覆盖已有内容，不把 reasoning 渲染成工具调用。

### CHK-RS-003 Multiple reasoning items

- 验证方法：同一 turn 发送两个不同 reasoning item，并穿插 command activity。
- 量化指标：生成 2 张 Thinking 卡和对应工具卡；跨 item 串内容次数为 0；事件排序与服务端 sequence 一致。
- 预期结果：每个 item 独立聚合，Thinking 与工具活动保持明确边界。

### CHK-RS-004 Refresh recovery

- 验证方法：reasoning 流传输中刷新一次，完成后再刷新一次。
- 量化指标：两次刷新后文本丢失字符数为 0；重复 section 和重复卡数量为 0；后续 live delta 继续追加到原 item。
- 预期结果：运行中和完成后的 reasoning summary 均能稳定恢复。

### CHK-RS-005 No-event behavior

- 验证方法：执行简单问候和不产生 reasoning 通知的 fixture。
- 量化指标：空 Thinking 卡数量为 0；伪造摘要数量为 0。
- 预期结果：只有 runtime 实际提供内容时才显示 Thinking 卡。

### CHK-RS-006 Redaction and truncation

- 验证方法：reasoning delta 中放入测试 token、Authorization、Cookie、凭据 URL、嵌套 secret 和超过上限的文本。
- 量化指标：原始敏感测试值泄露数量为 0；超长内容有明确截断标记；事件关联 ID 保留率 100%。
- 预期结果：实时 UI、持久化文件、刷新历史和错误日志均不出现原始敏感值。

### CHK-RS-007 Accurate user wording

- 验证方法：检查 Thinking 卡标题、状态和说明文字。
- 量化指标：不得出现“完整思维链”“完整内部思考”等承诺；必须明确是 Codex 提供且可能不出现的 reasoning summary。
- 预期结果：用户可以理解内容性质，不会把摘要误认为隐藏 chain-of-thought。

### CHK-RS-008 Real Codex complex task

- 验证方法：使用 `_VO_INT=1`、`demo=false` 执行一个需要读取、搜索、命令和总结的只读任务。
- 量化指标：若 runtime 发出 reasoning 通知，所有通知均形成 Thinking 卡并可展开；工具卡完整；最终回复唯一；工作区新增修改为 0。
- 预期结果：真实复杂任务中 reasoning summary 与工具轨迹协调展示。若模型未发出 reasoning，记录协议证据，不将其判为 UI 失败。

### CHK-RS-009 Phase 6 regression

- 验证方法：重跑 Phase 6 bridge/server/HTTP E2E，并浏览器验证审批、输入、取消和刷新。
- 量化指标：现有自动化通过率 100%；审批续跑、取消、busy 定位和恢复行为回归数为 0。
- 预期结果：reasoning 展示不改变 Phase 6 控制状态机。

### CHK-RS-010 Provider compatibility

- 验证方法：检查 OpenClaw/Hermes Thinking 与工具卡历史，并执行可用的 provider 回归。
- 量化指标：既有 Thinking 卡 DOM/样式行为回归数为 0；OpenClaw/Hermes 路由和 history 回归数为 0。
- 预期结果：共用视觉组件但不改变其他 provider 的数据语义。

## 人工验收路径

1. 发送复杂只读任务，确认 Thinking 与工具卡分离。
2. 展开 Thinking 卡，确认内容按段增量出现。
3. 运行中刷新，确认卡片不丢失、不重复。
4. 发送简单问候，确认不会生成空 Thinking 卡。
5. 确认说明文字没有宣称展示完整内部思维链。

## 执行状态

- 实现完成，等待用户浏览器验收。

## 实现验证记录

- 执行时间：2026-06-09T23:39:00+08:00。
- 协议：已独立处理 `summaryTextDelta`、`summaryPartAdded`、`textDelta`，并默认通过 `turn/start.summary=concise` 请求可读摘要。
- 聚合：20 delta、3 section、重复事件、最终 authoritative replace 和无事件空状态测试通过。
- 安全：reasoning 内容复用服务端脱敏与 12,000 字符截断，敏感值和截断测试通过。
- 回归：Codex bridge、server、Phase 6 HTTP E2E、JavaScript 聚合与语法检查全部通过。
- 真实 Codex：`_VO_INT=1`、`demo=false` 下完成复杂只读任务；runtime 发出 1 个 reasoning item、1 个 section boundary、5 个 summary delta 和最终摘要 `Correcting parallel usage`，未修改文件。
- 待确认：用户在浏览器硬刷新后确认 Thinking 卡实时出现、可展开，并在刷新后不重复。
