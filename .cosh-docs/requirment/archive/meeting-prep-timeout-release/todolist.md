# 实施 Todolist

## TODO-001 梳理会议生命周期与配置接入点

- 目标：确认准备态超时应接入的后端函数、配置保存位置和前端设置入口。
- 涉及区域：`app/server.py`、`app/index.html`、`app/game.js`、`app/locales/en.json`、`app/locales/zh.json`、现有会议测试。
- 输入：已确认 requirement、review、checklist，现有 `preparing` 会议创建和 transition 逻辑。
- 输出：实现前的代码定位结论，明确配置键名和默认值。
- 依赖：无。
- 完成标准：确认使用 `meetings.preparingTimeoutSec` 或等价稳定配置键；默认值为 300 秒；实现范围不碰无关会议流程。
- 关联 checklist：CHK-001、CHK-002、CHK-012、CHK-013。

## TODO-002 增加后端配置读取和校验

- 目标：提供准备态超时秒数的统一读取函数。
- 涉及区域：`app/server.py` 配置读取、`VO_CONFIG` 或 `vo-config.json` 合并逻辑。
- 输入：配置值 `meetings.preparingTimeoutSec`，默认值 300。
- 输出：例如 `_meeting_preparing_timeout_sec()` 的 helper，包含最小值、最大值和非法值兜底。
- 依赖：TODO-001。
- 完成标准：无配置时返回 300；合法配置按配置返回；非法值不会抛异常；边界值按约定夹取或回退。
- 关联 checklist：CHK-001、CHK-002、CHK-003。

## TODO-003 记录准备态计时基准

- 目标：为进入 `preparing` 的会议记录稳定计时起点。
- 涉及区域：会议创建、冲突解决、恢复到 preparing 的 transition。
- 输入：会议创建时间、阶段转换事件。
- 输出：`preparingStartedAt` 或等价字段；旧数据缺字段时回退 `createdAt`。
- 依赖：TODO-001。
- 完成标准：无冲突新会议创建时有准备起点；冲突解决进入准备态时重新计时；从暂停恢复到准备态时重新计时；旧会议兼容。
- 关联 checklist：CHK-004、CHK-005、CHK-008、CHK-013。

## TODO-004 实现准备态超时释放服务

- 目标：识别并释放超过配置时长的 `preparing` 可执行会议。
- 涉及区域：`app/server.py` executable meeting store、occupancy、事件追加。
- 输入：会议 store、当前时间、配置秒数。
- 输出：幂等 helper，例如 `_release_timed_out_preparing_meetings(store, now=None)`。
- 依赖：TODO-002、TODO-003。
- 完成标准：仅处理 `stage == "preparing"` 的非终态会议；超时会议转为 `cancelled` 或约定释放终态；记录 `cancelReason = "preparing_timeout"`、超时时间和配置秒数；释放对应 occupancy；重复执行不重复污染事件。
- 关联 checklist：CHK-004、CHK-005、CHK-007、CHK-009、CHK-010。

## TODO-005 接入惰性清理入口和启动前防竞态

- 目标：确保用户查看、刷新、reconcile 或启动会议时都能触发超时释放。
- 涉及区域：`_meeting_active_projection`、`_handle_executable_meeting_detail`、`_handle_executable_meeting_reconcile`、`_handle_executable_meeting_run`。
- 输入：TODO-004 helper。
- 输出：各入口在返回或执行前完成超时清理，并保存 store。
- 依赖：TODO-004。
- 完成标准：活动列表不再返回已超时准备态会议；详情能反映超时释放状态；reconcile 能清理遗留占用；run/start 无法启动已超时会议。
- 关联 checklist：CHK-004、CHK-006、CHK-009、CHK-010。

## TODO-006 增加设置页控件和保存逻辑

- 目标：让用户在设置中配置准备态释放时间，单位秒。
- 涉及区域：`app/index.html` 设置表单、`app/game.js` 配置加载与保存、可能的 `/vo-config` 保存 API。
- 输入：后端配置键、默认值 300。
- 输出：设置项输入框、加载默认值、保存配置、刷新后回显。
- 依赖：TODO-002。
- 完成标准：设置页有清晰秒级文案；保存合法值后持久化；刷新后回显；非法值有前端约束或后端兜底。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-011。

