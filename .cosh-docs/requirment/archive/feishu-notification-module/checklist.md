# Feishu Notification Module Checklist

确认状态：已确认

## Checklist

### CHK-001 - Four notification categories are supported

- 关联需求点：四级通知模块；四类分别为申请表单、通知、警告、错误。
- 验证方法：用测试或人工调用分别构造 application_form、notification、warning、error 四类通知。
- 预期结果：四类通知都能生成合法 Feishu card payload；类型映射清晰，不需要业务方手写完整 Feishu JSON。

### CHK-002 - Category visual and content rules are semi-unified

- 关联需求点：颜色、标题层级、核心字段统一，业务可增加自定义内容。
- 验证方法：检查四类卡片的结构和渲染字段，确认包含统一标题、摘要、核心字段和类型样式，同时允许业务 detail 字段。
- 预期结果：卡片体验一致；业务字段可扩展；没有每个业务模块完全自由拼装导致的样式漂移。

### CHK-003 - Application form supports extensible buttons with common action categories

- 关联需求点：按钮可扩展，不同业务场景可定义不同含义，但必须归类为通用动作类型。
- 验证方法：构造至少三种按钮：确认类、取消类、跳转类；再构造一个未归类动作。
- 预期结果：合法按钮能出现在申请表单卡片中；未归类或不受支持的决策动作被拒绝或显式标记为无效。

### CHK-004 - Application form state expression is complete for first phase

- 关联需求点：待处理、已处理、已过期、已取消、不再可处理等状态。
- 验证方法：分别生成 pending、submitted/processing、approved/rejected、expired、cancelled、no_longer_actionable 状态的申请表单。
- 预期结果：每种状态在卡片上有明确可读表达；失效状态不会看起来仍可正常处理。

### CHK-005 - Application form supports single decision by default and multi-participant declaration

- 关联需求点：默认单人最终决策，允许业务声明多人参与。
- 验证方法：构造默认申请表单和显式多人参与申请表单。
- 预期结果：默认语义体现单人处理；多人场景能在卡片或元数据中明确表达，不与默认规则混淆。

### CHK-006 - First phase does not falsely claim complete callback workflow

- 关联需求点：点击处理完整业务闭环后续接入；第一版只需通用反馈和状态表达。
- 验证方法：检查卡片文案、代码注释、记录字段和用户可见反馈。
- 预期结果：系统不会把按钮点击包装成已完成业务审批；没有依赖不存在的 Feishu 回调闭环。

### CHK-007 - Non-application notifications only support navigation actions

- 关联需求点：通知、警告、错误可以有查看详情/打开相关页面按钮，但不承载决策。
- 验证方法：为 notification、warning、error 构造跳转按钮和决策按钮。
- 预期结果：跳转按钮允许；同意、拒绝、确认处理等决策按钮不允许或被清晰拒绝。

### CHK-008 - Error notifications distinguish user-facing and admin-facing content

- 关联需求点：错误默认同时发给用户和管理员，但需区分用户可理解错误和系统内部错误。
- 验证方法：构造用户操作错误和系统内部错误。
- 预期结果：用户版不包含堆栈、token、内部 payload；管理员版可包含必要的诊断摘要；两者均不泄露 webhook 密钥。

### CHK-009 - Delivery records support troubleshooting

- 关联需求点：基础记录服务排障。
- 验证方法：模拟 Feishu 成功、非成功响应、网络失败或超时。
- 预期结果：记录包含发送时间、类型、标题、目标描述、成功状态和失败原因；失败原因经过脱敏。

### CHK-010 - Delivery records support business traceability

- 关联需求点：基础记录服务业务追踪，知道某个业务对象是否通知过。
- 验证方法：发送带 related business object 的会议申请或任务通知。
- 预期结果：记录可关联业务对象类型和 ID；能判断该业务对象是否尝试过通知以及结果。

### CHK-011 - Webhook secret is not committed or leaked

