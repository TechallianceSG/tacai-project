#!/usr/bin/env python3
"""TACAI Master Data Management local web app.

This module intentionally uses only Python standard library modules so it can
run locally without installing dependencies.
"""

from __future__ import annotations

import argparse
import cgi
import copy
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Optional
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
I18N_DIR = ROOT_DIR / "i18n"
ENTITIES_PATH = DATABASE_DIR / "entities.json"
DEPARTMENTS_PATH = DATABASE_DIR / "departments.json"
TEAMS_PATH = DATABASE_DIR / "teams.json"
CUSTOMERS_PATH = DATABASE_DIR / "customers.json"
VENDORS_PATH = DATABASE_DIR / "vendors.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
MASTERDATA_VERSIONS_PATH = DATABASE_DIR / "masterdata_versions.json"
SYSTEM_PARAMETERS_PATH = DATABASE_DIR / "system_parameters.json"
STORAGE_DIR = ROOT_DIR / "storage"
VENDOR_OCR_UPLOAD_DIR = STORAGE_DIR / "vendor_ocr_uploads"
CUSTOMER_OCR_UPLOAD_DIR = STORAGE_DIR / "customer_ocr_uploads"
MACOS_VISION_OCR_SCRIPT = ROOT_DIR / "backend" / "macos_vision_ocr.swift"

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009}


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


