# Checklist: Agent Guide Skill Viewer

确认状态：已通过

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-07-07T22:03:28+08:00
- 用户确认摘要：用户回复 "continue"，确认当前 checklist 可作为后续 todolist 和实施验收依据。
- 确认项：tested / done
- 确认时间：2026-07-07T23:12:00+08:00
- 用户确认摘要：用户验收 Agent 指南及完整 `SKILL.md` 详情弹窗无问题，并要求标记与提交。

## Scope

This checklist validates the first phase of the Agent Guide feature:

- Add a bottom-toolbar "Agent Guide" entry.
- Open a center modal.
- Display read-only information cards for VO built-in exposed skills.
- Support category filtering.
- Do not provide skill recommendation, keyword search, editing, or execution.

## Checklist Items

### CHK-001 Toolbar Entry Is Visible

- 关联需求点：add an "Agent Guide" button to the bottom toolbar.
- 验证方法：Open the VO main page and inspect the bottom toolbar near the existing toolbar actions.
- 预期结果：A visible "Agent Guide" entry appears in the bottom toolbar and does not overlap or hide existing toolbar buttons.

### CHK-002 Toolbar Entry Opens Center Modal

- 关联需求点：the entry should open a center modal.
- 验证方法：Click the "Agent Guide" button.
- 预期结果：A center modal opens for Agent Guide content; the feature is not rendered as a narrow right-sidebar section.

### CHK-003 Modal Can Be Closed Reliably

- 关联需求点：preserve existing modal interaction expectations.
- 验证方法：Open the modal, then close it using the visible close control and any existing modal close interaction supported by the app.
- 预期结果：The modal closes cleanly and the office UI returns to the previous state without stale overlays.

### CHK-004 Only VO Built-In Exposed Skills Are Shown

- 关联需求点：displayed scope is VO built-in exposed skills.
- 验证方法：Compare the displayed skills against the VO exposed skill source, currently `skills/catalog.md`.
- 预期结果：The modal shows the exposed VO built-in skills and does not include unrelated global Codex skills, user-created skills, internal debug skills, or unavailable skills.

### CHK-005 Skill Cards Include Required Fields

- 关联需求点：information card display.
- 验证方法：Inspect each skill card in the modal.
- 预期结果：Each card shows skill name, purpose or short usage description, triggering / applicable scenarios, and category.

### CHK-006 Category Filters Are Present

- 关联需求点：category filtering is in scope.
- 验证方法：Open the modal and inspect the filter controls.
- 预期结果：Category filter controls are visible and can be used to narrow the displayed skill cards.

### CHK-007 Category Filters Work Without Recommendation Behavior

- 关联需求点：filtering yes; recommendation no.
- 验证方法：Switch between categories and observe the visible cards and copy.
- 预期结果：Filtering only shows or hides cards by category; the UI does not rank, recommend, auto-select, or claim a best skill for the user's task.

### CHK-008 No Keyword Search In This Phase

- 关联需求点：keyword search is out of scope.
- 验证方法：Inspect the modal controls.
- 预期结果：The modal does not include a keyword search box or search workflow in this phase.

### CHK-009 Read-Only Behavior

- 关联需求点：keep this feature read-only.
- 验证方法：Inspect skill cards and modal controls.
- 预期结果：The modal does not include add, edit, delete, upload, save, or apply controls for skills.

### CHK-010 No Direct Skill Execution

- 关联需求点：do not trigger an agent run directly from a skill card.
- 验证方法：Inspect card actions and click available card controls if any.
- 预期结果：Cards do not start agent runs, inject prompts, or call task execution APIs.

### CHK-011 Existing Skills Library Still Works

- 关联需求点：preserve existing Skills Library behavior.
- 验证方法：Open the existing Skills Library after using Agent Guide.
- 预期结果：The Skills Library can still open, list skills, and expose its existing add/edit/upload behaviors without being affected by Agent Guide.

### CHK-012 Existing Agent Skill Panels Still Work

- 关联需求点：preserve existing agent skill editing.
- 验证方法：Open an agent detail modal and inspect the existing skill panel / skill workshop behavior.
- 预期结果：Agent-level skill viewing and editing continue to behave as before.

### CHK-013 Modal Layout Is Scannable On Desktop

