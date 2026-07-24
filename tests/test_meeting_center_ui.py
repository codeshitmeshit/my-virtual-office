from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
SCRIPT = (ROOT / "app" / "meeting-center.js").read_text(encoding="utf-8")
STYLE = (ROOT / "app" / "meeting-center.css").read_text(encoding="utf-8")


def test_meeting_center_uses_focused_assets_and_three_pane_workspace():
    assert 'href="meeting-center.css?' in INDEX
    assert 'src="meeting-center.js?' in INDEX
    assert 'id="meeting-center-list"' in INDEX
    assert 'id="meeting-center-main"' in INDEX
    assert 'id="meeting-center-controls"' in INDEX
    assert "grid-template-columns: 300px minmax(420px, 620px) minmax(260px, 340px)" in STYLE
    assert 'class="meeting-center-mark"' not in INDEX


def test_ai_turns_show_position_and_fold_supporting_fields():
    assert "structured.position" in SCRIPT
    assert "<details class=\"meeting-center-turn-details\"" in SCRIPT
    for field in ("reasoning", "disagreements", "questions", "suggestedNextStep", "confidence"):
        assert f"['{field}'" in SCRIPT


def test_participants_are_reduced_to_avatar_and_name():
    participant_override = SCRIPT.split("function renderParticipantRow", 1)[1].split(
        "function renderStructuredTurn", 1
    )[0]
    assert "mtg-participant-emoji" in participant_override
    assert "mtg-participant-name" in participant_override
    assert "mtg-participant-role" not in participant_override
    assert "mtg-participant-actions" not in participant_override


def test_legacy_controller_explicitly_delegates_to_meeting_center():
    game = (ROOT / "app" / "game.js").read_text(encoding="utf-8")
    assert "window.MeetingCenterUI.render({" in game
    assert "window.MeetingCenterUI.renderParticipantRow" in game
    assert "window.MeetingCenterUI.renderStructuredTurn" in game
    assert "window._mtgRender = render" not in SCRIPT


def test_history_record_splits_transcript_from_aside_detail():
    assert "meeting-center-record-header" in SCRIPT
    assert "record.topic" in SCRIPT
    assert "runtime.renderMeetingTranscript(record)" in SCRIPT
    assert "runtime.renderMeetingDetail(record, { includeTranscript: false })" in SCRIPT
    assert "openMeetingDetailModal(" not in SCRIPT
    assert "openMeetingRequestDetailModal(" in SCRIPT


def test_left_column_record_titles_are_bold():
    title_rule = STYLE.split(".meeting-center-item-title {", 1)[1].split("}", 1)[0]
    assert "font-weight: 700;" in title_rule
