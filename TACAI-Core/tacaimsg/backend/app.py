#!/usr/bin/env python3
"""TACAI Message Center & Approval Workflow — local MVP web app.

Zero-dependency Python standard-library implementation for:
  - Message Center (inbox, detail, read/unread, search, retention)
  - Approval Workflow (templates, state machine, delegation, batch actions)
  - Active Notification (publishing, templates, webhooks, training responses)

Data is stored as UTF-8 JSON arrays under ../database.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import html
import io
import json
import mimetypes
import os
import re
import sys
import threading
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Paths & constants
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = ROOT_DIR / "database"
FRONTEND_DIR = ROOT_DIR / "frontend"
MESSAGES_PATH = DATABASE_DIR / "messages.json"
WORKFLOWS_PATH = DATABASE_DIR / "workflows.json"
WORKFLOW_STEPS_PATH = DATABASE_DIR / "workflow_steps.json"
WORKFLOW_RECORDS_PATH = DATABASE_DIR / "workflow_records.json"
WORKFLOW_TEMPLATES_PATH = DATABASE_DIR / "workflow_templates.json"
DELEGATIONS_PATH = DATABASE_DIR / "delegations.json"
NOTIFICATION_TEMPLATES_PATH = DATABASE_DIR / "notification_templates.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"

# Cross-module read-only paths (never written by tacaimsg)
PROJECT_ROOT = ROOT_DIR.parents[1]
USER_ADMIN_USERS_PATH = ROOT_DIR.parent / "User_admin" / "database" / "users.json"
MASTERDATA_ENTITIES_PATH = ROOT_DIR.parent / "masterdata" / "database" / "entities.json"
MASTERDATA_DEPARTMENTS_PATH = ROOT_DIR.parent / "masterdata" / "database" / "departments.json"
EMPLOYEEADMIN_EMPLOYEES_PATH = PROJECT_ROOT / "TAC-employeeadmin" / "database" / "employees.json"

MODULE_NAME = "tacaimsg"
DEFAULT_PORT = 8012
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "tacaimsg_flash"
LANG_COOKIE = "tacaimsg_lang"
SUPPORTED_LANGS = {"zh", "ja", "en"}
DEFAULT_LANG = "zh"
REQUIRED_MODULE_PERMISSION = "tacaimsg.access"
MAX_POST_BYTES = 2 * 1024 * 1024  # 2MB
JSON_WRITE_LOCK = threading.RLock()

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAIMSG_INTERNAL_TOKEN = os.environ.get("TACAIMSG_INTERNAL_TOKEN", "tacai-internal-token").strip()


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


APP_BASE_URL = public_base_url("TACAIMSG_PUBLIC_BASE_URL", DEFAULT_PORT)
PORTAL_BASE_URL = public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")

MESSAGE_TYPES = ["workflow_approval", "notification", "salary_notification", "training_notification", "system"]
MESSAGE_STATUSES = ["unread", "read", "confirmed", "actioned", "expired"]
PRIORITY_LEVELS = ["low", "normal", "high", "urgent"]
WF_STATUSES = ["pending", "processing", "approved", "rejected", "cancelled", "expired"]
STEP_STATUSES = ["pending", "processing", "approved", "rejected", "skipped", "escalated", "timeout"]
WF_ACTIONS = ["approve", "reject", "transfer"]

# Retention constants
RETENTION_APPROVAL_DAYS = 1095  # 3 years
RETENTION_NOTIFICATION_DAYS = 365  # 1 year
DEFAULT_TIMEOUT_HOURS = 48


# ---------------------------------------------------------------------------
# i18n Translations
# ---------------------------------------------------------------------------
TRANSLATIONS = {
    "zh": {
        "app.title": "TACAI 消息中心",
        "app.subtitle": "消息通知、审批工作流和通知推送管理",
        "nav.portal": "返回主 Portal",
        "nav.dashboard": "仪表盘",
        "nav.inbox": "收件箱",
        "nav.workflows": "审批工作流",
        "nav.templates": "审批模板",
        "nav.notifications": "通知管理",
        "nav.delegations": "委托管理",
        "nav.audit": "审计日志",
        "language.label": "语言",
        "current_user": "当前用户",
        "current_entity": "当前法人",
        "no_entity": "无当前法人",
        "dashboard.title": "消息中心仪表盘",
        "dashboard.unread": "未读消息",
        "dashboard.pending_approvals": "待审批",
        "dashboard.active_delegations": "活跃委托",
        "dashboard.expiring_workflows": "即将过期工作流",
        "dashboard.quick_actions": "快捷操作",
        "dashboard.view_inbox": "查看收件箱",
        "dashboard.new_workflow": "新建审批",
        "dashboard.send_notification": "发送通知",
        "inbox.title": "消息收件箱",
        "inbox.filter_type": "类型",
        "inbox.filter_status": "状态",
        "inbox.filter_keyword": "搜索关键词",
        "inbox.filter_start": "开始日期",
        "inbox.filter_end": "结束日期",
        "inbox.filter_btn": "筛选",
        "inbox.mark_all_read": "全部标为已读",
        "inbox.export_csv": "导出CSV",
        "inbox.col_sender": "发送者",
        "inbox.col_title": "标题",
        "inbox.col_type": "类型",
        "inbox.col_status": "状态",
        "inbox.col_priority": "优先级",
        "inbox.col_date": "时间",
        "inbox.col_actions": "操作",
        "inbox.no_messages": "暂无消息",
        "inbox.record_count": "条记录",
        "inbox.showing_filtered": "显示 {shown} / 共 {total} 条记录（已筛选）",
        "inbox.showing_all": "共 {total} 条记录",
        "message.detail_title": "消息详情",
        "message.sender": "发送者",
        "message.recipient": "接收者",
        "message.type": "类型",
        "message.status": "状态",
        "message.priority": "优先级",
        "message.time": "时间",
        "message.back_to_inbox": "返回收件箱",
        "message.mark_read": "标为已读",
        "message.confirm_receipt": "确认收到",
        "message.confirm_training": "确认参加",
        "message.decline_training": "婉拒",
        "message.related_workflow": "关联审批",
        "message.no_related": "无",
        "search.title": "消息搜索",
        "search.keyword": "关键词",
        "search.start": "开始日期",
        "search.end": "结束日期",
        "search.btn": "搜索",
        "search.results": "搜索结果",
        "search.no_results": "未找到匹配消息",
        "audit.title": "审计日志",
        "common.save": "保存",
        "common.cancel": "取消",
        "common.delete": "删除",
        "common.edit": "编辑",
        "common.create": "创建",
        "common.actions": "操作",
        "common.status": "状态",
        "common.no_records": "暂无记录",
        "common.records_total": "共 {total} 条记录",
        "common.confirm": "确认",
        "type.workflow_approval": "审批",
        "type.notification": "通知",
        "type.salary_notification": "薪资通知",
        "type.training_notification": "培训通知",
        "type.system": "系统",
        "status.unread": "未读",
        "status.read": "已读",
        "status.confirmed": "已确认",
        "status.actioned": "已处理",
        "status.expired": "已过期",
        "priority.low": "低",
        "priority.normal": "普通",
        "priority.high": "高",
        "priority.urgent": "紧急",
        "msg.read_ok": "已标记为已读",
        "msg.read_all_ok": "已标记全部为已读",
        "msg.confirmed_ok": "已确认收到",
        "msg.training_confirmed": "已确认参加培训",
        "msg.training_declined": "已婉拒培训",
    },
    "ja": {
        "app.title": "TACAI メッセージセンター",
        "app.subtitle": "メッセージ通知、承認ワークフロー、通知配信の管理",
        "nav.portal": "Portalに戻る",
        "nav.dashboard": "ダッシュボード",
        "nav.inbox": "受信箱",
        "nav.workflows": "承認ワークフロー",
        "nav.templates": "承認テンプレート",
        "nav.notifications": "通知管理",
        "nav.delegations": "委任管理",
        "nav.audit": "監査ログ",
        "language.label": "言語",
        "current_user": "現在のユーザー",
        "current_entity": "現在の法人",
        "no_entity": "法人なし",
        "dashboard.title": "メッセージセンターダッシュボード",
        "dashboard.unread": "未読メッセージ",
        "dashboard.pending_approvals": "承認待ち",
        "dashboard.active_delegations": "有効な委任",
        "dashboard.expiring_workflows": "期限切れ間近のワークフロー",
        "dashboard.quick_actions": "クイック操作",
        "dashboard.view_inbox": "受信箱を見る",
        "dashboard.new_workflow": "新規承認",
        "dashboard.send_notification": "通知を送信",
        "inbox.title": "メッセージ受信箱",
        "inbox.filter_type": "種類",
        "inbox.filter_status": "ステータス",
        "inbox.filter_keyword": "キーワード検索",
        "inbox.filter_start": "開始日",
        "inbox.filter_end": "終了日",
        "inbox.filter_btn": "絞り込む",
        "inbox.mark_all_read": "すべて既読にする",
        "inbox.export_csv": "CSVエクスポート",
        "inbox.col_sender": "送信者",
        "inbox.col_title": "タイトル",
        "inbox.col_type": "種類",
        "inbox.col_status": "ステータス",
        "inbox.col_priority": "優先度",
        "inbox.col_date": "日時",
        "inbox.col_actions": "操作",
        "inbox.no_messages": "メッセージがありません",
        "inbox.record_count": "件",
        "inbox.showing_filtered": "{shown}件表示 / 全{total}件（絞り込み中）",
        "inbox.showing_all": "全{total}件",
        "message.detail_title": "メッセージ詳細",
        "message.sender": "送信者",
        "message.recipient": "受信者",
        "message.type": "種類",
        "message.status": "ステータス",
        "message.priority": "優先度",
        "message.time": "日時",
        "message.back_to_inbox": "受信箱に戻る",
        "message.mark_read": "既読にする",
        "message.confirm_receipt": "受領確認",
        "message.confirm_training": "参加確認",
        "message.decline_training": "辞退",
        "message.related_workflow": "関連承認",
        "message.no_related": "なし",
        "search.title": "メッセージ検索",
        "search.keyword": "キーワード",
        "search.start": "開始日",
        "search.end": "終了日",
        "search.btn": "検索",
        "search.results": "検索結果",
        "search.no_results": "一致するメッセージがありません",
        "audit.title": "監査ログ",
        "common.save": "保存",
        "common.cancel": "キャンセル",
        "common.delete": "削除",
        "common.edit": "編集",
        "common.create": "作成",
        "common.actions": "操作",
        "common.status": "ステータス",
        "common.no_records": "レコードがありません",
        "common.records_total": "全{total}件",
        "common.confirm": "確認",
        "type.workflow_approval": "承認",
        "type.notification": "通知",
        "type.salary_notification": "給与通知",
        "type.training_notification": "研修通知",
        "type.system": "システム",
        "status.unread": "未読",
        "status.read": "既読",
        "status.confirmed": "確認済",
        "status.actioned": "処理済",
        "status.expired": "期限切れ",
        "priority.low": "低",
        "priority.normal": "通常",
        "priority.high": "高",
        "priority.urgent": "緊急",
        "msg.read_ok": "既読にしました",
        "msg.read_all_ok": "すべて既読にしました",
        "msg.confirmed_ok": "受領確認済み",
        "msg.training_confirmed": "研修参加を確認しました",
        "msg.training_declined": "研修を辞退しました",
    },
    "en": {
        "app.title": "TACAI Message Center",
        "app.subtitle": "Message notifications, approval workflows, and notification delivery",
        "nav.portal": "Back to Portal",
        "nav.dashboard": "Dashboard",
        "nav.inbox": "Inbox",
        "nav.workflows": "Approval Workflows",
        "nav.templates": "Workflow Templates",
        "nav.notifications": "Notifications",
        "nav.delegations": "Delegations",
        "nav.audit": "Audit Logs",
        "language.label": "Language",
        "current_user": "Current User",
        "current_entity": "Current Entity",
        "no_entity": "No Entity",
        "dashboard.title": "Message Center Dashboard",
        "dashboard.unread": "Unread Messages",
        "dashboard.pending_approvals": "Pending Approvals",
        "dashboard.active_delegations": "Active Delegations",
        "dashboard.expiring_workflows": "Expiring Workflows",
        "dashboard.quick_actions": "Quick Actions",
        "dashboard.view_inbox": "View Inbox",
        "dashboard.new_workflow": "New Workflow",
        "dashboard.send_notification": "Send Notification",
        "inbox.title": "Message Inbox",
        "inbox.filter_type": "Type",
        "inbox.filter_status": "Status",
        "inbox.filter_keyword": "Search keyword",
        "inbox.filter_start": "Start Date",
        "inbox.filter_end": "End Date",
        "inbox.filter_btn": "Filter",
        "inbox.mark_all_read": "Mark All Read",
        "inbox.export_csv": "Export CSV",
        "inbox.col_sender": "Sender",
        "inbox.col_title": "Title",
        "inbox.col_type": "Type",
        "inbox.col_status": "Status",
        "inbox.col_priority": "Priority",
        "inbox.col_date": "Date",
        "inbox.col_actions": "Actions",
        "inbox.no_messages": "No messages",
        "inbox.record_count": "record(s)",
        "inbox.showing_filtered": "Showing {shown} of {total} records (filtered)",
        "inbox.showing_all": "{total} record(s) total",
        "message.detail_title": "Message Detail",
        "message.sender": "Sender",
        "message.recipient": "Recipient",
        "message.type": "Type",
        "message.status": "Status",
        "message.priority": "Priority",
        "message.time": "Time",
        "message.back_to_inbox": "Back to Inbox",
        "message.mark_read": "Mark Read",
        "message.confirm_receipt": "Confirm Receipt",
        "message.confirm_training": "Confirm Attendance",
        "message.decline_training": "Decline",
        "message.related_workflow": "Related Workflow",
        "message.no_related": "None",
        "search.title": "Message Search",
        "search.keyword": "Keyword",
        "search.start": "Start Date",
        "search.end": "End Date",
        "search.btn": "Search",
        "search.results": "Search Results",
        "search.no_results": "No matching messages found",
        "audit.title": "Audit Logs",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.delete": "Delete",
        "common.edit": "Edit",
        "common.create": "Create",
        "common.actions": "Actions",
        "common.status": "Status",
        "common.no_records": "No records",
        "common.records_total": "{total} record(s) total",
        "common.confirm": "Confirm",
        "type.workflow_approval": "Approval",
        "type.notification": "Notification",
        "type.salary_notification": "Salary Notice",
        "type.training_notification": "Training Notice",
        "type.system": "System",
        "status.unread": "Unread",
        "status.read": "Read",
        "status.confirmed": "Confirmed",
        "status.actioned": "Actioned",
        "status.expired": "Expired",
        "priority.low": "Low",
        "priority.normal": "Normal",
        "priority.high": "High",
        "priority.urgent": "Urgent",
        "msg.read_ok": "Marked as read",
        "msg.read_all_ok": "All marked as read",
        "msg.confirmed_ok": "Receipt confirmed",
        "msg.training_confirmed": "Training attendance confirmed",
        "msg.training_declined": "Training declined",
    },
}

# Merge workflow module translations at module load time
try:
    from .workflow import WF_TRANSLATIONS
    for lang_key in ("zh", "ja", "en"):
        if lang_key in WF_TRANSLATIONS and lang_key in TRANSLATIONS:
            TRANSLATIONS[lang_key].update(WF_TRANSLATIONS[lang_key])
except ImportError:
    # Try non-relative import (for direct execution)
    try:
        from workflow import WF_TRANSLATIONS
        for lang_key in ("zh", "ja", "en"):
            if lang_key in WF_TRANSLATIONS and lang_key in TRANSLATIONS:
                TRANSLATIONS[lang_key].update(WF_TRANSLATIONS[lang_key])
    except ImportError:
        pass


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------
def h(text: Any) -> str:
    return html.escape(str(text), quote=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")


def now_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


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


def localize_body(body: str, lang: str) -> str:
    """Replace server-side i18n markers in HTML body."""
    for key, value in TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).items():
        body = body.replace(f"%%{key}%%", value)
    return body


def status_badge(status: str) -> str:
    normalized = (status or "unknown").lower().replace("_", "-")
    return f'<span class="status-badge status-{h(normalized)}">{h(status or "unknown")}</span>'


def priority_badge(priority: str) -> str:
    normalized = (priority or "normal").lower()
    return f'<span class="status-badge status-{h(normalized)}">{h(priority or "normal")}</span>'


def paginate(rows: list[dict[str, Any]], page: int = 1, per_page: int = 20) -> tuple[list[dict[str, Any]], int, int, int]:
    total = len(rows)
    total_pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, total_pages))
    start = (page - 1) * per_page
    return rows[start:start + per_page], total, page, total_pages


def pagination_html(current_page: int, total_pages: int, base_url: str) -> str:
    if total_pages <= 1:
        return ""
    parts = ['<div class="pagination" style="margin-top:16px;display:flex;gap:6px;flex-wrap:wrap;align-items:center">']
    for p in range(1, total_pages + 1):
        if p == current_page:
            parts.append(f'<span style="background:var(--tacai-primary);color:white;padding:6px 12px;border-radius:6px;font-weight:800">{p}</span>')
        else:
            parts.append(f'<a href="{h(base_url)}&page={p}" style="padding:6px 12px;border:1px solid var(--tacai-border);border-radius:6px;text-decoration:none;color:var(--tacai-sidebar)">{p}</a>')
    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# JSON I/O
# ---------------------------------------------------------------------------
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
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2) + "\n"
    tmp_path = path.with_name(f".{path.name}.tmp")
    with JSON_WRITE_LOCK:
        with tmp_path.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, path)


def next_sequence_id(rows: list[dict[str, Any]], key: str, prefix: str, width: int = 4) -> str:
    now = datetime.now(timezone.utc)
    year_month = now.strftime("%Y%m")
    prefix_with_ym = f"{prefix}-{year_month}-"
    max_num = 0
    for row in rows:
        value = str(row.get(key, ""))
        if value.startswith(prefix_with_ym):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix_with_ym}{max_num + 1:0{width}d}"


def next_simple_id(rows: list[dict[str, Any]], key: str, prefix: str, width: int = 4) -> str:
    max_num = 0
    for row in rows:
        value = str(row.get(key, ""))
        if value.startswith(f"{prefix}-"):
            try:
                max_num = max(max_num, int(value.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return f"{prefix}-{max_num + 1:0{width}d}"


# ---------------------------------------------------------------------------
# Data access helpers
# ---------------------------------------------------------------------------
def messages() -> list[dict[str, Any]]:
    return load_json_array(MESSAGES_PATH)


def save_messages(rows: list[dict[str, Any]]) -> None:
    save_json_array(MESSAGES_PATH, rows)


def workflows() -> list[dict[str, Any]]:
    return load_json_array(WORKFLOWS_PATH)


def save_workflows(rows: list[dict[str, Any]]) -> None:
    save_json_array(WORKFLOWS_PATH, rows)


def workflow_steps() -> list[dict[str, Any]]:
    return load_json_array(WORKFLOW_STEPS_PATH)


def save_workflow_steps(rows: list[dict[str, Any]]) -> None:
    save_json_array(WORKFLOW_STEPS_PATH, rows)


def workflow_records() -> list[dict[str, Any]]:
    return load_json_array(WORKFLOW_RECORDS_PATH)


def save_workflow_records(rows: list[dict[str, Any]]) -> None:
    save_json_array(WORKFLOW_RECORDS_PATH, rows)


def workflow_templates() -> list[dict[str, Any]]:
    return load_json_array(WORKFLOW_TEMPLATES_PATH)


def save_workflow_templates(rows: list[dict[str, Any]]) -> None:
    save_json_array(WORKFLOW_TEMPLATES_PATH, rows)


def delegations() -> list[dict[str, Any]]:
    return load_json_array(DELEGATIONS_PATH)


def save_delegations(rows: list[dict[str, Any]]) -> None:
    save_json_array(DELEGATIONS_PATH, rows)


def notification_templates() -> list[dict[str, Any]]:
    return load_json_array(NOTIFICATION_TEMPLATES_PATH)


def save_notification_templates(rows: list[dict[str, Any]]) -> None:
    save_json_array(NOTIFICATION_TEMPLATES_PATH, rows)


def audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def save_audit_logs(rows: list[dict[str, Any]]) -> None:
    save_json_array(AUDIT_LOGS_PATH, rows)


# ---------------------------------------------------------------------------
# User / Session / Permission (adapted from fileadmin)
# ---------------------------------------------------------------------------
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


def has_permission(user: dict[str, Any] | None, permission_key: str) -> bool:
    if not user:
        return False
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return "system_admin" in roles or "*" in permissions or permission_key in permissions


def is_system_admin(user: dict[str, Any] | None) -> bool:
    if not user:
        return False
    roles = {str(role).strip().lower() for role in user.get("roles", []) if str(role).strip()}
    return "system_admin" in roles or "*" in set(user.get("permissions", []))


def user_entity_id(user: dict[str, Any] | None) -> str:
    entity = user_entity(user)
    return str(entity.get("entity_id") or entity.get("entity_code") or "").strip()


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
        user["_session_id"] = session_id
        if isinstance(data.get("session"), dict):
            user["_session"] = data["session"]
        return user
    return None


# ---------------------------------------------------------------------------
# Cross-module read-only data access
# ---------------------------------------------------------------------------
def read_users() -> list[dict[str, Any]]:
    return load_json_array(USER_ADMIN_USERS_PATH)


def read_entities() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_ENTITIES_PATH)


def read_departments() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_DEPARTMENTS_PATH)


def resolve_user_name(user_id: str) -> str:
    for u in read_users():
        if str(u.get("user_id", "")) == user_id:
            return str(u.get("display_name") or u.get("username") or user_id)
    return user_id


def resolve_user_entity(user_id: str) -> str:
    for u in read_users():
        if str(u.get("user_id", "")) == user_id:
            return str(u.get("entity_id") or u.get("entity_code") or "")
    return ""


def find_users_by_role(role_key: str, entity_id: str = "") -> list[dict[str, Any]]:
    result = []
    for u in read_users():
        roles = [str(r).strip().lower() for r in u.get("roles", [])]
        if role_key in roles or "system_admin" in roles:
            if not entity_id or str(u.get("entity_id", "")) == entity_id or "system_admin" in roles:
                result.append(u)
    return result


def find_supervisor(user_id: str) -> dict[str, Any] | None:
    """Find supervisor from employee master data."""
    employees = load_json_array(EMPLOYEEADMIN_EMPLOYEES_PATH) if EMPLOYEEADMIN_EMPLOYEES_PATH.exists() else []
    for emp in employees:
        linked = str(emp.get("linked_user_id") or emp.get("user_id") or "")
        if linked == user_id:
            supervisor_id = str(emp.get("supervisor_id") or emp.get("reports_to") or "")
            if supervisor_id:
                for u in read_users():
                    if str(u.get("user_id", "")) == supervisor_id:
                        return u
    return None


def resolve_user_id_from_employee(employee_id: str) -> dict[str, Any] | None:
    """Resolve a TACAI User Admin user_id from an employee_id.

    Returns the user dict if a linked account exists, None otherwise.
    Checks linked_employee_id field on User Admin users.
    """
    if not employee_id:
        return None
    for u in read_users():
        linked = str(u.get("linked_employee_id", "")).strip()
        if linked and linked == str(employee_id).strip():
            return u
    return None


def resolve_employee_to_users(employee_ids: list[str]) -> dict[str, dict[str, Any] | None]:
    """Batch resolve employee_ids to User Admin user accounts.

    Returns a dict mapping employee_id -> user dict or None.
    """
    result: dict[str, dict[str, Any] | None] = {}
    users = read_users()
    # Build lookup: linked_employee_id -> user
    lookup: dict[str, dict[str, Any]] = {}
    for u in users:
        linked = str(u.get("linked_employee_id", "")).strip()
        if linked:
            lookup[linked] = u
    for eid in employee_ids:
        result[str(eid).strip()] = lookup.get(str(eid).strip())
    return result


def find_all_users_with_accounts(entity_id: str = "") -> list[dict[str, Any]]:
    """Return all active users that have a linked employee record.

    Optionally filter by entity_id.
    """
    result = []
    for u in read_users():
        if str(u.get("status", "active")).lower() != "active":
            continue
        linked = str(u.get("linked_employee_id", "")).strip()
        if not linked:
            continue
        if entity_id and str(u.get("entity_id", "")) != entity_id:
            continue
        result.append(u)
    return result


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------
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
        "audit_id": next_sequence_id(rows, "audit_id", "TMSG", width=6),
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
    save_audit_logs(rows)


# ---------------------------------------------------------------------------
# Message business logic
# ---------------------------------------------------------------------------
def send_message(
    msg_type: str,
    title: str,
    content: str,
    recipient_user_id: str,
    sender_user_id: str = "SYSTEM",
    sender_name: str = "",
    priority: str = "normal",
    biz_type: str = "",
    biz_id: str = "",
    workflow_id: str = "",
    action_buttons: list[dict[str, str]] | None = None,
    template_variables: dict[str, Any] | None = None,
    training_info: dict[str, Any] | None = None,
    created_by: str = "",
) -> dict[str, Any]:
    rows = messages()
    entity_id = resolve_user_entity(recipient_user_id)
    msg = {
        "msg_id": next_sequence_id(rows, "msg_id", "MSG"),
        "msg_type": msg_type,
        "title": title,
        "content": content,
        "sender_user_id": sender_user_id,
        "sender_name": sender_name or resolve_user_name(sender_user_id),
        "recipient_user_id": recipient_user_id,
        "recipient_name": resolve_user_name(recipient_user_id),
        "entity_id": entity_id,
        "entity_code": entity_id,
        "workflow_id": workflow_id,
        "biz_type": biz_type,
        "biz_id": biz_id,
        "status": "unread",
        "priority": priority,
        "action_buttons": action_buttons or [],
        "read_at": "",
        "confirmed_at": "",
        "expires_at": compute_expiry(msg_type),
        "training_info": training_info,
        "template_variables": template_variables or {},
        "created_by": created_by or sender_user_id,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }
    rows.append(msg)
    save_messages(rows)
    return msg


def compute_expiry(msg_type: str) -> str:
    days = RETENTION_APPROVAL_DAYS if msg_type == "workflow_approval" else RETENTION_NOTIFICATION_DAYS
    expiry = datetime.now(timezone.utc) + timedelta(days=days)
    return expiry.strftime("%Y-%m-%dT%H:%M:%S+00:00")


def get_user_messages(
    user_id: str,
    msg_type: str = "",
    status: str = "",
    keyword: str = "",
    start_date: str = "",
    end_date: str = "",
    page: int = 1,
    per_page: int = 20,
) -> dict[str, Any]:
    all_msgs = messages()
    # Filter for this recipient
    filtered = [m for m in all_msgs if str(m.get("recipient_user_id", "")) == user_id]
    if msg_type:
        filtered = [m for m in filtered if m.get("msg_type") == msg_type]
    if status:
        filtered = [m for m in filtered if m.get("status") == status]
    if keyword:
        kw = keyword.lower()
        filtered = [m for m in filtered if kw in str(m.get("title", "")).lower() or kw in str(m.get("content", "")).lower()]
    if start_date:
        filtered = [m for m in filtered if str(m.get("created_at", ""))[:10] >= start_date]
    if end_date:
        filtered = [m for m in filtered if str(m.get("created_at", ""))[:10] <= end_date]
    # Sort newest first
    filtered.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
    paged, total, page_num, total_pages = paginate(filtered, page, per_page)
    unread_count = sum(1 for m in all_msgs if str(m.get("recipient_user_id", "")) == user_id and m.get("status") == "unread")
    return {
        "total": total,
        "unread_count": unread_count,
        "page": page_num,
        "per_page": per_page,
        "total_pages": total_pages,
        "items": paged,
    }


def get_message(msg_id: str) -> dict[str, Any] | None:
    for m in messages():
        if str(m.get("msg_id", "")) == msg_id:
            return m
    return None


def mark_read(msg_id: str, user: dict[str, Any]) -> bool:
    rows = messages()
    for m in rows:
        if str(m.get("msg_id", "")) == msg_id:
            if m.get("status") == "unread":
                m["status"] = "read"
                m["read_at"] = now_iso()
                m["updated_at"] = now_iso()
                save_messages(rows)
                append_audit_log(msg_id, "message", "marked_read", {"status": "unread"}, {"status": "read"}, user)
            return True
    return False


def mark_all_read(user_id: str, msg_type: str, user: dict[str, Any]) -> int:
    rows = messages()
    count = 0
    for m in rows:
        if str(m.get("recipient_user_id", "")) == user_id and m.get("status") == "unread":
            if not msg_type or m.get("msg_type") == msg_type:
                m["status"] = "read"
                m["read_at"] = now_iso()
                m["updated_at"] = now_iso()
                count += 1
    if count:
        save_messages(rows)
        append_audit_log("batch", "message", "marked_all_read", {}, {"count": count, "type": msg_type or "all"}, user)
    return count


def confirm_receipt(msg_id: str, user: dict[str, Any]) -> bool:
    rows = messages()
    for m in rows:
        if str(m.get("msg_id", "")) == msg_id:
            m["status"] = "confirmed"
            m["confirmed_at"] = now_iso()
            m["updated_at"] = now_iso()
            save_messages(rows)
            append_audit_log(msg_id, "message", "confirmed_receipt", {"status": "read"}, {"status": "confirmed"}, user)
            return True
    return False


def training_response(msg_id: str, response: str, user: dict[str, Any]) -> bool:
    rows = messages()
    for m in rows:
        if str(m.get("msg_id", "")) == msg_id:
            ti = m.get("training_info") or {}
            ti["response"] = response
            ti["responded_at"] = now_iso()
            m["training_info"] = ti
            m["status"] = "confirmed"
            m["confirmed_at"] = now_iso()
            m["updated_at"] = now_iso()
            save_messages(rows)
            append_audit_log(msg_id, "message", "training_response", {}, {"response": response}, user)
            return True
    return False


def cleanup_expired_messages() -> int:
    """Remove messages past their retention period. Called periodically."""
    rows = messages()
    now = datetime.now(timezone.utc)
    kept = []
    removed = 0
    for m in rows:
        expires = str(m.get("expires_at", ""))
        if expires:
            try:
                expiry_dt = datetime.fromisoformat(expires.replace("Z", "+00:00"))
                if now > expiry_dt:
                    removed += 1
                    continue
            except (ValueError, TypeError):
                pass
        kept.append(m)
    if removed:
        save_messages(kept)
    return removed


def send_message_batch(
    messages_payload: list[dict[str, Any]],
    sender_user_id: str = "SYSTEM",
    sender_name: str = "",
) -> dict[str, Any]:
    """Batch create messages for multiple recipients.

    Each item in messages_payload should contain:
      - recipient_user_id (required): User Admin user_id
      - msg_type, title, content, priority, biz_type, biz_id, action_buttons, etc.

    Returns a summary dict with per-recipient results.
    """
    rows = messages()
    results = []
    sent_count = 0
    failed_count = 0
    skipped_no_account = 0
    now = now_iso()

    for payload in messages_payload:
        recipient_user_id = str(payload.get("recipient_user_id", "")).strip()
        if not recipient_user_id:
            results.append({
                "recipient": payload.get("employee_id", "unknown"),
                "msg_id": None,
                "status": "no_user_account",
                "message": "Missing recipient_user_id",
            })
            skipped_no_account += 1
            continue

        msg_type = str(payload.get("msg_type", "salary_notification")).strip()
        title = str(payload.get("title", "")).strip()
        content = str(payload.get("content", "")).strip()
        if not title or not content:
            results.append({
                "recipient": recipient_user_id,
                "msg_id": None,
                "status": "failed",
                "message": "Missing title or content",
            })
            failed_count += 1
            continue

        try:
            entity_id = resolve_user_entity(recipient_user_id)
            msg = {
                "msg_id": next_sequence_id(rows, "msg_id", "MSG"),
                "msg_type": msg_type,
                "title": title,
                "content": content,
                "sender_user_id": sender_user_id,
                "sender_name": sender_name or resolve_user_name(sender_user_id),
                "recipient_user_id": recipient_user_id,
                "recipient_name": resolve_user_name(recipient_user_id),
                "entity_id": entity_id,
                "entity_code": entity_id,
                "workflow_id": str(payload.get("workflow_id", "")).strip(),
                "biz_type": str(payload.get("biz_type", "salary_payslip")).strip(),
                "biz_id": str(payload.get("biz_id", "")).strip(),
                "status": "unread",
                "priority": str(payload.get("priority", "normal")).strip(),
                "action_buttons": payload.get("action_buttons") if isinstance(payload.get("action_buttons"), list) else [],
                "read_at": "",
                "confirmed_at": "",
                "expires_at": compute_expiry(msg_type),
                "training_info": None,
                "template_variables": payload.get("template_variables") if isinstance(payload.get("template_variables"), dict) else {},
                "created_by": sender_user_id,
                "created_at": now,
                "updated_at": now,
            }
            rows.append(msg)
            results.append({
                "recipient": recipient_user_id,
                "msg_id": msg["msg_id"],
                "status": "sent",
                "message": "",
            })
            sent_count += 1
        except Exception as exc:
            results.append({
                "recipient": recipient_user_id,
                "msg_id": None,
                "status": "failed",
                "message": str(exc)[:200],
            })
            failed_count += 1

    if sent_count > 0:
        save_messages(rows)

    # Audit log for batch send
    audit_rows = audit_logs()
    audit_entry = {
        "audit_id": next_sequence_id(audit_rows, "audit_id", "TMSG", width=6),
        "module": MODULE_NAME,
        "record_id": "batch",
        "record_type": "message_batch",
        "action": "batch_send",
        "user": sender_user_id,
        "user_name_snapshot": sender_name or sender_user_id,
        "timestamp": now,
        "before_value": {},
        "after_value": {
            "sent_count": sent_count,
            "failed_count": failed_count,
            "skipped_no_account": skipped_no_account,
            "msg_type": messages_payload[0].get("msg_type", "") if messages_payload else "",
        },
        "ip_address": "",
        "user_agent": "internal-api",
        "notes": f"Batch message send via internal API: {sent_count} sent, {failed_count} failed, {skipped_no_account} skipped",
        "previous_hash": str(audit_rows[-1].get("event_hash", "")) if audit_rows else "",
    }
    audit_entry["event_hash"] = audit_payload_hash(audit_entry)
    audit_rows.append(audit_entry)
    save_audit_logs(audit_rows)

    return {
        "sent_count": sent_count,
        "failed_count": failed_count,
        "skipped_no_account": skipped_no_account,
        "total": len(messages_payload),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Page renderer (SAP/Fiori-like inline CSS)
# ---------------------------------------------------------------------------
def page(title: str, body: str, user: dict[str, Any] | None = None, current_path: str = "/", flash: str = "", lang: str = DEFAULT_LANG) -> str:
    lang = normalize_lang(lang)
    nav_links = [
        ("/dashboard", "nav.dashboard", "tacaimsg.access", "📊"),
        ("/messages/inbox", "nav.inbox", "tacaimsg.view", "📬"),
        ("/workflows", "nav.workflows", "tacaimsg.workflow", "📋"),
        ("/workflows/templates", "nav.templates", "tacaimsg.admin", "⚙️"),
        ("/delegations", "nav.delegations", "tacaimsg.delegate", "🔄"),
        ("/audit-logs", "nav.audit", "tacaimsg.audit.view", "📝"),
    ]
    nav_html = "".join(
        f'<a class="{h("active" if path == current_path else "")}" href="{h(url_with_lang(path, lang))}"><span>{icon}</span>{h(tr(lang, label_key))}</a>'
        for path, label_key, permission_key, icon in nav_links
        if has_permission(user, permission_key)
    )
    portal_back_html = f'<a class="portal-back" href="{h(PORTAL_BASE_URL)}/dashboard?lang={h(lang)}">⌂ {h(tr(lang, "nav.portal"))}</a>'
    entity = user_entity(user)
    user_html = ""
    if user:
        entity_text = entity_label(entity) or tr(lang, "no_entity")
        user_html = f"""
        <span class="current-user-chip" title="{h(tr(lang, 'current_user'))}: {h(user_display_name(user))}">
          <small class="current-user-label">{h(tr(lang, "current_user"))}</small>
          <strong>👤 {h(user_display_name(user))}</strong>
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
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-brand">
      <div class="sidebar-title">{h(tr(lang, "app.title"))}</div>
      <p class="sidebar-subtitle">{h(tr(lang, "app.subtitle"))}</p>
    </div>
    <nav>
      {nav_html}
      {portal_back_html}
    </nav>
    <div class="sidebar-footer">
      {language_html}
    </div>
  </aside>
  <main class="content">
    <header class="topbar">
      <div class="topbar-left">
        <p class="eyebrow">TACAI Message Center</p>
        <h1>{h(localize_body(title, lang))}</h1>
      </div>
      <div class="topbar-actions">
        {user_html}
      </div>
    </header>
    {flash_html}
    {body}
  </main>
