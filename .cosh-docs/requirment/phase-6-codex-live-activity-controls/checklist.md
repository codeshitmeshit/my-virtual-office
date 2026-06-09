# Phase 6 Codex Live Activity and Controls Test Checklist

确认状态：已确认

## Checklist 确认记录

- 确认项：Phase 6 全量测试 checklist（26 项，保留稳定编号并移除 CHK-011、CHK-023）。
- 确认时间：2026-06-09T06:54:09+08:00。
- 用户确认摘要：用户确认当前 checklist，可以生成 todolist。

## 实现验证记录

- 执行时间：2026-06-09T15:04:57+08:00。
- 自动化：Codex bridge/provider/server 测试通过；Phase 6 HTTP E2E 通过，覆盖活动增量、允许一次、跨窗口 busy 定位、取消、`_VO_INT=1`/`demo:false` 和挂起审批服务重启后的安全失效。
- 浏览器：工具卡片、审批卡片、`acceptForSession` 范围提示、审批中刷新恢复、原 turn 续跑和取消无回滚提示通过。
- 真实 Codex：在 `_VO_INT=1` 且 `/api/license` 返回 `demo:false` 下完成只读任务；真实 thread/turn、命令活动、增量输出、终态和回复均通过，未修改文件。
- 回归：Review parser 16/16 和 85/85 通过；项目 CRUD 5/5 通过；JavaScript/Python/shell 静态检查及 `git diff --check` 通过。
- 待确认：用户最终浏览器验收；具备实际 OpenClaw/Hermes gateway 的环境中进行 live provider 回归后，再确认 `confirmed.tested`。

## 分阶段验收规则

Phase 6 按以下三个阶段独立开发、独立测试、独立人工确认。前一阶段未通过时，不应把后一阶段标记为完成。

每个阶段完成时必须在本文件追加阶段确认记录，包含：阶段名称、执行时间、通过项、阻塞项、用户确认摘要。Phase 6 整体的 `confirmed.tested` 和 `confirmed.done` 仅在 Phase 6C 及全量回归确认后更新。

## Phase 6A：实时活动可见

### 阶段目标

让用户在不获得交互式审批能力的前提下，看见 Codex 的实时工具活动、安全详情和刷新后的执行轨迹。审批与补充信息仍沿用 Phase 5 的终止式处理。

### 必过检查项

- 核心活动：CHK-001、CHK-002、CHK-003、CHK-004、CHK-005。
- 安全与数据：CHK-006、CHK-007、CHK-008。
- 运行中刷新恢复：CHK-019。
- 阶段兼容性：CHK-025、CHK-026，以及 CHK-027 中 OpenClaw/Hermes 既有工具卡片不回归的部分。

### 阶段验收步骤

1. 使用 deterministic fixtures 完成事件状态机、脱敏、截断、批处理和 UI 自动化测试。
2. 使用真实 Codex 任务验证读取、搜索、命令、文件变更、MCP、错误和运行中刷新。
3. 重跑 Phase 5 核心回归，并人工检查 OpenClaw/Hermes 工具卡片。
4. 在浏览器完成仅覆盖“轨迹可见”的局部验收。

### 阶段通过条件

- 所有必过检查项通过或有用户明确接受的非阻塞限制。
- 用户能够判断 Codex 当前正在做什么、是否仍在推进以及最终做了什么。
- 不出现原始测试密钥、重复工具卡片、丢失终态或页面明显卡顿。
- Phase 6A 通过后可以独立交付，但不得宣称已支持审批续跑、回答续跑或取消。

## Phase 6B：人工介入控制

### 阶段目标

在 Phase 6A 的事件身份和持久化基础上，让真人处理 Codex 的审批与补充问题，并能够取消运行中或等待中的任务。

### 必过检查项

- 审批与回答：CHK-009、CHK-010、CHK-012、CHK-013、CHK-014、CHK-015。
- 取消：CHK-016、CHK-017、CHK-018。
- 阶段兼容性：CHK-024 的交互终态子集、CHK-025，以及 CHK-026/CHK-027 的相关回归。

### 阶段验收步骤

1. 使用 fake app-server 覆盖 allow once、Codex runtime session allow、reject、answer、cancel 和竞态。
2. 使用真实 Codex 分别验证命令审批、文件审批、补充问题和取消。
3. 验证普通消息在等待期间被拒绝，Agent 来源仍 fail closed。
4. 在浏览器完成两种允许语义、运行时授权范围提示、取消后修改提示的局部验收。

### 阶段通过条件

- 所有必过检查项通过或有用户明确接受的非阻塞限制。
- 审批、回答和取消都作用于原 turn，不创建隐藏替代任务。
- “允许一次”和 Codex 运行会话级允许的范围对用户可理解，且不宣称与 VO conversation 生命周期绑定。
- 任一交互终态都释放锁并恢复正确 presence。
- Phase 6B 通过后可以独立交付，但服务重启后的挂起交互恢复仍不作为承诺。

## Phase 6C：恢复与生产加固

### 阶段目标

