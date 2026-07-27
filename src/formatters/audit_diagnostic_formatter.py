# -*- coding: utf-8 -*-

from src.diagnostics.detail_fetch_diagnostics import DetailFetchResult, ResourceDiagnostic


# 將來源與附件擷取診斷整理為終端機文字行。
def build_fetch_diagnostic_lines(result: DetailFetchResult) -> list[str]:
    lines = [f"  來源診斷：{_resource_summary(result.source)}"]
    lines.extend(_redirect_lines(result.source, "來源"))
    if result.source.error:
        lines.append(f"  來源錯誤：{result.source.error}")
    lines.append(_attachment_summary(result))
    for index, item in enumerate(result.attachments, start=1):
        lines.extend(_attachment_lines(index, item))
    return lines


# 建立附件發現、成功與失敗統計。
def _attachment_summary(result: DetailFetchResult) -> str:
    success = result.successful_attachment_count()
    failed = result.failed_attachment_count()
    return f"  附件診斷：發現 {result.discovered_attachment_count}，成功 {success}，失敗 {failed}"


# 建立單一附件的摘要、網址與錯誤行。
def _attachment_lines(index: int, item: ResourceDiagnostic) -> list[str]:
    lines = [f"    [{index}] {_resource_summary(item)}", f"        請求：{item.requested_url}"]
    lines.extend(_redirect_lines(item, "        最終"))
    if item.error:
        lines.append(f"        錯誤：{item.error}")
    return lines


# 建立資源狀態、格式、大小與擷取文字長度摘要。
def _resource_summary(item: ResourceDiagnostic) -> str:
    content_type = item.content_type or "unknown"
    size = _format_bytes(item.size_bytes)
    return (
        f"{item.status} | {item.document_kind} | {content_type} | "
        f"{size} | 文字 {item.text_length} 字"
    )


# 只在發生重新導向時輸出最終網址。
def _redirect_lines(item: ResourceDiagnostic, label: str) -> list[str]:
    if not item.final_url or item.final_url == item.requested_url:
        return []
    return [f"{label}：{item.final_url}"]


# 將位元組數量轉為易讀單位。
def _format_bytes(size_bytes: int) -> str:
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KiB"
    return f"{size_bytes / 1024 / 1024:.1f} MiB"
