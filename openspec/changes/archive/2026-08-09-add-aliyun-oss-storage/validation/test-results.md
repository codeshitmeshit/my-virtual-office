# Alibaba Cloud OSS 验证证据

## 状态

- 执行日期：2026-08-08
- OpenSpec change：`add-aliyun-oss-storage`
- 自动化验证：通过
- 真实云验证：未执行；默认测试未使用真实 AccessKey、未连接或修改任何 Bucket
- 人工测试结果确认：待用户确认

## 自动化结果

### Python 受影响矩阵

命令：

```bash
.venv/bin/python -m pytest -q \
  tests/test_oss_settings.py \
  tests/test_oss_storage.py \
  tests/test_aliyun_oss_storage.py \
  tests/test_oss_settings_live_server_routes.py \
  tests/test_mcp_registry_live_server_routes.py
```

结果：`48 passed in 0.56s`。

覆盖：

- 私有 `0600` 设置文件、原子替换、重启恢复、环境变量不覆盖、secret 安全投影。
- 标准公网、内网和 dual-stack Endpoint 的 Region 推导；加速 Endpoint/CNAME 返回 `oss_region_unresolved` 且 provider 零调用。
- 设置 API 和 `oss-settings.json` 不含 Region；旧开发文件中的 Region 被忽略并从 Endpoint 重算。
- 连接测试成功/失败、失败替换保留旧配置、secret 保留/替换和完整 runtime context 切换。
- integration scope 隔离、主动恢复、覆盖、删除、存在性、metadata、分页列表和跨 scope token 拒绝。
- 大于 transfer buffer 的有界 reader/sink 往返。
- SDK V2 `StaticCredentialsProvider`、只读 ListObjectsV2 探测、Uploader、stream body 关闭、分页和错误归一化。
- 管理令牌鉴权先于 body/runtime；未配置 GET 返回成功空投影且不构造 provider；成功/失败响应不回显 secret 或内部 Region；既有 MCP route 回归。

### 前端与模块边界

命令：

```bash
node tests/test_oss_settings_ui.js
node tests/test_management_token_dialog.js
node tests/check_server_frontend_module_split.mjs
```

结果：全部通过。

覆盖：关闭设置面板时零 OSS 请求、Region 控件与 POST 字段均不存在、OSS section 位于 `.mm-save-all` 前、初始和未配置状态不预占状态块、首次打开只加载一次、secret 不回填、提交后清空、既有管理令牌挑战行为和 `server.py`/前端模块边界。

### 语法、编译与 OpenSpec

命令及结果：

- `bash -n start.sh`：通过。
- `.venv/bin/python -m py_compile ...OSS modules...`：通过。
- `openspec validate add-aliyun-oss-storage --strict`：通过。
- 本需求精确文件集合 `git diff --check -- <OSS files>`：通过。
- 官方 `alibabacloud-oss-v2==1.3.2` 本地 client 构造 smoke check：通过；没有发送网络请求。

### 本地运行态与 UI 证据

- 旧后端进程启动于 OSS route 写入之前，真实 `GET /api/settings/oss` 曾返回 404 HTML；已重启当前工作区 VO，新后端进程启动于 `2026-08-08 23:27:31 +08:00`。
- 重启后，以现有管理令牌请求真实 `http://127.0.0.1:8090/api/settings/oss`，结果精确为 `ok=true`、空 endpoint/bucket/accessKeyId、`configured=false`、`secretConfigured=false`，没有 Region 或错误字段。
- 应用内浏览器首次 DOM 检查确认仅有 Endpoint、Bucket、AccessKey ID、AccessKey Secret，OSS section 位于页面级保存按钮之前，沿用现有 `8px` section 间距；该检查发现初始空 status 仍预占空间，随后已通过先失败后通过的 UI contract 增加 `hidden` 初始状态。
- 修正后的第二次应用内浏览器导航被页面长期连接拖到导航超时，因此最终空 status 证据来自可重复 DOM contract；未把该次超时记录为通过。

## 安全与边界证据

- 生产适配器没有 `EnvironmentVariableCredentialsProvider`，只显式构造 `StaticCredentialsProvider`。
- HTTP settings view 的类型和 JSON 中没有 `accessKeySecret` 字段。
- HTTP settings view、前端 DOM/POST 与持久化投影中没有 Region；Region 仅存在于后端不可变 client config。
- provider raw exception、候选配置、reader/sink 内容不会进入 HTTP 响应或日志。
- 对象能力没有浏览器 HTTP route、public URL 或 signed URL。
- Bucket 探测只执行 `ListObjectsV2(prefix="vo/v1/", max_keys=1)`，不执行 Put/Delete/Bucket 管理。
- 本轮 Region/UI 修正没有修改 `app/game.js`、全局设置 CSS、通用 `/setup/save`、`_load_vo_config()` 或 `_persist_setup_payload()`。

## 已识别的非本需求工作树问题

完整工作树 `git diff --check` 报告：

```text
openspec/specs/meeting-collaboration-service-boundaries/spec.md:200: new blank line at EOF.
```

该文件在本任务开始前已处于用户修改状态，本需求未读取或修改其内容；OSS 精确文件集合的 diff check 通过。为保护用户工作，本任务没有替用户清理该无关改动。

## 提交与环境限制

- 连续推进期间 Git 暂存区为空。
- 流程禁止自动 `git add`，因此各 task 均未创建空提交，也未提交用户工作树中的其他改动。
- 未验证真实 RAM 权限和真实 Bucket 网络路径；如需真实环境验收，应由用户在设置页提供测试配置并主动点击“测试并启用”。
