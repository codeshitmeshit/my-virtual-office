<!-- cosh-dashboard-control {"mode":"continuous","sequence":2,"mode_updated_at":"2026-08-08T21:51:55+08:00","tasks_confirmed_at":"2026-08-08T23:23:22+08:00"} -->

## 1. 私有 OSS 设置存储

- [x] 1.1 调整 OSS 配置值对象、只读投影和原子文件存储，使 Region 只从 Endpoint 派生且不进入设置 API 或持久化投影。
  - **Scenario：** `Service restarts after configuration activation`、`OSS-like environment variables are present`、`Reload settings after saving credentials`、`Replace a configured secret`、`Observe settings failure output`。
  - **Design / 修改点：** Design 决策 1；MP-OSS-02。
  - **精确文件与符号：**
    - 修改 `app/services/oss_settings.py`。
    - `_derive_region_from_endpoint(endpoint: str) -> str`：从标准公网、内网和 dual-stack hostname 推导 Region；无法确定时返回 `oss_region_unresolved`。
    - `OssConnectionConfig`：内部不可变配置仍含派生的 `region: str`；`create()` 删除外部 region 参数。
    - `OssSettingsView`：变量仅为 `endpoint/bucket/access_key_id/configured/secret_configured`，类型中不得存在 secret 或 Region 字段。
    - `OssSettingsStore.__init__(data_dir)`、`load_active()`、`write_active(config)`；内部路径固定为显式 `data_dir / "oss-settings.json"`。
    - 修改 `tests/test_oss_settings.py`，先写失败测试再实现。
  - **复用与新增理由：** 复用 `app/project_store.py::_atomic_write_private` 已证实的临时文件 `0600` + `os.replace` 模式，但不导入其私有函数；现有 `_persist_setup_payload()` 允许环境变量和普通 JSON 写入，不能安全复用。
  - **实现步骤：**
    1. 用哨兵 secret 建立安全 `repr`、序列化和 settings view 测试。
    2. 增加三类标准 Endpoint 的推导测试，以及加速域名/自定义 CNAME 在 provider 前稳定失败的测试。
    3. 删除 persisted dict 和 settings view 的 Region；加载旧开发文件时忽略旧 Region 并从 endpoint 重算。
    4. 保持同目录临时文件、flush/fsync、`0600`、原子替换和 OSS-like 环境变量无效语义。
    5. 为 Region 派生边界、旧字段忽略、secret 永不投影和损坏配置失败语义添加中文注释。
  - **日志观测：** 只在读取损坏文件或持久化失败边界记录安全类别和文件用途；禁止记录 candidate、AccessKey、完整路径内容或原始 JSON。
  - **不得修改：** `app/server.py::_resolve_config_path/_load_vo_config/_persist_setup_payload/_SETUP_SECRET_KEYS`、`app/project_store.py`、现有 `vo-config.json` 行为。
  - **验证命令：** `.venv/bin/python -m pytest -q tests/test_oss_settings.py`；`git diff --check -- app/services/oss_settings.py tests/test_oss_settings.py`。
  - **回滚：** 删除本任务新增的 store 和定点测试即可；不得删除用户机器上可能已存在的 `oss-settings.json`。

## 2. 配置测试与原子激活运行时

