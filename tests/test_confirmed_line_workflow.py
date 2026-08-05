# -*- coding: utf-8 -*-

from pathlib import Path

WORKFLOW_PATH = (
    Path(__file__).parents[1] / ".github/workflows/confirmed-line-send.yml"
)
SENDER_PATH = (
    Path(__file__).parents[1] / "src/automation/send_confirmed_line_links.py"
)


def test_confirmed_line_workflow_is_fast_and_state_free() -> None:
    content = WORKFLOW_PATH.read_text(encoding="utf-8")

    assert '".github/confirmed-line-trigger"' in content
    assert "python -m src.automation.send_confirmed_line_links" in content
    assert "LINE_CHANNEL_ACCESS_TOKEN" in content
    assert "LINE_USER_ID" in content
    assert "GEMINI_API_KEY" not in content
    assert "STUDENT_PROFILE_B64" not in content
    assert "STATE_PASSPHRASE" not in content
    assert "timeout-minutes: 10" in content


def test_confirmed_line_sender_uses_fixed_message_builder() -> None:
    content = SENDER_PATH.read_text(encoding="utf-8")

    assert "USER_CONFIRMED_ELIGIBLE_LINKS" in content
    assert "build_line_message" in content
    assert "Asia/Taipei" in content
    assert "send_text_message" in content
