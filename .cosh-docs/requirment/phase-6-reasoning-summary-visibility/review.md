# Phase 6 Reasoning Summary Visibility Review

## Review status

Reviewed with no blocking product or technical questions. The change is a focused Phase 6 acceptance defect fix.

## Current behavior

- `app/providers/codex_bridge.py` receives `item/reasoning/summaryTextDelta` together with command and MCP progress and emits a generic `activity` event.
- `app/chat.js` renders every Codex `activity` event through the tool-card path.
- The shared frontend already contains `renderThinkingCard`, used by provider history containing `thinking` or `reasoningTokens`.
- No bridge, server, or Phase 6 E2E test currently asserts Codex reasoning rendering.

## Protocol basis

The official Codex App Server event contract defines:

- `item/reasoning/summaryTextDelta` for readable reasoning summaries;
- `item/reasoning/summaryPartAdded` for summary section boundaries;
- `item/reasoning/textDelta` for reasoning text when supported by the model.

These are runtime-provided events. Their presence is model-dependent and must not be described as guaranteed access to hidden chain-of-thought.

## Recommended implementation

1. Emit a distinct normalized event such as `type: reasoning` with item ID, sequence, section index, delta kind, and bounded text.
2. Set `turn/start.summary` to `concise` by default so the runtime is asked to produce readable summaries; allow `auto`, `detailed`, or `none` through `VO_CODEX_REASONING_SUMMARY`.
3. Persist normalized reasoning events through the existing Codex activity store after redaction and truncation.
4. In the browser, maintain one reasoning-card state per operation/item and append deltas in sequence order.
5. Use section boundaries to insert readable separators without creating additional chat messages.
6. Restore the same card from activity history and deduplicate live events using existing sequence IDs.
7. Keep reasoning cards visually distinct from commands, file changes, MCP calls, and errors.

## Security and wording

- Label the card `Thinking` or `Reasoning summary`, with explanatory copy stating that it contains Codex-provided summaries when available.
- Do not label the content as complete internal reasoning or chain-of-thought.
- Run recursive redaction and output bounding before persistence.
- Do not render an empty card when the runtime emits no usable text.

## Compatibility

- Existing OpenClaw/Hermes Thinking cards remain unchanged.
- Existing Codex tool cards and interaction controls remain unchanged.
- Historical Phase 6 activity without reasoning events remains valid.
- Unknown future reasoning notifications must fail safely without exposing raw payloads.

## Source

- Official Codex App Server documentation: `https://developers.openai.com/codex/app-server#item-deltas`.
