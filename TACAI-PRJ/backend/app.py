"""Local web app for TACAI Prj - Japan HR Finance System.

This MVP intentionally uses only Python standard library modules so it can run
on a laptop without installing dependencies.
"""

from __future__ import annotations

import argparse
import cgi
import csv
import json
import os
import re
import smtplib
import ssl
from calendar import monthrange
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from http import cookies
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree
from zipfile import ZipFile

ROOT_DIR = Path(__file__).resolve().parents[1]
I18N_DIR = ROOT_DIR / "i18n"
SAMPLE_PAYROLL_PATH = ROOT_DIR / "docs" / "Payroll_Sample.xlsx"
PAYROLL_RECORDS_PATH = ROOT_DIR / "database" / "payroll_records.json"
PAYROLL_BATCHES_PATH = ROOT_DIR / "database" / "payroll_batches.json"
PAYROLL_VALIDATION_RESULTS_PATH = ROOT_DIR / "database" / "payroll_validation_results.json"
PAYSLIPS_PATH = ROOT_DIR / "database" / "payslips.json"
PAYSLIP_EMAIL_DELIVERIES_PATH = ROOT_DIR / "database" / "payslip_email_deliveries.json"
PAYSLIP_OUTPUT_DIR = ROOT_DIR / "database" / "generated" / "payslips"
PAYSLIP_EMAIL_ENABLED = os.environ.get("PAYSLIP_EMAIL_ENABLED", "true")
PAYSLIP_EMAIL_SENDER = os.environ.get("PAYSLIP_EMAIL_SENDER", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
PAYSLIP_EMAIL_SENDER_NAME = os.environ.get("PAYSLIP_EMAIL_SENDER_NAME", "TAC HR Admin").strip() or "TAC HR Admin"
PAYSLIP_EMAIL_REPLY_TO = os.environ.get("PAYSLIP_EMAIL_REPLY_TO", PAYSLIP_EMAIL_SENDER).strip() or PAYSLIP_EMAIL_SENDER
PAYSLIP_SMTP_HOST = os.environ.get("PAYSLIP_SMTP_HOST", "smtp.mxhichina.com").strip() or "smtp.mxhichina.com"
PAYSLIP_SMTP_PORT = os.environ.get("PAYSLIP_SMTP_PORT", "465").strip() or "465"
PAYSLIP_SMTP_USERNAME = os.environ.get("PAYSLIP_SMTP_USERNAME", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
PAYSLIP_SMTP_PASSWORD = os.environ.get("PAYSLIP_SMTP_PASSWORD") or os.environ.get("ONBOARDING_SMTP_PASSWORD", "")
PAYSLIP_SMTP_USE_TLS = os.environ.get("PAYSLIP_SMTP_USE_TLS", "true")
PAYSLIP_SMTP_USE_SSL = os.environ.get("PAYSLIP_SMTP_USE_SSL", "")
PAYSLIP_SMTP_TIMEOUT_SECONDS = os.environ.get("PAYSLIP_SMTP_TIMEOUT_SECONDS", "20")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
SALARY_PROFILES_PATH = ROOT_DIR / "database" / "salary_profiles.json"
PAYROLL_RULES_PATH = ROOT_DIR / "database" / "payroll_rules.json"
AUDIT_LOGS_PATH = ROOT_DIR / "database" / "audit_logs.json"
TAX_REFERENCE_CONFIG_PATH = ROOT_DIR / "database" / "tax_reference_config.json"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST}
LOCAL_ALLOWED_PORTS = {8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009}
FLASH_COOKIE = "tacai_flash"


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


APP_BASE_URL = local_base_url(8001)
EMPLOYEEADMIN_BASE_URL = local_base_url(8004)
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", local_base_url(8005)).strip() or local_base_url(8005)).rstrip("/")
USER_ADMIN_BASE_URL = local_base_url(8006)
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
LEGACY_SESSION_COOKIE_NAME = "tacai_session"
REQUIRED_MODULE_PERMISSION = "payroll.access"
DEFAULT_LANG = "zh"
SUPPORTED_LANGS = {"zh", "ja", "en"}

PAYMENT_FIELDS = [
    "Base Salary (基本給)",
    "Position Allowance (役職手当)",
    "Attendance Allowance (勤務手当)",
    "Housing Allowance (住宅手当)",
    "Taxable Transportation Allowance (課税通勤費)",
    "Non-taxable Transportation Allowance (非課税通勤費)",
    "Overtime Allowance (普通残業手当)",
    "Additional Payment (追加支給)",
]

DEDUCTION_FIELDS = [
    "Health Insurance (健康保険)",
    "Pension (厚生年金)",
    "Employment Insurance (雇用保険)",
    "Income Tax (所得税)",
    "Additional Deduction (追加控除)",
]

DERIVED_FIELDS = [
    "Gross Pay (総支給額)",
    "Total Deduction (控除合計)",
    "Net Pay (差引支給額)",
]

IDENTITY_FIELDS = [
    "Employee No. (社員No.)",
    "Employee Name (氏名)",
    "Payroll Month (給与月)",
]

PAYROLL_FIELD_LABEL_KEYS = {
    "Employee No. (社員No.)": "field.employee_no",
    "Employee Name (氏名)": "field.employee_name",
    "Payroll Month (給与月)": "field.payroll_month",
    "Base Salary (基本給)": "field.base_salary",
    "Position Allowance (役職手当)": "field.position_allowance",
    "Attendance Allowance (勤務手当)": "field.attendance_allowance",
    "Housing Allowance (住宅手当)": "field.housing_allowance",
    "Taxable Transportation Allowance (課税通勤費)": "field.taxable_transportation_allowance",
    "Non-taxable Transportation Allowance (非課税通勤費)": "field.non_taxable_transportation_allowance",
    "Overtime Allowance (普通残業手当)": "field.overtime_allowance",
    "Additional Payment (追加支給)": "field.additional_payment",
    "Health Insurance (健康保険)": "field.health_insurance",
    "Pension (厚生年金)": "field.pension",
    "Employment Insurance (雇用保険)": "field.employment_insurance",
    "Income Tax (所得税)": "field.income_tax",
    "Additional Deduction (追加控除)": "field.additional_deduction",
    "Gross Pay (総支給額)": "field.gross_pay",
    "Total Deduction (控除合計)": "field.total_deduction",
    "Net Pay (差引支給額)": "field.net_pay",
}

AMOUNT_INPUTS = [
    ("base_salary", "Base Salary (基本給)"),
    ("position_allowance", "Position Allowance (役職手当)"),
    ("attendance_allowance", "Attendance Allowance (勤務手当)"),
    ("housing_allowance", "Housing Allowance (住宅手当)"),
    ("taxable_transportation_allowance", "Taxable Transportation Allowance (課税通勤費)"),
    ("non_taxable_transportation_allowance", "Non-taxable Transportation Allowance (非課税通勤費)"),
    ("overtime_allowance", "Overtime Allowance (普通残業手当)"),
    ("health_insurance", "Health Insurance (健康保険)"),
    ("pension", "Pension (厚生年金)"),
    ("employment_insurance", "Employment Insurance (雇用保険)"),
    ("income_tax", "Income Tax (所得税)"),
    ("additional_payment", "Additional Payment (追加支給)"),
    ("additional_deduction", "Additional Deduction (追加控除)"),
]

HEADER_ALIASES = {
    "Employee No. (社員No.)": "Employee No. (社員No.)",
    "Employee No.": "Employee No. (社員No.)",
    "社員No.": "Employee No. (社員No.)",
    "社員No": "Employee No. (社員No.)",
    "Employee Name (氏名)": "Employee Name (氏名)",
    "Employee Name": "Employee Name (氏名)",
    "氏名": "Employee Name (氏名)",
    "Payroll Month (給与月)": "Payroll Month (給与月)",
    "Payroll Month": "Payroll Month (給与月)",
    "給与月": "Payroll Month (給与月)",
    "Base Salary (基本給)": "Base Salary (基本給)",
    "Base Salary": "Base Salary (基本給)",
    "基本給": "Base Salary (基本給)",
    "Position Allowance (役職手当)": "Position Allowance (役職手当)",
    "Position Allowance": "Position Allowance (役職手当)",
    "役職手当": "Position Allowance (役職手当)",
    "Attendance Allowance (勤務手当)": "Attendance Allowance (勤務手当)",
    "Attendance Allowance": "Attendance Allowance (勤務手当)",
    "勤務手当": "Attendance Allowance (勤務手当)",
    "Housing Allowance (住宅手当)": "Housing Allowance (住宅手当)",
    "Housing Allowance": "Housing Allowance (住宅手当)",
    "住宅手当": "Housing Allowance (住宅手当)",
    "Taxable Transportation Allowance (課税通勤費)": "Taxable Transportation Allowance (課税通勤費)",
    "Taxable Transportation Allowance": "Taxable Transportation Allowance (課税通勤費)",
    "課税通勤費": "Taxable Transportation Allowance (課税通勤費)",
    "Non-taxable Transportation Allowance (非課税通勤費)": "Non-taxable Transportation Allowance (非課税通勤費)",
    "Non-taxable Transportation Allowance": "Non-taxable Transportation Allowance (非課税通勤費)",
    "非課税通勤費": "Non-taxable Transportation Allowance (非課税通勤費)",
    "Overtime Allowance (普通残業手当)": "Overtime Allowance (普通残業手当)",
    "Overtime Allowance": "Overtime Allowance (普通残業手当)",
    "普通残業手当": "Overtime Allowance (普通残業手当)",
    "Health Insurance (健康保険)": "Health Insurance (健康保険)",
    "Health Insurance": "Health Insurance (健康保険)",
    "健康保険": "Health Insurance (健康保険)",
    "Pension (厚生年金)": "Pension (厚生年金)",
    "Pension": "Pension (厚生年金)",
    "厚生年金": "Pension (厚生年金)",
    "Employment Insurance (雇用保険)": "Employment Insurance (雇用保険)",
    "Employment Insurance": "Employment Insurance (雇用保険)",
    "雇用保険": "Employment Insurance (雇用保険)",
    "Income Tax (所得税)": "Income Tax (所得税)",
    "Income Tax": "Income Tax (所得税)",
    "所得税": "Income Tax (所得税)",
}

STATUS_LABEL_KEYS = {
    "Ready for HR confirmation": "status.ready",
    "Waiting for input": "status.waiting",
    "Saved": "status.saved",
    "Sample": "status.sample",
    "User_admin integrated": "status.user_admin_integrated",
    "EmployeeAdmin source": "status.employeeadmin_source",
    "External source": "status.external_source",
    "Unavailable": "status.unavailable",
    "Voided": "status.voided",
    "Blocked by Employee Master": "status.blocked_employee_master",
}

PAYROLL_SCHEMES = {
    "jp_simple": "Japan Monthly Fixed",
    "jp_monthly_prorated": "Japan Monthly Prorated by Attendance Days",
    "jp_hourly": "Japan Hourly",
    "jp_daily_consultant": "Japan Daily Consultant",
    "jp_hourly_consultant": "Japan Hourly Consultant",
    "jp_consultant_hourly_base_prorated": "Japan Consultant Hourly + Prorated Base",
    "cn_consultant_monthly": "China Monthly Consultant",
    "cn_dispatch_monthly_prorated": "China Dispatch Monthly Prorated",
    "cn_contractor_daily": "China Contractor Daily",
    "cn_contractor_hourly": "China Contractor Hourly",
    "sg_monthly_prorated": "Singapore Monthly Prorated",
}

PAYROLL_RULE_CALCULATION_TYPES = {
    "monthly_fixed": "Monthly fixed",
    "monthly_prorated_by_attendance_days": "Monthly salary × attendance days / monthly working days",
    "daily_rate_by_attendance_days": "Daily rate × attendance days",
    "hourly_rate_by_attendance_hours": "Hourly rate × attendance hours",
    "hourly_plus_base_prorated_by_standard_hours": "Hourly pay + base amount prorated by standard hours",
}

DEFAULT_PAYROLL_RULES = [
    {
        "rule_id": "rule-jp-monthly-fixed",
        "rule_code": "JP_MONTHLY_FIXED",
        "rule_name": "Japan monthly fixed",
        "country": "JP",
        "linked_scheme": "jp_simple",
        "calculation_type": "monthly_fixed",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Fixed monthly salary for Japan employees.",
    },
    {
        "rule_id": "rule-jp-monthly-prorated-days",
        "rule_code": "JP_MONTHLY_PRORATED_DAYS",
        "rule_name": "Japan monthly prorated by attendance days",
        "country": "JP",
        "linked_scheme": "jp_monthly_prorated",
        "calculation_type": "monthly_prorated_by_attendance_days",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Monthly salary multiplied by attendance days and divided by monthly working days.",
    },
    {
        "rule_id": "rule-jp-hourly",
        "rule_code": "JP_HOURLY",
        "rule_name": "Japan hourly",
        "country": "JP",
        "linked_scheme": "jp_hourly",
        "calculation_type": "hourly_rate_by_attendance_hours",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Hourly rate multiplied by attendance hours.",
    },
    {
        "rule_id": "rule-jp-daily-consultant",
        "rule_code": "JP_DAILY_CONSULTANT",
        "rule_name": "Japan daily consultant",
        "country": "JP",
        "linked_scheme": "jp_daily_consultant",
        "calculation_type": "daily_rate_by_attendance_days",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Daily consultant rate multiplied by working days.",
    },
    {
        "rule_id": "rule-jp-hourly-consultant",
        "rule_code": "JP_HOURLY_CONSULTANT",
        "rule_name": "Japan hourly consultant",
        "country": "JP",
        "linked_scheme": "jp_hourly_consultant",
        "calculation_type": "hourly_rate_by_attendance_hours",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Hourly consultant rate multiplied by working hours.",
    },
    {
        "rule_id": "rule-jp-consultant-hourly-base-prorated",
        "rule_code": "JP_CONSULTANT_HOURLY_BASE_PRORATED",
        "rule_name": "Japan consultant hourly plus prorated base",
        "country": "JP",
        "linked_scheme": "jp_consultant_hourly_base_prorated",
        "calculation_type": "hourly_plus_base_prorated_by_standard_hours",
        "parameters": {"standard_hours": "160", "cap_base_hours": "true"},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Hourly rate × actual hours plus monthly base amount prorated by actual hours / 160, with the base component capped at 160 hours.",
    },
    {
        "rule_id": "rule-cn-monthly-consultant",
        "rule_code": "CN_CONSULTANT_MONTHLY",
        "rule_name": "China monthly consultant",
        "country": "CN",
        "linked_scheme": "cn_consultant_monthly",
        "calculation_type": "monthly_fixed",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Fixed monthly consultant salary for China.",
    },
    {
        "rule_id": "rule-cn-dispatch-monthly-prorated",
        "rule_code": "CN_DISPATCH_MONTHLY_PRORATED",
        "rule_name": "China dispatch monthly prorated",
        "country": "CN",
        "linked_scheme": "cn_dispatch_monthly_prorated",
        "calculation_type": "monthly_prorated_by_attendance_days",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "China dispatch monthly salary prorated by attendance days.",
    },
    {
        "rule_id": "rule-cn-contractor-daily",
        "rule_code": "CN_CONTRACTOR_DAILY",
        "rule_name": "China contractor daily",
        "country": "CN",
        "linked_scheme": "cn_contractor_daily",
        "calculation_type": "daily_rate_by_attendance_days",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "China contractor daily rate multiplied by attendance days.",
    },
    {
        "rule_id": "rule-cn-contractor-hourly",
        "rule_code": "CN_CONTRACTOR_HOURLY",
        "rule_name": "China contractor hourly",
        "country": "CN",
        "linked_scheme": "cn_contractor_hourly",
        "calculation_type": "hourly_rate_by_attendance_hours",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "China contractor hourly rate multiplied by attendance hours.",
    },
    {
        "rule_id": "rule-sg-monthly-prorated",
        "rule_code": "SG_MONTHLY_PRORATED",
        "rule_name": "Singapore monthly prorated",
        "country": "SG",
        "linked_scheme": "sg_monthly_prorated",
        "calculation_type": "monthly_prorated_by_attendance_days",
        "parameters": {},
        "effective_from": "2026-01-01",
        "effective_to": "",
        "status": "active",
        "description": "Singapore monthly salary prorated by attendance days.",
    },
]

COUNTRY_OPTIONS = ["JP", "CN", "SG"]
WORK_LOCATION_OPTIONS = ["JP", "CN", "SG", "IN"]
CURRENCY_OPTIONS = ["JPY", "CNY", "SGD", "INR"]

PROFILE_DECIMAL_FIELDS = [
    "monthly_salary",
    "daily_rate",
    "hourly_rate",
    "standard_monthly_working_days",
    "standard_monthly_hours",
    "jp_dependent_count",
    "jp_monthly_health_insurance",
    "jp_monthly_pension",
    "jp_monthly_employment_insurance",
    "jp_fixed_resident_tax_monthly",
    "cn_monthly_social_insurance",
    "cn_monthly_housing_fund",
    "cn_monthly_special_additional_deductions",
    "cn_monthly_other_deductions",
    "cn_iit_cumulative_months_default",
    "sg_cpf_employee",
    "sg_cpf_employer",
]

UNIVERSAL_PAYROLL_DECIMAL_FIELDS = [
    "monthly_salary",
    "daily_rate",
    "hourly_rate",
    "attendance_days",
    "monthly_working_days",
    "attendance_hours",
    "calculated_base_pay",
    "base_component_pay",
    "additional_payment",
    "additional_deduction",
    "gross_pay",
    "total_deduction",
    "net_pay",
    "estimated_income_tax",
    "estimated_resident_tax",
    "confirmed_income_tax",
    "confirmed_resident_tax",
    "taxable_income_reference",
    "jp_health_insurance",
    "jp_pension",
    "jp_employment_insurance",
    "cn_social_insurance",
    "cn_housing_fund",
    "cn_special_additional_deductions",
    "cn_other_deductions",
    "sg_cpf_employee",
    "sg_cpf_employer",
    "hourly_pay",
]

UNIVERSAL_REGISTER_FIELDS = [
    "entity",
    "country",
    "work_location_country",
    "currency",
    "payroll_scheme",
    "attendance_days",
    "monthly_working_days",
    "attendance_hours",
    "calculated_base_pay",
    "tax_reference_mode",
    "tax_reference_city",
    "estimated_income_tax",
    "confirmed_income_tax",
    "tax_reference_status",
    "record_status",
]

TAX_REFERENCE_MODES = {
    "none": "None",
    "jp_income_tax_reference": "Japan Income Tax Reference",
    "cn_iit_reference": "China IIT Reference",
}

ROUNDING_POLICIES = {
    "round_to_yen": "Round to nearest yen",
    "floor_to_yen": "Floor to yen",
    "ceil_to_yen": "Ceil to yen",
}

PAYROLL_ELIGIBLE_EMPLOYEE_STATUSES = {"active", "employed", "probation"}

TAX_AMOUNT_FIELDS = {
    "estimated_income_tax",
    "estimated_resident_tax",
    "confirmed_income_tax",
    "confirmed_resident_tax",
    "taxable_income_reference",
}

COUNTRY_DEFAULTS = {
    "JP": {"lang": "ja", "currency": "JPY", "name_key": "country.jp"},
    "CN": {"lang": "zh", "currency": "CNY", "name_key": "country.cn"},
    "SG": {"lang": "en", "currency": "SGD", "name_key": "country.sg"},
}

AMOUNT_REPORT_KEYS = {
    "calculated_base_pay", "base_component_pay", "monthly_salary", "daily_rate", "hourly_rate", "hourly_pay",
    "additional_payment", "additional_deduction", "gross_pay", "total_deduction", "net_pay",
    "estimated_income_tax", "confirmed_income_tax", "estimated_resident_tax", "confirmed_resident_tax",
    "taxable_income_reference", "jp_health_insurance", "jp_pension", "jp_employment_insurance",
    "cn_social_insurance", "cn_housing_fund", "cn_special_additional_deductions", "cn_other_deductions",
    "sg_cpf_employee", "sg_cpf_employer",
}

PAYROLL_REPORT_TEMPLATES = {
    "ALL": {
        "title_key": "report.all.title",
        "language": "",
        "columns": [
            {"key": "payroll_month", "label_key": "field.payroll_month"},
            {"key": "employee_no", "label_key": "field.employee_no"},
            {"key": "employee_name", "label_key": "field.employee_name"},
            {"key": "country", "label_key": "field.country"},
            {"key": "currency", "label_key": "field.currency"},
            {"key": "payroll_scheme", "label_key": "field.payroll_scheme"},
            {"key": "gross_pay", "label_key": "field.gross_pay", "amount": True},
            {"key": "total_deduction", "label_key": "field.total_deduction", "amount": True},
            {"key": "net_pay", "label_key": "field.net_pay", "amount": True},
            {"key": "record_status", "label_key": "field.record_status"},
        ],
    },
    "CN": {
        "title_key": "report.cn.title",
        "language": "zh",
        "columns": [
            {"key": "payroll_month", "label_key": "field.payroll_month"},
            {"key": "employee_no", "label_key": "field.employee_no"},
            {"key": "employee_name", "label_key": "field.employee_name"},
            {"key": "entity", "label_key": "field.entity"},
            {"key": "work_location_country", "label_key": "field.work_location_country"},
            {"key": "currency", "label_key": "field.currency"},
            {"key": "tax_reference_city", "label_key": "field.tax_reference_city"},
            {"key": "payroll_scheme", "label_key": "field.payroll_scheme"},
            {"key": "monthly_working_days", "label_key": "field.monthly_working_days"},
            {"key": "attendance_days", "label_key": "field.attendance_days"},
            {"key": "attendance_hours", "label_key": "field.attendance_hours"},
            {"key": "hourly_rate", "label_key": "field.hourly_rate", "amount": True},
            {"key": "calculated_base_pay", "label_key": "field.cn_base_pay", "amount": True},
            {"key": "hourly_pay", "label_key": "field.hourly_pay", "amount": True},
            {"key": "additional_payment", "label_key": "field.additional_payment", "amount": True},
            {"key": "cn_social_insurance", "label_key": "field.cn_social_insurance", "amount": True},
            {"key": "cn_housing_fund", "label_key": "field.cn_housing_fund", "amount": True},
            {"key": "estimated_income_tax", "label_key": "field.estimated_income_tax", "amount": True},
            {"key": "confirmed_income_tax", "label_key": "field.cn_individual_income_tax", "amount": True},
            {"key": "tax_reference_status", "label_key": "field.tax_reference_status"},
            {"key": "additional_deduction", "label_key": "field.additional_deduction", "amount": True},
            {"key": "gross_pay", "label_key": "field.gross_pay", "amount": True},
            {"key": "total_deduction", "label_key": "field.total_deduction", "amount": True},
            {"key": "net_pay", "label_key": "field.net_pay", "amount": True},
            {"key": "record_status", "label_key": "field.record_status"},
        ],
    },
    "JP": {
        "title_key": "report.jp.title",
        "language": "ja",
        "columns": [
            {"key": "payroll_month", "label_key": "field.payroll_month"},
            {"key": "employee_no", "label_key": "field.employee_no"},
            {"key": "employee_name", "label_key": "field.employee_name"},
            {"key": "entity", "label_key": "field.entity"},
            {"key": "payroll_scheme", "label_key": "field.payroll_scheme"},
            {"key": "monthly_working_days", "label_key": "field.monthly_working_days"},
            {"key": "attendance_days", "label_key": "field.attendance_days"},
            {"key": "attendance_hours", "label_key": "field.attendance_hours"},
            {"key": "hourly_rate", "label_key": "field.hourly_rate", "amount": True},
            {"key": "calculated_base_pay", "label_key": "field.base_salary", "amount": True},
            {"key": "hourly_pay", "label_key": "field.hourly_pay", "amount": True},
            {"key": "additional_payment", "label_key": "field.additional_payment", "amount": True},
            {"key": "jp_health_insurance", "label_key": "field.jp_health_insurance", "amount": True},
            {"key": "jp_pension", "label_key": "field.jp_pension", "amount": True},
            {"key": "jp_employment_insurance", "label_key": "field.jp_employment_insurance", "amount": True},
            {"key": "estimated_income_tax", "label_key": "field.estimated_income_tax", "amount": True},
            {"key": "confirmed_income_tax", "label_key": "field.income_tax", "amount": True},
            {"key": "confirmed_resident_tax", "label_key": "field.confirmed_resident_tax", "amount": True},
            {"key": "additional_deduction", "label_key": "field.additional_deduction", "amount": True},
            {"key": "gross_pay", "label_key": "field.gross_pay", "amount": True},
            {"key": "total_deduction", "label_key": "field.total_deduction", "amount": True},
            {"key": "net_pay", "label_key": "field.net_pay", "amount": True},
            {"key": "record_status", "label_key": "field.record_status"},
        ],
    },
    "SG": {
        "title_key": "report.sg.title",
        "language": "en",
        "columns": [
            {"key": "payroll_month", "label_key": "field.payroll_month"},
            {"key": "employee_no", "label_key": "field.employee_no"},
            {"key": "employee_name", "label_key": "field.employee_name"},
            {"key": "entity", "label_key": "field.entity"},
            {"key": "work_location_country", "label_key": "field.work_location_country"},
            {"key": "payroll_scheme", "label_key": "field.payroll_scheme"},
            {"key": "monthly_salary", "label_key": "field.monthly_salary", "amount": True},
            {"key": "monthly_working_days", "label_key": "field.monthly_working_days"},
            {"key": "attendance_days", "label_key": "field.attendance_days"},
            {"key": "attendance_hours", "label_key": "field.attendance_hours"},
            {"key": "hourly_rate", "label_key": "field.hourly_rate", "amount": True},
            {"key": "calculated_base_pay", "label_key": "field.sg_basic_salary", "amount": True},
            {"key": "hourly_pay", "label_key": "field.hourly_pay", "amount": True},
            {"key": "additional_payment", "label_key": "field.additional_payment", "amount": True},
            {"key": "sg_cpf_employee", "label_key": "field.sg_cpf_employee", "amount": True},
            {"key": "sg_cpf_employer", "label_key": "field.sg_cpf_employer", "amount": True},
            {"key": "additional_deduction", "label_key": "field.additional_deduction", "amount": True},
            {"key": "gross_pay", "label_key": "field.gross_pay", "amount": True},
            {"key": "total_deduction", "label_key": "field.total_deduction", "amount": True},
            {"key": "net_pay", "label_key": "field.net_pay", "amount": True},
            {"key": "currency", "label_key": "field.currency"},
            {"key": "record_status", "label_key": "field.record_status"},
        ],
    },
}


def validate_user_admin_session(session_id: str) -> dict[str, Any] | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    request = Request(
        f"{USER_ADMIN_BASE_URL}/api/validate-session",
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


def current_path_from_context(context: dict[str, Any] | None) -> str:
    if context and str(context.get("current_path", "")):
        return str(context.get("current_path"))
    return "/"


def field_label(messages: dict[str, str], canonical: str) -> str:
    return t(messages, PAYROLL_FIELD_LABEL_KEYS.get(canonical, ""), canonical)


def option_html(value: str, label: str, selected: str = "") -> str:
    selected_attr = " selected" if str(value) == str(selected) else ""
    return f'<option value="{h(value)}"{selected_attr}>{h(label)}</option>'


def route_record_id(path: str, prefix: str, suffix: str) -> str:
    if not path.startswith(prefix) or not path.endswith(suffix):
        return ""
    record_id = path[len(prefix):len(path) - len(suffix)]
    return unquote(record_id).strip()


def language_switcher_html(lang: str, current_path: str = "/") -> str:
    messages = load_i18n(lang)
    links = []
    for candidate in ["zh", "ja", "en"]:
        label = t(messages, f"language.{candidate}", candidate)
        class_name = "pill" if candidate == lang else "button secondary"
        links.append(f'<a class="{class_name}" href="{h(url_with_lang(current_path, candidate))}">{h(label)}</a>')
    return "".join(links)


class TacaiHandler(BaseHTTPRequestHandler):
    server_version = "TACAIPrjWeb/0.3"

    def _csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        return parsed.hostname in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS

    def _user_admin_session_id_from_cookie(self) -> str:
        cookie_header = self.headers.get("Cookie", "")
        if not cookie_header:
            return ""
        try:
            parsed = cookies.SimpleCookie(cookie_header)
        except cookies.CookieError:
            return ""
        morsel = parsed.get(USER_ADMIN_SESSION_COOKIE)
        return morsel.value if morsel else ""

    def _current_user_admin_user(self) -> dict[str, Any] | None:
        return validate_user_admin_session(self._user_admin_session_id_from_cookie())

    def _require_user_admin_access(self) -> dict[str, Any] | None:
        user = self._current_user_admin_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self._redirect(f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            return None
        if not has_required_module_access(user):
            self.send_error(403, "This User_admin account does not have permission to access Payroll.")
            return None
        return user

    def flash_message(self) -> str:
        jar = cookies.SimpleCookie(self.headers.get("Cookie", ""))
        morsel = jar.get(FLASH_COOKIE)
        return unquote(morsel.value) if morsel else ""

    def flash_cookie_header(self, message: str) -> str:
        jar = cookies.SimpleCookie()
        jar[FLASH_COOKIE] = quote(message)
        jar[FLASH_COOKIE]["path"] = "/"
        jar[FLASH_COOKIE]["samesite"] = "Lax"
        return jar.output(header="").strip()

    def clear_flash_cookie_header(self) -> str:
        return f"{FLASH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax"

    def request_context(self, lang: str, messages: dict[str, str], user: dict[str, Any] | None, current_path: str = "/") -> dict[str, Any]:
        return {
            "lang": lang,
            "messages": messages,
            "user": user,
            "session_id": self._user_admin_session_id_from_cookie(),
            "current_path": current_path,
            "flash": self.flash_message(),
        }

    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        if path == "/health":
            self._send_text("OK")
            return
        if path == "/login":
            next_url = quote(f"{APP_BASE_URL}{url_with_lang('/', lang)}", safe="")
            self._redirect(f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            return
        if path == "/logout":
            next_url = quote(f"{APP_BASE_URL}{url_with_lang('/login', lang)}", safe="")
            self._redirect(f"{USER_ADMIN_BASE_URL}/logout?next={next_url}", headers={"Set-Cookie": clear_legacy_session_cookie_header()})
            return
        current_user = self._require_user_admin_access()
        if not current_user:
            return
        context = self.request_context(lang, messages, current_user, path)
        context["country_filter"] = normalize_country(query.get("country", ["ALL"])[0])
        context["month_filter"] = query.get("month", [""])[0].strip()
        context["salary_profile_status_filter"] = query.get("status", ["active"])[0].strip().lower() or "active"
        if path == "/":
            self._send_html(page(t(messages, "nav.dashboard"), dashboard_html(context), context))
            return
        if path == "/payroll-cockpit":
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            self._send_html(page(t(messages, "nav.payroll_cockpit"), payroll_cockpit_html(context=context), context))
            return
        if path.startswith("/payroll-batches/"):
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            batch_id = unquote(path[len("/payroll-batches/"):]).strip()
            if not batch_id or "/" in batch_id:
                self.send_error(404, "Payroll batch not found")
                return
            batch = find_payroll_batch(batch_id)
            if not batch:
                self.send_error(404, "Payroll batch not found")
                return
            self._send_html(page(t(messages, "payroll_batch.detail_title"), payroll_batch_detail_html(batch, context=context), context))
            return
        if path == "/salary-profiles":
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            self._send_html(page(t(messages, "nav.salary_profiles"), salary_profiles_html(context=context), context))
            return
        salary_profile_edit_id = route_record_id(path, "/salary-profiles/", "/edit")
        if salary_profile_edit_id:
            if not has_permission(current_user, "payroll.edit"):
                self.send_error(403, "Missing payroll.edit permission")
                return
            profile = find_salary_profile(salary_profile_edit_id)
            if not profile:
                self.send_error(404, "Salary profile not found")
                return
            self._send_html(page(t(messages, "salary_profiles.edit_title"), salary_profile_edit_html(profile, context=context), context))
            return
        if path == "/payroll-rules":
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            self._send_html(page(t(messages, "nav.payroll_rules"), payroll_rules_html(context=context), context))
            return
        payroll_rule_edit_id = route_record_id(path, "/payroll-rules/", "/edit")
        if payroll_rule_edit_id:
            if not has_permission(current_user, "payroll.edit"):
                self.send_error(403, "Missing payroll.edit permission")
                return
            rule = find_payroll_rule(payroll_rule_edit_id)
            if not rule:
                self.send_error(404, "Payroll rule not found")
                return
            self._send_html(page(t(messages, "payroll_rules.edit_title"), payroll_rule_edit_html(rule, context=context), context))
            return
        if path == "/payroll-input":
            if not has_permission(current_user, "payroll.edit"):
                self.send_error(403, "Missing payroll.edit permission")
                return
            if query.get("source") == ["sample"]:
                records = load_sample_payroll_records()
                record = records[0] if records else None
                message = t(messages, "message.sample_loaded")
                self._send_html(page(t(messages, "nav.payroll_input"), payroll_input_html(record=record, message=message, context=context), context))
            else:
                self._send_html(page(t(messages, "nav.payroll_input"), payroll_input_html(context=context), context))
            return
        if path == "/payroll-register/download":
            if not has_permission(current_user, "payroll.reports.view"):
                self.send_error(403, "Missing payroll.reports.view permission")
                return
            month_filter = query.get("month", [""])[0].strip()
            country_filter = normalize_country(query.get("country", ["ALL"])[0])
            records = filter_payroll_records(active_payroll_records(load_saved_payroll_records()), country_filter, month_filter)
            content = payroll_register_csv(records, country_filter, lang)
            actor = user_actor(current_user)
            append_audit_log("payroll", month_filter or "payroll-register", "payroll_register_exported", actor, None, {"record_count": len(records), "month": month_filter, "country": country_filter})
            filename = f"payroll-register-{country_filter}-{month_filter or 'all'}.csv"
            self._send_csv(filename, content)
            return
        if path == "/payroll-register":
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            self._send_html(page(t(messages, "nav.payroll_register"), payroll_register_html(context), context))
            return
        payslip_download_id = route_record_id(path, "/payslips/", "/download")
        if payslip_download_id:
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            payslip = find_payslip(payslip_download_id)
            if not payslip or not str(payslip.get("pdf_path", "")):
                self.send_error(404, "Payslip PDF not found")
                return
            pdf_path = Path(str(payslip.get("pdf_path", "")))
            resolved = pdf_path.resolve()
            if not pdf_path.exists() or PAYSLIP_OUTPUT_DIR.resolve() not in resolved.parents:
                self.send_error(404, "Payslip PDF not found")
                return
            self._send_binary(pdf_path.name, pdf_path.read_bytes(), "application/pdf")
            return
        if path == "/payslips":
            if not has_permission(current_user, "payroll.view"):
                self.send_error(403, "Missing payroll.view permission")
                return
            self._send_html(page(t(messages, "nav.payslips"), payslips_html(context), context))
            return
        if path == "/audit-logs/download":
            if not has_permission(current_user, "payroll.reports.view"):
                self.send_error(403, "Missing payroll.reports.view permission")
                return
            logs = load_audit_logs()
            actor = user_actor(current_user)
            append_audit_log("audit", "audit-logs", "audit_logs_exported", actor, None, {"record_count": len(logs)})
            content = audit_logs_csv(load_audit_logs(), actor)
            self._send_csv("audit-logs.csv", content)
            return
        if path == "/audit-logs":
            if not has_permission(current_user, "payroll.reports.view"):
                self.send_error(403, "Missing payroll.reports.view permission")
                return
            self._send_html(page(t(messages, "nav.audit_logs"), audit_logs_html(context), context))
            return
        self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802 - stdlib handler API
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        context = self.request_context(lang, messages, None, path)
        if not self._csrf_origin_allowed():
            self.send_error(403, "Invalid request origin")
            return
        try:
            if path == "/login":
                next_url = quote(f"{APP_BASE_URL}{url_with_lang('/', lang)}", safe="")
                self._redirect(f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
                return
            current_user = self._require_user_admin_access()
            if not current_user:
                return
            context = self.request_context(lang, messages, current_user, path)
            if not has_permission(current_user, "payroll.edit"):
                self.send_error(403, "Missing payroll.edit permission")
                return
            form, files = self._parse_request_form()
            if path == "/payroll-batches":
                batch = create_payroll_batch(form, user_actor(current_user), messages)
                self._redirect(url_with_lang("/payroll-cockpit", lang), flash=operation_success_message("Payroll Batch", payroll_batch_label(batch), "saved", user_actor(current_user), lang))
                return
            batch_generate_id = route_record_id(path, "/payroll-batches/", "/generate")
            if batch_generate_id:
                batch = generate_payroll_batch(batch_generate_id, context, user_actor(current_user), messages)
                self._redirect(url_with_lang(f"/payroll-batches/{quote(str(batch.get('batch_id', '')))}", lang), flash=t(messages, "message.batch_generated", "Payroll batch generated."))
                return
            batch_validate_id = route_record_id(path, "/payroll-batches/", "/validate")
            if batch_validate_id:
                result = run_payroll_batch_validation(batch_validate_id, context, user_actor(current_user), messages)
                self._redirect(url_with_lang(f"/payroll-batches/{quote(batch_validate_id)}", lang), flash=t(messages, "message.batch_validated", "Payroll batch checks completed: {errors} error(s), {warnings} warning(s).").format(errors=result.get("error_count", 0), warnings=result.get("warning_count", 0)))
                return
            batch_confirm_id = route_record_id(path, "/payroll-batches/", "/confirm")
            if batch_confirm_id:
                batch = confirm_payroll_batch(batch_confirm_id, user_actor(current_user), messages)
                self._redirect(url_with_lang(f"/payroll-batches/{quote(str(batch.get('batch_id', '')))}", lang), flash=t(messages, "message.batch_confirmed", "Payroll batch confirmed."))
                return
            batch_lock_id = route_record_id(path, "/payroll-batches/", "/lock")
            if batch_lock_id:
                batch = lock_payroll_batch(batch_lock_id, user_actor(current_user), messages)
                self._redirect(url_with_lang(f"/payroll-batches/{quote(str(batch.get('batch_id', '')))}", lang), flash=t(messages, "message.batch_locked", "Payroll batch locked."))
                return
            batch_payslips_id = route_record_id(path, "/payroll-batches/", "/payslips/generate")
            if batch_payslips_id:
                generated = generate_payslips_for_batch(batch_payslips_id, context, user_actor(current_user), messages)
                self._redirect(url_with_lang("/payslips", lang), flash=t(messages, "message.payslips_generated", "{count} payslip PDF(s) generated.").format(count=len(generated)))
                return
            if path == "/payslips/select-for-email":
                delivery = select_payslip_for_email(form.get("payslip_id", ""), user_actor(current_user), messages)
                self._redirect(url_with_lang("/payslips", lang), flash=t(messages, "message.payslip_queued", "Payslip queued for email distribution to {email}.").format(email=delivery.get("employee_email", "")))
                return
            if path == "/payslips/send-email":
                delivery = send_queued_payslip_delivery(form.get("delivery_id", ""), user_actor(current_user), messages)
                status = str(delivery.get("status", ""))
                key = "message.payslip_email_sent" if status == "sent" else "message.payslip_email_failed"
                fallback = "Payslip email sent to {email}." if status == "sent" else "Payslip email failed for {email}: {error}."
                self._redirect(url_with_lang("/payslips", lang), flash=t(messages, key, fallback).format(email=delivery.get("employee_email", ""), error=delivery.get("error", "")))
                return
            if path == "/salary-profiles":
                profile = salary_profile_from_form(form, messages)
                saved_profile = save_salary_profile(profile, user_actor(current_user), messages)
                self._redirect(url_with_lang("/salary-profiles", lang), flash=operation_success_message("Salary Profile", salary_profile_label(saved_profile), "saved", user_actor(current_user), lang))
                return
            salary_profile_edit_id = route_record_id(path, "/salary-profiles/", "/edit")
            if salary_profile_edit_id:
                profile = salary_profile_from_form(form, messages)
                profile["profile_id"] = salary_profile_edit_id
                saved_profile = update_salary_profile(profile, user_actor(current_user), messages)
                message = no_change_message("Salary Profile", salary_profile_label(saved_profile), lang) if saved_profile.get("_no_changes") else operation_success_message("Salary Profile", salary_profile_label(saved_profile), "saved", user_actor(current_user), lang)
                self._redirect(url_with_lang("/salary-profiles", lang), flash=message)
                return
            salary_profile_version_id = route_record_id(path, "/salary-profiles/", "/version")
            if salary_profile_version_id:
                profile = salary_profile_from_form(form, messages)
                saved_profile = create_salary_profile_version(salary_profile_version_id, profile, user_actor(current_user), messages)
                self._redirect(url_with_lang("/salary-profiles", lang), flash=operation_success_message("Salary Profile Version", salary_profile_label(saved_profile), "saved", user_actor(current_user), lang))
                return
            salary_profile_deactivate_id = route_record_id(path, "/salary-profiles/", "/deactivate")
            if salary_profile_deactivate_id:
                reason = form.get("deactivation_reason", "").strip()
                if not reason:
                    raise ValueError(t(messages, "error.deactivation_reason_required", "Please enter a deactivation reason."))
                if form.get("confirm_deactivate", "") != "yes":
                    raise ValueError(t(messages, "error.deactivation_confirm_required", "Please confirm salary profile deactivation."))
                saved_profile = deactivate_salary_profile(salary_profile_deactivate_id, user_actor(current_user), reason, messages)
                self._redirect(url_with_lang("/salary-profiles", lang), flash=operation_success_message("Salary Profile", salary_profile_label(saved_profile), "deactivated", user_actor(current_user), lang))
                return
            salary_profile_void_id = route_record_id(path, "/salary-profiles/", "/void")
            if salary_profile_void_id:
                reason = form.get("void_reason", "").strip()
                if not reason:
                    raise ValueError(t(messages, "error.void_reason_required", "Please enter a void reason."))
                if form.get("confirm_void", "") != "yes":
                    raise ValueError(t(messages, "error.void_confirm_required", "Please confirm voiding this salary profile."))
                saved_profile = void_salary_profile(salary_profile_void_id, user_actor(current_user), reason, messages)
                self._redirect(url_with_lang("/salary-profiles", lang, {"status": "voided"}), flash=operation_success_message("Salary Profile", salary_profile_label(saved_profile), "voided", user_actor(current_user), lang))
                return
            if path == "/payroll-rules":
                rule = payroll_rule_from_form(form, messages)
                saved_rule = save_payroll_rule(rule, user_actor(current_user), messages)
                message = no_change_message("Payroll Rule", payroll_rule_label(saved_rule), lang) if saved_rule.get("_no_changes") else operation_success_message("Payroll Rule", payroll_rule_label(saved_rule), "saved", user_actor(current_user), lang)
                self._redirect(url_with_lang("/payroll-rules", lang), flash=message)
                return
            payroll_rule_edit_id = route_record_id(path, "/payroll-rules/", "/edit")
            if payroll_rule_edit_id:
                rule = payroll_rule_from_form(form, messages)
                rule["rule_id"] = payroll_rule_edit_id
                saved_rule = save_payroll_rule(rule, user_actor(current_user), messages)
                message = no_change_message("Payroll Rule", payroll_rule_label(saved_rule), lang) if saved_rule.get("_no_changes") else operation_success_message("Payroll Rule", payroll_rule_label(saved_rule), "saved", user_actor(current_user), lang)
                self._redirect(url_with_lang("/payroll-rules", lang), flash=message)
                return
            payroll_rule_deactivate_id = route_record_id(path, "/payroll-rules/", "/deactivate")
            if payroll_rule_deactivate_id:
                saved_rule = deactivate_payroll_rule(payroll_rule_deactivate_id, user_actor(current_user), messages)
                self._redirect(url_with_lang("/payroll-rules", lang), flash=operation_success_message("Payroll Rule", payroll_rule_label(saved_rule), "deactivated", user_actor(current_user), lang))
                return
            if path == "/payroll-input":
                mode = form.get("mode", "manual")
                actor = user_actor(current_user)
                if mode == "upload":
                    upload = files.get("payroll_file")
                    if not upload or not upload[1]:
                        raise ValueError(t(messages, "error.upload_required"))
                    filename, content = upload
                    records = records_from_rows(read_first_sheet_from_bytes(content))
                    if not records:
                        raise ValueError(t(messages, "error.no_excel_record"))
                    record = records[0]
                    extra = f" {t(messages, 'message.only_first_record')}" if len(records) > 1 else ""
                    message = t(messages, "message.excel_imported", "Excel imported into the manual form: {filename}.").format(filename=filename) + extra
                    append_audit_log("payroll", str(record.get("Employee No. (社員No.)", filename)), "payroll_upload_previewed", actor, None, {"filename": filename, "parsed_records": len(records), "loaded_first_record": serialize_record(record)})
                elif mode == "profile":
                    record = profile_payroll_record_from_form(form, messages)
                    message = t(messages, "message.profile_payroll_calculated")
                    append_audit_log("payroll", payroll_record_label(record), "payroll_calculated_previewed", actor, None, {"mode": "profile", "record": serialize_record(record)})
                else:
                    record = manual_record_from_form(form, messages)
                    message = t(messages, "message.manual_calculated")
                    append_audit_log("payroll", payroll_record_label(record), "payroll_calculated_previewed", actor, None, {"mode": "manual", "record": serialize_record(record)})
                self._send_html(page(t(messages, "nav.payroll_input"), payroll_input_html(record=record, message=message, context=context), context))
                return
            if path == "/payroll-confirm":
                mode = form.get("mode", "manual")
                record = profile_payroll_record_from_form(form, messages) if mode == "profile" else manual_record_from_form(form, messages)
                actor = user_actor(current_user)
                saved = save_payroll_record(record, actor)
                self._redirect(url_with_lang("/payroll-register", lang), flash=operation_success_message("Payroll", payroll_record_label(saved), "saved", actor, lang))
                return
            if path == "/payroll-delete":
                actor = user_actor(current_user)
                voided = delete_payroll_record(form.get("record_id", ""), actor)
                record_id = form.get("record_id", "").strip()
                message = operation_success_message("Payroll", record_id, "voided", actor, lang) if voided else t(messages, "message.payroll_not_found")
                self._redirect(url_with_lang("/payroll-register", lang), flash=message)
                return
            self.send_error(404, "Not found")
        except Exception as exc:  # noqa: BLE001 - local MVP should show concise operational errors.
            if path in {"/payroll-input", "/payroll-confirm"}:
                try:
                    append_audit_log("payroll", path.strip("/") or "payroll", "payroll_validation_failed", user_actor(context.get("user") if isinstance(context, dict) else None), None, {"path": path, "error": str(exc)})
                except Exception:
                    pass
            error_html = f"<section class='panel'><h2>{h(t(messages, 'error.input_title'))}</h2><p class='message-strip message-error'>{h(str(exc))}</p></section>"
            if path.startswith("/salary-profiles"):
                fallback_html = salary_profiles_html(context=context)
            elif path.startswith("/payroll-rules"):
                fallback_html = payroll_rules_html(context=context)
            elif path.startswith("/payroll-batches") or path == "/payroll-cockpit":
                fallback_html = payroll_cockpit_html(context=context)
            elif path.startswith("/payslips"):
                fallback_html = payslips_html(context=context)
            else:
                fallback_html = payroll_input_html(context=context)
            self._send_html(page(t(messages, "error.input_title"), error_html + fallback_html, context), status=400)

    def _parse_request_form(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes]]]:
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
            files: dict[str, tuple[str, bytes]] = {}
            for key in fields.keys():
                item = fields[key]
                if isinstance(item, list):
                    item = item[0]
                if item.filename:
                    files[key] = (item.filename, item.file.read())
                else:
                    raw_value = item.value
                    form[key] = raw_value if isinstance(raw_value, str) else raw_value.decode("utf-8", errors="replace")
            return form, files

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(body).items()}, {}

    def _send_html(self, html: str, status: int = 200, headers: dict[str, str] | None = None) -> None:
        payload = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        if self.flash_message():
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect(self, location: str, headers: dict[str, str] | None = None, flash: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        if headers:
            for key, value in headers.items():
                self.send_header(key, value)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_text(self, text: str, status: int = 200) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_csv(self, filename: str, content: str, status: int = 200) -> None:
        payload = ("\ufeff" + content).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_binary(self, filename: str, payload: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def page(title: str, body: str, context: dict[str, Any] | None = None) -> str:
    lang = context_lang(context)
    messages = context_messages(context)
    nav_links = [
        ("/", "nav.dashboard"),
        ("/payroll-cockpit", "nav.payroll_cockpit"),
        ("/salary-profiles", "nav.salary_profiles"),
        ("/payroll-rules", "nav.payroll_rules"),
        ("/payroll-input", "nav.payroll_input"),
        ("/payroll-register", "nav.payroll_register"),
        ("/payslips", "nav.payslips"),
        ("/audit-logs", "nav.audit_logs"),
    ]
    nav_html = "".join(f'<a href="{h(url_with_lang(path, lang))}">{h(t(messages, key))}</a>' for path, key in nav_links)
    portal_html = (
        f'<a class="portal-link" href="{h(PORTAL_BASE_URL)}" title="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" '
        f'aria-label="{h(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{h(t(messages, "nav.portal", "Back to Portal"))}</a>'
    )
    language_html = language_switcher_html(lang, current_path_from_context(context))
    auth_nav = auth_nav_html(context)
    flash = str((context or {}).get("flash", ""))
    flash_html = f'<section class="message-strip message-success" role="status">{h(flash)}</section>' if flash else ""
    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)} - TACAI Prj</title>
  <style>
    :root {{ --navy: #14213d; --blue: #1f6feb; --bg: #f6f8fb; --card: #ffffff; --line: #d8dee9; --muted: #65758b; --green: #0f766e; --amber: #b45309; --red: #b91c1c; }}
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: #17202a; }}
    header {{ background: var(--navy); color: white; padding: 22px 32px; }}
    header h1 {{ margin: 0 0 6px; }}
    header p {{ margin: 0; color: #dbeafe; }}
    nav {{ display: flex; gap: 10px; flex-wrap: wrap; padding: 14px 32px; background: white; border-bottom: 1px solid var(--line); align-items: center; }}
    nav a {{ color: var(--navy); text-decoration: none; border: 1px solid var(--line); padding: 8px 12px; border-radius: 999px; font-weight: 700; }}
    nav a:hover {{ border-color: var(--blue); color: var(--blue); }}
    nav a.portal-link {{ display: inline-flex; align-items: center; gap: 0.35rem; color: #0b4f8a; background: linear-gradient(180deg, #f8fbff 0%, #eaf4ff 100%); border-color: #9cc7f2; box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 1px 2px rgba(15,23,42,.08); }}
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
    input[readonly] {{ background: #f8fafc; color: #334155; }}
    .actions {{ margin: 18px 0; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .nav-utility {{ margin-left: auto; display: flex; gap: 10px; flex-wrap: wrap; align-items: center; }}
    .current-user-chip {{ display: grid; gap: 2px; min-width: 180px; padding: 7px 10px; background: #fff; border: 1px solid #d6e4f2; border-radius: 12px; color: var(--navy); box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
    .current-user-chip strong {{ font-size: .9rem; }}
    .current-user-chip small {{ color: var(--muted); font-size: .76rem; }}
    .button, button {{ display: inline-block; background: var(--blue); color: white; padding: 10px 14px; border-radius: 8px; border: 0; text-decoration: none; font-weight: 800; cursor: pointer; }}
    .button.secondary, button.secondary {{ background: #475569; }}
    .button.success, button.success {{ background: var(--green); }}
    .button.warning, button.warning {{ background: var(--amber); }}
    .button.danger, button.danger {{ background: var(--red); }}
    .button.ghost {{ background: white; color: var(--navy); border: 1px solid var(--line); }}
    .pill, .status-badge {{ display: inline-block; padding: 4px 8px; border-radius: 999px; background: #ecfeff; color: #155e75; font-weight: 800; }}
    .status-active, .status-ready, .status-saved, .status-set {{ background: #dcfce7; color: #166534; }}
    .status-inactive, .status-sample, .status-waiting, .status-missing, .status-unavailable {{ background: #fef3c7; color: #92400e; }}
    .status-error {{ background: #fee2e2; color: #991b1b; }}
    .notice, .message-strip {{ border-left: 4px solid var(--blue); background: #eff6ff; padding: 12px 14px; border-radius: 8px; }}
    .message-warning {{ border-left-color: var(--amber); background: #fffbeb; }}
    .message-success {{ border-left-color: var(--green); background: #ecfdf5; }}
    .message-error {{ border-left-color: var(--red); background: #fef2f2; }}
    .message-info {{ border-left-color: var(--blue); background: #eff6ff; }}
    .sap-confirm-backdrop {{ position: fixed; inset: 0; background: rgba(15,23,42,.48); display: none; align-items: center; justify-content: center; padding: 1rem; z-index: 50; }}
    .sap-confirm-backdrop.active {{ display: flex; }}
    .sap-confirm-dialog {{ width: min(460px, 100%); background: white; border-radius: 18px; border: 1px solid var(--line); box-shadow: 0 24px 80px rgba(15,23,42,.28); padding: 1.2rem; }}
    .wide {{ overflow-x: auto; }}
    .sap-page-header {{ background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); border: 1px solid var(--line); border-radius: 16px; padding: 20px; margin-bottom: 18px; }}
    .sap-page-header h2 {{ margin: 0 0 8px; color: var(--navy); }}
    .sap-object-meta {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; align-items: center; }}
    .sap-section {{ background: var(--card); border: 1px solid var(--line); border-radius: 14px; padding: 18px; margin-top: 16px; }}
    .sap-section h3 {{ margin: 0 0 14px; color: var(--navy); }}
    .sap-toolbar {{ display: flex; gap: 10px; flex-wrap: wrap; align-items: center; justify-content: flex-end; padding-top: 16px; border-top: 1px solid var(--line); margin-top: 18px; }}
    .sap-readonly-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
    .sap-readonly-field {{ background: #f8fafc; border: 1px solid var(--line); border-radius: 10px; padding: 12px; }}
    .sap-readonly-field .label {{ color: var(--muted); font-size: .82rem; font-weight: 800; margin-bottom: 4px; }}
    .sap-readonly-field .value {{ color: var(--navy); font-weight: 850; }}
    .table-scroll {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; background: white; }}
    .wide {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; }}
    input:focus, select:focus, textarea:focus {{ outline: 3px solid rgba(31, 111, 235, 0.18); border-color: var(--blue); }}
    @media (max-width: 720px) {{
      header {{ padding: 16px 18px; }}
      nav {{ flex-wrap: nowrap; overflow-x: auto; padding: 10px 14px; align-items: stretch; }}
      nav a {{ flex: 0 0 auto; min-height: 42px; white-space: nowrap; }}
      .nav-utility {{ flex: 0 0 auto; margin-left: 0; align-items: stretch; }}
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
    <h1>{h(t(messages, 'app.title'))}</h1>
    <p>{h(t(messages, 'app.subtitle'))}</p>
  </header>
  <nav>{portal_html}{nav_html}<span class="nav-utility">{language_html}{auth_nav}</span></nav>
  <main>{flash_html}{body}</main>
</body>
</html>"""


def auth_nav_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    user = context.get("user") if context else None
    if not user:
        return f'<a href="{h(url_with_lang("/login", lang))}">{h(t(messages, "nav.login"))}</a>'
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    account = str(user.get("username") or user.get("email") or user.get("display_name") or user.get("user_id") or "User")
    display_name = str(user.get("display_name") or account)
    entity_code = str(user.get("entity_code") or session.get("entity", {}).get("entity_code", ""))
    login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
    chip = f'<span class="current-user-chip" title="Login: {h(login_time)}"><strong>👤 {h(account)}</strong><small>{h(display_name)}{(" · " + h(entity_code)) if entity_code else ""}</small><small>Login: {h(login_time)}</small></span>'
    return f'{chip}<a href="{h(url_with_lang("/logout", lang))}">{h(t(messages, "nav.logout"))}</a>'


def dashboard_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    records = load_payroll_records()
    totals = calculate_totals(records)
    employee_status = employeeadmin_source_status(context)
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'dashboard.area'))}</p>
  <h2>{h(t(messages, 'dashboard.title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'dashboard.desc'))}</p>
  <div class="sap-object-meta">
    {status_badge('User_admin integrated', context)}
    {status_badge('EmployeeAdmin source', context)}
    {status_badge('Blocked by Employee Master', context)}
  </div>
</section>
{employee_master_dependency_html(context)}
<section class="grid">
  <div class="card"><h3>{h(t(messages, 'dashboard.payroll_month'))}</h3><div class="metric">{h(payroll_month(records))}</div><p class="muted">{h(t(messages, 'dashboard.payroll_month_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'dashboard.employee_count'))}</h3><div class="metric">{len(records)}</div><p class="muted">{h(t(messages, 'dashboard.employee_count_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'field.gross_pay'))}</h3><div class="metric">{money(totals['Gross Pay (総支給額)'])}</div><p class="muted">{h(t(messages, 'dashboard.gross_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'field.net_pay'))}</h3><div class="metric">{money(totals['Net Pay (差引支給額)'])}</div><p class="muted">{h(t(messages, 'dashboard.net_desc'))}</p></div>
</section>
<section class="panel" style="margin-top: 18px;">
  <h2>{h(t(messages, 'dashboard.status_title'))}</h2>
  <p>{h(t(messages, 'integration.user_source'))}</p>
  <p>{h(t(messages, 'integration.employee_source'))}</p>
  <p class="message-strip {h(employee_status['class'])}">{h(t(messages, employee_status['message_key'])).format(count=employee_status['count'])}</p>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/salary-profiles', lang))}">{h(t(messages, 'nav.salary_profiles'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.open_payroll_input'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payroll-register', lang))}">{h(t(messages, 'action.open_payroll_register'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payslips', lang))}">{h(t(messages, 'action.open_payslips'))}</a>
    {portal_return_button_html(context)}
  </div>
</section>
"""


def payroll_cockpit_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    batches = active_payroll_batches(load_payroll_batches())
    month_filter = str((context or {}).get("month_filter", "")).strip()
    country_filter = normalize_country(str((context or {}).get("country_filter", "ALL")))
    filtered = [batch for batch in batches if (not month_filter or str(batch.get("payroll_month", "")) == month_filter)]
    if country_filter != "ALL":
        filtered = [batch for batch in filtered if normalize_country(str(batch.get("country", "ALL"))) == country_filter]
    generated_count = len([batch for batch in batches if str(batch.get("status", "")).lower() == "generated"])
    checked_count = len([batch for batch in batches if str(batch.get("status", "")).lower() == "checked"])
    confirmed_count = len([batch for batch in batches if str(batch.get("status", "")).lower() in {"confirmed", "locked"}])
    validation_error_count = sum(int(batch.get("validation_error_count") or 0) for batch in batches)
    default_month = month_filter or datetime.now(timezone.utc).strftime("%Y-%m")
    country_options = "".join([
        option_html("ALL", t(messages, "country.all"), country_filter),
        option_html("JP", t(messages, "country.jp"), country_filter),
        option_html("CN", t(messages, "country.cn"), country_filter),
        option_html("SG", t(messages, "country.sg"), country_filter),
    ])
    create_country_options = "".join([
        option_html("JP", t(messages, "country.jp"), "JP"),
        option_html("CN", t(messages, "country.cn"), "JP"),
        option_html("SG", t(messages, "country.sg"), "JP"),
        option_html("ALL", t(messages, "country.all"), "JP"),
    ])
    rows = []
    for batch in filtered:
        batch_id = str(batch.get("batch_id", ""))
        detail_url = url_with_lang(f"/payroll-batches/{quote(batch_id, safe='')}", lang)
        rows.append(f"""
          <tr>
            <td><a href="{h(detail_url)}"><strong>{h(str(batch.get('payroll_month', '-')))}</strong></a></td>
            <td>{h(str(batch.get('country', 'ALL') or 'ALL'))}</td>
            <td>{h(str(batch.get('entity_code', '') or '-'))}</td>
            <td>v{h(str(batch.get('version_no', '1')))}</td>
            <td>{payroll_batch_status_badge(batch, messages)}</td>
            <td class="num">{h(str(batch.get('record_count', 0) or 0))}</td>
            <td>{payroll_batch_validation_badge(batch, messages)}</td>
            <td>{h(str(batch.get('created_by', '') or '-'))}</td>
            <td>{h(str(batch.get('created_at', '') or '-'))}</td>
            <td><a class="button secondary" href="{h(detail_url)}">{h(t(messages, 'action.view_batch'))}</a></td>
          </tr>
        """)
    batch_rows = "".join(rows) or f"<tr><td colspan='10'>{h(t(messages, 'payroll_cockpit.empty'))}</td></tr>"
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'payroll_cockpit.title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'payroll_cockpit.desc'))}</p>
  <div class="sap-object-meta">
    {status_badge('User_admin integrated', context)}
    {status_badge('EmployeeAdmin source', context)}
    {status_badge('Blocked by Employee Master', context)}
  </div>
</section>
{employee_master_dependency_html(context)}
<section class="grid">
  <div class="card"><h3>{h(t(messages, 'payroll_cockpit.total_batches'))}</h3><div class="metric">{len(batches)}</div><p class="muted">{h(t(messages, 'payroll_cockpit.total_batches_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'payroll_batch.status.generated'))}</h3><div class="metric">{generated_count}</div><p class="muted">{h(t(messages, 'payroll_cockpit.generated_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'payroll_batch.status.checked'))}</h3><div class="metric">{checked_count}</div><p class="muted">{h(t(messages, 'payroll_cockpit.checked_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'payroll_cockpit.validation_errors'))}</h3><div class="metric">{validation_error_count}</div><p class="muted">{h(t(messages, 'payroll_cockpit.validation_errors_desc'))}</p></div>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_cockpit.new_batch'))}</h3>
  <form method="post" action="{h(url_with_lang('/payroll-batches', lang))}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.payroll_month'))}</label><input name="payroll_month" value="{h(default_month)}" placeholder="YYYY-MM" required></div>
      <div><label>{h(t(messages, 'field.country'))}</label><select name="country">{create_country_options}</select></div>
      <div><label>{h(t(messages, 'field.entity'))}</label><input name="entity_code" placeholder="TAKK / entity code"></div>
      <div><label>{h(t(messages, 'field.description'))}</label><input name="notes" placeholder="{h(t(messages, 'payroll_cockpit.notes_placeholder'))}"></div>
    </div>
    <div class="sap-toolbar"><button type="submit">{h(t(messages, 'action.create_batch'))}</button></div>
  </form>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_cockpit.batch_list'))}</h3>
  <form method="get" action="{h(url_with_lang('/payroll-cockpit', lang))}" class="form-grid">
    <div><label>{h(t(messages, 'report.month_filter'))}</label><input name="month" value="{h(month_filter)}" placeholder="YYYY-MM"></div>
    <div><label>{h(t(messages, 'report.country_filter'))}</label><select name="country">{country_options}</select></div>
    <div style="align-self:end;"><button type="submit" class="secondary">{h(t(messages, 'report.apply_filter'))}</button></div>
  </form>
  <div class="wide" style="margin-top: 14px;">
    <table>
      <thead><tr><th>{h(t(messages, 'field.payroll_month'))}</th><th>{h(t(messages, 'field.country'))}</th><th>{h(t(messages, 'field.entity'))}</th><th>{h(t(messages, 'payroll_batch.version'))}</th><th>{h(t(messages, 'field.status'))}</th><th class="num">{h(t(messages, 'payroll_batch.records'))}</th><th>{h(t(messages, 'payroll_batch.validation'))}</th><th>{h(t(messages, 'payroll_batch.created_by'))}</th><th>{h(t(messages, 'payroll_batch.created_at'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
      <tbody>{batch_rows}</tbody>
    </table>
  </div>
</section>
"""


def payroll_batch_detail_html(batch: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    batch_id = str(batch.get("batch_id", ""))
    records = records_for_batch(batch_id)
    totals = calculate_totals(records)
    rows = []
    for record in records:
        rows.append(f"""
          <tr>
            <td>{h(str(record.get('record_id', '') or '-'))}</td>
            <td>{h(str(record.get('Employee No. (社員No.)') or record.get('employee_no') or '-'))}</td>
            <td>{h(str(record.get('Employee Name (氏名)') or record.get('employee_name') or '-'))}</td>
            <td>{h(str(record.get('currency', '') or '-'))}</td>
            <td class="num">{h(money(record.get('Gross Pay (総支給額)', record.get('gross_pay', 0))))}</td>
            <td class="num">{h(money(record.get('Total Deduction (控除合計)', record.get('total_deduction', 0))))}</td>
            <td class="num">{h(money(record.get('Net Pay (差引支給額)', record.get('net_pay', 0))))}</td>
            <td>{status_badge('Voided', context) if str(record.get('record_status', 'active')) == 'voided' else status_badge('Saved', context)}</td>
          </tr>
        """)
    record_rows = "".join(rows) or f"<tr><td colspan='8'>{h(t(messages, 'payroll_batch.no_records'))}</td></tr>"
    status = str(batch.get("status", "draft")).lower()
    latest_validation = latest_validation_for_batch(batch_id)
    validation_items = latest_validation.get("items", []) if latest_validation else []
    validation_rows = []
    for item in validation_items[:80]:
        validation_rows.append(f"""
          <tr>
            <td>{h(str(item.get('severity', '')))}</td>
            <td>{h(str(item.get('code', '')))}</td>
            <td>{h(str(item.get('employee_no') or item.get('employee_id') or '-'))}</td>
            <td>{h(str(item.get('message', '')))}</td>
          </tr>
        """)
    validation_table = ""
    if validation_rows:
        validation_table = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_batch.validation_results'))}</h3>
  <div class="wide"><table><thead><tr><th>{h(t(messages, 'payroll_batch.severity'))}</th><th>{h(t(messages, 'payroll_batch.issue_code'))}</th><th>{h(t(messages, 'field.employee'))}</th><th>{h(t(messages, 'payroll_batch.issue_message'))}</th></tr></thead><tbody>{''.join(validation_rows)}</tbody></table></div>
</section>
"""
    if status in {"draft", "generated", "checked"}:
        generate_action = f'<form method="post" action="{h(url_with_lang(f"/payroll-batches/{quote(batch_id)}/generate", lang))}" style="display:inline"><button type="submit">{h(t(messages, "action.generate_batch"))}</button></form>'
    else:
        generate_action = f'<button type="button" class="secondary" disabled>{h(t(messages, "action.generate_batch"))}</button>'
    validate_action = f'<form method="post" action="{h(url_with_lang(f"/payroll-batches/{quote(batch_id)}/validate", lang))}" style="display:inline"><button class="secondary" type="submit">{h(t(messages, "action.validate_batch"))}</button></form>' if status in {"generated", "checked"} else f'<button type="button" class="secondary" disabled>{h(t(messages, "action.validate_batch"))}</button>'
    can_confirm = status == "checked" and latest_validation and int(latest_validation.get("error_count") or 0) == 0
    confirm_action = f'<form method="post" action="{h(url_with_lang(f"/payroll-batches/{quote(batch_id)}/confirm", lang))}" style="display:inline"><button class="success" type="submit">{h(t(messages, "action.confirm_batch"))}</button></form>' if can_confirm else f'<button type="button" class="secondary" disabled>{h(t(messages, "action.confirm_batch"))}</button>'
    lock_action = f'<form method="post" action="{h(url_with_lang(f"/payroll-batches/{quote(batch_id)}/lock", lang))}" style="display:inline"><button class="warning" type="submit">{h(t(messages, "action.lock_batch"))}</button></form>' if status == "confirmed" else f'<button type="button" class="secondary" disabled>{h(t(messages, "action.lock_batch"))}</button>'
    payslip_action = f'<form method="post" action="{h(url_with_lang(f"/payroll-batches/{quote(batch_id)}/payslips/generate", lang))}" style="display:inline"><button class="success" type="submit">{h(t(messages, "action.generate_payslips"))}</button></form>' if status in {"confirmed", "locked"} else f'<button type="button" class="secondary" disabled>{h(t(messages, "action.generate_payslips"))}</button>'
    control_hint_key = "payroll_batch.control_hint_locked" if status == "locked" else "payroll_batch.control_hint"
    generation_hint = t(messages, control_hint_key)
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll_cockpit.title'))}</p>
  <h2>{h(payroll_batch_label(batch))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'payroll_batch.detail_desc'))}</p>
  <div class="sap-object-meta">
    {payroll_batch_status_badge(batch, messages)}
    {payroll_batch_validation_badge(batch, messages)}
    <span class="pill">{h(batch_id)}</span>
  </div>
</section>
<section class="grid">
  <div class="card"><h3>{h(t(messages, 'payroll_batch.records'))}</h3><div class="metric">{len(records)}</div><p class="muted">{h(t(messages, 'payroll_batch.records_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'field.gross_pay'))}</h3><div class="metric">{h(money(totals['Gross Pay (総支給額)']))}</div><p class="muted">{h(t(messages, 'dashboard.gross_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'field.net_pay'))}</h3><div class="metric">{h(money(totals['Net Pay (差引支給額)']))}</div><p class="muted">{h(t(messages, 'dashboard.net_desc'))}</p></div>
  <div class="card"><h3>{h(t(messages, 'payroll_batch.version'))}</h3><div class="metric">v{h(str(batch.get('version_no', '1')))}</div><p class="muted">{h(str(batch.get('created_at', '') or '-'))}</p></div>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_batch.control_title'))}</h3>
  <div class="sap-readonly-grid">
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.payroll_month'))}</div><div class="value">{h(str(batch.get('payroll_month', '-')))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.country'))}</div><div class="value">{h(str(batch.get('country', 'ALL') or 'ALL'))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.entity'))}</div><div class="value">{h(str(batch.get('entity_code', '') or '-'))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.status'))}</div><div class="value">{payroll_batch_status_badge(batch, messages)}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'payroll_batch.validation'))}</div><div class="value">{payroll_batch_validation_badge(batch, messages)}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(t(messages, 'payroll_batch.created_by'))}</div><div class="value">{h(str(batch.get('created_by', '') or '-'))}</div></div>
  </div>
  <p class="message-strip message-warning" style="margin-top: 14px;">{h(generation_hint)}</p>
  <div class="sap-toolbar">
    <a class="button secondary" href="{h(url_with_lang('/payroll-cockpit', lang))}">{h(t(messages, 'action.back_to_cockpit'))}</a>
    {generate_action}
    {validate_action}
    {confirm_action}
    {lock_action}
    {payslip_action}
  </div>
</section>
{validation_table}
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_batch.records_table'))}</h3>
  <div class="wide">
    <table>
      <thead><tr><th>{h(t(messages, 'audit.record_id'))}</th><th>{h(t(messages, 'field.employee_no'))}</th><th>{h(t(messages, 'field.employee_name'))}</th><th>{h(t(messages, 'field.currency'))}</th><th class="num">{h(t(messages, 'field.gross_pay'))}</th><th class="num">{h(t(messages, 'field.total_deduction'))}</th><th class="num">{h(t(messages, 'field.net_pay'))}</th><th>{h(t(messages, 'field.status'))}</th></tr></thead>
      <tbody>{record_rows}</tbody>
    </table>
  </div>
</section>
"""


def status_badge(label: str, context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    css_class = {
        "Ready for HR confirmation": "status-ready",
        "Waiting for input": "status-waiting",
        "Saved": "status-saved",
        "Sample": "status-sample",
        "User_admin integrated": "status-active",
        "EmployeeAdmin source": "status-active",
        "External source": "status-active",
        "Unavailable": "status-unavailable",
        "Voided": "status-inactive",
        "Blocked by Employee Master": "status-waiting",
    }.get(label, "")
    label_text = t(messages, STATUS_LABEL_KEYS.get(label, ""), label)
    return f"<span class=\"status-badge {css_class}\">{h(label_text or '-')}</span>"


def user_actor(user: dict[str, Any] | None) -> str:
    if not user:
        return "system"
    return str(user.get("display_name") or user.get("email") or user.get("username") or user.get("user_id") or "current_user")


def timestamp_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_json_array(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    return [item for item in payload if isinstance(item, dict)]


def save_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([to_json_safe(item) for item in records], ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def to_json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {str(key): to_json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [to_json_safe(item) for item in value]
    return value


def append_audit_log(module: str, record_id: str, action: str, user: str, before_value: Any, after_value: Any) -> None:
    logs = load_json_array(AUDIT_LOGS_PATH)
    logs.append({
        "audit_id": timestamp_id("audit"),
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": user or "system",
        "timestamp": now_iso(),
        "before_value": to_json_safe(before_value),
        "after_value": to_json_safe(after_value),
    })
    save_json_array(AUDIT_LOGS_PATH, logs)


NO_OP_COMPARE_IGNORE_FIELDS = {"updated_at", "updated_by"}


def records_business_equal(before: dict[str, Any] | None, after: dict[str, Any] | None, ignore_fields: set[str] | None = None) -> bool:
    before = before or {}
    after = after or {}
    ignored = ignore_fields or NO_OP_COMPARE_IGNORE_FIELDS
    keys = (set(before.keys()) | set(after.keys())) - ignored
    return all(to_json_safe(before.get(key, "")) == to_json_safe(after.get(key, "")) for key in keys)


def load_payroll_batches() -> list[dict[str, Any]]:
    batches = load_json_array(PAYROLL_BATCHES_PATH)
    return sorted(batches, key=lambda item: str(item.get("created_at", "")), reverse=True)


def save_payroll_batches(batches: list[dict[str, Any]]) -> None:
    save_json_array(PAYROLL_BATCHES_PATH, batches)


def active_payroll_batches(batches: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    source = batches if batches is not None else load_payroll_batches()
    return [batch for batch in source if str(batch.get("status", "draft")).lower() != "voided"]


def find_payroll_batch(batch_id: str) -> dict[str, Any] | None:
    target = batch_id.strip()
    for batch in load_payroll_batches():
        if str(batch.get("batch_id", "")) == target:
            return batch
    return None


def records_for_batch(batch_id: str) -> list[dict[str, Any]]:
    target = batch_id.strip()
    return [record for record in active_payroll_records(load_saved_payroll_records()) if str(record.get("batch_id", "")) == target]


def payroll_batch_label(batch: dict[str, Any]) -> str:
    month = str(batch.get("payroll_month", "") or "-")
    country = str(batch.get("country", "") or "ALL")
    entity = str(batch.get("entity_code", "") or "-")
    version = str(batch.get("version_no", "") or "1")
    return f"{month} / {country} / {entity} / v{version}"


def payroll_batch_status_label(status: str, messages: dict[str, str]) -> str:
    key = f"payroll_batch.status.{str(status or 'draft').lower()}"
    return t(messages, key, str(status or "draft").replace("_", " ").title())


def payroll_batch_status_badge(batch: dict[str, Any], messages: dict[str, str]) -> str:
    status = str(batch.get("status", "draft")).lower()
    css_class = {
        "draft": "status-waiting",
        "generated": "status-saved",
        "checked": "status-ready",
        "confirmed": "status-active",
        "locked": "status-active",
        "voided": "status-inactive",
    }.get(status, "")
    return f'<span class="status-badge {css_class}">{h(payroll_batch_status_label(status, messages))}</span>'


def payroll_batch_validation_badge(batch: dict[str, Any], messages: dict[str, str]) -> str:
    status = str(batch.get("validation_status", "not_run")).lower()
    css_class = {
        "not_run": "status-waiting",
        "passed": "status-ready",
        "failed": "status-error",
    }.get(status, "status-waiting")
    label = t(messages, f"validation.status.{status}", status.replace("_", " ").title())
    errors = int(batch.get("validation_error_count") or 0)
    warnings = int(batch.get("validation_warning_count") or 0)
    suffix = f" · E{errors}/W{warnings}" if errors or warnings else ""
    return f'<span class="status-badge {css_class}">{h(label + suffix)}</span>'


def next_payroll_batch_version(payroll_month_value: str, country: str, entity_code: str, batches: list[dict[str, Any]] | None = None) -> int:
    source = batches if batches is not None else load_payroll_batches()
    matching = [
        int(batch.get("version_no") or 1)
        for batch in source
        if str(batch.get("payroll_month", "")) == payroll_month_value
        and str(batch.get("country", "")).upper() == country.upper()
        and str(batch.get("entity_code", "")) == entity_code
    ]
    return (max(matching) + 1) if matching else 1


def create_payroll_batch(form: dict[str, str], actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    payroll_month_value = validate_payroll_month(form.get("payroll_month", ""), messages)
    country = normalize_country(form.get("country", "ALL"))
    entity_code = form.get("entity_code", "").strip()
    notes = form.get("notes", "").strip()
    batches = load_payroll_batches()
    now = now_iso()
    batch = {
        "batch_id": timestamp_id("batch"),
        "payroll_month": payroll_month_value,
        "country": country,
        "entity_code": entity_code,
        "status": "draft",
        "version_no": next_payroll_batch_version(payroll_month_value, country, entity_code, batches),
        "created_at": now,
        "created_by": actor or "system",
        "updated_at": now,
        "updated_by": actor or "system",
        "generated_at": "",
        "generated_by": "",
        "confirmed_at": "",
        "confirmed_by": "",
        "locked_at": "",
        "locked_by": "",
        "record_count": 0,
        "validation_status": "not_run",
        "validation_error_count": 0,
        "validation_warning_count": 0,
        "notes": notes,
    }
    batches.insert(0, batch)
    save_payroll_batches(batches)
    append_audit_log("payroll", str(batch["batch_id"]), "payroll_batch_created", actor, None, batch)
    return batch


def update_payroll_batch_status(batch_id: str, status: str, actor: str, extra: dict[str, Any] | None = None) -> dict[str, Any] | None:
    batches = load_payroll_batches()
    updated: dict[str, Any] | None = None
    for index, batch in enumerate(batches):
        if str(batch.get("batch_id", "")) != batch_id:
            continue
        before = dict(batch)
        batch = dict(batch)
        batch["status"] = status
        batch["updated_at"] = now_iso()
        batch["updated_by"] = actor or "system"
        if extra:
            batch.update(extra)
        batches[index] = batch
        updated = batch
        append_audit_log("payroll", batch_id, "payroll_batch_status_updated", actor, before, batch)
        break
    if updated:
        save_payroll_batches(batches)
    return updated


def save_all_payroll_records(records: list[dict[str, Any]]) -> None:
    save_json_array(PAYROLL_RECORDS_PATH, records)


def employee_id_from_profile(profile: dict[str, Any]) -> str:
    return str(profile.get("employee_external_id") or profile.get("employee_id") or "").strip()


def employee_no_from_any(record: dict[str, Any]) -> str:
    return str(record.get("employee_no") or record.get("Employee No. (社員No.)") or record.get("employee_number") or "").strip()


def employee_key_from_record(record: dict[str, Any]) -> str:
    employee_id = str(record.get("employee_id") or record.get("employee_external_id") or "").strip().casefold()
    if employee_id:
        return f"id:{employee_id}"
    employee_no = employee_no_from_any(record).casefold()
    return f"no:{employee_no}" if employee_no else ""


def employee_lookup_maps(employees: list[dict[str, Any]]) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    by_id: dict[str, dict[str, Any]] = {}
    by_no: dict[str, dict[str, Any]] = {}
    for employee in employees:
        employee_id = str(employee.get("employee_id", "")).strip().casefold()
        employee_no = str(employee.get("employee_number") or employee.get("employee_no") or "").strip().casefold()
        if employee_id:
            by_id[employee_id] = employee
        if employee_no:
            by_no[employee_no] = employee
    return by_id, by_no


def employee_for_profile(profile: dict[str, Any], employees: list[dict[str, Any]]) -> dict[str, Any] | None:
    by_id, by_no = employee_lookup_maps(employees)
    employee_id = employee_id_from_profile(profile).casefold()
    employee_no = str(profile.get("employee_no", "")).strip().casefold()
    if employee_id and employee_id in by_id:
        return by_id[employee_id]
    if employee_no and employee_no in by_no:
        return by_no[employee_no]
    return None


def employee_email(employee: dict[str, Any] | None) -> str:
    if not employee:
        return ""
    for key in ("email", "work_email", "company_email", "personal_email"):
        value = str(employee.get(key, "")).strip()
        if value:
            return value
    return ""


def profile_matches_batch(profile: dict[str, Any], batch: dict[str, Any], messages: dict[str, str] | None = None) -> bool:
    country = normalize_country(str(batch.get("country", "ALL")))
    if country != "ALL" and normalize_country(str(profile.get("country", ""))) != country:
        return False
    entity_code = str(batch.get("entity_code", "")).strip().casefold()
    if entity_code and str(profile.get("entity", "")).strip().casefold() != entity_code:
        return False
    period_start, period_end = month_period(str(batch.get("payroll_month", "")), messages)
    return dates_overlap(str(profile.get("effective_from", "")), str(profile.get("effective_to", "")), period_start, period_end)


def default_batch_input_data(profile: dict[str, Any], batch: dict[str, Any]) -> dict[str, Any]:
    payroll_month_value = str(batch.get("payroll_month", ""))
    _start, _end = month_period(payroll_month_value)
    month_no = int(payroll_month_value.split("-", 1)[1]) if "-" in payroll_month_value else 1
    working_days = profile.get("standard_monthly_working_days", "20") or "20"
    standard_hours = profile.get("standard_monthly_hours", "160") or "160"
    return {
        "payroll_month": payroll_month_value,
        "attendance_days": working_days,
        "monthly_working_days": working_days,
        "attendance_hours": standard_hours,
        "additional_payment": "0",
        "additional_deduction": "0",
        "confirmed_income_tax": "0",
        "apply_tax_reference_to_income_tax": "",
        "jp_dependent_count_override": "",
        "jp_monthly_social_insurance_override": "",
        "jp_resident_tax_monthly": "",
        "cn_cumulative_months": str(month_no),
        "cn_prior_ytd_income": "0",
        "cn_prior_ytd_social_insurance": "0",
        "cn_prior_ytd_housing_fund": "0",
        "cn_prior_ytd_special_additional_deductions": "0",
        "cn_prior_ytd_other_deductions": "0",
        "cn_prior_ytd_tax_withheld": "0",
    }


def payroll_record_from_profile_for_batch(profile: dict[str, Any], employee: dict[str, Any] | None, batch: dict[str, Any], actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    record = calculate_universal_payroll(profile, default_batch_input_data(profile, batch), messages)
    employee_id = employee_id_from_profile(profile) or str((employee or {}).get("employee_id", "")).strip()
    email = employee_email(employee)
    record.update({
        "batch_id": batch.get("batch_id", ""),
        "version_no": batch.get("version_no", 1),
        "employee_id": employee_id,
        "employee_external_id": employee_id,
        "employee_email": email,
        "salary_profile_id": profile.get("profile_id", ""),
        "record_source": "batch_generation",
        "generated_at": now_iso(),
        "generated_by": actor or "system",
        "confirmed": False,
        "confirmed_at": "",
        "confirmed_by": "",
        "locked": False,
        "locked_at": "",
        "locked_by": "",
    })
    if employee:
        record["employee_status_snapshot"] = employee.get("status", "")
        record["employee_email"] = email
    apply_legacy_canonical_fields(record)
    return record


def conflicting_confirmed_employee_month(records: list[dict[str, Any]], batch_id: str, generated_records: list[dict[str, Any]]) -> dict[str, Any] | None:
    targets = {(employee_key_from_record(record), str(record.get("payroll_month") or record.get("Payroll Month (給与月)") or "")) for record in generated_records}
    for record in records:
        if str(record.get("record_status", "active")) == "voided" or str(record.get("batch_id", "")) == batch_id:
            continue
        key = (employee_key_from_record(record), str(record.get("payroll_month") or record.get("Payroll Month (給与月)") or ""))
        if key not in targets:
            continue
        other_batch = find_payroll_batch(str(record.get("batch_id", "")))
        other_status = str((other_batch or {}).get("status", "")).lower()
        if other_status in {"confirmed", "locked"} or truthy(record.get("confirmed")) or truthy(record.get("locked")):
            return record
    return None


def generate_payroll_batch(batch_id: str, context: dict[str, Any] | None, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    batch = find_payroll_batch(batch_id)
    if not batch:
        raise ValueError(t(messages, "error.batch_not_found", "Payroll batch was not found."))
    status = str(batch.get("status", "draft")).lower()
    if status in {"confirmed", "locked", "voided"}:
        raise ValueError(t(messages, "error.batch_generation_not_allowed", "This payroll batch cannot be regenerated in its current status."))
    append_audit_log("payroll", batch_id, "payroll_batch_generation_started", actor, None, {"batch_id": batch_id})
    employees = load_employeeadmin_employees(context)
    profiles = [profile for profile in active_salary_profiles(load_salary_profiles()) if profile_matches_batch(profile, batch, messages)]
    if not profiles:
        raise ValueError(t(messages, "error.no_profiles_for_batch", "No active Salary Profiles match this batch."))
    generated_records = [payroll_record_from_profile_for_batch(profile, employee_for_profile(profile, employees), batch, actor, messages) for profile in profiles]
    saved_records = load_saved_payroll_records()
    conflict = conflicting_confirmed_employee_month(saved_records, batch_id, generated_records)
    if conflict:
        append_audit_log("payroll", batch_id, "payroll_batch_generation_failed", actor, None, {"reason": "duplicate_confirmed_employee_month", "conflict": serialize_record(conflict)})
        raise ValueError(t(messages, "error.duplicate_confirmed_employee_month", "Another confirmed or locked batch already has an active record for the same employee and month."))
    updated_records: list[dict[str, Any]] = []
    voided_count = 0
    for record in saved_records:
        if str(record.get("batch_id", "")) == batch_id and str(record.get("record_status", "active")) != "voided":
            before = dict(record)
            record = dict(record)
            record["record_status"] = "voided"
            record["voided_at"] = now_iso()
            record["voided_by"] = actor
            record["void_reason"] = "batch_regeneration"
            append_audit_log("payroll", str(record.get("record_id", "")), "payroll_batch_records_voided_for_regeneration", actor, before, record)
            voided_count += 1
        updated_records.append(record)
    for record in generated_records:
        record["record_id"] = timestamp_id("payroll")
        record["saved_at"] = now_iso()
        updated_records.append(record)
        append_audit_log("payroll", str(record["record_id"]), "payroll_record_created", actor, None, record)
    save_all_payroll_records(updated_records)
    extra = {
        "generated_at": now_iso(),
        "generated_by": actor or "system",
        "record_count": len(generated_records),
        "validation_status": "not_run",
        "validation_error_count": 0,
        "validation_warning_count": 0,
    }
    updated_batch = update_payroll_batch_status(batch_id, "generated", actor, extra) or batch
    append_audit_log("payroll", batch_id, "payroll_batch_generated", actor, None, {"batch_id": batch_id, "record_count": len(generated_records), "voided_count": voided_count})
    return updated_batch


def load_payroll_validation_results() -> list[dict[str, Any]]:
    return load_json_array(PAYROLL_VALIDATION_RESULTS_PATH)


def save_payroll_validation_results(results: list[dict[str, Any]]) -> None:
    save_json_array(PAYROLL_VALIDATION_RESULTS_PATH, results)


def latest_validation_for_batch(batch_id: str) -> dict[str, Any] | None:
    matches = [result for result in load_payroll_validation_results() if str(result.get("batch_id", "")) == batch_id]
    if not matches:
        return None
    return sorted(matches, key=lambda item: str(item.get("run_at", "")), reverse=True)[0]


def validation_item(severity: str, code: str, message: str, record: dict[str, Any] | None = None) -> dict[str, Any]:
    record = record or {}
    return {
        "severity": severity,
        "code": code,
        "message": message,
        "record_id": record.get("record_id", ""),
        "employee_id": record.get("employee_id", ""),
        "employee_no": employee_no_from_any(record),
    }


def validate_payroll_batch(batch: dict[str, Any], context: dict[str, Any] | None, messages: dict[str, str] | None = None) -> dict[str, Any]:
    batch_id = str(batch.get("batch_id", ""))
    records = records_for_batch(batch_id)
    items: list[dict[str, Any]] = []
    if not records:
        items.append(validation_item("error", "batch_has_no_records", t(messages, "validation.batch_has_no_records", "Batch has no generated payroll records.")))
    employees = load_employeeadmin_employees(context)
    employee_ids = {str(employee.get("employee_id", "")).strip().casefold(): employee for employee in employees if str(employee.get("employee_id", "")).strip()}
    seen: set[tuple[str, str]] = set()
    all_records = active_payroll_records(load_saved_payroll_records())
    for record in records:
        key = employee_key_from_record(record)
        payroll_month_value = str(record.get("payroll_month") or record.get("Payroll Month (給与月)") or "")
        if not str(record.get("employee_id", "")).strip():
            items.append(validation_item("error", "missing_employee_id", t(messages, "validation.missing_employee_id", "Generated payroll record is missing EmployeeAdmin employee_id."), record))
        if not payroll_month_value:
            items.append(validation_item("error", "missing_payroll_month", t(messages, "validation.missing_payroll_month", "Payroll month is missing."), record))
        if not str(record.get("salary_profile_id") or record.get("profile_id") or "").strip():
            items.append(validation_item("error", "missing_salary_profile", t(messages, "validation.missing_salary_profile", "Salary Profile is missing."), record))
        if not str(record.get("payroll_rule_id", "")).strip():
            items.append(validation_item("error", "missing_payroll_rule", t(messages, "validation.missing_payroll_rule", "Payroll Rule is missing."), record))
        if not str(record.get("currency", "")).strip():
            items.append(validation_item("error", "missing_currency", t(messages, "validation.missing_currency", "Currency is missing."), record))
        if parse_decimal(record.get("Gross Pay (総支給額)", record.get("gross_pay", "0"))) < 0:
            items.append(validation_item("error", "negative_gross_pay", t(messages, "validation.negative_gross_pay", "Gross pay is negative."), record))
        if parse_decimal(record.get("Net Pay (差引支給額)", record.get("net_pay", "0"))) < 0:
            items.append(validation_item("error", "negative_net_pay", t(messages, "validation.negative_net_pay", "Net pay is negative."), record))
        duplicate_key = (key, payroll_month_value)
        if key and duplicate_key in seen:
            items.append(validation_item("error", "duplicate_employee_month_in_batch", t(messages, "validation.duplicate_employee_month_in_batch", "Duplicate employee/month exists in this batch."), record))
        seen.add(duplicate_key)
        for other in all_records:
            if str(other.get("batch_id", "")) == batch_id or str(other.get("record_status", "active")) == "voided":
                continue
            other_batch = find_payroll_batch(str(other.get("batch_id", "")))
            if str((other_batch or {}).get("status", "")).lower() not in {"confirmed", "locked"} and not truthy(other.get("confirmed")) and not truthy(other.get("locked")):
                continue
            other_key = (employee_key_from_record(other), str(other.get("payroll_month") or other.get("Payroll Month (給与月)") or ""))
            if other_key == duplicate_key:
                items.append(validation_item("error", "duplicate_confirmed_employee_month", t(messages, "validation.duplicate_confirmed_employee_month", "Another confirmed/locked batch already contains this employee/month."), record))
        employee_id = str(record.get("employee_id", "")).strip().casefold()
        if employees and employee_id and employee_id not in employee_ids:
            items.append(validation_item("error", "employee_not_found_in_employeeadmin", t(messages, "validation.employee_not_found", "Employee was not found in EmployeeAdmin."), record))
        if not str(record.get("employee_email", "")).strip():
            items.append(validation_item("warning", "missing_employee_email", t(messages, "validation.missing_employee_email", "Employee email is missing; payslip email distribution will be blocked."), record))
        if truthy(record.get("tax_reference_review_required")) or record.get("estimated_income_tax"):
            items.append(validation_item("warning", "tax_reference_requires_review", t(messages, "validation.tax_reference_requires_review", "Tax reference is estimated and requires HR review."), record))
    error_count = len([item for item in items if item.get("severity") == "error"])
    warning_count = len([item for item in items if item.get("severity") == "warning"])
    return {
        "validation_id": timestamp_id("validation"),
        "batch_id": batch_id,
        "run_at": now_iso(),
        "status": "failed" if error_count else "passed",
        "error_count": error_count,
        "warning_count": warning_count,
        "items": items,
    }


def run_payroll_batch_validation(batch_id: str, context: dict[str, Any] | None, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    batch = find_payroll_batch(batch_id)
    if not batch:
        raise ValueError(t(messages, "error.batch_not_found", "Payroll batch was not found."))
    if str(batch.get("status", "")).lower() in {"locked", "voided"}:
        raise ValueError(t(messages, "error.batch_validation_not_allowed", "This payroll batch cannot be checked in its current status."))
    result = validate_payroll_batch(batch, context, messages)
    result["run_by"] = actor or "system"
    results = load_payroll_validation_results()
    results.append(result)
    save_payroll_validation_results(results)
    next_status = "checked" if int(result.get("error_count") or 0) == 0 else str(batch.get("status", "generated"))
    update_payroll_batch_status(batch_id, next_status, actor, {
        "validation_status": result.get("status", "failed"),
        "validation_error_count": result.get("error_count", 0),
        "validation_warning_count": result.get("warning_count", 0),
    })
    append_audit_log("payroll", batch_id, "payroll_batch_validated", actor, None, {"status": result.get("status"), "error_count": result.get("error_count"), "warning_count": result.get("warning_count")})
    return result


def mark_batch_records(batch_id: str, updates: dict[str, Any], actor: str, audit_action: str) -> int:
    records = load_saved_payroll_records()
    changed = 0
    for index, record in enumerate(records):
        if str(record.get("batch_id", "")) == batch_id and str(record.get("record_status", "active")) != "voided":
            before = dict(record)
            record = dict(record)
            record.update(updates)
            records[index] = record
            append_audit_log("payroll", str(record.get("record_id", "")), audit_action, actor, before, record)
            changed += 1
    save_all_payroll_records(records)
    return changed


def confirm_payroll_batch(batch_id: str, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    batch = find_payroll_batch(batch_id)
    if not batch:
        raise ValueError(t(messages, "error.batch_not_found", "Payroll batch was not found."))
    latest = latest_validation_for_batch(batch_id)
    if str(batch.get("status", "")).lower() != "checked" or not latest or int(latest.get("error_count") or 0) != 0:
        raise ValueError(t(messages, "error.batch_confirm_not_allowed", "Batch must pass validation before confirmation."))
    now = now_iso()
    count = mark_batch_records(batch_id, {"confirmed": True, "confirmed_at": now, "confirmed_by": actor}, actor, "payroll_record_confirmed")
    updated = update_payroll_batch_status(batch_id, "confirmed", actor, {"confirmed_at": now, "confirmed_by": actor, "record_count": count}) or batch
    append_audit_log("payroll", batch_id, "payroll_batch_confirmed", actor, None, {"batch_id": batch_id, "record_count": count})
    return updated


def lock_payroll_batch(batch_id: str, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    batch = find_payroll_batch(batch_id)
    if not batch:
        raise ValueError(t(messages, "error.batch_not_found", "Payroll batch was not found."))
    if str(batch.get("status", "")).lower() != "confirmed":
        raise ValueError(t(messages, "error.batch_lock_not_allowed", "Only confirmed batches can be locked."))
    now = now_iso()
    count = mark_batch_records(batch_id, {"locked": True, "locked_at": now, "locked_by": actor}, actor, "payroll_record_locked")
    updated = update_payroll_batch_status(batch_id, "locked", actor, {"locked_at": now, "locked_by": actor, "record_count": count}) or batch
    append_audit_log("payroll", batch_id, "payroll_batch_locked", actor, None, {"batch_id": batch_id, "record_count": count})
    return updated


def load_payslips() -> list[dict[str, Any]]:
    return load_json_array(PAYSLIPS_PATH)


def save_payslips(payslips: list[dict[str, Any]]) -> None:
    save_json_array(PAYSLIPS_PATH, payslips)


def find_payslip(payslip_id: str) -> dict[str, Any] | None:
    target = payslip_id.strip()
    for payslip in load_payslips():
        if str(payslip.get("payslip_id", "")) == target:
            return payslip
    return None


def config_bool(value: Any, default: bool = False) -> bool:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def config_int(value: Any, default: int) -> int:
    try:
        return int(str(value or "").strip())
    except ValueError:
        return default


def payslip_email_settings() -> dict[str, Any]:
    smtp_port = config_int(PAYSLIP_SMTP_PORT, 465)
    use_ssl_default = smtp_port == 465
    return {
        "enabled": config_bool(PAYSLIP_EMAIL_ENABLED, True),
        "sender_email": PAYSLIP_EMAIL_SENDER,
        "sender_display_name": PAYSLIP_EMAIL_SENDER_NAME,
        "sender_header": formataddr((PAYSLIP_EMAIL_SENDER_NAME, PAYSLIP_EMAIL_SENDER)),
        "reply_to_email": PAYSLIP_EMAIL_REPLY_TO,
        "smtp_host": PAYSLIP_SMTP_HOST,
        "smtp_port": smtp_port,
        "smtp_username": PAYSLIP_SMTP_USERNAME,
        "smtp_password": PAYSLIP_SMTP_PASSWORD,
        "smtp_use_tls": config_bool(PAYSLIP_SMTP_USE_TLS, True),
        "smtp_use_ssl": config_bool(PAYSLIP_SMTP_USE_SSL, use_ssl_default),
        "smtp_timeout_seconds": config_int(PAYSLIP_SMTP_TIMEOUT_SECONDS, 20),
    }


def latest_delivery_by_payslip(deliveries: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for delivery in deliveries:
        payslip_id = str(delivery.get("payslip_id", ""))
        if not payslip_id:
            continue
        current = latest.get(payslip_id)
        current_time = str((current or {}).get("last_attempt_at") or (current or {}).get("selected_at") or "")
        candidate_time = str(delivery.get("last_attempt_at") or delivery.get("selected_at") or "")
        if current is None or candidate_time >= current_time:
            latest[payslip_id] = delivery
    return latest


def validated_payslip_pdf_path(payslip: dict[str, Any]) -> tuple[Path | None, str]:
    pdf_text = str(payslip.get("pdf_path", "")).strip()
    if not pdf_text:
        return None, "pdf_not_found"
    pdf_path = Path(pdf_text)
    try:
        resolved = pdf_path.resolve()
        output_root = PAYSLIP_OUTPUT_DIR.resolve()
    except OSError:
        return None, "pdf_path_invalid"
    if not pdf_path.exists():
        return None, "pdf_not_found"
    if output_root != resolved and output_root not in resolved.parents:
        return None, "pdf_path_invalid"
    return pdf_path, "ok"


def safe_filename_part(value: Any) -> str:
    text = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(value or "").strip())
    return text.strip("-._") or "unknown"


def safe_payslip_attachment_filename(payslip: dict[str, Any]) -> str:
    month = safe_filename_part(payslip.get("payroll_month", "month"))
    employee_no = safe_filename_part(payslip.get("employee_no", "employee"))
    return f"payslip-{month}-{employee_no}.pdf"


def payslip_email_subject(payslip: dict[str, Any], messages: dict[str, str] | None = None) -> str:
    month = str(payslip.get("payroll_month", "")) or "Payroll Month"
    return t(messages, "payslip_email.subject", "Your payslip for {month}").format(month=month)


def payslip_email_body(payslip: dict[str, Any], messages: dict[str, str] | None = None) -> str:
    employee_name = str(payslip.get("employee_name", "")) or t(messages, "field.employee", "Employee")
    month = str(payslip.get("payroll_month", "")) or "-"
    return t(messages, "payslip_email.body", """Dear {employee_name},

Your payslip for {month} is attached as a PDF.

This email and attachment contain confidential personal information. Please do not forward or share it with unauthorized parties.

If you have questions, please contact HR/Payroll.

TAC HR Admin""").format(employee_name=employee_name, month=month)


def send_payslip_email(to_address: str, subject: str, body: str, pdf_path: Path, attachment_filename: str) -> tuple[bool, str]:
    settings = payslip_email_settings()
    if not settings["enabled"]:
        return False, "disabled"
    if not settings["smtp_host"] or not settings["smtp_username"] or not settings["smtp_password"] or not settings["sender_email"]:
        return False, "not_configured"
    recipient = str(to_address or "").strip()
    if not EMAIL_PATTERN.fullmatch(recipient):
        return False, "invalid_recipient"
    if not pdf_path.exists():
        return False, "pdf_not_found"
    try:
        resolved = pdf_path.resolve()
        output_root = PAYSLIP_OUTPUT_DIR.resolve()
    except OSError:
        return False, "pdf_path_invalid"
    if output_root != resolved and output_root not in resolved.parents:
        return False, "pdf_path_invalid"
    message = EmailMessage()
    message["From"] = settings["sender_header"]
    message["To"] = recipient
    message["Subject"] = subject
    if settings.get("reply_to_email"):
        message["Reply-To"] = str(settings["reply_to_email"])
    message.set_content(body)
    message.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=attachment_filename)
    try:
        if settings["smtp_use_ssl"] or int(settings["smtp_port"]) == 465:
            with smtplib.SMTP_SSL(settings["smtp_host"], int(settings["smtp_port"]), timeout=int(settings["smtp_timeout_seconds"]), context=ssl.create_default_context()) as smtp:
                smtp.login(settings["smtp_username"], settings["smtp_password"])
                smtp.send_message(message)
        else:
            with smtplib.SMTP(settings["smtp_host"], int(settings["smtp_port"]), timeout=int(settings["smtp_timeout_seconds"])) as smtp:
                if settings["smtp_use_tls"]:
                    smtp.starttls(context=ssl.create_default_context())
                smtp.login(settings["smtp_username"], settings["smtp_password"])
                smtp.send_message(message)
    except (OSError, smtplib.SMTPException) as exc:
        return False, exc.__class__.__name__
    return True, "sent"


def find_delivery_index(deliveries: list[dict[str, Any]], delivery_id: str) -> int:
    target = delivery_id.strip()
    for index, delivery in enumerate(deliveries):
        if str(delivery.get("delivery_id", "")) == target:
            return index
    return -1


def send_queued_payslip_delivery(delivery_id: str, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    deliveries = load_payslip_email_deliveries()
    delivery_index = find_delivery_index(deliveries, delivery_id)
    if delivery_index < 0:
        raise ValueError(t(messages, "error.delivery_not_found", "Payslip email delivery was not found."))
    delivery = dict(deliveries[delivery_index])
    status = str(delivery.get("status", "queued")).lower()
    if status not in {"queued", "failed"}:
        raise ValueError(t(messages, "error.delivery_not_sendable", "This payslip email delivery cannot be sent in its current status."))
    payslips = load_payslips()
    payslip_index = -1
    payslip: dict[str, Any] | None = None
    for index, item in enumerate(payslips):
        if str(item.get("payslip_id", "")) == str(delivery.get("payslip_id", "")):
            payslip_index = index
            payslip = dict(item)
            break
    if payslip is None:
        raise ValueError(t(messages, "error.payslip_not_found", "Payslip was not found."))
    recipient = str(delivery.get("employee_email") or payslip.get("employee_email") or "").strip()
    if not EMAIL_PATTERN.fullmatch(recipient):
        send_status = "invalid_recipient"
        ok = False
        pdf_path = None
        attachment_filename = ""
    else:
        pdf_path, pdf_status = validated_payslip_pdf_path(payslip)
        if pdf_status != "ok" or not pdf_path:
            send_status = pdf_status
            ok = False
            attachment_filename = ""
        else:
            attachment_filename = safe_payslip_attachment_filename(payslip)
            ok, send_status = send_payslip_email(recipient, payslip_email_subject(payslip, messages), payslip_email_body(payslip, messages), pdf_path, attachment_filename)
    now = now_iso()
    attempt_count = int(delivery.get("attempt_count") or 0) + 1
    before_delivery = dict(delivery)
    delivery.update({
        "status": "sent" if ok else "failed",
        "provider": "smtp",
        "attempt_count": attempt_count,
        "last_attempt_at": now,
        "last_attempt_by": actor or "system",
        "subject": payslip_email_subject(payslip, messages),
        "attachment_filename": attachment_filename,
        "error": "" if ok else send_status,
    })
    if ok:
        delivery["sent_at"] = now
        delivery["sent_by"] = actor or "system"
    deliveries[delivery_index] = delivery
    before_payslip = dict(payslip)
    payslip.update({
        "delivery_status": "sent" if ok else "failed",
        "delivery_id": delivery.get("delivery_id", ""),
        "delivery_error": "" if ok else send_status,
        "last_delivery_attempt_at": now,
    })
    if ok:
        payslip["delivered_at"] = now
        payslip["delivered_by"] = actor or "system"
    payslips[payslip_index] = payslip
    save_payslip_email_deliveries(deliveries)
    save_payslips(payslips)
    audit_action = "payroll_payslip_email_sent" if ok else "payroll_payslip_email_failed"
    append_audit_log("payroll", str(delivery.get("delivery_id", "")), audit_action, actor, before_delivery, {
        "delivery_id": delivery.get("delivery_id", ""),
        "payslip_id": delivery.get("payslip_id", ""),
        "batch_id": delivery.get("batch_id", ""),
        "employee_id": delivery.get("employee_id", ""),
        "employee_email": recipient,
        "status": delivery.get("status", ""),
        "provider": delivery.get("provider", ""),
        "attempt_count": attempt_count,
        "error": delivery.get("error", ""),
    })
    return delivery


def pdf_escape_text(value: Any) -> str:
    text = str(value).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    return text.encode("latin-1", errors="replace").decode("latin-1")


def simple_pdf_bytes(lines: list[str]) -> bytes:
    content_lines = ["BT", "/F1 11 Tf", "72 760 Td", "14 TL"]
    for line in lines[:48]:
        content_lines.append(f"({pdf_escape_text(line)}) Tj")
        content_lines.append("T*")
    content_lines.append("ET")
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream",
    ]
    payload = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(payload))
        payload.extend(f"{i} 0 obj\n".encode("ascii"))
        payload.extend(obj)
        payload.extend(b"\nendobj\n")
    xref = len(payload)
    payload.extend(f"xref\n0 {len(objects)+1}\n0000000000 65535 f \n".encode("ascii"))
    for offset in offsets[1:]:
        payload.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    payload.extend(f"trailer << /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    return bytes(payload)


def payslip_lines(record: dict[str, Any], batch: dict[str, Any]) -> list[str]:
    currency = str(record.get("currency", ""))
    return [
        "TACAI Payroll Payslip",
        f"Payslip Month: {record.get('Payroll Month (給与月)', record.get('payroll_month', ''))}",
        f"Batch: {batch.get('batch_id', '')} / Status: {batch.get('status', '')}",
        f"Employee No: {record.get('Employee No. (社員No.)', record.get('employee_no', ''))}",
        f"Employee Name: {record.get('Employee Name (氏名)', record.get('employee_name', ''))}",
        f"Entity: {record.get('entity', '')}",
        f"Country: {record.get('country', '')}",
        f"Payroll Scheme: {record.get('payroll_scheme', '')}",
        "",
        f"Gross Pay: {money_with_currency(record.get('Gross Pay (総支給額)', record.get('gross_pay', 0)), currency)}",
        f"Total Deduction: {money_with_currency(record.get('Total Deduction (控除合計)', record.get('total_deduction', 0)), currency)}",
        f"Net Pay: {money_with_currency(record.get('Net Pay (差引支給額)', record.get('net_pay', 0)), currency)}",
        "",
        "Tax values are reference-only unless confirmed by HR/Payroll.",
        f"Generated at: {now_iso()}",
    ]


def generate_payslips_for_batch(batch_id: str, context: dict[str, Any] | None, actor: str, messages: dict[str, str] | None = None) -> list[dict[str, Any]]:
    batch = find_payroll_batch(batch_id)
    if not batch:
        raise ValueError(t(messages, "error.batch_not_found", "Payroll batch was not found."))
    if str(batch.get("status", "")).lower() not in {"confirmed", "locked"}:
        raise ValueError(t(messages, "error.payslip_generation_not_allowed", "Payslips can only be generated after payroll confirmation."))
    records = records_for_batch(batch_id)
    if not records:
        raise ValueError(t(messages, "error.no_records_for_payslips", "No payroll records are available for payslip generation."))
    payslips = load_payslips()
    by_record = {str(item.get("record_id", "")): item for item in payslips}
    generated: list[dict[str, Any]] = []
    output_dir = PAYSLIP_OUTPUT_DIR / str(batch.get("payroll_month", "unknown")) / batch_id
    output_dir.mkdir(parents=True, exist_ok=True)
    for record in records:
        record_id = str(record.get("record_id", ""))
        payslip = dict(by_record.get(record_id, {}))
        payslip_id = str(payslip.get("payslip_id") or timestamp_id("payslip"))
        pdf_path = output_dir / f"{payslip_id}.pdf"
        pdf_path.write_bytes(simple_pdf_bytes(payslip_lines(record, batch)))
        payslip.update({
            "payslip_id": payslip_id,
            "batch_id": batch_id,
            "record_id": record_id,
            "employee_id": record.get("employee_id", ""),
            "employee_no": employee_no_from_any(record),
            "employee_name": record.get("employee_name") or record.get("Employee Name (氏名)") or "",
            "employee_email": record.get("employee_email", ""),
            "payroll_month": record.get("payroll_month") or record.get("Payroll Month (給与月)") or "",
            "pdf_status": "generated",
            "pdf_path": str(pdf_path),
            "generated_at": now_iso(),
            "generated_by": actor or "system",
            "delivery_status": payslip.get("delivery_status", "not_sent"),
        })
        by_record[record_id] = payslip
        generated.append(payslip)
    existing_without_records = [item for item in payslips if str(item.get("record_id", "")) not in by_record]
    save_payslips(existing_without_records + list(by_record.values()))
    append_audit_log("payroll", batch_id, "payroll_payslips_generated", actor, None, {"batch_id": batch_id, "count": len(generated)})
    return generated


def load_payslip_email_deliveries() -> list[dict[str, Any]]:
    return load_json_array(PAYSLIP_EMAIL_DELIVERIES_PATH)


def save_payslip_email_deliveries(deliveries: list[dict[str, Any]]) -> None:
    save_json_array(PAYSLIP_EMAIL_DELIVERIES_PATH, deliveries)


def select_payslip_for_email(payslip_id: str, actor: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    payslips = load_payslips()
    target = payslip_id.strip()
    deliveries = load_payslip_email_deliveries()
    latest = latest_delivery_by_payslip(deliveries)
    selected: dict[str, Any] | None = None
    for index, payslip in enumerate(payslips):
        if str(payslip.get("payslip_id", "")) == target:
            selected = dict(payslip)
            existing = latest.get(target)
            if str(selected.get("delivery_status", "")).lower() == "sent" or str((existing or {}).get("status", "")).lower() == "sent":
                raise ValueError(t(messages, "error.payslip_already_sent", "Payslip email has already been sent."))
            if str((existing or {}).get("status", "")).lower() == "queued":
                raise ValueError(t(messages, "error.payslip_already_queued", "Payslip email is already queued."))
            if not str(selected.get("employee_email", "")).strip():
                raise ValueError(t(messages, "error.employee_email_required", "Employee email is required before queuing payslip email."))
            if not EMAIL_PATTERN.fullmatch(str(selected.get("employee_email", "")).strip()):
                raise ValueError(t(messages, "error.invalid_employee_email", "Employee email format is invalid."))
            pdf_path, pdf_status = validated_payslip_pdf_path(selected)
            if pdf_status == "pdf_not_found":
                raise ValueError(t(messages, "error.payslip_pdf_missing", "Payslip PDF is missing."))
            if pdf_status != "ok":
                raise ValueError(t(messages, "error.payslip_pdf_invalid", "Payslip PDF path is invalid."))
            selected["delivery_status"] = "queued"
            selected["delivery_selected"] = True
            selected["delivery_selected_at"] = now_iso()
            selected["delivery_selected_by"] = actor or "system"
            selected["delivery_error"] = ""
            payslips[index] = selected
            break
    if not selected:
        raise ValueError(t(messages, "error.payslip_not_found", "Payslip was not found."))
    delivery = {
        "delivery_id": timestamp_id("delivery"),
        "payslip_id": target,
        "batch_id": selected.get("batch_id", ""),
        "employee_id": selected.get("employee_id", ""),
        "employee_email": selected.get("employee_email", ""),
        "selected_by": actor or "system",
        "selected_at": now_iso(),
        "status": "queued",
        "sent_at": "",
        "sent_by": "",
        "provider": "smtp",
        "attempt_count": 0,
        "last_attempt_at": "",
        "last_attempt_by": "",
        "error": "",
    }
    deliveries.append(delivery)
    save_payslip_email_deliveries(deliveries)
    save_payslips(payslips)
    append_audit_log("payroll", target, "payroll_payslips_selected_for_email", actor, None, delivery)
    return delivery


def load_audit_logs() -> list[dict[str, Any]]:
    return sorted(load_json_array(AUDIT_LOGS_PATH), key=lambda item: str(item.get("timestamp", "")), reverse=True)


def audit_logs_csv(logs: list[dict[str, Any]], actor: str = "system") -> str:
    output = StringIO()
    fieldnames = ["exported_at", "exported_by", "audit_id", "timestamp", "module", "record_id", "action", "user", "before_value", "after_value"]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    exported_at = now_iso()
    for item in logs:
        writer.writerow({
            "exported_at": exported_at,
            "exported_by": actor or "system",
            "audit_id": item.get("audit_id", ""),
            "timestamp": item.get("timestamp", ""),
            "module": item.get("module", ""),
            "record_id": item.get("record_id", ""),
            "action": item.get("action", ""),
            "user": item.get("user", ""),
            "before_value": json.dumps(item.get("before_value"), ensure_ascii=False),
            "after_value": json.dumps(item.get("after_value"), ensure_ascii=False),
        })
    return output.getvalue()


def load_salary_profiles() -> list[dict[str, Any]]:
    profiles = []
    for raw in load_json_array(SALARY_PROFILES_PATH):
        profile = dict(raw)
        for field in PROFILE_DECIMAL_FIELDS:
            profile[field] = parse_decimal(profile.get(field, "0"))
        profiles.append(profile)
    return profiles


def active_salary_profiles(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [profile for profile in profiles if str(profile.get("status", "active")).lower() == "active"]


def load_payroll_rules() -> list[dict[str, Any]]:
    rules = []
    source = load_json_array(PAYROLL_RULES_PATH)
    if not source:
        source = DEFAULT_PAYROLL_RULES
    for raw in source:
        rule = dict(raw)
        params = rule.get("parameters") if isinstance(rule.get("parameters"), dict) else {}
        rule["parameters"] = dict(params)
        rules.append(rule)
    return rules


def active_payroll_rules(rules: list[dict[str, Any]] | None = None, country: str = "") -> list[dict[str, Any]]:
    source = rules if rules is not None else load_payroll_rules()
    country_key = country.strip().upper()
    active = [rule for rule in source if str(rule.get("status", "active")).lower() == "active"]
    if country_key:
        active = [rule for rule in active if str(rule.get("country", "")).strip().upper() in {country_key, "ALL", ""}]
    return active


def find_payroll_rule(rule_id: str) -> dict[str, Any] | None:
    target = rule_id.strip()
    if not target:
        return None
    for rule in load_payroll_rules():
        if str(rule.get("rule_id", "")) == target:
            return rule
    return None


def find_default_rule_for_scheme(scheme: str) -> dict[str, Any] | None:
    for rule in active_payroll_rules():
        if str(rule.get("linked_scheme", "")) == scheme:
            return rule
    return None


def payroll_rule_label(rule: dict[str, Any] | None) -> str:
    if not rule:
        return ""
    return " / ".join(part for part in (str(rule.get("rule_code", "")).strip(), str(rule.get("rule_name", "")).strip()) if part) or str(rule.get("rule_id", ""))


def calculation_type_label(calculation_type: Any) -> str:
    value = str(calculation_type or "")
    return PAYROLL_RULE_CALCULATION_TYPES.get(value, value)


def payroll_rule_options(selected_rule_id: str = "", country: str = "") -> str:
    options = [option_html("", "-- Select payroll rule --", selected_rule_id)]
    for rule in active_payroll_rules(country=country):
        label = f"{payroll_rule_label(rule)} / {calculation_type_label(rule.get('calculation_type', ''))}"
        options.append(option_html(str(rule.get("rule_id", "")), label, selected_rule_id))
    return "".join(options)


def payroll_rule_from_form(form: dict[str, str], messages: dict[str, str] | None = None) -> dict[str, Any]:
    rule_code = form.get("rule_code", "").strip().upper()
    rule_name = form.get("rule_name", "").strip()
    calculation_type = form.get("calculation_type", "").strip()
    linked_scheme = form.get("linked_scheme", "").strip()
    if not rule_code or not rule_name or not calculation_type:
        raise ValueError(t(messages, "error.required_rule_fields", "Rule code, rule name, and calculation type are required."))
    if calculation_type not in PAYROLL_RULE_CALCULATION_TYPES:
        raise ValueError(t(messages, "error.invalid_calculation_type", "Invalid calculation type."))
    if linked_scheme and linked_scheme not in PAYROLL_SCHEMES:
        raise ValueError(t(messages, "error.invalid_payroll_scheme"))
    rounding_policy = form.get("rounding_policy", "round_to_yen").strip() or "round_to_yen"
    if rounding_policy not in ROUNDING_POLICIES:
        raise ValueError(t(messages, "error.invalid_rounding_policy", "Invalid rounding policy."))
    standard_hours = parse_decimal(form.get("standard_hours", "0"))
    require_nonnegative(standard_hours, "standard_hours", messages)
    parameters: dict[str, Any] = {}
    if standard_hours:
        parameters["standard_hours"] = standard_hours
    if truthy(form.get("cap_base_hours", "")):
        parameters["cap_base_hours"] = "true"
    return {
        "rule_id": form.get("rule_id", "").strip(),
        "rule_code": rule_code,
        "rule_name": rule_name,
        "country": form.get("country", "JP").strip().upper() or "JP",
        "linked_scheme": linked_scheme,
        "calculation_type": calculation_type,
        "rounding_policy": rounding_policy,
        "parameters": parameters,
        "effective_from": form.get("effective_from", date.today().isoformat()).strip() or date.today().isoformat(),
        "effective_to": form.get("effective_to", "").strip(),
        "status": form.get("status", "active").strip().lower() or "active",
        "description": form.get("description", "").strip(),
    }


def validate_payroll_rule_uniqueness(rule: dict[str, Any], existing_rules: list[dict[str, Any]], messages: dict[str, str] | None = None, exclude_rule_id: str = "") -> None:
    if str(rule.get("status", "active")).lower() != "active":
        return
    rule_code = str(rule.get("rule_code", "")).strip().casefold()
    if not rule_code:
        return
    for existing in existing_rules:
        if exclude_rule_id and str(existing.get("rule_id", "")) == exclude_rule_id:
            continue
        if str(existing.get("status", "active")).lower() != "active":
            continue
        if str(existing.get("rule_code", "")).strip().casefold() != rule_code:
            continue
        if dates_overlap(str(existing.get("effective_from", "")), str(existing.get("effective_to", "")), str(rule.get("effective_from", "")), str(rule.get("effective_to", ""))):
            raise ValueError(t(messages, "error.duplicate_active_rule", "An active payroll rule with the same code and overlapping effective dates already exists."))


def save_payroll_rule(rule: dict[str, Any], actor: str = "system", messages: dict[str, str] | None = None) -> dict[str, Any]:
    rules = load_payroll_rules()
    saved = dict(rule)
    saved["rule_id"] = saved.get("rule_id") or timestamp_id("rule")
    saved["updated_at"] = now_iso()
    before = None
    updated_rules = []
    replaced = False
    validate_payroll_rule_uniqueness(saved, rules, messages, str(saved["rule_id"]))
    for existing in rules:
        if str(existing.get("rule_id", "")) == str(saved["rule_id"]):
            before = dict(existing)
            saved["created_at"] = existing.get("created_at") or saved.get("created_at") or now_iso()
            updated_rules.append(saved)
            replaced = True
        else:
            updated_rules.append(existing)
    if not replaced:
        saved["created_at"] = saved.get("created_at") or now_iso()
        updated_rules.append(saved)
    if before and records_business_equal(before, saved):
        unchanged = dict(before)
        unchanged["_no_changes"] = True
        return unchanged
    save_json_array(PAYROLL_RULES_PATH, updated_rules)
    append_audit_log("payroll_rule", str(saved["rule_id"]), "payroll_rule_updated" if before else "payroll_rule_created", actor, before, saved)
    return saved


def deactivate_payroll_rule(rule_id: str, actor: str = "system", messages: dict[str, str] | None = None) -> dict[str, Any]:
    rules = load_payroll_rules()
    updated_rules = []
    saved = None
    before = None
    for rule in rules:
        if str(rule.get("rule_id", "")) == rule_id:
            before = dict(rule)
            rule = dict(rule)
            rule["status"] = "inactive"
            rule["updated_at"] = now_iso()
            saved = rule
        updated_rules.append(rule)
    if not saved:
        raise ValueError(t(messages, "error.rule_not_found", "Payroll rule was not found."))
    save_json_array(PAYROLL_RULES_PATH, updated_rules)
    append_audit_log("payroll_rule", str(saved["rule_id"]), "payroll_rule_deactivated", actor, before, saved)
    return saved


def profile_employee_key(profile: dict[str, Any]) -> str:
    external_id = str(profile.get("employee_external_id", "")).strip().casefold()
    if external_id:
        return f"id:{external_id}"
    return f"no:{str(profile.get('employee_no', '')).strip().casefold()}"


def dates_overlap(start_a: str, end_a: str, start_b: str, end_b: str) -> bool:
    def parsed(value: str, default: date) -> date:
        try:
            return date.fromisoformat(str(value or "").strip())
        except ValueError:
            return default
    a_start = parsed(start_a, date.min)
    a_end = parsed(end_a, date(9999, 12, 31))
    b_start = parsed(start_b, date.min)
    b_end = parsed(end_b, date(9999, 12, 31))
    return a_start <= b_end and b_start <= a_end


def validate_salary_profile_uniqueness(profile: dict[str, Any], existing_profiles: list[dict[str, Any]], messages: dict[str, str] | None = None, exclude_profile_id: str = "") -> None:
    if str(profile.get("status", "active")).lower() != "active":
        return
    key = profile_employee_key(profile)
    if key in {"id:", "no:"}:
        return
    for existing in existing_profiles:
        if exclude_profile_id and str(existing.get("profile_id", "")) == exclude_profile_id:
            continue
        if str(existing.get("status", "active")).lower() != "active":
            continue
        if profile_employee_key(existing) != key:
            continue
        if dates_overlap(str(existing.get("effective_from", "")), str(existing.get("effective_to", "")), str(profile.get("effective_from", "")), str(profile.get("effective_to", ""))):
            raise ValueError(t(messages, "error.duplicate_active_profile", "This employee already has an active salary profile for the same effective period."))


def find_salary_profile(profile_id: str) -> dict[str, Any] | None:
    target = profile_id.strip()
    for profile in load_salary_profiles():
        if str(profile.get("profile_id", "")) == target:
            return profile
    return None


def save_salary_profile(profile: dict[str, Any], actor: str = "system", messages: dict[str, str] | None = None) -> dict[str, Any]:
    profiles = load_salary_profiles()
    validate_salary_profile_uniqueness(profile, profiles, messages)
    saved = dict(profile)
    saved["profile_id"] = saved.get("profile_id") or timestamp_id("profile")
    saved["created_at"] = saved.get("created_at") or now_iso()
    saved["updated_at"] = now_iso()
    profiles.append(saved)
    save_json_array(SALARY_PROFILES_PATH, profiles)
    append_audit_log("payroll", str(saved["profile_id"]), "salary_profile_created", actor, None, saved)
    return saved


def update_salary_profile(profile: dict[str, Any], actor: str = "system", messages: dict[str, str] | None = None) -> dict[str, Any]:
    profiles = load_salary_profiles()
    profile_id = str(profile.get("profile_id", "")).strip()
    if not profile_id:
        raise ValueError(t(messages, "error.profile_required"))
    validate_salary_profile_uniqueness(profile, profiles, messages, profile_id)
    updated = []
    saved = None
    before = None
    for existing in profiles:
        if str(existing.get("profile_id", "")) == profile_id:
            before = dict(existing)
            saved = dict(profile)
            saved["profile_id"] = profile_id
            saved["created_at"] = existing.get("created_at") or now_iso()
            saved["updated_at"] = now_iso()
            updated.append(saved)
        else:
            updated.append(existing)
    if not saved:
        raise ValueError(t(messages, "error.profile_required"))
    if before and records_business_equal(before, saved):
        unchanged = dict(before)
        unchanged["_no_changes"] = True
        return unchanged
    save_json_array(SALARY_PROFILES_PATH, updated)
    append_audit_log("payroll", profile_id, "salary_profile_updated", actor, before, saved)
    return saved


def create_salary_profile_version(source_profile_id: str, profile: dict[str, Any], actor: str = "system", messages: dict[str, str] | None = None) -> dict[str, Any]:
    profiles = load_salary_profiles()
    source = None
    for existing in profiles:
        if str(existing.get("profile_id", "")) == source_profile_id:
            source = existing
            break
    if not source:
        raise ValueError(t(messages, "error.profile_required"))
    new_profile = dict(profile)
    new_profile.pop("profile_id", None)
    new_profile["previous_profile_id"] = source_profile_id
    effective_from = parse_iso_date(new_profile.get("effective_from", "")) or date.today()
    old_effective_to = (effective_from - timedelta(days=1)).isoformat()
    updated_profiles = []
    old_before = None
    old_after = None
    for existing in profiles:
        if str(existing.get("profile_id", "")) == source_profile_id:
            old_before = dict(existing)
            ended = dict(existing)
            ended["effective_to"] = old_effective_to
            ended["status"] = "inactive"
            ended["updated_at"] = now_iso()
            old_after = ended
            updated_profiles.append(ended)
        else:
            updated_profiles.append(existing)
    validate_salary_profile_uniqueness(new_profile, updated_profiles, messages)
    saved = dict(new_profile)
    saved["profile_id"] = timestamp_id("profile")
    saved["created_at"] = now_iso()
    saved["updated_at"] = now_iso()
    updated_profiles.append(saved)
    save_json_array(SALARY_PROFILES_PATH, updated_profiles)
    append_audit_log("payroll", source_profile_id, "salary_profile_version_ended", actor, old_before, old_after)
    append_audit_log("payroll", str(saved["profile_id"]), "salary_profile_version_created", actor, source, saved)
    return saved


def deactivate_salary_profile(profile_id: str, actor: str = "system", reason: str = "", messages: dict[str, str] | None = None) -> dict[str, Any]:
    target = profile_id.strip()
    profiles = load_salary_profiles()
    updated_profiles = []
    saved = None
    before = None
    for profile in profiles:
        if str(profile.get("profile_id", "")) == target:
            if str(profile.get("status", "active")).lower() != "active":
                raise ValueError(t(messages, "error.profile_already_inactive", "Salary profile is already inactive."))
            before = dict(profile)
            profile = dict(profile)
            profile["status"] = "inactive"
            profile["deactivated_at"] = now_iso()
            profile["deactivated_by"] = actor
            profile["deactivation_reason"] = reason.strip()
            profile["updated_at"] = now_iso()
            saved = profile
        updated_profiles.append(profile)
    if not saved:
        raise ValueError(t(messages, "error.profile_not_found", "Salary profile was not found."))
    save_json_array(SALARY_PROFILES_PATH, updated_profiles)
    append_audit_log("payroll", str(saved["profile_id"]), "salary_profile_deactivated", actor, before, saved)
    return saved


def void_salary_profile(profile_id: str, actor: str = "system", reason: str = "", messages: dict[str, str] | None = None) -> dict[str, Any]:
    target = profile_id.strip()
    profiles = load_salary_profiles()
    updated_profiles = []
    saved = None
    before = None
    for profile in profiles:
        if str(profile.get("profile_id", "")) == target:
            if str(profile.get("status", "active")).lower() == "voided":
                raise ValueError(t(messages, "error.profile_already_voided", "Salary profile is already voided."))
            before = dict(profile)
            profile = dict(profile)
            profile["status"] = "voided"
            profile["voided_at"] = now_iso()
            profile["voided_by"] = actor
            profile["void_reason"] = reason.strip()
            profile["created_in_error"] = True
            profile["updated_at"] = now_iso()
            saved = profile
        updated_profiles.append(profile)
    if not saved:
        raise ValueError(t(messages, "error.profile_not_found", "Salary profile was not found."))
    save_json_array(SALARY_PROFILES_PATH, updated_profiles)
    append_audit_log("payroll", str(saved["profile_id"]), "salary_profile_voided", actor, before, saved)
    return saved


def salary_profile_label(profile: dict[str, Any]) -> str:
    employee_no = str(profile.get("employee_no", "")).strip()
    employee_name = str(profile.get("employee_name", "")).strip()
    scheme = str(profile.get("payroll_scheme", "")).strip()
    return " / ".join(part for part in (employee_no, employee_name, scheme) if part) or str(profile.get("profile_id", ""))


def salary_profile_status(profile: dict[str, Any]) -> str:
    status = str(profile.get("status", "active") or "active").strip().lower()
    return status if status in {"active", "inactive", "voided"} else "inactive"


def salary_profile_status_label(status: str, messages: dict[str, str]) -> str:
    return t(messages, f"status.{status}", status)


def salary_profile_status_badge(status: str, messages: dict[str, str]) -> str:
    css_class = "status-active" if status == "active" else "status-inactive"
    if status == "voided":
        css_class = "status-inactive"
    return f'<span class="status-badge {css_class}">{h(salary_profile_status_label(status, messages))}</span>'


def salary_profile_from_form(form: dict[str, str], messages: dict[str, str] | None = None) -> dict[str, Any]:
    employee_no = form.get("employee_no", "").strip()
    employee_name = form.get("employee_name", "").strip()
    entity = form.get("entity", "").strip()
    payroll_scheme = form.get("payroll_scheme", "").strip()
    payroll_rule_id = form.get("payroll_rule_id", "").strip()
    payroll_rule = find_payroll_rule(payroll_rule_id) if payroll_rule_id else find_default_rule_for_scheme(payroll_scheme)
    if payroll_rule and not payroll_rule_id:
        payroll_rule_id = str(payroll_rule.get("rule_id", ""))
    if not employee_no or not employee_name or not entity or not payroll_scheme:
        raise ValueError(t(messages, "error.required_profile_fields"))
    if payroll_scheme not in PAYROLL_SCHEMES:
        raise ValueError(t(messages, "error.invalid_payroll_scheme"))
    if payroll_rule_id and not payroll_rule:
        raise ValueError(t(messages, "error.invalid_payroll_rule", "Invalid payroll rule."))
    today = date.today().isoformat()
    profile: dict[str, Any] = {
        "employee_no": employee_no,
        "employee_name": employee_name,
        "employee_external_id": form.get("employee_external_id", "").strip(),
        "employee_source": form.get("employee_source", "EmployeeAdmin" if form.get("employee_external_id", "").strip() else "manual").strip(),
        "entity": entity,
        "country": form.get("country", "JP").strip().upper() or "JP",
        "work_location_country": form.get("work_location_country", form.get("country", "JP")).strip().upper() or "JP",
        "currency": form.get("currency", "JPY").strip().upper() or "JPY",
        "payroll_scheme": payroll_scheme,
        "payroll_rule_id": payroll_rule_id,
        "payroll_rule_code": str(payroll_rule.get("rule_code", "")) if payroll_rule else "",
        "payroll_calculation_type": str(payroll_rule.get("calculation_type", "")) if payroll_rule else "",
        "rounding_policy": str(payroll_rule.get("rounding_policy", "round_to_yen")) if payroll_rule else "round_to_yen",
        "monthly_salary": parse_decimal(form.get("monthly_salary", "0")),
        "daily_rate": parse_decimal(form.get("daily_rate", "0")),
        "hourly_rate": parse_decimal(form.get("hourly_rate", "0")),
        "standard_monthly_working_days": parse_decimal(form.get("standard_monthly_working_days", "20")),
        "standard_monthly_hours": parse_decimal(form.get("standard_monthly_hours", "160")),
        "effective_from": form.get("effective_from", today).strip() or today,
        "effective_to": form.get("effective_to", "").strip(),
        "termination_date": form.get("termination_date", "").strip(),
        "status": form.get("status", "active").strip().lower() or "active",
        "tax_reference_mode": form.get("tax_reference_mode", "none").strip() or "none",
        "tax_reference_city": form.get("tax_reference_city", "Tokyo").strip(),
        "tax_reference_notes": form.get("tax_reference_notes", "").strip(),
        "jp_dependent_count": parse_decimal(form.get("jp_dependent_count", "0")),
        "jp_monthly_health_insurance": parse_decimal(form.get("jp_monthly_health_insurance", "0")),
        "jp_monthly_pension": parse_decimal(form.get("jp_monthly_pension", "0")),
        "jp_monthly_employment_insurance": parse_decimal(form.get("jp_monthly_employment_insurance", "0")),
        "jp_fixed_resident_tax_monthly": parse_decimal(form.get("jp_fixed_resident_tax_monthly", "0")),
        "cn_monthly_social_insurance": parse_decimal(form.get("cn_monthly_social_insurance", "0")),
        "cn_monthly_housing_fund": parse_decimal(form.get("cn_monthly_housing_fund", "0")),
        "cn_monthly_special_additional_deductions": parse_decimal(form.get("cn_monthly_special_additional_deductions", "0")),
        "cn_monthly_other_deductions": parse_decimal(form.get("cn_monthly_other_deductions", "0")),
        "cn_iit_cumulative_months_default": parse_decimal(form.get("cn_iit_cumulative_months_default", "0")),
        "sg_cpf_employee": parse_decimal(form.get("sg_cpf_employee", "0")),
        "sg_cpf_employer": parse_decimal(form.get("sg_cpf_employer", "0")),
    }
    if profile["tax_reference_mode"] not in TAX_REFERENCE_MODES:
        profile["tax_reference_mode"] = "none"
    for field in PROFILE_DECIMAL_FIELDS:
        require_nonnegative(profile[field], field, messages)
    return profile


def profile_select_options(selected_profile_id: str = "") -> str:
    profiles = active_salary_profiles(load_salary_profiles())
    options = [option_html("", "-- Select salary profile --", selected_profile_id)]
    for profile in profiles:
        rule = find_payroll_rule(str(profile.get("payroll_rule_id", "")))
        rule_label = payroll_rule_label(rule) if rule else payroll_scheme_label(profile.get('payroll_scheme', ''))
        label = f"{profile.get('employee_no', '')} - {profile.get('employee_name', '')} / {rule_label}"
        options.append(option_html(str(profile.get("profile_id", "")), label, selected_profile_id))
    return "".join(options)


def payroll_scheme_label(scheme: Any) -> str:
    value = str(scheme or "")
    return PAYROLL_SCHEMES.get(value, value)


def tax_reference_mode_label(mode: Any) -> str:
    value = str(mode or "none")
    return TAX_REFERENCE_MODES.get(value, value)


def normalize_country(value: Any) -> str:
    country = str(value or "").strip().upper()
    return country if country in PAYROLL_REPORT_TEMPLATES else "ALL"


def payroll_record_country(record: dict[str, Any]) -> str:
    for key in ("country", "work_location_country"):
        value = str(record.get(key, "")).strip().upper()
        if value in COUNTRY_DEFAULTS:
            return value
    scheme = str(record.get("payroll_scheme", "")).lower()
    if scheme.startswith("jp_"):
        return "JP"
    if scheme.startswith("cn_"):
        return "CN"
    if scheme.startswith("sg_"):
        return "SG"
    currency = str(record.get("currency", "")).strip().upper()
    if currency == "JPY":
        return "JP"
    if currency == "CNY":
        return "CN"
    if currency == "SGD":
        return "SG"
    if any(key in record for key in ["Employee No. (社員No.)", "Base Salary (基本給)", "Income Tax (所得税)"]):
        return "JP"
    return "JP"


def payroll_record_currency(record: dict[str, Any]) -> str:
    currency = str(record.get("currency", "")).strip().upper()
    if currency:
        return currency
    return COUNTRY_DEFAULTS.get(payroll_record_country(record), {}).get("currency", "")


def payroll_report_template(country: Any) -> dict[str, Any]:
    normalized = normalize_country(country)
    return PAYROLL_REPORT_TEMPLATES.get(normalized, PAYROLL_REPORT_TEMPLATES["ALL"])


def payroll_report_language(country: str, fallback_lang: str) -> str:
    template = payroll_report_template(country)
    template_lang = str(template.get("language", ""))
    return template_lang if template_lang in SUPPORTED_LANGS else fallback_lang


def payroll_record_value(record: dict[str, Any], key: str) -> Any:
    fallback_map = {
        "employee_no": ["employee_no", "Employee No. (社員No.)"],
        "employee_name": ["employee_name", "Employee Name (氏名)"],
        "payroll_month": ["payroll_month", "Payroll Month (給与月)"],
        "calculated_base_pay": ["calculated_base_pay", "Base Salary (基本給)"],
        "additional_payment": ["additional_payment", "Additional Payment (追加支給)"],
        "additional_deduction": ["additional_deduction", "Additional Deduction (追加控除)"],
        "gross_pay": ["gross_pay", "Gross Pay (総支給額)"],
        "total_deduction": ["total_deduction", "Total Deduction (控除合計)"],
        "net_pay": ["net_pay", "Net Pay (差引支給額)"],
        "confirmed_income_tax": ["confirmed_income_tax", "Income Tax (所得税)"],
        "jp_health_insurance": ["jp_health_insurance", "Health Insurance (健康保険)"],
        "jp_pension": ["jp_pension", "Pension (厚生年金)"],
        "jp_employment_insurance": ["jp_employment_insurance", "Employment Insurance (雇用保険)"],
    }
    if key == "country":
        return payroll_record_country(record)
    if key == "currency":
        return payroll_record_currency(record)
    if key == "payroll_scheme":
        return payroll_scheme_label(record.get("payroll_scheme", ""))
    if key == "tax_reference_mode":
        return tax_reference_mode_label(record.get("tax_reference_mode", "none"))
    for candidate in fallback_map.get(key, [key]):
        value = record.get(candidate)
        if value not in {None, ""}:
            return value
    return Decimal("0") if key in AMOUNT_REPORT_KEYS else ""


def filter_payroll_records(records: list[dict[str, Any]], country: str = "ALL", month: str = "") -> list[dict[str, Any]]:
    normalized_country = normalize_country(country)
    filtered = []
    for record in records:
        if normalized_country != "ALL" and payroll_record_country(record) != normalized_country:
            continue
        if month and str(payroll_record_value(record, "payroll_month")) != month:
            continue
        filtered.append(record)
    return filtered


def report_filter_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    country_filter = str((context or {}).get("country_filter", "ALL"))
    month_filter = str((context or {}).get("month_filter", ""))
    country_options = "".join(option_html(value, t(messages, f"country.{value.lower()}", value), country_filter) for value in ["ALL", "JP", "CN", "SG"])
    return f"""
    <form method="get" action="{h(url_with_lang('/payroll-register', lang))}" class="actions">
      <input type="hidden" name="lang" value="{h(lang)}">
      <div><label>{h(t(messages, 'report.country_filter'))}</label><select name="country">{country_options}</select></div>
      <div><label>{h(t(messages, 'report.month_filter'))}</label><input name="month" placeholder="2026-06" value="{h(month_filter)}"></div>
      <button type="submit">{h(t(messages, 'report.apply_filter'))}</button>
    </form>
    """


def portal_return_button_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    return f'<a class="button ghost" href="{h(PORTAL_BASE_URL)}">{h(t(messages, "action.return_to_portal"))}</a>'


def employee_master_dependency_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    return f"""
    <section class="message-strip message-warning" role="status">
      <strong>{h(t(messages, 'payroll.employee_master_dependency_title'))}</strong><br>
      {h(t(messages, 'payroll.employee_master_dependency_desc'))}
    </section>
    """


def format_report_cell(record: dict[str, Any], column: dict[str, Any], for_csv: bool = False) -> str:
    key = str(column.get("key", ""))
    value = payroll_record_value(record, key)
    if column.get("amount"):
        return plain_amount(value) if for_csv else money_with_currency(value, payroll_record_currency(record))
    if key == "record_status" and not for_csv:
        return status_badge("Voided" if str(value) == "voided" else str(value or "Saved"))
    return str(value)


def report_amount_total(records: list[dict[str, Any]], key: str) -> Decimal:
    return sum((parse_decimal(payroll_record_value(record, key)) for record in active_payroll_records(records)), Decimal("0"))


def truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "checked"}


def default_tax_reference_config() -> dict[str, Any]:
    return {
        "version": "2026-reference-v1",
        "jp": {
            "enabled": True,
            "method": "monthly_withholding_table_reference",
            "default_city": "Tokyo",
            "resident_tax_auto_calculation": False,
            "withholding_table": [],
        },
        "cn": {
            "enabled": True,
            "method": "cumulative_annual_iit_reference",
            "standard_monthly_deduction": "5000",
            "rates": [
                {"upper": "36000", "rate": "0.03", "quick_deduction": "0"},
                {"upper": "144000", "rate": "0.10", "quick_deduction": "2520"},
                {"upper": "300000", "rate": "0.20", "quick_deduction": "16920"},
                {"upper": "420000", "rate": "0.25", "quick_deduction": "31920"},
                {"upper": "660000", "rate": "0.30", "quick_deduction": "52920"},
                {"upper": "960000", "rate": "0.35", "quick_deduction": "85920"},
                {"upper": None, "rate": "0.45", "quick_deduction": "181920"},
            ],
        },
    }


def load_tax_reference_config() -> dict[str, Any]:
    default = default_tax_reference_config()
    if not TAX_REFERENCE_CONFIG_PATH.exists():
        return default
    try:
        loaded = json.loads(TAX_REFERENCE_CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default
    if not isinstance(loaded, dict):
        return default
    merged = dict(default)
    for section in ("jp", "cn"):
        if isinstance(loaded.get(section), dict):
            merged[section] = {**default.get(section, {}), **loaded[section]}
    if loaded.get("version"):
        merged["version"] = loaded["version"]
    return merged


def optional_decimal(value: Any, fallback: Any = "0") -> Decimal:
    text = str(value if value is not None else "").strip()
    return parse_decimal(text if text else fallback)


def decimal_to_int(value: Any) -> int:
    amount = parse_decimal(value)
    return int(amount)


def calculate_reference_tax(profile: dict[str, Any], input_data: dict[str, Any], gross_pay: Decimal, payroll_month_value: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    mode = str(profile.get("tax_reference_mode", "none") or "none")
    if mode == "jp_income_tax_reference":
        return calculate_japan_income_tax_reference(profile, input_data, gross_pay, messages)
    if mode == "cn_iit_reference":
        return calculate_china_iit_reference(profile, input_data, gross_pay, payroll_month_value, messages)
    return {
        "tax_reference_mode": "none",
        "tax_reference_city": str(profile.get("tax_reference_city", "")),
        "tax_reference_status": "not_applicable",
        "tax_reference_review_required": False,
        "estimated_income_tax": Decimal("0"),
        "estimated_resident_tax": Decimal("0"),
        "taxable_income_reference": Decimal("0"),
        "tax_reference_basis": {},
        "tax_reference_warnings": [],
    }


def calculate_japan_income_tax_reference(profile: dict[str, Any], input_data: dict[str, Any], gross_pay: Decimal, messages: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_tax_reference_config()
    jp_config = config.get("jp", {}) if isinstance(config.get("jp"), dict) else {}
    warnings: list[str] = [t(messages, "tax_reference.hr_confirm_required")]
    override_social = str(input_data.get("jp_monthly_social_insurance_override", "")).strip()
    if override_social:
        monthly_social_insurance = parse_decimal(override_social)
    else:
        monthly_social_insurance = (
            parse_decimal(profile.get("jp_monthly_health_insurance", "0"))
            + parse_decimal(profile.get("jp_monthly_pension", "0"))
            + parse_decimal(profile.get("jp_monthly_employment_insurance", "0"))
        )
    dependent_text = str(input_data.get("jp_dependent_count_override", "")).strip()
    dependent_count = decimal_to_int(dependent_text if dependent_text else profile.get("jp_dependent_count", "0"))
    taxable_income = max(Decimal("0"), gross_pay - monthly_social_insurance)
    table = jp_config.get("withholding_table") if isinstance(jp_config.get("withholding_table"), list) else []
    estimated_income_tax = Decimal("0")
    status = "estimated"
    if table:
        estimated_income_tax = lookup_japan_withholding_table(table, taxable_income, dependent_count)
        if estimated_income_tax == 0:
            warnings.append(t(messages, "tax_reference.jp_table_no_match"))
    else:
        status = "not_configured"
        warnings.append(t(messages, "tax_reference.missing_jp_table"))
    resident_tax_text = str(input_data.get("jp_resident_tax_monthly", "")).strip()
    estimated_resident_tax = parse_decimal(resident_tax_text if resident_tax_text else profile.get("jp_fixed_resident_tax_monthly", "0"))
    return {
        "tax_reference_mode": "jp_income_tax_reference",
        "tax_reference_city": str(profile.get("tax_reference_city") or jp_config.get("default_city") or "Tokyo"),
        "tax_reference_status": status,
        "tax_reference_review_required": True,
        "estimated_income_tax": estimated_income_tax.quantize(Decimal("1")),
        "estimated_resident_tax": estimated_resident_tax.quantize(Decimal("1")),
        "taxable_income_reference": taxable_income.quantize(Decimal("1")),
        "tax_reference_basis": {
            "method": jp_config.get("method", "monthly_withholding_table_reference"),
            "gross_pay": gross_pay,
            "monthly_social_insurance": monthly_social_insurance,
            "dependent_count": dependent_count,
            "resident_tax_auto_calculation": False,
        },
        "tax_reference_warnings": warnings,
    }


def lookup_japan_withholding_table(table: list[Any], taxable_income: Decimal, dependent_count: int) -> Decimal:
    for row in table:
        if not isinstance(row, dict):
            continue
        lower = parse_decimal(row.get("lower", "0"))
        upper_raw = row.get("upper")
        upper = None if upper_raw in {None, ""} else parse_decimal(upper_raw)
        if taxable_income < lower or (upper is not None and taxable_income >= upper):
            continue
        dependents = row.get("dependents")
        if isinstance(dependents, dict):
            return parse_decimal(dependents.get(str(dependent_count), dependents.get("0", "0")))
        return parse_decimal(row.get(f"tax_{dependent_count}", row.get("tax_0", "0")))
    return Decimal("0")


def calculate_china_iit_reference(profile: dict[str, Any], input_data: dict[str, Any], gross_pay: Decimal, payroll_month_value: str, messages: dict[str, str] | None = None) -> dict[str, Any]:
    config = load_tax_reference_config()
    cn_config = config.get("cn", {}) if isinstance(config.get("cn"), dict) else {}
    warnings: list[str] = [t(messages, "tax_reference.hr_confirm_required"), t(messages, "tax_reference.cn_cumulative_note")]
    month_number = int(payroll_month_value.split("-", 1)[1])
    cumulative_months = decimal_to_int(input_data.get("cn_cumulative_months") or profile.get("cn_iit_cumulative_months_default") or month_number)
    if cumulative_months <= 0:
        cumulative_months = month_number
    prior_ytd_income = parse_decimal(input_data.get("cn_prior_ytd_income", "0"))
    prior_ytd_social_insurance = parse_decimal(input_data.get("cn_prior_ytd_social_insurance", "0"))
    prior_ytd_housing_fund = parse_decimal(input_data.get("cn_prior_ytd_housing_fund", "0"))
    prior_ytd_special = parse_decimal(input_data.get("cn_prior_ytd_special_additional_deductions", "0"))
    prior_ytd_other = parse_decimal(input_data.get("cn_prior_ytd_other_deductions", "0"))
    prior_ytd_tax_withheld = parse_decimal(input_data.get("cn_prior_ytd_tax_withheld", "0"))
    if cumulative_months > 1 and prior_ytd_income == 0:
        warnings.append(t(messages, "tax_reference.missing_cn_ytd"))
    current_social_insurance = parse_decimal(profile.get("cn_monthly_social_insurance", "0"))
    current_housing_fund = parse_decimal(profile.get("cn_monthly_housing_fund", "0"))
    current_special = parse_decimal(profile.get("cn_monthly_special_additional_deductions", "0"))
    current_other = parse_decimal(profile.get("cn_monthly_other_deductions", "0"))
    standard_monthly_deduction = parse_decimal(cn_config.get("standard_monthly_deduction", "5000"))
    cumulative_income = prior_ytd_income + gross_pay
    cumulative_social_insurance = prior_ytd_social_insurance + current_social_insurance
    cumulative_housing_fund = prior_ytd_housing_fund + current_housing_fund
    cumulative_special = prior_ytd_special + current_special
    cumulative_other = prior_ytd_other + current_other
    cumulative_standard = standard_monthly_deduction * Decimal(cumulative_months)
    cumulative_taxable_income = max(Decimal("0"), cumulative_income - cumulative_social_insurance - cumulative_housing_fund - cumulative_standard - cumulative_special - cumulative_other)
    rate, quick_deduction = select_china_iit_rate(cumulative_taxable_income, cn_config)
    cumulative_tax_due = max(Decimal("0"), cumulative_taxable_income * rate - quick_deduction).quantize(Decimal("1"))
    current_month_iit = max(Decimal("0"), cumulative_tax_due - prior_ytd_tax_withheld).quantize(Decimal("1"))
    return {
        "tax_reference_mode": "cn_iit_reference",
        "tax_reference_city": str(profile.get("tax_reference_city", "")),
        "tax_reference_status": "estimated",
        "tax_reference_review_required": True,
        "estimated_income_tax": current_month_iit,
        "estimated_resident_tax": Decimal("0"),
        "taxable_income_reference": cumulative_taxable_income.quantize(Decimal("1")),
        "tax_reference_basis": {
            "method": cn_config.get("method", "cumulative_annual_iit_reference"),
            "cumulative_months": cumulative_months,
            "gross_pay": gross_pay,
            "prior_ytd_income": prior_ytd_income,
            "prior_ytd_tax_withheld": prior_ytd_tax_withheld,
            "standard_monthly_deduction": standard_monthly_deduction,
            "cumulative_taxable_income": cumulative_taxable_income,
            "rate": rate,
            "quick_deduction": quick_deduction,
            "cumulative_tax_due": cumulative_tax_due,
        },
        "tax_reference_warnings": warnings,
    }


def select_china_iit_rate(cumulative_taxable_income: Decimal, cn_config: dict[str, Any]) -> tuple[Decimal, Decimal]:
    rates = cn_config.get("rates") if isinstance(cn_config.get("rates"), list) else default_tax_reference_config()["cn"]["rates"]
    for row in rates:
        if not isinstance(row, dict):
            continue
        upper = row.get("upper")
        if upper in {None, ""} or cumulative_taxable_income <= parse_decimal(upper):
            return parse_decimal(row.get("rate", "0")), parse_decimal(row.get("quick_deduction", "0"))
    return Decimal("0"), Decimal("0")


def rounding_policy_label(policy: Any) -> str:
    value = str(policy or "round_to_yen")
    return ROUNDING_POLICIES.get(value, value)


def payroll_rule_form_html(rule: dict[str, Any] | None, context: dict[str, Any] | None = None, action_path: str = "/payroll-rules", submit_key: str = "action.save_rule") -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    rule = rule or {}
    country_options = "".join(option_html(value, value, str(rule.get("country", "JP"))) for value in ["JP", "CN", "SG", "ALL"])
    scheme_options = "".join(option_html(key, payroll_scheme_label(key), str(rule.get("linked_scheme", ""))) for key in PAYROLL_SCHEMES)
    calculation_options = "".join(option_html(key, calculation_type_label(key), str(rule.get("calculation_type", ""))) for key in PAYROLL_RULE_CALCULATION_TYPES)
    rounding_options = "".join(option_html(key, rounding_policy_label(key), str(rule.get("rounding_policy", "round_to_yen"))) for key in ROUNDING_POLICIES)
    params = rule.get("parameters") if isinstance(rule.get("parameters"), dict) else {}
    standard_hours = plain_amount(params.get("standard_hours", "160"))
    cap_base_hours = "on" if truthy(params.get("cap_base_hours", "")) else ""
    return f"""
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.rule_code'))}</label><input name="rule_code" required value="{h(rule.get('rule_code', ''))}" placeholder="JP_CONSULTANT_HOURLY_BASE_PRORATED"></div>
      <div><label>{h(t(messages, 'field.rule_name'))}</label><input name="rule_name" required value="{h(rule.get('rule_name', ''))}" placeholder="Japan consultant hourly + base"></div>
      <div><label>{h(t(messages, 'field.country'))}</label><select name="country">{country_options}</select></div>
      <div><label>{h(t(messages, 'field.payroll_scheme'))}</label><select name="linked_scheme">{scheme_options}</select></div>
      <div><label>{h(t(messages, 'field.calculation_type'))}</label><select name="calculation_type" required>{calculation_options}</select></div>
      <div><label>{h(t(messages, 'field.rounding_policy'))}</label><select name="rounding_policy">{rounding_options}</select></div>
      <div><label>{h(t(messages, 'field.standard_monthly_hours'))}</label><input name="standard_hours" type="number" min="0" step="0.01" value="{h(standard_hours)}"></div>
      <div><label>{h(t(messages, 'field.cap_base_hours'))}</label><select name="cap_base_hours">{option_html('on', t(messages, 'status.active'), cap_base_hours)}{option_html('', t(messages, 'status.inactive'), cap_base_hours)}</select></div>
      <div><label>{h(t(messages, 'field.effective_from'))}</label><input name="effective_from" type="date" value="{h(rule.get('effective_from', date.today().isoformat()))}"></div>
      <div><label>{h(t(messages, 'field.effective_to'))}</label><input name="effective_to" type="date" value="{h(rule.get('effective_to', ''))}"></div>
      <div><label>{h(t(messages, 'field.status'))}</label><select name="status">{option_html('active', t(messages, 'status.active'), str(rule.get('status', 'active')))}{option_html('inactive', t(messages, 'status.inactive'), str(rule.get('status', 'active')))}</select></div>
      <div><label>{h(t(messages, 'field.description'))}</label><input name="description" value="{h(rule.get('description', ''))}" placeholder="Business notes"></div>
    </div>
    <div class="sap-toolbar">{portal_return_button_html(context)}<button type="submit">{h(t(messages, submit_key))}</button></div>
  </form>
"""


def payroll_rule_edit_html(rule: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    rule_id = str(rule.get("rule_id", ""))
    deactivate_button = ""
    if str(rule.get("status", "active")).lower() == "active":
        deactivate_button = f"""
        <form method="post" action="{h(url_with_lang(f'/payroll-rules/{quote(rule_id)}/deactivate', lang))}" class="actions">
          <button class="danger" type="submit">{h(t(messages, 'action.deactivate'))}</button>
        </form>
        """
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'payroll_rules.edit_title'))}: {h(payroll_rule_label(rule))}</h2>
  <p class="message-strip message-warning">{h(t(messages, 'payroll_rules.edit_desc'))}</p>
</section>
<section class="sap-section">
  {payroll_rule_form_html(rule, context, f'/payroll-rules/{quote(rule_id)}/edit', 'action.save_rule')}
  {deactivate_button}
</section>
"""


def payroll_rules_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    rules = load_payroll_rules()
    rows = []
    for rule in rules:
        params = rule.get("parameters") if isinstance(rule.get("parameters"), dict) else {}
        rule_id = str(rule.get("rule_id", ""))
        edit_url = url_with_lang(f"/payroll-rules/{quote(rule_id)}/edit", lang)
        deactivate_form = ""
        if str(rule.get("status", "active")).lower() == "active":
            deactivate_form = f"""
            <form method="post" action="{h(url_with_lang(f'/payroll-rules/{quote(rule_id)}/deactivate', lang))}" style="display:inline">
              <button class="warning" type="submit">{h(t(messages, 'action.deactivate'))}</button>
            </form>
            """
        rows.append(f"""
        <tr>
          <td>{h(rule.get('rule_code', ''))}</td>
          <td>{h(rule.get('rule_name', ''))}</td>
          <td>{h(rule.get('country', ''))}</td>
          <td>{h(payroll_scheme_label(rule.get('linked_scheme', '')))}</td>
          <td>{h(calculation_type_label(rule.get('calculation_type', '')))}</td>
          <td>{h(rounding_policy_label(rule.get('rounding_policy', 'round_to_yen')))}</td>
          <td>{h(json.dumps(to_json_safe(params), ensure_ascii=False))}</td>
          <td>{h(rule.get('effective_from', ''))}</td>
          <td>{h(rule.get('effective_to', ''))}</td>
          <td>{h(rule.get('status', 'active'))}</td>
          <td>{h(rule.get('description', ''))}</td>
          <td><a class="button secondary" href="{h(edit_url)}">{h(t(messages, 'action.edit'))}</a> {deactivate_form}</td>
        </tr>
        """)
    empty = f"<tr><td colspan='12' class='muted'>{h(t(messages, 'payroll_rules.empty'))}</td></tr>" if not rows else ""
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'payroll_rules.title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'payroll_rules.desc'))}</p>
  <div class="sap-object-meta"><span class="status-badge">{len(rules)} {h(t(messages, 'payroll_rules.count'))}</span></div>
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'payroll_rules.new_title'))}</h3>
  {payroll_rule_form_html(None, context)}
</section>
<section class="panel wide" style="margin-top: 18px;">
  <table>
    <thead><tr><th>{h(t(messages, 'field.rule_code'))}</th><th>{h(t(messages, 'field.rule_name'))}</th><th>{h(t(messages, 'field.country'))}</th><th>{h(t(messages, 'field.payroll_scheme'))}</th><th>{h(t(messages, 'field.calculation_type'))}</th><th>{h(t(messages, 'field.rounding_policy'))}</th><th>{h(t(messages, 'field.parameters'))}</th><th>{h(t(messages, 'field.effective_from'))}</th><th>{h(t(messages, 'field.effective_to'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.description'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
    <tbody>{empty if empty else ''.join(rows)}</tbody>
  </table>
</section>
"""


def eligible_employeeadmin_payroll_employees(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    profiled_keys = {profile_employee_key(profile) for profile in active_salary_profiles(load_salary_profiles())}
    eligible = []
    for employee in load_employeeadmin_employees(context):
        status = str(employee.get("status", "")).strip().lower()
        if status and status not in PAYROLL_ELIGIBLE_EMPLOYEE_STATUSES:
            continue
        if not bool(employee.get("payroll_ready", False)):
            continue
        employee_id = str(employee.get("employee_id", "")).strip().casefold()
        employee_no = str(employee.get("employee_number", employee.get("employee_no", ""))).strip().casefold()
        if (employee_id and f"id:{employee_id}" in profiled_keys) or (employee_no and f"no:{employee_no}" in profiled_keys):
            continue
        eligible.append(employee)
    return eligible


def employee_options_html(employees: list[dict[str, Any]], messages: dict[str, str]) -> str:
    options = [f'<option value="">{h(t(messages, "salary_profiles.employee_select_placeholder"))}</option>']
    for employee in employees:
        country = employee.get("work_country") or employee.get("country_code") or employee.get("country") or "JP"
        options.append(
            '<option value="{id}" data-number="{number}" data-name="{name}" data-entity="{entity}" data-country="{country}" data-status="{status}">{number} - {name} / {entity} / {readiness}%</option>'.format(
                id=h(employee.get("employee_id", "")),
                number=h(employee.get("employee_number", employee.get("employee_no", ""))),
                name=h(employee.get("display_name", "")),
                entity=h(employee.get("entity_label") or employee.get("entity_name") or employee.get("entity_id", "")),
                country=h(country),
                status=h(employee.get("status", "")),
                readiness=h(employee.get("payroll_readiness_percent", "")),
            )
        )
    return "".join(options)


def select_options(values: list[str], selected: Any = "") -> str:
    return "".join(option_html(value, value, str(selected)) for value in values)


def salary_profile_form_html(profile: dict[str, Any] | None, context: dict[str, Any] | None, action_path: str, submit_key: str, include_employee_picker: bool = False) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    profile = profile or {}
    employee_picker = ""
    if include_employee_picker:
        employees = eligible_employeeadmin_payroll_employees(context)
        employee_picker = f"""
        <p class="message-strip {'message-success' if employees else 'message-warning'}">{h(t(messages, 'salary_profiles.eligible_employee_count')).format(count=len(employees))}</p>
        <input type="hidden" name="employee_source" value="EmployeeAdmin">
        <div><label>{h(t(messages, 'field.employeeadmin_employee'))}</label><select id="employee-source-select" name="employee_external_id">{employee_options_html(employees, messages)}</select></div>
        """
    else:
        employee_picker = f'<input type="hidden" name="employee_source" value="{h(profile.get("employee_source", "EmployeeAdmin"))}"><input type="hidden" name="employee_external_id" value="{h(profile.get("employee_external_id", ""))}">'
    country_options = select_options(COUNTRY_OPTIONS, profile.get("country", "JP"))
    work_location_options = select_options(WORK_LOCATION_OPTIONS, profile.get("work_location_country", profile.get("country", "JP")))
    currency_options = select_options(CURRENCY_OPTIONS, profile.get("currency", "JPY"))
    scheme_options = "".join(option_html(key, payroll_scheme_label(key), str(profile.get("payroll_scheme", ""))) for key in PAYROLL_SCHEMES)
    rule_options = payroll_rule_options(str(profile.get("payroll_rule_id", "")))
    tax_mode_options = "".join(option_html(key, tax_reference_mode_label(key), str(profile.get("tax_reference_mode", "none"))) for key in TAX_REFERENCE_MODES)
    picker_employees = eligible_employeeadmin_payroll_employees(context) if include_employee_picker else load_employeeadmin_employees(context)
    employee_no_options = "".join(f'<option value="{h(employee.get("employee_number", employee.get("employee_no", "")))}">{h(employee.get("employee_number", employee.get("employee_no", "")))} - {h(employee.get("display_name", ""))}</option>' for employee in picker_employees if str(employee.get("employee_number", employee.get("employee_no", ""))).strip())
    entity_values = sorted({str(employee.get("entity_label") or employee.get("entity_name") or employee.get("entity_id") or "").strip() for employee in picker_employees if str(employee.get("entity_label") or employee.get("entity_name") or employee.get("entity_id") or "").strip()} | {str(profile.get("entity", "")).strip()})
    entity_options = "".join(f'<option value="{h(value)}">{h(value)}</option>' for value in entity_values if value)
    return f"""
  <form method="post" action="{h(url_with_lang(action_path, lang))}">
    <datalist id="profile-employee-no-options">{employee_no_options}</datalist>
    <datalist id="profile-entity-options">{entity_options}</datalist>
    <div class="form-grid">
      {employee_picker}
      <div><label>{h(t(messages, 'field.employee_no'))}</label><input id="profile-employee-no" name="employee_no" list="profile-employee-no-options" required value="{h(profile.get('employee_no', ''))}" placeholder="E001"></div>
      <div><label>{h(t(messages, 'field.employee_name'))}</label><input id="profile-employee-name" name="employee_name" required value="{h(profile.get('employee_name', ''))}" placeholder="Employee Name"></div>
      <div><label>{h(t(messages, 'field.entity'))}</label><input id="profile-entity" name="entity" list="profile-entity-options" required value="{h(profile.get('entity', ''))}" placeholder="TAC Japan / TAC China / TAC Singapore"></div>
      <div><label>{h(t(messages, 'field.country'))}</label><select id="profile-country" name="country">{country_options}</select></div>
      <div><label>{h(t(messages, 'field.work_location_country'))}</label><select name="work_location_country">{work_location_options}</select></div>
      <div><label>{h(t(messages, 'field.currency'))}</label><select name="currency">{currency_options}</select></div>
      <div><label>{h(t(messages, 'field.payroll_scheme'))}</label><select name="payroll_scheme" required>{scheme_options}</select></div>
      <div><label>{h(t(messages, 'nav.payroll_rules'))}</label><select name="payroll_rule_id">{rule_options}</select></div>
      <div><label>{h(t(messages, 'field.monthly_salary'))}</label><input name="monthly_salary" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('monthly_salary', '0')))}"></div>
      <div><label>{h(t(messages, 'field.daily_rate'))}</label><input name="daily_rate" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('daily_rate', '0')))}"></div>
      <div><label>{h(t(messages, 'field.hourly_rate'))}</label><input name="hourly_rate" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('hourly_rate', '0')))}"></div>
      <div><label>{h(t(messages, 'field.standard_monthly_working_days'))}</label><input name="standard_monthly_working_days" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('standard_monthly_working_days', '20')))}"></div>
      <div><label>{h(t(messages, 'field.standard_monthly_hours'))}</label><input name="standard_monthly_hours" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('standard_monthly_hours', '160')))}"></div>
      <div><label>{h(t(messages, 'field.effective_from'))}</label><input name="effective_from" type="date" value="{h(profile.get('effective_from', date.today().isoformat()))}"></div>
      <div><label>{h(t(messages, 'field.effective_to'))}</label><input name="effective_to" type="date" value="{h(profile.get('effective_to', ''))}"></div>
      <div><label>{h(t(messages, 'field.termination_date'))}</label><input name="termination_date" type="date" value="{h(profile.get('termination_date', ''))}"></div>
      <input type="hidden" name="status" value="{h(salary_profile_status(profile))}">
    </div>
    <h3 style="margin-top: 18px;">{h(t(messages, 'tax_reference.title'))}</h3>
    <p class="message-strip message-warning">{h(t(messages, 'tax_reference.disclaimer'))}</p>
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.tax_reference_mode'))}</label><select name="tax_reference_mode">{tax_mode_options}</select></div>
      <div><label>{h(t(messages, 'field.tax_reference_city'))}</label><input name="tax_reference_city" value="{h(profile.get('tax_reference_city', 'Tokyo'))}" placeholder="Tokyo / Shanghai"></div>
      <div><label>{h(t(messages, 'field.jp_dependent_count'))}</label><input name="jp_dependent_count" type="number" min="0" step="1" value="{h(plain_amount(profile.get('jp_dependent_count', '0')))}"></div>
      <div><label>{h(t(messages, 'field.jp_monthly_health_insurance'))}</label><input name="jp_monthly_health_insurance" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('jp_monthly_health_insurance', '0')))}"></div>
      <div><label>{h(t(messages, 'field.jp_monthly_pension'))}</label><input name="jp_monthly_pension" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('jp_monthly_pension', '0')))}"></div>
      <div><label>{h(t(messages, 'field.jp_monthly_employment_insurance'))}</label><input name="jp_monthly_employment_insurance" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('jp_monthly_employment_insurance', '0')))}"></div>
      <div><label>{h(t(messages, 'field.jp_fixed_resident_tax_monthly'))}</label><input name="jp_fixed_resident_tax_monthly" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('jp_fixed_resident_tax_monthly', '0')))}"></div>
      <div><label>{h(t(messages, 'field.cn_monthly_social_insurance'))}</label><input name="cn_monthly_social_insurance" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('cn_monthly_social_insurance', '0')))}"></div>
      <div><label>{h(t(messages, 'field.cn_monthly_housing_fund'))}</label><input name="cn_monthly_housing_fund" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('cn_monthly_housing_fund', '0')))}"></div>
      <div><label>{h(t(messages, 'field.cn_monthly_special_additional_deductions'))}</label><input name="cn_monthly_special_additional_deductions" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('cn_monthly_special_additional_deductions', '0')))}"></div>
      <div><label>{h(t(messages, 'field.cn_monthly_other_deductions'))}</label><input name="cn_monthly_other_deductions" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('cn_monthly_other_deductions', '0')))}"></div>
      <div><label>{h(t(messages, 'field.cn_iit_cumulative_months_default'))}</label><input name="cn_iit_cumulative_months_default" type="number" min="0" step="1" value="{h(plain_amount(profile.get('cn_iit_cumulative_months_default', '0')))}"></div>
      <div><label>{h(t(messages, 'field.sg_cpf_employee'))}</label><input name="sg_cpf_employee" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('sg_cpf_employee', '0')))}"></div>
      <div><label>{h(t(messages, 'field.sg_cpf_employer'))}</label><input name="sg_cpf_employer" type="number" min="0" step="0.01" value="{h(plain_amount(profile.get('sg_cpf_employer', '0')))}"></div>
      <div><label>{h(t(messages, 'field.tax_reference_notes'))}</label><input name="tax_reference_notes" value="{h(profile.get('tax_reference_notes', ''))}" placeholder="HR notes"></div>
    </div>
    <div class="sap-toolbar">{portal_return_button_html(context)}<a class="button secondary" href="{h(url_with_lang('/salary-profiles', lang))}">{h(t(messages, 'nav.salary_profiles'))}</a><button type="submit">{h(t(messages, submit_key))}</button></div>
  </form>
