# Alibaba Cloud OSS 修改点分析

## 分析基线

- 仓库：`/Users/bytedance/cosh/my-virtual-office`
- Git 基线：`a1c300311eafdd874f4c195c5b863683663730b4`
- OpenSpec change：`add-aliyun-oss-storage`
- CodeGraph：已在当前工作树执行同步，并以同步后的符号关系为分析入口。
- 工作树状态：存在大量与本需求无关的用户改动；以下方案只新增聚焦模块，并将对既有脏文件的修改压缩到必要的加载、注册和装配行。
- 规格映射：
  - `VOOS-*` 表示 `specs/vo-object-storage/spec.md` 中的场景。
  - `VOSS-*` 表示 `specs/vo-oss-settings/spec.md` 中的场景。

## 当前变量流

```text
浏览器设置面板
  app/index.html #main-menu-panel > .main-menu-body
    -> app/game.js::_mmLoadCurrentSettings()
       -> GET /vo-config
    -> app/game.js::mmSaveSettings()
       -> i18n.managementFetch('/setup/save')
          -> X-VO-Management-Token
          -> app/server.py::OfficeHandler.do_POST()
          -> _persist_setup_payload(body)
          -> vo-config.json

现状问题：通用 setup 路径允许环境变量覆盖，且以普通 JSON 写入配置文件；它不满足
OSS“无环境变量回退、密钥写后不可读、验证成功后才原子激活”的独立约束。
```

```text
目标设置流
  app/oss-settings.js
    -> i18n.managementFetch(OSS 设置 API)
    -> OfficeHandler 管理鉴权
    -> server_routes.oss_settings（仅 HTTP 适配）
    -> services.oss_settings / services.oss_runtime
    -> 应用私有 OSS 设置文件（0600、原子替换）
    -> 显式 StaticCredentialsProvider
    -> 阿里云 OSS V2 客户端验证现有 Bucket

目标对象流（本期不增加浏览器对象 API）
  未来业务后端调用方
    -> services.oss_storage::OssStorageService
    -> integration_id 隔离后的 object_key
    -> services.aliyun_oss_storage
    -> 当前已激活配置的阿里云 OSS V2 客户端
```

## MP-OSS-01：在现有设置页加载独立 OSS 设置模块

### 现有定义与读写点

- `app/index.html:49` 定义 `#main-menu-panel`；`app/index.html:54` 定义 `.main-menu-body`，这是现有设置内容容器。
- `app/index.html:1255` 加载实际运行的 `game.js`，随后继续加载聚焦 UI 模块。
- `app/game.js:14062` 的 `_mmSettingsConfigRequest` 读取 `/vo-config`；`app/game.js:14105` 定义 `_mmLoadCurrentSettings()`。
- `app/game.js:15137` 定义 `mmSaveSettings()`，其 `config: object` 最终通过 `i18n.managementFetch('/setup/save')` 写入通用设置。
- `app/i18n.js:330-347` 的 `managementFetch(input, init)` 从 `sessionStorage.voManagementToken` 读取管理令牌并写入 `X-VO-Management-Token`。
- `app/main-menu-settings.js` 虽有同名设置函数，但没有被 `app/index.html` 加载，不是当前运行入口。

### 预期修改

- 修改 `app/oss-settings.js`，保持模块私有 `state: { loaded: boolean, configured: boolean, pending: boolean }` 不变：
  - `ensureOssSettingsSection()` 的 `section: HTMLDivElement` 不再创建 `#oss-region`；`host: HTMLElement` 使用 `insertBefore(section, saveButton)` 插入 `.mm-save-all` 之前，找不到该按钮时才追加，继续复用 `.mm-section/.mm-label/.mm-input/.mm-btn`，不新增全局间距 CSS。
  - `renderStatus(kind, message)` 的 `status: HTMLElement` 在 `message` 为空时移除状态样式并隐藏；加载、成功或失败有文本时才显示 `.mm-status`。
  - `renderSafeState(settings)` 不再读取或回填 `settings.region`；未配置投影 `configured=false/secretConfigured=false` 时保留空表单且收起状态区。
  - `testAndActivateOssSettings()` 的 `candidate: { endpoint, bucket, accessKeyId, accessKeySecret }` 删除 `region`，必填校验也不再读取它。