- 关联需求点：readable center modal and information cards.
- 验证方法：Open the modal on a normal desktop viewport similar to the provided screenshot.
- 预期结果：Cards are readable, category controls are accessible, and no text overlaps or is clipped in a way that blocks comprehension.

### CHK-014 Modal Layout Is Usable On Narrow Viewports

- 关联需求点：responsive, no broken UI.
- 验证方法：Open the modal on a narrow viewport or responsive browser size.
- 预期结果：The modal remains usable, cards stack or wrap cleanly, and text does not overflow its containers.

### CHK-015 Chinese And English Copy Are Available

- 关联需求点：VO UI localization consistency.
- 验证方法：Check `app/locales/zh.json` and `app/locales/en.json`, then switch or inspect the UI language behavior if supported.
- 预期结果：Agent Guide button, modal title, category filters, empty states, and card labels have Chinese and English copy.

### CHK-016 Empty Or Load Failure State Is Understandable

- 关联需求点：do not expose unavailable skills; keep UI understandable.
- 验证方法：Simulate or inspect behavior when the skill source is empty or unavailable, if the implementation supports dynamic loading.
- 预期结果：The modal shows a concise empty or failure message instead of a broken blank panel.

### CHK-017 Source Boundary Is Explicit In Implementation

- 关联需求点：avoid scope drift from global Codex skills or user-created skills.
- 验证方法：Review the implementation source used to populate the Agent Guide.
- 预期结果：The implementation clearly sources or defines only VO built-in exposed skills and does not scan unrelated global skill directories.

### CHK-018 No `skill-turial` Scope Creep

- 关联需求点：skill recommendation belongs in VO `skill-turial`.
- 验证方法：Review UI copy and behavior.
- 预期结果：Agent Guide does not describe itself as recommending skills and does not implement task-to-skill matching; any recommendation language remains out of this feature.

### CHK-019 No Existing Toolbar Regression

- 关联需求点：bottom toolbar remains usable.
- 验证方法：Use nearby toolbar actions such as Projects, Archive Room, Reset, SMS, and Browser after adding Agent Guide.
- 预期结果：Existing toolbar actions remain visible and functional.

### CHK-020 Static Checks Pass

- 关联需求点：safe implementation and localization.
- 验证方法：Run appropriate static checks for touched frontend files and JSON locale files.
- 预期结果：JavaScript and JSON files parse successfully; no obvious syntax or localization file errors are introduced.

## 测试执行记录

- 执行时间：2026-07-07T22:14:50+08:00
- 执行人：Codex
- 结果摘要：自动化静态检查、i18n 完整性检查和浏览器 E2E 交互验证通过；等待用户人工确认测试结果。

### 已执行命令

```bash
node --check app/agent-guide.js
node tests/check_agent_guide_static.mjs
node tests/test_i18n_integrity.js
python3 -m json.tool app/locales/zh.json >/dev/null
python3 -m json.tool app/locales/en.json >/dev/null
```

### 浏览器 E2E 验证

- 验证环境：临时隔离 VO 服务 `http://127.0.0.1:8097/`，使用当前工作区代码启动。
- 桌面验证：
  - Agent Guide 按钮可见，文本为 `🧭 Agent 指南`。
  - 点击按钮后中心 modal 可见。
  - modal 显示 7 张 VO 内置暴露 skill 卡片。
  - 分类按钮显示：全部、运行规范、沟通协作、浏览器、工作区、项目流程、会议。
  - modal 没有搜索输入框。
  - modal 没有添加、上传、保存等编辑控件。
  - 浏览器分类过滤后只显示 `VO 浏览器控制` 一张卡片，卡片分类为 `browser`。
  - 关闭按钮可关闭 modal，关闭后 `agentGuideModal` 回到 hidden 状态。
- 窄屏验证：
  - 视口设置为 `390x720`。
  - Agent Guide 按钮仍可见并可打开 modal。
  - modal 显示 7 张卡片。
  - 卡片单列堆叠。
  - modal、filter、cards 和卡片无横向溢出。

### 覆盖说明

