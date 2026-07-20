# Human Resources Technical Review

## 评审结论

**带条件通过。**

方案已覆盖全局 HR 优先创建、档案管理员生命周期抽取、HR 名册、日报、评价、权限审计、一级 UI、调度、降级、测试和开发机 OpenClaw 验证。进入任务拆分的条件是：任务清单必须保留“characterization-first”“每个实现任务同步单测”“档案室与会议回归”“开发机真实 OpenClaw 验收”四类独立门禁，不能合并为最后一次笼统测试。

## 阻塞问题

当前没有阻止技术方案成立的问题。

开发机的具体目标和部署命令尚未确定，但这不改变架构；它必须在真实环境验收任务开始前明确，否则测试结果确认将被阻塞。

## 主要风险

### 稳定性

- 档案管理员抽取可能改变已有创建、Profile 修复、状态或降级语义。方案通过保留旧状态文件、兼容 delegates、先锁定 characterization、逐片迁移规避。
- 日报 Agent 调用可能长时间阻塞或堆积。方案采用持久 claim、有界 worker、超时、有限重试和单 Agent 隔离。
- 重启、双 loop 或人工重试可能产生重复周期。数据库唯一键和 occurrence/claim fencing 是必须测试项。

### 数据一致性

- Agent 改名不能切断历史，所有关联必须使用稳定 AI ID。
- 原始日报、归一化日报和评价版本不能无痕覆盖；修订必须保留版本和原因。
- 成功跨 Agent 披露必须先提交审计记录；审计写失败时披露失败关闭。
- SQLite schema 迁移必须在事务中完成，失败不得留下半迁移状态。

### 安全与隐私

- 产品确认 VO 体系内部交互默认可信；`X-VO-Agent-Id` 作为操作日志身份即可，不要求密码学级别的调用者证明。
- 人类完整视图必须使用 management token；普通 Agent 路由不能复用完整 DTO 后在前端隐藏字段。
- 日志、指标、证据和导出不得包含 bearer、管理 token、原始 provider envelope 或无界 transcript。
- 本设计不防御拥有整机和所有 workspace 读取权限的恶意本地进程，该威胁边界需要在文档中保留。

### 性能与容量

- 所有 Agent 同时请求会放大 provider 压力，默认 worker 数必须小且有上限。
- 证据读取必须按 Agent/日期过滤并限制每类数量，禁止扫描全部聊天和全部 workspace。
- 人事历史和访问日志需要分页；UI 不得一次加载全部历史。
- 高频失败日志需要限频，否则 provider 故障时会形成日志风暴。

### 兼容性

- 会议资格必须从“所有系统角色禁止”变成按角色策略判断，但档案管理员旧错误语义需要保留。
- 项目分配应升级为通用 `assignable=False` 策略，同时覆盖现有 archive-manager 专用调用点。
- HR Agent 目录必须注册为当前 VO `/skills` 内置 Skill，不得复制进 Agent workspace；已有 communication skill 的分发兼容性保持不变。
- 本地已有用户修改的 project-authoring Skill 和测试不属于该需求，任务实现不得误改。

### 可回滚性

- HR master/scheduler 开关必须独立，先停自动写再停整个 HR。
- 回滚不删除 HR Agent 或 HR 数据，避免无法恢复；HR 只暂停。
- 档案管理员继续使用原状态路径，公共逻辑抽取不引入不可逆数据迁移。

### 可观测性

- 必须区分没有到期、已到期未 claim、执行中、Agent 超时、归一化失败、评价失败、审计失败和成功无更新。
- 健康视图需要包含最老未完成周期/claim 年龄，否则无法判断是否堆积。
- 开发机验收记录必须包含环境、版本、命令、结果和未覆盖项。

## 关键追问

### Q1：为什么先抽公共生命周期，仍能满足“第一阶段先创建 HR”？

第一阶段的产品出口仍是 HR 被创建；公共生命周期是创建 HR 的内部前置切片。它先通过档案管理员 characterization 固定行为，再抽取最小公共能力，随后立即用同一能力创建 HR。不会先实现名册再补 HR。

### Q2：为什么不直接复制档案管理员代码？

