import importlib
from pathlib import Path

from app.services import provider_skill_sync


def test_provider_skill_roots_follow_runtime_conventions(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    cases = [
        ("openclaw", workspace / "skills"),
        ("hermes", workspace / "skills"),
        ("codex", workspace / ".codex" / "skills"),
        ("claude-code", workspace / ".claude" / "skills"),
    ]

    for provider, expected in cases:
        root = provider_skill_sync.skill_root_for_agent(
            {"providerKind": provider, "workspace": str(workspace)}
        )
        assert root == expected


def test_install_and_delete_synced_skill_in_provider_directory(tmp_path):
    library_skill = tmp_path / "library" / "probe" / "SKILL.md"
    library_skill.parent.mkdir(parents=True)
    library_skill.write_text(
        "---\n"
        "name: probe\n"
        "description: Use when asked for PROBE_ACTIVATE.\n"
        "---\n\n"
        "# Probe\n\n"
        "Reply PROBE_LOADED.\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "codex-workspace"
    agent = {"id": "codex-local", "providerKind": "codex", "workspace": str(workspace)}

    installed = provider_skill_sync.install_skill_file(
        library_skill,
        "probe",
        agent,
        overwrite=False,
    )

    assert installed["ok"] is True
    target = workspace / ".codex" / "skills" / "probe" / "SKILL.md"
    assert Path(installed["path"]) == target
    assert target.read_text(encoding="utf-8").endswith("Reply PROBE_LOADED.\n")
    assert (target.parent / provider_skill_sync.SYNC_MARKER).read_text(encoding="utf-8") == "1\n"

    conflict = provider_skill_sync.install_skill_file(
        library_skill,
        "probe",
        agent,
        overwrite=False,
    )
    assert conflict["ok"] is False
    assert conflict["exists"] is True

    deleted = provider_skill_sync.delete_skill("probe", agent)
    assert deleted["ok"] is True
    assert deleted["deleted"] is True
    assert not target.exists()


def test_split_skills_service_uses_provider_neutral_apply(tmp_path, monkeypatch):
    app_path = Path(__file__).resolve().parents[1] / "app"
    monkeypatch.syspath_prepend(str(app_path))
    split_skills = importlib.import_module("server_services.skills")

    library_skill = tmp_path / "library" / "probe" / "SKILL.md"
    library_skill.parent.mkdir(parents=True)
    library_skill.write_text(
        "---\n"
        "name: probe\n"
        "description: Use when asked for PROBE_ACTIVATE.\n"
        "---\n\n"
        "# Probe\n\n"
        "Reply PROBE_LOADED.\n",
        encoding="utf-8",
    )
    workspace = tmp_path / "claude-workspace"

    monkeypatch.setattr(split_skills, "_get_skills_library_dir", lambda: str(tmp_path / "library"))
    monkeypatch.setattr(
        split_skills,
        "_skill_sync_agent_context",
        lambda agent_id: {
            "id": agent_id,
            "providerKind": "claude-code",
            "workspace": str(workspace),
        },
    )

    result = split_skills._handle_skills_library_apply({
        "skill": "probe",
        "agentId": "claude-code-local",
        "overwrite": True,
    })

    target = workspace / ".claude" / "skills" / "probe" / "SKILL.md"
    assert result["ok"] is True
    assert Path(result["path"]) == target
    assert target.read_text(encoding="utf-8").endswith("Reply PROBE_LOADED.\n")
    assert (target.parent / provider_skill_sync.SYNC_MARKER).is_file()
