"""Local web app for TACAI User Management core service.

This project intentionally uses only Python standard library modules so it can
run locally without installing dependencies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
from typing import Any
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
# === PostgreSQL integration ===
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
# ============================================

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
I18N_DIR = ROOT_DIR / "i18n"
USERS_PATH = DATABASE_DIR / "users.json"
ROLES_PATH = DATABASE_DIR / "roles.json"
PERMISSIONS_PATH = DATABASE_DIR / "permissions.json"
USER_ROLE_MAPPING_PATH = DATABASE_DIR / "user_role_mapping.json"
ROLE_PERMISSION_MAPPING_PATH = DATABASE_DIR / "role_permission_mapping.json"
USER_ENTITY_MAPPING_PATH = DATABASE_DIR / "user_entity_mapping.json"
USER_SESSIONS_PATH = DATABASE_DIR / "user_sessions.json"
USER_AUDIT_LOGS_PATH = DATABASE_DIR / "user_audit_logs.json"
MASTERDATA_ENTITIES_PATH = ROOT_DIR.parent / "masterdata" / "database" / "entities.json"
MASTERDATA_DEPARTMENTS_PATH = ROOT_DIR.parent / "masterdata" / "database" / "departments.json"
EMPLOYEEADMIN_EMPLOYEES_PATH = ROOT_DIR.parents[1] / "TAC-employeeadmin" / "database" / "employees.json"

DEFAULT_LANG = "en"
SUPPORTED_LANGS = {"en", "ja", "zh"}
SYSTEM_USER = "system"
SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "tacai_flash"
SESSION_TIMEOUT_MINUTES = 480
PASSWORD_ITERATIONS = 120_000
MAX_FAILED_LOGINS = 5
USER_STATUSES = {"active", "inactive", "locked", "suspended"}
USER_TYPES = {"employee", "admin", "external", "system"}
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
USER_ADMIN_PUBLIC_BASE_URL = os.environ.get("USER_ADMIN_BASE_URL", os.environ.get("USER_ADMIN_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8006")).strip().rstrip("/")
PORTAL_PUBLIC_BASE_URL = os.environ.get("PORTAL_BASE_URL", os.environ.get("PORTAL_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8005")).strip().rstrip("/")
REMOTE_COOKIE_DOMAIN = os.environ.get("TACAI_COOKIE_DOMAIN", "").strip()
REMOTE_COOKIE_SECURE = os.environ.get("TACAI_COOKIE_SECURE", "").strip().lower() in {"1", "true", "yes", "on"} or USER_ADMIN_PUBLIC_BASE_URL.startswith("https://")
CONFIGURED_PUBLIC_HOSTS = {host.strip().lower() for host in os.environ.get("TACAI_ALLOWED_PUBLIC_HOSTS", "").split(",") if host.strip()}
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST}
LOCAL_ALLOWED_PORTS = {3000, 3001, 4000, 4001, 5000, 5001, 6000, 6001, 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8011, 8012, 8015, 8016, 8018}


def base_url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


def configured_public_hosts() -> set[str]:
    hosts = set(CONFIGURED_PUBLIC_HOSTS)
    for value in [USER_ADMIN_PUBLIC_BASE_URL, PORTAL_PUBLIC_BASE_URL]:
        host = base_url_host(value)
        if host:
            hosts.add(host)
    return hosts


ALLOWED_PUBLIC_HOSTS = configured_public_hosts()
ALLOWED_NEXT_HOSTS = LOCAL_ALLOWED_HOSTS | ALLOWED_PUBLIC_HOSTS
ALLOWED_NEXT_PORTS = LOCAL_ALLOWED_PORTS | {443}


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def origin_allowed(source: str) -> bool:
    if not source:
        return True
    parsed = urlparse(source)
    host = (parsed.hostname or "").lower()
    if host in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS:
        return True
    if parsed.scheme == "https" and host in ALLOWED_PUBLIC_HOSTS and (parsed.port in {None, 443}):
        return True
    return False


def cookie_attributes(max_age: int | None = None) -> str:
    attrs = ["HttpOnly", "SameSite=Lax", "Path=/"]
    if REMOTE_COOKIE_DOMAIN:
        attrs.append(f"Domain={REMOTE_COOKIE_DOMAIN}")
    if REMOTE_COOKIE_SECURE:
        attrs.append("Secure")
    if max_age is not None:
        attrs.append(f"Max-Age={max_age}")
    return "; ".join(attrs)


def session_cookie_header(session_id: str) -> str:
    return f"{SESSION_COOKIE}={session_id}; {cookie_attributes()}"


def clear_session_cookie_header() -> str:
    return f"{SESSION_COOKIE}=; {cookie_attributes(0)}"


INITIAL_ADMIN_EMAIL = "admin@tacai.local"
INITIAL_ADMIN_PASSWORD_HASH = "pbkdf2_sha256$120000$local_mvp_bootstrap_admin_salt$91f57a94132fb289a58e10af6b18e54ab7bc2efa109d773af3d6e3eef5316033"

ROLE_DEFINITIONS = [
    {"role_id": "ROLE-SYSTEM-ADMIN", "role_key": "system_admin", "role_name": "System Admin", "description_key": "role.system_admin.description"},
    {"role_id": "ROLE-HR-MANAGER", "role_key": "hr_manager", "role_name": "HR Manager", "description_key": "role.hr_manager.description"},
    {"role_id": "ROLE-FINANCE", "role_key": "finance", "role_name": "Finance", "description_key": "role.finance.description"},
    {"role_id": "ROLE-MANAGER", "role_key": "manager", "role_name": "Manager", "description_key": "role.manager.description"},
    {"role_id": "ROLE-EMPLOYEE", "role_key": "employee", "role_name": "Employee", "description_key": "role.employee.description"},
    {"role_id": "ROLE-REMOTE-CONSULTANT", "role_key": "remote_consultant", "role_name": "Remote Consultant", "description_key": "role.remote_consultant.description"},
]

PERMISSION_DEFINITIONS = [
    ("user_management.access", "user_management", "access"),
    ("user_management.manage_users", "user_management", "manage_users"),
    ("user_management.manage_roles", "user_management", "manage_roles"),
    ("user_management.manage_permissions", "user_management", "manage_permissions"),
    ("user_management.audit.view", "user_management", "audit_view"),
    ("masterdata.access", "masterdata", "access"),
    ("masterdata.view", "masterdata", "view"),
    ("masterdata.maintain", "masterdata", "maintain"),
    ("masterdata.admin", "masterdata", "admin"),
    ("employee_management.access", "employee_management", "access"),
    ("employee_management.view", "employee_management", "view"),
    ("employee_management.edit", "employee_management", "edit"),
    ("employee_management.payroll.view", "employee_management", "payroll_view"),
    ("employee_management.payroll.edit", "employee_management", "payroll_edit"),
    ("employee_management.visa.view", "employee_management", "visa_view"),
    ("employee_management.visa.edit", "employee_management", "visa_edit"),
    ("employee_management.documents.manage", "employee_management", "documents_manage"),
    ("employee_management.reports.view", "employee_management", "reports_view"),
    ("employee_management.export", "employee_management", "export"),
    ("employee_management.audit.view", "employee_management", "audit_view"),
    ("timesheet.access", "timesheet", "access"),
    ("timesheet.submit", "timesheet", "submit"),
    ("timesheet.edit_own", "timesheet", "edit_own"),
    ("timesheet.delete_own", "timesheet", "delete_own"),
    ("timesheet.approve", "timesheet", "approve"),
    ("timesheet.team_view", "timesheet", "team_view"),
    ("timesheet.proxy_edit", "timesheet", "proxy_edit"),
    ("timesheet.delete", "timesheet", "delete"),
    ("reimbursement.access", "reimbursement", "access"),
    ("reimbursement.submit", "reimbursement", "submit"),
    ("reimbursement.view_own", "reimbursement", "view_own"),
    ("reimbursement.approve", "reimbursement", "approve"),
    ("reimbursement.payment", "reimbursement", "payment"),
    ("reimbursement.reports.view", "reimbursement", "reports_view"),
    ("payroll.access", "payroll", "access"),
    ("payroll.view", "payroll", "view"),
    ("payroll.edit", "payroll", "edit"),
    ("payroll.reports.view", "payroll", "reports_view"),
    ("financial_reports.view", "financial_reports", "view"),
    ("interview_ready.access", "interview_ready", "access"),
    ("interview_ready.jd_insight", "interview_ready", "jd_insight"),
    ("interview_ready.resume_match", "interview_ready", "resume_match"),
    ("interview_ready.mock_interview", "interview_ready", "mock_interview"),
    ("interview_ready.japan_risk", "interview_ready", "japan_risk"),
    ("interview_ready.report.view", "interview_ready", "report_view"),
    ("interview_ready.report.export", "interview_ready", "report_export"),
    ("interview_ready.audit.view", "interview_ready", "audit_view"),
    ("training.access", "training", "access"),
    ("training.manage", "training", "manage"),
    ("training.view_own", "training", "view_own"),
    ("vendor_expense.access", "vendor_expense", "access"),
    ("vendor_expense.submit", "vendor_expense", "submit"),
    ("vendor_expense.approve", "vendor_expense", "approve"),
    ("vendor_expense.payment", "vendor_expense", "payment"),
    ("client_revenue.access", "client_revenue", "access"),
    ("client_revenue.view", "client_revenue", "view"),
    ("client_revenue.manage", "client_revenue", "manage"),
    ("client_revenue.reports.view", "client_revenue", "reports_view"),
    ("client_revenue.customer_master.maintain", "client_revenue", "customer_master_maintain"),
    ("fileadmin.access", "fileadmin", "access"),
    ("fileadmin.view", "fileadmin", "view"),
    ("fileadmin.create", "fileadmin", "create"),
    ("fileadmin.edit", "fileadmin", "edit"),
    ("fileadmin.upload", "fileadmin", "upload"),
    ("fileadmin.archive", "fileadmin", "archive"),
    ("fileadmin.reminders.manage", "fileadmin", "reminders_manage"),
    ("fileadmin.audit.view", "fileadmin", "audit_view"),
    ("fileadmin.download", "fileadmin", "download"),
    ("tacaipay_sg.access", "tacaipay_sg", "access"),
    ("tacaipay_sg.view", "tacaipay_sg", "view"),
    ("tacaipay_sg.manage", "tacaipay_sg", "manage"),
    ("tacaipay_sg.calculate", "tacaipay_sg", "calculate"),
    ("tacaipay_sg.approve", "tacaipay_sg", "approve"),
    ("tacaipay_sg.release_payment", "tacaipay_sg", "release_payment"),
    ("tacaipay_sg.pay", "tacaipay_sg", "pay"),
    ("tacaipay_sg.reports.view", "tacaipay_sg", "reports_view"),
    ("tacaipay_sg.audit.view", "tacaipay_sg", "audit_view"),
    ("tacaipay_jp.access", "tacaipay_jp", "access"),
    ("tacaipay_jp.view", "tacaipay_jp", "view"),
    ("tacaipay_jp.manage", "tacaipay_jp", "manage"),
    ("tacaipay_jp.calculate", "tacaipay_jp", "calculate"),
    ("tacaipay_jp.approve", "tacaipay_jp", "approve"),
    ("tacaipay_jp.release_payment", "tacaipay_jp", "release_payment"),
    ("tacaipay_jp.reports.view", "tacaipay_jp", "reports_view"),
    ("tacaipay_jp.audit.view", "tacaipay_jp", "audit_view"),
]

ROLE_PERMISSION_KEYS = {
    "system_admin": "*",
    "hr_manager": [
        "employee_management.access",
        "employee_management.view",
        "employee_management.edit",
        "employee_management.payroll.view",
        "employee_management.payroll.edit",
        "employee_management.visa.view",
        "employee_management.visa.edit",
        "employee_management.documents.manage",
        "employee_management.reports.view",
        "employee_management.export",
        "masterdata.access",
        "masterdata.view",
        "masterdata.maintain",
        "timesheet.access",
        "timesheet.team_view",
        "reimbursement.access",
        "reimbursement.approve",
        "payroll.access",
        "payroll.view",
        "interview_ready.access",
        "interview_ready.jd_insight",
        "interview_ready.resume_match",
        "interview_ready.mock_interview",
        "interview_ready.japan_risk",
        "interview_ready.report.view",
        "interview_ready.report.export",
        "fileadmin.access",
        "fileadmin.view",
        "fileadmin.create",
        "fileadmin.edit",
        "fileadmin.upload",
        "fileadmin.archive",
        "fileadmin.reminders.manage",
        "fileadmin.audit.view",
        "fileadmin.download",
        "tacaipay_sg.access",
        "tacaipay_sg.view",
        "tacaipay_sg.manage",
        "tacaipay_sg.calculate",
        "tacaipay_sg.approve",
        "tacaipay_sg.reports.view",
        "tacaipay_sg.audit.view",
        "tacaipay_jp.access",
        "tacaipay_jp.view",
        "tacaipay_jp.manage",
        "tacaipay_jp.calculate",
        "tacaipay_jp.approve",
        "tacaipay_jp.reports.view",
        "tacaipay_jp.audit.view",
    ],
    "finance": [
        "payroll.access",
        "payroll.view",
        "payroll.edit",
        "payroll.reports.view",
        "reimbursement.access",
        "reimbursement.payment",
        "reimbursement.reports.view",
        "financial_reports.view",
        "vendor_expense.access",
        "vendor_expense.submit",
        "vendor_expense.approve",
        "vendor_expense.payment",
        "client_revenue.access",
        "client_revenue.view",
        "client_revenue.manage",
        "client_revenue.reports.view",
        "client_revenue.customer_master.maintain",
        "masterdata.access",
        "masterdata.view",
        "fileadmin.access",
        "fileadmin.view",
        "fileadmin.create",
        "fileadmin.upload",
        "fileadmin.reminders.manage",
        "fileadmin.download",
        "tacaipay_sg.access",
        "tacaipay_sg.view",
        "tacaipay_sg.release_payment",
        "tacaipay_sg.pay",
        "tacaipay_sg.reports.view",
        "tacaipay_jp.access",
        "tacaipay_jp.view",
        "tacaipay_jp.release_payment",
        "tacaipay_jp.reports.view",
    ],
    "manager": [
        "timesheet.access",
        "timesheet.submit",
        "timesheet.edit_own",
        "timesheet.approve",
        "timesheet.team_view",
        "reimbursement.access",
        "reimbursement.submit",
        "reimbursement.view_own",
        "reimbursement.approve",
        "masterdata.access",
        "masterdata.view",
        "fileadmin.access",
        "fileadmin.view",
        "fileadmin.download",
    ],
    "employee": [
        "employee_management.access",
        "timesheet.access",
        "timesheet.submit",
        "timesheet.edit_own",
        "reimbursement.access",
        "reimbursement.submit",
        "reimbursement.view_own",
        "masterdata.access",
        "masterdata.view",
    ],
    "remote_consultant": [
        "employee_management.access",
        "employee_management.view",
        "employee_management.edit",
        "timesheet.access",
        "timesheet.submit",
        "timesheet.edit_own",
        "reimbursement.access",
        "reimbursement.submit",
        "reimbursement.view_own",
        "masterdata.access",
        "masterdata.view",
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def operation_notice(messages: dict[str, str], record_type: str, record_name: str, action: str, actor: str) -> str:
    template = t(messages, f"operation.{action}", t(messages, "operation.saved", "{record_type} record {record} was saved successfully at {time} by {actor}."))
    return template.format(record_type=record_type, record=record_name or "-", time=now_iso(), actor=actor or "-")


def no_change_notice(messages: dict[str, str], record_type: str, record_name: str) -> str:
    template = t(messages, "operation.no_changes", "No changes detected for {record_type} record {record} at {time}. Nothing was saved and no audit entry was created.")
    return template.format(record_type=record_type, record=record_name or "-", time=now_iso())


def parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def format_jst(value: str) -> str:
    parsed = parse_iso(value)
    if not parsed:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M JST")


def h(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def load_json_array(path: Path) -> list:
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
    return [item for item in data if isinstance(item, dict)]

def save_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def load_users() -> list[dict[str, Any]]:
    return load_json_array(USERS_PATH)


def save_users(records: list[dict[str, Any]]) -> None:
    save_json_array(USERS_PATH, records)


def load_roles() -> list[dict[str, Any]]:
    return load_json_array(ROLES_PATH)


def load_permissions() -> list[dict[str, Any]]:
    return load_json_array(PERMISSIONS_PATH)


def load_user_role_mappings() -> list[dict[str, Any]]:
    return load_json_array(USER_ROLE_MAPPING_PATH)


def save_user_role_mappings(records: list[dict[str, Any]]) -> None:
    save_json_array(USER_ROLE_MAPPING_PATH, records)


def load_role_permission_mappings() -> list[dict[str, Any]]:
    return load_json_array(ROLE_PERMISSION_MAPPING_PATH)


def save_role_permission_mappings(records: list[dict[str, Any]]) -> None:
    save_json_array(ROLE_PERMISSION_MAPPING_PATH, records)


def load_user_entity_mappings() -> list[dict[str, Any]]:
    return load_json_array(USER_ENTITY_MAPPING_PATH)


def save_user_entity_mappings(records: list[dict[str, Any]]) -> None:
    save_json_array(USER_ENTITY_MAPPING_PATH, records)


def load_masterdata_entities() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_ENTITIES_PATH)


def load_masterdata_departments() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_DEPARTMENTS_PATH)


def load_employeeadmin_employees() -> list[dict[str, Any]]:
    return load_json_array(EMPLOYEEADMIN_EMPLOYEES_PATH)


def get_nested(record: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def load_sessions() -> list[dict[str, Any]]:
    return load_json_array(USER_SESSIONS_PATH)


def save_sessions(records: list[dict[str, Any]]) -> None:
    save_json_array(USER_SESSIONS_PATH, records)


def load_audit_logs() -> list[dict[str, Any]]:
    return load_json_array(USER_AUDIT_LOGS_PATH)


def save_audit_logs(records: list[dict[str, Any]]) -> None:
    save_json_array(USER_AUDIT_LOGS_PATH, records)


def next_id(records: list[dict[str, Any]], field: str, prefix: str, width: int) -> str:
    max_number = 0
    for record in records:
        value = str(record.get(field, ""))
        if value.startswith(prefix):
            suffix = value[len(prefix):]
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))
    return f"{prefix}{max_number + 1:0{width}d}"


def hash_password(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, encoded_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt, expected_hex = encoded_hash.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), iterations).hex()
    return hmac.compare_digest(digest, expected_hex)


def password_policy_errors(password: str, messages: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if len(password) < 6:
        errors.append(t(messages, "validation.password_min_length"))
    if len(password) > 10:
        errors.append(t(messages, "validation.password_max_length"))
    if not any(char.isupper() for char in password):
        errors.append(t(messages, "validation.password_uppercase"))
    if not any(char.islower() for char in password):
        errors.append(t(messages, "validation.password_lowercase"))
    if not any(char.isdigit() for char in password):
        errors.append(t(messages, "validation.password_number"))
    return errors


def load_i18n(lang: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    for candidate in (DEFAULT_LANG, lang):
        path = I18N_DIR / f"{candidate}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            messages.update({str(key): str(value) for key, value in data.items()})
    return messages


def t(messages: dict[str, str], key: str, default: str | None = None) -> str:
    return messages.get(key, default if default is not None else key)


def get_lang(query: dict[str, list[str]]) -> str:
    lang = query.get("lang", [DEFAULT_LANG])[0]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def url_with_lang(path: str, lang: str, params: dict[str, str] | None = None) -> str:
    query = {"lang": lang}
    if params:
        query.update({key: value for key, value in params.items() if value != ""})
    return f"{path}?{urlencode(query)}"


def safe_next_url(raw_next: str, default: str) -> str:
    next_url = raw_next.strip()
    if not next_url:
        return default
    parsed = urlparse(next_url)
    host = (parsed.hostname or "").lower()
    if not parsed.scheme and not parsed.netloc and parsed.path.startswith("/"):
        return next_url
    if parsed.scheme == "http" and host in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS:
        return next_url
    if parsed.scheme == "https" and host in ALLOWED_PUBLIC_HOSTS and (parsed.port in {None, 443}):
        return next_url
    return default


def find_user_by_email(email: str) -> dict[str, Any] | None:
    email_normalized = email.strip().lower()
    for user in load_users():
        if str(user.get("email", "")).strip().lower() == email_normalized and user.get("status") != "deleted":
            return user
    return None


def find_user_by_id(user_id: str) -> dict[str, Any] | None:
    for user in load_users():
        if user.get("user_id") == user_id and user.get("status") != "deleted":
            return user
    return None


def find_role_by_id(role_id: str) -> dict[str, Any] | None:
    for role in load_roles():
        if role.get("role_id") == role_id:
            return role
    return None


def find_permission_by_id(permission_id: str) -> dict[str, Any] | None:
    for permission in load_permissions():
        if permission.get("permission_id") == permission_id:
            return permission
    return None


def active_roles() -> list[dict[str, Any]]:
    return [role for role in load_roles() if role.get("active", True)]


def active_permissions() -> list[dict[str, Any]]:
    return [permission for permission in load_permissions() if permission.get("active", True)]


def active_user_role_ids(user_id: str) -> list[str]:
    active_role_ids = {str(role.get("role_id")) for role in active_roles()}
    role_ids: list[str] = []
    for mapping in load_user_role_mappings():
        role_id = str(mapping.get("role_id", ""))
        if mapping.get("user_id") == user_id and mapping.get("active", True) and role_id in active_role_ids:
            role_ids.append(role_id)
    return sorted(set(role_ids))


def role_keys_for_ids(role_ids: list[str]) -> list[str]:
    roles_by_id = {str(role.get("role_id")): role for role in load_roles()}
    keys = [str(roles_by_id[role_id].get("role_key")) for role_id in role_ids if role_id in roles_by_id]
    return sorted(set(keys))


def active_role_permission_ids(role_id: str) -> list[str]:
    active_permission_ids = {str(permission.get("permission_id")) for permission in active_permissions()}
    permission_ids: list[str] = []
    for mapping in load_role_permission_mappings():
        permission_id = str(mapping.get("permission_id", ""))
        if mapping.get("role_id") == role_id and mapping.get("active", True) and permission_id in active_permission_ids:
            permission_ids.append(permission_id)
    return sorted(set(permission_ids))


def permission_keys_for_ids(permission_ids: list[str]) -> list[str]:
    permissions_by_id = {str(permission.get("permission_id")): permission for permission in load_permissions()}
    keys = [str(permissions_by_id[permission_id].get("permission_key")) for permission_id in permission_ids if permission_id in permissions_by_id]
    return sorted(set(keys))


def sanitized_user_for_audit(user: dict[str, Any]) -> dict[str, Any]:
    allowed_fields = [
        "user_id",
        "username",
        "display_name",
        "email",
        "phone",
        "department",
        "position",
        "status",
        "user_type",
        "linked_employee_id",
        "linked_employee_no",
        "linked_employee_name",
        "linked_entity_id",
        "linked_entity_code",
        "linked_entity_name",
        "linked_department_id",
        "linked_department_code",
        "linked_department_name",
        "language_preference",
        "account_locked",
        "created_at",
        "updated_at",
        "deleted",
    ]
    return {field: user.get(field, "") for field in allowed_fields if field in user}


def actor_label(user: dict[str, Any] | None) -> str:
    if not user:
        return "unknown"
    return str(user.get("email") or user.get("user_id") or "unknown")


def would_leave_no_active_system_admin(target_user_id: str, new_role_ids: list[str] | None = None, new_status: str | None = None) -> bool:
    system_admin_role_ids = {str(role.get("role_id")) for role in load_roles() if role.get("role_key") == "system_admin" and role.get("active", True)}
    if not system_admin_role_ids:
        return False
    count = 0
    for user in load_users():
        user_id = str(user.get("user_id", ""))
        if user.get("status") == "deleted" or user.get("deleted"):
            continue
        status = new_status if user_id == target_user_id and new_status is not None else str(user.get("status", ""))
        if status != "active" or user.get("account_locked"):
            continue
        if user_id == target_user_id and new_role_ids is not None:
            role_ids = set(new_role_ids)
        else:
            role_ids = set(active_user_role_ids(user_id))
        if role_ids & system_admin_role_ids:
            count += 1
    return count == 0


def form_first(parsed: dict[str, list[str]], key: str, default: str = "") -> str:
    values = parsed.get(key, [])
    return values[0] if values else default


def enrich_user_employee_link(data: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(data)
    linked_employee_number = str(enriched.get("linked_employee_number", "") or "").strip()
    linked_employee_id = str(enriched.get("linked_employee_id", "") or "").strip()
    employee: dict[str, Any] | None = None
    resolution_error = ""
    if linked_employee_number:
        employee, resolution_error = find_employeeadmin_employee_by_number(linked_employee_number, linked_employee_id)
        linked_employee_id = str(employee.get("employee_id", "") if employee else "")
    elif linked_employee_id:
        employee = find_employeeadmin_employee(linked_employee_id)
    if resolution_error:
        enriched["_linked_employee_resolution_error"] = resolution_error
    if not employee and not linked_employee_id:
        enriched.update({
            "linked_employee_id": "",
            "linked_employee_no": "",
            "linked_employee_name": "",
            "linked_entity_id": "",
            "linked_entity_code": "",
            "linked_entity_name": "",
            "linked_department_id": "",
            "linked_department_code": "",
            "linked_department_name": "",
        })
        return enriched
    snapshot = employee_context_from_employee(employee) if employee else employee_link_snapshot(linked_employee_id)
    enriched.update({
        "linked_employee_id": snapshot.get("employee_id", linked_employee_id),
        "linked_employee_no": snapshot.get("employee_no", ""),
        "linked_employee_name": snapshot.get("employee_name", ""),
        "linked_entity_id": snapshot.get("entity_id", ""),
        "linked_entity_code": snapshot.get("entity_code", ""),
        "linked_entity_name": snapshot.get("entity_name", ""),
        "linked_department_id": snapshot.get("department_id", ""),
        "linked_department_code": snapshot.get("department_code", ""),
        "linked_department_name": snapshot.get("department_name", ""),
    })
    if snapshot.get("department") and not enriched.get("department"):
        enriched["department"] = snapshot["department"]
    return enriched


def user_persistable_data(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    cleaned.pop("linked_employee_number", None)
    cleaned.pop("_linked_employee_resolution_error", None)
    return cleaned


def user_employee_link_errors(messages: dict[str, str], data: dict[str, Any], current_user_id: str = "") -> list[str]:
    errors: list[str] = []
    user_type = str(data.get("user_type", "admin") or "admin")
    linked_employee_id = str(data.get("linked_employee_id", "") or "").strip()
    linked_employee_number = str(data.get("linked_employee_number", "") or "").strip()
    resolution_error = str(data.get("_linked_employee_resolution_error", "") or "")
    if user_type not in USER_TYPES:
        errors.append(t(messages, "validation.invalid_user_type", "Invalid user type."))
    if user_type == "employee" and not linked_employee_id and not linked_employee_number:
        errors.append(t(messages, "validation.linked_employee_required", "Employee-type users must be linked to an employee."))
    if resolution_error == "not_found":
        errors.append(t(messages, "validation.linked_employee_number_invalid", "Employee number was not found in EmployeeAdmin."))
    elif resolution_error == "ambiguous":
        errors.append(t(messages, "validation.linked_employee_number_ambiguous", "Employee number matches multiple employees. Please select the exact linked employee."))
    if linked_employee_id:
        employee = find_employeeadmin_employee(linked_employee_id)
        if not employee:
            errors.append(t(messages, "validation.linked_employee_invalid", "Linked employee was not found."))
        else:
            status = employee_status(employee).strip().lower()
            if status and status not in {"active", "probation", "onboarding"}:
                errors.append(t(messages, "validation.linked_employee_inactive", "Linked employee is not active."))
            for existing in load_users():
                if existing.get("status") == "deleted" or existing.get("deleted") or existing.get("user_id") == current_user_id:
                    continue
                if str(existing.get("status", "active")) != "active":
                    continue
                if str(existing.get("linked_employee_id", "") or "") == linked_employee_id:
                    errors.append(t(messages, "validation.linked_employee_duplicate", "This employee is already linked to another active user."))
                    break
    return errors


def sync_user_entity_mapping_for_employee(user_id: str, employee_snapshot: dict[str, str], actor: str) -> None:
    entity_id = str(employee_snapshot.get("entity_id", "") or "").strip()
    entity_code = str(employee_snapshot.get("entity_code", "") or "").strip()
    if not user_id or not entity_id or not entity_code:
        return
    mappings = load_user_entity_mappings()
    found = False
    before = [dict(mapping) for mapping in mappings if mapping.get("user_id") == user_id]
    for mapping in mappings:
        if mapping.get("user_id") != user_id:
            continue
        if str(mapping.get("entity_id", "")) == entity_id:
            mapping.update({
                "entity_code": entity_code,
                "entity_name_en": employee_snapshot.get("entity_name", mapping.get("entity_name_en", "")),
                "entity_name_ja": mapping.get("entity_name_ja", ""),
                "entity_name_zh": mapping.get("entity_name_zh", employee_snapshot.get("entity_name", "")),
                "is_default": True,
                "active": True,
                "assigned_by": actor,
            })
            found = True
        elif mapping.get("active", True):
            mapping["is_default"] = False
    if not found:
        mappings.append({
            "mapping_id": next_id(mappings, "mapping_id", "UEM-", 4),
            "user_id": user_id,
            "entity_id": entity_id,
            "entity_code": entity_code,
            "entity_name_en": employee_snapshot.get("entity_name", ""),
            "entity_name_ja": "",
            "entity_name_zh": employee_snapshot.get("entity_name", ""),
            "is_default": True,
            "active": True,
            "assigned_at": now_iso(),
            "assigned_by": actor,
        })
    save_user_entity_mappings(mappings)
    after = [dict(mapping) for mapping in mappings if mapping.get("user_id") == user_id]
    if before != after:
        append_audit("user_entity_mapping", user_id, actor, "sync_employee_entity", {"mappings": before}, {"mappings": after})


def active_user_role_keys(user_id: str) -> list[str]:
    roles_by_id = {role.get("role_id"): role for role in load_roles() if role.get("active", True)}
    keys: list[str] = []
    for mapping in load_user_role_mappings():
        if mapping.get("user_id") == user_id and mapping.get("active", True):
            role = roles_by_id.get(mapping.get("role_id"))
            if role:
                keys.append(str(role.get("role_key")))
    return sorted(set(keys))


def is_system_admin_user(user_id: str) -> bool:
    return "system_admin" in active_user_role_keys(user_id)


def entity_code_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def active_masterdata_entities() -> list[dict[str, Any]]:
    return [entity for entity in load_masterdata_entities() if str(entity.get("status", "active")) == "active"]


def find_active_entity_by_code(entity_code: str) -> dict[str, Any] | None:
    target = entity_code_key(entity_code)
    if not target:
        return None
    for entity in active_masterdata_entities():
        if entity_code_key(entity.get("entity_code")) == target:
            return entity
    return None


def entity_context_from_record(entity: dict[str, Any]) -> dict[str, str]:
    return {
        "entity_id": str(entity.get("entity_id", "")),
        "entity_code": str(entity.get("entity_code", "")),
        "entity_name_en": str(entity.get("entity_name_en", "")),
        "entity_name_ja": str(entity.get("entity_name_ja", "")),
        "entity_name_zh": str(entity.get("entity_name_zh") or entity.get("entity_name_en", "")),
    }


def active_entity_by_id(entity_id: str) -> dict[str, Any] | None:
    target = str(entity_id or "").strip()
    if not target:
        return None
    for entity in active_masterdata_entities():
        if str(entity.get("entity_id", "")) == target:
            return entity
    return None


def active_masterdata_departments() -> list[dict[str, Any]]:
    return [department for department in load_masterdata_departments() if str(department.get("status", "active")) == "active"]


def active_department_by_id(department_id: str) -> dict[str, Any] | None:
    target = str(department_id or "").strip()
    if not target:
        return None
    for department in active_masterdata_departments():
        if str(department.get("department_id", "")) == target:
            return department
    return None


def department_name_from_record(department: dict[str, Any]) -> str:
    return str(department.get("department_name_en") or department.get("department_name_ja") or department.get("department_name_zh") or "").strip()


def employee_number_from_record(employee: dict[str, Any]) -> str:
    return str(employee.get("employee_number") or employee.get("employee_no") or employee.get("employee_id") or "").strip()


def employee_entity_id(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.entity_id", "") or employee.get("entity_id") or "").strip()


def employee_display_name(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "profile.name.display_name", "") or employee.get("display_name") or "").strip()


def employee_email(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "profile.email", "") or employee.get("email") or "").strip()


def employee_department(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.department_id", "") or employee.get("department") or "").strip()


def employee_status(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.status", "") or employee.get("status") or "").strip()


def visible_employeeadmin_employees() -> list[dict[str, Any]]:
    return [employee for employee in load_employeeadmin_employees() if not bool(get_nested(employee, "metadata.deleted", False))]


def find_employeeadmin_employee(employee_id: str) -> dict[str, Any] | None:
    target = str(employee_id or "").strip()
    if not target:
        return None
    for employee in visible_employeeadmin_employees():
        if str(employee.get("employee_id", "")) == target:
            return employee
    return None


def employee_number_key(value: Any) -> str:
    return str(value or "").strip().casefold()


def find_employeeadmin_employee_by_number(employee_number: str, employee_id_hint: str = "") -> tuple[dict[str, Any] | None, str]:
    target = employee_number_key(employee_number)
    if not target:
        return None, ""
    matches = [employee for employee in visible_employeeadmin_employees() if employee_number_key(employee_number_from_record(employee)) == target]
    if not matches:
        return None, "not_found"
    if len(matches) == 1:
        return matches[0], ""
    hint = str(employee_id_hint or "").strip()
    if hint:
        for employee in matches:
            if str(employee.get("employee_id", "")) == hint:
                return employee, ""
    return None, "ambiguous"


def employee_context_from_employee(employee: dict[str, Any]) -> dict[str, str]:
    entity = active_entity_by_id(employee_entity_id(employee)) or {}
    department_id = employee_department(employee)
    department = active_department_by_id(department_id) or {}
    department_name = department_name_from_record(department) or department_id
    return {
        "employee_id": str(employee.get("employee_id", "")),
        "employee_no": employee_number_from_record(employee),
        "employee_number": employee_number_from_record(employee),
        "employee_name": employee_display_name(employee),
        "display_name": employee_display_name(employee),
        "email": employee_email(employee),
        "entity_id": employee_entity_id(employee),
        "entity_code": str(entity.get("entity_code", "")),
        "entity_name": str(entity.get("entity_name_en") or entity.get("entity_name_ja") or entity.get("entity_name_zh") or ""),
        "department": department_id,
        "department_id": department_id,
        "department_code": str(department.get("department_code", "")),
        "department_name": department_name,
        "employment_status": employee_status(employee),
    }


def employee_link_snapshot(employee_id: str) -> dict[str, str]:
    employee = find_employeeadmin_employee(employee_id)
    return employee_context_from_employee(employee) if employee else {}


def entity_context_from_session(session: dict[str, Any] | None) -> dict[str, str]:
    if not session:
        return {}
    entity_id = str(session.get("entity_id", "")).strip()
    entity_code = str(session.get("entity_code", "")).strip()
    if not entity_id or not entity_code:
        return {}
    return {
        "entity_id": entity_id,
        "entity_code": entity_code,
        "entity_name_en": str(session.get("entity_name_en", "")),
        "entity_name_ja": str(session.get("entity_name_ja", "")),
        "entity_name_zh": str(session.get("entity_name_zh", "")),
    }


def active_user_entity_assignments(user_id: str) -> list[dict[str, Any]]:
    return [mapping for mapping in load_user_entity_mappings() if mapping.get("user_id") == user_id and mapping.get("active", True)]


def user_has_entity_assignment(user_id: str, entity_code: str) -> bool:
    target = entity_code_key(entity_code)
    return any(entity_code_key(mapping.get("entity_code")) == target for mapping in active_user_entity_assignments(user_id))


def validate_login_entity(user: dict[str, Any], entity_code: str, messages: dict[str, str]) -> tuple[dict[str, str] | None, list[str]]:
    normalized_entity_code = str(entity_code or "").strip()
    if not normalized_entity_code:
        return None, [t(messages, "validation.entity_code_required")]
    entity = find_active_entity_by_code(normalized_entity_code)
    if not entity:
        return None, [t(messages, "validation.invalid_entity_code")]
    user_id = str(user.get("user_id", ""))
    if not is_system_admin_user(user_id) and not user_has_entity_assignment(user_id, normalized_entity_code):
        return None, [t(messages, "validation.entity_assignment_required")]
    return entity_context_from_record(entity), []


def session_has_active_entity(session: dict[str, Any]) -> bool:
    context = entity_context_from_session(session)
    if not context:
        return False
    entity = find_active_entity_by_code(context.get("entity_code", ""))
    return bool(entity and str(entity.get("entity_id", "")) == context.get("entity_id"))


def effective_permissions(user_id: str) -> list[str]:
    role_keys = active_user_role_keys(user_id)
    permission_by_id = {permission.get("permission_id"): permission for permission in load_permissions()}
    if "system_admin" in role_keys:
        configured = {str(permission.get("permission_key")) for permission in permission_by_id.values() if permission.get("active", True)}
        seeded = {permission[0] for permission in PERMISSION_DEFINITIONS}
        return sorted(configured | seeded)
    roles = {role.get("role_id"): role for role in load_roles()}
    effective: set[str] = set()
    for mapping in load_role_permission_mappings():
        if not mapping.get("active", True):
            continue
        role = roles.get(mapping.get("role_id"))
        if not role or role.get("role_key") not in role_keys:
            continue
        permission = permission_by_id.get(mapping.get("permission_id"))
        if permission:
            effective.add(str(permission.get("permission_key")))
    return sorted(effective)


def user_context(user: dict[str, Any], session: dict[str, Any] | None = None) -> dict[str, Any]:
    user_id = str(user.get("user_id", ""))
    employee_context = employee_link_snapshot(str(user.get("linked_employee_id", "")))
    legacy_employee_no = str(user.get("linked_employee_no") or user.get("employee_no") or "")
    legacy_employee_name = str(user.get("linked_employee_name") or user.get("employee_name") or user.get("display_name", ""))
    context = {
        "user_id": user_id,
        "username": user.get("username", ""),
        "display_name": user.get("display_name", ""),
        "email": user.get("email", ""),
        "user_type": user.get("user_type", "admin"),
        "linked_employee_id": user.get("linked_employee_id", ""),
        "employee_id": employee_context.get("employee_id", user.get("linked_employee_id", "")),
        "employee_no": employee_context.get("employee_no", legacy_employee_no),
        "employee_number": employee_context.get("employee_number", legacy_employee_no),
        "employee_name": employee_context.get("employee_name", legacy_employee_name),
        "department": employee_context.get("department", user.get("department", "")),
        "department_id": employee_context.get("department_id", user.get("linked_department_id", "")),
        "department_code": employee_context.get("department_code", user.get("linked_department_code", "")),
        "department_name": employee_context.get("department_name", user.get("linked_department_name", "")),
        "employee_context": employee_context,
        "language_preference": user.get("language_preference", DEFAULT_LANG),
        "roles": active_user_role_keys(user_id),
        "permissions": effective_permissions(user_id),
    }
    entity = entity_context_from_session(session)
    if entity:
        context["entity"] = entity
        context["entity_id"] = entity["entity_id"]
        context["entity_code"] = entity["entity_code"]
        context["entity_name"] = entity.get("entity_name_en", "")
    elif employee_context.get("entity_id"):
        context["entity_id"] = employee_context.get("entity_id", "")
        context["entity_code"] = employee_context.get("entity_code", "")
        context["entity_name"] = employee_context.get("entity_name", "")
    return context


def session_context(session: dict[str, Any] | None) -> dict[str, Any]:
    if not session:
        return {}
    return {
        "session_id_suffix": str(session.get("session_id", ""))[-8:],
        "login_time": session.get("login_time", ""),
        "login_time_jst": format_jst(str(session.get("login_time", ""))),
        "logout_time": session.get("logout_time", ""),
        "logout_time_jst": format_jst(str(session.get("logout_time", ""))),
        "expires_at": session.get("expires_at", ""),
        "expires_at_jst": format_jst(str(session.get("expires_at", ""))),
        "ip_address": session.get("ip_address", ""),
        "browser": session.get("browser", ""),
        "device": session.get("device", ""),
        "active": bool(session.get("active", True)),
        "entity": entity_context_from_session(session),
        "current_module_key": session.get("current_module_key", ""),
        "current_module_path": session.get("current_module_path", ""),
        "current_module_opened_at": session.get("current_module_opened_at", ""),
        "current_module_opened_at_jst": format_jst(str(session.get("current_module_opened_at", ""))),
        "last_seen_at": session.get("last_seen_at", ""),
        "last_seen_at_jst": format_jst(str(session.get("last_seen_at", ""))),
        "last_activity_source": session.get("last_activity_source", ""),
    }


def can_view_all_sessions(user: dict[str, Any] | None) -> bool:
    return bool(user and "system_admin" in active_user_role_keys(str(user.get("user_id", ""))))


def sanitize_module_key(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyz0123456789_-." )
    normalized = str(value or "").strip().lower().replace(" ", "_")
    return "".join(char for char in normalized if char in allowed)[:64]


def sanitize_module_path(value: str) -> str:
    raw_value = str(value or "").strip()
    if not raw_value:
        return ""
    parsed = urlparse(raw_value)
    path_value = parsed.path or raw_value.split("?", 1)[0]
    if path_value and not path_value.startswith("/"):
        path_value = "/" + path_value
    return path_value[:160]


def module_display_name(module_key: str, messages: dict[str, str]) -> str:
    module_key = sanitize_module_key(module_key)
    if not module_key:
        return t(messages, "session.no_module", "Not reported")
    fallback = module_key.replace("_", " ").replace("-", " ").title()
    return t(messages, f"module.{module_key}", fallback)


def record_session_activity(session_id: str, module_key: str = "", module_path: str = "", source: str = "") -> dict[str, Any]:
    session_id = str(session_id or "").strip()
    if not session_id:
        return {}
    clean_module_key = sanitize_module_key(module_key)
    clean_module_path = sanitize_module_path(module_path)
    source_text = sanitize_module_key(source) or "session_activity"
    now_text = now_iso()
    now_dt = parse_iso(now_text)
    sessions = load_sessions()
    updated_session: dict[str, Any] = {}
    audit_payload: tuple[dict[str, Any], dict[str, Any], str, str] | None = None
    for session in sessions:
        if session.get("session_id") != session_id:
            continue
        expires_at = parse_iso(str(session.get("expires_at", "")))
        if not session.get("active", True) or (expires_at and now_dt and expires_at <= now_dt):
            break
        before_module = str(session.get("current_module_key", "") or "")
        before_path = str(session.get("current_module_path", "") or "")
        session["last_seen_at"] = now_text
        session["last_activity_source"] = source_text
        if clean_module_key:
            module_changed = before_module != clean_module_key
            path_changed = before_path != clean_module_path
            if module_changed or path_changed or not session.get("current_module_opened_at"):
                before_value = {
                    "session_id_suffix": str(session.get("session_id", ""))[-8:],
                    "current_module_key": before_module,
                    "current_module_path": before_path,
                }
                session["current_module_key"] = clean_module_key
                session["current_module_path"] = clean_module_path
                if module_changed or not session.get("current_module_opened_at"):
                    session["current_module_opened_at"] = now_text
                if module_changed:
                    after_value = {
                        "session_id_suffix": str(session.get("session_id", ""))[-8:],
                        "current_module_key": clean_module_key,
                        "current_module_path": clean_module_path,
                        "current_module_opened_at": session.get("current_module_opened_at", ""),
                    }
                    audit_user = actor_label(find_user_by_id(str(session.get("user_id", ""))))
                    audit_payload = (before_value, after_value, str(session.get("user_id", "")), audit_user)
        updated_session = dict(session)
        break
    if updated_session:
        save_sessions(sessions)
        if audit_payload:
            before_value, after_value, record_id, audit_user = audit_payload
            append_audit("user_management", record_id, audit_user, "session_module_opened", before_value, after_value)
    return session_context(updated_session)


def append_audit(module: str, record_id: str, user: str, action: str, before_value: Any, after_value: Any) -> None:
    logs = load_audit_logs()
    logs.append(
        {
            "audit_id": next_id(logs, "audit_id", "AUD-", 6),
            "module": module,
            "record_id": record_id,
            "user": user,
            "action": action,
            "timestamp": now_iso(),
            "before_value": before_value,
            "after_value": after_value,
        }
    )
    save_audit_logs(logs)


def seed_data() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    roles = [
        {
            **role,
            "active": True,
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        for role in ROLE_DEFINITIONS
    ]
    if not load_roles():
        save_json_array(ROLES_PATH, roles)

    permissions = [
        {
            "permission_id": f"PERM-{index:04d}",
            "permission_key": key,
            "module": module,
            "action": action,
            "description": key.replace("_", " ").replace(".", " / ").title(),
            "active": True,
        }
        for index, (key, module, action) in enumerate(PERMISSION_DEFINITIONS, start=1)
    ]
    if not load_permissions():
        save_json_array(PERMISSIONS_PATH, permissions)

    if not load_role_permission_mappings():
        role_by_key = {role["role_key"]: role["role_id"] for role in roles}
        permission_by_key = {permission["permission_key"]: permission["permission_id"] for permission in permissions}
        mappings: list[dict[str, Any]] = []
        counter = 1
        for role_key, permission_keys in ROLE_PERMISSION_KEYS.items():
            keys = list(permission_by_key) if permission_keys == "*" else list(permission_keys)
            for permission_key in keys:
                if permission_key not in permission_by_key:
                    continue
                mappings.append(
                    {
                        "mapping_id": f"RPM-{counter:04d}",
                        "role_id": role_by_key[role_key],
                        "permission_id": permission_by_key[permission_key],
                        "active": True,
                    }
                )
                counter += 1
        save_json_array(ROLE_PERMISSION_MAPPING_PATH, mappings)

    if not load_users():
        timestamp = now_iso()
        admin = {
            "user_id": "USR-0001",
            "username": "admin",
            "display_name": "System Admin",
            "email": INITIAL_ADMIN_EMAIL,
            "phone": "",
            "department": "System",
            "position": "System Admin",
            "status": "active",
            "language_preference": "en",
            "password_hash": INITIAL_ADMIN_PASSWORD_HASH,
            "password_last_changed": timestamp,
            "last_login": "",
            "failed_login_count": 0,
            "account_locked": False,
            "account_locked_date": "",
            "created_at": timestamp,
            "updated_at": timestamp,
            "deleted": False,
        }
        save_users([admin])
        save_json_array(
            USER_ROLE_MAPPING_PATH,
            [
                {
                    "mapping_id": "URM-0001",
                    "user_id": "USR-0001",
                    "role_id": "ROLE-SYSTEM-ADMIN",
                    "assigned_at": timestamp,
                    "assigned_by": SYSTEM_USER,
                    "active": True,
                }
            ],
        )
        append_audit("user_management", "USR-0001", SYSTEM_USER, "bootstrap_admin_created", {}, {"user_id": "USR-0001", "email": INITIAL_ADMIN_EMAIL})

    if not USER_ENTITY_MAPPING_PATH.exists():
        active_entities = active_masterdata_entities()
        default_entity = active_entities[0] if active_entities else None
        mappings: list[dict[str, Any]] = []
        if default_entity:
            entity_context = entity_context_from_record(default_entity)
            counter = 1
            for user in load_users():
                if user.get("status") != "active" or user.get("deleted") or user.get("account_locked"):
                    continue
                mappings.append(
                    {
                        "mapping_id": f"UEM-{counter:04d}",
                        "user_id": str(user.get("user_id", "")),
                        **entity_context,
                        "is_default": True,
                        "active": True,
                        "assigned_at": now_iso(),
                        "assigned_by": SYSTEM_USER,
                    }
                )
                counter += 1
        save_user_entity_mappings(mappings)

    for path in (USER_SESSIONS_PATH, USER_AUDIT_LOGS_PATH):
        if not path.exists():
            save_json_array(path, [])


def active_sessions() -> list[dict[str, Any]]:
    now = datetime.now(timezone.utc)
    sessions = []
    changed = False
    for session in load_sessions():
        expires_at = parse_iso(str(session.get("expires_at", "")))
        if session.get("active", True) and expires_at and expires_at <= now:
            session["active"] = False
            session["logout_time"] = session.get("logout_time") or now_iso()
            changed = True
        sessions.append(session)
    if changed:
        save_sessions(sessions)
    return sessions


def validate_session_id(session_id: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not session_id:
        return None, None
    now = datetime.now(timezone.utc)
    for session in active_sessions():
        if session.get("session_id") != session_id or not session.get("active", True):
            continue
        expires_at = parse_iso(str(session.get("expires_at", "")))
        if not expires_at or expires_at <= now:
            return None, None
        user = find_user_by_id(str(session.get("user_id", "")))
        if not user or user.get("status") != "active" or user.get("account_locked"):
            return None, None
        if not session_has_active_entity(session):
            return None, None
        return session, user
    return None, None


def render_page(title: str, body: str, lang: str, messages: dict[str, str], current_user: dict[str, Any] | None = None, current_url: str = "/", current_session: dict[str, Any] | None = None) -> bytes:
    parsed_current = urlparse(current_url or "/")
    query = parse_qs(parsed_current.query)
    notice = query.get("notice", [""])[0]
    notice_html = f'<div class="message-strip message-success" role="status">{h(notice)}</div>' if notice else ""
    user_html = ""
    if current_user:
        session = session_context(current_session)
        account = current_user.get("username") or current_user.get("email") or current_user.get("display_name")
        display_name = current_user.get("display_name") or account
        entity_code = session.get("entity", {}).get("entity_code") or current_user.get("entity_code", "")
        login_time = session.get("login_time_jst", "")
        user_html = f"""
        <div class=\"current-user-chip\" title=\"{h(t(messages, 'session.login_time'))}: {h(login_time)}\">
          <strong>👤 {h(account)}</strong>
          <span>{h(display_name)}{(' · ' + h(entity_code)) if entity_code else ''}</span>
          <small>{h(t(messages, 'session.login_time'))}: {h(login_time or '-')}</small>
        </div>
        <form method=\"post\" action=\"{h(url_with_lang('/logout', lang))}\"><button type=\"submit\" class=\"link-button\">{h(t(messages, 'nav.logout'))}</button></form>
        """
    portal_nav_html = (
        f'<a class="portal-link" href="{h(PORTAL_PUBLIC_BASE_URL)}" title="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" '
        f'aria-label="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{h(t(messages, "nav.portal", "Back to Portal"))}</a>'
    )
    nav = f"""
