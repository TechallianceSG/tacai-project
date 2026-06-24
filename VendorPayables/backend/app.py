#!/usr/bin/env python3
"""VendorPayables local MVP web app.

Dependency-free Python standard-library implementation for supplier payment
management. Data is stored as UTF-8 JSON arrays under ../database.
"""

from __future__ import annotations

import argparse
import cgi
import csv
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import StringIO
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlencode, urlparse

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
I18N_DIR = ROOT_DIR / "i18n"
ATTACHMENTS_DIR = ROOT_DIR / "attachments"
MACOS_VISION_OCR_SCRIPT = ROOT_DIR / "backend" / "macos_vision_ocr.swift"

PAYABLES_PATH = DATABASE_DIR / "vendor_payables.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
REPORT_EXPORTS_PATH = DATABASE_DIR / "report_exports.json"
MASTERDATA_ROOT = ROOT_DIR.parent / "TACAI-Core" / "masterdata"
MASTERDATA_VENDORS_PATH = MASTERDATA_ROOT / "database" / "vendors.json"
MASTERDATA_VENDOR_URL = "http://127.0.0.1:8007/vendors"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8005").strip() or f"http://{TACAI_PUBLIC_HOST}:8005").rstrip("/")

DEFAULT_LANG = "ja"
LANGS = ("en", "ja", "zh")
ACTOR = "finance_user"
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp"}
OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OCR_TESSERACT_LANGUAGES = "jpn+eng"
OCR_TIMEOUT_SECONDS = 30
OCR_STATUSES = {"not_run", "draft", "confirmed", "failed", "not_available"}
ACTIVE_STATUSES = {"Draft", "Submitted", "Approved", "Scheduled", "Rejected"}

EXPENSE_CATEGORIES = [
    "recruitment_media_fee",
    "outsourcing_project_cost",
    "saas_system_fee",
    "professional_service_fee",
    "office_admin_cost",
    "other",
]

PAYMENT_METHODS = ["bank_transfer", "card", "cash", "other"]
TAX_RATES = ["10%", "8%", "0%", "mixed", "unknown"]
STATUSES = ["Draft", "Submitted", "Approved", "Scheduled", "Paid", "Rejected", "Cancelled"]
SUPPLIER_RECORD_MODES = ["standard_vendor", "one_time_vendor"]
ONE_TIME_VENDOR_CODE = "ONETIME"
ONE_TIME_VENDOR_REASONS = [
    "small_amount_once",
    "trial_service",
    "government_fee",
    "event_or_spot_purchase",
    "no_expected_future_transaction",
    "other",
]


def ensure_storage() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in [PAYABLES_PATH, AUDIT_LOGS_PATH, REPORT_EXPORTS_PATH]:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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


def save_json_array(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_i18n(lang: str) -> dict[str, str]:
    path = I18N_DIR / f"{lang}.json"
    fallback = I18N_DIR / f"{DEFAULT_LANG}.json"
    target = path if path.exists() else fallback
    if not target.exists():
        return {}
    data = json.loads(target.read_text(encoding="utf-8"))
    return {str(k): str(v) for k, v in data.items()}


def t(messages: dict[str, str], key: str, default: str | None = None) -> str:
    return messages.get(key, default or key)


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def parse_amount(value: str | None) -> int:
    raw = (value or "").replace(",", "").strip()
    if not raw:
        return 0
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.0+", raw):
        return int(float(raw))
    return 0


def fmt_money(value: Any) -> str:
    try:
        amount = int(str(value or "0"))
    except ValueError:
        return esc(value)
    return f"{amount:,}"


def sanitize_filename(filename: str) -> str:
    base = Path(filename).name.strip() or "attachment"
    base = re.sub(r"[^A-Za-z0-9._-]+", "_", base)
    return base[:120] or "attachment"


def next_sequence(rows: list[dict[str, Any]], key: str, prefix: str) -> str:
    max_num = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-?(\d+)$")
    for row in rows:
        value = str(row.get(key, ""))
        match = pattern.match(value)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}{max_num + 1:04d}"


def next_payable_no(rows: list[dict[str, Any]]) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"VP-{year}-"
    max_num = 0
    for row in rows:
        value = str(row.get("payable_no", ""))
        if value.startswith(prefix):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


def append_audit_log(module: str, record_id: str, action: str, before_value: Any, after_value: Any) -> None:
    logs = load_json_array(AUDIT_LOGS_PATH)
    audit_id = next_sequence(logs, "audit_id", "AUD-")
    logs.append(
        {
            "audit_id": audit_id,
            "module": module,
            "record_id": record_id,
            "action": action,
            "user": ACTOR,
            "timestamp": now_iso(),
            "before_value": before_value,
            "after_value": after_value,
        }
    )
    save_json_array(AUDIT_LOGS_PATH, logs)


NO_OP_COMPARE_IGNORE_FIELDS = {"updated_at", "updated_by"}


def records_business_equal(before: dict[str, Any] | None, after: dict[str, Any] | None, ignore_fields: set[str] | None = None) -> bool:
    before = before or {}
    after = after or {}
    ignored = ignore_fields or NO_OP_COMPARE_IGNORE_FIELDS
    keys = (set(before.keys()) | set(after.keys())) - ignored
    return all(before.get(key, "") == after.get(key, "") for key in keys)


def no_change_message(record_name: str) -> str:
    timestamp = now_iso()
    record = record_name or "-"
    return f"No changes detected for Payable record {record} at {timestamp}. Nothing was saved and no audit entry was created. / {timestamp} 未检测到供应商付款记录 {record} 的变更。未保存，也未生成审计记录。 / {timestamp} 時点で仕入先支払レコード {record} に変更はありません。保存および監査記録の作成は行われませんでした。"


def find_by_id(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get(key, "")) == value:
            return row
    return None


def active_payables() -> list[dict[str, Any]]:
    return [row for row in load_json_array(PAYABLES_PATH) if row.get("record_status", "Active") == "Active"]


def vendor_display_name(vendor: dict[str, Any], lang: str = DEFAULT_LANG) -> str:
    localized = str(vendor.get(f"vendor_name_{lang}", "")).strip()
    english = str(vendor.get("vendor_name_en", "")).strip()
    japanese = str(vendor.get("vendor_name_ja", "")).strip()
    legacy = str(vendor.get("vendor_name", "")).strip()
    code = str(vendor.get("vendor_code", "")).strip()
    return localized or english or japanese or legacy or code


def active_vendors() -> list[dict[str, Any]]:
    return [row for row in load_json_array(MASTERDATA_VENDORS_PATH) if row.get("status") == "active"]


def masterdata_vendor_available() -> bool:
    return MASTERDATA_VENDORS_PATH.exists()


def vendor_snapshot(vendor: dict[str, Any], lang: str = DEFAULT_LANG) -> dict[str, str]:
    return {
        "vendor_code_snapshot": str(vendor.get("vendor_code", "")),
        "vendor_name_snapshot": vendor_display_name(vendor, lang),
        "qualified_invoice_number_snapshot": str(vendor.get("qualified_invoice_number", "")),
        "payment_terms_snapshot": str(vendor.get("payment_terms", "")),
        "supplier_record_mode_snapshot": str(vendor.get("supplier_record_mode", "standard_vendor") or "standard_vendor"),
        "bank_name_snapshot": str(vendor.get("bank_name", "")),
        "bank_branch_snapshot": str(vendor.get("bank_branch", "")),
        "bank_account_number_masked_snapshot": str(vendor.get("bank_account_number_masked", "")),
        "bank_account_holder_snapshot": str(vendor.get("bank_account_holder", "")),
    }


def supplier_record_mode_label(mode: str) -> str:
    labels = {
        "standard_vendor": "Standard Vendor / 通常仕入先 / 正常供应商",
        "one_time_vendor": "One-time Vendor / 一回限り仕入先 / 一次性供应商",
    }
    return labels.get(mode, mode or "-")


def one_time_reason_label(reason: str) -> str:
    labels = {
        "small_amount_once": "Small amount once / 小額一回限り / 小额一次性",
        "trial_service": "Trial service / トライアル / 试用服务",
        "government_fee": "Government/public fee / 公的費用 / 政府公共费用",
        "event_or_spot_purchase": "Event or spot purchase / 臨時購入 / 临时采购",
        "no_expected_future_transaction": "No expected future transaction / 継続予定なし / 不预计再交易",
        "other": "Other / その他 / 其他",
    }
    return labels.get(reason, reason or "-")


def one_time_vendor_master(lang: str = DEFAULT_LANG) -> dict[str, Any] | None:
    candidates = [
        vendor for vendor in active_vendors()
        if str(vendor.get("supplier_record_mode", "standard_vendor")) == "one_time_vendor"
        or str(vendor.get("vendor_code", "")).upper() == ONE_TIME_VENDOR_CODE
    ]
    if not candidates:
        return None
    return sorted(candidates, key=lambda vendor: str(vendor.get("vendor_code", "")))[0]


def virtual_one_time_vendor_snapshot() -> dict[str, str]:
    return {
        "vendor_code_snapshot": ONE_TIME_VENDOR_CODE,
        "vendor_name_snapshot": "One-time Vendor / 一回限り仕入先 / 一次性供应商",
        "qualified_invoice_number_snapshot": "",
        "payment_terms_snapshot": "",
        "supplier_record_mode_snapshot": "one_time_vendor",
        "bank_name_snapshot": "",
        "bank_branch_snapshot": "",
        "bank_account_number_masked_snapshot": "",
        "bank_account_holder_snapshot": "",
    }


def normalized_match_text(value: Any) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", str(value or "")).casefold())


def match_ocr_vendor(draft: dict[str, Any], lang: str = DEFAULT_LANG) -> dict[str, Any]:
    qualified = str(draft.get("qualified_invoice_number") or "").strip().upper()
    vendor_name = normalized_match_text(draft.get("vendor_name"))
    active = [vendor for vendor in active_vendors() if str(vendor.get("supplier_record_mode", "standard_vendor")) != "one_time_vendor"]
    if qualified:
        matches = [vendor for vendor in active if str(vendor.get("qualified_invoice_number", "")).strip().upper() == qualified]
        if len(matches) == 1:
            vendor = matches[0]
            return {"status": "matched", "matched_vendor_id": vendor.get("vendor_id", ""), "matched_vendor_code": vendor.get("vendor_code", ""), "matched_vendor_name": vendor_display_name(vendor, lang), "confidence": "high", "match_reasons": ["qualified_invoice_number"]}
        if len(matches) > 1:
            return {"status": "multiple", "matched_vendor_id": "", "matched_vendor_code": "", "matched_vendor_name": "", "confidence": "medium", "match_reasons": ["qualified_invoice_number"]}
    if vendor_name:
        exact = [vendor for vendor in active if vendor_name in {normalized_match_text(vendor_display_name(vendor, lang)), normalized_match_text(vendor.get("vendor_name_en")), normalized_match_text(vendor.get("vendor_name_ja")), normalized_match_text(vendor.get("vendor_name"))}]
        if len(exact) == 1:
            vendor = exact[0]
            return {"status": "matched", "matched_vendor_id": vendor.get("vendor_id", ""), "matched_vendor_code": vendor.get("vendor_code", ""), "matched_vendor_name": vendor_display_name(vendor, lang), "confidence": "medium", "match_reasons": ["vendor_name"]}
        if len(exact) > 1:
            return {"status": "multiple", "matched_vendor_id": "", "matched_vendor_code": "", "matched_vendor_name": "", "confidence": "low", "match_reasons": ["vendor_name"]}
    return {"status": "none", "matched_vendor_id": "", "matched_vendor_code": "", "matched_vendor_name": "", "confidence": "low", "match_reasons": []}


