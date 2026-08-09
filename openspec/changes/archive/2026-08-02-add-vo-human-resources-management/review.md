# Merged Agent Management and Human Resources Technical Review

## 评审结论

**带条件通过。**

合并方案在产品上成立，技术上也可实现，但不能把“同一套 UI”解释为前端切换身份或仅隐藏字段。评审确认采用两条互不继承权限的服务端边界：

- 人类继续使用 management token；
- 普通 Agent 从现有无浏览器 Origin 的可信本机边界申请一次性 launch code，浏览器单次换取短时、HttpOnly、仅限 Agent Management 的 Agent 会话。

实现前置条件已经写入设计：Agent 配置从 `app/game.js` 拆入聚焦模块；低风险字段按字段自动保存、带 revision 和服务端 undo token；高风险变更使用绑定变更摘要的服务端确认 challenge；所有旧写接口必须纳入同一授权策略或取消写能力。开发机真实 OpenClaw 的浏览器端到端回归是测试结果确认的硬门禁，smoke、单测、静态测试和 API 测试都不能替代。

## 阻塞问题

当前没有阻止技术方案进入任务拆分的问题。

以下是后续门禁条件，而不是可延期的优化：

1. 任务清单必须先完成旧 Agent/office/workspace/create/delete 写入口盘点；任何旁路未封闭时，不得宣称权限完成。
2. Agent UI 会话不得由 URL 中的 Agent ID、localStorage、当前选中 Agent 或浏览器自报 header 建立。
3. 开发机 E2E 开始前必须写明批准的机器、部署命令、VO/OpenClaw 版本和开关顺序；缺失时测试结果确认保持阻塞。

## 主要风险

### 稳定性

- 档案管理员生命周期抽取可能改变已有创建、Profile 修复、状态或降级语义。保留旧状态文件和兼容 delegates，先锁定 characterization，再逐片迁移。
- 日报 Agent 调用可能长时间阻塞或堆积。使用持久 claim、有界 worker、超时、有限重试和单 Agent 隔离。
- 合并 UI 后 tab 切换可能丢失 Agent 选择、加载或滚动状态。以稳定 AI ID 为共享选择键，各 tab 独立保存视图状态。
- 一次性 launch code 或 Agent 会话在重启后失效是预期行为；UI 必须给出重新发起入口，不能把它误报为 HR 数据丢失。

### 数据一致性

- Agent 改名不能切断历史，所有关联必须使用稳定 AI ID。
- 自动保存必须按字段携带 `expectedRevision`；冲突显式返回，不允许静默 last-write-wins。
- undo 使用服务端生成、单次、短时、revision-checked 的逆操作 token，不能覆盖更晚修改。
- 原始日报、归一化日报和评价版本不能无痕覆盖；修订保留版本和原因。
- 成功跨 Agent 披露必须先提交审计记录；审计写失败时披露失败关闭。
- SQLite schema 迁移必须事务化，失败不得留下半迁移状态。

### 安全与隐私

- management token 与 Agent UI session 互不升级、互不继承；同一浏览器同时存在两者时，每条 route 仍按服务端 actor policy 判定。
- launch code 只允许无 Origin 的本机可信 Agent 请求生成，随机、单次、短过期；浏览器换票后从 URL 移除，日志只记录摘要和结果。
- 普通 Agent route 必须返回 public/self DTO，禁止获取完整 DTO 后由前端隐藏。
- Provider、branch、workspace、assignment、binding、创建和删除等高风险操作使用绑定 actor、Agent、action、before/after digest 和 expiry 的确认 challenge；简单 `confirmed: true` 不足以防止替换 payload。
- 现有 whole-office、workspace settings、create/delete 和 Provider-binding 写路由必须受同一策略保护，否则构成授权绕过。
- 日志、指标、证据和导出不得包含 launch code、session cookie、management token、原始 Provider envelope 或无界 transcript。

### 性能与容量

- 文本字段短 debounce，类别选择立即提交；服务端按字段写入，避免每次改动重写无关 HR 历史。
- launch code 仓库有总量、每 Agent 数量和过期清理上限，防止本机请求导致内存增长。
- 所有 Agent 同时日报会放大 Provider 压力，默认 worker 数必须小且有上限。
- 证据读取按 Agent/日期过滤并限制每类数量；人事历史和访问日志必须分页。

### 兼容性

- 新 `agent-management.js`、`agent-configuration.js` 和对应样式文件拥有新逻辑；`game.js` 只保留临时薄入口，迁移完成后删除旧 `_acp*` 实现。
- 旧 `role` 仅作为兼容读取和迁移来源，产品语义改为“职责/专长”；它影响展示、筛选和推荐，不成为授权或分配硬门禁。
- 独立 Human Resources modal、重复返回按钮和全局保存按钮在迁移完成后删除，右上角 `×` 作为唯一关闭入口。
- 会议资格从“所有系统角色禁止”改为角色策略，但档案管理员旧错误语义保留。
- HR Skill 仍是当前 VO `/skills` 内置能力，不复制进 Agent workspace。

### 可回滚性

- 先停 scheduler，再停 HR；不删除 HR Agent、HR 数据或 Agent 配置。
- 短时 Agent UI session 不持久化，重启自然失效，不需要数据迁移。
- 新 profile store 使用原子写和 revision；兼容读取旧 office-config，回滚时保留可恢复数据。
- 档案管理员继续使用原状态路径，公共逻辑抽取不引入不可逆迁移。

