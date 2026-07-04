> English version: [UNIVERSAL-AGENT-HARNESS-SPEC.md](UNIVERSAL-AGENT-HARNESS-SPEC.md)

# 通用代理管理器规范

状态：草案 v0.1  
所有者：Eli / My Virtual Office  
范围：将 My Virtual Office 从一个 OpenClaw 特定的控制面转变为一个通用的多提供商办公运行时，能够同时托管、路由、可视化和协调来自多个系统的代理。

---

## 1. 摘要

My Virtual Office 应从：

- 一个连接到一个 OpenClaw 后端的办公室

演变为：

- 一个能够同时托管来自多个提供商系统的代理的办公运行时
- 一个共享的代理目录、任务空间、消息总线和项目模型
- 一个办公室，其中 OpenClaw 代理可以与 Hermes 代理通信，后者又可以与 Claude Code 或 Codex 工作器通信，所有这些都是办公室的一等公民

本规范定义了该通用管理器的架构。

---

## 2. 产品目标

用户应能够：

- 将多个代理提供商连接到一个办公室
- 在一个共享办公室中同时查看所有代理
- 从单一 UI 与任何代理聊天
- 让代理跨提供商相互发送消息
- 跨提供商分配项目和任务
- 跨提供商运行自动化
- 管理大部分统一设置体验，同时在需要时保留提供商特定的功能

示例目标场景：

- `openclaw:elix` 将研究任务委托给 `hermes:research-1`
- `hermes:research-1` 要求 `claude-code:frontend-dev` 检视一个仓库
- `codex:reviewer` 审查输出
- 所有活动出现在同一个办公室、同一会议系统、同一项目、同一任务线程中

---

## 3. 非目标

本项目不应尝试：

- 替换 OpenClaw、Hermes、Claude Code、Codex 等提供商的本地运行时内部结构
- 强制所有提供商暴露相同的原生功能集
- 将每个提供商的特定能力完全标准化为一个最小公分母 UI
- 要求提供商在变得有用之前实现全新的外部协议

办公室是一个代理器和控制平面，而不是对每个提供商的重实现。

---

## 4. 核心架构决策

My Virtual Office 成为提供商运行时之上的**共享办公运行时**。

### 4.1 层次

1. **办公运行时 / 代理器**
   - 办公室身份、路由、项目、任务、会议和标准化事件的权威记录系统

2. **提供商适配器**
   - 将外部系统连接到办公室
   - 示例：OpenClaw 适配器、Hermes 适配器、Claude Code 适配器、Codex 适配器

3. **办公 UI**
   - 呈现标准化的办公室状态，而非原始提供商负载

### 4.2 重要结果

提供商之间不直接通信。

它们通过办公运行时进行通信：

- 代理 A 向代理器发送消息
- 代理器解析接收者、权限、项目上下文和线程
- 接收者适配器将消息传递到接收者提供商
- 适配器将标准化事件返回给代理器
- 代理器更新办公室状态并分发

这保持了产品的一致性。

---

## 5. 支持的提供商类别

系统必须支持多个适配器类别。

### 5.1 运行时提供商

具有自身会话和代理概念的完整代理运行时。

示例：
- OpenClaw
- Hermes
- 未来的编排器

### 5.2 管理器提供商

由办公室管理的 CLI 或基于会话的编码代理。

示例：
- Claude Code
- Codex
- Gemini CLI
- OpenCode
- Aider

### 5.3 API 提供商

可以作为代理行事的 HTTP 或 WebSocket 服务。

示例：
- 自定义内部 AI 服务
- 托管的编排器
- 特定领域的远程代理

---

## 6. 标准化办公室模型

以下模型是产品的真理。提供商数据被映射到这些模型中。

## 6.1 OfficeAgent

