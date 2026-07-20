---
name: vo-operating-guidelines
description: Virtual Office 引导入口。任意 CLI 或 agent 需要判断是否处于本地 VO/VU、按本地端口拼接 HTTP 地址、读取当前 VO 实例的权威 skill、选择通信/HR Agent 目录/项目/workspace/浏览器/会议工作流，或在 VO 不可达时安全降级时使用；不在主入口维护具体 VO API 细节。
---

# Virtual Office Skill 入口

## 目标

定位当前可访问的 Virtual Office，读取该实例提供的权威 skill 总入口，再按任务意图路由到合适的 VO skill。

本 skill 只负责发现、路由和降级。不要在主入口复制 VO 的具体 API、业务规则或专用工作流；普通跨 agent 通信、HR Agent 目录、浏览器状态、项目创作/执行、Agent workspace、会议申请和会议执行必须切换到当前实例暴露的对应 skill。

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
curl -sS "$VO_BASE_URL/skills/index.md"
```

如果按启动配置得到的地址不可用，不要立刻判定 VO 不可用；先报告尝试过的 `VO_BASE_URL`，再在没有明确 `VO_BASE_URL`/`VO_PORT` 的情况下尝试 `http://127.0.0.1:8038`。当 `/skills/index.md` 可读取时，基本可认为当前可访问 Virtual Office。

如果当前 provider runtime 访问 `127.0.0.1` 失败，不要传递显式的 `escalated`、`sandbox_permissions` 或类似提权参数；审批通道不接受这类显式参数。应继续发起同一条普通本机 `curl` 命令，并使用较短超时，让当前运行环境按策略决定是否产生审批。用户批准该普通命令后，VO 后端可以执行这条本机 HTTP 请求并把结果回传给 agent。注意：用户批准前，provider runtime 自己报 `Failed to connect to 127.0.0.1` 不是最终 VO 结果，只说明需要把同一条普通 curl 交给当前审批/命令通道处理；不要因此直接判定 VO 不可用。只有审批/命令通道接管后的普通 curl 被拒绝，或 VO 后端回传本机执行失败，才停止 VO 专属动作并报告真实错误。

不要把通用 VO 探测升级成业务数据探测。尤其在项目创作场景中，确认前不要调用 `/api/projects`、项目详情、创建、维护、执行或 review 接口；命中专用项目场景后，以当前实例 `/skills/vo-project-authoring/SKILL.md` 的阶段门禁为准。

也可以辅助读取环境变量，但不要只依赖它们：

```bash
echo $VO_BASE_URL
echo $VO_PORT
echo $VO_STATUS_DIR
echo $VO_GATEWAY_HTTP
```

如果未检测到 VO，明确说明“当前未检测到 Virtual Office”，停止 VO 专属动作，并询问用户是否改用普通协作方式继续。

### 2. 读取实例权威 Skill

完整读取当前实例返回的 `/skills/index.md`，再根据其中的路由说明读取所需专用 skill。以当前 VO 实例暴露的 `/skills/...` 内容为唯一权威来源。

不要使用 skill-manager 中的历史知识补全具体接口，也不要绕过当前实例定义的通信、项目、workspace、浏览器或会议边界。

### 3. 路由到专用 VO Skill

根据任务意图选择：

- 普通跨 agent 沟通、提问、短任务委派、状态转交、复用 `conversationId`：使用 本地 `/skills/vo-agent-communication/SKILL.md`。
- 普通跨 agent 通信统一使用 本地 `/skills/vo-agent-communication/SKILL.md`，目标可以是 OpenClaw、Hermes、Claude Code、Codex 或其他已接入 provider。
- 需要检查 VO 共享浏览器状态、标签页或控制者，或浏览器访问遇到登录、权限、验证码、MFA、付费墙、网站拒绝自动化、支付/提交等人工介入阻塞：使用 本地 `/skills/vo-browser-control/SKILL.md`。当前 VO 没有 provider-neutral browser action endpoint，不能通过该 skill 执行点击、输入、导航或 DOM snapshot；人工介入场景应请求用户接管，不要升级为 raw CDP 操作。
- 用户明确调用 `$vo-project-authoring`，或自然语言要求创建、复用、周期化 VO 项目，或维护已有 VO 项目：使用 本地 `/skills/vo-project-authoring/SKILL.md`；该 skill 在对话中展示自然语言方案并等待明确确认，然后直接创建或修改真实项目。不要先用普通 Codex 流程读取本地项目文件、运行 Python、查询 `/api/projects` 或自行判断“已存在”。
- 需要读取或推进已创建项目/任务的 Project Execution、review、验收、阻塞、取消或项目 artifact：使用 本地 `/skills/vo-project-workflow/SKILL.md`。不要用项目创作 skill 绕过这些执行门禁。
- 需要读取或维护 Agent workspace、公告、workspace 任务、笔记、受控文本文件、Skills Library 或 OpenClaw agent skill：使用 本地 `/skills/vo-agent-workspace/SKILL.md`。
- 需要查询 HR Agent 名册、区分 Agent 职责与可用性、读取另一 Agent 被允许公开的工作信息，或查看谁访问过自己的公开工作信息：使用 本地 `/skills/vo-agent-hr/SKILL.md`。
- 需要正式 AI 会议申请、多方同步决策、用户确认会议上下文或产出明确会议结论：先按下文“会议分流”判断；确定需要申请或查询时读取 [references/meeting-requests.md](references/meeting-requests.md)。
- 需要操作已确认的 executable meeting，包括 run/transition、事件跟踪、干预、冲突处理或 action item 草稿：使用 本地 `/skills/vo-meeting-execution/SKILL.md`。

