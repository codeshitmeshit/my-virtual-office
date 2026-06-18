# Meeting for AI Phase 4 Checklist

确认状态：已确认

## 人工确认记录

- 2026-06-17T00:00:00+08:00：用户确认可以生成 todolist。确认范围包含 Phase 4 checklist 现有条目，尤其是接口和前端 UI 可先用确定性 fixture 验证、真实 AI 申请测试前必须通知用户安装对应 skill、以及右侧控制面板 Meetings 区域显示人工确认提示。

## Request Creation

### CHK-P4-001 Valid Project Task Request

- 关联需求：AI request eligibility, project-task source.
- 验证方法：从项目任务上下文提交一条包含会议目标、期望产物、无法单独完成原因、建议参会者和会议类型的 AI 会议申请。
- 预期结果：系统创建 pending/requested 状态的会议申请；申请显示来源项目、来源任务和请求 AI；不创建 active meeting。

### CHK-P4-002 Request Quality Gate

- 关联需求：required explanation fields, anti-spam.
- 验证方法：分别缺少会议目标、期望产物、无法单独完成原因时提交申请。
- 预期结果：申请不能成为可处理的 pending request；用户不会看到缺失关键信息的有效申请；错误或拒绝原因可理解。

### CHK-P4-003 Request Source Boundary

- 关联需求：ordinary chat out of scope, future trigger extension point.
- 验证方法：尝试从普通聊天或无项目任务来源创建正式 AI 会议申请，同时检查 request source 字段或等价来源记录。
- 预期结果：本期不产生正式 pending request；系统保留可扩展的来源表达，不把产品永久限制为只能项目任务。

## Context Candidates

### CHK-P4-004 Same-Project Context Candidate Generation

- 关联需求：context candidate scope.
- 验证方法：在一个包含当前任务、相关同项目任务和同项目历史会议的项目中创建申请。
- 预期结果：候选上下文包含当前项目、当前任务、相关同项目任务和同项目历史会议的摘要或引用；不包含跨项目内容。

### CHK-P4-005 Context Defaults Unselected

- 关联需求：recommended context must be explicitly selected.
- 验证方法：打开待确认申请，检查所有自动推荐上下文的默认状态。
- 预期结果：推荐上下文默认未选中；未做选择直接确认时，不会把候选内容作为会议上下文发送。

### CHK-P4-006 Confirmed Context Snapshot Isolation

- 关联需求：selected context only, immutable snapshot.
- 验证方法：选择部分候选上下文并补充手写上下文后确认会议；随后修改原项目任务或历史会议内容。
- 预期结果：创建的会议只包含已选候选和补充上下文；未选候选不出现在 provider 输入、发言记录、总结或结果中；已确认会议保留确认时的快照，不随源内容变化。

## User Review

### CHK-P4-007 Editable Confirmation

- 关联需求：user can edit before confirmation.
- 验证方法：用户在确认前修改主题、目的、会议类型、参会者、主持人、最大轮次、上下文选择和补充资料。
- 预期结果：最终创建的会议使用用户修改后的配置；原始 AI 申请理由仍可追踪。

### CHK-P4-008 Lightweight Edit Trace

- 关联需求：retain original request and edit summary.
- 验证方法：确认一条经过用户修改的申请后查看申请记录或会议来源信息。
- 预期结果：能看到原始申请理由和用户修改摘要；不要求完整字段级审计。

### CHK-P4-009 Reject With Feedback

- 关联需求：rejection handling.
- 验证方法：用户拒绝一条申请并填写拒绝原因。
- 预期结果：申请进入 rejected/closed 状态；不会创建会议；拒绝原因回到来源任务上下文，供请求 AI 或用户后续查看。

## Safety

### CHK-P4-010 Unconfirmed Request Does Not Execute

- 关联需求：no provider call or occupancy before confirmation.
- 验证方法：创建 pending request 后观察 active meetings、Agent occupancy、provider call records 或等价状态。
- 预期结果：未确认申请不占用任何 Agent，不调用会议参与者，不出现在进行中会议列表。

### CHK-P4-011 Confirmed Request Converts Once

- 关联需求：idempotent confirmation and conversion.
- 验证方法：对同一申请重复提交确认请求，或刷新后再次点击确认。
- 预期结果：只创建一场 executable meeting；申请记录关联该 meeting ID；不会重复占用或重复启动。

### CHK-P4-012 Rejected Request Cannot Be Confirmed Later Without Reopen

- 关联需求：request lifecycle consistency.
- 验证方法：拒绝申请后尝试直接确认同一申请。
- 预期结果：系统拒绝非法转换，除非存在明确的重新打开流程；不会创建会议。

