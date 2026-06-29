"""
TACAI Project: Shared PostgreSQL Database Utility
Drop-in replacement for JSON file-based storage.

Usage:
    from db_utils import load_table, save_table, insert_record, update_record, delete_record

    # Reads all rows from PostgreSQL table (replaces load_json_array)
    records = load_table("ts_timesheet_entries")

    # Writes all rows to PostgreSQL table (replaces write_json_array)
    save_table("ts_timesheet_entries", records)

Set TACAI_DB_ENABLED=false to force JSON fallback mode.
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Optional, Union

import psycopg2
import psycopg2.extras

# ── Configuration (from environment) ────────────────────────
DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": int(os.environ.get("DB_PORT", "5432")),
    "dbname": os.environ.get("DB_NAME", "tacai_dev"),
    "user": os.environ.get("DB_USER", "tacai_user"),
    "password": os.environ.get("DB_PASS", "tacai123"),
}

DB_ENABLED = os.environ.get("TACAI_DB_ENABLED", "true").lower() in ("true", "1", "yes")

# ── Connection management ───────────────────────────────────
_conn = None


def _get_conn():
    """Get or create a database connection."""
    global _conn
    if _conn is None or _conn.closed:
        _conn = psycopg2.connect(**DB_CONFIG)
        _conn.autocommit = False
    return _conn


def _is_available():
    """Check if PostgreSQL is available."""
    if not DB_ENABLED:
        return False
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.close()
        return True
    except Exception:
        return False


# ── Core CRUD Operations ────────────────────────────────────

def load_table(table_name: str, where: Optional[str] = None,
               order_by: Optional[str] = None) -> list:
    """Load all rows from a PostgreSQL table. Returns list of dicts."""
    if not _is_available():
        return _json_fallback_load(table_name)

    conn = _get_conn()
    cur = conn.cursor()
    try:
        sql = f'SELECT * FROM "{table_name}"'
        if where:
            sql += f" WHERE {where}"
        if order_by:
            sql += f" ORDER BY {order_by}"
        cur.execute(sql)
        columns = [desc[0] for desc in cur.description]
        rows = []
        for row in cur.fetchall():
            record = {}
            for i, col in enumerate(columns):
                val = row[i]
                # Convert JSONB strings back to Python objects
                if isinstance(val, str) and (val.startswith('{') or val.startswith('[')):
                    try:
                        record[col] = json.loads(val)
                    except (json.JSONDecodeError, ValueError):
                        record[col] = val
                else:
                    record[col] = val
            rows.append(record)
        return rows
    except Exception as e:
        print(f"[db_utils] load_table({table_name}) error: {e}", file=sys.stderr)
        conn.rollback()
        return _json_fallback_load(table_name)
    finally:
        cur.close()


def save_table(table_name: str, records: list[dict[str, Any]],
               pk_column: Optional[str] = None) -> int:
    """Replace all rows in a table with the given records.
    Uses DELETE + INSERT within a transaction for atomicity.
    Returns number of rows inserted.
    """
    if not _is_available():
        return _json_fallback_save(table_name, records)

    conn = _get_conn()
    cur = conn.cursor()
    try:
        # Auto-detect PK if not provided
        if pk_column is None:
            pk_column = _detect_pk(table_name)

        # Delete all existing rows
        cur.execute(f'DELETE FROM "{table_name}"')

        if not records:
            conn.commit()
            return 0

        # Get column info
        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table_name,))
        valid_cols = {row[0] for row in cur.fetchall()}

        count = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            common = {k: _serialize_for_db(v) for k, v in record.items() if k in valid_cols}
            if not common:
                continue
            cols = list(common.keys())
            vals = [common[c] for c in cols]
            ph = ', '.join(['%s'] * len(cols))
            cn = ', '.join(f'"{c}"' for c in cols)

            if pk_column and pk_column in common:
                cur.execute(
                    f'INSERT INTO "{table_name}" ({cn}) VALUES ({ph}) '
                    f'ON CONFLICT ("{pk_column}") DO UPDATE SET '
                    + ', '.join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c != pk_column),
                    vals
                )
            else:
                cur.execute(f'INSERT INTO "{table_name}" ({cn}) VALUES ({ph})', vals)
            count += 1

        conn.commit()
        return count
    except Exception as e:
        print(f"[db_utils] save_table({table_name}) error: {e}", file=sys.stderr)
        conn.rollback()
        return _json_fallback_save(table_name, records)
    finally:
        cur.close()


def insert_record(table_name: str, record: dict[str, Any],
                  pk_column: Optional[str] = None) -> bool:
    """Insert a single record. Returns True on success."""
    if not _is_available():
        return _json_fallback_insert(table_name, record)

    conn = _get_conn()
    cur = conn.cursor()
    try:
        if pk_column is None:
            pk_column = _detect_pk(table_name)

        cur.execute("""
            SELECT column_name FROM information_schema.columns
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table_name,))
        valid_cols = {row[0] for row in cur.fetchall()}

        common = {k: _serialize_for_db(v) for k, v in record.items() if k in valid_cols}
        if not common:
            return False
        cols = list(common.keys())
        vals = [common[c] for c in cols]
        ph = ', '.join(['%s'] * len(cols))
        cn = ', '.join(f'"{c}"' for c in cols)

        if pk_column and pk_column in common:
            cur.execute(
                f'INSERT INTO "{table_name}" ({cn}) VALUES ({ph}) '
                f'ON CONFLICT ("{pk_column}") DO UPDATE SET '
                + ', '.join(f'"{c}" = EXCLUDED."{c}"' for c in cols if c != pk_column),
                vals
            )
        else:
            cur.execute(f'INSERT INTO "{table_name}" ({cn}) VALUES ({ph})', vals)
        conn.commit()
        return True
    except Exception as e:
        print(f"[db_utils] insert_record({table_name}) error: {e}", file=sys.stderr)
        conn.rollback()
        return _json_fallback_insert(table_name, record)
    finally:
        cur.close()


