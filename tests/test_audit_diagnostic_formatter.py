# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.formatters.audit_diagnostic_formatter import build_fetch_diagnostic_lines


# 驗證 audit 會顯示附件統計、重新導向與解析錯誤。
def test_build_fetch_diagnostic_lines() -> None:
    source = ResourceDiagnostic(
        "source", "https://reurl.cc/a", "https://example.com/news",
        "text/html", 2048, "html", "success", 500, "",
    )
    success = ResourceDiagnostic(
        "attachment", "https://example.com/a.pdf", "https://cdn.example.com/a.pdf",
        "application/pdf", 4096, "pdf", "success", 1200, "",
    )
    failed = ResourceDiagnostic(
        "attachment", "https://example.com/b.doc", "", "",
        0, "unknown", "error", 0, "ValueError: 不支援的附件格式",
    )
    result = DetailFetchResult("正文", source, (success, failed), 4)

    lines = build_fetch_diagnostic_lines(result)
    output = "\n".join(lines)

    assert "附件診斷：發現 4，嘗試 2，成功 1，失敗 1" in output
    assert "https://cdn.example.com/a.pdf" in output
    assert "application/pdf" in output
    assert "4.0 KiB" in output
    assert "不支援的附件格式" in output


# 驗證來源失敗時會顯示實際例外內容。
def test_build_source_error_lines() -> None:
    source = ResourceDiagnostic(
        "source", "https://reurl.cc/missing", "", "", 0,
        "unknown", "error", 0, "HTTPStatusError: 404 Not Found",
    )
    result = DetailFetchResult("", source, tuple(), 0)

    output = "\n".join(build_fetch_diagnostic_lines(result))

    assert "來源診斷：error" in output
    assert "來源錯誤：HTTPStatusError: 404 Not Found" in output
    assert "附件診斷：發現 0，嘗試 0，成功 0，失敗 0" in output
