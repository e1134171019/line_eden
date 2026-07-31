# -*- coding: utf-8 -*-

import config


def test_gemini_retry_defaults_are_positive() -> None:
    assert config.GEMINI_MAX_ATTEMPTS >= 1
    assert config.GEMINI_RETRY_BASE_SECONDS >= 1
