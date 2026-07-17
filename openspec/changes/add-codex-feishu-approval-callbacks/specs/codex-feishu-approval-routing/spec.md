## ADDED Requirements

### Requirement: Eligible Codex approvals reach the originating Feishu user
When a Feishu-originated Codex turn requests approval for command execution, file changes, or permissions, Virtual Office SHALL deliver an interactive approval card to the human who initiated that turn. The card MUST identify the bounded action awaiting approval and MUST offer exactly the supported one-time approve and cancel decisions without exposing secrets or unrelated conversation data.

#### Scenario: Command approval originates from Feishu
- **WHEN** a Codex turn started by a Feishu user emits a pending command-execution approval
- **THEN** that originating user receives an approval card describing the bounded command and offering approve-once and cancel actions

#### Scenario: File or permission approval originates from Feishu
- **WHEN** a Codex turn started by a Feishu user emits a pending file-change or permission approval
- **THEN** that originating user receives an approval card with the same approve-once and cancel decision semantics

#### Scenario: Approval belongs to another conversation
- **WHEN** an approval cannot be linked to the originating Feishu user and turn
- **THEN** Virtual Office MUST NOT send the approval contents to a guessed recipient or unrelated conversation

### Requirement: Notification application has delivery priority with Chat App fallback
Virtual Office SHALL send an eligible Codex approval card through the configured Feishu notification application when that application is configured. If the notification application is not configured, unavailable, or reports a delivery failure, Virtual Office SHALL fall back to the Feishu Chat App conversation that originated the turn. A fallback MUST preserve the same approval identity and decision authority as the primary card.

#### Scenario: Notification application delivers successfully
- **WHEN** the notification application is configured and accepts delivery of an eligible approval card
- **THEN** Virtual Office uses that delivery as the primary approval surface and does not intentionally send a second Chat App card

#### Scenario: Notification application is not configured
- **WHEN** an eligible approval is created and no notification application is configured
- **THEN** Virtual Office sends the card through the originating Feishu Chat App conversation

#### Scenario: Notification delivery fails
- **WHEN** the configured notification application reports that the approval card was not delivered
- **THEN** Virtual Office attempts delivery through the originating Feishu Chat App conversation using the same approval identity

#### Scenario: Notification outcome is ambiguous
- **WHEN** notification delivery may have succeeded but its response is lost or classified as failed and fallback delivery also occurs
- **THEN** cards from both delivery attempts refer to one approval whose first valid decision is authoritative

### Requirement: Feishu decisions continue the original Codex turn exactly once
An approval action SHALL be accepted only when its trusted Feishu callback context matches the pending Codex approval, originating user, Agent, conversation, thread, turn, and approval identity. The first valid approve or cancel decision SHALL resolve and continue the original turn exactly once. Duplicate, replayed, conflicting, stale, or late actions MUST NOT execute the guarded action or resolve the turn again.

#### Scenario: Originating user approves once
- **WHEN** the originating user selects approve on a card linked to a currently pending approval
- **THEN** Virtual Office submits one approve-once decision to the original Codex turn and allows that turn to continue

#### Scenario: Originating user cancels
- **WHEN** the originating user selects cancel on a card linked to a currently pending approval
- **THEN** Virtual Office submits one cancel decision to the original Codex turn and allows that turn to reach its resulting terminal response

#### Scenario: Duplicate callback is replayed
- **WHEN** Feishu repeats an already accepted card callback
- **THEN** Virtual Office returns an already-processed outcome without submitting another provider decision

#### Scenario: Conflicting cards are acted on
- **WHEN** one delivered card has resolved the approval and a user later acts on another primary or fallback card
- **THEN** the later action does not change the authoritative decision and the user is told that the approval was already processed

#### Scenario: Callback identity or linkage is invalid
- **WHEN** a card action comes from a different user or does not match the pending Agent, conversation, thread, turn, and approval identity
- **THEN** Virtual Office rejects the action without revealing approval contents or changing the Codex turn

### Requirement: All delivered cards reflect the resolved state
After an approval is resolved, Virtual Office SHALL make every known primary and fallback card for that approval non-actionable and show the authoritative processed outcome. Failure to update one card MUST NOT reverse or repeat an already accepted decision and SHALL remain diagnosable.

#### Scenario: Primary card resolves approval
- **WHEN** the user resolves an approval from the primary notification card
- **THEN** every known card for the approval is updated to show the processed result and no longer offers an effective action

#### Scenario: Fallback card resolves approval
- **WHEN** the user resolves an approval from a fallback Chat App card
- **THEN** the primary and fallback cards are updated consistently with the authoritative result

#### Scenario: Card update fails
- **WHEN** one delivered card cannot be updated after resolution
- **THEN** the approval remains resolved exactly once and the update failure is recorded for diagnosis

### Requirement: Undeliverable approvals fail visibly without leaving the Agent stalled
If neither Feishu application can deliver an eligible approval card, Virtual Office SHALL stop waiting for that approval, prevent the guarded action from executing, and send a normal failure response to the originating Feishu conversation explaining that approval could not be delivered. The Agent MUST NOT remain indefinitely pending or be reported as successfully completed.

#### Scenario: Both delivery paths fail
- **WHEN** notification delivery fails and the originating Chat App delivery also fails
- **THEN** Virtual Office cancels the pending approval, ends the wait, and attempts a normal failure reply to the originating Feishu conversation

#### Scenario: Only Chat App is available and fails
- **WHEN** no notification application is configured and Chat App card delivery fails
- **THEN** Virtual Office cancels the pending approval and surfaces the delivery failure through the originating conversation's normal failure path

#### Scenario: Failure reply cannot be delivered
- **WHEN** the normal failure reply also cannot be delivered to Feishu
- **THEN** Virtual Office leaves the turn in a non-success terminal state and records a diagnosable delivery failure instead of silently retaining a pending approval

### Requirement: Approval cards remain isolated from VO chat history
Approval-card delivery, card updates, and card-action acknowledgements MUST NOT be written as messages in Virtual Office normalized chat history, provider conversation history, or agent-platform communication history. Virtual Office SHALL retain approval lifecycle, delivery attempts, callback claims, decisions, card-update outcomes, and failures in separate bounded audit surfaces. The accepted user message and the Codex turn's normal final reply or terminal failure SHALL retain their existing chat-history behavior.

#### Scenario: Approval card is delivered
- **WHEN** either Feishu application sends an approval card
- **THEN** no approval-card message appears in Virtual Office chat history or communication history

#### Scenario: User acts on a card
- **WHEN** an approval callback is accepted, rejected, replayed, or fails
- **THEN** its audit outcome is retained outside VO chat messages and no synthetic approval message is added to the conversation

#### Scenario: Codex finishes after approval
- **WHEN** the original Codex turn produces its normal final reply or terminal failure after the decision
- **THEN** that Agent outcome remains eligible for the existing VO and Feishu conversation-history flow

#### Scenario: Operator diagnoses delivery and callback behavior
- **WHEN** an operator inspects the approval lifecycle
- **THEN** separate audit records identify redacted delivery, fallback, callback, decision, update, and failure outcomes without exposing credentials or unrestricted sensitive content
