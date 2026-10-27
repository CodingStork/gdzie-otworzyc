"""Tabela `meta`: skąd i kiedy pochodzą dane (pokazywane w stopce aplikacji)."""
import datetime

import duckdb


def record_meta(con: duckdb.DuckDBPyConnection, source: str, url: str, rows: int,
                when: datetime.datetime | None = None) -> None:
    """Zapisuje (lub nadpisuje) wiersz o źródle `source` w tabeli meta."""
    con.execute("""CREATE TABLE IF NOT EXISTS meta (
        source VARCHAR PRIMARY KEY, url VARCHAR, downloaded_at TIMESTAMP, rows BIGINT)""")
    con.execute("INSERT OR REPLACE INTO meta VALUES (?, ?, ?, ?)", [source, url, when or datetime.datetime.now(), rows])
