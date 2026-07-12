"""Artifact boundary characterization before the Service extraction."""

import os
import sys
import tempfile


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("VO_HERMES_ENABLED", "0")
os.environ.setdefault("VO_CODEX_ENABLED", "0")
os.environ.setdefault("VO_STATUS_DIR", tempfile.mkdtemp(prefix="vo-artifact-import-"))

import server
from services import artifacts as artifact_service


def _write(path, data=b"data"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    mode = "wb" if isinstance(data, bytes) else "w"
    kwargs = {} if isinstance(data, bytes) else {"encoding": "utf-8"}
    with open(path, mode, **kwargs) as handle:
        handle.write(data)


def test_missing_or_relative_root_fails_closed_for_all_operations(monkeypatch, tmp_path):
    _write(str(tmp_path / "cwd-secret.md"), "must remain")
    monkeypatch.chdir(tmp_path)
    invalid_contexts = [
        {},
        {"root": ""},
        {"root": "   "},
        {"root": "."},
        {"root": None},
    ]
    for context in invalid_contexts:
        context["sourcesByPath"] = {"cwd-secret.md": [{"taskId": "t"}]}
        assert artifact_service.list_artifacts(context)["_status"] == 409
        assert artifact_service.read_artifact(context, "cwd-secret.md")["_status"] == 409
        assert artifact_service.open_file(context, "cwd-secret.md")["_status"] == 409
        assert artifact_service.delete_file(context, "cwd-secret.md")["_status"] == 409
        assert artifact_service.delete_directory(context, "")["_status"] == 409
        assert (tmp_path / "cwd-secret.md").read_text() == "must remain"


def test_list_is_bounded_markdown_only_and_does_not_follow_excluded_or_escape_links():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        _write(os.path.join(root, "docs", "guide.md"), "# guide")
        _write(os.path.join(root, "docs", "data.json"), "{}")
        _write(os.path.join(root, "node_modules", "pkg", "README.md"), "# dependency")
        _write(os.path.join(outside, "escaped.md"), "# outside")
        os.symlink(outside, os.path.join(root, "linked-outside"))
        result = artifact_service.list_artifacts({"root": root, "sourcesByPath": {}})
        assert result["ok"] is True
        assert [item["path"] for item in result["artifacts"]] == ["docs/guide.md"]
        assert result["artifacts"][0]["unassociated"] is True


def test_read_preserves_status_contract_and_utf8_truncation_limit():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "doc.md"), "x" * (server._ARTIFACT_MAX_READ_BYTES + 16))
        _write(os.path.join(root, "data.json"), "{}")
        context = {"root": root, "sourcesByPath": {}}
        result = artifact_service.read_artifact(context, "doc.md")
        assert result["ok"] is True
        assert result["artifact"]["truncated"] is True
        assert len(result["artifact"]["content"]) == server._ARTIFACT_MAX_READ_BYTES
        assert artifact_service.read_artifact(context, "") == {"error": "Artifact path is required", "_status": 400}
        assert artifact_service.read_artifact(context, "../doc.md")["_status"] == 400
        assert artifact_service.read_artifact(context, "data.json")["_status"] == 415
        assert artifact_service.read_artifact(context, "missing.md")["_status"] == 404


def test_file_preview_requires_supported_extension_and_explicit_project_association():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "registered.mp4"), b"video")
        _write(os.path.join(root, "private.mp4"), b"private")
        _write(os.path.join(root, "script.py"), "print('x')")
        context = {"root": root, "sourcesByPath": {"registered.mp4": [{"taskId": "t"}]}}
        result = artifact_service.open_file(context, "registered.mp4")
        assert result["ok"] is True
        with result["opened"] as opened:
            assert opened.kind == "video"
            assert opened.relative_path == "registered.mp4"
        assert artifact_service.open_file(context, "private.mp4")["_status"] == 403
        assert artifact_service.open_file(context, "script.py")["_status"] == 415


def test_traversal_symlink_escape_and_non_regular_files_are_rejected():
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        _write(os.path.join(outside, "secret.md"), "secret")
        os.symlink(os.path.join(outside, "secret.md"), os.path.join(root, "escape.md"))
        context = {"root": root, "sourcesByPath": {"escape.md": [{"taskId": "t"}]}}
        assert artifact_service.read_artifact(context, "escape.md")["_status"] == 403
        assert artifact_service.open_file(context, "escape.md")["_status"] == 403
        assert artifact_service.delete_file(context, "escape.md")["_status"] == 403
        assert artifact_service.open_file(context, "%2e%2e/secret.md")["_status"] == 400
        if hasattr(os, "mkfifo"):
            os.mkfifo(os.path.join(root, "pipe.md"))
            assert artifact_service.read_artifact(context, "pipe.md")["_status"] == 403