```ts
export type OfficeAgent = {
  id: string;                     // canonical office id, e.g. "openclaw:elix"
  providerId: string;             // e.g. "openclaw-main", "hermes-local", "claude-code"
  providerType: "runtime" | "harness" | "api";
  providerAgentId: string;        // native provider id
  name: string;
  role: string | null;
  branchId: string | null;
  deskId: string | null;
  avatar: OfficeAvatar | null;
  status: OfficeAgentStatus;
  capabilities: string[];
  projectIds: string[];
  tags: string[];
  metadata: Record<string, unknown>;
  createdAt: number;
  updatedAt: number;
};
```

### 6.2 OfficeAgentStatus

```ts
export type OfficeAgentStatus =
  | "offline"
  | "idle"
  | "working"
  | "thinking"
  | "meeting"
  | "waiting_input"
  | "waiting_approval"
  | "error";
```

### 6.3 OfficeThread

```ts
export type OfficeThread = {
  id: string;
  projectId: string | null;
  title: string | null;
  participants: string[]; // OfficeAgent ids
  visibility: "private" | "project" | "office";
  source: "user" | "agent" | "system";
  createdAt: number;
  updatedAt: number;
};
```

### 6.4 OfficeMessage

```ts
export type OfficeMessage = {
  id: string;
  threadId: string;
  senderAgentId: string | null;
  senderKind: "user" | "agent" | "system";
  text: string;
  attachments: OfficeAttachment[];
  providerRef?: {
    providerId: string;
    nativeSessionId?: string;
    nativeMessageId?: string;
    nativeRunId?: string;
  };
  createdAt: number;
};
```

### 6.5 OfficeProject

```ts
export type OfficeProject = {
  id: string;
  name: string;
  description: string | null;
  rootPath: string | null;
  repoUrl: string | null;
  defaultBranch: string | null;
  linkedAgentIds: string[];
  sharedContextId: string | null;
  tags: string[];
  createdAt: number;
  updatedAt: number;
};
```

### 6.6 OfficeAutomation

```ts
export type OfficeAutomation = {
  id: string;
  name: string;
  targetAgentId: string | null;
  targetThreadId: string | null;
  projectId: string | null;
  schedule: OfficeSchedule;
  action: OfficeAutomationAction;
  executor: {
    kind: "provider-native" | "office-runtime";
    providerId?: string;
  };
  enabled: boolean;
  lastRunAt: number | null;
  lastStatus: "ok" | "error" | null;
  createdAt: number;
  updatedAt: number;
};
```

### 6.7 OfficePromptPack

标准的提示/个性表示。

```ts
export type OfficePromptPack = {
  identity: string | null;
  mission: string | null;
  style: string | null;
  boundaries: string | null;
  memory: string | null;
  userContext: string | null;
  projectContext: string | null;
  extraSections: Array<{ key: string; title: string; content: string }>;
  updatedAt: number;
};
```

重要说明：`AGENTS.md`、`SOUL.md`、`USER.md`、`MEMORY.md` 等是该模型在提供商/工作区中的具体化，而非权威真理。

---

## 7. 能力模型

每个提供商和每个代理都可以暴露能力。

```ts
export type OfficeCapability =
  | "chat"
  | "streaming"
  | "projects"
  | "workspace"
  | "files.read"
  | "files.write"
  | "shell"
  | "automation.native"
  | "automation.office"
  | "approvals.native"
  | "settings.raw"
  | "multi-agent"
  | "agent-management"
  | "prompt-pack.sync"
  | "sessions.persistent"
  | "review"
  | "browser"
  | "voice";
```

规则：

- UI 必须根据能力来屏蔽功能
- 不支持的功能必须隐藏或标记为不可用
- 没有伪造的成功路径
- 如果办公室能够安全地模拟某个功能，则将其暴露为办公室所有，而非原生功能

---

## 8. 提供商适配器契约

每个提供商适配器实现一个共享契约。

