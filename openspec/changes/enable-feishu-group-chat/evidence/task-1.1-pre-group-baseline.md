# Task 1.1 Pre-Group-Chat Baseline

## Scope

This evidence locks the Feishu Agent Chat behavior before group admission is implemented. Task 1.1 changes tests and evidence only; production code is unchanged.

The new integrated characterization `test_feishu_private_only_baseline_contract_before_group_enablement` proves that:

- management configuration exposes only `allowedChatTypes: ["p2p"]`;
- a `group` event remains rejected even if it contains structured `isBot` mention metadata;
- bound private text and image turns share one `feishu-dm:*` conversation;
- private text/image requests and replies remain visible in the communication ledger and Feishu SSE replay;
- rejected group input creates only an ignored channel record and no provider, outbound, ledger, history, or SSE effect;
- notification application credentials remain isolated from Chat processing; and
- the selected Chat transport remains `channel-sdk-node` while the existing legacy override contract is covered separately.

## Coverage Map

| Baseline area | Characterization |
| --- | --- |
| Private-only configuration | `test_feishu_private_only_baseline_contract_before_group_enablement` |
| Group rejection | `test_feishu_private_only_baseline_contract_before_group_enablement`, `test_feishu_channel_unsupported_chat_or_message_type_is_ignored` |
| Private identity and binding | `test_feishu_private_only_baseline_contract_before_group_enablement`, `test_feishu_chat_bindings_config_is_persisted_and_lookupable`, `test_feishu_channel_unbound_user_dispatches_with_feishu_source_identity` |
| Text/image handling | `test_feishu_channel_adapter_records_and_dedupes`, `test_feishu_channel_image_message_downloads_records_and_dispatches`, `test_feishu_chat_worker_normalizes_rich_post_with_image_resource_as_multimodal_message` |
| Durable inbound contract | `test_feishu_chat_worker_v1_envelope_returns_durable_ack_and_persists_metadata` |
| Ledger/history visibility | `test_feishu_channel_adapter_records_and_dedupes`, `test_feishu_private_only_baseline_contract_before_group_enablement`, `ChatHistoryContractTest.test_comm_history_includes_only_selected_agent_feishu_cross_conversation`, `ChatHistoryContractTest.test_comm_history_page_merges_feishu_rows_with_stable_pagination` |
| SSE live/replay behavior | `test_feishu_sse_replays_real_comm_event_when_in_memory_publish_is_missed`, `test_feishu_sse_stream_writes_replayed_event_without_queue_publish`, integrated baseline replay assertion |
| Notification/card-action isolation | `test_feishu_chat_config_is_separate_from_notification_app`, `test_feishu_chat_worker_status_and_card_action_state_are_isolated` |
| Node/legacy selection | `test_feishu_chat_transport_selection_and_node_command_ports_are_backward_compatible` |
| Node protocol, spool, resources, status, and bounds | `integrations/feishu-channel-worker/test/*.test.mjs` |

## Reproducible Commands and Results

Focused Python characterization:

```bash
.venv/bin/python -m pytest -q \
  tests/test_feishu_notifications.py::test_feishu_chat_config_is_separate_from_notification_app \
  tests/test_feishu_notifications.py::test_feishu_channel_adapter_records_and_dedupes \
  tests/test_feishu_notifications.py::test_feishu_private_only_baseline_contract_before_group_enablement \
  tests/test_feishu_notifications.py::test_feishu_sse_replays_real_comm_event_when_in_memory_publish_is_missed \
  tests/test_feishu_notifications.py::test_feishu_sse_stream_writes_replayed_event_without_queue_publish \
  tests/test_feishu_notifications.py::test_feishu_chat_worker_v1_envelope_returns_durable_ack_and_persists_metadata \
  tests/test_feishu_notifications.py::test_feishu_chat_worker_normalizes_rich_post_with_image_resource_as_multimodal_message \
  tests/test_feishu_notifications.py::test_feishu_chat_transport_selection_and_node_command_ports_are_backward_compatible \
  tests/test_feishu_notifications.py::test_feishu_chat_worker_status_and_card_action_state_are_isolated \
  tests/test_feishu_notifications.py::test_feishu_chat_bindings_config_is_persisted_and_lookupable \
  tests/test_feishu_notifications.py::test_feishu_channel_unsupported_chat_or_message_type_is_ignored \
  tests/test_feishu_notifications.py::test_feishu_channel_image_message_downloads_records_and_dispatches \
  tests/test_feishu_notifications.py::test_feishu_channel_unbound_user_dispatches_with_feishu_source_identity
```

Result: **13 passed in 1.34s**.

Normalized history characterization:

```bash
.venv/bin/python -m pytest -q \
  tests/test_chat_history_api.py::ChatHistoryContractTest::test_comm_history_includes_only_selected_agent_feishu_cross_conversation \
  tests/test_chat_history_api.py::ChatHistoryContractTest::test_comm_history_page_merges_feishu_rows_with_stable_pagination
```

Result: **2 passed in 0.13s**.

Node worker baseline:

```bash
cd integrations/feishu-channel-worker
npm test
```

Result: **22 passed, 0 failed**. The suite covers authenticated commands, reply/send compatibility, resource safety, exact SDK dependency, strict v1 protocol, secret redaction, atomic status, durable spool/replay, callback recovery, timeout, and queue bounds.

## Baseline Conclusion

The pre-change behavior is deterministic and green: private Chat remains functional and visible in VO, groups remain unsupported with no Agent effect, notification/card-action configuration remains isolated, and both Node and legacy compatibility seams are characterized. This evidence is the comparison point for later group-enable tasks.
