# 变量级修改点分析

## 分析基线

- 仓库：`/Users/bytedance/cosh/my-virtual-office`
- Git 基线：`f0b7f3e646a1a4e64b350d447d6e18fa15362065`
- CodeGraph：仓库存在 `.codegraph/`，但当前环境既没有 `codegraph` 命令，也没有可调用的 CodeGraph MCP；以下结论由符号级源码读取、调用点检索和针对性测试交叉验证得到。
- OpenSpec 校验：`openspec validate add-feishu-project-completion-reports` 通过。
- 基线测试：5 passed。
  - `tests/test_project_materialization.py::test_materialize_project_base_supplies_complete_canonical_defaults`
  - `tests/test_project_orchestration_store.py::test_completed_reusable_project_writes_project_final_report_sidecar`
  - `tests/test_project_stage_dispatch.py` 中项目最终完成、完成通知去重、通知失败不回滚项目完成的 3 个用例。

## 修改点卡片

修改点 ID：MP-1

对应 scenario：项目未显式选择时默认开启；首次成功完成前允许修改；首次成功完成后拒绝修改；不同项目不继承个人默认值。
- 仓库/基线：本仓库 / `f0b7f3e646a1a4e64b350d447d6e18fa15362065`
文件：`app/services/project_materialization.py`
符号：`CANONICAL_PROJECT_BASE_FIELDS`（31-64），`materialize_project_base`（598-676）
变量：计划新增 `project["feishuCompletionReportEnabled"]: bool`；输入来自 `configuration: Mapping[str, Any]`，缺省值为 `True`。
类型：持久化数据模型 / 所有创建路径的统一默认值。
- 定义/写入：`materialize_project_base` 构造 `project: dict[str, Any]`；`CANONICAL_PROJECT_BASE_FIELDS` 固化完整基础字段集合。
- 读取来源：`project_commands.create_project`、浏览器模板创建、直接物化、模板物化均汇入该函数。
目标变化：把偏好建模为项目级布尔字段，所有创建入口都获得同一个默认开启语义，不增加个人默认配置。
- 影响面：创建 API 返回、Markdown frontmatter 持久化、项目编辑表单、规范化测试的精确字段集合。
- 测试锚点：扩展 `test_materialize_project_base_supplies_complete_canonical_defaults`，并覆盖显式 `false` 与各创建入口。
- 排除方案：不在各创建 handler 分别补默认值，避免入口间默认值漂移；不新增用户级配置。
未决假设：无。

修改点 ID：MP-2

对应 scenario：所有偏好修改场景；完成后仍展示锁定值。
- 仓库/基线：本仓库 / `f0b7f3e646a1a4e64b350d447d6e18fa15362065`
文件：`app/services/project_commands.py`；`app/projects.js`
符号：`update_project`（324-369）；`showFormModal`（3258 起）；`submitNewProject`（3787 起）；`submitEditProject`（3831 起）。
变量：后端 `mutable_body: dict`、`current_project: dict`、`fields: list[str]`；前端计划新增复选框值与创建/编辑请求 `body.feishuCompletionReportEnabled: boolean`。
类型：命令校验 / UI 与 API 请求契约。
- 定义/写入：`update_project.mutate` 当前按 `fields` 白名单直接覆写项目字段；前端两个 submit 函数组装请求体。
- 读取来源：完成锁定依据必须读取持久化的首次成功完成事实，优先使用不可逆的完成 occurrence/history，而不是可被重跑重置的当前 `status`。
目标变化：创建页默认勾选；首次成功前可编辑；首次成功后 UI 锁定且后端拒绝绕过 UI 的修改请求。拒绝应使用稳定错误码，且不改变原值。
- 影响面：项目创建/编辑弹窗、项目更新命令、活动记录、浏览器/API 测试。
- 测试锚点：`tests/test_project_commands.py`（或新聚焦测试文件）验证完成前更新、完成后 409/422 拒绝及未修改；浏览器测试验证默认勾选和锁定态。
- 排除方案：不能只在前端禁用控件；不能仅凭 `project.status == "completed"` 判断首次完成，因为重跑可能改变当前状态。
未决假设：现有接口没有可靠的“当前用户身份”，`createdBy` 也可能是 Agent ID；若产品是单用户部署，可把现有项目编辑权限视为 owner 权限，但这不等价于多用户鉴权。

修改点 ID：MP-3