## UI and Observability

### CHK-P4-013 Pending Request Visibility

- 关联需求：user can view pending AI requests.
- 验证方法：创建 pending request 后分别打开来源任务详情面板和 Meetings dashboard 的 AI Requests 队列。
- 预期结果：用户可以在来源任务详情看到该任务相关申请，也可以在 Meetings dashboard 聚合队列看到全部待处理申请；两处均展示来源任务、请求 AI、请求理由、期望产物、状态和处理入口。

### CHK-P4-014 Request Status Is Understandable

- 关联需求：accepted, rejected, pending state clarity.
- 验证方法：分别查看 pending、rejected、confirmed 三种状态。
- 预期结果：界面能区分待处理、已拒绝、已确认并已创建会议；状态文案不把 pending request 误称为 active meeting。

### CHK-P4-015 Requests Are Not Active Meetings

- 关联需求：Meetings dashboard placement, no active meeting before confirmation.
- 验证方法：创建 pending request 后查看 Meetings dashboard Active tab、AI Requests tab 和右侧控制面板的 Meetings 区域。
- 预期结果：pending request 只出现在 AI Requests 队列和来源任务上下文；不出现在 Active meetings 列表；控制面板 Meetings 区域只显示待处理数量或需要人工确认的轻量提示，不显示完整审查表单。

### CHK-P4-016 Control Panel Confirmation Prompt

- 关联需求：control panel Meetings widget confirmation-needed prompt.
- 验证方法：创建至少一条 pending AI meeting request 后查看右侧控制面板的 Meetings 区域，并点击提示入口。
- 预期结果：Meetings 区域显示有 AI 会议申请需要人工确认的提示或数量；点击后打开 Meetings dashboard 并进入或突出显示 AI Requests 队列；提示不把申请渲染成 active meeting。

### CHK-P4-017 Task Card Compact Indicator

- 关联需求：task card compact status badge.
- 验证方法：为某个任务创建 pending AI meeting request 后查看项目看板任务卡片。
- 预期结果：任务卡可显示紧凑状态徽标或数量提示；点击任务后在详情面板处理申请；任务卡不承载完整申请确认流程。

### CHK-P4-018 User-Started Meeting Regression

- 关联需求：Phase 1-3 compatibility.
- 验证方法：在 Phase 4 改动后继续从用户入口创建并运行一场普通 executable meeting。
- 预期结果：用户发起会议的创建、执行、实时讨论、结束和历史展示不受 AI 申请功能影响。

## Manual Acceptance

### CHK-P4-019 API and UI Happy Path Before Real AI Gate

- 关联需求：Phase 4 success criteria.
- 验证方法：使用确定性 fixture 或等价项目任务场景创建 AI 会议申请，用户编辑配置，选择部分上下文，补充资料，确认并启动会议。
- 预期结果：接口、状态流和前端 UI 均可用；会议按用户最终配置启动；参与 AI 只接收用户确认的上下文；申请与创建的会议可互相追踪；未确认阶段没有 Agent 占用或 provider 调用。

### CHK-P4-020 Full Rejection Path

- 关联需求：rejection feedback to source task.
- 验证方法：从项目任务场景创建 AI 会议申请，用户拒绝并填写原因。
- 预期结果：申请关闭，会议不启动，来源任务可看到拒绝原因，后续不会重复展示为待处理申请。

### CHK-P4-021 Real AI Skill Preparation Gate

- 关联需求：real AI acceptance gate.
- 验证方法：在需要验证真实 AI 从项目任务中主动提交会议申请前，停止自动测试并通知用户准备和安装对应 skill。
- 预期结果：未获得用户确认前，不执行真实 AI-originated request 验收；获得确认后再运行真实 AI 申请、用户确认和会议启动流程。

### CHK-P4-022 Full Real AI-Originated Happy Path

- 关联需求：AI request eligibility, user-controlled confirmation, confirmed context snapshot.
- 验证方法：用户确认 skill 已安装后，让真实项目任务 AI 在明确阻塞场景中提交会议申请，用户编辑配置，选择上下文并确认启动会议。
- 预期结果：真实 AI 能按要求提交包含目标、期望产物和无法单独完成原因的申请；用户确认前不调用参会者；确认后会议使用用户最终配置和已选上下文启动。

## 测试记录

