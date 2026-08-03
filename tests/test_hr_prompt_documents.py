import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

from services.hr_prompt_documents import daily_report_request_document  # noqa: E402


def test_daily_report_prompt_directs_agent_to_bridge_conversation_references():
    prompt = daily_report_request_document(
        "请提交今天的日报。",
        ai_id="market-management-team-agent",
        local_date="2026-08-02",
    )

    assert "vo-agent-communication bridge" in prompt
    assert "conversationId" in prompt
    assert "轻量会话引用只是索引" in prompt
