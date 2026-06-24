#!/usr/bin/env python3
"""FileAdmin local MVP web app.

Dependency-free Python standard-library implementation for enterprise document
management. Data is stored as UTF-8 JSON arrays under ../database and uploaded
files are stored under ../attachments.
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
import smtplib
import threading
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
ATTACHMENTS_DIR = ROOT_DIR / "attachments"
DOCUMENTS_PATH = DATABASE_DIR / "documents.json"
DOCUMENT_RECORDS_PATH = DATABASE_DIR / "document_records.json"
VERSIONS_PATH = DATABASE_DIR / "document_versions.json"
FILE_ATTACHMENTS_PATH = DATABASE_DIR / "file_attachments.json"
REMINDERS_PATH = DATABASE_DIR / "contract_reminders.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
CATEGORIES_PATH = DATABASE_DIR / "document_categories.json"
FOLDERS_PATH = DATABASE_DIR / "folders.json"
DOCUMENT_TEMPLATES_PATH = DATABASE_DIR / "document_templates.json"
TEMPLATE_PARAMETERS_PATH = DATABASE_DIR / "template_parameters.json"
TEMPLATE_GENERATION_RUNS_PATH = DATABASE_DIR / "template_generation_runs.json"
TEMPLATE_COUNTRY_RULES_PATH = DATABASE_DIR / "template_country_rules.json"
EMAIL_MESSAGES_PATH = DATABASE_DIR / "email_messages.json"
EMAIL_TEMPLATES_PATH = DATABASE_DIR / "email_templates.json"
TEMPLATE_SOURCE_DIR = ROOT_DIR / "templates"

MODULE_NAME = "fileadmin"
DEFAULT_PORT = 8011
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "fileadmin_flash"
LANG_COOKIE = "fileadmin_lang"
SUPPORTED_LANGS = {"zh", "ja", "en"}
DEFAULT_LANG = "zh"
REQUIRED_MODULE_PERMISSION = "fileadmin.access"
MAX_UPLOAD_BYTES = 25 * 1024 * 1024
JSON_WRITE_LOCK = threading.RLock()
ALLOWED_UPLOAD_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".txt", ".csv", ".png", ".jpg", ".jpeg",
}
ALLOWED_UPLOAD_MIME_PREFIXES = {"text/", "image/"}
ALLOWED_UPLOAD_MIME_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "application/octet-stream",
}
BLOCKED_UPLOAD_EXTENSIONS = {
    ".app", ".bat", ".cmd", ".command", ".com", ".dmg", ".exe", ".html", ".htm",
    ".jar", ".js", ".msi", ".pkg", ".ps1", ".py", ".rb", ".scpt", ".sh", ".vbs",
}

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


APP_BASE_URL = public_base_url("FILEADMIN_PUBLIC_BASE_URL", DEFAULT_PORT)
PORTAL_BASE_URL = public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")
EMAIL_SEND_MODE = os.environ.get("FILEADMIN_EMAIL_SEND_MODE", "dry_run").strip().lower() or "dry_run"
SMTP_HOST = os.environ.get("FILEADMIN_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("FILEADMIN_SMTP_PORT", "587") or 587)
SMTP_USERNAME = os.environ.get("FILEADMIN_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("FILEADMIN_SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("FILEADMIN_SMTP_USE_TLS", "true").strip().lower() in {"1", "true", "yes", "on"}
EMAIL_FROM = os.environ.get("FILEADMIN_EMAIL_FROM", SMTP_USERNAME or "no-reply@tacai.local").strip()
EMAIL_FROM_NAME = os.environ.get("FILEADMIN_EMAIL_FROM_NAME", "TACAI FileAdmin").strip()

DOCUMENT_TYPES = [
    ("contract_client_dispatch", "派遣客户合同 / 派遣顧客契約 / Dispatch Client Contract"),
    ("contract_client_recruitment", "猎头客户合同 / 人材紹介顧客契約 / Recruitment Client Contract"),
    ("contract_rpo", "RPO 合同 / RPO契約 / RPO Contract"),
    ("contract_it_service", "IT 服务合同 / ITサービス契約 / IT Service Contract"),
    ("contract_vendor", "供应商合同 / 仕入先契約 / Vendor Contract"),
    ("company_external_template", "对外文书模板 / 対外文書テンプレート / External Template"),
    ("proposal_quotation", "报价/提案 / 見積・提案 / Proposal & Quotation"),
    ("order_acceptance", "注文书/注文请书 / Order & Acceptance"),
    ("delivery_acceptance", "纳品/检收 / 納品・検収 / Delivery & Acceptance"),
    ("compliance_hr_dispatch", "派遣/HR 合规 / 派遣・HRコンプライアンス / HR Dispatch Compliance"),
    ("internal_policy", "内部规则/SOP / Internal Policy"),
    ("other", "其他 / その他 / Other"),
]
BUSINESS_LINES = [
    ("dispatch", "派遣 / Haken Dispatch"),
    ("recruitment", "猎头/人材紹介 / Recruitment"),
    ("rpo", "RPO"),
    ("it_service", "IT 服务/SES / IT Service"),
    ("corporate", "公司通用 / Corporate"),
    ("finance", "财务 / Finance"),
    ("hr", "HR"),
    ("other", "其他 / Other"),
]
CONFIDENTIALITY_LEVELS = [
    ("public_internal", "内部公开 / Internal"),
    ("business_confidential", "业务机密 / Business Confidential"),
    ("contract_confidential", "合同机密 / Contract Confidential"),
    ("personal_data", "个人信息 / Personal Data"),
    ("highly_sensitive", "高敏 / Highly Sensitive"),
]
DOCUMENT_STATUSES = ["draft", "active", "expiring", "expired", "renewed", "terminated", "archived"]
VERSION_STATUSES = ["draft", "review", "approved", "active", "replaced", "archived"]
REMINDER_STATUSES = ["open", "acknowledged", "in_progress", "completed", "waived"]
TEMPLATE_REVIEW_STATUSES = ["pending", "needs_revision", "reviewed", "approved_generated", "rejected"]
LANGUAGES = [("ja", "日本語"), ("en", "English"), ("zh", "中文")]
FILE_TYPES = [
    ("contract_signed_pdf", "正式签署合同 / Signed Contract PDF"),
    ("contract_draft_word", "合同草稿 Word / Contract Draft Word"),
    ("contract_review_pdf", "法务/审核版 PDF / Review PDF"),
    ("amendment", "补充协议 / Amendment"),
    ("nda", "NDA / 保密协议"),
    ("quotation", "报价/见積 / Quotation"),
    ("purchase_order", "注文书 / Purchase Order"),
    ("delivery_note", "纳品书 / Delivery Note"),
    ("inspection_acceptance", "验收/検収 / Acceptance"),
    ("email_confirmation_pdf", "邮件确认 PDF / Email Evidence"),
    ("external_letter_pdf", "对外文书 PDF / External Letter"),
    ("generated_template_html", "系统生成模板草稿 HTML / Generated Template Draft HTML"),
    ("template_word", "模板 Word / Template Word"),
    ("other", "其他 / Other"),
]
FILE_ROLES = [
    ("main_contract", "主合同 / Main Contract"),
    ("individual_contract", "个别契约 / Individual Contract"),
    ("amendment", "补充协议 / Amendment"),
    ("nda", "NDA"),
    ("price_table", "单价表 / Price Table"),
    ("purchase_order", "订单 / Purchase Order"),
    ("signed_scan", "盖章扫描版 / Signed Scan"),
    ("legal_review", "法务审核 / Legal Review"),
    ("email_evidence", "邮件证据 / Email Evidence"),
    ("template", "模板 / Template"),
    ("generated_draft", "系统生成草稿 / Generated Draft"),
    ("other", "其他 / Other"),
]


class AccessDenied(Exception):
    pass


TRANSLATIONS = {
    "zh": {
        "app.title": "FileAdmin 文件管理",
        "app.subtitle": "TACAI 合同、文件台账、版本、提醒和审计管理",
        "nav.portal": "返回主 Portal",
        "nav.dashboard": "仪表盘",
        "nav.documents": "文件台账",
        "nav.new_document": "新建文件",
        "nav.templates": "模板生成",
        "nav.emails": "邮件发送",
        "nav.reminders": "提醒",
        "nav.audit": "审计",
        "language.label": "语言",
        "current_user": "当前用户",
        "current_entity": "当前法人",
        "no_entity": "无当前法人",
        "current_version": "当前最新版本",
        "version_history": "版本历史",
        "version_policy": "上传新版本后会自动成为最新版本，旧版本保留为历史版本，不会覆盖或删除。",
    },
    "ja": {
        "app.title": "FileAdmin ファイル管理",
        "app.subtitle": "TACAI 契約書・文書台帳・バージョン・リマインダー・監査管理",
        "nav.portal": "Portalへ戻る",
        "nav.dashboard": "ダッシュボード",
        "nav.documents": "文書台帳",
        "nav.new_document": "新規文書",
        "nav.templates": "テンプレート生成",
        "nav.emails": "メール送信",
        "nav.reminders": "リマインダー",
        "nav.audit": "監査",
        "language.label": "言語",
        "current_user": "現在のユーザー",
        "current_entity": "現在の法人",
        "no_entity": "法人未選択",
        "current_version": "現在の最新版",
        "version_history": "バージョン履歴",
        "version_policy": "新しいバージョンをアップロードすると最新版になり、旧バージョンは履歴として保持されます。上書き・削除はしません。",
    },
    "en": {
        "app.title": "FileAdmin Document Management",
        "app.subtitle": "TACAI contracts, document register, versions, reminders, and audit",
        "nav.portal": "Back to Portal",
        "nav.dashboard": "Dashboard",
        "nav.documents": "Documents",
        "nav.new_document": "New Document",
        "nav.templates": "Templates",
        "nav.emails": "Emails",
        "nav.reminders": "Reminders",
        "nav.audit": "Audit",
        "language.label": "Language",
        "current_user": "Current User",
        "current_entity": "Current Entity",
        "no_entity": "No Entity",
        "current_version": "Current Latest Version",
        "version_history": "Version History",
        "version_policy": "Uploading a new version automatically makes it the latest version. Older versions remain in history and are never overwritten or deleted.",
    },
}

BODY_REPLACEMENTS = {
    "zh": {
        "Document Governance": "文件治理",
        "FileAdmin Dashboard": "FileAdmin 仪表盘",
        "Dashboard": "仪表盘",
        "Active Documents": "有效文件",
        "Expiring Contracts": "即将到期合同",
        "Open Reminders": "未处理提醒",
        "Attachments": "附件",
        "Quick Actions": "快捷操作",
        "Recent File Attachments": "最近文件附件",
        "Recent Versions": "最近版本",
        "Recent Audit": "最近审计",
        "Uploaded": "上传时间",
        "Document": "文件",
        "Attachment": "附件",
        "Role": "用途",
        "Current": "当前",
        "Document Register": "文件台账",
        "Search": "检索",
        "Document Type": "文件类型",
        "Business Line": "业务线",
        "Status": "状态",
        "Owner": "负责人",
        "Action": "操作",
        "Actions": "操作",
        "Filter": "筛选",
        "New Document": "新建文件",
        "Register New Document": "登记新文件",
        "Basic Information": "基本信息",
        "Title *": "标题 *",
        "Document No": "文件编号",
        "Contract Details": "合同信息",
        "Template / First Version": "模板 / 第一版",
        "Template / First File Attachment": "模板 / 首个文件附件",
        "Save Document": "保存文件",
        "Save": "保存",
        "Cancel": "取消",
        "Upload File Attachment": "上传文件附件",
        "File Attachments": "文件附件",
        "Back to Register": "返回台账",
        "Document Detail": "文件详情",
        "Document ID": "文件ID",
        "Document No": "文件编号",
        "Business Summary": "业务摘要",
        "Template Generator": "模板生成",
        "Template Library": "模板库",
        "Generate Draft": "生成草稿",
        "Generate from Template": "从模板生成",
        "Template Parameters": "模板参数",
        "Generate Draft and Save to FileAdmin": "生成草稿并保存到 FileAdmin",
        "This is a system-suggested workflow-test template. It is not a formal approved company template and requires human review.": "这是系统建议的流程测试模板，尚不是正式批准的公司模板，使用前需要人工审阅。",
        "Current templates are workflow-test standard drafts: system-suggested / not formally approved / require human review.": "当前模板为流程测试标准草稿：系统建议 / 尚未正式批准 / 需要人工审阅。",
        "Country": "国家/地区",
        "All": "全部",
        "Scope": "适用范围",
    },
    "ja": {
        "FileAdmin Dashboard": "FileAdmin ダッシュボード",
        "轻量管理客户合同、对外文书版本、到期提醒和审计记录。": "顧客契約、対外文書バージョン、期限リマインダー、監査記録を軽量に管理します。",
        "Active Documents": "有効文書",
        "当前未归档文件": "未アーカイブ文書",
        "Expiring Contracts": "期限間近の契約",
        "90 天内到期或已过期": "90日以内に期限到来または期限切れ",
        "Open Reminders": "未完了リマインダー",
        "待处理合同提醒": "対応待ち契約リマインダー",
        "Versions": "バージョン",
        "已上传版本总数": "アップロード済みバージョン総数",
        "Quick Actions": "クイック操作",
        "登记新文件": "新規文書登録",
        "打开文件台账": "文書台帳を開く",
        "查看到期提醒": "期限リマインダーを見る",
        "返回主 Portal": "Portalへ戻る",
        "Recent Versions": "最近のバージョン",
        "Recent Audit": "最近の監査",
        "Document Register": "文書台帳",
        "文件台账": "文書台帳",
        "按业务线、文件类型、状态和负责人查找企业文件。": "業務ライン、文書種別、ステータス、担当者で企業文書を検索します。",
        "Search": "検索",
        "Document Type": "文書種別",
        "Business Line": "業務ライン",
        "Status": "ステータス",
        "Owner": "担当者",
        "Filter": "絞り込み",
        "New Document": "新規文書",
        "新建文件": "新規文書",
        "建立文件 metadata，可同时上传第一版附件。": "文書メタデータを登録し、初版ファイルも同時にアップロードできます。",
        "Basic Information": "基本情報",
        "Title *": "タイトル *",
        "Document No": "文書番号",
        "Contract Details": "契約情報",
        "Template / First Version": "テンプレート / 初版",
        "Save Document": "保存",
        "Upload New Version": "新バージョンをアップロード",
        "Back to Register": "台帳へ戻る",
        "Current Version": "現在の最新版",
        "Version History": "バージョン履歴",
        "当前最新版本": "現在の最新版",
        "版本历史": "バージョン履歴",
        "上传新版本后会自动成为最新版本；旧版本会保留为 replaced 历史版本，并保留上传人与变更原因。": "新しいバージョンをアップロードすると最新版になります。旧バージョンは replaced 履歴として保持され、アップロード者と変更理由も残ります。",
        "Change Reason": "変更理由",
        "Download Current Version": "最新版をダウンロード",
        "Audit Summary": "監査サマリー",
        "Archive Document": "文書をアーカイブ",
        "Archive Only": "アーカイブのみ",
        "Contract Reminders": "契約リマインダー",
        "合同到期与续约提醒": "契約期限・更新リマインダー",
        "Audit Logs": "監査ログ",
        "审计日志": "監査ログ",
        "Template Generator": "テンプレート生成",
        "模板生成": "テンプレート生成",
        "先用系统建议标准模板跑通流程；正式业务模板待后续审批后再纳入。": "まずシステム推奨の標準テンプレートでワークフローを検証し、正式な業務テンプレートは後続承認後に追加します。",
        "当前模板为 workflow test 标准草稿：System-suggested standard / Not formal approved / Requires human review.": "現在のテンプレートはワークフロー検証用の標準ドラフトです：システム推奨 / 正式未承認 / 人によるレビュー必須。",
        "Template Library": "テンプレートライブラリ",
        "Generate Draft": "ドラフト生成",
        "Generate from Template": "テンプレートから生成",
        "生成草稿": "ドラフト生成",
        "输入参数后生成 HTML 草稿，并自动进入 FileAdmin 文件台账。": "パラメータを入力すると HTML ドラフトを生成し、FileAdmin の文書台帳に自動登録します。",
        "This is a system-suggested workflow-test template. It is not a formal approved company template and requires human review.": "これはシステム推奨のワークフロー検証用テンプレートです。正式承認済みの会社テンプレートではなく、人によるレビューが必要です。",
        "Document Metadata": "文書メタデータ",
        "Template Parameters": "テンプレートパラメータ",
        "Generate Draft and Save to FileAdmin": "ドラフトを生成して FileAdmin に保存",
        "Template Generation Run": "テンプレート生成記録",
        "生成记录保存模板版本、参数快照、文件和审阅状态。": "生成記録にはテンプレート版、パラメータスナップショット、ファイル、レビュー状態を保存します。",
        "Run Summary": "生成サマリー",
        "Open FileAdmin Document": "FileAdmin 文書を開く",
        "Download Generated Draft": "生成ドラフトをダウンロード",
        "Back to Templates": "テンプレートへ戻る",
        "Parameter Snapshot": "パラメータスナップショット",
        "Review Generated Draft": "生成ドラフトをレビュー",
        "Review Status": "レビュー状態",
        "Review Notes": "レビューコメント",
        "Update Review": "レビュー更新",
        "Template Generation": "テンプレート生成",
        "Dashboard": "ダッシュボード",
        "Document Governance": "文書ガバナンス",
        "Attachments": "添付ファイル",
        "Recent File Attachments": "最近の添付ファイル",
        "Uploaded": "アップロード日時",
        "Document": "文書",
        "Attachment": "添付ファイル",
        "Role": "役割",
        "Current": "現行",
        "Action": "操作",
        "Actions": "操作",
        "File Attachments": "ファイル添付",
        "Upload File Attachment": "ファイル添付をアップロード",
        "Document Detail": "文書詳細",
        "Document ID": "文書ID",
        "Business Summary": "業務サマリー",
        "Template / First File Attachment": "テンプレート / 初回添付ファイル",
        "Save": "保存",
        "Cancel": "キャンセル",
        "Country": "国・地域",
        "All": "すべて",
        "Scope": "適用範囲",
        "输入参数后生成 HTML 草稿，并自动进入 FileAdmin 文書台帳。": "パラメータを入力すると HTML ドラフトを生成し、FileAdmin の文書台帳に自動登録します。",
    },
    "en": {
        "FileAdmin Dashboard": "FileAdmin Dashboard",
        "轻量管理客户合同、对外文书版本、到期提醒和审计记录。": "Lightweight management for customer contracts, external document versions, expiry reminders, and audit records.",
        "当前未归档文件": "Non-archived documents",
        "90 天内到期或已过期": "Due within 90 days or already expired",
        "待处理合同提醒": "Pending contract reminders",
        "已上传版本总数": "Total uploaded versions",
        "登记新文件": "Register New Document",
        "打开文件台账": "Open Document Register",
        "查看到期提醒": "View Reminders",
        "返回主 Portal": "Back to Portal",
        "文件台账": "Document Register",
        "按业务线、文件类型、状态和负责人查找企业文件。": "Find enterprise documents by business line, document type, status, and owner.",
        "新建文件": "New Document",
        "建立文件 metadata，可同时上传第一版附件。": "Create document metadata and optionally upload the first version attachment.",
        "合同到期与续约提醒": "Contract Expiry and Renewal Reminders",
        "审计日志": "Audit Logs",
        "Template Generator": "Template Generator",
        "模板生成": "Template Generator",
        "先用系统建议标准模板跑通流程；正式业务模板待后续审批后再纳入。": "Use system-suggested standard templates to validate the workflow first; formal business templates will be added after later approval.",
        "当前模板为 workflow test 标准草稿：System-suggested standard / Not formal approved / Requires human review.": "Current templates are workflow-test standard drafts: system-suggested / not formally approved / require human review.",
        "生成草稿": "Generate Draft",
        "输入参数后生成 HTML 草稿，并自动进入 FileAdmin 文件台账。": "Enter parameters to generate an HTML draft and automatically register it in FileAdmin.",
        "生成记录保存模板版本、参数快照、文件和审阅状态。": "The generation record stores template version, parameter snapshot, generated file, and review status.",
        "当前最新版本": "Current Latest Version",
        "版本历史": "Version History",
        "上传新版本后会自动成为最新版本；旧版本会保留为 replaced 历史版本，并保留上传人与变更原因。": "Uploading a new version automatically makes it the latest. Older versions remain as replaced history with uploader and change reason retained.",
    },
}


def normalize_lang(value: str | None) -> str:
    return value if value in SUPPORTED_LANGS else DEFAULT_LANG


def tr(lang: str, key: str) -> str:
    lang = normalize_lang(lang)
    return TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).get(key, key)


def url_with_lang(path: str, lang: str) -> str:
    parsed = urlparse(path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["lang"] = [normalize_lang(lang)]
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()


def language_switcher_html(current_path: str, lang: str) -> str:
    links = []
    labels = {"zh": "中文", "ja": "日本語", "en": "English"}
    for code in ("zh", "ja", "en"):
        cls = "active" if normalize_lang(lang) == code else ""
        links.append(f'<a class="lang-link {h(cls)}" href="{h(url_with_lang(current_path, code))}">{h(labels[code])}</a>')
    return f'<span class="language-switcher"><span class="language-label">{h(tr(lang, "language.label"))}</span>{"".join(links)}</span>'


def localize_body(body: str, lang: str) -> str:
    for old, new in BODY_REPLACEMENTS.get(normalize_lang(lang), {}).items():
        body = body.replace(old, new)
    return body


def ensure_storage() -> None:
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)
    ATTACHMENTS_DIR.mkdir(parents=True, exist_ok=True)
    for path in [
        DOCUMENTS_PATH, DOCUMENT_RECORDS_PATH, VERSIONS_PATH, FILE_ATTACHMENTS_PATH,
        REMINDERS_PATH, AUDIT_LOGS_PATH, CATEGORIES_PATH, FOLDERS_PATH,
        DOCUMENT_TEMPLATES_PATH, TEMPLATE_PARAMETERS_PATH, TEMPLATE_GENERATION_RUNS_PATH,
        TEMPLATE_COUNTRY_RULES_PATH, EMAIL_MESSAGES_PATH, EMAIL_TEMPLATES_PATH,
    ]:
        if not path.exists():
            path.write_text("[]\n", encoding="utf-8")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def today() -> date:
    return datetime.now(timezone.utc).date()


def parse_date(value: str) -> date | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def date_add_days(value: str, delta: int) -> str:
    parsed = parse_date(value)
    if not parsed:
        return ""
    return (parsed + timedelta(days=delta)).isoformat()


def days_until(value: str) -> int | None:
    parsed = parse_date(value)
    if not parsed:
        return None
    return (parsed - today()).days


def h(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


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


def save_json_array(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically save a JSON array with a process-local write lock.

    FileAdmin is served by ThreadingHTTPServer, so two uploads can otherwise
    rewrite the same JSON file at the same time. The lock prevents in-process
    races; the temporary file plus os.replace avoids leaving partial JSON if a
    write is interrupted.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(f".{path.name}.tmp")
    with JSON_WRITE_LOCK:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)


def save_document_record_shadow(doc: dict[str, Any]) -> None:
    """Keep document_records.json aligned with the existing documents.json MVP file."""
    rows = load_json_array(DOCUMENT_RECORDS_PATH)
    document_id = str(doc.get("document_id", ""))
    for index, row in enumerate(rows):
        if str(row.get("document_id", "")) == document_id:
            rows[index] = doc
            save_json_array(DOCUMENT_RECORDS_PATH, rows)
            return
    rows.append(doc)
    save_json_array(DOCUMENT_RECORDS_PATH, rows)


def next_sequence_id(rows: list[dict[str, Any]], key: str, prefix: str, width: int = 4) -> str:
    year = datetime.now(timezone.utc).year
    prefix_with_year = f"{prefix}-{year}-"
    max_num = 0
    for row in rows:
        value = str(row.get(key, ""))
        if value.startswith(prefix_with_year):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix_with_year}{max_num + 1:0{width}d}"


def safe_filename(filename: str) -> str:
    base = Path(filename or "").name.strip() or "attachment"
    base = re.sub(r"[^A-Za-z0-9._\-぀-ヿ㐀-鿿々ー]+", "_", base)
    return base[:160] or "attachment"


def validate_uploaded_file(filename: str, content: bytes, content_type: str) -> None:
    original = Path(filename or "").name.strip()
    suffix = Path(original).suffix.lower()
    if not original:
        raise ValueError("Uploaded file must have a filename.")
    if suffix in BLOCKED_UPLOAD_EXTENSIONS:
        raise ValueError(f"File type {suffix} is blocked for security reasons.")
    if suffix not in ALLOWED_UPLOAD_EXTENSIONS:
        raise ValueError(f"File type {suffix or '(none)'} is not allowed in the FileAdmin MVP.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Uploaded file exceeds the 25MB MVP limit.")
    normalized_mime = (content_type or mimetypes.guess_type(original)[0] or "application/octet-stream").split(";", 1)[0].strip().lower()
    if normalized_mime not in ALLOWED_UPLOAD_MIME_TYPES and not any(normalized_mime.startswith(prefix) for prefix in ALLOWED_UPLOAD_MIME_PREFIXES):
        raise ValueError(f"MIME type {normalized_mime} is not allowed.")


def user_display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return "anonymous"
    for key in ["display_name", "username", "email", "user_id"]:
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return "unknown_user"


def audit_actor_from_user(user: dict[str, Any] | None) -> str:
    if not user:
        return "anonymous"
    for key in ["username", "email", "display_name", "user_id"]:
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return "unknown_user"


def user_entity(user: dict[str, Any] | None) -> dict[str, str]:
    if not user:
        return {}
    entity = user.get("entity") if isinstance(user.get("entity"), dict) else {}
    if entity:
        return {str(k): str(v) for k, v in entity.items() if v is not None}
    result = {}
    for key in ["entity_id", "entity_code", "entity_name", "entity_name_en", "entity_name_ja", "entity_name_zh"]:
        value = str(user.get(key, "")).strip()
        if value:
            result[key] = value
    return result


def entity_label(entity: dict[str, Any]) -> str:
    for keys in [("entity_code", "entity_name_en"), ("entity_code", "entity_name"), ("entity_id", "entity_name_en")]:
        left = str(entity.get(keys[0], "")).strip()
        right = str(entity.get(keys[1], "")).strip()
        if left and right:
            return f"{left} - {right}"
    return str(entity.get("entity_code") or entity.get("entity_id") or entity.get("entity_name_en") or "").strip()


def entity_select_options_for_user(user: dict[str, Any], selected_entity_id: str = "", include_blank: bool = False) -> str:
    selected_entity_id = str(selected_entity_id or "").strip()
    choices: dict[str, str] = {}
    current = user_entity(user)
    current_key = str(current.get("entity_id") or current.get("entity_code") or "").strip()
    if current_key:
        choices[current_key] = entity_label(current) or current_key
    if is_system_admin(user):
        for doc in documents(include_archived=True):
            key = str(doc.get("entity_id", "")).strip()
            if key:
                choices.setdefault(key, " - ".join(bit for bit in [key, str(doc.get("entity_name_snapshot", "")).strip()] if bit))
    options = []
    if include_blank:
        options.append(f"<option value=''{' selected' if not selected_entity_id else ''}>All</option>")
    for key, label in sorted(choices.items(), key=lambda item: item[1]):
        selected = " selected" if key == selected_entity_id else ""
        options.append(f"<option value='{h(key)}'{selected}>{h(label)}</option>")
    return "".join(options)


def has_permission(user: dict[str, Any] | None, permission_key: str) -> bool:
    if not user:
        return False
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return "system_admin" in roles or "*" in permissions or permission_key in permissions


def user_role_keys(user: dict[str, Any] | None) -> set[str]:
    if not user:
        return set()
    return {str(role).strip().lower() for role in user.get("roles", []) if str(role).strip()}


def is_system_admin(user: dict[str, Any] | None) -> bool:
    return bool(user and ("system_admin" in user_role_keys(user) or "*" in set(user.get("permissions", []))))


def user_entity_id(user: dict[str, Any] | None) -> str:
    entity = user_entity(user)
    return str(entity.get("entity_id") or entity.get("entity_code") or "").strip()


def confidentiality_allows(user: dict[str, Any] | None, level: str) -> bool:
    normalized = (level or "").strip().lower()
    if not normalized or normalized in {"public_internal", "business_confidential", "contract_confidential"}:
        return True
    if is_system_admin(user) or has_permission(user, "fileadmin.sensitive.view"):
        return True
    roles = user_role_keys(user)
    if normalized == "personal_data" and ("hr_manager" in roles or "document_admin" in roles):
        return True
    return False


def can_view_document(user: dict[str, Any] | None, doc: dict[str, Any] | None) -> bool:
    if not user or not doc or not has_permission(user, "fileadmin.view"):
        return False
    if is_system_admin(user):
        return True
    doc_entity = str(doc.get("entity_id", "")).strip()
    current_entity = user_entity_id(user)
    if doc_entity and current_entity and doc_entity not in {current_entity, str(user_entity(user).get("entity_code", "")).strip()}:
        if not has_permission(user, "fileadmin.cross_entity.view"):
            return False
    if not confidentiality_allows(user, str(doc.get("confidentiality_level", ""))):
        return False
    return True


def can_upload_attachment(user: dict[str, Any] | None, doc: dict[str, Any] | None) -> bool:
    return bool(doc and doc.get("status") != "archived" and has_permission(user, "fileadmin.upload") and can_view_document(user, doc))


def can_download_attachment(user: dict[str, Any] | None, doc: dict[str, Any] | None, attachment: dict[str, Any] | None) -> bool:
    if not attachment or not has_permission(user, "fileadmin.download") or not can_view_document(user, doc):
        return False
    return confidentiality_allows(user, str(attachment.get("confidentiality_level", "")))


def can_archive_document(user: dict[str, Any] | None, doc: dict[str, Any] | None) -> bool:
    return bool(doc and doc.get("status") != "archived" and has_permission(user, "fileadmin.archive") and can_view_document(user, doc))


def email_send_eligibility(user: dict[str, Any] | None, doc: dict[str, Any] | None, attachment: dict[str, Any] | None) -> tuple[bool, str]:
    if not doc or not attachment:
        return False, "Blocked: document or attachment not found."
    if doc.get("status") == "archived":
        return False, "Blocked: archived documents cannot be emailed."
    if not can_download_attachment(user, doc, attachment):
        return False, "Blocked: missing download permission or confidentiality access."
    if not (has_permission(user, "fileadmin.upload") or has_permission(user, "fileadmin.archive")):
        return False, "Blocked: email sending requires reviewer-level permission."
    if str(attachment.get("confidentiality_level", "")) == "highly_sensitive":
        return False, "Blocked: highly sensitive files cannot be emailed."
    file_status = str(attachment.get("file_status") or attachment.get("status") or "").strip()
    if file_status in {"approved", "active", "signed"}:
        return True, "Eligible: file status is approved/active/signed."
    doc_template = doc.get("template") if isinstance(doc.get("template"), dict) else {}
    if doc_template.get("is_template_generated") and doc_template.get("review_status") == "approved_generated":
        return True, "Eligible: generated draft review status is approved_generated."
    if file_status in {"draft", "review", "pending", "needs_revision", ""}:
        return False, "Blocked: file is still draft/review and must be approved first."
    return False, f"Blocked: file status {file_status} is not eligible for email sending."


def can_send_attachment_email(user: dict[str, Any] | None, doc: dict[str, Any] | None, attachment: dict[str, Any] | None) -> bool:
    allowed, _ = email_send_eligibility(user, doc, attachment)
    return allowed


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


def documents() -> list[dict[str, Any]]:
    return load_json_array(DOCUMENTS_PATH)


def versions() -> list[dict[str, Any]]:
    return load_json_array(VERSIONS_PATH)


def file_attachments() -> list[dict[str, Any]]:
    return load_json_array(FILE_ATTACHMENTS_PATH)


def reminders() -> list[dict[str, Any]]:
    return load_json_array(REMINDERS_PATH)


def audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def document_templates() -> list[dict[str, Any]]:
    return load_json_array(DOCUMENT_TEMPLATES_PATH)


def template_parameters() -> list[dict[str, Any]]:
    return load_json_array(TEMPLATE_PARAMETERS_PATH)


def template_generation_runs() -> list[dict[str, Any]]:
    return load_json_array(TEMPLATE_GENERATION_RUNS_PATH)


def template_country_rules() -> list[dict[str, Any]]:
    return load_json_array(TEMPLATE_COUNTRY_RULES_PATH)


def email_messages() -> list[dict[str, Any]]:
    return load_json_array(EMAIL_MESSAGES_PATH)


def email_templates() -> list[dict[str, Any]]:
    return load_json_array(EMAIL_TEMPLATES_PATH)


def find_document(document_id: str) -> dict[str, Any] | None:
    for row in documents():
        if str(row.get("document_id", "")) == document_id:
            return row
    return None


def find_version(version_id: str) -> dict[str, Any] | None:
    for row in versions():
        if str(row.get("version_id", "")) == version_id:
            return row
    return None


def find_file_attachment(file_id: str) -> dict[str, Any] | None:
    for row in file_attachments():
        if str(row.get("file_id", "")) == file_id:
            return row
    return None


def find_template(template_id: str) -> dict[str, Any] | None:
    for row in document_templates():
        if str(row.get("template_id", "")) == template_id:
            return row
    return None


def template_params_for(template_id: str) -> list[dict[str, Any]]:
    rows = [row for row in template_parameters() if str(row.get("template_id", "")) == template_id]
    return sorted(rows, key=lambda row: int(row.get("sort_order") or 0))


def find_generation_run(generation_id: str) -> dict[str, Any] | None:
    for row in template_generation_runs():
        if str(row.get("generation_id", "")) == generation_id:
            return row
    return None


def find_email_message(email_id: str) -> dict[str, Any] | None:
    for row in email_messages():
        if str(row.get("email_id", "")) == email_id:
            return row
    return None


def find_email_template(email_template_id: str) -> dict[str, Any] | None:
    for row in email_templates():
        if str(row.get("email_template_id", "")) == email_template_id:
            return row
    return None


def document_email_messages(document_id: str) -> list[dict[str, Any]]:
    return [row for row in email_messages() if str(row.get("document_id", "")) == document_id]


def document_versions(document_id: str) -> list[dict[str, Any]]:
    return [row for row in versions() if str(row.get("document_id", "")) == document_id]


def document_file_attachments(document_id: str) -> list[dict[str, Any]]:
    return [row for row in file_attachments() if str(row.get("document_id", "")) == document_id and not row.get("deleted")]


def document_reminders(document_id: str) -> list[dict[str, Any]]:
    return [row for row in reminders() if str(row.get("document_id", "")) == document_id]


def document_email_messages(document_id: str) -> list[dict[str, Any]]:
    return [row for row in email_messages() if str(row.get("document_id", "")) == document_id]


def active_documents() -> list[dict[str, Any]]:
    return [row for row in documents() if row.get("status") != "archived"]


def document_title(document_id: str) -> str:
    doc = find_document(document_id)
    return str(doc.get("title", document_id)) if doc else document_id


def audit_payload_hash(row: dict[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key != "event_hash"}
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def append_audit_log(
    record_id: str,
    record_type: str,
    action: str,
    before_value: Any,
    after_value: Any,
    user: dict[str, Any] | None,
    handler: BaseHTTPRequestHandler | None = None,
    notes: str = "",
) -> None:
    rows = audit_logs()
    entity = user_entity(user)
    previous_hash = str(rows[-1].get("event_hash", "")) if rows else ""
    row = {
        "audit_id": next_sequence_id(rows, "audit_id", "FAA", width=6),
        "module": MODULE_NAME,
        "record_id": record_id,
        "record_type": record_type,
        "action": action,
        "user": audit_actor_from_user(user),
        "user_name_snapshot": user_display_name(user),
        "timestamp": now_iso(),
        "before_value": before_value if before_value is not None else {},
        "after_value": after_value if after_value is not None else {},
        "ip_address": handler.client_address[0] if handler else "",
        "user_agent": handler.headers.get("User-Agent", "") if handler else "",
        "notes": notes,
        "previous_hash": previous_hash,
    }
    if entity:
        row.update({
            "entity_id": entity.get("entity_id", ""),
            "entity_code": entity.get("entity_code", ""),
            "entity_name": entity.get("entity_name_en") or entity.get("entity_name") or "",
        })
    row["event_hash"] = audit_payload_hash(row)
    rows.append(row)
    save_json_array(AUDIT_LOGS_PATH, rows)


def status_badge(status: str) -> str:
    normalized = (status or "unknown").lower().replace("_", "-")
    return f'<span class="status-badge status-{h(normalized)}">{h(status or "unknown")}</span>'


def option_html(options: list[tuple[str, str]], selected: str = "") -> str:
    return "".join(
        f'<option value="{h(value)}" {"selected" if value == selected else ""}>{h(label)}</option>'
        for value, label in options
    )


def text_option_html(values: list[str], selected: str = "") -> str:
    return "".join(
        f'<option value="{h(value)}" {"selected" if value == selected else ""}>{h(value)}</option>'
        for value in values
    )


def current_version_for(doc: dict[str, Any]) -> dict[str, Any] | None:
    current_id = str(doc.get("current_version_id", ""))
    if current_id:
        found = find_version(current_id)
        if found:
            return found
    for version in document_versions(str(doc.get("document_id", ""))):
        if version.get("is_current"):
            return version
    return None


def reminder_bucket(row: dict[str, Any]) -> str:
    if row.get("status") in {"completed", "waived"}:
        return "completed"
    days = days_until(str(row.get("reminder_date", "")))
    if days is None:
        return "unscheduled"
    if days < 0:
        return "overdue"
    if days <= 7:
        return "7 days"
    if days <= 14:
        return "14 days"
    if days <= 30:
        return "30 days"
    if days <= 60:
        return "60 days"
    if days <= 90:
        return "90 days"
    return "later"


def build_contract_payload(form: dict[str, str]) -> dict[str, Any]:
    return {
        "is_contract": form.get("is_contract") == "yes" or form.get("document_type", "").startswith("contract_"),
        "contract_start_date": form.get("contract_start_date", "").strip(),
        "contract_end_date": form.get("contract_end_date", "").strip(),
        "auto_renewal": form.get("auto_renewal") == "yes",
        "renewal_notice_days": int(form.get("renewal_notice_days") or 0),
        "termination_notice_days": int(form.get("termination_notice_days") or 0),
        "contract_amount": form.get("contract_amount", "").strip() or None,
        "currency": form.get("currency", "JPY").strip() or "JPY",
        "payment_terms": form.get("payment_terms", "").strip(),
        "fee_terms": form.get("fee_terms", "").strip(),
        "guarantee_terms": form.get("guarantee_terms", "").strip(),
        "risk_notes": form.get("risk_notes", "").strip(),
    }


def build_template_payload(form: dict[str, str]) -> dict[str, Any]:
    return {
        "is_template": form.get("is_template") == "yes" or form.get("document_type") == "company_external_template",
        "template_code": form.get("template_code", "").strip(),
        "is_current_template": form.get("is_current_template") == "yes",
        "effective_date": form.get("effective_date", "").strip(),
        "retired_date": form.get("retired_date", "").strip(),
    }


def document_no_for(form: dict[str, str], rows: list[dict[str, Any]]) -> str:
    explicit = form.get("document_no", "").strip()
    if explicit:
        return explicit
    doc_type = form.get("document_type", "")
    business_line = form.get("business_line", "")
    prefix_map = {
        "dispatch": "CT-DISP",
        "recruitment": "CT-REC",
        "rpo": "CT-RPO",
        "it_service": "CT-IT",
        "finance": "FA-FIN",
        "hr": "FA-HR",
        "corporate": "FA-CORP",
    }
    if doc_type == "contract_vendor":
        prefix = "CT-VEN"
    elif doc_type.startswith("contract_"):
        prefix = prefix_map.get(business_line, "CT-CORP")
    elif doc_type == "company_external_template":
        prefix = "TPL"
    else:
        prefix = "FA-DOC"
    year = datetime.now(timezone.utc).year
    prefix_with_year = f"{prefix}-{year}-"
    max_num = 0
    for row in rows:
        value = str(row.get("document_no", ""))
        if value.startswith(prefix_with_year):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix_with_year}{max_num + 1:04d}"


def form_bool(form: dict[str, str], key: str, default: bool = False) -> bool:
    value = form.get(key, "").strip().lower()
    if not value:
        return default
    return value in {"yes", "true", "1", "on"}


def save_uploaded_version(document_id: str, doc: dict[str, Any], form: dict[str, str], file_tuple: tuple[str, bytes, str], user: dict[str, Any], handler: BaseHTTPRequestHandler | None) -> dict[str, Any]:
    """Save an uploaded file as both an attachment and legacy version record.

    The legacy `document_versions.json` record is retained for compatibility with
    the first FileAdmin MVP. The new source of truth for package-style document
    management is `file_attachments.json`, where each uploaded file carries its
    own title, description, type, role, flags, and storage metadata.
    """
    filename, content, content_type = file_tuple
    if not filename or not content:
        raise ValueError("Please choose a file to upload.")
    validate_uploaded_file(filename, content, content_type)

    all_versions = versions()
    all_files = file_attachments()
    version_id = next_sequence_id(all_versions, "version_id", "FAV")
    file_id = next_sequence_id(all_files, "file_id", "FILE")
    original_filename = Path(filename).name
    safe_name = safe_filename(original_filename)
    category = safe_filename(str(doc.get("document_type") or "other"))
    version_no = form.get("version_no", "").strip() or "v1.0"
    relative_path = Path("attachments") / category / document_id / f"{file_id}__{safe_filename(version_no)}__{safe_name}"
    target_path = ROOT_DIR / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        raise ValueError("Upload target already exists; refusing to overwrite.")
    temp_path = target_path.with_name(f".{target_path.name}.uploading")
    if temp_path.exists():
        raise ValueError("Temporary upload target already exists; retry the upload later.")
    try:
        with temp_path.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    sha256 = hashlib.sha256(content).hexdigest()

    file_role = form.get("file_role", "").strip() or "main_contract"
    is_current = form_bool(form, "is_current", True)
    file_status = form.get("file_status", "").strip() or form.get("version_status", "").strip() or "active"

    if is_current:
        for row in all_files:
            if str(row.get("document_id")) == document_id and str(row.get("file_role", "")) == file_role and row.get("is_current"):
                row["is_current"] = False
                row["file_status"] = "replaced"
                row["updated_at"] = now_iso()
                row["updated_by"] = audit_actor_from_user(user)
        for row in all_versions:
            if str(row.get("document_id")) == document_id and row.get("is_current"):
                row["is_current"] = False
                row["status"] = "replaced"

    uploaded_at = now_iso()
    mime_type = content_type or mimetypes.guess_type(original_filename)[0] or "application/octet-stream"
    file_title = form.get("file_title", "").strip() or form.get("version_title", "").strip() or original_filename
    file_description = form.get("file_description", "").strip() or form.get("version_notes", "").strip()

    attachment = {
        "file_id": file_id,
        "document_id": document_id,
        "linked_version_id": version_id,
        "file_title": file_title,
        "file_description": file_description,
        "file_type": form.get("file_type", "").strip() or "contract_signed_pdf",
        "file_role": file_role,
        "version_no": version_no,
        "file_status": file_status,
        "is_current": is_current,
        "is_signed": form_bool(form, "is_signed", False),
        "is_original_scan": form_bool(form, "is_original_scan", False),
        "language": form.get("file_language", "").strip() or form.get("language", "").strip() or doc.get("language", "ja"),
        "confidentiality_level": form.get("file_confidentiality_level", "").strip() or doc.get("confidentiality_level", "contract_confidential"),
        "original_filename": original_filename,
        "stored_filename": target_path.name,
        "storage_path": str(relative_path),
        "mime_type": mime_type,
        "file_extension": Path(original_filename).suffix,
        "file_size_bytes": len(content),
        "checksum_sha256": sha256,
        "file_effective_start_date": form.get("file_effective_start_date", "").strip(),
        "file_effective_end_date": form.get("file_effective_end_date", "").strip(),
        "uploaded_by": audit_actor_from_user(user),
        "uploaded_at": uploaded_at,
        "updated_by": audit_actor_from_user(user),
        "updated_at": uploaded_at,
        "archived": False,
        "deleted": False,
        "notes": form.get("version_notes", "").strip(),
    }

    version = {
        "version_id": version_id,
        "document_id": document_id,
        "file_id": file_id,
        "version_no": version_no,
        "version_title": file_title,
        "status": file_status,
        "is_current": is_current,
        "original_filename": original_filename,
        "stored_path": str(relative_path),
        "mime_type": mime_type,
        "file_size_bytes": len(content),
        "sha256": sha256,
        "uploaded_by": audit_actor_from_user(user),
        "uploaded_at": uploaded_at,
        "change_reason": form.get("change_reason", "").strip(),
        "approved_by": form.get("approved_by", "").strip(),
        "approved_at": form.get("approved_at", "").strip(),
        "notes": file_description,
    }
    all_files.append(attachment)
    all_versions.append(version)
    save_json_array(FILE_ATTACHMENTS_PATH, all_files)
    save_json_array(VERSIONS_PATH, all_versions)
    append_audit_log(document_id, "file_attachment", "file_uploaded", {}, attachment, user, handler)
    append_audit_log(document_id, "document_version", "version_uploaded", {}, version, user, handler)
    return attachment


def country_rule_for(country_code: str) -> dict[str, Any]:
    for row in template_country_rules():
        if str(row.get("country_code", "")).upper() == country_code.upper():
            return row
    return {}


def template_document_type(template: dict[str, Any]) -> str:
    explicit = str(template.get("document_type", "")).strip()
    if explicit:
        return explicit
    category = str(template.get("template_category", "")).strip().lower()
    if category == "offer_letter":
        return "compliance_hr_dispatch"
    if category == "recruitment_agreement":
        return "contract_client_recruitment"
    if category == "dispatch_agreement":
        return "contract_client_dispatch"
    if category == "rpo_agreement":
        return "contract_rpo"
    return "other"


def template_source_text(template: dict[str, Any]) -> str:
    source_path = str(template.get("source_path", "")).strip()
    if not source_path:
        raise ValueError("Template source path is missing.")
    target = (TEMPLATE_SOURCE_DIR / source_path).resolve()
    source_root = TEMPLATE_SOURCE_DIR.resolve()
    if target != source_root and source_root not in target.parents:
        raise ValueError("Template source path is outside the template library.")
    if not target.exists() or not target.is_file():
        raise ValueError(f"Template source file not found: {source_path}")
    return target.read_text(encoding="utf-8")


def validate_template_parameters(template: dict[str, Any], form: dict[str, str]) -> dict[str, str]:
    params = template_params_for(str(template.get("template_id", "")))
    if not params:
        raise ValueError("Template has no parameter definition.")
    country_rule = country_rule_for(str(template.get("country_code", "")))
    default_currency = str(country_rule.get("default_currency", "")).strip()
    values: dict[str, str] = {}
    missing: list[str] = []
    for param in params:
        key = str(param.get("parameter_key", "")).strip()
        if not key:
            continue
        raw = form.get(f"param_{key}", "").strip()
        if not raw and key == "currency" and default_currency:
            raw = default_currency
        if not raw and param.get("default_value") is not None:
            raw = str(param.get("default_value", "")).strip()
        if param.get("required") and not raw:
            missing.append(str(param.get("label") or key))
            continue
        if str(param.get("data_type", "")).strip() == "date" and raw and not parse_date(raw):
            raise ValueError(f"Invalid date for {param.get('label') or key}; use YYYY-MM-DD.")
        if len(raw) > int(param.get("max_length") or 2000):
            raise ValueError(f"Value for {param.get('label') or key} is too long.")
        values[key] = raw
    if missing:
        raise ValueError("Missing required template parameters: " + ", ".join(missing))
    return values


def render_template_text(source_text: str, values: dict[str, str]) -> str:
    rendered = source_text
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", value)
    unreplaced = sorted(set(re.findall(r"\{\{\s*([A-Za-z0-9_\-]+)\s*\}\}", rendered)))
    if unreplaced:
        raise ValueError("Template still has unreplaced placeholders: " + ", ".join(unreplaced))
    return rendered


def markdown_to_simple_html(markdown_text: str, title: str) -> str:
    lines: list[str] = []
    in_list = False
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            if in_list:
                lines.append("</ul>")
                in_list = False
            continue
        if line.startswith("### "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h3>{h(line[4:])}</h3>")
        elif line.startswith("## "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h2>{h(line[3:])}</h2>")
        elif line.startswith("# "):
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<h1>{h(line[2:])}</h1>")
        elif line.startswith("- "):
            if not in_list:
                lines.append("<ul>")
                in_list = True
            lines.append(f"<li>{h(line[2:])}</li>")
        else:
            if in_list:
                lines.append("</ul>")
                in_list = False
            lines.append(f"<p>{h(line)}</p>")
    if in_list:
        lines.append("</ul>")
    body = "\n".join(lines)
    return f"""<!doctype html>
