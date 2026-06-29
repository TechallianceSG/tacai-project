"""Local web app for TAC-employeeadmin - employee administration MVP.

This project intentionally uses only Python standard library modules so it can
run locally without installing dependencies.
"""

from __future__ import annotations

import argparse
import base64
import copy
import csv
import hashlib
import hmac
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from email.parser import BytesParser
from email.policy import default as EMAIL_POLICY
from email.utils import formataddr
from html import escape
from http.cookies import Morsel, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import shutil
import smtplib
import ssl
from typing import Any
from urllib.error import HTTPError, URLError
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
EMPLOYEES_PATH = ROOT_DIR / "database" / "employees.json"
EMPLOYEE_BACKUPS_DIR = ROOT_DIR / "database" / "backups"
AUDIT_LOGS_PATH = ROOT_DIR / "database" / "audit_logs.json"
I18N_DIR = ROOT_DIR / "i18n"
EMPLOYEE_DOCS_DIR = ROOT_DIR / "docs" / "empdoc"
EMPLOYEE_DOCS_RELATIVE_DIR = "docs/empdoc"
ONBOARDING_REQUESTS_PATH = ROOT_DIR / "database" / "employee_onboarding_requests.json"
ONBOARDING_SUBMISSIONS_PATH = ROOT_DIR / "database" / "employee_onboarding_submissions.json"
ONBOARDING_DOCUMENTS_PATH = ROOT_DIR / "database" / "employee_onboarding_documents.json"
ONBOARDING_SIGNATURES_PATH = ROOT_DIR / "database" / "employee_onboarding_signatures.json"
ONBOARDING_MYNUMBER_ACCESS_LOGS_PATH = ROOT_DIR / "database" / "employee_onboarding_mynumber_access_logs.json"
ONBOARDING_DOCS_DIR = ROOT_DIR / "docs" / "onboarding"
ONBOARDING_DOCS_RELATIVE_DIR = "docs/onboarding"

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {3000, 3001, 4000, 4001, 5000, 5001, 6000, 6001, 8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8012, 8016, 8018}
CONFIGURED_PUBLIC_HOSTS = {host.strip().lower() for host in os.environ.get("TACAI_ALLOWED_PUBLIC_HOSTS", "").split(",") if host.strip()}


def _resolve_host(request_host: str | None = None) -> str:
    """Return 127.0.0.1 when accessed locally, otherwise the LAN IP."""
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return TACAI_PUBLIC_HOST


def resolve_portal_url(request_host: str | None = None, default_portal_url: str | None = None) -> str:
    """Return portal URL adjusted for the request origin."""
    from urllib.parse import urlparse as _urlparse
    portal = default_portal_url or PORTAL_BASE_URL
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        parsed = _urlparse(portal)
        port = parsed.port or 3000
        return f"http://127.0.0.1:{port}{parsed.path if parsed.path else ''}"
    return portal


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return (os.environ.get(env_name, local_base_url(fallback_port)).strip() or local_base_url(fallback_port)).rstrip("/")


def base_url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


APP_BASE_URL = public_base_url("EMPLOYEE_ADMIN_PUBLIC_BASE_URL", 8004)
PORTAL_BASE_URL = (os.environ.get("PORTAL_BASE_URL", os.environ.get("PORTAL_PUBLIC_BASE_URL", local_base_url(8005))).strip() or local_base_url(8005)).rstrip("/")
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = (os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip() or internal_base_url(8006)).rstrip("/")
MASTERDATA_BASE_URL = (os.environ.get("MASTERDATA_BASE_URL", os.environ.get("MASTERDATA_PUBLIC_BASE_URL", local_base_url(8007))).strip() or local_base_url(8007)).rstrip("/")
MASTERDATA_INTERNAL_BASE_URL = (os.environ.get("MASTERDATA_INTERNAL_BASE_URL", internal_base_url(8007)).strip() or internal_base_url(8007)).rstrip("/")
MASTERDATA_INTERNAL_API_TOKEN = os.environ.get("MASTERDATA_INTERNAL_API_TOKEN", "").strip()
MASTERDATA_API_TIMEOUT_SECONDS = int(os.environ.get("MASTERDATA_API_TIMEOUT_SECONDS", "5") or "5")
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "tacai_flash"
ONBOARDING_VERIFICATION_COOKIE = "tacai_onboarding_verify"
REQUIRED_MODULE_PERMISSION = "employee_management.access"

DEFAULT_LANG = "en"
SUPPORTED_LANGS = {"en", "ja", "zh"}
DEFAULT_ACTOR = "Admin"
VISA_ALERT_DAYS = 90
PROBATION_ALERT_DAYS = 30
DOCUMENT_ALERT_DAYS = 90
LABOR_CONTRACT_ALERT_DAYS = 90
LABOR_CONTRACT_OPEN_END_DATE = "2099-12-12"
DATA_COMPLETION_WARNING_THRESHOLD = 80
MAX_UPLOAD_REQUEST_BYTES = 25 * 1024 * 1024
MAX_FORM_REQUEST_BYTES = 1 * 1024 * 1024
MAX_UPLOAD_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOAD_FILES_PER_REQUEST = 10
ALLOWED_UPLOAD_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".doc", ".docx", ".xls", ".xlsx", ".txt"}
ONBOARDING_EMAIL_SENDER = os.environ.get("ONBOARDING_EMAIL_SENDER", "HRadmin@tacjob.com").strip() or "HRadmin@tacjob.com"
ONBOARDING_EMAIL_REPLY_TO = os.environ.get("ONBOARDING_EMAIL_REPLY_TO", ONBOARDING_EMAIL_SENDER).strip() or ONBOARDING_EMAIL_SENDER
ONBOARDING_DEFAULT_CC_EMAIL = os.environ.get("ONBOARDING_DEFAULT_CC_EMAIL", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
ONBOARDING_EMAIL_TEMPLATE_VERSION = "onboarding_invitation_v1"
ONBOARDING_HR_NOTIFICATION_EMAIL = os.environ.get("ONBOARDING_HR_NOTIFICATION_EMAIL", ONBOARDING_EMAIL_SENDER).strip() or ONBOARDING_EMAIL_SENDER
ONBOARDING_SMTP_HOST = os.environ.get("ONBOARDING_SMTP_HOST", "").strip()
ONBOARDING_SMTP_PORT = int(os.environ.get("ONBOARDING_SMTP_PORT", "587") or "587")
ONBOARDING_SMTP_USERNAME = os.environ.get("ONBOARDING_SMTP_USERNAME", "").strip()
ONBOARDING_SMTP_PASSWORD = os.environ.get("ONBOARDING_SMTP_PASSWORD", "")
ONBOARDING_SMTP_USE_TLS = os.environ.get("ONBOARDING_SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no", "off"}
ONBOARDING_TOKEN_DAYS = int(os.environ.get("ONBOARDING_TOKEN_DAYS", "7") or "7")
ONBOARDING_VERIFICATION_CODE_MINUTES = int(os.environ.get("ONBOARDING_VERIFICATION_CODE_MINUTES", "10") or "10")
ONBOARDING_VERIFICATION_MAX_ATTEMPTS = int(os.environ.get("ONBOARDING_VERIFICATION_MAX_ATTEMPTS", "5") or "5")
ONBOARDING_VERIFICATION_LOCK_MINUTES = int(os.environ.get("ONBOARDING_VERIFICATION_LOCK_MINUTES", "15") or "15")
ONBOARDING_VERIFICATION_SECRET_CONFIGURED = bool(os.environ.get("ONBOARDING_VERIFICATION_SECRET", "").strip())
ONBOARDING_VERIFICATION_SECRET = os.environ.get("ONBOARDING_VERIFICATION_SECRET", "").strip() or secrets.token_urlsafe(32)
ONBOARDING_STATUSES = ["draft", "ready_to_send", "sent", "opened", "in_progress", "submitted", "pending_hr_review", "returned_to_candidate", "resubmitted", "approved", "imported_to_employee_master", "rejected", "expired", "cancelled"]
ONBOARDING_CATEGORIES = ["regular_employee", "dispatch_employee", "contractor", "foreign_employee", "other"]
ONBOARDING_DOCUMENT_TYPES = ["employment_contract", "nda", "labor_condition_notice", "personal_information_consent", "dispatch_condition_notice", "residence_card", "passport", "bank_proof", "address_proof", "resume", "other_signed_document", "other_identity_document", "other_bank_or_payroll_document", "other_hr_requested_file", "other"]
ONBOARDING_SIGNING_MODES = ["electronic_signature_required", "electronic_signature_optional", "manual_sign_upload_required", "acknowledgement_only", "no_signature_required"]
ONBOARDING_DOCUMENT_STATUSES = ["uploaded_by_hr", "available_for_candidate", "viewed_by_candidate", "downloaded_by_candidate", "manual_signed_upload_received", "signed_by_candidate", "evidence_captured", "submitted_by_candidate", "pending_hr_review", "accepted", "rejected", "needs_resubmission", "archived_to_employee_master"]
ONBOARDING_REQUIRED_DISPATCH_DOCUMENT_TYPES = ["employment_contract", "nda", "labor_condition_notice", "dispatch_condition_notice"]
ONBOARDING_SIGNATURE_CAPABLE_MODES = {"electronic_signature_required", "electronic_signature_optional", "manual_sign_upload_required"}
PUBLIC_LINK_LOCAL_HOSTS = {"", "127.0.0.1", "localhost", "::1"}

EMPLOYMENT_STATUSES = ["active", "inactive", "pending", "on_leave", "resigned", "probation"]
TIMESHEET_SELECTABLE_EMPLOYMENT_STATUSES = {"active", "probation", "on_leave"}
EMPLOYMENT_TYPES = ["employee", "contractor", "dispatch", "part_time", "intern"]
COUNTRY_CODES = ["JP", "CN", "SG"]
BUSINESS_LINES = ["recruitment", "rpo", "haken", "payroll", "internal", "ai_platform"]
PROFILE_STATUSES = ["draft", "needs_review", "complete", "archived"]
DEFAULT_MANAGER_EMPLOYEE_NUMBER = "ADMIN-001"
GENDERS = ["", "male", "female", "other", "prefer_not_to_say"]
SALARY_TYPES = ["", "monthly", "hourly", "annual", "daily"]
SUPPORTED_CURRENCIES = ["SGD", "USD", "CNY", "INR", "TWD", "JPY"]
# salary_type -> required wage field path mapping for data completeness
SALARY_TYPE_REQUIRED_WAGE_FIELD: dict[str, str] = {
    "monthly": "payroll.monthly_base_salary",
    "daily": "payroll.daily_wage",
    "hourly": "payroll.hourly_wage",
}
BANK_ACCOUNT_TYPES = ["", "ordinary", "current", "savings"]
DISPATCH_CONTRACT_TYPES = ["", "worker_dispatch", "ses", "contract", "other"]
JAPANESE_LEVELS = ["", "native", "N1", "N2", "N3", "N4", "N5", "none"]
ENGLISH_LEVELS = ["", "native", "business", "fluent", "intermediate", "basic", "none"]
DOCUMENT_TYPES = ["", "employment_contract", "nda", "residence_card", "passport", "my_number_related", "offer_letter", "certificate", "other"]
DOCUMENT_STATUSES = ["", "on_file", "missing", "expired", "pending_renewal", "not_required"]
BASE_REQUIRED_DOCUMENT_TYPES = ["employment_contract", "nda", "offer_letter"]
ACTIVE_EMPLOYEE_REQUIRED_DOCUMENT_TYPES = ["my_number_related"]
FOREIGN_EMPLOYEE_REQUIRED_DOCUMENT_TYPES = ["residence_card", "passport"]
ONBOARDING_CANDIDATE_REQUIRED_DOCUMENT_TYPES = ["bank_proof"]
ONBOARDING_FOREIGN_REQUIRED_DOCUMENT_TYPES = ["residence_card", "passport"]
ONBOARDING_REQUIRED_SIGNING_MODES = {"electronic_signature_required", "manual_sign_upload_required"}
ONBOARDING_DOCUMENT_COMPLETE_STATUSES = {"submitted_by_candidate", "manual_signed_upload_received", "signed_by_candidate", "accepted", "archived_to_employee_master"}
DOCUMENT_COMPLETE_STATUSES = {"on_file", "not_required"}
DOCUMENT_FIELD_NAMES = [
    "document_id",
    "document_type",
    "title",
    "issuer",
    "document_date",
    "expiry_date",
    "received_date",
    "storage_reference",
    "status",
    "notes",
    "original_filename",
    "stored_filename",
    "content_type",
    "file_size_bytes",
    "uploaded_at",
    "uploaded_by",
]
UPLOAD_DOCUMENT_METADATA_FIELDS = {
    "upload_document_type": "document_type",
    "upload_issuer": "issuer",
    "upload_document_date": "document_date",
    "upload_expiry_date": "expiry_date",
    "upload_received_date": "received_date",
    "upload_status": "status",
    "upload_notes": "notes",
}

PROFILE_FIELD_PATHS = [
    "profile.name.display_name",
    "profile.name.family_name",
    "profile.name.given_name",
    "profile.name.family_name_kana",
    "profile.name.given_name_kana",
    "profile.name.romaji_name",
    "profile.gender",
    "profile.date_of_birth",
    "profile.nationality",
    "profile.address.postal_code",
    "profile.address.prefecture",
    "profile.address.city",
    "profile.address.street",
    "profile.address.building",
    "profile.email",
    "profile.email_p",
    "profile.phone",
    "profile.emergency_contact.name",
    "profile.emergency_contact.relationship",
    "profile.emergency_contact.phone",
    "profile.emergency_contact.email",
]

EMPLOYMENT_FIELD_PATHS = [
    "employment.country_code",
    "employment.legal_entity",
    "employment.work_country",
    "employment.business_line",
    "employment.department",
    "employment.join_date",
    "employment.employment_type",
    "employment.entity_id",
    "employment.department_id",
    "employment.team_id",
    "employment.position",
    "employment.manager_employee_id",
    "employment.office_location",
    "employment.assignment",
    "employment.status",
    "employment.probation_end_date",
    "employment.contract.start_date",
    "employment.contract.end_date",
    "employment.resignation.resignation_date",
    "employment.resignation.last_working_date",
    "employment.resignation.reason",
]

PAYROLL_FIELD_PATHS = [
    "payroll.bank.bank_name",
    "payroll.bank.branch_name",
    "payroll.bank.swift_code",
    "payroll.bank.account_type",
    "payroll.bank.account_number",
    "payroll.bank.account_holder",
    "payroll.salary_type",
    "payroll.payroll_currency",
    "payroll.monthly_base_salary",
    "payroll.daily_wage",
    "payroll.hourly_wage",
    "payroll.salary_amount_yen",
    "payroll.transportation_allowance_yen",
    "payroll.bonus_eligible",
    "payroll.social_insurance_enrolled",
    "payroll.pension_enrolled",
    "payroll.employment_insurance_enrolled",
    "payroll.notes",
]

VISA_FIELD_PATHS = [
    "visa.visa_type",
    "visa.residence_status",
    "visa.expiry_date",
    "visa.residence_card_number",
    "visa.passport_number",
    "visa.passport_expiry_date",
    "visa.renewal_reminder_enabled",
    "visa.renewal_reminder_date",
    "visa.notes",
]

DISPATCH_FIELD_PATHS = [
    "dispatch_compliance.client_name",
    "dispatch_compliance.assignment_location",
    "dispatch_compliance.dispatch_start_date",
    "dispatch_compliance.dispatch_end_date",
    "dispatch_compliance.contract_type",
    "dispatch_compliance.work_description",
    "dispatch_compliance.supervisor.name",
    "dispatch_compliance.supervisor.title",
    "dispatch_compliance.supervisor.phone",
    "dispatch_compliance.supervisor.email",
    "dispatch_compliance.notes",
]

LANGUAGE_PROFILE_FIELD_PATHS = [
    "language_profile.japanese_level",
    "language_profile.english_level",
    "language_profile.native_languages",
    "language_profile.additional_languages",
    "language_profile.notes",
]

SKILLS_PROFILE_FIELD_PATHS = [
    "skills_profile.primary_skill",
    "skills_profile.secondary_skill",
    "skills_profile.years_of_experience",
    "skills_profile.it_skills",
    "skills_profile.engineering_skills",
    "skills_profile.certifications",
    "skills_profile.industry_experience",
    "skills_profile.notes",
]

SKILLS_LANGUAGE_FIELD_PATHS = LANGUAGE_PROFILE_FIELD_PATHS + SKILLS_PROFILE_FIELD_PATHS
DOCUMENT_FIELD_PATHS = ["documents"]
HISTORY_FIELD_PATHS = ["employment_history", "visa_history", "dispatch_assignment_history"]
HISTORY_ATTACHMENT_FIELD_NAMES = [field if field != "document_id" else "attachment_id" for field in DOCUMENT_FIELD_NAMES]
HISTORY_COMMON_FIELD_NAMES = ["history_id", "event_type", "effective_date", "changed_at", "changed_by", "source", "changed_fields", "previous_values", "notes", "attachments"]
VISA_HISTORY_FIELD_NAMES = HISTORY_COMMON_FIELD_NAMES + ["visa_type", "residence_status", "expiry_date", "residence_card_number", "passport_number", "passport_expiry_date", "renewal_reminder_enabled", "renewal_reminder_date"]
DISPATCH_HISTORY_FIELD_NAMES = HISTORY_COMMON_FIELD_NAMES + ["client_name", "assignment_location", "dispatch_start_date", "dispatch_end_date", "contract_type", "work_description", "supervisor"]
EMPLOYMENT_HISTORY_FIELD_NAMES = HISTORY_COMMON_FIELD_NAMES + ["join_date", "employment_type", "entity_id", "department_id", "team_id", "position", "manager_employee_id", "office_location", "assignment", "status", "probation_end_date", "contract", "resignation"]

VISA_HISTORY_TRIGGER_FIELD_PATHS = [
    "visa.visa_type",
    "visa.residence_status",
    "visa.expiry_date",
    "visa.residence_card_number",
    "visa.passport_number",
    "visa.passport_expiry_date",
    "visa.renewal_reminder_enabled",
    "visa.renewal_reminder_date",
]
DISPATCH_HISTORY_TRIGGER_FIELD_PATHS = [
    "dispatch_compliance.client_name",
    "dispatch_compliance.assignment_location",
    "dispatch_compliance.dispatch_start_date",
    "dispatch_compliance.dispatch_end_date",
    "dispatch_compliance.contract_type",
    "dispatch_compliance.work_description",
    "dispatch_compliance.supervisor.name",
    "dispatch_compliance.supervisor.title",
    "dispatch_compliance.supervisor.phone",
    "dispatch_compliance.supervisor.email",
]
EMPLOYMENT_HISTORY_TRIGGER_FIELD_PATHS = EMPLOYMENT_FIELD_PATHS

VISA_HISTORY_EVENT_TYPES = ["visa_change", "visa_renewal", "passport_update", "residence_status_change", "manual_record"]
DISPATCH_HISTORY_EVENT_TYPES = ["assignment_start", "assignment_change", "assignment_end", "supervisor_change", "manual_record"]
EMPLOYMENT_HISTORY_EVENT_TYPES = ["employment_change", "status_change", "department_change", "position_change", "resignation", "manual_record"]
HISTORY_SOURCES = ["auto", "manual", "migration"]

HISTORY_CONFIG = {
    "employment": {
        "array_key": "employment_history",
        "title_key": "section.employment_history",
        "add_action_key": "action.add_employment_history",
        "permission": "employee_management.edit",
        "history_id_prefix": "EMPLOYMENT-HIST",
        "event_types": EMPLOYMENT_HISTORY_EVENT_TYPES,
        "audit_created": "employment_history_created",
        "audit_updated": "employment_history_updated",
        "trigger_paths": EMPLOYMENT_HISTORY_TRIGGER_FIELD_PATHS,
    },
    "visa": {
        "array_key": "visa_history",
        "title_key": "section.visa_history",
        "add_action_key": "action.add_visa_history",
        "permission": "employee_management.visa.edit",
        "history_id_prefix": "VISA-HIST",
        "event_types": VISA_HISTORY_EVENT_TYPES,
        "audit_created": "visa_history_created",
        "audit_updated": "visa_history_updated",
        "trigger_paths": VISA_HISTORY_TRIGGER_FIELD_PATHS,
    },
    "dispatch": {
        "array_key": "dispatch_assignment_history",
        "title_key": "section.dispatch_assignment_history",
        "add_action_key": "action.add_dispatch_history",
        "permission": "employee_management.edit",
        "history_id_prefix": "DISPATCH-HIST",
        "event_types": DISPATCH_HISTORY_EVENT_TYPES,
        "audit_created": "dispatch_history_created",
        "audit_updated": "dispatch_history_updated",
        "trigger_paths": DISPATCH_HISTORY_TRIGGER_FIELD_PATHS,
    },
}

FIELD_PATHS = (
    PROFILE_FIELD_PATHS
    + EMPLOYMENT_FIELD_PATHS
    + PAYROLL_FIELD_PATHS
    + VISA_FIELD_PATHS
    + DISPATCH_FIELD_PATHS
    + SKILLS_LANGUAGE_FIELD_PATHS
    + DOCUMENT_FIELD_PATHS
    + HISTORY_FIELD_PATHS
)
BANK_FIELD_PATHS = [
    "payroll.bank.bank_name",
    "payroll.bank.branch_name",
    "payroll.bank.swift_code",
    "payroll.bank.account_type",
    "payroll.bank.account_number",
    "payroll.bank.account_holder",
]
METADATA_FORM_FIELD_PATHS = ["metadata.profile_status"]
PHASE1_FORM_FIELD_PATHS = ["employee_number"] + PROFILE_FIELD_PATHS + EMPLOYMENT_FIELD_PATHS + BANK_FIELD_PATHS + METADATA_FORM_FIELD_PATHS
DATE_FIELD_PATHS = [
    "profile.date_of_birth",
    "employment.join_date",
    "employment.probation_end_date",
    "employment.contract.start_date",
    "employment.contract.end_date",
    "employment.resignation.resignation_date",
    "employment.resignation.last_working_date",
    "visa.expiry_date",
    "visa.passport_expiry_date",
    "visa.renewal_reminder_date",
    "dispatch_compliance.dispatch_start_date",
    "dispatch_compliance.dispatch_end_date",
]
MONEY_FIELD_PATHS = ["payroll.monthly_base_salary", "payroll.daily_wage", "payroll.hourly_wage", "payroll.salary_amount_yen", "payroll.transportation_allowance_yen"]
BOOLEAN_FIELD_PATHS = [
    "payroll.bonus_eligible",
    "payroll.social_insurance_enrolled",
    "payroll.pension_enrolled",
    "payroll.employment_insurance_enrolled",
    "visa.renewal_reminder_enabled",
]
LIST_FIELD_PATHS = [
    "language_profile.native_languages",
    "language_profile.additional_languages",
    "skills_profile.it_skills",
    "skills_profile.engineering_skills",
    "skills_profile.certifications",
    "skills_profile.industry_experience",
]

DETAIL_LONG_FIELD_PATHS = {
    "profile.address.street",
    "profile.address.building",
    "employment.resignation.reason",
    "payroll.notes",
    "visa.notes",
    "dispatch_compliance.work_description",
    "dispatch_compliance.notes",
    "language_profile.native_languages",
    "language_profile.additional_languages",
    "language_profile.notes",
    "skills_profile.it_skills",
    "skills_profile.engineering_skills",
    "skills_profile.certifications",
    "skills_profile.industry_experience",
    "skills_profile.notes",
    "metadata.created_at",
    "metadata.updated_at",
}

PROFILE_DETAIL_GROUPS = [
    ("form.group.name", ["employee_number", "profile.name.display_name", "profile.name.family_name", "profile.name.given_name", "profile.name.family_name_kana", "profile.name.given_name_kana", "profile.name.romaji_name"]),
    ("form.group.personal", ["profile.gender", "profile.date_of_birth", "profile.nationality"]),
    ("form.group.contact", ["profile.email", "profile.email_p", "profile.phone"]),
    ("form.group.address", ["profile.address.postal_code", "profile.address.prefecture", "profile.address.city", "profile.address.street", "profile.address.building"]),
    ("form.group.emergency_contact", ["profile.emergency_contact.name", "profile.emergency_contact.relationship", "profile.emergency_contact.phone", "profile.emergency_contact.email"]),
]
EMPLOYMENT_DETAIL_GROUPS = [
    ("form.group.employment_basics", ["employment.country_code", "employment.entity_id", "employment.work_country", "employment.business_line", "employment.join_date", "employment.employment_type", "employment.department_id", "employment.team_id", "employment.department", "employment.position", "employment.manager_employee_id"]),
    ("form.group.labor_contract", ["employment.contract.start_date", "employment.contract.end_date"]),
    ("form.group.assignment", ["employment.office_location", "employment.assignment", "employment.status", "employment.probation_end_date"]),
    ("form.group.resignation", ["employment.resignation.resignation_date", "employment.resignation.last_working_date", "employment.resignation.reason"]),
]
PAYROLL_DETAIL_GROUPS = [
    ("detail.group.bank", ["payroll.bank.bank_name", "payroll.bank.branch_name", "payroll.bank.swift_code", "payroll.bank.account_type", "payroll.bank.account_number", "payroll.bank.account_holder"]),
    ("detail.group.salary", ["payroll.salary_type", "payroll.payroll_currency", "payroll.monthly_base_salary", "payroll.daily_wage", "payroll.hourly_wage", "payroll.salary_amount_yen", "payroll.transportation_allowance_yen", "payroll.bonus_eligible"]),
    ("detail.group.insurance", ["payroll.social_insurance_enrolled", "payroll.pension_enrolled", "payroll.employment_insurance_enrolled"]),
    ("detail.group.notes", ["payroll.notes"]),
]
VISA_DETAIL_GROUPS = [
    ("detail.group.visa_status", ["visa.visa_type", "visa.residence_status", "visa.expiry_date", "visa.residence_card_number"]),
    ("detail.group.passport", ["visa.passport_number", "visa.passport_expiry_date"]),
    ("detail.group.renewal", ["visa.renewal_reminder_enabled", "visa.renewal_reminder_date"]),
    ("detail.group.notes", ["visa.notes"]),
]
DISPATCH_DETAIL_GROUPS = [
    ("detail.group.dispatch_assignment", ["dispatch_compliance.client_name", "dispatch_compliance.assignment_location", "dispatch_compliance.dispatch_start_date", "dispatch_compliance.dispatch_end_date", "dispatch_compliance.contract_type", "dispatch_compliance.work_description"]),
    ("detail.group.supervisor", ["dispatch_compliance.supervisor.name", "dispatch_compliance.supervisor.title", "dispatch_compliance.supervisor.phone", "dispatch_compliance.supervisor.email"]),
    ("detail.group.notes", ["dispatch_compliance.notes"]),
]
SKILLS_LANGUAGE_DETAIL_GROUPS = [
    ("section.language_profile", LANGUAGE_PROFILE_FIELD_PATHS),
    ("section.skills_profile", SKILLS_PROFILE_FIELD_PATHS),
]
METADATA_DETAIL_GROUPS = [
    ("section.metadata", ["metadata.profile_status", "metadata.created_at", "metadata.created_by", "metadata.updated_at", "metadata.updated_by"]),
]

EMPLOYEE_MASTER_REQUIRED_FIELD_MAPPING = [
    ("employee_id", "employee_number"),
    ("full_name", "profile.name.display_name"),
    ("country_code", "employment.country_code"),
    ("legal_entity_code", "employment.entity_id"),
    ("employment_status", "employment.status"),
    ("employment_type", "employment.employment_type"),
    ("hire_date", "employment.join_date"),
    ("department_code", "employment.department_id"),
    ("work_email", "profile.email"),
    ("work_country", "employment.work_country"),
    ("business_line", "employment.business_line"),
    ("profile_status", "metadata.profile_status"),
]
BANK_IMPORT_REQUIRED_FIELD_MAPPING = [
    ("bank_name", "payroll.bank.bank_name"),
    ("bank_branch_name", "payroll.bank.branch_name"),
    ("bank_account_type", "payroll.bank.account_type"),
    ("bank_account_number", "payroll.bank.account_number"),
    ("bank_account_holder", "payroll.bank.account_holder"),
]
BANK_IMPORT_OPTIONAL_FIELD_MAPPING = [
    ("bank_swift_code", "payroll.bank.swift_code"),
]
LABOR_CONTRACT_IMPORT_OPTIONAL_FIELD_MAPPING = [
    ("labor_contract_start_date", "employment.contract.start_date"),
    ("labor_contract_end_date", "employment.contract.end_date"),
]
COMMON_REQUIRED_FIELD_MAPPING = EMPLOYEE_MASTER_REQUIRED_FIELD_MAPPING + BANK_IMPORT_REQUIRED_FIELD_MAPPING + BANK_IMPORT_OPTIONAL_FIELD_MAPPING + LABOR_CONTRACT_IMPORT_OPTIONAL_FIELD_MAPPING
COMMON_REQUIRED_CSV_FIELDS = [field for field, _path in COMMON_REQUIRED_FIELD_MAPPING]
IMPORT_REQUIRED_CSV_FIELDS = [field for field, _path in EMPLOYEE_MASTER_REQUIRED_FIELD_MAPPING + BANK_IMPORT_REQUIRED_FIELD_MAPPING]
COMMON_REQUIRED_CSV_TO_PATH = dict(COMMON_REQUIRED_FIELD_MAPPING)
COMMON_REQUIRED_PATH_TO_CSV = {path: field for field, path in COMMON_REQUIRED_FIELD_MAPPING}
COMMON_REQUIRED_FIELD_PATHS = [path for _field, path in EMPLOYEE_MASTER_REQUIRED_FIELD_MAPPING]
IMPORT_REQUIRED_FIELD_PATHS = [path for _field, path in EMPLOYEE_MASTER_REQUIRED_FIELD_MAPPING + BANK_IMPORT_REQUIRED_FIELD_MAPPING]
REQUIRED_FIELD_PATHS = COMMON_REQUIRED_FIELD_PATHS
CSV_HEADER_LANGS = ("en", "ja", "zh")
CSV_HEADER_LABELS = {
    "en": {field: field for field in COMMON_REQUIRED_CSV_FIELDS},
    "ja": {
        "employee_id": "社員番号",
        "full_name": "氏名",
        "country_code": "所属国コード",
        "legal_entity_code": "法人コード",
        "employment_status": "雇用ステータス",
        "employment_type": "雇用形態",
        "hire_date": "入社日",
        "department_code": "部署コード",
        "work_email": "会社メール",
        "work_country": "勤務国コード",
        "business_line": "事業ライン",
        "profile_status": "プロフィール状態",
        "bank_name": "銀行名",
        "bank_branch_name": "支店名",
        "bank_account_type": "口座種別",
        "bank_account_number": "口座番号",
        "bank_account_holder": "口座名義",
        "bank_swift_code": "SWIFTコード",
        "labor_contract_start_date": "労働契約開始日",
        "labor_contract_end_date": "労働契約終了日",
    },
    "zh": {
        "employee_id": "员工编号",
        "full_name": "姓名",
        "country_code": "所属国家代码",
        "legal_entity_code": "法人代码",
        "employment_status": "雇佣状态",
        "employment_type": "雇佣类型",
        "hire_date": "入职日期",
        "department_code": "部门代码",
        "work_email": "公司邮箱",
        "work_country": "工作国家代码",
        "business_line": "业务线",
        "profile_status": "资料状态",
        "bank_name": "银行名称",
        "bank_branch_name": "支店/分行名称",
        "bank_account_type": "账户类型",
        "bank_account_number": "银行账号",
        "bank_account_holder": "账户名义人",
        "bank_swift_code": "SWIFT代码",
        "labor_contract_start_date": "劳动合同开始日期",
        "labor_contract_end_date": "劳动合同终止日期",
    },
}

SAFE_EMPLOYEE_EXPORT_FIELDS = [
    ("employee_number", "employee_number"),
    ("display_name", "profile.name.display_name"),
    ("email", "profile.email"),
    ("phone", "profile.phone"),
    ("country_code", "employment.country_code"),
    ("work_country", "employment.work_country"),
    ("business_line", "employment.business_line"),
    ("profile_status", "metadata.profile_status"),
    ("department", "employment.department"),
    ("entity_id", "employment.entity_id"),
    ("entity_label", "__entity_label"),
    ("department_id", "employment.department_id"),
    ("department_label", "__department_label"),
    ("team_id", "employment.team_id"),
    ("team_label", "__team_label"),
    ("position", "employment.position"),
    ("manager_employee_id", "employment.manager_employee_id"),
    ("office_location", "employment.office_location"),
    ("assignment", "employment.assignment"),
    ("employment_type", "employment.employment_type"),
    ("status", "employment.status"),
    ("join_date", "employment.join_date"),
    ("probation_end_date", "employment.probation_end_date"),
    ("labor_contract_start_date", "employment.contract.start_date"),
    ("labor_contract_end_date", "employment.contract.end_date"),
    ("nationality", "profile.nationality"),
    ("japanese_level", "language_profile.japanese_level"),
    ("english_level", "language_profile.english_level"),
    ("primary_skill", "skills_profile.primary_skill"),
    ("secondary_skill", "skills_profile.secondary_skill"),
]

SENSITIVE_AUDIT_PATH_MARKERS = (
    "date_of_birth",
    "address",
    "emergency_contact",
    "email_p",
    "payroll",
    "salary",
    "bank",
    "residence_card_number",
    "passport_number",
    "storage_reference",
    "my_number",
    "documents",
    "visa_history",
    "employment_history.attachments",
    "dispatch_assignment_history.attachments",
    "attachments",
    "password",
    "password_secret",
    "secret_ref",
    "ciphertext",
    "nonce",
)

SECTION_CONFIG = {
    "payroll": {
        "title_key": "section.payroll",
        "field_paths": PAYROLL_FIELD_PATHS,
        "audit_action": "payroll_updated",
        "audit_section": "payroll",
        "route": "payroll",
        "edit_action_key": "action.edit_payroll",
    },
    "visa": {
        "title_key": "section.visa",
        "field_paths": VISA_FIELD_PATHS,
        "audit_action": "visa_updated",
        "audit_section": "visa",
        "route": "visa",
        "edit_action_key": "action.edit_visa",
    },
    "dispatch": {
        "title_key": "section.dispatch_compliance",
        "field_paths": DISPATCH_FIELD_PATHS,
        "audit_action": "dispatch_updated",
        "audit_section": "dispatch_compliance",
        "route": "dispatch",
        "edit_action_key": "action.edit_dispatch",
    },
    "skills": {
        "title_key": "section.skills_language",
        "field_paths": SKILLS_LANGUAGE_FIELD_PATHS,
        "audit_action": "skills_language_updated",
        "audit_section": "skills_language",
        "route": "skills",
        "edit_action_key": "action.edit_skills_language",
    },
    "documents": {
        "title_key": "section.documents",
        "field_paths": DOCUMENT_FIELD_PATHS,
        "audit_action": "documents_updated",
        "audit_section": "documents",
        "route": "documents",
        "edit_action_key": "action.edit_documents",
    },
}

EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NON_FOREIGN_NATIONALITIES = {"japan", "japanese", "日本", "日本国籍", "日本人"}


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
    with tmp_path.open("w", encoding="utf-8") as file:
        json.dump(records, file, ensure_ascii=False, indent=2)
        file.write("\n")
    tmp_path.replace(path)


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def h(value: Any) -> str:
    return escape(str(value or ""), quote=True)


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
    roles = set(str(role) for role in user.get("roles", []))
    role = str(user.get("role", ""))
    permissions = set(str(permission) for permission in user.get("permissions", []))
    return role == "system_admin" or "system_admin" in roles or "*" in permissions or permission_key in permissions


def has_required_module_access(user: dict[str, Any]) -> bool:
    return has_permission(user, REQUIRED_MODULE_PERMISSION)


def actor_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return DEFAULT_ACTOR
    for key in ("username", "email", "display_name", "user_id", "id"):
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return DEFAULT_ACTOR


def masterdata_api_get(session_id: str, path: str, query: dict[str, str] | None = None) -> tuple[Any, str | None]:
    if not session_id:
        return None, "validation.masterdata_unavailable"
    url = f"{MASTERDATA_INTERNAL_BASE_URL}{path}"
    if query:
        clean_query = {key: value for key, value in query.items() if value}
        if clean_query:
            url = f"{url}?{urlencode(clean_query)}"
    request = Request(url, headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"}, method="GET")
    try:
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8")), None
    except (OSError, URLError, json.JSONDecodeError):
        return None, "validation.masterdata_unavailable"


def masterdata_items_from_payload(data: Any, collection_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in (*collection_keys, "items", "results"):
        value = data.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    nested = data.get("data")
    if isinstance(nested, (list, dict)):
        return masterdata_items_from_payload(nested, collection_keys)
    return []


def fetch_masterdata_entities(session_id: str) -> tuple[list[dict[str, Any]], str | None]:
    data, error = masterdata_api_get(session_id, "/api/entities")
    if error:
        return [], error
    return masterdata_items_from_payload(data, ("entities",)), None


def fetch_masterdata_departments(session_id: str, entity_id: str = "") -> tuple[list[dict[str, Any]], str | None]:
    data, error = masterdata_api_get(session_id, "/api/departments", {"entity_id": entity_id})
    if error:
        return [], error
    return masterdata_items_from_payload(data, ("departments",)), None


def fetch_masterdata_teams(session_id: str, department_id: str = "") -> tuple[list[dict[str, Any]], str | None]:
    data, error = masterdata_api_get(session_id, "/api/teams", {"department_id": department_id})
    if error:
        return [], error
    return masterdata_items_from_payload(data, ("teams",)), None


def localized_master_name(record: dict[str, Any], name_prefix: str, code_field: str, lang: str) -> str:
    localized = str(record.get(f"{name_prefix}_{lang}", "")).strip()
    english = str(record.get(f"{name_prefix}_en", "")).strip()
    code = str(record.get(code_field, "")).strip()
    return localized or english or code


def masterdata_label(record: dict[str, Any], name_prefix: str, code_field: str, lang: str) -> str:
    if not record:
        return ""
    code = str(record.get(code_field, "")).strip()
    name = localized_master_name(record, name_prefix, code_field, lang)
    return f"{code} - {name}" if code and name and name != code else code or name


def masterdata_entity_lookup_by_code(session_id: str) -> tuple[dict[str, dict[str, Any]], str | None, list[str]]:
    entities, error = fetch_masterdata_entities(session_id)
    if error:
        return {}, error, []
    lookup: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for entity in entities:
        code = str(entity.get("entity_code", "")).strip()
        if not code:
            continue
        key = code.casefold()
        if key in lookup:
            duplicates.append(code)
        else:
            lookup[key] = entity
    return lookup, None, duplicates


def masterdata_department_lookup_by_code(session_id: str, entity_id: str) -> tuple[dict[str, dict[str, Any]], str | None, list[str]]:
    departments, error = fetch_masterdata_departments(session_id, entity_id)
    if error:
        return {}, error, []
    lookup: dict[str, dict[str, Any]] = {}
    duplicates: list[str] = []
    for department in departments:
        code = str(department.get("department_code", "")).strip()
        if not code:
            continue
        key = code.casefold()
        if key in lookup:
            duplicates.append(code)
        else:
            lookup[key] = department
    return lookup, None, duplicates


def empty_masterdata_context() -> dict[str, dict[str, str]]:
    return {"entities": {}, "departments": {}, "teams": {}}


def masterdata_context_for_employees(session_id: str, lang: str, employees: list[dict[str, Any]]) -> tuple[dict[str, dict[str, str]], str | None]:
    context = empty_masterdata_context()
    first_error: str | None = None

    entities, entity_error = fetch_masterdata_entities(session_id)
    if entity_error:
        first_error = entity_error
    entity_ids = {employment_entity_id(employee) for employee in employees if employment_entity_id(employee)}
    for entity in entities:
        entity_id = str(entity.get("entity_id", "")).strip()
        if entity_id:
            entity_ids.add(entity_id)
            context["entities"][entity_id] = masterdata_label(entity, "entity_name", "entity_code", lang) or entity_id

    department_ids = {employment_department_id(employee) for employee in employees if employment_department_id(employee)}
    for entity_id in sorted(entity_ids):
        departments, department_error = fetch_masterdata_departments(session_id, entity_id)
        if department_error and first_error is None:
            first_error = department_error
        for department in departments:
            department_id = str(department.get("department_id", "")).strip()
            if department_id:
                department_ids.add(department_id)
                context["departments"][department_id] = masterdata_label(department, "department_name", "department_code", lang) or department_id

    for department_id in sorted(department_ids):
        teams, team_error = fetch_masterdata_teams(session_id, department_id)
        if team_error and first_error is None:
            first_error = team_error
        for team in teams:
            team_id = str(team.get("team_id", "")).strip()
            if team_id:
                context["teams"][team_id] = masterdata_label(team, "team_name", "team_code", lang) or team_id

    return context, first_error


def masterdata_context_for_all_employees(session_id: str, lang: str) -> tuple[dict[str, dict[str, str]], str | None]:
    return masterdata_context_for_employees(session_id, lang, visible_employees(load_employees()))


def masterdata_context_label(context: dict[str, dict[str, str]] | None, record_type: str, record_id: str) -> str:
    record_id = str(record_id or "").strip()
    if not record_id:
        return ""
    if not context:
        return record_id
    return context.get(record_type, {}).get(record_id, record_id)


def employment_entity_display(employee: dict[str, Any], context: dict[str, dict[str, str]] | None = None) -> str:
    return masterdata_context_label(context, "entities", employment_entity_id(employee))


def employment_department_display(employee: dict[str, Any], context: dict[str, dict[str, str]] | None = None) -> str:
    return masterdata_context_label(context, "departments", employment_department_id(employee))


def employment_team_display(employee: dict[str, Any], context: dict[str, dict[str, str]] | None = None) -> str:
    return masterdata_context_label(context, "teams", employment_team_id(employee))


def display_employee_value(messages: dict[str, str], employee: dict[str, Any], path: str, context: dict[str, dict[str, str]] | None = None) -> str:
    if path == "employment.entity_id":
        return employment_entity_display(employee, context)
    if path == "employment.department_id":
        return employment_department_display(employee, context)
    if path == "employment.team_id":
        return employment_team_display(employee, context)
    return display_value(messages, path, get_nested(employee, path, ""))


def get_nested(record: dict[str, Any], path: str, default: Any = "") -> Any:
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def set_nested(record: dict[str, Any], path: str, value: Any) -> None:
    current = record
    parts = path.split(".")
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def default_employee() -> dict[str, Any]:
    timestamp = now_iso()
    return {
        "employee_id": "",
        "employee_number": "",
        "profile": {
            "name": {
                "display_name": "",
                "family_name": "",
                "given_name": "",
                "family_name_kana": "",
                "given_name_kana": "",
                "romaji_name": "",
            },
            "gender": "",
            "date_of_birth": "",
            "nationality": "",
            "address": {
                "postal_code": "",
                "prefecture": "",
                "city": "",
                "street": "",
                "building": "",
                "country": "Japan",
            },
            "email": "",
            "email_p": "",
            "phone": "",
            "emergency_contact": {
                "name": "",
                "relationship": "",
                "phone": "",
                "email": "",
            },
            "photo_path": "",
        },
        "employment": {
            "country_code": "",
            "legal_entity": "",
            "work_country": "",
            "business_line": "",
            "department": "",
            "join_date": "",
            "employment_type": "employee",
            "entity_id": "",
            "department_id": "",
            "team_id": "",
            "position": "",
            "manager_employee_id": "",
            "office_location": "",
            "assignment": "",
            "status": "active",
            "probation_end_date": "",
            "contract": {
                "start_date": "",
                "end_date": "",
            },
            "resignation": {
                "resignation_date": "",
                "last_working_date": "",
                "reason": "",
            },
        },
        "payroll": {
            "bank": {
                "bank_name": "",
                "branch_name": "",
                "swift_code": "",
                "account_type": "",
                "account_number": "",
                "account_holder": "",
            },
            "salary_type": "monthly",
            "payroll_currency": "SGD",
            "monthly_base_salary": "",
            "daily_wage": "",
            "hourly_wage": "",
            "salary_amount_yen": "",
            "transportation_allowance_yen": "",
            "bonus_eligible": False,
            "social_insurance_enrolled": False,
            "pension_enrolled": False,
            "employment_insurance_enrolled": False,
            "notes": "",
        },
        "visa": {
            "visa_type": "",
            "residence_status": "",
            "expiry_date": "",
            "residence_card_number": "",
            "passport_number": "",
            "passport_expiry_date": "",
            "renewal_reminder_enabled": False,
            "renewal_reminder_date": "",
            "notes": "",
        },
        "dispatch_compliance": {
            "client_name": "",
            "assignment_location": "",
            "dispatch_start_date": "",
            "dispatch_end_date": "",
            "contract_type": "",
            "work_description": "",
            "supervisor": {
                "name": "",
                "title": "",
                "phone": "",
                "email": "",
            },
            "notes": "",
        },
        "language_profile": {
            "japanese_level": "",
            "english_level": "",
            "native_languages": [],
            "additional_languages": [],
            "notes": "",
        },
        "skills_profile": {
            "primary_skill": "",
            "secondary_skill": "",
            "years_of_experience": "",
            "it_skills": [],
            "engineering_skills": [],
            "certifications": [],
            "industry_experience": [],
            "notes": "",
        },
        "documents": [],
        "employment_history": [],
        "visa_history": [],
        "dispatch_assignment_history": [],
        "metadata": {
            "created_at": timestamp,
            "created_by": DEFAULT_ACTOR,
            "updated_at": timestamp,
            "updated_by": DEFAULT_ACTOR,
            "deleted": False,
            "profile_status": "draft",
        },
    }


def normalize_employee(record: dict[str, Any]) -> dict[str, Any]:
    employee = default_employee()
    section_keys = {
        "profile",
        "employment",
        "payroll",
        "visa",
        "dispatch_compliance",
        "language_profile",
        "skills_profile",
        "documents",
        "employment_history",
        "visa_history",
        "dispatch_assignment_history",
        "metadata",
    }
    employee.update({key: value for key, value in record.items() if key not in section_keys})
    employee["employee_number"] = str(record.get("employee_number") or record.get("employee_id") or "").strip()
    for path in FIELD_PATHS:
        value = get_nested(record, path, None)
        if value is not None:
            if path in BOOLEAN_FIELD_PATHS:
                value = bool(value)
            elif path in LIST_FIELD_PATHS:
                value = normalize_tags(value)
            elif path == "documents":
                value = normalize_documents(value)
            elif path in HISTORY_FIELD_PATHS:
                history_type = history_type_for_array_key(path)
                value = normalize_history_records(history_type, value) if history_type else []
            set_nested(employee, path, value)
    metadata = record.get("metadata")
    if isinstance(metadata, dict):
        employee["metadata"].update(metadata)
    employee["metadata"]["deleted"] = bool(employee["metadata"].get("deleted", False))
    return employee


def load_employees() -> list[dict[str, Any]]:
    return [normalize_employee(record) for record in load_json_array(EMPLOYEES_PATH)]


def save_employees(employees: list[dict[str, Any]]) -> None:
    save_json_array(EMPLOYEES_PATH, employees)


def load_audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def load_onboarding_requests() -> list[dict[str, Any]]:
    return [normalize_onboarding_request(record) for record in load_json_array(ONBOARDING_REQUESTS_PATH)]


def save_onboarding_requests(records: list[dict[str, Any]]) -> None:
    save_json_array(ONBOARDING_REQUESTS_PATH, records)


def load_onboarding_submissions() -> list[dict[str, Any]]:
    return load_json_array(ONBOARDING_SUBMISSIONS_PATH)


def save_onboarding_submissions(records: list[dict[str, Any]]) -> None:
    save_json_array(ONBOARDING_SUBMISSIONS_PATH, records)


def load_onboarding_documents() -> list[dict[str, Any]]:
    return [normalize_onboarding_document(record) for record in load_json_array(ONBOARDING_DOCUMENTS_PATH)]


def save_onboarding_documents(records: list[dict[str, Any]]) -> None:
    save_json_array(ONBOARDING_DOCUMENTS_PATH, records)


def load_onboarding_signatures() -> list[dict[str, Any]]:
    return load_json_array(ONBOARDING_SIGNATURES_PATH)


def save_onboarding_signatures(records: list[dict[str, Any]]) -> None:
    save_json_array(ONBOARDING_SIGNATURES_PATH, records)


def load_onboarding_mynumber_access_logs() -> list[dict[str, Any]]:
    return load_json_array(ONBOARDING_MYNUMBER_ACCESS_LOGS_PATH)


def save_onboarding_mynumber_access_logs(records: list[dict[str, Any]]) -> None:
    save_json_array(ONBOARDING_MYNUMBER_ACCESS_LOGS_PATH, records)


def config_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def config_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default



def next_prefixed_id(records: list[dict[str, Any]], field: str, prefix: str, width: int = 4) -> str:
    max_number = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{{width},}})$")
    for record in records:
        match = pattern.fullmatch(str(record.get(field, "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-{max_number + 1:0{width}d}"


def next_onboarding_request_id(records: list[dict[str, Any]]) -> str:
    return next_prefixed_id(records, "onboarding_request_id", "ONB")


def next_onboarding_submission_id(records: list[dict[str, Any]]) -> str:
    return next_prefixed_id(records, "submission_id", "ONB-SUB")


def next_onboarding_document_id(records: list[dict[str, Any]]) -> str:
    return next_prefixed_id(records, "document_id", "ONB-DOC")


def next_onboarding_signature_id(records: list[dict[str, Any]]) -> str:
    return next_prefixed_id(records, "signature_id", "ONB-SIG")


def generate_onboarding_token() -> str:
    return secrets.token_urlsafe(32)


def hash_onboarding_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value or ""))
    except ValueError:
        return None


def onboarding_token_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(days=ONBOARDING_TOKEN_DAYS)).isoformat()


def onboarding_verification_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=ONBOARDING_VERIFICATION_CODE_MINUTES)).isoformat()


def onboarding_verification_lock_expiry() -> str:
    return (datetime.now(timezone.utc) + timedelta(minutes=ONBOARDING_VERIFICATION_LOCK_MINUTES)).isoformat()


def generate_onboarding_verification_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_onboarding_verification_code(request_id: str, code: str) -> str:
    payload = f"{request_id}:{str(code).strip()}".encode("utf-8")
    return hmac.new(ONBOARDING_VERIFICATION_SECRET.encode("utf-8"), payload, hashlib.sha256).hexdigest()


def hash_onboarding_verification_session(session_id: str) -> str:
    return hmac.new(ONBOARDING_VERIFICATION_SECRET.encode("utf-8"), session_id.encode("utf-8"), hashlib.sha256).hexdigest()


def onboarding_verification_locked(request: dict[str, str]) -> bool:
    locked_until = parse_iso_datetime(request.get("verification_locked_until", ""))
    return bool(locked_until and locked_until > datetime.now(timezone.utc))


def onboarding_verification_code_valid(request: dict[str, str]) -> bool:
    expiry = parse_iso_datetime(request.get("verification_code_expiry", ""))
    return bool(request.get("verification_code_hash") and expiry and expiry > datetime.now(timezone.utc) and not onboarding_verification_locked(request))


def onboarding_verification_attempts(request: dict[str, str]) -> int:
    try:
        return int(str(request.get("verification_attempts", "0") or "0"))
    except ValueError:
        return 0


def masked_email(address: str) -> str:
    value = str(address or "").strip()
    if "@" not in value:
        return value
    local, domain = value.split("@", 1)
    masked_local = local[:1] + "*" if len(local) <= 2 else local[:1] + "***" + local[-1:]
    return f"{masked_local}@{domain}"


def onboarding_verification_email_body(request: dict[str, str], code: str) -> str:
    return f"""TAC HR Admin

{request.get('candidate_name', '')} 様

Your TAC onboarding verification code is below.
入社手続きフォームの確認コードは以下です。
您的 TAC 入职表单验证码如下。

Verification code / 確認コード / 验证码:
{code}

This code expires at:
{request.get('verification_code_expiry', '')}

Please enter this code before filling the onboarding form. Do not forward this email.
入社手続きフォームに入力する前に、このコードを入力してください。このメールは転送しないでください。
填写入职表单前请输入此验证码。请勿转发此邮件。
"""


def onboarding_manual_invitation_email_body(request: dict[str, str], link: str, verification_code: str) -> str:
    return f"""TAC HR Admin

{request.get('candidate_name', '')} 様

Please complete your onboarding information from the secure link below.
以下の安全なリンクから入社手続き情報をご入力ください。
请通过以下安全链接填写入职资料。

Secure link / 安全なリンク / 安全链接:
{link}

Verification code / 確認コード / 验证码:
{verification_code}

Link expiry / 有効期限 / 链接有效期:
{request.get('token_expiry', '')}

Code expiry / コード有効期限 / 验证码有效期:
{request.get('verification_code_expiry', '')}

Please send this only to the registered candidate email: {request.get('candidate_email', '')}
登録済み候補者メールアドレスのみに送信してください。
请仅发送到已登记的候选人邮箱。
"""


def default_onboarding_request() -> dict[str, str]:
    return {
        "onboarding_request_id": "",
        "candidate_name": "",
        "candidate_email": "",
        "planned_start_date": "",
        "employment_type": "employee",
        "onboarding_category": "regular_employee",
        "status": "draft",
        "token_hash": "",
        "token_expiry": "",
        "token_created_at": "",
        "token_last_used_at": "",
        "created_by": "",
        "created_at": "",
        "updated_by": "",
        "updated_at": "",
        "sent_at": "",
        "email_sender": current_onboarding_email_sender(),
        "email_status": "not_sent",
        "email_draft_status": "not_prepared",
        "email_draft_prepared_by": "",
        "email_draft_prepared_at": "",
        "email_review_confirmed_by": "",
        "email_review_confirmed_at": "",
        "email_to": "",
        "email_cc_default": ONBOARDING_DEFAULT_CC_EMAIL,
        "email_cc_additional": "",
        "email_sent_to_snapshot": "",
        "email_sent_cc_snapshot": "",
        "email_subject_snapshot": "",
        "email_template_version": ONBOARDING_EMAIL_TEMPLATE_VERSION,
        "verification_code_hash": "",
        "verification_code_created_at": "",
        "verification_code_expiry": "",
        "verification_attempts": "0",
        "verification_locked_until": "",
        "verification_last_sent_at": "",
        "verification_delivery_status": "not_sent",
        "verification_verified_at": "",
        "verification_session_id_hash": "",
        "hr_notes": "",
        "review_notes": "",
        "imported_employee_id": "",
    }


def normalize_onboarding_request(record: dict[str, Any]) -> dict[str, str]:
    result = default_onboarding_request()
    for key in result:
        result[key] = str(record.get(key, result[key]) or "").strip()
    if result["status"] not in ONBOARDING_STATUSES:
        result["status"] = "draft"
    return result


def find_onboarding_request(records: list[dict[str, Any]], request_id: str) -> dict[str, str] | None:
    for record in records:
        normalized = normalize_onboarding_request(record)
        if normalized.get("onboarding_request_id") == request_id:
            return normalized
    return None


def onboarding_token_valid(request: dict[str, str]) -> bool:
    if request.get("status") in {"expired", "cancelled", "rejected", "imported_to_employee_master"}:
        return False
    expiry = parse_iso_datetime(request.get("token_expiry", ""))
    return bool(expiry and expiry > datetime.now(timezone.utc) and request.get("token_hash"))


def find_onboarding_request_by_token(token: str) -> dict[str, str] | None:
    token_hash = hash_onboarding_token(token)
    for request in load_onboarding_requests():
        stored_hash = request.get("token_hash", "")
        if stored_hash and hmac.compare_digest(stored_hash, token_hash) and onboarding_token_valid(request):
            return request
    return None


def default_onboarding_document() -> dict[str, str]:
    return {
        "document_id": "",
        "onboarding_request_id": "",
        "document_type": "other",
        "direction": "hr_to_candidate",
        "signing_mode": "no_signature_required",
        "status": "uploaded_by_hr",
        "title": "",
        "original_filename": "",
        "stored_filename": "",
        "storage_reference": "",
        "signed_stored_filename": "",
        "signed_storage_reference": "",
        "signed_pdf_stored_filename": "",
        "signed_pdf_storage_reference": "",
        "signed_pdf_content_type": "",
        "signed_pdf_file_size_bytes": "",
        "signed_pdf_created_at": "",
        "signed_pdf_status": "",
        "content_type": "",
        "file_size_bytes": "",
        "sha256_original": "",
        "sha256_signed": "",
        "sha256_signed_pdf": "",
        "uploaded_by": "",
        "uploaded_at": "",
        "notes": "",
    }


def normalize_onboarding_document(record: dict[str, Any]) -> dict[str, str]:
    result = default_onboarding_document()
    for key in result:
        result[key] = str(record.get(key, result[key]) or "").strip()
    if result["document_type"] not in ONBOARDING_DOCUMENT_TYPES:
        result["document_type"] = "other"
    if result["signing_mode"] not in ONBOARDING_SIGNING_MODES:
        result["signing_mode"] = "no_signature_required"
    if result["status"] not in ONBOARDING_DOCUMENT_STATUSES:
        result["status"] = "uploaded_by_hr"
    return result


def onboarding_documents_for_request(request_id: str) -> list[dict[str, str]]:
    return [doc for doc in load_onboarding_documents() if doc.get("onboarding_request_id") == request_id]


def find_onboarding_document(request_id: str, document_id: str) -> dict[str, str] | None:
    for doc in onboarding_documents_for_request(request_id):
        if doc.get("document_id") == document_id:
            return doc
    return None


def onboarding_candidate_uploaded_documents(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    return [doc for doc in documents if doc.get("direction") in {"candidate_to_hr", "manual_signed_upload"}]


def onboarding_candidate_document_complete(document: dict[str, str]) -> bool:
    if document.get("status") in {"rejected", "needs_resubmission"}:
        return False
    return bool(document.get("storage_reference") and document.get("status") in ONBOARDING_DOCUMENT_COMPLETE_STATUSES)


def onboarding_required_document_types_for_candidate(employee: dict[str, Any]) -> list[str]:
    required = list(ONBOARDING_CANDIDATE_REQUIRED_DOCUMENT_TYPES)
    if is_foreign_employee(employee):
        required.extend(ONBOARDING_FOREIGN_REQUIRED_DOCUMENT_TYPES)
    return list(dict.fromkeys(required))


def onboarding_candidate_document_matrix(employee: dict[str, Any], documents: list[dict[str, str]]) -> list[dict[str, Any]]:
    uploaded = onboarding_candidate_uploaded_documents(documents)
    rows: list[dict[str, Any]] = []
    for document_type in onboarding_required_document_types_for_candidate(employee):
        matches = [doc for doc in uploaded if doc.get("document_type") == document_type]
        complete = [doc for doc in matches if onboarding_candidate_document_complete(doc)]
        rows.append({
            "document_type": document_type,
            "documents": matches,
            "matched_count": len(matches),
            "is_complete": bool(complete),
            "status": "complete" if complete else "missing",
        })
    return rows


def onboarding_pending_required_hr_documents(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    pending: list[dict[str, str]] = []
    for document in documents:
        if document.get("direction") != "hr_to_candidate":
            continue
        if document.get("signing_mode") not in ONBOARDING_REQUIRED_SIGNING_MODES:
            continue
        if document.get("status") not in {"signed_by_candidate", "manual_signed_upload_received", "accepted", "archived_to_employee_master"}:
            pending.append(document)
    return pending


def candidate_onboarding_completion_errors(employee: dict[str, Any], documents: list[dict[str, str]], messages: dict[str, str]) -> list[str]:
    errors: list[str] = []
    missing = [row for row in onboarding_candidate_document_matrix(employee, documents) if not row["is_complete"]]
    if missing:
        missing_names = ", ".join(enum_label(messages, "onboarding_document_type", str(row["document_type"])) for row in missing)
        errors.append(t(messages, "onboarding.missing_required_documents_message").format(documents=missing_names))
    pending_signatures = onboarding_pending_required_hr_documents(documents)
    if pending_signatures:
        pending_names = ", ".join(doc.get("title") or enum_label(messages, "onboarding_document_type", doc.get("document_type", "")) for doc in pending_signatures)
        errors.append(t(messages, "onboarding.pending_required_signatures_message").format(documents=pending_names))
    return errors


def format_file_size_label(value: Any) -> str:
    try:
        size = int(str(value or "0"))
    except ValueError:
        return ""
    if size >= 1024 * 1024:
        return f"{size / (1024 * 1024):.1f} MB"
    if size >= 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size} B" if size else ""


def onboarding_bucket_for_direction(direction: str) -> str:
    if direction == "hr_to_candidate":
        return "hr"
    if direction == "manual_signed_upload":
        return "signed"
    if direction == "system_generated_signed":
        return "evidence"
    return "candidate"


def onboarding_safe_request_dir(request_id: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "", request_id)[:32] or "ONB"


def onboarding_document_sequence(documents: list[dict[str, str]], request_id: str) -> int:
    prefix = onboarding_safe_request_dir(request_id).replace("-", "")
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4}})\.[A-Za-z0-9]+$")
    max_sequence = 0
    for doc in documents:
        for key in ("stored_filename", "signed_stored_filename", "signed_pdf_stored_filename"):
            match = pattern.fullmatch(str(doc.get(key, "")))
            if match:
                max_sequence = max(max_sequence, int(match.group(1)))
    return max_sequence + 1


def build_onboarding_stored_filename(request_id: str, sequence: int, extension: str) -> str:
    prefix = onboarding_safe_request_dir(request_id).replace("-", "")
    return f"{prefix}-{sequence:04d}{extension}"


def onboarding_relative_path(request_id: str, bucket: str, stored_filename: str) -> str:
    return f"{ONBOARDING_DOCS_RELATIVE_DIR}/{onboarding_safe_request_dir(request_id)}/{bucket}/{stored_filename}"


def onboarding_document_path(document: dict[str, str], signed: bool = False, variant: str = "original") -> Path | None:
    if signed and variant == "original":
        variant = "evidence"
    if variant == "evidence":
        reference_key = "signed_storage_reference"
        filename_key = "signed_stored_filename"
        fallback_bucket = "evidence"
    elif variant == "signed_pdf":
        reference_key = "signed_pdf_storage_reference"
        filename_key = "signed_pdf_stored_filename"
        fallback_bucket = "signed_pdf"
    else:
        reference_key = "storage_reference"
        filename_key = "stored_filename"
        fallback_bucket = onboarding_bucket_for_direction(str(document.get("direction", "")))
    storage_reference = str(document.get(reference_key, "") or "").replace("\\", "/")
    stored_filename = str(document.get(filename_key, "") or Path(storage_reference).name).strip()
    request_id = str(document.get("onboarding_request_id", "")).strip()
    root = ONBOARDING_DOCS_DIR.resolve()
    if storage_reference.startswith(f"{ONBOARDING_DOCS_RELATIVE_DIR}/"):
        relative_part = storage_reference[len(ONBOARDING_DOCS_RELATIVE_DIR) + 1:]
        resolved = (ONBOARDING_DOCS_DIR / relative_part).resolve()
        if root not in resolved.parents:
            return None
        if stored_filename and resolved.name != stored_filename:
            return None
        return resolved
    if not stored_filename or not request_id:
        return None
    bucket_root = (ONBOARDING_DOCS_DIR / onboarding_safe_request_dir(request_id) / fallback_bucket).resolve()
    resolved = (bucket_root / stored_filename).resolve()
    if resolved.parent != bucket_root or root not in resolved.parents:
        return None
    return resolved


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()



def default_onboarding_email_settings(error: str = "") -> dict[str, Any]:
    sender_display_name = "TAC HR Admin"
    sender_email = ONBOARDING_EMAIL_SENDER
    return {
        "enabled": False,
        "sender_display_name": sender_display_name,
        "sender_email": sender_email,
        "sender_header": formataddr((sender_display_name, sender_email)) if sender_display_name else sender_email,
        "reply_to_email": ONBOARDING_EMAIL_REPLY_TO,
        "hr_notification_email": ONBOARDING_HR_NOTIFICATION_EMAIL,
        "department_manager_cc_emails": [],
        "smtp_host": ONBOARDING_SMTP_HOST,
        "smtp_port": ONBOARDING_SMTP_PORT,
        "smtp_username": ONBOARDING_SMTP_USERNAME,
        "smtp_password": "",
        "smtp_use_tls": ONBOARDING_SMTP_USE_TLS,
        "smtp_use_ssl": ONBOARDING_SMTP_PORT == 465,
        "smtp_timeout_seconds": 15,
        "settings_error": error,
        "password_error": error,
        "secret_status": "missing",
        "source": "masterdata",
    }


def normalize_email_list(value: Any, max_count: int = 3) -> list[str]:
    raw_items: list[str]
    if isinstance(value, list):
        raw_items = [str(item or "") for item in value]
    else:
        raw_items = re.split(r"[,;\n]", str(value or ""))
    emails: list[str] = []
    seen: set[str] = set()
    for item in raw_items:
        email = str(item or "").strip()
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


def onboarding_invitation_email_subject(request: dict[str, str]) -> str:
    candidate_name = str(request.get("candidate_name", "") or "").strip()
    return f"TAC onboarding request: {candidate_name}" if candidate_name else "TAC onboarding request"


def onboarding_link_for_token(token: str, lang: str) -> str:
    return f"{APP_BASE_URL}{url_with_lang('/onboarding/token/' + quote(token), lang)}"


def onboarding_request_is_dispatch(request: dict[str, str]) -> bool:
    category = str(request.get("onboarding_category", "") or "").strip().lower()
    return request.get("employment_type") == "dispatch" or category in {"dispatch", "dispatch_employee", "dispatched", "haken", "haken_employee"}


def onboarding_hr_documents(documents: list[dict[str, str]]) -> list[dict[str, str]]:
    return [doc for doc in documents if doc.get("direction") == "hr_to_candidate"]


def onboarding_public_url_readiness_items(messages: dict[str, str]) -> list[tuple[bool, str]]:
    parsed = urlparse(APP_BASE_URL)
    host = (parsed.hostname or "").lower()
    return [
        (parsed.scheme == "https", t(messages, "onboarding.readiness_public_url_https").format(url=APP_BASE_URL)),
        (host not in PUBLIC_LINK_LOCAL_HOSTS, t(messages, "onboarding.readiness_public_url_host").format(host=host or APP_BASE_URL)),
        (ONBOARDING_VERIFICATION_SECRET_CONFIGURED, t(messages, "onboarding.readiness_verification_secret")),
        (bool(MASTERDATA_INTERNAL_API_TOKEN), t(messages, "onboarding.readiness_masterdata_token")),
    ]


def onboarding_readiness_items(request: dict[str, str], documents: list[dict[str, str]], messages: dict[str, str]) -> list[tuple[bool, str]]:
    items = onboarding_public_url_readiness_items(messages)
    candidate_email = str(request.get("candidate_email", "") or "").strip()
    items.append((bool(candidate_email and EMAIL_PATTERN.fullmatch(candidate_email)), t(messages, "onboarding.readiness_candidate_email")))
    hr_docs = onboarding_hr_documents(documents)
    if onboarding_request_is_dispatch(request):
        present_types = {doc.get("document_type", "") for doc in hr_docs}
        for document_type in ONBOARDING_REQUIRED_DISPATCH_DOCUMENT_TYPES:
            items.append((document_type in present_types, t(messages, "onboarding.readiness_dispatch_document").format(document=enum_label(messages, "onboarding_document_type", document_type))))
    has_signature_document = any(doc.get("signing_mode") in ONBOARDING_SIGNATURE_CAPABLE_MODES for doc in hr_docs)
    items.append((has_signature_document, t(messages, "onboarding.readiness_signature_document")))
    if request.get("token_hash") and not onboarding_token_valid(request):
        items.append((False, t(messages, "onboarding.readiness_token_valid")))
    return items


def onboarding_readiness_warnings(request: dict[str, str], documents: list[dict[str, str]], messages: dict[str, str]) -> list[str]:
    return [text for ok, text in onboarding_readiness_items(request, documents, messages) if not ok]


def onboarding_token_from_link(link: str) -> str:
    parsed = urlparse(str(link or "").strip())
    parts = [part for part in parsed.path.split("/") if part]
    if len(parts) >= 3 and parts[0] == "onboarding" and parts[1] == "token":
        return unquote(parts[2])
    return ""


def validate_onboarding_additional_cc(raw_items: list[str], candidate_email: str, messages: dict[str, str]) -> tuple[list[str], list[str]]:
    emails: list[str] = []
    errors: list[str] = []
    blocked = {ONBOARDING_DEFAULT_CC_EMAIL.lower(), str(candidate_email or "").strip().lower()}
    seen = set(blocked)
    for raw in raw_items[:3]:
        email = str(raw or "").strip()
        if not email:
            continue
        if not EMAIL_PATTERN.fullmatch(email):
            errors.append(t(messages, "onboarding.email_cc_invalid").format(email=email))
            continue
        key = email.lower()
        if key in seen:
            errors.append(t(messages, "onboarding.email_cc_duplicate").format(email=email))
            continue
        seen.add(key)
        emails.append(email)
    return emails, errors


def onboarding_email_cc_list(additional_cc: list[str]) -> list[str]:
    return normalize_email_list([ONBOARDING_DEFAULT_CC_EMAIL] + additional_cc, 4)


def fetch_masterdata_outbound_email_settings() -> tuple[dict[str, Any] | None, str]:
    if not MASTERDATA_INTERNAL_API_TOKEN:
        return None, "masterdata_token_missing"
    request = Request(
        f"{MASTERDATA_INTERNAL_BASE_URL}/api/master-data/system-parameters/outbound-email-onboarding",
        headers={"X-TACAI-Internal-Token": MASTERDATA_INTERNAL_API_TOKEN},
        method="GET",
    )
    try:
        with urlopen(request, timeout=MASTERDATA_API_TIMEOUT_SECONDS) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read().decode("utf-8"))
        except (OSError, json.JSONDecodeError):
            return None, exc.__class__.__name__
        return None, str(payload.get("error", exc.__class__.__name__)) if isinstance(payload, dict) else exc.__class__.__name__
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return None, exc.__class__.__name__
    if not isinstance(payload, dict) or not payload.get("ok"):
        return None, str(payload.get("error", "masterdata_not_configured")) if isinstance(payload, dict) else "masterdata_invalid_response"
    return payload, ""


def onboarding_email_settings() -> dict[str, Any]:
    payload, error = fetch_masterdata_outbound_email_settings()
    if not payload:
        return default_onboarding_email_settings(error)
    sender_email = str(payload.get("sender_email", ONBOARDING_EMAIL_SENDER) or ONBOARDING_EMAIL_SENDER).strip()
    sender_display_name = str(payload.get("sender_display_name", "TAC HR Admin") or "TAC HR Admin").strip()
    return {
        "enabled": config_bool(payload.get("enabled", True), True),
        "sender_display_name": sender_display_name,
        "sender_email": sender_email,
        "sender_header": formataddr((sender_display_name, sender_email)) if sender_display_name else sender_email,
        "reply_to_email": str(payload.get("reply_to_email", ONBOARDING_EMAIL_REPLY_TO) or ONBOARDING_EMAIL_REPLY_TO).strip(),
        "hr_notification_email": str(payload.get("hr_notification_email", ONBOARDING_HR_NOTIFICATION_EMAIL) or ONBOARDING_HR_NOTIFICATION_EMAIL).strip(),
        "department_manager_cc_emails": normalize_email_list(payload.get("department_manager_cc_emails", []), 3),
        "smtp_host": str(payload.get("smtp_host") or "").strip(),
        "smtp_port": config_int(payload.get("smtp_port", ONBOARDING_SMTP_PORT), ONBOARDING_SMTP_PORT),
        "smtp_username": str(payload.get("smtp_username") or "").strip(),
        "smtp_password": str(payload.get("smtp_password") or ""),
        "smtp_use_tls": config_bool(payload.get("smtp_use_tls", ONBOARDING_SMTP_USE_TLS), ONBOARDING_SMTP_USE_TLS),
        "smtp_use_ssl": config_bool(payload.get("smtp_use_ssl", False), False),
        "smtp_timeout_seconds": config_int(payload.get("smtp_timeout_seconds", 15), 15),
        "settings_error": "",
        "password_error": "",
        "secret_status": str(payload.get("secret_status", "") or ""),
        "source": "masterdata",
    }


def current_onboarding_email_sender() -> str:
    return str(onboarding_email_settings().get("sender_email", ONBOARDING_EMAIL_SENDER) or ONBOARDING_EMAIL_SENDER)


def current_hr_notification_email() -> str:
    return str(onboarding_email_settings().get("hr_notification_email", ONBOARDING_HR_NOTIFICATION_EMAIL) or ONBOARDING_HR_NOTIFICATION_EMAIL)


def smtp_configured() -> bool:
    settings = onboarding_email_settings()
    return bool(
        settings.get("enabled")
        and settings.get("smtp_host")
        and settings.get("smtp_username")
        and settings.get("smtp_password")
        and settings.get("sender_email")
    )


def send_onboarding_email(to_address: str, subject: str, body: str, cc_addresses: list[str] | None = None) -> tuple[bool, str]:
    settings = onboarding_email_settings()
    if settings.get("settings_error"):
        return False, str(settings.get("settings_error"))
    if not settings.get("enabled"):
        return False, "disabled"
    if settings.get("password_error"):
        return False, str(settings.get("password_error"))
    if not (settings.get("smtp_host") and settings.get("smtp_username") and settings.get("smtp_password") and settings.get("sender_email")):
        return False, "not_configured"
    recipient = str(to_address or "").strip()
    if not recipient or not EMAIL_PATTERN.fullmatch(recipient):
        return False, "invalid_recipient"
    cc_list = [email for email in normalize_email_list(cc_addresses or [], 4) if EMAIL_PATTERN.fullmatch(email)]
    message = EmailMessage()
    message["From"] = str(settings.get("sender_header") or settings.get("sender_email"))
    message["To"] = recipient
    if cc_list:
        message["Cc"] = ", ".join(cc_list)
    message["Subject"] = subject
    if settings.get("reply_to_email"):
        message["Reply-To"] = str(settings.get("reply_to_email"))
    message.set_content(body)
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


def onboarding_invitation_email_body(request: dict[str, str], link: str) -> str:
    return f"""TAC HR Admin

{request.get('candidate_name', '')} 様

Please complete your onboarding information from the secure link below.
以下の安全なリンクから入社手続き情報をご入力ください。
请通过以下安全链接填写入职资料。

{link}

Link expiry / 有効期限 / 链接有效期:
{request.get('token_expiry', '')}

A separate verification code email will be sent to your registered email address. Enter that code after opening the link.
確認コードは登録済みメールアドレスへ別送されます。リンクを開いた後、そのコードを入力してください。
验证码将通过另一封邮件发送到你的登记邮箱。打开链接后请输入该验证码。

Please do not forward this link. If you have questions, contact TAC HR.
このリンクは転送しないでください。不明点はTAC HRまでご連絡ください。
请勿转发此链接。如有问题请联系 TAC HR。
"""


def onboarding_completion_email_body(request: dict[str, str]) -> str:
    return f"""Onboarding submission completed.

Request ID: {request.get('onboarding_request_id', '')}
Candidate: {request.get('candidate_name', '')}
Candidate email: {request.get('candidate_email', '')}
Submitted at: {now_iso()}

Please review this onboarding package in EmployeeAdmin.
"""


def onboarding_return_email_body(request: dict[str, str], review_notes: str, link: str) -> str:
    return f"""TAC HR Admin

{request.get('candidate_name', '')} 様

Your onboarding package was returned by HR for correction.
入社手続き内容について、HRから修正依頼があります。
您的入职资料已由 HR 退回修改。

Correction notes / 修正内容 / 修改说明:
{review_notes or 'Please review the onboarding form and documents again.'}

Secure link / 安全なリンク / 安全链接:
{link}

Link expiry / 有効期限 / 链接有效期:
{request.get('token_expiry', '')}

Please do not forward this link. If you have questions, contact TAC HR.
このリンクは転送しないでください。不明点はTAC HRまでご連絡ください。
请勿转发此链接。如有问题请联系 TAC HR。
"""


def onboarding_evidence_filename(request_id: str, document_id: str) -> str:
    safe_doc = re.sub(r"[^A-Za-z0-9_-]", "", document_id)[:40] or "DOC"
    return f"{onboarding_safe_request_dir(request_id)}-{safe_doc}-signature.html"


def write_onboarding_signature_evidence(request: dict[str, str], document: dict[str, str], signer_name: str, signer_email: str, signature_data: str, user_agent: str) -> tuple[str, str, str, str]:
    request_id = request.get("onboarding_request_id", "")
    filename = onboarding_evidence_filename(request_id, document.get("document_id", ""))
    evidence_dir = ONBOARDING_DOCS_DIR / onboarding_safe_request_dir(request_id) / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    path = (evidence_dir / filename).resolve()
    if path.parent != evidence_dir.resolve():
        raise ValueError("Invalid evidence destination")
    original_path = onboarding_document_path(document)
    before_hash = document.get("sha256_original", "")
    if original_path and original_path.is_file():
        before_hash = sha256_bytes(original_path.read_bytes())
    signed_at = now_iso()
    body = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>Onboarding Signature Evidence</title></head>
<body>
<h1>Onboarding Signature Evidence</h1>
<p>Request ID: {h(request_id)}</p>
<p>Document ID: {h(document.get('document_id', ''))}</p>
<p>Document Type: {h(document.get('document_type', ''))}</p>
<p>Signer Name: {h(signer_name)}</p>
<p>Signer Email: {h(signer_email)}</p>
<p>Signed At: {h(signed_at)}</p>
<p>User Agent: {h(user_agent)}</p>
<p>Document SHA-256 Before Signature: {h(before_hash)}</p>
<p>Evidence SHA-256: pending until file write</p>
<h2>Drawn Signature</h2>
<img src=\"{h(signature_data)}\" alt=\"Drawn signature\" style=\"max-width:420px;border:1px solid #ccc;padding:8px;\">
</body></html>"""
    path.write_text(body, encoding="utf-8")
    evidence_hash = sha256_bytes(path.read_bytes())
    return filename, before_hash, evidence_hash, signed_at


def pdf_stamping_available() -> tuple[bool, str]:
    try:
        import pypdf  # noqa: F401
        import reportlab  # noqa: F401
    except ImportError:
        return False, "missing_dependency"
    return True, "available"


def onboarding_signed_pdf_filename(request_id: str, document_id: str) -> str:
    safe_doc = re.sub(r"[^A-Za-z0-9_-]", "", document_id)[:40] or "DOC"
    return f"{onboarding_safe_request_dir(request_id)}-{safe_doc}-signed.pdf"


def write_onboarding_signed_pdf(
    request: dict[str, str],
    document: dict[str, str],
    signer_name: str,
    signer_email: str,
    signature_png: bytes,
    signed_at: str,
    before_hash: str,
    evidence_hash: str,
) -> dict[str, str]:
    original_path = onboarding_document_path(document)
    if not original_path or not original_path.is_file():
        return {"status": "failed_source_missing"}
    original_name = (document.get("original_filename") or document.get("stored_filename") or original_path.name).lower()
    if original_path.suffix.lower() != ".pdf" and not original_name.endswith(".pdf") and document.get("content_type") != "application/pdf":
        return {"status": "failed_source_not_pdf"}
    available, reason = pdf_stamping_available()
    if not available:
        return {"status": "failed_dependency_missing", "reason": reason}
    try:
        from pypdf import PdfReader, PdfWriter
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.utils import ImageReader
        from reportlab.pdfgen import canvas
    except ImportError:
        return {"status": "failed_dependency_missing", "reason": "missing_dependency"}

    request_id = request.get("onboarding_request_id", "")
    stored_filename = onboarding_signed_pdf_filename(request_id, document.get("document_id", ""))
    signed_dir = ONBOARDING_DOCS_DIR / onboarding_safe_request_dir(request_id) / "signed_pdf"
    signed_dir.mkdir(parents=True, exist_ok=True)
    destination = (signed_dir / stored_filename).resolve()
    if destination.parent != signed_dir.resolve():
        raise ValueError("Invalid signed PDF destination")

    try:
        packet = io.BytesIO()
        page_width, page_height = A4
        cert = canvas.Canvas(packet, pagesize=A4)
        cert.setTitle("Onboarding Signature Certificate")
        cert.setFont("Helvetica-Bold", 18)
        cert.drawString(48, page_height - 64, "Signature Certificate")
        cert.setFont("Helvetica", 10)
        y = page_height - 100
        rows = [
            ("Request ID", request_id),
            ("Document ID", document.get("document_id", "")),
            ("Document Type", document.get("document_type", "")),
            ("Signer Name", signer_name),
            ("Signer Email", signer_email),
            ("Signed At", signed_at),
            ("Original PDF SHA-256", before_hash),
            ("Evidence SHA-256", evidence_hash),
        ]
        for label, value in rows:
            cert.setFont("Helvetica-Bold", 9)
            cert.drawString(48, y, f"{label}:")
            cert.setFont("Helvetica", 9)
            cert.drawString(170, y, str(value or "")[:95])
            y -= 22
        cert.setFont("Helvetica-Bold", 11)
        cert.drawString(48, y - 10, "Drawn Signature")
        image = ImageReader(io.BytesIO(signature_png))
        cert.rect(48, y - 150, 300, 110, stroke=1, fill=0)
        cert.drawImage(image, 58, y - 140, width=280, height=90, preserveAspectRatio=True, mask="auto")
        cert.setFont("Helvetica", 8)
        cert.drawString(48, 48, "Generated by TAC EmployeeAdmin local onboarding workflow. Original PDF is preserved separately.")
        cert.showPage()
        cert.save()
        packet.seek(0)

        reader = PdfReader(str(original_path))
        cert_reader = PdfReader(packet)
        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        writer.add_page(cert_reader.pages[0])
        with destination.open("wb") as file:
            writer.write(file)
    except Exception:
        try:
            destination.unlink()
        except FileNotFoundError:
            pass
        return {"status": "failed_generation_error"}

    content = destination.read_bytes()
    return {
        "status": "created",
        "stored_filename": stored_filename,
        "storage_reference": onboarding_relative_path(request_id, "signed_pdf", stored_filename),
        "content_type": "application/pdf",
        "file_size_bytes": str(len(content)),
        "sha256": sha256_bytes(content),
        "created_at": now_iso(),
    }


def uploaded_onboarding_documents_from_parts(
    request_id: str,
    form: dict[str, str],
    uploads: list[dict[str, Any]],
    direction: str,
    actor: str,
) -> tuple[list[dict[str, str]], list[tuple[Path, bytes]]]:
    existing = load_onboarding_documents()
    request_docs = [doc for doc in existing if doc.get("onboarding_request_id") == request_id]
    sequence = onboarding_document_sequence(request_docs, request_id)
    bucket = onboarding_bucket_for_direction(direction)
    documents: list[dict[str, str]] = []
    writes: list[tuple[Path, bytes]] = []
    for upload in uploads:
        original_filename = safe_original_filename(str(upload.get("original_filename", "")))
        content = upload.get("content", b"")
        extension = upload_extension(original_filename)
        stored_filename = build_onboarding_stored_filename(request_id, sequence, extension)
        sequence += 1
        doc = default_onboarding_document()
        doc["document_id"] = next_onboarding_document_id(existing + documents)
        doc["onboarding_request_id"] = request_id
        doc["document_type"] = str(form.get("upload_document_type", "other") or "other").strip()
        if doc["document_type"] not in ONBOARDING_DOCUMENT_TYPES:
            doc["document_type"] = "other"
        doc["direction"] = direction
        doc["signing_mode"] = str(form.get("upload_signing_mode", "no_signature_required") or "no_signature_required").strip()
        if doc["signing_mode"] not in ONBOARDING_SIGNING_MODES:
            doc["signing_mode"] = "no_signature_required"
        doc["status"] = "uploaded_by_hr" if direction == "hr_to_candidate" else "submitted_by_candidate"
        if direction == "manual_signed_upload":
            doc["status"] = "manual_signed_upload_received"
        doc["title"] = str(form.get("upload_title", "") or title_from_filename(original_filename)).strip()
        doc["original_filename"] = original_filename
        doc["stored_filename"] = stored_filename
        doc["storage_reference"] = onboarding_relative_path(request_id, bucket, stored_filename)
        doc["content_type"] = str(upload.get("content_type", "application/octet-stream") or "application/octet-stream")[:160]
        doc["file_size_bytes"] = str(len(content))
        doc["sha256_original"] = sha256_bytes(content)
        doc["uploaded_by"] = actor
        doc["uploaded_at"] = now_iso()
        doc["notes"] = str(form.get("upload_notes", "") or "").strip()
        documents.append(normalize_onboarding_document(doc))
        writes.append((ONBOARDING_DOCS_DIR / onboarding_safe_request_dir(request_id) / bucket / stored_filename, content))
    return documents, writes


def write_onboarding_uploaded_files(file_writes: list[tuple[Path, bytes]]) -> list[Path]:
    root = ONBOARDING_DOCS_DIR.resolve()
    written: list[Path] = []
    try:
        for destination, content in file_writes:
            resolved = destination.resolve()
            if root not in resolved.parents:
                raise ValueError("Invalid onboarding upload destination")
            resolved.parent.mkdir(parents=True, exist_ok=True)
            with resolved.open("xb") as file:
                file.write(content)
            written.append(resolved)
    except Exception:
        for written_path in written:
            try:
                written_path.unlink()
            except FileNotFoundError:
                pass
        raise
    return written


def append_module_audit_log(
    module: str,
    record_id: str,
    action: str,
    fields: list[str],
    summary: str,
    before_record: dict[str, Any] | None = None,
    after_record: dict[str, Any] | None = None,
    actor: str = DEFAULT_ACTOR,
) -> None:
    audit_logs = load_audit_logs()
    timestamp = now_iso()
    audit_logs.append({
        "audit_id": next_audit_id(audit_logs),
        "employee_id": record_id,
        "actor": actor,
        "action": action,
        "section": module,
        "changed_fields": fields,
        "summary": summary,
        "created_at": timestamp,
        "module": module,
        "record_id": record_id,
        "user": actor,
        "timestamp": timestamp,
        "before_value": audit_field_snapshot(before_record, fields),
        "after_value": audit_field_snapshot(after_record, fields),
    })
    save_json_array(AUDIT_LOGS_PATH, audit_logs)


def onboarding_submission_for_request(request_id: str) -> dict[str, Any] | None:
    submissions = load_onboarding_submissions()
    matches = [record for record in submissions if str(record.get("onboarding_request_id", "")) == request_id]
    if not matches:
        return None
    return matches[-1]


def onboarding_employee_from_form(form: dict[str, str], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    employee = copy.deepcopy(existing) if existing else default_employee()
    candidate_paths = [
        "profile.name.display_name", "profile.name.family_name", "profile.name.given_name", "profile.name.family_name_kana", "profile.name.given_name_kana", "profile.name.romaji_name",
        "profile.gender", "profile.date_of_birth", "profile.nationality", "profile.address.postal_code", "profile.address.prefecture", "profile.address.city", "profile.address.street", "profile.address.building",
        "profile.email_p", "profile.phone", "profile.emergency_contact.name", "profile.emergency_contact.relationship", "profile.emergency_contact.phone", "profile.emergency_contact.email",
        "employment.join_date", "employment.employment_type", "employment.position", "employment.office_location", "employment.assignment", "employment.probation_end_date",
        "payroll.bank.bank_name", "payroll.bank.branch_name", "payroll.bank.swift_code", "payroll.bank.account_type", "payroll.bank.account_number", "payroll.bank.account_holder", "payroll.transportation_allowance_yen",
        "visa.visa_type", "visa.residence_status", "visa.expiry_date", "visa.residence_card_number", "visa.passport_number", "visa.passport_expiry_date",
        "language_profile.japanese_level", "language_profile.english_level", "language_profile.native_languages", "language_profile.additional_languages", "skills_profile.primary_skill", "skills_profile.secondary_skill", "skills_profile.it_skills", "skills_profile.certifications",
    ]
    apply_form_fields(employee, form, candidate_paths)
    return employee


def save_onboarding_submission_form(request_id: str, form: dict[str, str], status: str) -> dict[str, Any]:
    submissions = load_onboarding_submissions()
    submission = onboarding_submission_for_request(request_id)
    if not submission:
        submission = {"submission_id": next_onboarding_submission_id(submissions), "onboarding_request_id": request_id, "status": "draft", "form_data": {}, "submitted_at": "", "reviewed_by": "", "reviewed_at": "", "review_notes": ""}
        submissions.append(submission)
    employee_data = onboarding_employee_from_form(form)
    submission["form_data"] = employee_data
    submission["status"] = status
    if status == "pending_hr_review":
        submission["submitted_at"] = now_iso()
    save_onboarding_submissions(submissions)
    return submission


def update_onboarding_request(request_id: str, updates: dict[str, str]) -> dict[str, str] | None:
    requests = load_onboarding_requests()
    updated: dict[str, str] | None = None
    for index, request in enumerate(requests):
        if request.get("onboarding_request_id") == request_id:
            before = copy.deepcopy(request)
            request.update({key: str(value) for key, value in updates.items()})
            requests[index] = normalize_onboarding_request(request)
            updated = requests[index]
            break
    if updated:
        save_onboarding_requests(requests)
    return updated

def next_employee_id(employees: list[dict[str, Any]]) -> str:
    max_number = 0
    for employee in employees:
        employee_id = str(employee.get("employee_id", ""))
        match = re.fullmatch(r"EMP-(\d{4,})", employee_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"EMP-{max_number + 1:04d}"


def next_audit_id(audit_logs: list[dict[str, Any]]) -> str:
    max_number = 0
    for audit in audit_logs:
        audit_id = str(audit.get("audit_id", ""))
        match = re.fullmatch(r"AUD-(\d{6,})", audit_id)
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"AUD-{max_number + 1:06d}"


def find_employee(employees: list[dict[str, Any]], employee_id: str) -> dict[str, Any] | None:
    for employee in employees:
        if employee.get("employee_id") == employee_id:
            return employee
    return None


def visible_employees(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [employee for employee in employees if not get_nested(employee, "metadata.deleted", False)]


def get_employee_number(employee: dict[str, Any]) -> str:
    return str(employee.get("employee_number") or employee.get("employee_id") or "").strip()


def employment_entity_id(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.entity_id", "")).strip()


def employment_department_id(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.department_id", "")).strip()


def employment_team_id(employee: dict[str, Any]) -> str:
    return str(get_nested(employee, "employment.team_id", "")).strip()


def normalize_country_code(value: Any) -> str:
    country_code = str(value or "").strip().upper()
    return country_code if country_code in COUNTRY_CODES else ""


def employment_country_code(employee: dict[str, Any]) -> str:
    return normalize_country_code(get_nested(employee, "employment.country_code", ""))


def timesheet_employee_payload(employee: dict[str, Any], context: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    return {
        "employee_id": str(employee.get("employee_id", "")),
        "employee_number": get_employee_number(employee),
        "employee_no": get_employee_number(employee),
        "display_name": str(get_nested(employee, "profile.name.display_name", "")),
        "email": str(get_nested(employee, "profile.email", "")),
        "entity_id": employment_entity_id(employee),
        "entity_label": employment_entity_display(employee, context),
        "entity_name": employment_entity_display(employee, context),
        "department_id": employment_department_id(employee),
        "department_label": employment_department_display(employee, context),
        "team_id": employment_team_id(employee),
        "team_label": employment_team_display(employee, context),
        "department": employment_department_display(employee, context),
        "employment_type": str(get_nested(employee, "employment.employment_type", "")),
        "status": str(get_nested(employee, "employment.status", "")),
    }


def timesheet_employee_api_payload(session_id: str = "", lang: str = DEFAULT_LANG) -> dict[str, Any]:
    source_employees = visible_employees(load_employees())
    context, _error = masterdata_context_for_employees(session_id, lang, source_employees) if session_id else (empty_masterdata_context(), None)
    employees = []
    for employee in source_employees:
        status = str(get_nested(employee, "employment.status", "")).strip().lower()
        if status and status not in TIMESHEET_SELECTABLE_EMPLOYMENT_STATUSES:
            continue
        payload = timesheet_employee_payload(employee, context)
        if payload["employee_number"]:
            employees.append(payload)
    employees.sort(key=lambda item: (str(item.get("employee_number", "")), str(item.get("display_name", ""))))
    return {
        "source": "TAC-employeeadmin",
        "generated_at": now_iso(),
        "employees": employees,
    }


def useradmin_employee_api_payload(query: dict[str, list[str]], session_id: str = "", lang: str = DEFAULT_LANG) -> dict[str, Any]:
    source_employees = visible_employees(load_employees())
    context, _error = masterdata_context_for_employees(session_id, lang, source_employees) if session_id else (empty_masterdata_context(), None)
    entity_filter = str(query.get("entity_id", [""])[0]).strip()
    country_filter = normalize_country_code(query.get("country_code", [""])[0])
    q = str(query.get("q", [""])[0]).strip().casefold()
    employees = []
    for employee in source_employees:
        status = str(get_nested(employee, "employment.status", "")).strip().lower()
        if status and status not in TIMESHEET_SELECTABLE_EMPLOYMENT_STATUSES:
            continue
        payload = timesheet_employee_payload(employee, context)
        employee_country = employment_country_code(employee)
        work_country = str(get_nested(employee, "employment.work_country", "")).strip().upper()
        if entity_filter and str(payload.get("entity_id", "")) != entity_filter:
            continue
        if country_filter and employee_country != country_filter:
            continue
        searchable = " ".join(str(value) for value in [payload.get("employee_id", ""), payload.get("employee_number", ""), payload.get("employee_no", ""), payload.get("display_name", ""), payload.get("email", ""), payload.get("entity_id", ""), payload.get("entity_label", ""), payload.get("department_label", ""), employee_country, work_country]).casefold()
        if q and q not in searchable:
            continue
        employees.append(payload)
    employees.sort(key=lambda item: (str(item.get("entity_id", "")), str(item.get("employee_number", "")), str(item.get("display_name", ""))))
    return {
        "source": "TAC-employeeadmin",
        "generated_at": now_iso(),
        "employees": employees,
    }


def find_visible_employee_by_id(employee_id: str) -> dict[str, Any] | None:
    employee_id = employee_id.strip()
    if not employee_id:
        return None
    for employee in visible_employees(load_employees()):
        if str(employee.get("employee_id", "")) == employee_id:
            return employee
    return None


def visible_employees_by_number(employee_no: str, entity_id: str = "") -> list[dict[str, Any]]:
    employee_no_key = employee_no.strip().casefold()
    entity_id = entity_id.strip()
    if not employee_no_key:
        return []
    matches = []
    for employee in visible_employees(load_employees()):
        if get_employee_number(employee).casefold() != employee_no_key:
            continue
        if entity_id and employment_entity_id(employee) != entity_id:
            continue
        matches.append(employee)
    return matches


def find_visible_employee_by_number(employee_no: str, entity_id: str = "") -> dict[str, Any] | None:
    matches = visible_employees_by_number(employee_no, entity_id)
    return matches[0] if len(matches) == 1 else None


def parse_iso_date(value: Any) -> date | None:
    value_text = str(value or "").strip()
    if not value_text:
        return None
    try:
        return datetime.strptime(value_text, "%Y-%m-%d").date()
    except ValueError:
        return None


def dispatch_assignment_matches_date(record: dict[str, Any], work_date: date) -> bool:
    start_date = parse_iso_date(record.get("dispatch_start_date", ""))
    end_date = parse_iso_date(record.get("dispatch_end_date", ""))
    if str(record.get("dispatch_start_date", "")).strip() and start_date is None:
        return False
    if str(record.get("dispatch_end_date", "")).strip() and end_date is None:
        return False
    if start_date and work_date < start_date:
        return False
    if end_date and work_date > end_date:
        return False
    return True


def dispatch_assignment_snapshot(record: dict[str, Any], source: str, history_id: str = "") -> dict[str, Any]:
    supervisor = record.get("supervisor", {})
    if not isinstance(supervisor, dict):
        supervisor = {}
    return {
        "matched": True,
        "source": source,
        "history_id": history_id,
        "client_name": str(record.get("client_name", "") or "").strip(),
        "project_name": str(record.get("project_name", "") or "").strip(),
        "assignment_location": str(record.get("assignment_location", "") or "").strip(),
        "dispatch_start_date": str(record.get("dispatch_start_date", "") or "").strip(),
        "dispatch_end_date": str(record.get("dispatch_end_date", "") or "").strip(),
        "contract_type": str(record.get("contract_type", "") or "").strip(),
        "work_description": str(record.get("work_description", "") or "").strip(),
        "supervisor": {
            "name": str(supervisor.get("name", "") or "").strip(),
            "title": str(supervisor.get("title", "") or "").strip(),
            "phone": str(supervisor.get("phone", "") or "").strip(),
            "email": str(supervisor.get("email", "") or "").strip(),
        },
    }


def matching_dispatch_assignment(employee: dict[str, Any], work_date_text: str) -> dict[str, Any]:
    work_date = parse_iso_date(work_date_text)
    if work_date is None:
        return {"matched": False, "warning": "Invalid work_date. Expected YYYY-MM-DD."}
    history_records = employee.get("dispatch_assignment_history", [])
    if isinstance(history_records, list):
        matches = [record for record in history_records if isinstance(record, dict) and dispatch_assignment_matches_date(record, work_date)]
        matches.sort(
            key=lambda item: (
                parse_iso_date(item.get("dispatch_start_date", "")) or date.min,
                parse_iso_date(item.get("effective_date", "")) or date.min,
                str(item.get("changed_at", "")),
            ),
            reverse=True,
        )
        if matches:
            return dispatch_assignment_snapshot(matches[0], "dispatch_assignment_history", str(matches[0].get("history_id", "")))
    current = employee.get("dispatch_compliance", {})
    if isinstance(current, dict) and dispatch_assignment_matches_date(current, work_date):
        return dispatch_assignment_snapshot(current, "dispatch_compliance")
    return {"matched": False}


def timesheet_dispatch_assignment_api_payload(employee_no: str, work_date: str, employee_id: str = "", entity_id: str = "") -> tuple[int, dict[str, Any]]:
    employee_no = employee_no.strip()
    work_date = work_date.strip()
    employee_id = employee_id.strip()
    entity_id = entity_id.strip()
    if not (employee_id or employee_no) or not work_date:
        return 400, {"error": "employee_id or employee_no, and work_date are required."}
    if parse_iso_date(work_date) is None:
        return 400, {"error": "work_date must use YYYY-MM-DD."}
    employee = find_visible_employee_by_id(employee_id) if employee_id else None
    if employee and entity_id and employment_entity_id(employee) != entity_id:
        employee = None
    if not employee and employee_no:
        matches = visible_employees_by_number(employee_no, entity_id)
        if len(matches) > 1:
            return 409, {
                "source": "TAC-employeeadmin",
                "generated_at": now_iso(),
                "employee_no": employee_no,
                "entity_id": entity_id,
                "work_date": work_date,
                "assignment": {"matched": False, "warning": "Employee number is ambiguous; pass employee_id or entity_id."},
            }
        employee = matches[0] if matches else None
    if not employee:
        return 404, {
            "source": "TAC-employeeadmin",
            "generated_at": now_iso(),
            "employee_id": employee_id,
            "employee_no": employee_no,
            "entity_id": entity_id,
            "work_date": work_date,
            "assignment": {"matched": False, "warning": "Employee was not found."},
        }
    return 200, {
        "source": "TAC-employeeadmin",
        "generated_at": now_iso(),
        "employee_id": str(employee.get("employee_id", "")),
        "employee_no": get_employee_number(employee),
        "entity_id": employment_entity_id(employee),
        "work_date": work_date,
        "assignment": matching_dispatch_assignment(employee, work_date),
    }


def load_i18n(lang: str) -> dict[str, str]:
    messages: dict[str, str] = {}
    for candidate in (DEFAULT_LANG, lang):
        path = I18N_DIR / f"{candidate}.json"
        if not path.exists():
            continue
        try:
            with path.open("r", encoding="utf-8") as file:
                data = json.load(file)
        except json.JSONDecodeError:
            data = {}
        if isinstance(data, dict):
            messages.update({str(key): str(value) for key, value in data.items()})
    return messages


def t(messages: dict[str, str], key: str, default: str | None = None) -> str:
    return messages.get(key, default if default is not None else key)


def enum_label(messages: dict[str, str], prefix: str, value: str) -> str:
    if not value:
        return ""
    return t(messages, f"{prefix}.{value}", value.replace("_", " ").title())


def bool_label(messages: dict[str, str], value: Any) -> str:
    return t(messages, "boolean.yes") if bool(value) else t(messages, "boolean.no")


def operation_notice(messages: dict[str, str], record_type: str, record_name: str, action: str, actor: str) -> str:
    template = t(messages, f"operation.{action}", t(messages, "operation.saved"))
    return template.format(record_type=record_type, record=record_name or "-", time=now_iso(), actor=actor or "-")


def no_change_notice(messages: dict[str, str], record_type: str, record_name: str) -> str:
    template = t(messages, "operation.no_changes")
    return template.format(record_type=record_type, record=record_name or "-", time=now_iso())


def get_lang_from_query(query: dict[str, list[str]]) -> str:
    lang = query.get("lang", [DEFAULT_LANG])[0]
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def url_with_lang(path: str, lang: str, params: dict[str, str] | None = None) -> str:
    query = {"lang": lang}
    if params:
        query.update({key: value for key, value in params.items() if value != ""})
    return f"{path}?{urlencode(query)}"


def selected(current: str, value: str) -> str:
    return " selected" if current == value else ""


def checked(value: Any) -> str:
    return " checked" if bool(value) else ""


def parse_date(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def is_valid_date(value: str) -> bool:
    return value == "" or parse_date(value) is not None


def is_non_negative_integer(value: str) -> bool:
    return value == "" or (value.isdigit() and int(value) >= 0)


def split_csv_tags(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def normalize_tags(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return split_csv_tags(str(value or ""))


def join_tags(value: Any) -> str:
    return ", ".join(normalize_tags(value))


def default_document() -> dict[str, str]:
    return {field: "" for field in DOCUMENT_FIELD_NAMES}


def normalize_document(record: Any) -> dict[str, str]:
    document = default_document()
    if isinstance(record, dict):
        for field in DOCUMENT_FIELD_NAMES:
            document[field] = str(record.get(field, "") or "").strip()
    return document


def normalize_documents(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    documents = []
    for item in value:
        document = normalize_document(item)
        if document_row_has_data(document) or document.get("document_id"):
            documents.append(document)
    return documents


def next_document_id(documents: list[dict[str, str]]) -> str:
    max_number = 0
    for document in documents:
        match = re.fullmatch(r"DOC-(\d{4,})", str(document.get("document_id", "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"DOC-{max_number + 1:04d}"


def document_row_has_data(document: dict[str, str]) -> bool:
    return any(str(document.get(field, "")).strip() for field in DOCUMENT_FIELD_NAMES if field != "document_id")


def employee_document_prefix(employee_id: str) -> str:
    match = re.fullmatch(r"EMP-(\d+)", employee_id)
    if not match:
        safe = re.sub(r"[^A-Za-z0-9]", "", employee_id) or "EMP"
        return safe[:16]
    number_text = str(int(match.group(1)))
    return f"E{number_text.zfill(3)}"


def safe_original_filename(filename: str) -> str:
    normalized = filename.replace("\\", "/")
    name = Path(normalized).name.strip()
    return name[:160] or "uploaded_file"


def upload_extension(filename: str) -> str:
    return Path(safe_original_filename(filename)).suffix.lower()


def employee_document_sequence(documents: list[dict[str, str]], employee_id: str) -> int:
    prefix = employee_document_prefix(employee_id)
    pattern = re.compile(rf"^{re.escape(prefix)}\d{{8}}(\d{{4}})\.[A-Za-z0-9]+$")
    max_sequence = 0
    for document in documents:
        stored_filename = str(document.get("stored_filename") or Path(str(document.get("storage_reference", ""))).name)
        match = pattern.fullmatch(stored_filename)
        if match:
            max_sequence = max(max_sequence, int(match.group(1)))
    return max_sequence + 1


def build_stored_document_filename(employee_id: str, sequence: int, extension: str) -> str:
    return f"{employee_document_prefix(employee_id)}{date.today().strftime('%Y%m%d')}{sequence:04d}{extension}"


def document_relative_path(stored_filename: str) -> str:
    return f"{EMPLOYEE_DOCS_RELATIVE_DIR}/{stored_filename}"


def find_employee_document(employee: dict[str, Any], document_id: str) -> dict[str, str] | None:
    for document in normalize_documents(get_nested(employee, "documents", [])):
        if document.get("document_id") == document_id:
            return document
    return None


def document_file_path(document: dict[str, str]) -> Path | None:
    stored_filename = str(document.get("stored_filename", "")).strip()
    if not stored_filename:
        storage_reference = str(document.get("storage_reference", "")).replace("\\", "/")
        stored_filename = Path(storage_reference).name.strip()
    if not stored_filename:
        return None
    root = EMPLOYEE_DOCS_DIR.resolve()
    resolved = (EMPLOYEE_DOCS_DIR / stored_filename).resolve()
    if resolved.parent != root:
        return None
    return resolved


def document_content_type(document: dict[str, str], path: Path) -> str:
    content_type = str(document.get("content_type", "")).strip()
    if content_type and "\r" not in content_type and "\n" not in content_type:
        return content_type[:160]
    guessed_type, _ = mimetypes.guess_type(path.name)
    return guessed_type or "application/octet-stream"


def content_disposition(disposition: str, filename: str) -> str:
    safe_filename = safe_original_filename(filename).replace('"', "").replace("\r", "").replace("\n", "")
    ascii_fallback = safe_filename.encode("ascii", errors="ignore").decode("ascii").strip() or "document"
    ascii_fallback = re.sub(r"[^A-Za-z0-9._ -]", "_", ascii_fallback)
    encoded_filename = quote(safe_filename, safe="")
    return f'{disposition}; filename="{ascii_fallback}"; filename*=UTF-8\'\'{encoded_filename}'


def title_from_filename(filename: str) -> str:
    title = Path(safe_original_filename(filename)).stem.strip()
    return title[:160] or "Uploaded Document"


def validate_upload_parts(uploads: list[dict[str, Any]], messages: dict[str, str]) -> list[str]:
    errors: list[str] = []
    if len(uploads) > MAX_UPLOAD_FILES_PER_REQUEST:
        errors.append(t(messages, "validation.too_many_upload_files"))
    for upload in uploads:
        original_filename = safe_original_filename(str(upload.get("original_filename", "")))
        content = upload.get("content", b"")
        if not original_filename:
            errors.append(t(messages, "validation.upload_filename_required"))
        if not content:
            errors.append(f"{original_filename}: {t(messages, 'validation.upload_empty_file')}")
        if len(content) > MAX_UPLOAD_FILE_BYTES:
            errors.append(f"{original_filename}: {t(messages, 'validation.upload_file_too_large')}")
        extension = upload_extension(original_filename)
        if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            errors.append(f"{original_filename}: {t(messages, 'validation.upload_invalid_extension')}")
    return errors


def uploaded_documents_from_parts(
    employee_id: str,
    form: dict[str, str],
    existing_documents: list[dict[str, str]],
    uploads: list[dict[str, Any]],
    actor: str = DEFAULT_ACTOR,
) -> tuple[list[dict[str, str]], list[tuple[Path, bytes]]]:
    documents = copy.deepcopy(existing_documents)
    file_writes: list[tuple[Path, bytes]] = []
    sequence = employee_document_sequence(documents, employee_id)
    for upload in uploads:
        original_filename = safe_original_filename(str(upload.get("original_filename", "")))
        extension = upload_extension(original_filename)
        stored_filename = build_stored_document_filename(employee_id, sequence, extension)
        sequence += 1
        document = default_document()
        for form_field, document_field in UPLOAD_DOCUMENT_METADATA_FIELDS.items():
            document[document_field] = str(form.get(form_field, "")).strip()
        document["document_id"] = next_document_id(documents)
        document["document_type"] = document["document_type"] or "other"
        document["title"] = title_from_filename(original_filename)
        document["received_date"] = document["received_date"] or date.today().isoformat()
        document["status"] = document["status"] or "on_file"
        document["storage_reference"] = document_relative_path(stored_filename)
        document["original_filename"] = original_filename
        document["stored_filename"] = stored_filename
        document["content_type"] = str(upload.get("content_type", "application/octet-stream") or "application/octet-stream")[:160]
        document["file_size_bytes"] = str(len(upload.get("content", b"")))
        document["uploaded_at"] = now_iso()
        document["uploaded_by"] = actor
        documents.append(normalize_document(document))
        file_writes.append((EMPLOYEE_DOCS_DIR / stored_filename, upload.get("content", b"")))
    return documents, file_writes


def write_uploaded_files(file_writes: list[tuple[Path, bytes]]) -> list[Path]:
    EMPLOYEE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    root = EMPLOYEE_DOCS_DIR.resolve()
    written: list[Path] = []
    try:
        for destination, content in file_writes:
            resolved = destination.resolve()
            if root != resolved.parent:
                raise ValueError("Invalid upload destination")
            with resolved.open("xb") as file:
                file.write(content)
            written.append(resolved)
    except Exception:
        for written_path in written:
            try:
                written_path.unlink()
            except FileNotFoundError:
                pass
        raise
    return written


def apply_form_fields(employee: dict[str, Any], form: dict[str, str], field_paths: list[str]) -> None:
    for path in field_paths:
        form_name = path.replace(".", "__")
        if path in BOOLEAN_FIELD_PATHS:
            set_nested(employee, path, form_name in form)
        elif path in LIST_FIELD_PATHS and form_name in form:
            set_nested(employee, path, split_csv_tags(form[form_name]))
        elif form_name in form:
            set_nested(employee, path, form[form_name].strip())


def employee_from_form(form: dict[str, str], existing: dict[str, Any] | None = None, actor: str = DEFAULT_ACTOR) -> dict[str, Any]:
    employee = copy.deepcopy(existing) if existing else default_employee()
    apply_form_fields(employee, form, PHASE1_FORM_FIELD_PATHS)
    employee.setdefault("metadata", {})
    timestamp = now_iso()
    if existing:
        employee["metadata"]["updated_at"] = timestamp
        employee["metadata"]["updated_by"] = actor
    else:
        employee["metadata"]["created_at"] = timestamp
        employee["metadata"]["created_by"] = actor
        employee["metadata"]["updated_at"] = timestamp
        employee["metadata"]["updated_by"] = actor
        employee["metadata"]["deleted"] = False
    return normalize_employee(employee)


def employee_from_import_row(row: dict[str, str], existing: dict[str, Any] | None = None, actor: str = DEFAULT_ACTOR, entity: dict[str, Any] | None = None, department: dict[str, Any] | None = None) -> dict[str, Any]:
    employee = copy.deepcopy(existing) if existing else default_employee()
    for csv_field, path in COMMON_REQUIRED_FIELD_MAPPING:
        if csv_field in {"legal_entity_code", "department_code"}:
            continue
        value = str(row.get(csv_field, "") or "").strip()
        if path in {"employment.country_code", "employment.work_country"}:
            value = value.upper()
        elif path in {"employment.status", "employment.employment_type", "employment.business_line", "metadata.profile_status", "payroll.bank.account_type"}:
            value = value.lower()
        set_nested(employee, path, value)
    if entity:
        set_nested(employee, "employment.entity_id", str(entity.get("entity_id", "")).strip())
        set_nested(employee, "employment.legal_entity", str(entity.get("entity_code", "")).strip())
    if department:
        set_nested(employee, "employment.department_id", str(department.get("department_id", "")).strip())
        set_nested(employee, "employment.department", str(department.get("department_code", "")).strip())
    employee.setdefault("metadata", {})
    timestamp = now_iso()
    if existing:
        employee["metadata"]["updated_at"] = timestamp
        employee["metadata"]["updated_by"] = actor
    else:
        employee["metadata"]["created_at"] = timestamp
        employee["metadata"]["created_by"] = actor
        employee["metadata"]["updated_at"] = timestamp
        employee["metadata"]["updated_by"] = actor
        employee["metadata"]["deleted"] = False
    return normalize_employee(employee)


def find_employee_index_by_number(employees: list[dict[str, Any]], employee_number: str, entity_id: str = "") -> int | None:
    key = employee_number.strip().casefold()
    if not key:
        return None
    for index, employee in enumerate(employees):
        if entity_id and employment_entity_id(employee) != entity_id:
            continue
        if get_employee_number(employee).casefold() == key:
            return index
    return None


def backup_employees_before_import(employees: list[dict[str, Any]]) -> str:
    EMPLOYEE_BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = EMPLOYEE_BACKUPS_DIR / f"employees_{stamp}_before_import.json"
    save_json_array(backup_path, employees)
    return str(backup_path.relative_to(ROOT_DIR))


def csv_header_language(lang: str) -> str:
    return lang if lang in CSV_HEADER_LANGS else "en"


def localized_csv_fieldnames(fieldnames: list[str], header_lang: str) -> list[str]:
    labels = CSV_HEADER_LABELS[csv_header_language(header_lang)]
    return [labels.get(field, field) for field in fieldnames]


def localize_csv_rows(rows: list[dict[str, str]], fieldnames: list[str], header_lang: str) -> list[dict[str, str]]:
    labels = CSV_HEADER_LABELS[csv_header_language(header_lang)]
    localized_rows: list[dict[str, str]] = []
    for row in rows:
        localized_rows.append({labels.get(field, field): str(row.get(field, "") or "") for field in fieldnames})
    return localized_rows


def detect_csv_header_language(headers: list[str]) -> tuple[str | None, list[str]]:
    stripped_headers = {str(header or "").strip() for header in headers}
    best_lang = "en"
    best_missing: list[str] = []
    best_missing_count: int | None = None
    for header_lang in CSV_HEADER_LANGS:
        labels = CSV_HEADER_LABELS[header_lang]
        missing = [labels.get(field, field) for field in IMPORT_REQUIRED_CSV_FIELDS if labels.get(field, field) not in stripped_headers]
        if not missing:
            return header_lang, []
        if best_missing_count is None or len(missing) < best_missing_count:
            best_lang = header_lang
            best_missing = missing
            best_missing_count = len(missing)
    return None, best_missing or localized_csv_fieldnames(IMPORT_REQUIRED_CSV_FIELDS, best_lang)


def canonical_import_row(raw_row: dict[str, str], header_lang: str) -> dict[str, str]:
    labels = CSV_HEADER_LABELS[csv_header_language(header_lang)]
    return {field: str(raw_row.get(labels.get(field, field), "") or "").strip() for field in COMMON_REQUIRED_CSV_FIELDS}


def section_from_form(form: dict[str, str], existing: dict[str, Any], field_paths: list[str], actor: str = DEFAULT_ACTOR) -> dict[str, Any]:
    employee = copy.deepcopy(existing)
    apply_form_fields(employee, form, field_paths)
    employee.setdefault("metadata", {})
    employee["metadata"]["updated_at"] = now_iso()
    employee["metadata"]["updated_by"] = actor
    return normalize_employee(employee)


def documents_from_form(form: dict[str, str], existing: dict[str, Any], uploads: list[dict[str, Any]] | None = None, actor: str = DEFAULT_ACTOR) -> tuple[dict[str, Any], list[tuple[Path, bytes]]]:
    employee = copy.deepcopy(existing)
    documents = parse_documents_form(form, normalize_documents(get_nested(existing, "documents", [])))
    file_writes: list[tuple[Path, bytes]] = []
    if uploads:
        documents, file_writes = uploaded_documents_from_parts(str(existing.get("employee_id", "")), form, documents, uploads, actor)
    set_nested(employee, "documents", documents)
    employee.setdefault("metadata", {})
    employee["metadata"]["updated_at"] = now_iso()
    employee["metadata"]["updated_by"] = actor
    return normalize_employee(employee), file_writes


def history_type_for_array_key(array_key: str) -> str | None:
    for history_type, config in HISTORY_CONFIG.items():
        if config["array_key"] == array_key:
            return history_type
    return None


def default_history_attachment() -> dict[str, str]:
    attachment = {field: "" for field in HISTORY_ATTACHMENT_FIELD_NAMES}
    attachment.setdefault("attachment_id", "")
    return attachment


def normalize_history_attachment(record: Any) -> dict[str, str]:
    attachment = default_history_attachment()
    if isinstance(record, dict):
        for field in HISTORY_ATTACHMENT_FIELD_NAMES:
            source_field = "document_id" if field == "attachment_id" else field
            attachment[field] = str(record.get(field, record.get(source_field, "")) or "").strip()
    return attachment


def history_attachment_has_data(attachment: dict[str, str]) -> bool:
    return any(str(attachment.get(field, "")).strip() for field in HISTORY_ATTACHMENT_FIELD_NAMES if field != "attachment_id")


def normalize_history_attachments(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list):
        return []
    attachments = []
    for item in value:
        attachment = normalize_history_attachment(item)
        if attachment.get("attachment_id") or history_attachment_has_data(attachment):
            attachments.append(attachment)
    return attachments


def next_history_attachment_id(attachments: list[dict[str, str]]) -> str:
    max_number = 0
    for attachment in attachments:
        match = re.fullmatch(r"ATT-(\d{4,})", str(attachment.get("attachment_id", "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"ATT-{max_number + 1:04d}"


def default_history_record(history_type: str) -> dict[str, Any]:
    timestamp = now_iso()
    record: dict[str, Any] = {
        "history_id": "",
        "event_type": "manual_record",
        "effective_date": date.today().isoformat(),
        "changed_at": timestamp,
        "changed_by": DEFAULT_ACTOR,
        "source": "manual",
        "changed_fields": [],
        "previous_values": {},
        "notes": "",
        "attachments": [],
    }
    if history_type == "visa":
        record.update({
            "visa_type": "",
            "residence_status": "",
            "expiry_date": "",
            "residence_card_number": "",
            "passport_number": "",
            "passport_expiry_date": "",
            "renewal_reminder_enabled": False,
            "renewal_reminder_date": "",
        })
    elif history_type == "dispatch":
        record.update({
            "client_name": "",
            "assignment_location": "",
            "dispatch_start_date": "",
            "dispatch_end_date": "",
            "contract_type": "",
            "work_description": "",
            "supervisor": {"name": "", "title": "", "phone": "", "email": ""},
        })
    else:
        record.update({
            "join_date": "",
            "employment_type": "",
            "entity_id": "",
            "department_id": "",
            "team_id": "",
            "position": "",
            "manager_employee_id": "",
            "office_location": "",
            "assignment": "",
            "status": "",
            "probation_end_date": "",
            "contract": {"start_date": "", "end_date": ""},
            "resignation": {"resignation_date": "", "last_working_date": "", "reason": ""},
        })
    return record


def normalize_history_record(history_type: str, value: Any) -> dict[str, Any]:
    record = default_history_record(history_type)
    if not isinstance(value, dict):
        return record
    for field in ("history_id", "event_type", "effective_date", "changed_at", "changed_by", "source", "notes"):
        record[field] = str(value.get(field, record.get(field, "")) or "").strip()
    changed = value.get("changed_fields", [])
    record["changed_fields"] = [str(item) for item in changed if str(item)] if isinstance(changed, list) else []
    previous = value.get("previous_values", {})
    record["previous_values"] = previous if isinstance(previous, dict) else {}
    record["attachments"] = normalize_history_attachments(value.get("attachments", []))
    if history_type == "visa":
        for field in ("visa_type", "residence_status", "expiry_date", "residence_card_number", "passport_number", "passport_expiry_date", "renewal_reminder_date"):
            record[field] = str(value.get(field, "") or "").strip()
        record["renewal_reminder_enabled"] = bool(value.get("renewal_reminder_enabled", False))
    elif history_type == "dispatch":
        for field in ("client_name", "assignment_location", "dispatch_start_date", "dispatch_end_date", "contract_type", "work_description"):
            record[field] = str(value.get(field, "") or "").strip()
        supervisor = value.get("supervisor", {})
        if not isinstance(supervisor, dict):
            supervisor = {}
        record["supervisor"] = {field: str(supervisor.get(field, "") or "").strip() for field in ("name", "title", "phone", "email")}
    else:
        for field in ("join_date", "employment_type", "entity_id", "department_id", "team_id", "position", "manager_employee_id", "office_location", "assignment", "status", "probation_end_date"):
            record[field] = str(value.get(field, "") or "").strip()
        contract = value.get("contract", {})
        if not isinstance(contract, dict):
            contract = {}
        record["contract"] = {field: str(contract.get(field, "") or "").strip() for field in ("start_date", "end_date")}
        resignation = value.get("resignation", {})
        if not isinstance(resignation, dict):
            resignation = {}
        record["resignation"] = {field: str(resignation.get(field, "") or "").strip() for field in ("resignation_date", "last_working_date", "reason")}
    return record


def normalize_history_records(history_type: str, value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    records = []
    for item in value:
        record = normalize_history_record(history_type, item)
        if record.get("history_id") or record.get("event_type") or record.get("notes") or record.get("attachments"):
            records.append(record)
    return records


def next_history_id(records: list[dict[str, Any]], prefix: str) -> str:
    max_number = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d{{4,}})$")
    for record in records:
        match = pattern.fullmatch(str(record.get("history_id", "")))
        if match:
            max_number = max(max_number, int(match.group(1)))
    return f"{prefix}-{max_number + 1:04d}"


def all_employee_file_records(employee: dict[str, Any]) -> list[dict[str, str]]:
    records = normalize_documents(get_nested(employee, "documents", []))
    for history_type, config in HISTORY_CONFIG.items():
        for record in normalize_history_records(history_type, get_nested(employee, str(config["array_key"]), [])):
            records.extend(normalize_history_attachments(record.get("attachments", [])))
    return records


def uploaded_history_attachments_from_parts(
    employee_id: str,
    form: dict[str, str],
    existing_attachments: list[dict[str, str]],
    uploads: list[dict[str, Any]],
    sequence_records: list[dict[str, str]],
    actor: str = DEFAULT_ACTOR,
) -> tuple[list[dict[str, str]], list[tuple[Path, bytes]]]:
    attachments = copy.deepcopy(existing_attachments)
    file_writes: list[tuple[Path, bytes]] = []
    sequence = employee_document_sequence(sequence_records + attachments, employee_id)
    for upload in uploads:
        original_filename = safe_original_filename(str(upload.get("original_filename", "")))
        extension = upload_extension(original_filename)
        stored_filename = build_stored_document_filename(employee_id, sequence, extension)
        sequence += 1
        attachment = default_history_attachment()
        for form_field, document_field in UPLOAD_DOCUMENT_METADATA_FIELDS.items():
            attachment[document_field] = str(form.get(form_field, "")).strip()
        attachment["attachment_id"] = next_history_attachment_id(attachments)
        attachment["document_type"] = attachment["document_type"] or "other"
        attachment["title"] = title_from_filename(original_filename)
        attachment["received_date"] = attachment["received_date"] or date.today().isoformat()
        attachment["status"] = attachment["status"] or "on_file"
        attachment["storage_reference"] = document_relative_path(stored_filename)
        attachment["original_filename"] = original_filename
        attachment["stored_filename"] = stored_filename
        attachment["content_type"] = str(upload.get("content_type", "application/octet-stream") or "application/octet-stream")[:160]
        attachment["file_size_bytes"] = str(len(upload.get("content", b"")))
        attachment["uploaded_at"] = now_iso()
        attachment["uploaded_by"] = actor
        attachments.append(normalize_history_attachment(attachment))
        file_writes.append((EMPLOYEE_DOCS_DIR / stored_filename, upload.get("content", b"")))
    return attachments, file_writes


def find_history_record(employee: dict[str, Any], history_type: str, history_id: str) -> dict[str, Any] | None:
    config = HISTORY_CONFIG.get(history_type)
    if not config:
        return None
    for record in normalize_history_records(history_type, get_nested(employee, str(config["array_key"]), [])):
        if record.get("history_id") == history_id:
            return record
    return None


def find_history_attachment(employee: dict[str, Any], history_type: str, history_id: str, attachment_id: str) -> dict[str, str] | None:
    record = find_history_record(employee, history_type, history_id)
    if not record:
        return None
    for attachment in normalize_history_attachments(record.get("attachments", [])):
        if attachment.get("attachment_id") == attachment_id:
            return attachment
    return None


def previous_values_snapshot(before: dict[str, Any], changed_paths: list[str]) -> dict[str, Any]:
    snapshot: dict[str, Any] = {}
    for path in changed_paths:
        snapshot[path] = get_nested(before, path, "")
    return snapshot


def infer_visa_event(changed_paths: list[str], before: dict[str, Any], after: dict[str, Any]) -> str:
    if any(path in changed_paths for path in ("visa.passport_number", "visa.passport_expiry_date")):
        return "passport_update"
    if "visa.residence_status" in changed_paths:
        return "residence_status_change"
    if "visa.expiry_date" in changed_paths:
        old_date = parse_date(str(get_nested(before, "visa.expiry_date", "")))
        new_date = parse_date(str(get_nested(after, "visa.expiry_date", "")))
        if old_date and new_date and new_date > old_date:
            return "visa_renewal"
    return "visa_change"


def infer_dispatch_event(changed_paths: list[str], before: dict[str, Any], after: dict[str, Any]) -> str:
    if "dispatch_compliance.dispatch_end_date" in changed_paths and get_nested(after, "dispatch_compliance.dispatch_end_date", ""):
        return "assignment_end"
    if "dispatch_compliance.dispatch_start_date" in changed_paths and not get_nested(before, "dispatch_compliance.dispatch_start_date", ""):
        return "assignment_start"
    if changed_paths and all(path.startswith("dispatch_compliance.supervisor.") for path in changed_paths):
        return "supervisor_change"
    return "assignment_change"


def infer_employment_event(changed_paths: list[str], before: dict[str, Any], after: dict[str, Any]) -> str:
    if "employment.status" in changed_paths:
        if str(get_nested(after, "employment.status", "")) == "resigned":
            return "resignation"
        return "status_change"
    if any(path in changed_paths for path in ("employment.entity_id", "employment.department_id", "employment.team_id")):
        return "department_change"
    if "employment.position" in changed_paths:
        return "position_change"
    return "employment_change"


def build_history_from_current(history_type: str, employee: dict[str, Any], before: dict[str, Any], changed_paths: list[str], actor: str = DEFAULT_ACTOR) -> dict[str, Any]:
    config = HISTORY_CONFIG[history_type]
    records = normalize_history_records(history_type, get_nested(employee, str(config["array_key"]), []))
    record = default_history_record(history_type)
    record["history_id"] = next_history_id(records, str(config["history_id_prefix"]))
    record["source"] = "auto"
    record["changed_at"] = now_iso()
    record["changed_by"] = actor
    record["changed_fields"] = changed_paths
    record["previous_values"] = previous_values_snapshot(before, changed_paths)
    if history_type == "visa":
        visa = employee.get("visa", {}) if isinstance(employee.get("visa"), dict) else {}
        for field in ("visa_type", "residence_status", "expiry_date", "residence_card_number", "passport_number", "passport_expiry_date", "renewal_reminder_enabled", "renewal_reminder_date", "notes"):
            record[field] = copy.deepcopy(visa.get(field, record.get(field, "")))
        record["event_type"] = infer_visa_event(changed_paths, before, employee)
        record["effective_date"] = date.today().isoformat()
    elif history_type == "dispatch":
        dispatch = employee.get("dispatch_compliance", {}) if isinstance(employee.get("dispatch_compliance"), dict) else {}
        for field in ("client_name", "assignment_location", "dispatch_start_date", "dispatch_end_date", "contract_type", "work_description", "notes"):
            record[field] = copy.deepcopy(dispatch.get(field, ""))
        supervisor = dispatch.get("supervisor", {}) if isinstance(dispatch.get("supervisor"), dict) else {}
        record["supervisor"] = {field: str(supervisor.get(field, "") or "") for field in ("name", "title", "phone", "email")}
        record["event_type"] = infer_dispatch_event(changed_paths, before, employee)
        record["effective_date"] = str(dispatch.get("dispatch_start_date") or date.today().isoformat())
    else:
        employment = employee.get("employment", {}) if isinstance(employee.get("employment"), dict) else {}
        for field in ("join_date", "employment_type", "entity_id", "department_id", "team_id", "position", "manager_employee_id", "office_location", "assignment", "status", "probation_end_date"):
            record[field] = copy.deepcopy(employment.get(field, ""))
        contract = employment.get("contract", {}) if isinstance(employment.get("contract"), dict) else {}
        record["contract"] = {field: str(contract.get(field, "") or "") for field in ("start_date", "end_date")}
        resignation = employment.get("resignation", {}) if isinstance(employment.get("resignation"), dict) else {}
        record["resignation"] = {field: str(resignation.get(field, "") or "") for field in ("resignation_date", "last_working_date", "reason")}
        record["event_type"] = infer_employment_event(changed_paths, before, employee)
        record["effective_date"] = str(resignation.get("resignation_date") or date.today().isoformat())
    return normalize_history_record(history_type, record)


def latest_history_snapshot_matches(records: list[dict[str, Any]], candidate: dict[str, Any], history_type: str) -> bool:
    if not records:
        return False
    latest = records[-1]
    ignored = {"history_id", "changed_at"}
    for key, value in candidate.items():
        if key in ignored:
            continue
        if latest.get(key) != value:
            return False
    return True


def append_auto_history_record(employee: dict[str, Any], before: dict[str, Any], history_type: str, changed_paths: list[str], actor: str = DEFAULT_ACTOR) -> str | None:
    if not changed_paths:
        return None
    config = HISTORY_CONFIG[history_type]
    array_key = str(config["array_key"])
    records = normalize_history_records(history_type, get_nested(employee, array_key, []))
    candidate = build_history_from_current(history_type, employee, before, changed_paths, actor)
    if latest_history_snapshot_matches(records, candidate, history_type):
        return None
    records.append(candidate)
    set_nested(employee, array_key, records)
    return str(candidate.get("history_id", ""))


def parse_history_attachments_form(form: dict[str, str], existing_attachments: list[dict[str, str]]) -> list[dict[str, str]]:
    attachments: list[dict[str, str]] = []
    for index, attachment in enumerate(existing_attachments):
        if form.get(f"attachments__{index}__delete") == "1":
            continue
        parsed = default_history_attachment()
        for field in HISTORY_ATTACHMENT_FIELD_NAMES:
            parsed[field] = form.get(f"attachments__{index}__{field}", attachment.get(field, "")).strip()
        if parsed.get("attachment_id") or history_attachment_has_data(parsed):
            attachments.append(normalize_history_attachment(parsed))
    return attachments


def history_record_from_form(
    history_type: str,
    form: dict[str, str],
    existing_employee: dict[str, Any],
    existing_record: dict[str, Any] | None,
    uploads: list[dict[str, Any]],
    actor: str = DEFAULT_ACTOR,
) -> tuple[dict[str, Any], list[tuple[Path, bytes]]]:
    config = HISTORY_CONFIG[history_type]
    records = normalize_history_records(history_type, get_nested(existing_employee, str(config["array_key"]), []))
    record = normalize_history_record(history_type, existing_record or default_history_record(history_type))
    if not record.get("history_id"):
        record["history_id"] = next_history_id(records, str(config["history_id_prefix"]))
    record["event_type"] = form.get("event_type", record.get("event_type", "manual_record")).strip() or "manual_record"
    record["effective_date"] = form.get("effective_date", record.get("effective_date", "")).strip()
    record["source"] = form.get("source", record.get("source", "manual")).strip() or "manual"
    record["notes"] = form.get("notes", record.get("notes", "")).strip()
    record["changed_at"] = now_iso()
    record["changed_by"] = actor
    record.setdefault("changed_fields", [])
    record.setdefault("previous_values", {})
    if history_type == "visa":
        for field in ("visa_type", "residence_status", "expiry_date", "residence_card_number", "passport_number", "passport_expiry_date", "renewal_reminder_date"):
            record[field] = form.get(field, record.get(field, "")).strip()
        record["renewal_reminder_enabled"] = form.get("renewal_reminder_enabled") == "1"
    elif history_type == "dispatch":
        for field in ("client_name", "assignment_location", "dispatch_start_date", "dispatch_end_date", "contract_type", "work_description"):
            record[field] = form.get(field, record.get(field, "")).strip()
        record["supervisor"] = {field: form.get(f"supervisor__{field}", get_nested(record, f"supervisor.{field}", "")).strip() for field in ("name", "title", "phone", "email")}
    else:
        for field in ("join_date", "employment_type", "entity_id", "department_id", "team_id", "position", "manager_employee_id", "office_location", "assignment", "status", "probation_end_date"):
            record[field] = form.get(field, record.get(field, "")).strip()
        record["contract"] = {field: form.get(f"contract__{field}", get_nested(record, f"contract.{field}", "")).strip() for field in ("start_date", "end_date")}
        record["resignation"] = {field: form.get(f"resignation__{field}", get_nested(record, f"resignation.{field}", "")).strip() for field in ("resignation_date", "last_working_date", "reason")}
    existing_attachments = normalize_history_attachments(record.get("attachments", []))
    attachments = parse_history_attachments_form(form, existing_attachments)
    file_writes: list[tuple[Path, bytes]] = []
    if uploads:
        attachments, file_writes = uploaded_history_attachments_from_parts(str(existing_employee.get("employee_id", "")), form, attachments, uploads, all_employee_file_records(existing_employee), actor)
    record["attachments"] = attachments
    return normalize_history_record(history_type, record), file_writes


def parse_documents_form(form: dict[str, str], existing_documents: list[dict[str, str]]) -> list[dict[str, str]]:
    rows: dict[int, dict[str, str]] = {}
    deleted: set[int] = set()
    for key, value in form.items():
        match = re.fullmatch(r"documents__(\d+)__(\w+)", key)
        if not match:
            continue
        index = int(match.group(1))
        field = match.group(2)
        if field == "delete":
            deleted.add(index)
            continue
        if field not in DOCUMENT_FIELD_NAMES:
            continue
        rows.setdefault(index, default_document())[field] = value.strip()

    documents: list[dict[str, str]] = []
    next_id_source = copy.deepcopy(existing_documents)
    for index in sorted(rows):
        if index in deleted:
            continue
        document = normalize_document(rows[index])
        if not document_row_has_data(document):
            continue
        if not document.get("document_id"):
            document["document_id"] = next_document_id(next_id_source + documents)
        documents.append(document)
    return documents


def validation_item(messages: dict[str, str], field_path: str, message_key: str, code: str, *, csv_field: str = "", row: int | None = None, suggestion_key: str = "") -> dict[str, Any]:
    message = t(messages, message_key)
    return {
        "field_path": field_path,
        "csv_field": csv_field or COMMON_REQUIRED_PATH_TO_CSV.get(field_path, field_path.replace(".", "__")),
        "label": field_label(messages, field_path),
        "message": message,
        "code": code,
        "row": row,
        "suggestion": t(messages, suggestion_key) if suggestion_key else "",
    }


def validation_item_message(error: dict[str, Any]) -> str:
    label = str(error.get("label", ""))
    message = str(error.get("message", ""))
    return f"{label}: {message}" if label else message


def format_validation_errors(errors: list[dict[str, Any]]) -> list[str]:
    return [validation_item_message(error) for error in errors]


def field_errors_by_path(errors: list[dict[str, Any]]) -> dict[str, list[str]]:
    grouped: dict[str, list[str]] = {}
    for error in errors:
        path = str(error.get("field_path", ""))
        if path:
            grouped.setdefault(path, []).append(str(error.get("message", "")))
    return grouped


def employee_number_exists(employees: list[dict[str, Any]], employee_number: str, current_employee_id: str = "") -> bool:
    key = employee_number.strip().casefold()
    if not key:
        return False
    for existing in visible_employees(employees):
        if str(existing.get("employee_id", "")) == current_employee_id:
            continue
        if get_employee_number(existing).casefold() == key:
            return True
    return False


def employee_validation_errors(employee: dict[str, Any], employees: list[dict[str, Any]], messages: dict[str, str], *, row: int | None = None) -> list[dict[str, Any]]:
    errors: list[dict[str, Any]] = []
    employee_id = str(employee.get("employee_id", ""))

    for path in REQUIRED_FIELD_PATHS:
        if not str(get_nested(employee, path, "")).strip():
            errors.append(validation_item(messages, path, "validation.required", "required", row=row))
    employee["employee_number"] = get_employee_number(employee)
    employee_number = employee["employee_number"]
    employee_entity_id = employment_entity_id(employee)
    if employee_number:
        if len(employee_number) > 64 or any(ord(character) < 32 for character in employee_number):
            errors.append(validation_item(messages, "employee_number", "validation.invalid_employee_number", "invalid_employee_number", row=row))
        employee_number_key = employee_number.casefold()
        for existing in visible_employees(employees):
            if existing.get("employee_id") == employee_id:
                continue
            if employment_entity_id(existing) == employee_entity_id and get_employee_number(existing).casefold() == employee_number_key:
                errors.append(validation_item(messages, "employee_number", "validation.duplicate_employee_number", "duplicate_employee_number", row=row))
                break

    email = str(get_nested(employee, "profile.email", "")).strip().lower()
    if email and not EMAIL_PATTERN.fullmatch(email):
        errors.append(validation_item(messages, "profile.email", "validation.invalid_email", "invalid_email", row=row))
    if email:
        for existing in visible_employees(employees):
            if existing.get("employee_id") == employee_id:
                continue
            if str(get_nested(existing, "profile.email", "")).strip().lower() == email:
                errors.append(validation_item(messages, "profile.email", "validation.duplicate_email", "duplicate_email", row=row))
                break

    personal_email = str(get_nested(employee, "profile.email_p", "")).strip().lower()
    if personal_email and not EMAIL_PATTERN.fullmatch(personal_email):
        errors.append(validation_item(messages, "profile.email_p", "validation.invalid_email", "invalid_email", row=row))

    emergency_email = str(get_nested(employee, "profile.emergency_contact.email", "")).strip()
    if emergency_email and not EMAIL_PATTERN.fullmatch(emergency_email):
        errors.append(validation_item(messages, "profile.emergency_contact.email", "validation.invalid_email", "invalid_email", row=row))

    for path in PHASE1_FORM_FIELD_PATHS:
        value = str(get_nested(employee, path, "")).strip()
        if path in DATE_FIELD_PATHS and value and not is_valid_date(value):
            errors.append(validation_item(messages, path, "validation.invalid_date", "invalid_date", row=row))

    contract_start = parse_date(str(get_nested(employee, "employment.contract.start_date", "")).strip())
    contract_end_text = str(get_nested(employee, "employment.contract.end_date", "")).strip()
    contract_end = parse_date(contract_end_text)
    if contract_start and contract_end and not is_open_ended_labor_contract_date(contract_end_text) and contract_end < contract_start:
        errors.append(validation_item(messages, "employment.contract.end_date", "validation.labor_contract_end_before_start", "labor_contract_end_before_start", row=row))

    resignation_date = parse_date(str(get_nested(employee, "employment.resignation.resignation_date", "")).strip())
    last_working_date = parse_date(str(get_nested(employee, "employment.resignation.last_working_date", "")).strip())
    if resignation_date and last_working_date and last_working_date < resignation_date:
        errors.append(validation_item(messages, "employment.resignation.last_working_date", "validation.last_working_before_resignation", "last_working_before_resignation", row=row))

    status = str(get_nested(employee, "employment.status", ""))
    if status not in EMPLOYMENT_STATUSES:
        errors.append(validation_item(messages, "employment.status", "validation.invalid_status", "invalid_status", row=row, suggestion_key="validation.suggestion.employment_status"))

    employment_type = str(get_nested(employee, "employment.employment_type", ""))
    if employment_type not in EMPLOYMENT_TYPES:
        errors.append(validation_item(messages, "employment.employment_type", "validation.invalid_employment_type", "invalid_employment_type", row=row, suggestion_key="validation.suggestion.employment_type"))

    country_code = str(get_nested(employee, "employment.country_code", ""))
    if country_code and country_code not in COUNTRY_CODES:
        errors.append(validation_item(messages, "employment.country_code", "validation.invalid_country_code", "invalid_country_code", row=row, suggestion_key="validation.suggestion.country_code"))

    work_country = str(get_nested(employee, "employment.work_country", ""))
    if work_country and work_country not in COUNTRY_CODES:
        errors.append(validation_item(messages, "employment.work_country", "validation.invalid_country_code", "invalid_country_code", row=row, suggestion_key="validation.suggestion.country_code"))

    business_line = str(get_nested(employee, "employment.business_line", ""))
    if business_line and business_line not in BUSINESS_LINES:
        errors.append(validation_item(messages, "employment.business_line", "validation.invalid_business_line", "invalid_business_line", row=row, suggestion_key="validation.suggestion.business_line"))

    profile_status = str(get_nested(employee, "metadata.profile_status", ""))
    if profile_status and profile_status not in PROFILE_STATUSES:
        errors.append(validation_item(messages, "metadata.profile_status", "validation.invalid_profile_status", "invalid_profile_status", row=row, suggestion_key="validation.suggestion.profile_status"))

    manager_id = str(get_nested(employee, "employment.manager_employee_id", "")).strip()
    if manager_id and manager_id != DEFAULT_MANAGER_EMPLOYEE_NUMBER and not employee_number_exists(employees, manager_id, employee_id):
        errors.append(validation_item(messages, "employment.manager_employee_id", "validation.manager_not_found", "manager_not_found", row=row, suggestion_key="validation.suggestion.manager_id"))

    gender = str(get_nested(employee, "profile.gender", ""))
    if gender not in GENDERS:
        errors.append(validation_item(messages, "profile.gender", "validation.invalid_gender", "invalid_gender", row=row))

    return errors


def validate_employee(employee: dict[str, Any], employees: list[dict[str, Any]], messages: dict[str, str]) -> list[str]:
    return format_validation_errors(employee_validation_errors(employee, employees, messages))


def masterdata_reference_fields_changed(employee: dict[str, Any], before: dict[str, Any] | None) -> bool:
    if not before:
        return True
    for path in ("employment.entity_id", "employment.department_id", "employment.team_id"):
        if str(get_nested(employee, path, "")) != str(get_nested(before, path, "")):
            return True
    return False


def validate_masterdata_references(employee: dict[str, Any], session_id: str, messages: dict[str, str], lang: str, before: dict[str, Any] | None = None) -> list[str]:
    errors: list[str] = []
    entity_id = employment_entity_id(employee)
    department_id = employment_department_id(employee)
    team_id = employment_team_id(employee)
    if not any((entity_id, department_id, team_id)):
        return errors
    if not masterdata_reference_fields_changed(employee, before):
        return errors
    entities, entity_error = fetch_masterdata_entities(session_id)
    if entity_error:
        errors.append(t(messages, "validation.masterdata_unavailable"))
        return errors
    if entity_id and entity_id not in {str(item.get("entity_id", "")) for item in entities}:
        errors.append(f"{field_label(messages, 'employment.entity_id')}: {t(messages, 'validation.invalid_entity')}")
    departments, department_error = fetch_masterdata_departments(session_id, entity_id)
    if department_error:
        errors.append(t(messages, "validation.masterdata_unavailable"))
        return errors
    department_by_id = {str(item.get("department_id", "")): item for item in departments}
    selected_department = department_by_id.get(department_id) if department_id else None
    if department_id and not selected_department:
        errors.append(f"{field_label(messages, 'employment.department_id')}: {t(messages, 'validation.invalid_department')}")
    if team_id:
        teams, team_error = fetch_masterdata_teams(session_id, department_id)
        if team_error:
            errors.append(t(messages, "validation.masterdata_unavailable"))
            return errors
        if team_id not in {str(item.get("team_id", "")) for item in teams}:
            errors.append(f"{field_label(messages, 'employment.team_id')}: {t(messages, 'validation.invalid_team')}")
    return errors


def sync_masterdata_display_codes(employee: dict[str, Any], session_id: str) -> dict[str, Any]:
    entity_id = employment_entity_id(employee)
    department_id = employment_department_id(employee)
    if not entity_id:
        set_nested(employee, "employment.legal_entity", "")
        set_nested(employee, "employment.department", "")
        return employee

    entities, entity_error = fetch_masterdata_entities(session_id)
    if not entity_error:
        entity = next((item for item in entities if str(item.get("entity_id", "")) == entity_id), None)
        if entity:
            set_nested(employee, "employment.legal_entity", str(entity.get("entity_code", "")).strip())

    if not department_id:
        set_nested(employee, "employment.department", "")
        return employee

    departments, department_error = fetch_masterdata_departments(session_id, entity_id)
    if not department_error:
        department = next((item for item in departments if str(item.get("department_id", "")) == department_id), None)
        if department:
            set_nested(employee, "employment.department", str(department.get("department_code", "")).strip())
    return employee


def validate_dates(employee: dict[str, Any], field_paths: list[str], messages: dict[str, str]) -> list[str]:
    errors: list[str] = []
    for path in field_paths:
        if path not in DATE_FIELD_PATHS:
            continue
        value = str(get_nested(employee, path, "")).strip()
        if value and not is_valid_date(value):
            errors.append(f"{field_label(messages, path)}: {t(messages, 'validation.invalid_date')}")
    return errors


def validate_section(employee: dict[str, Any], section_key: str, messages: dict[str, str]) -> list[str]:
    config = SECTION_CONFIG[section_key]
    field_paths = config["field_paths"]
    errors = validate_dates(employee, field_paths, messages)

    if section_key == "payroll":
        salary_type = str(get_nested(employee, "payroll.salary_type", ""))
        if salary_type not in SALARY_TYPES:
            errors.append(f"{field_label(messages, 'payroll.salary_type')}: {t(messages, 'validation.invalid_salary_type')}")
        # currency validation
        payroll_currency = str(get_nested(employee, "payroll.payroll_currency", "")).strip().upper()
        if payroll_currency:
            if payroll_currency not in SUPPORTED_CURRENCIES:
                errors.append(f"{field_label(messages, 'payroll.payroll_currency')}: {t(messages, 'validation.invalid_currency')}")
        # conditional wage field validation based on salary_type
        if salary_type in SALARY_TYPE_REQUIRED_WAGE_FIELD:
            required_wage_path = SALARY_TYPE_REQUIRED_WAGE_FIELD[salary_type]
            wage_value = str(get_nested(employee, required_wage_path, "")).strip()
            if not wage_value:
                errors.append(f"{field_label(messages, required_wage_path)}: {t(messages, 'validation.wage_required_for_salary_type')}")
        account_type = str(get_nested(employee, "payroll.bank.account_type", ""))
        if account_type not in BANK_ACCOUNT_TYPES:
            errors.append(f"{field_label(messages, 'payroll.bank.account_type')}: {t(messages, 'validation.invalid_bank_account_type')}")
        for path in MONEY_FIELD_PATHS:
            value = str(get_nested(employee, path, "")).strip()
            if value and not is_non_negative_integer(value):
                errors.append(f"{field_label(messages, path)}: {t(messages, 'validation.invalid_money')}")

    if section_key == "visa":
        reminder_enabled = bool(get_nested(employee, "visa.renewal_reminder_enabled", False))
        reminder_date = str(get_nested(employee, "visa.renewal_reminder_date", "")).strip()
        expiry_date = str(get_nested(employee, "visa.expiry_date", "")).strip()
        if reminder_enabled and not reminder_date:
            errors.append(f"{field_label(messages, 'visa.renewal_reminder_date')}: {t(messages, 'validation.renewal_date_required')}")
        parsed_reminder = parse_date(reminder_date)
        parsed_expiry = parse_date(expiry_date)
        if parsed_reminder and parsed_expiry and parsed_reminder > parsed_expiry:
            errors.append(f"{field_label(messages, 'visa.renewal_reminder_date')}: {t(messages, 'validation.renewal_after_expiry')}")

    if section_key == "dispatch":
        contract_type = str(get_nested(employee, "dispatch_compliance.contract_type", ""))
        if contract_type not in DISPATCH_CONTRACT_TYPES:
            errors.append(f"{field_label(messages, 'dispatch_compliance.contract_type')}: {t(messages, 'validation.invalid_dispatch_contract_type')}")
        start_date = parse_date(str(get_nested(employee, "dispatch_compliance.dispatch_start_date", "")).strip())
        end_date = parse_date(str(get_nested(employee, "dispatch_compliance.dispatch_end_date", "")).strip())
        if start_date and end_date and end_date < start_date:
            errors.append(f"{field_label(messages, 'dispatch_compliance.dispatch_end_date')}: {t(messages, 'validation.end_before_start')}")
        supervisor_email = str(get_nested(employee, "dispatch_compliance.supervisor.email", "")).strip()
        if supervisor_email and not EMAIL_PATTERN.fullmatch(supervisor_email):
            errors.append(f"{field_label(messages, 'dispatch_compliance.supervisor.email')}: {t(messages, 'validation.invalid_email')}")

    if section_key == "skills":
        japanese_level = str(get_nested(employee, "language_profile.japanese_level", ""))
        english_level = str(get_nested(employee, "language_profile.english_level", ""))
        years = str(get_nested(employee, "skills_profile.years_of_experience", "")).strip()
        if japanese_level not in JAPANESE_LEVELS:
            errors.append(f"{field_label(messages, 'language_profile.japanese_level')}: {t(messages, 'validation.invalid_japanese_level')}")
        if english_level not in ENGLISH_LEVELS:
            errors.append(f"{field_label(messages, 'language_profile.english_level')}: {t(messages, 'validation.invalid_english_level')}")
        if not is_non_negative_integer(years):
            errors.append(f"{field_label(messages, 'skills_profile.years_of_experience')}: {t(messages, 'validation.invalid_years_experience')}")
        for path in LIST_FIELD_PATHS:
            tags = normalize_tags(get_nested(employee, path, []))
            if len(tags) > 30:
                errors.append(f"{field_label(messages, path)}: {t(messages, 'validation.too_many_tags')}")
            if any(len(tag) > 80 for tag in tags):
                errors.append(f"{field_label(messages, path)}: {t(messages, 'validation.tag_too_long')}")

    if section_key == "documents":
        documents = normalize_documents(get_nested(employee, "documents", []))
        if len(documents) > 50:
            errors.append(t(messages, 'validation.too_many_documents'))
        for document in documents:
            prefix = f"{document.get('document_id') or t(messages, 'section.documents')}"
            if document_row_has_data(document) and not document.get("document_type"):
                errors.append(f"{prefix}: {t(messages, 'validation.document_type_required')}")
            if document.get("document_type", "") not in DOCUMENT_TYPES:
                errors.append(f"{prefix}: {t(messages, 'validation.invalid_document_type')}")
            if document.get("status", "") not in DOCUMENT_STATUSES:
                errors.append(f"{prefix}: {t(messages, 'validation.invalid_document_status')}")
            for field in ("document_date", "expiry_date", "received_date"):
                if document.get(field) and not is_valid_date(document[field]):
                    errors.append(f"{prefix} {field_label(messages, 'documents.' + field)}: {t(messages, 'validation.invalid_date')}")
            for field in ("title", "issuer", "storage_reference", "original_filename", "stored_filename", "content_type", "file_size_bytes", "uploaded_at", "uploaded_by"):
                if len(document.get(field, "")) > 160:
                    errors.append(f"{prefix} {field_label(messages, 'documents.' + field)}: {t(messages, 'validation.text_too_long')}")
            if len(document.get("notes", "")) > 1000:
                errors.append(f"{prefix} {field_label(messages, 'documents.notes')}: {t(messages, 'validation.text_too_long')}")

    return errors


def validate_history_record(record: dict[str, Any], history_type: str, messages: dict[str, str]) -> list[str]:
    errors: list[str] = []
    config = HISTORY_CONFIG.get(history_type)
    if not config:
        errors.append(t(messages, "validation.not_found"))
        return errors
    if record.get("event_type", "") not in config["event_types"]:
        errors.append(t(messages, "validation.invalid_history_event_type"))
    if record.get("source", "") not in HISTORY_SOURCES:
        errors.append(t(messages, "validation.invalid_history_source"))
    if record.get("effective_date") and not is_valid_date(str(record.get("effective_date", ""))):
        errors.append(t(messages, "validation.invalid_date"))
    if len(str(record.get("notes", ""))) > 1000:
        errors.append(t(messages, "validation.text_too_long"))
    attachments = normalize_history_attachments(record.get("attachments", []))
    if len(attachments) > 20:
        errors.append(t(messages, "validation.too_many_history_attachments"))
    for attachment in attachments:
        prefix = attachment.get("attachment_id") or t(messages, "history.attachments")
        if attachment.get("document_type", "") not in DOCUMENT_TYPES:
            errors.append(f"{prefix}: {t(messages, 'validation.invalid_document_type')}")
        if attachment.get("status", "") not in DOCUMENT_STATUSES:
            errors.append(f"{prefix}: {t(messages, 'validation.invalid_document_status')}")
        for field in ("document_date", "expiry_date", "received_date"):
            if attachment.get(field) and not is_valid_date(attachment[field]):
                errors.append(f"{prefix} {field_label(messages, 'documents.' + field)}: {t(messages, 'validation.invalid_date')}")
    if history_type == "visa":
        for field in ("expiry_date", "passport_expiry_date", "renewal_reminder_date"):
            if record.get(field) and not is_valid_date(str(record.get(field, ""))):
                errors.append(f"{field}: {t(messages, 'validation.invalid_date')}")
        expiry = parse_date(str(record.get("expiry_date", "")))
        renewal = parse_date(str(record.get("renewal_reminder_date", "")))
        if bool(record.get("renewal_reminder_enabled")) and not record.get("renewal_reminder_date"):
            errors.append(t(messages, "validation.renewal_date_required"))
        if expiry and renewal and renewal > expiry:
            errors.append(t(messages, "validation.renewal_after_expiry"))
    elif history_type == "dispatch":
        if record.get("contract_type", "") not in DISPATCH_CONTRACT_TYPES:
            errors.append(t(messages, "validation.invalid_dispatch_contract_type"))
        start = parse_date(str(record.get("dispatch_start_date", "")))
        end = parse_date(str(record.get("dispatch_end_date", "")))
        if start and end and end < start:
            errors.append(t(messages, "validation.end_before_start"))
        supervisor_email = str(get_nested(record, "supervisor.email", "")).strip()
        if supervisor_email and not EMAIL_PATTERN.match(supervisor_email):
            errors.append(t(messages, "validation.invalid_email"))
    else:
        if record.get("employment_type", "") not in EMPLOYMENT_TYPES:
            errors.append(t(messages, "validation.invalid_employment_type"))
        if record.get("status", "") not in EMPLOYMENT_STATUSES:
            errors.append(t(messages, "validation.invalid_status"))
        contract_start_text = str(get_nested(record, "contract.start_date", "")).strip()
        contract_end_text = str(get_nested(record, "contract.end_date", "")).strip()
        if contract_start_text and not is_valid_date(contract_start_text):
            errors.append(t(messages, "validation.invalid_date"))
        if contract_end_text and not is_valid_date(contract_end_text):
            errors.append(t(messages, "validation.invalid_date"))
        contract_start = parse_date(contract_start_text)
        contract_end = parse_date(contract_end_text)
        if contract_start and contract_end and not is_open_ended_labor_contract_date(contract_end_text) and contract_end < contract_start:
            errors.append(t(messages, "validation.labor_contract_end_before_start"))
        resignation_date = parse_date(str(get_nested(record, "resignation.resignation_date", "")))
        last_working = parse_date(str(get_nested(record, "resignation.last_working_date", "")))
        if resignation_date and last_working and last_working < resignation_date:
            errors.append(t(messages, "validation.end_before_start"))
    return errors


def changed_fields(before: dict[str, Any], after: dict[str, Any], field_paths: list[str] | None = None) -> list[str]:
    changed: list[str] = []
    for path in field_paths or FIELD_PATHS:
        if get_nested(before, path, "") != get_nested(after, path, ""):
            changed.append(path)
    return changed


def is_sensitive_audit_path(path: str) -> bool:
    lowered = path.lower()
    return any(marker in lowered for marker in SENSITIVE_AUDIT_PATH_MARKERS)


def audit_field_snapshot(record: dict[str, Any] | None, fields: list[str]) -> dict[str, Any]:
    if not record:
        return {}
    snapshot: dict[str, Any] = {}
    for path in fields:
        if is_sensitive_audit_path(path):
            snapshot[path] = "[REDACTED]"
        elif path == "employee":
            snapshot[path] = str(record.get("employee_id", ""))
        else:
            value = get_nested(record, path, "")
            if isinstance(value, (dict, list)):
                snapshot[path] = "[COMPLEX_VALUE]"
            else:
                snapshot[path] = value
    return snapshot


def append_audit_log(
    employee_id: str,
    action: str,
    section: str,
    fields: list[str],
    summary: str,
    before_record: dict[str, Any] | None = None,
    after_record: dict[str, Any] | None = None,
    actor: str = DEFAULT_ACTOR,
) -> None:
    audit_logs = load_audit_logs()
    timestamp = now_iso()
    audit_logs.append(
        {
            "audit_id": next_audit_id(audit_logs),
            "employee_id": employee_id,
            "actor": actor,
            "action": action,
            "section": section,
            "changed_fields": fields,
            "summary": summary,
            "created_at": timestamp,
            "module": section,
            "record_id": employee_id,
            "user": actor,
            "timestamp": timestamp,
            "before_value": audit_field_snapshot(before_record, fields),
            "after_value": audit_field_snapshot(after_record, fields),
        }
    )
    save_json_array(AUDIT_LOGS_PATH, audit_logs)


def alert_date_in_window(value: str, days: int) -> bool:
    parsed = parse_date(value)
    if not parsed:
        return False
    return parsed <= date.today() + timedelta(days=days)


def days_until(value: str) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return (parsed - date.today()).days


def is_open_ended_labor_contract_date(value: str) -> bool:
    return str(value or "").strip() == LABOR_CONTRACT_OPEN_END_DATE


def labor_contract_end_display(messages: dict[str, str], value: str) -> str:
    value_text = str(value or "").strip()
    if is_open_ended_labor_contract_date(value_text):
        return t(messages, "employment.contract_open_ended")
    return value_text


def labor_contract_renewal_alert_date(employee: dict[str, Any]) -> str:
    status = str(get_nested(employee, "employment.status", ""))
    if status not in {"active", "probation", "on_leave"}:
        return ""
    end_date = str(get_nested(employee, "employment.contract.end_date", "")).strip()
    if not end_date or is_open_ended_labor_contract_date(end_date):
        return ""
    if not alert_date_in_window(end_date, LABOR_CONTRACT_ALERT_DAYS):
        return ""
    return end_date


def is_foreign_employee(employee: dict[str, Any]) -> bool:
    nationality = str(get_nested(employee, "profile.nationality", "")).strip()
    return bool(nationality) and nationality.lower() not in NON_FOREIGN_NATIONALITIES


def is_dispatch_employee(employee: dict[str, Any]) -> bool:
    return get_nested(employee, "employment.employment_type") == "dispatch" or bool(
        str(get_nested(employee, "dispatch_compliance.client_name", "")).strip()
    )


def dashboard_alerts(employees: list[dict[str, Any]]) -> list[dict[str, str]]:
    alerts: list[dict[str, str]] = []
    for employee in visible_employees(employees):
        employee_id = str(employee.get("employee_id", ""))
        employee_number = get_employee_number(employee)
        display_name = str(get_nested(employee, "profile.name.display_name", ""))
        visa_expiry = str(get_nested(employee, "visa.expiry_date", "")).strip()
        if is_foreign_employee(employee) and alert_date_in_window(visa_expiry, VISA_ALERT_DAYS):
            alerts.append({"employee_id": employee_id, "employee_number": employee_number, "display_name": display_name, "type": "visa_expiry", "date": visa_expiry})
        probation_end = str(get_nested(employee, "employment.probation_end_date", "")).strip()
        status = str(get_nested(employee, "employment.status", ""))
        if status in {"active", "probation"} and alert_date_in_window(probation_end, PROBATION_ALERT_DAYS):
            alerts.append({"employee_id": employee_id, "employee_number": employee_number, "display_name": display_name, "type": "probation_end", "date": probation_end})
        contract_end = labor_contract_renewal_alert_date(employee)
        if contract_end:
            alerts.append({"employee_id": employee_id, "employee_number": employee_number, "display_name": display_name, "type": "labor_contract_renewal", "date": contract_end})
    return alerts


def dashboard_metrics(employees: list[dict[str, Any]]) -> dict[str, int]:
    today = date.today()
    visible = visible_employees(employees)
    new_joiners = 0
    for employee in visible:
        parsed = parse_date(str(get_nested(employee, "employment.join_date", "")))
        if parsed and parsed.year == today.year and parsed.month == today.month:
            new_joiners += 1
    alerts = dashboard_alerts(employees)
    data_scores = [data_completion_score(employee) for employee in visible]
    avg_data_completion = round(sum(score["percent"] for score in data_scores) / len(data_scores)) if data_scores else 100
    return {
        "total_employees": len(visible),
        "active_employees": sum(1 for employee in visible if get_nested(employee, "employment.status") == "active"),
        "new_joiners": new_joiners,
        "dispatch_employees": sum(1 for employee in visible if is_dispatch_employee(employee)),
        "foreign_employees": sum(1 for employee in visible if is_foreign_employee(employee)),
        "visa_expiry_alerts": sum(1 for alert in alerts if alert["type"] == "visa_expiry"),
        "probation_alerts": sum(1 for alert in alerts if alert["type"] == "probation_end"),
        "labor_contract_renewal_alerts": sum(1 for alert in alerts if alert["type"] == "labor_contract_renewal"),
        "avg_data_completion": avg_data_completion,
        "incomplete_employees": sum(1 for score in data_scores if score["percent"] < DATA_COMPLETION_WARNING_THRESHOLD),
        "missing_required_documents": len(report_missing_required_documents(employees)),
    }


def report_missing_required_data(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        missing = [path for path in REQUIRED_FIELD_PATHS if not str(get_nested(employee, path, "")).strip()]
        if missing:
            rows.append({"employee": employee, "missing_fields": missing})
    return sorted(rows, key=lambda row: str(row["employee"].get("employee_id", "")))


def report_visa_expiry(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        expiry_date = str(get_nested(employee, "visa.expiry_date", "")).strip()
        if is_foreign_employee(employee) and alert_date_in_window(expiry_date, VISA_ALERT_DAYS):
            rows.append({"employee": employee, "days_until": days_until(expiry_date)})
    return sorted(rows, key=lambda row: row["days_until"] if row["days_until"] is not None else 999999)


def report_probation_ending(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        status = str(get_nested(employee, "employment.status", ""))
        probation_end = str(get_nested(employee, "employment.probation_end_date", "")).strip()
        if status in {"active", "probation"} and alert_date_in_window(probation_end, PROBATION_ALERT_DAYS):
            rows.append({"employee": employee, "days_until": days_until(probation_end)})
    return sorted(rows, key=lambda row: row["days_until"] if row["days_until"] is not None else 999999)


def report_labor_contract_renewals(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        contract_end = labor_contract_renewal_alert_date(employee)
        if contract_end:
            rows.append({"employee": employee, "days_until": days_until(contract_end)})
    return sorted(rows, key=lambda row: row["days_until"] if row["days_until"] is not None else 999999)


def report_dispatch_assignments(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = [{"employee": employee} for employee in visible_employees(employees) if is_dispatch_employee(employee)]
    return sorted(rows, key=lambda row: str(row["employee"].get("employee_id", "")))


def report_document_expiry(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        for document in normalize_documents(get_nested(employee, "documents", [])):
            expiry_date = str(document.get("expiry_date", "")).strip()
            status = str(document.get("status", ""))
            if status != "not_required" and alert_date_in_window(expiry_date, DOCUMENT_ALERT_DAYS):
                rows.append({"employee": employee, "document": document, "days_until": days_until(expiry_date)})
    return sorted(rows, key=lambda row: row["days_until"] if row["days_until"] is not None else 999999)


def report_missing_documents(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        for document in normalize_documents(get_nested(employee, "documents", [])):
            if document.get("status") == "missing":
                rows.append({"employee": employee, "document": document})
    return sorted(rows, key=lambda row: (str(row["employee"].get("employee_id", "")), str(row["document"].get("document_id", ""))))


def required_field_paths_for_employee(employee: dict[str, Any]) -> list[str]:
    paths = list(REQUIRED_FIELD_PATHS)
    if is_foreign_employee(employee):
        paths.extend(["visa.residence_status", "visa.expiry_date"])
    if is_dispatch_employee(employee):
        paths.extend([
            "dispatch_compliance.client_name",
            "dispatch_compliance.assignment_location",
            "dispatch_compliance.dispatch_start_date",
            "dispatch_compliance.supervisor.name",
        ])
    return list(dict.fromkeys(paths))


def completion_score_for_paths(employee: dict[str, Any], paths: list[str]) -> dict[str, Any]:
    missing = [path for path in paths if not str(get_nested(employee, path, "")).strip()]
    total = len(paths)
    completed = total - len(missing)
    percent = round((completed / total) * 100) if total else 100
    return {"completed": completed, "total": total, "percent": percent, "missing_fields": missing}


def data_completion_score(employee: dict[str, Any]) -> dict[str, Any]:
    return completion_score_for_paths(employee, required_field_paths_for_employee(employee))


def required_document_types_for_employee(employee: dict[str, Any]) -> list[str]:
    required = list(BASE_REQUIRED_DOCUMENT_TYPES)
    if str(get_nested(employee, "employment.status", "")) in {"active", "probation"}:
        required.extend(ACTIVE_EMPLOYEE_REQUIRED_DOCUMENT_TYPES)
    if is_foreign_employee(employee):
        required.extend(FOREIGN_EMPLOYEE_REQUIRED_DOCUMENT_TYPES)
    return list(dict.fromkeys(required))


def documents_by_type(employee: dict[str, Any]) -> dict[str, list[dict[str, str]]]:
    grouped: dict[str, list[dict[str, str]]] = {}
    for document in normalize_documents(get_nested(employee, "documents", [])):
        document_type = str(document.get("document_type", "")).strip()
        if document_type:
            grouped.setdefault(document_type, []).append(document)
    return grouped


def document_requirement_matrix(employee: dict[str, Any]) -> list[dict[str, Any]]:
    grouped = documents_by_type(employee)
    rows = []
    for document_type in required_document_types_for_employee(employee):
        documents = grouped.get(document_type, [])
        complete_documents = [document for document in documents if str(document.get("status", "")) in DOCUMENT_COMPLETE_STATUSES]
        expiry_dates = [str(document.get("expiry_date", "")).strip() for document in documents if str(document.get("expiry_date", "")).strip()]
        latest_expiry = max(expiry_dates, default="")
        is_complete = bool(complete_documents)
        is_expired_or_expiring = bool(latest_expiry and alert_date_in_window(latest_expiry, DOCUMENT_ALERT_DAYS))
        rows.append({
            "employee": employee,
            "document_type": document_type,
            "documents": documents,
            "matched_count": len(documents),
            "complete_count": len(complete_documents),
            "latest_expiry_date": latest_expiry,
            "days_until_expiry": days_until(latest_expiry) if latest_expiry else None,
            "status": "complete" if is_complete else "missing",
            "is_complete": is_complete,
            "is_expired_or_expiring": is_expired_or_expiring,
        })
    return rows


def document_completion_score(employee: dict[str, Any]) -> dict[str, Any]:
    requirements = document_requirement_matrix(employee)
    total = len(requirements)
    missing = [row for row in requirements if not row["is_complete"]]
    completed = total - len(missing)
    percent = round((completed / total) * 100) if total else 100
    return {
        "completed": completed,
        "total": total,
        "percent": percent,
        "missing_document_types": [str(row["document_type"]) for row in missing],
    }


def report_data_completion(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        rows.append({
            "employee": employee,
            "data_score": data_completion_score(employee),
            "document_score": document_completion_score(employee),
        })
    return sorted(rows, key=lambda row: (row["data_score"]["percent"], str(row["employee"].get("employee_id", ""))))


PAYROLL_READY_EMPLOYMENT_STATUSES = {"active", "probation"}


def payroll_readiness_required_paths(employee: dict[str, Any] | None = None) -> list[str]:
    paths = list(IMPORT_REQUIRED_FIELD_PATHS)
    # payroll_currency is required for payroll readiness
    if "payroll.payroll_currency" not in paths:
        paths.append("payroll.payroll_currency")
    # conditional wage field based on salary_type
    if employee:
        salary_type = str(get_nested(employee, "payroll.salary_type", "")).strip()
        if salary_type in SALARY_TYPE_REQUIRED_WAGE_FIELD:
            wage_path = SALARY_TYPE_REQUIRED_WAGE_FIELD[salary_type]
            if wage_path not in paths:
                paths.append(wage_path)
    return paths


def payroll_readiness_missing_fields(employee: dict[str, Any]) -> list[str]:
    missing = []
    for path in payroll_readiness_required_paths(employee):
        value = get_nested(employee, path, "")
        if isinstance(value, str):
            is_missing = not value.strip()
        else:
            is_missing = value in (None, "")
        if is_missing:
            missing.append(path)
    return missing


def payroll_readiness_score(employee: dict[str, Any]) -> dict[str, Any]:
    required_paths = payroll_readiness_required_paths(employee)
    missing = payroll_readiness_missing_fields(employee)
    status = str(get_nested(employee, "employment.status", "")).strip().lower()
    employment_status_ready = status in PAYROLL_READY_EMPLOYMENT_STATUSES
    if status and not employment_status_ready and "employment.status" not in missing:
        missing = [*missing, "employment.status"]
    total = len(required_paths) + (0 if employment_status_ready else 1)
    total = max(total, 1)
    completed = max(total - len(missing), 0)
    return {
        "ready": not missing,
        "completed": completed,
        "total": total,
        "percent": round((completed / total) * 100),
        "missing_fields": missing,
        "status": "ready" if not missing else "blocked",
    }


def report_payroll_readiness(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        score = payroll_readiness_score(employee)
        rows.append({"employee": employee, "payroll_readiness": score})
    return sorted(rows, key=lambda row: (row["payroll_readiness"]["percent"], get_employee_number(row["employee"]).casefold(), str(row["employee"].get("employee_id", ""))))


def payroll_employee_payload(employee: dict[str, Any], context: dict[str, dict[str, str]] | None = None) -> dict[str, Any]:
    base = timesheet_employee_payload(employee, context)
    score = payroll_readiness_score(employee)
    payroll_bank = get_nested(employee, "payroll.bank", {})
    if not isinstance(payroll_bank, dict):
        payroll_bank = {}
    salary_amount = get_nested(employee, "payroll.salary_amount_yen", "")
    monthly_base = get_nested(employee, "payroll.monthly_base_salary", "")
    daily_wage = get_nested(employee, "payroll.daily_wage", "")
    hourly_wage = get_nested(employee, "payroll.hourly_wage", "")
    payroll_payload = {
        "salary_type": str(get_nested(employee, "payroll.salary_type", "")),
        "payroll_currency": str(get_nested(employee, "payroll.payroll_currency", "SGD")),
        "salary_amount_yen": salary_amount,
        "monthly_base_salary": monthly_base,
        "daily_wage": daily_wage,
        "hourly_wage": hourly_wage,
        "base_salary": monthly_base or daily_wage or hourly_wage or salary_amount,
        "basic_salary": monthly_base or daily_wage or hourly_wage or salary_amount,
        "hourly_rate": get_nested(employee, "payroll.hourly_rate", hourly_wage),
        "daily_rate": get_nested(employee, "payroll.daily_rate", daily_wage),
        "transportation_allowance_yen": get_nested(employee, "payroll.transportation_allowance_yen", ""),
        "bank_name": str(payroll_bank.get("bank_name", "")),
        "bank_account_name": str(payroll_bank.get("account_holder", "")),
        "bank_account_number": str(payroll_bank.get("account_number", "")),
        "bank": dict(payroll_bank),
        "notes": str(get_nested(employee, "payroll.notes", "")),
    }
    base.update({
        "country_code": str(get_nested(employee, "employment.country_code", "")),
        "work_country": str(get_nested(employee, "employment.work_country", "")),
        "business_line": str(get_nested(employee, "employment.business_line", "")),
        "profile_status": str(get_nested(employee, "metadata.profile_status", "")),
        "payroll": payroll_payload,
        "payroll_ready": bool(score["ready"]),
        "payroll_readiness_status": score["status"],
        "payroll_readiness_percent": score["percent"],
        "missing_payroll_readiness_fields": list(score["missing_fields"]),
    })
    return base


def payroll_employee_api_payload(query: dict[str, list[str]], session_id: str = "", lang: str = DEFAULT_LANG) -> dict[str, Any]:
    source_employees = visible_employees(load_employees())
    context, _error = masterdata_context_for_employees(session_id, lang, source_employees) if session_id else (empty_masterdata_context(), None)
    entity_filter = str(query.get("entity_id", [""])[0]).strip()
    department_filter = str((query.get("department_id") or query.get("department") or [""])[0]).strip().casefold()
    country_filter = normalize_country_code(query.get("country_code", [""])[0])
    q = str(query.get("q", [""])[0]).strip().casefold()
    employees = []
    for employee in source_employees:
        payload = payroll_employee_payload(employee, context)
        if entity_filter and str(payload.get("entity_id", "")) != entity_filter:
            continue
        if country_filter and normalize_country_code(payload.get("country_code", "")) != country_filter:
            continue
        department_values = " ".join(str(payload.get(key, "")) for key in ["department_id", "department", "department_label"]).casefold()
        if department_filter and department_filter not in department_values:
            continue
        searchable = " ".join(str(payload.get(key, "")) for key in ["employee_id", "employee_number", "employee_no", "display_name", "email", "entity_id", "entity_label", "entity_name", "department_id", "department", "department_label", "team_id", "team_label", "country_code", "work_country", "business_line"]).casefold()
        if q and q not in searchable:
            continue
        employees.append(payload)
    employees.sort(key=lambda item: (not bool(item.get("payroll_ready")), str(item.get("entity_id", "")), str(item.get("employee_number", "")), str(item.get("display_name", ""))))
    return {
        "source": "TAC-employeeadmin",
        "purpose": "payroll_readiness",
        "generated_at": now_iso(),
        "employees": employees,
    }


def report_required_document_matrix(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for employee in visible_employees(employees):
        rows.extend(document_requirement_matrix(employee))
    return sorted(rows, key=lambda row: (str(row["employee"].get("employee_id", "")), str(row["document_type"])))


def report_missing_required_documents(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in report_required_document_matrix(employees) if not row["is_complete"]]


def report_duplicate_values(employees: list[dict[str, Any]], path: str, case_insensitive: bool = False) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    display_values: dict[str, str] = {}
    for employee in visible_employees(employees):
        if path == "employee_id":
            value = str(employee.get("employee_id", "")).strip()
        elif path == "employee_number":
            value = get_employee_number(employee)
        else:
            value = str(get_nested(employee, path, "")).strip()
        if not value:
            continue
        key = value.lower() if case_insensitive else value
        grouped.setdefault(key, []).append(employee)
        display_values.setdefault(key, value)
    rows = []
    for key, matches in grouped.items():
        if len(matches) <= 1:
            continue
        for employee in matches:
            rows.append({"employee": employee, "path": path, "value": display_values[key]})
    return sorted(rows, key=lambda row: (row["path"], row["value"], str(row["employee"].get("employee_id", ""))))


def report_data_quality(employees: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for row in report_duplicate_values(employees, "employee_number", case_insensitive=True):
        row["issue_key"] = "reports.issue_duplicate_employee_number"
        rows.append(row)
    for row in report_duplicate_values(employees, "profile.email", case_insensitive=True):
        row["issue_key"] = "reports.issue_duplicate_email"
        rows.append(row)
    return rows


def safe_employee_export_rows(employees: list[dict[str, Any]], context: dict[str, dict[str, str]] | None = None) -> list[dict[str, str]]:
    rows = []
    for employee in sorted(visible_employees(employees), key=lambda item: (get_employee_number(item).casefold(), str(item.get("employee_id", "")))):
        row: dict[str, str] = {}
        for column, path in SAFE_EMPLOYEE_EXPORT_FIELDS:
            if path == "employee_id":
                value = employee.get("employee_id", "")
            elif path == "employee_number":
                value = get_employee_number(employee)
            elif path == "__entity_label":
                value = employment_entity_display(employee, context)
            elif path == "__department_label":
                value = employment_department_display(employee, context)
            elif path == "__team_label":
                value = employment_team_display(employee, context)
            else:
                value = get_nested(employee, path, "")
            row[column] = join_tags(value) if isinstance(value, list) else str(value or "")
        rows.append(row)
    return rows


def unique_entity_ids(employees: list[dict[str, Any]]) -> list[str]:
    entities = {employment_entity_id(employee) for employee in visible_employees(employees)}
    return sorted(entity for entity in entities if entity)


def unique_department_ids(employees: list[dict[str, Any]]) -> list[str]:
    departments = {employment_department_id(employee) for employee in visible_employees(employees)}
    return sorted(department for department in departments if department)


def unique_team_ids(employees: list[dict[str, Any]]) -> list[str]:
    teams = {employment_team_id(employee) for employee in visible_employees(employees)}
    return sorted(team for team in teams if team)


def filter_employees(employees: list[dict[str, Any]], query: dict[str, list[str]]) -> list[dict[str, Any]]:
    keyword = query.get("q", [""])[0].strip().lower()
    entity_id = query.get("entity_id", [""])[0].strip()
    country_code = normalize_country_code(query.get("country_code", [""])[0])
    department = query.get("department_id", query.get("department", [""]))[0].strip()
    team_id = query.get("team_id", [""])[0].strip()
    status = query.get("status", [""])[0].strip()
    show_resigned = query.get("show_resigned", [""])[0].strip() == "1"
    employment_type = query.get("employment_type", [""])[0].strip()
    japanese_level = query.get("japanese_level", [""])[0].strip()
    english_level = query.get("english_level", [""])[0].strip()
    skill = query.get("skill", [""])[0].strip().lower()
    new_joiners_month = query.get("new_joiners_month", [""])[0].strip() == "1"
    results = visible_employees(employees)
    if not show_resigned and status != "resigned":
        results = [employee for employee in results if get_nested(employee, "employment.status") != "resigned"]
    if keyword:
        results = [
            employee
            for employee in results
            if keyword
            in " ".join(
                [
                    get_employee_number(employee),
                    str(get_nested(employee, "profile.name.display_name", "")),
                    str(get_nested(employee, "profile.email", "")),
                    str(get_nested(employee, "profile.email_p", "")),
                ]
            ).lower()
        ]
    if entity_id:
        results = [employee for employee in results if employment_entity_id(employee) == entity_id]
    if country_code:
        results = [employee for employee in results if employment_country_code(employee) == country_code]
    if department:
        results = [employee for employee in results if employment_department_id(employee) == department]
    if team_id:
        results = [employee for employee in results if employment_team_id(employee) == team_id]
    if status:
        results = [employee for employee in results if get_nested(employee, "employment.status") == status]
    if employment_type:
        results = [employee for employee in results if get_nested(employee, "employment.employment_type") == employment_type]
    if japanese_level:
        results = [employee for employee in results if get_nested(employee, "language_profile.japanese_level") == japanese_level]
    if english_level:
        results = [employee for employee in results if get_nested(employee, "language_profile.english_level") == english_level]
    if skill:
        results = [
            employee
            for employee in results
            if skill
            in " ".join(
                [
                    str(get_nested(employee, "skills_profile.primary_skill", "")),
                    str(get_nested(employee, "skills_profile.secondary_skill", "")),
                    join_tags(get_nested(employee, "skills_profile.it_skills", [])),
                    join_tags(get_nested(employee, "skills_profile.engineering_skills", [])),
                    join_tags(get_nested(employee, "skills_profile.certifications", [])),
                    join_tags(get_nested(employee, "skills_profile.industry_experience", [])),
                ]
            ).lower()
        ]
    if new_joiners_month:
        today = date.today()
        filtered: list[dict[str, Any]] = []
        for employee in results:
            parsed = parse_date(str(get_nested(employee, "employment.join_date", "")))
            if parsed and parsed.year == today.year and parsed.month == today.month:
                filtered.append(employee)
        results = filtered
    return sorted(results, key=lambda employee: (get_employee_number(employee).casefold(), str(employee.get("employee_id", ""))))


def field_label(messages: dict[str, str], path: str) -> str:
    key = "field." + path.replace(".", "__")
    return t(messages, key, path.split(".")[-1].replace("_", " ").title())


def display_value(messages: dict[str, str], path: str, value: Any) -> str:
    if path in BOOLEAN_FIELD_PATHS:
        return bool_label(messages, value)
    if path in LIST_FIELD_PATHS:
        return join_tags(value)
    value_text = str(value or "")
    if path == "employment.status":
        return enum_label(messages, "status", value_text)
    if path == "employment.employment_type":
        return enum_label(messages, "employment_type", value_text)
    if path in {"employment.country_code", "employment.work_country"}:
        return enum_label(messages, "country", value_text)
    if path == "employment.business_line":
        return enum_label(messages, "business_line", value_text)
    if path == "employment.contract.end_date":
        return labor_contract_end_display(messages, value_text)
    if path == "metadata.profile_status":
        return enum_label(messages, "profile_status", value_text)
    if path == "profile.gender" and value_text:
        return enum_label(messages, "gender", value_text)
    if path == "payroll.salary_type":
        return enum_label(messages, "salary_type", value_text)
    if path == "payroll.bank.account_type":
        return enum_label(messages, "bank_account_type", value_text)
    if path == "dispatch_compliance.contract_type":
        return enum_label(messages, "dispatch_contract_type", value_text)
    if path == "language_profile.japanese_level":
        return enum_label(messages, "japanese_level", value_text)
    if path == "language_profile.english_level":
        return enum_label(messages, "english_level", value_text)
    return value_text


def current_user_html(user: dict[str, Any] | None = None) -> str:
    if not user:
        return ""
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    account = str(user.get("username") or user.get("email") or user.get("display_name") or user.get("user_id") or "User")
    display_name = str(user.get("display_name") or account)
    entity_code = str(user.get("entity_code") or session.get("entity", {}).get("entity_code", ""))
    login_time = str(session.get("login_time_jst") or session.get("login_time") or "-")
    return f'<span class="current-user-chip" title="Login: {h(login_time)}"><strong>👤 {h(account)}</strong><small>{h(display_name)}{(" · " + h(entity_code)) if entity_code else ""}</small><small>Login: {h(login_time)}</small></span>'


def render_page(title: str, body: str, lang: str, messages: dict[str, str], current_url: str = "/", current_user: dict[str, Any] | None = None, request_host: str | None = None) -> bytes:
    parsed_current = urlparse(current_url or "/")
    current_path = parsed_current.path or "/"
    parsed_query = parse_qs(parsed_current.query)
    current_query = {key: values[-1] for key, values in parsed_query.items() if key not in {"lang", "notice", "notice_type"} and values}
    notice = parsed_query.get("notice", [""])[0]
    notice_type = parsed_query.get("notice_type", ["success"])[0] or "success"
    notice_class = "message-success" if notice_type == "success" else "message-info"
    notice_html = f'<div class="message-strip {notice_class}" role="status">{h(notice)}</div>' if notice else ""
    primary_nav = [
        ("/", "nav.dashboard"),
        ("/employees", "nav.employees"),
        ("/onboarding", "nav.onboarding"),
        ("/reports", "nav.reports"),
        ("/audit-logs", "nav.audit_logs"),
    ]
    primary_nav_html = "".join(f'<a href="{h(url_with_lang(path, lang))}">{h(t(messages, key))}</a>' for path, key in primary_nav)
    portal_nav_html = (
        f'<a class="portal-link" href="{h(resolve_portal_url(request_host))}" title="{h(t(messages, "nav.portal_tooltip"))}" '
        f'aria-label="{h(t(messages, "nav.portal_tooltip"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{h(t(messages, "nav.portal"))}</a>'
    )
    language_html = "".join(
        f'<a class="language-pill{ " active" if candidate == lang else "" }" href="{h(url_with_lang(current_path, candidate, current_query))}">{h(label)}</a>'
        for candidate, label in [("zh", "简体中文"), ("ja", "日本語"), ("en", "English")]
    )
    user_html = current_user_html(current_user)
    nav = f"""
<header class="site-header">
  <div class="site-brand">
    <h1>{h(t(messages, 'app.title'))}</h1>
    <p class="muted">{h(t(messages, 'app.subtitle'))}</p>
  </div>
  <nav class="top-nav" aria-label="Primary navigation">
    <div class="primary-nav">{portal_nav_html}{primary_nav_html}</div>
    <span class="language-switcher" aria-label="{h(t(messages, 'nav.language'))}">{user_html}{language_html}</span>
  </nav>
</header>
"""
    html = f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)}</title>
  <style>
    :root {{
      color-scheme: light;
      --navy: #14213d;
      --blue: #1f6feb;
      --page-bg: #f6f8fb;
      --surface: #ffffff;
      --surface-muted: #f8fafc;
      --border: #d8dee9;
      --border-strong: #c8d1dc;
      --text: #17202a;
      --muted: #65758b;
      --accent: #1f6feb;
      --accent-dark: #1d4ed8;
      --green: #0f766e;
      --amber: #b45309;
      --danger: #b91c1c;
      --focus: rgba(31, 111, 235, 0.18);
      --shadow-soft: 0 1px 2px rgba(15, 23, 42, 0.04);
    }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 16px; line-height: 1.45; margin: 0; color: var(--text); background: var(--page-bg); }}
    main {{ max-width: 1240px; margin: 0 auto; padding: 22px 18px 42px; }}
    .site-header {{ background: var(--navy); color: white; padding: 16px 28px 14px; display: grid; gap: 0.75rem; border-bottom: 0; }}
    .site-brand {{ min-width: 0; }}
    .site-header h1 {{ margin: 0 0 4px; font-size: clamp(1.35rem, 2.2vw, 1.85rem); line-height: 1.15; }}
    .site-header .muted {{ color: #dbeafe; margin: 0; font-size: 0.95rem; }}
    .top-nav, .primary-nav, .language-switcher, .actions {{ display: flex; gap: 0.6rem; flex-wrap: wrap; align-items: center; }}
    .top-nav {{ width: 100%; }}
    .language-switcher {{ margin-left: auto; justify-content: flex-end; }}
    .current-user-chip {{ display: grid; gap: 2px; min-width: 180px; padding: 7px 10px; background: #fff; border: 1px solid #d6e4f2; border-radius: 12px; color: var(--navy); box-shadow: 0 1px 2px rgba(15,23,42,.04); }}
    .current-user-chip strong {{ font-size: .9rem; }}
    .current-user-chip small {{ color: var(--muted); font-size: .76rem; }}
    .site-header nav a, .language-switcher a {{ color: var(--navy); text-decoration: none; border: 1px solid var(--border); padding: 7px 11px; border-radius: 999px; font-weight: 750; background: white; line-height: 1.15; }}
    .site-header nav a:hover, .language-switcher a:hover {{ border-color: var(--blue); color: var(--blue); text-decoration: none; }}
    .site-header nav a.portal-link {{ display: inline-flex; align-items: center; gap: 0.35rem; color: #0b4f8a; background: linear-gradient(180deg, #f8fbff 0%, #eaf4ff 100%); border-color: #9cc7f2; box-shadow: inset 0 1px 0 rgba(255,255,255,.9), 0 1px 2px rgba(15,23,42,.08); }}
    .site-header nav a.portal-link:hover {{ color: #064b86; border-color: #1f6feb; background: #ffffff; }}
    .portal-icon {{ font-size: 1rem; line-height: 1; }}
    .language-pill.active {{ background: #ecfeff; color: #155e75; border-color: #bae6fd; }}
    a {{ color: var(--accent); text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    .card {{ border: 1px solid var(--border); border-radius: 14px; padding: 16px; background: var(--surface); margin-bottom: 0.85rem; box-shadow: var(--shadow-soft); }}
    .metric-card {{ display: block; color: inherit; }}
    .metric-card:hover {{ text-decoration: none; border-color: var(--accent); }}
    .grid {{ display: grid; gap: 0.85rem; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); }}
    .metric {{ font-size: 1.85rem; font-weight: 700; margin: 0.2rem 0; }}
    .muted {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; background: var(--surface); }}
    th, td {{ border-bottom: 1px solid #e5e7eb; padding: 0.68rem 0.75rem; text-align: left; vertical-align: top; font-size: 0.95rem; line-height: 1.4; }}
    th {{ background: #f3f4f6; font-size: 0.9rem; font-weight: 800; }}
    label {{ display: block; font-weight: 700; margin-bottom: 0.42rem; }}
    input, select, textarea {{ box-sizing: border-box; width: 100%; min-height: 42px; padding: 0.68rem 0.78rem; border: 1px solid var(--border-strong); border-radius: 10px; font: inherit; background: #fff; color: var(--text); }}
    input:focus, select:focus, textarea:focus {{ outline: 3px solid var(--focus); border-color: var(--accent); }}
    textarea {{ min-height: 5rem; }}
    .form-grid {{ display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); }}
    .form-grid.compact {{ grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); }}
    .form-field {{ margin-bottom: 1rem; }}
    .form-field label {{ color: #24364b; font-size: 0.95rem; line-height: 1.25; }}
    .required-marker {{ color: var(--danger); margin-left: 0.2rem; font-weight: 800; }}
    .required-note {{ margin: 0 0 1rem; color: var(--muted); font-size: 0.92rem; }}
    .field-error {{ margin: 0.35rem 0 0; color: var(--danger); font-size: 0.9rem; font-weight: 700; }}
    .checkbox-field {{ display: flex; gap: 0.6rem; align-items: center; padding: 0.75rem; border: 1px solid var(--border); border-radius: 10px; background: var(--surface-muted); }}
    .checkbox-field input {{ width: auto; }}
    .checkbox-field label {{ margin: 0; }}
    .button, button {{ display: inline-flex; align-items: center; justify-content: center; min-height: 42px; background: var(--accent); color: #fff; border: 0; border-radius: 8px; padding: 11px 16px; cursor: pointer; text-decoration: none; font-weight: 800; }}
    .button:hover, button:hover {{ background: var(--accent-dark); text-decoration: none; }}
    .button.secondary {{ background: #475569; }}
    .button.success {{ background: var(--green); }}
    .button.warning {{ background: var(--amber); }}
    .button.danger, button.danger {{ background: var(--danger); }}
    .button.ghost, .button.light {{ background: #ffffff; color: var(--navy); border: 1px solid var(--border); }}
    .button.ghost:hover, .button.light:hover {{ background: #f8fafc; color: var(--blue); }}
    .errors, .message-strip {{ border-left: 4px solid var(--danger); background: #fef2f2; color: #991b1b; border-radius: 8px; padding: 12px 14px; margin-bottom: 1rem; }}
    .message-info {{ border-left-color: var(--blue); background: #eff6ff; color: var(--text); }}
    .message-success {{ border-left-color: var(--green); background: #ecfdf5; color: var(--text); }}
    .message-warning {{ border-left-color: var(--amber); background: #fffbeb; color: var(--text); }}
    .badge, .status-badge {{ display: inline-block; border-radius: 999px; background: #ecfeff; color: #155e75; padding: 4px 8px; font-size: 0.85rem; font-weight: 800; }}
    .badge.success, .status-success {{ background: #dcfce7; color: #166534; }}
    .badge.alert, .status-error {{ background: #fee2e2; color: #991b1b; }}
    .file-preview {{ margin-top: 0.45rem; padding: 0.6rem 0.75rem; border: 1px dashed #cbd5e1; border-radius: 10px; background: #f8fafc; color: var(--muted); font-size: 0.92rem; }}
    .file-preview ul {{ margin: 0.35rem 0 0; padding-left: 1.1rem; color: var(--text); }}
    .document-checklist-table td {{ vertical-align: top; }}
    .empty {{ padding: 1rem; text-align: center; color: var(--muted); }}
    .object-page {{ display: grid; gap: 0.8rem; }}
    .object-header, .sap-page-header {{ border: 1px solid var(--border); border-radius: 16px; background: linear-gradient(135deg, #ffffff 0%, #eef4ff 100%); box-shadow: var(--shadow-soft); padding: 16px; display: grid; grid-template-columns: minmax(0, 1fr) minmax(300px, 0.78fr); gap: 1rem; align-items: start; }}
    .object-header-content {{ min-width: 0; }}
    .object-header h2 {{ margin: 0.05rem 0 0.35rem; font-size: clamp(1.35rem, 2.2vw, 1.8rem); line-height: 1.18; color: #0f172a; }}
    .object-header .muted {{ max-width: 58rem; line-height: 1.38; margin: 0.25rem 0 0; }}
    .eyebrow {{ margin: 0 0 0.18rem; color: var(--accent); font-size: 0.74rem; font-weight: 800; letter-spacing: 0.055em; text-transform: uppercase; }}
    .object-meta {{ display: grid; gap: 0.42rem; grid-template-columns: repeat(auto-fit, minmax(128px, 1fr)); align-items: stretch; }}
    .meta-chip {{ border: 1px solid #d6e4f2; border-radius: 12px; background: rgba(255, 255, 255, 0.8); padding: 0.48rem 0.56rem; min-width: 0; box-shadow: 0 4px 10px rgba(15, 23, 42, 0.035); }}
    .meta-chip-label {{ display: block; color: var(--muted); font-size: 0.74rem; font-weight: 800; letter-spacing: 0.035em; text-transform: uppercase; margin-bottom: 0.16rem; }}
    .meta-chip-value {{ display: block; color: #0f172a; font-weight: 750; overflow-wrap: anywhere; line-height: 1.28; font-size: 1rem; }}
    .employee-form {{ display: grid; gap: 1rem; }}
    .form-section, .sap-section {{ border: 1px solid var(--border); border-radius: 14px; background: var(--surface); overflow: hidden; box-shadow: var(--shadow-soft); }}
    .section-header {{ padding: 0.78rem 1rem; border-bottom: 1px solid var(--border); background: linear-gradient(180deg, #f8fafc 0%, #f1f5f9 100%); }}
    .section-header h3 {{ margin: 0; color: #0f172a; font-size: 1.08rem; }}
    .field-group {{ padding: 1rem 1.1rem 1.05rem; border-bottom: 1px solid #eef2f7; }}
    .field-group:last-child {{ border-bottom: 0; }}
    .field-group-title {{ margin: 0 0 0.68rem; font-size: 0.98rem; color: #24364b; }}
    .employee-detail {{ gap: 0.85rem; }}
    .object-actions {{ display: flex; gap: 0.55rem; flex-wrap: wrap; justify-content: flex-start; margin-top: 0.7rem; }}
    .detail-section .section-header {{ display: flex; justify-content: space-between; align-items: center; gap: 0.8rem; }}
    .detail-section-actions {{ display: flex; gap: 0.5rem; flex-wrap: wrap; }}
    .detail-grid {{ display: grid; gap: 0.7rem; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); }}
    .detail-field, .sap-readonly-field {{ border: 1px solid var(--border); border-radius: 10px; background: #f8fafc; padding: 10px 12px; min-width: 0; box-shadow: var(--shadow-soft); }}
    .detail-field.long {{ grid-column: span 2; }}
    .detail-label {{ color: var(--muted); font-size: 0.78rem; font-weight: 800; letter-spacing: 0.025em; text-transform: uppercase; margin-bottom: 0.24rem; }}
    .detail-value {{ color: var(--text); font-size: 0.98rem; line-height: 1.42; min-height: 1.2rem; overflow-wrap: anywhere; white-space: pre-wrap; }}
    .detail-value.empty {{ color: var(--muted); }}
    .table-scroll, .wide {{ overflow-x: auto; border: 1px solid #e5edf6; border-radius: 12px; }}
    .documents-table {{ min-width: 1050px; }}
    .documents-table th, .documents-table td {{ padding: 0.58rem 0.65rem; font-size: 0.95rem; }}
    .history-section .muted {{ margin: 0 0 0.55rem; }}
    .form-actions, .sap-toolbar {{ border: 1px solid var(--border); border-radius: 14px; background: var(--surface); padding: 0.85rem 1rem; display: flex; gap: 0.65rem; justify-content: flex-end; align-items: center; box-shadow: var(--shadow-soft); }}
    .sap-confirm-backdrop {{ position: fixed; inset: 0; background: rgba(15, 23, 42, 0.48); display: none; align-items: center; justify-content: center; padding: 1rem; z-index: 50; }}
    .sap-confirm-backdrop.active {{ display: flex; }}
    .sap-confirm-dialog {{ width: min(460px, 100%); background: white; border-radius: 18px; box-shadow: 0 24px 80px rgba(15, 23, 42, 0.28); border: 1px solid var(--border); padding: 1.2rem; }}
    .sap-confirm-dialog h3 {{ margin: 0 0 0.5rem; color: var(--navy); }}
    .sap-confirm-dialog p {{ margin: 0 0 1rem; color: var(--muted); }}
    @media (max-width: 720px) {{
      main {{ padding: 1rem; }}
      .site-header {{ padding: 14px 16px; }}
      .top-nav {{ display: block; }}
      .primary-nav, .language-switcher {{ flex-wrap: nowrap; overflow-x: auto; padding-bottom: 4px; }}
      .language-switcher {{ margin: 8px 0 0; justify-content: flex-start; }}
      .site-header nav a, .language-switcher a {{ flex: 0 0 auto; min-height: 42px; white-space: nowrap; }}
      .grid, .form-grid, .form-grid.compact {{ grid-template-columns: 1fr; }}
      .object-header, .sap-page-header {{ display: block; padding: 14px; }}
      .object-meta {{ justify-content: flex-start; margin-top: 0.75rem; }}
      .object-actions {{ justify-content: flex-start; }}
      .detail-section .section-header {{ align-items: flex-start; flex-direction: column; }}
      .detail-grid {{ grid-template-columns: 1fr; }}
      .detail-field.long {{ grid-column: auto; }}
      .actions, .object-actions, .detail-section-actions, .form-actions, .sap-toolbar {{ justify-content: stretch; flex-direction: column; align-items: stretch; }}
      .actions .button, .actions button, .object-actions .button, .object-actions button, .detail-section-actions .button, .detail-section-actions button, .form-actions .button, .form-actions button, .sap-toolbar .button, .sap-toolbar button {{ text-align: center; width: 100%; }}
      table {{ display: block; overflow-x: auto; }}
      body {{ font-size: 16px; }}
      .section-header h3 {{ font-size: 1.08rem; }}
      .field-group {{ padding: 1rem; }}
      .form-field label {{ font-size: 1rem; }}
      .detail-value {{ font-size: 1rem; }}
      .message-strip {{ font-size: 0.98rem; line-height: 1.45; padding: 0.95rem 1rem; margin-bottom: 1rem; border-radius: 12px; }}
      input, select, textarea, .button, button {{ min-height: 46px; }}
    }}
  </style>
</head>
<body>
  {nav}
  <main>
    {notice_html}
    {body}
  </main>
  <div class="sap-confirm-backdrop" id="sapConfirmBackdrop" aria-hidden="true">
    <div class="sap-confirm-dialog" role="dialog" aria-modal="true" aria-labelledby="sapConfirmTitle">
      <h3 id="sapConfirmTitle">{h(t(messages, 'confirm.title', 'Confirm action'))}</h3>
      <p id="sapConfirmText">{h(t(messages, 'confirm.delete_message', 'Please confirm this action.'))}</p>
      <div class="actions">
        <button type="button" class="danger" id="sapConfirmOk">{h(t(messages, 'confirm.ok', 'Confirm'))}</button>
        <button type="button" class="button light" id="sapConfirmCancel">{h(t(messages, 'confirm.cancel', 'Cancel'))}</button>
      </div>
    </div>
  </div>
  <script>
  (() => {{
    const backdrop = document.getElementById('sapConfirmBackdrop');
    const textEl = document.getElementById('sapConfirmText');
    const ok = document.getElementById('sapConfirmOk');
    const cancel = document.getElementById('sapConfirmCancel');
    let pendingForm = null;
    document.addEventListener('submit', (event) => {{
      const form = event.target;
      if (!form || !form.matches('[data-confirm]')) return;
      event.preventDefault();
      pendingForm = form;
      textEl.textContent = form.getAttribute('data-confirm') || textEl.textContent;
      backdrop.classList.add('active');
      backdrop.setAttribute('aria-hidden', 'false');
      ok.focus();
    }});
    ok.addEventListener('click', () => {{ if (pendingForm) {{ const f = pendingForm; pendingForm = null; f.submit(); }} }});
    cancel.addEventListener('click', () => {{ pendingForm = null; backdrop.classList.remove('active'); backdrop.setAttribute('aria-hidden', 'true'); }});
    backdrop.addEventListener('click', (event) => {{ if (event.target === backdrop) cancel.click(); }});
  }})();
  </script>
  <script>
  (() => {{
    document.querySelectorAll('input[type="file"][data-file-preview]').forEach((input) => {{
      const target = document.getElementById(input.getAttribute('data-file-preview'));
      if (!target) return;
      const emptyText = {json.dumps(t(messages, 'onboarding.file_preview_empty', 'No files selected yet.'))};
      const selectedText = {json.dumps(t(messages, 'onboarding.selected_files', 'Selected files'))};
      const limitText = {json.dumps(t(messages, 'onboarding.upload_limits_short', 'Allowed: pdf, jpg, jpeg, png, doc, docx, xls, xlsx, txt. Max 10 MB per file, 10 files per upload.'))};
      target.textContent = emptyText;
      input.addEventListener('change', () => {{
        const files = Array.from(input.files || []);
        if (!files.length) {{ target.textContent = emptyText; return; }}
        const list = files.map((file) => `<li>${{file.name}} — ${{Math.ceil(file.size / 1024)}} KB</li>`).join('');
        target.innerHTML = `<strong>${{selectedText}}</strong><ul>${{list}}</ul><p class="muted">${{limitText}}</p>`;
      }});
    }});
  }})();
  </script>
  <script>
  (() => {{
    function eventPosition(event, canvas) {{
      const rect = canvas.getBoundingClientRect();
      const point = event.touches && event.touches.length ? event.touches[0] : event;
      return {{ x: point.clientX - rect.left, y: point.clientY - rect.top }};
    }}
    document.querySelectorAll('.signature-form').forEach((form) => {{
      const canvas = document.getElementById(form.getAttribute('data-canvas'));
      const input = document.getElementById(form.getAttribute('data-input'));
      if (!canvas || !input) return;
      const context = canvas.getContext('2d');
      let drawing = false;
      let dirty = false;
      context.lineWidth = 2.2;
      context.lineCap = 'round';
      context.strokeStyle = '#0f172a';
      const start = (event) => {{ event.preventDefault(); drawing = true; const pos = eventPosition(event, canvas); context.beginPath(); context.moveTo(pos.x, pos.y); }};
      const move = (event) => {{ if (!drawing) return; event.preventDefault(); const pos = eventPosition(event, canvas); context.lineTo(pos.x, pos.y); context.stroke(); dirty = true; }};
      const end = (event) => {{ if (!drawing) return; event.preventDefault(); drawing = false; input.value = dirty ? canvas.toDataURL('image/png') : ''; }};
      canvas.addEventListener('mousedown', start);
      canvas.addEventListener('mousemove', move);
      canvas.addEventListener('mouseup', end);
      canvas.addEventListener('mouseleave', end);
      canvas.addEventListener('touchstart', start, {{ passive: false }});
      canvas.addEventListener('touchmove', move, {{ passive: false }});
      canvas.addEventListener('touchend', end, {{ passive: false }});
      const clearButton = form.querySelector('.signature-clear');
      if (clearButton) clearButton.addEventListener('click', () => {{ context.clearRect(0, 0, canvas.width, canvas.height); dirty = false; input.value = ''; }});
      form.addEventListener('submit', (event) => {{ if (!dirty || !input.value) {{ event.preventDefault(); canvas.focus(); alert({json.dumps(t(messages, 'onboarding.signature_required', 'Please draw your signature before submitting.'))}); }} }});
    }});
  }})();
  </script>
</body>
</html>"""
    return html.encode("utf-8")


class EmployeeAdminHandler(BaseHTTPRequestHandler):
    server_version = "TACEmployeeAdmin/0.3"

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
        allowed_hosts = LOCAL_ALLOWED_HOSTS | CONFIGURED_PUBLIC_HOSTS | {
            base_url_host(APP_BASE_URL),
            base_url_host(PORTAL_BASE_URL),
            base_url_host(USER_ADMIN_BASE_URL),
            base_url_host(MASTERDATA_BASE_URL),
        }
        allowed_hosts.discard("")
        if host in allowed_hosts and parsed.port in LOCAL_ALLOWED_PORTS:
            return True
        return parsed.scheme == "https" and host in allowed_hosts and parsed.port in {None, 443}

    def current_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return session_cookie.value if session_cookie else ""

    def current_onboarding_verification_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(ONBOARDING_VERIFICATION_COOKIE)
        return session_cookie.value if session_cookie else ""

    def onboarding_verification_cookie_header(self, session_id: str) -> str:
        cookie = SimpleCookie()
        cookie[ONBOARDING_VERIFICATION_COOKIE] = session_id
        cookie[ONBOARDING_VERIFICATION_COOKIE]["path"] = "/onboarding/token"
        cookie[ONBOARDING_VERIFICATION_COOKIE]["httponly"] = True
        cookie[ONBOARDING_VERIFICATION_COOKIE]["samesite"] = "Lax"
        if urlparse(APP_BASE_URL).scheme == "https":
            cookie[ONBOARDING_VERIFICATION_COOKIE]["secure"] = True
        return cookie.output(header="").strip()

    def candidate_request_verified(self, request: dict[str, str]) -> bool:
        session_id = self.current_onboarding_verification_session_id()
        stored_hash = request.get("verification_session_id_hash", "")
        return bool(session_id and stored_hash and hmac.compare_digest(stored_hash, hash_onboarding_verification_session(session_id)))

    def current_user(self) -> dict[str, Any] | None:
        return validate_user_admin_session(self.current_session_id())

    def require_user_admin_access(self, lang: str, messages: dict[str, str]) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.redirect(f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            return None
        if not has_required_module_access(user):
            self.send_forbidden(lang, messages)
            return None
        return user

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        path = parsed.path
        parts = [part for part in path.split("/") if part]

        if path == "/health":
            self.send_text(200, "OK")
            return
        if len(parts) >= 3 and parts[0] == "onboarding" and parts[1] == "token":
            self.handle_candidate_onboarding_get(lang, messages, parts, query)
            return
        if path in {"/master-data/system-parameters", "/master-data/system-parameters/email-onboarding"}:
            self.redirect(f"{MASTERDATA_BASE_URL}{url_with_lang(path, lang)}")
            return
        if path == "/api/payroll/employees":
            user = self.current_user()
            if not user:
                self.send_json(401, {"error": "authentication_required"})
                return
            if not (has_permission(user, "employee_management.access") or has_permission(user, "employee_management.view") or has_permission(user, "payroll.access")):
                self.send_json(403, {"error": "forbidden"})
                return
            self.send_json(200, payroll_employee_api_payload(query, self.current_session_id(), lang))
            return

        user = self.require_user_admin_access(lang, messages)
        if not user:
            return

        if path.startswith("/reports") and not has_permission(user, "employee_management.reports.view"):
            self.send_forbidden(lang, messages)
            return
        if path in {"/exports/employees.csv", "/employees.json"} and not has_permission(user, "employee_management.export"):
            self.send_forbidden(lang, messages)
            return
        if path in {"/exports/employees-import-template.csv", "/exports/employees-import-field-guide.csv", "/exports/employees-import-sample.csv"} and not has_permission(user, "employee_management.edit"):
            self.send_forbidden(lang, messages)
            return
        if path in {"/audit-logs", "/audit_logs.json"} and not has_permission(user, "employee_management.audit.view"):
            self.send_forbidden(lang, messages)
            return

        if path == "/api/masterdata/entities":
            entities, error = fetch_masterdata_entities(self.current_session_id())
            self.send_json(503 if error else 200, {"error": t(messages, error)} if error else entities)
        elif path == "/api/masterdata/departments":
            departments, error = fetch_masterdata_departments(self.current_session_id(), query.get("entity_id", [""])[0])
            self.send_json(503 if error else 200, {"error": t(messages, error)} if error else departments)
        elif path == "/api/masterdata/teams":
            teams, error = fetch_masterdata_teams(self.current_session_id(), query.get("department_id", [""])[0])
            self.send_json(503 if error else 200, {"error": t(messages, error)} if error else teams)
        elif path == "/api/timesheet/employees":
            self.send_json(200, timesheet_employee_api_payload(self.current_session_id(), lang))
        elif path == "/api/useradmin/employees":
            if not (has_permission(user, "employee_management.view") or has_permission(user, "user_management.manage_users")):
                self.send_forbidden(lang, messages)
                return
            self.send_json(200, useradmin_employee_api_payload(query, self.current_session_id(), lang))
        elif path == "/api/payroll/employees":
            if not (has_permission(user, "employee_management.view") or has_permission(user, "employee_management.access")):
                self.send_forbidden(lang, messages)
                return
            self.send_json(200, payroll_employee_api_payload(query, self.current_session_id(), lang))
        elif path == "/api/timesheet/dispatch-assignment":
            status, payload = timesheet_dispatch_assignment_api_payload(
                query.get("employee_no", [""])[0],
                query.get("work_date", [""])[0],
                query.get("employee_id", [""])[0],
                query.get("entity_id", [""])[0],
            )
            self.send_json(status, payload)
        elif path == "/employees.json":
            self.send_json(200, load_employees())
        elif path == "/audit_logs.json":
            self.send_json(200, load_audit_logs())
        elif path in {"/", "/dashboard"}:
            self.send_dashboard(lang, messages)
        elif path == "/onboarding":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_onboarding_list(lang, messages, query, user)
        elif path == "/onboarding/new":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_onboarding_new_form(lang, messages, default_onboarding_request(), [])
        elif len(parts) == 5 and parts[0] == "onboarding" and parts[2] == "documents" and parts[4] in {"open", "download", "evidence", "signed-pdf"}:
            if not has_permission(user, "employee_management.documents.manage"):
                self.send_forbidden(lang, messages)
                return
            document = find_onboarding_document(parts[1], parts[3])
            if not document:
                self.send_not_found(lang, messages)
                return
            if parts[4] == "evidence":
                self.send_onboarding_document_file(lang, messages, document, "evidence")
            else:
                self.send_onboarding_document_file(lang, messages, document, parts[4])
        elif len(parts) == 3 and parts[0] == "onboarding" and parts[2] == "review":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_onboarding_review(lang, messages, parts[1], user)
        elif len(parts) == 3 and parts[0] == "onboarding" and parts[2] == "email-draft":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_onboarding_email_draft(lang, messages, parts[1], user, prepare_fresh=query.get("fresh", [""])[0] == "1")
        elif len(parts) == 2 and parts[0] == "onboarding":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_onboarding_detail(lang, messages, parts[1], user)
        elif path == "/employees":
            self.send_employee_list(lang, messages, query, user)
        elif path == "/employees/new":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_employee_form(lang, messages, default_employee(), [], "create")
        elif path == "/employees/import":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_employee_import_page(lang, messages)
        elif path == "/reports":
            if not has_permission(user, "employee_management.reports.view"):
                self.send_forbidden(lang, messages)
                return
            self.send_reports_index(lang, messages)
        elif path == "/reports/missing-required-data":
            if not has_permission(user, "employee_management.reports.view"):
                self.send_forbidden(lang, messages)
                return
            self.send_missing_required_data_report(lang, messages)
        elif path == "/reports/visa-expiry":
            self.send_visa_expiry_report(lang, messages)
        elif path == "/reports/probation-ending":
            self.send_probation_ending_report(lang, messages)
        elif path == "/reports/labor-contract-renewals":
            self.send_labor_contract_renewal_report(lang, messages)
        elif path == "/reports/dispatch-assignments":
            self.send_dispatch_assignment_report(lang, messages)
        elif path == "/reports/document-expiry":
            self.send_document_expiry_report(lang, messages)
        elif path == "/reports/missing-documents":
            self.send_missing_documents_report(lang, messages)
        elif path == "/reports/data-quality":
            self.send_data_quality_report(lang, messages)
        elif path == "/reports/data-completion":
            self.send_data_completion_report(lang, messages)
        elif path == "/reports/payroll-readiness":
            self.send_payroll_readiness_report(lang, messages)
        elif path == "/reports/required-document-matrix":
            self.send_required_document_matrix_report(lang, messages)
        elif path == "/exports/employees.csv":
            self.send_employee_master_csv()
        elif path == "/exports/employees-import-template.csv":
            self.send_employee_import_template_csv(query, lang)
        elif path == "/exports/employees-import-field-guide.csv":
            self.send_employee_import_field_guide_csv(query, lang, messages)
        elif path == "/exports/employees-import-sample.csv":
            self.send_employee_import_sample_csv(query, lang)
        elif path == "/audit-logs":
            self.send_audit_logs_page(lang, messages)
        elif len(parts) == 8 and parts[0] == "employees" and parts[2] == "history" and parts[5] == "attachments" and parts[7] in {"open", "download"}:
            if not has_permission(user, "employee_management.documents.manage"):
                self.send_forbidden(lang, messages)
                return
            self.send_employee_history_attachment_file(lang, messages, parts[1], parts[3], parts[4], parts[6], parts[7])
        elif len(parts) == 5 and parts[0] == "employees" and parts[2] == "history" and parts[4] == "new":
            config = HISTORY_CONFIG.get(parts[3])
            if not config:
                self.send_not_found(lang, messages)
                return
            if not has_permission(user, str(config["permission"])):
                self.send_forbidden(lang, messages)
                return
            self.send_history_form(lang, messages, parts[1], parts[3], None, [])
        elif len(parts) == 6 and parts[0] == "employees" and parts[2] == "history" and parts[5] == "edit":
            config = HISTORY_CONFIG.get(parts[3])
            if not config:
                self.send_not_found(lang, messages)
                return
            if not has_permission(user, str(config["permission"])):
                self.send_forbidden(lang, messages)
                return
            self.send_history_form(lang, messages, parts[1], parts[3], parts[4], [])
        elif len(parts) == 5 and parts[0] == "employees" and parts[2] == "documents" and parts[4] in {"open", "download"}:
            if not has_permission(user, "employee_management.documents.manage"):
                self.send_forbidden(lang, messages)
                return
            self.send_employee_document_file(lang, messages, parts[1], parts[3], parts[4])
        elif len(parts) == 4 and parts[0] == "employees" and parts[2] in SECTION_CONFIG and parts[3] == "edit":
            section_permission = {
                "payroll": "employee_management.payroll.edit",
                "visa": "employee_management.visa.edit",
                "documents": "employee_management.documents.manage",
            }.get(parts[2], "employee_management.edit")
            if not has_permission(user, section_permission):
                self.send_forbidden(lang, messages)
                return
            self.send_section_form(lang, messages, parts[1], parts[2], [])
        elif len(parts) == 3 and parts[0] == "employees" and parts[2] == "edit":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.send_edit_employee(lang, messages, parts[1])
        elif len(parts) == 2 and parts[0] == "employees":
            self.send_employee_detail(lang, messages, parts[1], user)
        else:
            self.send_not_found(lang, messages)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang_from_query(query)
        messages = load_i18n(lang)
        path = parsed.path
        parts = [part for part in path.split("/") if part]

        content_type = self.headers.get("Content-Type", "")
        try:
            content_length = int(self.headers.get("Content-Length", "0") or "0")
        except ValueError:
            content_length = 0
        if not content_type.startswith("multipart/form-data") and content_length > MAX_FORM_REQUEST_BYTES:
            self.send_text(413, "Request body too large")
            return
        if not self.csrf_origin_allowed():
            self.send_forbidden(lang, messages)
            return
        if len(parts) >= 3 and parts[0] == "onboarding" and parts[1] == "token":
            self.handle_candidate_onboarding_post(lang, messages, parts)
            return

        user = self.require_user_admin_access(lang, messages)
        if not user:
            return

        if path == "/onboarding/new":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_create_onboarding_request(lang, messages, user)
        elif path in {"/master-data/system-parameters/email-onboarding", "/master-data/system-parameters/email-onboarding/test"}:
            self.send_not_found(lang, messages)
            return
        elif len(parts) == 3 and parts[0] == "onboarding" and parts[2] == "send":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_generate_link(lang, messages, parts[1], user)
        elif len(parts) == 4 and parts[0] == "onboarding" and parts[2] == "email-draft" and parts[3] == "send":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_email_draft_send(lang, messages, parts[1], user)
        elif len(parts) == 3 and parts[0] == "onboarding" and parts[2] == "manual-email-package":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_manual_email_package(lang, messages, parts[1], user)
        elif len(parts) == 4 and parts[0] == "onboarding" and parts[2] == "documents" and parts[3] == "upload":
            if not has_permission(user, "employee_management.documents.manage"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_document_upload(lang, messages, parts[1], user)
        elif len(parts) == 4 and parts[0] == "onboarding" and parts[2] == "review" and parts[3] == "return":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_return(lang, messages, parts[1], user)
        elif len(parts) == 4 and parts[0] == "onboarding" and parts[2] == "review" and parts[3] == "approve":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_approve(lang, messages, parts[1], user)
        elif len(parts) == 3 and parts[0] == "onboarding" and parts[2] == "import":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_onboarding_import(lang, messages, parts[1], user)
        elif path == "/employees/new":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_create_employee(lang, messages, user)
        elif path == "/employees/import":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_employee_import(lang, messages, user)
        elif len(parts) == 5 and parts[0] == "employees" and parts[2] == "history" and parts[4] == "new":
            config = HISTORY_CONFIG.get(parts[3])
            if not config:
                self.send_not_found(lang, messages)
                return
            if not has_permission(user, str(config["permission"])):
                self.send_forbidden(lang, messages)
                return
            self.handle_create_history_record(lang, messages, parts[1], parts[3], user)
        elif len(parts) == 6 and parts[0] == "employees" and parts[2] == "history" and parts[5] == "edit":
            config = HISTORY_CONFIG.get(parts[3])
            if not config:
                self.send_not_found(lang, messages)
                return
            if not has_permission(user, str(config["permission"])):
                self.send_forbidden(lang, messages)
                return
            self.handle_update_history_record(lang, messages, parts[1], parts[3], parts[4], user)
        elif len(parts) == 4 and parts[0] == "employees" and parts[2] in SECTION_CONFIG and parts[3] == "edit":
            section_permission = {
                "payroll": "employee_management.payroll.edit",
                "visa": "employee_management.visa.edit",
                "documents": "employee_management.documents.manage",
            }.get(parts[2], "employee_management.edit")
            if not has_permission(user, section_permission):
                self.send_forbidden(lang, messages)
                return
            self.handle_update_section(lang, messages, parts[1], parts[2], user)
        elif len(parts) == 3 and parts[0] == "employees" and parts[2] == "edit":
            if not has_permission(user, "employee_management.edit"):
                self.send_forbidden(lang, messages)
                return
            self.handle_update_employee(lang, messages, parts[1], user)
        else:
            self.send_not_found(lang, messages)


    def handle_candidate_onboarding_get(self, lang: str, messages: dict[str, str], parts: list[str], query: dict[str, list[str]]) -> None:
        token = unquote(parts[2]) if len(parts) >= 3 else ""
        request = find_onboarding_request_by_token(token)
        if not request:
            self.send_invalid_onboarding_link(lang, messages)
            return
        if request.get("status") in {"ready_to_send", "sent", "returned_to_candidate"}:
            update_onboarding_request(request["onboarding_request_id"], {"status": "opened", "token_last_used_at": now_iso()})
            append_module_audit_log("onboarding_request", request["onboarding_request_id"], "onboarding_link_opened", ["status", "token_last_used_at"], "Candidate opened onboarding link", request, {**request, "status": "opened", "token_last_used_at": now_iso()}, f"candidate:{request['onboarding_request_id']}")
            request = find_onboarding_request(load_onboarding_requests(), request["onboarding_request_id"]) or request
        if len(parts) == 4 and parts[3] == "verify":
            self.send_candidate_verification_form(lang, messages, token, request, [])
            return
        if not self.candidate_request_verified(request):
            self.send_candidate_verification_form(lang, messages, token, request, [])
            return
        if len(parts) == 3:
            self.send_candidate_onboarding_form(lang, messages, token, request, [])
            return
        if len(parts) == 4 and parts[3] == "form":
            self.send_candidate_onboarding_form(lang, messages, token, request, [])
            return
        if len(parts) == 6 and parts[3] == "documents" and parts[5] in {"open", "download", "signed-pdf"}:
            document = find_onboarding_document(request["onboarding_request_id"], parts[4])
            if not document or document.get("direction") != "hr_to_candidate":
                self.send_not_found(lang, messages)
                return
            self.send_onboarding_document_file(lang, messages, document, parts[5])
            if parts[5] in {"open", "download"}:
                status = "downloaded_by_candidate" if parts[5] == "download" else "viewed_by_candidate"
                self.update_onboarding_document_status(document, status, f"candidate:{request['onboarding_request_id']}")
            return
        self.send_not_found(lang, messages)

    def handle_candidate_onboarding_post(self, lang: str, messages: dict[str, str], parts: list[str]) -> None:
        token = unquote(parts[2]) if len(parts) >= 3 else ""
        request = find_onboarding_request_by_token(token)
        if not request:
            self.send_invalid_onboarding_link(lang, messages)
            return
        actor = f"candidate:{request['onboarding_request_id']}"
        if len(parts) == 5 and parts[3] == "verify" and parts[4] == "send-code":
            self.handle_candidate_send_verification_code(lang, messages, token, request, actor)
            return
        if len(parts) == 5 and parts[3] == "verify" and parts[4] == "confirm":
            self.handle_candidate_confirm_verification_code(lang, messages, token, request, actor)
            return
        if not self.candidate_request_verified(request):
            self.send_candidate_verification_form(lang, messages, token, request, [t(messages, "onboarding.verification_required")])
            return
        if len(parts) == 5 and parts[3] == "form" and parts[4] in {"save", "submit"}:
            form, uploads, request_errors = self.parse_request_body(messages)
            errors = request_errors + validate_upload_parts(uploads, messages)
            if "my_number" in " ".join(form.keys()).lower():
                errors.append(t(messages, "onboarding.mynumber_disabled"))
            docs: list[dict[str, str]] = []
            writes: list[tuple[Path, bytes]] = []
            if uploads and not errors:
                docs, writes = uploaded_onboarding_documents_from_parts(request["onboarding_request_id"], form, uploads, "candidate_to_hr", actor)
            if parts[4] == "submit" and not errors:
                employee_preview = onboarding_employee_from_form(form)
                errors.extend(candidate_onboarding_completion_errors(employee_preview, load_onboarding_documents() + docs, messages))
            if errors:
                self.send_candidate_onboarding_form(lang, messages, token, request, errors)
                return
            status = "pending_hr_review" if parts[4] == "submit" else "draft"
            submission = save_onboarding_submission_form(request["onboarding_request_id"], form, status)
            if docs:
                try:
                    write_onboarding_uploaded_files(writes)
                except Exception:
                    self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "validation.upload_save_failed")])
                    return
                all_docs = load_onboarding_documents() + docs
                save_onboarding_documents(all_docs)
            new_status = "pending_hr_review" if parts[4] == "submit" else "in_progress"
            update_onboarding_request(request["onboarding_request_id"], {"status": new_status, "token_last_used_at": now_iso()})
            append_module_audit_log("onboarding_submission", submission["submission_id"], "onboarding_candidate_submitted" if parts[4] == "submit" else "onboarding_candidate_saved", ["status", "form_data"], f"Candidate {'submitted' if parts[4] == 'submit' else 'saved'} onboarding package", None, submission, actor)
            if parts[4] == "submit":
                sent, email_status = send_onboarding_email(
                    current_hr_notification_email(),
                    f"Onboarding completed: {request.get('candidate_name', '')}",
                    onboarding_completion_email_body(request),
                )
                notification_status = f"hr_notification_{email_status}"
                update_onboarding_request(request["onboarding_request_id"], {"email_status": notification_status, "updated_at": now_iso()})
                append_module_audit_log("onboarding_request", request["onboarding_request_id"], "hr_completion_notification_sent" if sent else "hr_completion_notification_prepared", ["email_status"], f"HR completion notification {email_status}", None, {"email_status": notification_status}, actor)
                self.send_candidate_submitted(lang, messages, request)
            else:
                self.redirect(url_with_lang(f"/onboarding/token/{quote(token)}/form", lang), t(messages, "onboarding.saved"))
            return
        if len(parts) == 6 and parts[3] == "documents" and parts[5] in {"sign", "manual-signed-upload"}:
            document = find_onboarding_document(request["onboarding_request_id"], parts[4])
            if not document or document.get("direction") != "hr_to_candidate":
                self.send_not_found(lang, messages)
                return
            if parts[5] == "sign":
                self.handle_candidate_document_signature(lang, messages, token, request, document, actor)
                return
            self.handle_candidate_manual_signed_upload(lang, messages, token, request, document, actor)
            return
        self.send_not_found(lang, messages)

    def send_invalid_onboarding_link(self, lang: str, messages: dict[str, str]) -> None:
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'onboarding.invalid_link_title'))}</h2>
  <p class="muted">{h(t(messages, 'onboarding.invalid_link_description'))}</p>
</section>
"""
        self.send_html(404, t(messages, "onboarding.invalid_link_title"), body, lang, messages)

    def send_candidate_verification_form(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], errors: list[str], notice: str = "") -> None:
        send_action = url_with_lang(f"/onboarding/token/{quote(token)}/verify/send-code", lang)
        confirm_action = url_with_lang(f"/onboarding/token/{quote(token)}/verify/confirm", lang)
        locked = onboarding_verification_locked(request)
        status_note = notice or t(messages, f"onboarding.verification_status.{request.get('verification_delivery_status', '')}", "")
        locked_note = f'<p class="message-strip message-warning">{h(t(messages, "onboarding.verification_locked"))}</p>' if locked else ""
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'onboarding.verification_title'))}</h2>
  <p class="muted">{h(t(messages, 'onboarding.verification_description'))}</p>
  <p><strong>{h(t(messages, 'onboarding.candidate_email'))}:</strong> {h(masked_email(request.get('candidate_email', '')))}</p>
  {self.render_errors(messages, errors)}
  {locked_note}
  <p class="muted">{h(status_note)}</p>
</section>
<section class="card">
  <h3>{h(t(messages, 'onboarding.verification_send_code'))}</h3>
  <form method="post" action="{h(send_action)}"><button type="submit">{h(t(messages, 'onboarding.verification_send_code'))}</button></form>
</section>
<section class="card">
  <h3>{h(t(messages, 'onboarding.verification_confirm'))}</h3>
  <form method="post" action="{h(confirm_action)}" class="employee-form">
    <div class="form-field"><label>{h(t(messages, 'onboarding.verification_code'))}</label><input name="verification_code" inputmode="numeric" pattern="[0-9]{{6}}" maxlength="6" required></div>
    <button type="submit">{h(t(messages, 'onboarding.verification_confirm'))}</button>
  </form>
</section>
"""
        self.send_html(200, t(messages, "onboarding.verification_title"), body, lang, messages)

    def handle_candidate_send_verification_code(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], actor: str) -> None:
        if onboarding_verification_locked(request):
            self.send_candidate_verification_form(lang, messages, token, request, [t(messages, "onboarding.verification_locked")])
            return
        code = generate_onboarding_verification_code()
        now = now_iso()
        expiry = onboarding_verification_expiry()
        updates = {
            "verification_code_hash": hash_onboarding_verification_code(request["onboarding_request_id"], code),
            "verification_code_created_at": now,
            "verification_code_expiry": expiry,
            "verification_attempts": "0",
            "verification_locked_until": "",
            "verification_last_sent_at": now,
            "verification_delivery_status": "prepared",
            "verification_verified_at": "",
            "verification_session_id_hash": "",
            "updated_at": now,
        }
        candidate = {**request, **updates}
        before = copy.deepcopy(request)
        prepared = update_onboarding_request(request["onboarding_request_id"], updates) or candidate
        sent, email_status = send_onboarding_email(
            request.get("candidate_email", ""),
            f"TAC onboarding verification code: {request.get('candidate_name', '')}",
            onboarding_verification_email_body(prepared, code),
        )
        delivery_updates = {"verification_delivery_status": "sent" if sent else f"manual_required_{email_status}", "updated_at": now_iso()}
        updated = update_onboarding_request(request["onboarding_request_id"], delivery_updates) or {**prepared, **delivery_updates}
        append_module_audit_log("onboarding_request", request["onboarding_request_id"], "candidate_email_verification_code_sent" if sent else "candidate_email_verification_code_prepared", ["verification_delivery_status", "verification_code_expiry"], f"Candidate verification code delivery {email_status}", before, updated, actor)
        notice = t(messages, "onboarding.verification_sent") if sent else t(messages, "onboarding.verification_manual_required")
        self.send_candidate_verification_form(lang, messages, token, updated, [], notice)

    def handle_candidate_confirm_verification_code(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], actor: str) -> None:
        if onboarding_verification_locked(request):
            self.send_candidate_verification_form(lang, messages, token, request, [t(messages, "onboarding.verification_locked")])
            return
        form = self.parse_form_body()
        code = str(form.get("verification_code", "") or "").strip()
        if not re.fullmatch(r"\d{6}", code) or not onboarding_verification_code_valid(request):
            self.record_candidate_verification_failure(lang, messages, token, request, actor, "expired" if not onboarding_verification_code_valid(request) else "invalid")
            return
        expected = request.get("verification_code_hash", "")
        actual = hash_onboarding_verification_code(request["onboarding_request_id"], code)
        if not expected or not hmac.compare_digest(expected, actual):
            self.record_candidate_verification_failure(lang, messages, token, request, actor, "invalid")
            return
        session_id = secrets.token_urlsafe(32)
        updates = {
            "verification_code_hash": "",
            "verification_attempts": "0",
            "verification_locked_until": "",
            "verification_verified_at": now_iso(),
            "verification_session_id_hash": hash_onboarding_verification_session(session_id),
            "updated_at": now_iso(),
        }
        before = copy.deepcopy(request)
        updated = update_onboarding_request(request["onboarding_request_id"], updates) or {**request, **updates}
        append_module_audit_log("onboarding_request", request["onboarding_request_id"], "candidate_email_verified", ["verification_verified_at"], "Candidate email verification succeeded", before, updated, actor)
        self.redirect(url_with_lang(f"/onboarding/token/{quote(token)}/form", lang), t(messages, "onboarding.verification_success"), self.onboarding_verification_cookie_header(session_id))

    def record_candidate_verification_failure(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], actor: str, reason: str) -> None:
        attempts = onboarding_verification_attempts(request) + 1
        updates = {"verification_attempts": str(attempts), "updated_at": now_iso()}
        error_key = "onboarding.verification_expired" if reason == "expired" else "onboarding.verification_invalid"
        action = "candidate_email_verification_failed"
        if attempts >= ONBOARDING_VERIFICATION_MAX_ATTEMPTS:
            updates["verification_locked_until"] = onboarding_verification_lock_expiry()
            error_key = "onboarding.verification_locked"
            action = "candidate_email_verification_locked"
        before = copy.deepcopy(request)
        updated = update_onboarding_request(request["onboarding_request_id"], updates) or {**request, **updates}
        append_module_audit_log("onboarding_request", request["onboarding_request_id"], action, ["verification_attempts", "verification_locked_until"], f"Candidate verification failed: {reason}", before, updated, actor)
        self.send_candidate_verification_form(lang, messages, token, updated, [t(messages, error_key)])

    def handle_candidate_document_signature(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], document: dict[str, str], actor: str) -> None:
        if document.get("signing_mode") not in {"electronic_signature_required", "electronic_signature_optional"}:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "onboarding.signature_not_allowed")])
            return
        form = self.parse_form_body()
        if form.get("electronic_consent") != "1":
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "onboarding.signature_consent_required")])
            return
        signature_data = str(form.get("signature_data", "") or "").strip()
        signer_name = str(form.get("signer_name", "") or request.get("candidate_name", "")).strip()
        signer_email = str(form.get("signer_email", "") or request.get("candidate_email", "")).strip()
        if not signature_data.startswith("data:image/png;base64,") or len(signature_data) > 750000:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "onboarding.signature_required")])
            return
        try:
            decoded_signature = base64.b64decode(signature_data.split(",", 1)[1], validate=True)
        except Exception:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "onboarding.signature_required")])
            return
        if len(decoded_signature) < 200:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "onboarding.signature_required")])
            return
        try:
            evidence_filename, before_hash, evidence_hash, signed_at = write_onboarding_signature_evidence(request, document, signer_name, signer_email, signature_data, self.headers.get("User-Agent", ""))
        except Exception:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "validation.upload_save_failed")])
            return
        signed_pdf_info = write_onboarding_signed_pdf(request, document, signer_name, signer_email, decoded_signature, signed_at, before_hash, evidence_hash)
        signatures = load_onboarding_signatures()
        signature = {
            "signature_id": next_onboarding_signature_id(signatures),
            "onboarding_request_id": request["onboarding_request_id"],
            "document_id": document["document_id"],
            "signer_name": signer_name,
            "signer_email": signer_email,
            "signature_method": "drawn_signature_pad",
            "consent_text_version": "electronic_signature_consent_v1",
            "signed_at": signed_at,
            "ip_address": self.client_address[0] if self.client_address else "",
            "user_agent": self.headers.get("User-Agent", ""),
            "document_sha256_before": before_hash,
            "document_sha256_after": evidence_hash,
            "evidence_status": "captured",
            "evidence_storage_reference": onboarding_relative_path(request["onboarding_request_id"], "evidence", evidence_filename),
            "signed_pdf_status": signed_pdf_info.get("status", ""),
            "signed_pdf_storage_reference": signed_pdf_info.get("storage_reference", ""),
            "signed_pdf_sha256": signed_pdf_info.get("sha256", ""),
        }
        signatures.append(signature)
        save_onboarding_signatures(signatures)
        docs = load_onboarding_documents()
        for index, doc in enumerate(docs):
            if doc.get("document_id") == document.get("document_id"):
                before = copy.deepcopy(doc)
                doc["status"] = "signed_by_candidate"
                doc["signed_stored_filename"] = evidence_filename
                doc["signed_storage_reference"] = signature["evidence_storage_reference"]
                doc["sha256_signed"] = evidence_hash
                doc["signed_pdf_status"] = signed_pdf_info.get("status", "")
                if signed_pdf_info.get("status") == "created":
                    doc["signed_pdf_stored_filename"] = signed_pdf_info.get("stored_filename", "")
                    doc["signed_pdf_storage_reference"] = signed_pdf_info.get("storage_reference", "")
                    doc["signed_pdf_content_type"] = signed_pdf_info.get("content_type", "application/pdf")
                    doc["signed_pdf_file_size_bytes"] = signed_pdf_info.get("file_size_bytes", "")
                    doc["signed_pdf_created_at"] = signed_pdf_info.get("created_at", "")
                    doc["sha256_signed_pdf"] = signed_pdf_info.get("sha256", "")
                docs[index] = normalize_onboarding_document(doc)
                save_onboarding_documents(docs)
                append_module_audit_log("onboarding_signature", signature["signature_id"], "document_signed_by_candidate", ["signature_id", "document_id", "evidence_status", "signed_pdf_status"], f"Candidate signed onboarding document {document['document_id']}", None, signature, actor)
                append_module_audit_log("onboarding_document", document["document_id"], "onboarding_document_signed_electronically", ["status", "signed_storage_reference", "signed_pdf_storage_reference", "signed_pdf_status"], f"Onboarding document electronically signed", before, docs[index], actor)
                if signed_pdf_info.get("status") == "created":
                    append_module_audit_log("onboarding_document", document["document_id"], "onboarding_signed_pdf_generated", ["signed_pdf_storage_reference", "sha256_signed_pdf"], "Generated signed onboarding PDF", before, docs[index], actor)
                else:
                    append_module_audit_log("onboarding_document", document["document_id"], "onboarding_signed_pdf_not_generated", ["signed_pdf_status"], f"Signed PDF not generated: {signed_pdf_info.get('status', '')}", before, docs[index], actor)
                break
        self.redirect(url_with_lang(f"/onboarding/token/{quote(token)}/form", lang), t(messages, "onboarding.signature_saved"))

    def handle_candidate_manual_signed_upload(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], document: dict[str, str], actor: str) -> None:
        form, uploads, request_errors = self.parse_request_body(messages)
        errors = request_errors + validate_upload_parts(uploads, messages)
        if not uploads:
            errors.append(t(messages, "validation.upload_filename_required"))
        if errors:
            self.send_candidate_onboarding_form(lang, messages, token, request, errors)
            return
        form = dict(form)
        form["upload_document_type"] = document.get("document_type", "other")
        form["upload_title"] = f"{document.get('title') or document.get('original_filename') or document.get('document_id')} - signed"
        docs, writes = uploaded_onboarding_documents_from_parts(request["onboarding_request_id"], form, uploads[:1], "manual_signed_upload", actor)
        try:
            write_onboarding_uploaded_files(writes)
        except Exception:
            self.send_candidate_onboarding_form(lang, messages, token, request, [t(messages, "validation.upload_save_failed")])
            return
        save_onboarding_documents(load_onboarding_documents() + docs)
        self.update_onboarding_document_status(document, "manual_signed_upload_received", actor)
        for doc in docs:
            append_module_audit_log("onboarding_document", doc["document_id"], "manual_signed_file_uploaded", ["document_id", "document_type", "status"], f"Candidate uploaded manually signed file for {document['document_id']}", None, doc, actor)
        self.redirect(url_with_lang(f"/onboarding/token/{quote(token)}/form", lang), t(messages, "onboarding.manual_upload_saved"))

    def send_onboarding_list(self, lang: str, messages: dict[str, str], query: dict[str, list[str]], user: dict[str, Any]) -> None:
        requests = load_onboarding_requests()
        rows = []
        for request in sorted(requests, key=lambda item: str(item.get("created_at", "")), reverse=True):
            request_id = request.get("onboarding_request_id", "")
            rows.append(f"""
<tr>
  <td><a href="{h(url_with_lang('/onboarding/' + quote(request_id), lang))}">{h(request_id)}</a></td>
  <td>{h(request.get('candidate_name'))}</td>
  <td>{h(request.get('candidate_email'))}</td>
  <td>{h(request.get('planned_start_date'))}</td>
  <td>{h(enum_label(messages, 'employment_type', request.get('employment_type', '')))}</td>
  <td>{h(enum_label(messages, 'onboarding_status', request.get('status', '')))}</td>
  <td>{h(request.get('email_status'))}</td>
</tr>
""")
        table = "".join(rows) if rows else f'<tr><td colspan="7" class="empty">{h(t(messages, "onboarding.empty"))}</td></tr>'
        body = f"""
<section class="card">
  <div class="actions"><h2>{h(t(messages, 'onboarding.title'))}</h2><a class="button" href="{h(url_with_lang('/onboarding/new', lang))}">{h(t(messages, 'onboarding.new'))}</a></div>
  <p class="muted">{h(t(messages, 'onboarding.description'))}</p>
</section>
<section class="card table-scroll">
  <table><thead><tr><th>ID</th><th>{h(t(messages, 'onboarding.candidate_name'))}</th><th>{h(t(messages, 'onboarding.candidate_email'))}</th><th>{h(t(messages, 'onboarding.planned_start_date'))}</th><th>{h(field_label(messages, 'employment.employment_type'))}</th><th>{h(t(messages, 'onboarding.status'))}</th><th>{h(t(messages, 'onboarding.email_status'))}</th></tr></thead><tbody>{table}</tbody></table>
  <div class="helper-text" style="margin-top:8px">{len(requests)} request(s) total</div>
</section>
"""
        self.send_html(200, t(messages, "onboarding.title"), body, lang, messages)

    def send_onboarding_new_form(self, lang: str, messages: dict[str, str], request: dict[str, str], errors: list[str]) -> None:
        action = url_with_lang("/onboarding/new", lang)
        body = f"""
<section class="object-page">
  {self.render_form_header(messages, 'onboarding.new', 'onboarding.new_description', '')}
  <form class="employee-form" method="post" action="{h(action)}">
    {self.render_errors(messages, errors)}
    <section class="form-section"><div class="section-header"><h3>{h(t(messages, 'onboarding.request_details'))}</h3></div><div class="form-grid">
      <div class="form-field"><label>{h(t(messages, 'onboarding.candidate_name'))}<span class="required-marker">*</span></label><input name="candidate_name" value="{h(request.get('candidate_name'))}" required></div>
      <div class="form-field"><label>{h(t(messages, 'onboarding.candidate_email'))}<span class="required-marker">*</span></label><input type="email" name="candidate_email" value="{h(request.get('candidate_email'))}" required></div>
      <div class="form-field"><label>{h(t(messages, 'onboarding.planned_start_date'))}</label><input type="date" name="planned_start_date" value="{h(request.get('planned_start_date'))}"></div>
      <div class="form-field"><label>{h(field_label(messages, 'employment.employment_type'))}</label><select name="employment_type">{''.join(f'<option value="{h(v)}"{selected(request.get("employment_type"), v)}>{h(enum_label(messages, "employment_type", v))}</option>' for v in EMPLOYMENT_TYPES)}</select></div>
      <div class="form-field"><label>{h(t(messages, 'onboarding.category'))}</label><select name="onboarding_category">{''.join(f'<option value="{h(v)}"{selected(request.get("onboarding_category"), v)}>{h(enum_label(messages, "onboarding_category", v))}</option>' for v in ONBOARDING_CATEGORIES)}</select></div>
      <div class="form-field"><label>{h(t(messages, 'onboarding.hr_notes'))}</label><textarea name="hr_notes">{h(request.get('hr_notes'))}</textarea></div>
    </div></section>
    {self.render_form_actions(messages, url_with_lang('/onboarding', lang))}
  </form>
</section>
"""
        self.send_html(200, t(messages, "onboarding.new"), body, lang, messages)

    def render_onboarding_readiness(self, messages: dict[str, str], request: dict[str, str], documents: list[dict[str, str]]) -> str:
        rows = []
        for ok, text in onboarding_readiness_items(request, documents, messages):
            badge_class = "success" if ok else "alert"
            badge_text = t(messages, "documents.requirement_complete") if ok else t(messages, "documents.requirement_missing")
            rows.append(f"<li><span class=\"badge {badge_class}\">{h(badge_text)}</span> {h(text)}</li>")
        items = "".join(rows)
        public_note = t(messages, "onboarding.readiness_public_test_note")
        return f"""
<section class="card">
  <h3>{h(t(messages, 'onboarding.readiness_title'))}</h3>
  <p class="muted">{h(public_note)}</p>
  <ul class="compact-list">{items}</ul>
</section>
"""

    def send_onboarding_detail(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any], errors: list[str] | None = None) -> None:
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        docs = onboarding_documents_for_request(request_id)
        submission = onboarding_submission_for_request(request_id)
        readiness_html = self.render_onboarding_readiness(messages, request, docs)
        token_link = ""
        if request.get("token_hash") and onboarding_token_valid(request):
            token_link = f'<p class="muted">{h(t(messages, "onboarding.link_prepared_note"))}</p>'
        rows = []
        for doc in docs:
            doc_id = doc.get("document_id", "")
            open_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/open", lang)
            download_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/download", lang)
            evidence_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/evidence", lang)
            signed_pdf_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/signed-pdf", lang)
            evidence_link = f' | <a href="{h(evidence_url)}" target="_blank">{h(t(messages, "onboarding.signature_evidence"))}</a>' if doc.get("signed_storage_reference") else ""
            signed_pdf_link = f' | <a href="{h(signed_pdf_url)}" target="_blank">{h(t(messages, "onboarding.signed_pdf"))}</a>' if doc.get("signed_pdf_storage_reference") else f' | <span class="muted">{h(t(messages, "onboarding.signed_pdf_status"))}: {h(doc.get("signed_pdf_status", ""))}</span>' if doc.get("signed_pdf_status") else ""
            rows.append(f"""
<tr><td>{h(doc_id)}</td><td>{h(enum_label(messages, 'onboarding_document_type', doc.get('document_type', '')))}</td><td>{h(doc.get('direction', ''))}</td><td>{h(enum_label(messages, 'signing_mode', doc.get('signing_mode', '')))}</td><td>{h(enum_label(messages, 'onboarding_document_status', doc.get('status', '')))}</td><td>{h(doc.get('original_filename'))}</td><td><a href="{h(open_url)}" target="_blank">{h(t(messages, 'action.open'))}</a> | <a href="{h(download_url)}">{h(t(messages, 'action.download'))}</a>{evidence_link}{signed_pdf_link}</td></tr>
""")
        doc_table = "".join(rows) if rows else f'<tr><td colspan="7" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        review_link = f'<a class="button secondary" href="{h(url_with_lang(f"/onboarding/{quote(request_id)}/review", lang))}">{h(t(messages, "onboarding.review"))}</a>' if submission else ""
        body = f"""
<section class="card">
  <div class="actions"><h2>{h(t(messages, 'onboarding.detail'))}: {h(request_id)}</h2><a class="button light" href="{h(url_with_lang('/onboarding', lang))}">{h(t(messages, 'action.back'))}</a>{review_link}</div>
  {self.render_errors(messages, errors or [])}
  <p><strong>{h(t(messages, 'onboarding.candidate_name'))}:</strong> {h(request.get('candidate_name'))}</p>
  <p><strong>{h(t(messages, 'onboarding.candidate_email'))}:</strong> {h(request.get('candidate_email'))}</p>
  <p><strong>{h(t(messages, 'onboarding.status'))}:</strong> {h(enum_label(messages, 'onboarding_status', request.get('status', '')))}</p>
  {token_link}
</section>
{readiness_html}
<section class="card"><h3>{h(t(messages, 'onboarding.generate_link'))}</h3><div class="actions"><a class="button" href="{h(url_with_lang(f'/onboarding/{quote(request_id)}/email-draft', lang))}">{h(t(messages, 'onboarding.email_draft'))}</a><form method="post" action="{h(url_with_lang(f'/onboarding/{quote(request_id)}/manual-email-package', lang))}"><button type="submit" class="secondary">{h(t(messages, 'onboarding.manual_email_package'))}</button></form></div><p class="muted">{h(t(messages, 'onboarding.email_draft_description'))}</p><p class="muted">{h(t(messages, 'onboarding.manual_email_package_hint'))}</p></section>
<section class="card"><h3>{h(t(messages, 'onboarding.hr_documents'))}</h3><form method="post" enctype="multipart/form-data" action="{h(url_with_lang(f'/onboarding/{quote(request_id)}/documents/upload', lang))}"><div class="form-grid"><div class="form-field"><label>{h(field_label(messages, 'documents.document_type'))}</label><select name="upload_document_type">{''.join(f'<option value="{h(v)}">{h(enum_label(messages, "onboarding_document_type", v))}</option>' for v in ONBOARDING_DOCUMENT_TYPES)}</select></div><div class="form-field"><label>{h(t(messages, 'onboarding.signing_mode'))}</label><select name="upload_signing_mode">{''.join(f'<option value="{h(v)}">{h(enum_label(messages, "signing_mode", v))}</option>' for v in ONBOARDING_SIGNING_MODES)}</select></div><div class="form-field"><label>{h(field_label(messages, 'documents.title'))}</label><input name="upload_title"></div><div class="form-field"><label>{h(t(messages, 'documents.upload_files'))}</label><input type="file" name="upload_files" multiple></div><div class="form-field"><label>{h(field_label(messages, 'documents.notes'))}</label><textarea name="upload_notes"></textarea></div></div><button type="submit">{h(t(messages, 'action.upload'))}</button></form><div class="table-scroll"><table><thead><tr><th>ID</th><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(t(messages, 'onboarding.document_direction'))}</th><th>{h(t(messages, 'onboarding.signing_mode'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(t(messages, 'table.actions'))}</th></tr></thead><tbody>{doc_table}</tbody></table></div></section>
"""
        self.send_html(200, t(messages, "onboarding.detail"), body, lang, messages)

    def send_onboarding_email_draft(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any], errors: list[str] | None = None, prepare_fresh: bool = False) -> None:
        actor = actor_from_user(user)
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        candidate_email = str(request.get("candidate_email", "") or "").strip()
        docs = onboarding_documents_for_request(request_id)
        readiness_html = self.render_onboarding_readiness(messages, request, docs)
        if not candidate_email or not EMAIL_PATTERN.fullmatch(candidate_email):
            self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}", lang), t(messages, "onboarding.email_invalid_recipient"))
            return
        if request.get("status") == "sent" and onboarding_token_valid(request) and not prepare_fresh and not errors:
            fresh_url = url_with_lang(f"/onboarding/{quote(request_id)}/email-draft", lang, {"fresh": "1"})
            body = f"""
<section class="card">
  <div class="actions"><h2>{h(t(messages, 'onboarding.email_already_sent_title'))}</h2><a class="button light" href="{h(url_with_lang(f'/onboarding/{quote(request_id)}', lang))}">{h(t(messages, 'action.back'))}</a></div>
  <p class="message-strip message-warning">{h(t(messages, 'onboarding.email_already_sent_note'))}</p>
  <p><strong>{h(t(messages, 'onboarding.candidate_email'))}:</strong> {h(candidate_email)}</p>
  <p><strong>{h(t(messages, 'onboarding.email_status'))}:</strong> {h(request.get('email_status'))}</p>
  <p><strong>{h(t(messages, 'onboarding.link_expiry'))}:</strong> {h(request.get('token_expiry'))}</p>
  {readiness_html}
  <div class="actions"><a class="button warning" href="{h(fresh_url)}">{h(t(messages, 'onboarding.prepare_fresh_email_draft'))}</a></div>
</section>
"""
            self.send_html(200, t(messages, "onboarding.email_draft"), body, lang, messages)
            return
        token = generate_onboarding_token()
        now = now_iso()
        token_expiry = onboarding_token_expiry()
        link = onboarding_link_for_token(token, lang)
        subject = onboarding_invitation_email_subject(request)
        token_updates = {
            "token_hash": hash_onboarding_token(token),
            "token_expiry": token_expiry,
            "token_created_at": now,
            "status": "ready_to_send",
            "email_status": "draft_prepared",
            "email_draft_status": "pending_hr_confirmation",
            "email_draft_prepared_by": actor,
            "email_draft_prepared_at": now,
            "email_to": candidate_email,
            "email_cc_default": ONBOARDING_DEFAULT_CC_EMAIL,
            "email_subject_snapshot": subject,
            "email_template_version": ONBOARDING_EMAIL_TEMPLATE_VERSION,
            "sent_at": "",
            "verification_code_hash": "",
            "verification_code_created_at": "",
            "verification_code_expiry": "",
            "verification_attempts": "0",
            "verification_locked_until": "",
            "verification_delivery_status": "not_sent",
            "verification_verified_at": "",
            "verification_session_id_hash": "",
            "updated_by": actor,
            "updated_at": now,
        }
        before = copy.deepcopy(request)
        prepared = update_onboarding_request(request_id, token_updates) or {**request, **token_updates}
        append_module_audit_log("onboarding_request", request_id, "onboarding_email_draft_prepared", ["status", "email_status", "email_draft_status", "email_to", "email_cc_default", "email_subject_snapshot", "token_hash", "token_expiry"], "Prepared onboarding invitation email draft for HR review", before, prepared, actor)
        additional = normalize_email_list(prepared.get("email_cc_additional", ""), 3)
        additional += [""] * (3 - len(additional))
        body_preview = onboarding_invitation_email_body(prepared, link)
        send_action = url_with_lang(f"/onboarding/{quote(request_id)}/email-draft/send", lang)
        body = f"""
<section class="object-page">
  <section class="object-header">
    <div class="object-header-content">
      <p class="eyebrow">{h(t(messages, 'onboarding.email_draft'))}</p>
      <h2>{h(t(messages, 'onboarding.email_draft'))}: {h(request_id)}</h2>
      <p class="muted">{h(t(messages, 'onboarding.email_draft_description'))}</p>
    </div>
    <div class="object-meta">
      <div class="meta-chip"><span class="meta-chip-label">{h(t(messages, 'onboarding.candidate_name'))}</span><span class="meta-chip-value">{h(prepared.get('candidate_name'))}</span></div>
      <div class="meta-chip"><span class="meta-chip-label">{h(t(messages, 'onboarding.link_expiry'))}</span><span class="meta-chip-value">{h(token_expiry)}</span></div>
    </div>
  </section>
  <form class="employee-form" method="post" action="{h(send_action)}">
    {self.render_errors(messages, errors or [])}
    {readiness_html}
    <input type="hidden" name="secure_link" value="{h(link)}">
    <section class="form-section">
      <div class="section-header"><h3>{h(t(messages, 'onboarding.email_recipients'))}</h3></div>
      <div class="field-group"><div class="form-grid">
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_to'))}</label><input value="{h(candidate_email)}" readonly></div>
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_cc_default'))}</label><input value="{h(ONBOARDING_DEFAULT_CC_EMAIL)}" readonly></div>
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_cc_additional_1'))}</label><input type="email" name="additional_cc_1" value="{h(additional[0])}"></div>
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_cc_additional_2'))}</label><input type="email" name="additional_cc_2" value="{h(additional[1])}"></div>
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_cc_additional_3'))}</label><input type="email" name="additional_cc_3" value="{h(additional[2])}"></div>
      </div></div>
    </section>
    <section class="form-section">
      <div class="section-header"><h3>{h(t(messages, 'onboarding.email_body_preview'))}</h3></div>
      <div class="field-group">
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_subject'))}</label><input value="{h(subject)}" readonly></div>
        <div class="form-field"><label>{h(t(messages, 'onboarding.email_body_preview'))}</label><textarea rows="16" readonly style="font-family:monospace;">{h(body_preview)}</textarea></div>
        <p class="message-strip message-info">{h(t(messages, 'onboarding.email_draft_security_note'))}</p>
        <div class="checkbox-field"><input type="checkbox" name="email_review_confirmed" value="1" required><label>{h(t(messages, 'onboarding.email_confirm_checkbox'))}</label></div>
      </div>
    </section>
    <div class="form-actions"><a class="button light" href="{h(url_with_lang(f'/onboarding/{quote(request_id)}', lang))}">{h(t(messages, 'action.back'))}</a><button type="submit">{h(t(messages, 'onboarding.confirm_and_send_email'))}</button></div>
  </form>
</section>
"""
        self.send_html(200, t(messages, "onboarding.email_draft"), body, lang, messages)

    def candidate_document_actions_html(self, lang: str, messages: dict[str, str], token: str, document: dict[str, str]) -> str:
        doc_id = document.get("document_id", "")
        download_url = url_with_lang(f"/onboarding/token/{quote(token)}/documents/{quote(doc_id)}/download", lang)
        actions = [f'<a href="{h(download_url)}">{h(t(messages, "action.download"))}</a>']
        if document.get("signed_pdf_storage_reference"):
            signed_pdf_url = url_with_lang(f"/onboarding/token/{quote(token)}/documents/{quote(doc_id)}/signed-pdf", lang)
            actions.append(f'<a href="{h(signed_pdf_url)}" target="_blank">{h(t(messages, "onboarding.signed_pdf"))}</a>')
        if document.get("status") == "signed_by_candidate":
            actions.append(f'<span class="badge success">{h(t(messages, "onboarding.signature_saved"))}</span>')
            return "<div class='onboarding-doc-actions'>" + "<hr>".join(actions) + "</div>"
        signing_mode = document.get("signing_mode", "")
        if signing_mode in {"electronic_signature_required", "electronic_signature_optional"}:
            form_action = url_with_lang(f"/onboarding/token/{quote(token)}/documents/{quote(doc_id)}/sign", lang)
            canvas_id = f"signature_{re.sub(r'[^A-Za-z0-9_]', '_', doc_id)}"
            input_id = f"signature_data_{re.sub(r'[^A-Za-z0-9_]', '_', doc_id)}"
            actions.append(f"""
<form method="post" action="{h(form_action)}" class="signature-form" data-canvas="{h(canvas_id)}" data-input="{h(input_id)}">
  <div class="checkbox-field"><input type="checkbox" name="electronic_consent" value="1" required><label>{h(t(messages, 'onboarding.signature_consent_short'))}</label></div>
  <input name="signer_name" value="" placeholder="{h(t(messages, 'onboarding.signer_name'))}">
  <input name="signer_email" value="" placeholder="{h(t(messages, 'onboarding.signer_email'))}">
  <canvas id="{h(canvas_id)}" width="360" height="120" style="border:1px solid #c8d1dc;border-radius:8px;background:white;touch-action:none;"></canvas>
  <input type="hidden" id="{h(input_id)}" name="signature_data">
  <div class="actions"><button type="submit">{h(t(messages, 'onboarding.sign_electronically'))}</button><button type="button" class="button light signature-clear">{h(t(messages, 'action.clear'))}</button></div>
</form>""")
        if signing_mode in {"electronic_signature_optional", "manual_sign_upload_required"}:
            upload_action = url_with_lang(f"/onboarding/token/{quote(token)}/documents/{quote(doc_id)}/manual-signed-upload", lang)
            actions.append(f"""
<form method="post" enctype="multipart/form-data" action="{h(upload_action)}">
  <label>{h(t(messages, 'onboarding.manual_signed_upload'))}</label>
  <input type="file" name="upload_files" required>
  <button type="submit">{h(t(messages, 'action.upload'))}</button>
</form>""")
        return "<div class='onboarding-doc-actions'>" + "<hr>".join(actions) + "</div>"

    def render_candidate_document_status_html(self, messages: dict[str, str], employee: dict[str, Any], documents: list[dict[str, str]]) -> str:
        matrix_rows = []
        for row in onboarding_candidate_document_matrix(employee, documents):
            document_type = str(row.get("document_type", ""))
            matching_docs = row.get("documents", []) if isinstance(row.get("documents"), list) else []
            files = ", ".join(str(doc.get("original_filename") or doc.get("stored_filename") or "") for doc in matching_docs if doc.get("original_filename") or doc.get("stored_filename")) or "-"
            badge_class = "success" if row.get("is_complete") else "alert"
            status_key = "documents.requirement_complete" if row.get("is_complete") else "documents.requirement_missing"
            matrix_rows.append(f"""
<tr><td>{h(enum_label(messages, 'onboarding_document_type', document_type))}</td><td><span class="badge {badge_class}">{h(t(messages, status_key))}</span></td><td>{h(str(row.get('matched_count', 0)))}</td><td>{h(files)}</td></tr>
""")
        checklist_body = "".join(matrix_rows) if matrix_rows else f'<tr><td colspan="4" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        uploaded_rows = []
        for doc in onboarding_candidate_uploaded_documents(documents):
            uploaded_rows.append(f"""
<tr><td>{h(enum_label(messages, 'onboarding_document_type', doc.get('document_type', '')))}</td><td>{h(doc.get('original_filename') or doc.get('stored_filename') or '-')}</td><td>{h(format_file_size_label(doc.get('file_size_bytes')) or '-')}</td><td>{h(enum_label(messages, 'onboarding_document_status', doc.get('status', '')))}</td><td>{h(doc.get('uploaded_at') or '-')}</td></tr>
""")
        uploaded_body = "".join(uploaded_rows) if uploaded_rows else f'<tr><td colspan="5" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        pending_docs = onboarding_pending_required_hr_documents(documents)
        pending_note = ""
        if pending_docs:
            pending_names = ", ".join(doc.get("title") or enum_label(messages, "onboarding_document_type", doc.get("document_type", "")) for doc in pending_docs)
            pending_note = f'<p class="message-strip message-warning">{h(t(messages, "onboarding.pending_required_signatures_message").format(documents=pending_names))}</p>'
        return f"""
<section class="form-section">
  <div class="section-header"><h3>{h(t(messages, 'onboarding.required_upload_checklist'))}</h3></div>
  <p class="muted">{h(t(messages, 'onboarding.required_document_note'))}</p>
  {pending_note}
  <div class="table-scroll"><table class="document-checklist-table"><thead><tr><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(t(messages, 'documents.requirement_status'))}</th><th>{h(t(messages, 'documents.matched_count'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th></tr></thead><tbody>{checklist_body}</tbody></table></div>
</section>
<section class="form-section">
  <div class="section-header"><h3>{h(t(messages, 'onboarding.candidate_uploaded_documents'))}</h3></div>
  <div class="table-scroll"><table><thead><tr><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(field_label(messages, 'documents.file_size_bytes'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(field_label(messages, 'documents.uploaded_at'))}</th></tr></thead><tbody>{uploaded_body}</tbody></table></div>
</section>
"""

    def send_candidate_onboarding_form(self, lang: str, messages: dict[str, str], token: str, request: dict[str, str], errors: list[str]) -> None:
        submission = onboarding_submission_for_request(request["onboarding_request_id"])
        employee = submission.get("form_data") if submission and isinstance(submission.get("form_data"), dict) else default_employee()
        all_docs = onboarding_documents_for_request(request["onboarding_request_id"])
        docs = [doc for doc in all_docs if doc.get("direction") == "hr_to_candidate"]
        document_status_html = self.render_candidate_document_status_html(messages, employee, all_docs)
        doc_rows = []
        for doc in docs:
            actions_html = self.candidate_document_actions_html(lang, messages, token, doc)
            doc_rows.append(f"<tr><td>{h(enum_label(messages, 'onboarding_document_type', doc.get('document_type', '')))}</td><td>{h(enum_label(messages, 'signing_mode', doc.get('signing_mode', '')))}</td><td>{h(enum_label(messages, 'onboarding_document_status', doc.get('status', '')))}</td><td>{actions_html}</td></tr>")
        documents_table = "".join(doc_rows) if doc_rows else f'<tr><td colspan="4" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        action = url_with_lang(f"/onboarding/token/{quote(token)}/form/submit", lang)
        body = f"""
<section class="card"><h2>{h(t(messages, 'onboarding.candidate_form'))}</h2><p class="muted">{h(t(messages, 'onboarding.candidate_description'))}</p><p><strong>{h(request.get('candidate_name'))}</strong></p></section>
<section class="card"><h3>{h(t(messages, 'onboarding.hr_documents'))}</h3><div class="table-scroll"><table><thead><tr><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(t(messages, 'onboarding.signing_mode'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(t(messages, 'table.actions'))}</th></tr></thead><tbody>{documents_table}</tbody></table></div></section>
<section class="object-page"><form class="employee-form" method="post" enctype="multipart/form-data" action="{h(action)}">{self.render_errors(messages, errors)}{self.render_form_section(messages, 'section.profile', self.render_candidate_profile_fields(messages, employee))}{self.render_form_section(messages, 'section.employment', self.render_candidate_employment_fields(messages, employee))}{self.render_form_section(messages, 'section.payroll', self.render_candidate_payroll_fields(messages, employee))}{self.render_form_section(messages, 'section.visa', self.render_candidate_visa_fields(messages, employee))}{document_status_html}<section class="form-section"><div class="section-header"><h3>{h(t(messages, 'onboarding.upload_documents'))}</h3></div><p class="muted">{h(t(messages, 'onboarding.upload_documents_note'))}</p><p class="muted">{h(t(messages, 'onboarding.upload_limits_short'))}</p><div class="form-grid"><div class="form-field"><label>{h(field_label(messages, 'documents.document_type'))}</label><select name="upload_document_type">{''.join(f'<option value="{h(v)}">{h(enum_label(messages, "onboarding_document_type", v))}</option>' for v in ONBOARDING_DOCUMENT_TYPES)}</select></div><div class="form-field"><label>{h(t(messages, 'documents.upload_files'))}</label><input type="file" name="upload_files" multiple data-file-preview="candidateUploadPreview"><div id="candidateUploadPreview" class="file-preview"></div></div><div class="form-field"><label>{h(field_label(messages, 'documents.notes'))}</label><textarea name="upload_notes"></textarea></div></div></section><div class="form-actions"><button type="submit">{h(t(messages, 'onboarding.submit'))}</button><button type="submit" formaction="{h(url_with_lang(f'/onboarding/token/{quote(token)}/form/save', lang))}">{h(t(messages, 'onboarding.save_draft'))}</button></div></form></section>
"""
        self.send_html(200, t(messages, "onboarding.candidate_form"), body, lang, messages)

    def render_candidate_profile_fields(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        fields = "".join([self.render_input(messages, employee, path, "date" if path == "profile.date_of_birth" else "email" if path in {"profile.email_p", "profile.emergency_contact.email"} else "text") for path in ["profile.name.display_name", "profile.name.family_name", "profile.name.given_name", "profile.name.family_name_kana", "profile.name.given_name_kana", "profile.name.romaji_name", "profile.date_of_birth", "profile.nationality", "profile.email_p", "profile.phone", "profile.address.postal_code", "profile.address.prefecture", "profile.address.city", "profile.address.street", "profile.address.building", "profile.emergency_contact.name", "profile.emergency_contact.relationship", "profile.emergency_contact.phone", "profile.emergency_contact.email"]])
        return self.render_field_group(messages, "form.group.personal", fields)

    def render_candidate_employment_fields(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        return self.render_field_group(messages, "form.group.employment_basics", f"{self.render_input(messages, employee, 'employment.join_date', 'date')}{self.render_select(messages, employee, 'employment.employment_type', EMPLOYMENT_TYPES, 'employment_type')}{self.render_input(messages, employee, 'employment.position')}{self.render_input(messages, employee, 'employment.office_location')}{self.render_input(messages, employee, 'employment.assignment')}")

    def render_candidate_payroll_fields(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        return self.render_field_group(messages, "form.group.payroll_bank", f"{self.render_input(messages, employee, 'payroll.bank.bank_name')}{self.render_input(messages, employee, 'payroll.bank.branch_name')}{self.render_input(messages, employee, 'payroll.bank.swift_code')}{self.render_select(messages, employee, 'payroll.bank.account_type', BANK_ACCOUNT_TYPES, 'bank_account_type')}{self.render_input(messages, employee, 'payroll.bank.account_number')}{self.render_input(messages, employee, 'payroll.bank.account_holder')}{self.render_input(messages, employee, 'payroll.transportation_allowance_yen', 'number')}") + f"<p class='muted'>{h(t(messages, 'onboarding.mynumber_disabled'))}</p>"

    def render_candidate_visa_fields(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        return self.render_field_group(messages, "form.group.visa_residence", f"{self.render_input(messages, employee, 'visa.visa_type')}{self.render_input(messages, employee, 'visa.residence_status')}{self.render_input(messages, employee, 'visa.expiry_date', 'date')}{self.render_input(messages, employee, 'visa.residence_card_number')}{self.render_input(messages, employee, 'visa.passport_number')}{self.render_input(messages, employee, 'visa.passport_expiry_date', 'date')}")

    def render_candidate_dispatch_fields(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        return self.render_field_group(messages, "form.group.dispatch_assignment", f"{self.render_input(messages, employee, 'dispatch_compliance.client_name')}{self.render_input(messages, employee, 'dispatch_compliance.assignment_location')}{self.render_input(messages, employee, 'dispatch_compliance.dispatch_start_date', 'date')}{self.render_input(messages, employee, 'dispatch_compliance.dispatch_end_date', 'date')}{self.render_select(messages, employee, 'dispatch_compliance.contract_type', DISPATCH_CONTRACT_TYPES, 'dispatch_contract_type')}{self.render_textarea(messages, employee, 'dispatch_compliance.work_description')}")

    def send_candidate_submitted(self, lang: str, messages: dict[str, str], request: dict[str, str]) -> None:
        body = f"<section class='card'><h2>{h(t(messages, 'onboarding.submitted'))}</h2><p class='muted'>{h(t(messages, 'onboarding.submitted_description'))}</p></section>"
        self.send_html(200, t(messages, "onboarding.submitted"), body, lang, messages)

    def send_onboarding_review(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any], errors: list[str] | None = None) -> None:
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        submission = onboarding_submission_for_request(request_id)
        if not request or not submission:
            self.send_not_found(lang, messages)
            return
        employee = submission.get("form_data") if isinstance(submission.get("form_data"), dict) else default_employee()
        docs = onboarding_documents_for_request(request_id)
        doc_rows_parts = []
        for doc in docs:
            doc_id = doc.get("document_id", "")
            open_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/open", lang)
            download_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/download", lang)
            evidence_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/evidence", lang)
            signed_pdf_url = url_with_lang(f"/onboarding/{quote(request_id)}/documents/{quote(doc_id)}/signed-pdf", lang)
            evidence_link = f' | <a href="{h(evidence_url)}" target="_blank">{h(t(messages, "onboarding.signature_evidence"))}</a>' if doc.get("signed_storage_reference") else ""
            signed_pdf_link = f' | <a href="{h(signed_pdf_url)}" target="_blank">{h(t(messages, "onboarding.signed_pdf"))}</a>' if doc.get("signed_pdf_storage_reference") else f' | <span class="muted">{h(t(messages, "onboarding.signed_pdf_status"))}: {h(doc.get("signed_pdf_status", ""))}</span>' if doc.get("signed_pdf_status") else ""
            doc_rows_parts.append(f"<tr><td>{h(doc_id)}</td><td>{h(enum_label(messages, 'onboarding_document_type', doc.get('document_type', '')))}</td><td>{h(doc.get('direction', ''))}</td><td>{h(enum_label(messages, 'signing_mode', doc.get('signing_mode', '')))}</td><td>{h(enum_label(messages, 'onboarding_document_status', doc.get('status', '')))}</td><td>{h(doc.get('original_filename'))}</td><td><a href=\"{h(open_url)}\" target=\"_blank\">{h(t(messages, 'action.open'))}</a> | <a href=\"{h(download_url)}\">{h(t(messages, 'action.download'))}</a>{evidence_link}{signed_pdf_link}</td></tr>")
        doc_rows = "".join(doc_rows_parts) or f'<tr><td colspan="7" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        body = f"""
<section class="card"><div class="actions"><h2>{h(t(messages, 'onboarding.review'))}: {h(request_id)}</h2><a class="button light" href="{h(url_with_lang(f'/onboarding/{quote(request_id)}', lang))}">{h(t(messages, 'action.back'))}</a></div>{self.render_errors(messages, errors or [])}<p>{h(t(messages, 'onboarding.candidate_name'))}: {h(request.get('candidate_name'))}</p></section>
<section class="card"><h3>{h(t(messages, 'onboarding.submitted_data'))}</h3><div class="detail-grid"><div><strong>{h(field_label(messages, 'profile.name.display_name'))}</strong><br>{h(get_nested(employee, 'profile.name.display_name'))}</div><div><strong>{h(field_label(messages, 'profile.email_p'))}</strong><br>{h(get_nested(employee, 'profile.email_p'))}</div><div><strong>{h(field_label(messages, 'profile.phone'))}</strong><br>{h(get_nested(employee, 'profile.phone'))}</div><div><strong>{h(field_label(messages, 'employment.join_date'))}</strong><br>{h(get_nested(employee, 'employment.join_date'))}</div></div></section>
<section class="card"><h3>{h(t(messages, 'onboarding.documents'))}</h3><table><thead><tr><th>ID</th><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(t(messages, 'onboarding.document_direction'))}</th><th>{h(t(messages, 'onboarding.signing_mode'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(t(messages, 'table.actions'))}</th></tr></thead><tbody>{doc_rows}</tbody></table></section>
<section class="card"><h3>{h(t(messages, 'onboarding.approve_import'))}</h3><form method="post" action="{h(url_with_lang(f'/onboarding/{quote(request_id)}/review/approve', lang))}"><button type="submit">{h(t(messages, 'onboarding.approve'))}</button></form><form method="post" action="{h(url_with_lang(f'/onboarding/{quote(request_id)}/review/return', lang))}"><textarea name="review_notes" placeholder="{h(t(messages, 'onboarding.review_notes'))}"></textarea><button type="submit">{h(t(messages, 'onboarding.return_to_candidate'))}</button></form></section>
<section class="card"><h3>{h(t(messages, 'onboarding.import'))}</h3><form method="post" action="{h(url_with_lang(f'/onboarding/{quote(request_id)}/import', lang))}"><div class="form-grid"><div class="form-field"><label>{h(field_label(messages, 'employee_number'))}</label><input name="employee_number" required></div><div class="form-field"><label>{h(field_label(messages, 'profile.email'))}</label><input type="email" name="company_email" required></div><div class="form-field"><label>{h(field_label(messages, 'employment.department_id'))}</label><input name="department_id" required></div><div class="form-field"><label>{h(field_label(messages, 'employment.entity_id'))}</label><input name="entity_id"></div><div class="form-field"><label>{h(field_label(messages, 'employment.team_id'))}</label><input name="team_id"></div><div class="form-field"><label>{h(field_label(messages, 'employment.status'))}</label><select name="employment_status">{''.join(f'<option value="{h(v)}">{h(enum_label(messages, "status", v))}</option>' for v in EMPLOYMENT_STATUSES)}</select></div></div><button type="submit">{h(t(messages, 'onboarding.import_to_employee_master'))}</button></form></section>
"""
        self.send_html(200, t(messages, "onboarding.review"), body, lang, messages)

    def send_onboarding_document_file(self, lang: str, messages: dict[str, str], document: dict[str, str], mode: str) -> None:
        if mode == "evidence":
            variant = "evidence"
        elif mode == "signed-pdf":
            variant = "signed_pdf"
        else:
            variant = "original"
        path = onboarding_document_path(document, variant=variant)
        if not path or not path.is_file():
            self.send_not_found(lang, messages)
            return
        if variant == "evidence":
            filename = path.name
            content_type = "text/html; charset=utf-8"
        elif variant == "signed_pdf":
            filename = document.get("signed_pdf_stored_filename") or path.name
            content_type = "application/pdf"
        else:
            filename = document.get("original_filename") or document.get("stored_filename") or path.name
            content_type = document_content_type(document, path)
        disposition = content_disposition("attachment" if mode == "download" else "inline", filename)
        self.send_document_bytes(200, content_type, path.read_bytes(), disposition)

    def update_onboarding_document_status(self, document: dict[str, str], status: str, actor: str) -> None:
        docs = load_onboarding_documents()
        for index, doc in enumerate(docs):
            if doc.get("document_id") == document.get("document_id"):
                before = copy.deepcopy(doc)
                doc["status"] = status
                docs[index] = normalize_onboarding_document(doc)
                save_onboarding_documents(docs)
                append_module_audit_log("onboarding_document", doc["document_id"], "onboarding_document_status_changed", ["status"], f"Onboarding document status changed to {status}", before, doc, actor)
                return

    def handle_create_onboarding_request(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form = self.parse_form_body()
        requests = load_onboarding_requests()
        request = default_onboarding_request()
        for key in ["candidate_name", "candidate_email", "planned_start_date", "employment_type", "onboarding_category", "hr_notes"]:
            request[key] = str(form.get(key, "") or "").strip()
        if request["onboarding_category"] not in ONBOARDING_CATEGORIES:
            request["onboarding_category"] = "regular_employee"
        if request["employment_type"] == "dispatch" and request["onboarding_category"] == "regular_employee":
            request["onboarding_category"] = "dispatch_employee"
        request["onboarding_request_id"] = next_onboarding_request_id(requests)
        request["created_by"] = actor
        request["created_at"] = now_iso()
        errors = []
        if not request["candidate_name"]:
            errors.append(t(messages, "validation.required") + ": " + t(messages, "onboarding.candidate_name"))
        if not EMAIL_PATTERN.fullmatch(request["candidate_email"]):
            errors.append(t(messages, "validation.invalid_email"))
        if request["planned_start_date"] and not is_valid_date(request["planned_start_date"]):
            errors.append(t(messages, "validation.invalid_date"))
        if errors:
            self.send_onboarding_new_form(lang, messages, request, errors)
            return
        requests.append(request)
        save_onboarding_requests(requests)
        append_module_audit_log("onboarding_request", request["onboarding_request_id"], "onboarding_request_created", ["onboarding_request_id", "candidate_email", "status"], f"Created onboarding request {request['onboarding_request_id']}", None, request, actor)
        self.redirect(url_with_lang(f"/onboarding/{quote(request['onboarding_request_id'])}", lang), operation_notice(messages, "Onboarding", request["onboarding_request_id"], "created", actor))

    def handle_onboarding_generate_link(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}/email-draft", lang))

    def handle_onboarding_email_draft_send(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form = self.parse_form_body()
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        candidate_email = str(request.get("candidate_email", "") or "").strip()
        errors: list[str] = []
        if not candidate_email or not EMAIL_PATTERN.fullmatch(candidate_email):
            errors.append(t(messages, "onboarding.email_invalid_recipient"))
        if form.get("email_review_confirmed") != "1":
            errors.append(t(messages, "onboarding.email_confirm_required"))
        additional_cc, cc_errors = validate_onboarding_additional_cc(
            [str(form.get("additional_cc_1", "") or ""), str(form.get("additional_cc_2", "") or ""), str(form.get("additional_cc_3", "") or "")],
            candidate_email,
            messages,
        )
        errors.extend(cc_errors)
        secure_link = str(form.get("secure_link", "") or "").strip()
        token = onboarding_token_from_link(secure_link)
        if not token or not request.get("token_hash") or not hmac.compare_digest(hash_onboarding_token(token), request.get("token_hash", "")) or not onboarding_token_valid(request):
            errors.append(t(messages, "onboarding.email_draft_expired"))
        if errors:
            self.send_onboarding_email_draft(lang, messages, request_id, user, errors)
            return
        subject = str(request.get("email_subject_snapshot", "") or onboarding_invitation_email_subject(request)).strip()
        cc_addresses = onboarding_email_cc_list(additional_cc)
        body = onboarding_invitation_email_body(request, secure_link)
        sent, email_status = send_onboarding_email(candidate_email, subject, body, cc_addresses=cc_addresses)
        confirmed_at = now_iso()
        code_sent = False
        code_status = "not_sent"
        code_expiry = ""
        verification_updates: dict[str, str] = {
            "verification_attempts": "0",
            "verification_locked_until": "",
            "verification_verified_at": "",
            "verification_session_id_hash": "",
        }
        if sent:
            code = generate_onboarding_verification_code()
            code_expiry = onboarding_verification_expiry()
            code_sent, code_status = send_onboarding_email(
                candidate_email,
                f"TAC onboarding verification code: {request.get('candidate_name', '')}",
                onboarding_verification_email_body({**request, "verification_code_expiry": code_expiry}, code),
            )
            verification_updates["verification_delivery_status"] = "sent" if code_sent else f"manual_required_{code_status}"
            if code_sent:
                verification_updates.update({
                    "verification_code_hash": hash_onboarding_verification_code(request_id, code),
                    "verification_code_created_at": confirmed_at,
                    "verification_code_expiry": code_expiry,
                    "verification_last_sent_at": confirmed_at,
                })
            else:
                verification_updates.update({
                    "verification_code_hash": "",
                    "verification_code_created_at": "",
                    "verification_code_expiry": "",
                })
        else:
            verification_updates.update({
                "verification_code_hash": "",
                "verification_code_created_at": "",
                "verification_code_expiry": "",
                "verification_delivery_status": "not_sent",
            })
        delivery_updates = {
            "status": "sent" if sent else "ready_to_send",
            "email_sender": current_onboarding_email_sender(),
            "email_status": email_status,
            "email_draft_status": "sent" if sent else "confirmed_send_failed",
            "email_review_confirmed_by": actor,
            "email_review_confirmed_at": confirmed_at,
            "email_to": candidate_email,
            "email_cc_default": ONBOARDING_DEFAULT_CC_EMAIL,
            "email_cc_additional": "\n".join(additional_cc),
            "email_sent_to_snapshot": candidate_email,
            "email_sent_cc_snapshot": ", ".join(cc_addresses),
            "email_subject_snapshot": subject,
            "email_template_version": ONBOARDING_EMAIL_TEMPLATE_VERSION,
            "sent_at": confirmed_at if sent else "",
            "updated_by": actor,
            "updated_at": confirmed_at,
            **verification_updates,
        }
        before = copy.deepcopy(request)
        delivered = update_onboarding_request(request_id, delivery_updates) or {**request, **delivery_updates}
        append_module_audit_log("onboarding_request", request_id, "onboarding_email_review_confirmed", ["email_draft_status", "email_review_confirmed_by", "email_review_confirmed_at", "email_to", "email_cc_default", "email_cc_additional", "email_subject_snapshot"], "HR confirmed onboarding invitation email draft", before, delivered, actor)
        action = "onboarding_email_sent" if sent else "onboarding_email_send_failed"
        append_module_audit_log("onboarding_request", request_id, action, ["status", "email_status", "email_draft_status", "email_sent_to_snapshot", "email_sent_cc_snapshot", "sent_at"], f"Onboarding invitation email {email_status}", before, delivered, actor)
        if sent:
            code_action = "candidate_email_verification_code_sent" if code_sent else "candidate_email_verification_code_prepared"
            append_module_audit_log("onboarding_request", request_id, code_action, ["verification_delivery_status", "verification_code_expiry"], f"Candidate verification code delivery {code_status}", before, delivered, actor)
        if sent and code_sent:
            notice = t(messages, "onboarding.email_sent_with_code_detail")
        elif sent:
            notice = f"{t(messages, 'onboarding.email_sent_code_failed')} ({code_status})"
        else:
            notice = f"{t(messages, 'onboarding.email_failed_manual_available')} ({email_status})"
        self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}", lang), notice)

    def handle_onboarding_manual_email_package(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        token = generate_onboarding_token()
        code = generate_onboarding_verification_code()
        now = now_iso()
        token_expiry = onboarding_token_expiry()
        code_expiry = onboarding_verification_expiry()
        link = onboarding_link_for_token(token, lang)
        updates = {
            "token_hash": hash_onboarding_token(token),
            "token_expiry": token_expiry,
            "token_created_at": now,
            "status": "ready_to_send",
            "email_sender": current_onboarding_email_sender(),
            "email_status": "manual_package_prepared",
            "verification_code_hash": hash_onboarding_verification_code(request_id, code),
            "verification_code_created_at": now,
            "verification_code_expiry": code_expiry,
            "verification_attempts": "0",
            "verification_locked_until": "",
            "verification_last_sent_at": now,
            "verification_delivery_status": "manual_package_prepared",
            "verification_verified_at": "",
            "verification_session_id_hash": "",
            "updated_by": actor,
            "updated_at": now,
        }
        before = copy.deepcopy(request)
        updated = update_onboarding_request(request_id, updates) or {**request, **updates}
        manual_body = onboarding_manual_invitation_email_body(updated, link, code)
        readiness_html = self.render_onboarding_readiness(messages, updated, onboarding_documents_for_request(request_id))
        append_module_audit_log("onboarding_request", request_id, "onboarding_manual_email_package_prepared", ["token_hash", "token_expiry", "verification_code_expiry", "email_status"], "Prepared manual onboarding email package", before, updated, actor)
        body = f"""
<section class="card">
  <div class="actions"><h2>{h(t(messages, 'onboarding.manual_email_package'))}</h2><a class="button light" href="{h(url_with_lang(f'/onboarding/{quote(request_id)}', lang))}">{h(t(messages, 'action.back'))}</a></div>
  <p class="muted">{h(t(messages, 'onboarding.manual_email_package_description'))}</p>
  <p><strong>{h(t(messages, 'onboarding.candidate_email'))}:</strong> {h(updated.get('candidate_email'))}</p>
  <p><strong>{h(t(messages, 'onboarding.verification_code'))}:</strong> <code>{h(code)}</code></p>
  <p><strong>{h(t(messages, 'onboarding.link_expiry'))}:</strong> {h(token_expiry)}</p>
  <p><strong>{h(t(messages, 'onboarding.code_expiry'))}:</strong> {h(code_expiry)}</p>
  {readiness_html}
  <textarea rows="18" style="width:100%;font-family:monospace;">{h(manual_body)}</textarea>
</section>
"""
        self.send_html(200, t(messages, "onboarding.manual_email_package"), body, lang, messages)

    def handle_onboarding_document_upload(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        form, uploads, request_errors = self.parse_request_body(messages)
        errors = request_errors + validate_upload_parts(uploads, messages)
        if errors:
            self.send_onboarding_detail(lang, messages, request_id, user, errors)
            return
        docs, writes = uploaded_onboarding_documents_from_parts(request_id, form, uploads, "hr_to_candidate", actor)
        try:
            write_onboarding_uploaded_files(writes)
        except Exception:
            self.send_onboarding_detail(lang, messages, request_id, user, [t(messages, "validation.upload_save_failed")])
            return
        save_onboarding_documents(load_onboarding_documents() + docs)
        for doc in docs:
            append_module_audit_log("onboarding_document", doc["document_id"], "onboarding_document_uploaded_by_hr", ["document_id", "document_type", "signing_mode", "status"], f"Uploaded onboarding document {doc['document_id']}", None, doc, actor)
        self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}", lang), t(messages, "onboarding.document_uploaded"))

    def handle_onboarding_return(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form = self.parse_form_body()
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        candidate_email = str(request.get("candidate_email", "") or "").strip()
        if not candidate_email or not EMAIL_PATTERN.fullmatch(candidate_email):
            self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}/review", lang), t(messages, "onboarding.email_invalid_recipient"))
            return
        review_notes = str(form.get("review_notes", "") or "").strip()
        token = generate_onboarding_token()
        now = now_iso()
        link = onboarding_link_for_token(token, lang)
        token_updates = {
            "status": "returned_to_candidate",
            "review_notes": review_notes,
            "token_hash": hash_onboarding_token(token),
            "token_expiry": onboarding_token_expiry(),
            "token_created_at": now,
            "email_status": "return_link_prepared",
            "updated_by": actor,
            "updated_at": now,
        }
        before = copy.deepcopy(request)
        prepared = update_onboarding_request(request_id, token_updates) or {**request, **token_updates}
        append_module_audit_log("onboarding_request", request_id, "submission_returned_to_candidate", ["status", "review_notes", "token_hash", "token_expiry", "email_status"], "Returned onboarding submission to candidate and prepared correction link", before, prepared, actor)
        cc_addresses = normalize_email_list(onboarding_email_settings().get("department_manager_cc_emails", []), 3)
        sent, email_status = send_onboarding_email(
            candidate_email,
            f"TAC onboarding correction request: {request.get('candidate_name', '')}",
            onboarding_return_email_body(prepared, review_notes, link),
            cc_addresses=cc_addresses,
        )
        delivery_updates = {
            "email_status": f"return_{email_status}",
            "updated_by": actor,
            "updated_at": now_iso(),
        }
        if sent:
            delivery_updates["sent_at"] = now_iso()
        delivered = update_onboarding_request(request_id, delivery_updates) or {**prepared, **delivery_updates}
        append_module_audit_log("onboarding_request", request_id, "return_to_candidate_email_sent" if sent else "return_to_candidate_email_prepared", ["email_status", "sent_at"], f"Return-to-candidate email {email_status}", prepared, delivered, actor)
        notice = t(messages, "onboarding.email_sent_detail") if sent else f"{t(messages, 'onboarding.email_failed_manual_available')} ({email_status})"
        self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}/review", lang), f"{t(messages, 'onboarding.returned')} / {notice}")

    def handle_onboarding_approve(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        if not request:
            self.send_not_found(lang, messages)
            return
        before = copy.deepcopy(request)
        updated = update_onboarding_request(request_id, {"status": "approved", "updated_by": actor, "updated_at": now_iso()})
        append_module_audit_log("onboarding_request", request_id, "submission_approved", ["status"], "Approved onboarding submission", before, updated, actor)
        self.redirect(url_with_lang(f"/onboarding/{quote(request_id)}/review", lang), t(messages, "onboarding.approved"))

    def handle_onboarding_import(self, lang: str, messages: dict[str, str], request_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        request = find_onboarding_request(load_onboarding_requests(), request_id)
        submission = onboarding_submission_for_request(request_id)
        if not request or not submission:
            self.send_not_found(lang, messages)
            return
        if request.get("status") != "approved":
            self.send_onboarding_review(lang, messages, request_id, user, [t(messages, "onboarding.import_requires_approval")])
            return
        form = self.parse_form_body()
        employees = load_employees()
        employee = normalize_employee(submission.get("form_data", {}))
        employee["employee_id"] = next_employee_id(employees)
        employee["employee_number"] = str(form.get("employee_number", "") or "").strip()
        set_nested(employee, "profile.email", str(form.get("company_email", "") or "").strip())
        set_nested(employee, "employment.entity_id", str(form.get("entity_id", "") or "").strip())
        set_nested(employee, "employment.department_id", str(form.get("department_id", "") or "").strip())
        set_nested(employee, "employment.team_id", str(form.get("team_id", "") or "").strip())
        set_nested(employee, "employment.status", str(form.get("employment_status", "active") or "active").strip())
        employee.setdefault("metadata", {})
        employee["metadata"]["created_at"] = now_iso()
        employee["metadata"]["created_by"] = actor
        employee["metadata"]["source_onboarding_request_id"] = request_id
        docs_to_import = []
        file_copies: list[tuple[Path, Path]] = []
        employee_docs: list[dict[str, str]] = []
        sequence = employee_document_sequence([], employee["employee_id"])
        for doc in onboarding_documents_for_request(request_id):
            path = onboarding_document_path(doc)
            if not path or not path.is_file():
                continue
            ext = upload_extension(doc.get("stored_filename") or doc.get("original_filename")) or path.suffix.lower()
            stored = build_stored_document_filename(employee["employee_id"], sequence, ext)
            sequence += 1
            document = default_document()
            document["document_id"] = next_document_id(employee_docs)
            dtype = doc.get("document_type", "other")
            document["document_type"] = dtype if dtype in DOCUMENT_TYPES else "other"
            document["title"] = doc.get("title") or title_from_filename(doc.get("original_filename", ""))
            document["issuer"] = "TAC" if doc.get("direction") == "hr_to_candidate" else "Employee"
            document["received_date"] = date.today().isoformat()
            document["status"] = "on_file"
            document["storage_reference"] = document_relative_path(stored)
            document["original_filename"] = doc.get("original_filename", "")
            document["stored_filename"] = stored
            document["content_type"] = doc.get("content_type", "application/octet-stream")
            document["file_size_bytes"] = doc.get("file_size_bytes", "")
            document["uploaded_at"] = now_iso()
            document["uploaded_by"] = actor
            employee_docs.append(document)
            file_copies.append((path, EMPLOYEE_DOCS_DIR / stored))
            evidence_path = onboarding_document_path(doc, signed=True)
            if evidence_path and evidence_path.is_file():
                evidence_stored = build_stored_document_filename(employee["employee_id"], sequence, evidence_path.suffix.lower() or ".html")
                sequence += 1
                evidence_document = default_document()
                evidence_document["document_id"] = next_document_id(employee_docs)
                evidence_document["document_type"] = document["document_type"]
                evidence_document["title"] = f"{document['title']} - signature evidence"
                evidence_document["issuer"] = "Employee"
                evidence_document["received_date"] = date.today().isoformat()
                evidence_document["status"] = "on_file"
                evidence_document["storage_reference"] = document_relative_path(evidence_stored)
                evidence_document["original_filename"] = evidence_path.name
                evidence_document["stored_filename"] = evidence_stored
                evidence_document["content_type"] = "text/html; charset=utf-8"
                evidence_document["file_size_bytes"] = str(evidence_path.stat().st_size)
                evidence_document["uploaded_at"] = now_iso()
                evidence_document["uploaded_by"] = actor
                employee_docs.append(evidence_document)
                file_copies.append((evidence_path, EMPLOYEE_DOCS_DIR / evidence_stored))
            signed_pdf_path = onboarding_document_path(doc, variant="signed_pdf")
            if signed_pdf_path and signed_pdf_path.is_file():
                signed_pdf_stored = build_stored_document_filename(employee["employee_id"], sequence, ".pdf")
                sequence += 1
                signed_pdf_document = default_document()
                signed_pdf_document["document_id"] = next_document_id(employee_docs)
                signed_pdf_document["document_type"] = document["document_type"]
                signed_pdf_document["title"] = f"{document['title']} - signed PDF"
                signed_pdf_document["issuer"] = "Employee"
                signed_pdf_document["received_date"] = date.today().isoformat()
                signed_pdf_document["status"] = "on_file"
                signed_pdf_document["storage_reference"] = document_relative_path(signed_pdf_stored)
                signed_pdf_document["original_filename"] = signed_pdf_path.name
                signed_pdf_document["stored_filename"] = signed_pdf_stored
                signed_pdf_document["content_type"] = "application/pdf"
                signed_pdf_document["file_size_bytes"] = str(signed_pdf_path.stat().st_size)
                signed_pdf_document["uploaded_at"] = now_iso()
                signed_pdf_document["uploaded_by"] = actor
                employee_docs.append(signed_pdf_document)
                file_copies.append((signed_pdf_path, EMPLOYEE_DOCS_DIR / signed_pdf_stored))
        set_nested(employee, "documents", employee_docs)
        errors = validate_employee(employee, employees, messages)
        errors.extend(validate_section(employee, "payroll", messages))
        errors.extend(validate_section(employee, "visa", messages))
        errors.extend(validate_section(employee, "dispatch", messages))
        if errors:
            self.send_onboarding_review(lang, messages, request_id, user, errors)
            return
        EMPLOYEE_DOCS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            for source, destination in file_copies:
                resolved = destination.resolve()
                if resolved.parent != EMPLOYEE_DOCS_DIR.resolve():
                    raise ValueError("Invalid employee document destination")
                shutil.copy2(source, resolved)
        except Exception:
            self.send_onboarding_review(lang, messages, request_id, user, [t(messages, "validation.upload_save_failed")])
            return
        employees.append(employee)
        save_employees(employees)
        before_request = copy.deepcopy(request)
        update_onboarding_request(request_id, {"status": "imported_to_employee_master", "imported_employee_id": employee["employee_id"], "updated_by": actor, "updated_at": now_iso()})
        append_module_audit_log("onboarding_request", request_id, "employee_master_created_from_onboarding", ["status", "imported_employee_id"], f"Imported onboarding request {request_id} into employee {employee['employee_id']}", before_request, {**request, "status": "imported_to_employee_master", "imported_employee_id": employee["employee_id"]}, actor)
        append_audit_log(employee["employee_id"], "employee_created", "employee", ["employee"], f"Created employee {employee['employee_id']} from onboarding {request_id}", None, employee, actor)
        self.redirect(url_with_lang(f"/employees/{quote(employee['employee_id'])}", lang), operation_notice(messages, "Employee", get_employee_number(employee), "created", actor))


    def send_dashboard(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        metrics = dashboard_metrics(employees)
        alerts = dashboard_alerts(employees)
        alert_rows = []
        for alert in alerts:
            employee_id = alert["employee_id"]
            employee_number = alert.get("employee_number") or employee_id
            alert_rows.append(
                f"""
<tr>
  <td><a href="{h(url_with_lang(f'/employees/{quote(employee_id)}', lang))}">{h(employee_number)}</a></td>
  <td>{h(alert['display_name'])}</td>
  <td><span class="badge alert">{h(t(messages, 'alert.' + alert['type']))}</span></td>
  <td>{h(alert['date'])}</td>
</tr>
"""
            )
        alert_table = "".join(alert_rows) if alert_rows else f"<tr><td colspan=\"4\" class=\"empty\">{h(t(messages, 'dashboard.no_alerts'))}</td></tr>"
        body = f"""
<section class="grid">
  <a class="card metric-card" href="{h(url_with_lang('/employees', lang))}"><div class="muted">{h(t(messages, 'dashboard.total_employees'))}</div><p class="metric">{metrics['total_employees']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/employees', lang, {'status': 'active'}))}"><div class="muted">{h(t(messages, 'dashboard.active_employees'))}</div><p class="metric">{metrics['active_employees']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/employees', lang, {'new_joiners_month': '1'}))}"><div class="muted">{h(t(messages, 'dashboard.new_joiners'))}</div><p class="metric">{metrics['new_joiners']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/dispatch-assignments', lang))}"><div class="muted">{h(t(messages, 'dashboard.dispatch_employees'))}</div><p class="metric">{metrics['dispatch_employees']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/visa-expiry', lang))}"><div class="muted">{h(t(messages, 'dashboard.foreign_employees'))}</div><p class="metric">{metrics['foreign_employees']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/visa-expiry', lang))}"><div class="muted">{h(t(messages, 'dashboard.visa_expiry_alerts'))}</div><p class="metric">{metrics['visa_expiry_alerts']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/probation-ending', lang))}"><div class="muted">{h(t(messages, 'dashboard.probation_alerts'))}</div><p class="metric">{metrics['probation_alerts']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/labor-contract-renewals', lang))}"><div class="muted">{h(t(messages, 'dashboard.labor_contract_renewal_alerts'))}</div><p class="metric">{metrics['labor_contract_renewal_alerts']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/data-completion', lang))}"><div class="muted">{h(t(messages, 'dashboard.avg_data_completion'))}</div><p class="metric">{metrics['avg_data_completion']}%</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/data-completion', lang))}"><div class="muted">{h(t(messages, 'dashboard.incomplete_employees'))}</div><p class="metric">{metrics['incomplete_employees']}</p></a>
  <a class="card metric-card" href="{h(url_with_lang('/reports/required-document-matrix', lang))}"><div class="muted">{h(t(messages, 'dashboard.missing_required_documents'))}</div><p class="metric">{metrics['missing_required_documents']}</p></a>
</section>
<section class="card">
  <h2>{h(t(messages, 'dashboard.title'))}</h2>
  <p class="muted">{h(t(messages, 'dashboard.description'))}</p>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/employees', lang))}">{h(t(messages, 'nav.employees'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/onboarding', lang))}">{h(t(messages, 'nav.onboarding'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/employees/new', lang))}">{h(t(messages, 'action.create_employee'))}</a>
    <a class="button light" href="{h(url_with_lang('/reports', lang))}">{h(t(messages, 'nav.reports'))}</a>
  </div>
</section>
<section class="card">
  <div class="actions">
    <div>
      <h2>{h(t(messages, 'dashboard.onboarding_self_service_title'))}</h2>
      <p class="muted">{h(t(messages, 'dashboard.onboarding_self_service_description'))}</p>
    </div>
    <a class="button" href="{h(url_with_lang('/onboarding', lang))}">{h(t(messages, 'dashboard.onboarding_manage'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/onboarding/new', lang))}">{h(t(messages, 'dashboard.onboarding_new_link'))}</a>
  </div>
</section>
<section class="card">
  <h2>{h(t(messages, 'dashboard.alerts'))}</h2>
  <table>
    <thead><tr><th>{h(field_label(messages, 'employee_number'))}</th><th>{h(field_label(messages, 'profile.name.display_name'))}</th><th>{h(t(messages, 'dashboard.alert_type'))}</th><th>{h(t(messages, 'dashboard.alert_date'))}</th></tr></thead>
    <tbody>{alert_table}</tbody>
  </table>
  <div class="helper-text" style="margin-top:8px">{len(alerts)} alert(s) total</div>
</section>
"""
        self.send_html(200, t(messages, "dashboard.title"), body, lang, messages)

    def report_card(self, lang: str, messages: dict[str, str], title_key: str, description_key: str, path: str, count: int | None = None) -> str:
        count_html = f"<p class=\"metric\">{count}</p>" if count is not None else ""
        return f"""
<article class="card">
  <h3><a href="{h(url_with_lang(path, lang))}">{h(t(messages, title_key))}</a></h3>
  {count_html}
  <p class="muted">{h(t(messages, description_key))}</p>
</article>
"""

    def render_report_table(self, headers: list[str], rows: list[list[str]], empty_message: str) -> str:
        header_html = "".join(f"<th>{h(header)}</th>" for header in headers)
        if rows:
            body_html = "".join("<tr>" + "".join(f"<td>{cell}</td>" for cell in row) + "</tr>" for row in rows)
        else:
            body_html = f"<tr><td colspan=\"{len(headers)}\" class=\"empty\">{h(empty_message)}</td></tr>"
        return f"""
<table>
  <thead><tr>{header_html}</tr></thead>
  <tbody>{body_html}</tbody>
</table>
"""

    def report_employee_link(self, employee: dict[str, Any], lang: str) -> str:
        employee_id = str(employee.get("employee_id", ""))
        return f"<a href=\"{h(url_with_lang(f'/employees/{quote(employee_id)}', lang))}\">{h(get_employee_number(employee))}</a>"

    def send_reports_index(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        cards = [
            self.report_card(lang, messages, "reports.missing_required_data.title", "reports.missing_required_data.description", "/reports/missing-required-data", len(report_missing_required_data(employees))),
            self.report_card(lang, messages, "reports.visa_expiry.title", "reports.visa_expiry.description", "/reports/visa-expiry", len(report_visa_expiry(employees))),
            self.report_card(lang, messages, "reports.probation_ending.title", "reports.probation_ending.description", "/reports/probation-ending", len(report_probation_ending(employees))),
            self.report_card(lang, messages, "reports.labor_contract_renewals.title", "reports.labor_contract_renewals.description", "/reports/labor-contract-renewals", len(report_labor_contract_renewals(employees))),
            self.report_card(lang, messages, "reports.dispatch_assignments.title", "reports.dispatch_assignments.description", "/reports/dispatch-assignments", len(report_dispatch_assignments(employees))),
            self.report_card(lang, messages, "reports.document_expiry.title", "reports.document_expiry.description", "/reports/document-expiry", len(report_document_expiry(employees))),
            self.report_card(lang, messages, "reports.missing_documents.title", "reports.missing_documents.description", "/reports/missing-documents", len(report_missing_documents(employees))),
            self.report_card(lang, messages, "reports.data_quality.title", "reports.data_quality.description", "/reports/data-quality", len(report_data_quality(employees))),
            self.report_card(lang, messages, "reports.data_completion.title", "reports.data_completion.description", "/reports/data-completion", len(report_data_completion(employees))),
            self.report_card(lang, messages, "reports.payroll_readiness.title", "reports.payroll_readiness.description", "/reports/payroll-readiness", len([row for row in report_payroll_readiness(employees) if not row["payroll_readiness"]["ready"]])),
            self.report_card(lang, messages, "reports.required_document_matrix.title", "reports.required_document_matrix.description", "/reports/required-document-matrix", len(report_missing_required_documents(employees))),
        ]
        body = f"""
<section class="card">
  <div class="actions">
    <h2>{h(t(messages, 'reports.title'))}</h2>
    <a class="button" href="{h(url_with_lang('/exports/employees.csv', lang))}">{h(t(messages, 'reports.export_csv'))}</a>
  </div>
  <p class="muted">{h(t(messages, 'reports.description'))}</p>
  <p class="muted">{h(t(messages, 'reports.safe_export_note'))}</p>
</section>
<section class="grid">
  {''.join(cards)}
</section>
"""
        self.send_html(200, t(messages, "reports.title"), body, lang, messages)

    def send_missing_required_data_report(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        context, _error = masterdata_context_for_employees(self.current_session_id(), lang, visible_employees(employees))
        rows = []
        for item in report_missing_required_data(employees):
            employee = item["employee"]
            missing = ", ".join(field_label(messages, path) for path in item["missing_fields"])
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(get_nested(employee, "profile.email")),
                h(employment_department_display(employee, context)),
                h(enum_label(messages, "status", str(get_nested(employee, "employment.status")))),
                h(missing),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "profile.email"), field_label(messages, "employment.department_id"), field_label(messages, "employment.status"), t(messages, "reports.missing_fields")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.missing_required_data.title", "reports.missing_required_data.description", table, count=len(rows))

    def send_visa_expiry_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_visa_expiry(load_employees()):
            employee = item["employee"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(get_nested(employee, "profile.nationality")),
                h(get_nested(employee, "visa.residence_status")),
                h(get_nested(employee, "visa.visa_type")),
                h(get_nested(employee, "visa.expiry_date")),
                h(item["days_until"] if item["days_until"] is not None else ""),
                h(bool_label(messages, get_nested(employee, "visa.renewal_reminder_enabled", False))),
                h(get_nested(employee, "visa.renewal_reminder_date")),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "profile.nationality"), field_label(messages, "visa.residence_status"), field_label(messages, "visa.visa_type"), field_label(messages, "visa.expiry_date"), t(messages, "reports.days_until"), field_label(messages, "visa.renewal_reminder_enabled"), field_label(messages, "visa.renewal_reminder_date")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.visa_expiry.title", "reports.visa_expiry.description", table, count=len(rows))

    def send_probation_ending_report(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        context, _error = masterdata_context_for_employees(self.current_session_id(), lang, visible_employees(employees))
        rows = []
        for item in report_probation_ending(employees):
            employee = item["employee"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(employment_department_display(employee, context)),
                h(get_nested(employee, "employment.position")),
                h(get_nested(employee, "employment.join_date")),
                h(get_nested(employee, "employment.probation_end_date")),
                h(item["days_until"] if item["days_until"] is not None else ""),
                h(get_nested(employee, "employment.manager_employee_id")),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "employment.department_id"), field_label(messages, "employment.position"), field_label(messages, "employment.join_date"), field_label(messages, "employment.probation_end_date"), t(messages, "reports.days_until"), field_label(messages, "employment.manager_employee_id")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.probation_ending.title", "reports.probation_ending.description", table, count=len(rows))

    def send_labor_contract_renewal_report(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        context, _error = masterdata_context_for_employees(self.current_session_id(), lang, visible_employees(employees))
        rows = []
        for item in report_labor_contract_renewals(employees):
            employee = item["employee"]
            contract_end = str(get_nested(employee, "employment.contract.end_date", "")).strip()
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(employment_department_display(employee, context)),
                h(enum_label(messages, "employment_type", str(get_nested(employee, "employment.employment_type")))),
                h(enum_label(messages, "status", str(get_nested(employee, "employment.status")))),
                h(get_nested(employee, "employment.contract.start_date")),
                h(labor_contract_end_display(messages, contract_end)),
                h(item["days_until"] if item["days_until"] is not None else ""),
                h(get_nested(employee, "employment.manager_employee_id")),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "employment.department_id"), field_label(messages, "employment.employment_type"), field_label(messages, "employment.status"), field_label(messages, "employment.contract.start_date"), field_label(messages, "employment.contract.end_date"), t(messages, "reports.days_until"), field_label(messages, "employment.manager_employee_id")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.labor_contract_renewals.title", "reports.labor_contract_renewals.description", table, count=len(rows))

    def send_dispatch_assignment_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_dispatch_assignments(load_employees()):
            employee = item["employee"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(enum_label(messages, "employment_type", str(get_nested(employee, "employment.employment_type")))),
                h(get_nested(employee, "dispatch_compliance.client_name")),
                h(get_nested(employee, "dispatch_compliance.assignment_location")),
                h(get_nested(employee, "dispatch_compliance.dispatch_start_date")),
                h(get_nested(employee, "dispatch_compliance.dispatch_end_date")),
                h(enum_label(messages, "dispatch_contract_type", str(get_nested(employee, "dispatch_compliance.contract_type")))),
                h(get_nested(employee, "dispatch_compliance.supervisor.name")),
                h(get_nested(employee, "dispatch_compliance.supervisor.email")),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "employment.employment_type"), field_label(messages, "dispatch_compliance.client_name"), field_label(messages, "dispatch_compliance.assignment_location"), field_label(messages, "dispatch_compliance.dispatch_start_date"), field_label(messages, "dispatch_compliance.dispatch_end_date"), field_label(messages, "dispatch_compliance.contract_type"), field_label(messages, "dispatch_compliance.supervisor.name"), field_label(messages, "dispatch_compliance.supervisor.email")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.dispatch_assignments.title", "reports.dispatch_assignments.description", table, count=len(rows))

    def send_document_expiry_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_document_expiry(load_employees()):
            employee = item["employee"]
            document = item["document"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(document.get("document_id", "")),
                h(enum_label(messages, "document_type", document.get("document_type", ""))),
                h(document.get("title", "")),
                h(enum_label(messages, "document_status", document.get("status", ""))),
                h(document.get("expiry_date", "")),
                h(item["days_until"] if item["days_until"] is not None else ""),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "documents.document_id"), field_label(messages, "documents.document_type"), field_label(messages, "documents.title"), field_label(messages, "documents.status"), field_label(messages, "documents.expiry_date"), t(messages, "reports.days_until")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.document_expiry.title", "reports.document_expiry.description", table, count=len(rows))

    def send_missing_documents_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_missing_documents(load_employees()):
            employee = item["employee"]
            document = item["document"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(document.get("document_id", "")),
                h(enum_label(messages, "document_type", document.get("document_type", ""))),
                h(document.get("title", "")),
                h(enum_label(messages, "document_status", document.get("status", ""))),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "documents.document_id"), field_label(messages, "documents.document_type"), field_label(messages, "documents.title"), field_label(messages, "documents.status")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.missing_documents.title", "reports.missing_documents.description", table, count=len(rows))

    def send_data_quality_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_data_quality(load_employees()):
            employee = item["employee"]
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(t(messages, item["issue_key"])),
                h(item["value"]),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), t(messages, "reports.issue"), t(messages, "reports.duplicate_value")],
            rows,
            t(messages, "reports.no_data_quality_issues"),
        )
        self.send_report_page(lang, messages, "reports.data_quality.title", "reports.data_quality.description", table, count=len(rows))

    def send_data_completion_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_data_completion(load_employees()):
            employee = item["employee"]
            data_score = item["data_score"]
            document_score = item["document_score"]
            missing_fields = ", ".join(field_label(messages, path) for path in data_score["missing_fields"]) or "-"
            missing_docs = ", ".join(enum_label(messages, "document_type", document_type) for document_type in document_score["missing_document_types"]) or "-"
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(f"{data_score['percent']}%"),
                h(f"{data_score['completed']} / {data_score['total']}"),
                h(missing_fields),
                h(f"{document_score['percent']}%"),
                h(missing_docs),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), t(messages, "completion.data_completion"), t(messages, "completion.completed_total"), t(messages, "reports.missing_fields"), t(messages, "completion.document_completion"), t(messages, "documents.required_missing")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.data_completion.title", "reports.data_completion.description", table, count=len(rows))

    def send_payroll_readiness_report(self, lang: str, messages: dict[str, str]) -> None:
        employees = load_employees()
        context, _error = masterdata_context_for_employees(self.current_session_id(), lang, visible_employees(employees))
        rows = []
        for item in report_payroll_readiness(employees):
            employee = item["employee"]
            score = item["payroll_readiness"]
            missing = ", ".join(field_label(messages, path) for path in score["missing_fields"])
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(employment_entity_display(employee, context)),
                h(employment_department_display(employee, context)),
                h(enum_label(messages, "country", str(get_nested(employee, "employment.country_code")))),
                h(enum_label(messages, "country", str(get_nested(employee, "employment.work_country")))),
                h(enum_label(messages, "business_line", str(get_nested(employee, "employment.business_line")))),
                h(enum_label(messages, "status", str(get_nested(employee, "employment.status")))),
                h(f"{score['completed']} / {score['total']} ({score['percent']}%)"),
                h(t(messages, "payroll_readiness.ready") if score["ready"] else t(messages, "payroll_readiness.blocked")),
                h(missing or t(messages, "reports.empty")),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "employment.entity_id"), field_label(messages, "employment.department_id"), field_label(messages, "employment.country_code"), field_label(messages, "employment.work_country"), field_label(messages, "employment.business_line"), field_label(messages, "employment.status"), t(messages, "payroll_readiness.score"), t(messages, "payroll_readiness.status"), t(messages, "reports.missing_fields")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.payroll_readiness.title", "reports.payroll_readiness.description", table, count=len(rows))

    def send_required_document_matrix_report(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        for item in report_required_document_matrix(load_employees()):
            employee = item["employee"]
            status_key = "documents.requirement_complete" if item["is_complete"] else "documents.requirement_missing"
            rows.append([
                self.report_employee_link(employee, lang),
                h(get_nested(employee, "profile.name.display_name")),
                h(enum_label(messages, "document_type", str(item["document_type"]))),
                h(t(messages, status_key)),
                h(str(item["matched_count"])),
                h(item["latest_expiry_date"] or "-"),
                h(item["days_until_expiry"] if item["days_until_expiry"] is not None else ""),
            ])
        table = self.render_report_table(
            [field_label(messages, "employee_number"), field_label(messages, "profile.name.display_name"), field_label(messages, "documents.document_type"), t(messages, "documents.requirement_status"), t(messages, "documents.matched_count"), field_label(messages, "documents.expiry_date"), t(messages, "reports.days_until")],
            rows,
            t(messages, "reports.empty"),
        )
        self.send_report_page(lang, messages, "reports.required_document_matrix.title", "reports.required_document_matrix.description", table, count=len(rows))

    def send_report_page(self, lang: str, messages: dict[str, str], title_key: str, description_key: str, table_html: str, count: int | None = None) -> None:
        count_html = f"<div class='helper-text' style='margin-top:8px'>{count} record(s) total</div>" if count is not None else ""
        body = f"""
<section class="card">
  <div class="actions">
    <h2>{h(t(messages, title_key))}</h2>
    <a class="button light" href="{h(url_with_lang('/reports', lang))}">{h(t(messages, 'action.back'))}</a>
  </div>
  <p class="muted">{h(t(messages, description_key))}</p>
  <p class="muted">{h(t(messages, 'reports.safe_export_note'))}</p>
</section>
<section class="card">
  {table_html}
  {count_html}
</section>
"""
        self.send_html(200, t(messages, title_key), body, lang, messages)

    def send_employee_master_csv(self) -> None:
        output = io.StringIO(newline="")
        fieldnames = [column for column, _path in SAFE_EMPLOYEE_EXPORT_FIELDS]
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        employees = load_employees()
        context, _error = masterdata_context_for_employees(self.current_session_id(), DEFAULT_LANG, visible_employees(employees))
        writer.writerows(safe_employee_export_rows(employees, context))
        body = output.getvalue().encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="employees.csv"')
        if getattr(self, "_clear_flash_after_response", False):
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
            self._clear_flash_after_response = False
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def import_header_lang(self, query: dict[str, list[str]], lang: str) -> str:
        return csv_header_language(query.get("header_lang", [lang])[0])

    def send_csv_download(self, filename: str, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
        output = io.StringIO(newline="")
        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
        body = output.getvalue().encode("utf-8-sig")
        self.send_document_bytes(200, "text/csv; charset=utf-8", body, f'attachment; filename="{filename}"')

    def send_employee_import_template_csv(self, query: dict[str, list[str]], lang: str) -> None:
        header_lang = self.import_header_lang(query, lang)
        self.send_csv_download(f"employees_import_template_{header_lang}.csv", localized_csv_fieldnames(COMMON_REQUIRED_CSV_FIELDS, header_lang), [])

    def employee_import_field_guide_rows(self, messages: dict[str, str], header_lang: str = "en") -> list[dict[str, str]]:
        allowed_values = {
            "country_code": ", ".join(COUNTRY_CODES),
            "work_country": ", ".join(COUNTRY_CODES),
            "employment_status": ", ".join(EMPLOYMENT_STATUSES),
            "employment_type": ", ".join(EMPLOYMENT_TYPES),
            "business_line": ", ".join(BUSINESS_LINES),
            "profile_status": ", ".join(PROFILE_STATUSES),
            "legal_entity_code": t(messages, "import.allowed_legal_entity_code"),
            "department_code": t(messages, "import.allowed_department_code"),
            "bank_account_type": ", ".join(value for value in BANK_ACCOUNT_TYPES if value),
        }
        rows = []
        labels = CSV_HEADER_LABELS[csv_header_language(header_lang)]
        required_fields = set(IMPORT_REQUIRED_CSV_FIELDS)
        for csv_field, path in COMMON_REQUIRED_FIELD_MAPPING:
            rows.append({
                "csv_field": labels.get(csv_field, csv_field),
                "canonical_field": csv_field,
                "label": field_label(messages, path),
                "required": t(messages, "boolean.yes") if csv_field in required_fields else t(messages, "boolean.no"),
                "allowed_values": allowed_values.get(csv_field, ""),
                "description": t(messages, f"import.field_description.{csv_field}", ""),
            })
        return rows

    def send_employee_import_field_guide_csv(self, query: dict[str, list[str]], lang: str, messages: dict[str, str]) -> None:
        header_lang = self.import_header_lang(query, lang)
        filename = f"employees_import_field_guide_{header_lang}.csv"
        self.send_csv_download(filename, ["csv_field", "canonical_field", "label", "required", "allowed_values", "description"], self.employee_import_field_guide_rows(messages, header_lang))

    def send_employee_import_sample_csv(self, query: dict[str, list[str]], lang: str) -> None:
        header_lang = self.import_header_lang(query, lang)
        rows = [
            {"employee_id": "JP-EMP-0001", "full_name": "山田 太郎", "country_code": "JP", "legal_entity_code": "JP", "employment_status": "active", "employment_type": "employee", "hire_date": "2026-04-01", "department_code": "RECRUITMENT", "work_email": "taro.yamada@example.com", "work_country": "JP", "business_line": "recruitment", "profile_status": "complete", "bank_name": "Sample Bank", "bank_branch_name": "Tokyo", "bank_account_type": "ordinary", "bank_account_number": "1234567", "bank_account_holder": "YAMADA TARO", "bank_swift_code": "SMPLJPJT", "labor_contract_start_date": "2026-04-01", "labor_contract_end_date": "2099-12-12"},
            {"employee_id": "CN-EMP-0001", "full_name": "张三", "country_code": "CN", "legal_entity_code": "CN", "employment_status": "active", "employment_type": "contractor", "hire_date": "2026-04-01", "department_code": "RPO", "work_email": "zhang.san@example.com", "work_country": "CN", "business_line": "rpo", "profile_status": "needs_review", "bank_name": "Sample Bank", "bank_branch_name": "Shanghai", "bank_account_type": "ordinary", "bank_account_number": "1234567890", "bank_account_holder": "ZHANG SAN", "bank_swift_code": "SMPLCNBS", "labor_contract_start_date": "2026-04-01", "labor_contract_end_date": "2027-03-31"},
            {"employee_id": "SG-EMP-0001", "full_name": "Tan Wei Ming", "country_code": "SG", "legal_entity_code": "SG", "employment_status": "active", "employment_type": "employee", "hire_date": "2026-04-01", "department_code": "PAYROLL", "work_email": "tan.weiming@example.com", "work_country": "SG", "business_line": "payroll", "profile_status": "needs_review", "bank_name": "Sample Bank", "bank_branch_name": "Singapore", "bank_account_type": "savings", "bank_account_number": "123456789", "bank_account_holder": "TAN WEI MING", "bank_swift_code": "SMPLSGSG", "labor_contract_start_date": "2026-04-01", "labor_contract_end_date": "2027-03-31"},
        ]
        self.send_csv_download(f"employees_import_sample_{header_lang}.csv", localized_csv_fieldnames(COMMON_REQUIRED_CSV_FIELDS, header_lang), localize_csv_rows(rows, COMMON_REQUIRED_CSV_FIELDS, header_lang))

    def render_employee_import_error_table(self, messages: dict[str, str], import_errors: list[dict[str, Any]]) -> str:
        if not import_errors:
            return ""
        rows = "".join(
            f"<tr><td>{h(str(error.get('row') or ''))}</td><td>{h(str(error.get('csv_field') or ''))}</td><td>{h(str(error.get('label') or ''))}</td><td>{h(str(error.get('message') or ''))}</td><td>{h(str(error.get('suggestion') or ''))}</td></tr>"
            for error in import_errors
        )
        return f"""
<section class="card">
  <h3>{h(t(messages, 'import.error_report'))}</h3>
  <table>
    <thead><tr><th>{h(t(messages, 'import.row'))}</th><th>{h(t(messages, 'import.csv_field'))}</th><th>{h(t(messages, 'import.label'))}</th><th>{h(t(messages, 'import.error'))}</th><th>{h(t(messages, 'import.suggestion'))}</th></tr></thead>
    <tbody>{rows}</tbody>
  </table>
</section>
"""

    def send_employee_import_page(self, lang: str, messages: dict[str, str], errors: list[str] | None = None, import_errors: list[dict[str, Any]] | None = None) -> None:
        errors = errors or []
        import_errors = import_errors or []
        guide_rows = "".join(
            f"<tr><td>{h(row['csv_field'])}</td><td>{h(row['canonical_field'])}</td><td>{h(row['label'])}</td><td>{h(row['required'])}</td><td>{h(row['allowed_values'] or '-')}</td><td>{h(row['description'])}</td></tr>"
            for row in self.employee_import_field_guide_rows(messages, lang)
        )
        header_links = "".join(
            f"""
            <div class=\"card\">
              <h4>{h(t(messages, 'import.header_language.' + header_lang))}</h4>
              <div class=\"actions\">
                <a class=\"button\" href=\"{h(url_with_lang('/exports/employees-import-template.csv', lang, {'header_lang': header_lang}))}\">{h(t(messages, 'import.download_template'))}</a>
                <a class=\"button light\" href=\"{h(url_with_lang('/exports/employees-import-field-guide.csv', lang, {'header_lang': header_lang}))}\">{h(t(messages, 'import.download_field_guide'))}</a>
                <a class=\"button light\" href=\"{h(url_with_lang('/exports/employees-import-sample.csv', lang, {'header_lang': header_lang}))}\">{h(t(messages, 'import.download_sample'))}</a>
              </div>
            </div>
            """
            for header_lang in CSV_HEADER_LANGS
        )
        body = f"""
<section class="card">
  <div class="actions">
    <h2>{h(t(messages, 'import.title'))}</h2>
    <a class="button light" href="{h(url_with_lang('/employees', lang))}">{h(t(messages, 'action.back'))}</a>
  </div>
  <p class="muted">{h(t(messages, 'import.description'))}</p>
  {self.render_errors(messages, errors)}
  <h3>{h(t(messages, 'import.header_language_title'))}</h3>
  <div class="grid">
    {header_links}
  </div>
  <ol>
    <li>{h(t(messages, 'import.instruction_1'))}</li>
    <li>{h(t(messages, 'import.instruction_2'))}</li>
    <li>{h(t(messages, 'import.instruction_3'))}</li>
    <li>{h(t(messages, 'import.instruction_4'))}</li>
    <li>{h(t(messages, 'import.instruction_5'))}</li>
  </ol>
</section>
<section class="card">
  <h3>{h(t(messages, 'import.upload_title'))}</h3>
  <form method="post" enctype="multipart/form-data" action="{h(url_with_lang('/employees/import', lang))}">
    <div class="form-grid">
      <div class="form-field"><label for="upload_files">{h(t(messages, 'import.upload_csv'))}</label><input id="upload_files" type="file" name="upload_files" accept=".csv,text/csv" required></div>
      <div class="form-field actions"><button type="submit">{h(t(messages, 'import.validate_and_import'))}</button></div>
    </div>
  </form>
</section>
<section class="card">
  <h3>{h(t(messages, 'import.field_guide'))}</h3>
  <table><thead><tr><th>{h(t(messages, 'import.csv_header'))}</th><th>{h(t(messages, 'import.csv_field'))}</th><th>{h(t(messages, 'import.label'))}</th><th>{h(t(messages, 'import.required'))}</th><th>{h(t(messages, 'import.allowed_values'))}</th><th>{h(t(messages, 'import.description_column'))}</th></tr></thead><tbody>{guide_rows}</tbody></table>
</section>
{self.render_employee_import_error_table(messages, import_errors)}
"""
        self.send_html(200, t(messages, "import.title"), body, lang, messages)

    def send_employee_list(self, lang: str, messages: dict[str, str], query: dict[str, list[str]], user: dict[str, Any]) -> None:
        employees = load_employees()
        results = filter_employees(employees, query)
        context, masterdata_error = masterdata_context_for_employees(self.current_session_id(), lang, visible_employees(employees))
        q = query.get("q", [""])[0]
        entity_id = query.get("entity_id", [""])[0]
        country_code = normalize_country_code(query.get("country_code", [""])[0])
        department = query.get("department_id", query.get("department", [""]))[0]
        team_id = query.get("team_id", [""])[0]
        status = query.get("status", [""])[0]
        show_resigned = query.get("show_resigned", [""])[0] == "1"
        employment_type = query.get("employment_type", [""])[0]
        japanese_level = query.get("japanese_level", [""])[0]
        english_level = query.get("english_level", [""])[0]
        skill = query.get("skill", [""])[0]
        new_joiners_month = query.get("new_joiners_month", [""])[0] == "1"
        has_filter = bool(q or entity_id or country_code or department or team_id or status or show_resigned or employment_type or japanese_level or english_level or skill or new_joiners_month)
        can_view = has_permission(user, "employee_management.access")
        can_edit = has_permission(user, "employee_management.edit")
        rows = []
        for employee in results:
            employee_id = str(employee.get("employee_id", ""))
            employee_number = get_employee_number(employee)
            detail_url = url_with_lang(f"/employees/{quote(employee_id)}", lang)
            edit_url = url_with_lang(f"/employees/{quote(employee_id)}/edit", lang)
            action_links = []
            if can_view:
                action_links.append(f'<a href="{h(detail_url)}">{h(t(messages, "action.view"))}</a>')
            if can_edit:
                action_links.append(f'<a href="{h(edit_url)}">{h(t(messages, "action.edit"))}</a>')
            actions_html = " | ".join(action_links) if action_links else "-"
            rows.append(
                f"""
<tr>
  <td><a href="{h(detail_url)}">{h(employee_number)}</a></td>
  <td>{h(get_nested(employee, 'profile.name.display_name'))}</td>
  <td>{h(get_nested(employee, 'profile.email'))}</td>
  <td>{h(employment_entity_display(employee, context))}</td>
  <td>{h(employment_department_display(employee, context))}</td>
  <td>{h(employment_team_display(employee, context))}</td>
  <td>{h(get_nested(employee, 'employment.position'))}</td>
  <td>{h(enum_label(messages, 'employment_type', str(get_nested(employee, 'employment.employment_type'))))}</td>
  <td><span class="badge">{h(enum_label(messages, 'status', str(get_nested(employee, 'employment.status'))))}</span></td>
  <td>{h(enum_label(messages, 'japanese_level', str(get_nested(employee, 'language_profile.japanese_level'))))}</td>
  <td>{h(enum_label(messages, 'english_level', str(get_nested(employee, 'language_profile.english_level'))))}</td>
  <td>{h(get_nested(employee, 'skills_profile.primary_skill'))}</td>
  <td>{actions_html}</td>
</tr>
"""
            )
        table_body = "".join(rows) if rows else f"<tr><td colspan=\"13\" class=\"empty\">{h(t(messages, 'employee.list.empty'))}</td></tr>"
        entity_options = "".join(
            f"<option value=\"{h(value)}\"{selected(entity_id, value)}>{h(masterdata_context_label(context, 'entities', value))}</option>"
            for value in unique_entity_ids(employees)
        )
        country_options = "".join(
            f"<option value=\"{h(value)}\"{selected(country_code, value)}>{h(enum_label(messages, 'country', value))}</option>"
            for value in COUNTRY_CODES
        )
        department_option_employees = [
            employee for employee in visible_employees(employees) if not entity_id or employment_entity_id(employee) == entity_id
        ]
        department_options = "".join(
            f"<option value=\"{h(value)}\"{selected(department, value)}>{h(masterdata_context_label(context, 'departments', value))}</option>"
            for value in unique_department_ids(department_option_employees)
        )
        team_option_employees = [
            employee for employee in department_option_employees
            if not department or employment_department_id(employee) == department
        ]
        team_options = "".join(
            f"<option value=\"{h(value)}\"{selected(team_id, value)}>{h(masterdata_context_label(context, 'teams', value))}</option>"
            for value in unique_team_ids(team_option_employees)
        )
        masterdata_warning = f'<p class="muted">{h(t(messages, "validation.masterdata_unavailable"))}</p>' if masterdata_error else ""
        status_options = "".join(
            f"<option value=\"{h(value)}\"{selected(status, value)}>{h(enum_label(messages, 'status', value))}</option>"
            for value in EMPLOYMENT_STATUSES
        )
        show_resigned_checked = " checked" if show_resigned else ""
        type_options = "".join(
            f"<option value=\"{h(value)}\"{selected(employment_type, value)}>{h(enum_label(messages, 'employment_type', value))}</option>"
            for value in EMPLOYMENT_TYPES
        )
        japanese_options = "".join(
            f"<option value=\"{h(value)}\"{selected(japanese_level, value)}>{h(t(messages, 'filter.all') if value == '' else enum_label(messages, 'japanese_level', value))}</option>"
            for value in JAPANESE_LEVELS
        )
        english_options = "".join(
            f"<option value=\"{h(value)}\"{selected(english_level, value)}>{h(t(messages, 'filter.all') if value == '' else enum_label(messages, 'english_level', value))}</option>"
            for value in ENGLISH_LEVELS
        )
        create_button = f'<a class="button" href="{h(url_with_lang("/employees/new", lang))}">{h(t(messages, "action.create_employee"))}</a>' if can_edit else ""
        import_button = f'<a class="button light" href="{h(url_with_lang("/employees/import", lang))}">{h(t(messages, "import.title"))}</a>' if can_edit else ""
        body = f"""
<section class="card">
  <div class="actions">
    <h2>{h(t(messages, 'employee.list.title'))}</h2>
    {create_button}
    {import_button}
  </div>
  {masterdata_warning}
  <form method="get" action="/employees" class="form-grid">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-field"><label for="q">{h(t(messages, 'action.search'))}</label><input id="q" name="q" value="{h(q)}" placeholder="{h(t(messages, 'employee.search_placeholder'))}"></div>
    <div class="form-field"><label for="entity">{h(field_label(messages, 'employment.entity_id'))}</label><select id="entity" name="entity_id"><option value="">{h(t(messages, 'filter.all'))}</option>{entity_options}</select></div>
    <div class="form-field"><label for="country_code">{h(field_label(messages, 'employment.country_code'))}</label><select id="country_code" name="country_code"><option value="">{h(t(messages, 'filter.all'))}</option>{country_options}</select></div>
    <div class="form-field"><label for="department">{h(field_label(messages, 'employment.department_id'))}</label><select id="department" name="department_id"><option value="">{h(t(messages, 'filter.all'))}</option>{department_options}</select></div>
    <div class="form-field"><label for="team">{h(field_label(messages, 'employment.team_id'))}</label><select id="team" name="team_id"><option value="">{h(t(messages, 'filter.all'))}</option>{team_options}</select></div>
    <div class="form-field"><label for="status">{h(field_label(messages, 'employment.status'))}</label><select id="status" name="status"><option value="">{h(t(messages, 'filter.all'))}</option>{status_options}</select></div>
    <div class="form-field checkbox-field"><label for="show_resigned"><input id="show_resigned" type="checkbox" name="show_resigned" value="1"{show_resigned_checked}> {h(t(messages, 'filter.show_resigned'))}</label></div>
    <div class="form-field"><label for="employment_type">{h(field_label(messages, 'employment.employment_type'))}</label><select id="employment_type" name="employment_type"><option value="">{h(t(messages, 'filter.all'))}</option>{type_options}</select></div>
    <div class="form-field"><label for="japanese_level">{h(field_label(messages, 'language_profile.japanese_level'))}</label><select id="japanese_level" name="japanese_level">{japanese_options}</select></div>
    <div class="form-field"><label for="english_level">{h(field_label(messages, 'language_profile.english_level'))}</label><select id="english_level" name="english_level">{english_options}</select></div>
    <div class="form-field"><label for="skill">{h(t(messages, 'filter.skill'))}</label><input id="skill" name="skill" value="{h(skill)}" placeholder="{h(t(messages, 'filter.skill_placeholder'))}"></div>
    <div class="form-field actions"><button type="submit">{h(t(messages, 'action.filter'))}</button><a class="button light" href="{h(url_with_lang('/employees', lang))}">{h(t(messages, 'action.clear'))}</a></div>
  </form>
</section>
<section class="card">
  <p class="muted">{h(t(messages, 'employee.list.sensitive_note'))}</p>
  <p class="muted">{h(t(messages, 'employee.list.resigned_hidden_note'))}</p>
  <table>
    <thead><tr>
      <th>{h(field_label(messages, 'employee_number'))}</th><th>{h(field_label(messages, 'profile.name.display_name'))}</th><th>{h(field_label(messages, 'profile.email'))}</th><th>{h(field_label(messages, 'employment.entity_id'))}</th><th>{h(field_label(messages, 'employment.department_id'))}</th><th>{h(field_label(messages, 'employment.team_id'))}</th><th>{h(field_label(messages, 'employment.position'))}</th><th>{h(field_label(messages, 'employment.employment_type'))}</th><th>{h(field_label(messages, 'employment.status'))}</th><th>{h(field_label(messages, 'language_profile.japanese_level'))}</th><th>{h(field_label(messages, 'language_profile.english_level'))}</th><th>{h(field_label(messages, 'skills_profile.primary_skill'))}</th><th>{h(t(messages, 'table.actions'))}</th>
    </tr></thead>
    <tbody>{table_body}</tbody>
  </table>
  <div class="helper-text" style="margin:8px 0 0">{f'Showing {len(results)} of {len(employees)} employees (filtered)' if has_filter else f'{len(results)} employee(s) total'}</div>
</section>
"""
        self.send_html(200, t(messages, "employee.list.title"), body, lang, messages)

    def send_employee_detail(self, lang: str, messages: dict[str, str], employee_id: str, user: dict[str, Any]) -> None:
        employee = find_employee(load_employees(), employee_id)
        if not employee or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        can_edit = has_permission(user, "employee_management.edit")
        payroll_edit_url = self.section_edit_url(employee_id, 'payroll', lang) if has_permission(user, "employee_management.payroll.edit") else None
        visa_edit_url = self.section_edit_url(employee_id, 'visa', lang) if has_permission(user, "employee_management.visa.edit") else None
        dispatch_edit_url = self.section_edit_url(employee_id, 'dispatch', lang) if can_edit else None
        skills_edit_url = self.section_edit_url(employee_id, 'skills', lang) if can_edit else None
        can_manage_documents = has_permission(user, "employee_management.documents.manage")
        documents_edit_url = self.section_edit_url(employee_id, 'documents', lang) if can_manage_documents else None
        context, masterdata_error = masterdata_context_for_employees(self.current_session_id(), lang, [employee])
        masterdata_warning = f'<div class="message-strip message-info">{h(t(messages, "validation.masterdata_unavailable"))}</div>' if masterdata_error else ""
        body = f"""
<section class="object-page employee-detail">
  {masterdata_warning}
  {self.render_detail_header(messages, employee, employee_id, lang, can_edit, context)}
  {self.render_detail_section(messages, employee, 'section.profile', groups=PROFILE_DETAIL_GROUPS, masterdata_context=context)}
  {self.render_detail_section(messages, employee, 'section.employment', groups=EMPLOYMENT_DETAIL_GROUPS, masterdata_context=context)}
  {self.render_history_section(messages, employee, 'employment', lang, can_edit, can_manage_documents)}
  {self.render_detail_section(messages, employee, 'section.payroll', edit_url=payroll_edit_url, edit_label=t(messages, 'action.edit_payroll'), groups=PAYROLL_DETAIL_GROUPS)}
  {self.render_detail_section(messages, employee, 'section.visa', edit_url=visa_edit_url, edit_label=t(messages, 'action.edit_visa'), groups=VISA_DETAIL_GROUPS)}
  {self.render_history_section(messages, employee, 'visa', lang, has_permission(user, 'employee_management.visa.edit'), can_manage_documents)}
  {self.render_detail_section(messages, employee, 'section.dispatch_compliance', edit_url=dispatch_edit_url, edit_label=t(messages, 'action.edit_dispatch'), groups=DISPATCH_DETAIL_GROUPS)}
  {self.render_history_section(messages, employee, 'dispatch', lang, can_edit, can_manage_documents)}
  {self.render_detail_section(messages, employee, 'section.skills_language', edit_url=skills_edit_url, edit_label=t(messages, 'action.edit_skills_language'), groups=SKILLS_LANGUAGE_DETAIL_GROUPS)}
  {self.render_documents_section(messages, employee, documents_edit_url, t(messages, 'action.edit_documents') if documents_edit_url else None, can_manage_documents, lang)}
  {self.render_data_quality_section(messages, employee)}
  {self.render_detail_section(messages, employee, 'section.metadata', groups=METADATA_DETAIL_GROUPS)}
</section>
"""
        self.send_html(200, f"{t(messages, 'employee.detail.title')} {get_employee_number(employee)}", body, lang, messages)

    def section_edit_url(self, employee_id: str, section_key: str, lang: str) -> str:
        route = SECTION_CONFIG[section_key]["route"]
        return url_with_lang(f"/employees/{quote(employee_id)}/{route}/edit", lang)

    def render_detail_header(self, messages: dict[str, str], employee: dict[str, Any], employee_id: str, lang: str, can_edit: bool, masterdata_context: dict[str, dict[str, str]] | None = None) -> str:
        display_name = str(get_nested(employee, "profile.name.display_name", "")).strip() or get_employee_number(employee) or employee_id
        employee_number = get_employee_number(employee)
        department = employment_department_display(employee, masterdata_context)
        status = display_value(messages, "employment.status", get_nested(employee, "employment.status", ""))
        employment_type = display_value(messages, "employment.employment_type", get_nested(employee, "employment.employment_type", ""))
        data_score = data_completion_score(employee)
        document_score = document_completion_score(employee)
        meta_items = [
            (field_label(messages, "employee_number"), employee_number or "-"),
            (field_label(messages, "employment.status"), status or "-"),
            (field_label(messages, "employment.department_id"), department or "-"),
            (field_label(messages, "employment.employment_type"), employment_type or "-"),
            (t(messages, "completion.data_completion"), f"{data_score['percent']}%"),
            (t(messages, "documents.required_missing"), str(len(document_score['missing_document_types']))),
        ]
        meta_html = "".join(
            f'<span class="meta-chip"><span class="meta-chip-label">{h(label)}</span><span class="meta-chip-value">{h(value)}</span></span>'
            for label, value in meta_items
        )
        edit_button = f'<a class="button" href="{h(url_with_lang(f"/employees/{quote(employee_id)}/edit", lang))}">{h(t(messages, "action.edit"))}</a>' if can_edit else ""
        return f"""
<div class="object-header">
  <div class="object-header-content">
    <p class="eyebrow">{h(t(messages, 'employee.detail.kicker'))}</p>
    <h2>{h(t(messages, 'employee.detail.title'))}: {h(display_name)}</h2>
    <p class="muted">{h(t(messages, 'employee.detail.description'))}</p>
    <div class="object-actions">
      {edit_button}
      <a class="button light" href="{h(url_with_lang('/employees', lang))}">{h(t(messages, 'action.back'))}</a>
    </div>
  </div>
  <div class="object-meta">
    {meta_html}
  </div>
</div>
"""

    def render_detail_field(self, messages: dict[str, str], employee: dict[str, Any], path: str, masterdata_context: dict[str, dict[str, str]] | None = None) -> str:
        value = display_employee_value(messages, employee, path, masterdata_context)
        is_empty = value == ""
        display_text = value if value else "-"
        field_classes = ["detail-field"]
        if path in DETAIL_LONG_FIELD_PATHS or len(display_text) > 48:
            field_classes.append("long")
        value_classes = ["detail-value"]
        if is_empty:
            value_classes.append("empty")
        return f"""
<div class="{' '.join(field_classes)}">
  <div class="detail-label">{h(field_label(messages, path))}</div>
  <div class="{' '.join(value_classes)}">{h(display_text)}</div>
</div>
"""

    def render_detail_group(self, messages: dict[str, str], employee: dict[str, Any], title_key: str, paths: list[str], masterdata_context: dict[str, dict[str, str]] | None = None) -> str:
        fields_html = "".join(self.render_detail_field(messages, employee, path, masterdata_context) for path in paths)
        return f"""
<div class="field-group">
  <h4 class="field-group-title">{h(t(messages, title_key))}</h4>
  <div class="detail-grid">{fields_html}</div>
</div>
"""

    def render_detail_section(
        self,
        messages: dict[str, str],
        employee: dict[str, Any],
        title_key: str,
        paths: list[str] | None = None,
        edit_url: str | None = None,
        edit_label: str | None = None,
        groups: list[tuple[str, list[str]]] | None = None,
        masterdata_context: dict[str, dict[str, str]] | None = None,
    ) -> str:
        section_groups = groups or [(title_key, paths or [])]
        groups_html = "".join(self.render_detail_group(messages, employee, group_title_key, group_paths, masterdata_context) for group_title_key, group_paths in section_groups)
        edit_html = f'<a class="button secondary" href="{h(edit_url)}">{h(edit_label)}</a>' if edit_url and edit_label else ""
        return f"""
<section class="form-section detail-section">
  <div class="section-header"><h3>{h(t(messages, title_key))}</h3><div class="detail-section-actions">{edit_html}</div></div>
  {groups_html}
</section>
"""

    def render_data_quality_section(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        data_score = data_completion_score(employee)
        document_score = document_completion_score(employee)
        data_quality_issues = [row for row in report_data_quality(load_employees()) if row["employee"].get("employee_id") == employee.get("employee_id")]
        missing_fields = ", ".join(field_label(messages, path) for path in data_score["missing_fields"]) or "-"
        missing_documents = ", ".join(enum_label(messages, "document_type", document_type) for document_type in document_score["missing_document_types"]) or "-"
        fields_html = f"""
        <div class="detail-field"><div class="detail-label">{h(t(messages, 'completion.data_completion'))}</div><div class="detail-value">{h(str(data_score['percent']))}%</div></div>
        <div class="detail-field"><div class="detail-label">{h(t(messages, 'completion.completed_total'))}</div><div class="detail-value">{h(str(data_score['completed']))} / {h(str(data_score['total']))}</div></div>
        <div class="detail-field"><div class="detail-label">{h(t(messages, 'completion.document_completion'))}</div><div class="detail-value">{h(str(document_score['percent']))}%</div></div>
        <div class="detail-field"><div class="detail-label">{h(t(messages, 'reports.issue'))}</div><div class="detail-value">{h(str(len(data_quality_issues)))}</div></div>
        <div class="detail-field long"><div class="detail-label">{h(t(messages, 'reports.missing_fields'))}</div><div class="detail-value">{h(missing_fields)}</div></div>
        <div class="detail-field long"><div class="detail-label">{h(t(messages, 'documents.required_missing'))}</div><div class="detail-value">{h(missing_documents)}</div></div>
        """
        return f"""
<section class="form-section detail-section">
  <div class="section-header"><h3>{h(t(messages, 'detail.group.data_quality'))}</h3></div>
  <div class="field-group">
    <div class="detail-grid">{fields_html}</div>
  </div>
</section>
"""

    def history_label(self, messages: dict[str, str], prefix: str, value: str) -> str:
        if not value:
            return ""
        return t(messages, f"{prefix}.{value}", value.replace("_", " ").title())

    def render_history_attachment_links(self, employee_id: str, history_type: str, history_id: str, attachments: list[dict[str, str]], lang: str, can_manage_documents: bool, messages: dict[str, str]) -> str:
        if not attachments:
            return "-"
        if not can_manage_documents:
            return h(str(len(attachments)))
        links = []
        for attachment in attachments:
            attachment_id = str(attachment.get("attachment_id", ""))
            title = attachment.get("title") or attachment.get("original_filename") or attachment_id
            base_url = f"/employees/{quote(employee_id)}/history/{quote(history_type)}/{quote(history_id)}/attachments/{quote(attachment_id)}"
            links.append(
                f'{h(title)}: <a href="{h(url_with_lang(base_url + "/open", lang))}" target="_blank" rel="noopener">{h(t(messages, "action.open"))}</a> | '
                f'<a href="{h(url_with_lang(base_url + "/download", lang))}">{h(t(messages, "action.download"))}</a>'
            )
        return "<br>".join(links)

    def render_history_section(self, messages: dict[str, str], employee: dict[str, Any], history_type: str, lang: str, can_edit_history: bool, can_manage_documents: bool) -> str:
        config = HISTORY_CONFIG[history_type]
        employee_id = str(employee.get("employee_id", ""))
        records = list(reversed(normalize_history_records(history_type, get_nested(employee, str(config["array_key"]), []))))
        add_html = ""
        if can_edit_history:
            add_url = url_with_lang(f"/employees/{quote(employee_id)}/history/{quote(history_type)}/new", lang)
            add_html = f'<a class="button secondary" href="{h(add_url)}">{h(t(messages, str(config["add_action_key"])) )}</a>'
        rows = []
        for record in records:
            history_id = str(record.get("history_id", ""))
            attachments = normalize_history_attachments(record.get("attachments", []))
            attachment_html = self.render_history_attachment_links(employee_id, history_type, history_id, attachments, lang, can_manage_documents, messages)
            edit_html = ""
            if can_edit_history:
                edit_url = url_with_lang(f"/employees/{quote(employee_id)}/history/{quote(history_type)}/{quote(history_id)}/edit", lang)
                edit_html = f'<a href="{h(edit_url)}">{h(t(messages, "action.edit_history"))}</a>'
            if history_type == "visa":
                cells = [
                    record.get("effective_date", ""),
                    self.history_label(messages, "history_event", str(record.get("event_type", ""))),
                    record.get("visa_type", ""),
                    record.get("residence_status", ""),
                    record.get("expiry_date", ""),
                    record.get("passport_expiry_date", ""),
                    attachment_html,
                    record.get("changed_at", ""),
                    edit_html,
                ]
            elif history_type == "dispatch":
                cells = [
                    record.get("effective_date", ""),
                    self.history_label(messages, "history_event", str(record.get("event_type", ""))),
                    record.get("client_name", ""),
                    record.get("assignment_location", ""),
                    record.get("dispatch_start_date", ""),
                    record.get("dispatch_end_date", ""),
                    enum_label(messages, "dispatch_contract_type", str(record.get("contract_type", ""))),
                    get_nested(record, "supervisor.name", ""),
                    attachment_html,
                    record.get("changed_at", ""),
                    edit_html,
                ]
            else:
                cells = [
                    record.get("effective_date", ""),
                    self.history_label(messages, "history_event", str(record.get("event_type", ""))),
                    enum_label(messages, "employment_type", str(record.get("employment_type", ""))),
                    record.get("department_id", ""),
                    record.get("position", ""),
                    enum_label(messages, "status", str(record.get("status", ""))),
                    get_nested(record, "contract.start_date", ""),
                    labor_contract_end_display(messages, str(get_nested(record, "contract.end_date", ""))),
                    record.get("manager_employee_id", ""),
                    attachment_html,
                    record.get("changed_at", ""),
                    edit_html,
                ]
            html_indexes = {6, 8} if history_type == "visa" else ({8, 10} if history_type == "dispatch" else {9, 11})
            row_cells = []
            for index, cell in enumerate(cells):
                row_cells.append(f"<td>{cell if index in html_indexes else h(cell)}</td>")
            rows.append("<tr>" + "".join(row_cells) + "</tr>")
        if history_type == "visa":
            headers = ["history.effective_date", "history.event_type", "field.visa__visa_type", "field.visa__residence_status", "field.visa__expiry_date", "field.visa__passport_expiry_date", "history.attachments", "history.changed_at", "table.actions"]
        elif history_type == "dispatch":
            headers = ["history.effective_date", "history.event_type", "field.dispatch_compliance__client_name", "field.dispatch_compliance__assignment_location", "field.dispatch_compliance__dispatch_start_date", "field.dispatch_compliance__dispatch_end_date", "field.dispatch_compliance__contract_type", "field.dispatch_compliance__supervisor__name", "history.attachments", "history.changed_at", "table.actions"]
        else:
            headers = ["history.effective_date", "history.event_type", "field.employment__employment_type", "field.employment__department_id", "field.employment__position", "field.employment__status", "field.employment__contract__start_date", "field.employment__contract__end_date", "field.employment__manager_employee_id", "history.attachments", "history.changed_at", "table.actions"]
        header_html = "".join(f"<th>{h(t(messages, key))}</th>" for key in headers)
        table_body = "".join(rows) if rows else f'<tr><td colspan="{len(headers)}" class="empty">{h(t(messages, "history.empty"))}</td></tr>'
        return f"""
<section class="form-section detail-section history-section">
  <div class="section-header"><h3>{h(t(messages, str(config['title_key'])))}</h3><div class="detail-section-actions">{add_html}</div></div>
  <div class="field-group">
    <p class="muted">{h(t(messages, 'history.note'))}</p>
    <div class="table-scroll">
      <table class="documents-table">
        <thead><tr>{header_html}</tr></thead>
        <tbody>{table_body}</tbody>
      </table>
    </div>
  </div>
</section>
"""

    def render_history_upload_block(self, messages: dict[str, str]) -> str:
        upload_type_document = {"document_type": "other"}
        upload_status_document = {"status": "on_file"}
        return f"""
<section class="card">
  <h3>{h(t(messages, 'history.upload_title'))}</h3>
  <p class="muted">{h(t(messages, 'documents.upload_limits_note'))}</p>
  <div class="form-grid">
    <div class="form-field"><label for="upload_files">{h(t(messages, 'documents.upload_files'))}</label><input id="upload_files" type="file" name="upload_files" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.txt"></div>
    <div class="form-field"><label for="upload_document_type">{h(field_label(messages, 'documents.document_type'))}</label>{self.render_named_document_select('upload_document_type', 'document_type', upload_type_document, DOCUMENT_TYPES, 'document_type', messages)}</div>
    <div class="form-field"><label for="upload_issuer">{h(field_label(messages, 'documents.issuer'))}</label><input id="upload_issuer" name="upload_issuer"></div>
    <div class="form-field"><label for="upload_document_date">{h(field_label(messages, 'documents.document_date'))}</label><input id="upload_document_date" type="date" name="upload_document_date"></div>
    <div class="form-field"><label for="upload_expiry_date">{h(field_label(messages, 'documents.expiry_date'))}</label><input id="upload_expiry_date" type="date" name="upload_expiry_date"></div>
    <div class="form-field"><label for="upload_received_date">{h(field_label(messages, 'documents.received_date'))}</label><input id="upload_received_date" type="date" name="upload_received_date"></div>
    <div class="form-field"><label for="upload_status">{h(field_label(messages, 'documents.status'))}</label>{self.render_named_document_select('upload_status', 'status', upload_status_document, DOCUMENT_STATUSES, 'document_status', messages)}</div>
  </div>
  <div class="form-field"><label for="upload_notes">{h(field_label(messages, 'documents.notes'))}</label><textarea id="upload_notes" name="upload_notes"></textarea></div>
</section>
"""

    def render_history_fields(self, messages: dict[str, str], history_type: str, record: dict[str, Any]) -> str:
        config = HISTORY_CONFIG[history_type]
        event_options = "".join(f'<option value="{h(value)}"{selected(str(record.get("event_type", "")), value)}>{h(self.history_label(messages, "history_event", value))}</option>' for value in config["event_types"])
        common = f"""
<div class="form-grid">
  <div class="form-field"><label for="event_type">{h(t(messages, 'history.event_type'))}</label><select id="event_type" name="event_type">{event_options}</select></div>
  <div class="form-field"><label for="effective_date">{h(t(messages, 'history.effective_date'))}</label><input id="effective_date" type="date" name="effective_date" value="{h(record.get('effective_date'))}"></div>
</div>
"""
        if history_type == "visa":
            body = f"""
<div class="form-grid">
  <div class="form-field"><label for="visa_type">{h(field_label(messages, 'visa.visa_type'))}</label><input id="visa_type" name="visa_type" value="{h(record.get('visa_type'))}"></div>
  <div class="form-field"><label for="residence_status">{h(field_label(messages, 'visa.residence_status'))}</label><input id="residence_status" name="residence_status" value="{h(record.get('residence_status'))}"></div>
  <div class="form-field"><label for="expiry_date">{h(field_label(messages, 'visa.expiry_date'))}</label><input id="expiry_date" type="date" name="expiry_date" value="{h(record.get('expiry_date'))}"></div>
  <div class="form-field"><label for="residence_card_number">{h(field_label(messages, 'visa.residence_card_number'))}</label><input id="residence_card_number" name="residence_card_number" value="{h(record.get('residence_card_number'))}"></div>
  <div class="form-field"><label for="passport_number">{h(field_label(messages, 'visa.passport_number'))}</label><input id="passport_number" name="passport_number" value="{h(record.get('passport_number'))}"></div>
  <div class="form-field"><label for="passport_expiry_date">{h(field_label(messages, 'visa.passport_expiry_date'))}</label><input id="passport_expiry_date" type="date" name="passport_expiry_date" value="{h(record.get('passport_expiry_date'))}"></div>
  <div class="checkbox-field"><input type="checkbox" id="renewal_reminder_enabled" name="renewal_reminder_enabled" value="1"{checked(record.get('renewal_reminder_enabled'))}><label for="renewal_reminder_enabled">{h(field_label(messages, 'visa.renewal_reminder_enabled'))}</label></div>
  <div class="form-field"><label for="renewal_reminder_date">{h(field_label(messages, 'visa.renewal_reminder_date'))}</label><input id="renewal_reminder_date" type="date" name="renewal_reminder_date" value="{h(record.get('renewal_reminder_date'))}"></div>
</div>
"""
        elif history_type == "dispatch":
            body = f"""
<div class="form-grid">
  <div class="form-field"><label for="client_name">{h(field_label(messages, 'dispatch_compliance.client_name'))}</label><input id="client_name" name="client_name" value="{h(record.get('client_name'))}"></div>
  <div class="form-field"><label for="assignment_location">{h(field_label(messages, 'dispatch_compliance.assignment_location'))}</label><input id="assignment_location" name="assignment_location" value="{h(record.get('assignment_location'))}"></div>
  <div class="form-field"><label for="dispatch_start_date">{h(field_label(messages, 'dispatch_compliance.dispatch_start_date'))}</label><input id="dispatch_start_date" type="date" name="dispatch_start_date" value="{h(record.get('dispatch_start_date'))}"></div>
  <div class="form-field"><label for="dispatch_end_date">{h(field_label(messages, 'dispatch_compliance.dispatch_end_date'))}</label><input id="dispatch_end_date" type="date" name="dispatch_end_date" value="{h(record.get('dispatch_end_date'))}"></div>
  <div class="form-field"><label for="contract_type">{h(field_label(messages, 'dispatch_compliance.contract_type'))}</label><select id="contract_type" name="contract_type">{''.join(f'<option value="{h(value)}"{selected(str(record.get("contract_type", "")), value)}>{h(t(messages, "filter.select") if value == "" else enum_label(messages, "dispatch_contract_type", value))}</option>' for value in DISPATCH_CONTRACT_TYPES)}</select></div>
  <div class="form-field"><label for="supervisor__name">{h(field_label(messages, 'dispatch_compliance.supervisor.name'))}</label><input id="supervisor__name" name="supervisor__name" value="{h(get_nested(record, 'supervisor.name'))}"></div>
  <div class="form-field"><label for="supervisor__title">{h(field_label(messages, 'dispatch_compliance.supervisor.title'))}</label><input id="supervisor__title" name="supervisor__title" value="{h(get_nested(record, 'supervisor.title'))}"></div>
  <div class="form-field"><label for="supervisor__phone">{h(field_label(messages, 'dispatch_compliance.supervisor.phone'))}</label><input id="supervisor__phone" name="supervisor__phone" value="{h(get_nested(record, 'supervisor.phone'))}"></div>
  <div class="form-field"><label for="supervisor__email">{h(field_label(messages, 'dispatch_compliance.supervisor.email'))}</label><input id="supervisor__email" name="supervisor__email" type="email" value="{h(get_nested(record, 'supervisor.email'))}"></div>
</div>
<div class="form-field"><label for="work_description">{h(field_label(messages, 'dispatch_compliance.work_description'))}</label><textarea id="work_description" name="work_description">{h(record.get('work_description'))}</textarea></div>
"""
        else:
            type_options = "".join(f'<option value="{h(value)}"{selected(str(record.get("employment_type", "")), value)}>{h(t(messages, "filter.select") if value == "" else enum_label(messages, "employment_type", value))}</option>' for value in EMPLOYMENT_TYPES)
            status_options = "".join(f'<option value="{h(value)}"{selected(str(record.get("status", "")), value)}>{h(enum_label(messages, "status", value))}</option>' for value in EMPLOYMENT_STATUSES)
            body = f"""
<div class="form-grid">
  <div class="form-field"><label for="join_date">{h(field_label(messages, 'employment.join_date'))}</label><input id="join_date" type="date" name="join_date" value="{h(record.get('join_date'))}"></div>
  <div class="form-field"><label for="employment_type">{h(field_label(messages, 'employment.employment_type'))}</label><select id="employment_type" name="employment_type">{type_options}</select></div>
  <div class="form-field"><label for="entity_id">{h(field_label(messages, 'employment.entity_id'))}</label><input id="entity_id" name="entity_id" value="{h(record.get('entity_id'))}"></div>
  <div class="form-field"><label for="department_id">{h(field_label(messages, 'employment.department_id'))}</label><input id="department_id" name="department_id" value="{h(record.get('department_id'))}"></div>
  <div class="form-field"><label for="team_id">{h(field_label(messages, 'employment.team_id'))}</label><input id="team_id" name="team_id" value="{h(record.get('team_id'))}"></div>
  <div class="form-field"><label for="position">{h(field_label(messages, 'employment.position'))}</label><input id="position" name="position" value="{h(record.get('position'))}"></div>
  <div class="form-field"><label for="manager_employee_id">{h(field_label(messages, 'employment.manager_employee_id'))}</label><input id="manager_employee_id" name="manager_employee_id" value="{h(record.get('manager_employee_id'))}"></div>
  <div class="form-field"><label for="office_location">{h(field_label(messages, 'employment.office_location'))}</label><input id="office_location" name="office_location" value="{h(record.get('office_location'))}"></div>
  <div class="form-field"><label for="assignment">{h(field_label(messages, 'employment.assignment'))}</label><input id="assignment" name="assignment" value="{h(record.get('assignment'))}"></div>
  <div class="form-field"><label for="status">{h(field_label(messages, 'employment.status'))}</label><select id="status" name="status">{status_options}</select></div>
  <div class="form-field"><label for="probation_end_date">{h(field_label(messages, 'employment.probation_end_date'))}</label><input id="probation_end_date" type="date" name="probation_end_date" value="{h(record.get('probation_end_date'))}"></div>
  <div class="form-field"><label for="contract__start_date">{h(field_label(messages, 'employment.contract.start_date'))}</label><input id="contract__start_date" type="date" name="contract__start_date" value="{h(get_nested(record, 'contract.start_date'))}"></div>
  <div class="form-field"><label for="contract__end_date">{h(field_label(messages, 'employment.contract.end_date'))}</label><input id="contract__end_date" type="date" name="contract__end_date" value="{h(get_nested(record, 'contract.end_date'))}"></div>
  <div class="form-field"><label for="resignation__resignation_date">{h(field_label(messages, 'employment.resignation.resignation_date'))}</label><input id="resignation__resignation_date" type="date" name="resignation__resignation_date" value="{h(get_nested(record, 'resignation.resignation_date'))}"></div>
  <div class="form-field"><label for="resignation__last_working_date">{h(field_label(messages, 'employment.resignation.last_working_date'))}</label><input id="resignation__last_working_date" type="date" name="resignation__last_working_date" value="{h(get_nested(record, 'resignation.last_working_date'))}"></div>
</div>
<div class="form-field"><label for="resignation__reason">{h(field_label(messages, 'employment.resignation.reason'))}</label><textarea id="resignation__reason" name="resignation__reason">{h(get_nested(record, 'resignation.reason'))}</textarea></div>
"""
        attachments = normalize_history_attachments(record.get("attachments", []))
        attachment_rows = []
        for index, attachment in enumerate(attachments):
            attachment_rows.append(f"""
<tr>
  <td>{h(attachment.get('attachment_id'))}<input type="hidden" name="attachments__{index}__attachment_id" value="{h(attachment.get('attachment_id'))}"></td>
  <td>{h(attachment.get('title'))}<input type="hidden" name="attachments__{index}__title" value="{h(attachment.get('title'))}"></td>
  <td>{h(attachment.get('original_filename'))}<input type="hidden" name="attachments__{index}__original_filename" value="{h(attachment.get('original_filename'))}"></td>
  <td>{h(attachment.get('stored_filename'))}<input type="hidden" name="attachments__{index}__stored_filename" value="{h(attachment.get('stored_filename'))}"></td>
  <td><input type="checkbox" name="attachments__{index}__delete" value="1"></td>
  {''.join(f'<input type="hidden" name="attachments__{index}__{field}" value="{h(attachment.get(field))}">' for field in HISTORY_ATTACHMENT_FIELD_NAMES if field not in {'attachment_id', 'title', 'original_filename', 'stored_filename'})}
</tr>
""")
        attachment_table = "" if not attachment_rows else f"""
<section class="card">
  <h3>{h(t(messages, 'history.existing_attachments'))}</h3>
  <table><thead><tr><th>{h(t(messages, 'history.attachment_id'))}</th><th>{h(field_label(messages, 'documents.title'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(field_label(messages, 'documents.stored_filename'))}</th><th>{h(field_label(messages, 'documents.delete'))}</th></tr></thead><tbody>{''.join(attachment_rows)}</tbody></table>
</section>
"""
        return common + body + f'<div class="form-field"><label for="notes">{h(t(messages, "history.notes"))}</label><textarea id="notes" name="notes">{h(record.get("notes"))}</textarea></div>' + attachment_table + self.render_history_upload_block(messages)

    def send_history_form(self, lang: str, messages: dict[str, str], employee_id: str, history_type: str, history_id: str | None, errors: list[str]) -> None:
        employee = find_employee(load_employees(), employee_id)
        config = HISTORY_CONFIG.get(history_type)
        if not employee or not config or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        record = find_history_record(employee, history_type, history_id) if history_id else None
        if history_id and not record:
            self.send_not_found(lang, messages)
            return
        record = record or default_history_record(history_type)
        action_path = f"/employees/{quote(employee_id)}/history/{quote(history_type)}/{quote(history_id)}/edit" if history_id else f"/employees/{quote(employee_id)}/history/{quote(history_type)}/new"
        body = f"""
<section class="card">
  <h2>{h(t(messages, str(config['title_key'])))}: {h(get_employee_number(employee))}</h2>
  {self.render_errors(messages, errors)}
  <form method="post" action="{h(url_with_lang(action_path, lang))}" enctype="multipart/form-data">
    {self.render_history_fields(messages, history_type, record)}
    <div class="actions">
      <button type="submit">{h(t(messages, 'action.save'))}</button>
      <a class="button light" href="{h(url_with_lang(f'/employees/{quote(employee_id)}', lang))}">{h(t(messages, 'action.cancel'))}</a>
    </div>
  </form>
</section>
"""
        self.send_html(200, t(messages, str(config["title_key"])), body, lang, messages)

    def save_history_record(self, lang: str, messages: dict[str, str], employee_id: str, history_type: str, history_id: str | None, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form, uploads, request_errors = self.parse_request_body(messages)
        employees = load_employees()
        employee = find_employee(employees, employee_id)
        config = HISTORY_CONFIG.get(history_type)
        if not employee or not config or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        array_key = str(config["array_key"])
        records = normalize_history_records(history_type, get_nested(employee, array_key, []))
        existing_record = None
        if history_id:
            existing_record = next((record for record in records if record.get("history_id") == history_id), None)
            if not existing_record:
                self.send_not_found(lang, messages)
                return
        before = copy.deepcopy(employee)
        upload_errors = request_errors + validate_upload_parts(uploads, messages)
        record, file_writes = history_record_from_form(history_type, form, employee, existing_record, [] if upload_errors else uploads, actor)
        errors = upload_errors + validate_history_record(record, history_type, messages)
        if errors:
            self.send_history_form(lang, messages, employee_id, history_type, history_id, errors)
            return
        if history_id:
            records = [record if item.get("history_id") == history_id else item for item in records]
            audit_action = str(config["audit_updated"])
            summary = f"Updated {array_key} record {history_id} for {employee_id}"
        else:
            records.append(record)
            audit_action = str(config["audit_created"])
            summary = f"Created {array_key} record {record.get('history_id')} for {employee_id}"
        set_nested(employee, array_key, records)
        employee.setdefault("metadata", {})
        employee["metadata"]["updated_at"] = now_iso()
        employee["metadata"]["updated_by"] = actor
        try:
            if file_writes:
                write_uploaded_files(file_writes)
        except Exception:
            self.send_history_form(lang, messages, employee_id, history_type, history_id, [t(messages, "validation.upload_save_failed")])
            return
        for index, existing_employee in enumerate(employees):
            if existing_employee.get("employee_id") == employee_id:
                employees[index] = normalize_employee(employee)
                break
        save_employees(employees)
        append_audit_log(employee_id, audit_action, array_key, [array_key], summary, before, employee, actor)
        action_text = "updated" if history_id else "created"
        notice = operation_notice(messages, "Employee history", record.get("history_id", ""), action_text, actor)
        self.redirect(url_with_lang(f"/employees/{quote(employee_id)}", lang), notice)

    def handle_create_history_record(self, lang: str, messages: dict[str, str], employee_id: str, history_type: str, user: dict[str, Any]) -> None:
        self.save_history_record(lang, messages, employee_id, history_type, None, user)

    def handle_update_history_record(self, lang: str, messages: dict[str, str], employee_id: str, history_type: str, history_id: str, user: dict[str, Any]) -> None:
        self.save_history_record(lang, messages, employee_id, history_type, history_id, user)

    def send_employee_history_attachment_file(self, lang: str, messages: dict[str, str], employee_id: str, history_type: str, history_id: str, attachment_id: str, mode: str) -> None:
        employee = find_employee(load_employees(), employee_id)
        if not employee or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        attachment = find_history_attachment(employee, history_type, history_id, attachment_id)
        if not attachment:
            self.send_not_found(lang, messages)
            return
        path = document_file_path(attachment)
        if not path or not path.is_file():
            self.send_not_found(lang, messages)
            return
        filename = attachment.get("original_filename") or attachment.get("stored_filename") or path.name
        disposition = content_disposition("attachment" if mode == "download" else "inline", filename)
        self.send_document_bytes(200, document_content_type(attachment, path), path.read_bytes(), disposition)

    def render_required_document_matrix_html(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        rows = []
        for item in document_requirement_matrix(employee):
            status_key = "documents.requirement_complete" if item["is_complete"] else "documents.requirement_missing"
            rows.append(f"""
<tr>
  <td>{h(enum_label(messages, 'document_type', str(item['document_type'])))}</td>
  <td>{h(t(messages, status_key))}</td>
  <td>{h(str(item['matched_count']))}</td>
  <td>{h(item['latest_expiry_date'] or '-')}</td>
</tr>
""")
        table_body = "".join(rows) if rows else f'<tr><td colspan="4" class="empty">{h(t(messages, "reports.empty"))}</td></tr>'
        return f"""
<div class="field-group">
  <h4 class="field-group-title">{h(t(messages, 'documents.required_matrix.title'))}</h4>
  <p class="muted">{h(t(messages, 'documents.required_matrix.description'))}</p>
  <div class="table-scroll">
    <table class="documents-table">
      <thead><tr><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(t(messages, 'documents.requirement_status'))}</th><th>{h(t(messages, 'documents.matched_count'))}</th><th>{h(field_label(messages, 'documents.expiry_date'))}</th></tr></thead>
      <tbody>{table_body}</tbody>
    </table>
  </div>
</div>
"""

    def render_documents_section(
        self,
        messages: dict[str, str],
        employee: dict[str, Any],
        edit_url: str | None,
        edit_label: str | None,
        can_manage_documents: bool,
        lang: str,
    ) -> str:
        employee_id = str(employee.get("employee_id", ""))
        rows = []
        for document in normalize_documents(get_nested(employee, "documents", [])):
            document_id = str(document.get("document_id", ""))
            has_file = bool(document.get("stored_filename") or document.get("storage_reference"))
            if can_manage_documents and document_id and has_file:
                base_url = f"/employees/{quote(employee_id)}/documents/{quote(document_id)}"
                actions_html = (
                    f'<a href="{h(url_with_lang(base_url + "/open", lang))}" target="_blank" rel="noopener">{h(t(messages, "action.open"))}</a>'
                    " | "
                    f'<a href="{h(url_with_lang(base_url + "/download", lang))}">{h(t(messages, "action.download"))}</a>'
                )
            elif not has_file:
                actions_html = h(t(messages, "documents.no_file"))
            else:
                actions_html = "-"
            rows.append(
                f"""
<tr>
  <td>{h(document_id)}</td>
  <td>{h(enum_label(messages, 'document_type', document.get('document_type', '')))}</td>
  <td>{h(document.get('title'))}</td>
  <td>{h(enum_label(messages, 'document_status', document.get('status', '')))}</td>
  <td>{h(document.get('expiry_date'))}</td>
  <td>{h(document.get('original_filename'))}</td>
  <td>{h(document.get('stored_filename'))}</td>
  <td>{h(document.get('file_size_bytes'))}</td>
  <td>{h(document.get('uploaded_at'))}</td>
  <td>{h(document.get('storage_reference'))}</td>
  <td>{actions_html}</td>
</tr>
"""
            )
        table_body = "".join(rows) if rows else f'<tr><td colspan="11" class="empty">{h(t(messages, "documents.empty"))}</td></tr>'
        edit_html = f'<a class="button secondary" href="{h(edit_url)}">{h(edit_label)}</a>' if edit_url and edit_label else ""
        return f"""
<section class="form-section detail-section documents-section">
  <div class="section-header"><h3>{h(t(messages, 'section.documents'))}</h3><div class="detail-section-actions">{edit_html}</div></div>
  {self.render_required_document_matrix_html(messages, employee)}
  <div class="field-group">
    <p class="muted">{h(t(messages, 'documents.local_upload_note'))}</p>
    <p class="muted">{h(t(messages, 'documents.file_access_note'))}</p>
    <div class="table-scroll">
      <table class="documents-table">
        <thead><tr><th>{h(field_label(messages, 'documents.document_id'))}</th><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(field_label(messages, 'documents.title'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(field_label(messages, 'documents.expiry_date'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(field_label(messages, 'documents.stored_filename'))}</th><th>{h(field_label(messages, 'documents.file_size_bytes'))}</th><th>{h(field_label(messages, 'documents.uploaded_at'))}</th><th>{h(field_label(messages, 'documents.storage_reference'))}</th><th>{h(t(messages, 'documents.actions'))}</th></tr></thead>
        <tbody>{table_body}</tbody>
      </table>
    </div>
  </div>
</section>
"""

    def send_edit_employee(self, lang: str, messages: dict[str, str], employee_id: str) -> None:
        employee = find_employee(load_employees(), employee_id)
        if not employee or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        self.send_employee_form(lang, messages, employee, [], "edit")

    def render_form_header(self, messages: dict[str, str], title_key: str, description_key: str, employee_number: str = "") -> str:
        meta = f'<span class="badge">{h(field_label(messages, "employee_number"))}: {h(employee_number)}</span>' if employee_number else f'<span class="badge">{h(t(messages, "employee.form.new_employee"))}</span>'
        return f"""
<div class="object-header">
  <div>
    <p class="eyebrow">{h(t(messages, 'employee.form.kicker'))}</p>
    <h2>{h(t(messages, title_key))}</h2>
    <p class="muted">{h(t(messages, description_key))}</p>
  </div>
  <div class="object-meta">{meta}</div>
</div>
"""

    def render_form_section(self, messages: dict[str, str], title_key: str, body_html: str) -> str:
        return f"""
<section class="form-section">
  <div class="section-header"><h3>{h(t(messages, title_key))}</h3></div>
  {body_html}
</section>
"""

    def render_field_group(self, messages: dict[str, str], title_key: str, fields_html: str, compact: bool = False) -> str:
        compact_class = " compact" if compact else ""
        return f"""
<div class="field-group">
  <h4 class="field-group-title">{h(t(messages, title_key))}</h4>
  <div class="form-grid{compact_class}">{fields_html}</div>
</div>
"""

    def render_form_actions(self, messages: dict[str, str], cancel_url: str, detail_url: str | None = None) -> str:
        detail_button = (
            f'<a class="button secondary" href="{h(detail_url)}">{h(t(messages, "action.detail_inquiry"))}</a>'
            if detail_url
            else ""
        )
        return f"""
<div class="form-actions">
  <button type="submit">{h(t(messages, 'action.save'))}</button>
  {detail_button}
  <a class="button light" href="{h(cancel_url)}">{h(t(messages, 'action.cancel'))}</a>
</div>
"""

    def send_employee_form(self, lang: str, messages: dict[str, str], employee: dict[str, Any], errors: list[str], mode: str, field_errors: dict[str, list[str]] | None = None) -> None:
        is_edit = mode == "edit"
        field_errors = field_errors or {}
        employee_id = str(employee.get("employee_id", ""))
        action = url_with_lang(f"/employees/{quote(employee_id)}/edit" if is_edit else "/employees/new", lang)
        title_key = "employee.edit.title" if is_edit else "employee.create.title"
        description_key = "employee.form.edit_description" if is_edit else "employee.form.create_description"
        cancel_url = url_with_lang(f"/employees/{quote(employee_id)}" if is_edit else "/employees", lang)
        detail_url = url_with_lang(f"/employees/{quote(employee_id)}", lang) if is_edit and employee_id else None
        profile_name = self.render_field_group(
            messages,
            "form.group.name",
            f"""
            {self.render_input(messages, employee, 'employee_number', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'profile.name.display_name', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'profile.name.family_name')}
            {self.render_input(messages, employee, 'profile.name.given_name')}
            {self.render_input(messages, employee, 'profile.name.family_name_kana')}
            {self.render_input(messages, employee, 'profile.name.given_name_kana')}
            {self.render_input(messages, employee, 'profile.name.romaji_name')}
            """,
        )
        profile_personal = self.render_field_group(
            messages,
            "form.group.personal",
            f"""
            {self.render_select(messages, employee, 'profile.gender', GENDERS, 'gender')}
            {self.render_input(messages, employee, 'profile.date_of_birth', input_type='date')}
            {self.render_input(messages, employee, 'profile.nationality')}
            """,
            compact=True,
        )
        profile_contact = self.render_field_group(
            messages,
            "form.group.contact",
            f"""
            {self.render_input(messages, employee, 'profile.email', input_type='email', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'profile.email_p', input_type='email', field_errors=field_errors)}
            {self.render_input(messages, employee, 'profile.phone')}
            """,
            compact=True,
        )
        profile_address = self.render_field_group(
            messages,
            "form.group.address",
            f"""
            {self.render_input(messages, employee, 'profile.address.postal_code')}
            {self.render_input(messages, employee, 'profile.address.prefecture')}
            {self.render_input(messages, employee, 'profile.address.city')}
            {self.render_input(messages, employee, 'profile.address.street')}
            {self.render_input(messages, employee, 'profile.address.building')}
            """,
        )
        profile_emergency = self.render_field_group(
            messages,
            "form.group.emergency_contact",
            f"""
            {self.render_input(messages, employee, 'profile.emergency_contact.name')}
            {self.render_input(messages, employee, 'profile.emergency_contact.relationship')}
            {self.render_input(messages, employee, 'profile.emergency_contact.phone')}
            {self.render_input(messages, employee, 'profile.emergency_contact.email', input_type='email')}
            """,
        )
        employment_basics = self.render_field_group(
            messages,
            "form.group.employment_basics",
            f"""
            {self.render_employee_masterdata_fields(lang, messages, employee, field_errors)}
            {self.render_select(messages, employee, 'employment.country_code', [""] + COUNTRY_CODES, 'country', required=True, field_errors=field_errors)}
            {self.render_select(messages, employee, 'employment.work_country', [""] + COUNTRY_CODES, 'country', required=True, field_errors=field_errors)}
            {self.render_select(messages, employee, 'employment.business_line', [""] + BUSINESS_LINES, 'business_line', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'employment.join_date', input_type='date', required=True, field_errors=field_errors)}
            {self.render_select(messages, employee, 'employment.employment_type', EMPLOYMENT_TYPES, 'employment_type', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'employment.position')}
            {self.render_input(messages, employee, 'employment.manager_employee_id', field_errors=field_errors)}
            """,
        )
        employment_labor_contract = self.render_field_group(
            messages,
            "form.group.labor_contract",
            f"""
            {self.render_input(messages, employee, 'employment.contract.start_date', input_type='date', field_errors=field_errors)}
            {self.render_input(messages, employee, 'employment.contract.end_date', input_type='date', field_errors=field_errors)}
            <p class="muted long">{h(t(messages, 'employment.labor_contract_note'))}</p>
            """,
        )
        employment_assignment = self.render_field_group(
            messages,
            "form.group.assignment",
            f"""
            {self.render_input(messages, employee, 'employment.office_location')}
            {self.render_input(messages, employee, 'employment.assignment')}
            {self.render_select(messages, employee, 'employment.status', EMPLOYMENT_STATUSES, 'status', required=True, field_errors=field_errors)}
            {self.render_select(messages, employee, 'metadata.profile_status', PROFILE_STATUSES, 'profile_status', required=True, field_errors=field_errors)}
            {self.render_input(messages, employee, 'employment.probation_end_date', input_type='date', field_errors=field_errors)}
            """,
        )
        employment_resignation = self.render_field_group(
            messages,
            "form.group.resignation",
            f"""
            {self.render_input(messages, employee, 'employment.resignation.resignation_date', input_type='date')}
            {self.render_input(messages, employee, 'employment.resignation.last_working_date', input_type='date')}
            {self.render_textarea(messages, employee, 'employment.resignation.reason')}
            """,
        )
        bank_info = self.render_field_group(
            messages,
            "form.group.payroll_bank",
            f"""
            {self.render_input(messages, employee, 'payroll.bank.bank_name')}
            {self.render_input(messages, employee, 'payroll.bank.branch_name')}
            {self.render_input(messages, employee, 'payroll.bank.swift_code')}
            {self.render_select(messages, employee, 'payroll.bank.account_type', BANK_ACCOUNT_TYPES, 'bank_account_type')}
            {self.render_input(messages, employee, 'payroll.bank.account_number')}
            {self.render_input(messages, employee, 'payroll.bank.account_holder')}
            """,
        )
        body = f"""
<section class="object-page">
  {self.render_form_header(messages, title_key, description_key, get_employee_number(employee) if is_edit else "")}
  <form class="employee-form" method="post" action="{h(action)}">
    {self.render_errors(messages, errors)}
    <p class="required-note">{h(t(messages, 'employee.form.required_note'))}</p>
    {self.render_form_section(messages, 'section.profile', profile_name + profile_personal + profile_contact + profile_address + profile_emergency)}
    {self.render_form_section(messages, 'section.employment', employment_basics + employment_labor_contract + employment_assignment + employment_resignation)}
    {self.render_form_section(messages, 'section.bank', bank_info)}
    {self.render_form_actions(messages, cancel_url, detail_url)}
  </form>
</section>
"""
        self.send_html(200, t(messages, title_key), body, lang, messages)

    def send_section_form(self, lang: str, messages: dict[str, str], employee_id: str, section_key: str, errors: list[str]) -> None:
        employee = find_employee(load_employees(), employee_id)
        if not employee or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        self.send_section_form_with_employee(lang, messages, employee, section_key, errors)

    def render_section_fields(self, messages: dict[str, str], employee: dict[str, Any], section_key: str) -> str:
        if section_key == "payroll":
            bank = self.render_field_group(messages, "form.group.payroll_bank", f"""
            {self.render_input(messages, employee, 'payroll.bank.bank_name')}
            {self.render_input(messages, employee, 'payroll.bank.branch_name')}
            {self.render_input(messages, employee, 'payroll.bank.swift_code')}
            {self.render_select(messages, employee, 'payroll.bank.account_type', BANK_ACCOUNT_TYPES, 'bank_account_type')}
            {self.render_input(messages, employee, 'payroll.bank.account_number')}
            {self.render_input(messages, employee, 'payroll.bank.account_holder')}
            """)
            compensation = self.render_field_group(messages, "form.group.payroll_compensation", f"""
            {self.render_select(messages, employee, 'payroll.salary_type', SALARY_TYPES, 'salary_type')}
            {self.render_select(messages, employee, 'payroll.payroll_currency', SUPPORTED_CURRENCIES, 'currency')}
            {self.render_input(messages, employee, 'payroll.monthly_base_salary', input_type='number')}
            {self.render_input(messages, employee, 'payroll.daily_wage', input_type='number')}
            {self.render_input(messages, employee, 'payroll.hourly_wage', input_type='number')}
            {self.render_input(messages, employee, 'payroll.salary_amount_yen', input_type='number')}
            {self.render_input(messages, employee, 'payroll.transportation_allowance_yen', input_type='number')}
            {self.render_checkbox(messages, employee, 'payroll.bonus_eligible')}
            """, compact=True)
            insurance = self.render_field_group(messages, "form.group.payroll_insurance", f"""
            {self.render_checkbox(messages, employee, 'payroll.social_insurance_enrolled')}
            {self.render_checkbox(messages, employee, 'payroll.pension_enrolled')}
            {self.render_checkbox(messages, employee, 'payroll.employment_insurance_enrolled')}
            """, compact=True)
            notes = self.render_field_group(messages, "detail.group.notes", self.render_textarea(messages, employee, 'payroll.notes'))
            return bank + compensation + insurance + notes
        if section_key == "visa":
            residence = self.render_field_group(messages, "form.group.visa_residence", f"""
            {self.render_input(messages, employee, 'visa.visa_type')}
            {self.render_input(messages, employee, 'visa.residence_status')}
            {self.render_input(messages, employee, 'visa.expiry_date', input_type='date')}
            {self.render_input(messages, employee, 'visa.residence_card_number')}
            """)
            passport = self.render_field_group(messages, "form.group.visa_passport", f"""
            {self.render_input(messages, employee, 'visa.passport_number')}
            {self.render_input(messages, employee, 'visa.passport_expiry_date', input_type='date')}
            """, compact=True)
            renewal = self.render_field_group(messages, "form.group.visa_renewal", f"""
            {self.render_checkbox(messages, employee, 'visa.renewal_reminder_enabled')}
            {self.render_input(messages, employee, 'visa.renewal_reminder_date', input_type='date')}
            """, compact=True)
            notes = self.render_field_group(messages, "detail.group.notes", self.render_textarea(messages, employee, 'visa.notes'))
            return residence + passport + renewal + notes
        if section_key == "skills":
            language = self.render_field_group(messages, "section.language_profile", f"""
            {self.render_select(messages, employee, 'language_profile.japanese_level', JAPANESE_LEVELS, 'japanese_level')}
            {self.render_select(messages, employee, 'language_profile.english_level', ENGLISH_LEVELS, 'english_level')}
            {self.render_tag_input(messages, employee, 'language_profile.native_languages')}
            {self.render_tag_input(messages, employee, 'language_profile.additional_languages')}
            {self.render_textarea(messages, employee, 'language_profile.notes')}
            """)
            skills = self.render_field_group(messages, "section.skills_profile", f"""
            {self.render_input(messages, employee, 'skills_profile.primary_skill')}
            {self.render_input(messages, employee, 'skills_profile.secondary_skill')}
            {self.render_input(messages, employee, 'skills_profile.years_of_experience', input_type='number')}
            {self.render_tag_input(messages, employee, 'skills_profile.it_skills')}
            {self.render_tag_input(messages, employee, 'skills_profile.engineering_skills')}
            {self.render_tag_input(messages, employee, 'skills_profile.certifications')}
            {self.render_tag_input(messages, employee, 'skills_profile.industry_experience')}
            {self.render_textarea(messages, employee, 'skills_profile.notes')}
            """)
            return language + skills
        if section_key == "documents":
            return self.render_documents_form(messages, employee)
        assignment = self.render_field_group(messages, "form.group.dispatch_assignment", f"""
        {self.render_input(messages, employee, 'dispatch_compliance.client_name')}
        {self.render_input(messages, employee, 'dispatch_compliance.assignment_location')}
        {self.render_input(messages, employee, 'dispatch_compliance.dispatch_start_date', input_type='date')}
        {self.render_input(messages, employee, 'dispatch_compliance.dispatch_end_date', input_type='date')}
        {self.render_select(messages, employee, 'dispatch_compliance.contract_type', DISPATCH_CONTRACT_TYPES, 'dispatch_contract_type')}
        """)
        supervisor = self.render_field_group(messages, "form.group.dispatch_supervisor", f"""
        {self.render_input(messages, employee, 'dispatch_compliance.supervisor.name')}
        {self.render_input(messages, employee, 'dispatch_compliance.supervisor.title')}
        {self.render_input(messages, employee, 'dispatch_compliance.supervisor.phone')}
        {self.render_input(messages, employee, 'dispatch_compliance.supervisor.email', input_type='email')}
        """)
        notes = self.render_field_group(messages, "detail.group.notes", f"""
        {self.render_textarea(messages, employee, 'dispatch_compliance.work_description')}
        {self.render_textarea(messages, employee, 'dispatch_compliance.notes')}
        """)
        return assignment + supervisor + notes

    def render_documents_form(self, messages: dict[str, str], employee: dict[str, Any]) -> str:
        documents = normalize_documents(get_nested(employee, "documents", [])) + [default_document()]
        rows = []
        for index, document in enumerate(documents):
            is_existing = bool(document.get("document_id"))
            delete_html = f'<input type="checkbox" name="documents__{index}__delete" value="1">' if is_existing else ""
            rows.append(
                f"""
<tr>
  <td><input type="hidden" name="documents__{index}__document_id" value="{h(document.get('document_id'))}">{h(document.get('document_id'))}</td>
  <td>{self.render_document_select(index, 'document_type', document, DOCUMENT_TYPES, 'document_type', messages)}</td>
  <td><input name="documents__{index}__title" value="{h(document.get('title'))}"></td>
  <td><input name="documents__{index}__issuer" value="{h(document.get('issuer'))}"></td>
  <td><input type="date" name="documents__{index}__document_date" value="{h(document.get('document_date'))}"></td>
  <td><input type="date" name="documents__{index}__expiry_date" value="{h(document.get('expiry_date'))}"></td>
  <td><input type="date" name="documents__{index}__received_date" value="{h(document.get('received_date'))}"></td>
  <td>{self.render_document_select(index, 'status', document, DOCUMENT_STATUSES, 'document_status', messages)}</td>
  <td><input name="documents__{index}__storage_reference" value="{h(document.get('storage_reference'))}"></td>
  <td>{h(document.get('original_filename'))}<input type="hidden" name="documents__{index}__original_filename" value="{h(document.get('original_filename'))}"></td>
  <td>{h(document.get('stored_filename'))}<input type="hidden" name="documents__{index}__stored_filename" value="{h(document.get('stored_filename'))}"></td>
  <td><textarea name="documents__{index}__notes">{h(document.get('notes'))}</textarea></td>
  <td>{delete_html}</td>
  <input type="hidden" name="documents__{index}__content_type" value="{h(document.get('content_type'))}">
  <input type="hidden" name="documents__{index}__file_size_bytes" value="{h(document.get('file_size_bytes'))}">
  <input type="hidden" name="documents__{index}__uploaded_at" value="{h(document.get('uploaded_at'))}">
  <input type="hidden" name="documents__{index}__uploaded_by" value="{h(document.get('uploaded_by'))}">
</tr>
"""
            )
        upload_type_document = {"document_type": "other"}
        upload_status_document = {"status": "on_file"}
        upload_group = self.render_field_group(messages, "form.group.documents_upload", f"""
        <p class="muted">{h(t(messages, 'documents.local_upload_note'))}</p>
        <p class="muted">{h(t(messages, 'documents.upload_note'))}</p>
        <p class="muted">{h(t(messages, 'documents.upload_limits_note'))}</p>
        <div class="form-field"><label for="upload_files">{h(t(messages, 'documents.upload_files'))}</label><input id="upload_files" type="file" name="upload_files" multiple accept=".pdf,.jpg,.jpeg,.png,.doc,.docx,.xls,.xlsx,.txt"></div>
        <div class="form-field"><label for="upload_document_type">{h(field_label(messages, 'documents.document_type'))}</label>{self.render_named_document_select('upload_document_type', 'document_type', upload_type_document, DOCUMENT_TYPES, 'document_type', messages)}</div>
        <div class="form-field"><label for="upload_issuer">{h(field_label(messages, 'documents.issuer'))}</label><input id="upload_issuer" name="upload_issuer"></div>
        <div class="form-field"><label for="upload_document_date">{h(field_label(messages, 'documents.document_date'))}</label><input id="upload_document_date" type="date" name="upload_document_date"></div>
        <div class="form-field"><label for="upload_expiry_date">{h(field_label(messages, 'documents.expiry_date'))}</label><input id="upload_expiry_date" type="date" name="upload_expiry_date"></div>
        <div class="form-field"><label for="upload_received_date">{h(field_label(messages, 'documents.received_date'))}</label><input id="upload_received_date" type="date" name="upload_received_date"></div>
        <div class="form-field"><label for="upload_status">{h(field_label(messages, 'documents.status'))}</label>{self.render_named_document_select('upload_status', 'status', upload_status_document, DOCUMENT_STATUSES, 'document_status', messages)}</div>
        <div class="form-field"><label for="upload_notes">{h(field_label(messages, 'documents.notes'))}</label><textarea id="upload_notes" name="upload_notes"></textarea></div>
        """)
        register_table = f"""
        <p class="muted">{h(t(messages, 'documents.add_row_note'))}</p>
        <div class="table-scroll">
          <table class="documents-table">
            <thead><tr><th>{h(field_label(messages, 'documents.document_id'))}</th><th>{h(field_label(messages, 'documents.document_type'))}</th><th>{h(field_label(messages, 'documents.title'))}</th><th>{h(field_label(messages, 'documents.issuer'))}</th><th>{h(field_label(messages, 'documents.document_date'))}</th><th>{h(field_label(messages, 'documents.expiry_date'))}</th><th>{h(field_label(messages, 'documents.received_date'))}</th><th>{h(field_label(messages, 'documents.status'))}</th><th>{h(field_label(messages, 'documents.storage_reference'))}</th><th>{h(field_label(messages, 'documents.original_filename'))}</th><th>{h(field_label(messages, 'documents.stored_filename'))}</th><th>{h(field_label(messages, 'documents.notes'))}</th><th>{h(field_label(messages, 'documents.delete'))}</th></tr></thead>
            <tbody>{''.join(rows)}</tbody>
          </table>
        </div>
        """
        return self.render_form_section(messages, 'documents.required_matrix.title', self.render_required_document_matrix_html(messages, employee)) + self.render_form_section(messages, 'documents.upload_title', upload_group) + self.render_form_section(messages, 'form.group.documents_register', register_table)

    def render_document_select(self, index: int, field: str, document: dict[str, str], values: list[str], label_prefix: str, messages: dict[str, str]) -> str:
        current = document.get(field, "")
        options = []
        for value in values:
            label = t(messages, "filter.select") if value == "" else enum_label(messages, label_prefix, value)
            options.append(f"<option value=\"{h(value)}\"{selected(current, value)}>{h(label)}</option>")
        return f"<select name=\"documents__{index}__{field}\">{''.join(options)}</select>"


    def render_named_document_select(self, name: str, field: str, document: dict[str, str], values: list[str], label_prefix: str, messages: dict[str, str]) -> str:
        current = document.get(field, "")
        options = []
        for value in values:
            label = t(messages, "filter.select") if value == "" else enum_label(messages, label_prefix, value)
            options.append(f"<option value=\"{h(value)}\"{selected(current, value)}>{h(label)}</option>")
        return f"<select id=\"{h(name)}\" name=\"{h(name)}\">{''.join(options)}</select>"

    def render_errors(self, messages: dict[str, str], errors: list[str]) -> str:
        if not errors:
            return ""
        error_items = "".join(f"<li>{h(error)}</li>" for error in errors)
        return f"<div class=\"errors\"><strong>{h(t(messages, 'validation.title'))}</strong><ul>{error_items}</ul></div>"

    def render_field_errors(self, path: str, field_errors: dict[str, list[str]] | None = None) -> str:
        messages = (field_errors or {}).get(path, [])
        if not messages:
            return ""
        return "".join(f'<p class="field-error">{h(message)}</p>' for message in messages)

    def render_input(self, messages: dict[str, str], employee: dict[str, Any], path: str, input_type: str = "text", required: bool = False, field_errors: dict[str, list[str]] | None = None) -> str:
        name = path.replace(".", "__")
        required_attr = ' required aria-required="true"' if required else ""
        required_marker = ' <span class="required-marker" aria-hidden="true">*</span>' if required else ""
        min_attr = ' min="0" step="1"' if path in MONEY_FIELD_PATHS else ""
        return f"""
<div class="form-field">
  <label for="{h(name)}">{h(field_label(messages, path))}{required_marker}</label>
  <input type="{h(input_type)}" id="{h(name)}" name="{h(name)}" value="{h(get_nested(employee, path))}"{required_attr}{min_attr}>
  {self.render_field_errors(path, field_errors)}
</div>
"""

    def render_select(self, messages: dict[str, str], employee: dict[str, Any], path: str, values: list[str], label_prefix: str, required: bool = False, field_errors: dict[str, list[str]] | None = None) -> str:
        name = path.replace(".", "__")
        current = str(get_nested(employee, path, ""))
        required_attr = ' required aria-required="true"' if required else ""
        required_marker = ' <span class="required-marker" aria-hidden="true">*</span>' if required else ""
        options = []
        for value in values:
            label = t(messages, "filter.select") if value == "" else enum_label(messages, label_prefix, value)
            options.append(f"<option value=\"{h(value)}\"{selected(current, value)}>{h(label)}</option>")
        return f"""
<div class="form-field">
  <label for="{h(name)}">{h(field_label(messages, path))}{required_marker}</label>
  <select id="{h(name)}" name="{h(name)}"{required_attr}>{''.join(options)}</select>
  {self.render_field_errors(path, field_errors)}
</div>
"""

    def render_options_select(self, messages: dict[str, str], employee: dict[str, Any], path: str, options: list[tuple[str, str]], required: bool = False, field_errors: dict[str, list[str]] | None = None, disabled: bool = False, data_attrs: str = "") -> str:
        name = path.replace(".", "__")
        current = str(get_nested(employee, path, ""))
        required_attr = ' required aria-required="true"' if required else ""
        disabled_attr = ' disabled aria-disabled="true"' if disabled else ""
        required_marker = ' <span class="required-marker" aria-hidden="true">*</span>' if required else ""
        option_html = [f'<option value="">{h(t(messages, "filter.select"))}</option>']
        for value, label in options:
            option_html.append(f'<option value="{h(value)}"{selected(current, value)}>{h(label)}</option>')
        return f"""
<div class="form-field">
  <label for="{h(name)}">{h(field_label(messages, path))}{required_marker}</label>
  <select id="{h(name)}" name="{h(name)}"{required_attr}{disabled_attr}{data_attrs}>{''.join(option_html)}</select>
  {self.render_field_errors(path, field_errors)}
</div>
"""

    def render_employee_masterdata_fields(self, lang: str, messages: dict[str, str], employee: dict[str, Any], field_errors: dict[str, list[str]] | None = None) -> str:
        session_id = self.current_session_id()
        entities, entity_error = fetch_masterdata_entities(session_id)
        entity_id = employment_entity_id(employee)
        department_id = employment_department_id(employee)
        departments: list[dict[str, Any]] = []
        teams: list[dict[str, Any]] = []
        masterdata_warning = ""
        if entity_error:
            masterdata_warning = f'<p class="muted">{h(t(messages, "validation.masterdata_unavailable"))}</p>'
        if entity_id and not entity_error:
            departments, department_error = fetch_masterdata_departments(session_id, entity_id)
            if department_error:
                masterdata_warning = f'<p class="muted">{h(t(messages, "validation.masterdata_unavailable"))}</p>'
        if department_id and not masterdata_warning:
            teams, team_error = fetch_masterdata_teams(session_id, department_id)
            if team_error:
                masterdata_warning = f'<p class="muted">{h(t(messages, "validation.masterdata_unavailable"))}</p>'
        entity_options = [(str(item.get("entity_id", "")), masterdata_label(item, "entity_name", "entity_code", lang)) for item in entities if item.get("entity_id")]
        department_options = [(str(item.get("department_id", "")), masterdata_label(item, "department_name", "department_code", lang)) for item in departments if item.get("department_id")]
        team_options = [(str(item.get("team_id", "")), masterdata_label(item, "team_name", "team_code", lang)) for item in teams if item.get("team_id")]
        return f"""
{masterdata_warning}
{self.render_options_select(messages, employee, 'employment.entity_id', entity_options, required=True, field_errors=field_errors, data_attrs=' data-org-level="entity"')}
{self.render_options_select(messages, employee, 'employment.department_id', department_options, required=True, field_errors=field_errors, disabled=not bool(entity_id), data_attrs=' data-org-level="department"')}
{self.render_options_select(messages, employee, 'employment.team_id', team_options, field_errors=field_errors, disabled=not bool(department_id), data_attrs=' data-org-level="team"')}
<p class="muted" data-org-masterdata-status aria-live="polite"></p>
<script>
(() => {{
  const entitySelect = document.getElementById('employment__entity_id');
  const departmentSelect = document.getElementById('employment__department_id');
  const teamSelect = document.getElementById('employment__team_id');
  const statusText = document.querySelector('[data-org-masterdata-status]');
  if (!entitySelect || !departmentSelect || !teamSelect) return;
  const formLang = {json.dumps(lang)};
  const blankLabel = {json.dumps(t(messages, "filter.select"))};
  const loadingLabel = `${{blankLabel}}...`;
  const loadErrorText = {json.dumps(t(messages, "validation.masterdata_unavailable"))};
  function setStatus(message = '') {{
    if (statusText) statusText.textContent = message;
  }}
  function setOptions(select, rows, idField, codeField, namePrefix, preferredValue = '', placeholder = blankLabel) {{
    const current = preferredValue || select.value;
    const items = Array.isArray(rows) ? rows : [];
    select.innerHTML = '';
    const blank = document.createElement('option');
    blank.value = '';
    blank.textContent = placeholder;
    select.appendChild(blank);
    let matched = false;
    for (const row of items) {{
      const value = row[idField] || '';
      const code = (row[codeField] || '').trim();
      const localized = (row[namePrefix + '_' + formLang] || '').trim();
      const english = (row[namePrefix + '_en'] || '').trim();
      const name = localized || english || code;
      const option = document.createElement('option');
      option.value = value;
      option.textContent = code && name && name !== code ? `${{code}} - ${{name}}` : (code || name || value);
      if (value === current) {{
        option.selected = true;
        matched = true;
      }}
      select.appendChild(option);
    }}
    if (!matched) select.value = '';
  }}
  function syncDisabledState() {{
    departmentSelect.disabled = !entitySelect.value;
    departmentSelect.setAttribute('aria-disabled', departmentSelect.disabled ? 'true' : 'false');
    teamSelect.disabled = !departmentSelect.value;
    teamSelect.setAttribute('aria-disabled', teamSelect.disabled ? 'true' : 'false');
  }}
  async function loadMasterdataRows(url) {{
    try {{
      const res = await fetch(url, {{ credentials: 'same-origin', headers: {{ 'Accept': 'application/json' }} }});
      const contentType = res.headers.get('content-type') || '';
      if (!res.ok || !contentType.includes('application/json')) throw new Error('masterdata_load_failed');
      setStatus('');
      const rows = await res.json();
      return Array.isArray(rows) ? rows : [];
    }} catch (error) {{
      setStatus(loadErrorText);
      return [];
    }}
  }}
  entitySelect.addEventListener('change', async () => {{
    setOptions(departmentSelect, [], 'department_id', 'department_code', 'department_name', '', entitySelect.value ? loadingLabel : blankLabel);
    setOptions(teamSelect, [], 'team_id', 'team_code', 'team_name', '');
    syncDisabledState();
    if (!entitySelect.value) {{
      setStatus('');
      return;
    }}
    const departments = await loadMasterdataRows(`/api/masterdata/departments?entity_id=${{encodeURIComponent(entitySelect.value)}}&lang={h(lang)}`);
    setOptions(departmentSelect, departments, 'department_id', 'department_code', 'department_name', '');
    syncDisabledState();
  }});
  departmentSelect.addEventListener('change', async () => {{
    setOptions(teamSelect, [], 'team_id', 'team_code', 'team_name', '', departmentSelect.value ? loadingLabel : blankLabel);
    syncDisabledState();
    if (!departmentSelect.value) {{
      setStatus('');
      return;
    }}
    const teams = await loadMasterdataRows(`/api/masterdata/teams?department_id=${{encodeURIComponent(departmentSelect.value)}}&lang={h(lang)}`);
    setOptions(teamSelect, teams, 'team_id', 'team_code', 'team_name', '');
    syncDisabledState();
  }});
  syncDisabledState();
}})();
</script>
"""

    def render_tag_input(self, messages: dict[str, str], employee: dict[str, Any], path: str) -> str:
        name = path.replace(".", "__")
        return f"""
<div class="form-field">
  <label for="{h(name)}">{h(field_label(messages, path))}</label>
  <input id="{h(name)}" name="{h(name)}" value="{h(join_tags(get_nested(employee, path, [])))}">
</div>
"""

    def render_checkbox(self, messages: dict[str, str], employee: dict[str, Any], path: str) -> str:
        name = path.replace(".", "__")
        return f"""
<div class="checkbox-field">
  <input type="checkbox" id="{h(name)}" name="{h(name)}" value="1"{checked(get_nested(employee, path, False))}>
  <label for="{h(name)}">{h(field_label(messages, path))}</label>
</div>
"""

    def render_textarea(self, messages: dict[str, str], employee: dict[str, Any], path: str) -> str:
        name = path.replace(".", "__")
        return f"""
<div class="form-field">
  <label for="{h(name)}">{h(field_label(messages, path))}</label>
  <textarea id="{h(name)}" name="{h(name)}">{h(get_nested(employee, path))}</textarea>
</div>
"""

    def import_error_item(self, messages: dict[str, str], row: int | str, csv_field: str, field_path: str, message_key: str, suggestion_key: str = "") -> dict[str, Any]:
        return {
            "row": row,
            "csv_field": csv_field,
            "field_path": field_path,
            "label": field_label(messages, field_path) if field_path else csv_field,
            "message": t(messages, message_key),
            "suggestion": t(messages, suggestion_key) if suggestion_key else "",
        }

    def handle_employee_import(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        _form, uploads, request_errors = self.parse_request_body(messages)
        import_errors: list[dict[str, Any]] = []
        if request_errors:
            self.send_employee_import_page(lang, messages, request_errors)
            return
        if len(uploads) != 1:
            self.send_employee_import_page(lang, messages, [t(messages, "import.error_one_file_required")])
            return
        upload = uploads[0]
        filename = str(upload.get("original_filename", ""))
        if not filename.lower().endswith(".csv"):
            self.send_employee_import_page(lang, messages, [t(messages, "import.error_csv_required")])
            return
        try:
            text = bytes(upload.get("content", b"")).decode("utf-8-sig")
        except UnicodeDecodeError:
            self.send_employee_import_page(lang, messages, [t(messages, "import.error_decode_failed")])
            return
        reader = csv.DictReader(io.StringIO(text))
        headers = reader.fieldnames or []
        detected_header_lang, missing_headers = detect_csv_header_language(headers)
        if missing_headers or not detected_header_lang:
            message = t(messages, "import.error_missing_headers").format(fields=", ".join(missing_headers))
            self.send_employee_import_page(lang, messages, [message])
            return
        rows = list(reader)
        if not rows:
            self.send_employee_import_page(lang, messages, [t(messages, "import.error_empty_file")])
            return

        entity_lookup, entity_error, duplicate_entity_codes = masterdata_entity_lookup_by_code(self.current_session_id())
        if entity_error:
            self.send_employee_import_page(lang, messages, [t(messages, "validation.masterdata_unavailable")])
            return
        if duplicate_entity_codes:
            message = t(messages, "import.error_duplicate_entity_codes").format(codes=", ".join(sorted(set(duplicate_entity_codes))))
            self.send_employee_import_page(lang, messages, [message])
            return

        current_employees = load_employees()
        proposed_employees = copy.deepcopy(current_employees)
        row_employees: list[tuple[int, dict[str, str], dict[str, Any], str]] = []
        next_id_seed = copy.deepcopy(proposed_employees)
        seen_employee_numbers: dict[str, int] = {}
        seen_emails: dict[str, int] = {}
        department_lookup_cache: dict[str, tuple[dict[str, dict[str, Any]], str | None, list[str]]] = {}

        for offset, raw_row in enumerate(rows, start=2):
            clean_row = canonical_import_row(raw_row, detected_header_lang)
            entity_code = clean_row.get("legal_entity_code", "")
            entity = entity_lookup.get(entity_code.casefold()) if entity_code else None
            if entity_code and not entity:
                import_errors.append(self.import_error_item(messages, offset, "legal_entity_code", "employment.entity_id", "validation.invalid_entity", "validation.suggestion.legal_entity_code"))
            department_code = clean_row.get("department_code", "")
            department: dict[str, Any] | None = None
            entity_id_for_department = str(entity.get("entity_id", "")).strip() if entity else ""
            if entity_id_for_department and entity_id_for_department not in department_lookup_cache:
                department_lookup_cache[entity_id_for_department] = masterdata_department_lookup_by_code(self.current_session_id(), entity_id_for_department)
            if entity_id_for_department:
                department_lookup, department_error, duplicate_department_codes = department_lookup_cache[entity_id_for_department]
                if department_error:
                    self.send_employee_import_page(lang, messages, [t(messages, "validation.masterdata_unavailable")])
                    return
                if duplicate_department_codes:
                    message = t(messages, "import.error_duplicate_department_codes").format(codes=", ".join(sorted(set(duplicate_department_codes))))
                    self.send_employee_import_page(lang, messages, [message])
                    return
                department = department_lookup.get(department_code.casefold()) if department_code else None
                if department_code and not department:
                    import_errors.append(self.import_error_item(messages, offset, "department_code", "employment.department_id", "validation.invalid_department", "validation.suggestion.department_code"))
            for csv_field in IMPORT_REQUIRED_CSV_FIELDS:
                if not clean_row.get(csv_field):
                    import_errors.append(self.import_error_item(messages, offset, csv_field, COMMON_REQUIRED_CSV_TO_PATH.get(csv_field, ""), "validation.required"))
            account_type = clean_row.get("bank_account_type", "").lower()
            if account_type and account_type not in {value for value in BANK_ACCOUNT_TYPES if value}:
                import_errors.append(self.import_error_item(messages, offset, "bank_account_type", "payroll.bank.account_type", "validation.invalid_bank_account_type", "validation.suggestion.bank_account_type"))
            account_number = clean_row.get("bank_account_number", "")
            if account_number and (not account_number.isdigit() or len(account_number) > 20):
                import_errors.append(self.import_error_item(messages, offset, "bank_account_number", "payroll.bank.account_number", "validation.invalid_bank_account_number", "validation.suggestion.bank_account_number"))
            employee_number_key = f"{str(entity.get('entity_id', '') if entity else '').casefold()}::{clean_row.get('employee_id', '').casefold()}"
            email_key = clean_row.get("work_email", "").casefold()
            if clean_row.get("employee_id"):
                first_row = seen_employee_numbers.get(employee_number_key)
                if first_row:
                    import_errors.append({"row": offset, "csv_field": "employee_id", "field_path": "employee_number", "label": field_label(messages, "employee_number"), "message": t(messages, "validation.duplicate_employee_number"), "suggestion": t(messages, "import.suggestion_duplicate_row").format(row=first_row)})
                else:
                    seen_employee_numbers[employee_number_key] = offset
            if email_key:
                first_row = seen_emails.get(email_key)
                if first_row:
                    import_errors.append({"row": offset, "csv_field": "work_email", "field_path": "profile.email", "label": field_label(messages, "profile.email"), "message": t(messages, "validation.duplicate_email"), "suggestion": t(messages, "import.suggestion_duplicate_row").format(row=first_row)})
                else:
                    seen_emails[email_key] = offset
            entity_id = str(entity.get("entity_id", "")).strip() if entity else ""
            existing_index = find_employee_index_by_number(proposed_employees, clean_row.get("employee_id", ""), entity_id)
            existing = proposed_employees[existing_index] if existing_index is not None else None
            employee = employee_from_import_row(clean_row, existing, actor, entity, department)
            mode = "updated" if existing else "created"
            if existing_index is None:
                employee["employee_id"] = next_employee_id(next_id_seed)
                next_id_seed.append(employee)
                proposed_employees.append(employee)
            else:
                proposed_employees[existing_index] = employee
            row_employees.append((offset, clean_row, employee, mode))

        for row_number, _row, employee, _mode in row_employees:
            import_errors.extend(employee_validation_errors(employee, proposed_employees, messages, row=row_number))

        if import_errors:
            append_module_audit_log(
                "employee",
                f"employee_import:{now_iso()}",
                "employee_import_failed",
                ["row_count", "error_count"],
                f"Employee CSV import failed with {len(import_errors)} errors",
                {"row_count": 0, "error_count": 0},
                {"row_count": len(rows), "error_count": len(import_errors)},
                actor,
            )
            self.send_employee_import_page(lang, messages, [t(messages, "import.failed")], import_errors)
            return

        created_count = sum(1 for _row_number, _row, _employee, mode in row_employees if mode == "created")
        updated_count = sum(1 for _row_number, _row, _employee, mode in row_employees if mode == "updated")
        before_count = len(visible_employees(current_employees))
        backup_path = backup_employees_before_import(current_employees)
        save_employees(proposed_employees)
        after_count = len(visible_employees(proposed_employees))
        import_id = f"employee_import:{now_iso()}"
        append_module_audit_log(
            "employee",
            import_id,
            "employee_imported",
            ["employee_count", "created_count", "updated_count", "backup_path"],
            f"Imported employee CSV: {created_count} created, {updated_count} updated, backup {backup_path}",
            {"employee_count": before_count, "created_count": 0, "updated_count": 0, "backup_path": ""},
            {"employee_count": after_count, "created_count": created_count, "updated_count": updated_count, "backup_path": backup_path},
            actor,
        )
        notice = t(messages, "import.success").format(created=created_count, updated=updated_count, backup=backup_path)
        self.redirect(url_with_lang("/employees", lang), notice)

    def handle_create_employee(self, lang: str, messages: dict[str, str], user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form = self.parse_form_body()
        employees = load_employees()
        employee = employee_from_form(form, actor=actor)
        employee["employee_id"] = next_employee_id(employees)
        validation_errors = employee_validation_errors(employee, employees, messages)
        errors = format_validation_errors(validation_errors)
        errors.extend(validate_masterdata_references(employee, self.current_session_id(), messages, lang))
        if errors:
            self.send_employee_form(lang, messages, employee, errors, "create", field_errors_by_path(validation_errors))
            return
        sync_masterdata_display_codes(employee, self.current_session_id())
        employees.append(employee)
        save_employees(employees)
        append_audit_log(employee["employee_id"], "employee_created", "employee", ["employee"], f"Created employee {employee['employee_id']}", None, employee, actor)
        notice = operation_notice(messages, "Employee", get_employee_number(employee), "created", actor)
        self.redirect(url_with_lang(f"/employees/{quote(employee['employee_id'])}/documents/edit", lang), notice)

    def handle_update_employee(self, lang: str, messages: dict[str, str], employee_id: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        form = self.parse_form_body()
        employees = load_employees()
        existing = find_employee(employees, employee_id)
        if not existing or get_nested(existing, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        before = copy.deepcopy(existing)
        updated = employee_from_form(form, existing, actor)
        updated["employee_id"] = employee_id
        validation_errors = employee_validation_errors(updated, employees, messages)
        errors = format_validation_errors(validation_errors)
        errors.extend(validate_masterdata_references(updated, self.current_session_id(), messages, lang, before))
        if errors:
            self.send_employee_form(lang, messages, updated, errors, "edit", field_errors_by_path(validation_errors))
            return
        sync_masterdata_display_codes(updated, self.current_session_id())
        fields = changed_fields(before, updated, PHASE1_FORM_FIELD_PATHS)
        if not fields:
            notice = no_change_notice(messages, "Employee", get_employee_number(updated))
            self.redirect(url_with_lang(f"/employees/{quote(employee_id)}", lang), notice)
            return
        employment_history_id = None
        employment_changed = [field for field in fields if field in EMPLOYMENT_HISTORY_TRIGGER_FIELD_PATHS]
        if employment_changed:
            employment_history_id = append_auto_history_record(updated, before, "employment", employment_changed, actor)
            if employment_history_id:
                fields.append("employment_history")
        for index, employee in enumerate(employees):
            if employee.get("employee_id") == employee_id:
                employees[index] = updated
                break
        save_employees(employees)
        action = "employee_status_changed" if "employment.status" in fields else "employee_updated"
        section = "employment" if any(field.startswith("employment.") for field in fields) else "profile"
        summary = f"Updated employee {employee_id}"
        if employment_history_id:
            summary += f" and appended employment history record {employment_history_id}"
        append_audit_log(employee_id, action, section, fields, summary, before, updated, actor)
        notice = operation_notice(messages, "Employee", get_employee_number(updated), "saved", actor)
        self.redirect(url_with_lang(f"/employees/{quote(employee_id)}", lang), notice)

    def handle_update_section(self, lang: str, messages: dict[str, str], employee_id: str, section_key: str, user: dict[str, Any]) -> None:
        actor = actor_from_user(user)
        config = SECTION_CONFIG[section_key]
        form: dict[str, str]
        uploads: list[dict[str, Any]] = []
        request_errors: list[str] = []
        if section_key == "documents":
            form, uploads, request_errors = self.parse_request_body(messages)
        else:
            form = self.parse_form_body()
        employees = load_employees()
        existing = find_employee(employees, employee_id)
        if not existing or get_nested(existing, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        before = copy.deepcopy(existing)
        file_writes: list[tuple[Path, bytes]] = []
        if section_key == "documents":
            upload_errors = request_errors + validate_upload_parts(uploads, messages)
            if upload_errors:
                updated, file_writes = documents_from_form(form, existing, [], actor)
                errors = upload_errors
            else:
                updated, file_writes = documents_from_form(form, existing, uploads, actor)
                errors = []
        else:
            updated = section_from_form(form, existing, config["field_paths"], actor)
            errors = []
        updated["employee_id"] = employee_id
        errors.extend(validate_section(updated, section_key, messages))
        if errors:
            self.send_section_form_with_employee(lang, messages, updated, section_key, errors)
            return
        fields = changed_fields(before, updated, config["field_paths"])
        section_label = t(messages, str(config["title_key"]))
        if not fields:
            notice = no_change_notice(messages, section_label, get_employee_number(updated))
            self.redirect(url_with_lang(f"/employees/{quote(employee_id)}", lang), notice)
            return
        history_id = None
        if section_key == "visa":
            trigger_fields = [field for field in fields if field in VISA_HISTORY_TRIGGER_FIELD_PATHS]
            history_id = append_auto_history_record(updated, before, "visa", trigger_fields, actor)
            if history_id:
                fields.append("visa_history")
        elif section_key == "dispatch":
            trigger_fields = [field for field in fields if field in DISPATCH_HISTORY_TRIGGER_FIELD_PATHS]
            history_id = append_auto_history_record(updated, before, "dispatch", trigger_fields, actor)
            if history_id:
                fields.append("dispatch_assignment_history")
        for index, employee in enumerate(employees):
            if employee.get("employee_id") == employee_id:
                employees[index] = updated
                break
        if file_writes:
            try:
                write_uploaded_files(file_writes)
            except Exception:
                self.send_section_form_with_employee(lang, messages, updated, section_key, [t(messages, "validation.upload_save_failed")])
                return
        save_employees(employees)
        upload_count = len(uploads) if section_key == "documents" else 0
        summary = f"Uploaded {upload_count} document file(s) for {employee_id}" if upload_count else f"Updated {config['audit_section']} information for {employee_id}"
        if history_id:
            summary += f" and appended history record {history_id}"
        append_audit_log(
            employee_id,
            str(config["audit_action"]),
            str(config["audit_section"]),
            fields,
            summary,
            before,
            updated,
            actor,
        )
        notice = operation_notice(messages, section_label, get_employee_number(updated), "saved", actor)
        self.redirect(url_with_lang(f"/employees/{quote(employee_id)}", lang), notice)

    def send_section_form_with_employee(self, lang: str, messages: dict[str, str], employee: dict[str, Any], section_key: str, errors: list[str]) -> None:
        employee_id = str(employee.get("employee_id", ""))
        config = SECTION_CONFIG[section_key]
        action = self.section_edit_url(employee_id, section_key, lang)
        enctype = ' enctype="multipart/form-data"' if section_key == "documents" else ""
        cancel_url = url_with_lang(f"/employees/{quote(employee_id)}", lang)
        body = f"""
<section class="object-page">
  {self.render_form_header(messages, str(config['title_key']), 'employee.form.section_description', get_employee_number(employee))}
  <form class="employee-form" method="post" action="{h(action)}"{enctype}>
    {self.render_errors(messages, errors)}
    {self.render_form_section(messages, str(config['title_key']), self.render_section_fields(messages, employee, section_key))}
    {self.render_form_actions(messages, cancel_url)}
  </form>
</section>
"""
        self.send_html(200, t(messages, config["title_key"]), body, lang, messages)

    def send_audit_logs_page(self, lang: str, messages: dict[str, str]) -> None:
        rows = []
        all_logs = load_audit_logs()
        employees_by_id = {str(employee.get("employee_id", "")): employee for employee in load_employees()}
        for audit in reversed(all_logs):
            fields = audit.get("changed_fields", [])
            if isinstance(fields, list):
                fields_text = ", ".join(str(field) for field in fields)
            else:
                fields_text = str(fields)
            employee_id = str(audit.get("employee_id", ""))
            employee = employees_by_id.get(employee_id, {})
            employee_label = get_employee_number(employee) if employee else employee_id
            summary_text = str(audit.get("summary", ""))
            if employee_id and employee_label:
                summary_text = summary_text.replace(employee_id, employee_label)
            employee_link = url_with_lang(f"/employees/{quote(employee_id)}", lang) if employee_id else "#"
            rows.append(
                f"""
<tr>
  <td>{h(audit.get('audit_id'))}</td>
  <td><a href="{h(employee_link)}">{h(employee_label)}</a></td>
  <td>{h(t(messages, 'audit_action.' + str(audit.get('action')), str(audit.get('action', ''))))}</td>
  <td>{h(audit.get('actor'))}</td>
  <td>{h(fields_text)}</td>
  <td>{h(summary_text)}</td>
  <td>{h(audit.get('created_at'))}</td>
</tr>
"""
            )
        table_body = "".join(rows) if rows else f"<tr><td colspan=\"7\" class=\"empty\">{h(t(messages, 'audit.empty'))}</td></tr>"
        body = f"""
<section class="card">
  <h2>{h(t(messages, 'audit.title'))}</h2>
  <table>
    <thead><tr>
      <th>{h(t(messages, 'audit.audit_id'))}</th><th>{h(field_label(messages, 'employee_number'))}</th><th>{h(t(messages, 'audit.action'))}</th><th>{h(t(messages, 'audit.actor'))}</th><th>{h(t(messages, 'audit.changed_fields'))}</th><th>{h(t(messages, 'audit.summary'))}</th><th>{h(t(messages, 'audit.created_at'))}</th>
    </tr></thead>
    <tbody>{table_body}</tbody>
  </table>
  <div class="helper-text" style="margin-top:8px">Showing latest {len(rows)} of {len(all_logs)} audit entries</div>
</section>
"""
        self.send_html(200, t(messages, "audit.title"), body, lang, messages)

    def send_employee_document_file(self, lang: str, messages: dict[str, str], employee_id: str, document_id: str, mode: str) -> None:
        employee = find_employee(load_employees(), employee_id)
        if not employee or get_nested(employee, "metadata.deleted", False):
            self.send_not_found(lang, messages)
            return
        document = find_employee_document(employee, document_id)
        if not document:
            self.send_not_found(lang, messages)
            return
        path = document_file_path(document)
        if not path or not path.is_file():
            self.send_not_found(lang, messages)
            return
        filename = document.get("original_filename") or document.get("stored_filename") or path.name
        disposition = content_disposition("attachment" if mode == "download" else "inline", filename)
        self.send_document_bytes(200, document_content_type(document, path), path.read_bytes(), disposition)

    def send_forbidden(self, lang: str, messages: dict[str, str]) -> None:
        body = """
<section class="card">
  <h2>403 Forbidden</h2>
  <p>This User_admin account does not have permission to access Employee Mgmt.</p>
</section>
"""
        self.send_html(403, "403 Forbidden", body, lang, messages)

    def send_not_found(self, lang: str, messages: dict[str, str]) -> None:
        body = f"<section class=\"card\"><h2>{h(t(messages, 'error.not_found'))}</h2><p>{h(t(messages, 'validation.not_found'))}</p></section>"
        self.send_html(404, t(messages, "error.not_found"), body, lang, messages)

    def parse_request_body(self, messages: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
        content_type = self.headers.get("Content-Type", "")
        if content_type.startswith("multipart/form-data"):
            return self.parse_multipart_body(content_type, messages)
        return self.parse_form_body(), [], []

    def parse_multipart_body(self, content_type: str, messages: dict[str, str]) -> tuple[dict[str, str], list[dict[str, Any]], list[str]]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > MAX_UPLOAD_REQUEST_BYTES:
            self.rfile.read(length)
            return {}, [], [t(messages, "validation.upload_request_too_large")]
        body = self.rfile.read(length)
        raw_message = f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
        try:
            message = BytesParser(policy=EMAIL_POLICY).parsebytes(raw_message)
        except Exception:
            return {}, [], [t(messages, "validation.upload_parse_failed")]
        form: dict[str, str] = {}
        uploads: list[dict[str, Any]] = []
        for part in message.iter_parts():
            disposition = part.get("Content-Disposition", "")
            if "form-data" not in disposition:
                continue
            name = part.get_param("name", header="Content-Disposition")
            if not name:
                continue
            filename = part.get_filename()
            payload = part.get_payload(decode=True) or b""
            if filename:
                uploads.append(
                    {
                        "field_name": str(name),
                        "original_filename": safe_original_filename(filename),
                        "content_type": part.get_content_type(),
                        "content": payload,
                    }
                )
            else:
                charset = part.get_content_charset() or "utf-8"
                form[str(name)] = payload.decode(charset, errors="replace")
        uploads = [upload for upload in uploads if upload.get("field_name") == "upload_files" and (upload.get("original_filename") or upload.get("content"))]
        return form, uploads, []

    def parse_form_body(self) -> dict[str, str]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        body = self.rfile.read(length).decode("utf-8")
        parsed = parse_qs(body, keep_blank_values=True)
        return {key: values[0] if values else "" for key, values in parsed.items()}

    def flash_message(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(FLASH_COOKIE)
        return unquote(morsel.value) if morsel else ""

    def flash_cookie_header(self, message: str) -> str:
        cookie = SimpleCookie()
        cookie[FLASH_COOKIE] = quote(message)
        cookie[FLASH_COOKIE]["path"] = "/"
        cookie[FLASH_COOKIE]["httponly"] = True
        cookie[FLASH_COOKIE]["samesite"] = "Lax"
        return cookie.output(header="").strip()

    def clear_flash_cookie_header(self) -> str:
        return f"{FLASH_COOKIE}=; Path=/; Max-Age=0; SameSite=Lax"

    def redirect(self, location: str, flash: str = "", extra_cookie: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        if extra_cookie:
            self.send_header("Set-Cookie", extra_cookie)
        self.end_headers()

    def send_html(self, status: int, title: str, body: str, lang: str, messages: dict[str, str]) -> None:
        flash = self.flash_message()
        if flash:
            body = f'<div class="message-strip message-success" role="status">{h(flash)}</div>' + body
            self._clear_flash_after_response = True
        self.send_bytes(status, "text/html; charset=utf-8", render_page(title, body, lang, messages, self.path, self.current_user(), self.request_host))

    def send_json(self, status: int, payload: Any) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_bytes(status, "application/json; charset=utf-8", body)

    def send_text(self, status: int, text: str) -> None:
        self.send_bytes(status, "text/plain; charset=utf-8", text.encode("utf-8"))

    def send_bytes(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        if content_type.startswith(("text/html", "application/json")):
            self.send_header("Cache-Control", "no-store")
        if getattr(self, "_clear_flash_after_response", False):
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
            self._clear_flash_after_response = False
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_document_bytes(self, status: int, content_type: str, body: bytes, disposition: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Content-Disposition", disposition)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "same-origin")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TAC-employeeadmin local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8004)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), EmployeeAdminHandler)
    print(f"TAC-employeeadmin running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TAC-employeeadmin")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