- 保持 `app/index.html` 的 `oss-settings.js` 加载行，以及 `app/locales/en.json`、`app/locales/zh.json` 的既有 OSS 文案；删除不再使用的 `oss_region` 键。
- 不修改 `app/game.js::mmSaveSettings()`，避免 OSS 密钥进入通用 `config` 对象和 `/setup/save`。
- 不修改未加载的 `app/main-menu-settings.js`。

### 上下游影响

- 上游：现有设置面板打开行为和 `i18n.managementFetch`。
- 下游：MP-OSS-03 的管理 API；页面永远不接收已保存的 `accessKeySecret`。
- 前端改动范围：一个新模块、一个脚本注册行、两份 locale 的增量键，不新增页面或前端路由。

### 场景与验证

- 覆盖：`VOSS-Authorized settings user opens OSS settings`、`VOSS-Unauthorized caller attempts to change OSS settings`、`VOSS-Reload settings after saving credentials`、`VOSS-Replace a configured secret`、`VOSS-Connection test succeeds/fails`。
- 扩展 `tests/test_oss_settings_ui.js`，验证：区块只插入一次且位于 `.mm-save-all` 前、DOM 和 POST 均无 region、未配置成功响应显示空表单且不显示状态块、密钥不回填、失败不改变“已配置”显示、管理令牌挑战复用既有流程。

### 排除方案

- 不直接扩写大型 `app/game.js`。
- 不把 OSS 字段并入通用 `mmSaveSettings()` 或 `/vo-config`。
- 不创建独立 OSS 管理页面。

## MP-OSS-02：应用私有的 OSS 设置存储与原子运行时快照

### 现有定义与读写点

- `app/server.py:806-829` 的 `_resolve_config_path()` 通过 `VO_CONFIG`、`VO_STATUS_DIR` 选择通用配置路径。
- `app/server.py:831-846` 的 `_load_vo_config()` 明确执行环境变量覆盖。
- `app/server.py:1066` 的 `_SETUP_SECRET_KEYS` 只影响通用设置合并，不提供独立密钥存储边界。
- `app/server.py:1377-1420` 的 `_persist_setup_payload(body)`：
  - 读取 `cfg_path/existing: dict`；
  - 合并 `body: dict`；
  - 以普通 `open(..., 'w')` 写入 `vo-config.json`；
  - 路径仍受环境变量影响。
- `app/project_store.py:177-192` 有项目私有 `_atomic_write_private(path, content)` 模式：临时文件 `0600`、`os.replace`、目标文件 `0600`。该函数属于项目存储内部，不应跨职责直接导入，但可复用其安全写入模式。

### 预期修改

- 修改 `app/services/oss_settings.py`：
  - `_normalize_endpoint(value) -> str` 继续完成安全 URL 规范化；新增 `_derive_region_from_endpoint(endpoint: str) -> str`，只接受地域明确的标准公网、内网和 dual-stack Endpoint，并从 `urlsplit(endpoint).hostname` 得到 SDK 所需 Region；加速域名、自定义 CNAME 或其他无法确定的 host 抛出稳定 `oss_region_unresolved` 校验错误。
  - `OssConnectionConfig` 继续以 `region: str` 保存一次派生后的不可变内部值，保证 provider 构造不重复猜测；`create()` 删除外部 `region` 参数，改为从已规范化 `endpoint` 派生。
  - `OssSettingsView` 删除 `region`，只含 `endpoint/bucket/access_key_id/configured/secret_configured`，禁止出现 secret 或内部 Region 字段值。
  - `OssSettingsStore`：固定使用应用拥有的数据目录内的 OSS 专用文件；路径构造不得读取任何 OSS 环境变量，也不得从 `_load_vo_config()` 取值。
  - `load_active()`：从持久化 endpoint 重新派生内部 Region；忽略开发阶段旧文件里可能存在的 `region` 键。
  - `write_active(config)`：持久化投影删除 `region`，在验证成功后以同目录临时文件、`0600` 权限和 `os.replace` 原子落盘。
  - 序列化、校验和异常消息必须经过密钥脱敏。
