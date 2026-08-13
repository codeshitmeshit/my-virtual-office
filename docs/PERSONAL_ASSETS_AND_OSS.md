# 个人资产与 Alibaba Cloud OSS

> 状态：当前运维说明；已按 2026-08-10 代码核对。

## 能力边界

个人资产用于保存单用户的基本信息、职业方向、兴趣、聊天偏好、办公室目标和扩展信息。浏览器中的管理界面由管理会话保护；Agent 只能通过受限接口读取轮廓、申请上下文或提交已确认的建档变更。

- 本地权威数据：`VO_STATUS_DIR/personal-assets.json`
- OSS 配置：`VO_STATUS_DIR/oss-settings.json`，原子写入且权限为当前账户独占
- OSS 同步：可选、异步、local-first 的弱同步；OSS 失败不会回滚已经成功的本地修改
- 敏感数据：不会出现在 profile outline、日志、通知、导出配置或普通 Agent 响应中
- 敏感读取：统一进入 HUMAN DECISIONS，由用户选择一次性披露或当前任务范围披露

## 管理接口

管理接口必须经过现有管理令牌/管理会话边界。

- `GET /api/personal-assets`：读取管理视图与同步状态
- `POST /api/personal-assets/entries`：创建条目
- `POST /api/personal-assets/entries/<entryId>`：以 `operation=update|delete` 修改或删除
- `POST /api/personal-assets/suggestions/<suggestionId>/accept`
- `POST /api/personal-assets/suggestions/<suggestionId>/reject`

写操作使用 `expectedRevision` 做乐观并发控制。发生冲突时保留草稿并重新加载基线，不应静默覆盖其他写入。

## Agent 接口与 Skill

Agent 应先读取 `skills/vo-personal-assets/SKILL.md`，并使用 Agent 身份边界而不是管理令牌。

- `POST /api/agent/personal-assets/profile-outline`：只返回 revision 和不含值的条目元数据
- `POST /api/agent/personal-assets/request-context`：申请当前任务所需的个人上下文；敏感项会创建人工决策
- `POST /api/agent/personal-assets/suggest-change`：提交待用户审核的非直接写入建议
- `POST /api/agent/personal-assets/apply-confirmed-onboarding`：只提交用户明确确认的建档批次
- `POST /api/agent/personal-assets/feishu-onboarding-form`：通过已配置的飞书入口发起建档表单

建档草稿保留在对话上下文中。未得到精确确认时不得写入；幂等键与规范化变更集合绑定，不能复用于另一批内容。

## OSS 配置

OSS 只通过设置页配置，不读取 OSS 环境变量，也不混入通用 `vo-config.json`。

- `GET /api/settings/oss`：读取脱敏配置状态
- `POST /api/settings/oss/test-and-activate`：验证 Endpoint、Bucket 和凭证，探测成功后原子激活

启动脚本会在缺少时尝试安装 `alibabacloud-oss-v2`。Endpoint 必须是阿里云可解析地域的 HTTP(S) 服务地址；API 从不回显 AccessKey Secret 或原始 Provider 异常。

## 个人资产弱同步

- `GET /api/personal-assets/sync/availability`：懒检查 OSS 是否可用
- `POST /api/personal-assets/sync/preferences`：`{"enabled": true|false}`
- `POST /api/personal-assets/sync/now`：空对象，排队立即同步
- `POST /api/personal-assets/sync/conflict`：`{"resolution":"local"}` 保留本地，或 `{"resolution":"remote"}` 使用云端

首次启用时，空本地区域可以安全恢复云端快照。两端都变化时进入 `conflict`，必须由用户明确选择；系统不会自动覆盖。

## 验证

```bash
.venv/bin/python -m pytest -q \
  tests/test_personal_asset_store.py \
  tests/test_personal_asset_service.py \
  tests/test_personal_asset_http.py \
  tests/test_personal_asset_server_wiring.py \
  tests/test_personal_asset_sync_state.py \
  tests/test_personal_asset_sync_service.py \
  tests/test_oss_settings_live_server_routes.py \
  tests/test_aliyun_oss_storage.py
node tests/check_personal_assets_ui.mjs
```
