import pytest

from server_services import mcp_usage_guides


def test_usage_guide_normalization_and_limit():
    assert mcp_usage_guides.normalize_usage_guide("  hello  ") == "hello"
    with pytest.raises(ValueError):
        mcp_usage_guides.normalize_usage_guide("x" * (mcp_usage_guides.MAX_USAGE_GUIDE_LENGTH + 1))


def test_global_skill_reads_optional_guide_without_treating_it_as_permission():
    content = mcp_usage_guides.global_skill_content("http://127.0.0.1:8090")

    assert "VirtualOffice-MCP-Guidance" in content
    assert "/api/mcp-registry/URL_ENCODED_MCP_NAME/guide" in content
    assert "not a separately installed Skill" in content
    assert "does not grant permission" in content