```ts
export interface OfficeProviderAdapter {
  id: string;
  label: string;
  type: "runtime" | "harness" | "api";

  connect(): Promise<void>;
  disconnect(): Promise<void>;
  health(): Promise<ProviderHealth>;

  listAgents(): Promise<ProviderAgentRecord[]>;
  getAgent(providerAgentId: string): Promise<ProviderAgentRecord | null>;
  createAgent?(input: CreateProviderAgentInput): Promise<ProviderAgentRecord>;
  updateAgent?(providerAgentId: string, patch: ProviderAgentPatch): Promise<void>;
  deleteAgent?(providerAgentId: string): Promise<void>;

  listThreads?(agentId?: string): Promise<ProviderThreadRecord[]>;
  getThreadMessages?(threadId: string): Promise<ProviderMessageRecord[]>;

  sendMessage(input: ProviderSendMessageInput): Promise<ProviderSendMessageResult>;
  interrupt?(input: ProviderInterruptInput): Promise<void>;

  syncPromptPack?(providerAgentId: string, promptPack: OfficePromptPack): Promise<void>;
  loadPromptPack?(providerAgentId: string): Promise<OfficePromptPack | null>;

  bindProject?(providerAgentId: string, project: OfficeProject): Promise<void>;

  listAutomations?(providerAgentId?: string): Promise<ProviderAutomationRecord[]>;
  upsertAutomation?(input: ProviderAutomationInput): Promise<void>;
  deleteAutomation?(automationId: string): Promise<void>;

  supports(capability: OfficeCapability): boolean;
  subscribe(listener: (event: ProviderEvent) => void): () => void;
}
```

---

## 9. 办公运行时职责

办公运行时，称为 **Office Broker**，拥有以下职责。

### 9.1 注册表

- 维护标准化的办公室代理 ID
- 将提供商代理映射到办公室代理
- 处理提供商的连接/断开
- 持久化办公室专用属性，如头像、办公桌、分支、标签

### 9.2 路由
- 路由用户到智能体、智能体到智能体以及系统到智能体的消息
- 解析目标提供者适配器
- 在提供者之间维护共享线程
- 强制执行权限和可见性

### 9.3 事件标准化

- 消费提供者原生事件
- 标准化为办公事件
- 分发给UI和内部系统

### 9.4 状态持久化

- 智能体
- 线程
- 消息
- 项目
- 会议
- 自动化
- 办公布局偏好
- 提供者连接配置

### 9.5 存在/动画映射

- 将运行时状态转换为办公状态
- 驱动行走、坐下、思考、开会、错误指示器等

### 9.6 自动化执行

- 当提供者原生调度不可用时，运行办公层拥有的自动化
- 可选地，在支持的情况下将原生自动化委托给提供者

---

## 10. 办公事件模型

办公UI应消费办公原生事件，而非原始提供者载荷。

```ts
export type OfficeEvent =
  | { type: "agent.registered"; agent: OfficeAgent }
  | { type: "agent.updated"; agent: OfficeAgent }
  | { type: "agent.removed"; agentId: string }
  | { type: "agent.status.changed"; agentId: string; status: OfficeAgentStatus }
  | { type: "thread.created"; thread: OfficeThread }
  | { type: "message.created"; message: OfficeMessage }
  | { type: "message.delta"; threadId: string; senderAgentId: string; textDelta: string }
  | { type: "task.updated"; taskId: string; status: string }
  | { type: "meeting.updated"; meetingId: string; state: string }
  | { type: "automation.updated"; automation: OfficeAutomation }
  | { type: "provider.health"; providerId: string; health: ProviderHealth };
```

提供者适配器可能仍然为高级工具发出提供者特定的载荷，但办公UI不应依赖它们。

---

## 11. 跨提供者消息模型

这是通用中枢的定义性特性。

## 11.1 规则

- 所有跨提供者消息都通过办公代理（Office Broker）传递
- 每条消息都属于一个办公线程
- 提供者原生会话是链接的，而非被视为规范线程
- 代理负责关联ID和对话拼接

## 11.2 流程

