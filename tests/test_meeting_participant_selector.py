from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GAME_JS = (ROOT / "app" / "game.js").read_text(encoding="utf-8")


def test_unassigned_agents_are_rendered_as_meeting_participants():
    selector_start = GAME_JS.index("function _mtgParticipantSelectorHtml")
    selector_end = GAME_JS.index("function _mtgSelectedParticipantValues", selector_start)
    selector_source = GAME_JS[selector_start:selector_end]

    assert "var participantBranches = getBranchList().slice();" in selector_source
    assert "(byBranch.UNASSIGNED || []).length" in selector_source
    assert "participantBranches.push({ id: 'UNASSIGNED'" in selector_source
    assert selector_source.count("participantBranches.map(function(branch)") == 2
