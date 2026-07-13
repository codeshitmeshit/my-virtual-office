# Technical design review

## 评审结论

**带条件通过。** 方案满足已确认的后台模块化规格，未引入新外部依赖、数据迁移或产品行为变化。进入 tasks 前，必须把下述条件转换为可验证任务：完整 writer/caller inventory、精确 Provider/SSE characterization、并发 fencing、容量基线、单进程 `start.sh` 验收和回滚演练。

## 阻塞问题

无阻塞设计问题。

条件项：当前各 Provider 的事件别名、approval queue 上界、transport-only delegate 最终白名单需要由基线任务从代码生成并冻结。建议选项是“先建立自动生成 inventory/manifest，再开始任何迁移”，设计已采用该选项。

## 主要风险

- **稳定性**：取消、完成、approval continuation、timer cleanup 并发可能产生双 terminal。方案使用 run generation/version 和 claim token CAS。
- **数据一致性**：幂等 reservation 与 worker launch 分离会留下假 active。方案要求 reservation 后 launch 失败也进入 terminal compare-and-set。
- **安全**：通用事件/approval DTO 可能携带 credential、raw output、prompt、绝对路径。方案要求进入 journal/notification 前 allowlist、bound、redact。
- **性能**：当前全局 event deque 的 scope replay 可能 O(4000)。方案保留 4,000 上界并增加 eviction-consistent scope index，以固定 1/20/100 与 10/1,000/4,000 fixture 验证。
- **兼容性**：把 Provider 能力压成最低共同接口会改变 fallback/cancel/approval 语义。方案使用 capability ports 和 provider-path adapter。
- **可回滚性**：外部 Provider/Feishu 效果不可逆。方案保持历史格式不变，并在 release/rollback rehearsal 记录、停止和对账外部效果。
- **可观测性**：若只看 HTTP 成功无法区分未启动、运行中、事件丢失、terminal 竞争。方案要求 operation/state/event/idempotency/stale token/retained count/duration 诊断。

## 关键追问

**Q：为什么不新建持久化 Provider Run Store？**

A：现有 Provider 进程本身不能跨 server restart 恢复；新增 Store 会扩大范围并制造“记录存在但原生进程不存在”的新一致性问题。本期仅抽取现有内存语义。

**Q：为什么不能保留旧新两个 coordinator 做灰度？**

A：双 coordinator 可能重复启动真实 Provider 工作。灰度单位必须是调用路径/Provider slice，每个命令在任一时刻只有一个 owner。

**Q：最容易拖慢主链路的点是什么？**

A：在 registry lock 内调用 Provider、扫描 event journal、或向 SSE socket 写入。设计明确把慢调用/序列化/IO 移出锁，并为 scope replay 建索引与性能门禁。

**Q：OpenClaw 是否必须被强制改成 background run？**

A：否。OpenClaw 只迁移其已有 conversation/queued delivery orchestration；capability model 禁止合成不存在的 run/SSE 行为。

**Q：关闭或回滚后残留状态如何处理？**

A：停止接收新 run，等待或取消 active，保存 pending approval/idempotency/event/conversation 证据，停止 candidate，恢复 prior code 并通过 `start.sh` 重启。外部效果单独对账。

**Q：如何证明协议未变化？**

A：迁移前冻结 route/request/response/status/SSE event/Last-Event-ID/approval/cancel/native-ID fixtures；每个 slice 做 exact compatibility comparison，最终跑完整 Provider、Project、Meeting、浏览器和启动验收。

## 测试与上线建议

- 建立每个 Provider path 的 happy/failure/timeout/cancel/approval/conversation/SSE trace manifest。
- 覆盖同 scope 并发 start、不同 scope 并发、late result、cancel-vs-complete、approval replay、cleanup-vs-new generation。
- 覆盖 event 0/1/4,000/4,001、cursor eviction、reconnect、heartbeat、malformed/oversized/raw-secret payload。
- 覆盖 Provider unavailable、adapter exception、history write failure、notification failure、SSE disconnect，证明其他 Provider 不受影响。
- 固定 1/20/100 run 和 10/1,000/4,000 event 性能基线，记录 adapter calls、terminal events、journal scans、retained bytes、lock duration、median/p95。
- 上线从代码落地且无双 coordinator 开始；逐 Provider slice 切换，每步以 focused regression + large-task CR 为继续门槛。
- 最终候选只通过 `start.sh` 启动；真实凭据不可用时使用 fake/local adapter，并明确记录 manual-only 外部覆盖。
- 回滚演练必须验证旧代码读取原 conversation/history/native-ID 状态，并对 Provider/Feishu 非可逆效果做 reconcile。
