# 本期汉化完整性修复需求

需求名：`localization-completion`

## 背景

项目已经具备 `app/i18n.js`、`app/locales/en.json`、`app/locales/zh.json` 和 `data-i18n*` 属性组成的中英文切换机制。当前中英文语言包均有 880 个键，但界面仍存在以下问题：

- 已有中文词条没有绑定到静态 DOM。
- JavaScript 动态生成的按钮、状态、提示、确认框和错误信息仍硬编码英文。
- 少数代码引用了不存在的翻译键。
- 官网含 HTML 的翻译通过 `textContent` 注入，导致标签按字面显示。
- 部分中文词条夹杂不必要英文、术语不统一或存在疑似误译。

## 目标用户

- 使用简体中文操作 Virtual Office 的部署者和普通用户。
- 在中文界面中配置 OpenClaw、Hermes、浏览器、短信、模型和定时任务的管理员。
- 使用代理详情、聊天、会议、技能库、项目和办公室编辑功能的用户。

## 目标

### RQ-001 静态界面完整汉化

中文模式下，所有用户可见的静态操作文案、标题、标签、占位符和悬浮提示都应显示中文，覆盖：

- 主页面工具栏、设置菜单、侧边栏和代理详情。
- 会议、技能库、短信、浏览器和代理工作区。
- 设置向导、模型管理器、定时任务管理器。
- 产品官网。

### RQ-002 动态界面完整汉化

JavaScript 动态生成的状态、按钮、空状态、Toast、错误、确认框、输入提示和编辑器文案必须通过统一翻译机制生成，并能随当前语言正确显示。

重点覆盖：

- `app/game.js` 中的办公室编辑器、代理管理、会议和技能管理。
- `app/chat.js` 中的 Codex/Hermes 会话状态和交互提示。
- `app/setup.html` 中的连接、检测、保存和许可证状态。
- `app/models.html`、`app/cron.html` 和 `app/index.html` 内联脚本中的动态文案。

### RQ-003 翻译键与渲染方式正确

- 所有被引用的静态翻译键必须同时存在于中英文语言包。
- 动态键允许通过受控前缀构造，但必须有可验证的完整映射。
- 含受信任格式标签的翻译使用 HTML 翻译入口；纯文本翻译不得被当作 HTML 执行。
- 切换语言后，静态 DOM 和需要重绘的动态组件均显示目标语言。

### RQ-004 中文词条质量统一

- 修复已知混杂和误译，如 `workspace`、`Internal`、`卡尔tran工程`。
- Gateway、OpenClaw、Hermes、Codex、CDP、API、SMS、Twilio、Docker 等品牌或技术缩写可保留，但周边说明应为中文。
- 同一概念在不同页面使用一致译法。

### RQ-005 不破坏英文与业务功能

- 英文模式继续完整可用，不出现中文硬编码。
- 汉化修改不得改变接口请求、配置结构、权限逻辑、业务状态值、模型标识和持久化数据。
- 用户输入、代理输出、文件内容、模型名、代理名和服务端原始错误详情不做自动翻译。

## 范围

### 包含

- `app/index.html`
- `app/setup.html`
- `app/models.html`
- `app/cron.html`
- `app/game.js`
- `app/chat.js`
- `app/projects.js`
- `app/sms-panel.js`
- `app/feishu-panel.js`
- `app/browser-panel.js`
- `app/api-usage.js`
- `website/index.html`
- `website/script.js`
- `app/i18n.js`
- `app/locales/en.json`
- `app/locales/zh.json`
- 与本地化完整性直接相关的自动化测试

### 非目标

- 翻译 README、设计历史、开发文档和 `.cosh-docs` 既有教程。
- 翻译用户创建的项目、任务、技能、会议内容或代理回复。
- 增加简体中文和英文之外的新语言。
- 改造为第三方 i18n 框架。
- 翻译品牌名、协议名、文件名、代码、命令、URL 和 API 返回的不可控原始文本。

## 关键约束

- 继续使用现有轻量 i18n 机制和 JSON 语言包。
- 中英文键必须保持同步。
- 动态 HTML 中插入业务数据时必须继续转义，不能因汉化引入 XSS。
- 不依赖外部在线翻译服务。
- 不覆盖当前工作区中与本需求无关的未提交修改。

## 已知问题基线

- `app/cron.html` 引用了语言包中不存在的 `save_failed`。
- `app/index.html` 设置区、代理详情、会议和技能库存在未绑定翻译的英文。
- `app/game.js` 中办公室编辑、代理管理、会议和技能库动态文案大量硬编码英文。
- `app/chat.js` 中 Codex 状态、确认框和错误信息未完整汉化。
- `app/setup.html` 的运行状态和错误提示未走 i18n。
- `app/models.html` 的 LM Studio 动态区域未完整汉化。
- `website/index.html` 的页面标题、示例聊天和部分 HTML 富文本翻译存在问题。

## 验收总则

- 中文模式下，业务界面不再出现未批准的用户可见英文。
- 英文模式下，不出现中文硬编码或翻译键名。
- 不出现 `<br>`、`<strong>`、`<code>` 等翻译标签的字面文本。
- 不出现 `save_failed` 等裸翻译键。
- 核心页面和动态交互均通过自动化检查与人工浏览验证。
