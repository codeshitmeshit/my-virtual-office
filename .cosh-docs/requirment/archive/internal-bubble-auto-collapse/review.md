# Internal Bubble Auto Collapse Review

## Review Summary

Result: approved for checklist drafting. No blocking product or technical questions remain.

## Product Review

The desired behavior is internally consistent:

- The bubble remains available through a minimized icon rather than disappearing.
- New information receives attention by automatically expanding.
- Manual inspection has a predictable full timeout window.
- A shared setting avoids per-agent configuration overhead.
- `0` provides an explicit opt-out for users who prefer persistent bubbles.

The feature is narrowly scoped to `Internal` status bubbles and does not conflict with the separate Hermes activity bubble.

## Current-System Findings

- `app/game.js` owns thought bubble rendering, per-agent minimized state, status polling, and local display preferences.
- `app/index.html` contains the Display settings UI.
- `vo-display-prefs` in `localStorage` already persists browser-specific display settings.
- New thought content currently resets typewriter state and automatically expands a minimized thought bubble.
- Manual icon restoration already resets display animation state.
- The current hard-coded fade timer starts after typewriter completion. That behavior does not match the clarified requirement and must be replaced for `Internal` auto-collapse.

## Proposed Technical Approach

### State Model

- Add a per-agent timestamp representing the start of the current `Internal` inactivity window.
- Set it when `Internal` content changes.
- Reset it when a user manually restores the minimized `Internal` bubble.
- Do not update it for repeated polling of identical content or for speech/chat/tool activity.
- When the configured timeout is greater than zero and elapsed, set the existing thought minimized state to `true`.

### Preference Model

- Add `internalBubbleTimeoutSec` to `vo-display-prefs`.
- Default missing or invalid values to `60`.
- Treat `0` as disabled.
- Reject or normalize negative, non-finite, and non-numeric values.
- Load the value into the settings input and apply saved changes without requiring a server restart.

### Presentation

- Give thought bubbles dedicated compact dimensions rather than changing shared speech bubble constants.
- Reduce width, padding, line height, and maximum visible lines conservatively.
- Keep stable header and close-button dimensions so the title and control do not overlap.
- Preserve the existing minimized icon and collision resolution.

## State Transitions

1. New `Internal` content:
   - Save content.
   - Reset typewriter state.
   - Record update timestamp.
   - Expand the bubble.

2. Identical status poll:
   - No timestamp change.
   - Existing countdown continues.

3. Timeout expires:
   - Collapse thought bubble to icon.
   - Keep latest content available.

4. User restores icon:
   - Expand bubble.
   - Restart inactivity timestamp.
   - Replay existing typewriter behavior if retained.

5. Timeout setting changes:
   - `0`: stop future automatic collapse.
   - Positive value: evaluate expanded bubbles against their current inactivity timestamp.

## Compatibility And Migration

- Existing users have no stored timeout field, so they receive the `60` second default.
- Existing `vo-display-prefs` keys remain unchanged.
- No server configuration, database, API, or permission changes are required.
- The implementation remains provider-independent because it uses normalized `thought` content.

## Risks And Mitigations

- Risk: repeated polling could indefinitely reset the timer.
  - Mitigation: reset only when content changes.

- Risk: the compact header could overlap the agent name or minimize button.
  - Mitigation: reserve close-button space and verify long names visually.

- Risk: changing shared constants could shrink speech bubbles.
  - Mitigation: introduce thought-specific layout values.

- Risk: legacy hard-coded fade behavior could conflict with collapse behavior.
  - Mitigation: remove or supersede the hard-coded thought fade lifecycle.

- Risk: invalid stored values could collapse immediately or never collapse.
  - Mitigation: normalize values to a non-negative finite number with a `60` second fallback.

## Security, Privacy, And Permissions

- No new sensitive data is collected.
- The preference is local display state only.
- No new permissions or external requests are introduced.

## Performance And Observability

- Timeout evaluation is constant time per visible agent during the existing render/update cycle.
- No additional polling is required.
- Manual verification can observe expansion, icon collapse, restoration, and persistence directly on the canvas.

## Test Feasibility

- Syntax and static checks can validate JavaScript and document consistency.
- Browser automation or manual timing can verify timeout transitions.
- Reload testing can verify local preference persistence.
- Multiple agents can verify the global setting and independent per-agent countdown timestamps.