不要把本 skill 当成普通通信、HR Agent 目录、浏览器、项目、workspace 或会议执行的完整手册；命中专用场景后应切换到对应 skill 的规则。

普通跨 agent 通信使用同一套聊天法则：先查询当前 agent 列表并识别目标的 `providerKind`，再通过统一 VO endpoint 路由。`providerKind=codex` 与其他 provider 一样不得使用 `sessions_send`、私人 CLI 或其他不可见通道，不再要求切换到另一份聊天 skill。

### 4. 会议分流

主入口只判断“是否需要会议”，不内联会议申请 API、确认/拒绝流程或会议上下文规则。默认先使用普通 agent 通信；只有满足以下条件之一时，才考虑正式 AI 会议：

- 需要另一个 AI 独立评审、补充专业判断或比较方案。
- 需要多方同步决策，而不是单个 agent 的一次性回复。
- 需要形成明确会议产出，例如决策、执行方向、风险结论或下一步责任。
- 会议上下文需要用户确认选择，例如 `selectedContextIds` 或补充上下文。

不要申请会议的场景：

- 普通问答、简单澄清或单轮意见请求。
- 自己卡住但只需要用户输入；此时向用户提问。
- 可以通过 本地 `/skills/vo-agent-communication/SKILL.md` 完成的普通协作。
- 只是为了通知另一个 AI 或转交信息。

确定需要申请或查询 AI 会议时，停止在本文件展开细节，读取 [references/meeting-requests.md](references/meeting-requests.md)。AI 只能申请和查询会议请求；不要自行调用确认或拒绝接口，不要替用户选择最终会议上下文。

## 用户确认优先级

普通单轮 agent 通信可以直接执行；但只要操作会改变 VO 项目结构、任务状态、会议状态或自动化策略，默认必须先让用户确认草案。

以下 VO 写操作必须先输出草案并等待用户明确确认：

- 创建、修改或删除项目。
- 创建、修改或删除模板。
- 批量创建任务，或创建任务链路 / 工作流 / 可复用流程。
- 提交可能影响项目状态的会议申请。
- 启动 Project Execution、workflow 或 meeting run。
- 设置自动批准、自动执行、定时任务、长期项目或可复用项目策略。

确认草案应说明目标对象、将要修改的结构/状态、涉及的 Agent 分工、是否会启动执行或会议、是否涉及自动化策略，以及不会修改的内容。只有用户明确说“确认/同意/按这个创建/按这个修改/可以启动”等等价语义后，才可调用对应写接口。

## 降级规则

- VO 不可用：说明当前未检测到 Virtual Office，停止 VO 专属动作，并询问是否改用普通协作方式。
- 浏览器页面需要登录、权限、验证码、MFA、付费授权或敏感操作：停止浏览器自动化，路由到 本地 `/skills/vo-browser-control/SKILL.md` 的用户接管流程；不要通过普通 agent 通信、AI 会议或 raw CDP 绕过用户介入。
- 会议申请失败：报告真实错误，不宣称已申请成功，不重复提交无幂等保障的请求。
- 无法确认项目或任务来源：说明当前会议接口只支持项目任务来源，向用户请求有效 `projectId` 和 `taskId`，或改用普通 agent 沟通。
- 参会者无法确认：停止申请，列出已发现的候选信息并要求用户确认，不猜测 ID。

## 质量检查

执行 VO 动作前确认：

- 已通过 HTTP 探测确认当前可访问 VO，或已明确降级。
- 已完整读取当前实例的 `/skills/index.md`。
- 已根据任务意图路由到正确 VO skill，没有用本 skill 替代专用通信、浏览器、项目、workspace 或会议执行规则。
- 会改变 VO 项目结构、任务状态、会议状态或自动化策略的写操作，已先展示草案并获得明确用户确认。
- 普通通信已先识别目标 `providerKind`，并统一使用 本地 `/skills/vo-agent-communication/SKILL.md`。
- 普通协作已优先考虑专用通信 skill，会议只用于正式多方决策、独立评审或需要用户确认上下文的场景。
- 明确的项目创作/受控维护与项目执行/review/验收已分别路由到 本地 `/skills/vo-project-authoring/SKILL.md` 和 本地 `/skills/vo-project-workflow/SKILL.md`。
- Agent workspace、HR Agent 能力、已确认会议执行已分别路由到 本地 `/skills/vo-agent-workspace/SKILL.md`、本地 `/skills/vo-agent-hr/SKILL.md`、本地 `/skills/vo-meeting-execution/SKILL.md`。
- 浏览器权限/登录/验证码/敏感操作阻塞已路由到 本地 `/skills/vo-browser-control/SKILL.md`，并已停止自动化或明确请求用户接管。
- 需要提交或查询会议申请时，已读取 [references/meeting-requests.md](references/meeting-requests.md)。
- 没有自行 confirm/reject 会议，也没有替用户选择最终会议上下文。