完成挂起状态恢复、服务重启对账、多窗口定位和全链路稳定性，使 Phase 6 达到整体验收标准。

### 必过检查项

- 恢复与多窗口：CHK-020、CHK-021、CHK-022。
- 完整终态矩阵：CHK-024。
- 完整兼容回归：CHK-025、CHK-026、CHK-027。
- 全链路人工验收：CHK-028。
- 回归要求：重新执行 Phase 6A 和 Phase 6B 的全部必过检查项。

### 阶段验收步骤

1. 在等待审批、等待回答和运行中分别执行刷新、断线重连及服务重启测试。
2. 验证事件去重、序列连续性、不可恢复请求的安全终止及多窗口活动会话跳转。
3. 执行 completed、failed、timeout、cancelled、rejected、bridge unavailable 和协议错误矩阵。
4. 执行 Phase 5、OpenClaw、Hermes、demo、安全和浏览器全量回归。

### 阶段通过条件

- Phase 6C 必过项及 Phase 6A/6B 全量回归全部通过。
- 刷新或服务重启后不存在虚假可操作按钮、隐藏 busy、重复事件或串会话。
- 用户在任何窗口都能定位活动任务，并明确区分 running、waiting 和 terminal 状态。
- 用户确认最终浏览器验收后，Phase 6 才可设置 `confirmed.tested=true`；最终交付再单独确认 `done`。

## 详细检查项

### Live activity

#### CHK-001 Comprehensive activity coverage

- 验证方法：让 Codex 在一个真实短任务中读取文件、搜索、执行命令、修改文件并调用可用的外部/MCP 工具。
- 预期结果：每类操作都产生可识别的工具卡片，包含稳定顺序、运行状态和终态；未知 item 以安全通用卡片呈现而非丢失。
- 关联需求点：完整执行过程可见、非黑盒体验。

#### CHK-002 Incremental command progress

- 验证方法：运行会持续输出多段内容的命令。
- 预期结果：同一命令卡片增量更新而不重复创建；输出经过批处理，页面保持可响应，最终包含退出状态。
- 关联需求点：实时进度、高频事件可用性。

#### CHK-003 File and external-tool activity

- 验证方法：触发文件变更、MCP 调用及一个工具错误。
- 预期结果：文件路径、工具名称、进度和安全错误分别显示；最终修改文件清单与轨迹一致。
- 关联需求点：文件修改、外部工具、错误全部可追踪。

#### CHK-004 Expandable card presentation

- 验证方法：检查运行中、完成和失败卡片的默认与展开状态。
- 预期结果：默认显示简洁摘要；展开后可查看过滤后的输入、输出或错误；当前活动卡片优先展开。
- 关联需求点：默认简洁、按需查看细节。

#### CHK-005 Long trajectory collapsing

- 验证方法：产生超过界面折叠阈值的工具事件。
- 预期结果：所有事件仍可追溯，较早卡片自动折叠并可重新展开，不发生静默永久删除。
- 关联需求点：完整保留与长轨迹可读性。

### Security and data handling

#### CHK-006 Sensitive-value redaction

- 验证方法：使用测试值覆盖 token、API key、Authorization、Cookie、环境变量、带凭据 URL 和嵌套 JSON 字段。
- 预期结果：实时事件、刷新历史、日志和错误中均不出现原始敏感值；普通代码与路径仍保持可理解。
- 关联需求点：自动敏感信息过滤。

#### CHK-007 Payload limits and truncation

- 验证方法：产生超大命令输出、工具结果和错误文本。
- 预期结果：存储和 UI 使用有界内容并明确显示截断；事件状态、工具身份和关联 ID 不丢失。
- 关联需求点：输出安全、性能与可理解性。

#### CHK-008 Tool-data visibility notice

- 验证方法：首次展开包含代码或业务数据的工具详情。
- 预期结果：界面明确说明工具详情可能包含工作区内容且已执行敏感值过滤。
- 关联需求点：数据可见性预期管理。

### Approval and input continuation

#### CHK-009 Allow once

- 验证方法：触发命令或文件审批，选择“允许一次”。
- 预期结果：原 turn 继续，不创建新 turn；仅当前请求被放行，后续同类请求仍可再次询问。
- 关联需求点：人类允许一次并续跑原任务。

#### CHK-010 Allow for current Codex runtime session

- 验证方法：触发命令或文件审批，选择“当前 Codex 运行会话允许同类操作”，随后在同一 Codex runtime session 中触发匹配请求。
- 预期结果：协议返回 `acceptForSession`，Codex 按原生 session cache 处理后续匹配操作；界面明确说明范围和有效期由 Codex runtime 控制，不与 VO conversation 绑定，也不提供撤销承诺。
- 关联需求点：使用 Codex 原生运行会话级审批并准确表达其范围。

#### CHK-012 Reject approval

- 验证方法：对审批请求选择拒绝。
- 预期结果：请求不被执行，当前任务按产品规则终止，记录拒绝原因并恢复 idle。
- 关联需求点：拒绝并终止、安全控制。

