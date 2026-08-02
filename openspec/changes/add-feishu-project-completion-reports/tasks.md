<!-- cosh-dashboard-control {"mode":"continuous","sequence":1,"mode_updated_at":"2026-08-03T01:22:26+08:00"} -->

## 1. 项目偏好模型与锁定规则

- [x] 1.1 [MP-1] 在 `app/services/project_materialization.py` 的 `CANONICAL_PROJECT_BASE_FIELDS` 与 `materialize_project_base` 中加入 `feishuCompletionReportEnabled: bool`，缺省为 `True`，并扩展 `tests/test_project_materialization.py` 覆盖缺省开启、显式关闭以及 canonical exact-field contract；验证：运行该测试文件；提交：`feat(projects): add completion report preference default`。
- [x] 1.2 [MP-1][MP-2] 在 `app/project_store.py` 的 `_write_project`/`_read_project_dir` 持久化该 scalar，历史项目缺失时读取为 `True`；在 `app/services/project_commands.py::update_project` 增加字段白名单和基于 `orchestration.completedAt` 的锁定校验，返回 `feishu_completion_report_preference_locked`；新增或扩展 command/store 测试覆盖首次完成前修改、完成后拒绝、相同值幂等和旧数据兼容；提交：`feat(projects): persist and lock report preference`。
- [x] 1.3 [MP-2] 在 `app/projects.js::showFormModal`、`submitNewProject`、`submitEditProject` 增加默认勾选的“项目完成后发送飞书汇报”控件与请求字段，完成后显示锁定态；扩展现有前端静态/浏览器测试，验证创建默认值、编辑 payload、完成后禁用及服务端错误展示；提交：`feat(projects-ui): expose completion report preference`。

## 2. 完成 occurrence 与版本化 outbox

- [x] 2.1 [MP-3] 新建 `app/services/project_completion_reporting.py`，实现纯状态函数 `stage_completion_report_occurrence`：以 `stage-run:<run_id>` 为 `occurrenceId`，维护递增 `version`、`state`、`visibleStatus`、claim/attempt 元数据，并在关闭偏好时不创建 intent；新建 `tests/test_project_completion_reporting.py` 覆盖同 run 幂等、新 run 新版本、关闭跳过、完成锁定和输入异常；提交：`feat(reporting): model completion report occurrences`。
- [x] 2.2 [MP-3] 在 `app/services/project_stage_dispatch.py::reconcile_stage` 的最终完成事务内调用 occurrence staging，并将事务后 callback 缩减为 worker wakeup；更新持久化 helper，使 pending occurrence 随项目状态可靠保存；扩展 `tests/test_project_stage_dispatch.py` 覆盖正常完成、skip、recovery、重复 reconcile、callback 异常和项目完成不回滚；提交：`feat(reporting): stage outbox with project completion`。
- [x] 2.3 [MP-3] 新建 `app/services/project_completion_report_storage.py`，安全、原子写入 `.vo/project-completion-reports/v<version>-<occurrence>/FEISHU_COMPLETION_REPORT.md`，保存相对路径与 SHA-256，不覆盖历史版本；新建聚焦测试覆盖路径穿越、缺失 workspace、重复写入、不同版本和 digest；提交：`feat(reporting): persist versioned report sidecars`。

## 3. 最终产物安全收集

- [x] 3.1 [MP-4] 新建 `app/services/project_completion_report_artifacts.py`，只枚举 `task.finalResult.markdownPath`、`task.finalResult.artifactRefs` 和当前项目 `finalReport.markdownPath`，稳定去重并通过注入的 `read_artifact(..., allow_text=True, associated_only=True)` 读取；限制 20 个引用、单文件 512 KiB、总文本 512 KiB，并为缺失/不支持/超限项生成 omission；提交：`feat(reporting): collect final project artifacts safely`。
- [ ] 3.2 [MP-4] 在同一聚焦模块加入敏感 basename denylist 与 Agent 前 scrubber，覆盖 authorization、API key、token、password、secret、webhook 和私钥块；新建 `tests/test_project_completion_report_artifacts.py`，直接观察 collector/Agent-port 边界，证明日志、evidence、changedFiles、越界路径、符号链接、敏感文件和未脱敏正文不会进入 Agent；提交：`security(reporting): enforce final artifact data boundary`。

## 4. Agent 报告生成

