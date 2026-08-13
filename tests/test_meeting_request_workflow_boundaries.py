def test_meeting_request_workflow_has_explicit_ports_and_no_server_hydration():
    from app.services import meeting_request_workflow

    fields = set(meeting_request_workflow.MeetingRequestPorts.__dataclass_fields__)
    assert {"repository", "block_project", "update_blocker", "send_notification", "run_meeting"} <= fields
    source = open(meeting_request_workflow.__file__, encoding="utf-8").read()
    assert "import server" not in source
    assert "sys.modules" not in source
    assert "_hydrate" not in source