<script>
(function() {{
  var select = document.getElementById('employee-source-select');
  if (!select) return;
  select.addEventListener('change', function() {{
    var option = select.options[select.selectedIndex];
    if (!option) return;
    [['profile-employee-no', 'number'], ['profile-employee-name', 'name'], ['profile-entity', 'entity'], ['profile-country', 'country']].forEach(function(item) {{
      var el = document.getElementById(item[0]);
      var value = option.getAttribute('data-' + item[1]) || '';
      if (el && value) el.value = value;
    }});
  }});
}})();
</script>
"""


def salary_profile_edit_html(profile: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    profile_id = str(profile.get("profile_id", ""))
    current_status = salary_profile_status(profile)
    next_version = dict(profile)
    next_version["effective_from"] = date.today().isoformat()
    next_version["effective_to"] = ""
    next_version["status"] = "active"
    lifecycle_notice = ""
    if current_status != "active":
        lifecycle_notice = f"<p class='message-strip message-info'>{h(t(messages, 'salary_profiles.non_active_notice'))}</p>"
    if current_status == "active":
        deactivate_html = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.deactivate_title'))}</h3>
  <p class="message-strip message-warning">{h(t(messages, 'salary_profiles.deactivate_desc'))}</p>
  <form method="post" action="{h(url_with_lang(f'/salary-profiles/{quote(profile_id)}/deactivate', lang))}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.deactivation_reason'))}</label><input name="deactivation_reason" required placeholder="No longer used / replaced by new profile"></div>
      <div><label>{h(t(messages, 'salary_profiles.deactivate_confirm'))}</label><select name="confirm_deactivate" required>{option_html('', '--')}{option_html('yes', t(messages, 'status.active'))}</select></div>
    </div>
    <div class="sap-toolbar"><button class="danger" type="submit">{h(t(messages, 'action.deactivate_profile'))}</button></div>
  </form>
</section>
"""
    else:
        deactivate_html = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.deactivate_title'))}</h3>
  <p class="message-strip message-info">{h(t(messages, 'salary_profiles.inactive_notice'))}</p>