def get_lang(query: dict[str, list[str]]) -> str:
    lang = (query.get("lang") or [DEFAULT_LANG])[0]
    return lang if lang in LANGS else DEFAULT_LANG


def url(path: str, lang: str, **params: str) -> str:
    query = {"lang": lang}
    query.update({k: v for k, v in params.items() if v is not None})
    return f"{path}?{urlencode(query)}"


def status_badge(status: str) -> str:
    safe = re.sub(r"[^a-z0-9_-]+", "-", status.lower())
    return f'<span class="status-badge status-{safe}">{esc(status)}</span>'


def options_html(options: list[str], selected: str = "", include_blank: bool = False) -> str:
    chunks = []
    if include_blank:
        chunks.append('<option value=""></option>')
    for option in options:
        sel = " selected" if option == selected else ""
        chunks.append(f'<option value="{esc(option)}"{sel}>{esc(option)}</option>')
    return "".join(chunks)


def vendor_options(vendors: list[dict[str, Any]], selected: str = "", lang: str = DEFAULT_LANG) -> str:
    chunks = ['<option value=""></option>']
    for vendor in vendors:
        vendor_id = str(vendor.get("vendor_id", ""))
        label = f"{vendor.get('vendor_code', '')} {vendor_display_name(vendor, lang)}".strip()
        sel = " selected" if vendor_id == selected else ""
        chunks.append(f'<option value="{esc(vendor_id)}"{sel}>{esc(label)}</option>')
    return "".join(chunks)


def is_overdue(row: dict[str, Any]) -> bool:
    due = str(row.get("payment_due_date", ""))
    return bool(due and due < today_iso() and row.get("status") in ACTIVE_STATUSES)


def parse_form(handler: BaseHTTPRequestHandler) -> tuple[dict[str, str], dict[str, cgi.FieldStorage]]:
    content_type = handler.headers.get("Content-Type", "")
    fields: dict[str, str] = {}
    files: dict[str, cgi.FieldStorage] = {}
    if content_type.startswith("multipart/form-data"):
        form = cgi.FieldStorage(
            fp=handler.rfile,
            headers=handler.headers,
            environ={
                "REQUEST_METHOD": "POST",
                "CONTENT_TYPE": content_type,
            },
        )
        for key in form.keys():
            item = form[key]
            if isinstance(item, list):
                item = item[0]
            if getattr(item, "filename", None):
                files[key] = item
            else:
                fields[key] = item.value if item.value is not None else ""
    else:
        length = int(handler.headers.get("Content-Length", "0") or 0)
        body = handler.rfile.read(length).decode("utf-8")
        parsed = parse_qs(body, keep_blank_values=True)
        fields = {key: values[0] if values else "" for key, values in parsed.items()}
    return fields, files


def save_attachment(item: cgi.FieldStorage, payable_no: str) -> dict[str, Any] | None:
    original = getattr(item, "filename", "") or ""
    if not original:
        return None
    safe_original = sanitize_filename(original)
    ext = Path(safe_original).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported attachment type.")
    content = item.file.read()
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Attachment exceeds 5MB limit.")
    stored = sanitize_filename(f"{payable_no}-{int(datetime.now(timezone.utc).timestamp())}-{safe_original}")
    target = ATTACHMENTS_DIR / stored
    target.write_bytes(content)
    content_type = item.type or mimetypes.guess_type(safe_original)[0] or "application/octet-stream"
    return {
        "original_filename": original,
        "stored_filename": stored,
        "relative_path": f"attachments/{stored}",
        "content_type": content_type,
        "size_bytes": len(content),
        "uploaded_at": now_iso(),
    }


OCR_TO_PAYABLE_FIELD_MAPPING = [
    ("vendor_name", "vendor_name_snapshot", "Vendor / 仕入先"),
    ("invoice_number", "invoice_number", "Invoice No. / 請求書番号"),
    ("invoice_date", "invoice_date", "Invoice Date / 請求日"),
    ("payment_due_date", "payment_due_date", "Payment Due Date / 支払期限"),
    ("currency", "currency", "Currency / 通貨"),
    ("amount_excluding_tax", "amount_excluding_tax", "Amount excl. Tax / 税抜金額"),
    ("tax_amount", "tax_amount", "Tax Amount / 消費税額"),
    ("total_amount", "total_amount", "Total Amount / 請求金額"),
    ("tax_rate", "tax_rate", "Tax Rate / 税率"),
    ("qualified_invoice_number", "qualified_invoice_number", "Qualified Invoice No. / 適格請求書登録番号"),
    ("bank_account_text", "finance_notes", "Bank Account Text / 振込先"),
]
STANDARD_PAYABLE_INPUT_FIELDS = [
    "supplier_record_mode", "vendor_id", "vendor_name_snapshot", "request_title", "business_purpose", "invoice_number", "invoice_date",
    "received_date", "payment_due_date", "actual_payment_date", "currency", "amount_excluding_tax", "tax_rate",
    "tax_amount", "total_amount", "withholding_tax_amount", "payment_method", "expense_category",
    "related_client_name", "related_project_name", "department", "qualified_invoice_number",
    "one_time_vendor_name", "one_time_vendor_address", "one_time_qualified_invoice_number", "one_time_bank_account_text", "one_time_reason",
    "finance_notes",
]
MONEY_PAYABLE_FIELDS = {"amount_excluding_tax", "tax_amount", "total_amount", "withholding_tax_amount"}
SELECT_PAYABLE_FIELDS = {"tax_rate", "payment_method", "expense_category"}


def default_ocr_draft() -> dict[str, Any]:
    return {
        "vendor_name": None,
        "invoice_number": None,
        "invoice_date": None,
        "payment_due_date": None,
        "currency": "JPY",
        "total_amount": None,
        "amount_excluding_tax": None,
        "tax_amount": None,
        "tax_rate": None,
        "qualified_invoice_number": None,
        "bank_account_text": None,
        "confidence_notes": [],
        "requires_manual_review": True,
        "raw_text_preview": "",
        "source_attachment": "",
        "created_at": "",
        "vendor_match": {
            "status": "none",
            "matched_vendor_id": "",
            "matched_vendor_code": "",
            "matched_vendor_name": "",
            "confidence": "low",
            "match_reasons": [],
        },
    }


def empty_to_none(value: Any) -> str | None:
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def optional_amount(value: Any) -> int | None:
    if value in (None, ""):
        return None
    amount = parse_amount(str(value))
    return amount if amount >= 0 else None


def normalize_ocr_draft(draft: dict[str, Any] | None) -> dict[str, Any]:
    normalized = default_ocr_draft()
    if isinstance(draft, dict):
        normalized.update(draft)
    for key in ["vendor_name", "invoice_number", "invoice_date", "payment_due_date", "qualified_invoice_number", "tax_rate", "bank_account_text", "raw_text_preview", "source_attachment", "created_at"]:
        normalized[key] = empty_to_none(normalized.get(key))
    normalized["currency"] = str(normalized.get("currency") or "JPY").strip() or "JPY"
    if normalized["tax_rate"] not in set(TAX_RATES) | {None}:
        normalized["tax_rate"] = "unknown"
    for key in ["total_amount", "amount_excluding_tax", "tax_amount"]:
        normalized[key] = optional_amount(normalized.get(key))
    qualified = normalized.get("qualified_invoice_number")
    if qualified:
        qualified = str(qualified).strip().upper()
        normalized["qualified_invoice_number"] = qualified if re.fullmatch(r"T\d{13}", qualified) else None
    notes = normalized.get("confidence_notes")
    if not isinstance(notes, list):
        notes = [str(notes)] if notes else []
    normalized["confidence_notes"] = [str(note) for note in notes if str(note).strip()]
    vendor_match = normalized.get("vendor_match") if isinstance(normalized.get("vendor_match"), dict) else {}
    normalized["vendor_match"] = {
        "status": str(vendor_match.get("status", "none") or "none"),
        "matched_vendor_id": str(vendor_match.get("matched_vendor_id", "") or ""),
        "matched_vendor_code": str(vendor_match.get("matched_vendor_code", "") or ""),
        "matched_vendor_name": str(vendor_match.get("matched_vendor_name", "") or ""),
        "confidence": str(vendor_match.get("confidence", "low") or "low"),
        "match_reasons": vendor_match.get("match_reasons") if isinstance(vendor_match.get("match_reasons"), list) else [],
    }
    normalized["requires_manual_review"] = True
    return normalized


def validate_vendor_ocr_draft_record(row: dict[str, Any]) -> None:
    if row.get("ocr_status") not in OCR_STATUSES:
        raise ValueError("OCR status is invalid.")
    if row.get("ocr_status") in {"draft", "confirmed"} and not row.get("attachment"):
        raise ValueError("OCR draft requires a saved attachment.")
    draft = normalize_ocr_draft(row.get("ocr_draft") or {})
    if row.get("ocr_status") == "draft" and not draft.get("requires_manual_review"):
        raise ValueError("OCR draft must require manual review.")


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
    return f'<span class="status-badge {css_class}">{esc(labels.get(status, status or "-"))}</span>'


def ocr_display_value(value_to_show: Any) -> str:
    if value_to_show in (None, ""):
        return "-"
    return str(value_to_show)


def ocr_field_hint_html(row: dict[str, Any], payable_field: str) -> str:
    if str(row.get("ocr_status", "not_run")) not in {"draft", "confirmed", "failed"}:
        return ""
    draft = normalize_ocr_draft(row.get("ocr_draft") or {})
    source = next((source for source, target, _label in OCR_TO_PAYABLE_FIELD_MAPPING if target == payable_field), "")
    if not source:
        return ""
    value_to_show = draft.get(source)
    if value_to_show in (None, "", "unknown"):
        return ""
    return f'<p class="ocr-hint">OCR suggestion: {esc(value_to_show)}</p>'


