# -*- coding: utf-8 -*-

import ssl

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
