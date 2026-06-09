# Internal Bubble Auto Collapse

## Background

The `Internal` status bubble currently occupies more canvas space than needed and remains visible without a user-configurable inactivity policy. Users need a quieter office view while retaining access to the most recent internal status.

## Target Users

- Virtual Office users monitoring one or more agents on the office canvas.
- Users who want current agent status visibility without persistent visual clutter.

## Goals

- Make the `Internal` bubble visually smaller than its current presentation.
- Add one global inactivity timeout setting, expressed in seconds.
- Automatically collapse stale `Internal` bubbles to their existing small icon.
- Preserve predictable recovery when new status arrives or the user manually expands an icon.

## Requirements

### REQ-001 Smaller Internal Bubble

- Reduce the width and visual density of the `Internal` bubble.
- The change applies only to `Internal` thought/status bubbles.
- Speech bubbles and the separate chat/activity bubbles must retain their existing sizing and behavior.
- Header, body text, minimize control, and connector must remain readable and usable.

### REQ-002 Global Auto-Collapse Setting

- Add one setting shared by all agents.
- The value is measured in seconds.
- Default value: `60`.
- Value `0` means automatic collapse is disabled.
- The preference must persist across page reloads for the current browser.

### REQ-003 Timeout Semantics

- Countdown starts when `Internal` content is last updated.
- Only a change to `Internal` content resets the countdown.
- Changes to reasoning, tool calls, chat replies, speech bubbles, or unrelated agent state must not reset it.
- When the timeout expires, the expanded `Internal` bubble collapses to its existing minimized icon.

### REQ-004 Reopening Behavior

- New `Internal` content automatically expands the bubble and restarts the countdown.
- Manually expanding a minimized `Internal` icon restarts the countdown from the configured value.
- Manual minimization remains available.

## Scope

Included:

- Canvas rendering adjustments for the `Internal` bubble.
- Global display setting and browser-side persistence.
- Automatic and manual collapse state transitions.
- English and Chinese setting labels.

Excluded:

- Changes to Hermes reasoning or tool activity bubbles.
- Per-agent timeout values.
- Server-side preference synchronization.
- Changes to speech bubble timeout behavior.
- Removal of the minimized `Internal` icon.

## Constraints

- Existing uncommitted workspace changes must be preserved.
- The feature must work for every provider represented by the common agent status model.
- Existing bubble collision handling and click targets must continue to work.

## Product Decisions

- Timeout unit: seconds.
- Timeout begins at the latest `Internal` content update.
- Timeout result: collapse to icon.
- Reset trigger: `Internal` content change only.
- Scope: one setting for all agents.
- Default: `60` seconds.
- Disabled value: `0`.
- New content: automatically expand and restart.
- Manual restore: restart timeout.
