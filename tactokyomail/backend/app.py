#!/usr/bin/env python3
"""
TAC Tokyo Mail — Approval Workflow Server
==========================================
Standard-library HTTP server implementing an approval workflow with
snapshot-based undo capability and append-only audit logging.

Port: 8006

Approval States (6):
  Draft → Submitted → HR_Reviewed → Manager_Approved → Final_Approved

  Rejected (reachable from Submitted/HR_Reviewed/Manager_Approved)

Undoable transitions:
  submit, hr_review, manager_approve, final_approve

Usage:
  python3 backend/app.py --host 127.0.0.1 --port 8006
"""

import json
import uuid
import argparse
import threading
from pathlib import Path
from datetime import datetime, timezone, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs, quote, unquote
from typing import Optional, Union

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATABASE_DIR = BASE_DIR / "database"
FRONTEND_DIR = BASE_DIR / "frontend"

APPROVAL_ITEMS_PATH = DATABASE_DIR / "approval_items.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
EMAIL_DRAFTS_PATH = DATABASE_DIR / "email_drafts.json"

JST = timezone(timedelta(hours=9))
FILE_LOCK = threading.RLock()

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STATUSES = [
    "Draft",
    "Submitted",
    "HR_Reviewed",
    "Manager_Approved",
    "Final_Approved",
    "Rejected",
]

STATUS_LABELS = {
    "Draft":             "草稿 / 下書き / Draft",
    "Submitted":         "已提交 / 申請済 / Submitted",
    "HR_Reviewed":       "HR已审核 / HR確認済 / HR Reviewed",
    "Manager_Approved":  "上级已批准 / 上長承認済 / Manager Approved",
    "Final_Approved":    "最终已批准 / 最終承認済 / Final Approved",
    "Rejected":          "已驳回 / 差戻し / Rejected",
}

# States from which undo is permitted (pure approval steps, no data mutation)
UNDOABLE_STATES = {"Submitted", "HR_Reviewed", "Manager_Approved", "Final_Approved"}

# Transition map: (current_status, action) → (target_status, undoable)
TRANSITION_MAP = {
    ("Draft",            "submit"):           ("Submitted",        True),
    ("Submitted",        "hr_review"):        ("HR_Reviewed",      True),
    ("HR_Reviewed",      "manager_approve"):  ("Manager_Approved", True),
    ("Manager_Approved", "final_approve"):    ("Final_Approved",   True),
    ("Submitted",        "reject"):           ("Rejected",         False),
    ("HR_Reviewed",      "reject"):           ("Rejected",         False),
    ("Manager_Approved", "reject"):           ("Rejected",         False),
    ("Rejected",         "resubmit"):         ("Draft",            False),
}

ACTION_LABELS = {
    "submit":          "提交 / 申請 / Submit",
    "hr_review":       "HR确认审核 / HR確認 / HR Review",
    "manager_approve": "上级批准 / 上長承認 / Manager Approve",
    "final_approve":   "最终批准 / 最終承認 / Final Approve",
    "reject":          "驳回 / 差戻し / Reject",
    "undo":            "撤销 / 取り消し / Undo",
    "resubmit":        "重新提交 / 再申請 / Resubmit",
}

# Undo reverse map: given current state, what was the previous state?
# Used as a fallback when the audit log snapshot is unavailable.
UNDO_REVERSE_MAP = {
    "Submitted":        "Draft",
    "HR_Reviewed":      "Submitted",
    "Manager_Approved": "Manager_Approved",  # resolved via audit log
    "Final_Approved":   "Manager_Approved",
}

# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def ensure_database():
    """Create database directory if missing."""
    DATABASE_DIR.mkdir(parents=True, exist_ok=True)


def load_json_array(path: Path) -> list[dict]:
    """Load a JSON array from file; return [] if missing or empty."""
    ensure_database()
    if not path.exists():
        return []
    try:
        with FILE_LOCK:
            data = json.loads(path.read_text(encoding="utf-8"))
        return [item for item in data if isinstance(item, dict)]
    except (json.JSONDecodeError, FileNotFoundError):
        return []


