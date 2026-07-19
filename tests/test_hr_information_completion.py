"""Manual completion of missing Agent introductions."""

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from services.hr_information_completion import (
    CallableHRInformationConversation,
    HRInformationCompletionCommands,
    HRInformationCompletionService,
)
from services.hr_repository import HRRepository
from services.hr_command_status import HRCommandStatusTracker


def summary(raw, introduction):
    return json.dumps(
        {
            "schemaVersion": 1,
            "introduction": introduction,
            "supportingEvidence": [raw],
            "materialConflict": False,
            "clarificationQuestion": "",
        },
        ensure_ascii=False,
    )


def repository(tmp_path):
    result = HRRepository(tmp_path / "status")
    result.initialize()
    for ai_id, availability in (
        ("hr", "available"),
        ("missing", "available"),
        ("waiting-summary", "busy"),
        ("complete", "available"),
        ("offline", "offline"),
    ):
        result.upsert_agent(
            ai_id=ai_id,
            name=ai_id,
            agent_kind="system" if ai_id == "hr" else "project",
            provider_kind="openclaw",
            status="active",
            availability=availability,
            source="test",
        )
    result.save_introduction(
        ai_id="waiting-summary",
        state="response_received",
        raw_response="I review release quality.",
        introduction="",
        source="agent-response",
        actor_id="hr",
        expected_version=0,
    )
    result.save_introduction(
        ai_id="complete",
        state="published",
        raw_response="I maintain APIs.",
        introduction="Maintains APIs.",
        source="hr-structured-summary",
        actor_id="hr",
        expected_version=0,
    )
    return result


def test_completion_only_contacts_available_agents_with_missing_introductions(tmp_path):
    repo = repository(tmp_path)
    agent_calls = []
    hr_calls = []

    def ask_agent(ai_id, message, conversation_key, timeout):
        agent_calls.append((ai_id, message, conversation_key, timeout))
        return "I coordinate infrastructure incidents."

    def ask_hr(prompt, conversation_key, timeout):
        hr_calls.append((prompt, conversation_key, timeout))
        if "review release quality" in prompt.lower():
            return summary("I review release quality.", "Reviews release quality.")
        return summary(
            "I coordinate infrastructure incidents.",
            "Coordinates infrastructure incidents.",
        )

    service = HRInformationCompletionService(
        repo,
        CallableHRInformationConversation(ask_agent, ask_hr),
        max_workers=2,
        new_id=iter([f"id-{index}" for index in range(20)]).__next__,
    )
    result = service.complete_missing()

    assert result.available == 3
    assert result.missing == 2
    assert result.published == 2
    assert result.failed == 0
    assert [call[0] for call in agent_calls] == ["missing"]
    assert '"requestType":"vo.hr.agent_introduction"' in agent_calls[0][1]
    assert '"agentAiId":"missing"' in agent_calls[0][1]
    assert '"responsibilities":["<responsibility>"]' in agent_calls[0][1]
    assert "自然语言回答" in agent_calls[0][1]
    assert "```" not in agent_calls[0][1]
    assert len(hr_calls) == 2
    assert repo.get_current_introduction("missing").introduction == "Coordinates infrastructure incidents."
    assert repo.get_current_introduction("waiting-summary").introduction == "Reviews release quality."
    assert repo.get_current_introduction("complete").version == 1
    assert repo.get_current_introduction("offline") is None


def test_no_response_stays_missing_without_inventing_an_introduction(tmp_path):
    repo = repository(tmp_path)
    conversation = CallableHRInformationConversation(
        lambda *_args: None,
        lambda prompt, *_args: (
            summary("I review release quality.", "Reviews release quality.")
            if "review release quality" in prompt.lower()
            else (_ for _ in ()).throw(AssertionError("HR must not summarize no response"))
        ),
    )
    service = HRInformationCompletionService(repo, conversation, max_workers=1)
    result = service.complete_missing()

    assert result.no_response == 1
    assert result.published == 1
    pending = repo.get_current_introduction("missing")
    assert pending.state == "introduction_pending"
    assert pending.introduction == ""


def test_command_is_async_single_flight_and_records_bounded_activity(tmp_path):
    repo = repository(tmp_path)
    service = HRInformationCompletionService(
        repo,
        CallableHRInformationConversation(
            lambda _ai_id, *_args: "I coordinate infrastructure incidents.",
            lambda prompt, *_args: (
                summary("I review release quality.", "Reviews release quality.")
                if "review release quality" in prompt.lower()
                else summary(
                    "I coordinate infrastructure incidents.",
                    "Coordinates infrastructure incidents.",
                )
            ),
        ),
        max_workers=1,
        new_id=iter([f"service-{index}" for index in range(30)]).__next__,
    )
    queued = []
    commands = HRInformationCompletionCommands(
        service,
        tracker=HRCommandStatusTracker(repo),
        submit=lambda callback: queued.append(callback) or True,
        new_id=iter(("command-1", "command-2", "command-3")).__next__,
    )

    first = commands.complete()
    duplicate = commands.complete()
    assert first.accepted is True
    assert duplicate.accepted is False
    assert len(queued) == 1
    assert repo.list_active_hr_commands()[0].status == "accepted"

    queued.pop()()
    assert repo.list_active_hr_commands() == ()
    assert commands.complete().accepted is True
    activity = next(
        item for item in repo.list_hr_activity().items if item.id == "command-1"
    )
    assert activity.action == "complete_information"
    assert activity.status == "complete"
    assert activity.context["published"] == 2


def test_completion_module_has_no_transport_or_legacy_entrypoint_dependency():
    source = (APP_DIR / "services" / "hr_information_completion.py").read_text(
        encoding="utf-8"
    )
    assert "import server" not in source
    assert "OfficeHandler" not in source
    assert "http.server" not in source