def ocr_draft_review_html(row: dict[str, Any]) -> str:
    status = str(row.get("ocr_status", "not_run"))
    if status == "not_run":
        return ""
    draft = normalize_ocr_draft(row.get("ocr_draft") or {})
    notes = draft.get("confidence_notes") or []
    note_items = "".join(f"<li>{esc(note)}</li>" for note in notes) or "<li>No confidence notes.</li>"
    rows = []
    for source, target, label in OCR_TO_PAYABLE_FIELD_MAPPING:
        rows.append(
            "<tr>"
            f"<th>{esc(label)}</th>"
            f"<td>{esc(ocr_display_value(draft.get(source)))}</td>"
            f"<td>{esc(ocr_display_value(row.get(target)))}</td>"
            "</tr>"
        )
    raw_preview = draft.get("raw_text_preview") or ""
    raw_html = f"<details><summary>Raw OCR preview</summary><pre>{esc(raw_preview)}</pre></details>" if raw_preview else ""
    vendor_match = draft.get("vendor_match") if isinstance(draft.get("vendor_match"), dict) else {}
    match_html = (
        '<h4>Vendor Master Match / 仕入先マッチング</h4>'
        f'<p class="muted">Status: {esc(vendor_match.get("status", "none"))}; '
        f'Code: {esc(vendor_match.get("matched_vendor_code", ""))}; '
        f'Name: {esc(vendor_match.get("matched_vendor_name", ""))}; '
        f'Confidence: {esc(vendor_match.get("confidence", "low"))}</p>'
    )
    return (
        '<div class="card ocr-panel">'
        '<h3>OCR Draft Review / OCR下書き確認</h3>'
        f'<p class="message">OCR status: {ocr_status_badge(status)}. OCR suggestions are draft assistance only; final payments use the reviewed payable fields.</p>'
        f'{match_html}'
        f'<table><thead><tr><th>Field</th><th>OCR suggestion</th><th>Current payable value</th></tr></thead><tbody>{"".join(rows)}</tbody></table>'
        '<h4>Confidence notes / 確認メモ</h4>'
        f'<ul>{note_items}</ul>{raw_html}</div>'
    )


def safe_attachment_path(attachment: dict[str, Any]) -> Path:
    relative_path = str(attachment.get("relative_path", "")).strip()
    if not relative_path:
        stored = str(attachment.get("stored_filename", "")).strip()
        relative_path = f"attachments/{stored}" if stored else ""
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
    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError("Attachment type is not supported for OCR.")
    return path


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
            with tempfile.TemporaryDirectory(prefix="vendorpayables-ocr-") as temp_dir:
                output_prefix = str(Path(temp_dir) / "page")
                subprocess.run([pdftoppm, "-f", "1", "-singlefile", "-png", str(path), output_prefix], check=True, capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS)
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


def run_tesseract_ocr(image_path: Path) -> tuple[str, list[str], str]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return "", ["Local OCR requires Tesseract, but tesseract was not found on PATH."], "not_available"
    notes: list[str] = []
    outputs: list[str] = []
    for psm in ["6", "11"]:
        try:
            result = subprocess.run([tesseract, str(image_path), "stdout", "-l", OCR_TESSERACT_LANGUAGES, "--psm", psm], check=False, capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS)
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
        result = subprocess.run([swift, str(MACOS_VISION_OCR_SCRIPT), str(path)], check=False, capture_output=True, text=True, timeout=OCR_TIMEOUT_SECONDS)
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


def build_vendor_invoice_ocr_draft(attachment: dict[str, Any]) -> tuple[dict[str, Any], str]:
    notes = ["Local OCR engine: Tesseract (jpn+eng). OCR values are draft suggestions only."]
    text, extraction_notes, status = extract_local_ocr_text(attachment)
    notes.extend(extraction_notes)
    if status != "draft":
        draft = default_ocr_draft()
        draft["confidence_notes"] = notes
        draft["source_attachment"] = str(attachment.get("stored_filename", ""))
        draft["created_at"] = now_iso()
        return normalize_ocr_draft(draft), status
    draft = parse_vendor_invoice_ocr_text(text, notes)
    draft["vendor_match"] = match_ocr_vendor(draft)
    draft["raw_text_preview"] = normalize_ocr_text(text)[:1600]
    draft["source_attachment"] = str(attachment.get("stored_filename", ""))
    draft["created_at"] = now_iso()
    parsed_values = [draft.get(key) for key in ["vendor_name", "invoice_number", "invoice_date", "payment_due_date", "qualified_invoice_number", "total_amount", "tax_amount", "amount_excluding_tax"]]
    if not any(value not in (None, "", 0, "unknown") for value in parsed_values):
        draft["confidence_notes"].append("OCR ran, but no supported vendor invoice fields were confidently recognized. Please enter the payable manually.")
        return normalize_ocr_draft(draft), "failed"
    return normalize_ocr_draft(draft), "draft"


def parse_vendor_invoice_ocr_text(text: str, notes: list[str]) -> dict[str, Any]:
    normalized = normalize_ocr_text(text)
    lines = [line.strip() for line in normalized.splitlines() if line.strip()]
    joined = "\n".join(lines)
    draft = default_ocr_draft()
    draft["confidence_notes"] = list(notes)
    draft["qualified_invoice_number"] = extract_qualified_invoice_number(joined, draft["confidence_notes"])
    draft["invoice_number"] = extract_invoice_number(joined)
    draft["invoice_date"] = extract_labeled_date(joined, ["請求日", "発行日", "Invoice Date", "Date"], draft["confidence_notes"])
    draft["payment_due_date"] = extract_labeled_date(joined, ["支払期限", "支払期日", "お支払期限", "Due Date", "Payment Due"], draft["confidence_notes"], allow_unlabeled=False)
    draft["total_amount"] = extract_labeled_amount(joined, ["ご請求金額", "請求金額", "税込合計", "合計金額", "お支払金額", "Amount Due", "Total", "合計"], ["小計", "税", "消費税"])
    draft["amount_excluding_tax"] = extract_labeled_amount(joined, ["税抜金額", "税抜", "小計", "Subtotal"], ["消費税"])
    draft["tax_amount"] = extract_labeled_amount(joined, ["消費税等", "消費税", "税額", "Tax"], [])
    draft["tax_rate"] = extract_tax_rate(joined)
    draft["vendor_name"] = extract_vendor_name(lines, draft["confidence_notes"])
    draft["bank_account_text"] = extract_bank_account_text(lines)
    draft["currency"] = "JPY"
    draft["requires_manual_review"] = True
    for key, label in [("vendor_name", "Vendor name"), ("invoice_number", "Invoice number"), ("invoice_date", "Invoice date"), ("total_amount", "Total amount")]:
        if not draft.get(key):
            draft["confidence_notes"].append(f"{label} was not confidently recognized.")
    return draft


def extract_qualified_invoice_number(text: str, notes: list[str]) -> str | None:
    candidates = []
    for match in re.finditer(r"[TＴ][ \t\-]*\d(?:[\d \t\-]{11,20})", text, flags=re.IGNORECASE):
        normalized = re.sub(r"[^TtＴ0-9]", "", match.group(0)).upper().replace("Ｔ", "T")
        if re.fullmatch(r"T\d{13}", normalized):
            candidates.append(normalized)
    unique = list(dict.fromkeys(candidates))
    if len(unique) > 1:
        notes.append("Multiple qualified invoice number candidates were found; the first one was used.")
    return unique[0] if unique else None


