# 人工决策中枢正式集成验证证据

日期：2026-08-03

## 自动化验证

- 前端组件、生产接线与 SSE 静态契约通过：`node tests/check_human_decision_center.mjs`、`node tests/check_dashboard_realtime_static.mjs`。
- 相关 UI 回归通过：`node tests/check_project_orchestration_task_dialog.mjs`、`node tests/test_management_token_dialog.js`。
- 人工决策状态、投递、工作流、飞书同步、Skill、Dashboard、飞书通知、会议 UI 及真实 HTTP/SSE 链路聚焦批次：`117 passed in 6.09s`。
- 新增的浏览器服务夹具使用临时状态目录和无外部副作用的投递器，不读取生产决策状态，也不会向真实飞书发送消息。
- HTTP/SSE 集成用例覆盖管理令牌提交、统一状态落库与 `dashboard.decisions` 实时事件；同时选 B 和填写自定义答案时，最终 `answer` 采用自定义输入且 `optionId=null`。
- 排除三个既有 collection 阻塞后的广覆盖批次：`2655 passed, 4 failed in 115.62s`。四个失败属于既有飞书消息元数据、Provider 生成基线和 HR 通信提示词，不涉及人工决策模块；失败项为：
  - `tests/test_feishu_original_channel_notice_sync.py`
  - `tests/test_feishu_rich_post_inbound.py`
  - `tests/test_provider_baseline_inventory.py`
  - `tests/test_vo_agent_communication_service.py`
- `openspec validate add-decision-request-ui-prototype --json`：valid，无 issues。
- 本次范围内 whitespace 检查通过。全工作树检查仅命中范围外既有修改 `openspec/specs/meeting-collaboration-service-boundaries/spec.md` 的文件尾空行。
- 未排除项目既有阻塞的全量收集仍有 3 项错误：两项依赖已缺失的其他 OpenSpec evidence 文件，一项 live workflow E2E 未提供管理令牌；均与人工决策模块无关。
- 聊天、会议、项目正式 Prompt 均通过共享 `human_decision_escalation` XML 节点提示 Agent：先调查并继续安全可逆工作，重大未授权取舍使用 `vo-human-decision`，普通可验证不确定性不升级。
- 无新规则的三类压力场景中，Agent 会避免危险代决，但不会稳定进入决策中枢；加载更新后 Skill 后，三类场景均明确创建决策请求并只暂停受影响分支。反过度升级场景中，已锁定依赖缺失问题继续由 Agent 自主修复。

## 浏览器 E2E

- 在正式 VO 控制面板宿主上验证右侧控制面板入口与页面级居中弹窗。
- 提交 B 并同时填写“先给 20 位内部用户灰度 48 小时”，权威结果采用自定义输入，且不再保留 B 的 `optionId`。
- SSE 将待处理徽标从 1 更新为 0，并把事项迁入历史；页面未创建第二条 EventSource。
- 760×900 窄屏验证列表/详情单视图及返回列表交互。
- 隔离的正式 `OfficeHandler` 验证管理端创建返回 201、读取和提交返回 200；本机 Agent 创建返回 201，决策后 execution-started 返回 200 并进入 locked。

### VO 壳层复验（2026-08-03）

- 人工决策入口已从顶部工具栏移入右侧控制面板，作为与会议、项目同级的“⚖️ 人工决策”折叠区块；顶部工具栏不再保留重复入口。
- 详细界面改为参考会议/项目的页面居中管理弹窗。1280×720 视口实测弹窗为 900×612，中心点为 (640, 360)，不再呈现右侧抽屉或右下角浮层。
- 字体层级实测统一为：弹窗标题 14px、事项标题 12px、正文 10px、按钮与元数据 9px；已移除 20–34px 的响应式大标题。
- 浏览器复验发现并修复两处静态缓存失效问题：决策组件资源和 Dashboard 实时脚本均更新版本参数。更新后 SSE 显示“实时连接”，已处理记录从权威快照呈现为 1 条，并展示“飞书已处理 · 已实时同步”。
- 关闭按钮实测将弹窗宿主恢复为 hidden；待处理/历史、飞书终态和统一 SSE 投影保持正常。

## 飞书真实租户验收

- 通知机器人未配置时，卡片通过聊天机器人回退会话成功发送，返回 application=`chat`。
- A–D 排版改为四个独立 Markdown 信息块，每块分别展示选项标题、VO 推荐标记和对应影响；底部 A/B/C/D 与“提交自定义”按钮保持不变。
- 选项组前后使用飞书原生 `hr` 元素分隔：第一条位于“风险 / 紧急度”之后，第二条位于 D 与“VO 推荐”之间。
- 通用飞书通知渲染与人工决策卡片聚焦回归：`84 passed in 5.19s`。
- 排版调整后的决策投递、工作流和飞书同步聚焦测试：`13 passed in 0.14s`。
- 新建真实 Mock「[Mock 验收] 飞书 A–D 选项分组展示」并通过聊天机器人发送成功：决策状态为 `pending`，飞书状态为 `sent`，通知记录已持久化真实 message ID。
- 新建真实 Mock「[Mock 验收] 飞书 A–D 选项组分隔线」并通过聊天机器人发送成功：决策状态为 `pending`，飞书状态为 `sent`。
- 模拟真实飞书表单回调后，同一权威状态记录 channel=`feishu`。
- 发现飞书不允许 schema 2 卡片 PATCH 为 schema 1 后，终态卡片保持 schema 2、移除提交动作；重试真实消息更新成功，返回 code=`0`。
- 最终审计再次使用当前代码更新同一张真实验收卡片，返回 `ok=true`、status=`updated`、application=`chat`、code=`0`。
- 定时语义验证为三次提醒均实际投递；第三次后再等待一个对应紧急度间隔，仍未处理才进入低风险推荐或继续等待策略。

## 展览宿主收口

UI 已确认，`app/human-decision-center-prototype.html` 与 `app/human-decision-center-prototype.js` 已删除。正式页面只加载 `human-decision-center.js`、`human-decision-center.css` 和 `human-decision-center-app.js`。
