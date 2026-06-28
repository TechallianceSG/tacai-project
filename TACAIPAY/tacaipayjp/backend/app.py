#!/usr/bin/env python3
"""TACAIPAY JP local-first payroll MVP.

Standard-library web app for Japanese dispatch/headhunting payroll operations.
The calculation engine is parameter-assisted and requires HR/payroll review before
final approval.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import sys
import threading
import urllib.parse
from datetime import datetime, timezone
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

BACKEND_DIR = Path(__file__).resolve().parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from jp_payroll_engine import calculate_payroll_record, default_attendance, money
except ImportError:  # pragma: no cover
    from .jp_payroll_engine import calculate_payroll_record, default_attendance, money

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parents[1]
MODULE_KEY = "tacaipayjp"
MODULE_LABEL = "TACAIPAY JP"
DEFAULT_PORT = int(os.environ.get("TACAIPAYJP_PORT", "8017") or "8017")
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
MAX_POST_BYTES = 16 * 1024 * 1024  # 16MB for file uploads
MAX_POST_FORM_BYTES = 2 * 1024 * 1024  # 2MB for regular form POSTs
APP_BASE_URL = (os.environ.get("TACAIPAYJP_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:{DEFAULT_PORT}").strip() or f"http://{TACAI_PUBLIC_HOST}:{DEFAULT_PORT}").rstrip("/")
DATABASE_DIR = Path(os.environ.get("TACAIPAYJP_DATA_DIR", ROOT / "database"))
PAYSLIP_DIR = Path(os.environ.get("TACAIPAYJP_PAYSLIP_DIR", ROOT / "payslips"))
FRONTEND_DIR = ROOT / "frontend"
EMPLOYEEADMIN_EMPLOYEES = PROJECT_ROOT / "TAC-employeeadmin" / "database" / "employees.json"

JSON_FILES = {
    "employees_cache": "employees_cache.json",
    "salary_master": "salary_master.json",
    "payroll_batches": "payroll_batches.json",
    "payroll_records": "payroll_records.json",
    "payroll_item_definitions": "payroll_item_definitions.json",
    "payroll_parameters": "payroll_parameters.json",
    "payslip_documents": "payslip_documents.json",
    "payslip_feedback": "payslip_feedback.json",
    "payroll_confirmations": "payroll_confirmations.json",
    "payment_records": "payment_records.json",
    "report_exports": "report_exports.json",
    "email_deliveries": "email_deliveries.json",
    "audit_logs": "audit_logs.json",
}

BATCH_LOCKED_STATUSES = {"finalized", "sent_to_finance", "payment_prepared", "paid", "archived"}
BATCH_STATUSES = [
    "draft_created",
    "master_loaded",
    "attendance_input",
    "calculated",
    "hr_reviewed",
    "first_approved",
    "payslips_generated",
    "payslip_sent",
    "employee_feedback",
    "final_approved",
    "finalized",
    "sent_to_finance",
    "payment_prepared",
    "paid",
    "archived",
]
RECORD_STATUSES = [
    "master_snapshot",
    "attendance_entered",
    "calculated",
    "hr_reviewed",
    "first_approved",
    "payslips_generated",
    "payslip_sent",
    "feedback_received",
    "employee_confirmed",
    "final_approved",
    "finalized",
    "payment_prepared",
    "paid",
]
ALLOWED_BATCH_TRANSITIONS = {
    "draft_created": {"master_loaded"},
    "master_loaded": {"attendance_input", "calculated"},
    "attendance_input": {"calculated"},
    "calculated": {"attendance_input", "calculated", "hr_reviewed"},
    "hr_reviewed": {"first_approved"},
    "first_approved": {"payslips_generated"},
    "payslips_generated": {"payslip_sent"},
    "payslip_sent": {"employee_feedback", "final_approved"},
    "employee_feedback": {"final_approved"},
    "final_approved": {"finalized"},
    "finalized": {"sent_to_finance", "payment_prepared"},
    "sent_to_finance": {"payment_prepared"},
    "payment_prepared": {"paid"},
    "paid": {"archived"},
}
DATA_LOCK = threading.RLock()

DEFAULT_PARAMETERS = {
    "parameter_id": "param-jp-default-2026",
    "country_code": "JP",
    "entity_id": "default",
    "status": "active",
    "effective_start": "2026-01-01",
    "effective_end": "2099-12-31",
    "rule_version_id": "jp-mvp-2026-parameter-assisted",
    "standard_monthly_work_days": 20,
    "standard_monthly_work_hours": 160,
    "standard_daily_work_hours": 8,
    "overtime_multiplier": "1.25",
    "late_night_multiplier": "0.25",
    "holiday_multiplier": "1.35",
    "health_insurance_employee_rate": "0.0491",
    "health_insurance_employer_rate": "0.0491",
    "pension_employee_rate": "0.0915",
    "pension_employer_rate": "0.0915",
    "employment_insurance_employee_rate": "0.006",
    "employment_insurance_employer_rate": "0.0095",
    "notes": "MVP parameter-assisted rates. HR/payroll/tax specialists must confirm statutory amounts.",
}

DEFAULT_ITEMS = [
    ("base_pay", "earning", "base", "Basic salary", "基本給", "基本工资"),
    ("hourly_pay", "earning", "base", "Hourly pay", "時給", "时薪"),
    ("daily_pay", "earning", "base", "Daily pay", "日給", "日薪"),
    ("transportation", "earning", "allowance", "Transportation allowance", "通勤手当", "交通补贴"),
    ("site_allowance", "earning", "allowance", "Dispatch site allowance", "派遣先手当", "派遣现场津贴"),
    ("overtime", "earning", "overtime", "Overtime pay", "時間外手当", "加班费"),
    ("late_night", "earning", "overtime", "Late-night premium", "深夜手当", "深夜津贴"),
    ("holiday", "earning", "overtime", "Holiday work pay", "休日手当", "休日出勤费"),
    ("bonus", "earning", "manual", "Bonus/commission", "賞与・歩合", "奖金/佣金"),
    ("absence", "deduction", "attendance", "Absence deduction", "欠勤控除", "缺勤扣款"),
    ("advance", "deduction", "manual", "Advance repayment", "前払控除", "预支扣款"),
    ("health_insurance", "deduction", "statutory", "Health insurance", "健康保険", "健康保险"),
    ("pension", "deduction", "statutory", "Welfare pension", "厚生年金", "厚生年金"),
    ("employment_insurance", "deduction", "statutory", "Employment insurance", "雇用保険", "雇用保险"),
    ("income_tax", "deduction", "statutory", "Income tax", "所得税", "所得税"),
    ("resident_tax", "deduction", "statutory", "Resident tax", "住民税", "住民税"),
    ("employer_health_insurance", "employer_cost", "statutory", "Employer health insurance", "会社負担健康保険", "公司负担健康保险"),
    ("employer_pension", "employer_cost", "statutory", "Employer pension", "会社負担厚生年金", "公司负担厚生年金"),
    ("employer_employment_insurance", "employer_cost", "statutory", "Employer employment insurance", "会社負担雇用保険", "公司负担雇用保险"),
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_id(prefix: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    return f"{prefix}-{stamp}"


def path_for(name: str) -> Path:
    return DATABASE_DIR / JSON_FILES[name]


def read_json(name: str) -> List[Dict[str, Any]]:
    ensure_database()
    path = path_for(name)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def write_json(name: str, records: List[Dict[str, Any]]) -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    path = path_for(name)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def ensure_database() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    PAYSLIP_DIR.mkdir(parents=True, exist_ok=True)
    for file_name in JSON_FILES.values():
        path = DATABASE_DIR / file_name
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    item_path = path_for("payroll_item_definitions")
    try:
        existing_items = json.loads(item_path.read_text(encoding="utf-8"))
    except Exception:
        existing_items = []
    if not existing_items:
        items = []
        for index, (code, category, sub_category, en, ja, zh) in enumerate(DEFAULT_ITEMS, start=10):
            items.append({
                "item_id": f"item-{code}",
                "code": code,
                "category": category,
                "sub_category": sub_category,
                "labels": {"en": en, "ja": ja, "zh": zh},
                "taxable": category == "earning" and code != "transportation",
                "social_insurance_base": category == "earning" and code not in {"transportation"},
                "employment_insurance_base": category == "earning",
                "payslip_visible": True,
                "requires_reason": sub_category in {"manual", "adjustment"},
                "display_order": index,
                "status": "active",
            })
        item_path.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    param_path = path_for("payroll_parameters")
    try:
        existing_params = json.loads(param_path.read_text(encoding="utf-8"))
    except Exception:
        existing_params = []
    if not existing_params:
        param_path.write_text(json.dumps([DEFAULT_PARAMETERS], ensure_ascii=False, indent=2), encoding="utf-8")


def append_audit(action: str, record_id: str, user: str = "system", before: Any = None, after: Any = None, summary: str = "") -> None:
    with DATA_LOCK:
        logs = read_json("audit_logs")
        logs.append({
            "audit_id": new_id("audit"),
            "module": "tacaipayjp",
            "record_id": record_id,
            "action": action,
            "user": user,
            "timestamp": now_iso(),
            "before_value": redact_sensitive(before),
            "after_value": redact_sensitive(after),
            "summary": summary,
        })
        write_json("audit_logs", logs)


def redact_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, inner in value.items():
            if any(token in key.lower() for token in ["account", "bank", "my_number", "tax_id"]):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = redact_sensitive(inner)
        return redacted
    if isinstance(value, list):
        return [redact_sensitive(item) for item in value]
    return value


def find_by(records: List[Dict[str, Any]], key: str, value: str) -> Optional[Dict[str, Any]]:
    return next((record for record in records if str(record.get(key)) == str(value)), None)


def can_transition_batch(current_status: str, next_status: str) -> bool:
    if current_status == next_status and current_status in {"calculated", "payslips_generated", "payslip_sent"}:
        return True
    return next_status in ALLOWED_BATCH_TRANSITIONS.get(current_status or "draft_created", set())


def require_batch_transition(batch: Dict[str, Any], next_status: str) -> None:
    current_status = batch.get("status") or "draft_created"
    if not can_transition_batch(current_status, next_status):
        raise ValueError(f"invalid batch transition: {current_status} -> {next_status}")


def employee_email_for_record(record: Dict[str, Any]) -> str:
    employee_snapshot = record.get("employee_snapshot") or {}
    profile_snapshot = record.get("salary_master_snapshot") or {}
    return str(employee_snapshot.get("email") or profile_snapshot.get("email") or record.get("email") or "").strip()


def nested_value(data: Dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict):
            return default
        current = current.get(part)
        if current is None:
            return default
    return current


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def active_parameters(entity_id: str = "default") -> Dict[str, Any]:
    params = read_json("payroll_parameters")
    for param in params:
        if param.get("status") == "active" and param.get("entity_id") in {entity_id, "default", None, ""}:
            merged = dict(DEFAULT_PARAMETERS)
            merged.update(param)
            return merged
    return dict(DEFAULT_PARAMETERS)


def normalize_employee(employee: Dict[str, Any]) -> Dict[str, Any]:
    profile = employee.get("profile") if isinstance(employee.get("profile"), dict) else {}
    employment = employee.get("employment") if isinstance(employee.get("employment"), dict) else {}
    payroll = employee.get("payroll") if isinstance(employee.get("payroll"), dict) else {}
    payroll_bank = payroll.get("bank") if isinstance(payroll.get("bank"), dict) else {}
    name = first_present(
        nested_value(profile, "name.display_name"),
        profile.get("display_name"),
        profile.get("name"),
        employee.get("display_name"),
        employee.get("employee_name"),
        employee.get("name"),
    )
    employee_id = first_present(employee.get("employee_id"), employee.get("id"), employee.get("employee_number"), employee.get("employee_no"))
    entity_id = first_present(employment.get("entity_id"), employee.get("entity_id"), "default")
    salary_amount = first_present(payroll.get("salary_amount_yen"), payroll.get("base_salary"), payroll.get("basic_salary"), employee.get("base_salary"), employee.get("basic_salary"), 0)
    country_code = str(first_present(employment.get("country_code"), employment.get("work_country"), employee.get("country_code"), employee.get("work_country"), "JP")).upper()
    return {
        "employee_id": employee_id,
        "employee_number": first_present(employee.get("employee_number"), employee.get("employee_no"), employee_id),
        "display_name": name,
        "email": first_present(profile.get("email"), employee.get("email")),
        "entity_id": entity_id,
        "department_id": first_present(employment.get("department_id"), employee.get("department_id")),
        "department": first_present(employee.get("department"), employee.get("department_label"), employment.get("department"), employment.get("department_name")),
        "employment_status": first_present(employment.get("status"), employee.get("employment_status"), employee.get("status"), "active"),
        "employment_type": first_present(employment.get("employment_type"), employee.get("employment_type"), "employee"),
        "country_code": country_code,
        "payroll_ready": employee.get("payroll_ready", True),
        "payroll": payroll,
        "salary_type": first_present(payroll.get("salary_type"), employee.get("salary_type"), "monthly"),
        "base_salary": money(salary_amount),
        "hourly_rate": money(first_present(payroll.get("hourly_rate"), employee.get("hourly_rate"))),
        "daily_rate": money(first_present(payroll.get("daily_rate"), employee.get("daily_rate"))),
        "transportation_allowance": money(first_present(payroll.get("transportation_allowance_yen"), payroll.get("transportation_allowance"), employee.get("transportation_allowance"), 0)),
        "health_insurance_enrolled": bool(payroll.get("social_insurance_enrolled", True)),
        "pension_enrolled": bool(payroll.get("pension_enrolled", True)),
        "employment_insurance_enrolled": bool(payroll.get("employment_insurance_enrolled", True)),
        "bank": payroll_bank,
    }


def salary_profile_from_employee(employee: Dict[str, Any], actor: str = "system") -> Dict[str, Any]:
    normalized = normalize_employee(employee)
    return {
        "profile_id": new_id("salprof"),
        "employee_id": normalized["employee_id"],
        "employee_number": normalized["employee_number"],
        "display_name": normalized["display_name"],
        "email": normalized["email"],
        "entity_id": normalized["entity_id"],
        "department_id": normalized["department_id"],
        "department": normalized["department"],
        "employment_type": normalized["employment_type"],
        "country_code": "JP",
        "salary_type": normalized["salary_type"],
        "base_salary": normalized["base_salary"],
        "hourly_rate": normalized["hourly_rate"],
        "daily_rate": normalized["daily_rate"],
        "standard_work_days": 20,
        "standard_work_hours": 160,
        "transportation_allowance": normalized["transportation_allowance"],
        "fixed_earnings": [],
        "fixed_deductions": [],
        "health_insurance_enrolled": normalized["health_insurance_enrolled"],
        "pension_enrolled": normalized["pension_enrolled"],
        "employment_insurance_enrolled": normalized["employment_insurance_enrolled"],
        "default_income_tax": 0,
        "default_resident_tax": 0,
        "bank": normalized["bank"],
        "source": "employeeadmin",
        "status": "active" if normalized["employment_status"] in {"active", "probation", "onboarding"} else "inactive",
        "effective_from": "",
        "effective_to": "",
        "created_at": now_iso(),
        "created_by": actor,
        "updated_at": now_iso(),
        "updated_by": actor,
    }


def load_employeeadmin_employees() -> List[Dict[str, Any]]:
    if not EMPLOYEEADMIN_EMPLOYEES.exists():
        return []
    try:
        data = json.loads(EMPLOYEEADMIN_EMPLOYEES.read_text(encoding="utf-8"))
        if isinstance(data, list):
            normalized = [normalize_employee(item) for item in data]
            write_json("employees_cache", normalized)
            return normalized
    except Exception:
        return []
    return []


def filter_employeeadmin_employees(query: Dict[str, List[str]]) -> List[Dict[str, Any]]:
    employees = load_employeeadmin_employees()
    country = str((query.get("country_code") or ["JP"])[0] or "JP").strip().upper()
    entity = str((query.get("entity_id") or [""])[0]).strip()
    department = str((query.get("department") or query.get("department_id") or [""])[0]).strip().casefold()
    q = str((query.get("q") or [""])[0]).strip().casefold()
    rows = []
    for employee in employees:
        if country and str(employee.get("country_code", "")).upper() not in {country, "JPN" if country == "JP" else country}:
            continue
        if entity and str(employee.get("entity_id", "")) != entity:
            continue
        department_values = " ".join(str(employee.get(key, "")) for key in ["department_id", "department"]).casefold()
        if department and department not in department_values:
            continue
        searchable = " ".join(str(employee.get(key, "")) for key in ["employee_id", "employee_number", "display_name", "email", "entity_id", "department_id", "department", "country_code"]).casefold()
        if q and q not in searchable:
            continue
        rows.append(employee)
    rows.sort(key=lambda item: (str(item.get("entity_id", "")), str(item.get("employee_number", "")), str(item.get("display_name", ""))))
    return rows


def recalculate_batch_totals(batch_id: str) -> Optional[Dict[str, Any]]:
    batches = read_json("payroll_batches")
    batch = find_by(batches, "batch_id", batch_id)
    if not batch:
        return None
    records = [record for record in read_json("payroll_records") if record.get("batch_id") == batch_id and record.get("active_status", "active") == "active"]
    batch.update({
        "record_count": len(records),
        "gross_total": sum(money(r.get("gross_total")) for r in records),
        "deduction_total": sum(money(r.get("deduction_total")) for r in records),
        "net_total": sum(money(r.get("net_pay")) for r in records),
        "employer_cost_total": sum(money(r.get("employer_cost_total")) for r in records),
        "company_total_cost": sum(money(r.get("company_total_cost")) for r in records),
        "updated_at": now_iso(),
    })
    write_json("payroll_batches", batches)
    return batch


def create_record_snapshot(batch: Dict[str, Any], profile: Dict[str, Any]) -> Dict[str, Any]:
    params = active_parameters(batch.get("entity_id") or "default")
    return {
        "record_id": new_id("payrec"),
        "batch_id": batch["batch_id"],
        "entity_id": batch.get("entity_id") or profile.get("entity_id") or "default",
        "payroll_month": batch["payroll_month"],
        "employee_id": profile.get("employee_id"),
        "employee_number": profile.get("employee_number"),
        "display_name": profile.get("display_name"),
        "employee_snapshot": {
            "employee_id": profile.get("employee_id"),
            "employee_number": profile.get("employee_number"),
            "display_name": profile.get("display_name"),
            "email": profile.get("email"),
            "entity_id": profile.get("entity_id"),
            "department_id": profile.get("department_id"),
            "employment_type": profile.get("employment_type"),
        },
        "salary_master_snapshot": dict(profile),
        "attendance": default_attendance(params),
        "variable_earnings": [],
        "variable_deductions": [],
        "earnings": [],
        "deductions": [],
        "employer_costs": [],
        "calculation_messages": [],
        "gross_total": 0,
        "deduction_total": 0,
        "net_pay": 0,
        "employer_cost_total": 0,
        "company_total_cost": 0,
        "status": "master_snapshot",
        "employee_feedback_status": "not_sent",
        "payment_status": "not_prepared",
        "active_status": "active",
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def csv_safe_cell(value: Any) -> str:
    text = "" if value is None else str(value)
    if text.startswith(("=", "+", "-", "@", "\t", "\r", "\n")):
        return "'" + text
    return text


def records_to_csv(rows: List[Dict[str, Any]], fieldnames: List[str]) -> bytes:
    output = StringIO()
    writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
    writer.writeheader()
    for row in rows:
        writer.writerow({key: csv_safe_cell(row.get(key, "")) for key in fieldnames})
    return output.getvalue().encode("utf-8-sig")


def render_payslip_html(record: Dict[str, Any], batch: Dict[str, Any]) -> str:
    def row(label: str, amount: Any) -> str:
        return f"<tr><td>{html.escape(label)}</td><td class='amount'>¥{money(amount):,}</td></tr>"

    employee_email = employee_email_for_record(record)
    earnings_rows = "".join(row(item.get("label") or item.get("code") or "earning", item.get("amount")) for item in record.get("earnings") or [])
    deduction_rows = "".join(row(item.get("label") or item.get("code") or "deduction", item.get("amount")) for item in record.get("deductions") or [])
    employer_rows = "".join(row(item.get("label") or item.get("code") or "employer_cost", item.get("amount")) for item in record.get("employer_costs") or [])
    messages = "".join(f"<li>{html.escape(str(message))}</li>" for message in record.get("calculation_messages") or [])
    if not messages:
        messages = "<li>No calculation warnings recorded.</li>"
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8"><title>Payslip {html.escape(str(record.get('display_name','')))}</title>
<style>
body{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;margin:32px;color:#1f2937;line-height:1.45}}.head{{border-bottom:3px solid #0f172a;padding-bottom:16px;margin-bottom:18px}}.meta{{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 24px;background:#f8fafc;border:1px solid #e2e8f0;border-radius:10px;padding:14px;margin:16px 0}}.grid{{display:grid;grid-template-columns:1fr 1fr;gap:24px}}table{{width:100%;border-collapse:collapse;margin-top:12px}}td,th{{border-bottom:1px solid #e5e7eb;padding:8px;text-align:left}}.amount{{text-align:right;font-variant-numeric:tabular-nums}}.net{{font-size:30px;color:#0369a1;font-weight:700}}.note{{background:#fff7ed;border:1px solid #fed7aa;padding:12px;border-radius:8px;margin:14px 0}}.muted{{color:#64748b;font-size:12px}}@media print{{body{{margin:16mm}}.note{{break-inside:avoid}}a{{color:inherit;text-decoration:none}}}}
</style>
</head><body><div class="head"><h1>給与明細 / Payroll Payslip</h1><p class="muted">HTML payslip. Use browser print/save as PDF if PDF output is required.</p></div>
<div class="meta"><div><strong>Payroll month:</strong> {html.escape(str(batch.get('payroll_month','')))}</div><div><strong>Payment date:</strong> {html.escape(str(batch.get('payment_date','')))}</div><div><strong>Batch ID:</strong> {html.escape(str(batch.get('batch_id','')))}</div><div><strong>Record ID:</strong> {html.escape(str(record.get('record_id','')))}</div><div><strong>Employee:</strong> {html.escape(str(record.get('employee_number','')))} · {html.escape(str(record.get('display_name','')))}</div><div><strong>Email:</strong> {html.escape(employee_email or 'Missing')}</div></div>
<div class="grid"><section><h2>Earnings / 支給</h2><table>{earnings_rows}</table></section><section><h2>Deductions / 控除</h2><table>{deduction_rows}</table></section></div>
<section><h2>Employer Costs / 会社負担</h2><table>{employer_rows}</table></section>
<h2>Net Pay / 差引支給額</h2><p class="net">¥{money(record.get('net_pay')):,}</p>
<p>Gross: ¥{money(record.get('gross_total')):,} · Deductions: ¥{money(record.get('deduction_total')):,} · Employer cost: ¥{money(record.get('employer_cost_total')):,} · Company total: ¥{money(record.get('company_total_cost')):,}</p>
<div class="note"><strong>Review note:</strong> Japan statutory values in this MVP are parameter-assisted. Income tax/resident tax are manual-review fields. HR/payroll/tax specialists must confirm final values before payment.</div>
<h2>Calculation messages / 計算メッセージ</h2><ul>{messages}</ul></body></html>"""


