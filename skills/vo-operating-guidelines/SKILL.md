---
name: vo-operating-guidelines
description: Virtual Office 中任意 CLI 或 agent 需要判断是否处于 VO 环境、选择正确 VO skill、遵守 VO 工作边界、决定普通沟通还是申请 AI 会议、或处理 VO 不可用降级时使用；作为 VO 运行时协作、项目创作与执行分流、通信、浏览器和会议申请的总入口准则。
---

# Virtual Office 工作准则

## 目标

作为 Virtual Office 的总入口准则，先判断当前是否在 VO 环境中，再根据任务意图路由到合适的 VO skill，并约束 AI 何时可以申请会议、何时必须降级或等待用户。

本 skill 不替代专用 VO skill；普通跨 agent 通信、浏览器状态、项目工作流、Agent workspace 和会议执行必须路由到对应 skill。

## 工作流

### 1. 探测 Virtual Office

优先使用当前运行环境或 `start.sh` 启动配置中的端口。`start.sh` 会加载 `.env` 并导出 `VO_PORT`，服务端按这个端口启动；因此不能因为 `127.0.0.1:8090` 不通就判断 VO 不可用。

当 agent 位于当前 VO/VU 的本地项目目录中，并需要访问本 skill 或任一专用 VO skill 提到的 HTTP 接口时，不需要获取、询问或暴露外部 Base URL。先读取当前进程的 `VO_PORT`；如果没有，再读取当前 VO 项目 `.env` 中的 `VO_PORT`，然后把 skill 中给出的接口路径拼到 `http://127.0.0.1:$VO_PORT`。例如接口路径是 `/api/agents`，本地完整地址就是 `http://127.0.0.1:${VO_PORT:-8090}/api/agents`。只有调用方明确不在当前 VO/VU 本地运行环境中时，才设置 `VO_REMOTE_CALLER=1` 并使用显式提供的 `VO_BASE_URL`；不要自行猜测或传播外部部署地址。

探测顺序：

1. 当前 VO/VU 本地运行环境中，如果有 `VO_PORT`，使用 `http://127.0.0.1:$VO_PORT`。
2. 如果能访问当前 VO 项目目录，读取其 `.env` 中的 `VO_PORT`，再拼成本地地址。
3. 如果调用方明确不在当前 VO/VU 本地运行环境中，设置 `VO_REMOTE_CALLER=1`；此时必须已有显式提供的 `VO_BASE_URL`，才使用该地址。
4. 本地场景最后才回退到 `http://127.0.0.1:8090`。测试环境可能使用 `8038`，但不要把它当作生产默认值。

```bash
if [ "${VO_REMOTE_CALLER:-0}" = "1" ]; then
  : "${VO_BASE_URL:?VO_BASE_URL is required for an explicitly remote caller}"
else
  VO_PROJECT_ROOT="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
  if [ -z "${VO_PORT:-}" ] && [ -f "$VO_PROJECT_ROOT/.env" ]; then
    VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$VO_PROJECT_ROOT/.env")"
  fi
  VO_BASE_URL="http://127.0.0.1:${VO_PORT:-8090}"
fi
curl -sS "$VO_BASE_URL/status"
curl -sS "$VO_BASE_URL/api/agents"
curl -sS "$VO_BASE_URL/api/projects"
```

如果按启动配置得到的地址不可用，不要立刻判定 VO 不可用；先报告尝试过的 `VO_BASE_URL`，再在没有明确 `VO_BASE_URL`/`VO_PORT` 的情况下尝试 `http://127.0.0.1:8038`。当接口返回 JSON，且 `/api/agents` 中存在 `agents` 列表时，基本可认为当前可访问 Virtual Office。

也可以辅助读取环境变量，但不要只依赖它们：

```bash
echo $VO_BASE_URL
echo $VO_PORT
echo $VO_STATUS_DIR
echo $VO_GATEWAY_HTTP
```

如果未检测到 VO，明确说明“当前未检测到 Virtual Office”，停止 VO 专属动作，并询问用户是否改用普通协作方式继续。

### 2. 路由到专用 VO Skill

根据任务意图选择：

