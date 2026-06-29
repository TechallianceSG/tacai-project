#!/usr/bin/env python3
"""
TACAI Project: JSON → PostgreSQL Migration v3
Strategy: One connection per table = complete error isolation.
"""
import json, os, sys
from datetime import datetime
import psycopg2

DB = {"host":"localhost", "port":5432, "dbname":"tacai_dev", "user":"tacai_user", "password":"tacai123"}
ROOT = "/Users/terencewang/Documents/claude-project/TACAI-Project"

MODULES = [
    ("TAC-timesheet",        "ts",     "考勤"),
    ("TAC-employeeadmin",    "emp",    "员工管理"),
    ("TAC-reimbursement",    "rmb",    "费用报销"),
    ("TACAIPAY/tacaipaysg",  "pay_sg", "薪资SG"),
    ("TACAI-Core/User_admin","ua",     "用户管理"),
    ("TACAI-Core/masterdata","md",     "主数据"),
    ("TACAI-Core/tacai-portal","pt",   "门户"),
    ("TACAI-Core/tacaimsg",  "msg",    "消息中心"),
    ("InterviewReady",        "iv",     "面试系统"),
    ("TacSelfService/TacSelfVacation","ss","员工自助"),
]

JSONB_COLS = {'before_value','after_value','profile','employment','payroll','visa',
    'dispatch_compliance','language_profile','labels','statuses','descriptions',
    'steps','changed_fields','labels_i18n','config','metadata','payload',
    'extra','details','salary_components','deductions','allowances','changed_data',
    'step_config','item_labels','condition_config','calculation_config','fields',
    'permissions','settings','roles','modules','attributes','properties'}

def infer_type(col, vals):
    non_null = [v for v in vals if v is not None]
    if not non_null: return "TEXT"

    # Only mark as JSONB if name matches AND actual data contains complex types
    if col in JSONB_COLS:
        if any(isinstance(v, (dict, list)) for v in non_null):
            return "JSONB"
        # If all values are strings despite being in JSONB_COLS, use TEXT
        # (e.g., 'summary' might be plain text, not JSON)

    if all(isinstance(v, bool) for v in non_null): return "BOOLEAN"
    if all(isinstance(v, int) for v in non_null): return "INTEGER"
    if all(isinstance(v, (int,float)) for v in non_null): return "NUMERIC"
    if all(isinstance(v, (dict,list)) for v in non_null): return "JSONB"
    return "TEXT"

def convert(val, col, pgtype):
    if val is None: return None
    pt = pgtype.upper() if pgtype else "TEXT"

    # JSONB columns: must produce valid JSON
    if pt == "JSONB":
        if isinstance(val, str):
            # Already a JSON string — verify it's valid
            try:
                json.loads(val)
                return val
            except:
                # Not valid JSON, wrap as JSON string
                return json.dumps(val, ensure_ascii=False)
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False, default=str)
        # Scalar value → wrap in json.dumps
        return json.dumps(val, ensure_ascii=False, default=str)

    if pt == "BOOLEAN":
        if isinstance(val, bool): return val
        if isinstance(val, str): return val.lower() in ('true','1','yes')
        return bool(val)
    if pt in ("INTEGER","NUMERIC"):
        try: return int(val) if pt=="INTEGER" else float(val)
        except: return val

    # For TEXT columns
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False, default=str)
    if isinstance(val, bool): return val
    if isinstance(val, str): return val
    return str(val)

def extract_items(data):
    if isinstance(data, list): return data
    if isinstance(data, dict):
        vals = list(data.values())
        if vals and all(isinstance(v, dict) for v in vals[:5]):
            return list(data.values())
        return [data]
    return []

def load_table(fpath):
    try:
        with open(fpath) as f: return json.load(f)
    except: return None

# ── Collect tasks ──────────────────────────────────────────
tasks = []
for mod_path, prefix, mod_name in MODULES:
    db_dir = os.path.join(ROOT, mod_path, "database")
    if not os.path.isdir(db_dir): continue
    for jf in sorted(os.listdir(db_dir)):
        if not jf.endswith('.json') or jf.startswith('bak_'): continue
        fpath = os.path.join(db_dir, jf)
        table = f"{prefix}_{jf.replace('.json','')}"
        data = load_table(fpath)
        items = extract_items(data) if data else []
        tasks.append((table, fpath, mod_name, items))

print("=" * 70)
print("TACAI: JSON → PostgreSQL Migration v3 (per-table isolation)")
print(f"Target: {DB['host']}:{DB['port']}/{DB['dbname']}")
print(f"Tables: {len(tasks)}")
print("=" * 70)

# ── Phase 1: Create all tables ─────────────────────────────
print("\n📐 Phase 1: Drop + Create tables...")
conn = psycopg2.connect(**DB)
cur = conn.cursor()
created = 0

