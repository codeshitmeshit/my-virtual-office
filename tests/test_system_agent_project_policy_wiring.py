"""Server wiring coverage for system-role project and deletion protection."""

import os
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_HR_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-system-policy-status-"))
os.environ.setdefault("VO_OPENCLAW_PATH", tempfile.mkdtemp(prefix="vo-system-policy-openclaw-"))

import server


def test_server_rejects_hr_assignment_and_deletion_without_provider_mutation(monkeypatch):
    provider_calls = []
    monkeypatch.setattr(
        server,
        "_gateway_rpc_call",
        lambda *args, **kwargs: provider_calls.append((args, kwargs)) or {"ok": True},
    )
    assignment = server._system_agent_assignment_error("hr", "task")
    assert assignment["code"] == "system_agent_not_assignable"
    assert assignment["systemRole"] == "hr"
    assert assignment["_status"] == 400

    deletion = server._handle_agent_delete({"id": "HR"})
    assert deletion["code"] == "system_agent_cannot_delete"
    assert deletion["systemRole"] == "hr"
    assert deletion["_status"] == 403
    assert provider_calls == []


def test_archive_manager_codes_remain_compatible_through_general_policy():
    assert server._system_agent_assignment_error(
        "archive-manager", "project_defaults",
    )["code"] == "archive_manager_not_assignable"
    assert server._system_agent_deletion_error(
        "archive-manager",
    )["code"] == "archive_manager_cannot_delete"


def test_server_policy_can_resolve_a_persisted_provider_hr_identity(monkeypatch):
    class PersistedHR:
        @staticmethod
        def is_hr(candidate):
            return candidate == "provider-hr-7"

    monkeypatch.setattr(server, "_hr_shared_adapter", lambda: PersistedHR())
    rejected = server._system_agent_deletion_error("provider-hr-7")
    assert rejected["code"] == "system_agent_cannot_delete"
    assert rejected["systemRole"] == "hr"


def test_project_authoring_and_score_paths_exclude_every_unassignable_system_role():
    assert server._PROJECT_AUTHORING_SERVICE.is_excluded_agent("archive-manager") is True
    assert server._PROJECT_AUTHORING_SERVICE.is_excluded_agent("hr") is True
    assert server._PROJECT_AUTHORING_SERVICE.is_excluded_agent("ordinary-agent") is False
    assert server._score_valid_agent_key("archive-manager") == ""
    assert server._score_valid_agent_key("hr") == ""
    assert server._score_valid_agent_key("ordinary-agent") == "ordinary-agent"


def test_template_rejects_hr_before_workspace_or_project_mutation(monkeypatch):
    template = {
        "id": "template-hr",
        "title": "Unsafe",
        "description": "",
        "columns": [{"title": "Backlog"}],
        "taskTemplates": [{"title": "HR task", "assignee": "hr"}],
    }
    workspace_calls = []
    save_calls = []
    monkeypatch.setattr(server, "_load_projects", lambda: {"projects": [], "templates": []})
    monkeypatch.setattr(server, "_project_browser_templates", lambda _data: [template])
    monkeypatch.setattr(
        server,
        "_project_prepare_workspace",
        lambda *args: workspace_calls.append(args) or {"ok": True},
    )
    monkeypatch.setattr(server, "_save_projects", lambda data: save_calls.append(data))

    result = server._handle_project_from_template({
        "templateId": "template-hr",
        "title": "Rejected project",
    })
    assert result["code"] == "system_agent_not_assignable"
    assert result["systemRole"] == "hr"
    assert workspace_calls == []
    assert save_calls == []


def test_extracted_project_commands_no_longer_depend_on_archive_specific_policy_names():
    source = (APP_DIR / "services" / "project_commands.py").read_text(encoding="utf-8")
    assert "is_archive_manager" not in source
    assert "system_agent_assignment_error" in source
