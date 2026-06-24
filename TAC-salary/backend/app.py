#!/usr/bin/env python3
"""Local TAC-salary web app.

Standard-library HTTP service for the salary MVP. It stores salary records,
APAC payroll v2 records, and audit logs as JSON files under ../database.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import io
import json
import mimetypes
import os
import re
import smtplib
import threading
import uuid
from datetime import datetime, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

try:
    from payroll_engines import apply_country_engine
except ModuleNotFoundError:  # Supports importlib-based tests from project root.
    from backend.payroll_engines import apply_country_engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "database"
FRONTEND_DIR = PROJECT_ROOT / "frontend"
PAYSLIP_DIR = PROJECT_ROOT / "payslips"
SALARY_FILE = DATA_DIR / "salary_records.json"
EMPLOYEE_FILE = DATA_DIR / "employees.json"
AUDIT_FILE = DATA_DIR / "audit_logs.json"

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
REQUIRED_MODULE_PERMISSION = "payroll.access"
AUTH_ENFORCEMENT = os.environ.get("TAC_SALARY_AUTH_ENFORCEMENT", "soft").strip().lower()
USER_ADMIN_BASE_URL = (os.environ.get("USER_ADMIN_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8006").strip() or f"http://{TACAI_PUBLIC_HOST}:8006").rstrip("/")
USER_ADMIN_INTERNAL_BASE_URL = (os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", f"http://{TACAI_INTERNAL_HOST}:8006").strip() or f"http://{TACAI_INTERNAL_HOST}:8006").rstrip("/")
EMPLOYEEADMIN_INTERNAL_BASE_URL = (os.environ.get("EMPLOYEEADMIN_INTERNAL_BASE_URL", f"http://{TACAI_INTERNAL_HOST}:8004").strip() or f"http://{TACAI_INTERNAL_HOST}:8004").rstrip("/")
EMPLOYEEADMIN_LOCAL_FILE = PROJECT_ROOT.parent / "TAC-employeeadmin" / "database" / "employees.json"
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8005").strip() or f"http://{TACAI_PUBLIC_HOST}:8005").rstrip("/")
APP_BASE_URL = ((os.environ.get("TAC_PAYROLL_PUBLIC_BASE_URL") or os.environ.get("SALARY_PUBLIC_BASE_URL") or f"http://{TACAI_PUBLIC_HOST}:8005").strip() or f"http://{TACAI_PUBLIC_HOST}:8005").rstrip("/")

PAYROLL_BATCHES_FILE = DATA_DIR / "payroll_batches.json"
PAYROLL_RECORDS_JP_FILE = DATA_DIR / "payroll_records_jp.json"
PAYROLL_RECORDS_SG_FILE = DATA_DIR / "payroll_records_sg.json"
PAYROLL_RECORDS_CN_FILE = DATA_DIR / "payroll_records_cn.json"
SALARY_MASTER_FILE = DATA_DIR / "salary_master.json"
PAYROLL_PARAMETERS_FILE = DATA_DIR / "payroll_parameters.json"
PAYROLL_NOTICES_FILE = DATA_DIR / "payroll_notices.json"
PAYSLIP_DOCUMENTS_FILE = DATA_DIR / "payslip_documents.json"
EMPLOYEE_FEEDBACK_FILE = DATA_DIR / "employee_feedback.json"
PAYROLL_CONFIRMATIONS_FILE = DATA_DIR / "payroll_confirmations.json"
PAYMENT_RECORDS_FILE = DATA_DIR / "payment_records.json"
PAYROLL_IMPORT_RUNS_FILE = DATA_DIR / "payroll_import_runs.json"

ALL_JSON_FILES = (
    SALARY_FILE,
    EMPLOYEE_FILE,
    AUDIT_FILE,
    PAYROLL_BATCHES_FILE,
    PAYROLL_RECORDS_JP_FILE,
    PAYROLL_RECORDS_SG_FILE,
    PAYROLL_RECORDS_CN_FILE,
    SALARY_MASTER_FILE,
    PAYROLL_PARAMETERS_FILE,
    PAYROLL_NOTICES_FILE,
    PAYSLIP_DOCUMENTS_FILE,
    EMPLOYEE_FEEDBACK_FILE,
    PAYROLL_CONFIRMATIONS_FILE,
    PAYMENT_RECORDS_FILE,
    PAYROLL_IMPORT_RUNS_FILE,
)

PAYROLL_RECORD_FILES = {
    "JP": PAYROLL_RECORDS_JP_FILE,
    "SG": PAYROLL_RECORDS_SG_FILE,
    "CN": PAYROLL_RECORDS_CN_FILE,
}

MASTER_ENTITIES = {
    "ENT-0001": {
        "entity_id": "ENT-0001",
        "entity_code": "TAKK",
        "country_code": "JP",
        "country_name": "Japan",
        "currency": "JPY",
        "entity_name_en": "Tech Alliance KK",
        "entity_name_local": "Tech Alliance株式会社",
        "status": "active",
    },
    "ENT-0002": {
        "entity_id": "ENT-0002",
        "entity_code": "TASG",
        "country_code": "SG",
        "country_name": "Singapore",
        "currency": "SGD",
        "entity_name_en": "Tech Alliance Consultancy Service Pte. Ltd",
        "entity_name_local": "Tech Alliance Consultancy Service Pte. Ltd",
        "status": "active",
    },
    "ENT-0003": {
        "entity_id": "ENT-0003",
        "entity_code": "TANJ",
        "country_code": "CN",
        "country_name": "China",
        "currency": "CNY",
        "entity_name_en": "Tech Alliance Consultancy Nanjing Co. Ltd",
        "entity_name_local": "南京特谙斯企业咨询有限公司",
        "status": "active",
    },
    "ENT-0004": {
        "entity_id": "ENT-0004",
        "entity_code": "TAXA",
        "country_code": "CN",
        "country_name": "China",
        "currency": "CNY",
        "entity_name_en": "Tech Alliance Consultancy Xian Co. Ltd",
        "entity_name_local": "西安特谙斯企业咨询有限公司",
        "status": "active",
    },
    "ENT-0005": {
        "entity_id": "ENT-0005",
        "entity_code": "TASH",
        "country_code": "CN",
        "country_name": "China",
        "currency": "CNY",
        "entity_name_en": "Tech Alliance Consultancy Shanghai Co. Ltd",
        "entity_name_local": "上海特安企业管理有限公司",
        "status": "active",
    },
}

COUNTRY_PAYROLL_SYSTEMS = {
    "JP": {
        "payroll_system_code": "JP_PAYROLL",
        "payroll_area_code": "JP_MONTHLY",
        "route": "/payroll/jp",
        "module": "日本薪资计算",
        "module_en": "Japan Payroll",
        "currency": "JPY",
        "description": "Japan salary calculation with haken/dispatch context, overtime, social insurance and resident tax workflow.",
    },
    "SG": {
        "payroll_system_code": "SG_PAYROLL",
        "payroll_area_code": "SG_MONTHLY",
        "route": "/payroll/sg",
        "module": "新加坡薪资计算",
        "module_en": "Singapore Payroll",
        "currency": "SGD",
        "description": "Singapore payroll with CPF employee/employer, work pass and employer cost workflow.",
    },
    "CN": {
        "payroll_system_code": "CN_PAYROLL",
        "payroll_area_code": "CN_MONTHLY",
        "route": "/payroll/cn",
        "module": "中国薪资计算",
        "module_en": "China Payroll",
        "currency": "CNY",
        "description": "China payroll scoped to China entities, city parameters, social insurance, housing fund and IIT workflow.",
    },
}

REQUIRED_CREATE_FIELDS = {"employee_id", "salary_month", "base_salary"}
MONEY_FIELDS = {
    "base_salary",
    "position_allowance",
    "commute_allowance",
    "housing_allowance",
    "other_allowance",
    "overtime_pay",
    "health_insurance",
    "pension_insurance",
    "employment_insurance",
    "income_tax",
    "resident_tax",
    "other_deduction",
}

PAYROLL_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
FILE_LOCK = threading.RLock()
DRAFT_SALARY_STATUS = "draft"
ACTIVE_SALARY_STATUS = "active"
PAYROLL_ELIGIBLE_SALARY_STATUSES = {ACTIVE_SALARY_STATUS}
SALARY_RULE_TYPES = {"monthly_fixed", "monthly_prorated", "hourly", "daily"}
LOCKED_BATCH_STATUSES = {"finalized", "payment_prepared", "paid", "archived"}
ACTIVE_BATCH_STATUSES = {
    "draft_created",
    "data_loaded",
    "calculated",
    "hr_review",
    "first_confirmed",
    "final_review",
    "finalized",
    "payment_prepared",
    "paid",
}

EARNING_FIELDS = (
    "base_salary",
    "position_allowance",
    "commute_allowance",
    "housing_allowance",
    "other_allowance",
    "overtime_pay",
    "late_night_overtime_pay",
    "holiday_work_pay",
    "statutory_holiday_work_pay",
    "bonus",
    "other_earnings",
)
DEDUCTION_FIELDS = (
    "health_insurance",
    "pension_insurance",
    "employment_insurance",
    "income_tax",
    "resident_tax",
    "cpf_employee",
    "social_insurance_employee",
    "housing_fund_employee",
    "individual_income_tax",
    "other_deduction",
)
EMPLOYER_COST_FIELDS = (
    "employer_health_insurance",
    "employer_pension_insurance",
    "employer_employment_insurance",
    "employer_workers_compensation",
    "cpf_employer",
    "social_insurance_employer",
    "housing_fund_employer",
    "employer_other_cost",
)

SUPPORTED_CN_CITIES = {"SHANGHAI", "NANJING", "XIAN", "WUHU"}

PERMISSION_GROUPS = {
    "view": {"payroll.access", "payroll.view", "payroll.reports.view", "salary.access", "salary.view", "employee_management.payroll.view"},
    "edit": {"payroll.edit", "salary.edit", "salary.batch.create", "salary.profile.manage", "salary.calculate", "salary.adjust", "employee_management.payroll.edit"},
    "reports": {"payroll.reports.view", "salary.reports.view", "financial_reports.view"},
    "payment": {"payroll.edit", "salary.payment.manage", "payroll.payment.manage"},
    "notice": {"payroll.edit", "salary.notice.send", "salary.payslip.download"},
    "audit": {"payroll.access", "payroll.view", "salary.audit.view"},
    "admin_override": {"salary.admin.override", "payroll.admin.override"},
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_database() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PAYSLIP_DIR.mkdir(parents=True, exist_ok=True)
    for path in ALL_JSON_FILES:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")


def read_json(path: Path) -> list[dict]:
    ensure_database()
    with FILE_LOCK:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON database file: {path.name}") from exc
    if not isinstance(payload, list):
        raise ValueError(f"JSON database file must contain an array: {path.name}")
    return payload


def write_json(path: Path, records: list[dict]) -> None:
    if not isinstance(records, list):
        raise ValueError("Only JSON arrays can be saved")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with FILE_LOCK:
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        tmp_path.replace(path)


def append_json_record(path: Path, record: dict) -> dict:
    records = read_json(path)
    records.append(record)
    write_json(path, records)
    return record


def money(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid money value: {value!r}") from exc


def clean_text(value: object) -> str:
    return str(value or "").strip()


def parse_bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y", "on"}
    return bool(value)


def get_nested(record: dict, path: str, default: object = "") -> object:
    current: object = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def parse_cookie_header(cookie_header: str) -> dict[str, str]:
    if not cookie_header:
        return {}
    cookie = SimpleCookie()
    try:
        cookie.load(cookie_header)
    except Exception:
        return {}
    return {key: morsel.value for key, morsel in cookie.items()}


def validate_user_admin_session(session_id: str) -> dict | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id, "module_key": "payroll", "module_path": "/"}).encode("utf-8")
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


def has_permission(user: dict | None, permission_key: str) -> bool:
    if not user:
        return False
    roles = {str(role) for role in user.get("roles", [])}
    role = str(user.get("role", ""))
    permissions = {str(permission) for permission in user.get("permissions", [])}
    return role == "system_admin" or "system_admin" in roles or "*" in permissions or permission_key in permissions


def has_any_permission(user: dict | None, permission_keys: set[str] | list[str] | tuple[str, ...]) -> bool:
    return any(has_permission(user, permission_key) for permission_key in permission_keys)


def permission_group(name: str) -> set[str]:
    return set(PERMISSION_GROUPS.get(name, set()))


def is_system_admin(user: dict | None) -> bool:
    if not user:
        return False
    roles = {str(role) for role in user.get("roles", [])}
    return str(user.get("role", "")) == "system_admin" or "system_admin" in roles or "*" in {str(permission) for permission in user.get("permissions", [])}


def actor_from_user(user: dict | None, fallback: str = "local_admin") -> str:
    if not user:
        return fallback
    for key in ("username", "email", "display_name", "user_id", "id"):
        value = clean_text(user.get(key))
        if value:
            return value
    return fallback


def normalize_country_code(value: object) -> str:
    raw = clean_text(value).upper()
    aliases = {
        "JAPAN": "JP",
        "日本": "JP",
        "SGP": "SG",
        "SINGAPORE": "SG",
        "新加坡": "SG",
        "CHINA": "CN",
        "中国": "CN",
    }
    code = aliases.get(raw, raw)
    if code not in PAYROLL_RECORD_FILES:
        raise ValueError("country_code must be JP, SG, or CN")
    return code


def country_payroll_system(country_code: object) -> dict:
    return dict(COUNTRY_PAYROLL_SYSTEMS[normalize_country_code(country_code)])


def payroll_system_code(country_code: object) -> str:
    return country_payroll_system(country_code)["payroll_system_code"]


def payroll_area_code(country_code: object) -> str:
    return country_payroll_system(country_code)["payroll_area_code"]


def default_rule_version_id(country_code: object, payroll_month: object = "") -> str:
    country = normalize_country_code(country_code)
    month = clean_text(payroll_month) or now_iso()[:7]
    return f"RULE-{country}-{month}-V001"


def validate_payroll_month(value: object) -> str:
    month = clean_text(value)
    if not PAYROLL_MONTH_RE.match(month):
        raise ValueError("payroll_month must use YYYY-MM format")
    month_number = int(month[-2:])
    if not 1 <= month_number <= 12:
        raise ValueError("payroll_month month must be 01-12")
    return month


def parse_date(value: object):
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def payroll_period(batch: dict) -> tuple[object, object]:
    payroll_month = validate_payroll_month(batch.get("payroll_month"))
    year = int(payroll_month[:4])
    month = int(payroll_month[-2:])
    period_start = parse_date(batch.get("period_start")) or datetime(year, month, 1).date()
    period_end = parse_date(batch.get("period_end")) or datetime(year, month, calendar.monthrange(year, month)[1]).date()
    return period_start, period_end


def payable_days_for_period(batch: dict, contract_snapshot: dict) -> tuple[int, int]:
    period_start, period_end = payroll_period(batch)
    start_candidates = [period_start]
    end_candidates = [period_end]
    for field in ("contract_start_date", "employment_start_date"):
        date_value = parse_date(contract_snapshot.get(field))
        if date_value:
            start_candidates.append(date_value)
    for field in ("contract_end_date", "employment_end_date"):
        date_value = parse_date(contract_snapshot.get(field))
        if date_value:
            end_candidates.append(date_value)
    effective_start = max(start_candidates)
    effective_end = min(end_candidates)
    total_days = max((period_end - period_start).days + 1, 1)
    if effective_start > effective_end:
        return 0, total_days
    return max((effective_end - effective_start).days + 1, 0), total_days


def entity_snapshot(entity_id: object, country_code: object | None = None) -> dict:
    entity_key = clean_text(entity_id)
    entity = MASTER_ENTITIES.get(entity_key)
    if not entity or entity.get("status") != "active":
        raise ValueError(f"Unknown or inactive entity_id: {entity_key}")
    if country_code is not None and entity["country_code"] != normalize_country_code(country_code):
        raise ValueError(f"Entity {entity_key} does not belong to country {country_code}")
    snapshot = dict(entity)
    country_system = country_payroll_system(snapshot["country_code"])
    snapshot["legal_entity_id"] = snapshot["entity_id"]
    snapshot["payroll_system_code"] = country_system["payroll_system_code"]
    snapshot["payroll_area_code"] = country_system["payroll_area_code"]
    snapshot["payroll_module_name"] = country_system["module"]
    return snapshot


def payroll_record_file(country_code: object) -> Path:
    return PAYROLL_RECORD_FILES[normalize_country_code(country_code)]


def month_digits(payroll_month: str) -> str:
    return payroll_month.replace("-", "")


def make_batch_id(country_code: str, entity_id: str, payroll_month: str, batch_version: int) -> str:
    return f"PB-{country_code}-{entity_id}-{payroll_month}-V{batch_version:03d}"


def make_payroll_record_id(country_code: str, entity_id: str, payroll_month: str, employee_id: str, batch_version: int) -> str:
    safe_employee = re.sub(r"[^A-Za-z0-9_-]", "", employee_id) or "EMP"
    return f"PR-{country_code}-{entity_id}-{payroll_month}-{safe_employee}-V{batch_version:03d}"


def next_sequence_id(prefix: str, payroll_month: str, existing_records: list[dict], id_field: str) -> str:
    base = f"{prefix}-{month_digits(payroll_month)}-"
    max_number = 0
    for record in existing_records:
        value = str(record.get(id_field, ""))
        if value.startswith(base):
            try:
                max_number = max(max_number, int(value[len(base) :]))
            except ValueError:
                continue
    return f"{base}{max_number + 1:04d}"


def batch_by_id(batch_id: str) -> dict | None:
    return next((batch for batch in read_json(PAYROLL_BATCHES_FILE) if batch.get("batch_id") == batch_id), None)


def batch_records(batch_id: str, country_code: str | None = None) -> list[dict]:
    if country_code:
        files = [payroll_record_file(country_code)]
    else:
        files = list(PAYROLL_RECORD_FILES.values())
    rows: list[dict] = []
    for path in files:
        rows.extend(record for record in read_json(path) if record.get("batch_id") == batch_id)
    return rows


def find_payroll_record(record_id: str) -> tuple[Path, list[dict], int, dict] | None:
    for path in PAYROLL_RECORD_FILES.values():
        records = read_json(path)
        for index, record in enumerate(records):
            if record.get("payroll_record_id") == record_id:
                return path, records, index, record
    return None


def update_batch(batch_id: str, changes: dict) -> dict:
    batches = read_json(PAYROLL_BATCHES_FILE)
    for index, batch in enumerate(batches):
        if batch.get("batch_id") == batch_id:
            updated = dict(batch)
            updated.update(changes)
            updated["updated_at"] = now_iso()
            batches[index] = updated
            write_json(PAYROLL_BATCHES_FILE, batches)
            return updated
    raise ValueError("Payroll batch not found")


def calculate_batch_totals(records: list[dict]) -> dict:
    return {
        "employee_count": len(records),
        "gross_pay_total": round(sum(money(record.get("gross_pay")) for record in records), 2),
        "deduction_total": round(sum(money(record.get("deduction_total")) for record in records), 2),
        "net_pay_total": round(sum(money(record.get("net_pay")) for record in records), 2),
        "employer_cost_total": round(sum(money(record.get("employer_cost_total")) for record in records), 2),
    }


def append_audit(
    module: str,
    record_id: str,
    action: str,
    user: str,
    before_value: object,
    after_value: object,
    **context: object,
) -> None:
    audit = {
        "id": str(uuid.uuid4()),
        "audit_id": str(uuid.uuid4()),
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": user or "local_admin",
        "timestamp": now_iso(),
        "before_value": before_value,
        "after_value": after_value,
    }
    audit.update({key: value for key, value in context.items() if value not in (None, "")})
    append_json_record(AUDIT_FILE, audit)


def normalize_salary(payload: dict, existing: dict | None = None) -> dict:
    record = dict(existing or {})
    record.update(payload)

    for field in MONEY_FIELDS:
        record[field] = money(record.get(field, 0))

    gross_salary = sum(
        record[field]
        for field in (
            "base_salary",
            "position_allowance",
            "commute_allowance",
            "housing_allowance",
            "other_allowance",
            "overtime_pay",
        )
    )
    total_deductions = sum(
        record[field]
        for field in (
            "health_insurance",
            "pension_insurance",
            "employment_insurance",
            "income_tax",
            "resident_tax",
            "other_deduction",
        )
    )
    record["gross_salary"] = round(gross_salary, 2)
    record["total_deductions"] = round(total_deductions, 2)
    record["net_salary"] = round(gross_salary - total_deductions, 2)
    record.setdefault("currency", "JPY")
    record.setdefault("country", "JP")
    record.setdefault("status", "draft")
    return record


def normalize_contract_snapshot(payload: dict, existing: dict | None = None) -> dict:
    existing_snapshot = dict((existing or {}).get("contract_snapshot") or {})
    return {
        "contract_start_date": clean_text(payload.get("contract_start_date") or existing_snapshot.get("contract_start_date")),
        "contract_end_date": clean_text(payload.get("contract_end_date") or existing_snapshot.get("contract_end_date")),
        "employment_start_date": clean_text(payload.get("employment_start_date") or existing_snapshot.get("employment_start_date")),
        "employment_end_date": clean_text(payload.get("employment_end_date") or existing_snapshot.get("employment_end_date")),
        "probation_end_date": clean_text(payload.get("probation_end_date") or existing_snapshot.get("probation_end_date")),
        "contract_type": clean_text(payload.get("contract_type") or existing_snapshot.get("contract_type") or payload.get("employment_type") or (existing or {}).get("employment_type") or "regular"),
    }


def normalize_salary_calculation_rule(payload: dict, existing: dict | None = None) -> dict:
    existing_rule = dict((existing or {}).get("salary_calculation_rule") or {})
    rule_type = clean_text(payload.get("rule_type") or payload.get("salary_rule_type") or existing_rule.get("rule_type") or "monthly_fixed")
    if rule_type not in SALARY_RULE_TYPES:
        raise ValueError("salary rule_type must be monthly_fixed, monthly_prorated, hourly, or daily")
    base_salary = money(payload.get("base_salary", (existing or {}).get("base_salary", existing_rule.get("base_rate", 0))))
    base_rate = money(payload.get("base_rate", existing_rule.get("base_rate", base_salary))) or base_salary
    return {
        "rule_type": rule_type,
        "pay_unit": clean_text(payload.get("pay_unit") or existing_rule.get("pay_unit") or {"hourly": "hour", "daily": "day"}.get(rule_type, "month")),
        "base_rate": base_rate,
        "hourly_rate": money(payload.get("hourly_rate", existing_rule.get("hourly_rate", base_salary if rule_type == "hourly" else 0))),
        "daily_rate": money(payload.get("daily_rate", existing_rule.get("daily_rate", base_salary if rule_type == "daily" else 0))),
        "standard_hours_per_month": money(payload.get("standard_hours_per_month", existing_rule.get("standard_hours_per_month", 160))),
        "standard_days_per_month": money(payload.get("standard_days_per_month", existing_rule.get("standard_days_per_month", 20))),
        "actual_work_hours": money(payload.get("actual_work_hours", existing_rule.get("actual_work_hours", 0))),
        "actual_work_days": money(payload.get("actual_work_days", existing_rule.get("actual_work_days", 0))),
        "proration_method": clean_text(payload.get("proration_method") or existing_rule.get("proration_method") or "calendar_days"),
        "rounding_method": clean_text(payload.get("rounding_method") or existing_rule.get("rounding_method") or "round_half_up"),
        "overtime_eligible": bool(payload.get("overtime_eligible", existing_rule.get("overtime_eligible", rule_type in {"monthly_fixed", "monthly_prorated", "hourly"}))),
    }


def salary_master_completeness(profile: dict) -> dict:
    missing = []
    rule = dict(profile.get("salary_calculation_rule") or {})
    rule_type = clean_text(rule.get("rule_type") or profile.get("rule_type") or "monthly_fixed")
    if rule_type not in SALARY_RULE_TYPES:
        missing.append("salary_calculation_rule.rule_type")
    if rule_type in {"monthly_fixed", "monthly_prorated"} and money(profile.get("base_salary", rule.get("base_rate", 0))) <= 0:
        missing.append("base_salary")
    if rule_type == "hourly" and money(rule.get("hourly_rate", 0)) <= 0:
        missing.append("salary_calculation_rule.hourly_rate")
    if rule_type == "daily" and money(rule.get("daily_rate", 0)) <= 0:
        missing.append("salary_calculation_rule.daily_rate")
    if not clean_text(profile.get("effective_from")):
        missing.append("effective_from")
    if not clean_text(profile.get("salary_type")):
        missing.append("salary_type")
    return {"pay_complete": not missing, "missing_fields": missing}


def normalize_salary_master(payload: dict, existing: dict | None = None) -> dict:
    country_code = normalize_country_code(payload.get("country_code") or payload.get("country") or (existing or {}).get("country_code"))
    entity = entity_snapshot(payload.get("entity_id") or (existing or {}).get("entity_id"), country_code)
    employee_id = clean_text(payload.get("employee_id") or (existing or {}).get("employee_id"))
    if not employee_id:
        raise ValueError("employee_id is required")

    record = dict(existing or {})
    record.update(payload)
    record["profile_id"] = record.get("profile_id") or f"SM-{country_code}-{entity['entity_id']}-{employee_id}"
    record["employee_id"] = employee_id
    record["employee_no"] = clean_text(record.get("employee_no") or record.get("employee_number") or employee_id)
    record["employee_name"] = clean_text(record.get("employee_name") or record.get("display_name") or employee_id)
    record["country_code"] = country_code
    record["payroll_system_code"] = payroll_system_code(country_code)
    record["payroll_area_code"] = payroll_area_code(country_code)
    record["legal_entity_id"] = entity["entity_id"]
    record["entity_id"] = entity["entity_id"]
    record["entity_snapshot"] = entity
    record["currency"] = entity["currency"]
    record["salary_type"] = clean_text(record.get("salary_type") or "monthly")
    record["employment_type"] = clean_text(record.get("employment_type") or "regular")
    record["work_city"] = clean_text(record.get("work_city"))
    record["effective_from"] = clean_text(record.get("effective_from") or "2026-01-01")
    record["effective_to"] = clean_text(record.get("effective_to"))
    record["rule_version_id"] = clean_text(record.get("rule_version_id")) or default_rule_version_id(country_code, record["effective_from"][:7])
    record["status"] = clean_text(record.get("status") or (existing or {}).get("status") or DRAFT_SALARY_STATUS)

    fixed_allowances = dict(record.get("fixed_allowances") or {})
    for field in ("position_allowance", "commute_allowance", "housing_allowance", "other_allowance"):
        fixed_allowances[field] = money(record.get(field, fixed_allowances.get(field, 0)))
        record.pop(field, None)
    record["base_salary"] = money(record.get("base_salary", 0))
    record["fixed_allowances"] = fixed_allowances
    record["contract_snapshot"] = normalize_contract_snapshot(record, existing)
    record["salary_calculation_rule"] = normalize_salary_calculation_rule(record, existing)
    record["payroll_flags"] = dict(record.get("payroll_flags") or {})
    record["country_profile"] = dict(record.get("country_profile") or {})
    record["salary_profile_completeness"] = salary_master_completeness(record)
    requested_status = clean_text(payload.get("status"))
    if requested_status == ACTIVE_SALARY_STATUS and not record["salary_profile_completeness"]["pay_complete"]:
        missing = ", ".join(record["salary_profile_completeness"]["missing_fields"])
        raise ValueError(f"Cannot activate salary profile until required pay fields are complete: {missing}")
    return record


def validate_batch_unique(country_code: str, entity_id: str, payroll_month: str, payroll_type: str, batch_version: int) -> None:
    for batch in read_json(PAYROLL_BATCHES_FILE):
        if (
            batch.get("country_code") == country_code
            and batch.get("entity_id") == entity_id
            and batch.get("payroll_month") == payroll_month
            and batch.get("payroll_type") == payroll_type
            and int(batch.get("batch_version", 1)) == batch_version
            and batch.get("status") in ACTIVE_BATCH_STATUSES
        ):
            raise ValueError("Active payroll batch already exists for this country/entity/month/type/version")


def create_batch(payload: dict) -> dict:
    country_code = normalize_country_code(payload.get("country_code") or payload.get("country"))
    entity = entity_snapshot(payload.get("entity_id"), country_code)
    payroll_month = validate_payroll_month(payload.get("payroll_month"))
    payroll_type = clean_text(payload.get("payroll_type") or "regular")
    batch_version = int(payload.get("batch_version") or 1)
    validate_batch_unique(country_code, entity["entity_id"], payroll_month, payroll_type, batch_version)
    batch_id = make_batch_id(country_code, entity["entity_id"], payroll_month, batch_version)
    created_at = now_iso()
    batch = {
        "batch_id": batch_id,
        "country_code": country_code,
        "payroll_system_code": payroll_system_code(country_code),
        "payroll_area_code": payroll_area_code(country_code),
        "rule_version_id": clean_text(payload.get("rule_version_id")) or default_rule_version_id(country_code, payroll_month),
        "entity_id": entity["entity_id"],
        "legal_entity_id": entity["entity_id"],
        "entity_snapshot": entity,
        "currency": entity["currency"],
        "payroll_month": payroll_month,
        "period_start": clean_text(payload.get("period_start")) or f"{payroll_month}-01",
        "period_end": clean_text(payload.get("period_end")),
        "payment_date": clean_text(payload.get("payment_date")),
        "payroll_type": payroll_type,
        "batch_version": batch_version,
        "status": "draft_created",
        "employee_count": 0,
        "gross_pay_total": 0.0,
        "deduction_total": 0.0,
        "net_pay_total": 0.0,
        "employer_cost_total": 0.0,
        "created_by": clean_text(payload.get("user") or "local_admin"),
        "created_at": created_at,
        "updated_at": created_at,
        "notes": clean_text(payload.get("notes")),
        "first_confirmed_at": "",
        "second_confirmed_at": "",
        "finalized_at": "",
    }
    append_json_record(PAYROLL_BATCHES_FILE, batch)
    append_audit("salary", batch_id, "payroll_batch_created", batch["created_by"], None, batch, submodule="payroll_batch", batch_id=batch_id, country_code=country_code, entity_id=entity["entity_id"])
    return batch


def salary_profile_batch_validation(profile: dict, batch: dict) -> tuple[bool, list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    payroll_month = batch.get("payroll_month", "")
    employee_id = clean_text(profile.get("employee_id") or "unknown employee")
    if profile.get("status") not in PAYROLL_ELIGIBLE_SALARY_STATUSES:
        errors.append(f"{employee_id}: salary profile status is {profile.get('status') or 'blank'}, not active")
    completeness = salary_master_completeness(profile)
    if not completeness["pay_complete"]:
        errors.append(f"{employee_id}: salary profile is pay-incomplete ({', '.join(completeness['missing_fields'])})")
    if profile.get("country_code") != batch.get("country_code") or profile.get("entity_id") != batch.get("entity_id"):
        errors.append(f"{employee_id}: salary profile country/entity does not match batch")
    effective_to = clean_text(profile.get("effective_to"))
    if effective_to and effective_to[:7] < payroll_month:
        errors.append(f"{employee_id}: salary profile effective_to {effective_to} is before payroll month {payroll_month}")
    effective_from = clean_text(profile.get("effective_from"))
    if effective_from and effective_from[:7] > payroll_month:
        errors.append(f"{employee_id}: salary profile effective_from {effective_from} is after payroll month {payroll_month}")

    period_start, period_end = payroll_period(batch)
    contract = dict(profile.get("contract_snapshot") or {})
    contract_start = parse_date(contract.get("contract_start_date") or contract.get("employment_start_date"))
    contract_end = parse_date(contract.get("contract_end_date") or contract.get("employment_end_date"))
    if contract_end and contract_end < period_start:
        errors.append(f"{employee_id}: contract ended on {contract_end.isoformat()} before payroll period {period_start.isoformat()}")
    if contract_start and contract_start > period_end:
        errors.append(f"{employee_id}: contract starts on {contract_start.isoformat()} after payroll period {period_end.isoformat()}")
    if contract_start and period_start <= contract_start <= period_end:
        warnings.append(f"{employee_id}: contract starts during this payroll period on {contract_start.isoformat()}; prorated calculation may be required")
    if contract_end and period_start <= contract_end <= period_end:
        warnings.append(f"{employee_id}: contract ends during this payroll period on {contract_end.isoformat()}; prorated calculation may be required")
    if not contract_start:
        warnings.append(f"{employee_id}: contract_start_date is missing; confirm payroll period eligibility")
    return not errors, warnings, errors


def salary_profiles_for_batch(batch: dict) -> list[dict]:
    profiles = []
    for profile in read_json(SALARY_MASTER_FILE):
        eligible, _, _ = salary_profile_batch_validation(profile, batch)
        if eligible:
            profiles.append(profile)
    return profiles


def country_for_entity(entity_id: object) -> str:
    entity = MASTER_ENTITIES.get(clean_text(entity_id))
    return entity.get("country_code", "") if entity else ""


def normalize_employment_type_for_payroll(value: object, nationality: object = "") -> str:
    raw = clean_text(value).lower().replace("-", "_").replace(" ", "_")
    if raw in {"haken", "dispatch", "dispatched"}:
        return "haken"
    if raw in {"contract", "contractor", "fixed_term"}:
        return "contract"
    if raw in {"part_time", "parttime", "アルバイト"}:
        return "part_time"
    if raw in {"foreign_national", "foreigner"}:
        return "foreign_national"
    if clean_text(nationality) and clean_text(nationality).lower() not in {"japan", "japanese", "日本"}:
        return "foreign_national"
    return "regular"


def employeeadmin_name(employee: dict) -> str:
    return clean_text(
        employee.get("display_name")
        or employee.get("employee_name")
        or get_nested(employee, "profile.name.display_name")
        or get_nested(employee, "profile.name.romaji_name")
        or employee.get("employee_id")
    )


def flatten_employeeadmin_employee(employee: dict) -> dict:
    employment = employee.get("employment") if isinstance(employee.get("employment"), dict) else {}
    payroll = employee.get("payroll") if isinstance(employee.get("payroll"), dict) else {}
    profile = employee.get("profile") if isinstance(employee.get("profile"), dict) else {}
    address = profile.get("address") if isinstance(profile.get("address"), dict) else {}
    entity_id = clean_text(employee.get("entity_id") or employment.get("entity_id"))
    entity_country_code = country_for_entity(entity_id)
    country_code = clean_text(entity_country_code or employee.get("country_code") or employment.get("country_code") or employee.get("work_country") or employment.get("work_country"))
    if country_code:
        country_code = normalize_country_code(country_code)
    employee_no = clean_text(employee.get("employee_no") or employee.get("employee_number") or employee.get("employee_id"))
    salary_amount = payroll.get("salary_amount_yen", employee.get("base_salary", 0))
    commute_allowance = payroll.get("transportation_allowance_yen", employee.get("commute_allowance", 0))
    status = clean_text(employee.get("status") or employment.get("status") or "active").lower()
    return {
        "employee_id": clean_text(employee.get("employee_id")),
        "employee_no": employee_no,
        "employee_number": employee_no,
        "employee_name": employeeadmin_name(employee),
        "display_name": employeeadmin_name(employee),
        "email": clean_text(employee.get("email") or get_nested(employee, "profile.email")),
        "entity_id": entity_id,
        "entity_name": clean_text(employee.get("entity_name") or employee.get("entity_label") or MASTER_ENTITIES.get(entity_id, {}).get("entity_name_local", "")),
        "department": clean_text(employee.get("department") or employee.get("department_label") or employment.get("department")),
        "department_id": clean_text(employee.get("department_id") or employment.get("department_id")),
        "team_id": clean_text(employee.get("team_id") or employment.get("team_id")),
        "team_name": clean_text(employee.get("team_name") or employee.get("team_label")),
        "employment_type": normalize_employment_type_for_payroll(employee.get("employment_type") or employment.get("employment_type"), get_nested(employee, "profile.nationality")),
        "source_employment_type": clean_text(employee.get("employment_type") or employment.get("employment_type")),
        "country_code": country_code,
        "work_country": clean_text(employee.get("work_country") or employment.get("work_country") or country_code),
        "work_city": clean_text(employee.get("work_city") or employment.get("office_location") or address.get("city")),
        "business_line": clean_text(employee.get("business_line") or employment.get("business_line")),
        "position": clean_text(employee.get("position") or employment.get("position")),
        "office_location": clean_text(employment.get("office_location")),
        "contract_start_date": clean_text(employee.get("contract_start_date") or employment.get("contract_start_date") or employment.get("start_date") or employee.get("join_date") or employment.get("join_date")),
        "contract_end_date": clean_text(employee.get("contract_end_date") or employment.get("contract_end_date") or employment.get("end_date") or employee.get("resign_date") or employment.get("resign_date")),
        "employment_start_date": clean_text(employee.get("employment_start_date") or employment.get("employment_start_date") or employee.get("join_date") or employment.get("join_date") or employment.get("start_date")),
        "employment_end_date": clean_text(employee.get("employment_end_date") or employment.get("employment_end_date") or employee.get("resign_date") or employment.get("resign_date") or employment.get("end_date")),
        "probation_end_date": clean_text(employee.get("probation_end_date") or employment.get("probation_end_date")),
        "contract_type": clean_text(employee.get("contract_type") or employment.get("contract_type") or employee.get("employment_type") or employment.get("employment_type") or "regular"),
        "status": status or "active",
        "base_salary": money(salary_amount),
        "commute_allowance": money(commute_allowance),
        "payroll_ready": bool(employee.get("payroll_ready")),
        "payroll_readiness_status": clean_text(employee.get("payroll_readiness_status") or "local_employee_master"),
        "payroll_readiness_percent": employee.get("payroll_readiness_percent", 0),
        "missing_payroll_readiness_fields": list(employee.get("missing_payroll_readiness_fields") or []),
        "bank_account_snapshot": payroll.get("bank", {}),
        "source_system": "TAC-employeeadmin",
        "source_generated_at": now_iso(),
    }


def local_employeeadmin_payroll_employees(country_code: str = "", entity_id: str = "", employee_ids: set[str] | None = None, query_text: str = "") -> list[dict]:
    if not EMPLOYEEADMIN_LOCAL_FILE.exists():
        return []
    employees = []
    query_key = clean_text(query_text).casefold()
    for raw_employee in read_json(EMPLOYEEADMIN_LOCAL_FILE):
        if not isinstance(raw_employee, dict):
            continue
        if bool(get_nested(raw_employee, "metadata.deleted", False)):
            continue
        employee = flatten_employeeadmin_employee(raw_employee)
        if employee.get("status") and employee["status"] not in {"active", "onboarding", "probation"}:
            continue
        if employee_ids and employee.get("employee_id") not in employee_ids:
            continue
        if entity_id and employee.get("entity_id") != entity_id:
            continue
        if country_code and employee.get("country_code") != country_code:
            continue
        searchable = " ".join(clean_text(employee.get(key)) for key in ("employee_id", "employee_no", "employee_name", "email", "entity_id", "department", "work_city")).casefold()
        if query_key and query_key not in searchable:
            continue
        employees.append(employee)
    employees.sort(key=lambda item: (item.get("entity_id", ""), item.get("employee_no", ""), item.get("employee_name", "")))
    return employees


def fetch_employeeadmin_payroll_employees(batch: dict, session_id: str, employee_ids: set[str] | None = None) -> tuple[list[dict], list[str]]:
    country_code = clean_text(batch.get("country_code"))
    entity_id = clean_text(batch.get("entity_id"))
    warnings: list[str] = []
    if not session_id:
        local_employees = local_employeeadmin_payroll_employees(country_code, entity_id, employee_ids)
        if local_employees:
            return local_employees, ["Using local TAC-employeeadmin JSON because User_admin session is unavailable."]
        return [], ["EmployeeAdmin session is unavailable and no local employee records matched; using local salary master fallback if allowed."]
    query = urlencode({"entity_id": entity_id})
    request = Request(
        f"{EMPLOYEEADMIN_INTERNAL_BASE_URL}/api/payroll/employees?{query}",
        headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=4) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        local_employees = local_employeeadmin_payroll_employees(country_code, entity_id, employee_ids)
        return local_employees, [f"EmployeeAdmin returned HTTP {exc.code}; using local employee JSON if matched."]
    except (OSError, URLError, json.JSONDecodeError) as exc:
        local_employees = local_employeeadmin_payroll_employees(country_code, entity_id, employee_ids)
        return local_employees, [f"EmployeeAdmin unavailable: {exc}; using local employee JSON if matched."]
    employees = payload.get("employees", []) if isinstance(payload, dict) else []
    if not isinstance(employees, list):
        return local_employeeadmin_payroll_employees(country_code, entity_id, employee_ids), ["EmployeeAdmin response did not include an employees array; using local employee JSON if matched."]
    filtered = []
    for employee in employees:
        if not isinstance(employee, dict):
            continue
        flattened = flatten_employeeadmin_employee(employee)
        employee_id = flattened["employee_id"]
        if employee_ids and employee_id not in employee_ids:
            continue
        if flattened.get("entity_id") != entity_id:
            continue
        if flattened.get("country_code") and flattened.get("country_code") != country_code:
            continue
        filtered.append(flattened)
    if filtered:
        return filtered, warnings
    return local_employeeadmin_payroll_employees(country_code, entity_id, employee_ids), ["No live EmployeeAdmin employees matched; using local employee JSON if matched."]


def employeeadmin_snapshot(employee: dict) -> dict:
    return {
        "employee_id": clean_text(employee.get("employee_id")),
        "employee_no": clean_text(employee.get("employee_no") or employee.get("employee_number") or employee.get("employee_id")),
        "employee_name": clean_text(employee.get("display_name") or employee.get("employee_name") or employee.get("employee_id")),
        "email": clean_text(employee.get("email")),
        "entity_id": clean_text(employee.get("entity_id")),
        "entity_name": clean_text(employee.get("entity_name") or employee.get("entity_label")),
        "department": clean_text(employee.get("department") or employee.get("department_label")),
        "department_id": clean_text(employee.get("department_id")),
        "team_id": clean_text(employee.get("team_id")),
        "team_name": clean_text(employee.get("team_label")),
        "employment_type": clean_text(employee.get("employment_type") or "regular"),
        "work_country": clean_text(employee.get("work_country") or employee.get("country_code")),
        "work_city": clean_text(employee.get("work_city") or employee.get("office_location")),
        "business_line": clean_text(employee.get("business_line")),
        "contract_start_date": clean_text(employee.get("contract_start_date")),
        "contract_end_date": clean_text(employee.get("contract_end_date")),
        "employment_start_date": clean_text(employee.get("employment_start_date")),
        "employment_end_date": clean_text(employee.get("employment_end_date")),
        "probation_end_date": clean_text(employee.get("probation_end_date")),
        "contract_type": clean_text(employee.get("contract_type")),
        "payroll_ready": bool(employee.get("payroll_ready")),
        "payroll_readiness_status": clean_text(employee.get("payroll_readiness_status")),
        "payroll_readiness_percent": employee.get("payroll_readiness_percent", 0),
        "missing_payroll_readiness_fields": list(employee.get("missing_payroll_readiness_fields") or []),
        "source_system": "TAC-employeeadmin",
        "source_generated_at": now_iso(),
    }


def merge_employeeadmin_with_salary_master(batch: dict, employees: list[dict], profiles: list[dict], all_profiles: list[dict] | None = None) -> tuple[list[dict], list[str]]:
    profile_by_employee = {profile.get("employee_id"): profile for profile in profiles}
    all_profile_by_employee = {profile.get("employee_id"): profile for profile in (all_profiles or profiles)}
    merged = []
    warnings = []
    for employee in employees:
        snapshot = employeeadmin_snapshot(employee)
        employee_id = snapshot["employee_id"]
        profile = profile_by_employee.get(employee_id)
        if not profile:
            candidate = all_profile_by_employee.get(employee_id)
            if candidate:
                _, candidate_warnings, candidate_errors = salary_profile_batch_validation(candidate, batch)
                warnings.extend(f"Skipped {employee_id}: {message}" for message in candidate_errors)
                warnings.extend(f"Warning {employee_id}: {message}" for message in candidate_warnings)
            else:
                warnings.append(f"Skipped {employee_id or 'unknown employee'}: salary master profile is missing for {batch.get('payroll_month')}.")
            continue
        enriched = dict(profile)
        enriched["employee_no"] = snapshot.get("employee_no") or enriched.get("employee_no")
        enriched["employee_name"] = snapshot.get("employee_name") or enriched.get("employee_name")
        enriched["employeeadmin_snapshot"] = snapshot
        enriched["department"] = snapshot.get("department", "")
        enriched["work_city"] = snapshot.get("work_city") or enriched.get("work_city", "")
        enriched["employment_type"] = snapshot.get("employment_type") or enriched.get("employment_type", "regular")
        if snapshot.get("contract_start_date") or snapshot.get("contract_end_date") or snapshot.get("employment_start_date") or snapshot.get("employment_end_date"):
            contract_snapshot = dict(enriched.get("contract_snapshot") or {})
            for field in ("contract_start_date", "contract_end_date", "employment_start_date", "employment_end_date", "probation_end_date", "contract_type"):
                if snapshot.get(field):
                    contract_snapshot[field] = snapshot[field]
            enriched["contract_snapshot"] = contract_snapshot
        _, profile_warnings, _ = salary_profile_batch_validation(enriched, batch)
        warnings.extend(profile_warnings)
        merged.append(enriched)
    return merged, warnings


def salary_profiles_with_employeeadmin(batch: dict, session_id: str = "", allow_fallback: bool = True, requested_ids: set[str] | None = None) -> tuple[list[dict], str, list[str]]:
    all_profiles = read_json(SALARY_MASTER_FILE)
    local_profiles = [profile for profile in all_profiles if salary_profile_batch_validation(profile, batch)[0]]
    if requested_ids:
        local_profiles = [profile for profile in local_profiles if profile.get("employee_id") in requested_ids]
        all_profiles = [profile for profile in all_profiles if profile.get("employee_id") in requested_ids]
    employees, warnings = fetch_employeeadmin_payroll_employees(batch, session_id, requested_ids)
    if employees:
        merged, merge_warnings = merge_employeeadmin_with_salary_master(batch, employees, local_profiles, all_profiles)
        warnings.extend(merge_warnings)
        if merged:
            return merged, "employeeadmin", warnings
    if allow_fallback:
        return local_profiles, "salary_master_fallback", warnings
    if warnings:
        raise ValueError("; ".join(warnings))
    return [], "employeeadmin", ["No EmployeeAdmin employees matched this payroll batch."]


def employeeadmin_employees_payload(query: dict[str, list[str]], session_id: str = "") -> dict:
    country_filter = clean_text(query.get("country_code", [""])[0])
    if country_filter:
        country_filter = normalize_country_code(country_filter)
    entity_filter = clean_text(query.get("entity_id", [""])[0])
    q = clean_text(query.get("q", [""])[0])
    employees: list[dict] = []
    warnings: list[str] = []
    if session_id and entity_filter:
        batch_like = {"country_code": country_filter or country_for_entity(entity_filter), "entity_id": entity_filter}
        employees, warnings = fetch_employeeadmin_payroll_employees(batch_like, session_id)
        if q:
            query_key = q.casefold()
            employees = [employee for employee in employees if query_key in " ".join(clean_text(employee.get(key)) for key in ("employee_id", "employee_no", "employee_name", "email", "department", "work_city")).casefold()]
    if not employees:
        employees = local_employeeadmin_payroll_employees(country_filter, entity_filter, query_text=q)
        if not warnings:
            warnings = ["Using local TAC-employeeadmin employee JSON."]
    return {"source": "TAC-employeeadmin", "generated_at": now_iso(), "warnings": warnings, "count": len(employees), "employees": employees}


def salary_master_payload_from_employeeadmin(employee: dict, effective_from: str, existing: dict | None = None, overwrite_pay_values: bool = False, target_status: str = DRAFT_SALARY_STATUS) -> dict:
    pay_hint = {
        "base_salary": money(employee.get("base_salary", 0)),
        "commute_allowance": money(employee.get("commute_allowance", 0)),
        "source_system": employee.get("source_system", "TAC-employeeadmin"),
        "source_generated_at": employee.get("source_generated_at", now_iso()),
    }
    payload = {
        "country_code": employee.get("country_code") or country_for_entity(employee.get("entity_id")),
        "payroll_system_code": payroll_system_code(employee.get("country_code") or country_for_entity(employee.get("entity_id"))),
        "payroll_area_code": payroll_area_code(employee.get("country_code") or country_for_entity(employee.get("entity_id"))),
        "entity_id": employee.get("entity_id"),
        "legal_entity_id": employee.get("entity_id"),
        "employee_id": employee.get("employee_id"),
        "employee_no": employee.get("employee_no") or employee.get("employee_number"),
        "employee_name": employee.get("employee_name") or employee.get("display_name"),
        "employment_type": employee.get("employment_type") or "regular",
        "work_city": employee.get("work_city"),
        "salary_type": "monthly",
        "effective_from": effective_from,
        "status": target_status,
        "department": employee.get("department", ""),
        "department_id": employee.get("department_id", ""),
        "position": employee.get("position", ""),
        "contract_start_date": employee.get("contract_start_date", ""),
        "contract_end_date": employee.get("contract_end_date", ""),
        "employment_start_date": employee.get("employment_start_date", ""),
        "employment_end_date": employee.get("employment_end_date", ""),
        "probation_end_date": employee.get("probation_end_date", ""),
        "contract_type": employee.get("contract_type", ""),
        "rule_type": "monthly_fixed",
        "pay_unit": "month",
        "proration_method": "calendar_days",
        "rounding_method": "round_half_up",
        "salary_profile_source": "employeeadmin_import",
        "salary_profile_stage": "preliminary" if target_status == DRAFT_SALARY_STATUS else "reviewed",
        "employeeadmin_snapshot": employeeadmin_snapshot(employee),
        "bank_account_snapshot": employee.get("bank_account_snapshot", {}),
        "employeeadmin_pay_hint": pay_hint,
    }
    if not existing or overwrite_pay_values:
        payload.update({
            "base_salary": employee.get("base_salary", 0),
            "commute_allowance": employee.get("commute_allowance", 0),
            "position_allowance": 0,
            "housing_allowance": 0,
            "other_allowance": 0,
        })
    return payload


def import_salary_master_from_employeeadmin(payload: dict, session_id: str = "") -> dict:
    country_code = clean_text(payload.get("country_code"))
    if country_code:
        country_code = normalize_country_code(country_code)
    entity_id = clean_text(payload.get("entity_id"))
    effective_from = clean_text(payload.get("effective_from") or "2026-01-01")
    overwrite_pay_values = bool(payload.get("overwrite_pay_values"))
    update_existing_drafts = bool(payload.get("update_existing_drafts", True))
    employee_query_payload = employeeadmin_employees_payload({"country_code": [country_code], "entity_id": [entity_id], "q": [clean_text(payload.get("q"))]}, session_id)
    employees = employee_query_payload["employees"]
    records = read_json(SALARY_MASTER_FILE)
    existing_by_profile = {record.get("profile_id"): index for index, record in enumerate(records)}
    created: list[dict] = []
    updated: list[dict] = []
    active_preserved: list[dict] = []
    skipped: list[str] = []
    warnings = list(employee_query_payload.get("warnings", []))
    for employee in employees:
        try:
            profile_id = f"SM-{employee.get('country_code')}-{employee.get('entity_id')}-{employee.get('employee_id')}"
            existing_index = existing_by_profile.get(profile_id)
            existing = records[existing_index] if existing_index is not None else None
            if existing and existing.get("status") == ACTIVE_SALARY_STATUS:
                profile_payload = salary_master_payload_from_employeeadmin(employee, effective_from, existing, False, target_status=ACTIVE_SALARY_STATUS)
                profile_payload.pop("status", None)
                for pay_field in ("base_salary", "position_allowance", "commute_allowance", "housing_allowance", "other_allowance"):
                    profile_payload.pop(pay_field, None)
                profile = normalize_salary_master(profile_payload, existing)
                profile["profile_id"] = existing["profile_id"]
                profile["created_at"] = existing.get("created_at", now_iso())
                profile["updated_at"] = now_iso()
                records[existing_index] = profile
                active_preserved.append(profile)
                warnings.append(f"Preserved active salary profile for {employee.get('employee_id')}; EmployeeAdmin identity snapshot refreshed only.")
                continue
            if existing and existing.get("status") == DRAFT_SALARY_STATUS and not update_existing_drafts:
                skipped.append(f"{employee.get('employee_id')}: draft salary profile already exists")
                continue
            profile_payload = salary_master_payload_from_employeeadmin(employee, effective_from, existing, overwrite_pay_values, target_status=DRAFT_SALARY_STATUS)
            profile = normalize_salary_master(profile_payload, existing)
            if existing_index is None:
                profile["created_at"] = now_iso()
                profile["updated_at"] = profile["created_at"]
                existing_by_profile[profile["profile_id"]] = len(records)
                records.append(profile)
                created.append(profile)
            else:
                profile["profile_id"] = existing["profile_id"]
                profile["created_at"] = existing.get("created_at", now_iso())
                profile["updated_at"] = now_iso()
                records[existing_index] = profile
                updated.append(profile)
        except ValueError as exc:
            skipped.append(f"{employee.get('employee_id') or employee.get('employee_no')}: {exc}")
    write_json(SALARY_MASTER_FILE, records)
    actor = clean_text(payload.get("user") or "local_admin")
    summary = {
        "source": employee_query_payload.get("source"),
        "created_count": len(created),
        "created_draft_count": len(created),
        "updated_count": len(updated),
        "updated_draft_count": len(updated),
        "active_preserved_count": len(active_preserved),
        "skipped_count": len(skipped),
        "employee_source_count": len(employees),
        "country_code": country_code,
        "payroll_system_code": payroll_system_code(country_code) if country_code else "",
        "entity_id": entity_id,
        "legal_entity_id": entity_id,
        "warnings": warnings,
        "skipped": skipped,
    }
    append_audit("salary", "salary_master", "salary_master_employeeadmin_imported", actor, None, summary, submodule="salary_master", country_code=country_code, entity_id=entity_id)
    return {**summary, "created": created, "updated": updated, "active_preserved": active_preserved}


def append_import_run(batch: dict, source: str, user: str, loaded_count: int, skipped_count: int, warnings: list[str], errors: list[str] | None = None) -> dict:
    import_run = {
        "import_run_id": next_sequence_id("IMP", batch.get("payroll_month", "0000-00"), read_json(PAYROLL_IMPORT_RUNS_FILE), "import_run_id"),
        "batch_id": batch.get("batch_id"),
        "import_type": "employee_master",
        "source_system": source,
        "source_record_count": loaded_count + skipped_count,
        "success_count": loaded_count,
        "warning_count": len(warnings),
        "error_count": len(errors or []),
        "warnings": warnings,
        "errors": errors or [],
        "imported_by": user,
        "imported_at": now_iso(),
        "notes": "Payroll employee snapshot load",
    }
    append_json_record(PAYROLL_IMPORT_RUNS_FILE, import_run)
    return import_run


def latest_import_run_for_batch(batch_id: str) -> dict | None:
    runs = [record for record in read_json(PAYROLL_IMPORT_RUNS_FILE) if record.get("batch_id") == batch_id]
    if not runs:
        return None
    return sorted(runs, key=lambda record: record.get("imported_at", ""), reverse=True)[0]


def parameter_applies_to_record(parameter: dict, record: dict) -> bool:
    if parameter.get("status") != "active":
        return False
    if parameter.get("country_code") != record.get("country_code"):
        return False
    parameter_entity = clean_text(parameter.get("entity_id"))
    if parameter_entity and parameter_entity != clean_text(record.get("entity_id")):
        return False
    parameter_rule = clean_text(parameter.get("rule_version_id"))
    record_rule = clean_text(record.get("rule_version_id"))
    if parameter_rule and record_rule and parameter_rule != record_rule:
        return False
    payroll_month = clean_text(record.get("payroll_month"))
    effective_start = clean_text(parameter.get("effective_start_date"))
    effective_end = clean_text(parameter.get("effective_end_date"))
    if effective_start and effective_start[:7] > payroll_month:
        return False
    if effective_end and effective_end[:7] < payroll_month:
        return False
    if record.get("country_code") == "CN":
        parameter_city = clean_text(parameter.get("city_code")).upper().replace("'", "")
        record_city = clean_text(record.get("cn_fields", {}).get("city_code") or record.get("cn_fields", {}).get("social_insurance_city") or record.get("cn_fields", {}).get("work_city")).upper().replace("'", "")
        if record_city == "XI'AN":
            record_city = "XIAN"
        if parameter_city and record_city and parameter_city != record_city:
            return False
    return True


def active_parameters_for_record(record: dict) -> list[dict]:
    parameters = [parameter for parameter in read_json(PAYROLL_PARAMETERS_FILE) if parameter_applies_to_record(parameter, record)]
    return sorted(parameters, key=lambda parameter: (clean_text(parameter.get("effective_start_date")), clean_text(parameter.get("updated_at"))), reverse=True)


def country_empty_deductions(country_code: str) -> dict:
    if country_code == "SG":
        return {"cpf_employee": 0.0, "other_deduction": 0.0, "income_tax": 0.0}
    if country_code == "CN":
        return {"social_insurance_employee": 0.0, "housing_fund_employee": 0.0, "individual_income_tax": 0.0, "other_deduction": 0.0}
    return {"health_insurance": 0.0, "pension_insurance": 0.0, "employment_insurance": 0.0, "income_tax": 0.0, "resident_tax": 0.0, "other_deduction": 0.0}


def country_empty_employer_costs(country_code: str) -> dict:
    if country_code == "SG":
        return {"cpf_employer": 0.0, "employer_other_cost": 0.0}
    if country_code == "CN":
        return {"social_insurance_employer": 0.0, "housing_fund_employer": 0.0, "employer_other_cost": 0.0}
    return {"employer_health_insurance": 0.0, "employer_pension_insurance": 0.0, "employer_employment_insurance": 0.0, "employer_workers_compensation": 0.0, "employer_other_cost": 0.0}


def create_payroll_row(batch: dict, profile: dict) -> dict:
    country_code = batch["country_code"]
    employee_id = profile["employee_id"]
    employee_snapshot_source = dict(profile.get("employeeadmin_snapshot") or {})
    contract_snapshot = dict(profile.get("contract_snapshot") or {})
    salary_rule_snapshot = dict(profile.get("salary_calculation_rule") or normalize_salary_calculation_rule(profile))
    earnings = {
        "base_salary": money(profile.get("base_salary")),
        "position_allowance": money(profile.get("fixed_allowances", {}).get("position_allowance")),
        "commute_allowance": money(profile.get("fixed_allowances", {}).get("commute_allowance")),
        "housing_allowance": money(profile.get("fixed_allowances", {}).get("housing_allowance")),
        "other_allowance": money(profile.get("fixed_allowances", {}).get("other_allowance")),
        "overtime_pay": money(profile.get("overtime_pay", 0)),
        "late_night_overtime_pay": money(profile.get("late_night_overtime_pay", 0)),
        "holiday_work_pay": money(profile.get("holiday_work_pay", 0)),
        "statutory_holiday_work_pay": money(profile.get("statutory_holiday_work_pay", 0)),
        "bonus": money(profile.get("bonus", 0)),
        "other_earnings": money(profile.get("other_earnings", 0)),
    }
    record = {
        "payroll_record_id": make_payroll_record_id(country_code, batch["entity_id"], batch["payroll_month"], employee_id, int(batch.get("batch_version", 1))),
        "batch_id": batch["batch_id"],
        "country_code": country_code,
        "payroll_system_code": batch.get("payroll_system_code") or payroll_system_code(country_code),
        "payroll_area_code": batch.get("payroll_area_code") or payroll_area_code(country_code),
        "rule_version_id": batch.get("rule_version_id") or default_rule_version_id(country_code, batch["payroll_month"]),
        "entity_id": batch["entity_id"],
        "legal_entity_id": batch["entity_id"],
        "entity_snapshot": batch.get("entity_snapshot", {}),
        "payroll_month": batch["payroll_month"],
        "currency": batch["currency"],
        "employee_id": employee_id,
        "employee_snapshot": {
            "employee_id": employee_id,
            "employee_no": employee_snapshot_source.get("employee_no") or profile.get("employee_no", employee_id),
            "employee_name": employee_snapshot_source.get("employee_name") or profile.get("employee_name", employee_id),
            "email": employee_snapshot_source.get("email", ""),
            "entity_id": employee_snapshot_source.get("entity_id") or batch["entity_id"],
            "entity_name": employee_snapshot_source.get("entity_name") or batch.get("entity_snapshot", {}).get("entity_name_local", ""),
            "employment_type": employee_snapshot_source.get("employment_type") or profile.get("employment_type", "regular"),
            "work_country": employee_snapshot_source.get("work_country") or country_code,
            "work_city": employee_snapshot_source.get("work_city") or profile.get("work_city", ""),
            "department": employee_snapshot_source.get("department") or profile.get("department", ""),
            "department_id": employee_snapshot_source.get("department_id", ""),
            "team_id": employee_snapshot_source.get("team_id", ""),
            "team_name": employee_snapshot_source.get("team_name", ""),
            "business_line": employee_snapshot_source.get("business_line", ""),
            "contract_start_date": employee_snapshot_source.get("contract_start_date") or contract_snapshot.get("contract_start_date", ""),
            "contract_end_date": employee_snapshot_source.get("contract_end_date") or contract_snapshot.get("contract_end_date", ""),
            "employment_start_date": employee_snapshot_source.get("employment_start_date") or contract_snapshot.get("employment_start_date", ""),
            "employment_end_date": employee_snapshot_source.get("employment_end_date") or contract_snapshot.get("employment_end_date", ""),
            "contract_type": employee_snapshot_source.get("contract_type") or contract_snapshot.get("contract_type", ""),
            "payroll_ready": employee_snapshot_source.get("payroll_ready", False),
            "payroll_readiness_status": employee_snapshot_source.get("payroll_readiness_status", "local_salary_master"),
            "payroll_readiness_percent": employee_snapshot_source.get("payroll_readiness_percent", 0),
            "missing_payroll_readiness_fields": employee_snapshot_source.get("missing_payroll_readiness_fields", []),
            "dispatch_client": profile.get("dispatch_client", ""),
            "bank_account_snapshot": profile.get("bank_account_snapshot", ""),
            "source_system": employee_snapshot_source.get("source_system", "TAC-salary salary_master"),
            "source_generated_at": employee_snapshot_source.get("source_generated_at", now_iso()),
        },
        "contract_snapshot": contract_snapshot,
        "salary_calculation_rule_snapshot": salary_rule_snapshot,
        "salary_profile_snapshot": profile,
        "earnings": earnings,
        "deductions": country_empty_deductions(country_code),
        "employer_costs": country_empty_employer_costs(country_code),
        "manual_adjustments": [],
        "manual_adjustments_total": 0.0,
        "gross_pay": 0.0,
        "deduction_total": 0.0,
        "net_pay": 0.0,
        "employer_cost_total": 0.0,
        "status": "loaded",
        "calculation_messages": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    if country_code == "JP":
        record["jp_fields"] = {
            "overtime_hours": money(profile.get("overtime_hours", 0)),
            "late_night_hours": money(profile.get("late_night_hours", 0)),
            "holiday_work_hours": money(profile.get("holiday_work_hours", 0)),
            "statutory_holiday_work_hours": money(profile.get("statutory_holiday_work_hours", 0)),
            "income_tax_manual": money(profile.get("income_tax", 0)),
            "resident_tax_manual": money(profile.get("resident_tax", 0)),
            "haken_assignment_id": profile.get("haken_assignment_id", ""),
            "dispatch_contract_reference": profile.get("dispatch_contract_reference", ""),
        }
    elif country_code == "SG":
        record["sg_fields"] = {
            "cpf_applicable": parse_bool(profile.get("cpf_applicable", True), True),
            "cpf_input_mode": clean_text(profile.get("cpf_input_mode") or "manual"),
            "cpf_ordinary_wage": money(profile.get("cpf_ordinary_wage", 0)),
            "cpf_additional_wage": money(profile.get("cpf_additional_wage", 0)),
            "cpf_employee": money(profile.get("cpf_employee", 0)),
            "cpf_employer": money(profile.get("cpf_employer", 0)),
            "cpf_manual_reason": clean_text(profile.get("cpf_manual_reason") or "Manual CPF entry pending validation"),
            "residency_status": clean_text(profile.get("residency_status")),
            "work_pass_type": clean_text(profile.get("work_pass_type")),
            "skill_development_levy": money(profile.get("skill_development_levy", 0)),
            "foreign_worker_levy": money(profile.get("foreign_worker_levy", 0)),
        }
        record["deductions"]["cpf_employee"] = record["sg_fields"]["cpf_employee"]
        record["employer_costs"]["cpf_employer"] = record["sg_fields"]["cpf_employer"]
        record["employer_costs"]["employer_other_cost"] = record["sg_fields"]["skill_development_levy"] + record["sg_fields"]["foreign_worker_levy"]
    elif country_code == "CN":
        city = clean_text(profile.get("city_code") or profile.get("work_city") or "").upper().replace("'", "")
        if city == "XI'AN":
            city = "XIAN"
        if city and city not in SUPPORTED_CN_CITIES:
            city = ""
        record["cn_fields"] = {
            "city_code": city,
            "work_city": profile.get("work_city", ""),
            "social_insurance_city": profile.get("social_insurance_city", profile.get("work_city", "")),
            "housing_fund_city": profile.get("housing_fund_city", profile.get("work_city", "")),
            "social_insurance_employee": money(profile.get("social_insurance_employee", 0)),
            "housing_fund_employee": money(profile.get("housing_fund_employee", 0)),
            "social_insurance_employer": money(profile.get("social_insurance_employer", 0)),
            "housing_fund_employer": money(profile.get("housing_fund_employer", 0)),
            "individual_income_tax": money(profile.get("individual_income_tax", 0)),
            "special_additional_deduction": money(profile.get("special_additional_deduction", 0)),
        }
        record["deductions"]["social_insurance_employee"] = record["cn_fields"]["social_insurance_employee"]
        record["deductions"]["housing_fund_employee"] = record["cn_fields"]["housing_fund_employee"]
        record["deductions"]["individual_income_tax"] = record["cn_fields"]["individual_income_tax"]
        record["employer_costs"]["social_insurance_employer"] = record["cn_fields"]["social_insurance_employer"]
        record["employer_costs"]["housing_fund_employer"] = record["cn_fields"]["housing_fund_employer"]
    return calculate_payroll_row(record)


def calculate_payroll_row(record: dict) -> dict:
    earnings = dict(record.get("earnings") or {})
    deductions = dict(record.get("deductions") or {})
    employer_costs = dict(record.get("employer_costs") or {})
    adjustments = list(record.get("manual_adjustments") or [])
    rule = dict(record.get("salary_calculation_rule_snapshot") or record.get("salary_profile_snapshot", {}).get("salary_calculation_rule") or {})
    rule_type = clean_text(rule.get("rule_type") or "monthly_fixed")
    messages = []
    contract_snapshot = dict(record.get("contract_snapshot") or record.get("salary_profile_snapshot", {}).get("contract_snapshot") or {})
    batch = batch_by_id(record.get("batch_id", "")) or {"payroll_month": record.get("payroll_month"), "period_start": record.get("period_start"), "period_end": record.get("period_end")}
    payable_days, period_days = payable_days_for_period(batch, contract_snapshot)
    calculation_basis = {
        "rule_type": rule_type,
        "period_days": period_days,
        "payable_days": payable_days,
        "actual_work_hours": money(rule.get("actual_work_hours", 0)),
        "actual_work_days": money(rule.get("actual_work_days", 0)),
    }
    if rule_type in {"monthly_fixed", "monthly_prorated"}:
        base_rate = money(rule.get("base_rate", earnings.get("base_salary", 0)))
        if rule_type == "monthly_prorated" or payable_days < period_days:
            earnings["base_salary"] = round(base_rate * payable_days / period_days, 2) if period_days else 0.0
            messages.append(f"Base salary prorated by calendar days: {payable_days}/{period_days}.")
        else:
            earnings["base_salary"] = base_rate
    elif rule_type == "hourly":
        actual_hours = money(rule.get("actual_work_hours", 0))
        hourly_rate = money(rule.get("hourly_rate", 0))
        if actual_hours <= 0:
            messages.append("Hourly salary rule requires actual_work_hours before calculation.")
            record["status"] = "validation_error"
        earnings["base_salary"] = round(actual_hours * hourly_rate, 2)
    elif rule_type == "daily":
        actual_days = money(rule.get("actual_work_days", 0))
        daily_rate = money(rule.get("daily_rate", 0))
        if actual_days <= 0:
            messages.append("Daily salary rule requires actual_work_days before calculation.")
            record["status"] = "validation_error"
        earnings["base_salary"] = round(actual_days * daily_rate, 2)
    else:
        messages.append(f"Unsupported salary rule_type: {rule_type}.")
        record["status"] = "validation_error"
    record["earnings"] = {key: money(value) for key, value in earnings.items()}
    record["deductions"] = {key: money(value) for key, value in deductions.items()}
    record["employer_costs"] = {key: money(value) for key, value in employer_costs.items()}
    record["calculation_basis"] = calculation_basis
    record["calculation_messages"] = list(record.get("calculation_messages") or []) + messages
    record = apply_country_engine(record, active_parameters_for_record(record))
    earnings = dict(record.get("earnings") or {})
    deductions = dict(record.get("deductions") or {})
    employer_costs = dict(record.get("employer_costs") or {})
    gross_pay = round(sum(money(earnings.get(field, 0)) for field in EARNING_FIELDS), 2)
    deduction_total = round(sum(money(deductions.get(field, 0)) for field in DEDUCTION_FIELDS), 2)
    manual_adjustments_total = round(sum(money(adjustment.get("amount", 0)) for adjustment in adjustments), 2)
    employer_costs_subtotal = round(sum(money(employer_costs.get(field, 0)) for field in EMPLOYER_COST_FIELDS), 2)
    record["earnings"] = {key: money(value) for key, value in earnings.items()}
    record["deductions"] = {key: money(value) for key, value in deductions.items()}
    record["employer_costs"] = {key: money(value) for key, value in employer_costs.items()}
    record["manual_adjustments_total"] = manual_adjustments_total
    record["gross_pay"] = gross_pay
    record["deduction_total"] = deduction_total
    record["net_pay"] = round(gross_pay - deduction_total + manual_adjustments_total, 2)
    record["employer_cost_total"] = round(gross_pay + employer_costs_subtotal, 2)
    record["calculated_at"] = now_iso()
    record["updated_at"] = record["calculated_at"]
    return record


def load_employees_for_batch(batch_id: str, payload: dict, session_id: str = "") -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Finalized or paid batch cannot load employees")
    requested_ids = {clean_text(item) for item in payload.get("employee_ids") or [] if clean_text(item)}
    allow_fallback = bool(payload.get("allow_salary_master_fallback", AUTH_ENFORCEMENT != "strict"))
    profiles, source, warnings = salary_profiles_with_employeeadmin(batch, session_id, allow_fallback=allow_fallback, requested_ids=requested_ids or None)
    record_path = payroll_record_file(batch["country_code"])
    records = read_json(record_path)
    existing_ids = {record.get("payroll_record_id") for record in records if record.get("batch_id") == batch_id}
    new_records = []
    for profile in profiles:
        row = create_payroll_row(batch, profile)
        if row["payroll_record_id"] in existing_ids:
            continue
        new_records.append(row)
        records.append(row)
    write_json(record_path, records)
    current_rows = batch_records(batch_id, batch["country_code"])
    totals = calculate_batch_totals(current_rows)
    skipped_existing = len(profiles) - len(new_records)
    import_run = append_import_run(batch, source, clean_text(payload.get("user") or "local_admin"), len(new_records), skipped_existing, warnings)
    updated_batch = update_batch(batch_id, {"status": "data_loaded", **totals, "last_employee_load_source": source, "last_employee_load_import_run_id": import_run["import_run_id"], "last_employee_load_warning_count": len(warnings)})
    append_audit("salary", batch_id, "payroll_employees_loaded", clean_text(payload.get("user") or "local_admin"), None, {"loaded_count": len(new_records), "skipped_existing_count": skipped_existing, "source": source, "warnings": warnings, "import_run_id": import_run["import_run_id"], "batch": updated_batch}, submodule="payroll_batch", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return {"batch": updated_batch, "source": source, "loaded_count": len(new_records), "skipped_existing_count": skipped_existing, "warnings": warnings, "import_run": import_run, "records": new_records}


def calculate_batch(batch_id: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Finalized or paid batch cannot be recalculated")
    path = payroll_record_file(batch["country_code"])
    records = read_json(path)
    calculated = []
    for index, record in enumerate(records):
        if record.get("batch_id") != batch_id:
            continue
        before = dict(record)
        updated = calculate_payroll_row(record)
        if updated.get("status") != "validation_error":
            updated["status"] = "calculated"
        records[index] = updated
        calculated.append(updated)
        append_audit("salary", updated["payroll_record_id"], "payroll_record_calculated", clean_text(payload.get("user") or "local_admin"), before, updated, submodule="payroll_record", batch_id=batch_id, payroll_record_id=updated["payroll_record_id"], country_code=batch["country_code"], entity_id=batch["entity_id"], employee_id=updated.get("employee_id"))
    write_json(path, records)
    totals = calculate_batch_totals(calculated)
    updated_batch = update_batch(batch_id, {"status": "calculated", **totals, "calculated_at": now_iso()})
    append_audit("salary", batch_id, "payroll_calculated", clean_text(payload.get("user") or "local_admin"), None, {"calculated_count": len(calculated), "batch": updated_batch}, submodule="payroll_batch", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return {"batch": updated_batch, "calculated_count": len(calculated), "records": calculated}


def adjust_record(record_id: str, payload: dict) -> dict:
    found = find_payroll_record(record_id)
    if not found:
        raise ValueError("Payroll record not found")
    path, records, index, record = found
    batch = batch_by_id(record.get("batch_id", ""))
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Finalized or paid batch cannot be adjusted directly")
    before = dict(record)
    adjustment = {
        "adjustment_id": str(uuid.uuid4()),
        "amount": money(payload.get("amount", 0)),
        "reason": clean_text(payload.get("reason") or "Manual payroll adjustment"),
        "created_by": clean_text(payload.get("user") or "local_admin"),
        "created_at": now_iso(),
    }
    record.setdefault("manual_adjustments", []).append(adjustment)
    record = calculate_payroll_row(record)
    record["status"] = "hr_review"
    records[index] = record
    write_json(path, records)
    updated_rows = batch_records(batch["batch_id"], batch["country_code"])
    updated_batch = update_batch(batch["batch_id"], {"status": "hr_review", **calculate_batch_totals(updated_rows)})
    append_audit("salary", record_id, "payroll_record_adjusted", adjustment["created_by"], before, record, submodule="payroll_record", batch_id=batch["batch_id"], payroll_record_id=record_id, country_code=batch["country_code"], entity_id=batch["entity_id"], employee_id=record.get("employee_id"), reason=adjustment["reason"])
    return {"record": record, "batch": updated_batch}


def update_payroll_record(record_id: str, payload: dict) -> dict:
    found = find_payroll_record(record_id)
    if not found:
        raise ValueError("Payroll record not found")
    path, records, index, record = found
    batch = batch_by_id(record.get("batch_id", ""))
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Finalized or paid batch cannot be edited directly")
    before = dict(record)
    for section in ("earnings", "deductions", "employer_costs", "salary_calculation_rule_snapshot", "contract_snapshot"):
        values = payload.get(section)
        if isinstance(values, dict):
            current = dict(record.get(section) or {})
            for key, value in values.items():
                clean_key = clean_text(key)
                if section in {"earnings", "deductions", "employer_costs"} or clean_key in {"base_rate", "hourly_rate", "daily_rate", "standard_hours_per_month", "standard_days_per_month", "actual_work_hours", "actual_work_days"}:
                    current[clean_key] = money(value)
                elif clean_key == "overtime_eligible":
                    current[clean_key] = parse_bool(value)
                else:
                    current[clean_key] = clean_text(value)
            record[section] = current
    country_section = {"JP": "jp_fields", "SG": "sg_fields", "CN": "cn_fields"}.get(record.get("country_code"))
    if country_section and isinstance(payload.get(country_section), dict):
        current_country = dict(record.get(country_section) or {})
        for key, value in payload[country_section].items():
            key = clean_text(key)
            if key == "city_code":
                city = clean_text(value).upper().replace("'", "")
                if city and city not in SUPPORTED_CN_CITIES:
                    raise ValueError("CN city_code must be SHANGHAI, NANJING, XIAN, or WUHU")
                current_country[key] = city
            elif isinstance(value, (int, float)) or clean_text(value).replace(".", "", 1).replace("-", "", 1).isdigit():
                current_country[key] = money(value)
            else:
                current_country[key] = clean_text(value)
        record[country_section] = current_country
    record = calculate_payroll_row(record)
    record["status"] = "hr_review"
    records[index] = record
    write_json(path, records)
    updated_rows = batch_records(batch["batch_id"], batch["country_code"])
    updated_batch = update_batch(batch["batch_id"], {"status": "hr_review", **calculate_batch_totals(updated_rows)})
    append_audit("salary", record_id, "payroll_record_updated", clean_text(payload.get("user") or "local_admin"), before, record, submodule="payroll_record", batch_id=batch["batch_id"], payroll_record_id=record_id, country_code=batch["country_code"], entity_id=batch["entity_id"], employee_id=record.get("employee_id"))
    return {"record": record, "batch": updated_batch}


def confirmations_for_batch(batch_id: str) -> list[dict]:
    return [record for record in read_json(PAYROLL_CONFIRMATIONS_FILE) if record.get("batch_id") == batch_id]


def create_confirmation(batch_id: str, level: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Finalized or paid batch cannot be confirmed again")
    confirmations = confirmations_for_batch(batch_id)
    if any(record.get("confirmation_level") == level for record in confirmations):
        raise ValueError(f"{level} confirmation already exists")
    if level == "second" and not any(record.get("confirmation_level") == "first" for record in confirmations):
        raise ValueError("First confirmation is required before second confirmation")
    confirming_user = clean_text(payload.get("user") or "local_admin")
    if level == "second" and any(record.get("confirmation_level") == "first" and record.get("confirmed_by") == confirming_user for record in confirmations) and not payload.get("admin_override_allowed"):
        raise ValueError("Second confirmation by the same user requires admin override permission")
    confirmation_id = next_sequence_id("CONF", batch["payroll_month"], read_json(PAYROLL_CONFIRMATIONS_FILE), "confirmation_id")
    confirmation = {
        "confirmation_id": confirmation_id,
        "batch_id": batch_id,
        "country_code": batch["country_code"],
        "entity_id": batch["entity_id"],
        "payroll_month": batch["payroll_month"],
        "confirmation_level": level,
        "confirmed_by": confirming_user,
        "confirmed_at": now_iso(),
        "comment": clean_text(payload.get("comment")),
        "checklist": payload.get("checklist") if isinstance(payload.get("checklist"), list) else [],
    }
    append_json_record(PAYROLL_CONFIRMATIONS_FILE, confirmation)
    if level == "first":
        updated_batch = update_batch(batch_id, {"status": "first_confirmed", "first_confirmed_by": confirmation["confirmed_by"], "first_confirmed_at": confirmation["confirmed_at"]})
        action = "payroll_first_confirmation_completed"
    else:
        updated_batch = update_batch(batch_id, {"status": "final_review", "second_confirmed_by": confirmation["confirmed_by"], "second_confirmed_at": confirmation["confirmed_at"]})
        action = "payroll_second_confirmation_completed"
    append_audit("salary", batch_id, action, confirmation["confirmed_by"], None, confirmation, submodule="payroll_confirmation", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return {"confirmation": confirmation, "batch": updated_batch}


def finalize_batch(batch_id: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") in LOCKED_BATCH_STATUSES:
        raise ValueError("Payroll batch is already finalized or paid")
    confirmations = confirmations_for_batch(batch_id)
    levels = {record.get("confirmation_level") for record in confirmations}
    if not {"first", "second"}.issubset(levels):
        raise ValueError("Both first and second confirmations are required before finalization")
    path = payroll_record_file(batch["country_code"])
    records = read_json(path)
    blocking_rows = [record for record in records if record.get("batch_id") == batch_id and record.get("status") == "validation_error"]
    if blocking_rows:
        raise ValueError("Payroll cannot be finalized while records have validation_error status")
    finalized_rows = []
    for index, record in enumerate(records):
        if record.get("batch_id") == batch_id:
            updated = dict(record)
            updated["status"] = "finalized"
            updated["finalized_at"] = now_iso()
            updated["updated_at"] = updated["finalized_at"]
            records[index] = updated
            finalized_rows.append(updated)
    write_json(path, records)
    final_totals = calculate_batch_totals(finalized_rows)
    finalized_at = now_iso()
    before = dict(batch)
    updated_batch = update_batch(batch_id, {"status": "finalized", "finalized_by": clean_text(payload.get("user") or "local_admin"), "finalized_at": finalized_at, **final_totals})
    append_audit("salary", batch_id, "payroll_finalized", updated_batch.get("finalized_by", "local_admin"), before, updated_batch, submodule="payroll_batch", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return {"batch": updated_batch, "finalized_record_count": len(finalized_rows)}


def update_payment_row_status(batch: dict, row_status: str, payment_status: str, actor: str, paid_at: str = "") -> list[dict]:
    path = payroll_record_file(batch["country_code"])
    records = read_json(path)
    updated_rows = []
    for index, record in enumerate(records):
        if record.get("batch_id") != batch["batch_id"]:
            continue
        updated = dict(record)
        updated["status"] = row_status
        updated["payment_status"] = payment_status
        updated["payment_updated_by"] = actor
        updated["payment_updated_at"] = now_iso()
        if paid_at:
            updated["paid_at"] = paid_at
        updated["updated_at"] = updated["payment_updated_at"]
        records[index] = updated
        updated_rows.append(updated)
    write_json(path, records)
    return updated_rows


def prepare_payment(batch_id: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") != "finalized":
        raise ValueError("Payment can only be prepared after payroll finalization")
    existing = [record for record in read_json(PAYMENT_RECORDS_FILE) if record.get("batch_id") == batch_id and record.get("payment_status") != "cancelled"]
    if existing:
        return existing[-1]
    payment_id = next_sequence_id("PAY", batch["payroll_month"], read_json(PAYMENT_RECORDS_FILE), "payment_id")
    records = batch_records(batch_id, batch["country_code"])
    totals = calculate_batch_totals(records)
    actor = clean_text(payload.get("user") or "local_admin")
    payment = {
        "payment_id": payment_id,
        "batch_id": batch_id,
        "country_code": batch["country_code"],
        "entity_id": batch["entity_id"],
        "payroll_month": batch["payroll_month"],
        "currency": batch["currency"],
        "employee_count": totals["employee_count"],
        "total_net_pay": totals["net_pay_total"],
        "total_employer_cost": totals["employer_cost_total"],
        "payment_method": clean_text(payload.get("payment_method") or "manual_bank_transfer"),
        "payment_status": "prepared",
        "prepared_by": actor,
        "prepared_at": now_iso(),
        "paid_by": "",
        "paid_at": "",
        "reference_number": clean_text(payload.get("reference_number")),
        "notes": clean_text(payload.get("notes")),
        "export_count": 0,
        "latest_exported_at": "",
    }
    append_json_record(PAYMENT_RECORDS_FILE, payment)
    updated_rows = update_payment_row_status(batch, "payment_prepared", "prepared", actor)
    update_batch(batch_id, {"status": "payment_prepared", "payment_prepared_by": actor, "payment_prepared_at": payment["prepared_at"], **calculate_batch_totals(updated_rows)})
    append_audit("salary", payment_id, "payroll_payment_prepared", actor, None, {**payment, "row_count": len(updated_rows)}, submodule="payment", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return payment


def payment_export_csv(batch_id: str, user: str = "local_admin") -> tuple[str, str]:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") not in {"payment_prepared", "paid", "archived"}:
        raise ValueError("Payment export requires prepared, paid, or archived payroll")
    records = batch_records(batch_id, batch["country_code"])
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["batch_id", "country_code", "entity_id", "payroll_month", "employee_id", "employee_no", "employee_name", "currency", "payment_amount", "payment_status", "payment_method"])
    for record in records:
        employee = record.get("employee_snapshot", {}) if isinstance(record.get("employee_snapshot"), dict) else {}
        writer.writerow([
            batch_id,
            record.get("country_code", ""),
            record.get("entity_id", ""),
            record.get("payroll_month", ""),
            record.get("employee_id", ""),
            employee.get("employee_no", ""),
            employee.get("employee_name", ""),
            record.get("currency", ""),
            record.get("net_pay", 0),
            record.get("payment_status", ""),
            "manual_bank_transfer",
        ])
    content = output.getvalue()
    filename = f"payment_list_{batch_id}.csv"
    payments = read_json(PAYMENT_RECORDS_FILE)
    for index, payment in enumerate(payments):
        if payment.get("batch_id") == batch_id and payment.get("payment_status") in {"prepared", "paid"}:
            before = dict(payment)
            payment["export_count"] = int(payment.get("export_count", 0) or 0) + 1
            payment["latest_exported_at"] = now_iso()
            payment["latest_exported_by"] = user
            payment["latest_export_file_name"] = filename
            payments[index] = payment
            write_json(PAYMENT_RECORDS_FILE, payments)
            append_audit("salary", payment.get("payment_id", batch_id), "payroll_payment_list_exported", user, before, payment, submodule="payment", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
            break
    else:
        append_audit("salary", batch_id, "payroll_payment_list_exported", user, None, {"file_name": filename, "row_count": len(records)}, submodule="payment", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return filename, content


def mark_payment_paid(batch_id: str, payload: dict) -> dict:
    payments = read_json(PAYMENT_RECORDS_FILE)
    for index, payment in enumerate(payments):
        if payment.get("batch_id") == batch_id and payment.get("payment_status") == "prepared":
            before = dict(payment)
            paid_by = clean_text(payload.get("user") or "local_admin")
            paid_at = now_iso()
            payment["payment_status"] = "paid"
            payment["paid_by"] = paid_by
            payment["paid_at"] = paid_at
            payment["reference_number"] = clean_text(payload.get("reference_number") or payment.get("reference_number"))
            payment["notes"] = clean_text(payload.get("notes") or payment.get("notes"))
            payments[index] = payment
            write_json(PAYMENT_RECORDS_FILE, payments)
            batch = batch_by_id(batch_id)
            if not batch:
                raise ValueError("Payroll batch not found")
            updated_rows = update_payment_row_status(batch, "paid", "paid", paid_by, paid_at)
            batch = update_batch(batch_id, {"status": "paid", "paid_by": paid_by, "paid_at": paid_at, **calculate_batch_totals(updated_rows)})
            append_audit("salary", payment["payment_id"], "payroll_payment_marked_paid", paid_by, before, {**payment, "row_count": len(updated_rows)}, submodule="payment", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
            return payment
    raise ValueError("Prepared payment record not found")


def archive_batch(batch_id: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if batch.get("status") == "archived":
        return batch
    if batch.get("status") != "paid":
        raise ValueError("Only paid payroll batches can be archived")
    actor = clean_text(payload.get("user") or "local_admin")
    archived_at = now_iso()
    path = payroll_record_file(batch["country_code"])
    records = read_json(path)
    archived_rows = []
    for index, record in enumerate(records):
        if record.get("batch_id") != batch_id:
            continue
        updated = dict(record)
        updated["final_lock_flag"] = True
        updated["archived_at"] = archived_at
        updated["archived_by"] = actor
        updated["updated_at"] = archived_at
        records[index] = updated
        archived_rows.append(updated)
    write_json(path, records)
    before = dict(batch)
    updated_batch = update_batch(batch_id, {"status": "archived", "archived_by": actor, "archived_at": archived_at, **calculate_batch_totals(archived_rows)})
    append_audit("salary", batch_id, "payroll_batch_archived", actor, before, {**updated_batch, "archived_record_count": len(archived_rows)}, submodule="payroll_batch", batch_id=batch_id, country_code=batch["country_code"], entity_id=batch["entity_id"])
    return updated_batch


def scope_from_query(query: dict[str, list[str]] | None = None) -> dict:
    query = query or {}
    country_code = clean_text(query.get("country_code", [""])[0])
    if country_code:
        country_code = normalize_country_code(country_code)
    entity_id = clean_text(query.get("entity_id", [""])[0])
    if entity_id and entity_id not in MASTER_ENTITIES:
        raise ValueError(f"Unknown entity_id: {entity_id}")
    if country_code and entity_id:
        entity_snapshot(entity_id, country_code)
    return {
        "country_code": country_code,
        "entity_id": entity_id,
        "department": clean_text(query.get("department", [""])[0]).casefold(),
        "employee": clean_text(query.get("employee", [""])[0]).casefold(),
        "payroll_month": clean_text(query.get("payroll_month", [""])[0]),
        "status": clean_text(query.get("status", [""])[0]),
        "q": clean_text(query.get("q", [""])[0]).casefold(),
    }


def searchable_record_text(record: dict) -> str:
    employee = record.get("employee_snapshot") if isinstance(record.get("employee_snapshot"), dict) else {}
    profile = record.get("salary_profile_snapshot") if isinstance(record.get("salary_profile_snapshot"), dict) else {}
    parts = [
        record.get("batch_id"),
        record.get("payroll_record_id"),
        record.get("profile_id"),
        record.get("parameter_id"),
        record.get("payment_id"),
        record.get("notice_id"),
        record.get("feedback_id"),
        record.get("employee_id"),
        record.get("employee_no"),
        record.get("employee_name"),
        employee.get("employee_no"),
        employee.get("employee_name"),
        employee.get("department"),
        profile.get("employee_name"),
        record.get("department"),
        record.get("notes"),
        record.get("status"),
    ]
    return " ".join(clean_text(part) for part in parts).casefold()


def in_scope(record: dict, scope: dict) -> bool:
    country_code = scope.get("country_code")
    entity_id = scope.get("entity_id")
    if country_code and record.get("country_code") != country_code:
        return False
    if entity_id and record.get("entity_id") != entity_id:
        return False
    if scope.get("payroll_month") and record.get("payroll_month") != scope.get("payroll_month"):
        return False
    if scope.get("status") and record.get("status", record.get("feedback_status", record.get("payment_status"))) != scope.get("status"):
        return False
    return True


def scoped_records(records: list[dict], scope: dict) -> list[dict]:
    return [record for record in records if in_scope(record, scope)]


def query_value(record: dict, paths: tuple[str, ...]) -> str:
    values = []
    for path in paths:
        value = get_nested(record, path, None)
        if value is None:
            value = record.get(path, "")
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False)
        values.append(clean_text(value))
    return " ".join(value for value in values if value)


def first_query_value(query: dict[str, list[str]], key: str) -> str:
    return clean_text(query.get(key, [""])[0])


def matches_query(record: dict, query: dict[str, list[str]], record_type: str = "generic") -> bool:
    filters = {
        "entity": ("entity_id", "legal_entity_id", "entity_snapshot.entity_id", "entity_snapshot.entity_code", "entity_snapshot.entity_name_en", "entity_snapshot.entity_name_local"),
        "department_id": ("department_id", "employeeadmin_snapshot.department_id", "employee_snapshot.department_id", "salary_profile_snapshot.department_id"),
        "department": ("department", "department_id", "employeeadmin_snapshot.department", "employeeadmin_snapshot.department_id", "employee_snapshot.department", "employee_snapshot.department_id", "salary_profile_snapshot.department", "salary_profile_snapshot.department_id"),
        "team_id": ("team_id", "employeeadmin_snapshot.team_id", "employee_snapshot.team_id", "salary_profile_snapshot.team_id"),
        "employee": ("employee_id", "employee_no", "employee_number", "employee_name", "recipient_employee_id", "employeeadmin_snapshot.employee_id", "employeeadmin_snapshot.employee_no", "employeeadmin_snapshot.employee_name", "employee_snapshot.employee_id", "employee_snapshot.employee_no", "employee_snapshot.employee_name", "salary_profile_snapshot.employee_id", "salary_profile_snapshot.employee_no", "salary_profile_snapshot.employee_name"),
        "employee_id": ("employee_id", "recipient_employee_id", "employeeadmin_snapshot.employee_id", "employee_snapshot.employee_id", "salary_profile_snapshot.employee_id"),
        "employee_no": ("employee_no", "employee_number", "employeeadmin_snapshot.employee_no", "employee_snapshot.employee_no", "salary_profile_snapshot.employee_no"),
        "employee_name": ("employee_name", "employeeadmin_snapshot.employee_name", "employee_snapshot.employee_name", "salary_profile_snapshot.employee_name"),
        "month": ("payroll_month", "salary_month"),
        "payroll_month": ("payroll_month", "salary_month"),
        "status": ("status", "payment_status", "feedback_status"),
        "payment_status": ("payment_status",),
        "batch_id": ("batch_id",),
    }
    for key, paths in filters.items():
        expected = first_query_value(query, key)
        if not expected:
            continue
        actual = query_value(record, paths).casefold()
        if expected.casefold() not in actual:
            return False
    keyword = first_query_value(query, "q") or first_query_value(query, "keyword")
    if keyword:
        searchable_paths = (
            "batch_id", "payroll_record_id", "profile_id", "payment_id", "notice_id", "feedback_id",
            "employee_id", "employee_no", "employee_number", "employee_name", "department", "department_id",
            "employeeadmin_snapshot.employee_no", "employeeadmin_snapshot.employee_name", "employeeadmin_snapshot.department", "employeeadmin_snapshot.department_id",
            "employee_snapshot.employee_no", "employee_snapshot.employee_name", "employee_snapshot.department", "employee_snapshot.department_id",
            "salary_profile_snapshot.employee_no", "salary_profile_snapshot.employee_name", "salary_profile_snapshot.department",
            "entity_id", "legal_entity_id", "entity_snapshot.entity_code", "entity_snapshot.entity_name_en", "entity_snapshot.entity_name_local", "payroll_month", "country_code", "status", "payment_status", "feedback_status", "notes", "message",
        )
        if keyword.casefold() not in query_value(record, searchable_paths).casefold():
            return False
    return True


def filter_records(records: list[dict], query: dict[str, list[str]], record_type: str = "generic") -> list[dict]:
    scope = scope_from_query(query)
    return [record for record in scoped_records(records, scope) if matches_query(record, query, record_type)]


def all_payroll_records(query: dict[str, list[str]] | None = None) -> list[dict]:
    query = query or {}
    scope = scope_from_query(query)
    countries = [scope["country_code"]] if scope.get("country_code") else list(PAYROLL_RECORD_FILES)
    rows: list[dict] = []
    for country in countries:
        rows.extend(read_json(PAYROLL_RECORD_FILES[country]))
    return filter_records(rows, query, "payroll_record")


def batch_ids_for_query(query: dict[str, list[str]]) -> set[str]:
    return {batch.get("batch_id") for batch in filter_records(read_json(PAYROLL_BATCHES_FILE), query, "batch")}


def filter_batch_related(records: list[dict], query: dict[str, list[str]], record_type: str = "generic") -> list[dict]:
    scope = scope_from_query(query)
    batch_ids = batch_ids_for_query(query)
    if batch_ids:
        scoped = [record for record in records if not record.get("batch_id") or record.get("batch_id") in batch_ids]
    else:
        scoped = scoped_records(records, scope)
    return [record for record in scoped if matches_query(record, query, record_type)]


def scoped_entities(scope: dict) -> list[dict]:
    return [entity_snapshot(entity["entity_id"]) for entity in MASTER_ENTITIES.values() if in_scope(entity, scope)]


def payroll_report(report_type: str, query: dict[str, list[str]] | None = None) -> dict:
    query = query or {}
    scope = scope_from_query(query)
    batches = filter_records(read_json(PAYROLL_BATCHES_FILE), query, "batch")
    rows = []
    for batch in batches:
        if report_type == "employer-cost":
            amount = money(batch.get("employer_cost_total"))
        else:
            amount = money(batch.get("net_pay_total"))
        rows.append({
            "batch_id": batch.get("batch_id"),
            "country_code": batch.get("country_code"),
            "entity_id": batch.get("entity_id"),
            "entity_name": batch.get("entity_snapshot", {}).get("entity_name_local") or batch.get("entity_id"),
            "payroll_month": batch.get("payroll_month"),
            "currency": batch.get("currency"),
            "employee_count": batch.get("employee_count", 0),
            "status": batch.get("status"),
            "amount": amount,
        })
    return {"report_type": report_type, "generated_at": now_iso(), "scope": scope, "rows": rows, "total_amount": round(sum(row["amount"] for row in rows), 2)}


def payslip_text(record: dict) -> str:
    employee = record.get("employee_snapshot", {})
    lines = [
        "TAC Salary Payslip",
        f"Payroll Month: {record.get('payroll_month', '')}",
        f"Employee: {employee.get('employee_name', '')} ({record.get('employee_id', '')})",
        f"Country/Entity: {record.get('country_code', '')} / {record.get('entity_id', '')}",
        f"Currency: {record.get('currency', '')}",
        "",
        f"Gross Pay: {record.get('gross_pay', 0)}",
        f"Deductions: {record.get('deduction_total', 0)}",
        f"Manual Adjustments: {record.get('manual_adjustments_total', 0)}",
        f"Net Pay: {record.get('net_pay', 0)}",
        f"Employer Cost: {record.get('employer_cost_total', 0)}",
        "",
        "Note: statutory calculations are manual/parameter-assisted until validated.",
    ]
    return "\n".join(lines) + "\n"


def generate_payslips(batch_id: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    records = batch_records(batch_id, batch["country_code"])
    documents = read_json(PAYSLIP_DOCUMENTS_FILE)
    generated = []
    for record in records:
        payslip_id = next_sequence_id("PS", batch["payroll_month"], documents, "payslip_id")
        filename = f"{payslip_id}_{record['employee_id']}.txt"
        file_path = PAYSLIP_DIR / filename
        content = payslip_text(record)
        file_path.write_text(content, encoding="utf-8")
        doc = {
            "payslip_id": payslip_id,
            "batch_id": batch_id,
            "payroll_record_id": record["payroll_record_id"],
            "employee_id": record["employee_id"],
            "country_code": batch["country_code"],
            "entity_id": batch["entity_id"],
            "payroll_month": batch["payroll_month"],
            "document_type": clean_text(payload.get("document_type") or "draft_text_payslip"),
            "file_name": filename,
            "file_path": str(file_path.relative_to(PROJECT_ROOT)),
            "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest(),
            "download_url": f"/api/v2/payslips/{payslip_id}/download",
            "status": "generated",
            "generated_by": clean_text(payload.get("user") or "local_admin"),
            "generated_at": now_iso(),
        }
        documents.append(doc)
        generated.append(doc)
        append_audit("salary", payslip_id, "payslip_generated", doc["generated_by"], None, doc, submodule="payslip", batch_id=batch_id, payroll_record_id=record["payroll_record_id"], country_code=batch["country_code"], entity_id=batch["entity_id"], employee_id=record["employee_id"])
    write_json(PAYSLIP_DOCUMENTS_FILE, documents)
    return {"batch_id": batch_id, "generated_count": len(generated), "payslips": generated}


def payment_for_batch(batch_id: str) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    payments = [payment for payment in read_json(PAYMENT_RECORDS_FILE) if payment.get("batch_id") == batch_id and payment.get("payment_status") != "cancelled"]
    return {"batch": batch, "payment": payments[-1] if payments else None, "payments": payments}


def payslips_for_batch(batch_id: str) -> list[dict]:
    return [doc for doc in read_json(PAYSLIP_DOCUMENTS_FILE) if doc.get("batch_id") == batch_id]


def payslip_by_id(payslip_id: str) -> dict | None:
    return next((doc for doc in read_json(PAYSLIP_DOCUMENTS_FILE) if doc.get("payslip_id") == payslip_id), None)


def notices_for_batch(batch_id: str) -> list[dict]:
    return [notice for notice in read_json(PAYROLL_NOTICES_FILE) if notice.get("batch_id") == batch_id]


def smtp_configured() -> bool:
    return bool(os.environ.get("TAC_SALARY_SMTP_HOST") and os.environ.get("TAC_SALARY_EMAIL_FROM"))


def send_notice_email(recipient: str, subject: str, body: str) -> tuple[bool, str]:
    if not smtp_configured():
        return False, "SMTP not configured; manual send pending"
    message = EmailMessage()
    message["From"] = os.environ.get("TAC_SALARY_EMAIL_FROM", "")
    message["To"] = recipient
    message["Subject"] = subject
    message.set_content(body)
    host = os.environ.get("TAC_SALARY_SMTP_HOST", "")
    port = int(os.environ.get("TAC_SALARY_SMTP_PORT", "587") or 587)
    username = os.environ.get("TAC_SALARY_SMTP_USER", "")
    password = os.environ.get("TAC_SALARY_SMTP_PASSWORD", "")
    try:
        with smtplib.SMTP(host, port, timeout=10) as smtp:
            smtp.starttls()
            if username and password:
                smtp.login(username, password)
            smtp.send_message(message)
        return True, "sent"
    except OSError as exc:
        return False, str(exc)


def create_notices(batch_id: str, notice_type: str, payload: dict) -> dict:
    batch = batch_by_id(batch_id)
    if not batch:
        raise ValueError("Payroll batch not found")
    if notice_type == "first" and batch.get("status") not in {"calculated", "hr_review", "first_confirmed", "final_review", "finalized"}:
        raise ValueError("First notice requires calculated payroll")
    if notice_type == "final" and batch.get("status") not in {"final_review", "finalized", "payment_prepared", "paid"}:
        raise ValueError("Final notice requires second confirmation/final review or later")
    records = batch_records(batch_id, batch["country_code"])
    notices = read_json(PAYROLL_NOTICES_FILE)
    created = []
    actor = clean_text(payload.get("user") or "local_admin")
    for record in records:
        employee = record.get("employee_snapshot", {})
        notice_id = next_sequence_id("NOTICE", batch["payroll_month"], notices, "notice_id")
        subject = f"TAC Payroll {notice_type.title()} Notice {batch['payroll_month']}"
        body = payslip_text(record)
        recipient = clean_text(employee.get("email"))
        sent, message = send_notice_email(recipient, subject, body) if recipient else (False, "No employee email snapshot; manual send pending")
        status = "sent" if sent else "manual_send_pending"
        notice = {
            "notice_id": notice_id,
            "batch_id": batch_id,
            "payroll_record_id": record.get("payroll_record_id"),
            "notice_type": f"{notice_type}_notice",
            "channel": "system_email" if smtp_configured() else "manual_email",
            "recipient_employee_id": record.get("employee_id"),
            "recipient_email_snapshot": recipient,
            "email_subject_snapshot": subject,
            "status": status,
            "queued_by": actor,
            "queued_at": now_iso(),
            "sent_by": actor if sent else "",
            "sent_at": now_iso() if sent else "",
            "failure_reason": "" if sent else message,
            "notes": clean_text(payload.get("notes")),
        }
        notices.append(notice)
        created.append(notice)
        append_audit("salary", notice_id, f"payroll_{notice_type}_notice_{'sent' if sent else 'queued'}", actor, None, notice, submodule="notice", batch_id=batch_id, payroll_record_id=record.get("payroll_record_id"), country_code=batch["country_code"], entity_id=batch["entity_id"], employee_id=record.get("employee_id"))
    write_json(PAYROLL_NOTICES_FILE, notices)
    status_update = "first_notice_sent" if notice_type == "first" else "final_notice_sent"
    update_batch(batch_id, {"status": status_update})
    return {"batch_id": batch_id, "notice_type": notice_type, "created_count": len(created), "notices": created}


def create_feedback(payload: dict) -> dict:
    feedback = {
        "feedback_id": next_sequence_id("FB", clean_text(payload.get("payroll_month") or now_iso()[:7]), read_json(EMPLOYEE_FEEDBACK_FILE), "feedback_id"),
        "payroll_record_id": clean_text(payload.get("payroll_record_id")),
        "batch_id": clean_text(payload.get("batch_id")),
        "employee_id": clean_text(payload.get("employee_id")),
        "notice_id": clean_text(payload.get("notice_id")),
        "feedback_type": clean_text(payload.get("feedback_type") or "question"),
        "feedback_status": "submitted",
        "message": clean_text(payload.get("message")),
        "submitted_by": clean_text(payload.get("user") or payload.get("employee_id") or "local_employee"),
        "submitted_at": now_iso(),
        "resolution": "",
        "closed_by": "",
        "closed_at": "",
    }
    append_json_record(EMPLOYEE_FEEDBACK_FILE, feedback)
    append_audit("salary", feedback["feedback_id"], "employee_feedback_submitted", feedback["submitted_by"], None, feedback, submodule="feedback", batch_id=feedback.get("batch_id"), payroll_record_id=feedback.get("payroll_record_id"), employee_id=feedback.get("employee_id"))
    return feedback


def resolve_feedback(feedback_id: str, payload: dict) -> dict:
    feedback_records = read_json(EMPLOYEE_FEEDBACK_FILE)
    for index, feedback in enumerate(feedback_records):
        if feedback.get("feedback_id") == feedback_id:
            before = dict(feedback)
            feedback["feedback_status"] = clean_text(payload.get("feedback_status") or "closed")
            feedback["resolution"] = clean_text(payload.get("resolution"))
            feedback["correction_required_flag"] = bool(payload.get("correction_required_flag", False))
            feedback["closed_by"] = clean_text(payload.get("user") or "local_admin")
            feedback["closed_at"] = now_iso()
            feedback_records[index] = feedback
            write_json(EMPLOYEE_FEEDBACK_FILE, feedback_records)
            append_audit("salary", feedback_id, "employee_feedback_resolved", feedback["closed_by"], before, feedback, submodule="feedback", batch_id=feedback.get("batch_id"), payroll_record_id=feedback.get("payroll_record_id"), employee_id=feedback.get("employee_id"))
            return feedback
    raise ValueError("Feedback not found")


def normalize_parameter(payload: dict, existing: dict | None = None) -> dict:
    country_code = normalize_country_code(payload.get("country_code") or (existing or {}).get("country_code"))
    entity = entity_snapshot(payload.get("entity_id") or (existing or {}).get("entity_id"), country_code)
    city = clean_text(payload.get("city_code") or (existing or {}).get("city_code")).upper().replace("'", "")
    if country_code == "CN" and city and city not in SUPPORTED_CN_CITIES:
        raise ValueError("CN city_code must be SHANGHAI, NANJING, XIAN, or WUHU")
    record = dict(existing or {})
    record.update(payload)
    record["parameter_id"] = record.get("parameter_id") or next_sequence_id("PARAM", clean_text(record.get("effective_start_date") or now_iso()[:7])[:7], read_json(PAYROLL_PARAMETERS_FILE), "parameter_id")
    record["country_code"] = country_code
    record["payroll_system_code"] = payroll_system_code(country_code)
    record["payroll_area_code"] = payroll_area_code(country_code)
    record["entity_id"] = entity["entity_id"]
    record["legal_entity_id"] = entity["entity_id"]
    record["currency"] = entity["currency"]
    record["rule_version_id"] = clean_text(record.get("rule_version_id")) or default_rule_version_id(country_code, record.get("effective_start_date") or now_iso()[:7])
    record["city_code"] = city
    record["parameter_type"] = clean_text(record.get("parameter_type") or "manual_payroll_parameter")
    record["calculation_method"] = clean_text(record.get("calculation_method") or "manual")
    record["values"] = record.get("values") if isinstance(record.get("values"), dict) else {}
    record["status"] = clean_text(record.get("status") or "draft")
    record["updated_at"] = now_iso()
    return record


def create_parameter(payload: dict) -> dict:
    record = normalize_parameter(payload)
    now = now_iso()
    record["created_at"] = now
    record["created_by"] = clean_text(payload.get("user") or "local_admin")
    records = read_json(PAYROLL_PARAMETERS_FILE)
    if any(existing.get("parameter_id") == record["parameter_id"] for existing in records):
        raise ValueError("Payroll parameter already exists")
    records.append(record)
    write_json(PAYROLL_PARAMETERS_FILE, records)
    append_audit("salary", record["parameter_id"], "payroll_parameter_created", record["created_by"], None, record, submodule="payroll_parameter", country_code=record["country_code"], entity_id=record["entity_id"])
    return record


def update_parameter(parameter_id: str, payload: dict) -> dict:
    records = read_json(PAYROLL_PARAMETERS_FILE)
    for index, existing in enumerate(records):
        if existing.get("parameter_id") == parameter_id:
            before = dict(existing)
            updated = normalize_parameter(payload, existing)
            updated["parameter_id"] = parameter_id
            updated["created_at"] = existing.get("created_at", now_iso())
            updated["created_by"] = existing.get("created_by", "")
            updated["updated_at"] = now_iso()
            records[index] = updated
            write_json(PAYROLL_PARAMETERS_FILE, records)
            append_audit("salary", parameter_id, "payroll_parameter_updated", clean_text(payload.get("user") or "local_admin"), before, updated, submodule="payroll_parameter", country_code=updated["country_code"], entity_id=updated["entity_id"])
            return updated
    raise ValueError("Payroll parameter not found")


def payroll_systems_payload(query: dict[str, list[str]] | None = None) -> dict:
    scope = scope_from_query(query)
    systems = []
    batches = read_json(PAYROLL_BATCHES_FILE)
    salary_master = read_json(SALARY_MASTER_FILE)
    for country_code, config in COUNTRY_PAYROLL_SYSTEMS.items():
        if scope.get("country_code") and scope["country_code"] != country_code:
            continue
        country_scope = {"country_code": country_code, "entity_id": scope.get("entity_id", "")}
        entities = scoped_entities(country_scope)
        country_batches = scoped_records(batches, country_scope)
        country_profiles = scoped_records(salary_master, country_scope)
        systems.append({
            **config,
            "country_code": country_code,
            "entity_count": len(entities),
            "entities": entities,
            "batch_count": len(country_batches),
            "salary_master_count": len(country_profiles),
            "open_batch_count": len([batch for batch in country_batches if batch.get("status") not in ("finalized", "paid", "archived", "voided")]),
        })
    return {"generated_at": now_iso(), "scope": scope, "systems": systems}


def dashboard_payload(query: dict[str, list[str]] | None = None) -> dict:
    query = query or {}
    scope = scope_from_query(query)
    batches = filter_records(read_json(PAYROLL_BATCHES_FILE), query, "batch")
    salary_master = filter_records(read_json(SALARY_MASTER_FILE), query, "salary_master")
    confirmations = filter_batch_related(read_json(PAYROLL_CONFIRMATIONS_FILE), query, "confirmation")
    all_records = all_payroll_records(query)
    status_counts: dict[str, int] = {}
    country_counts: dict[str, int] = {}
    for batch in batches:
        status_counts[batch.get("status", "unknown")] = status_counts.get(batch.get("status", "unknown"), 0) + 1
        country_counts[batch.get("country_code", "unknown")] = country_counts.get(batch.get("country_code", "unknown"), 0) + 1
    return {
        "generated_at": now_iso(),
        "scope": scope,
        "entity_count": len(scoped_entities(scope)),
        "batch_count": len(batches),
        "salary_master_count": len(salary_master),
        "payroll_record_count": len(all_records),
        "confirmation_count": len(confirmations),
        "status_counts": status_counts,
        "country_counts": country_counts,
        "open_batches": [batch for batch in batches if batch.get("status") not in ("finalized", "paid", "archived", "voided")],
        "totals": calculate_batch_totals(all_records),
    }


class SalaryHandler(BaseHTTPRequestHandler):
    server_version = "TACSalary/0.3"

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_common_headers()
        self.end_headers()

    def current_session_id(self) -> str:
        return parse_cookie_header(self.headers.get("Cookie", "")).get(USER_ADMIN_SESSION_COOKIE, "")

    def current_user(self) -> dict | None:
        return validate_user_admin_session(self.current_session_id())

    def authorize(self, permissions: set[str] | list[str] | tuple[str, ...]) -> tuple[bool, dict | None]:
        user = self.current_user()
        if user and (is_system_admin(user) or has_permission(user, REQUIRED_MODULE_PERMISSION) or has_any_permission(user, permissions)):
            return True, user
        if AUTH_ENFORCEMENT != "strict":
            return True, user
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.send_json({"error": "authentication_required", "login_url": f"{USER_ADMIN_BASE_URL}/login?next={next_url}"}, status=HTTPStatus.UNAUTHORIZED)
            return False, None
        self.send_json({"error": "forbidden", "permissions_required": sorted(permissions)}, status=HTTPStatus.FORBIDDEN)
        return False, user

    def require_permission(self, permission_key: str) -> dict | None:
        allowed, user = self.authorize({permission_key})
        return user if allowed else None

    def actor_payload(self, payload: dict, user: dict | None) -> dict:
        enriched = dict(payload)
        enriched.setdefault("user", actor_from_user(user, clean_text(payload.get("user") or "local_admin")))
        return enriched

    def read_authorized(self) -> tuple[bool, dict | None]:
        return self.authorize(permission_group("view"))

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path == "/health":
                self.send_json({"status": "ok", "project": "TAC-salary", "version": "0.2", "timestamp": now_iso()})
                return
            if path == "/api/salary-records":
                self.send_json(read_json(SALARY_FILE))
                return
            if path == "/api/employees":
                self.send_json(read_json(EMPLOYEE_FILE))
                return
            if path == "/api/audit-logs":
                self.send_json(read_json(AUDIT_FILE))
                return
            if self.handle_v2_get(path, parsed.query):
                return
            self.serve_static(path)
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if self.handle_v2_post(path):
                return
            if path != "/api/salary-records":
                self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found")
                return
            payload = self.read_body_json()
            missing = sorted(field for field in REQUIRED_CREATE_FIELDS if not payload.get(field))
            if missing:
                self.send_error_json(HTTPStatus.BAD_REQUEST, f"Missing required fields: {', '.join(missing)}")
                return
            record = normalize_salary(payload)
            record["id"] = str(uuid.uuid4())
            record["created_at"] = now_iso()
            record["updated_at"] = record["created_at"]
            records = read_json(SALARY_FILE)
            records.append(record)
            write_json(SALARY_FILE, records)
            append_audit("salary", record["id"], "create", payload.get("user", "local_admin"), None, record)
            self.send_json(record, status=HTTPStatus.CREATED)
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def do_PUT(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if self.handle_v2_put(path):
                return
            prefix = "/api/salary-records/"
            if not path.startswith(prefix):
                self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found")
                return
            record_id = path[len(prefix) :]
            payload = self.read_body_json()
            records = read_json(SALARY_FILE)
            for index, existing in enumerate(records):
                if existing.get("id") == record_id:
                    before_value = dict(existing)
                    updated = normalize_salary(payload, existing)
                    updated["id"] = record_id
                    updated["created_at"] = existing.get("created_at", now_iso())
                    updated["updated_at"] = now_iso()
                    records[index] = updated
                    write_json(SALARY_FILE, records)
                    append_audit("salary", record_id, "update", payload.get("user", "local_admin"), before_value, updated)
                    self.send_json(updated)
                    return
            self.send_error_json(HTTPStatus.NOT_FOUND, "Salary record not found")
        except ValueError as exc:
            self.send_error_json(HTTPStatus.BAD_REQUEST, str(exc))

    def handle_v2_get(self, path: str, query: str = "") -> bool:
        if not path.startswith("/api/v2"):
            return False
        query_params = parse_qs(query)
        scope = scope_from_query(query_params)
        if path in ("/api/v2/dashboard", "/api/v2", "/api/v2/config", "/api/v2/payroll-systems", "/api/v2/entities", "/api/v2/employeeadmin-employees", "/api/v2/batches", "/api/v2/salary-master", "/api/v2/records", "/api/v2/payments", "/api/v2/payslips", "/api/v2/notices", "/api/v2/confirmations", "/api/v2/parameters", "/api/v2/feedback", "/api/v2/audit-logs") or path.startswith(("/api/v2/batches/", "/api/v2/records/", "/api/v2/reports/", "/api/v2/payslips/")):
            allowed, user = self.authorize(permission_group("view"))
            if not allowed:
                return True
        if path in ("/api/v2/dashboard", "/api/v2"):
            self.send_json(dashboard_payload(query_params))
            return True
        if path == "/api/v2/config":
            self.send_json({"portal_base_url": PORTAL_BASE_URL, "app_base_url": APP_BASE_URL, "auth_enforcement": AUTH_ENFORCEMENT, "payroll_systems": COUNTRY_PAYROLL_SYSTEMS})
            return True
        if path == "/api/v2/payroll-systems":
            self.send_json(payroll_systems_payload(query_params))
            return True
        if path == "/api/v2/entities":
            self.send_json(scoped_entities(scope))
            return True
        if path == "/api/v2/employeeadmin-employees":
            self.send_json(employeeadmin_employees_payload(query_params, self.current_session_id()))
            return True
        if path == "/api/v2/batches":
            self.send_json(filter_records(read_json(PAYROLL_BATCHES_FILE), query_params, "batch"))
            return True
        if path == "/api/v2/salary-master":
            self.send_json(filter_records(read_json(SALARY_MASTER_FILE), query_params, "salary_master"))
            return True
        if path == "/api/v2/records":
            self.send_json(all_payroll_records(query_params))
            return True
        if path == "/api/v2/payments":
            self.send_json(filter_batch_related(read_json(PAYMENT_RECORDS_FILE), query_params, "payment"))
            return True
        if path == "/api/v2/payslips":
            self.send_json(filter_batch_related(read_json(PAYSLIP_DOCUMENTS_FILE), query_params, "payslip"))
            return True
        if path == "/api/v2/notices":
            self.send_json(filter_batch_related(read_json(PAYROLL_NOTICES_FILE), query_params, "notice"))
            return True
        if path == "/api/v2/confirmations":
            self.send_json(filter_batch_related(read_json(PAYROLL_CONFIRMATIONS_FILE), query_params, "confirmation"))
            return True
        if path == "/api/v2/parameters":
            self.send_json(filter_records(read_json(PAYROLL_PARAMETERS_FILE), query_params, "parameter"))
            return True
        if path == "/api/v2/feedback":
            self.send_json(filter_batch_related(read_json(EMPLOYEE_FEEDBACK_FILE), query_params, "feedback"))
            return True
        if path == "/api/v2/audit-logs":
            allowed, user = self.authorize(permission_group("audit"))
            if not allowed:
                return True
            self.send_json(filter_records(read_json(AUDIT_FILE), query_params, "audit"))
            return True
        if path.startswith("/api/v2/reports/"):
            report_type = path[len("/api/v2/reports/") :]
            if report_type not in {"employer-cost", "net-pay"}:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Report not found")
                return True
            allowed, user = self.authorize(permission_group("reports"))
            if not allowed:
                return True
            report = payroll_report(report_type, query_params)
            append_audit("salary", f"report-{report_type}", "payroll_report_viewed", actor_from_user(user), None, {"report_type": report_type, "row_count": len(report["rows"]), "query": query_params}, submodule="report")
            self.send_json(report)
            return True
        if path.startswith("/api/v2/payslips/") and path.endswith("/download"):
            payslip_id = unquote(path[len("/api/v2/payslips/") : -len("/download")])
            doc = payslip_by_id(payslip_id)
            if not doc:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Payslip not found")
                return True
            file_path = PROJECT_ROOT / clean_text(doc.get("file_path"))
            if not file_path.exists() or not file_path.is_file():
                self.send_error_json(HTTPStatus.NOT_FOUND, "Payslip file not found")
                return True
            append_audit("salary", payslip_id, "payslip_downloaded", actor_from_user(user), None, {"file_name": doc.get("file_name")}, submodule="payslip", batch_id=doc.get("batch_id"), payroll_record_id=doc.get("payroll_record_id"), country_code=doc.get("country_code"), entity_id=doc.get("entity_id"), employee_id=doc.get("employee_id"))
            self.send_file(file_path, "text/plain; charset=utf-8", clean_text(doc.get("file_name") or file_path.name))
            return True
        if path.startswith("/api/v2/batches/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) >= 4:
                batch_id = parts[3]
                batch = batch_by_id(batch_id)
                if not batch:
                    self.send_error_json(HTTPStatus.NOT_FOUND, "Payroll batch not found")
                    return True
                if len(parts) == 4:
                    self.send_json({"batch": batch, "records": batch_records(batch_id, batch["country_code"]), "confirmations": confirmations_for_batch(batch_id), "payment": payment_for_batch(batch_id).get("payment"), "payslips": payslips_for_batch(batch_id), "notices": notices_for_batch(batch_id), "latest_import_run": latest_import_run_for_batch(batch_id)})
                    return True
                if len(parts) == 5 and parts[4] == "records":
                    self.send_json(batch_records(batch_id, batch["country_code"]))
                    return True
                if len(parts) == 5 and parts[4] == "payment":
                    self.send_json(payment_for_batch(batch_id))
                    return True
                if len(parts) == 6 and parts[4:] == ["payment", "export"]:
                    allowed, export_user = self.authorize(permission_group("payment"))
                    if not allowed:
                        return True
                    filename, content = payment_export_csv(batch_id, actor_from_user(export_user))
                    self.send_download(content.encode("utf-8-sig"), "text/csv; charset=utf-8", filename)
                    return True
                if len(parts) == 5 and parts[4] == "payslips":
                    self.send_json(payslips_for_batch(batch_id))
                    return True
                if len(parts) == 5 and parts[4] == "notices":
                    self.send_json(notices_for_batch(batch_id))
                    return True
        if path.startswith("/api/v2/records/"):
            record_id = unquote(path[len("/api/v2/records/") :])
            found = find_payroll_record(record_id)
            if not found:
                self.send_error_json(HTTPStatus.NOT_FOUND, "Payroll record not found")
                return True
            self.send_json(found[3])
            return True
        return False

    def handle_v2_post(self, path: str) -> bool:
        if not path.startswith("/api/v2"):
            return False
        if path == "/api/v2/batches":
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            self.send_json(create_batch(self.actor_payload(self.read_body_json(), user)), status=HTTPStatus.CREATED)
            return True
        if path == "/api/v2/salary-master":
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            payload = self.actor_payload(self.read_body_json(), user)
            record = normalize_salary_master(payload)
            now = now_iso()
            record["created_at"] = now
            record["updated_at"] = now
            records = read_json(SALARY_MASTER_FILE)
            if any(existing.get("profile_id") == record["profile_id"] for existing in records):
                self.send_error_json(HTTPStatus.CONFLICT, "Salary master profile already exists; use PUT to update")
                return True
            records.append(record)
            write_json(SALARY_MASTER_FILE, records)
            append_audit("salary", record["profile_id"], "salary_master_created", payload.get("user", "local_admin"), None, record, submodule="salary_master", country_code=record["country_code"], entity_id=record["entity_id"], employee_id=record["employee_id"])
            self.send_json(record, status=HTTPStatus.CREATED)
            return True
        if path == "/api/v2/salary-master/import-employeeadmin":
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            self.send_json(import_salary_master_from_employeeadmin(self.actor_payload(self.read_body_json(), user), self.current_session_id()), status=HTTPStatus.CREATED)
            return True
        if path == "/api/v2/parameters":
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            payload = self.actor_payload(self.read_body_json(), user)
            parameter = normalize_parameter(payload)
            parameter["created_by"] = payload.get("user", "local_admin")
            parameter["created_at"] = now_iso()
            append_json_record(PAYROLL_PARAMETERS_FILE, parameter)
            append_audit("salary", parameter["parameter_id"], "payroll_parameter_created", payload.get("user", "local_admin"), None, parameter, submodule="parameter", country_code=parameter["country_code"], entity_id=parameter["entity_id"])
            self.send_json(parameter, status=HTTPStatus.CREATED)
            return True
        if path == "/api/v2/feedback":
            allowed, user = self.authorize(permission_group("view"))
            if not allowed:
                return True
            self.send_json(create_feedback(self.actor_payload(self.read_body_json(), user)), status=HTTPStatus.CREATED)
            return True
        if path.startswith("/api/v2/feedback/") and path.endswith("/resolve"):
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            feedback_id = unquote(path[len("/api/v2/feedback/") : -len("/resolve")])
            self.send_json(resolve_feedback(feedback_id, self.actor_payload(self.read_body_json(), user)))
            return True
        if path.startswith("/api/v2/batches/"):
            parts = [unquote(part) for part in path.split("/") if part]
            if len(parts) >= 5:
                batch_id = parts[3]
                action = parts[4:]
                permission = permission_group("payment") if action and action[0] == "payment" else permission_group("notice") if action and action[0] in {"payslips", "notices"} else permission_group("edit")
                allowed, user = self.authorize(permission)
                if not allowed:
                    return True
                payload = self.actor_payload(self.read_body_json(), user)
                if action == ["load-employees"]:
                    self.send_json(load_employees_for_batch(batch_id, payload, self.current_session_id()))
                    return True
                if action == ["calculate"]:
                    self.send_json(calculate_batch(batch_id, payload))
                    return True
                if action == ["confirm", "first"]:
                    payload["admin_override_allowed"] = is_system_admin(user) or has_any_permission(user, permission_group("admin_override"))
                    self.send_json(create_confirmation(batch_id, "first", payload), status=HTTPStatus.CREATED)
                    return True
                if action == ["confirm", "second"]:
                    payload["admin_override_allowed"] = is_system_admin(user) or has_any_permission(user, permission_group("admin_override"))
                    self.send_json(create_confirmation(batch_id, "second", payload), status=HTTPStatus.CREATED)
                    return True
                if action == ["finalize"]:
                    self.send_json(finalize_batch(batch_id, payload))
                    return True
                if action == ["payment", "prepare"]:
                    self.send_json(prepare_payment(batch_id, payload), status=HTTPStatus.CREATED)
                    return True
                if action == ["payment", "mark-paid"]:
                    self.send_json(mark_payment_paid(batch_id, payload))
                    return True
                if action == ["archive"]:
                    self.send_json(archive_batch(batch_id, payload))
                    return True
                if action == ["payslips", "generate"]:
                    self.send_json(generate_payslips(batch_id, payload), status=HTTPStatus.CREATED)
                    return True
                if action == ["notices", "first"]:
                    self.send_json(create_notices(batch_id, "first", payload), status=HTTPStatus.CREATED)
                    return True
                if action == ["notices", "final"]:
                    self.send_json(create_notices(batch_id, "final", payload), status=HTTPStatus.CREATED)
                    return True
        if path.startswith("/api/v2/records/") and path.endswith("/adjust"):
            allowed, user = self.authorize(permission_group("edit"))
            if not allowed:
                return True
            record_id = unquote(path[len("/api/v2/records/") : -len("/adjust")])
            self.send_json(adjust_record(record_id, self.actor_payload(self.read_body_json(), user)))
            return True
        return False

    def handle_v2_put(self, path: str) -> bool:
        if not path.startswith("/api/v2"):
            return False
        allowed, user = self.authorize(permission_group("edit"))
        if not allowed:
            return True
        payload = self.actor_payload(self.read_body_json(), user)
        if path.startswith("/api/v2/salary-master/"):
            profile_id = unquote(path[len("/api/v2/salary-master/") :])
            records = read_json(SALARY_MASTER_FILE)
            for index, existing in enumerate(records):
                if existing.get("profile_id") == profile_id:
                    before = dict(existing)
                    updated = normalize_salary_master(payload, existing)
                    updated["profile_id"] = profile_id
                    updated["created_at"] = existing.get("created_at", now_iso())
                    updated["updated_at"] = now_iso()
                    records[index] = updated
                    write_json(SALARY_MASTER_FILE, records)
                    append_audit("salary", profile_id, "salary_master_updated", payload.get("user", "local_admin"), before, updated, submodule="salary_master", country_code=updated["country_code"], entity_id=updated["entity_id"], employee_id=updated["employee_id"])
                    self.send_json(updated)
                    return True
            self.send_error_json(HTTPStatus.NOT_FOUND, "Salary master profile not found")
            return True
        if path.startswith("/api/v2/parameters/"):
            parameter_id = unquote(path[len("/api/v2/parameters/") :])
            self.send_json(update_parameter(parameter_id, payload))
            return True
        if path.startswith("/api/v2/records/"):
            record_id = unquote(path[len("/api/v2/records/") :])
            self.send_json(update_payroll_record(record_id, payload))
            return True
        self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found")
        return True

    def read_body_json(self) -> dict:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else "{}"
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            self.send_error_json(HTTPStatus.BAD_REQUEST, "Invalid JSON body")
            raise
        if not isinstance(payload, dict):
            self.send_error_json(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
            raise ValueError("JSON body must be an object")
        return payload

    def serve_static(self, path: str) -> None:
        app_routes = {"/", "", "/dashboard", "/batches", "/salary-master", "/payroll/jp", "/payroll/sg", "/payroll/cn", "/payroll/jp/", "/payroll/sg/", "/payroll/cn/"}
        static_path = FRONTEND_DIR / "index.html" if path in app_routes else FRONTEND_DIR / path.lstrip("/")
        if not static_path.exists() or not static_path.is_file():
            self.send_error_json(HTTPStatus.NOT_FOUND, "Route not found")
            return
        content_type = mimetypes.guess_type(static_path.name)[0] or "application/octet-stream"
        body = static_path.read_bytes()
        self.send_response(HTTPStatus.OK)
        self.send_common_headers(content_type=content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, payload: object, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_common_headers()
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_error_json(self, status: HTTPStatus, message: str) -> None:
        self.send_json({"error": message}, status=status)

    def send_file(self, file_path: Path, content_type: str, download_name: str = "") -> None:
        body = file_path.read_bytes()
        self.send_download(body, content_type, download_name)

    def send_download(self, body: bytes, content_type: str, download_name: str = "") -> None:
        self.send_response(HTTPStatus.OK)
        self.send_common_headers(content_type=content_type)
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_common_headers(self, content_type: str = "application/json; charset=utf-8") -> None:
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Cache-Control", "no-store")

    def log_message(self, format: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TAC-salary local web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    ensure_database()
    server = ThreadingHTTPServer((args.host, args.port), SalaryHandler)
    print(f"TAC-salary running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TAC-salary")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
