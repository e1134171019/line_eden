# -*- coding: utf-8 -*-

import importlib

import pytest

import config


def test_notify_review_items_reads_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTIFY_REVIEW_ITEMS", "true")
    reloaded = importlib.reload(config)
    assert reloaded.NOTIFY_REVIEW_ITEMS is True

    monkeypatch.setenv("NOTIFY_REVIEW_ITEMS", "false")
    reloaded = importlib.reload(config)
    assert reloaded.NOTIFY_REVIEW_ITEMS is False
