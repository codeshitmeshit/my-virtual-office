# Project Agent Instructions

## Frontend UI Standard — Required First Read

- Canonical Figma reference: [`00 · SYSTEM UI STANDARD · AI START HERE`](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=356-240).
- Before creating or modifying any frontend UI, every Agent must open this page and align the implementation with its tokens, components, icons, interaction states, dialogs, notifications, destructive actions, and page-composition rules.

## Highest-Priority Constraint

- This constraint takes precedence over all other implementation preferences in this file: for every new requirement, default to placing the implementation in one or more new, focused files. Do not append new logic to existing large files unless the change is both minimal and unquestionably part of that file's existing responsibility.

## User and Scale Assumptions

- This system is generally intended for single-user use. Unless a requirement explicitly introduces multi-user or multi-tenant behavior, do not design or optimize for those scenarios.
- When proposing new components, architecture, infrastructure, or technical evaluations, size the solution and its capacity, complexity, operational burden, and cost assumptions for a single-user workload. Avoid over-engineering for hypothetical scale, while preserving straightforward extension points where doing so has little cost.

## Workflow Constraints

- Do not invoke or use the `hammer` skill or any `hammer-*` skill in this repository.
- If a task would normally trigger a Hammer workflow, skip Hammer and handle the task directly with ordinary repository inspection, implementation, testing, and review.
- Do not create, restore, or rely on `.hammer/` workflow files or Hammer gates for this project.
- Treat every `superpowers:*` skill as opt-in in this repository. Invoke one only when the user explicitly names that skill or explicitly asks to use Superpowers.
- Do not auto-trigger a `superpowers:*` skill from its general task-description match, including `superpowers:using-superpowers`; handle ordinary tasks directly unless the user opts in.

## Prompt Structure

- All prompts constructed by this project for an Agent or language model must use XML as their outer structural format.
- Separate instruction concerns into explicit semantic elements such as `<role>`, `<task>`, `<context>`, `<security>`, `<rules>`, and `<output_schema>` instead of relying on unstructured prose.
- Dynamic or untrusted material must be placed inside a clearly named XML data boundary and escaped so that it cannot close or replace instruction elements. JSON may be embedded inside that XML data element when it is the clearest representation.
- The required response format is independent of the prompt envelope: request JSON, Markdown, XML, or plain text explicitly inside `<output_schema>` or an equivalent XML element.
- When modifying an existing prompt that does not follow this structure, migrate the touched prompt to the XML format as part of the same change.
- Provider-visible Agent prompts must be assembled through the shared bridge input/output formatter (`services.bridge_input_output_formatting`) by passing key-value or nested mapping input. Even simple prompts should be represented as named fields such as `message`, not bare string concatenation.
- Business-specific XML tags are allowed, but tag names and attributes must be supplied to the formatter so it can validate XML names and escape dynamic values. Dynamic or user-supplied content belongs in formatter untrusted text or JSON data boundaries.
- System-authored prompts that expect a stable reply shape should include an `output` key/section. The formatter renders `output` as the final top-level section; do not add a separate output-contract wrapper.

<!-- CODEGRAPH_START -->
## CodeGraph

In repositories indexed by CodeGraph (a `.codegraph/` directory exists at the repo root), reach for it BEFORE grep/find or reading files when you need to understand or locate code:

- **MCP tool** (when available): `codegraph_explore` answers most code questions in one call — the relevant symbols' verbatim source plus the call paths between them, including dynamic-dispatch hops grep can't follow. Name a file or symbol in the query to read its current line-numbered source. If it's listed but deferred, load it by name via tool search.
- **Shell** (always works): `codegraph explore "<symbol names or question>"` prints the same output.

If there is no `.codegraph/` directory, skip CodeGraph entirely — indexing is the user's decision.
<!-- CODEGRAPH_END -->

## Modularity and Complexity Constraints

