# Phase4 Codex Harness MVP Checklist

确认状态：已确认

## Checklist

### CHK-001 Codex 协作者可见

- 关联需求点：Codex 作为首个非 Gateway agent 的 MVP 接入对象；办公室中具备稳定身份。
- 验证方法：启动应用后查看 agent 列表/办公室可视区域/相关 provider surface，确认 Codex 以可识别身份出现。
- 预期结果：用户能明确看到 Codex 协作者，并能区分其不是 OpenClaw 或 Hermes agent。

### CHK-002 Codex 状态可见

- 关联需求点：Codex 状态至少能表达 idle、working、error/needs attention。
- 验证方法：在空闲、协作处理中、失败或不可用场景分别观察 UI/API 状态。
- 预期结果：Codex 状态能被用户理解，不会静默失败或误显示为普通 OpenClaw 状态。

### CHK-003 用户可向 Codex 发起协作

- 关联需求点：用户能通过办公室与 Codex 发生一次可追踪协作。
- 验证方法：从 Virtual Office 的用户入口向 Codex 发送一条协作消息或任务意图。
- 预期结果：Codex 收到协作请求并产生回复、关键输出或明确失败原因。

### CHK-004 OpenClaw/Hermes 可与 Codex 发生可追踪协作

- 关联需求点：非 OpenClaw Codex agent 能与 OpenClaw/Hermes agent 完成一次可追踪协作。
- 验证方法：通过现有 agent-platform communication 或等价 office surface，让 OpenClaw 或 Hermes agent 向 Codex 发起一次协作。
- 预期结果：协作双方、消息意图、Codex 回复/关键输出被记录，用户能追踪完整上下文。

### CHK-005 协作事件流记录完整

- 关联需求点：事件流至少包含发起方、接收方、消息/任务意图、状态变化、关键输出、时间。
- 验证方法：完成一次协作后检查 UI 活动日志、聊天气泡、history endpoint 或等价追踪 surface。
- 预期结果：用户无需读取底层日志，也能理解这次协作是谁发起、给谁、要做什么、发生了什么、结果是什么。

### CHK-006 不误导为完整项目 worker

- 关联需求点：Codex 是可对话协作者，不是完整项目 worker；不做完整项目自动化。
- 验证方法：检查 UI 文案、按钮、状态、项目板入口和帮助说明。
- 预期结果：没有把 Codex 描述为可自动接项目板任务、自动跑 workflow 或进入 review 的完整项目 worker。

### CHK-007 项目自动化不进入 Phase 4 范围

- 关联需求点：本期非目标是不要求 Codex 自动接项目板任务。
- 验证方法：检查项目 workflow、自动模式和任务分配流程是否仍保持现有 OpenClaw/Hermes 约束或明确提示不可用。
- 预期结果：Phase 4 不引入 Codex 自动项目执行；如出现入口，必须是禁用或明确提示后续阶段。

### CHK-008 OpenClaw 回归验证

- 关联需求点：不影响现有 OpenClaw 原生体验。
- 验证方法：验证 OpenClaw agent discovery、状态更新、聊天、项目 workflow 的基本路径。
- 预期结果：OpenClaw 原有功能保持可用，行为不因 Codex MVP 发生回归。
- 环境依赖：需要本地可用 OpenClaw。若开发时暂未安装，标记为“待环境补齐”，进入回归测试阶段前提醒用户安装。

### CHK-009 Hermes 回归验证

- 关联需求点：不影响现有 Hermes adapter。
- 验证方法：验证 Hermes test/discovery、chat、history、create/delete 相关路径中至少核心路径仍可用。
- 预期结果：Hermes 仍作为 providerKind=hermes 的 agent 正常出现和交互。
- 环境依赖：需要本地可用 Hermes CLI 和 Hermes home。若开发时暂未安装，标记为“待环境补齐”，进入回归测试阶段前提醒用户安装。

### CHK-010 不可用或失败状态有提示

- 关联需求点：可观测性；用户能知道 Codex 是否可用以及失败原因。
- 验证方法：模拟 Codex 未配置、不可达、协作失败或被禁用场景。
- 预期结果：UI 或 API 返回可理解的不可用原因，不出现入口消失但无解释的情况。

### CHK-011 敏感信息不暴露

- 关联需求点：不暴露 Codex 原始凭据、私密配置或完整敏感日志。
- 验证方法：检查协作事件流、UI 展示、history/API 响应中是否包含凭据、环境变量、私密路径或无过滤底层日志。
- 预期结果：只展示用户需要理解的协作信息和关键输出，不泄露敏感信息。

### CHK-012 重启后的追踪数据表现合理

- 关联需求点：事件需要可追踪、可恢复、可被读取。
- 验证方法：完成一次协作后重启服务，再查看最近协作事件或历史入口。
- 预期结果：至少最近关键协作记录仍可被查看，或产品明确说明哪些事件是实时态、哪些是持久态。

### CHK-013 中文/英文提示可理解

- 关联需求点：用户能理解 Codex 身份、状态和不可用原因。
- 验证方法：分别切换中文和英文界面，检查 Codex 相关入口、状态、错误和协作事件文案。
- 预期结果：文案清楚表达“可对话协作者”“未配置/不可用/工作中”等状态，不出现误导或缺失。

### CHK-014 人工验收闭环

- 关联需求点：Phase 4 成功标准是一条可追踪协作闭环。
- 验证方法：人工执行一次完整验收：看到 Codex -> 发起协作 -> 观察状态变化 -> 查看关键输出 -> 查看事件流。
- 预期结果：人工能够确认 Phase 4 的核心价值成立，即 Codex 在办公室中可见、可对话、可追踪。

## 人工确认记录

- 确认项：checklist 初次确认
- 确认时间：2026-06-07T23:32:14+08:00
- 用户确认摘要：用户确认 checklist 没问题，可以进入 todolist 生成阶段。

## 测试环境分层

- 可立即执行：Codex/当前开发环境相关验证，包括 Codex 可见性、状态提示、协作入口、事件流结构、不可用提示、中文/英文文案、敏感信息展示边界。
- 待环境补齐：OpenClaw 回归验证（CHK-008）和 Hermes 回归验证（CHK-009）。
- 执行约定：进入回归测试阶段前，明确提醒用户安装或提供 OpenClaw/Hermes 最小可用环境；在环境未补齐前，不将 CHK-008/CHK-009 视为已通过。