对应 scenario：每个成功 completion occurrence 只产生一个 intent；成功重跑产生可区分的新版本；重复完成信号不重复投递。
- 仓库/基线：本仓库 / `f0b7f3e646a1a4e64b350d447d6e18fa15362065`
文件：`app/services/project_stage_dispatch.py`；`app/services/project_final_report.py`；`app/project_store.py`；计划新增 `app/services/project_completion_reporting.py`。
符号：`reconcile_stage`（1144-1481）、`_persist_project_completion_notification`（1484-1500）；`ensure_project_final_report`（15-38）；`ProjectStore._write_project_final_report`（618-630）；计划新增 `CompletionReportCoordinator.record_successful_completion(...)`。
变量：现有 `run_id: str`、`timestamp: str`、`state: dict[str, Any]`、`orchestration["finalReport"]: dict`；计划新增 `occurrence_id: str`、`version: int`、`delivery_intent: dict[str, Any]` 和持久化的 `orchestration["completionReports"]` 历史。
类型：完成状态机 / 幂等副作用 / 版本化持久化。
- 定义/写入：`reconcile_stage` 在最终 stage 提交内先写 `STATE_COMPLETED` 和 `finalReport`，提交后才调用 `on_project_completed`；当前通知持久化只复制 `feishuNotifications`。
- 读取来源：正常最终阶段、跳过阶段、恢复 reconcile 都通过同一完成 callback 接入；`run_id` 是比“已完成任务数”更可靠的 occurrence 基础。
目标变化：完成事务持久化一个稳定 occurrence 与 pending intent，再异步/事务后处理；同一 occurrence 重入幂等，新 run 递增版本；投递状态不影响 `project.status=completed`。
- 影响面：最终报告路径/history、Markdown 写盘、恢复 reconcile、通知回调、并发冲突处理、报告页 API。
- 测试锚点：扩展 `tests/test_project_stage_dispatch.py` 覆盖同 run 重入、新 run 新版本、禁用时无 intent、处理失败项目仍 completed；扩展 store 测试验证历史报告不被覆盖。
- 排除方案：不再使用 `project-complete:<project_id>:<completed_task_count>` 作为 occurrence，因为相同任务数的重跑会误判重复；不把状态只保存在进程内队列。
未决假设：重跑入口是否始终分配新的 `stageRunId` 需要在设计阶段对所有重跑路径再做一次调用链验证；若不能保证，occurrence ID 需由持久化序号与完成时间共同生成。

修改点 ID：MP-4

对应 scenario：只使用可交付最终产物；缺失/过大/不可读时标注但不回退到日志或中间材料；生成包含要求章节的人类可读报告。
- 仓库/基线：本仓库 / `f0b7f3e646a1a4e64b350d447d6e18fa15362065`
文件：`app/services/project_task_final_result.py`；`app/services/artifacts.py`；`app/services/project_final_report.py`；计划新增 `app/services/project_completion_report_artifacts.py` 与 `app/services/project_completion_report_prompt.py`。
符号：`ensure_task_final_result`；`read_artifact`（346-375）；`render_project_final_report_markdown`（47-84）；计划新增 `collect_completion_report_artifacts(...)`、`format_completion_report_prompt(...)`。
变量：只允许读取 `task["finalResult"]["markdownPath"]: str`、`task["finalResult"]["artifactRefs"]: list` 及项目级 `orchestration["finalReport"]["markdownPath"]`；生成 `eligible_artifacts: list[ArtifactInput]`、`omissions: list[ArtifactOmission]`。
类型：安全边界 / 产物选择 / Agent Prompt。
- 定义/写入：`finalResult` 已保存最终摘要、Markdown 路径和显式 artifact refs；`read_artifact` 已提供安全根目录、关联性和 512 KiB 上限校验。
- 读取来源：新收集器只遍历显式最终结果引用并通过注入的安全读取端口获取文本；不得复用 server 中会混入 `changedFiles`、测试证据和执行 evidence 的宽泛 artifact source 扫描。
目标变化：建立显式 allowlist、单文件/总输入大小与数量边界、缺失原因列表；使用共享 `services.bridge_input_output_formatting` 构造 XML 外层 prompt，动态产物放入转义的数据边界，输出契约要求结构化的人类可读结果。
- 影响面：Provider 调用、Prompt 注入防护、秘密泄露面、报告质量、超限行为。
- 测试锚点：新聚焦测试验证只读 final refs、拒绝日志/越界路径/符号链接/超限文件、动态内容无法闭合 XML 指令、缺失产物形成 omission 而非 evidence 回退。
- 排除方案：不把完整 workspace、执行日志、review prompt、隐藏推理或任意 changed file 送给 Agent；不在 `app/server.py` 拼接新 prompt。
未决假设：哪些扩展名可视为“人类可读最终产物”需在设计中给出白名单；二进制产物应只展示安全引用/元数据，不直接内联。

