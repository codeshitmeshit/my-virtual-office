#!/usr/bin/env python3
"""Provider-neutral execution contract helpers keep Codex and Claude compatible."""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from provider_execution import (
    collect_modified_files,
    normalize_active_operation,
    normalize_approval_record,
    normalize_provider_result,
    provider_http_status,
)


def test_normalized_result_preserves_codex_project_fields():
    result = normalize_provider_result(
        "codex",
        {"id": "codex-local", "name": "Codex", "profile": "local"},
        {
            "ok": True,
            "reply": "done",
            "status": "completed",
            "threadId": "thr-1",
            "turnId": "turn-1",
            "modifiedFiles": ["a.txt"],
            "tools": [{"id": "tool"}],
            "tokenUsage": {"input_tokens": 10},
        },
        conversation_id="conv-1",
        modified_files=collect_modified_files(["a.txt"], {"old.txt"}, {"old.txt", "b.txt"}),
    )
    assert result["ok"] is True
    assert result["providerKind"] == "codex"
    assert result["conversationId"] == "conv-1"
    assert result["threadId"] == "thr-1"
    assert result["turnId"] == "turn-1"
    assert result["modifiedFiles"] == ["a.txt", "b.txt"]
    assert result["tools"][0]["id"] == "tool"
    assert provider_http_status(result) == 200


def test_status_http_mapping_and_human_intervention():
    result = normalize_provider_result(
        "codex",
        {"id": "codex-local"},
        {"ok": False, "status": "needs_human_intervention", "error": "approval"},
    )
    assert result["needsHumanIntervention"] is True
    assert provider_http_status(result) == 409

    timeout = normalize_provider_result("claude-code", {"id": "claude"}, {"ok": False, "status": "timeout"})
    assert provider_http_status(timeout) == 408


def test_approval_and_active_operation_contracts_are_provider_scoped():
    approval = normalize_approval_record("codex", "codex-local", "conv-1", {
        "operationId": "op-1",
        "interactionId": "int-1",
        "method": "item/commandExecution/requestApproval",
        "status": "pending",
    })
    assert approval["providerKind"] == "codex"
    assert approval["agentId"] == "codex-local"
    assert approval["interactionId"] == "int-1"
    assert approval["approvalId"] == "int-1"
    assert approval["raw"]["operationId"] == "op-1"

    active = normalize_active_operation(
        "claude-code",
        "claude-code-local",
        "conv-2",
        session_id="sess-1",
        run_id="run-1",
        pending=approval,
    )
    assert active["providerKind"] == "claude-code"
    assert active["agentId"] == "claude-code-local"
    assert active["conversationId"] == "conv-2"
    assert active["pending"]["providerKind"] == "codex"


if __name__ == "__main__":
    test_normalized_result_preserves_codex_project_fields()
    test_status_http_mapping_and_human_intervention()
    test_approval_and_active_operation_contracts_are_provider_scoped()
    print("test_provider_execution_contract.py passed")
