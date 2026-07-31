---
name: vo-agent-communication
description: 任意 CLI 或 agent 需要通过 Virtual Office 联系 OpenClaw、Hermes、Claude Code、Codex 或其他办公室 Agent 时使用；查询实际 Agent ID 和 providerKind，通过统一通信 API 提问、委派任务、转交信息或复用 conversationId 延续跨平台会话，并返回可在 history 中追踪的真实响应。
---

# Virtual Office Agent 通信

## 目标

通过 Virtual Office 与所有办公室 Agent 通信，包括 OpenClaw、Hermes、Claude Code、Codex 等 provider，确保请求、回复和状态均可在 Virtual Office history 中追踪。

如果任务是在判断是否处于 VO、选择哪个 VO skill、或决定普通沟通是否应升级为正式 AI 会议，先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。本技能处理已确定要进行的普通跨 agent 通信，不按目标 provider 拆分聊天法则。

## 核心规则

与办公室 Agent 通信时，必须调用：

```text
POST /api/agent-platform-communications/send
```

不要：

- 直接调用 OpenClaw 私有 session。
- 使用 `sessions_list`、`sessions_send`、`openclaw agents` 或等价的 provider-private 发现/消息路径完成办公室 Agent 通信。
- 直接执行 Hermes、Claude Code CLI 或其他目标平台的私人 CLI。
- 绕过 Virtual Office 建立不可见通信。
- 把目标 Agent 当成本地 Codex subagent。
- 猜测、补全或复用未确认的 Agent ID。
- 传输凭据、密钥或敏感配置。

## 原通道进度告知

当你是从用户交互通道收到请求，并且需要通过本技能联系其他 VO Agent 时，无论这次沟通是否很快，都必须先沿原始交互通道发送一条简短进度告知，再继续调用 VO 通信 API。用户必须能看出最终结论是在 Agent 交互之后得到的。

- 需要询问其他 VO Agent “之前做了什么”、查询对方状态、读取对方历史或等待对方回复。
- 需要长时间调控、分阶段协调、跨 VO 通信或可能超过一次普通短问答的处理时间。
- 已经决定把消息发送给另一个 Agent，即使预计很快拿到结果。

告知内容要短，只说明“我会去问/已发送给目标 Agent，请稍等”或同等意思；不要提前编造目标 Agent 的结果。只有完全不涉及其他 Agent 交互的本地快速回复，才不需要发送这条进度告知。

如果运行环境提供了原始来源信息，例如 `sourceApp=feishu`、`sourceSurface=feishu-dm/feishu-group`、`sourceMessageId`、`conversationId`、`feishuChatId` 或当前聊天窗口上下文，应优先使用同一个来源通道回复这条进度告知；不要改发到无关会话、默认群或 provider 私有通道。

当 `sourceApp=feishu` 且 `feishuChatId` 存在时，这不是可选文字规则，而是可执行步骤：必须先调用 `POST /api/feishu-chat/original-channel-notice` 发送进度告知，再继续调用 `/api/agent-platform-communications/send` 联系其他 Agent。该 endpoint 是 Virtual Office 通用能力，不属于 Codex 私有工具；OpenClaw、Hermes、Claude Code、Codex 等 provider 只要能访问当前 VO HTTP 地址，都按同一规则使用。

请求体：

```json
{
  "sourceApp": "feishu",
  "sourceSurface": "feishu-dm",
  "sourceMessageId": "<来自 prompt/source context 的原飞书消息 id>",
  "conversationId": "<来自 prompt/source context 的 VO 会话 id>",
  "feishuChatId": "<来自 prompt/source context 的原飞书 chat id>",
  "chatType": "p2p",
  "text": "我去问分析师，请稍等。"
}
```

群聊时 `sourceSurface` 应为 `feishu-group`，`chatType` 应为 `group`，并且必须带 `sourceMessageId`，这样 VO 会回复到原群消息。不要猜测或手填 `feishuChatId` 或 `conversationId`；如果 prompt/source context 没有 `feishuChatId`，不要假装已通知飞书，应报告或记录 `missing_feishu_chat_id`，然后再按任务需要继续或停止。

没有可用原通道发送能力时，跳过进度告知，并在最终回复中说明已完成或遇到的阻塞。

### 必须拆成两条消息的示例

用户问：“问问分析师他现在有哪些 skill?”

正确行为：