def test_delete_file_keeps_status_and_extension_policy():
    with tempfile.TemporaryDirectory() as root:
        allowed = os.path.join(root, "report.md")
        forbidden = os.path.join(root, "tool.py")
        _write(allowed, "report")
        _write(forbidden, "tool")
        context = {"root": root, "sourcesByPath": {}}
        result = artifact_service.delete_file(context, "report.md")
        assert result == {"ok": True, "deleted": "report.md"}
        assert not os.path.exists(allowed)
        assert artifact_service.delete_file(context, "tool.py")["_status"] == 415
        assert os.path.exists(forbidden)


def test_root_level_delete_rejects_workspace_root_symlink_swap(monkeypatch):
    with tempfile.TemporaryDirectory() as parent, tempfile.TemporaryDirectory() as outside:
        root = os.path.join(parent, "workspace")
        original_root = os.path.join(parent, "workspace-original")
        os.mkdir(root)
        _write(os.path.join(root, "victim.md"), "inside")
        outside_victim = os.path.join(outside, "victim.md")
        _write(outside_victim, "outside")
        original_open = artifact_service.os.open
        swapped = {"value": False}

        def swap_root_before_open(path, flags, *args, **kwargs):
            if path == root and "dir_fd" not in kwargs and not swapped["value"]:
                swapped["value"] = True
                os.rename(root, original_root)
                os.symlink(outside, root)
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(artifact_service.os, "open", swap_root_before_open)
        try:
            result = artifact_service.delete_file({"root": root}, "victim.md")
            assert result.get("ok") is not True
            assert os.path.exists(outside_victim)
            assert open(outside_victim, encoding="utf-8").read() == "outside"
        finally:
            if os.path.islink(root):
                os.unlink(root)
            if os.path.isdir(original_root):
                os.rename(original_root, root)


def test_operations_reject_workspace_root_real_directory_swap(monkeypatch):
    operations = [
        lambda context: artifact_service.list_artifacts(context),
        lambda context: artifact_service.read_artifact(context, "victim.md"),
        lambda context: artifact_service.open_file(context, "victim.md", associated_only=False),
        lambda context: artifact_service.delete_file(context, "nested/victim.md"),
        lambda context: artifact_service.delete_directory(context, "generated"),
    ]
    for operation in operations:
        with tempfile.TemporaryDirectory() as parent:
            root = os.path.join(parent, "workspace")
            canonical_root = os.path.realpath(root)
            original_root = os.path.join(parent, "workspace-original")
            replacement = os.path.join(parent, "replacement")
            os.mkdir(root)
            os.mkdir(replacement)
            for base, content in ((root, "inside"), (replacement, "replacement")):
                _write(os.path.join(base, "victim.md"), content)
                _write(os.path.join(base, "nested", "victim.md"), content)
                _write(os.path.join(base, "generated", "victim.md"), content)
            original_open = artifact_service.os.open
            swapped = {"value": False}

            def swap_root_before_open(path, flags, *args, **kwargs):
                if path == canonical_root and "dir_fd" not in kwargs and not swapped["value"]:
                    swapped["value"] = True
                    os.rename(root, original_root)
                    os.rename(replacement, root)
                return original_open(path, flags, *args, **kwargs)

            monkeypatch.setattr(artifact_service, "_secure_open_available", lambda: True)
            monkeypatch.setattr(artifact_service.os, "open", swap_root_before_open)
            try:
                result = operation({"root": root, "sourcesByPath": {}})
                assert result.get("ok") is not True
                assert open(os.path.join(root, "victim.md"), encoding="utf-8").read() == "replacement"
                assert open(os.path.join(root, "nested", "victim.md"), encoding="utf-8").read() == "replacement"
                assert open(os.path.join(root, "generated", "victim.md"), encoding="utf-8").read() == "replacement"
            finally:
                monkeypatch.setattr(artifact_service.os, "open", original_open)
                if swapped["value"] and os.path.isdir(root):
                    os.rename(root, replacement)
                if os.path.isdir(original_root):
                    os.rename(original_root, root)


def test_directory_delete_is_allowlist_recursive_and_preserves_other_files():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "generated", "one.md"), "one")
        _write(os.path.join(root, "generated", "nested", "two.png"), b"png")
        _write(os.path.join(root, "generated", "keep.py"), "keep")
        _write(os.path.join(root, "outside.md"), "outside")
        context = {"root": root, "sourcesByPath": {}}
        result = artifact_service.delete_directory(context, "generated")
        assert result["ok"] is True
        assert result["deleted"] == 2
        assert os.path.exists(os.path.join(root, "generated", "keep.py"))
        assert os.path.exists(os.path.join(root, "outside.md"))
        assert artifact_service.delete_directory(context, "../")["_status"] in {400, 403}


