# 项目定时任务 Phase 1 方案评审

## 评审结论

该子需求可以进入 checklist 草案阶段，但实施前必须把“现有 Cron 的所有权和持久化位置”作为首要任务确认。当前仓库能看到 Cron Manager 前端和 WebSocket gateway 调用，但没有看到 `cron.*` 的本地后端实现，因此不能假设直接修改 `app/server.py` 就能扩展 cron job 字段。

该不确定性不阻塞 checklist，因为 Phase 1 的范围已经把“定位 Cron 存储/RPC 所有权”列为第一项验收和任务。

## 当前代码观察

- `app/cron.html` 负责 Cron Manager UI。
- `app/cron.html` 通过 `/gateway-info` 获取 gateway token 和 WebSocket 信息。
- `app/cron.html` 通过 WebSocket RPC 调用：
  - `cron.list`
  - `cron.add`
  - `cron.update`
  - `cron.remove`
  - `cron.run`
- `app/server.py` 提供 gateway 信息、WebSocket proxy、项目 API 和 gateway RPC helper。
- 本仓库内没有直接搜索到 `cron.add/list/update/remove/run` 的 server-side handler。
- 项目数据目前由 `app/project_store.py` 和 `app/server.py` 中的项目 API 管理。

## 技术风险

### 风险 1：Cron job 真实存储不在 Virtual Office 仓库内

如果 `cron.*` 完全由 OpenClaw gateway/provider 管理，VO 不能直接改字段定义。

建议：

- 先通过实际 gateway RPC 或 provider 文档/配置文件确认 cron job 返回结构和未知字段保留行为。
- 如果 provider 能保存未知字段，优先在 cron job metadata/payload 保存项目绑定。
- 如果 provider 不保留未知字段，VO 侧保存绑定表，例如 `project-cron-bindings.json` 或项目 markdown 附加字段。

### 风险 2：把项目定时任务塞进普通 `payload.message` 会造成语义不清

如果只是把项目名称写入 prompt，就无法可靠校验、查询、过滤和后续派发。

建议：

- 显式保存 `projectId`、`targetType`、`taskId`。
- 普通 Agent cron 和项目绑定 cron 必须可以被程序区分。

### 风险 3：普通 Cron Manager 兼容性

扩展字段可能影响 `/cron.html` 现有创建、编辑和渲染逻辑。

建议：

- 不带 `projectId` 的 cron job 继续走原逻辑。
- 列表渲染中未知字段不能造成异常。
- Phase 1 测试必须覆盖普通 Agent cron。

### 风险 4：项目资格字段不一定已存在

当前项目模型未必有明确 owner 字段。

建议：

- 优先检查是否已有 owner/负责人字段。
- 如果没有，Phase 1 使用“绑定 Agent”作为最低可配置条件。
- 在 review 和错误信息里明确该兼容策略。

## 推荐实现路径

### Step 1：确认 Cron 所有权

确认 `cron.*` RPC 是否由 OpenClaw gateway/provider 实现，确认返回字段、保存字段和未知字段保留行为。

### Step 2：确定项目绑定元数据保存策略

优先顺序：

1. 现有 cron job 原生 metadata 字段。
2. 现有 cron job payload 中明确的 structured project binding 字段。
3. VO 侧绑定表，用 cron job id 关联项目绑定元数据。

不建议：

- 只把项目名称或项目 ID 拼进 message 文本。

### Step 3：增加后端封装

无论底层保存在哪里，VO 应提供稳定的项目绑定 cron 管理封装，供 Phase 2 项目详情页使用。

建议封装能力：

- list project-bound cron by project id
- create project-bound cron
- update project-bound cron
- delete project-bound cron
- enable/disable project-bound cron

### Step 4：增加校验

- 项目存在。
- 项目有 owner 或绑定 Agent；如 owner 不存在，先以绑定 Agent 为准。
- `targetType` 合法。
- `taskId` 属于当前项目。
- schedule 复用现有 Cron 校验。

### Step 5：测试兼容性

- 项目绑定 cron CRUD。
- 元数据持久化。
- 校验失败不保存。
- 普通 Agent cron 不受影响。

## 非阻塞技术澄清

- VO 是否应该新增 REST API 供 Phase 2 使用，还是继续让项目页直接走 gateway RPC？建议新增 VO 后端封装，避免项目页直接理解 provider cron 细节。
- 项目 owner 字段如果不存在，第一版是否只用绑定 Agent 判断资格？建议可以。
- 如果 gateway 不保留未知字段，VO 侧绑定表放在全局状态目录还是项目 markdown 中？建议优先放项目相关持久化结构，但实现时应以现有项目存储模式为准。

## 评审结论

可以生成 checklist 草案。Checklist 确认后再生成 todolist 并进入执行。

