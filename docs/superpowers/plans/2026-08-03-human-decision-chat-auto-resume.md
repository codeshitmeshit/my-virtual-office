# Human Decision Chat Auto-Resume Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (\`- [ ]\`) syntax for tracking.

**Goal:** Resolve a chat-origin human decision by durably and at most once waking the original VO Agent in the original conversation, even when the browser is closed.

**Architecture:** \`HumanDecisionStore\` remains the single persisted authority and keeps a private continuation record beside each chat decision. A new \`human_decision_chat_continuation.py\` service owns binding validation, XML prompt construction, atomic claim/result transitions, and dispatch classification; \`HumanDecisionWorkflow\` only queues and kicks this service after a terminal decision. Thin server wiring supplies the trusted Agent identity and reuses \`VOAgentCommunicationService\` for the original conversation.

**Tech Stack:** Python 3, JSON-file persistence with atomic replacement, existing VO Agent provider adapters, \`services.bridge_input_output_formatting\`, pytest, OpenSpec.

## Global Constraints

- Only \`source.type=chat\` automatically resumes in this phase; meeting and task lifecycles remain unchanged.
- Use the exact chat \`conversationId\` as \`source.id\`, and bind the Agent only from trusted \`X-VO-Agent-Id\` transport context.
- Do not keep the creating Provider turn alive with polling.
- Use the stable source message ID \`human-decision-resume:{decisionId}\` and the original Agent/conversation.
- Never expose Agent, conversation, claim-token, lease, or raw provider-error fields in Dashboard or Feishu projections.
- Put all provider-visible prompts in an XML outer envelope assembled by \`services.bridge_input_output_formatting\`; decision data is untrusted and escaped.
- Do not add another frontend SSE, WebSocket, polling loop, or chat history.
- Retry only failures known to happen before provider dispatch, at most three attempts; ambiguous dispatch becomes \`uncertain\` and is not retried automatically.
- Place new orchestration in focused files; keep \`app/server.py\` to trusted transport extraction and dependency wiring.
- Preserve unrelated dirty-worktree changes and stage only files owned by this feature.

---

### Task 1: Expose the trusted conversation identity to chat Agents

**Files:**
- Modify: \`app/services/agent_platform_prompt_formatting.py\`
- Modify: \`app/services/bridge_prompt_preprocessing.py\`
- Modify: \`skills/vo-human-decision/SKILL.md\`
- Test: \`tests/test_bridge_prompt_preprocessing.py\`
- Test: \`tests/test_human_decision_skill.py\`

**Interfaces:**
- Consumes: existing bridge metadata keys \`agent_id\`, \`provider_kind\`, and \`conversation_id\`.
- Produces: an XML \`<conversation_context>\` section and a Skill contract requiring chat \`source.id == conversationId\`.

- [ ] **Step 1: Write failing prompt and Skill tests**

\`\`\`python
def test_local_chat_prompt_exposes_escaped_conversation_context():
    prompt = preprocess_bridge_prompt({
        "message": "continue",
        "metadata": {
            "agent_id": "agent-1",
            "provider_kind": "codex",
            "conversation_id": "chat<&1",
        },
    })
    assert "<conversation_context>" in prompt
    assert "chat&lt;&amp;1" in prompt
\`\`\`

Add a Skill assertion that chat requests use the displayed conversation ID and end the current turn after creation rather than polling.

- [ ] **Step 2: Run tests and verify RED**

Run: \`.venv/bin/python -m pytest -q tests/test_bridge_prompt_preprocessing.py tests/test_human_decision_skill.py\`

- [ ] **Step 3: Implement the minimal formatter and Skill changes**

Pass a named nested mapping to the shared formatter and render it as one semantic XML section:

\`\`\`python
conversation_context = {
    "agent_id": metadata.get("agent_id", ""),
    "provider_kind": metadata.get("provider_kind", ""),
    "conversation_id": metadata.get("conversation_id", ""),
}
\`\`\`

- [ ] **Step 4: Run tests and verify GREEN**

Run: \`.venv/bin/python -m pytest -q tests/test_bridge_prompt_preprocessing.py tests/test_human_decision_skill.py\`

- [ ] **Step 5: Commit only Task 1 files**

\`\`\`bash
git add app/services/agent_platform_prompt_formatting.py app/services/bridge_prompt_preprocessing.py skills/vo-human-decision/SKILL.md tests/test_bridge_prompt_preprocessing.py tests/test_human_decision_skill.py
git commit -m "feat: expose chat decision continuation context"
\`\`\`

### Task 2: Persist and atomically claim private continuation state

**Files:**
- Modify: \`app/services/human_decisions.py\`
- Test: \`tests/test_human_decisions.py\`

**Interfaces:**
- Consumes: the existing JSON lock/write discipline and injected clock/token factory.
- Produces: \`bind_chat_continuation\`, \`queue_chat_continuation\`, \`claim_due_chat_continuations\`, \`complete_chat_continuation\`, \`retry_chat_continuation\`, and \`mark_chat_continuation_uncertain\`.

- [ ] **Step 1: Write failing persistence and projection tests**

\`\`\`python
store.bind_chat_continuation(decision_id, agent_id="agent-1", conversation_id="chat-1")
assert "_continuation" not in store.get(decision_id)
store.resolve(decision_id, {"optionId": "A"}, channel="local")
store.queue_chat_continuation(decision_id)
first = store.claim_due_chat_continuations(limit=10, lease_seconds=30)
second = store.claim_due_chat_continuations(limit=10, lease_seconds=30)
assert [item.decision_id for item in first] == [decision_id]
assert second == []
\`\`\`

Also reload the JSON file, prove \`queued/retry_wait\` survives restart, prove expired \`running\` becomes \`uncertain\`, and prove public output exposes only \`status\`, \`attempts\`, \`updatedAt\`, and \`errorCategory\`.

- [ ] **Step 2: Run tests and verify RED**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decisions.py\`

- [ ] **Step 3: Implement the finite-state persistence contract**

\`\`\`python
"_continuation": {
    "kind": "chat",
    "agentId": "agent-1",
    "conversationId": "chat-1",
    "status": "waiting",
    "attempts": 0,
    "nextAttemptAt": None,
    "claimToken": "",
    "leaseExpiresAt": None,
    "updatedAt": "...",
    "errorCategory": "",
}
\`\`\`

All transitions validate current status and claim token under the store lock, increment revision, and atomically replace the JSON file. \`_public\` removes private continuation data and emits only the safe summary.

- [ ] **Step 4: Run tests and verify GREEN**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decisions.py\`

- [ ] **Step 5: Commit only Task 2 files**

\`\`\`bash
git add app/services/human_decisions.py tests/test_human_decisions.py
git commit -m "feat: persist chat decision continuation state"
\`\`\`

### Task 3: Add the focused continuation dispatcher

**Files:**
- Create: \`app/services/human_decision_chat_continuation.py\`
- Create: \`tests/test_human_decision_chat_continuation.py\`

**Interfaces:**
- Consumes: the Task 2 store port and injected \`dispatch(ContinuationDispatchRequest) -> ContinuationDispatchResult\`.
- Produces: \`HumanDecisionChatContinuation\`, \`ContinuationDispatchRequest\`, \`ContinuationDispatchResult\`, \`queue(decision_id)\`, and \`process_due(limit=10)\`.

- [ ] **Step 1: Write failing XML, dispatch, and failure-classification tests**

\`\`\`python
request = continuation.build_dispatch_request(claim)
assert request.agent_id == "agent-1"
assert request.conversation_id == "chat-1"
assert request.source_message_id == f"human-decision-resume:{decision_id}"
assert "&lt;/untrusted_decision_data&gt;" in request.prompt
\`\`\`

Test success -> \`completed\`, explicit pre-dispatch busy -> \`retry_wait\`, third safe failure -> \`failed\`, ambiguous result -> \`uncertain\`, and repeated processing never redispatches completed/uncertain work.

- [ ] **Step 2: Run tests and verify RED**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decision_chat_continuation.py\`

- [ ] **Step 3: Implement XML prompt construction and dispatch transitions**

The trusted envelope expresses role, task, rules, and output. Put a JSON object containing decision ID, answer, situation, reason, and next step beneath one untrusted data boundary. Carry Agent/conversation/source-message identity outside prompt text.

- [ ] **Step 4: Run tests and verify GREEN**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decision_chat_continuation.py\`

- [ ] **Step 5: Commit only Task 3 files**

\`\`\`bash
git add app/services/human_decision_chat_continuation.py tests/test_human_decision_chat_continuation.py
git commit -m "feat: dispatch resolved chat decisions"
\`\`\`

### Task 4: Queue continuations from every valid resolution path

**Files:**
- Modify: \`app/services/human_decision_workflow.py\`
- Modify: \`tests/test_human_decision_workflow.py\`
- Modify: \`tests/test_human_decision_feishu.py\`

**Interfaces:**
- Consumes: \`HumanDecisionChatContinuation.queue\` and \`.process_due\`.
- Produces: \`HumanDecisionWorkflow.create(payload, agent_id="")\`, non-blocking kicks after local/Feishu/timeout resolution, and periodic recovery through \`process_due\`.

- [ ] **Step 1: Write failing workflow tests**

Test that a chat create with trusted Agent ID binds once, task/meeting creates never bind, local and Feishu first resolutions each queue once, idempotent callbacks never queue twice, and \`process_due\` delegates after reminder/timeout work.

- [ ] **Step 2: Run tests and verify RED**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decision_workflow.py tests/test_human_decision_feishu.py\`

- [ ] **Step 3: Add injected continuation orchestration**

Extend the constructor with an optional continuation collaborator. Pass trusted Agent ID only for chat creation. After a successful first terminal transition, queue and kick background processing without waiting for Provider completion. Preserve current behavior when no collaborator is configured.

- [ ] **Step 4: Run tests and verify GREEN**

Run: \`.venv/bin/python -m pytest -q tests/test_human_decision_workflow.py tests/test_human_decision_feishu.py\`

- [ ] **Step 5: Commit only Task 4 files**

\`\`\`bash
git add app/services/human_decision_workflow.py tests/test_human_decision_workflow.py tests/test_human_decision_feishu.py
git commit -m "feat: queue chat continuation on decision"
\`\`\`

### Task 5: Reuse VO Agent communication in the original conversation

**Files:**
- Modify: \`app/services/vo_agent_communication.py\`
- Modify: \`app/server.py\`
- Test: \`tests/test_vo_agent_communication.py\`
- Test: \`tests/test_human_decision_http.py\`

**Interfaces:**
- Consumes: \`ContinuationDispatchRequest\` and existing VO Agent provider routing/history behavior.
- Produces: a trusted internal communication method targeting an exact Agent/conversation and a thin server adapter returning \`dispatched\`, \`not_dispatched_retryable\`, or \`dispatch_uncertain\`.

- [ ] **Step 1: Write failing service and HTTP tests**

Prove trusted resume uses the original Agent and \`conversationId\`, writes the provider reply to that conversation, includes stable \`sourceMessageId\`, rejects missing binding, and lets \`/api/agent/human-decisions\` use the validated header Agent ID rather than a body field.

- [ ] **Step 2: Run tests and verify RED**

Run: \`.venv/bin/python -m pytest -q tests/test_vo_agent_communication.py tests/test_human_decision_http.py\`

- [ ] **Step 3: Implement the internal method and thin wiring**

Add an explicitly named internal resume method instead of weakening public human-source validation. In \`app/server.py\`, instantiate the continuation service, pass the validated header Agent ID into workflow creation, and let the existing minute timer process due continuations. Keep state-transition rules out of the server.

- [ ] **Step 4: Run tests and verify GREEN**

Run: \`.venv/bin/python -m pytest -q tests/test_vo_agent_communication.py tests/test_human_decision_http.py\`

- [ ] **Step 5: Commit only Task 5 files**

\`\`\`bash
git add app/services/vo_agent_communication.py app/server.py tests/test_vo_agent_communication.py tests/test_human_decision_http.py
git commit -m "feat: resume original chat after human decision"
\`\`\`

### Task 6: Update OpenSpec and verify the complete behavior

**Files:**
- Modify: \`openspec/changes/add-decision-request-ui-prototype/proposal.md\`
- Modify: \`openspec/changes/add-decision-request-ui-prototype/design.md\`
- Modify: \`openspec/changes/add-decision-request-ui-prototype/specs/human-decision-center-ui/spec.md\`
- Modify: \`openspec/changes/add-decision-request-ui-prototype/tasks.md\`

**Interfaces:**
- Consumes: all prior task behavior.
- Produces: an auditable requirement, design decision, and completed task checklist.

- [ ] **Step 1: Add the chat auto-resume requirement and scenarios**

Specify original Agent/conversation continuation, browser-independent wake, single dispatch under duplicate resolve/callback, safe retry, ambiguous \`uncertain\`, and meeting/task exclusions.

- [ ] **Step 2: Record the durable state machine and server boundary**

Document \`waiting -> queued -> running -> completed|retry_wait|failed|uncertain\`, trusted Agent binding, stable source-message ID, XML untrusted boundary, and reuse of existing communication/history.

- [ ] **Step 3: Run focused and regression tests**

\`\`\`bash
.venv/bin/python -m pytest -q tests/test_human_decisions.py tests/test_human_decision_chat_continuation.py tests/test_human_decision_workflow.py tests/test_human_decision_feishu.py tests/test_human_decision_http.py tests/test_bridge_prompt_preprocessing.py tests/test_human_decision_skill.py tests/test_vo_agent_communication.py tests/test_dashboard_realtime.py
node tests/check_dashboard_realtime_static.mjs
node tests/check_human_decision_center.mjs
\`\`\`

- [ ] **Step 4: Validate OpenSpec and inspect the exact diff**

\`\`\`bash
openspec validate add-decision-request-ui-prototype --json
git diff --check
git status --short
git diff -- app/services/human_decisions.py app/services/human_decision_chat_continuation.py app/services/human_decision_workflow.py app/services/vo_agent_communication.py app/server.py skills/vo-human-decision/SKILL.md tests openspec/changes/add-decision-request-ui-prototype
\`\`\`

- [ ] **Step 5: Mark continuation tasks complete and commit artifacts**

\`\`\`bash
git add openspec/changes/add-decision-request-ui-prototype/proposal.md openspec/changes/add-decision-request-ui-prototype/design.md openspec/changes/add-decision-request-ui-prototype/specs/human-decision-center-ui/spec.md openspec/changes/add-decision-request-ui-prototype/tasks.md
git commit -m "docs: specify decision driven chat resume"
\`\`\`
