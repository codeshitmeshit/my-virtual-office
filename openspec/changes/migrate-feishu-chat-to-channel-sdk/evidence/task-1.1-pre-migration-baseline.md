# Task 1.1 Pre-migration Feishu Chat Baseline

Recorded: 2026-07-14 (Asia/Shanghai)

## Scope

This baseline characterizes the existing Python `lark_oapi` Feishu Chat transport before introducing `@larksuite/channel`. It intentionally changes no production code and establishes the observable contracts that the replacement transport must preserve.

## Contract coverage

| Contract | Characterization tests |
| --- | --- |
| Chat App configuration and notification App isolation | `test_feishu_chat_config_is_separate_from_notification_app`, `test_disabling_feishu_chat_config_stops_existing_long_connection`, `test_setup_save_disabling_feishu_chat_stops_existing_long_connection` |
| Authenticated inbound worker | `test_feishu_chat_worker_route_requires_token_and_dispatches` |
| Private-chat and supported-message policy | `test_feishu_channel_unsupported_chat_or_message_type_is_ignored`, `test_feishu_channel_empty_text_is_ignored_before_dispatch`, `test_feishu_channel_image_message_downloads_records_and_dispatches` |
| Representative-Agent selection and routing | `test_feishu_channel_representative_agent_change_affects_future_messages`, `test_feishu_channel_missing_representative_agent_does_not_dispatch`, `test_feishu_channel_unavailable_representative_agent_records_failure` |
| Provider routing and Feishu source metadata | `test_feishu_representative_dispatch_preserves_source_metadata_for_native_providers`, `test_feishu_channel_metadata_is_written_to_hermes_history` |
| Persistent idempotency and ordering | `test_feishu_channel_adapter_records_and_dedupes`, `test_feishu_channel_consecutive_messages_keep_order_and_conversation` |
| Channel records and communication-ledger/history projection | `test_feishu_channel_adapter_records_and_dedupes`, `test_feishu_chat_records_route_reads_recent_channel_records`, `test_feishu_channel_metadata_is_written_to_hermes_history` |
| Outbound reply, reaction, delete-reaction, receipt and recall behavior | `test_text_sender_uses_chat_app_credentials_without_leaking_secret`, `test_markdown_sender_preserves_markdown_without_prefix`, `test_feishu_channel_adds_and_deletes_message_reaction_receipt`, `test_feishu_channel_falls_back_to_temporary_receipt_when_reaction_fails` |
| Worker status projection | `test_feishu_chat_worker_status_and_card_action_state_are_isolated` |
| Notification/card-action state isolation | `test_feishu_chat_config_is_separate_from_notification_app`, `test_feishu_card_action_challenge_and_recording`, `test_feishu_chat_worker_status_and_card_action_state_are_isolated` |

The two task-specific tests added for this baseline are:

- `test_feishu_representative_dispatch_preserves_source_metadata_for_native_providers`: locks the Hermes, Codex, and Claude Code routing envelope and its Feishu metadata/attachment fields.
- `test_feishu_chat_worker_status_and_card_action_state_are_isolated`: locks worker-status projection through the existing config response and proves card-action processing does not replace either the Chat worker or notification receiver.

## Results

Focused task-specific tests:

```text
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_feishu_notifications.py -q -k 'representative_dispatch_preserves_source_metadata or worker_status_and_card_action_state_are_isolated'
..                                                                       [100%]
2 passed, 44 deselected in 0.15s
```

Feishu regression after replacing the environment-sensitive `lark_oapi` import assertion with an equivalent lightweight receiver serialization contract:

```text
PYTHONPYCACHEPREFIX=/private/tmp/cosh-pycache .venv/bin/python -m pytest tests/test_feishu_notifications.py -q
..................................................                       [100%]
50 passed in 0.31s
```

The replacement retains the actual contract under test: a handler result containing a plain toast dictionary is JSON serializable. It avoids importing the full legacy SDK solely to construct its response wrapper.