</section>
"""
    if current_status != "voided":
        void_html = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.void_title'))}</h3>
  <p class="message-strip message-warning">{h(t(messages, 'salary_profiles.void_desc'))}</p>
  <form method="post" action="{h(url_with_lang(f'/salary-profiles/{quote(profile_id)}/void', lang))}">
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.void_reason'))}</label><input name="void_reason" required placeholder="Created for wrong employee / duplicate setup / input error"></div>
      <div><label>{h(t(messages, 'salary_profiles.void_confirm'))}</label><select name="confirm_void" required>{option_html('', '--')}{option_html('yes', t(messages, 'status.active'))}</select></div>
    </div>
    <div class="sap-toolbar"><button class="danger" type="submit">{h(t(messages, 'action.void_created_in_error'))}</button></div>
  </form>
</section>
"""
    else:
        void_html = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.void_title'))}</h3>
  <p class="message-strip message-info">{h(t(messages, 'salary_profiles.voided_notice'))}</p>
</section>
"""
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'salary_profiles.edit_title'))}: {h(salary_profile_label(profile))}</h2>
  <p>{salary_profile_status_badge(current_status, messages)}</p>
  <p class="message-strip message-warning">{h(t(messages, 'salary_profiles.edit_desc'))}</p>
  {lifecycle_notice}
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.edit_current_title'))}</h3>
  {salary_profile_form_html(profile, context, f'/salary-profiles/{quote(profile_id)}/edit', 'action.save_profile')}
</section>
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.new_version_title'))}</h3>
  <p class="message-strip message-info">{h(t(messages, 'salary_profiles.new_version_desc'))}</p>
  {salary_profile_form_html(next_version, context, f'/salary-profiles/{quote(profile_id)}/version', 'action.create_new_version')}
</section>
{deactivate_html}
{void_html}
"""

