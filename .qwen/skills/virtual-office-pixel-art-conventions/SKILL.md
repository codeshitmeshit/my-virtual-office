---
name: virtual-office-pixel-art-conventions
description: Conventions for the project's "Soft Pixel Art" style — characters, furniture, and UI are all hand-drawn via Canvas API with no external images.
source: auto-skill
extracted_at: '2026-06-09T12:00:00.000Z'
---

# Virtual Office — Soft Pixel Art Conventions

All scene elements (characters, desks, plants, bookshelves, costumes) are **hand-drawn programmatically via Canvas API** — no external PNG/JPG assets. When adding new elements, follow these patterns.

## Core Principles

### 1. Soft Pixel Art (柔和像素)
- **NO black outlines** — use same-hue color shades to distinguish edges
- **Rounded edges** — avoid sharp corners, use color block transitions
- **Low saturation** — muted colors matching GBA retro aesthetic
- **No anti-aliasing** — `ctx.imageSmoothingEnabled = false` + `image-rendering: pixelated`

### 2. Drawing Method
- Use `ctx.fillRect(x, y, w, h)` for all pixel art (not `drawImage`)
- Canvas origin `(0,0)` at element center
- Character size: ~20×20 logical pixels
- Bottom shadow: `ctx.fillStyle = 'rgba(30,20,40,0.12)'; ctx.fillRect(-9, 9, 18, 3);`

### 3. Color Structure (per element)
Define 4-5 shades of the same hue:
```javascript
var BD = '#2a2030';  // darkest (shadow/outline)
var BM = '#3d3347';  // body main
var BL = '#4a4256';  // light
var BH = '#5a5066';  // highlight
var FUR = '#332838'; // texture/accent
```

### 4. Required States (characters)
Each pet/character must implement:
| State | Visual |
|-------|--------|
| `sleeping` | Lying on side, head resting, eyes closed (happy arches) |
| `sitting` | Front-facing, big head small body |
| `grooming` | Similar to sitting, head tilted |
| `isMoving` | Walk bob via `Math.sin(this.tick * 0.3) * 2` |

### 5. Micro-animations (all elements)
Use `Math.sin(this.tick * frequency)` for:
- Breathing: `Math.sin(this.tick * 0.06) * 0.5`
- Tail sway: `Math.sin(this.tick * 0.12) * 2`
- Ear twitch: `(this.tick % 120 < 6) ? 1 : 0`
- Blinking: random or tick-based toggle

### 6. Font
- `'Press Start 2P'` from Google Fonts for all text
- Canvas text: `ctx.font = '7px "Press Start 2P", monospace'`
- CSS: `image-rendering: pixelated` on `#officeCanvas`

## Drawing Order
1. Shadow (semi-transparent, bottom)
2. Body/tail/legs
3. Head (larger proportion than body — "cute" ratio)
4. Ears/horns
5. Eyes + nose + mouth
6. Paws/feet
7. Accessories

## Reference Implementations
- Cat: `_drawCat()` — dark charcoal, white chest, pink inner ears
- Pug: `_drawPug()` — fawn body, dark mask, curly tail
- Lobster: `_drawLobster()` — red segmented body, gold feet, antennae
- Desk: `drawDesk()` — wood tones, monitor, keyboard, mouse
- Plant: `drawPlant()` — white pot, green circles for leaves
- Bookshelf: `drawBookshelf()` — frame + colored books + gold ornament
