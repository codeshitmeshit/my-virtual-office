# 方案评审

## 产品评审

需求目标清晰：这是一个会议参会人选择效率和可见性增强，不是会议执行模型变化。产品层面已经澄清：

- 支持两个入口：新建会议、AI 会议申请确认。
- branch 仅用于快捷选择，不定义会议边界。
- 允许 branch 批量选择后手动取消单个 AI。
- branch 需要半选状态，降低误选风险。
- Moderator 只在当前 Moderator 被取消时做兜底切换。

暂无产品阻塞问题。

## 技术评审

### 现有实现观察

- 新建会议表单在 `app/game.js` 中渲染 `.new-mtg-participant` checkbox。
- AI 会议申请确认表单在 `app/game.js` 中渲染 `.mtg-request-participant` checkbox。
- 前端已有 branch 数据与工具函数：`getBranchList()`、`getBranchById()`、`getBranchDisplayName()`、`_mtgAgentKey()`。
- 后端会议创建和申请确认已经接收最终 `participants` 数组，并通过 `_exec_meeting_clean_participants` 去重。
- 后端要求至少两名参与人，Moderator 必须属于 participants；这些约束应保持。

### 建议方案

1. 抽取会议参会人选择渲染辅助函数，避免新建会议和申请确认各自复制 branch 逻辑。
2. 在参与人区域上方或内部展示 branch 复选框列表。
3. 每个 branch 复选框根据该 branch 下 agent 的选中数量显示：
   - 全部选中：checked。
   - 部分选中：indeterminate。
   - 全部未选：unchecked。
4. 勾选 branch 时批量选中该 branch 下所有 agent；取消 branch 时批量取消。
5. 单个 agent checkbox 改变后，刷新 branch 状态和 Moderator 选项。
6. Moderator 更新规则保持克制：
   - 如果当前 Moderator 仍在 participants 中，不改变。
   - 如果当前 Moderator 已不在 participants 中，选剩余 participants 的第一个。
   - 如果没有 participants，则 Moderator 为空并由既有校验阻止提交。

### 数据与兼容性

- 不新增后端字段。
- 不改变会议、会议申请、会议执行数据结构。
- 对旧 agent 数据兼容：缺少 branch 时视为 `UNASSIGNED`。
- 对 branch 删除/重命名兼容：以当前 officeConfig branch 和 agent.branch 为准实时渲染。

### 风险与缓解

- 风险：branch 全选后用户没看清单个 AI，造成误选。
  - 缓解：branch 下仍显示单个 AI checkbox，并通过半选状态提示当前不是全选。
- 风险：两个入口行为不一致。
  - 缓解：共用渲染和状态更新逻辑，测试覆盖两个入口。
- 风险：Moderator 被取消后提交失败。
  - 缓解：每次参与人变化都刷新 Moderator；当前 Moderator 缺失时自动选择第一个剩余参会人。
- 风险：只有一个参会人或空参会人。
  - 缓解：保持既有“至少两名参会者”校验。
- 风险：branch 过多导致 UI 冗长。
  - 缓解：branch 控制区保持紧凑；只作为选择工具，不重复冗长说明。

## 结论

无阻塞问题。可以进入 checklist 确认。实现应优先保持两个入口一致、最终 participants 兼容、Moderator 合法和用户可见性。