1. 先在用户原来的聊天通道发送：“我去问分析师他当前有哪些 skill，请稍等。”
2. 如果原通道是飞书，并且 source context 含有 `feishuChatId`，先调用 `/api/feishu-chat/original-channel-notice` 发送上面的进度告知。
3. 再调用 `/api/agent-platform-communications/send` 联系分析师。
4. 收到分析师回复后，再在原来的聊天通道发送最终结果：“分析师回复了，他现在有这些 skills: ...”

错误行为：

- 直接调用目标 Agent 后，只发送一条最终回复：“问到了。分析师当前可用的 skills 有: ...”
- 在最终回复开头补一句“问到了”或“已询问”，但没有提前发送独立的原通道进度告知。
- 因为目标 Agent 回复很快，就省略进度告知。

更多必须先告知的场景：

- 用户说：“问问 Hermes 对这个方案怎么看。”
- 用户说：“让 Claude Code 看一下这个错误原因。”
- 用户说：“问问 main 之前做了什么。”
- 用户说：“把这段信息转给 analyst，然后告诉我他的回复。”

这些场景即使可以很快完成，也必须先发送独立的进度告知消息；最终答案不能替代进度告知。

## 通信工作流

### 1. 确定 Virtual Office 地址

优先使用当前运行环境或 `start.sh` 启动配置中的端口。`start.sh` 会加载 `.env` 并导出 `VO_PORT`，服务端按这个端口启动；不要只探测 `8090`。

```bash
vo_project_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f "$vo_project_root/.env" ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_project_root/.env")"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
```

如果调用方位于另一台机器，使用其能够访问的 Virtual Office 地址，不要假设远程调用方的 `127.0.0.1` 指向 Virtual Office 所在主机。

### 2. 查询并确认 Agent

发送消息前查询 Agent 列表：

```bash
curl -sS "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agents"
```

常见 ID 包括：

- `main`：OpenClaw 默认 Agent。
- `hermes-default`：Hermes 默认 Agent。
- `claude-code-local`：Claude Code 本地 Agent。
- `codex-local`：Codex 协作者，同样通过本技能的统一 VO 通信 endpoint 联系。

始终以 `/api/agents` 当前返回的实际 ID 和 provider 信息为准，不要把常见 ID 当作存在性证明。

同时确认 `fromAgentId` 是调用方在 Virtual Office 中的实际身份。不要冒用其他 Agent 的 ID。

按以下规则处理目标：

- 唯一匹配：使用返回的实际 ID。
- 多个可能目标：停止发送，列出候选项并要求用户明确选择。
- 目标不存在：报告不可用并停止，不自动转交给 `main` 或其他替代 Agent。
- 目标为 `codex-local` 或 `providerKind=codex`：继续使用本流程和同一 VO 通信 endpoint，不启动私人 Codex CLI 或 OpenClaw session。
- 无法确认发送方身份：报告缺失信息并停止。

### 2.1 查询目标 Agent 的 skill 清单

当用户要求“问某个 Agent 现在有哪些 skill”、“系统侧能看到哪些 skill”、“已安装和当前会话可用 skill 是否一致”时，必须把问题写成可验证的系统自检任务，而不是让目标 Agent 凭当前提示上下文自由自报。

消息必须要求目标 Agent：

- 区分“provider 原生已安装/可发现的 skill”与“当前会话 prompt 中显式出现的指令片段”。
- 以实际 skill 目录、provider 自带 skill 列表命令、或 VO 暴露的 workspace/skills API 返回为准；不要仅凭模型记忆、当前上下文里出现过的 skill 名称、或历史会话结论回答。
- 如果只能看到部分 skill，必须说明这是“当前上下文可见范围”，不能说成“系统只安装了这些”。
- 如果发现数量不一致，必须列出核验来源、完整已安装列表、当前上下文可见列表和缺失项。
- 不要使用或传播 `vo_synced_skills`、`MAX_PROMPT_SKILLS`、`当前注入 12 个` 这类已废弃 VO prompt 注入模型作为事实依据，除非它能在当前运行代码或当前 provider 日志中被重新验证。

推荐消息模板：

```text
请自检你当前系统侧能看到哪些 skill。请不要只按当前对话上下文自报。
请分别返回：
1. provider 原生已安装/可发现的 skill 清单及核验来源；
2. 当前会话 prompt 中显式可见的 skill/指令片段，如果无法直接核验请说明；
3. 两者是否一致，若不一致列出缺失项；
4. 不要把旧的 VO synced prompt 注入上限或历史会话结论当作当前事实。
```