- [x] 2.1 调整 `OssRuntime` 候选输入与空配置投影，保持连接验证和完整 context 原子切换语义。
  - **Scenario：** `Connection test succeeds`、`Connection test fails`、`Failed replacement preserves the active configuration`、`Activate a tested replacement`、`No validated configuration is active`。
  - **Design / 修改点：** Design 决策 2、7；MP-OSS-02。
  - **精确文件与符号：**
    - 修改 `app/services/oss_runtime.py`。
    - `ActiveOssContext`：不可变对象，变量 `config: OssConnectionConfig`、`provider: object`、`revision: int`。
    - `OssRuntime._active_snapshot: ActiveOssContext | None`、`_lock`、`settings_view()`、`active_context()`、`test_and_activate(candidate)`。
    - `OssConnectionValidator`/provider factory protocol：接收完整 candidate，提供只读 Bucket 探测，供后续 adapter 实现及本任务 fake 注入。
    - 扩展 `tests/test_oss_settings.py` 的 runtime 测试，不创建真实云连接。
  - **复用与新增理由：** 复用 Task 1 的 store 与不可变值对象；现有 VO globals 通过逐字段 reload 更新，无法保证 OSS 长传输看到完整单一快照，因此新增聚焦 runtime。
  - **实现步骤：**
    1. 先写无活动配置返回成功无 Region 空投影且 provider factory 零调用的测试。
    2. 启动时从 store 恢复配置并构造完整 context；无文件时保持 `None`。
    3. `test_and_activate` 不读取 candidate region；先合并 secret，再由配置对象从 endpoint 派生 Region、构造候选 provider并执行只读探测。
    4. `active_context()` 在锁内取得一个完整引用；锁外执行网络操作，避免长传输阻塞配置读取。
    5. 为“旧请求继续、启用响应后的新请求用新快照”和崩溃窗口语义添加中文注释。
  - **日志观测：** 验证失败记录安全 error code；激活成功只记录 revision 与 bucket 的安全指纹，不记录 endpoint query、AccessKey 或 secret；同一异常只在 runtime 或 adapter 的责任边界记录一次。
  - **不得修改：** 通用 `VO_CONFIG` globals、环境变量读取、任何对象业务流程；不得持久化“待测试候选”或测试 token。
  - **验证命令：** `.venv/bin/python -m pytest -q tests/test_oss_settings.py`；`git diff --check -- app/services/oss_runtime.py app/services/oss_settings.py tests/test_oss_settings.py`。
  - **回滚：** 删除 runtime 文件及对应测试增量；Task 1 store 保持可独立使用。

## 3. 调用方隔离的对象存储领域服务

- [x] 3.1 实现后端 `OssStorageService`、scope-bound `ObjectRef`、稳定错误和有界内存对象操作，并用 fake provider 覆盖全部对象规格。
  - **Scenario：** `Save and explicitly restore a material`、`No direct browser access is issued`、`Integration accesses its own object`、`Integration attempts cross-scope access`、`Overwrite an existing object`、`Delete an existing object`、`List scoped object metadata`、`Transfer a material larger than the in-memory working buffer`、`Provider rejects a save`、`Restore target does not exist`、`No validated configuration is active`。
  - **Design / 修改点：** Design 决策 4、5、7；MP-OSS-04。
  - **精确文件与符号：**
    - 新建 `app/services/oss_storage.py`。
    - `ObjectRef`：变量 `object_id: str`、`scope_fingerprint: str`；提供稳定序列化/解析。
    - `ObjectMetadata`：变量 `ref/size/content_type/etag/last_modified`；不得包含 URL、endpoint、bucket 或 raw provider key。
    - `OssStorageError` 及稳定 code：`configuration_unavailable/scope_mismatch/invalid_identifier/not_found/authentication/connectivity/provider_operation`。
    - `OssStorageService.save()`、`restore_to()`、`exists()`、`metadata()`、`list()`、`delete()`。
    - key 构造私有函数：固定 `vo/v1/` root，URL-safe base64 编码 `integration_id/object_id`，检查最终 UTF-8 key 长度。
    - 新建 `tests/test_oss_storage.py`。
  - **复用与新增理由：** 复用 Task 2 的 `active_context()`；仓库没有可安全扩展的对象存储领域接口，新增单一 service 是隔离 SDK、scope 与未来业务授权的最小边界。
  - **实现步骤：**
    1. 先构造 fake provider、禁止无界 `read()` 的 reader 和记录写入片段的 sink。
    2. 实现 ObjectRef 与 key 编解码，测试相同 object ID 可在不同 integration 共存、跨 scope ref 在 provider 前被拒绝。
    3. 实现 save/restore_to 仅传递流，不读取完整内容；restore 只有显式调用才触发 fake provider。
    4. 实现覆盖、删除、exists、HEAD metadata、prefix + continuation token list；列表 content type 不可用时返回 `None`。
    5. 统一领域错误，不暴露另一个 scope 是否存在同名对象。
    6. 为 scope 双重防护、主动恢复边界、列表不做 N+1 HEAD 和有界内存原因添加中文注释。
  - **日志观测：** provider 失败只记录 action、scope fingerprint、ObjectRef、error code、request ID；预期 not-found 不打 error；不得记录 integration ID 原文、reader/sink 内容或 raw key。
  - **不得修改：** 不增加 HTTP route、后台 worker、定时器、公共/签名 URL、最终用户 ACL、本地 fallback、版本/回收站逻辑。
  - **验证命令：** `.venv/bin/python -m pytest -q tests/test_oss_storage.py`；`git diff --check -- app/services/oss_storage.py tests/test_oss_storage.py`。
  - **回滚：** 删除领域模块和 fake-provider 测试；不触碰云端或本地配置文件。

