# Checklist

确认状态：已确认

## 参与人选择主流程

- [x] CHK-001 新建会议支持按 branch 快捷选择参会人。
  - 验证方法：打开新建会议表单，找到参会人区域，勾选一个 branch。
  - 预期结果：该 branch 下所有 AI 被勾选，其他 branch 的已选 AI 不被错误清空。
  - 关联需求点：两个入口都支持 branch 快选；branch 勾选代表选择该 branch 下全部 AI。

- [x] CHK-002 AI 会议申请确认支持按 branch 快捷选择参会人。
  - 验证方法：构造或打开一个 pending AI 会议申请，在确认区域勾选一个 branch。
  - 预期结果：该 branch 下所有 AI 被勾选，用户可以继续确认会议。
  - 关联需求点：AI 会议申请确认入口支持 branch 快选。

- [x] CHK-003 取消 branch 会取消该 branch 下所有 AI。
  - 验证方法：先勾选一个 branch，再取消该 branch。
  - 预期结果：该 branch 下 AI 全部取消；其他 branch 中用户已选 AI 不受影响。
  - 关联需求点：branch 取消语义。

- [x] CHK-004 branch 批量选择后允许手动取消单个 AI。
  - 验证方法：勾选一个 branch 后，手动取消该 branch 下某个 AI。
  - 预期结果：该 AI 被取消；同 branch 其他 AI 保持选中；最终参会人列表按用户微调结果提交。
  - 关联需求点：branch 快选后仍可手动微调。

- [x] CHK-005 单个 AI 可在 branch 选择后重新勾选。
  - 验证方法：勾选 branch、取消单个 AI、再重新勾选该 AI。
  - 预期结果：该 AI 恢复参会；branch 状态同步更新。
  - 关联需求点：最终参会人以用户确认后的 AI 列表为准。

## 状态可见性

- [x] CHK-006 branch 全选状态显示准确。
  - 验证方法：某 branch 下所有 AI 都被选中时观察 branch 复选框。
  - 预期结果：branch 显示 checked。
  - 关联需求点：选了谁一眼可见。

- [x] CHK-007 branch 半选状态显示准确。
  - 验证方法：某 branch 下只有部分 AI 被选中时观察 branch 复选框。
  - 预期结果：branch 显示半选状态。
  - 关联需求点：部分选中表达。

- [x] CHK-008 branch 未选状态显示准确。
  - 验证方法：某 branch 下没有 AI 被选中时观察 branch 复选框。
  - 预期结果：branch 显示 unchecked。
  - 关联需求点：选中状态可见。

- [x] CHK-009 缺少 branch 的 AI 仍可被选择。
  - 验证方法：准备或确认存在 UNASSIGNED/未分配 branch 的 AI，在会议表单中选择。
  - 预期结果：未分配 AI 出现在可选区域，可被 branch 或单独 checkbox 选择。
  - 关联需求点：兼容未分配 agent。

## Moderator 行为

- [x] CHK-010 branch 选择不会主动覆盖有效 Moderator。
  - 验证方法：选择多个 AI 并指定 Moderator，再勾选另一个 branch。
  - 预期结果：如果原 Moderator 仍在参会人中，Moderator 不被自动改掉。
  - 关联需求点：branch 选择不主动改变 Moderator。

- [x] CHK-011 当前 Moderator 被取消时自动兜底到剩余第一个参会人。
  - 验证方法：选择多个 AI，指定其中一个为 Moderator，然后取消该 AI。
  - 预期结果：Moderator 自动切换到剩余参会人中的第一个。
  - 关联需求点：Moderator 被取消时自动兜底。

- [x] CHK-012 参会人不足时仍保留既有校验。
  - 验证方法：通过 branch 或单独 checkbox 让最终参会人少于 2 人后提交。
  - 预期结果：提交被阻止，并提示至少选择两名参会者。
  - 关联需求点：不改变会议创建基本约束。

## 入口一致性与回归

- [x] CHK-013 新建会议提交的 participants 是最终勾选结果。
  - 验证方法：branch 批量选择后手动取消部分 AI，提交会议，查看创建结果。
  - 预期结果：会议中的 participants 只包含最终勾选 AI。
  - 关联需求点：最终参会人以用户确认列表为准。

- [x] CHK-014 AI 会议申请确认提交的 participants 是最终勾选结果。
  - 验证方法：在申请确认中 branch 批量选择后手动取消部分 AI，确认会议。
  - 预期结果：生成会议中的 participants 只包含最终勾选 AI。
  - 关联需求点：申请确认入口最终列表准确。

- [x] CHK-015 既有会议执行流程不回归。
  - 验证方法：使用 branch 选择创建会议后启动会议，或确认 AI 会议申请后运行会议。
  - 预期结果：会议仍能进入 active/completed 流程，参与人轮次和结果生成正常。
  - 关联需求点：不改变会议执行模型。

- [x] CHK-016 忙碌冲突和占用提示不回归。
  - 验证方法：选择包含忙碌 AI 的 branch 创建会议。
  - 预期结果：既有 conflict/忙碌处理仍按最终 participants 生效。
  - 关联需求点：不破坏 Phase 5 忙碌冲突流程。

- [x] CHK-017 中英文文案完整。
  - 验证方法：切换中文和英文 UI，查看 branch 选择区域、提示、按钮或标签。
  - 预期结果：新增文案在两种语言下自然可读，无硬编码语言混用。
  - 关联需求点：会议 UI 一致性。

## 人工验证

- [x] CHK-018 真实 UI 验收覆盖两个入口。
  - 验证方法：在 8090 或当前验收环境中分别打开新建会议和 AI 会议申请确认，完成 branch 选择、单 AI 微调、Moderator 兜底检查。
  - 预期结果：用户能清楚看到当前选中的 branch/AI，并成功创建或确认会议。
  - 关联需求点：产品成功标准。

## 人工确认记录

- checklist 确认：2026-06-20T08:11:21+08:00，用户回复 “continuee”，确认 checklist，可以生成 todolist。
- 最终验收确认：2026-06-20T10:00:00+08:00，用户回复“我测完了，可以归档了”，确认需求验收通过并允许归档。

## 实施与测试记录

- 2026-06-20：`app/game.js` 已实现会议参与人 branch 快捷选择组件，新建会议和 AI 会议申请确认共用同一套渲染、branch 状态同步和 Moderator 选项刷新逻辑。
- 2026-06-20：修正真实 `/agents-list` 返回 branch 显示名时的前端归类逻辑，兼容 branch id、branch name、本地化未分配名和 provider 名。
- 2026-06-20：已执行 `node --check app/game.js`、`tests/test_meeting_for_ai_phase1.py`、`tests/test_meeting_for_ai_phase6.py`，均通过。
- 2026-06-20：此前已执行 `tests/test_meeting_for_ai_phase4.py` 通过；`tests/test_meeting_for_ai_phase5.py` 在 live advisory 打开时受网关状态影响失败一次，设置 `VO_MEETING_DISABLE_LIVE_ADVISORY=1` 后通过。
- 2026-06-20：Chrome MCP 连接真实 8090 页面完成新建会议入口 UI smoke：branch 勾选全选、取消 branch 全取消、手动取消单个 AI 后 branch 进入 indeterminate、Moderator 自动回退到剩余第一个参与人。测试结果保存于 `/tmp/meeting-branch-ui-smoke.json`。
- 2026-06-20：Chrome MCP 已释放回 `about:blank`。
- 2026-06-20：用户完成最终验收并确认可以归档。