- 2026-06-17T13:18:34+08:00：自动化静态检查通过：`node --check app/game.js`、`node --check app/projects.js`、`app/locales/en.json` 和 `app/locales/zh.json` JSON 解析通过。
- 2026-06-17T13:18:34+08:00：后端回归通过：`.venv/bin/python tests/test_meeting_for_ai_phase4.py`、`.venv/bin/python tests/test_meeting_for_ai_phase1.py`。
- 2026-06-17T13:18:34+08:00：8038 端口 API fixture 验证通过。fixture 创建项目任务来源 AI 会议申请，确认 pending request 不进入 active meetings；上下文候选包含 `project`、`task`、`related_task`；按任务查询返回该申请；确认后 request 状态为 `confirmed` 并创建 meeting；重复确认返回幂等结果；拒绝路径将拒绝原因回写来源任务评论。覆盖 CHK-P4-001、CHK-P4-004、CHK-P4-009、CHK-P4-010、CHK-P4-011、CHK-P4-013、CHK-P4-019、CHK-P4-020 的 API/状态流部分。
- 2026-06-17T13:18:34+08:00：已按用户要求尝试使用 MCP Chrome DevTools 做前端页面验证，但 `mcp__chrome_devtools.new_page` 和 `mcp__chrome_devtools.list_pages` 均返回浏览器 profile 占用错误：`The browser is already running for /home/wo/.cache/chrome-devtools-mcp/chrome-profile`。前端页面实测因此未完成；当前仅完成 JS 语法、i18n、API 支撑和代码路径检查。
- 2026-06-17T13:18:34+08:00：真实 AI-originated 验收未执行。根据用户约束，必须先通知用户准备并安装请求 AI 需要的 skill，之后再运行 CHK-P4-021 和 CHK-P4-022。
- 2026-06-17T14:22:56+08:00：MCP Chrome DevTools 前端补测通过。使用隔离 8038 服务和页面内 fetch 创建项目任务来源 pending 申请；右侧控制面板 Meetings 区显示“有 AI 会议申请需要确认 1”，入口打开 Meetings dashboard 并选中“AI 申请”tab；AI 申请卡展示来源项目、来源任务、请求 AI、目标、期望产物、原因、确认/拒绝按钮；上下文候选 3 个且默认 0 个选中；Active tab 显示“暂无进行中会议”，pending request 不在 active meetings；项目任务卡显示 `📊 1` 紧凑提示；任务详情显示“AI 会议申请”区、待确认状态、请求 AI、理由和打开队列入口；在 UI 中选择真实参会代理后确认，request 转为 `confirmed`、pendingCount 归零并创建 active executable meeting；另建 pending request 后通过 UI 拒绝，request 转为 `rejected`，拒绝原因回写来源任务评论，未新增 active meeting。覆盖 CHK-P4-005、CHK-P4-007、CHK-P4-009、CHK-P4-013、CHK-P4-014、CHK-P4-015、CHK-P4-016、CHK-P4-017、CHK-P4-019、CHK-P4-020 的前端展示和交互部分。
- 2026-06-17T15:35:42+08:00：真实 AI-originated 验收通过。用户确认对应 AI skill 已安装后，在真实 8090 VO 环境中创建项目 `Real AI Meeting Request Acceptance` 和任务 `Trigger a real AI meeting request`，通过 VO agent communication 要求 `hermes-default` 作为真实 AI 使用已安装 skill 主动提交项目任务来源 meeting request。Hermes 返回 request `61fd964c-00de-4814-a187-d80a07576921`，API 验证其状态为 `pending`、来源 project/task 正确、`requestingAgentId=hermes-default`、`suggestedParticipants=["hermes-default","main"]`、必填 goal/expectedOutcome/cannotCompleteAloneReason 均存在；确认前 `/api/meetings/active` 为空。MCP UI 验证右侧控制面板显示待确认提示，AI 申请队列显示该真实申请，上下文候选默认未选中。随后以用户确认动作选择 task 上下文和补充上下文，request 转为 `confirmed` 并转换为 executable meeting `87adccde-e700-447e-8c35-7690a961dbda`；会议来源保留 `meetingRequestId`、projectId、taskId；确认后的会议上下文只包含选中的 task 候选和补充上下文。调用 run 后真实参会 AI `main` 与 `hermes-default` 均产生 provider call 和 participant turn，会议进入 `awaiting_user_decision`。覆盖 CHK-P4-021、CHK-P4-022，并补强 CHK-P4-010、CHK-P4-013、CHK-P4-015、CHK-P4-019。

## 最终验收确认

- 2026-06-17T23:46:48+08:00：用户确认 Phase 4 已验收完成，可以归档。确认范围包含前述确定性 API/UI 验证、MCP 前端补测和真实 AI-originated happy path 验收记录。