- 修改 `app/services/oss_runtime.py`：
  - `OssRuntime` 持有 `_active_snapshot: OssConnectionConfig | None` 与对应 provider client。
  - `activate(candidate)` 先用候选 client 验证现有 Bucket，再原子持久化和交换快照；失败时保留旧快照。
  - 新操作在锁内获取完整快照引用后再执行，避免观察到新旧字段混合。
  - `settings_view()` 的无活动配置分支返回不含 region 的成功空投影，不构造 provider；`_test_and_activate_locked()` 不再从 candidate 读取 region。
- OSS 配置文件路径可建立在 VO 已选定的应用数据目录之下，但 OSS 文件名和内容不接受环境变量覆盖；即使进程存在 `OSS_*`、`ALIBABA_CLOUD_*` 等变量也不读取。

### 安全边界（需本次修改点确认）

- 本期“保护持久化密钥”的具体落点为：独立文件、原子替换、文件权限 `0600`、API/日志永不返回或记录密钥、错误统一脱敏。
- 本期不额外引入 KMS、系统钥匙串或主密码加密层；如需超出本机账户文件权限的静态加密，应作为独立密钥管理需求处理。

### 上下游影响

- 上游：MP-OSS-03 设置 API 和 MP-OSS-04 对象服务。
- 下游：独立配置文件、显式构造的 OSS provider client。
- 不触碰通用 `VO_CONFIG` 全局及其环境变量合并逻辑。

### 场景与验证

- 覆盖：全部 `VOSS-OSS configuration is application-persisted without environment fallback`、`VOSS-Credential secrets are write-only`、`VOSS-Configuration must pass an explicit connection test before activation`、`VOSS-Activated settings take effect`，以及 `VOOS-No validated configuration is active`。
- 扩展 `tests/test_oss_settings.py`，验证三类标准 Endpoint 的 Region 推导、加速/CNAME 的稳定拒绝、持久化与 view 不含 region、重启重新推导、无配置成功空投影且 provider factory 零调用，以及原有密钥、并发和失败保留语义。

### 排除方案

- 不扩展 `_SETUP_SECRET_KEYS` 后继续写通用 `vo-config.json`。
- 不从任何环境变量、默认 SDK 凭证链或 `/vo-config` 回退读取 OSS 设置。
- 不在本期实现 Bucket 创建、删除或配置管理。

## MP-OSS-03：复用现有管理鉴权的聚焦 HTTP 路由

### 现有定义与读写点

- `app/server.py:28814` 定义 `OfficeHandler`。
- `app/server.py:28852-28865` 的 `_management_request_allowed()` / `_reject_untrusted_management_request()` 读取 `X-VO-Management-Token` 并返回稳定的 `management_token_required`。
- `app/server.py:29834-29843` 的 `do_GET()` 解析 `request_path: str` 并手工转发聚焦 route module。
- `app/server.py:32508-32510` 的 `do_POST()` 同样先解析 `request_path: str`。
- `app/server_routes/skill_library_organization.py:19-32` 展示当前可用的显式运行时注入模式：`_runtime_provider`、`configure_runtime()`、`_runtime()`。
- `app/server.py:38410-38412` 在 composition root 调用 route 的 `configure_runtime()`。
- `app/server_routes/__init__.py:1-18` 汇总 route modules；通用 `dispatch()` 虽存在，但当前 `OfficeHandler` 仍以手工分支为实际运行路径。

