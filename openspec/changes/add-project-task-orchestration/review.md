## 评审结论

**带条件通过。**

规格可以通过“单一阶段状态机 + 任务级 attempt + 幂等阶段派发”实现，且不需要保留自由/单任务推进兼容层。进入任务拆分前必须接受以下条件：内部标识写入当前 Markdown frontmatter 权威存储而非新建 JSONL；上线使用维护窗口和数据备份；实现任务与当前仍活跃的项目物化、Agent 建项和工作流聊天 OpenSpec change 做逐项冲突检查。

## 阻塞问题

当前没有需要产品重新决策的阻塞问题。

进入实现前的技术门禁：

1. **存储事实纠正**：项目权威存储是 Markdown frontmatter，不是 JSONL。建议采用 `executionModel: stage_pipeline_v1` 并禁止创建平行 JSONL。
2. **重叠 change 协调**：`unify-project-materialization`、`add-agent-managed-vo-projects`、`add-project-workflow-chat-realtime-stream` 与本变更共享调用方。建议每个实现 task 开始前读取其最新状态，冲突时暂停并更新规格。
3. **破坏性上线**：不做旧项目兼容意味着不能仅回滚代码。建议将状态目录备份、精确旧项目清单和恢复演练列为发布阻断项。

## 主要风险

- **稳定性**：同阶段最多可包含 100 个任务，当前无界线程启动会形成资源突刺。采用共享 8-worker 有界执行器和有界队列。
- **数据一致性**：并行任务完成会同时尝试推进阶段。通过项目锁、`currentRunId` 和单次 reservation 保证只推进一次。
- **安全**：现有系统没有通用项目经理 RBAC。浏览器管理沿用 management token，Agent 沿用项目关系授权；跳过决定必须写审计。
- **性能**：拖动过程中持续写完整项目会放大 Markdown 全量重写。仅在 drop 完成后提交一次完整 assignment，并使用 revision。
- **兼容性**：删除多个项目级字段和 `executionOrder` 会影响物化、模板、计划任务、通知、实时投影和测试。必须使用调用方 inventory 作为删除清单。
- **可回滚性**：新旧存储形状不双写。回滚必须同时恢复代码和上线前状态目录备份。
- **可观测性**：没有 run/stage 维度时无法区分未派发、排队、执行失败和未推进。日志与计数器必须包含 project/task/stage/run/attempt/revision。

## 关键追问

**Q：为什么不直接允许重复 `executionOrder`？**
A：现有排序、启动、活动任务和完成回调都以单任务为核心。只允许重复编号仍会被 `activeTaskId` 和 `maxActiveTasks: 1` 阻断，也不能正确处理并行完成竞态。

**Q：为什么删除旧属性而不是保留计算镜像？**
A：可写镜像会重新成为隐藏状态权威，使 legacy caller 能恢复 single/continuous 行为，并造成新旧状态漂移。

**Q：为什么内部标识不按用户原话写 JSONL？**
A：仓库的项目权威是 `MarkdownProjectStore`；新建 JSONL 会造成双写和恢复冲突。frontmatter 能提供同等持久化标识且服从当前架构。

**Q：如何保证同阶段启动不是部分成功？**
A：先对整阶段做无副作用预检，再原子 reservation；reservation 后的执行器拒绝不会伪装成成功，而是将阶段置为 blocked，保留已提交任务的真实状态。

**Q：为什么需要全局并发上限？**
A：作者配置允许最多 100 个初始任务。产品上的“并行”表示同阶段同时具备执行资格，不代表允许单项目无界创建线程或压垮 provider。

**Q：暂停为何使用两阶段？**
A：项目锁内只能提交状态，不能等待 provider 取消。先禁止新派发，再在锁外取消，最后原子收敛，才能避免长时间持锁和取消期间推进下一阶段。

## 测试与上线建议

- 将所有创建路径写入 marker/stage 的存储 round-trip 测试列为第一批门禁。
- 对双 start、双 completion、完成与暂停并发、skip 审批与 completion 并发做确定性竞态测试。
- 验证任务级 start、mode/startMode/restartPipeline 和旧字段无法重新启用单任务行为。
- 使用 100-task 单阶段夹具验证有界执行、队列拒绝、阶段阻塞和恢复，不做无证据的性能声明。
- 对 project store 进行备份、旧项目清单生成、精确删除和恢复演练；任何一步失败都不得上线。
- 后端与前端同时发布，先运行不修改数据的 invariant 检查，再开放项目管理入口。
- 使用 Figma 参考视口完成截图对比，并覆盖删除保存按钮后的布局、拖拽自动保存、冲突恢复和锁定态。
