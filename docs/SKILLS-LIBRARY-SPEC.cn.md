> English version: [SKILLS-LIBRARY-SPEC.md](SKILLS-LIBRARY-SPEC.md)

# 技能库功能规格

## 概述
一个集中的技能库，用户可在此管理可复用的技能文件。技能可以应用（复制）到单个智能体。每个智能体获得独立的副本，并可自行定制。

## 数据模型
- **库位置：** `STATUS_DIR/skills-library/`（宿主机可访问的文件夹）
- **每个技能：** 包含 `SKILL.md` 的文件夹（与 OpenClaw 技能格式一致）
  - 路径：`STATUS_DIR/skills-library/<skill-name>/SKILL.md`
- **智能体技能：** 已存在于各智能体的 `WORKSPACE/skills/<skill-name>/SKILL.md`
- **流程：** 库（主副本）→ 复制到智能体 → 智能体拥有其副本

## SKILL.md 格式
```yaml
---
name: skill-name
description: One-line description of what the skill does
---

# Skill Title

Skill content (markdown instructions for the agent)
```

## API 端点（server.py）

### GET /api/skills-library
列出库中的所有技能。
返回：`[{name, description, path}]`，按字母顺序排序。

### GET /api/skills-library/<name>
读取指定技能的 SKILL.md 内容。
返回：`{name, description, content}`

### POST /api/skills-library
在库中创建或更新一个技能。
请求体：`{name: string, content: string}`
- `name` 成为文件夹名称（slugified）
- `content` 为完整的 SKILL.md 内容
- 如果技能已存在，则覆盖它

### DELETE /api/skills-library/<name>
从库中删除一个技能。

### POST /api/skills-library/apply
将库中的技能应用（复制）到智能体。
请求体：`{skill: string, agentId: string}`
- 复制 `skills-library/<skill>/SKILL.md` → 到智能体的 `workspace/skills/<skill>/SKILL.md`
- 如有必要则创建智能体的技能文件夹
- 如果智能体已有该技能则不覆盖（返回警告）

### POST /api/skills-library/upload
上传一个 SKILL.md 文件到库中。
请求体：`{filename: string, content: string}`（base64 内容）

## 用户界面（game.js）

### 侧边栏入口
- 在侧边栏菜单的“📊 会议”下添加“📚 技能库”
- 打开一个模态面板（与会议面板模式相同）

### 技能库面板模态框
**布局：**
- 标题栏：“📚 技能库”及关闭按钮
- 顶部栏：“➕ 添加技能”按钮、文件上传按钮（📎）
- 技能列表：按字母顺序排列的卡片

**技能卡片：**
- 技能名称（粗体）、描述（灰色文字）
- “📋 应用到智能体”按钮 → 打开智能体下拉列表
- “✏️ 编辑”按钮 → 打开编辑器
- “🗑️ 删除”按钮 → 确认对话框

**应用流程：**
- 点击“应用到智能体” → 所有智能体的下拉列表（来自 /agents-list）
- 选择智能体 → POST /api/skills-library/apply
- 成功提示：“✅ 已将 {skill} 应用到 {agent}”
- 如果智能体已有该技能：警告提示，并提供覆盖选项

**添加/编辑流程：**
- 打开编辑器，包含名称字段和内容文本区域
- 保存 → POST /api/skills-library
- 编辑器应为全高度，等宽字体用于 Markdown

**上传流程：**
- 文件选择器，选择 .md 文件
- 读取文件，从 frontmatter 或文件名中提取名称
- POST /api/skills-library/upload

## 文件结构
```
STATUS_DIR/
└── skills-library/
    ├── continuous-work/
    │   └── SKILL.md
    ├── another-skill/
    │   └── SKILL.md
    └── ...
```

## 备注
- 库对宿主机可访问 — 用户也可直接管理文件
- UI 是便捷层，文件是真实来源
- 智能体的副本是独立的 — 编辑不会同步回库
- 训练器智能体使用智能体专属副本，而非库原始文件
- 仅产品变更；适用于 My Virtual Office 应用。
