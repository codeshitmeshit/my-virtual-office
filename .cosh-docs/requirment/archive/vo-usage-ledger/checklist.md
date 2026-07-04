# VO Usage Ledger 测试 Checklist

确认状态：已确认

## 验收标准

### CHK-001 旧账号额度面板仍可访问

- 关联需求点：保留旧 `API Usage` 能力，但改为账号额度语义。
- 验证方法：打开资源用量区域，查看旧 provider quota/credential 信息是否仍能展示。
- 预期结果：旧能力未被删除；用户能看到 provider 额度或凭据状态；文案不再暗示这是 VO 实际 token 用量。

### CHK-002 新增 VO Usage 入口

- 关联需求点：新旧统计在同一区域用 tab 区分。
- 验证方法：打开资源用量区域，检查是否存在 `Account Limits` 和 `VO Usage` 两个入口。
- 预期结果：用户能明确在两个 tab 间切换；两个 tab 的语义清楚区分。

### CHK-003 VO Usage 展示今日 recorded total tokens

- 关联需求点：第一版回答“今天 VO 记录到多少 token”。
- 验证方法：制造或使用已有带 usage 的 Agent run，打开 `VO Usage`。
- 预期结果：今日 token 总量展示为已记录 usage 的聚合值；没有 usage 的 run 不被计入 token 总量。

### CHK-004 VO Usage 展示 byAgent 排名

- 关联需求点：管理者需要知道哪个 Agent 用得最多。
- 验证方法：准备多个不同 Agent 的 usage records，查看 `Usage by Agent`。
- 预期结果：各 Agent 的 total tokens 能正确聚合和排序；显示字段能识别 Agent。

### CHK-005 VO Usage 展示 byModel 排名

- 关联需求点：第一版必须包含模型维度。
- 验证方法：准备多个模型的 usage records，查看 `Usage by Model`。
- 预期结果：各模型的 total tokens 能正确聚合和排序；模型为空或未知时有明确兜底展示。

### CHK-006 展示 usage 缺失情况

- 关联需求点：无 usage 的 run 不计入总量，但展示未统计 run 数或缺失率。
- 验证方法：准备至少一条没有 usage 的 run 和一条有 usage 的 run。
- 预期结果：总 token 只统计有 usage 的 run；UI 显示 missing usage runs 或 coverage；用户能判断统计覆盖度。

### CHK-007 Recent Runs 区分 recorded 和 unavailable

- 关联需求点：最近 run 列表应暴露有无 usage。
- 验证方法：查看 `Recent Runs` 列表。
- 预期结果：有 usage 的 run 显示 token 数；无 usage 的 run 显示 `Usage unavailable` 或等价文案。

### CHK-008 不额外请求 Agent 自报 token

- 关联需求点：统计来自 provider 已返回 usage，不触发额外模型调用。
- 验证方法：执行一次 Agent run，观察调用路径或日志。
- 预期结果：没有出现为了统计 token 而追加的 Agent 对话或模型调用。

### CHK-009 账本记录不包含敏感正文

- 关联需求点：账本只记录统计元数据，不记录 prompt/reply/tool output。
- 验证方法：检查本地 usage ledger 文件中的记录字段。
- 预期结果：记录包含 agentId、model、runId、token counters 等元数据；不包含用户消息正文、模型回复正文、API key 或工具输出。

### CHK-010 JSONL 写入失败不影响正常回复

- 关联需求点：用量统计是旁路能力，不应影响 Agent 正常使用。
- 验证方法：模拟或制造 ledger 写入失败场景。
- 预期结果：Agent 回复仍正常返回；服务端记录错误日志；UI 可以继续使用已有数据。

### CHK-011 去重避免重复累计

- 关联需求点：流式和同步路径可能重复看到同一个 run。
- 验证方法：对同一 run 模拟重复完成事件或重复写入。
- 预期结果：同一 run 不会被重复计入 total tokens、byAgent 或 byModel。

