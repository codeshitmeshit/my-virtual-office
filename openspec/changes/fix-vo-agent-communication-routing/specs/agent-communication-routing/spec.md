## ADDED Requirements

### Requirement: Canonical office communication skill
Virtual Office SHALL expose one canonical agent communication skill whose instructions require office-visible routing for ordinary cross-agent communication. The runtime copy, Skills Library copy, and agent-installed copy of that skill SHALL express the same routing rules and SHALL NOT retain a divergent legacy communication contract.

#### Scenario: Runtime skill is seeded
- **WHEN** Virtual Office initializes or refreshes its built-in Skills Library entries
- **THEN** the canonical agent communication skill is available under its current skill identity with the same normative routing rules as the VO-served communication guidance

#### Scenario: Legacy skill data exists
- **WHEN** Virtual Office finds an older built-in communication skill managed by a previous VO version
- **THEN** it migrates or replaces that managed entry without deleting unrelated user-created skills

### Requirement: Communication skill lifecycle for OpenClaw agents
Virtual Office SHALL install the canonical communication skill into every discovered or newly created OpenClaw agent workspace that supports workspace skills. Virtual Office SHALL refresh VO-managed copies when the canonical version changes while preserving unrelated workspace skills and user-authored files.

#### Scenario: Existing OpenClaw agent is discovered
- **WHEN** an eligible OpenClaw agent is added to the current VO roster
- **THEN** its workspace contains a usable canonical communication skill before VO presents it as ready for cross-agent delegation

#### Scenario: New OpenClaw agent is created
- **WHEN** Virtual Office successfully creates an OpenClaw agent
- **THEN** the new agent receives the canonical communication skill as part of its initialization

#### Scenario: Canonical skill changes
- **WHEN** a later VO version updates the VO-managed canonical communication skill
- **THEN** each eligible OpenClaw workspace receives the updated managed copy without overwriting unrelated skills or files

### Requirement: Provider-aware office routing
An office agent handling an ordinary cross-agent request SHALL resolve the current sender identity, target identity, and target provider from the Virtual Office roster before sending. It SHALL send the request through `POST /api/agent-platform-communications/send` with a stable conversation identifier instead of guessing an agent ID or provider route.

#### Scenario: Unique target exists
- **WHEN** the current VO roster contains one target matching the requested office agent
- **THEN** the sender uses the returned VO identities and provider information in a request to the VO communication endpoint

#### Scenario: Target is ambiguous or absent
- **WHEN** the current VO roster contains multiple plausible targets or no matching target
- **THEN** the sender reports the ambiguity or unavailability and does not substitute another agent

#### Scenario: Conversation continues
- **WHEN** a sender follows up within an existing cross-agent business conversation
- **THEN** it reuses the stable `conversationId` associated with that sender, target, and topic

### Requirement: No private fallback for office communication
An office agent SHALL NOT use provider-private session discovery, session messaging, direct provider CLI execution, or a local subagent as a fallback for a cross-agent interaction that belongs in Virtual Office. If the VO communication route is unavailable, busy, timed out, or invalid, the agent SHALL report the actual state and stop unless the user explicitly chooses a different workflow.

#### Scenario: Agent considers native session tools
- **WHEN** an office agent needs to ask, delegate to, notify, or hand off to another office agent
- **THEN** it does not invoke `sessions_list`, `sessions_send`, `openclaw agents`, or an equivalent private provider path for that interaction

#### Scenario: VO communication is unavailable
- **WHEN** roster lookup or the VO communication endpoint cannot provide a valid route
- **THEN** the sender returns the real failure or unavailable state without privately resending the request

#### Scenario: Target is busy or times out
- **WHEN** the VO communication response is `busy`, `timeout`, or has no valid reply
- **THEN** the sender preserves that status and does not interpret it as success or automatically retry over a private channel

### Requirement: Traceable communication history
Virtual Office SHALL persist each accepted cross-agent request and its resulting reply or terminal failure in office-owned communication history using the same `conversationId`, with the actual sender and target identities available for later inspection.

#### Scenario: Cross-agent request completes
- **WHEN** the VO communication endpoint returns a target-agent reply
- **THEN** the request and reply can be queried from VO history by `conversationId`

#### Scenario: Provider execution fails
- **WHEN** the target provider returns an execution error or terminal failure
- **THEN** VO history retains the request and the actual failure outcome without fabricating a reply

### Requirement: Truthful OpenClaw availability
Virtual Office SHALL report OpenClaw as detected only when the configured OpenClaw home contains usable agent configuration or discoverable agent data. The existence of an otherwise empty or skills-only directory SHALL NOT be sufficient to report OpenClaw as detected.

#### Scenario: Usable OpenClaw data exists
- **WHEN** the configured OpenClaw home contains parseable agent configuration or discoverable agent directories accepted by the roster discovery rules
- **THEN** VO reports OpenClaw as detected and exposes the discovered agents through the roster API

#### Scenario: Only a residual directory exists
- **WHEN** the configured OpenClaw home exists but contains no usable agent configuration and no discoverable agent data
- **THEN** VO reports OpenClaw as not detected and provides a non-sensitive configuration or availability indication

#### Scenario: OpenClaw configuration is malformed
- **WHEN** configured OpenClaw agent data cannot be parsed or validated
- **THEN** VO does not claim usable OpenClaw availability and does not populate the roster with guessed agents
