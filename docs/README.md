# 文档中心

> 当前文档基线：2026-08-13。面向当前运行版本；历史设计和验收材料按原始时间保留。

本目录把文档分为“当前使用与运维”“架构与开发契约”“历史记录”三类。初次使用先读根目录 [README.md](../README.md)，Agent 在 VO 内工作时先读 [VO_AGENT_USAGE_GUIDE.md](VO_AGENT_USAGE_GUIDE.md)。

## 当前使用与运维

| 主题 | 文档 |
| --- | --- |
| Agent 完整操作手册 | [VO_AGENT_USAGE_GUIDE.md](VO_AGENT_USAGE_GUIDE.md) / [中文镜像](VO_AGENT_USAGE_GUIDE.cn.md) |
| Agent 可用工具与 API 索引 | [VIRTUAL_OFFICE_AGENT_TOOLS.md](VIRTUAL_OFFICE_AGENT_TOOLS.md) / [中文镜像](VIRTUAL_OFFICE_AGENT_TOOLS.cn.md) |
| 个人资产、敏感授权与 OSS 弱同步 | [PERSONAL_ASSETS_AND_OSS.md](PERSONAL_ASSETS_AND_OSS.md) / [English](PERSONAL_ASSETS_AND_OSS.en.md) |
| HUMAN DECISIONS | [HUMAN_DECISIONS.md](HUMAN_DECISIONS.md) / [English](HUMAN_DECISIONS.en.md) |
| 跨 Provider 通信 | [AGENT_PLATFORM_COMMUNICATIONS.md](AGENT_PLATFORM_COMMUNICATIONS.md) / [中文镜像](AGENT_PLATFORM_COMMUNICATIONS.cn.md) |
| 聊天斜杠命令 | [CHAT_SLASH_COMMANDS.md](CHAT_SLASH_COMMANDS.md) |
| 飞书通知 Topic | [feishu-notification-topics.md](feishu-notification-topics.md) |
| 飞书 Chat Channel Worker | [feishu-channel-worker.md](feishu-channel-worker.md) |
| Codex Provider | [CODEX_PROVIDER_ADAPTER.md](CODEX_PROVIDER_ADAPTER.md) / [中文镜像](CODEX_PROVIDER_ADAPTER.cn.md) |
| Codex Chat 快路径 | [CODEX_CHAT_FAST_PATH_OPERATIONS.md](CODEX_CHAT_FAST_PATH_OPERATIONS.md) |
| Codex 飞书审批 | [CODEX_FEISHU_APPROVALS.md](CODEX_FEISHU_APPROVALS.md) |
| Hermes Provider | [HERMES_PROVIDER_ADAPTER.md](HERMES_PROVIDER_ADAPTER.md) / [中文镜像](HERMES_PROVIDER_ADAPTER.cn.md) |
| Hermes Platform Adapter | [HERMES_PLATFORM_ADAPTER.md](HERMES_PLATFORM_ADAPTER.md) |
| 会议状态迁移 | [MEETING_DOMAIN_OPERATIONS.md](MEETING_DOMAIN_OPERATIONS.md) |
| 开发机性能存储迁移 | [PERFORMANCE_STORE_MIGRATION.md](PERFORMANCE_STORE_MIGRATION.md) |
| 后端性能实测报告 | [PERFORMANCE_OPTIMIZATION_REPORT_2026-08-13.md](PERFORMANCE_OPTIMIZATION_REPORT_2026-08-13.md) |
| 项目任务编排 | [PROJECT_TASK_ORCHESTRATION_OPERATIONS.md](PROJECT_TASK_ORCHESTRATION_OPERATIONS.md) |
| Agent 创建 VO 项目 | [VO_PROJECT_AUTHORING_OPERATIONS.md](VO_PROJECT_AUTHORING_OPERATIONS.md) |

## 架构与开发契约

- [SERVICE_BOUNDARIES.md](SERVICE_BOUNDARIES.md)：项目与会议服务边界。
- [PROVIDER_SERVICE_ARCHITECTURE.md](PROVIDER_SERVICE_ARCHITECTURE.md)：Provider 服务权威状态与调用方向。
- [prompt-formatter-inventory.md](prompt-formatter-inventory.md)：XML Prompt 与共享 formatter 覆盖面。
- [MULTI-CHAT-ARCHITECTURE.md](MULTI-CHAT-ARCHITECTURE.md)：多聊天窗口状态模型。
- [SKILLS-LIBRARY-SPEC.md](SKILLS-LIBRARY-SPEC.md)：技能库数据模型与接口。
- [UNIVERSAL-AGENT-HARNESS-SPEC.md](UNIVERSAL-AGENT-HARNESS-SPEC.md)：多 Provider harness 的长期规格；它是设计基线，不代替当前运维手册。
- [vo-adapter.md](vo-adapter.md)：Provider adapter 开发指南。

## 历史与规划材料

- [design-history/](design-history/) 是已完成或被替代的历史设计记录。
- `docs/superpowers/plans/` 与 `docs/superpowers/specs/` 是当时的实施方案，不是当前功能清单。
- `openspec/changes/archive/` 是归档变更及其验收证据；不得为了贴合当前实现而改写历史结果。
- 尚未归档的 `openspec/changes/` 表示提案、进行中或待收尾的变更，是否已上线以代码和验证证据为准。
- [VO_PROJECT_TEMPLATE_EDITING_NEXT.md](VO_PROJECT_TEMPLATE_EDITING_NEXT.md) 和 [todo-task.md](todo-task.md) 是 backlog，不代表已实现能力。

## 维护规则

1. 用户可见行为、路由、配置默认值或持久化位置变化时，同一变更必须更新对应运维文档。
2. 中英文成对文档应同步修改；根 README 中文为主，英文版覆盖相同关键事实。
3. 当前说明只引用真实存在的路由、文件和测试；不要把 OpenSpec 提案当作已上线功能。
4. 历史证据保持不可变；通过新文档或索引说明其时代背景。
5. 提交前运行文档链接检查、`git diff --check`，并执行与修改主题对应的测试。
