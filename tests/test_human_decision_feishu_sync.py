from __future__ import annotations

from app.dashboard_realtime import build_dashboard_snapshot, diff_dashboard_events
from app.services.human_decision_workflow import HumanDecisionWorkflow
from app.services.human_decisions import HumanDecisionStore
from tests.test_human_decisions import request_payload


class FeishuAcceptanceDelivery:
    def __init__(self):
        self.updated = []

    def deliver(self, decision, **_configs):
        return {"ok": True, "status": "sent", "messageId": "om_acceptance", "application": "notification"}

    def update_terminal(self, decision, records, **_configs):
        self.updated.append({"decision": decision, "records": records})
        return [{"ok": True, "status": "updated", "messageId": "om_acceptance"}]


def test_feishu_submit_updates_card_and_emits_dashboard_decision_event(tmp_path):
    delivery = FeishuAcceptanceDelivery()
    workflow = HumanDecisionWorkflow(
        store=HumanDecisionStore(tmp_path / "human-decisions.json"),
        delivery=delivery,
        notification_config=lambda: {"appId": "notification", "appSecret": "secret", "receiveId": "oc_notification"},
        chat_config=lambda: {},
        fallback_chat_id=lambda: "",
    )
    created = workflow.create(request_payload())
    decision_id = created["decision"]["id"]
    before = build_dashboard_snapshot({}, [], [], decisions=created["snapshot"])

    callback = workflow.handle_feishu_action(
        {"action": "human_decision_submit", "decision_id": decision_id, "option_id": "A"},
        {"custom_answer": "先给 10 位内部用户灰度"},
        {"openId": "ou_acceptance"},
    )
    after = build_dashboard_snapshot({}, [], [], decisions=callback["snapshot"])
    events = diff_dashboard_events(before, after)

    assert callback["decision"]["resolution"]["channel"] == "feishu"
    assert callback["decision"]["resolution"]["answer"] == "先给 10 位内部用户灰度"
    assert callback["decision"]["resolution"]["optionId"] is None
    assert delivery.updated[0]["records"][0]["messageId"] == "om_acceptance"
    assert [name for name, _ in events] == ["dashboard.decisions"]
    assert events[0][1]["decisions"]["decisions"][0]["status"] == "resolved"
