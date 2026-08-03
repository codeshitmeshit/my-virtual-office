---
name: vo-human-decision
description: Use when a VO task, meeting, or chat execution reaches multiple reasonable choices that materially affect outcome, risk, scope, cost, or an irreversible action and the agent is not authorized to choose for the user.
---

# VO 人工决策

## 核心原则

只在 VO 无法安全代决时创建请求。只暂停受影响的执行分支；其他独立且安全的工作继续运行。普通澄清、可由既定规则推出的选择、或只有一个安全答案时不要使用本 Skill。

## 升级门槛

1. 先调查：使用可用工具、证据、既定规则和用户之前的选择消除普通执行不确定性；继续授权范围内可逆、低风险且不影响该选择的工作。
2. 调查后仍有两个或以上合理且实质不同的方案，且选择会影响结果、风险、范围、成本或不可逆动作时，检查自己是否有明确授权和足够置信度。
3. 没有授权或置信度不足时，必须使用本 Skill 创建人工决策；不要默默替用户选择，也不要用普通聊天提问代替决策中枢。
4. 仅有一个安全答案，或可通过继续读取、测试、验证解决时，不要升级。一般“禁止询问用户”的执行指令不阻止本 Skill；人工决策是处理重大未授权取舍的专用例外。

## 执行流程

1. 读取当前 VO 的 `/skills/index.md` 并按其中规则确定 `VO_BASE_URL`。
2. 准备真实的 A、B、C、D 四个互斥选项；每项说明影响。指定一个 VO 推荐项并给出理由。
3. 使用稳定的 `idempotencyKey` 创建请求。`source.type` 必须为 `task`、`meeting` 或 `chat`，并带来源 ID 和可读名称。聊天来源的 `source.id` 必须使用当前 Prompt `<conversation_context>` 中的 `conversation_id`；会议使用真实 `meetingId`；项目任务使用真实 `taskId` 作为 `source.id` 并同时填写 `source.projectId`。不得生成新的来源 ID。
4. 告知当前执行链：决策 ID、受影响分支已等待、仍继续的安全工作。不要因为等待决策而结束整个项目或干预无关分支。
5. 任意来源创建成功后，结束当前 turn（只结束受影响分支）；不要轮询。VO 后端会在决策完成后自动唤醒原 conversation、会议生命周期或项目 task attempt。所有来源都以 `resolution.answer` 为唯一最终答案。
6. 在继续受影响分支前，调用 `POST /api/agent/human-decisions/{id}/execution-started` 并提交 `{"impact":"已经开始且可能影响修改的动作"}`。使用与创建相同的 Agent 请求头；成功后再执行决定。

创建接口会优先向通知机器人发送飞书卡片；通知机器人未配置时由 VO 降级到聊天机器人的回退会话。本地控制面板与飞书共用同一权威状态。

## 请求契约

```json
{
  "idempotencyKey": "task:release-42:rollout-scope",
  "source": {"type": "task", "id": "release-42", "projectId": "project-control-panel", "label": "控制面板发布"},
  "title": "选择上线范围",
  "situation": "自测完成，需要确定首批用户范围。",
  "reason": "不同范围代表不同业务风险，VO 无权代替用户选择。",
  "risk": "medium",
  "urgency": "urgent",
  "deadlineAt": "2026-08-04T10:00:00+08:00",
  "timeoutConsequence": "三次提醒后按已声明的安全策略处理。",
  "options": [
    {"id": "A", "label": "立即全量", "impact": "最快，影响面最大"},
    {"id": "B", "label": "分阶段灰度", "impact": "先验证再扩大"},
    {"id": "C", "label": "仅内部试用", "impact": "风险最低，外部验证延后"},
    {"id": "D", "label": "暂缓", "impact": "不增加风险，分支继续等待"}
  ],
  "recommendation": {"optionId": "B", "reason": "兼顾窗口与回滚能力。"},
  "taskDetail": {"summary": "发布新版控制面板", "blocked": "等待上线范围", "nextStep": "创建发布批次"}
}
```

Agent 使用 `POST /api/agent/human-decisions`，请求头必须包含 `Content-Type: application/json`、`X-VO-Agent-Action: human-decision` 和当前 `X-VO-Agent-Id`。该写入口只接受无浏览器 Origin 的本机调用。重复调用必须复用同一 `idempotencyKey`。本地控制面板使用受管理令牌保护的 `/api/human-decisions/{id}/resolve`，不要由 Agent 伪造用户答案。

## 判定规则

- 用户同时选择 A、B、C、D 之一并填写自定义输入时，以非空自定义输入为准。
- 相同终态重试视为幂等成功；不同答案的后续提交是冲突，绝不覆盖首个有效终态。
- 执行开始前可通过 `POST /api/human-decisions/{id}/reopen` 修改；执行开始后创建新的变更决策，不改写旧决定。
- 最多提醒三次。低风险事项可按请求中已明确的推荐策略继续；高风险事项继续等待，其他安全分支照常运行。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| 用四个措辞不同但实质相同的选项凑 A-D | 提供四个真实、互斥且影响不同的选择 |
| 创建请求后继续执行受影响分支 | 等待权威 `resolution` |
| 在任务、会议、聊天各维护一套决策状态 | 始终调用同一 `/api/human-decisions` |
| 飞书或本地先提交后再覆盖结果 | 接受首个有效终态，冲突时保留原结果 |
