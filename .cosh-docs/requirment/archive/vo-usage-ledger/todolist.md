# VO Usage Ledger Todo List

## TODO-001 梳理现有用量与 Provider 返回字段

- 目标：确认 Codex、Claude Code、Hermes/OpenClaw 当前返回 usage/tokenUsage 的位置和字段形态。
- 涉及区域：provider 执行结果归一、chat/run 完成路径、现有 `/api-usage` 面板。
- 输入：现有 provider result、run event、history 接口和 usage 相关代码。
- 输出：明确的字段映射和可接入位置清单。
- 依赖：无。
- 完成标准：能列出第一版实际接入的 provider；不能返回 usage 的路径有明确缺失处理策略。
- 关联 checklist：CHK-003、CHK-006、CHK-008、CHK-016。

## TODO-002 设计 VO Usage ledger 记录 schema

- 目标：定义 run 粒度账本记录字段，确保能支持 byAgent、byModel、coverage 和 recent runs。
- 涉及区域：本地状态文件、usage 记录结构、隐私边界。
- 输入：需求文档、评审结论、TODO-001 字段映射。
- 输出：schemaVersion、id、ts、providerKind、agentId、model、runId、token counters、source、confidence、missing reason 等字段定义。
- 依赖：TODO-001。
- 完成标准：schema 不记录 prompt/reply/tool output；能表示 usage available 与 usage unavailable 两类 run。
- 关联 checklist：CHK-006、CHK-007、CHK-009、CHK-011。

## TODO-003 实现本地按月 JSONL ledger 写入能力

- 目标：提供轻量 append-only 存储，记录每次 Agent run 的 usage 状态。
- 涉及区域：`STATUS_DIR` 本地数据目录、文件写入、错误处理。
- 输入：TODO-002 schema。
- 输出：按月文件，例如 `STATUS_DIR/vo-usage/YYYY-MM.jsonl`。
- 依赖：TODO-002。
- 完成标准：写入失败不影响 Agent 回复；缺失目录可自动创建；同一 run 重复写入可去重或避免重复累计。
- 关联 checklist：CHK-010、CHK-011、CHK-013、CHK-016。

## TODO-004 实现 usage 标准化逻辑

- 目标：将不同 provider 的 usage/tokenUsage 统一为 VO Usage counters。
- 涉及区域：provider result 处理、usage 标准化 helper。
- 输入：OpenAI/Codex 风格、Claude Code 风格和现有 tokenUsage 结构。
- 输出：统一 counters：inputTokens、outputTokens、cacheReadTokens、cacheWriteTokens、reasoningTokens、totalTokens。
- 依赖：TODO-001、TODO-002。
- 完成标准：支持 snake_case、camelCase、嵌套 `last/total`；未识别 usage 时不产生误导性 token 总量。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006。

## TODO-005 接入 Agent run 完成路径

- 目标：在 Agent run 完成时旁路记录 usage，不增加额外模型调用。
- 涉及区域：Codex chat/run、Claude Code chat/run，后续可扩展 Hermes/OpenClaw。
- 输入：标准化逻辑、ledger 写入能力、现有 normalize result。
- 输出：每次 run 完成后写入 available 或 unavailable record。
- 依赖：TODO-003、TODO-004。
- 完成标准：不会新增“询问 Agent 用量”的请求；正常回复路径不受写入失败影响；流式和同步路径不会重复累计。
- 关联 checklist：CHK-008、CHK-010、CHK-011、CHK-016。

## TODO-006 实现 VO Usage 聚合查询接口

- 目标：提供 UI 所需的 summary 数据。
- 涉及区域：HTTP API、ledger 读取、聚合逻辑。
- 输入：按月 JSONL ledger。
- 输出：summary，包括 totals、coverage、byAgent、byModel、byDay、recent runs。
- 依赖：TODO-003、TODO-005。
- 完成标准：默认查询今天或有限范围；recent 限制数量；缺失文件返回空统计；不与旧 `/api-usage` 数据混算。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006、CHK-012、CHK-013、CHK-014、CHK-017。

## TODO-007 调整旧 API Usage 产品表达

- 目标：将旧 provider quota/credential 面板表达为账号额度，降低误解。
- 涉及区域：前端标题、文案、多语言资源。
- 输入：现有 `API Usage` 面板和 i18n 文案。
- 输出：`Account Limits` / 账号额度文案。
- 依赖：无。
- 完成标准：旧功能仍可访问；文案不再暗示它是 VO 实际 token 消耗。
- 关联 checklist：CHK-001、CHK-014、CHK-015。

## TODO-008 新增 VO Usage UI tab

- 目标：在同一区域提供 `Account Limits` 与 `VO Usage` 两个 tab。
- 涉及区域：侧边栏/资源用量面板、前端 JS、样式。
- 输入：VO Usage 聚合接口和旧 Account Limits 面板。
- 输出：可切换的两个 tab。
- 依赖：TODO-006、TODO-007。
- 完成标准：两个 tab 语义清楚；切换不破坏旧面板；空状态清楚。
- 关联 checklist：CHK-002、CHK-014、CHK-017、CHK-018。

## TODO-009 实现 VO Usage 核心展示

- 目标：展示第一版必要指标。
- 涉及区域：VO Usage 前端渲染。
- 输入：TODO-006 聚合接口返回。
- 输出：今日 recorded total tokens、runs、recorded runs、missing runs、coverage、byAgent、byModel、recent runs。
- 依赖：TODO-008。
- 完成标准：无 usage run 不计入 token 总量但显示缺失；有 usage run 显示 token；byAgent/byModel 排序正确。
- 关联 checklist：CHK-003、CHK-004、CHK-005、CHK-006、CHK-007、CHK-017。

## TODO-010 补充测试覆盖

- 目标：用自动化测试覆盖核心账本和聚合逻辑。
- 涉及区域：Python 单测、可能的前端轻量检查。
- 输入：ledger helper、标准化 helper、聚合接口。
- 输出：标准化、去重、缺失 usage、聚合、空状态相关测试。
- 依赖：TODO-003、TODO-004、TODO-006。
- 完成标准：测试覆盖 provider usage 字段差异、重复 run、missing usage 和默认查询范围。
- 关联 checklist：CHK-003、CHK-006、CHK-010、CHK-011、CHK-012、CHK-013。

## TODO-011 执行回归验证

- 目标：确认新增统计不破坏现有聊天、run 和旧 usage 面板。
- 涉及区域：Codex、Claude Code、旧 Account Limits、VO Usage UI。
- 输入：实现后的功能和 checklist。
- 输出：测试结果记录。
- 依赖：TODO-005、TODO-008、TODO-009、TODO-010。
- 完成标准：按 checklist 完成自动化和人工验证；失败项有明确修复记录。
- 关联 checklist：CHK-001、CHK-002、CHK-014、CHK-016、CHK-018。

## TODO-012 更新需求状态和交付说明

- 目标：在实现和测试后保持需求归档闭环。
- 涉及区域：`.cosh-docs/requirment/vo-usage-ledger/`。
- 输入：测试结果、用户确认。
- 输出：更新 checklist 测试记录、status.json 阶段、最终交付说明。
- 依赖：TODO-011。
- 完成标准：测试完成后等待用户确认 tested；最终 done 需等待用户确认后归档。
- 关联 checklist：CHK-018。
