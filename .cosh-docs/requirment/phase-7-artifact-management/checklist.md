# Phase 7 Artifact Management Checklist

确认状态：已确认

## 验收规则

- 本期只验收 Markdown 产物管理。
- 非 Markdown 文件不在本期产物列表中展示。
- 产物管理必须以通用能力和通用 UI 组件为基础，Phase 7 项目只是第一个适配场景。
- 本期不实现会议产物入口，但不能把核心能力写死在 Project Execution 任务看板中。
- 所有 checklist 项必须在隔离临时工作区或可控测试项目中验证。
- checklist 确认前不得生成 todolist。

## Checklist

### CHK-001 通用产物核心边界
- 验证方法：检查实现结构或单元测试，确认 Markdown 扫描、读取、路径安全和基础 source record shape 不依赖 Project Execution 任务看板对象。
- 预期结果：核心产物能力可以通过 adapter 输入上下文根目录和来源记录；Phase 7 项目逻辑位于适配层。
- 关联需求点：通用产物管理核心；后续会议功能可复用。

### CHK-002 通用产物 UI 组件
- 验证方法：检查前端实现或组件级测试，确认产物列表、来源展示、Preview/Source、空状态和错误状态由可复用视图承载。
- 预期结果：组件不硬编码 Project Execution 文案和任务字段；可通过配置显示项目上下文，后续可配置为会议上下文。
- 关联需求点：通用产物管理 UI；未来会议复用。

### CHK-003 Phase 7 项目适配层
- 验证方法：打开启用 Project Execution 且已绑定有效工作区的项目，检查项目页是否通过 Phase 7 adapter 提供产物管理入口。
- 预期结果：用户可以从项目页进入产物管理；入口不会破坏原有任务看板、报告、模板和编辑入口。
- 关联需求点：Project Execution 是首个产物管理适配场景。

### CHK-004 未来会议复用约束
- 验证方法：审查后端和前端产物能力的公开输入输出，模拟一个 meeting-like 上下文 payload 或 adapter stub。
- 预期结果：无需复制 Markdown 列表/读取/查看器主体逻辑，即可表达 meetingId、meeting title、source agent、generatedAt 等来源字段。
- 关联需求点：后续会议功能可使用同一产物管理能力。

### CHK-005 项目级产物入口
- 验证方法：打开启用 Project Execution 且已绑定有效工作区的项目，检查项目页是否提供产物管理入口。
- 预期结果：用户可以从项目页进入产物管理；入口不会破坏原有任务看板、报告、模板和编辑入口。
- 关联需求点：项目级产物入口；服务 Phase 7 任务结果验收。

### CHK-006 非 Project Execution 项目处理
- 验证方法：打开未启用 Project Execution 或未配置 workspace 的普通项目。
- 预期结果：产物入口不展示，或展示为明确不可用状态；不会让用户误以为可以浏览任意文件系统。
- 关联需求点：产物管理依赖项目绑定工作区；非通用文件浏览器。

### CHK-007 Markdown 产物列表
- 验证方法：在项目工作区创建多个 `.md` 和 `.markdown` 文件并刷新产物视图。
- 预期结果：列表展示 Markdown 文件，包含相对路径、文件名、大小和修改时间。
- 关联需求点：显示项目中的 Markdown 产物。

### CHK-008 非 Markdown 文件不展示
- 验证方法：在同一工作区创建图片、PDF、HTML、JSON、日志、压缩包和普通无扩展文件。
- 预期结果：这些文件不出现在本期产物列表中。
- 关联需求点：本期只展示 Markdown 文件。

### CHK-009 噪音目录排除
- 验证方法：在 `.git`、`node_modules`、`.venv`、`__pycache__`、缓存或构建目录中放置 Markdown 文件。
- 预期结果：这些目录内的 Markdown 不进入产物列表，避免依赖和缓存噪音。
- 关联需求点：产物列表应聚焦项目产物，不淹没用户。

### CHK-010 空状态
- 验证方法：绑定一个没有 Markdown 文件的有效工作区并打开产物视图。
- 预期结果：展示清楚的空状态，说明当前项目没有 Markdown 产物；不报错。
- 关联需求点：用户能理解当前项目无可查看 Markdown 产物。

### CHK-011 工作区失效状态
- 验证方法：项目绑定后删除或移动工作区，再打开产物视图。
- 预期结果：展示可操作错误，说明工作区不可访问；不会暴露无关目录内容。
- 关联需求点：工作区无效时安全失败。

