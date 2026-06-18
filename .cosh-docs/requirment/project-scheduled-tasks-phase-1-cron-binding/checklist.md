# 项目定时任务 Phase 1 Checklist

确认状态：已确认

- [ ] CHK-001 确认现有 Cron 的 RPC 所有权和存储位置。
  - 验证方法：检查 `cron.list/add/update/remove/run` 的实际处理方，确认是在 OpenClaw gateway/provider 还是 VO 本地，并记录 cron job 返回结构。
  - 预期结果：明确项目绑定字段应保存在现有 cron job metadata/payload 中，还是需要 VO 侧绑定表。
  - 关联需求点：Phase 1 首要目标是复用现有 Cron，不重做 scheduler。

- [ ] CHK-002 现有 cron job 支持保存项目绑定元数据或 VO 侧绑定表。
  - 验证方法：创建带 `projectId`、`targetType`、可选 `taskId` 的项目绑定 cron，并重新查询。
  - 预期结果：项目绑定元数据可被稳定读回；普通 Agent cron 不需要这些字段。
  - 关联需求点：项目定时任务必须显式绑定项目。

- [ ] CHK-003 项目绑定元数据可持久化。
  - 验证方法：创建项目绑定 cron 后重启服务或重载 cron/项目存储，再查询。
  - 预期结果：`projectId`、`targetType`、`taskId`、schedule、enabled 状态不丢失。
  - 关联需求点：项目绑定 cron 必须能跨重启恢复。

- [ ] CHK-004 项目资格校验正确。
  - 验证方法：分别对存在且满足条件的项目、不存在项目、没有负责人且没有绑定 Agent 的项目创建项目绑定 cron。
  - 预期结果：满足条件的项目创建成功；不存在或不满足条件的项目被拒绝，且没有半成品记录。
  - 关联需求点：只有有负责人或绑定 Agent 的项目才能配置。

- [ ] CHK-005 项目目标校验正确。
  - 验证方法：分别创建 `projectWorkflow`、当前项目任务、缺失任务、其他项目任务、非法 `targetType` 的项目绑定 cron。
  - 预期结果：合法目标成功；非法目标被拒绝并返回清晰错误。
  - 关联需求点：支持整个项目 workflow 和指定项目任务两类目标。

- [ ] CHK-006 schedule 校验复用现有 Cron 行为。
  - 验证方法：分别提交 cron、循环间隔、一次性时间的合法和非法 schedule。
  - 预期结果：项目绑定 cron 和普通 Agent cron 使用一致的 schedule 校验结果。
  - 关联需求点：复用现有 Cron 调度规则。

- [ ] CHK-007 普通 Agent 级 Cron Manager 兼容。
  - 验证方法：使用 `/cron.html` 或现有测试创建、查询、编辑、启用/禁用、删除、运行普通 Agent cron。
  - 预期结果：不带 `projectId` 的普通 Agent cron 行为不变，原 payload 语义不受影响。
  - 关联需求点：不能破坏现有 Cron Manager。

- [ ] CHK-008 提供供 Phase 2 使用的稳定后端封装。
  - 验证方法：调用 VO 后端封装或内部函数，按项目查询、创建、更新、删除、启停项目绑定 cron。
  - 预期结果：Phase 2 项目详情页无需直接理解 provider cron 细节即可管理项目绑定 cron。
  - 关联需求点：Phase 1 为项目详情页配置体验提供基础能力。

- [ ] CHK-009 错误响应可理解且不会保存部分状态。
  - 验证方法：构造项目缺失、任务缺失、非法 schedule、provider cron 保存失败、绑定表写入失败等场景。
  - 预期结果：返回清晰错误；cron job 和项目绑定元数据不会出现不一致的半保存状态。
  - 关联需求点：边界条件和错误场景。

- [ ] CHK-010 自动化测试覆盖 Phase 1。
  - 验证方法：运行新增 Phase 1 测试和现有 cron/websocket/project 相关回归测试。
  - 预期结果：新增测试覆盖 CHK-001 至 CHK-009；现有相关测试仍通过。
  - 关联需求点：可测试性和回归保护。

## 人工确认记录

- 确认项：checklist 初次确认
  - 确认时间：2026-06-18T00:00:00+08:00
  - 用户确认摘要：用户确认 Phase 1 子需求 checklist 可以继续执行。

## 实施与测试记录

- 实施时间：2026-06-18T00:00:00+08:00
  - 实施摘要：已新增 VO 侧项目 Cron 绑定表，使用 gateway `cron.*` 作为底层 Cron 能力；新增项目级 scheduled-cron 后端封装 API；新增项目资格、目标、schedule 校验；新增 Phase 1 后端测试。
  - 覆盖范围：CHK-001 至 CHK-010。

- 测试时间：2026-06-18T00:00:00+08:00
  - `.venv/bin/python tests/test_project_scheduled_cron_phase1.py`：通过。
  - `.venv/bin/python tests/test_websocket_route_contract.py`：通过。
  - `.venv/bin/python tests/test_project_execution.py`：通过。运行中出现 gateway 未连接日志，但测试结果为 `ok`。
  - 确认状态：等待用户确认测试通过。

- Live 复测时间：2026-06-18T00:00:00+08:00
  - 启动方式：`VO_PORT=8090 VO_WS_PORT=8091 VO_STATUS_DIR=/tmp/vo-phase1-cron-binding-live ./start.sh`
  - 服务地址：`http://localhost:8090`
  - 健康检查：`GET /health` 返回 `{"ok": true, "status": "running"}`。
  - Live API 链路：创建项目、创建任务、创建项目绑定 cron、列表查询、更新为 disabled/every、run-now、删除、删除后再次列表。
  - 复测结果：全部返回 200 且业务结果符合预期；删除后 `/tmp/vo-phase1-cron-binding-live/project-cron-bindings.json` 中 `bindings` 为空。
  - 页面检查：`/cron.html` 可访问；`/api/projects` 可访问并返回测试项目。
  - 确认状态：用户已确认 Phase 1 通过，并反馈全局定时任务页也应展示项目绑定 cron；该反馈已转入父需求 Phase 2。

## 测试确认记录

- 确认项：checklist 测试通过确认
  - 确认时间：2026-06-18T00:00:00+08:00
  - 用户确认摘要：用户验收 Phase 1，并要求将全局定时任务页展示项目绑定 cron 的需求写入 Phase 2。

## 完成确认记录

- 确认项：Phase 1 子需求完成确认
  - 确认时间：2026-06-18T00:00:00+08:00
  - 用户确认摘要：Phase 1 后端基础能力验收通过，剩余 UI 可见性诉求转入父需求 Phase 2。
