# Technical Review

## 评审结论

**带条件通过。** 方案已覆盖已确认规格的主链路、异步边界、数据权威、并发、容量、安全、观测、灰度和回滚。进入任务规划的条件是：基线必须先于行为修改；并发 2 必须有 app-server 多路复用证据；快速路径必须由默认关闭的总开关保护；关键状态恢复和 flag-off 回滚必须作为独立验收项。

## 阻塞问题

无当前阻塞问题。若后续无法证明不同 thread 的 app-server 并发安全，则 `VO_CODEX_MAX_CONCURRENT_TURNS` 必须保持 1，不得通过放宽隔离、审批或终态正确性来满足并发目标。

## 主要风险

- **稳定性：** reader callback 中残留同步磁盘或外部调用会阻塞所有 app-server 消息；design 已要求 callback 有界并将 O(N) progress/activity 写移出。
- **数据一致性：** transient 与 durable 分类错误可能让审批或终态丢失；design 已给出权威映射、stable ID 和 barrier。
- **安全：** 新增时间线和指标可能意外携带 prompt/路径；design 限制为 numeric timing、event class 和摘要 ID。
- **性能：** coalescer 可能变成新队列热点；design 给出 scope、fragment、byte、global 四层容量以及 flush/bypass 策略。
- **兼容性：** flag-off 路径和 polling/activity 兼容投影可能漂移；必须双模式执行 characterization。
- **可回滚性：** 运行中直接关开关可能丢关键状态；design 规定停止接收、处理 active turn、drain durable、丢弃 transient 后重启。
- **可观测性：** 只看总耗时无法区分 Provider 与 VO；design 使用分阶段时间线并分开 first-native-event 与 first-text。

## 关键追问

**Q：为什么不先优化 Provider journal/SSE？**
A：现有固定基准显示它们是有界、索引化的微秒级路径；实际 Codex callback 在到达 journal 前执行两类全量文件重写，优先级更高。

**Q：为什么 transient 不继续同步落盘？**
A：确认规格允许 reasoning/delta 在崩溃后丢失；用户、审批、final 和 terminal 分别进入现有 durable authority，同步保存 transient 只放大首事件延迟。

**Q：为什么不直接解除 `_run_lock`？**
A：JSONL request ID 支持多 pending request 不等于 Provider 支持多 active turn；必须保留 per-thread ordering、全局 semaphore 和并发证明门禁。

**Q：为什么 coalescer 不丢弃高频文本？**
A：规格要求最终有序内容一致；压力下采用 force flush 或 bypass，不能以静默丢文本换性能。

**Q：为什么需要总开关和重启？**
A：本次同时改变事件调度、持久化频率和并发边界；启动时固定配置可以避免运行中半旧半新的状态，并提供确定性回滚。

## 测试与上线建议

- 基线与最终结果使用同一 10 次 warm-up、至少 100 次 measured fixture，报告 p50/p95/max/error 和操作次数。
- 覆盖首片段 bypass、33/100ms 窗口、barrier、容量满 force flush/bypass、乱序与重复事件。
- 覆盖同 conversation busy、不同 conversation 并发、capacity busy、approval 路由、cancel/terminal race、runtime exit。
- 覆盖 durable 写失败、compatibility projection 失败、重启丢 transient 但保留用户/approval/final/terminal。
- 覆盖 flag off、flag on concurrency 1、证明后 concurrency 2，以及冷启动/新 thread/其他 Provider 不回退。
- 上线必须从代码已部署且开关关闭开始；每次放量检查 SLO、busy 原因、buffer bytes、forced flush、durable failure、reader callback latency，再决定继续或回滚。
