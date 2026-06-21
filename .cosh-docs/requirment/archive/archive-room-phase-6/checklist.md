# Archive Room Phase 6 Checklist

确认状态：已确认

## Human Archive Understanding

### CHK-001: Archive Introduction Is Visible

- 关联需求点：项目档案详情需要解释档案用途。
- 验证方法：打开一个有真实任务、产物和维护记录的项目档案详情页。
- 预期结果：详情页在机械摘要之前展示该项目档案的用途，说明它服务于人类验收/交接、AI 入场、上下文查询、产物索引和风险追踪。

### CHK-002: Archive Contents Map

- 关联需求点：用户需要知道档案里现在有什么。
- 验证方法：打开项目档案详情页，检查信息地图。
- 预期结果：能看到基础信息、任务、产物、决策、风险、会议、重要消息、待确认等内容类型的存在/缺失状态。

### CHK-003: Archive Future Content Explanation

- 关联需求点：用户需要知道未来会继续放什么。
- 验证方法：查看档案说明区域。
- 预期结果：清楚说明未来维护会继续补充关键决策、风险、会议结论、重要消息、任务结果、产物来源和待确认项。

### CHK-004: Archive Usage Map

- 关联需求点：用户需要知道档案可以做什么。
- 验证方法：查看档案详情的信息地图或用途区域。
- 预期结果：能看到人类验收/追踪/交接、AI 入场、任务执行上下文、风险治理、产物浏览等使用目的。

### CHK-005: Project Identity First Screen

- 关联需求点：第一屏应同时包含项目身份、档案用途、完整度和可用动作。
- 验证方法：打开项目档案详情页首屏。
- 预期结果：无需滚动大量内容即可理解项目是什么、档案当前可用程度、可执行的主要动作。

### CHK-006: Project Basic Information

- 关联需求点：基础情况不能只是 Goal/Current State/Next Step。
- 验证方法：对照项目原始数据查看档案详情。
- 预期结果：展示项目名称、描述、状态、任务进度、最近更新时间、长期维护状态、活跃 AI/参与者（如有）、产物数量、待确认数量和主要来源类型。

### CHK-007: Missing Fields Are Not Misleading

- 关联需求点：缺失字段不能让用户误解为空事实。
- 验证方法：打开描述、参与者、规则或风险缺失的项目档案。
- 预期结果：缺失项显示“暂无/未记录/待补充”类状态，而不是显示为已确认没有。

## AI Onboarding And Context

### CHK-008: Standard Project Onboarding Package

- 关联需求点：新 AI 默认获得标准入场包。
- 验证方法：请求某项目的 AI onboarding context。
- 预期结果：返回项目目标、当前状态、关键规则、当前任务、关键决策、风险/阻塞、相关目录索引、产物和来源引用。

### CHK-009: Onboarding Package Is Bounded

- 关联需求点：入场包不能退化成原始历史 dump。
- 验证方法：对复杂项目请求 AI onboarding context。
- 预期结果：上下文以摘要和来源引用为主，包含可继续加载项，不默认返回大量原始聊天或完整日志。

### CHK-010: Task-Level Context Prioritizes Current Task

- 关联需求点：任务级入场包应先围绕当前任务。
- 验证方法：针对一个项目任务请求上下文。
- 预期结果：先返回当前任务目标、依赖、历史决策、风险、阻塞、相关产物和来源，再补项目背景。

### CHK-011: Context Query Conclusions First

- 关联需求点：AI 查询时先返回最相关结论。
- 验证方法：针对具体任务或问题请求项目上下文。
- 预期结果：响应先给结论，再给 source references，再给可选继续加载的 archive entries/artifacts。

### CHK-012: Context Query Preserves Confidence

- 关联需求点：AI 不应把推断或待确认内容当作确认事实。
- 验证方法：准备 confirmed fact、ai inference、pending confirmation suggestion、stale entry 混合的项目档案并查询上下文。
- 预期结果：响应明确标记各条内容的置信度、待确认或 stale 状态。

