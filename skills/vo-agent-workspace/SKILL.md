---
name: vo-agent-workspace
description: Virtual Office 中任意 CLI 或 agent 需要读取或维护办公室 agent workspace、公告、任务、笔记、受控文本文件、技能库或 OpenClaw agent skill 时使用；必须确认当前 agent 身份和 providerKind，遵守 workspace 边界，OpenClaw-only 动作不得用于 Hermes、Codex 或 Claude Code。
---

# Virtual Office Agent Workspace

## 目标

通过当前 VO `agent-workspace` 和 Skills Library API 读取、维护 agent workspace 中的公告、任务、笔记、文件和技能。面向所有 VO agent，但部分文件/技能/heartbeat 动作只适用于 `providerKind=openclaw`。

如果任务是在判断是否处于 VO、选择哪个 VO skill，先使用 本地 `/skills/vo-operating-guidelines/SKILL.md`。

## 地址和身份

```bash
vo_project_root="${VO_PROJECT_ROOT:-$(git rev-parse --show-toplevel 2>/dev/null || pwd)}"
if [ -z "${VO_BASE_URL:-}" ] && [ -z "${VO_PORT:-}" ] && [ -f "$vo_project_root/.env" ]; then
  VO_PORT="$(awk -F= '$1=="VO_PORT"{print $2; exit}' "$vo_project_root/.env")"
fi
VO_BASE_URL="${VO_BASE_URL:-http://127.0.0.1:${VO_PORT:-8090}}"
curl -sS "$VO_BASE_URL/api/agents"
```

始终使用 `/api/agents` 当前返回的实际 `id`/`statusKey`。不要跨 agent 冒用身份或写入来源不明的 workspace。

## 读取 workspace

```bash
curl -sS "$VO_BASE_URL/api/agent-workspace/AGENT_ID"
```

响应包含 `agent`、`presence`、`workspace`、`files`、`skills`、`skillLibrary`、`projectTasks`、`activity`、`score` 和 `settings`。先检查 `settings.*Applicable` 再决定是否执行写操作。

## 可写动作

统一入口：

```bash
curl -sS -X POST "$VO_BASE_URL/api/agent-workspace/AGENT_ID" \
  -H 'Content-Type: application/json' \
  -d '{"action":"addNote","actor":"AGENT_ID","title":"Note","content":"..."}'
```

当前实现支持：

- 公告：`addBulletin`、`updateBulletin`、`deleteBulletin`
- workspace 任务：`addTask`、`updateTask`、`toggleTask`、`startTask`、`completeTask`、`deleteTask`、`setTaskMode`
- 笔记：`addNote`、`updateNote`、`deleteNote`
- 文本文件：`readFile`、`saveFile`、`createFile`、`deleteFile`
- 设置：`updateSettings`
- 技能库：`saveLibrarySkill`
- OpenClaw-only：`saveAgentSkill`、`deleteAgentSkill`、`applyLibrarySkill`、`saveAgentSkillToLibrary`、`heartbeatContent`

## Skills Library

可直接使用全局技能库接口：

```bash
curl -sS "$VO_BASE_URL/api/skills-library"
curl -sS "$VO_BASE_URL/api/skills-library/SKILL_NAME"
curl -sS -X POST "$VO_BASE_URL/api/skills-library/apply" \
  -H 'Content-Type: application/json' \
  -d '{"skill":"SKILL_NAME","agentId":"AGENT_ID","overwrite":true}'
```

应用到 agent workspace 前必须确认目标 agent 是 OpenClaw；当前实现对非 OpenClaw 返回 `Workspace skills are OpenClaw-only for this platform`。

## 安全规则

- 写入前确认目标 agent 身份、providerKind 和 `settings.*Applicable`。
- 不把 Codex/Hermes/Claude Code 当作 OpenClaw workspace skill 目标。
- `saveFile/createFile/deleteFile` 只用于 VO workspace 暴露的受控文本文件，不作为通用文件系统访问入口。
- 不写入密钥、token、认证配置或用户隐私数据。
- 删除公告、任务、笔记、文件、agent skill 前必须有明确用户要求。
- 需要跨 agent 沟通时使用通信 skill，不要用 workspace 留言替代实时沟通。

## 输出规则

报告目标 agent、执行的 action、VO 返回状态和可验证结果。写操作后重新读取 workspace 或相关资源确认。

## 质量检查

- 已查询 `/api/agents` 并确认目标 agent。
- 已读取 `/api/agent-workspace/<id>` 并检查适用性。
- 没有对非 OpenClaw agent 执行 OpenClaw-only 动作。
- 删除或覆盖前有明确授权。
- 写入后已验证 workspace 状态。
