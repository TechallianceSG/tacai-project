#!/usr/bin/env python3
"""Customer Billing / Accounts Receivable local MVP web app.

Dependency-free Python standard-library implementation for customer invoice/request
note creation and manual payment tracking. Data is stored as UTF-8 JSON under
../database.
"""

from __future__ import annotations

import argparse
import cgi
import hashlib
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import unicodedata
import zipfile
from copy import deepcopy
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
I18N_DIR = ROOT_DIR / "i18n"

BILLINGS_PATH = DATABASE_DIR / "customer_billings.json"
CUSTOMERS_PATH = DATABASE_DIR / "customers.json"
COMPANY_PROFILE_PATH = DATABASE_DIR / "company_profile.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
REPORT_EXPORTS_PATH = DATABASE_DIR / "report_exports.json"
OCR_DRAFTS_PATH = DATABASE_DIR / "ocr_invoice_drafts.json"
STORAGE_DIR = ROOT_DIR / "storage"
OCR_UPLOAD_DIR = STORAGE_DIR / "ocr_uploads"

DEFAULT_LANG = "ja"
LANGS = ("ja", "en", "zh")
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009}


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


APP_BASE_URL = local_base_url(8009)
PORTAL_BASE_URL = (os.environ.get("PORTAL_PUBLIC_BASE_URL", local_base_url(8005)).strip() or local_base_url(8005)).rstrip("/")
USER_ADMIN_BASE_URL = local_base_url(8006)
USER_ADMIN_INTERNAL_BASE_URL = internal_base_url(8006)
MASTERDATA_BASE_URL = local_base_url(8007)
MASTERDATA_INTERNAL_BASE_URL = internal_base_url(8007)
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
REQUIRED_MODULE_PERMISSION = "client_revenue.access"
MODULE_NAME = "customerbilling"
DEFAULT_FINANCE_ACTOR = "Finance"

DOCUMENT_TYPES = ["invoice", "request_note"]
BUSINESS_TYPES = ["haken_dispatch", "recruitment_placement", "rpo", "other"]
TAX_RATES = ["10%", "8%", "0%", "mixed", "unknown"]
STATUSES = ["Draft", "Issued", "Sent", "Partially Paid", "Paid", "Cancelled"]
PAYMENT_METHODS = ["bank_transfer", "cash", "card", "other"]
ACTIVE_RECORD_STATUS = "Active"
OCR_MAX_UPLOAD_BYTES = 10 * 1024 * 1024
OCR_ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png", ".webp", ".docx", ".doc", ".rtf", ".txt", ".md", ".markdown"}
OCR_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
OCR_TEXT_EXTENSIONS = {".txt", ".md", ".markdown"}
OCR_WORD_EXTENSIONS = {".docx", ".doc", ".rtf"}

DEFAULT_COMPANY_PROFILE = {
    "company_name_ja": "TAC Japan",
    "company_name_en": "TAC Japan",
    "company_registration_number": "",
    "qualified_invoice_registration_number": "T0000000000000",
    "postal_code": "",
    "address_ja": "東京都",
    "address_en": "Tokyo, Japan",
    "phone": "",
    "email": "finance@example.com",
    "bank_name": "Bank Name",
    "bank_branch": "Branch Name",
    "bank_account_type": "普通",
    "bank_account_number": "0000000",
    "bank_account_name": "TAC JAPAN",
    "default_tax_rate": "10%",
    "default_payment_terms_days": 30,
}

TRANSLATIONS = {
    "ja": {
        "app.title": "Customer Billing",
        "app.subtitle": "顧客請求・売掛金管理",
        "nav.dashboard": "ダッシュボード",
        "nav.billings": "請求一覧",
        "nav.new_billing": "新規請求",
        "nav.customers": "顧客マスタ",
        "nav.reports": "レポート",
        "nav.audit": "監査ログ",
        "nav.portal": "ポータルへ戻る",
        "nav.portal_tooltip": "TACAIポータルへ戻る",
        "action.save": "保存",
        "action.cancel": "キャンセル",
        "action.copy": "コピー作成",
        "action.issue": "発行",
        "action.sent": "送付済みにする",
        "action.payment": "入金登録",
        "label.customer": "顧客",
        "label.status": "ステータス",
        "label.language": "言語",
        "label.business_type": "業務区分",
        "label.document_type": "書類区分",
        "label.issue_date": "発行日",
        "label.due_date": "支払期限",
        "label.total": "税込合計",
        "label.paid": "入金済",
        "label.balance": "残高",
        "label.tax": "消費税",
        "label.subtotal": "小計",
        "message.saved": "保存しました。",
    },
    "en": {
        "app.title": "Customer Billing",
        "app.subtitle": "Billing & Accounts Receivable",
        "nav.dashboard": "Dashboard",
        "nav.billings": "Billing List",
        "nav.new_billing": "New Billing",
        "nav.customers": "Customers",
        "nav.reports": "Reports",
        "nav.audit": "Audit Logs",
        "nav.portal": "Back to Portal",
        "nav.portal_tooltip": "Return to TACAI Portal",
        "action.save": "Save",
        "action.cancel": "Cancel",
        "action.copy": "Copy",
        "action.issue": "Issue",
        "action.sent": "Mark Sent",
        "action.payment": "Register Payment",
        "label.customer": "Customer",
        "label.status": "Status",
        "label.language": "Language",
        "label.business_type": "Business Type",
        "label.document_type": "Document Type",
        "label.issue_date": "Issue Date",
        "label.due_date": "Due Date",
        "label.total": "Total incl. tax",
        "label.paid": "Paid",
        "label.balance": "Balance",
        "label.tax": "Tax",
        "label.subtotal": "Subtotal",
        "message.saved": "Saved.",
    },
    "zh": {
        "app.title": "Customer Billing",
        "app.subtitle": "客户请款与应收账款管理",
        "nav.dashboard": "仪表盘",
        "nav.billings": "请款列表",
        "nav.new_billing": "新建请款",
        "nav.customers": "客户主数据",
        "nav.reports": "报表",
        "nav.audit": "审计日志",
        "nav.portal": "返回 Portal",
        "nav.portal_tooltip": "返回 TACAI 主 Portal",
        "action.save": "保存",
        "action.cancel": "取消",
        "action.copy": "复制",
        "action.issue": "发行",
        "action.sent": "标记已发送",
        "action.payment": "登记回款",
        "label.customer": "客户",
        "label.status": "状态",
        "label.language": "语言",
        "label.business_type": "业务类型",
        "label.document_type": "单据类型",
        "label.issue_date": "开票日期",
        "label.due_date": "付款期限",
        "label.total": "含税合计",
        "label.paid": "已回款",
        "label.balance": "未回款",
        "label.tax": "消费税",
        "label.subtotal": "小计",
        "message.saved": "已保存。",
    },
}


def ensure_storage() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    I18N_DIR.mkdir(parents=True, exist_ok=True)
    OCR_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for path in [BILLINGS_PATH, CUSTOMERS_PATH, AUDIT_LOGS_PATH, REPORT_EXPORTS_PATH, OCR_DRAFTS_PATH]:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")
    if not COMPANY_PROFILE_PATH.exists():
        COMPANY_PROFILE_PATH.write_text(json.dumps(DEFAULT_COMPANY_PROFILE, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def parse_date(value: str | None) -> date | None:
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        return None


def add_days(value: str | None, days: int) -> str:
    base = parse_date(value) or datetime.now(timezone.utc).date()
    return (base + timedelta(days=days)).isoformat()


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


def load_json_object(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return dict(default or {})
    data = json.loads(text)
    return data if isinstance(data, dict) else dict(default or {})


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def t(lang: str, key: str, default: str | None = None) -> str:
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).get(key, default or key)


def get_lang(query: dict[str, list[str]]) -> str:
    lang = (query.get("lang") or [DEFAULT_LANG])[0]
    return lang if lang in LANGS else DEFAULT_LANG


def with_lang(path: str, lang: str, **params: str) -> str:
    query = {"lang": lang}
    query.update({k: v for k, v in params.items() if v is not None})
    return f"{path}?{urlencode(query)}"


def parse_amount(value: str | None) -> int:
    raw = (value or "").replace(",", "").strip()
    if not raw:
        return 0
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if re.fullmatch(r"-?\d+\.0+", raw):
        return int(Decimal(raw))
    return 0


def parse_decimal(value: str | None) -> Decimal:
    raw = (value or "").replace(",", "").strip()
    if not raw:
        return Decimal("0")
    try:
        return Decimal(raw)
    except InvalidOperation:
        return Decimal("0")


def money(value: Any) -> str:
    try:
        return f"{int(value or 0):,}"
    except (TypeError, ValueError):
        return esc(value)


def tax_rate_decimal(tax_rate: str) -> Decimal:
    if tax_rate == "10%":
        return Decimal("0.10")
    if tax_rate == "8%":
        return Decimal("0.08")
    return Decimal("0")


def round_yen(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def next_sequence(rows: list[dict[str, Any]], key: str, prefix: str) -> str:
    max_num = 0
    pattern = re.compile(rf"^{re.escape(prefix)}(\d+)$")
    for row in rows:
        value = str(row.get(key, ""))
        match = pattern.match(value)
        if match:
            max_num = max(max_num, int(match.group(1)))
    return f"{prefix}{max_num + 1:04d}"


def next_customer_id(rows: list[dict[str, Any]]) -> str:
    return next_sequence(rows, "customer_id", "CUS-")


def next_payment_id(payments: list[dict[str, Any]]) -> str:
    return next_sequence(payments, "payment_id", "PAY-")


def next_history_id(history: list[dict[str, Any]]) -> str:
    return next_sequence(history, "history_id", "HIS-")


def next_attachment_id(attachments: list[dict[str, Any]]) -> str:
    return next_sequence(attachments, "attachment_id", "ATT-")


def next_billing_id(rows: list[dict[str, Any]]) -> str:
    return next_sequence(rows, "billing_id", "CBR-")


def next_billing_no(rows: list[dict[str, Any]]) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"CB-{year}-"
    max_num = 0
    for row in rows:
        value = str(row.get("billing_no", ""))
        if value.startswith(prefix):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


def next_ocr_draft_id(rows: list[dict[str, Any]]) -> str:
    year = datetime.now(timezone.utc).year
    prefix = f"OCR-{year}-"
    max_num = 0
    for row in rows:
        value = str(row.get("ocr_draft_id", ""))
        if value.startswith(prefix):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


def safe_upload_filename(filename: str) -> str:
    base = Path(filename or "invoice").name.strip() or "invoice"
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(base).stem).strip("._") or "invoice"
    suffix = Path(base).suffix.lower()
    return f"{stem}{suffix}"


def relative_to_root(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT_DIR.resolve()))
    except ValueError:
        return path.name


def attachment_from_ocr_source(source_file: dict[str, Any], draft_id: str) -> dict[str, Any]:
    attachment = {
        "attachment_id": "ATT-001",
        "attachment_type": "source_invoice_scan",
        "source": "ocr_import",
        "original_filename": source_file.get("original_filename", ""),
        "stored_filename": source_file.get("stored_filename", ""),
        "relative_path": source_file.get("relative_path", ""),
        "content_type": source_file.get("content_type", "application/octet-stream"),
        "size_bytes": source_file.get("size_bytes", 0),
        "sha256": source_file.get("sha256", ""),
        "uploaded_at": source_file.get("uploaded_at", ""),
        "uploaded_by": source_file.get("uploaded_by", ""),
        "linked_from_ocr_draft_id": draft_id,
        "linked_at": now_iso(),
    }
    return attachment


def attachment_file_path(attachment: dict[str, Any]) -> Path | None:
    relative_path = str(attachment.get("relative_path", "")).strip()
    if not relative_path:
        return None
    resolved = (ROOT_DIR / relative_path).resolve()
    allowed_root = OCR_UPLOAD_DIR.resolve()
    if resolved != allowed_root and allowed_root not in resolved.parents:
        return None
    return resolved


def normalize_ocr_text(text: str) -> str:
    return unicodedata.normalize("NFKC", text or "").replace("\r\n", "\n").replace("\r", "\n")


def decode_text_bytes(data: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp932", "shift_jis", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def read_docx_text(path: Path) -> str:
    with zipfile.ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ElementTree.fromstring(xml)
    chunks = [node.text or "" for node in root.iter() if node.tag.endswith("}t")]
    return "\n".join(chunk for chunk in chunks if chunk.strip())


def run_command_text(command: list[str], timeout: int = 20) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=False)
    if result.returncode != 0:
        return ""
    return result.stdout or ""


def run_macos_vision_ocr(path: Path) -> str:
    script = ROOT_DIR.parent / "TAC-reimbursement" / "backend" / "macos_vision_ocr.swift"
    if not script.exists() or not shutil.which("swift"):
        return ""
    return run_command_text(["swift", str(script), str(path)], timeout=45)


def extract_text_from_document(path: Path, extension: str) -> tuple[str, list[str], str]:
    warnings: list[str] = []
    engine = ""
    text = ""
    if extension in OCR_TEXT_EXTENSIONS:
        text = decode_text_bytes(path.read_bytes())
        engine = "text_decode"
    elif extension == ".docx":
        try:
            text = read_docx_text(path)
            engine = "docx_xml"
        except (KeyError, zipfile.BadZipFile, ElementTree.ParseError):
            warnings.append("DOCX text extraction failed; please review manually.")
    elif extension in {".doc", ".rtf"}:
        if shutil.which("textutil"):
            text = run_command_text(["textutil", "-convert", "txt", "-stdout", str(path)], timeout=20)
            engine = "textutil"
        else:
            warnings.append("macOS textutil is unavailable for Word/RTF extraction.")
    elif extension == ".pdf":
        if shutil.which("pdftotext"):
            text = run_command_text(["pdftotext", "-layout", str(path), "-"], timeout=30)
            engine = "pdftotext"
        if not text.strip():
            text = run_macos_vision_ocr(path)
            engine = "macos_vision" if text.strip() else engine
        if not text.strip():
            warnings.append("PDF text/OCR extraction was unavailable or returned no text.")
    elif extension in OCR_IMAGE_EXTENSIONS:
        if shutil.which("tesseract"):
            text = run_command_text(["tesseract", str(path), "stdout", "-l", "jpn+eng", "--psm", "6"], timeout=45)
            engine = "tesseract"
        if not text.strip():
            text = run_macos_vision_ocr(path)
            engine = "macos_vision" if text.strip() else engine
        if not text.strip():
            warnings.append("Image OCR engine is unavailable or returned no text.")
    else:
        warnings.append("Unsupported source document type.")
    text = normalize_ocr_text(text)
    if not text.strip():
        warnings.append("No extractable text was found; manual entry is required.")
    return text, warnings, engine or "not_available"


def first_match(patterns: list[str], text: str, flags: int = re.IGNORECASE) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags)
        if match:
            return (match.group(1) or "").strip()
    return ""