### CHK-012 路径安全
- 验证方法：通过产物读取入口请求 `../`、绝对路径、符号链接逃逸路径或编码后的穿越路径。
- 预期结果：请求被拒绝；无法读取项目工作区外的文件。
- 关联需求点：不得成为任意文件浏览器；路径安全。

### CHK-013 Markdown 渲染预览
- 验证方法：打开包含标题、列表、代码块、链接和表格的 Markdown 文件。
- 预期结果：预览模式可读，主要 Markdown 结构正确呈现，布局不与周边 UI 重叠。
- 关联需求点：支持查看 Markdown 文件的渲染内容。

### CHK-014 Markdown 原文查看
- 验证方法：在同一 Markdown 文件中切换到原文模式。
- 预期结果：显示原始 Markdown 文本，保留换行和代码块内容；用户可与预览模式来回切换。
- 关联需求点：支持预览和原文两种查看方式。

### CHK-015 Markdown 内容安全
- 验证方法：打开包含内嵌 HTML、脚本标签、事件属性或可疑链接的 Markdown 文件。
- 预期结果：预览不会执行脚本或危险 HTML；原文模式按文本展示。
- 关联需求点：查看产物不引入脚本执行风险。

### CHK-016 大文件截断
- 验证方法：创建超过读取上限的大型 Markdown 文件并打开。
- 预期结果：页面保持可用；内容有明确截断提示；不会卡死浏览器或服务端。
- 关联需求点：容量限制和可用性。

### CHK-017 来源任务记录
- 验证方法：构造任务 evidence 中包含某个 Markdown 文件路径，再打开产物列表。
- 预期结果：该文件显示来源任务标题、taskId、attemptId 和证据时间；用户可以判断它来自项目中的哪个任务。
- 关联需求点：产物必须展示可追溯来源任务。

### CHK-018 来源 Agent 记录
- 验证方法：构造 OpenClaw、Hermes 或 Codex 执行证据中包含 Markdown 文件路径，并打开产物列表。
- 预期结果：匹配产物显示生成或修改它的 executor agentId 和 providerKind；Reviewer 不被误标为产物生成者。
- 关联需求点：产物必须展示哪个 Agent 生成或修改。

### CHK-019 未关联产物标记
- 验证方法：在工作区中放置没有出现在任何 Phase 7 task evidence 中的 Markdown 文件。
- 预期结果：该文件仍可作为项目 Markdown 产物查看，但来源显示为未关联，不猜测任务或 Agent。
- 关联需求点：来源信息必须基于执行证据；无法匹配时明确未关联。

### CHK-020 来源匹配准确性
- 验证方法：创建两个任务，分别在 evidence 中记录不同 Markdown 文件；再创建一个同名但不同目录的 Markdown 文件。
- 预期结果：来源匹配按相对路径精确匹配，不把同名文件、目录前缀相似文件或其他任务误关联。
- 关联需求点：用户需要判断产物属于哪个任务，不能误导归属。

### CHK-021 来源记录刷新
- 验证方法：同一 Markdown 文件先后被两个不同任务 evidence 记录，再刷新产物视图。
- 预期结果：产物能展示最近或全部可用来源记录；至少不会丢失最新任务、Agent、Provider 和 attempt 信息。
- 关联需求点：产物来源需要反映项目执行历史。

### CHK-022 只读行为
- 验证方法：在产物管理中查看多个 Markdown 文件，并检查项目数据和工作区文件状态。
- 预期结果：查看产物不会修改项目、任务、Markdown 文件或执行状态。
- 关联需求点：本期只读，不做编辑或管理操作。

### CHK-023 Project Execution 回归
- 验证方法：在加入产物管理后，执行 Project Execution 的启动、执行完成、审查、返工、用户验收流程的现有自动化回归。
- 预期结果：原有 Phase 7 执行/审查/验收状态流不受影响。
- 关联需求点：不破坏现有 Phase 7 核心流程。

### CHK-024 项目 CRUD 与报告回归
- 验证方法：执行项目创建、编辑、任务创建、任务更新、报告查看和模板相关回归。
- 预期结果：现有项目管理能力正常工作。
- 关联需求点：新增产物管理不破坏项目管理基础能力。

### CHK-025 浏览器人工验收
- 验证方法：在浏览器中创建或打开一个真实 Project Execution 项目，准备至少两个 Markdown 产物，进入产物管理并查看预览和原文。
- 预期结果：用户可以自然完成“进入产物列表 -> 查看来源任务/Agent -> 打开 md -> 预览 -> 原文 -> 返回项目”的核心流程。
- 关联需求点：第一版成功标准。

## 变更记录