<header class="site-header">
  <div>
    <h1>{h(t(messages, 'app.title'))}</h1>
    <p class="muted">{h(t(messages, 'app.subtitle'))}</p>
  </div>
  <nav>
    {portal_nav_html}
    <a href="{h(url_with_lang('/dashboard', lang))}">{h(t(messages, 'nav.dashboard'))}</a>
    <a href="{h(url_with_lang('/users', lang))}">{h(t(messages, 'nav.users'))}</a>
    <a href="{h(url_with_lang('/roles', lang))}">{h(t(messages, 'nav.roles'))}</a>
    <a href="{h(url_with_lang('/audit-logs', lang))}">{h(t(messages, 'nav.audit_logs'))}</a>
    <a href="{h(url_with_lang('/login-sessions', lang))}">{h(t(messages, 'nav.login_sessions'))}</a>
    <a href="{h(url_with_lang('/change-password', lang))}">{h(t(messages, 'nav.change_password'))}</a>
  </nav>
  <div class="top-actions">{user_html}<span>{h(t(messages, 'nav.language'))}</span><a href="?lang=en">English</a><a href="?lang=ja">日本語</a><a href="?lang=zh">中文</a></div>
</header>
"""
    html = f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{ --navy: #14213d; --blue: #1f6feb; --bg: #f6f8fb; --card: #ffffff; --line: #d8dee9; --muted: #65758b; --green: #0f766e; --amber: #b45309; --red: #b91c1c; }}
    * {{ box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 0; background: var(--bg); color: #17202a; }}
    main, .site-header {{ max-width: 1180px; margin: 0 auto; }}
    main {{ padding: 1.5rem; }}
    .site-header {{ padding: 1.25rem 1.5rem; background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); border-bottom: 1px solid var(--line); display: grid; gap: 1rem; }}
    .site-header h1 {{ margin: 0; color: var(--navy); }}
    nav, .top-actions, .actions {{ display: flex; gap: .75rem; flex-wrap: wrap; align-items: center; }}
    nav a {{ color: var(--navy); text-decoration: none; border: 1px solid var(--line); padding: 8px 12px; border-radius: 999px; font-weight: 800; background: white; }}
    nav a:hover {{ border-color: var(--blue); color: var(--blue); text-decoration: none; }}
    nav a.portal-link {{ display: inline-flex; align-items: center; gap: 0.35rem; color: #0b4f8a; background: linear-gradient(180deg, #f8fbff 0%, #eaf4ff 100%); border-color: #9cc7f2; box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 1px 2px rgba(15,23,42,.08); }}
    nav a.portal-link:hover {{ color: #064b86; border-color: #1f6feb; background: #ffffff; }}
    .portal-icon {{ font-size: 1rem; line-height: 1; }}
    a {{ color: var(--blue); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .card, .sap-section {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 1.25rem; margin-bottom: 1rem; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .sap-page-header {{ background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); border: 1px solid var(--line); border-radius: 16px; padding: 20px; margin-bottom: 18px; }}
    .sap-toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; justify-content: flex-end; align-items: center; padding-top: 14px; border-top: 1px solid var(--line); margin-top: 16px; }}
    .grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }}
    .metric {{ font-size: 2rem; font-weight: 850; margin: .25rem 0; color: var(--navy); }}
    .muted {{ color: var(--muted); }}
    label {{ display: block; font-weight: 800; margin-bottom: .35rem; color: #334155; }}
    input, select {{ box-sizing: border-box; width: 100%; padding: .68rem .72rem; border: 1px solid #cbd5e1; border-radius: 9px; font: inherit; }}
    input[type="checkbox"] {{ width: auto; }}
    input:focus, select:focus {{ outline: 3px solid rgba(31, 111, 235, 0.18); border-color: var(--blue); }}
    .form-grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .form-field {{ margin-bottom: 1rem; }}
    .checkbox-grid {{ display: grid; gap: .5rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .checkbox-item {{ border: 1px solid #e5e7eb; border-radius: 10px; padding: .65rem; background: #f8fafc; }}
    .checkbox-item label {{ display: flex; gap: .5rem; align-items: flex-start; margin: 0; }}
    .button, button {{ background: var(--blue); color: #fff; border: 0; border-radius: 9px; padding: .68rem .95rem; cursor: pointer; text-decoration: none; display: inline-block; font-weight: 800; }}
    .button.light {{ background: #e5e7eb; color: #111827; }}
    .button.danger, button.danger {{ background: var(--red); }}
    .link-button {{ background: transparent; color: var(--blue); padding: 0; }}
    .current-user-chip {{ display: grid; gap: 2px; min-width: 190px; padding: 8px 10px; background: #fff; border: 1px solid #d6e4f2; border-radius: 12px; box-shadow: 0 1px 2px rgba(15,23,42,.04); color: var(--navy); }}
    .current-user-chip strong {{ font-size: .92rem; }}
    .current-user-chip span, .current-user-chip small {{ color: var(--muted); font-size: .78rem; }}
    .wide, .table-scroll {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; background: white; }}
    table {{ width: 100%; border-collapse: collapse; background: white; }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: .72rem; text-align: left; vertical-align: top; }}
    th {{ background: #eef4ff; color: var(--navy); }}
    .errors, .message-strip {{ background: #fef2f2; border: 1px solid #fecaca; border-left: 4px solid var(--red); color: #991b1b; border-radius: 10px; padding: 1rem; }}
    .message-success {{ background: #ecfdf5; border-color: #bbf7d0; border-left-color: var(--green); color: #14532d; }}
    .message-warning {{ background: #fffbeb; border-color: #fde68a; border-left-color: var(--amber); color: #92400e; }}
    .sap-confirm-backdrop {{ position: fixed; inset: 0; background: rgba(15,23,42,.48); display: none; align-items: center; justify-content: center; padding: 1rem; z-index: 50; }}
    .sap-confirm-backdrop.active {{ display: flex; }}
    .sap-confirm-dialog {{ width: min(460px, 100%); background: white; border-radius: 18px; border: 1px solid var(--line); box-shadow: 0 24px 80px rgba(15,23,42,.28); padding: 1.2rem; }}
    .badge, .status-badge {{ display: inline-block; border-radius: 999px; background: #e0f2fe; color: #075985; padding: .24rem .6rem; font-size: .85rem; font-weight: 800; }}
    @media (max-width: 720px) {{
      main {{ padding: 1rem .75rem 2rem; }}
      .site-header {{ padding: 1rem; }}
      nav {{ overflow-x: auto; flex-wrap: nowrap; padding-bottom: 4px; }}
      nav a {{ flex: 0 0 auto; min-height: 42px; white-space: nowrap; }}
      .top-actions {{ align-items: stretch; flex-direction: column; }}
      .top-actions form, .top-actions button, .top-actions .button {{ width: 100%; }}
      .grid, .form-grid, .checkbox-grid {{ grid-template-columns: 1fr; }}
      .actions, .sap-toolbar {{ align-items: stretch; flex-direction: column; }}
      .actions .button, .actions button, .sap-toolbar .button, .sap-toolbar button {{ width: 100%; text-align: center; }}
      .message-strip {{ font-size: .98rem; line-height: 1.45; padding: .95rem 1rem; border-radius: 12px; margin-bottom: 1rem; }}
      table {{ display: block; overflow-x: auto; min-width: 720px; }}
    }}
  </style>
</head>
<body>
  {nav}
  <main>{notice_html}{body}</main>
  <div class="sap-confirm-backdrop" id="sapConfirmBackdrop" aria-hidden="true"><div class="sap-confirm-dialog" role="dialog" aria-modal="true"><h3>{h(t(messages, 'confirm.title', 'Confirm action'))}</h3><p>{h(t(messages, 'confirm.delete_message', 'Please confirm this deactivate action.'))}</p><div class="actions"><button type="button" class="danger" id="sapConfirmOk">{h(t(messages, 'confirm.ok', 'Confirm'))}</button><button type="button" class="button light" id="sapConfirmCancel">{h(t(messages, 'confirm.cancel', 'Cancel'))}</button></div></div></div>
  <script>
  (() => {{ const backdrop = document.getElementById('sapConfirmBackdrop'); const ok = document.getElementById('sapConfirmOk'); const cancel = document.getElementById('sapConfirmCancel'); let pendingForm = null; document.addEventListener('submit', (event) => {{ const form = event.target; if (!form || !form.action || !form.action.includes('deactivate')) return; event.preventDefault(); pendingForm = form; backdrop.classList.add('active'); ok.focus(); }}); ok.addEventListener('click', () => {{ if (pendingForm) {{ const f = pendingForm; pendingForm = null; f.submit(); }} }}); cancel.addEventListener('click', () => {{ pendingForm = null; backdrop.classList.remove('active'); }}); backdrop.addEventListener('click', (event) => {{ if (event.target === backdrop) cancel.click(); }}); }})();
  </script>
</body>
</html>"""
    return html.encode("utf-8")


