# -*- coding: utf-8 -*-

import ssl

import httpx
import pytest

import src.collectors.http_client as http_client_module
from src.collectors.http_client import (
    DetailSafeHttpClient,
    SafeHttpClient,
    build_legacy_compatible_ssl_context,
)


# 建立測試用 Missing Subject Key Identifier 錯誤。
def _legacy_error() -> RuntimeError:
    return RuntimeError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "Missing Subject Key Identifier"
    )


# 相容 context 只能移除 X509 strict，不得關閉 CA 或 hostname 驗證。
def test_legacy_ssl_context_keeps_identity_verification() -> None:
    context = build_legacy_compatible_ssl_context()

    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT


# 清單 client 只有白名單網域的指定憑證錯誤可以安全重試。
def test_listing_retry_is_restricted_to_known_domain() -> None:
    client = SafeHttpClient(10.0, "test")
    try:
        assert client._can_use_legacy_context("https://www.edu.tw/page", _legacy_error())
        assert client._can_use_legacy_context(
            "https://xinzhuangawards.ntpc.gov.tw/Schs/Frontend/RowView",
            _legacy_error(),
        )
        assert client._can_use_legacy_context(
            "https://www.ctci.org.tw/8838/talent/ctci-scholarship/",
            _legacy_error(),
        )
        assert client._can_use_legacy_context(
            "https://lf.hk.edu.tw/category/scholarship/",
            _legacy_error(),
        )
        assert not client._can_use_legacy_context(
            "https://education.example.gov.tw/page",
            _legacy_error(),
        )
    finally:
        client.close()


# 公告內頁 client 可處理任意 HTTPS 網域的同一種舊憑證格式。
def test_detail_retry_accepts_any_https_domain_for_exact_error() -> None:
    client = DetailSafeHttpClient(10.0, "test")
    try:
        assert client._can_use_legacy_context(
            "https://education.example.gov.tw/page",
            _legacy_error(),
        )
        assert not client._can_use_legacy_context(
            "http://education.example.gov.tw/page",
            _legacy_error(),
        )
        assert not client._can_use_legacy_context(
            "https://education.example.gov.tw/page",
            RuntimeError("certificate expired"),
        )
    finally:
        client.close()


# timeout 前兩次失敗、第三次成功時應回傳內容並記錄重試網域。
def test_get_text_retries_transient_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SafeHttpClient(10.0, "test")
    calls = 0
    sleeps: list[float] = []

    def fake_get(_client: httpx.Client, _url: str) -> str:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise httpx.ReadTimeout("timed out")
        return "ok"

    monkeypatch.setattr(client, "_get", fake_get)
    monkeypatch.setattr(http_client_module.time, "sleep", sleeps.append)
    try:
        assert client.get_text("https://www.lhu.edu.tw/page") == "ok"
        assert calls == 3
        assert sleeps == [0.5, 1.0]
        assert client.timeout_retry_hosts == {"www.lhu.edu.tw"}
    finally:
        client.close()


# 三次 timeout 後仍必須拋出，不得把失敗改成成功或空頁。
def test_get_text_raises_after_timeout_attempts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SafeHttpClient(10.0, "test")
    calls = 0

    def fake_get(_client: httpx.Client, _url: str) -> str:
        nonlocal calls
        calls += 1
        raise httpx.ConnectTimeout("timed out")

    monkeypatch.setattr(client, "_get", fake_get)
    monkeypatch.setattr(http_client_module.time, "sleep", lambda _seconds: None)
    try:
        with pytest.raises(httpx.ConnectTimeout):
            client.get_text("https://www.lhu.edu.tw/page")
        assert calls == 3
    finally:
        client.close()


# 非 timeout transport error 不得進入一般重試，也不得繞過憑證限制。
def test_get_text_does_not_retry_non_timeout_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = SafeHttpClient(10.0, "test")
    calls = 0

    def fake_get(_client: httpx.Client, _url: str) -> str:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("dns failure")

    monkeypatch.setattr(client, "_get", fake_get)
    try:
        with pytest.raises(httpx.ConnectError):
            client.get_text("https://www.lhu.edu.tw/page")
        assert calls == 1
    finally:
        client.close()