## 4. 阿里云 OSS SDK V2 适配器与启动依赖

- [x] 4.1 复核阿里云 SDK V2 适配器继续只消费内部派生 Region，并更新 contract 测试。
  - **Scenario：** 所有 `vo-object-storage` provider/large-material 场景，以及 `OSS-like environment variables are present`、`Connection test succeeds/fails`。
  - **Design / 修改点：** Design 决策 2、3、5、7；MP-OSS-04。
  - **精确文件与符号：**
    - 新建 `app/services/aliyun_oss_storage.py`，这是唯一允许接触 `alibabacloud_oss_v2` 的业务文件。
    - `_load_sdk()`：延迟导入并在缺依赖时返回可行动错误，避免未使用 OSS 的模块导入失败。
    - `build_client(config)`：显式创建 `StaticCredentialsProvider`，覆盖 `cfg.credentials_provider/region/endpoint` 后创建 `Client`。
    - `AliyunOssProvider.probe_bucket()`、`upload_from()`、`download_to()`、`head()`、`exists()`、`list()`、`delete()`。
    - `_classify_sdk_error()`：把 SDK/transport 错误映射为 Task 3 稳定领域类别并保留安全 request ID。
    - 修改 `tests/test_aliyun_oss_storage.py`，以 fake SDK module 断言 client config 使用由 Endpoint 派生的 Region。
    - 修改 `start.sh:360-403` 附近的 `python_bin` 依赖检查，检测 `alibabacloud_oss_v2`，安装包名 `alibabacloud-oss-v2`。
  - **复用与新增理由：** 复用 SDK V2 `Uploader.upload_from`、GetObject streaming body 和 ListObjectsV2 continuation token；复用 `start.sh` 的 `.venv` 自修复结构。不得自行实现 OSS 签名、HTTP 重试或 multipart 协议。
  - **实现步骤：**
    1. 更新 fake SDK contract，配置对象不接收外部 Region，仍断言只构造 `StaticCredentialsProvider`，环境变量 provider 从未实例化。
    2. 实现 client factory 和只读 `ListObjectsV2(prefix="vo/v1/", max_keys=1)` 探测；断言没有 Put/Delete/Bucket 管理调用。
    3. 实现 uploader multipart reader、GetObject 固定 chunk 写 sink并可靠关闭 body、HEAD/delete/list 分页。
    4. 实现 SDK 错误分类和秘密脱敏，覆盖 404、401/403、连接/超时和其他 provider error。
    5. 增加启动脚本依赖检测，不把版本或凭证写成环境变量配置入口。
    6. 为显式静态凭证、只读探测、body 关闭与异常归一化原因添加中文注释。
  - **日志观测：** adapter 只做错误归一化，不重复记录；设置验证失败由 runtime、对象操作失败由领域 service 各记录一次。不得输出 request model、client config、AccessKey 或原始 exception repr。
  - **不得修改：** 不引入旧 `oss2`、`EnvironmentVariableCredentialsProvider`、手写签名、Bucket 创建/删除、presign；不改其他依赖检查语义。
  - **验证命令：** `.venv/bin/python -m pytest -q tests/test_aliyun_oss_storage.py tests/test_oss_storage.py tests/test_oss_settings.py`；`bash -n start.sh`；`git diff --check -- app/services/aliyun_oss_storage.py tests/test_aliyun_oss_storage.py start.sh`。
  - **回滚：** 删除 adapter 与 contract test，并只撤销 `start.sh` 中 OSS SDK 检查块；Task 1-3 的 provider-neutral 能力保持可测试。

## 5. 受管理令牌保护的 OSS 设置 API

