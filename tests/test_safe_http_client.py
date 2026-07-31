# -*- coding: utf-8 -*-

import ssl

from src.collectors.http_client import (
    SafeHttpClient,
    build_legacy_compatible_ssl_context,
)


# 相容 context 只能移除 X509 strict，不得關閉 CA 或 hostname 驗證。
def test_legacy_ssl_context_keeps_identity_verification() -> None:
    context = build_legacy_compatible_ssl_context()

    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert not context.verify_flags & ssl.VERIFY_X509_STRICT


# 只有允許網域的 Subject Key Identifier 錯誤可以安全重試。
def test_legacy_retry_is_restricted_to_known_certificate_error() -> None:
    client = SafeHttpClient(10.0, "test")
    error = RuntimeError(
        "[SSL: CERTIFICATE_VERIFY_FAILED] certificate verify failed: "
        "Missing Subject Key Identifier"
    )
    try:
        assert client._can_use_legacy_context("https://www.edu.tw/page", error)
        assert not client._can_use_legacy_context("https://example.com/page", error)
        assert not client._can_use_legacy_context(
            "https://www.edu.tw/page",
            RuntimeError("certificate expired"),
        )
    finally:
        client.close()
