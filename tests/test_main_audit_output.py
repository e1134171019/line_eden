# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic
from src.models.scholarship import Scholarship
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
        0, "unknown", "error", 0, "HTTPStatusError: 403 Forbidden",
    )
    fetch_result = DetailFetchResult("正文", source, (attachment,), 1)
    record = AuditRecord(evaluated, "正文", fetch_result)
    result = AuditResult([record], 0, 1, 0, "完成")

    main.print_audit(result)

    output = capsys.readouterr().out
    assert "附件診斷：發現 1，嘗試 1，成功 0，失敗 1" in output
    assert "403 Forbidden" in output
    assert "https://example.com/rules.pdf" in output