1. 发送者创建或追加到办公线程
2. 代理存储规范消息
3. 代理解析接收者适配器
4. 适配器将消息传递给原生提供者会话
5. 适配器发出标准化的增量/最终输出
6. 代理将这些追加回同一办公线程

## 11.3 上下文策略

每次发送操作可以定义以下之一：

- `full-thread` — 发送最近的办公线程上下文
- `project-summary` — 发送项目摘要和最近N条消息
- `task-brief` — 仅发送精简的任务简报
- `custom` — 由发送者或系统准备的显式适配器输入

这避免了不受控制的对话膨胀。

---

## 12. 设置架构

设置必须按层拆分。

## 12.1 办公层拥有的设置

示例：
- 工位分配
- 头像/外观
- 分支/团队位置
- 办公室房间行为
- 移动偏好
- 可见标题和徽章样式
- 办公通知偏好

这些不属于任何提供者。

## 12.2 通用智能体设置

示例：
- 显示名称
- 角色/标题
- 提示包
- 边界
- 项目分配
- 自动化目标
- 标签

这些是规范的办公设置，可选地同步到提供者。

## 12.3 提供者支持的设置

示例：
- OpenClaw工具策略、执行审批、沙箱模式
- Hermes编排配置
- Claude Code模型/权限模式/工作区策略
- Codex执行配置

这些显示在提供者特定的标签页中。

## 12.4 原始高级设置

示例：
- 原始配置文件
- 原始工作区文件编辑器
- 提供者原生调试/状态

这应仅为高级模式。

---

## 13. 提示包物化

办公层应编辑规范的提示数据，然后将其物化为提供者特定的形状。

### 13.1 OpenClaw物化

可能的文件：
- `AGENTS.md`
- `SOUL.md`
- `USER.md`
- `MEMORY.md`
- `memory/YYYY-MM-DD.md`

### 13.2 Hermes物化

选项：
- 同步到Hermes智能体指令/系统提示
- 可选地，如果存在基于工作区的模式，则写入适配器管理的文件

### 13.3 Claude Code / Codex物化

选项：
- 作为会话引导系统上下文注入
- 在工作区文件夹内写入办公层管理的提示文件，例如`.office/`
- 将项目提示包同步到工作树引导文件夹

规则：UI编辑`OfficePromptPack`，而非原始`AGENTS.md`作为主要用户体验。

---

## 14. 项目架构

项目必须是办公层的一等对象。

### 14.1 规范项目所有权

办公运行时拥有：
- 项目标识
- 仓库/根路径元数据
- 共享上下文
- 链接的智能体
- 活跃任务
- 项目级线程

### 14.2 提供者绑定

每个提供者可以不同方式绑定项目。

#### OpenClaw
- 工作区路径
- 项目文件夹
- 工作区中的技能/上下文

#### Hermes
- 共享项目上下文
- 链接的子智能体
- 可选的基于工作区的绑定（如果支持）

#### Claude Code / Codex
- 仓库检出或工作树路径
- 会话当前工作目录
- 引导提示文件
- 分支/工作树策略

项目不仅仅是"OpenClaw内的文件夹"。那只是其中一种提供者策略。

---

## 15. 自动化架构

当前的OpenClaw原生cron模型将变为通用自动化模型。

### 15.1 规范的办公自动化

用户在一个UI中创建自动化。

每个自动化选择执行者：

- `provider-native` 当提供者支持可靠的原生调度时
- `office-runtime` 当办公层应自行调度和分派动作时

### 15.2 为何重要

这允许：
- OpenClaw智能体在需要时使用OpenClaw cron
- Hermes智能体在可用时使用Hermes原生调度
- Claude Code或Codex智能体仍能通过办公层运行的调度参与

### 15.3 UI规则

主UI显示`Automations`，而非`OpenClaw Cron`。

高级视图仍可暴露提供者原生调度器详情。

---

## 16. Claude Code和Codex集成模型

Claude Code和Codex应作为**中枢支持的提供者**处理。

