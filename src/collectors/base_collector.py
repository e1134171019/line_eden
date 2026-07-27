# -*- coding: utf-8 -*-

from abc import ABC, abstractmethod

from src.models.scholarship import Scholarship


class BaseCollector(ABC):
    """公告蒐集器抽象基底。"""

    # 定義統一的公告蒐集介面。
    @abstractmethod
    def collect(self) -> list[Scholarship]:
        raise NotImplementedError