- Prefer implementing every new API, route group, integration, background job, or substantial feature in a new, focused module instead of adding more business logic to a large legacy file such as `app/server.py`.
- Keep legacy entry-point files limited to transport handling, route registration, dependency wiring, and thin compatibility delegation. Put validation, orchestration, state transitions, and persistence decisions in the owning module.
- New modules must depend on explicit interfaces or injected collaborators and must not import a legacy entry-point module to reach its globals or helpers. Avoid circular imports, duplicated state authorities, and hidden cross-module mutation.
- When modifying an existing feature in a highly coupled file, extract the touched responsibility into a focused module when it is safe and proportionate to the change. Do not make the legacy file larger by default.
- Preserve public behavior and compatibility during extraction, but remove obsolete compatibility delegates and duplicate implementations after their callers have migrated.
- Treat reduced coupling, smaller responsibility boundaries, readability, and maintainability as required implementation outcomes. The project should become incrementally simpler with each change rather than accumulating more logic in shared files.
- If keeping new logic in an existing legacy file is genuinely necessary, document the reason and keep the addition as small and isolated as possible.

## UI and Figma Design Standards

When a requirement involves designing, redesigning, or materially changing a UI, use the following design-delivery format before implementation. This is the repository's default UI specification standard, not an optional presentation layer.

### Authoritative system UI standard

