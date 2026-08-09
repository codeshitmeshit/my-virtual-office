---
name: vo-personal-assets
description: Use when the owner explicitly asks to create, continue, correct, or append their Virtual Office personal asset profile through a guided conversation.
---

# VO 个人资产建档

## 核心原则

仅在 owner 明确手动调用时开始。通过对话逐步收集和追加个人资料；确认前零写入，未确认草稿不持久化。个人资产页只用于管理，不在页面启动建档引导。

## 对话状态

只在当前对话维护：

- `collectionDraft`：候选 create/update，包含精确 category/label/value。
- `skippedTopics`：owner 选择跳过的主题。
- `sensitivityByEntry`：每个候选条目的 `standard|sensitive`。
- `confirmedChanges`：owner 最后确认的精确变更集。
- `idempotencyKey`：同一变更集重试时保持不变；摘要改变时重新生成。

不将这些变量写入文件、workspace、项目或另一份 onboarding progress store。

## 执行流程

1. 按 `/skills/vo-operating-guidelines/SKILL.md` 确定当前本地 `VO_BASE_URL`、当前运行时 Agent ID 和对话 task context。个人资产不依赖 HR 名册；不要调用 HR 接口验证、注册或激活当前 Agent。
2. 调用 `POST /api/agent/personal-assets/profile-outline`，读取权威 revision 和已有目录。它不返回 value，sensitive label 已脱敏。不索取、读取、缓存或传递 `X-VO-Management-Token`。
3. 根据目录和 owner 目标，依次处理基本信息、职业与 VO 方向、兴趣、聊天偏好、办公室目标，以及 owner 主动选择的可选敏感项。基本信息必须遵循下方固定引导；其他主题一次只询问一个主题。允许回答、跳过、修正或停止；只允许按“确认前规范化”处理高置信度信息，不猜测低置信度缺失值。
4. owner 停止时，只将本轮已明确给出的候选项进入摘要；跳过项保留在 `skippedTopics`。后续手动调用时重新读取 outline 推导继续/追加范围。
5. 按“确认前规范化”整理候选项，再展示精确摘要：每项 create/update、label、owner 原始填写、规范化后的 value、推导补充及理由、sensitivity，以及所有 skips。原值与建议值相同时可省略原值。询问 owner 是否确认这一份完整变更集。
6. owner 修正时更新草稿并重新展示摘要；owner 取消时结束且零写入。
7. owner 明确确认后，将摘要中选定的变更固化为 `confirmedChanges`，用服务端相同的 canonical JSON（UTF-8、key 排序、紧凑分隔符、保留 Unicode）计算 SHA-256 `confirmationSummaryDigest`，再调用 `apply-confirmed-onboarding`。
8. 只报告返回的 revision 和实际保存 scope，不输出 token、完整敏感值日志或确认原文。`409` 后重新读 outline、重建摘要并重新请 owner 确认；不对旧 revision 静默重试。

## 确认前规范化

在生成确认摘要前规范化 owner 的简写，但不直接写入：

- 对不改变原意的高置信度简写，生成规范值。例如在上下文明确为简体中文时，将“中文”建议为“简体中文”；将时区字段中的“上海”或“北京时间”建议为 IANA 时区 `Asia/Shanghai`。
- 可从已填写内容推导高置信度的关联候选。例如 owner 填写所在地区“上海”且没有填写时区时，可新增“所在时区：`Asia/Shanghai`”候选，并标记为“根据所在地区推导”。所在地区本身仍保存为“上海”，不要用时区覆盖地区。
- 对有歧义的语言、地区、职业、偏好或目标，只给出可选建议，不自动进入 `confirmedChanges`。不要根据刻板印象扩写兴趣、职业或个人目标。
- 摘要必须区分“原始填写”“规范化建议”和“推导补充”，并说明简短理由。owner 可以逐项接受、修正或移除；最终 `confirmedChanges` 只能包含摘要中展示且由 owner 明确确认的规范值。
- 规范化不得降低或改变 sensitivity，不得把 sensitive classification 解释为读取授权。

## 基本信息引导

不要反问 owner 自己设计基本信息字段，也不要只问“你希望我记录哪些基本信息”。使用以下固定清单，每个字段作为 `basic-info` category 下的独立 entry，便于以后单独追加或修改：

1. `称呼`：owner 希望 Agent 如何称呼自己。
2. `常用语言`：对话默认使用的语言。
3. `所在时区`：用于时间、日程和提醒理解。
4. `当前职业或工作身份`：只记录 owner 自己给出的表述。
5. `所在地区`：可选，只询问国家、城市或宽泛地区，不主动索取精确地址。

默认采用逐项模式，一次只问一个字段。进入空 profile 的基本信息时，直接从“我应该如何称呼你？”开始；owner 回答后简短确认，再询问下一项，并始终允许回答“跳过”“修正”或“停止”。不要重复询问本轮已经回答的字段。结合 outline 中的已有 label，只询问缺失项；owner 明确要修改已有字段时才重新询问该字段的新值。

当 owner 说“一次填写”“全部列出来”“把基本信息全部拉出来”或同义表达时，切换为一次填写模式，在一条消息中展开上述完整清单和可复制的填写模板；仍允许逐项留空或写“跳过”。收到整表回复后，逐项解析到独立 entry，不把整段内容保存成单一的“基本信息”条目。

