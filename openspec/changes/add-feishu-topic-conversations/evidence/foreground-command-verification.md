# Foreground command verification

Date: 2026-08-01

Scope:

- `/here` foreground command parsing, main-chat delegation, topic interception, bounded context selection, notification branch intent construction, duplicate handling, delivery failure handling, and light local acknowledgement behavior.
- `/change` foreground command parsing, topic-local Agent catalog, empty-catalog handling, topic binding Agent updates, topic command handling, server wiring, unsupported-location rejection, later-turn dispatch to the selected Agent, sibling-topic isolation, and concurrent Agent binding updates.
- Centralization guardrails for unified notification sending and topic-local Agent selection ownership.

Manual acceptance checklist:

- Task 13.2: In the Feishu main direct chat, send one ordinary message and then `/here`; verify Virtual Office posts only a short local acknowledgement in the source chat and creates a replyable notification topic whose card summarizes the immediately preceding relevant context.
- Task 13.3: From an already activated notification topic, send an ordinary topic message and then `/here`; verify the resulting child notification topic has its own independent conversation and the parent topic/main chat history is not polluted by child turns.
- Task 13.4: In an activated notification topic, verify bare `/change` lists available Agents, `/change <agent-id-or-alias>` acknowledges the topic-local Agent switch, `/change unsupported-agent` rejects without changing state, and later topic replies dispatch only to that topic's selected Agent.
- Unsupported-location check: Send `/change` in the main direct chat and, if available, an ordinary bot-DM timeline or group chat; verify the command is rejected locally and no topic Agent selection changes.
- Rollback/non-regression check: Temporarily disable `topicConversationsEnabled`, verify new topic activation stops while ordinary notification config, card actions, Chat App DM, and group chat behavior remain available, then re-enable the flag and confirm `/change` again lists Agents from the live roster.

Commands and results:

```text
.venv/bin/python -m pytest -q --tb=short tests/test_feishu_topic_foreground_commands.py tests/test_feishu_notification_topics.py tests/test_feishu_chat_commands.py tests/test_feishu_chat_command_server.py
103 passed in 2.70s
```

```text
.venv/bin/python -m pytest -q --tb=short tests/test_feishu_chat_command_server.py tests/test_feishu_notification_topics.py tests/test_feishu_topic_foreground_commands.py tests/test_feishu_chat_commands.py
101 passed in 2.62s
```

```text
.venv/bin/python -m pytest -q --tb=short tests/test_feishu_topic_foreground_commands.py tests/test_feishu_chat_command_server.py
41 passed in 1.57s
```

```text
.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notifications.py tests/test_feishu_notification_recipients.py tests/test_feishu_notification_topics.py tests/test_feishu_topic_foreground_commands.py tests/test_feishu_chat_commands.py tests/test_feishu_chat_command_server.py tests/test_chat_slash_commands_characterization.py tests/test_chat_commands_service.py tests/test_chat_command_runtime.py tests/test_provider_conversations.py tests/test_agent_followup_delivery.py
243 passed in 4.72s
```

```text
.venv/bin/python -m pytest -q --tb=short tests/test_feishu_notifications.py tests/test_feishu_notification_recipients.py tests/test_feishu_notification_topics.py tests/test_feishu_topic_foreground_commands.py tests/test_feishu_chat_commands.py tests/test_feishu_chat_command_server.py tests/test_chat_slash_commands_characterization.py tests/test_chat_commands_service.py tests/test_chat_command_runtime.py tests/test_provider_conversations.py tests/test_agent_followup_delivery.py tests/test_provider_runtime_config.py
256 passed in 6.67s
```

```text
node tests/check_chat_slash_commands.mjs
chat slash command regression checks passed
```

```text
openspec validate add-feishu-topic-conversations --strict
Change 'add-feishu-topic-conversations' is valid
```

```text
git diff --check
passed
```

```text
curl -fsS http://127.0.0.1:7243/health
{"ok": true, "status": "running"}
```

```text
curl -fsS -X POST http://127.0.0.1:7243/api/feishu-notification/config ...
topicConversationsEnabled: true
topicConversationModels: [{"label": "当前 Codex", "model": "gpt-5.5", "aliases": ["current", "codex", "default"]}]
notificationRecipientPolicy: originating_user_dm
```

```text
curl -fsS http://127.0.0.1:7243/api/feishu-notification/config
topicConversationsEnabled: true
topicConversationModels: [{"label": "当前 Codex", "model": "gpt-5.5", "aliases": ["current", "codex", "default"]}]
feishuLongConnection.status: running
```

```text
curl -fsS -X POST http://127.0.0.1:7243/api/feishu-notification/config ...
topicConversationsEnabled: false
topicConversationModels preserved: [{"label": "当前 Codex", "model": "gpt-5.5", "aliases": ["current", "codex", "default"]}]
feishuLongConnection.status: running
```

```text
curl -fsS -X POST http://127.0.0.1:7243/api/feishu-notification/topic-preflight ...
{"ok": false, "rootHash": "4a547ba96e3908aa", "classification": "unverified", "fields": {"messageId": false, "conversationId": false, "agentId": false, "request": false, "response": false}}
```

```text
curl -fsS -X POST http://127.0.0.1:7243/api/feishu-notification/config ...
topicConversationsEnabled: true
topicConversationModels preserved: [{"label": "当前 Codex", "model": "gpt-5.5", "aliases": ["current", "codex", "default"]}]
feishuLongConnection.status: running
```

Notes:

- The Python regression commands include notification sends, recipient policy, topic conversation activation/recovery, foreground command behavior, Feishu chat command behavior, server wiring, slash guard behavior, Provider conversation behavior, and agent follow-up delivery.
- Product correction follow-up changed `/change` from topic-local model selection to topic-local Agent selection; bare `/change` now lists live roster Agents and `/change <agent>` updates the current topic binding's `agent_id`.
- Product correction follow-up removed `topicModel` propagation from representative-Agent dispatch payloads; later topic turns route to the selected Agent instead of overriding a model.
- Code review follow-up verified `/change` state remains behind the notification-topic binding/store path, not Provider adapters, notification audit records, chat handlers, or `app/server.py`.
- Manual-readiness follow-up registered the notification long connection's `bot_p2p_chat_entered` event as a no-op, with a fake-SDK registration regression, so opening the bot DM during acceptance does not produce SDK "processor not found" noise or dispatch a topic message.
- Manual-readiness follow-up exposed the safe notification-topic preflight route through the main `OfficeHandler` POST path, preserving the existing split-route handler and redacted response contract.
- Local runtime was prepared for manual command acceptance by enabling notification topic conversations; `/change` now derives choices from the live Agent roster.
- Local rollback-readiness check verified that disabling `topicConversationsEnabled` preserves existing Feishu long connection behavior, the safe preflight route returns only hashed/boolean evidence while disabled, and re-enabling restores the acceptance-ready configuration.
- Node coverage is a focused slash-command static regression because this change does not add frontend UI behavior.
- Local service restart completed successfully after the final server wiring, Agent-catalog guard, and binding-store changes; real Feishu topic behavior remains tracked separately in tasks 13.2 through 13.5 because those require true client-side Feishu interaction.
