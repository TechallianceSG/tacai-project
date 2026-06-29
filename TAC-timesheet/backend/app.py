"""Local web app for TAC-timesheet - Japan dispatch timesheet management.

This MVP intentionally uses only Python standard library modules so it can run
on a laptop without installing dependencies.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import os
from datetime import date, datetime, timedelta, timezone
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
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
I18N_DIR = ROOT_DIR / "i18n"
TIMESHEET_ENTRIES_PATH = ROOT_DIR / "database" / "timesheet_entries.json"
EMPLOYEES_PATH = ROOT_DIR / "database" / "employees.json"
PROJECTS_PATH = ROOT_DIR / "database" / "projects.json"
ENTITIES_PATH = ROOT_DIR / "database" / "entities.json"
DEPARTMENTS_PATH = ROOT_DIR / "database" / "departments.json"
TEAMS_PATH = ROOT_DIR / "database" / "teams.json"
MONTH_LOCKS_PATH = ROOT_DIR / "database" / "month_locks.json"
INVOICE_DRAFTS_PATH = ROOT_DIR / "database" / "invoice_drafts.json"
AUDIT_LOGS_PATH = ROOT_DIR / "database" / "audit_logs.json"
LOCAL_ACTOR = "local_user"
FLASH_COOKIE = "tacai_flash"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
CONFIGURED_PUBLIC_HOSTS = {host.strip().lower() for host in os.environ.get("TACAI_ALLOWED_PUBLIC_HOSTS", "").split(",") if host.strip()}
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {3000, 3001, 4000, 4001, 5000, 5001, 6000, 6001, 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8012, 8016, 8018}


def _resolve_host(request_host: str | None = None) -> str:
    """Return 127.0.0.1 when accessed locally, otherwise the LAN IP."""
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return TACAI_PUBLIC_HOST


def resolve_portal_url(request_host: str | None = None, default_portal_url: str | None = None) -> str:
    """Return portal URL adjusted for the request origin."""
    portal = default_portal_url or PORTAL_BASE_URL
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        parsed = urlparse(portal)
        port = parsed.port or 3000
        return f"http://127.0.0.1:{port}{parsed.path if parsed.path else ''}"
    return portal


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


def base_url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


APP_BASE_URL = public_base_url("TIMESHEET_PUBLIC_BASE_URL", 8002)
PORTAL_BASE_URL = (os.environ.get("PORTAL_BASE_URL") or "").strip().rstrip("/") or public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
EMPLOYEEADMIN_BASE_URL = public_base_url("EMPLOYEEADMIN_PUBLIC_BASE_URL", 8004)
EMPLOYEEADMIN_INTERNAL_BASE_URL = os.environ.get("EMPLOYEEADMIN_INTERNAL_BASE_URL", internal_base_url(8004)).strip().rstrip("/")
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")
PUBLIC_ALLOWED_HOSTS = CONFIGURED_PUBLIC_HOSTS | {host for host in [base_url_host(APP_BASE_URL), base_url_host(PORTAL_BASE_URL), base_url_host(USER_ADMIN_BASE_URL)] if host}
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
REQUIRED_MODULE_PERMISSION = "timesheet.access"
DEFAULT_LANG = "zh"
SUPPORTED_LANGS = {"zh", "ja", "en"}
DEFAULT_SCHEDULED_WORK_MINUTES = 480

ATTENDANCE_STATUSES = [
    ("Worked", "Worked / 出勤"),
    ("Paid Leave", "Paid Leave / 有給休暇"),
    ("Sick Leave", "Sick Leave / 病欠"),
    ("Absence", "Absence / 欠勤"),
    ("Holiday", "Holiday / 休日"),
    ("Substitute Holiday", "Substitute Holiday / 振替休日"),
    ("Special Leave", "Special Leave / 特別休暇"),
]

APPROVAL_STATUSES = [
    ("Draft", "Draft / 下書き"),
    ("Submitted", "Submitted / 申請済"),
    ("Approved", "Approved / 承認済"),
    ("Rejected", "Rejected / 差戻し"),
]

WORK_LOCATIONS = [
    ("Office", "Office / 自社オフィス"),
    ("Customer Site", "Customer Site / 顧客先"),
    ("Remote", "Remote / 在宅勤務"),
    ("Business Trip", "Business Trip / 出張"),
    ("Other", "Other / その他"),
]

DISPATCH_TYPES = [
    ("Expatriate", "Expatriate / 海外赴任・駐在"),
    ("Dispatch", "Dispatch / 派遣"),
    ("Client Site", "Client Site / 客先常駐"),
    ("Remote Support", "Remote Support / リモート支援"),
    ("Other", "Other / その他"),
]

BOOLEAN_SELECT = [("false", "No / いいえ"), ("true", "Yes / はい")]

ENTRY_SOURCES = [
    ("web_self", "Self web entry"),
    ("web_proxy", "Proxy web entry"),
    ("email_manual", "Email/manual attendance sheet"),
]

ASSISTANCE_REASONS = [
    ("", "Select reason"),
    ("email_attendance_sheet", "Email attendance sheet"),
    ("offsite_no_network", "Offsite without network access"),
    ("hr_finance_assisted", "HR/Finance assisted entry"),
    ("manager_correction", "Manager correction"),
    ("other", "Other"),
]


def validate_user_admin_session(session_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    request = Request(
        f"{USER_ADMIN_INTERNAL_BASE_URL}/api/validate-session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None
    if data.get("valid") and isinstance(data.get("user"), dict):
        user = data["user"]
        if isinstance(data.get("session"), dict):
            user["_session"] = data["session"]
        return user
    return None


def has_permission(user: dict[str, Any], permission_key: str) -> bool:
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return "system_admin" in roles or permission_key in permissions


def has_required_module_access(user: dict[str, Any]) -> bool:
    return has_permission(user, REQUIRED_MODULE_PERMISSION)


def has_any_permission(user: dict[str, Any], permission_keys: list[str]) -> bool:
    return any(has_permission(user, permission_key) for permission_key in permission_keys)


def can_submit_self(user: dict[str, Any]) -> bool:
    return has_any_permission(user, ["timesheet.submit_self", "timesheet.submit"])


def can_proxy_submit(user: dict[str, Any]) -> bool:
    return has_any_permission(user, ["timesheet.proxy_submit", "timesheet.submit"])


def can_edit_own_timesheet(user: dict[str, Any]) -> bool:
    return has_permission(user, "timesheet.edit_own")


def can_proxy_edit_timesheet(user: dict[str, Any]) -> bool:
    return has_permission(user, "timesheet.proxy_edit")


def can_delete_timesheet(user: dict[str, Any], record: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    if is_own_employee_record(record, context):
        return can_edit_own_timesheet(user) or has_permission(user, "timesheet.delete_own")
    return can_proxy_edit_timesheet(user) or has_permission(user, "timesheet.delete")


def audit_actor_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return LOCAL_ACTOR
    for key in ["email", "username", "user_name", "name", "display_name", "user_id", "id"]:
        value_text = str(user.get(key, "")).strip()
        if value_text:
            return value_text
    return LOCAL_ACTOR


def user_identifier(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    for key in ["user_id", "id", "email", "username", "user_name"]:
        value_text = str(user.get(key, "") or "").strip()
        if value_text:
            return value_text
    return ""


def user_display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return LOCAL_ACTOR
    for key in ["display_name", "name", "email", "username", "user_name", "user_id", "id"]:
        value_text = str(user.get(key, "") or "").strip()
        if value_text:
            return value_text
    return LOCAL_ACTOR


def current_entity_from_user(user: dict[str, Any] | None) -> dict[str, str]:
    if not user:
        return {}
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    session_entity = session.get("entity") if isinstance(session.get("entity"), dict) else {}
    entity = {
        "entity_id": str(user.get("entity_id") or session_entity.get("entity_id") or session.get("entity_id") or "").strip(),
        "entity_code": str(user.get("entity_code") or session_entity.get("entity_code") or session.get("entity_code") or "").strip(),
        "entity_name": str(user.get("entity_name") or session_entity.get("entity_name") or session.get("entity_name") or "").strip(),
    }
    return {key: value for key, value in entity.items() if value}


def context_current_entity(context: dict[str, Any] | None) -> dict[str, str]:
    if context and isinstance(context.get("current_entity"), dict):
        return {str(key): str(value) for key, value in context["current_entity"].items() if str(value).strip()}
    return current_entity_from_user((context or {}).get("user") if context else None)


def current_entity_id(context: dict[str, Any] | None) -> str:
    return str(context_current_entity(context).get("entity_id", "")).strip()


def current_entity_code(context: dict[str, Any] | None) -> str:
    return str(context_current_entity(context).get("entity_code", "")).strip()


def current_entity_label(context: dict[str, Any] | None) -> str:
    entity = context_current_entity(context)
    return " - ".join(bit for bit in [entity.get("entity_code", ""), entity.get("entity_name", "")] if bit) or "-"


def apply_current_entity_snapshot(record: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    entity = context_current_entity(context)
    if entity:
        record["entity_id"] = entity.get("entity_id", record.get("entity_id", ""))
        record["entity_code"] = entity.get("entity_code", record.get("entity_code", ""))
        record["entity_name"] = entity.get("entity_name", record.get("entity_name", ""))
    return record


def record_entity_matches(record: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    entity = context_current_entity(context)
    if not entity:
        return True
    entity_id = str(entity.get("entity_id", "")).strip()
    entity_code = str(entity.get("entity_code", "")).strip()
    record_entity_id = str(record.get("entity_id", "")).strip()
    record_entity_code = str(record.get("entity_code", "")).strip()
    if entity_id:
        return bool(record_entity_id) and record_entity_id == entity_id
    if entity_code:
        return bool(record_entity_code) and record_entity_code == entity_code
    return False


def require_record_entity_access(record: dict[str, Any], context: dict[str, Any] | None = None, label: str = "Record") -> None:
    if not record_entity_matches(record, context):
        raise ValueError(f"{label} does not belong to the current Entity. Please switch Entity from Portal before operating it.")


def scope_records_to_current_entity(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    entity = context_current_entity(context)
    if not entity:
        return records
    return [record for record in records if record_entity_matches(record, context)]


def h(value: Any) -> str:
    return escape(str(value if value is not None else ""), quote=True)


def load_i18n(lang: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    for candidate in ("en", lang):
        path = I18N_DIR / f"{candidate}.json"
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            messages.update({str(key): str(value) for key, value in data.items()})
    return messages


def t(messages: dict[str, str] | None, key: str, default: str | None = None) -> str:
    if messages and key in messages:
        return messages[key]
    if default is not None:
        return default
    fallback = load_i18n("en")
    return fallback.get(key, key)


def get_lang_from_query(query: dict[str, list[str]]) -> str:
    lang = query.get("lang", [DEFAULT_LANG])[0].strip().lower()
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def url_with_lang(path: str, lang: str, params: dict[str, Any] | None = None) -> str:
    params = {key: value for key, value in (params or {}).items() if value not in {None, ""}}
    params["lang"] = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    return f"{path}?{urlencode(params)}"


def context_lang(context: dict[str, Any] | None) -> str:
    if context and str(context.get("lang", "")) in SUPPORTED_LANGS:
        return str(context.get("lang"))
    return DEFAULT_LANG


def context_messages(context: dict[str, Any] | None) -> dict[str, str]:
    if context and isinstance(context.get("messages"), dict):
        return context["messages"]
    return load_i18n(DEFAULT_LANG)


def enum_label(messages: dict[str, str], prefix: str, value_text: Any) -> str:
    value_string = str(value_text if value_text is not None else "")
    return t(messages, f"enum.{prefix}.{value_string}", value_string)


def language_switcher_html(lang: str, current_path: str = "/") -> str:
    messages = load_i18n(lang)
    links = []
    for candidate in ["zh", "ja", "en"]:
        label = t(messages, f"language.{candidate}", candidate)
        class_name = "pill" if candidate == lang else "button secondary"
        links.append(f'<a class="{class_name}" href="{h(url_with_lang(current_path, candidate))}">{h(label)}</a>')
    return "".join(links)


class TACTimesheetHandler(BaseHTTPRequestHandler):
    server_version = "TACTimesheetWeb/0.1"

    @property
    def request_host(self) -> str:
        """Return the request Host header hostname (without port)."""
        raw = self.headers.get("Host", "")
        return raw.split(":", 1)[0] if raw else "127.0.0.1"

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        host = (parsed.hostname or "").lower()
        if host in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS:
            return True
        return parsed.scheme == "https" and host in PUBLIC_ALLOWED_HOSTS and parsed.port in {None, 443}

    def current_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return session_cookie.value if session_cookie else ""

    def current_user(self) -> dict[str, Any] | None:
        return validate_user_admin_session(self.current_session_id())

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

    def request_context(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> dict[str, Any]:
        current_entity = current_entity_from_user(user)
        return {
            "lang": lang,
            "messages": messages,
            "user": user,
            "current_entity": current_entity,
            "portal_url": resolve_portal_url(self.request_host),
            "session_id": self.current_session_id(),
            "flash": self.flash_message(),
            "current_path": urlparse(self.path).path,
        }

    def require_user_admin_access(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.send_response(303)
            self.send_header("Location", f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            self.end_headers()
            return None
        if not has_required_module_access(user):
            self.send_error(403, "This User_admin account does not have permission to access Timesheet.")
            return None
        if not current_entity_from_user(user):
            self.send_response(403)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            body = f"""<!doctype html><html><head><meta charset='utf-8'><title>Entity Required - TAC-timesheet</title></head><body><main style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;max-width:720px;margin:40px auto;padding:20px;'><h1>Current Entity is required</h1><p>Please return to Portal/User_admin and select or switch Entity before opening TAC-timesheet.</p><p><a href='{h(PORTAL_BASE_URL)}'>Back to Portal</a></p></main></body></html>""".encode("utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return None
        return user

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        if path == "/health":
            self._send_text("OK")
            return
        if path == "/api/payroll/attendance-summary":
            user = self.require_user_admin_access()
            if not user:
                return
            month = query.get("month", [""])[0].strip()
            entity_id = query.get("entity_id", [""])[0].strip()
            country_code = query.get("country_code", ["SG"])[0].strip().upper()
            if not month:
                self._send_json({"ok": False, "error": "month parameter required"}, 400)
                return
            entries = load_timesheet_entries()
            # Filter by month and entity
            month_entries = [e for e in entries if str(e.get("work_date", "")).startswith(month) and e.get("record_status") != "deleted"]
            if entity_id:
                month_entries = [e for e in month_entries if str(e.get("entity_id", "")).upper() == entity_id.upper()]
            # Aggregate by employee using employee_id from record
            employee_agg: dict[str, dict[str, Any]] = {}
            for e in month_entries:
                eid = str(e.get("employee_id") or e.get("employee_no") or "")
                if not eid:
                    continue
                if eid not in employee_agg:
                    employee_agg[eid] = {
                        "employee_id": eid,
                        "employee_number": str(e.get("employee_no", eid)),
                        "employee_name": str(e.get("employee_name", "")),
                        "entity_id": str(e.get("entity_id", "")),
                        "total_work_days": 0,
                        "total_work_hours": 0.0,
                        "total_overtime_hours": 0.0,
                        "total_late_night_hours": 0.0,
                        "total_holiday_hours": 0.0,
                        "total_paid_leave_days": 0.0,
                        "total_unpaid_leave_days": 0.0,
                        "absence_days": 0.0,
                    }
                agg = employee_agg[eid]
                actual_min = float(e.get("actual_work_minutes", 0) or 0)
                ot_min = float(e.get("overtime_minutes", 0) or 0)
                night_min = float(e.get("night_work_minutes", 0) or 0)
                holiday_min = float(e.get("holiday_work_minutes", 0) or 0)
                if actual_min > 0:
                    agg["total_work_days"] += 1
                    agg["total_work_hours"] += round(actual_min / 60.0, 2)
                if ot_min > 0:
                    agg["total_overtime_hours"] += round(ot_min / 60.0, 2)
                if night_min > 0:
                    agg["total_late_night_hours"] += round(night_min / 60.0, 2)
                if holiday_min > 0:
                    agg["total_holiday_hours"] += round(holiday_min / 60.0, 2)
                # Check attendance status for leave/absence
                att_status = str(e.get("attendance_status", "")).lower()
                if att_status in ("paid_leave", "paid leave", "有給休暇"):
                    agg["total_paid_leave_days"] += 1
                elif att_status in ("unpaid_leave", "unpaid leave", "無給休暇"):
                    agg["total_unpaid_leave_days"] += 1
                elif att_status in ("absence", "absent", "欠勤"):
                    agg["absence_days"] += 1
            self._send_json({"ok": True, "month": month, "country_code": country_code, "entity_id": entity_id, "employees": list(employee_agg.values())})
            return
        user = self.require_user_admin_access()
        if not user:
            return
        context = self.request_context(lang, messages, user)
        if path == "/":
            self._send_html(page(t(messages, "nav.dashboard"), dashboard_html(context), context))
            return
        if path == "/clock-entry":
            selected_date = query.get("work_date", [""])[0].strip()
            selected_employee_no = query.get("employee_no", [""])[0].strip()
            record = default_clock_entry_record(context, selected_date, selected_employee_no) if selected_date or selected_employee_no else None
            self._send_html(page(t(messages, "clock_entry.title"), clock_entry_form_html(record=record, context=context), context))
            return
        if path == "/my-timesheet":
            self._send_html(page(t(messages, "nav.my_timesheet"), my_timesheet_html(query, context), context))
            return
        if path == "/timesheets":
            self._send_html(page(t(messages, "nav.timesheets"), timesheets_html(query, context), context))
            return
        if path == "/timesheets.csv":
            filters = timesheet_filters_from_query(query)
            self._send_csv(timesheets_csv_text(query, context), timesheet_export_filename(filters))
            return
        if path == "/timesheet-new":
            self._send_html(page(t(messages, "nav.timesheet_new"), timesheet_form_html(context=context), context))
            return
        if path == "/timesheet-edit":
            record_id = query.get("id", [""])[0].strip()
            record = find_timesheet_entry(record_id)
            if not record:
                self.send_error(404, "Timesheet record not found")
                return
            try:
                require_record_entity_access(record, context, "Timesheet")
                ensure_record_editable(record)
                ensure_record_month_not_locked(record, context)
            except ValueError as exc:
                self._send_html(page("Timesheet Not Editable", error_message_html(str(exc), context) + timesheets_html({}, context), context), status=400)
                return
            self._send_html(page(t(messages, "timesheet.edit_title"), timesheet_form_html(record=record, mode="edit", context=context), context))
            return
        if path == "/employees":
            self._send_html(page(t(messages, "nav.employees"), employees_html(context), context))
            return
        if path in {"/employee-new", "/employee-edit"}:
            self._send_html(page(t(messages, "employee.source_title"), error_message_html(t(messages, "employee.managed_in_employeeadmin", "Employee master is managed in TAC-employeeadmin."), context) + employees_html(context), context), status=400)
            return
        if path == "/organization":
            self._send_html(page(t(messages, "nav.organization"), organization_html(context), context))
            return
        if path == "/entities":
            self._send_html(page(t(messages, "nav.entities"), entities_html(context), context))
            return
        if path == "/entity-new":
            self._send_html(page(t(messages, "entity.new_title"), entity_form_html(context=context), context))
            return
        if path == "/entity-edit":
            entity_id = query.get("id", [""])[0].strip()
            record = find_entity(entity_id)
            if not record:
                self.send_error(404, "Entity record not found")
                return
            require_record_entity_access(record, context, "Entity")
            self._send_html(page(t(messages, "entity.edit_title"), entity_form_html(record=record, mode="edit", context=context), context))
            return
        if path == "/departments":
            self._send_html(page(t(messages, "nav.departments"), departments_html(context), context))
            return
        if path == "/department-new":
            self._send_html(page(t(messages, "department.new_title"), department_form_html(context=context), context))
            return
        if path == "/department-edit":
            department_id = query.get("id", [""])[0].strip()
            record = find_department(department_id)
            if not record:
                self.send_error(404, "Department record not found")
                return
            require_record_entity_access(record, context, "Department")
            self._send_html(page(t(messages, "department.edit_title"), department_form_html(record=record, mode="edit", context=context), context))
            return
        if path == "/teams":
            self._send_html(page(t(messages, "nav.teams"), teams_html(query, context), context))
            return
        if path == "/team-new":
            self._send_html(page(t(messages, "team.new_title"), team_form_html(context=context), context))
            return
        if path == "/team-edit":
            team_id = query.get("id", [""])[0].strip()
            record = find_team(team_id)
            if not record:
                self.send_error(404, "Team record not found")
                return
            require_record_entity_access(record, context, "Team")
            self._send_html(page(t(messages, "team.edit_title"), team_form_html(record=record, mode="edit", context=context), context))
            return
        if path == "/projects":
            self._send_html(page("Projects", projects_html(context), context))
            return
        if path == "/billing":
            self._send_html(page("Billing", billing_html(query, context), context))
            return
        if path == "/invoices":
            self._send_html(page("Invoices", invoices_html(query, context), context))
            return
        if path == "/audit-logs":
            self._send_html(page("Audit Logs", audit_logs_html(query, context), context))
            return
        if path == "/project-new":
            self._send_html(page("New Project", project_form_html(context=context), context))
            return
        if path == "/project-edit":
            project_id = query.get("id", [""])[0].strip()
            record = find_project(project_id)
            if not record:
                self.send_error(404, "Project record not found")
                return
            require_record_entity_access(record, context, "Project")
            self._send_html(page("Edit Project", project_form_html(record=record, mode="edit", context=context), context))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        if not self.csrf_origin_allowed():
            self.send_error(403, "Invalid request origin")
            return
        user = self.require_user_admin_access()
        if not user:
            return
        context = self.request_context(lang, messages, user)
        try:
            form = self._parse_request_form()
            actor = audit_actor_from_user(user)
            if path == "/clock-entry":
                selected_employee_no = form.get("employee_no", "").strip()
                is_proxy_clock_entry = bool(selected_employee_no) and not is_own_employee_record(selected_employee_no, context)
                if is_proxy_clock_entry and not can_proxy_submit(user):
                    self.send_error(403, "Missing timesheet.proxy_submit permission")
                    return
                if not is_proxy_clock_entry and not can_submit_self(user) and not can_proxy_submit(user):
                    self.send_error(403, "Missing timesheet.submit_self permission")
                    return
                saved = save_clock_entry_from_form(form, actor=actor, context=context)
                self._send_html(page(t(messages, "clock_entry.title"), clock_entry_form_html(record=saved, context=context, message=t(messages, "clock_entry.saved_message")), context))
                return
            if path == "/timesheet-new":
                record = timesheet_record_from_form(form)
                is_proxy = not is_own_employee_record(record, context)
                if is_proxy and not can_proxy_submit(user):
                    self.send_error(403, "Missing timesheet.proxy_submit permission")
                    return
                if not is_proxy and not can_submit_self(user):
                    self.send_error(403, "Missing timesheet.submit_self permission")
                    return
                record = apply_timesheet_entry_metadata(record, form, actor, context)
                saved = save_timesheet_entry(record, actor=actor, context=context)
                self._send_html(page(t(messages, "timesheet.saved_title"), timesheet_saved_html(saved, message=operation_success_message("Timesheet", timesheet_record_label(saved), "saved", actor, lang), context=context), context))
                return
            if path == "/timesheet-edit":
                record_id = form.get("record_id", "").strip()
                existing = find_timesheet_entry(record_id)
                if not existing:
                    raise ValueError("Timesheet record was not found.")
                require_record_entity_access(existing, context, "Timesheet")
                is_proxy = not is_own_employee_record(existing, context)
                if is_proxy and not can_proxy_edit_timesheet(user):
                    self.send_error(403, "Missing timesheet.proxy_edit permission")
                    return
                if not is_proxy and not can_edit_own_timesheet(user):
                    self.send_error(403, "Missing timesheet.edit_own permission")
                    return
                record = timesheet_update_from_form(existing, form)
                record = apply_timesheet_entry_metadata(record, form, actor, context, existing=existing)
                saved = update_timesheet_entry(record, actor=actor, context=context)
                message = no_change_message("Timesheet", timesheet_record_label(saved), lang) if saved.get("_no_changes") else operation_success_message("Timesheet", timesheet_record_label(saved), "saved", actor, lang)
                self._send_html(page("Timesheet Updated", timesheet_saved_html(saved, message=message, context=context), context))
                return
            if path == "/timesheet-delete":
                record_id = form.get("record_id", "").strip()
                existing = find_timesheet_entry(record_id)
                if not existing:
                    message = "Timesheet record was not found."
                else:
                    require_record_entity_access(existing, context, "Timesheet")
                    if not can_delete_timesheet(user, existing, context):
                        self.send_error(403, "Missing timesheet delete/proxy permission")
                        return
                    deleted = soft_delete_timesheet_entry(record_id, actor=actor, context=context)
                    message = operation_success_message("Timesheet", record_id, "deleted", actor, lang) if deleted else "Timesheet record was not found."
                self._send_html(page(t(messages, "nav.timesheets"), status_message_html(message, context) + timesheets_html({}, context), context))
                return
            if path == "/timesheet-submit":
                if not has_permission(user, "timesheet.submit"):
                    self.send_error(403, "Missing timesheet.submit permission")
                    return
                submit_timesheet_record(form.get("record_id", ""), actor=actor, context=context)
                record_id = form.get("record_id", "").strip()
                self._send_html(page("Timesheet Submitted", status_message_html(operation_success_message("Timesheet", record_id, "submitted", actor, lang), context) + timesheets_html({}, context), context))
                return
            if path == "/timesheet-approve":
                if not has_permission(user, "timesheet.approve"):
                    self.send_error(403, "Missing timesheet.approve permission")
                    return
                approve_timesheet_record(form.get("record_id", ""), actor=actor, context=context)
                record_id = form.get("record_id", "").strip()
                self._send_html(page("Timesheet Approved", status_message_html(operation_success_message("Timesheet", record_id, "approved", actor, lang), context) + timesheets_html({}, context), context))
                return
            if path == "/timesheet-reject":
                if not has_permission(user, "timesheet.approve"):
                    self.send_error(403, "Missing timesheet.approve permission")
                    return
                reject_timesheet_record(form.get("record_id", ""), form.get("reject_reason", ""), actor=actor, context=context)
                record_id = form.get("record_id", "").strip()
                self._send_html(page("Timesheet Rejected", status_message_html(operation_success_message("Timesheet", record_id, "rejected", actor, lang), context) + timesheets_html({}, context), context))
                return
            if path == "/timesheet-reopen":
                if not has_permission(user, "timesheet.approve"):
                    self.send_error(403, "Missing timesheet.approve permission")
                    return
                reopen_timesheet_record(form.get("record_id", ""), actor=actor, context=context)
                record_id = form.get("record_id", "").strip()
                self._send_html(page("Timesheet Reopened", status_message_html(operation_success_message("Timesheet", record_id, "reopened", actor, lang), context) + timesheets_html({}, context), context))
                return
            if path in {"/month-lock", "/timesheet-period-close"}:
                if not has_permission(user, "timesheet.approve"):
                    self.send_error(403, "Missing timesheet.approve permission")
                    return
                work_month = form.get("work_month", "").strip()
                close_timesheet_period(work_month, form.get("notes", ""), actor=actor, context=context)
                self._send_html(page(t(messages, "period.closed_title", "Period Closed"), status_message_html(t(messages, "period.closed_message", "Timesheet period closed.").format(work_month=work_month), context) + timesheets_html({"work_month": [work_month]}, context), context))
                return
            if path == "/timesheet-period-open":
                if not has_permission(user, "timesheet.approve"):
                    self.send_error(403, "Missing timesheet.approve permission")
                    return
                work_month = form.get("work_month", "").strip()
                open_timesheet_period(work_month, form.get("notes", ""), actor=actor, context=context)
                self._send_html(page(t(messages, "period.opened_title", "Period Opened"), status_message_html(t(messages, "period.opened_message", "Timesheet period opened.").format(work_month=work_month), context) + timesheets_html({"work_month": [work_month]}, context), context))
                return
            if path in {"/employee-new", "/employee-edit", "/employee-delete"}:
                message = t(messages, "employee.managed_in_employeeadmin", "Employee master is managed in TAC-employeeadmin.")
                self._send_html(page(t(messages, "employee.source_title"), error_message_html(message, context) + employees_html(context), context), status=400)
                return
            if path == "/entity-new":
                record = entity_fields_from_form(form)
                saved = save_entity(record, actor=actor)
                self._send_html(page(t(messages, "entity.saved_title"), organization_saved_html(saved, "entity.saved_title", "entity.saved_message", "/entities", "/entity-new", context), context))
                return
            if path == "/entity-edit":
                entity_id = form.get("entity_id", "").strip()
                existing = find_entity(entity_id)
                if not existing:
                    raise ValueError("Entity record was not found.")
                require_record_entity_access(existing, context, "Entity")
                record = entity_update_from_form(existing, form)
                saved = update_entity(record, actor=actor)
                self._send_html(page(t(messages, "entity.saved_title"), organization_saved_html(saved, "entity.saved_title", "entity.updated_message", "/entities", "/entity-new", context), context))
                return
            if path == "/entity-delete":
                entity_record = find_entity(form.get("entity_id", ""))
                if entity_record:
                    require_record_entity_access(entity_record, context, "Entity")
                deleted = soft_delete_entity(form.get("entity_id", ""), actor=actor)
                entity_id = form.get("entity_id", "").strip()
                message = operation_success_message("Entity", entity_id, "deleted", actor, lang) if deleted else t(messages, "entity.not_found")
                self._send_html(page(t(messages, "nav.entities"), status_message_html(message, context) + entities_html(context), context))
                return
            if path == "/department-new":
                record = apply_current_entity_snapshot(department_fields_from_form(form), context)
                saved = save_department(record, actor=actor)
                self._send_html(page(t(messages, "department.saved_title"), organization_saved_html(saved, "department.saved_title", "department.saved_message", "/departments", "/department-new", context), context))
                return
            if path == "/department-edit":
                department_id = form.get("department_id", "").strip()
                existing = find_department(department_id)
                if not existing:
                    raise ValueError("Department record was not found.")
                require_record_entity_access(existing, context, "Department")
                record = apply_current_entity_snapshot(department_update_from_form(existing, form), context)
                saved = update_department(record, actor=actor)
                self._send_html(page(t(messages, "department.saved_title"), organization_saved_html(saved, "department.saved_title", "department.updated_message", "/departments", "/department-new", context), context))
                return
            if path == "/department-delete":
                department_record = find_department(form.get("department_id", ""))
                if department_record:
                    require_record_entity_access(department_record, context, "Department")
                deleted = soft_delete_department(form.get("department_id", ""), actor=actor)
                department_id = form.get("department_id", "").strip()
                message = operation_success_message("Department", department_id, "deleted", actor, lang) if deleted else t(messages, "department.not_found")
                self._send_html(page(t(messages, "nav.departments"), status_message_html(message, context) + departments_html(context), context))
                return
            if path == "/team-new":
                record = apply_current_entity_snapshot(team_fields_from_form(form), context)
                saved = save_team(record, actor=actor)
                self._send_html(page(t(messages, "team.saved_title"), organization_saved_html(saved, "team.saved_title", "team.saved_message", "/teams", "/team-new", context), context))
                return
            if path == "/team-edit":
                team_id = form.get("team_id", "").strip()
                existing = find_team(team_id)
                if not existing:
                    raise ValueError("Team record was not found.")
                require_record_entity_access(existing, context, "Team")
                record = apply_current_entity_snapshot(team_update_from_form(existing, form), context)
                saved = update_team(record, actor=actor)
                self._send_html(page(t(messages, "team.saved_title"), organization_saved_html(saved, "team.saved_title", "team.updated_message", "/teams", "/team-new", context), context))
                return
            if path == "/team-delete":
                team_record = find_team(form.get("team_id", ""))
                if team_record:
                    require_record_entity_access(team_record, context, "Team")
                deleted = soft_delete_team(form.get("team_id", ""), actor=actor)
                team_id = form.get("team_id", "").strip()
                message = operation_success_message("Team", team_id, "deleted", actor, lang) if deleted else t(messages, "team.not_found")
                self._send_html(page(t(messages, "nav.teams"), status_message_html(message, context) + teams_html({}, context), context))
                return
            if path == "/project-new":
                record = project_fields_from_form(form)
                saved = save_project(record, actor=actor, context=context)
                self._send_html(page("Project Saved", project_saved_html(saved, message=operation_success_message("Project", project_record_label(saved), "saved", actor, lang), context=context), context))
                return
            if path == "/project-edit":
                project_id = form.get("project_id", "").strip()
                existing = find_project(project_id)
                if not existing:
                    raise ValueError("Project record was not found.")
                require_record_entity_access(existing, context, "Project")
                record = project_update_from_form(existing, form)
                saved = update_project(record, actor=actor, context=context)
                message = no_change_message("Project", project_record_label(saved), lang) if saved.get("_no_changes") else operation_success_message("Project", project_record_label(saved), "saved", actor, lang)
                self._send_html(page("Project Updated", project_saved_html(saved, message=message, context=context), context))
                return
            if path == "/project-delete":
                project_record = find_project(form.get("project_id", ""))
                if project_record:
                    require_record_entity_access(project_record, context, "Project")
                deleted = soft_delete_project(form.get("project_id", ""), actor=actor, context=context)
                project_id = form.get("project_id", "").strip()
                message = operation_success_message("Project", project_id, "deleted", actor, lang) if deleted else "Project record was not found."
                self._send_html(page("Projects", status_message_html(message, context) + projects_html(context), context))
                return
            if path == "/invoice-draft-create":
                draft = create_invoice_draft_from_billing_summary(form.get("work_month", ""), form.get("customer_name", ""), form.get("project_code", ""), actor=actor, context=context)
                self._send_html(page("Invoice Draft Created", status_message_html(f"Invoice draft {draft.get('invoice_no', '')} created.", context) + invoices_html({}, context), context))
                return
            if path == "/invoice-draft-void":
                draft = void_invoice_draft(form.get("invoice_id", ""), form.get("void_reason", ""), actor=actor, context=context)
                self._send_html(page("Invoice Draft Voided", status_message_html(f"Invoice draft {draft.get('invoice_no', '')} voided.", context) + invoices_html({"include_voided": ["true"]}, context), context))
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001 - local MVP should show concise operational errors.
            error_html = error_message_html(str(exc), context if "context" in locals() else None)
            if path == "/clock-entry":
                fallback_record = default_clock_entry_record(context)
                if "form" in locals():
                    fallback_record["start_time"] = form.get("start_time", "").strip()
                    fallback_record["end_time"] = form.get("end_time", "").strip()
                    fallback_record["break_minutes"] = form.get("break_minutes", "60").strip() or 60
                self._send_html(page(t(messages, "clock_entry.title"), clock_entry_form_html(record=fallback_record, context=context, error_message=str(exc)), context), status=400)
            elif path in {"/timesheet-delete", "/timesheet-submit", "/timesheet-approve", "/timesheet-reject", "/timesheet-reopen", "/month-lock", "/timesheet-period-close", "/timesheet-period-open"}:
                self._send_html(page("Timesheet Workflow Error", error_html + timesheets_html({}, context), context), status=400)
            elif path == "/timesheet-edit":
                existing = find_timesheet_entry(form.get("record_id", "")) if "form" in locals() else None
                if existing and approval_status(existing) in {"Draft", "Rejected"} and not record_month_is_locked(existing, context):
                    self._send_html(page("Timesheet Input Error", error_html + timesheet_form_html(record=existing, mode="edit", context=context), context), status=400)
                else:
                    self._send_html(page("Timesheet Input Error", error_html + timesheets_html({}, context), context), status=400)
            elif path.startswith("/entity"):
                existing = find_entity(form.get("entity_id", "")) if "form" in locals() else None
                body = error_html + entity_form_html(record=existing, mode="edit" if existing else "new", context=context)
                self._send_html(page(t(messages, "error.input_title"), body, context), status=400)
            elif path.startswith("/department"):
                existing = find_department(form.get("department_id", "")) if "form" in locals() else None
                body = error_html + department_form_html(record=existing, mode="edit" if existing else "new", context=context)
                self._send_html(page(t(messages, "error.input_title"), body, context), status=400)
            elif path.startswith("/team"):
                existing = find_team(form.get("team_id", "")) if "form" in locals() else None
                body = error_html + team_form_html(record=existing, mode="edit" if existing else "new", context=context)
                self._send_html(page(t(messages, "error.input_title"), body, context), status=400)
            elif path.startswith("/employee"):
                existing = find_employee(form.get("employee_id", "")) if "form" in locals() else None
                self._send_html(page("Employee Input Error", error_html + employee_form_html(record=existing, mode="edit" if existing else "new", context=context), context), status=400)
            elif path.startswith("/project"):
                existing = find_project(form.get("project_id", "")) if "form" in locals() else None
                self._send_html(page("Project Input Error", error_html + project_form_html(record=existing, mode="edit" if existing else "new", context=context), context), status=400)
            elif path.startswith("/invoice"):
                self._send_html(page("Invoice Error", error_html + invoices_html({"include_voided": ["true"]}, context), context), status=400)
            else:
                self._send_html(page("Timesheet Input Error", error_html + timesheet_form_html(context=context), context), status=400)

    def _parse_request_form(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}

    def _send_html(self, html: str, status: int = 200) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if self.flash_message():
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_redirect(self, location: str, flash: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_text(self, text: str, status: int = 200) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: dict[str, Any], status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_csv(self, text: str, filename: str, status: int = 200) -> None:
        payload = text.encode("utf-8-sig")
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def current_user_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    user = (context or {}).get("user") or {}
    if not user:
        return ""
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    account = str(user.get("username") or user.get("email") or user.get("display_name") or user.get("user_id") or "User")
    display_name = str(user.get("display_name") or account)
    entity_label = current_entity_label(context)
    login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
    return (
        f'<span class="current-user-chip" title="{h(t(messages, "field.login_time", "Login Time"))}: {h(login_time)}">'
        f'<strong>👤 {h(t(messages, "field.current_user", "Current User"))}: {h(account)}</strong>'
        f'<small>{h(display_name)}</small>'
        f'<small>🏢 {h(t(messages, "field.current_entity", "Current Entity"))}: {h(entity_label)}</small>'
        f'<small>{h(t(messages, "field.login_time", "Login Time"))}: {h(login_time)}</small>'
        f'</span>'
    )


def page(title: str, body: str, context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    messages = context_messages(context)
    nav_links = [
        ("/", "nav.dashboard"),
        ("/clock-entry", "nav.clock_entry"),
        ("/my-timesheet", "nav.my_timesheet"),
        ("/timesheet-new", "nav.timesheet_new"),
        ("/timesheets", "nav.timesheets"),
        ("/projects", "nav.projects"),
        ("/organization", "nav.organization"),
        ("/billing", "nav.billing"),
        ("/invoices", "nav.invoices"),
        ("/audit-logs", "nav.audit_logs"),
    ]
    current_path = str((context or {}).get("current_path", "/"))
    nav_html = "".join(
        f'<a class="{h("active" if path == current_path else "")}" href="{h(url_with_lang(path, lang))}">{h(t(messages, key))}</a>'
        for path, key in nav_links
    )
    language_html = language_switcher_html(lang, current_path)
    user_html = current_user_html(context)
    portal_url = str((context or {}).get("portal_url") or PORTAL_BASE_URL)
    portal_html = (
        f'<a class="portal-link" href="{h(portal_url)}" title="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" '
        f'aria-label="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{h(t(messages, "nav.portal", "Back to Portal"))}</a>'
    )
    flash = str((context or {}).get("flash", ""))
    flash_html = f'<section class="message-strip message-success" role="status">{h(flash)}</section>' if flash else ""
    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)} - TAC-timesheet</title>
  <style>
    :root {{ --navy: #14213d; --blue: #1f6feb; --bg: #f6f8fb; --card: #ffffff; --line: #d8dee9; --muted: #65758b; --green: #0f766e; --amber: #b45309; --red: #b91c1c; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: #17202a; }}
    header {{ background: var(--navy); color: white; padding: 22px 32px; }}
    header h1 {{ margin: 0 0 6px; }}
    header p {{ margin: 0; color: #dbeafe; }}
    nav {{ display: flex; align-items: center; gap: 8px; flex-wrap: wrap; padding: 10px 32px; background: white; border-bottom: 1px solid var(--line); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    nav a {{ display: inline-flex; align-items: center; justify-content: center; min-height: 34px; color: #223548; background: #f7f9fb; text-decoration: none; border: 1px solid transparent; padding: 0 13px; border-radius: 8px; font-size: 0.92rem; font-weight: 760; line-height: 1; white-space: nowrap; transition: background-color .16s ease, border-color .16s ease, color .16s ease, box-shadow .16s ease; }}
    nav a:hover {{ background: #eef6ff; border-color: #91c8f6; color: #0a6ed1; }}
    nav a.active {{ background: #e5f2fd; border-color: #0a6ed1; color: #0a6ed1; box-shadow: inset 0 -2px 0 #0a6ed1; }}
    nav a.portal-link {{ gap: 0.35rem; color: #0b4f8a; background: linear-gradient(180deg, #f8fbff 0%, #eaf4ff 100%); border-color: #9cc7f2; box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 1px 2px rgba(15,23,42,.08); }}
    nav a.portal-link:hover {{ color: #064b86; border-color: #1f6feb; background: #ffffff; }}
    .portal-icon {{ font-size: 1rem; line-height: 1; }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 28px 20px 48px; }}
    .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 16px; }}
    .form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 14px; }}
    .card, .panel {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); }}
    .card h3, .panel h2, .panel h3 {{ margin-top: 0; }}
    .metric {{ font-size: 2rem; font-weight: 850; color: var(--navy); }}
    .muted {{ color: var(--muted); }}
    .good {{ color: var(--green); font-weight: 800; }}
    .warn {{ color: var(--amber); font-weight: 800; }}
    .error {{ color: var(--red); font-weight: 800; }}
    table {{ width: 100%; border-collapse: collapse; background: white; border: 1px solid var(--line); border-radius: 12px; overflow: hidden; }}
    th, td {{ border-bottom: 1px solid var(--line); padding: 10px 12px; text-align: left; vertical-align: top; }}
    th {{ background: #eef4ff; color: var(--navy); font-size: 0.9rem; }}
    td.num, th.num {{ text-align: right; font-variant-numeric: tabular-nums; }}
    tr:last-child td {{ border-bottom: 0; }}
    label {{ display: block; font-weight: 800; margin-bottom: 6px; }}
    input, select, textarea {{ box-sizing: border-box; width: 100%; border: 1px solid #c8d1dc; border-radius: 8px; padding: 9px 10px; font: inherit; }}
    textarea {{ min-height: 88px; resize: vertical; }}
    .actions {{ margin: 18px 0; display: flex; gap: 10px; flex-wrap: wrap; }}
    .button, button {{ display: inline-block; background: var(--blue); color: white; padding: 10px 14px; border-radius: 8px; border: 0; text-decoration: none; font-weight: 800; cursor: pointer; }}
    .button.secondary, button.secondary {{ background: #475569; }}
    .button.success, button.success {{ background: var(--green); }}
    .button.warning, button.warning {{ background: var(--amber); }}
    .button.danger, button.danger {{ background: var(--red); }}
    .button.ghost {{ background: white; color: var(--navy); border: 1px solid var(--line); }}
    .language-switcher {{ margin-left: auto; display: flex; align-items: center; gap: 6px; flex: 0 0 auto; }}
    .current-user-chip {{ display: grid; gap: 2px; min-width: 180px; padding: 7px 10px; background: #fff; border: 1px solid #d6e4f2; border-radius: 12px; color: var(--navy); box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
    .current-user-chip strong {{ font-size: .9rem; }}
    .current-user-chip small {{ color: var(--muted); font-size: .76rem; }}
    .language-switcher .pill, .language-switcher .button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 30px; padding: 0 10px; border-radius: 8px; font-size: 0.8rem; line-height: 1; }}
    .language-switcher .button.secondary {{ background: #eef2f7; color: #223548; border: 1px solid #d6e0eb; }}
    .pill, .status-badge {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #ecfeff; color: #155e75; font-weight: 800; }}
    .status-draft {{ background: #f1f5f9; color: #334155; }}
    .status-submitted {{ background: #dbeafe; color: #1d4ed8; }}
    .status-approved {{ background: #dcfce7; color: #166534; }}
    .status-rejected {{ background: #fef3c7; color: #92400e; }}
    .notice, .message-strip {{ border-left: 4px solid var(--blue); background: #eff6ff; padding: 12px 14px; border-radius: 8px; }}
    .message-warning {{ border-left-color: var(--amber); background: #fffbeb; }}
    .message-success {{ border-left-color: var(--green); background: #ecfdf5; }}
    .sap-confirm-backdrop {{ position: fixed; inset: 0; background: rgba(15,23,42,.48); display: none; align-items: center; justify-content: center; padding: 1rem; z-index: 50; }}
    .sap-confirm-backdrop.active {{ display: flex; }}
    .sap-confirm-dialog {{ width: min(460px, 100%); background: white; border-radius: 18px; border: 1px solid var(--line); box-shadow: 0 24px 80px rgba(15,23,42,.28); padding: 1.2rem; }}
    .wide {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; }}
    .sap-page-header {{ background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); border: 1px solid var(--line); border-radius: 16px; padding: 20px; margin-bottom: 18px; }}
    .sap-page-header h2 {{ margin: 0 0 8px; color: var(--navy); }}
    .sap-object-meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; }}
    .sap-section {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; margin-top: 16px; }}
    .sap-section h3 {{ margin: 0 0 14px; color: var(--navy); }}
    .sap-toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; justify-content: flex-end; padding-top: 16px; border-top: 1px solid var(--line); margin-top: 18px; }}
    .sap-readonly-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .sap-readonly-field {{ background: #f8fafc; border: 1px solid var(--line); border-radius: 10px; padding: 12px; }}
    .sap-readonly-field .label {{ color: var(--muted); font-size: .82rem; font-weight: 800; margin-bottom: 4px; }}
    .sap-readonly-field .value {{ color: var(--navy); font-weight: 850; }}
    .form-field {{ margin-bottom: 0.85rem; }}
    .form-field label {{ color: #334155; font-size: 0.9rem; }}
    input:focus, select:focus, textarea:focus {{ outline: 3px solid rgba(31, 111, 235, 0.18); border-color: var(--blue); }}
    .object-page {{ display: grid; gap: 0.85rem; }}
    .object-header {{ border: 1px solid var(--line); border-radius: 16px; background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); box-shadow: 0 1px 2px rgba(15, 23, 42, 0.04); padding: 18px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 0.75fr); gap: 1rem; align-items: start; }}
    .object-header h2 {{ margin: 0 0 8px; color: var(--navy); }}
    .eyebrow {{ margin: 0 0 4px; color: var(--blue); font-size: 0.74rem; font-weight: 850; letter-spacing: 0.055em; text-transform: uppercase; }}
    .object-meta {{ display: grid; gap: 0.45rem; grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }}
    .meta-chip {{ border: 1px solid #d6e4f2; border-radius: 12px; background: rgba(255,255,255,0.82); padding: 9px 10px; min-width: 0; }}
    .meta-chip-label {{ display: block; color: var(--muted); font-size: 0.68rem; font-weight: 850; letter-spacing: 0.035em; text-transform: uppercase; margin-bottom: 3px; }}
    .meta-chip-value {{ display: block; color: #0f172a; font-weight: 800; overflow-wrap: anywhere; }}
    .section-header {{ padding: 0.78rem 1rem; border-bottom: 1px solid var(--line); background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%); }}
    .section-header h3 {{ margin: 0; color: var(--navy); }}
    .section-body {{ padding: 1rem; }}
    .table-scroll {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; }}
    .hierarchy-list {{ display: grid; gap: 12px; }}
    .hierarchy-entity {{ border: 1px solid var(--line); border-radius: 14px; background: white; padding: 14px; }}
    .hierarchy-department {{ margin: 10px 0 0 18px; border-left: 3px solid #dbeafe; padding-left: 12px; }}
    .hierarchy-team {{ margin: 6px 0 0 18px; color: var(--muted); }}
    .clock-entry-card {{ max-width: 560px; margin: 0 auto; }}
    .clock-entry-hero {{ background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); border: 1px solid var(--line); border-radius: 18px; padding: 20px; margin-bottom: 16px; }}
    .clock-entry-hero h2 {{ margin: 0 0 8px; color: var(--navy); }}
    .clock-entry-grid {{ display: grid; gap: 16px; }}
    .clock-entry-field input {{ min-height: 52px; font-size: 1.15rem; font-weight: 750; }}
    .clock-entry-submit {{ width: 100%; min-height: 52px; font-size: 1.08rem; }}
    .quick-break-actions {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 8px; }}
    .quick-break-actions button {{ background: white; color: var(--navy); border: 1px solid var(--line); padding: 9px 8px; }}
    .my-day-list {{ display: grid; gap: 10px; }}
    .my-day-card {{ display: grid; grid-template-columns: 1.1fr 1.4fr 1fr 1fr auto; gap: 12px; align-items: center; background: #fff; border: 1px solid var(--line); border-radius: 12px; padding: 12px; }}
    @media (min-width: 760px) {{ .clock-entry-grid.two-col {{ grid-template-columns: 1fr 1fr; }} }}
    @media (max-width: 720px) {{ header {{ padding: 16px 18px; }} nav {{ flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; align-items: center; gap: 8px; padding: 8px 12px; scrollbar-width: thin; }} nav a {{ flex: 0 0 auto; min-height: 34px; padding: 0 12px; border-radius: 8px; white-space: nowrap; }} .language-switcher {{ margin-left: 6px; flex-direction: row; align-items: center; }} .language-switcher .pill, .language-switcher .button {{ width: auto; min-height: 30px; padding: 0 9px; }} main {{ padding: 18px 12px 36px; }} .grid, .form-grid, .sap-readonly-grid {{ grid-template-columns: 1fr; }} .object-header, .sap-page-header {{ display: block; padding: 16px; }} .object-meta, .sap-object-meta {{ margin-top: 12px; }} .actions, .sap-toolbar {{ justify-content: stretch; flex-direction: column; align-items: stretch; }} .actions .button, .actions button, .sap-toolbar .button, .sap-toolbar button {{ text-align: center; width: 100%; }} table {{ display: block; overflow-x: auto; min-width: 760px; }} input, select, textarea {{ min-height: 44px; }} .quick-break-actions {{ grid-template-columns: repeat(2, 1fr); }} .my-day-card {{ grid-template-columns: 1fr; align-items: stretch; }} }}
  </style>
</head>
<body>
  <header>
    <h1>{h(t(messages, 'app.title'))}</h1>
    <p>{h(t(messages, 'app.subtitle'))}</p>
  </header>
  <nav>{portal_html}{nav_html}<span class="language-switcher">{user_html}{language_html}</span></nav>
  <main>{flash_html}{body}</main>
</body>
</html>"""


def dashboard_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    records = scope_records_to_current_entity(load_timesheet_entries(), context)
    employees = load_timesheet_employees(context)
    projects = scope_records_to_current_entity(load_projects(), context)
    entities = scope_records_to_current_entity(load_entities(), context)
    departments = scope_records_to_current_entity(load_departments(), context)
    teams = scope_records_to_current_entity(load_teams(), context)
    current_month = datetime.now().strftime("%Y-%m")
    month_records = [record for record in records if str(record.get("work_date", "")).startswith(current_month)]
    totals = calculate_timesheet_totals(month_records)
    status = employee_source_status(context)
    return f"""
<section class="grid">
  <div class="card"><h3>{h(t(messages, 'dashboard.total_records'))}</h3><div class="metric">{len(records)}</div><p class="muted">{h(t(messages, 'dashboard.total_records_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'dashboard.employees'))}</h3><div class="metric">{len(employees)}</div><p class="muted">{h(t(messages, 'dashboard.employees_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'dashboard.projects'))}</h3><div class="metric">{len(projects)}</div><p class="muted">{h(t(messages, 'dashboard.projects_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'dashboard.organization'))}</h3><div class="metric">{len(entities)} / {len(departments)} / {len(teams)}</div><p class="muted">{h(t(messages, 'dashboard.organization_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'dashboard.monthly_work'))}</h3><div class="metric">{format_minutes(totals['actual_work_minutes'])}</div><p class="muted">{h(t(messages, 'dashboard.current_month'))}: {h(current_month)} / {len(month_records)}</p></div>
</section>
<section class="panel" style="margin-top: 18px;">
  <h2>{h(t(messages, 'dashboard.status_title'))}</h2>
  <p><span class="pill">{h(t(messages, 'dashboard.status_badge'))}</span></p>
  <p>{h(t(messages, 'dashboard.status_desc'))}</p>
  <p class="notice">{h(t(messages, str(status.get('message_key', 'message.employeeadmin_unavailable'))))}</p>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/timesheet-new', lang))}">{h(t(messages, 'action.input_timesheet'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/employees', lang))}">{h(t(messages, 'employee.source_title'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/projects', lang))}">{h(t(messages, 'action.manage_projects'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/organization', lang))}">{h(t(messages, 'action.manage_organization'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/timesheets', lang))}">{h(t(messages, 'action.open_timesheets'))}</a>
  </div>
</section>
"""


def timesheet_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["entity_id", "employee_no", "work_month", "customer_name", "project_code", "project_name", "approval_status"]}


def timesheets_html(query: dict[str, list[str]], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    filters = timesheet_filters_from_query(query)
    records = filter_timesheet_entries(load_timesheet_entries(), filters, context)
    totals = calculate_timesheet_totals(records)
    employee_summary_rows = calculate_monthly_employee_summary(records)
    project_summary_rows = calculate_monthly_project_summary(records)
    organization_summary_rows = calculate_monthly_organization_summary(records)
    rows_html = timesheet_table_rows(records, messages, context)
    employee_summary_html = monthly_employee_summary_rows(employee_summary_rows)
    project_summary_html = monthly_project_summary_rows(project_summary_rows)
    organization_summary_html = monthly_organization_summary_rows(organization_summary_rows, messages)
    closing_month = filters["work_month"] or datetime.now().strftime("%Y-%m")
    closing_panel = monthly_closing_panel_html(closing_month, context)
    export_query = urlencode({key: value for key, value in filters.items() if value})
    export_href = f"/timesheets.csv?{export_query}" if export_query else "/timesheets.csv"
    approval_options = f"<option value=''>{h(t(messages, 'filter.all'))}</option>" + select_options_i18n(APPROVAL_STATUSES, filters["approval_status"], messages, "approval_status")
    return f"""
<section class="panel">
  <h2>{h(t(messages, 'timesheet.table_title'))}</h2>
  <p class="notice">{h(t(messages, 'timesheet.table_notice'))}</p>
  <form method="get" action="/timesheets">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.entity'))}</label><select name="entity_id">{entity_select_options(filters['entity_id'], include_blank=True, blank_label=t(messages, 'filter.all'), context=context)}</select></div>
      <div><label>{h(t(messages, 'field.employee'))}</label><select name="employee_no"><option value="">{h(t(messages, 'filter.all_employees'))}</option>{employee_select_options(filters['employee_no'], context)}</select></div>
      <div><label>{h(t(messages, 'field.work_month'))}</label><input name="work_month" value="{h(filters['work_month'])}" placeholder="2026-06"></div>
      <div><label>{h(t(messages, 'field.customer'))}</label><input name="customer_name" value="{h(filters['customer_name'])}" placeholder="ABC Corp"></div>
      <div><label>{h(t(messages, 'field.project'))}</label><select name="project_code">{project_select_options(filters['project_code'], include_blank=True, blank_label=t(messages, 'filter.all_projects'), context=context)}</select></div>
      <div><label>{h(t(messages, 'field.approval'))}</label><select name="approval_status">{approval_options}</select></div>
    </div>
    <div class="actions">
      <button type="submit">{h(t(messages, 'action.filter'))}</button>
      <a class="button secondary" href="{h(url_with_lang('/timesheets', lang))}">{h(t(messages, 'action.clear'))}</a>
      <a class="button" href="{h(url_with_lang('/timesheet-new', lang))}">{h(t(messages, 'nav.timesheet_new'))}</a>
      <a class="button secondary" href="{h(export_href + ('&' if '?' in export_href else '?') + urlencode({'lang': lang}))}">{h(t(messages, 'action.export_csv'))}</a>
    </div>
  </form>
</section>
{closing_panel}
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>{h(t(messages, 'timesheet.filtered_rows'))}</h3><div class="metric">{len(records)}</div></div>
  <div class="card"><h3>{h(t(messages, 'timesheet.actual_work'))}</h3><div class="metric">{format_minutes(totals['actual_work_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'timesheet.overtime'))}</h3><div class="metric">{format_minutes(totals['overtime_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'field.night_work'))}</h3><div class="metric">{format_minutes(totals['night_work_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'field.holiday_work'))}</h3><div class="metric">{format_minutes(totals['holiday_work_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'field.break_shortage'))}</h3><div class="metric">{format_minutes(totals['break_shortage_minutes'])}</div></div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>{h(t(messages, 'timesheet.summary_employee'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'field.work_month'))}</th><th>{h(t(messages, 'field.employee_no'))}</th><th>{h(t(messages, 'field.employee_name'))}</th><th class="num">{h(t(messages, 'field.entries_days'))}</th><th class="num">{h(t(messages, 'timesheet.actual_work'))}</th><th class="num">{h(t(messages, 'timesheet.overtime'))}</th><th class="num">{h(t(messages, 'field.night_work'))}</th><th class="num">{h(t(messages, 'field.holiday_work'))}</th><th class="num">{h(t(messages, 'field.break_shortage'))}</th></tr></thead>
    <tbody>{employee_summary_html}</tbody>
  </table>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>{h(t(messages, 'timesheet.summary_project'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'field.work_month'))}</th><th>{h(t(messages, 'field.customer'))}</th><th>{h(t(messages, 'field.project_code'))}</th><th>{h(t(messages, 'field.project_name'))}</th><th class="num">{h(t(messages, 'field.entries_days'))}</th><th class="num">{h(t(messages, 'timesheet.actual_work'))}</th><th class="num">{h(t(messages, 'timesheet.overtime'))}</th><th class="num">{h(t(messages, 'field.night_work'))}</th><th class="num">{h(t(messages, 'field.holiday_work'))}</th><th class="num">{h(t(messages, 'field.break_shortage'))}</th></tr></thead>
    <tbody>{project_summary_html}</tbody>
  </table>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>{h(t(messages, 'timesheet.summary_organization'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'field.work_month'))}</th><th>{h(t(messages, 'field.entity'))}</th><th>{h(t(messages, 'field.department'))}</th><th>{h(t(messages, 'field.team'))}</th><th class="num">{h(t(messages, 'field.entries_days'))}</th><th class="num">{h(t(messages, 'timesheet.actual_work'))}</th><th class="num">{h(t(messages, 'timesheet.overtime'))}</th><th class="num">{h(t(messages, 'field.night_work'))}</th><th class="num">{h(t(messages, 'field.holiday_work'))}</th><th class="num">{h(t(messages, 'field.break_shortage'))}</th></tr></thead>
    <tbody>{organization_summary_html}</tbody>
  </table>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>{h(t(messages, 'timesheet.daily_rows'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'field.date'))}</th><th>{h(t(messages, 'field.employee'))}</th><th>{h(t(messages, 'field.customer'))} / {h(t(messages, 'field.project'))}</th><th>{h(t(messages, 'field.time'))}</th><th>{h(t(messages, 'field.break'))}</th><th class="num">{h(t(messages, 'field.actual'))}</th><th class="num">{h(t(messages, 'field.ot'))}</th><th>{h(t(messages, 'timesheet.calculation_breakdown'))}</th><th>{h(t(messages, 'field.remarks'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.lock'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def timesheets_csv_text(query: dict[str, list[str]]) -> str:
    filters = timesheet_filters_from_query(query)
    records = filter_timesheet_entries(load_timesheet_entries(), filters, context)
    output = io.StringIO(newline="")
    fieldnames = [
        "record_id",
        "work_date",
        "weekday",
        "employee_no",
        "employee_name",
        "department",
        "entity_id",
        "entity_code",
        "entity_name",
        "department_id",
        "department_code",
        "department_name",
        "team_id",
        "team_code",
        "team_name",
        "entry_mode",
        "entry_source",
        "entered_by",
        "entered_by_user_id",
        "entered_by_name",
        "on_behalf_of_employee_no",
        "assistance_reason",
        "assistance_note",
        "last_modified_by",
        "last_modified_entry_mode",
        "customer_name",
        "customer_code",
        "project_code",
        "project_name",
        "billing_enabled",
        "billing_rate_per_hour_yen",
        "dispatch_type",
        "work_location",
        "attendance_status",
        "start_time",
        "end_time",
        "break_minutes",
        "scheduled_work_minutes",
        "actual_work_minutes",
        "overtime_minutes",
        "night_work_minutes",
        "holiday_work_minutes",
        "approval_status",
        "record_status",
        "employee_remarks",
        "manager_remarks",
        "created_at",
        "updated_at",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for row in timesheet_csv_rows(records):
        writer.writerow(row)
    return output.getvalue()


def timesheet_csv_rows(records: list[dict[str, Any]]) -> list[dict[str, str]]:
    fieldnames = [
        "record_id",
        "work_date",
        "weekday",
        "employee_no",
        "employee_name",
        "department",
        "entity_id",
        "entity_code",
        "entity_name",
        "department_id",
        "department_code",
        "department_name",
        "team_id",
        "team_code",
        "team_name",
        "entry_mode",
        "entry_source",
        "entered_by",
        "entered_by_user_id",
        "entered_by_name",
        "on_behalf_of_employee_no",
        "assistance_reason",
        "assistance_note",
        "last_modified_by",
        "last_modified_entry_mode",
        "customer_name",
        "customer_code",
        "project_code",
        "project_name",
        "billing_enabled",
        "billing_rate_per_hour_yen",
        "dispatch_type",
        "work_location",
        "attendance_status",
        "start_time",
        "end_time",
        "break_minutes",
        "scheduled_work_minutes",
        "actual_work_minutes",
        "overtime_minutes",
        "night_work_minutes",
        "holiday_work_minutes",
        "approval_status",
        "record_status",
        "employee_remarks",
        "manager_remarks",
        "created_at",
        "updated_at",
    ]
    rows = []
    for record in sorted(records, key=lambda item: (str(item.get("work_date", "")), str(item.get("employee_no", "")), str(item.get("project_code", "")))):
        row = {key: csv_safe_cell(record.get(key, "")) for key in fieldnames}
        row["approval_status"] = csv_safe_cell(approval_status(record))
        rows.append(row)
    return rows


def csv_safe_cell(value: Any) -> str:
    text = str(value if value is not None else "")
    if text.startswith(("=", "+", "-", "@")):
        return f"'{text}"
    return text


def timesheet_export_filename(filters: dict[str, str]) -> str:
    month = filters.get("work_month", "").strip()
    suffix = month if month else "all"
    return f"timesheets_{suffix}.csv"


def monthly_closing_panel_html(work_month: str, context: dict[str, Any] | None = None) -> str:
    try:
        normalized = normalize_work_month(work_month)
    except ValueError:
        normalized = datetime.now().strftime("%Y-%m")
    counts = calculate_monthly_approval_counts(normalized, context)
    period = find_timesheet_period(normalized, context) or build_default_period_record(normalized, context=context)
    status = period_status(period)
    closed = status == "Closed"
    status_label = "Closed / 账期关闭 / 締め済" if closed else "Open / 账期打开 / 未締め"
    close_reason = period_close_blocking_reason(normalized, context) if not closed else ""
    open_reason = period_open_blocking_reason(normalized, context) if closed else ""
    details = f"""
      <p class="muted">Opened at: {h(period.get('opened_at') or '-')} / By: {h(period.get('opened_by') or '-')}</p>
      <p class="muted">Closed at: {h(period.get('closed_at') or period.get('locked_at') or '-')} / By: {h(period.get('closed_by') or period.get('locked_by') or '-')}</p>
      <p class="muted">Notes: {h(period.get('notes') or '-')}</p>
    """
    action_form = ""
    if closed:
        if open_reason:
            action_form = f"<p class='muted'>Open unavailable / 无法打开 / 再オープン不可: {h(open_reason)}</p>"
        else:
            action_form = f"""
            <form method="post" action="/timesheet-period-open">
              <input type="hidden" name="work_month" value="{h(normalized)}">
              <div style="margin-top: 14px;"><label>Open Notes / 打开备注 / 再オープンメモ</label><textarea name="notes" placeholder="Optional opening note"></textarea></div>
              <div class="actions"><button type="submit">Open Period / 打开账期 / 再オープン</button></div>
            </form>
            """
    else:
        if close_reason:
            action_form = f"<p class='muted'>Close unavailable / 无法关闭 / 締め不可: {h(close_reason)}</p>"
        else:
            action_form = f"""
            <form method="post" action="/timesheet-period-close">
              <input type="hidden" name="work_month" value="{h(normalized)}">
              <div style="margin-top: 14px;"><label>Close Notes / 关闭备注 / 締めメモ</label><textarea name="notes" placeholder="Optional closing note"></textarea></div>
              <div class="actions"><button class="danger" type="submit">Close Period / 关闭账期 / 締める</button></div>
            </form>
            """
    return f"""
<section class="panel" style="margin-top: 18px;">
  <h3>Timesheet accounting period / 工时账期 / 勤怠会計期間</h3>
  <form method="get" action="/timesheets">
    <div class="form-grid">
      <div><label>Period Month / 账期月份 / 対象月</label><input name="work_month" value="{h(normalized)}" placeholder="2026-06"></div>
    </div>
    <div class="actions"><button type="submit">Show Period / 显示账期 / 表示</button></div>
  </form>
  <section class="grid" style="margin-top: 18px;">
    <div class="card"><h3>Period Status / 账期状态 / 状態</h3><p><span class="pill">{h(status_label)}</span></p></div>
    <div class="card"><h3>Active Rows / 有効行</h3><div class="metric">{counts['active_count']}</div></div>
    <div class="card"><h3>Draft / 下書き</h3><div class="metric">{counts['Draft']}</div></div>
    <div class="card"><h3>Submitted / 申請済</h3><div class="metric">{counts['Submitted']}</div></div>
    <div class="card"><h3>Approved / 承認済</h3><div class="metric">{counts['Approved']}</div></div>
    <div class="card"><h3>Rejected / 差戻し</h3><div class="metric">{counts['Rejected']}</div></div>
    <div class="card"><h3>Deleted / 削除済</h3><div class="metric">{counts['deleted_count']}</div></div>
  </section>
  {details}
  {action_form}
</section>
"""


def organization_unassigned_label(messages: dict[str, str] | None = None) -> str:
    return t(messages or load_i18n(DEFAULT_LANG), "timesheet.organization_unassigned", "Unassigned")


def organization_label_for_record(record: dict[str, Any], messages: dict[str, str] | None = None) -> str:
    unassigned = organization_unassigned_label(messages)
    entity = " ".join(bit for bit in [str(record.get("entity_code", "")).strip(), str(record.get("entity_name", "")).strip()] if bit)
    department = " ".join(bit for bit in [str(record.get("department_code", "")).strip(), str(record.get("department_name", "")).strip()] if bit) or str(record.get("department", "")).strip()
    team = " ".join(bit for bit in [str(record.get("team_code", "")).strip(), str(record.get("team_name", "")).strip()] if bit)
    parts = [part for part in [entity, department, team] if part]
    return " / ".join(parts) if parts else unassigned


def timesheet_table_rows(records: list[dict[str, Any]], messages: dict[str, str] | None = None, context: dict[str, Any] | None = None) -> str:
    if not records:
        return "<tr><td colspan='12' class='muted'>No timesheet records saved yet.</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: (str(item.get("work_date", "")), str(item.get("employee_no", ""))), reverse=True):
        status = approval_status(record)
        locked = record_month_is_locked(record, context)
        lock_label = "Locked / 締め済" if locked else "Open / 未締め"
        status_class = "good" if status == "Approved" else "warn" if status in {"Draft", "Submitted"} else "error"
        lock_class = "error" if locked else "good"
        action_html = timesheet_action_html(record, status, locked)
        organization_label = organization_label_for_record(record, messages)
        organization_html = f"<br><span class='muted'>{h(organization_label)}</span>" if organization_label else ""
        reject_reason = str(record.get("reject_reason", "")).strip()
        entry_mode = str(record.get("entry_mode", "") or "self")
        entry_source = str(record.get("entry_source", "") or "")
        assistance_reason = str(record.get("assistance_reason", "") or "")
        entered_by = str(record.get("entered_by_name") or record.get("entered_by") or "")
        proxy_bits = [
            t(messages, "entry_mode." + entry_mode, entry_mode),
            t(messages, "entry_source." + entry_source, entry_source) if entry_source else "",
            t(messages, "assistance_reason." + assistance_reason, assistance_reason) if assistance_reason else "",
        ]
        proxy_text = " / ".join(bit for bit in proxy_bits if bit)
        remarks_html = value(record, "employee_remarks")
        if proxy_text:
            remarks_html += f"<br><span class='muted'>{h(proxy_text)}</span>"
        if entered_by:
            remarks_html += f"<br><span class='muted'>{h(t(messages, 'field.entered_by', 'Entered By'))}: {h(entered_by)}</span>"
        if reject_reason:
            remarks_html += f"<br><span class='warn'>Reject reason: {escape(reject_reason)}</span>"
        rows.append(f"""
        <tr>
          <td>{value(record, 'work_date')}<br><span class="muted">{value(record, 'weekday')}</span></td>
          <td>{value(record, 'employee_no')}<br><span class="muted">{value(record, 'employee_name')}</span>{organization_html}</td>
          <td>{value(record, 'customer_name')}<br><span class="muted">{value(record, 'project_code')} {value(record, 'project_name')}</span></td>
          <td>{value(record, 'start_time')} - {value(record, 'end_time')}</td>
          <td>{value(record, 'break_minutes')} min</td>
          <td class="num">{format_minutes(record.get('actual_work_minutes', 0))}</td>
          <td class="num">{format_minutes(record.get('overtime_minutes', 0))}</td>
          <td>{compact_breakdown_html(record)}</td>
          <td>{remarks_html}</td>
          <td><span class="{status_class}">{escape(status)}</span></td>
          <td><span class="{lock_class}">{escape(lock_label)}</span></td>
          <td>{action_html}</td>
        </tr>
        """)
    return "".join(rows)


def timesheet_action_html(record: dict[str, Any], status: str, locked: bool) -> str:
    record_id = escape(str(record.get("record_id", "")))
    if not record_id:
        return ""
    if locked:
        return "<span class='muted'>Locked</span>"
    actions = []
    if status in {"Draft", "Rejected"}:
        actions.append(f"<a class='button secondary' href='/timesheet-edit?id={record_id}'>Edit</a>")
        actions.append(f"<form method='post' action='/timesheet-delete'><input type='hidden' name='record_id' value='{record_id}'><button class='danger' type='submit'>Soft Delete</button></form>")
        actions.append(f"<form method='post' action='/timesheet-submit'><input type='hidden' name='record_id' value='{record_id}'><button type='submit'>Submit</button></form>")
    elif status == "Submitted":
        actions.append(f"<form method='post' action='/timesheet-approve'><input type='hidden' name='record_id' value='{record_id}'><button type='submit'>Approve</button></form>")
        actions.append(f"<form method='post' action='/timesheet-reject'><input type='hidden' name='record_id' value='{record_id}'><input name='reject_reason' placeholder='Reject reason'><button class='danger' type='submit'>Reject</button></form>")
        actions.append(f"<form method='post' action='/timesheet-reopen'><input type='hidden' name='record_id' value='{record_id}'><button class='secondary' type='submit'>Reopen</button></form>")
    elif status == "Approved":
        actions.append(f"<form method='post' action='/timesheet-reopen'><input type='hidden' name='record_id' value='{record_id}'><button class='secondary' type='submit'>Reopen</button></form>")
    return f"<div class='actions'>{''.join(actions)}</div>" if actions else ""


def monthly_employee_summary_rows(summary_rows: list[dict[str, Any]]) -> str:
    if not summary_rows:
        return "<tr><td colspan='9' class='muted'>No monthly employee summary data yet.</td></tr>"
    rows = []
    for row in summary_rows:
        rows.append(f"""
        <tr>
          <td>{escape(str(row.get('work_month', '')))}</td>
          <td>{escape(str(row.get('employee_no', '')))}</td>
          <td>{escape(str(row.get('employee_name', '')))}</td>
          <td class="num">{escape(str(row.get('entry_count', 0)))}</td>
          <td class="num">{format_minutes(row.get('actual_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('overtime_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('night_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('holiday_work_minutes', 0))}</td>
          <td class="num">{escape(str(row.get('break_shortage_count', 0)))}</td>
        </tr>
        """)
    return "".join(rows)


def monthly_project_summary_rows(summary_rows: list[dict[str, Any]]) -> str:
    if not summary_rows:
        return "<tr><td colspan='10' class='muted'>No monthly project/customer summary data yet.</td></tr>"
    rows = []
    for row in summary_rows:
        rows.append(f"""
        <tr>
          <td>{escape(str(row.get('work_month', '')))}</td>
          <td>{escape(str(row.get('customer_name', '') or 'Unassigned'))}</td>
          <td>{escape(str(row.get('project_code', '') or '-'))}</td>
          <td>{escape(str(row.get('project_name', '') or 'Unassigned'))}</td>
          <td class="num">{escape(str(row.get('entry_count', 0)))}</td>
          <td class="num">{format_minutes(row.get('actual_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('overtime_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('night_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('holiday_work_minutes', 0))}</td>
          <td class="num">{escape(str(row.get('break_shortage_count', 0)))}</td>
        </tr>
        """)
    return "".join(rows)


def monthly_organization_summary_rows(summary_rows: list[dict[str, Any]], messages: dict[str, str] | None = None) -> str:
    if not summary_rows:
        return f"<tr><td colspan='10' class='muted'>{h(t(messages, 'timesheet.no_organization_summary', 'No monthly organization summary data yet.'))}</td></tr>"
    rows = []
    for row in summary_rows:
        rows.append(f"""
        <tr>
          <td>{h(row.get('work_month', ''))}</td>
          <td>{h(row.get('entity_label', ''))}</td>
          <td>{h(row.get('department_label', ''))}</td>
          <td>{h(row.get('team_label', ''))}</td>
          <td class="num">{h(row.get('entry_count', 0))}</td>
          <td class="num">{format_minutes(row.get('actual_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('overtime_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('night_work_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('holiday_work_minutes', 0))}</td>
          <td class="num">{h(row.get('break_shortage_count', 0))}</td>
        </tr>
        """)
    return "".join(rows)


def billing_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["entity_id", "work_month", "customer_name", "project_code"]}


def billing_html(query: dict[str, list[str]], context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    filters = billing_filters_from_query(query)
    records = filter_billing_timesheet_entries(load_timesheet_entries(), filters, context)
    summary_rows = calculate_billing_summary(records, context)
    rows_html = billing_summary_rows(summary_rows, context)
    return f"""
<section class="panel">
  <h2>Billing summary / 請求集計</h2>
  <p class="notice">Billing summary includes active, Approved timesheet rows for billing-enabled projects. Amounts use exact minutes and project hourly JPY rates.</p>
  <form method="get" action="/billing">
    <div class="form-grid">
      <div><label>Entity / 法人</label><select name="entity_id">{entity_select_options(filters['entity_id'], include_blank=True, blank_label='All entities', context=context)}</select></div>
      <div><label>Work Month / 勤務月</label><input name="work_month" value="{escape(filters['work_month'])}" placeholder="2026-06"></div>
      <div><label>Customer / 顧客名</label><input name="customer_name" value="{escape(filters['customer_name'])}" placeholder="ABC Corp"></div>
      <div><label>Project / 案件</label><select name="project_code">{project_select_options(filters['project_code'], include_blank=True, blank_label='All projects', context=context)}</select></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索</button>
      <a class="button secondary" href="{h(url_with_lang('/billing', lang))}">Clear / クリア</a>
      <a class="button secondary" href="{h(url_with_lang('/projects', lang))}">Manage Project Rates</a>
    </div>
  </form>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Billable approved work / 請求対象承認済み工数</h3>
  <table>
    <thead><tr><th>Month</th><th>Customer</th><th>Project</th><th class="num">Rate / Hour</th><th class="num">Approved Entries</th><th class="num">Billable Time</th><th class="num">Overtime</th><th class="num">Amount</th><th>Lock</th><th>Warnings</th><th>Invoice</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def filter_billing_timesheet_entries(records: list[dict[str, Any]], filters: dict[str, str], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filtered = [record for record in scope_records_to_current_entity(records, context) if is_billable_timesheet_record(record, context)]
    entity_id = filters.get("entity_id", "")
    work_month = filters.get("work_month", "")
    customer_name = filters.get("customer_name", "").lower()
    project_code = filters.get("project_code", "").lower()
    if entity_id:
        filtered = [record for record in filtered if entity_id in {str(record.get("entity_id", "")).strip(), str(record.get("entity_code", "")).strip()}]
    if work_month:
        filtered = [record for record in filtered if str(record.get("work_date", "")).startswith(work_month)]
    if customer_name:
        filtered = [record for record in filtered if customer_name in str(record.get("customer_name", "")).lower()]
    if project_code:
        filtered = [record for record in filtered if project_code == str(record.get("project_code", "")).lower()]
    return filtered


def is_billable_timesheet_record(record: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    if approval_status(record) != "Approved":
        return False
    return billing_enabled_for_record(record, context)


def billing_enabled_for_record(record: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    if "billing_enabled" in record:
        return bool(record.get("billing_enabled"))
    project = find_active_project_by_code(str(record.get("project_code", "")), context)
    return bool(project and project.get("billing_enabled"))


def billing_rate_for_record(record: dict[str, Any], context: dict[str, Any] | None = None) -> int:
    if "billing_rate_per_hour_yen" in record:
        return parse_non_negative_int(record.get("billing_rate_per_hour_yen", 0), "Billing Rate per Hour JPY")
    project = find_active_project_by_code(str(record.get("project_code", "")), context)
    return parse_non_negative_int(project.get("billing_rate_per_hour_yen", 0) if project else 0, "Billing Rate per Hour JPY")


def calculate_billing_amount_yen(minutes: int, hourly_rate_yen: int) -> int:
    return (minutes * hourly_rate_yen + 30) // 60


def calculate_billing_summary(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str, int], dict[str, Any]] = {}
    for record in records:
        work_month = str(record.get("work_date", ""))[:7]
        if len(work_month) != 7:
            continue
        rate = billing_rate_for_record(record, context)
        key = (
            work_month,
            str(record.get("customer_name", "")),
            str(record.get("project_code", "")),
            str(record.get("project_name", "")),
            rate,
        )
        if key not in grouped:
            grouped[key] = {
                "work_month": work_month,
                "customer_name": str(record.get("customer_name", "")),
                "customer_code": str(record.get("customer_code", "")),
                "project_code": str(record.get("project_code", "")),
                "project_name": str(record.get("project_name", "")),
                "billing_rate_per_hour_yen": rate,
                "entry_count": 0,
                "billable_minutes": 0,
                "overtime_minutes": 0,
                "entity_id": str(record.get("entity_id", "")),
                "entity_code": str(record.get("entity_code", "")),
                "entity_name": str(record.get("entity_name", "")),
                "source_record_ids": [],
            }
        grouped[key]["entry_count"] += 1
        grouped[key]["billable_minutes"] += parse_non_negative_int(record.get("actual_work_minutes", 0), "Actual Work Minutes")
        grouped[key]["overtime_minutes"] += parse_non_negative_int(record.get("overtime_minutes", 0), "Overtime Minutes")
        if record.get("record_id"):
            grouped[key]["source_record_ids"].append(str(record.get("record_id")))
    for row in grouped.values():
        row["billing_amount_yen"] = calculate_billing_amount_yen(row["billable_minutes"], row["billing_rate_per_hour_yen"])
        warnings = []
        if row["billing_rate_per_hour_yen"] == 0:
            warnings.append("Rate is 0")
        if not is_month_locked(row["work_month"], context):
            warnings.append("Month is not locked")
        row["warnings"] = warnings
    return sorted(grouped.values(), key=lambda row: (str(row.get("work_month", "")), str(row.get("customer_name", "")), str(row.get("project_code", ""))), reverse=True)


def billing_summary_rows(summary_rows: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    if not summary_rows:
        return "<tr><td colspan='11' class='muted'>No approved billable rows found.</td></tr>"
    rows = []
    for row in summary_rows:
        lock_label = "Locked / 締め済" if is_month_locked(str(row.get("work_month", "")), context) else "Open / 未締め"
        warnings = ", ".join(str(item) for item in row.get("warnings", [])) or "-"
        invoice_action = invoice_create_action_html(row, context)
        rows.append(f"""
        <tr>
          <td>{escape(str(row.get('work_month', '')))}</td>
          <td>{escape(str(row.get('customer_name', '') or 'Unassigned'))}</td>
          <td>{escape(str(row.get('project_code', '') or '-'))}<br><span class="muted">{escape(str(row.get('project_name', '') or 'Unassigned'))}</span></td>
          <td class="num">{format_yen(row.get('billing_rate_per_hour_yen', 0))}</td>
          <td class="num">{escape(str(row.get('entry_count', 0)))}</td>
          <td class="num">{format_minutes(row.get('billable_minutes', 0))}</td>
          <td class="num">{format_minutes(row.get('overtime_minutes', 0))}</td>
          <td class="num"><strong>{format_yen(row.get('billing_amount_yen', 0))}</strong></td>
          <td>{escape(lock_label)}</td>
          <td>{escape(warnings)}</td>
          <td>{invoice_action}</td>
        </tr>
        """)
    return "".join(rows)


def invoice_create_action_html(row: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    work_month = str(row.get("work_month", ""))
    customer_name = str(row.get("customer_name", ""))
    project_code = str(row.get("project_code", ""))
    if not is_month_locked(work_month, context):
        return "<span class='muted'>Lock month first</span>"
    if duplicate_invoice_draft_exists(work_month, customer_name, project_code, context):
        return "<span class='muted'>Draft exists</span>"
    return f"""
    <form method="post" action="/invoice-draft-create">
      <input type="hidden" name="work_month" value="{escape(work_month)}">
      <input type="hidden" name="customer_name" value="{escape(customer_name)}">
      <input type="hidden" name="project_code" value="{escape(project_code)}">
      <button type="submit">Create Draft / 請求ドラフト作成</button>
    </form>
    """


def load_invoice_drafts(include_voided: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(INVOICE_DRAFTS_PATH)
    if include_voided:
        return records
    return [record for record in records if record.get("invoice_status", "Draft") != "Voided"]


def load_invoice_drafts_for_context(context: dict[str, Any] | None = None, include_voided: bool = False) -> list[dict[str, Any]]:
    return scope_records_to_current_entity(load_invoice_drafts(include_voided=include_voided), context)


def save_invoice_drafts(records: list[dict[str, Any]]) -> None:
    write_json_array(INVOICE_DRAFTS_PATH, records)


def find_invoice_draft(invoice_id: str) -> dict[str, Any] | None:
    invoice_id = invoice_id.strip()
    if not invoice_id:
        return None
    for record in load_invoice_drafts(include_voided=True):
        if record.get("invoice_id") == invoice_id:
            return record
    return None


def duplicate_invoice_draft_exists(work_month: str, customer_name: str, project_code: str, context: dict[str, Any] | None = None) -> bool:
    normalized = normalize_work_month(work_month)
    for record in load_invoice_drafts_for_context(context):
        if (
            record.get("work_month") == normalized
            and str(record.get("customer_name", "")).strip().lower() == customer_name.strip().lower()
            and str(record.get("project_code", "")).strip().lower() == project_code.strip().lower()
        ):
            return True
    return False


def next_invoice_no(work_month: str, existing: list[dict[str, Any]]) -> str:
    normalized = normalize_work_month(work_month)
    prefix = f"INV-{normalized.replace('-', '')}-"
    numbers = []
    for record in existing:
        invoice_no = str(record.get("invoice_no", ""))
        if invoice_no.startswith(prefix):
            suffix = invoice_no.rsplit("-", 1)[-1]
            if suffix.isdigit():
                numbers.append(int(suffix))
    return f"{prefix}{max(numbers, default=0) + 1:04d}"


def billing_summary_for_invoice(work_month: str, customer_name: str, project_code: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_work_month(work_month)
    filters = {"work_month": normalized, "customer_name": customer_name.strip(), "project_code": project_code.strip()}
    rows = calculate_billing_summary(filter_billing_timesheet_entries(load_timesheet_entries(), filters, context), context)
    matches = [
        row for row in rows
        if row.get("work_month") == normalized
        and str(row.get("customer_name", "")).strip().lower() == customer_name.strip().lower()
        and str(row.get("project_code", "")).strip().lower() == project_code.strip().lower()
    ]
    if not matches:
        raise ValueError("No billing summary row was found for this invoice draft.")
    if len(matches) > 1:
        raise ValueError("Multiple billing rates were found for this project/month. Create separate invoice support in a later phase.")
    return matches[0]


def create_invoice_draft_from_billing_summary(work_month: str, customer_name: str, project_code: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_work_month(work_month)
    if not is_month_locked(normalized, context):
        raise ValueError("Invoice drafts can only be created for locked months.")
    if duplicate_invoice_draft_exists(normalized, customer_name, project_code, context):
        raise ValueError("An active invoice draft already exists for this month/customer/project.")
    summary = billing_summary_for_invoice(normalized, customer_name, project_code, context)
    now = datetime.now(timezone.utc)
    existing = load_invoice_drafts(include_voided=True)
    subtotal = parse_non_negative_int(summary.get("billing_amount_yen", 0), "Subtotal JPY")
    draft = {
        "invoice_id": f"inv-{now.strftime('%Y%m%d%H%M%S%f')}",
        "invoice_no": next_invoice_no(normalized, existing),
        "invoice_status": "Draft",
        "work_month": normalized,
        "customer_name": summary.get("customer_name", ""),
        "customer_code": summary.get("customer_code", ""),
        "entity_id": summary.get("entity_id", ""),
        "entity_code": summary.get("entity_code", ""),
        "entity_name": summary.get("entity_name", ""),
        "project_code": summary.get("project_code", ""),
        "project_name": summary.get("project_name", ""),
        "billing_rate_per_hour_yen": summary.get("billing_rate_per_hour_yen", 0),
        "billable_minutes": summary.get("billable_minutes", 0),
        "subtotal_yen": subtotal,
        "tax_rate_percent": 0,
        "tax_yen": 0,
        "total_yen": subtotal,
        "source_record_ids": summary.get("source_record_ids", []),
        "created_by": actor,
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
        "voided_at": "",
        "voided_by": "",
        "void_reason": "",
    }
    draft = apply_current_entity_snapshot(draft, context)
    existing.append(draft)
    save_invoice_drafts(existing)
    append_audit_log("timesheet.invoice_draft", str(draft.get("invoice_id", "")), "create", None, dict(draft), user=actor, context=context)
    return draft


def void_invoice_draft(invoice_id: str, reason: str = "", actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    invoice_id = invoice_id.strip()
    records = load_invoice_drafts(include_voided=True)
    for record in records:
        if record.get("invoice_id") == invoice_id:
            require_record_entity_access(record, context, "Invoice draft")
            if record.get("invoice_status") == "Voided":
                raise ValueError("Invoice draft is already voided.")
            before_value = dict(record)
            now = datetime.now(timezone.utc).isoformat()
            record["invoice_status"] = "Voided"
            record["voided_at"] = now
            record["voided_by"] = actor
            record["void_reason"] = reason.strip()
            record["updated_at"] = now
            save_invoice_drafts(records)
            append_audit_log("timesheet.invoice_draft", invoice_id, "void", before_value, dict(record), user=actor, context=context)
            return record
    raise ValueError("Invoice draft was not found.")


def invoices_html(query: dict[str, list[str]], context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    include_voided = parse_bool(query.get("include_voided", [""])[0]) if query else False
    records = load_invoice_drafts_for_context(context, include_voided=include_voided)
    rows_html = invoice_draft_table_rows(records, context)
    checked = " checked" if include_voided else ""
    return f"""
<section class="panel">
  <h2>Invoice drafts / 請求書ドラフト</h2>
  <p class="notice">Invoice drafts are generated from locked-month billing summaries. Drafts snapshot source totals and do not change when source project rates are later edited.</p>
  <form method="get" action="/invoices">
    <label><input type="checkbox" name="include_voided" value="true"{checked}> Include voided / 無効化済みも表示</label>
    <div class="actions">
      <button type="submit">Apply / 適用</button>
      <a class="button secondary" href="{h(url_with_lang('/billing', lang))}">Open Billing Summary</a>
    </div>
  </form>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Invoice draft records / 請求ドラフト一覧</h3>
  <table>
    <thead><tr><th>Invoice No.</th><th>Status</th><th>Month</th><th>Customer</th><th>Project</th><th class="num">Billable Time</th><th class="num">Subtotal</th><th class="num">Tax</th><th class="num">Total</th><th>Source</th><th>Action</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def invoice_draft_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    if not records:
        return "<tr><td colspan='11' class='muted'>No invoice drafts saved yet.</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("invoice_no", "")), reverse=True):
        status = str(record.get("invoice_status", "Draft"))
        invoice_id = escape(str(record.get("invoice_id", "")))
        action_html = ""
        if status != "Voided" and invoice_id:
            action_html = f"""
            <form method="post" action="/invoice-draft-void">
              <input type="hidden" name="invoice_id" value="{invoice_id}">
              <input name="void_reason" placeholder="Void reason">
              <button class="danger" type="submit">Void</button>
            </form>
            """
        rows.append(f"""
        <tr>
          <td>{value(record, 'invoice_no')}</td>
          <td><span class="pill">{escape(status)}</span></td>
          <td>{value(record, 'work_month')}</td>
          <td>{value(record, 'customer_name')}<br><span class="muted">{value(record, 'customer_code')}</span></td>
          <td>{value(record, 'project_code')}<br><span class="muted">{value(record, 'project_name')}</span></td>
          <td class="num">{format_minutes(record.get('billable_minutes', 0))}</td>
          <td class="num">{format_yen(record.get('subtotal_yen', 0))}</td>
          <td class="num">{format_yen(record.get('tax_yen', 0))}</td>
          <td class="num"><strong>{format_yen(record.get('total_yen', 0))}</strong></td>
          <td>{escape(str(len(record.get('source_record_ids', []))))} rows</td>
          <td>{action_html}</td>
        </tr>
        """)
    return "".join(rows)


def employee_select_options(selected_employee_no: str, context: dict[str, Any] | None = None) -> str:
    selected_employee_no = selected_employee_no.strip()
    option_html = []
    for employee in load_timesheet_employees(context):
        employee_no = str(employee.get("employee_no", ""))
        label_bits = [employee_no, str(employee.get("employee_name", ""))]
        organization_bits = [str(employee.get("department_name") or employee.get("department", "")).strip(), str(employee.get("team_name", "")).strip()]
        organization_label = " / ".join(bit for bit in organization_bits if bit)
        if organization_label:
            label_bits.append(organization_label)
        selected_attr = " selected" if employee_no == selected_employee_no else ""
        option_html.append(f"<option value='{h(employee_no)}'{selected_attr}>{h(' - '.join(bit for bit in label_bits if bit))}</option>")
    return "".join(option_html)


def project_select_options(selected_project_code: str, include_blank: bool = False, blank_label: str = "No project / 案件なし", context: dict[str, Any] | None = None) -> str:
    selected_project_code = selected_project_code.strip()
    option_html = []
    if include_blank:
        selected_attr = " selected" if not selected_project_code else ""
        option_html.append(f"<option value='' {selected_attr}>{h(blank_label)}</option>")
    for project in load_projects_for_context(context):
        project_code = str(project.get("project_code", ""))
        label_bits = [project_code, str(project.get("project_name", "")), str(project.get("customer_name", ""))]
        selected_attr = " selected" if project_code == selected_project_code else ""
        option_html.append(f"<option value='{h(project_code)}'{selected_attr}>{h(' - '.join(bit for bit in label_bits if bit))}</option>")
    return "".join(option_html)


def employee_source_status_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    status = employee_source_status(context)
    class_name = "notice" if status.get("source") == "employeeadmin" else "warn"
    return f'<p class="{class_name}">{h(t(messages, str(status.get("message_key", "message.employeeadmin_unavailable"))))}</p>'


def timesheet_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    record = record or default_timesheet_record()
    is_edit = mode == "edit"
    title = t(messages, "timesheet.edit_title") if is_edit else t(messages, "timesheet.new_title")
    action = url_with_lang("/timesheet-edit", lang) if is_edit else url_with_lang("/timesheet-new", lang)
    button_label = t(messages, "action.save_update") if is_edit else t(messages, "action.save_timesheet")
    hidden_id = f'<input type="hidden" name="record_id" value="{value(record, "record_id")}">' if is_edit else ""
    employees = load_timesheet_employees(context)
    projects = load_projects()
    status_label = approval_status(record) if is_edit else "Draft"
    lock_label = "Locked" if record_month_is_locked(record, context) else "Unlocked"
    employee_summary = " - ".join(bit for bit in [str(record.get("employee_no", "")), str(record.get("employee_name", "")), str(record.get("department", ""))] if bit) or t(messages, "field.employee")
    project_summary = " - ".join(bit for bit in [str(record.get("project_code", "")), str(record.get("project_name", "")), str(record.get("customer_name", ""))] if bit) or t(messages, "filter.no_project")
    if employees:
        employee_input = f"""
        <div><label>{h(t(messages, 'field.employee'))}</label><select name="employee_no" required>{employee_select_options(str(record.get('employee_no', '')), context)}</select></div>
        """
        employee_notice = employee_source_status_html(context)
    else:
        employee_input = f"""
        <div><label>{h(t(messages, 'field.employee_no'))}</label><input name="employee_no" required value="{value(record, 'employee_no')}" placeholder="E001"></div>
        """
        employee_notice = f'<p class="message-strip message-warning">{h(t(messages, "timesheet.no_employee_notice"))}</p>'
    project_input = f"""
        <div><label>{h(t(messages, 'field.project'))}</label><select name="project_code">{project_select_options(str(record.get('project_code', '')), include_blank=True, blank_label=t(messages, 'filter.no_project'), context=context)}</select></div>
    """ if projects else ""
    entry_mode = str(record.get("entry_mode", "") or "").strip() or "self"
    entry_source = str(record.get("entry_source", "") or "").strip() or ("web_proxy" if entry_mode == "proxy" else "web_self")
    assistance_reason = str(record.get("assistance_reason", "") or "").strip()
    assistance_note = str(record.get("assistance_note", "") or "").strip()
    entered_by = str(record.get("entered_by_name") or record.get("entered_by") or "")
    proxy_meta_html = ""
    if is_edit:
        proxy_meta_html = f"""
        <div class="sap-readonly-grid">
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.entry_mode'))}</div><div class="value">{h(t(messages, 'entry_mode.' + entry_mode, entry_mode or '-'))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.entered_by'))}</div><div class="value">{h(entered_by or '-')}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.on_behalf_of_employee_no'))}</div><div class="value">{value(record, 'on_behalf_of_employee_no') or value(record, 'employee_no')}</div></div>
        </div>
        """
    delete_html = ""
    if is_edit:
        delete_html = f"""
        <form method="post" action="{h(url_with_lang('/timesheet-delete', lang))}">
          <input type="hidden" name="record_id" value="{value(record, 'record_id')}">
          <button class="danger" type="submit">{h(t(messages, 'action.soft_delete'))}</button>
        </form>
        """
    return f"""
<section class="sap-page-header">
  <h2>{h(title)}</h2>
  <p class="muted">{h(t(messages, 'timesheet.form_notice'))}</p>
  <div class="sap-object-meta">
    <span class="status-badge status-{h(status_label.lower())}">{h(enum_label(messages, 'approval_status', status_label))}</span>
    <span class="status-badge">{h(lock_label)}</span>
    <span class="status-badge">{h(t(messages, 'field.employee'))}: {h(employee_summary)}</span>
    <span class="status-badge">{h(t(messages, 'field.project'))}: {h(project_summary)}</span>
  </div>
</section>
{employee_notice}
<form method="post" action="{h(action)}">
  {hidden_id}
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.section_basic', 'Basic Information'))}</h3>
    <div class="form-grid">
      {employee_input}
      <div><label>{h(t(messages, 'field.work_date'))}</label><input name="work_date" type="date" required value="{value(record, 'work_date')}"></div>
      <div><label>{h(t(messages, 'timesheet.field.attendance_status', 'Attendance Status'))}</label><select name="attendance_status">{select_options_i18n(ATTENDANCE_STATUSES, str(record.get('attendance_status', 'Worked')), messages, 'attendance_status')}</select></div>
    </div>
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.section_assistance', 'Assisted Entry / Proxy Input'))}</h3>
    <p class="muted">{h(t(messages, 'timesheet.assistance_notice', 'Use this area when Admin, HR, Finance, or a manager enters an attendance sheet received by email or from an offsite employee. Proxy entry is allowed only for open accounting periods.'))}</p>
    {proxy_meta_html}
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.entry_source', 'Entry Source'))}</label><select name="entry_source">{i18n_options(ENTRY_SOURCES, entry_source, messages, 'entry_source')}</select></div>
      <div><label>{h(t(messages, 'field.assistance_reason', 'Assistance Reason'))}</label><select name="assistance_reason">{i18n_options(ASSISTANCE_REASONS, assistance_reason, messages, 'assistance_reason')}</select></div>
    </div>
    <label>{h(t(messages, 'field.assistance_note', 'Assistance Note'))}</label>
    <textarea name="assistance_note" placeholder="{h(t(messages, 'timesheet.assistance_note_placeholder', 'Optional note, e.g. employee submitted attendance by email while offsite.'))}">{h(assistance_note)}</textarea>
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.section_work_time', 'Work Time'))}</h3>
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.start_time'))}</label><input name="start_time" required value="{value(record, 'start_time')}" placeholder="9:00 or 09:00"></div>
      <div><label>{h(t(messages, 'field.end_time'))}</label><input name="end_time" required value="{value(record, 'end_time')}" placeholder="18:00 or 24:00"></div>
      <div><label>{h(t(messages, 'field.break_minutes'))}</label><input name="break_minutes" type="number" min="0" step="1" value="{value(record, 'break_minutes')}"></div>
      <div><label>{h(t(messages, 'field.scheduled_work'))}</label><input name="scheduled_work_minutes" type="number" min="0" step="1" value="{value(record, 'scheduled_work_minutes')}"></div>
      <div><label>{h(t(messages, 'field.legal_holiday'))}</label>{bool_select_html('is_legal_holiday', bool(record.get('is_legal_holiday', False)), messages)}</div>
      <div><label>{h(t(messages, 'field.company_holiday'))}</label>{bool_select_html('is_company_holiday', bool(record.get('is_company_holiday', False)), messages)}</div>
    </div>
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.section_project', 'Project / Customer'))}</h3>
    <div class="form-grid">
      {project_input}
      <div><label>{h(t(messages, 'field.customer'))}</label><input value="{value(record, 'customer_name')}" readonly></div>
      <div><label>{h(t(messages, 'field.project_name'))}</label><input value="{value(record, 'project_name')}" readonly></div>
    </div>
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.calculation_breakdown'))}</h3>
    <p class="muted">{h(t(messages, 'timesheet.calculation_finalized_on_save'))}</p>
    {calculation_breakdown_html(record, messages)}
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'timesheet.section_remarks', 'Remarks'))}</h3>
    <label>{h(t(messages, 'field.remarks'))}</label>
    <textarea name="employee_remarks">{value(record, 'employee_remarks')}</textarea>
  </section>
  <div class="sap-toolbar">
    <a class="button ghost" href="{h(url_with_lang('/timesheets', lang))}">{h(t(messages, 'action.cancel'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/projects', lang))}">{h(t(messages, 'nav.projects'))}</a>
    <button type="submit">{h(button_label)}</button>
    {delete_html}
  </div>
</form>
"""


def user_identity_values(user: dict[str, Any]) -> list[str]:
    values = []
    employee_context = user.get("employee_context") if isinstance(user.get("employee_context"), dict) else {}
    for source in [employee_context, user]:
        for key in ["employee_id", "linked_employee_id", "employee_no", "employee_number", "employeeNo", "employeeNumber", "email", "username", "user_name", "name", "display_name"]:
            value_text = str(source.get(key, "") or "").strip().lower()
            if value_text:
                values.append(value_text)
    return values


def employee_context_from_user(context: dict[str, Any] | None) -> dict[str, Any]:
    if not context or not isinstance(context.get("user"), dict):
        return {}
    user = context["user"]
    employee_context = user.get("employee_context") if isinstance(user.get("employee_context"), dict) else {}
    return employee_context or user


def employee_id_from_user_context(context: dict[str, Any] | None) -> str:
    employee_context = employee_context_from_user(context)
    for key in ["employee_id", "linked_employee_id", "employee_master_id"]:
        value_text = str(employee_context.get(key, "") or "").strip()
        if value_text:
            return value_text
    return ""


def employee_no_from_user_context(context: dict[str, Any] | None) -> str:
    if not context or not isinstance(context.get("user"), dict):
        return ""
    employee_context = employee_context_from_user(context)
    for key in ["employee_no", "employee_number", "employeeNo", "employeeNumber"]:
        value_text = str(employee_context.get(key, "") or "").strip()
        if value_text:
            return value_text
    user = context["user"]
    identities = set(user_identity_values(user))
    matches = []
    for employee in load_timesheet_employees(context):
        employee_email = str(employee.get("email", "") or "").strip().lower()
        if employee_email and employee_email in identities:
            matches.append(employee)
    if len(matches) == 1:
        return str(matches[0].get("employee_no", "") or "").strip()
    return ""


def employee_no_from_record_or_text(record_or_employee_no: dict[str, Any] | str) -> str:
    if isinstance(record_or_employee_no, dict):
        return str(record_or_employee_no.get("employee_no", "") or record_or_employee_no.get("employee_no_snapshot", "") or "").strip()
    return str(record_or_employee_no or "").strip()


def employee_id_from_record(record: dict[str, Any]) -> str:
    for key in ["employee_id", "employee_master_id", "linked_employee_id"]:
        value_text = str(record.get(key, "") or "").strip()
        if value_text:
            return value_text
    return ""


def is_own_employee_record(record_or_employee_no: dict[str, Any] | str, context: dict[str, Any] | None = None) -> bool:
    if isinstance(record_or_employee_no, dict):
        record_employee_id = employee_id_from_record(record_or_employee_no)
        actor_employee_id = employee_id_from_user_context(context)
        if record_employee_id and actor_employee_id:
            return record_employee_id == actor_employee_id
    employee_no = employee_no_from_record_or_text(record_or_employee_no).lower()
    actor_employee_no = employee_no_from_user_context(context).lower()
    record_entity = str(record_or_employee_no.get("entity_id", "") if isinstance(record_or_employee_no, dict) else "").strip()
    actor_entity = current_entity_id(context)
    if record_entity and actor_entity and record_entity != actor_entity:
        return False
    return bool(employee_no and actor_employee_no and employee_no == actor_employee_no)


def i18n_options(options: list[tuple[str, str]], selected: str, messages: dict[str, str], prefix: str) -> str:
    option_html = []
    for option_value, label in options:
        selected_attr = " selected" if option_value == selected else ""
        label_text = t(messages, f"{prefix}.{option_value}", label) if option_value else t(messages, "filter.select", label)
        option_html.append(f"<option value='{h(option_value)}'{selected_attr}>{h(label_text)}</option>")
    return "".join(option_html)


def normalize_entry_source(source: str, is_proxy: bool) -> str:
    source = source.strip()
    allowed = {option for option, _label in ENTRY_SOURCES}
    if source in allowed:
        if not is_proxy and source != "web_self":
            return "web_self"
        if is_proxy and source == "web_self":
            return "web_proxy"
        return source
    return "email_manual" if is_proxy else "web_self"


def apply_timesheet_entry_metadata(record: dict[str, Any], form: dict[str, str], actor: str, context: dict[str, Any] | None = None, existing: dict[str, Any] | None = None) -> dict[str, Any]:
    user = (context or {}).get("user") if isinstance((context or {}).get("user"), dict) else None
    is_proxy = not is_own_employee_record(record, context)
    entry_mode = "proxy" if is_proxy else "self"
    entry_source = normalize_entry_source(form.get("entry_source", ""), is_proxy)
    assistance_reason = form.get("assistance_reason", "").strip()
    assistance_note = form.get("assistance_note", "").strip()
    if is_proxy and not assistance_reason:
        raise ValueError("Assistance reason is required when entering or editing another employee's timesheet.")

    if existing:
        for key in [
            "entry_mode",
            "entered_by",
            "entered_by_user_id",
            "entered_by_name",
            "on_behalf_of_employee_no",
            "entry_source",
            "assistance_reason",
            "assistance_note",
        ]:
            if key in existing and key not in record:
                record[key] = existing.get(key, "")
        record["last_modified_by"] = actor
        record["last_modified_by_user_id"] = user_identifier(user)
        record["last_modified_by_name"] = user_display_name(user)
        record["last_modified_entry_mode"] = entry_mode
        record["last_modified_at"] = datetime.now(timezone.utc).isoformat()
    else:
        record["entered_by"] = actor
        record["entered_by_user_id"] = user_identifier(user)
        record["entered_by_name"] = user_display_name(user)

    record["entry_mode"] = record.get("entry_mode") or entry_mode
    record["on_behalf_of_employee_no"] = str(record.get("employee_no", "") or "").strip()
    record["entry_source"] = entry_source
    record["assistance_reason"] = assistance_reason if is_proxy else assistance_reason or str(record.get("assistance_reason", "") or "").strip()
    record["assistance_note"] = assistance_note
    return record


def current_and_previous_work_months(today: date | None = None) -> tuple[str, str]:
    today = today or date.today()
    current_month = today.strftime("%Y-%m")
    previous_month_date = today.replace(day=1) - timedelta(days=1)
    return current_month, previous_month_date.strftime("%Y-%m")


def employee_edit_window_policy(work_date: str, record: dict[str, Any] | None = None, context: dict[str, Any] | None = None, allow_open_period: bool = False) -> dict[str, Any]:
    messages = context_messages(context)
    try:
        parsed_date = datetime.strptime(work_date.strip(), "%Y-%m-%d").date()
    except ValueError:
        return {"allowed": False, "reason": t(messages, "clock_entry.invalid_date"), "work_month": "", "is_locked": False}
    work_month = parsed_date.strftime("%Y-%m")
    current_month, previous_month = current_and_previous_work_months()
    if not allow_open_period and work_month not in {current_month, previous_month}:
        return {"allowed": False, "reason": t(messages, "clock_entry.outside_edit_window"), "work_month": work_month, "is_locked": is_month_locked(work_month, context)}
    if is_month_locked(work_month, context):
        return {"allowed": False, "reason": t(messages, "clock_entry.readonly_locked"), "work_month": work_month, "is_locked": True}
    if record and approval_status(record) in {"Submitted", "Approved"}:
        return {"allowed": False, "reason": t(messages, "clock_entry.readonly_status"), "work_month": work_month, "is_locked": False}
    return {"allowed": True, "reason": "", "work_month": work_month, "is_locked": False}


def employee_month_records(employee_no: str, work_month: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    employee_key = employee_no.strip().lower()
    if not employee_key:
        return []
    return [
        record
        for record in scope_records_to_current_entity(load_timesheet_entries(), context)
        if str(record.get("employee_no", "")).strip().lower() == employee_key
        and str(record.get("work_date", "")).startswith(work_month)
    ]


def month_date_range(work_month: str) -> tuple[date, date]:
    first_day = datetime.strptime(work_month + "-01", "%Y-%m-%d").date()
    if first_day.month == 12:
        next_month = first_day.replace(year=first_day.year + 1, month=1)
    else:
        next_month = first_day.replace(month=first_day.month + 1)
    return first_day, next_month - timedelta(days=1)


def employee_missing_weekdays(employee_no: str, work_month: str, records: list[dict[str, Any]]) -> list[str]:
    try:
        first_day, last_day = month_date_range(work_month)
    except ValueError:
        return []
    today = date.today()
    if work_month == today.strftime("%Y-%m"):
        last_day = min(last_day, today)
    recorded_dates = {str(record.get("work_date", "")) for record in records if record.get("record_status", "Active") != "Deleted"}
    missing = []
    cursor = first_day
    while cursor <= last_day:
        if cursor.weekday() < 5 and cursor.strftime("%Y-%m-%d") not in recorded_dates:
            missing.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return missing


def find_clock_entry_for_date(employee_no: str, work_date: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    employee_no = employee_no.strip().lower()
    work_date = work_date.strip()
    if not employee_no or not work_date:
        return None
    for record in scope_records_to_current_entity(load_timesheet_entries(include_deleted=True), context):
        if record.get("record_status", "Active") == "Deleted":
            continue
        if str(record.get("employee_no", "")).strip().lower() != employee_no:
            continue
        if str(record.get("work_date", "")).strip() != work_date:
            continue
        if str(record.get("project_code", "")).strip():
            continue
        return record
    return None


def clock_entry_employee_no_from_request(form: dict[str, str], context: dict[str, Any] | None = None) -> str:
    requested_employee_no = form.get("employee_no", "").strip()
    own_employee_no = employee_no_from_user_context(context)
    user = (context or {}).get("user") if isinstance((context or {}).get("user"), dict) else {}
    if requested_employee_no:
        if requested_employee_no.lower() == own_employee_no.lower():
            return requested_employee_no
        if can_proxy_submit(user):
            return requested_employee_no
        raise ValueError(t(context_messages(context), "clock_entry.proxy_permission_required", "Only Admin/HR/Finance users can select another employee."))
    if own_employee_no:
        return own_employee_no
    if can_proxy_submit(user):
        employees = load_timesheet_employees(context)
        if employees:
            return str(employees[0].get("employee_no", "") or "").strip()
    return ""


def default_clock_entry_record(context: dict[str, Any] | None = None, work_date: str = "", employee_no: str = "") -> dict[str, Any]:
    record = default_timesheet_record()
    record["employee_no"] = clock_entry_employee_no_from_request({"employee_no": employee_no}, context)
    record["work_date"] = work_date.strip() or datetime.now().strftime("%Y-%m-%d")
    record["start_time"] = ""
    record["end_time"] = ""
    record["break_minutes"] = 60
    record["project_code"] = ""
    record["attendance_status"] = "Worked"
    return record


def clock_entry_record_from_form(form: dict[str, str], context: dict[str, Any] | None = None) -> dict[str, Any]:
    employee_no = clock_entry_employee_no_from_request(form, context)
    if not employee_no:
        raise ValueError(t(context_messages(context), "clock_entry.employee_unresolved"))
    work_date = form.get("work_date", "").strip() or datetime.now().strftime("%Y-%m-%d")
    return {
        "employee_no": employee_no,
        "employee_name": "",
        "department": "",
        "customer_name": "",
        "project_code": "",
        "project_name": "",
        "dispatch_type": "Other",
        "work_location": "Other",
        "country": "Japan",
        "client_approval_required": False,
        "billing_enabled": False,
        "billing_rate_per_hour_yen": 0,
        "work_date": work_date,
        "attendance_status": "Worked",
        "start_time": form.get("start_time", "").strip(),
        "end_time": form.get("end_time", "").strip(),
        "break_minutes": parse_non_negative_int(form.get("break_minutes", "60"), "Break Minutes", default=60),
        "scheduled_work_minutes": DEFAULT_SCHEDULED_WORK_MINUTES,
        "night_work_minutes": 0,
        "is_legal_holiday": False,
        "is_company_holiday": False,
        "is_late": False,
        "is_early_leave": False,
        "late_minutes": 0,
        "early_leave_minutes": 0,
        "approval_status": "Draft",
        "employee_remarks": "",
        "manager_remarks": "",
    }


def save_clock_entry_from_form(form: dict[str, str], actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    record = clock_entry_record_from_form(form, context)
    existing = find_clock_entry_for_date(str(record.get("employee_no", "")), str(record.get("work_date", "")), context)
    is_proxy = not is_own_employee_record(record, context)
    policy = employee_edit_window_policy(str(record.get("work_date", "")), existing, context, allow_open_period=is_proxy)
    if not policy.get("allowed"):
        raise ValueError(str(policy.get("reason") or t(context_messages(context), "clock_entry.outside_edit_window")))
    metadata_form = dict(form)
    metadata_form["entry_source"] = normalize_entry_source(form.get("entry_source", ""), is_proxy)
    if existing:
        ensure_record_editable(existing)
        ensure_record_month_not_locked(existing, context)
        now = datetime.now(timezone.utc).isoformat()
        record["record_id"] = existing.get("record_id", "")
        record["record_status"] = existing.get("record_status", "Active")
        record["created_at"] = existing.get("created_at", now)
        record["updated_at"] = now
        record = apply_timesheet_entry_metadata(record, metadata_form, actor, context, existing=existing)
        return update_timesheet_entry(record, actor=actor, context=context)
    record = apply_timesheet_entry_metadata(record, metadata_form, actor, context)
    return save_timesheet_entry(record, actor=actor, context=context)


def clock_entry_form_html(record: dict[str, Any] | None = None, context: dict[str, Any] | None = None, message: str = "", error_message: str = "") -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    record = record or default_clock_entry_record(context)
    user = (context or {}).get("user") if isinstance((context or {}).get("user"), dict) else {}
    can_select_employee = can_proxy_submit(user)
    employee_no = str(record.get("employee_no", "") or "").strip()
    if employee_no:
        existing = find_clock_entry_for_date(employee_no, str(record.get("work_date", "")), context)
        if existing and not record.get("record_id"):
            record = existing
        try:
            display_record = calculate_timesheet_fields(enrich_timesheet_from_master_data(dict(record), context))
        except Exception:
            display_record = record
    else:
        display_record = record
        error_message = error_message or t(messages, "clock_entry.employee_unresolved")
    is_proxy_view = can_select_employee and not is_own_employee_record(employee_no, context)
    policy = employee_edit_window_policy(str(record.get("work_date", "")), record if record.get("record_id") else None, context, allow_open_period=is_proxy_view) if employee_no else {"allowed": False, "reason": ""}
    readonly_reason = str(policy.get("reason", ""))
    disabled = " disabled" if readonly_reason or not employee_no else ""
    current_month, previous_month = current_and_previous_work_months()
    today_text = date.today().strftime("%Y-%m-%d")
    yesterday_text = (date.today() - timedelta(days=1)).strftime("%Y-%m-%d")
    previous_month_day = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m-%d")
    date_shortcuts = "".join(
        f'<a class="button ghost" href="{h(url_with_lang("/clock-entry", lang, {"work_date": target, "employee_no": employee_no if can_select_employee else ""}))}">{h(label)}</a>'
        for label, target in [
            (t(messages, "clock_entry.today"), today_text),
            (t(messages, "clock_entry.yesterday"), yesterday_text),
            (t(messages, "clock_entry.previous_month"), previous_month_day),
        ]
    )
    dispatch_text = t(messages, "clock_entry.dispatch_auto_notice") if display_record.get("dispatch_assignment_matched") else t(messages, "clock_entry.no_assignment_notice")
    customer = str(display_record.get("customer_name", "") or "-")
    project = str(display_record.get("project_name", "") or "-")
    status_html = f'<p class="message-strip message-success">{h(message)}</p>' if message else ""
    error_html = f'<p class="message-strip message-warning">{h(error_message)}</p>' if error_message else ""
    readonly_html = f'<p class="message-strip message-warning">{h(readonly_reason)}</p>' if readonly_reason else ""
    break_value = h(record.get("break_minutes", 60))
    calculation_html = calculation_breakdown_html(display_record, messages) if display_record.get("start_time") and display_record.get("end_time") else f'<p class="muted">{h(t(messages, "clock_entry.calculation_after_save"))}</p>'
    employee_selector_html = ""
    proxy_assistance_html = ""
    if can_select_employee:
        employee_selector_html = f"""
        <div class="clock-entry-field"><label>{h(t(messages, 'field.employee'))}</label><select id="clock_employee_no" name="employee_no" required onchange="if(this.value) window.location='{h(url_with_lang('/clock-entry', lang))}&work_date=' + encodeURIComponent(document.getElementById('clock_work_date').value || '{h(str(record.get('work_date', '')))}') + '&employee_no=' + encodeURIComponent(this.value)">{employee_select_options(employee_no, context)}</select><p class="muted">{h(t(messages, 'clock_entry.proxy_employee_notice', 'Admin/HR/Finance users can select an employee and assist with entry.'))}</p></div>
        """
        proxy_source = normalize_entry_source(str(record.get("entry_source", "") or "web_proxy"), is_proxy_view)
        proxy_reason = str(record.get("assistance_reason", "") or "hr_finance_assisted")
        proxy_assistance_html = f"""
        <section class="sap-section">
          <h3>{h(t(messages, 'timesheet.section_assistance', 'Assisted Entry / Proxy Input'))}</h3>
          <p class="muted">{h(t(messages, 'clock_entry.proxy_notice', 'For Admin/HR/Finance assisted clock entry, select the employee and record the assistance source/reason.'))}</p>
          <div class="form-grid">
            <div><label>{h(t(messages, 'field.entry_source', 'Entry Source'))}</label><select name="entry_source">{i18n_options(ENTRY_SOURCES, proxy_source, messages, 'entry_source')}</select></div>
            <div><label>{h(t(messages, 'field.assistance_reason', 'Assistance Reason'))}</label><select name="assistance_reason">{i18n_options(ASSISTANCE_REASONS, proxy_reason, messages, 'assistance_reason')}</select></div>
          </div>
          <label>{h(t(messages, 'field.assistance_note', 'Assistance Note'))}</label>
          <textarea name="assistance_note" placeholder="{h(t(messages, 'timesheet.assistance_note_placeholder', 'Optional note, e.g. employee submitted attendance by email while offsite.'))}">{value(record, 'assistance_note')}</textarea>
        </section>
        """
    else:
        employee_selector_html = f'<input type="hidden" name="employee_no" value="{h(employee_no)}">'
    edit_window_notice = t(messages, "clock_entry.proxy_edit_window_notice", "Proxy entry can use any open accounting period.") if is_proxy_view else f"{t(messages, 'clock_entry.edit_window_notice')}: {current_month} / {previous_month}"
    return f"""
<section class="clock-entry-card">
  <section class="clock-entry-hero">
    <p class="eyebrow">{h(t(messages, 'nav.clock_entry'))}</p>
    <h2>{h(t(messages, 'clock_entry.title'))}</h2>
    <p class="muted">{h(t(messages, 'clock_entry.notice'))}</p>
    <div class="sap-object-meta">
      <span class="status-badge">{h(t(messages, 'field.work_date'))}: {value(record, 'work_date')}</span>
      <span class="status-badge">{h(t(messages, 'field.employee_no'))}: {h(employee_no or '-')}</span>
      <span class="status-badge status-{h(approval_status(record).lower())}">{h(enum_label(messages, 'approval_status', approval_status(record)))}</span>
    </div>
  </section>
  {status_html}
  {error_html}
  {readonly_html}
  <form method="post" action="{h(url_with_lang('/clock-entry', lang))}">
    <section class="sap-section">
      <h3>{h(t(messages, 'clock_entry.date_section'))}</h3>
      <p class="muted">{h(edit_window_notice)}</p>
      <div class="actions">{date_shortcuts}<a class="button secondary" href="{h(url_with_lang('/my-timesheet', lang, {'work_month': str(record.get('work_date', ''))[:7]}))}">{h(t(messages, 'nav.my_timesheet'))}</a></div>
      <div class="clock-entry-grid">
        {employee_selector_html}
        <div class="clock-entry-field"><label>{h(t(messages, 'field.work_date'))}</label><input id="clock_work_date" name="work_date" type="date" required value="{value(record, 'work_date')}" onchange="if(this.value) window.location='{h(url_with_lang('/clock-entry', lang))}&work_date=' + encodeURIComponent(this.value) + '{('&employee_no=' + h(employee_no)) if can_select_employee and employee_no else ''}'"><div class="actions"><button class="button secondary" type="submit" formmethod="get" formaction="{h(url_with_lang('/clock-entry', lang))}" formnovalidate>{h(t(messages, 'clock_entry.load_date'))}</button></div></div>
      </div>
    </section>
    {proxy_assistance_html}
    <section class="sap-section">
      <h3>{h(t(messages, 'clock_entry.time_input'))}</h3>
      <div class="clock-entry-grid">
        <div class="clock-entry-field"><label>{h(t(messages, 'field.start_time'))}</label><input id="start_time" name="start_time" inputmode="numeric" required value="{value(record, 'start_time')}" placeholder="09:00"{disabled}><div class="quick-break-actions"><button type="button" onclick="document.getElementById('start_time').value='09:00'"{disabled}>09:00</button><button type="button" onclick="document.getElementById('start_time').value='09:30'"{disabled}>09:30</button><button type="button" onclick="document.getElementById('start_time').value='10:00'"{disabled}>10:00</button><button type="button" onclick="document.getElementById('start_time').value='08:30'"{disabled}>08:30</button></div></div>
        <div class="clock-entry-field"><label>{h(t(messages, 'field.end_time'))}</label><input id="end_time" name="end_time" inputmode="numeric" required value="{value(record, 'end_time')}" placeholder="18:00"{disabled}><div class="quick-break-actions"><button type="button" onclick="document.getElementById('end_time').value='18:00'"{disabled}>18:00</button><button type="button" onclick="document.getElementById('end_time').value='18:30'"{disabled}>18:30</button><button type="button" onclick="document.getElementById('end_time').value='19:00'"{disabled}>19:00</button><button type="button" onclick="document.getElementById('end_time').value='17:30'"{disabled}>17:30</button></div></div>
        <div class="clock-entry-field"><label>{h(t(messages, 'field.break_minutes'))}</label><input id="break_minutes" name="break_minutes" type="number" min="0" step="1" required value="{break_value}"{disabled}>
          <div class="quick-break-actions">
            <button type="button" onclick="document.getElementById('break_minutes').value='0'"{disabled}>0</button>
            <button type="button" onclick="document.getElementById('break_minutes').value='45'"{disabled}>45</button>
            <button type="button" onclick="document.getElementById('break_minutes').value='60'"{disabled}>60</button>
            <button type="button" onclick="document.getElementById('break_minutes').value='90'"{disabled}>90</button>
          </div>
        </div>
      </div>
    </section>
    <section class="sap-section">
      <h3>{h(t(messages, 'clock_entry.dispatch_title'))}</h3>
      <p class="muted">{h(dispatch_text)}</p>
      <div class="sap-readonly-grid">
        <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.customer'))}</div><div class="value">{h(customer)}</div></div>
        <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.project_name'))}</div><div class="value">{h(project)}</div></div>
      </div>
    </section>
    <section class="sap-section">
      <h3>{h(t(messages, 'timesheet.section_calculation'))}</h3>
      {calculation_html}
    </section>
    <div class="sap-toolbar">
      <a class="button ghost" href="{h(url_with_lang('/timesheets', lang))}">{h(t(messages, 'action.open_timesheets'))}</a>
      <button class="clock-entry-submit" type="submit"{disabled}>{h(t(messages, 'clock_entry.save_button'))}</button>
    </div>
  </form>
</section>
"""


def my_timesheet_html(query: dict[str, list[str]], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    employee_no = employee_no_from_user_context(context)
    current_month, previous_month = current_and_previous_work_months()
    requested_month = query.get("work_month", [""])[0].strip() or current_month
    try:
        work_month = normalize_work_month(requested_month)
    except ValueError:
        work_month = current_month
    if work_month not in {current_month, previous_month}:
        work_month = current_month
    if not employee_no:
        return f"""
<section class="sap-page-header">
  <p class="eyebrow">{h(t(messages, 'nav.my_timesheet'))}</p>
  <h2>{h(t(messages, 'my_timesheet.title'))}</h2>
  <p class="message-strip message-warning">{h(t(messages, 'clock_entry.employee_unresolved'))}</p>
</section>
"""
    records = employee_month_records(employee_no, work_month, context)
    totals = calculate_timesheet_totals(records)
    missing_dates = employee_missing_weekdays(employee_no, work_month, records)
    counts = {status: 0 for status, _label in APPROVAL_STATUSES}
    for record in records:
        counts[approval_status(record)] = counts.get(approval_status(record), 0) + 1
    locked = is_month_locked(work_month, context)
    lock_label = t(messages, "my_timesheet.locked") if locked else t(messages, "my_timesheet.open")
    month_tabs = "".join(
        f'<a class="button {"" if month == work_month else "ghost"}" href="{h(url_with_lang("/my-timesheet", lang, {"work_month": month}))}">{h(label)} {h(month)}</a>'
        for label, month in [(t(messages, "my_timesheet.current_month"), current_month), (t(messages, "my_timesheet.previous_month"), previous_month)]
    )
    missing_html = "".join(
        f'<a class="button ghost" href="{h(url_with_lang("/clock-entry", lang, {"work_date": missing_date}))}">{h(missing_date)}</a>'
        for missing_date in missing_dates[:12]
    )
    if not missing_html:
        missing_html = f'<p class="muted">{h(t(messages, "my_timesheet.no_missing"))}</p>'
    elif len(missing_dates) > 12:
        missing_html += f'<span class="muted">+{len(missing_dates) - 12}</span>'
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("work_date", "")), reverse=True):
        status = approval_status(record)
        policy = employee_edit_window_policy(str(record.get("work_date", "")), record, context)
        action = f'<a class="button secondary" href="{h(url_with_lang("/clock-entry", lang, {"work_date": str(record.get("work_date", ""))}))}">{h(t(messages, "action.edit" if policy.get("allowed") else "action.view", "View"))}</a>'
        rows.append(f"""
        <article class="my-day-card">
          <div><strong>{value(record, 'work_date')}</strong><br><span class="muted">{value(record, 'weekday')}</span></div>
          <div>{value(record, 'start_time')} - {value(record, 'end_time')}<br><span class="muted">{h(t(messages, 'field.break'))}: {value(record, 'break_minutes')} min</span></div>
          <div><strong>{format_minutes(record.get('actual_work_minutes', 0))}</strong><br><span class="muted">OT {format_minutes(record.get('overtime_minutes', 0))}</span></div>
          <div><span class="status-badge status-{h(status.lower())}">{h(enum_label(messages, 'approval_status', status))}</span><br><span class="muted">{h(lock_label)}</span></div>
          <div>{action}</div>
        </article>
        """)
    records_html = "".join(rows) or f'<p class="muted">{h(t(messages, "my_timesheet.no_records"))}</p>'
    return f"""
<section class="sap-page-header">
  <p class="eyebrow">{h(t(messages, 'nav.my_timesheet'))}</p>
  <h2>{h(t(messages, 'my_timesheet.title'))}</h2>
  <p class="muted">{h(t(messages, 'field.employee_no'))}: {h(employee_no)} / {h(t(messages, 'field.work_month'))}: {h(work_month)} / {h(t(messages, 'field.lock'))}: {h(lock_label)}</p>
  <div class="actions">{month_tabs}<a class="button" href="{h(url_with_lang('/clock-entry', lang))}">{h(t(messages, 'nav.clock_entry'))}</a></div>
</section>
<section class="grid">
  <div class="card"><h3>{h(t(messages, 'field.entries_days'))}</h3><div class="metric">{len(records)}</div></div>
  <div class="card"><h3>{h(t(messages, 'timesheet.actual_work'))}</h3><div class="metric">{format_minutes(totals['actual_work_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'timesheet.overtime'))}</h3><div class="metric">{format_minutes(totals['overtime_minutes'])}</div></div>
  <div class="card"><h3>{h(t(messages, 'my_timesheet.missing_days'))}</h3><div class="metric">{len(missing_dates)}</div></div>
</section>
<section class="grid" style="margin-top: 16px;">
  <div class="card"><h3>{h(enum_label(messages, 'approval_status', 'Draft'))}</h3><div class="metric">{counts.get('Draft', 0)}</div></div>
  <div class="card"><h3>{h(enum_label(messages, 'approval_status', 'Submitted'))}</h3><div class="metric">{counts.get('Submitted', 0)}</div></div>
  <div class="card"><h3>{h(enum_label(messages, 'approval_status', 'Approved'))}</h3><div class="metric">{counts.get('Approved', 0)}</div></div>
  <div class="card"><h3>{h(enum_label(messages, 'approval_status', 'Rejected'))}</h3><div class="metric">{counts.get('Rejected', 0)}</div></div>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'my_timesheet.missing_title'))}</h3>
  <p class="muted">{h(t(messages, 'my_timesheet.missing_notice'))}</p>
  <div class="actions">{missing_html}</div>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'my_timesheet.daily_title'))}</h3>
  <div class="my-day-list">{records_html}</div>
</section>
"""


def operation_success_message(record_type: str, record_name: str, action: str, actor: str = LOCAL_ACTOR, lang: str = "en") -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    actor = actor or "-"
    if lang == "zh":
        action_text = {"saved": "保存", "deleted": "删除", "submitted": "提交", "approved": "审批通过", "rejected": "退回", "reopened": "重新打开"}.get(action, action)
        return f"{record_type}记录 {record} 已于 {timestamp} 由 {actor} {action_text}成功。"
    if lang == "ja":
        action_text = {"saved": "保存", "deleted": "削除", "submitted": "提出", "approved": "承認", "rejected": "差戻し", "reopened": "再オープン"}.get(action, action)
        return f"{record_type} レコード {record} は {timestamp} に {actor} により{action_text}されました。"
    return f"{record_type} record {record} {action} successfully at {timestamp} by {actor}."


def no_change_message(record_type: str, record_name: str, lang: str = "en") -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    if lang == "zh":
        return f"{timestamp} 未检测到 {record_type}记录 {record} 的变更。未保存，也未生成审计记录。"
    if lang == "ja":
        return f"{timestamp} 時点で {record_type} レコード {record} に変更はありません。保存および監査記録の作成は行われませんでした。"
    return f"No changes detected for {record_type} record {record} at {timestamp}. Nothing was saved and no audit entry was created."


def timesheet_record_label(record: dict[str, Any]) -> str:
    return str(record.get("record_id") or f"{record.get('employee_no', '')}/{record.get('work_date', '')}").strip()


def project_record_label(record: dict[str, Any]) -> str:
    return str(record.get("project_code") or record.get("project_id") or "").strip()

def timesheet_saved_html(record: dict[str, Any], message: str = "", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    message = message or operation_success_message("Timesheet", timesheet_record_label(record), "saved", lang=lang)
    entry_mode = str(record.get("entry_mode", "") or "self")
    entry_source = str(record.get("entry_source", "") or "")
    assistance_reason = str(record.get("assistance_reason", "") or "")
    entered_by = str(record.get("entered_by_name") or record.get("entered_by") or "-")
    return f"""
<section class="panel">
  <h2>{h(t(messages, 'timesheet.saved_title'))}</h2>
  <p class="message-strip message-success">{h(message)}</p>
  <div class="grid">
    <div class="card"><h3>{h(t(messages, 'field.employee_no'))}</h3><p>{value(record, 'employee_no')}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.work_date'))}</h3><p>{value(record, 'work_date')} ({value(record, 'weekday')})</p></div>
    <div class="card"><h3>{h(t(messages, 'field.entry_mode', 'Entry Mode'))}</h3><p>{h(t(messages, 'entry_mode.' + entry_mode, entry_mode))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.entered_by', 'Entered By'))}</h3><p>{h(entered_by)}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.entry_source', 'Entry Source'))}</h3><p>{h(t(messages, 'entry_source.' + entry_source, entry_source or '-'))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.assistance_reason', 'Assistance Reason'))}</h3><p>{h(t(messages, 'assistance_reason.' + assistance_reason, assistance_reason or '-'))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.time'))}</h3><p>{value(record, 'start_time')} - {value(record, 'end_time')}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.break'))}</h3><p>{value(record, 'break_minutes')} min</p></div>
    <div class="card"><h3>{h(t(messages, 'timesheet.actual_work'))}</h3><p>{format_minutes(record.get('actual_work_minutes', 0))}</p></div>
    <div class="card"><h3>{h(t(messages, 'timesheet.overtime'))}</h3><p>{format_minutes(record.get('overtime_minutes', 0))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.gross_work'))}</h3><p>{format_minutes(record.get('gross_work_minutes', 0))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.night_work'))}</h3><p>{format_minutes(record.get('night_work_minutes', 0))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.holiday_work'))}</h3><p>{format_minutes(record.get('holiday_work_minutes', 0))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.break_shortage'))}</h3><p>{format_minutes(record.get('break_shortage_minutes', 0))}</p></div>
  </div>
  {f'<p class="message-strip message-warning">{h(record.get("break_warning", ""))}</p>' if str(record.get('break_warning', '')).strip() else ''}
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/timesheets', lang))}">{h(t(messages, 'action.open_timesheets'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/timesheet-new', lang))}">{h(t(messages, 'action.input_timesheet'))}</a>
  </div>
</section>
"""


def employees_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    records = load_timesheet_employees(context)
    status = employee_source_status(context)
    rows_html = employee_table_rows(records, context=context, read_only=status.get("source") == "employeeadmin")
    source_text_key = "employee.source_employeeadmin" if status.get("source") == "employeeadmin" else "employee.source_local"
    actions = f'<a class="button" href="{h(EMPLOYEEADMIN_BASE_URL + "/employees?" + urlencode({"lang": lang}))}">{h(t(messages, "action.manage_in_employeeadmin"))}</a>'
    return f"""
<section class="panel">
  <h2>{h(t(messages, 'employee.title'))}</h2>
  <p class="notice">{h(t(messages, source_text_key))}</p>
  {employee_source_status_html(context)}
  <div class="actions">
    {actions}
    <a class="button secondary" href="{h(url_with_lang('/timesheet-new', lang))}">{h(t(messages, 'action.input_timesheet'))}</a>
  </div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>{h(t(messages, 'employee.active_title'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'field.employee_no'))}</th><th>{h(t(messages, 'field.employee_name'))}</th><th>{h(t(messages, 'field.department'))}</th><th>{h(t(messages, 'field.email'))}</th><th class="num">{h(t(messages, 'field.scheduled_work'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.source'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def employee_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None, read_only: bool = False) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    if not records:
        return f"<tr><td colspan='8' class='muted'>{h(t(messages, 'employee.no_records'))}</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("employee_no", ""))):
        employee_id = h(str(record.get("employee_id", "")))
        if read_only:
            action_html = ""
        else:
            edit_link = f"<a class='button secondary' href='{h(url_with_lang('/employee-edit', lang, {'id': employee_id}))}'>{h(t(messages, 'action.edit'))}</a>" if employee_id else ""
            delete_form = f"<form method='post' action='{h(url_with_lang('/employee-delete', lang))}'><input type='hidden' name='employee_id' value='{employee_id}'><button class='danger' type='submit'>{h(t(messages, 'action.soft_delete'))}</button></form>" if employee_id else ""
            action_html = f"<div class='actions'>{edit_link}{delete_form}</div>"
        rows.append(f"""
        <tr>
          <td>{value(record, 'employee_no')}</td>
          <td>{value(record, 'employee_name')}</td>
          <td>{value(record, 'department')}</td>
          <td>{value(record, 'email')}</td>
          <td class="num">{format_minutes(record.get('default_scheduled_work_minutes', DEFAULT_SCHEDULED_WORK_MINUTES))}</td>
          <td><span class="pill">{value(record, 'employment_status') or value(record, 'record_status')}</span></td>
          <td>{value(record, 'source')}</td>
          <td>{action_html}</td>
        </tr>
        """)
    return "".join(rows)


def employee_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    record = record or default_employee_record()
    is_edit = mode == "edit"
    title = "Edit employee / 社員編集" if is_edit else "New employee / 社員追加"
    action = "/employee-edit" if is_edit else "/employee-new"
    button_label = "Save Employee Update / 社員更新" if is_edit else "Save Employee / 社員保存"
    hidden_id = f'<input type="hidden" name="employee_id" value="{value(record, "employee_id")}">' if is_edit else ""
    return f"""
<section class="panel">
  <h2>{title}</h2>
  <p class="notice">Employee master records control which employee numbers can be selected for timesheet input.</p>
</section>
<section class="panel" style="margin-top: 18px;">
  <form method="post" action="{action}">
    {hidden_id}
    <div class="form-grid">
      <div><label>Employee No. / 社員No.</label><input name="employee_no" required value="{value(record, 'employee_no')}" placeholder="E001"></div>
      <div><label>Employee Name / 氏名</label><input name="employee_name" required value="{value(record, 'employee_name')}" placeholder="Taro Yamada"></div>
      <div><label>Department / 部署</label><input name="department" value="{value(record, 'department')}" placeholder="Engineering"></div>
      <div><label>Email / メール</label><input name="email" type="email" value="{value(record, 'email')}" placeholder="employee@example.com"></div>
      <div><label>Default Scheduled Work Minutes / 標準所定労働時間</label><input name="default_scheduled_work_minutes" type="number" min="0" step="1" value="{value(record, 'default_scheduled_work_minutes')}"></div>
    </div>
    <div class="actions">
      <button type="submit">{button_label}</button>
      <a class="button secondary" href="/employees">Cancel / キャンセル</a>
    </div>
  </form>
</section>
"""


def employee_saved_html(record: dict[str, Any], message: str = "Employee saved.") -> str:
    return f"""
<section class="panel">
  <h2>Employee saved / 社員保存完了</h2>
  <p class="message-strip message-success">{escape(message)}</p>
  <div class="grid">
    <div class="card"><h3>Employee No.</h3><p>{value(record, 'employee_no')}</p></div>
    <div class="card"><h3>Name</h3><p>{value(record, 'employee_name')}</p></div>
    <div class="card"><h3>Department</h3><p>{value(record, 'department')}</p></div>
    <div class="card"><h3>Scheduled Work</h3><p>{format_minutes(record.get('default_scheduled_work_minutes', 480))}</p></div>
  </div>
  <div class="actions">
    <a class="button" href="/employees">Open Employees</a>
    <a class="button secondary" href="/employee-new">Add Next Employee</a>
  </div>
</section>
"""


def projects_html(context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    records = load_projects_for_context(context)
    rows_html = project_table_rows(records, context)
    return f"""
<section class="panel">
  <h2>Projects / 案件・顧客マスタ</h2>
  <p class="notice">Manage project/customer records for timesheet grouping, monthly statistics, and future invoicing.</p>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/project-new', lang))}">New Project / 案件追加</a>
    <a class="button secondary" href="{h(url_with_lang('/timesheet-new', lang))}">Input Timesheet</a>
  </div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Active projects / 有効案件</h3>
  <table>
    <thead><tr><th>Project Code</th><th>Project Name</th><th>Customer</th><th>Dispatch</th><th>Location</th><th>Client Approval</th><th>Billing</th><th class="num">Rate / Hour</th><th>Action</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def project_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    if not records:
        return "<tr><td colspan='9' class='muted'>No active projects saved yet.</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("project_code", ""))):
        project_id = escape(str(record.get("project_id", "")))
        lang = context_lang(context)
        edit_link = f"<a class='button secondary' href='{h(url_with_lang('/project-edit', lang, {'id': project_id}))}'>Edit</a>" if project_id else ""
        delete_form = f"<form method='post' action='{h(url_with_lang('/project-delete', lang))}'><input type='hidden' name='project_id' value='{project_id}'><button class='danger' type='submit'>Soft Delete</button></form>" if project_id else ""
        client_approval = "Yes" if record.get("client_approval_required") else "No"
        billing = "Yes" if record.get("billing_enabled") else "No"
        rows.append(f"""
        <tr>
          <td>{value(record, 'project_code')}</td>
          <td>{value(record, 'project_name')}</td>
          <td>{value(record, 'customer_name')}<br><span class="muted">{value(record, 'customer_code')}</span></td>
          <td>{value(record, 'dispatch_type')}</td>
          <td>{value(record, 'work_location')}<br><span class="muted">{value(record, 'prefecture')}</span></td>
          <td>{escape(client_approval)}</td>
          <td>{escape(billing)}<br><span class="muted">{value(record, 'billing_note')}</span></td>
          <td class="num">{format_yen(record.get('billing_rate_per_hour_yen', 0))}</td>
          <td><div class="actions">{edit_link}{delete_form}</div></td>
        </tr>
        """)
    return "".join(rows)


def project_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    record = apply_current_entity_snapshot(record or default_project_record(), context)
    is_edit = mode == "edit"
    title = "Edit project / 案件編集" if is_edit else "New project / 案件追加"
    lang = context_lang(context)
    action = url_with_lang("/project-edit", lang) if is_edit else url_with_lang("/project-new", lang)
    button_label = "Save Project Update / 案件更新" if is_edit else "Save Project / 案件保存"
    hidden_id = f'<input type="hidden" name="project_id" value="{value(record, "project_id")}">' if is_edit else ""
    return f"""
<section class="panel">
  <h2>{title}</h2>
  <p class="notice">Project/customer master records are copied into timesheet rows when selected, preserving a snapshot for reporting and future invoicing.</p>
</section>
<section class="panel" style="margin-top: 18px;">
  <form method="post" action="{action}">
    {hidden_id}
    <div class="form-grid">
      <div><label>Project Code / 案件コード</label><input name="project_code" required value="{value(record, 'project_code')}" placeholder="P001"></div>
      <div><label>Project Name / 案件名</label><input name="project_name" required value="{value(record, 'project_name')}" placeholder="Customer Support"></div>
      <div><label>Customer Name / 顧客名</label><input name="customer_name" required value="{value(record, 'customer_name')}" placeholder="ABC Corp"></div>
      <div><label>Customer Code / 顧客コード</label><input name="customer_code" value="{value(record, 'customer_code')}" placeholder="C001"></div>
      <div><label>Dispatch Type / 外派区分</label><select name="dispatch_type">{select_options(DISPATCH_TYPES, str(record.get('dispatch_type', 'Client Site')))}</select></div>
      <div><label>Work Location / 勤務場所</label><select name="work_location">{select_options(WORK_LOCATIONS, str(record.get('work_location', 'Customer Site')))}</select></div>
      <div><label>Country / 国</label><input name="country" value="{value(record, 'country')}" placeholder="Japan"></div>
      <div><label>Prefecture / 都道府県</label><input name="prefecture" value="{value(record, 'prefecture')}" placeholder="Tokyo"></div>
      <div><label>Client Approval Required</label><select name="client_approval_required">{select_options(BOOLEAN_SELECT, bool_value(record, 'client_approval_required'))}</select></div>
      <div><label>Billing Enabled / 請求対象</label><select name="billing_enabled">{select_options(BOOLEAN_SELECT, bool_value(record, 'billing_enabled'))}</select></div>
      <div><label>Billing Rate per Hour JPY / 時間単価</label><input name="billing_rate_per_hour_yen" type="number" min="0" step="1" value="{value(record, 'billing_rate_per_hour_yen')}"></div>
      <div><label>Billing Note / 請求メモ</label><input name="billing_note" value="{value(record, 'billing_note')}" placeholder="Optional billing memo"></div>
    </div>
    <div class="actions">
      <button type="submit">{button_label}</button>
      <a class="button secondary" href="{h(url_with_lang('/projects', lang))}">Cancel / キャンセル</a>
    </div>
  </form>
</section>
"""


def project_saved_html(record: dict[str, Any], message: str = "", context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    message = message or operation_success_message("Project", project_record_label(record), "saved")
    return f"""
<section class="panel">
  <h2>Project saved / 案件保存完了</h2>
  <p class="good">{escape(message)}</p>
  <div class="grid">
    <div class="card"><h3>Project Code</h3><p>{value(record, 'project_code')}</p></div>
    <div class="card"><h3>Project Name</h3><p>{value(record, 'project_name')}</p></div>
    <div class="card"><h3>Customer</h3><p>{value(record, 'customer_name')}</p></div>
    <div class="card"><h3>Location</h3><p>{value(record, 'work_location')}</p></div>
    <div class="card"><h3>Billing Rate / 時間単価</h3><p>{format_yen(record.get('billing_rate_per_hour_yen', 0))}</p></div>
  </div>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/projects', lang))}">Open Projects</a>
    <a class="button secondary" href="{h(url_with_lang('/project-new', lang))}">Add Next Project</a>
  </div>
</section>
"""


def organization_header_html(messages: dict[str, str], eyebrow_key: str, title_key: str, notice_key: str, chips: list[tuple[str, Any]]) -> str:
    chip_html = "".join(f"<div class='meta-chip'><span class='meta-chip-label'>{h(label)}</span><span class='meta-chip-value'>{h(value_text)}</span></div>" for label, value_text in chips)
    return f"""
<section class="object-header">
  <div>
    <p class="eyebrow">{h(t(messages, eyebrow_key))}</p>
    <h2>{h(t(messages, title_key))}</h2>
    <p class="muted">{h(t(messages, notice_key))}</p>
  </div>
  <div class="object-meta">{chip_html}</div>
</section>
"""


def entity_select_options(selected_entity_id: str, include_blank: bool = False, blank_label: str = "", context: dict[str, Any] | None = None) -> str:
    options = []
    if include_blank:
        options.append(f"<option value=''{' selected' if not selected_entity_id else ''}>{h(blank_label)}</option>")
    for entity in sorted(scope_records_to_current_entity(load_entities(), context), key=lambda item: (str(item.get("entity_code", "")), str(item.get("entity_name", "")))):
        entity_id = str(entity.get("entity_id", ""))
        selected_attr = " selected" if entity_id == selected_entity_id else ""
        label = " - ".join(bit for bit in [str(entity.get("entity_code", "")), str(entity.get("entity_name", ""))] if bit)
        options.append(f"<option value='{h(entity_id)}'{selected_attr}>{h(label)}</option>")
    return "".join(options)


def department_select_options(selected_department_id: str, include_blank: bool = False, blank_label: str = "", entity_id: str = "", context: dict[str, Any] | None = None) -> str:
    options = []
    if include_blank:
        options.append(f"<option value=''{' selected' if not selected_department_id else ''}>{h(blank_label)}</option>")
    departments = scope_records_to_current_entity(load_departments(), context)
    if entity_id:
        departments = [record for record in departments if str(record.get("entity_id", "")) == entity_id]
    for department in sorted(departments, key=lambda item: (str(item.get("entity_code", "")), str(item.get("department_code", "")))):
        department_id = str(department.get("department_id", ""))
        selected_attr = " selected" if department_id == selected_department_id else ""
        label = " / ".join(bit for bit in [str(department.get("entity_code", "")), str(department.get("department_code", "")), str(department.get("department_name", ""))] if bit)
        options.append(f"<option value='{h(department_id)}'{selected_attr}>{h(label)}</option>")
    return "".join(options)


def organization_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    entities = load_entities()
    departments = scope_records_to_current_entity(load_departments(), context)
    teams = load_teams()
    header = organization_header_html(messages, "organization.eyebrow", "organization.title", "organization.notice", [(t(messages, "organization.entities"), len(entities)), (t(messages, "organization.departments"), len(departments)), (t(messages, "organization.teams"), len(teams))])
    hierarchy = organization_hierarchy_html(entities, departments, teams, messages)
    return f"""
<section class="object-page">
  {header}
  <section class="grid">
    <div class="card"><h3>{h(t(messages, 'organization.entities'))}</h3><div class="metric">{len(entities)}</div><p class="muted">{h(t(messages, 'organization.entities_desc'))}</p></div>
    <div class="card"><h3>{h(t(messages, 'organization.departments'))}</h3><div class="metric">{len(departments)}</div><p class="muted">{h(t(messages, 'organization.departments_desc'))}</p></div>
    <div class="card"><h3>{h(t(messages, 'organization.teams'))}</h3><div class="metric">{len(teams)}</div><p class="muted">{h(t(messages, 'organization.teams_desc'))}</p></div>
  </section>
  <section class="sap-section">
    <div class="section-header"><h3>{h(t(messages, 'organization.structure_title'))}</h3></div>
    <div class="section-body">{hierarchy}</div>
  </section>
  <div class="sap-toolbar">
    <a class="button ghost" href="{h(url_with_lang('/', lang))}">{h(t(messages, 'nav.dashboard'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/entities', lang))}">{h(t(messages, 'nav.entities'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/departments', lang))}">{h(t(messages, 'nav.departments'))}</a>
    <a class="button" href="{h(url_with_lang('/teams', lang))}">{h(t(messages, 'nav.teams'))}</a>
  </div>
</section>
"""


def organization_hierarchy_html(entities: list[dict[str, Any]], departments: list[dict[str, Any]], teams: list[dict[str, Any]], messages: dict[str, str]) -> str:
    if not entities:
        return f"<p class='muted'>{h(t(messages, 'organization.no_structure'))}</p>"
    blocks = []
    for entity in sorted(entities, key=lambda item: str(item.get("entity_code", ""))):
        entity_departments = [department for department in departments if department.get("entity_id") == entity.get("entity_id")]
        if entity_departments:
            department_html_parts = []
            for department in sorted(entity_departments, key=lambda item: str(item.get("department_code", ""))):
                department_teams = [team for team in teams if team.get("department_id") == department.get("department_id")]
                teams_html = "".join(f"<div class='hierarchy-team'>↳ {h(team.get('team_code', ''))} {h(team.get('team_name', ''))}</div>" for team in sorted(department_teams, key=lambda item: str(item.get("team_code", ""))))
                if not teams_html:
                    teams_html = f"<div class='hierarchy-team'>{h(t(messages, 'organization.no_teams'))}</div>"
                department_html_parts.append(f"<div class='hierarchy-department'><strong>{h(department.get('department_code', ''))} {h(department.get('department_name', ''))}</strong>{teams_html}</div>")
            departments_html = "".join(department_html_parts)
        else:
            departments_html = f"<div class='hierarchy-department'>{h(t(messages, 'organization.no_departments'))}</div>"
        blocks.append(f"<article class='hierarchy-entity'><h3>{h(entity.get('entity_code', ''))} {h(entity.get('entity_name', ''))}</h3>{departments_html}</article>")
    return f"<div class='hierarchy-list'>{''.join(blocks)}</div>"


def entities_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    records = scope_records_to_current_entity(load_entities(), context)
    rows_html = entity_table_rows(records, context)
    return f"""
{organization_header_html(messages, 'organization.eyebrow', 'entity.title', 'entity.notice', [(t(messages, 'organization.entities'), len(records))])}
<section class="sap-section">
  <div class="section-header"><h3>{h(t(messages, 'entity.active_title'))}</h3></div>
  <div class="section-body">
    <div class="actions"><a class="button" href="{h(url_with_lang('/entity-new', lang))}">{h(t(messages, 'action.new_entity'))}</a><a class="button secondary" href="{h(url_with_lang('/organization', lang))}">{h(t(messages, 'nav.organization'))}</a></div>
    <div class="table-scroll"><table><thead><tr><th>{h(t(messages, 'field.entity_code'))}</th><th>{h(t(messages, 'field.entity_name'))}</th><th>{h(t(messages, 'field.country'))}</th><th>{h(t(messages, 'field.registration_no'))}</th><th>{h(t(messages, 'field.effective_period'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead><tbody>{rows_html}</tbody></table></div>
  </div>
</section>
"""


def entity_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    if not records:
        return f"<tr><td colspan='6' class='muted'>{h(t(messages, 'entity.no_records'))}</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("entity_code", ""))):
        entity_id = str(record.get("entity_id", ""))
        rows.append(f"""
        <tr><td>{value(record, 'entity_code')}</td><td>{value(record, 'entity_name')}</td><td>{value(record, 'country')}</td><td>{value(record, 'registration_no')}</td><td>{value(record, 'effective_from')} - {value(record, 'effective_to') or '-'}</td><td><div class='actions'><a class='button secondary' href='{h(url_with_lang('/entity-edit', lang, {'id': entity_id}))}'>{h(t(messages, 'action.edit'))}</a><form method='post' action='{h(url_with_lang('/entity-delete', lang))}'><input type='hidden' name='entity_id' value='{h(entity_id)}'><button class='danger' type='submit'>{h(t(messages, 'action.soft_delete'))}</button></form></div></td></tr>
        """)
    return "".join(rows)


def entity_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    record = record or default_entity_record()
    is_edit = mode == "edit"
    title_key = "entity.edit_title" if is_edit else "entity.new_title"
    action = url_with_lang("/entity-edit", lang) if is_edit else url_with_lang("/entity-new", lang)
    hidden_id = f'<input type="hidden" name="entity_id" value="{value(record, "entity_id")}">' if is_edit else ""
    button_key = "action.save_entity_update" if is_edit else "action.save_entity"
    return f"""
{organization_header_html(messages, 'organization.eyebrow', title_key, 'entity.form_notice', [(t(messages, 'field.entity_code'), record.get('entity_code', '-') or '-'), (t(messages, 'field.status'), record.get('record_status', 'Active'))])}
<form method="post" action="{h(action)}">
  {hidden_id}
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'organization.section_basic'))}</h3></div><div class="section-body"><div class="form-grid">
    <div class="form-field"><label>{h(t(messages, 'field.entity_code'))}</label><input name="entity_code" required value="{value(record, 'entity_code')}" placeholder="TAC-JP"></div>
    <div class="form-field"><label>{h(t(messages, 'field.entity_name'))}</label><input name="entity_name" required value="{value(record, 'entity_name')}" placeholder="TAC Japan K.K."></div>
    <div class="form-field"><label>{h(t(messages, 'field.country'))}</label><input name="country" value="{value(record, 'country')}" placeholder="Japan"></div>
    <div class="form-field"><label>{h(t(messages, 'field.registration_no'))}</label><input name="registration_no" value="{value(record, 'registration_no')}"></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_from'))}</label><input name="effective_from" type="date" value="{value(record, 'effective_from')}"></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_to'))}</label><input name="effective_to" type="date" value="{value(record, 'effective_to')}"></div>
  </div></div></section>
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'field.remarks'))}</h3></div><div class="section-body"><textarea name="remarks">{value(record, 'remarks')}</textarea></div></section>
  <div class="sap-toolbar"><a class="button ghost" href="{h(url_with_lang('/entities', lang))}">{h(t(messages, 'action.cancel'))}</a><button type="submit">{h(t(messages, button_key))}</button></div>
</form>
"""


def departments_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    records = scope_records_to_current_entity(load_departments(), context)
    rows_html = department_table_rows(records, context)
    return f"""
{organization_header_html(messages, 'organization.eyebrow', 'department.title', 'department.notice', [(t(messages, 'organization.departments'), len(records))])}
<section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'department.active_title'))}</h3></div><div class="section-body">
  <div class="actions"><a class="button" href="{h(url_with_lang('/department-new', lang))}">{h(t(messages, 'action.new_department'))}</a><a class="button secondary" href="{h(url_with_lang('/organization', lang))}">{h(t(messages, 'nav.organization'))}</a></div>
  <div class="table-scroll"><table><thead><tr><th>{h(t(messages, 'field.entity'))}</th><th>{h(t(messages, 'field.department_code'))}</th><th>{h(t(messages, 'field.department_name'))}</th><th>{h(t(messages, 'field.department_manager'))}</th><th>{h(t(messages, 'field.effective_period'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead><tbody>{rows_html}</tbody></table></div>
</div></section>
"""


def department_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    if not records:
        return f"<tr><td colspan='6' class='muted'>{h(t(messages, 'department.no_records'))}</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: (str(item.get("entity_code", "")), str(item.get("department_code", "")))):
        department_id = str(record.get("department_id", ""))
        rows.append(f"<tr><td>{value(record, 'entity_code')}<br><span class='muted'>{value(record, 'entity_name')}</span></td><td>{value(record, 'department_code')}</td><td>{value(record, 'department_name')}</td><td>{value(record, 'department_manager')}</td><td>{value(record, 'effective_from')} - {value(record, 'effective_to') or '-'}</td><td><div class='actions'><a class='button secondary' href='{h(url_with_lang('/department-edit', lang, {'id': department_id}))}'>{h(t(messages, 'action.edit'))}</a><form method='post' action='{h(url_with_lang('/department-delete', lang))}'><input type='hidden' name='department_id' value='{h(department_id)}'><button class='danger' type='submit'>{h(t(messages, 'action.soft_delete'))}</button></form></div></td></tr>")
    return "".join(rows)


def department_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    record = record or default_department_record()
    is_edit = mode == "edit"
    title_key = "department.edit_title" if is_edit else "department.new_title"
    action = url_with_lang("/department-edit", lang) if is_edit else url_with_lang("/department-new", lang)
    hidden_id = f'<input type="hidden" name="department_id" value="{value(record, "department_id")}">' if is_edit else ""
    button_key = "action.save_department_update" if is_edit else "action.save_department"
    has_entity = bool(str(record.get('entity_id', '')).strip())
    disabled_attr = "" if has_entity else ' disabled aria-disabled="true"'
    select_entity_first = h(t(messages, 'team.select_entity_first', 'Select an Entity first.'))
    return f"""
{organization_header_html(messages, 'organization.eyebrow', title_key, 'department.form_notice', [(t(messages, 'field.department_code'), record.get('department_code', '-') or '-'), (t(messages, 'field.entity'), record.get('entity_code', '-') or '-')])}
<form method="post" action="{h(action)}">
  {hidden_id}
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'organization.section_assignment'))}</h3></div><div class="section-body"><div class="form-grid">
    <div class="form-field"><label>{h(t(messages, 'field.entity'))}</label><select id="department_entity_id" name="entity_id" required>{entity_select_options(str(record.get('entity_id', '')), include_blank=True, blank_label=t(messages, 'filter.select'), context=context)}</select></div>
    <p class="muted" id="department_entity_hint">{select_entity_first}</p>
    <div class="form-field"><label>{h(t(messages, 'field.department_code'))}</label><input name="department_code" data-requires-entity="1" required value="{value(record, 'department_code')}" placeholder="HR"{disabled_attr}></div>
    <div class="form-field"><label>{h(t(messages, 'field.department_name'))}</label><input name="department_name" data-requires-entity="1" required value="{value(record, 'department_name')}" placeholder="Human Resources"{disabled_attr}></div>
    <div class="form-field"><label>{h(t(messages, 'field.department_manager'))}</label><input name="department_manager" data-requires-entity="1" value="{value(record, 'department_manager')}"{disabled_attr}></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_from'))}</label><input name="effective_from" data-requires-entity="1" type="date" value="{value(record, 'effective_from')}"{disabled_attr}></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_to'))}</label><input name="effective_to" data-requires-entity="1" type="date" value="{value(record, 'effective_to')}"{disabled_attr}></div>
  </div></div></section>
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'field.remarks'))}</h3></div><div class="section-body"><textarea name="remarks" data-requires-entity="1"{disabled_attr}>{value(record, 'remarks')}</textarea></div></section>
  <div class="sap-toolbar"><a class="button ghost" href="{h(url_with_lang('/departments', lang))}">{h(t(messages, 'action.cancel'))}</a><button type="submit">{h(t(messages, button_key))}</button></div>
</form>
<script>
(() => {{
  const entitySelect = document.getElementById('department_entity_id');
  const hint = document.getElementById('department_entity_hint');
  const dependentFields = Array.from(document.querySelectorAll('[data-requires-entity="1"]'));
  if (!entitySelect) return;
  function syncDepartmentInputs() {{
    const enabled = Boolean(entitySelect.value);
    for (const field of dependentFields) {{
      field.disabled = !enabled;
      field.setAttribute('aria-disabled', enabled ? 'false' : 'true');
    }}
    if (hint) hint.style.display = enabled ? 'none' : '';
  }}
  entitySelect.addEventListener('change', syncDepartmentInputs);
  syncDepartmentInputs();
}})();
</script>
"""


def teams_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["entity_id", "department_id", "q"]}


def filter_teams(records: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    results = records
    if filters.get("entity_id"):
        results = [record for record in results if str(record.get("entity_id", "")) == filters["entity_id"]]
    if filters.get("department_id"):
        results = [record for record in results if str(record.get("department_id", "")) == filters["department_id"]]
    q = filters.get("q", "").lower()
    if q:
        results = [record for record in results if q in " ".join(str(record.get(key, "")) for key in ["team_code", "team_name", "team_manager", "department_name", "entity_name"]).lower()]
    return results


def teams_html(query: dict[str, list[str]] | None = None, context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    filters = teams_filters_from_query(query or {})
    current_entity = context_current_entity(context)
    if current_entity:
        filters["entity_id"] = current_entity.get("entity_id", filters.get("entity_id", ""))
    records = filter_teams(scope_records_to_current_entity(load_teams(), context), filters)
    rows_html = team_table_rows(records, context)
    return f"""
{organization_header_html(messages, 'organization.eyebrow', 'team.title', 'team.notice', [(t(messages, 'organization.teams'), len(records)), (t(messages, 'organization.departments'), len(load_departments()))])}
<section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'action.filter'))}</h3></div><div class="section-body">
  <form method="get" action="/teams"><input type="hidden" name="lang" value="{h(lang)}"><div class="form-grid">
    <div class="form-field"><label>{h(t(messages, 'field.entity'))}</label><select name="entity_id">{entity_select_options(filters['entity_id'], include_blank=True, blank_label=t(messages, 'filter.all'), context=context)}</select></div>
    <div class="form-field"><label>{h(t(messages, 'field.department'))}</label><select name="department_id">{department_select_options(filters['department_id'], include_blank=True, blank_label=t(messages, 'filter.all'), entity_id=filters['entity_id'], context=context)}</select></div>
    <div class="form-field"><label>{h(t(messages, 'action.search'))}</label><input name="q" value="{h(filters['q'])}" placeholder="Team code / name"></div>
    <div class="form-field actions"><button type="submit">{h(t(messages, 'action.filter'))}</button><a class="button ghost" href="{h(url_with_lang('/teams', lang))}">{h(t(messages, 'action.clear'))}</a></div>
  </div></form>
</div></section>
<section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'team.active_title'))}</h3></div><div class="section-body">
  <div class="actions"><a class="button" href="{h(url_with_lang('/team-new', lang))}">{h(t(messages, 'action.new_team'))}</a><a class="button secondary" href="{h(url_with_lang('/organization', lang))}">{h(t(messages, 'nav.organization'))}</a></div>
  <div class="table-scroll"><table><thead><tr><th>{h(t(messages, 'field.entity'))}</th><th>{h(t(messages, 'field.department'))}</th><th>{h(t(messages, 'field.team_code'))}</th><th>{h(t(messages, 'field.team_name'))}</th><th>{h(t(messages, 'field.team_manager'))}</th><th>{h(t(messages, 'field.effective_period'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead><tbody>{rows_html}</tbody></table></div>
</div></section>
"""


def team_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    if not records:
        return f"<tr><td colspan='7' class='muted'>{h(t(messages, 'team.no_records'))}</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: (str(item.get("entity_code", "")), str(item.get("department_code", "")), str(item.get("team_code", "")))):
        team_id = str(record.get("team_id", ""))
        rows.append(f"<tr><td>{value(record, 'entity_code')}<br><span class='muted'>{value(record, 'entity_name')}</span></td><td>{value(record, 'department_code')}<br><span class='muted'>{value(record, 'department_name')}</span></td><td>{value(record, 'team_code')}</td><td>{value(record, 'team_name')}</td><td>{value(record, 'team_manager')}</td><td>{value(record, 'effective_from')} - {value(record, 'effective_to') or '-'}</td><td><div class='actions'><a class='button secondary' href='{h(url_with_lang('/team-edit', lang, {'id': team_id}))}'>{h(t(messages, 'action.edit'))}</a><form method='post' action='{h(url_with_lang('/team-delete', lang))}'><input type='hidden' name='team_id' value='{h(team_id)}'><button class='danger' type='submit'>{h(t(messages, 'action.soft_delete'))}</button></form></div></td></tr>")
    return "".join(rows)


def team_form_html(record: dict[str, Any] | None = None, mode: str = "new", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    record = record or default_team_record()
    is_edit = mode == "edit"
    title_key = "team.edit_title" if is_edit else "team.new_title"
    action = url_with_lang("/team-edit", lang) if is_edit else url_with_lang("/team-new", lang)
    hidden_id = f'<input type="hidden" name="team_id" value="{value(record, "team_id")}">' if is_edit else ""
    button_key = "action.save_team_update" if is_edit else "action.save_team"
    return f"""
{organization_header_html(messages, 'organization.eyebrow', title_key, 'team.form_notice', [(t(messages, 'field.team_code'), record.get('team_code', '-') or '-'), (t(messages, 'field.department'), record.get('department_code', '-') or '-')])}
<form method="post" action="{h(action)}">
  {hidden_id}
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'organization.section_assignment'))}</h3></div><div class="section-body"><div class="form-grid">
    <div class="form-field"><label>{h(t(messages, 'field.entity'))}</label><select name="entity_id" required>{entity_select_options(str(record.get('entity_id', '')), include_blank=True, blank_label=t(messages, 'filter.select'), context=context)}</select></div>
    <div class="form-field"><label>{h(t(messages, 'field.department'))}</label><select name="department_id" required>{department_select_options(str(record.get('department_id', '')), include_blank=True, blank_label=t(messages, 'filter.select'), entity_id=str(record.get('entity_id', '')), context=context)}</select></div>
    <div class="form-field"><label>{h(t(messages, 'field.team_code'))}</label><input name="team_code" required value="{value(record, 'team_code')}" placeholder="TEAM-001"></div>
    <div class="form-field"><label>{h(t(messages, 'field.team_name'))}</label><input name="team_name" required value="{value(record, 'team_name')}" placeholder="Payroll Team"></div>
    <div class="form-field"><label>{h(t(messages, 'field.team_manager'))}</label><input name="team_manager" value="{value(record, 'team_manager')}"></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_from'))}</label><input name="effective_from" type="date" value="{value(record, 'effective_from')}"></div>
    <div class="form-field"><label>{h(t(messages, 'field.effective_to'))}</label><input name="effective_to" type="date" value="{value(record, 'effective_to')}"></div>
  </div></div></section>
  <section class="sap-section"><div class="section-header"><h3>{h(t(messages, 'field.remarks'))}</h3></div><div class="section-body"><textarea name="remarks">{value(record, 'remarks')}</textarea></div></section>
  <div class="sap-toolbar"><a class="button ghost" href="{h(url_with_lang('/teams', lang))}">{h(t(messages, 'action.cancel'))}</a><button type="submit">{h(t(messages, button_key))}</button></div>
</form>
"""


def organization_saved_html(record: dict[str, Any], record_type_key: str, message_key: str, list_path: str, new_path: str, context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    summary_fields = [(key, value_text) for key, value_text in [("field.entity", record.get("entity_name")), ("field.department", record.get("department_name")), ("field.team", record.get("team_name")), ("field.status", record.get("record_status", "Active"))] if value_text]
    cards = "".join(f"<div class='card'><h3>{h(t(messages, key))}</h3><p>{h(value_text)}</p></div>" for key, value_text in summary_fields)
    return f"""
<section class="panel">
  <h2>{h(t(messages, record_type_key))}</h2>
  <p class="good">{h(t(messages, message_key))}</p>
  <div class="grid">{cards}</div>
  <div class="actions"><a class="button" href="{h(url_with_lang(list_path, lang))}">{h(t(messages, 'action.open_master'))}</a><a class="button secondary" href="{h(url_with_lang(new_path, lang))}">{h(t(messages, 'action.add_next'))}</a></div>
</section>
"""


def master_data_html(title: str, path: Path) -> str:
    records = load_json_array(path)
    rows = "".join(f"<tr><td>{escape(json.dumps(record, ensure_ascii=False))}</td></tr>" for record in records)
    if not rows:
        rows = "<tr><td class='muted'>No master data saved yet. This MVP keeps the file available for future integration.</td></tr>"
    return f"""
<section class="panel">
  <h2>{escape(title)}</h2>
  <p class="notice">Read-only MVP view for <strong>{escape(str(path.relative_to(ROOT_DIR)))}</strong>.</p>
  <table><thead><tr><th>JSON row</th></tr></thead><tbody>{rows}</tbody></table>
</section>
"""


def load_audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def audit_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["module", "record_id", "action", "user"]}


def filter_audit_logs(records: list[dict[str, Any]], filters: dict[str, str], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filtered = scope_records_to_current_entity(records, context)
    module = filters.get("module", "")
    record_id = filters.get("record_id", "").lower()
    action = filters.get("action", "")
    user = filters.get("user", "").lower()
    if module:
        filtered = [record for record in filtered if str(record.get("module", "")) == module]
    if record_id:
        filtered = [record for record in filtered if record_id in str(record.get("record_id", "")).lower()]
    if action:
        filtered = [record for record in filtered if str(record.get("action", "")) == action]
    if user:
        filtered = [record for record in filtered if user in str(record.get("user", "")).lower()]
    return filtered


def audit_select_options(values: list[str], selected: str, blank_label: str) -> str:
    options = [f"<option value='' {' selected' if not selected else ''}>{escape(blank_label)}</option>"]
    for value_text in values:
        selected_attr = " selected" if value_text == selected else ""
        options.append(f"<option value='{escape(value_text)}'{selected_attr}>{escape(value_text)}</option>")
    return "".join(options)


def audit_logs_html(query: dict[str, list[str]], context: dict[str, Any] | None = None) -> str:
    all_records = scope_records_to_current_entity(load_audit_logs(), context)
    filters = audit_filters_from_query(query)
    records = filter_audit_logs(all_records, filters, context)
    modules = sorted({str(record.get("module", "")) for record in all_records if str(record.get("module", ""))})
    actions = sorted({str(record.get("action", "")) for record in all_records if str(record.get("action", ""))})
    rows_html = audit_log_table_rows(records, context)
    shown_count = min(len(records), 200)
    return f"""
<section class="panel">
  <h2>Audit logs / 監査ログ</h2>
  <p class="notice">Read-only audit viewer for append-only records in <strong>database/audit_logs.json</strong>. Filter by module, record ID, action, or User_admin actor.</p>
  <form method="get" action="/audit-logs">
    <div class="form-grid">
      <div><label>Module / モジュール</label><select name="module">{audit_select_options(modules, filters['module'], 'All modules')}</select></div>
      <div><label>Record ID / レコードID</label><input name="record_id" value="{escape(filters['record_id'])}" placeholder="ts-, emp-, prj-, inv-"></div>
      <div><label>Action / 操作</label><select name="action">{audit_select_options(actions, filters['action'], 'All actions')}</select></div>
      <div><label>User / ユーザー</label><input name="user" value="{escape(filters['user'])}" placeholder="email or username"></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索</button>
      <a class="button secondary" href="/audit-logs">Clear / クリア</a>
    </div>
  </form>
</section>
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>Total audit rows</h3><div class="metric">{len(all_records)}</div></div>
  <div class="card"><h3>Filtered rows</h3><div class="metric">{len(records)}</div><p class="muted">Showing latest {shown_count} rows.</p></div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Audit trail / 監査証跡</h3>
  <table>
    <thead><tr><th>Timestamp</th><th>Module</th><th>Action</th><th>Record ID</th><th>User</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def audit_log_table_rows(records: list[dict[str, Any]], context: dict[str, Any] | None = None) -> str:
    if not records:
        return "<tr><td colspan='7' class='muted'>No audit rows found.</td></tr>"
    rows = []
    sorted_records = sorted(records, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:200]
    for record in sorted_records:
        before_json = escape(json.dumps(record.get("before_value", {}), ensure_ascii=False, indent=2))
        after_json = escape(json.dumps(record.get("after_value", {}), ensure_ascii=False, indent=2))
        rows.append(f"""
        <tr>
          <td>{value(record, 'timestamp')}</td>
          <td>{value(record, 'module')}</td>
          <td><span class="pill">{value(record, 'action')}</span></td>
          <td>{value(record, 'record_id')}</td>
          <td>{value(record, 'user')}</td>
          <td><details><summary>Before</summary><pre>{before_json}</pre></details></td>
          <td><details><summary>After</summary><pre>{after_json}</pre></details></td>
        </tr>
        """)
    return "".join(rows)


def status_message_html(message: str, context: dict[str, Any] | None = None) -> str:
    return f"<section class='panel'><p class='good'>{h(message)}</p></section>"


def error_message_html(message: str, context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    return f"<section class='panel'><h2>{h(t(messages, 'error.input_title'))}</h2><p class='warn'>{h(message)}</p></section>"


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

def write_json_array(path: Path, records: list) -> None:
    if _PG_AVAILABLE:
        try:
            _db.save_table(_db.path_to_table(path), records)
            return
        except Exception:
            pass
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def audit_entity_from_values(before_value: dict[str, Any] | None, after_value: dict[str, Any] | None, context: dict[str, Any] | None = None) -> dict[str, str]:
    entity = context_current_entity(context)
    if entity:
        return entity
    for source in [after_value or {}, before_value or {}]:
        candidate = {
            "entity_id": str(source.get("entity_id", "")).strip(),
            "entity_code": str(source.get("entity_code", "")).strip(),
            "entity_name": str(source.get("entity_name", "")).strip(),
        }
        if candidate.get("entity_id") or candidate.get("entity_code"):
            return {key: value for key, value in candidate.items() if value}
    return {}


def append_audit_log(module: str, record_id: str, action: str, before_value: dict[str, Any] | None, after_value: dict[str, Any] | None, user: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> None:
    now = datetime.now(timezone.utc)
    records = load_json_array(AUDIT_LOGS_PATH)
    entity = audit_entity_from_values(before_value, after_value, context)
    row = {
        "audit_id": f"audit-{now.strftime('%Y%m%d%H%M%S%f')}",
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": user,
        "timestamp": now.isoformat(),
        "before_value": before_value or {},
        "after_value": after_value or {},
    }
    row.update(entity)
    records.append(row)
    write_json_array(AUDIT_LOGS_PATH, records)


NO_OP_COMPARE_IGNORE_FIELDS = {
    "updated_at",
    "updated_by",
    "last_modified_at",
    "last_modified_by",
    "last_modified_by_user_id",
    "last_modified_by_name",
    "last_modified_entry_mode",
}


def records_business_equal(before: dict[str, Any] | None, after: dict[str, Any] | None, ignore_fields: set[str] | None = None) -> bool:
    before = before or {}
    after = after or {}
    ignored = ignore_fields or NO_OP_COMPARE_IGNORE_FIELDS
    keys = (set(before.keys()) | set(after.keys())) - ignored
    return all(before.get(key, "") == after.get(key, "") for key in keys)


def normalize_work_month(work_month: str) -> str:
    work_month = work_month.strip()
    if len(work_month) != 7 or work_month[4] != "-" or not work_month[:4].isdigit() or not work_month[5:].isdigit():
        raise ValueError("Work Month must use YYYY-MM format.")
    month = int(work_month[5:])
    if not 1 <= month <= 12:
        raise ValueError("Work Month month must be between 01 and 12.")
    return work_month


def work_month_from_date(work_date: str) -> str:
    try:
        parsed = datetime.strptime(work_date.strip(), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Work Date must use YYYY-MM-DD format before checking month lock.") from exc
    return f"{parsed.year:04d}-{parsed.month:02d}"


def load_month_lock_records() -> list[dict[str, Any]]:
    return load_json_array(MONTH_LOCKS_PATH)


def save_month_lock_records(records: list[dict[str, Any]]) -> None:
    write_json_array(MONTH_LOCKS_PATH, records)


def load_timesheet_periods() -> list[dict[str, Any]]:
    return load_month_lock_records()


def save_timesheet_periods(records: list[dict[str, Any]]) -> None:
    save_month_lock_records(records)


def period_id_for_month(work_month: str, context: dict[str, Any] | None = None) -> str:
    normalized = normalize_work_month(work_month)
    entity = context_current_entity(context)
    entity_key = str(entity.get("entity_id") or entity.get("entity_code") or "global").strip().replace(" ", "-")
    return f"period-{entity_key}-{normalized.replace('-', '')}"


def default_period_status(work_month: str) -> str:
    normalized = normalize_work_month(work_month)
    if normalized.startswith("2026-") and 1 <= int(normalized[5:]) <= 4:
        return "Closed"
    return "Open"


def period_status(record: dict[str, Any]) -> str:
    status = str(record.get("status", "") or "").strip().title()
    if status in {"Open", "Closed"}:
        return status
    return "Closed" if str(record.get("lock_status", "")).strip() == "Locked" else "Open"


def build_default_period_record(work_month: str, actor: str = "system", context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_work_month(work_month)
    status = default_period_status(normalized)
    now = datetime.now(timezone.utc).isoformat()
    is_closed = status == "Closed"
    record = {
        "period_id": period_id_for_month(normalized, context),
        "lock_id": period_id_for_month(normalized, context),
        "work_month": normalized,
        "period_year": int(normalized[:4]),
        "period_month": int(normalized[5:]),
        "status": status,
        "lock_status": "Locked" if is_closed else "Open",
        "opened_at": "" if is_closed else now,
        "opened_by": "" if is_closed else actor,
        "closed_at": now if is_closed else "",
        "closed_by": actor if is_closed else "",
        "locked_at": now if is_closed else "",
        "locked_by": actor if is_closed else "",
        "notes": "",
        "created_at": now,
        "updated_at": now,
    }
    return apply_current_entity_snapshot(record, context)


def normalize_period_record(record: dict[str, Any], work_month: str, actor: str = "system", context: dict[str, Any] | None = None) -> tuple[dict[str, Any], bool]:
    normalized = normalize_work_month(work_month)
    updated = dict(record)
    before = dict(updated)
    status = period_status(updated)
    now = datetime.now(timezone.utc).isoformat()
    if context_current_entity(context):
        updated = apply_current_entity_snapshot(updated, context)
    updated.setdefault("period_id", period_id_for_month(normalized, context))
    updated.setdefault("lock_id", updated.get("period_id", period_id_for_month(normalized, context)))
    updated["work_month"] = normalized
    updated.setdefault("period_year", int(normalized[:4]))
    updated.setdefault("period_month", int(normalized[5:]))
    updated["status"] = status
    updated["lock_status"] = "Locked" if status == "Closed" else "Open"
    updated.setdefault("opened_at", "")
    updated.setdefault("opened_by", "")
    updated.setdefault("closed_at", updated.get("locked_at", "") if status == "Closed" else "")
    updated.setdefault("closed_by", updated.get("locked_by", "") if status == "Closed" else "")
    updated.setdefault("locked_at", updated.get("closed_at", "") if status == "Closed" else "")
    updated.setdefault("locked_by", updated.get("closed_by", "") if status == "Closed" else "")
    updated.setdefault("notes", "")
    updated.setdefault("created_at", now)
    updated.setdefault("updated_at", now)
    if updated != before:
        updated["updated_at"] = now
    return updated, updated != before


def years_requiring_period_sync() -> set[int]:
    years = {2026, datetime.now(timezone.utc).year}
    for record in load_timesheet_entries(include_deleted=True):
        work_date = str(record.get("work_date", ""))
        if len(work_date) >= 4 and work_date[:4].isdigit():
            years.add(int(work_date[:4]))
    for record in load_invoice_drafts(include_voided=True):
        work_month = str(record.get("work_month", ""))
        if len(work_month) >= 4 and work_month[:4].isdigit():
            years.add(int(work_month[:4]))
    return years


def sync_timesheet_periods_for_year(year: int, actor: str = "system") -> list[dict[str, Any]]:
    records = load_timesheet_periods()
    by_month: dict[str, dict[str, Any]] = {}
    changed = False
    for record in records:
        raw_month = str(record.get("work_month", ""))
        if not raw_month:
            continue
        try:
            normalized_month = normalize_work_month(raw_month)
        except ValueError:
            continue
        normalized_record, record_changed = normalize_period_record(record, normalized_month, actor=actor)
        if record_changed:
            append_audit_log("timesheet.accounting_period", str(normalized_record.get("period_id", "")), "sync_update", dict(record), dict(normalized_record), user=actor)
            changed = True
        if normalized_month not in by_month:
            by_month[normalized_month] = normalized_record
    for month in range(1, 13):
        work_month = f"{year:04d}-{month:02d}"
        if work_month not in by_month:
            period = build_default_period_record(work_month, actor=actor)
            by_month[work_month] = period
            append_audit_log("timesheet.accounting_period", str(period.get("period_id", "")), "sync_create", None, dict(period), user=actor)
            changed = True
    merged = sorted(by_month.values(), key=lambda item: str(item.get("work_month", "")))
    if changed or len(merged) != len(records):
        save_timesheet_periods(merged)
    return merged


def sync_relevant_timesheet_periods(actor: str = "system") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for year in sorted(years_requiring_period_sync()):
        records = sync_timesheet_periods_for_year(year, actor=actor)
    return records or load_timesheet_periods()


def find_timesheet_period(work_month: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    normalized = normalize_work_month(work_month)
    for record in scope_records_to_current_entity(load_timesheet_periods(), context):
        if record.get("work_month") == normalized:
            normalized_record, _changed = normalize_period_record(record, normalized, context=context)
            return normalized_record
    return None


def is_period_closed(work_month: str, context: dict[str, Any] | None = None) -> bool:
    period = find_timesheet_period(work_month, context)
    return bool(period and period_status(period) == "Closed")


def find_month_lock(work_month: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    period = find_timesheet_period(work_month, context)
    if period and period_status(period) == "Closed":
        return period
    return None


def is_month_locked(work_month: str, context: dict[str, Any] | None = None) -> bool:
    return is_period_closed(work_month, context)


def record_month_is_locked(record: dict[str, Any], context: dict[str, Any] | None = None) -> bool:
    try:
        return is_month_locked(work_month_from_date(str(record.get("work_date", ""))), context)
    except ValueError:
        return False


def active_rows_for_month(work_month: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = normalize_work_month(work_month)
    return [record for record in scope_records_to_current_entity(load_timesheet_entries(), context) if str(record.get("work_date", "")).startswith(normalized)]


def active_invoice_drafts_for_month(work_month: str, context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    normalized = normalize_work_month(work_month)
    return [record for record in load_invoice_drafts_for_context(context) if str(record.get("work_month", "")) == normalized]


def period_close_blocking_reason(work_month: str, context: dict[str, Any] | None = None) -> str:
    normalized = normalize_work_month(work_month)
    period = find_timesheet_period(normalized, context)
    if period and period_status(period) == "Closed":
        return f"Period {normalized} is already closed."
    month_rows = active_rows_for_month(normalized, context)
    not_approved = [record for record in month_rows if approval_status(record) != "Approved"]
    if not_approved:
        return f"{len(not_approved)} active row(s) are not Approved yet."
    return ""


def period_open_blocking_reason(work_month: str, context: dict[str, Any] | None = None) -> str:
    normalized = normalize_work_month(work_month)
    period = find_timesheet_period(normalized, context)
    if period and period_status(period) == "Open":
        return f"Period {normalized} is already open."
    invoice_count = len(active_invoice_drafts_for_month(normalized, context))
    if invoice_count:
        return f"{invoice_count} active invoice draft(s) exist. Void them before opening this period."
    return ""


def close_timesheet_period(work_month: str, notes: str = "", actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_work_month(work_month)
    sync_relevant_timesheet_periods(actor=actor)
    reason = period_close_blocking_reason(normalized, context)
    if reason:
        raise ValueError(reason)
    records = load_timesheet_periods()
    now = datetime.now(timezone.utc).isoformat()
    updated_records = []
    saved_period: dict[str, Any] | None = None
    before_value: dict[str, Any] | None = None
    for record in records:
        if record.get("work_month") == normalized and record_entity_matches(record, context):
            period, _changed = normalize_period_record(record, normalized, actor=actor, context=context)
            before_value = dict(period)
            period["status"] = "Closed"
            period["lock_status"] = "Locked"
            period["closed_at"] = now
            period["closed_by"] = actor
            period["locked_at"] = now
            period["locked_by"] = actor
            period["notes"] = notes.strip()
            period["updated_at"] = now
            saved_period = period
            updated_records.append(period)
        else:
            updated_records.append(record)
    if saved_period is None:
        saved_period = build_default_period_record(normalized, actor=actor, context=context)
        saved_period["status"] = "Closed"
        saved_period["lock_status"] = "Locked"
        saved_period["closed_at"] = now
        saved_period["closed_by"] = actor
        saved_period["locked_at"] = now
        saved_period["locked_by"] = actor
        saved_period["notes"] = notes.strip()
        saved_period["updated_at"] = now
        updated_records.append(saved_period)
    save_timesheet_periods(sorted(updated_records, key=lambda item: str(item.get("work_month", ""))))
    append_audit_log("timesheet.accounting_period", str(saved_period.get("period_id", "")), "close", before_value, dict(saved_period), user=actor, context=context)
    return saved_period


def open_timesheet_period(work_month: str, notes: str = "", actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    normalized = normalize_work_month(work_month)
    sync_relevant_timesheet_periods(actor=actor)
    reason = period_open_blocking_reason(normalized, context)
    if reason:
        raise ValueError(reason)
    records = load_timesheet_periods()
    now = datetime.now(timezone.utc).isoformat()
    updated_records = []
    saved_period: dict[str, Any] | None = None
    before_value: dict[str, Any] | None = None
    for record in records:
        if record.get("work_month") == normalized and record_entity_matches(record, context):
            period, _changed = normalize_period_record(record, normalized, actor=actor, context=context)
            before_value = dict(period)
            period["status"] = "Open"
            period["lock_status"] = "Open"
            period["opened_at"] = now
            period["opened_by"] = actor
            period["notes"] = notes.strip()
            period["updated_at"] = now
            saved_period = period
            updated_records.append(period)
        else:
            updated_records.append(record)
    if saved_period is None:
        saved_period = build_default_period_record(normalized, actor=actor, context=context)
        saved_period["status"] = "Open"
        saved_period["lock_status"] = "Open"
        saved_period["opened_at"] = now
        saved_period["opened_by"] = actor
        saved_period["notes"] = notes.strip()
        saved_period["updated_at"] = now
        updated_records.append(saved_period)
    save_timesheet_periods(sorted(updated_records, key=lambda item: str(item.get("work_month", ""))))
    append_audit_log("timesheet.accounting_period", str(saved_period.get("period_id", "")), "open", before_value, dict(saved_period), user=actor, context=context)
    return saved_period


def create_month_lock(work_month: str, notes: str = "", actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return close_timesheet_period(work_month, notes=notes, actor=actor, context=context)


def load_local_employees(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(EMPLOYEES_PATH)
    if include_deleted:
        return records
    return [record for record in records if record.get("record_status", "Active") != "Deleted"]


def employee_source_status(context: dict[str, Any] | None) -> dict[str, Any]:
    if context is None:
        return {"source": "local", "message_key": "message.employeeadmin_unavailable", "count": len(load_local_employees())}
    status = context.get("employee_source_status")
    if isinstance(status, dict):
        return status
    return {"source": "unknown", "message_key": "message.employeeadmin_unavailable", "count": 0}


def set_employee_source_status(context: dict[str, Any] | None, source: str, message_key: str, count: int, detail: str = "") -> None:
    if context is not None:
        context["employee_source_status"] = {"source": source, "message_key": message_key, "count": count, "detail": detail}


def normalize_employeeadmin_employee(record: dict[str, Any]) -> dict[str, Any]:
    department_name = str(record.get("department_name") or record.get("department", "")).strip()
    return {
        "employee_id": str(record.get("employee_id", "")),
        "employee_master_id": str(record.get("employee_id", "")),
        "employee_no": str(record.get("employee_number", "")).strip(),
        "employee_name": str(record.get("display_name", "")).strip(),
        "department": str(record.get("department", "")).strip() or department_name,
        "email": str(record.get("email", "")).strip(),
        "employment_type": str(record.get("employment_type", "")).strip(),
        "employment_status": str(record.get("status", "")).strip(),
        "entity_id": str(record.get("entity_id", "")).strip(),
        "entity_code": str(record.get("entity_code", "")).strip(),
        "entity_name": str(record.get("entity_name", "")).strip(),
        "department_id": str(record.get("department_id", "")).strip(),
        "department_code": str(record.get("department_code", "")).strip(),
        "department_name": department_name,
        "team_id": str(record.get("team_id", "")).strip(),
        "team_code": str(record.get("team_code", "")).strip(),
        "team_name": str(record.get("team_name", "")).strip(),
        "default_scheduled_work_minutes": DEFAULT_SCHEDULED_WORK_MINUTES,
        "record_status": "Active",
        "source": "employeeadmin",
    }


def fetch_employeeadmin_employees(session_id: str) -> list[dict[str, Any]]:
    if not session_id:
        raise ValueError("User_admin session is required for EmployeeAdmin employee lookup.")
    request = Request(
        f"{EMPLOYEEADMIN_INTERNAL_BASE_URL}/api/timesheet/employees",
        headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"},
        method="GET",
    )
    with urlopen(request, timeout=3) as response:
        data = json.loads(response.read().decode("utf-8"))
    employees = data.get("employees", []) if isinstance(data, dict) else []
    if not isinstance(employees, list):
        return []
    return [normalize_employeeadmin_employee(item) for item in employees if isinstance(item, dict)]


def normalize_employeeadmin_dispatch_assignment(payload: dict[str, Any]) -> dict[str, Any] | None:
    assignment = payload.get("assignment", {}) if isinstance(payload, dict) else {}
    if not isinstance(assignment, dict) or not assignment.get("matched"):
        return None
    supervisor = assignment.get("supervisor", {})
    if not isinstance(supervisor, dict):
        supervisor = {}
    project_name = str(assignment.get("project_name", "") or "").strip()
    if not project_name:
        project_name = str(assignment.get("work_description", "") or assignment.get("assignment_location", "") or "").strip()
    return {
        "dispatch_assignment_matched": True,
        "dispatch_assignment_source": str(assignment.get("source", "") or "").strip(),
        "dispatch_assignment_history_id": str(assignment.get("history_id", "") or "").strip(),
        "customer_name": str(assignment.get("client_name", "") or "").strip(),
        "project_name": project_name,
        "project_code": "",
        "dispatch_type": "Dispatch",
        "work_location": "Customer Site",
        "country": "Japan",
        "dispatch_contract_type": str(assignment.get("contract_type", "") or "").strip(),
        "dispatch_assignment_location": str(assignment.get("assignment_location", "") or "").strip(),
        "dispatch_work_description": str(assignment.get("work_description", "") or "").strip(),
        "dispatch_start_date": str(assignment.get("dispatch_start_date", "") or "").strip(),
        "dispatch_end_date": str(assignment.get("dispatch_end_date", "") or "").strip(),
        "dispatch_supervisor_name": str(supervisor.get("name", "") or "").strip(),
        "dispatch_supervisor_title": str(supervisor.get("title", "") or "").strip(),
        "dispatch_supervisor_phone": str(supervisor.get("phone", "") or "").strip(),
        "dispatch_supervisor_email": str(supervisor.get("email", "") or "").strip(),
    }


def fetch_employeeadmin_dispatch_assignment(session_id: str, employee_no: str, work_date: str) -> dict[str, Any] | None:
    employee_no = employee_no.strip()
    work_date = work_date.strip()
    if not session_id or not employee_no or not work_date:
        return None
    query = urlencode({"employee_no": employee_no, "work_date": work_date})
    request = Request(
        f"{EMPLOYEEADMIN_INTERNAL_BASE_URL}/api/timesheet/dispatch-assignment?{query}",
        headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    return normalize_employeeadmin_dispatch_assignment(data)


def load_timesheet_employees(context: dict[str, Any] | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
    if include_deleted:
        return load_local_employees(include_deleted=True)
    session_id = str(context.get("session_id", "")) if context else ""
    if session_id:
        try:
            remote_employees = fetch_employeeadmin_employees(session_id)
            if remote_employees:
                scoped_employees = scope_records_to_current_entity(remote_employees, context)
                set_employee_source_status(context, "employeeadmin", "message.employeeadmin_active", len(scoped_employees))
                return scoped_employees
            set_employee_source_status(context, "local", "message.employeeadmin_empty", 0)
        except (OSError, URLError, ValueError, json.JSONDecodeError) as exc:
            set_employee_source_status(context, "local", "message.employeeadmin_unavailable", 0, str(exc))
    local_employees = scope_records_to_current_entity(load_local_employees(), context)
    if context is not None and not isinstance(context.get("employee_source_status"), dict):
        set_employee_source_status(context, "local", "message.employeeadmin_unavailable", len(local_employees))
    return local_employees


def load_employees(include_deleted: bool = False) -> list[dict[str, Any]]:
    return load_local_employees(include_deleted=include_deleted)


def find_employee(employee_id: str) -> dict[str, Any] | None:
    employee_id = employee_id.strip()
    if not employee_id:
        return None
    for record in load_employees(include_deleted=True):
        if record.get("employee_id") == employee_id:
            return record
    return None


def find_active_employee_by_no(employee_no: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    employee_no = employee_no.strip().lower()
    if not employee_no:
        return None
    for record in load_timesheet_employees(context):
        if str(record.get("employee_no", "")).strip().lower() == employee_no:
            return record
    return None


def employee_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    return {
        "employee_no": form.get("employee_no", "").strip(),
        "employee_name": form.get("employee_name", "").strip(),
        "department": form.get("department", "").strip(),
        "email": form.get("email", "").strip(),
        "default_scheduled_work_minutes": parse_non_negative_int(form.get("default_scheduled_work_minutes", "480"), "Default Scheduled Work Minutes", default=480),
    }


def employee_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = employee_fields_from_form(form)
    record["employee_id"] = existing.get("employee_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def validate_employee_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_employee_id: str = "") -> None:
    required_fields = [
        ("employee_no", "Employee No. / 社員No."),
        ("employee_name", "Employee Name / 氏名"),
    ]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    email = str(record.get("email", "")).strip()
    if email and "@" not in email:
        raise ValueError("Email must contain @ when provided.")
    parse_non_negative_int(record.get("default_scheduled_work_minutes", 480), "Default Scheduled Work Minutes")
    employee_no = str(record.get("employee_no", "")).strip().lower()
    for existing in existing_records:
        if exclude_employee_id and existing.get("employee_id") == exclude_employee_id:
            continue
        if str(existing.get("employee_no", "")).strip().lower() == employee_no:
            raise ValueError(f"Employee No. already exists: {record.get('employee_no', '')}")


def save_employee(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_employees(include_deleted=True)
    active = [item for item in records if item.get("record_status", "Active") != "Deleted"]
    record = dict(record)
    validate_employee_record(record, active)
    now = datetime.now(timezone.utc)
    record["employee_id"] = f"emp-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(EMPLOYEES_PATH, records)
    append_audit_log("master_data.employee", str(record.get("employee_id", "")), "create", None, dict(record), user=actor)
    return record


def update_employee(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_employees(include_deleted=True)
    employee_id = str(record.get("employee_id", "")).strip()
    if not employee_id:
        raise ValueError("Employee record ID is required.")
    active = [item for item in records if item.get("record_status", "Active") != "Deleted"]
    validate_employee_record(record, active, exclude_employee_id=employee_id)
    updated_records = []
    updated = False
    before_value: dict[str, Any] | None = None
    for item in records:
        if item.get("employee_id") == employee_id:
            before_value = dict(item)
            updated_records.append(record)
            updated = True
        else:
            updated_records.append(item)
    if not updated:
        raise ValueError("Employee record was not found.")
    write_json_array(EMPLOYEES_PATH, updated_records)
    append_audit_log("master_data.employee", employee_id, "update", before_value, dict(record), user=actor)
    return record


def soft_delete_employee(employee_id: str, actor: str = LOCAL_ACTOR) -> bool:
    employee_id = employee_id.strip()
    records = load_employees(include_deleted=True)
    updated = False
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("employee_id") == employee_id:
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            updated = True
            break
    if updated:
        write_json_array(EMPLOYEES_PATH, records)
        append_audit_log("master_data.employee", employee_id, "soft_delete", before_value, after_value, user=actor)
    return updated


def default_employee_record() -> dict[str, Any]:
    return {
        "employee_no": "",
        "employee_name": "",
        "department": "",
        "email": "",
        "default_scheduled_work_minutes": 480,
        "record_status": "Active",
    }


def load_projects(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(PROJECTS_PATH)
    if include_deleted:
        return records
    return [record for record in records if record.get("record_status", "Active") != "Deleted"]


def load_projects_for_context(context: dict[str, Any] | None = None, include_deleted: bool = False) -> list[dict[str, Any]]:
    return scope_records_to_current_entity(load_projects(include_deleted=include_deleted), context)


def find_project(project_id: str) -> dict[str, Any] | None:
    project_id = project_id.strip()
    if not project_id:
        return None
    for record in load_projects(include_deleted=True):
        if record.get("project_id") == project_id:
            return record
    return None


def find_active_project_by_code(project_code: str, context: dict[str, Any] | None = None) -> dict[str, Any] | None:
    project_code = project_code.strip().lower()
    if not project_code:
        return None
    for record in load_projects_for_context(context):
        if str(record.get("project_code", "")).strip().lower() == project_code:
            return record
    return None


def project_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    return {
        "project_code": form.get("project_code", "").strip(),
        "project_name": form.get("project_name", "").strip(),
        "customer_name": form.get("customer_name", "").strip(),
        "customer_code": form.get("customer_code", "").strip(),
        "dispatch_type": form.get("dispatch_type", "Client Site").strip() or "Client Site",
        "work_location": form.get("work_location", "Customer Site").strip() or "Customer Site",
        "country": form.get("country", "Japan").strip() or "Japan",
        "prefecture": form.get("prefecture", "").strip(),
        "client_approval_required": parse_bool(form.get("client_approval_required", "true")),
        "billing_enabled": parse_bool(form.get("billing_enabled", "true")),
        "billing_rate_per_hour_yen": parse_non_negative_int(form.get("billing_rate_per_hour_yen", "0"), "Billing Rate per Hour JPY", default=0),
        "billing_note": form.get("billing_note", "").strip(),
    }


def project_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = project_fields_from_form(form)
    record["project_id"] = existing.get("project_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def validate_project_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_project_id: str = "") -> None:
    required_fields = [
        ("project_code", "Project Code / 案件コード"),
        ("project_name", "Project Name / 案件名"),
        ("customer_name", "Customer Name / 顧客名"),
    ]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    if record.get("dispatch_type") not in {key for key, _label in DISPATCH_TYPES}:
        raise ValueError("Dispatch Type is invalid.")
    if record.get("work_location") not in {key for key, _label in WORK_LOCATIONS}:
        raise ValueError("Work Location is invalid.")
    project_code = str(record.get("project_code", "")).strip().lower()
    entity_id = str(record.get("entity_id", "")).strip()
    entity_code = str(record.get("entity_code", "")).strip()
    for existing in existing_records:
        if exclude_project_id and existing.get("project_id") == exclude_project_id:
            continue
        same_entity = (entity_id and str(existing.get("entity_id", "")).strip() == entity_id) or (not entity_id and entity_code and str(existing.get("entity_code", "")).strip() == entity_code)
        if same_entity and str(existing.get("project_code", "")).strip().lower() == project_code:
            raise ValueError(f"Project Code already exists in the current Entity: {record.get('project_code', '')}")


def save_project(record: dict[str, Any], actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_projects(include_deleted=True)
    active = [item for item in records if item.get("record_status", "Active") != "Deleted"]
    record = apply_current_entity_snapshot(dict(record), context)
    validate_project_record(record, active)
    now = datetime.now(timezone.utc)
    record["project_id"] = f"prj-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(PROJECTS_PATH, records)
    append_audit_log("master_data.project", str(record.get("project_id", "")), "create", None, dict(record), user=actor, context=context)
    return record


def update_project(record: dict[str, Any], actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_projects(include_deleted=True)
    record = apply_current_entity_snapshot(dict(record), context)
    project_id = str(record.get("project_id", "")).strip()
    if not project_id:
        raise ValueError("Project record ID is required.")
    active = [item for item in records if item.get("record_status", "Active") != "Deleted"]
    validate_project_record(record, active, exclude_project_id=project_id)
    updated_records = []
    updated = False
    before_value: dict[str, Any] | None = None
    for item in records:
        if item.get("project_id") == project_id:
            before_value = dict(item)
            updated_records.append(record)
            updated = True
        else:
            updated_records.append(item)
    if not updated:
        raise ValueError("Project record was not found.")
    if records_business_equal(before_value, record):
        unchanged = dict(before_value or record)
        unchanged["_no_changes"] = True
        return unchanged
    write_json_array(PROJECTS_PATH, updated_records)
    append_audit_log("master_data.project", project_id, "update", before_value, dict(record), user=actor, context=context)
    return record


def soft_delete_project(project_id: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> bool:
    project_id = project_id.strip()
    records = load_projects(include_deleted=True)
    updated = False
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("project_id") == project_id:
            require_record_entity_access(record, context, "Project")
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            updated = True
            break
    if updated:
        write_json_array(PROJECTS_PATH, records)
        append_audit_log("master_data.project", project_id, "soft_delete", before_value, after_value, user=actor, context=context)
    return updated


def default_project_record() -> dict[str, Any]:
    return {
        "project_code": "",
        "project_name": "",
        "customer_name": "",
        "customer_code": "",
        "entity_id": "",
        "entity_code": "",
        "entity_name": "",
        "dispatch_type": "Client Site",
        "work_location": "Customer Site",
        "country": "Japan",
        "prefecture": "Tokyo",
        "client_approval_required": True,
        "billing_enabled": True,
        "billing_rate_per_hour_yen": 0,
        "billing_note": "",
        "record_status": "Active",
    }


# Organization master data: entity -> department -> team.
def active_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if record.get("record_status", "Active") != "Deleted"]


def load_entities(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(ENTITIES_PATH)
    return records if include_deleted else active_records(records)


def load_departments(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(DEPARTMENTS_PATH)
    return records if include_deleted else active_records(records)


def load_teams(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(TEAMS_PATH)
    return records if include_deleted else active_records(records)


def find_entity(entity_id: str) -> dict[str, Any] | None:
    entity_id = entity_id.strip()
    if not entity_id:
        return None
    for record in load_entities(include_deleted=True):
        if record.get("entity_id") == entity_id:
            return record
    return None


def find_active_entity(entity_id: str) -> dict[str, Any] | None:
    record = find_entity(entity_id)
    if record and record.get("record_status", "Active") != "Deleted":
        return record
    return None


def find_department(department_id: str) -> dict[str, Any] | None:
    department_id = department_id.strip()
    if not department_id:
        return None
    for record in load_departments(include_deleted=True):
        if record.get("department_id") == department_id:
            return record
    return None


def find_active_department(department_id: str) -> dict[str, Any] | None:
    record = find_department(department_id)
    if record and record.get("record_status", "Active") != "Deleted":
        return record
    return None


def find_team(team_id: str) -> dict[str, Any] | None:
    team_id = team_id.strip()
    if not team_id:
        return None
    for record in load_teams(include_deleted=True):
        if record.get("team_id") == team_id:
            return record
    return None


def find_active_team(team_id: str) -> dict[str, Any] | None:
    record = find_team(team_id)
    if record and record.get("record_status", "Active") != "Deleted":
        return record
    return None


def entity_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    return {
        "entity_code": form.get("entity_code", "").strip(),
        "entity_name": form.get("entity_name", "").strip(),
        "country": form.get("country", "Japan").strip() or "Japan",
        "registration_no": form.get("registration_no", "").strip(),
        "effective_from": form.get("effective_from", "").strip(),
        "effective_to": form.get("effective_to", "").strip(),
        "remarks": form.get("remarks", "").strip(),
    }


def entity_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = entity_fields_from_form(form)
    record["entity_id"] = existing.get("entity_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def validate_entity_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_entity_id: str = "") -> None:
    required_fields = [("entity_code", "Entity Code / 法人コード"), ("entity_name", "Entity Name / 法人名")]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    entity_code = str(record.get("entity_code", "")).strip().lower()
    for existing in existing_records:
        if exclude_entity_id and existing.get("entity_id") == exclude_entity_id:
            continue
        if str(existing.get("entity_code", "")).strip().lower() == entity_code:
            raise ValueError(f"Entity Code already exists: {record.get('entity_code', '')}")


def save_entity(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_entities(include_deleted=True)
    record = dict(record)
    validate_entity_record(record, active_records(records))
    now = datetime.now(timezone.utc)
    record["entity_id"] = f"ent-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(ENTITIES_PATH, records)
    append_audit_log("master_data.entity", str(record.get("entity_id", "")), "create", None, dict(record), user=actor)
    return record


def update_entity(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_entities(include_deleted=True)
    entity_id = str(record.get("entity_id", "")).strip()
    if not entity_id:
        raise ValueError("Entity record ID is required.")
    validate_entity_record(record, active_records(records), exclude_entity_id=entity_id)
    updated_records = []
    before_value: dict[str, Any] | None = None
    for item in records:
        if item.get("entity_id") == entity_id:
            before_value = dict(item)
            updated_records.append(record)
        else:
            updated_records.append(item)
    if before_value is None:
        raise ValueError("Entity record was not found.")
    write_json_array(ENTITIES_PATH, updated_records)
    append_audit_log("master_data.entity", entity_id, "update", before_value, dict(record), user=actor)
    return record


def soft_delete_entity(entity_id: str, actor: str = LOCAL_ACTOR) -> bool:
    entity_id = entity_id.strip()
    if any(record.get("entity_id") == entity_id for record in load_departments()):
        raise ValueError("Entity cannot be deleted while active departments reference it.")
    records = load_entities(include_deleted=True)
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("entity_id") == entity_id:
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            break
    if before_value is None:
        return False
    write_json_array(ENTITIES_PATH, records)
    append_audit_log("master_data.entity", entity_id, "soft_delete", before_value, after_value, user=actor)
    return True


def default_entity_record() -> dict[str, Any]:
    return {"entity_code": "", "entity_name": "", "country": "Japan", "registration_no": "", "effective_from": "", "effective_to": "", "remarks": "", "record_status": "Active"}


def department_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    record = {
        "entity_id": form.get("entity_id", "").strip(),
        "department_code": form.get("department_code", "").strip(),
        "department_name": form.get("department_name", "").strip(),
        "department_manager": form.get("department_manager", "").strip(),
        "effective_from": form.get("effective_from", "").strip(),
        "effective_to": form.get("effective_to", "").strip(),
        "remarks": form.get("remarks", "").strip(),
    }
    return apply_entity_snapshot(record)


def apply_entity_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    entity = find_active_entity(str(record.get("entity_id", "")))
    if entity:
        record["entity_code"] = entity.get("entity_code", "")
        record["entity_name"] = entity.get("entity_name", "")
    else:
        record["entity_code"] = ""
        record["entity_name"] = ""
    return record


def department_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = department_fields_from_form(form)
    record["department_id"] = existing.get("department_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def validate_department_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_department_id: str = "") -> None:
    required_fields = [("entity_id", "Entity / 法人"), ("department_code", "Department Code / 部門コード"), ("department_name", "Department Name / 部門名")]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    if not find_active_entity(str(record.get("entity_id", ""))):
        raise ValueError("Entity must exist and be active.")
    entity_id = str(record.get("entity_id", "")).strip()
    department_code = str(record.get("department_code", "")).strip().lower()
    for existing in existing_records:
        if exclude_department_id and existing.get("department_id") == exclude_department_id:
            continue
        if str(existing.get("entity_id", "")).strip() == entity_id and str(existing.get("department_code", "")).strip().lower() == department_code:
            raise ValueError(f"Department Code already exists under this entity: {record.get('department_code', '')}")


def save_department(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_departments(include_deleted=True)
    record = dict(record)
    validate_department_record(record, active_records(records))
    now = datetime.now(timezone.utc)
    record["department_id"] = f"dept-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(DEPARTMENTS_PATH, records)
    append_audit_log("master_data.department", str(record.get("department_id", "")), "create", None, dict(record), user=actor)
    return record


def update_department(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_departments(include_deleted=True)
    department_id = str(record.get("department_id", "")).strip()
    if not department_id:
        raise ValueError("Department record ID is required.")
    validate_department_record(record, active_records(records), exclude_department_id=department_id)
    updated_records = []
    before_value: dict[str, Any] | None = None
    for item in records:
        if item.get("department_id") == department_id:
            before_value = dict(item)
            updated_records.append(record)
        else:
            updated_records.append(item)
    if before_value is None:
        raise ValueError("Department record was not found.")
    write_json_array(DEPARTMENTS_PATH, updated_records)
    append_audit_log("master_data.department", department_id, "update", before_value, dict(record), user=actor)
    return record


def soft_delete_department(department_id: str, actor: str = LOCAL_ACTOR) -> bool:
    department_id = department_id.strip()
    if any(record.get("department_id") == department_id for record in load_teams()):
        raise ValueError("Department cannot be deleted while active teams reference it.")
    records = load_departments(include_deleted=True)
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("department_id") == department_id:
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            break
    if before_value is None:
        return False
    write_json_array(DEPARTMENTS_PATH, records)
    append_audit_log("master_data.department", department_id, "soft_delete", before_value, after_value, user=actor)
    return True


def default_department_record() -> dict[str, Any]:
    return {"entity_id": "", "entity_code": "", "entity_name": "", "department_code": "", "department_name": "", "department_manager": "", "effective_from": "", "effective_to": "", "remarks": "", "record_status": "Active"}


def team_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    record = {
        "entity_id": form.get("entity_id", "").strip(),
        "department_id": form.get("department_id", "").strip(),
        "team_code": form.get("team_code", "").strip(),
        "team_name": form.get("team_name", "").strip(),
        "team_manager": form.get("team_manager", "").strip(),
        "effective_from": form.get("effective_from", "").strip(),
        "effective_to": form.get("effective_to", "").strip(),
        "remarks": form.get("remarks", "").strip(),
    }
    return apply_department_snapshot(record)


def apply_department_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    department = find_active_department(str(record.get("department_id", "")))
    if department:
        record["entity_id"] = department.get("entity_id", "")
        record["entity_code"] = department.get("entity_code", "")
        record["entity_name"] = department.get("entity_name", "")
        record["department_code"] = department.get("department_code", "")
        record["department_name"] = department.get("department_name", "")
    else:
        record["entity_code"] = ""
        record["entity_name"] = ""
        record["department_code"] = ""
        record["department_name"] = ""
    return record


def apply_department_snapshot_preserving_existing(record: dict[str, Any]) -> dict[str, Any]:
    department = find_active_department(str(record.get("department_id", "")))
    if department:
        record["entity_id"] = department.get("entity_id", "")
        record["entity_code"] = department.get("entity_code", "")
        record["entity_name"] = department.get("entity_name", "")
        record["department_id"] = department.get("department_id", "")
        record["department_code"] = department.get("department_code", "")
        record["department_name"] = department.get("department_name", "")
        if not str(record.get("department", "")).strip() and str(department.get("department_name", "")).strip():
            record["department"] = department.get("department_name", "")
    return record


def apply_team_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    team = find_active_team(str(record.get("team_id", "")))
    if team:
        record["team_id"] = team.get("team_id", "")
        record["team_code"] = team.get("team_code", "")
        record["team_name"] = team.get("team_name", "")
        record["department_id"] = team.get("department_id", "")
        record["department_code"] = team.get("department_code", "")
        record["department_name"] = team.get("department_name", "")
        record["entity_id"] = team.get("entity_id", "")
        record["entity_code"] = team.get("entity_code", "")
        record["entity_name"] = team.get("entity_name", "")
        if not str(record.get("department", "")).strip() and str(team.get("department_name", "")).strip():
            record["department"] = team.get("department_name", "")
    return record


def apply_organization_snapshot_from_employee(record: dict[str, Any], employee: dict[str, Any]) -> dict[str, Any]:
    for key in [
        "entity_id",
        "entity_code",
        "entity_name",
        "department_id",
        "department_code",
        "department_name",
        "team_id",
        "team_code",
        "team_name",
    ]:
        value_text = str(employee.get(key, "")).strip()
        if value_text:
            record[key] = value_text
    if str(record.get("team_id", "")).strip():
        return apply_team_snapshot(record)
    if str(record.get("department_id", "")).strip():
        return apply_department_snapshot_preserving_existing(record)
    if not str(record.get("department", "")).strip() and str(employee.get("department_name", "")).strip():
        record["department"] = employee.get("department_name", "")
    return record


def team_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = team_fields_from_form(form)
    record["team_id"] = existing.get("team_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def validate_team_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_team_id: str = "") -> None:
    required_fields = [("entity_id", "Entity / 法人"), ("department_id", "Department / 部門"), ("team_code", "Team Code / チームコード"), ("team_name", "Team Name / チーム名")]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    department = find_active_department(str(record.get("department_id", "")))
    if not department:
        raise ValueError("Department must exist and be active.")
    if str(department.get("entity_id", "")) != str(record.get("entity_id", "")):
        raise ValueError("Department must belong to the selected entity.")
    department_id = str(record.get("department_id", "")).strip()
    team_code = str(record.get("team_code", "")).strip().lower()
    for existing in existing_records:
        if exclude_team_id and existing.get("team_id") == exclude_team_id:
            continue
        if str(existing.get("department_id", "")).strip() == department_id and str(existing.get("team_code", "")).strip().lower() == team_code:
            raise ValueError(f"Team Code already exists under this department: {record.get('team_code', '')}")


def save_team(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_teams(include_deleted=True)
    record = dict(record)
    validate_team_record(record, active_records(records))
    now = datetime.now(timezone.utc)
    record["team_id"] = f"team-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(TEAMS_PATH, records)
    append_audit_log("master_data.team", str(record.get("team_id", "")), "create", None, dict(record), user=actor)
    return record


def update_team(record: dict[str, Any], actor: str = LOCAL_ACTOR) -> dict[str, Any]:
    records = load_teams(include_deleted=True)
    team_id = str(record.get("team_id", "")).strip()
    if not team_id:
        raise ValueError("Team record ID is required.")
    validate_team_record(record, active_records(records), exclude_team_id=team_id)
    updated_records = []
    before_value: dict[str, Any] | None = None
    for item in records:
        if item.get("team_id") == team_id:
            before_value = dict(item)
            updated_records.append(record)
        else:
            updated_records.append(item)
    if before_value is None:
        raise ValueError("Team record was not found.")
    write_json_array(TEAMS_PATH, updated_records)
    append_audit_log("master_data.team", team_id, "update", before_value, dict(record), user=actor)
    return record


def soft_delete_team(team_id: str, actor: str = LOCAL_ACTOR) -> bool:
    team_id = team_id.strip()
    records = load_teams(include_deleted=True)
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("team_id") == team_id:
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            break
    if before_value is None:
        return False
    write_json_array(TEAMS_PATH, records)
    append_audit_log("master_data.team", team_id, "soft_delete", before_value, after_value, user=actor)
    return True


def default_team_record() -> dict[str, Any]:
    return {"entity_id": "", "entity_code": "", "entity_name": "", "department_id": "", "department_code": "", "department_name": "", "team_code": "", "team_name": "", "team_manager": "", "effective_from": "", "effective_to": "", "remarks": "", "record_status": "Active"}



def load_timesheet_entries(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(TIMESHEET_ENTRIES_PATH)
    if include_deleted:
        return records
    return [record for record in records if record.get("record_status", "Active") != "Deleted"]


def find_timesheet_entry(record_id: str) -> dict[str, Any] | None:
    record_id = record_id.strip()
    if not record_id:
        return None
    for record in load_timesheet_entries(include_deleted=True):
        if record.get("record_id") == record_id:
            return record
    return None


def approval_status(record: dict[str, Any]) -> str:
    status = str(record.get("approval_status", "Draft") or "Draft").strip()
    return status if status in {key for key, _label in APPROVAL_STATUSES} else "Draft"


def workflow_fields_from_existing(existing: dict[str, Any]) -> dict[str, Any]:
    return {
        "approval_status": approval_status(existing),
        "submitted_at": existing.get("submitted_at", ""),
        "submitted_by": existing.get("submitted_by", ""),
        "approved_at": existing.get("approved_at", ""),
        "approved_by": existing.get("approved_by", ""),
        "rejected_at": existing.get("rejected_at", ""),
        "rejected_by": existing.get("rejected_by", ""),
        "reject_reason": existing.get("reject_reason", ""),
        "reopened_at": existing.get("reopened_at", ""),
        "reopened_by": existing.get("reopened_by", ""),
    }


def initial_workflow_fields() -> dict[str, Any]:
    return {
        "approval_status": "Draft",
        "submitted_at": "",
        "submitted_by": "",
        "approved_at": "",
        "approved_by": "",
        "rejected_at": "",
        "rejected_by": "",
        "reject_reason": "",
        "reopened_at": "",
        "reopened_by": "",
    }


def ensure_month_not_locked(work_month: str, context: dict[str, Any] | None = None) -> None:
    normalized = normalize_work_month(work_month)
    if is_month_locked(normalized, context):
        raise ValueError(f"Month {normalized} is locked for the current Entity and cannot be changed.")


def ensure_record_month_not_locked(record: dict[str, Any], context: dict[str, Any] | None = None) -> None:
    ensure_month_not_locked(work_month_from_date(str(record.get("work_date", ""))), context)


def ensure_record_editable(record: dict[str, Any]) -> None:
    status = approval_status(record)
    if status in {"Submitted", "Approved"}:
        raise ValueError(f"Timesheet records with status {status} must be reopened or rejected before editing.")


def ensure_record_deletable(record: dict[str, Any]) -> None:
    status = approval_status(record)
    if status in {"Submitted", "Approved"}:
        raise ValueError(f"Timesheet records with status {status} cannot be deleted.")


def save_timesheet_entry(record: dict[str, Any], actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_timesheet_entries(include_deleted=True)
    active_records = scope_records_to_current_entity([item for item in records if item.get("record_status", "Active") != "Deleted"], context)
    record = enrich_timesheet_from_master_data(dict(record), context)
    record = apply_current_entity_snapshot(record, context)
    require_record_entity_access(record, context, "Timesheet")
    record.update(initial_workflow_fields())
    record = calculate_timesheet_fields(record)
    validate_timesheet_record(record, active_records, context=context)
    ensure_month_not_locked(work_month_from_date(str(record.get("work_date", ""))), context)
    now = datetime.now(timezone.utc)
    record["record_id"] = f"ts-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    records.append(record)
    write_json_array(TIMESHEET_ENTRIES_PATH, records)
    append_audit_log("timesheet.entry", str(record.get("record_id", "")), "create", None, dict(record), user=actor, context=context)
    return record


def update_timesheet_entry(record: dict[str, Any], actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_timesheet_entries(include_deleted=True)
    record_id = str(record.get("record_id", "")).strip()
    if not record_id:
        raise ValueError("Timesheet record ID is required.")
    existing = next((item for item in records if item.get("record_id") == record_id and item.get("record_status", "Active") != "Deleted"), None)
    if not existing:
        raise ValueError("Timesheet record was not found.")
    before_value = dict(existing)
    require_record_entity_access(existing, context, "Timesheet")
    ensure_record_editable(existing)
    ensure_record_month_not_locked(existing, context)
    record = enrich_timesheet_from_master_data(dict(record), context)
    record = apply_current_entity_snapshot(record, context)
    require_record_entity_access(record, context, "Timesheet")
    record.update(workflow_fields_from_existing(existing))
    record = calculate_timesheet_fields(record)
    ensure_month_not_locked(work_month_from_date(str(record.get("work_date", ""))), context)
    active_records = scope_records_to_current_entity([item for item in records if item.get("record_status", "Active") != "Deleted"], context)
    validate_timesheet_record(record, active_records, exclude_record_id=record_id, context=context)
    updated_records = []
    for item in records:
        if item.get("record_id") == record_id:
            updated_records.append(record)
        else:
            updated_records.append(item)
    if records_business_equal(before_value, record):
        unchanged = dict(before_value)
        unchanged["_no_changes"] = True
        return unchanged
    write_json_array(TIMESHEET_ENTRIES_PATH, updated_records)
    append_audit_log("timesheet.entry", record_id, "update", before_value, dict(record), user=actor, context=context)
    return record


def soft_delete_timesheet_entry(record_id: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> bool:
    record_id = record_id.strip()
    records = load_timesheet_entries(include_deleted=True)
    updated = False
    before_value: dict[str, Any] | None = None
    after_value: dict[str, Any] | None = None
    now = datetime.now(timezone.utc).isoformat()
    for record in records:
        if record.get("record_id") == record_id:
            if record.get("record_status", "Active") == "Deleted":
                return False
            require_record_entity_access(record, context, "Timesheet")
            before_value = dict(record)
            ensure_record_deletable(record)
            ensure_record_month_not_locked(record, context)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            updated = True
            break
    if updated:
        write_json_array(TIMESHEET_ENTRIES_PATH, records)
        append_audit_log("timesheet.entry", record_id, "soft_delete", before_value, after_value, user=actor, context=context)
    return updated


def update_timesheet_workflow(record_id: str, action: str, reject_reason: str = "", actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    record_id = record_id.strip()
    if not record_id:
        raise ValueError("Timesheet record ID is required.")
    records = load_timesheet_entries(include_deleted=True)
    target: dict[str, Any] | None = None
    for record in records:
        if record.get("record_id") == record_id:
            target = record
            break
    if not target or target.get("record_status", "Active") == "Deleted":
        raise ValueError("Timesheet record was not found.")
    require_record_entity_access(target, context, "Timesheet")
    before_value = dict(target)
    ensure_record_month_not_locked(target, context)
    status = approval_status(target)
    now = datetime.now(timezone.utc).isoformat()
    if action == "submit":
        if status not in {"Draft", "Rejected"}:
            raise ValueError("Only Draft or Rejected timesheets can be submitted.")
        target["approval_status"] = "Submitted"
        target["submitted_at"] = now
        target["submitted_by"] = actor
    elif action == "approve":
        if status != "Submitted":
            raise ValueError("Only Submitted timesheets can be approved.")
        target["approval_status"] = "Approved"
        target["approved_at"] = now
        target["approved_by"] = actor
    elif action == "reject":
        if status != "Submitted":
            raise ValueError("Only Submitted timesheets can be rejected.")
        target["approval_status"] = "Rejected"
        target["rejected_at"] = now
        target["rejected_by"] = actor
        target["reject_reason"] = reject_reason.strip()
    elif action == "reopen":
        if status not in {"Submitted", "Approved"}:
            raise ValueError("Only Submitted or Approved timesheets can be reopened.")
        target["approval_status"] = "Draft"
        target["reopened_at"] = now
        target["reopened_by"] = actor
    else:
        raise ValueError("Unknown timesheet workflow action.")
    target["updated_at"] = now
    write_json_array(TIMESHEET_ENTRIES_PATH, records)
    append_audit_log("timesheet.entry", record_id, action, before_value, dict(target), user=actor, context=context)
    return target


def submit_timesheet_record(record_id: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return update_timesheet_workflow(record_id, "submit", actor=actor, context=context)


def approve_timesheet_record(record_id: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return update_timesheet_workflow(record_id, "approve", actor=actor, context=context)


def reject_timesheet_record(record_id: str, reason: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return update_timesheet_workflow(record_id, "reject", reason, actor=actor, context=context)


def reopen_timesheet_record(record_id: str, actor: str = LOCAL_ACTOR, context: dict[str, Any] | None = None) -> dict[str, Any]:
    return update_timesheet_workflow(record_id, "reopen", actor=actor, context=context)


def clear_project_snapshot(record: dict[str, Any]) -> dict[str, Any]:
    for key in [
        "customer_name",
        "customer_code",
        "project_code",
        "project_name",
        "prefecture",
        "billing_note",
        "dispatch_assignment_source",
        "dispatch_assignment_history_id",
        "dispatch_contract_type",
        "dispatch_assignment_location",
        "dispatch_work_description",
        "dispatch_start_date",
        "dispatch_end_date",
        "dispatch_supervisor_name",
        "dispatch_supervisor_title",
        "dispatch_supervisor_phone",
        "dispatch_supervisor_email",
    ]:
        record[key] = ""
    record["dispatch_type"] = "Other"
    record["work_location"] = "Other"
    record["country"] = "Japan"
    record["client_approval_required"] = False
    record["billing_enabled"] = False
    record["billing_rate_per_hour_yen"] = 0
    record["dispatch_assignment_matched"] = False
    return record


def apply_dispatch_assignment_snapshot(record: dict[str, Any], assignment: dict[str, Any]) -> dict[str, Any]:
    record["customer_name"] = assignment.get("customer_name", "")
    record["project_name"] = assignment.get("project_name", "")
    record["project_code"] = ""
    record["dispatch_type"] = assignment.get("dispatch_type", "Dispatch") or "Dispatch"
    record["work_location"] = assignment.get("work_location", "Customer Site") or "Customer Site"
    record["country"] = assignment.get("country", "Japan") or "Japan"
    record["client_approval_required"] = False
    record["billing_enabled"] = False
    record["billing_rate_per_hour_yen"] = 0
    record["billing_note"] = ""
    for key in [
        "dispatch_assignment_matched",
        "dispatch_assignment_source",
        "dispatch_assignment_history_id",
        "dispatch_contract_type",
        "dispatch_assignment_location",
        "dispatch_work_description",
        "dispatch_start_date",
        "dispatch_end_date",
        "dispatch_supervisor_name",
        "dispatch_supervisor_title",
        "dispatch_supervisor_phone",
        "dispatch_supervisor_email",
    ]:
        record[key] = assignment.get(key, False if key == "dispatch_assignment_matched" else "")
    return record


def enrich_timesheet_from_master_data(record: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    record = dict(record)
    employee = find_active_employee_by_no(str(record.get("employee_no", "")), context)
    if employee:
        record["employee_id"] = employee.get("employee_id", "")
        record["employee_master_id"] = employee.get("employee_master_id") or employee.get("employee_id", "")
        record["employee_no"] = employee.get("employee_no", record.get("employee_no", ""))
        record["employee_no_snapshot"] = record.get("employee_no", "")
        record["employee_name"] = employee.get("employee_name", "")
        record["employee_name_snapshot"] = employee.get("employee_name", "")
        record["department"] = employee.get("department", "")
        record["employee_source"] = employee.get("source", "local")
        record["employment_type"] = employee.get("employment_type", "")
        record["employment_status"] = employee.get("employment_status", "")
        record = apply_organization_snapshot_from_employee(record, employee)
        record["scheduled_work_minutes"] = parse_non_negative_int(employee.get("default_scheduled_work_minutes", DEFAULT_SCHEDULED_WORK_MINUTES), "Default Scheduled Work Minutes", default=DEFAULT_SCHEDULED_WORK_MINUTES)
    project_code = str(record.get("project_code", "")).strip()
    project = find_active_project_by_code(project_code, context)
    if project:
        record["project_name"] = project.get("project_name", "")
        record["customer_name"] = project.get("customer_name", "")
        record["dispatch_type"] = project.get("dispatch_type", "Other") or "Other"
        record["work_location"] = project.get("work_location", "Other") or "Other"
        record["country"] = project.get("country", "Japan") or "Japan"
        record["prefecture"] = project.get("prefecture", "")
        record["client_approval_required"] = bool(project.get("client_approval_required", False))
        record["customer_code"] = project.get("customer_code", "")
        record["billing_enabled"] = bool(project.get("billing_enabled", False))
        record["billing_rate_per_hour_yen"] = parse_non_negative_int(project.get("billing_rate_per_hour_yen", 0), "Billing Rate per Hour JPY", default=0)
        record["billing_note"] = project.get("billing_note", "")
        record["dispatch_assignment_matched"] = False
    elif not project_code:
        session_id = str(context.get("session_id", "")) if context else ""
        assignment = fetch_employeeadmin_dispatch_assignment(session_id, str(record.get("employee_no", "")), str(record.get("work_date", "")))
        record = clear_project_snapshot(record)
        if assignment:
            record = apply_dispatch_assignment_snapshot(record, assignment)
    return record


def timesheet_record_from_form(form: dict[str, str]) -> dict[str, Any]:
    record = timesheet_fields_from_form(form)
    return record


def timesheet_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    record = timesheet_fields_from_form(form)
    record["record_id"] = existing.get("record_id", "")
    record["record_status"] = existing.get("record_status", "Active")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def timesheet_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    employee_no = form.get("employee_no", "").strip()
    return {
        "employee_no": employee_no,
        "employee_name": form.get("employee_name", "").strip(),
        "department": form.get("department", "").strip(),
        "entity_id": form.get("entity_id", "").strip(),
        "entity_code": form.get("entity_code", "").strip(),
        "entity_name": form.get("entity_name", "").strip(),
        "department_id": form.get("department_id", "").strip(),
        "department_code": form.get("department_code", "").strip(),
        "department_name": form.get("department_name", "").strip(),
        "team_id": form.get("team_id", "").strip(),
        "team_code": form.get("team_code", "").strip(),
        "team_name": form.get("team_name", "").strip(),
        "customer_name": form.get("customer_name", "").strip(),
        "project_code": form.get("project_code", "").strip(),
        "project_name": form.get("project_name", "").strip(),
        "dispatch_type": form.get("dispatch_type", "Other").strip() or "Other",
        "work_location": form.get("work_location", "Other").strip() or "Other",
        "country": form.get("country", "Japan").strip() or "Japan",
        "prefecture": form.get("prefecture", "").strip(),
        "business_trip_flag": parse_bool(form.get("business_trip_flag", "false")),
        "visa_status": form.get("visa_status", "").strip(),
        "client_approval_required": parse_bool(form.get("client_approval_required", "false")),
        "work_date": form.get("work_date", "").strip(),
        "attendance_status": form.get("attendance_status", "Worked").strip() or "Worked",
        "start_time": form.get("start_time", "").strip(),
        "end_time": form.get("end_time", "").strip(),
        "break_minutes": parse_non_negative_int(form.get("break_minutes", "60"), "Break Minutes", default=60),
        "scheduled_work_minutes": parse_non_negative_int(form.get("scheduled_work_minutes", "480"), "Scheduled Work Minutes", default=480),
        "night_work_minutes": parse_non_negative_int(form.get("night_work_minutes", "0"), "Night Work Minutes", default=0),
        "is_legal_holiday": parse_bool(form.get("is_legal_holiday", "false")),
        "is_company_holiday": parse_bool(form.get("is_company_holiday", "false")),
        "is_late": parse_bool(form.get("is_late", "false")),
        "is_early_leave": parse_bool(form.get("is_early_leave", "false")),
        "late_minutes": parse_non_negative_int(form.get("late_minutes", "0"), "Late Minutes", default=0),
        "early_leave_minutes": parse_non_negative_int(form.get("early_leave_minutes", "0"), "Early Leave Minutes", default=0),
        "approval_status": form.get("approval_status", "Draft").strip() or "Draft",
        "approved_by": form.get("approved_by", "").strip(),
        "approved_at": form.get("approved_at", "").strip(),
        "employee_remarks": form.get("employee_remarks", "").strip(),
        "manager_remarks": form.get("manager_remarks", "").strip(),
    }


def overlap_minutes(start_a: int, end_a: int, start_b: int, end_b: int) -> int:
    return max(0, min(end_a, end_b) - max(start_a, start_b))


def calculate_night_work_minutes(start_minutes: int, end_minutes: int, actual_work_minutes: int) -> int:
    night_windows = [(-120, 300), (1320, 1740), (2760, 3180)]
    gross_night_minutes = sum(overlap_minutes(start_minutes, end_minutes, window_start, window_end) for window_start, window_end in night_windows)
    return min(gross_night_minutes, actual_work_minutes)


def required_break_minutes_for_work(actual_work_minutes: int) -> int:
    if actual_work_minutes > 480:
        return 60
    if actual_work_minutes > 360:
        return 45
    return 0


def break_warning_text(shortage_minutes: int) -> str:
    if shortage_minutes <= 0:
        return ""
    return f"Break time may be insufficient under Japanese labor standards. Shortage: {shortage_minutes} minutes."


def bool_select_html(name: str, selected: bool, messages: dict[str, str]) -> str:
    options = []
    for option_value, label_key in [("false", "boolean.false"), ("true", "boolean.true")]:
        selected_attr = " selected" if (option_value == "true") == selected else ""
        options.append(f"<option value='{option_value}'{selected_attr}>{h(t(messages, label_key))}</option>")
    return f"<select name='{h(name)}'>{''.join(options)}</select>"


def calculation_breakdown_html(record: dict[str, Any], messages: dict[str, str]) -> str:
    warning = str(record.get("break_warning", "")).strip()
    warning_html = f"<p class='message-strip message-warning'>{h(warning)}</p>" if warning else ""
    return f"""
    <div class="sap-readonly-grid">
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.gross_work'))}</div><div class="value">{format_minutes(record.get('gross_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'timesheet.actual_work'))}</div><div class="value">{format_minutes(record.get('actual_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.scheduled_work'))}</div><div class="value">{format_minutes(record.get('scheduled_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'timesheet.overtime'))}</div><div class="value">{format_minutes(record.get('overtime_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.night_work'))}</div><div class="value">{format_minutes(record.get('night_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.holiday_work'))}</div><div class="value">{format_minutes(record.get('holiday_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.legal_holiday_work'))}</div><div class="value">{format_minutes(record.get('legal_holiday_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.company_holiday_work'))}</div><div class="value">{format_minutes(record.get('company_holiday_work_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.break_required'))}</div><div class="value">{format_minutes(record.get('break_required_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.break_shortage'))}</div><div class="value">{format_minutes(record.get('break_shortage_minutes', 0))}</div></div>
      <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.cross_midnight'))}</div><div class="value">{h(t(messages, 'boolean.true' if record.get('cross_midnight_flag') else 'boolean.false'))}</div></div>
    </div>
    {warning_html}
    """


def compact_breakdown_html(record: dict[str, Any]) -> str:
    parts = []
    night = parse_non_negative_int(record.get("night_work_minutes", 0), "Night Work Minutes")
    holiday = parse_non_negative_int(record.get("holiday_work_minutes", 0), "Holiday Work Minutes")
    shortage = parse_non_negative_int(record.get("break_shortage_minutes", 0), "Break Shortage Minutes")
    if night:
        parts.append(f"Night: {format_minutes(night)}")
    if holiday:
        parts.append(f"Holiday: {format_minutes(holiday)}")
    if shortage:
        parts.append(f"<span class='warn'>Break shortage: {shortage} min</span>")
    if record.get("cross_midnight_flag"):
        parts.append("Cross-midnight")
    return "<br>".join(parts) if parts else "-"


def calculate_timesheet_fields(record: dict[str, Any]) -> dict[str, Any]:
    work_date = str(record.get("work_date", "")).strip()
    if work_date:
        try:
            parsed_date = datetime.strptime(work_date, "%Y-%m-%d")
            record["weekday"] = parsed_date.strftime("%A")
        except ValueError:
            record["weekday"] = ""
    else:
        record["weekday"] = ""

    if record.get("attendance_status") != "Worked":
        record["start_time"] = str(record.get("start_time", "")).strip()
        record["end_time"] = str(record.get("end_time", "")).strip()
        for key in [
            "gross_work_minutes",
            "actual_work_minutes",
            "overtime_minutes",
            "night_work_minutes",
            "holiday_work_minutes",
            "legal_holiday_work_minutes",
            "company_holiday_work_minutes",
            "break_required_minutes",
            "break_shortage_minutes",
        ]:
            record[key] = 0
        record["break_warning"] = ""
        record["cross_midnight_flag"] = False
        return record

    start_minutes = parse_time_to_minutes(str(record.get("start_time", "")), "Start Time")
    raw_end_minutes = parse_time_to_minutes(str(record.get("end_time", "")), "End Time")
    break_minutes = parse_non_negative_int(record.get("break_minutes", 0), "Break Minutes")
    scheduled_minutes = parse_non_negative_int(record.get("scheduled_work_minutes", 480), "Scheduled Work Minutes")
    if raw_end_minutes == start_minutes:
        raise ValueError("End Time must be different from Start Time.")
    cross_midnight = raw_end_minutes < start_minutes
    end_minutes = raw_end_minutes + (24 * 60 if cross_midnight else 0)
    gross_minutes = end_minutes - start_minutes
    actual_minutes = gross_minutes - break_minutes
    if actual_minutes < 0:
        raise ValueError("Actual work minutes cannot be negative. Please check break time.")
    record["gross_work_minutes"] = gross_minutes
    record["cross_midnight_flag"] = cross_midnight
    record["actual_work_minutes"] = actual_minutes
    record["overtime_minutes"] = max(0, actual_minutes - scheduled_minutes)
    record["night_work_minutes"] = calculate_night_work_minutes(start_minutes, end_minutes, actual_minutes)
    is_legal_holiday = bool(record.get("is_legal_holiday"))
    is_company_holiday = bool(record.get("is_company_holiday"))
    record["legal_holiday_work_minutes"] = actual_minutes if is_legal_holiday else 0
    record["company_holiday_work_minutes"] = actual_minutes if is_company_holiday else 0
    record["holiday_work_minutes"] = actual_minutes if is_legal_holiday or is_company_holiday else 0
    required_break = required_break_minutes_for_work(actual_minutes)
    shortage = max(0, required_break - break_minutes)
    record["break_required_minutes"] = required_break
    record["break_shortage_minutes"] = shortage
    record["break_warning"] = break_warning_text(shortage)
    return record


def validate_timesheet_record(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_record_id: str = "", context: dict[str, Any] | None = None) -> None:
    required_fields = [
        ("employee_no", "Employee No. / 社員No."),
        ("work_date", "Work Date / 勤務日"),
        ("attendance_status", "Attendance Status / 勤怠区分"),
        ("approval_status", "Approval Status / 承認状態"),
    ]
    missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
    if missing:
        raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    try:
        datetime.strptime(str(record.get("work_date", "")), "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError("Work Date must use YYYY-MM-DD format.") from exc
    if record.get("attendance_status") not in {key for key, _label in ATTENDANCE_STATUSES}:
        raise ValueError("Attendance Status is invalid.")
    if record.get("approval_status") not in {key for key, _label in APPROVAL_STATUSES}:
        raise ValueError("Approval Status is invalid.")
    if record.get("work_location") not in {key for key, _label in WORK_LOCATIONS}:
        raise ValueError("Work Location is invalid.")
    if record.get("dispatch_type") not in {key for key, _label in DISPATCH_TYPES}:
        raise ValueError("Dispatch Type is invalid.")
    available_employees = load_timesheet_employees(context)
    if available_employees and not find_active_employee_by_no(str(record.get("employee_no", "")), context):
        raise ValueError("Employee No. must exist in active Employee Master.")
    project_code = str(record.get("project_code", "")).strip()
    if project_code and not find_active_project_by_code(project_code, context):
        raise ValueError("Project Code must exist in active Project Master for the current Entity when selected.")
    if record.get("attendance_status") == "Worked":
        if not record.get("start_time") or not record.get("end_time"):
            raise ValueError("Start Time and End Time are required for Worked attendance.")
        parse_time_to_minutes(str(record.get("start_time", "")), "Start Time")
        parse_time_to_minutes(str(record.get("end_time", "")), "End Time")
    if str(record.get("approved_at", "")).strip():
        validate_datetime_text(str(record.get("approved_at", "")), "Approved At")
    validate_duplicate_timesheet(record, existing_records, exclude_record_id=exclude_record_id)


def validate_duplicate_timesheet(record: dict[str, Any], existing_records: list[dict[str, Any]], exclude_record_id: str = "") -> None:
    employee_no = str(record.get("employee_no", "")).strip().lower()
    work_date = str(record.get("work_date", "")).strip()
    project_key = str(record.get("project_code") or record.get("project_name") or "").strip().lower()
    for existing in existing_records:
        if exclude_record_id and existing.get("record_id") == exclude_record_id:
            continue
        existing_key = str(existing.get("project_code") or existing.get("project_name") or "").strip().lower()
        if (
            str(existing.get("employee_no", "")).strip().lower() == employee_no
            and str(existing.get("work_date", "")).strip() == work_date
            and existing_key == project_key
        ):
            raise ValueError("Duplicate active timesheet exists for the same employee, work date, and project.")


def validate_datetime_text(value_text: str, label: str) -> None:
    value_text = value_text.strip()
    if not value_text:
        return
    try:
        datetime.fromisoformat(value_text)
    except ValueError as exc:
        raise ValueError(f"{label} must use ISO datetime format, for example 2026-06-15T18:00:00+09:00.") from exc


def filter_timesheet_entries(records: list[dict[str, Any]], filters: dict[str, str], context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    filtered = scope_records_to_current_entity(records, context)
    entity_id = filters.get("entity_id", "")
    employee_no = filters.get("employee_no", "").lower()
    work_month = filters.get("work_month", "")
    customer_name = filters.get("customer_name", "").lower()
    project_code = filters.get("project_code", "").lower()
    project_name = filters.get("project_name", "").lower()
    approval_status_filter = filters.get("approval_status", "")
    if entity_id:
        filtered = [record for record in filtered if entity_id in {str(record.get("entity_id", "")).strip(), str(record.get("entity_code", "")).strip()}]
    if employee_no:
        filtered = [record for record in filtered if employee_no == str(record.get("employee_no", "")).lower()]
    if work_month:
        filtered = [record for record in filtered if str(record.get("work_date", "")).startswith(work_month)]
    if customer_name:
        filtered = [record for record in filtered if customer_name in str(record.get("customer_name", "")).lower()]
    if project_code:
        filtered = [record for record in filtered if project_code == str(record.get("project_code", "")).lower()]
    if project_name:
        filtered = [record for record in filtered if project_name in str(record.get("project_name", "")).lower()]
    if approval_status_filter:
        filtered = [record for record in filtered if approval_status(record) == approval_status_filter]
    return filtered


def calculate_timesheet_totals(records: list[dict[str, Any]]) -> dict[str, int]:
    keys = [
        "actual_work_minutes",
        "overtime_minutes",
        "night_work_minutes",
        "holiday_work_minutes",
        "legal_holiday_work_minutes",
        "company_holiday_work_minutes",
        "break_shortage_minutes",
    ]
    return {key: sum(parse_non_negative_int(record.get(key, 0), key) for record in records) for key in keys}


def calculate_monthly_approval_counts(work_month: str, context: dict[str, Any] | None = None) -> dict[str, int]:
    normalized = normalize_work_month(work_month)
    counts = {"Draft": 0, "Submitted": 0, "Approved": 0, "Rejected": 0, "active_count": 0, "deleted_count": 0}
    for record in scope_records_to_current_entity(load_timesheet_entries(include_deleted=True), context):
        if not str(record.get("work_date", "")).startswith(normalized):
            continue
        if record.get("record_status", "Active") == "Deleted":
            counts["deleted_count"] += 1
            continue
        counts["active_count"] += 1
        counts[approval_status(record)] += 1
    return counts


def month_lock_blocking_reason(work_month: str) -> str:
    return period_close_blocking_reason(work_month)


def calculate_monthly_employee_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for record in records:
        work_date = str(record.get("work_date", ""))
        if len(work_date) < 7:
            continue
        work_month = work_date[:7]
        employee_no = str(record.get("employee_no", "")).strip()
        if not employee_no:
            continue
        key = (work_month, employee_no)
        if key not in grouped:
            grouped[key] = {
                "work_month": work_month,
                "employee_no": employee_no,
                "employee_name": str(record.get("employee_name", "")),
                "entry_count": 0,
                "actual_work_minutes": 0,
                "overtime_minutes": 0,
                "night_work_minutes": 0,
                "holiday_work_minutes": 0,
                "break_shortage_count": 0,
            }
        if not grouped[key].get("employee_name") and record.get("employee_name"):
            grouped[key]["employee_name"] = str(record.get("employee_name", ""))
        grouped[key]["entry_count"] += 1
        grouped[key]["actual_work_minutes"] += parse_non_negative_int(record.get("actual_work_minutes", 0), "Actual Work Minutes")
        grouped[key]["overtime_minutes"] += parse_non_negative_int(record.get("overtime_minutes", 0), "Overtime Minutes")
        grouped[key]["night_work_minutes"] += parse_non_negative_int(record.get("night_work_minutes", 0), "Night Work Minutes")
        grouped[key]["holiday_work_minutes"] += parse_non_negative_int(record.get("holiday_work_minutes", 0), "Holiday Work Minutes")
        if parse_non_negative_int(record.get("break_shortage_minutes", 0), "Break Shortage Minutes"):
            grouped[key]["break_shortage_count"] += 1
    return sorted(grouped.values(), key=lambda row: (str(row.get("work_month", "")), str(row.get("employee_no", ""))), reverse=True)


def calculate_monthly_project_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str, str], dict[str, Any]] = {}
    for record in records:
        work_date = str(record.get("work_date", ""))
        if len(work_date) < 7:
            continue
        work_month = work_date[:7]
        customer_name = str(record.get("customer_name", "")).strip()
        project_code = str(record.get("project_code", "")).strip()
        project_name = str(record.get("project_name", "")).strip()
        key = (work_month, customer_name, project_code, project_name)
        if key not in grouped:
            grouped[key] = {
                "work_month": work_month,
                "customer_name": customer_name,
                "project_code": project_code,
                "project_name": project_name,
                "entry_count": 0,
                "actual_work_minutes": 0,
                "overtime_minutes": 0,
                "night_work_minutes": 0,
                "holiday_work_minutes": 0,
                "break_shortage_count": 0,
            }
        grouped[key]["entry_count"] += 1
        grouped[key]["actual_work_minutes"] += parse_non_negative_int(record.get("actual_work_minutes", 0), "Actual Work Minutes")
        grouped[key]["overtime_minutes"] += parse_non_negative_int(record.get("overtime_minutes", 0), "Overtime Minutes")
        grouped[key]["night_work_minutes"] += parse_non_negative_int(record.get("night_work_minutes", 0), "Night Work Minutes")
        grouped[key]["holiday_work_minutes"] += parse_non_negative_int(record.get("holiday_work_minutes", 0), "Holiday Work Minutes")
        if parse_non_negative_int(record.get("break_shortage_minutes", 0), "Break Shortage Minutes"):
            grouped[key]["break_shortage_count"] += 1
    return sorted(grouped.values(), key=lambda row: (str(row.get("work_month", "")), str(row.get("customer_name", "")), str(row.get("project_code", ""))), reverse=True)


def organization_summary_label(*parts: Any, fallback: str) -> str:
    label = " ".join(str(part).strip() for part in parts if str(part).strip())
    return label or fallback


def calculate_monthly_organization_summary(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    unassigned = "Unassigned"
    grouped: dict[tuple[str, str, str, str, str, str, str], dict[str, Any]] = {}
    for record in records:
        work_date = str(record.get("work_date", ""))
        if len(work_date) < 7:
            continue
        work_month = work_date[:7]
        entity_code = str(record.get("entity_code", "")).strip()
        entity_label = organization_summary_label(record.get("entity_code", ""), record.get("entity_name", ""), fallback=unassigned)
        department_code = str(record.get("department_code", "")).strip()
        department_label = organization_summary_label(record.get("department_code", ""), record.get("department_name", ""), fallback=str(record.get("department", "")).strip() or unassigned)
        team_code = str(record.get("team_code", "")).strip()
        team_label = organization_summary_label(record.get("team_code", ""), record.get("team_name", ""), fallback=unassigned)
        key = (work_month, entity_code, entity_label, department_code, department_label, team_code, team_label)
        if key not in grouped:
            grouped[key] = {
                "work_month": work_month,
                "entity_code": entity_code,
                "entity_label": entity_label,
                "department_code": department_code,
                "department_label": department_label,
                "team_code": team_code,
                "team_label": team_label,
                "entry_count": 0,
                "actual_work_minutes": 0,
                "overtime_minutes": 0,
                "night_work_minutes": 0,
                "holiday_work_minutes": 0,
                "break_shortage_count": 0,
            }
        grouped[key]["entry_count"] += 1
        grouped[key]["actual_work_minutes"] += parse_non_negative_int(record.get("actual_work_minutes", 0), "Actual Work Minutes")
        grouped[key]["overtime_minutes"] += parse_non_negative_int(record.get("overtime_minutes", 0), "Overtime Minutes")
        grouped[key]["night_work_minutes"] += parse_non_negative_int(record.get("night_work_minutes", 0), "Night Work Minutes")
        grouped[key]["holiday_work_minutes"] += parse_non_negative_int(record.get("holiday_work_minutes", 0), "Holiday Work Minutes")
        if parse_non_negative_int(record.get("break_shortage_minutes", 0), "Break Shortage Minutes"):
            grouped[key]["break_shortage_count"] += 1
    return sorted(grouped.values(), key=lambda row: (str(row.get("work_month", "")), str(row.get("entity_code", "")), str(row.get("department_code", "")), str(row.get("team_code", ""))), reverse=True)


def default_timesheet_record() -> dict[str, Any]:
    return {
        "employee_id": "",
        "employee_master_id": "",
        "employee_no_snapshot": "",
        "employee_name_snapshot": "",
        "employee_source": "",
        "employment_type": "",
        "employment_status": "",
        "employee_name": "",
        "department": "",
        "entity_id": "",
        "entity_code": "",
        "entity_name": "",
        "department_id": "",
        "department_code": "",
        "department_name": "",
        "team_id": "",
        "team_code": "",
        "team_name": "",
        "customer_name": "",
        "project_code": "",
        "project_name": "",
        "dispatch_type": "Other",
        "work_location": "Other",
        "country": "Japan",
        "business_trip_flag": False,
        "client_approval_required": False,
        "attendance_status": "Worked",
        "start_time": "09:00",
        "end_time": "18:00",
        "break_minutes": 60,
        "scheduled_work_minutes": 480,
        "gross_work_minutes": 0,
        "night_work_minutes": 0,
        "holiday_work_minutes": 0,
        "legal_holiday_work_minutes": 0,
        "company_holiday_work_minutes": 0,
        "break_required_minutes": 0,
        "break_shortage_minutes": 0,
        "break_warning": "",
        "cross_midnight_flag": False,
        "is_legal_holiday": False,
        "is_company_holiday": False,
        "is_late": False,
        "late_minutes": 0,
        "is_early_leave": False,
        "early_leave_minutes": 0,
        "approval_status": "Draft",
        "submitted_at": "",
        "submitted_by": "",
        "approved_at": "",
        "approved_by": "",
        "rejected_at": "",
        "rejected_by": "",
        "reject_reason": "",
        "reopened_at": "",
        "reopened_by": "",
    }


def parse_time_to_minutes(value_text: str, label: str) -> int:
    value_text = value_text.strip()
    if ":" not in value_text:
        raise ValueError(f"{label} must use 0-24 hour format, for example 0:00, 00:00, 9:00, 18:00, or 24:00.")
    hour_text, minute_text = value_text.split(":", 1)
    if not hour_text.isdigit() or not minute_text.isdigit() or len(minute_text) != 2:
        raise ValueError(f"{label} must use 0-24 hour format, for example 0:00, 00:00, 9:00, 18:00, or 24:00.")
    hour = int(hour_text)
    minute = int(minute_text)
    if not 0 <= hour <= 24 or not 0 <= minute <= 59:
        raise ValueError(f"{label} must be a valid 0-24 hour time.")
    if hour == 24 and minute != 0:
        raise ValueError(f"{label} can use 24:00, but not times after 24:00.")
    return hour * 60 + minute


def parse_non_negative_int(value: Any, label: str, default: int = 0) -> int:
    if value is None or value == "":
        return default
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer.") from exc
    if parsed < 0:
        raise ValueError(f"{label} cannot be negative.")
    return parsed


def parse_bool(value_text: str) -> bool:
    return str(value_text).strip().lower() in {"1", "true", "yes", "on"}


def bool_value(record: dict[str, Any], key: str) -> str:
    return "true" if bool(record.get(key, False)) else "false"


def format_minutes(value: Any) -> str:
    minutes = parse_non_negative_int(value, "Minutes")
    hours, remaining = divmod(minutes, 60)
    return f"{hours}h {remaining:02d}m"


def format_yen(value: Any) -> str:
    amount = parse_non_negative_int(value, "JPY Amount")
    return f"¥{amount:,}"


def select_options(options: list[tuple[str, str]], selected: str) -> str:
    option_html = []
    for option_value, label in options:
        selected_attr = " selected" if option_value == selected else ""
        option_html.append(f"<option value='{escape(option_value)}'{selected_attr}>{escape(label)}</option>")
    return "".join(option_html)


def select_options_i18n(options: list[tuple[str, str]], selected: str, messages: dict[str, str], prefix: str) -> str:
    option_html = []
    for option_value, _label in options:
        selected_attr = " selected" if option_value == selected else ""
        label = enum_label(messages, prefix, option_value)
        option_html.append(f"<option value='{h(option_value)}'{selected_attr}>{h(label)}</option>")
    return "".join(option_html)


def value(record: dict[str, Any], key: str) -> str:
    return escape(str(record.get(key, "") if record.get(key, "") is not None else ""))


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the TAC-timesheet local web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    args = parser.parse_args()
    sync_relevant_timesheet_periods()
    server = ThreadingHTTPServer((args.host, args.port), TACTimesheetHandler)
    print(f"TAC-timesheet running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TAC-timesheet.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
