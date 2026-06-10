---
name: vanilla-js-i18n-implementation
description: Procedure for adding lightweight i18n (internationalization) support to vanilla JavaScript/HTML projects without frameworks or build systems
source: auto-skill
extracted_at: '2026-06-07T00:00:00.000Z'
---

## When to use

- Adding language support to a vanilla JS/HTML/CSS project
- No build system, no npm, no framework (React/Vue/etc.)
- Want minimal invasion of existing code
- Need to support 2+ languages with easy switching

## Architecture

### 1. Create the i18n engine

File: `app/i18n.js`

Core features:
- `t(key, params)` — translate a key, supports `{{param}}` interpolation
- `setLanguage(lang)` — switch language, persist to `localStorage`
- `initLanguage()` — called on page load, reads preference or falls back to `navigator.language`
- Auto-scans DOM for `data-i18n` (textContent), `data-i18n-html` (innerHTML), `data-i18n-title` (title attr), `data-i18n-placeholder` (placeholder attr) and applies translations
- Dispatches `i18n:ready` and `i18n:changed` custom events for components to react
- Loads locale JSON from `<script id="locale-XX" type="application/json">` tags (inline) or fetches from `locales/` directory
- Preloads English as fallback so untranslated keys still show English

### 2. Create locale dictionaries

Directory: `app/locales/`
- `en.json` — English key-value pairs
- `zh.json` — Chinese key-value pairs (must have identical keys)

Key naming convention:
- Use snake_case: `openclaw_path`, `gateway_token`, `test_connection`
- Prefix by feature area when keys get large: `proj_new_project`, `api_usage_no_providers`
- Keep keys descriptive but concise
- Both files MUST have identical key sets (verify with script)

### 3. Wire into each HTML page

Add this block in `<head>` before `</head>`:

```html
<script id="locale-en" type="application/json">{}</script>
<script id="locale-zh" type="application/json">{}</script>
<script src="i18n.js"></script>
<script>
(function(){
    var lang='en';
    try{var s=localStorage.getItem('vo-i18n-lang');if(s==='zh')lang='zh';
    else if(navigator.language&&navigator.language.toLowerCase().indexOf('zh')>=0)lang='zh';}catch(e){}
    var eE=document.getElementById('locale-en'),eZ=document.getElementById('locale-zh');
    function load(l,el){fetch('locales/'+l+'.json').then(function(r){return r.json()}).then(function(d){el.textContent=JSON.stringify(d)}).catch(function(){});}
    load('en',eE);load('zh',eZ);
})();
</script>
```

Why inline JSON + fetch: The inline `<script>` tags provide immediate locale data on first render. The fetch populates them asynchronously so the next page load has data ready synchronously.

For pages in subdirectories (e.g., `website/`), adjust paths: `src="../app/i18n.js"` and `fetch('../app/locales/'+l+'.json')`.

### 4. Mark HTML elements

Add `data-i18n="key"` to elements with translatable text:

```html
<!-- textContent -->
<span data-i18n="settings">☰ SETTINGS</span>
<button data-i18n="save">💾 Save</button>

<!-- placeholder -->
<input data-i18n-placeholder="type_message" placeholder="Type a message...">

<!-- title attribute -->
<button data-i18n-title="new_session" title="New Session">🔄</button>

<!-- innerHTML -->
<div data-i18n-html="help_text"></div>
```

Keep emoji prefixes outside the translatable span if they should remain:
```html
<div class="mm-section-title" data-i18n="openclaw_connection">🔌 OpenClaw Connection</div>
```

### 5. Handle JavaScript strings

For JS files that generate UI text dynamically:

Add a helper at the top:
```js
const _t = (key) => typeof i18n !== 'undefined' ? i18n.t(key) : key;
```

Replace user-visible string literals:
```js
// Before
statusEl.textContent = 'Connecting...';

// After
statusEl.textContent = _t('connecting');
```

For template literals with variables:
```js
// Before
el.textContent = `Connected to ${agentName}`;

// After
el.textContent = _t('connected_to').replace('{{name}}', agentName);
```

For default branch data or config objects:
```js
{ id: 'HQ', name: typeof i18n !== 'undefined' ? i18n.t('branch_hq') : 'Office Manager', ... }
```

### 6. Add language switcher UI

Place in existing Settings/control panel:

```html
<label>🌐 Language</label>
<button onclick="i18n.setLanguage('en')">English</button>
<button onclick="i18n.setLanguage('zh')">中文</button>
```

Optionally highlight the active language button on `i18n:changed` event.

### 7. Verify consistency

Run this check before deploying:

```python
import json
with open('locales/en.json') as f: en = json.load(f)
with open('locales/zh.json') as f: zh = json.load(f)
assert set(en.keys()) == set(zh.keys()), f"Key mismatch: EN-only={set(en.keys())-set(zh.keys())}, ZH-only={set(zh.keys())-set(en.keys())}"
print(f"✅ {len(en.keys())} keys match")
```

Check JS syntax:
```bash
for f in *.js; do node -c "$f" || echo "FAILED: $f"; done
```

## What NOT to translate

- Code/terminal output, log messages, error stack traces
- API endpoints, method names, CSS class names, DOM IDs
- Debugging/console.log strings
- File paths, URLs, technical identifiers
- Emoji icons (keep as-is)

## Scaling to more languages

To add a third language (e.g., Japanese):
1. Add `locales/ja.json` with all 876 keys
2. The i18n engine automatically supports it — just call `i18n.setLanguage('ja')`
3. Add a button for it in the language switcher

## Lessons learned

- **Parallel processing works well**: When processing many files (10+), use parallel agents to handle different files concurrently. Each file is independent.
- **Guard pattern is essential**: `typeof i18n !== 'undefined' ? i18n.t('key') : 'Fallback English'` prevents errors if i18n.js loads after the JS file executes.
- **Inline locale loading is faster than fetch-only**: Pre-populating `<script id="locale-XX">` tags on the first page load avoids a flash of untranslated content.
- **876 keys covered a 20,000+ line JS codebase**: You don't need to translate every single string — focus on what users actually see.
