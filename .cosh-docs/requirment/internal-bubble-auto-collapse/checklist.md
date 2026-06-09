# Internal Bubble Auto Collapse Checklist

确认状态：已确认

## Acceptance And Main Flow

### CHK-001 Compact Internal Bubble

- 关联需求：REQ-001
- 验证方法：触发包含短文本和多行文本的 `Internal` 状态，对比当前版本并检查画布。
- 预期结果：`Internal` 气泡明显更窄、更紧凑；标题、正文、连接点和最小化按钮清晰且不重叠。

### CHK-002 Other Bubble Types Unchanged

- 关联需求：REQ-001
- 验证方法：同时展示 speech 气泡和右侧聊天/活动气泡，比较尺寸与交互。
- 预期结果：只有 `Internal` 气泡缩小，其他气泡尺寸和行为无回归。

### CHK-003 Default 60-Second Collapse

- 关联需求：REQ-002、REQ-003
- 验证方法：清除现有显示偏好或使用无该字段的偏好数据，触发新 `Internal` 内容并计时。
- 预期结果：默认设置显示 `60`；内容更新约 60 秒后气泡收起为小图标。

### CHK-004 New Content Resets And Expands

- 关联需求：REQ-003、REQ-004
- 验证方法：在倒计时过程中发送不同的 `Internal` 内容；在已自动收起后再次发送新内容。
- 预期结果：不同内容会自动展开气泡，并从新内容到达时重新完整计时。

### CHK-005 Identical Content Does Not Reset

- 关联需求：REQ-003
- 验证方法：保持服务端连续返回相同 `Internal` 内容，观察多个状态轮询周期。
- 预期结果：重复的相同内容不延长倒计时，气泡仍按最初更新时间收起。

### CHK-006 Unrelated Activity Does Not Reset

- 关联需求：REQ-003
- 验证方法：倒计时期间产生 Hermes reasoning、工具调用、聊天回复或 speech 更新，但不改变 `Internal` 内容。
- 预期结果：`Internal` 倒计时不重置，按原定时间收起。

### CHK-007 Manual Restore Restarts Timeout

- 关联需求：REQ-004
- 验证方法：等待自动收起，点击 `Internal` 小图标恢复并重新计时。
- 预期结果：旧内容重新展开，并从点击恢复时开始新的完整倒计时。

### CHK-008 Manual Minimize Remains Functional

- 关联需求：REQ-004
- 验证方法：在自动收起前点击气泡最小化按钮，再点击图标恢复。
- 预期结果：手动收起立即生效；恢复后重新开始倒计时。

## Settings And Persistence

### CHK-009 Custom Positive Timeout

- 关联需求：REQ-002、REQ-003
- 验证方法：分别保存较短正整数值，例如 `2` 和 `5` 秒，并触发状态。
- 预期结果：所有代理均使用保存的全局秒数，各自根据最近内容更新时间自动收起。

### CHK-010 Zero Disables Auto-Collapse

- 关联需求：REQ-002
- 验证方法：保存 `0`，触发 `Internal` 内容并等待超过之前默认超时时间。
- 预期结果：气泡不会自动收起，手动最小化仍然可用。

### CHK-011 Preference Persists Across Reload

- 关联需求：REQ-002
- 验证方法：保存自定义秒数后刷新页面并重新打开设置。
- 预期结果：设置值保持不变，后续气泡使用该值。

### CHK-012 Invalid Value Handling

- 关联需求：REQ-002
- 验证方法：尝试负数、空值、非数字和非有限值，并模拟损坏的本地偏好数据。
- 预期结果：界面不报错；无效值被阻止或规范化，运行时使用安全默认值 `60`。

## Multi-Agent, Compatibility, And Regression

### CHK-013 Independent Agent Timers

- 关联需求：REQ-002、REQ-003
- 验证方法：让两个代理在不同时间更新 `Internal` 内容。
- 预期结果：二者使用同一超时配置，但按照各自最后更新时间独立收起。

### CHK-014 Long Names And Text Layout

- 关联需求：REQ-001
- 验证方法：使用长代理名、长英文单词、中英文混排和达到最大行数的内容。
- 预期结果：文本不遮挡关闭按钮、不越出气泡，气泡位置和碰撞处理保持稳定。

### CHK-015 Reload And Legacy Preference Compatibility

- 关联需求：REQ-002
- 验证方法：使用仅包含旧字段 `showBubbles`、`showWeather`、`showNames` 的 `vo-display-prefs` 加载页面。
- 预期结果：旧显示设置继续生效，新超时采用默认 `60`，页面无异常。

### CHK-016 Visibility Toggle Regression

- 关联需求：REQ-001、REQ-002
- 验证方法：切换 Show chat bubbles、Expand All、Minimize All，并触发新状态。
- 预期结果：现有全局气泡控制继续工作；新状态与自动收起不会破坏全局显示状态。

## Quality And Manual Verification

### CHK-017 Static Validation

- 关联需求：REQ-001 至 REQ-004
- 验证方法：运行 JavaScript 语法检查、JSON 校验和 `git diff --check`。
- 预期结果：全部检查通过，无语法错误或空白错误。

### CHK-018 Desktop And Mobile Visual Check

- 关联需求：REQ-001
- 验证方法：在桌面和窄屏视口中截图检查短文本、长文本、多个气泡和最小化图标。
- 预期结果：气泡保持在可视区域，文本和控件无重叠，图标可点击。

## Confirmation Record

- Checklist confirmation: confirmed at `2026-06-09T00:10:38+08:00`.
- User confirmation summary: `pass`.
- Test execution confirmation: pending.