### CHK-012 查询范围不会高频全量扫描历史

- 关联需求点：性能需适配 4 核 8G，默认只查有限范围。
- 验证方法：打开 `VO Usage` 并观察请求参数或返回范围。
- 预期结果：默认查询今天或有限时间范围；recent 返回有限条数；不会为了面板刷新频繁读取全部历史。

### CHK-013 按月 JSONL 文件可被正确读取

- 关联需求点：建议使用按月全局 ledger 文件。
- 验证方法：准备当前月 usage 文件并请求统计接口。
- 预期结果：当前月文件中的记录能被读取和聚合；缺失文件时返回空统计而不是错误。

### CHK-014 旧 Account Limits 与新 VO Usage 数据不混算

- 关联需求点：账号额度与 VO 用量语义必须分离。
- 验证方法：对比 `Account Limits` 与 `VO Usage` 的数据来源和展示指标。
- 预期结果：Account Limits 展示 quota/credential 状态；VO Usage 展示本地 ledger 聚合；两者不会互相参与计算。

### CHK-015 多语言文案清晰

- 关联需求点：避免继续误导用户。
- 验证方法：切换中英文界面，检查 tab 标题、空状态、缺失率、统计范围文案。
- 预期结果：中文和英文都能表达 “账号额度” 与 “VO 已记录用量” 的区别。

### CHK-016 回归现有聊天和 run 流程

- 关联需求点：新增统计不能破坏现有 Agent 使用。
- 验证方法：分别执行 Codex、Claude Code 或其他可用 Agent 的普通聊天和 run 流程。
- 预期结果：聊天、流式进度、历史记录和错误处理保持原有行为；用量统计为旁路增强。

### CHK-017 空状态清楚

- 关联需求点：新功能上线初期可能没有 ledger 数据。
- 验证方法：清空或使用无 usage ledger 的环境打开 `VO Usage`。
- 预期结果：UI 显示清楚的空状态，例如 “No recorded VO usage yet”；不显示错误或误导性的 0 完整统计。

### CHK-018 人工验证路径明确

- 关联需求点：上线前需要人工判断产品语义是否解决混淆。
- 验证方法：人工查看两个 tab 和核心指标，判断是否能区分账号额度与实际用量。
- 预期结果：人工验证者能准确说出两个 tab 的区别，并能解释缺失率含义。

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-07-04T20:16:01+08:00
- 用户确认摘要：用户输入 `continue`，理解为确认当前 checklist 并继续生成 todolist。

## 测试执行记录

执行时间：2026-07-04T20:16:01+08:00 至 2026-07-04T21:07:08+08:00

已执行自动化检查：

- `./.venv/bin/python tests/test_vo_usage_ledger.py`
  - 覆盖：usage 标准化、嵌套 `last/total`、Claude cache 字段、recorded/unavailable run、去重、coverage、byAgent、byModel、按月 JSONL 文件、账本不保存 prompt/reply/tool output、agent/model 查询过滤、Claude Code provider 异常时记录 unavailable usage。
  - 结果：通过。
- `./.venv/bin/python tests/test_claude_code_provider.py`
  - 覆盖：Claude Code provider 既有 usage 转换和 provider 行为回归。
  - 结果：通过。
- `./.venv/bin/python tests/test_codex_bridge.py`
  - 覆盖：Codex bridge tokenUsage 事件和 run state 回归。
  - 结果：通过。
- `./.venv/bin/python -m py_compile app/server.py tests/test_vo_usage_ledger.py`
  - 覆盖：后端语法检查。
  - 结果：通过。
- `node --check app/api-usage.js`
  - 覆盖：前端资源用量脚本语法检查。
  - 结果：通过。
- `./.venv/bin/python -m json.tool app/locales/en.json` 与 `./.venv/bin/python -m json.tool app/locales/zh.json`
  - 覆盖：中英文 locale JSON 格式。
  - 结果：通过。