</div>
</body>
</html>"""


LANGUAGE_LABELS = {
    "ja": "日本語",
    "zh": "中文",
    "en": "English",
}


def language_switcher_html(current_path: str, current_lang: str) -> str:
    parts = [f'<div class="language-switcher"><span class="language-label">{h(tr(current_lang, "language.label"))}</span>']
    for code in ("ja", "zh", "en"):
        label = LANGUAGE_LABELS.get(code, code)
        active = " active" if code == current_lang else ""
        parts.append(f'<a class="lang-link{active}" href="{h(url_with_lang(current_path, code))}">{label}</a>')
    parts.append("</div>")
    return "".join(parts)


def breadcrumb_html(items: list[tuple[str, str]], lang: str) -> str:
    """Render breadcrumb navigation. Each item is (label, url) or (label, "") for current."""
    if not items:
        return ""
    parts = ['<nav class="breadcrumb" aria-label="Breadcrumb">']
    for i, (label, url) in enumerate(items):
        if i > 0:
            parts.append('<span class="separator">/</span>')
        if url:
            parts.append(f'<a href="{h(url_with_lang(url, lang))}">{h(label)}</a>')
        else:
            parts.append(f'<span class="current">{h(label)}</span>')
    parts.append('</nav>')
    return "".join(parts)


def page_header(title: str, subtitle: str = "", eyebrow: str = "", breadcrumb: str = "") -> str:
    eyebrow_html = f'<p class="eyebrow">{h(eyebrow)}</p>' if eyebrow else ""
    subtitle_html = f'<p>{h(subtitle)}</p>' if subtitle else ""
    return f"""{breadcrumb}