### 预期修改

- 新建 `app/server_routes/oss_settings.py`：
  - 模块级 `_runtime_provider: Callable[[], OssRuntime] | None`。
  - `configure_runtime(provider)` 和 `_runtime()` 只负责显式依赖注入。
  - `handle_get(handler, parsed_url) -> bool` 返回安全 settings view。
  - `handle_post(handler, parsed_url) -> bool` 读取有界 JSON，执行连接测试与激活，并把领域异常映射为稳定、安全的错误码。
- 在 `app/server_routes/__init__.py` 注册 `oss_settings`。
- 在 `OfficeHandler.do_GET()` 与 `do_POST()` 的 `request_path` 分支各增加薄转发：
  1. 判断 OSS settings route group；
  2. 在读取请求体或访问 runtime 前调用 `_reject_untrusted_management_request()`；
  3. 委托 `server_routes.oss_settings` 后立即返回。
- 在 `app/server.py:38410` 附近增加一次 `configure_runtime()` 装配，不在 `server.py` 实现校验、持久化或 provider 业务逻辑。

### 上下游影响

- 上游：MP-OSS-01 的 `i18n.managementFetch`。
- 下游：MP-OSS-02 的 `OssRuntime`。
- 对象存储本身不增加 HTTP route；未来业务模块通过 Python 服务接口接入，避免形成无授权的通用文件网关。

### 场景与验证

- 覆盖：`VOSS-Unauthorized caller attempts to change OSS settings`、所有设置读取/测试/激活场景。
- 扩展 live-server route 测试，验证无令牌 GET/POST 均为 403、鉴权先于 body/provider、无活动配置的授权 GET 返回 `200` 与安全空投影、密钥和内部 Region 不出现在成功或失败响应、未知路径不被吞掉。
- 当前截图中的通用错误已由运行态证据定位为旧后端进程：进程启动早于 OSS route 文件变更，实际 `GET /api/settings/oss` 返回静态服务器 404 HTML；实现完成后必须重启 VO，再用真实 HTTP 请求验证空配置路径，而不能只依赖进程内单测。

### 排除方案

- 不在 `server.py` 增加 OSS 业务实现。
- 不复用 `/setup/save`，避免候选配置在验证前被写成活动配置。
- 不暴露上传、恢复、删除、列表的公共浏览器 API。

## MP-OSS-04：调用方隔离的对象服务与阿里云适配器

### 现有定义与依赖点

- 当前仓库没有 OSS SDK、对象存储领域接口或 OSS provider 实现。
- `start.sh:360-403` 使用 `python_bin` 检测并按需安装 Python 依赖，是当前无集中依赖清单情况下的启动约定。
- 阿里云 OSS Python SDK V2 官方包为 `alibabacloud-oss-v2`，导入名为 `alibabacloud_oss_v2`；其 `StaticCredentialsProvider(access_key_id, access_key_secret)` 可显式注入设置值。

### 预期修改

- 新建 `app/services/oss_storage.py`：
  - `OssStorageService` 是未来业务模块唯一建议接入面。
  - 每个方法显式接收 `integration_id: str`，并把调用方 `object_id: str` 映射到不可越界的 provider key；禁止调用方传入绝对 key 或 `..` 等跨 scope 表达。
  - 建议方法：`save`、`restore_to`/流式 restore、`exists`、`metadata`、`list`、`delete`。
  - `ObjectMetadata` 只暴露内部 object ID、size、content type、etag/last-modified 等基本信息，不包含 provider URL。
  - 稳定领域错误：configuration unavailable、not found、authentication、connectivity、provider operation、invalid identifier。