class UserAdminHandler(BaseHTTPRequestHandler):
    server_version = "TACAIUserAdmin/0.1"

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        return origin_allowed(source or "")

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        messages = load_i18n(lang)
        path = parsed.path
        session, user = self.current_session_user()

        if path == "/health":
            self.send_text(200, "OK")
        elif path in {"/", "/login"}:
            next_url = safe_next_url(query.get("next", [""])[0], url_with_lang("/dashboard", lang))
            if user:
                self.redirect(next_url)
            else:
                self.send_login(lang, messages, [], next_url)
        elif path == "/dashboard":
            self.require_user_or_login(lang, messages, user) and self.send_dashboard(lang, messages, user)
        elif path == "/users":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.send_users(lang, messages, user)
        elif path == "/users/new":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.send_user_form(lang, messages, user, "create", {}, [], [])
        elif path == "/users/edit":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.send_edit_user_form(lang, messages, user, query)
        elif path == "/roles":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_roles") and self.send_roles(lang, messages, user)
        elif path == "/roles/permissions":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_permissions") and self.send_role_permissions(lang, messages, user, query, [])
        elif path == "/audit-logs":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.audit.view") and self.send_audit_logs(lang, messages, user)
        elif path == "/login-sessions":
            self.require_user_or_login(lang, messages, user) and self.send_login_sessions(lang, messages, user, query)
        elif path == "/change-password":
            self.require_user_or_login(lang, messages, user) and self.send_change_password(lang, messages, user, [])
        elif path == "/api/current-user":
            self.send_json(200 if user else 401, {"authenticated": bool(user), "user": user_context(user, session) if user else None, "session": session_context(session) if user else None})
        elif path == "/api/roles":
            self.send_json(200, load_roles())
        elif path == "/api/permissions":
            self.send_json(200, load_permissions())
        else:
            self.send_not_found(lang, messages, user)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        messages = load_i18n(lang)
        if not self.csrf_origin_allowed():
            self.send_forbidden(lang, messages, self.current_session_user()[1])
            return
        path = parsed.path
        _session, user = self.current_session_user()

        if path == "/login":
            self.handle_login(lang, messages, query.get("next", [""])[0])
        elif path == "/logout":
            self.handle_logout(lang, messages, user, query.get("next", [""])[0])
        elif path == "/change-password":
            self.require_user_or_login(lang, messages, user) and self.handle_change_password(lang, messages, user)
        elif path == "/users/create":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.handle_create_user(lang, messages, user)
        elif path == "/users/update":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.handle_update_user(lang, messages, user)
        elif path == "/users/deactivate":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_users") and self.handle_deactivate_user(lang, messages, user)
        elif path == "/roles/permissions":
            self.require_permission_or_forbidden(lang, messages, user, "user_management.manage_permissions") and self.handle_update_role_permissions(lang, messages, user)
        elif path == "/api/validate-session":
            self.handle_api_validate_session()
        elif path == "/api/check-permission":
            self.handle_api_check_permission()
        elif path == "/api/check-role":
            self.handle_api_check_role()
        elif path == "/api/check-module-access":
            self.handle_api_check_module_access()
        else:
            self.send_not_found(lang, messages, user)

    def current_session_user(self) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        session_id = morsel.value if morsel else ""
        return validate_session_id(session_id)

    def parse_form_body(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(body, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def parse_form_multi_body(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        return parse_qs(body, keep_blank_values=True)

    def parse_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if not length:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def require_user_or_login(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None) -> bool:
        if user:
            return True
        self.redirect(url_with_lang("/login", lang, {"next": self.path}))
        return False

    def require_permission_or_forbidden(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None, permission_key: str) -> bool:
        if not self.require_user_or_login(lang, messages, user):
            return False
        if permission_key in effective_permissions(str(user.get("user_id"))):
            return True
        self.send_forbidden(lang, messages, user)
        return False

    def send_login(self, lang: str, messages: dict[str, str], errors: list[str], next_url: str = "", entity_code: str = "TAKK", email: str = "") -> None:
        error_html = self.render_errors(messages, errors)
        login_action = url_with_lang("/login", lang, {"next": next_url})
        next_field = f'<input type="hidden" name="next" value="{h(next_url)}">' if next_url else ""
        active_entities = active_masterdata_entities()
        entity_options = []
        entity_select_options = []
        entity_codes = []
        for entity in active_entities:
            code = str(entity.get("entity_code", "")).strip()
            if not code:
                continue
            entity_codes.append(code)
            name = str(entity.get(f"entity_name_{lang}") or entity.get("entity_name_en") or entity.get("entity_name_ja") or "").strip()
            label = f"{code} - {name}" if name else code
            entity_options.append(f'<option value="{h(code)}" label="{h(label)}"></option>')
            entity_select_options.append(f'<option value="{h(code)}">{h(label)}</option>')
        selected_entity_code = str(entity_code or "").strip() or "TAKK"
        entity_codes_json = json.dumps(entity_codes, ensure_ascii=False)
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'login.title'))}</h2>
  <p class="muted">{h(t(messages, 'login.description'))}</p>
  {error_html}
  <form id="login_form" method="post" action="{h(login_action)}">
    {next_field}
    <div class="form-field"><label for="entity_code_select">{h(t(messages, 'field.entity_code'))}</label><select id="entity_code_select"><option value="">--</option>{''.join(entity_select_options)}</select></div>
    <div class="form-field"><label for="entity_code">{h(t(messages, 'field.entity_code_manual'))}</label><input id="entity_code" name="entity_code" value="{h(selected_entity_code)}" list="entity_code_options" required placeholder="TAKK" autocomplete="organization"><datalist id="entity_code_options">{''.join(entity_options)}</datalist><p class="muted">{h(t(messages, 'login.entity_help'))}</p></div>
    <div class="form-field"><label for="email">{h(t(messages, 'field.email'))}</label><input id="email" name="email" type="email" value="{h(email)}" required autocomplete="username"></div>
    <div class="form-field"><label for="password">{h(t(messages, 'field.password'))}</label><input id="password" name="password" type="password" required autocomplete="current-password"></div>
    <button type="submit">{h(t(messages, 'login.submit'))}</button>
  </form>
