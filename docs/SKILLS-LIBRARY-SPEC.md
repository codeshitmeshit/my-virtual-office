> 中文版: [SKILLS-LIBRARY-SPEC.cn.md](SKILLS-LIBRARY-SPEC.cn.md)

# Skills Library Feature Spec

## Overview
A central Skills Library where users manage reusable skill files. Skills can be applied (copied) to individual agents. Agents get their own independent copy they can customize.

## Data Model
- **Library location:** `STATUS_DIR/skills-library/` (host-accessible folder)
- **Each skill:** A folder containing `SKILL.md` (matches OpenClaw skill format)
  - Path: `STATUS_DIR/skills-library/<skill-name>/SKILL.md`
- **Agent skills:** Already exist at `WORKSPACE/skills/<skill-name>/SKILL.md` per agent
- **Flow:** Library (master) → Copy to agent → Agent owns their copy

## SKILL.md Format
```yaml
---
name: skill-name
description: One-line description of what the skill does
---

# Skill Title

Skill content (markdown instructions for the agent)
```

## API Endpoints (server.py)

### GET /api/skills-library
List all skills in the library.
Returns: `[{name, description, path}]` sorted alphabetically.

### GET /api/skills-library/<name>
Read a specific skill's SKILL.md content.
Returns: `{name, description, content}`

### POST /api/skills-library
Create or update a skill in the library.
Body: `{name: string, content: string}`
- `name` becomes the folder name (slugified)
- `content` is the full SKILL.md content
- If skill exists, overwrites it

### DELETE /api/skills-library/<name>
Delete a skill from the library.

### POST /api/skills-library/apply
Apply (copy) a library skill to an agent.
Body: `{skill: string, agentId: string}`
- Copies `skills-library/<skill>/SKILL.md` → agent's `workspace/skills/<skill>/SKILL.md`
- Creates the agent skill folder if needed
- Does NOT overwrite if agent already has it (returns warning)

### POST /api/skills-library/upload
Upload a SKILL.md file to the library.
Body: `{filename: string, content: string}` (base64 content)

## UI (game.js)

### Sidebar Entry
- Add "📚 Skills Library" under "📊 Meetings" in the sidebar menu
- Opens a modal dashboard (same pattern as Meetings Dashboard)

### Skills Library Dashboard Modal
**Layout:**
- Header: "📚 Skills Library" with close button
- Top bar: "➕ Add Skill" button, file upload button (📎)
- Skill list: cards in alphabetical order

**Skill Card:**
- Skill name (bold), description (gray text)
- "📋 Apply to Agent" button → opens agent dropdown
- "✏️ Edit" button → opens editor
- "🗑️ Delete" button → confirmation dialog

**Apply Flow:**
- Click "Apply to Agent" → dropdown of all agents (from /agents-list)
- Select agent → POST /api/skills-library/apply
- Success toast: "✅ Applied {skill} to {agent}"
- If agent already has it: warning toast with option to overwrite

**Add/Edit Flow:**
- Opens editor with name field + content textarea
- Save → POST /api/skills-library
- Editor should be full-height, monospace font for markdown

**Upload Flow:**
- File picker for .md files
- Reads file, extracts name from frontmatter or filename
- POST /api/skills-library/upload

## Classification and Smart Organization

- `SKILL.md` files and skill directories remain the content source of truth. Classification metadata lives in the `.vo-library-catalog.json` sidecar at the Skills Library root.
- A skill has only `primaryCategoryId` and `tags` classification metadata. The system does not add lifecycle states such as pending admission, admitted, or pending organization.
- New, imported, and unclassified skills enter the immutable Default category. Each organization run processes only that category and moves successful items to their destination category.
- Seeded general categories are Default, Development & Testing, Collaboration & Docs, Projects & Process, Operations & Diagnostics, and Knowledge & Content. When a skill clearly does not fit them, the archive manager may create an ordinary category and has final authority over its name and classification.
- Smart organization reuses the Archive Room's existing archive-manager AI; it does not create a separate organizer bot. Start fails explicitly or remains disabled when that manager is missing, unavailable, or busy with other archive work.
- Duplicate starts and manual category corrections are disabled while a run is active. On completion, the header shows only a dismissible result marker. Partial failures remain in Default; the marker opens a failure-only view where the owner can move one skill at a time.
- Category correction is an owner management operation. It uses management-token authorization and a catalog revision; on revision conflict, the client refreshes authoritative state instead of overwriting it.
- The MCP Registry keeps its separate entry point and does not appear in the Skills Library modal. The product currently has no team-space concept, and this feature neither introduces nor depends on one.

### Classification and Organization APIs

- `GET /api/skills-library` returns skills, categories, catalog revision, the latest organization summary, and archive-manager availability.
- `POST /api/skills-library/organization/runs` starts an organization run limited to Default.
- `POST /api/skills-library/<name>/category` moves one skill manually with `{categoryId, expectedRevision}`.
- `POST /api/skills-library/organization/dismiss` dismisses the header result marker.

## File Structure
```
STATUS_DIR/
└── skills-library/
    ├── .vo-library-catalog.json
    ├── continuous-work/
    │   └── SKILL.md
    ├── another-skill/
    │   └── SKILL.md
    └── ...
```

## Notes
- Library is host-accessible — users can manage files directly too
- The UI is a convenience layer, files are source of truth
- Agent copies are independent — edits don't sync back to library
- Trainer agent uses agent-specific copies, not library originals
- Product change only; applies to the My Virtual Office app.
