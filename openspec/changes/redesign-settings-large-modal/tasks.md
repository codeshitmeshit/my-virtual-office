<!-- cosh-dashboard-control {"mode":"continuous","sequence":1,"mode_updated_at":"2026-08-09T00:07:28+08:00"} -->

## 1. Figma 行为校准（MP-SET-01、MP-SET-02）

- [x] 1.1 在现有 Figma 文件中保留大弹窗主视觉节点 `334:240`，逐项核对 header、七分类导航、内容卡片、状态反馈、footer 和窄桌面布局，并建立 spec scenario 到画板区域的可追溯标注。
- [x] 1.2 修订交互全景节点 `338:240`：删除 dirty-close、backdrop/Escape 新语义，标明分类切换只改变展示且保留字段值，关闭仍走当前按钮与 `toggleMainMenu()`，所有测试/保存按钮继续触发当前 handler 和副作用。
- [x] 1.3 修订存储与提交节点 `338:249`：绘制当前全局保存的 localStorage-first → `/setup/save` 顺序、现有失败结果及 Feishu/Chat/OSS 独立保存测试边界，不再表达“测试默认不落库”或“服务端成功后才写本地偏好”。
- [x] 1.4 对 Figma 三个节点执行设计 CR，逐项对照已确认 spec、design 与 MP-SET-01/02；确认行为图没有发明新产品语义，并保存可复核的节点链接或截图证据。

## 2. 设置弹窗契约测试先行（MP-SET-01、MP-SET-03）

- [x] 2.1 新增 `tests/test_settings_modal_ui.js` 的最小 Fake DOM 骨架，先写七分类、当前每个 `.mm-section` 恰好归属一次、未知 section 降级 Advanced 和重复 mount 幂等的失败用例；验证命令 `node tests/test_settings_modal_ui.js` 应因实现缺失而失败。
- [x] 2.2 扩展 Fake DOM 失败用例，覆盖重排后原 input/section/`.mm-save-all` 节点身份不变、编辑值跨分类保留、导航不调用业务 handler、ARIA active/hidden 状态一致、语言变更不重建表单节点。
- [x] 2.3 新增 `tests/check_settings_modal_wiring.mjs` 的失败契约，覆盖 CSS 位于 `style.css` 后、JS 位于 `oss-settings.js` 后、8 个中英文 locale key、现有设置 ID inventory 未减少、OSS section 仍位于保留的 panel/body 契约中。
- [x] 2.4 在 wiring 契约中加入行为隔离守卫：`app/settings-modal-ui.js` 不得包含 `/setup/save`、localStorage、业务 endpoint、`toggleMainMenu`/`mmSaveSettings`/`mmTest*` 的覆盖或复制实现；记录 `check_provider_runtime_settings_ui.mjs` 的既有基线失败，避免误报本次回归。

## 3. DOM 保真布局适配器（MP-SET-01）

- [x] 3.1 新增 `app/settings-modal-ui.js`，实现 `CATEGORY_DEFINITIONS` 与 `classifySection(section)`，按已确认稳定锚点将当前 section 唯一映射到 Connections & Agents、Office、Display、Tools & Browser、Notifications、Storage、Advanced，未知未来 section 可见地降级到 Advanced。
- [x] 3.2 实现幂等 `mountSettingsModal()`：在 OSS 初始化后创建 dialog/nav/content/category/footer 展示容器，移动而不克隆现有 header、`.mm-section` 与 `.mm-save-all`，保留 `#main-menu-panel`、`.main-menu-body`、所有 ID、内联 handler 和 `open` class；仅在完整成功后添加 `settings-modal-mounted`。
- [x] 3.3 实现 `settingsModalState` 与 `activateCategory(categoryId)`，只维护页面会话内 active category，更新键盘可达的导航及 ARIA 状态，不读写存储、不调用保存/测试逻辑，并确保切换时现有字段值和条件展示状态不丢失。
- [x] 3.4 接入现有 `window.i18n.t` 与 `i18n:changed` 生命周期，只刷新标题、副标题和分类标签，不重建或再次移动表单节点；缺少翻译能力时使用安全的英文 fallback。
- [x] 3.5 运行 `node tests/test_settings_modal_ui.js`，执行 MP-SET-01 代码 CR，确认模块没有第二套设置状态权威、没有新增关闭语义、没有改变测试/保存副作用；修复后重复运行聚焦测试。

## 4. 大弹窗作用域样式（MP-SET-02）

- [x] 4.1 新增 `app/settings-modal.css`，所有覆盖均限定在 `.main-menu-panel.settings-modal-mounted` 下；定义局部尺寸、表面和边界变量，实现 viewport overlay、居中 dialog、稳定 header、左侧导航、独立滚动 content 与固定 footer，未挂载时保留旧侧栏降级。
- [x] 4.2 按已确认 Figma 主视觉实现约 960 × 680 px 且受 viewport 约束的桌面几何、高密度卡片网格、清晰 action/status 层级和长文本换行；只在作用域内细化现有 `.mm-section`、`.mm-input`、`.mm-btn`、`.mm-status`。
- [x] 4.3 增加窄桌面响应式规则，使导航与内容在有限宽度下切换为紧凑单列或横向分类入口，dialog 不越界、无页面级横向滚动，全部条件控件、状态和 footer 动作可滚动访问。
- [x] 4.4 扩展静态契约检查 CSS 作用域、挂载 gate、关键布局区域、响应式断点和禁止全局 `.modal` 覆盖；执行 MP-SET-02 样式 CR，确认不影响 canvas、toolbar 及其他弹窗。
- [x] 4.5 根据桌面实机反馈将整体调整为三栏：左侧一栏分类导航，右侧两栏连续内容流；弹窗上限扩至 1240px，卡片禁止跨栏拆分，≤820px 回退单栏，消除普通 Grid 行高造成的卡片断层，并补充静态契约与真实浏览器验收。