<div class="sap-page-header">
  {eyebrow_html}
  <h2>{h(title)}</h2>
  {subtitle_html}
</div>"""


def forbidden_html(message: str) -> str:
    return f"""<div class="message-strip message-error" role="alert">
  <strong>403 Forbidden</strong>
  <p>{h(message)}</p>
</div>"""


# ---------------------------------------------------------------------------
# Message type / status option helpers
# ---------------------------------------------------------------------------
def msg_type_options(lang: str, selected: str = "") -> str:
    options = []
    for mt in MESSAGE_TYPES:
        key = f"type.{mt}"
        label = tr(lang, key) if key in TRANSLATIONS.get(lang, {}) else mt
        sel = " selected" if mt == selected else ""
        options.append(f'<option value="{h(mt)}"{sel}>{h(label)}</option>')
    return "".join(options)


def msg_status_options(lang: str, selected: str = "") -> str:
    options = []
    for ms in MESSAGE_STATUSES:
        key = f"status.{ms}"
        label = tr(lang, key) if key in TRANSLATIONS.get(lang, {}) else ms
        sel = " selected" if ms == selected else ""
        options.append(f'<option value="{h(ms)}"{sel}>{h(label)}</option>')
    return "".join(options)


def msg_priority_options(lang: str, selected: str = "normal") -> str:
    options = []
    for p in PRIORITY_LEVELS:
        key = f"priority.{p}"
        label = tr(lang, key) if key in TRANSLATIONS.get(lang, {}) else p
        sel = " selected" if p == selected else ""
        options.append(f'<option value="{h(p)}"{sel}>{h(label)}</option>')
    return "".join(options)


# ---------------------------------------------------------------------------
# HTML page builders — Phase A: Dashboard + Message Center
# ---------------------------------------------------------------------------
def dashboard_html(user: dict[str, Any], lang: str) -> str:
    user_id = str(user.get("user_id", ""))
    all_msgs = messages()
    entity_id = user_entity_id(user)
    # Unread count
    unread = sum(1 for m in all_msgs if str(m.get("recipient_user_id", "")) == user_id and m.get("status") == "unread")
    # Pending approvals
    wf_list = workflows()
    pending = [w for w in wf_list if w.get("status") in ("pending", "processing")]
    if entity_id and not is_system_admin(user):
        pending = [w for w in pending if str(w.get("entity_id", "")) == entity_id]
    pending_count = len(pending)
    # Active delegations
    del_list = delegations()
    active_del = [d for d in del_list if d.get("status") == "active"]
    del_count = len(active_del)
    # Expiring workflows (within 24h)
    now = datetime.now(timezone.utc)
    expiring = 0
    for w in wf_list:
        if w.get("status") == "processing":
            expires_at = str(w.get("expires_at", ""))
            if expires_at:
                try:
                    exp_dt = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                    if timedelta(0) < (exp_dt - now) < timedelta(hours=24):
                        expiring += 1
                except (ValueError, TypeError):
                    pass

    body = page_header(tr(lang, "dashboard.title"), "", tr(lang, "dashboard.title"))
    body += f"""<div class="grid" style="margin-top:16px">
  <a class="metric-card" href="{h(url_with_lang('/messages/inbox', lang))}">
    <div class="muted" style="font-size:.82rem">{h(tr(lang, 'dashboard.unread'))}</div>
    <div class="metric" style="color:var(--tacai-primary)">{unread}</div>
  </a>
  <a class="metric-card" href="{h(url_with_lang('/workflows?status=processing', lang))}">
    <div class="muted" style="font-size:.82rem">{h(tr(lang, 'dashboard.pending_approvals'))}</div>
    <div class="metric" style="color:var(--tacai-amber)">{pending_count}</div>
  </a>
  <a class="metric-card" href="{h(url_with_lang('/delegations', lang))}">
    <div class="muted" style="font-size:.82rem">{h(tr(lang, 'dashboard.active_delegations'))}</div>
    <div class="metric" style="color:var(--tacai-purple)">{del_count}</div>
  </a>
  <a class="metric-card" href="{h(url_with_lang('/workflows?status=processing', lang))}">
    <div class="muted" style="font-size:.82rem">{h(tr(lang, 'dashboard.expiring_workflows'))}</div>
    <div class="metric" style="color:var(--tacai-red)">{expiring}</div>
  </a>