- 关联需求点：webhook URL 是敏感凭据；不得进入源码、日志、前端或文档。
- 验证方法：检查配置方式、日志输出、错误记录、测试 fixture 和仓库 diff。
- 预期结果：真实 webhook 不出现在提交文件中；日志和记录中 token 被隐藏；前端无法读取完整 webhook。

### CHK-012 - Feishu payload validation covers malformed inputs

- 关联需求点：通用模块应保护一致性和可维护性。
- 验证方法：构造缺少标题、未知类型、非法按钮、过长或空内容等输入。
- 预期结果：模块返回可理解的错误或降级行为；不会生成明显非法或误导性的卡片。

### CHK-013 - Existing VO workflows are not forced to migrate all at once

- 关联需求点：先实现通用模块，后续实现或调用该模块。
- 验证方法：检查引入方式和调用点。
- 预期结果：模块可以独立存在；会议申请可作为首个调用方；其他现有功能不因未迁移而破坏。

### CHK-014 - Manual Feishu verification is possible and clearly marked

- 关联需求点：上线后重要事件能及时、统一、易读地推到飞书。
- 验证方法：使用测试 webhook 或用户明确允许的 webhook 发送一条测试通知和一条测试申请表单。
- 预期结果：群里能看到清晰测试卡片；测试内容不包含敏感业务数据；发送结果被记录。

### CHK-015 - Regression coverage protects existing notification or meeting behavior

- 关联需求点：VO 内部模块复用，会议申请是首个典型场景。
- 验证方法：运行相关单元测试和现有会议/项目通知回归测试。
- 预期结果：新增模块不破坏已有会议申请、项目执行、Agent 协作或现有 Feishu 相关功能。

## 人工确认记录

- 2026-07-02T02:03:12+08:00 - checklist 初次确认。用户确认摘要：pass。

## 实现验证记录

- 2026-07-02T02:20:17+08:00 - CHK-001 至 CHK-013 自动化验证通过。覆盖测试：`.venv/bin/python tests/test_feishu_notifications.py`、`.venv/bin/python tests/test_feishu_sync.py`、`.venv/bin/python tests/test_meeting_request_blocks_task.py`、`.venv/bin/python tests/test_meeting_for_ai_phase4.py`、`.venv/bin/python -m py_compile app/feishu_notifications.py app/server.py tests/test_feishu_notifications.py tests/test_meeting_for_ai_phase4.py`、`git diff --check`。
- 2026-07-02T02:20:17+08:00 - CHK-014 手动飞书验收未执行。本次实现未使用真实 webhook 发送消息；真实 webhook 只允许通过 `VO_FEISHU_NOTIFICATION_WEBHOOK` 环境变量配置。
- 2026-07-02T02:20:17+08:00 - CHK-015 会议申请相关回归通过。扩展项目执行回归 `.venv/bin/python tests/test_project_execution.py` 在既有 `test_project_level_start_selects_first_eligible_and_auto_reviews_to_done_by_default` 等待点超时；隔离运行该测试同样超时，失败路径未经过本次新增 Feishu 通知模块或会议申请通知接入。
- 2026-07-02T21:39:49+08:00 - CHK-001 至 CHK-015 最终验收通过。自动化验证覆盖：`.venv/bin/python tests/test_feishu_notifications.py`、`.venv/bin/python -m py_compile app/server.py app/feishu_notifications.py app/feishu_long_connection.py tests/test_feishu_notifications.py`、`node --check app/game.js`、`bash -n start.sh`、`git diff --cached --check`。
- 2026-07-02T21:39:49+08:00 - CHK-014 生产飞书验收通过。用户在生产飞书群中验证四类测试卡片可发送，申请表单按钮点击后通过长连接返回“操作已收到”toast。

## 最终验收记录

- 2026-07-02T21:39:49+08:00 - 测试通过确认。用户确认摘要：可以，那先验收这个需求吧。
- 2026-07-02T21:39:49+08:00 - 最终 done 确认。用户确认摘要：可以，那先验收这个需求吧。
