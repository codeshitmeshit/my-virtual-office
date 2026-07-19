"""Canonical VO Agent-directory skill and endpoint contract checks."""

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL_DIR = ROOT / "skills" / "vo-agent-directory"
SKILL_PATH = SKILL_DIR / "SKILL.md"
OPENAI_YAML_PATH = SKILL_DIR / "agents" / "openai.yaml"


def skill_text():
    return SKILL_PATH.read_text(encoding="utf-8")


def test_skill_has_valid_minimal_frontmatter_and_canonical_name():
    text = skill_text()
    match = re.match(r"\A---\n(.*?)\n---\n", text, re.DOTALL)
    assert match is not None
    lines = [line for line in match.group(1).splitlines() if line.strip()]
    assert [line.split(":", 1)[0] for line in lines] == ["name", "description"]
    assert lines[0] == "name: vo-agent-directory"
    assert "TODO" not in text
    assert len(text.splitlines()) < 500


def test_skill_documents_only_the_three_agent_hr_endpoints():
    text = skill_text()
    assert "GET /api/agent-human-resources/directory" in text
    assert "GET /api/agent-human-resources/agents/{ai_id}" in text
    assert "GET /api/agent-human-resources/access-log/self" in text
    allowed = {
        "/api/agent-human-resources/directory",
        "/api/agent-human-resources/agents/{ai_id}",
        "/api/agent-human-resources/access-log/self",
    }
    found = set(re.findall(r"/api/agent-human-resources/[A-Za-z0-9_{}?=/.-]+", text))
    assert found == allowed


def test_skill_requires_identity_bound_grant_headers_without_embedding_a_grant():
    text = skill_text()
    assert "Authorization: Bearer <workspace-provisioned-grant>" in text
    assert "X-VO-Agent-Action: human-resources" in text
    assert "X-VO-Agent-Id: <caller-ai-id>" in text
    assert "不要发送浏览器 `Origin`" in text
    assert "grant_live_" not in text
    assert not re.search(r"Bearer [A-Za-z0-9_-]{24,}", text)


def test_skill_directory_contract_is_exactly_the_safe_projection():
    text = skill_text()
    safe_fields = {"name", "introduction", "ai_id", "availability", "readiness"}
    for field in safe_fields:
        assert f"`{field}`" in text
    for forbidden in (
        "raw_response",
        "normalized_json",
        "secret_digest",
        "principal_contributions_json",
        "assessment_evidence",
    ):
        assert f"`{forbidden}`" not in text


def test_skill_explicitly_prohibits_storage_management_and_sensitive_access():
    text = skill_text()
    assert "不得读取 `human-resources/hr.sqlite3`" in text
    assert "不得调用 `/api/human-resources/*`" in text
    assert "不得请求原始日报、完整评估、详细证据、敏感改进反馈" in text
    assert "不得伪造 `X-VO-Agent-Id`" in text
    assert "不得把调用方 ID 当作认证凭据" in text
    assert "不得在响应、命令输出、错误报告或通信消息中暴露 bearer grant" in text


def test_skill_explains_success_audit_and_self_log_scope():
    text = skill_text()
    assert "一次成功的跨 Agent 查看会记录一条访问日志" in text
    assert "只返回当前 Agent 是被查看目标的记录" in text
    assert "不要请求或推断无关 Agent 的访问历史" in text


def test_openai_metadata_matches_skill_and_mentions_explicit_invocation():
    text = OPENAI_YAML_PATH.read_text(encoding="utf-8")
    assert 'display_name: "VO Agent Directory"' in text
    assert 'short_description: "Query safe VO Agent directory and public work views"' in text
    assert "$vo-agent-directory" in text
    assert "TODO" not in text


def test_skill_folder_contains_only_runtime_skill_artifacts():
    files = {
        path.relative_to(SKILL_DIR).as_posix()
        for path in SKILL_DIR.rglob("*")
        if path.is_file()
    }
    assert files == {"SKILL.md", "agents/openai.yaml"}