<html lang="utf-8">
<head>
  <meta charset="utf-8">
  <title>{h(title)}</title>
  <style>
    body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; line-height:1.58; max-width:880px; margin:32px auto; padding:0 24px; color:#17202a; }}
    h1,h2,h3 {{ color:#14213d; }}
    .warning {{ border-left:5px solid #b45309; background:#fffbeb; padding:12px 14px; margin-bottom:20px; font-weight:800; }}
  </style>
</head>
<body>
  <div class="warning">DRAFT - SYSTEM-SUGGESTED STANDARD - REQUIRES HUMAN REVIEW - NOT A FORMAL APPROVED TEMPLATE</div>
  {body}
</body>
</html>"""


def save_generated_template_attachment(
    document_id: str,
    doc: dict[str, Any],
    template: dict[str, Any],
    generation_id: str,
    rendered_html: str,
    parameter_values: dict[str, str],
    user: dict[str, Any],
    handler: BaseHTTPRequestHandler | None,
) -> dict[str, Any]:
    all_versions = versions()
    all_files = file_attachments()
    version_id = next_sequence_id(all_versions, "version_id", "FAV")
    file_id = next_sequence_id(all_files, "file_id", "FILE")
    country = safe_filename(str(template.get("country_code", "XX")).upper())
    template_code = safe_filename(str(template.get("template_code", "template")))
    original_filename = f"{generation_id}__{template_code}.html"
    content = rendered_html.encode("utf-8")
    relative_path = Path("attachments") / "template_generated" / country / document_id / f"{file_id}__{original_filename}"
    target_path = ROOT_DIR / relative_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
    if target_path.exists():
        raise ValueError("Generated file target already exists; refusing to overwrite.")
    temp_path = target_path.with_name(f".{target_path.name}.generating")
    try:
        with temp_path.open("xb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temp_path, target_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise
    created_at = now_iso()
    sha256 = hashlib.sha256(content).hexdigest()
    attachment = {
        "file_id": file_id,
        "document_id": document_id,
        "linked_version_id": version_id,
        "file_title": f"Generated draft - {template.get('template_name', template_code)}",
        "file_description": "Generated from a system-suggested standard template; requires human review and is not a formal approved template.",
        "file_type": "generated_template_html",
        "file_role": "generated_draft",
        "version_no": str(template.get("version", "v1.0")),
        "file_status": "review",
        "is_current": True,
        "is_signed": False,
        "is_original_scan": False,
        "language": str(template.get("language", doc.get("language", "ja"))),
        "confidentiality_level": str(doc.get("confidentiality_level", "contract_confidential")),
        "original_filename": original_filename,
        "stored_filename": target_path.name,
        "storage_path": str(relative_path),
        "mime_type": "text/html; charset=utf-8",
        "file_extension": ".html",
        "file_size_bytes": len(content),
        "checksum_sha256": sha256,
        "file_effective_start_date": "",
        "file_effective_end_date": "",
        "uploaded_by": audit_actor_from_user(user),
        "uploaded_at": created_at,
        "updated_by": audit_actor_from_user(user),
        "updated_at": created_at,
        "archived": False,
        "deleted": False,
        "template_generation": {
            "generation_id": generation_id,
            "template_id": template.get("template_id", ""),
            "template_code": template.get("template_code", ""),
            "parameter_values_snapshot": parameter_values,
        },
        "notes": "System-suggested generated draft; review required.",
    }
    version = {
        "version_id": version_id,
        "document_id": document_id,
        "file_id": file_id,
        "version_no": str(template.get("version", "v1.0")),
        "version_title": attachment["file_title"],
        "status": "review",
        "is_current": True,
        "original_filename": original_filename,
        "stored_path": str(relative_path),
        "mime_type": "text/html; charset=utf-8",
        "file_size_bytes": len(content),
        "sha256": sha256,
        "uploaded_by": audit_actor_from_user(user),
        "uploaded_at": created_at,
        "change_reason": "Generated from Template Generator MVP standard template.",
        "approved_by": "",
        "approved_at": "",
        "notes": attachment["file_description"],
    }
    all_files.append(attachment)
    all_versions.append(version)
    save_json_array(FILE_ATTACHMENTS_PATH, all_files)
    save_json_array(VERSIONS_PATH, all_versions)
    append_audit_log(document_id, "file_attachment", "generated_file_created", {}, attachment, user, handler)
    append_audit_log(document_id, "document_version", "version_uploaded", {}, version, user, handler)
    return attachment


def generate_template_document(form: dict[str, str], user: dict[str, Any], handler: BaseHTTPRequestHandler | None) -> dict[str, Any]:
    if not has_permission(user, "fileadmin.upload"):
        raise ValueError("Template generation requires fileadmin.upload so the generated draft can be saved as a FileAdmin attachment.")
    template_id = form.get("template_id", "").strip()
    template = find_template(template_id)
    if not template:
        raise ValueError("Template not found.")
    if str(template.get("status", "")).strip() != "active" or not template.get("is_current"):
        raise ValueError("Only active current templates can be generated.")
    values = validate_template_parameters(template, form)
    source_text = template_source_text(template)
    rendered_text = render_template_text(source_text, values)
    title = form.get("title", "").strip() or f"{template.get('template_name', 'Generated Template')} - {values.get('candidate_name') or values.get('employee_name') or values.get('client_name') or 'Draft'}"
    rendered_html = markdown_to_simple_html(rendered_text, title)

    docs = documents()
    doc_id = next_sequence_id(docs, "document_id", "FA")
    generation_id = next_sequence_id(template_generation_runs(), "generation_id", "TGEN")
    now = now_iso()
    entity = user_entity(user)
    requested_entity = form.get("entity_id", "").strip() or entity.get("entity_id") or entity.get("entity_code", "")
    current_entity = user_entity_id(user)
    current_entity_code = str(entity.get("entity_code", "")).strip()
    if requested_entity and current_entity and requested_entity not in {current_entity, current_entity_code} and not (is_system_admin(user) or has_permission(user, "fileadmin.cross_entity.create")):
        raise ValueError("You cannot create a FileAdmin document for another entity.")

    doc_form = {
        "document_type": template_document_type(template),
        "business_line": str(template.get("business_line", "hr") or "hr"),
    }
    doc = {
        "document_id": doc_id,
        "document_no": document_no_for(doc_form, docs),
        "title": title,
        "document_type": doc_form["document_type"],
        "business_line": doc_form["business_line"],
        "entity_id": requested_entity,
        "entity_name_snapshot": form.get("entity_name_snapshot", "").strip() or entity.get("entity_name_en") or entity.get("entity_name") or "",
        "customer_id": form.get("customer_id", "").strip(),
        "customer_name_snapshot": form.get("customer_name_snapshot", "").strip() or values.get("client_name", ""),
        "vendor_id": "",
        "vendor_name_snapshot": "",
        "project_id": "",
        "project_name_snapshot": form.get("project_name_snapshot", "").strip(),
        "employee_id": form.get("employee_id", "").strip(),
        "owner_user_id": form.get("owner_user_id", "").strip() or str(user.get("user_id", "")),
        "owner_name_snapshot": form.get("owner_name_snapshot", "").strip() or user_display_name(user),
        "confidentiality_level": form.get("confidentiality_level", "personal_data").strip() or "personal_data",
        "language": str(template.get("language", form.get("language", "ja"))).strip() or "ja",
        "status": "draft",
        "tags": ["template_generated", str(template.get("country_code", "")).lower(), str(template.get("template_category", ""))],
        "summary": "Generated draft from a system-suggested standard template. Human review is required before use.",
        "contract": build_contract_payload({
            "is_contract": "no",
            "contract_start_date": values.get("start_date", ""),
            "contract_end_date": "",
            "currency": values.get("currency", str(country_rule_for(str(template.get("country_code", ""))).get("default_currency", "JPY"))),
        }),
        "template": {
            "is_template": False,
            "is_template_generated": True,
            "template_id": template_id,
            "template_code_snapshot": template.get("template_code", ""),
            "template_name_snapshot": template.get("template_name", ""),
            "template_version_snapshot": template.get("version", ""),
            "generation_id": generation_id,
            "generation_status": "generated_draft",
            "review_status": "pending",
            "template_source_type": template.get("template_source_type", "system_suggested_standard"),
            "formal_approval_required_later": bool(template.get("formal_approval_required_later", True)),
            "legal_review_status": template.get("legal_review_status", "not_formal_template"),
        },
        "current_version_id": "",
        "created_by": audit_actor_from_user(user),
        "created_at": now,
        "updated_by": audit_actor_from_user(user),
        "updated_at": now,
        "archived_at": "",
        "archived_by": "",
        "archive_reason": "",
    }
    docs.append(doc)
    save_json_array(DOCUMENTS_PATH, docs)
    save_document_record_shadow(doc)
    append_audit_log(doc_id, "document", "document_created", {}, doc, user, handler)

    attachment = save_generated_template_attachment(doc_id, doc, template, generation_id, rendered_html, values, user, handler)
    runs = template_generation_runs()
    run = {
        "generation_id": generation_id,
        "template_id": template_id,
        "template_code_snapshot": template.get("template_code", ""),
        "template_name_snapshot": template.get("template_name", ""),
        "template_version_snapshot": template.get("version", ""),
        "template_source_type": template.get("template_source_type", "system_suggested_standard"),
        "country_code": template.get("country_code", ""),
        "language": template.get("language", ""),
        "business_line": template.get("business_line", ""),
        "status": "generated_draft",
        "review_status": "pending",
        "generated_document_id": doc_id,
        "generated_file_id": attachment.get("file_id", ""),
        "generated_version_id": attachment.get("linked_version_id", ""),
        "generated_output_path": attachment.get("storage_path", ""),
        "parameter_values_snapshot": values,
        "generated_by": audit_actor_from_user(user),
        "generated_at": now,
        "reviewed_by": "",
        "reviewed_at": "",
        "review_notes": "",
        "notes": "System-suggested standard workflow-test draft; not a formal approved template.",
    }
    runs.append(run)
    save_json_array(TEMPLATE_GENERATION_RUNS_PATH, runs)

    docs = documents()
    for row in docs:
        if str(row.get("document_id")) == doc_id:
            row["current_version_id"] = attachment.get("linked_version_id", "")
            row["updated_at"] = now_iso()
            row["updated_by"] = audit_actor_from_user(user)
            doc = row
            break
    save_json_array(DOCUMENTS_PATH, docs)
    save_document_record_shadow(doc)
    append_audit_log(generation_id, "template_generation_run", "template_generated", {}, run, user, handler)
    return {"document": doc, "run": run, "attachment": attachment}


def template_badges(template: dict[str, Any]) -> str:
    bits = [status_badge(str(template.get("status", "")))]
    if template.get("is_current"):
        bits.append(status_badge("current"))
    if template.get("template_source_type") == "system_suggested_standard":
        bits.append(status_badge("system_suggested"))
    if template.get("review_required"):
        bits.append(status_badge("review_required"))
    return " ".join(bits)


def templates_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = {key: query.get(key, [""])[0].strip() for key in ["country_code", "business_line", "status", "q"]}
    rows = document_templates()
    for key in ["country_code", "business_line", "status"]:
        if filters[key]:
            rows = [row for row in rows if str(row.get(key, "")) == filters[key]]
    if filters["q"]:
        needle = filters["q"].lower()
        rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).lower()]
    rows = sorted(rows, key=lambda row: (str(row.get("country_code", "")), str(row.get("template_code", ""))))
    body = page_header("Template Generator", "模板生成", "先用系统建议标准模板跑通流程；正式业务模板待后续审批后再纳入。")
    body += """
    <section class="message-strip message-warning">
      当前模板为 workflow test 标准草稿：System-suggested standard / Not formal approved / Requires human review.
    </section>
    """
    body += f"""
    <section class="sap-section">
      <form method="get" action="/templates" class="form-grid">
        <div class="form-field"><label>Country</label><select name="country_code"><option value="">All</option>{text_option_html(['JP', 'CN', 'SG'], filters['country_code'])}</select></div>
        <div class="form-field"><label>Business Line</label><select name="business_line"><option value="">All</option>{option_html(BUSINESS_LINES, filters['business_line'])}</select></div>
        <div class="form-field"><label>Status</label><select name="status"><option value="">All</option>{text_option_html(['draft', 'active', 'archived'], filters['status'])}</select></div>
        <div class="form-field"><label>Search</label><input name="q" value="{h(filters['q'])}" placeholder="template code/name/category"></div>
        <div class="form-field"><label>&nbsp;</label><button type="submit">Filter</button></div>
      </form>
    </section>
    <section class="sap-section">
      <h3>Template Library ({len(rows)})</h3>
      <div class="table-scroll"><table><tr><th>Template</th><th>Country / Language</th><th>Scope</th><th>Status</th><th>Action</th></tr>
    """
    for row in rows:
        can_generate = str(row.get("status", "")) == "active" and bool(row.get("is_current")) and has_permission(user, "fileadmin.create") and has_permission(user, "fileadmin.upload")
        action = f"<a class='button' href='/templates/generate?template_id={h(row.get('template_id'))}'>Generate Draft</a>" if can_generate else "<span class='muted'>No generate permission / inactive</span>"
        body += f"<tr><td><strong>{h(row.get('template_name'))}</strong><br><small>{h(row.get('template_code'))} · {h(row.get('template_id'))}</small><br><small class='muted'>{h(row.get('notes'))}</small></td><td>{h(row.get('country_code'))}<br><small>{h(row.get('language'))}</small></td><td>{h(row.get('template_category'))}<br><small>{h(row.get('business_line'))}</small></td><td>{template_badges(row)}<br><small class='warn'>Not formal approved</small></td><td>{action}</td></tr>"
    if not rows:
        body += "<tr><td colspan='5' class='muted'>No templates found.</td></tr>"
    body += "</table></div></section>"
    return body


def template_generate_form_html(template_id: str, user: dict[str, Any], form: dict[str, str] | None = None) -> str:
    form = form or {}
    template = find_template(template_id)
    if not template:
        return page_header("Not Found", "Template not found", template_id)
    if not has_permission(user, "fileadmin.create") or not has_permission(user, "fileadmin.upload"):
        return forbidden_html("Template generation requires fileadmin.create and fileadmin.upload permissions.")
    if str(template.get("status", "")) != "active" or not template.get("is_current"):
        return forbidden_html("Only active current templates can be generated.")
    entity = user_entity(user)
    selected_entity_id = form.get("entity_id") or entity.get("entity_id") or entity.get("entity_code", "")
    entity_options = entity_select_options_for_user(user, selected_entity_id)
    country_rule = country_rule_for(str(template.get("country_code", "")))
    body = page_header("Generate from Template", f"生成草稿：{template.get('template_name')}", "输入参数后生成 HTML 草稿，并自动进入 FileAdmin 文件台账。")
    body += "<section class='message-strip message-warning'>This is a system-suggested workflow-test template. It is not a formal approved company template and requires human review.</section>"
    body += f"""
    <form method="post" action="/templates/generate">
      <input type="hidden" name="template_id" value="{h(template_id)}">
      <section class="sap-section">
        <h3>Document Metadata</h3>
        <div class="form-grid">
          <div class="form-field"><label>Title</label><input name="title" value="{h(form.get('title', ''))}" placeholder="留空则自动生成标题"></div>
          <div class="form-field"><label>Entity</label><select name="entity_id">{entity_options}</select></div>
          <div class="form-field"><label>Entity Name Snapshot</label><input name="entity_name_snapshot" value="{h(form.get('entity_name_snapshot') or entity.get('entity_name_en') or entity.get('entity_name') or '')}"></div>
          <div class="form-field"><label>Customer / Client Name</label><input name="customer_name_snapshot" value="{h(form.get('customer_name_snapshot', ''))}"></div>
          <div class="form-field"><label>Owner User ID</label><input name="owner_user_id" value="{h(form.get('owner_user_id') or str(user.get('user_id', '')))}"></div>
          <div class="form-field"><label>Owner Name</label><input name="owner_name_snapshot" value="{h(form.get('owner_name_snapshot') or user_display_name(user))}"></div>
          <div class="form-field"><label>Confidentiality</label><select name="confidentiality_level">{option_html(CONFIDENTIALITY_LEVELS, form.get('confidentiality_level', 'personal_data'))}</select></div>
        </div>
      </section>
      <section class="sap-section">
        <h3>Template Parameters</h3>
        <div class="form-grid">
    """
    for param in template_params_for(template_id):
        key = str(param.get("parameter_key", "")).strip()
        label = str(param.get("label") or key)
        required = " required" if param.get("required") else ""
        data_type = str(param.get("data_type", "text"))
        input_type = "date" if data_type == "date" else "number" if data_type == "number" else "email" if data_type == "email" else "text"
        default = form.get(f"param_{key}", str(param.get("default_value", "") or ""))
        if key == "currency" and not default:
            default = str(country_rule.get("default_currency", ""))
        help_text = f"<small class='muted'>{h(param.get('help_text', ''))}</small>" if param.get("help_text") else ""
        if data_type == "textarea":
            body += f"<div class='form-field'><label>{h(label)}{' *' if required else ''}</label><textarea name='param_{h(key)}'{required}>{h(default)}</textarea>{help_text}</div>"
        else:
            body += f"<div class='form-field'><label>{h(label)}{' *' if required else ''}</label><input type='{input_type}' name='param_{h(key)}' value='{h(default)}'{required}>{help_text}</div>"
    body += """
        </div>
      </section>
      <div class="sap-toolbar"><a class="button ghost" href="/templates">Cancel</a><button type="submit">Generate Draft and Save to FileAdmin</button></div>
    </form>
    """
    return body


def template_generation_detail_html(generation_id: str, user: dict[str, Any]) -> str:
    run = find_generation_run(generation_id)
    if not run:
        return page_header("Not Found", "Generation run not found", generation_id)
    doc = find_document(str(run.get("generated_document_id", "")))
    if doc and not can_view_document(user, doc):
        return forbidden_html("You do not have permission to view the generated document.")
    values_json = json.dumps(run.get("parameter_values_snapshot", {}), ensure_ascii=False, indent=2)
    body = page_header("Template Generation Run", str(run.get("generation_id", "")), "生成记录保存模板版本、参数快照、文件和审阅状态。")
    body += "<section class='message-strip message-warning'>Generated from system-suggested standard. Not formal approved. Human review required.</section>"
    body += f"""
    <section class="sap-section">
      <h3>Run Summary</h3>
      <div class="sap-readonly-grid">
        <div class="sap-readonly-field"><div class="label">Template</div><div class="value">{h(run.get('template_code_snapshot'))}<br>{h(run.get('template_name_snapshot'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Country / Language</div><div class="value">{h(run.get('country_code'))} / {h(run.get('language'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Status</div><div class="value">{status_badge(str(run.get('status', '')))} {status_badge(str(run.get('review_status', '')))}</div></div>
        <div class="sap-readonly-field"><div class="label">Generated By</div><div class="value">{h(run.get('generated_by'))}<br>{h(run.get('generated_at'))}</div></div>
      </div>
      <div class="actions" style="margin-top:14px;">
        <a class="button" href="/documents/detail?id={h(run.get('generated_document_id'))}">Open FileAdmin Document</a>
        <a class="button secondary" href="/attachments/download?file_id={h(run.get('generated_file_id'))}">Download Generated Draft</a>
        <a class="button ghost" href="/templates">Back to Templates</a>
      </div>
    </section>
    <section class="sap-section"><h3>Parameter Snapshot</h3><details open><summary>Values used for generation</summary><pre>{h(values_json)}</pre></details></section>
    """
    if has_permission(user, "fileadmin.upload") or has_permission(user, "fileadmin.archive"):
        body += f"""
        <section class="sap-section">
          <h3>Review Generated Draft</h3>
          <form method="post" action="/templates/runs/review" class="form-grid">
            <input type="hidden" name="generation_id" value="{h(generation_id)}">
            <div class="form-field"><label>Review Status</label><select name="review_status">{text_option_html(['pending', 'needs_revision', 'reviewed', 'approved_generated', 'rejected'], str(run.get('review_status', 'pending')))}</select></div>
            <div class="form-field"><label>Review Notes</label><input name="review_notes" value="{h(run.get('review_notes', ''))}"></div>
            <div class="form-field"><label>&nbsp;</label><button type="submit">Update Review</button></div>
          </form>
        </section>
        """
    return body


def update_template_generation_review(form: dict[str, str], user: dict[str, Any], handler: BaseHTTPRequestHandler | None) -> dict[str, Any]:
    if not (has_permission(user, "fileadmin.upload") or has_permission(user, "fileadmin.archive")):
        raise ValueError("You do not have permission to review generated drafts.")
    generation_id = form.get("generation_id", "").strip()
    new_status = form.get("review_status", "").strip()
    allowed = {"pending", "needs_revision", "reviewed", "approved_generated", "rejected"}
    if new_status not in allowed:
        raise ValueError("Invalid review status.")
    runs = template_generation_runs()
    updated: dict[str, Any] | None = None
    before: dict[str, Any] | None = None
    for row in runs:
        if str(row.get("generation_id")) == generation_id:
            before = dict(row)
            row["review_status"] = new_status
            row["review_notes"] = form.get("review_notes", "").strip()
            row["reviewed_by"] = audit_actor_from_user(user)
            row["reviewed_at"] = now_iso()
            updated = row
            break
    if not updated or before is None:
        raise ValueError("Generation run not found.")
    save_json_array(TEMPLATE_GENERATION_RUNS_PATH, runs)

    document_id = str(updated.get("generated_document_id", ""))
    docs = documents()
    for doc in docs:
        if str(doc.get("document_id")) == document_id:
            template_meta = doc.get("template") if isinstance(doc.get("template"), dict) else {}
            template_meta["review_status"] = new_status
            doc["template"] = template_meta
            doc["updated_at"] = now_iso()
            doc["updated_by"] = audit_actor_from_user(user)
            save_document_record_shadow(doc)
            break
    save_json_array(DOCUMENTS_PATH, docs)

    files = file_attachments()
    for attachment in files:
        if str(attachment.get("file_id")) == str(updated.get("generated_file_id", "")):
            attachment["file_status"] = "approved" if new_status == "approved_generated" else "archived" if new_status == "rejected" else "review"
            attachment["updated_at"] = now_iso()
            attachment["updated_by"] = audit_actor_from_user(user)
            break
    save_json_array(FILE_ATTACHMENTS_PATH, files)
    append_audit_log(generation_id, "template_generation_run", "template_review_status_changed", before, updated, user, handler)
    return updated


def mark_generation_archived_for_document(document_id: str, user: dict[str, Any], handler: BaseHTTPRequestHandler | None) -> None:
    rows = template_generation_runs()
    changed = False
    for row in rows:
        if str(row.get("generated_document_id", "")) == document_id and str(row.get("status", "")) != "archived":
            before = dict(row)
            row["status"] = "archived"
            row["archived_by"] = audit_actor_from_user(user)
            row["archived_at"] = now_iso()
            changed = True
            append_audit_log(str(row.get("generation_id", document_id)), "template_generation_run", "template_run_archived", before, row, user, handler)
    if changed:
        save_json_array(TEMPLATE_GENERATION_RUNS_PATH, rows)


def generate_contract_reminders(doc: dict[str, Any], user: dict[str, Any], handler: BaseHTTPRequestHandler | None = None) -> list[dict[str, Any]]:
    contract = doc.get("contract") if isinstance(doc.get("contract"), dict) else {}
    if not contract.get("is_contract"):
        return []
    contract_end = str(contract.get("contract_end_date", "")).strip()
    if not parse_date(contract_end):
        return []
    rows = reminders()
    created: list[dict[str, Any]] = []
    reminder_specs: list[tuple[str, int, str]] = []
    renewal_days = int(contract.get("renewal_notice_days") or 0)
    termination_days = int(contract.get("termination_notice_days") or 0)
    if contract.get("auto_renewal") and renewal_days > 0:
        reminder_specs.append(("auto_renewal_notice", renewal_days, "high"))
    if termination_days > 0:
        reminder_specs.append(("termination_notice", termination_days, "high"))
    if not reminder_specs:
        reminder_specs.append(("contract_expiry", 30, "normal"))

    for reminder_type, days_before, priority in reminder_specs:
        reminder_date = date_add_days(contract_end, -days_before)
        row = {
            "reminder_id": next_sequence_id(rows + created, "reminder_id", "FAR"),
            "document_id": doc.get("document_id", ""),
            "reminder_type": reminder_type,
            "reminder_date": reminder_date,
            "due_date": contract_end,
            "days_before_due": days_before,
            "assigned_user_id": doc.get("owner_user_id", ""),
            "assigned_user_name_snapshot": doc.get("owner_name_snapshot", ""),
            "status": "open",
            "priority": priority,
            "message": f"{doc.get('title', '')} reminder: {reminder_type} before {contract_end}",
            "action_result": "",
            "acknowledged_by": "",
            "acknowledged_at": "",
            "completed_by": "",
            "completed_at": "",
            "created_at": now_iso(),
            "updated_at": now_iso(),
        }
        created.append(row)
        append_audit_log(str(doc.get("document_id", "")), "contract_reminder", "contract_reminder_created", {}, row, user, handler)
    if created:
        save_json_array(REMINDERS_PATH, rows + created)
    return created


def page(title: str, body: str, user: dict[str, Any] | None = None, current_path: str = "/", flash: str = "", lang: str = DEFAULT_LANG) -> str:
    lang = normalize_lang(lang)
    nav_links = [
        ("/dashboard", "nav.dashboard"),
        ("/documents", "nav.documents"),
        ("/documents/new", "nav.new_document"),
        ("/templates", "nav.templates"),
        ("/emails", "nav.emails"),
        ("/reminders", "nav.reminders"),
        ("/audit-logs", "nav.audit"),
    ]
    nav_html = "".join(
        f'<a class="{h("active" if path == current_path else "")}" href="{h(url_with_lang(path, lang))}">{h(tr(lang, label_key))}</a>'
        for path, label_key in nav_links
    )
    portal_html = f'<a class="portal-link" href="{h(PORTAL_BASE_URL)}/dashboard" title="{h(tr(lang, "nav.portal"))}"><span class="portal-icon">⌂</span>{h(tr(lang, "nav.portal"))}</a>'
    entity = user_entity(user)
    user_html = ""
    if user:
        entity_text = entity_label(entity) or tr(lang, "no_entity")
        user_html = f"""
        <span class="current-user-chip" title="{h(tr(lang, 'current_user'))}: {h(user_display_name(user))}">
          <small class="current-user-label">{h(tr(lang, "current_user"))}</small>
          <strong>{h(user_display_name(user))}</strong>
          <small>{h(tr(lang, "current_entity"))}: {h(entity_text)}</small>
        </span>
        """
    flash_html = f'<section class="message-strip message-success" role="status">{h(flash)}</section>' if flash else ""
    body = localize_body(body, lang)
    language_html = language_switcher_html(current_path, lang)
    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(localize_body(title, lang))} - {h(tr(lang, "app.title"))}</title>
  <style>
    :root {{ --navy:#14213d; --blue:#0a6ed1; --bg:#f6f8fb; --card:#fff; --line:#d8dee9; --muted:#65758b; --green:#0f766e; --amber:#b45309; --red:#b91c1c; --purple:#6d28d9; }}
    body {{ margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif; background:var(--bg); color:#17202a; }}
    header {{ background:var(--navy); color:white; padding:22px 32px; }}
    header h1 {{ margin:0 0 6px; }} header p {{ margin:0; color:#dbeafe; }}
    nav {{ display:flex; align-items:center; gap:8px; flex-wrap:wrap; padding:10px 32px; background:white; border-bottom:1px solid var(--line); box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    nav a {{ display:inline-flex; align-items:center; justify-content:center; min-height:34px; color:#223548; background:#f7f9fb; text-decoration:none; border:1px solid transparent; padding:0 13px; border-radius:8px; font-size:.92rem; font-weight:760; white-space:nowrap; }}
    nav a:hover {{ background:#eef6ff; border-color:#91c8f6; color:var(--blue); }}
    nav a.active {{ background:#e5f2fd; border-color:var(--blue); color:var(--blue); box-shadow:inset 0 -2px 0 var(--blue); }}
    nav a.portal-link {{ gap:.35rem; color:#0b4f8a; background:linear-gradient(180deg,#f8fbff 0%,#eaf4ff 100%); border-color:#9cc7f2; }}
    .language-switcher {{ display:flex; align-items:center; gap:6px; margin-left:auto; }} .language-label {{ color:var(--muted); font-size:.82rem; font-weight:800; }} .lang-link {{ min-height:28px; padding:0 9px; font-size:.8rem; }} .lang-link.active {{ background:#e5f2fd; border-color:var(--blue); color:var(--blue); }}
    .current-user-chip {{ margin-left:0; display:grid; gap:2px; min-width:210px; padding:7px 10px; background:#fff; border:1px solid #d6e4f2; border-radius:12px; color:var(--navy); }}
    .current-user-chip strong {{ font-size:.9rem; }} .current-user-chip small {{ color:var(--muted); font-size:.76rem; }} .current-user-chip .current-user-label {{ color:var(--blue); font-weight:850; letter-spacing:.03em; text-transform:uppercase; }}
    main {{ max-width:1240px; margin:0 auto; padding:28px 20px 48px; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(230px,1fr)); gap:16px; }}
    .form-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:14px; }}
    .card,.panel,.sap-section {{ background:var(--card); border:1px solid var(--line); border-radius:14px; padding:18px; box-shadow:0 1px 2px rgba(15,23,42,.04); }}
    .panel,.sap-section {{ margin-top:16px; }} .card h3,.panel h2,.sap-section h3 {{ margin-top:0; color:var(--navy); }}
    .metric {{ font-size:2rem; font-weight:850; color:var(--navy); }} .muted {{ color:var(--muted); }} .good {{ color:var(--green); font-weight:800; }} .warn {{ color:var(--amber); font-weight:800; }} .error {{ color:var(--red); font-weight:800; }}
    .sap-page-header,.object-header {{ background:linear-gradient(135deg,#fff 0%,#eef4ff 100%); border:1px solid var(--line); border-radius:16px; padding:20px; margin-bottom:18px; }}
    .sap-page-header h2,.object-header h2 {{ margin:0 0 8px; color:var(--navy); }} .eyebrow {{ margin:0 0 4px; color:var(--blue); font-size:.74rem; font-weight:850; letter-spacing:.055em; text-transform:uppercase; }}
    .sap-object-meta,.actions,.sap-toolbar {{ display:flex; gap:10px; flex-wrap:wrap; align-items:center; }} .sap-toolbar {{ justify-content:flex-end; padding-top:16px; border-top:1px solid var(--line); margin-top:18px; }}
    .sap-readonly-grid,.object-meta {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px; }}
    .sap-readonly-field,.meta-chip {{ background:#f8fafc; border:1px solid var(--line); border-radius:10px; padding:12px; }}
    .label,.meta-chip-label {{ color:var(--muted); font-size:.78rem; font-weight:850; text-transform:uppercase; margin-bottom:4px; }} .value,.meta-chip-value {{ color:var(--navy); font-weight:850; overflow-wrap:anywhere; }}
    table {{ width:100%; border-collapse:collapse; background:white; border:1px solid var(--line); border-radius:12px; overflow:hidden; }} th,td {{ border-bottom:1px solid var(--line); padding:10px 12px; text-align:left; vertical-align:top; }} th {{ background:#eef4ff; color:var(--navy); font-size:.9rem; }} tr:last-child td {{ border-bottom:0; }} .table-scroll,.wide {{ overflow-x:auto; border:1px solid #e5edf6; border-radius:12px; }}
    label {{ display:block; font-weight:800; margin-bottom:6px; }} input,select,textarea {{ box-sizing:border-box; width:100%; border:1px solid #c8d1dc; border-radius:8px; padding:9px 10px; font:inherit; }} textarea {{ min-height:88px; resize:vertical; }} input:focus,select:focus,textarea:focus {{ outline:3px solid rgba(31,111,235,.18); border-color:var(--blue); }}
    .form-field {{ margin-bottom:.85rem; }} .button,button {{ display:inline-block; background:var(--blue); color:white; padding:10px 14px; border-radius:8px; border:0; text-decoration:none; font-weight:800; cursor:pointer; }} .button.secondary,button.secondary {{ background:#475569; }} .button.ghost {{ background:white; color:var(--navy); border:1px solid var(--line); }} .button.warning,button.warning {{ background:var(--amber); }} .button.danger,button.danger {{ background:var(--red); }}
    .pill,.status-badge {{ display:inline-block; padding:4px 8px; border-radius:999px; background:#ecfeff; color:#155e75; font-weight:800; font-size:.82rem; }} .status-active {{ background:#dcfce7; color:#166534; }} .status-draft {{ background:#f1f5f9; color:#334155; }} .status-expiring,.status-open {{ background:#fef3c7; color:#92400e; }} .status-expired,.status-archived,.status-waived {{ background:#fee2e2; color:#991b1b; }} .status-completed,.status-approved,.status-current,.status-signed {{ background:#dcfce7; color:#166534; }} .status-replaced {{ background:#ede9fe; color:#5b21b6; }}
    .message-strip,.notice {{ border-left:4px solid var(--blue); background:#eff6ff; padding:12px 14px; border-radius:8px; }} .message-success {{ border-left-color:var(--green); background:#ecfdf5; }} .message-warning {{ border-left-color:var(--amber); background:#fffbeb; }} .message-error {{ border-left-color:var(--red); background:#fef2f2; }}
    details pre {{ white-space:pre-wrap; max-width:520px; background:#0f172a; color:#e5e7eb; padding:10px; border-radius:8px; overflow:auto; }}
    @media(max-width:720px) {{ header {{ padding:16px 18px; }} nav {{ flex-wrap:nowrap; overflow-x:auto; padding:8px 12px; }} nav a {{ flex:0 0 auto; }} .current-user-chip {{ margin-left:6px; min-width:150px; }} main {{ padding:18px 12px 36px; }} .grid,.form-grid,.sap-readonly-grid,.object-meta {{ grid-template-columns:1fr; }} .actions,.sap-toolbar {{ flex-direction:column; align-items:stretch; }} .actions .button,.actions button,.sap-toolbar .button,.sap-toolbar button {{ text-align:center; width:100%; }} table {{ display:block; overflow-x:auto; min-width:760px; }} }}
  </style>
</head>
<body>
  <header><h1>{h(tr(lang, "app.title"))}</h1><p>{h(tr(lang, "app.subtitle"))}</p></header>
  <nav>{portal_html}{nav_html}{language_html}{user_html}</nav>
  <main>{flash_html}{body}</main>
</body>
</html>"""


def page_header(eyebrow: str, title: str, text: str, meta: list[tuple[str, str]] | None = None) -> str:
    meta_html = ""
    if meta:
        meta_html = '<div class="sap-object-meta">' + "".join(
            f'<span class="meta-chip"><span class="meta-chip-label">{h(label)}</span><span class="meta-chip-value">{h(value)}</span></span>'
            for label, value in meta
        ) + "</div>"
    return f"""
    <section class="sap-page-header">
      <p class="eyebrow">{h(eyebrow)}</p>
      <h2>{h(title)}</h2>
      <p class="muted">{h(text)}</p>
      {meta_html}
    </section>
    """


def dashboard_html(user: dict[str, Any]) -> str:
    docs = [row for row in documents() if can_view_document(user, row)]
    visible_document_ids = {str(row.get("document_id", "")) for row in docs}
    active = [row for row in docs if row.get("status") != "archived"]
    reminder_rows = [row for row in reminders() if str(row.get("document_id", "")) in visible_document_ids]
    open_reminders = [row for row in reminder_rows if row.get("status") not in {"completed", "waived"}]
    expiring = [row for row in active if (days_until(str((row.get("contract") or {}).get("contract_end_date", ""))) or 99999) <= 90]
    attachment_rows = [row for row in file_attachments() if str(row.get("document_id", "")) in visible_document_ids]
    recent_attachments = sorted(attachment_rows, key=lambda row: str(row.get("uploaded_at", "")), reverse=True)[:5]
    recent_versions = sorted([row for row in versions() if str(row.get("document_id", "")) in visible_document_ids], key=lambda row: str(row.get("uploaded_at", "")), reverse=True)[:5]
    recent_audits = sorted(audit_logs(), key=lambda row: str(row.get("timestamp", "")), reverse=True)[:6]
    body = page_header(
        "Document Governance",
        "FileAdmin Dashboard",
        "轻量管理客户合同、对外文书版本、到期提醒和审计记录。",
    )
    body += f"""
    <section class="grid">
      <div class="card"><h3>Active Documents</h3><div class="metric">{len(active)}</div><p class="muted">当前未归档文件</p></div>
      <div class="card"><h3>Expiring Contracts</h3><div class="metric">{len(expiring)}</div><p class="muted">90 天内到期或已过期</p></div>
      <div class="card"><h3>Open Reminders</h3><div class="metric">{len(open_reminders)}</div><p class="muted">待处理合同提醒</p></div>
      <div class="card"><h3>Attachments</h3><div class="metric">{len(attachment_rows) or len(versions())}</div><p class="muted">已上传文件附件总数</p></div>
    </section>
    <section class="sap-section">
      <h3>Quick Actions</h3>
      <div class="actions">
        <a class="button" href="/documents/new">登记新文件</a>
        <a class="button secondary" href="/documents">打开文件台账</a>
        <a class="button secondary" href="/reminders">查看到期提醒</a>
        <a class="button ghost" href="{h(PORTAL_BASE_URL)}/dashboard">返回主 Portal</a>
      </div>
    </section>
    """
    body += "<section class='sap-section'><h3>Recent File Attachments</h3><div class='table-scroll'><table><tr><th>Uploaded</th><th>Document</th><th>Attachment</th><th>Role</th><th>Current</th></tr>"
    if recent_attachments:
        for row in recent_attachments:
            body += f"<tr><td>{h(row.get('uploaded_at'))}</td><td><a href='/documents/detail?id={h(row.get('document_id'))}'>{h(document_title(str(row.get('document_id', ''))))}</a></td><td>{h(row.get('file_title') or row.get('original_filename'))}<br><small class='muted'>{h(row.get('version_no'))}</small></td><td>{h(row.get('file_role'))}</td><td>{status_badge('current') if row.get('is_current') else h('history')}</td></tr>"
    else:
        for row in recent_versions:
            body += f"<tr><td>{h(row.get('uploaded_at'))}</td><td><a href='/documents/detail?id={h(row.get('document_id'))}'>{h(document_title(str(row.get('document_id', ''))))}</a></td><td>{h(row.get('version_title') or row.get('original_filename'))}<br><small class='muted'>{h(row.get('version_no'))}</small></td><td>legacy_version</td><td>{status_badge('current') if row.get('is_current') else h('history')}</td></tr>"
    if not recent_attachments and not recent_versions:
        body += "<tr><td colspan='5' class='muted'>No attachments uploaded yet.</td></tr>"
    body += "</table></div></section>"
    body += "<section class='sap-section'><h3>Recent Audit</h3><div class='table-scroll'><table><tr><th>Time</th><th>Action</th><th>Record</th><th>User</th></tr>"
    for row in recent_audits:
        body += f"<tr><td>{h(row.get('timestamp'))}</td><td>{status_badge(str(row.get('action', '')))}</td><td>{h(row.get('record_id'))}</td><td>{h(row.get('user'))}</td></tr>"
    if not recent_audits:
        body += "<tr><td colspan='4' class='muted'>No audit events yet.</td></tr>"
    body += "</table></div></section>"
    return body


def document_filters(query: dict[str, list[str]]) -> dict[str, str]:
    return {key: query.get(key, [""])[0].strip() for key in ["entity_id", "q", "document_type", "business_line", "status", "owner"]}


def documents_html(query: dict[str, list[str]], user: dict[str, Any]) -> str:
    filters = document_filters(query)
    rows = [row for row in documents() if can_view_document(user, row)]
    if filters["q"]:
        needle = filters["q"].lower()
        rows = [row for row in rows if needle in json.dumps(row, ensure_ascii=False).lower()]
    if filters["entity_id"]:
        rows = [row for row in rows if filters["entity_id"] == str(row.get("entity_id", "")).strip()]
    for key in ["document_type", "business_line", "status"]:
        if filters[key]:
            rows = [row for row in rows if str(row.get(key, "")) == filters[key]]
    if filters["owner"]:
        needle = filters["owner"].lower()
        rows = [row for row in rows if needle in str(row.get("owner_name_snapshot", "")).lower() or needle in str(row.get("owner_user_id", "")).lower()]
    rows = sorted(rows, key=lambda row: str(row.get("updated_at", row.get("created_at", ""))), reverse=True)
    entity_options = entity_select_options_for_user(user, filters["entity_id"], include_blank=True)
    body = page_header("Document Register", "文件台账", "按业务线、文件类型、状态、法人和负责人查找企业文件。")
    body += f"""
    <section class="sap-section">
      <form method="get" action="/documents" class="form-grid">
        <div class="form-field"><label>Entity</label><select name="entity_id">{entity_options}</select></div>
        <div class="form-field"><label>Search</label><input name="q" value="{h(filters['q'])}" placeholder="客户名、标题、编号、标签"></div>
        <div class="form-field"><label>Document Type</label><select name="document_type"><option value="">All</option>{option_html(DOCUMENT_TYPES, filters['document_type'])}</select></div>
        <div class="form-field"><label>Business Line</label><select name="business_line"><option value="">All</option>{option_html(BUSINESS_LINES, filters['business_line'])}</select></div>
        <div class="form-field"><label>Status</label><select name="status"><option value="">All</option>{text_option_html(DOCUMENT_STATUSES, filters['status'])}</select></div>
        <div class="form-field"><label>Owner</label><input name="owner" value="{h(filters['owner'])}"></div>
        <div class="form-field"><label>&nbsp;</label><button type="submit">Filter</button></div>
      </form>
      <div class="actions"><a class="button" href="/documents/new">登记新文件</a></div>
    </section>
    <section class="sap-section">
      <h3>Documents ({len(rows)})</h3>
      <div class="table-scroll"><table>
        <tr><th>编号</th><th>标题</th><th>类型</th><th>业务线</th><th>客户/对象</th><th>到期</th><th>状态</th><th>负责人</th></tr>
    """
    for row in rows:
        contract = row.get("contract") if isinstance(row.get("contract"), dict) else {}
        body += f"""
        <tr>
          <td>{h(row.get('document_no') or row.get('document_id'))}</td>
          <td><a href="/documents/detail?id={h(row.get('document_id'))}">{h(row.get('title'))}</a><br><small class="muted">{h(row.get('document_id'))}</small></td>
          <td>{h(row.get('document_type'))}</td>
          <td>{h(row.get('business_line'))}</td>
          <td>{h(row.get('customer_name_snapshot') or row.get('vendor_name_snapshot') or row.get('project_name_snapshot') or '-')}</td>
          <td>{h(contract.get('contract_end_date', ''))}</td>
          <td>{status_badge(str(row.get('status', '')))}</td>
          <td>{h(row.get('owner_name_snapshot') or row.get('owner_user_id'))}</td>
        </tr>
        """
    if not rows:
        body += "<tr><td colspan='8' class='muted'>No documents found.</td></tr>"
    body += "</table></div></section>"
    return body


def document_form_html(user: dict[str, Any], form: dict[str, str] | None = None) -> str:
    form = form or {}
    entity = user_entity(user)
    entity_id = form.get("entity_id") or entity.get("entity_id") or entity.get("entity_code", "")
    entity_name = form.get("entity_name_snapshot") or entity.get("entity_name_en") or entity.get("entity_name") or ""
    owner_id = form.get("owner_user_id") or str(user.get("user_id", ""))
    owner_name = form.get("owner_name_snapshot") or user_display_name(user)
    entity_options = entity_select_options_for_user(user, entity_id)
    return page_header("New Document", "登记新文件", "建立文件 metadata，可同时上传第一版附件。") + f"""
    <form method="post" action="/documents/new" enctype="multipart/form-data">
      <section class="sap-section">
        <h3>Basic Information</h3>
        <div class="form-grid">
          <div class="form-field"><label>Title *</label><input name="title" required value="{h(form.get('title', ''))}"></div>
          <div class="form-field"><label>Document No</label><input name="document_no" value="{h(form.get('document_no', ''))}" placeholder="留空自动编号"></div>
          <div class="form-field"><label>Document Type *</label><select name="document_type" required>{option_html(DOCUMENT_TYPES, form.get('document_type', 'contract_client_dispatch'))}</select></div>
          <div class="form-field"><label>Business Line *</label><select name="business_line" required>{option_html(BUSINESS_LINES, form.get('business_line', 'dispatch'))}</select></div>
          <div class="form-field"><label>Entity</label><select name="entity_id">{entity_options}</select></div>
          <div class="form-field"><label>Entity Name Snapshot</label><input name="entity_name_snapshot" value="{h(entity_name)}"></div>
          <div class="form-field"><label>Customer Name</label><input name="customer_name_snapshot" value="{h(form.get('customer_name_snapshot', ''))}"></div>
          <div class="form-field"><label>Vendor Name</label><input name="vendor_name_snapshot" value="{h(form.get('vendor_name_snapshot', ''))}"></div>
          <div class="form-field"><label>Project Name</label><input name="project_name_snapshot" value="{h(form.get('project_name_snapshot', ''))}"></div>
          <div class="form-field"><label>Owner User ID</label><input name="owner_user_id" value="{h(owner_id)}"></div>
          <div class="form-field"><label>Owner Name</label><input name="owner_name_snapshot" value="{h(owner_name)}"></div>
          <div class="form-field"><label>Confidentiality</label><select name="confidentiality_level">{option_html(CONFIDENTIALITY_LEVELS, form.get('confidentiality_level', 'contract_confidential'))}</select></div>
          <div class="form-field"><label>Language</label><select name="language">{option_html(LANGUAGES, form.get('language', 'ja'))}</select></div>
          <div class="form-field"><label>Status</label><select name="status">{text_option_html(DOCUMENT_STATUSES, form.get('status', 'active'))}</select></div>
          <div class="form-field"><label>Tags</label><input name="tags" value="{h(form.get('tags', ''))}" placeholder="逗号分隔"></div>
        </div>
        <div class="form-field"><label>Summary</label><textarea name="summary">{h(form.get('summary', ''))}</textarea></div>
      </section>
      <section class="sap-section">
        <h3>Contract Details</h3>
        <div class="form-grid">
          <div class="form-field"><label>Is Contract</label><select name="is_contract"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Start Date</label><input type="date" name="contract_start_date" value="{h(form.get('contract_start_date', ''))}"></div>
          <div class="form-field"><label>End Date</label><input type="date" name="contract_end_date" value="{h(form.get('contract_end_date', ''))}"></div>
          <div class="form-field"><label>Auto Renewal</label><select name="auto_renewal"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Renewal Notice Days</label><input type="number" name="renewal_notice_days" value="{h(form.get('renewal_notice_days', '60'))}"></div>
          <div class="form-field"><label>Termination Notice Days</label><input type="number" name="termination_notice_days" value="{h(form.get('termination_notice_days', '60'))}"></div>
          <div class="form-field"><label>Contract Amount</label><input name="contract_amount" value="{h(form.get('contract_amount', ''))}"></div>
          <div class="form-field"><label>Currency</label><input name="currency" value="{h(form.get('currency', 'JPY'))}"></div>
        </div>
        <div class="form-grid">
          <div class="form-field"><label>Payment Terms</label><textarea name="payment_terms">{h(form.get('payment_terms', ''))}</textarea></div>
          <div class="form-field"><label>Fee / Guarantee Terms</label><textarea name="fee_terms">{h(form.get('fee_terms', ''))}</textarea></div>
          <div class="form-field"><label>Risk Notes</label><textarea name="risk_notes">{h(form.get('risk_notes', ''))}</textarea></div>
        </div>
      </section>
      <section class="sap-section">
        <h3>Template / First File Attachment</h3>
        <p class="notice">FileAdmin 使用“文档记录 + 多个文件附件”模型。创建记录时可以先上传一个附件，之后可在详情页继续追加主合同、NDA、补充协议、盖章扫描版、邮件证据等多个文件。</p>
        <div class="form-grid">
          <div class="form-field"><label>Is External Template</label><select name="is_template"><option value="no">No</option><option value="yes">Yes</option></select></div>
          <div class="form-field"><label>Template Code</label><input name="template_code" value="{h(form.get('template_code', ''))}"></div>
          <div class="form-field"><label>Current Template</label><select name="is_current_template"><option value="no">No</option><option value="yes">Yes</option></select></div>
          <div class="form-field"><label>Effective Date</label><input type="date" name="effective_date" value="{h(form.get('effective_date', ''))}"></div>
          <div class="form-field"><label>File Title</label><input name="file_title" value="{h(form.get('file_title', 'Initial upload'))}" placeholder="例：主合同签署版"></div>
          <div class="form-field"><label>File Type</label><select name="file_type">{option_html(FILE_TYPES, form.get('file_type', 'contract_signed_pdf'))}</select></div>
          <div class="form-field"><label>File Role</label><select name="file_role">{option_html(FILE_ROLES, form.get('file_role', 'main_contract'))}</select></div>
          <div class="form-field"><label>Initial Version No</label><input name="version_no" value="{h(form.get('version_no', 'v1.0'))}"></div>
          <div class="form-field"><label>Current Effective File</label><select name="is_current"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Signed / Sealed File</label><select name="is_signed"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Original Scan</label><select name="is_original_scan"><option value="no">No</option><option value="yes">Yes</option></select></div>
          <div class="form-field"><label>Attachment</label><input type="file" name="attachment"></div>
          <div class="form-field"><label>Change Reason</label><input name="change_reason" value="初回登记"></div>
        </div>
        <div class="form-field"><label>File Description</label><textarea name="file_description" placeholder="说明这个附件在合同包中的作用、适用范围、正式程度等">{h(form.get('file_description', ''))}</textarea></div>
      </section>
      <div class="sap-toolbar"><a class="button ghost" href="/documents">Cancel</a><button type="submit">Save Document</button></div>
    </form>
    """


def create_document(form: dict[str, str], files: dict[str, tuple[str, bytes, str]], user: dict[str, Any], handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    title = form.get("title", "").strip()
    if not title:
        raise ValueError("Title is required.")
    doc_type = form.get("document_type", "").strip()
    business_line = form.get("business_line", "").strip()
    if not doc_type or not business_line:
        raise ValueError("Document type and business line are required.")
    rows = documents()
    doc_id = next_sequence_id(rows, "document_id", "FA")
    now = now_iso()
    requested_entity = form.get("entity_id", "").strip()
    current_entity = user_entity_id(user)
    current_entity_code = str(user_entity(user).get("entity_code", "")).strip()
    if requested_entity and current_entity and requested_entity not in {current_entity, current_entity_code} and not (is_system_admin(user) or has_permission(user, "fileadmin.cross_entity.create")):
        raise ValueError("You cannot create a FileAdmin document for another entity.")
    doc = {
        "document_id": doc_id,
        "document_no": document_no_for(form, rows),
        "title": title,
        "document_type": doc_type,
        "business_line": business_line,
        "entity_id": form.get("entity_id", "").strip(),
        "entity_name_snapshot": form.get("entity_name_snapshot", "").strip(),
        "customer_id": form.get("customer_id", "").strip(),
        "customer_name_snapshot": form.get("customer_name_snapshot", "").strip(),
        "vendor_id": form.get("vendor_id", "").strip(),
        "vendor_name_snapshot": form.get("vendor_name_snapshot", "").strip(),
        "project_id": form.get("project_id", "").strip(),
        "project_name_snapshot": form.get("project_name_snapshot", "").strip(),
        "employee_id": form.get("employee_id", "").strip(),
        "owner_user_id": form.get("owner_user_id", "").strip(),
        "owner_name_snapshot": form.get("owner_name_snapshot", "").strip(),
        "confidentiality_level": form.get("confidentiality_level", "contract_confidential").strip(),
        "language": form.get("language", "ja").strip(),
        "status": form.get("status", "active").strip(),
        "tags": [tag.strip() for tag in form.get("tags", "").split(",") if tag.strip()],
        "summary": form.get("summary", "").strip(),
        "contract": build_contract_payload(form),
        "template": build_template_payload(form),
        "current_version_id": "",
        "created_by": audit_actor_from_user(user),
        "created_at": now,
        "updated_by": audit_actor_from_user(user),
        "updated_at": now,
        "archived_at": "",
        "archived_by": "",
        "archive_reason": "",
    }
    rows.append(doc)
    save_json_array(DOCUMENTS_PATH, rows)
    save_document_record_shadow(doc)
    append_audit_log(doc_id, "document", "document_created", {}, doc, user, handler)

    if "attachment" in files:
        attachment = save_uploaded_version(doc_id, doc, form, files["attachment"], user, handler)
        rows = documents()
        for row in rows:
            if row.get("document_id") == doc_id:
                row["current_version_id"] = attachment.get("linked_version_id", "")
                row["updated_at"] = now_iso()
                row["updated_by"] = audit_actor_from_user(user)
                doc = row
                break
        save_json_array(DOCUMENTS_PATH, rows)
        save_document_record_shadow(doc)
    generate_contract_reminders(doc, user, handler)
    return doc


def upload_version(document_id: str, form: dict[str, str], files: dict[str, tuple[str, bytes, str]], user: dict[str, Any], handler: BaseHTTPRequestHandler) -> dict[str, Any]:
    rows = documents()
    doc = None
    for row in rows:
        if str(row.get("document_id")) == document_id:
            doc = row
            break
    if not doc:
        raise ValueError("Document not found.")
    if not can_upload_attachment(user, doc):
        raise ValueError("You do not have permission to upload attachments for this document, or the document is archived.")
    if "attachment" not in files:
        raise ValueError("Please choose a file to upload.")
    before = dict(doc)
    attachment = save_uploaded_version(document_id, doc, form, files["attachment"], user, handler)
    doc["current_version_id"] = attachment.get("linked_version_id", "")
    doc["updated_at"] = now_iso()
    doc["updated_by"] = audit_actor_from_user(user)
    save_json_array(DOCUMENTS_PATH, rows)
    save_document_record_shadow(doc)
    append_audit_log(document_id, "document", "file_marked_current", before, doc, user, handler)
    return attachment


EMAIL_ADDRESS_RE = re.compile(r"^[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+$")


def parse_email_recipients(raw: str, max_count: int, label: str) -> list[dict[str, str]]:
    values = [item.strip() for item in re.split(r"[,;\n]+", raw or "") if item.strip()]
    if len(values) > max_count:
        raise ValueError(f"{label} can include at most {max_count} recipients.")
    recipients: list[dict[str, str]] = []
    for value in values:
        name = ""
        email = value
        match = re.match(r"^(.*?)<([^>]+)>$", value)
        if match:
            name = match.group(1).strip().strip('"')
            email = match.group(2).strip()
        if not EMAIL_ADDRESS_RE.match(email):
            raise ValueError(f"Invalid {label} email address: {email}")
        recipients.append({"name": name, "email": email})
    return recipients


def email_context_for(doc: dict[str, Any], attachment: dict[str, Any]) -> dict[str, str]:
    template_meta = doc.get("template") if isinstance(doc.get("template"), dict) else {}
    generation_id = str(template_meta.get("generation_id") or (attachment.get("template_generation") or {}).get("generation_id") or "")
    generation = find_generation_run(generation_id) if generation_id else None
    params = generation.get("parameter_values_snapshot", {}) if generation and isinstance(generation.get("parameter_values_snapshot"), dict) else {}
    context = {
        "document_title": str(doc.get("title", "")),
        "document_no": str(doc.get("document_no", "")),
        "file_title": str(attachment.get("file_title", "")),
        "sender_name": "",
        "company_name": str(params.get("company_name") or doc.get("entity_name_snapshot") or ""),
        "candidate_name": str(params.get("candidate_name") or ""),
        "candidate_email": str(params.get("candidate_email") or ""),
        "client_name": str(params.get("client_name") or doc.get("customer_name_snapshot") or ""),
        "generation_id": generation_id,
    }
    return context


def render_email_text(template_text: str, context: dict[str, str]) -> str:
    rendered = template_text or ""
    for key, value in context.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def default_email_template_for(doc: dict[str, Any], attachment: dict[str, Any]) -> dict[str, Any] | None:
    language = str(attachment.get("language") or doc.get("language") or "").strip()
    rows = [row for row in email_templates() if row.get("status") == "active"]
    if language:
        for row in rows:
            if str(row.get("language", "")) == language:
                return row
    return rows[0] if rows else None


def read_attachment_payload(attachment: dict[str, Any]) -> tuple[str, bytes, str]:
    relative = Path(str(attachment.get("storage_path", "") or attachment.get("stored_path", "")))
    target = (ROOT_DIR / relative).resolve()
    attachments_root = ATTACHMENTS_DIR.resolve()
    if attachments_root not in target.parents:
        raise ValueError("Invalid attachment path.")
    if not target.exists() or not target.is_file():
        raise ValueError("Attachment file not found.")
    filename = safe_filename(str(attachment.get("original_filename") or target.name))
    content_type = str(attachment.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream").split(";", 1)[0]
    return filename, target.read_bytes(), content_type


def send_smtp_email(message_row: dict[str, Any], attachment: dict[str, Any]) -> str:
    if not SMTP_HOST:
        raise ValueError("SMTP host is not configured.")
    msg = EmailMessage()
    from_header = f"{EMAIL_FROM_NAME} <{EMAIL_FROM}>" if EMAIL_FROM_NAME else EMAIL_FROM
    msg["From"] = from_header
    msg["To"] = ", ".join(item["email"] for item in message_row.get("to", []))
    if message_row.get("cc"):
        msg["Cc"] = ", ".join(item["email"] for item in message_row.get("cc", []))
    msg["Subject"] = str(message_row.get("subject", ""))
    msg.set_content(str(message_row.get("body_text", "")))
    filename, payload, content_type = read_attachment_payload(attachment)
    maintype, _, subtype = content_type.partition("/")
    msg.add_attachment(payload, maintype=maintype or "application", subtype=subtype or "octet-stream", filename=filename)
    recipients = [item["email"] for item in message_row.get("to", []) + message_row.get("cc", []) + message_row.get("bcc", [])]
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USERNAME:
            smtp.login(SMTP_USERNAME, SMTP_PASSWORD)
        smtp.send_message(msg, to_addrs=recipients)
    return str(msg.get("Message-ID", ""))


def create_email_message(form: dict[str, str], user: dict[str, Any], handler: BaseHTTPRequestHandler | None) -> dict[str, Any]:
    if form.get("compliance_confirm", "").lower() not in {"yes", "on", "true", "1"}:
        raise ValueError("Please confirm the email compliance checkbox before sending.")
    document_id = form.get("document_id", "").strip()
    file_id = form.get("file_id", "").strip()
    doc = find_document(document_id)
    attachment = find_file_attachment(file_id)
    if not doc or not attachment or str(attachment.get("document_id", "")) != document_id:
        raise ValueError("Document or attachment not found.")
    if str(attachment.get("confidentiality_level", "")) == "personal_data" and form.get("personal_data_confirm", "").lower() not in {"yes", "on", "true", "1"}:
        raise ValueError("Please confirm the personal-data email checkbox before sending.")
    eligible, reason = email_send_eligibility(user, doc, attachment)
    if not eligible:
        raise ValueError(reason)
    to_recipients = parse_email_recipients(form.get("to_emails", ""), 5, "To")
    if not to_recipients:
        raise ValueError("At least one To recipient is required.")
    cc_recipients = parse_email_recipients(form.get("cc_emails", ""), 10, "Cc")
    bcc_recipients = parse_email_recipients(form.get("bcc_emails", ""), 10, "Bcc")
    context = email_context_for(doc, attachment)
    context["sender_name"] = user_display_name(user)
    template = find_email_template(form.get("email_template_id", "").strip()) or default_email_template_for(doc, attachment) or {}
    subject = form.get("subject", "").strip() or render_email_text(str(template.get("subject_template", "FileAdmin document: {{document_title}}")), context)
    body_text = form.get("body_text", "").strip() or render_email_text(str(template.get("body_template", "Please find the attached document for review.")), context)
    rows = email_messages()
    email_id = next_sequence_id(rows, "email_id", "EMAIL")
    now = now_iso()
    generation_id = context.get("generation_id", "")
    approval_snapshot = {
        "document_status": doc.get("status", ""),
        "file_status": attachment.get("file_status", ""),
        "review_status": (doc.get("template") or {}).get("review_status", "") if isinstance(doc.get("template"), dict) else "",
    }
    message_row = {
        "email_id": email_id,
        "document_id": document_id,
        "file_id": file_id,
        "generation_id": generation_id,
        "email_template_id": template.get("email_template_id", ""),
        "email_type": template.get("email_type", form.get("email_type", "document_send")),
        "recipient_type": form.get("recipient_type", "candidate").strip() or "candidate",
        "to": to_recipients,
        "cc": cc_recipients,
        "bcc": bcc_recipients,
        "subject": subject,
        "body_text": body_text,
        "body_html": "",
        "attachment_file_ids": [file_id],
        "status": "queued",
        "send_mode": EMAIL_SEND_MODE if EMAIL_SEND_MODE in {"dry_run", "smtp"} else "dry_run",
        "smtp_message_id": "",
        "error_message": "",
        "created_by": audit_actor_from_user(user),
        "created_at": now,
        "sent_by": "",
        "sent_at": "",
        "approved_before_send": True,
        "approval_snapshot": approval_snapshot,
        "notes": form.get("notes", "").strip(),
    }
    action = "email_dry_run_created"
    if message_row["send_mode"] == "smtp":
        try:
            message_row["smtp_message_id"] = send_smtp_email(message_row, attachment)
            message_row["status"] = "sent"
            message_row["sent_by"] = audit_actor_from_user(user)
            message_row["sent_at"] = now_iso()
            action = "email_sent"
        except Exception as exc:  # noqa: BLE001
            message_row["status"] = "failed"
            message_row["error_message"] = str(exc)
            action = "email_send_failed"
    else:
        message_row["status"] = "dry_run"
    rows.append(message_row)
    save_json_array(EMAIL_MESSAGES_PATH, rows)
    append_audit_log(email_id, "email_message", action, {}, message_row, user, handler)
    return message_row


def email_recipient_text(recipients: list[dict[str, str]]) -> str:
    return ", ".join(item.get("email", "") for item in recipients)


def email_messages_html(user: dict[str, Any]) -> str:
    visible_docs = {str(doc.get("document_id", "")) for doc in documents() if can_view_document(user, doc)}
    rows = [row for row in email_messages() if str(row.get("document_id", "")) in visible_docs]
    rows = sorted(rows, key=lambda row: str(row.get("created_at", "")), reverse=True)
    body = page_header("Email Sending", "邮件发送记录", "只发送已确认文件；默认 dry_run，不会真实发送外部邮件。")
    body += "<section class='sap-section'><div class='table-scroll'><table><tr><th>Time</th><th>Status</th><th>Document</th><th>Recipients</th><th>Subject</th><th>Action</th></tr>"
    for row in rows[:300]:
        body += f"<tr><td>{h(row.get('created_at'))}</td><td>{status_badge(str(row.get('status', '')))}<br><small>{h(row.get('send_mode'))}</small></td><td><a href='/documents/detail?id={h(row.get('document_id'))}'>{h(document_title(str(row.get('document_id', ''))))}</a></td><td>{h(email_recipient_text(row.get('to', [])))}</td><td>{h(row.get('subject'))}</td><td><a class='button ghost' href='/emails/detail?id={h(row.get('email_id'))}'>Detail</a></td></tr>"
    if not rows:
        body += "<tr><td colspan='6' class='muted'>No email sending records yet.</td></tr>"
    body += "</table></div></section>"
    return body


def email_new_form_html(document_id: str, file_id: str, user: dict[str, Any], form: dict[str, str] | None = None) -> str:
    form = form or {}
    doc = find_document(document_id)
    attachment = find_file_attachment(file_id)
    if not doc or not attachment:
        return page_header("Not Found", "Document or attachment not found", f"{document_id} / {file_id}")
    if not can_send_attachment_email(user, doc, attachment):
        return forbidden_html("Only approved/active/signed files, or approved generated drafts, can be sent by email.")
    context = email_context_for(doc, attachment)
    context["sender_name"] = user_display_name(user)
    template = default_email_template_for(doc, attachment) or {}
    default_to = context.get("candidate_email", "")
    subject = form.get("subject") or render_email_text(str(template.get("subject_template", "FileAdmin document: {{document_title}}")), context)
    body_text = form.get("body_text") or render_email_text(str(template.get("body_template", "Please find the attached document for review.")), context)
    template_options = option_html([(str(row.get("email_template_id", "")), str(row.get("template_name", row.get("template_code", "")))) for row in email_templates() if row.get("status") == "active"], str(template.get("email_template_id", "")))
    eligible, eligibility_reason = email_send_eligibility(user, doc, attachment)
    recipient_source = "来源：Template Generation parameter candidate_email" if default_to else "未找到默认邮箱，请手动输入。"
    mode_warning = "当前模式：DRY RUN。本次不会真实发送邮件，只会生成发送记录和审计日志。" if EMAIL_SEND_MODE != "smtp" else "当前模式：SMTP REAL SEND。提交后将真实发送邮件，请再次确认收件人和附件。"
    mode_class = "message-warning" if EMAIL_SEND_MODE != "smtp" else "message-error"
    file_size = int(attachment.get("file_size_bytes") or 0)
    file_size_text = f"{file_size:,} bytes" if file_size else "-"
    review_status = str((doc.get("template") or {}).get("review_status", "")) if isinstance(doc.get("template"), dict) else ""
    personal_data_checkbox = ""
    if str(attachment.get("confidentiality_level", "")) == "personal_data":
        personal_data_checkbox = "<label><input type='checkbox' name='personal_data_confirm' value='yes' required style='width:auto;'> 我确认该邮件包含个人信息，收件人和附件内容已经审核。</label>"
    body = page_header("Send Email", "发送确认后的文件", "默认 dry_run：先生成发送记录和审计，不真实发送外部邮件。")
    body += f"""
    <section class="message-strip {mode_class}"><strong>{h(mode_warning)}</strong></section>
    <section class="message-strip message-warning">发送前请确认附件内容已完成内部审核，收件人邮箱正确，且当前文件不是草稿。</section>
    <form method="post" action="/emails/send">
      <input type="hidden" name="document_id" value="{h(document_id)}">
      <input type="hidden" name="file_id" value="{h(file_id)}">
      <section class="sap-section">
        <h3>Attachment Confirmation / 附件确认</h3>
        <p class="notice">请在发送前再次确认下面的文件就是要发给客户或人选的版本。</p>
        <div class="sap-readonly-grid">
          <div class="sap-readonly-field"><div class="label">Document</div><div class="value">{h(doc.get('title'))}<br><small>{h(doc.get('document_no'))}</small></div></div>
          <div class="sap-readonly-field"><div class="label">Attachment</div><div class="value">{h(attachment.get('file_title') or attachment.get('original_filename'))}<br><small>{h(attachment.get('original_filename'))}</small></div></div>
          <div class="sap-readonly-field"><div class="label">File Status</div><div class="value">{status_badge(str(attachment.get('file_status', '')))}</div></div>
          <div class="sap-readonly-field"><div class="label">Review Status</div><div class="value">{status_badge(review_status) if review_status else h('-')}</div></div>
          <div class="sap-readonly-field"><div class="label">File Type / Size</div><div class="value">{h(attachment.get('file_type'))}<br><small>{h(file_size_text)}</small></div></div>
          <div class="sap-readonly-field"><div class="label">Confidentiality</div><div class="value">{h(attachment.get('confidentiality_level'))}</div></div>
          <div class="sap-readonly-field"><div class="label">Eligibility</div><div class="value">{status_badge('can_send' if eligible else 'blocked')}<br><small>{h(eligibility_reason)}</small></div></div>
          <div class="sap-readonly-field"><div class="label">Preview</div><div class="value"><a class="button ghost" href="/attachments/download?file_id={h(file_id)}">Download / Preview</a></div></div>
        </div>
      </section>
      <section class="sap-section">
        <h3>Email</h3>
        <div class="form-grid">
          <div class="form-field"><label>Email Template</label><select name="email_template_id"><option value="">Default</option>{template_options}</select><small class="muted">自动选择模板：{h(template.get('template_name', 'Default'))}</small></div>
          <div class="form-field"><label>Recipient Type</label><select name="recipient_type"><option value="candidate">Candidate</option><option value="customer">Customer</option><option value="employee">Employee</option><option value="internal">Internal</option></select></div>
          <div class="form-field"><label>To *</label><input name="to_emails" required value="{h(form.get('to_emails', default_to))}" placeholder="name@example.com"><small class="muted">{h(recipient_source)}</small></div>
          <div class="form-field"><label>Cc</label><input name="cc_emails" value="{h(form.get('cc_emails', ''))}"></div>
          <div class="form-field"><label>Bcc</label><input name="bcc_emails" value="{h(form.get('bcc_emails', ''))}"></div>
        </div>
        <div class="form-field"><label>Subject *</label><input name="subject" required value="{h(subject)}"></div>
        <div class="form-field"><label>Body *</label><textarea name="body_text" required>{h(body_text)}</textarea></div>
        <div class="form-field"><label>Available Variables</label><p class="muted">{{{{candidate_name}}}}, {{{{company_name}}}}, {{{{sender_name}}}}, {{{{document_title}}}}, {{{{file_title}}}}, {{{{client_name}}}}</p></div>
        <div class="form-field"><label>Notes</label><input name="notes" placeholder="Internal sending note"></div>
        <label><input type="checkbox" name="compliance_confirm" value="yes" required style="width:auto;"> 我确认附件内容已经完成内部审核，可以按当前收件人执行发送 / dry-run。</label>
        {personal_data_checkbox}
      </section>
      <div class="sap-toolbar"><a class="button ghost" href="/documents/detail?id={h(document_id)}">Cancel</a><button type="submit">Create Email Sending Record</button></div>
    </form>
    """
    return body


def email_detail_html(email_id: str, user: dict[str, Any]) -> str:
    row = find_email_message(email_id)
    if not row:
        return page_header("Not Found", "Email record not found", email_id)
    doc = find_document(str(row.get("document_id", "")))
    if not can_view_document(user, doc):
        return forbidden_html("You do not have permission to view this email record.")
    detail_json = json.dumps(row, ensure_ascii=False, indent=2)
    return page_header("Email Detail", str(row.get("subject", "")), "邮件发送记录不可删除；默认 dry_run 不真实发送。") + f"""
    <section class="sap-section">
      <div class="sap-readonly-grid">
        <div class="sap-readonly-field"><div class="label">Email ID</div><div class="value">{h(row.get('email_id'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Status</div><div class="value">{status_badge(str(row.get('status', '')))}</div></div>
        <div class="sap-readonly-field"><div class="label">Mode</div><div class="value">{h(row.get('send_mode'))}</div></div>
        <div class="sap-readonly-field"><div class="label">To</div><div class="value">{h(email_recipient_text(row.get('to', [])))}</div></div>
      </div>
      <div class="actions" style="margin-top:14px;"><a class="button" href="/documents/detail?id={h(row.get('document_id'))}">Open Document</a><a class="button secondary" href="/emails">Back to Emails</a></div>
    </section>
    <section class="sap-section"><h3>Body</h3><pre>{h(row.get('body_text', ''))}</pre></section>
    <section class="sap-section"><h3>Raw Record</h3><details><summary>JSON</summary><pre>{h(detail_json)}</pre></details></section>
    """


def attachment_actions_html(doc: dict[str, Any], attachment: dict[str, Any], user: dict[str, Any]) -> str:
    file_id = str(attachment.get("file_id", ""))
    eligible, reason = email_send_eligibility(user, doc, attachment)
    actions = [f"<a class='button ghost' href='/attachments/download?file_id={h(file_id)}'>Download</a>"]
    if eligible:
        actions.append(f"<a class='button secondary' href='/emails/new?document_id={h(doc.get('document_id'))}&file_id={h(file_id)}'>Send Email</a>")
    eligibility_html = f"<div style='margin-top:6px;'>{status_badge('can_send' if eligible else 'blocked')}<br><small class='muted'>{h(reason)}</small></div>"
    return " ".join(actions) + eligibility_html


def version_upload_form_html(document_id: str, user: dict[str, Any]) -> str:
    doc = find_document(document_id)
    if not doc:
        return page_header("Not Found", "Document not found", document_id)
    if not can_upload_attachment(user, doc):
        return forbidden_html("You do not have permission to upload attachments for this document, or the document is archived.")
    existing = document_file_attachments(document_id) or document_versions(document_id)
    default_version = f"v1.{len(existing)}" if existing else "v1.0"
    return page_header("Upload Attachment", f"上传文件附件：{doc.get('title')}", "同一文档记录可以包含多个文件；每个文件都需要单独描述、分类、标记版本和签署/当前有效状态。") + f"""
    <form method="post" action="/versions/upload" enctype="multipart/form-data">
      <input type="hidden" name="document_id" value="{h(document_id)}">
      <section class="sap-section">
        <h3>Attachment Metadata</h3>
        <div class="form-grid">
          <div class="form-field"><label>File Title *</label><input name="file_title" required placeholder="例：派遣基本契約書 双方盖章版"></div>
          <div class="form-field"><label>File Type</label><select name="file_type">{option_html(FILE_TYPES, 'contract_signed_pdf')}</select></div>
          <div class="form-field"><label>File Role</label><select name="file_role">{option_html(FILE_ROLES, 'main_contract')}</select></div>
          <div class="form-field"><label>Version No</label><input name="version_no" value="{h(default_version)}"></div>
          <div class="form-field"><label>Status</label><select name="file_status">{text_option_html(VERSION_STATUSES, 'active')}</select></div>
          <div class="form-field"><label>Current Effective File</label><select name="is_current"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Signed / Sealed File</label><select name="is_signed"><option value="yes">Yes</option><option value="no">No</option></select></div>
          <div class="form-field"><label>Original Scan</label><select name="is_original_scan"><option value="no">No</option><option value="yes">Yes</option></select></div>
          <div class="form-field"><label>Language</label><select name="file_language">{option_html(LANGUAGES, str(doc.get('language', 'ja')))}</select></div>
          <div class="form-field"><label>Confidentiality</label><select name="file_confidentiality_level">{option_html(CONFIDENTIALITY_LEVELS, str(doc.get('confidentiality_level', 'contract_confidential')))}</select></div>
          <div class="form-field"><label>File Effective Start</label><input type="date" name="file_effective_start_date"></div>
          <div class="form-field"><label>File Effective End</label><input type="date" name="file_effective_end_date"></div>
          <div class="form-field"><label>Attachment *</label><input type="file" name="attachment" required></div>
        </div>
        <div class="form-field"><label>File Description *</label><textarea name="file_description" required placeholder="说明这个文件在合同包里的作用、适用范围、是否正式签署等"></textarea></div>
        <div class="form-grid">
          <div class="form-field"><label>Change Reason</label><input name="change_reason" placeholder="初回登记、客户签署版、补充协议、模板更新等"></div>
          <div class="form-field"><label>Notes</label><input name="version_notes"></div>
        </div>
      </section>
      <div class="sap-toolbar"><a class="button ghost" href="/documents/detail?id={h(document_id)}">Cancel</a><button type="submit">Upload Attachment</button></div>
    </form>
    """


def document_detail_html(document_id: str, user: dict[str, Any]) -> str:
    doc = find_document(document_id)
    if not doc:
        return page_header("Not Found", "Document not found", document_id)
    if not can_view_document(user, doc):
        return forbidden_html("You do not have permission to view this document record.")
    contract = doc.get("contract") if isinstance(doc.get("contract"), dict) else {}
    template = doc.get("template") if isinstance(doc.get("template"), dict) else {}
    current_version = current_version_for(doc)
    meta = [
        ("Document ID", str(doc.get("document_id", ""))),
        ("Document No", str(doc.get("document_no", ""))),
        ("Status", str(doc.get("status", ""))),
        ("Owner", str(doc.get("owner_name_snapshot") or doc.get("owner_user_id") or "")),
    ]
    body = page_header("Document Detail", str(doc.get("title", "")), str(doc.get("summary", "")), meta)
    body += f"""
    <section class="sap-section">
      <h3>Actions</h3>
      <div class="actions">
        <a class="button" href="/versions/upload?document_id={h(document_id)}">Upload File Attachment</a>
        <a class="button secondary" href="/documents">Back to Register</a>
        <a class="button ghost" href="{h(PORTAL_BASE_URL)}/dashboard">Back to Portal</a>
      </div>
    </section>
    <section class="sap-section">
      <h3>Document Metadata</h3>
      <div class="sap-readonly-grid">
        <div class="sap-readonly-field"><div class="label">Type</div><div class="value">{h(doc.get('document_type'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Business Line</div><div class="value">{h(doc.get('business_line'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Entity</div><div class="value">{h(doc.get('entity_id'))} {h(doc.get('entity_name_snapshot'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Counterparty</div><div class="value">{h(doc.get('customer_name_snapshot') or doc.get('vendor_name_snapshot') or doc.get('project_name_snapshot') or '-')}</div></div>
        <div class="sap-readonly-field"><div class="label">Confidentiality</div><div class="value">{h(doc.get('confidentiality_level'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Language</div><div class="value">{h(doc.get('language'))}</div></div>
      </div>
    </section>
    <section class="sap-section">
      <h3>Contract / Template</h3>
      <div class="sap-readonly-grid">
        <div class="sap-readonly-field"><div class="label">Contract Period</div><div class="value">{h(contract.get('contract_start_date'))} → {h(contract.get('contract_end_date'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Auto Renewal</div><div class="value">{h(contract.get('auto_renewal'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Notice Days</div><div class="value">Renewal {h(contract.get('renewal_notice_days'))} / Termination {h(contract.get('termination_notice_days'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Template</div><div class="value">{h(template.get('template_code'))} Current: {h(template.get('is_current_template'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Payment Terms</div><div class="value">{h(contract.get('payment_terms'))}</div></div>
        <div class="sap-readonly-field"><div class="label">Risk Notes</div><div class="value">{h(contract.get('risk_notes'))}</div></div>
      </div>
    </section>
    """
    if template.get("is_template_generated"):
        body += f"""
        <section class="sap-section">
          <h3>Template Generation</h3>
          <p class="message-strip message-warning">This document was generated from a system-suggested standard template. It is not a formal approved template and requires human review.</p>
          <div class="sap-readonly-grid">
            <div class="sap-readonly-field"><div class="label">Generation ID</div><div class="value"><a href="/templates/runs/detail?id={h(template.get('generation_id'))}">{h(template.get('generation_id'))}</a></div></div>
            <div class="sap-readonly-field"><div class="label">Template Code</div><div class="value">{h(template.get('template_code_snapshot'))}</div></div>
            <div class="sap-readonly-field"><div class="label">Template Version</div><div class="value">{h(template.get('template_version_snapshot'))}</div></div>
            <div class="sap-readonly-field"><div class="label">Review Status</div><div class="value">{status_badge(str(template.get('review_status', 'pending')))}</div></div>
            <div class="sap-readonly-field"><div class="label">Source Type</div><div class="value">{h(template.get('template_source_type'))}</div></div>
            <div class="sap-readonly-field"><div class="label">Formal Approval Later</div><div class="value">{h(template.get('formal_approval_required_later'))}</div></div>
          </div>
        </section>
        """
    attachment_rows = sorted(document_file_attachments(document_id), key=lambda item: str(item.get("uploaded_at", "")), reverse=True)
    body += "<section class='sap-section'><h3>File Attachments</h3><p class='notice'>一条文档记录可以包含多个文件附件；每个附件都有独立说明、类型、角色、版本、当前有效和签署状态。</p><div class='table-scroll'><table><tr><th>Title / Description</th><th>Type / Role</th><th>Version</th><th>Current</th><th>Signed</th><th>Language</th><th>Effective Period</th><th>Uploaded</th><th>Action</th></tr>"
    for row in attachment_rows:
        effective_period = f"{row.get('file_effective_start_date', '')} → {row.get('file_effective_end_date', '')}".strip(" →")
        body += f"<tr><td><strong>{h(row.get('file_title') or row.get('original_filename'))}</strong><br><small class='muted'>{h(row.get('file_description') or row.get('notes') or '-')}</small><br><small>{h(row.get('original_filename'))}</small></td><td>{h(row.get('file_type'))}<br><small class='muted'>{h(row.get('file_role'))}</small></td><td>{h(row.get('version_no'))}<br>{status_badge(str(row.get('file_status') or row.get('status') or 'active'))}</td><td>{status_badge('current') if row.get('is_current') else h('history')}</td><td>{status_badge('signed') if row.get('is_signed') else h('not signed')}</td><td>{h(row.get('language'))}<br><small>{h(row.get('confidentiality_level'))}</small></td><td>{h(effective_period or '-')}</td><td>{h(row.get('uploaded_at'))}<br><small>{h(row.get('uploaded_by'))}</small></td><td>{attachment_actions_html(doc, row, user)}</td></tr>"
    if not attachment_rows:
        body += "<tr><td colspan='9' class='muted'>No file attachments yet. Use Upload File Attachment to add the main contract, NDA, amendment, signed scan, email evidence, or template file.</td></tr>"
    body += "</table></div></section>"

    if current_version:
        body += f"""
        <section class="sap-section">
          <h3>当前最新版本</h3>
          <p>{status_badge(str(current_version.get('status', '')))} <strong>{h(current_version.get('version_no'))}</strong> — {h(current_version.get('original_filename'))}</p>
          <p class="muted">SHA-256: {h(current_version.get('sha256'))}</p>
          <div class="actions"><a class="button" href="/versions/download?version_id={h(current_version.get('version_id'))}">Download Current Version</a></div>
        </section>
        """
    body += "<section class='sap-section'><h3>版本历史</h3><p class='notice'>上传新版本后会自动成为最新版本；旧版本会保留为 replaced 历史版本，并保留上传人与变更原因。</p><div class='table-scroll'><table><tr><th>Version</th><th>Status</th><th>Current</th><th>File</th><th>Uploaded</th><th>Change Reason</th><th>Hash</th><th>Action</th></tr>"
    for row in sorted(document_versions(document_id), key=lambda item: str(item.get("uploaded_at", "")), reverse=True):
        body += f"<tr><td>{h(row.get('version_no'))}</td><td>{status_badge(str(row.get('status', '')))}</td><td>{status_badge('current') if row.get('is_current') else h('history')}</td><td>{h(row.get('original_filename'))}</td><td>{h(row.get('uploaded_at'))}<br><small>{h(row.get('uploaded_by'))}</small></td><td>{h(row.get('change_reason') or row.get('notes') or '-')}</td><td><small>{h(row.get('sha256'))}</small></td><td><a class='button ghost' href='/versions/download?version_id={h(row.get('version_id'))}'>Download</a></td></tr>"
    if not document_versions(document_id):
        body += "<tr><td colspan='8' class='muted'>No version uploaded yet.</td></tr>"
    body += "</table></div></section>"
    body += "<section class='sap-section'><h3>Reminders</h3><div class='table-scroll'><table><tr><th>Type</th><th>Reminder Date</th><th>Due Date</th><th>Status</th><th>Message</th></tr>"
    for row in document_reminders(document_id):
        body += f"<tr><td>{h(row.get('reminder_type'))}</td><td>{h(row.get('reminder_date'))}</td><td>{h(row.get('due_date'))}</td><td>{status_badge(str(row.get('status', '')))}</td><td>{h(row.get('message'))}</td></tr>"
    if not document_reminders(document_id):
        body += "<tr><td colspan='5' class='muted'>No reminders.</td></tr>"
    body += "</table></div></section>"
    email_rows = sorted(document_email_messages(document_id), key=lambda item: str(item.get("created_at", "")), reverse=True)
    body += "<section class='sap-section'><h3>Email Sending History</h3><p class='notice'>这里显示该文档相关的系统邮件发送记录。dry_run 只生成记录和审计，不真实发送。</p><div class='table-scroll'><table><tr><th>Time</th><th>Status</th><th>Mode</th><th>Recipients</th><th>Subject</th><th>User</th><th>Action</th></tr>"
    for row in email_rows[:20]:
        body += f"<tr><td>{h(row.get('created_at'))}</td><td>{status_badge(str(row.get('status', '')))}</td><td>{h(row.get('send_mode'))}</td><td>{h(email_recipient_text(row.get('to', [])))}</td><td>{h(row.get('subject'))}</td><td>{h(row.get('created_by'))}</td><td><a class='button ghost' href='/emails/detail?id={h(row.get('email_id'))}'>Detail</a></td></tr>"
    if not email_rows:
        body += "<tr><td colspan='7' class='muted'>No email sending records for this document yet.</td></tr>"
    body += "</table></div></section>"
    related_audit = [row for row in audit_logs() if str(row.get("record_id")) == document_id]
    body += "<section class='sap-section'><h3>Audit Summary</h3><div class='table-scroll'><table><tr><th>Time</th><th>Action</th><th>User</th><th>Notes</th></tr>"
    for row in sorted(related_audit, key=lambda item: str(item.get("timestamp", "")), reverse=True)[:10]:
        body += f"<tr><td>{h(row.get('timestamp'))}</td><td>{status_badge(str(row.get('action', '')))}</td><td>{h(row.get('user'))}</td><td>{h(row.get('notes'))}</td></tr>"
    if not related_audit:
        body += "<tr><td colspan='4' class='muted'>No audit events.</td></tr>"
    body += "</table></div></section>"
    if doc.get("status") != "archived":
        body += f"""
        <section class="sap-section">
          <h3>Archive Document</h3>
          <p class="message-strip message-warning">Archive keeps metadata, versions, reminders and files. It does not physically delete records.</p>
          <form method="post" action="/documents/archive" class="form-grid">
            <input type="hidden" name="document_id" value="{h(document_id)}">
            <div class="form-field"><label>Archive Reason</label><input name="archive_reason" required></div>
            <div class="form-field"><label>&nbsp;</label><button class="danger" type="submit">Archive Only</button></div>
          </form>
        </section>
        """
    return body


def reminders_html(user: dict[str, Any]) -> str:
    visible_document_ids = {str(row.get("document_id", "")) for row in documents() if can_view_document(user, row)}
    rows = sorted([row for row in reminders() if str(row.get("document_id", "")) in visible_document_ids], key=lambda row: (str(row.get("status", "")), str(row.get("reminder_date", ""))))
    body = page_header("Contract Reminders", "合同到期与续约提醒", "按过期、7/14/30/60/90 天分组处理合同风险。")
    body += "<section class='sap-section'><h3>Reminder List</h3><div class='table-scroll'><table><tr><th>Bucket</th><th>Document</th><th>Type</th><th>Reminder</th><th>Due</th><th>Status</th><th>Owner</th><th>Action</th></tr>"
    for row in rows:
        status = str(row.get("status", ""))
        action_html = ""
        if status not in {"completed", "waived"} and has_permission(user, "fileadmin.reminders.manage"):
            options = "".join(f'<option value="{s}">{s}</option>' for s in ["acknowledged", "in_progress", "completed", "waived"])
            action_html = f"""
            <form method="post" action="/reminders/update-status" style="display:flex;gap:6px;align-items:center;">
              <input type="hidden" name="reminder_id" value="{h(row.get('reminder_id'))}">
              <select name="status">{options}</select>
              <input name="action_result" placeholder="Result / reason">
              <button type="submit">Update</button>
            </form>
            """
        body += f"<tr><td>{h(reminder_bucket(row))}</td><td><a href='/documents/detail?id={h(row.get('document_id'))}'>{h(document_title(str(row.get('document_id', ''))))}</a></td><td>{h(row.get('reminder_type'))}</td><td>{h(row.get('reminder_date'))}</td><td>{h(row.get('due_date'))}</td><td>{status_badge(status)}</td><td>{h(row.get('assigned_user_name_snapshot'))}</td><td>{action_html}</td></tr>"
    if not rows:
        body += "<tr><td colspan='8' class='muted'>No reminders yet.</td></tr>"
    body += "</table></div></section>"
    return body


def audit_logs_html(user: dict[str, Any]) -> str:
    rows = sorted(audit_logs(), key=lambda row: str(row.get("timestamp", "")), reverse=True)
    body = page_header("Audit Logs", "审计日志", "只读审计记录。审计日志不得删除。")
    body += "<section class='sap-section'><div class='table-scroll'><table><tr><th>Time</th><th>Action</th><th>Record</th><th>User</th><th>Before</th><th>After</th><th>Hash Chain</th></tr>"
    for row in rows[:300]:
        before_json = json.dumps(row.get("before_value", {}), ensure_ascii=False, indent=2)
        after_json = json.dumps(row.get("after_value", {}), ensure_ascii=False, indent=2)
        hash_json = json.dumps({"previous_hash": row.get("previous_hash", ""), "event_hash": row.get("event_hash", "")}, ensure_ascii=False, indent=2)
        body += f"<tr><td>{h(row.get('timestamp'))}</td><td>{status_badge(str(row.get('action', '')))}</td><td>{h(row.get('record_id'))}</td><td>{h(row.get('user'))}</td><td><details><summary>Before</summary><pre>{h(before_json)}</pre></details></td><td><details><summary>After</summary><pre>{h(after_json)}</pre></details></td><td><details><summary>Hash</summary><pre>{h(hash_json)}</pre></details></td></tr>"
    if not rows:
        body += "<tr><td colspan='7' class='muted'>No audit logs yet.</td></tr>"
    body += "</table></div></section>"
    return body


def forbidden_html(message: str) -> str:
    return page_header("Access Denied", "访问被拒绝", message) + f"<section class='sap-section'><a class='button ghost' href='{h(PORTAL_BASE_URL)}/dashboard'>Back to Portal</a></section>"


class FileAdminHandler(BaseHTTPRequestHandler):
    server_version = "FileAdminMVP/1.0"

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        try:
            lang = self.request_lang(query)
            if path == "/health":
                self._send_text("OK")
                return
            if path == "/login":
                self._send_redirect(self.user_admin_login_url("/dashboard"))
                return
            if path == "/":
                self._send_redirect("/dashboard")
                return
            if path == "/dashboard":
                user = self.require_user("fileadmin.access")
                if not user:
                    return
                self._send_html(page("Dashboard", dashboard_html(user), user, "/dashboard", self.flash_message(), lang))
                return
            if path == "/documents":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                self._send_html(page("Documents", documents_html(query, user), user, "/documents", self.flash_message(), lang))
                return
            if path == "/documents/new":
                user = self.require_user("fileadmin.create")
                if not user:
                    return
                self._send_html(page("New Document", document_form_html(user), user, "/documents/new", self.flash_message(), lang))
                return
            if path == "/templates":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                self._send_html(page("Templates", templates_html(query, user), user, "/templates", self.flash_message(), lang))
                return
            if path == "/templates/generate":
                user = self.require_user("fileadmin.create")
                if not user:
                    return
                template_id = query.get("template_id", [""])[0].strip()
                self._send_html(page("Generate from Template", template_generate_form_html(template_id, user), user, "/templates", self.flash_message(), lang))
                return
            if path == "/templates/runs/detail":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                generation_id = query.get("id", [""])[0].strip()
                self._send_html(page("Template Generation", template_generation_detail_html(generation_id, user), user, "/templates", self.flash_message(), lang))
                return
            if path == "/emails":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                self._send_html(page("Emails", email_messages_html(user), user, "/emails", self.flash_message(), lang))
                return
            if path == "/emails/new":
                user = self.require_user("fileadmin.download")
                if not user:
                    return
                document_id = query.get("document_id", [""])[0].strip()
                file_id = query.get("file_id", [""])[0].strip()
                self._send_html(page("Send Email", email_new_form_html(document_id, file_id, user), user, "/emails", self.flash_message(), lang))
                return
            if path == "/emails/detail":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                email_id = query.get("id", [""])[0].strip()
                self._send_html(page("Email Detail", email_detail_html(email_id, user), user, "/emails", self.flash_message(), lang))
                return
            if path == "/documents/detail":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                document_id = query.get("id", [""])[0].strip()
                self._send_html(page("Document Detail", document_detail_html(document_id, user), user, "/documents", self.flash_message(), lang))
                return
            if path == "/versions/upload":
                user = self.require_user("fileadmin.upload")
                if not user:
                    return
                document_id = query.get("document_id", [""])[0].strip()
                self._send_html(page("Upload Version", version_upload_form_html(document_id, user), user, "/documents", self.flash_message(), lang))
                return
            if path == "/attachments/download":
                user = self.require_user("fileadmin.download")
                if not user:
                    return
                file_id = query.get("file_id", [""])[0].strip()
                self.send_attachment_file(file_id, user)
                return
            if path == "/versions/download":
                user = self.require_user("fileadmin.download")
                if not user:
                    return
                version_id = query.get("version_id", [""])[0].strip()
                self.send_version_file(version_id, user)
                return
            if path == "/reminders":
                user = self.require_user("fileadmin.view")
                if not user:
                    return
                self._send_html(page("Reminders", reminders_html(user), user, "/reminders", self.flash_message(), lang))
                return
            if path == "/audit-logs":
                user = self.require_user("fileadmin.audit.view")
                if not user:
                    return
                self._send_html(page("Audit Logs", audit_logs_html(user), user, "/audit-logs", self.flash_message(), lang))
                return
            self._send_html(page("Not Found", page_header("404", "Page not found", path), lang=lang), status=404)
        except Exception as exc:  # noqa: BLE001 - local MVP shows concise operational errors.
            self._send_html(page("FileAdmin Error", page_header("Error", "Operation failed", str(exc)), lang=lang), status=500)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        lang = self.request_lang(query)
        try:
            if path == "/documents/new":
                user = self.require_user("fileadmin.create")
                if not user:
                    return
                form, files = self._parse_request_form()
                doc = create_document(form, files, user, self)
                self._send_redirect(f"/documents/detail?id={quote(str(doc.get('document_id', '')))}", f"Document {doc.get('document_no')} was saved successfully.")
                return
            if path == "/versions/upload":
                user = self.require_user("fileadmin.upload")
                if not user:
                    return
                form, files = self._parse_request_form()
                document_id = form.get("document_id", "").strip()
                attachment = upload_version(document_id, form, files, user, self)
                self._send_redirect(f"/documents/detail?id={quote(document_id)}", f"Attachment {attachment.get('file_title')} ({attachment.get('version_no')}) was uploaded successfully.")
                return
            if path == "/templates/generate":
                user = self.require_user("fileadmin.create")
                if not user:
                    return
                form, _ = self._parse_request_form()
                result = generate_template_document(form, user, self)
                run = result.get("run", {})
                self._send_redirect(f"/templates/runs/detail?id={quote(str(run.get('generation_id', '')))}", "Generated draft was saved to FileAdmin and is pending review.")
                return
            if path == "/templates/runs/review":
                user = self.require_user("fileadmin.access")
                if not user:
                    return
                form, _ = self._parse_request_form()
                run = update_template_generation_review(form, user, self)
                self._send_redirect(f"/templates/runs/detail?id={quote(str(run.get('generation_id', '')))}", f"Review status updated to {run.get('review_status')}.")
                return
            if path == "/emails/send":
                user = self.require_user("fileadmin.download")
                if not user:
                    return
                form, _ = self._parse_request_form()
                row = create_email_message(form, user, self)
                self._send_redirect(f"/emails/detail?id={quote(str(row.get('email_id', '')))}", f"Email sending record {row.get('email_id')} created with status {row.get('status')}.")
                return
            if path == "/documents/archive":
                user = self.require_user("fileadmin.archive")
                if not user:
                    return
                form, _ = self._parse_request_form()
                self.archive_document(form, user)
                return
            if path == "/reminders/update-status":
                user = self.require_user("fileadmin.reminders.manage")
                if not user:
                    return
                form, _ = self._parse_request_form()
                self.update_reminder_status(form, user)
                return
            self._send_html(page("Not Found", page_header("404", "Page not found", path), lang=lang), status=404)
        except Exception as exc:  # noqa: BLE001
            user = self.current_user()
            self._send_html(page("FileAdmin Error", page_header("Error", "Operation failed", str(exc)), user, lang=lang), status=400)

    def request_lang(self, query: dict[str, list[str]] | None = None) -> str:
        query = query or {}
        lang = query.get("lang", [""])[0].strip().lower()
        if lang not in SUPPORTED_LANGS:
            cookie = SimpleCookie(self.headers.get("Cookie", ""))
            morsel = cookie.get(LANG_COOKIE)
            lang = morsel.value if morsel and morsel.value in SUPPORTED_LANGS else DEFAULT_LANG
        self._response_lang = lang
        return lang

    def current_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return morsel.value if morsel else ""

    def current_user(self) -> dict[str, Any] | None:
        return validate_user_admin_session(self.current_session_id())

    def require_user(self, permission_key: str = REQUIRED_MODULE_PERMISSION) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            self._send_redirect(self.user_admin_login_url(self.path))
            return None
        if not has_permission(user, REQUIRED_MODULE_PERMISSION):
            self._send_html(page("Forbidden", forbidden_html("Missing fileadmin.access permission."), user, lang=getattr(self, "_response_lang", DEFAULT_LANG)), status=403)
            return None
        if permission_key and not has_permission(user, permission_key):
            self._send_html(page("Forbidden", forbidden_html(f"Missing {permission_key} permission."), user, lang=getattr(self, "_response_lang", DEFAULT_LANG)), status=403)
            return None
        return user

    def user_admin_login_url(self, next_path: str) -> str:
        next_url = f"{APP_BASE_URL}{next_path if next_path.startswith('/') else '/' + next_path}"
        return f"{USER_ADMIN_BASE_URL}/login?next={quote(next_url, safe='')}"

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

    def _parse_request_form(self) -> tuple[dict[str, str], dict[str, tuple[str, bytes, str]]]:
        content_length = int(self.headers.get("Content-Length", "0") or 0)
        if content_length > MAX_UPLOAD_BYTES + 1024 * 1024:
            raise ValueError("Request is too large for the FileAdmin MVP upload limit.")
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
                    if content:
                        files[key] = (item.filename, content, item.type or "application/octet-stream")
                else:
                    raw_value = item.value
                    form[key] = raw_value if isinstance(raw_value, str) else raw_value.decode("utf-8", errors="replace")
            return form, files
        body = self.rfile.read(content_length).decode("utf-8")
        return {key: values[0] for key, values in parse_qs(body, keep_blank_values=True).items()}, {}

    def _send_html(self, html_text: str, status: int = 200) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        lang = getattr(self, "_response_lang", DEFAULT_LANG)
        if lang in SUPPORTED_LANGS:
            self.send_header("Set-Cookie", f"{LANG_COOKIE}={lang}; Path=/; SameSite=Lax")
            self.send_header("Content-Language", lang)
        if self.flash_message():
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
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def send_attachment_file(self, file_id: str, user: dict[str, Any]) -> None:
        attachment = find_file_attachment(file_id)
        if not attachment:
            self._send_html(page("Not Found", page_header("Not Found", "Attachment not found", file_id), user), status=404)
            return
        doc = find_document(str(attachment.get("document_id", "")))
        if not can_download_attachment(user, doc, attachment):
            self._send_html(page("Forbidden", forbidden_html("You do not have permission to download this attachment."), user), status=403)
            return
        relative = Path(str(attachment.get("storage_path", "") or attachment.get("stored_path", "")))
        target = (ROOT_DIR / relative).resolve()
        attachments_root = ATTACHMENTS_DIR.resolve()
        if attachments_root not in target.parents:
            self._send_html(page("Forbidden", forbidden_html("Invalid stored path."), user), status=403)
            return
        if not target.exists() or not target.is_file():
            self._send_html(page("Not Found", page_header("Not Found", "Stored file not found", str(relative)), user), status=404)
            return
        payload = target.read_bytes()
        filename = safe_filename(str(attachment.get("original_filename") or target.name))
        content_type = str(attachment.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        append_audit_log(
            str(attachment.get("document_id", file_id)),
            "file_attachment",
            "file_downloaded",
            {},
            {
                "file_id": file_id,
                "filename": filename,
                "file_title": attachment.get("file_title", ""),
                "document_id": attachment.get("document_id", ""),
                "document_title": doc.get("title", "") if doc else "",
                "file_role": attachment.get("file_role", ""),
                "confidentiality_level": attachment.get("confidentiality_level", ""),
                "download_result": "success",
            },
            user,
            self,
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def send_version_file(self, version_id: str, user: dict[str, Any]) -> None:
        version = find_version(version_id)
        if not version:
            self._send_html(page("Not Found", page_header("Not Found", "Version not found", version_id), user), status=404)
            return
        doc = find_document(str(version.get("document_id", "")))
        attachment = find_file_attachment(str(version.get("file_id", ""))) if version.get("file_id") else None
        if attachment:
            if not can_download_attachment(user, doc, attachment):
                self._send_html(page("Forbidden", forbidden_html("You do not have permission to download this version."), user), status=403)
                return
        elif not can_view_document(user, doc) or not has_permission(user, "fileadmin.download"):
            self._send_html(page("Forbidden", forbidden_html("You do not have permission to download this version."), user), status=403)
            return
        relative = Path(str(version.get("stored_path", "")))
        target = (ROOT_DIR / relative).resolve()
        attachments_root = ATTACHMENTS_DIR.resolve()
        if attachments_root not in target.parents:
            self._send_html(page("Forbidden", forbidden_html("Invalid stored path."), user), status=403)
            return
        if not target.exists() or not target.is_file():
            self._send_html(page("Not Found", page_header("Not Found", "Stored file not found", str(relative)), user), status=404)
            return
        payload = target.read_bytes()
        filename = safe_filename(str(version.get("original_filename") or target.name))
        content_type = str(version.get("mime_type") or mimetypes.guess_type(filename)[0] or "application/octet-stream")
        append_audit_log(
            str(version.get("document_id", version_id)),
            "document_version",
            "file_downloaded",
            {},
            {
                "version_id": version_id,
                "file_id": version.get("file_id", ""),
                "filename": filename,
                "document_id": version.get("document_id", ""),
                "document_title": doc.get("title", "") if doc else "",
                "confidentiality_level": (attachment or {}).get("confidentiality_level", str((doc or {}).get("confidentiality_level", ""))),
                "download_result": "success",
            },
            user,
            self,
        )
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def archive_document(self, form: dict[str, str], user: dict[str, Any]) -> None:
        document_id = form.get("document_id", "").strip()
        reason = form.get("archive_reason", "").strip()
        if not reason:
            raise ValueError("Archive reason is required.")
        rows = documents()
        for row in rows:
            if str(row.get("document_id")) == document_id:
                if not can_archive_document(user, row):
                    raise ValueError("You do not have permission to archive this document, or the document is already archived.")
                before = dict(row)
                row["status"] = "archived"
                row["archived_at"] = now_iso()
                row["archived_by"] = audit_actor_from_user(user)
                row["archive_reason"] = reason
                row["updated_at"] = now_iso()
                row["updated_by"] = audit_actor_from_user(user)
                save_json_array(DOCUMENTS_PATH, rows)
                save_document_record_shadow(row)
                append_audit_log(document_id, "document", "document_archived", before, row, user, self, reason)
                mark_generation_archived_for_document(document_id, user, self)
                self._send_redirect("/documents", f"Document {document_id} was archived. Files and audit history were preserved.")
                return
        raise ValueError("Document not found.")

    def update_reminder_status(self, form: dict[str, str], user: dict[str, Any]) -> None:
        reminder_id = form.get("reminder_id", "").strip()
        new_status = form.get("status", "").strip()
        if new_status not in REMINDER_STATUSES:
            raise ValueError("Invalid reminder status.")
        rows = reminders()
        for row in rows:
            if str(row.get("reminder_id")) == reminder_id:
                before = dict(row)
                row["status"] = new_status
                row["action_result"] = form.get("action_result", "").strip()
                row["updated_at"] = now_iso()
                if new_status == "acknowledged":
                    row["acknowledged_by"] = audit_actor_from_user(user)
                    row["acknowledged_at"] = now_iso()
                if new_status in {"completed", "waived"}:
                    row["completed_by"] = audit_actor_from_user(user)
                    row["completed_at"] = now_iso()
                save_json_array(REMINDERS_PATH, rows)
                append_audit_log(str(row.get("document_id", reminder_id)), "contract_reminder", f"contract_reminder_{new_status}", before, row, user, self)
                self._send_redirect("/reminders", f"Reminder {reminder_id} updated to {new_status}.")
                return
        raise ValueError("Reminder not found.")

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return


def main() -> None:
    parser = argparse.ArgumentParser(description="Run FileAdmin local MVP app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    ensure_storage()
    server = ThreadingHTTPServer((args.host, args.port), FileAdminHandler)
    print(f"FileAdmin running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping FileAdmin")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