### CHK-013: Optional Next-Load Entries

- 关联需求点：AI 可按需加载更多档案，不一次性读取全部历史。
- 验证方法：请求复杂项目上下文。
- 预期结果：响应包含可选继续加载项，例如相关 archive entry、artifact、meeting 或 task source，而不是全部展开。

## Project-Characterized AI Context

### CHK-014: Project-Specific Characteristics Included

- 关联需求点：AI 上下文需要体现项目自己的特征。
- 验证方法：请求项目/任务上下文并检查内容。
- 预期结果：上下文包含项目业务背景、目标、已确认规则、用户偏好、决策风格、重要历史、风险和相关产物。

### CHK-015: Same AI Gets Different Project Context

- 关联需求点：同一个 AI 在不同项目中应获得不同项目特征。
- 验证方法：让同一个 AI 分别进入两个不同项目或任务，比较入场包/任务上下文。
- 预期结果：两个上下文有可感知差异，差异来自项目目标、规则、历史、风险、产物或用户偏好，而不是只有项目名不同。

### CHK-016: Global AI Identity Is Not Rewritten

- 关联需求点：项目上下文不能改写 AI 全局身份、安全边界或工具规则。
- 验证方法：检查注入到 AI 的项目/任务上下文。
- 预期结果：上下文明确作为项目/任务补充，不覆盖 AI 的基础身份、通用安全规则或工具使用边界。

## Archive Manager Reminders

### CHK-017: Ordinary Missing Context Is Query-Time Only

- 关联需求点：普通缺失只在查询上下文时返回。
- 验证方法：准备一个缺少描述或缺少规则的项目，并触发普通上下文查询。
- 预期结果：响应中包含缺失上下文提醒，但不会主动打断执行 AI。

### CHK-018: Severe Conflict Can Proactively Remind

- 关联需求点：严重冲突可以主动提醒执行 AI。
- 验证方法：准备与已确认规则冲突的任务上下文。
- 预期结果：系统生成面向执行 AI 的冲突提醒，包含冲突内容、来源和建议处理方式。

### CHK-019: Reminder Severity Is Controlled

- 关联需求点：分级提醒避免噪音。
- 验证方法：分别准备低影响缺失、普通风险和严重冲突。
- 预期结果：低影响缺失只出现在上下文中；普通风险不强制打断；严重冲突可主动提醒。

## UI And Regression

### CHK-020: Archive Detail UI Keeps Existing Artifact Access

- 关联需求点：Phase 6 不破坏产物浏览。
- 验证方法：打开有图片、视频、音频、文档和多层路径产物的项目档案。
- 预期结果：产物按钮、两栏弹窗、按来源/按路径切换和预览继续可用。

### CHK-021: Phase 5 Maintenance Data Still Visible

- 关联需求点：Phase 6 不破坏维护状态与记录。
- 验证方法：打开启用长期维护且有维护记录的项目档案。
- 预期结果：长期维护状态、最近巡检时间、维护记录、重要消息入档结果继续可见。

### CHK-022: No Human Free-Form Ask UI Required

- 关联需求点：Phase 6 不做自由问答 UI。
- 验证方法：检查 Archive Room UI。
- 预期结果：不要求出现“问档案室”的自由问答入口；如出现入口，应是后续 phase 或实验入口，不作为 Phase 6 验收必须项。

### CHK-023: Existing Project/Task/Chat/Meeting Regression

- 关联需求点：Archive Room 不替代或破坏已有业务流程。
- 验证方法：执行项目创建/编辑、任务移动/完成、聊天、会议创建/完成、产物查看。
- 预期结果：原有流程仍可使用；Phase 6 上下文能力不改变业务结果或阻断操作。

### CHK-024: Degraded Mode

- 关联需求点：Archive Room 在档案 AI 或整理失败时仍可用。
- 验证方法：模拟 archive manager unavailable 或上下文生成失败。
- 预期结果：已有项目档案和产物仍可查看；上下文/提醒能力显示降级或错误，不导致主应用不可用。