- [x] 5.1 更新 OSS settings route 的安全投影测试，并验证真实未配置 HTTP 空状态。
  - **Scenario：** `Authorized settings user opens OSS settings`、`Unauthorized caller attempts to change OSS settings`、全部连接测试/激活/密钥写后不可读场景。
  - **Design / 修改点：** Design 决策 2、6、7；MP-OSS-03。
  - **精确文件与符号：**
    - 新建 `app/server_routes/oss_settings.py`。
    - `_runtime_provider: Callable[[], OssRuntime] | None`、`configure_runtime(provider)`、`_runtime()`。
    - `handle_get(handler, parsed_url)` 处理 `GET /api/settings/oss`。
    - `handle_post(handler, parsed_url)` 处理 `POST /api/settings/oss/test-and-activate`，使用 `server_routes.http.read_json/send_json` 的有界 JSON 约定。
    - 修改 `app/server_routes/__init__.py` 注册 `oss_settings`。
    - 修改 `app/server.py::OfficeHandler.do_GET()` 的 `request_path: str` 分支：先 `_reject_untrusted_management_request()`，再 route delegation。
    - 修改 `app/server.py::OfficeHandler.do_POST()` 同类分支：鉴权必须先于 body/runtime。
    - 在 `app/server.py:38410` 附近 composition root 以已解析 `STATUS_DIR` 显式构造 `OssSettingsStore/OssRuntime` 并调用 `server_routes.oss_settings.configure_runtime()`；禁止 runtime/store 回读环境变量。
    - 修改 `tests/test_oss_settings_live_server_routes.py`。
  - **复用与新增理由：** 复用 `_reject_untrusted_management_request()`、`i18n.managementFetch` 所依赖的挑战码、`server_routes.http` 和 `skill_library_organization.configure_runtime` 模式；通用 `/setup/save` 不具备验证后激活和密钥安全语义，不能复用。
  - **实现步骤：**
    1. 先写 live-server 无 token/错误 token/正确 token 的 GET、POST 测试，断言鉴权先于 JSON 解析及 provider 调用。
    2. route GET 在无活动配置时返回 `200`、`ok=true` 和不含 Region 的空投影；POST 不要求或转发 Region。
    3. 在 `OfficeHandler` 添加最小两处分支并立即返回，不在 legacy entry point 添加业务逻辑。
    4. composition root 只做构造、恢复和显式注入；SDK 缺失错误只在实际测试/使用 OSS 时出现。
    5. 增加未知路径透传、失败替换后 GET 仍显示旧配置，以及 response/log 无哨兵 secret/Region 测试。
    6. 完成实现后重启 VO，使用真实 HTTP 请求证明旧进程导致的 404 已消失；未配置时不得显示操作失败。
    7. 为鉴权顺序和薄路由边界添加中文注释。
  - **日志观测：** route 不重复记录 runtime/adapter 已记录的 provider failure；只在不可预期 route 错误时记录 request path 与安全 code，禁止记录 body。
  - **不得修改：** `/setup/save`、`/vo-config`、`_persist_setup_payload`、其他 route 顺序与鉴权语义；不增加对象 CRUD HTTP API。
  - **验证命令：** `.venv/bin/python -m pytest -q tests/test_oss_settings_live_server_routes.py tests/test_mcp_registry_live_server_routes.py`；`git diff --check -- app/server_routes/oss_settings.py app/server_routes/__init__.py app/server.py tests/test_oss_settings_live_server_routes.py`。
  - **回滚：** 删除 route 和 live test，只撤销 `server.py` 的两处转发及 composition 注入、`server_routes/__init__.py` 的一项注册；不改动私有设置文件。

## 6. 现有设置页中的 OSS 小型区块