APP_BASE_URL = local_base_url(8007)
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", local_base_url(8005)).strip() or local_base_url(8005)).rstrip("/")
USER_ADMIN_BASE_URL = local_base_url(8006)
USER_ADMIN_INTERNAL_BASE_URL = internal_base_url(8006)
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "tacai_flash"
MODULE_NAME = "masterdata"
DEFAULT_LANG = "en"
SUPPORTED_LANGS = {"en", "ja", "zh"}
STATUS_VALUES = {"active", "inactive", "deleted"}
SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID = "email.onboarding.smtp"
MASTERDATA_INTERNAL_API_TOKEN = os.environ.get("MASTERDATA_INTERNAL_API_TOKEN", "").strip()
ONBOARDING_EMAIL_SENDER = os.environ.get("ONBOARDING_EMAIL_SENDER", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
ONBOARDING_EMAIL_REPLY_TO = os.environ.get("ONBOARDING_EMAIL_REPLY_TO", ONBOARDING_EMAIL_SENDER).strip() or ONBOARDING_EMAIL_SENDER
ONBOARDING_HR_NOTIFICATION_EMAIL = os.environ.get("ONBOARDING_HR_NOTIFICATION_EMAIL", ONBOARDING_EMAIL_SENDER).strip() or ONBOARDING_EMAIL_SENDER
ONBOARDING_SMTP_HOST = os.environ.get("ONBOARDING_SMTP_HOST", "").strip()
ONBOARDING_SMTP_PORT = int(os.environ.get("ONBOARDING_SMTP_PORT", "587") or "587")
ONBOARDING_SMTP_USERNAME = os.environ.get("ONBOARDING_SMTP_USERNAME", "").strip()
ONBOARDING_SMTP_USE_TLS = os.environ.get("ONBOARDING_SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no", "off"}
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SUPPLIER_RECORD_MODES = {"standard_vendor", "one_time_vendor"}
CUSTOMER_RECORD_MODES = {"standard_customer", "one_time_customer"}
ONE_TIME_CODE_SUFFIX = "9999"
VENDOR_OCR_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
VENDOR_OCR_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
CUSTOMER_OCR_MAX_UPLOAD_BYTES = VENDOR_OCR_MAX_UPLOAD_BYTES
CUSTOMER_OCR_ALLOWED_EXTENSIONS = VENDOR_OCR_ALLOWED_EXTENSIONS


MASTERDATA_VERSION_FIELDS = {
    "entity": ["entity_code", "entity_type", "legal_name", "entity_name_en", "entity_name_ja", "entity_name_zh", "registration_number", "tax_registration_number", "country", "currency", "status"],
    "department": ["department_code", "department_name_en", "department_name_ja", "department_name_zh", "entity_id", "status"],
    "team": ["team_code", "team_name_en", "team_name_ja", "team_name_zh", "department_id", "status"],
    "customer": [
        "customer_code",
        "customer_record_mode",
        "customer_name",
        "customer_name_en",
        "customer_name_zh",
        "customer_registration_number",
        "billing_address",
        "billing_contact_name",
        "billing_contact_email",
        "default_language",
        "default_payment_terms_days",
        "default_tax_rate",
        "business_types",
        "notes",
        "status",
    ],
    "vendor": [
        "vendor_code",
        "vendor_name_en",
        "vendor_name_ja",
        "vendor_name_zh",
        "vendor_name_kana",
        "vendor_type",
        "supplier_record_mode",
        "entity_id",
        "country",
        "postal_code",
        "address",
        "qualified_invoice_number",
        "is_qualified_invoice_vendor",
        "contact_person",
        "email",
        "phone",
        "bank_name",
        "bank_branch",
        "bank_account_type",
        "bank_account_number_masked",
        "bank_account_holder",
        "payment_terms",
        "default_currency",
        "notes",
        "status",
    ],
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def h(value: Any) -> str:
    return escape(str(value or ""), quote=True)


def config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def config_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def checked(value: Any) -> str:
    return " checked" if config_bool(value, False) else ""


def selected(current: Any, value: str) -> str:
    return " selected" if str(current) == str(value) else ""


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def save_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp_path.replace(path)


def next_id(records: list[dict[str, Any]], field: str, prefix: str, width: int) -> str:
    max_number = 0
    for record in records:
        value = str(record.get(field, ""))
        if value.startswith(prefix):
            suffix = value[len(prefix):]
            if suffix.isdigit():
                max_number = max(max_number, int(suffix))
    return f"{prefix}{max_number + 1:0{width}d}"


def ensure_database_files() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    VENDOR_OCR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    CUSTOMER_OCR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for path in (ENTITIES_PATH, DEPARTMENTS_PATH, TEAMS_PATH, CUSTOMERS_PATH, VENDORS_PATH, AUDIT_LOGS_PATH, MASTERDATA_VERSIONS_PATH):
        if not path.exists():
            save_json_array(path, [])


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


def t(messages: dict[str, str], key: str, default: Optional[str] = None) -> str:
    return messages.get(key, default if default is not None else key)


def get_lang(query: dict[str, list[str]]) -> str:
    lang = query.get("lang", [DEFAULT_LANG])[0]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def url_with_lang(path: str, lang: str, params: Optional[dict[str, str]] = None) -> str:
    query = {"lang": lang}
    if params:
        query.update({key: value for key, value in params.items() if value != ""})
    return f"{path}?{urlencode(query)}"


def load_entities() -> list[dict[str, Any]]:
    return load_json_array(ENTITIES_PATH)


def save_entities(records: list[dict[str, Any]]) -> None:
    save_json_array(ENTITIES_PATH, records)


def load_departments() -> list[dict[str, Any]]:
    return load_json_array(DEPARTMENTS_PATH)


def save_departments(records: list[dict[str, Any]]) -> None:
    save_json_array(DEPARTMENTS_PATH, records)


def load_teams() -> list[dict[str, Any]]:
    return load_json_array(TEAMS_PATH)


def save_teams(records: list[dict[str, Any]]) -> None:
    save_json_array(TEAMS_PATH, records)


def load_customers() -> list[dict[str, Any]]:
    return load_json_array(CUSTOMERS_PATH)


def save_customers(records: list[dict[str, Any]]) -> None:
    save_json_array(CUSTOMERS_PATH, records)


def load_vendors() -> list[dict[str, Any]]:
    return load_json_array(VENDORS_PATH)


def save_vendors(records: list[dict[str, Any]]) -> None:
    save_json_array(VENDORS_PATH, records)


def load_audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def save_audit_logs(records: list[dict[str, Any]]) -> None:
    save_json_array(AUDIT_LOGS_PATH, records)


def load_masterdata_versions() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_VERSIONS_PATH)


def save_masterdata_versions(records: list[dict[str, Any]]) -> None:
    save_json_array(MASTERDATA_VERSIONS_PATH, records)




def load_system_parameters() -> list[dict[str, Any]]:
    parameters = [normalize_system_parameter(record) for record in load_json_array(SYSTEM_PARAMETERS_PATH)]
    if not any(record.get("parameter_id") == SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID for record in parameters):
        parameters.append(default_outbound_email_parameter())
    parameters.sort(key=lambda item: (config_int(item.get("sort_order", 100), 100), str(item.get("parameter_id", ""))))
    return parameters


def save_system_parameters(records: list[dict[str, Any]]) -> None:
    save_json_array(SYSTEM_PARAMETERS_PATH, [normalize_system_parameter(record) for record in records])


def find_system_parameter(parameter_id: str) -> Optional[dict[str, Any]]:
    for parameter in load_system_parameters():
        if parameter.get("parameter_id") == parameter_id:
            return parameter
    return None


def upsert_system_parameter(parameter: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_system_parameter(parameter)
    records = load_system_parameters()
    replaced = False
    for index, record in enumerate(records):
        if record.get("parameter_id") == normalized.get("parameter_id"):
            records[index] = normalized
            replaced = True
            break
    if not replaced:
        records.append(normalized)
    save_system_parameters(records)
    return normalized


def outbound_email_secret_status(value: dict[str, Any]) -> str:
    mode = str(value.get("password_config_mode", "environment") or "environment").strip()
    secret_ref = str(value.get("password_secret_ref", "ONBOARDING_SMTP_PASSWORD") or "ONBOARDING_SMTP_PASSWORD").strip()
    if mode in {"environment", "secret_ref"}:
        return "configured" if secret_ref and os.environ.get(secret_ref) else "missing"
    if mode == "encrypted":
        return "encrypted_unsupported"
    return "missing"


def resolve_outbound_email_password(value: dict[str, Any]) -> tuple[str, str]:
    mode = str(value.get("password_config_mode", "environment") or "environment").strip()
    secret_ref = str(value.get("password_secret_ref", "ONBOARDING_SMTP_PASSWORD") or "ONBOARDING_SMTP_PASSWORD").strip()
    if mode in {"environment", "secret_ref"}:
        password = os.environ.get(secret_ref, "") if secret_ref else ""
        return password, "available" if password else "missing"
    if mode == "encrypted":
        return "", "encrypted_unsupported"
    return "", "unsupported_password_mode"


def normalize_email_list(value: Any, max_count: int = 3) -> list[str]:
    raw_items: list[str] = []
    if isinstance(value, list):
        raw_items = [str(item or "") for item in value]
    else:
        raw = str(value or "")
        raw_items = re.split(r"[,;\n]", raw)
    emails: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        email = normalize_text(item)
        if not email:
            continue
        key = email.lower()
        if key in seen:
            continue
        seen.add(key)
        emails.append(email)
        if len(emails) >= max_count:
            break
    return emails


def validate_email_list(emails: list[str], messages: dict[str, str], max_count: int = 3) -> str:
    if len(emails) > max_count:
        return t(messages, "system_parameters.validation.department_manager_cc_limit")
    invalid = [email for email in emails if not EMAIL_PATTERN.fullmatch(email)]
    if invalid:
        return f"{t(messages, 'system_parameters.validation.department_manager_cc_invalid')}: {', '.join(invalid)}"
    return ""


def default_outbound_email_parameter(actor: str = "system") -> dict[str, Any]:
    timestamp = now_iso()
    value = {
        "sender_display_name": "TAC HR Admin",
        "sender_email": ONBOARDING_EMAIL_SENDER,
        "reply_to_email": ONBOARDING_EMAIL_REPLY_TO,
        "hr_notification_email": ONBOARDING_HR_NOTIFICATION_EMAIL,
        "department_manager_cc_emails": [],
        "smtp_host": ONBOARDING_SMTP_HOST,
        "smtp_port": ONBOARDING_SMTP_PORT,
        "smtp_username": ONBOARDING_SMTP_USERNAME,
        "smtp_use_tls": ONBOARDING_SMTP_USE_TLS,
        "smtp_use_ssl": ONBOARDING_SMTP_PORT == 465,
        "smtp_timeout_seconds": 15,
        "password_config_mode": "environment",
        "password_secret_ref": "ONBOARDING_SMTP_PASSWORD",
        "last_test_status": "",
        "last_test_at": "",
        "last_test_by": "",
        "last_test_error": "",
    }
    return {
        "parameter_id": SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID,
        "module": "masterdata.system_parameters",
        "category": "communication",
        "subcategory": "outbound_email",
        "scenario": "onboarding",
        "display_name": "Onboarding outbound email settings",
        "description": "SMTP settings for onboarding invitation, candidate verification, HR notifications, and return-to-candidate emails.",
        "enabled": True,
        "value_type": "object",
        "value": value,
        "secret_status": outbound_email_secret_status(value),
        "environment": "local",
        "status": "active",
        "sort_order": 10,
        "created_at": timestamp,
        "created_by": actor,
        "updated_at": timestamp,
        "updated_by": actor,
    }


def normalize_system_parameter(record: dict[str, Any]) -> dict[str, Any]:
    parameter_id = str(record.get("parameter_id", "") or "").strip()
    base = default_outbound_email_parameter() if parameter_id == SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID else {
        "parameter_id": parameter_id,
        "module": "masterdata.system_parameters",
        "category": str(record.get("category", "") or ""),
        "subcategory": str(record.get("subcategory", "") or ""),
        "scenario": str(record.get("scenario", "") or ""),
        "display_name": str(record.get("display_name", parameter_id) or parameter_id),
        "description": str(record.get("description", "") or ""),
        "enabled": config_bool(record.get("enabled", True), True),
        "value_type": str(record.get("value_type", "object") or "object"),
        "value": {},
        "secret_status": str(record.get("secret_status", "") or ""),
        "environment": str(record.get("environment", "local") or "local"),
        "status": str(record.get("status", "active") or "active"),
        "sort_order": config_int(record.get("sort_order", 100), 100),
        "created_at": str(record.get("created_at", "") or ""),
        "created_by": str(record.get("created_by", "") or ""),
        "updated_at": str(record.get("updated_at", "") or ""),
        "updated_by": str(record.get("updated_by", "") or ""),
    }
    result = copy.deepcopy(base)
    for key in result:
        if key == "value":
            if isinstance(record.get("value"), dict):
                result["value"].update(record["value"])
        elif key in record:
            result[key] = record[key]
    result["parameter_id"] = str(result.get("parameter_id", "") or "").strip()
    result["module"] = "masterdata.system_parameters"
    result["enabled"] = config_bool(result.get("enabled", True), True)
    result["sort_order"] = config_int(result.get("sort_order", 100), 100)
    result["status"] = str(result.get("status", "active") or "active").strip() or "active"
    if result["parameter_id"] == SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID:
        value = result["value"] if isinstance(result.get("value"), dict) else {}
        value["smtp_port"] = config_int(value.get("smtp_port", 587), 587)
        value["smtp_timeout_seconds"] = config_int(value.get("smtp_timeout_seconds", 15), 15)
        value["department_manager_cc_emails"] = normalize_email_list(value.get("department_manager_cc_emails", []), 3)
        value["smtp_use_tls"] = config_bool(value.get("smtp_use_tls", True), True)
        value["smtp_use_ssl"] = config_bool(value.get("smtp_use_ssl", False), False)
        if str(value.get("password_config_mode", "environment") or "environment") not in {"environment", "secret_ref"}:
            value["password_config_mode"] = "environment"
        result["value"] = value
        result["secret_status"] = outbound_email_secret_status(value)
    return result


SYSTEM_PARAMETER_AUDIT_FIELDS = [
    "enabled",
    "status",
    "secret_status",
    "value.sender_display_name",
    "value.sender_email",
    "value.reply_to_email",
    "value.hr_notification_email",
    "value.department_manager_cc_emails",
    "value.smtp_host",
    "value.smtp_port",
    "value.smtp_username",
    "value.smtp_use_tls",
    "value.smtp_use_ssl",
    "value.smtp_timeout_seconds",
    "value.password_config_mode",
    "value.password_secret_ref",
    "value.last_test_status",
    "value.last_test_at",
    "value.last_test_error",
]


def nested_value(record: dict[str, Any], dotted_key: str) -> Any:
    value: Any = record
    for part in dotted_key.split("."):
        if not isinstance(value, dict):
            return ""
        value = value.get(part, "")
    return value


def sanitize_system_parameter(parameter: dict[str, Any]) -> dict[str, Any]:
    sanitized = copy.deepcopy(parameter)
    value = sanitized.get("value") if isinstance(sanitized.get("value"), dict) else {}
    if "password_secret" in value:
        value["password_secret"] = "[redacted]"
    if "smtp_password" in value:
        value["smtp_password"] = "[redacted]"
    sanitized["value"] = value
    return sanitized


def system_parameter_changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    before_safe = sanitize_system_parameter(before)
    after_safe = sanitize_system_parameter(after)
    return [field for field in SYSTEM_PARAMETER_AUDIT_FIELDS if str(nested_value(before_safe, field)) != str(nested_value(after_safe, field))]


def outbound_email_runtime_settings(parameter: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    parameter = normalize_system_parameter(parameter or find_system_parameter(SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID) or default_outbound_email_parameter())
    value = parameter.get("value") if isinstance(parameter.get("value"), dict) else {}
    password, password_status = resolve_outbound_email_password(value)
    sender_email = str(value.get("sender_email", ONBOARDING_EMAIL_SENDER) or ONBOARDING_EMAIL_SENDER).strip()
    sender_display_name = str(value.get("sender_display_name", "TAC HR Admin") or "TAC HR Admin").strip()
    return {
        "parameter_id": str(parameter.get("parameter_id", SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID)),
        "enabled": bool(parameter.get("enabled", True)) and str(parameter.get("status", "active")) == "active",
        "sender_display_name": sender_display_name,
        "sender_email": sender_email,
        "sender_header": formataddr((sender_display_name, sender_email)) if sender_display_name else sender_email,
        "reply_to_email": str(value.get("reply_to_email", ONBOARDING_EMAIL_REPLY_TO) or ONBOARDING_EMAIL_REPLY_TO).strip(),
        "hr_notification_email": str(value.get("hr_notification_email", ONBOARDING_HR_NOTIFICATION_EMAIL) or ONBOARDING_HR_NOTIFICATION_EMAIL).strip(),
        "department_manager_cc_emails": normalize_email_list(value.get("department_manager_cc_emails", []), 3),
        "smtp_host": str(value.get("smtp_host") or ONBOARDING_SMTP_HOST).strip(),
        "smtp_port": config_int(value.get("smtp_port", ONBOARDING_SMTP_PORT), ONBOARDING_SMTP_PORT),
        "smtp_username": str(value.get("smtp_username") or ONBOARDING_SMTP_USERNAME).strip(),
        "smtp_password": password,
        "smtp_use_tls": config_bool(value.get("smtp_use_tls", ONBOARDING_SMTP_USE_TLS), ONBOARDING_SMTP_USE_TLS),
        "smtp_use_ssl": config_bool(value.get("smtp_use_ssl", False), False),
        "smtp_timeout_seconds": config_int(value.get("smtp_timeout_seconds", 15), 15),
        "password_status": password_status,
        "secret_status": outbound_email_secret_status(value),
    }


def outbound_email_runtime_error(settings: dict[str, Any]) -> str:
    if not settings.get("enabled"):
        return "disabled"
    if settings.get("password_status") != "available":
        return str(settings.get("password_status") or "password_missing")
    required = ["sender_email", "smtp_host", "smtp_username", "smtp_password"]
    if not all(settings.get(key) for key in required):
        return "not_configured"
    return ""


def send_outbound_email_test(recipient: str, actor: str) -> tuple[bool, str]:
    settings = outbound_email_runtime_settings()
    runtime_error = outbound_email_runtime_error(settings)
    if runtime_error:
        return False, runtime_error
    message = EmailMessage()
    message["From"] = str(settings.get("sender_header") or settings.get("sender_email"))
    message["To"] = recipient
    cc_addresses = normalize_email_list(settings.get("department_manager_cc_emails", []), 3)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    message["Subject"] = "TAC Master Data email test"
    if settings.get("reply_to_email"):
        message["Reply-To"] = str(settings.get("reply_to_email"))
    message.set_content(f"""This is a test email from TACAI Master Data Management.

If you received this message, outbound email settings are working.

Generated at: {now_iso()}
Sent by: {actor}
""")
    smtp_host = str(settings.get("smtp_host"))
    smtp_port = config_int(settings.get("smtp_port"), 587)
    smtp_timeout = config_int(settings.get("smtp_timeout_seconds"), 15)
    try:
        if config_bool(settings.get("smtp_use_ssl"), False) or smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_host, smtp_port, context=ssl.create_default_context(), timeout=smtp_timeout) as smtp:
                smtp.login(str(settings.get("smtp_username")), str(settings.get("smtp_password")))
                smtp.send_message(message)
        else:
            with smtplib.SMTP(smtp_host, smtp_port, timeout=smtp_timeout) as smtp:
                if config_bool(settings.get("smtp_use_tls"), True):
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(str(settings.get("smtp_username")), str(settings.get("smtp_password")))
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return False, exc.__class__.__name__
    return True, "sent"


def masterdata_record_fields(record_type: str) -> list[str]:
    return list(MASTERDATA_VERSION_FIELDS.get(record_type, []))


def masterdata_changed_fields(record_type: str, before_value: dict[str, Any], after_value: dict[str, Any]) -> list[str]:
    changed: list[str] = []
    for field in masterdata_record_fields(record_type):
        if str(before_value.get(field, "")) != str(after_value.get(field, "")):
            changed.append(field)
    return changed


def next_masterdata_version_number(versions: list[dict[str, Any]], record_type: str, record_id: str) -> int:
    numbers = [
        int(version.get("version_number", 0) or 0)
        for version in versions
        if version.get("record_type") == record_type and str(version.get("record_id", "")) == str(record_id)
    ]
    return (max(numbers) if numbers else 0) + 1


def masterdata_versions_for_record(record_type: str, record_id: str) -> list[dict[str, Any]]:
    return sorted(
        [
            version
            for version in load_masterdata_versions()
            if version.get("record_type") == record_type and str(version.get("record_id", "")) == str(record_id)
        ],
        key=lambda item: int(item.get("version_number", 0) or 0),
    )


def append_masterdata_version(
    record_type: str,
    record_id: str,
    action: str,
    user: dict[str, Any],
    data_snapshot: dict[str, Any],
    change_reason: str = "",
    changed_fields: Optional[list[str]] = None,
    restored_from_version_id: str = "",
) -> dict[str, Any]:
    versions = load_masterdata_versions()
    timestamp = now_iso()
    version = {
        "version_id": next_id(versions, "version_id", "VER-", 6),
        "record_type": record_type,
        "record_id": record_id,
        "version_number": next_masterdata_version_number(versions, record_type, record_id),
        "action": action,
        "changed_by": actor_label(user),
        "changed_at": timestamp,
        "change_reason": change_reason,
        "changed_fields": changed_fields or [],
        "restored_from_version_id": restored_from_version_id,
        "data_snapshot": copy.deepcopy(data_snapshot),
    }
    versions.append(version)
    save_masterdata_versions(versions)
    return version


def ensure_masterdata_version_baseline(record_type: str, record_id: str, user: dict[str, Any], current_record: dict[str, Any]) -> None:
    if masterdata_versions_for_record(record_type, record_id):
        return
    append_masterdata_version(
        record_type,
        record_id,
        "baseline",
        user,
        current_record,
        "System baseline created before first governed change.",
        masterdata_record_fields(record_type),
    )


def validate_change_governance(form: dict[str, str], messages: dict[str, str], changed_fields: list[str]) -> tuple[str, dict[str, str]]:
    if not changed_fields:
        return "", {}
    errors: dict[str, str] = {}
    change_reason = normalize_text(form.get("change_reason"))
    if not change_reason:
        errors["change_reason"] = t(messages, "validation.change_reason_required")
    if form.get("masterdata_change_ack") != "1":
        errors["masterdata_change_ack"] = t(messages, "validation.change_ack_required")
    return change_reason, errors


def visible_entities() -> list[dict[str, Any]]:
    return [entity for entity in load_entities() if entity.get("status") != "deleted"]


def find_entity(entity_id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    for entity in load_entities():
        if str(entity.get("entity_id", "")) == str(entity_id):
            if not include_deleted and entity.get("status") == "deleted":
                return None
            return entity
    return None


def active_entities() -> list[dict[str, Any]]:
    return [entity for entity in load_entities() if entity.get("status") == "active"]


def localized_master_name(record: dict[str, Any], name_prefix: str, code_field: str, lang: str) -> str:
    localized = str(record.get(f"{name_prefix}_{lang}", "")).strip()
    english = str(record.get(f"{name_prefix}_en", "")).strip()
    code = str(record.get(code_field, "")).strip()
    return localized or english or code


def entity_label(entity: Optional[dict[str, Any]], lang: str = DEFAULT_LANG) -> str:
    if not entity:
        return ""
    code = str(entity.get("entity_code", ""))
    name = localized_master_name(entity, "entity_name", "entity_code", lang)
    return f"{code} - {name}" if code and name and name != code else code or name


def visible_departments() -> list[dict[str, Any]]:
    return [department for department in load_departments() if department.get("status") != "deleted"]


def find_department(department_id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    for department in load_departments():
        if str(department.get("department_id", "")) == str(department_id):
            if not include_deleted and department.get("status") == "deleted":
                return None
            return department
    return None


def department_label(department: Optional[dict[str, Any]], lang: str = DEFAULT_LANG) -> str:
    if not department:
        return ""
    code = str(department.get("department_code", ""))
    name = localized_master_name(department, "department_name", "department_code", lang)
    return f"{code} - {name}" if code and name and name != code else code or name


def visible_teams() -> list[dict[str, Any]]:
    return [team for team in load_teams() if team.get("status") != "deleted"]


def team_label(team: Optional[dict[str, Any]], lang: str = DEFAULT_LANG) -> str:
    if not team:
        return ""
    code = str(team.get("team_code", ""))
    name = localized_master_name(team, "team_name", "team_code", lang)
    return f"{code} - {name}" if code and name and name != code else code or name


def find_team(team_id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    for team in load_teams():
        if str(team.get("team_id", "")) == str(team_id):
            if not include_deleted and team.get("status") == "deleted":
                return None
            return team
    return None


def actor_label(user: dict[str, Any]) -> str:
    for key in ("username", "email", "display_name", "user_id"):
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return "unknown"


def append_audit(record_type: str, record_id: str, action: str, user: dict[str, Any], before_value: Any, after_value: Any, change_reason: str = "", changed_fields: Optional[list[str]] = None, version_id: str = "") -> None:
    logs = load_audit_logs()
    logs.append(
        {
            "audit_id": next_id(logs, "audit_id", "AUD-", 6),
            "module": MODULE_NAME,
            "record_type": record_type,
            "record_id": record_id,
            "action": action,
            "user": actor_label(user),
            "timestamp": now_iso(),
            "before_value": before_value,
            "after_value": after_value,
            "change_reason": change_reason,
            "changed_fields": changed_fields or [],
            "version_id": version_id,
        }
    )
    save_audit_logs(logs)


def validate_user_admin_session(session_id: str) -> Optional[dict[str, Any]]:
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


def is_system_admin(user: dict[str, Any]) -> bool:
    roles = set(str(role) for role in user.get("roles", []))
    role = str(user.get("role", ""))
    permissions = set(str(permission) for permission in user.get("permissions", []))
    return role == "system_admin" or "system_admin" in roles or "*" in permissions


def has_permission(user: dict[str, Any], permission_key: str) -> bool:
    permissions = set(str(permission) for permission in user.get("permissions", []))
    return is_system_admin(user) or permission_key in permissions


def can_access(user: dict[str, Any]) -> bool:
    return has_permission(user, "masterdata.access")


def can_view(user: dict[str, Any]) -> bool:
    return can_access(user) and (has_permission(user, "masterdata.view") or has_permission(user, "masterdata.maintain"))


def can_maintain(user: dict[str, Any]) -> bool:
    return can_access(user) and has_permission(user, "masterdata.maintain")


def can_admin_masterdata(user: dict[str, Any]) -> bool:
    return can_access(user) and has_permission(user, "masterdata.admin")


def can_customer_master_view(user: dict[str, Any]) -> bool:
    return has_permission(user, "client_revenue.view") or has_permission(user, "client_revenue.manage")


def can_customer_master_maintain(user: dict[str, Any]) -> bool:
    return has_permission(user, "client_revenue.customer_master.maintain") or has_permission(user, "client_revenue.manage")


def current_entity(user: dict[str, Any]) -> dict[str, Any]:
    entity = user.get("entity") if isinstance(user.get("entity"), dict) else {}
    if entity:
        return entity
    entity_id = str(user.get("entity_id", "")).strip()
    entity_code = str(user.get("entity_code", "")).strip()
    if not entity_id or not entity_code:
        return {}
    return {"entity_id": entity_id, "entity_code": entity_code, "entity_name_en": str(user.get("entity_name", ""))}


def current_entity_id(user: dict[str, Any]) -> str:
    return str(current_entity(user).get("entity_id", "")).strip()


def current_entity_label(user: dict[str, Any], lang: str = DEFAULT_LANG) -> str:
    entity = current_entity(user)
    entity_code = str(entity.get("entity_code", "") or "").strip()
    name_keys = [f"entity_name_{lang}", "entity_name_en", "entity_name", "name"]
    entity_name = ""
    for key in name_keys:
        entity_name = str(entity.get(key, "") or "").strip()
        if entity_name:
            break
    if entity_code and entity_name:
        return f"{entity_code} - {entity_name}"
    return entity_code or entity_name


def current_user_label(user: dict[str, Any]) -> str:
    for key in ["display_name", "name", "username", "email", "user_name", "user_id", "id"]:
        value = str(user.get(key, "") or "").strip()
        if value:
            return value
    return "-"


def has_entity_context(user: Optional[dict[str, Any]]) -> bool:
    return bool(user and current_entity_id(user) and str(current_entity(user).get("entity_code", "")).strip())


def entity_accessible_to_user(entity: dict[str, Any], user: dict[str, Any]) -> bool:
    return can_admin_masterdata(user) or str(entity.get("entity_id", "")) == current_entity_id(user)


def visible_entities_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [entity for entity in visible_entities() if entity_accessible_to_user(entity, user)]


def active_entities_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [entity for entity in visible_entities_for_user(user) if entity.get("status") == "active"]


def department_accessible_to_user(department: dict[str, Any], user: dict[str, Any]) -> bool:
    return can_admin_masterdata(user) or str(department.get("entity_id", "")) == current_entity_id(user)


def visible_departments_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [department for department in visible_departments() if department_accessible_to_user(department, user)]


def team_accessible_to_user(team: dict[str, Any], user: dict[str, Any]) -> bool:
    parent_department = find_department(str(team.get("department_id", "")), include_deleted=True)
    return bool(parent_department and department_accessible_to_user(parent_department, user))


def visible_teams_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [team for team in visible_teams() if team_accessible_to_user(team, user)]


def active_departments_for_entity_for_user(user: dict[str, Any], entity_id: str) -> list[dict[str, Any]]:
    target_entity_id = str(entity_id)
    return [
        department
        for department in visible_departments_for_user(user)
        if department.get("status") == "active" and str(department.get("entity_id", "")) == target_entity_id
    ]


def department_belongs_to_entity(department_id: str, entity_id: str) -> bool:
    department = find_department(department_id)
    return bool(department and str(department.get("entity_id", "")) == str(entity_id))


def team_parent_entity_id(team: dict[str, Any]) -> str:
    department = find_department(str(team.get("department_id", "")), include_deleted=True)
    return str(department.get("entity_id", "")).strip() if department else ""


def team_persisted_values(values: dict[str, str]) -> dict[str, str]:
    return {key: values.get(key, "") for key in ("team_code", "team_name_en", "team_name_ja", "team_name_zh", "department_id", "status")}


def normalize_text(value: Any) -> str:
    return str(value or "").strip()


def normalized_code(value: Any) -> str:
    return normalize_text(value).casefold()


def is_reserved_one_time_code(code: Any) -> bool:
    return normalized_code(code).endswith(ONE_TIME_CODE_SUFFIX.casefold())


def entity_code_exists(entity_code: str, entities: list[dict[str, Any]], current_entity_id: str = "") -> bool:
    target = normalized_code(entity_code)
    for entity in entities:
        if entity.get("status") == "deleted":
            continue
        if current_entity_id and str(entity.get("entity_id", "")) == current_entity_id:
            continue
        if normalized_code(entity.get("entity_code", "")) == target:
            return True
    return False


def validate_entity_input(form: dict[str, str], entities: list[dict[str, Any]], messages: dict[str, str], current_entity_id: str = "") -> tuple[dict[str, str], dict[str, str]]:
    values = {
        "entity_code": normalize_text(form.get("entity_code")),
        "entity_type": "legal_entity",
        "legal_name": normalize_text(form.get("legal_name")),
        "entity_name_en": normalize_text(form.get("entity_name_en")),
        "entity_name_ja": normalize_text(form.get("entity_name_ja")),
        "entity_name_zh": normalize_text(form.get("entity_name_zh")),
        "registration_number": normalize_text(form.get("registration_number")),
        "tax_registration_number": normalize_text(form.get("tax_registration_number")),
        "country": normalize_text(form.get("country")),
        "currency": normalize_text(form.get("currency")),
        "status": normalize_text(form.get("status") or "active"),
    }
    if not values["legal_name"]:
        values["legal_name"] = values["entity_name_en"]
    errors: dict[str, str] = {}
    for field in ("entity_code", "legal_name", "entity_name_en", "country", "currency", "status"):
        if not values[field]:
            errors[field] = t(messages, "validation.required")
    if values["status"] and values["status"] not in STATUS_VALUES:
        errors["status"] = t(messages, "validation.invalid_status")
    if values["entity_code"] and entity_code_exists(values["entity_code"], entities, current_entity_id):
        errors["entity_code"] = t(messages, "validation.entity_code_duplicate")
    return values, errors


def department_code_exists(department_code: str, entity_id: str, departments: list[dict[str, Any]], current_department_id: str = "") -> bool:
    target = normalized_code(department_code)
    target_entity_id = str(entity_id)
    for department in departments:
        if department.get("status") == "deleted":
            continue
        if current_department_id and str(department.get("department_id", "")) == current_department_id:
            continue
        if str(department.get("entity_id", "")) != target_entity_id:
            continue
        if normalized_code(department.get("department_code", "")) == target:
            return True
    return False


def validate_department_input(form: dict[str, str], departments: list[dict[str, Any]], messages: dict[str, str], current_department_id: str = "") -> tuple[dict[str, str], dict[str, str]]:
    values = {
        "department_code": normalize_text(form.get("department_code")),
        "department_name_en": normalize_text(form.get("department_name_en")),
        "department_name_ja": normalize_text(form.get("department_name_ja")),
        "department_name_zh": normalize_text(form.get("department_name_zh")),
        "entity_id": normalize_text(form.get("entity_id")),
        "status": normalize_text(form.get("status") or "active"),
    }
    errors: dict[str, str] = {}
    for field in ("department_code", "department_name_en", "entity_id", "status"):
        if not values[field]:
            errors[field] = t(messages, "validation.required")
    if values["status"] and values["status"] not in STATUS_VALUES:
        errors["status"] = t(messages, "validation.invalid_status")
    if values["department_code"] and values["entity_id"] and department_code_exists(values["department_code"], values["entity_id"], departments, current_department_id):
        errors["department_code"] = t(messages, "validation.department_code_duplicate")
    parent_entity = find_entity(values["entity_id"]) if values["entity_id"] else None
    if values["entity_id"] and (not parent_entity or parent_entity.get("status") != "active"):
        errors["entity_id"] = t(messages, "validation.parent_entity_required")
    return values, errors


def team_code_exists(team_code: str, department_id: str, teams: list[dict[str, Any]], current_team_id: str = "") -> bool:
    target = normalized_code(team_code)
    target_department_id = str(department_id)
    for team in teams:
        if team.get("status") == "deleted":
            continue
        if current_team_id and str(team.get("team_id", "")) == current_team_id:
            continue
        if str(team.get("department_id", "")) != target_department_id:
            continue
        if normalized_code(team.get("team_code", "")) == target:
            return True
    return False


def validate_team_input(form: dict[str, str], teams: list[dict[str, Any]], messages: dict[str, str], current_team_id: str = "") -> tuple[dict[str, str], dict[str, str]]:
    values = {
        "entity_id": normalize_text(form.get("entity_id")),
        "team_code": normalize_text(form.get("team_code")),
        "team_name_en": normalize_text(form.get("team_name_en")),
        "team_name_ja": normalize_text(form.get("team_name_ja")),
        "team_name_zh": normalize_text(form.get("team_name_zh")),
        "department_id": normalize_text(form.get("department_id")),
        "status": normalize_text(form.get("status") or "active"),
    }
    errors: dict[str, str] = {}
    for field in ("entity_id", "team_code", "team_name_en", "department_id", "status"):
        if not values[field]:
            errors[field] = t(messages, "validation.required")
    if values["status"] and values["status"] not in STATUS_VALUES:
        errors["status"] = t(messages, "validation.invalid_status")
    parent_entity = find_entity(values["entity_id"]) if values["entity_id"] else None
    if values["entity_id"] and (not parent_entity or parent_entity.get("status") != "active"):
        errors["entity_id"] = t(messages, "validation.parent_entity_required")
    if values["team_code"] and values["department_id"] and team_code_exists(values["team_code"], values["department_id"], teams, current_team_id):
        errors["team_code"] = t(messages, "validation.team_code_duplicate")
    parent_department = find_department(values["department_id"]) if values["department_id"] else None
    if values["department_id"] and (not parent_department or parent_department.get("status") != "active"):
        errors["department_id"] = t(messages, "validation.parent_department_required")
    if parent_department and values["entity_id"] and str(parent_department.get("entity_id", "")) != values["entity_id"]:
        errors["department_id"] = t(messages, "validation.department_entity_mismatch")
    return values, errors



def visible_customers() -> list[dict[str, Any]]:
    return [customer for customer in load_customers() if customer.get("status") != "deleted"]


def active_customers() -> list[dict[str, Any]]:
    return [customer for customer in visible_customers() if customer.get("status") == "active"]


def find_customer(customer_id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    for customer in load_customers():
        if str(customer.get("customer_id", "")) == str(customer_id):
            if not include_deleted and customer.get("status") == "deleted":
                return None
            return customer
    return None


def customer_label(customer: Optional[dict[str, Any]], lang: str = DEFAULT_LANG) -> str:
    if not customer:
        return ""
    code = str(customer.get("customer_code", ""))
    localized = str(customer.get(f"customer_name_{lang}", "")).strip()
    default_name = str(customer.get("customer_name", "")).strip()
    english = str(customer.get("customer_name_en", "")).strip()
    name = localized or default_name or english or code
    return f"{code} - {name}" if code and name and name != code else code or name


def customer_code_exists(customer_code: str, customers: list[dict[str, Any]], current_customer_id: str = "") -> bool:
    target = normalized_code(customer_code)
    for customer in customers:
        if customer.get("status") == "deleted":
            continue
        if current_customer_id and str(customer.get("customer_id", "")) == current_customer_id:
            continue
        if normalized_code(customer.get("customer_code", "")) == target:
            return True
    return False


def customer_persisted_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "customer_code": str(values.get("customer_code", "")),
        "customer_record_mode": str(values.get("customer_record_mode", "standard_customer") or "standard_customer"),
        "customer_name": str(values.get("customer_name", "")),
        "customer_name_en": str(values.get("customer_name_en", "")),
        "customer_name_zh": str(values.get("customer_name_zh", "")),
        "customer_registration_number": str(values.get("customer_registration_number", "")),
        "billing_address": str(values.get("billing_address", "")),
        "billing_contact_name": str(values.get("billing_contact_name", "")),
        "billing_contact_email": str(values.get("billing_contact_email", "")),
        "default_language": str(values.get("default_language", "ja")),
        "default_payment_terms_days": int(values.get("default_payment_terms_days", 30) or 30),
        "default_tax_rate": str(values.get("default_tax_rate", "10%")),
        "business_types": values.get("business_types", []) if isinstance(values.get("business_types"), list) else [],
        "notes": str(values.get("notes", "")),
        "status": str(values.get("status", "active")),
    }


def validate_customer_input(form: dict[str, str], customers: list[dict[str, Any]], messages: dict[str, str], current_customer_id: str = "") -> tuple[dict[str, Any], dict[str, str]]:
    days_raw = normalize_text(form.get("default_payment_terms_days") or "30")
    try:
        payment_terms_days = int(days_raw)
    except ValueError:
        payment_terms_days = 0
    business_types = [item.strip() for item in normalize_text(form.get("business_types")).split(",") if item.strip()]
    values: dict[str, Any] = {
        "customer_code": normalize_text(form.get("customer_code")),
        "customer_record_mode": normalize_text(form.get("customer_record_mode") or "standard_customer"),
        "customer_name": normalize_text(form.get("customer_name")),
        "customer_name_en": normalize_text(form.get("customer_name_en")),
        "customer_name_zh": normalize_text(form.get("customer_name_zh")),
        "customer_registration_number": normalize_text(form.get("customer_registration_number")),
        "billing_address": normalize_text(form.get("billing_address")),
        "billing_contact_name": normalize_text(form.get("billing_contact_name")),
        "billing_contact_email": normalize_text(form.get("billing_contact_email")),
        "default_language": normalize_text(form.get("default_language") or "ja"),
        "default_payment_terms_days": payment_terms_days,
        "default_tax_rate": normalize_text(form.get("default_tax_rate") or "10%"),
        "business_types": business_types,
        "notes": normalize_text(form.get("notes")),
        "status": normalize_text(form.get("status") or "active"),
    }
    errors: dict[str, str] = {}
    for field in ("customer_code", "customer_record_mode", "customer_name", "default_language", "default_payment_terms_days", "default_tax_rate", "status"):
        if not values[field]:
            errors[field] = t(messages, "validation.required")
    if values["customer_record_mode"] and values["customer_record_mode"] not in CUSTOMER_RECORD_MODES:
        errors["customer_record_mode"] = t(messages, "validation.invalid_status")
    is_one_time = values["customer_record_mode"] == "one_time_customer"
    reserved_code = is_reserved_one_time_code(values["customer_code"]) if values["customer_code"] else False
    if values["customer_code"] and is_one_time and not reserved_code:
        errors["customer_code"] = t(messages, "validation.one_time_code_required", "One-time records must use a code ending in 9999.")
    if values["customer_code"] and not is_one_time and reserved_code:
        errors["customer_code"] = t(messages, "validation.one_time_code_reserved", "Codes ending in 9999 are reserved for one-time records.")
    if values["status"] and values["status"] not in STATUS_VALUES:
        errors["status"] = t(messages, "validation.invalid_status")
    if values["default_language"] and values["default_language"] not in SUPPORTED_LANGS:
        errors["default_language"] = t(messages, "validation.invalid_language", "Invalid language.")
    if values["default_tax_rate"] and values["default_tax_rate"] not in {"10%", "8%", "0%", "mixed", "unknown"}:
        errors["default_tax_rate"] = t(messages, "validation.invalid_tax_rate", "Invalid tax rate.")
    if payment_terms_days <= 0:
        errors["default_payment_terms_days"] = t(messages, "validation.invalid_payment_terms", "Payment terms must be a positive number of days.")
    if values["customer_code"] and customer_code_exists(str(values["customer_code"]), customers, current_customer_id):
        errors["customer_code"] = t(messages, "validation.customer_code_duplicate", "Customer Code already exists.")
    return values, errors


def customer_api_record(customer: dict[str, Any]) -> dict[str, Any]:
    status = str(customer.get("status", "active"))
    customer_record_mode = str(customer.get("customer_record_mode", "standard_customer") or "standard_customer")
    is_one_time = customer_record_mode == "one_time_customer"
    return {
        **customer,
        "customer_record_mode": customer_record_mode,
        "is_one_time_customer": is_one_time,
        "requires_manual_description": is_one_time,
        "manual_description_context": "customer" if is_one_time else "",
        "record_status": "Active" if status == "active" else "Inactive",
    }



def safe_filename(filename: str) -> str:
    base = Path(filename).name.strip() or "vendor-ocr-upload"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:120] or "vendor-ocr-upload"


def parse_multipart_form(handler: Any) -> tuple[dict[str, str], dict[str, cgi.FieldStorage]]:
    content_type = handler.headers.get("Content-Type", "")
    if not content_type.startswith("multipart/form-data"):
        return handler.parse_form_body(), {}
    form = cgi.FieldStorage(
        fp=handler.rfile,
        headers=handler.headers,
        environ={"REQUEST_METHOD": "POST", "CONTENT_TYPE": content_type, "CONTENT_LENGTH": handler.headers.get("Content-Length", "0")},
    )
    fields: dict[str, str] = {}
    files: dict[str, cgi.FieldStorage] = {}
    for key in form.keys():
        item = form[key]
        if isinstance(item, list):
            item = item[0]
        if getattr(item, "filename", None):
            files[key] = item
        else:
            raw_value = item.value
            fields[key] = raw_value if isinstance(raw_value, str) else raw_value.decode("utf-8", errors="replace")
    return fields, files


def save_vendor_ocr_upload(item: cgi.FieldStorage) -> dict[str, Any]:
    original = getattr(item, "filename", "") or ""
    if not original:
        raise ValueError("Please choose a supplier invoice/request file before OCR extraction.")
    safe_original = safe_filename(original)
    extension = Path(safe_original).suffix.lower()
    if extension not in VENDOR_OCR_ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported OCR upload type.")
    content = item.file.read()
    if len(content) > VENDOR_OCR_MAX_UPLOAD_BYTES:
        raise ValueError("OCR upload exceeds 10MB limit.")
    stored = safe_filename(f"vendor-ocr-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{safe_original}")
    target = VENDOR_OCR_UPLOAD_DIR / stored
    target.write_bytes(content)
    return {"original_filename": original, "stored_filename": stored, "path": str(target), "content_type": item.type or mimetypes.guess_type(safe_original)[0] or "application/octet-stream", "size_bytes": len(content)}


def run_vendor_master_ocr(path: Path) -> tuple[str, list[str]]:
    notes = ["Local vendor master OCR uses macOS Vision fallback for invoice/request files."]
    swift = shutil.which("swift")
    if not swift:
        raise ValueError("Vendor Master OCR requires Swift/macOS Vision on this machine.")
    if not MACOS_VISION_OCR_SCRIPT.exists():
        raise ValueError("Vendor Master OCR helper script is missing.")
    try:
        result = subprocess.run([swift, str(MACOS_VISION_OCR_SCRIPT), str(path)], check=False, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Vendor Master OCR timed out.") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Vendor Master OCR failed.").strip()
        raise ValueError(f"Vendor Master OCR failed: {message[:300]}")
    text = (result.stdout or "").strip()
    if not text:
        raise ValueError("Vendor Master OCR completed but no text was detected.")
    notes.append("macOS Vision OCR completed locally.")
    return text, notes


def normalize_ocr_text(text: str) -> str:
    normalized = unicodedata.normalize("NFKC", text or "")
    normalized = normalized.replace("￥", "¥")
    normalized = re.sub(r"[ \t]+", " ", normalized)
    return normalized.strip()


def extract_qualified_invoice_number_from_text(text: str) -> str:
    for match in re.finditer(r"[TＴ][ \t\-]*\d(?:[\d \t\-]{11,20})", text, flags=re.IGNORECASE):
        normalized = re.sub(r"[^TtＴ0-9]", "", match.group(0)).upper().replace("Ｔ", "T")
        if re.fullmatch(r"T\d{13}", normalized):
            return normalized
    return ""


def extract_master_vendor_name(lines: list[str]) -> str:
    label_pattern = re.compile(r"(?:請求元|発行者|販売者|事業者名|会社名|Vendor|Supplier|From)\s*[:：]?\s*(.+)", re.IGNORECASE)
    for line in lines[:20]:
        match = label_pattern.search(line)
        if match:
            return re.sub(r"\s+", " ", match.group(1)).strip(" -*:：")[:100]
    skip_keywords = ["請求書", "見積書", "納品書", "登録番号", "TEL", "電話", "住所", "合計", "消費税", "請求日", "発行日", "支払", "振込", "銀行"]
    company_keywords = ["株式会社", "有限会社", "合同会社", "Inc.", "Co.", "Ltd", "LLC", "Company"]
    clean_lines = [line for line in lines[:14] if len(line) >= 2 and not any(keyword in line for keyword in skip_keywords)]
    for line in clean_lines:
        if any(keyword in line for keyword in company_keywords):
            return re.sub(r"\s+", " ", line).strip(" -*:：")[:100]
    return clean_lines[0][:100] if clean_lines else ""


def extract_labeled_value(lines: list[str], labels: list[str]) -> str:
    for index, line in enumerate(lines):
        for label in labels:
            match = re.search(rf"{re.escape(label)}\s*[:：]?\s*(.+)", line, flags=re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                if value:
                    return value[:160]
            if label.lower() in line.lower() and index + 1 < len(lines):
                return lines[index + 1].strip()[:160]
    return ""


def extract_address_text(lines: list[str]) -> str:
    selected = [line for line in lines if any(token in line for token in ["〒", "東京都", "大阪府", "県", "市", "区", "町", "Address"])]
    return "\n".join(selected[:4])[:400]


def mask_account_number(text: str) -> str:
    matches = re.findall(r"(?:口座番号|Account(?:\s*No\.?)?)\D{0,8}(\d{4,12})", text, flags=re.IGNORECASE)
    number = matches[0] if matches else ""
    if not number:
        return ""
    return "****" + number[-4:]


def parse_vendor_master_ocr_text(text: str, notes: list[str]) -> dict[str, Any]:
    normalized = normalize_ocr_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = "\n".join(lines)
    qualified = extract_qualified_invoice_number_from_text(joined)
    bank_text = "\n".join(line for line in lines if any(keyword.lower() in line.lower() for keyword in ["振込先", "銀行", "支店", "普通", "当座", "口座番号", "口座名義", "Bank", "Account", "Branch"]))[:700]
    vendor_name = extract_master_vendor_name(lines)
    account_holder = extract_labeled_value(lines, ["口座名義", "Account Holder"])
    draft = {
        "vendor_name_en": vendor_name,
        "vendor_name_ja": vendor_name,
        "vendor_name_zh": "",
        "vendor_name_kana": "",
        "country": "Japan",
        "postal_code": extract_labeled_value(lines, ["〒", "Postal Code"]),
        "address": extract_address_text(lines),
        "qualified_invoice_number": qualified,
        "is_qualified_invoice_vendor": "yes" if qualified else "unknown",
        "contact_person": "",
        "email": extract_labeled_value(lines, ["Email", "E-mail", "メール"]),
        "phone": extract_labeled_value(lines, ["TEL", "電話", "Phone"]),
        "bank_name": extract_labeled_value(lines, ["銀行", "Bank"]),
        "bank_branch": extract_labeled_value(lines, ["支店", "Branch"]),
        "bank_account_type": "ordinary" if "普通" in joined else "current" if "当座" in joined else "",
        "bank_account_number_masked": mask_account_number(joined),
        "bank_account_holder": account_holder,
        "payment_terms": extract_labeled_value(lines, ["支払期限", "支払期日", "Payment Due", "Due Date"]),
        "default_currency": "JPY",
        "notes": "OCR draft from supplier invoice/request. Review all values before saving.\n" + bank_text,
        "vendor_ocr_status": "draft",
        "vendor_ocr_confidence_notes": notes + ["Vendor Master OCR suggestions are draft-only and must be reviewed before save."],
        "vendor_ocr_raw_text_preview": normalized[:1600],
    }
    return draft


def save_customer_ocr_upload(item: cgi.FieldStorage) -> dict[str, Any]:
    original = getattr(item, "filename", "") or ""
    if not original:
        raise ValueError("Please choose an issued invoice file before OCR extraction.")
    safe_original = safe_filename(original)
    extension = Path(safe_original).suffix.lower()
    if extension not in CUSTOMER_OCR_ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported OCR upload type.")
    content = item.file.read()
    if len(content) > CUSTOMER_OCR_MAX_UPLOAD_BYTES:
        raise ValueError("OCR upload exceeds 10MB limit.")
    stored = safe_filename(f"customer-ocr-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}-{safe_original}")
    target = CUSTOMER_OCR_UPLOAD_DIR / stored
    target.write_bytes(content)
    return {"original_filename": original, "stored_filename": stored, "path": str(target), "content_type": item.type or mimetypes.guess_type(safe_original)[0] or "application/octet-stream", "size_bytes": len(content)}


def run_customer_master_ocr(path: Path) -> tuple[str, list[str]]:
    notes = ["Local customer master OCR uses macOS Vision fallback for issued invoice files."]
    swift = shutil.which("swift")
    if not swift:
        raise ValueError("Customer Master OCR requires Swift/macOS Vision on this machine.")
    if not MACOS_VISION_OCR_SCRIPT.exists():
        raise ValueError("Customer Master OCR helper script is missing.")
    try:
        result = subprocess.run([swift, str(MACOS_VISION_OCR_SCRIPT), str(path)], check=False, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired as exc:
        raise ValueError("Customer Master OCR timed out.") from exc
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "Customer Master OCR failed.").strip()
        raise ValueError(f"Customer Master OCR failed: {message[:300]}")
    text = (result.stdout or "").strip()
    if not text:
        raise ValueError("Customer Master OCR completed but no text was detected.")
    notes.append("macOS Vision OCR completed locally.")
    return text, notes


def extract_master_customer_name(lines: list[str]) -> str:
    positive_pattern = re.compile(r"(?:請求先|宛先|顧客名|取引先|お客様|Bill\s*To|Billing\s*To|Customer|Client|Sold\s*To|To)\s*[:：]?\s*(.+)", re.IGNORECASE)
    issuer_markers = ["請求元", "発行者", "販売者", "差出人", "From", "Issuer", "Seller", "弊社"]
    for index, line in enumerate(lines[:40]):
        if any(marker.lower() in line.lower() for marker in issuer_markers):
            continue
        match = positive_pattern.search(line)
        if match:
            value = re.sub(r"\s+", " ", match.group(1)).strip(" -*:：御中様")
            if value:
                return value[:100]
        if ("御中" in line or "様" in line) and not any(marker.lower() in line.lower() for marker in issuer_markers):
            value = re.sub(r"(御中|様)", "", line).strip(" -*:：")
            if 2 <= len(value) <= 100:
                return value
        if re.search(r"(?:請求先|宛先|Bill\s*To|Customer|Client)", line, flags=re.IGNORECASE) and index + 1 < len(lines):
            candidate = lines[index + 1].strip(" -*:：御中様")
            if candidate:
                return candidate[:100]
    return ""


def infer_default_language_from_ocr(text: str) -> str:
    if re.search(r"[ぁ-んァ-ン一-龯]", text or ""):
        return "ja"
    return "en"


def extract_payment_terms_days(text: str) -> int:
    match = re.search(r"(?:支払条件|Payment\s*Terms|Terms)\D{0,20}(\d{1,3})\s*(?:日|days?)", text, flags=re.IGNORECASE)
    if match:
        try:
            days = int(match.group(1))
            if 0 < days <= 365:
                return days
        except ValueError:
            pass
    return 30


def extract_registration_number_from_text(lines: list[str], joined: str) -> str:
    qualified = extract_qualified_invoice_number_from_text(joined)
    if qualified:
        return qualified
    return extract_labeled_value(lines, ["法人番号", "登録番号", "Registration No.", "Registration Number", "Tax ID"])


def parse_customer_master_ocr_text(text: str, notes: list[str]) -> dict[str, Any]:
    normalized = normalize_ocr_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = "\n".join(lines)
    customer_name = extract_master_customer_name(lines)
    contact_name = extract_labeled_value(lines, ["担当者", "Contact", "Attn", "Attention"])
    email = extract_labeled_value(lines, ["Email", "E-mail", "メール"])
    relevant_text = "\n".join(line for line in lines if any(keyword.lower() in line.lower() for keyword in ["請求先", "宛先", "顧客", "取引先", "bill to", "customer", "client", "payment", "支払", "住所", "address", "email"]))[:900]
    draft = {
        "customer_name": customer_name,
        "customer_name_en": customer_name if re.search(r"[A-Za-z]", customer_name) else "",
        "customer_name_zh": "",
        "customer_registration_number": extract_registration_number_from_text(lines, joined),
        "billing_address": extract_address_text(lines),
        "billing_contact_name": contact_name,
        "billing_contact_email": email,
        "default_language": infer_default_language_from_ocr(joined),
        "default_payment_terms_days": extract_payment_terms_days(joined),
        "default_tax_rate": "10%" if any(keyword in joined for keyword in ["消費税", "税率10", "10%"] ) else "unknown",
        "notes": "OCR draft from issued invoice. Review all values before saving.\n" + relevant_text,
        "customer_ocr_status": "draft",
        "customer_ocr_confidence_notes": notes + ["Customer Master OCR suggestions are draft-only and must be reviewed before save."],
        "customer_ocr_raw_text_preview": normalized[:1600],
    }
    return draft


def visible_vendors() -> list[dict[str, Any]]:
    return [vendor for vendor in load_vendors() if vendor.get("status") != "deleted"]


def active_vendors() -> list[dict[str, Any]]:
    return [vendor for vendor in visible_vendors() if vendor.get("status") == "active"]


def find_vendor(vendor_id: str, include_deleted: bool = False) -> Optional[dict[str, Any]]:
    for vendor in load_vendors():
        if str(vendor.get("vendor_id", "")) == str(vendor_id):
            if not include_deleted and vendor.get("status") == "deleted":
                return None
            return vendor
    return None


def vendor_label(vendor: Optional[dict[str, Any]], lang: str = DEFAULT_LANG) -> str:
    if not vendor:
        return ""
    code = str(vendor.get("vendor_code", ""))
    name = localized_master_name(vendor, "vendor_name", "vendor_code", lang)
    return f"{code} - {name}" if code and name and name != code else code or name


def vendor_accessible_to_user(vendor: dict[str, Any], user: dict[str, Any]) -> bool:
    return can_admin_masterdata(user) or not vendor.get("entity_id") or str(vendor.get("entity_id", "")) == current_entity_id(user)


def visible_vendors_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [vendor for vendor in visible_vendors() if vendor_accessible_to_user(vendor, user)]


def active_vendors_for_user(user: dict[str, Any]) -> list[dict[str, Any]]:
    return [vendor for vendor in visible_vendors_for_user(user) if vendor.get("status") == "active"]


def vendor_code_exists(vendor_code: str, entity_id: str, vendors: list[dict[str, Any]], current_vendor_id: str = "") -> bool:
    target = normalized_code(vendor_code)
    target_entity_id = str(entity_id)
    for vendor in vendors:
        if vendor.get("status") == "deleted":
            continue
        if current_vendor_id and str(vendor.get("vendor_id", "")) == current_vendor_id:
            continue
        if str(vendor.get("entity_id", "")) != target_entity_id:
            continue
        if normalized_code(vendor.get("vendor_code", "")) == target:
            return True
    return False


def vendor_persisted_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        "vendor_code": str(values.get("vendor_code", "")),
        "vendor_name_en": str(values.get("vendor_name_en", "")),
        "vendor_name_ja": str(values.get("vendor_name_ja", "")),
        "vendor_name_zh": str(values.get("vendor_name_zh", "")),
        "vendor_name_kana": str(values.get("vendor_name_kana", "")),
        "vendor_type": str(values.get("vendor_type", "other")),
        "supplier_record_mode": str(values.get("supplier_record_mode", "standard_vendor") or "standard_vendor"),
        "entity_id": str(values.get("entity_id", "")),
        "country": str(values.get("country", "Japan")),
        "postal_code": str(values.get("postal_code", "")),
        "address": str(values.get("address", "")),
        "qualified_invoice_number": str(values.get("qualified_invoice_number", "")),
        "is_qualified_invoice_vendor": str(values.get("is_qualified_invoice_vendor", "unknown")),
        "contact_person": str(values.get("contact_person", "")),
        "email": str(values.get("email", "")),
        "phone": str(values.get("phone", "")),
        "bank_name": str(values.get("bank_name", "")),
        "bank_branch": str(values.get("bank_branch", "")),
        "bank_account_type": str(values.get("bank_account_type", "")),
        "bank_account_number_masked": str(values.get("bank_account_number_masked", "")),
        "bank_account_holder": str(values.get("bank_account_holder", "")),
        "payment_terms": str(values.get("payment_terms", "")),
        "default_currency": str(values.get("default_currency", "JPY")),
        "notes": str(values.get("notes", "")),
        "status": str(values.get("status", "active")),
    }


def validate_vendor_input(form: dict[str, str], vendors: list[dict[str, Any]], messages: dict[str, str], current_vendor_id: str = "") -> tuple[dict[str, Any], dict[str, str]]:
    values: dict[str, Any] = {
        "vendor_code": normalize_text(form.get("vendor_code")),
        "vendor_name_en": normalize_text(form.get("vendor_name_en")),
        "vendor_name_ja": normalize_text(form.get("vendor_name_ja")),
        "vendor_name_zh": normalize_text(form.get("vendor_name_zh")),
        "vendor_name_kana": normalize_text(form.get("vendor_name_kana")),
        "vendor_type": normalize_text(form.get("vendor_type") or "other"),
        "supplier_record_mode": normalize_text(form.get("supplier_record_mode") or "standard_vendor"),
        "entity_id": normalize_text(form.get("entity_id")),
        "country": normalize_text(form.get("country") or "Japan"),
        "postal_code": normalize_text(form.get("postal_code")),
        "address": normalize_text(form.get("address")),
        "qualified_invoice_number": normalize_text(form.get("qualified_invoice_number")),
        "is_qualified_invoice_vendor": normalize_text(form.get("is_qualified_invoice_vendor") or "unknown"),
        "contact_person": normalize_text(form.get("contact_person")),
        "email": normalize_text(form.get("email")),
        "phone": normalize_text(form.get("phone")),
        "bank_name": normalize_text(form.get("bank_name")),
        "bank_branch": normalize_text(form.get("bank_branch")),
        "bank_account_type": normalize_text(form.get("bank_account_type")),
        "bank_account_number_masked": normalize_text(form.get("bank_account_number_masked")),
        "bank_account_holder": normalize_text(form.get("bank_account_holder")),
        "payment_terms": normalize_text(form.get("payment_terms")),
        "default_currency": normalize_text(form.get("default_currency") or "JPY"),
        "notes": normalize_text(form.get("notes")),
        "status": normalize_text(form.get("status") or "active"),
    }
    errors: dict[str, str] = {}
    for field in ("vendor_code", "vendor_name_en", "vendor_type", "supplier_record_mode", "entity_id", "country", "default_currency", "status"):
        if not values[field]:
            errors[field] = t(messages, "validation.required")
    is_one_time = values["supplier_record_mode"] == "one_time_vendor"
    reserved_code = is_reserved_one_time_code(values["vendor_code"]) if values["vendor_code"] else False
    if values["vendor_code"] and is_one_time and not reserved_code:
        errors["vendor_code"] = t(messages, "validation.one_time_code_required", "One-time records must use a code ending in 9999.")
    if values["vendor_code"] and not is_one_time and reserved_code:
        errors["vendor_code"] = t(messages, "validation.one_time_code_reserved", "Codes ending in 9999 are reserved for one-time records.")
    if values["status"] and values["status"] not in STATUS_VALUES:
        errors["status"] = t(messages, "validation.invalid_status")
    if values["supplier_record_mode"] not in SUPPLIER_RECORD_MODES:
        errors["supplier_record_mode"] = t(messages, "validation.invalid_status")
    parent_entity = find_entity(str(values.get("entity_id", ""))) if values.get("entity_id") else None
    if values.get("entity_id") and (not parent_entity or parent_entity.get("status") != "active"):
        errors["entity_id"] = t(messages, "validation.parent_entity_required")
    if values["vendor_code"] and values["entity_id"] and vendor_code_exists(str(values["vendor_code"]), str(values["entity_id"]), vendors, current_vendor_id):
        errors["vendor_code"] = t(messages, "validation.vendor_code_duplicate", "Vendor Code already exists within the selected Entity.")
    if values["is_qualified_invoice_vendor"] not in {"yes", "no", "unknown"}:
        errors["is_qualified_invoice_vendor"] = t(messages, "validation.invalid_status")
    qualified_invoice_number = str(values.get("qualified_invoice_number", "")).strip().upper()
    if qualified_invoice_number and not re.fullmatch(r"T\d{13}", qualified_invoice_number):
        errors["qualified_invoice_number"] = t(messages, "validation.invalid_qualified_invoice_number", "Qualified Invoice Number must be T followed by 13 digits.")
    return values, errors


def vendor_api_record(vendor: dict[str, Any], lang: str = DEFAULT_LANG) -> dict[str, Any]:
    supplier_record_mode = str(vendor.get("supplier_record_mode", "standard_vendor") or "standard_vendor")
    is_one_time = supplier_record_mode == "one_time_vendor"
    return {
        **vendor,
        "supplier_record_mode": supplier_record_mode,
        "vendor_name": localized_master_name(vendor, "vendor_name", "vendor_code", lang),
        "vendor_label": vendor_label(vendor, lang),
        "is_one_time_vendor": is_one_time,
        "requires_manual_description": is_one_time,
        "manual_description_context": "vendor" if is_one_time else "",
        "record_status": "Active" if vendor.get("status") == "active" else "Inactive",
    }


def render_status(messages: dict[str, str], status: str) -> str:
    return t(messages, f"entity.status.{status}", status)


def render_errors(errors: dict[str, str]) -> str:
    if not errors:
        return ""
    items = "".join(f"<li>{h(message)}</li>" for message in errors.values())
    return f'<div class="alert alert-error"><ul>{items}</ul></div>'


def render_message(messages: dict[str, str], message_key: str, record_name: str = "", timestamp: str = "") -> str:
    if not message_key:
        return ""
    message = t(messages, message_key, message_key)
    if record_name:
        message = f"{message} — {record_name} at {timestamp or now_iso()}."
    return f'<div class="alert alert-success" role="status">{h(message)}</div>'


def render_message_from_query(messages: dict[str, str], query: dict[str, list[str]]) -> str:
    return render_message(messages, query.get("message", [""])[0], query.get("record", [""])[0], query.get("time", [""])[0])


def masterdata_field_label(messages: dict[str, str], record_type: str, field: str) -> str:
    if field == "status":
        return t(messages, "common.status")
    if field == "created_at":
        return t(messages, "common.created_at")
    if field == "updated_at":
        return t(messages, "common.updated_at")
    return t(messages, f"{record_type}.{field}", field.replace("_", " ").title())


def masterdata_display_value(messages: dict[str, str], record_type: str, field: str, value: Any, lang: str) -> str:
    value_text = str(value or "")
    if field == "status":
        return render_status(messages, value_text)
    if record_type == "department" and field == "entity_id":
        return entity_label(find_entity(value_text, include_deleted=True), lang) or value_text
    if record_type == "team" and field == "department_id":
        return department_label(find_department(value_text, include_deleted=True), lang) or value_text
    if record_type == "customer" and field == "customer_record_mode":
        return t(messages, f"customer.customer_record_mode.{value_text or 'standard_customer'}", value_text or "standard_customer")
    if record_type == "customer" and field == "business_types" and isinstance(value, list):
        return ", ".join(str(item) for item in value)
    if record_type == "vendor" and field == "supplier_record_mode":
        return t(messages, f"vendor.supplier_record_mode.{value_text or 'standard_vendor'}", value_text or "standard_vendor")
    if record_type == "vendor" and field == "entity_id":
        return entity_label(find_entity(value_text, include_deleted=True), lang) or value_text
    return value_text


def render_change_governance_block(messages: dict[str, str], errors: dict[str, str], source: dict[str, Any]) -> str:
    reason_error = errors.get("change_reason", "")
    ack_error = errors.get("masterdata_change_ack", "")
    reason_value = str(source.get("change_reason", ""))
    return f"""
    <div class="alert alert-warning">
      <strong>{h(t(messages, "governance.warning_title"))}</strong>
      <p>{h(t(messages, "governance.warning_text"))}</p>
    </div>
    <label for="change_reason">{h(t(messages, "governance.change_reason"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <textarea id="change_reason" name="change_reason">{h(reason_value)}</textarea>
    {f'<div class="field-error">{h(reason_error)}</div>' if reason_error else ''}
    <label><input type="checkbox" name="masterdata_change_ack" value="1"> {h(t(messages, "governance.acknowledge"))}</label>
    {f'<div class="field-error">{h(ack_error)}</div>' if ack_error else ''}
    """


def render_diff_table(record_type: str, before: dict[str, Any], after: dict[str, Any], messages: dict[str, str], lang: str) -> str:
    changed = masterdata_changed_fields(record_type, before, after)
    if not changed:
        return f'<p class="muted">{h(t(messages, "governance.no_field_changes"))}</p>'
    rows = []
    for field in changed:
        rows.append(
            "<tr>"
            f"<td>{h(masterdata_field_label(messages, record_type, field))}</td>"
            f"<td class=\"old-value\">{h(masterdata_display_value(messages, record_type, field, before.get(field, ''), lang))}</td>"
            f"<td class=\"new-value\">{h(masterdata_display_value(messages, record_type, field, after.get(field, ''), lang))}</td>"
            "</tr>"
        )
    return f"""
    <table class="diff-table">
      <thead><tr><th>{h(t(messages, "governance.field"))}</th><th>{h(t(messages, "governance.before"))}</th><th>{h(t(messages, "governance.after"))}</th></tr></thead>
      <tbody>{''.join(rows)}</tbody>
    </table>
    """


def plural_path_for_record_type(record_type: str) -> str:
    return {"entity": "entities", "department": "departments", "team": "teams", "customer": "customers", "vendor": "vendors"}.get(record_type, record_type + "s")


def render_masterdata_version_history(record_type: str, record_id: str, current_record: dict[str, Any], messages: dict[str, str], lang: str, can_restore: bool) -> str:
    versions = masterdata_versions_for_record(record_type, record_id)
    if not versions:
        return f"""
<section class="card">
  <h3>{h(t(messages, "version.history_title"))}</h3>
  <p class="muted">{h(t(messages, "version.no_versions"))}</p>
</section>
"""
    previous_snapshot: dict[str, Any] = {}
    rows = []
    for version in versions:
        snapshot = version.get("data_snapshot", {}) if isinstance(version.get("data_snapshot"), dict) else {}
        compare_html = render_diff_table(record_type, previous_snapshot, snapshot, messages, lang) if previous_snapshot else f'<p class="muted">{h(t(messages, "version.baseline_snapshot"))}</p>'
        restore_html = ""
        if can_restore and snapshot and masterdata_changed_fields(record_type, current_record, snapshot):
            version_id = str(version.get("version_id", ""))
            restore_path = f"/{plural_path_for_record_type(record_type)}/{quote(record_id)}/versions/{quote(version_id)}/restore"
            restore_html = (
                f'<form class="inline-form" method="post" action="{h(url_with_lang(restore_path, lang))}" '
                'data-confirm-reason="1">'
                '<input type="hidden" name="masterdata_change_ack" value="1">'
                '<input type="hidden" name="change_reason" value="">'
                f'<button type="submit">{h(t(messages, "action.restore"))}</button></form>'
            )
        rows.append(
            "<tr>"
            f"<td>v{h(version.get('version_number'))}</td>"
            f"<td>{h(t(messages, 'version.action.' + str(version.get('action', '')), str(version.get('action', ''))))}</td>"
            f"<td>{h(version.get('changed_by'))}</td>"
            f"<td>{h(version.get('changed_at'))}</td>"
            f"<td>{h(version.get('change_reason'))}</td>"
            f"<td><details><summary>{h(t(messages, 'version.compare'))}</summary>{compare_html}</details></td>"
            f"<td>{restore_html}</td>"
            "</tr>"
        )
        previous_snapshot = snapshot
    return f"""
<section class="card">
  <h3>{h(t(messages, "version.history_title"))}</h3>
  <p class="muted">{h(t(messages, "version.history_note"))}</p>
  <table>
    <thead><tr><th>{h(t(messages, "version.version"))}</th><th>{h(t(messages, "version.action"))}</th><th>{h(t(messages, "version.changed_by"))}</th><th>{h(t(messages, "version.changed_at"))}</th><th>{h(t(messages, "version.reason"))}</th><th>{h(t(messages, "version.compare"))}</th><th>{h(t(messages, "common.actions"))}</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
</section>
"""


def render_page(title: str, body: str, lang: str, messages: dict[str, str], current_user: Optional[dict[str, Any]] = None) -> bytes:
    nav_items = [
        ("/dashboard", t(messages, "nav.dashboard")),
        ("/entities", t(messages, "nav.entities")),
        ("/departments", t(messages, "nav.departments")),
        ("/teams", t(messages, "nav.teams")),
    ]
    if current_user and can_customer_master_view(current_user):
        nav_items.append(("/customers", t(messages, "nav.customers", "Customers")))
    if current_user and can_view(current_user):
        nav_items.append(("/vendors", t(messages, "nav.vendors", "Vendors")))
        nav_items.append(("/master-data/system-parameters", t(messages, "nav.system_parameters", "System Parameters")))
    nav_html = "".join(f'<a href="{h(url_with_lang(path, lang))}">{h(label)}</a>' for path, label in nav_items)
    portal_html = (
        f'<a class="portal-link" href="{h(PORTAL_BASE_URL)}" title="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" '
        f'aria-label="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{h(t(messages, "nav.portal", "Back to Portal"))}</a>'
    )
    user_html = ""
    if current_user:
        entity_text = current_entity_label(current_user, lang) or "-"
        user_text = current_user_label(current_user)
        session = current_user.get("_session") if isinstance(current_user.get("_session"), dict) else {}
        login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
        user_html = (
            '<div class="session-context">'
            f'<div class="session-chip"><span>{h(t(messages, "session.entity"))}</span><strong>{h(entity_text)}</strong></div>'
            f'<div class="session-chip"><span>{h(t(messages, "session.user"))}</span><strong>👤 {h(user_text)}</strong><small>{h(login_time)}</small></div>'
            '</div>'
        )
    lang_links = " | ".join(
        f'<a href="{h(url_with_lang("/dashboard", code))}">{h(label)}</a>'
        for code, label in (
            ("en", t(messages, "language.english")),
            ("ja", t(messages, "language.japanese")),
            ("zh", t(messages, "language.chinese")),
        )
    )
    html = f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)} - {h(t(messages, "app.title"))}</title>
  <style>
    :root {{ --bg:#f6f8fb; --card:#ffffff; --ink:#17202a; --muted:#65758b; --line:#d8dee9; --brand:#1f6feb; --navy:#14213d; --danger:#b91c1c; --ok:#047857; }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:var(--ink); }}
    header {{ background:var(--navy); color:white; padding:18px 28px; }}
    header h1 {{ margin:0; font-size:22px; }}
    header p {{ margin:4px 0 0; color:#dbeafe; }}
    .topline {{ display:flex; justify-content:space-between; align-items:flex-start; gap:18px; }}
    .language {{ color:#dbeafe; font-size:13px; }}
    .language a {{ color:white; text-decoration:none; }}
    .session-context {{ display:flex; flex-wrap:wrap; justify-content:flex-end; gap:8px; margin-bottom:8px; }}
    .session-chip {{ display:grid; gap:2px; min-width:140px; padding:7px 10px; border:1px solid rgba(219,234,254,.35); border-radius:12px; background:rgba(255,255,255,.1); color:#dbeafe; text-align:left; }}
    .session-chip span {{ font-size:11px; text-transform:uppercase; letter-spacing:.04em; opacity:.85; }}
    .session-chip strong {{ color:white; font-size:13px; line-height:1.25; }}
    nav {{ display:flex; gap:10px; flex-wrap:wrap; background:white; border-bottom:1px solid var(--line); padding:12px 28px; }}
    nav a {{ display:inline-block; color:var(--navy); text-decoration:none; border:1px solid var(--line); padding:8px 12px; border-radius:999px; font-weight:800; }}
    nav a:hover {{ border-color:var(--brand); color:var(--brand); }}
    nav a.portal-link {{ display:inline-flex; align-items:center; gap:0.35rem; color:#0b4f8a; background:linear-gradient(180deg,#f8fbff 0%,#eaf4ff 100%); border-color:#9cc7f2; box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 1px 2px rgba(15,23,42,.08); }}
    nav a.portal-link:hover {{ color:#064b86; border-color:#1f6feb; background:#ffffff; }}
    .portal-icon {{ font-size:1rem; line-height:1; }}
    main {{ max-width:1120px; margin:24px auto; padding:0 20px 40px; }}
    .card, .sap-section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:20px; box-shadow:0 1px 2px rgba(15,23,42,.04); margin-bottom:18px; }}
    .sap-page-header {{ background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%); border:1px solid var(--line); border-radius:16px; padding:20px; margin-bottom:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(240px,1fr)); gap:16px; }}
    .muted {{ color:var(--muted); }}
    .actions, .sap-toolbar {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; }}
    .sap-toolbar {{ justify-content:flex-end; padding-top:14px; border-top:1px solid var(--line); margin-top:16px; }}
    .button, button {{ background:var(--brand); color:white; border:0; border-radius:9px; padding:9px 13px; text-decoration:none; cursor:pointer; font-size:14px; font-weight:800; }}
    .button.secondary {{ background:#64748b; }}
    .button.danger, button.danger {{ background:var(--danger); }}
    .button.ghost {{ background:#eef2ff; color:#1e40af; }}
    .wide, .table-scroll {{ overflow-x:auto; border:1px solid #e5edf6; border-radius:12px; background:white; }}
    table {{ width:100%; border-collapse:collapse; background:white; }}
    th, td {{ border-bottom:1px solid var(--line); padding:10px; text-align:left; vertical-align:top; }}
    th {{ background:#eef4ff; color:var(--navy); }}
    label {{ display:block; font-weight:800; margin:12px 0 5px; color:#334155; }}
    input, select, textarea {{ width:100%; padding:9px 10px; border:1px solid #cbd5e1; border-radius:8px; font:inherit; }}
    textarea {{ min-height:84px; }}
    input:focus, select:focus, textarea:focus {{ outline:3px solid rgba(31,111,235,.18); border-color:var(--brand); }}
    input[disabled], select[disabled], .locked-field {{ background:#f1f5f9; color:#64748b; cursor:not-allowed; }}
    .field-error {{ color:var(--danger); font-size:13px; margin-top:4px; }}
    .alert {{ border-radius:10px; padding:12px 14px; margin-bottom:16px; }}
    .alert-error {{ background:#fef2f2; color:#991b1b; border:1px solid #fecaca; border-left:4px solid var(--danger); }}
    .alert-success {{ background:#ecfdf5; color:#065f46; border:1px solid #a7f3d0; border-left:4px solid var(--ok); }}
    .alert-warning {{ background:#fffbeb; color:#854d0e; border:1px solid #fde68a; border-left:4px solid #d97706; }}
    .diff-table td.old-value {{ color:#991b1b; }}
    .diff-table td.new-value {{ color:#065f46; }}
    .badge, .status-badge {{ display:inline-block; border-radius:999px; padding:3px 9px; font-size:12px; font-weight:800; background:#e2e8f0; color:#334155; }}
    .badge.active {{ background:#dcfce7; color:#166534; }}
    .badge.inactive {{ background:#fef9c3; color:#854d0e; }}
    .badge.deleted {{ background:#fee2e2; color:#991b1b; }}
    .inline-form {{ display:inline; }}
    .sap-confirm-backdrop {{ position:fixed; inset:0; background:rgba(15,23,42,.48); display:none; align-items:center; justify-content:center; padding:1rem; z-index:50; }}
    .sap-confirm-backdrop.active {{ display:flex; }}
    .sap-confirm-dialog {{ width:min(500px,100%); background:white; border-radius:18px; border:1px solid var(--line); box-shadow:0 24px 80px rgba(15,23,42,.28); padding:1.2rem; }}
    .sap-confirm-dialog h3 {{ margin:0 0 .5rem; color:var(--navy); }}
    @media (max-width:720px) {{
      header {{ padding:16px 18px; }}
      .topline {{ display:block; }}
      .topline > div:last-child {{ margin-top:12px; }}
      .session-context {{ justify-content:flex-start; }}
      .session-chip {{ width:100%; min-width:0; }}
      nav {{ flex-wrap:nowrap; overflow-x:auto; padding:10px 14px; }}
      nav a {{ flex:0 0 auto; min-height:42px; white-space:nowrap; }}
      main {{ margin:0 auto; padding:18px 12px 36px; }}
      .grid {{ grid-template-columns:1fr; }}
      .actions, .sap-toolbar {{ align-items:stretch; flex-direction:column; }}
      .actions .button, .actions button, .sap-toolbar .button, .sap-toolbar button {{ width:100%; text-align:center; }}
      .alert, .message-strip {{ font-size:.98rem; line-height:1.45; padding:.95rem 1rem; border-radius:12px; margin-bottom:1rem; }}
      table {{ display:block; overflow-x:auto; min-width:720px; }}
    }}
  </style>
</head>
<body>
<header>
  <div class="topline">
    <div>
      <h1>{h(t(messages, "app.title"))}</h1>
      <p>{h(t(messages, "app.subtitle"))}</p>
    </div>
    <div>
      {user_html}<br>
      <span class="language">{h(t(messages, "language.label"))}: {lang_links}</span>
    </div>
  </div>
</header>
<nav>{portal_html}{nav_html}</nav>
<main>{body}</main>
<div class="sap-confirm-backdrop" id="sapConfirmBackdrop" aria-hidden="true"><div class="sap-confirm-dialog" role="dialog" aria-modal="true"><h3>{h(t(messages, 'confirm.title', 'Confirm action'))}</h3><p>{h(t(messages, 'governance.deactivate_reason_prompt'))}</p><label for="sapConfirmReason">{h(t(messages, 'version.reason'))}</label><textarea id="sapConfirmReason" required></textarea><div class="actions"><button type="button" class="danger" id="sapConfirmOk">{h(t(messages, 'confirm.ok', 'Confirm'))}</button><button type="button" class="button ghost" id="sapConfirmCancel">{h(t(messages, 'confirm.cancel', 'Cancel'))}</button></div></div></div>
<script>
(() => {{ const backdrop = document.getElementById('sapConfirmBackdrop'); const ok = document.getElementById('sapConfirmOk'); const cancel = document.getElementById('sapConfirmCancel'); const reason = document.getElementById('sapConfirmReason'); let pendingForm = null; document.addEventListener('submit', (event) => {{ const form = event.target; if (!form || !form.matches('[data-confirm-reason]')) return; event.preventDefault(); pendingForm = form; reason.value = ''; backdrop.classList.add('active'); backdrop.setAttribute('aria-hidden','false'); reason.focus(); }}); ok.addEventListener('click', () => {{ if (!pendingForm) return; const value = reason.value.trim(); if (!value) {{ reason.focus(); return; }} const input = pendingForm.querySelector('input[name="change_reason"]'); if (input) input.value = value; const f = pendingForm; pendingForm = null; backdrop.classList.remove('active'); f.submit(); }}); cancel.addEventListener('click', () => {{ pendingForm = null; backdrop.classList.remove('active'); backdrop.setAttribute('aria-hidden','true'); }}); backdrop.addEventListener('click', (event) => {{ if (event.target === backdrop) cancel.click(); }}); }})();
</script>
</body>
</html>"""
    return html.encode("utf-8")


def hmac_compare(left: str, right: str) -> bool:
    if len(left) != len(right):
        return False
    result = 0
    for left_char, right_char in zip(left.encode("utf-8"), right.encode("utf-8")):
        result |= left_char ^ right_char
    return result == 0


class MasterDataHandler(BaseHTTPRequestHandler):
    server_version = "TACAIMasterData/0.1"

    def flash_message_payload(self) -> dict[str, str]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(FLASH_COOKIE)
        if not morsel:
            return {}
        try:
            data = json.loads(unquote(morsel.value))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def flash_cookie_header(self, message_key: str, record: str = "", timestamp: str = "") -> str:
        cookie = SimpleCookie()
        cookie[FLASH_COOKIE] = quote(json.dumps({"message": message_key, "record": record, "time": timestamp or now_iso()}))
        cookie[FLASH_COOKIE]["path"] = "/"
        cookie[FLASH_COOKIE]["samesite"] = "Lax"
        return cookie.output(header="").strip()

    def clear_flash_cookie_header(self) -> str:
        return f"{FLASH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax"

    def send_html(self, status: int, title: str, body: str, lang: str, messages: dict[str, str], current_user: Optional[dict[str, Any]] = None) -> None:
        flash = self.flash_message_payload()
        if flash:
            body = render_message(messages, flash.get("message", ""), flash.get("record", ""), flash.get("time", "")) + body
        payload = render_page(title, body, lang, messages, current_user)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if flash:
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_text(self, status: int, text: str) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, status: int, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str, status: int = 303) -> None:
        parsed = urlparse(location)
        query = parse_qs(parsed.query)
        message_key = query.get("message", [""])[0]
        record = query.get("record", [""])[0]
        timestamp = query.get("time", [""])[0]
        if message_key:
            clean_query = {key: values[-1] for key, values in query.items() if key not in {"message", "record", "time"} and values}
            location = parsed._replace(query=urlencode(clean_query)).geturl()
        self.send_response(status)
        self.send_header("Location", location)
        if message_key:
            self.send_header("Set-Cookie", self.flash_cookie_header(message_key, record, timestamp))
        self.end_headers()

    def parse_form_body(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        raw = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(raw, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        return parsed.hostname in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS

    def current_user(self) -> Optional[dict[str, Any]]:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        if not session_cookie:
            return None
        return validate_user_admin_session(session_cookie.value)

    def is_api_request(self) -> bool:
        return urlparse(self.path).path.startswith("/api/")

    def require_user(self, lang: str, messages: dict[str, str]) -> Optional[dict[str, Any]]:
        user = self.current_user()
        if user and has_entity_context(user):
            return user
        if user and not has_entity_context(user):
            if self.is_api_request():
                self.send_json(403, {"error": t(messages, "auth.entity_required")})
                return None
            body = f"""
<section class="card">
  <h2>{h(t(messages, "auth.entity_required"))}</h2>
  <p class="muted">{h(t(messages, "auth.entity_required_text"))}</p>
  <p><a class="button secondary" href="{h(USER_ADMIN_BASE_URL + '/login')}">{h(t(messages, "auth.login_required"))}</a></p>
</section>
"""
            self.send_html(403, t(messages, "auth.entity_required"), body, lang, messages, user)
            return None
        if self.is_api_request():
            self.send_json(401, {"error": t(messages, "api.unauthorized")})
            return None
        next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
        self.redirect(f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
        return None

    def require_permission(self, user: dict[str, Any], permission_key: str, lang: str, messages: dict[str, str]) -> bool:
        if has_permission(user, permission_key):
            return True
        if self.is_api_request():
            self.send_json(403, {"error": t(messages, "api.forbidden")})
        else:
            self.send_forbidden(lang, messages, user)
        return False

    def send_forbidden(self, lang: str, messages: dict[str, str], user: Optional[dict[str, Any]] = None) -> None:
        if self.is_api_request():
            self.send_json(403, {"error": t(messages, "api.forbidden")})
            return
        body = f"""
<section class="card">
  <h2>{h(t(messages, "auth.access_denied"))}</h2>
  <p class="muted">{h(t(messages, "auth.access_denied_text"))}</p>
  <p><a class="button secondary" href="{h(url_with_lang('/dashboard', lang))}">{h(t(messages, "nav.dashboard"))}</a></p>
</section>
"""
        self.send_html(403, t(messages, "auth.access_denied"), body, lang, messages, user)

    def send_not_found(self, lang: str, messages: dict[str, str], user: Optional[dict[str, Any]] = None, message_key: str = "entity.not_found", back_path: str = "/entities") -> None:
        body = f"""
<section class="card">
  <h2>{h(t(messages, message_key))}</h2>
  <p><a class="button secondary" href="{h(url_with_lang(back_path, lang))}">{h(t(messages, "action.back"))}</a></p>
</section>
"""
        self.send_html(404, t(messages, message_key), body, lang, messages, user)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        messages = load_i18n(lang)
        path = parsed.path
        parts = [part for part in path.split("/") if part]

        if path == "/health":
            self.send_text(200, "OK")
            return

        if path == "/":
            self.redirect(url_with_lang("/dashboard", lang))
            return

        if path == "/api/master-data/system-parameters/outbound-email-onboarding":
            self.send_outbound_email_settings_api()
            return

        user = self.require_user(lang, messages)
        if not user:
            return

        if path == "/dashboard":
            if not self.require_permission(user, "masterdata.access", lang, messages):
                return
            self.send_dashboard(lang, messages, user)
        elif path == "/entities":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_entities_list(lang, messages, user, query)
        elif path == "/entities/new":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            self.send_entity_form(lang, messages, user, "create", None, {})
        elif len(parts) == 2 and parts[0] == "entities":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            entity = find_entity(parts[1])
            if not entity or not entity_accessible_to_user(entity, user):
                self.send_not_found(lang, messages, user)
                return
            self.send_entity_detail(lang, messages, user, parts[1], query)
        elif len(parts) == 3 and parts[0] == "entities" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            entity = find_entity(parts[1])
            if not entity or not entity_accessible_to_user(entity, user):
                self.send_not_found(lang, messages, user)
                return
            self.send_entity_form(lang, messages, user, "edit", entity, {})
        elif path == "/departments":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_departments_list(lang, messages, user, query)
        elif path == "/departments/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.send_department_form(lang, messages, user, "create", None, {})
        elif len(parts) == 2 and parts[0] == "departments":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            department = find_department(parts[1])
            if not department or not department_accessible_to_user(department, user):
                self.send_not_found(lang, messages, user, "department.not_found", "/departments")
                return
            self.send_department_detail(lang, messages, user, parts[1], query)
        elif len(parts) == 3 and parts[0] == "departments" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            department = find_department(parts[1])
            if not department or not department_accessible_to_user(department, user):
                self.send_not_found(lang, messages, user, "department.not_found", "/departments")
                return
            self.send_department_form(lang, messages, user, "edit", department, {})
        elif path == "/teams":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_teams_list(lang, messages, user, query)
        elif path == "/teams/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.send_team_form(lang, messages, user, "create", None, {}, query=query)
        elif len(parts) == 2 and parts[0] == "teams":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            team = find_team(parts[1])
            if not team or not team_accessible_to_user(team, user):
                self.send_not_found(lang, messages, user, "team.not_found", "/teams")
                return
            self.send_team_detail(lang, messages, user, parts[1], query)
        elif len(parts) == 3 and parts[0] == "teams" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            team = find_team(parts[1])
            if not team or not team_accessible_to_user(team, user):
                self.send_not_found(lang, messages, user, "team.not_found", "/teams")
                return
            self.send_team_form(lang, messages, user, "edit", team, {})
        elif path == "/vendors":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_vendors_list(lang, messages, user, query)
        elif path == "/vendors/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.send_vendor_form(lang, messages, user, "create", None, {})
        elif len(parts) == 2 and parts[0] == "vendors":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            vendor = find_vendor(parts[1])
            if not vendor or not vendor_accessible_to_user(vendor, user):
                self.send_not_found(lang, messages, user, "vendor.not_found", "/vendors")
                return
            self.send_vendor_detail(lang, messages, user, parts[1], query)
        elif len(parts) == 3 and parts[0] == "vendors" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            vendor = find_vendor(parts[1])
            if not vendor or not vendor_accessible_to_user(vendor, user):
                self.send_not_found(lang, messages, user, "vendor.not_found", "/vendors")
                return
            self.send_vendor_form(lang, messages, user, "edit", vendor, {})
        elif path == "/customers":
            if not can_customer_master_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_customers_list(lang, messages, user, query)
        elif path == "/master-data/system-parameters":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_system_parameters_list(lang, messages, user)
        elif path == "/master-data/system-parameters/email-onboarding":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_outbound_email_settings_form(lang, messages, user, {})
        elif path == "/customers/new":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_customer_form(lang, messages, user, "create", None, {})
        elif len(parts) == 2 and parts[0] == "customers":
            if not can_customer_master_view(user):
                self.send_forbidden(lang, messages, user)
                return
            customer = find_customer(parts[1])
            if not customer:
                self.send_not_found(lang, messages, user, "customer.not_found", "/customers")
                return
            self.send_customer_detail(lang, messages, user, parts[1], query)
        elif len(parts) == 3 and parts[0] == "customers" and parts[2] == "edit":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            customer = find_customer(parts[1])
            if not customer:
                self.send_not_found(lang, messages, user, "customer.not_found", "/customers")
                return
            self.send_customer_form(lang, messages, user, "edit", customer, {})
        elif path == "/api/customers":
            if not can_customer_master_view(user):
                self.send_forbidden(lang, messages, user)
                return
            include_inactive = query.get("include_inactive", [""])[0] == "1" and can_customer_master_maintain(user)
            customers = visible_customers() if include_inactive else active_customers()
            customers = sorted(customers, key=lambda item: str(item.get("customer_code", "")).casefold())
            self.send_json(200, [customer_api_record(customer) for customer in customers])
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "customers":
            if not can_customer_master_view(user):
                self.send_forbidden(lang, messages, user)
                return
            customer = find_customer(parts[2])
            if not customer or customer.get("status") != "active":
                self.send_json(404, {"error": t(messages, "customer.not_found", "Customer not found.")})
                return
            self.send_json(200, customer_api_record(customer))
        elif path == "/api/vendors/active" or path == "/api/vendors":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            include_inactive = query.get("include_inactive", [""])[0] == "1" and can_maintain(user)
            vendors = visible_vendors_for_user(user) if include_inactive else active_vendors_for_user(user)
            vendors = sorted(vendors, key=lambda item: str(item.get("vendor_code", "")).casefold())
            self.send_json(200, [vendor_api_record(vendor, lang) for vendor in vendors])
        elif len(parts) == 3 and parts[0] == "api" and parts[1] == "vendors":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            vendor = find_vendor(parts[2])
            if not vendor or vendor.get("status") != "active" or not vendor_accessible_to_user(vendor, user):
                self.send_json(404, {"error": t(messages, "vendor.not_found", "Vendor not found.")})
                return
            self.send_json(200, vendor_api_record(vendor, lang))
        elif path == "/api/entities/current":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            entity = find_entity(current_entity_id(user))
            self.send_json(200, entity if entity else {})
        elif path == "/api/entities":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            self.send_json(200, active_entities_for_user(user))
        elif path == "/api/departments":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            entity_filter = query.get("entity_id", [""])[0]
            departments = [item for item in visible_departments_for_user(user) if item.get("status") == "active"]
            if entity_filter:
                departments = [item for item in departments if str(item.get("entity_id", "")) == entity_filter]
            self.send_json(200, departments)
        elif path == "/api/teams":
            if not can_view(user):
                self.send_forbidden(lang, messages, user)
                return
            department_filter = query.get("department_id", [""])[0]
            teams = [item for item in visible_teams_for_user(user) if item.get("status") == "active"]
            if department_filter:
                parent = find_department(department_filter)
                if not parent or not department_accessible_to_user(parent, user):
                    self.send_json(200, [])
                    return
                teams = [item for item in teams if str(item.get("department_id", "")) == department_filter]
            self.send_json(200, teams)
        else:
            self.send_not_found(lang, messages, user)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        messages = load_i18n(lang)
        path = parsed.path
        parts = [part for part in path.split("/") if part]

        if not self.csrf_origin_allowed():
            if self.is_api_request():
                self.send_json(403, {"error": t(messages, "validation.csrf")})
            else:
                self.send_forbidden(lang, messages)
            return

        user = self.require_user(lang, messages)
        if not user:
            return

        if path == "/entities/new":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            self.handle_create_entity(lang, messages, user)
        elif len(parts) == 3 and parts[0] == "entities" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            self.handle_update_entity(lang, messages, user, parts[1])
        elif len(parts) == 5 and parts[0] == "entities" and parts[2] == "versions" and parts[4] == "restore":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            self.handle_restore_master_record(lang, messages, user, "entity", parts[1], parts[3])
        elif len(parts) == 3 and parts[0] == "entities" and parts[2] == "delete":
            if not self.require_permission(user, "masterdata.admin", lang, messages):
                return
            self.handle_delete_entity(lang, messages, user, parts[1])
        elif path == "/departments/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_create_department(lang, messages, user)
        elif len(parts) == 3 and parts[0] == "departments" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_update_department(lang, messages, user, parts[1])
        elif len(parts) == 5 and parts[0] == "departments" and parts[2] == "versions" and parts[4] == "restore":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_restore_master_record(lang, messages, user, "department", parts[1], parts[3])
        elif len(parts) == 3 and parts[0] == "departments" and parts[2] == "delete":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_delete_department(lang, messages, user, parts[1])
        elif path == "/teams/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_create_team(lang, messages, user)
        elif len(parts) == 3 and parts[0] == "teams" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_update_team(lang, messages, user, parts[1])
        elif len(parts) == 5 and parts[0] == "teams" and parts[2] == "versions" and parts[4] == "restore":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_restore_master_record(lang, messages, user, "team", parts[1], parts[3])
        elif len(parts) == 3 and parts[0] == "teams" and parts[2] == "delete":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_delete_team(lang, messages, user, parts[1])
        elif path == "/vendors/ocr":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_vendor_ocr(lang, messages, user)
        elif path == "/vendors/new":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_create_vendor(lang, messages, user)
        elif len(parts) == 3 and parts[0] == "vendors" and parts[2] == "edit":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_update_vendor(lang, messages, user, parts[1])
        elif len(parts) == 5 and parts[0] == "vendors" and parts[2] == "versions" and parts[4] == "restore":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_restore_master_record(lang, messages, user, "vendor", parts[1], parts[3])
        elif len(parts) == 3 and parts[0] == "vendors" and parts[2] == "delete":
            if not self.require_permission(user, "masterdata.maintain", lang, messages):
                return
            self.handle_delete_vendor(lang, messages, user, parts[1])
        elif path == "/customers/ocr":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_customer_ocr(lang, messages, user)
        elif path == "/customers/new":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_create_customer(lang, messages, user)
        elif path == "/master-data/system-parameters/email-onboarding":
            if not can_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_update_outbound_email_settings(lang, messages, user)
        elif path == "/master-data/system-parameters/email-onboarding/test":
            if not can_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_test_outbound_email_settings(lang, messages, user)
        elif len(parts) == 3 and parts[0] == "customers" and parts[2] == "edit":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_update_customer(lang, messages, user, parts[1])
        elif len(parts) == 5 and parts[0] == "customers" and parts[2] == "versions" and parts[4] == "restore":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_restore_master_record(lang, messages, user, "customer", parts[1], parts[3])
        elif len(parts) == 3 and parts[0] == "customers" and parts[2] == "delete":
            if not can_customer_master_maintain(user):
                self.send_forbidden(lang, messages, user)
                return
            self.handle_delete_customer(lang, messages, user, parts[1])
        else:
            self.send_not_found(lang, messages, user)


    def system_parameter_from_form(self, messages: dict[str, str], form: dict[str, str], user: dict[str, Any], existing: Optional[dict[str, Any]] = None) -> tuple[dict[str, Any], dict[str, str]]:
        actor = actor_label(user)
        parameter = copy.deepcopy(existing or default_outbound_email_parameter(actor))
        previous_value = parameter.get("value") if isinstance(parameter.get("value"), dict) else {}
        errors: dict[str, str] = {}
        enabled = form.get("enabled") == "1"
        sender_display_name = normalize_text(form.get("sender_display_name") or "TAC HR Admin")
        sender_email = normalize_text(form.get("sender_email"))
        reply_to_email = normalize_text(form.get("reply_to_email"))
        hr_notification_email = normalize_text(form.get("hr_notification_email"))
        department_manager_cc_emails = normalize_email_list([
            form.get("department_manager_cc_email_1", ""),
            form.get("department_manager_cc_email_2", ""),
            form.get("department_manager_cc_email_3", ""),
        ], 3)
        smtp_host = normalize_text(form.get("smtp_host"))
        smtp_username = normalize_text(form.get("smtp_username"))
        password_config_mode = normalize_text(form.get("password_config_mode") or "environment")
        password_secret_ref = normalize_text(form.get("password_secret_ref") or "ONBOARDING_SMTP_PASSWORD")
        smtp_port = config_int(form.get("smtp_port", "587"), 587)
        smtp_timeout = config_int(form.get("smtp_timeout_seconds", "15"), 15)
        if password_config_mode not in {"environment", "secret_ref"}:
            errors["password_config_mode"] = t(messages, "system_parameters.validation.password_mode")
        if smtp_port < 1 or smtp_port > 65535:
            errors["smtp_port"] = t(messages, "system_parameters.validation.smtp_port")
        if smtp_timeout < 1 or smtp_timeout > 120:
            errors["smtp_timeout_seconds"] = t(messages, "system_parameters.validation.timeout")
        for field, email in (("sender_email", sender_email), ("reply_to_email", reply_to_email), ("hr_notification_email", hr_notification_email)):
            if email and not EMAIL_PATTERN.fullmatch(email):
                errors[field] = t(messages, "validation.invalid_email", "Invalid email address.")
                break
        cc_error = validate_email_list(department_manager_cc_emails, messages, 3)
        if cc_error:
            errors["department_manager_cc_emails"] = cc_error
        if enabled:
            if not sender_email or not smtp_host or not smtp_username:
                errors["required"] = t(messages, "system_parameters.validation.required_email_settings")
            if not password_secret_ref:
                errors["password_secret_ref"] = t(messages, "system_parameters.validation.password_secret_ref_required")
        value = {
            "sender_display_name": sender_display_name,
            "sender_email": sender_email,
            "reply_to_email": reply_to_email,
            "hr_notification_email": hr_notification_email,
            "department_manager_cc_emails": department_manager_cc_emails,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_username": smtp_username,
            "smtp_use_tls": form.get("smtp_use_tls") == "1",
            "smtp_use_ssl": form.get("smtp_use_ssl") == "1",
            "smtp_timeout_seconds": smtp_timeout,
            "password_config_mode": password_config_mode,
            "password_secret_ref": password_secret_ref,
            "last_test_status": str(previous_value.get("last_test_status", "") or ""),
            "last_test_at": str(previous_value.get("last_test_at", "") or ""),
            "last_test_by": str(previous_value.get("last_test_by", "") or ""),
            "last_test_error": str(previous_value.get("last_test_error", "") or ""),
        }
        timestamp = now_iso()
        parameter.update({
            "parameter_id": SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID,
            "module": "masterdata.system_parameters",
            "category": "communication",
            "subcategory": "outbound_email",
            "scenario": "onboarding",
            "display_name": "Onboarding outbound email settings",
            "description": "SMTP settings for onboarding invitation, candidate verification, HR notifications, and return-to-candidate emails.",
            "enabled": enabled,
            "value_type": "object",
            "value": value,
            "secret_status": outbound_email_secret_status(value),
            "environment": "local",
            "status": "active",
            "sort_order": 10,
            "updated_at": timestamp,
            "updated_by": actor,
        })
        if not parameter.get("created_at"):
            parameter["created_at"] = timestamp
        if not parameter.get("created_by"):
            parameter["created_by"] = actor
        return normalize_system_parameter(parameter), errors

    def send_system_parameters_list(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        rows = []
        can_edit = can_maintain(user)
        for parameter in load_system_parameters():
            parameter_id = str(parameter.get("parameter_id", ""))
            actions = ""
            if parameter_id == SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID:
                actions = f'<a href="{h(url_with_lang("/master-data/system-parameters/email-onboarding", lang))}">{h(t(messages, "action.view"))}</a>'
                if can_edit:
                    actions += f' | <a href="{h(url_with_lang("/master-data/system-parameters/email-onboarding", lang))}">{h(t(messages, "action.edit"))}</a>'
            rows.append(f"""
<tr>
  <td>{h(parameter_id)}</td>
  <td>{h(str(parameter.get('category', '')))}</td>
  <td>{h(str(parameter.get('scenario', '')))}</td>
  <td>{h('Yes' if parameter.get('enabled') else 'No')}</td>
  <td>{h(str(parameter.get('secret_status', '')))}</td>
  <td>{h(str(parameter.get('updated_at', '')))}</td>
  <td>{h(str(parameter.get('updated_by', '')))}</td>
  <td>{actions}</td>
</tr>""")
        table_rows = "".join(rows) or f'<tr><td colspan="8" class="empty">{h(t(messages, "system_parameters.empty"))}</td></tr>'
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'system_parameters.title'))}</h2>
  <p class="muted">{h(t(messages, 'system_parameters.description'))}</p>
  <table>
    <thead><tr><th>{h(t(messages, 'system_parameters.parameter_id'))}</th><th>{h(t(messages, 'system_parameters.category'))}</th><th>{h(t(messages, 'system_parameters.scenario'))}</th><th>{h(t(messages, 'system_parameters.enabled'))}</th><th>{h(t(messages, 'system_parameters.secret_status'))}</th><th>{h(t(messages, 'system_parameters.updated_at'))}</th><th>{h(t(messages, 'system_parameters.updated_by'))}</th><th>{h(t(messages, 'common.actions'))}</th></tr></thead>
    <tbody>{table_rows}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "system_parameters.title"), body, lang, messages, user)

    def send_outbound_email_settings_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], errors: dict[str, str], parameter: Optional[dict[str, Any]] = None) -> None:
        parameter = normalize_system_parameter(parameter or find_system_parameter(SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID) or default_outbound_email_parameter())
        value = parameter.get("value") if isinstance(parameter.get("value"), dict) else {}
        can_edit = can_maintain(user)
        disabled = "" if can_edit else " disabled"
        cc_values = normalize_email_list(value.get("department_manager_cc_emails", []), 3)
        while len(cc_values) < 3:
            cc_values.append("")
        mode_options = "".join(
            f'<option value="{h(mode)}"{selected(str(value.get("password_config_mode", "environment")), mode)}>{h(t(messages, "system_parameters.password_mode." + mode))}</option>'
            for mode in ["environment", "secret_ref"]
        )
        status_rows = "".join(
            f'<div><strong>{h(label)}</strong><br><span class="muted">{h(val or "-")}</span></div>'
            for label, val in [
                (t(messages, "system_parameters.secret_status"), str(parameter.get("secret_status", ""))),
                (t(messages, "system_parameters.last_test_status"), str(value.get("last_test_status", ""))),
                (t(messages, "system_parameters.last_test_at"), str(value.get("last_test_at", ""))),
                (t(messages, "system_parameters.last_test_by"), str(value.get("last_test_by", ""))),
                (t(messages, "system_parameters.last_test_error"), str(value.get("last_test_error", ""))),
            ]
        )
        save_button = f'<button type="submit">{h(t(messages, "action.save"))}</button>' if can_edit else ""
        test_form = ""
        if can_edit:
            test_form = f"""
  <section class="card"><h3>{h(t(messages, 'system_parameters.test_email'))}</h3>
    <p class="muted">{h(t(messages, 'system_parameters.test_email_hint'))}</p>
    <form method="post" action="{h(url_with_lang('/master-data/system-parameters/email-onboarding/test', lang))}">
      <label for="test_recipient">{h(t(messages, 'system_parameters.test_recipient'))}</label>
      <input id="test_recipient" name="test_recipient" type="email" value="{h(value.get('hr_notification_email'))}" required>
      <div class="sap-toolbar"><button type="submit">{h(t(messages, 'system_parameters.send_test_email'))}</button></div>
    </form>
  </section>
"""
        body = f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'system_parameters.title'))}</p>
  <h2>{h(t(messages, 'system_parameters.email_settings_title'))}</h2>
  <p>{h(t(messages, 'system_parameters.email_settings_description'))}</p>
  <a class="button secondary" href="{h(url_with_lang('/master-data/system-parameters', lang))}">{h(t(messages, 'action.back'))}</a>
</section>
<section class="card">
  <form method="post" action="{h(url_with_lang('/master-data/system-parameters/email-onboarding', lang))}">
    {render_errors(errors)}
    <div class="grid">
      <label><input type="checkbox" name="enabled" value="1"{checked(parameter.get('enabled'))}{disabled}> {h(t(messages, 'system_parameters.enabled'))}</label>
      <label>{h(t(messages, 'system_parameters.parameter_id'))}<input value="{h(parameter.get('parameter_id'))}" disabled></label>
      <label>{h(t(messages, 'system_parameters.environment'))}<input value="{h(parameter.get('environment'))}" disabled></label>
    </div>
    <h3>{h(t(messages, 'system_parameters.sender_settings'))}</h3>
    <div class="grid">
      <label>{h(t(messages, 'system_parameters.sender_display_name'))}<input name="sender_display_name" value="{h(value.get('sender_display_name'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.sender_email'))}<input name="sender_email" type="email" value="{h(value.get('sender_email'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.reply_to_email'))}<input name="reply_to_email" type="email" value="{h(value.get('reply_to_email'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.hr_notification_email'))}<input name="hr_notification_email" type="email" value="{h(value.get('hr_notification_email'))}"{disabled}></label>
    </div>
    <h3>{h(t(messages, 'system_parameters.department_manager_cc_emails'))}</h3>
    <p class="muted">{h(t(messages, 'system_parameters.department_manager_cc_hint'))}</p>
    <div class="grid">
      <label>{h(t(messages, 'system_parameters.department_manager_cc_email_1'))}<input name="department_manager_cc_email_1" type="email" value="{h(cc_values[0])}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.department_manager_cc_email_2'))}<input name="department_manager_cc_email_2" type="email" value="{h(cc_values[1])}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.department_manager_cc_email_3'))}<input name="department_manager_cc_email_3" type="email" value="{h(cc_values[2])}"{disabled}></label>
    </div>
    <h3>{h(t(messages, 'system_parameters.smtp_settings'))}</h3>
    <div class="grid">
      <label>{h(t(messages, 'system_parameters.smtp_host'))}<input name="smtp_host" value="{h(value.get('smtp_host'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.smtp_port'))}<input name="smtp_port" type="number" min="1" max="65535" value="{h(value.get('smtp_port'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.smtp_username'))}<input name="smtp_username" value="{h(value.get('smtp_username'))}"{disabled}></label>
      <label>{h(t(messages, 'system_parameters.smtp_timeout_seconds'))}<input name="smtp_timeout_seconds" type="number" min="1" max="120" value="{h(value.get('smtp_timeout_seconds'))}"{disabled}></label>
      <label><input type="checkbox" name="smtp_use_tls" value="1"{checked(value.get('smtp_use_tls'))}{disabled}> {h(t(messages, 'system_parameters.smtp_use_tls'))}</label>
      <label><input type="checkbox" name="smtp_use_ssl" value="1"{checked(value.get('smtp_use_ssl'))}{disabled}> {h(t(messages, 'system_parameters.smtp_use_ssl'))}</label>
    </div>
    <h3>{h(t(messages, 'system_parameters.secret_settings'))}</h3>
    <p class="muted">{h(t(messages, 'system_parameters.secret_note'))}</p>
    <div class="grid">
      <label>{h(t(messages, 'system_parameters.password_config_mode'))}<select name="password_config_mode"{disabled}>{mode_options}</select></label>
      <label>{h(t(messages, 'system_parameters.password_secret_ref'))}<input name="password_secret_ref" value="{h(value.get('password_secret_ref'))}"{disabled}></label>
    </div>
    <h3>{h(t(messages, 'system_parameters.status'))}</h3>
    <div class="grid">{status_rows}</div>
    <label>{h(t(messages, 'governance.change_reason', 'Change Reason'))}<textarea name="change_reason"></textarea></label>
    <div class="sap-toolbar">{save_button}<a class="button secondary" href="{h(url_with_lang('/master-data/system-parameters', lang))}">{h(t(messages, 'action.cancel'))}</a></div>
  </form>
</section>
{test_form}
"""
        self.send_html(200, t(messages, "system_parameters.email_settings_title"), body, lang, messages, user)

    def handle_update_outbound_email_settings(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        before = normalize_system_parameter(find_system_parameter(SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID) or default_outbound_email_parameter(actor_label(user)))
        parameter, errors = self.system_parameter_from_form(messages, form, user, before)
        if errors:
            self.send_outbound_email_settings_form(lang, messages, user, errors, parameter)
            return
        updated = upsert_system_parameter(parameter)
        changed = system_parameter_changed_fields(before, updated)
        change_reason = normalize_text(form.get("change_reason")) or "Updated onboarding outbound email settings."
        if changed:
            safe_before = sanitize_system_parameter(before)
            safe_after = sanitize_system_parameter(updated)
            version = append_masterdata_version("system_parameters", SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID, "update", user, safe_after, change_reason, changed)
            append_audit("system_parameters", SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID, "system_parameter_updated", user, safe_before, safe_after, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/master-data/system-parameters/email-onboarding", lang, {"message": "system_parameters.saved"}))

    def handle_test_outbound_email_settings(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        recipient = normalize_text(form.get("test_recipient"))
        if not recipient or not EMAIL_PATTERN.fullmatch(recipient):
            self.send_outbound_email_settings_form(lang, messages, user, {"test_recipient": t(messages, "validation.invalid_email", "Invalid email address.")})
            return
        before = normalize_system_parameter(find_system_parameter(SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID) or default_outbound_email_parameter(actor_label(user)))
        sent, email_status = send_outbound_email_test(recipient, actor_label(user))
        updated = copy.deepcopy(before)
        value = updated.get("value") if isinstance(updated.get("value"), dict) else {}
        value["last_test_status"] = "sent" if sent else "failed"
        value["last_test_at"] = now_iso()
        value["last_test_by"] = actor_label(user)
        value["last_test_error"] = "" if sent else email_status
        updated["value"] = value
        updated["secret_status"] = outbound_email_secret_status(value)
        updated["updated_at"] = now_iso()
        updated["updated_by"] = actor_label(user)
        updated = upsert_system_parameter(updated)
        action = "system_parameter_test_email_sent" if sent else "system_parameter_test_email_failed"
        append_audit("system_parameters", SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID, action, user, sanitize_system_parameter(before), sanitize_system_parameter(updated), f"Outbound email test {email_status}", system_parameter_changed_fields(before, updated))
        notice_key = "system_parameters.test_email_sent" if sent else "system_parameters.test_email_failed"
        self.redirect(url_with_lang("/master-data/system-parameters/email-onboarding", lang, {"message": notice_key, "record": email_status}))

    def send_outbound_email_settings_api(self) -> None:
        expected = MASTERDATA_INTERNAL_API_TOKEN
        provided = self.headers.get("X-TACAI-Internal-Token", "").strip()
        if not expected or not provided or not hmac_compare(provided, expected):
            self.send_json(401, {"ok": False, "error": "unauthorized"})
            return
        parameter = find_system_parameter(SYSTEM_PARAMETER_OUTBOUND_EMAIL_ID)
        if not parameter:
            self.send_json(404, {"ok": False, "error": "not_found"})
            return
        settings = outbound_email_runtime_settings(parameter)
        runtime_error = outbound_email_runtime_error(settings)
        if runtime_error:
            status = 409 if runtime_error in {"disabled", "missing", "not_configured", "encrypted_unsupported", "unsupported_password_mode"} else 500
            payload = {key: value for key, value in settings.items() if key != "smtp_password"}
            payload.update({"ok": False, "error": runtime_error})
            self.send_json(status, payload)
            return
        self.send_json(200, {"ok": True, **settings})

    def send_dashboard(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        vendor_actions = ""
        if can_view(user):
            vendor_actions = f'<a class="button" href="{h(url_with_lang("/vendors", lang))}">{h(t(messages, "action.view"))}</a>'
            if can_maintain(user):
                vendor_actions += f' <a class="button secondary" href="{h(url_with_lang("/vendors/new", lang))}">{h(t(messages, "action.create_vendor", "Create Vendor"))}</a>'
        vendor_card = (
            f'<article class="card"><h3>{h(t(messages, "nav.vendors", "Vendors"))}</h3>'
            f'<p class="muted">{h(t(messages, "dashboard.vendors.description", "Manage supplier and vendor master data used by Vendor Payments."))}</p>'
            f'<div class="actions">{vendor_actions}</div></article>'
            if can_view(user)
            else ""
        )
        system_parameters_card = (
            f'<article class="card"><h3>{h(t(messages, "nav.system_parameters", "System Parameters"))}</h3>'
            f'<p class="muted">{h(t(messages, "dashboard.system_parameters.description", "Manage business-operable system settings and outbound email configuration."))}</p>'
            f'<div class="actions"><a class="button" href="{h(url_with_lang("/master-data/system-parameters", lang))}">{h(t(messages, "action.view"))}</a></div></article>'
            if can_view(user)
            else ""
        )
        body = f"""
<section class="card">
  <h2>{h(t(messages, "dashboard.title"))}</h2>
  <p class="muted">{h(t(messages, "dashboard.description"))}</p>
</section>
<section class="grid">
  <article class="card">
    <h3>{h(t(messages, "nav.entities"))}</h3>
    <p class="muted">{h(t(messages, "dashboard.entities.description"))}</p>
    <a class="button" href="{h(url_with_lang('/entities', lang))}">{h(t(messages, "action.view"))}</a>
  </article>
  <article class="card">
    <h3>{h(t(messages, "nav.departments"))}</h3>
    <p class="muted">{h(t(messages, "dashboard.departments.description"))}</p>
    <a class="button" href="{h(url_with_lang('/departments', lang))}">{h(t(messages, "action.view"))}</a>
  </article>
  <article class="card">
    <h3>{h(t(messages, "nav.teams"))}</h3>
    <p class="muted">{h(t(messages, "dashboard.teams.description"))}</p>
    <a class="button" href="{h(url_with_lang('/teams', lang))}">{h(t(messages, "action.view"))}</a>
  </article>
  {f'<article class="card"><h3>{h(t(messages, "nav.customers", "Customers"))}</h3><p class="muted">{h(t(messages, "dashboard.customers.description", "Manage customer master data used by Customer Billing."))}</p><a class="button" href="{h(url_with_lang("/customers", lang))}">{h(t(messages, "action.view"))}</a></article>' if can_customer_master_view(user) else ''}
  {vendor_card}
  {system_parameters_card}
</section>
"""
        self.send_html(200, t(messages, "dashboard.title"), body, lang, messages, user)

    def send_coming_soon(self, lang: str, messages: dict[str, str], user: dict[str, Any], path: str) -> None:
        title_key = "nav.departments" if path == "/departments" else "nav.teams"
        body = f"""
<section class="card">
  <h2>{h(t(messages, title_key))}</h2>
  <p class="muted">{h(t(messages, "common.coming_soon"))}</p>
  <p><a class="button secondary" href="{h(url_with_lang('/dashboard', lang))}">{h(t(messages, "nav.dashboard"))}</a></p>
</section>
"""
        self.send_html(200, t(messages, title_key), body, lang, messages, user)

    def send_entities_list(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        entities = sorted(visible_entities_for_user(user), key=lambda item: str(item.get("entity_code", "")).casefold())
        maintain = can_admin_masterdata(user)
        rows = []
        for entity in entities:
            entity_id = str(entity.get("entity_id", ""))
            actions = [f'<a class="button ghost" href="{h(url_with_lang(f"/entities/{entity_id}", lang))}">{h(t(messages, "action.view"))}</a>']
            if maintain:
                actions.append(f'<a class="button secondary" href="{h(url_with_lang(f"/entities/{entity_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
                actions.append(
                    f'<form class="inline-form" method="post" action="{h(url_with_lang(f"/entities/{entity_id}/delete", lang))}" data-confirm-reason="1">'
                    '<input type="hidden" name="masterdata_change_ack" value="1"><input type="hidden" name="change_reason" value="">'
                    f'<button class="danger" type="submit">{h(t(messages, "action.deactivate"))}</button></form>'
                )
            rows.append(
                "<tr>"
                f"<td>{h(entity.get('entity_code'))}</td>"
                f"<td>{h(entity.get('legal_name') or entity.get('entity_name_en'))}</td>"
                f"<td>{h(entity.get('entity_name_en'))}</td>"
                f"<td>{h(entity.get('entity_name_ja'))}</td>"
                f"<td>{h(entity.get('entity_name_zh'))}</td>"
                f"<td>{h(entity.get('country'))}</td>"
                f"<td>{h(entity.get('currency'))}</td>"
                f"<td><span class=\"badge {h(entity.get('status'))}\">{h(render_status(messages, str(entity.get('status', ''))))}</span></td>"
                f"<td>{h(entity.get('updated_at'))}</td>"
                f"<td class=\"actions\">{''.join(actions)}</td>"
                "</tr>"
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="10" class="muted">{h(t(messages, "common.no_records"))}</td></tr>'
        create_action = f'<a class="button" href="{h(url_with_lang("/entities/new", lang))}">{h(t(messages, "action.create_entity"))}</a>' if maintain else f'<span class="badge">{h(t(messages, "common.read_only"))}</span>'
        message_html = render_message_from_query(messages, query)
        body = f"""
<section class="card">
  <div class="topline">
    <div>
      <h2>{h(t(messages, "entity.list_title"))}</h2>
      <p class="muted">{h(t(messages, "dashboard.entities.description"))}</p>
    </div>
    <div>{create_action}</div>
  </div>
  {message_html}
  <table>
    <thead>
      <tr>
        <th>{h(t(messages, "entity.entity_code"))}</th>
        <th>{h(t(messages, "entity.legal_name"))}</th>
        <th>{h(t(messages, "entity.entity_name_en"))}</th>
        <th>{h(t(messages, "entity.entity_name_ja"))}</th>
        <th>{h(t(messages, "entity.entity_name_zh"))}</th>
        <th>{h(t(messages, "entity.country"))}</th>
        <th>{h(t(messages, "entity.currency"))}</th>
        <th>{h(t(messages, "common.status"))}</th>
        <th>{h(t(messages, "common.updated_at"))}</th>
        <th>{h(t(messages, "common.actions"))}</th>
      </tr>
    </thead>
    <tbody>{table_body}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "entity.list_title"), body, lang, messages, user)

    def send_entity_detail(self, lang: str, messages: dict[str, str], user: dict[str, Any], entity_id: str, query: dict[str, list[str]]) -> None:
        entity = find_entity(entity_id)
        if not entity:
            self.send_not_found(lang, messages, user)
            return
        maintain = can_admin_masterdata(user)
        actions = [f'<a class="button secondary" href="{h(url_with_lang("/entities", lang))}">{h(t(messages, "action.back"))}</a>']
        if maintain:
            actions.append(f'<a class="button" href="{h(url_with_lang(f"/entities/{entity_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
            if entity.get("status") == "active":
                actions.append(f'<a class="button ghost" href="{h(url_with_lang("/teams/new", lang, {"entity_id": entity_id}))}">{h(t(messages, "action.create_team_under_entity"))}</a>')
        message_html = render_message_from_query(messages, query)
        fields = [
            ("entity.entity_id", "entity_id"),
            ("entity.entity_code", "entity_code"),
            ("entity.entity_type", "entity_type"),
            ("entity.legal_name", "legal_name"),
            ("entity.entity_name_en", "entity_name_en"),
            ("entity.entity_name_ja", "entity_name_ja"),
            ("entity.entity_name_zh", "entity_name_zh"),
            ("entity.registration_number", "registration_number"),
            ("entity.tax_registration_number", "tax_registration_number"),
            ("entity.country", "country"),
            ("entity.currency", "currency"),
            ("common.status", "status"),
            ("common.created_at", "created_at"),
            ("common.updated_at", "updated_at"),
        ]
        rows = "".join(
            f"<tr><th>{h(t(messages, label_key))}</th><td>{h(render_status(messages, str(entity.get(field, ''))) if field == 'status' else entity.get(field, ''))}</td></tr>"
            for label_key, field in fields
        )
        body = f"""
<section class="card">
  <h2>{h(t(messages, "entity.detail_title"))}</h2>
  {message_html}
  <table><tbody>{rows}</tbody></table>
  <p class="actions">{''.join(actions)}</p>
</section>
{render_masterdata_version_history("entity", entity_id, entity, messages, lang, maintain)}
"""
        self.send_html(200, t(messages, "entity.detail_title"), body, lang, messages, user)

    def send_entity_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], mode: str, entity: Optional[dict[str, Any]], errors: dict[str, str], values: Optional[dict[str, str]] = None) -> None:
        is_edit = mode == "edit"
        source: dict[str, Any] = values or entity or {"status": "active"}
        title_key = "entity.edit_title" if is_edit else "entity.new_title"
        action_path = f"/entities/{entity.get('entity_id')}/edit" if is_edit and entity else "/entities/new"
        status_options = "".join(
            f'<option value="{h(status)}" {"selected" if str(source.get("status", "active")) == status else ""}>{h(render_status(messages, status))}</option>'
            for status in ("active", "inactive")
        )
        field_specs = [
            ("entity_code", "entity.entity_code", "text"),
            ("legal_name", "entity.legal_name", "text"),
            ("entity_name_en", "entity.entity_name_en", "text"),
            ("entity_name_ja", "entity.entity_name_ja", "text"),
            ("entity_name_zh", "entity.entity_name_zh", "text"),
            ("registration_number", "entity.registration_number", "text"),
            ("tax_registration_number", "entity.tax_registration_number", "text"),
            ("country", "entity.country", "text"),
            ("currency", "entity.currency", "text"),
        ]
        inputs = []
        for field, label_key, input_type in field_specs:
            error = errors.get(field, "")
            required_text = h(t(messages, "common.required")) if field in {"entity_code", "legal_name", "entity_name_en", "country", "currency"} else ""
            error_html = f'<div class="field-error">{h(error)}</div>' if error else ""
            inputs.append(
                f'<label for="{h(field)}">{h(t(messages, label_key))} <span class="muted">{required_text}</span></label>'
                f'<input type="{h(input_type)}" id="{h(field)}" name="{h(field)}" value="{h(source.get(field, ""))}">'
                f'{error_html}'
            )
        status_error = errors.get("status", "")
        status_error_html = f'<div class="field-error">{h(status_error)}</div>' if status_error else ""
        body = f"""
<section class="card">
  <h2>{h(t(messages, title_key))}</h2>
  {render_errors(errors)}
  <div class="alert alert-info">
    <strong>{h(t(messages, "entity.legal_entity_notice_title"))}</strong>
    <p class="muted">{h(t(messages, "entity.legal_entity_notice_text"))}</p>
  </div>
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    {''.join(inputs)}
    <label for="status">{h(t(messages, "common.status"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="status" name="status">{status_options}</select>
    {status_error_html}
    {render_change_governance_block(messages, errors, source) if is_edit else ""}
    <p class="actions">
      <button type="submit">{h(t(messages, "action.save"))}</button>
      <a class="button secondary" href="{h(url_with_lang('/entities', lang))}">{h(t(messages, "action.cancel"))}</a>
    </p>
  </form>
</section>
"""
        self.send_html(200 if not errors else 400, t(messages, title_key), body, lang, messages, user)

    def handle_create_entity(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        entities = load_entities()
        values, errors = validate_entity_input(form, entities, messages)
        if errors:
            self.send_entity_form(lang, messages, user, "create", None, errors, values)
            return
        timestamp = now_iso()
        entity = {
            "entity_id": next_id(entities, "entity_id", "ENT-", 4),
            **values,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        entities.append(entity)
        save_entities(entities)
        version = append_masterdata_version("entity", str(entity["entity_id"]), "create", user, entity, "Initial master data creation.", masterdata_record_fields("entity"))
        append_audit("entity", str(entity["entity_id"]), "create", user, None, entity, "Initial master data creation.", masterdata_record_fields("entity"), str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/entities/{entity['entity_id']}", lang, {"message": "entity.created", "record": entity_label(entity, lang), "time": now_iso()}))

    def handle_update_entity(self, lang: str, messages: dict[str, str], user: dict[str, Any], entity_id: str) -> None:
        form = self.parse_form_body()
        entities = load_entities()
        index = next((i for i, entity in enumerate(entities) if str(entity.get("entity_id", "")) == entity_id and entity.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user)
            return
        values, errors = validate_entity_input(form, entities, messages, entity_id)
        if errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**entities[index], **values}
            self.send_entity_form(lang, messages, user, "edit", current, errors, values)
            return
        before_value = dict(entities[index])
        updated = {
            **entities[index],
            **values,
            "entity_id": entities[index].get("entity_id"),
            "created_at": entities[index].get("created_at", now_iso()),
            "updated_at": now_iso(),
        }
        changed = masterdata_changed_fields("entity", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**entities[index], **values}
            self.send_entity_form(lang, messages, user, "edit", current, {**errors, **governance_errors}, values)
            return
        if not changed:
            self.redirect(url_with_lang(f"/entities/{entity_id}", lang, {"message": "governance.no_changes", "record": entity_label(entities[index], lang), "time": now_iso()}))
            return
        ensure_masterdata_version_baseline("entity", entity_id, user, before_value)
        entities[index] = updated
        save_entities(entities)
        version = append_masterdata_version("entity", entity_id, "update", user, updated, change_reason, changed)
        append_audit("entity", entity_id, "update", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/entities/{entity_id}", lang, {"message": "entity.updated", "record": entity_label(updated, lang), "time": now_iso()}))

    def handle_delete_entity(self, lang: str, messages: dict[str, str], user: dict[str, Any], entity_id: str) -> None:
        entities = load_entities()
        index = next((i for i, entity in enumerate(entities) if str(entity.get("entity_id", "")) == entity_id and entity.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user)
            return
        form = self.parse_form_body()
        before_value = dict(entities[index])
        updated = {**entities[index], "status": "inactive", "updated_at": now_iso()}
        changed = masterdata_changed_fields("entity", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            self.send_entity_form(lang, messages, user, "edit", entities[index], governance_errors, {**entities[index], "change_reason": form.get("change_reason", "")})
            return
        ensure_masterdata_version_baseline("entity", entity_id, user, before_value)
        entities[index] = updated
        save_entities(entities)
        version = append_masterdata_version("entity", entity_id, "deactivate", user, updated, change_reason, changed)
        append_audit("entity", entity_id, "deactivate", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/entities", lang, {"message": "entity.deactivated", "record": entity_label(updated, lang), "time": now_iso()}))


    def send_departments_list(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        entities_by_id = {str(entity.get("entity_id", "")): entity for entity in load_entities()}
        departments = sorted(visible_departments_for_user(user), key=lambda item: str(item.get("department_code", "")).casefold())
        maintain = can_maintain(user)
        rows = []
        for department in departments:
            department_id = str(department.get("department_id", ""))
            parent = entities_by_id.get(str(department.get("entity_id", "")))
            actions = [f'<a class="button ghost" href="{h(url_with_lang(f"/departments/{department_id}", lang))}">{h(t(messages, "action.view"))}</a>']
            if maintain:
                actions.append(f'<a class="button secondary" href="{h(url_with_lang(f"/departments/{department_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
                actions.append(
                    f'<form class="inline-form" method="post" action="{h(url_with_lang(f"/departments/{department_id}/delete", lang))}" data-confirm-reason="1">'
                    '<input type="hidden" name="masterdata_change_ack" value="1"><input type="hidden" name="change_reason" value="">'
                    f'<button class="danger" type="submit">{h(t(messages, "action.deactivate"))}</button></form>'
                )
            rows.append(
                "<tr>"
                f"<td>{h(department.get('department_code'))}</td>"
                f"<td>{h(department.get('department_name_en'))}</td>"
                f"<td>{h(department.get('department_name_ja'))}</td>"
                f"<td>{h(department.get('department_name_zh'))}</td>"
                f"<td>{h(entity_label(parent, lang))}</td>"
                f"<td><span class=\"badge {h(department.get('status'))}\">{h(render_status(messages, str(department.get('status', ''))))}</span></td>"
                f"<td>{h(department.get('updated_at'))}</td>"
                f"<td class=\"actions\">{''.join(actions)}</td>"
                "</tr>"
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="8" class="muted">{h(t(messages, "common.no_records"))}</td></tr>'
        create_action = f'<a class="button" href="{h(url_with_lang("/departments/new", lang))}">{h(t(messages, "action.create_department"))}</a>' if maintain else f'<span class="badge">{h(t(messages, "common.read_only"))}</span>'
        message_html = render_message_from_query(messages, query)
        body = f"""
<section class="card">
  <div class="topline">
    <div>
      <h2>{h(t(messages, "department.list_title"))}</h2>
      <p class="muted">{h(t(messages, "dashboard.departments.description"))}</p>
    </div>
    <div>{create_action}</div>
  </div>
  {message_html}
  <table>
    <thead>
      <tr>
        <th>{h(t(messages, "department.department_code"))}</th>
        <th>{h(t(messages, "department.department_name_en"))}</th>
        <th>{h(t(messages, "department.department_name_ja"))}</th>
        <th>{h(t(messages, "department.department_name_zh"))}</th>
        <th>{h(t(messages, "department.parent_entity"))}</th>
        <th>{h(t(messages, "common.status"))}</th>
        <th>{h(t(messages, "common.updated_at"))}</th>
        <th>{h(t(messages, "common.actions"))}</th>
      </tr>
    </thead>
    <tbody>{table_body}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "department.list_title"), body, lang, messages, user)

    def send_department_detail(self, lang: str, messages: dict[str, str], user: dict[str, Any], department_id: str, query: dict[str, list[str]]) -> None:
        department = find_department(department_id)
        if not department:
            self.send_not_found(lang, messages, user, "department.not_found", "/departments")
            return
        parent = find_entity(str(department.get("entity_id", "")), include_deleted=True)
        maintain = can_maintain(user)
        actions = [f'<a class="button secondary" href="{h(url_with_lang("/departments", lang))}">{h(t(messages, "action.back"))}</a>']
        if maintain:
            actions.append(f'<a class="button" href="{h(url_with_lang(f"/departments/{department_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
        message_html = render_message_from_query(messages, query)
        fields = [
            ("department.department_id", "department_id"),
            ("department.department_code", "department_code"),
            ("department.department_name_en", "department_name_en"),
            ("department.department_name_ja", "department_name_ja"),
            ("department.department_name_zh", "department_name_zh"),
            ("department.parent_entity", "entity_id"),
            ("common.status", "status"),
            ("common.created_at", "created_at"),
            ("common.updated_at", "updated_at"),
        ]
        rows = "".join(
            f"<tr><th>{h(t(messages, label_key))}</th><td>{h(entity_label(parent, lang) if field == 'entity_id' else render_status(messages, str(department.get(field, ''))) if field == 'status' else department.get(field, ''))}</td></tr>"
            for label_key, field in fields
        )
        body = f"""
<section class="card">
  <h2>{h(t(messages, "department.detail_title"))}</h2>
  {message_html}
  <table><tbody>{rows}</tbody></table>
  <p class="actions">{''.join(actions)}</p>
</section>
{render_masterdata_version_history("department", department_id, department, messages, lang, maintain)}
"""
        self.send_html(200, t(messages, "department.detail_title"), body, lang, messages, user)

    def send_department_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], mode: str, department: Optional[dict[str, Any]], errors: dict[str, str], values: Optional[dict[str, str]] = None) -> None:
        is_edit = mode == "edit"
        default_entity_id = "" if can_admin_masterdata(user) else current_entity_id(user)
        source: dict[str, Any] = values or department or {"status": "active", "entity_id": default_entity_id}
        title_key = "department.edit_title" if is_edit else "department.new_title"
        action_path = f"/departments/{department.get('department_id')}/edit" if is_edit and department else "/departments/new"
        status_options = "".join(
            f'<option value="{h(status)}" {"selected" if str(source.get("status", "active")) == status else ""}>{h(render_status(messages, status))}</option>'
            for status in ("active", "inactive")
        )
        entity_options = ['<option value="">--</option>']
        for entity in active_entities_for_user(user):
            entity_id = str(entity.get("entity_id", ""))
            selected = "selected" if str(source.get("entity_id", "")) == entity_id else ""
            entity_options.append(f'<option value="{h(entity_id)}" {selected}>{h(entity_label(entity, lang))}</option>')
        department_fields_enabled = bool(str(source.get("entity_id", "")).strip())
        disabled_attr = "" if department_fields_enabled else ' disabled aria-disabled="true"'
        field_specs = [
            ("department_code", "department.department_code", "text"),
            ("department_name_en", "department.department_name_en", "text"),
            ("department_name_ja", "department.department_name_ja", "text"),
            ("department_name_zh", "department.department_name_zh", "text"),
        ]
        inputs = []
        for field, label_key, input_type in field_specs:
            error = errors.get(field, "")
            required_text = h(t(messages, "common.required")) if field in {"department_code", "department_name_en"} else ""
            error_html = f'<div class="field-error">{h(error)}</div>' if error else ""
            inputs.append(
                f'<label for="{h(field)}">{h(t(messages, label_key))} <span class="muted">{required_text}</span></label>'
                f'<input type="{h(input_type)}" id="{h(field)}" name="{h(field)}" value="{h(source.get(field, ""))}" data-requires-entity="1"{disabled_attr}>'
                f'{error_html}'
            )
        entity_error = errors.get("entity_id", "")
        status_error = errors.get("status", "")
        select_entity_first = h(t(messages, "team.select_entity_first", "Select an Entity first."))
        body = f"""
<section class="card">
  <h2>{h(t(messages, title_key))}</h2>
  {render_errors(errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    <label for="entity_id">{h(t(messages, "department.parent_entity"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="entity_id" name="entity_id" required aria-required="true">{''.join(entity_options)}</select>
    {f'<div class="field-error">{h(entity_error)}</div>' if entity_error else ''}
    <p class="muted" id="department_entity_hint">{select_entity_first}</p>
    {''.join(inputs)}
    <label for="status">{h(t(messages, "common.status"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="status" name="status" data-requires-entity="1"{disabled_attr}>{status_options}</select>
    {f'<div class="field-error">{h(status_error)}</div>' if status_error else ''}
    {render_change_governance_block(messages, errors, source) if is_edit else ""}
    <p class="actions">
      <button type="submit">{h(t(messages, "action.save"))}</button>
      <a class="button secondary" href="{h(url_with_lang('/departments', lang))}">{h(t(messages, "action.cancel"))}</a>
    </p>
  </form>
</section>
<script>
(() => {{
  const entitySelect = document.getElementById('entity_id');
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
        self.send_html(200 if not errors else 400, t(messages, title_key), body, lang, messages, user)

    def handle_create_department(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        if not can_admin_masterdata(user):
            form["entity_id"] = current_entity_id(user)
        departments = load_departments()
        values, errors = validate_department_input(form, departments, messages)
        if not can_admin_masterdata(user) and values.get("entity_id") != current_entity_id(user):
            errors["entity_id"] = t(messages, "api.forbidden")
        if errors:
            self.send_department_form(lang, messages, user, "create", None, errors, values)
            return
        timestamp = now_iso()
        department = {
            "department_id": next_id(departments, "department_id", "DEP-", 4),
            **values,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        departments.append(department)
        save_departments(departments)
        version = append_masterdata_version("department", str(department["department_id"]), "create", user, department, "Initial master data creation.", masterdata_record_fields("department"))
        append_audit("department", str(department["department_id"]), "create", user, None, department, "Initial master data creation.", masterdata_record_fields("department"), str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/departments/{department['department_id']}", lang, {"message": "department.created", "record": department_label(department, lang), "time": now_iso()}))

    def handle_update_department(self, lang: str, messages: dict[str, str], user: dict[str, Any], department_id: str) -> None:
        form = self.parse_form_body()
        departments = load_departments()
        index = next((i for i, department in enumerate(departments) if str(department.get("department_id", "")) == department_id and department.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "department.not_found", "/departments")
            return
        if not department_accessible_to_user(departments[index], user):
            self.send_not_found(lang, messages, user, "department.not_found", "/departments")
            return
        if not can_admin_masterdata(user):
            form["entity_id"] = str(departments[index].get("entity_id", current_entity_id(user)))
        values, errors = validate_department_input(form, departments, messages, department_id)
        if not can_admin_masterdata(user) and values.get("entity_id") != current_entity_id(user):
            errors["entity_id"] = t(messages, "api.forbidden")
        if errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**departments[index], **values}
            self.send_department_form(lang, messages, user, "edit", current, errors, values)
            return
        before_value = dict(departments[index])
        updated = {
            **departments[index],
            **values,
            "department_id": departments[index].get("department_id"),
            "created_at": departments[index].get("created_at", now_iso()),
            "updated_at": now_iso(),
        }
        changed = masterdata_changed_fields("department", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**departments[index], **values}
            self.send_department_form(lang, messages, user, "edit", current, {**errors, **governance_errors}, values)
            return
        if not changed:
            self.redirect(url_with_lang(f"/departments/{department_id}", lang, {"message": "governance.no_changes", "record": department_label(departments[index], lang), "time": now_iso()}))
            return
        ensure_masterdata_version_baseline("department", department_id, user, before_value)
        departments[index] = updated
        save_departments(departments)
        version = append_masterdata_version("department", department_id, "update", user, updated, change_reason, changed)
        append_audit("department", department_id, "update", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/departments/{department_id}", lang, {"message": "department.updated", "record": department_label(updated, lang), "time": now_iso()}))

    def handle_delete_department(self, lang: str, messages: dict[str, str], user: dict[str, Any], department_id: str) -> None:
        departments = load_departments()
        index = next((i for i, department in enumerate(departments) if str(department.get("department_id", "")) == department_id and department.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "department.not_found", "/departments")
            return
        if not department_accessible_to_user(departments[index], user):
            self.send_not_found(lang, messages, user, "department.not_found", "/departments")
            return
        form = self.parse_form_body()
        before_value = dict(departments[index])
        updated = {**departments[index], "status": "inactive", "updated_at": now_iso()}
        changed = masterdata_changed_fields("department", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            self.send_department_form(lang, messages, user, "edit", departments[index], governance_errors, {**departments[index], "change_reason": form.get("change_reason", "")})
            return
        ensure_masterdata_version_baseline("department", department_id, user, before_value)
        departments[index] = updated
        save_departments(departments)
        version = append_masterdata_version("department", department_id, "deactivate", user, updated, change_reason, changed)
        append_audit("department", department_id, "deactivate", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/departments", lang, {"message": "department.deactivated", "record": department_label(updated, lang), "time": now_iso()}))

    def send_teams_list(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        departments_by_id = {str(department.get("department_id", "")): department for department in load_departments()}
        entities_by_id = {str(entity.get("entity_id", "")): entity for entity in load_entities()}
        entity_filter = query.get("entity_id", [""])[0]
        teams = visible_teams_for_user(user)
        if entity_filter:
            entity = find_entity(entity_filter)
            if entity and entity_accessible_to_user(entity, user):
                teams = [team for team in teams if team_parent_entity_id(team) == entity_filter]
        teams = sorted(
            teams,
            key=lambda item: (
                entity_label(entities_by_id.get(team_parent_entity_id(item)), lang).casefold(),
                department_label(departments_by_id.get(str(item.get("department_id", ""))), lang).casefold(),
                str(item.get("team_code", "")).casefold(),
            ),
        )
        maintain = can_maintain(user)
        rows = []
        for team in teams:
            team_id = str(team.get("team_id", ""))
            parent = departments_by_id.get(str(team.get("department_id", "")))
            parent_entity = entities_by_id.get(str(parent.get("entity_id", ""))) if parent else None
            actions = [f'<a class="button ghost" href="{h(url_with_lang(f"/teams/{team_id}", lang))}">{h(t(messages, "action.view"))}</a>']
            if maintain:
                actions.append(f'<a class="button secondary" href="{h(url_with_lang(f"/teams/{team_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
                actions.append(
                    f'<form class="inline-form" method="post" action="{h(url_with_lang(f"/teams/{team_id}/delete", lang))}" data-confirm-reason="1">'
                    '<input type="hidden" name="masterdata_change_ack" value="1"><input type="hidden" name="change_reason" value="">'
                    f'<button class="danger" type="submit">{h(t(messages, "action.deactivate"))}</button></form>'
                )
            rows.append(
                "<tr>"
                f"<td>{h(team.get('team_code'))}</td>"
                f"<td>{h(team.get('team_name_en'))}</td>"
                f"<td>{h(team.get('team_name_ja'))}</td>"
                f"<td>{h(team.get('team_name_zh'))}</td>"
                f"<td>{h(entity_label(parent_entity, lang))}</td>"
                f"<td>{h(department_label(parent, lang))}</td>"
                f"<td><span class=\"badge {h(team.get('status'))}\">{h(render_status(messages, str(team.get('status', ''))))}</span></td>"
                f"<td>{h(team.get('updated_at'))}</td>"
                f"<td class=\"actions\">{''.join(actions)}</td>"
                "</tr>"
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="10" class="muted">{h(t(messages, "common.no_records"))}</td></tr>'
        create_action = f'<a class="button" href="{h(url_with_lang("/teams/new", lang))}">{h(t(messages, "action.create_team"))}</a>' if maintain else f'<span class="badge">{h(t(messages, "common.read_only"))}</span>'
        message_html = render_message_from_query(messages, query)
        body = f"""
<section class="card">
  <div class="topline">
    <div>
      <h2>{h(t(messages, "team.list_title"))}</h2>
      <p class="muted">{h(t(messages, "dashboard.teams.description"))}</p>
    </div>
    <div>{create_action}</div>
  </div>
  {message_html}
  <table>
    <thead>
      <tr>
        <th>{h(t(messages, "team.team_code"))}</th>
        <th>{h(t(messages, "team.team_name_en"))}</th>
        <th>{h(t(messages, "team.team_name_ja"))}</th>
        <th>{h(t(messages, "team.team_name_zh"))}</th>
        <th>{h(t(messages, "team.parent_entity"))}</th>
        <th>{h(t(messages, "team.parent_department"))}</th>
        <th>{h(t(messages, "common.status"))}</th>
        <th>{h(t(messages, "common.updated_at"))}</th>
        <th>{h(t(messages, "common.actions"))}</th>
      </tr>
    </thead>
    <tbody>{table_body}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "team.list_title"), body, lang, messages, user)

    def send_team_detail(self, lang: str, messages: dict[str, str], user: dict[str, Any], team_id: str, query: dict[str, list[str]]) -> None:
        team = find_team(team_id)
        if not team:
            self.send_not_found(lang, messages, user, "team.not_found", "/teams")
            return
        parent = find_department(str(team.get("department_id", "")), include_deleted=True)
        parent_entity = find_entity(str(parent.get("entity_id", "")), include_deleted=True) if parent else None
        maintain = can_maintain(user)
        actions = [f'<a class="button secondary" href="{h(url_with_lang("/teams", lang))}">{h(t(messages, "action.back"))}</a>']
        if maintain:
            actions.append(f'<a class="button" href="{h(url_with_lang(f"/teams/{team_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
        message_html = render_message_from_query(messages, query)
        fields = [
            ("team.team_id", "team_id"),
            ("team.team_code", "team_code"),
            ("team.team_name_en", "team_name_en"),
            ("team.team_name_ja", "team_name_ja"),
            ("team.team_name_zh", "team_name_zh"),
            ("team.parent_entity", "entity_id"),
            ("team.parent_department", "department_id"),
            ("common.status", "status"),
            ("common.created_at", "created_at"),
            ("common.updated_at", "updated_at"),
        ]
        rows = "".join(
            f"<tr><th>{h(t(messages, label_key))}</th><td>{h(entity_label(parent_entity, lang) if field == 'entity_id' else department_label(parent, lang) if field == 'department_id' else render_status(messages, str(team.get(field, ''))) if field == 'status' else team.get(field, ''))}</td></tr>"
            for label_key, field in fields
        )
        body = f"""
<section class="card">
  <h2>{h(t(messages, "team.detail_title"))}</h2>
  {message_html}
  <table><tbody>{rows}</tbody></table>
  <p class="actions">{''.join(actions)}</p>
</section>
{render_masterdata_version_history("team", team_id, team, messages, lang, maintain)}
"""
        self.send_html(200, t(messages, "team.detail_title"), body, lang, messages, user)

    def send_team_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], mode: str, team: Optional[dict[str, Any]], errors: dict[str, str], values: Optional[dict[str, str]] = None, query: Optional[dict[str, list[str]]] = None) -> None:
        is_edit = mode == "edit"
        query = query or {}
        query_entity_id = query.get("entity_id", [""])[0]
        query_entity = find_entity(query_entity_id) if query_entity_id else None
        query_entity_allowed = bool(query_entity and query_entity.get("status") == "active" and entity_accessible_to_user(query_entity, user))
        team_entity_id = team_parent_entity_id(team) if team else ""
        source: dict[str, Any] = values or team or {"status": "active"}
        selected_entity_id = str(source.get("entity_id", "")).strip()
        if not selected_entity_id and team_entity_id:
            selected_entity_id = team_entity_id
        if not selected_entity_id and query_entity_allowed:
            selected_entity_id = query_entity_id
        if not selected_entity_id and not can_admin_masterdata(user):
            selected_entity_id = current_entity_id(user)
        active_entities = active_entities_for_user(user)
        if not selected_entity_id and len(active_entities) == 1:
            selected_entity_id = str(active_entities[0].get("entity_id", ""))
        active_departments = active_departments_for_entity_for_user(user, selected_entity_id) if selected_entity_id else []
        if not source.get("department_id") and len(active_departments) == 1:
            source = {**source, "department_id": str(active_departments[0].get("department_id", ""))}
        source = {**source, "entity_id": selected_entity_id}
        lock_entity = (not can_admin_masterdata(user)) or query_entity_allowed or str(source.get("_entity_locked", "")) == "1"
        title_key = "team.edit_title" if is_edit else "team.new_title"
        action_path = f"/teams/{team.get('team_id')}/edit" if is_edit and team else "/teams/new"
        action_params = {"entity_id": selected_entity_id} if lock_entity and selected_entity_id else None
        status_options = "".join(
            f'<option value="{h(status)}" {"selected" if str(source.get("status", "active")) == status else ""}>{h(render_status(messages, status))}</option>'
            for status in ("active", "inactive")
        )
        entity_options = ['<option value="">--</option>']
        for entity in active_entities:
            entity_id = str(entity.get("entity_id", ""))
            selected = "selected" if selected_entity_id == entity_id else ""
            entity_options.append(f'<option value="{h(entity_id)}" {selected}>{h(entity_label(entity, lang))}</option>')
        if lock_entity:
            entity_control = (
                f'<select id="entity_id_display" disabled>{"".join(entity_options)}</select>'
                f'<input type="hidden" name="entity_id" value="{h(selected_entity_id)}">'
                f'<input type="hidden" name="_entity_locked" value="1">'
            )
        else:
            entity_control = f'<select id="entity_id" name="entity_id">{"".join(entity_options)}</select>'
        department_options = ['<option value="">--</option>']
        for department in active_departments:
            department_id = str(department.get("department_id", ""))
            selected = "selected" if str(source.get("department_id", "")) == department_id else ""
            department_options.append(f'<option value="{h(department_id)}" {selected}>{h(department_label(department, lang))}</option>')
        field_specs = [
            ("team_code", "team.team_code", "text"),
            ("team_name_en", "team.team_name_en", "text"),
            ("team_name_ja", "team.team_name_ja", "text"),
            ("team_name_zh", "team.team_name_zh", "text"),
        ]
        inputs = []
        for field, label_key, input_type in field_specs:
            error = errors.get(field, "")
            required_text = h(t(messages, "common.required")) if field in {"team_code", "team_name_en"} else ""
            error_html = f'<div class="field-error">{h(error)}</div>' if error else ""
            inputs.append(
                f'<label for="{h(field)}">{h(t(messages, label_key))} <span class="muted">{required_text}</span></label>'
                f'<input type="{h(input_type)}" id="{h(field)}" name="{h(field)}" value="{h(source.get(field, ""))}">'
                f'{error_html}'
            )
        entity_error = errors.get("entity_id", "")
        department_error = errors.get("department_id", "")
        status_error = errors.get("status", "")
        select_entity_first = h(t(messages, "team.select_entity_first"))
        body = f"""
<section class="card">
  <h2>{h(t(messages, title_key))}</h2>
  {render_errors(errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang, action_params))}">
    <label for="entity_id">{h(t(messages, "team.parent_entity"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    {entity_control}
    {f'<div class="field-error">{h(entity_error)}</div>' if entity_error else ''}
    <label for="department_id">{h(t(messages, "team.parent_department"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="department_id" name="department_id" data-selected="{h(source.get('department_id', ''))}">{''.join(department_options)}</select>
    {f'<div class="field-error">{h(department_error)}</div>' if department_error else ''}
    {''.join(inputs)}
    <label for="status">{h(t(messages, "common.status"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="status" name="status">{status_options}</select>
    {f'<div class="field-error">{h(status_error)}</div>' if status_error else ''}
    {render_change_governance_block(messages, errors, source) if is_edit else ""}
    <p class="actions">
      <button type="submit">{h(t(messages, "action.save"))}</button>
      <a class="button secondary" href="{h(url_with_lang('/teams', lang))}">{h(t(messages, "action.cancel"))}</a>
    </p>
  </form>
</section>
<script>
(() => {{
  const entitySelect = document.getElementById('entity_id');
  const departmentSelect = document.getElementById('department_id');
  if (!entitySelect || !departmentSelect) return;
  const lang = {json.dumps(lang)};
  const selectEntityFirst = {json.dumps(select_entity_first)};
  function departmentName(department) {{
    const localized = (department[`department_name_${{lang}}`] || '').trim();
    const english = (department.department_name_en || '').trim();
    const code = (department.department_code || '').trim();
    const name = localized || english || code;
    return code && name && name !== code ? `${{code}} - ${{name}}` : (code || name);
  }}
  function setBlank(label) {{
    departmentSelect.innerHTML = '';
    const option = document.createElement('option');
    option.value = '';
    option.textContent = label || '--';
    departmentSelect.appendChild(option);
  }}
  entitySelect.addEventListener('change', async () => {{
    const entityId = entitySelect.value;
    departmentSelect.dataset.selected = '';
    if (!entityId) {{
      setBlank(selectEntityFirst);
      return;
    }}
    const response = await fetch(`/api/departments?entity_id=${{encodeURIComponent(entityId)}}&lang=${{encodeURIComponent(lang)}}`);
    if (!response.ok) {{
      setBlank('--');
      return;
    }}
    const departments = await response.json();
    setBlank('--');
    for (const department of departments) {{
      const option = document.createElement('option');
      option.value = department.department_id || '';
      option.textContent = departmentName(department);
      departmentSelect.appendChild(option);
    }}
  }});
}})();
</script>
"""
        self.send_html(200 if not errors else 400, t(messages, title_key), body, lang, messages, user)

    def handle_create_team(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        if not can_admin_masterdata(user):
            form["entity_id"] = current_entity_id(user)
        teams = load_teams()
        values, errors = validate_team_input(form, teams, messages)
        if form.get("_entity_locked") == "1":
            values["_entity_locked"] = "1"
        parent_entity = find_entity(values.get("entity_id", "")) if values.get("entity_id") else None
        if parent_entity and not entity_accessible_to_user(parent_entity, user):
            errors["entity_id"] = t(messages, "api.forbidden")
        parent_department = find_department(values.get("department_id", "")) if values.get("department_id") else None
        if parent_department and not department_accessible_to_user(parent_department, user):
            errors["department_id"] = t(messages, "api.forbidden")
        if errors:
            self.send_team_form(lang, messages, user, "create", None, errors, values)
            return
        persisted_values = team_persisted_values(values)
        timestamp = now_iso()
        team = {
            "team_id": next_id(teams, "team_id", "TEAM-", 4),
            **persisted_values,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        teams.append(team)
        save_teams(teams)
        version = append_masterdata_version("team", str(team["team_id"]), "create", user, team, "Initial master data creation.", masterdata_record_fields("team"))
        append_audit("team", str(team["team_id"]), "create", user, None, team, "Initial master data creation.", masterdata_record_fields("team"), str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/teams/{team['team_id']}", lang, {"message": "team.created", "record": team_label(team, lang), "time": now_iso()}))

    def handle_update_team(self, lang: str, messages: dict[str, str], user: dict[str, Any], team_id: str) -> None:
        form = self.parse_form_body()
        teams = load_teams()
        index = next((i for i, team in enumerate(teams) if str(team.get("team_id", "")) == team_id and team.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "team.not_found", "/teams")
            return
        if not team_accessible_to_user(teams[index], user):
            self.send_not_found(lang, messages, user, "team.not_found", "/teams")
            return
        if not can_admin_masterdata(user):
            form["entity_id"] = current_entity_id(user)
        values, errors = validate_team_input(form, teams, messages, team_id)
        if form.get("_entity_locked") == "1":
            values["_entity_locked"] = "1"
        parent_entity = find_entity(values.get("entity_id", "")) if values.get("entity_id") else None
        if parent_entity and not entity_accessible_to_user(parent_entity, user):
            errors["entity_id"] = t(messages, "api.forbidden")
        parent_department = find_department(values.get("department_id", "")) if values.get("department_id") else None
        if parent_department and not department_accessible_to_user(parent_department, user):
            errors["department_id"] = t(messages, "api.forbidden")
        if errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**teams[index], **values}
            self.send_team_form(lang, messages, user, "edit", current, errors, values)
            return
        persisted_values = team_persisted_values(values)
        before_value = dict(teams[index])
        updated = {
            **teams[index],
            **persisted_values,
            "team_id": teams[index].get("team_id"),
            "created_at": teams[index].get("created_at", now_iso()),
            "updated_at": now_iso(),
        }
        changed = masterdata_changed_fields("team", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**teams[index], **values}
            self.send_team_form(lang, messages, user, "edit", current, {**errors, **governance_errors}, values)
            return
        if not changed:
            self.redirect(url_with_lang(f"/teams/{team_id}", lang, {"message": "governance.no_changes", "record": team_label(teams[index], lang), "time": now_iso()}))
            return
        ensure_masterdata_version_baseline("team", team_id, user, before_value)
        teams[index] = updated
        save_teams(teams)
        version = append_masterdata_version("team", team_id, "update", user, updated, change_reason, changed)
        append_audit("team", team_id, "update", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/teams/{team_id}", lang, {"message": "team.updated", "record": team_label(updated, lang), "time": now_iso()}))

    def handle_delete_team(self, lang: str, messages: dict[str, str], user: dict[str, Any], team_id: str) -> None:
        teams = load_teams()
        index = next((i for i, team in enumerate(teams) if str(team.get("team_id", "")) == team_id and team.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "team.not_found", "/teams")
            return
        if not team_accessible_to_user(teams[index], user):
            self.send_not_found(lang, messages, user, "team.not_found", "/teams")
            return
        form = self.parse_form_body()
        before_value = dict(teams[index])
        updated = {**teams[index], "status": "inactive", "updated_at": now_iso()}
        changed = masterdata_changed_fields("team", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            self.send_team_form(lang, messages, user, "edit", teams[index], governance_errors, {**teams[index], "change_reason": form.get("change_reason", "")})
            return
        ensure_masterdata_version_baseline("team", team_id, user, before_value)
        teams[index] = updated
        save_teams(teams)
        version = append_masterdata_version("team", team_id, "deactivate", user, updated, change_reason, changed)
        append_audit("team", team_id, "deactivate", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/teams", lang, {"message": "team.deactivated", "record": team_label(updated, lang), "time": now_iso()}))



    def send_vendors_list(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        include_inactive = query.get("include_inactive", [""])[0] == "1" and can_maintain(user)
        vendors = visible_vendors_for_user(user) if include_inactive else active_vendors_for_user(user)
        vendors = sorted(vendors, key=lambda item: str(item.get("vendor_code", "")).casefold())
        maintain = can_maintain(user)
        rows = []
        for vendor in vendors:
            vendor_id = str(vendor.get("vendor_id", ""))
            actions = [f'<a class="button ghost" href="{h(url_with_lang(f"/vendors/{vendor_id}", lang))}">{h(t(messages, "action.view"))}</a>']
            if maintain:
                actions.append(f'<a class="button secondary" href="{h(url_with_lang(f"/vendors/{vendor_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
                actions.append(
                    f'<form class="inline-form" method="post" action="{h(url_with_lang(f"/vendors/{vendor_id}/delete", lang))}" data-confirm-reason="1">'
                    '<input type="hidden" name="masterdata_change_ack" value="1"><input type="hidden" name="change_reason" value="">'
                    f'<button class="danger" type="submit">{h(t(messages, "action.deactivate"))}</button></form>'
                )
            rows.append(
                "<tr>"
                f"<td>{h(vendor.get('vendor_code'))}</td>"
                f"<td>{h(localized_master_name(vendor, 'vendor_name', 'vendor_code', lang))}</td>"
                f"<td>{h(vendor.get('vendor_type'))}</td>"
                f"<td>{h(t(messages, 'vendor.supplier_record_mode.' + str(vendor.get('supplier_record_mode', 'standard_vendor') or 'standard_vendor'), str(vendor.get('supplier_record_mode', 'standard_vendor') or 'standard_vendor')))}</td>"
                f"<td>{h(entity_label(find_entity(str(vendor.get('entity_id', '')), include_deleted=True), lang))}</td>"
                f"<td>{h(vendor.get('qualified_invoice_number'))}</td>"
                f"<td>{h(vendor.get('payment_terms'))}</td>"
                f"<td><span class=\"badge {h(vendor.get('status'))}\">{h(render_status(messages, str(vendor.get('status', ''))))}</span></td>"
                f"<td class=\"actions\">{''.join(actions)}</td>"
                "</tr>"
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="9" class="muted">{h(t(messages, "common.no_records"))}</td></tr>'
        create_action = f'<a class="button" href="{h(url_with_lang("/vendors/new", lang))}">{h(t(messages, "action.create_vendor", "Create Vendor"))}</a>' if maintain else f'<span class="badge">{h(t(messages, "common.read_only"))}</span>'
        body = f"""
<section class="card">
  <div class="topline"><div><h2>{h(t(messages, "vendor.list_title", "Vendor Master"))}</h2><p class="muted">{h(t(messages, "dashboard.vendors.description", "Manage supplier and vendor master data used by Vendor Payments."))}</p></div><div>{create_action}</div></div>
  {render_message_from_query(messages, query)}
  <table>
    <thead><tr><th>{h(t(messages, "vendor.vendor_code", "Vendor Code"))}</th><th>{h(t(messages, "vendor.vendor_name", "Vendor Name"))}</th><th>{h(t(messages, "vendor.vendor_type", "Vendor Type"))}</th><th>{h(t(messages, "vendor.supplier_record_mode", "Supplier Mode"))}</th><th>{h(t(messages, "vendor.entity", "Entity"))}</th><th>{h(t(messages, "vendor.qualified_invoice_number", "Qualified Invoice No."))}</th><th>{h(t(messages, "vendor.payment_terms", "Payment Terms"))}</th><th>{h(t(messages, "common.status"))}</th><th>{h(t(messages, "common.actions"))}</th></tr></thead>
    <tbody>{table_body}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "vendor.list_title", "Vendor Master"), body, lang, messages, user)

    def send_vendor_detail(self, lang: str, messages: dict[str, str], user: dict[str, Any], vendor_id: str, query: dict[str, list[str]]) -> None:
        vendor = find_vendor(vendor_id)
        if not vendor or not vendor_accessible_to_user(vendor, user):
            self.send_not_found(lang, messages, user, "vendor.not_found", "/vendors")
            return
        maintain = can_maintain(user)
        actions = [f'<a class="button secondary" href="{h(url_with_lang("/vendors", lang))}">{h(t(messages, "action.back"))}</a>']
        if maintain:
            actions.append(f'<a class="button" href="{h(url_with_lang(f"/vendors/{vendor_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
        fields = [
            ("vendor.vendor_id", "vendor_id"), ("vendor.vendor_code", "vendor_code"), ("vendor.vendor_name_en", "vendor_name_en"), ("vendor.vendor_name_ja", "vendor_name_ja"), ("vendor.vendor_name_zh", "vendor_name_zh"), ("vendor.vendor_name_kana", "vendor_name_kana"), ("vendor.vendor_type", "vendor_type"), ("vendor.supplier_record_mode", "supplier_record_mode"), ("vendor.entity", "entity_id"), ("vendor.country", "country"), ("vendor.postal_code", "postal_code"), ("vendor.address", "address"), ("vendor.qualified_invoice_number", "qualified_invoice_number"), ("vendor.is_qualified_invoice_vendor", "is_qualified_invoice_vendor"), ("vendor.contact_person", "contact_person"), ("vendor.email", "email"), ("vendor.phone", "phone"), ("vendor.bank_name", "bank_name"), ("vendor.bank_branch", "bank_branch"), ("vendor.bank_account_type", "bank_account_type"), ("vendor.bank_account_number_masked", "bank_account_number_masked"), ("vendor.bank_account_holder", "bank_account_holder"), ("vendor.payment_terms", "payment_terms"), ("vendor.default_currency", "default_currency"), ("vendor.notes", "notes"), ("common.status", "status"), ("common.created_at", "created_at"), ("common.updated_at", "updated_at"),
        ]
        rows = ""
        for label_key, field in fields:
            if field == "entity_id":
                display_value = entity_label(find_entity(str(vendor.get(field, "")), include_deleted=True), lang)
            elif field == "status":
                display_value = render_status(messages, str(vendor.get(field, "")))
            elif field == "supplier_record_mode":
                mode_value = str(vendor.get(field, "standard_vendor") or "standard_vendor")
                display_value = t(messages, f"vendor.supplier_record_mode.{mode_value}", mode_value)
            else:
                display_value = vendor.get(field, "")
            rows += f"<tr><th>{h(t(messages, label_key, label_key))}</th><td>{h(display_value)}</td></tr>"
        body = f"""
<section class="card">
  <h2>{h(t(messages, "vendor.detail_title", "Vendor Detail"))}</h2>
  {render_message_from_query(messages, query)}
  <table><tbody>{rows}</tbody></table>
  <p class="actions">{''.join(actions)}</p>
</section>
{render_masterdata_version_history("vendor", vendor_id, vendor, messages, lang, maintain)}
"""
        self.send_html(200, t(messages, "vendor.detail_title", "Vendor Detail"), body, lang, messages, user)

    def send_vendor_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], mode: str, vendor: Optional[dict[str, Any]], errors: dict[str, str], values: Optional[dict[str, Any]] = None) -> None:
        is_edit = mode == "edit"
        source: dict[str, Any] = values or vendor or {"status": "active", "country": "Japan", "default_currency": "JPY", "vendor_type": "other", "supplier_record_mode": "standard_vendor", "is_qualified_invoice_vendor": "unknown", "entity_id": current_entity_id(user)}
        title_key = "vendor.edit_title" if is_edit else "vendor.new_title"
        action_path = f"/vendors/{vendor.get('vendor_id')}/edit" if is_edit and vendor else "/vendors/new"
        status_options = "".join(f'<option value="{h(status)}" {"selected" if str(source.get("status", "active")) == status else ""}>{h(render_status(messages, status))}</option>' for status in ("active", "inactive"))
        vendor_type_options = "".join(f'<option value="{h(item)}" {"selected" if str(source.get("vendor_type", "other")) == item else ""}>{h(t(messages, "vendor.type." + item, item))}</option>' for item in ("recruitment_media", "outsourcing_partner", "saas_system", "professional_service", "office_admin", "other"))
        supplier_record_mode_options = "".join(f'<option value="{h(item)}" {"selected" if str(source.get("supplier_record_mode", "standard_vendor")) == item else ""}>{h(t(messages, "vendor.supplier_record_mode." + item, item))}</option>' for item in ("standard_vendor", "one_time_vendor"))
        invoice_vendor_options = "".join(f'<option value="{h(item)}" {"selected" if str(source.get("is_qualified_invoice_vendor", "unknown")) == item else ""}>{h(item)}</option>' for item in ("unknown", "yes", "no"))
        entity_options = "".join(f'<option value="{h(entity.get("entity_id"))}" {"selected" if str(source.get("entity_id", "")) == str(entity.get("entity_id", "")) else ""}>{h(entity_label(entity, lang))}</option>' for entity in active_entities_for_user(user))
        field_specs = [
            ("vendor_code", "vendor.vendor_code", "text", True), ("vendor_name_en", "vendor.vendor_name_en", "text", True), ("vendor_name_ja", "vendor.vendor_name_ja", "text", False), ("vendor_name_zh", "vendor.vendor_name_zh", "text", False), ("vendor_name_kana", "vendor.vendor_name_kana", "text", False), ("country", "vendor.country", "text", True), ("postal_code", "vendor.postal_code", "text", False), ("qualified_invoice_number", "vendor.qualified_invoice_number", "text", False), ("contact_person", "vendor.contact_person", "text", False), ("email", "vendor.email", "email", False), ("phone", "vendor.phone", "text", False), ("bank_name", "vendor.bank_name", "text", False), ("bank_branch", "vendor.bank_branch", "text", False), ("bank_account_type", "vendor.bank_account_type", "text", False), ("bank_account_number_masked", "vendor.bank_account_number_masked", "text", False), ("bank_account_holder", "vendor.bank_account_holder", "text", False), ("payment_terms", "vendor.payment_terms", "text", False), ("default_currency", "vendor.default_currency", "text", True),
        ]
        inputs = []
        for field, label_key, input_type, required in field_specs:
            error = errors.get(field, "")
            required_text = h(t(messages, "common.required")) if required else ""
            error_html = f'<div class="field-error">{h(error)}</div>' if error else ""
            inputs.append(
                f'<label for="{h(field)}">{h(t(messages, label_key, field))} <span class="muted">{required_text}</span></label>'
                f'<input type="{h(input_type)}" id="{h(field)}" name="{h(field)}" value="{h(source.get(field, ""))}">'
                f'{error_html}'
            )
        vendor_ocr_error = errors.get("vendor_ocr_file", "")
        vendor_ocr_error_html = f'<div class="field-error">{h(vendor_ocr_error)}</div>' if vendor_ocr_error else ''
        vendor_ocr_form = f"""
<section class=\"card\">
  <h3>{h(t(messages, 'vendor.ocr_title', 'OCR Draft from Supplier Invoice'))}</h3>
  <p class=\"muted\">{h(t(messages, 'vendor.ocr_help', 'Upload a supplier invoice or request file to prefill a Vendor Master draft. Review before saving.'))}</p>
  <form method=\"post\" enctype=\"multipart/form-data\" action=\"{h(url_with_lang('/vendors/ocr', lang))}\">
    <input type=\"hidden\" name=\"mode\" value=\"{h(mode)}\">
    <input type=\"hidden\" name=\"vendor_id\" value=\"{h(vendor.get('vendor_id', '') if vendor else '')}\">
    <label for=\"vendor_ocr_file\">{h(t(messages, 'vendor.ocr_file', 'Supplier invoice/request file'))}</label>
    <input type=\"file\" id=\"vendor_ocr_file\" name=\"vendor_ocr_file\" accept=\".pdf,.jpg,.jpeg,.png,.webp\">
    {vendor_ocr_error_html}
    <p class=\"actions\"><button type=\"submit\">{h(t(messages, 'vendor.ocr_extract', 'Extract OCR Draft'))}</button></p>
  </form>
</section>
"""
        body = f"""
{vendor_ocr_form}
<section class="card">
  <h2>{h(t(messages, title_key, "Vendor"))}</h2>
  {render_errors(errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    <label for="entity_id">{h(t(messages, "vendor.entity", "Entity"))} <span class="muted">{h(t(messages, "common.required"))}</span></label><select id="entity_id" name="entity_id">{entity_options}</select>{f'<div class="field-error">{h(errors.get("entity_id", ""))}</div>' if errors.get("entity_id") else ''}
    <label for="vendor_type">{h(t(messages, "vendor.vendor_type", "Vendor Type"))} <span class="muted">{h(t(messages, "common.required"))}</span></label><select id="vendor_type" name="vendor_type">{vendor_type_options}</select>
    <label for="supplier_record_mode">{h(t(messages, "vendor.supplier_record_mode", "Supplier Mode"))}</label><select id="supplier_record_mode" name="supplier_record_mode">{supplier_record_mode_options}</select>{f'<div class="field-error">{h(errors.get("supplier_record_mode", ""))}</div>' if errors.get("supplier_record_mode") else ''}<p class="muted">{h(t(messages, "vendor.one_time_help", "One-time suppliers use a vendor code ending in 9999. Downstream payment flows should collect manual payee/invoice descriptions when this record is selected."))}</p>
    {''.join(inputs)}
    <label for="is_qualified_invoice_vendor">{h(t(messages, "vendor.is_qualified_invoice_vendor", "Qualified Invoice Vendor"))}</label><select id="is_qualified_invoice_vendor" name="is_qualified_invoice_vendor">{invoice_vendor_options}</select>
    <label for="address">{h(t(messages, "vendor.address", "Address"))}</label><textarea id="address" name="address">{h(source.get('address', ''))}</textarea>
    <label for="notes">{h(t(messages, "vendor.notes", "Notes"))}</label><textarea id="notes" name="notes">{h(source.get('notes', ''))}</textarea>
    <label for="status">{h(t(messages, "common.status"))} <span class="muted">{h(t(messages, "common.required"))}</span></label><select id="status" name="status">{status_options}</select>{f'<div class="field-error">{h(errors.get("status", ""))}</div>' if errors.get("status") else ''}
    {render_change_governance_block(messages, errors, source) if is_edit else ""}
    <p class="actions"><button type="submit">{h(t(messages, "action.save"))}</button><a class="button secondary" href="{h(url_with_lang('/vendors', lang))}">{h(t(messages, "action.cancel"))}</a></p>
  </form>
</section>
"""
        self.send_html(200 if not errors else 400, t(messages, title_key, "Vendor"), body, lang, messages, user)

    def handle_vendor_ocr(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        fields, files = parse_multipart_form(self)
        mode = fields.get("mode", "create") or "create"
        vendor_id = fields.get("vendor_id", "").strip()
        vendor = find_vendor(vendor_id) if vendor_id else None
        upload = files.get("vendor_ocr_file")
        errors: dict[str, str] = {}
        try:
            if not upload:
                raise ValueError("Please choose a supplier invoice/request file before OCR extraction.")
            saved_upload = save_vendor_ocr_upload(upload)
            text, notes = run_vendor_master_ocr(Path(saved_upload["path"]))
            draft = parse_vendor_master_ocr_text(text, notes + [f"Source file: {saved_upload['original_filename']}"])
            source = dict(vendor or {"status": "active", "country": "Japan", "default_currency": "JPY", "vendor_type": "other", "supplier_record_mode": "standard_vendor", "is_qualified_invoice_vendor": "unknown", "entity_id": current_entity_id(user)})
            for key, value in draft.items():
                if key.startswith("vendor_ocr_"):
                    source[key] = value
                elif value and not str(source.get(key, "")).strip():
                    source[key] = value
            ocr_notes = source.get("vendor_ocr_confidence_notes") if isinstance(source.get("vendor_ocr_confidence_notes"), list) else []
            if ocr_notes:
                source["notes"] = (str(source.get("notes", "")).strip() + "\n\nOCR notes:\n" + "\n".join(f"- {note}" for note in ocr_notes)).strip()
            self.send_vendor_form(lang, messages, user, "edit" if mode == "edit" and vendor else "create", vendor, errors, source)
        except ValueError as exc:
            errors["vendor_ocr_file"] = str(exc)
            self.send_vendor_form(lang, messages, user, "edit" if mode == "edit" and vendor else "create", vendor, errors, vendor or None)

    def handle_create_vendor(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        vendors = load_vendors()
        values, errors = validate_vendor_input(form, vendors, messages)
        if errors:
            self.send_vendor_form(lang, messages, user, "create", None, errors, values)
            return
        timestamp = now_iso()
        vendor = {"vendor_id": next_id(vendors, "vendor_id", "VEN-", 4), **vendor_persisted_values(values), "created_at": timestamp, "created_by": actor_label(user), "updated_at": timestamp, "updated_by": actor_label(user)}
        vendors.append(vendor)
        save_vendors(vendors)
        version = append_masterdata_version("vendor", str(vendor["vendor_id"]), "create", user, vendor, "Initial vendor master creation.", masterdata_record_fields("vendor"))
        append_audit("vendor", str(vendor["vendor_id"]), "create", user, None, vendor, "Initial vendor master creation.", masterdata_record_fields("vendor"), str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/vendors/{vendor['vendor_id']}", lang, {"message": "vendor.created", "record": vendor_label(vendor, lang), "time": now_iso()}))

    def handle_update_vendor(self, lang: str, messages: dict[str, str], user: dict[str, Any], vendor_id: str) -> None:
        form = self.parse_form_body()
        vendors = load_vendors()
        index = next((i for i, vendor in enumerate(vendors) if str(vendor.get("vendor_id", "")) == vendor_id and vendor.get("status") != "deleted"), None)
        if index is None or not vendor_accessible_to_user(vendors[index], user):
            self.send_not_found(lang, messages, user, "vendor.not_found", "/vendors")
            return
        values, errors = validate_vendor_input(form, vendors, messages, vendor_id)
        if errors:
            values["change_reason"] = form.get("change_reason", "")
            self.send_vendor_form(lang, messages, user, "edit", {**vendors[index], **values}, errors, values)
            return
        before_value = dict(vendors[index])
        updated = {**vendors[index], **vendor_persisted_values(values), "vendor_id": vendor_id, "created_at": vendors[index].get("created_at", now_iso()), "created_by": vendors[index].get("created_by", actor_label(user)), "updated_at": now_iso(), "updated_by": actor_label(user)}
        changed = masterdata_changed_fields("vendor", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            values["change_reason"] = form.get("change_reason", "")
            self.send_vendor_form(lang, messages, user, "edit", {**vendors[index], **values}, {**errors, **governance_errors}, values)
            return
        if not changed:
            self.redirect(url_with_lang(f"/vendors/{vendor_id}", lang, {"message": "governance.no_changes", "record": vendor_label(vendors[index], lang), "time": now_iso()}))
            return
        ensure_masterdata_version_baseline("vendor", vendor_id, user, before_value)
        vendors[index] = updated
        save_vendors(vendors)
        version = append_masterdata_version("vendor", vendor_id, "update", user, updated, change_reason, changed)
        append_audit("vendor", vendor_id, "update", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/vendors/{vendor_id}", lang, {"message": "vendor.updated", "record": vendor_label(updated, lang), "time": now_iso()}))

    def handle_delete_vendor(self, lang: str, messages: dict[str, str], user: dict[str, Any], vendor_id: str) -> None:
        vendors = load_vendors()
        index = next((i for i, vendor in enumerate(vendors) if str(vendor.get("vendor_id", "")) == vendor_id and vendor.get("status") != "deleted"), None)
        if index is None or not vendor_accessible_to_user(vendors[index], user):
            self.send_not_found(lang, messages, user, "vendor.not_found", "/vendors")
            return
        form = self.parse_form_body()
        before_value = dict(vendors[index])
        updated = {**vendors[index], "status": "inactive", "updated_at": now_iso(), "updated_by": actor_label(user)}
        changed = masterdata_changed_fields("vendor", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            self.send_vendor_form(lang, messages, user, "edit", vendors[index], governance_errors, {**vendors[index], "change_reason": form.get("change_reason", "")})
            return
        ensure_masterdata_version_baseline("vendor", vendor_id, user, before_value)
        vendors[index] = updated
        save_vendors(vendors)
        version = append_masterdata_version("vendor", vendor_id, "deactivate", user, updated, change_reason, changed)
        append_audit("vendor", vendor_id, "deactivate", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/vendors", lang, {"message": "vendor.deactivated", "record": vendor_label(updated, lang), "time": now_iso()}))


    def send_customers_list(self, lang: str, messages: dict[str, str], user: dict[str, Any], query: dict[str, list[str]]) -> None:
        include_inactive = query.get("include_inactive", [""])[0] == "1" and can_customer_master_maintain(user)
        customers = visible_customers() if include_inactive else active_customers()
        customers = sorted(customers, key=lambda item: str(item.get("customer_code", "")).casefold())
        maintain = can_customer_master_maintain(user)
        rows = []
        for customer in customers:
            customer_id = str(customer.get("customer_id", ""))
            actions = [f'<a class="button ghost" href="{h(url_with_lang(f"/customers/{customer_id}", lang))}">{h(t(messages, "action.view"))}</a>']
            if maintain:
                actions.append(f'<a class="button secondary" href="{h(url_with_lang(f"/customers/{customer_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
                actions.append(
                    f'<form class="inline-form" method="post" action="{h(url_with_lang(f"/customers/{customer_id}/delete", lang))}" data-confirm-reason="1">'
                    '<input type="hidden" name="masterdata_change_ack" value="1"><input type="hidden" name="change_reason" value="">'
                    f'<button class="danger" type="submit">{h(t(messages, "action.deactivate"))}</button></form>'
                )
            rows.append(
                "<tr>"
                f"<td>{h(customer.get('customer_code'))}</td>"
                f"<td>{h(customer.get('customer_name'))}</td>"
                f"<td>{h(t(messages, 'customer.customer_record_mode.' + str(customer.get('customer_record_mode', 'standard_customer') or 'standard_customer'), str(customer.get('customer_record_mode', 'standard_customer') or 'standard_customer')))}</td>"
                f"<td>{h(customer.get('customer_name_en'))}</td>"
                f"<td>{h(customer.get('billing_contact_name'))}</td>"
                f"<td>{h(customer.get('billing_contact_email'))}</td>"
                f"<td>{h(customer.get('default_language'))}</td>"
                f"<td>{h(customer.get('default_payment_terms_days'))}</td>"
                f"<td><span class=\"badge {h(customer.get('status'))}\">{h(render_status(messages, str(customer.get('status', ''))))}</span></td>"
                f"<td class=\"actions\">{''.join(actions)}</td>"
                "</tr>"
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="10" class="muted">{h(t(messages, "common.no_records"))}</td></tr>'
        create_action = f'<a class="button" href="{h(url_with_lang("/customers/new", lang))}">{h(t(messages, "action.create_customer", "Create Customer"))}</a>' if maintain else f'<span class="badge">{h(t(messages, "common.read_only"))}</span>'
        message_html = render_message_from_query(messages, query)
        body = f"""
<section class="card">
  <div class="topline">
    <div>
      <h2>{h(t(messages, "customer.list_title", "Customer Master"))}</h2>
      <p class="muted">{h(t(messages, "dashboard.customers.description", "Manage customer billing master data used by Customer Billing."))}</p>
    </div>
    <div>{create_action}</div>
  </div>
  {message_html}
  <table>
    <thead><tr><th>{h(t(messages, "customer.customer_code", "Customer Code"))}</th><th>{h(t(messages, "customer.customer_name", "Customer Name"))}</th><th>{h(t(messages, "customer.customer_record_mode", "Customer Mode"))}</th><th>{h(t(messages, "customer.customer_name_en", "English Name"))}</th><th>{h(t(messages, "customer.billing_contact_name", "Billing Contact"))}</th><th>{h(t(messages, "customer.billing_contact_email", "Billing Email"))}</th><th>{h(t(messages, "customer.default_language", "Language"))}</th><th>{h(t(messages, "customer.default_payment_terms_days", "Terms Days"))}</th><th>{h(t(messages, "common.status"))}</th><th>{h(t(messages, "common.actions"))}</th></tr></thead>
    <tbody>{table_body}</tbody>
  </table>
</section>
"""
        self.send_html(200, t(messages, "customer.list_title", "Customer Master"), body, lang, messages, user)

    def send_customer_detail(self, lang: str, messages: dict[str, str], user: dict[str, Any], customer_id: str, query: dict[str, list[str]]) -> None:
        customer = find_customer(customer_id)
        if not customer:
            self.send_not_found(lang, messages, user, "customer.not_found", "/customers")
            return
        maintain = can_customer_master_maintain(user)
        actions = [f'<a class="button secondary" href="{h(url_with_lang("/customers", lang))}">{h(t(messages, "action.back"))}</a>']
        if maintain:
            actions.append(f'<a class="button" href="{h(url_with_lang(f"/customers/{customer_id}/edit", lang))}">{h(t(messages, "action.edit"))}</a>')
        message_html = render_message_from_query(messages, query)
        fields = [
            ("customer.customer_id", "customer_id"),
            ("customer.customer_code", "customer_code"),
            ("customer.customer_record_mode", "customer_record_mode"),
            ("customer.customer_name", "customer_name"),
            ("customer.customer_name_en", "customer_name_en"),
            ("customer.customer_name_zh", "customer_name_zh"),
            ("customer.customer_registration_number", "customer_registration_number"),
            ("customer.billing_address", "billing_address"),
            ("customer.billing_contact_name", "billing_contact_name"),
            ("customer.billing_contact_email", "billing_contact_email"),
            ("customer.default_language", "default_language"),
            ("customer.default_payment_terms_days", "default_payment_terms_days"),
            ("customer.default_tax_rate", "default_tax_rate"),
            ("customer.business_types", "business_types"),
            ("customer.notes", "notes"),
            ("common.status", "status"),
            ("common.created_at", "created_at"),
            ("common.updated_at", "updated_at"),
        ]
        rows = ""
        for label_key, field in fields:
            if field == "business_types" and isinstance(customer.get(field), list):
                display_value = ", ".join(customer.get(field, []))
            elif field == "status":
                display_value = render_status(messages, str(customer.get(field, "")))
            elif field == "customer_record_mode":
                mode_value = str(customer.get(field, "standard_customer") or "standard_customer")
                display_value = t(messages, f"customer.customer_record_mode.{mode_value}", mode_value)
            else:
                display_value = customer.get(field, "")
            rows += f"<tr><th>{h(t(messages, label_key, label_key))}</th><td>{h(display_value)}</td></tr>"
        body = f"""
<section class="card">
  <h2>{h(t(messages, "customer.detail_title", "Customer Detail"))}</h2>
  {message_html}
  <table><tbody>{rows}</tbody></table>
  <p class="actions">{''.join(actions)}</p>
</section>
{render_masterdata_version_history("customer", customer_id, customer, messages, lang, maintain)}
"""
        self.send_html(200, t(messages, "customer.detail_title", "Customer Detail"), body, lang, messages, user)

    def send_customer_form(self, lang: str, messages: dict[str, str], user: dict[str, Any], mode: str, customer: Optional[dict[str, Any]], errors: dict[str, str], values: Optional[dict[str, Any]] = None) -> None:
        is_edit = mode == "edit"
        source: dict[str, Any] = values or customer or {"status": "active", "default_language": "ja", "default_payment_terms_days": 30, "default_tax_rate": "10%", "customer_record_mode": "standard_customer"}
        title_key = "customer.edit_title" if is_edit else "customer.new_title"
        action_path = f"/customers/{customer.get('customer_id')}/edit" if is_edit and customer else "/customers/new"
        status_options = "".join(f'<option value="{h(status)}" {"selected" if str(source.get("status", "active")) == status else ""}>{h(render_status(messages, status))}</option>' for status in ("active", "inactive"))
        lang_options = "".join(f'<option value="{h(code)}" {"selected" if str(source.get("default_language", "ja")) == code else ""}>{h(code)}</option>' for code in ("ja", "en", "zh"))
        tax_options = "".join(f'<option value="{h(rate)}" {"selected" if str(source.get("default_tax_rate", "10%")) == rate else ""}>{h(rate)}</option>' for rate in ("10%", "8%", "0%", "mixed", "unknown"))
        customer_record_mode_options = "".join(f'<option value="{h(item)}" {"selected" if str(source.get("customer_record_mode", "standard_customer")) == item else ""}>{h(t(messages, "customer.customer_record_mode." + item, item))}</option>' for item in ("standard_customer", "one_time_customer"))
        business_types_value = ",".join(source.get("business_types", [])) if isinstance(source.get("business_types"), list) else str(source.get("business_types", ""))
        field_specs = [
            ("customer_code", "customer.customer_code", "text", True),
            ("customer_name", "customer.customer_name", "text", True),
            ("customer_name_en", "customer.customer_name_en", "text", False),
            ("customer_name_zh", "customer.customer_name_zh", "text", False),
            ("customer_registration_number", "customer.customer_registration_number", "text", False),
            ("billing_contact_name", "customer.billing_contact_name", "text", False),
            ("billing_contact_email", "customer.billing_contact_email", "email", False),
            ("default_payment_terms_days", "customer.default_payment_terms_days", "number", True),
        ]
        inputs = []
        for field, label_key, input_type, required in field_specs:
            error = errors.get(field, "")
            required_text = h(t(messages, "common.required")) if required else ""
            error_html = f'<div class="field-error">{h(error)}</div>' if error else ""
            inputs.append(
                f'<label for="{h(field)}">{h(t(messages, label_key, field))} <span class="muted">{required_text}</span></label>'
                f'<input type="{h(input_type)}" id="{h(field)}" name="{h(field)}" value="{h(source.get(field, ""))}">'
                f'{error_html}'
            )
        customer_ocr_error = errors.get("customer_ocr_file", "")
        customer_ocr_error_html = f'<div class="field-error">{h(customer_ocr_error)}</div>' if customer_ocr_error else ''
        customer_ocr_form = f"""
<section class=\"card\">
  <h3>{h(t(messages, 'customer.ocr_title', 'OCR Draft from Issued Invoice'))}</h3>
  <p class=\"muted\">{h(t(messages, 'customer.ocr_help', 'Upload a previously issued invoice to prefill a Customer Master draft. Review before saving.'))}</p>
  <form method=\"post\" enctype=\"multipart/form-data\" action=\"{h(url_with_lang('/customers/ocr', lang))}\">
    <input type=\"hidden\" name=\"mode\" value=\"{h(mode)}\">
    <input type=\"hidden\" name=\"customer_id\" value=\"{h(customer.get('customer_id', '') if customer else '')}\">
    <label for=\"customer_ocr_file\">{h(t(messages, 'customer.ocr_file', 'Issued invoice file'))}</label>
    <input type=\"file\" id=\"customer_ocr_file\" name=\"customer_ocr_file\" accept=\".pdf,.jpg,.jpeg,.png,.webp\">
    {customer_ocr_error_html}
    <p class=\"actions\"><button type=\"submit\">{h(t(messages, 'customer.ocr_extract', 'Extract OCR Draft'))}</button></p>
  </form>
</section>
"""
        body = f"""
{customer_ocr_form}
<section class="card">
  <h2>{h(t(messages, title_key, "Customer"))}</h2>
  {render_errors(errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    <label for="customer_record_mode">{h(t(messages, "customer.customer_record_mode", "Customer Mode"))}</label><select id="customer_record_mode" name="customer_record_mode">{customer_record_mode_options}</select>{f'<div class="field-error">{h(errors.get("customer_record_mode", ""))}</div>' if errors.get("customer_record_mode") else ''}<p class="muted">{h(t(messages, "customer.one_time_help", "One-time customers use a customer code ending in 9999. Downstream billing flows should collect manual billing/customer descriptions when this record is selected."))}</p>
    {''.join(inputs)}
    <label for="default_language">{h(t(messages, "customer.default_language", "Default Language"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="default_language" name="default_language">{lang_options}</select>
    {f'<div class="field-error">{h(errors.get("default_language", ""))}</div>' if errors.get("default_language") else ''}
    <label for="default_tax_rate">{h(t(messages, "customer.default_tax_rate", "Default Tax Rate"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="default_tax_rate" name="default_tax_rate">{tax_options}</select>
    {f'<div class="field-error">{h(errors.get("default_tax_rate", ""))}</div>' if errors.get("default_tax_rate") else ''}
    <label for="business_types">{h(t(messages, "customer.business_types", "Business Types"))}</label>
    <input id="business_types" name="business_types" value="{h(business_types_value)}" placeholder="haken_dispatch,recruitment_placement,rpo">
    <label for="billing_address">{h(t(messages, "customer.billing_address", "Billing Address"))}</label>
    <textarea id="billing_address" name="billing_address">{h(source.get('billing_address', ''))}</textarea>
    <label for="notes">{h(t(messages, "customer.notes", "Notes"))}</label>
    <textarea id="notes" name="notes">{h(source.get('notes', ''))}</textarea>
    <label for="status">{h(t(messages, "common.status"))} <span class="muted">{h(t(messages, "common.required"))}</span></label>
    <select id="status" name="status">{status_options}</select>
    {f'<div class="field-error">{h(errors.get("status", ""))}</div>' if errors.get("status") else ''}
    {render_change_governance_block(messages, errors, source) if is_edit else ""}
    <p class="actions"><button type="submit">{h(t(messages, "action.save"))}</button><a class="button secondary" href="{h(url_with_lang('/customers', lang))}">{h(t(messages, "action.cancel"))}</a></p>
  </form>
</section>
"""
        self.send_html(200 if not errors else 400, t(messages, title_key, "Customer"), body, lang, messages, user)


    def handle_customer_ocr(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        fields, files = parse_multipart_form(self)
        mode = fields.get("mode", "create") or "create"
        customer_id = fields.get("customer_id", "").strip()
        customer = find_customer(customer_id) if customer_id else None
        upload = files.get("customer_ocr_file")
        errors: dict[str, str] = {}
        try:
            if not upload:
                raise ValueError("Please choose an issued invoice file before OCR extraction.")
            saved_upload = save_customer_ocr_upload(upload)
            text, notes = run_customer_master_ocr(Path(saved_upload["path"]))
            draft = parse_customer_master_ocr_text(text, notes + [f"Source file: {saved_upload['original_filename']}"])
            source = dict(customer or {"status": "active", "default_language": "ja", "default_payment_terms_days": 30, "default_tax_rate": "10%", "customer_record_mode": "standard_customer"})
            for key, value in draft.items():
                if key.startswith("customer_ocr_"):
                    source[key] = value
                elif value and not str(source.get(key, "")).strip():
                    source[key] = value
            ocr_notes = source.get("customer_ocr_confidence_notes") if isinstance(source.get("customer_ocr_confidence_notes"), list) else []
            if ocr_notes:
                source["notes"] = (str(source.get("notes", "")).strip() + "\n\nOCR notes:\n" + "\n".join(f"- {note}" for note in ocr_notes)).strip()
            self.send_customer_form(lang, messages, user, "edit" if mode == "edit" and customer else "create", customer, errors, source)
        except ValueError as exc:
            errors["customer_ocr_file"] = str(exc)
            self.send_customer_form(lang, messages, user, "edit" if mode == "edit" and customer else "create", customer, errors, customer or None)

    def handle_create_customer(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        form = self.parse_form_body()
        customers = load_customers()
        values, errors = validate_customer_input(form, customers, messages)
        if errors:
            self.send_customer_form(lang, messages, user, "create", None, errors, values)
            return
        timestamp = now_iso()
        customer = {"customer_id": next_id(customers, "customer_id", "CUS-", 4), **customer_persisted_values(values), "created_at": timestamp, "created_by": actor_label(user), "updated_at": timestamp, "updated_by": actor_label(user)}
        customers.append(customer)
        save_customers(customers)
        version = append_masterdata_version("customer", str(customer["customer_id"]), "create", user, customer, "Initial customer master creation.", masterdata_record_fields("customer"))
        append_audit("customer", str(customer["customer_id"]), "create", user, None, customer, "Initial customer master creation.", masterdata_record_fields("customer"), str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/customers/{customer['customer_id']}", lang, {"message": "customer.created", "record": customer_label(customer, lang), "time": now_iso()}))

    def handle_update_customer(self, lang: str, messages: dict[str, str], user: dict[str, Any], customer_id: str) -> None:
        form = self.parse_form_body()
        customers = load_customers()
        index = next((i for i, customer in enumerate(customers) if str(customer.get("customer_id", "")) == customer_id and customer.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "customer.not_found", "/customers")
            return
        values, errors = validate_customer_input(form, customers, messages, customer_id)
        if errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**customers[index], **values}
            self.send_customer_form(lang, messages, user, "edit", current, errors, values)
            return
        before_value = dict(customers[index])
        updated = {**customers[index], **customer_persisted_values(values), "customer_id": customer_id, "created_at": customers[index].get("created_at", now_iso()), "created_by": customers[index].get("created_by", actor_label(user)), "updated_at": now_iso(), "updated_by": actor_label(user)}
        changed = masterdata_changed_fields("customer", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            values["change_reason"] = form.get("change_reason", "")
            current = {**customers[index], **values}
            self.send_customer_form(lang, messages, user, "edit", current, {**errors, **governance_errors}, values)
            return
        if not changed:
            self.redirect(url_with_lang(f"/customers/{customer_id}", lang, {"message": "governance.no_changes", "record": customer_label(customers[index], lang), "time": now_iso()}))
            return
        ensure_masterdata_version_baseline("customer", customer_id, user, before_value)
        customers[index] = updated
        save_customers(customers)
        version = append_masterdata_version("customer", customer_id, "update", user, updated, change_reason, changed)
        append_audit("customer", customer_id, "update", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/customers/{customer_id}", lang, {"message": "customer.updated", "record": customer_label(updated, lang), "time": now_iso()}))

    def handle_delete_customer(self, lang: str, messages: dict[str, str], user: dict[str, Any], customer_id: str) -> None:
        customers = load_customers()
        index = next((i for i, customer in enumerate(customers) if str(customer.get("customer_id", "")) == customer_id and customer.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, "customer.not_found", "/customers")
            return
        form = self.parse_form_body()
        before_value = dict(customers[index])
        updated = {**customers[index], "status": "inactive", "updated_at": now_iso(), "updated_by": actor_label(user)}
        changed = masterdata_changed_fields("customer", before_value, updated)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            self.send_customer_form(lang, messages, user, "edit", customers[index], governance_errors, {**customers[index], "change_reason": form.get("change_reason", "")})
            return
        ensure_masterdata_version_baseline("customer", customer_id, user, before_value)
        customers[index] = updated
        save_customers(customers)
        version = append_masterdata_version("customer", customer_id, "deactivate", user, updated, change_reason, changed)
        append_audit("customer", customer_id, "deactivate", user, before_value, updated, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang("/customers", lang, {"message": "customer.deactivated", "record": customer_label(updated, lang), "time": now_iso()}))

    def handle_restore_master_record(self, lang: str, messages: dict[str, str], user: dict[str, Any], record_type: str, record_id: str, version_id: str) -> None:
        form = self.parse_form_body()
        versions = masterdata_versions_for_record(record_type, record_id)
        target_version = next((version for version in versions if str(version.get("version_id", "")) == version_id), None)
        snapshot = target_version.get("data_snapshot", {}) if isinstance(target_version, dict) and isinstance(target_version.get("data_snapshot"), dict) else None
        if not target_version or not snapshot:
            self.send_not_found(lang, messages, user, "version.not_found", f"/{plural_path_for_record_type(record_type)}")
            return

        if record_type == "entity":
            records = load_entities()
            id_field = "entity_id"
            detail_title = "entity.detail_title"
            not_found_key = "entity.not_found"
            can_restore_record = can_admin_masterdata(user)
        elif record_type == "department":
            records = load_departments()
            id_field = "department_id"
            detail_title = "department.detail_title"
            not_found_key = "department.not_found"
            can_restore_record = True
        elif record_type == "team":
            records = load_teams()
            id_field = "team_id"
            detail_title = "team.detail_title"
            not_found_key = "team.not_found"
            can_restore_record = True
        elif record_type == "vendor":
            records = load_vendors()
            id_field = "vendor_id"
            detail_title = "vendor.detail_title"
            not_found_key = "vendor.not_found"
            can_restore_record = can_maintain(user)
        else:
            records = load_customers()
            id_field = "customer_id"
            detail_title = "customer.detail_title"
            not_found_key = "customer.not_found"
            can_restore_record = can_customer_master_maintain(user)

        index = next((i for i, record in enumerate(records) if str(record.get(id_field, "")) == record_id and record.get("status") != "deleted"), None)
        if index is None:
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        current = records[index]
        if record_type == "entity" and not entity_accessible_to_user(current, user):
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        if record_type == "department" and not department_accessible_to_user(current, user):
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        if record_type == "team" and not team_accessible_to_user(current, user):
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        if record_type == "customer" and not can_customer_master_view(user):
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        if record_type == "vendor" and (not can_view(user) or not vendor_accessible_to_user(current, user)):
            self.send_not_found(lang, messages, user, not_found_key, f"/{plural_path_for_record_type(record_type)}")
            return
        if not can_restore_record:
            self.send_forbidden(lang, messages, user)
            return

        before_value = dict(current)
        restored = {**current, **snapshot, id_field: record_id, "created_at": current.get("created_at", snapshot.get("created_at", now_iso())), "updated_at": now_iso()}
        changed = masterdata_changed_fields(record_type, before_value, restored)
        change_reason, governance_errors = validate_change_governance(form, messages, changed)
        if governance_errors:
            body = f"""
<section class="card">
  <h2>{h(t(messages, "version.restore_failed"))}</h2>
  {render_errors(governance_errors)}
  <p><a class="button secondary" href="{h(url_with_lang(f'/{plural_path_for_record_type(record_type)}/{quote(record_id)}', lang))}">{h(t(messages, "action.back"))}</a></p>
</section>
"""
            self.send_html(400, t(messages, detail_title), body, lang, messages, user)
            return
        if not changed:
            self.redirect(url_with_lang(f"/{plural_path_for_record_type(record_type)}/{quote(record_id)}", lang, {"message": "governance.no_changes", "record": record_id, "time": now_iso()}))
            return

        ensure_masterdata_version_baseline(record_type, record_id, user, before_value)
        records[index] = restored
        if record_type == "entity":
            save_entities(records)
        elif record_type == "department":
            save_departments(records)
        elif record_type == "team":
            save_teams(records)
        elif record_type == "vendor":
            save_vendors(records)
        else:
            save_customers(records)
        version = append_masterdata_version(record_type, record_id, "restore", user, restored, change_reason, changed, version_id)
        append_audit(record_type, record_id, "restore", user, before_value, restored, change_reason, changed, str(version.get("version_id", "")))
        self.redirect(url_with_lang(f"/{plural_path_for_record_type(record_type)}/{quote(record_id)}", lang, {"message": "version.restored", "record": record_id, "time": now_iso()}))




def migrate_legacy_customerbilling_customers() -> None:
    legacy_path = ROOT_DIR.parents[1] / "customerbilling" / "database" / "customers.json"
    if not legacy_path.exists():
        return
    legacy_rows = load_json_array(legacy_path)
    if not legacy_rows:
        return
    customers = load_customers()
    existing_ids = {str(row.get("customer_id", "")) for row in customers}
    existing_codes = {normalized_code(row.get("customer_code", "")) for row in customers}
    changed = False
    migration_user = {"username": "legacy_customerbilling_migration", "permissions": ["*"]}
    for legacy in legacy_rows:
        customer_id = str(legacy.get("customer_id", "") or "").strip()
        customer_code = str(legacy.get("customer_code", "") or customer_id).strip()
        if not customer_id or customer_id in existing_ids or normalized_code(customer_code) in existing_codes:
            continue
        timestamp = now_iso()
        customer = {
            "customer_id": customer_id,
            "customer_code": customer_code,
            "customer_record_mode": "standard_customer",
            "customer_name": str(legacy.get("customer_name", "") or legacy.get("customer_name_ja", "") or customer_code),
            "customer_name_en": str(legacy.get("customer_name_en", "")),
            "customer_name_zh": str(legacy.get("customer_name_zh", "")),
            "customer_registration_number": str(legacy.get("customer_registration_number", "")),
            "billing_address": str(legacy.get("billing_address", "")),
            "billing_contact_name": str(legacy.get("billing_contact_name", "")),
            "billing_contact_email": str(legacy.get("billing_contact_email", "")),
            "default_language": str(legacy.get("default_language", "ja") or "ja"),
            "default_payment_terms_days": int(legacy.get("default_payment_terms_days", 30) or 30),
            "default_tax_rate": str(legacy.get("default_tax_rate", "10%") or "10%"),
            "business_types": legacy.get("business_types", []) if isinstance(legacy.get("business_types"), list) else [],
            "notes": str(legacy.get("notes", "")),
            "status": "active" if str(legacy.get("record_status", "Active")) == "Active" else "inactive",
            "created_at": str(legacy.get("created_at", timestamp) or timestamp),
            "created_by": str(legacy.get("created_by", "legacy_customerbilling_migration") or "legacy_customerbilling_migration"),
            "updated_at": str(legacy.get("updated_at", timestamp) or timestamp),
            "updated_by": str(legacy.get("updated_by", "legacy_customerbilling_migration") or "legacy_customerbilling_migration"),
        }
        customers.append(customer)
        existing_ids.add(customer_id)
        existing_codes.add(normalized_code(customer_code))
        changed = True
        version = append_masterdata_version("customer", customer_id, "create", migration_user, customer, "Migrated from legacy customerbilling customer master.", masterdata_record_fields("customer"))
        append_audit("customer", customer_id, "migrate_from_customerbilling", migration_user, None, customer, "Migrated from legacy customerbilling customer master.", masterdata_record_fields("customer"), str(version.get("version_id", "")))
    if changed:
        save_customers(customers)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TACAI Master Data Management local web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8007)
    args = parser.parse_args()

    ensure_database_files()
    migrate_legacy_customerbilling_customers()
    server = ThreadingHTTPServer((args.host, args.port), MasterDataHandler)
    print(f"TACAI Master Data Management running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