- [ ] 4.1 [MP-4] 新建 `app/services/project_completion_report_prompt.py`，只通过 `services.bridge_input_output_formatting` 生成 XML 外层 prompt，使用 `<role>`、`<task>`、`<rules>`、`<context>`、`<final_artifacts>` 和最终 `<output>`，动态项目/产物数据全部使用不可信文本或 JSON boundary；新建 prompt 测试覆盖 XML 闭合注入、特殊字符、超长输入和稳定 JSON output schema；提交：`feat(reporting): add secure XML report prompt`。
- [ ] 4.2 [MP-4][MP-5] 新建 `app/services/project_completion_report_generation.py`，通过注入 provider port 调用 `VO_CONFIG.feishu.chatApp.representativeAgentId` 对应 Agent，严格解析 `goal/conclusion/keyResults/nonFatalExceptions/followUps/importantArtifacts`，限制字段长度与数量，并确定性渲染带项目、版本、run marker 的 Markdown；新建测试覆盖成功、Agent 缺失、busy/timeout、空回复、非法 JSON、额外内部字段和 schema 截断；提交：`feat(reporting): generate structured human-readable reports`。

## 5. 通知机器人投递与恢复

- [ ] 5.1 [MP-5] 在 `app/feishu_notifications.py::send_feishu_notification` 增加默认兼容的 `allow_webhook=True` 参数；新建 `app/services/project_completion_report_delivery.py`，强制校验 notification app 的 appId/appSecret/receiveIdType/receiveId，调用时设置 `allow_webhook=False`，把结构化报告映射到现有卡片长度边界且不接受 recipient 覆盖；扩展飞书通知测试覆盖 app 定向发送、缺配置失败、禁止 webhook fallback、chat bot 未调用和其他通知兼容；提交：`feat(reporting): deliver through notification app only`。
- [ ] 5.2 [MP-3][MP-5] 在 `project_completion_reporting.py` 完成原子 claim/finish/fail/manual-resend 状态转换：内部状态映射为 pending/delivered/failed，claim token 与 expiry 防并发，attempt history 每 occurrence 保留 20 条；实现每周期最多 3 次及 0/30/120 秒退避，并把 stale delivering/发送结果未知标记为 `delivery_outcome_unknown` 而非自动重试；扩展状态机测试覆盖竞争 claim、确定失败、未知结果、重试耗尽和同版本手动重发；提交：`feat(reporting): add bounded delivery state machine`。
- [ ] 5.3 [MP-5] 新建 `app/services/project_completion_report_worker.py`，使用 `services.periodic_timer.PeriodicTimer` 每 15 秒扫描、每批最多 claim 10 条，串联 artifact collector、generation、storage 与 delivery ports；测试立即扫描、due filter、批量上限、进程重启恢复、单条异常隔离和 stop 行为；提交：`feat(reporting): add persistent completion report worker`。

## 6. 服务装配、API 与项目页面

- [ ] 6.1 [MP-3][MP-5] 在新的聚焦 wiring/factory 模块中组装 worker ports，并在 `app/server.py` 仅增加薄依赖注入、完成 callback wakeup、启动和停止注册；移除或薄委托旧 `_send_project_execution_project_complete_notification` 的成功完成卡片路径，保留失败/取消通知；扩展 server wiring 测试验证 normal/skip/recovery 共用新入口且 chat bot transport 不参与；提交：`feat(reporting): wire completion report runtime`。
- [ ] 6.2 [MP-5] 新建聚焦的 completion-report query/resend service 与 handler，向 `GET /api/projects/{id}/report` 增加清理后的逐版本状态，并提供 `POST /api/projects/{projectId}/completion-reports/{occurrenceId}/resend`；只允许 failed occurrence、拒绝请求体覆盖 Agent/版本/内容/recipient，返回稳定 404/409 错误码；新增 API 测试覆盖列表清理、pending/delivered/failed、owner access boundary、并发处理中和同版本重发；提交：`feat(reporting): expose report status and resend API`。
- [ ] 6.3 [MP-5] 扩展 `app/projects.js::renderReportView`，按版本倒序展示 pending/delivered/failed、完成/送达时间、可读错误和仅失败态可见的“重新发送”按钮；调用 resend API 后刷新状态并防重复点击；扩展前端测试覆盖三种状态、多个版本、错误转义、按钮条件和重发交互；提交：`feat(projects-ui): show Feishu report delivery status`。

## 7. 集成验证与交付

- [ ] 7.1 [MP-1..MP-5] 运行新增聚焦测试以及受影响的 `test_project_materialization.py`、project command/store、`test_project_stage_dispatch.py`、`test_feishu_notifications.py`、periodic timer 和项目 API/UI 测试；修复仅由本变更引入的回归，记录命令、通过数与任何环境限制；提交：`test(reporting): verify completion report integration`（仅在确有测试修正或新夹具时提交）。
- [ ] 7.2 [MP-1..MP-5] 使用 fake Agent 和 fake notification app 完成端到端场景：默认开启成功送达、显式关闭不建 intent、失败项目仍走原 VO 通知、同 run 不重复、成功重跑生成 v2、敏感产物不进入 Agent、自动重试耗尽、手动重发成功、项目状态始终 completed；保存可复现测试证据并运行 `openspec validate add-feishu-project-completion-reports`；提交：`test(reporting): add end-to-end completion report coverage`。