- [x] 6.1 调整现有设置面板中的 OSS section，移除 Region、修正插入位置并收起空状态提示。
  - **Scenario：** `Authorized settings user opens OSS settings`、`Unauthorized caller attempts to change OSS settings`、`Reload settings after saving credentials`、`Replace a configured secret`、`Connection test succeeds/fails`。
  - **Design / 修改点：** Design 决策 6、7；MP-OSS-01；补充源码事实 `app/game.js::toggleMainMenu()` 在 `panel.classList.toggle('open', _mainMenuOpen)` 后加载现有设置。
  - **精确文件与符号：**
    - 修改 `app/oss-settings.js`。
    - 私有 `state: { loaded: boolean, configured: boolean, pending: boolean }`。
    - `ensureOssSettingsSection()`、`observeSettingsPanel()`、`loadOssSettings()`、`testAndActivateOssSettings()`、`renderSafeState()`。
    - `observeSettingsPanel()` 观察 `#main-menu-panel` 的 `class`，仅在首次出现 `.open` 时通过 `i18n.managementFetch` 调用 GET，避免首页启动就弹管理令牌挑战。
    - 保持 `app/index.html` 现有 `oss-settings.js` 加载行不变。
    - 修改 `app/locales/en.json`、`app/locales/zh.json`，删除不再使用的 Region 文案键。
    - 修改 `tests/test_oss_settings_ui.js`。
  - **复用与新增理由：** 复用 `.mm-section/.mm-label/.mm-status`、`i18n.t` 和 `i18n.managementFetch`；现有实际逻辑位于大型 dirty `game.js`，新增独立模块可保持最小接入且避免密钥进入通用 `mmSaveSettings()`。
  - **实现步骤：**
    1. 先写 DOM 测试：section 幂等插入并位于 `.mm-save-all` 前、DOM 无 Region、面板关闭时零请求、首次打开时一次 GET。
    2. 只渲染 endpoint/bucket/access key ID/password 和“测试并启用”；POST payload 不含 Region。
    3. GET 只处理 `secretConfigured`，password 永不回填；提交空 secret 表示保留旧值，无旧值时前端提示必填。
    4. 未配置成功响应保持空表单并隐藏 status；加载、成功或失败有文案时才显示现有 `.mm-status`。
    5. POST 成功或失败后立即清空 password DOM value，失败不把表单标成已启用；所有错误使用文本节点或 escape helper 防止注入。
    6. 复用 management token challenge，验证 403 后只走现有 token prompt/重试逻辑。
    7. 为延迟加载、防止 secret 驻留、插入顺序和空状态收起添加中文注释。
  - **日志观测：** 前端不 `console.log` payload、secret 或完整错误 response；状态区只显示后端安全 code/message。
  - **不得修改：** `app/game.js`、未加载的 `app/main-menu-settings.js`、`mmSaveSettings()`、`/vo-config`、现有设置 section 行为；不新增页面或前端路由。
  - **验证命令：** `node tests/test_oss_settings_ui.js`；`node tests/test_management_token_dialog.js`；`node tests/check_server_frontend_module_split.mjs`；`git diff --check -- app/oss-settings.js app/index.html app/locales/en.json app/locales/zh.json tests/test_oss_settings_ui.js`。
  - **回滚：** 删除新 JS 与 DOM test，并只撤销 `index.html` 脚本行和两份 locale 的 OSS 键；现有设置页保持原样。

## 7. 跨层验收与 OpenSpec 证据

- [x] 7.1 重新运行完整受影响验证矩阵并更新规格、设计、实现和测试之间的最终追溯证据。
  - **Scenario：** 两份 capability spec 的全部 scenarios。
  - **Design / 修改点：** 全部 Design 决策；MP-OSS-01 至 MP-OSS-04。
  - **精确范围：** 只允许修复前述任务中由测试暴露、且仍处于已确认 design 内的问题；若需要新文件、API、配置项、环境变量、后台任务或业务接入，立即停止并重新走受影响门禁。
  - **实现步骤：**
    1. 复查 `git diff`，确认没有 AccessKey、测试凭证、对象内容、调试日志、生成物、无关格式化或用户已有修改被覆盖。
    2. 运行 settings、runtime、storage、adapter、live route 和 UI 定点测试。
    3. 运行既有管理令牌、route module split 和受影响 server route 回归。
    4. 运行 OpenSpec strict validation，并将真实命令、结果、未覆盖项和环境限制作为测试结果门禁材料。
    5. 检查新增核心逻辑的中文注释及关键失败/激活日志均存在且已脱敏。
    6. 重启本地 VO 后以真实 `/api/settings/oss` 请求和设置页观察验证：无配置为正常空状态、无 Region 控件、区块间距与顺序符合现有设置 UI。
  - **不得修改：** 不迁移现有资料、不连接真实 Bucket 作为默认测试、不创建云资源、不删除本地配置；不因顺手清理扩大 diff。
  - **验证命令：**
    - `.venv/bin/python -m pytest -q tests/test_oss_settings.py tests/test_oss_storage.py tests/test_aliyun_oss_storage.py tests/test_oss_settings_live_server_routes.py tests/test_mcp_registry_live_server_routes.py`
    - `node tests/test_oss_settings_ui.js && node tests/test_management_token_dialog.js && node tests/check_server_frontend_module_split.mjs`
    - `bash -n start.sh`
    - `/Users/bytedance/.nvm/versions/node/v20.20.2/bin/openspec validate add-aliyun-oss-storage --strict`
    - `git diff --check`
  - **回滚：** 若验收失败，保留失败证据并回到产生回归的最早任务修复；不得通过删除测试、放宽密钥检查或跳过 scenario 宣称通过。