## 5. 最小接线与本地化（MP-SET-03）

- [x] 5.1 对 `app/index.html` 做局部 patch：在 `style.css` 后加载 `settings-modal.css`，在 `oss-settings.js` 后加载 `settings-modal-ui.js`；不得改写现有设置 markup、字段 ID、handler、Personal Assets 或 OSS wiring。
- [x] 5.2 对 `app/locales/en.json` 与 `app/locales/zh.json` 做局部 patch，增加 7 个分类键和 `settings_modal_subtitle`；禁止整体重排 JSON，保留当前未提交的 Personal Assets/OSS 文案。
- [x] 5.3 运行 `node tests/test_settings_modal_ui.js` 与 `node tests/check_settings_modal_wiring.mjs`，执行 MP-SET-03 diff CR，逐块确认 index/locale 只含批准的增量且脚本顺序保证 OSS section 在 mount 前存在。

## 6. 浏览器与行为验收

- [ ] 6.1 在本地 VO 页面以 1512 × 742 viewport 验证打开/关闭、七分类切换、字段编辑保留、条件控件、状态文本、全局 footer 和 OSS 动态 section；保存桌面截图并与 Figma `334:240` 对比。
- [ ] 6.2 在窄桌面 viewport 验证弹窗边界、分类导航、内容滚动、footer 可达、长文本/密钥字段无裁切、键盘焦点与 ARIA selection；保存窄屏截图证据。
- [x] 6.3 逐项执行现有 action 的兼容性抽查：关闭只走当前语义，测试按钮保留当前保存副作用，普通全局保存保持 localStorage-first → `/setup/save`，Feishu/Chat/OSS 独立边界不变；不得用真实生产密钥或产生非必要外部通知。
- [ ] 6.4 对运行时截图、Figma 交互板和存储板做最终 UI/行为 CR；任何差异必须回到已确认 spec/design 判断，禁止以视觉调整为由扩展保存、关闭或 API 范围。

## 7. 回归、范围审查与交付证据

- [x] 7.1 运行 `node tests/test_settings_modal_ui.js`、`node tests/check_settings_modal_wiring.mjs`、`node tests/test_oss_settings_ui.js` 与 `node tests/check_server_frontend_module_split.mjs`，记录命令、结果和失败定位。
- [x] 7.2 单独运行 `node tests/check_provider_runtime_settings_ui.mjs`；若仍为已记录的 `codexCfg.routeApprovalsThroughVo` 基线失败则明确隔离报告，若出现新的设置弹窗相关失败则修复后重跑。
- [x] 7.3 执行 UI 阶段代码 CR：按每个 spec scenario 回查 MP-SET-01 至 MP-SET-03、Figma 证据和自动化/浏览器证据；当时确认未修改业务实现，后续经用户明确批准的保存反馈与单入口改动由第 8、9 节独立约束和验证。
- [x] 7.4 检查最终 git diff 与范围内 whitespace，确认用户原有未提交修改全部保留；运行 `openspec validate redesign-settings-large-modal --json` 并整理测试、截图、Figma 节点、已知基线失败和低风险回滚说明供测试结果门禁确认。

## 8. 保存结果感知与功能确认

- [x] 8.1 新增保存行为失败测试，直接执行当前 `mmSaveSettings`，覆盖 localStorage-first、`/setup/save` payload、pending 重复调用只发一次请求、成功运行时更新、服务端 `{ ok:false }` 和网络异常；先确认测试因反馈模块和 pending 契约缺失而失败。
- [x] 8.2 新增 `app/settings-save-feedback.js` 及其 Fake DOM 测试，实现唯一 footer live status、保存中禁用原按钮、成功/失败持久状态、错误文本安全展示和语言刷新；模块不得拥有 endpoint、payload 或 localStorage。
- [x] 8.3 对 `app/game.js` 的权威 `mmSaveSettings` 做最小生命周期接线并返回/复用 in-flight promise；增加 3 个中英文 locale key、作用域样式和脚本顺序契约，不改变原有 payload、localStorage-first 顺序、运行时更新或关闭行为。
- [x] 8.4 运行保存行为、反馈模块、设置弹窗、OSS、模块边界、已知 provider 基线和 OpenSpec 校验；在本地浏览器确认 pending/success/failure 状态区域可见且不会产生重复提交，并记录证据。

## 9. 保存单入口与真实功能闭环

- [x] 9.1 新增单入口静态契约与路由测试，要求 `server.py` 不再定义或直接调用旧 `_persist_setup_payload`/merge/secret helper，真实 `/setup/save` 委托 `server_routes.config` 并只调用 `server_services.config_runtime`。
- [x] 9.2 将旧实现的显式 `VO_CONFIG`、status-dir、secret、Codex demo reply、Feishu transport、runtime refresh 与连接生命周期行为迁入 config runtime，迁移内部调用方并删除 `server.py` 的重复实现。
- [x] 9.3 新增真实落盘、运行时更新、磁盘写失败传播、业务失败 HTTP 状态和管理令牌跨本地源挑战测试，确认失败不能误报成功。
- [x] 9.4 新增 `settings-save-transport.js` 与测试，使用专用本地连接避开 SSE 连接池饥饿并设置 15 秒超时；非本地部署继续使用相对 `/setup/save`。
- [x] 9.5 在隔离的 18090/18091 端口、临时状态目录和合成管理令牌下执行浏览器保存：确认 saving 锁定、鉴权重试、持久 success、按钮恢复、无 console error，并读取临时 `vo-config.json` 核对真实落盘；测试服务已停止，临时目录已移入废纸篓。