def parse_body(handler: BaseHTTPRequestHandler) -> Dict[str, Any]:
    length = int(handler.headers.get("Content-Length") or 0)
    if length <= 0:
        return {}
    limit = MAX_POST_BYTES if "/upload" in handler.path or "/import" in handler.path else MAX_POST_FORM_BYTES
    if length > limit:
        return {"_error": f"Request body exceeds {limit // 1024 // 1024}MB limit", "_status": 413}
    raw = handler.rfile.read(length)
    content_type = handler.headers.get("Content-Type", "")
    if "application/json" in content_type:
        try:
            data = json.loads(raw.decode("utf-8"))
            return data if isinstance(data, dict) else {"items": data}
        except json.JSONDecodeError:
            return {}
    parsed = urllib.parse.parse_qs(raw.decode("utf-8"), keep_blank_values=True)
    return {key: values[-1] if values else "" for key, values in parsed.items()}


class TacaipayHandler(BaseHTTPRequestHandler):
    server_version = "TACAIPAYJP/0.1"

    def log_message(self, fmt: str, *args: Any) -> None:  # quieter local app
        sys.stderr.write("%s - - [%s] %s\n" % (self.address_string(), self.log_date_time_string(), fmt % args))

    def send_json(self, payload: Any, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_text(self, body: str, status: int = 200, content_type: str = "text/html; charset=utf-8") -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def send_csv(self, body: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def actor(self) -> str:
        return self.headers.get("X-TACAI-User") or "local-user"

    def do_GET(self) -> None:
        ensure_database()
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/health":
                return self.send_json({"ok": True, "module": MODULE_KEY, "label": MODULE_LABEL, "base_url": APP_BASE_URL, "default_port": DEFAULT_PORT, "time": now_iso()})
            if path in {"/", "/dashboard"}:
                index = FRONTEND_DIR / "index.html"
                if index.exists():
                    return self.send_text(index.read_text(encoding="utf-8"))
                return self.send_text("<h1>TACAIPAY JP</h1>")
            if path == "/api/v1/config":
                return self.send_json({
                    "module": MODULE_KEY,
                    "label": MODULE_LABEL,
                    "base_url": APP_BASE_URL,
                    "default_port": DEFAULT_PORT,
                    "languages": ["zh", "ja", "en"],
                    "statuses": self.statuses(),
                    "mvp_limitations": [
                        "Japan statutory tax/social insurance values are parameter-assisted.",
                        "Income tax and resident tax require manual review/input.",
                        "Payslips are generated as printable HTML.",
                        "Email sending is a dry-run metadata workflow unless SMTP is added later.",
                    ],
                })
            if path == "/api/v1/employeeadmin-employees":
                return self.send_json({"employees": filter_employeeadmin_employees(query)})
            if path == "/api/v1/salary-master":
                return self.send_json({"records": read_json("salary_master")})
            if path == "/api/v1/batches":
                return self.send_json({"records": read_json("payroll_batches")})
            if path == "/api/v1/records":
                records = read_json("payroll_records")
                batch_id = (query.get("batch_id") or [""])[0]
                if batch_id:
                    records = [r for r in records if r.get("batch_id") == batch_id]
                return self.send_json({"records": records})
            if path == "/api/v1/payroll-items":
                return self.send_json({"records": read_json("payroll_item_definitions")})
            if path == "/api/v1/parameters":
                return self.send_json({"records": read_json("payroll_parameters")})
            if path == "/api/v1/payslips":
                return self.send_json({"records": read_json("payslip_documents")})
            if path == "/api/v1/email-deliveries":
                return self.send_json({"records": read_json("email_deliveries")})
            if path == "/api/v1/feedback":
                return self.send_json({"records": read_json("payslip_feedback")})
            if path == "/api/v1/audit-logs":
                return self.send_json({"records": read_json("audit_logs")[-500:]})
            if path.startswith("/api/v1/reports/"):
                return self.handle_report(path)
            match = re.match(r"^/api/v1/payslips/([^/]+)/download$", path)
            if match:
                return self.download_payslip(match.group(1))
            match = re.match(r"^/api/v1/batches/([^/]+)/(finance-export|payment-export)\.csv$", path)
            if match:
                return self.export_batch_csv(match.group(1), match.group(2))
            return self.send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)
        except Exception as exc:
            return self.send_json({"error": "server_error", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_POST(self) -> None:
        ensure_database()
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        payload = parse_body(self)
        try:
            if path == "/api/v1/salary-master":
                return self.create_salary_profile(payload)
            if path == "/api/v1/salary-master/import-employeeadmin":
                return self.import_employeeadmin(payload)
            if path == "/api/v1/batches":
                return self.create_batch(payload)
            if path == "/api/v1/payroll-items":
                return self.create_generic("payroll_item_definitions", payload, "item_id", "item")
            if path == "/api/v1/parameters":
                return self.create_generic("payroll_parameters", payload, "parameter_id", "param")
            if path == "/api/v1/feedback":
                return self.create_feedback(payload)
            match = re.match(r"^/api/v1/salary-master/([^/]+)/deactivate$", path)
            if match:
                return self.deactivate_salary_profile(match.group(1))
            match = re.match(r"^/api/v1/batches/([^/]+)/(.+)$", path)
            if match:
                return self.batch_action(match.group(1), match.group(2), payload)
            match = re.match(r"^/api/v1/records/([^/]+)/adjust$", path)
            if match:
                return self.adjust_record(match.group(1), payload)
            match = re.match(r"^/api/v1/feedback/([^/]+)/resolve$", path)
            if match:
                return self.resolve_feedback(match.group(1), payload)
            return self.send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            return self.send_json({"error": "validation_error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except Exception as exc:
            return self.send_json({"error": "server_error", "message": str(exc)}, HTTPStatus.INTERNAL_SERVER_ERROR)

    def do_PUT(self) -> None:
        ensure_database()
        path = urllib.parse.urlparse(self.path).path.rstrip("/") or "/"
        payload = parse_body(self)
        try:
            match = re.match(r"^/api/v1/salary-master/([^/]+)$", path)
            if match:
                return self.update_generic("salary_master", "profile_id", match.group(1), payload)
            match = re.match(r"^/api/v1/records/([^/]+)$", path)
            if match:
                return self.update_record(match.group(1), payload)
            match = re.match(r"^/api/v1/payroll-items/([^/]+)$", path)
            if match:
                return self.update_generic("payroll_item_definitions", "item_id", match.group(1), payload)
            match = re.match(r"^/api/v1/parameters/([^/]+)$", path)
            if match:
                return self.update_generic("payroll_parameters", "parameter_id", match.group(1), payload)
            return self.send_json({"error": "not_found", "path": path}, HTTPStatus.NOT_FOUND)
        except ValueError as exc:
            return self.send_json({"error": "validation_error", "message": str(exc)}, HTTPStatus.BAD_REQUEST)

    def statuses(self) -> Dict[str, List[str]]:
        return {
            "batch": BATCH_STATUSES,
            "record": RECORD_STATUSES,
            "transitions": {key: sorted(value) for key, value in ALLOWED_BATCH_TRANSITIONS.items()},
        }

    def create_generic(self, store: str, payload: Dict[str, Any], id_key: str, prefix: str) -> None:
        with DATA_LOCK:
            records = read_json(store)
            record = dict(payload)
            record.setdefault(id_key, new_id(prefix))
            record.setdefault("status", "active")
            record.setdefault("created_at", now_iso())
            record["updated_at"] = now_iso()
            records.append(record)
            write_json(store, records)
            append_audit(f"{store}_create", record[id_key], self.actor(), after=record)
            return self.send_json({"record": record}, HTTPStatus.CREATED)

    def update_generic(self, store: str, id_key: str, record_id: str, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            records = read_json(store)
            record = find_by(records, id_key, record_id)
            if not record:
                return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            before = dict(record)
            record.update(payload)
            record[id_key] = record_id
            record["updated_at"] = now_iso()
            record["updated_by"] = self.actor()
            write_json(store, records)
            append_audit(f"{store}_update", record_id, self.actor(), before=before, after=record)
            return self.send_json({"record": record})

    def create_salary_profile(self, payload: Dict[str, Any]) -> None:
        employee_id = payload.get("employee_id") or payload.get("employee_number")
        if not employee_id:
            raise ValueError("employee_id or employee_number is required")
        with DATA_LOCK:
            profiles = read_json("salary_master")
            duplicate = next((p for p in profiles if p.get("employee_id") == employee_id and p.get("status") == "active"), None)
            if duplicate:
                raise ValueError("active salary profile already exists for this employee")
            profile = salary_profile_from_employee(payload, self.actor())
            profile.update({k: v for k, v in payload.items() if k not in {"profile_id", "created_at", "created_by"}})
            profile.setdefault("profile_id", new_id("salprof"))
            profile["updated_at"] = now_iso()
            profile["updated_by"] = self.actor()
            profiles.append(profile)
            write_json("salary_master", profiles)
            append_audit("salary_profile_create", profile["profile_id"], self.actor(), after=profile)
            return self.send_json({"record": profile}, HTTPStatus.CREATED)

    def import_employeeadmin(self, payload: Dict[str, Any]) -> None:
        employees = payload.get("employees") if isinstance(payload.get("employees"), list) else load_employeeadmin_employees()
        created = 0
        updated = 0
        skipped = 0
        incomplete = 0
        imported: List[Dict[str, Any]] = []
        with DATA_LOCK:
            profiles = read_json("salary_master")
            by_employee = {p.get("employee_id"): p for p in profiles if p.get("employee_id")}
            for employee in employees:
                normalized = normalize_employee(employee)
                if not normalized.get("employee_id") or normalized.get("country_code") not in {"JP", "JPN", "", None}:
                    skipped += 1
                    continue
                profile = salary_profile_from_employee(employee, self.actor())
                if not profile.get("base_salary") or not profile.get("bank"):
                    incomplete += 1
                existing = by_employee.get(profile["employee_id"])
                if existing:
                    before = dict(existing)
                    for key in ["employee_number", "display_name", "email", "entity_id", "department_id", "department", "employment_type", "bank"]:
                        existing[key] = profile.get(key)
                    existing["updated_at"] = now_iso()
                    existing["updated_by"] = self.actor()
                    existing["source"] = "employeeadmin"
                    imported.append(existing)
                    updated += 1
                    append_audit("salary_profile_import_update", existing["profile_id"], self.actor(), before=before, after=existing)
                else:
                    profiles.append(profile)
                    by_employee[profile["employee_id"]] = profile
                    imported.append(profile)
                    created += 1
                    append_audit("salary_profile_import_create", profile["profile_id"], self.actor(), after=profile)
            write_json("salary_master", profiles)
        return self.send_json({"created": created, "updated": updated, "skipped": skipped, "incomplete": incomplete, "records": imported})

    def deactivate_salary_profile(self, profile_id: str) -> None:
        with DATA_LOCK:
            profiles = read_json("salary_master")
            profile = find_by(profiles, "profile_id", profile_id)
            if not profile:
                return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            before = dict(profile)
            profile["status"] = "inactive"
            profile["effective_to"] = now_iso()[:10]
            profile["updated_at"] = now_iso()
            profile["updated_by"] = self.actor()
            write_json("salary_master", profiles)
            append_audit("salary_profile_deactivate", profile_id, self.actor(), before=before, after=profile)
            return self.send_json({"record": profile})

    def create_batch(self, payload: Dict[str, Any]) -> None:
        payroll_month = payload.get("payroll_month")
        if not re.match(r"^\d{4}-\d{2}$", str(payroll_month or "")):
            raise ValueError("payroll_month must be YYYY-MM")
        entity_id = payload.get("entity_id") or "default"
        payroll_type = payload.get("payroll_type") or "monthly"
        with DATA_LOCK:
            batches = read_json("payroll_batches")
            duplicate = next((b for b in batches if b.get("entity_id") == entity_id and b.get("payroll_month") == payroll_month and b.get("payroll_type") == payroll_type and b.get("active_status", "active") == "active"), None)
            if duplicate:
                raise ValueError("active batch already exists for entity/month/type")
            batch = {
                "batch_id": new_id("batch"),
                "entity_id": entity_id,
                "payroll_month": payroll_month,
                "payroll_type": payroll_type,
                "period_start": payload.get("period_start") or f"{payroll_month}-01",
                "period_end": payload.get("period_end") or "",
                "payment_date": payload.get("payment_date") or "",
                "status": "draft_created",
                "version_no": 1,
                "record_count": 0,
                "gross_total": 0,
                "deduction_total": 0,
                "net_total": 0,
                "employer_cost_total": 0,
                "company_total_cost": 0,
                "active_status": "active",
                "created_at": now_iso(),
                "created_by": self.actor(),
                "updated_at": now_iso(),
            }
            batches.append(batch)
            write_json("payroll_batches", batches)
            append_audit("batch_create", batch["batch_id"], self.actor(), after=batch)
            return self.send_json({"record": batch}, HTTPStatus.CREATED)

    def batch_action(self, batch_id: str, action: str, payload: Dict[str, Any]) -> None:
        action = action.replace("-", "_")
        if action == "load_master":
            return self.load_master(batch_id)
        if action == "calculate":
            return self.calculate_batch(batch_id)
        if action in {"hr_review", "first_approve", "final_approve", "finalize"}:
            transitions = {"hr_review": "hr_reviewed", "first_approve": "first_approved", "final_approve": "final_approved", "finalize": "finalized"}
            return self.transition_batch(batch_id, transitions[action], action)
        if action == "payslips/generate" or action == "payslips_generate":
            return self.generate_payslips(batch_id, payload)
        if action == "payslips/send" or action == "payslips_send":
            return self.send_payslips(batch_id, payload)
        if action == "payment/prepare" or action == "payment_prepare":
            return self.prepare_payment(batch_id)
        if action == "payment/mark_paid" or action == "payment_mark_paid":
            return self.mark_paid(batch_id)
        return self.send_json({"error": "unsupported_action", "action": action}, HTTPStatus.BAD_REQUEST)

    def load_master(self, batch_id: str) -> None:
        with DATA_LOCK:
            batches = read_json("payroll_batches")
            batch = find_by(batches, "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "master_loaded")
            if batch.get("status") in BATCH_LOCKED_STATUSES:
                raise ValueError("batch is locked")
            existing_records = read_json("payroll_records")
            if any(r.get("batch_id") == batch_id for r in existing_records):
                raise ValueError("batch already has payroll records")
            profiles = [p for p in read_json("salary_master") if p.get("status") == "active" and p.get("country_code", "JP") == "JP"]
            if batch.get("entity_id") != "default":
                profiles = [p for p in profiles if p.get("entity_id") == batch.get("entity_id")]
            new_records = [create_record_snapshot(batch, profile) for profile in profiles]
            existing_records.extend(new_records)
            batch["status"] = "master_loaded"
            batch["loaded_at"] = now_iso()
            batch["loaded_by"] = self.actor()
            write_json("payroll_records", existing_records)
            write_json("payroll_batches", batches)
            recalculate_batch_totals(batch_id)
            append_audit("batch_load_master", batch_id, self.actor(), after={"record_count": len(new_records)})
            return self.send_json({"loaded": len(new_records), "records": new_records, "batch": recalculate_batch_totals(batch_id)})

    def calculate_batch(self, batch_id: str) -> None:
        with DATA_LOCK:
            records = read_json("payroll_records")
            batches = read_json("payroll_batches")
            batch = find_by(batches, "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "calculated")
            if batch.get("status") in BATCH_LOCKED_STATUSES:
                raise ValueError("batch is locked")
            params = active_parameters(batch.get("entity_id") or "default")
            changed = 0
            warnings = []
            for record in records:
                if record.get("batch_id") != batch_id or record.get("active_status", "active") != "active":
                    continue
                result, messages = calculate_payroll_record(record, params)
                record.update(result)
                record["calculation_messages"] = messages
                record["status"] = "calculated"
                record["calculated_at"] = now_iso()
                record["calculated_by"] = self.actor()
                record["updated_at"] = now_iso()
                warnings.extend([{"record_id": record["record_id"], "message": message} for message in messages if "manual" in message.lower() or "confirm" in message.lower()])
                changed += 1
            batch["status"] = "calculated"
            batch["calculated_at"] = now_iso()
            batch["calculated_by"] = self.actor()
            write_json("payroll_records", records)
            write_json("payroll_batches", batches)
            updated_batch = recalculate_batch_totals(batch_id)
            append_audit("batch_calculate", batch_id, self.actor(), after={"records": changed, "warnings": len(warnings)})
            return self.send_json({"calculated": changed, "warnings": warnings, "batch": updated_batch})

    def transition_batch(self, batch_id: str, status: str, action: str) -> None:
        with DATA_LOCK:
            batches = read_json("payroll_batches")
            records = read_json("payroll_records")
            batch = find_by(batches, "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, status)
            before = dict(batch)
            batch["status"] = status
            batch[f"{status}_at"] = now_iso()
            batch[f"{status}_by"] = self.actor()
            batch["updated_at"] = now_iso()
            for record in records:
                if record.get("batch_id") == batch_id:
                    record["status"] = status
                    record["updated_at"] = now_iso()
            write_json("payroll_batches", batches)
            write_json("payroll_records", records)
            if status == "finalized":
                self.create_confirmation(batch_id, "finalized")
            append_audit(f"batch_{action}", batch_id, self.actor(), before=before, after=batch)
            return self.send_json({"record": batch})

    def create_confirmation(self, batch_id: str, confirmation_type: str) -> None:
        confirmations = read_json("payroll_confirmations")
        confirmations.append({
            "confirmation_id": new_id("confirm"),
            "batch_id": batch_id,
            "confirmation_type": confirmation_type,
            "confirmed_by": self.actor(),
            "confirmed_at": now_iso(),
        })
        write_json("payroll_confirmations", confirmations)

    def update_record(self, record_id: str, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            records = read_json("payroll_records")
            record = find_by(records, "record_id", record_id)
            if not record:
                return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            batches = read_json("payroll_batches")
            batch = find_by(batches, "batch_id", record.get("batch_id"))
            if batch and batch.get("status") in BATCH_LOCKED_STATUSES:
                raise ValueError("batch is locked")
            if batch and batch.get("status") in {"master_loaded", "calculated"}:
                require_batch_transition(batch, "attendance_input")
                batch["status"] = "attendance_input"
                batch["attendance_input_at"] = now_iso()
                batch["attendance_input_by"] = self.actor()
                batch["updated_at"] = now_iso()
            before = dict(record)
            for key in ["attendance", "variable_earnings", "variable_deductions", "manual_income_tax", "manual_resident_tax", "employee_feedback_status"]:
                if key in payload:
                    if key == "attendance" and isinstance(payload["attendance"], dict):
                        att = payload["attendance"]
                        if "work_days" in att and "regular_hours" not in att:
                            att["regular_hours"] = max(int(att.get("work_days") or 0), 0) * 8
                    record[key] = payload[key]
            record["status"] = "attendance_entered"
            record["updated_at"] = now_iso()
            record["updated_by"] = self.actor()
            write_json("payroll_records", records)
            if batch:
                write_json("payroll_batches", batches)
            append_audit("record_update", record_id, self.actor(), before=before, after=record)
            return self.send_json({"record": record})

    def adjust_record(self, record_id: str, payload: Dict[str, Any]) -> None:
        reason = payload.get("reason")
        if not reason:
            raise ValueError("adjustment reason is required")
        return self.update_record(record_id, payload)

    def generate_payslips(self, batch_id: str, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            batches = read_json("payroll_batches")
            batch = find_by(batches, "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "payslips_generated")
            regenerate = bool(payload.get("regenerate", False))
            records = [r for r in read_json("payroll_records") if r.get("batch_id") == batch_id and r.get("active_status", "active") == "active"]
            docs = read_json("payslip_documents")
            existing_docs = [doc for doc in docs if doc.get("batch_id") == batch_id and doc.get("status") != "voided"]
            if existing_docs and not regenerate:
                raise ValueError("payslips already generated; pass regenerate=true to create a new set")
            if regenerate:
                for doc in existing_docs:
                    doc["status"] = "voided"
                    doc["voided_at"] = now_iso()
                    doc["voided_by"] = self.actor()
            generated = []
            for record in records:
                payslip_id = new_id("payslip")
                safe_employee = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(record.get("employee_number") or "employee"))
                filename = f"{payslip_id}_{safe_employee}.html"
                path = PAYSLIP_DIR / filename
                path.write_text(render_payslip_html(record, batch), encoding="utf-8")
                messages = record.get("calculation_messages") or []
                employee_email = employee_email_for_record(record)
                doc = {
                    "payslip_id": payslip_id,
                    "batch_id": batch_id,
                    "record_id": record.get("record_id"),
                    "employee_id": record.get("employee_id"),
                    "employee_number": record.get("employee_number"),
                    "display_name": record.get("display_name"),
                    "employee_email": employee_email,
                    "payroll_month": batch.get("payroll_month"),
                    "payment_date": batch.get("payment_date"),
                    "document_type": "html_payslip",
                    "mime_type": "text/html",
                    "review_required": True if messages else False,
                    "file_name": filename,
                    "file_path": str(path),
                    "status": "generated",
                    "generated_at": now_iso(),
                    "generated_by": self.actor(),
                }
                docs.append(doc)
                generated.append(doc)
                record["employee_feedback_status"] = "payslip_generated"
                record["status"] = "payslips_generated"
                record["updated_at"] = now_iso()
            batch["status"] = "payslips_generated" if generated else batch.get("status")
            batch["payslips_generated_at"] = now_iso()
            batch["payslips_generated_by"] = self.actor()
            batch["updated_at"] = now_iso()
            all_records = read_json("payroll_records")
            record_updates = {record.get("record_id"): record for record in records}
            for index, stored in enumerate(all_records):
                replacement = record_updates.get(stored.get("record_id"))
                if replacement:
                    all_records[index] = replacement
            write_json("payslip_documents", docs)
            write_json("payroll_records", all_records)
            write_json("payroll_batches", batches)
            append_audit("payslips_generate", batch_id, self.actor(), after={"count": len(generated), "regenerate": regenerate})
            return self.send_json({"generated": len(generated), "records": generated, "batch": batch})

    def send_payslips(self, batch_id: str, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            dry_run = bool(payload.get("dry_run", True))
            batches = read_json("payroll_batches")
            batch = find_by(batches, "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "payslip_sent")
            docs = [doc for doc in read_json("payslip_documents") if doc.get("batch_id") == batch_id and doc.get("status") != "voided"]
            records = read_json("payroll_records")
            records_by_id = {record.get("record_id"): record for record in records}
            deliveries = read_json("email_deliveries")
            created = []
            missing = []
            for doc in docs:
                record = records_by_id.get(doc.get("record_id")) or {}
                recipient = str(payload.get("recipient_override") or doc.get("employee_email") or employee_email_for_record(record) or "").strip()
                status = "dry_run" if dry_run and recipient else "queued" if recipient else "missing_recipient"
                if not recipient:
                    missing.append(doc.get("employee_number") or doc.get("record_id"))
                delivery = {
                    "delivery_id": new_id("email"),
                    "batch_id": batch_id,
                    "payslip_id": doc.get("payslip_id"),
                    "record_id": doc.get("record_id"),
                    "recipient": recipient,
                    "subject": f"Payroll payslip {doc.get('payroll_month') or batch.get('payroll_month')} {doc.get('employee_number')}",
                    "status": status,
                    "dry_run": dry_run,
                    "attempt_count": 0,
                    "created_at": now_iso(),
                    "created_by": self.actor(),
                }
                deliveries.append(delivery)
                created.append(delivery)
                if record:
                    record["employee_feedback_status"] = "payslip_sent" if recipient else "missing_recipient"
                    record["status"] = "payslip_sent" if recipient else record.get("status")
                    record["updated_at"] = now_iso()
            batch["status"] = "payslip_sent"
            batch["payslip_sent_at"] = now_iso()
            batch["payslip_sent_by"] = self.actor()
            batch["payslip_delivery_missing_count"] = len(missing)
            batch["updated_at"] = now_iso()
            write_json("email_deliveries", deliveries)
            write_json("payroll_records", records)
            write_json("payroll_batches", batches)
            append_audit("payslips_send", batch_id, self.actor(), after={"count": len(created), "dry_run": dry_run, "missing_recipients": len(missing)})
            return self.send_json({
                "deliveries": len(created),
                "missing_recipients": len(missing),
                "dry_run": dry_run,
                "recipient_preview": [{"employee_number": d.get("subject", "").split()[-1], "recipient": d.get("recipient"), "status": d.get("status")} for d in created],
            })

    def download_payslip(self, payslip_id: str) -> None:
        doc = find_by(read_json("payslip_documents"), "payslip_id", payslip_id)
        if not doc:
            return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
        path = Path(doc.get("file_path") or "")
        try:
            path.resolve().relative_to(PAYSLIP_DIR.resolve())
        except Exception:
            return self.send_json({"error": "invalid_payslip_path"}, HTTPStatus.BAD_REQUEST)
        if not path.exists():
            return self.send_json({"error": "file_missing"}, HTTPStatus.NOT_FOUND)
        return self.send_text(path.read_text(encoding="utf-8"))

    def create_feedback(self, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            feedback = dict(payload)
            feedback.setdefault("feedback_id", new_id("fb"))
            feedback.setdefault("status", "open")
            feedback.setdefault("created_at", now_iso())
            feedback.setdefault("created_by", self.actor())
            items = read_json("payslip_feedback")
            items.append(feedback)
            write_json("payslip_feedback", items)
            record_id = feedback.get("record_id")
            if record_id:
                records = read_json("payroll_records")
                record = find_by(records, "record_id", record_id)
                if record:
                    record["employee_feedback_status"] = feedback.get("feedback_type") or "feedback_received"
                    write_json("payroll_records", records)
            append_audit("feedback_create", feedback["feedback_id"], self.actor(), after=feedback)
            return self.send_json({"record": feedback}, HTTPStatus.CREATED)

    def resolve_feedback(self, feedback_id: str, payload: Dict[str, Any]) -> None:
        with DATA_LOCK:
            items = read_json("payslip_feedback")
            feedback = find_by(items, "feedback_id", feedback_id)
            if not feedback:
                return self.send_json({"error": "not_found"}, HTTPStatus.NOT_FOUND)
            before = dict(feedback)
            feedback["status"] = "resolved"
            feedback["resolution_note"] = payload.get("resolution_note") or "resolved"
            feedback["resolved_at"] = now_iso()
            feedback["resolved_by"] = self.actor()
            write_json("payslip_feedback", items)
            append_audit("feedback_resolve", feedback_id, self.actor(), before=before, after=feedback)
            return self.send_json({"record": feedback})

    def prepare_payment(self, batch_id: str) -> None:
        with DATA_LOCK:
            batch = find_by(read_json("payroll_batches"), "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "payment_prepared")
            batch = self.set_batch_status(batch_id, "payment_prepared")
            records = read_json("payroll_records")
            payments = read_json("payment_records")
            for record in records:
                if record.get("batch_id") == batch_id:
                    record["payment_status"] = "payment_prepared"
                    record["status"] = "payment_prepared"
                    record["updated_at"] = now_iso()
            payments.append({
                "payment_id": new_id("payment"),
                "batch_id": batch_id,
                "status": "payment_prepared",
                "net_total": batch.get("net_total"),
                "prepared_at": now_iso(),
                "prepared_by": self.actor(),
            })
            write_json("payroll_records", records)
            write_json("payment_records", payments)
            append_audit("payment_prepare", batch_id, self.actor(), after=batch)
            return self.send_json({"record": batch})

    def mark_paid(self, batch_id: str) -> None:
        with DATA_LOCK:
            batch = find_by(read_json("payroll_batches"), "batch_id", batch_id)
            if not batch:
                return self.send_json({"error": "batch_not_found"}, HTTPStatus.NOT_FOUND)
            require_batch_transition(batch, "paid")
            batch = self.set_batch_status(batch_id, "paid")
            records = read_json("payroll_records")
            for record in records:
                if record.get("batch_id") == batch_id:
                    record["payment_status"] = "paid"
                    record["status"] = "paid"
                    record["updated_at"] = now_iso()
            payments = read_json("payment_records")
            for payment in payments:
                if payment.get("batch_id") == batch_id:
                    payment["status"] = "paid"
                    payment["paid_at"] = now_iso()
                    payment["paid_by"] = self.actor()
            write_json("payroll_records", records)
            write_json("payment_records", payments)
            append_audit("payment_mark_paid", batch_id, self.actor(), after=batch)
            return self.send_json({"record": batch})

    def set_batch_status(self, batch_id: str, status: str) -> Dict[str, Any]:
        batches = read_json("payroll_batches")
        batch = find_by(batches, "batch_id", batch_id)
        if not batch:
            raise ValueError("batch not found")
        batch["status"] = status
        batch[f"{status}_at"] = now_iso()
        batch[f"{status}_by"] = self.actor()
        batch["updated_at"] = now_iso()
        write_json("payroll_batches", batches)
        return batch

    def export_batch_csv(self, batch_id: str, export_type: str) -> None:
        records = [r for r in read_json("payroll_records") if r.get("batch_id") == batch_id]
        rows = []
        for record in records:
            rows.append({
                "payroll_month": record.get("payroll_month"),
                "employee_number": record.get("employee_number"),
                "display_name": record.get("display_name"),
                "gross_total": record.get("gross_total"),
                "deduction_total": record.get("deduction_total"),
                "net_pay": record.get("net_pay"),
                "employer_cost_total": record.get("employer_cost_total"),
                "company_total_cost": record.get("company_total_cost"),
                "payment_status": record.get("payment_status"),
            })
        body = records_to_csv(rows, ["payroll_month", "employee_number", "display_name", "gross_total", "deduction_total", "net_pay", "employer_cost_total", "company_total_cost", "payment_status"])
        exports = read_json("report_exports")
        exports.append({
            "export_id": new_id("export"),
            "batch_id": batch_id,
            "report_type": export_type,
            "row_count": len(rows),
            "total_amount": sum(money(r.get("net_pay")) for r in records),
            "created_at": now_iso(),
            "created_by": self.actor(),
        })
        write_json("report_exports", exports)
        append_audit("export_csv", batch_id, self.actor(), after={"type": export_type, "rows": len(rows)})
        return self.send_csv(body, f"tacaipayjp_{export_type}_{batch_id}.csv")

    def handle_report(self, path: str) -> None:
        batches = read_json("payroll_batches")
        records = read_json("payroll_records")
        if path.endswith("cost-summary") or path.endswith("summary"):
            return self.send_json({
                "batch_count": len(batches),
                "record_count": len(records),
                "gross_total": sum(money(r.get("gross_total")) for r in records),
                "deduction_total": sum(money(r.get("deduction_total")) for r in records),
                "net_total": sum(money(r.get("net_pay")) for r in records),
                "employer_cost_total": sum(money(r.get("employer_cost_total")) for r in records),
                "company_total_cost": sum(money(r.get("company_total_cost")) for r in records),
                "open_feedback": len([f for f in read_json("payslip_feedback") if f.get("status") == "open"]),
            })
        return self.send_json({"error": "report_not_found"}, HTTPStatus.NOT_FOUND)


def run(host: str, port: int) -> None:
    ensure_database()
    server = ThreadingHTTPServer((host, port), TacaipayHandler)
    print(f"TACAIPAY JP running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TACAIPAY JP payroll MVP")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
