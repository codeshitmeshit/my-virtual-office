#!/usr/bin/env python3
"""Static guardrails for provider-visible prompt formatting."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


BRIDGE_INTERNAL_DIRECT_FORMATTER_FILES = {
    "app/services/agent_platform_prompt_formatting.py",
    "app/services/bridge_input_output_formatting.py",
    "app/services/business_prompt_bridge.py",
}


TEMPORARY_BUSINESS_PROMPT_FORMATTER_EXCEPTIONS = set()


SUPPORT_DOCUMENT_FORMATTER_EXCEPTIONS = set()


SERVER_PRIVATE_PROMPT_WRAPPERS = {
    "_agent_template_files",
    "_archive_context_prompt_block",
    "_bridge_provider_delivery_prompt",
    "_feishu_group_provider_message",
    "_project_execution_build_prompt",
    "_project_execution_build_review_prompt",
    "_wf_build_project_context",
    "_wf_build_rework_prompt",
    "_wf_build_review_prompt",
    "_wf_build_task_prompt",
    "_with_vo_provider_guidance",
}


REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS = {
    "_agent_template_files",
    "_archive_context_prompt_block",
    "_bridge_provider_delivery_prompt",
    "_feishu_group_provider_message",
    "_project_execution_build_prompt",
    "_project_execution_build_review_prompt",
    "_wf_build_project_context",
    "_wf_build_rework_prompt",
    "_wf_build_review_prompt",
    "_wf_build_task_prompt",
    "_with_vo_provider_guidance",
}


REGISTERED_SERVER_PRIVATE_PROMPT_WRAPPER_TEST_REFERENCES = {}


def _python_prompt_files() -> list[Path]:
    roots = [ROOT / "app" / "server.py", ROOT / "app" / "server_services", ROOT / "app" / "services"]
    files: list[Path] = []
    for root in roots:
        if root.is_file():
            files.append(root)
        elif root.exists():
            files.extend(sorted(root.rglob("*.py")))
    return files


def _has_direct_low_level_prompt_formatter_render(text: str) -> bool:
    return "bridge_input_output_formatting" in text and "render_document(" in text


def _python_test_files() -> list[Path]:
    return sorted((ROOT / "tests").rglob("*.py"))


def _server_private_prompt_wrapper_references() -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    for path in _python_test_files():
        text = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(ROOT))
        for wrapper in SERVER_PRIVATE_PROMPT_WRAPPERS:
            if f"server.{wrapper}" in text:
                references.append((relative, wrapper))
    return sorted(references)


def test_legacy_output_contract_prompt_tags_do_not_return():
    offenders = []
    for path in _python_prompt_files():
        text = path.read_text(encoding="utf-8")
        if "<output_contract" in text or "<agent_output_contract" in text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_separate_agent_output_contract_module_was_removed():
    assert not (ROOT / "app" / "services" / "agent_output_contracts.py").exists()


def test_provider_visible_prompt_formatter_direct_usage_is_registered():
    allowed = (
        BRIDGE_INTERNAL_DIRECT_FORMATTER_FILES
        | TEMPORARY_BUSINESS_PROMPT_FORMATTER_EXCEPTIONS
        | SUPPORT_DOCUMENT_FORMATTER_EXCEPTIONS
    )
    offenders = []
    for path in _python_prompt_files():
        text = path.read_text(encoding="utf-8")
        relative = str(path.relative_to(ROOT))
        if _has_direct_low_level_prompt_formatter_render(text) and relative not in allowed:
            offenders.append(relative)

    assert offenders == []


def test_server_private_prompt_wrapper_test_references_are_registered():
    references = set(_server_private_prompt_wrapper_references())
    registered = set(REGISTERED_SERVER_PRIVATE_PROMPT_WRAPPER_TEST_REFERENCES)
    assert sorted(references - registered) == []
    assert sorted(registered - references) == []


def test_removed_server_private_prompt_wrappers_are_not_used_by_tests():
    removed_references = [
        (path, wrapper)
        for path, wrapper in _server_private_prompt_wrapper_references()
        if wrapper in REMOVED_SERVER_PRIVATE_PROMPT_WRAPPERS
    ]
    assert removed_references == []


def test_split_service_prompt_helpers_are_hydration_protected():
    expected = {
        "app/server_services/projects.py": {
            "_project_execution_build_prompt",
            "_project_execution_build_review_prompt",
        },
        "app/server_services/workflow.py": {
            "_wf_build_project_context",
            "_wf_build_rework_prompt",
            "_wf_build_review_prompt",
            "_wf_build_task_prompt",
        },
    }
    for relative, helpers in expected.items():
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert "_SERVICE_OWNED_PROMPT_HELPERS" in text
        assert "if key in _SERVICE_OWNED_PROMPT_HELPERS:" in text
        for helper in helpers:
            assert f'"{helper}"' in text
