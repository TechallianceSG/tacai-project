#!/usr/bin/env python3
"""TACAI Employee Self-Service — Leave Management local MVP.

Zero-dependency Python standard-library web app for:
  - Leave request submission (事假/病假/调休)
  - Two-step approval: Supervisor → HR
  - Auto-escalation: supervisor 2-day skip, HR 3-day auto-approve
  - Integration with User_admin, EmployeeAdmin, tacaimsg

Data stored as UTF-8 JSON arrays under ../database.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
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
LEAVE_REQUESTS_PATH = DATABASE_DIR / "leave_requests.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"

PROJECT_ROOT = ROOT_DIR.parents[2]  # tacai-project/
USER_ADMIN_USERS_PATH = PROJECT_ROOT / "TACAI-Core" / "User_admin" / "database" / "users.json"
EMPLOYEEADMIN_EMPLOYEES_PATH = PROJECT_ROOT / "TAC-employeeadmin" / "database" / "employees.json"
MASTERDATA_ENTITIES_PATH = PROJECT_ROOT / "TACAI-Core" / "masterdata" / "database" / "entities.json"

MODULE_NAME = "tacai-selfservice"
DEFAULT_PORT = 8018
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
FLASH_COOKIE = "selfservice_flash"
LANG_COOKIE = "selfservice_lang"
SUPPORTED_LANGS = {"zh", "ja", "en"}
DEFAULT_LANG = "zh"
REQUIRED_MODULE_PERMISSION = "selfservice.access"
MAX_POST_BYTES = 2 * 1024 * 1024
JSON_WRITE_LOCK = threading.RLock()

TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAIMSG_INTERNAL_TOKEN = os.environ.get("TACAIMSG_INTERNAL_TOKEN", "tacai-internal-token").strip()

# Timeout constants
SUPERVISOR_TIMEOUT_HOURS = 48   # 2 days
HR_TIMEOUT_HOURS = 72           # 3 days


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


APP_BASE_URL = public_base_url("SELFSERVICE_PUBLIC_BASE_URL", DEFAULT_PORT)
PORTAL_BASE_URL = public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")
TACAIMSG_INTERNAL_BASE_URL = os.environ.get("TACAIMSG_INTERNAL_BASE_URL", internal_base_url(8012)).strip().rstrip("/")
EMPLOYEEADMIN_INTERNAL_BASE_URL = os.environ.get("EMPLOYEEADMIN_INTERNAL_BASE_URL", internal_base_url(8004)).strip().rstrip("/")

LEAVE_TYPES = ["personal_leave", "sick_leave", "compensatory_leave"]
LEAVE_STATUSES = ["draft", "submitted", "supervisor_pending", "supervisor_skipped",
                  "hr_pending", "hr_auto_approved", "approved", "rejected", "cancelled"]
ACTIVE_STATUSES = {"submitted", "supervisor_pending", "hr_pending"}
FINAL_STATUSES = {"approved", "hr_auto_approved", "rejected", "cancelled"}

# ---------------------------------------------------------------------------
# i18n Translations
# ---------------------------------------------------------------------------
TRANSLATIONS = {
    "zh": {
        "app.title": "TACAI 员工自助",
        "app.subtitle": "请假申请、审批管理",
        "nav.portal": "返回 Portal",
        "nav.dashboard": "仪表盘",
        "nav.new_leave": "新建请假",
        "nav.my_leaves": "我的请假",
        "nav.pending_approvals": "待审批",
        "nav.all_leaves": "全部请假",
        "nav.audit": "审计日志",
        "language.label": "语言",
        "current_user": "当前用户",
        "dashboard.title": "请假管理仪表盘",
        "dashboard.my_pending": "我的待审批",
        "dashboard.to_approve": "待我审批",
        "dashboard.approved_month": "本月已批准",
        "dashboard.quick_new": "新建请假申请",
        "dashboard.quick_my": "查看我的请假",
        "dashboard.quick_approve": "查看待审批",
        "leave.new_title": "新建请假申请",
        "leave.edit_title": "编辑请假申请",
        "leave.detail_title": "请假详情",
        "leave.list_title": "请假列表",
        "leave.type": "请假类型",
        "leave.start_date": "开始日期",
        "leave.end_date": "结束日期",
        "leave.days": "天数",
        "leave.reason": "请假原因",
        "leave.status": "状态",
        "leave.entity": "法人实体",
        "leave.department": "部门",
        "leave.applicant": "申请人",
        "leave.supervisor": "主管",
        "leave.hr": "HR",
        "leave.submitted_at": "提交时间",
        "leave.approved_at": "批准时间",
        "leave.no_records": "暂无记录",
        "type.personal_leave": "事假",
        "type.sick_leave": "病假",
        "type.compensatory_leave": "调休",
        "status.draft": "草稿",
        "status.submitted": "已提交",
        "status.supervisor_pending": "主管审批中",
        "status.supervisor_skipped": "主管超时跳过",
        "status.hr_pending": "HR审批中",
        "status.hr_auto_approved": "HR超时自动批准",
        "status.approved": "已批准",
        "status.rejected": "已拒绝",
        "status.cancelled": "已取消",
        "action.submit": "提交申请",
        "action.save_draft": "保存草稿",
        "action.approve": "批准",
        "action.reject": "拒绝",
        "action.cancel": "取消申请",
        "action.back": "返回",
        "action.view_detail": "查看详情",
        "common.save": "保存",
        "common.cancel": "取消",
        "common.confirm": "确认",
        "common.actions": "操作",
        "common.status": "状态",
        "common.no_records": "暂无记录",
        "common.records_total": "共 {total} 条记录",
        "msg.leave_created": "请假申请已创建",
        "msg.leave_submitted": "请假申请已提交，等待审批",
        "msg.leave_approved": "请假申请已批准",
        "msg.leave_rejected": "请假申请已拒绝",
        "msg.leave_cancelled": "请假申请已取消",
        "msg.supervisor_skipped": "主管审批超时(48h)，自动跳过",
        "msg.hr_auto_approved": "HR审批超时(72h)，自动批准",
        "msg.no_supervisor": "未找到主管信息，将直接提交HR审批",
        "msg.confirm_submit": "确认提交请假申请？提交后无法修改。",
        "msg.confirm_approve": "确认批准此请假申请？",
        "msg.confirm_reject": "确认拒绝此请假申请？",
        "msg.confirm_cancel": "确认取消此请假申请？",
        "label.days_count": "{days} 天",
        "label.half_day": "半天",
        "label.am": "上午",
        "label.pm": "下午",
        "timeout.supervisor_info": "主管审批超时：提交后48小时无操作自动跳过",
        "timeout.hr_info": "HR审批超时：到达HR后72小时无操作自动批准",
    },
    "ja": {
        "app.title": "TACAI 従業員セルフサービス",
        "app.subtitle": "休暇申請・承認管理",
        "nav.portal": "Portalへ戻る",
        "nav.dashboard": "ダッシュボード",
        "nav.new_leave": "新規休暇申請",
        "nav.my_leaves": "自分の休暇",
        "nav.pending_approvals": "承認待ち",
        "nav.all_leaves": "すべての休暇",
        "nav.audit": "監査ログ",
        "language.label": "言語",
        "current_user": "現在のユーザー",
        "dashboard.title": "休暇管理ダッシュボード",
        "dashboard.my_pending": "自分の承認待ち",
        "dashboard.to_approve": "承認待ち",
        "dashboard.approved_month": "今月の承認済み",
        "dashboard.quick_new": "新規休暇申請",
        "dashboard.quick_my": "自分の休暇を見る",
        "dashboard.quick_approve": "承認待ちを見る",
        "leave.new_title": "新規休暇申請",
        "leave.edit_title": "休暇申請を編集",
        "leave.detail_title": "休暇申請詳細",
        "leave.list_title": "休暇申請一覧",
        "leave.type": "休暇種類",
        "leave.start_date": "開始日",
        "leave.end_date": "終了日",
        "leave.days": "日数",
        "leave.reason": "理由",
        "leave.status": "ステータス",
        "leave.entity": "法人",
        "leave.department": "部署",
        "leave.applicant": "申請者",
        "leave.supervisor": "上司",
        "leave.hr": "HR",
        "leave.submitted_at": "申請日時",
        "leave.approved_at": "承認日時",
        "leave.no_records": "記録なし",
        "type.personal_leave": "私用休暇",
        "type.sick_leave": "病気休暇",
        "type.compensatory_leave": "振替休暇",
        "status.draft": "下書き",
        "status.submitted": "提出済み",
        "status.supervisor_pending": "上司承認待ち",
        "status.supervisor_skipped": "上司タイムアウト(スキップ)",
        "status.hr_pending": "HR承認待ち",
        "status.hr_auto_approved": "HRタイムアウト(自動承認)",
        "status.approved": "承認済み",
        "status.rejected": "却下",
        "status.cancelled": "キャンセル",
        "action.submit": "申請を提出",
        "action.save_draft": "下書き保存",
        "action.approve": "承認",
        "action.reject": "却下",
        "action.cancel": "申請取消",
        "action.back": "戻る",
        "action.view_detail": "詳細を見る",
        "common.save": "保存",
        "common.cancel": "取消",
        "common.confirm": "確認",
        "common.actions": "操作",
        "common.status": "ステータス",
        "common.no_records": "記録なし",
        "common.records_total": "合計 {total} 件",
        "msg.leave_created": "休暇申請を作成しました",
        "msg.leave_submitted": "休暇申請を提出しました。承認待ちです。",
        "msg.leave_approved": "休暇申請が承認されました",
        "msg.leave_rejected": "休暇申請が却下されました",
        "msg.leave_cancelled": "休暇申請をキャンセルしました",
        "msg.supervisor_skipped": "上司承認タイムアウト(48h)、自動スキップ",
        "msg.hr_auto_approved": "HR承認タイムアウト(72h)、自動承認",
        "msg.no_supervisor": "上司情報が見つかりません。HR承認に直接進みます。",
        "msg.confirm_submit": "休暇申請を提出しますか？提出後は修正できません。",
        "msg.confirm_approve": "この休暇申請を承認しますか？",
        "msg.confirm_reject": "この休暇申請を却下しますか？",
        "msg.confirm_cancel": "この休暇申請をキャンセルしますか？",
        "label.days_count": "{days} 日",
        "label.half_day": "半日",
        "label.am": "午前",
        "label.pm": "午後",
        "timeout.supervisor_info": "上司承認タイムアウト：提出後48時間で自動スキップ",
        "timeout.hr_info": "HR承認タイムアウト：HR到着後72時間で自動承認",
    },
    "en": {
        "app.title": "TACAI Employee Self-Service",
        "app.subtitle": "Leave Request & Approval Management",
        "nav.portal": "Back to Portal",
        "nav.dashboard": "Dashboard",
        "nav.new_leave": "New Leave",
        "nav.my_leaves": "My Leaves",
        "nav.pending_approvals": "Pending Approvals",
        "nav.all_leaves": "All Leaves",
        "nav.audit": "Audit Logs",
        "language.label": "Language",
        "current_user": "Current User",
        "dashboard.title": "Leave Management Dashboard",
        "dashboard.my_pending": "My Pending",
        "dashboard.to_approve": "To Approve",
        "dashboard.approved_month": "Approved This Month",
        "dashboard.quick_new": "New Leave Request",
        "dashboard.quick_my": "View My Leaves",
        "dashboard.quick_approve": "View Approvals",
        "leave.new_title": "New Leave Request",
        "leave.edit_title": "Edit Leave Request",
        "leave.detail_title": "Leave Request Detail",
        "leave.list_title": "Leave Request List",
        "leave.type": "Leave Type",
        "leave.start_date": "Start Date",
        "leave.end_date": "End Date",
        "leave.days": "Days",
        "leave.reason": "Reason",
        "leave.status": "Status",
        "leave.entity": "Entity",
        "leave.department": "Department",
        "leave.applicant": "Applicant",
        "leave.supervisor": "Supervisor",
        "leave.hr": "HR",
        "leave.submitted_at": "Submitted At",
        "leave.approved_at": "Approved At",
        "leave.no_records": "No records",
        "type.personal_leave": "Personal Leave",
        "type.sick_leave": "Sick Leave",
        "type.compensatory_leave": "Compensatory Leave",
        "status.draft": "Draft",
        "status.submitted": "Submitted",
        "status.supervisor_pending": "Supervisor Pending",
        "status.supervisor_skipped": "Supervisor Skipped",
        "status.hr_pending": "HR Pending",
        "status.hr_auto_approved": "HR Auto-Approved",
        "status.approved": "Approved",
        "status.rejected": "Rejected",
        "status.cancelled": "Cancelled",
        "action.submit": "Submit Request",
        "action.save_draft": "Save Draft",
        "action.approve": "Approve",
        "action.reject": "Reject",
        "action.cancel": "Cancel Request",
        "action.back": "Back",
        "action.view_detail": "View Detail",
        "common.save": "Save",
        "common.cancel": "Cancel",
        "common.confirm": "Confirm",
        "common.actions": "Actions",
        "common.status": "Status",
        "common.no_records": "No records",
        "common.records_total": "{total} record(s) total",
        "msg.leave_created": "Leave request created",
        "msg.leave_submitted": "Leave request submitted, pending approval",
        "msg.leave_approved": "Leave request approved",
        "msg.leave_rejected": "Leave request rejected",
        "msg.leave_cancelled": "Leave request cancelled",
        "msg.supervisor_skipped": "Supervisor timeout (48h), auto-skipped",
        "msg.hr_auto_approved": "HR timeout (72h), auto-approved",
        "msg.no_supervisor": "No supervisor found, will proceed to HR directly",
        "msg.confirm_submit": "Confirm submit leave request? Cannot be modified after submission.",
        "msg.confirm_approve": "Confirm approve this leave request?",
        "msg.confirm_reject": "Confirm reject this leave request?",
        "msg.confirm_cancel": "Confirm cancel this leave request?",
        "label.days_count": "{days} day(s)",
        "label.half_day": "Half Day",
        "label.am": "AM",
        "label.pm": "PM",
        "timeout.supervisor_info": "Supervisor timeout: Auto-skip after 48h without action",
        "timeout.hr_info": "HR timeout: Auto-approve after 72h without action",
    },
}


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
    for key, value in TRANSLATIONS.get(lang, TRANSLATIONS[DEFAULT_LANG]).items():
        body = body.replace(f"%%{key}%%", value)
    return body


def status_badge(status: str) -> str:
    normalized = (status or "unknown").lower()
    return f'<span class="status-badge status-{h(normalized)}">{h(status or "unknown")}</span>'


def leave_type_badge(leave_type: str, lang: str) -> str:
    label = tr(lang, f"type.{leave_type}") if f"type.{leave_type}" in TRANSLATIONS.get(lang, {}) else leave_type
    return f'<span class="status-badge status-{h(leave_type)}">{h(label)}</span>'


def status_label(status: str, lang: str) -> str:
    key = f"status.{status}"
    return tr(lang, key) if key in TRANSLATIONS.get(lang, {}) else status


def clean_text(value: object) -> str:
    return str(value or "").strip()


def parse_date(value: object):
    text = clean_text(value)
    if not text:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def compute_leave_days(start_str: str, end_str: str) -> float:
    """Calculate leave days between two dates (inclusive)."""
    start = parse_date(start_str)
    end = parse_date(end_str)
    if not start or not end:
        return 0
    if end < start:
        return 0
    return (end - start).days + 1.0


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


# ---------------------------------------------------------------------------
# User / Session / Permission (adapted from tacaimsg)
# ---------------------------------------------------------------------------
def user_display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return "anonymous"
    for key in ["display_name", "username", "email", "user_id"]:
        value = str(user.get(key, "")).strip()
        if value:
            return value
    return "unknown_user"


def has_permission(user: dict[str, Any] | None, permission_key: str) -> bool:
    if not user:
        return False
    roles = set(user.get("roles", []))
    permissions = set(user.get("permissions", []))
    return "system_admin" in roles or "*" in permissions or permission_key in permissions


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
# Employee data access
# ---------------------------------------------------------------------------
def read_users() -> list[dict[str, Any]]:
    return load_json_array(USER_ADMIN_USERS_PATH)


def read_employees() -> list[dict[str, Any]]:
    return load_json_array(EMPLOYEEADMIN_EMPLOYEES_PATH)


def read_entities() -> list[dict[str, Any]]:
    return load_json_array(MASTERDATA_ENTITIES_PATH)


def get_employee_by_user_id(user_id: str) -> dict[str, Any] | None:
    """Find employee record linked to a user account."""
    # First find the user to get linked_employee_id
    users = read_users()
    linked_employee_id = ""
    for u in users:
        if str(u.get("user_id", "")) == str(user_id):
            linked_employee_id = str(u.get("linked_employee_id", "")).strip()
            break

    if linked_employee_id:
        for emp in read_employees():
            if str(emp.get("employee_id", "")) == linked_employee_id:
                return emp

    # Fallback: try matching user_id directly
    for emp in read_employees():
        if str(emp.get("linked_user_id", "")) == str(user_id):
            return emp
    return None


def get_employee_info(user: dict[str, Any]) -> dict[str, Any]:
    """Extract employee info (entity, department, supervisor) from user + employeeadmin."""
    user_id = str(user.get("user_id", ""))
    emp = get_employee_by_user_id(user_id)

    employment = emp.get("employment") if emp and isinstance(emp.get("employment"), dict) else {}
    profile = emp.get("profile") if emp and isinstance(emp.get("profile"), dict) else {}

    entity_id = clean_text(emp.get("entity_id") or employment.get("entity_id") or user.get("entity_id", ""))
    department = clean_text(emp.get("department") or employment.get("department", ""))
    employee_id = clean_text(emp.get("employee_id", ""))
    employee_name = clean_text(
        emp.get("display_name")
        or profile.get("name", {}).get("display_name", "")
        or user_display_name(user)
    )

    # Find supervisor
    supervisor_id = clean_text(emp.get("supervisor_id") or employment.get("reports_to", ""))
    supervisor_name = ""
    supervisor_user_id = ""
    supervisor_has_account = False

    if supervisor_id:
        # Get supervisor name from employeeadmin
        for e in read_employees():
            if str(e.get("employee_id", "")) == supervisor_id:
                supervisor_name = clean_text(e.get("display_name") or e.get("employee_name", ""))
                break
        # Check if supervisor has a User_admin account
        for u in read_users():
            if str(u.get("linked_employee_id", "")) == supervisor_id:
                supervisor_user_id = str(u.get("user_id", ""))
                supervisor_has_account = True
                break

    # Resolve entity name
    entity_name = ""
    entity_code = ""
    for ent in read_entities():
        if str(ent.get("entity_id", "")) == entity_id:
            entity_name = clean_text(ent.get("entity_name_en") or ent.get("entity_name_local", ""))
            entity_code = clean_text(ent.get("entity_code", ""))
            break

    return {
        "employee_id": employee_id,
        "employee_name": employee_name,
        "entity_id": entity_id,
        "entity_code": entity_code,
        "entity_name": entity_name or entity_id,
        "department": department,
        "supervisor_id": supervisor_id,
        "supervisor_name": supervisor_name,
        "supervisor_user_id": supervisor_user_id,
        "supervisor_has_account": supervisor_has_account,
    }


# ---------------------------------------------------------------------------
# Leave request business logic
# ---------------------------------------------------------------------------
def leave_requests() -> list[dict[str, Any]]:
    return load_json_array(LEAVE_REQUESTS_PATH)


def save_leave_requests(rows: list[dict[str, Any]]) -> None:
    save_json_array(LEAVE_REQUESTS_PATH, rows)


def audit_logs() -> list[dict[str, Any]]:
    return load_json_array(AUDIT_LOGS_PATH)


def save_audit_logs(rows: list[dict[str, Any]]) -> None:
    save_json_array(AUDIT_LOGS_PATH, rows)


def append_audit(record_id: str, action: str, user_name: str, before_val: Any, after_val: Any, notes: str = "") -> None:
    rows = audit_logs()
    rows.append({
        "audit_id": next_sequence_id(rows, "audit_id", "SELF"),
        "module": MODULE_NAME,
        "record_id": record_id,
        "action": action,
        "user": user_name,
        "timestamp": now_iso(),
        "before_value": before_val if before_val is not None else {},
        "after_value": after_val if after_val is not None else {},
        "notes": notes,
    })
    save_audit_logs(rows)


def get_leave_request(leave_id: str) -> dict[str, Any] | None:
    for lr in leave_requests():
        if str(lr.get("leave_id", "")) == leave_id:
            return lr
    return None


def check_and_apply_timeouts(lr: dict[str, Any]) -> dict[str, Any]:
    """Check if any approval timeout has elapsed and auto-transition."""
    now = datetime.now(timezone.utc)
    status = str(lr.get("status", ""))

    if status == "supervisor_pending":
        submitted_at = str(lr.get("submitted_at", ""))
        if submitted_at:
            try:
                submitted_dt = datetime.fromisoformat(submitted_at.replace("Z", "+00:00"))
                if now - submitted_dt > timedelta(hours=SUPERVISOR_TIMEOUT_HOURS):
                    lr["status"] = "supervisor_skipped"
                    lr["supervisor_action"] = "auto_skipped"
                    lr["supervisor_action_at"] = now_iso()
                    lr["supervisor_action_by"] = "SYSTEM"
                    lr["supervisor_note"] = f"Auto-skipped: {SUPERVISOR_TIMEOUT_HOURS}h timeout"
                    lr["hr_pending_at"] = now_iso()
                    lr["updated_at"] = now_iso()
            except (ValueError, TypeError):
                pass

    if status in ("supervisor_skipped", "supervisor_pending"):
        # After supervisor step, check HR timeout
        hr_pending_at = str(lr.get("hr_pending_at", ""))
        current_status = str(lr.get("status", ""))
        if current_status in ("supervisor_skipped",) and hr_pending_at:
            try:
                hr_dt = datetime.fromisoformat(hr_pending_at.replace("Z", "+00:00"))
                if now - hr_dt > timedelta(hours=HR_TIMEOUT_HOURS):
                    lr["status"] = "hr_auto_approved"
                    lr["hr_action"] = "auto_approved"
                    lr["hr_action_at"] = now_iso()
                    lr["hr_action_by"] = "SYSTEM"
                    lr["hr_note"] = f"Auto-approved: {HR_TIMEOUT_HOURS}h timeout"
                    lr["approved_at"] = now_iso()
                    lr["updated_at"] = now_iso()
            except (ValueError, TypeError):
                pass

    if status == "hr_pending":
        hr_pending_at = str(lr.get("hr_pending_at", ""))
        if hr_pending_at:
            try:
                hr_dt = datetime.fromisoformat(hr_pending_at.replace("Z", "+00:00"))
                if now - hr_dt > timedelta(hours=HR_TIMEOUT_HOURS):
                    lr["status"] = "hr_auto_approved"
                    lr["hr_action"] = "auto_approved"
                    lr["hr_action_at"] = now_iso()
                    lr["hr_action_by"] = "SYSTEM"
                    lr["hr_note"] = f"Auto-approved: {HR_TIMEOUT_HOURS}h timeout"
                    lr["approved_at"] = now_iso()
                    lr["updated_at"] = now_iso()
            except (ValueError, TypeError):
                pass

    return lr


def create_leave_request(payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    rows = leave_requests()
    user_id = str(user.get("user_id", ""))
    emp_info = get_employee_info(user)

    leave_id = next_sequence_id(rows, "leave_id", "LEAVE")
    now = now_iso()

    start_date = clean_text(payload.get("start_date", ""))
    end_date = clean_text(payload.get("end_date", ""))
    leave_days = compute_leave_days(start_date, end_date)

    lr = {
        "leave_id": leave_id,
        "leave_type": clean_text(payload.get("leave_type", "personal_leave")),
        "start_date": start_date,
        "end_date": end_date,
        "leave_days": leave_days,
        "reason": clean_text(payload.get("reason", "")),
        "status": "draft",
        # Applicant info (auto-populated from employee record)
        "applicant_user_id": user_id,
        "applicant_name": user_display_name(user),
        "employee_id": emp_info["employee_id"],
        "employee_name": emp_info["employee_name"],
        "entity_id": emp_info["entity_id"],
        "entity_code": emp_info["entity_code"],
        "entity_name": emp_info["entity_name"],
        "department": emp_info["department"],
        # Supervisor info
        "supervisor_id": emp_info["supervisor_id"],
        "supervisor_name": emp_info["supervisor_name"],
        "supervisor_user_id": emp_info["supervisor_user_id"],
        "supervisor_has_account": emp_info["supervisor_has_account"],
        "supervisor_action": "",
        "supervisor_action_at": "",
        "supervisor_action_by": "",
        "supervisor_note": "",
        # HR info
        "hr_action": "",
        "hr_action_at": "",
        "hr_action_by": "",
        "hr_note": "",
        # Timestamps
        "created_at": now,
        "submitted_at": "",
        "supervisor_pending_at": "",
        "hr_pending_at": "",
        "approved_at": "",
        "updated_at": now,
        "notes": clean_text(payload.get("notes", "")),
    }

    if clean_text(payload.get("action")) == "submit":
        lr = _submit_leave(lr, user)

    rows.append(lr)
    save_leave_requests(rows)
    append_audit(leave_id, "created", user_display_name(user), None, lr)
    return lr


def update_leave_request(leave_id: str, payload: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            before = dict(lr)
            status = str(lr.get("status", ""))

            if status == "draft":
                lr["leave_type"] = clean_text(payload.get("leave_type", lr.get("leave_type")))
                lr["start_date"] = clean_text(payload.get("start_date", lr.get("start_date")))
                lr["end_date"] = clean_text(payload.get("end_date", lr.get("end_date")))
                lr["leave_days"] = compute_leave_days(str(lr["start_date"]), str(lr["end_date"]))
                lr["reason"] = clean_text(payload.get("reason", lr.get("reason")))
                lr["notes"] = clean_text(payload.get("notes", lr.get("notes")))
                lr["updated_at"] = now_iso()

                if clean_text(payload.get("action")) == "submit":
                    lr = _submit_leave(lr, user)

                rows[i] = lr
                save_leave_requests(rows)
                append_audit(leave_id, "updated", user_display_name(user), before, lr)
                return lr
            else:
                raise ValueError(f"Cannot edit leave request in '{status}' status")

    raise ValueError(f"Leave request not found: {leave_id}")


def _submit_leave(lr: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
    """Transition a leave request from draft to submitted/supervisor_pending/hr_pending."""
    now = now_iso()
    lr["status"] = "submitted"
    lr["submitted_at"] = now
    lr["updated_at"] = now

    if lr.get("supervisor_has_account") and lr.get("supervisor_user_id"):
        lr["status"] = "supervisor_pending"
        lr["supervisor_pending_at"] = now
        _send_notification(
            recipient_user_id=lr["supervisor_user_id"],
            title=f"Leave Approval - {lr['employee_name']}",
            content=_build_notification_content(lr, "supervisor"),
            biz_id=lr["leave_id"],
        )
    else:
        # No supervisor with account → skip to HR
        lr["status"] = "supervisor_skipped"
        lr["supervisor_action"] = "auto_skipped"
        lr["supervisor_action_at"] = now
        lr["supervisor_action_by"] = "SYSTEM"
        lr["supervisor_note"] = "No supervisor with user account; auto-skipped"
        lr["hr_pending_at"] = now
        _send_notification_to_hr(lr)

    return lr


def approve_by_supervisor(leave_id: str, user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Supervisor approves → move to HR pending."""
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            lr = check_and_apply_timeouts(lr)
            before = dict(lr)
            if str(lr.get("status", "")) != "supervisor_pending":
                raise ValueError(f"Leave request is not in supervisor_pending status (current: {lr.get('status')})")

            now = now_iso()
            lr["status"] = "supervisor_approved" if False else "hr_pending"  # simplified: go straight to hr_pending
            lr["supervisor_action"] = "approved"
            lr["supervisor_action_at"] = now
            lr["supervisor_action_by"] = user_display_name(user)
            lr["supervisor_note"] = note
            lr["hr_pending_at"] = now
            lr["updated_at"] = now

            rows[i] = lr
            save_leave_requests(rows)
            append_audit(leave_id, "supervisor_approved", user_display_name(user), before, lr)
            _send_notification_to_hr(lr)
            return lr
    raise ValueError(f"Leave request not found: {leave_id}")