def test_list_item_limit_sets_truncated_without_scanning_unbounded_results():
    with tempfile.TemporaryDirectory() as root:
        for index in range(server._ARTIFACT_MAX_ITEMS + 5):
            _write(os.path.join(root, f"{index:04d}.md"), str(index))
        result = artifact_service.list_artifacts({"root": root, "sourcesByPath": {}})
        assert result["ok"] is True
        assert len(result["artifacts"]) == server._ARTIFACT_MAX_ITEMS
        assert result["truncated"] is True


def test_read_rejects_symlink_swap_between_validation_and_open(monkeypatch):
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        target = os.path.join(root, "report.md")
        secret = os.path.join(outside, "secret.md")
        _write(target, "safe")
        _write(secret, "api_key=canary")
        original_open = artifact_service._open_component_no_follow
        swapped = {"value": False}

        def swap_before_open(root_value, relative, expected_root):
            if relative == "report.md" and not swapped["value"]:
                swapped["value"] = True
                os.unlink(target)
                os.symlink(secret, target)
            return original_open(root_value, relative, expected_root)

        monkeypatch.setattr(artifact_service, "_open_component_no_follow", swap_before_open)
        result = artifact_service.read_artifact({"root": root, "sourcesByPath": {}}, "report.md")
        assert result.get("ok") is not True
        assert "canary" not in str(result)


def test_open_file_returns_handle_not_reopenable_path():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "video.mp4"), b"video")
        context = {"root": root, "sourcesByPath": {"video.mp4": [{"taskId": "t"}]}}
        result = artifact_service.open_file(context, "video.mp4")
        assert result["ok"] is True
        assert "path" not in result
        with result["opened"] as opened:
            assert opened.read() == b"video"


def test_opened_artifact_closes_descriptor_on_client_interruption():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "video.mp4"), b"video")
        context = {"root": root, "sourcesByPath": {"video.mp4": [{"taskId": "t"}]}}
        result = artifact_service.open_file(context, "video.mp4")
        assert result["ok"] is True
        opened = result["opened"]
        try:
            with opened:
                assert opened.read(2) == b"vi"
                raise BrokenPipeError("client disconnected")
        except BrokenPipeError:
            pass
        assert opened.closed is True


def test_open_fallback_revalidates_regular_file(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "report.md"), "report")
        monkeypatch.setattr(
            artifact_service,
            "_open_component_no_follow",
            lambda *args, **kwargs: (_ for _ in ()).throw(NotImplementedError()),
        )
        result = artifact_service.read_artifact({"root": root, "sourcesByPath": {}}, "report.md")
        assert result["ok"] is True
        assert result["artifact"]["content"] == "report"


def test_handler_stream_closes_opened_artifact_when_client_disconnects():
    class BrokenWriter:
        def write(self, _data):
            raise BrokenPipeError("disconnected")

    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "video.mp4"), b"video")
        result = artifact_service.open_file(
            {"root": root, "sourcesByPath": {"video.mp4": [{"taskId": "t"}]}},
            "video.mp4",
        )
        opened = result["opened"]
        handler = server.OfficeHandler.__new__(server.OfficeHandler)
        handler.wfile = BrokenWriter()
        handler.path = "/api/projects/p/artifacts/file?path=video.mp4"
        handler.send_response = lambda _status: None
        handler.send_header = lambda _name, _value: None
        handler.end_headers = lambda: None
        assert handler._stream_opened_artifact(opened) is False
        assert opened.closed is True


def test_inline_read_can_require_explicit_association():
    with tempfile.TemporaryDirectory() as root:
        _write(os.path.join(root, "private.json"), '{"secret":"value"}')
        context = {"root": root, "sourcesByPath": {}}
        blocked = artifact_service.read_artifact(
            context, "private.json", allow_text=True, associated_only=True,
        )
        assert blocked["_status"] == 403
        context["sourcesByPath"]["private.json"] = [{"taskId": "t"}]
        allowed = artifact_service.read_artifact(
            context, "private.json", allow_text=True, associated_only=True,
        )
        assert allowed["ok"] is True