完成固定清单后，简短列出本轮已收集和跳过的基本信息，再进入下一个主题。称呼、语言、时区、职业身份和宽泛地区默认均为 `standard`；若 owner 主动要求将某项标为 `sensitive`，尊重该选择，但不得把它解释为后续读取授权。

## 飞书表单

当当前来源是 `feishu-dm` 或 `feishu-group` 时，不逐题发送消息。直接调用 `POST /api/agent/personal-assets/feishu-onboarding-form`，用一张完整表单收集本轮全部问题，并按类型分区：基本信息、职业与 VO 方向、兴趣爱好、聊天偏好、办公室目标，以及其他与可选敏感信息。所有字段允许留空；表单内不放读取授权开关。

请求沿用 Agent API headers，并传入当前 prompt 中的可信路由上下文：

```json
{
  "requestId": "<stable-form-request-id>",
  "expectedRevision": 0,
  "sourceContext": {
    "sourceApp": "feishu",
    "sourceSurface": "feishu-dm",
    "sourceMessageId": "<current-source-message-id>",
    "conversationId": "<current-conversation-id>",
    "feishuChatId": "<current-feishu-chat-id>",
    "chatType": "p2p",
    "ownerId": "<current-from-id>"
  }
}
```

只使用当前 provider prompt 已给出的 route values，不猜测 ID。接口返回 `form_delivered` 后，告诉 owner 在卡片中一次填写即可。卡片回调会把非空字段送回同一 Agent 对话并生成精确摘要；表单提交不等于确认写入。仍须 owner 明确确认摘要后，才能调用 `apply-confirmed-onboarding`。敏感字段只携带 `sensitive` classification；以后读取仍走 HUMAN DECISIONS。

卡片状态必须按 `待填写 → 处理中 → 已提交、等待确认` 转换。owner 提交后，处理中时锁定原表单并移除输入控件和提交按钮，防止重复提交；同一 Agent 先按“确认前规范化”修正和适度补全，再发送包含原始填写、规范值和推导项的确认摘要；摘要成功送达后显示“已提交、等待确认”。摘要生成或发送失败时显示失败状态，明确说明零写入并提示重新发起。状态更新只是展示层弱依赖，更新失败不得改变草稿和确认门禁。

## Agent API 契约

两个请求都使用无浏览器 `Origin` 的本机调用，并携带：

```http
Content-Type: application/json
X-VO-Agent-Action: personal-assets
X-VO-Agent-Id: <current-active-agent-id>
```

任意具备有效运行时 ID 的本地 VO Agent 均可调用这些写入接口，不依赖 HR 名册、HR 状态或职责同步。`X-VO-Agent-Id` 仅用于幂等、审计和敏感读取决策的 Agent scope，不是 HR 授权门禁。

Outline：

```json
{"requestId":"<stable-outline-request-id>","taskContext":{"type":"chat","id":"<conversation-id>","label":"个人资产建档"}}
```

Confirmed write：`POST /api/agent/personal-assets/apply-confirmed-onboarding`

```json
{
  "requestId": "<idempotencyKey>",
  "expectedRevision": 3,
  "confirmedChanges": [
    {
      "action": "create",
      "entry": {
        "category": "chat-preferences",
        "label": "聊天偏好",
        "value": "<owner-confirmed-value>",
        "sensitivity": "standard"
      }
    }
  ],
  "confirmationSummaryDigest": "<canonical confirmedChanges SHA-256>",
  "taskContext": {"type": "chat", "id": "<conversation-id>", "label": "个人资产建档"}
}
```

## 敏感信息边界

敏感 classification 不等于授权。建档时 owner 可以把新值标为 sensitive，但不因此为任何 Agent 创建 standing grant。以后任务中需要使用个人资产时，必须切换到 `/skills/vo-personal-context/SKILL.md`，由它使用精确 entry ID 调用 `request-context`；敏感读取再按 `/skills/vo-human-decision/SKILL.md` 进入 HUMAN DECISIONS。不把 profile outline、建档确认或 digest 解释为后续读取授权。

## Prompt 边界

本 Skill 默认直接使用当前 owner 对话，不需要额外 provider prompt。如果实现中确实要构造 provider-visible prompt，必须通过 `services.bridge_input_output_formatting` 传入 key-value 或 nested mapping，使用 XML 外层，并把 owner 回答、outline 和动态内容放入转义的 `untrusted` data boundary。禁止用裸字符串拼接动态内容。

## 常见错误

| 错误 | 正确做法 |
|---|---|
| 打开页面后自动开始提问 | 只响应 owner 手动调用 |
| 猜 revision 或用 management token 读完整 profile | 先读无 value `profile-outline` |
| 未确认就调用写入 | 展示精确摘要，确认后才写 |
| 修正摘要后沿用旧 digest/幂等键 | 为新变更集重新计算 |
| 把 sensitive 标记当成读取授权 | 后续读取仍走 HUMAN DECISIONS |
| 让 owner 自己想基本信息字段 | 使用固定清单，默认逐项询问；owner 要求时一次展开全部 |
| 飞书中连续发送逐题问答 | 发送一张按类型分区的完整表单 |
| 把卡片提交当成最终确认 | 卡片只生成草稿摘要，仍等待明确确认 |
| 原样照抄“中文”“上海时区”等简写 | 确认前给出“简体中文”“Asia/Shanghai”等规范值，并展示原值与理由 |
| 从地区或职业随意扩写个人事实 | 只补充高置信度关联候选；有歧义时仅建议且不进入确认集 |