def salary_profile_filter_options(status_filter: str, lang: str, messages: dict[str, str]) -> str:
    filters = [
        ("active", "salary_profiles.active_view"),
        ("inactive", "salary_profiles.inactive_view"),
        ("voided", "salary_profiles.voided_view"),
        ("all", "salary_profiles.all_history_view"),
    ]
    links = []
    for value, key in filters:
        class_name = "pill" if value == status_filter else "button secondary"
        links.append(f'<a class="{class_name}" href="{h(url_with_lang("/salary-profiles", lang, {"status": value}))}">{h(t(messages, key))}</a>')
    return "".join(links)


def filtered_salary_profiles(profiles: list[dict[str, Any]], status_filter: str) -> list[dict[str, Any]]:
    if status_filter == "all":
        return profiles
    if status_filter not in {"active", "inactive", "voided"}:
        status_filter = "active"
    return [profile for profile in profiles if salary_profile_status(profile) == status_filter]


def salary_profiles_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    status_filter = str((context or {}).get("salary_profile_status_filter", "active")).strip().lower() or "active"
    if status_filter not in {"active", "inactive", "voided", "all"}:
        status_filter = "active"
    all_profiles = load_salary_profiles()
    profiles = filtered_salary_profiles(all_profiles, status_filter)
    eligible_employees = eligible_employeeadmin_payroll_employees(context)
    active_count = len(active_salary_profiles(all_profiles))
    rows = []
    for profile in profiles:
        rule = find_payroll_rule(str(profile.get("payroll_rule_id", "")))
        profile_id = str(profile.get("profile_id", ""))
        edit_url = url_with_lang(f"/salary-profiles/{quote(profile_id)}/edit", lang)
        profile_status = salary_profile_status(profile)
        rows.append(f"""
        <tr>
          <td>{h(profile.get('employee_no', ''))}</td>
          <td>{h(profile.get('employee_name', ''))}</td>
          <td>{h(profile.get('employee_external_id', ''))}</td>
          <td>{h(profile.get('entity', ''))}</td>
          <td>{h(profile.get('country', ''))}</td>
          <td>{h(profile.get('currency', ''))}</td>
          <td>{h(payroll_scheme_label(profile.get('payroll_scheme', '')))}</td>
          <td>{h(payroll_rule_label(rule) if rule else profile.get('payroll_rule_code', ''))}</td>
          <td>{h(rounding_policy_label(profile.get('rounding_policy', (rule or {}).get('rounding_policy', 'round_to_yen'))))}</td>
          <td class="num">{money_with_currency(profile.get('monthly_salary', 0), profile.get('currency', ''))}</td>
          <td class="num">{money_with_currency(profile.get('daily_rate', 0), profile.get('currency', ''))}</td>
          <td class="num">{money_with_currency(profile.get('hourly_rate', 0), profile.get('currency', ''))}</td>
          <td class="num">{h(profile.get('standard_monthly_hours', ''))}</td>
          <td>{h(profile.get('effective_from', ''))}</td>
          <td>{h(profile.get('effective_to', ''))}</td>
          <td>{salary_profile_status_badge(profile_status, messages)}</td>
          <td><a class="button secondary" href="{h(edit_url)}">{h(t(messages, 'action.modify_profile'))}</a></td>
        </tr>
        """)
    empty = f"<tr><td colspan='17' class='muted'>{h(t(messages, 'salary_profiles.empty'))}</td></tr>" if not rows else ""
    history_notice = "" if status_filter == "active" else f"<p class='message-strip message-warning'>{h(t(messages, 'salary_profiles.history_notice'))}</p>"
    create_section = ""
    if status_filter == "active":
        create_section = f"""
<section class="sap-section">
  <h3>{h(t(messages, 'salary_profiles.new_title'))}</h3>
  {salary_profile_form_html(None, context, '/salary-profiles', 'action.save_profile', include_employee_picker=True)}
</section>
"""
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'salary_profiles.title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'salary_profiles.desc'))}</p>
  <div class="sap-object-meta"><span class="status-badge status-active">{active_count} {h(t(messages, 'salary_profiles.active_count'))}</span><span class="status-badge">{len(all_profiles)} {h(t(messages, 'salary_profiles.count'))}</span><span class="status-badge status-active">{len(eligible_employees)} {h(t(messages, 'salary_profiles.eligible_count_badge'))}</span></div>
  <div class="actions">{salary_profile_filter_options(status_filter, lang, messages)}</div>
