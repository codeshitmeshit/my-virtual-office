"""Stable cross-domain protection errors for VO system-Agent roles."""

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.system_agent_policy import assignment_error, deletion_error
from services.system_agent_roles import ARCHIVE_MANAGER_ROLE, HR_ROLE


def test_archive_manager_policy_preserves_legacy_codes_and_messages():
    project = assignment_error(ARCHIVE_MANAGER_ROLE, scope="project_defaults")
    task = assignment_error(ARCHIVE_MANAGER_ROLE, scope="task")
    deletion = deletion_error(ARCHIVE_MANAGER_ROLE)
    assert project.code == "archive_manager_not_assignable"
    assert project.message == "档案管理员不能作为普通项目默认执行或审查 AI"
    assert task.code == "archive_manager_not_assignable"
    assert task.message == "档案管理员不能被分配普通项目任务"
    assert deletion.code == "archive_manager_cannot_delete"
    assert deletion.status == 403


def test_hr_policy_uses_stable_system_role_codes_and_pause_direction():
    assignment = assignment_error(HR_ROLE, scope="task")
    deletion = deletion_error(HR_ROLE)
    assert assignment.as_payload() == {
        "error": "HR 是 VO 系统角色，不能被分配普通项目工作",
        "code": "system_agent_not_assignable",
        "systemRole": "hr",
        "operation": "project_assignment",
        "_status": 400,
    }
    assert deletion.code == "system_agent_cannot_delete"
    assert deletion.role_key == "hr"
    assert deletion.status == 403
    assert "暂停控制" in deletion.message


def test_unknown_or_permitted_roles_have_no_protection_error():
    assert assignment_error(None) is None
    assert deletion_error(None) is None
