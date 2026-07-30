from __future__ import annotations

import json

import pytest

from services.archive_manager_work_coordinator import (
    ArchiveManagerWorkCoordinator,
)
from services.mcp_usage_guide_organization import (
    McpGuideOrganizationError,
    McpUsageGuideOrganizationService,
    build_guide_prompt,
    collect_reference_documents,
    parse_guide_reply,
)


def _server(**overrides):
    return {
        "name": "market-data",
        "description": "Read market data",
        "transport": "stdio",
        "command": "/opt/market/server",
        "args": [],
        "include": ["quotes"],
        "env": {"MARKET_TOKEN": "never-leak-this"},
        **overrides,
    }


def test_prompt_includes_tool_material_but_never_environment_values():
    prompt = build_guide_prompt(
        _server(
            args=["--api-key", "argument-secret", "--mode=research"],
            url="https://user:pass@example.com/mcp?token=url-secret",
        ),
        [{"name": "quotes", "description": "Get quotes", "inputSchema": {}}],
        [{"name": "README.md", "content": "Research only."}],
    )

    assert "quotes" in prompt
    assert "Research only." in prompt
    assert "MARKET_TOKEN" in prompt
    assert "never-leak-this" not in prompt
    assert "argument-secret" not in prompt
    assert "url-secret" not in prompt
    assert "user:pass" not in prompt
    assert "https://example.com/mcp" in prompt
    assert "不可信资料" in prompt


def test_reference_documents_are_bounded_and_match_mcp_name(tmp_path):
    skill_dir = tmp_path / "mcp-market-data"
    skill_dir.mkdir()
    (skill_dir / "SKILL.md").write_text("# Market MCP\nResearch only.", encoding="utf-8")
    unrelated = tmp_path / "other"
    unrelated.mkdir()
    (unrelated / "README.md").write_text("must not be read", encoding="utf-8")

    documents = collect_reference_documents(_server(), [tmp_path])

    assert documents == [
        {"name": "SKILL.md", "content": "# Market MCP\nResearch only."}
    ]


def test_parse_guide_reply_requires_one_non_empty_guide():
    assert parse_guide_reply('{"guide":"  ## 使用方式\\n只读查询  "}') == (
        "## 使用方式\n只读查询"
    )
    with pytest.raises(McpGuideOrganizationError) as exc:
        parse_guide_reply('{"guide":"","extra":true}')
    assert exc.value.code == "archive_manager_invalid_response"


def test_service_uses_shared_manager_and_returns_unsaved_draft(tmp_path):
    events = []
    coordinator = ArchiveManagerWorkCoordinator(
        token_factory=lambda: "lease-1", coordinator_id="guide-test"
    )

    def call_manager(agent_id, prompt, timeout):
        events.append(("call", agent_id, timeout, prompt))
        return json.dumps({"guide": "## 适用场景\n用于只读行情研究。"}, ensure_ascii=False)

    service = McpUsageGuideOrganizationService(
        coordinator=coordinator,
        manager_state=lambda: {"status": "idle", "agentId": "archive-manager"},
        call_archive_manager=call_manager,
        inspect_tools=lambda _server: [
            {"name": "quotes", "description": "Get quotes", "inputSchema": {}}
        ],
        documentation_roots=[tmp_path],
        mark_manager_working=lambda label: events.append(("working", label)),
        finalize_manager=lambda error: events.append(("finalize", error)),
        record_result=lambda name, success, error: events.append(
            ("record", name, success, error)
        ),
    )

    result = service.organize(_server())

    assert result["guide"].startswith("## 适用场景")
    assert result["source"] == {
        "toolCount": 1,
        "documentCount": 0,
        "toolIntrospectionAvailable": True,
    }
    assert events[0][0] == "working"
    assert events[1][0:3] == ("call", "archive-manager", 180)
    assert events[-2] == ("record", "market-data", True, "")
    assert events[-1] == ("finalize", None)
    assert coordinator.holder() is None


def test_service_reports_missing_or_busy_archive_manager():
    coordinator = ArchiveManagerWorkCoordinator(
        token_factory=lambda: "lease-1", coordinator_id="guide-test"
    )
    unavailable = McpUsageGuideOrganizationService(
        coordinator=coordinator,
        manager_state=lambda: {"status": "missing"},
        call_archive_manager=lambda *_args: "",
        inspect_tools=lambda _server: [],
    )
    with pytest.raises(McpGuideOrganizationError) as missing:
        unavailable.organize(_server())
    assert missing.value.code == "archive_manager_unavailable"

    stale_working = McpUsageGuideOrganizationService(
        coordinator=coordinator,
        manager_state=lambda: {
            "status": "working",
            "agentId": "archive-manager",
        },
        call_archive_manager=lambda *_args: "",
        inspect_tools=lambda _server: [],
    )
    with pytest.raises(McpGuideOrganizationError) as working:
        stale_working.organize(_server())
    assert working.value.code == "archive_manager_busy"

    held = coordinator.acquire("skill-organization")
    busy = McpUsageGuideOrganizationService(
        coordinator=coordinator,
        manager_state=lambda: {"status": "idle", "agentId": "archive-manager"},
        call_archive_manager=lambda *_args: "",
        inspect_tools=lambda _server: [],
    )
    with pytest.raises(McpGuideOrganizationError) as conflict:
        busy.organize(_server())
    assert conflict.value.code == "archive_manager_busy"
    coordinator.release(held)
