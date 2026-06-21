# Todolist

## TODO-001 梳理会议参会人选择现有入口（已完成）

- 目标：确认新建会议和 AI 会议申请确认两个入口的参会人选择代码路径和共用点。
- 涉及区域：`app/game.js` 中新建会议表单、AI 会议申请确认表单、Moderator 更新逻辑。
- 输入：已确认 checklist、现有 `_mtgAgents`、`_mtgAgentKey`、branch 工具函数。
- 输出：明确的改造点和共用辅助函数边界。
- 依赖：无。
- 完成标准：两个入口的参与人选择渲染和状态同步路径已识别，不引入后端协议变更。
- 关联 checklist：CHK-001、CHK-002、CHK-013、CHK-014。

## TODO-002 实现 branch 分组选择 UI（已完成）

- 目标：在会议参会人区域展示 branch 快捷复选框。
- 涉及区域：`app/game.js`、必要 CSS 或内联样式。
- 输入：officeConfig branches、agent.branch、UNASSIGNED 分组。
- 输出：按 branch 展示的快捷选择控件，支持所有 branch 和未分配 AI。
- 依赖：TODO-001。
- 完成标准：新建会议和申请确认入口都能看到 branch 快选区域；缺少 branch 的 AI 有合理归类。
- 关联 checklist：CHK-001、CHK-002、CHK-009、CHK-017。

## TODO-003 实现 branch 全选、取消全选和半选状态（已完成）

- 目标：让 branch checkbox 能正确批量勾选/取消，并根据单个 AI 选择状态显示 checked/indeterminate/unchecked。
- 涉及区域：`app/game.js` 参会人 checkbox 事件、branch checkbox 状态刷新逻辑。
- 输入：当前表单上下文、新建会议和申请确认的不同 CSS class/data-request-id。
- 输出：可复用的 branch 状态同步函数。
- 依赖：TODO-002。
- 完成标准：branch 全选、取消全选、单个 AI 微调后 branch 状态准确。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-008。

## TODO-004 保持 Moderator 合法并实现兜底切换（已完成）

- 目标：参会人变化时同步 Moderator 选项，当前 Moderator 被取消时自动切换到剩余第一个参会人。
- 涉及区域：`updateNewMeetingModeratorOptions`、`_mtgUpdateRequestModeratorOptions` 或共用逻辑。
- 输入：最终参会人 checkbox 结果、当前 Moderator 选择。
- 输出：稳定的 Moderator 选项刷新行为。
- 依赖：TODO-003。
- 完成标准：有效 Moderator 不被 branch 选择主动覆盖；被取消后自动兜底；参会人不足时保留原校验。
- 关联 checklist：CHK-010、CHK-011、CHK-012。

## TODO-005 确保提交 participants 使用最终选择结果（已完成）

- 目标：确认 branch 快选不改变后端协议，提交仍只发送最终 participants 数组。
- 涉及区域：`submitNewMeeting`、`_mtgConfirmRequest`。
- 输入：用户最终勾选的 AI checkbox。
- 输出：新建会议和申请确认请求体中 participants 与 UI 最终选择一致。
- 依赖：TODO-003、TODO-004。
- 完成标准：branch 批量选择后手动取消的 AI 不会出现在提交结果里。
- 关联 checklist：CHK-013、CHK-014。

## TODO-006 补充中英文文案（已完成）

- 目标：为 branch 快选相关标签和提示补齐中英文文案。
- 涉及区域：`app/game.js` 内会议文案字典，必要时 locale 文件。
- 输入：新增 UI 文案。
- 输出：中文和英文 UI 均自然可读。
- 依赖：TODO-002。
- 完成标准：切换中英文时无明显硬编码混用。
- 关联 checklist：CHK-017。

## TODO-007 补充自动化和静态回归测试（已完成）

- 目标：覆盖新建会议、AI 会议申请确认、participants 最终结果和既有会议执行约束。
- 涉及区域：会议相关测试文件、必要的 JS syntax check。
- 输入：实现完成后的代码。
- 输出：测试用例或可复现验证脚本。
- 依赖：TODO-005、TODO-006。
- 完成标准：相关测试通过；至少覆盖 participants 最终结果、Moderator 兜底和参会人数校验。
- 关联 checklist：CHK-012、CHK-013、CHK-014、CHK-015、CHK-016。

## TODO-008 真实 UI 验收（部分完成，待用户最终验收）

- 目标：在真实或当前验收环境中验证两个入口的 branch 快选体验。
- 涉及区域：8090 本地服务、Chrome MCP 或用户手动 UI。
- 输入：实现完成并重启后的服务。
- 输出：UI 验收记录。
- 依赖：TODO-007。
- 完成标准：新建会议和 AI 会议申请确认均完成 branch 选择、单 AI 微调、Moderator 兜底和会议创建/确认验证。
- 关联 checklist：CHK-001 至 CHK-018。
- 进展：Chrome MCP 已完成新建会议入口真实页面 smoke；AI 会议申请确认入口使用同一组件和提交逻辑，等待真实 pending 申请或用户人工验收。

## TODO-009 更新需求归档（已更新，待最终归档）

- 目标：把实现、测试、真实 UI 验收和用户确认结果写回需求归档。
- 涉及区域：`checklist.md`、`status.json`。
- 输入：TODO-007、TODO-008 结果和用户确认。
- 输出：测试记录、阶段推进和最终完成状态。
- 依赖：TODO-008。
- 完成标准：测试完成后进入 `tested`；用户最终确认后进入 `done`。
- 关联 checklist：CHK-001 至 CHK-018。
