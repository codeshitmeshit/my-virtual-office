## Why

The Feishu Agent Chat channel currently accepts only private `p2p` messages, so teams cannot collaborate with the representative Agent inside a trusted group. This change adds an explicit group-chat product scope for groups whose administrators intentionally add the bot, while preserving isolation from private conversations and the VO chat UI.

## What Changes

- Accept text and image messages from a Feishu group only when the bot is explicitly mentioned.
- Treat intentional bot membership as the trust decision for the group; any group member may mention the bot without a separate VO binding or allowlist.
- Maintain one continuous shared Agent conversation per Feishu group, isolated from every other group and every private conversation.
- Reply in the originating group and preserve sender attribution for each triggering member.
- Keep non-mentioned group messages outside the Agent pipeline and outside the group conversation history.
- Keep group requests and replies out of the VO chat UI and its Feishu SSE synchronization path.
- Preserve the existing private-chat behavior and its current UI synchronization.

## Capabilities

### New Capabilities

- `feishu-agent-group-chat`: Defines trusted-group admission, mention-gated text and image interaction, shared per-group context, cross-conversation isolation, sender attribution, delivery behavior, and failure handling.

### Modified Capabilities

- `chat-history-navigation`: Excludes Feishu group-chat communication from normalized VO chat history and live refresh while preserving existing private-chat visibility.

## Impact

- Feishu Chat App event normalization, inbound policy, representative-Agent routing, conversation identity, message/resource handling, outbound reply operations, audit records, and tests.
- Normalized chat-history selection and Feishu SSE publication/filtering.
- Feishu application permissions and real-tenant acceptance for group message events and replies.
- No intended change to the separate Feishu notification/card-action application, private-chat binding behavior, or provider-native conversation contracts.
