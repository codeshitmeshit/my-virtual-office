"""Static dependency and persistence boundaries for extracted project services."""

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SERVICES = ROOT / "app" / "services"
EXTRACTED = tuple(path.name for path in sorted(SERVICES.glob("*.py")) if path.name != "__init__.py")


def _tree(path: Path) -> ast.AST:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _attribute_name(node: ast.AST) -> str:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
    return ".".join(reversed(parts))


def test_extracted_services_do_not_import_server_or_http_transport():
    forbidden_imports = {"server", "app.server", "http.server"}
    forbidden_names = {
        "OfficeHandler", "BaseHTTPRequestHandler", "send_response",
        "send_header", "end_headers", "wfile", "rfile",
    }
    for filename in EXTRACTED:
        path = SERVICES / filename
        tree = _tree(path)
        imports = set()
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.add(node.module or "")
            elif isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
        assert not imports.intersection(forbidden_imports), f"{filename} imports HTTP/server transport: {imports}"
        assert not names.intersection(forbidden_names), f"{filename} references HTTP handler state: {names}"


def test_direct_project_store_writes_exist_only_in_repository_wiring():
    app_files = tuple((ROOT / "app").rglob("*.py"))
    direct_writes = []
    store_references = []
    for path in app_files:
        tree = _tree(path)
        relative = path.relative_to(ROOT).as_posix()
        if relative == "app/server.py":
            allowed_spans = []
            for node in tree.body:
                if not isinstance(node, (ast.Assign, ast.AnnAssign)):
                    continue
                targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                target_names = {target.id for target in targets if isinstance(target, ast.Name)}
                if target_names.intersection({"PROJECT_STORE", "_PROJECT_REPOSITORY"}):
                    allowed_spans.append((node.lineno, node.end_lineno or node.lineno))
        else:
            allowed_spans = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "PROJECT_STORE":
                store_references.append((relative, node.lineno, allowed_spans))
            if not isinstance(node, ast.Call):
                continue
            name = _attribute_name(node.func)
            method = name.rsplit(".", 1)[-1]
            if method == "save_all" or (method == "delete_project" and name != "project_command_service.delete_project"):
                direct_writes.append((relative, node.lineno, name, allowed_spans))
    assert all(
        path == "app/server.py" and any(start <= line <= end for start, end in spans)
        for path, line, spans in store_references
    ), store_references
    assert [(path, name) for path, _line, name, _spans in direct_writes] == [
        ("app/server.py", "PROJECT_STORE.save_all"),
        ("app/server.py", "PROJECT_STORE.delete_project"),
    ]
    assert all(any(start <= line <= end for start, end in spans) for _path, line, _name, spans in direct_writes)


def test_legacy_save_delegate_uses_repository_commit_snapshot():
    server_tree = _tree(ROOT / "app" / "server.py")
    save_function = next(
        node for node in server_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "_save_projects"
    )
    calls = {_attribute_name(node.func) for node in ast.walk(save_function) if isinstance(node, ast.Call)}
    assert "_PROJECT_REPOSITORY.commit_snapshot" in calls
    assert "PROJECT_STORE.save_all" not in calls
    assert "PROJECT_STORE.delete_project" not in calls
