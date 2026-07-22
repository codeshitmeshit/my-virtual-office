# 技术方案评审

## 评审结论

**通过。** 方案能够在不合并事务边界、不扩大权限入口、不迁移历史项目的前提下建立唯一 materialization 权威。周期自动执行的跨事务风险已通过“同事务持久化 intent、事务后启动、重复回调协调”解决；没有遗留阻塞问题。

## 阻塞问题

无。

## 主要风险

### 稳定性

- 周期实例创建成功但启动调用失败或进程崩溃：持久化 `pending`/`failed_retryable` intent，由同一 occurrence 的重复回调恢复。
- 默认启用执行导致 workspace 准备失败：创建整体失败并清理本次新建 workspace，不降级创建。

### 数据一致性

- 多入口默认字段再次漂移：基础字段只能由 `project_materialization.py` 生成，并用跨入口字段投影测试约束。
- 自动启动重复触发：复用 occurrence claim、确定性 Project ID、持久化启动状态和 Project Execution 原子启动门禁。
- 不同存储边界嵌套：root-store commit 内禁止调用 ProjectRepository execution start；启动只发生在 commit 之后。

### 安全

- AI 默认启用可能引入非预期资源消耗：确认内容明确展示执行状态和 Agent；仅跟踪必须显式选择；执行条件失败时 fail closed。
- workspace ownership 被 authoring source 污染：统一 `system/user` 语义，authoring provenance 单独保存。

### 性能

- materialization 仍为 O(columns + tasks + checklist)，不增加外部调用和持久化次数。
- 周期自动启动新增一次现有 Project Execution 命令，仅在用户明确授权的 occurrence 上发生，并在 root lock 外运行。

### 兼容性

- 历史模板的 `false` 可能是旧代码补出的默认：安全优先，按已存储 disabled 处理，不自动开启。
- 浏览器模板和手动 API 可能依赖当前响应：保留路由、status、payload 和 activity 类型，并加入兼容测试。

### 可回滚性

- 新字段均为 additive，旧代码可继续读取 Project；回滚后未处理的自动启动 intent 可能保持 inert，需要恢复新代码或用户手动启动。
- 使用现有 authoring/recurrence 开关停止新行为，不执行数据回写。

### 可观测性

- 自动启动需区分 requested、started、retryable failure、intervention；进入 bounded occurrence history 和现有 sanitised observability。
- 失败日志沿用限频和脱敏，禁止输出 grant、confirmation text、workspace credential 或 provider output。

## 关键追问

**Q：为什么不直接复用 `create_project` command？**
A：该 command 同时拥有手动校验、workspace 编排、repository mutation 和响应语义；直接复用会破坏 authoring 的 grant/template/recurrence/root-CAS 原子边界。复用纯 materializer 才能共享规则而不共享事务。

**Q：为什么 materializer 不负责 workspace 创建？**
A：文件系统操作有失败和清理语义，且不能在 repository/root lock 内执行。materializer 只投影已经准备好的 canonical workspace 值。

**Q：为什么不从确认 Markdown 直接解析 checklist？**
A：确认文本用于用户确认和 digest 审计，不应成为第二份结构化模型。skill 生成结构化 checklist，backend 验证，materializer 规范化。

**Q：为什么周期自动执行需要持久化 intent？**
A：Project commit 与执行启动无法组成一个分布式事务。没有 intent 时，commit 后崩溃会永久丢失自动执行；先写 intent 可以安全恢复。

**Q：为什么历史模板 false 不按 AI 默认 true 改写？**
A：旧 schema 无法区分用户明确关闭和代码补默认。自动开启可能执行用户不希望运行的历史自动化，安全性优先于猜测修复。

## 测试与上线建议

- 为 canonical Project/Task/column/checklist/workspace 建立表驱动单测和深拷贝测试。
- 对手动、Agent、浏览器模板、版本模板、周期实例执行基础字段投影对比，只允许声明的 overlay 差异。
- 覆盖 AI 缺省启用、显式仅跟踪、无效 executor、workspace 失败与 cleanup、确认 digest/idempotency 差异。
- 覆盖无 columns 四列生成、模板列 ID remap、Task Backlog fallback、验收标准 checklist 和会议数据隔离。
- 覆盖 create-only recurrence、create-and-execute、commit 后崩溃、启动失败重试、重复/并发 callback、已启动协调和 intervention。
- 覆盖历史 Project/模板读取、浏览器 API payload/activity、grant/template/version/recurrence/source 元数据兼容。
- 静态检查所有创建入口均调用 materializer，且 `project_authoring.py`/新模块不导入 `server.py`。
- 上线顺序为代码 + authoring/recurrence 开关关闭，先启用 Agent 直接创建，再 create-only recurrence，最后启用用户明确确认的自动执行 recurrence。
- 回滚前关闭 authoring 和 recurrence；确认无未观察的 pending auto-start intent，再回退代码。已启动 Project 走现有停止流程。
