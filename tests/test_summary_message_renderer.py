# -*- coding: utf-8 -*-

from dataclasses import replace

import pytest

from config import SUMMARY_TEMPLATE_NAME
from src.formatters.summary_message_renderer import (
    build_summary_context,
    load_summary_message_renderer,
)
from src.models.scholarship import Scholarship


def test_jinja_summary_template_preserves_existing_message_contract() -> None:
    notice = replace(
        Scholarship.from_raw(
            "lhu",
            "能源工程獎學金",
            "2026-08-01",
            "https://example.com/energy",
        ),
        eligibility_reason="符合電子工程系條件",
    )
    renderer = load_summary_message_renderer(SUMMARY_TEMPLATE_NAME)

    message = renderer.render(build_summary_context([notice], 1, 2))

    assert message == (
        "【適合你的獎學金｜第 1/2 則】\n"
        "1. 2026-08-01\n"
        "能源工程獎學金\n"
        "符合原因：符合電子工程系條件\n"
        "https://example.com/energy"
    )


def test_summary_context_rejects_invalid_batch_index() -> None:
    with pytest.raises(ValueError, match="批次索引"):
        build_summary_context([], 2, 1)
