# Phase 5 Codex Live Bridge Test Checklist

确认状态：已确认

## Functional acceptance

### CHK-001 Real human-to-Codex execution

- 验证方法：从 Virtual Office 以真人用户身份向已启用的 Codex collaborator 发送一个可单轮完成的仓库分析问题。
- 预期结果：请求进入真实 Codex turn，办公室显示 working，最终返回真实回复并恢复 idle；通信历史同时包含 request 与 reply。
- 关联需求点：真人用户首发路径、真实执行闭环、状态与历史可追溯。

### CHK-002 Localized workspace modification

- 验证方法：发送一个只修改绑定工作区内单个测试文件的短任务。
- 预期结果：Codex 完成修改；最终结果包含修改文件路径；路径同时由 Codex 文件事件产生，并可由 Git 前后状态对比验证。
- 关联需求点：工作区读写、局部代码修改、修改文件清单。

### CHK-003 Same-conversation context continuity

- 验证方法：在同一 `conversationId` 中先提供一个事实，再刷新页面并发送依赖该事实的后续问题。
- 预期结果：系统恢复原 Codex thread，后续回复使用已有上下文；刷新不创建新 thread。
- 关联需求点：同会话跨刷新保留上下文。

### CHK-004 Conversation isolation

- 验证方法：新建另一个办公室会话，并询问仅存在于原会话中的信息。
- 预期结果：新会话映射到不同 Codex thread，不能依赖原会话私有上下文。
- 关联需求点：不同会话上下文隔离。

### CHK-005 Reset context with clear/new conversation

- 验证方法：清空或新建当前聊天后，再发送依赖旧上下文的问题。
- 预期结果：旧映射被失效或删除，后续请求使用新 Codex thread；既有办公室历史按产品现有规则处理且不再驱动隐藏上下文。
- 关联需求点：显式重置上下文、避免可见历史与隐藏上下文不一致。

### CHK-006 Manual context compaction

- 验证方法：在已有多轮上下文的空闲会话中执行“压缩 Codex 上下文”，随后继续提问。
- 预期结果：调用映射 thread 的 `thread/compact/start`；显示 working 和最终成功状态；保留同一 `conversationId`、thread 映射和可见历史；后续消息仍可继续该会话。
- 关联需求点：新增上下文压缩操作、上下文持续性。

## Concurrency and lifecycle

### CHK-007 Reject a second message while busy

- 验证方法：保持一个 Codex turn 运行，再向同一 collaborator 发送第二条消息。
- 预期结果：第二条消息不进入队列、不成为 steering 输入，并以 busy/wait 结果立即结束；首个 turn 不受影响。
- 关联需求点：单活动 turn、忙碌时拒绝新消息。

### CHK-008 Compaction shares the busy lock

- 验证方法：分别在 turn 运行期间触发压缩，以及在压缩运行期间发送消息。
- 预期结果：后发操作均被 busy 规则拒绝；任一时刻只存在一个 Codex turn 或 compaction 操作。
- 关联需求点：单活动操作、压缩与执行互斥。

### CHK-009 Presence cleanup on all terminal paths

- 验证方法：分别触发成功、超时、bridge 错误和 approval-required 结果。
- 预期结果：每次 accepted 后显示 working；所有终态最终恢复 idle，不遗留虚假 busy 状态。
- 关联需求点：基本状态传播、异常状态恢复。

## Errors and human intervention

### CHK-010 Approval-required fails closed

- 验证方法：让 Codex 尝试需要越过当前沙箱或权限策略的操作。
- 预期结果：系统不自动批准；turn 终止并分类为 `needs_human_intervention`，历史包含安全、可理解的原因。
- 关联需求点：保持正常沙箱、授权请求终止并人工介入。

### CHK-011 Missing-information outcome

- 验证方法：发送一个缺少必要输入且无法安全假设的短任务。
- 预期结果：任务明确结束并说明需要补充的信息；不会伪装成成功或保持无限等待。
- 关联需求点：信息不足时明确结束。

### CHK-012 Timeout handling

- 验证方法：配置短测试超时并运行超过限制的 turn。
- 预期结果：请求以 timeout 终态结束，记录关联 ID 和安全错误信息，恢复 idle，锁可被下一请求正常获取。
- 关联需求点：超时传播、历史记录、锁释放。

