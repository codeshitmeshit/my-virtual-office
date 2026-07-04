> English version: [MULTI-CHAT-ARCHITECTURE.md](MULTI-CHAT-ARCHITECTURE.md)

# 多聊天窗口架构

状态：现有虚拟办公室聊天 UI 的已批准架构方案
范围：保留一个共享聊天系统，同时允许主聊天窗口外加最多 3 个侧滑窗口

## 1) 窗口模型

使用一个 `ChatWindowManager`，包含 **4 个槽位**：

- `primary` — 现有的主聊天窗口
- `secondary-1`
- `secondary-2`
- `secondary-3`

规则：

- `primary` 始终存在，并拥有当前聊天切换按钮的行为。
- 辅助窗口是可选的，仅在打开时创建。
- 同一时间最多打开的窗口数 = **4** 个（`primary` + 3 个辅助窗口）。
- 辅助窗口按槽位编号从左到右排列，以保证布局确定性。
- 关闭辅助窗口仅销毁该槽位实例的布局/UI 状态，不销毁底层的会话历史。

## 2) 每窗口状态模型

每个槽位存储自己的聊天目标和 UI 状态。

```js
const chatWindows = {
  primary: {
    slotId: 'primary',
    kind: 'primary',
    isOpen: false,
    selectedAgentKey: 'main',
    sessionKey: 'agent:main:main',
    draft: '',
    attachments: [],
    pendingRunId: null,
    streamingMessageId: null,
    modelName: '—',
    contextWindow: 0,
    contextUsed: 0,
    unread: 0,
    layoutMode: 'docked-right',
  },
  'secondary-1': null,
  'secondary-2': null,
  'secondary-3': null,
};
```

说明：

- `selectedAgentKey` 和 `sessionKey` **按窗口**存储，而非全局。
- 草稿文本、待上传附件、流式传输状态、模型信息和未读计数也是按窗口存储的。
- 会话历史仍然通过 `sessionKey` 从 OpenClaw 获取；窗口仅指向它正在渲染的会话。
- 如果两个窗口有意指向同一个 `sessionKey`，两者应渲染相同的对话流，但保留各自独立的本地草稿/布局状态。

## 3) 共享 UI/组件逻辑

**不要**将聊天逻辑复制为 4 份。

构建一个可复用的系统：

- `createChatWindow(slotId, containerEl)`
- `renderChatWindow(slotState)`
- `bindChatWindowEvents(slotState, elements)`
- `loadChatHistory(slotState)`
- `connectChatStream(slotState)`
- `sendChatMessage(slotState)`
- `resetChatSession(slotState)`
- `destroyChatWindow(slotId)`

实现规则：

- 将现有的单例（如 `chatPanel`、`chatMessages`、`chatInput`、`chatStatus`、`SESSION_KEY` 和 `currentAgentKey`）替换为**基于槽位的作用域状态对象**。
- 保持一份共享的标记模板和一份共享的 CSS 代码块。
- 在每个窗口根元素上使用 `data-chat-slot="primary|secondary-1|secondary-2|secondary-3"`。
- 事件处理器从最近的 `[data-chat-slot]` 根元素解析槽位，而不是使用全局 DOM id。

推荐拆分：

- `chat.js` 负责 `ChatWindowManager`、共享渲染、WebSocket/RPC 助手和槽位生命周期。
- HTML 包含一个宿主容器，而不是四个硬编码的完整聊天面板。
- CSS 样式 `.chat-panel` 通用，仅使用 `.chat-panel--primary` / `.chat-panel--secondary` 等修饰符处理布局差异。

## 4) 会话 + 连接策略

使用**共享传输，隔离窗口状态**。

- 一次网关令牌获取。
- 每个页面一个 WebSocket 连接管理器。
- 窗口实例根据 `sessionKey` 订阅/取消订阅。
- RPC 助手保持共享，但消息路由包含 `slotId` + `sessionKey`。
- 流式回调按 `runId -> slotId` 映射，使部分响应落在正确的窗口中。

这样避免了四个独立的 WebSocket 栈，同时保持每个聊天视图的独立性。

## 5) 辅助窗口创建规则

当辅助窗口打开时：

1. 找到请求的槽位（`secondary-1`、`secondary-2`、`secondary-3`）。
2. 如果为空，则创建窗口状态，方式为：
   - 从主窗口克隆目标，或
   - 用户明确选择的代理/会话。
3. 将共享聊天模板挂载到槽位容器中。
4. 加载该槽位的 `sessionKey` 对应的历史记录。
5. 注册该槽位的流式/未读监听器。

当辅助窗口关闭时：

1. 停止槽位特定的监听器。
2. 不保留任何内容，仅保留服务器备份的聊天历史。
3. 删除该辅助槽位的 DOM。
4. 重新排列剩余的辅助窗口，但不重新编号已占用的槽位。

## 6) 按钮 1、2 和 3：切换行为

将按钮 `1`、`2` 和 `3` 视为 `secondary-1`、`secondary-2` 和 `secondary-3` 的专用切换开关。

### 按钮规则

- 按钮 `1` 切换 `secondary-1`
- 按钮 `2` 切换 `secondary-2`
- 按钮 `3` 切换 `secondary-3`

### 打开行为

- 如果槽位关闭，点击其按钮将打开该特定槽位。
- 打开时的默认目标 = 来自 `primary` 的当前目标。
- 如果该槽位在同一页面生命周期内之前选择了代理且仅被隐藏，则恢复该代理。

### 关闭行为

- 如果槽位打开，点击其按钮将其关闭。
- 关闭一个辅助槽位**不会**关闭或重新定位任何其他槽位。

### 最大窗口行为

- 硬上限始终为总计 4 个窗口。
- 由于按钮映射到固定槽位，除了防止第 4 个辅助窗口存在之外，不需要额外的溢出逻辑。
- 如果全部 3 个辅助窗口已打开，按钮点击仅作为各自槽位的关闭切换。
- 主窗口不受 `1/2/3` 上限的限制，且不能被辅助槽位替代。

### 推荐按钮状态

- 非活跃 = 槽位关闭
- 活跃 = 槽位打开
- 关注点 = 槽位在未聚焦时有未读活动

## 7) 焦点与布局行为

- 主聊天窗口保持锚点窗口，并保留当前的停靠/吸附行为。
- 辅助窗口作为叠列从主聊天区域左侧滑出。
- 获得焦点的窗口获得活动输入光标和最高 z-index。
- 未聚焦的窗口继续流式传输并更新未读计数器。
- 移动端回退：一次仅显示一个聊天窗口；按钮 `1/2/3` 切换显示的辅助槽位。

## 8) 从当前代码迁移

当前代码使用页面级全局变量来管理一个聊天实例。按以下顺序迁移：

1. 提取一个 `slotState` 对象。
2. 将 DOM 查找从 id 改为基于槽位根的查询。
3. 将全局 `SESSION_KEY` / `currentAgentKey` 替换为槽位属性。
4. 将消息渲染/助手函数迁移到共享的槽位感知函数。
5. 添加顶层 `ChatWindowManager` 注册表。
6. 添加辅助槽位按钮和槽位容器。
7. 保持当前主窗口行为不变，逐步添加辅助槽位。

## 9) 验收标准

当所有以下条件成立时，此架构正确：

- 主聊天窗口加 3 个辅助窗口可以作为同一系统存在。
- 每个窗口记住自己选择的代理/会话状态。
- 所有窗口由相同的共享聊天模板和 JS 逻辑渲染。
- 按钮 `1`、`2` 和 `3` 是固定槽位切换开关，具有确定性的打开/关闭行为。
- 不需要按窗口复制的聊天代码。