- 2026-06-11T05:25:57+08:00：checklist 已确认后发生方案变更，新增“通用产物管理组件/核心能力”要求。原 checklist 确认失效，需重新确认后再生成新的 todolist。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-11T05:37:14+08:00
- 用户确认摘要：用户回复 “pass”，确认包含通用产物核心、通用 UI 组件、Phase 7 项目适配层和未来会议复用约束的新版 checklist。

- 确认项：checklist
- 确认时间：2026-06-11T05:23:29+08:00
- 用户确认摘要：用户确认可以生成 todolist，表示当时 checklist 草稿可作为执行依据。该确认已被 2026-06-11T05:25:57+08:00 的通用组件化方案变更取代，需重新确认新版 checklist。

## 实现与自动化记录

- 记录时间：2026-06-15T03:59:01+08:00
- 开发状态：实现完成，等待浏览器人工验收和用户测试确认。
- 已实现：通用 Markdown artifact 核心、Project Execution project adapter、项目级 list/read API、Project Manager 产物入口、Artifact Manager list/viewer、Preview/Source 切换、只读安全读取、来源记录展示和未关联标记。
- 已覆盖：CHK-001、CHK-003、CHK-006 至 CHK-012、CHK-016 至 CHK-024 的主要后端与静态路径；CHK-002、CHK-013 至 CHK-015、CHK-025 仍需浏览器人工验收确认视觉与交互。
- 自动化通过：`.venv/bin/python tests/test_project_execution.py`、`node --check app/projects.js`、`git diff --check`。
- 测试备注：`tests/test_project_execution.py` 输出了一条 gateway session abort 权限警告，但脚本最终退出 `ok`，不影响本次 artifact 管理断言结果。
- 待完成：在浏览器中完成“进入产物列表 -> 查看来源任务/Agent -> 打开 md -> 预览 -> 原文 -> 返回项目”的 CHK-025 验收；通过后仍需用户确认才能推进 `confirmed.tested`。

- 沙箱外 HTTP 验收时间：2026-06-15T04:05:35+08:00
- 沙箱外环境：`./start.sh` 启动 `http://127.0.0.1:8090` 成功；`/api/license` 返回 DEV 且 `demo:false`。
- 沙箱外已通过：真实 HTTP API 创建 Project Execution 项目并绑定 `/tmp/vo-artifact-acceptance-*` 工作区；`/api/projects/<id>/artifacts` 只列出 `docs/accepted.md`，未列出 `node_modules/pkg/README.md` 和 `docs/data.json`；Markdown read 返回原文；非 Markdown read 返回 HTTP 415；路径穿越 read 返回 HTTP 400；非 Project Execution 项目 artifact 入口返回 HTTP 409。
- 浏览器验收阻塞：`/browser-status` 返回 `{"enabled": false, "cdpAvailable": false, ...}`，共享 Kasm 浏览器不可用。按 VO browser-control 规则，未使用本地 Chrome、Playwright 或其他 CDP 替代，因此 CHK-025 仍待浏览器人工验收。

- Chrome MCP 补充端到端验证时间：2026-06-15T04:07:06+08:00
- Chrome MCP 验证结果：按用户要求调用 Chrome MCP 完成补充浏览器 E2E。打开 `http://127.0.0.1:8090` 后进入 Project Manager，打开 `Artifact API Acceptance` 项目，确认项目详情有 `产物` 入口和绑定工作区路径；进入产物页后看到 `Markdown 产物` 列表、`docs/accepted.md`、大小、修改时间和 `未关联到来源记录`；点击 artifact 后 Preview 显示 `# Accepted Artifact`、列表项和 code 内容；切换 Source 后显示原始 Markdown；点击返回后回到项目看板。
- Chrome MCP 网络证据：`GET /api/projects/516f2e2d-8b9b-44c7-9fff-7b03460dbd78/artifacts` 返回 200，`GET /api/projects/516f2e2d-8b9b-44c7-9fff-7b03460dbd78/artifacts/read?path=docs%2Faccepted.md` 返回 200。
- Chrome MCP 控制台结果：没有 artifact 工作流相关错误；仅有既有/通用警告（pointer-lock、CSS import 顺序、表单 label/id）和 perf log。
- 确认状态：补充 E2E 已通过，但 `confirmed.tested` 仍等待用户明确确认后再推进。

