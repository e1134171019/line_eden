# -*- coding: utf-8 -*-

from pathlib import Path
import sqlite3

import pytest

from src.repositories.sqlite_connection import open_database


def test_open_database_commits_and_closes_connection(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with open_database(db_path) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
        connection.execute("INSERT INTO values_table VALUES ('saved')")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with open_database(db_path) as reader:
        row = reader.execute("SELECT value FROM values_table").fetchone()
    assert row == ("saved",)


def test_open_database_rolls_back_and_closes_after_error(tmp_path: Path) -> None:
    db_path = tmp_path / "state.db"
    with open_database(db_path) as connection:
        connection.execute("CREATE TABLE values_table (value TEXT NOT NULL)")
    with pytest.raises(RuntimeError):
        with open_database(db_path) as connection:
            connection.execute("INSERT INTO values_table VALUES ('discarded')")
            raise RuntimeError("rollback")
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute("SELECT 1")
    with open_database(db_path) as reader:
        row = reader.execute("SELECT COUNT(1) FROM values_table").fetchone()
    assert row == (0,)