</section>
{employee_master_dependency_html(context)}
{history_notice}
{create_section}
<section class="panel wide" style="margin-top: 18px;">
  <table>
    <thead><tr><th>{h(t(messages, 'field.employee_no'))}</th><th>{h(t(messages, 'field.employee_name'))}</th><th>{h(t(messages, 'field.employee_external_id'))}</th><th>{h(t(messages, 'field.entity'))}</th><th>{h(t(messages, 'field.country'))}</th><th>{h(t(messages, 'field.currency'))}</th><th>{h(t(messages, 'field.payroll_scheme'))}</th><th>{h(t(messages, 'nav.payroll_rules'))}</th><th>{h(t(messages, 'field.rounding_policy'))}</th><th class="num">{h(t(messages, 'field.monthly_salary'))}</th><th class="num">{h(t(messages, 'field.daily_rate'))}</th><th class="num">{h(t(messages, 'field.hourly_rate'))}</th><th class="num">{h(t(messages, 'field.standard_monthly_hours'))}</th><th>{h(t(messages, 'field.effective_from'))}</th><th>{h(t(messages, 'field.effective_to'))}</th><th>{h(t(messages, 'field.status'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
    <tbody>{empty if empty else ''.join(rows)}</tbody>
  </table>
</section>
"""


def profile_form_values_from_record(record: dict[str, Any] | None) -> dict[str, str]:
    values = {
        "profile_id": "",
        "payroll_month": "",
        "attendance_days": "0",
        "monthly_working_days": "20",
        "attendance_hours": "0",
        "profile_additional_payment": "0",
        "profile_additional_deduction": "0",
        "confirmed_income_tax": "0",
        "jp_dependent_count_override": "",
        "jp_monthly_social_insurance_override": "",
        "jp_resident_tax_monthly": "",
        "cn_cumulative_months": "",
        "cn_prior_ytd_income": "0",
        "cn_prior_ytd_social_insurance": "0",
        "cn_prior_ytd_housing_fund": "0",
        "cn_prior_ytd_special_additional_deductions": "0",
        "cn_prior_ytd_other_deductions": "0",
        "cn_prior_ytd_tax_withheld": "0",
    }
    if not record:
        return values
    values["profile_id"] = str(record.get("profile_id", ""))
    values["payroll_month"] = str(record.get("payroll_month") or record.get("Payroll Month (給与月)", ""))
    values["attendance_days"] = plain_amount(record.get("attendance_days", "0"))
    values["monthly_working_days"] = plain_amount(record.get("monthly_working_days", "20"))
    values["attendance_hours"] = plain_amount(record.get("attendance_hours", "0"))
    values["profile_additional_payment"] = plain_amount(record.get("additional_payment", record.get("Additional Payment (追加支給)", "0")))
    values["profile_additional_deduction"] = plain_amount(record.get("additional_deduction", record.get("Additional Deduction (追加控除)", "0")))
    values["confirmed_income_tax"] = plain_amount(record.get("confirmed_income_tax", "0"))
    values["jp_resident_tax_monthly"] = plain_amount(record.get("confirmed_resident_tax", "0"))
    values["cn_cumulative_months"] = plain_amount(record.get("tax_reference_basis", {}).get("cumulative_months", "0") if isinstance(record.get("tax_reference_basis"), dict) else "0")
    return values


def profile_payroll_record_from_form(form: dict[str, str], messages: dict[str, str] | None = None) -> dict[str, Any]:
    profile_id = form.get("profile_id", "").strip()
    if not profile_id:
        raise ValueError(t(messages, "error.profile_required"))
    profile = find_salary_profile(profile_id)
    if not profile:
        raise ValueError(t(messages, "error.profile_required"))
    if str(profile.get("status", "active")).lower() != "active":
        raise ValueError(t(messages, "error.inactive_profile_not_allowed", "Inactive salary profiles cannot be used for new payroll calculations."))
    input_data = {
        "payroll_month": form.get("payroll_month", "").strip(),
        "attendance_days": parse_decimal(form.get("attendance_days", "0")),
        "monthly_working_days": parse_decimal(form.get("monthly_working_days", "") or profile.get("standard_monthly_working_days", "20")),
        "attendance_hours": parse_decimal(form.get("attendance_hours", "0")),
        "additional_payment": parse_decimal(form.get("profile_additional_payment", form.get("additional_payment", "0"))),
        "additional_deduction": parse_decimal(form.get("profile_additional_deduction", form.get("additional_deduction", "0"))),
        "confirmed_income_tax": parse_decimal(form.get("confirmed_income_tax", "0")),
        "apply_tax_reference_to_income_tax": form.get("apply_tax_reference_to_income_tax", ""),
        "jp_dependent_count_override": form.get("jp_dependent_count_override", "").strip(),
        "jp_monthly_social_insurance_override": form.get("jp_monthly_social_insurance_override", "").strip(),
        "jp_resident_tax_monthly": form.get("jp_resident_tax_monthly", "").strip(),
        "cn_cumulative_months": form.get("cn_cumulative_months", "").strip(),
        "cn_prior_ytd_income": parse_decimal(form.get("cn_prior_ytd_income", "0")),
        "cn_prior_ytd_social_insurance": parse_decimal(form.get("cn_prior_ytd_social_insurance", "0")),
        "cn_prior_ytd_housing_fund": parse_decimal(form.get("cn_prior_ytd_housing_fund", "0")),
        "cn_prior_ytd_special_additional_deductions": parse_decimal(form.get("cn_prior_ytd_special_additional_deductions", "0")),
        "cn_prior_ytd_other_deductions": parse_decimal(form.get("cn_prior_ytd_other_deductions", "0")),
        "cn_prior_ytd_tax_withheld": parse_decimal(form.get("cn_prior_ytd_tax_withheld", "0")),
    }
    return calculate_universal_payroll(profile, input_data, messages)


def validate_payroll_month(value: str, messages: dict[str, str] | None = None) -> str:
    cleaned = value.strip()
    try:
        year_text, month_text = cleaned.split("-", 1)
        year = int(year_text)
        month = int(month_text)
        if month < 1 or month > 12:
            raise ValueError
    except ValueError as exc:
        raise ValueError(t(messages, "error.invalid_payroll_month")) from exc
    return f"{year:04d}-{month:02d}"


def month_period(payroll_month: str, messages: dict[str, str] | None = None) -> tuple[str, str]:
    normalized = validate_payroll_month(payroll_month, messages)
    year, month = [int(part) for part in normalized.split("-")]
    last_day = monthrange(year, month)[1]
    return f"{year:04d}-{month:02d}-01", f"{year:04d}-{month:02d}-{last_day:02d}"


def parse_iso_date(value: Any) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    return date.fromisoformat(text)


def require_nonnegative(value: Decimal, field: str, messages: dict[str, str] | None = None) -> None:
    if value < 0:
        raise ValueError(t(messages, "error.negative_not_allowed", "Negative values are not allowed.") + f" ({field})")


def validate_not_after_termination(profile: dict[str, Any], period_start: str, period_end: str, messages: dict[str, str] | None = None) -> list[str]:
    termination = parse_iso_date(profile.get("termination_date", ""))
    if not termination:
        return []
    start = parse_iso_date(period_start)
    end = parse_iso_date(period_end)
    if start and termination < start:
        raise ValueError(t(messages, "error.after_termination"))
    if start and end and start <= termination <= end:
        return [t(messages, "message.mid_month_termination_note")]
    return []


def calculate_prorated_monthly(monthly_salary: Decimal, attendance_days: Decimal, working_days: Decimal, messages: dict[str, str] | None = None) -> Decimal:
    if working_days <= 0:
        raise ValueError(t(messages, "error.working_days_required"))
    return monthly_salary * attendance_days / working_days


def round_payroll_amount(value: Decimal, policy: str = "round_to_yen") -> Decimal:
    if policy == "floor_to_yen":
        return value.to_integral_value(rounding=ROUND_FLOOR)
    if policy == "ceil_to_yen":
        return value.to_integral_value(rounding=ROUND_CEILING)
    return value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def calculate_universal_payroll(profile: dict[str, Any], input_data: dict[str, Any], messages: dict[str, str] | None = None) -> dict[str, Any]:
    scheme = str(profile.get("payroll_scheme", ""))
    if scheme not in PAYROLL_SCHEMES:
        raise ValueError(t(messages, "error.invalid_payroll_scheme"))
    payroll_rule = find_payroll_rule(str(profile.get("payroll_rule_id", "")))
    calculation_type = str((payroll_rule or {}).get("calculation_type") or profile.get("payroll_calculation_type") or "")
    payroll_month_value = validate_payroll_month(str(input_data.get("payroll_month", "")), messages)
    period_start, period_end = month_period(payroll_month_value, messages)
    notes = validate_not_after_termination(profile, period_start, period_end, messages)

    monthly_salary = parse_decimal(profile.get("monthly_salary", "0"))
    daily_rate = parse_decimal(profile.get("daily_rate", "0"))
    hourly_rate = parse_decimal(profile.get("hourly_rate", "0"))
    standard_monthly_hours = parse_decimal(profile.get("standard_monthly_hours", "160"))
    attendance_days = parse_decimal(input_data.get("attendance_days", "0"))
    monthly_working_days = parse_decimal(input_data.get("monthly_working_days", profile.get("standard_monthly_working_days", "20")))
    attendance_hours = parse_decimal(input_data.get("attendance_hours", "0"))
    additional_payment = parse_decimal(input_data.get("additional_payment", "0"))
    additional_deduction = parse_decimal(input_data.get("additional_deduction", "0"))

    for field, value in {
        "monthly_salary": monthly_salary,
        "daily_rate": daily_rate,
        "hourly_rate": hourly_rate,
        "standard_monthly_hours": standard_monthly_hours,
        "attendance_days": attendance_days,
        "monthly_working_days": monthly_working_days,
        "attendance_hours": attendance_hours,
        "additional_payment": additional_payment,
        "additional_deduction": additional_deduction,
    }.items():
        require_nonnegative(value, field, messages)

    if not calculation_type:
        if scheme in {"jp_simple", "cn_consultant_monthly"}:
            calculation_type = "monthly_fixed"
        elif scheme in {"jp_monthly_prorated", "cn_dispatch_monthly_prorated", "sg_monthly_prorated"}:
            calculation_type = "monthly_prorated_by_attendance_days"
        elif scheme in {"jp_daily_consultant", "cn_contractor_daily"}:
            calculation_type = "daily_rate_by_attendance_days"
        elif scheme in {"jp_hourly", "jp_hourly_consultant", "cn_contractor_hourly"}:
            calculation_type = "hourly_rate_by_attendance_hours"
        elif scheme == "jp_consultant_hourly_base_prorated":
            calculation_type = "hourly_plus_base_prorated_by_standard_hours"
    rule_params = (payroll_rule or {}).get("parameters") if isinstance((payroll_rule or {}).get("parameters"), dict) else {}
    rounding_policy = str((payroll_rule or {}).get("rounding_policy") or profile.get("rounding_policy") or "round_to_yen")
    base_component_pay = Decimal("0")
    if calculation_type == "monthly_fixed":
        base_pay = monthly_salary
        base_component_pay = monthly_salary
    elif calculation_type == "monthly_prorated_by_attendance_days":
        base_pay = calculate_prorated_monthly(monthly_salary, attendance_days, monthly_working_days, messages)
        base_component_pay = base_pay
    elif calculation_type == "daily_rate_by_attendance_days":
        base_pay = daily_rate * attendance_days
        base_component_pay = base_pay
    elif calculation_type == "hourly_rate_by_attendance_hours":
        base_pay = hourly_rate * attendance_hours
    elif calculation_type == "hourly_plus_base_prorated_by_standard_hours":
        standard_hours = parse_decimal(rule_params.get("standard_hours", standard_monthly_hours) or standard_monthly_hours)
        if standard_hours <= 0:
            raise ValueError(t(messages, "error.standard_hours_required", "Standard monthly hours must be greater than zero."))
        base_hours = min(attendance_hours, standard_hours) if truthy(rule_params.get("cap_base_hours", "true")) else attendance_hours
        hourly_component = hourly_rate * attendance_hours
        base_component_pay = monthly_salary * base_hours / standard_hours
        base_pay = hourly_component + base_component_pay
    else:
        raise ValueError(t(messages, "error.invalid_calculation_type", "Invalid calculation type."))

    base_pay = round_payroll_amount(base_pay, rounding_policy)
    base_component_pay = round_payroll_amount(base_component_pay, rounding_policy)
    gross_pay = round_payroll_amount(base_pay + additional_payment, rounding_policy)
    tax_reference = calculate_reference_tax(profile, input_data, gross_pay, payroll_month_value, messages)
    estimated_income_tax = parse_decimal(tax_reference.get("estimated_income_tax", "0")).quantize(Decimal("1"))
    estimated_resident_tax = parse_decimal(tax_reference.get("estimated_resident_tax", "0")).quantize(Decimal("1"))
    confirmed_income_tax = parse_decimal(input_data.get("confirmed_income_tax", "0")).quantize(Decimal("1"))
    if confirmed_income_tax == 0 and truthy(input_data.get("apply_tax_reference_to_income_tax")):
        confirmed_income_tax = estimated_income_tax
    confirmed_resident_tax = estimated_resident_tax
    country = str(profile.get("country", "")).strip().upper() or ("JP" if scheme.startswith("jp_") else "CN" if scheme.startswith("cn_") else "SG" if scheme.startswith("sg_") else "JP")
    jp_health_insurance = parse_decimal(profile.get("jp_monthly_health_insurance", "0")) if country == "JP" else Decimal("0")
    jp_pension = parse_decimal(profile.get("jp_monthly_pension", "0")) if country == "JP" else Decimal("0")
    jp_employment_insurance = parse_decimal(profile.get("jp_monthly_employment_insurance", "0")) if country == "JP" else Decimal("0")
    cn_social_insurance = parse_decimal(profile.get("cn_monthly_social_insurance", "0")) if country == "CN" else Decimal("0")
    cn_housing_fund = parse_decimal(profile.get("cn_monthly_housing_fund", "0")) if country == "CN" else Decimal("0")
    cn_special_additional_deductions = parse_decimal(profile.get("cn_monthly_special_additional_deductions", "0")) if country == "CN" else Decimal("0")
    cn_other_deductions = parse_decimal(profile.get("cn_monthly_other_deductions", "0")) if country == "CN" else Decimal("0")
    sg_cpf_employee = parse_decimal(profile.get("sg_cpf_employee", "0")) if country == "SG" else Decimal("0")
    sg_cpf_employer = parse_decimal(profile.get("sg_cpf_employer", "0")) if country == "SG" else Decimal("0")
    hourly_pay = (hourly_rate * attendance_hours).quantize(Decimal("1")) if attendance_hours and hourly_rate else Decimal("0")
    total_deduction = (
        additional_deduction
        + confirmed_income_tax
        + confirmed_resident_tax
        + jp_health_insurance
        + jp_pension
        + jp_employment_insurance
        + cn_social_insurance
        + cn_housing_fund
        + sg_cpf_employee
    ).quantize(Decimal("1"))
    net_pay = (gross_pay - total_deduction).quantize(Decimal("1"))
    record: dict[str, Any] = {
        "profile_id": profile.get("profile_id", ""),
        "employee_no": profile.get("employee_no", ""),
        "employee_name": profile.get("employee_name", ""),
        "entity": profile.get("entity", ""),
        "country": country,
        "work_location_country": profile.get("work_location_country", ""),
        "currency": profile.get("currency", ""),
        "payroll_scheme": scheme,
        "payroll_rule_id": profile.get("payroll_rule_id", ""),
        "payroll_rule_code": str((payroll_rule or {}).get("rule_code", profile.get("payroll_rule_code", ""))),
        "payroll_calculation_type": calculation_type,
        "rounding_policy": rounding_policy,
        "payroll_month": payroll_month_value,
        "period_start": period_start,
        "period_end": period_end,
        "monthly_salary": monthly_salary,
        "daily_rate": daily_rate,
        "hourly_rate": hourly_rate,
        "standard_monthly_hours": standard_monthly_hours,
        "attendance_days": attendance_days,
        "monthly_working_days": monthly_working_days,
        "attendance_hours": attendance_hours,
        "calculated_base_pay": base_pay,
        "base_component_pay": base_component_pay,
        "additional_payment": additional_payment,
        "additional_deduction": additional_deduction,
        "gross_pay": gross_pay,
        "total_deduction": total_deduction,
        "net_pay": net_pay,
        "jp_health_insurance": jp_health_insurance,
        "jp_pension": jp_pension,
        "jp_employment_insurance": jp_employment_insurance,
        "cn_social_insurance": cn_social_insurance,
        "cn_housing_fund": cn_housing_fund,
        "cn_special_additional_deductions": cn_special_additional_deductions,
        "cn_other_deductions": cn_other_deductions,
        "sg_cpf_employee": sg_cpf_employee,
        "sg_cpf_employer": sg_cpf_employer,
        "hourly_pay": hourly_pay,
        "tax_reference_mode": tax_reference.get("tax_reference_mode", "none"),
        "tax_reference_city": tax_reference.get("tax_reference_city", ""),
        "tax_reference_status": tax_reference.get("tax_reference_status", "not_applicable"),
        "tax_reference_review_required": tax_reference.get("tax_reference_review_required", False),
        "tax_reference_currency": profile.get("currency", ""),
        "estimated_income_tax": estimated_income_tax,
        "estimated_resident_tax": estimated_resident_tax,
        "confirmed_income_tax": confirmed_income_tax,
        "confirmed_resident_tax": confirmed_resident_tax,
        "taxable_income_reference": parse_decimal(tax_reference.get("taxable_income_reference", "0")),
        "tax_reference_basis": tax_reference.get("tax_reference_basis", {}),
        "tax_reference_warnings": tax_reference.get("tax_reference_warnings", []),
        "tax_reference_config_version": load_tax_reference_config().get("version", ""),
        "record_status": "active",
        "calculation_notes": [*notes, *tax_reference.get("tax_reference_warnings", [])],
    }
    apply_legacy_canonical_fields(record)
    return record


def apply_legacy_canonical_fields(record: dict[str, Any]) -> dict[str, Any]:
    record["Employee No. (社員No.)"] = record.get("employee_no", "")
    record["Employee Name (氏名)"] = record.get("employee_name", "")
    record["Payroll Month (給与月)"] = record.get("payroll_month", "")
    for label in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS]:
        record.setdefault(label, Decimal("0"))
    record["Base Salary (基本給)"] = parse_decimal(record.get("calculated_base_pay", "0"))
    record["Additional Payment (追加支給)"] = parse_decimal(record.get("additional_payment", "0"))
    record["Additional Deduction (追加控除)"] = parse_decimal(record.get("additional_deduction", "0"))
    record["Health Insurance (健康保険)"] = parse_decimal(record.get("jp_health_insurance", "0"))
    record["Pension (厚生年金)"] = parse_decimal(record.get("jp_pension", "0"))
    record["Employment Insurance (雇用保険)"] = parse_decimal(record.get("jp_employment_insurance", "0"))
    record["Income Tax (所得税)"] = parse_decimal(record.get("confirmed_income_tax", "0"))
    record["Gross Pay (総支給額)"] = parse_decimal(record.get("gross_pay", "0"))
    record["Total Deduction (控除合計)"] = parse_decimal(record.get("total_deduction", "0"))
    record["Net Pay (差引支給額)"] = parse_decimal(record.get("net_pay", "0"))
    return record


def payroll_input_html(record: dict[str, Any] | None = None, message: str = "", context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    values = form_values_from_record(record)
    profile_values = profile_form_values_from_record(record)
    employees = load_employeeadmin_employees(context)
    employee_number_options = "".join(f'<option value="{h(item.get("employee_number", ""))}">{h(item.get("employee_number", ""))} - {h(item.get("display_name", ""))}</option>' for item in employees)
    employee_name_options = "".join(f'<option value="{h(item.get("display_name", ""))}">{h(item.get("employee_number", ""))} - {h(item.get("display_name", ""))}</option>' for item in employees)
    manual_country_options = "".join(option_html(value, t(messages, f"country.{value.lower()}", value), values.get("country", "JP")) for value in COUNTRY_OPTIONS)
    manual_currency_options = "".join(option_html(value, value, values.get("currency", "JPY")) for value in CURRENCY_OPTIONS)
    source_message_key = "integration.employeeadmin_available" if employees else "integration.employeeadmin_unavailable"
    source_message_class = "message-success" if employees else "message-warning"
    manual_fields = "".join(
        f"""
        <div>
          <label>{h(field_label(messages, canonical))}</label>
          <input name="{h(key)}" type="number" min="0" step="1" value="{h(values.get(key, '0'))}">
        </div>
        """
        for key, canonical in AMOUNT_INPUTS
    )
    progress = payroll_progress_html(message, bool(record), context)
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'payroll.input_title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'payroll.input_desc'))}</p>
  <p class="message-strip {source_message_class}">{h(t(messages, source_message_key)).format(count=len(employees))}</p>
  <div class="sap-object-meta">
    {status_badge('Ready for HR confirmation' if record else 'Waiting for input', context)}
    {status_badge('External source', context)}
  </div>
  <div class="actions">
    <a class="button secondary" href="{h(url_with_lang('/salary-profiles', lang))}">{h(t(messages, 'nav.salary_profiles'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payroll-input', lang, {'source': 'sample'}))}">{h(t(messages, 'action.fill_sample'))}</a>
    <a class="button ghost" href="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.clear_form'))}</a>
    {portal_return_button_html(context)}
  </div>
</section>
{employee_master_dependency_html(context)}
{progress}
<section class="sap-section" style="margin-top: 18px;">
  <h3>{h(t(messages, 'payroll.profile_title'))}</h3>
  <p class="muted">{h(t(messages, 'payroll.profile_desc'))}</p>
  <form method="post" action="{h(url_with_lang('/payroll-confirm', lang))}">
    <input type="hidden" name="mode" value="profile">
    <div class="form-grid">
      <div><label>{h(t(messages, 'nav.salary_profiles'))}</label><select name="profile_id" required>{profile_select_options(profile_values.get('profile_id', ''))}</select></div>
      <div><label>{h(t(messages, 'field.payroll_month'))}</label><input name="payroll_month" required placeholder="2026-06" value="{h(profile_values.get('payroll_month', ''))}"></div>
      <div><label>{h(t(messages, 'field.attendance_days'))}</label><input name="attendance_days" type="number" min="0" step="0.01" value="{h(profile_values.get('attendance_days', '0'))}"></div>
      <div><label>{h(t(messages, 'field.monthly_working_days'))}</label><input name="monthly_working_days" type="number" min="0" step="0.01" value="{h(profile_values.get('monthly_working_days', '20'))}"></div>
      <div><label>{h(t(messages, 'field.attendance_hours'))}</label><input name="attendance_hours" type="number" min="0" step="0.01" value="{h(profile_values.get('attendance_hours', '0'))}"></div>
      <div><label>{h(t(messages, 'field.additional_payment'))}</label><input name="profile_additional_payment" type="number" min="0" step="0.01" value="{h(profile_values.get('profile_additional_payment', '0'))}"></div>
      <div><label>{h(t(messages, 'field.additional_deduction'))}</label><input name="profile_additional_deduction" type="number" min="0" step="0.01" value="{h(profile_values.get('profile_additional_deduction', '0'))}"></div>
    </div>
    <h3 style="margin-top: 18px;">{h(t(messages, 'tax_reference.title'))}</h3>
    <p class="message-strip message-warning">{h(t(messages, 'tax_reference.disclaimer'))}</p>
    <div class="form-grid">
      <div><label>{h(t(messages, 'field.confirmed_income_tax'))}</label><input name="confirmed_income_tax" type="number" min="0" step="0.01" value="{h(profile_values.get('confirmed_income_tax', '0'))}"></div>
      <div><label>{h(t(messages, 'action.apply_tax_reference'))}</label><select name="apply_tax_reference_to_income_tax">{option_html('', t(messages, 'status.inactive'))}{option_html('on', t(messages, 'status.active'))}</select></div>
      <div><label>{h(t(messages, 'field.jp_dependent_count'))}</label><input name="jp_dependent_count_override" type="number" min="0" step="1" value="{h(profile_values.get('jp_dependent_count_override', ''))}"></div>
      <div><label>{h(t(messages, 'field.jp_monthly_social_insurance_override'))}</label><input name="jp_monthly_social_insurance_override" type="number" min="0" step="0.01" value="{h(profile_values.get('jp_monthly_social_insurance_override', ''))}"></div>
      <div><label>{h(t(messages, 'field.jp_resident_tax_monthly'))}</label><input name="jp_resident_tax_monthly" type="number" min="0" step="0.01" value="{h(profile_values.get('jp_resident_tax_monthly', ''))}"></div>
      <div><label>{h(t(messages, 'field.cn_cumulative_months'))}</label><input name="cn_cumulative_months" type="number" min="0" step="1" value="{h(profile_values.get('cn_cumulative_months', ''))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_income'))}</label><input name="cn_prior_ytd_income" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_income', '0'))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_social_insurance'))}</label><input name="cn_prior_ytd_social_insurance" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_social_insurance', '0'))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_housing_fund'))}</label><input name="cn_prior_ytd_housing_fund" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_housing_fund', '0'))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_special_additional_deductions'))}</label><input name="cn_prior_ytd_special_additional_deductions" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_special_additional_deductions', '0'))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_other_deductions'))}</label><input name="cn_prior_ytd_other_deductions" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_other_deductions', '0'))}"></div>
      <div><label>{h(t(messages, 'field.cn_prior_ytd_tax_withheld'))}</label><input name="cn_prior_ytd_tax_withheld" type="number" min="0" step="0.01" value="{h(profile_values.get('cn_prior_ytd_tax_withheld', '0'))}"></div>
    </div>
    <div class="sap-toolbar">
      <button class="secondary" type="submit" formaction="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.recalculate'))}</button>
      <button type="submit">{h(t(messages, 'action.confirm_save'))}</button>
    </div>
  </form>
</section>
<section class="grid" style="margin-top: 18px; align-items: start;">
  <section class="sap-section">
    <h3>{h(t(messages, 'payroll.manual_title'))}</h3>
    <p class="muted">{h(t(messages, 'payroll.manual_desc'))}</p>
    <form method="post" action="{h(url_with_lang('/payroll-confirm', lang))}">
      <datalist id="employee-number-options">{employee_number_options}</datalist>
      <datalist id="employee-name-options">{employee_name_options}</datalist>
      <div class="form-grid">
        <div><label>{h(t(messages, 'field.employee_no'))}</label><input name="employee_no" list="employee-number-options" required placeholder="E001" value="{h(values.get('employee_no', ''))}"></div>
        <div><label>{h(t(messages, 'field.employee_name'))}</label><input name="employee_name" list="employee-name-options" required placeholder="Yamada Taro" value="{h(values.get('employee_name', ''))}"></div>
        <div><label>{h(t(messages, 'field.payroll_month'))}</label><input name="payroll_month" required placeholder="2026-06" value="{h(values.get('payroll_month', ''))}"></div>
        <div><label>{h(t(messages, 'field.country'))}</label><select name="country">{manual_country_options}</select></div>
        <div><label>{h(t(messages, 'field.currency'))}</label><select name="currency">{manual_currency_options}</select></div>
        {manual_fields}
      </div>
      <div class="sap-toolbar">
        <a class="button ghost" href="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.clear'))}</a>
        <button class="secondary" type="submit" formaction="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.recalculate'))}</button>
        <button type="submit">{h(t(messages, 'action.confirm_save'))}</button>
      </div>
    </form>
  </section>
  <section class="sap-section">
    <h3>{h(t(messages, 'payroll.excel_title'))}</h3>
    <p class="muted">{h(t(messages, 'payroll.excel_desc'))}</p>
    <form method="post" action="{h(url_with_lang('/payroll-input', lang))}" enctype="multipart/form-data">
      <input type="hidden" name="mode" value="upload">
      <label>{h(t(messages, 'field.payroll_excel_file'))}</label>
      <input type="file" name="payroll_file" accept=".xlsx" required>
      <div class="actions"><button type="submit">{h(t(messages, 'action.import_excel'))}</button></div>
    </form>
    <ol class="muted">
      <li>{h(t(messages, 'payroll.step_choose_excel'))}</li>
      <li>{h(t(messages, 'payroll.step_parse'))}</li>
      <li>{h(t(messages, 'payroll.step_check'))}</li>
      <li>{h(t(messages, 'payroll.step_confirm'))}</li>
    </ol>
  </section>
</section>
{payroll_form_preview(record, context) if record else ''}
"""


def payroll_progress_html(message: str, has_record: bool, context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    if not message and not has_record:
        message = t(messages, "message.default_progress")
    status = "Ready for HR confirmation" if has_record else "Waiting for input"
    return f"""
<section class="sap-section" style="margin-top: 18px;">
  <h3>{h(t(messages, 'payroll.progress_title'))}</h3>
  <p>{status_badge(status, context)}</p>
  <p class="message-strip message-info">{h(message)}</p>
</section>
"""


def payroll_form_preview(record: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    currency = str(record.get("currency", ""))
    notes = record.get("calculation_notes", []) if isinstance(record.get("calculation_notes"), list) else []
    note_html = "".join(f"<p class='message-strip message-warning'>{h(note)}</p>" for note in notes)
    detail_html = ""
    if record.get("payroll_scheme"):
        detail_html = f"""
        <section class="sap-readonly-grid" style="margin-top: 16px;">
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.entity'))}</div><div class="value">{h(record.get('entity', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.country'))}</div><div class="value">{h(record.get('country', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.work_location_country'))}</div><div class="value">{h(record.get('work_location_country', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.payroll_scheme'))}</div><div class="value">{h(payroll_scheme_label(record.get('payroll_scheme', '')))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'nav.payroll_rules'))}</div><div class="value">{h(record.get('payroll_rule_code', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.calculation_type'))}</div><div class="value">{h(calculation_type_label(record.get('payroll_calculation_type', '')))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.attendance_days'))}</div><div class="value">{h(record.get('attendance_days', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.monthly_working_days'))}</div><div class="value">{h(record.get('monthly_working_days', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.attendance_hours'))}</div><div class="value">{h(record.get('attendance_hours', ''))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.calculated_base_pay'))}</div><div class="value">{h(money_with_currency(record.get('calculated_base_pay', 0), currency))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.base_component_pay'))}</div><div class="value">{h(money_with_currency(record.get('base_component_pay', 0), currency))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.estimated_income_tax'))}</div><div class="value">{h(money_with_currency(record.get('estimated_income_tax', 0), currency))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.confirmed_income_tax'))}</div><div class="value">{h(money_with_currency(record.get('confirmed_income_tax', 0), currency))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.estimated_resident_tax'))}</div><div class="value">{h(money_with_currency(record.get('estimated_resident_tax', 0), currency))}</div></div>
          <div class="sap-readonly-field"><div class="label">{h(t(messages, 'field.tax_reference_status'))}</div><div class="value">{h(record.get('tax_reference_status', ''))}</div></div>
        </section>
        """
    return f"""
<section class="panel" style="margin-top: 18px;">
  <h2>{h(t(messages, 'payroll.preview_title'))}</h2>
  <p class="muted">{h(t(messages, 'payroll.preview_desc'))}</p>
  {note_html}
  <section class="grid">
    <div class="card"><h3>{h(t(messages, 'field.gross_pay'))}</h3><div class="metric">{money_with_currency(record.get('Gross Pay (総支給額)', 0), currency)}</div></div>
    <div class="card"><h3>{h(t(messages, 'field.total_deduction'))}</h3><div class="metric">{money_with_currency(record.get('Total Deduction (控除合計)', 0), currency)}</div></div>
    <div class="card"><h3>{h(t(messages, 'field.net_pay'))}</h3><div class="metric">{money_with_currency(record.get('Net Pay (差引支給額)', 0), currency)}</div></div>
  </section>
  {detail_html}
</section>
"""


def form_values_from_record(record: dict[str, Any] | None) -> dict[str, str]:
    values = {key: "0" for key, _canonical in AMOUNT_INPUTS}
    values.update({"employee_no": "", "employee_name": "", "payroll_month": "", "country": "JP", "currency": "JPY"})
    if not record:
        return values
    values["employee_no"] = str(record.get("Employee No. (社員No.)", ""))
    values["employee_name"] = str(record.get("Employee Name (氏名)", ""))
    values["payroll_month"] = str(record.get("Payroll Month (給与月)", ""))
    values["country"] = payroll_record_country(record)
    values["currency"] = payroll_record_currency(record) or values["currency"]
    for key, canonical in AMOUNT_INPUTS:
        values[key] = plain_amount(record.get(canonical, Decimal("0")))
    return values



def operation_success_message(record_type: str, record_name: str, action: str, actor: str = "current_user", lang: str = "en") -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    if lang == "zh":
        return f"{record_type}记录 {record} 已于 {timestamp} 由 {actor} {action}成功。"
    if lang == "ja":
        return f"{record_type} レコード {record} は {timestamp} に {actor} により{action}されました。"
    return f"{record_type} record {record} {action} successfully at {timestamp} by {actor}."


def no_change_message(record_type: str, record_name: str, lang: str = "en") -> str:
    timestamp = datetime.now(timezone.utc).isoformat()
    record = record_name or "-"
    if lang == "zh":
        return f"{timestamp} 未检测到 {record_type}记录 {record} 的变更。未保存，也未生成审计记录。"
    if lang == "ja":
        return f"{timestamp} 時点で {record_type} レコード {record} に変更はありません。保存および監査記録の作成は行われませんでした。"
    return f"No changes detected for {record_type} record {record} at {timestamp}. Nothing was saved and no audit entry was created."


def payroll_record_label(record: dict[str, Any]) -> str:
    employee = str(record.get("Employee No. (社員No.)", "")).strip()
    month = str(record.get("Payroll Month (給与月)", "")).strip()
    return " / ".join(part for part in (employee, month) if part) or str(record.get("record_id", "")).strip()

def payroll_saved_html(record: dict[str, Any], context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(messages, 'payroll.saved_title'))}</h2>
  <p class="message-strip message-success">{h(operation_success_message('Payroll', payroll_record_label(record), 'saved', str((context or {}).get('user', {}).get('display_name') or (context or {}).get('user', {}).get('email') or 'current_user'), lang))}</p>
  <div class="sap-object-meta">{status_badge('Saved', context)}</div>
  <div class="grid">
    <div class="card"><h3>{h(t(messages, 'field.employee'))}</h3><p>{h(record.get('Employee No. (社員No.)', ''))} - {h(record.get('Employee Name (氏名)', ''))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.payroll_month'))}</h3><p>{h(record.get('Payroll Month (給与月)', ''))}</p></div>
    <div class="card"><h3>{h(t(messages, 'field.net_pay'))}</h3><p class="metric">{money(record.get('Net Pay (差引支給額)', 0))}</p></div>
  </div>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/payroll-register', lang))}">{h(t(messages, 'action.open_payroll_register'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payslips', lang))}">{h(t(messages, 'action.open_payslips'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.input_next_employee'))}</a>
    {portal_return_button_html(context)}
  </div>
</section>
"""


def status_message_html(message: str, context: dict[str, Any] | None = None) -> str:
    return f"<section class='message-strip message-success'>{h(message)}</section>"


def payroll_register_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    country_filter = normalize_country((context or {}).get("country_filter", "ALL"))
    month_filter = str((context or {}).get("month_filter", "")).strip()
    saved_records = load_saved_payroll_records()
    base_records = saved_records if saved_records else load_sample_payroll_records()
    records = filter_payroll_records(base_records, country_filter, month_filter)
    active_records = active_payroll_records(records)
    template = payroll_report_template(country_filter)
    report_lang = payroll_report_language(country_filter, lang)
    report_messages = load_i18n(report_lang)
    data_note = t(messages, "register.saved_note") if saved_records else t(messages, "register.sample_note")
    columns = template["columns"]
    header_cells = "".join(f"<th class='num'>{h(t(report_messages, col['label_key'], col['key']))}</th>" if col.get("amount") else f"<th>{h(t(report_messages, col['label_key'], col['key']))}</th>" for col in columns)
    header_cells += f"<th>{h(t(messages, 'field.action'))}</th>"
    rows_html = []
    for record in records:
        cells = []
        for col in columns:
            value = format_report_cell(record, col, for_csv=False)
            if col.get("amount"):
                cells.append(f"<td class='num'>{h(value)}</td>")
            elif col.get("key") == "record_status":
                cells.append(f"<td>{value}</td>")
            else:
                cells.append(f"<td>{h(value)}</td>")
        record_id = h(str(record.get("record_id", "")))
        if record_id and str(record.get("record_status", "active")) != "voided":
            cells.append(f"""<td><form method='post' action='{h(url_with_lang('/payroll-delete', lang))}'><input type='hidden' name='record_id' value='{record_id}'><button class='danger' type='submit'>{h(t(messages, 'action.void'))}</button></form></td>""")
        elif record_id:
            cells.append(f"<td>{status_badge('Voided', context)}</td>")
        else:
            cells.append(f"<td>{status_badge('Sample', context)}</td>")
        rows_html.append(f"<tr>{''.join(cells)}</tr>")
    total_cells = []
    first_total = True
    for col in columns:
        if col.get("amount"):
            total_cells.append(f"<td class='num'><strong>{money_with_currency(report_amount_total(active_records, str(col.get('key', ''))), '')}</strong></td>")
        elif first_total:
            total_cells.append(f"<td><strong>{h(t(messages, 'register.monthly_total'))}</strong></td>")
            first_total = False
        else:
            total_cells.append("<td></td>")
    total_cells.append("<td></td>")
    empty_note = f"<tr><td colspan='{len(columns) + 1}' class='muted'>{h(t(messages, 'register.empty'))}</td></tr>" if not records else ""
    csv_params = {"country": country_filter, "month": month_filter}
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payroll.area'))}</p>
  <h2>{h(t(report_messages, template.get('title_key', 'register.title'), t(messages, 'register.title')))}</h2>
  <p class="message-strip message-info">{h(data_note)} {h(t(messages, 'report.template_note'))}</p>
  <div class="sap-object-meta">{status_badge('Saved' if saved_records else 'Sample', context)}<span class="status-badge">{h(t(messages, f'country.{country_filter.lower()}', country_filter))}</span></div>
  {report_filter_html(context)}
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/payroll-input', lang))}">{h(t(messages, 'action.open_payroll_input'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/payroll-register/download', lang, csv_params))}">{h(t(messages, 'action.download_csv'))}</a>
    {portal_return_button_html(context)}
  </div>
</section>
{employee_master_dependency_html(context)}
<section class="panel wide">
  <table>
    <thead><tr>{header_cells}</tr></thead>
    <tbody>{empty_note if empty_note else ''.join(rows_html) + '<tr>' + ''.join(total_cells) + '</tr>'}</tbody>
  </table>
</section>
"""


def payslips_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    payslips = load_payslips()
    deliveries_by_payslip = latest_delivery_by_payslip(load_payslip_email_deliveries())
    rows = []
    for payslip in sorted(payslips, key=lambda item: str(item.get("generated_at", "")), reverse=True):
        payslip_id = str(payslip.get("payslip_id", ""))
        delivery = deliveries_by_payslip.get(payslip_id, {})
        delivery_id = str(delivery.get("delivery_id", ""))
        delivery_status = str(delivery.get("status") or payslip.get("delivery_status", "not_sent"))
        pdf_path = str(payslip.get("pdf_path", ""))
        download = ""
        if pdf_path:
            download = f'<a class="button secondary" href="{h(url_with_lang(f"/payslips/{quote(payslip_id)}/download", lang))}">{h(t(messages, "action.download_pdf"))}</a>'
        queue_form = ""
        if pdf_path and str(payslip.get("employee_email", "")).strip() and delivery_status not in {"queued", "sent"}:
            queue_form = f"""
            <form method="post" action="{h(url_with_lang('/payslips/select-for-email', lang))}" style="display:inline">
              <input type="hidden" name="payslip_id" value="{h(payslip_id)}">
              <button type="submit" class="success">{h(t(messages, 'action.queue_for_email'))}</button>
            </form>
            """
        send_form = ""
        if delivery_id and delivery_status in {"queued", "failed"}:
            action_key = "action.retry_payslip_email" if delivery_status == "failed" else "action.send_payslip_email"
            button_class = "warning" if delivery_status == "failed" else "success"
            send_form = f"""
            <form method="post" action="{h(url_with_lang('/payslips/send-email', lang))}" style="display:inline">
              <input type="hidden" name="delivery_id" value="{h(delivery_id)}">
              <button type="submit" class="{button_class}">{h(t(messages, action_key))}</button>
            </form>
            """
        rows.append(f"""
        <tr>
          <td>{h(payslip_id)}</td>
          <td>{h(str(payslip.get('employee_no', '')))}</td>
          <td>{h(str(payslip.get('employee_name', '')))}</td>
          <td>{h(str(payslip.get('payroll_month', '')))}</td>
          <td>{h(str(payslip.get('batch_id', '')))}</td>
          <td>{h(str(payslip.get('employee_email', '') or '-'))}</td>
          <td>{h(str(payslip.get('pdf_status', 'not_generated')))}</td>
          <td>{h(delivery_status)}</td>
          <td class="num">{h(str(delivery.get('attempt_count', 0) or 0))}</td>
          <td>{h(str(delivery.get('last_attempt_at', '') or '-'))}</td>
          <td>{h(str(delivery.get('error') or payslip.get('delivery_error') or '-'))}</td>
          <td>{download} {queue_form} {send_form}</td>
        </tr>
        """)
    empty_html = f"<tr><td colspan='12' class='muted'>{h(t(messages, 'payslips.empty'))}</td></tr>" if not rows else ""
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'payslips.area'))}</p>
  <h2>{h(t(messages, 'payslips.title'))}</h2>
  <p class="message-strip message-info">{h(t(messages, 'payslips.desc'))}</p>
  <p class="message-strip message-warning">{h(t(messages, 'payslips.email_send_note'))}</p>
  <div class="sap-object-meta">
    {status_badge('Saved', context)}
    <span class="status-badge">{len(payslips)} {h(t(messages, 'payslips.preview_count'))}</span>
  </div>
  <div class="actions">{portal_return_button_html(context)}</div>