### 可观测性

- 自动保存区分 saving、saved、conflict、denied、failed、undo-expired 和 undo-conflict。
- Agent UI 会话记录 mint/exchange/replay/expired/inactive/origin-rejected 的安全码和关联 ID，不记录明文凭证。
- HR 命令区分 accepted、processing、partial、complete、failed，并暴露最老未完成 cycle/claim 年龄。
- E2E 证据必须可从浏览器动作关联到 HTTP/command ID、Provider 调用、持久化结果、重启恢复和最终 UI。

## 关键追问

### Q1：为什么普通 Agent 不能直接在浏览器传自己的 AI ID？

浏览器中的 query、localStorage、下拉选择和自定义 header 都可由页面脚本或用户改写。现有 Agent HR 接口正因如此明确拒绝浏览器 Origin。一次性换票把“可信本机 Agent 自报身份”限制在原有边界，浏览器只能获得服务端绑定后的短时身份，不能切换成 roster 中的另一个 Agent。

### Q2：短时 Agent UI session 是否违背“不需要 grant”？

不违背。它不是持久授权、Provider 凭证或 workspace 文件，不进入 HR 数据库，也不随 Skill 分发。它只是一次浏览器会话的短时 bearer，重启或过期即失效；originless Agent API 仍按原有可信边界工作。

### Q3：为什么高风险确认不能只发 `confirmed: true`？

如果确认与具体 before/after payload 不绑定，页面在用户确认后仍可能替换 Agent、workspace 或 Provider 值。服务端 challenge 绑定 actor、目标、动作和变更摘要，提交时重新校验 revision 与 expiry，才能证明确认对应的是用户看到的影响。

### Q4：自动保存和撤销如何避免互相覆盖？

每次只提交一个 allowlisted 字段和期望 revision。成功后服务端返回新 revision 与单次 inverse token；撤销只有在 token 未过期且当前 revision 仍匹配时生效。若已有更晚改动，返回冲突并保留新值。

### Q5：`role` 还有什么含义？

不再承担权限含义。旧 `role` 作为兼容数据迁移到“职责/专长”，用于展示、筛选和候选推荐；实际权限由 actor policy、系统角色策略和具体操作授权决定。

### Q6：为什么必须检查旧接口，而不只改新 UI？

服务端权限要求“直接受限 mutation 也拒绝”。如果 `/api/office-config`、Agent workspace settings、create/delete 或 binding 路由仍可无授权写入，用户绕开新 UI 就能完成同一高风险操作，前端确认没有安全意义。

### Q7：为什么开发机必须做端到端，而不是跑 API 回归？

该需求包含浏览器认证/换票、tab 状态、异步命令、真实 OpenClaw 对话、持久化、重启恢复和最终 UI 投影。只有从浏览器动作开始贯穿这些边界，才能覆盖集成失败；API-only 和 fake-provider 只能作为定位更快的辅助层。

## 测试与上线建议

任务清单至少独立覆盖：

1. 旧 Agent、office-config、workspace、create/delete、Provider-binding mutation route 盘点与基线。
2. system-Agent lifecycle/profile/path/provider 单元测试及档案管理员逐片迁移回归。
3. SQLite repository、目录、日报、评价、证据、审计和后台命令状态测试。
4. field-level profile store 的原子写、revision、冲突、迁移、自动保存和 undo token 测试。
5. human/Agent actor policy、self/public/full DTO 和全部旁路拒绝测试。
6. launch code/session 的 mint、单次 exchange、HttpOnly/SameSite/path、expiry、replay、CSRF/origin、inactive Agent、并发和 restart 测试。
7. 高风险 confirmation challenge 的 payload binding、revision、expiry、replay 与替换攻击测试。
8. 模块边界测试：新逻辑不增长 `game.js`/`server.py`，无反向 import、隐藏全局或双 authority。
9. 合并 UI 的共享 roster/selection、tab/scroll/loading 恢复、唯一 `×`、无全局保存按钮、紧凑下拉视觉网格、键盘操作和 i18n。
10. HR 命令 accepted→processing→terminal、刷新恢复、部分失败与降级可读性。
11. Archive Room、会议、项目分配/删除、Agent workspace、Provider 和既有 VO 回归。
12. 开发机关闭 HR 的浏览器基线与分阶段启用证据。
13. 人类浏览器 E2E：management token、同步、补充信息、日报纠正/周期、持久化和刷新投影。
14. 普通 Agent 浏览器 E2E：真实 originless mint、换票、self edit/undo、同事 public read/audit、restricted denial。
15. 高风险人类 E2E：影响说明、challenge 确认、真实 Provider/branch/workspace/binding 结果。
16. VO/OpenClaw 中途重启、claim 恢复、session 失效重进、数据恢复和最终 UI。
17. 回滚演练：停 scheduler、停 HR、保留数据，Archive Room 与既有 VO 继续工作。

放量继续门槛：无授权旁路、无跨 audience 字段泄漏、无 silent overwrite、无重复 Agent/周期、无持续 claim 堆积、无 Archive Room/会议/项目回归、无未解释 Provider 错误。任一条件失败则关闭对应开关并保留诊断证据。
