#!/usr/bin/env python3
"""
Clean one-shot patcher: adds PostgreSQL support to TACAI modules.
"""
import re
from pathlib import Path

ROOT = Path("/Users/terencewang/Documents/claude-project/TACAI-Project")

FILES = [
    "TAC-timesheet/backend/app.py",
    "TAC-employeeadmin/backend/app.py",
    "TAC-reimbursement/backend/app.py",
    "TACAI-Core/User_admin/backend/app.py",
    "TACAI-Core/masterdata/backend/app.py",
    "TACAI-Core/tacaimsg/backend/app.py",
    "TacSelfService/TacSelfVacation/backend/app.py",
]

PG_IMPORT = '''# === PostgreSQL integration ===
import sys as _sys, os as _os
from pathlib import Path as _Path
_pg_project_root = _Path(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
while not (_pg_project_root / 'TACAI-Core').exists() and _pg_project_root != _pg_project_root.parent:
    _pg_project_root = _pg_project_root.parent
_pg_core_path = _pg_project_root / 'TACAI-Core'
if str(_pg_core_path) not in _sys.path:
    _sys.path.insert(0, str(_pg_core_path))
try:
    import db_utils as _db
    _PG_AVAILABLE = _db._is_available() if _db.DB_ENABLED else False
except Exception:
    _PG_AVAILABLE = False
# ============================================'''

NEW_LOAD = '''def load_json_array(path: Path) -> list:
    if _PG_AVAILABLE:
        try:
            result = _db.load_table(_db.path_to_table(path))
            if result is not None:
                return result
        except Exception:
            pass
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array.")
    return [item for item in data if isinstance(item, dict)]'''

NEW_WRITE = '''def write_json_array(path: Path, records: list) -> None:
    if _PG_AVAILABLE:
        try:
            _db.save_table(_db.path_to_table(path), records)
            return
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")'''


def patch_file(filepath: Path):
    content = filepath.read_text(encoding='utf-8')

    # Verify not already patched
    if '_PG_AVAILABLE' in content:
        print(f"  ⏭️  Already patched")
        return False

    # Find insertion point: after last import line
    lines = content.split('\n')
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i + 1
    if insert_idx == 0:
        insert_idx = 5  # fallback after shebang/docstring

    # Insert PG import
    lines.insert(insert_idx, PG_IMPORT)
    content = '\n'.join(lines)

    # Replace load_json_array
    old_load = re.search(
        r'def load_json_array\([^)]*\).*?(?=\n    def |\n\ndef |\nclass |\Z)',
        content, re.DOTALL
    )
    if old_load:
        content = content.replace(old_load.group(0), NEW_LOAD)

    # Replace write_json_array
    old_write = re.search(
        r'def write_json_array\([^)]*\).*?(?=\n    def |\n\ndef |\nclass |\Z)',
        content, re.DOTALL
    )
    if old_write:
        content = content.replace(old_write.group(0), NEW_WRITE)

    filepath.write_text(content, encoding='utf-8')

    # Syntax check
    import py_compile
    try:
        py_compile.compile(str(filepath), doraise=True)
        return True
    except py_compile.PyCompileError as e:
        print(f"  ❌ Syntax error: {e}")
        return False


def main():
    print("Clean PostgreSQL patcher v4...")
    for f in FILES:
        filepath = ROOT / f
        if not filepath.exists():
            print(f"  ⚠️  Not found: {f}")
            continue
        if patch_file(filepath):
            print(f"  ✅ {f}")
    print("Done")

if __name__ == "__main__":
    main()