## Test Execution Record

- Execution time: `2026-06-09T14:32:34+08:00`
- Environment: shared Chrome, `https://xiaoou.cosh.fun/`, desktop and narrow viewport.
- Overall result: failed; the planned feature is not integrated into the running page.

| Checklist | Result | Evidence |
| --- | --- | --- |
| CHK-001 | Failed | Chrome reported the `Internal` bubble width as `170`, the unchanged shared bubble width, rather than the planned compact width. |
| CHK-002 | Passed | Existing speech and manual bubble behavior remained available; no shared layout change was present. |
| CHK-003 | Failed | No timeout setting exists and the bubble remained expanded after waiting. |
| CHK-004 | Failed | No `thoughtUpdatedAt` lifecycle exists in the running Agent state. |
| CHK-005 | Failed | No inactivity timer is implemented, so identical-content polling cannot preserve a countdown. |
| CHK-006 | Failed | No independent `Internal` countdown exists to protect from unrelated activity resets. |
| CHK-007 | Failed | Manual restore works, but it does not restart an inactivity timestamp. |
| CHK-008 | Passed | Chrome verified the existing minimize button and minimized icon restore flow. |
| CHK-009 | Failed | No configurable positive timeout is exposed or consumed. |
| CHK-010 | Failed | No timeout preference exists, including the `0` disabled behavior. |
| CHK-011 | Failed | No timeout preference is saved to `vo-display-prefs`. |
| CHK-012 | Failed | The timeout normalization helper is not loaded by the page. |
| CHK-013 | Failed | Agent instances have no independent `thoughtUpdatedAt` timestamps. |
| CHK-014 | Failed | Long unbroken text remained on the old layout and exceeded the intended compact wrapping behavior. |
| CHK-015 | Failed | Legacy preferences load, but the missing timeout does not resolve to a runtime default of `60`. |
| CHK-016 | Passed | Existing Expand All, Minimize All, and manual bubble controls remain present. |
| CHK-017 | Failed | The standalone helper test is not sufficient because `internal-bubble.js` is not loaded or integrated by the application. |
| CHK-018 | Failed | Narrow-view Chrome inspection showed the old bubble geometry; compact responsive acceptance cannot pass. |

### Chrome Evidence

- `InternalBubbleSettings` loaded: `false`
- Timeout setting element present: `false`
- Runtime display preferences: only `showWeather`
- Measured `Internal` bubble: `170 x 65`
- Automatic collapse after wait: `false`
- Manual minimize and restore: passed
- Agent inactivity timestamp after restore: absent
- Narrow-view screenshot: `/tmp/internal-bubble-current-mobile.png`

## Retest Execution Record

- Execution time: `2026-06-09T14:43:35+08:00`
- Environment: shared Chrome, `https://xiaoou.cosh.fun/`, desktop `1440 x 900` and narrow `500 x 844` viewports.
- Overall result: passed; all checklist behaviors are implemented and verified.

| Checklist | Result | Evidence |
| --- | --- | --- |
| CHK-001 | Passed | Chrome measured the `Internal` bubble at `132px`; compact padding and line height were applied. |
| CHK-002 | Passed | Simultaneous speech bubble remained at the original `170px` width. |
| CHK-003 | Passed | Missing timeout defaults to `60`; a short test timeout automatically collapsed to the existing icon. |
| CHK-004 | Passed | New content expanded a collapsed bubble and restarted the full timeout. |
| CHK-005 | Passed | Reapplying identical content left `thoughtUpdatedAt` unchanged. |
| CHK-006 | Passed | Speech activity did not change the `Internal` timestamp or collapse schedule. |
| CHK-007 | Passed | Clicking the minimized icon restored the bubble and advanced `thoughtUpdatedAt`. |
| CHK-008 | Passed | Manual minimize and restore remained functional. |
| CHK-009 | Passed | Positive timeout values controlled the collapse interval. |
| CHK-010 | Passed | Timeout `0` kept a bubble open even with a timestamp ten minutes old. |
| CHK-011 | Passed | Stored timeout `5` loaded into runtime and the settings input after reload/opening settings. |
| CHK-012 | Passed | Empty, invalid, negative, and non-finite values normalize to `60`; decimal positive values are floored. |
| CHK-013 | Passed | Two agents with timestamps one second apart collapsed independently. |
| CHK-014 | Passed | Long agent names were truncated in the header and unbroken mixed-language text wrapped inside the bubble. |
| CHK-015 | Passed | Missing legacy timeout safely resolves to runtime default `60`. |
| CHK-016 | Passed | Minimize All and Expand All worked; expanding restarted the `Internal` timeout. |
| CHK-017 | Passed | JavaScript syntax, locale JSON, integration test, and `git diff --check` passed. |
| CHK-018 | Passed | Desktop and narrow screenshots showed bounded geometry with no control/text overlap. |

### Retest Evidence

- Helper loaded by page: `true`
- Settings input present with default: `60`
- Compact `Internal` geometry: `132 x 58`
- Unchanged speech geometry: `170 x 65`
- Independent timer observation: first agent collapsed while second remained expanded
- Chinese labels: `Internal 气泡自动收起（秒）`, `设为 0 可禁用自动收起。`
- Desktop screenshot: `/tmp/internal-bubble-desktop-passed.png`
- Narrow screenshot: `/tmp/internal-bubble-mobile-passed.png`
- Automated test: `node tests/test_internal_bubble.js`
- Test execution confirmation: pending user confirmation
