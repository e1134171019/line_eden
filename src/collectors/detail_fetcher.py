# -*- coding: utf-8 -*-

from typing import Protocol

from src.models.scholarship import Scholarship


class DetailFetcher(Protocol):
    """服務層依賴的公告正文擷取介面。"""

    def fetch_text(self, scholarship: Scholarship) -> str:
        """回傳指定公告可供判斷的正文。"""
        ...