def update_record(table_name: str, pk_column: str, pk_value: Any,
                  updates: dict) -> bool:
    """Update a single record by primary key. Returns True on success."""
    if not _is_available():
        return _json_fallback_update(table_name, pk_column, pk_value, updates)

    conn = _get_conn()
    cur = conn.cursor()
    try:
        set_clause = ', '.join(
            f'"{k}" = %s' for k in updates.keys()
        )
        vals = [_serialize_for_db(v) for v in updates.values()]
        vals.append(pk_value)
        cur.execute(
            f'UPDATE "{table_name}" SET {set_clause} WHERE "{pk_column}" = %s',
            vals
        )
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"[db_utils] update_record({table_name}) error: {e}", file=sys.stderr)
        conn.rollback()
        return _json_fallback_update(table_name, pk_column, pk_value, updates)
    finally:
        cur.close()


def delete_record(table_name: str, pk_column: str, pk_value: Any) -> bool:
    """Delete a single record by primary key. Returns True on success."""
    if not _is_available():
        return _json_fallback_delete(table_name, pk_column, pk_value)

    conn = _get_conn()
    cur = conn.cursor()
    try:
        cur.execute(f'DELETE FROM "{table_name}" WHERE "{pk_column}" = %s', (pk_value,))
        conn.commit()
        return cur.rowcount > 0
    except Exception as e:
        print(f"[db_utils] delete_record({table_name}) error: {e}", file=sys.stderr)
        conn.rollback()
        return _json_fallback_delete(table_name, pk_column, pk_value)
    finally:
        cur.close()


# ── Helpers ─────────────────────────────────────────────────

def _detect_pk(table_name: str) -> Optional[str]:
    """Auto-detect primary key column for a table."""
    try:
        conn = _get_conn()
        cur = conn.cursor()
        cur.execute("""
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_name = %s
        """, (table_name,))
        row = cur.fetchone()
        cur.close()
        return row[0] if row else None
    except Exception:
        return None


def _serialize_for_db(val: Any) -> Any:
    """Convert Python value to PostgreSQL-compatible format."""
    if val is None:
        return None
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, default=str)
    return str(val)


# ── JSON Fallback (backward compatible) ─────────────────────

# Map table names to legacy JSON paths (configured per module)
_TABLE_PATH_MAP: dict[str, Path] = {}


def register_table_path(table_name: str, json_path: Path):
    """Register a JSON file path as fallback for a table."""
    _TABLE_PATH_MAP[table_name] = Path(json_path)


