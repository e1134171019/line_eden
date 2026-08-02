# -*- coding: utf-8 -*-

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3


@contextmanager
def open_database(db_path: Path) -> Iterator[sqlite3.Connection]:
    """保留 transaction context 語意，並保證離開區塊後關閉連線。"""

    connection = sqlite3.connect(db_path)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
