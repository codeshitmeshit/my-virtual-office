from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"


def test_agent_decision_create_passes_validated_header_identity():
    source = SERVER.read_text(encoding="utf-8")
    route_start = source.index('if request_path == "/api/agent/human-decisions"')
    route_end = source.index('if request_path == "/api/human-decisions"', route_start)
    route = source[route_start:route_end]

    assert 'agent_id=str(self.headers.get("X-VO-Agent-Id") or "").strip()' in route
    assert "HUMAN_DECISION_WORKFLOW.create(" in route
    assert "body," in route


def test_server_wires_durable_chat_continuation_to_shared_communication_service():
    source = SERVER.read_text(encoding="utf-8")
    workflow_start = source.index("HUMAN_DECISION_WORKFLOW = HumanDecisionWorkflow(")
    workflow_end = source.index("\nos.makedirs(STATUS_DIR", workflow_start)
    wiring = source[workflow_start:workflow_end]
    dispatch_start = source.index("def _dispatch_human_decision_chat_continuation(")
    dispatch_end = source.index("\ndef ", dispatch_start + 5)
    dispatch = source[dispatch_start:dispatch_end]

    assert "HUMAN_DECISION_CHAT_CONTINUATION = HumanDecisionChatContinuation(" in source
    assert "chat_continuation=HUMAN_DECISION_CHAT_CONTINUATION" in wiring
    assert "continuation_kick=_kick_human_decision_chat_continuation" in wiring
    assert "_vo_agent_communication_service().send_trusted_resume(request)" in dispatch
    assert 'ContinuationDispatchResult("dispatched")' in dispatch
    assert '"not_dispatched_retryable"' in dispatch
    assert '"dispatch_uncertain"' in dispatch
