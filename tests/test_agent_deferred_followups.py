from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from app.services.agent_deferred_followups import DeferredAgentFollowupScheduler


def test_deferred_followup_delivers_first_final_feishu_reply():
    replies = []
    delivered = []

    def find_reply(_payload):
        return replies[0] if replies else None

    scheduler = DeferredAgentFollowupScheduler(
        find_reply=find_reply,
        deliver_reply=lambda payload, reply: delivered.append((dict(payload), dict(reply))) or {"ok": True},
        wait_seconds=2,
        interval_seconds=0.05,
    )

    result = scheduler.schedule({
        "requestEventId": "event-1",
        "conversationId": "conv-1",
        "agentId": "market-research-team-agent",
        "sourceContext": {"sourceApp": "feishu", "sourceMessageId": "om-1"},
    })
    assert result["status"] == "scheduled"

    replies.append({"id": "reply-1", "text": "最终研究结果"})
    deadline = time.time() + 1
    while not delivered and time.time() < deadline:
        time.sleep(0.02)

    assert delivered[0][0]["requestEventId"] == "event-1"
    assert delivered[0][1]["text"] == "最终研究结果"


def test_deferred_followup_ignores_non_feishu_sources():
    scheduler = DeferredAgentFollowupScheduler(
        find_reply=lambda _payload: None,
        deliver_reply=lambda _payload, _reply: {"ok": True},
        wait_seconds=1,
        interval_seconds=0.05,
    )

    result = scheduler.schedule({
        "requestEventId": "event-1",
        "conversationId": "conv-1",
        "agentId": "market-research-team-agent",
        "sourceContext": {"sourceApp": "virtual-office"},
    })

    assert result == {"ok": True, "status": "not_required", "reason": "non_feishu_source"}
