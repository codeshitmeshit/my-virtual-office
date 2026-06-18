# 项目定时任务 Phase 2-3 Todolist

## TODO-001 梳理现有项目 UI、Cron UI 和执行入口

- 目标：在编码前确认项目详情页、全局 `/cron.html`、项目 workflow 和任务执行 API 的现有结构。
- 涉及区域：`app/projects.js`、`app/projects.css`、`app/cron.html`、`app/server.py`、现有 project execution 测试。
- 输入：Phase 1 API、现有项目详情数据结构、现有 cron UI 数据结构。
- 输出：实现用到的函数、状态字段和调用路径清单。
- 依赖：Phase 1 已完成。
- 完成标准：明确项目页插入点、全局页合并渲染策略、派发调用路径和必要状态字段。
- 关联 checklist：CHK-001 至 CHK-017。

## TODO-002 新增项目定时任务聚合/详情 API 能力

- 目标：让全局页面可以一次性获取项目绑定 cron 及项目上下文，避免前端逐项目低效加载。
- 涉及区域：`app/server.py`、Phase 1 project scheduled cron helpers。
- 输入：`project-cron-bindings.json`、项目列表、任务列表、gateway `cron.list` 返回结果。
- 输出：可供 `/cron.html` 使用的聚合接口或等价后端能力。
- 依赖：TODO-001。
- 完成标准：返回项目 cron、项目名、目标类型、目标任务名、enabled、schedule、last/next 状态；项目缺失或任务缺失时仍能安全返回状态。
- 关联 checklist：CHK-007、CHK-008、CHK-009、CHK-014、CHK-015。

## TODO-003 在项目详情页增加定时任务配置区

- 目标：用户能在项目上下文内创建、查看、编辑、启用/禁用、删除、立即运行项目定时任务。
- 涉及区域：`app/projects.js`、`app/projects.css`、必要的 locale 文案。
- 输入：Phase 1 项目定时任务 API、当前项目任务列表。
- 输出：项目详情页的项目定时任务 UI。
- 依赖：TODO-001、TODO-002 的接口形态。
- 完成标准：支持 whole-project 和 project-task 两种目标；project-task 只能选择当前项目任务；操作成功后 UI 与后端一致；错误提示清楚。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-006。

## TODO-004 增加项目级暂停/恢复能力

- 目标：支持用户暂停或恢复某个项目的全部项目定时任务。
- 涉及区域：`app/server.py`、`app/projects.js`、项目持久化字段或等价状态文件。
- 输入：项目 ID、现有项目数据、项目绑定 cron 列表。
- 输出：项目级 scheduled cron pause/resume 状态及 UI 控件。
- 依赖：TODO-001、TODO-003。
- 完成标准：暂停状态可保存；暂停时项目页和全局页可见；暂停不删除配置；恢复后允许后续派发。
- 关联 checklist：CHK-005、CHK-013。

## TODO-005 改造全局 `/cron.html` 总览项目绑定 cron

- 目标：全局定时任务页同时展示普通 Agent cron 和项目绑定 cron。
- 涉及区域：`app/cron.html`、必要的 CSS/JS 内联逻辑、后端聚合接口。
- 输入：普通 `cron.list` 数据、项目 cron 聚合数据。
- 输出：合并后的 cron 列表、类型标识和项目上下文展示。
- 依赖：TODO-002。
- 完成标准：项目 cron 在全局页可见；能区分 Agent cron 和 Project cron；显示项目名、目标类型、目标任务；普通 Agent cron 原有操作保持可用。
- 关联 checklist：CHK-007、CHK-008、CHK-016。

## TODO-006 为 `/cron.html` 增加类型和项目过滤

- 目标：用户可以按全部、Agent cron、Project cron 和指定项目过滤全局 cron。
- 涉及区域：`app/cron.html`。
- 输入：合并后的 cron 列表、项目列表或项目 cron 聚合数据。
- 输出：过滤控件与过滤后的列表渲染。
- 依赖：TODO-005。
- 完成标准：过滤结果准确；切换过滤不破坏原有 Agent cron 筛选或操作；空状态文案清晰。
- 关联 checklist：CHK-009、CHK-016。

## TODO-007 实现项目绑定 cron 派发协调器

- 目标：当项目绑定 cron 到期或被 run-now 时，派发到项目 workflow 或指定项目任务。
- 涉及区域：`app/server.py`、现有 project execution/workflow handlers。
- 输入：项目绑定 cron、gateway cron 状态、项目和任务状态。
- 输出：projectWorkflow 和 projectTask 两条派发路径。
- 依赖：TODO-001、TODO-002、TODO-004。
- 完成标准：whole-project 在空闲时启动 workflow；workflow 已运行时跳过；project-task 启动指定任务执行；普通 Agent cron 不受影响。
- 关联 checklist：CHK-010、CHK-011、CHK-012、CHK-016。

## TODO-008 增加派发保护和状态更新

- 目标：确保暂停、删除、归档、任务缺失和不满足条件时不会错误派发，并维护基础运行状态。
- 涉及区域：`app/server.py`、项目 cron 绑定状态文件。
- 输入：项目状态、任务状态、派发结果。
- 输出：`lastRunAt`、`lastStatus`、`lastError`、`nextRunAt` 或等价字段。
- 依赖：TODO-007。
- 完成标准：started、skipped、failed、paused、missing-target 等状态可区分；后端不崩溃；UI 可读取基础状态。
- 关联 checklist：CHK-013、CHK-014、CHK-015。

## TODO-009 补充自动化测试

- 目标：用自动化测试覆盖 Phase 2+3 的后端核心行为和回归点。
- 涉及区域：`tests/`、`app/server.py`。
- 输入：新增/调整后的 API、派发协调器、项目状态。
- 输出：新增测试文件或扩展现有项目定时任务测试。
- 依赖：TODO-002、TODO-004、TODO-007、TODO-008。
- 完成标准：测试覆盖创建/查询聚合、暂停、whole-project 派发、运行中跳过、project-task 派发、缺失目标保护、普通 Agent cron 回归。
- 关联 checklist：CHK-005、CHK-010 至 CHK-017。

## TODO-010 执行回归测试和 8090 live 验收

- 目标：确认 Phase 2+3 在真实启动服务下可验收。
- 涉及区域：本地测试命令、8090 服务、浏览器或 HTTP live 检查。
- 输入：已完成实现和测试。
- 输出：测试结果记录、live 验收结论。
- 依赖：TODO-003 至 TODO-009。
- 完成标准：新增测试通过；现有 cron/websocket/project 相关测试通过；8090 live 复测能看到项目页创建、全局页可见/过滤、项目派发主链路。
- 关联 checklist：CHK-017。

## TODO-011 更新需求状态和交付说明

- 目标：把 Phase 2+3 的实现、测试结果和剩余风险写回需求归档。
- 涉及区域：本目录 `checklist.md`、`status.json`、父需求相关文档。
- 输入：测试结果、live 验收结果、实现范围。
- 输出：需求状态更新和交付说明。
- 依赖：TODO-010。
- 完成标准：checklist 标注测试结果；`status.json` 推进到合适阶段；如发现 Phase 4/5 遗留项，同步记录。
- 关联 checklist：CHK-017。