## 16.1 原因

它们不是OpenClaw意义上的完整网关运行时。
它们是受管理会话和工作进程。

## 16.2 办公适配器拥有什么

- 会话启动/恢复/终止
- 工作区绑定
- 运行状态检测
- 对话持久化
- 提示包注入
- 活动标准化
- 将原生会话状态映射为办公存在状态

## 16.3 办公存在映射

- 空闲 → 坐着/游荡
- 运行中 → 打字/工作状态
- 等待输入 → 可见提示/举手指示器
- 等待审批 → 审批指示器
- 错误 → 红色徽章/错误气泡
- 完成 → 报告气泡/任务完成状态

---

## 17. OpenClaw适配器预期

OpenClaw适配器应暴露强大的原生支持：

- 智能体
- 会话
- 流式聊天
- 文件
- cron
- 审批
- 提示包同步
- 项目绑定

OpenClaw仍是一等提供者，但它不是产品真理。

---

## 18. Hermes适配器预期

Hermes适配器应暴露：

- 智能体注册表或合成团队注册表
- 会话和线程映射
- 流式聊天
- 编排事件
- 可能情况下的提示包同步
- 自动化支持（原生或办公层拥有的）

Hermes可能需要比OpenClaw更多的适配器拥有的结构。这是可以接受的。

---

## 19. 安全模型

### 19.1 服务端提供者访问

在可避免的情况下，浏览器不应直接持有提供者密钥。

办公服务器应：
- 管理提供者令牌和凭证
- 代理提供者API连接
- 向UI暴露同源WebSocket/HTTP API

### 19.2 隔离

中枢支持的提供者应支持工作区隔离策略。

示例：
- 每个智能体的工作区
- 每个项目的工作树
- 用于审查智能体的只读项目挂载
- 显式的破坏性操作门控

### 19.3 跨提供者权限

代理必须支持类似以下的策略决策：
- 该智能体能否向那个智能体发消息
- 该智能体能否访问那个项目
- 该自动化能否调用那个中枢
- 该提供者能否看到办公全局线程

---

## 20. 持久化

办公运行时需要持久存储以下内容：

- 提供者配置
- 办公智能体和元数据
- 线程和消息
- 项目
- 自动化
- 提示包
- 办公层专用设置
- 提供者原生映射引用

建议规则：
- 提供者原生数据在适当时保留在其提供者中
- 办公关联、布局、路由和共享对话数据保留在办公存储中

---

## 21. 推荐UI结构

## 21.1 智能体设置标签页

### 核心标签页
- 身份
- 大脑
- 工作区
- 项目
- 自动化
- 办公

### 提供者标签页
- OpenClaw
- Hermes
- Claude Code
- Codex
- 高级

## 21.2 提供者目录

添加一个提供者管理界面，显示：
- 已连接的提供者
- 健康状态
- 上次同步时间
- 支持的能力
- 认证状态
- 智能体数量

## 21.3 智能体目录
全办公室范围的目录，可按以下条件筛选：
- 提供商
- 分支
- 项目
- 状态
- 能力

---

## 22. 交付阶段

## 阶段一 - 办公室运行时基础

交付内容：
- 办公室代理器
- 规范办公室模型
- 事件总线
- 提供商注册表
- 提供商健康状态展示
- 标准化线程/消息持久化

成功条件：
- 办公室能够托管多个提供商，而无需 UI 硬编码某个特定提供商的形态

## 阶段二 - OpenClaw 一等适配器

交付内容：
- 将当前 OpenClaw 特定的行为封装在提供商契约之后
- 保持现有办公室体验正常工作

成功条件：
- OpenClaw 在新抽象层下保持完全可用

## 阶段三 - Hermes 适配器

交付内容：
- Hermes 提供商支持
- 跨提供商消息传递（OpenClaw 与 Hermes 之间）

成功条件：
- OpenClaw 智能体和 Hermes 智能体可以共存于同一办公室中，并通过代理器交换消息

