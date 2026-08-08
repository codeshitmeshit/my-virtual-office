# Figma AI UI Reference Design

## Goal

Add a clearly marked UI reference area to the existing **My Virtual Office｜核心产品原型** Figma file. It is a visual reference for future Agents creating or reviewing UI, not a production implementation specification and not an automated test contract.

## Placement and discoverability

- Create a dedicated page named `00 · AI UI Reference · START HERE`.
- Place the page first in the Figma file when the API permits page reordering.
- Start the page with a high-contrast cover frame titled `AI UI Reference` and a short Chinese explanation of its purpose.
- Use stable, searchable English prefixes for top-level frames and components while keeping user-facing guidance in Chinese.

## Reference contents

The page contains four top-level sections:

1. `01 · Foundations`: product colors, typography, spacing, and corner-radius examples derived from the existing prototype.
2. `02 · Components`: buttons, inputs, selects, toggles, navigation items, status badges, cards, and modal structure.
3. `03 · States`: default, hover, focus, selected, disabled, loading, success, warning, and error examples where relevant.
4. `04 · Composition Example`: a compact example assembled from the reference patterns, using the current Virtual Office dark visual language.

## Visual direction

- Reuse the established dark canvas, dark surfaces, gold accent, cool blue informational color, green success color, and red destructive/error color.
- Reuse the existing Chinese typeface and visible sizing hierarchy where available.
- Keep the reference visually distinct from product screens through a labeled cover, numbered sections, and an informational banner.
- Prefer Auto Layout and reusable components so future Agents can inspect and reuse the patterns.

## Agent guidance

The cover frame includes concise instructions:

- Read this page before creating new UI.
- Reuse the listed foundations and components.
- Treat composition examples as guidance rather than fixed layouts.
- Preserve existing product behavior when visual guidance conflicts with implemented behavior.

## Safety and scope

- Do not modify or delete existing prototype screens.
- Do not add application code or change runtime behavior.
- Do not encode secrets, live credentials, or environment-specific paths in the reference.
- Keep this first version focused on shared desktop UI patterns; responsive/mobile rules can be added later if needed.

## Verification

- Confirm the reference page is easy to identify and appears first when supported.
- Inspect all frames for clipped text, overflow, font substitution, inconsistent spacing, and unclear labels.
- Confirm component/state naming is stable and searchable.
- Capture screenshots of the completed top-level reference sections for review.
