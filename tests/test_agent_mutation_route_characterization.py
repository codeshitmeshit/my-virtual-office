"""Pre-migration characterization for Agent-related mutation routes.

These tests intentionally describe the current route topology and actor checks.
Later migration tasks must replace an assertion only when they also add the new
authorization/policy coverage described by the OpenSpec inventory.
"""

from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = (ROOT / "app" / "server.py").read_text(encoding="utf-8")
GAME = (ROOT / "app" / "game.js").read_text(encoding="utf-8")
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
MODELS = (ROOT / "app" / "models.html").read_text(encoding="utf-8")
SETUP = (ROOT / "app" / "setup.html").read_text(encoding="utf-8")
INVENTORY = (
    ROOT
    / "openspec"
    / "changes"
    / "add-vo-human-resources-management"
    / "evidence"
    / "agent-mutation-route-inventory.md"
).read_text(encoding="utf-8")


def _method_block(name: str, next_name: str) -> str:
    start = SERVER.index(f"    def {name}(self):")
    end = SERVER.index(f"    def {next_name}(self):", start)
    return SERVER[start:end]


def _route_block(source: str, route_literal: str, *, start: int = 0) -> str:
    route_at = source.index(route_literal, start)
    next_elif = source.find("\n        elif ", route_at + len(route_literal))
    next_else = source.find("\n        else:", route_at + len(route_literal))
    ends = [position for position in (next_elif, next_else) if position >= 0]
    return source[route_at : min(ends) if ends else len(source)]


def test_inventory_covers_every_required_mutation_surface_and_disposition():
    required_fragments = (
        "`POST /api/office-config`",
        "`POST /api/agent-workspace/{agent}`",
        "`POST /api/agent/create`",
        "`DELETE /api/agent/delete`",
        "`POST /api/agent/{agent}/skills`",
        "`DELETE /api/agent/{agent}/skills/{skill}`",
        "`POST /api/skills-library`",
        "`POST /set-model`",
        "`POST /setup/save`",
        "`POST /api/native-models/openclaw/agent-model`",
        "`POST /api/native-models/hermes/profile-model`",
        "`POST /api/native-models/{openclaw,hermes}/{auth,provider}/*`",
        "`POST /config/providers/{save-key,delete-key,save-custom}`",
        "`PUT /api/projects/{project}`",
        "`PUT /api/projects/{project}/tasks/{task}`",
        "`POST /api/presence/{agent}`",
        "`POST /api/agent-platform-communications/send`",
        "`POST /api/agent/project-authoring/*`",
        "**delegate**",
        "**split/delegate**",
        "**keep**",
        "**remove**",
    )
    for fragment in required_fragments:
        assert fragment in INVENTORY, f"inventory is missing {fragment}"
    assert "TBD" not in INVENTORY


def test_current_direct_agent_routes_are_explicitly_characterized_as_unprotected():
    # do_GET precedes do_POST in the source, so isolate do_POST to EOF instead.
    post_start = SERVER.index("    def do_POST(self):")
    post = SERVER[post_start:]
    delete = _method_block("do_DELETE", "do_OPTIONS")

    for route in (
        'self.path == "/api/office-config"',
        'self.path == "/api/agent/create"',
        'request_path.startswith("/api/agent-workspace/")',
        'self.path == "/set-model"',
    ):
        block = _route_block(post, route)
        assert "_reject_untrusted_management_request" not in block, route

    agent_delete = _route_block(delete, 'self.path == "/api/agent/delete"')
    assert "_reject_untrusted_management_request" not in agent_delete
    assert "_handle_agent_delete(body)" in agent_delete


def test_current_global_provider_and_project_prefixes_require_management_token():
    post_start = SERVER.index("    def do_POST(self):")
    post = SERVER[post_start:]
    native_guard = (
        'if request_path.startswith("/api/native-models/") '
        'or request_path.startswith("/config/providers/"):'
    )
    assert native_guard in post
    assert post.index(native_guard) < post.index(
        'elif self.path == "/api/native-models/openclaw/agent-model"'
    )
    assert post.index(native_guard) < post.index(
        'elif self.path == "/config/providers/save-custom"'
    )

    project_guard = (
        '(request_path == "/api/projects" or '
        'request_path.startswith("/api/projects/"))'
    )
    assert project_guard in post
    assert 'and self._reject_untrusted_management_request()' in post[
        post.index(project_guard) : post.index(project_guard) + 300
    ]

    put = _method_block("do_PUT", "do_DELETE")
    assert 'project_mutation = request_path.startswith("/api/projects/")' in put
    assert "if project_mutation or authoring_mutation:" in put
    assert "if self._reject_untrusted_management_request():" in put

    delete = _method_block("do_DELETE", "do_OPTIONS")
    assert (
        'urllib.parse.urlparse(self.path).path.startswith("/api/projects/") '
        "and self._reject_untrusted_management_request()"
    ) in delete


