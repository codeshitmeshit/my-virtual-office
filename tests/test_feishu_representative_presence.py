import os
import sys
import tempfile


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
APP = os.path.join(ROOT, "app")
if APP not in sys.path:
    sys.path.insert(0, APP)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ["VO_STATUS_DIR"] = tempfile.mkdtemp(prefix="vo-feishu-presence-")

import server


def test_openclaw_feishu_representative_is_working_while_provider_runs(monkeypatch):
    agent_id = "openclaw-feishu-presence"
    observed_states = []

    monkeypatch.setattr(
        server,
        "_find_agent_record",
        lambda requested: {
            "id": requested,
            "name": "Representative",
            "providerKind": "openclaw",
        },
    )

    def fake_deliver(*args, **kwargs):
        observed_states.append(server.gateway_presence.get_agent_state(agent_id)["state"])
        return "completed reply"

    monkeypatch.setattr(server.PROVIDER_CONVERSATION_SERVICE, "deliver_queued", fake_deliver)

    result = server._dispatch_representative_agent_message(
        agent_id,
        "please execute this task",
        "feishu-group:presence-regression",
        {
            "senderName": "Feishu User",
            "sourceMessageId": "om_presence_regression",
            "feishuChatId": "oc_presence_regression",
            "sourceSurface": "feishu-group",
        },
    )

    assert result["ok"] is True
    assert observed_states == ["working"]
    assert server.gateway_presence.get_agent_state(agent_id)["state"] == "idle"
