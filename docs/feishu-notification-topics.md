# Feishu notification-topic conversations

Verified baseline: 2026-08-10. Topic conversations now also support the foreground commands documented below.

This feature lets a human continue a long-running Virtual Office result inside a topic under the application-level notification bot's direct message. Each verified topic receives an independent Agent conversation. It does not change Chat App or group-chat behavior.

## Identity and scope

- Inbound events come from the existing notification App `FeishuLongConnectionReceiver`, not the separately configured Chat App Channel SDK worker.
- Only `chatType=p2p` topic messages are eligible.
- The root must match an authenticated successful notification audit record whose `topicContext.classification` is `long_running_diversion` and which identifies the originating conversation and Agent.
- Ordinary notification-bot DMs, other notification types, bot/system messages, and every group-chat event remain unchanged.
- Replies and approval cards use the notification App credentials and Feishu's native message-reply API with `reply_in_thread=true`.

## Configuration

The feature is default-off.

```json
{
  "notifications": {
    "topicConversationsEnabled": false
  }
}
```

Environment override:

```text
VO_FEISHU_NOTIFICATION_TOPICS_ENABLED=true
```

This flag does not alter `feishu.chatApp`, `groupChatEnabled`, Channel SDK `requireMention`, or Feishu permissions.

## Foreground commands

Only an activated notification topic handles these exact commands; ordinary DMs and group chats keep their existing behavior.

- `/here`: creates a bounded branch from the current topic context and routes any notification through the centralized notification-delivery boundary.
- `/change`: lists the Agents available to this topic and shows the current selection.
- `/change <agent>`: changes the active Agent for this topic only. It does not mutate Provider configuration, audit records, or another topic.

Commands with attachments, unknown Agents, inactive topics, or malformed arguments fail without changing the binding. The topic binding store remains the single owner of the selected Agent.

## Notification producer contract

Successful long-running result notifications should include this bounded metadata in their common notification intent:

```json
{
  "topicContext": {
    "classification": "long_running_diversion",
    "conversationId": "originating VO conversation id",
    "agentId": "originating Agent id",
    "requestId": "optional request reference",
    "responseId": "optional response reference",
    "title": "optional bounded title",
    "summary": "optional bounded summary",
    "requestText": "optional bounded original request",
    "responseText": "optional bounded original response",
    "goal": "optional bounded established goal"
  }
}
```

The notification audit persists only bounded values. Missing optional context degrades inheritance; missing classification, originating conversation, or Agent prevents activation.

## Local verification

Production-shaped data is represented by redacted fixtures in `tests/test_feishu_notification_topics.py`.

```bash
.venv/bin/python -m pytest -q \
  tests/test_feishu_notification_topics.py \
  tests/test_feishu_topic_foreground_commands.py \
  tests/test_feishu_chat_commands.py
```

The tests cover normalization, root verification, opaque identity, atomic binding, prompt boundaries, idempotency, ordering, different-topic progress, queue pressure, restart recovery, Provider-neutral dispatch, topic delivery, and approval cards.

## Read-only production preflight

Keep the feature disabled and submit one explicitly selected notification root to:

```text
POST /api/feishu-notification/topic-preflight
Content-Type: application/json

{"rootMessageId":"<selected Feishu message id>"}
```

The response exposes only a root hash, classification, and required-field presence. It does not return message bodies, credentials, or raw user/conversation identifiers.
The endpoint refuses to perform a lookup while `topicConversationsEnabled=true`; disable the feature before every preflight audit.

## Rollout

1. Deploy with the feature disabled and run the read-only preflight for one known long-running notification.
2. If the production record differs, add a focused `NotificationRootLookup` compatibility adapter and capture its redacted shape as a local fixture.
3. Enable the feature for a controlled test window and create a topic under the selected notification.
4. Verify no `@` is needed, activation is acknowledged once, context inheritance is disclosed, later turns reuse the same conversation and Agent, and all output remains in the topic.
5. Verify ordinary bot DMs and group chats are unchanged. Observe root-verification, queue, Agent, recovery, and delivery counters before expanding use.

## Rollback

Set `topicConversationsEnabled=false` (or the environment override to false). No Feishu permission, Chat App worker, database, or data rollback is required. Existing bindings remain inert and can be reused after re-enabling.
