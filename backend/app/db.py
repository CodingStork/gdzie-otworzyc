"""Połączenie z bazą DuckDB (w aplikacji tylko do odczytu).

Jedno globalne połączenie read-only; każde żądanie dostaje własny `cursor()`
(DuckDB pozwala na wiele kursorów z jednego połączenia, także z różnych wątków).
Serwer i ETL nie mogą działać naraz — ETL potrzebuje zapisu do pliku.
"""
import threading

import duckdb

from backend.app import config


class DatabaseMissing(Exception):
    """Plik bazy nie istnieje — trzeba uruchomić ETL."""


_conn: duckdb.DuckDBPyConnection | None = None
_lock = threading.Lock()
_reset_hooks: list = []   # funkcje do wywołania przy zmianie bazy (np. czyszczenie cache wyników)


def cursor() -> duckdb.DuckDBPyConnection:
    global _conn
    with _lock:
        if _conn is None:
            if not config.DB_PATH.exists():
                raise DatabaseMissing(str(config.DB_PATH))
            _conn = duckdb.connect(str(config.DB_PATH), read_only=True)
        return _conn.cursor()


def on_reset(hook) -> None:
    """Rejestruje funkcję wywoływaną przez reset_connection()."""
    _reset_hooks.append(hook)


def reset_connection() -> None:
    """Zamyka połączenie (następne cursor() otworzy je od nowa). Używane w testach."""
    global _conn
    with _lock:
        if _conn is not None:
            _conn.close()
            _conn = None
    for hook in _reset_hooks:
        hook()
