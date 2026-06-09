# Internal Bubble Auto Collapse Todo List

## TODO-001 Add And Persist The Global Timeout Preference

- 目标：在 Display 设置中提供以秒为单位的全局 `Internal` 自动收起时间。
- 涉及区域：`app/index.html`、`app/game.js`、`app/locales/en.json`、`app/locales/zh.json`。
- 输入：
  - 默认值 `60`。
  - `0` 表示禁用自动收起。
  - 现有 `vo-display-prefs` 数据。
- 输出：
  - 设置面板中的数值输入。
  - `internalBubbleTimeoutSec` 本地偏好字段。
  - 加载、保存和运行时规范化逻辑。
- 依赖：无。
- 完成标准：
  - 正整数和 `0` 可保存并立即生效。
  - 刷新后值保持不变。
  - 缺失或无效数据安全回退到 `60`。
  - 英文和中文设置文本完整。
- 关联 checklist：CHK-003、CHK-009、CHK-010、CHK-011、CHK-012、CHK-015。

## TODO-002 Implement Per-Agent Internal Inactivity Tracking

- 目标：为每个代理维护独立的 `Internal` 最近更新时间，并按全局秒数判断超时。
- 涉及区域：`app/game.js` 的 Agent 状态、状态轮询和气泡收集逻辑。
- 输入：
  - 规范化后的 `internalBubbleTimeoutSec`。
  - 每个代理的 `thought` 内容变化。
  - 当前 thought minimized 状态。
- 输出：
  - 每个代理独立的 inactivity timestamp。
  - 超时后切换为现有最小化图标状态。
- 依赖：TODO-001。
- 完成标准：
  - 仅不同的 `Internal` 内容重置时间。
  - 相同内容轮询不重置。
  - reasoning、工具、聊天和 speech 活动不重置。
  - `0` 时不执行自动收起。
  - 多代理按各自更新时间独立收起。
- 关联 checklist：CHK-003、CHK-005、CHK-006、CHK-009、CHK-010、CHK-013。

## TODO-003 Align New-Content And Manual-Restore Transitions

- 目标：确保新状态和手动恢复均按已确认规则展开并重新计时。
- 涉及区域：`app/game.js` 的 `pollStatus`、`handleBubbleClick`、Expand/Minimize 控制。
- 输入：
  - 新的 `Internal` 内容事件。
  - 用户点击最小化图标或按钮的事件。
- 输出：
  - 新内容自动展开并重新计时。
  - 手动恢复旧内容后重新计时。
  - 手动最小化仍立即生效。
- 依赖：TODO-002。
- 完成标准：
  - 自动收起后新状态可重新展开。
  - 手动恢复拥有完整的新倒计时。
  - 全局 Expand All、Minimize All 和 Show chat bubbles 行为不回归。
- 关联 checklist：CHK-004、CHK-007、CHK-008、CHK-016。

## TODO-004 Replace Legacy Fade Lifecycle

- 目标：移除或调整当前按文字显示完成后固定淡出的 thought 生命周期，避免与按内容更新时间自动收起冲突。
- 涉及区域：`app/game.js` 的 `THOUGHT_BUBBLE_HOLD_MS`、`THOUGHT_BUBBLE_FADE_MS`、`thoughtSettledAt` 及透明度计算。
- 输入：
  - 已确认的 inactivity timeout 语义。
  - 现有 typewriter 动画状态。
- 输出：
  - 单一、可预测的自动收起生命周期。
  - 不受帧率或文本长度影响的更新时间计时。
- 依赖：TODO-002、TODO-003。
- 完成标准：
  - 气泡不会在用户设置的超时前因旧固定计时逻辑消失。
  - 超时结果是最小化图标，而非完全透明但状态未同步。
  - typewriter 动画仍可正常完成。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-007。

## TODO-005 Create A Compact Internal-Only Layout

- 目标：缩小 `Internal` 气泡，同时保持可读性和稳定点击区域。
- 涉及区域：`app/game.js` 的 thought 布局常量、换行、绘制和碰撞定位。
- 输入：
  - 当前 thought/speech 共用尺寸。
  - 长代理名、中英文文本和最大行数场景。
- 输出：
  - thought 专用宽度、内边距、行高和最大行数。
  - 与 speech/chat 活动气泡隔离的布局参数。
- 依赖：无。
- 完成标准：
  - `Internal` 气泡明显更紧凑。
  - 标题、正文和最小化按钮不重叠。
  - 长文本不越界。
  - speech 与聊天/活动气泡保持原样。
- 关联 checklist：CHK-001、CHK-002、CHK-014、CHK-018。

## TODO-006 Add Focused Automated Validation

- 目标：覆盖偏好规范化和自动收起状态转换的高风险逻辑。
- 涉及区域：项目现有测试目录或可独立执行的前端逻辑测试。
- 输入：
  - 默认、`0`、正整数及无效设置值。
  - 新内容、相同内容、手动恢复和多代理时间序列。
- 输出：
  - 可重复执行的测试用例。
  - 清晰的通过/失败结果。
- 依赖：TODO-001 至 TODO-004。
- 完成标准：
  - 覆盖默认、禁用、重置、不重置、手动恢复和独立计时。
  - 测试不依赖真实 Hermes 或 OpenClaw 服务。
- 关联 checklist：CHK-003 至 CHK-013、CHK-015。

## TODO-007 Execute Static And Visual Regression Checks

- 目标：按已确认 checklist 验证实现与视觉行为。
- 涉及区域：JavaScript、HTML、locale JSON、浏览器画布。
- 输入：
  - TODO-001 至 TODO-006 的实现结果。
  - 桌面和窄屏浏览器视口。
- 输出：
  - 静态检查结果。
  - 关键状态的截图或人工验证记录。
  - checklist 测试结果回写。
- 依赖：TODO-001 至 TODO-006。
- 完成标准：
  - JavaScript 语法、JSON 和 `git diff --check` 通过。
  - CHK-001 至 CHK-018 均有结果。
  - 桌面与移动视口无文本或控件重叠。
- 关联 checklist：CHK-001 至 CHK-018。

## TODO-008 Update Requirement Status And Delivery Notes

- 目标：保持需求归档与实际开发、测试状态一致。
- 涉及区域：本需求目录中的 `checklist.md`、`status.json` 和交付说明。
- 输入：
  - 实现结果。
  - 测试结果。
  - 后续用户人工确认。
- 输出：
  - 实际测试记录。
  - 准确的阶段、确认项和时间戳。
- 依赖：TODO-007。
- 完成标准：
  - 开发完成后阶段更新为 `implementation_done`。
  - checklist 测试完成后等待用户确认，不提前标记 `tested`。
  - 最终完成仍等待用户明确确认。
- 关联 checklist：CHK-017、CHK-018。
