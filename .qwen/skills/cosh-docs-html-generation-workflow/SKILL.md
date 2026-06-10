---
name: cosh-docs-html-generation-workflow
description: Practical workflow for generating multi-page .cosh-docs HTML tutorials with parallel agents, SVG assets, and post-generation link verification.
source: auto-skill
extracted_at: '2026-06-06T15:14:23.752Z'
---

# .cosh-docs HTML 生成工作流

## 适用场景

当需要为项目生成多页 HTML 教程站点（.cosh-docs/）时，使用此工作流。特别是：
- 页面数量 >= 4 页
- 需要跨页链接和 SVG 图表资产
- 需要保证离线可打开、无断链

## 核心流程

### 1. 目录初始化

```bash
mkdir -p .cosh-docs/asset
```

### 2. 读取模板

始终从 `cosh-tutorial-html-docs` Skill 的模板出发：
- `assets/guide-template.html` — 目录页模板
- `assets/tutorial-page-template.html` — 详情页模板

保持模板的核心视觉体系不变（浅色背景、白色卡片、柔和阴影、20px 圆角、深色代码块、响应式断点）。

### 3. 并行生成 HTML 页面

使用多个 Agent 并行生成不同类别的页面：
- **结构分析页面**：项目定位、目录地图、架构图
- **主流程链路页面**：启动、发现、状态、聊天、工作流
- **Git 历史溯源页面**：时间线、架构演进、代码增长

每个页面必须包含：
- `<a class="back" href="./guide.html">返回教程目录</a>` 作为首元素
- 独立的 `<nav class="toc">` 本页目录
- 所有跨页引用使用 `./filename.html` 相对路径
- 响应式 CSS（至少包含 820px 和 560px 断点）

### 4. 生成 SVG 图表资产

图表放入 `.cosh-docs/asset/`，使用内联 SVG 而非 Mermaid（保证离线渲染）。

SVG 图表规范：
- 使用 `viewBox` 而非固定宽高，确保响应式
- 使用系统字体栈（`-apple-system, BlinkMacSystemFont, "Segoe UI"`），避免外部字体依赖
- 颜色使用与教程一致的 CSS 变量语义（蓝色=结构、绿色=流程、琥珀色=可选、红色=风险）
- 每个图表只表达一个核心问题，不混入多种信息
- HTML 中使用 `<img src="./asset/filename.svg" alt="描述" />` 引用

### 5. 目录页生成

`guide.html` 必须包含：
- 所有详情页的卡片入口（编号、标题、简介、标签、链接）
- 阅读路径建议（roadmap）
- 风险声明与分析边界（不可验证项、未运行测试、推断图等）
- 按类别分组的标签（结构分析/主流程链路/Git 历史）

### 6. 链接验证（关键！）

**生成后必须执行链接验证，不要假设所有链接都正确。**

```bash
# 检查所有 HTML 页面中的内部链接是否对应实际文件
cd .cosh-docs
for f in *.html; do
  links=$(grep -oP 'href="\./[^"]*"' "$f" 2>/dev/null | sed 's/href="\.\///;s/"//')
  for link in $links; do
    if [ ! -f "$link" ]; then
      echo "BROKEN: $f -> $link"
    fi
  done
done

# 检查所有 SVG 引用是否对应实际文件
grep -rn 'src="./asset/' *.html
ls asset/
```

**常见断链原因：**
- Subagent 建议的页面名与实际生成的文件名不一致（如 `chat-evolution.html` vs `history-timeline.html`）
- 跨页引用时拼写错误
- 删除或合并页面后未更新引用

**修复方式：** 将断链指向最接近的替代页面，而不是创建空洞页面。

### 7. 最终验收清单

- [ ] `guide.html` 存在并可作为入口
- [ ] 所有详情页均可从目录页进入
- [ ] 所有详情页均有"返回目录"链接
- [ ] 所有内部链接无断链（已用脚本验证）
- [ ] 所有 SVG 图片引用对应实际文件
- [ ] 无外部 CDN/字体/脚本依赖（离线可打开）
- [ ] 响应式断点已包含（820px / 560px）
- [ ] 不同 Subagent 的内容未混写进同一正文页
- [ ] 关键判断有文件路径、函数名或 commit hash 证据
- [ ] 风险声明与不可验证项已显式标注

## 页面数量建议

| 项目规模 | 建议页数 | 说明 |
|----------|----------|------|
| 小型（< 20 文件） | 4-5 页 | 总览 + 结构 + 链路 + 历史 |
| 中型（20-100 文件） | 8-12 页 | 可拆分启动、发现、状态、聊天等独立页面 |
| 大型（> 100 文件） | 15+ 页 | 按模块拆分，大模块独立成页 |

**原则：** 不少于 4 页，不把三个 Subagent 的内容混写进同一正文页。

## 常见陷阱

1. **不要假设链接正确** — 生成后立即验证，断链是最常见的质量问题
2. **不要使用 Mermaid** — 离线环境可能无法渲染，优先使用内联 SVG
3. **不要遗漏风险声明** — 未运行测试、未验证的代码区域、推断图都要标注
4. **不要创建空洞页面** — 如果某个建议页面内容不足，合并到最接近的页面而不是单独创建
5. **不要破坏模板样式** — 按主题调整 `--primary` 颜色可以，但不要大幅改动布局、字号、组件间距