</section>
<script>
(() => {{
  const storageKey = 'tacai_user_admin_last_entity_by_email';
  const fallbackEntity = 'TAKK';
  const activeEntityCodes = {entity_codes_json};
  const form = document.getElementById('login_form');
  const emailInput = document.getElementById('email');
  const entityInput = document.getElementById('entity_code');
  const entitySelect = document.getElementById('entity_code_select');
  if (!form || !emailInput || !entityInput || !entitySelect) return;

  function loadMap() {{
    try {{
      const parsed = JSON.parse(localStorage.getItem(storageKey) || '{{}}');
      return parsed && typeof parsed === 'object' ? parsed : {{}};
    }} catch (_error) {{
      return {{}};
    }}
  }}

  function saveMap(value) {{
    try {{
      localStorage.setItem(storageKey, JSON.stringify(value));
    }} catch (_error) {{
      // Ignore storage failures; server-side validation remains authoritative.
    }}
  }}

  function normalizedEmail() {{
    return (emailInput.value || '').trim().toLowerCase();
  }}

  function canonicalEntityCode(value) {{
    const requested = (value || '').trim().toLowerCase();
    if (!requested) return '';
    for (const code of activeEntityCodes) {{
      if (String(code).toLowerCase() === requested) return String(code);
    }}
    return '';
  }}

  function setEntity(value) {{
    const canonical = canonicalEntityCode(value) || (value || '').trim();
    entityInput.value = canonical || fallbackEntity;
    entitySelect.value = canonicalEntityCode(canonical) || '';
  }}

  function fillEntityFromEmail() {{
    const email = normalizedEmail();
    if (!email) {{
      if (!entityInput.value.trim()) setEntity(fallbackEntity);
      return;
    }}
    const storedEntity = canonicalEntityCode(loadMap()[email]);
    if (storedEntity) {{
      setEntity(storedEntity);
    }} else if (!entityInput.value.trim()) {{
      setEntity(fallbackEntity);
    }} else {{
      setEntity(entityInput.value);
    }}
  }}

  entitySelect.addEventListener('change', () => {{
    if (entitySelect.value) setEntity(entitySelect.value);
  }});
  entityInput.addEventListener('change', () => setEntity(entityInput.value));
  entityInput.addEventListener('blur', () => setEntity(entityInput.value));
  emailInput.addEventListener('change', fillEntityFromEmail);
  emailInput.addEventListener('blur', fillEntityFromEmail);
  form.addEventListener('submit', () => {{
    const email = normalizedEmail();
    const entityCode = canonicalEntityCode(entityInput.value);
    if (!email || !entityCode) return;
    const map = loadMap();
    map[email] = entityCode;
    saveMap(map);
  }});

  if (!entityInput.value.trim()) setEntity(fallbackEntity);
  setEntity(entityInput.value);
  if (emailInput.value.trim() && entityInput.value.trim() === fallbackEntity) fillEntityFromEmail();
}})();
</script>
"""
        self.send_html(200, t(messages, "login.title"), body, lang, messages, None)

    def handle_login(self, lang: str, messages: dict[str, str], next_url: str = "") -> None:
        form = self.parse_form_body()
        requested_next = form.get("next", next_url)
        redirect_url = safe_next_url(requested_next, url_with_lang("/dashboard", lang))
        entity_code = form.get("entity_code", "").strip()
        email = form.get("email", "").strip().lower()
        password = form.get("password", "")
        user = find_user_by_email(email)
        if not user:
            append_audit("user_management", email, "anonymous", "login_failed", {}, {"reason": "user_not_found"})
            self.send_login(lang, messages, [t(messages, "validation.invalid_login")], redirect_url, entity_code, email)
            return
        if user.get("account_locked") or user.get("status") in {"locked", "suspended", "inactive"}:
            append_audit("user_management", str(user.get("user_id")), str(user.get("email")), "login_blocked", {}, {"status": user.get("status")})
            self.send_login(lang, messages, [t(messages, "validation.account_locked")], redirect_url, entity_code, email)
            return
        if not verify_password(password, str(user.get("password_hash", ""))):
            self.record_failed_login(user)
            self.send_login(lang, messages, [t(messages, "validation.invalid_login")], redirect_url, entity_code, email)
            return
        entity_context, entity_errors = validate_login_entity(user, entity_code, messages)
        if entity_errors or not entity_context:
            append_audit("user_management", str(user.get("user_id")), str(user.get("email")), "login_blocked", {}, {"reason": "invalid_entity", "entity_code": entity_code})
            self.send_login(lang, messages, entity_errors, redirect_url, entity_code, email)
            return
        self.record_successful_login(user)
        session_id = secrets.token_urlsafe(32)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=SESSION_TIMEOUT_MINUTES)
        sessions = load_sessions()
        sessions.append(
            {
                "session_id": session_id,
                "user_id": user["user_id"],
                **entity_context,
                "login_time": now_iso(),
                "logout_time": "",
                "ip_address": self.client_address[0] if self.client_address else "",
                "browser": self.headers.get("User-Agent", ""),
                "device": self.headers.get("User-Agent", ""),
                "active": True,
                "expires_at": expires_at.isoformat(),
                "current_module_key": "user_management",
                "current_module_path": sanitize_module_path(urlparse(redirect_url).path or "/dashboard"),
                "current_module_opened_at": now_iso(),
                "last_seen_at": now_iso(),
                "last_activity_source": "login",
            }
        )
        save_sessions(sessions)
        append_audit("user_management", str(user.get("user_id")), str(user.get("email")), "user_login", {}, {"session_id": session_id, "entity": entity_context})
        self.send_response(303)
        self.send_header("Location", redirect_url)
        self.send_header("Set-Cookie", session_cookie_header(session_id))
        self.end_headers()

    def record_failed_login(self, user: dict[str, Any]) -> None:
        users = load_users()
        before = {"failed_login_count": user.get("failed_login_count", 0), "account_locked": user.get("account_locked", False)}
        for record in users:
            if record.get("user_id") == user.get("user_id"):
                failed_count = int(record.get("failed_login_count", 0)) + 1
                record["failed_login_count"] = failed_count
                if failed_count >= MAX_FAILED_LOGINS:
                    record["account_locked"] = True
                    record["account_locked_date"] = now_iso()
                    record["status"] = "locked"
                record["updated_at"] = now_iso()
                after = {"failed_login_count": record.get("failed_login_count"), "account_locked": record.get("account_locked")}
                save_users(users)
                append_audit("user_management", str(record.get("user_id")), str(record.get("email")), "login_failed", before, after)
                return

    def record_successful_login(self, user: dict[str, Any]) -> None:
        users = load_users()
        for record in users:
            if record.get("user_id") == user.get("user_id"):
                record["failed_login_count"] = 0
                record["last_login"] = now_iso()
                record["updated_at"] = now_iso()
                save_users(users)
                user.update(record)
                return

    def handle_logout(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None, next_url: str = "") -> None:
        redirect_url = safe_next_url(next_url, url_with_lang("/login", lang))
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(SESSION_COOKIE)
        session_id = morsel.value if morsel else ""
        sessions = load_sessions()
        for session in sessions:
            if session.get("session_id") == session_id and session.get("active", True):
                session["active"] = False
                session["logout_time"] = now_iso()
                append_audit("user_management", str(session.get("user_id")), str(user.get("email") if user else "unknown"), "user_logout", {}, {"session_id": session_id})
                break
        save_sessions(sessions)
        self.send_response(303)
        self.send_header("Location", redirect_url)
        self.send_header("Set-Cookie", clear_session_cookie_header())
        self.end_headers()

    def send_dashboard(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        users = [item for item in load_users() if item.get("status") != "deleted"]
        sessions = load_sessions()
        audits = load_audit_logs()
        locked_count = sum(1 for item in users if item.get("account_locked") or item.get("status") == "locked")
        active_count = sum(1 for item in users if item.get("status") == "active")
        role_counts = {role.get("role_key"): 0 for role in load_roles()}
        for mapping in load_user_role_mappings():
            if not mapping.get("active", True):
                continue
            for role in load_roles():
                if role.get("role_id") == mapping.get("role_id"):
                    role_counts[str(role.get("role_key"))] = role_counts.get(str(role.get("role_key")), 0) + 1
        role_rows = "".join(f"<tr><td>{h(key)}</td><td>{count}</td></tr>" for key, count in role_counts.items())
        recent_logins = [audit for audit in reversed(audits) if audit.get("action") == "user_login"][:5]
        recent_failed = [audit for audit in reversed(audits) if audit.get("action") == "login_failed"][:5]
        body = f"""