- `./.venv/bin/python tests/test_provider_runtime_config.py`
  - 覆盖：provider/runtime 配置合并与保存路径回归，确认资源用量改动未破坏共享配置行为。
  - 结果：通过。
- `./.venv/bin/python tests/test_feishu_notifications.py`
  - 覆盖：当前工作区已有飞书通知相关改动的回归，确认 VO 用量统计改动未引入共享配置/通知路径的明显破坏。
  - 结果：通过。
- `./.venv/bin/python -m compileall -q app tests/test_vo_usage_ledger.py`
  - 覆盖：app 与新增 VO usage 测试文件的 Python 编译检查。
  - 结果：通过。

实现复核：

- `GET /api/vo-usage` 已接入后端聚合函数；默认范围为当天，按月读取 `STATUS_DIR/vo-usage/YYYY-MM.jsonl`。
- Codex、Claude Code、Hermes 聊天完成路径已做旁路记录；统计只使用 provider result 中已有 `tokenUsage`，不会额外请求 Agent 自报 token。
- 账本记录仅包含 Agent、provider、model、run/session/thread id 和 token counters 等元数据，不写入 prompt、reply、tool output 或密钥。
- 旧 `/api-usage` 仍保留为账号额度来源；新 `/api/vo-usage` 为 VO 本地账本来源，前端以 `Account Limits` / `VO Usage` tab 区分。
- Codex 与 Claude Code 异步 run worker 复用对应 chat handler；完成结果会经过同一 `_append_vo_usage_record` 旁路记录，避免 chat/run 双路径重复实现和重复累计。
- Hermes 和 Claude Code 的 handler 级异常路径会旁路写入 unavailable usage record；统计覆盖率不会因为 provider 异常而偏乐观。

运行时验收：

- 启动当前工作区代码的临时服务：`VO_PORT=8190 VO_WS_PORT=8191 VO_STATUS_DIR=/private/tmp/vo-usage-runtime-check .venv/bin/python app/server.py`。
- `GET http://127.0.0.1:8190/health` 返回 `{"ok": true, "status": "running"}`。
- `GET http://127.0.0.1:8190/api/vo-usage?limit=5` 在空账本状态返回 `ok: true`、`source: vo-usage-ledger`、`totals.runs: 0`、`byAgent: []`、`byModel: []`、`recent: []`。
- 通过 in-app browser 打开 `http://127.0.0.1:8190/`，启用临时配置 `features.apiUsage=true` 后，资源用量面板可见，包含 `账号额度` 与 `VO 用量` 两个 tab。
- 空账本 UI：切换到 `VO 用量` 后显示 `暂无已记录的 VO 用量`。
- 非空账本 UI：使用同一后端 helper 在临时状态目录写入一条 provider-reported usage 记录，接口返回 `totalTokens: 168`、`recordedRuns: 1`、`coveragePct: 100.0`、`byAgent[0].agentId: runtime-agent`、`byModel[0].model: gpt-runtime`。
- 非空页面可见内容包含 `今日已记录 168`、`覆盖率 100.0%`、`runtime-agent`、`gpt-runtime` 和 `最近运行`，证明核心指标在 UI 中可见。
- 临时服务已停止；运行时测试数据仅写入 `/private/tmp/vo-usage-runtime-check`。

待人工确认：

- CHK-018 仍需要用户最终确认产品语义是否满足预期。
- CHK-016 的完整运行时回归仍建议在实际服务启动后执行一次 Codex / Claude Code / Hermes 聊天路径。

## 最终验收记录

- 确认项：checklist 测试通过确认
- 确认时间：2026-07-05T02:53:18+08:00
- 用户确认摘要：用户确认“这个需求我验收没问题了”，视为测试结果和产品语义验收通过。

- 确认项：最终 done 确认
- 确认时间：2026-07-05T02:53:18+08:00
- 用户确认摘要：用户要求在需求侧标记已验收并 push，视为需求闭环完成确认。