def extract_invoice_number(text: str) -> str | None:
    patterns = [
        r"(?:請求書番号|請求番号|Invoice\s*(?:No\.?|#|Number)|No\.?)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9._\-/]{1,40})",
        r"(?:番号)\s*[:：#]?\s*([A-Za-z0-9][A-Za-z0-9._\-/]{2,40})",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if not match:
            continue
        value = match.group(1).strip().strip(".,;")
        if not re.fullmatch(r"T\d{13}", value.upper()):
            return value[:40]
    return None


def extract_labeled_date(text: str, labels: list[str], notes: list[str], allow_unlabeled: bool = True) -> str | None:
    for label in labels:
        for pattern in [
            rf"{re.escape(label)}\D{{0,12}}(\d{{4}})[年/\-.](\d{{1,2}})[月/\-.](\d{{1,2}})日?",
            rf"{re.escape(label)}\D{{0,12}}令和\s*(\d{{1,2}})[年/\-.](\d{{1,2}})[月/\-.](\d{{1,2}})日?",
            rf"{re.escape(label)}\D{{0,12}}R\s*(\d{{1,2}})[年/\-.](\d{{1,2}})[月/\-.](\d{{1,2}})日?",
        ]:
            match = re.search(pattern, text, flags=re.IGNORECASE)
            if match:
                return normalize_date_match(match.groups())
    if not allow_unlabeled:
        return None
    candidates = []
    for pattern in [r"(\d{4})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?", r"令和\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?", r"R\s*(\d{1,2})[年/\-.](\d{1,2})[月/\-.](\d{1,2})日?"]:
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


def normalize_date_match(groups: tuple[str, ...]) -> str | None:
    try:
        first = int(groups[0])
        year = 2018 + first if first < 100 else first
        month = int(groups[1])
        day = int(groups[2])
        candidate = f"{year:04d}-{month:02d}-{day:02d}"
        datetime.strptime(candidate, "%Y-%m-%d")
        return candidate
    except (ValueError, IndexError):
        return None


def extract_labeled_amount(text: str, labels: list[str], excluded_nearby: list[str]) -> int | None:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for index, line in enumerate(lines):
        matching_label = next((label for label in labels if label.lower() in line.lower()), "")
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
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            nearby = text[max(0, match.start() - 8): match.end() + 8]
            if any(excluded in nearby and excluded not in label for excluded in excluded_nearby):
                continue
            amount = parse_amount_text(match.group(1))
            if amount is not None:
                return amount
    return None


def extract_first_positive_amount(text: str) -> int | None:
    for pattern in [r"(?<![-−])[¥￥]\s*([0-9][0-9,]*)", r"(?<![-−])([0-9][0-9,]*)\s*円"]:
        for match in re.finditer(pattern, text):
            amount = parse_amount_text(match.group(1))
            if amount is not None:
                return amount
    for match in re.finditer(r"(?<![-−])([0-9][0-9,]*)", text):
        amount = parse_amount_text(match.group(1))
        if amount is not None:
            return amount
    return None


def parse_amount_text(value: str) -> int | None:
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


def extract_vendor_name(lines: list[str], notes: list[str]) -> str | None:
    label_pattern = re.compile(r"(?:請求元|発行者|販売者|事業者名|会社名|Vendor|Supplier|From)\s*[:：]?\s*(.+)", re.IGNORECASE)
    for line in lines[:20]:
        match = label_pattern.search(line)
        if match:
            value = trim_vendor_line(match.group(1))
            if value:
                return value
    skip_keywords = ["請求書", "見積書", "納品書", "登録番号", "TEL", "電話", "住所", "合計", "消費税", "請求日", "発行日", "支払", "振込", "銀行"]
    company_keywords = ["株式会社", "有限会社", "合同会社", "Inc.", "Co.", "Ltd", "LLC", "Company"]
    clean_lines = [line for line in lines[:14] if len(line) >= 2 and not any(keyword in line for keyword in skip_keywords)]
    for line in clean_lines:
        if any(keyword in line for keyword in company_keywords):
            return trim_vendor_line(line)
    for line in clean_lines[:5]:
        if not re.search(r"[0-9]{3,}|[¥円]", line):
            notes.append("Vendor name candidate was selected from the top OCR text and must be reviewed.")
            return trim_vendor_line(line)
    return None


def trim_vendor_line(line: str) -> str:
    return re.sub(r"\s+", " ", line).strip(" -*:：")[:100]


def extract_bank_account_text(lines: list[str]) -> str | None:
    keywords = ["振込先", "銀行", "支店", "普通", "当座", "口座番号", "口座名義", "Bank", "Account", "Branch"]
    selected: list[str] = []
    for index, line in enumerate(lines):
        if any(keyword.lower() in line.lower() for keyword in keywords):
            start = max(0, index - 1)
            end = min(len(lines), index + 4)
            selected.extend(lines[start:end])
    unique = list(dict.fromkeys(selected))
    return "\n".join(unique)[:700] if unique else None


def apply_ocr_draft_to_payable_defaults(row: dict[str, Any]) -> dict[str, Any]:
    draft = normalize_ocr_draft(row.get("ocr_draft") or {})
    row = dict(row)
    supplier_mode = str(row.get("supplier_record_mode", "standard_vendor") or "standard_vendor")
    if supplier_mode == "one_time_vendor":
        one_time_mapping = [
            ("vendor_name", "one_time_vendor_name"),
            ("qualified_invoice_number", "one_time_qualified_invoice_number"),
            ("bank_account_text", "one_time_bank_account_text"),
        ]
        for source, target in one_time_mapping:
            value_to_apply = draft.get(source)
            if value_to_apply not in (None, "", "unknown") and not str(row.get(target, "")).strip():
                row[target] = value_to_apply
    else:
        vendor_match = draft.get("vendor_match") if isinstance(draft.get("vendor_match"), dict) else {}
        matched_vendor_id = str(vendor_match.get("matched_vendor_id", ""))
        if matched_vendor_id and not row.get("vendor_id"):
            matched_vendor = find_by_id(active_vendors(), "vendor_id", matched_vendor_id)
            if matched_vendor:
                row["vendor_id"] = matched_vendor_id
                row.update(vendor_snapshot(matched_vendor))
    for source, target, _label in OCR_TO_PAYABLE_FIELD_MAPPING:
        value_to_apply = draft.get(source)
        if value_to_apply in (None, "", "unknown"):
            continue
        if target == "finance_notes":
            continue
        current = row.get(target)
        if target in MONEY_PAYABLE_FIELDS:
            if parse_amount(str(current or "0")) == 0:
                row[target] = value_to_apply
        elif target == "vendor_name_snapshot" and supplier_mode == "standard_vendor" and row.get("vendor_id"):
            continue
        elif not str(current or "").strip():
            row[target] = value_to_apply
    row["ocr_draft"] = draft
    return row


def preserve_manual_payable_form_values(row: dict[str, Any], fields: dict[str, str]) -> dict[str, Any]:
    row = dict(row)
    for field in STANDARD_PAYABLE_INPUT_FIELDS:
        raw_value = fields.get(field, "")
        text_value = raw_value.strip() if isinstance(raw_value, str) else str(raw_value).strip()
        if not text_value:
            continue
        if field in MONEY_PAYABLE_FIELDS:
            parsed_value = parse_amount(text_value)
            if parsed_value > 0:
                row[field] = parsed_value
            continue
        row[field] = text_value.upper() if field == "qualified_invoice_number" else text_value
    return row


def ocr_audit_summary(row: dict[str, Any]) -> dict[str, Any]:
    draft = normalize_ocr_draft(row.get("ocr_draft") or {})
    extracted_fields = [key for key in ["vendor_name", "invoice_number", "invoice_date", "payment_due_date", "qualified_invoice_number", "total_amount", "tax_amount", "amount_excluding_tax", "bank_account_text"] if draft.get(key) not in (None, "", "unknown")]
    attachment = row.get("attachment") or {}
    return {
        "payable_id": row.get("payable_id", ""),
        "payable_no": row.get("payable_no", ""),
        "attachment": attachment.get("original_filename") or attachment.get("stored_filename", ""),
        "ocr_status": row.get("ocr_status", "not_run"),
        "fields_extracted": extracted_fields,
        "requires_manual_review": draft.get("requires_manual_review", True),
        "confidence_notes": draft.get("confidence_notes", [])[:5],
    }


def update_row_from_payable_form(row: dict[str, Any], fields: dict[str, str], lang: str) -> dict[str, Any]:
    supplier_mode = fields.get("supplier_record_mode", str(row.get("supplier_record_mode", "standard_vendor"))).strip() or "standard_vendor"
    if supplier_mode not in SUPPLIER_RECORD_MODES:
        supplier_mode = "standard_vendor"
    vendor_id = fields.get("vendor_id", "").strip()
    vendor_name = fields.get("vendor_name_snapshot", "").strip()
    selected_vendor = find_by_id(active_vendors(), "vendor_id", vendor_id) if vendor_id else None
    snapshot_values: dict[str, str] = {}
    if supplier_mode == "one_time_vendor":
        one_time_vendor = selected_vendor if selected_vendor and str(selected_vendor.get("supplier_record_mode", "standard_vendor")) == "one_time_vendor" else one_time_vendor_master(lang)
        if one_time_vendor:
            vendor_id = str(one_time_vendor.get("vendor_id", ""))
            snapshot_values = vendor_snapshot(one_time_vendor, lang)
            vendor_name = snapshot_values["vendor_name_snapshot"]
        else:
            vendor_id = ""
            snapshot_values = virtual_one_time_vendor_snapshot()
            vendor_name = snapshot_values["vendor_name_snapshot"]
    elif selected_vendor:
        supplier_mode = "standard_vendor"
        snapshot_values = vendor_snapshot(selected_vendor, lang)
        vendor_name = snapshot_values["vendor_name_snapshot"]
    row.update(
        {
            "supplier_record_mode": supplier_mode,
            "vendor_id": vendor_id,
            "vendor_name_snapshot": vendor_name,
            "vendor_code_snapshot": snapshot_values.get("vendor_code_snapshot", row.get("vendor_code_snapshot", "")),
            "qualified_invoice_number_snapshot": snapshot_values.get("qualified_invoice_number_snapshot", row.get("qualified_invoice_number_snapshot", "")),
            "payment_terms_snapshot": snapshot_values.get("payment_terms_snapshot", row.get("payment_terms_snapshot", "")),
            "supplier_record_mode_snapshot": snapshot_values.get("supplier_record_mode_snapshot", row.get("supplier_record_mode_snapshot", supplier_mode)),
            "bank_name_snapshot": snapshot_values.get("bank_name_snapshot", row.get("bank_name_snapshot", "")),
            "bank_branch_snapshot": snapshot_values.get("bank_branch_snapshot", row.get("bank_branch_snapshot", "")),
            "bank_account_number_masked_snapshot": snapshot_values.get("bank_account_number_masked_snapshot", row.get("bank_account_number_masked_snapshot", "")),
            "bank_account_holder_snapshot": snapshot_values.get("bank_account_holder_snapshot", row.get("bank_account_holder_snapshot", "")),
            "request_title": fields.get("request_title", "").strip(),
            "business_purpose": fields.get("business_purpose", "").strip(),
            "invoice_number": fields.get("invoice_number", "").strip(),
            "invoice_date": fields.get("invoice_date", "").strip(),
            "received_date": fields.get("received_date", "").strip(),
            "payment_due_date": fields.get("payment_due_date", "").strip(),
            "actual_payment_date": fields.get("actual_payment_date", "").strip(),
            "currency": fields.get("currency", "JPY").strip() or "JPY",
            "amount_excluding_tax": parse_amount(fields.get("amount_excluding_tax")),
            "tax_rate": fields.get("tax_rate", "unknown"),
            "tax_amount": parse_amount(fields.get("tax_amount")),
            "total_amount": parse_amount(fields.get("total_amount")),
            "withholding_tax_amount": parse_amount(fields.get("withholding_tax_amount")),
            "payment_method": fields.get("payment_method", "bank_transfer"),
            "expense_category": fields.get("expense_category", "other"),
            "related_client_name": fields.get("related_client_name", "").strip(),
            "related_project_name": fields.get("related_project_name", "").strip(),
            "department": fields.get("department", "").strip(),
            "qualified_invoice_number": fields.get("qualified_invoice_number", "").strip().upper(),
            "one_time_vendor_name": fields.get("one_time_vendor_name", "").strip(),
            "one_time_vendor_address": fields.get("one_time_vendor_address", "").strip(),
            "one_time_qualified_invoice_number": fields.get("one_time_qualified_invoice_number", "").strip().upper(),
            "one_time_bank_account_text": fields.get("one_time_bank_account_text", "").strip(),
            "one_time_reason": fields.get("one_time_reason", "").strip(),
            "one_time_reviewed": fields.get("one_time_reviewed") == "1",
            "finance_notes": fields.get("finance_notes", "").strip(),
        }
    )
    return row

def validate_payable(row: dict[str, Any], target_status: str) -> list[str]:
    errors: list[str] = []
    total = parse_amount(str(row.get("total_amount", "0")))
    tax = parse_amount(str(row.get("tax_amount", "0")))
    if tax < 0:
        errors.append("Tax amount cannot be negative.")
    if total and tax > total:
        errors.append("Tax amount cannot exceed total amount.")
    if target_status in {"Submitted", "Approved", "Scheduled", "Paid"}:
        supplier_mode = str(row.get("supplier_record_mode", "standard_vendor") or "standard_vendor")
        if supplier_mode == "one_time_vendor":
            if str(row.get("vendor_code_snapshot", "")).upper() != ONE_TIME_VENDOR_CODE and not row.get("vendor_id"):
                errors.append("One-time vendor code is required. Create/select the ONETIME vendor or keep the system ONETIME snapshot.")
            if not str(row.get("one_time_vendor_name", "")).strip():
                errors.append("Actual one-time vendor name is required.")
            if not str(row.get("one_time_reason", "")).strip():
                errors.append("One-time vendor reason is required.")
            if not row.get("one_time_reviewed"):
                errors.append("One-time vendor information must be reviewed before submit.")
        else:
            if not row.get("vendor_id"):
                errors.append("Standard vendor code is required. Select an active Vendor Master record or use One-time Vendor mode.")
        if not row.get("received_date"):
            errors.append("Received date is required.")
        if not row.get("payment_due_date"):
            errors.append("Payment due date is required.")
        if total <= 0:
            errors.append("Total amount must be greater than zero.")
    if target_status == "Paid" and not row.get("actual_payment_date"):
        errors.append("Actual payment date is required when marking paid.")
    return errors


class VendorPayablesHandler(BaseHTTPRequestHandler):
    server_version = "VendorPayables/0.1"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        messages = load_i18n(lang)
        try:
            if parsed.path == "/health":
                self.send_json({"status": "ok"})
            elif parsed.path == "/":
                self.send_html(self.render_dashboard(lang, messages, query))
            elif parsed.path == "/payables":
                self.send_html(self.render_payables(lang, messages, query))
            elif parsed.path == "/payables/new":
                self.send_html(self.render_payable_form(lang, messages, None, []))
            elif parsed.path == "/payables/edit":
                self.send_html(self.handle_payable_edit(lang, messages, query))
            elif parsed.path == "/payable":
                self.send_html(self.handle_payable_detail(lang, messages, query))
            elif parsed.path == "/payables/export.csv":
                self.send_payables_csv(query)
            elif parsed.path in {"/vendors", "/vendors/new", "/vendors/edit"}:
                self.redirect(MASTERDATA_VENDOR_URL)
            elif parsed.path == "/audit-logs":
                self.send_html(self.render_audit_logs(lang, messages, query))
            elif parsed.path == "/attachment":
                self.serve_attachment(query)
            else:
                self.send_error(404, "Not found")
        except Exception as exc:  # pragma: no cover - local MVP diagnostics
            self.send_error(500, str(exc))

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = get_lang(query)
        try:
            if parsed.path == "/payables/save":
                self.handle_payable_save(lang)
            elif parsed.path == "/payables/ocr":
                self.handle_payable_ocr(lang)
            elif parsed.path == "/payables/status":
                self.handle_payable_status(lang)
            elif parsed.path in {"/vendors/save", "/vendors/deactivate"}:
                self.redirect(MASTERDATA_VENDOR_URL)
            else:
                self.send_error(404, "Not found")
        except ValueError as exc:
            self.redirect(url("/payables", lang, error=str(exc)))
        except Exception as exc:  # pragma: no cover - local MVP diagnostics
            self.send_error(500, str(exc))

    def log_message(self, format: str, *args: Any) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {format % args}")

    def send_json(self, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_body: str, status: int = 200) -> None:
        body = html_body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def layout(self, lang: str, messages: dict[str, str], title: str, content: str) -> str:
        request_host = (self.headers.get("Host") or "127.0.0.1").split(":")[0]
        masterdata_vendor_url = f"http://{request_host}:8007/vendors"
        nav_items = [
            ("/", t(messages, "nav.dashboard", "Dashboard")),
            ("/payables", t(messages, "nav.payables", "Payables")),
            ("/payables/new", t(messages, "nav.new_payable", "New Payable")),
            (masterdata_vendor_url, t(messages, "nav.vendors", "Vendor Master")),
            ("/audit-logs", t(messages, "nav.audit_logs", "Audit Logs")),
        ]
        current_path = urlparse(self.path).path
        portal_nav = f'<a class="portal-link" href="{esc(PORTAL_BASE_URL)}" title="{esc(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}" aria-label="{esc(t(messages, "nav.portal_tooltip", "Return to TACAI Portal"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{esc(t(messages, "nav.portal", "Back to Portal"))}</a>'
        nav = portal_nav + "".join(
            f'<a class="{esc("active" if path == current_path else "")}" href="{esc(path if path.startswith("http") else url(path, lang))}">{esc(label)}</a>'
            for path, label in nav_items
        )
        langs = " ".join(
            f'<a class="lang {"active" if lang == code else ""}" href="?lang={code}">{esc(t(messages, f"language.{code}", code))}</a>'
            for code in LANGS
        )
        return f"""<!doctype html>
<html lang="{esc(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - VendorPayables</title>
  <style>
    :root {{ --blue:#0a6ed1; --dark:#1f2a44; --bg:#f5f7fa; --line:#d9e2ec; --text:#1f2937; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; color:var(--text); background:var(--bg); }}
    header {{ background:#fff; border-bottom:1px solid var(--line); padding:14px 24px; display:flex; align-items:center; justify-content:space-between; gap:16px; }}
    .brand h1 {{ margin:0; font-size:20px; color:var(--dark); }}
    .brand p {{ margin:2px 0 0; font-size:12px; color:#64748b; }}
    nav {{ background:#edf4fb; border-bottom:1px solid var(--line); padding:0 24px; display:flex; gap:4px; flex-wrap:wrap; }}
    nav a {{ color:#0f3557; text-decoration:none; padding:11px 14px; border-bottom:3px solid transparent; font-size:14px; }}
    nav a:hover {{ background:#fff; border-bottom-color:var(--blue); }}
    nav a.portal-link {{ display:inline-flex; align-items:center; gap:0.35rem; color:#0b4f8a; background:linear-gradient(180deg,#f8fbff 0%,#eaf4ff 100%); border:1px solid #9cc7f2; border-bottom-width:3px; box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 1px 2px rgba(15,23,42,.08); }}
    nav a.portal-link:hover {{ color:#064b86; border-color:#1f6feb; background:#ffffff; }}
    .portal-icon {{ font-size:1rem; line-height:1; }}
    main {{ padding:24px; max-width:1320px; margin:0 auto; }}
    .lang {{ color:#0a6ed1; text-decoration:none; padding:4px 8px; border-radius:12px; font-size:12px; }}
    .lang.active {{ background:#e7f0fb; font-weight:700; }}
    .page-title {{ display:flex; justify-content:space-between; align-items:center; gap:12px; margin-bottom:18px; }}
    .page-title h2 {{ margin:0; color:var(--dark); font-size:24px; }}
    .cards {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:14px; margin-bottom:20px; }}
    .card {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .card .label {{ color:#64748b; font-size:13px; }}
    .card .value {{ font-size:26px; font-weight:700; margin-top:8px; color:#0f3557; }}
    table {{ width:100%; border-collapse:collapse; background:#fff; border:1px solid var(--line); border-radius:10px; overflow:hidden; }}
    th, td {{ padding:10px 12px; border-bottom:1px solid #edf2f7; text-align:left; vertical-align:top; font-size:13px; }}
    th {{ background:#f8fafc; color:#475569; font-weight:700; }}
    tr:hover td {{ background:#fbfdff; }}
    .button, button {{ display:inline-block; border:0; background:var(--blue); color:#fff; padding:8px 12px; border-radius:6px; text-decoration:none; cursor:pointer; font-size:13px; }}
    .button.secondary, button.secondary {{ background:#64748b; }}
    .button.ghost, button.ghost {{ background:#fff; color:#0a6ed1; border:1px solid #b8d4f2; }}
    .button.danger, button.danger {{ background:#b91c1c; }}
    .filters, form.panel {{ background:#fff; border:1px solid var(--line); border-radius:10px; padding:16px; margin-bottom:18px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:14px; }}
    label {{ display:block; font-size:12px; color:#475569; margin-bottom:5px; font-weight:600; }}
    input, select, textarea {{ width:100%; padding:8px 10px; border:1px solid #cbd5e1; border-radius:6px; font:inherit; background:#fff; }}
    textarea {{ min-height:80px; }}
    .actions {{ display:flex; gap:8px; align-items:center; flex-wrap:wrap; margin-top:14px; }}
    .message {{ margin-bottom:14px; padding:10px 12px; border-radius:8px; border:1px solid #bae6fd; background:#e0f2fe; color:#075985; }}
    .message.error {{ border-color:#fecaca; background:#fee2e2; color:#991b1b; }}
    .status-badge {{ display:inline-block; padding:4px 8px; border-radius:999px; font-size:12px; font-weight:700; background:#e2e8f0; color:#334155; }}
    .status-submitted {{ background:#dbeafe; color:#1d4ed8; }}
    .status-approved {{ background:#dcfce7; color:#166534; }}
    .status-scheduled {{ background:#ede9fe; color:#6d28d9; }}
    .status-paid {{ background:#bbf7d0; color:#14532d; }}
    .status-rejected {{ background:#fee2e2; color:#991b1b; }}
    .status-cancelled {{ background:#e5e7eb; color:#374151; }}
    .status-draft-review, .status-warning {{ background:#fef3c7; color:#92400e; }}
    .status-confirmed {{ background:#dcfce7; color:#166534; }}
    .status-failed {{ background:#fee2e2; color:#991b1b; }}
    .ocr-hint {{ margin:5px 0 0; color:#0f766e; font-size:12px; }}
    .ocr-panel {{ margin-bottom:18px; }}
    .ocr-panel pre {{ white-space:pre-wrap; max-height:220px; overflow:auto; background:#f8fafc; border:1px solid var(--line); border-radius:8px; padding:10px; }}
    .muted {{ color:#64748b; font-size:13px; }}
    .detail-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(280px,1fr)); gap:14px; }}
    .kv {{ display:grid; grid-template-columns:150px 1fr; gap:8px; font-size:14px; padding:5px 0; border-bottom:1px solid #f1f5f9; }}
    .kv b {{ color:#475569; }}
  </style>
</head>
<body>
<header>
  <div class="brand"><h1>{esc(t(messages, "app.title", "VendorPayables"))}</h1><p>{esc(t(messages, "app.subtitle", "Supplier payment management"))}</p></div>
  <div>{langs}</div>
</header>
<nav>{nav}</nav>
<main>{content}</main>
</body>
</html>"""

    def flash_html(self, query: dict[str, list[str]]) -> str:
        if query.get("msg"):
            return f'<div class="message">{esc(query["msg"][0])}</div>'
        if query.get("error"):
            return f'<div class="message error">{esc(query["error"][0])}</div>'
        return ""

    def render_dashboard(self, lang: str, messages: dict[str, str], query: dict[str, list[str]]) -> str:
        rows = active_payables()
        today = today_iso()
        month = today[:7]
        open_rows = [r for r in rows if r.get("status") in ACTIVE_STATUSES]
        overdue = [r for r in open_rows if is_overdue(r)]
        due_month = [r for r in open_rows if str(r.get("payment_due_date", "")).startswith(month)]
        paid_month = [r for r in rows if r.get("status") == "Paid" and str(r.get("actual_payment_date", "")).startswith(month)]
        open_amount = sum(parse_amount(str(r.get("total_amount", "0"))) for r in open_rows)
        cards = [
            (t(messages, "dashboard.open_payables", "Open payables"), len(open_rows)),
            (t(messages, "dashboard.overdue", "Overdue"), len(overdue)),
            (t(messages, "dashboard.due_this_month", "Due this month"), len(due_month)),
            (t(messages, "dashboard.paid_this_month", "Paid this month"), len(paid_month)),
            (t(messages, "dashboard.open_amount", "Open amount"), f"¥{fmt_money(open_amount)}"),
        ]
        card_html = "".join(f'<div class="card"><div class="label">{esc(label)}</div><div class="value">{esc(value)}</div></div>' for label, value in cards)
        recent = sorted(rows, key=lambda r: str(r.get("updated_at", "")), reverse=True)[:8]
        table = self.payables_table(lang, messages, recent, compact=True)
        content = f"""
<div class="page-title"><h2>{esc(t(messages, 'nav.dashboard', 'Dashboard'))}</h2><a class="button" href="{url('/payables/new', lang)}">{esc(t(messages, 'action.new_payable', 'New Payable'))}</a></div>
{self.flash_html(query)}
<div class="cards">{card_html}</div>
<div class="card"><h3>{esc(t(messages, 'dashboard.recent_payables', 'Recent payables'))}</h3>{table}</div>
"""
        return self.layout(lang, messages, "Dashboard", content)

    def payables_table(self, lang: str, messages: dict[str, str], rows: list[dict[str, Any]], compact: bool = False) -> str:
        if not rows:
            return f'<p class="muted">{esc(t(messages, "payable.empty", "No payable records yet."))}</p>'
        body = []
        for row in rows:
            detail = url("/payable", lang, id=str(row.get("payable_id", "")))
            body.append(
                "<tr>"
                f"<td><a href=\"{detail}\">{esc(row.get('payable_no'))}</a></td>"
                f"<td>{esc(row.get('vendor_name_snapshot'))}</td>"
                f"<td>{esc(row.get('invoice_number'))}</td>"
                f"<td>{esc(row.get('invoice_date'))}</td>"
                f"<td>{esc(row.get('received_date'))}</td>"
                f"<td>{esc(row.get('payment_due_date'))}</td>"
                f"<td>{esc(row.get('actual_payment_date'))}</td>"
                f"<td>¥{fmt_money(row.get('total_amount'))}</td>"
                f"<td>{status_badge(str(row.get('status', 'Draft')))}</td>"
                f"<td><a class=\"button ghost\" href=\"{detail}\">{esc(t(messages, 'payable.detail_title', 'Detail'))}</a></td>"
                "</tr>"
            )
        return (
            "<table><thead><tr>"
            f"<th>{esc(t(messages, 'field.payable_no', 'Payable No.'))}</th>"
            f"<th>{esc(t(messages, 'field.vendor', 'Vendor'))}</th>"
            f"<th>{esc(t(messages, 'field.invoice_number', 'Invoice No.'))}</th>"
            f"<th>{esc(t(messages, 'field.invoice_date', 'Invoice Date'))}</th>"
            f"<th>{esc(t(messages, 'field.received_date', 'Received Date'))}</th>"
            f"<th>{esc(t(messages, 'field.payment_due_date', 'Due Date'))}</th>"
            f"<th>{esc(t(messages, 'field.actual_payment_date', 'Actual Payment Date'))}</th>"
            f"<th>{esc(t(messages, 'field.total_amount', 'Amount'))}</th>"
            f"<th>{esc(t(messages, 'field.status', 'Status'))}</th>"
            f"<th>{esc(t(messages, 'field.action', 'Action'))}</th>"
            "</tr></thead><tbody>" + "".join(body) + "</tbody></table>"
        )

    def render_payables(self, lang: str, messages: dict[str, str], query: dict[str, list[str]]) -> str:
        rows = active_payables()
        status_filter = (query.get("status") or [""])[0]
        vendor_filter = (query.get("vendor") or [""])[0].lower()
        month_filter = (query.get("month") or [""])[0]
        if status_filter:
            rows = [r for r in rows if r.get("status") == status_filter]
        if vendor_filter:
            rows = [r for r in rows if vendor_filter in str(r.get("vendor_name_snapshot", "")).lower()]
        if month_filter:
            rows = [r for r in rows if str(r.get("payment_due_date", "")).startswith(month_filter)]
        rows = sorted(rows, key=lambda r: (str(r.get("payment_due_date", "9999-99-99")), str(r.get("payable_no", ""))))
        filters = f"""
<form class="filters" method="get" action="/payables">
  <input type="hidden" name="lang" value="{esc(lang)}">
  <div class="grid">
    <div><label>{esc(t(messages, 'field.status', 'Status'))}</label><select name="status"><option value="">{esc(t(messages, 'filter.all', 'All'))}</option>{options_html(STATUSES, status_filter)}</select></div>
    <div><label>{esc(t(messages, 'field.vendor', 'Vendor'))}</label><input name="vendor" value="{esc((query.get('vendor') or [''])[0])}"></div>
    <div><label>Due Month</label><input type="month" name="month" value="{esc(month_filter)}"></div>
  </div>
  <div class="actions"><button>{esc(t(messages, 'action.filter', 'Filter'))}</button><a class="button ghost" href="{url('/payables', lang)}">{esc(t(messages, 'action.clear', 'Clear'))}</a></div>
</form>
"""
        content = f"""
<div class="page-title"><h2>{esc(t(messages, 'payable.list_title', 'Vendor payables'))}</h2><div><a class="button secondary" href="{url('/payables/export.csv', lang, status=status_filter, vendor=vendor_filter, month=month_filter)}">{esc(t(messages, 'action.export_csv', 'Export CSV'))}</a> <a class="button" href="{url('/payables/new', lang)}">{esc(t(messages, 'action.new_payable', 'New Payable'))}</a></div></div>
{self.flash_html(query)}
{filters}
{self.payables_table(lang, messages, rows)}
"""
        return self.layout(lang, messages, "Payables", content)

    def handle_payable_edit(self, lang: str, messages: dict[str, str], query: dict[str, list[str]]) -> str:
        payable_id = (query.get("id") or [""])[0]
        row = find_by_id(active_payables(), "payable_id", payable_id)
        if not row:
            return self.layout(lang, messages, "Not found", f'<div class="message error">{esc(t(messages, "error.not_found", "Record not found."))}</div>')
        return self.render_payable_form(lang, messages, row, [])

    def render_payable_form(self, lang: str, messages: dict[str, str], row: dict[str, Any] | None, errors: list[str]) -> str:
        row = dict(row or {})
        row["ocr_status"] = row.get("ocr_status") if row.get("ocr_status") in OCR_STATUSES else "not_run"
        row["ocr_draft"] = normalize_ocr_draft(row.get("ocr_draft") or {})
        vendors = active_vendors()
        title_key = "payable.edit_title" if row.get("payable_id") else "payable.new_title"
        error_html = "".join(f'<div class="message error">{esc(error)}</div>' for error in errors)
        attachment = row.get("attachment") or {}
        attachment_html = ""
        if attachment:
            attachment_html = f'<p class="muted">Current: <a href="/attachment?file={quote(str(attachment.get("stored_filename", "")))}">{esc(attachment.get("original_filename"))}</a></p>'
        ocr_panel = ocr_draft_review_html(row)
        ocr_review_control = ""
        if row.get("ocr_status") == "draft":
            ocr_review_control = (
                '<div style="margin-top:14px;">'
                '<label>OCR Review Confirmation / OCR確認</label>'
                '<label style="font-weight:normal;"><input type="checkbox" name="ocr_reviewed" value="1"> I reviewed and corrected all OCR-prefilled fields / OCR読取項目を確認・修正しました</label>'
                '<p class="muted">Draft can be saved without confirmation. Submit requires OCR review confirmation.</p>'
                '</div>'
            )
        supplier_mode = str(row.get("supplier_record_mode", "standard_vendor") or "standard_vendor")
        supplier_mode_options = "".join(f'<option value="{esc(mode)}"{" selected" if supplier_mode == mode else ""}>{esc(supplier_record_mode_label(mode))}</option>' for mode in SUPPLIER_RECORD_MODES)
        one_time_reason = str(row.get("one_time_reason", "") or "")
        one_time_reason_options = '<option value=""></option>' + "".join(f'<option value="{esc(reason)}"{" selected" if one_time_reason == reason else ""}>{esc(one_time_reason_label(reason))}</option>' for reason in ONE_TIME_VENDOR_REASONS)
        one_time_reviewed_checked = " checked" if row.get("one_time_reviewed") else ""
        content = f"""
<div class="page-title"><h2>{esc(t(messages, title_key, 'Payable'))}</h2><a class="button ghost" href="{url('/payables', lang)}">{esc(t(messages, 'action.back', 'Back'))}</a></div>
{error_html}
{ocr_panel}
<form class="panel" method="post" action="{url('/payables/save', lang)}" enctype="multipart/form-data">
  <input type="hidden" name="payable_id" value="{esc(row.get('payable_id', ''))}">
  <div class="grid">
    <div><label>Supplier Mode / 仕入先区分 / 供应商模式</label><select name="supplier_record_mode">{supplier_mode_options}</select><p class="muted">Use Standard Vendor for recurring suppliers; use One-time Vendor for temporary/spot payment requests.</p></div>
    <div><label>{esc(t(messages, 'field.vendor', 'Vendor'))}</label><select name="vendor_id">{vendor_options(vendors, str(row.get('vendor_id', '')), lang)}</select><p class="muted">{esc(t(messages, 'message.vendor_master_managed_in_masterdata', 'Vendor Master is maintained in Master Data Management.'))} For one-time mode, ONETIME code is used automatically if configured.</p></div>
    <div><label>{esc(t(messages, 'field.vendor_name', 'Vendor Name Snapshot'))}</label><input name="vendor_name_snapshot" value="{esc(row.get('vendor_name_snapshot', ''))}" readonly>{ocr_field_hint_html(row, 'vendor_name_snapshot')}</div>
    <div><label>{esc(t(messages, 'field.request_title', 'Request Title'))}</label><input name="request_title" value="{esc(row.get('request_title', ''))}"></div>
    <div><label>{esc(t(messages, 'field.invoice_number', 'Invoice No.'))}</label><input name="invoice_number" value="{esc(row.get('invoice_number', ''))}">{ocr_field_hint_html(row, 'invoice_number')}</div>
    <div><label>{esc(t(messages, 'field.invoice_date', 'Invoice Date'))}</label><input type="date" name="invoice_date" value="{esc(row.get('invoice_date', ''))}">{ocr_field_hint_html(row, 'invoice_date')}</div>
    <div><label>{esc(t(messages, 'field.received_date', 'Received Date'))}</label><input type="date" name="received_date" value="{esc(row.get('received_date', ''))}"></div>
    <div><label>{esc(t(messages, 'field.payment_due_date', 'Payment Due Date'))}</label><input type="date" name="payment_due_date" value="{esc(row.get('payment_due_date', ''))}">{ocr_field_hint_html(row, 'payment_due_date')}</div>
    <div><label>{esc(t(messages, 'field.actual_payment_date', 'Actual Payment Date'))}</label><input type="date" name="actual_payment_date" value="{esc(row.get('actual_payment_date', ''))}"></div>
    <div><label>{esc(t(messages, 'field.currency', 'Currency'))}</label><input name="currency" value="{esc(row.get('currency', 'JPY'))}">{ocr_field_hint_html(row, 'currency')}</div>
    <div><label>{esc(t(messages, 'field.amount_excluding_tax', 'Amount excl. Tax'))}</label><input name="amount_excluding_tax" value="{esc(row.get('amount_excluding_tax', ''))}">{ocr_field_hint_html(row, 'amount_excluding_tax')}</div>
    <div><label>{esc(t(messages, 'field.tax_rate', 'Tax Rate'))}</label><select name="tax_rate">{options_html(TAX_RATES, str(row.get('tax_rate', '10%')))}</select>{ocr_field_hint_html(row, 'tax_rate')}</div>
    <div><label>{esc(t(messages, 'field.tax_amount', 'Tax Amount'))}</label><input name="tax_amount" value="{esc(row.get('tax_amount', ''))}">{ocr_field_hint_html(row, 'tax_amount')}</div>
    <div><label>{esc(t(messages, 'field.total_amount', 'Total Amount'))}</label><input name="total_amount" value="{esc(row.get('total_amount', ''))}">{ocr_field_hint_html(row, 'total_amount')}</div>
    <div><label>{esc(t(messages, 'field.withholding_tax_amount', 'Withholding Tax'))}</label><input name="withholding_tax_amount" value="{esc(row.get('withholding_tax_amount', '0'))}"></div>
    <div><label>{esc(t(messages, 'field.payment_method', 'Payment Method'))}</label><select name="payment_method">{options_html(PAYMENT_METHODS, str(row.get('payment_method', 'bank_transfer')))}</select></div>
    <div><label>{esc(t(messages, 'field.expense_category', 'Expense Category'))}</label><select name="expense_category">{options_html(EXPENSE_CATEGORIES, str(row.get('expense_category', 'recruitment_media_fee')))}</select></div>
    <div><label>{esc(t(messages, 'field.related_client_name', 'Related Client'))}</label><input name="related_client_name" value="{esc(row.get('related_client_name', ''))}"></div>
    <div><label>{esc(t(messages, 'field.related_project_name', 'Related Project'))}</label><input name="related_project_name" value="{esc(row.get('related_project_name', ''))}"></div>
    <div><label>{esc(t(messages, 'field.department', 'Department'))}</label><input name="department" value="{esc(row.get('department', ''))}"></div>
    <div><label>{esc(t(messages, 'field.qualified_invoice_number', 'Qualified Invoice No.'))}</label><input name="qualified_invoice_number" value="{esc(row.get('qualified_invoice_number', ''))}">{ocr_field_hint_html(row, 'qualified_invoice_number')}</div>
    <div><label>Actual One-time Vendor Name / 一回限り実仕入先名</label><input name="one_time_vendor_name" value="{esc(row.get('one_time_vendor_name', ''))}"><p class="muted">Required only for One-time Vendor mode.</p>{ocr_field_hint_html({'ocr_status': row.get('ocr_status'), 'ocr_draft': row.get('ocr_draft')}, 'vendor_name_snapshot')}</div>
    <div><label>One-time Qualified Invoice No. / 一回限り登録番号</label><input name="one_time_qualified_invoice_number" value="{esc(row.get('one_time_qualified_invoice_number', ''))}"></div>
    <div><label>One-time Reason / 一回限り理由</label><select name="one_time_reason">{one_time_reason_options}</select></div>
  </div>
  <div style="margin-top:14px;"><label>One-time Vendor Address / 一回限り住所</label><textarea name="one_time_vendor_address">{esc(row.get('one_time_vendor_address', ''))}</textarea></div>
  <div style="margin-top:14px;"><label>One-time Bank Account Text / 一回限り振込先</label><textarea name="one_time_bank_account_text">{esc(row.get('one_time_bank_account_text', ''))}</textarea>{ocr_field_hint_html(row, 'finance_notes')}</div>
  <div style="margin-top:14px;"><label style="font-weight:normal;"><input type="checkbox" name="one_time_reviewed" value="1"{one_time_reviewed_checked}> I reviewed one-time vendor identity and payment information / 一回限り仕入先情報を確認しました</label></div>
  <div class="grid" style="margin-top:14px;">
    <div><label>{esc(t(messages, 'field.attachment', 'Attachment'))}</label><input type="file" name="attachment" accept=".jpg,.jpeg,.png,.pdf,.webp">{attachment_html}<p class="muted">{esc(t(messages, 'message.upload_hint', 'Upload invoice/request file.'))}</p></div>
    <div><label>OCR/AI</label><button name="submit_action" value="extract_ocr" class="secondary" formaction="{url('/payables/ocr', lang)}">Extract from invoice/request</button><p class="muted">OCR status: {ocr_status_badge(str(row.get('ocr_status', 'not_run')))}</p><p class="muted">Local OCR uses Tesseract first and macOS Vision fallback when available.</p></div>
  </div>
  <div style="margin-top:14px;"><label>{esc(t(messages, 'field.business_purpose', 'Business Purpose'))}</label><textarea name="business_purpose">{esc(row.get('business_purpose', ''))}</textarea></div>
  <div style="margin-top:14px;"><label>{esc(t(messages, 'field.finance_notes', 'Finance Notes'))}</label><textarea name="finance_notes">{esc(row.get('finance_notes', ''))}</textarea>{ocr_field_hint_html(row, 'finance_notes')}</div>
  {ocr_review_control}
  <div class="actions">
    <button name="submit_action" value="draft">{esc(t(messages, 'action.save_draft', 'Save Draft'))}</button>
    <button name="submit_action" value="submit" class="secondary">{esc(t(messages, 'action.submit', 'Submit'))}</button>
  </div>
</form>
"""
        return self.layout(lang, messages, t(messages, title_key, "Payable"), content)

    def handle_payable_ocr(self, lang: str) -> None:
        messages = load_i18n(lang)
        fields, files = parse_form(self)
        rows = load_json_array(PAYABLES_PATH)
        payable_id = fields.get("payable_id", "").strip()
        existing = find_by_id(rows, "payable_id", payable_id) if payable_id else None
        before = dict(existing) if existing else None
        now = now_iso()
        row = existing or {
            "payable_id": next_sequence(rows, "payable_id", "PAY-"),
            "payable_no": next_payable_no(rows),
            "created_by": ACTOR,
            "created_at": now,
            "record_status": "Active",
            "status": "Draft",
        }
        row = update_row_from_payable_form(row, fields, lang)
        row["status"] = row.get("status") or "Draft"
        row["updated_at"] = now
        if "attachment" in files:
            attachment = save_attachment(files["attachment"], str(row["payable_no"]))
            if attachment:
                row["attachment"] = attachment
        if not row.get("attachment"):
            raise ValueError("Please choose or keep an invoice/request attachment before extracting OCR fields.")
        append_audit_log("vendor_payables", str(row["payable_id"]), "ocr_started", before, {"attachment": (row.get("attachment") or {}).get("original_filename", "")})
        draft, ocr_status = build_vendor_invoice_ocr_draft(row.get("attachment") or {})
        row["ocr_status"] = ocr_status
        row["ocr_draft"] = draft
        row = apply_ocr_draft_to_payable_defaults(row)
        row = preserve_manual_payable_form_values(row, fields)
        validate_vendor_ocr_draft_record(row)
        if existing:
            rows = [row if r.get("payable_id") == row.get("payable_id") else r for r in rows]
            audit_action = "ocr_replaced" if before and before.get("ocr_status") in {"draft", "confirmed", "failed"} else "ocr_draft_created"
        else:
            rows.append(row)
            audit_action = "ocr_draft_created"
        save_json_array(PAYABLES_PATH, rows)
        if ocr_status == "draft":
            append_audit_log("vendor_payables", str(row["payable_id"]), audit_action, before, ocr_audit_summary(row))
        elif ocr_status == "not_available":
            append_audit_log("vendor_payables", str(row["payable_id"]), "ocr_not_available", before, ocr_audit_summary(row))
        else:
            append_audit_log("vendor_payables", str(row["payable_id"]), "ocr_failed", before, ocr_audit_summary(row))
        self.send_html(self.render_payable_form(lang, messages, row, []))

    def handle_payable_save(self, lang: str) -> None:
        fields, files = parse_form(self)
        rows = load_json_array(PAYABLES_PATH)
        payable_id = fields.get("payable_id", "").strip()
        existing = find_by_id(rows, "payable_id", payable_id) if payable_id else None
        before = dict(existing) if existing else None
        now = now_iso()
        target_status = "Submitted" if fields.get("submit_action") == "submit" else (existing or {}).get("status", "Draft")
        if fields.get("submit_action") == "draft" and target_status in {"Submitted", "Rejected"}:
            target_status = "Draft"
        row = existing or {
            "payable_id": next_sequence(rows, "payable_id", "PAY-"),
            "payable_no": next_payable_no(rows),
            "created_by": ACTOR,
            "created_at": now,
            "record_status": "Active",
        }
        previous_ocr_status = str(row.get("ocr_status", "not_run"))
        row["ocr_status"] = previous_ocr_status if previous_ocr_status in OCR_STATUSES else "not_run"
        row["ocr_draft"] = normalize_ocr_draft(row.get("ocr_draft") or {})
        if row["ocr_status"] == "draft" and target_status == "Submitted":
            if fields.get("ocr_reviewed") != "1":
                raise ValueError("Please review and confirm the OCR draft before submitting.")
            row["ocr_status"] = "confirmed"
        row = update_row_from_payable_form(row, fields, lang)
        row["status"] = target_status
        row["updated_at"] = now
        if target_status == "Submitted" and not row.get("submitted_at"):
            row["submitted_at"] = now
        errors = validate_payable(row, target_status)
        if errors:
            raise ValueError("; ".join(errors))
        if "attachment" in files:
            attachment = save_attachment(files["attachment"], str(row["payable_no"]))
            if attachment:
                row["attachment"] = attachment
        validate_vendor_ocr_draft_record(row)
        if existing:
            rows = [row if r.get("payable_id") == payable_id else r for r in rows]
            action = "update_payable"
        else:
            rows.append(row)
            action = "create_payable"
        if existing and records_business_equal(before, row):
            self.redirect(url("/payable", lang, id=str(row["payable_id"]), msg=no_change_message(str(row.get("payable_no") or row.get("payable_id") or ""))))
            return
        save_json_array(PAYABLES_PATH, rows)
        append_audit_log("vendor_payables", str(row["payable_id"]), action, before, row)
        if previous_ocr_status == "draft" and row.get("ocr_status") == "confirmed":
            append_audit_log("vendor_payables", str(row["payable_id"]), "ocr_confirmed", before, ocr_audit_summary(row))
        self.redirect(url("/payable", lang, id=str(row["payable_id"]), msg="saved"))

    def handle_payable_detail(self, lang: str, messages: dict[str, str], query: dict[str, list[str]]) -> str:
        payable_id = (query.get("id") or [""])[0]
        row = find_by_id(active_payables(), "payable_id", payable_id)
        if not row:
            return self.layout(lang, messages, "Not found", f'<div class="message error">{esc(t(messages, "error.not_found", "Record not found."))}</div>')
        fields = [
            ("field.payable_no", row.get("payable_no")),
            ("field.vendor_name", row.get("vendor_name_snapshot")),
            ("field.vendor_code", row.get("vendor_code_snapshot")),
            ("field.qualified_invoice_number", row.get("qualified_invoice_number_snapshot") or row.get("qualified_invoice_number")),
            ("field.payment_terms", row.get("payment_terms_snapshot")),
            ("field.invoice_number", row.get("invoice_number")),
            ("field.invoice_date", row.get("invoice_date")),
            ("field.received_date", row.get("received_date")),
            ("field.payment_due_date", row.get("payment_due_date")),
            ("field.actual_payment_date", row.get("actual_payment_date")),
            ("field.total_amount", f"¥{fmt_money(row.get('total_amount'))}"),
            ("field.tax_amount", f"¥{fmt_money(row.get('tax_amount'))}"),
            ("field.expense_category", row.get("expense_category")),
            ("field.related_client_name", row.get("related_client_name")),
            ("field.related_project_name", row.get("related_project_name")),
            ("field.department", row.get("department")),
            ("field.qualified_invoice_number", row.get("qualified_invoice_number")),
            ("field.finance_notes", row.get("finance_notes")),
            ("OCR status", row.get("ocr_status", "not_run")),
        ]
        kv_html = "".join(f'<div class="kv"><b>{esc(t(messages, key, key))}</b><span>{esc(value)}</span></div>' for key, value in fields)
        attachment = row.get("attachment") or {}
        attachment_html = '<p class="muted">No attachment.</p>'
        if attachment:
            attachment_html = f'<a href="/attachment?file={quote(str(attachment.get("stored_filename", "")))}">{esc(attachment.get("original_filename"))}</a> <span class="muted">({esc(attachment.get("content_type"))}, {esc(attachment.get("size_bytes"))} bytes)</span>'
        actions = self.status_actions(lang, messages, row)
        content = f"""
<div class="page-title"><h2>{esc(row.get('payable_no'))} {status_badge(str(row.get('status', 'Draft')))}</h2><div><a class="button ghost" href="{url('/payables', lang)}">{esc(t(messages, 'action.back', 'Back'))}</a> <a class="button" href="{url('/payables/edit', lang, id=str(row.get('payable_id')))}">{esc(t(messages, 'action.edit', 'Edit'))}</a></div></div>
{self.flash_html(query)}
<div class="detail-grid"><div class="card">{kv_html}</div><div class="card"><h3>{esc(t(messages, 'field.attachment', 'Attachment'))}</h3>{attachment_html}<h3>Workflow</h3>{actions}</div></div>
{ocr_draft_review_html(row)}
"""
        return self.layout(lang, messages, "Payable detail", content)

    def status_actions(self, lang: str, messages: dict[str, str], row: dict[str, Any]) -> str:
        status = row.get("status", "Draft")
        payable_id = esc(row.get("payable_id"))
        buttons: list[tuple[str, str, str]] = []
        if status == "Draft":
            buttons = [("submit", "action.submit", "") , ("cancel", "action.cancel", "danger")]
        elif status == "Submitted":
            buttons = [("approve", "action.approve", ""), ("reject", "action.reject", "danger"), ("cancel", "action.cancel", "danger")]
        elif status == "Rejected":
            buttons = [("draft", "action.save_draft", "secondary")]
        elif status == "Approved":
            buttons = [("schedule", "action.schedule", "secondary"), ("paid", "action.mark_paid", ""), ("cancel", "action.cancel", "danger")]
        elif status == "Scheduled":
            buttons = [("paid", "action.mark_paid", "")]
        if not buttons:
            return '<p class="muted">No available workflow actions.</p>'
        html_parts = []
        for action, label_key, cls in buttons:
            date_field = ""
            if action == "paid":
                date_field = f'<label>{esc(t(messages, "field.actual_payment_date", "Actual Payment Date"))}</label><input type="date" name="actual_payment_date" value="{esc(row.get("actual_payment_date") or today_iso())}">'
            elif action == "submit" and row.get("ocr_status") == "draft":
                date_field = '<label style="font-weight:normal;"><input type="checkbox" name="ocr_reviewed" value="1"> I reviewed and corrected OCR suggestions / OCR読取項目を確認・修正しました</label>'
            html_parts.append(
                f'<form method="post" action="{url("/payables/status", lang)}" style="margin-bottom:10px;">'
                f'<input type="hidden" name="payable_id" value="{payable_id}">'
                f'<input type="hidden" name="status_action" value="{action}">{date_field}'
                f'<button class="{cls}">{esc(t(messages, label_key, label_key))}</button></form>'
            )
        return "".join(html_parts)

    def handle_payable_status(self, lang: str) -> None:
        fields, _ = parse_form(self)
        payable_id = fields.get("payable_id", "")
        action = fields.get("status_action", "")
        rows = load_json_array(PAYABLES_PATH)
        row = find_by_id(rows, "payable_id", payable_id)
        if not row:
            raise ValueError("Record not found.")
        before = dict(row)
        current = row.get("status", "Draft")
        previous_ocr_status = str(row.get("ocr_status", "not_run"))
        mapping = {
            ("Draft", "submit"): "Submitted",
            ("Draft", "cancel"): "Cancelled",
            ("Submitted", "approve"): "Approved",
            ("Submitted", "reject"): "Rejected",
            ("Submitted", "cancel"): "Cancelled",
            ("Rejected", "draft"): "Draft",
            ("Approved", "schedule"): "Scheduled",
            ("Approved", "paid"): "Paid",
            ("Approved", "cancel"): "Cancelled",
            ("Scheduled", "paid"): "Paid",
        }
        target = mapping.get((current, action))
        if not target:
            raise ValueError("Invalid status transition.")
        row["status"] = target
        row["updated_at"] = now_iso()
        if target == "Submitted" and previous_ocr_status == "draft":
            if fields.get("ocr_reviewed") != "1":
                raise ValueError("Please review and confirm the OCR draft before submitting.")
            row["ocr_status"] = "confirmed"
        if target == "Submitted":
            row["submitted_at"] = now_iso()
        elif target == "Approved":
            row["approved_by"] = ACTOR
            row["approved_at"] = now_iso()
        elif target == "Scheduled":
            row["scheduled_at"] = now_iso()
        elif target == "Paid":
            row["actual_payment_date"] = fields.get("actual_payment_date", "") or row.get("actual_payment_date", "")
            row["paid_by"] = ACTOR
            row["paid_at"] = now_iso()
        elif target == "Cancelled":
            row["cancelled_at"] = now_iso()
        errors = validate_payable(row, target)
        if errors:
            raise ValueError("; ".join(errors))
        save_json_array(PAYABLES_PATH, rows)
        append_audit_log("vendor_payables", payable_id, f"status_{action}", before, row)
        if previous_ocr_status == "draft" and row.get("ocr_status") == "confirmed":
            append_audit_log("vendor_payables", payable_id, "ocr_confirmed", before, ocr_audit_summary(row))
        self.redirect(url("/payable", lang, id=payable_id, msg=target))

    def render_audit_logs(self, lang: str, messages: dict[str, str], query: dict[str, list[str]]) -> str:
        rows = sorted(load_json_array(AUDIT_LOGS_PATH), key=lambda r: str(r.get("timestamp", "")), reverse=True)[:100]
        body = "".join(
            "<tr>"
            f"<td>{esc(r.get('timestamp'))}</td><td>{esc(r.get('module'))}</td><td>{esc(r.get('record_id'))}</td>"
            f"<td>{esc(r.get('action'))}</td><td>{esc(r.get('user'))}</td>"
            "</tr>" for r in rows
        )
        table = "<table><thead><tr><th>Timestamp</th><th>Module</th><th>Record</th><th>Action</th><th>User</th></tr></thead><tbody>" + body + "</tbody></table>" if rows else '<p class="muted">No audit logs yet.</p>'
        content = f'<div class="page-title"><h2>{esc(t(messages, "audit.title", "Audit logs"))}</h2></div>{self.flash_html(query)}{table}'
        return self.layout(lang, messages, "Audit logs", content)

    def send_payables_csv(self, query: dict[str, list[str]]) -> None:
        rows = active_payables()
        status_filter = (query.get("status") or [""])[0]
        vendor_filter = (query.get("vendor") or [""])[0].lower()
        month_filter = (query.get("month") or [""])[0]
        if status_filter:
            rows = [r for r in rows if r.get("status") == status_filter]
        if vendor_filter:
            rows = [r for r in rows if vendor_filter in str(r.get("vendor_name_snapshot", "")).lower()]
        if month_filter:
            rows = [r for r in rows if str(r.get("payment_due_date", "")).startswith(month_filter)]
        output = StringIO()
        writer = csv.writer(output)
        columns = [
            "payable_no", "vendor_name_snapshot", "invoice_number", "invoice_date", "received_date",
            "payment_due_date", "actual_payment_date", "currency", "amount_excluding_tax", "tax_amount",
            "total_amount", "status", "payment_method", "expense_category", "qualified_invoice_number",
            "created_at", "approved_at", "paid_at",
        ]
        writer.writerow(columns)
        for row in rows:
            writer.writerow([row.get(col, "") for col in columns])
        body = output.getvalue().encode("utf-8-sig")
        exports = load_json_array(REPORT_EXPORTS_PATH)
        export_id = next_sequence(exports, "export_id", "EXP-")
        file_name = f"vendor_payables_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}.csv"
        exports.append(
            {
                "export_id": export_id,
                "report_type": "vendor_payables_csv",
                "file_name": file_name,
                "filter_json": {"status": status_filter, "vendor": vendor_filter, "month": month_filter},
                "row_count": len(rows),
                "total_amount": sum(parse_amount(str(r.get("total_amount", "0"))) for r in rows),
                "created_by": ACTOR,
                "created_at": now_iso(),
            }
        )
        save_json_array(REPORT_EXPORTS_PATH, exports)
        append_audit_log("vendor_payables", export_id, "export_csv", None, exports[-1])
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{file_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def serve_attachment(self, query: dict[str, list[str]]) -> None:
        stored = sanitize_filename((query.get("file") or [""])[0])
        path = ATTACHMENTS_DIR / stored
        if not stored or not path.exists() or not path.is_file():
            self.send_error(404, "Attachment not found")
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        self.send_header("Content-Disposition", f'inline; filename="{path.name}"')
        self.end_headers()
        with path.open("rb") as f:
            shutil.copyfileobj(f, self.wfile)


def run(host: str, port: int) -> None:
    ensure_storage()
    server = ThreadingHTTPServer((host, port), VendorPayablesHandler)
    print(f"VendorPayables running at http://{host}:{port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping VendorPayables.")
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run VendorPayables local MVP app.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8008)
    args = parser.parse_args()
    run(args.host, args.port)


if __name__ == "__main__":
    main()