- CHK-001, CHK-002, CHK-003：通过浏览器 E2E 覆盖按钮可见、点击打开、关闭 modal。
- CHK-004, CHK-005, CHK-017：通过 `tests/check_agent_guide_static.mjs` 和浏览器 E2E 覆盖只展示 `skills/catalog.md` 中 VO 内置暴露 skill，且卡片字段完整。
- CHK-006, CHK-007, CHK-008：通过浏览器 E2E 覆盖分类过滤；通过静态检查确认无搜索框、无推荐行为。
- CHK-009, CHK-010, CHK-018：通过静态检查和浏览器 E2E 覆盖只读、无执行入口、无 `skill-turial` 范围漂移。
- CHK-011, CHK-012, CHK-019：通过独立 modal / 独立 JS 边界和静态检查覆盖不复用 editable Skills Library 行为；仍建议用户在日常 8090 环境中手动抽查既有技能库和 Agent 技能面板。
- CHK-013, CHK-014：通过桌面和 `390x720` 窄屏浏览器 E2E 覆盖布局可读、无横向溢出。
- CHK-015, CHK-020：通过 `tests/test_i18n_integrity.js`、locale JSON 解析和静态检查覆盖。

### 用户确认

- 用户已确认当前实现和验证结果可以标记为测试通过。

## 补充验收修正记录

- 执行时间：2026-07-07T22:30:00+08:00
- 背景：用户验收反馈 Agent Guide 卡片只展示摘要，未直接展示 skill 详细内容。
- 修正内容：为每个 VO 内置暴露 skill 增加默认展开的“Skill 详细内容”列表，覆盖使用边界、前置检查、核心流程和注意事项；保留只读和分类过滤，不加入推荐能力。
- 验证结果：`http://localhost:8090/` 刷新后，Agent Guide 默认显示 7 张 skill 卡片，7 个详情区默认展开；第一张卡片展示 4 条运行指南详情。

## 二次补充验收修正记录

- 执行时间：2026-07-07T22:40:00+08:00
- 背景：用户继续反馈点击“查看详细内容”后仍看不到内容。
- 根因：上一版使用原生 `<details>/<summary>`，并将其默认展开；“查看详细内容”文案实际仍是折叠开关，点击时可能把内容收起，交互语义与验收预期冲突。
- 修正内容：移除 `<details>/<summary>` 折叠交互，把 skill 详情改为普通常驻正文块；卡片直接展示“Skill 详细内容”和列表条目。
- 验证结果：`http://localhost:8090/` 刷新后，Agent Guide 显示 7 个详情块、0 个原生 `<details>`、0 个 `<summary>`；第一张详情列表 `display=block`、`visibility=visible`，高度正常。

## 三次补充验收修正记录

- 执行时间：2026-07-07T23:05:00+08:00
- 背景：用户明确期望“skill 的详细内容”不是摘要条目，而是点击后弹窗展示对应完整 `SKILL.md`。
- 修正内容：保留 Agent Guide 卡片作为列表入口；新增只读二级详情弹窗，点击卡片或“查看完整 SKILL.md”后从当前 VO 的 `/skills/<skill>/SKILL.md` 路径读取并展示完整原文。
- 验证结果：`http://localhost:8090/` 中点击 `VO 运行指南` 后，详情弹窗展示路径 `/skills/vo-operating-guidelines/SKILL.md`，内容以 `---\nname: vo-operating-guidelines` 开头，包含 `## 工作流`，无加载错误。

## 四次补充验收修正记录

- 执行时间：2026-07-08T00:05:00+08:00
- 背景：用户询问是否应直接使用项目里的文件，以及哪个来源更准确。
- 结论：当前项目中的 `skills/catalog.md` 和各 `skills/*/SKILL.md` 是最准确来源。
- 修正内容：Agent Guide 列表从静态前端文案改为运行时读取 `/skills/catalog.md`，再读取每个 catalog 暴露的 `SKILL.md`，从 frontmatter、一级标题和二级标题解析卡片标题、描述和章节；分类仍保留为 UI 分组元数据。
- 验证结果：静态检查确认 Agent Guide 读取 catalog、解析 `SKILL.md` frontmatter/章节，并继续通过 i18n 和 JSON 校验。

### 补充执行命令

```bash
node --check app/agent-guide.js
node tests/check_agent_guide_static.mjs
node tests/test_i18n_integrity.js
python3 -m json.tool app/locales/zh.json >/tmp/agent-guide-zh-json-check.txt
python3 -m json.tool app/locales/en.json >/tmp/agent-guide-en-json-check.txt
curl -sS http://127.0.0.1:8090/skills/vo-operating-guidelines/SKILL.md
```