for table, fpath, mod_name, items in tasks:
    if not items:
        # Create empty table with id column for tables with no data
        cur.execute(f'DROP TABLE IF EXISTS "{table}" CASCADE')
        cur.execute(f'CREATE TABLE "{table}" (id TEXT)')
        created += 1
        continue

    # collect columns + types — scan ALL rows for complete column discovery
    cols = {}
    for item in items:
        if not isinstance(item, dict): continue
        for k, v in item.items():
            if k not in cols: cols[k] = []
            if len(cols[k]) < 20: cols[k].append(v)

    # Find best PK: prefer columns ending in _id that have ALL UNIQUE values in sample
    id_cols = [c for c in cols if c.endswith('_id') or c in ('module_key','project_code','name')]
    best_pk = None
    for candidate in id_cols:
        vals = [item.get(candidate) for item in items[:200] if isinstance(item, dict)]
        if vals and len(vals) == len(set(str(v) for v in vals)):
            best_pk = candidate
            break
    # Fallback to first _id column
    if best_pk is None and id_cols:
        best_pk = id_cols[0]
    pk = best_pk

    col_defs = []
    for c in cols:
        t = infer_type(c, cols[c])
        nulls = "NOT NULL" if c == pk else ""
        col_defs.append(f'"{c}" {t} {nulls}'.strip())
    pk_line = f', PRIMARY KEY ("{pk}")' if pk else ''

    ddl = f'DROP TABLE IF EXISTS "{table}" CASCADE;\n'
    ddl += f'CREATE TABLE "{table}" (\n  '
    ddl += ',\n  '.join(col_defs)
    ddl += pk_line + '\n)'

    try:
        cur.execute(ddl)
        created += 1
    except Exception as e:
        print(f"  ❌ DDL error {table}: {e}")

conn.commit()
cur.close()
conn.close()
print(f"  ✅ {created} tables created")

# ── Phase 2: Import data (one connection per table) ────────
print("\n📥 Phase 2: Importing data...")
total_imported = 0
import_ok = 0
import_err = 0
import_empty = 0

for idx, (table, fpath, mod_name, items) in enumerate(tasks):
    if not items:
        import_empty += 1
        continue

    conn = psycopg2.connect(**DB)
    cur = conn.cursor()

    # Get column type info
    try:
        cur.execute("""
            SELECT column_name, data_type FROM information_schema.columns
            WHERE table_name = %s ORDER BY ordinal_position
        """, (table,))
        col_types = {row[0]: row[1] for row in cur.fetchall()}
    except:
        col_types = {}

    count = 0
    for item in items:
        if not isinstance(item, dict): continue
        # Only use columns that exist in this table
        common = {k: v for k, v in item.items() if k in col_types}
        if not common: continue

        converted = {}
        for k, v in common.items():
            converted[k] = convert(v, k, col_types[k])

        cols = list(converted.keys())
        vals = [converted[c] for c in cols]
        ph = ', '.join(['%s'] * len(cols))
        cn = ', '.join(f'"{c}"' for c in cols)

        try:
            # Use savepoint per row for clean error recovery
            cur.execute(f'SAVEPOINT sp_row')
            cur.execute(f'INSERT INTO "{table}" ({cn}) VALUES ({ph})', vals)
            cur.execute(f'RELEASE SAVEPOINT sp_row')
            count += 1
        except Exception as e:
            # Rollback to savepoint, then skip this bad row
            try:
                cur.execute(f'ROLLBACK TO SAVEPOINT sp_row')
            except:
                pass
            # Try upsert in case it's a PK conflict
            try:
                cur.execute(f'SAVEPOINT sp_row2')
                cur.execute(f'INSERT INTO "{table}" ({cn}) VALUES ({ph}) ON CONFLICT DO NOTHING', vals)
                cur.execute(f'RELEASE SAVEPOINT sp_row2')
                if cur.rowcount and cur.rowcount > 0:
                    count += 1
            except:
                try:
                    cur.execute(f'ROLLBACK TO SAVEPOINT sp_row2')
                except:
                    pass

    conn.commit()
    cur.close()
    conn.close()

    status = "✅" if count == len(items) else f"⚠️ {count}/{len(items)}"
    if count == len(items): import_ok += 1
    elif count > 0: import_err += 1
    else: import_err += 1

    total_imported += count
    print(f"  [{idx+1:2d}/{len(tasks)}] {table:<38s} {count:>5d}/{len(items):<5d} {status}")

print(f"  Total: {total_imported} records, {import_ok} tables OK, {import_err} partial, {import_empty} empty")

# ── Phase 3: Verification ──────────────────────────────────
print(f"\n🔍 Phase 3: Verification (fresh connection)...")
vconn = psycopg2.connect(**DB)
vcur = vconn.cursor()

match = 0; mismatch = 0
for table, fpath, mod_name, items in tasks:
    expected = len(items)
    try:
        vcur.execute(f'SELECT COUNT(*) FROM "{table}"')
        actual = vcur.fetchone()[0]
    except:
        actual = -2

    if expected == actual:
        match += 1
    elif expected > 0 or actual > 0:
        mismatch += 1
        if actual >= 0:
            print(f"  MISMATCH: {table:<38s} json={expected:>5d}  pg={actual:>5d}")

vcur.close(); vconn.close()

print(f"  Verified: {match} match, {mismatch} mismatch (total {len(tasks)} tables)")
print(f"\n✅ Migration v3 completed at {datetime.now().isoformat()}")
print(f"   Total records imported: {total_imported}")