def _json_fallback_load(table_name: str) -> list[dict[str, Any]]:
    """Fallback: read from JSON file."""
    path = _TABLE_PATH_MAP.get(table_name)
    if path and path.exists():
        try:
            text = path.read_text(encoding="utf-8")
            return json.loads(text) if text.strip() else []
        except Exception:
            return []
    return []


def _json_fallback_save(table_name: str, records: list[dict[str, Any]]) -> int:
    """Fallback: write to JSON file."""
    path = _TABLE_PATH_MAP.get(table_name)
    if path:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n",
                          encoding="utf-8")
            return len(records)
        except Exception:
            return 0
    return 0


def _json_fallback_insert(table_name: str, record: dict[str, Any]) -> bool:
    """Fallback: append to JSON array."""
    records = _json_fallback_load(table_name)
    records.append(record)
    _json_fallback_save(table_name, records)
    return True


def _json_fallback_update(table_name: str, pk_column: str, pk_value: Any,
                          updates: dict[str, Any]) -> bool:
    """Fallback: update record in JSON array."""
    records = _json_fallback_load(table_name)
    for rec in records:
        if rec.get(pk_column) == pk_value:
            rec.update(updates)
            _json_fallback_save(table_name, records)
            return True
    return False


def _json_fallback_delete(table_name: str, pk_column: str, pk_value: Any) -> bool:
    """Fallback: remove record from JSON array."""
    records = _json_fallback_load(table_name)
    new_records = [r for r in records if r.get(pk_column) != pk_value]
    if len(new_records) < len(records):
        _json_fallback_save(table_name, new_records)
        return True
    return False


# ── Bulk import from JSON to PostgreSQL ─────────────────────

def import_json_to_pg(json_path: Path, table_name: str) -> int:
    """One-time import: read JSON file and write to PostgreSQL table.
    Returns number of rows imported.
    """
    try:
        text = json_path.read_text(encoding="utf-8")
        data = json.loads(text) if text.strip() else []
    except Exception:
        return 0

    if isinstance(data, dict):
        vals = list(data.values())
        if vals and all(isinstance(v, dict) for v in vals[:5]):
            data = list(data.values())
        else:
            data = [data]
    if not isinstance(data, list):
        return 0

    return save_table(table_name, data)


# ── Initialization ──────────────────────────────────────────

# Module prefix mapping (derived from directory name)
_MODULE_PREFIX_MAP = {
    "TAC-timesheet": "ts",
    "TAC-employeeadmin": "emp",
    "TAC-reimbursement": "rmb",
    "tacaipaysg": "pay_sg",
    "User_admin": "ua",
    "masterdata": "md",
    "tacai-portal": "pt",
    "tacaimsg": "msg",
    "InterviewReady": "iv",
    "TacSelfVacation": "ss",
}


def path_to_table(path: Path) -> str:
    """Convert a JSON database path to a PostgreSQL table name.

    Example:
        .../TAC-timesheet/database/timesheet_entries.json → ts_timesheet_entries
        .../TACAIPAY/tacaipaysg/database/audit_logs.json → pay_sg_audit_logs
    """
    file_stem = path.stem  # filename without .json
    path_str = str(path)

    # Try to find the module prefix from path components
    for module_dir, prefix in _MODULE_PREFIX_MAP.items():
        if module_dir in path_str:
            return f"{prefix}_{file_stem}"

    # Fallback: use parent directory name
    return f"tbl_{file_stem}"


def init_module(db_dir: Path, prefix: str):
    """Register all JSON files in a module's database directory as table fallbacks.
    Call this once per module at startup.

    Example:
        init_module(Path(__file__).parent.parent / "database", "ts")
    """
    if not db_dir.exists():
        return

    for jf in sorted(db_dir.glob("*.json")):
        if jf.name.startswith("bak_"):
            continue
        table_name = f"{prefix}_{jf.stem}"
        register_table_path(table_name, jf)


# Print status at import time
if DB_ENABLED:
    _available = _is_available()
    _status = "connected" if _available else "fallback to JSON"
    print(f"[db_utils] PostgreSQL {DB_CONFIG['host']}:{DB_CONFIG['port']}/{DB_CONFIG['dbname']} → {_status}",
          file=sys.stderr)
