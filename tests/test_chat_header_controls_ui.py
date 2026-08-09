from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "app" / "index.html").read_text(encoding="utf-8")
SHELL_CSS = (ROOT / "app" / "ui-main-shell.css").read_text(encoding="utf-8")


def test_chat_header_actions_keep_close_control_in_the_fixed_group():
    chat_header = INDEX[
        INDEX.index('<div class="chat-header">', INDEX.index('id="chat-panel"')) :
        INDEX.index('<div id="chat-model-bar"')
    ]
    assert 'class="chat-header-spacer"' in chat_header
    assert '<span style="flex:1"></span>' not in chat_header
    assert '>🗜</button>' not in chat_header
    assert '>🔄</button>' not in chat_header
    assert '>⇲</button>' in chat_header
    assert '>↻</button>' in chat_header

    for control_id in (
        "chat-compact-context",
        "chat-new-session",
        "chat-move",
        "chat-close",
    ):
        marker = f'id="{control_id}"'
        start = chat_header.index(marker)
        button = chat_header[chat_header.rfind("<button", 0, start) : chat_header.index("</button>", start)]
        assert 'type="button"' in button
        assert "aria-label=" in button

    assert "grid-auto-columns: 32px" in SHELL_CSS
    assert "flex: 0 0 auto" in SHELL_CSS
    assert ".chat-header-main" not in SHELL_CSS
    assert ".chat-header-spacer" in SHELL_CSS
    assert ".chat-header-btns > :is(" in SHELL_CSS
    assert ".chat-compact-context" in SHELL_CSS
    assert ".chat-new-session" in SHELL_CSS
    assert ".chat-move-btn" in SHELL_CSS
    assert ".chat-close" in SHELL_CSS
    assert "border: 1px solid transparent" in SHELL_CSS
    assert "background: transparent" in SHELL_CSS
    assert "border-color: transparent" in SHELL_CSS


def test_chat_header_information_can_shrink_before_actions_are_clipped():
    assert ".chat-header > .chat-agent-select" in SHELL_CSS
    assert "min-width: 0" in SHELL_CSS
    assert ".chat-header > :is(.chat-status, .chat-feishu-live-status)" in SHELL_CSS
    assert "text-overflow: ellipsis" in SHELL_CSS
    assert "overflow: hidden" in SHELL_CSS