</div>
<div class="panel" style="margin-top:20px">
  <h3>{h(tr(lang, 'dashboard.quick_actions'))}</h3>
  <div class="actions" style="margin-top:12px">
    <a class="button" href="{h(url_with_lang('/messages/inbox', lang))}">{h(tr(lang, 'dashboard.view_inbox'))}</a>
    <a class="button" href="{h(url_with_lang('/workflows/new', lang))}">{h(tr(lang, 'dashboard.new_workflow'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/delegations/new', lang))}">{h(tr(lang, 'del.new_title'))}</a>
  </div>
</div>"""
    return body


def inbox_html(user: dict[str, Any], lang: str, query_params: dict[str, list[str]]) -> str:
    user_id = str(user.get("user_id", ""))
    msg_type = (query_params.get("type", [""])[0] or "").strip()
    status = (query_params.get("status", [""])[0] or "").strip()
    keyword = (query_params.get("keyword", [""])[0] or "").strip()
    start_date = (query_params.get("start_date", [""])[0] or "").strip()
    end_date = (query_params.get("end_date", [""])[0] or "").strip()
    page_num = int((query_params.get("page", ["1"])[0] or "1"))
    per_page = 20

    result = get_user_messages(user_id, msg_type, status, keyword, start_date, end_date, page_num, per_page)

    bc = breadcrumb_html([(tr(lang, "nav.dashboard"), "/dashboard"), (tr(lang, "nav.inbox"), "")], lang)
    body = page_header(tr(lang, "inbox.title"), "", tr(lang, "inbox.title"), bc)
    # Filter bar
    base_inbox = url_with_lang("/messages/inbox", lang)
    body += f"""<div class="panel" style="margin-bottom:16px">
  <form method="GET" action="{h(base_inbox)}" class="form-grid">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-field"><label>{h(tr(lang, 'inbox.filter_type'))}</label><select name="type">{msg_type_options(lang, msg_type)}</select></div>
    <div class="form-field"><label>{h(tr(lang, 'inbox.filter_status'))}</label><select name="status">{msg_status_options(lang, status)}</select></div>
    <div class="form-field"><label>{h(tr(lang, 'inbox.filter_keyword'))}</label><input type="text" name="keyword" value="{h(keyword)}" placeholder="{h(tr(lang, 'inbox.filter_keyword'))}"></div>
    <div class="form-field"><label>{h(tr(lang, 'inbox.filter_start'))}</label><input type="date" name="start_date" value="{h(start_date)}"></div>
    <div class="form-field"><label>{h(tr(lang, 'inbox.filter_end'))}</label><input type="date" name="end_date" value="{h(end_date)}"></div>
    <div class="form-field" style="display:flex;align-items:flex-end"><button type="submit">{h(tr(lang, 'inbox.filter_btn'))}</button></div>
  </form>
</div>"""
    # Toolbar
    body += f"""<div class="sap-toolbar" style="justify-content:flex-start;margin-bottom:12px">
  <form method="POST" action="{h(url_with_lang('/messages/inbox/mark-read', lang))}" style="display:inline">
    <input type="hidden" name="type" value="{h(msg_type)}">
    <button type="submit" class="button secondary">{h(tr(lang, 'inbox.mark_all_read'))}</button>
  </form>
</div>"""
    # Message table
    if not result["items"]:
        body += f'<div class="message-strip">{h(tr(lang, "inbox.no_messages"))}</div>'
    else:
        body += '<div class="table-scroll"><table><thead><tr>'
        for col_key in ["inbox.col_sender", "inbox.col_title", "inbox.col_type", "inbox.col_priority", "inbox.col_status", "inbox.col_date"]:
            body += f'<th>{h(tr(lang, col_key))}</th>'
        body += "</tr></thead><tbody>"
        for m in result["items"]:
            detail_url = url_with_lang(f"/messages/{m['msg_id']}", lang)
            body += f"""<tr>
  <td>{h(m.get('sender_name', ''))}</td>
  <td><a href="{h(detail_url)}" style="color:var(--tacai-primary);text-decoration:none;font-weight:800">{h(m.get('title', ''))}</a></td>
  <td>{h(tr(lang, f"type.{m.get('msg_type', '')}") if f"type.{m.get('msg_type', '')}" in TRANSLATIONS.get(lang, {}) else m.get('msg_type', ''))}</td>
  <td>{priority_badge(m.get('priority', 'normal'))}</td>
  <td>{status_badge(m.get('status', 'unread'))}</td>
  <td style="white-space:nowrap">{h(str(m.get('created_at', ''))[:16])}</td>
</tr>"""
        body += "</tbody></table></div>"

    # Pagination
    qs_parts = []
    if msg_type: qs_parts.append(f"type={quote(msg_type)}")
    if status: qs_parts.append(f"status={quote(status)}")
    if keyword: qs_parts.append(f"keyword={quote(keyword)}")
    if start_date: qs_parts.append(f"start_date={quote(start_date)}")
    if end_date: qs_parts.append(f"end_date={quote(end_date)}")
    qs = "&".join(qs_parts)
    page_base = f"{base_inbox}{'&' if '?' in base_inbox else '?'}{qs}"
    body += pagination_html(result["page"], result["total_pages"], page_base)

    # Record count
    if msg_type or status or keyword or start_date or end_date:
        body += f'<div class="helper-text">{h(tr(lang, "inbox.showing_filtered").format(shown=len(result["items"]), total=result["total"]))}</div>'
    else:
        body += f'<div class="helper-text">{h(tr(lang, "inbox.showing_all").format(total=result["total"]))}</div>'
    return body


def message_detail_html(user: dict[str, Any], lang: str, msg_id: str) -> str:
    m = get_message(msg_id)
    if not m:
        return f'<div class="message-strip message-error">Message not found: {h(msg_id)}</div>'
    bc = breadcrumb_html([(tr(lang, "nav.dashboard"), "/dashboard"), (tr(lang, "nav.inbox"), "/messages/inbox"), (m.get("title", tr(lang, "message.detail_title")), "")], lang)
    body = page_header(tr(lang, "message.detail_title"), m.get("title", ""), tr(lang, "message.detail_title"), bc)
    # Meta grid
    body += f"""<div class="card" style="margin-bottom:16px">
  <div class="sap-readonly-grid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:12px">
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.sender'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{h(m.get('sender_name', ''))}</div></div>
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.recipient'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{h(m.get('recipient_name', ''))}</div></div>
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.type'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{h(tr(lang, f"type.{m.get('msg_type', '')}") if f"type.{m.get('msg_type', '')}" in TRANSLATIONS.get(lang, {}) else m.get('msg_type', ''))}</div></div>
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.status'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{status_badge(m.get('status', 'unread'))}</div></div>
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.priority'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{priority_badge(m.get('priority', 'normal'))}</div></div>
    <div class="sap-readonly-field" style="background:#f8fafc;border:1px solid var(--tacai-border);border-radius:10px;padding:12px"><div class="label" style="color:var(--tacai-muted);font-size:.78rem;font-weight:850;text-transform:uppercase;margin-bottom:4px">{h(tr(lang, 'message.time'))}</div><div class="value" style="color:var(--tacai-sidebar);font-weight:850">{h(str(m.get('created_at', ''))[:19])}</div></div>
  </div>
</div>"""
    # Content
    body += f'<div class="card" style="margin-bottom:16px"><div style="line-height:1.7">{m.get("content", "")}</div></div>'
    # Linked workflow
    wf_id = str(m.get("workflow_id", ""))
    if wf_id:
        body += f'<div class="panel" style="margin-bottom:16px"><strong>{h(tr(lang, "message.related_workflow"))}:</strong> <a href="{h(url_with_lang(f"/workflows/{wf_id}", lang))}" style="color:var(--tacai-primary)">{h(wf_id)}</a></div>'
    # Training info
    ti = m.get("training_info")
    if ti and isinstance(ti, dict):
        body += f"""<div class="panel" style="margin-bottom:16px">
  <h3>Training Info</h3>
  <p>Name: {h(str(ti.get('training_name', '')))}</p>
  <p>Date: {h(str(ti.get('training_date', '')))}</p>
  <p>Location: {h(str(ti.get('location', '')))}</p>
  <p>Response: {h(str(ti.get('response', 'Not responded')))}</p>
</div>"""
    # Action buttons
    body += '<div class="actions" style="margin-top:16px">'
    # Back link
    body += f'<a class="button ghost" href="{h(url_with_lang("/messages/inbox", lang))}">{h(tr(lang, "message.back_to_inbox"))}</a>'
    # Mark as read
    if m.get("status") == "unread":
        body += f"""<form method="POST" action="{h(url_with_lang(f"/messages/{msg_id}/read", lang))}" style="display:inline">
  <button type="submit" class="button secondary">{h(tr(lang, 'message.mark_read'))}</button>
</form>"""
    # Confirm receipt
    if m.get("status") != "confirmed" and m.get("msg_type") in ("notification", "salary_notification", "system"):
        body += f"""<form method="POST" action="{h(url_with_lang(f"/messages/{msg_id}/confirm", lang))}" style="display:inline">
  <button type="submit" class="button success">{h(tr(lang, 'message.confirm_receipt'))}</button>
</form>"""
    # Training response
    if ti and isinstance(ti, dict) and ti.get("response") in ("", None):
        body += f"""<form method="POST" action="{h(url_with_lang(f"/messages/{msg_id}/training-response", lang))}" style="display:inline">
  <input type="hidden" name="response" value="confirmed">
  <button type="submit" class="button success">{h(tr(lang, 'message.confirm_training'))}</button>
</form>
<form method="POST" action="{h(url_with_lang(f"/messages/{msg_id}/training-response", lang))}" style="display:inline">
  <input type="hidden" name="response" value="declined">
  <button type="submit" class="button warning">{h(tr(lang, 'message.decline_training'))}</button>
</form>"""
    body += "</div>"
    return body


def search_html(user: dict[str, Any], lang: str, query_params: dict[str, list[str]]) -> str:
    user_id = str(user.get("user_id", ""))
    keyword = (query_params.get("keyword", [""])[0] or "").strip()
    start_date = (query_params.get("start", [""])[0] or "").strip()
    end_date = (query_params.get("end", [""])[0] or "").strip()

    bc = breadcrumb_html([(tr(lang, "nav.dashboard"), "/dashboard"), (tr(lang, "nav.inbox"), "/messages/inbox"), (tr(lang, "search.title"), "")], lang)
    body = page_header(tr(lang, "search.title"), "", tr(lang, "search.title"), bc)
    body += f"""<div class="panel" style="margin-bottom:16px">
  <form method="GET" action="{h(url_with_lang('/messages/search', lang))}" class="form-grid">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-field"><label>{h(tr(lang, 'search.keyword'))}</label><input type="text" name="keyword" value="{h(keyword)}"></div>
    <div class="form-field"><label>{h(tr(lang, 'search.start'))}</label><input type="date" name="start" value="{h(start_date)}"></div>
    <div class="form-field"><label>{h(tr(lang, 'search.end'))}</label><input type="date" name="end" value="{h(end_date)}"></div>
    <div class="form-field" style="display:flex;align-items:flex-end"><button type="submit">{h(tr(lang, 'search.btn'))}</button></div>
  </form>
</div>"""
    if keyword or start_date or end_date:
        all_msgs = [m for m in messages() if str(m.get("recipient_user_id", "")) == user_id]
        if keyword:
            kw = keyword.lower()
            all_msgs = [m for m in all_msgs if kw in str(m.get("title", "")).lower() or kw in str(m.get("content", "")).lower()]
        if start_date:
            all_msgs = [m for m in all_msgs if str(m.get("created_at", ""))[:10] >= start_date]
        if end_date:
            all_msgs = [m for m in all_msgs if str(m.get("created_at", ""))[:10] <= end_date]
        all_msgs.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
        if all_msgs:
            body += f'<h3>{h(tr(lang, "search.results"))} ({len(all_msgs)})</h3><div class="table-scroll"><table><thead><tr><th>{h(tr(lang, "inbox.col_title"))}</th><th>{h(tr(lang, "inbox.col_type"))}</th><th>{h(tr(lang, "inbox.col_date"))}</th></tr></thead><tbody>'
            for m in all_msgs[:50]:
                detail_url = url_with_lang(f"/messages/{m['msg_id']}", lang)
                body += f'<tr><td><a href="{h(detail_url)}" style="color:var(--tacai-primary);text-decoration:none">{h(m.get("title", ""))}</a></td><td>{h(m.get("msg_type", ""))}</td><td style="white-space:nowrap">{h(str(m.get("created_at", ""))[:16])}</td></tr>'
            body += "</tbody></table></div>"
        else:
            body += f'<div class="message-strip">{h(tr(lang, "search.no_results"))}</div>'
    return body


def audit_html(user: dict[str, Any], lang: str) -> str:
    rows = audit_logs()
    rows.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    bc = breadcrumb_html([(tr(lang, "nav.dashboard"), "/dashboard"), (tr(lang, "audit.title"), "")], lang)
    body = page_header(tr(lang, "audit.title"), "", tr(lang, "audit.title"), bc)
    if not rows:
        body += f'<div class="message-strip">{h(tr(lang, "common.no_records"))}</div>'
    else:
        body += '<div class="table-scroll"><table><thead><tr><th>ID</th><th>Action</th><th>Record</th><th>User</th><th>Timestamp</th><th>Notes</th></tr></thead><tbody>'
        for r in rows[:100]:
            body += f'<tr><td>{h(r.get("audit_id", ""))}</td><td>{h(r.get("action", ""))}</td><td>{h(r.get("record_type", ""))} / {h(r.get("record_id", ""))}</td><td>{h(r.get("user_name_snapshot", ""))}</td><td style="white-space:nowrap">{h(str(r.get("timestamp", ""))[:19])}</td><td>{h(str(r.get("notes", ""))[:80])}</td></tr>'
        body += "</tbody></table></div>"
        body += f'<div class="helper-text">{h(tr(lang, "common.records_total").format(total=min(len(rows), 100)))}</div>'
    return body


# ---------------------------------------------------------------------------
# JSON API helpers (Phase A)
# ---------------------------------------------------------------------------
def api_inbox(self: BaseHTTPRequestHandler, user: dict[str, Any]) -> None:
    parsed = urlparse(self.path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    user_id = str(user.get("user_id", ""))
    msg_type = (query.get("type", [""])[0] or "").strip()
    status = (query.get("status", [""])[0] or "").strip()
    keyword = (query.get("keyword", [""])[0] or "").strip()
    start_date = (query.get("start_date", [""])[0] or "").strip()
    end_date = (query.get("end_date", [""])[0] or "").strip()
    page = int((query.get("page", ["1"])[0] or "1"))
    limit = int((query.get("limit", ["20"])[0] or "20"))
    result = get_user_messages(user_id, msg_type, status, keyword, start_date, end_date, page, limit)
    self._send_json({"code": 200, "data": result})


def api_unread_count(self: BaseHTTPRequestHandler, user: dict[str, Any]) -> None:
    user_id = str(user.get("user_id", ""))
    count = sum(1 for m in messages() if str(m.get("recipient_user_id", "")) == user_id and m.get("status") == "unread")
    self._send_json({"code": 200, "data": {"unread_count": count}})


def api_message_detail(self: BaseHTTPRequestHandler, user: dict[str, Any], msg_id: str) -> None:
    m = get_message(msg_id)
    if not m:
        self._send_json({"code": 404, "error": "Message not found"}, 404)
        return
    user_id = str(user.get("user_id", ""))
    if str(m.get("recipient_user_id", "")) != user_id and not is_system_admin(user):
        self._send_json({"code": 403, "error": "Forbidden"}, 403)
        return
    self._send_json({"code": 200, "data": m})


# ---------------------------------------------------------------------------
# Handler class
# ---------------------------------------------------------------------------
class TacaiMsgHandler(BaseHTTPRequestHandler):
    server_version = "TACAIMsg/0.1"

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
            self._send_html(page("Forbidden", forbidden_html("Missing tacaimsg.access permission."), user, lang=getattr(self, "_response_lang", DEFAULT_LANG)), status=403)
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

    def request_lang(self, query: dict[str, list[str]] | None = None) -> str:
        if query is None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("lang", [""])[0] in SUPPORTED_LANGS:
            return query["lang"][0]
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(LANG_COOKIE)
        lang = morsel.value if morsel and morsel.value in SUPPORTED_LANGS else DEFAULT_LANG
        self._response_lang = lang
        return lang

    def _send_html(self, html_text: str, status: int = 200) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        lang = getattr(self, "_response_lang", DEFAULT_LANG)
        if lang in SUPPORTED_LANGS:
            self.send_header("Set-Cookie", f"{LANG_COOKIE}={lang}; Path=/; SameSite=Lax")
            self.send_header("Content-Language", lang)
        if self.flash_message():
            self.send_header("Set-Cookie", self.clear_flash_cookie_header())
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_json(self, data: Any, status: int = 200) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_text(self, text: str, status: int = 200) -> None:
        payload = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_csv(self, body: bytes, filename: str) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_redirect(self, location: str, flash: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if flash:
            self.send_header("Set-Cookie", self.flash_cookie_header(flash))
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_body_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_POST_BYTES:
            self._send_json({"error": "Request body too large"}, 413)
            raise ValueError("Request body too large")
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        try:
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            self._send_json({"error": "Invalid JSON"}, 400)
            raise

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_POST_BYTES:
            raise ValueError("Request body too large")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    # ---- Route dispatchers ----

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        lang = self.request_lang(query)
        flash = self.flash_message()
        try:
            # Health
            if path == "/health":
                self._send_text("OK")
                return
            # Static CSS
            if path == "/static/app.css":
                css_path = FRONTEND_DIR / "app.css"
                if css_path.exists():
                    payload = css_path.read_bytes()
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "text/css; charset=utf-8")
                    self.send_header("Content-Length", str(len(payload)))
                    self.send_header("Cache-Control", "public, max-age=3600")
                    self.end_headers()
                    self.wfile.write(payload)
                else:
                    self._send_text("/* CSS not found */", 404)
                return
            # Root
            if path in ("/", ""):
                self._send_redirect(url_with_lang("/dashboard", lang))
                return
            # Login redirect
            if path == "/login":
                self._send_redirect(self.user_admin_login_url("/dashboard"))
                return

            # === API routes ===
            if path == "/api/v1/messages/inbox":
                user = self.require_user("tacaimsg.view")
                if not user: return
                api_inbox(self, user)
                return
            if path == "/api/v1/messages/unread-count":
                user = self.require_user("tacaimsg.view")
                if not user: return
                api_unread_count(self, user)
                return
            if path.startswith("/api/v1/messages/search"):
                user = self.require_user("tacaimsg.view")
                if not user: return
                # Simple search API
                user_id = str(user.get("user_id", ""))
                keyword = (query.get("keyword", [""])[0] or "").strip()
                all_msgs = [m for m in messages() if str(m.get("recipient_user_id", "")) == user_id]
                if keyword:
                    kw = keyword.lower()
                    all_msgs = [m for m in all_msgs if kw in str(m.get("title", "")).lower() or kw in str(m.get("content", "")).lower()]
                all_msgs.sort(key=lambda m: str(m.get("created_at", "")), reverse=True)
                self._send_json({"code": 200, "data": {"total": len(all_msgs), "items": all_msgs[:50]}})
                return

            # API: message detail
            api_msg_match = re.match(r"^/api/v1/messages/(MSG-\d{6}-\d+)$", path)
            if api_msg_match:
                user = self.require_user("tacaimsg.view")
                if not user: return
                api_message_detail(self, user, api_msg_match.group(1))
                return

            # === HTML page routes ===
            if path == "/dashboard":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "dashboard.title"), dashboard_html(user, lang), user, "/dashboard", flash, lang))
                return
            if path == "/messages/inbox":
                user = self.require_user("tacaimsg.view")
                if not user: return
                self._send_html(page(tr(lang, "inbox.title"), inbox_html(user, lang, query), user, "/messages/inbox", flash, lang))
                return
            if path == "/messages/search":
                user = self.require_user("tacaimsg.view")
                if not user: return
                self._send_html(page(tr(lang, "search.title"), search_html(user, lang, query), user, "/messages/search", flash, lang))
                return
            if path.startswith("/messages/"):
                msg_match = re.match(r"^/messages/(MSG-\d{6}-\d+)$", path)
                if msg_match:
                    user = self.require_user("tacaimsg.view")
                    if not user: return
                    msg_id = msg_match.group(1)
                    m = get_message(msg_id)
                    if not m:
                        self._send_html(page("Not Found", '<div class="message-strip message-error">Message not found</div>', user, lang=lang), status=404)
                        return
                    # Auto-mark as read when viewing
                    if m.get("status") == "unread":
                        mark_read(msg_id, user)
                    self._send_html(page(tr(lang, "message.detail_title"), message_detail_html(user, lang, msg_id), user, "/messages/inbox", flash, lang))
                    return
            if path == "/audit-logs":
                user = self.require_user("tacaimsg.audit.view")
                if not user: return
                self._send_html(page(tr(lang, "audit.title"), audit_html(user, lang), user, "/audit-logs", flash, lang))
                return

            # === Phase B: Workflow routes ===
            # Import workflow module (lazy, cached)
            import importlib
            try:
                wf = importlib.import_module("workflow")
            except ImportError:
                try:
                    wf = importlib.import_module("backend.workflow")
                except ImportError:
                    wf = None

            if path == "/workflows":
                user = self.require_user("tacaimsg.workflow")
                if not user: return
                if wf:
                    body_html = wf.wf_list_html(user, lang, workflows(), workflow_steps(), query, url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "wf.list_title"), body_html, user, "/workflows", flash, lang))
                return
            if path == "/workflows/new":
                user = self.require_user("tacaimsg.workflow")
                if not user: return
                if wf:
                    body_html = wf.wf_new_html(user, lang, workflow_templates(), url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "wf.new_title"), body_html, user, "/workflows/new", flash, lang))
                return
            if path == "/workflows/export":
                user = self.require_user("tacaimsg.workflow")
                if not user: return
                if wf:
                    csv_data = wf.export_workflows_csv(workflows(), workflow_steps())
                    self._send_csv(csv_data, "workflows_export.csv")
                return
            if path == "/workflows/templates":
                user = self.require_user("tacaimsg.admin")
                if not user: return
                if wf:
                    body_html = wf.wft_list_html(user, lang, workflow_templates(), url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "wft.title"), body_html, user, "/workflows/templates", flash, lang))
                return
            if path == "/workflows/templates/new":
                user = self.require_user("tacaimsg.admin")
                if not user: return
                if wf:
                    body_html = wf.wft_form_html(user, lang, None, url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "wft.new_title"), body_html, user, "/workflows/templates/new", flash, lang))
                return
            wft_match = re.match(r"^/workflows/templates/(WFT-\d+)$", path)
            if wft_match:
                user = self.require_user("tacaimsg.admin")
                if not user: return
                if wf:
                    tpl = None
                    for t in workflow_templates():
                        if str(t.get("template_id","")) == wft_match.group(1):
                            tpl = t; break
                    if tpl:
                        body_html = wf.wft_form_html(user, lang, tpl, url_with_lang, h, tr)
                        self._send_html(page(tr(lang, "wft.edit_title"), body_html, user, path, flash, lang))
                return
            wf_match = re.match(r"^/workflows/(WF-\d{6}-\d+)$", path)
            if wf_match:
                user = self.require_user("tacaimsg.workflow")
                if not user: return
                if wf:
                    body_html = wf.wf_detail_html(user, lang, wf_match.group(1), workflows(), workflow_steps(), workflow_records(), url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "wf.detail_title"), body_html, user, path, flash, lang))
                return
            if path == "/delegations":
                user = self.require_user("tacaimsg.delegate")
                if not user: return
                if wf:
                    body_html = wf.delegations_html(user, lang, delegations(), url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "del.title"), body_html, user, "/delegations", flash, lang))
                return
            if path == "/delegations/new":
                user = self.require_user("tacaimsg.delegate")
                if not user: return
                if wf:
                    body_html = wf.delegation_new_html(user, lang, url_with_lang, h, tr)
                    self._send_html(page(tr(lang, "del.new_title"), body_html, user, "/delegations/new", flash, lang))
                return

            # Phase C placeholder
            if path.startswith("/notifications"):
                user = self.require_user()
                if not user: return
                self._send_html(page("Coming Soon", '<div class="message-strip"><strong>Phase C</strong> — Notifications coming next.</div>', user, path, flash, lang), status=501)
                return

            self._send_html(page("Not Found", f'<div class="message-strip message-error"><h3>404</h3><p>Page not found: {h(path)}</p></div>', lang=lang), status=404)
        except Exception as exc:
            user = self.current_user()
            self._send_html(page("Error", f'<div class="message-strip message-error"><h3>Error</h3><p>{h(str(exc))}</p></div>', user, lang=lang), status=500)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        lang = self.request_lang(query)
        try:
            # Message actions
            if path.startswith("/messages/") and path.endswith("/read"):
                msg_match = re.match(r"^/messages/(MSG-\d{6}-\d+)/read$", path)
                if msg_match:
                    user = self.require_user("tacaimsg.view")
                    if not user: return
                    mark_read(msg_match.group(1), user)
                    self._send_redirect(url_with_lang(f"/messages/{msg_match.group(1)}", lang), tr(lang, "msg.read_ok"))
                    return
            if path.startswith("/messages/") and path.endswith("/confirm"):
                msg_match = re.match(r"^/messages/(MSG-\d{6}-\d+)/confirm$", path)
                if msg_match:
                    user = self.require_user("tacaimsg.view")
                    if not user: return
                    confirm_receipt(msg_match.group(1), user)
                    self._send_redirect(url_with_lang(f"/messages/{msg_match.group(1)}", lang), tr(lang, "msg.confirmed_ok"))
                    return
            if path.startswith("/messages/") and path.endswith("/training-response"):
                msg_match = re.match(r"^/messages/(MSG-\d{6}-\d+)/training-response$", path)
                if msg_match:
                    user = self.require_user("tacaimsg.view")
                    if not user: return
                    form = self._read_form()
                    response = (form.get("response", ["confirmed"])[0] or "confirmed").strip()
                    training_response(msg_match.group(1), response, user)
                    flash_msg = tr(lang, "msg.training_confirmed") if response == "confirmed" else tr(lang, "msg.training_declined")
                    self._send_redirect(url_with_lang(f"/messages/{msg_match.group(1)}", lang), flash_msg)
                    return
            if path == "/messages/inbox/mark-read":
                user = self.require_user("tacaimsg.view")
                if not user: return
                form = self._read_form()
                msg_type = (form.get("type", [""])[0] or "").strip()
                user_id = str(user.get("user_id", ""))
                count = mark_all_read(user_id, msg_type, user)
                self._send_redirect(url_with_lang("/messages/inbox", lang), tr(lang, "msg.read_all_ok"))
                return

            # === Internal API routes (token-authenticated, called by other modules) ===
            if path == "/api/internal/messages/send-batch":
                body = self._read_body_json()
                # Validate internal token
                token = self.headers.get("X-TACAI-Internal-Token", "")
                if token != TACAIMSG_INTERNAL_TOKEN:
                    self._send_json({"code": 403, "error": "Forbidden: invalid internal token"}, 403)
                    return
                messages_payload = body.get("messages")
                if not isinstance(messages_payload, list) or not messages_payload:
                    self._send_json({"code": 400, "error": "Missing or empty 'messages' array"}, 400)
                    return
                sender_user_id = str(body.get("sender_user_id", "SYSTEM")).strip()
                sender_name = str(body.get("sender_name", "TACAI Payroll System")).strip()
                result = send_message_batch(messages_payload, sender_user_id, sender_name)
                self._send_json({"code": 200, "data": result})
                return

            if path == "/api/internal/users/resolve-employees":
                # Resolve employee_ids to user accounts
                token = self.headers.get("X-TACAI-Internal-Token", "")
                if token != TACAIMSG_INTERNAL_TOKEN:
                    self._send_json({"code": 403, "error": "Forbidden: invalid internal token"}, 403)
                    return
                body = self._read_body_json()
                employee_ids = body.get("employee_ids")
                if not isinstance(employee_ids, list):
                    self._send_json({"code": 400, "error": "Missing or invalid 'employee_ids' array"}, 400)
                    return
                mapping = resolve_employee_to_users(employee_ids)
                # Convert user objects to safe summaries
                result_mapping = {}
                for eid, user in mapping.items():
                    if user:
                        result_mapping[eid] = {
                            "user_id": user.get("user_id", ""),
                            "username": user.get("username", ""),
                            "display_name": user.get("display_name", ""),
                            "email": user.get("email", ""),
                            "entity_id": user.get("entity_id", ""),
                            "has_account": True,
                        }
                    else:
                        result_mapping[eid] = {"has_account": False}
                self._send_json({"code": 200, "data": {"mapping": result_mapping}})
                return

            # === API POST routes ===
            # Mark read (API)
            api_read_match = re.match(r"^/api/v1/messages/(MSG-\d{6}-\d+)/read$", path)
            if api_read_match:
                user = self.require_user("tacaimsg.view")
                if not user: return
                mark_read(api_read_match.group(1), user)
                self._send_json({"code": 200, "message": tr(lang, "msg.read_ok")})
                return
            if path == "/api/v1/messages/read-all":
                user = self.require_user("tacaimsg.view")
                if not user: return
                body = self._read_body_json()
                msg_type = str(body.get("type", "")).strip()
                user_id = str(user.get("user_id", ""))
                count = mark_all_read(user_id, msg_type, user)
                self._send_json({"code": 200, "updated_count": count})
                return
            # Confirm receipt (API)
            api_confirm_match = re.match(r"^/api/v1/messages/(MSG-\d{6}-\d+)/confirm$", path)
            if api_confirm_match:
                user = self.require_user("tacaimsg.view")
                if not user: return
                confirm_receipt(api_confirm_match.group(1), user)
                self._send_json({"code": 200, "message": tr(lang, "msg.confirmed_ok")})
                return
            # Training response (API)
            api_tr_match = re.match(r"^/api/v1/messages/(MSG-\d{6}-\d+)/training-response$", path)
            if api_tr_match:
                user = self.require_user("tacaimsg.view")
                if not user: return
                body = self._read_body_json()
                response = str(body.get("response", "confirmed")).strip()
                training_response(api_tr_match.group(1), response, user)
                self._send_json({"code": 200, "message": tr(lang, "msg.training_confirmed") if response == "confirmed" else tr(lang, "msg.training_declined")})
                return

            # === Phase B: Workflow POST routes ===
            import importlib as _imp
            try:
                wf = _imp.import_module("workflow")
            except ImportError:
                try:
                    wf = _imp.import_module("backend.workflow")
                except ImportError:
                    wf = None

            # Create workflow
            if path == "/workflows/new":
                user = self.require_user("tacaimsg.workflow")
                if not user: return
                form = self._read_form()
                template_id = (form.get("template_id", [""])[0] or "").strip()
                biz_id = (form.get("biz_id", [""])[0] or "").strip()
                title = (form.get("title", [""])[0] or "").strip()
                try:
                    amount = float((form.get("amount", ["0"])[0] or "0"))
                except ValueError:
                    amount = 0
                if not biz_id:
                    self._send_redirect(url_with_lang("/workflows/new", lang), "Business ID is required")
                    return
                # Find template to get biz_type
                tpl = None
                for t in workflow_templates():
                    if str(t.get("template_id", "")) == template_id:
                        tpl = t
                        break
                if not tpl:
                    tpls = workflow_templates()
                    if tpls:
                        tpl = tpls[0]
                if not tpl:
                    self._send_redirect(url_with_lang("/workflows/new", lang), "No active template found")
                    return
                biz_type = str(tpl.get("biz_type", ""))
                # Create workflow using the full creation logic
                user_id = str(user.get("user_id", ""))
                user_name = user_display_name(user)
                entity_id = user_entity_id(user)
                try:
                    # Helper to append new steps to existing
                    def _append_steps(new_steps):
                        existing = workflow_steps()
                        existing.extend(new_steps)
                        save_workflow_steps(existing)
                    result = wf.create_workflow_full(
                        biz_type=biz_type,
                        biz_id=biz_id,
                        initiator_user_id=user_id,
                        initiator_name=user_name,
                        title=title,
                        biz_amount=amount,
                        entity_id=entity_id,
                        template_id=template_id,
                        load_templates_fn=workflow_templates,
                        load_wf_fn=workflows,
                        save_wf_fn=save_workflows,
                        save_steps_fn=_append_steps,
                        send_msg_fn=send_message,
                    )
                except Exception as exc:
                    self._send_redirect(url_with_lang("/workflows/new", lang), f"Error: {exc}")
                    return
                self._send_redirect(url_with_lang(f"/workflows/{result['wf_id']}", lang), tr(lang, "wf.created_ok"))
                return

            # Workflow action (approve/reject/transfer)
            wf_action_match = re.match(r"^/workflows/(WF-\d{6}-\d+)/action$", path)
            if wf_action_match:
                user = self.require_user("tacaimsg.approve")
                if not user: return
                form = self._read_form()
                action = (form.get("action", [""])[0] or "").strip()
                comment = (form.get("comment", [""])[0] or "").strip()
                transfer_to = (form.get("transfer_to", [""])[0] or "").strip()
                user_id = str(user.get("user_id", ""))
                user_name = user_display_name(user)
                wf_id = wf_action_match.group(1)
                try:
                    result = wf.execute_workflow_action(
                        wf_id=wf_id,
                        action=action,
                        operator_user_id=user_id,
                        operator_name=user_name,
                        comment=comment,
                        transfer_to_user_id=transfer_to,
                        get_workflows_fn=workflows,
                        save_workflows_fn=save_workflows,
                        get_steps_fn=workflow_steps,
                        save_steps_fn=save_workflow_steps,
                        get_records_fn=workflow_records,
                        save_records_fn=save_workflow_records,
                        send_msg_fn=send_message,
                        now_iso_fn=now_iso,
                    )
                    flash_key = f"wf.{action}ed_ok" if action in ("approve", "reject", "transfer") else "wf.batch_ok"
                    self._send_redirect(url_with_lang(f"/workflows/{wf_id}", lang), tr(lang, flash_key))
                except Exception as exc:
                    self._send_redirect(url_with_lang(f"/workflows/{wf_id}", lang), f"Error: {exc}")
                return

            # Save template (new/create)
            if path in ("/workflows/templates/new",) or path.startswith("/workflows/templates/WFT-"):
                user = self.require_user("tacaimsg.admin")
                if not user: return
                form = self._read_form()
                template_id = str(form.get("template_id", [""])[0] or "").strip()
                name = str(form.get("template_name", [""])[0] or "").strip()
                biz_type = str(form.get("biz_type", [""])[0] or "").strip()
                status = str(form.get("status", ["active"])[0] or "active").strip()
                if not name or not biz_type:
                    self._send_redirect(url_with_lang(path, lang), "Name and biz_type required")
                    return
                # Parse steps from form
                steps = []
                i = 0
                while f"step_name_{i}" in form:
                    sname = str(form.get(f"step_name_{i}", [""])[0] or "").strip()
                    srole = str(form.get(f"step_role_{i}", [""])[0] or "").strip()
                    tout = int(form.get(f"step_timeout_{i}", ["48"])[0] or "48")
                    i += 1
                    if sname and srole:
                        steps.append({"step_number": i, "step_name": sname, "approver_role": srole, "timeout_hours": tout})
                tpl_rows = workflow_templates()
                now = now_iso()
                if template_id:
                    # Update existing
                    for t in tpl_rows:
                        if str(t.get("template_id", "")) == template_id:
                            t["template_name"] = name
                            t["biz_type"] = biz_type
                            t["status"] = status
                            t["steps"] = steps
                            t["updated_at"] = now
                            break
                else:
                    template_id = next_simple_id(tpl_rows, "template_id", "WFT")
                    tpl_rows.append({
                        "template_id": template_id, "template_name": name, "biz_type": biz_type,
                        "status": status, "steps": steps, "created_by": str(user.get("user_id", "")),
                        "created_at": now, "updated_at": now,
                    })
                save_workflow_templates(tpl_rows)
                append_audit_log(template_id, "workflow_template", "saved", {}, {"name": name, "biz_type": biz_type, "steps": len(steps)}, user, self)
                self._send_redirect(url_with_lang("/workflows/templates", lang), tr(lang, "wft.saved_ok"))
                return

            # Create delegation
            if path == "/delegations/new":
                user = self.require_user("tacaimsg.delegate")
                if not user: return
                form = self._read_form()
                delegate_id = str(form.get("delegate_id", [""])[0] or "").strip()
                start_date = str(form.get("start_date", [""])[0] or "").strip()
                end_date = str(form.get("end_date", [""])[0] or "").strip()
                reason = str(form.get("reason", [""])[0] or "").strip()
                del_rows = delegations()
                del_id = next_simple_id(del_rows, "delegation_id", "DEL")
                now = now_iso()
                del_rows.append({
                    "delegation_id": del_id,
                    "delegator_user_id": str(user.get("user_id", "")),
                    "delegator_name": user_display_name(user),
                    "delegate_user_id": delegate_id,
                    "delegate_name": resolve_user_name(delegate_id),
                    "biz_types": [],
                    "start_date": start_date, "end_date": end_date,
                    "status": "active", "reason": reason,
                    "created_by": str(user.get("user_id", "")),
                    "created_at": now, "updated_at": now,
                })
                save_delegations(del_rows)
                append_audit_log(del_id, "delegation", "created", {}, {"delegate_id": delegate_id}, user, self)
                self._send_redirect(url_with_lang("/delegations", lang), tr(lang, "del.created_ok"))
                return

            # Cancel delegation
            del_cancel_match = re.match(r"^/delegations/(DEL-\d{6}-\d+)/cancel$", path)
            if del_cancel_match:
                user = self.require_user("tacaimsg.delegate")
                if not user: return
                del_id = del_cancel_match.group(1)
                del_rows = delegations()
                for d in del_rows:
                    if str(d.get("delegation_id", "")) == del_id:
                        d["status"] = "cancelled"
                        d["updated_at"] = now_iso()
                        break
                save_delegations(del_rows)
                append_audit_log(del_id, "delegation", "cancelled", {}, {}, user, self)
                self._send_redirect(url_with_lang("/delegations", lang), tr(lang, "del.cancelled_ok"))
                return

            # Fallback for unimplemented routes
            self._send_json({"error": "Route not found"}, 404)
        except ValueError:
            pass  # Error already sent in _read_body_json
        except Exception as exc:
            user = self.current_user()
            self._send_html(page("Error", f'<div class="message-strip message-error"><h3>Error</h3><p>{h(str(exc))}</p></div>', user, lang=lang), status=500)

    def do_PUT(self) -> None:
        self.do_POST()

    def log_message(self, fmt: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {fmt % args}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Storage initialization
# ---------------------------------------------------------------------------
def ensure_storage() -> None:
    """Create all JSON database files if they don't exist."""
    paths = [
        MESSAGES_PATH, WORKFLOWS_PATH, WORKFLOW_STEPS_PATH,
        WORKFLOW_RECORDS_PATH, WORKFLOW_TEMPLATES_PATH,
        DELEGATIONS_PATH, NOTIFICATION_TEMPLATES_PATH, AUDIT_LOGS_PATH,
    ]
    for p in paths:
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("[]", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Run TACAI Message Center local MVP app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    ensure_storage()
    # Run cleanup on startup
    removed = cleanup_expired_messages()
    if removed:
        print(f"[tacaimsg] Cleaned up {removed} expired messages on startup")
    server = ThreadingHTTPServer((args.host, args.port), TacaiMsgHandler)
    print(f"TACAI Message Center running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TACAI Message Center")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
