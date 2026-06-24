"""Local web app for TAC-reimbursement - Japan employee reimbursement MVP.

This MVP intentionally uses only Python standard library modules so it can run
on a laptop without installing dependencies.
"""

from __future__ import annotations

import argparse
import cgi
import csv
from datetime import datetime, timezone
import io
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
import unicodedata

ROOT_DIR = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT_DIR / "i18n"
MACOS_VISION_OCR_SCRIPT = ROOT_DIR / "backend" / "macos_vision_ocr.swift"
CLAIMS_PATH = ROOT_DIR / "database" / "claims.json"
APPROVAL_LOGS_PATH = ROOT_DIR / "database" / "approval_logs.json"
AUDIT_LOGS_PATH = ROOT_DIR / "database" / "audit_logs.json"
REPORT_EXPORTS_PATH = ROOT_DIR / "database" / "report_exports.json"
PAYMENT_CLOSINGS_PATH = ROOT_DIR / "database" / "payment_closings.json"
ATTACHMENTS_DIR = ROOT_DIR / "attachments"  # Legacy compatibility for records created before expensebill storage.
EXPENSEBILL_DIR = ROOT_DIR / "expensebill"
EMPLOYEEADMIN_EMPLOYEES_PATH = ROOT_DIR.parent / "TAC-employeeadmin" / "database" / "employees.json"
DEFAULT_FINANCE_ACTOR = "Finance"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
CONFIGURED_PUBLIC_HOSTS = {host.strip().lower() for host in os.environ.get("TACAI_ALLOWED_PUBLIC_HOSTS", "").split(",") if host.strip()}
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009}


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


def base_url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


APP_BASE_URL = public_base_url("EXPENSE_PUBLIC_BASE_URL", 8003)
PORTAL_BASE_URL = public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")
PUBLIC_ALLOWED_HOSTS = CONFIGURED_PUBLIC_HOSTS | {host for host in [base_url_host(APP_BASE_URL), base_url_host(PORTAL_BASE_URL), base_url_host(USER_ADMIN_BASE_URL)] if host}
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "tacai_flash"
LANG_COOKIE = "tacai_lang"
REQUIRED_MODULE_PERMISSION = "reimbursement.access"
DEFAULT_LANG = "zh"
SUPPORTED_LANGS = {"zh", "ja", "en"}
MAX_ATTACHMENT_BYTES = 5 * 1024 * 1024
ALLOWED_ATTACHMENT_EXTENSIONS = {".jpg", ".jpeg", ".pdf", ".png", ".webp"}
OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OCR_TESSERACT_LANGUAGES = "jpn+eng"
OCR_TIMEOUT_SECONDS = 30
REPORT_TYPE_PAYROLL_REIMBURSEMENT_CSV = "payroll_reimbursement_csv"
REPORT_CSV_COLUMNS = [
    "claim_no",
    "status",
    "employee_no",
    "employee_name",
    "department",
    "claim_month",
    "expense_date",
    "category",
    "vendor_name",
    "invoice_or_receipt_number",
    "qualified_invoice_number",
    "is_qualified_invoice",
    "currency",
    "total_amount",
    "tax_amount",
    "tax_rate",
    "payment_method",
    "business_purpose",
    "attachment_filename",
    "approved_at",
    "approved_by",
    "finance_notes",
]

CLAIM_STATUSES = [
    ("Draft", "草稿 / 下書き / Draft"),
    ("Submitted", "已提交 / 申請済 / Submitted"),
    ("Approved", "已批准 / 承認済 / Approved"),
    ("Rejected", "已驳回 / 差戻し / Rejected"),
    ("Paid", "已付款 / 支払済 / Paid"),
]

CATEGORIES = [
    ("transportation", "交通费 / 交通費 / Transportation"),
    ("client_visit", "客户拜访 / 顧客訪問 / Client Visit"),
    ("meal", "餐费・会议费 / 会議費・接待交際費 / Meal"),
    ("office_expense", "办公用品 / 消耗品費 / Office Expense"),
    ("communication", "通信费 / 通信費 / Communication"),
    ("accommodation", "住宿费 / 宿泊費 / Accommodation"),
    ("other", "其他 / その他 / Other"),
]

TAX_RATES = ["10%", "8%", "0%", "mixed", "unknown"]
OCR_STATUSES = {"not_run", "draft", "confirmed", "failed", "not_available"}

PAYMENT_METHODS = [
    ("employee_paid", "员工垫付 / 立替払い / Employee paid"),
    ("company_card", "公司卡 / 法人カード / Company card"),
    ("bank_transfer", "银行转账 / 銀行振込 / Bank transfer"),
    ("other", "其他 / その他 / Other"),
]

QUALIFIED_INVOICE_OPTIONS = [
    ("unknown", "未确认 / 未確認 / Unknown"),
    ("yes", "是 / 適格請求書 / Yes"),
    ("no", "否 / 対象外 / No"),
]


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


def get_lang_from_request(query: dict[str, list[str]], cookie_header: str = "") -> str:
    lang = query.get("lang", [""])[0].strip().lower()
    if lang in SUPPORTED_LANGS:
        return lang
    cookie = SimpleCookie(cookie_header)
    morsel = cookie.get(LANG_COOKIE)
    if morsel and morsel.value in SUPPORTED_LANGS:
        return morsel.value
    return DEFAULT_LANG


def url_with_lang(path: str, lang: str, params: dict[str, Any] | None = None) -> str:
    params = {key: value for key, value in (params or {}).items() if value not in {None, ""}}
    params["lang"] = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    return f"{path}?{urlencode(params)}"


def user_lang(user: dict[str, Any] | None) -> str:
    if user and str(user.get("_lang", "")) in SUPPORTED_LANGS:
        return str(user.get("_lang"))
    return DEFAULT_LANG


def user_messages(user: dict[str, Any] | None) -> dict[str, str]:
    return load_i18n(user_lang(user))


def ui_text(user: dict[str, Any] | None, zh: str, ja: str, en: str) -> str:
    return {"zh": zh, "ja": ja, "en": en}.get(user_lang(user), zh)


def language_switcher_html(lang: str, current_path: str = "/") -> str:
    messages = load_i18n(lang)
    links = []
    for candidate in ["zh", "ja", "en"]:
        label = t(messages, f"language.{candidate}", candidate)
        class_name = "pill" if candidate == lang else "button secondary"
        links.append(f'<a class="{class_name}" href="{escape(url_with_lang(current_path, candidate))}">{escape(label)}</a>')
    return "".join(links)


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


def is_system_admin(user: dict[str, Any] | None) -> bool:
    return bool(user and "system_admin" in set(user.get("roles", [])))


def has_any_permission(user: dict[str, Any], permission_keys: list[str] | tuple[str, ...]) -> bool:
    return any(has_permission(user, permission_key) for permission_key in permission_keys)


def actor_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return DEFAULT_FINANCE_ACTOR
    for key in ("display_name", "username", "email", "user_id", "id"):
        value = str(user.get(key, "") or "").strip()
        if value:
            return value
    return DEFAULT_FINANCE_ACTOR


def has_required_module_access(user: dict[str, Any]) -> bool:
    return has_permission(user, REQUIRED_MODULE_PERMISSION)