### CHK-013 Bridge unavailable and protocol failure

- 验证方法：分别停止本地 bridge、配置不可达外部 URL、返回畸形或错误协议消息。
- 预期结果：返回 `bridge_unavailable` 或 `execution_failed` 类别，不写入伪造成功回复；服务保持可用且状态恢复。
- 关联需求点：桥接异常处理、明确失败。

### CHK-014 Invalid and unsupported requests

- 验证方法：发送空消息、未知 Codex agent、无有效 conversation 标识的非法请求，以及明确超出单轮短任务范围的请求。
- 预期结果：非法输入得到稳定 4xx/结构化错误；超范围任务明确结束，不进入长期编排。
- 关联需求点：输入边界、Phase 5/6 范围隔离。

## Data, security, and observability

### CHK-015 Durable conversation mapping

- 验证方法：创建会话映射，重启 Virtual Office 服务，再继续同一 `conversationId`。
- 预期结果：从 `VO_STATUS_DIR` 恢复正确 thread ID；映射文件损坏时安全失败，不误串其他会话。
- 关联需求点：跨刷新和服务重启的上下文持久化、会话隔离。

### CHK-016 Workspace boundary

- 验证方法：让 Codex 修改工作区内文件，并尝试写入工作区外路径。
- 预期结果：工作区内修改成功；工作区外写入不能被静默允许，并进入 approval-required/人工介入终态。
- 关联需求点：绑定工作区读写、安全边界。

### CHK-017 Correlation and safe logging

- 验证方法：检查一次成功和一次失败请求的服务日志与通信事件。
- 预期结果：可通过 request、conversation、thread、turn ID 关联完整链路；日志不包含认证令牌或其他凭据。
- 关联需求点：可观测性、安全日志。

### CHK-018 Structured history metadata

- 验证方法：读取通信历史接口和 JSONL 存储中的成功、busy、timeout、人工介入、压缩事件。
- 预期结果：事件保留现有文本兼容性，并包含终态、Codex 标识、修改文件和 intervention 标志等结构化元数据。
- 关联需求点：完整历史、状态与文件结果追溯。

## Compatibility and regression

### CHK-019 Deterministic demo mode

- 验证方法：设置 `VO_CODEX_REPLY_TEXT` 并在没有 live bridge 的环境运行现有 Codex provider 测试。
- 预期结果：确定性回复保持有效，不依赖 Codex 认证或进程；既有测试不回归。
- 关联需求点：保留 Phase 4 回归模式。

### CHK-020 No-bridge configured behavior

- 验证方法：启用 Codex，但不配置 demo reply、外部 URL，且使本地 bridge 无法启动。
- 预期结果：发现能力仍按约定呈现；发送时返回清晰的 bridge 未配置/不可用错误，不伪造回复。
- 关联需求点：现有无 bridge 错误兼容。

### CHK-021 OpenClaw and Hermes regression

- 验证方法：运行现有 OpenClaw、Hermes 和跨平台通信测试，并分别发送到非 Codex agent。
- 预期结果：路由、历史、presence 和回复行为不因 Codex bridge 改动而变化。
- 关联需求点：其他 provider 不回归。

### CHK-022 Agent-to-Codex compatibility

- 验证方法：分别由 OpenClaw 和 Hermes 向空闲 Codex collaborator 发送一个单轮消息。
- 预期结果：复用同一 live bridge 和事件模型并得到完整终态；该路径可用，但不要求新增专属 UI。
- 关联需求点：Agent 发送兼容范围。

## Manual acceptance

### CHK-023 End-to-end browser acceptance

- 验证方法：在浏览器中完成发送、观察 working、查看回复与修改文件、刷新续聊、压缩上下文、清空后重建会话的完整流程。
- 预期结果：用户可理解每一步当前状态与终态；没有隐藏排队、静默授权、上下文串线或页面刷新丢失。
- 关联需求点：Phase 5 用户体验与最终成功标准。

## 人工确认记录

- 确认项：Phase 5 Codex Live Bridge 测试 checklist
- 确认时间：2026-06-09T00:57:33+08:00
- 用户确认摘要：用户表示“我没问题，继续吧”，确认当前 checklist 无需修改并同意进入任务拆解。