- 普通跨 agent 沟通、提问、短任务委派、状态转交、复用 `conversationId`：使用 本地 `/skills/vo-agent-communication/SKILL.md`。
- 普通跨 agent 通信统一使用 本地 `/skills/vo-agent-communication/SKILL.md`，目标可以是 OpenClaw、Hermes、Claude Code、Codex 或其他已接入 provider。
- 需要检查 VO 共享浏览器状态、标签页或控制者，或浏览器访问遇到登录、权限、验证码、MFA、付费墙、网站拒绝自动化、支付/提交等人工介入阻塞：使用 本地 `/skills/vo-browser-control/SKILL.md`。当前 VO 没有 provider-neutral browser action endpoint，不能通过该 skill 执行点击、输入、导航或 DOM snapshot；人工介入场景应请求用户接管，不要升级为 raw CDP 操作。
- 用户明确调用 `$vo-project-authoring`，或自然语言要求创建、复用、周期化 VO 项目，或按 scoped grant 维护 Agent 创建的项目：使用 本地 `/skills/vo-project-authoring/SKILL.md`；该 skill 在对话中展示自然语言方案并等待明确确认，然后直接创建真实但未运行的项目。不要先用普通 Codex 流程读取本地项目文件、运行 Python、查询 `/api/projects` 或自行判断“已存在”。
- 需要读取或推进已创建项目/任务的 Project Execution、review、验收、阻塞、取消或项目 artifact：使用 本地 `/skills/vo-project-workflow/SKILL.md`。不要用项目创作 skill 绕过这些执行门禁。
- 需要读取或维护 Agent workspace、公告、workspace 任务、笔记、受控文本文件、Skills Library 或 OpenClaw agent skill：使用 本地 `/skills/vo-agent-workspace/SKILL.md`。
- 需要操作已确认的 executable meeting，包括 run/transition、事件跟踪、干预、冲突处理或 action item 草稿：使用 本地 `/skills/vo-meeting-execution/SKILL.md`。
- 需要正式 AI 会议申请、多方同步决策、用户确认会议上下文或产出明确会议结论：继续使用本 skill 的会议判断规则；确定需要申请时读取 [references/meeting-requests.md](references/meeting-requests.md)。

不要把本 skill 当成普通通信、浏览器、项目、workspace 或会议执行的完整手册；命中专用场景后应切换到对应 skill 的规则。

普通跨 agent 通信使用同一套聊天法则：先查询当前 agent 列表并识别目标的 `providerKind`，再通过统一 VO endpoint 路由。`providerKind=codex` 与其他 provider 一样不得使用 `sessions_send`、私人 CLI 或其他不可见通道，不再要求切换到另一份聊天 skill。

### 3. 决定是否申请会议

默认先使用普通沟通。只有满足以下条件之一时，才申请 AI 会议：

- 需要另一个 AI 独立评审、补充专业判断或比较方案。
- 需要多方同步决策，而不是单个 agent 的一次性回复。
- 需要形成明确会议产出，例如决策、执行方向、风险结论或下一步责任。
- 会议上下文需要用户确认选择，例如 `selectedContextIds` 或补充上下文。

不要申请会议的场景：

- 普通问答、简单澄清或单轮意见请求。
- 自己卡住但只需要用户输入；此时向用户提问。
- 可以通过 本地 `/skills/vo-agent-communication/SKILL.md` 完成的普通协作。
- 只是为了通知另一个 AI 或转交信息。

申请前必须说明 `goal`、`expectedOutcome` 和 `reason`。申请后停止等待用户处理，不要假设会议已经开始。

确定需要申请或查询 AI 会议时，读取 [references/meeting-requests.md](references/meeting-requests.md)，按其中流程识别参会者、提交请求、查询状态并处理用户控制面。

### 4. 用户控制面

AI 只能申请和查询会议请求，不要自行调用确认或拒绝接口。

自动推荐的上下文默认不会进入会议。只有用户确认时选择的 `selectedContextIds` 和补充的 `supplementalContext` 才会进入会议。

拒绝原因会写回来源任务评论，AI 后续可以在任务上下文里看到。不要绕过用户决定继续推进会议。

## 降级规则

- VO 不可用：说明当前未检测到 Virtual Office，停止 VO 专属动作，并询问是否改用普通协作方式。
- 浏览器页面需要登录、权限、验证码、MFA、付费授权或敏感操作：停止浏览器自动化，路由到 本地 `/skills/vo-browser-control/SKILL.md` 的用户接管流程；不要通过普通 agent 通信、AI 会议或 raw CDP 绕过用户介入。
- 会议申请失败：报告真实错误，不宣称已申请成功，不重复提交无幂等保障的请求。
- 无法确认项目或任务来源：说明当前会议接口只支持项目任务来源，向用户请求有效 `projectId` 和 `taskId`，或改用普通 agent 沟通。
- 参会者无法确认：停止申请，列出已发现的候选信息并要求用户确认，不猜测 ID。

## 质量检查

执行 VO 动作前确认：

- 已通过 HTTP 探测确认当前可访问 VO，或已明确降级。
- 已根据任务意图路由到正确 VO skill，没有用本 skill 替代专用通信、浏览器、项目、workspace 或会议执行规则。
- 普通通信已先识别目标 `providerKind`，并统一使用 本地 `/skills/vo-agent-communication/SKILL.md`。
- 普通协作已优先考虑专用通信 skill，会议只用于正式多方决策或需要用户确认上下文的场景。
- 明确的项目创作/受控维护与项目执行/review/验收已分别路由到 本地 `/skills/vo-project-authoring/SKILL.md` 和 本地 `/skills/vo-project-workflow/SKILL.md`。
- Agent workspace、已确认会议执行已分别路由到 本地 `/skills/vo-agent-workspace/SKILL.md`、本地 `/skills/vo-meeting-execution/SKILL.md`。
- 浏览器权限/登录/验证码/敏感操作阻塞已路由到 本地 `/skills/vo-browser-control/SKILL.md`，并已停止自动化或明确请求用户接管。
- 需要提交或查询会议申请时，已读取 [references/meeting-requests.md](references/meeting-requests.md)。
- 没有自行 confirm/reject 会议，也没有替用户选择最终会议上下文。