### 3. 选择 Conversation ID

需要延续上下文时，复用相同的 `conversationId`：

```text
codex__main__project-alpha
```

需要隔离任务时，创建新的稳定 ID：

```text
codex__main__bug-123
codex__main__release-review
```

ID 应表达发送方、接收方和业务主题。不要在同一任务或业务会话中频繁更换 ID。

### 4. 发送消息

向 OpenClaw `main` 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "main",
    "conversationId": "codex__main__general",
    "message": "请检查当前 OpenClaw 服务状态，并简要返回结果。",
    "metadata": {
      "topic": "service-status"
    }
  }'
```

向 Hermes 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "hermes-default",
    "conversationId": "codex__hermes__review",
    "message": "请从产品角度评审这个方案，并指出两个主要风险。"
  }'
```

向 Claude Code 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "codex-local",
    "toAgentId": "claude-code-local",
    "conversationId": "codex__claude-code__review",
    "message": "请从实现角度评审这个改动，并只返回高风险问题。"
  }'
```

向 Codex 发送消息：

```bash
curl -sS \
  -X POST "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/send" \
  -H 'Content-Type: application/json' \
  -d '{
    "fromAgentId": "main",
    "toAgentId": "codex-local",
    "conversationId": "main__codex__review",
    "message": "请评审当前方案并返回高风险问题。"
  }'
```

示例中的 `fromAgentId` 仅用于展示对应发送方。实际调用方必须替换为自己经确认的 Virtual Office Agent ID，不得冒用 `main`、`codex-local` 或其他 Agent。

消息应包含明确目标、必要上下文、任务边界和期望输出。默认委派短任务；复杂任务可以发送，但应提示超时和协调风险，不要将本技能用于长期项目编排。

### 5. 处理响应

成功响应通常包含：

```json
{
  "ok": true,
  "conversationId": "codex__main__general",
  "reply": "服务当前运行正常。",
  "status": "completed",
  "modifiedFiles": [],
  "needsHumanIntervention": false
}
```

按以下规则处理：

- `ok=false`：明确报告通信失败和实际错误，不宣称任务成功。
- `status=completed` 且 `reply` 非空：返回目标 Agent 的真实回复。
- `status=busy`：报告忙碌并停止，不自动重试或并发发送。
- `status=timeout`：报告结果未知，不推定成功或失败，不自动重发。
- `reply` 为空：报告未获得有效回复，不把空回复解释为成功。
- `needsHumanIntervention=true`：停止自动执行并通知用户介入。
- 未识别状态：原样报告关键响应字段，不伪造目标 Agent 的回复。

### 6. 按需查询历史

需要确认既有通信或结果时，按 `conversationId` 查询：

```bash
curl -sS \
  "${VO_BASE_URL:-http://127.0.0.1:8090}/api/agent-platform-communications/history?conversationId=codex__main__general"
```

不要使用 history 中的旧 Agent ID 替代当前 `/api/agents` 检查。

## 任务边界

适合：

- 提问和获取意见。
- 短任务委派。
- 代码或产品评审请求。
- 状态查询和信息转交。
- 单轮协作或复用稳定会话的少量后续沟通。

不适合：

- 高频并发对话。
- 无限自主 Agent 循环。
- 长期项目编排。
- 正式 AI 会议申请、多方同步决策或需要用户确认会议上下文的场景；这类场景先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。
- 绕过人工授权的操作。
- 传输凭据或敏感配置。

## 质量检查

发送前确认：

- 已使用当前可访问的 Virtual Office 地址。
- 已查询 `/api/agents` 并确认发送方和唯一目标的实际 ID。
- 已确认目标的实际 `providerKind`，包括目标为 Codex 的情况。
- 没有使用目标平台的私有 session、CLI 或本地 subagent 绕过 Virtual Office。
- 延续任务复用了原 `conversationId`，隔离任务使用了新的稳定 ID。
- 消息范围清晰，且不包含凭据或敏感配置。

收到响应后确认：

- 已检查 `ok`、`status`、`reply` 和 `needsHumanIntervention`。
- 返回的是目标 Agent 的真实响应，没有自行补写或伪造。
- `busy`、`timeout` 和空回复均未被解释为成功。
- 通信使用的 `conversationId` 可用于查询 Virtual Office history。