def save_json_array(path: Path, rows: list[dict]):
    """Atomically write a JSON array to file."""
    ensure_database()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with FILE_LOCK:
        tmp.write_text(
            json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp.replace(path)


def next_sequence(rows: list[dict], id_field: str, prefix: str) -> str:
    """Generate the next sequential ID (e.g., EML-0001)."""
    max_num = 0
    for row in rows:
        val = row.get(id_field, "")
        if val.startswith(prefix):
            try:
                num = int(val[len(prefix):])
                max_num = max(max_num, num)
            except ValueError:
                pass
    return f"{prefix}{max_num + 1:04d}"


def now_iso() -> str:
    """ISO 8601 timestamp in JST."""
    return datetime.now(JST).isoformat()


def now_utc_iso() -> str:
    """ISO 8601 timestamp in UTC."""
    return datetime.now(timezone.utc).isoformat()


def parse_json_body(body: str) -> dict:
    """Parse a JSON or form-urlencoded request body into a dict."""
    if not body:
        return {}
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        result = {}
        for pair in body.split("&"):
            if "=" in pair:
                key, val = pair.split("=", 1)
                result[unquote(key)] = unquote(val.replace("+", " "))
        return result


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------

def append_audit_log(module: str, record_id: str, action: str,
                     before_value: Optional[dict], after_value: Optional[dict],
                     user: str = "system", undoable: bool = False,
                     undo_target_audit_id: str = "",
                     context: Optional[dict] = None) -> dict:
    """
    Append an immutable audit log entry.
    Audit logs MUST never be deleted or modified.
    """
    logs = load_json_array(AUDIT_LOGS_PATH)
    audit_id = next_sequence(logs, "audit_id", "AUD-")
    entry = {
        "audit_id": audit_id,
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": user,
        "timestamp": now_iso(),
        "timestamp_utc": now_utc_iso(),
        "before_value": before_value if before_value is not None else {},
        "after_value": after_value if after_value is not None else {},
        "undoable": undoable,
        "undo_target_audit_id": undo_target_audit_id,
    }
    if context:
        entry["context"] = context
    logs.append(entry)
    save_json_array(AUDIT_LOGS_PATH, logs)
    return entry


# ---------------------------------------------------------------------------
# Approval item helpers
# ---------------------------------------------------------------------------

def load_approval_items() -> list[dict]:
    return load_json_array(APPROVAL_ITEMS_PATH)


def save_approval_items(items: list[dict]):
    save_json_array(APPROVAL_ITEMS_PATH, items)


def find_approval_item(item_id: str) -> tuple:
    """Return (record, index) or (None, None)."""
    items = load_approval_items()
    for i, item in enumerate(items):
        if item.get("item_id") == item_id:
            return item, i
    return None, None


def get_available_actions(status: str) -> list[dict]:
    """
    Return the list of actions available from the given status.
    Each action dict: {key, label, target, undoable, css_class}
    """
    actions = []
    for (from_status, action_key), (target, undoable) in TRANSITION_MAP.items():
        if from_status == status:
            css = ""
            if action_key == "reject":
                css = "danger"
            elif action_key == "resubmit":
                css = "secondary"
            actions.append({
                "key": action_key,
                "label": ACTION_LABELS.get(action_key, action_key),
                "target": target,
                "undoable": undoable,
                "css_class": css,
            })
    # Add undo action if the current state is undoable
    if status in UNDOABLE_STATES:
        actions.append({
            "key": "undo",
            "label": ACTION_LABELS["undo"],
            "target": UNDO_REVERSE_MAP.get(status, "Draft"),
            "undoable": False,
            "css_class": "warning",
        })
    return actions


# ---------------------------------------------------------------------------
# Core transition logic
# ---------------------------------------------------------------------------

def execute_transition(item_id: str, action: str, user: str = "system",
                       comment: str = "") -> tuple[dict, dict]:
    """
    Execute a state transition on an approval item.

    Returns (updated_item, audit_entry).
    Raises ValueError for invalid transitions.
    """
    action = action.strip().lower()
    items = load_approval_items()
    item, idx = find_approval_item(item_id)
    if item is None:
        raise ValueError(f"Approval item {item_id} not found.")

    current_status = item.get("status", "Draft")

    # --- Handle UNDO action ---
    if action == "undo":
        if current_status not in UNDOABLE_STATES:
            raise ValueError(
                f"Cannot undo from status '{current_status}'. "
                f"Undo is only available from: {', '.join(UNDOABLE_STATES)}."
            )
        # Find the most recent forward-transition audit entry to restore from
        logs = load_json_array(AUDIT_LOGS_PATH)
        target_log = None
        for log_entry in reversed(logs):
            if (log_entry.get("record_id") == item_id and
                    log_entry.get("action") != "undo" and
                    log_entry.get("undoable") is True):
                target_log = log_entry
                break

        if target_log is None:
            # Fallback: use reverse map
            prev_status = UNDO_REVERSE_MAP.get(current_status, "Draft")
            before_value = dict(item)
            restored = dict(item)
            restored["status"] = prev_status
            restored["updated_at"] = now_iso()
        else:
            before_value = dict(item)
            # Restore from the snapshot stored in the target audit log
            snapshot = target_log.get("before_value", {})
            restored = dict(item)
            # Only restore status and reviewer fields from snapshot;
            # preserve item identity fields and content
            for key in ("status", "reviewed_by", "reviewed_at",
                        "approved_by", "approved_at",
                        "final_approved_by", "final_approved_at"):
                if key in snapshot:
                    restored[key] = snapshot[key]
            # Clear the reviewer/approver fields for the state we're undoing
            if current_status == "HR_Reviewed":
                restored["reviewed_by"] = ""
                restored["reviewed_at"] = ""
            elif current_status == "Manager_Approved":
                restored["approved_by"] = ""
                restored["approved_at"] = ""
            elif current_status == "Final_Approved":
                restored["final_approved_by"] = ""
                restored["final_approved_at"] = ""
            restored["updated_at"] = now_iso()
            restored["undo_comment"] = comment

        items[idx] = restored
        save_approval_items(items)

        audit = append_audit_log(
            module="approval.email_draft",
            record_id=item_id,
            action="undo",
            before_value=before_value,
            after_value=dict(restored),
            user=user,
            undoable=False,
            undo_target_audit_id=target_log.get("audit_id", "") if target_log else "",
            context={"comment": comment, "undone_action": target_log.get("action", "") if target_log else ""},
        )
        return restored, audit

    # --- Handle forward transitions ---
    target_info = TRANSITION_MAP.get((current_status, action))
    if target_info is None:
        raise ValueError(
            f"Invalid transition: cannot '{action}' from status '{current_status}'."
        )

    target_status, undoable = target_info
    before_value = dict(item)
    now = now_iso()

    # Apply transition
    item["status"] = target_status
    item["updated_at"] = now

    if action == "submit":
        item["submitted_at"] = now
        item["submitted_by"] = user
    elif action == "hr_review":
        item["reviewed_at"] = now
        item["reviewed_by"] = user
    elif action == "manager_approve":
        item["approved_at"] = now
        item["approved_by"] = user
    elif action == "final_approve":
        item["final_approved_at"] = now
        item["final_approved_by"] = user
    elif action == "reject":
        item["rejected_at"] = now
        item["rejected_by"] = user
        item["reject_reason"] = comment
    elif action == "resubmit":
        item["resubmitted_at"] = now
        item["resubmitted_by"] = user
        # Clear rejection fields
        item["rejected_at"] = ""
        item["rejected_by"] = ""
        item["reject_reason"] = ""

    items[idx] = item
    save_approval_items(items)

    audit = append_audit_log(
        module="approval.email_draft",
        record_id=item_id,
        action=action,
        before_value=before_value,
        after_value=dict(item),
        user=user,
        undoable=undoable,
        context={"comment": comment} if comment else None,
    )
    return dict(item), audit


# ---------------------------------------------------------------------------
# HTML rendering
# ---------------------------------------------------------------------------

PAGE_HEADER = """<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg: #f5f5f5; --card: #fff; --text: #222; --muted: #666;
    --border: #ddd; --primary: #2563eb; --danger: #dc2626;
    --warning: #d97706; --good: #16a34a; --secondary: #6b7280;
    --radius: 6px;
  }}
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
          background: var(--bg); color: var(--text); line-height:1.5; }}
  .container {{ max-width:1100px; margin:0 auto; padding:16px 20px; }}
  nav {{ background: var(--card); border-bottom:1px solid var(--border); padding:10px 20px;
         display:flex; gap:16px; align-items:center; flex-wrap:wrap; }}
  nav a {{ color: var(--primary); text-decoration:none; font-weight:500; }}
  nav a:hover {{ text-decoration:underline; }}
  nav .brand {{ font-weight:700; font-size:1.1em; color:var(--text); margin-right:8px; }}
  h1 {{ margin-bottom:12px; font-size:1.4em; }}
  h2 {{ margin:16px 0 8px; font-size:1.15em; }}
  .card {{ background:var(--card); border:1px solid var(--border); border-radius:var(--radius);
           padding:16px 20px; margin-bottom:16px; }}
  table {{ width:100%; border-collapse:collapse; margin:8px 0; }}
  th, td {{ padding:8px 10px; text-align:left; border-bottom:1px solid var(--border); font-size:0.92em; }}
  th {{ background:#f9fafb; font-weight:600; white-space:nowrap; }}
  tr:hover {{ background:#fafafa; }}
  .badge {{ display:inline-block; padding:2px 8px; border-radius:12px; font-size:0.82em;
            font-weight:500; white-space:nowrap; }}
  .badge-draft {{ background:#e5e7eb; color:#374151; }}
  .badge-submitted {{ background:#dbeafe; color:#1e40af; }}
  .badge-hr_reviewed {{ background:#fef3c7; color:#92400e; }}
  .badge-manager_approved {{ background:#d1fae5; color:#065f46; }}
  .badge-final_approved {{ background:#c7d2fe; color:#3730a3; }}
  .badge-rejected {{ background:#fee2e2; color:#991b1b; }}
  .btn {{ display:inline-block; padding:6px 14px; border-radius:var(--radius); border:1px solid var(--border);
          background:var(--card); color:var(--text); cursor:pointer; text-decoration:none;
          font-size:0.9em; font-family:inherit; }}
  .btn:hover {{ filter:brightness(0.95); }}
  .btn-primary {{ background:var(--primary); color:#fff; border-color:var(--primary); }}
  .btn-danger {{ background:var(--danger); color:#fff; border-color:var(--danger); }}
  .btn-warning {{ background:var(--warning); color:#fff; border-color:var(--warning); }}
  .btn-good {{ background:var(--good); color:#fff; border-color:var(--good); }}
  .btn-secondary {{ background:var(--secondary); color:#fff; border-color:var(--secondary); }}
  .btn-sm {{ padding:3px 10px; font-size:0.8em; }}
  .actions {{ display:flex; gap:8px; flex-wrap:wrap; margin:12px 0; }}
  .helper-text {{ color:var(--muted); font-size:0.85em; margin-top:8px; }}
  .flash {{ padding:8px 14px; border-radius:var(--radius); margin-bottom:12px; font-size:0.9em; }}
  .flash-info {{ background:#dbeafe; color:#1e40af; border:1px solid #bfdbfe; }}
  .flash-error {{ background:#fee2e2; color:#991b1b; border:1px solid #fecaca; }}
  .flash-success {{ background:#d1fae5; color:#065f46; border:1px solid #a7f3d0; }}
  .detail-row {{ display:flex; padding:6px 0; border-bottom:1px solid var(--border); }}
  .detail-label {{ width:180px; font-weight:600; color:var(--muted); flex-shrink:0; }}
  .detail-value {{ flex:1; }}
  textarea, input[type=text], select {{ padding:6px 10px; border:1px solid var(--border);
          border-radius:var(--radius); font-size:0.9em; font-family:inherit; width:100%;
          max-width:500px; }}
  label {{ display:block; font-weight:600; margin:8px 0 4px; font-size:0.9em; }}
  .form-group {{ margin-bottom:12px; }}
  .undo-highlight {{ background:#fffbeb; border-left:3px solid var(--warning); padding-left:12px; }}
  @media (max-width:640px) {{
    .detail-row {{ flex-direction:column; }}
    .detail-label {{ width:100%; }}
    table {{ font-size:0.82em; }}
    th, td {{ padding:6px 4px; }}
  }}
</style>
</head>
<body>
<nav>
  <span class="brand">📧 TAC Tokyo Mail</span>
  <a href="/">首页 / Home</a>
  <a href="/approvals">审批列表 / Approvals</a>
  <a href="/audit-logs">审计日志 / Audit Logs</a>
  <a href="/approval-new">新建审批 / New</a>
</nav>
<div class="container">
"""

PAGE_FOOTER = """
</div>
</body>
</html>"""


def status_badge(status: str) -> str:
    """Render a colored status badge."""
    cls_map = {
        "Draft": "draft",
        "Submitted": "submitted",
        "HR_Reviewed": "hr_reviewed",
        "Manager_Approved": "manager_approved",
        "Final_Approved": "final_approved",
        "Rejected": "rejected",
    }
    cls = cls_map.get(status, "draft")
    label = STATUS_LABELS.get(status, status)
    return f'<span class="badge badge-{cls}">{label}</span>'


def render_dashboard(user: str) -> str:
    """Dashboard with summary counts per status."""
    items = load_approval_items()
    counts = {s: 0 for s in STATUSES}
    for item in items:
        s = item.get("status", "Draft")
        if s in counts:
            counts[s] += 1

    rows = ""
    for status in STATUSES:
        count = counts[status]
        rows += f"""<tr>
            <td>{status_badge(status)}</td>
            <td style="text-align:right;font-weight:600;">{count}</td>
        </tr>"""

    return PAGE_HEADER.format(title="TAC Tokyo Mail — Dashboard") + f"""
<h1>📧 TAC Tokyo Mail — 审批控制台 / Approval Dashboard</h1>
<div class="card">
  <h2>审批状态汇总 / Status Summary</h2>
  <table style="max-width:400px;">
    <tr><th>状态 / Status</th><th style="text-align:right;">数量 / Count</th></tr>
    {rows}
  </table>
  <div class="helper-text">{len(items)} total approval item(s)</div>
</div>
<div class="card">
  <h2>快捷操作 / Quick Actions</h2>
  <div class="actions">
    <a class="btn btn-primary" href="/approval-new">+ 新建审批 / New Approval</a>
    <a class="btn" href="/approvals">查看审批列表 / View All</a>
    <a class="btn btn-secondary" href="/audit-logs">审计日志 / Audit Logs</a>
  </div>
</div>
""" + PAGE_FOOTER


def render_approval_list(query_params: dict, user: str) -> str:
    """List all approval items with filter support."""
    items = load_approval_items()
    filter_status = query_params.get("status", [""])[0]

    if filter_status and filter_status in STATUSES:
        items = [i for i in items if i.get("status") == filter_status]

    # Sort: newest first
    items.sort(key=lambda x: x.get("created_at", ""), reverse=True)

    rows = ""
    for item in items:
        item_id = item.get("item_id", "")
        status = item.get("status", "Draft")
        subject = item.get("subject", "(no subject)")
        created = item.get("created_at", "")[:16]
        rows += f"""<tr>
            <td><a href="/approvals/{quote(item_id)}">{item_id}</a></td>
            <td>{subject}</td>
            <td>{status_badge(status)}</td>
            <td>{item.get('submitted_by', '-')}</td>
            <td style="white-space:nowrap;">{created}</td>
        </tr>"""

    filter_options = '<option value="">全部 / All</option>'
    for s in STATUSES:
        sel = " selected" if s == filter_status else ""
        filter_options += f'<option value="{s}"{sel}>{STATUS_LABELS.get(s, s)}</option>'

    return PAGE_HEADER.format(title="审批列表 / Approvals") + f"""
<h1>审批列表 / Approval Items</h1>
<div class="card">
  <form method="get" action="/approvals" style="margin-bottom:12px;">
    <label>状态过滤 / Filter by Status:</label>
    <div style="display:flex;gap:8px;align-items:center;">
      <select name="status" style="max-width:300px;">{filter_options}</select>
      <button type="submit" class="btn btn-primary btn-sm">过滤 / Filter</button>
      {f'<a href="/approvals" class="btn btn-secondary btn-sm">清除 / Clear</a>' if filter_status else ''}
    </div>
  </form>
  <table>
    <tr><th>ID</th><th>主题 / Subject</th><th>状态 / Status</th><th>提交人 / By</th><th>创建时间 / Created</th></tr>
    {rows if rows else '<tr><td colspan="5" style="text-align:center;color:var(--muted);">暂无审批项 / No approval items found</td></tr>'}
  </table>
  <div class="helper-text">{len(items)} record(s) total</div>
</div>
""" + PAGE_FOOTER


def render_approval_detail(item_id: str, user: str, flash_msg: str = "",
                           flash_type: str = "info") -> str:
    """Detail view for a single approval item with action buttons."""
    item, _ = find_approval_item(item_id)
    if item is None:
        return PAGE_HEADER.format(title="Not Found") + \
            '<h1>404 — 未找到 / Not Found</h1>' + PAGE_FOOTER

    status = item.get("status", "Draft")
    actions = get_available_actions(status)

    # Flash message
    flash_html = ""
    if flash_msg:
        flash_html = f'<div class="flash flash-{flash_type}">{flash_msg}</div>'

    # Action buttons
    action_buttons = ""
    for a in actions:
        akey = a["key"]
        alabel = a["label"]
        acls = a["css_class"]
        confirm_attr = ""
        if akey == "undo":
            confirm_attr = ' onclick="return confirm(\'确定要撤销到上一个状态吗？\\nUndo to previous state?\')"'
        elif akey == "reject":
            confirm_attr = ' onclick="return confirm(\'确定要驳回吗？\\nConfirm reject?\')"'
        btn_cls = f"btn-{acls}" if acls else "btn-primary"
        action_buttons += f"""<form method="post" action="/approvals/{quote(item_id)}/{akey}" style="display:inline;">
            <input type="hidden" name="comment" value="">
            <button type="submit" class="btn {btn_cls}"{confirm_attr}>{alabel}</button>
        </form> """

    if not action_buttons:
        action_buttons = '<span class="helper-text">无可用操作 / No actions available</span>'

    # Reject form (shown separately for comment input)
    can_reject = status in {"Submitted", "HR_Reviewed", "Manager_Approved"}
    reject_form = ""
    if can_reject:
        reject_form = f"""<div class="card" style="margin-top:12px; border-color:var(--danger);">
  <h2 style="color:var(--danger);">驳回 / Reject</h2>
  <form method="post" action="/approvals/{quote(item_id)}/reject">
    <div class="form-group">
      <label>驳回理由 / Reject Reason:</label>
      <textarea name="comment" rows="3" placeholder="请输入驳回理由 / Enter reject reason..."></textarea>
    </div>
    <button type="submit" class="btn btn-danger" onclick="return confirm('确定要驳回吗？ / Confirm reject?')">确认驳回 / Confirm Reject</button>
  </form>
</div>"""

    # Undo explanation
    undo_info = ""
    if status in UNDOABLE_STATES:
        undo_info = f"""<div class="card undo-highlight">
  <strong>💡 可撤销 / Undo Available:</strong> 当前状态 <em>{STATUS_LABELS.get(status, status)}</em> 为纯审批步骤，未涉及数据变更，可以安全撤销回到上一个状态。<br>
  <span style="color:var(--muted);font-size:0.85em;">This is a pure approval step with no data mutation. You can safely undo to the previous status. All audit logs are preserved.</span>
</div>"""

    # Detail fields
    fields = [
        ("审批ID / Item ID", item.get("item_id", "")),
        ("主题 / Subject", item.get("subject", "-")),
        ("内容 / Content", item.get("body", "-")),
        ("状态 / Status", status_badge(status)),
        ("创建时间 / Created", item.get("created_at", "-")[:19]),
        ("更新时间 / Updated", item.get("updated_at", "-")[:19]),
        ("提交人 / Submitted By", item.get("submitted_by", "-")),
        ("提交时间 / Submitted At", item.get("submitted_at", "-")[:19] if item.get("submitted_at") else "-"),
        ("HR审核人 / Reviewed By", item.get("reviewed_by", "-")),
        ("HR审核时间 / Reviewed At", item.get("reviewed_at", "-")[:19] if item.get("reviewed_at") else "-"),
        ("上级批准人 / Approved By", item.get("approved_by", "-")),
        ("上级批准时间 / Approved At", item.get("approved_at", "-")[:19] if item.get("approved_at") else "-"),
        ("最终批准人 / Final Approved By", item.get("final_approved_by", "-")),
        ("最终批准时间 / Final Approved At", item.get("final_approved_at", "-")[:19] if item.get("final_approved_at") else "-"),
    ]
    if item.get("reject_reason"):
        fields.append(("驳回理由 / Reject Reason", item.get("reject_reason", "")))
    if item.get("undo_comment"):
        fields.append(("撤销备注 / Undo Comment", item.get("undo_comment", "")))

    detail_rows = ""
    for label, value in fields:
        detail_rows += f"""<div class="detail-row">
            <div class="detail-label">{label}</div>
            <div class="detail-value">{value}</div>
        </div>"""

    # Recent audit log entries for this item
    logs = load_json_array(AUDIT_LOGS_PATH)
    item_logs = [l for l in logs if l.get("record_id") == item_id]
    item_logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
    log_rows = ""
    for l in item_logs[:10]:
        action_label = ACTION_LABELS.get(l.get("action", ""), l.get("action", ""))
        is_undo = l.get("action") == "undo"
        row_style = ' style="background:#fffbeb;"' if is_undo else ""
        log_rows += f"""<tr{row_style}>
            <td style="white-space:nowrap;">{l.get("timestamp", "")[:19]}</td>
            <td>{action_label}</td>
            <td>{l.get("user", "-")}</td>
            <td>{l.get("audit_id", "-")}</td>
        </tr>"""

    return PAGE_HEADER.format(title=f"审批详情 / {item_id}") + f"""
{flash_html}
<h1>审批详情 / Approval Detail: {item_id}</h1>
{undo_info}
<div class="card">
  <h2>基本信息 / Basic Info</h2>
  {detail_rows}
</div>
<div class="card">
  <h2>可用操作 / Available Actions</h2>
  <div class="actions">{action_buttons}</div>
</div>
{reject_form}
<div class="card">
  <h2>操作历史 / Action History <span class="helper-text">(最近10条 / Latest 10)</span></h2>
  <table>
    <tr><th>时间 / Time</th><th>操作 / Action</th><th>用户 / User</th><th>审计ID / Audit ID</th></tr>
    {log_rows if log_rows else '<tr><td colspan="4" style="text-align:center;color:var(--muted);">暂无记录 / No history</td></tr>'}
  </table>
  <div class="helper-text">审计日志保留所有操作记录，不可删除 / Audit logs preserve all actions and cannot be deleted.</div>
</div>
""" + PAGE_FOOTER


def render_new_approval_form(user: str) -> str:
    """Form to create a new approval item."""
    return PAGE_HEADER.format(title="新建审批 / New Approval") + """
<h1>新建审批 / New Approval Item</h1>
<div class="card">
  <form method="post" action="/approval-new">
    <div class="form-group">
      <label>主题 / Subject *</label>
      <input type="text" name="subject" placeholder="邮件主题 / Email subject..." required maxlength="200">
    </div>
    <div class="form-group">
      <label>邮件内容 / Email Body</label>
      <textarea name="body" rows="6" placeholder="邮件正文 / Email body content..."></textarea>
    </div>
    <div class="form-group">
      <label>收件人 / Recipient</label>
      <input type="text" name="recipient" placeholder="recipient@example.com">
    </div>
    <button type="submit" class="btn btn-primary">创建并保存为草稿 / Create as Draft</button>
    <a href="/approvals" class="btn btn-secondary">取消 / Cancel</a>
  </form>
</div>
""" + PAGE_FOOTER


def render_audit_logs(query_params: dict, user: str) -> str:
    """View all audit logs with optional filtering."""
    logs = load_json_array(AUDIT_LOGS_PATH)
    filter_item = query_params.get("item", [""])[0]

    if filter_item:
        logs = [l for l in logs if l.get("record_id") == filter_item]

    logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

    log_rows = ""
    for l in logs[:200]:  # Limit display to 200
        action_label = ACTION_LABELS.get(l.get("action", ""), l.get("action", ""))
        is_undo = l.get("action") == "undo"
        row_style = ' style="background:#fffbeb;"' if is_undo else ""
        undo_mark = " ↩️" if is_undo else ""
        log_rows += f"""<tr{row_style}>
            <td style="white-space:nowrap;">{l.get("timestamp", "")[:19]}</td>
            <td>{l.get("record_id", "-")}</td>
            <td>{action_label}{undo_mark}</td>
            <td>{l.get("user", "-")}</td>
            <td>{l.get("audit_id", "-")}</td>
        </tr>"""

    return PAGE_HEADER.format(title="审计日志 / Audit Logs") + f"""
<h1>审计日志 / Audit Logs</h1>
<div class="card">
  <form method="get" action="/audit-logs" style="margin-bottom:12px;">
    <label>按审批项过滤 / Filter by Item:</label>
    <div style="display:flex;gap:8px;align-items:center;">
      <input type="text" name="item" value="{filter_item}" placeholder="Item ID, e.g. EML-0001" style="max-width:260px;">
      <button type="submit" class="btn btn-primary btn-sm">过滤 / Filter</button>
      {f'<a href="/audit-logs" class="btn btn-secondary btn-sm">清除 / Clear</a>' if filter_item else ''}
    </div>
  </form>
  <table>
    <tr><th>时间 / Time</th><th>审批项 / Item</th><th>操作 / Action</th><th>用户 / User</th><th>审计ID / Audit ID</th></tr>
    {log_rows if log_rows else '<tr><td colspan="5" style="text-align:center;color:var(--muted);">暂无审计记录 / No audit records</td></tr>'}
  </table>
  <div class="helper-text">Showing latest {min(200, len(logs))} of {len(logs)} total audit entries. 审计日志仅可追加，不可删除。</div>
</div>
""" + PAGE_FOOTER


# ---------------------------------------------------------------------------
# HTTP Request Handler
# ---------------------------------------------------------------------------

class ApprovalHandler(BaseHTTPRequestHandler):
    """HTTP request handler for the approval workflow server."""

    ACTOR = "admin@tactokyo.local"

    def log_message(self, format, *args):
        """Override to add timestamp."""
        print(f"[{now_iso()}] {self.client_address[0]} - {format % args}")

    def _send_html(self, html: str, status: int = 200):
        """Send an HTML response."""
        body = html.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _redirect(self, location: str):
        """Send a 302 redirect."""
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def _get_user(self) -> str:
        """Resolve current user from request context."""
        # Simplified: use a fixed actor; in production this would parse auth headers/session
        return self.ACTOR

    # --- GET ---

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        user = self._get_user()

        # Remove trailing slash (except root)
        if path != "/" and path.endswith("/"):
            path = path.rstrip("/")

        try:
            if path == "/":
                self._send_html(render_dashboard(user))
            elif path == "/approvals":
                self._send_html(render_approval_list(query, user))
            elif path == "/audit-logs":
                self._send_html(render_audit_logs(query, user))
            elif path == "/approval-new":
                self._send_html(render_new_approval_form(user))
            elif path.startswith("/approvals/") and not any(
                    seg in path for seg in ["/submit", "/hr-review",
                                             "/manager-approve", "/final-approve",
                                             "/reject", "/undo", "/resubmit"]):
                # Detail view: /approvals/{item_id}
                parts = [p for p in path.split("/") if p]
                if len(parts) == 2:
                    item_id = unquote(parts[1])
                    self._send_html(render_approval_detail(item_id, user))
                else:
                    self.send_error(404, "Not found")
            else:
                self.send_error(404, "Not found")
        except Exception as e:
            self._send_html(
                PAGE_HEADER.format(title="Error") +
                f'<h1>Error</h1><div class="flash flash-error">{e}</div>' +
                PAGE_FOOTER,
                status=500,
            )

    # --- POST ---

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        user = self._get_user()

        # Read body
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length else ""
        params = parse_json_body(body)
        comment = params.get("comment", "").strip()

        try:
            # Create new approval item
            if path == "/approval-new":
                items = load_approval_items()
                item_id = next_sequence(items, "item_id", "EML-")
                now = now_iso()
                new_item = {
                    "item_id": item_id,
                    "subject": params.get("subject", "").strip(),
                    "body": params.get("body", "").strip(),
                    "recipient": params.get("recipient", "").strip(),
                    "status": "Draft",
                    "created_at": now,
                    "updated_at": now,
                    "created_by": user,
                    "submitted_by": "",
                    "submitted_at": "",
                    "reviewed_by": "",
                    "reviewed_at": "",
                    "approved_by": "",
                    "approved_at": "",
                    "final_approved_by": "",
                    "final_approved_at": "",
                    "rejected_by": "",
                    "rejected_at": "",
                    "reject_reason": "",
                    "resubmitted_by": "",
                    "resubmitted_at": "",
                    "undo_comment": "",
                }
                items.append(new_item)
                save_approval_items(items)
                append_audit_log(
                    module="approval.email_draft",
                    record_id=item_id,
                    action="create",
                    before_value=None,
                    after_value=dict(new_item),
                    user=user,
                )
                self._redirect(f"/approvals/{quote(item_id)}")

            # State transition actions: /approvals/{item_id}/{action}
            elif path.startswith("/approvals/") and "/" in path[12:]:
                parts = [p for p in path.split("/") if p]
                if len(parts) >= 3:
                    item_id = unquote(parts[1])
                    action = parts[2].replace("-", "_")  # normalize URL hyphens → underscores
                    try:
                        updated, audit = execute_transition(item_id, action, user, comment)
                        flash_msg = f"操作成功 / Action '{ACTION_LABELS.get(action, action)}' completed. → {STATUS_LABELS.get(updated['status'], updated['status'])}"
                        flash_type = "success"
                    except ValueError as e:
                        flash_msg = f"操作失败 / Failed: {e}"
                        flash_type = "error"
                    self._send_html(render_approval_detail(
                        item_id, user, flash_msg, flash_type,
                    ))
                else:
                    self.send_error(404, "Not found")
            else:
                self.send_error(404, "Not found")
        except Exception as e:
            self._send_html(
                PAGE_HEADER.format(title="Error") +
                f'<h1>Error</h1><div class="flash flash-error">{e}</div>' +
                PAGE_FOOTER,
                status=500,
            )


# ---------------------------------------------------------------------------
# Seed data
# ---------------------------------------------------------------------------

def seed_demo_data():
    """Create demo approval items if the database is empty."""
    items = load_approval_items()
    if items:
        return  # Already has data

    user = "admin@tactokyo.local"
    now = now_iso()

    demo_items = [
        {
            "item_id": "EML-0001",
            "subject": "Welcome onboard — Tanaka Taro",
            "body": "Dear Tanaka-san,\n\nWelcome to TAC! Please find your onboarding instructions below...\n\nBest regards,\nTAC HR",
            "recipient": "tanaka.taro@example.com",
            "status": "HR_Reviewed",
            "created_at": now,
            "updated_at": now,
            "created_by": user,
            "submitted_by": user,
            "submitted_at": now,
            "reviewed_by": "hr_admin",
            "reviewed_at": now,
            "approved_by": "",
            "approved_at": "",
            "final_approved_by": "",
            "final_approved_at": "",
            "rejected_by": "",
            "rejected_at": "",
            "reject_reason": "",
            "resubmitted_by": "",
            "resubmitted_at": "",
            "undo_comment": "",
        },
        {
            "item_id": "EML-0002",
            "subject": "Timesheet reminder — June 2026",
            "body": "Dear all,\n\nThis is a reminder to submit your timesheet for June 2026 by the 5th of July.\n\nThank you,\nTAC HR",
            "recipient": "all-employees@tactokyo.com",
            "status": "Draft",
            "created_at": now,
            "updated_at": now,
            "created_by": user,
            "submitted_by": "",
            "submitted_at": "",
            "reviewed_by": "",
            "reviewed_at": "",
            "approved_by": "",
            "approved_at": "",
            "final_approved_by": "",
            "final_approved_at": "",
            "rejected_by": "",
            "rejected_at": "",
            "reject_reason": "",
            "resubmitted_by": "",
            "resubmitted_at": "",
            "undo_comment": "",
        },
        {
            "item_id": "EML-0003",
            "subject": "Reimbursement policy update notification",
            "body": "Dear employees,\n\nPlease be informed that the reimbursement policy has been updated effective July 2026...\n\nRegards,\nFinance Team",
            "recipient": "all-employees@tactokyo.com",
            "status": "Final_Approved",
            "created_at": now,
            "updated_at": now,
            "created_by": user,
            "submitted_by": user,
            "submitted_at": now,
            "reviewed_by": "hr_admin",
            "reviewed_at": now,
            "approved_by": "manager_suzuki",
            "approved_at": now,
            "final_approved_by": "director_kato",
            "final_approved_at": now,
            "rejected_by": "",
            "rejected_at": "",
            "reject_reason": "",
            "resubmitted_by": "",
            "resubmitted_at": "",
            "undo_comment": "",
        },
    ]
    save_approval_items(demo_items)

    # Create audit log entries for demo data
    for item in demo_items:
        item_id = item["item_id"]
        status = item["status"]

        # Creation audit
        append_audit_log(
            "approval.email_draft", item_id, "create",
            None, dict(item), user,
        )

        # If status progressed beyond Draft, add those audit entries
        if status in {"Submitted", "HR_Reviewed", "Manager_Approved", "Final_Approved"}:
            draft_snapshot = dict(item)
            draft_snapshot["status"] = "Draft"
            draft_snapshot["submitted_by"] = ""
            draft_snapshot["submitted_at"] = ""
            append_audit_log(
                "approval.email_draft", item_id, "submit",
                draft_snapshot, dict(item), user, undoable=True,
            )

        if status in {"HR_Reviewed", "Manager_Approved", "Final_Approved"}:
            submitted_snapshot = dict(item)
            submitted_snapshot["status"] = "Submitted"
            submitted_snapshot["reviewed_by"] = ""
            submitted_snapshot["reviewed_at"] = ""
            append_audit_log(
                "approval.email_draft", item_id, "hr_review",
                submitted_snapshot, dict(item), "hr_admin", undoable=True,
            )

        if status in {"Manager_Approved", "Final_Approved"}:
            hr_snapshot = dict(item)
            hr_snapshot["status"] = "HR_Reviewed"
            hr_snapshot["approved_by"] = ""
            hr_snapshot["approved_at"] = ""
            append_audit_log(
                "approval.email_draft", item_id, "manager_approve",
                hr_snapshot, dict(item), "manager_suzuki", undoable=True,
            )

        if status == "Final_Approved":
            mgr_snapshot = dict(item)
            mgr_snapshot["status"] = "Manager_Approved"
            mgr_snapshot["final_approved_by"] = ""
            mgr_snapshot["final_approved_at"] = ""
            append_audit_log(
                "approval.email_draft", item_id, "final_approve",
                mgr_snapshot, dict(item), "director_kato", undoable=True,
            )

    print(f"[seed] Created {len(demo_items)} demo approval items with audit trail.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="TAC Tokyo Mail — Approval Workflow Server")
    parser.add_argument("--host", default="127.0.0.1", help="Bind address")
    parser.add_argument("--port", type=int, default=8006, help="Bind port")
    args = parser.parse_args()

    # Ensure database directory and seed demo data
    ensure_database()
    seed_demo_data()

    server = HTTPServer((args.host, args.port), ApprovalHandler)
    print(f"[server] TAC Tokyo Mail — Approval Workflow")
    print(f"[server] Listening on http://{args.host}:{args.port}")
    print(f"[server] Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[server] Shutting down.")
        server.shutdown()


if __name__ == "__main__":
    main()