</section>
<section class="panel wide">
  <table>
    <thead><tr><th>{h(t(messages, 'payslips.id'))}</th><th>{h(t(messages, 'field.employee_no'))}</th><th>{h(t(messages, 'field.employee_name'))}</th><th>{h(t(messages, 'field.payroll_month'))}</th><th>{h(t(messages, 'payroll_batch.detail_title'))}</th><th>{h(t(messages, 'field.email'))}</th><th>{h(t(messages, 'payslips.pdf_status'))}</th><th>{h(t(messages, 'payslips.delivery_status'))}</th><th class="num">{h(t(messages, 'payslips.delivery_attempts'))}</th><th>{h(t(messages, 'payslips.last_attempt_at'))}</th><th>{h(t(messages, 'payslips.delivery_error'))}</th><th>{h(t(messages, 'field.action'))}</th></tr></thead>
    <tbody>{empty_html if empty_html else ''.join(rows)}</tbody>
  </table>
</section>
"""


def audit_logs_html(context: dict[str, Any] | None = None) -> str:
    messages = context_messages(context)
    lang = context_lang(context)
    logs = load_audit_logs()
    rows = []
    for item in logs[:300]:
        rows.append(f"""
        <tr>
          <td>{h(item.get('timestamp', ''))}</td>
          <td>{h(item.get('module', ''))}</td>
          <td>{h(item.get('record_id', ''))}</td>
          <td>{h(item.get('action', ''))}</td>
          <td>{h(item.get('user', ''))}</td>
          <td><textarea readonly>{h(json.dumps(item.get('before_value'), ensure_ascii=False, indent=2))}</textarea></td>
          <td><textarea readonly>{h(json.dumps(item.get('after_value'), ensure_ascii=False, indent=2))}</textarea></td>
        </tr>
        """)
    empty = f"<tr><td colspan='7' class='muted'>{h(t(messages, 'audit.empty'))}</td></tr>" if not rows else ""
    return f"""
