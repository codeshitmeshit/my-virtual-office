# Phase 6 Reasoning Summary Visibility

## Background

Phase 6 exposes Codex tool activity, approvals, input requests, cancellation, and recovery. During browser acceptance, a complex-execution visibility gap was identified: Codex app-server reasoning events are not presented through the existing Thinking card experience.

The current bridge receives `item/reasoning/summaryTextDelta`, but normalizes it as a generic activity event. It does not handle `item/reasoning/summaryPartAdded` or `item/reasoning/textDelta`. The browser therefore cannot reliably distinguish readable reasoning summaries from tool calls.

## Goal

Display Codex-provided readable reasoning summaries in a dedicated Thinking card while preserving the security boundary that Virtual Office must not invent, reconstruct, or promise access to hidden model chain-of-thought.

## In scope

- Normalize Codex reasoning summary events as a distinct activity type.
- Support `summaryTextDelta`, summary section boundaries, and `textDelta` when the runtime emits it.
- Incrementally update one Thinking card per reasoning item instead of creating duplicate cards for every delta.
- Persist and restore reasoning summaries after browser refresh.
- Reuse the established OpenClaw/Hermes Thinking card visual language with accurate Codex labeling.
- Apply existing redaction, truncation, ordering, and payload limits before persistence and display.
- Add bridge, server, browser, and real-Codex acceptance coverage.
- Request concise reasoning summaries by default through `turn/start.summary`, configurable with `VO_CODEX_REASONING_SUMMARY`.

## Out of scope

- Requesting or reconstructing hidden chain-of-thought.
- Guaranteeing that every model or every simple prompt emits a reasoning event.
- Displaying private reasoning that the Codex runtime does not expose.
- Changing model reasoning effort or model selection.

## Product behavior

1. When Codex emits a readable reasoning summary, the chat shows a dedicated expandable Thinking card.
2. Multiple deltas for one reasoning item append to the same card in protocol order.
3. New summary sections remain readable and do not overwrite earlier sections.
4. If no reasoning event is emitted, the UI shows no empty or fabricated Thinking card.
5. Tool cards remain separate from Thinking cards.
6. The UI describes the content as a Codex-provided reasoning summary, not the model's complete internal thought process.

## Success criteria

- A fixture containing at least 20 reasoning deltas and 3 summary sections renders exactly one ordered Thinking card for the reasoning item.
- Refresh produces the same visible summary without duplication or loss.
- A simple prompt with no reasoning event produces zero Thinking cards.
- Existing tool activity, approval, cancellation, Phase 5 behavior, OpenClaw, and Hermes rendering do not regress.
