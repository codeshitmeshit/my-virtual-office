from app.services.meeting_request_reconciliation import MeetingRequestReconciliation, ReconciliationPorts


class Repository:
    def __init__(self):
        self.data = {"requests": {"r1": {"id": "r1", "reconciliation": []}}, "meetings": {}}

    def get_request(self, request_id):
        return self.data["requests"].get(request_id)

    def get_meeting(self, meeting_id):
        return self.data["meetings"].get(meeting_id)

    def mutate_request(self, request_id, mutator):
        result = mutator(self.data)
        return self.data, result


def service(repository, *, block_result=None):
    return MeetingRequestReconciliation(ReconciliationPorts(
        repository=repository, now=lambda: "2026-08-13T00:00:00Z",
        summarize=lambda value, limit: str(value)[:limit],
        block_project=lambda *args: block_result or {"ok": True},
        update_blocker=lambda *args, **kwargs: {"ok": True},
        apply_meeting_result=lambda *args, **kwargs: {"ok": True},
    ))


def test_record_is_bounded_and_successful_retry_resolves_entry():
    repository = Repository()
    workflow = service(repository)
    assert workflow.record("r1", "project_block_create", {"error": "temporary"}, {"projectId": "p1", "taskId": "t1"})
    result = workflow.reconcile("r1")
    assert result == {"ok": True, "attempted": 1, "results": [{"key": "r1:project_block_create", "operation": "project_block_create", "ok": True}]}
    entry = repository.data["requests"]["r1"]["reconciliation"][0]
    assert entry["status"] == "resolved" and entry["resolvedAt"]


def test_failed_retry_stays_pending_and_unknown_request_is_stable():
    repository = Repository()
    workflow = service(repository, block_result={"ok": False, "error": "still unavailable"})
    workflow.record("r1", "project_block_create", {"error": "temporary"}, {})
    assert workflow.reconcile("r1")["ok"] is False
    assert repository.data["requests"]["r1"]["reconciliation"][0]["status"] == "pending"
    assert workflow.reconcile("missing")["_status"] == 404


def test_reconciliation_module_has_no_server_dependency():
    import app.services.meeting_request_reconciliation as module
    source = open(module.__file__, encoding="utf-8").read()
    assert "import server" not in source and "sys.modules" not in source
