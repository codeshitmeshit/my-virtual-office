import threading
import time

from app import feishu_chat_channel


def test_async_acknowledgement_does_not_block_agent_dispatch():
    reaction_started = threading.Event()
    release_reaction = threading.Event()
    acknowledgement_recorded = threading.Event()
    records = []
    records_lock = threading.Lock()

    def record_event(record):
        with records_lock:
            stored = {"id": f"record-{len(records) + 1}", **record}
            records.append(stored)
        if record.get("event") == "acknowledgement_completed":
            acknowledgement_recorded.set()
        return stored

    def add_reaction(_message_id, _reaction_type):
        reaction_started.set()
        release_reaction.wait(timeout=2)
        return {"ok": True, "reactionId": "reaction-1"}

    body = {
        "event": {
            "sender": {"sender_id": {"open_id": "ou_async"}},
            "message": {
                "message_id": "om_async",
                "chat_id": "oc_async",
                "chat_type": "p2p",
                "message_type": "text",
                "content": {"text": "hello"},
            },
        }
    }
    started = time.monotonic()
    result = feishu_chat_channel.handle_message_event(
        body,
        cfg={
            "enabled": True,
            "appId": "cli_test",
            "appSecret": "secret",
            "representativeAgentId": "codex-local",
        },
        bindings={},
        load_records=lambda: [],
        idempotency_hit=lambda _message_id: None,
        record_event=record_event,
        lock_for=lambda _conversation_id: threading.Lock(),
        dispatch_agent=lambda *_args: {"ok": True, "reply": "done"},
        send_text=lambda *_args: {"ok": True, "messageId": "om_reply"},
        reply_text=None,
        find_agent=lambda _agent_id: {"id": "codex-local", "name": "Codex"},
        add_reaction=add_reaction,
        delete_reaction=lambda *_args: {"ok": True},
        mark_dispatching=lambda _message_id: {"executionPhase": "dispatching"},
        async_acknowledgement=True,
    )
    elapsed = time.monotonic() - started

    assert reaction_started.wait(timeout=1)
    assert elapsed < 0.5
    assert result["ok"] is True
    assert result["reply"] == "done"
    assert result["acknowledgementPending"] is True

    release_reaction.set()
    assert acknowledgement_recorded.wait(timeout=1)
    with records_lock:
        acknowledgement = next(record for record in records if record.get("event") == "acknowledgement_completed")
    assert acknowledgement["reactionResult"]["reactionId"] == "reaction-1"
    assert acknowledgement["reactionDeleteResult"]["ok"] is True