## 阶段四 - Harness 基础层

交付内容：
- 通用 harness 提供商框架
- 会话管理器
- 对话记录捕获
- 工作区绑定
- 状态映射

成功条件：
- 办公室能够将非网关智能体作为一等办公室工作者托管

## 阶段五 - Codex 实时桥接

交付内容：
- 在阶段四 Codex harness 适配器背后的实时 Codex 桥
- 从虚拟办公室到实际 Codex CLI/会话的消息转发
- 单个 Codex 协作者的会话生命周期
- 最终回复、错误、超时及基本状态传播回办公室事件
- 单消息实时执行与后续项目自动化之间的清晰边界

成功条件：
- 用户、OpenClaw 智能体或 Hermes 智能体可以通过办公室向 Codex 发送一条消息，Codex 通过实时桥执行，办公室记录真实的响应和状态事件

## 阶段六 - Claude Code 适配器与高级 Codex 会话

交付内容：
- 基于相同 harness 基础层构建的 Claude Code 提供商
- 提示包注入
- 工作区和项目绑定
- 流式 Codex 状态/工具事件
- 取消、超时、权限提示以及更长的任务会话控制

成功条件：
- Claude Code 能够与 OpenClaw、Hermes 和 Codex 一同参与办公室；Codex 实时会话可被管理，不再仅限于单次最终回复

## 阶段七 - 通用自动化与项目

交付内容：
- 办公室拥有的自动化
- 通用项目注册表
- 提供商绑定策略

成功条件：
- 自动化和项目不再是 OpenClaw 独有概念

---

## 23. 从当前状态迁移的策略

当前状态：
- 我的虚拟办公室原生基于 OpenClaw
- 许多 UX 概念直接映射到 OpenClaw 的文件、定时任务和工作区约定

迁移计划：

1. 保持当前 OpenClaw 行为正常工作
2. 在现有 UI 背后引入代理器和提供商抽象
3. 逐步将规范真理从 OpenClaw 特定假设迁移到办公室原生模型
4. 保留提供商原生的高级面板供高级用户使用
5. 仅在办公室自有系统准备就绪后，才将顶层 UI 标签（如“定时任务”）替换为“自动化”

这样可以避免标志日重写。

---

## 24. 待解答问题

- 办公室运行时应使用哪个持久化层来存储规范代理器状态？
- 办公室线程是否应始终是规范化的，还是某些提供商原生线程在 1:1 聊天视图中仍应保持为主？
- 如何为 harness 提供商配置项目工作树？
- 提示包的具体化应该基于文件还是基于会话注入？
- 智能体间的消息传递应该采用显式收件箱路由、共享项目线程，还是两者兼有？
- 如何将会议参与映射到实际的提供商任务和锁？
- 提供商适配器应运行在进程内、边车进程中还是远程微服务中？

---

## 25. 建议

将“我的虚拟办公室”构建为**具有提供商适配器的通用办公室运行时**，而不是：
- 一次选择一个后端
- 或者一个必须让其他所有系统永久模仿的 OpenClaw 形垫片

该架构是实现以下目标的最清晰路径：
- 多提供商团队
- 跨提供商协作
- 一等支持的 Claude Code 和 Codex 工作者
- 无需重新设计整个产品即可支持未来更多提供商

---

## 26. 下一步需编写的规范

在本规范之后，下一个文档应为：

1. `OFFICE-BROKER-API-SPEC.md`
2. `PROVIDER-ADAPTER-SDK-SPEC.md`
3. `HARNESS-PROVIDER-SPEC.md`
4. `UNIVERSAL-AUTOMATIONS-SPEC.md`
5. `UNIVERSAL-PROJECTS-SPEC.md`
6. `PROMPT-PACK-MATERIALIZATION-SPEC.md`
7. `CLAUDE-CODE-ADAPTER-SPEC.md`
8. `CODEX-ADAPTER-SPEC.md`