def test_fallback_rejects_regular_file_inode_swap(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        target = os.path.join(root, "registered.mp4")
        replacement = os.path.join(root, "replacement.mp4")
        _write(target, b"registered")
        _write(replacement, b"api_key=canary")
        original_open = artifact_service.os.open
        swapped = {"value": False}

        def swap_on_open(path, flags, *args, **kwargs):
            if os.path.basename(path) == "registered.mp4" and not swapped["value"]:
                swapped["value"] = True
                os.replace(replacement, target)
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(
            artifact_service, "_open_component_no_follow",
            lambda *args, **kwargs: (_ for _ in ()).throw(NotImplementedError()),
        )
        monkeypatch.setattr(artifact_service.os, "open", swap_on_open)
        result = artifact_service.open_file(
            {"root": root, "sourcesByPath": {"registered.mp4": [{"taskId": "t"}]}},
            "registered.mp4",
        )
        assert result.get("ok") is not True
        assert "canary" not in str(result)


def test_delete_fails_closed_when_secure_dir_fd_is_unavailable(monkeypatch):
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        _write(os.path.join(root, "report.md"), "report")
        _write(os.path.join(outside, "secret.md"), "secret")
        os.symlink(os.path.join(outside, "secret.md"), os.path.join(root, "escape.md"))
        monkeypatch.setattr(artifact_service, "_secure_file_delete_available", lambda: False)
        monkeypatch.setattr(artifact_service, "_secure_directory_delete_available", lambda: False)
        file_result = artifact_service.delete_file({"root": root}, "report.md")
        assert file_result["_status"] == 409
        assert file_result["code"] == "artifact_safe_delete_unavailable"
        assert artifact_service.delete_file({"root": root}, "escape.md")["_status"] == 403
        _write(os.path.join(root, "generated", "artifact.md"), "artifact")
        _write(os.path.join(root, "generated", "keep.py"), "keep")
        directory = artifact_service.delete_directory({"root": root}, "generated")
        assert directory["_status"] == 409
        assert directory["code"] == "artifact_safe_delete_unavailable"
        assert os.path.exists(os.path.join(root, "report.md"))
        assert os.path.exists(os.path.join(root, "generated", "artifact.md"))
        assert os.path.exists(os.path.join(root, "generated", "keep.py"))
        assert os.path.exists(os.path.join(outside, "secret.md"))


def test_directory_delete_rejects_top_level_symlink_swap(monkeypatch):
    with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
        target = os.path.join(root, "generated")
        _write(os.path.join(target, "inside.md"), "inside")
        _write(os.path.join(outside, "secret.md"), "outside")
        original_open = artifact_service.os.open
        swapped = {"value": False}

        def swap_target(path, flags, *args, **kwargs):
            if path == "generated" and kwargs.get("dir_fd") is not None and not swapped["value"]:
                swapped["value"] = True
                os.rename(target, target + "-old")
                os.symlink(outside, target)
            return original_open(path, flags, *args, **kwargs)

        monkeypatch.setattr(artifact_service, "_secure_directory_delete_available", lambda: True)
        monkeypatch.setattr(artifact_service, "_secure_open_available", lambda: True)
        monkeypatch.setattr(artifact_service.os, "open", swap_target)
        result = artifact_service.delete_directory({"root": root}, "generated")
        assert result.get("ok") is not True
        assert os.path.exists(os.path.join(outside, "secret.md"))


def test_scan_and_delete_have_independent_work_limits(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        for index in range(20):
            _write(os.path.join(root, f"ignored-{index}.py"), "x")
        monkeypatch.setattr(artifact_service, "MAX_SCANNED_ENTRIES", 10)
        listed = artifact_service.list_artifacts({"root": root, "sourcesByPath": {}})
        assert listed["ok"] is True
        assert listed["truncated"] is True

    with tempfile.TemporaryDirectory() as root:
        for index in range(4):
            _write(os.path.join(root, "generated", f"{index}.md"), "x")
        monkeypatch.setattr(artifact_service, "MAX_DELETED_FILES", 2)
        deleted = artifact_service.delete_directory({"root": root}, "generated")
        assert deleted["ok"] is True
        assert deleted["truncated"] is True
        assert deleted["deleted"] == 2
        assert len(os.listdir(os.path.join(root, "generated"))) == 2


def test_directory_delete_checks_all_capabilities_before_mutation(monkeypatch):
    with tempfile.TemporaryDirectory() as root:
        artifact = os.path.join(root, "generated", "artifact.md")
        _write(artifact, "artifact")
        monkeypatch.setattr(artifact_service, "_secure_file_delete_available", lambda: True)
        monkeypatch.setattr(artifact_service, "_secure_directory_delete_available", lambda: False)
        result = artifact_service.delete_directory({"root": root}, "generated")
        assert result["_status"] == 409
        assert result["code"] == "artifact_safe_delete_unavailable"
        assert os.path.exists(artifact)
