# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
from src.services.gemini_fallback_service import GeminiAnalysisDiagnostic
from src.services.scholarship_service import AuditRecord, AuditResult
import main


# 驗證終端 audit 會顯示來源、附件統計與錯誤原因。
def test_print_audit_includes_fetch_diagnostics(capsys: object) -> None:
    item = Scholarship.from_raw(
        "lhu", "測試獎學金", "2026-07-27", "https://example.com/news",
    )
    evaluated = Scholarship(
        **{**item.__dict__, "notice_kind": "application", "eligibility_status": "review",
           "eligibility_reason": "公告未提供足夠條件，暫不推播。"},
    )
    source = ResourceDiagnostic(
        "source", item.source_url, item.source_url, "text/html",
        1000, "html", "success", 200, "",
    )
    attachment = ResourceDiagnostic(
        "attachment", "https://example.com/rules.pdf", "", "",
        0, "unknown", "error", 0, "HTTPStatusError: 403 Forbidden", "rules",
    )
    fetch_result = DetailFetchResult("正文", source, (attachment,), 1)
    record = AuditRecord(evaluated, "正文", fetch_result)
    result = AuditResult([record], 0, 1, 0, "完成")

    main.print_audit(result)

    output = capsys.readouterr().out
    assert "附件診斷：發現 1，嘗試 1，成功 0，失敗 1" in output
    assert "角色 rules" in output
    assert "403 Forbidden" in output
    assert "https://example.com/rules.pdf" in output


# 驗證 Gemini audit 會顯示結構化欄位與實際頁碼證據。
def test_print_audit_includes_gemini_fields_and_evidence(capsys: object) -> None:
    item = Scholarship.from_raw(
        "lhu", "能源獎學金", "2026-07-27", "https://example.com/news",
    )
    evaluated = Scholarship(
        **{**item.__dict__, "notice_kind": "application", "eligibility_status": "eligible",
           "eligibility_reason": "公告領域相符。"},
    )
    source = ResourceDiagnostic(
        "source", item.source_url, item.source_url, "text/html",
        1000, "html", "success", 200, "",
    )
    fetch_result = DetailFetchResult("正文", source, tuple(), 0)
    diagnostic = GeminiAnalysisDiagnostic(
        "success", "https://example.com/rules.pdf", "gemini-test",
        False, 2, 100, 20, 120, "已抽取完整資格條件。",
        ("學位層級=大學部", "最低學業=80"),
        ("第1頁：大學部學生學業平均八十分以上",),
    )
    record = AuditRecord(evaluated, "正文", fetch_result, diagnostic)
    result = AuditResult([record], 1, 0, 0, "完成", 1, 0, 100, 20)

    main.print_audit(result)

    output = capsys.readouterr().out
    assert "Gemini欄位：學位層級=大學部" in output
    assert "Gemini欄位：最低學業=80" in output
    assert "Gemini證據：第1頁：大學部學生學業平均八十分以上" in output