复制会将 provider 创建、Profile 修复、状态、保护和错误处理分裂为两套，未来第三个 VO 系统 Agent 会继续放大。角色配置加 ports 可以复用生命周期，同时不共享档案室与 HR 业务。

### Q3：为什么选择 SQLite，而不是项目常用的 JSON？

该域同时需要日报历史、评价版本、唯一约束、并发 claim、跨 Agent 审计和按 Agent/日期分页。单 JSON 会不断全量重写，分片 JSON 又需要自建事务。Python 内置 SQLite 在不增加外部依赖的情况下提供原子事务和索引；代价是人工不可直接阅读，通过 management export/diagnostic 补足。

### Q4：为什么不用 OpenClaw cron 作为日报唯一调度器？

本地没有 OpenClaw，且 Gateway cron 的重复、丢失和重启状态不能成为 HR 数据一致性的唯一依据。VO 以日期唯一键和 durable claim 为权威，OpenClaw 只承担 Agent 对话与 HR 推理，测试和降级更明确。

### Q5：Agent 查看为什么不再需要 grant？

产品接受 VO 内部 Agent 自报身份，并将访问日志定位为尽力记录而非安全审计。接口仍要求 loopback、无浏览器 Origin、HR action header，并校验 AI ID 已登记且活跃；所有 Provider 因此可使用同一套接口，无需 workspace 凭证交付。
最终数据库也不保留 access grant 表或 Skill/grant readiness 字段；schema v3 会直接删除早期开发版本留下的相关数据。

### Q6：HR 如何评价但不“编造绩效”？

原始 Agent 回答不可变保存；HR 归一化与 HR 判断分层；证据通过只读端口提供并记录引用；输出 schema 拒绝数字评分和排名；证据不足时必须使用 `insufficient_information`。未提交日报本身不支持低工作量结论。

### Q7：HR 能参加会议会不会改变会议流程？

不会。HR 使用普通 participant 生命周期、占用和恢复。唯一变化是资格策略明确允许 HR；档案管理员继续禁止。会议记录只有在与当日工作相关时才可能成为后续只读证据，参会本身不触发评价。

### Q8：不同 Provider 如何使用 HR Skill？

所有 Provider 都从当前 VO 读取同一份内置 `vo-agent-hr`，不需要安装，也不需要 Provider 适配器。Agent 查询当前 VO Agent 列表确认自己的稳定 AI ID，然后携带 HR action header 和 AI ID 调用受控接口；管理界面不再显示授权 readiness。

## 测试与上线建议

任务清单必须至少独立覆盖：

1. 档案管理员、会议资格和项目分配的变更前 characterization baseline。
2. system-Agent lifecycle/profile/path/provider 的纯单元测试。
3. 档案管理员逐片迁移及 Phase 1–8 回归。
4. SQLite repository schema、事务、并发、唯一键、迁移失败和分页测试。
5. Agent 发现、改名、停用、恢复、HR self-exclusion 和介绍冲突测试。
6. `vo-agent-hr` catalog/Agent 指南曝光、禁止 workspace 分发或凭证依赖测试。
7. 调度时区、到期、启动补偿、双 loop、claim 过期、Agent 超时和队列上限测试。
8. 原始日报、归一化、未提交、补交、重复提交和失败隔离测试。
9. 评价 authority、证据、信息不足、版本修订、无评分/无排名测试。
10. management token、可信 Agent 身份 header、字段裁剪、来源拒绝、审计成功与审计失败关闭测试。
11. UI、i18n、错误态、分页、暂停/恢复和降级浏览测试。
12. 相关 Python/Node 回归、静态模块边界和 live browser 验收。
13. 开发机先关闭开关部署，再分阶段启用 HR 生命周期、Skill/名册、调度/评价。
14. 真实 OpenClaw 下验证 HR 与档案管理员隔离、重启修复、会议、对话、日报、评价和访问审计。
15. 回滚演练：停 scheduler、停 HR、保留数据、档案室继续工作。

放量继续门槛：当前阶段无重复 Agent/周期、无档案室或会议回归、无未授权字段泄露、无持续 claim 堆积、无未解释 provider 错误。任一条件失败则关闭对应开关并保留诊断证据。