## 人工确认记录

- 确认项：checklist
- 确认时间：2026-06-20T17:04:27+08:00
- 用户确认摘要：用户回复 `continue,可以写todolist了`，确认 Archive Room Phase 6 checklist 可以进入 todolist 生成。确认范围包含人类可读档案说明、项目基础信息、AI 入场包、任务级上下文、项目特征化上下文注入、档案管理员分级提醒、Phase 1-5 回归和 Phase 7 边界。

## 实现与自测记录

- 记录时间：2026-06-20T17:36:37+08:00
- 实现摘要：已完成项目档案说明、项目基础信息、档案内容地图、档案用途地图、标准 AI 入场包、任务级上下文、AI context query 响应、项目特征化上下文注入、全局身份边界说明、普通缺失/严重冲突分级提醒，以及项目执行 prompt 的 Archive Room 补充上下文接入。
- UI 摘要：档案室项目详情新增“项目档案”说明区、“档案信息地图”和“项目基础信息”，原“基本情况”调整为“关键摘要”；产物浏览、长期维护和整理记录继续保留。
- 自动化覆盖：`tests/test_archive_room_phase_6.py` 覆盖 CHK-001 到 CHK-019、CHK-024 的核心路径。
- 回归覆盖：已运行 `tests/test_archive_room_phase_1_3.py`、`tests/test_archive_room_phase_4.py`、`tests/test_archive_room_phase_5.py`、`tests/test_project_execution.py`、`tests/test_meeting_for_ai_phase1.py`、`tests/test_meeting_for_ai_phase4.py`、`python -m py_compile app/server.py`、`node --check app/archive-room.js`。
- API smoke：在 `./start.sh` 启动的本地服务 `http://127.0.0.1:8160` 上验证真实项目 `7692ca8b-2d88-44cf-9dbb-765f2e4eb855` 返回 `archiveIntroduction`、`projectBasicInfo`、`archiveContentMap`、`archiveUsageMap`、`contextPackage`；`/api/archive-room/projects/{id}/context` 返回 `conclusions`、`projectCharacteristics`、`optionalNextLoads`、`reminders` 和不改写 AI 全局身份的 `boundary`。
- Chrome MCP 验收：已按用户要求在沙盒外启动 `chrome-devtools-mcp@latest --browserUrl http://127.0.0.1:9224`，连接共享 Chrome/CDP 验收 `./start.sh` 启动的真实服务。共享 Chrome 访问宿主机服务使用 `http://10.110.139.216:8160`，因为浏览器容器内的 `127.0.0.1` 不指向宿主机服务。
- Chrome MCP 验收结果：通过。MCP 脚本调用页面入口 `openArchiveRoom()` 后确认真实档案室弹窗存在，并包含 `项目档案`、`档案信息地图`、`项目基础信息`、`使用目的`、`内容类型`、`AI 入场包`、`查看项目产物`、`长期维护`；截图保存到 `/tmp/archive-room-phase6-mcp.png`。验收结束后已关闭档案室弹窗并退出 MCP 进程。
- 临时浏览器降级验收：此前曾使用临时 headless Chrome 执行 DOM smoke，截图 `/tmp/archive-room-phase6-headless.png` 仅作为辅助记录；最终验收以 Chrome MCP 结果为准。

## 测试与最终验收确认记录

- 确认项：tested
- 确认时间：2026-06-20T19:53:24+08:00
- 用户确认摘要：用户回复 `可以了，我验收通过了，这个子需求可以归档了`，确认 Archive Room Phase 6 已通过验收。验收范围包含项目档案可读性、档案索引体验修正、AI 入场包/上下文、产物浏览、维护信息、自动化测试和 Chrome DevTools MCP 真实浏览器验收。

- 确认项：done
- 确认时间：2026-06-20T19:53:24+08:00
- 用户确认摘要：用户要求归档该子需求，需求闭环完成。