- The canonical UI standard for this repository is the Figma page [`00 · SYSTEM UI STANDARD · AI START HERE`](https://www.figma.com/design/o6Crht2KV89peGoPpCAJsX/My-Virtual-Office%EF%BD%9C%E6%A0%B8%E5%BF%83%E4%BA%A7%E5%93%81%E5%8E%9F%E5%9E%8B?node-id=356-240).
- Before writing or modifying any frontend UI code, every Agent must open and read that page, then follow its foundations, components, icons and action semantics, interaction states, destructive-action levels, and standard page composition.
- The standard applies to new pages, redesigned surfaces, incremental UI changes, and Agent-generated frontend output. Do not create a competing global color, typography, spacing, radius, component, icon, or state system inside a business feature.
- Reuse the Figma standard's semantic tokens and reusable patterns. Delete, close, clear, and remove are distinct actions and must follow the documented icon and behavior rules.
- If a product requirement must deviate from the standard, document the reason, affected surface, and regression expectation before implementation. Do not introduce an undocumented exception or silently diverge in code.
- The Figma page is the target UI source of truth. Frontend implementation and historical-page migration may be delivered in separate requirements, but when frontend work is authorized it must align to this standard.

### Required discovery

- Inspect the existing UI, its event handlers, data-loading paths, persistence APIs, local storage keys, and destructive actions before drawing the replacement.
- Distinguish verified current behavior from proposed target behavior. If an existing control has an unexpected side effect, such as a test action that saves configuration, show that difference explicitly in the design rather than silently carrying it forward.
- Reuse the product's established visual language, tokens, typography, and component patterns unless the requirement explicitly calls for a new direction.

### Required Figma deliverables

- Create or update an editable high-fidelity screen showing the proposed UI in its real product context. For settings or other dense workflows, prefer a large, clearly structured modal with a stable header, category navigation, scrollable content area, and persistent footer actions.
- Add a separate **interaction overview** frame. Number every clickable or keyboard-triggered interaction and map each number to its resulting UI state and data side effect. Cover opening, closing, backdrop click, Escape, cancel, navigation, inputs, selects, toggles, conditional fields, tests, retries, saves, imports, exports, resets, links, and confirmation-dialog choices.
- Add a separate **storage and submission** frame. Show where data is loaded from, where unsaved edits live, when each value is committed, which API or storage target receives it, and what happens on success, failure, retry, rollback, or dismissal.
- Keep the screen mock, interaction overview, and persistence design as separate top-level frames in the same Figma file. Preserve earlier approved work instead of overwriting it, and provide direct node links for review.
- For a small UI change, these deliverables may be compacted into fewer frames, but the interaction and persistence information must still be present.

### Interaction specification requirements

- Use stable numeric identifiers so hotspots in the screen map correspond one-to-one with the interaction inventory.
- For each interaction, document: the trigger, immediate visual response, loading/disabled behavior, success state, error state, retry behavior, and persistence side effect.
- Include the standard form state model where applicable: `Clean -> Dirty -> Validating -> Saving or Testing -> Success or Error`.
- Preserve unsaved drafts while switching categories. A failed save or test must keep the user's input and focus the relevant error.
- Closing a dirty surface must define explicit choices such as **Save and close**, **Discard changes**, and **Continue editing**. Destructive actions must use appropriately strong confirmation, and irreversible resets should require layered confirmation.
- A control labeled **Test** should be side-effect free by default. If successful validation also persists or activates configuration, label it explicitly as **Test and activate** or equivalent.
- Use consistent semantic colors for draft or regular actions, read-only navigation, testing or success, secure independent transactions, and destructive actions. Color must supplement clear text labels, not replace them.

### Storage and submission requirements

- Model editable values through an in-memory draft store with a saved baseline and per-section dirty tracking. Sensitive inputs should distinguish unchanged masked values, newly entered values, and explicit clearing without retaining plaintext after dismissal.
- Separate persistence domains instead of treating every field as one undifferentiated save:
  - browser-local preferences such as display and language settings;
  - general server configuration;
  - sensitive integrations with dedicated secure endpoints or stores;
  - domain data such as the office layout, imports, and exports.
- Identify concrete endpoints, local storage keys, and server-side files in the design whenever they are known.
- Define commit ordering. When local and server values belong to one user action, prefer validating first, committing the authoritative server state, and only then updating browser-local preferences and the saved baseline.
- Define partial-failure behavior. Do not clear dirty state or silently commit a local subset when the authoritative save fails. Independent secure transactions must report their own status without corrupting unrelated settings.
- Never place secrets in local storage, logs, toasts, analytics, screenshots, or exported configuration. Saved secrets should be represented only by a mask or a configured flag, and secure files must use atomic writes and restrictive permissions where supported.

### Design quality gate

- Before handing off a UI design, visually inspect every frame and programmatically check for clipped text, overflow, placeholder content, inconsistent fonts, incorrect hotspot numbering, and missing states.
- Provide reviewable screenshots together with direct Figma node links and summarize the most consequential interaction and storage decisions.
- Implementation must follow the approved interaction and persistence specification. If implementation constraints require a behavior change, update the Figma specification or call out the deviation before coding it.

## Feishu Notification Delivery

- All Feishu notification-module sends must go through the centralized notification delivery entry points in `app/services/feishu_notification_delivery.py`.
- Business modules may construct notification intents or markdown content, but they must not decide the final Feishu recipient, webhook fallback, receive ID type, or delivery policy themselves.
- Do not call low-level notification senders such as `send_feishu_notification`, `send_feishu_markdown_message`, or `_feishu_app_send_config` directly from business workflows for notification-module delivery. Add or extend a centralized delivery helper instead.
- The centralized delivery layer owns `notificationRecipientPolicy`, including `originating_user_dm`, source-user identity extraction, and the rule that missing source identity must not fall back to a fixed group chat.
- Feishu chat original-channel replies are separate from notification-module delivery. Functions that intentionally reply to the current Feishu chat by `chat_id` may keep using the chat transport path, but must not be reused for notification-module sends.

## Feishu Topic Foreground Commands

- Feishu notification-topic foreground commands such as `/here` and `/change` must be implemented through the centralized foreground command boundary in `app/services/feishu_topic_foreground_commands.py`.
- `/here` may select context and construct a notification intent, but actual Feishu notification sending must still go through the unified notification delivery entrypoint; do not call low-level Feishu senders from command code.
- `/change` switches the active Agent for the current notification-topic conversation only. The selected Agent must be owned by the notification-topic binding/store path; do not duplicate that state in Provider adapters, notification audit records, chat handlers, or `app/server.py`.
- Transport entry points such as `app/feishu_chat_channel.py`, `app/feishu_long_connection.py`, and `app/server.py` should only parse/admit and wire foreground command ports; they should not contain command business logic.