def reject_by_supervisor(leave_id: str, user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """Supervisor rejects."""
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            lr = check_and_apply_timeouts(lr)
            before = dict(lr)
            if str(lr.get("status", "")) != "supervisor_pending":
                raise ValueError(f"Leave request is not in supervisor_pending status (current: {lr.get('status')})")

            now = now_iso()
            lr["status"] = "rejected"
            lr["supervisor_action"] = "rejected"
            lr["supervisor_action_at"] = now
            lr["supervisor_action_by"] = user_display_name(user)
            lr["supervisor_note"] = note
            lr["updated_at"] = now

            rows[i] = lr
            save_leave_requests(rows)
            append_audit(leave_id, "supervisor_rejected", user_display_name(user), before, lr)
            _send_notification(
                recipient_user_id=lr["applicant_user_id"],
                title=f"Leave Rejected - {lr['leave_type']}",
                content=_build_notification_content(lr, "rejected"),
                biz_id=lr["leave_id"],
            )
            return lr
    raise ValueError(f"Leave request not found: {leave_id}")


def approve_by_hr(leave_id: str, user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """HR approves → completed."""
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            lr = check_and_apply_timeouts(lr)
            before = dict(lr)
            status = str(lr.get("status", ""))
            if status not in ("hr_pending", "supervisor_skipped"):
                raise ValueError(f"Leave request is not in HR-reviewable status (current: {status})")

            now = now_iso()
            lr["status"] = "approved"
            lr["hr_action"] = "approved"
            lr["hr_action_at"] = now
            lr["hr_action_by"] = user_display_name(user)
            lr["hr_note"] = note
            lr["approved_at"] = now
            lr["updated_at"] = now

            rows[i] = lr
            save_leave_requests(rows)
            append_audit(leave_id, "hr_approved", user_display_name(user), before, lr)
            _send_notification(
                recipient_user_id=lr["applicant_user_id"],
                title=f"Leave Approved - {lr['leave_type']}",
                content=_build_notification_content(lr, "approved"),
                biz_id=lr["leave_id"],
            )
            return lr
    raise ValueError(f"Leave request not found: {leave_id}")


def reject_by_hr(leave_id: str, user: dict[str, Any], note: str = "") -> dict[str, Any]:
    """HR rejects."""
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            lr = check_and_apply_timeouts(lr)
            before = dict(lr)
            status = str(lr.get("status", ""))
            if status not in ("hr_pending", "supervisor_skipped"):
                raise ValueError(f"Leave request is not in HR-reviewable status (current: {status})")

            now = now_iso()
            lr["status"] = "rejected"
            lr["hr_action"] = "rejected"
            lr["hr_action_at"] = now
            lr["hr_action_by"] = user_display_name(user)
            lr["hr_note"] = note
            lr["updated_at"] = now

            rows[i] = lr
            save_leave_requests(rows)
            append_audit(leave_id, "hr_rejected", user_display_name(user), before, lr)
            _send_notification(
                recipient_user_id=lr["applicant_user_id"],
                title=f"Leave Rejected - {lr['leave_type']}",
                content=_build_notification_content(lr, "rejected"),
                biz_id=lr["leave_id"],
            )
            return lr
    raise ValueError(f"Leave request not found: {leave_id}")


def cancel_leave(leave_id: str, user: dict[str, Any]) -> dict[str, Any]:
    """Applicant cancels their own leave request."""
    rows = leave_requests()
    for i, lr in enumerate(rows):
        if str(lr.get("leave_id", "")) == leave_id:
            before = dict(lr)
            status = str(lr.get("status", ""))
            if status in FINAL_STATUSES:
                raise ValueError(f"Cannot cancel leave request in '{status}' status")

            lr["status"] = "cancelled"
            lr["updated_at"] = now_iso()
            rows[i] = lr
            save_leave_requests(rows)
            append_audit(leave_id, "cancelled", user_display_name(user), before, lr)
            return lr
    raise ValueError(f"Leave request not found: {leave_id}")


# ---------------------------------------------------------------------------
# Notification integration (tacaimsg)
# ---------------------------------------------------------------------------
def _send_notification(recipient_user_id: str, title: str, content: str, biz_id: str = "",
                       priority: str = "normal", msg_type: str = "notification") -> bool:
    """Send a notification message via tacaimsg internal API."""
    try:
        payload = json.dumps({
            "messages": [{
                "recipient_user_id": recipient_user_id,
                "msg_type": msg_type,
                "title": title,
                "content": content,
                "priority": priority,
                "biz_type": "leave_request",
                "biz_id": biz_id,
                "action_buttons": [
                    {"label": "View Details", "url": f"{APP_BASE_URL}/leaves/{biz_id}"}
                ],
            }],
            "sender_user_id": "SYSTEM",
            "sender_name": "TACAI Self-Service",
        }).encode("utf-8")

        request = Request(
            f"{TACAIMSG_INTERNAL_BASE_URL}/api/internal/messages/send-batch",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "X-TACAI-Internal-Token": TACAIMSG_INTERNAL_TOKEN,
            },
            method="POST",
        )
        with urlopen(request, timeout=5) as response:
            result = json.loads(response.read().decode("utf-8"))
            return result.get("code") == 200
    except Exception:
        return False


def _send_notification_to_hr(lr: dict[str, Any]) -> None:
    """Send notification to all HR users."""
    users = read_users()
    hr_users = [u for u in users if "hr_manager" in [str(r).strip().lower() for r in u.get("roles", [])]]
    entity_id = str(lr.get("entity_id", ""))

    for hr in hr_users:
        hr_entity = str(hr.get("entity_id", ""))
        if hr_entity and entity_id and hr_entity != entity_id:
            continue
        _send_notification(
            recipient_user_id=str(hr.get("user_id", "")),
            title=f"Leave Approval - {lr['employee_name']} ({lr['leave_type']})",
            content=_build_notification_content(lr, "hr"),
            biz_id=lr["leave_id"],
            priority="normal",
        )


def _build_notification_content(lr: dict[str, Any], stage: str) -> str:
    """Build HTML notification content for a leave request."""
    leave_type_label = lr.get("leave_type", "")
    entity_name = lr.get("entity_name", "")
    employee_name = lr.get("employee_name", "")

    stage_messages = {
        "supervisor": "<p>A leave request from your team member requires your approval.</p>",
        "hr": "<p>A leave request requires HR approval.</p>",
        "approved": "<p>Your leave request has been <strong style='color:#059669'>approved</strong>.</p>",
        "rejected": "<p>Your leave request has been <strong style='color:#dc2626'>rejected</strong>.</p>",
    }

    return f"""<div style="font-family: sans-serif; max-width: 600px;">
<h3 style="color: #1a56db;">Leave Request</h3>
{stage_messages.get(stage, '')}
<table style="width:100%; border-collapse: collapse; margin: 12px 0; border: 1px solid #e5e7eb; border-radius: 8px;">
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600;">Type</td><td style="padding: 8px 12px;">{leave_type_label}</td></tr>
<tr><td style="padding: 8px 12px; font-weight: 600;">Employee</td><td style="padding: 8px 12px;">{employee_name}</td></tr>
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600;">Entity</td><td style="padding: 8px 12px;">{entity_name}</td></tr>
<tr><td style="padding: 8px 12px; font-weight: 600;">Period</td><td style="padding: 8px 12px;">{lr.get('start_date', '')} ~ {lr.get('end_date', '')} ({lr.get('leave_days', 0)} days)</td></tr>
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600;">Reason</td><td style="padding: 8px 12px;">{lr.get('reason', '')}</td></tr>
</table>
<p style="color: #6b7280; font-size: 0.9em;">This message was automatically sent by TACAI Self-Service.</p>
</div>"""


# ---------------------------------------------------------------------------
# HTML page builders
# ---------------------------------------------------------------------------
def page(title: str, body: str, user: dict[str, Any] | None = None, current_path: str = "/",
         flash: str = "", lang: str = DEFAULT_LANG) -> str:
    lang = normalize_lang(lang)
    nav_links = [
        ("/dashboard", "nav.dashboard"),
        ("/leaves/new", "nav.new_leave"),
        ("/leaves", "nav.my_leaves"),
        ("/leaves/approvals", "nav.pending_approvals"),
        ("/leaves/all", "nav.all_leaves"),
        ("/audit-logs", "nav.audit"),
    ]
    nav_html = "".join(
        f'<a class="{h("active" if current_path == p else "")}" href="{h(url_with_lang(p, lang))}">{h(tr(lang, label))}</a>'
        for p, label in nav_links
    )
    portal_back = f'<a class="portal-back" href="{h(PORTAL_BASE_URL)}/dashboard?lang={h(lang)}">⌂ {h(tr(lang, "nav.portal"))}</a>'

    user_html = ""
    if user:
        user_html = f'<span class="current-user-chip">👤 {h(user_display_name(user))}</span>'

    flash_html = f'<section class="message-strip message-success" role="status">{h(flash)}</section>' if flash else ""
    body = localize_body(body, lang)
    lang_switcher = language_switcher_html(current_path, lang)

    return f"""<!doctype html>
<html lang="{h(lang)}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{h(title)} - {h(tr(lang, "app.title"))}</title>
  <style>
:root {{ --tacai-primary: #1a56db; --tacai-sidebar: #1e293b; --tacai-bg: #f1f5f9; --tacai-surface: #ffffff; --tacai-border: #e2e8f0; --tacai-muted: #94a3b8; --tacai-green: #059669; --tacai-red: #dc2626; --tacai-amber: #d97706; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: var(--tacai-bg); color: #1e293b; }}
.app-shell {{ display: flex; min-height: 100vh; }}
.sidebar {{ width: 240px; background: var(--tacai-sidebar); color: #e2e8f0; padding: 20px 16px; display: flex; flex-direction: column; gap: 8px; }}
.sidebar-title {{ font-size: 1.1rem; font-weight: 800; color: #fff; }}
.sidebar-subtitle {{ font-size: 0.75rem; color: #94a3b8; margin-bottom: 8px; }}
.sidebar a {{ color: #cbd5e1; text-decoration: none; padding: 8px 12px; border-radius: 8px; display: block; font-size: 0.9rem; }}
.sidebar a:hover {{ background: #334155; color: #fff; }}
.sidebar a.active {{ background: var(--tacai-primary); color: #fff; font-weight: 700; }}
.sidebar a.portal-back {{ margin-top: auto; font-size: 0.8rem; color: #94a3b8; }}
.content {{ flex: 1; padding: 24px 32px; overflow-x: auto; }}
.topbar {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 24px; }}
.topbar h1 {{ font-size: 1.5rem; }}
.eyebrow {{ font-size: 0.75rem; text-transform: uppercase; color: var(--tacai-muted); letter-spacing: 0.5px; }}
.current-user-chip {{ background: #e2e8f0; padding: 4px 12px; border-radius: 20px; font-size: 0.85rem; }}
.card, .panel {{ background: var(--tacai-surface); border: 1px solid var(--tacai-border); border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
.metric-card {{ background: var(--tacai-surface); border: 1px solid var(--tacai-border); border-radius: 12px; padding: 16px; text-align: center; text-decoration: none; color: inherit; display: block; }}
.metric-card:hover {{ border-color: var(--tacai-primary); }}
.metric-card .value {{ font-size: 2rem; font-weight: 800; }}
.metric-card .muted {{ font-size: 0.8rem; color: var(--tacai-muted); }}
.grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; }}
.form-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; align-items: end; }}
.form-field {{ display: flex; flex-direction: column; gap: 4px; }}
.form-field label {{ font-size: 0.8rem; font-weight: 700; color: var(--tacai-muted); text-transform: uppercase; }}
.form-field input, .form-field select, .form-field textarea {{ padding: 8px 12px; border: 1px solid var(--tacai-border); border-radius: 8px; font-size: 0.9rem; }}
.form-field textarea {{ min-height: 80px; resize: vertical; }}
.form-field input:focus, .form-field select:focus, .form-field textarea:focus {{ outline: none; border-color: var(--tacai-primary); box-shadow: 0 0 0 3px rgba(26,86,219,0.1); }}
button, .button {{ display: inline-block; padding: 8px 16px; background: var(--tacai-primary); color: #fff; border: none; border-radius: 8px; cursor: pointer; font-size: 0.9rem; font-weight: 600; text-decoration: none; }}
button:hover, .button:hover {{ opacity: 0.9; }}
button.secondary, .button.secondary {{ background: #e2e8f0; color: #1e293b; }}
button.success, .button.success {{ background: var(--tacai-green); }}
button.danger, .button.danger {{ background: var(--tacai-red); }}
button.warning, .button.warning {{ background: var(--tacai-amber); }}
button.ghost, .button.ghost {{ background: transparent; color: var(--tacai-primary); }}
table {{ width: 100%; border-collapse: collapse; }}
th {{ background: #f8fafc; padding: 10px 12px; text-align: left; font-size: 0.8rem; font-weight: 700; color: var(--tacai-muted); text-transform: uppercase; border-bottom: 2px solid var(--tacai-border); }}
td {{ padding: 10px 12px; border-bottom: 1px solid var(--tacai-border); font-size: 0.9rem; }}
tr:hover {{ background: #f8fafc; }}
.table-scroll {{ overflow-x: auto; }}
.status-badge {{ display: inline-block; padding: 2px 10px; border-radius: 12px; font-size: 0.8rem; font-weight: 700; }}
.status-draft {{ background: #f1f5f9; color: #64748b; }}
.status-submitted {{ background: #dbeafe; color: #1e40af; }}
.status-supervisor_pending {{ background: #fef3c7; color: #92400e; }}
.status-supervisor_skipped {{ background: #fce7f3; color: #9d174d; }}
.status-hr_pending {{ background: #fef3c7; color: #92400e; }}
.status-hr_auto_approved {{ background: #fce7f3; color: #9d174d; }}
.status-approved {{ background: #d1fae5; color: #065f46; }}
.status-rejected {{ background: #fee2e2; color: #991b1b; }}
.status-cancelled {{ background: #f1f5f9; color: #64748b; }}
.status-personal_leave {{ background: #dbeafe; color: #1e40af; }}
.status-sick_leave {{ background: #fef3c7; color: #92400e; }}
.status-compensatory_leave {{ background: #d1fae5; color: #065f46; }}
.sap-info-strip {{ display: flex; gap: 16px; flex-wrap: wrap; font-size: 0.85rem; color: var(--tacai-muted); margin: 8px 0 16px; }}
.sap-info-strip span {{ background: #f1f5f9; padding: 4px 12px; border-radius: 16px; }}
.sap-toolbar {{ display: flex; gap: 8px; flex-wrap: wrap; margin: 12px 0; }}
.sap-readonly-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; }}
.sap-readonly-field {{ background: #f8fafc; border: 1px solid var(--tacai-border); border-radius: 10px; padding: 12px; }}
.sap-readonly-field .label {{ color: var(--tacai-muted); font-size: 0.78rem; font-weight: 850; text-transform: uppercase; margin-bottom: 4px; }}
.sap-readonly-field .value {{ color: var(--tacai-sidebar); font-weight: 850; }}
.helper-text {{ font-size: 0.8rem; color: var(--tacai-muted); margin-top: 8px; }}
.message-strip {{ padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; }}
.message-success {{ background: #d1fae5; color: #065f46; }}
.message-error {{ background: #fee2e2; color: #991b1b; }}
.message-info {{ background: #dbeafe; color: #1e40af; }}
.message-warning {{ background: #fef3c7; color: #92400e; }}
.language-switcher {{ display: flex; gap: 4px; align-items: center; font-size: 0.8rem; }}
.language-switcher a {{ color: #94a3b8; text-decoration: none; padding: 2px 6px; }}
.language-switcher a.active {{ color: #fff; font-weight: 700; }}
.empty-state {{ text-align: center; padding: 40px; color: var(--tacai-muted); }}
.leave-detail-card {{ max-width: 800px; }}
.workflow-timeline {{ margin-top: 16px; }}
.workflow-step {{ display: flex; gap: 12px; align-items: flex-start; padding: 12px 0; border-left: 2px solid var(--tacai-border); margin-left: 12px; padding-left: 24px; position: relative; }}
.workflow-step::before {{ content: ''; position: absolute; left: -7px; top: 16px; width: 12px; height: 12px; border-radius: 50%; background: var(--tacai-muted); }}
.workflow-step.completed::before {{ background: var(--tacai-green); }}
.workflow-step.active::before {{ background: var(--tacai-primary); box-shadow: 0 0 0 4px rgba(26,86,219,0.2); }}
.workflow-step.skipped::before {{ background: var(--tacai-amber); }}
.workflow-step.rejected::before {{ background: var(--tacai-red); }}
.actions {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 16px; }}
.timeout-info {{ font-size: 0.8rem; color: var(--tacai-muted); margin-top: 8px; padding: 8px 12px; background: #f8fafc; border-radius: 8px; }}
  </style>
</head>
<body>
<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-title">{h(tr(lang, "app.title"))}</div>
    <p class="sidebar-subtitle">{h(tr(lang, "app.subtitle"))}</p>
    <nav>{nav_html}{portal_back}</nav>
    <div class="sidebar-footer">{lang_switcher}</div>
  </aside>
  <main class="content">
    <header class="topbar">
      <div><p class="eyebrow">TACAI Self-Service</p><h1>{h(title)}</h1></div>
      <div class="topbar-actions">{user_html}</div>
    </header>
    {flash_html}
    {body}
  </main>
</div>
</body>
</html>"""


LANGUAGE_LABELS = {"ja": "日本語", "zh": "中文", "en": "English"}


def language_switcher_html(current_path: str, current_lang: str) -> str:
    parts = [f'<div class="language-switcher"><span>{h(tr(current_lang, "language.label"))}</span>']
    for code in ("ja", "zh", "en"):
        label = LANGUAGE_LABELS.get(code, code)
        active = " active" if code == current_lang else ""
        parts.append(f'<a class="lang-link{active}" href="{h(url_with_lang(current_path, code))}">{label}</a>')
    parts.append("</div>")
    return "".join(parts)


# ---- Dashboard ----
def dashboard_html(user: dict[str, Any], lang: str) -> str:
    user_id = str(user.get("user_id", ""))
    all_lrs = leave_requests()

    # Apply timeouts
    for i, lr in enumerate(all_lrs):
        all_lrs[i] = check_and_apply_timeouts(lr)

    my_pending = [lr for lr in all_lrs if lr.get("applicant_user_id") == user_id and lr.get("status") in ACTIVE_STATUSES]
    to_approve = [lr for lr in all_lrs if
                  (lr.get("supervisor_user_id") == user_id and lr.get("status") == "supervisor_pending")
                  or (lr.get("status") in ("hr_pending", "supervisor_skipped"))]
    this_month = now_date_str()[:7]
    approved_month = [lr for lr in all_lrs if lr.get("status") in ("approved", "hr_auto_approved")
                      and str(lr.get("approved_at", ""))[:7] == this_month]

    body = f"""
<div class="grid" style="margin-bottom:20px">
  <a class="metric-card" href="{h(url_with_lang('/leaves', lang))}">
    <div class="muted">{h(tr(lang, 'dashboard.my_pending'))}</div>
    <div class="value" style="color:var(--tacai-amber)">{len(my_pending)}</div>
  </a>
  <a class="metric-card" href="{h(url_with_lang('/leaves/approvals', lang))}">
    <div class="muted">{h(tr(lang, 'dashboard.to_approve'))}</div>
    <div class="value" style="color:var(--tacai-primary)">{len(to_approve)}</div>
  </a>
  <a class="metric-card" href="{h(url_with_lang('/leaves/all', lang))}">
    <div class="muted">{h(tr(lang, 'dashboard.approved_month'))}</div>
    <div class="value" style="color:var(--tacai-green)">{len(approved_month)}</div>
  </a>
</div>
<div class="card">
  <h3>Quick Actions</h3>
  <div class="actions">
    <a class="button" href="{h(url_with_lang('/leaves/new', lang))}">{h(tr(lang, 'dashboard.quick_new'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/leaves', lang))}">{h(tr(lang, 'dashboard.quick_my'))}</a>
    <a class="button secondary" href="{h(url_with_lang('/leaves/approvals', lang))}">{h(tr(lang, 'dashboard.quick_approve'))}</a>
  </div>
</div>
<div class="panel">
  <div class="timeout-info">⏱ {h(tr(lang, 'timeout.supervisor_info'))} &nbsp;|&nbsp; ⏱ {h(tr(lang, 'timeout.hr_info'))}</div>
</div>
"""
    return body


# ---- Leave Form (New/Edit) ----
def leave_form_html(user: dict[str, Any], lang: str, existing: dict[str, Any] | None = None) -> str:
    emp_info = get_employee_info(user)
    is_edit = existing is not None
    leave_id = existing.get("leave_id", "") if existing else ""

    title_key = "leave.edit_title" if is_edit else "leave.new_title"
    body = f"<h2>{h(tr(lang, title_key))}</h2>"

    # Show auto-populated employee info
    body += f"""
<div class="card" style="margin-bottom:16px">
  <h3 style="margin-bottom:12px">Employee Information (auto-populated)</h3>
  <div class="sap-readonly-grid">
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.applicant'))}</div><div class="value">{h(emp_info['employee_name'])}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.entity'))}</div><div class="value">{h(emp_info['entity_code'])} - {h(emp_info['entity_name'])}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.department'))}</div><div class="value">{h(emp_info['department'])}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.supervisor'))}</div><div class="value">{h(emp_info['supervisor_name'] or '—')}</div></div>
  </div>
</div>"""

    # Form
    lr = existing or {}
    leave_type = h(lr.get("leave_type", "personal_leave"))
    start_date = h(lr.get("start_date", ""))
    end_date = h(lr.get("end_date", ""))
    reason = h(lr.get("reason", ""))
    notes = h(lr.get("notes", ""))

    type_options = "".join(
        f'<option value="{lt}" {"selected" if lt == leave_type else ""}>{h(tr(lang, f"type.{lt}"))}</option>'
        for lt in LEAVE_TYPES
    )

    action_url = f"/leaves/{leave_id}/edit" if is_edit else "/leaves/new"
    body += f"""
<div class="card">
  <form method="POST" action="{h(url_with_lang(action_url, lang))}">
    <div class="form-grid">
      <div class="form-field">
        <label>{h(tr(lang, 'leave.type'))}</label>
        <select name="leave_type">{type_options}</select>
      </div>
      <div class="form-field">
        <label>{h(tr(lang, 'leave.start_date'))}</label>
        <input type="date" name="start_date" value="{start_date}" required>
      </div>
      <div class="form-field">
        <label>{h(tr(lang, 'leave.end_date'))}</label>
        <input type="date" name="end_date" value="{end_date}" required>
      </div>
    </div>
    <div class="form-field" style="margin-top:12px">
      <label>{h(tr(lang, 'leave.reason'))}</label>
      <textarea name="reason" placeholder="Please describe the reason for leave...">{reason}</textarea>
    </div>
    <div class="form-field" style="margin-top:12px">
      <label>Notes</label>
      <input type="text" name="notes" value="{notes}" placeholder="Optional notes">
    </div>
    <div class="timeout-info" style="margin-top:12px">
      ⏱ {h(tr(lang, 'timeout.supervisor_info'))} &nbsp;|&nbsp; ⏱ {h(tr(lang, 'timeout.hr_info'))}
    </div>
    <div class="actions">
      <button type="submit" name="action" value="save">{h(tr(lang, 'action.save_draft'))}</button>
      <button type="submit" name="action" value="submit" class="success" onclick="return confirm('{h(tr(lang, 'msg.confirm_submit'))}')">{h(tr(lang, 'action.submit'))}</button>
      <a class="button secondary" href="{h(url_with_lang('/leaves', lang))}">{h(tr(lang, 'action.back'))}</a>
    </div>
  </form>
</div>"""
    return body


# ---- Leave List ----
def leave_list_html(user: dict[str, Any], lang: str, list_type: str = "my") -> str:
    user_id = str(user.get("user_id", ""))
    all_lrs = leave_requests()

    # Apply timeouts
    for i, lr in enumerate(all_lrs):
        all_lrs[i] = check_and_apply_timeouts(lr)

    if list_type == "my":
        filtered = [lr for lr in all_lrs if lr.get("applicant_user_id") == user_id]
        title_key = "leave.list_title"
    elif list_type == "approvals":
        filtered = [lr for lr in all_lrs if
                    (lr.get("supervisor_user_id") == user_id and lr.get("status") == "supervisor_pending")
                    or (lr.get("status") in ("hr_pending", "supervisor_skipped"))]
        title_key = "nav.pending_approvals"
    else:
        filtered = all_lrs
        title_key = "nav.all_leaves"

    filtered.sort(key=lambda lr: str(lr.get("created_at", "")), reverse=True)

    if not filtered:
        return f"<h2>{h(tr(lang, title_key))}</h2><div class='card'><div class='empty-state'>{h(tr(lang, 'leave.no_records'))}</div></div>"

    rows_html = ""
    for lr in filtered:
        detail_url = url_with_lang(f"/leaves/{lr['leave_id']}", lang)
        rows_html += f"""<tr>
  <td><a href="{h(detail_url)}" style="color:var(--tacai-primary);text-decoration:none;font-weight:700">{h(lr.get('leave_id', ''))}</a></td>
  <td>{leave_type_badge(lr.get('leave_type', ''), lang)}</td>
  <td>{h(lr.get('start_date', ''))} ~ {h(lr.get('end_date', ''))}</td>
  <td>{h(str(lr.get('leave_days', '')))}</td>
  <td>{h(lr.get('employee_name', ''))}</td>
  <td>{h(lr.get('entity_name', ''))}</td>
  <td>{h(lr.get('department', ''))}</td>
  <td>{status_badge(status_label(lr.get('status', ''), lang))}</td>
  <td>{h(str(lr.get('created_at', ''))[:10])}</td>
</tr>"""

    return f"""
<h2>{h(tr(lang, title_key))}</h2>
<div class="card">
  <div class="table-scroll">
    <table>
      <thead><tr>
        <th>ID</th><th>{h(tr(lang, 'leave.type'))}</th><th>Period</th><th>{h(tr(lang, 'leave.days'))}</th>
        <th>{h(tr(lang, 'leave.applicant'))}</th><th>{h(tr(lang, 'leave.entity'))}</th>
        <th>{h(tr(lang, 'leave.department'))}</th><th>{h(tr(lang, 'leave.status'))}</th><th>Created</th>
      </tr></thead>
      <tbody>{rows_html}</tbody>
    </table>
  </div>
  <div class="helper-text">{h(tr(lang, 'common.records_total').format(total=len(filtered)))}</div>
</div>"""


# ---- Leave Detail ----
def leave_detail_html(user: dict[str, Any], lang: str, leave_id: str) -> str:
    lr = get_leave_request(leave_id)
    if not lr:
        return f'<div class="message-strip message-error">Leave request not found: {h(leave_id)}</div>'

    # Apply timeouts
    lr = check_and_apply_timeouts(lr)
    # Save if timeout was applied
    rows = leave_requests()
    for i, r in enumerate(rows):
        if str(r.get("leave_id", "")) == leave_id:
            rows[i] = lr
            break
    save_leave_requests(rows)

    user_id = str(user.get("user_id", ""))
    status = str(lr.get("status", ""))
    is_applicant = str(lr.get("applicant_user_id", "")) == user_id
    is_supervisor = str(lr.get("supervisor_user_id", "")) == user_id and status == "supervisor_pending"
    is_hr = status in ("hr_pending", "supervisor_skipped")
    can_approve = is_supervisor or is_hr
    can_cancel = is_applicant and status not in FINAL_STATUSES

    # Timeline
    timeline = _workflow_timeline_html(lr, lang)

    # Precompute URLs to avoid nested f-string issues
    approve_url = h(url_with_lang(f"/leaves/{leave_id}/approve", lang))
    reject_url = h(url_with_lang(f"/leaves/{leave_id}/reject", lang))
    cancel_url = h(url_with_lang(f"/leaves/{leave_id}/cancel", lang))
    leaves_url = h(url_with_lang("/leaves", lang))

    body = f"""
<h2>{h(tr(lang, 'leave.detail_title'))}</h2>
<div class="sap-info-strip">
  <span>ID: {h(leave_id)}</span>
  <span>{status_badge(status_label(status, lang))}</span>
  <span>{leave_type_badge(lr.get('leave_type', ''), lang)}</span>
</div>

<div class="card leave-detail-card">
  <div class="sap-readonly-grid">
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.applicant'))}</div><div class="value">{h(lr.get('employee_name', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.entity'))}</div><div class="value">{h(lr.get('entity_code', ''))} - {h(lr.get('entity_name', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.department'))}</div><div class="value">{h(lr.get('department', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.supervisor'))}</div><div class="value">{h(lr.get('supervisor_name', '') or '-')}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.start_date'))}</div><div class="value">{h(lr.get('start_date', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.end_date'))}</div><div class="value">{h(lr.get('end_date', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.days'))}</div><div class="value">{h(str(lr.get('leave_days', '')))}</div></div>
    <div class="sap-readonly-field"><div class="label">{h(tr(lang, 'leave.reason'))}</div><div class="value">{h(lr.get('reason', ''))}</div></div>
    <div class="sap-readonly-field"><div class="label">Submitted</div><div class="value">{h(str(lr.get('submitted_at', '-'))[0:19])}</div></div>
    <div class="sap-readonly-field"><div class="label">Approved</div><div class="value">{h(str(lr.get('approved_at', '-'))[0:19])}</div></div>
  </div>
</div>

<div class="card leave-detail-card">
  <h3 style="margin-bottom:12px">Approval Timeline</h3>
  {timeline}
</div>"""

    # Approval actions
    if can_approve:
        body += f"""
<div class="card leave-detail-card">
  <h3 style="margin-bottom:12px">Approval Action</h3>
  <form method="POST" action="{approve_url}" style="display:inline" onsubmit="return confirm('{h(tr(lang, 'msg.confirm_approve'))}')">
    <input type="text" name="note" placeholder="Optional comment" style="padding:6px 10px;border:1px solid var(--tacai-border);border-radius:6px;width:200px;margin-right:8px">
    <button type="submit" class="success">{h(tr(lang, 'action.approve'))}</button>
  </form>
  <form method="POST" action="{reject_url}" style="display:inline;margin-left:8px" onsubmit="return confirm('{h(tr(lang, 'msg.confirm_reject'))}')">
    <input type="text" name="note" placeholder="Rejection reason" style="padding:6px 10px;border:1px solid var(--tacai-border);border-radius:6px;width:200px;margin-right:8px">
    <button type="submit" class="danger">{h(tr(lang, 'action.reject'))}</button>
  </form>
  <div class="timeout-info" style="margin-top:12px">
    ⏱ {h(tr(lang, 'timeout.supervisor_info'))} &nbsp;|&nbsp; ⏱ {h(tr(lang, 'timeout.hr_info'))}
  </div>
</div>"""

    if can_cancel:
        body += f"""
<div class="card leave-detail-card">
  <form method="POST" action="{cancel_url}" onsubmit="return confirm('{h(tr(lang, 'msg.confirm_cancel'))}')">
    <button type="submit" class="warning">{h(tr(lang, 'action.cancel'))}</button>
  </form>
</div>"""

    body += f'<a class="button secondary" href="{leaves_url}">{h(tr(lang, "action.back"))}</a>'
    return body


def _workflow_timeline_html(lr: dict[str, Any], lang: str) -> str:
    """Build approval workflow timeline visualization."""
    status = str(lr.get("status", ""))
    steps = []

    # Step 1: Submitted
    submitted_at = str(lr.get("submitted_at", ""))[:16] if lr.get("submitted_at") else "—"
    steps.append(("completed", "Submitted", f"Leave request submitted<br><small>{submitted_at}</small>"))

    # Step 2: Supervisor
    sup_status = "pending"
    sup_label = "Supervisor Approval"
    sup_detail = ""
    if status in ("supervisor_pending",):
        sup_status = "active"
        sup_detail = "Awaiting supervisor action..."
    elif lr.get("supervisor_action") == "approved":
        sup_status = "completed"
        sup_detail = f"Approved by {lr.get('supervisor_action_by', '')}<br><small>{str(lr.get('supervisor_action_at', ''))[:16]}</small>"
    elif lr.get("supervisor_action") in ("auto_skipped",):
        sup_status = "skipped"
        sup_detail = f"Skipped: {lr.get('supervisor_note', '')}<br><small>{str(lr.get('supervisor_action_at', ''))[:16]}</small>"
    elif status in ("rejected",) and lr.get("supervisor_action") == "rejected":
        sup_status = "rejected"
        sup_detail = f"Rejected by {lr.get('supervisor_action_by', '')}<br><small>{str(lr.get('supervisor_action_at', ''))[:16]}</small>"

    steps.append((sup_status, sup_label, sup_detail))

    # Step 3: HR
    hr_status = "pending"
    hr_label = "HR Approval"
    hr_detail = ""
    if status in ("supervisor_skipped",) and not lr.get("hr_action"):
        hr_status = "active"
        hr_detail = "Awaiting HR action (supervisor skipped)..."
    elif status in ("hr_pending",):
        hr_status = "active"
        hr_detail = "Awaiting HR action..."
    elif lr.get("hr_action") == "approved":
        hr_status = "completed"
        hr_detail = f"Approved by {lr.get('hr_action_by', '')}<br><small>{str(lr.get('hr_action_at', ''))[:16]}</small>"
    elif lr.get("hr_action") == "auto_approved":
        hr_status = "skipped"
        hr_detail = f"Auto-approved: {lr.get('hr_note', '')}<br><small>{str(lr.get('hr_action_at', ''))[:16]}</small>"
    elif lr.get("hr_action") == "rejected":
        hr_status = "rejected"
        hr_detail = f"Rejected by {lr.get('hr_action_by', '')}<br><small>{str(lr.get('hr_action_at', ''))[:16]}</small>"

    steps.append((hr_status, hr_label, hr_detail))

    html_parts = ['<div class="workflow-timeline">']
    for step_status, label, detail in steps:
        html_parts.append(f"""
<div class="workflow-step {step_status}">
  <div>
    <strong>{h(label)}</strong>
    <div style="font-size:0.85rem;color:var(--tacai-muted)">{detail or '—'}</div>
  </div>
</div>""")
    html_parts.append('</div>')
    return "".join(html_parts)


# ---- Audit ----
def audit_html(lang: str) -> str:
    rows = audit_logs()
    rows.sort(key=lambda r: str(r.get("timestamp", "")), reverse=True)
    if not rows:
        return f"<h2>{h(tr(lang, 'nav.audit'))}</h2><div class='card'><div class='empty-state'>{h(tr(lang, 'common.no_records'))}</div></div>"

    trs = ""
    for r in rows[:100]:
        trs += f"<tr><td>{h(r.get('audit_id', ''))}</td><td>{h(r.get('action', ''))}</td><td>{h(r.get('record_id', ''))}</td><td>{h(r.get('user', ''))}</td><td>{h(str(r.get('timestamp', ''))[:19])}</td></tr>"

    return f"""
<h2>{h(tr(lang, 'nav.audit'))}</h2>
<div class="card">
  <div class="table-scroll"><table>
    <thead><tr><th>ID</th><th>Action</th><th>Record</th><th>User</th><th>Timestamp</th></tr></thead>
    <tbody>{trs}</tbody>
  </table></div>
  <div class="helper-text">{h(tr(lang, 'common.records_total').format(total=min(len(rows), 100)))}</div>
</div>"""


# ---------------------------------------------------------------------------
# Handler class
# ---------------------------------------------------------------------------
class SelfServiceHandler(BaseHTTPRequestHandler):
    server_version = "TACAI-SelfService/0.1"

    def current_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return morsel.value if morsel else ""

    def current_user(self) -> dict[str, Any] | None:
        return validate_user_admin_session(self.current_session_id())

    def require_user(self) -> dict[str, Any] | None:
        user = self.current_user()
        if not user:
            self._send_redirect(self.user_admin_login_url(self.path))
            return None
        return user

    def user_admin_login_url(self, next_path: str) -> str:
        next_url = f"{APP_BASE_URL}{next_path if next_path.startswith('/') else '/' + next_path}"
        return f"{USER_ADMIN_BASE_URL}/login?next={quote(next_url, safe='')}"

    def flash_message(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(FLASH_COOKIE)
        return unquote(morsel.value) if morsel else ""

    def request_lang(self, query: dict[str, list[str]] | None = None) -> str:
        if query is None:
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query, keep_blank_values=True)
        if query.get("lang", [""])[0] in SUPPORTED_LANGS:
            return query["lang"][0]
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(LANG_COOKIE)
        lang = morsel.value if morsel and morsel.value in SUPPORTED_LANGS else DEFAULT_LANG
        return lang

    def _send_html(self, html_text: str, status: int = 200) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _send_redirect(self, location: str, flash: str = "") -> None:
        self.send_response(303)
        self.send_header("Location", location)
        if flash:
            cookie = SimpleCookie()
            cookie[FLASH_COOKIE] = quote(flash)
            cookie[FLASH_COOKIE]["path"] = "/"
            cookie[FLASH_COOKIE]["samesite"] = "Lax"
            self.send_header("Set-Cookie", cookie.output(header="").strip())
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length > MAX_POST_BYTES:
            raise ValueError("Request body too large")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    def _form_value(self, form: dict[str, list[str]], key: str, default: str = "") -> str:
        return (form.get(key, [default])[0] or default).strip()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query, keep_blank_values=True)
        lang = self.request_lang(query)
        flash = self.flash_message()

        try:
            if path == "/health":
                self._send_html("OK")
                return

            if path in ("/", ""):
                self._send_redirect(url_with_lang("/dashboard", lang))
                return

            if path == "/login":
                self._send_redirect(self.user_admin_login_url("/dashboard"))
                return

            if path == "/dashboard":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "dashboard.title"), dashboard_html(user, lang), user, "/dashboard", flash, lang))
                return

            if path == "/leaves/new":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "leave.new_title"), leave_form_html(user, lang), user, "/leaves/new", flash, lang))
                return

            if path == "/leaves":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "leave.list_title"), leave_list_html(user, lang, "my"), user, "/leaves", flash, lang))
                return

            if path == "/leaves/approvals":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "nav.pending_approvals"), leave_list_html(user, lang, "approvals"), user, "/leaves/approvals", flash, lang))
                return

            if path == "/leaves/all":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "nav.all_leaves"), leave_list_html(user, lang, "all"), user, "/leaves/all", flash, lang))
                return

            # Leave detail
            detail_match = re.match(r"^/leaves/(LEAVE-\d{8}-\d+)$", path)
            if detail_match:
                user = self.require_user()
                if not user: return
                leave_id = detail_match.group(1)
                self._send_html(page(tr(lang, "leave.detail_title"), leave_detail_html(user, lang, leave_id), user, f"/leaves/{leave_id}", flash, lang))
                return

            if path == "/audit-logs":
                user = self.require_user()
                if not user: return
                self._send_html(page(tr(lang, "nav.audit"), audit_html(lang), user, "/audit-logs", flash, lang))
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
            # Create leave request
            if path == "/leaves/new":
                user = self.require_user()
                if not user: return
                form = self._read_form()
                lr = create_leave_request({
                    "leave_type": self._form_value(form, "leave_type", "personal_leave"),
                    "start_date": self._form_value(form, "start_date"),
                    "end_date": self._form_value(form, "end_date"),
                    "reason": self._form_value(form, "reason"),
                    "notes": self._form_value(form, "notes"),
                    "action": self._form_value(form, "action", "save"),
                }, user)
                flash_msg = tr(lang, "msg.leave_submitted") if lr.get("status") != "draft" else tr(lang, "msg.leave_created")
                self._send_redirect(url_with_lang(f"/leaves/{lr['leave_id']}", lang), flash_msg)
                return

            # Edit leave request
            edit_match = re.match(r"^/leaves/(LEAVE-\d{8}-\d+)/edit$", path)
            if edit_match:
                user = self.require_user()
                if not user: return
                form = self._read_form()
                leave_id = edit_match.group(1)
                update_leave_request(leave_id, {
                    "leave_type": self._form_value(form, "leave_type", "personal_leave"),
                    "start_date": self._form_value(form, "start_date"),
                    "end_date": self._form_value(form, "end_date"),
                    "reason": self._form_value(form, "reason"),
                    "notes": self._form_value(form, "notes"),
                    "action": self._form_value(form, "action", "save"),
                }, user)
                self._send_redirect(url_with_lang(f"/leaves/{leave_id}", lang), tr(lang, "msg.leave_submitted"))
                return

            # Approve
            approve_match = re.match(r"^/leaves/(LEAVE-\d{8}-\d+)/approve$", path)
            if approve_match:
                user = self.require_user()
                if not user: return
                form = self._read_form()
                leave_id = approve_match.group(1)
                note = self._form_value(form, "note")
                lr = get_leave_request(leave_id)
                status = str(lr.get("status", "")) if lr else ""
                if status == "supervisor_pending":
                    approve_by_supervisor(leave_id, user, note)
                else:
                    approve_by_hr(leave_id, user, note)
                self._send_redirect(url_with_lang(f"/leaves/{leave_id}", lang), tr(lang, "msg.leave_approved"))
                return

            # Reject
            reject_match = re.match(r"^/leaves/(LEAVE-\d{8}-\d+)/reject$", path)
            if reject_match:
                user = self.require_user()
                if not user: return
                form = self._read_form()
                leave_id = reject_match.group(1)
                note = self._form_value(form, "note")
                lr = get_leave_request(leave_id)
                status = str(lr.get("status", "")) if lr else ""
                if status == "supervisor_pending":
                    reject_by_supervisor(leave_id, user, note)
                else:
                    reject_by_hr(leave_id, user, note)
                self._send_redirect(url_with_lang(f"/leaves/{leave_id}", lang), tr(lang, "msg.leave_rejected"))
                return

            # Cancel
            cancel_match = re.match(r"^/leaves/(LEAVE-\d{8}-\d+)/cancel$", path)
            if cancel_match:
                user = self.require_user()
                if not user: return
                leave_id = cancel_match.group(1)
                cancel_leave(leave_id, user)
                self._send_redirect(url_with_lang(f"/leaves/{leave_id}", lang), tr(lang, "msg.leave_cancelled"))
                return

            self._send_html(page("Not Found", f'<div class="message-strip message-error"><h3>404</h3></div>', lang=lang), status=404)

        except ValueError as exc:
            user = self.current_user()
            self._send_html(page("Error", f'<div class="message-strip message-error"><h3>Error</h3><p>{h(str(exc))}</p></div>', user, lang=lang), status=400)
        except Exception as exc:
            user = self.current_user()
            self._send_html(page("Error", f'<div class="message-strip message-error"><h3>Error</h3><p>{h(str(exc))}</p></div>', user, lang=lang), status=500)

    def log_message(self, fmt: str, *args: object) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{timestamp}] {self.address_string()} {fmt % args}", file=__import__("sys").stderr)


# ---------------------------------------------------------------------------
# Storage initialization
# ---------------------------------------------------------------------------
def ensure_storage() -> None:
    for p in [LEAVE_REQUESTS_PATH, AUDIT_LOGS_PATH]:
        if not p.exists():
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("[]", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    parser = argparse.ArgumentParser(description="Run TACAI Employee Self-Service local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    ensure_storage()
    server = ThreadingHTTPServer((args.host, args.port), SelfServiceHandler)
    print(f"TACAI Employee Self-Service running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TACAI Employee Self-Service")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
