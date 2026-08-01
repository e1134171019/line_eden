# -*- coding: utf-8 -*-

from dataclasses import dataclass
from typing import Protocol

from jinja2 import Environment, PackageLoader, StrictUndefined, Template

from src.models.scholarship import Scholarship

DEFAULT_SUMMARY_TEMPLATE_NAME = "scholarship_summary.txt.j2"


@dataclass(frozen=True)
class SummaryMessageContext:
    """摘要模板可讀取的不可變資料。"""

    notices: tuple[Scholarship, ...]
    batch_index: int
    batch_count: int


class SummaryMessageRenderer(Protocol):
    """服務層使用的摘要訊息渲染介面。"""

    def render(self, context: SummaryMessageContext) -> str:
        """將摘要資料轉成通知文字。"""
        ...


@dataclass(frozen=True)
class JinjaSummaryMessageRenderer:
    """以預先載入的 Jinja2 純文字模板產生摘要。"""

    template: Template

    def render(self, context: SummaryMessageContext) -> str:
        """純函式：使用不可變 context 產生摘要文字。"""
        return self.template.render(context=context).strip()


def load_summary_message_renderer(template_name: str) -> JinjaSummaryMessageRenderer:
    """從 src/templates 載入嚴格模式純文字模板。"""
    environment = Environment(
        loader=PackageLoader("src", "templates"),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=False,
    )
    return JinjaSummaryMessageRenderer(environment.get_template(template_name))


def build_summary_context(
    notices: list[Scholarship],
    batch_index: int,
    batch_count: int,
) -> SummaryMessageContext:
    """純函式：將批次公告轉成模板 context。"""
    if batch_index < 1 or batch_count < 1 or batch_index > batch_count:
        raise ValueError("摘要批次索引不合法")
    return SummaryMessageContext(tuple(notices), batch_index, batch_count)