- 真实场景自动化补充时间：2026-06-15T04:12:48+08:00
- 新增用例：`test_project_artifacts_real_acceptance_review_scenario`。
- 场景内容：一个 Project Execution 工作区包含 agent 生成的 `requirements/acceptance.md` 验收记录、返工后的 `docs/handoff.markdown` 交接文档、手工创建且无执行证据的 `docs/manual.md`、依赖目录 `node_modules/pkg/README.md` 和非 Markdown 报告 `reports/raw-result.json`。
- 验证点：只列出项目 Markdown 产物；排除依赖 README 和非 Markdown 报告；`acceptance.md` 显示执行任务标题、executor agent、provider kind、attempt ID 和 evidence time；Reviewer 结果不会被误标为产物生成者；返工交接文档显示 Codex executor 来源；手工文档显示未关联；读取 Markdown 原文保留可疑 HTML 文本但不执行。
- 回归结果：`.venv/bin/python tests/test_project_execution.py`、`node --check app/projects.js`、`git diff --check` 均通过；Project Execution 测试仍有既有非致命 gateway abort 权限警告，最终输出 `ok`。

- 真实 AI 产物验收时间：2026-06-15T05:06:05+08:00
- 真实 AI 执行环境：本地服务 `http://127.0.0.1:8090`，Project Execution 项目 `Real AI Artifact Acceptance`，workspace `/tmp/vo-real-ai-artifact-vCPQGD`，executor `codex-local`。
- 真实 AI 执行结果：任务 `Generate Markdown artifact with real AI` 启动 attempt `0fc0e054-85a4-4df7-9d20-c3604d547c48`，最终状态 `execution_complete`；Codex 实际生成 `ai-output/real-ai-artifact.md`，内容包含验收短语 `REAL_AI_ARTIFACT_OK`，并保留原始 `seed.md`。
- 真实 AI 发现的问题：Codex evidence 的 `changedFiles` 使用绝对路径，初版 source 匹配只按相对路径处理，导致真实 AI 生成的 Markdown 一开始被标记为未关联；此外 task-level 和 attempt-level 相同 evidence 会产生重复 source records。
- 修复结果：`app/server.py` 已把工作区内绝对路径规范化为相对路径，并对相同 task/attempt/agent/provider/time 的 source record 去重；`tests/test_project_execution.py` 增加绝对路径 evidence 场景和去重断言。
- 复验结果：重启本地服务后，`GET /api/projects/890735db-445e-4f2e-8bca-60a8fa3e9d22/artifacts` 返回 `ai-output/real-ai-artifact.md`，`unassociated:false`，且仅有 1 条 source record：`agentId=codex-local`、`providerKind=codex`、`attemptId=0fc0e054-85a4-4df7-9d20-c3604d547c48`。
- 回归结果：`.venv/bin/python tests/test_project_execution.py`、`node --check app/projects.js`、`git diff --check` 均通过；Project Execution 测试仍有既有非致命 gateway abort 权限警告，最终输出 `ok`。

- 沙箱外权限警告复验时间：2026-06-15T05:09:44+08:00
- 沙箱外复验命令：`.venv/bin/python tests/test_project_execution.py`。
- 沙箱外复验结果：脚本退出 `ok`。此前沙箱内的 `[Errno 1] Operation not permitted` gateway abort 警告消失；剩余非致命警告为 `Connect call failed ('127.0.0.1', 18789)`，表示当前测试环境没有 gateway session 服务监听该端口，不是 artifact management 功能断言失败。

- 空产物入口补充时间：2026-06-15T05:18:00+08:00
- 产品约束：Project Execution 项目绑定有效工作区但尚未生成 Markdown 产物时，可以仍然展示 `产物` 按钮；点击后应进入产物页并显示空 Markdown 列表，不应把“暂无产物”当作错误，也不应仅因没有产物而隐藏入口。
- 实现确认：当前前端 `产物` 按钮按 `projectExecutionEnabled` 展示，不按 artifact 数量展示；Artifact Manager 已有空状态 `当前上下文没有 Markdown 产物。`。
- 自动化补充：`tests/test_project_execution.py` 已增加项目级空 workspace 验证，确认 Project Execution 项目无 Markdown 时 `/artifacts` 返回 `ok:true`、`artifacts: []`、`truncated:false`。
- 回归结果：`.venv/bin/python tests/test_project_execution.py` 与 `node --check app/projects.js` 均通过；测试环境仍有非致命 gateway abort 连接失败警告，最终输出 `ok`。

- 人工验收确认时间：2026-06-17T03:01:16+08:00
- 确认项：tested
- 用户确认摘要：用户确认验收通过，可以归档。

- 人工归档确认时间：2026-06-17T03:01:16+08:00
- 确认项：done
- 用户确认摘要：用户确认验收通过，并请求将该需求归档为完成。