## 测试执行记录

- 执行时间：2026-06-09T01:45:00+08:00
- 测试约束：所有 Virtual Office 服务与核心自动化测试均显式设置 `_VO_INT=1`，确认 `/api/license` 返回 `demo: false`。
- 已通过：CHK-001、CHK-002、CHK-003、CHK-005、CHK-006、CHK-007、CHK-009、CHK-010、CHK-012、CHK-015、CHK-017、CHK-019、CHK-023 的主要路径。
- 自动化通过：`tests/test_codex_bridge.py`、`tests/test_codex_server.py`、`tests/test_codex_provider.py`、`tests/test_review_parser.py`（16/16）。
- 静态检查通过：Python `py_compile`、`node --check app/chat.js`、`git diff --check`。
- 真实 Codex 验证：完成 app-server 回复、同 thread 续聊、HTTP 续聊、上下文压缩和测试工作区文件写入；浏览器完成发送、working/idle、刷新恢复、续聊、压缩和新会话操作。
- 部分覆盖：CHK-004、CHK-008、CHK-011、CHK-013、CHK-014、CHK-016、CHK-018、CHK-020。相关协议、映射、锁和错误分支已有自动化覆盖，但未逐项完成独立人工场景。
- 未执行：CHK-021、CHK-022。当前环境没有可用的 OpenClaw gateway，因此未完成 OpenClaw/Hermes 非 Codex 回归和 agent-to-Codex 实机发送。
- 受阻说明：浏览器执行“新会话后询问旧记忆”的最后一次真实请求时，Codex 账户触发用量上限；reset API 和映射删除已由自动化测试验证，但该条模型回复未取得。
- 未运行：`tests/test_workflow_e2e.py`。该脚本依赖活动中的 OpenClaw/项目服务并会创建、移动和删除项目，不属于本次隔离 Codex 验证范围。
- 当前结论：实现与核心验证完成，保留 `confirmed.tested=false`，等待补齐或接受上述残余验收项后再进行测试确认。

### 补充实机回归

- 执行时间：2026-06-09T05:35:15+08:00
- OpenClaw gateway：宿主机服务正常运行，版本 `2026.6.1`，监听 `127.0.0.1:18790`；Virtual Office `/api/gateway/test` 返回 `reachable` 且 token 有效。
- 原不可用原因：首轮 Codex 隔离测试显式设置了 `VO_OPENCLAW_PATH=/tmp/vo-no-openclaw`，同时 Codex 沙箱禁止直接探测宿主网络；并非宿主机 OpenClaw gateway 故障。
- CHK-004/CHK-005：真实 Codex 会话 B 返回 `ISOLATED`；会话 A reset 后新 thread 返回 `RESET CLEAN`。history 显示 reset 前后 `threadId` 不同。
- CHK-021：Codex 身份经统一通信层发送至 OpenClaw 与 Hermes，分别得到 `OPENCLAW REGRESSION OK` 和 `HERMES REGRESSION OK`，均为 `completed`。
- CHK-022：OpenClaw 与 Hermes 身份经统一通信层发送至真实 Codex，分别得到 `CODEX RECEIVED OPENCLAW` 和 `CODEX RECEIVED HERMES`，均为 `completed`。
- CHK-014：空消息返回 HTTP 400；未知 Codex agent 返回 HTTP 404。
- CHK-009/CHK-017/CHK-018：补充回归完成后 OpenClaw、Hermes、Codex presence 均为 `idle`；history 包含 conversation/thread/turn、duration、status 和 intervention 元数据。
- 更新结论：此前 OpenClaw/Hermes 与 post-reset 实机阻塞均已解除。未逐项实机复现的协议故障和越界授权分支仍由 focused automated tests 覆盖。

## 测试与交付确认记录

- 确认项：Phase 5 Codex Live Bridge checklist 测试结果
- 确认时间：2026-06-09T06:17:39+08:00
- 用户确认摘要：用户表示“我phase5验收好了”，确认 Phase 5 验收通过。

- 确认项：Phase 5 Codex Live Bridge 最终交付
- 确认时间：2026-06-09T06:17:39+08:00
- 用户确认摘要：用户要求标记需求状态，确认 Phase 5 可以完成闭环。