- 新建 `app/services/aliyun_oss_storage.py`：
  - 这是唯一导入 `alibabacloud_oss_v2` 的模块。
  - `build_client(config)` 必须构造 `StaticCredentialsProvider`；不得构造 `EnvironmentVariableCredentialsProvider` 或默认凭证链。
  - 保存和恢复接受 file-like/iterator/sink，使用 SDK 流式或 multipart 能力；业务服务不对对象设置更小的固定总大小上限。
  - 列表使用 scope prefix 和分页 token；输出前剥离 prefix，永远不返回其他 scope。
  - provider 异常只映射必要类别和 request ID，不记录凭证、请求体或完整对象内容。
- 在 `start.sh:386` 同类依赖检查区域增加 `alibabacloud_oss_v2` 检测及 `alibabacloud-oss-v2` 安装提示。
- MP-OSS-02 的 active runtime 向本服务提供原子 client snapshot；无活动配置时不发出 OSS 请求。

### 上下游影响

- 上游：未来 VO 业务后端；本期只有测试 fake caller，不迁移任何现有资料流程。
- 下游：阿里云 OSS 现有 Bucket。
- 覆盖保存、主动恢复、覆盖、删除、存在性、元数据、分页列表；删除后模块不提供恢复入口。

### 场景与验证

- 覆盖 `vo-object-storage` 的全部场景。
- 新增 `tests/test_oss_storage.py`，用 fake provider 验证：
  - 相同 object ID 覆盖；
  - 不同 `integration_id` 无法读/写/删/列彼此对象；
  - restore 只有显式调用才发生；
  - 大于工作 buffer 的流式往返不执行无界 `read()`；
  - 删除、not-found 和 provider 错误稳定；
  - 元数据与列表无 URL；
  - 错误和日志无 secret/content。
- 扩展 adapter contract 测试，以 fake SDK 验证显式静态凭证、由 Endpoint 派生的内部 region 及 endpoint/bucket 传递、分页和流式调用；默认测试不要求真实云凭证或联网。

### 排除方案

- 不提供 signed/public URL。
- 不做自动、后台或定时恢复。
- 不把最终用户授权逻辑放进通用存储模块；调用方只获得 integration scope 隔离。
- 不增加本地文件后备存储、多云接口或现有资料迁移。

## 拟修改文件清单

### 新文件

- `app/oss-settings.js`
- `app/services/oss_settings.py`
- `app/services/oss_runtime.py`
- `app/services/oss_storage.py`
- `app/services/aliyun_oss_storage.py`
- `app/server_routes/oss_settings.py`
- `tests/test_oss_settings.py`
- `tests/test_oss_storage.py`
- `tests/test_oss_settings_live_server_routes.py`
- OSS 前端 DOM 测试文件（名称在 design 中按现有测试命名约定确定）

### 最小既有文件修改

- `app/index.html`：加载新 UI 模块。
- `app/locales/en.json`、`app/locales/zh.json`：增加文案键。
- `app/server_routes/__init__.py`：注册 route module。
- `app/server.py`：GET/POST 鉴权转发和 composition-root 注入。
- `start.sh`：SDK 依赖检测与安装。

### 明确不修改

- `app/game.js`
- `app/main-menu-settings.js`
- 通用 `_load_vo_config()` / `_persist_setup_payload()` 行为
- 任何现有 VO 资料或 personal-assets 业务流程

## 进入 Design 前的确认项

确认本修改点即同时确认：

1. OSS 设置使用独立应用私有文件，不进入通用 `vo-config.json`，不接受任何环境变量覆盖或 fallback。
2. 密钥保护边界为 `0600` 私有文件 + 原子写入 + API/日志脱敏；本期不引入 KMS/钥匙串/主密码加密。
3. 设置页面通过新 JS 模块追加一个 section，不扩写 `game.js`，不新增独立管理页面。
4. 对象能力只开放给后端模块，不新增浏览器对象 API；未来业务接入另行提出需求。
5. SDK 使用阿里云 OSS Python V2 和显式 `StaticCredentialsProvider`，不会调用环境变量凭证提供器。
