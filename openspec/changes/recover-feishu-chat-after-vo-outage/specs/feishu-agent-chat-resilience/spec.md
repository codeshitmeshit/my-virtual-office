## ADDED Requirements

### Requirement: Durable inbound messages recover after VO outage
The Feishu Agent Chat channel SHALL retain every accepted inbound message that has not received a valid durable acknowledgement from VO. While retained messages exist and the worker is running, the system SHALL keep attempting delivery so that a responsive VO receives another attempt within one minute without requiring a new Feishu message, configuration change, WebSocket reconnect, or process restart. A retained message MUST NOT be removed until VO returns a valid durable acknowledgement for that source message.

#### Scenario: VO is unavailable when a message arrives
- **WHEN** the Feishu worker accepts and durably stores an inbound Agent Chat message but VO is unavailable, unresponsive, or returns a non-durable failure
- **THEN** the worker SHALL retain the message, expose degraded processing health, and continue automatic delivery attempts

#### Scenario: VO recovers without another Feishu event
- **WHEN** VO becomes responsive while one or more inbound messages remain retained and no new Feishu event, configuration change, reconnect, or process restart occurs
- **THEN** the system SHALL begin another delivery attempt within one minute and continue until each retained message receives a valid durable acknowledgement

#### Scenario: VO remains unavailable beyond immediate retries
- **WHEN** VO remains unavailable after any immediate retry sequence is exhausted
- **THEN** the system SHALL continue bounded background recovery instead of abandoning, deleting, or permanently pausing the retained messages

### Requirement: Recovery preserves exactly-once outcomes and conversation order
Recovery SHALL use the persistent Feishu source-message identity and VO business records so repeated delivery attempts produce at most one user-visible Agent turn and one authoritative reply outcome for each source message. Messages from the same Feishu conversation MUST become durable in source order, while failure in one conversation MUST NOT prevent unrelated conversations from making progress within configured safety capacity.

#### Scenario: Callback result is uncertain during outage
- **WHEN** a callback attempt may have reached VO but the worker did not receive a valid durable acknowledgement before failure
- **THEN** a later recovery attempt SHALL reuse the same source-message identity and VO SHALL reuse the existing outcome instead of invoking the Agent or delivering the authoritative reply twice

#### Scenario: VO restarts after provider dispatch becomes uncertain
- **WHEN** VO restarts after persisting that provider dispatch began but before a terminal provider outcome is durably reconcilable
- **THEN** VO SHALL retain a non-terminal processing state and MUST NOT invoke the Agent again merely because the prior process owner disappeared

#### Scenario: Multiple messages accumulate in one conversation
- **WHEN** two or more accepted messages from the same Feishu conversation remain unacknowledged during a VO outage
- **THEN** recovery SHALL preserve their deterministic source order and MUST NOT complete a later message ahead of an earlier retained message in that conversation

#### Scenario: Another conversation is healthy
- **WHEN** one Feishu conversation has retained or retrying work and another conversation can be processed safely
- **THEN** the healthy conversation SHALL continue to make progress without sharing ordering or idempotency state with the degraded conversation

### Requirement: Recovery state is observable and actionable
VO SHALL expose message-processing health independently from Feishu WebSocket connectivity. The status surface SHALL provide a stable processing state, retained-message count, oldest retained-message time or age, most recent durable acknowledgement time, current recovery activity or next retry information, and a redacted last failure. Sustained failure SHALL produce an operator-visible warning while automatic recovery continues.

#### Scenario: WebSocket is connected but VO processing is failing
- **WHEN** the Feishu WebSocket remains connected while callback delivery to VO is failing or retained messages are awaiting recovery
- **THEN** status SHALL report the connection as connected and message processing as degraded or recovering rather than presenting the whole channel as healthy

#### Scenario: Recovery is in progress
- **WHEN** the system is retrying one or more retained messages
- **THEN** status SHALL expose recovering state, backlog size, oldest pending age or time, and bounded retry progress without exposing credentials or message content

#### Scenario: Processing recovers completely
- **WHEN** VO has durably acknowledged every retained message and no callback failure remains active
- **THEN** processing health SHALL return to healthy and preserve the most recent successful acknowledgement time for operator diagnosis

#### Scenario: Failure exceeds the warning threshold
- **WHEN** processing remains degraded beyond the configured operator-warning threshold
- **THEN** VO SHALL display an actionable warning while retaining messages and continuing automatic recovery

#### Scenario: Recovery is disabled while backlog remains quiet
- **WHEN** background recovery is disabled and retained work crosses the warning threshold without another message or callback attempt
- **THEN** the heartbeat-driven status surface SHALL still raise the operator warning

### Requirement: Control panel shows Feishu message-processing health
The VO control panel SHALL include a Feishu message-processing status bar that is distinct from connection status and reflects the authoritative processing-health surface. It SHALL make healthy, degraded, and recovering states understandable to an operator and SHALL update as backlog and recovery state change.

#### Scenario: Operator opens the control panel during an outage
- **WHEN** Feishu connectivity is available but VO callback processing is degraded
- **THEN** the status bar SHALL visibly identify the processing failure and show the retained-message count and oldest pending age or time

#### Scenario: Operator observes automatic recovery
- **WHEN** VO becomes responsive and retained messages begin to clear
- **THEN** the status bar SHALL transition to recovering, update recovery progress, and return to healthy only after the retained backlog reaches zero

#### Scenario: Sensitive callback failure is displayed
- **WHEN** the latest processing failure contains credentials, authorization values, cookies, tokens, message content, or private endpoint details
- **THEN** the status bar and its backing management response SHALL expose only a stable redacted error summary

### Requirement: Existing Feishu behavior remains compatible
This resilience change SHALL preserve existing Feishu Agent selection, private and group conversation identities, sender attribution, supported inbound content, persistent history, notification/card-action isolation, and outbound command behavior. It MUST NOT expand recovery scope to the separate notification/card-action application or independently retry standalone outbound operations.

#### Scenario: Existing Agent Chat message is processed without outage
- **WHEN** VO is healthy and a supported Feishu Agent Chat message arrives
- **THEN** the message SHALL follow the existing routing, persistence, Agent execution, reply, history, and audit behavior without an additional user-visible turn

#### Scenario: Live message follows retained work while background recovery is disabled
- **WHEN** a new message arrives behind older retained work in the same conversation while background recovery is disabled
- **THEN** the live path SHALL attempt the retained heads in order through the new message, stop on the first failure, and leave failed work retained

#### Scenario: Notification or card action is used
- **WHEN** the separate Feishu notification/card-action application receives an event
- **THEN** its existing behavior SHALL remain independent from the Agent Chat callback-recovery lifecycle

#### Scenario: Standalone outbound operation fails
- **WHEN** a send, reply, reaction, recall, or resource command fails outside recovery of an accepted inbound Agent Chat message
- **THEN** the existing classified outbound failure behavior SHALL remain unchanged by this capability
