## 产品层面检查

需求明确：拆分 `game.js`，不改功能，不变行为。无产品歧义。

## 技术方案评审

### 现状分析

`game.js` 16,568 行，所有内容在全局作用域。文件末尾执行 `loop()` 启动游戏循环。代码组织方式：

- 模块级变量声明（`var`）散布在整个文件
- 函数定义与变量声明交错
- 约 29 个逻辑模块混合在一起
- 通过全局变量名与其他 JS 文件（`chat.js`, `i18n.js`, `projects.js` 等）交互

### 识别出的 29 个逻辑模块及归属分组

#### 分组 A：核心运行时（拆分后由主文件加载并装配）
| 模块 | 行号 | 说明 |
|---|---|---|
| Config & State | 1-155 | canvas 尺寸、officeConfig、colorFavorites |
| Branch System | 111-155 | 分支列表、缓存、映射 |
| Office Config | 157-196 | walls、furniture、topWallSection |
| Canvas & Camera | 1292-1370 | resizeCanvas、screenToWorld、camera、zoom |
| Mouse/Touch | 1371-1499 | 平移、缩放、点击处理 |
| Locations & Spots | 1500-1610 | LOCATIONS、meetingTable、interactionSpots |
| Collision System | 371-420 | isSpotOccupied、findOpenSpot、queue offset |
| Performance | 1161-1260 | FPS、性能分析、rim light cache |
| Game Loop | 9510-9500+ | loop()、Agent.update()、Pet.update()、渲染调度 |

#### 分组 B：编辑器子系统
| 模块 | 行号 | 说明 |
|---|---|---|
| Edit Mode State | 198-209 | editMode、multi-select 状态 |
| Snap Zones | 210-220 | 5 区域吸附系统 |
| Undo/Save | 221-269 | undoStack、saveEdits |
| Furniture Placement | 271-364 | 拖放、ghost、catalog、选中 |
| Wall Placement | 366-369 | wall 绘制模式 |
| Default Furniture | 1687-1688 | getDefaultFurniture() |
| Edit Mode Interactions | 13678-14665 | 编辑模式下的鼠标交互、color picker 等 |

#### 分组 C：视觉渲染
| 模块 | 行号 | 说明 |
|---|---|---|
| Agent Class | 2326-4130+ | Agent 构造、外观解析、desk assignment |
| Agent Appearance | 1917-2330 | 发型、服装、头饰、眼镜、道具、面部毛发绘制 |
| Environment Drawing | 4772-6316+ | drawEnvironment、墙壁、家具绘制函数 |
| Weather Rendering | 421-1057 | 天气粒子、积雪、闪电、窗口雨滴 |
| Time of Day | 1058-1159 | 光照参数、时间流逝 |
| Bubbles | 4146-4265 | 气泡绘制、最小化图标 |

#### 分组 D：UI 面板
| 模块 | 行号 | 说明 |
|---|---|---|
| Main Menu | 12439-13677 | 设置面板、保存/导出/导入/重置 |
| Agent Creator Panel | 12889-13635 | Agent 外观自定义 |
| Skill Workshop | 14666-15178 | 技能提案审查 |
| Agent Skills | 14973-15178 | Agent 绑定技能管理 |
| Meetings Dashboard | 15179-16316 | 会议看板、历史、实时轮询 |
| Skills Library | 16317-16568+ | 技能库浏览/编辑/上传 |

### 拆分策略对比

**方案 A：ES6 模块（`type="module"`）** ✅ 推荐
- 优点：原生 `import`/`export`，浏览器原生支持，无构建依赖，作用域隔离干净。
- 缺点：需要 HTML 中改为 `<script type="module">`，IIFE 类全局变量 `var` 需显式 `export`。
- 风险：某些通过全局变量名引用的函数需要显式 `window.fnName = fnName` 暴露。

**方案 B：IIFE 包裹 + 命名空间**
- 优点：不改 HTML 加载方式，兼容性更好。
- 缺点：仍是全局作用域，只是加了一层命名空间；无法真正模块化。

**方案 C：保留 `<script>` 标签顺序加载 + 拆文件**
- 优点：改动最小。
- 缺点：不解决全局命名污染，只是把一个大文件切成多个，仍无模块化。

**推荐方案 A**：ES6 模块。所有现代浏览器均支持 `type="module"`，且模块间依赖关系通过 `import`/`export` 显式声明，可读性和可维护性大幅提升。

### 关键依赖分析

以下函数被其他 JS 文件通过全局变量引用，拆分后必须显式暴露到 `window`：

- `toggleMainMenu` — 被主界面按钮调用
- `toggleAgentPanel` — Agent 面板入口
- `getBranchList`, `getBranchById`, `getBranchDisplayName` — 被 chat.js 使用
- `_fetchRoster`, `getInteractionSpots`, `buildCollisionGrid` — 被其他模块使用
- `updateMeetingLabels`, `openMeetingsDashboard` — 会议入口
- `openSkillsLibrary`, `refreshSkillsList` — 技能库入口
- `editMode` — 可能被外部读取
- `saveOfficeConfig`, `loadOfficeConfig` — 配置持久化

### 迁移步骤建议

1. 先将全局变量集中到 `game-state.js` 模块。
2. 按分组顺序逐模块抽取，每个模块 `export` 其对外接口。
3. 主入口 `game.js` 改为 `import` 各模块 + 装配 + 启动。
4. 需要暴露到 `window` 的 API 显式赋值。
5. 更新 HTML 中脚本加载（删除旧 `game.js`，新增 `<script type="module" src="app/game.js">`）。
6. 每拆一个模块后验证渲染和交互无回归。

### 阻塞问题

无阻塞技术问题。方案 A（ES6 模块）可行且风险可控。

### 评审结论

方案可行，进入 checklist 阶段。