#### CHK-013 Answer user-input request

- 验证方法：触发 Codex 补充信息问题，提交自由文本或结构化选择。
- 预期结果：答案关联原始问题 ID，原 turn 继续并完成；问题和答案在历史中可追溯。
- 关联需求点：聊天内补充信息并续跑原任务。

#### CHK-014 Block ordinary messages while waiting

- 验证方法：在等待审批和等待回答时分别发送普通消息。
- 预期结果：新消息被明确拒绝，不被当作回答、不排队、不启动新 turn；用户可选择处理或取消。
- 关联需求点：等待期间无歧义交互。

#### CHK-015 Agent-originated interaction fails closed

- 验证方法：由 OpenClaw 和 Hermes 发起会触发审批或补充信息的 Codex 请求。
- 预期结果：不允许其他 Agent 自动批准或回答；任务以 `needs_human_intervention` 终止并记录原因。
- 关联需求点：交互式控制仅面向真人。

### Cancellation

#### CHK-016 Cancel running turn

- 验证方法：在命令执行或工具调用期间点击取消。
- 预期结果：显示 cancelling，发送 interrupt，最终为 cancelled；锁和 presence 被释放，重复取消不会产生冲突。
- 关联需求点：运行中取消。

#### CHK-017 Cancel pending interaction

- 验证方法：在等待审批和等待回答时取消。
- 预期结果：挂起的协议请求被安全结束，turn 终止，待处理卡片不可再提交，刷新后不会复活。
- 关联需求点：等待状态取消。

#### CHK-018 Cancellation does not imply rollback

- 验证方法：先让 Codex 修改测试文件，再在后续步骤取消。
- 预期结果：界面显示“取消不会自动撤销修改”，列出已修改文件并保留已有轨迹；文件不会被擅自回滚。
- 关联需求点：取消事实记录、无自动回滚。

### Recovery and concurrency

#### CHK-019 Refresh during running activity

- 验证方法：turn 运行时刷新或重新打开聊天。
- 预期结果：恢复已有工具卡片及最新状态，不重复事件；后续实时事件继续追加到正确 item。
- 关联需求点：完整轨迹跨刷新恢复。

#### CHK-020 Refresh during pending approval or input

- 验证方法：在等待审批和等待回答时刷新。
- 预期结果：自动恢复并突出待处理卡片，仍可完成原请求；Codex 状态明确为等待用户而非普通 working。
- 关联需求点：待处理交互恢复。

#### CHK-021 Service restart reconciliation

- 验证方法：在已完成轨迹和可控的待处理场景下重启 Virtual Office。
- 预期结果：通过持久化和 thread read 恢复一致历史；无法恢复的挂起请求明确终止，不显示虚假可操作按钮。
- 关联需求点：持久状态、故障恢复。

#### CHK-022 Single active operation and active-chat navigation

- 验证方法：一个 conversation 运行时从另一个窗口或 conversation 发送消息。
- 预期结果：第二个请求被拒绝；界面说明活动任务所在 conversation，并可跳转；不自动切换或创建并行 turn。
- 关联需求点：单活动任务、多窗口可理解性。

### Terminal paths and compatibility

#### CHK-024 Terminal cleanup matrix

- 验证方法：覆盖 completed、failed、timeout、cancelled、rejected、bridge unavailable 和协议错误。
- 预期结果：每条路径都有唯一终态，锁释放，presence 恢复，pending action 清除，history 保留关联信息。
- 关联需求点：稳定生命周期与可观测性。

#### CHK-025 Demo and deterministic event mode

- 验证方法：不使用真实 Codex 账号运行合成活动、审批、回答和取消 fixtures。
- 预期结果：测试结果确定、可重复，不访问真实 thread 或凭据，覆盖 UI 与协议状态机。
- 关联需求点：自动化可测试性、Phase 5 demo 兼容。

#### CHK-026 Phase 5 regression

- 验证方法：重跑真实回复、上下文续聊/隔离、reset、compact、modified files、busy 和历史测试。
- 预期结果：Phase 5 已验收能力不回归；不支持实时事件的旧 history 仍正常显示。
- 关联需求点：向后兼容。

#### CHK-027 OpenClaw and Hermes regression

- 验证方法：验证两类 Agent 的聊天、工具卡片、presence、历史及双向 Codex 通信。
- 预期结果：既有渲染与路由不变；Agent-to-Codex 只有在需要交互时转为终止式人工介入。
- 关联需求点：其他 provider 不回归。

### Manual acceptance

#### CHK-028 End-to-end browser acceptance

- 验证方法：在浏览器完成实时轨迹、展开详情、允许一次、Codex 运行会话允许、补充回答、刷新恢复、跨窗口定位、取消和 reset 的完整流程。
- 预期结果：用户始终知道 Codex 正在做什么、是否等待自己、两种允许选择的真实范围、取消后遗留修改，以及如何返回活动会话；没有敏感信息泄露、虚假撤销承诺或隐藏队列。
- 关联需求点：Phase 6 主成功标准和次成功标准。