<section class="grid">
  <article class="card"><div class="muted">{h(t(messages, 'dashboard.total_users'))}</div><p class="metric">{len(users)}</p></article>
  <article class="card"><div class="muted">{h(t(messages, 'dashboard.active_users'))}</div><p class="metric">{active_count}</p></article>
  <article class="card"><div class="muted">{h(t(messages, 'dashboard.locked_users'))}</div><p class="metric">{locked_count}</p></article>
  <article class="card"><div class="muted">{h(t(messages, 'dashboard.active_sessions'))}</div><p class="metric">{sum(1 for session in sessions if session.get('active', True))}</p></article>
</section>
<section class="grid">
  <article class="card"><h3>{h(t(messages, 'dashboard.role_distribution'))}</h3><table><tbody>{role_rows}</tbody></table></article>
  <article class="card"><h3>{h(t(messages, 'dashboard.recent_logins'))}</h3>{self.render_audit_list(recent_logins)}</article>
  <article class="card"><h3>{h(t(messages, 'dashboard.recent_failed_logins'))}</h3>{self.render_audit_list(recent_failed)}</article>
</section>
"""
        self.send_html(200, t(messages, "dashboard.title"), body, lang, messages, user)

    def render_audit_list(self, records: list[dict[str, Any]]) -> str:
        if not records:
            return "<p class=\"muted\">-</p>"
        items = "".join(f"<li>{h(record.get('timestamp'))} — {h(record.get('user'))}</li>" for record in records)
        return f"<ul>{items}</ul>"

    def send_login_sessions(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        sessions = active_sessions()
        users_by_id = {str(item.get("user_id")): item for item in load_users()}
        can_view_all = can_view_all_sessions(user)
        current_user_id = str(user.get("user_id", ""))
        keyword = query.get("q", [""])[0].strip().lower()
        status_filter = query.get("status", [""])[0].strip()
        entity_filter = query.get("entity_code", [""])[0].strip().lower()
        module_filter = sanitize_module_key(query.get("module_key", [""])[0])
        date_from = query.get("date_from", [""])[0].strip()
        date_to = query.get("date_to", [""])[0].strip()

        def session_status(session: dict[str, Any]) -> str:
            if session.get("logout_time"):
                return "logged_out"
            if not session.get("active", True):
                return "expired"
            expires_at = parse_iso(str(session.get("expires_at", "")))
            if expires_at and expires_at <= datetime.now(timezone.utc):
                return "expired"
            return "active"

        visible_sessions = []
        filtered = []
        for session in sessions:
            user_id = str(session.get("user_id", ""))
            if not can_view_all and user_id != current_user_id:
                continue
            session_user = users_by_id.get(user_id, {})
            status = session_status(session)
            visible_sessions.append((session, session_user, status))
            combined = " ".join(str(session_user.get(field, "")) for field in ["username", "display_name", "email"]).lower()
            if keyword and keyword not in combined:
                continue
            if status_filter and status != status_filter:
                continue
            if entity_filter and entity_filter not in str(session.get("entity_code", "")).lower():
                continue
            session_module_key = sanitize_module_key(str(session.get("current_module_key", "")))
            if module_filter and module_filter not in session_module_key:
                continue
            login_date = str(session.get("login_time", ""))[:10]
            if date_from and login_date < date_from:
                continue
            if date_to and login_date > date_to:
                continue
            filtered.append((session, session_user, status))

        filtered.sort(key=lambda item: str(item[0].get("login_time", "")), reverse=True)
        active_visible = [(session, session_user, status) for session, session_user, status in visible_sessions if status == "active"]
        active_user_count = len({str(session.get("user_id", "")) for session, _session_user, _status in active_visible})
        not_reported_count = sum(1 for session, _session_user, _status in active_visible if not sanitize_module_key(str(session.get("current_module_key", ""))))
        rows = []
        for session, session_user, status in filtered:
            module_key = sanitize_module_key(str(session.get("current_module_key", "")))
            module_path = sanitize_module_path(str(session.get("current_module_path", "")))
            module_label = module_display_name(module_key, messages)
            module_html = h(module_label)
            if module_path:
                module_html += f'<br><span class="muted">{h(module_path)}</span>'
            rows.append(
                f'''
<tr>
  <td><span class="badge">{h(t(messages, 'session.status.' + status, status))}</span></td>
  <td>{h(session_user.get('username', ''))}<br><span class="muted">{h(session_user.get('display_name', ''))}</span></td>
  <td>{h(session_user.get('email', ''))}</td>
  <td>{h(session.get('entity_code', ''))}<br><span class="muted">{h(session.get('entity_name_en', session.get('entity_name', '')))}</span></td>
  <td>{module_html}</td>
  <td>{h(format_jst(str(session.get('current_module_opened_at', ''))) or '-')}</td>
  <td>{h(format_jst(str(session.get('last_seen_at', ''))) or '-')}</td>
  <td>{h(format_jst(str(session.get('login_time', ''))))}</td>
  <td>{h(format_jst(str(session.get('expires_at', ''))) or '-')}</td>
  <td>{h(session.get('ip_address', ''))}</td>
  <td>{h(str(session.get('device') or session.get('browser') or '')[:120])}</td>
</tr>
'''
            )
        status_options = "".join(
            f'<option value="{h(value)}" {"selected" if value == status_filter else ""}>{h(label)}</option>'
            for value, label in [
                ("", t(messages, "session.filter_all", "All")),
                ("active", t(messages, "session.status.active", "Active")),
                ("expired", t(messages, "session.status.expired", "Expired")),
                ("logged_out", t(messages, "session.status.logged_out", "Logged out")),
            ]
        )
        scope_note = t(messages, "session.scope_all" if can_view_all else "session.scope_own", "")
        active_only_url = url_with_lang("/login-sessions", lang, {"status": "active"})
        body = f'''
<section class="sap-page-header">
  <h2>{h(t(messages, 'sessions.monitor_title'))}</h2>
  <p class="muted">{h(t(messages, 'sessions.monitor_description'))}</p>
  <p class="muted">{h(scope_note)}</p>
</section>
<section class="grid">
  <article class="card"><div class="muted">{h(t(messages, 'sessions.active_sessions'))}</div><p class="metric">{len(active_visible)}</p></article>
  <article class="card"><div class="muted">{h(t(messages, 'sessions.active_users'))}</div><p class="metric">{active_user_count}</p></article>
  <article class="card"><div class="muted">{h(t(messages, 'sessions.not_reported'))}</div><p class="metric">{not_reported_count}</p></article>
</section>
<section class="message-strip message-warning" role="status">{h(t(messages, 'sessions.restart_warning'))}</section>
<section class="card">
  <form method="get" action="/login-sessions">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'session.filter_keyword'))}</label><input name="q" value="{h(query.get('q', [''])[0])}" placeholder="username / email / display name"></div>
      <div><label>{h(t(messages, 'field.status'))}</label><select name="status">{status_options}</select></div>
      <div><label>{h(t(messages, 'field.entity_code'))}</label><input name="entity_code" value="{h(query.get('entity_code', [''])[0])}"></div>
      <div><label>{h(t(messages, 'session.filter_module'))}</label><input name="module_key" value="{h(query.get('module_key', [''])[0])}" placeholder="timesheet / payroll"></div>
      <div><label>{h(t(messages, 'session.date_from'))}</label><input type="date" name="date_from" value="{h(date_from)}"></div>
      <div><label>{h(t(messages, 'session.date_to'))}</label><input type="date" name="date_to" value="{h(date_to)}"></div>
    </div>
    <div class="actions"><button type="submit">{h(t(messages, 'action.filter', 'Filter'))}</button><a class="button light" href="{h(active_only_url)}">{h(t(messages, 'session.active_only'))}</a><a class="button light" href="{h(url_with_lang('/login-sessions', lang))}">{h(t(messages, 'action.clear', 'Clear'))}</a></div>
  </form>
</section>
<section class="card">
  <h3>{h(t(messages, 'sessions.results'))}: {len(filtered)}</h3>
  <div class="table-scroll"><table><thead><tr><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.username'))}</th><th>{h(t(messages, 'field.email'))}</th><th>{h(t(messages, 'field.entity_code'))}</th><th>{h(t(messages, 'session.current_module'))}</th><th>{h(t(messages, 'session.module_opened_at'))}</th><th>{h(t(messages, 'session.last_seen_at'))}</th><th>{h(t(messages, 'session.login_time'))}</th><th>{h(t(messages, 'session.expires_at'))}</th><th>IP</th><th>{h(t(messages, 'session.device'))}</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="11" class="muted">-</td></tr>'}</tbody></table></div>
</section>
'''
        self.send_html(200, t(messages, "sessions.monitor_title"), body, lang, messages, user)

    def send_users(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        rows = []
        for item in load_users():
            if item.get("status") == "deleted" or item.get("deleted"):
                continue
            user_id = str(item.get("user_id"))
            edit_url = url_with_lang("/users/edit", lang, {"user_id": user_id})
            actions = [f'<a class="button light" href="{h(edit_url)}">{h(t(messages, "action.edit"))}</a>']
            if item.get("status") == "active" and user_id != user.get("user_id"):
                actions.append(
                    f'''
<form method="post" action="{h(url_with_lang('/users/deactivate', lang))}">
  <input type="hidden" name="user_id" value="{h(user_id)}">
  <button class="danger" type="submit">{h(t(messages, 'action.deactivate'))}</button>
</form>
'''
                )
            employee_bits = [str(item.get('linked_employee_no') or '').strip(), str(item.get('linked_employee_name') or '').strip()]
            entity_bits = [str(item.get('linked_entity_code') or '').strip()]
            rows.append(
                f'''
<tr>
  <td>{h(user_id)}</td>
  <td>{h(item.get('username'))}</td>
  <td>{h(item.get('display_name'))}</td>
  <td>{h(item.get('email'))}</td>
  <td>{h(t(messages, 'user_type.' + str(item.get('user_type', 'admin')), str(item.get('user_type', 'admin'))))}</td>
  <td>{h(' - '.join(bit for bit in employee_bits if bit) or '-')}<br><span class="muted">{h(' - '.join(bit for bit in entity_bits if bit))}</span></td>
  <td><span class="badge">{h(t(messages, 'status.' + str(item.get('status')), str(item.get('status'))))}</span></td>
  <td>{h(', '.join(active_user_role_keys(user_id)))}</td>
  <td>{h(item.get('last_login'))}</td>
  <td><div class="actions">{''.join(actions)}</div></td>
</tr>
'''
            )
        create_url = url_with_lang("/users/new", lang)
        body = f'''
<section class="card">
  <div class="actions"><h2>{h(t(messages, 'users.title'))}</h2><a class="button" href="{h(create_url)}">{h(t(messages, 'users.create'))}</a></div>
  <p class="muted">{h(t(messages, 'users.description'))}</p>
  <table><thead><tr><th>{h(t(messages, 'field.user_id'))}</th><th>{h(t(messages, 'field.username'))}</th><th>{h(t(messages, 'field.display_name'))}</th><th>{h(t(messages, 'field.email'))}</th><th>{h(t(messages, 'field.user_type', 'User Type'))}</th><th>{h(t(messages, 'field.linked_employee', 'Linked Employee'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.roles'))}</th><th>{h(t(messages, 'field.last_login'))}</th><th>{h(t(messages, 'field.actions'))}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</section>
'''
        self.send_html(200, t(messages, "users.title"), body, lang, messages, user)

    def send_edit_user_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        target = find_user_by_id(query.get("user_id", [""])[0])
        if not target:
            self.send_not_found(lang, messages, user)
            return
        self.send_user_form(lang, messages, user, "edit", target, active_user_role_ids(str(target.get("user_id"))), [])

    def send_user_form(
        self,
        lang: str,
        messages: dict[str, str],
        user: dict[str, Any],
        mode: str,
        target_user: dict[str, Any],
        selected_role_ids: list[str],
        errors: list[str],
    ) -> None:
        is_create = mode == "create"
        title_key = "users.form.title_create" if is_create else "users.form.title_edit"
        action_path = "/users/create" if is_create else "/users/update"
        status_options = "".join(
            f'<option value="{h(status)}" {"selected" if str(target_user.get("status", "active")) == status else ""}>{h(t(messages, "status." + status, status))}</option>'
            for status in sorted(USER_STATUSES)
        )
        language_options = "".join(
            f'<option value="{h(language)}" {"selected" if str(target_user.get("language_preference", DEFAULT_LANG)) == language else ""}>{h(language)}</option>'
            for language in sorted(SUPPORTED_LANGS)
        )
        selected_user_type = str(target_user.get("user_type", "admin") or "admin")
        user_type_options = "".join(
            f'<option value="{h(user_type)}" {"selected" if selected_user_type == user_type else ""}>{h(t(messages, "user_type." + user_type, user_type))}</option>'
            for user_type in ["employee", "admin", "external", "system"]
        )
        selected_employee_id = str(target_user.get("linked_employee_id", "") or "")
        selected_employee_number = str(target_user.get("linked_employee_number") or target_user.get("linked_employee_no") or "")
        if not selected_employee_number and selected_employee_id:
            selected_employee_number = employee_link_snapshot(selected_employee_id).get("employee_no", "")
        employee_options = ['<option value="">--</option>']
        employee_number_options = []
        for employee in visible_employeeadmin_employees():
            employee_id = str(employee.get("employee_id", ""))
            if not employee_id:
                continue
            snapshot = employee_context_from_employee(employee)
            label = " - ".join(bit for bit in [snapshot.get("entity_code", ""), snapshot.get("employee_no", ""), snapshot.get("employee_name", ""), snapshot.get("department_code") or snapshot.get("department_name", ""), snapshot.get("employment_status", "")] if bit)
            selected_attr = " selected" if employee_id == selected_employee_id else ""
            employee_options.append(f'<option value="{h(employee_id)}"{selected_attr}>{h(label or employee_id)}</option>')
            employee_number = snapshot.get("employee_no", "")
            if employee_number:
                employee_number_options.append(f'<option value="{h(employee_number)}" label="{h(label or employee_number)}"></option>')
        role_items = []
        selected = set(selected_role_ids)
        for role in active_roles():
            role_id = str(role.get("role_id"))
            checked = "checked" if role_id in selected else ""
            role_items.append(
                f'''
<div class="checkbox-item">
  <label><input type="checkbox" name="role_ids" value="{h(role_id)}" {checked}> <span><strong>{h(role.get('role_name'))}</strong><br><span class="muted">{h(t(messages, str(role.get('description_key')), str(role.get('role_key'))))}</span></span></label>
</div>
'''
            )
        password_field = ""
        if is_create:
            password_field = f'''
<div class="form-field"><label for="initial_password">{h(t(messages, 'field.initial_password'))}</label><input id="initial_password" name="initial_password" type="password" required></div>
'''
        hidden_user = "" if is_create else f'<input type="hidden" name="user_id" value="{h(target_user.get("user_id"))}">'
        body = f'''
<section class="card">
  <h2>{h(t(messages, title_key))}</h2>
  {self.render_errors(messages, errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    {hidden_user}
    <div class="form-grid">
      <div class="form-field"><label for="username">{h(t(messages, 'field.username'))}</label><input id="username" name="username" value="{h(target_user.get('username'))}" required></div>
      <div class="form-field"><label for="display_name">{h(t(messages, 'field.display_name'))}</label><input id="display_name" name="display_name" value="{h(target_user.get('display_name'))}" required></div>
      <div class="form-field"><label for="email">{h(t(messages, 'field.email'))}</label><input id="email" name="email" type="email" value="{h(target_user.get('email'))}" required></div>
      <div class="form-field"><label for="phone">{h(t(messages, 'field.phone'))}</label><input id="phone" name="phone" value="{h(target_user.get('phone'))}"></div>
      <div class="form-field"><label for="department">{h(t(messages, 'field.department'))}</label><input id="department" name="department" value="{h(target_user.get('department'))}"></div>
      <div class="form-field"><label for="position">{h(t(messages, 'field.position'))}</label><input id="position" name="position" value="{h(target_user.get('position'))}"></div>
      <div class="form-field"><label for="user_type">{h(t(messages, 'field.user_type', 'User Type'))}</label><select id="user_type" name="user_type">{user_type_options}</select></div>
      <div class="form-field"><label for="linked_employee_number">{h(t(messages, 'field.linked_employee_number', 'Employee Number'))}</label><input id="linked_employee_number" name="linked_employee_number" list="linked_employee_number_options" value="{h(selected_employee_number)}"><datalist id="linked_employee_number_options">{''.join(employee_number_options)}</datalist><p class="muted">{h(t(messages, 'users.linked_employee_number_help', 'Enter or select an EmployeeAdmin employee number. If provided, it must exist in employee master data.'))}</p></div>
      <div class="form-field"><label for="linked_employee_id">{h(t(messages, 'field.linked_employee', 'Linked Employee'))}</label><select id="linked_employee_id" name="linked_employee_id">{''.join(employee_options)}</select><p class="muted">{h(t(messages, 'users.linked_employee_help', 'Employee users must be linked to EmployeeAdmin master data.'))}</p></div>
      <div class="form-field"><label for="status">{h(t(messages, 'field.status'))}</label><select id="status" name="status">{status_options}</select></div>
      <div class="form-field"><label for="language_preference">{h(t(messages, 'field.language_preference'))}</label><select id="language_preference" name="language_preference">{language_options}</select></div>
      {password_field}
    </div>
    <h3>{h(t(messages, 'field.roles'))}</h3>
    <div class="checkbox-grid">{''.join(role_items)}</div>
    <p class="actions"><button type="submit">{h(t(messages, 'action.save'))}</button><a class="button light" href="{h(url_with_lang('/users', lang))}">{h(t(messages, 'action.cancel'))}</a></p>
  </form>
</section>
'''
        self.send_html(200, t(messages, title_key), body, lang, messages, user)

    def extract_user_form(self, parsed: dict[str, list[str]], existing: dict[str, Any] | None = None) -> dict[str, Any]:
        existing = existing or {}
        return {
            "user_id": existing.get("user_id", form_first(parsed, "user_id")),
            "username": form_first(parsed, "username").strip(),
            "display_name": form_first(parsed, "display_name").strip(),
            "email": form_first(parsed, "email").strip().lower(),
            "phone": form_first(parsed, "phone").strip(),
            "department": form_first(parsed, "department").strip(),
            "position": form_first(parsed, "position").strip(),
            "user_type": form_first(parsed, "user_type", existing.get("user_type", "admin") or "admin").strip() or "admin",
            "linked_employee_id": form_first(parsed, "linked_employee_id", existing.get("linked_employee_id", "")).strip(),
            "linked_employee_number": form_first(parsed, "linked_employee_number", existing.get("linked_employee_no", "")).strip(),
            "status": form_first(parsed, "status", "active").strip() or "active",
            "language_preference": form_first(parsed, "language_preference", DEFAULT_LANG).strip() or DEFAULT_LANG,
        }

    def validate_user_form(self, messages: dict[str, str], data: dict[str, Any], selected_role_ids: list[str], current_user_id: str = "") -> list[str]:
        errors: list[str] = []
        if not data.get("username"):
            errors.append(t(messages, "validation.username_required"))
        if not data.get("display_name"):
            errors.append(t(messages, "validation.display_name_required"))
        if not data.get("email"):
            errors.append(t(messages, "validation.email_required"))
        if data.get("status") not in USER_STATUSES:
            errors.append(t(messages, "validation.invalid_status"))
        errors.extend(user_employee_link_errors(messages, data, current_user_id))
        if data.get("language_preference") not in SUPPORTED_LANGS:
            errors.append(t(messages, "validation.invalid_language"))
        active_role_ids = {str(role.get("role_id")) for role in active_roles()}
        if not selected_role_ids:
            errors.append(t(messages, "validation.role_required"))
        if any(role_id not in active_role_ids for role_id in selected_role_ids):
            errors.append(t(messages, "validation.invalid_role"))
        for existing in load_users():
            if existing.get("status") == "deleted" or existing.get("deleted") or existing.get("user_id") == current_user_id:
                continue
            if str(existing.get("username", "")).strip().lower() == str(data.get("username", "")).lower():
                errors.append(t(messages, "validation.username_duplicate"))
            if str(existing.get("email", "")).strip().lower() == str(data.get("email", "")).lower():
                errors.append(t(messages, "validation.email_duplicate"))
        return errors

    def handle_create_user(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        parsed = self.parse_form_multi_body()
        data = enrich_user_employee_link(self.extract_user_form(parsed))
        selected_role_ids = sorted(set(parsed.get("role_ids", [])))
        errors = self.validate_user_form(messages, data, selected_role_ids)
        initial_password = form_first(parsed, "initial_password")
        if not initial_password:
            errors.append(t(messages, "validation.password_required"))
        errors.extend(password_policy_errors(initial_password, messages))
        if errors:
            self.send_user_form(lang, messages, user, "create", data, selected_role_ids, errors)
            return
        users = load_users()
        timestamp = now_iso()
        persist_data = user_persistable_data(data)
        new_user = {
            **persist_data,
            "user_id": next_id(users, "user_id", "USR-", 4),
            "password_hash": hash_password(initial_password),
            "password_last_changed": timestamp,
            "last_login": "",
            "failed_login_count": 0,
            "account_locked": persist_data.get("status") == "locked",
            "account_locked_date": timestamp if persist_data.get("status") == "locked" else "",
            "created_at": timestamp,
            "updated_at": timestamp,
            "deleted": False,
        }
        users.append(new_user)
        save_users(users)
        append_audit("user_management", str(new_user.get("user_id")), actor_label(user), "user_created", {}, sanitized_user_for_audit(new_user))
        sync_user_entity_mapping_for_employee(str(new_user.get("user_id")), employee_link_snapshot(str(new_user.get("linked_employee_id", ""))), actor_label(user))
        before_roles, after_roles, changed = self.update_user_roles(str(new_user.get("user_id")), selected_role_ids, actor_label(user))
        if changed:
            append_audit("user_management", str(new_user.get("user_id")), actor_label(user), "user_roles_updated", {"roles": before_roles}, {"roles": after_roles})
        notice = operation_notice(messages, "User", str(new_user.get("username") or new_user.get("email") or new_user.get("user_id")), "created", actor_label(user))
        self.redirect(url_with_lang("/users", lang, {"notice": notice}))

    def handle_update_user(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        parsed = self.parse_form_multi_body()
        target_user_id = form_first(parsed, "user_id")
        target = find_user_by_id(target_user_id)
        if not target:
            self.send_not_found(lang, messages, user)
            return
        data = enrich_user_employee_link(self.extract_user_form(parsed, target))
        selected_role_ids = sorted(set(parsed.get("role_ids", [])))
        errors = self.validate_user_form(messages, data, selected_role_ids, target_user_id)
        if target_user_id == user.get("user_id") and data.get("status") != "active":
            errors.append(t(messages, "validation.cannot_deactivate_self"))
        if would_leave_no_active_system_admin(target_user_id, selected_role_ids, str(data.get("status"))):
            errors.append(t(messages, "validation.last_system_admin"))
        if errors:
            form_target = {**target, **data}
            self.send_user_form(lang, messages, user, "edit", form_target, selected_role_ids, errors)
            return
        users = load_users()
        persist_data = user_persistable_data(data)
        before_user: dict[str, Any] = sanitized_user_for_audit(target)
        candidate = dict(target)
        candidate.update(persist_data)
        candidate["account_locked"] = persist_data.get("status") == "locked"
        if candidate["account_locked"] and not candidate.get("account_locked_date"):
            candidate["account_locked_date"] = now_iso()
        if persist_data.get("status") != "locked":
            candidate["account_locked_date"] = ""
        after_user = sanitized_user_for_audit(candidate)
        before_compare = {key: value for key, value in before_user.items() if key != "updated_at"}
        after_compare = {key: value for key, value in after_user.items() if key != "updated_at"}
        user_changed = before_compare != after_compare
        role_changed = set(active_user_role_ids(target_user_id)) != set(selected_role_ids)
        if not user_changed and not role_changed:
            notice = no_change_notice(messages, "User", str(after_user.get("username") or after_user.get("email") or target_user_id))
            self.redirect(url_with_lang("/users", lang, {"notice": notice}))
            return
        if user_changed:
            after_user = {}
            for record in users:
                if record.get("user_id") == target_user_id:
                    record.update(persist_data)
                    record["account_locked"] = persist_data.get("status") == "locked"
                    if record["account_locked"] and not record.get("account_locked_date"):
                        record["account_locked_date"] = now_iso()
                    if persist_data.get("status") != "locked":
                        record["account_locked_date"] = ""
                    record["updated_at"] = now_iso()
                    after_user = sanitized_user_for_audit(record)
                    break
            save_users(users)
            append_audit("user_management", target_user_id, actor_label(user), "user_updated", before_user, after_user)
            sync_user_entity_mapping_for_employee(target_user_id, employee_link_snapshot(str(after_user.get("linked_employee_id", ""))), actor_label(user))
        before_roles, after_roles, changed = self.update_user_roles(target_user_id, selected_role_ids, actor_label(user))
        if changed:
            append_audit("user_management", target_user_id, actor_label(user), "user_roles_updated", {"roles": before_roles}, {"roles": after_roles})
        display_user = after_user if user_changed else before_user
        notice = operation_notice(messages, "User", str(display_user.get("username") or display_user.get("email") or target_user_id), "saved", actor_label(user))
        self.redirect(url_with_lang("/users", lang, {"notice": notice}))

    def handle_deactivate_user(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        target_user_id = form.get("user_id", "")
        target = find_user_by_id(target_user_id)
        if not target:
            self.send_not_found(lang, messages, user)
            return
        errors: list[str] = []
        if target_user_id == user.get("user_id"):
            errors.append(t(messages, "validation.cannot_deactivate_self"))
        if would_leave_no_active_system_admin(target_user_id, active_user_role_ids(target_user_id), "inactive"):
            errors.append(t(messages, "validation.last_system_admin"))
        if errors:
            self.send_user_form(lang, messages, user, "edit", target, active_user_role_ids(target_user_id), errors)
            return
        users = load_users()
        before_user: dict[str, Any] = {}
        after_user: dict[str, Any] = {}
        for record in users:
            if record.get("user_id") == target_user_id:
                before_user = sanitized_user_for_audit(record)
                record["status"] = "inactive"
                record["updated_at"] = now_iso()
                after_user = sanitized_user_for_audit(record)
                break
        save_users(users)
        append_audit("user_management", target_user_id, actor_label(user), "user_deactivated", before_user, after_user)
        revoked_sessions = self.revoke_user_sessions(target_user_id)
        if revoked_sessions:
            append_audit("user_management", target_user_id, actor_label(user), "user_sessions_revoked", {}, {"session_ids": revoked_sessions})
        notice = operation_notice(messages, "User", str(target.get("username") or target.get("email") or target_user_id), "deactivated", actor_label(user))
        self.redirect(url_with_lang("/users", lang, {"notice": notice}))

    def update_user_roles(self, target_user_id: str, selected_role_ids: list[str], actor: str) -> tuple[list[str], list[str], bool]:
        selected = set(selected_role_ids)
        mappings = load_user_role_mappings()
        before = active_user_role_ids(target_user_id)
        existing_pairs = {(str(mapping.get("user_id")), str(mapping.get("role_id"))): mapping for mapping in mappings}
        changed = False
        for mapping in mappings:
            if mapping.get("user_id") != target_user_id:
                continue
            should_be_active = str(mapping.get("role_id")) in selected
            if bool(mapping.get("active", True)) != should_be_active:
                mapping["active"] = should_be_active
                if should_be_active:
                    mapping["assigned_at"] = now_iso()
                    mapping["assigned_by"] = actor
                changed = True
        for role_id in selected:
            if (target_user_id, role_id) not in existing_pairs:
                mappings.append({"mapping_id": next_id(mappings, "mapping_id", "URM-", 4), "user_id": target_user_id, "role_id": role_id, "assigned_at": now_iso(), "assigned_by": actor, "active": True})
                changed = True
        if changed:
            save_user_role_mappings(mappings)
        after = active_user_role_ids(target_user_id)
        return role_keys_for_ids(before), role_keys_for_ids(after), changed

    def revoke_user_sessions(self, target_user_id: str) -> list[str]:
        sessions = load_sessions()
        revoked: list[str] = []
        for session in sessions:
            if session.get("user_id") == target_user_id and session.get("active", True):
                session["active"] = False
                session["logout_time"] = now_iso()
                revoked.append(str(session.get("session_id")))
        if revoked:
            save_sessions(sessions)
        return revoked

    def send_roles(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        rows = []
        can_manage_permissions = "user_management.manage_permissions" in effective_permissions(str(user.get("user_id")))
        for role in load_roles():
            role_id = str(role.get("role_id"))
            permissions = active_role_permission_ids(role_id)
            actions = ""
            if can_manage_permissions and role.get("role_key") != "system_admin":
                actions = f'<a class="button light" href="{h(url_with_lang("/roles/permissions", lang, {"role_id": role_id}))}">{h(t(messages, "roles.manage_permissions"))}</a>'
            elif role.get("role_key") == "system_admin":
                actions = f'<span class="muted">{h(t(messages, "permissions.system_admin_readonly"))}</span>'
            rows.append(
                f'<tr><td>{h(role.get("role_key"))}</td><td>{h(role.get("role_name"))}</td><td><span class="badge">{h(t(messages, "status.active" if role.get("active", True) else "status.inactive"))}</span></td><td>{len(permissions)}</td><td>{actions}</td></tr>'
            )
        body = f'''
<section class="card">
  <h2>{h(t(messages, 'roles.title'))}</h2>
  <table><thead><tr><th>{h(t(messages, 'field.role_key'))}</th><th>{h(t(messages, 'field.role_name'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.permission_count'))}</th><th>{h(t(messages, 'field.actions'))}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</section>
'''
        self.send_html(200, t(messages, "roles.title"), body, lang, messages, user)

    def send_role_permissions(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]], errors: list[str]) -> None:
        role_id = query.get("role_id", [""])[0]
        role = find_role_by_id(role_id)
        if not role:
            self.send_not_found(lang, messages, user)
            return
        selected_ids = set(active_role_permission_ids(role_id))
        groups: dict[str, list[dict[str, Any]]] = {}
        for permission in active_permissions():
            groups.setdefault(str(permission.get("module")), []).append(permission)
        group_html = []
        readonly = role.get("role_key") == "system_admin"
        for module, permissions in sorted(groups.items()):
            items = []
            for permission in sorted(permissions, key=lambda item: str(item.get("permission_key"))):
                permission_id = str(permission.get("permission_id"))
                checked = "checked" if permission_id in selected_ids or readonly else ""
                disabled = "disabled" if readonly else ""
                items.append(
                    f'''
<div class="checkbox-item">
  <label><input type="checkbox" name="permission_ids" value="{h(permission_id)}" {checked} {disabled}> <span><strong>{h(permission.get('permission_key'))}</strong><br><span class="muted">{h(permission.get('description'))}</span></span></label>
</div>
'''
                )
            group_html.append(f'<section class="card"><h3>{h(module)}</h3><div class="checkbox-grid">{"".join(items)}</div></section>')
        readonly_note = f'<p class="muted">{h(t(messages, "permissions.system_admin_readonly"))}</p>' if readonly else ""
        submit_html = "" if readonly else f'<button type="submit">{h(t(messages, "action.save"))}</button>'
        body = f'''
<section class="card">
  <h2>{h(t(messages, 'permissions.title'))}: {h(role.get('role_name'))}</h2>
  <p class="muted">{h(t(messages, 'permissions.description'))}</p>
  {readonly_note}
  {self.render_errors(messages, errors)}
  <form method="post" action="{h(url_with_lang('/roles/permissions', lang))}">
    <input type="hidden" name="role_id" value="{h(role_id)}">
    {''.join(group_html)}
    <p class="actions">{submit_html}<a class="button light" href="{h(url_with_lang('/roles', lang))}">{h(t(messages, 'action.cancel'))}</a></p>
  </form>
</section>
'''
        self.send_html(200, t(messages, "permissions.title"), body, lang, messages, user)

    def handle_update_role_permissions(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        parsed = self.parse_form_multi_body()
        role_id = form_first(parsed, "role_id")
        role = find_role_by_id(role_id)
        if not role:
            self.send_not_found(lang, messages, user)
            return
        selected_permission_ids = sorted(set(parsed.get("permission_ids", [])))
        errors: list[str] = []
        if role.get("role_key") == "system_admin":
            errors.append(t(messages, "validation.system_admin_permissions_readonly"))
        active_permission_ids = {str(permission.get("permission_id")) for permission in active_permissions()}
        if any(permission_id not in active_permission_ids for permission_id in selected_permission_ids):
            errors.append(t(messages, "validation.invalid_permission"))
        if errors:
            self.send_role_permissions(lang, messages, user, {"role_id": [role_id]}, errors)
            return
        before, after, changed = self.update_role_permissions(role_id, selected_permission_ids)
        role = find_role_by_id(role_id) or {}
        if changed:
            append_audit("user_management", role_id, actor_label(user), "role_permissions_updated", {"permissions": before}, {"permissions": after})
            notice = operation_notice(messages, "Role permission", str(role.get("role_name") or role_id), "saved", actor_label(user))
        else:
            notice = no_change_notice(messages, "Role permission", str(role.get("role_name") or role_id))
        self.redirect(url_with_lang("/roles", lang, {"notice": notice}))

    def update_role_permissions(self, role_id: str, selected_permission_ids: list[str]) -> tuple[list[str], list[str], bool]:
        selected = set(selected_permission_ids)
        mappings = load_role_permission_mappings()
        before = active_role_permission_ids(role_id)
        existing_pairs = {(str(mapping.get("role_id")), str(mapping.get("permission_id"))): mapping for mapping in mappings}
        changed = False
        for mapping in mappings:
            if mapping.get("role_id") != role_id:
                continue
            should_be_active = str(mapping.get("permission_id")) in selected
            if bool(mapping.get("active", True)) != should_be_active:
                mapping["active"] = should_be_active
                changed = True
        for permission_id in selected:
            if (role_id, permission_id) not in existing_pairs:
                mappings.append({"mapping_id": next_id(mappings, "mapping_id", "RPM-", 4), "role_id": role_id, "permission_id": permission_id, "active": True})
                changed = True
        if changed:
            save_role_permission_mappings(mappings)
        after = active_role_permission_ids(role_id)
        return permission_keys_for_ids(before), permission_keys_for_ids(after), changed

    def send_audit_logs(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        rows = []
        for audit in reversed(load_audit_logs()[-100:]):
            rows.append(f"<tr><td>{h(audit.get('audit_id'))}</td><td>{h(audit.get('module'))}</td><td>{h(audit.get('record_id'))}</td><td>{h(audit.get('user'))}</td><td>{h(audit.get('action'))}</td><td>{h(audit.get('timestamp'))}</td></tr>")
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'audit.title'))}</h2>
  <table><thead><tr><th>{h(t(messages, 'field.audit_id'))}</th><th>{h(t(messages, 'field.module'))}</th><th>{h(t(messages, 'field.record_id'))}</th><th>{h(t(messages, 'field.user'))}</th><th>{h(t(messages, 'field.action'))}</th><th>{h(t(messages, 'field.timestamp'))}</th></tr></thead><tbody>{''.join(rows)}</tbody></table>
</section>
"""
        self.send_html(200, t(messages, "audit.title"), body, lang, messages, user)

    def send_change_password(self, lang: str, messages: dict[str, str], user: dict[str, Any], errors: list[str], success: bool = False) -> None:
        status_html = f"<p class=\"badge\">{h(t(messages, 'password.changed'))}</p>" if success else ""
        show_label = h(t(messages, "password.show"))
        hide_label = h(t(messages, "password.hide"))
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'password.title'))}</h2>
  <p class="muted">{h(t(messages, 'password.policy_hint'))}</p>
  {self.render_errors(messages, errors)}
  {status_html}
  <form method="post" action="{h(url_with_lang('/change-password', lang))}">
    <div class="form-field"><label for="current_password">{h(t(messages, 'field.current_password'))}</label><div class="actions"><input id="current_password" name="current_password" type="password" required autocomplete="current-password"><button type="button" class="light" data-toggle-password="current_password">{show_label}</button></div></div>
    <div class="form-field"><label for="new_password">{h(t(messages, 'field.new_password'))}</label><div class="actions"><input id="new_password" name="new_password" type="password" required minlength="6" maxlength="10" autocomplete="new-password"><button type="button" class="light" data-toggle-password="new_password">{show_label}</button></div></div>
    <div class="form-field"><label for="confirm_password">{h(t(messages, 'field.confirm_password'))}</label><div class="actions"><input id="confirm_password" name="confirm_password" type="password" required minlength="6" maxlength="10" autocomplete="new-password"><button type="button" class="light" data-toggle-password="confirm_password">{show_label}</button></div></div>
    <button type="submit">{h(t(messages, 'password.submit'))}</button>
  </form>