修改点 ID：MP-5

对应 scenario：通知机器人只发给创建者；pending/delivered/failed 可见；有限自动重试；失败后 owner 可手动重发；缺少目的地失败且不转发。
- 仓库/基线：本仓库 / `f0b7f3e646a1a4e64b350d447d6e18fa15362065`
文件：`app/feishu_notifications.py`；`app/server.py`；`app/server_services/projects.py`；`app/projects.js`；计划新增 `app/services/project_completion_report_delivery.py` 和聚焦的 resend handler/route 模块。
符号：`send_feishu_notification`（581-661）；`_send_feishu_workflow_notification`（13066-13072）；`_send_project_execution_project_complete_notification`（13299-13328）；`_handle_project_report` / `_project_final_report_payload`；`renderReportView`（4340 起）；计划新增 `CompletionReportDeliveryService.process/resend`。
变量：现有通知配置 `VO_CONFIG["notifications"]["feishuReceiveIdType"|"feishuReceiveId"]`；计划每 occurrence 持久化 `deliveryStatus: pending|delivered|failed`、`attemptCount: int`、`nextAttemptAt: str|null`、`lastError: str|null`、`messageId: str|null`。
类型：外部投递 / 重试状态机 / 项目报告 API 与 UI。
- 定义/写入：现有 notification bot 已通过独立 App credentials/receive ID 发送并返回结果，但没有项目报告重试策略；项目报告 API/UI 目前只展示本地 `finalReport`。
- 读取来源：新服务从持久化 occurrence 读取生成内容、版本与目的地，使用幂等键调用通知发送端口；报告页返回每个 occurrence 的状态并只在失败态提供 resend 动作。
目标变化：沿用 notification bot transport，chat bot 不参与发送；自动重试有明确上限和可恢复错误分类；手动 resend 针对同一 occurrence/version 新建 attempt，不改变项目完成状态。
- 影响面：配置、后台调度/恢复、项目 API、项目报告 UI、审计日志、错误可观测性。
- 测试锚点：新 delivery service 测试覆盖成功、可恢复失败后重试、上限耗尽、并发 claim、手工 resend、无目的地、重复 worker；API/UI 测试覆盖状态展示和授权拒绝。
- 排除方案：不使用 chat bot 发送；不因报告失败修改项目 status；不把失败报告重定向到群或备用接收人；不在 request 线程中做无界同步重试。
未决假设：当前 notification bot 只有一个全局 `receiveId`，没有 `createdBy -> Feishu identity` 映射；当前唯一 `representativeAgentId` 属于 chat bot 配置，notification bot 没有报告生成 Agent 绑定。两者必须在设计前明确。

## 跨修改点风险与待确认决策

1. **报告生成 Agent 的来源**：推荐复用当前 `feishu.chatApp.representativeAgentId` 作为“内容生成 Agent”，但最终发送仍严格走 notification bot；另一方案是给 notification 配置新增独立 `representativeAgentId`。不能默认使用项目执行 Agent，因为这会改变“飞书主执行 Agent”的语义。
2. **创建者接收人映射**：当前系统只配置一个全局 notification `receiveId`，而 `createdBy` 可能是 `user` 或 Agent ID。若本产品按单用户部署，应把全局目的地明确视为该项目 owner 的映射；若需要真正多用户，则必须新增身份映射能力，范围会显著扩大。
3. **owner 授权**：当前项目更新/resend API 缺少请求用户身份。单用户部署下可沿用现有访问边界；多用户语义需要先补认证授权上下文。

## 建议的确认结果

- 接受 MP-1 至 MP-5 作为后续 `design.md` 的唯一实现边界。
- 报告生成 Agent 采用“复用 chatApp 的 representative Agent 生成内容、notification bot 负责发送”。
- 当前版本按单用户部署定义 owner：全局 notification `receiveId` 即项目创建者的已映射飞书目的地；文档中明确这是部署约束，不宣称已有多用户映射。