def test_current_agent_skill_and_library_writes_are_characterized_as_unprotected():
    post_start = SERVER.index("    def do_POST(self):")
    post = SERVER[post_start:]
    delete = _method_block("do_DELETE", "do_OPTIONS")

    skill_write = _route_block(
        post, 'self.path.startswith("/api/agent/") and "/skills" in self.path'
    )
    assert "_reject_untrusted_management_request" not in skill_write
    assert "_handle_skill_write(" in skill_write

    skill_delete = _route_block(
        delete, 'self.path.startswith("/api/agent/") and "/skills/" in self.path'
    )
    assert "_reject_untrusted_management_request" not in skill_delete
    assert "_handle_skill_delete(" in skill_delete

    for route in (
        'self.path == "/api/skills-library"',
        'self.path == "/api/skills-library/apply"',
        'self.path == "/api/skills-library/save-from-agent"',
        'self.path == "/api/skills-library/upload"',
    ):
        block = _route_block(post, route)
        assert "_reject_untrusted_management_request" not in block, route


def test_setup_route_has_its_own_management_check():
    post_start = SERVER.index("    def do_POST(self):")
    post = SERVER[post_start:]
    block = _route_block(post, 'self.path == "/setup/save"')
    assert "if self._reject_untrusted_management_request():" in block
    assert "_persist_setup_payload(body)" in block


def test_agent_workspace_multiplexer_actions_and_persistence_are_locked():
    start = SERVER.index("def _handle_agent_workspace_update(")
    end = SERVER.index("\ndef _agent_platform_comm_skill_content(", start)
    block = SERVER[start:end]
    actions = set(re.findall(r'(?:if|elif) action == "([^"]+)"', block))
    expected = {
        "addBulletin",
        "deleteBulletin",
        "updateBulletin",
        "addTask",
        "updateTask",
        "toggleTask",
        "startTask",
        "completeTask",
        "deleteTask",
        "setTaskMode",
        "addNote",
        "updateNote",
        "deleteNote",
        "readFile",
        "saveFile",
        "createFile",
        "deleteFile",
        "saveAgentSkill",
        "deleteAgentSkill",
        "saveLibrarySkill",
        "applyLibrarySkill",
        "saveAgentSkillToLibrary",
        "updateSettings",
    }
    assert actions == expected
    assert 'actor = (body.get("actor") or "user")' in block
    assert "_update_office_config_agent(key, patch)" in block
    assert "_save_agent_workspaces(store)" in block
    assert '"HEARTBEAT.md"' in block
    assert "_save_scores(scores)" in block


def test_current_browser_callers_distinguish_raw_and_managed_fetches():
    raw_calls = (
        "fetch('/api/office-config',",
        "fetch('/api/agent-workspace/'",
        "fetch('/api/agent/create',",
        "fetch('/api/agent/delete',",
        "fetch('/api/agent/'",
        "fetch('/api/skills-library/apply',",
    )
    for call in raw_calls:
        assert call in GAME

    assert "i18n.managementFetch('/setup/save'," in GAME
    assert (
        "i18n.managementFetch('/api/native-models/openclaw/agent-model',"
        in GAME
    )
    assert (
        "i18n.managementFetch('/api/native-models/openclaw/agent-model',"
        in INDEX
    )
    assert "i18n.managementFetch('/setup/save'," in SETUP
    assert "i18n.managementFetch('/config/providers/save-custom'," in MODELS


def test_current_persistence_owners_and_assignment_policy_are_visible():
    assert 'os.path.join(STATUS_DIR, "office-config.json")' in SERVER
    assert 'AGENT_WORKSPACES_FILE = os.path.join(STATUS_DIR, "agent-workspaces.json")' in SERVER
    assert "def _persist_setup_payload(body):" in SERVER
    assert "def _set_hermes_profile_model(" in SERVER
    assert "def _set_agent_model(" in SERVER
    assert "def _handle_agent_create(body):" in SERVER
    assert "def _handle_agent_delete(body):" in SERVER

    task_update_start = SERVER.index("def _handle_task_update(")
    task_update_end = SERVER.index("\ndef ", task_update_start + 5)
    task_update = SERVER[task_update_start:task_update_end]
    assert "project_command_service.update_task(" in task_update
    assert "system_agent_assignment_error=_system_agent_assignment_error" in task_update
    assert '"assignee"' in SERVER
    assert '"executorAgentId"' in SERVER
    assert '"reviewerAgentId"' in SERVER