<section class="sap-page-header">
  <p class="muted">{h(t(messages, 'audit.area'))}</p>
  <h2>{h(t(messages, 'audit.title'))}</h2>
  <p class="message-strip message-warning">{h(t(messages, 'audit.desc'))}</p>
  <div class="actions">
    <a class="button secondary" href="{h(url_with_lang('/audit-logs/download', lang))}">{h(t(messages, 'action.download_audit_csv'))}</a>
    {portal_return_button_html(context)}
  </div>
</section>
<section class="panel wide">
  <table>
    <thead><tr><th>{h(t(messages, 'audit.time'))}</th><th>{h(t(messages, 'audit.module'))}</th><th>{h(t(messages, 'audit.record_id'))}</th><th>{h(t(messages, 'audit.event_type'))}</th><th>{h(t(messages, 'audit.performed_by'))}</th><th>{h(t(messages, 'audit.before_value'))}</th><th>{h(t(messages, 'audit.after_value'))}</th></tr></thead>
    <tbody>{empty if empty else ''.join(rows)}</tbody>
  </table>
</section>
"""


def employeeadmin_source_status(context: dict[str, Any] | None = None) -> dict[str, Any]:
    employees = load_employeeadmin_employees(context)
    if employees:
        return {"count": len(employees), "message_key": "integration.employeeadmin_available", "class": "message-success"}
    return {"count": 0, "message_key": "integration.employeeadmin_unavailable", "class": "message-warning"}


def load_employeeadmin_employees(context: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    session_id = str(context.get("session_id", "")) if context else ""
    if not session_id:
        return []
    request = Request(
        f"{EMPLOYEEADMIN_BASE_URL}/api/payroll/employees",
        headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=2) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return []
    employees = payload.get("employees") if isinstance(payload, dict) else None
    if not isinstance(employees, list):
        return []
    return [item for item in employees if isinstance(item, dict)]


def clear_legacy_session_cookie_header() -> str:
    return f"{LEGACY_SESSION_COOKIE_NAME}=; HttpOnly; Path=/; SameSite=Lax; Max-Age=0"


def load_payroll_records() -> list[dict[str, Any]]:
    saved = load_saved_payroll_records()
    if saved:
        return active_payroll_records(saved)
    return load_sample_payroll_records()


def active_payroll_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [record for record in records if str(record.get("record_status", "active")) != "voided"]


def load_sample_payroll_records() -> list[dict[str, Any]]:
    if not SAMPLE_PAYROLL_PATH.exists():
        return []
    return records_from_rows(read_first_sheet(SAMPLE_PAYROLL_PATH))


def load_saved_payroll_records() -> list[dict[str, Any]]:
    records = []
    for raw in load_json_array(PAYROLL_RECORDS_PATH):
        record: dict[str, Any] = {}
        for key, value in raw.items():
            if key in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS, *UNIVERSAL_PAYROLL_DECIMAL_FIELDS]:
                record[key] = parse_decimal(value)
            else:
                record[key] = value
        records.append(record)
    return records


def save_payroll_record(record: dict[str, Any], actor: str = "system") -> dict[str, Any]:
    records = load_saved_payroll_records()
    saved = dict(record)
    saved["record_id"] = saved.get("record_id") or timestamp_id("payroll")
    saved["saved_at"] = now_iso()
    saved.setdefault("record_status", "active")
    records.append(saved)
    save_json_array(PAYROLL_RECORDS_PATH, records)
    append_audit_log("payroll", str(saved["record_id"]), "payroll_record_created", actor, None, saved)
    return saved


def delete_payroll_record(record_id: str, actor: str = "system") -> bool:
    target = record_id.strip()
    records = load_saved_payroll_records()
    changed = False
    updated_records = []
    for record in records:
        if str(record.get("record_id", "")) == target and str(record.get("record_status", "active")) != "voided":
            if truthy(record.get("locked")):
                raise ValueError("Locked payroll records cannot be voided from the normal payroll register flow.")
            before = dict(record)
            record = dict(record)
            record["record_status"] = "voided"
            record["voided_at"] = now_iso()
            record["voided_by"] = actor
            append_audit_log("payroll", target, "payroll_record_voided", actor, before, record)
            changed = True
        updated_records.append(record)
    if not changed:
        return False
    save_json_array(PAYROLL_RECORDS_PATH, updated_records)
    return True


def serialize_record(record: dict[str, Any]) -> dict[str, Any]:
    return to_json_safe(record)


def payroll_register_csv(records: list[dict[str, Any]], country: str = "ALL", lang: str = DEFAULT_LANG) -> str:
    country_filter = normalize_country(country)
    template = payroll_report_template(country_filter)
    report_lang = payroll_report_language(country_filter, lang)
    messages = load_i18n(report_lang)
    output = StringIO()
    columns = template["columns"]
    fieldnames = [t(messages, str(col.get("label_key", "")), str(col.get("key", ""))) for col in columns]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()
    for record in records:
        writer.writerow({
            t(messages, str(col.get("label_key", "")), str(col.get("key", ""))): format_report_cell(record, col, for_csv=True)
            for col in columns
        })
    return output.getvalue()


def records_from_rows(rows: list[list[str]]) -> list[dict[str, Any]]:
    if not rows:
        return []

    header_index = find_tabular_header_row(rows)
    if header_index is None:
        payslip_record = extract_japanese_payslip_record(rows)
        return [payslip_record] if payslip_record else []

    headers = [normalize_header(str(value)) for value in rows[header_index]]
    records = []
    for row in rows[header_index + 1 :]:
        if not any(str(value).strip() for value in row):
            continue
        record: dict[str, Any] = {field: "" for field in IDENTITY_FIELDS}
        for label in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS]:
            record[label] = Decimal("0")
        for index, header in enumerate(headers):
            if not header:
                continue
            value = row[index] if index < len(row) else ""
            if header in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS]:
                record[header] = parse_decimal(value)
            elif header in IDENTITY_FIELDS:
                record[header] = str(value).strip()
        if not record.get("Employee No. (社員No.)") and not record.get("Employee Name (氏名)"):
            continue
        recalculate_record(record)
        records.append(record)
    return records


def find_tabular_header_row(rows: list[list[str]]) -> int | None:
    best_index: int | None = None
    best_score = 0
    for index, row in enumerate(rows[:30]):
        normalized = [normalize_header(str(value)) for value in row]
        identity_score = sum(1 for value in normalized if value in IDENTITY_FIELDS)
        amount_score = sum(1 for value in normalized if value in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS])
        score = identity_score * 2 + amount_score
        if identity_score >= 2 and amount_score >= 2 and score > best_score:
            best_score = score
            best_index = index
    return best_index


def extract_japanese_payslip_record(rows: list[list[str]]) -> dict[str, Any] | None:
    """Extract one employee record from a Japanese payslip-style worksheet."""

    cells: dict[tuple[int, int], str] = {}
    for row_index, row in enumerate(rows):
        for col_index, value in enumerate(row):
            text = str(value).strip()
            if text:
                cells[(row_index, col_index)] = text

    employee_no = value_near_label(cells, "社員No.") or value_near_label(cells, "社員No")
    employee_name = value_near_label(cells, "氏 名") or value_near_label(cells, "氏名")
    payroll_month_value = payroll_month_from_payslip(cells)
    if not employee_no and not employee_name:
        return None

    record: dict[str, Any] = {
        "Employee No. (社員No.)": employee_no,
        "Employee Name (氏名)": employee_name.replace("様", "").strip(),
        "Payroll Month (給与月)": payroll_month_value,
    }
    for label in [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS]:
        record[label] = Decimal("0")

    template_mapping = {
        "基本給": "Base Salary (基本給)",
        "役職手当": "Position Allowance (役職手当)",
        "勤務手当": "Attendance Allowance (勤務手当)",
        "住宅手当": "Housing Allowance (住宅手当)",
        "課税通勤費": "Taxable Transportation Allowance (課税通勤費)",
        "非課税通勤費": "Non-taxable Transportation Allowance (非課税通勤費)",
        "普通残業手当": "Overtime Allowance (普通残業手当)",
        "健康保険": "Health Insurance (健康保険)",
        "厚生年金": "Pension (厚生年金)",
        "雇用保険": "Employment Insurance (雇用保険)",
        "所得税": "Income Tax (所得税)",
        "支給額合計": "Gross Pay (総支給額)",
        "控除合計": "Total Deduction (控除合計)",
        "差引支給額": "Net Pay (差引支給額)",
    }
    for source_label, canonical in template_mapping.items():
        amount_text = amount_below_label(cells, source_label)
        if amount_text:
            record[canonical] = parse_decimal(amount_text)

    if record["Total Deduction (控除合計)"] == 0 and record["Gross Pay (総支給額)"] and record["Net Pay (差引支給額)"]:
        record["Total Deduction (控除合計)"] = record["Gross Pay (総支給額)"] - record["Net Pay (差引支給額)"]
    if record["Gross Pay (総支給額)"] == 0 or record["Net Pay (差引支給額)"] == 0:
        recalculate_record(record)
    record["employee_no"] = record["Employee No. (社員No.)"]
    record["employee_name"] = record["Employee Name (氏名)"]
    record["payroll_month"] = record["Payroll Month (給与月)"]
    record["calculated_base_pay"] = record.get("Base Salary (基本給)", Decimal("0"))
    record["additional_payment"] = record.get("Additional Payment (追加支給)", Decimal("0"))
    record["additional_deduction"] = record.get("Additional Deduction (追加控除)", Decimal("0"))
    record["gross_pay"] = record.get("Gross Pay (総支給額)", Decimal("0"))
    record["total_deduction"] = record.get("Total Deduction (控除合計)", Decimal("0"))
    record["net_pay"] = record.get("Net Pay (差引支給額)", Decimal("0"))
    record.setdefault("record_status", "active")
    return record


def value_near_label(cells: dict[tuple[int, int], str], label: str) -> str:
    for (row_index, col_index), value in cells.items():
        if value == label:
            candidate = cells.get((row_index + 1, col_index), "").strip()
            if candidate and candidate not in {"様"}:
                return candidate
            for delta_col in range(1, 4):
                candidate = (cells.get((row_index + 1, col_index + delta_col)) or cells.get((row_index, col_index + delta_col)) or "").strip()
                if candidate and candidate not in {"様"}:
                    return candidate
    return ""


def amount_below_label(cells: dict[tuple[int, int], str], label: str) -> str:
    for (row_index, col_index), value in cells.items():
        if value == label:
            for delta_row in range(1, 4):
                candidate = cells.get((row_index + delta_row, col_index), "").strip()
                if candidate and is_amount_like(candidate):
                    return candidate
    return ""


def payroll_month_from_payslip(cells: dict[tuple[int, int], str]) -> str:
    for value in cells.values():
        text = value.strip()
        if "年" in text and "月" in text:
            normalized = text.replace("支給日：", "").replace("支給日:", "")
            parts = normalized.split("年", 1)
            if len(parts) == 2:
                year = "".join(ch for ch in parts[0] if ch.isdigit())
                month = "".join(ch for ch in parts[1].split("月", 1)[0] if ch.isdigit())
                if year and month:
                    return f"{int(year):04d}-{int(month):02d}"
        if text.isdigit() and len(text) == 5:
            excel_month = excel_serial_to_month(int(text))
            if excel_month:
                return excel_month
    return ""


def excel_serial_to_month(serial: int) -> str:
    try:
        from datetime import date, timedelta

        value = date(1899, 12, 30) + timedelta(days=serial)
        return f"{value.year:04d}-{value.month:02d}"
    except Exception:  # noqa: BLE001 - best-effort parsing for uploaded templates.
        return ""


def is_amount_like(value: str) -> bool:
    try:
        parse_decimal(value)
    except Exception:  # noqa: BLE001 - validation helper.
        return False
    return True


def manual_record_from_form(form: dict[str, str], messages: dict[str, str] | None = None) -> dict[str, Any]:
    country = normalize_country(form.get("country", "JP"))
    if country == "ALL":
        country = "JP"
    currency = form.get("currency", COUNTRY_DEFAULTS.get(country, {}).get("currency", "JPY")).strip().upper() or COUNTRY_DEFAULTS.get(country, {}).get("currency", "JPY")
    record: dict[str, Any] = {
        "Employee No. (社員No.)": form.get("employee_no", "").strip(),
        "Employee Name (氏名)": form.get("employee_name", "").strip(),
        "Payroll Month (給与月)": form.get("payroll_month", "").strip(),
        "country": country,
        "work_location_country": country,
        "currency": currency,
    }
    if not record["Employee No. (社員No.)"] or not record["Employee Name (氏名)"] or not record["Payroll Month (給与月)"]:
        raise ValueError(t(messages, "error.required_identity"))
    for key, canonical in AMOUNT_INPUTS:
        record[canonical] = parse_decimal(form.get(key, "0"))
    recalculate_record(record)
    return record


def read_first_sheet(path: Path) -> list[list[str]]:
    with ZipFile(path) as archive:
        return read_sheet_from_archive(archive)


def read_first_sheet_from_bytes(content: bytes) -> list[list[str]]:
    with ZipFile(BytesIO(content)) as archive:
        return read_sheet_from_archive(archive)


def read_sheet_from_archive(archive: ZipFile) -> list[list[str]]:
    namespace = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
    shared_strings = read_shared_strings(archive, namespace)
    sheet_xml = archive.read("xl/worksheets/sheet1.xml")
    root = ElementTree.fromstring(sheet_xml)
    parsed_rows: list[list[str]] = []
    for row in root.findall(".//main:sheetData/main:row", namespace):
        values_by_col: dict[int, str] = {}
        for cell in row.findall("main:c", namespace):
            column_index = column_index_from_cell_ref(cell.attrib.get("r", "A1"))
            values_by_col[column_index] = cell_value(cell, namespace, shared_strings)
        if values_by_col:
            parsed_rows.append([values_by_col.get(index, "") for index in range(1, max(values_by_col) + 1)])
    return parsed_rows


def read_shared_strings(archive: ZipFile, namespace: dict[str, str]) -> list[str]:
    try:
        xml = archive.read("xl/sharedStrings.xml")
    except KeyError:
        return []
    root = ElementTree.fromstring(xml)
    strings = []
    for item in root.findall("main:si", namespace):
        strings.append("".join(text.text or "" for text in item.findall(".//main:t", namespace)))
    return strings


def cell_value(cell: ElementTree.Element, namespace: dict[str, str], shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    inline_text = cell.find("main:is/main:t", namespace)
    if inline_text is not None and inline_text.text is not None:
        return inline_text.text
    value_node = cell.find("main:v", namespace)
    if value_node is None or value_node.text is None:
        return ""
    raw_value = value_node.text
    if cell_type == "s":
        index = int(raw_value)
        return shared_strings[index] if index < len(shared_strings) else ""
    return raw_value


def column_index_from_cell_ref(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha()) or "A"
    index = 0
    for letter in letters.upper():
        index = index * 26 + (ord(letter) - 64)
    return index


def normalize_header(value: str) -> str:
    cleaned = value.strip()
    return HEADER_ALIASES.get(cleaned, cleaned if cleaned in [*IDENTITY_FIELDS, *PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS] else "")


def recalculate_record(record: dict[str, Any]) -> None:
    gross = sum((Decimal(record.get(label, 0)) for label in PAYMENT_FIELDS), Decimal("0"))
    deduction = sum((Decimal(record.get(label, 0)) for label in DEDUCTION_FIELDS), Decimal("0"))
    record["Gross Pay (総支給額)"] = gross
    record["Total Deduction (控除合計)"] = deduction
    record["Net Pay (差引支給額)"] = gross - deduction


def calculate_totals(records: list[dict[str, Any]]) -> dict[str, Decimal]:
    labels = [*PAYMENT_FIELDS, *DEDUCTION_FIELDS, *DERIVED_FIELDS]
    active_records = active_payroll_records(records)
    return {label: sum((parse_decimal(record.get(label, 0)) for record in active_records), Decimal("0")) for label in labels}


def payroll_month(records: list[dict[str, Any]]) -> str:
    if not records:
        return "N/A"
    return str(records[0].get("Payroll Month (給与月)", "N/A"))


def parse_decimal(value: Any) -> Decimal:
    cleaned = str(value or "0")
    for token in (",", "¥", "￥", "S$", "$", "CNY", "JPY", "SGD", "INR", "₹"):
        cleaned = cleaned.replace(token, "")
    cleaned = cleaned.strip()
    return Decimal(cleaned or "0")


def plain_amount(value: Any) -> str:
    amount = Decimal(str(value or "0"))
    return f"{amount:.0f}"


def money(value: Any) -> str:
    amount = parse_decimal(value)
    return f"¥{amount:,.0f}"


def money_with_currency(value: Any, currency: Any = "") -> str:
    amount = parse_decimal(value)
    code = str(currency or "").strip().upper()
    if not code:
        return money(amount)
    return f"{code} {amount:,.0f}"


def run(host: str = "127.0.0.1", port: int = 8001) -> None:
    server = ThreadingHTTPServer((host, port), TacaiHandler)
    print(f"TACAI Prj Web UI running at http://{host}:{port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down TACAI Prj Web UI")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run TACAI Prj local Web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8001)
    args = parser.parse_args()
    run(args.host, args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
