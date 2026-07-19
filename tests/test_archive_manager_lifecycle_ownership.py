"""Static ownership guards for the extracted Archive Manager lifecycle."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVER = ROOT / "app" / "server.py"


def functions_by_name(tree):
    result = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            result.setdefault(node.name, []).append(node)
    return result


def source_for(name, source, functions):
    nodes = functions.get(name, [])
    assert len(nodes) == 1, f"{name} must have one compatibility delegate"
    return ast.get_source_segment(source, nodes[0]) or ""


def test_server_has_one_thin_delegate_per_archive_lifecycle_operation():
    source = SERVER.read_text(encoding="utf-8")
    tree = ast.parse(source)
    functions = functions_by_name(tree)

    forbidden = {
        "_archive_manager_write_direct_profile_file",
        "_archive_manager_read_profile_file_version",
        "_archive_manager_profile_needs_update",
        "_archive_manager_default_state",
        "_archive_manager_file",
    }
    assert forbidden.isdisjoint(functions)
    assert "_archive_manager_create_if_missing_legacy" not in source
    assert "_archive_manager_write_profile_files_legacy" not in source
    assert "ARCHIVE_MANAGER_PROFILE_VERSION_RE" not in source
    assert "ARCHIVE_MANAGER_FILE" not in source

    create = source_for("_archive_manager_create_if_missing", source, functions)
    assert "_archive_manager_shared_adapter().legacy_state" in create
    assert "agents.create" not in create
    assert "_gateway_rpc_call" not in create

    profile = source_for("_archive_manager_write_profile_files", source, functions)
    assert "synchronize_legacy" in profile
    assert "open(" not in profile
    assert "os.replace" not in profile

    state_save = source_for("_archive_manager_save_state", source, functions)
    assert "save_legacy" in state_save
    assert "json.dump" not in state_save
    assert "os.replace" not in state_save


def test_extracted_lifecycle_modules_never_import_legacy_server():
    for relative in (
        "app/services/system_agent_roles.py",
        "app/services/system_agent_profiles.py",
        "app/services/system_agent_lifecycle.py",
        "app/services/archive_manager_lifecycle.py",
    ):
        path = ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        assert not any(name == "server" or name.endswith(".server") for name in imports), relative