def normalize_date_text(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    match = re.search(r"(20\d{2}|19\d{2})[年/.-]\s*(\d{1,2})[月/.-]\s*(\d{1,2})", raw)
    if not match:
        return ""
    year, month, day = match.groups()
    try:
        return date(int(year), int(month), int(day)).isoformat()
    except ValueError:
        return ""


def is_invoice_number_candidate(value: str) -> bool:
    raw = value.strip().strip("()[]{}<>.,:;|」』）")
    if not raw or re.fullmatch(r"T\d{13}", raw, re.IGNORECASE):
        return False
    if normalize_date_text(raw):
        return False
    return bool(re.fullmatch(r"(?=.*[A-Za-z])(?=.*\d)[A-Za-z0-9][A-Za-z0-9._/-]{2,}", raw))


def ocr_lines(text: str) -> list[str]:
    normalized = normalize_ocr_text(text)
    return [re.sub(r"\s+", " ", line.strip()) for line in normalized.split("\n") if line.strip()]


def parse_ocr_amount(value: str | None) -> int:
    raw = unicodedata.normalize("NFKC", value or "").strip()
    if not raw or re.search(r"\d\s*%", raw):
        return 0
    raw = re.sub(r"(?i)j\s*p\s*[vy]?", "", raw)
    raw = raw.replace("円", "").replace("¥", "").replace("￥", "")
    raw = re.sub(r"(?<=\d)[\s_]+(?=\d)", "", raw)
    raw = re.sub(r"[^0-9,.-]", "", raw).strip(".,")
    if not raw or raw in {"-", ".", ","}:
        return 0
    negative = raw.startswith("-")
    raw = raw[1:] if negative else raw
    if not re.search(r"\d", raw):
        return 0
    if "," in raw or "." in raw:
        parts = re.split(r"[,.]", raw)
        if len(parts) > 1 and all(part.isdigit() for part in parts) and all(len(part) == 3 for part in parts[1:]):
            number = "".join(parts)
            return -int(number) if negative else int(number)
        if "," in raw:
            raw = raw.replace(",", "")
        try:
            value_decimal = Decimal(raw)
            return -round_yen(value_decimal) if negative else round_yen(value_decimal)
        except InvalidOperation:
            return 0
    if re.fullmatch(r"\d+", raw):
        return -int(raw) if negative else int(raw)
    return 0


def line_is_bank_or_contact_context(line: str) -> bool:
    return bool(re.search(r"(?i)(tel|phone|bank|branch|account|swift|bic|口座|支店|金融機関|銀行|電話|〒|郵便|code|コード)", line))


def extract_amounts_from_text(value: str, min_amount: int = 1000) -> list[int]:
    amounts: list[int] = []
    text = normalize_ocr_text(value)
    if not text or line_is_bank_or_contact_context(text):
        return amounts
    if re.search(r"\b(?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2}\b", text):
        text = re.sub(r"\b(?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2}\b", " ", text)
    pattern = re.compile(r"(?:[¥￥]\s*)?-?\d[\d,._\s]*\d(?:\s*(?:JPY|JPN|JPy|Jpv|円))?", re.IGNORECASE)
    for match in pattern.finditer(text):
        after = text[match.end(): match.end() + 2]
        before = text[max(0, match.start() - 4): match.start()]
        if "%" in after or re.search(r"Tax\s*$", before, re.IGNORECASE):
            continue
        amount = parse_ocr_amount(match.group(0))
        if abs(amount) >= min_amount:
            amounts.append(amount)
    return amounts


def extract_amount_candidates(text: str) -> list[int]:
    candidates: list[int] = []
    for line in ocr_lines(text):
        candidates.extend(extract_amounts_from_text(line))
    return candidates


def header_label_kind(line: str) -> str:
    raw = line.strip()
    if re.search(r"登録番号|Registration\s*(?:No\.?|Number)", raw, re.IGNORECASE):
        return "registration"
    if re.search(r"請求書番号|請求番号|Invoice\s*(?:No\.?|Number)|Request\s*No\.?|Document\s*No\.?,?", raw, re.IGNORECASE):
        return "invoice_no"
    if re.search(r"発行日|請求日付|請求日|Invoice\s*Date|Issue\s*Date", raw, re.IGNORECASE):
        return "issue_date"
    if re.search(r"支払期限|支払期日|支払予定日|お支払期限|Payment\s*Due\s*Date|Payment\s*Due|Due\s*Date", raw, re.IGNORECASE):
        return "due_date"
    return ""


def extract_header_label_value_block(lines: list[str]) -> dict[str, str]:
    labels: list[tuple[str, int]] = []
    for index, line in enumerate(lines[:60]):
        if labels and re.search(r"今回ご請求金額|Total\s*Amount|請求内容|Description", line, re.IGNORECASE):
            break
        kind = header_label_kind(line)
        if kind and (not labels or labels[-1][0] != kind):
            labels.append((kind, index))
    if not labels:
        return {}
    last_label_index = labels[-1][1]
    values: list[str] = []
    for line in lines[last_label_index + 1:last_label_index + 15]:
        if header_label_kind(line):
            continue
        registration = first_match([r"\b(T\d{13})\b"], line)
        if registration:
            values.append(registration)
        elif normalize_date_text(line):
            values.append(line)
        else:
            invoice_match = re.search(r"[A-Za-z0-9][A-Za-z0-9._/-]{2,}", line)
            if invoice_match and is_invoice_number_candidate(invoice_match.group(0)):
                values.append(invoice_match.group(0))
        if len(values) >= len(labels):
            break
    mapped: dict[str, str] = {}
    for (kind, _), value in zip(labels, values):
        if kind == "registration" and re.fullmatch(r"T\d{13}", value, re.IGNORECASE):
            mapped[kind] = value
        elif kind in {"issue_date", "due_date"}:
            normalized_date = normalize_date_text(value)
            if normalized_date:
                mapped[kind] = normalized_date
        elif kind == "invoice_no" and is_invoice_number_candidate(value):
            mapped[kind] = value
    return mapped


def find_value_after_label(lines: list[str], label_patterns: list[str], value_pattern: str, max_lookahead: int = 6) -> str:
    compiled_labels = [re.compile(pattern, re.IGNORECASE) for pattern in label_patterns]
    compiled_value = re.compile(value_pattern, re.IGNORECASE)
    for index, line in enumerate(lines):
        if not any(pattern.search(line) for pattern in compiled_labels):
            continue
        current_match = compiled_value.search(line)
        if current_match:
            return current_match.group(1) if current_match.groups() else current_match.group(0)
        for candidate in lines[index + 1:index + 1 + max_lookahead]:
            if header_label_kind(candidate):
                continue
            match = compiled_value.search(candidate)
            if match:
                return match.group(1) if match.groups() else match.group(0)
    return ""


def find_date_after_label(lines: list[str], label_patterns: list[str]) -> str:
    value = find_value_after_label(lines, label_patterns, r"((?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2})", 8)
    return normalize_date_text(value)


def find_invoice_number_after_label(lines: list[str]) -> str:
    value = find_value_after_label(
        lines,
        [r"請求書番号", r"請求番号", r"Invoice\s*(?:No\.?|Number)", r"Request\s*No\.?,?", r"Document\s*No\.?,?"],
        r"([A-Za-z0-9][A-Za-z0-9._/-]{2,})",
        8,
    )
    return value if is_invoice_number_candidate(value) else ""


def amount_after_label(lines: list[str], label_patterns: list[str], max_lookahead: int = 6) -> int:
    compiled = [re.compile(pattern, re.IGNORECASE) for pattern in label_patterns]
    stop_pattern = re.compile(r"備考|Notes|金融機関|Bank|Account|口座|支店|Branch", re.IGNORECASE)
    for index, line in enumerate(lines):
        if not any(pattern.search(line) for pattern in compiled):
            continue
        for candidate in lines[index:index + 1 + max_lookahead]:
            if candidate != line and stop_pattern.search(candidate):
                break
            amounts = extract_amounts_from_text(candidate)
            if amounts:
                return amounts[0]
    return 0


def extract_amount_table_triples(lines: list[str]) -> list[tuple[int, int, int]]:
    start = -1
    for index, line in enumerate(lines):
        if re.search(r"総計|Grand\s*Total", line, re.IGNORECASE):
            start = index
            break
    if start < 0:
        for index, line in enumerate(lines):
            window = " ".join(lines[index:index + 8])
            if re.search(r"Net\s*Amount|金額", window, re.IGNORECASE) and re.search(r"Tax|消費税", window, re.IGNORECASE) and re.search(r"Total|合計", window, re.IGNORECASE):
                start = index
                break
    if start < 0:
        return []
    amounts: list[int] = []
    for line in lines[start + 1:start + 40]:
        if re.search(r"備考|Notes|金融機関|Bank|Account|口座|支店|Branch", line, re.IGNORECASE):
            break
        amounts.extend(extract_amounts_from_text(line))
    triples: list[tuple[int, int, int]] = []
    for index in range(0, len(amounts) - 2, 3):
        net, tax, total = amounts[index], amounts[index + 1], amounts[index + 2]
        if net >= 0 and tax >= 0 and total >= 0 and abs((net + tax) - total) <= 2:
            triples.append((net, tax, total))
    return triples


def extract_amount_summary(lines: list[str], text: str) -> tuple[int, int, int, list[tuple[int, int, int]]]:
    triples = extract_amount_table_triples(lines)
    total = amount_after_label(lines, [r"今回ご請求金額", r"ご請求金額", r"請求金額", r"税込合計", r"合計金額", r"Total\s*Amount", r"Amount\s*Due"], 6)
    subtotal = 0
    tax = 0
    if triples:
        summary_net, summary_tax, summary_total = triples[-1]
        subtotal = summary_net
        tax = summary_tax
        if not total or abs(total - summary_total) <= 2:
            total = summary_total
    if not subtotal:
        subtotal = amount_after_label(lines, [r"小計", r"税抜", r"Subtotal", r"Sub\s*Total", r"Net\s*Amount"], 6)
    if not tax:
        candidate_tax = amount_after_label(lines, [r"消費税", r"税額", r"Tax"], 4)
        tax = 0 if candidate_tax in {8, 10} else candidate_tax
    if not total:
        candidates = extract_amount_candidates(text)
        total = max(candidates) if candidates else 0
    if total and tax and not subtotal:
        subtotal = max(total - tax, 0)
    if total and subtotal and not tax:
        tax = max(total - subtotal, 0)
    return subtotal, tax, total, triples


def company_like_line(line: str) -> bool:
    return bool(re.search(r"株式会社|有限会社|合同会社|㈱|Co\.?\s*,?\s*Ltd\.?|Ltd\.?|Inc\.?|Corporation|LLC", line, re.IGNORECASE))


def issuer_like_line(line: str) -> bool:
    normalized = re.sub(r"[^a-z0-9一-龯ぁ-んァ-ン]", "", line.lower())
    return any(token in normalized for token in ["techalliance", "talliance", "tacjapan", "テックアライアンス"])


def extract_customer_name(lines: list[str], text: str) -> tuple[str, bool]:
    explicit = first_match([
        r"(?:請求先|宛先|Bill\s*To|Customer)\s*[:：]?\s*([^\n]+)",
        r"([^\n]{2,80}(?:御中|様))",
    ], text)
    explicit = explicit.replace("御中", "").replace("様", "").strip()
    if explicit:
        return explicit, False
    for index, line in enumerate(lines):
        if not re.search(r"御請求書|請求書|\bINVOICE\b", line, re.IGNORECASE):
            continue
        for candidate in reversed(lines[max(0, index - 6):index]):
            candidate = candidate.strip(" :：")
            if company_like_line(candidate) and not issuer_like_line(candidate):
                return candidate, True
    return "", False


def extract_due_date_from_notes(text: str) -> str:
    value = first_match([
        r"((?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2})\s*までに",
        r"by\s*((?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2})",
    ], text)
    return normalize_date_text(value)


def extract_description_items(lines: list[str]) -> list[str]:
    start = -1
    for index, line in enumerate(lines):
        if re.search(r"請求内容|Description", line, re.IGNORECASE):
            start = index + 1
            break
    if start < 0:
        return []
    section: list[str] = []
    for line in lines[start:start + 80]:
        if re.search(r"総計|Grand\s*Total|備考|Notes", line, re.IGNORECASE):
            break
        if re.fullmatch(r"\(?\s*(Description|Net\s*Amount|Tax\s*\d*%?|Total)\s*\)?", line, re.IGNORECASE):
            continue
        if re.search(r"^(金額|消費税|合計)$", line):
            break
        section.append(line)
    items: list[str] = []
    current: list[str] = []
    for line in section:
        starts_new = bool(re.search(r"On\s*board\s*Date", line, re.IGNORECASE)) and bool(current)
        if starts_new:
            items.append(" ".join(current).strip())
            current = [line]
        else:
            current.append(line)
    if current:
        items.append(" ".join(current).strip())
    return [re.sub(r"\s+", " ", item)[:240] for item in items if item.strip()]


def extract_line_items_from_ocr(lines: list[str], subtotal: int, total: int, tax_rate: str, triples: list[tuple[int, int, int]]) -> list[dict[str, Any]]:
    descriptions = extract_description_items(lines)
    item_triples = triples[:-1] if len(triples) > 1 and sum(item[0] for item in triples[:-1]) == triples[-1][0] else triples
    line_items: list[dict[str, Any]] = []
    if descriptions and item_triples and len(descriptions) == len(item_triples):
        for description, (net, _tax, _line_total) in zip(descriptions, item_triples):
            line_items.append({
                "description": description,
                "quantity": "1",
                "unit": "式",
                "unit_price": net,
                "tax_rate": tax_rate,
                "memo": "Review OCR-extracted source document before issuing.",
            })
    line_amount = subtotal or (total if total else 0)
    if not line_items and line_amount:
        line_items.append({
            "description": descriptions[0] if len(descriptions) == 1 else "OCR imported invoice line",
            "quantity": "1",
            "unit": "式",
            "unit_price": line_amount,
            "tax_rate": tax_rate,
            "memo": "Review OCR-extracted source document before issuing.",
        })
    return line_items


def amount_near_label(labels: list[str], text: str) -> int:
    return amount_after_label(ocr_lines(text), labels)


def infer_tax_rate(subtotal: int, tax: int) -> str:
    if subtotal <= 0 or tax < 0:
        return "10%"
    ratio = Decimal(tax) / Decimal(subtotal)
    if Decimal("0.075") <= ratio <= Decimal("0.085"):
        return "8%"
    if Decimal("0.095") <= ratio <= Decimal("0.105"):
        return "10%"
    if tax == 0:
        return "0%"
    return "unknown"


def extract_invoice_fields(raw_text: str) -> dict[str, Any]:
    text = normalize_ocr_text(raw_text)
    lines = ocr_lines(text)
    header_values = extract_header_label_value_block(lines)
    original_invoice_no = header_values.get("invoice_no") or find_invoice_number_after_label(lines) or first_match([
        r"(?:請求書番号|請求番号|Invoice\s*(?:No\.?|Number)|No\.)\s*[:：#]?\s*([A-Za-z0-9._/-]+)",
        r"(?:Request\s*No\.?|Document\s*No\.?)\s*[:：#]?\s*([A-Za-z0-9._/-]+)",
    ], text)
    if not is_invoice_number_candidate(original_invoice_no):
        original_invoice_no = ""
    qualified_no = header_values.get("registration") or first_match([r"\b(T\d{13})\b"], text)
    issue_date = header_values.get("issue_date") or find_date_after_label(lines, [r"発行日", r"請求日付", r"請求日", r"Invoice\s*Date", r"Issue\s*Date"])
    if not issue_date:
        issue_date = normalize_date_text(first_match([r"((?:19|20)\d{2}[年/.-]\s*\d{1,2}[月/.-]\s*\d{1,2})"], text))
    due_date = header_values.get("due_date") or find_date_after_label(lines, [r"支払期限", r"支払期日", r"支払予定日", r"お支払期限", r"Payment\s*Due\s*Date", r"Payment\s*Due", r"Due\s*Date"])
    due_date = due_date or extract_due_date_from_notes(text)
    customer_name, customer_inferred = extract_customer_name(lines, text)
    subtotal, tax, total, triples = extract_amount_summary(lines, text)
    tax_rate = infer_tax_rate(subtotal, tax)
    line_items = extract_line_items_from_ocr(lines, subtotal, total, tax_rate, triples)
    warnings = []
    for label, value in [("customer", customer_name), ("issue_date", issue_date), ("total_amount", total)]:
        if not value:
            warnings.append(f"Missing or uncertain {label}; manual review required.")
    if customer_inferred:
        warnings.append("Customer was inferred from invoice title context; please confirm before saving.")
    if subtotal and tax and total and subtotal + tax != total:
        warnings.append("Extracted subtotal + tax does not match extracted total.")
    if triples and len(line_items) == 1 and len(triples) > 2:
        warnings.append("OCR amount table was detected but line descriptions could not be paired confidently.")
    return {
        "original_invoice_no": original_invoice_no,
        "document_type": "invoice",
        "issue_date": issue_date,
        "due_date": due_date,
        "customer_name": customer_name,
        "business_type": "other",
        "currency": "JPY",
        "qualified_invoice_registration_number": qualified_no,
        "subtotal_amount": subtotal,
        "tax_amount": tax,
        "total_amount": total,
        "tax_rate": tax_rate,
        "line_items": line_items,
        "invoice_note": "",
        "internal_memo": "OCR-assisted historical invoice import. Review all extracted fields before use.",
        "warnings": warnings,
    }

def normalize_match_text(value: Any) -> str:
    raw = unicodedata.normalize("NFKC", str(value or "")).lower()
    raw = re.sub(r"\bco\.?\s*,?\s*ltd\.?\b", "", raw)
    raw = re.sub(r"\b(?:ltd|inc|corp|corporation|llc|kk)\.?\b", "", raw)
    for phrase in ["株式会社", "有限会社", "合同会社", "㈱"]:
        raw = raw.replace(phrase, "")
    return re.sub(r"[\s　()（）.,，。・_-]+", "", raw)


def match_customer_from_extraction(extracted: dict[str, Any], customers: list[dict[str, Any]]) -> dict[str, Any]:
    target = normalize_match_text(extracted.get("customer_name", ""))
    if not target:
        return {"matched_customer_id": "", "match_method": "none", "confidence": "low", "candidate_customer_ids": []}
    candidates: list[str] = []
    for customer in customers:
        names = [customer.get("customer_name"), customer.get("customer_name_en"), customer.get("customer_name_zh"), customer.get("customer_code")]
        normalized_names = [normalize_match_text(name) for name in names if name]
        if target in normalized_names:
            return {"matched_customer_id": customer.get("customer_id", ""), "match_method": "exact_name", "confidence": "high", "candidate_customer_ids": [customer.get("customer_id", "")]}
        if any(target and (target in name or name in target) for name in normalized_names):
            candidates.append(str(customer.get("customer_id", "")))
    return {"matched_customer_id": candidates[0] if len(candidates) == 1 else "", "match_method": "normalized_name" if candidates else "none", "confidence": "medium" if len(candidates) == 1 else "low", "candidate_customer_ids": candidates[:5]}


def duplicate_check_for_ocr(extracted: dict[str, Any], file_hash: str, customer_id: str = "") -> dict[str, Any]:
    matches: list[str] = []
    invoice_no = str(extracted.get("original_invoice_no", "")).strip()
    issue_date = str(extracted.get("issue_date", "")).strip()
    total = int(extracted.get("total_amount", 0) or 0)
    for row in active_billings():
        if file_hash and row.get("source_file_hash") == file_hash:
            matches.append(str(row.get("billing_id", "")))
            continue
        if invoice_no and row.get("original_invoice_no") == invoice_no and (not customer_id or row.get("customer_id") == customer_id):
            matches.append(str(row.get("billing_id", "")))
            continue
        if customer_id and issue_date and total and row.get("customer_id") == customer_id and row.get("issue_date") == issue_date and int(row.get("total_amount", 0) or 0) == total:
            matches.append(str(row.get("billing_id", "")))
    unique = [item for index, item in enumerate(matches) if item and item not in matches[:index]]
    return {"status": "possible" if unique else "none", "matched_billing_ids": unique[:5]}


def validate_ocr_upload(filename: str, data: bytes) -> str:
    extension = Path(filename or "").suffix.lower()
    if extension not in OCR_ALLOWED_EXTENSIONS:
        raise ValueError("Unsupported OCR source file type. Use PDF, JPG, PNG, WEBP, Word, RTF, TXT, or MD.")
    if not data:
        raise ValueError("Uploaded OCR source file is empty.")
    if len(data) > OCR_MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded OCR source file exceeds the 10 MB limit.")
    return extension


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



def fetch_masterdata_json(path: str, session_id: str) -> Any:
    if not session_id:
        raise ValueError("User session is required to read Customer Master Data.")
    request = Request(
        f"{MASTERDATA_INTERNAL_BASE_URL}{path}",
        headers={"Cookie": f"{USER_ADMIN_SESSION_COOKIE}={session_id}"},
        method="GET",
    )
    try:
        with urlopen(request, timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 401:
            raise ValueError("Master Data rejected the current session. Please log in again through User Management.") from exc
        if exc.code == 403:
            raise ValueError("Missing Master Data customer access permission. Finance users need client_revenue.view.") from exc
        if exc.code == 404:
            return None
        raise ValueError("TACAI Master Data customer API returned an error.") from exc
    except (OSError, URLError, json.JSONDecodeError) as exc:
        raise ValueError("TACAI Master Data is unavailable. Please start Master Data on port 8007.") from exc


def normalize_master_customer(customer: dict[str, Any]) -> dict[str, Any]:
    status = str(customer.get("status", "active"))
    return {
        **customer,
        "record_status": "Active" if status == "active" else "Inactive",
        "customer_name": customer.get("customer_name") or customer.get("customer_name_ja") or customer.get("customer_name_en") or customer.get("customer_code", ""),
        "default_language": customer.get("default_language") or "ja",
        "default_payment_terms_days": customer.get("default_payment_terms_days") or 30,
        "default_tax_rate": customer.get("default_tax_rate") or "10%",
    }


def has_permission(user: dict[str, Any], permission_key: str) -> bool:
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return user.get("role") == "system_admin" or "system_admin" in roles or "*" in permissions or permission_key in permissions


def actor_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return DEFAULT_FINANCE_ACTOR
    for key in ("display_name", "username", "email", "user_id", "id"):
        value = str(user.get(key, "") or "").strip()
        if value:
            return value
    return DEFAULT_FINANCE_ACTOR


def append_audit_log(record_id: str, action: str, user: dict[str, Any] | None, before_value: Any, after_value: Any) -> None:
    logs = load_json_array(AUDIT_LOGS_PATH)
    logs.append(
        {
            "audit_id": next_sequence(logs, "audit_id", "AUD-"),
            "module": MODULE_NAME,
            "record_id": record_id,
            "action": action,
            "user": actor_from_user(user),
            "timestamp": now_iso(),
            "before_value": before_value,
            "after_value": after_value,
        }
    )
    save_json_array(AUDIT_LOGS_PATH, logs)


def history_entry(row: dict[str, Any], action: str, user: dict[str, Any] | None, before_status: str = "", after_status: str = "", summary: str = "") -> dict[str, Any]:
    history = row.get("history", []) if isinstance(row.get("history"), list) else []
    return {
        "history_id": next_history_id(history),
        "action": action,
        "actor": actor_from_user(user),
        "timestamp": now_iso(),
        "before_status": before_status,
        "after_status": after_status,
        "summary": summary,
    }


def find_by_id(rows: list[dict[str, Any]], key: str, value: str) -> dict[str, Any] | None:
    for row in rows:
        if str(row.get(key, "")) == value:
            return row
    return None


def active_customers() -> list[dict[str, Any]]:
    return [row for row in load_json_array(CUSTOMERS_PATH) if row.get("record_status", ACTIVE_RECORD_STATUS) == ACTIVE_RECORD_STATUS]


def active_billings() -> list[dict[str, Any]]:
    return [row for row in load_json_array(BILLINGS_PATH) if row.get("record_status", ACTIVE_RECORD_STATUS) == ACTIVE_RECORD_STATUS]


def active_ocr_drafts() -> list[dict[str, Any]]:
    return [row for row in load_json_array(OCR_DRAFTS_PATH) if row.get("record_status", ACTIVE_RECORD_STATUS) == ACTIVE_RECORD_STATUS]


def display_customer_name(customer: dict[str, Any], lang: str = DEFAULT_LANG) -> str:
    if lang == "en" and customer.get("customer_name_en"):
        return str(customer.get("customer_name_en"))
    if lang == "zh" and customer.get("customer_name_zh"):
        return str(customer.get("customer_name_zh"))
    return str(customer.get("customer_name") or customer.get("customer_name_en") or customer.get("customer_code") or "")


def customer_snapshot(customer: dict[str, Any], lang: str) -> dict[str, Any]:
    return {
        "customer_id": customer.get("customer_id", ""),
        "customer_code": customer.get("customer_code", ""),
        "customer_name": display_customer_name(customer, lang),
        "customer_name_ja": customer.get("customer_name", ""),
        "customer_name_en": customer.get("customer_name_en", ""),
        "customer_name_zh": customer.get("customer_name_zh", ""),
        "customer_registration_number": customer.get("customer_registration_number", ""),
        "billing_address": customer.get("billing_address", ""),
        "billing_contact_name": customer.get("billing_contact_name", ""),
        "billing_contact_email": customer.get("billing_contact_email", ""),
    }


def calculate_line(description: str, quantity_raw: str, unit: str, unit_price_raw: str, tax_rate: str, memo: str = "") -> dict[str, Any] | None:
    description = description.strip()
    quantity = parse_decimal(quantity_raw)
    unit_price = parse_amount(unit_price_raw)
    if not description and quantity == 0 and unit_price == 0:
        return None
    amount_ex_tax = round_yen(quantity * Decimal(unit_price))
    tax_amount = round_yen(Decimal(amount_ex_tax) * tax_rate_decimal(tax_rate))
    return {
        "line_id": "",
        "description": description,
        "quantity": str(quantity.normalize()) if quantity != quantity.to_integral() else str(int(quantity)),
        "unit": unit.strip() or "式",
        "unit_price": unit_price,
        "amount_excluding_tax": amount_ex_tax,
        "tax_rate": tax_rate if tax_rate in TAX_RATES else "10%",
        "tax_amount": tax_amount,
        "amount_including_tax": amount_ex_tax + tax_amount,
        "memo": memo.strip(),
    }


def calculate_totals(line_items: list[dict[str, Any]]) -> dict[str, int]:
    subtotal = sum(int(line.get("amount_excluding_tax", 0) or 0) for line in line_items)
    tax = sum(int(line.get("tax_amount", 0) or 0) for line in line_items)
    total = subtotal + tax
    return {"subtotal_amount": subtotal, "tax_amount": tax, "total_amount": total}


def payment_totals(payments: list[dict[str, Any]]) -> int:
    return sum(int(payment.get("amount", 0) or 0) for payment in payments if payment.get("record_status", ACTIVE_RECORD_STATUS) == ACTIVE_RECORD_STATUS)


def recalc_payment_status(row: dict[str, Any]) -> None:
    paid = payment_totals(row.get("payments", []) if isinstance(row.get("payments"), list) else [])
    total = int(row.get("total_amount", 0) or 0)
    row["paid_amount"] = paid
    row["balance_amount"] = max(total - paid, 0)
    if paid <= 0:
        row["payment_status"] = "unpaid"
    elif paid < total:
        row["payment_status"] = "partially_paid"
        if row.get("status") not in {"Cancelled", "Draft"}:
            row["status"] = "Partially Paid"
    else:
        row["payment_status"] = "paid"
        if row.get("status") != "Cancelled":
            row["status"] = "Paid"


def due_bucket(row: dict[str, Any]) -> str:
    if row.get("payment_status") == "paid" or row.get("status") in {"Paid", "Cancelled"}:
        return "paid_or_closed"
    due = parse_date(str(row.get("due_date", "")))
    if not due:
        return "unknown"
    days = (datetime.now(timezone.utc).date() - due).days
    if days <= 0:
        return "not_due"
    if days <= 30:
        return "overdue_1_30"
    if days <= 60:
        return "overdue_31_60"
    if days <= 90:
        return "overdue_61_90"
    return "overdue_90_plus"


def status_badge(status: str) -> str:
    safe = re.sub(r"[^a-z0-9_-]+", "-", status.lower())
    return f'<span class="status-badge status-{safe}">{esc(status)}</span>'


def options_html(options: list[str] | tuple[str, ...], selected: str = "", include_blank: bool = False) -> str:
    chunks = []
    if include_blank:
        chunks.append('<option value=""></option>')
    for option in options:
        sel = " selected" if option == selected else ""
        chunks.append(f'<option value="{esc(option)}"{sel}>{esc(option)}</option>')
    return "".join(chunks)


def customer_options(customers: list[dict[str, Any]], selected: str = "", lang: str = DEFAULT_LANG) -> str:
    chunks = ['<option value=""></option>']
    for customer in customers:
        customer_id = str(customer.get("customer_id", ""))
        label = f"{customer.get('customer_code', '')} {display_customer_name(customer, lang)}".strip()
        sel = " selected" if customer_id == selected else ""
        chunks.append(f'<option value="{esc(customer_id)}"{sel}>{esc(label)}</option>')
    return "".join(chunks)


def layout(lang: str, user: dict[str, Any] | None, title: str, active: str, body: str, message: str = "") -> str:
    nav_items = [
        ("dashboard", with_lang("/dashboard", lang), t(lang, "nav.dashboard")),
        ("billings", with_lang("/billings", lang), t(lang, "nav.billings")),
        ("new", with_lang("/billings/new", lang), t(lang, "nav.new_billing")),
        ("customers", with_lang("/customers", lang), t(lang, "nav.customers")),
        ("reports", with_lang("/reports", lang), t(lang, "nav.reports")),
        ("audit", with_lang("/audit", lang), t(lang, "nav.audit")),
    ]
    nav_html = "".join(
        f'<a class="nav-link {"active" if key == active else ""}" href="{esc(href)}">{esc(label)}</a>'
        for key, href, label in nav_items
    )
    portal_html = f'<a class="portal-link" href="{esc(PORTAL_BASE_URL)}" title="{esc(t(lang, "nav.portal_tooltip"))}" aria-label="{esc(t(lang, "nav.portal_tooltip"))}"><span class="portal-icon" aria-hidden="true">⌂</span>{esc(t(lang, "nav.portal"))}</a>'
    lang_links = "".join(
        f'<a class="button secondary {"active" if code == lang else ""}" href="?lang={code}">{code.upper()}</a>'
        for code in LANGS
    )
    user_label = actor_from_user(user)
    message_html = f'<section class="message-strip message-success" role="status">{esc(message)}</section>' if message else ""
    return f"""<!doctype html>
<html lang="{esc(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)} - Customer Billing</title>
  <style>
    :root {{ --navy:#14213d; --blue:#1f6feb; --bg:#f6f8fb; --card:#ffffff; --line:#d8dee9; --muted:#65758b; --green:#0f766e; --amber:#b45309; --red:#b91c1c; }}
    * {{ box-sizing:border-box; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:#17202a; }}
    header {{ background:var(--navy); color:white; padding:22px 32px; }}
    header .top {{ display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap; }}
    header h1 {{ margin:0 0 6px; font-size:1.75rem; }}
    header p {{ margin:0; color:#dbeafe; }}
    nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:10px 32px; background:white; border-bottom:1px solid var(--line); box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    nav a {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; color:#223548; background:#f7f9fb; text-decoration:none; border:1px solid transparent; padding:0 13px; border-radius:8px; font-size:.92rem; font-weight:760; line-height:1; white-space:nowrap; transition:background-color .16s ease,border-color .16s ease,color .16s ease,box-shadow .16s ease; }}
    nav a:hover {{ background:#eef6ff; border-color:#91c8f6; color:#0a6ed1; }}
    nav a.active {{ background:#e5f2fd; border-color:#0a6ed1; color:#0a6ed1; box-shadow:inset 0 -2px 0 #0a6ed1; }}
    nav a.portal-link {{ gap:0.35rem; color:#0b4f8a; background:linear-gradient(180deg,#f8fbff 0%,#eaf4ff 100%); border-color:#9cc7f2; box-shadow:inset 0 1px 0 rgba(255,255,255,.9),0 1px 2px rgba(15,23,42,.08); }}
    nav a.portal-link:hover {{ color:#064b86; border-color:#1f6feb; background:#ffffff; }}
    .portal-icon {{ font-size:1rem; line-height:1; }}
    main {{ max-width:1240px; margin:0 auto; padding:28px 20px 48px; }}
    .language-switcher {{ margin-left:auto; display:flex; align-items:center; gap:6px; flex:0 0 auto; }}
    .current-user-chip {{ display:grid; gap:2px; min-width:180px; padding:7px 10px; background:#fff; border:1px solid #d6e4f2; border-radius:12px; color:var(--navy); box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .current-user-chip strong {{ font-size:.9rem; }}
    .current-user-chip small {{ color:var(--muted); font-size:.76rem; }}
    .language-switcher .button {{ display:inline-flex; align-items:center; justify-content:center; min-height:30px; padding:0 10px; border-radius:8px; font-size:.8rem; line-height:1; }}
    .language-switcher .button.active {{ background:#e5f2fd; color:#0a6ed1; border-color:#0a6ed1; }}
    .page-title, .sap-page-header {{ background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%); border:1px solid var(--line); border-radius:16px; padding:20px; margin-bottom:18px; display:flex; justify-content:space-between; gap:16px; align-items:flex-start; flex-wrap:wrap; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .page-title h2, .sap-page-header h2, .object-header h2 {{ margin:0 0 8px; color:var(--navy); }}
    .page-title p, .sap-page-header p, .object-header p {{ margin:0; color:var(--muted); }}
    .eyebrow {{ margin:0 0 4px; color:var(--blue); font-size:.74rem; font-weight:850; letter-spacing:.055em; text-transform:uppercase; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:16px; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
    .card,.panel,.sap-section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .panel,.sap-section {{ margin-top:16px; }}
    .card h3,.panel h2,.panel h3,.sap-section h3 {{ margin-top:0; color:var(--navy); }}
    .section-header {{ margin:-18px -18px 16px; padding:14px 18px; border-bottom:1px solid var(--line); background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%); border-radius:14px 14px 0 0; }}
    .section-header h3 {{ margin:0; }}
    .metric {{ color:var(--muted); font-size:.82rem; font-weight:800; letter-spacing:.02em; text-transform:uppercase; }}
    .metric-value {{ font-size:1.7rem; font-weight:850; color:var(--navy); margin-top:6px; }}
    .muted {{ color:var(--muted); }} .good {{ color:var(--green); font-weight:800; }} .warn {{ color:var(--amber); font-weight:800; }} .danger-text,.error {{ color:var(--red); font-weight:800; }} .right,td.right,th.right {{ text-align:right; font-variant-numeric:tabular-nums; }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); border-radius:12px; overflow:hidden; }}
    th,td {{ border-bottom:1px solid var(--line); padding:10px 12px; text-align:left; vertical-align:top; }}
    th {{ background:#eef4ff; color:var(--navy); font-size:.82rem; text-transform:uppercase; letter-spacing:.025em; }}
    tr:last-child td {{ border-bottom:0; }}
    .table-wrap,.table-scroll,.wide {{ overflow-x:auto; border:1px solid #e5edf6; border-radius:12px; background:white; }}
    .table-wrap table,.table-scroll table,.wide table {{ border:0; border-radius:0; }}
    label {{ display:block; font-weight:800; margin:10px 0 6px; color:#334155; }}
    input,select,textarea {{ box-sizing:border-box; width:100%; border:1px solid #c8d1dc; border-radius:8px; padding:9px 10px; font:inherit; background:white; }}
    textarea {{ min-height:88px; resize:vertical; }}
    input:focus,select:focus,textarea:focus {{ outline:3px solid rgba(31,111,235,.18); border-color:var(--blue); }}
    .actions {{ margin:18px 0 0; display:flex; gap:10px; flex-wrap:wrap; align-items:center; }}
    .actions form {{ margin:0; display:inline-flex; }}
    .button,button {{ display:inline-flex; align-items:center; justify-content:center; min-height:38px; background:var(--blue); color:white; padding:9px 14px; border-radius:8px; border:1px solid transparent; text-decoration:none; font-weight:800; cursor:pointer; line-height:1; }}
    .button.secondary,button.secondary {{ background:#475569; color:white; }}
    .button.ghost,button.ghost {{ background:white; color:var(--navy); border-color:var(--line); }}
    .button.success,button.success {{ background:var(--green); }}
    .button.warning,button.warning {{ background:var(--amber); }}
    .button.danger,button.danger {{ background:var(--red); }}
    .sap-toolbar {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; justify-content:flex-end; padding-top:16px; border-top:1px solid var(--line); margin-top:18px; }}
    .sap-toolbar .spacer {{ margin-right:auto; }}
    .pill,.status-badge {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#ecfeff; color:#155e75; font-size:.78rem; font-weight:850; line-height:1.2; }}
    .status-draft {{ background:#f1f5f9; color:#334155; }}
    .status-issued,.status-sent {{ background:#dbeafe; color:#1d4ed8; }}
    .status-partially-paid {{ background:#fef3c7; color:#92400e; }}
    .status-paid {{ background:#dcfce7; color:#166534; }}
    .status-cancelled {{ background:#fee2e2; color:#991b1b; }}
    .notice,.message-strip {{ border-left:4px solid var(--blue); background:#eff6ff; padding:12px 14px; border-radius:8px; margin-bottom:16px; }}
    .message-warning {{ border-left-color:var(--amber); background:#fffbeb; }}
    .message-success,.message-strip.success {{ border-left-color:var(--green); background:#ecfdf5; color:#166534; }}
    .object-page {{ display:grid; gap:.85rem; }}
    .object-header {{ border:1px solid var(--line); border-radius:16px; background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%); box-shadow:0 1px 2px rgba(15,23,42,.04); padding:18px; display:grid; grid-template-columns:minmax(0,1fr) minmax(280px,.6fr); gap:1rem; align-items:start; }}
    .object-meta {{ display:grid; gap:.45rem; grid-template-columns:repeat(auto-fit,minmax(135px,1fr)); margin-top:12px; }}
    .meta-chip {{ border:1px solid #d6e4f2; border-radius:12px; background:rgba(255,255,255,.82); padding:9px 10px; min-width:0; }}
    .meta-chip-label {{ display:block; color:var(--muted); font-size:.68rem; font-weight:850; letter-spacing:.035em; text-transform:uppercase; margin-bottom:3px; }}
    .meta-chip-value {{ display:block; color:#0f172a; font-weight:800; overflow-wrap:anywhere; }}
    @media (max-width:720px) {{ header {{ padding:16px 18px; }} nav {{ flex-wrap:nowrap; overflow-x:auto; -webkit-overflow-scrolling:touch; align-items:center; gap:8px; padding:8px 12px; scrollbar-width:thin; }} nav a {{ flex:0 0 auto; min-height:34px; padding:0 12px; }} .language-switcher {{ margin-left:6px; flex-direction:row; }} .language-switcher .button {{ width:auto; min-height:30px; padding:0 9px; }} main {{ padding:18px 12px 36px; }} .grid,.form-grid {{ grid-template-columns:1fr; }} .object-header,.sap-page-header,.page-title {{ display:block; padding:16px; }} .actions,.sap-toolbar {{ justify-content:stretch; flex-direction:column; align-items:stretch; }} .actions .button,.actions button,.actions form,.sap-toolbar .button,.sap-toolbar button {{ width:100%; text-align:center; }} table {{ display:block; overflow-x:auto; min-width:760px; }} input,select,textarea {{ min-height:44px; }} }}
  </style>
</head>
<body>
<header><div class="top"><div><h1>{esc(t(lang, "app.title"))}</h1><p>{esc(t(lang, "app.subtitle"))}</p></div></div></header>
<nav>{portal_html}{nav_html}<span class="language-switcher"><span class="current-user-chip"><strong>👤 {esc(user_label)}</strong><small>Customer Billing</small></span>{lang_links}</span></nav>
<main>{message_html}{body}</main>
</body></html>"""


def dashboard_page(lang: str, user: dict[str, Any], customers: list[dict[str, Any]], message: str = "") -> str:
    billings = active_billings()
    total_ar = sum(int(row.get("balance_amount", 0) or 0) for row in billings if row.get("status") != "Cancelled")
    overdue = sum(int(row.get("balance_amount", 0) or 0) for row in billings if due_bucket(row).startswith("overdue"))
    issued = sum(1 for row in billings if row.get("status") in {"Issued", "Sent", "Partially Paid"})
    paid_this_month = sum(
        int(payment.get("amount", 0) or 0)
        for row in billings
        for payment in (row.get("payments", []) if isinstance(row.get("payments"), list) else [])
        if str(payment.get("payment_date", "")).startswith(today_iso()[:7])
    )
    recent = sorted(billings, key=lambda row: str(row.get("updated_at") or row.get("created_at") or ""), reverse=True)[:8]
    rows = "".join(billing_row_html(row, lang) for row in recent) or '<tr><td colspan="8" class="muted">No billing records yet.</td></tr>'
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Overview</div>
        <h2>{esc(t(lang, 'nav.dashboard'))}</h2>
        <p>Monitor receivables, recent billing activity, and payment status.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings/new', lang, mode='ocr'))}">Import Previous Invoice / OCR Assist</a><a class="button" href="{esc(with_lang('/billings/new', lang))}">{esc(t(lang, 'nav.new_billing'))}</a></div>
    </section>
    <div class="grid">
      <div class="card"><div class="metric">Customers</div><div class="metric-value">{len(customers)}</div><p class="muted">Active customer master records</p></div>
      <div class="card"><div class="metric">Active receivables</div><div class="metric-value">¥{money(total_ar)}</div><p class="muted">Outstanding customer balance</p></div>
      <div class="card"><div class="metric">Overdue balance</div><div class="metric-value danger-text">¥{money(overdue)}</div><p class="muted">Needs collection follow-up</p></div>
      <div class="card"><div class="metric">Issued / open</div><div class="metric-value">{issued}</div><p class="muted">Issued, sent, or partially paid</p></div>
      <div class="card"><div class="metric">Paid this month</div><div class="metric-value good">¥{money(paid_this_month)}</div><p class="muted">Registered payment total</p></div>
    </div>
    <section class="panel wide"><div class="section-header"><div class="eyebrow">Activity</div><h3>Recent billings</h3></div><div class="table-scroll"><table>{billing_table_head()}<tbody>{rows}</tbody></table></div></section>
    """
    return layout(lang, user, "Dashboard", "dashboard", body, message)


def billing_table_head() -> str:
    return """<thead><tr><th>No.</th><th>Customer</th><th>Type</th><th>Status</th><th>Issue</th><th>Due</th><th class="right">Total</th><th class="right">Balance</th></tr></thead>"""


def billing_row_html(row: dict[str, Any], lang: str) -> str:
    href = with_lang("/billings/detail", lang, id=str(row.get("billing_id", "")))
    return f"""<tr>
      <td><a href="{esc(href)}">{esc(row.get('billing_no', ''))}</a></td>
      <td>{esc(row.get('customer_name_snapshot', ''))}</td>
      <td>{esc(row.get('business_type', ''))}</td>
      <td>{status_badge(str(row.get('status', 'Draft')))}</td>
      <td>{esc(row.get('issue_date', ''))}</td>
      <td>{esc(row.get('due_date', ''))}</td>
      <td class="right">¥{money(row.get('total_amount'))}</td>
      <td class="right">¥{money(row.get('balance_amount'))}</td>
    </tr>"""


def customers_page(lang: str, user: dict[str, Any], customers: list[dict[str, Any]], message: str = "") -> str:
    rows = []
    for customer in customers:
        customer_id = quote(str(customer.get("customer_id", "")))
        edit = f"{MASTERDATA_BASE_URL}/customers/{customer_id}?lang={quote(lang)}"
        rows.append(
            f"<tr><td><a href='{esc(edit)}'>{esc(customer.get('customer_code',''))}</a></td><td>{esc(display_customer_name(customer, lang))}</td><td>{esc(customer.get('billing_contact_name',''))}</td><td>{esc(customer.get('billing_contact_email',''))}</td><td>{esc(customer.get('default_language','ja'))}</td><td>{esc(customer.get('default_payment_terms_days','30'))} days</td></tr>"
        )
    body = f"""
    <div class="page-title"><h2>{esc(t(lang, 'nav.customers'))}</h2><a class="button" href="{esc(MASTERDATA_BASE_URL + '/customers/new?lang=' + quote(lang))}">New Customer in Master Data</a></div>
    <div class="table-wrap"><table><thead><tr><th>Code</th><th>Name</th><th>Contact</th><th>Email</th><th>Lang</th><th>Payment Terms</th></tr></thead><tbody>{''.join(rows) or '<tr><td colspan="6" class="muted">No customers yet.</td></tr>'}</tbody></table></div>
    """
    return layout(lang, user, "Customers", "customers", body, message)



def masterdata_unavailable_page(lang: str, user: dict[str, Any], error: str) -> str:
    body = f"""
    <div class="page-title"><h2>Master Data unavailable</h2></div>
    <div class="panel"><p class="danger-text">{esc(error)}</p><p class="muted">Customer Billing now reads Customer Master from TACAI Master Data on port 8007. Start Master Data first, then return to this page.</p><p><a class="button secondary" href="{esc(with_lang('/dashboard', lang))}">Back to Dashboard</a></p></div>
    """
    return layout(lang, user, "Master Data unavailable", "customers", body)


def customer_form_page(lang: str, user: dict[str, Any], customer: dict[str, Any] | None = None, message: str = "") -> str:
    customer = customer or {}
    title = "Edit Customer" if customer else "New Customer"
    deactivate = ""
    if customer.get("customer_id"):
        deactivate = f"""<form method="post" action="/customers/deactivate" onsubmit="return confirm('Deactivate this customer?')"><input type="hidden" name="customer_id" value="{esc(customer.get('customer_id'))}"><input type="hidden" name="lang" value="{esc(lang)}"><button class="danger" type="submit">Deactivate</button></form>"""
    body = f"""
    <div class="page-title"><h2>{esc(title)}</h2><a class="button secondary" href="{esc(with_lang('/customers', lang))}">Back</a></div>
    <form class="panel" method="post" action="/customers/save">
      <input type="hidden" name="customer_id" value="{esc(customer.get('customer_id',''))}"><input type="hidden" name="lang" value="{esc(lang)}">
      <div class="form-grid">
        <div><label>Customer Code</label><input name="customer_code" value="{esc(customer.get('customer_code',''))}" placeholder="CUS-ABC"></div>
        <div><label>Customer Name / 顧客名</label><input name="customer_name" value="{esc(customer.get('customer_name',''))}" required></div>
        <div><label>English Name</label><input name="customer_name_en" value="{esc(customer.get('customer_name_en',''))}"></div>
        <div><label>Chinese Name</label><input name="customer_name_zh" value="{esc(customer.get('customer_name_zh',''))}"></div>
        <div><label>Registration No.</label><input name="customer_registration_number" value="{esc(customer.get('customer_registration_number',''))}"></div>
        <div><label>Default Language</label><select name="default_language">{options_html(list(LANGS), customer.get('default_language','ja'))}</select></div>
        <div><label>Payment Terms Days</label><input name="default_payment_terms_days" value="{esc(customer.get('default_payment_terms_days','30'))}"></div>
        <div><label>Default Tax Rate</label><select name="default_tax_rate">{options_html(TAX_RATES, customer.get('default_tax_rate','10%'))}</select></div>
        <div><label>Billing Contact</label><input name="billing_contact_name" value="{esc(customer.get('billing_contact_name',''))}"></div>
        <div><label>Billing Email</label><input name="billing_contact_email" value="{esc(customer.get('billing_contact_email',''))}"></div>
      </div>
      <label>Billing Address</label><textarea name="billing_address">{esc(customer.get('billing_address',''))}</textarea>
      <label>Business Types</label><input name="business_types" value="{esc(','.join(customer.get('business_types', [])) if isinstance(customer.get('business_types'), list) else customer.get('business_types',''))}" placeholder="haken_dispatch,recruitment_placement,rpo">
      <label>Notes</label><textarea name="notes">{esc(customer.get('notes',''))}</textarea>
      <div class="actions"><button type="submit">{esc(t(lang, 'action.save'))}</button><a class="button secondary" href="{esc(with_lang('/customers', lang))}">Cancel</a></div>
    </form>
    <div class="actions">{deactivate}</div>
    """
    return layout(lang, user, title, "customers", body, message)


def billings_page(lang: str, user: dict[str, Any], query: dict[str, list[str]], message: str = "") -> str:
    billings = active_billings()
    status_filter = (query.get("status") or [""])[0]
    business_filter = (query.get("business_type") or [""])[0]
    if status_filter:
        billings = [row for row in billings if row.get("status") == status_filter]
    if business_filter:
        billings = [row for row in billings if row.get("business_type") == business_filter]
    billings = sorted(billings, key=lambda row: str(row.get("billing_no", "")), reverse=True)
    rows = "".join(billing_row_html(row, lang) for row in billings) or '<tr><td colspan="8" class="muted">No billing records.</td></tr>'
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Billing</div>
        <h2>{esc(t(lang, 'nav.billings'))}</h2>
        <p>Manage invoices, request notes, payment status, and outstanding balances.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings/new', lang, mode='ocr'))}">Import Previous Invoice / OCR Assist</a><a class="button" href="{esc(with_lang('/billings/new', lang))}">{esc(t(lang, 'nav.new_billing'))}</a></div>
    </section>
    <form class="sap-section" method="get" action="/billings">
      <div class="section-header"><div class="eyebrow">Filter</div><h3>Search billings</h3></div>
      <input type="hidden" name="lang" value="{esc(lang)}">
      <div class="form-grid"><div><label>Status</label><select name="status">{options_html(STATUSES, status_filter, True)}</select></div><div><label>Business Type</label><select name="business_type">{options_html(BUSINESS_TYPES, business_filter, True)}</select></div></div>
      <div class="sap-toolbar"><a class="button ghost spacer" href="{esc(with_lang('/billings', lang))}">Reset</a><button type="submit">Filter</button></div>
    </form>
    <section class="panel wide"><div class="section-header"><div class="eyebrow">List</div><h3>Billing records</h3></div><div class="table-scroll"><table>{billing_table_head()}<tbody>{rows}</tbody></table></div></section>
    """
    return layout(lang, user, "Billings", "billings", body, message)


def billing_new_entry_page(lang: str, user: dict[str, Any], message: str = "") -> str:
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">New Billing</div>
        <h2>Create billing draft</h2>
        <p>Start manually or create a reviewed draft from a scanned invoice/source document.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings', lang))}">Back to Billings</a></div>
    </section>
    <div class="grid">
      <section class="card">
        <div class="metric">Manual entry</div>
        <h3>Start from blank</h3>
        <p class="muted">Create a billing draft by selecting a Customer Master record and typing invoice details.</p>
        <div class="actions"><a class="button" href="{esc(with_lang('/billings/new', lang, mode='manual'))}">Create Manually</a></div>
      </section>
      <section class="card">
        <div class="metric">Previous invoice / OCR assist</div>
        <h3>Import previous invoice to assist input</h3>
        <p class="muted">Upload or paste an old invoice/request note. The system extracts likely fields into a reviewed billing draft and keeps the scan as an attachment.</p>
        <div class="actions"><a class="button secondary" href="{esc(with_lang('/billings/new', lang, mode='ocr'))}">Import Previous Invoice</a></div>
      </section>
    </div>
    <section class="notice message-warning">OCR is an assistant only. Finance must review customer, dates, tax, line items, duplicate warnings, and totals before saving.</section>
    """
    return layout(lang, user, "New Billing", "new", body, message)


def billing_form_page(lang: str, user: dict[str, Any], customers: list[dict[str, Any]], billing: dict[str, Any] | None = None, message: str = "") -> str:
    company = load_json_object(COMPANY_PROFILE_PATH, DEFAULT_COMPANY_PROFILE)
    billing = billing or {}
    selected_customer = billing.get("customer_id", "")
    issue_date = billing.get("issue_date") or today_iso()
    due_date = billing.get("due_date") or add_days(issue_date, int(company.get("default_payment_terms_days", 30) or 30))
    line_items = billing.get("line_items", []) if isinstance(billing.get("line_items"), list) else []
    line_rows = []
    for index in range(5):
        line = line_items[index] if index < len(line_items) else {}
        line_rows.append(
            f"""<tr><td><input name="line_description_{index}" value="{esc(line.get('description',''))}"></td><td><input name="line_quantity_{index}" value="{esc(line.get('quantity',''))}"></td><td><input name="line_unit_{index}" value="{esc(line.get('unit',''))}"></td><td><input name="line_unit_price_{index}" value="{esc(line.get('unit_price',''))}"></td><td><select name="line_tax_rate_{index}">{options_html(TAX_RATES, line.get('tax_rate','10%'))}</select></td><td><input name="line_memo_{index}" value="{esc(line.get('memo',''))}"></td></tr>"""
        )
    readonly_notice = ""
    if billing and billing.get("status") not in {"Draft", ""}:
        readonly_notice = '<div class="message-strip message-warning">Issued/sent billing records should only be changed through status, payment, cancel, or copy actions.</div>'
    page_title = 'Edit Billing' if billing else 'New Billing'
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Billing document</div>
        <h2>{esc(page_title)}</h2>
        <p>Create or update customer invoice/request note details without changing issued-record controls.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings/new', lang, mode='ocr'))}">Import Previous Invoice / OCR Assist</a><a class="button ghost" href="{esc(with_lang('/billings', lang))}">Back to Billings</a></div>
    </section>
    {readonly_notice}
    <form method="post" action="/billings/save">
      <input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}">
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Document & Customer</div><h3>Header information</h3></div>
        <div class="form-grid">
          <div><label>{esc(t(lang, 'label.document_type'))}</label><select name="document_type">{options_html(DOCUMENT_TYPES, billing.get('document_type','invoice'))}</select></div>
          <div><label>{esc(t(lang, 'label.language'))}</label><select name="billing_language">{options_html(list(LANGS), billing.get('language', lang))}</select></div>
          <div><label>{esc(t(lang, 'label.customer'))}</label><select name="customer_id" required>{customer_options(customers, selected_customer, lang)}</select></div>
          <div><label>{esc(t(lang, 'label.business_type'))}</label><select name="business_type">{options_html(BUSINESS_TYPES, billing.get('business_type','haken_dispatch'))}</select></div>
          <div><label>{esc(t(lang, 'label.issue_date'))}</label><input type="date" name="issue_date" value="{esc(issue_date)}"></div>
          <div><label>{esc(t(lang, 'label.due_date'))}</label><input type="date" name="due_date" value="{esc(due_date)}"></div>
          <div><label>PO Number (optional)</label><input name="po_number" value="{esc(billing.get('po_number',''))}"></div>
          <div><label>Currency</label><input name="currency" value="{esc(billing.get('currency','JPY'))}"></div>
        </div>
      </section>
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Business Details</div><h3>Service and contract reference</h3></div>
        <div class="form-grid">
          <div><label>Service Period From</label><input type="date" name="service_period_from" value="{esc(billing.get('service_period_from',''))}"></div>
          <div><label>Service Period To</label><input type="date" name="service_period_to" value="{esc(billing.get('service_period_to',''))}"></div>
          <div><label>Dispatch worker / Candidate / Contract</label><input name="subject_name" value="{esc(billing.get('subject_name',''))}"></div>
          <div><label>Placement Date / Billing Month</label><input name="business_reference_date" value="{esc(billing.get('business_reference_date',''))}" placeholder="2026-06"></div>
          <div><label>Reference Amount</label><input name="reference_amount" value="{esc(billing.get('reference_amount',''))}"></div>
          <div><label>Fee Rate</label><input name="fee_rate" value="{esc(billing.get('fee_rate',''))}" placeholder="35%"></div>
        </div>
      </section>
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Line Items</div><h3>Billing breakdown</h3></div>
        <div class="table-scroll"><table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit Price</th><th>Tax</th><th>Memo</th></tr></thead><tbody>{''.join(line_rows)}</tbody></table></div>
      </section>
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Notes</div><h3>Invoice text and internal memo</h3></div>
        <label>Invoice / Request Note</label><textarea name="invoice_note">{esc(billing.get('invoice_note',''))}</textarea>
        <label>Internal Memo</label><textarea name="internal_memo">{esc(billing.get('internal_memo',''))}</textarea>
        <div class="sap-toolbar"><a class="button ghost spacer" href="{esc(with_lang('/billings', lang))}">Cancel</a><button type="submit">{esc(t(lang, 'action.save'))}</button></div>
      </section>
    </form>
    """
    return layout(lang, user, "Billing", "new" if not billing else "billings", body, message)


def ocr_upload_page(lang: str, user: dict[str, Any], message: str = "") -> str:
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Import Previous Invoice / OCR Assist</div>
        <h2>Assist input from previous invoice</h2>
        <p>Upload a PDF/image/Word/text invoice or paste extracted text. The system will prefill a reviewed Customer Billing draft.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings/new', lang))}">Back to New Billing</a></div>
    </section>
    <section class="sap-section">
      <div class="section-header"><div class="eyebrow">Source document</div><h3>Upload invoice/request note</h3></div>
      <form method="post" action="/billings/ocr/upload" enctype="multipart/form-data">
        <input type="hidden" name="lang" value="{esc(lang)}">
        <div class="form-grid">
          <div><label>Invoice file / previous invoice scan</label><input type="file" name="source_file" accept=".pdf,.jpg,.jpeg,.png,.webp,.doc,.docx,.rtf,.txt,.md,.markdown"><p class="muted">Max 10 MB. Supported: PDF, JPG, PNG, WEBP, Word, RTF, TXT/MD. If no file is available, paste invoice text below.</p></div>
          <div><label>Language hint</label><select name="source_language_hint"><option value="auto">Auto</option><option value="ja">Japanese</option><option value="en">English</option></select></div>
          <div><label>Import mode</label><select name="import_mode"><option value="historical_backfill">Historical invoice backfill</option><option value="current_draft">Current billing draft</option></select></div>
        </div>
        <label>Optional pasted invoice text</label><textarea name="pasted_text" placeholder="Paste old invoice text here when you do not have a file, or to improve extraction from a scan."></textarea>
        <div class="sap-toolbar"><a class="button ghost spacer" href="{esc(with_lang('/billings/new', lang))}">Cancel</a><button type="submit">Import and Prefill Draft</button></div>
      </form>
    </section>
    <section class="notice message-warning">This import/OCR function is an input assistant only. Review customer, dates, tax, line items, duplicate warnings, and totals before saving the Billing Draft.</section>
    """
    return layout(lang, user, "New Billing from Scan", "new", body, message)


def ocr_review_page(lang: str, user: dict[str, Any], draft: dict[str, Any], customers: list[dict[str, Any]], message: str = "") -> str:
    extracted = draft.get("extracted", {}) if isinstance(draft.get("extracted"), dict) else {}
    customer_match = draft.get("customer_match", {}) if isinstance(draft.get("customer_match"), dict) else {}
    duplicate = draft.get("duplicate_check", {}) if isinstance(draft.get("duplicate_check"), dict) else {}
    selected_customer = str(customer_match.get("matched_customer_id", ""))
    issue_date = str(extracted.get("issue_date") or today_iso())
    due_date = str(extracted.get("due_date") or add_days(issue_date, 30))
    source_file = draft.get("source_file", {}) if isinstance(draft.get("source_file"), dict) else {}
    warnings = []
    warnings.extend(draft.get("warnings", []) if isinstance(draft.get("warnings"), list) else [])
    warnings.extend(extracted.get("warnings", []) if isinstance(extracted.get("warnings"), list) else [])
    duplicate_status = str(duplicate.get("status", "none") or "none")
    if duplicate_status != "none":
        warnings.append(f"Possible duplicate billing records: {', '.join(duplicate.get('matched_billing_ids', []))}")
    warning_html = "".join(f"<li>{esc(item)}</li>" for item in warnings) or "<li>No blocking warnings. Please still review all fields.</li>"
    duplicate_ack_html = ""
    if duplicate_status != "none":
        duplicate_ack_html = f"""<section class="sap-section message-warning"><label><input type="checkbox" name="duplicate_ack" value="yes" required> I reviewed possible duplicate billing records and want to continue.</label></section>"""
    raw_text = str(draft.get("raw_text", ""))[:6000]
    line_items = extracted.get("line_items", []) if isinstance(extracted.get("line_items"), list) else []
    line_row_count = max(5, len([item for item in line_items if isinstance(item, dict)]))
    line_rows = []
    for index in range(line_row_count):
        line = line_items[index] if index < len(line_items) and isinstance(line_items[index], dict) else {}
        line_rows.append(
            f"""<tr><td><input name="line_description_{index}" value="{esc(line.get('description','OCR imported invoice line' if index == 0 else ''))}"></td><td><input name="line_quantity_{index}" value="{esc(line.get('quantity','1' if index == 0 else ''))}"></td><td><input name="line_unit_{index}" value="{esc(line.get('unit','式' if index == 0 else ''))}"></td><td><input name="line_unit_price_{index}" value="{esc(line.get('unit_price',''))}"></td><td><select name="line_tax_rate_{index}">{options_html(TAX_RATES, line.get('tax_rate', extracted.get('tax_rate','10%')))}</select></td><td><input name="line_memo_{index}" value="{esc(line.get('memo',''))}"></td></tr>"""
        )
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">OCR Review</div>
        <h2>{esc(draft.get('ocr_draft_id',''))}</h2>
        <p>Confirm extracted invoice data and save it as a Customer Billing Draft.</p>
      </div>
      <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings/new', lang, mode='ocr'))}">Back to Scan Upload</a></div>
    </section>
    <section class="sap-section">
      <div class="section-header"><div class="eyebrow">Source</div><h3>Document extraction status</h3></div>
      <div class="object-meta">
        <span class="meta-chip"><span class="meta-chip-label">File</span><span class="meta-chip-value">{esc(source_file.get('original_filename',''))}</span></span>
        <span class="meta-chip"><span class="meta-chip-label">OCR Status</span><span class="meta-chip-value">{esc(draft.get('ocr_status',''))}</span></span>
        <span class="meta-chip"><span class="meta-chip-label">Engine</span><span class="meta-chip-value">{esc(draft.get('ocr_engine',''))}</span></span>
        <span class="meta-chip"><span class="meta-chip-label">Customer Match</span><span class="meta-chip-value">{esc(customer_match.get('confidence','low'))}</span></span>
      </div>
    </section>
    <section class="message-strip message-warning"><strong>Review required</strong><ul>{warning_html}</ul></section>
    <form method="post" action="/billings/ocr/confirm">
      <input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="ocr_draft_id" value="{esc(draft.get('ocr_draft_id',''))}"><input type="hidden" name="line_row_count" value="{line_row_count}">
      {duplicate_ack_html}
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Document & Customer</div><h3>Confirmed billing header</h3></div>
        <div class="form-grid">
          <div><label>Original Invoice No.</label><input name="original_invoice_no" value="{esc(extracted.get('original_invoice_no',''))}"></div>
          <div><label>{esc(t(lang, 'label.document_type'))}</label><select name="document_type">{options_html(DOCUMENT_TYPES, extracted.get('document_type','invoice'))}</select></div>
          <div><label>{esc(t(lang, 'label.language'))}</label><select name="billing_language">{options_html(list(LANGS), lang)}</select></div>
          <div><label>{esc(t(lang, 'label.customer'))}</label><select name="customer_id" required>{customer_options(customers, selected_customer, lang)}</select></div>
          <div><label>{esc(t(lang, 'label.business_type'))}</label><select name="business_type">{options_html(BUSINESS_TYPES, extracted.get('business_type','other'))}</select></div>
          <div><label>{esc(t(lang, 'label.issue_date'))}</label><input type="date" name="issue_date" value="{esc(issue_date)}"></div>
          <div><label>{esc(t(lang, 'label.due_date'))}</label><input type="date" name="due_date" value="{esc(due_date)}"></div>
          <div><label>Currency</label><input name="currency" value="{esc(extracted.get('currency','JPY'))}"></div>
        </div>
      </section>
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Line Items</div><h3>Review extracted billing lines</h3></div>
        <div class="table-scroll"><table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th>Unit Price</th><th>Tax</th><th>Memo</th></tr></thead><tbody>{''.join(line_rows)}</tbody></table></div>
      </section>
      <section class="sap-section">
        <div class="section-header"><div class="eyebrow">Notes</div><h3>Invoice note and OCR context</h3></div>
        <label>Invoice / Request Note</label><textarea name="invoice_note">{esc(extracted.get('invoice_note',''))}</textarea>
        <label>Internal Memo</label><textarea name="internal_memo">{esc(extracted.get('internal_memo',''))}</textarea>
        <label>Extracted raw text preview</label><textarea readonly>{esc(raw_text)}</textarea>
        <div class="sap-toolbar"><button class="ghost spacer" type="submit" name="action" value="discard" formmethod="post" formaction="/billings/ocr/discard">Discard OCR Draft</button><button type="submit">Save as Billing Draft</button></div>
      </section>
    </form>
    """
    return layout(lang, user, "OCR Review", "billings", body, message)


def billing_detail_page(lang: str, user: dict[str, Any], billing: dict[str, Any], message: str = "") -> str:
    lines = billing.get("line_items", []) if isinstance(billing.get("line_items"), list) else []
    line_rows = "".join(
        f"<tr><td>{esc(line.get('description',''))}</td><td>{esc(line.get('quantity',''))}</td><td>{esc(line.get('unit',''))}</td><td class='right'>¥{money(line.get('unit_price'))}</td><td>{esc(line.get('tax_rate',''))}</td><td class='right'>¥{money(line.get('amount_excluding_tax'))}</td><td class='right'>¥{money(line.get('tax_amount'))}</td><td class='right'>¥{money(line.get('amount_including_tax'))}</td></tr>"
        for line in lines
    ) or '<tr><td colspan="8" class="muted">No line items.</td></tr>'
    payments = billing.get("payments", []) if isinstance(billing.get("payments"), list) else []
    payment_rows = "".join(
        f"<tr><td>{esc(payment.get('payment_id',''))}</td><td>{esc(payment.get('payment_date',''))}</td><td class='right'>¥{money(payment.get('amount'))}</td><td>{esc(payment.get('method',''))}</td><td>{esc(payment.get('reference',''))}</td><td>{esc(payment.get('memo',''))}</td></tr>"
        for payment in payments
    ) or '<tr><td colspan="6" class="muted">No payments yet.</td></tr>'
    history = billing.get("history", []) if isinstance(billing.get("history"), list) else []
    history_rows = "".join(
        f"<tr><td>{esc(item.get('timestamp',''))}</td><td>{esc(item.get('action',''))}</td><td>{esc(item.get('actor',''))}</td><td>{esc(item.get('summary',''))}</td></tr>"
        for item in history[-10:]
    ) or '<tr><td colspan="4" class="muted">No history.</td></tr>'
    can_manage = has_permission(user, "client_revenue.manage")
    action_forms = ""
    if can_manage:
        action_forms = f"""
        <section class="sap-section">
          <div class="section-header"><div class="eyebrow">Actions</div><h3>Billing workflow</h3></div>
          <div class="actions">
            <a class="button secondary" href="{esc(with_lang('/billings/edit', lang, id=str(billing.get('billing_id',''))))}">Edit</a>
            <form method="post" action="/billings/copy"><input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}"><button class="ghost" type="submit">{esc(t(lang, 'action.copy'))}</button></form>
            <form method="post" action="/billings/status"><input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}"><input type="hidden" name="status" value="Issued"><button type="submit">{esc(t(lang, 'action.issue'))}</button></form>
            <form method="post" action="/billings/status"><input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}"><input type="hidden" name="status" value="Sent"><button class="secondary" type="submit">{esc(t(lang, 'action.sent'))}</button></form>
            <form method="post" action="/billings/status" onsubmit="return confirm('Cancel this billing?')"><input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}"><input type="hidden" name="status" value="Cancelled"><button class="danger" type="submit">Cancel</button></form>
          </div>
        </section>"""
    attachments = billing.get("attachments", []) if isinstance(billing.get("attachments"), list) else []
    attachment_rows = []
    for attachment in attachments:
        if not isinstance(attachment, dict):
            continue
        attachment_id = str(attachment.get("attachment_id", ""))
        link = with_lang("/billings/attachment", lang, billing_id=str(billing.get("billing_id", "")), attachment_id=attachment_id)
        sha = str(attachment.get("sha256", ""))
        size = attachment.get("size_bytes", "")
        try:
            size_label = f"{int(size or 0):,} bytes" if size != "" else ""
        except (TypeError, ValueError):
            size_label = esc(size)
        attachment_rows.append(
            f"<tr><td><a href='{esc(link)}'>{esc(attachment.get('original_filename',''))}</a></td><td>{esc(attachment.get('attachment_type',''))}</td><td>{esc(attachment.get('uploaded_by',''))}</td><td>{esc(attachment.get('uploaded_at',''))}</td><td>{esc(size_label)}</td><td>{esc((sha[:12] + '...') if sha else '')}</td><td>{esc(attachment.get('linked_from_ocr_draft_id',''))}</td></tr>"
        )
    attachment_section = ""
    if attachment_rows:
        attachment_section = f"""<section class="sap-section"><div class="section-header"><div class="eyebrow">Source Documents</div><h3>Attachments</h3></div><div class="table-scroll"><table><thead><tr><th>File</th><th>Type</th><th>Uploaded By</th><th>Uploaded At</th><th>Size</th><th>SHA-256</th><th>OCR Draft</th></tr></thead><tbody>{''.join(attachment_rows)}</tbody></table></div></section>"""
    elif billing.get("source_ocr_draft_id") or billing.get("source_file_hash"):
        source_hash = str(billing.get("source_file_hash", ""))
        attachment_section = f"""<section class="sap-section"><div class="section-header"><div class="eyebrow">Source Documents</div><h3>OCR source metadata</h3></div><div class="form-grid"><div><strong>OCR Draft:</strong> {esc(billing.get('source_ocr_draft_id',''))}</div><div><strong>Source Hash:</strong> {esc((source_hash[:12] + '...') if source_hash else '')}</div></div></section>"""
    payment_form = ""
    if can_manage and billing.get("status") != "Cancelled":
        payment_form = f"""
        <form class="sap-section" method="post" action="/billings/payment">
          <div class="section-header"><div class="eyebrow">Payment</div><h3>{esc(t(lang, 'action.payment'))}</h3></div>
          <input type="hidden" name="lang" value="{esc(lang)}"><input type="hidden" name="billing_id" value="{esc(billing.get('billing_id',''))}">
          <div class="form-grid"><div><label>Payment Date</label><input type="date" name="payment_date" value="{today_iso()}"></div><div><label>Amount</label><input name="amount" value="{esc(billing.get('balance_amount',''))}"></div><div><label>Method</label><select name="method">{options_html(PAYMENT_METHODS, 'bank_transfer')}</select></div><div><label>Reference</label><input name="reference"></div></div>
          <label>Memo</label><textarea name="memo"></textarea><div class="sap-toolbar"><button type="submit">{esc(t(lang, 'action.payment'))}</button></div>
        </form>"""
    body = f"""
    <div class="object-page">
      <section class="object-header">
        <div>
          <div class="eyebrow">Billing</div>
          <h2>{esc(billing.get('billing_no',''))} {status_badge(str(billing.get('status','Draft')))}</h2>
          <p>{esc(billing.get('customer_name_snapshot',''))}</p>
          <div class="object-meta">
            <span class="meta-chip"><span class="meta-chip-label">Issue</span><span class="meta-chip-value">{esc(billing.get('issue_date',''))}</span></span>
            <span class="meta-chip"><span class="meta-chip-label">Due</span><span class="meta-chip-value">{esc(billing.get('due_date',''))}</span></span>
            <span class="meta-chip"><span class="meta-chip-label">Business</span><span class="meta-chip-value">{esc(billing.get('business_type',''))}</span></span>
          </div>
        </div>
        <div class="actions"><a class="button ghost" href="{esc(with_lang('/billings', lang))}">Back to Billings</a></div>
      </section>
      <div class="grid">
        <div class="card"><div class="metric">Customer</div><div class="metric-value" style="font-size:20px;">{esc(billing.get('customer_name_snapshot',''))}</div></div>
        <div class="card"><div class="metric">Total</div><div class="metric-value">¥{money(billing.get('total_amount'))}</div></div>
        <div class="card"><div class="metric">Paid</div><div class="metric-value good">¥{money(billing.get('paid_amount'))}</div></div>
        <div class="card"><div class="metric">Balance</div><div class="metric-value warn">¥{money(billing.get('balance_amount'))}</div></div>
      </div>
      {action_forms}
      {attachment_section}
      <section class="sap-section"><div class="section-header"><div class="eyebrow">Header</div><h3>Billing Header</h3></div><div class="form-grid"><div><strong>Document:</strong> {esc(billing.get('document_type',''))}</div><div><strong>Business:</strong> {esc(billing.get('business_type',''))}</div><div><strong>Issue:</strong> {esc(billing.get('issue_date',''))}</div><div><strong>Due:</strong> {esc(billing.get('due_date',''))}</div><div><strong>Qualified Invoice No.:</strong> {esc(billing.get('qualified_invoice_registration_number',''))}</div><div><strong>Bank:</strong> {esc((billing.get('bank_info_snapshot') or {}).get('bank_name',''))}</div></div><p>{esc(billing.get('invoice_note',''))}</p></section>
      <section class="sap-section"><div class="section-header"><div class="eyebrow">Breakdown</div><h3>Line Items</h3></div><div class="table-scroll"><table><thead><tr><th>Description</th><th>Qty</th><th>Unit</th><th class="right">Unit Price</th><th>Tax</th><th class="right">Excl.</th><th class="right">Tax</th><th class="right">Incl.</th></tr></thead><tbody>{line_rows}</tbody><tfoot><tr><th colspan="5">Totals</th><th class="right">¥{money(billing.get('subtotal_amount'))}</th><th class="right">¥{money(billing.get('tax_amount'))}</th><th class="right">¥{money(billing.get('total_amount'))}</th></tr></tfoot></table></div></section>
      <section class="sap-section"><div class="section-header"><div class="eyebrow">Collection</div><h3>Payments</h3></div><div class="table-scroll"><table><thead><tr><th>ID</th><th>Date</th><th class="right">Amount</th><th>Method</th><th>Reference</th><th>Memo</th></tr></thead><tbody>{payment_rows}</tbody></table></div></section>
      {payment_form}
      <section class="sap-section"><div class="section-header"><div class="eyebrow">Audit trail</div><h3>History</h3></div><div class="table-scroll"><table><thead><tr><th>Time</th><th>Action</th><th>Actor</th><th>Summary</th></tr></thead><tbody>{history_rows}</tbody></table></div></section>
    </div>
    """
    return layout(lang, user, "Billing Detail", "billings", body, message)


def reports_page(lang: str, user: dict[str, Any]) -> str:
    billings = active_billings()
    buckets = {"not_due": 0, "overdue_1_30": 0, "overdue_31_60": 0, "overdue_61_90": 0, "overdue_90_plus": 0, "unknown": 0}
    business = {key: 0 for key in BUSINESS_TYPES}
    for row in billings:
        if row.get("status") == "Cancelled":
            continue
        balance = int(row.get("balance_amount", 0) or 0)
        bucket = due_bucket(row)
        if bucket in buckets:
            buckets[bucket] += balance
        btype = str(row.get("business_type", "other"))
        business[btype if btype in business else "other"] += int(row.get("total_amount", 0) or 0)
    bucket_rows = "".join(f"<tr><td>{esc(key)}</td><td class='right'>¥{money(value)}</td></tr>" for key, value in buckets.items())
    business_rows = "".join(f"<tr><td>{esc(key)}</td><td class='right'>¥{money(value)}</td></tr>" for key, value in business.items())
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Reports</div>
        <h2>{esc(t(lang, 'nav.reports'))}</h2>
        <p>Review accounts receivable aging and billing totals by business type.</p>
      </div>
    </section>
    <div class="grid">
      <section class="panel"><div class="section-header"><div class="eyebrow">Aging</div><h3>AR Aging</h3></div><div class="table-scroll"><table><tbody>{bucket_rows}</tbody></table></div></section>
      <section class="panel"><div class="section-header"><div class="eyebrow">Revenue</div><h3>Billing by Business Type</h3></div><div class="table-scroll"><table><tbody>{business_rows}</tbody></table></div></section>
    </div>
    """
    return layout(lang, user, "Reports", "reports", body)


def audit_page(lang: str, user: dict[str, Any]) -> str:
    logs = sorted(load_json_array(AUDIT_LOGS_PATH), key=lambda row: str(row.get("timestamp", "")), reverse=True)[:200]
    rows = "".join(
        f"<tr><td>{esc(log.get('timestamp',''))}</td><td>{esc(log.get('record_id',''))}</td><td>{esc(log.get('action',''))}</td><td>{esc(log.get('user',''))}</td></tr>"
        for log in logs
    ) or '<tr><td colspan="4" class="muted">No audit logs.</td></tr>'
    body = f"""
    <section class="sap-page-header">
      <div>
        <div class="eyebrow">Audit</div>
        <h2>{esc(t(lang, 'nav.audit'))}</h2>
        <p>Read-only operational history for billing records and financial actions.</p>
      </div>
    </section>
    <section class="panel wide"><div class="section-header"><div class="eyebrow">Log</div><h3>Recent audit entries</h3></div><div class="table-scroll"><table><thead><tr><th>Timestamp</th><th>Record</th><th>Action</th><th>User</th></tr></thead><tbody>{rows}</tbody></table></div></section>
    """
    return layout(lang, user, "Audit", "audit", body)


class CustomerBillingHandler(BaseHTTPRequestHandler):
    server_version = "CustomerBillingWeb/0.1"

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        return parsed.hostname in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS

    def current_user(self) -> dict[str, Any] | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        if not session_cookie:
            return None
        return validate_user_admin_session(session_cookie.value)


    def session_id_from_cookie(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        session_cookie = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return session_cookie.value if session_cookie else ""

    def masterdata_customers(self) -> list[dict[str, Any]]:
        data = fetch_masterdata_json("/api/customers", self.session_id_from_cookie())
        if not isinstance(data, list):
            return []
        return [normalize_master_customer(row) for row in data if isinstance(row, dict)]

    def masterdata_customer(self, customer_id: str) -> dict[str, Any] | None:
        if not customer_id:
            return None
        data = fetch_masterdata_json(f"/api/customers/{quote(customer_id)}", self.session_id_from_cookie())
        return normalize_master_customer(data) if isinstance(data, dict) else None

    def require_user(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            next_url = quote(f"{APP_BASE_URL}{self.path}", safe="")
            self.send_response(303)
            self.send_header("Location", f"{USER_ADMIN_BASE_URL}/login?next={next_url}")
            self.end_headers()
            return None
        if not has_permission(user, REQUIRED_MODULE_PERMISSION):
            self.send_error(403, "Missing client_revenue.access permission")
            return None
        return user

    def require_permission(self, user: dict[str, Any], permission_key: str) -> bool:
        if has_permission(user, permission_key):
            return True
        self.send_error(403, f"Missing {permission_key} permission")
        return False

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        if path == "/health":
            self._send_text("OK")
            return
        user = self.require_user()
        if not user:
            return
        lang = get_lang(query)
        message = (query.get("message") or [""])[0]
        if path == "/" or path == "/dashboard":
            try:
                customers = self.masterdata_customers()
            except ValueError:
                customers = []
            self._send_html(dashboard_page(lang, user, customers, message))
        elif path == "/customers":
            try:
                customers = self.masterdata_customers()
            except ValueError as exc:
                self._send_html(masterdata_unavailable_page(lang, user, str(exc)))
                return
            self._send_html(customers_page(lang, user, customers, message))
        elif path == "/customers/new":
            self._redirect(f"{MASTERDATA_BASE_URL}/customers/new?lang={quote(lang)}")
        elif path == "/customers/edit":
            customer_id = quote((query.get("id") or [""])[0])
            self._redirect(f"{MASTERDATA_BASE_URL}/customers/{customer_id}/edit?lang={quote(lang)}")
        elif path == "/billings":
            self._send_html(billings_page(lang, user, query, message))
        elif path == "/billings/new":
            if not self.require_permission(user, "client_revenue.manage"):
                return
            mode = (query.get("mode") or [""])[0]
            if not mode:
                self._send_html(billing_new_entry_page(lang, user, message))
                return
            if mode == "ocr":
                self._send_html(ocr_upload_page(lang, user, message))
                return
            if mode != "manual":
                self.send_error(400, "Unsupported New Billing mode")
                return
            try:
                customers = self.masterdata_customers()
            except ValueError as exc:
                self._send_html(masterdata_unavailable_page(lang, user, str(exc)))
                return
            self._send_html(billing_form_page(lang, user, customers, message=message))
        elif path == "/billings/ocr/new":
            if not self.require_permission(user, "client_revenue.manage"):
                return
            self._send_html(ocr_upload_page(lang, user, message))
        elif path == "/billings/ocr/review":
            if not self.require_permission(user, "client_revenue.manage"):
                return
            draft = find_by_id(load_json_array(OCR_DRAFTS_PATH), "ocr_draft_id", (query.get("id") or [""])[0])
            if not draft:
                self.send_error(404, "OCR draft not found")
                return
            try:
                customers = self.masterdata_customers()
            except ValueError as exc:
                self._send_html(masterdata_unavailable_page(lang, user, str(exc)))
                return
            self._send_html(ocr_review_page(lang, user, draft, customers, message))
        elif path == "/billings/edit":
            if not self.require_permission(user, "client_revenue.manage"):
                return
            billing = find_by_id(load_json_array(BILLINGS_PATH), "billing_id", (query.get("id") or [""])[0])
            if not billing:
                self.send_error(404, "Billing not found")
                return
            try:
                customers = self.masterdata_customers()
            except ValueError as exc:
                self._send_html(masterdata_unavailable_page(lang, user, str(exc)))
                return
            self._send_html(billing_form_page(lang, user, customers, billing))
        elif path == "/billings/detail":
            billing = find_by_id(load_json_array(BILLINGS_PATH), "billing_id", (query.get("id") or [""])[0])
            if not billing:
                self.send_error(404, "Billing not found")
                return
            self._send_html(billing_detail_page(lang, user, billing, message))
        elif path == "/billings/attachment":
            self._handle_billing_attachment(query)
        elif path == "/reports":
            if not self.require_permission(user, "client_revenue.reports.view"):
                return
            self._send_html(reports_page(lang, user))
        elif path == "/audit":
            if not (has_permission(user, "client_revenue.reports.view") or has_permission(user, "client_revenue.manage")):
                self.send_error(403, "Missing report or manage permission")
                return
            self._send_html(audit_page(lang, user))
        else:
            self.send_error(404, "Not found")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        if not self.csrf_origin_allowed():
            self.send_error(403, "Request origin is not allowed")
            return
        user = self.require_user()
        if not user:
            return
        if not self.require_permission(user, "client_revenue.manage"):
            return
        uploads: dict[str, dict[str, Any]] = {}
        if path == "/billings/ocr/upload":
            form, uploads = self._read_multipart_form()
        else:
            form = self._read_form()
        lang = (form.get("lang") or [DEFAULT_LANG])[0]
        if lang not in LANGS:
            lang = DEFAULT_LANG
        try:
            if path == "/customers/save":
                self._redirect(f"{MASTERDATA_BASE_URL}/customers?lang={quote(lang)}")
            elif path == "/customers/deactivate":
                self._redirect(f"{MASTERDATA_BASE_URL}/customers?lang={quote(lang)}")
            elif path == "/billings/save":
                self._handle_billing_save(form, user, lang)
            elif path == "/billings/status":
                self._handle_billing_status(form, user, lang)
            elif path == "/billings/payment":
                self._handle_billing_payment(form, user, lang)
            elif path == "/billings/copy":
                self._handle_billing_copy(form, user, lang)
            elif path == "/billings/ocr/upload":
                self._handle_ocr_upload(form, uploads, user, lang)
            elif path == "/billings/ocr/confirm":
                self._handle_ocr_confirm(form, user, lang)
            elif path == "/billings/ocr/discard":
                self._handle_ocr_discard(form, user, lang)
            else:
                self.send_error(404, "Not found")
        except ValueError as exc:
            self.send_error(400, str(exc))

    def _handle_billing_attachment(self, query: dict[str, list[str]]) -> None:
        billing = find_by_id(load_json_array(BILLINGS_PATH), "billing_id", (query.get("billing_id") or [""])[0])
        if not billing:
            self.send_error(404, "Billing not found")
            return
        attachment_id = (query.get("attachment_id") or [""])[0]
        attachments = billing.get("attachments", []) if isinstance(billing.get("attachments"), list) else []
        attachment = find_by_id([item for item in attachments if isinstance(item, dict)], "attachment_id", attachment_id)
        if not attachment:
            self.send_error(404, "Attachment not found")
            return
        file_path = attachment_file_path(attachment)
        if not file_path:
            self.send_error(403, "Attachment path is not allowed")
            return
        if not file_path.is_file():
            self.send_error(404, "Attachment file not found")
            return
        data = file_path.read_bytes()
        content_type = str(attachment.get("content_type") or mimetypes.guess_type(file_path.name)[0] or "application/octet-stream")
        filename = Path(str(attachment.get("original_filename") or file_path.name)).name or "attachment"
        ascii_filename = re.sub(r'[^A-Za-z0-9._ -]+', '_', filename).strip() or "attachment"
        disposition = f'inline; filename="{ascii_filename}"; filename*=UTF-8\'\'{quote(filename)}'
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle_customer_save(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(CUSTOMERS_PATH)
        customer_id = (form.get("customer_id") or [""])[0].strip()
        before = None
        row = find_by_id(rows, "customer_id", customer_id) if customer_id else None
        if row:
            before = deepcopy(row)
        else:
            row = {"customer_id": next_customer_id(rows), "created_at": now_iso(), "created_by": actor_from_user(user), "record_status": ACTIVE_RECORD_STATUS}
            rows.append(row)
        row.update(
            {
                "customer_code": (form.get("customer_code") or [""])[0].strip() or row["customer_id"],
                "customer_name": (form.get("customer_name") or [""])[0].strip(),
                "customer_name_en": (form.get("customer_name_en") or [""])[0].strip(),
                "customer_name_zh": (form.get("customer_name_zh") or [""])[0].strip(),
                "customer_registration_number": (form.get("customer_registration_number") or [""])[0].strip(),
                "billing_address": (form.get("billing_address") or [""])[0].strip(),
                "billing_contact_name": (form.get("billing_contact_name") or [""])[0].strip(),
                "billing_contact_email": (form.get("billing_contact_email") or [""])[0].strip(),
                "default_language": (form.get("default_language") or [DEFAULT_LANG])[0],
                "default_payment_terms_days": parse_amount((form.get("default_payment_terms_days") or ["30"])[0]) or 30,
                "default_tax_rate": (form.get("default_tax_rate") or ["10%"]) [0],
                "business_types": [item.strip() for item in (form.get("business_types") or [""])[0].split(",") if item.strip()],
                "notes": (form.get("notes") or [""])[0].strip(),
                "updated_at": now_iso(),
                "updated_by": actor_from_user(user),
            }
        )
        if not row.get("customer_name"):
            raise ValueError("Customer name is required")
        save_json_array(CUSTOMERS_PATH, rows)
        append_audit_log(row["customer_id"], "customer_save", user, before, row)
        self._redirect(with_lang("/customers", lang, message="Customer saved"))

    def _handle_customer_deactivate(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(CUSTOMERS_PATH)
        row = find_by_id(rows, "customer_id", (form.get("customer_id") or [""])[0])
        if not row:
            raise ValueError("Customer not found")
        before = deepcopy(row)
        row["record_status"] = "Inactive"
        row["updated_at"] = now_iso()
        row["updated_by"] = actor_from_user(user)
        save_json_array(CUSTOMERS_PATH, rows)
        append_audit_log(row["customer_id"], "customer_deactivate", user, before, row)
        self._redirect(with_lang("/customers", lang, message="Customer deactivated"))

    def _handle_billing_save(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(BILLINGS_PATH)
        company = load_json_object(COMPANY_PROFILE_PATH, DEFAULT_COMPANY_PROFILE)
        billing_id = (form.get("billing_id") or [""])[0].strip()
        row = find_by_id(rows, "billing_id", billing_id) if billing_id else None
        before = deepcopy(row) if row else None
        if row and row.get("status") not in {"Draft", ""}:
            # Keep the MVP conservative: let finance copy/cancel/payment-track issued records instead of overwriting them.
            raise ValueError("Only Draft billing records can be edited directly. Copy or cancel issued records.")
        if not row:
            row = {
                "billing_id": next_billing_id(rows),
                "billing_no": next_billing_no(rows),
                "record_status": ACTIVE_RECORD_STATUS,
                "status": "Draft",
                "payments": [],
                "history": [],
                "source_type": "manual",
                "source_ocr_draft_id": "",
                "source_file_hash": "",
                "original_invoice_no": "",
                "original_issue_year": "",
                "imported_historical": False,
                "attachments": [],
                "created_at": now_iso(),
                "created_by": actor_from_user(user),
            }
            rows.append(row)
        billing_language = (form.get("billing_language") or [lang])[0]
        customer = self.masterdata_customer((form.get("customer_id") or [""])[0])
        if not customer:
            raise ValueError("Customer is required from TACAI Master Data. Please create or activate the customer in Master Data first.")
        line_items: list[dict[str, Any]] = []
        try:
            line_row_count = min(max(int((form.get("line_row_count") or ["5"])[0]), 5), 50)
        except ValueError:
            line_row_count = 5
        for index in range(line_row_count):
            line = calculate_line(
                (form.get(f"line_description_{index}") or [""])[0],
                (form.get(f"line_quantity_{index}") or [""])[0],
                (form.get(f"line_unit_{index}") or [""])[0],
                (form.get(f"line_unit_price_{index}") or [""])[0],
                (form.get(f"line_tax_rate_{index}") or ["10%"]) [0],
                (form.get(f"line_memo_{index}") or [""])[0],
            )
            if line:
                line["line_id"] = f"LINE-{len(line_items) + 1:03d}"
                line_items.append(line)
        if not line_items:
            raise ValueError("At least one line item is required")
        totals = calculate_totals(line_items)
        bank_info = {key: company.get(key, "") for key in ["bank_name", "bank_branch", "bank_account_type", "bank_account_number", "bank_account_name"]}
        row.update(
            {
                "document_type": (form.get("document_type") or ["invoice"])[0],
                "language": billing_language if billing_language in LANGS else DEFAULT_LANG,
                "business_type": (form.get("business_type") or ["haken_dispatch"])[0],
                "customer_id": customer.get("customer_id", ""),
                "customer_snapshot": customer_snapshot(customer, billing_language),
                "customer_name_snapshot": customer_snapshot(customer, billing_language).get("customer_name", ""),
                "issue_date": (form.get("issue_date") or [today_iso()])[0],
                "due_date": (form.get("due_date") or [add_days(today_iso(), 30)])[0],
                "service_period_from": (form.get("service_period_from") or [""])[0],
                "service_period_to": (form.get("service_period_to") or [""])[0],
                "po_number": (form.get("po_number") or [""])[0].strip(),
                "currency": (form.get("currency") or ["JPY"])[0].strip() or "JPY",
                "subject_name": (form.get("subject_name") or [""])[0].strip(),
                "business_reference_date": (form.get("business_reference_date") or [""])[0].strip(),
                "reference_amount": parse_amount((form.get("reference_amount") or [""])[0]),
                "fee_rate": (form.get("fee_rate") or [""])[0].strip(),
                "line_items": line_items,
                "company_profile_snapshot": company,
                "bank_info_snapshot": bank_info,
                "qualified_invoice_registration_number": company.get("qualified_invoice_registration_number", ""),
                "invoice_note": (form.get("invoice_note") or [""])[0].strip(),
                "internal_memo": (form.get("internal_memo") or [""])[0].strip(),
                "updated_at": now_iso(),
                "updated_by": actor_from_user(user),
                **totals,
            }
        )
        recalc_payment_status(row)
        action = "billing_create" if before is None else "billing_update"
        row["history"].append(history_entry(row, action, user, before_status=(before or {}).get("status", ""), after_status=row.get("status", "Draft"), summary=f"{row.get('billing_no')} saved"))
        save_json_array(BILLINGS_PATH, rows)
        append_audit_log(row["billing_id"], action, user, before, row)
        self._redirect(with_lang("/billings/detail", lang, id=row["billing_id"], message="Billing saved"))

    def _handle_billing_status(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(BILLINGS_PATH)
        row = find_by_id(rows, "billing_id", (form.get("billing_id") or [""])[0])
        if not row:
            raise ValueError("Billing not found")
        status = (form.get("status") or [""])[0]
        if status not in {"Issued", "Sent", "Cancelled"}:
            raise ValueError("Unsupported status action")
        before = deepcopy(row)
        before_status = row.get("status", "")
        row["status"] = status
        stamp_key = {"Issued": "issued", "Sent": "sent", "Cancelled": "cancelled"}[status]
        row[f"{stamp_key}_at"] = now_iso()
        row[f"{stamp_key}_by"] = actor_from_user(user)
        row["updated_at"] = now_iso()
        row["updated_by"] = actor_from_user(user)
        row.setdefault("history", []).append(history_entry(row, f"billing_{status.lower()}", user, before_status, status, f"Status changed to {status}"))
        save_json_array(BILLINGS_PATH, rows)
        append_audit_log(row["billing_id"], f"billing_{status.lower()}", user, before, row)
        self._redirect(with_lang("/billings/detail", lang, id=row["billing_id"], message="Status updated"))

    def _handle_billing_payment(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(BILLINGS_PATH)
        row = find_by_id(rows, "billing_id", (form.get("billing_id") or [""])[0])
        if not row:
            raise ValueError("Billing not found")
        if row.get("status") == "Cancelled":
            raise ValueError("Cancelled billing cannot accept payment")
        amount = parse_amount((form.get("amount") or [""])[0])
        if amount <= 0:
            raise ValueError("Payment amount must be positive")
        before = deepcopy(row)
        payments = row.get("payments", []) if isinstance(row.get("payments"), list) else []
        payments.append(
            {
                "payment_id": next_payment_id(payments),
                "payment_date": (form.get("payment_date") or [today_iso()])[0],
                "amount": amount,
                "method": (form.get("method") or ["bank_transfer"])[0],
                "reference": (form.get("reference") or [""])[0].strip(),
                "memo": (form.get("memo") or [""])[0].strip(),
                "record_status": ACTIVE_RECORD_STATUS,
                "created_at": now_iso(),
                "created_by": actor_from_user(user),
            }
        )
        row["payments"] = payments
        before_status = row.get("status", "")
        recalc_payment_status(row)
        row["updated_at"] = now_iso()
        row["updated_by"] = actor_from_user(user)
        row.setdefault("history", []).append(history_entry(row, "payment_register", user, before_status, row.get("status", ""), f"Payment registered: ¥{money(amount)}"))
        save_json_array(BILLINGS_PATH, rows)
        append_audit_log(row["billing_id"], "payment_register", user, before, row)
        self._redirect(with_lang("/billings/detail", lang, id=row["billing_id"], message="Payment registered"))

    def _handle_billing_copy(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        rows = load_json_array(BILLINGS_PATH)
        source = find_by_id(rows, "billing_id", (form.get("billing_id") or [""])[0])
        if not source:
            raise ValueError("Billing not found")
        new_row = deepcopy(source)
        new_row.update(
            {
                "billing_id": next_billing_id(rows),
                "billing_no": next_billing_no(rows),
                "status": "Draft",
                "payment_status": "unpaid",
                "paid_amount": 0,
                "balance_amount": int(source.get("total_amount", 0) or 0),
                "payments": [],
                "copy_source_id": source.get("billing_id", ""),
                "source_type": "copy",
                "source_ocr_draft_id": "",
                "source_file_hash": "",
                "source_file_attachment_id": "",
                "original_invoice_no": "",
                "original_issue_year": "",
                "imported_historical": False,
                "attachments": [],
                "created_at": now_iso(),
                "created_by": actor_from_user(user),
                "updated_at": now_iso(),
                "updated_by": actor_from_user(user),
                "issued_at": "",
                "issued_by": "",
                "sent_at": "",
                "sent_by": "",
                "cancelled_at": "",
                "cancelled_by": "",
            }
        )
        new_row["history"] = [history_entry(new_row, "billing_copy", user, "", "Draft", f"Copied from {source.get('billing_no','')}")]
        rows.append(new_row)
        save_json_array(BILLINGS_PATH, rows)
        append_audit_log(new_row["billing_id"], "billing_copy", user, source, new_row)
        self._redirect(with_lang("/billings/edit", lang, id=new_row["billing_id"], message="Billing copied"))

    def _handle_ocr_upload(self, form: dict[str, list[str]], uploads: dict[str, dict[str, Any]], user: dict[str, Any], lang: str) -> None:
        upload = uploads.get("source_file") or {}
        filename = str(upload.get("filename") or "").strip()
        data = upload.get("data", b"") if isinstance(upload.get("data", b""), bytes) else b""
        pasted_text = (form.get("pasted_text") or [""])[0].strip()
        if not data and not pasted_text:
            raise ValueError("Upload a source file or paste extracted invoice text.")
        extension = validate_ocr_upload(filename, data) if data else ".txt"
        drafts = load_json_array(OCR_DRAFTS_PATH)
        draft_id = next_ocr_draft_id(drafts)
        safe_name = safe_upload_filename(filename or f"{draft_id}.txt")
        stored_name = f"{draft_id}_{safe_name}"
        stored_path = OCR_UPLOAD_DIR / stored_name
        file_hash = hashlib.sha256(data or pasted_text.encode("utf-8")).hexdigest()
        if data:
            stored_path.write_bytes(data)
        else:
            stored_path.write_text(pasted_text, encoding="utf-8")
        extracted_text, extraction_warnings, engine = extract_text_from_document(stored_path, extension) if data else (normalize_ocr_text(pasted_text), [], "pasted_text")
        if pasted_text and pasted_text not in extracted_text:
            extracted_text = normalize_ocr_text(f"{extracted_text}\n\n{pasted_text}")
        extracted = extract_invoice_fields(extracted_text)
        try:
            customers = self.masterdata_customers()
        except ValueError:
            customers = []
        customer_match = match_customer_from_extraction(extracted, customers)
        duplicate = duplicate_check_for_ocr(extracted, file_hash, str(customer_match.get("matched_customer_id", "")))
        warnings = extraction_warnings + extracted.get("warnings", [])
        draft = {
            "ocr_draft_id": draft_id,
            "record_status": ACTIVE_RECORD_STATUS,
            "ocr_status": "review_required",
            "source_file": {
                "original_filename": filename or "pasted_text.txt",
                "stored_filename": stored_name,
                "relative_path": relative_to_root(stored_path),
                "content_type": upload.get("content_type") or mimetypes.guess_type(filename)[0] or "text/plain",
                "size_bytes": len(data or pasted_text.encode("utf-8")),
                "sha256": file_hash,
                "uploaded_at": now_iso(),
                "uploaded_by": actor_from_user(user),
            },
            "source_document_type": extension.lstrip("."),
            "source_language_hint": (form.get("source_language_hint") or ["auto"])[0],
            "import_mode": (form.get("import_mode") or ["historical_backfill"])[0],
            "raw_text": extracted_text,
            "ocr_engine": engine,
            "extracted": extracted,
            "customer_match": customer_match,
            "duplicate_check": duplicate,
            "warnings": warnings,
            "created_at": now_iso(),
            "created_by": actor_from_user(user),
            "updated_at": now_iso(),
            "updated_by": actor_from_user(user),
        }
        drafts.append(draft)
        save_json_array(OCR_DRAFTS_PATH, drafts)
        append_audit_log(draft_id, "ocr_invoice_upload", user, None, {"ocr_draft_id": draft_id, "source_file": draft["source_file"], "warnings": warnings})
        self._redirect(with_lang("/billings/ocr/review", lang, id=draft_id, message="OCR draft created for review"))

    def _handle_ocr_confirm(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        draft_id = (form.get("ocr_draft_id") or [""])[0]
        drafts = load_json_array(OCR_DRAFTS_PATH)
        draft = find_by_id(drafts, "ocr_draft_id", draft_id)
        if not draft:
            raise ValueError("OCR draft not found")
        if draft.get("ocr_status") == "confirmed":
            raise ValueError("OCR draft is already confirmed")
        billings = load_json_array(BILLINGS_PATH)
        company = load_json_object(COMPANY_PROFILE_PATH, DEFAULT_COMPANY_PROFILE)
        customer = self.masterdata_customer((form.get("customer_id") or [""])[0])
        if not customer:
            raise ValueError("Customer is required from TACAI Master Data before saving OCR import.")
        line_items: list[dict[str, Any]] = []
        try:
            line_row_count = min(max(int((form.get("line_row_count") or ["5"])[0]), 5), 50)
        except ValueError:
            line_row_count = 5
        for index in range(line_row_count):
            line = calculate_line(
                (form.get(f"line_description_{index}") or [""])[0],
                (form.get(f"line_quantity_{index}") or [""])[0],
                (form.get(f"line_unit_{index}") or [""])[0],
                (form.get(f"line_unit_price_{index}") or [""])[0],
                (form.get(f"line_tax_rate_{index}") or ["10%"])[0],
                (form.get(f"line_memo_{index}") or [""])[0],
            )
            if line:
                line["line_id"] = f"LINE-{len(line_items) + 1:03d}"
                line_items.append(line)
        if not line_items:
            raise ValueError("At least one reviewed line item is required")
        totals = calculate_totals(line_items)
        billing_language = (form.get("billing_language") or [lang])[0]
        bank_info = {key: company.get(key, "") for key in ["bank_name", "bank_branch", "bank_account_type", "bank_account_number", "bank_account_name"]}
        duplicate = draft.get("duplicate_check", {}) if isinstance(draft.get("duplicate_check"), dict) else {}
        duplicate_status = str(duplicate.get("status", "none") or "none")
        if duplicate_status != "none" and (form.get("duplicate_ack") or [""])[0] != "yes":
            raise ValueError("Possible duplicate billing records were detected. Please review and acknowledge before saving.")
        source_file = draft.get("source_file", {}) if isinstance(draft.get("source_file"), dict) else {}
        attachments = [attachment_from_ocr_source(source_file, draft_id)] if source_file else []
        row = {
            "billing_id": next_billing_id(billings),
            "billing_no": next_billing_no(billings),
            "record_status": ACTIVE_RECORD_STATUS,
            "status": "Draft",
            "document_type": (form.get("document_type") or ["invoice"])[0],
            "language": billing_language if billing_language in LANGS else DEFAULT_LANG,
            "business_type": (form.get("business_type") or ["other"])[0],
            "customer_id": customer.get("customer_id", ""),
            "customer_snapshot": customer_snapshot(customer, billing_language),
            "customer_name_snapshot": customer_snapshot(customer, billing_language).get("customer_name", ""),
            "issue_date": (form.get("issue_date") or [today_iso()])[0],
            "due_date": (form.get("due_date") or [add_days(today_iso(), 30)])[0],
            "service_period_from": "",
            "service_period_to": "",
            "po_number": "",
            "currency": (form.get("currency") or ["JPY"])[0].strip() or "JPY",
            "subject_name": "",
            "business_reference_date": "",
            "reference_amount": 0,
            "fee_rate": "",
            "line_items": line_items,
            "payments": [],
            "company_profile_snapshot": company,
            "bank_info_snapshot": bank_info,
            "qualified_invoice_registration_number": company.get("qualified_invoice_registration_number", ""),
            "invoice_note": (form.get("invoice_note") or [""])[0].strip(),
            "internal_memo": (form.get("internal_memo") or [""])[0].strip(),
            "source_type": "ocr_import",
            "source_ocr_draft_id": draft_id,
            "source_file_hash": source_file.get("sha256", ""),
            "source_file_attachment_id": attachments[0]["attachment_id"] if attachments else "",
            "attachments": attachments,
            "original_invoice_no": (form.get("original_invoice_no") or [""])[0].strip(),
            "original_issue_year": ((form.get("issue_date") or [""])[0] or "")[:4],
            "imported_historical": True,
            "history": [],
            "created_at": now_iso(),
            "created_by": actor_from_user(user),
            "updated_at": now_iso(),
            "updated_by": actor_from_user(user),
            **totals,
        }
        recalc_payment_status(row)
        row["history"] = [history_entry(row, "billing_ocr_import", user, "", "Draft", f"Created from OCR draft {draft_id}")]
        if duplicate_status != "none":
            row.setdefault("history", []).append(history_entry(row, "duplicate_acknowledged", user, "Draft", "Draft", "Possible duplicate warning acknowledged during OCR import"))
        billings.append(row)
        before_draft = deepcopy(draft)
        draft["ocr_status"] = "confirmed"
        draft["confirmed_at"] = now_iso()
        draft["confirmed_by"] = actor_from_user(user)
        draft["created_billing_id"] = row["billing_id"]
        draft["updated_at"] = now_iso()
        draft["updated_by"] = actor_from_user(user)
        save_json_array(BILLINGS_PATH, billings)
        save_json_array(OCR_DRAFTS_PATH, drafts)
        append_audit_log(row["billing_id"], "billing_ocr_import", user, {"ocr_draft": before_draft, "duplicate_acknowledged": duplicate_status != "none"}, row)
        append_audit_log(draft_id, "ocr_invoice_confirm", user, before_draft, draft)
        self._redirect(with_lang("/billings/detail", lang, id=row["billing_id"], message="OCR import saved as Billing Draft"))

    def _handle_ocr_discard(self, form: dict[str, list[str]], user: dict[str, Any], lang: str) -> None:
        draft_id = (form.get("ocr_draft_id") or [""])[0]
        drafts = load_json_array(OCR_DRAFTS_PATH)
        draft = find_by_id(drafts, "ocr_draft_id", draft_id)
        if not draft:
            raise ValueError("OCR draft not found")
        before = deepcopy(draft)
        draft["ocr_status"] = "discarded"
        draft["record_status"] = "Inactive"
        draft["updated_at"] = now_iso()
        draft["updated_by"] = actor_from_user(user)
        save_json_array(OCR_DRAFTS_PATH, drafts)
        append_audit_log(draft_id, "ocr_invoice_discard", user, before, draft)
        self._redirect(with_lang("/billings", lang, message="OCR draft discarded"))

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    def _read_multipart_form(self) -> tuple[dict[str, list[str]], dict[str, dict[str, Any]]]:
        form: dict[str, list[str]] = {}
        uploads: dict[str, dict[str, Any]] = {}
        content_type = self.headers.get("Content-Type", "")
        if not content_type.startswith("multipart/form-data"):
            return self._read_form(), uploads
        env = {
            "REQUEST_METHOD": "POST",
            "CONTENT_TYPE": content_type,
            "CONTENT_LENGTH": self.headers.get("Content-Length", "0"),
        }
        fields = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ=env, keep_blank_values=True)
        for key in fields.keys():
            items = fields[key]
            if not isinstance(items, list):
                items = [items]
            for item in items:
                if item.filename:
                    uploads[key] = {
                        "filename": item.filename,
                        "content_type": item.type,
                        "data": item.file.read(),
                    }
                else:
                    form.setdefault(key, []).append(item.value)
        return form, uploads

    def _send_html(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _send_text(self, body: str, status: HTTPStatus = HTTPStatus.OK) -> None:
        data = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()


def main() -> None:
    ensure_storage()
    parser = argparse.ArgumentParser(description="Run Customer Billing local MVP web app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8009)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), CustomerBillingHandler)
    print(f"Customer Billing running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Customer Billing...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
