#!/usr/bin/env python3
"""
Patch all TACAI module app.py files to use PostgreSQL via db_utils.
Replaces load_json_array / write_json_array with PG-aware versions.
JSON fallback is preserved for backward compatibility.
"""

import re
import sys
from pathlib import Path

ROOT = Path("/Users/terencewang/Documents/claude-project/TACAI-Project")

TARGETS = [
    "TAC-timesheet/backend/app.py",
    "TAC-employeeadmin/backend/app.py",
    "TAC-reimbursement/backend/app.py",
    "TACAIPAY/tacaipaysg/backend/app.py",
    "TACAI-Core/User_admin/backend/app.py",
    "TACAI-Core/masterdata/backend/app.py",
    "TACAI-Core/tacai-portal/backend/app.py",
    "TACAI-Core/tacaimsg/backend/app.py",
    "InterviewReady/app/cli.py",  # may use different pattern
    "TacSelfService/TacSelfVacation/backend/app.py",
]

DB_UTILS_IMPORT = """
# === PostgreSQL integration (auto-patched) ===
import sys as _sys, os as _os
from pathlib import Path as _Path
_project_root = _Path(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
while not (_project_root / 'TACAI-Core').exists() and _project_root != _project_root.parent:
    _project_root = _project_root.parent
_core_path = _project_root / 'TACAI-Core'
if str(_core_path) not in _sys.path:
    _sys.path.insert(0, str(_core_path))
try:
    import db_utils as _db
    _DB_AVAILABLE = _db._is_available() if _db.DB_ENABLED else False
except Exception:
    _DB_AVAILABLE = False
# ============================================
"""

NEW_LOAD_FUNC = '''
def load_json_array(path: Path) -> list[dict[str, Any]]:
    """Load records from PostgreSQL (with JSON fallback)."""
    if _DB_AVAILABLE:
        try:
            table = _db.path_to_table(path)
            result = _db.load_table(table)
            if result is not None:
                return result
        except Exception:
            pass
    # JSON fallback
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array.")
    return [item for item in data if isinstance(item, dict)]
'''

NEW_WRITE_FUNC = '''
def write_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    """Save records to PostgreSQL (with JSON fallback)."""
    if _DB_AVAILABLE:
        try:
            table = _db.path_to_table(path)
            _db.save_table(table, records)
            return
        except Exception:
            pass
    # JSON fallback
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\\n", encoding="utf-8")
'''


def patch_file(filepath: Path) -> bool:
    """Patch a single app.py file. Returns True if modified."""
    if not filepath.exists():
        print(f"  ⚠️  Not found: {filepath}")
        return False

    content = filepath.read_text(encoding="utf-8")

    # Check if already patched
    if "=== PostgreSQL integration (auto-patched) ===" in content:
        print(f"  ⏭️  Already patched: {filepath}")
        return False

    # Check if it has the load_json_array function
    if "def load_json_array" not in content:
        print(f"  ⚠️  No load_json_array found: {filepath}")
        return False

    # 1. Add import block after the first """ or ''' docstring or after #! line
    # Find a good insertion point: after last early import but before function defs
    lines = content.split('\n')

    # Find the last import line before function definitions
    insert_idx = 0
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            insert_idx = i + 1
        if line.startswith('def ') and insert_idx > 0:
            break

    # If no imports found, insert after docstring
    if insert_idx == 0:
        for i, line in enumerate(lines):
            if line.strip().startswith('"""') or line.strip().startswith("'''"):
                if i > 0 and (lines[i-1].strip().startswith('#!') or i <= 2):
                    insert_idx = i + 2
                    break

    if insert_idx == 0:
        insert_idx = 10  # fallback

    lines.insert(insert_idx, DB_UTILS_IMPORT)
    content = '\n'.join(lines)

    # 2. Replace load_json_array function
    # Pattern: def load_json_array(path: Path) -> ... up to the next def or end of file
    old_load = re.compile(
        r'def load_json_array\(path: Path\) -> list\[dict\[str, Any\]\]:.*?'
        r'(?=\n\ndef |\n\nclass |\Z)',
        re.DOTALL
    )

    # Simpler approach: find and replace the specific function block
    old_load_simple = re.compile(
        r'def load_json_array\([^)]*\).*?(?=\n(?:\n|\S)def |\nclass |\Z)',
        re.DOTALL
    )

    # Actually, let's use a more precise approach
    # Find the exact function boundaries

    # Check for both styles: with type hints and without
    match = re.search(
        r'def load_json_array\(path: Path\) -> list\[dict\[str, Any\]\]:.*?(?=\n    def |\n\ndef |\nclass |\Z)',
        content, re.DOTALL
    )
    if not match:
        match = re.search(
            r'def load_json_array\(path\):.*?(?=\n    def |\n\ndef |\nclass |\Z)',
            content, re.DOTALL
        )
    if not match:
        match = re.search(
            r'def load_json_array\([^)]*\):.*?(?=\n    def |\n\ndef |\nclass |\Z)',
            content, re.DOTALL
        )

    if match:
        content = content.replace(match.group(0), NEW_LOAD_FUNC.strip())

    # 3. Replace write_json_array function
    match = re.search(
        r'def write_json_array\(path: Path, records: list\[dict\[str, Any\]\]\) -> None:.*?(?=\n    def |\n\ndef |\nclass |\Z)',
        content, re.DOTALL
    )
    if not match:
        match = re.search(
            r'def write_json_array\(path, records\):.*?(?=\n    def |\n\ndef |\nclass |\Z)',
            content, re.DOTALL
        )
    if not match:
        match = re.search(
            r'def write_json_array\([^)]*\):.*?(?=\n    def |\n\ndef |\nclass |\Z)',
            content, re.DOTALL
        )

    if match:
        content = content.replace(match.group(0), NEW_WRITE_FUNC.strip())

    filepath.write_text(content, encoding="utf-8")
    return True


def main():
    print("Patching TACAI modules for PostgreSQL...")
    patched = 0
    skipped = 0

    for target in TARGETS:
        filepath = ROOT / target
        rel = str(target)
        try:
            if patch_file(filepath):
                print(f"  ✅ {rel}")
                patched += 1
        except Exception as e:
            print(f"  ❌ {rel}: {e}")

    print(f"\nPatched: {patched}, Skipped: {skipped}")


if __name__ == "__main__":
    main()
