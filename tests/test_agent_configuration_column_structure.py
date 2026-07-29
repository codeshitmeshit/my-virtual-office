from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (ROOT / "app" / "agent-configuration.js").read_text(encoding="utf-8")


def test_profile_content_stays_inside_primary_column():
    active_status_markup = (
        '\'<span class="ac-active">● \' + esc(isPreview ? stateLabel : '
        "tr('agent_active_short', 'ACTIVE')) + '</span></section>' +"
    )

    assert SCRIPT.count(active_status_markup) == 1

    primary_start = SCRIPT.index(
        '\'<section class="ac-profile-primary">\' +'
    )
    appearance_start = SCRIPT.index(
        '\'<section class="ac-card ac-appearance-card" data-section="appearance">\' +'
    )
    primary_markup = SCRIPT[primary_start:appearance_start]

    assert 'data-section="identity"' in primary_markup
    assert 'data-section="introduction"' in primary_markup
    assert 'data-section="responsibilities"' in primary_markup
    assert primary_markup.rstrip().endswith("'</section>' +")
