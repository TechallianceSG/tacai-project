"""TACAI Pay JP — Audit logging helpers."""

import json
from datetime import datetime, timezone
from typing import Any

from database import execute


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def log_audit(
    table_name: str,
    record_id: str | None,
    action: str,
    user_name: str = "system",
    before: Any = None,
    after: Any = None,
) -> None:
    """Insert an audit log entry into pay_jp_audit_logs."""
    sql = """
        INSERT INTO pay_jp_audit_logs
            (module, record_id, action, user_name, table_name, before_value, after_value, created_at)
        VALUES
            (%s, %s, %s, %s, %s, %s, %s, %s)
    """
    params = (
        "pay_jp",
        record_id or "",
        action,
        user_name,
        table_name,
        json.dumps(before, ensure_ascii=False) if before is not None else None,
        json.dumps(after, ensure_ascii=False) if after is not None else None,
        now_iso(),
    )
    execute(sql, params)
