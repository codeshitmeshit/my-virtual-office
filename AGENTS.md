# Project Agent Instructions

## Highest-Priority Constraint

- This constraint takes precedence over all other implementation preferences in this file: for every new requirement, default to placing the implementation in one or more new, focused files. Do not append new logic to existing large files unless the change is both minimal and unquestionably part of that file's existing responsibility.

## Workflow Constraints

- Do not invoke or use the `hammer` skill or any `hammer-*` skill in this repository.
- If a task would normally trigger a Hammer workflow, skip Hammer and handle the task directly with ordinary repository inspection, implementation, testing, and review.
- Do not create, restore, or rely on `.hammer/` workflow files or Hammer gates for this project.

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