</section>
<script>
(() => {{
  const showText = {json.dumps(show_label, ensure_ascii=False)};
  const hideText = {json.dumps(hide_label, ensure_ascii=False)};
  for (const button of document.querySelectorAll('[data-toggle-password]')) {{
    button.addEventListener('click', () => {{
      const input = document.getElementById(button.dataset.togglePassword || '');
      if (!input) return;
      const shouldShow = input.type === 'password';
      input.type = shouldShow ? 'text' : 'password';
      button.textContent = shouldShow ? hideText : showText;
    }});
  }}
}})();
</script>
"""
        self.send_html(200, t(messages, "password.title"), body, lang, messages, user)

    def handle_change_password(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        current_password = form.get("current_password", "")
        new_password = form.get("new_password", "")
        confirm_password = form.get("confirm_password", "")
        if not verify_password(current_password, str(user.get("password_hash", ""))):
            self.send_change_password(lang, messages, user, [t(messages, "validation.current_password_invalid")])
            return
        errors = password_policy_errors(new_password, messages)
        if new_password != confirm_password:
            errors.append(t(messages, "validation.password_confirmation_mismatch"))
        if errors:
            self.send_change_password(lang, messages, user, errors)
            return
        users = load_users()
        for record in users:
            if record.get("user_id") == user.get("user_id"):
                before = {"password_last_changed": record.get("password_last_changed")}
                record["password_hash"] = hash_password(new_password)
                record["password_last_changed"] = now_iso()
                record["updated_at"] = now_iso()
                after = {"password_last_changed": record.get("password_last_changed")}
                save_users(users)
                append_audit("user_management", str(record.get("user_id")), str(record.get("email")), "password_changed", before, after)
                self.send_change_password(lang, messages, record, [], success=True)
                return

    def handle_api_validate_session(self) -> None:
        data = self.parse_json_body()
        session_id = str(data.get("session_id", ""))
        module_key = sanitize_module_key(str(data.get("module_key", "")))
        module_path = sanitize_module_path(str(data.get("module_path", "")))
        session, user = validate_session_id(session_id)
        activity = session_context(session) if user else {}
        if user:
            permissions = effective_permissions(str(user.get("user_id")))
            if module_key and any(permission.startswith(module_key + ".") for permission in permissions):
                activity = record_session_activity(session_id, module_key, module_path, "validate_session")
            else:
                activity = record_session_activity(session_id, source="validate_session")
        self.send_json(200, {"valid": bool(user), "user": user_context(user, session) if user else None, "session": activity if user else None})

    def handle_api_check_permission(self) -> None:
        data = self.parse_json_body()
        session_id = str(data.get("session_id", ""))
        permission_key = str(data.get("permission_key", ""))
        session, user = validate_session_id(session_id)
        allowed = bool(user and permission_key in effective_permissions(str(user.get("user_id"))))
        self.send_json(200, {"allowed": allowed, "user_id": user.get("user_id") if user else "", "permission_key": permission_key, "entity": entity_context_from_session(session), "reason": "role_permission_match" if allowed else "not_allowed"})

    def handle_api_check_role(self) -> None:
        data = self.parse_json_body()
        session_id = str(data.get("session_id", ""))
        role_key = str(data.get("role_key", ""))
        session, user = validate_session_id(session_id)
        allowed = bool(user and role_key in active_user_role_keys(str(user.get("user_id"))))
        self.send_json(200, {"allowed": allowed, "user_id": user.get("user_id") if user else "", "role_key": role_key, "entity": entity_context_from_session(session)})

    def handle_api_check_module_access(self) -> None:
        data = self.parse_json_body()
        session_id = str(data.get("session_id", ""))
        module_key = sanitize_module_key(str(data.get("module_key", "")))
        module_path = sanitize_module_path(str(data.get("module_path", "")))
        session, user = validate_session_id(session_id)
        permissions = effective_permissions(str(user.get("user_id"))) if user else []
        allowed = any(permission.startswith(module_key + ".") for permission in permissions)
        activity = record_session_activity(session_id, module_key, module_path, "check_module_access") if allowed else session_context(session)
        self.send_json(200, {"allowed": allowed, "user_id": user.get("user_id") if user else "", "module_key": module_key, "entity": entity_context_from_session(session), "session_activity": activity})

    def render_errors(self, messages: dict[str, str], errors: list[str]) -> str:
        if not errors:
            return ""
        items = "".join(f"<li>{h(error)}</li>" for error in errors)
        return f"<div class=\"errors\"><strong>{h(t(messages, 'validation.title'))}</strong><ul>{items}</ul></div>"

    def send_forbidden(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None) -> None:
        body = f"<section class=\"card\"><h2>{h(t(messages, 'error.forbidden'))}</h2><p>{h(t(messages, 'error.forbidden_description'))}</p></section>"
        self.send_html(403, t(messages, "error.forbidden"), body, lang, messages, user)

    def send_not_found(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None) -> None:
        body = f"<section class=\"card\"><h2>{h(t(messages, 'error.not_found'))}</h2></section>"
        self.send_html(404, t(messages, "error.not_found"), body, lang, messages, user)

    def flash_message(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(FLASH_COOKIE)
        return unquote(morsel.value) if morsel else ""

    def flash_cookie_header(self, message: str) -> str:
        cookie = SimpleCookie()
        cookie[FLASH_COOKIE] = quote(message)
        cookie[FLASH_COOKIE]["path"] = "/"
        cookie[FLASH_COOKIE]["samesite"] = "Lax"
        return cookie.output(header="").strip()

    def clear_flash_cookie_header(self) -> str:
        return f"{FLASH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax"

    def redirect(self, location: str) -> None:
        parsed = urlparse(location)
        query = parse_qs(parsed.query)
        notice = query.get("notice", [""])[0]
        if notice:
            clean_query = {key: values[-1] for key, values in query.items() if key != "notice" and values}
            location = parsed._replace(query=urlencode(clean_query)).geturl()
        self.send_response(303)
        self.send_header("Location", location)
        if notice:
            self.send_header("Set-Cookie", self.flash_cookie_header(notice))
        self.end_headers()

    def send_html(self, status: int, title: str, body: str, lang: str, messages: dict[str, str], current_user: dict[str, Any] | None) -> None:
        flash = self.flash_message()
        if flash:
            body = f'<div class="message-strip message-success" role="status">{h(flash)}</div>' + body
            self._clear_flash_after_response = True
        current_session, _ = self.current_session_user() if current_user else (None, None)
        if current_session and status < 500:
            record_session_activity(str(current_session.get("session_id", "")), "user_management", urlparse(self.path).path, "user_admin_page")
            current_session, _ = self.current_session_user()
        self.send_bytes(status, "text/html; charset=utf-8", render_page(title, body, lang, messages, current_user, self.path, current_session))

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_bytes(status, "application/json; charset=utf-8", body)

    def send_text(self, status: int, text: str) -> None:
        self.send_bytes(status, "text/plain; charset=utf-8", text.encode("utf-8"))

    def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if getattr(self, "_clear_flash_after_response", False):
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
            self._clear_flash_after_response = False
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TACAI User Management local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8006)
    return parser.parse_args()


def main() -> None:
    seed_data()
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), UserAdminHandler)
    print(f"TACAI User Management running at http://{args.host}:{args.port}")
    print(f"Initial local admin email: {INITIAL_ADMIN_EMAIL}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TACAI User Management")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