## TODO-007 增加会议列表和详情展示

- 目标：让用户理解准备态剩余时间和超时释放原因。
- 涉及区域：`app/game.js` 会议列表/详情渲染、`app/locales/en.json`、`app/locales/zh.json`。
- 输入：后端返回的准备起点、配置秒数、释放原因字段或事件。
- 输出：准备态倒计时或剩余时间提示；超时释放状态文案；中英文 i18n。
- 依赖：TODO-003、TODO-004、TODO-006。
- 完成标准：准备态会议展示清晰；超时释放后显示“准备超时已释放”或等价文案；不会造成 UI 文本溢出或覆盖。
- 关联 checklist：CHK-010、CHK-011、CHK-014。

## TODO-008 增加后端自动化测试

- 目标：稳定验证默认值、配置值、超时释放、非超时保留、非准备态不释放和 occupancy 精确释放。
- 涉及区域：`tests/test_meeting_for_ai_phase*.py` 或新增聚焦测试文件。
- 输入：可构造的 meeting store 和配置环境。
- 输出：确定性 Python 测试，不依赖真实等待。
- 依赖：TODO-002、TODO-003、TODO-004、TODO-005。
- 完成标准：覆盖默认 300 秒、配置 120 秒、非法配置、超时准备态释放、未超时保留、active/paused/conflict 不释放、只删除当前会议 occupancy。
- 关联 checklist：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005、CHK-007、CHK-009、CHK-013。

## TODO-009 增加前端与 i18n 校验

- 目标：验证设置项和文案不会破坏前端资源。
- 涉及区域：`tests/test_i18n_integrity.js`、`node --check app/game.js`、必要时补充前端测试。
- 输入：新增 i18n key、设置加载保存代码。
- 输出：语法和 i18n 完整性验证。
- 依赖：TODO-006、TODO-007。
- 完成标准：`app/game.js` 语法通过；中英文 JSON 可解析且 key 完整；设置页 DOM 人工检查无明显布局问题。
- 关联 checklist：CHK-011、CHK-013。

## TODO-010 执行回归测试

- 目标：确认新增准备态释放不会破坏 Meeting for AI 既有功能。
- 涉及区域：会议 Phase 1/4/5/6 测试、项目执行相关测试、i18n 测试。
- 输入：完成后的代码。
- 输出：测试命令结果和失败修复记录。
- 依赖：TODO-008、TODO-009。
- 完成标准：至少运行 `node --check app/game.js`、locale JSON 解析、`python -m py_compile app/server.py`、会议相关 Python 测试；如有既有环境问题需记录。
- 关联 checklist：CHK-012、CHK-013。

## TODO-011 浏览器人工验收

- 目标：用真实页面验证端到端体验。
- 涉及区域：本地服务、设置页、会议中心、Agent 状态/占用展示。
- 输入：可运行本地服务，测试会议，较短安全超时值例如 30 秒。
- 输出：人工验收记录。
- 依赖：TODO-006、TODO-007、TODO-010。
- 完成标准：设置 30 秒后创建会议不启动，超时后自动释放；Agent 可再次用于新会议；会议列表/详情文案清晰。
- 关联 checklist：CHK-014。

## TODO-012 更新归档状态和交付说明

- 目标：开发完成后把测试结果回写 checklist，并等待用户测试确认。
- 涉及区域：`.cosh-docs/requirment/meeting-prep-timeout-release/checklist.md`、`status.json`、最终交付说明。
- 输入：实现记录、测试结果、人工验收结果。
- 输出：checklist 测试记录、阶段推进到 `implementation_done` 或 `tested` 前的确认材料。
- 依赖：TODO-010、TODO-011。
- 完成标准：每个 CHK 项有结果或说明；等待用户确认测试通过；不越过用户确认直接标记 done。
- 关联 checklist：CHK-001 至 CHK-014。