def can_submit_self(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.submit")


def can_proxy_submit(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.submit_proxy")


def can_view_all_claims(user: dict[str, Any]) -> bool:
    return has_any_permission(user, ["reimbursement.approve", "reimbursement.payment", "reimbursement.reports.view"])


def can_view_own_claims(user: dict[str, Any]) -> bool:
    return has_any_permission(user, ["reimbursement.view_own", "reimbursement.submit"])


def can_view_finance_queue(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.approve")


def can_approve_claims(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.approve")


def can_view_reports(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.reports.view")


def can_close_payment(user: dict[str, Any]) -> bool:
    return has_permission(user, "reimbursement.payment")


def can_view_audit_logs(user: dict[str, Any]) -> bool:
    return has_any_permission(user, ["reimbursement.audit.view", "reimbursement.reports.view"])



def nested_value(record: dict[str, Any], path: str, default: Any = "") -> Any:
    value: Any = record
    for part in path.split("."):
        if not isinstance(value, dict):
            return default
        value = value.get(part, default)
    return value if value is not None else default


def active_employee_options_for_user(user: dict[str, Any] | None, selected_employee_no: str = "") -> str:
    current_entity = current_entity_from_user(user)
    current_entity_id = str(current_entity.get("entity_id", "")).strip()
    current_entity_code = str(current_entity.get("entity_code", "")).strip().lower()
    selected_employee_no = str(selected_employee_no or "").strip()
    options = []
    for employee in load_json_array(EMPLOYEEADMIN_EMPLOYEES_PATH):
        if nested_value(employee, "metadata.deleted", False):
            continue
        status = str(nested_value(employee, "employment.status", "") or employee.get("status", "")).strip().lower()
        if status and status not in {"active", "probation", "on_leave"}:
            continue
        emp_entity_id = str(nested_value(employee, "employment.entity_id", "")).strip()
        emp_entity_code = str(nested_value(employee, "employment.legal_entity", "")).strip().lower()
        if current_entity_id and emp_entity_id and emp_entity_id != current_entity_id:
            continue
        if current_entity_code and not emp_entity_id and emp_entity_code and emp_entity_code != current_entity_code:
            continue
        employee_no = str(employee.get("employee_number") or employee.get("employee_no") or "").strip()
        if not employee_no:
            continue
        name = str(nested_value(employee, "profile.name.display_name", "") or employee.get("display_name", "")).strip()
        dept = str(nested_value(employee, "employment.department", "")).strip()
        label = " - ".join(bit for bit in [employee_no, name, dept] if bit)
        selected = " selected" if employee_no == selected_employee_no else ""
        options.append(f"<option value='{escape(employee_no)}'{selected}>{escape(label)}</option>")
    return "".join(options)


def employee_datalist_html(user: dict[str, Any] | None, list_id: str = "employee-no-options") -> str:
    return f'<datalist id="{escape(list_id)}">{active_employee_options_for_user(user)}</datalist>'


def entity_dropdown_options(user: dict[str, Any] | None, records: list[dict[str, Any]], selected_entity_id: str = "") -> str:
    selected_entity_id = str(selected_entity_id or "").strip()
    entities: dict[str, str] = {}
    current = current_entity_from_user(user)
    current_key = str(current.get("entity_id") or current.get("entity_code") or "").strip()
    if current_key:
        entities[current_key] = " - ".join(bit for bit in [current.get("entity_code", ""), current.get("entity_name", "")] if bit) or current_key
    for record in records:
        key = str(record.get("entity_id") or record.get("entity_code") or "").strip()
        if not key:
            continue
        entities.setdefault(key, " - ".join(bit for bit in [str(record.get("entity_code", "")), str(record.get("entity_name", ""))] if bit) or key)
    options = [f"<option value=''{' selected' if not selected_entity_id else ''}>All / すべて</option>"]
    for key, label in sorted(entities.items(), key=lambda item: item[1]):
        selected = " selected" if key == selected_entity_id else ""
        options.append(f"<option value='{escape(key)}'{selected}>{escape(label)}</option>")
    return "".join(options)

def current_entity_from_user(user: dict[str, Any] | None) -> dict[str, str]:
    if not user:
        return {}
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    user_entity = user.get("entity") if isinstance(user.get("entity"), dict) else {}
    session_entity = session.get("entity") if isinstance(session.get("entity"), dict) else {}
    entity_id = str(user_entity.get("entity_id") or session_entity.get("entity_id") or user.get("entity_id") or "").strip()
    entity_code = str(user_entity.get("entity_code") or session_entity.get("entity_code") or user.get("entity_code") or "").strip()
    entity_name = str(
        user_entity.get("entity_name")
        or user_entity.get("entity_name_en")
        or session_entity.get("entity_name")
        or session_entity.get("entity_name_en")
        or user.get("entity_name")
        or ""
    ).strip()
    if not (entity_id or entity_code):
        return {}
    return {"entity_id": entity_id, "entity_code": entity_code, "entity_name": entity_name}


def apply_current_entity_snapshot(record: dict[str, Any], user: dict[str, Any] | None) -> dict[str, Any]:
    entity = current_entity_from_user(user)
    if not entity:
        return record
    record["entity_id"] = entity.get("entity_id", "")
    record["entity_code"] = entity.get("entity_code", "")
    record["entity_name"] = entity.get("entity_name", "")
    return record


def record_has_entity(record: dict[str, Any]) -> bool:
    return bool(str(record.get("entity_id") or "").strip() or str(record.get("entity_code") or "").strip())


def record_entity_matches(record: dict[str, Any], user: dict[str, Any] | None) -> bool:
    entity = current_entity_from_user(user)
    if not entity:
        return True
    if not record_has_entity(record):
        return is_system_admin(user)
    entity_id = str(entity.get("entity_id", "")).strip()
    record_entity_id = str(record.get("entity_id", "")).strip()
    if entity_id and record_entity_id:
        return entity_id == record_entity_id
    entity_code = str(entity.get("entity_code", "")).strip().lower()
    record_entity_code = str(record.get("entity_code", "")).strip().lower()
    return bool(entity_code and record_entity_code and entity_code == record_entity_code)


def require_record_entity_access(record: dict[str, Any], user: dict[str, Any] | None, label: str = "Record") -> None:
    if not record_entity_matches(record, user):
        raise ValueError(f"{label} belongs to another Entity or is missing Entity metadata.")


def scope_records_to_current_entity(records: list[dict[str, Any]], user: dict[str, Any] | None, include_own_legacy: bool = False) -> list[dict[str, Any]]:
    entity = current_entity_from_user(user)
    if not entity:
        return records
    scoped: list[dict[str, Any]] = []
    for record in records:
        if record_entity_matches(record, user):
            scoped.append(record)
        elif include_own_legacy and not record_has_entity(record) and user and can_view_own_claims(user) and is_own_claim(user, record):
            scoped.append(record)
    return scoped


def employee_identity_from_user(user: dict[str, Any]) -> dict[str, str]:
    employee_no = str(user.get("employee_no") or user.get("employee_number") or user.get("staff_no") or "").strip()
    employee_name = str(user.get("employee_name") or user.get("display_name") or user.get("username") or "").strip()
    department = str(user.get("department") or user.get("department_name") or "").strip()
    return {"employee_no": employee_no, "employee_name": employee_name, "department": department}


def current_employee_no(user: dict[str, Any]) -> str:
    return employee_identity_from_user(user).get("employee_no", "")


def is_own_claim(user: dict[str, Any], claim: dict[str, Any]) -> bool:
    employee_no = current_employee_no(user).lower()
    return bool(employee_no and employee_no == str(claim.get("employee_no", "")).strip().lower())


def can_access_claim(user: dict[str, Any], claim: dict[str, Any]) -> bool:
    if not record_has_entity(claim) and can_view_own_claims(user) and is_own_claim(user, claim):
        return True
    if not record_entity_matches(claim, user):
        return False
    return can_view_all_claims(user) or (can_view_own_claims(user) and is_own_claim(user, claim))


def apply_self_identity_to_form(user: dict[str, Any], form: dict[str, str]) -> dict[str, str]:
    if can_proxy_submit(user):
        return form
    identity = employee_identity_from_user(user)
    employee_no = identity.get("employee_no", "")
    if not employee_no:
        raise ValueError("This account is not linked to an employee number. Please ask Admin to set employee_no before using reimbursement self-service.")
    updated = dict(form)
    updated["employee_no"] = employee_no
    if identity.get("employee_name"):
        updated["employee_name"] = identity["employee_name"]
    if identity.get("department"):
        updated["department"] = identity["department"]
    return updated


OCR_TO_CLAIM_FIELD_MAPPING = [
    ("receipt_date", "expense_date", "Expense Date / 利用日"),
    ("vendor_name", "vendor_name", "Vendor / 店舗・支払先"),
    ("invoice_or_receipt_number", "invoice_or_receipt_number", "Receipt/Invoice No. / 領収書番号"),
    ("qualified_invoice_number", "qualified_invoice_number", "Qualified Invoice No. / 適格請求書登録番号"),
    ("total_amount", "total_amount", "Total incl. tax / 税込金額"),
    ("amount_excluding_tax", "amount_excluding_tax", "Amount excl. tax / 税抜金額"),
    ("tax_amount", "tax_amount", "Tax Amount / 消費税額"),
    ("tax_rate", "tax_rate", "Tax Rate / 税率"),
    ("payment_method", "payment_method", "Payment Method / 支払方法"),
    ("expense_category", "category", "Category / 費用区分"),
    ("employee_name_if_present", "employee_name", "Employee Name / 氏名"),
]

OCR_CONTEXT_FIELDS = ["employee_no", "employee_name", "department", "claim_month", "business_purpose", "notes"]
STANDARD_CLAIM_INPUT_FIELDS = [
    "employee_no",
    "employee_name",
    "department",
    "claim_month",
    "expense_date",
    "category",
    "vendor_name",
    "invoice_or_receipt_number",
    "qualified_invoice_number",
    "is_qualified_invoice",
    "total_amount",
    "amount_excluding_tax",
    "tax_amount",
    "tax_rate",
    "payment_method",
    "business_purpose",
    "notes",
]
MONEY_INPUT_FIELDS = {"total_amount", "amount_excluding_tax", "tax_amount"}
SELECT_INPUT_FIELDS = {"category", "tax_rate", "payment_method", "is_qualified_invoice"}


class TACReimbursementHandler(BaseHTTPRequestHandler):
    server_version = "TACReimbursementWeb/0.1"

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        host = (parsed.hostname or "").lower()
        if host in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS:
            return True
        return parsed.scheme == "https" and host in PUBLIC_ALLOWED_HOSTS and parsed.port in {None, 443}

    def current_user(self) -> dict[str, Any] | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        if not session_cookie:
            return None
        return validate_user_admin_session(session_cookie.value)

    def require_user_admin_access(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.send_response(303)
            self.send_header("Location", f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            self.end_headers()
            return None
        if not has_required_module_access(user):
            self.send_error(403, "This User_admin account does not have permission to access Expense.")
            return None
        return user

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_request(query, self.headers.get("Cookie", ""))
        self._response_lang = lang
        if path == "/health":
            self._send_text("OK")
            return
        user = self.require_user_admin_access()
        if not user:
            return
        user["_lang"] = lang
        user["_current_path"] = path
        if path in {"/finance-review", "/finance-claim"} and not can_view_finance_queue(user):
            self.send_error(403, "Missing reimbursement.approve permission")
            return
        if path.startswith("/finance-report") and not can_view_reports(user):
            self.send_error(403, "Missing reimbursement.reports.view permission")
            return
        if path == "/":
            self._send_html(page("Dashboard", dashboard_html(user), user))
            return
        if path == "/claims":
            self._send_html(page("Claims", claims_html(query, user), user))
            return
        if path == "/finance-review":
            self._send_html(page("Finance Review", finance_review_html(query, user), user))
            return
        if path == "/voucher":
            claim_id = query.get("claim_id", [""])[0].strip()
            record = find_claim(claim_id)
            if not record:
                self.send_error(404, "Claim record not found")
                return
            if not can_access_claim(user, record):
                self.send_error(403, "You can only access your own reimbursement voucher.")
                return
            attachment = record.get("attachment") or {}
            if not attachment:
                self.send_error(404, "Voucher attachment not found")
                return
            try:
                voucher_path = safe_attachment_path(attachment)
            except ValueError as exc:
                self.send_error(404, str(exc))
                return
            content_type = str(attachment.get("content_type") or mimetypes.guess_type(str(voucher_path))[0] or "application/octet-stream")
            filename = safe_filename(str(attachment.get("original_filename") or attachment.get("stored_filename") or "voucher"))
            self._send_file(voucher_path, content_type, filename, download=query.get("download", [""])[0] == "1")
            return
        if path == "/finance-claim":
            claim_id = query.get("id", [""])[0].strip()
            record = find_claim(claim_id)
            if not record:
                self.send_error(404, "Claim record not found")
                return
            try:
                require_record_entity_access(record, user, "Claim")
            except ValueError as exc:
                self.send_error(403, str(exc))
                return
            self._send_html(page("Finance Claim Review", finance_claim_detail_html(record, user), user))
            return
        if path == "/finance-report":
            self._send_html(page("Finance Report", finance_report_html(query, user), user))
            return
        if path == "/finance-report.csv":
            filters = report_filters_from_query(query)
            claims = report_claims(filters, user)
            file_name = report_export_filename(filters)
            append_report_export(filters, claims, file_name, actor=actor_from_user(user), user=user)
            self._send_csv(build_report_csv(claims), file_name)
            return
        if path == "/audit-logs":
            if not can_view_audit_logs(user):
                self.send_error(403, "Missing reimbursement.audit.view permission")
                return
            self._send_html(page("Audit Logs", audit_logs_html(query, user), user))
            return
        if path == "/claim-new":
            if not can_submit_self(user):
                self.send_error(403, "Missing reimbursement.submit permission")
                return
            self._send_html(page("New Claim", claim_form_html(user=user), user))
            return
        if path == "/claim-ocr-new":
            self._send_redirect("/claim-new")
            return
        if path == "/claim-edit":
            claim_id = query.get("id", [""])[0].strip()
            record = find_claim(claim_id)
            if not record:
                self.send_error(404, "Claim record not found")
                return
            if not can_access_claim(user, record):
                self.send_error(403, "You can only edit your own reimbursement claims in the current Entity.")
                return
            if not claim_is_editable(record):
                self._send_html(page("Claim Not Editable", error_message_html("Only Draft or Rejected claims can be edited.") + claims_html({}, user), user), status=400)
                return
            self._send_html(page("Edit Claim", claim_form_html(record=record, mode="edit", user=user), user))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_request(query, self.headers.get("Cookie", ""))
        self._response_lang = lang
        if not self.csrf_origin_allowed():
            self.send_error(403, "Invalid request origin")
            return
        user = self.require_user_admin_access()
        if not user:
            return
        user["_lang"] = lang
        user["_current_path"] = path
        try:
            form, files = self._parse_request_form()
            if path == "/claim-new":
                if not can_submit_self(user):
                    self.send_error(403, "Missing reimbursement.submit permission")
                    return
                form = apply_self_identity_to_form(user, form)
                action = form.get("action", "save_draft").strip() or "save_draft"
                if action == "extract_ocr":
                    saved = create_ocr_draft_from_new_claim_form(files.get("receipt_file"), form, user=user)
                    self._send_html(page("Review OCR-assisted Claim", claim_form_html(record=saved, mode="edit", user=user), user))
                    return
                if action == "submit":
                    form["status"] = "Submitted"
                else:
                    form["status"] = "Draft"
                record = claim_record_from_form(form)
                saved = save_claim(record, files.get("receipt_file"), user=user)
                self._send_redirect("/claims", operation_success_message("Claim", claim_record_label(saved), "saved", actor_from_user(user)))
                return
            if path == "/claim-ocr-new":
                self._send_redirect("/claim-new")
                return
            if path == "/claim-edit":
                if not can_submit_self(user):
                    self.send_error(403, "Missing reimbursement.submit permission")
                    return
                claim_id = form.get("claim_id", "").strip()
                existing = find_claim(claim_id)
                if not existing:
                    raise ValueError("Claim record was not found.")
                if not can_access_claim(user, existing):
                    self.send_error(403, "You can only update your own reimbursement claims.")
                    return
                form = apply_self_identity_to_form(user, form)
                record = claim_update_from_form(existing, form)
                saved = update_claim(record, files.get("receipt_file"), user=user)
                message = no_change_message("Claim", claim_record_label(saved)) if saved.get("_no_changes") else operation_success_message("Claim", claim_record_label(saved), "saved", actor_from_user(user))
                self._send_redirect("/claims", message)
                return
            if path == "/claim-delete":
                if not can_submit_self(user):
                    self.send_error(403, "Missing reimbursement.submit permission")
                    return
                claim_id = form.get("claim_id", "").strip()
                existing = find_claim(claim_id)
                if not existing:
                    raise ValueError("Claim record was not found.")
                if not can_access_claim(user, existing):
                    self.send_error(403, "You can only delete your own reimbursement claims.")
                    return
                deleted = soft_delete_claim(claim_id, user=user)
                message = operation_success_message("Claim", claim_id, "deleted", actor_from_user(user)) if deleted else "Claim record was not found."
                self._send_redirect("/claims", message)
                return
            if path == "/claim-approve":
                if not can_approve_claims(user):
                    self.send_error(403, "Missing reimbursement.approve permission")
                    return
                saved = finance_update_claim(form.get("claim_id", ""), "approve", finance_notes=form.get("finance_notes", ""), actor=actor_from_user(user), user=user)
                self._send_redirect(url_with_lang("/finance-review", lang), operation_success_message("Claim", claim_record_label(saved), "approved", actor_from_user(user)))
                return
            if path == "/claim-reject":
                if not can_approve_claims(user):
                    self.send_error(403, "Missing reimbursement.approve permission")
                    return
                saved = finance_update_claim(form.get("claim_id", ""), "reject", finance_notes=form.get("finance_notes", ""), reject_reason=form.get("reject_reason", ""), actor=actor_from_user(user), user=user)
                self._send_redirect(url_with_lang("/finance-review", lang), operation_success_message("Claim", claim_record_label(saved), "rejected", actor_from_user(user)))
                return
            if path == "/payment-close":
                if not can_close_payment(user):
                    self.send_error(403, "Missing reimbursement.payment permission")
                    return
                filters = payment_close_filters_from_form(form)
                closing = close_payment_batch(filters, form.get("payment_date", ""), form.get("notes", ""), actor=actor_from_user(user), user=user)
                self._send_redirect(url_with_lang("/finance-report", lang, {"claim_month": closing.get("claim_month", ""), "approval_status": "Paid"}), operation_success_message("Payment batch", closing.get("claim_month", ""), "closed", actor_from_user(user)))
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001 - local MVP should show concise operational errors.
            error_html = error_message_html(str(exc))
            if path == "/claim-edit":
                existing = find_claim(form.get("claim_id", "")) if "form" in locals() else None
                self._send_html(page("Claim Input Error", error_html + claim_form_html(record=existing, mode="edit" if existing else "new", user=user), user), status=400)
            elif path == "/claim-ocr-new":
                self._send_redirect("/claim-new")
            elif path in {"/claim-approve", "/claim-reject"}:
                existing = find_claim(form.get("claim_id", "")) if "form" in locals() else None
                body = finance_claim_detail_html(existing, user) if existing else finance_review_html({}, user)
                self._send_html(page("Finance Action Error", error_html + body, user), status=400)
            elif path == "/payment-close":
                self._send_html(page("Payment Close Error", error_html + finance_report_html({}, user), user), status=400)
            else:
                self._send_html(page("Claim Input Error", error_html + claim_form_html(user=user), user), status=400)

    def _parse_request_form(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            fields = cgi.FieldStorage(
                fp=self.rfile,
                headers=self.headers,
                environ={
                    "REQUEST_METHOD": "POST",
                    "CONTENT_TYPE": content_type,
                    "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
                },
            )
            form: dict[str, str] = {}
            files: dict[str, tuple[str, bytes, str]] = {}
            for key in fields.keys():
                item = fields[key]
                if isinstance(item, list):
                    item = item[0]
                if item.filename:
                    content = item.file.read()
                    files[key] = (item.filename, content, item.type or "application/octet-stream")
                else:
                    raw_value = item.value
                    form[key] = raw_value if isinstance(raw_value, str) else raw_value.decode("utf-8", errors="replace")
            return form, files

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}, {}

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

    def _send_html(self, html: str, status: int = 200) -> None:
        flash = self.flash_message()
        if flash:
            html = html.replace("<main>", f"<main><section class='message-strip message-success' role='status'>{escape(flash)}</section>", 1)
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        lang = getattr(self, "_response_lang", DEFAULT_LANG)
        if lang in SUPPORTED_LANGS:
            self.send_header("Set-Cookie", f"{LANG_COOKIE}={lang}; Path=/; SameSite=Lax")
            self.send_header("Content-Language", lang)
        if flash:
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str, status: int = 200) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_redirect(self, location: str, flash: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        lang = getattr(self, "_response_lang", DEFAULT_LANG)
        if lang in SUPPORTED_LANGS:
            self.send_header("Set-Cookie", f"{LANG_COOKIE}={lang}; Path=/; SameSite=Lax")
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_csv(self, csv_text: str, filename: str, status: int = 200) -> None:
        payload = csv_text.encode("utf-8-sig")
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{safe_filename(filename)}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_file(self, path: Path, content_type: str, filename: str, download: bool = False) -> None:
        payload = path.read_bytes()
        disposition = "attachment" if download else "inline"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'{disposition}; filename="{safe_filename(filename)}"')
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def current_user_html(user: dict[str, Any] | None = None) -> str:
    if not user:
        return ""
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    account = str(user.get("username") or user.get("email") or user.get("display_name") or user.get("user_id") or "User")
    display_name = str(user.get("display_name") or account)
    entity_code = str(user.get("entity_code") or session.get("entity", {}).get("entity_code", ""))
    login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
    return f'<span class="current-user-chip" title="Login: {escape(login_time)}"><strong>👤 {escape(account)}</strong><small>{escape(display_name)}{(" · " + escape(entity_code)) if entity_code else ""}</small><small>Login: {escape(login_time)}</small></span>'


def page(title: str, body: str, user: dict[str, Any] | None = None) -> str:
    lang = user_lang(user)
    messages = user_messages(user)
    current_path = str((user or {}).get("_current_path", "/"))
    user_html = current_user_html(user)
    nav_links = [
        ("/", "nav.dashboard"),
        ("/claim-new", "nav.claim_new"),
        ("/claims", "nav.claims"),
    ]
    if user and can_view_finance_queue(user):
        nav_links.append(("/finance-review", "nav.finance_review"))
    if user and can_view_reports(user):
        nav_links.append(("/finance-report", "nav.finance_report"))
    if user and can_view_audit_logs(user):
        nav_links.append(("/audit-logs", "nav.audit_logs"))
    nav_html = "".join(
        f'<a class="{escape("active" if path == current_path else "")}" href="{escape(url_with_lang(path, lang))}">{escape(t(messages, key))}</a>'
        for path, key in nav_links
    )
    language_html = language_switcher_html(lang, current_path)
    portal_html = (
        f'<a class="portal-link" href="{escape(PORTAL_BASE_URL)}" title="{escape(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" '
        f'aria-label="{escape(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{escape(t(messages, "nav.portal"))}</a>'
    )
    return f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} - TAC-reimbursement</title>
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
    .actions {{ margin: 18px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
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
    .status-approved, .status-paid, .status-confirmed {{ background: #dcfce7; color: #166534; }}
    .status-rejected, .status-warning, .status-draft-review {{ background: #fef3c7; color: #92400e; }}
    .status-failed, .status-error {{ background: #fee2e2; color: #991b1b; }}
    .notice, .message-strip {{ border-left: 4px solid var(--blue); background: #eff6ff; padding: 12px 14px; border-radius: 8px; }}
    .message-warning {{ border-left-color: var(--amber); background: #fffbeb; }}
    .message-success {{ border-left-color: var(--green); background: #ecfdf5; }}
    .message-error {{ border-left-color: var(--red); background: #fef2f2; }}
    .message-info {{ border-left-color: var(--blue); background: #eff6ff; }}
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
    .table-scroll {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; background: white; }}
    input:focus, select:focus, textarea:focus {{ outline: 3px solid rgba(31, 111, 235, 0.18); border-color: var(--blue); }}
    @media (max-width: 720px) {{
      header {{ padding: 16px 18px; }}
      nav {{ flex-wrap: nowrap; overflow-x: auto; -webkit-overflow-scrolling: touch; align-items: center; gap: 8px; padding: 8px 12px; scrollbar-width: thin; }}
      nav a, .language-switcher {{ flex: 0 0 auto; min-height: 34px; white-space: nowrap; }}
      .language-switcher {{ margin-left: 6px; flex-direction: row; align-items: center; }}
      .language-switcher .pill, .language-switcher .button {{ width: auto; min-height: 30px; padding: 0 9px; }}
      main {{ padding: 18px 12px 36px; }}
      .grid, .form-grid, .sap-readonly-grid {{ grid-template-columns: 1fr; }}
      .sap-page-header {{ padding: 16px; }}
      .sap-object-meta {{ margin-top: 12px; }}
      .actions, .sap-toolbar {{ align-items: stretch; flex-direction: column; justify-content: stretch; }}
      .actions .button, .actions button, .sap-toolbar .button, .sap-toolbar button {{ width: 100%; text-align: center; }}
      table {{ display: block; overflow-x: auto; min-width: 760px; }}
      input, select, textarea {{ min-height: 44px; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(t(messages, 'app.title'))}</h1>
    <p>{escape(t(messages, 'app.subtitle'))}</p>
  </header>
  <nav>{portal_html}{nav_html}<span class="language-switcher">{user_html}{language_html}</span></nav>
  <main>{body}</main>
</body>
</html>"""


def dashboard_html(user: dict[str, Any]) -> str:
    lang = user_lang(user)
    all_claims = scope_records_to_current_entity(load_claims(), user, include_own_legacy=True)
    claims = all_claims if can_view_all_claims(user) else [claim for claim in all_claims if is_own_claim(user, claim)]
    submitted = [claim for claim in claims if claim.get("status") == "Submitted"]
    approved = [claim for claim in claims if claim.get("status") == "Approved"]
    rejected = [claim for claim in claims if claim.get("status") == "Rejected"]
    paid = [claim for claim in claims if claim.get("status") == "Paid"]
    totals = calculate_claim_totals(claims)
    finance_review_action = f'<a class="button secondary" href="{escape(url_with_lang("/finance-review", lang))}">{escape(ui_text(user, "打开财务审批", "財務承認を開く", "Open Finance Review"))}</a>' if can_view_finance_queue(user) else ""
    finance_report_action = f'<a class="button secondary" href="{escape(url_with_lang("/finance-report", lang))}">{escape(ui_text(user, "打开月度报表", "月次レポートを開く", "Open Finance Report"))}</a>' if can_view_reports(user) else ""
    return f"""
<section class="sap-page-header">
  <p class="muted">{escape(ui_text(user, "费用报销", "経費精算", "Expense"))}</p>
  <h2>{escape(ui_text(user, "费用报销仪表盘", "経費精算ダッシュボード", "Reimbursement Dashboard"))}</h2>
  <p class="message-strip message-info">{escape(ui_text(user, "员工可手工录入或上传票据进行 OCR 辅助预填；普通员工默认只查看本人报销记录。", "従業員は手入力または領収書・請求書OCR補助で申請できます。一般ユーザーは本人の申請のみ表示されます。", "Employees create reimbursement claims with manual entry or OCR-assisted receipt/invoice extraction. Ordinary users see only their own reimbursement records."))}</p>
  <div class="sap-object-meta">
    <span class="status-badge">{len(claims)} {escape(ui_text(user, "条", "件", "total"))}</span>
    {claim_status_badge('Submitted')}: {len(submitted)}
    {claim_status_badge('Approved')}: {len(approved)}
    {claim_status_badge('Paid')}: {len(paid)}
  </div>
</section>
<section class="grid">
  <div class="card"><h3>{escape(ui_text(user, "申请总数", "申請件数", "Total Claims"))}</h3><div class="metric">{len(claims)}</div><p class="muted">{escape(ui_text(user, "有效报销申请。", "有効な経費申請。", "Active reimbursement claims."))}</p></div>
  <div class="card"><h3>{escape(ui_text(user, "已提交", "申請済", "Submitted"))}</h3><div class="metric">{len(submitted)}</div><p class="muted">{escape(ui_text(user, "等待财务审批。", "財務承認待ち。", "Waiting for finance approval."))}</p></div>
  <div class="card"><h3>{escape(ui_text(user, "已批准", "承認済", "Approved"))}</h3><div class="metric">{len(approved)}</div><p class="muted">{escape(ui_text(user, "可进入报表和付款关闭。", "レポートと支払締めの対象。", "Ready for report and payment close."))}</p></div>
  <div class="card"><h3>{escape(ui_text(user, "已驳回", "差戻し", "Rejected"))}</h3><div class="metric">{len(rejected)}</div><p class="muted">{escape(ui_text(user, "员工可修正后重新提交。", "従業員が修正して再申請できます。", "Editable by employees for correction."))}</p></div>
  <div class="card"><h3>{escape(ui_text(user, "已付款", "支払済", "Paid"))}</h3><div class="metric">{len(paid)}</div><p class="muted">{escape(ui_text(user, "付款关闭完成。", "支払締め済み。", "Closed for payment."))}</p></div>
  <div class="card"><h3>{escape(ui_text(user, "合计金额", "合計金額", "Total Amount"))}</h3><div class="metric">{money(totals['total_amount'])}</div><p class="muted">{escape(ui_text(user, "当前可见记录的合计。", "表示中の有効申請合計。", "Visible active claims."))}</p></div>
</section>
<section class="sap-section" style="margin-top: 18px;">
  <h2>{escape(ui_text(user, "新建申请：支持 OCR 辅助输入", "OCR対応の経費申請", "New Claim with optional OCR input"))}</h2>
  <p class="message-strip message-info">{escape(ui_text(user, "请在标准费用申请表中手工录入，或上传票据将 OCR 草稿值预填到原字段；提交前必须由员工确认。", "標準の経費申請フォームで手入力、または領収書・請求書をアップロードしてOCR候補を元の項目へ反映し、申請前に確認します。", "Employees create claims from the standard New Claim form. They can manually enter reimbursement details or upload a receipt/invoice in the same form to extract draft OCR values into the original fields before review and submission."))}</p>
  <div class="actions">
    <a class="button" href="{escape(url_with_lang('/claim-new', lang))}">{escape(ui_text(user, "新建申请 / OCR 辅助录入", "経費申請 / OCR補助入力", "New Claim / OCR-assisted Entry"))}</a>
    <a class="button secondary" href="{escape(url_with_lang('/claims', lang))}">{escape(ui_text(user, "打开申请列表", "申請一覧を開く", "Open Claims"))}</a>
    {finance_review_action}
    {finance_report_action}
  </div>
</section>
"""


def claims_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = {key: query.get(key, [""])[0].strip() for key in ["entity_id", "employee_no", "claim_month", "status"]}
    scoped_claims = scope_records_to_current_entity(load_claims(), user, include_own_legacy=True)
    if not can_view_all_claims(user):
        filters["employee_no"] = current_employee_no(user)
        claims = filter_claims(scoped_claims, filters) if filters["employee_no"] else []
    else:
        claims = filter_claims(scoped_claims, filters)
    totals = calculate_claim_totals(claims)
    rows_html = claim_table_rows(claims, user)
    status_options = "<option value=''>All / すべて</option>" + select_options(CLAIM_STATUSES, filters["status"])
    entity_options = entity_dropdown_options(user, scoped_claims, filters["entity_id"])
    employee_datalist = employee_datalist_html(user)
    return f"""
<section class="panel">
  <h2>Claims / 経費申請一覧</h2>
  <p class="notice">Manual entry MVP: enter claim data, attach receipt/invoice, save Draft or Submit for finance review.</p>
  <form method="get" action="/claims">
    {employee_datalist}
    <div class="form-grid">
      <div><label>Entity / 法人</label><select name="entity_id">{entity_options}</select></div>
      <div><label>Employee No. / 社員No.</label><input name="employee_no" list="employee-no-options" value="{escape(filters['employee_no'])}" placeholder="E001"></div>
      <div><label>Claim Month / 精算月</label><input name="claim_month" value="{escape(filters['claim_month'])}" placeholder="2026-06"></div>
      <div><label>Status / 状態</label><select name="status">{status_options}</select></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索</button>
      <a class="button secondary" href="/claims">Clear / クリア</a>
      <a class="button" href="/claim-new">New Claim / 経費申請</a>
    </div>
  </form>
</section>
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>Filtered rows</h3><div class="metric">{len(claims)}</div></div>
  <div class="card"><h3>Total incl. tax / 税込合計</h3><div class="metric">{money(totals['total_amount'])}</div></div>
  <div class="card"><h3>Excl. tax / 税抜合計</h3><div class="metric">{money(totals['amount_excluding_tax'])}</div></div>
  <div class="card"><h3>Tax / 消費税</h3><div class="metric">{money(totals['tax_amount'])}</div></div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Claim records / 申請レコード</h3>
  <table>
    <thead><tr><th>Claim No.</th><th>Employee</th><th>Month / Date</th><th>Category</th><th>Vendor</th><th class="num">Excl. Tax</th><th class="num">Tax</th><th class="num">Total</th><th>Attachment</th><th>OCR</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>
"""


def attachment_link_html(record: dict[str, Any]) -> str:
    attachment = record.get("attachment") or {}
    if not attachment:
        return "<span class='muted'>-</span>"
    claim_id = str(record.get("claim_id", "")).strip()
    if not claim_id:
        return escape(str(attachment.get("original_filename") or attachment.get("stored_filename") or "-"))
    label = str(attachment.get("original_filename") or attachment.get("stored_filename") or "Voucher")
    stored = str(attachment.get("stored_filename") or "")
    open_href = "/voucher?" + urlencode({"claim_id": claim_id})
    download_href = "/voucher?" + urlencode({"claim_id": claim_id, "download": "1"})
    stored_note = f"<br><span class='muted'>{escape(stored)}</span>" if stored else ""
    return f"<a href='{escape(open_href)}' target='_blank' rel='noopener'>{escape(label)}</a>{stored_note}<br><a class='muted' href='{escape(download_href)}'>Download</a>"


def claim_table_rows(claims: list[dict[str, Any]], user: dict[str, Any]) -> str:
    if not claims:
        return "<tr><td colspan='12' class='muted'>No claims saved yet.</td></tr>"
    rows = []
    for claim in sorted(claims, key=lambda item: (str(item.get("claim_month", "")), str(item.get("claim_no", ""))), reverse=True):
        claim_id = escape(str(claim.get("claim_id", "")))
        edit_link = f"<a class='button secondary' href='/claim-edit?id={claim_id}'>Edit</a>" if claim_id and claim_is_editable(claim) else ""
        finance_link = f"<a class='button' href='/finance-claim?id={claim_id}'>Finance Review</a>" if claim_id and claim.get("status") == "Submitted" and has_permission(user, "reimbursement.approve") else ""
        delete_form = f"<form method='post' action='/claim-delete'><input type='hidden' name='claim_id' value='{claim_id}'><button class='danger' type='submit'>Soft Delete</button></form>" if claim_id and claim_is_editable(claim) else ""
        action_html = f"<div class='actions'>{edit_link}{finance_link}{delete_form}</div>" if edit_link or finance_link or delete_form else "<span class='muted'>Locked by status</span>"
        attachment_html = attachment_link_html(claim)
        rows.append(f"""
        <tr>
          <td>{value(claim, 'claim_no')}</td>
          <td>{value(claim, 'employee_no')}<br><span class="muted">{value(claim, 'employee_name')}</span></td>
          <td>{value(claim, 'claim_month')}<br><span class="muted">{value(claim, 'expense_date')}</span></td>
          <td>{category_label(str(claim.get('category', '')))}</td>
          <td>{value(claim, 'vendor_name')}</td>
          <td class="num">{money(claim.get('amount_excluding_tax', 0))}</td>
          <td class="num">{money(claim.get('tax_amount', 0))}<br><span class="muted">{value(claim, 'tax_rate')}</span></td>
          <td class="num"><strong>{money(claim.get('total_amount', 0))}</strong></td>
          <td>{attachment_html}</td>
          <td>{ocr_status_badge(str(claim.get('ocr_status', 'not_run')))}</td>
          <td>{claim_status_badge(str(claim.get('status', '')))}</td>
          <td>{action_html}</td>
        </tr>
        """)
    return "".join(rows)


def finance_review_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = {key: query.get(key, [""])[0].strip() for key in ["entity_id", "employee_no", "claim_month", "status"]}
    if "status" not in query:
        filters["status"] = "Submitted"
    scoped_claims = scope_records_to_current_entity(load_claims(), user, include_own_legacy=False)
    claims = filter_claims(scoped_claims, filters)
    totals = calculate_claim_totals(claims)
    status_options = "<option value=''>All / すべて</option>" + select_options(CLAIM_STATUSES, filters["status"])
    entity_options = entity_dropdown_options(user, scoped_claims, filters["entity_id"])
    employee_datalist = employee_datalist_html(user)
    return f"""
<section class="sap-page-header">
  <p class="muted">Finance Review / 財務承認</p>
  <h2>Finance Review / 財務承認</h2>
  <p class="message-strip message-warning">Finance reviews current-Entity submitted claims, approves valid claims, or rejects claims with a required correction reason. Actions are recorded with the current User_admin actor.</p>
  <div class="sap-object-meta">
    {claim_status_badge(filters['status'] or 'Submitted')}
    <span class="status-badge">{len(claims)} filtered</span>
  </div>
</section>
<section class="sap-section">
  <form method="get" action="/finance-review">
    {employee_datalist}
    <div class="form-grid">
      <div><label>Entity / 法人</label><select name="entity_id">{entity_options}</select></div>
      <div><label>Employee No. / 社員No.</label><input name="employee_no" list="employee-no-options" value="{escape(filters['employee_no'])}" placeholder="E001"></div>
      <div><label>Claim Month / 精算月</label><input name="claim_month" value="{escape(filters['claim_month'])}" placeholder="2026-06"></div>
      <div><label>Status / 状態</label><select name="status">{status_options}</select></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索</button>
      <a class="button secondary" href="/finance-review">Submitted Queue</a>
      <a class="button secondary" href="/claims">Employee Claims</a>
    </div>
  </form>
</section>
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>Filtered rows</h3><div class="metric">{len(claims)}</div></div>
  <div class="card"><h3>Total incl. tax / 税込合計</h3><div class="metric">{money(totals['total_amount'])}</div></div>
  <div class="card"><h3>Tax / 消費税</h3><div class="metric">{money(totals['tax_amount'])}</div></div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Finance claim queue / 財務承認待ち</h3>
  <table>
    <thead><tr><th>Claim No.</th><th>Employee</th><th>Month / Date</th><th>Category</th><th>Vendor</th><th class="num">Total</th><th>Attachment</th><th>OCR</th><th>Status</th><th>Action</th></tr></thead>
    <tbody>{finance_claim_rows(claims, user)}</tbody>
  </table>
</section>
"""


def finance_claim_rows(claims: list[dict[str, Any]], user: dict[str, Any]) -> str:
    if not claims:
        return "<tr><td colspan='10' class='muted'>No finance review claims found.</td></tr>"
    rows = []
    for claim in sorted(claims, key=lambda item: (str(item.get("claim_month", "")), str(item.get("claim_no", ""))), reverse=True):
        claim_id = escape(str(claim.get("claim_id", "")))
        attachment_html = attachment_link_html(claim)
        rows.append(f"""
        <tr>
          <td>{value(claim, 'claim_no')}</td>
          <td>{value(claim, 'employee_no')}<br><span class="muted">{value(claim, 'employee_name')}</span></td>
          <td>{value(claim, 'claim_month')}<br><span class="muted">{value(claim, 'expense_date')}</span></td>
          <td>{category_label(str(claim.get('category', '')))}</td>
          <td>{value(claim, 'vendor_name')}</td>
          <td class="num"><strong>{money(claim.get('total_amount', 0))}</strong><br><span class="muted">Tax {money(claim.get('tax_amount', 0))}</span></td>
          <td>{attachment_html}</td>
          <td>{ocr_status_badge(str(claim.get('ocr_status', 'not_run')))}</td>
          <td>{claim_status_badge(str(claim.get('status', '')))}</td>
          <td><a class="button" href="{escape(url_with_lang('/finance-claim', user_lang(user), {'id': claim_id}))}">Review</a></td>
        </tr>
        """)
    return "".join(rows)


def finance_claim_detail_html(record: dict[str, Any], user: dict[str, Any]) -> str:
    attachment_html = attachment_link_html(record)
    can_review = record.get("status") == "Submitted" and record.get("record_status", "Active") != "Deleted"
    action_html = "<p class='muted'>Finance action unavailable for current status.</p>"
    if can_review:
        action_html = f"""
        <div class="grid">
          <div class="card">
            <h3>Approve / 承認</h3>
            <form method="post" action="{escape(url_with_lang('/claim-approve', user_lang(user)))}">
              <input type="hidden" name="claim_id" value="{value(record, 'claim_id')}">
              <label>Finance Notes / 財務メモ</label>
              <textarea name="finance_notes" placeholder="Optional approval note">{value(record, 'finance_notes')}</textarea>
              <div class="actions"><button class="success" type="submit">Approve / 承認</button></div>
            </form>
          </div>
          <div class="card">
            <h3>Reject / 差戻し</h3>
            <form method="post" action="{escape(url_with_lang('/claim-reject', user_lang(user)))}">
              <input type="hidden" name="claim_id" value="{value(record, 'claim_id')}">
              <label>Finance Notes / 財務メモ</label>
              <textarea name="finance_notes" placeholder="Optional finance note">{value(record, 'finance_notes')}</textarea>
              <label>Reject Reason / 差戻し理由</label>
              <textarea name="reject_reason" required placeholder="Required reason for employee correction">{value(record, 'reject_reason')}</textarea>
              <div class="actions"><button class="danger" type="submit">Reject / 差戻し</button></div>
            </form>
          </div>
        </div>
        """
    return f"""
<section class="sap-page-header">
  <p class="muted">Finance Review / 財務承認</p>
  <h2>Finance Claim Review / 財務申請確認</h2>
  <p class="message-strip message-info">Review claim details, receipt/invoice attachment, tax fields, business purpose, and OCR status before approving or rejecting.</p>
  <div class="sap-object-meta">
    {claim_status_badge(str(record.get('status', '')))}
    {ocr_status_badge(str(record.get('ocr_status', 'not_run')))}
    <span class="status-badge">{value(record, 'claim_no')}</span>
  </div>
  <div class="actions">
    <a class="button ghost" href="{escape(url_with_lang('/finance-review', user_lang(user)))}">Back to Finance Review</a>
    <a class="button secondary" href="{escape(url_with_lang('/claims', user_lang(user)))}">Open Claims</a>
  </div>
</section>
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>Claim No.</h3><p>{value(record, 'claim_no')}</p></div>
  <div class="card"><h3>Status</h3><p>{claim_status_badge(str(record.get('status', '')))}</p></div>
  <div class="card"><h3>Employee</h3><p>{value(record, 'employee_no')} - {value(record, 'employee_name')}<br><span class="muted">{value(record, 'department')}</span></p></div>
  <div class="card"><h3>Total</h3><p>{money(record.get('total_amount', 0))}</p></div>
  <div class="card"><h3>OCR</h3><p>{ocr_status_badge(str(record.get('ocr_status', 'not_run')))}</p></div>
  <div class="card"><h3>Attachment</h3><p>{attachment_html}</p></div>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Claim details / 申請詳細</h3>
  <table><tbody>
    <tr><th>Claim Month</th><td>{value(record, 'claim_month')}</td><th>Expense Date</th><td>{value(record, 'expense_date')}</td></tr>
    <tr><th>Category</th><td>{category_label(str(record.get('category', '')))}</td><th>Vendor</th><td>{value(record, 'vendor_name')}</td></tr>
    <tr><th>Receipt/Invoice No.</th><td>{value(record, 'invoice_or_receipt_number')}</td><th>Qualified Invoice No.</th><td>{value(record, 'qualified_invoice_number')}</td></tr>
    <tr><th>Amount excl. tax</th><td>{money(record.get('amount_excluding_tax', 0))}</td><th>Tax Amount</th><td>{money(record.get('tax_amount', 0))}</td></tr>
    <tr><th>Tax Rate</th><td>{value(record, 'tax_rate')}</td><th>Payment Method</th><td>{value(record, 'payment_method')}</td></tr>
    <tr><th>Business Purpose</th><td colspan="3">{value(record, 'business_purpose')}</td></tr>
    <tr><th>Employee Notes</th><td colspan="3">{value(record, 'notes')}</td></tr>
    <tr><th>Finance Notes</th><td colspan="3">{value(record, 'finance_notes')}</td></tr>
    <tr><th>Reject Reason</th><td colspan="3">{value(record, 'reject_reason')}</td></tr>
    <tr><th>Submitted</th><td>{value(record, 'submitted_at')}</td><th>Approved</th><td>{value(record, 'approved_at')} {value(record, 'approved_by')}</td></tr>
    <tr><th>Rejected</th><td>{value(record, 'rejected_at')} {value(record, 'rejected_by')}</td><th>Paid</th><td>{value(record, 'paid_at')}</td></tr>
  </tbody></table>
</section>
{ocr_draft_review_html(record) if record.get('ocr_status', 'not_run') != 'not_run' else ''}
<section class="panel" style="margin-top: 18px;">
  <h3>Finance action / 財務処理</h3>
  {action_html}
</section>
{approval_logs_html(str(record.get('claim_id', '')))}
"""


def approval_logs_html(claim_id: str) -> str:
    logs = approval_logs_for_claim(claim_id)
    if not logs:
        rows = "<tr><td colspan='6' class='muted'>No approval logs yet.</td></tr>"
    else:
        rows = "".join(
            f"<tr><td>{escape(str(log.get('action_at', '')))}</td><td>{escape(str(log.get('action', '')))}</td><td>{escape(str(log.get('actor', '')))}</td><td>{escape(str(log.get('before_status', '')))}</td><td>{escape(str(log.get('after_status', '')))}</td><td>{escape(str(log.get('notes', '')))}</td></tr>"
            for log in sorted(logs, key=lambda item: str(item.get("action_at", "")), reverse=True)
        )
    return f"""
<section class="panel wide" style="margin-top: 18px;">
  <h3>Approval history / 承認履歴</h3>
  <table>
    <thead><tr><th>Action At</th><th>Action</th><th>Actor</th><th>Before</th><th>After</th><th>Notes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


def audit_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["module", "record_id", "action", "user"]}


def filter_audit_logs(records: list[dict[str, Any]], filters: dict[str, str], user: dict[str, Any]) -> list[dict[str, Any]]:
    filtered = scope_records_to_current_entity(records, user, include_own_legacy=False)
    module_filter = filters.get("module", "").lower()
    record_id_filter = filters.get("record_id", "").lower()
    action_filter = filters.get("action", "").lower()
    user_filter = filters.get("user", "").lower()
    if module_filter:
        filtered = [record for record in filtered if module_filter in str(record.get("module", "")).lower()]
    if record_id_filter:
        filtered = [record for record in filtered if record_id_filter in str(record.get("record_id", "")).lower()]
    if action_filter:
        filtered = [record for record in filtered if action_filter in str(record.get("action", "")).lower()]
    if user_filter:
        filtered = [record for record in filtered if user_filter in str(record.get("user", "")).lower()]
    return filtered


def audit_json_block(value_to_show: Any) -> str:
    payload = json.dumps(value_to_show if value_to_show is not None else {}, ensure_ascii=False, indent=2)
    return f"<details><summary>JSON</summary><pre>{escape(payload)}</pre></details>"


def audit_log_table_rows(records: list[dict[str, Any]]) -> str:
    if not records:
        return "<tr><td colspan='8' class='muted'>No audit logs found.</td></tr>"
    rows = []
    for record in sorted(records, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:200]:
        rows.append(f"""
        <tr>
          <td>{escape(str(record.get('timestamp', '')))}</td>
          <td>{escape(str(record.get('module', '')))}</td>
          <td>{escape(str(record.get('action', '')))}</td>
          <td>{escape(str(record.get('record_id', '')))}</td>
          <td>{escape(str(record.get('user', '')))}</td>
          <td>{escape(str(record.get('entity_code') or record.get('entity_id') or '-'))}</td>
          <td>{audit_json_block(record.get('before_value', {}))}</td>
          <td>{audit_json_block(record.get('after_value', {}))}</td>
        </tr>
        """)
    return "".join(rows)


def audit_logs_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = audit_filters_from_query(query)
    all_logs = load_audit_logs()
    logs = filter_audit_logs(all_logs, filters, user)
    lang = user_lang(user)
    return f"""
<section class="sap-page-header">
  <p class="muted">Audit / 監査 / 审计</p>
  <h2>Audit Logs / 監査ログ / 审计日志</h2>
  <p class="message-strip message-info">Read-only standard audit trail for Reimbursement. Rows are scoped to the current User_admin Entity unless the user is System Admin.</p>
  <div class="sap-object-meta">
    <span class="status-badge">{len(logs)} filtered</span>
    <span class="status-badge">{len(all_logs)} total</span>
    <span class="status-badge">{escape(str(current_entity_from_user(user).get('entity_code') or 'All/No Entity'))}</span>
  </div>
</section>
<section class="sap-section">
  <form method="get" action="/audit-logs">
    <input type="hidden" name="lang" value="{escape(lang)}">
    <div class="form-grid">
      <div><label>Module / 模块</label><input name="module" value="{escape(filters['module'])}" placeholder="reimbursement.claim"></div>
      <div><label>Record ID / 记录ID</label><input name="record_id" value="{escape(filters['record_id'])}" placeholder="claim-..."></div>
      <div><label>Action / 操作</label><input name="action" value="{escape(filters['action'])}" placeholder="submit / approve"></div>
      <div><label>User / 用户</label><input name="user" value="{escape(filters['user'])}" placeholder="actor"></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索 / 搜索</button>
      <a class="button secondary" href="{escape(url_with_lang('/audit-logs', lang))}">Clear / クリア / 清除</a>
    </div>
  </form>
</section>
<section class="panel wide" style="margin-top: 18px;">
  <h3>Audit rows / 監査明細 / 审计明细</h3>
  <table>
    <thead><tr><th>Timestamp</th><th>Module</th><th>Action</th><th>Record ID</th><th>User</th><th>Entity</th><th>Before</th><th>After</th></tr></thead>
    <tbody>{audit_log_table_rows(logs)}</tbody>
  </table>
</section>
"""


def finance_report_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = report_filters_from_query(query)
    claims = report_claims(filters, user)
    summaries = calculate_report_summaries(claims)
    export_query = urlencode({key: value for key, value in filters.items() if value})
    export_href = url_with_lang("/finance-report.csv", user_lang(user), filters)
    status_options = select_options([(status, label) for status, label in CLAIM_STATUSES if status in {"Approved", "Paid"}], filters["approval_status"])
    category_options = "<option value=''>All / すべて</option>" + select_options(CATEGORIES, filters["category"])
    tax_options = "<option value=''>All / すべて</option>" + select_options([(rate, rate) for rate in TAX_RATES], filters["tax_rate"])
    payment_options = "<option value=''>All / すべて</option>" + select_options(PAYMENT_METHODS, filters["payment_method"])
    scoped_claims = scope_records_to_current_entity(load_claims(), user, include_own_legacy=False)
    entity_options = entity_dropdown_options(user, scoped_claims, filters["entity_id"])
    employee_datalist = employee_datalist_html(user)
    return f"""
<section class="sap-page-header">
  <p class="muted">Finance Report / 月次レポート</p>
  <h2>Month-end Reimbursement Report / 月次経費精算レポート</h2>
  <p class="message-strip message-info">Initial month-end report uses approved active claims by default. CSV exports are recorded in local export history for audit.</p>
  <div class="sap-object-meta">
    {claim_status_badge(filters['approval_status'] or 'Approved')}
    <span class="status-badge">{summaries['claim_count']} claim(s)</span>
    <span class="status-badge">{money(summaries['total_amount'])}</span>
  </div>
</section>
<section class="sap-section">
  <form method="get" action="/finance-report"><input type="hidden" name="lang" value="{escape(user_lang(user))}">
    {employee_datalist}
    <div class="form-grid">
      <div><label>Entity / 法人</label><select name="entity_id">{entity_options}</select></div>
      <div><label>Claim Month / 精算月</label><input name="claim_month" value="{escape(filters['claim_month'])}" placeholder="2026-06"></div>
      <div><label>Employee No. / 社員No.</label><input name="employee_no" list="employee-no-options" value="{escape(filters['employee_no'])}" placeholder="E001"></div>
      <div><label>Department / 部門</label><input name="department" value="{escape(filters['department'])}" placeholder="Finance"></div>
      <div><label>Approval Status / 承認状態</label><select name="approval_status">{status_options}</select></div>
      <div><label>Category / 費用区分</label><select name="category">{category_options}</select></div>
      <div><label>Tax Rate / 税率</label><select name="tax_rate">{tax_options}</select></div>
      <div><label>Payment Method / 支払方法</label><select name="payment_method">{payment_options}</select></div>
    </div>
    <div class="actions">
      <button type="submit">Filter / 検索</button>
      <a class="button secondary" href="{escape(url_with_lang('/finance-report', user_lang(user)))}">Clear / クリア</a>
      <a class="button" href="{export_href}">Export CSV / CSV出力</a>
    </div>
  </form>
</section>
<section class="grid" style="margin-top: 18px;">
  <div class="card"><h3>Claim Count / 件数</h3><div class="metric">{summaries['claim_count']}</div></div>
  <div class="card"><h3>Total Amount / 税込合計</h3><div class="metric">{money(summaries['total_amount'])}</div></div>
  <div class="card"><h3>Total Tax / 消費税合計</h3><div class="metric">{money(summaries['total_tax_amount'])}</div></div>
</section>
<section class="grid" style="margin-top: 18px;">
  {report_summary_table_html('By Employee / 社員別', summaries['by_employee'])}
  {report_summary_table_html('By Category / 費用区分別', summaries['by_category'])}
  {report_summary_table_html('By Tax Rate / 税率別', summaries['by_tax_rate'])}
  {report_summary_table_html('By Payment Method / 支払方法別', summaries['by_payment_method'])}
</section>
{payment_close_panel_html(filters, claims, user)}
<section class="panel wide" style="margin-top: 18px;">
  <h3>{escape(filters['approval_status'])} claim rows / 明細</h3>
  <table>
    <thead><tr><th>Claim No.</th><th>Employee</th><th>Department</th><th>Month / Date</th><th>Category</th><th>Vendor</th><th class="num">Total</th><th class="num">Tax</th><th>Tax Rate</th><th>Payment</th><th>Approved</th></tr></thead>
    <tbody>{report_claim_rows_html(claims)}</tbody>
  </table>
</section>
{report_export_history_html(user=user)}
"""


def report_summary_table_html(title: str, rows: list[dict[str, Any]]) -> str:
    if not rows:
        body = "<tr><td colspan='4' class='muted'>No rows.</td></tr>"
    else:
        body = "".join(
            f"<tr><td>{escape(str(row['label']))}</td><td class='num'>{row['claim_count']}</td><td class='num'>{money(row['total_amount'])}</td><td class='num'>{money(row['tax_amount'])}</td></tr>"
            for row in rows
        )
    return f"""
  <div class="card wide">
    <h3>{escape(title)}</h3>
    <table>
      <thead><tr><th>Group</th><th class="num">Count</th><th class="num">Total</th><th class="num">Tax</th></tr></thead>
      <tbody>{body}</tbody>
    </table>
  </div>
"""


def report_claim_rows_html(claims: list[dict[str, Any]]) -> str:
    if not claims:
        return "<tr><td colspan='11' class='muted'>No approved report claims found.</td></tr>"
    rows = []
    for claim in claims:
        rows.append(f"""
        <tr>
          <td>{value(claim, 'claim_no')}</td>
          <td>{value(claim, 'employee_no')}<br><span class="muted">{value(claim, 'employee_name')}</span></td>
          <td>{value(claim, 'department')}</td>
          <td>{value(claim, 'claim_month')}<br><span class="muted">{value(claim, 'expense_date')}</span></td>
          <td>{category_label(str(claim.get('category', '')))}</td>
          <td>{value(claim, 'vendor_name')}</td>
          <td class="num">{money(claim.get('total_amount', 0))}</td>
          <td class="num">{money(claim.get('tax_amount', 0))}</td>
          <td>{value(claim, 'tax_rate')}</td>
          <td>{value(claim, 'payment_method')}</td>
          <td>{value(claim, 'approved_at')}<br><span class="muted">{value(claim, 'approved_by')}</span></td>
        </tr>
        """)
    return "".join(rows)


def payment_close_panel_html(filters: dict[str, str], claims: list[dict[str, Any]], user: dict[str, Any]) -> str:
    claim_month = filters.get("claim_month", "")
    if not claim_month:
        return """
<section class="panel" style="margin-top: 18px;">
  <h3>Payment Closing / 支払締め</h3>
  <p class="muted">Select a Claim Month before closing payment.</p>
</section>
""" + payment_closing_history_html(user=user)
    existing = payment_closing_for_month(claim_month, user)
    if existing:
        return f"""
<section class="panel" style="margin-top: 18px;">
  <h3>Payment Closing / 支払締め</h3>
  <p class="notice">Claim Month {escape(claim_month)} is already payment-closed.</p>
  <div class="grid">
    <div class="card"><h3>Payment Date</h3><p>{escape(str(existing.get('payment_date', '')))}</p></div>
    <div class="card"><h3>Closed By</h3><p>{escape(str(existing.get('closed_by', '')))}</p></div>
    <div class="card"><h3>Closed At</h3><p>{escape(str(existing.get('closed_at', '')))}</p></div>
    <div class="card"><h3>Claim Count</h3><p>{escape(str(existing.get('claim_count', 0)))}</p></div>
    <div class="card"><h3>Total Amount</h3><p>{money(existing.get('total_amount', 0))}</p></div>
  </div>
</section>
""" + payment_closing_history_html(user=user)
    if filters.get("approval_status") != "Approved":
        return payment_closing_history_html(user=user)
    if not claims:
        return f"""
<section class="panel" style="margin-top: 18px;">
  <h3>Payment Closing / 支払締め</h3>
  <p class="muted">No Approved claims match the current filters for {escape(claim_month)}.</p>
</section>
""" + payment_closing_history_html(user=user)
    totals = calculate_claim_totals(claims)
    hidden_fields = "".join(f'<input type="hidden" name="{escape(key)}" value="{escape(value)}">' for key, value in filters.items() if key != "approval_status")
    return f"""
<section class="panel" style="margin-top: 18px;">
  <h3>Payment Closing / 支払締め</h3>
  <p class="notice">This marks the listed Approved claims as Paid and locks Claim Month {escape(claim_month)} from further changes. CSV export history remains separate from payment closing.</p>
  <div class="grid">
    <div class="card"><h3>Claims to mark Paid</h3><div class="metric">{len(claims)}</div></div>
    <div class="card"><h3>Total Amount</h3><div class="metric">{money(totals['total_amount'])}</div></div>
    <div class="card"><h3>Total Tax</h3><div class="metric">{money(totals['tax_amount'])}</div></div>
  </div>
  <form method="post" action="{escape(url_with_lang('/payment-close', user_lang(user)))}" style="margin-top: 16px;">
    {hidden_fields}
    <div class="form-grid">
      <div><label>Payment Date / 支払日</label><input name="payment_date" type="date" required></div>
      <div><label>Closing Notes / 支払締めメモ</label><textarea name="notes" placeholder="Optional payment batch note"></textarea></div>
    </div>
    <div class="actions"><button class="danger" type="submit">Close Payment / 支払締め</button></div>
  </form>
</section>
""" + payment_closing_history_html(user=user)


def payment_closing_history_html(limit: int = 10, user: dict[str, Any] | None = None) -> str:
    closings = sorted(scope_records_to_current_entity(load_payment_closings(), user, include_own_legacy=False), key=lambda item: str(item.get("closed_at", "")), reverse=True)[:limit]
    if not closings:
        rows = "<tr><td colspan='7' class='muted'>No payment closings yet.</td></tr>"
    else:
        rows = "".join(
            f"<tr><td>{escape(str(item.get('closed_at', '')))}</td><td>{escape(str(item.get('claim_month', '')))}</td><td>{escape(str(item.get('payment_date', '')))}</td><td class='num'>{escape(str(item.get('claim_count', 0)))}</td><td class='num'>{money(item.get('total_amount', 0))}</td><td>{escape(str(item.get('closed_by', '')))}</td><td>{escape(str(item.get('notes', '')))}</td></tr>"
            for item in closings
        )
    return f"""
<section class="panel wide" style="margin-top: 18px;">
  <h3>Payment closing history / 支払締め履歴</h3>
  <table>
    <thead><tr><th>Closed At</th><th>Claim Month</th><th>Payment Date</th><th class="num">Claims</th><th class="num">Total</th><th>Closed By</th><th>Notes</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


def report_export_history_html(limit: int = 10, user: dict[str, Any] | None = None) -> str:
    exports = sorted(scope_records_to_current_entity(load_report_exports(), user, include_own_legacy=False), key=lambda item: str(item.get("created_at", "")), reverse=True)[:limit]
    if not exports:
        rows = "<tr><td colspan='7' class='muted'>No report exports yet.</td></tr>"
    else:
        rows = "".join(
            f"<tr><td>{escape(str(item.get('created_at', '')))}</td><td>{escape(str(item.get('report_month', '')))}</td><td>{escape(str(item.get('report_type', '')))}</td><td>{escape(str(item.get('file_name', '')))}</td><td class='num'>{escape(str(item.get('row_count', 0)))}</td><td class='num'>{money(item.get('total_amount', 0))}</td><td>{escape(str(item.get('created_by', '')))}</td></tr>"
            for item in exports
        )
    return f"""
<section class="panel wide" style="margin-top: 18px;">
  <h3>Recent export history / 出力履歴</h3>
  <table>
    <thead><tr><th>Created At</th><th>Month</th><th>Type</th><th>File Name</th><th class="num">Rows</th><th class="num">Total</th><th>Created By</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""


def local_ocr_help_html() -> str:
    return """
<div class="notice" style="margin-top: 18px;">
  <strong>Local OCR / ローカルOCR:</strong> The Extract button uses local Tesseract OCR when installed. If Tesseract/Poppler are unavailable on macOS, the app falls back to Apple's local Vision OCR for images and first-page PDFs. OCR results are draft suggestions only and must be reviewed before submit.
</div>
"""


def ocr_field_hint_html(record: dict[str, Any], claim_field: str) -> str:
    if record.get("ocr_status", "not_run") == "not_run":
        return ""
    draft = normalize_ocr_draft(record.get("ocr_draft") or {})
    for mapping in OCR_TO_CLAIM_FIELD_MAPPING:
        source, target = mapping[0], mapping[1]
        if target != claim_field:
            continue
        suggestion = draft.get(source)
        if suggestion in (None, "", "unknown"):
            return ""
        return f'<p class="muted">OCR suggestion: {escape(str(suggestion))}. Please verify before submit.</p>'
    return ""


def claim_form_html(record: Optional[dict[str, Any]] = None, mode: str = "new", user: dict[str, Any] | None = None) -> str:
    record = dict(record or default_claim_record())
    identity_locked = bool(user and not can_proxy_submit(user))
    if identity_locked and not mode == "edit":
        identity = employee_identity_from_user(user)
        for key in ["employee_no", "employee_name", "department"]:
            if identity.get(key):
                record[key] = identity[key]
    identity_readonly = "readonly" if identity_locked else ""
    identity_hint = "Resolved from your User_admin account." if identity_locked else "Employee-provided standard claim field; required before Submit."
    is_edit = mode == "edit"
    is_ocr_assisted = is_edit and record.get("ocr_status", "not_run") != "not_run"
    title = "Review OCR-assisted Claim / OCR読取結果の確認・修正" if is_ocr_assisted else "Edit Claim / 経費申請編集" if is_edit else "New Claim / 経費申請"
    action = "/claim-edit" if is_edit else "/claim-new"
    button_label = "Save Update / 更新" if is_edit else "Save Draft / 下書き保存"
    hidden_id = f'<input type="hidden" name="claim_id" value="{value(record, "claim_id")}">' if is_edit else ""
    if is_edit:
        save_button = f'<button type="submit" name="status" value="Draft">{button_label}</button>'
        submit_button = '<button type="submit" name="status" value="Submitted">Submit / 申請</button>'
    else:
        save_button = f'<button type="submit" name="action" value="save_draft">{button_label}</button>'
        submit_button = '<button type="submit" name="action" value="submit">Submit / 申請</button>'
    category_options = select_options(CATEGORIES, str(record.get("category", "transportation")))
    tax_options = select_options([(rate, rate) for rate in TAX_RATES], str(record.get("tax_rate", "10%")))
    payment_options = select_options(PAYMENT_METHODS, str(record.get("payment_method", "employee_paid")))
    invoice_options = select_options(QUALIFIED_INVOICE_OPTIONS, str(record.get("is_qualified_invoice", "unknown")))
    attachment = record.get("attachment") or {}
    attachment_note = f"Current attachment: {escape(str(attachment.get('original_filename') or '-'))}" if is_edit else "Attach receipt/invoice image or PDF. This same file can be used for OCR extraction before saving."
    extract_button = "" if is_edit else '<button class="secondary" type="submit" name="action" value="extract_ocr">Extract from receipt/invoice / 領収書・請求書から読み取る</button>'
    mock_ocr_html = local_ocr_help_html() if not is_edit else ""
    if is_ocr_assisted:
        form_notice = "This is the final standard reimbursement form. OCR values are suggestions only; finance approval, reports, CSV export, and payment closing use the employee-reviewed standard fields below."
    else:
        form_notice = "This is the standard reimbursement form used for both manual entry and OCR-assisted entry. OCR-style values are prefill aids only; the final saved claim is the employee-reviewed form below."
    ocr_review_panel = ocr_draft_review_html(record) if is_ocr_assisted else ""
    ocr_review_control = ""
    if is_edit and record.get("ocr_status") == "draft":
        ocr_review_control = """
        <div style="margin-top: 14px;">
          <label>OCR Review Confirmation / OCR確認</label>
          <label style="font-weight: normal;"><input type="checkbox" name="ocr_reviewed" value="1"> I reviewed and corrected all OCR-prefilled fields / OCR読取項目を確認・修正しました</label>
          <p class="muted">You may save a Draft without confirming OCR review. Confirmation is required before Submit.</p>
        </div>
        """
    delete_html = ""
    if is_edit and claim_is_editable(record):
        delete_html = f"""
        <form method="post" action="/claim-delete">
          <input type="hidden" name="claim_id" value="{value(record, 'claim_id')}">
          <button class="danger" type="submit">Soft Delete / 論理削除</button>
        </form>
        """
    return f"""
<section class="sap-page-header">
  <p class="muted">Employee Reimbursement / 経費精算</p>
  <h2>{title}</h2>
  <p class="message-strip message-info">{escape(form_notice)}</p>
  <div class="sap-object-meta">
    {claim_status_badge(str(record.get('status', 'Draft')))}
    {ocr_status_badge(str(record.get('ocr_status', 'not_run')))}
  </div>
</section>
{ocr_review_panel}
<section class="sap-section" style="margin-top: 18px;">
  <form method="post" action="{action}" enctype="multipart/form-data">
    {employee_datalist_html(user)}
    {hidden_id}
    <div class="form-grid">
      <div><label>Employee No. / 社員No.</label><input name="employee_no" list="employee-no-options" value="{value(record, 'employee_no')}" placeholder="E001" {identity_readonly}><p class="muted">{identity_hint}</p></div>
      <div><label>Employee Name / 氏名</label><input name="employee_name" value="{value(record, 'employee_name')}" placeholder="Yamada Taro" {identity_readonly}>{ocr_field_hint_html(record, 'employee_name')}</div>
      <div><label>Department / 部門</label><input name="department" value="{value(record, 'department')}" placeholder="Finance" {identity_readonly}><p class="muted">Employee-provided standard claim field; OCR normally cannot provide this reliably.</p></div>
      <div><label>Claim Month / 精算月</label><input name="claim_month" value="{value(record, 'claim_month')}" placeholder="2026-06"><p class="muted">Employee-provided standard claim field; required before Submit.</p></div>
      <div><label>Expense Date / 利用日</label><input name="expense_date" type="date" value="{value(record, 'expense_date')}">{ocr_field_hint_html(record, 'expense_date')}</div>
      <div><label>Category / 費用区分</label><select name="category">{category_options}</select>{ocr_field_hint_html(record, 'category')}</div>
      <div><label>Vendor / 店舗・支払先</label><input name="vendor_name" value="{value(record, 'vendor_name')}" placeholder="JR East / 株式会社〇〇">{ocr_field_hint_html(record, 'vendor_name')}</div>
      <div><label>Receipt/Invoice No. / 領収書番号</label><input name="invoice_or_receipt_number" value="{value(record, 'invoice_or_receipt_number')}" placeholder="INV-001">{ocr_field_hint_html(record, 'invoice_or_receipt_number')}</div>
      <div><label>Qualified Invoice No. / 適格請求書登録番号</label><input name="qualified_invoice_number" value="{value(record, 'qualified_invoice_number')}" placeholder="T1234567890123">{ocr_field_hint_html(record, 'qualified_invoice_number')}</div>
      <div><label>Invoice Status / インボイス区分</label><select name="is_qualified_invoice">{invoice_options}</select></div>
      <div><label>Amount excl. tax / 税抜金額</label><input name="amount_excluding_tax" type="number" min="0" step="1" value="{value(record, 'amount_excluding_tax')}">{ocr_field_hint_html(record, 'amount_excluding_tax')}</div>
      <div><label>Tax Amount / 消費税額</label><input name="tax_amount" type="number" min="0" step="1" value="{value(record, 'tax_amount')}">{ocr_field_hint_html(record, 'tax_amount')}</div>
      <div><label>Total incl. tax / 税込金額</label><input name="total_amount" type="number" min="0" step="1" value="{value(record, 'total_amount')}">{ocr_field_hint_html(record, 'total_amount')}</div>
      <div><label>Tax Rate / 税率</label><select name="tax_rate">{tax_options}</select>{ocr_field_hint_html(record, 'tax_rate')}</div>
      <div><label>Payment Method / 支払方法</label><select name="payment_method">{payment_options}</select>{ocr_field_hint_html(record, 'payment_method')}</div>
      <div><label>Currency / 通貨</label><input name="currency" value="JPY" readonly></div>
      <div><label>Receipt/Invoice Attachment / 領収書・請求書添付</label><input type="file" name="receipt_file" accept=".jpg,.jpeg,.png,.pdf,.webp"><p class="muted">{attachment_note}</p>{extract_button}</div>
    </div>
    {mock_ocr_html}
    <div style="margin-top: 14px;">
      <label>Business Purpose / 利用目的</label>
      <textarea name="business_purpose" placeholder="Client visit / 顧客訪問">{value(record, 'business_purpose')}</textarea>
      <p class="muted">Employee-provided standard claim field; required before Submit.</p>
    </div>
    <div style="margin-top: 14px;">
      <label>Notes / 備考</label>
      <textarea name="notes" placeholder="Optional employee note">{value(record, 'notes')}</textarea>
    </div>
    {ocr_review_control}
    <div class="actions">
      {save_button}
      {submit_button}
      <a class="button ghost" href="/claims">Cancel / キャンセル</a>
    </div>
  </form>
  {delete_html}
</section>
"""



def operation_success_message(record_type: str, record_name: str, action: str, actor: str = DEFAULT_FINANCE_ACTOR) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    return f"{record_type} record {record} {action} successfully at {timestamp} by {actor}. / {record_type}记录 {record} 已于 {timestamp} 由 {actor} {action}成功。 / {record_type} レコード {record} は {timestamp} に {actor} により{action}されました。"


def no_change_message(record_type: str, record_name: str) -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    return f"No changes detected for {record_type} record {record} at {timestamp}. Nothing was saved and no audit entry was created. / {timestamp} 未检测到 {record_type}记录 {record} 的变更。未保存，也未生成审计记录。 / {timestamp} 時点で {record_type} レコード {record} に変更はありません。保存および監査記録の作成は行われませんでした。"


def claim_record_label(record: dict[str, Any]) -> str:
    return str(record.get("claim_no") or record.get("claim_id") or "").strip()

def claim_saved_html(record: dict[str, Any], message: str = "") -> str:
    message = message or operation_success_message("Claim", claim_record_label(record), "saved")
    attachment_html = attachment_link_html(record)
    return f"""
<section class="sap-page-header">
  <p class="muted">Employee Reimbursement / 経費精算</p>
  <h2>Claim saved / 経費申請保存完了</h2>
  <p class="message-strip message-success">{escape(message)}</p>
  <div class="sap-object-meta">
    {claim_status_badge(str(record.get('status', '')))}
    {ocr_status_badge(str(record.get('ocr_status', 'not_run')))}
  </div>
</section>
<section class="grid">
  <div class="card"><h3>Claim No.</h3><p>{value(record, 'claim_no')}</p></div>
  <div class="card"><h3>Employee</h3><p>{value(record, 'employee_no')} - {value(record, 'employee_name')}</p></div>
  <div class="card"><h3>Total / 税込金額</h3><p>{money(record.get('total_amount', 0))}</p></div>
  <div class="card"><h3>Status / 状態</h3><p>{claim_status_badge(str(record.get('status', '')))}</p></div>
  <div class="card"><h3>OCR Status / OCR状態</h3><p>{ocr_status_badge(str(record.get('ocr_status', 'not_run')))}</p></div>
  <div class="card"><h3>Attachment / 証憑</h3><p>{attachment_html}</p></div>
</section>
<section class="sap-section">
  <div class="actions">
    <a class="button" href="/claims">Open Claims</a>
    <a class="button secondary" href="/claim-new">Input Next Claim</a>
  </div>
</section>
"""


def ocr_display_value(value_to_show: Any) -> str:
    if value_to_show in (None, ""):
        return "-"
    return str(value_to_show)


def ocr_draft_review_html(record: dict[str, Any]) -> str:
    draft = normalize_ocr_draft(record.get("ocr_draft") or {})
    attachment_html = attachment_link_html(record)
    notes = draft.get("confidence_notes") or []
    note_items = "".join(f"<li>{escape(str(note))}</li>" for note in notes) or "<li>No confidence notes.</li>"
    comparison_rows = []
    for source, target, label in OCR_TO_CLAIM_FIELD_MAPPING:
        comparison_rows.append(
            "<tr>"
            f"<th>{escape(label)}</th>"
            f"<td>{escape(ocr_display_value(draft.get(source)))}</td>"
            f"<td>{escape(ocr_display_value(record.get(target)))}</td>"
            "</tr>"
        )
    comparison_rows.append(
        "<tr>"
        "<th>Currency / 通貨</th>"
        f"<td>{escape(ocr_display_value(draft.get('currency')))}</td>"
        f"<td>{escape(ocr_display_value(record.get('currency')))}</td>"
        "</tr>"
    )
    rows = "".join(comparison_rows)
    return f"""
<section class="panel" style="margin-top: 18px;">
  <h2>OCR Draft Review / OCR下書き確認</h2>
  <p class="notice">OCR status: {ocr_status_badge(str(record.get('ocr_status', 'not_run')))}. OCR suggestions are reference values only. Payroll, reports, approval, CSV export, and payment closing use the employee-reviewed standard claim values.</p>
  <p><strong>Attachment:</strong> {attachment_html}</p>
  <div class="wide">
    <table>
      <thead><tr><th>Field</th><th>OCR suggestion</th><th>Current standard claim value</th></tr></thead>
      <tbody>{rows}</tbody>
    </table>
  </div>
  <p class="muted">Employee No., Department, Claim Month, and Business Purpose are standard claim fields that OCR normally cannot provide reliably. Please fill or verify them in the form below.</p>
  <h3>Confidence notes / 確認メモ</h3>
  <ul>{note_items}</ul>
</section>
"""


def ocr_status_badge(status: str) -> str:
    labels = {
        "not_run": "Not run / 未実行",
        "draft": "Draft - review needed / 要確認",
        "confirmed": "Confirmed / 確認済み",
        "failed": "Failed / 失敗",
        "not_available": "Not available / 利用不可",
    }
    css_class = {
        "draft": "status-draft-review",
        "confirmed": "status-confirmed",
        "failed": "status-failed",
        "not_available": "status-warning",
    }.get(status, "status-draft")
    return f"<span class=\"status-badge {css_class}\">{escape(labels.get(status, status or '-'))}</span>"


def claim_status_badge(status: str) -> str:
    css_class = {
        "Draft": "status-draft",
        "Submitted": "status-submitted",
        "Approved": "status-approved",
        "Rejected": "status-rejected",
        "Paid": "status-paid",
    }.get(status, "")
    return f"<span class=\"status-badge {css_class}\">{escape(status or '-')}</span>"


def status_message_html(message: str) -> str:
    return f"<section class='message-strip message-success'>{escape(message)}</section>"


def error_message_html(message: str) -> str:
    return f"<section class='panel'><h2>Input Error / 入力エラー</h2><p class='message-strip message-error'>{escape(message)}</p></section>"


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    data = json.loads(text)
    if not isinstance(data, list):
        raise ValueError(f"{path.name} must contain a JSON array.")
    return [item for item in data if isinstance(item, dict)]


def write_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def audit_entity_from_values(before_value: Any, after_value: Any, user: dict[str, Any] | None = None) -> dict[str, str]:
    entity = current_entity_from_user(user)
    if entity:
        return entity
    for value_to_check in [after_value, before_value]:
        if isinstance(value_to_check, dict):
            entity_id = str(value_to_check.get("entity_id", "") or "").strip()
            entity_code = str(value_to_check.get("entity_code", "") or "").strip()
            entity_name = str(value_to_check.get("entity_name", "") or "").strip()
            if entity_id or entity_code:
                return {"entity_id": entity_id, "entity_code": entity_code, "entity_name": entity_name}
    return {}


def append_audit_log(module: str, record_id: str, action: str, before_value: Any, after_value: Any, user: dict[str, Any] | None = None) -> dict[str, Any]:
    logs = load_audit_logs()
    now = datetime.now(timezone.utc)
    entity = audit_entity_from_values(before_value, after_value, user)
    log = {
        "audit_id": f"audit-{now.strftime('%Y%m%d%H%M%S%f')}",
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": actor_from_user(user),
        "timestamp": now.isoformat(),
        "before_value": before_value if before_value is not None else {},
        "after_value": after_value if after_value is not None else {},
        "entity_id": entity.get("entity_id", ""),
        "entity_code": entity.get("entity_code", ""),
        "entity_name": entity.get("entity_name", ""),
    }
    logs.append(log)
    write_json_array(AUDIT_LOGS_PATH, logs)
    return log


NO_OP_COMPARE_IGNORE_FIELDS = {"updated_at", "updated_by"}


def records_business_equal(before: dict[str, Any] | None, after: dict[str, Any] | None, ignore_fields: set[str] | None = None) -> bool:
    before = before or {}
    after = after or {}
    ignored = ignore_fields or NO_OP_COMPARE_IGNORE_FIELDS
    keys = (set(before.keys()) | set(after.keys())) - ignored
    return all(before.get(key, "") == after.get(key, "") for key in keys)


def load_report_exports() -> list[dict[str, Any]]:
    return load_json_array(REPORT_EXPORTS_PATH)


def load_payment_closings() -> list[dict[str, Any]]:
    return load_json_array(PAYMENT_CLOSINGS_PATH)


def write_payment_closings(records: list[dict[str, Any]]) -> None:
    write_json_array(PAYMENT_CLOSINGS_PATH, records)


def payment_closing_for_month(claim_month: str, user: dict[str, Any] | None = None) -> Optional[dict[str, Any]]:
    claim_month = claim_month.strip()
    if not claim_month:
        return None
    for closing in scope_records_to_current_entity(load_payment_closings(), user, include_own_legacy=False):
        if closing.get("claim_month") == claim_month:
            return closing
    return None


def month_is_payment_closed(claim_month: str, user: dict[str, Any] | None = None) -> bool:
    return payment_closing_for_month(claim_month, user) is not None


def ensure_month_not_payment_closed(claim_month: str, user: dict[str, Any] | None = None) -> None:
    claim_month = claim_month.strip()
    if claim_month and month_is_payment_closed(claim_month, user):
        raise ValueError(f"Claim Month {claim_month} is payment-closed and cannot be changed.")


def load_approval_logs() -> list[dict[str, Any]]:
    return load_json_array(APPROVAL_LOGS_PATH)


def approval_logs_for_claim(claim_id: str) -> list[dict[str, Any]]:
    claim_id = claim_id.strip()
    return [log for log in load_approval_logs() if log.get("claim_id") == claim_id]


def claim_actor(claim: dict[str, Any]) -> str:
    employee_no = str(claim.get("employee_no", "")).strip()
    return employee_no or "Employee"


def append_approval_log(claim: dict[str, Any], action: str, actor: str, before_status: str, after_status: str, notes: str = "") -> dict[str, Any]:
    logs = load_approval_logs()
    now = datetime.now(timezone.utc)
    log = {
        "log_id": f"log-{now.strftime('%Y%m%d%H%M%S%f')}",
        "claim_id": claim.get("claim_id", ""),
        "claim_no": claim.get("claim_no", ""),
        "action": action,
        "actor": actor,
        "action_at": now.isoformat(),
        "before_status": before_status,
        "after_status": after_status,
        "notes": notes.strip(),
    }
    logs.append(log)
    write_json_array(APPROVAL_LOGS_PATH, logs)
    return log


def load_claims(include_deleted: bool = False) -> list[dict[str, Any]]:
    records = load_json_array(CLAIMS_PATH)
    if include_deleted:
        return records
    return [record for record in records if record.get("record_status", "Active") != "Deleted"]


def find_claim(claim_id: str) -> Optional[dict[str, Any]]:
    claim_id = claim_id.strip()
    if not claim_id:
        return None
    for record in load_claims(include_deleted=True):
        if record.get("claim_id") == claim_id:
            return record
    return None


def filter_claims(claims: list[dict[str, Any]], filters: dict[str, str]) -> list[dict[str, Any]]:
    filtered = claims
    entity_id = filters.get("entity_id", "")
    employee_no = filters.get("employee_no", "").lower()
    claim_month = filters.get("claim_month", "")
    status = filters.get("status", "")
    if entity_id:
        filtered = [claim for claim in filtered if entity_id in {str(claim.get("entity_id", "")).strip(), str(claim.get("entity_code", "")).strip()}]
    if employee_no:
        filtered = [claim for claim in filtered if employee_no == str(claim.get("employee_no", "")).lower()]
    if claim_month:
        filtered = [claim for claim in filtered if claim.get("claim_month") == claim_month]
    if status:
        filtered = [claim for claim in filtered if claim.get("status") == status]
    return filtered


def report_filters_from_query(query: dict[str, list[str]]) -> dict[str, str]:
    filters = {key: query.get(key, [""])[0].strip() for key in ["entity_id", "claim_month", "employee_no", "department", "approval_status", "category", "tax_rate", "payment_method"]}
    filters["approval_status"] = filters["approval_status"] or "Approved"
    if filters["claim_month"]:
        validate_month(filters["claim_month"])
    return filters


def report_claims(filters: dict[str, str], user: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    claims = scope_records_to_current_entity(load_claims(), user, include_own_legacy=False)
    status = filters.get("approval_status", "Approved") or "Approved"
    claims = [claim for claim in claims if claim.get("status") == status]
    entity_id = filters.get("entity_id", "")
    employee_no = filters.get("employee_no", "").lower()
    department = filters.get("department", "").lower()
    claim_month = filters.get("claim_month", "")
    category = filters.get("category", "")
    tax_rate = filters.get("tax_rate", "")
    payment_method = filters.get("payment_method", "")
    if claim_month:
        claims = [claim for claim in claims if claim.get("claim_month") == claim_month]
    if entity_id:
        claims = [claim for claim in claims if entity_id in {str(claim.get("entity_id", "")).strip(), str(claim.get("entity_code", "")).strip()}]
    if employee_no:
        claims = [claim for claim in claims if str(claim.get("employee_no", "")).lower() == employee_no]
    if department:
        claims = [claim for claim in claims if str(claim.get("department", "")).lower() == department]
    if category:
        claims = [claim for claim in claims if claim.get("category") == category]
    if tax_rate:
        claims = [claim for claim in claims if claim.get("tax_rate") == tax_rate]
    if payment_method:
        claims = [claim for claim in claims if claim.get("payment_method") == payment_method]
    return sorted(claims, key=lambda item: (str(item.get("claim_month", "")), str(item.get("employee_no", "")), str(item.get("expense_date", "")), str(item.get("claim_no", ""))))


def calculate_report_summaries(claims: list[dict[str, Any]]) -> dict[str, Any]:
    totals = calculate_claim_totals(claims)
    return {
        "claim_count": len(claims),
        "total_amount": totals["total_amount"],
        "total_tax_amount": totals["tax_amount"],
        "by_employee": group_report_totals(claims, lambda claim: (str(claim.get("employee_no", "")), f"{claim.get('employee_no', '')} - {claim.get('employee_name', '')}".strip(" -"))),
        "by_category": group_report_totals(claims, lambda claim: (str(claim.get("category", "")), category_label_text(str(claim.get("category", ""))))),
        "by_tax_rate": group_report_totals(claims, lambda claim: (str(claim.get("tax_rate", "")), str(claim.get("tax_rate", "") or "-"))),
        "by_payment_method": group_report_totals(claims, lambda claim: (str(claim.get("payment_method", "")), payment_method_label(str(claim.get("payment_method", ""))))),
    }


def group_report_totals(claims: list[dict[str, Any]], key_func: Any) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}
    for claim in claims:
        key, label = key_func(claim)
        key = key or "-"
        label = label or key
        if key not in groups:
            groups[key] = {"key": key, "label": label, "claim_count": 0, "total_amount": 0, "tax_amount": 0}
        groups[key]["claim_count"] += 1
        groups[key]["total_amount"] += parse_non_negative_int(claim.get("total_amount", 0), "Total Amount")
        groups[key]["tax_amount"] += parse_non_negative_int(claim.get("tax_amount", 0), "Tax Amount")
    return sorted(groups.values(), key=lambda row: str(row["label"]))


def claim_record_from_form(form: dict[str, str]) -> dict[str, Any]:
    record = claim_fields_from_form(form)
    record["status"] = form.get("status", "Draft").strip() or "Draft"
    return record


def claim_update_from_form(existing: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    if not claim_is_editable(existing):
        raise ValueError("Only Draft or Rejected claims can be edited.")
    now = datetime.now(timezone.utc)
    record = claim_fields_from_form(form)
    record["claim_id"] = existing.get("claim_id", "")
    record["claim_no"] = existing.get("claim_no", "")
    record["status"] = form.get("status", existing.get("status", "Draft")).strip() or "Draft"
    record["record_status"] = existing.get("record_status", "Active")
    record["attachment"] = existing.get("attachment")
    before_status = str(existing.get("status", "Draft"))
    after_status = str(record.get("status", "Draft"))
    existing_ocr_status = existing.get("ocr_status", "not_run")
    if existing_ocr_status == "draft":
        if after_status == "Submitted":
            if form.get("ocr_reviewed") != "1":
                raise ValueError("Please review and confirm the OCR draft before submitting.")
            record["ocr_status"] = "confirmed"
        else:
            record["ocr_status"] = "draft"
    else:
        record["ocr_status"] = existing_ocr_status if existing_ocr_status in OCR_STATUSES else "not_run"
    record["ocr_draft"] = normalize_ocr_draft(existing.get("ocr_draft") or default_ocr_draft())
    record["finance_notes"] = existing.get("finance_notes", "")
    record["reject_reason"] = existing.get("reject_reason", "")
    record["submitted_at"] = now.isoformat() if after_status == "Submitted" and before_status != "Submitted" else existing.get("submitted_at", "")
    record["approved_at"] = "" if after_status == "Submitted" and before_status != "Submitted" else existing.get("approved_at", "")
    record["approved_by"] = "" if after_status == "Submitted" and before_status != "Submitted" else existing.get("approved_by", "")
    record["rejected_at"] = existing.get("rejected_at", "")
    record["rejected_by"] = existing.get("rejected_by", "")
    record["paid_at"] = "" if after_status == "Submitted" and before_status != "Submitted" else existing.get("paid_at", "")
    record["created_at"] = existing.get("created_at", now.isoformat())
    record["updated_at"] = now.isoformat()
    return record


def claim_fields_from_form(form: dict[str, str]) -> dict[str, Any]:
    return {
        "employee_no": form.get("employee_no", "").strip(),
        "employee_name": form.get("employee_name", "").strip(),
        "department": form.get("department", "").strip(),
        "claim_month": form.get("claim_month", "").strip(),
        "expense_date": form.get("expense_date", "").strip(),
        "category": form.get("category", "transportation").strip() or "transportation",
        "vendor_name": form.get("vendor_name", "").strip(),
        "invoice_or_receipt_number": form.get("invoice_or_receipt_number", "").strip(),
        "qualified_invoice_number": form.get("qualified_invoice_number", "").strip().upper(),
        "is_qualified_invoice": form.get("is_qualified_invoice", "unknown").strip() or "unknown",
        "currency": "JPY",
        "total_amount": parse_non_negative_int(form.get("total_amount", "0"), "Total Amount"),
        "amount_excluding_tax": parse_non_negative_int(form.get("amount_excluding_tax", "0"), "Amount Excluding Tax"),
        "tax_amount": parse_non_negative_int(form.get("tax_amount", "0"), "Tax Amount"),
        "tax_rate": form.get("tax_rate", "unknown").strip() or "unknown",
        "payment_method": form.get("payment_method", "employee_paid").strip() or "employee_paid",
        "business_purpose": form.get("business_purpose", "").strip(),
        "notes": form.get("notes", "").strip(),
        "finance_notes": "",
        "reject_reason": "",
        "ocr_status": "not_run",
        "ocr_draft": default_ocr_draft(),
        "submitted_at": "",
        "approved_at": "",
        "approved_by": "",
        "rejected_at": "",
        "rejected_by": "",
        "paid_at": "",
    }


def payment_close_filters_from_form(form: dict[str, str]) -> dict[str, str]:
    filters = {key: form.get(key, "").strip() for key in ["claim_month", "employee_no", "department", "category", "tax_rate", "payment_method"]}
    if not filters["claim_month"]:
        raise ValueError("Claim Month / 精算月 is required for payment closing.")
    validate_month(filters["claim_month"])
    filters["approval_status"] = "Approved"
    return filters


def close_payment_batch(filters: dict[str, str], payment_date: str, notes: str = "", actor: str = DEFAULT_FINANCE_ACTOR, user: dict[str, Any] | None = None) -> dict[str, Any]:
    claim_month = filters.get("claim_month", "").strip()
    if not claim_month:
        raise ValueError("Claim Month / 精算月 is required for payment closing.")
    validate_month(claim_month)
    validate_date(payment_date.strip(), "Payment Date")
    if month_is_payment_closed(claim_month, user):
        raise ValueError(f"Claim Month {claim_month} is already payment-closed for the current Entity.")
    filters = dict(filters)
    filters["approval_status"] = "Approved"
    target_claims = report_claims(filters, user)
    if not target_claims:
        raise ValueError("No Approved claims match the selected payment closing filters for the current Entity.")
    target_ids = {str(claim.get("claim_id", "")) for claim in target_claims}
    records = load_claims(include_deleted=True)
    now = datetime.now(timezone.utc)
    totals = calculate_claim_totals(target_claims)
    closing = {
        "closing_id": f"closing-{now.strftime('%Y%m%d%H%M%S%f')}",
        "claim_month": claim_month,
        "payment_date": payment_date.strip(),
        "notes": notes.strip(),
        "claim_ids": sorted(target_ids),
        "claim_count": len(target_ids),
        "total_amount": totals["total_amount"],
        "total_tax_amount": totals["tax_amount"],
        "closed_by": actor,
        "closed_at": now.isoformat(),
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    apply_current_entity_snapshot(closing, user)
    updated_pairs: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for record in records:
        if str(record.get("claim_id", "")) not in target_ids:
            continue
        before_value = dict(record)
        require_record_entity_access(record, user, "Payment closing claim")
        if record.get("record_status", "Active") == "Deleted":
            raise ValueError("Deleted claims cannot be marked Paid.")
        if record.get("status") != "Approved":
            raise ValueError("Only Approved claims can be marked Paid.")
        if record.get("claim_month") != claim_month:
            raise ValueError("All payment closing claims must belong to the selected claim month.")
        record["status"] = "Paid"
        record["paid_at"] = now.isoformat()
        record["updated_at"] = now.isoformat()
        updated_pairs.append((before_value, dict(record)))
    if len(updated_pairs) != len(target_ids):
        raise ValueError("One or more payment closing claims were not found.")
    write_json_array(CLAIMS_PATH, records)
    for before_value, after_value in updated_pairs:
        log_notes = f"Payment closing {closing['closing_id']}; payment date {closing['payment_date']}. {notes.strip()}".strip()
        append_approval_log(after_value, "mark_paid", actor, "Approved", "Paid", log_notes)
        append_audit_log("reimbursement.claim", str(after_value.get("claim_id", "")), "mark_paid", before_value, after_value, user)
    closings = load_payment_closings()
    closings.append(closing)
    write_payment_closings(closings)
    append_audit_log("reimbursement.payment_closing", str(closing.get("closing_id", "")), "create_payment_closing", {}, dict(closing), user)
    return closing


def build_report_csv(claims: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=REPORT_CSV_COLUMNS)
    writer.writeheader()
    for claim in claims:
        writer.writerow(report_csv_row(claim))
    return output.getvalue()


def report_csv_row(claim: dict[str, Any]) -> dict[str, str]:
    attachment = claim.get("attachment") or {}
    row = {
        "claim_no": claim.get("claim_no", ""),
        "status": claim.get("status", ""),
        "employee_no": claim.get("employee_no", ""),
        "employee_name": claim.get("employee_name", ""),
        "department": claim.get("department", ""),
        "claim_month": claim.get("claim_month", ""),
        "expense_date": claim.get("expense_date", ""),
        "category": claim.get("category", ""),
        "vendor_name": claim.get("vendor_name", ""),
        "invoice_or_receipt_number": claim.get("invoice_or_receipt_number", ""),
        "qualified_invoice_number": claim.get("qualified_invoice_number", ""),
        "is_qualified_invoice": claim.get("is_qualified_invoice", ""),
        "currency": claim.get("currency", "JPY"),
        "total_amount": parse_non_negative_int(claim.get("total_amount", 0), "Total Amount"),
        "tax_amount": parse_non_negative_int(claim.get("tax_amount", 0), "Tax Amount"),
        "tax_rate": claim.get("tax_rate", ""),
        "payment_method": claim.get("payment_method", ""),
        "business_purpose": claim.get("business_purpose", ""),
        "attachment_filename": attachment.get("original_filename", ""),
        "approved_at": claim.get("approved_at", ""),
        "approved_by": claim.get("approved_by", ""),
        "finance_notes": claim.get("finance_notes", ""),
    }
    return {key: csv_safe_cell(row.get(key, "")) for key in REPORT_CSV_COLUMNS}


def csv_safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def report_export_filename(filters: dict[str, str], now: Optional[datetime] = None) -> str:
    now = now or datetime.now(timezone.utc)
    month = filters.get("claim_month") or "all"
    stamp = now.strftime("%Y%m%dT%H%M%SZ")
    return safe_filename(f"tac-reimbursement-month-end-{month}-{stamp}.csv")


def append_report_export(filters: dict[str, str], claims: list[dict[str, Any]], file_name: str, actor: str = DEFAULT_FINANCE_ACTOR, user: dict[str, Any] | None = None) -> dict[str, Any]:
    exports = load_report_exports()
    now = datetime.now(timezone.utc)
    totals = calculate_claim_totals(claims)
    record = {
        "export_id": f"export-{now.strftime('%Y%m%d%H%M%S%f')}",
        "report_month": filters.get("claim_month", ""),
        "report_type": REPORT_TYPE_PAYROLL_REIMBURSEMENT_CSV,
        "file_name": file_name,
        "filter_json": dict(filters),
        "row_count": len(claims),
        "total_amount": totals["total_amount"],
        "created_by": actor,
        "created_at": now.isoformat(),
    }
    apply_current_entity_snapshot(record, user)
    exports.append(record)
    write_json_array(REPORT_EXPORTS_PATH, exports)
    append_audit_log("reimbursement.report_export", str(record.get("export_id", "")), "export_csv", {}, dict(record), user)
    return record


def create_ocr_draft_from_new_claim_form(upload: Optional[tuple[str, bytes, str]], form: dict[str, str], user: dict[str, Any] | None = None) -> dict[str, Any]:
    if not upload:
        raise ValueError("Please choose a receipt/invoice attachment before extracting OCR fields.")
    records = load_claims(include_deleted=True)
    now = datetime.now(timezone.utc)
    claim_id = f"claim-{now.strftime('%Y%m%d%H%M%S%f')}"
    attachment = save_attachment(claim_id, upload)
    if not attachment:
        raise ValueError("Receipt/invoice attachment is required for OCR extraction.")
    draft, ocr_status = build_local_ocr_draft(attachment)
    record = default_claim_record()
    record["claim_id"] = claim_id
    record["claim_no"] = next_claim_no(records, form.get("claim_month", "") or str(now.year), now)
    record["status"] = "Draft"
    record["record_status"] = "Active"
    record["attachment"] = attachment
    record["ocr_status"] = ocr_status
    record["ocr_draft"] = draft
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    apply_current_entity_snapshot(record, user)
    record = apply_ocr_draft_to_claim_defaults(record)
    record = preserve_manual_form_values(record, form)
    ensure_month_not_payment_closed(str(record.get("claim_month", "")), user)
    validate_claim_record(record)
    validate_ocr_draft_record(record)
    records.append(record)
    write_json_array(CLAIMS_PATH, records)
    append_audit_log("reimbursement.claim", str(record.get("claim_id", "")), "create_ocr_draft", {}, dict(record), user)
    return record


def build_local_ocr_draft(attachment: dict[str, Any]) -> tuple[dict[str, Any], str]:
    notes = ["Local OCR engine: Tesseract (jpn+eng). OCR values are draft suggestions only."]
    text, extraction_notes, status = extract_local_ocr_text(attachment)
    notes.extend(extraction_notes)
    if status != "draft":
        draft = default_ocr_draft()
        draft["confidence_notes"] = notes
        draft["requires_manual_review"] = True
        return normalize_ocr_draft(draft), status
    draft = parse_japanese_receipt_ocr_text(text, notes)
    parsed_values = [
        draft.get("receipt_date"),
        draft.get("vendor_name"),
        draft.get("invoice_or_receipt_number"),
        draft.get("qualified_invoice_number"),
        draft.get("total_amount"),
        draft.get("tax_amount"),
        draft.get("amount_excluding_tax"),
    ]
    if not any(value not in (None, "", 0, "unknown") for value in parsed_values):
        draft["confidence_notes"].append("OCR ran, but no supported invoice fields were confidently recognized. Please enter the claim manually.")
        return normalize_ocr_draft(draft), "failed"
    return normalize_ocr_draft(draft), "draft"


def extract_local_ocr_text(attachment: dict[str, Any]) -> tuple[str, list[str], str]:
    try:
        path = safe_attachment_path(attachment)
    except ValueError as exc:
        return "", [str(exc)], "failed"
    extension = path.suffix.lower()
    if extension in OCR_IMAGE_EXTENSIONS:
        text, ocr_notes, status = run_tesseract_ocr(path)
        if status == "not_available":
            vision_text, vision_notes, vision_status = run_macos_vision_ocr(path)
            return vision_text, ocr_notes + ["Tesseract was not available; OCR used macOS Vision fallback."] + vision_notes, vision_status
        return text, ocr_notes, status
    if extension == ".pdf":
        pdftoppm = shutil.which("pdftoppm")
        if not pdftoppm:
            text, vision_notes, vision_status = run_macos_vision_ocr(path)
            return text, ["Poppler/pdftoppm was not found; PDF OCR used macOS Vision first-page fallback."] + vision_notes, vision_status
        try:
            with tempfile.TemporaryDirectory(prefix="tac-ocr-") as temp_dir:
                output_prefix = str(Path(temp_dir) / "page")
                subprocess.run(
                    [pdftoppm, "-f", "1", "-singlefile", "-png", str(path), output_prefix],
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=OCR_TIMEOUT_SECONDS,
                )
                image_path = Path(f"{output_prefix}.png")
                if not image_path.exists():
                    return "", ["PDF conversion did not create an image for OCR."], "failed"
                text, ocr_notes, status = run_tesseract_ocr(image_path)
                return text, ["PDF OCR used the first page only."] + ocr_notes, status
        except FileNotFoundError:
            return "", ["PDF OCR requires local Poppler/pdftoppm, but it was not found on PATH."], "not_available"
        except subprocess.TimeoutExpired:
            return "", ["PDF conversion timed out."], "failed"
        except subprocess.CalledProcessError as exc:
            message = (exc.stderr or exc.stdout or "PDF conversion failed.").strip()
            return "", [f"PDF conversion failed: {message[:300]}"], "failed"
    return "", [f"OCR is not supported for attachment type {extension or '(unknown)'}."] , "not_available"


def safe_attachment_path(attachment: dict[str, Any]) -> Path:
    relative_path = str(attachment.get("relative_path", "")).strip()
    if not relative_path:
        raise ValueError("Attachment path is missing; OCR cannot read the file.")
    path = (ROOT_DIR / relative_path).resolve()
    root = ROOT_DIR.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ValueError("Attachment path is outside the project directory; OCR was blocked.") from exc
    if not path.exists() or not path.is_file():
        raise ValueError("Attachment file was not found for OCR.")
    if path.suffix.lower() not in ALLOWED_ATTACHMENT_EXTENSIONS:
        raise ValueError("Attachment type is not supported for OCR.")
    return path


def run_tesseract_ocr(image_path: Path) -> tuple[str, list[str], str]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", ["Local OCR requires Tesseract, but tesseract was not found on PATH."], "not_available"
    notes: list[str] = []
    outputs: list[str] = []
    for psm in ["6", "11"]:
        try:
            result = subprocess.run(
                [tesseract, str(image_path), "stdout", "-l", OCR_TESSERACT_LANGUAGES, "--psm", psm],
                check=False,
                capture_output=True,
                text=True,
                timeout=OCR_TIMEOUT_SECONDS,
            )
        except FileNotFoundError:
            return "", ["Local OCR requires Tesseract, but tesseract was not found on PATH."], "not_available"
        except subprocess.TimeoutExpired:
            notes.append(f"Tesseract OCR timed out with page segmentation mode {psm}.")
            continue
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            if "Failed loading language" in stderr or "Error opening data file" in stderr:
                return "", ["Tesseract Japanese/English language data is missing. Install tesseract-lang and ensure jpn and eng are available."], "not_available"
            notes.append(f"Tesseract failed with page segmentation mode {psm}: {stderr[:300] or 'unknown error'}")
            continue
        output = (result.stdout or "").strip()
        outputs.append(output)
        if len(normalize_ocr_text(output)) >= 20:
            notes.append(f"Tesseract OCR completed with page segmentation mode {psm}.")
            return output, notes, "draft"
    best_output = max(outputs, key=len, default="")
    if best_output.strip():
        notes.append("Tesseract OCR completed, but the detected text was very short. Please review carefully.")
        return best_output, notes, "draft"
    notes.append("Tesseract OCR completed but no usable text was detected.")
    return "", notes, "failed"


def run_macos_vision_ocr(path: Path) -> tuple[str, list[str], str]:
    swift = shutil.which("swift")
    if not swift:
        return "", ["macOS Vision OCR fallback requires Swift, but swift was not found on PATH."], "not_available"
    if not MACOS_VISION_OCR_SCRIPT.exists():
        return "", ["macOS Vision OCR fallback script is missing."], "not_available"
    try:
        result = subprocess.run(
            [swift, str(MACOS_VISION_OCR_SCRIPT), str(path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=OCR_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        return "", ["macOS Vision OCR timed out."], "failed"
    except FileNotFoundError:
        return "", ["macOS Vision OCR fallback requires Swift, but swift was not found on PATH."], "not_available"
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "macOS Vision OCR failed.").strip()
        return "", [f"macOS Vision OCR failed: {message[:300]}"], "failed"
    output = (result.stdout or "").strip()
    if not output:
        return "", ["macOS Vision OCR completed but no usable text was detected."], "failed"
    return output, ["macOS Vision OCR completed locally."], "draft"


def normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("￥", "¥")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def parse_japanese_receipt_ocr_text(text: str, notes: list[str]) -> dict[str, Any]:
    normalized = normalize_ocr_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = "\n".join(lines)
    draft = default_ocr_draft()
    draft["confidence_notes"] = list(notes)
    draft["qualified_invoice_number"] = extract_qualified_invoice_number(joined, draft["confidence_notes"])
    draft["receipt_date"] = extract_receipt_date(joined, draft["confidence_notes"])
    draft["total_amount"] = extract_labeled_amount(joined, ["総合計", "税込合計", "お買上げ合計", "お買上げ", "請求金額", "領収金額", "お支払い金額", "合計金額", "合計"], ["小計", "税", "消費税", "値引"])
    draft["tax_amount"] = extract_labeled_amount(joined, ["消費税等", "内消費税等", "内消費税", "消費税", "消{税等", "税額"], [])
    draft["amount_excluding_tax"] = extract_labeled_amount(joined, ["税抜金額", "税抜", "本体価格", "対象額", "小計"], ["消費税"])
    draft["tax_rate"] = extract_tax_rate(joined)
    draft["vendor_name"] = extract_vendor_name(lines, draft["confidence_notes"])
    draft["invoice_or_receipt_number"] = extract_receipt_number(joined)
    draft["payment_method"] = extract_payment_method(joined)
    draft["expense_category"] = extract_expense_category(joined)
    draft["currency"] = "JPY"
    draft["requires_manual_review"] = True
    if not draft["vendor_name"]:
        draft["confidence_notes"].append("Vendor name was not confidently recognized.")
    if not draft["receipt_date"]:
        draft["confidence_notes"].append("Receipt/invoice date was not confidently recognized.")
    if not draft["total_amount"]:
        draft["confidence_notes"].append("Total amount was not confidently recognized.")
    return draft


def extract_qualified_invoice_number(text: str, notes: list[str]) -> Optional[str]:
    candidates = []
    for match in re.finditer(r"T[ \t\-]*\d(?:[\d \t\-]{11,20})", text, flags=re.IGNORECASE):
        normalized = re.sub(r"[^Tt0-9]", "", match.group(0)).upper()
        if re.fullmatch(r"T\d{13}", normalized):
            candidates.append(normalized)
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        notes.append("Multiple qualified invoice number candidates were found; the first one was used.")
    return unique[0] if unique else None


def extract_receipt_date(text: str, notes: list[str]) -> Optional[str]:
    labeled_patterns = [
        r"(?:領収日|発行日|取引年月日|利用日|日付)\D{0,8}(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        r"(?:領収日|発行日|取引年月日|利用日|日付)\D{0,8}令和\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        r"(?:領収日|発行日|取引年月日|利用日|日付)\D{0,8}R\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
    ]
    for pattern in labeled_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return normalize_date_match(match.groups())
    candidates = []
    for pattern in [
        r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        r"令和\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
        r"R\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?",
    ]:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            parsed = normalize_date_match(match.groups())
            if parsed:
                candidates.append(parsed)
    unique = list(dict.fromkeys(candidates))
    if len(unique) == 1:
        return unique[0]
    if len(unique) > 1:
        notes.append("Multiple date candidates were found; date was left blank for manual review.")
    return None


def normalize_date_match(groups: tuple[str, ...]) -> Optional[str]:
    try:
        first = int(groups[0])
        if first < 100:
            year = 2018 + first
        else:
            year = first
        month = int(groups[1])
        day = int(groups[2])
        candidate = f"{year:04d}-{month:02d}-{day:02d}"
        validate_date(candidate, "OCR Date")
        return candidate
    except (ValueError, IndexError):
        return None


def extract_labeled_amount(text: str, labels: list[str], excluded_nearby: list[str]) -> Optional[int]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        matching_label = next((label for label in labels if label in line), "")
        if not matching_label:
            continue
        if any(excluded in line and excluded not in matching_label for excluded in excluded_nearby):
            continue
        amount = None if "%" in line and not any(symbol in line for symbol in ["¥", "￥", "円"]) else extract_first_positive_amount(line)
        if amount is not None:
            return amount
        for next_line in lines[index + 1: index + 3]:
            if any(excluded in next_line and excluded not in matching_label for excluded in excluded_nearby):
                break
            amount = extract_first_positive_amount(next_line)
            if amount is not None:
                return amount
    for label in labels:
        pattern = rf"{re.escape(label)}[\s\S]{{0,30}}?[¥￥]?\s*([0-9][0-9,]*)\s*円?"
        for match in re.finditer(pattern, text):
            nearby = text[max(0, match.start() - 8): match.end() + 8]
            if any(excluded in nearby and excluded not in label for excluded in excluded_nearby):
                continue
            amount = parse_amount_text(match.group(1))
            if amount is not None:
                return amount
    return None


def extract_first_positive_amount(text: str) -> Optional[int]:
    preferred_patterns = [
        r"(?<![-−])[¥￥]\s*([0-9][0-9,]*)",
        r"(?<![-−])([0-9][0-9,]*)\s*円",
    ]
    for pattern in preferred_patterns:
        for match in re.finditer(pattern, text):
            amount = parse_amount_text(match.group(1))
            if amount is not None:
                return amount
    for match in re.finditer(r"(?<![-−])([0-9][0-9,]*)", text):
        amount = parse_amount_text(match.group(1))
        if amount is not None:
            return amount
    return None


def parse_amount_text(value: str) -> Optional[int]:
    cleaned = re.sub(r"[^0-9]", "", value or "")
    if not cleaned:
        return None
    try:
        return int(cleaned)
    except ValueError:
        return None


def extract_tax_rate(text: str) -> str:
    has_10 = bool(re.search(r"10\s*%|10\s*パーセント", text))
    has_8 = bool(re.search(r"8\s*%|8\s*パーセント|軽減税率", text))
    has_zero = any(keyword in text for keyword in ["非課税", "不課税", "免税"])
    if has_10 and has_8:
        return "mixed"
    if has_10:
        return "10%"
    if has_8:
        return "8%"
    if has_zero:
        return "0%"
    return "unknown"


def extract_vendor_name(lines: list[str], notes: list[str]) -> Optional[str]:
    skip_keywords = ["領収書", "請求書", "レシート", "納品書", "登録番号", "TEL", "電話", "住所", "合計", "消費税", "日付"]
    company_keywords = ["株式会社", "有限会社", "合同会社", "Co.", "Ltd", "Inc."]
    clean_lines = [line for line in lines[:12] if len(line) >= 2 and not any(keyword in line for keyword in skip_keywords)]
    for line in clean_lines:
        if any(keyword in line for keyword in company_keywords):
            return trim_vendor_line(line)
    for line in clean_lines[:5]:
        if not re.search(r"[0-9]{3,}|[¥円]", line):
            notes.append("Vendor name candidate was selected from the top OCR text and must be reviewed.")
            return trim_vendor_line(line)
    return None


def trim_vendor_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip(" -*:：")[:80]


def extract_receipt_number(text: str) -> Optional[str]:
    patterns = [
        r"(?:領収書番号|請求書番号|伝票番号|取引番号|No\.?|番号)\s*[:：#]?\s*([A-Za-z0-9\-]{3,30})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip()
        if not re.fullmatch(r"T\d{13}", value.upper()):
            return value
    return None


def extract_payment_method(text: str) -> Optional[str]:
    if any(keyword in text for keyword in ["法人カード", "会社カード"]):
        return "company_card"
    if any(keyword in text for keyword in ["振込", "銀行振込"]):
        return "bank_transfer"
    if any(keyword in text for keyword in ["現金", "クレジット", "カード", "VISA", "Master", "JCB", "AMEX", "PayPay", "Suica", "PASMO"]):
        return "employee_paid"
    return None


def extract_expense_category(text: str) -> str:
    category_keywords = [
        ("transportation", ["JR", "地下鉄", "電車", "駅", "タクシー", "交通", "高速", "駐車場"]),
        ("meal", ["レストラン", "居酒屋", "カフェ", "喫茶", "食堂", "ランチ", "飲食"]),
        ("accommodation", ["ホテル", "宿泊"]),
        ("communication", ["通信", "携帯", "郵便", "切手"]),
        ("office_expense", ["文具", "事務用品", "コピー", "印刷"]),
    ]
    for category, keywords in category_keywords:
        if any(keyword in text for keyword in keywords):
            return category
    return "unknown"


def build_mock_ocr_draft(attachment: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    draft = default_ocr_draft()
    draft.update(
        {
            "receipt_date": empty_to_none(form.get("ocr_receipt_date")),
            "vendor_name": empty_to_none(form.get("ocr_vendor_name")),
            "vendor_address": empty_to_none(form.get("ocr_vendor_address")),
            "invoice_or_receipt_number": empty_to_none(form.get("ocr_invoice_or_receipt_number")),
            "qualified_invoice_number": empty_to_none(form.get("ocr_qualified_invoice_number", "").upper()),
            "total_amount": optional_int(form.get("ocr_total_amount"), "OCR Total Amount"),
            "amount_excluding_tax": optional_int(form.get("ocr_amount_excluding_tax"), "OCR Amount Excluding Tax"),
            "tax_amount": optional_int(form.get("ocr_tax_amount"), "OCR Tax Amount"),
            "tax_rate": empty_to_none(form.get("ocr_tax_rate")),
            "payment_method": empty_to_none(form.get("ocr_payment_method")),
            "expense_category": form.get("ocr_expense_category", "unknown").strip() or "unknown",
            "employee_name_if_present": empty_to_none(form.get("ocr_employee_name_if_present")),
            "confidence_notes": [
                "OCR-style draft generated locally from the uploaded attachment; no real OCR provider is connected yet.",
                f"Uploaded attachment: {attachment.get('original_filename', '-')}",
                "Please review, correct, and complete the standard claim form before saving or submitting.",
            ],
            "requires_manual_review": True,
        }
    )
    return normalize_ocr_draft(draft)


def normalize_ocr_draft(draft: dict[str, Any]) -> dict[str, Any]:
    normalized = default_ocr_draft()
    normalized.update(draft or {})
    for key in [
        "receipt_date",
        "vendor_name",
        "vendor_address",
        "invoice_or_receipt_number",
        "qualified_invoice_number",
        "tax_rate",
        "payment_method",
        "employee_name_if_present",
    ]:
        normalized[key] = empty_to_none(normalized.get(key))
    normalized["currency"] = str(normalized.get("currency") or "JPY").strip() or "JPY"
    normalized["expense_category"] = str(normalized.get("expense_category") or "unknown").strip() or "unknown"
    if normalized["expense_category"] not in {option[0] for option in CATEGORIES} | {"unknown"}:
        normalized["expense_category"] = "unknown"
    if normalized["tax_rate"] not in set(TAX_RATES) | {None}:
        normalized["tax_rate"] = "unknown"
    if normalized["payment_method"] not in {option[0] for option in PAYMENT_METHODS} | {None}:
        normalized["payment_method"] = None
    for key, label in [
        ("total_amount", "OCR Total Amount"),
        ("amount_excluding_tax", "OCR Amount Excluding Tax"),
        ("tax_amount", "OCR Tax Amount"),
    ]:
        normalized[key] = optional_int(normalized.get(key), label)
    invoice_number = normalized.get("qualified_invoice_number")
    if invoice_number and (len(str(invoice_number)) != 14 or not str(invoice_number).startswith("T") or not str(invoice_number)[1:].isdigit()):
        notes = normalized.get("confidence_notes") if isinstance(normalized.get("confidence_notes"), list) else []
        notes.append("Qualified invoice number hint was ignored because it was not T followed by 13 digits.")
        normalized["confidence_notes"] = notes
        normalized["qualified_invoice_number"] = None
    if not isinstance(normalized.get("confidence_notes"), list):
        normalized["confidence_notes"] = [str(normalized.get("confidence_notes"))]
    normalized["requires_manual_review"] = True
    return normalized


def apply_ocr_draft_to_claim_defaults(record: dict[str, Any]) -> dict[str, Any]:
    draft = normalize_ocr_draft(record.get("ocr_draft") or {})
    record = dict(record)
    for mapping in OCR_TO_CLAIM_FIELD_MAPPING:
        source, target = mapping[0], mapping[1]
        value_to_apply = draft.get(source)
        if value_to_apply not in (None, "", "unknown"):
            record[target] = value_to_apply
    record["currency"] = draft.get("currency") or "JPY"
    record["ocr_draft"] = draft
    return record


def apply_upload_context_to_claim(record: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    record = dict(record)
    for field in OCR_CONTEXT_FIELDS:
        value_to_apply = form.get(field, "").strip()
        if value_to_apply:
            record[field] = value_to_apply
    return record


def preserve_manual_form_values(record: dict[str, Any], form: dict[str, str]) -> dict[str, Any]:
    record = dict(record)
    defaults = default_claim_record()
    for field in STANDARD_CLAIM_INPUT_FIELDS:
        raw_value = form.get(field, "")
        text_value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip()
        if not text_value:
            continue
        if field in MONEY_INPUT_FIELDS:
            parsed_value = parse_non_negative_int(text_value, field.replace("_", " ").title())
            if parsed_value > 0:
                record[field] = parsed_value
            continue
        if field in SELECT_INPUT_FIELDS:
            if text_value != str(defaults.get(field, "")):
                record[field] = text_value
            continue
        record[field] = text_value.upper() if field == "qualified_invoice_number" else text_value
    return record


def validate_ocr_draft_record(record: dict[str, Any]) -> None:
    if not record.get("claim_id") or not record.get("claim_no"):
        raise ValueError("OCR draft claim ID and claim number are required.")
    if not record.get("attachment"):
        raise ValueError("OCR draft requires a saved attachment.")
    if record.get("status") != "Draft" or record.get("record_status") != "Active":
        raise ValueError("OCR draft claims must start as active Draft records.")
    if record.get("ocr_status") not in OCR_STATUSES:
        raise ValueError("OCR status is invalid.")
    draft = normalize_ocr_draft(record.get("ocr_draft") or {})
    if not draft.get("requires_manual_review"):
        raise ValueError("OCR draft must require manual review.")


def empty_to_none(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def optional_int(value: Any, label: str) -> Optional[int]:
    if value is None or value == "":
        return None
    return parse_non_negative_int(value, label)


def save_claim(record: dict[str, Any], upload: Optional[tuple[str, bytes, str]], user: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_claims(include_deleted=True)
    record = dict(record)
    apply_current_entity_snapshot(record, user)
    validate_claim_record(record, require_attachment=record.get("status") == "Submitted" and upload is None)
    ensure_month_not_payment_closed(str(record.get("claim_month", "")), user)
    now = datetime.now(timezone.utc)
    record["claim_id"] = f"claim-{now.strftime('%Y%m%d%H%M%S%f')}"
    record["claim_no"] = next_claim_no(records, record.get("claim_month", ""), now)
    record["record_status"] = "Active"
    record["created_at"] = now.isoformat()
    record["updated_at"] = now.isoformat()
    if record.get("status") == "Submitted":
        record["submitted_at"] = now.isoformat()
    record["attachment"] = save_attachment(record["claim_id"], upload)
    if record.get("status") == "Submitted" and not record["attachment"]:
        raise ValueError("Receipt/invoice attachment is required before Submit.")
    records.append(record)
    write_json_array(CLAIMS_PATH, records)
    if record.get("status") == "Submitted":
        append_approval_log(record, "submit", actor_from_user(user) if user else claim_actor(record), "", "Submitted", "Claim submitted by employee.")
    append_audit_log("reimbursement.claim", str(record.get("claim_id", "")), "submit" if record.get("status") == "Submitted" else "create_draft", {}, dict(record), user)
    return record


def update_claim(record: dict[str, Any], upload: Optional[tuple[str, bytes, str]], user: dict[str, Any] | None = None) -> dict[str, Any]:
    records = load_claims(include_deleted=True)
    claim_id = str(record.get("claim_id", "")).strip()
    if not claim_id:
        raise ValueError("Claim record ID is required.")
    existing_record: Optional[dict[str, Any]] = None
    before_status = ""
    for item in records:
        if item.get("claim_id") == claim_id:
            existing_record = dict(item)
            before_status = str(item.get("status", ""))
            break
    if not existing_record:
        raise ValueError("Claim record was not found.")
    if not record_entity_matches(existing_record, user):
        if not (user and can_view_own_claims(user) and is_own_claim(user, existing_record) and not record_has_entity(existing_record)):
            raise ValueError("Claim belongs to another Entity or cannot be updated by this account.")
    if record_has_entity(existing_record):
        record["entity_id"] = existing_record.get("entity_id", "")
        record["entity_code"] = existing_record.get("entity_code", "")
        record["entity_name"] = existing_record.get("entity_name", "")
    else:
        apply_current_entity_snapshot(record, user)
    validate_claim_record(record, require_attachment=record.get("status") == "Submitted" and not record.get("attachment") and upload is None)
    ensure_month_not_payment_closed(str(record.get("claim_month", "")), user)
    new_attachment = save_attachment(claim_id, upload)
    if new_attachment:
        record["attachment"] = new_attachment
    if record.get("status") == "Submitted" and not record.get("submitted_at"):
        record["submitted_at"] = datetime.now(timezone.utc).isoformat()
    updated_records = []
    updated = False
    for item in records:
        if item.get("claim_id") == claim_id:
            updated_records.append(record)
            updated = True
        else:
            updated_records.append(item)
    if not updated:
        raise ValueError("Claim record was not found.")
    audit_action = "update_draft"
    if record.get("status") == "Submitted" and before_status != "Submitted":
        audit_action = "resubmit" if before_status == "Rejected" else "submit"
    if records_business_equal(existing_record, record):
        unchanged = dict(existing_record)
        unchanged["_no_changes"] = True
        return unchanged
    write_json_array(CLAIMS_PATH, updated_records)
    if audit_action in {"submit", "resubmit"}:
        append_approval_log(record, "submit", actor_from_user(user) if user else claim_actor(record), before_status, "Submitted", "Claim submitted by employee.")
    append_audit_log("reimbursement.claim", claim_id, audit_action, existing_record, dict(record), user)
    return record


def finance_update_claim(claim_id: str, action: str, finance_notes: str = "", reject_reason: str = "", actor: str = DEFAULT_FINANCE_ACTOR, user: dict[str, Any] | None = None) -> dict[str, Any]:
    claim_id = claim_id.strip()
    if not claim_id:
        raise ValueError("Claim record ID is required.")
    action = action.strip().lower()
    if action not in {"approve", "reject"}:
        raise ValueError("Finance action is invalid.")
    records = load_claims(include_deleted=True)
    now = datetime.now(timezone.utc)
    updated_record: Optional[dict[str, Any]] = None
    before_value: Optional[dict[str, Any]] = None
    before_status = ""
    for record in records:
        if record.get("claim_id") != claim_id:
            continue
        require_record_entity_access(record, user, "Claim")
        if record.get("record_status", "Active") == "Deleted":
            raise ValueError("Deleted claims cannot be approved or rejected.")
        before_value = dict(record)
        before_status = str(record.get("status", ""))
        if before_status != "Submitted":
            raise ValueError("Only Submitted claims can be approved or rejected by finance.")
        ensure_month_not_payment_closed(str(record.get("claim_month", "")), user)
        record["finance_notes"] = finance_notes.strip()
        record["updated_at"] = now.isoformat()
        if action == "approve":
            record["status"] = "Approved"
            record["approved_at"] = now.isoformat()
            record["approved_by"] = actor
            record["reject_reason"] = ""
            log_notes = finance_notes.strip()
        else:
            reject_reason = reject_reason.strip()
            if not reject_reason:
                raise ValueError("Reject Reason / 差戻し理由 is required when rejecting a claim.")
            record["status"] = "Rejected"
            record["rejected_at"] = now.isoformat()
            record["rejected_by"] = actor
            record["reject_reason"] = reject_reason
            log_notes = f"{finance_notes.strip()} Reason: {reject_reason}".strip()
        updated_record = dict(record)
        break
    if not updated_record or before_value is None:
        raise ValueError("Claim record was not found.")
    write_json_array(CLAIMS_PATH, records)
    append_approval_log(updated_record, action, actor, before_status, str(updated_record.get("status", "")), log_notes)
    append_audit_log("reimbursement.claim", claim_id, action, before_value, dict(updated_record), user)
    return updated_record


def soft_delete_claim(claim_id: str, user: dict[str, Any] | None = None) -> bool:
    claim_id = claim_id.strip()
    records = load_claims(include_deleted=True)
    now = datetime.now(timezone.utc).isoformat()
    updated = False
    before_value: Optional[dict[str, Any]] = None
    after_value: Optional[dict[str, Any]] = None
    for record in records:
        if record.get("claim_id") == claim_id:
            if not claim_is_editable(record):
                raise ValueError("Only Draft or Rejected claims can be deleted.")
            if not can_access_claim(user, record) if user else False:
                raise ValueError("You can only delete your own reimbursement claims in the current Entity.")
            ensure_month_not_payment_closed(str(record.get("claim_month", "")), user)
            before_value = dict(record)
            record["record_status"] = "Deleted"
            record["updated_at"] = now
            after_value = dict(record)
            updated = True
            break
    if updated:
        write_json_array(CLAIMS_PATH, records)
        append_audit_log("reimbursement.claim", claim_id, "soft_delete", before_value or {}, after_value or {}, user)
    return updated


def validate_claim_record(record: dict[str, Any], require_attachment: bool = False) -> None:
    status = str(record.get("status", "Draft"))
    if status not in {option[0] for option in CLAIM_STATUSES}:
        raise ValueError("Claim status is invalid.")
    is_submitted = status == "Submitted"
    required_fields = [
        ("employee_no", "Employee No. / 社員No."),
        ("employee_name", "Employee Name / 氏名"),
        ("claim_month", "Claim Month / 精算月"),
        ("expense_date", "Expense Date / 利用日"),
        ("category", "Category / 費用区分"),
        ("currency", "Currency / 通貨"),
        ("business_purpose", "Business Purpose / 利用目的"),
    ]
    if is_submitted:
        missing = [label for key, label in required_fields if not str(record.get(key, "")).strip()]
        if missing:
            raise ValueError(f"Required fields are missing: {', '.join(missing)}")
    claim_month = str(record.get("claim_month", "")).strip()
    expense_date = str(record.get("expense_date", "")).strip()
    if claim_month:
        validate_month(claim_month)
    elif is_submitted:
        raise ValueError("Claim Month / 精算月 is required.")
    if expense_date:
        validate_date(expense_date, "Expense Date")
    elif is_submitted:
        raise ValueError("Expense Date / 利用日 is required.")
    category = str(record.get("category", "")).strip()
    if category and category not in {option[0] for option in CATEGORIES}:
        raise ValueError("Expense category is invalid.")
    elif is_submitted and not category:
        raise ValueError("Category / 費用区分 is required.")
    tax_rate = str(record.get("tax_rate", "")).strip()
    if tax_rate and tax_rate not in set(TAX_RATES):
        raise ValueError("Tax rate is invalid.")
    payment_method = str(record.get("payment_method", "")).strip()
    if payment_method and payment_method not in {option[0] for option in PAYMENT_METHODS}:
        raise ValueError("Payment method is invalid.")
    if record.get("is_qualified_invoice") not in {option[0] for option in QUALIFIED_INVOICE_OPTIONS}:
        raise ValueError("Invoice status is invalid.")
    total_amount = parse_non_negative_int(record.get("total_amount", 0), "Total Amount")
    amount_excluding_tax = parse_non_negative_int(record.get("amount_excluding_tax", 0), "Amount Excluding Tax")
    tax_amount = parse_non_negative_int(record.get("tax_amount", 0), "Tax Amount")
    if is_submitted and total_amount <= 0:
        raise ValueError("Total Amount must be greater than 0.")
    if total_amount > 0 or amount_excluding_tax > 0 or tax_amount > 0:
        if tax_amount > total_amount:
            raise ValueError("Tax Amount cannot be greater than Total Amount.")
        if amount_excluding_tax > total_amount:
            raise ValueError("Amount Excluding Tax cannot be greater than Total Amount.")
        if amount_excluding_tax + tax_amount != total_amount:
            raise ValueError("Amount Excluding Tax plus Tax Amount must equal Total Amount.")
    invoice_number = str(record.get("qualified_invoice_number", "")).strip()
    if invoice_number and (len(invoice_number) != 14 or not invoice_number.startswith("T") or not invoice_number[1:].isdigit()):
        raise ValueError("Qualified Invoice No. must be T followed by 13 digits, for example T1234567890123.")
    if require_attachment:
        raise ValueError("Receipt/invoice attachment is required.")


def next_expensebill_filename(original_filename: str, now: Optional[datetime] = None) -> str:
    now = now or datetime.now()
    date_text = now.strftime("%Y%m%d")
    prefix = f"exp{date_text}"
    extension = Path(original_filename).suffix.lower()
    existing_sequences: list[int] = []
    if EXPENSEBILL_DIR.exists():
        for path in EXPENSEBILL_DIR.glob(f"{prefix}[0-9][0-9][0-9][0-9]*"):
            sequence_text = path.stem.replace(prefix, "", 1)[:4]
            if sequence_text.isdigit():
                existing_sequences.append(int(sequence_text))
    for record in load_claims(include_deleted=True):
        attachment = record.get("attachment") or {}
        stored_filename = str(attachment.get("stored_filename", ""))
        if stored_filename.startswith(prefix):
            sequence_text = Path(stored_filename).stem.replace(prefix, "", 1)[:4]
            if sequence_text.isdigit():
                existing_sequences.append(int(sequence_text))
    next_sequence = max(existing_sequences, default=0) + 1
    return f"{prefix}{next_sequence:04d}{extension}"


def save_attachment(claim_id: str, upload: Optional[tuple[str, bytes, str]]) -> Optional[dict[str, Any]]:
    if not upload:
        return None
    filename, content, content_type = upload
    if not filename or not content:
        return None
    original_filename = filename.replace("\\", "/").rsplit("/", 1)[-1]
    extension = Path(original_filename).suffix.lower()
    if extension not in ALLOWED_ATTACHMENT_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_ATTACHMENT_EXTENSIONS))
        raise ValueError(f"Attachment type is not supported. Allowed extensions: {allowed}.")
    if len(content) > MAX_ATTACHMENT_BYTES:
        raise ValueError("Attachment must be 5 MB or smaller.")
    stored_filename = next_expensebill_filename(original_filename)
    EXPENSEBILL_DIR.mkdir(parents=True, exist_ok=True)
    stored_path = EXPENSEBILL_DIR / stored_filename
    stored_path.write_bytes(content)
    return {
        "original_filename": original_filename,
        "stored_filename": stored_filename,
        "relative_path": str(stored_path.relative_to(ROOT_DIR)),
        "content_type": content_type,
        "size_bytes": len(content),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def next_claim_no(records: list[dict[str, Any]], claim_month: str, now: datetime) -> str:
    year_text = (claim_month or str(now.year))[:4]
    year = year_text if year_text.isdigit() else str(now.year)
    prefix = f"R-{year}-"
    existing_numbers = []
    for record in records:
        number = str(record.get("claim_no", ""))
        if number.startswith(prefix):
            suffix = number.rsplit("-", 1)[-1]
            if suffix.isdigit():
                existing_numbers.append(int(suffix))
    return f"{prefix}{max(existing_numbers, default=0) + 1:04d}"


def calculate_claim_totals(claims: list[dict[str, Any]]) -> dict[str, int]:
    return {
        "total_amount": sum(parse_non_negative_int(claim.get("total_amount", 0), "Total Amount") for claim in claims),
        "amount_excluding_tax": sum(parse_non_negative_int(claim.get("amount_excluding_tax", 0), "Amount Excluding Tax") for claim in claims),
        "tax_amount": sum(parse_non_negative_int(claim.get("tax_amount", 0), "Tax Amount") for claim in claims),
    }


def default_claim_record() -> dict[str, Any]:
    return {
        "status": "Draft",
        "employee_no": "",
        "employee_name": "",
        "department": "",
        "claim_month": "",
        "expense_date": "",
        "category": "transportation",
        "vendor_name": "",
        "invoice_or_receipt_number": "",
        "qualified_invoice_number": "",
        "is_qualified_invoice": "unknown",
        "currency": "JPY",
        "total_amount": 0,
        "amount_excluding_tax": 0,
        "tax_amount": 0,
        "tax_rate": "10%",
        "payment_method": "employee_paid",
        "business_purpose": "",
        "notes": "",
        "finance_notes": "",
        "reject_reason": "",
        "attachment": None,
        "ocr_status": "not_run",
        "ocr_draft": default_ocr_draft(),
    }


def default_ocr_draft() -> dict[str, Any]:
    return {
        "receipt_date": None,
        "vendor_name": None,
        "vendor_address": None,
        "invoice_or_receipt_number": None,
        "qualified_invoice_number": None,
        "currency": "JPY",
        "total_amount": None,
        "amount_excluding_tax": None,
        "tax_amount": None,
        "tax_rate": None,
        "payment_method": None,
        "expense_category": "unknown",
        "employee_name_if_present": None,
        "confidence_notes": [],
        "requires_manual_review": True,
    }


def claim_is_editable(record: dict[str, Any]) -> bool:
    return record.get("record_status", "Active") != "Deleted" and record.get("status", "Draft") in {"Draft", "Rejected"}


def category_label(category: str) -> str:
    return escape(category_label_text(category))


def category_label_text(category: str) -> str:
    for key, label in CATEGORIES:
        if key == category:
            return label
    return category or "-"


def payment_method_label(payment_method: str) -> str:
    for key, label in PAYMENT_METHODS:
        if key == payment_method:
            return label
    return payment_method or "-"


def validate_month(value: str) -> None:
    if len(value) != 7 or value[4] != "-" or not value[:4].isdigit() or not value[5:].isdigit():
        raise ValueError("Claim Month must use YYYY-MM format.")
    month = int(value[5:])
    if not 1 <= month <= 12:
        raise ValueError("Claim Month month must be between 01 and 12.")


def validate_date(value: str, label: str) -> None:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise ValueError(f"{label} must use YYYY-MM-DD format.") from exc


def parse_non_negative_int(value: Any, label: str) -> int:
    if value is None or value == "":
        return 0
    try:
        parsed = int(str(value).replace(",", "").replace("¥", "").strip())
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must be an integer yen amount.") from exc
    if parsed < 0:
        raise ValueError(f"{label} cannot be negative.")
    return parsed


def safe_filename(filename: str) -> str:
    cleaned = filename.replace("\\", "/").rsplit("/", 1)[-1].strip()
    cleaned = "".join(ch if ch.isalnum() or ch in {".", "_", "-"} else "_" for ch in cleaned)
    cleaned = cleaned.strip("._") or "attachment"
    if len(cleaned) > 120:
        suffix = Path(cleaned).suffix
        stem = cleaned[: 120 - len(suffix)] if suffix else cleaned[:120]
        cleaned = f"{stem}{suffix}"
    return cleaned


def select_options(options: list[tuple[str, str]], selected: str) -> str:
    option_html = []
    for option_value, label in options:
        selected_attr = " selected" if option_value == selected else ""
        option_html.append(f"<option value='{escape(option_value)}'{selected_attr}>{escape(label)}</option>")
    return "".join(option_html)


def value(record: dict[str, Any], key: str) -> str:
    return escape(str(record.get(key, "") if record.get(key, "") is not None else ""))


def money(value: Any) -> str:
    amount = parse_non_negative_int(value, "Amount")
    return f"¥{amount:,}"


def run(host: str = "127.0.0.1", port: int = 8003) -> None:
    server = ThreadingHTTPServer((host, port), TACReimbursementHandler)
    print(f"TAC-reimbursement running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TAC-reimbursement.")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TAC-reimbursement local web app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8003)
    args = parser.parse_args()
    run(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
