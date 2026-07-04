# VO Usage Ledger 方案评审

## 产品评审

### 结论

产品目标已经足够清晰，可以进入第一版 checklist。

核心产品判断：

- 当前问题不是缺少 provider 账号额度信息，而是旧面板语义容易被理解为 VO 实际消耗。
- 第一版应优先建立可信的 VO 内部用量账本，而不是追求成本估算或全量归因。
- 账号额度与 VO 实际用量是两个不同视角，必须在 UI 上明确区分。

### 已确认的产品范围

- 第一版主要服务 VO 管理者。
- 第一版聚焦今日总量、byAgent、byModel、recent runs 和 usage 缺失率。
- 旧面板保留并改为账号额度语义。
- 新面板与旧面板同区域 tab 展示。
- 未返回 usage 的 run 不计入 token 总量，但需要暴露缺失情况。

### 产品风险

- 如果只展示 token 总量而不展示缺失率，用户仍可能误以为统计完整。
- 如果 `Account Limits` 和 `VO Usage` 的文案不够清楚，混淆会继续存在。
- 如果第一版加入成本估算，可能会因为模型价格、缓存计费和 provider 口径差异引入新的不信任。

### 产品建议

- 第一版所有统计文案都应强调 `recorded` 或 “已记录”，避免暗示绝对完整。
- 将 usage 缺失作为一级指标展示，例如 `Coverage: 92%` 或 `8 runs missing usage`。
- 成本估算、项目归因、任务归因放入后续版本。

## 技术评审

### 结论

暂无阻塞性技术问题，可以生成 checklist。

建议采用小步实现：

- 不删除旧 `/api-usage`。
- 新增 VO usage ledger 旁路。
- 在 provider run 完成后消费已经返回的 `usage` / `tokenUsage` 字段。
- 使用本地 JSONL 账本存储 run 粒度记录。
- 查询接口按时间范围读取并聚合。

### 数据来源评审

可用来源：

- Codex App Server 可能通过 token usage 事件返回 `tokenUsage`。
- Claude Code stream result 可能返回 `usage`。
- 其他 provider 如果返回 usage，后续可接入同一标准化入口。

关键限制：

- 不是所有 provider 或异常路径都会返回 usage。
- usage 字段命名不统一，需要标准化。
- 第一版不应通过额外请求 Agent 自报用量。

### 存储评审

建议：

- 使用全局按月 JSONL 文件，例如 `STATUS_DIR/vo-usage/YYYY-MM.jsonl`。
- 原始粒度为 `1 agent run = 1 record`。
- 每条记录包含 agent、model、providerKind、conversation、run、token counters、source、confidence。

理由：

- 与现有本地 JSON/JSONL 风格一致。
- append-only 写入开销低。
- 便于人工检查和后续迁移。
- 按月切分便于控制扫描范围和归档。

性能判断：

- 预估 5 到 6 千条记录/天对 4 核 8G 服务器可接受。
- 写入只是追加一行 JSONL，开销很小。
- 查询时需避免高频全量扫描；默认查今日或最近 7/30 天，recent 只返回有限条数。

### 状态和异常评审

需要处理：

- usage 可用：计入总量，source 标记为 provider reported。
- usage 缺失：记录 run 缺失状态或在聚合中计入 missing count，但不计入 token 总量。
- run 失败或取消：如果 provider 返回 usage，可以记录；如果没有，则只计缺失。
- 重复回调或流式/同步双路径：需要稳定 id 去重。

### UI 评审

建议 UI 区分：

- `Account Limits`：旧 quota/credential 面板。
- `VO Usage`：新本地 ledger 面板。

第一版 `VO Usage` 展示：

- 今日 recorded total tokens。
- 今日 runs / recorded runs / missing usage runs / coverage。
- Usage by Agent。
- Usage by Model。
- Recent Runs。

### 安全和隐私评审

- 账本不应记录 prompt、reply、工具输出或敏感凭据。
- 只记录统计元数据和低敏上下文字段。
- 如包含 conversationId、taskId、projectId，应视为本地诊断信息，不对外暴露。

### 可观测性评审

- 写入失败应只记录服务端日志，不应影响 Agent 正常回复。
- 查询接口应返回数据来源、统计范围和 coverage。
- UI 应能区分 “0 token” 和 “usage unavailable”。

## 评审结论

方案无阻塞问题，进入 checklist 阶段。

建议第一版实现边界：

- 后端 ledger + 聚合接口。
- UI tab 区分 Account Limits / VO Usage。
- 不做成本估算。
- 不做项目/任务细分。
- 不做数据库迁移。
