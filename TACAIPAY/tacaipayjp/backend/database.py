"""TACAI Pay JP — Database connection and query helpers (psycopg2)."""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import psycopg2
import psycopg2.extras

from config import DB_HOST, DB_NAME, DB_PASS, DB_PORT, DB_USER

_CONN = None


def _get_conn():
    """Return a psycopg2 connection, creating one if needed."""
    global _CONN
    if _CONN is None or _CONN.closed:
        _CONN = psycopg2.connect(
            host=DB_HOST,
            port=DB_PORT,
            dbname=DB_NAME,
            user=DB_USER,
            password=DB_PASS,
        )
        _CONN.autocommit = False
        print(f"[tacaipayjp] PostgreSQL connected → {DB_HOST}:{DB_PORT}/{DB_NAME}", flush=True)
    return _CONN


def _is_available() -> bool:
    """Check if PostgreSQL is reachable."""
    try:
        conn = _get_conn()
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
        return True
    except Exception:
        return False


class _JSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (datetime, date)):
            return obj.isoformat()
        if isinstance(obj, Decimal):
            return float(obj)
        return super().default(obj)


def _serialize_row(row: dict) -> dict:
    """Convert Python objects to PG-compatible values."""
    out = {}
    for k, v in row.items():
        if isinstance(v, (dict, list)):
            out[k] = json.dumps(v, cls=_JSONEncoder, ensure_ascii=False)
        elif isinstance(v, datetime):
            out[k] = v.isoformat()
        elif isinstance(v, date):
            out[k] = v.isoformat()
        elif isinstance(v, Decimal):
            out[k] = float(v)
        else:
            out[k] = v
    return out


def fetch_all(sql: str, params: tuple | None = None) -> list[dict[str, Any]]:
    """Execute SELECT query and return all rows as list of dicts."""
    conn = _get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
        return [dict(r) for r in rows]


def fetch_one(sql: str, params: tuple | None = None) -> dict[str, Any] | None:
    """Execute SELECT query and return first row as dict or None."""
    conn = _get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None


def execute(sql: str, params: tuple | None = None) -> int:
    """Execute INSERT/UPDATE/DELETE. Returns rowcount."""
    conn = _get_conn()
    with conn.cursor() as cur:
        cur.execute(sql, params)
        conn.commit()
        return cur.rowcount


def execute_returning(sql: str, params: tuple | None = None) -> dict[str, Any] | None:
    """Execute INSERT/UPDATE with RETURNING clause, return the row."""
    conn = _get_conn()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        conn.commit()
        return dict(row) if row else None


def execute_many(sql: str, params_list: list[tuple]) -> int:
    """Execute the same SQL with many parameter sets. Returns total rowcount."""
    conn = _get_conn()
    total = 0
    with conn.cursor() as cur:
        for params in params_list:
            cur.execute(sql, params)
            total += cur.rowcount
    conn.commit()
    return total


def safe_str(val: Any) -> str:
    """Quote a string value for SQL (fallback escaping)."""
    if val is None:
        return "NULL"
    s = str(val).replace("'", "''")
    return f"'{s}'"
