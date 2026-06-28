#!/usr/bin/env python3
"""TACAI Message Center — Approval Workflow engine (Phase B).

Zero-dependency workflow state machine, template management, delegation,
and CSV export. Called from app.py route handlers.
"""

from __future__ import annotations

import csv
import io
import json
import re
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

# Import shared utilities from the main module (lazy to avoid circular)
# The route handlers pass the required functions as needed.

# ---------------------------------------------------------------------------
# Workflow translations (appended to TRANSLATIONS dict in app.py)
# ---------------------------------------------------------------------------
WF_TRANSLATIONS = {
    "zh": {
        "wf.title": "审批工作流",
        "wf.list_title": "工作流列表",
        "wf.new_title": "新建工作流",
        "wf.detail_title": "工作流详情",
        "wf.col_id": "ID",
        "wf.col_name": "名称",
        "wf.col_type": "业务类型",
        "wf.col_initiator": "发起人",
        "wf.col_status": "状态",
        "wf.col_step": "当前步骤",
        "wf.col_created": "创建时间",
        "wf.col_amount": "金额",
        "wf.col_actions": "操作",
        "wf.status.pending": "待处理",
        "wf.status.processing": "处理中",
        "wf.status.approved": "已通过",
        "wf.status.rejected": "已驳回",
        "wf.status.cancelled": "已取消",
        "wf.status.expired": "已过期",
        "wf.step_status.pending": "待审批",
        "wf.step_status.processing": "审批中",
        "wf.step_status.approved": "已同意",
        "wf.step_status.rejected": "已驳回",
        "wf.step_status.escalated": "已升级",
        "wf.step_status.timeout": "已超时",
        "wf.step_status.skipped": "已跳过",
        "wf.action.approve": "同意",
        "wf.action.reject": "驳回",
        "wf.action.transfer": "转交",
        "wf.action.submit": "提交",
        "wf.comment_placeholder": "请输入审批意见",
        "wf.transfer_to": "转交给",
        "wf.no_records": "暂无工作流",
        "wf.step_timeline": "审批步骤时间线",
        "wf.current_step": "当前步骤",
        "wf.history": "操作历史",
        "wf.initiated_by": "发起人",
        "wf.no_template": "未找到匹配模板",
        "wf.batch_approve": "批量同意",
        "wf.batch_reject": "批量驳回",
        "wf.export_csv": "导出CSV",
        "wf.records_total": "共 {total} 条工作流",
        "wf.created_ok": "工作流已创建",
        "wf.approved_ok": "已同意",
        "wf.rejected_ok": "已驳回",
        "wf.transferred_ok": "已转交",
        "wf.batch_ok": "批量操作完成",
        "wft.title": "审批模板管理",
        "wft.new_title": "新建模板",
        "wft.edit_title": "编辑模板",
        "wft.col_name": "模板名称",
        "wft.col_biz_type": "业务类型",
        "wft.col_steps": "步骤数",
        "wft.col_status": "状态",
        "wft.step_name": "步骤名称",
        "wft.step_role": "审批角色",
        "wft.step_timeout": "超时(小时)",
        "wft.add_step": "添加步骤",
        "wft.remove_step": "删除",
        "wft.no_records": "暂无模板",
        "wft.saved_ok": "模板已保存",
        "del.title": "审批委托管理",
        "del.new_title": "新建委托",
        "del.delegator": "委托人",
        "del.delegate": "受托人",
        "del.biz_types": "业务类型",
        "del.date_range": "委托期间",
        "del.status": "状态",
        "del.reason": "原因",
        "del.active": "生效中",
        "del.expired": "已过期",
        "del.cancelled": "已取消",
        "del.no_records": "暂无委托",
        "del.cancel_btn": "取消委托",
        "del.all_types": "全部类型",
        "del.created_ok": "委托已创建",
        "del.cancelled_ok": "委托已取消",
    },
    "ja": {
        "wf.title": "承認ワークフロー",
        "wf.list_title": "ワークフロー一覧",
        "wf.new_title": "新規ワークフロー",
        "wf.detail_title": "ワークフロー詳細",
        "wf.col_id": "ID",
        "wf.col_name": "名称",
        "wf.col_type": "業務種類",
        "wf.col_initiator": "起案者",
        "wf.col_status": "ステータス",
        "wf.col_step": "現在のステップ",
        "wf.col_created": "作成日時",
        "wf.col_amount": "金額",
        "wf.col_actions": "操作",
        "wf.status.pending": "保留中",
        "wf.status.processing": "処理中",
        "wf.status.approved": "承認済",
        "wf.status.rejected": "却下",
        "wf.status.cancelled": "取消",
        "wf.status.expired": "期限切れ",
        "wf.step_status.pending": "承認待ち",
        "wf.step_status.processing": "承認中",
        "wf.step_status.approved": "承認済",
        "wf.step_status.rejected": "却下",
        "wf.step_status.escalated": "エスカレーション",
        "wf.step_status.timeout": "タイムアウト",
        "wf.step_status.skipped": "スキップ",
        "wf.action.approve": "承認",
        "wf.action.reject": "却下",
        "wf.action.transfer": "転送",
        "wf.action.submit": "提出",
        "wf.comment_placeholder": "承認コメントを入力",
        "wf.transfer_to": "転送先",
        "wf.no_records": "ワークフローがありません",
        "wf.step_timeline": "承認ステップタイムライン",
        "wf.current_step": "現在のステップ",
        "wf.history": "操作履歴",
        "wf.initiated_by": "起案者",
        "wf.no_template": "一致するテンプレートがありません",
        "wf.batch_approve": "一括承認",
        "wf.batch_reject": "一括却下",
        "wf.export_csv": "CSVエクスポート",
        "wf.records_total": "全{total}件",
        "wf.created_ok": "ワークフローを作成しました",
        "wf.approved_ok": "承認しました",
        "wf.rejected_ok": "却下しました",
        "wf.transferred_ok": "転送しました",
        "wf.batch_ok": "一括操作が完了しました",
        "wft.title": "承認テンプレート管理",
        "wft.new_title": "新規テンプレート",
        "wft.edit_title": "テンプレート編集",
        "wft.col_name": "テンプレート名",
        "wft.col_biz_type": "業務種類",
        "wft.col_steps": "ステップ数",
        "wft.col_status": "状態",
        "wft.step_name": "ステップ名",
        "wft.step_role": "承認ロール",
        "wft.step_timeout": "タイムアウト(時間)",
        "wft.add_step": "ステップ追加",
        "wft.remove_step": "削除",
        "wft.no_records": "テンプレートがありません",
        "wft.saved_ok": "テンプレートを保存しました",
        "del.title": "承認委任管理",
        "del.new_title": "新規委任",
        "del.delegator": "委任者",
        "del.delegate": "受任者",
        "del.biz_types": "業務種類",
        "del.date_range": "委任期間",
        "del.status": "状態",
        "del.reason": "理由",
        "del.active": "有効",
        "del.expired": "期限切れ",
        "del.cancelled": "取消済",
        "del.no_records": "委任がありません",
        "del.cancel_btn": "委任取消",
        "del.all_types": "すべて",
        "del.created_ok": "委任を作成しました",
        "del.cancelled_ok": "委任を取消しました",
    },
    "en": {
        "wf.title": "Approval Workflows",
        "wf.list_title": "Workflow List",
        "wf.new_title": "New Workflow",
        "wf.detail_title": "Workflow Detail",
        "wf.col_id": "ID",
        "wf.col_name": "Name",
        "wf.col_type": "Business Type",
        "wf.col_initiator": "Initiator",
        "wf.col_status": "Status",
        "wf.col_step": "Current Step",
        "wf.col_created": "Created",
        "wf.col_amount": "Amount",
        "wf.col_actions": "Actions",
        "wf.status.pending": "Pending",
        "wf.status.processing": "Processing",
        "wf.status.approved": "Approved",
        "wf.status.rejected": "Rejected",
        "wf.status.cancelled": "Cancelled",
        "wf.status.expired": "Expired",
        "wf.step_status.pending": "Pending",
        "wf.step_status.processing": "Processing",
        "wf.step_status.approved": "Approved",
        "wf.step_status.rejected": "Rejected",
        "wf.step_status.escalated": "Escalated",
        "wf.step_status.timeout": "Timeout",
        "wf.step_status.skipped": "Skipped",
        "wf.action.approve": "Approve",
        "wf.action.reject": "Reject",
        "wf.action.transfer": "Transfer",
        "wf.action.submit": "Submit",
        "wf.comment_placeholder": "Enter comment",
        "wf.transfer_to": "Transfer to",
        "wf.no_records": "No workflows",
        "wf.step_timeline": "Approval Step Timeline",
        "wf.current_step": "Current Step",
        "wf.history": "Action History",
        "wf.initiated_by": "Initiated by",
        "wf.no_template": "No matching template found",
        "wf.batch_approve": "Batch Approve",
        "wf.batch_reject": "Batch Reject",
        "wf.export_csv": "Export CSV",
        "wf.records_total": "{total} record(s) total",
        "wf.created_ok": "Workflow created",
        "wf.approved_ok": "Approved",
        "wf.rejected_ok": "Rejected",
        "wf.transferred_ok": "Transferred",
        "wf.batch_ok": "Batch operation completed",
        "wft.title": "Workflow Template Management",
        "wft.new_title": "New Template",
        "wft.edit_title": "Edit Template",
        "wft.col_name": "Template Name",
        "wft.col_biz_type": "Business Type",
        "wft.col_steps": "Steps",
        "wft.col_status": "Status",
        "wft.step_name": "Step Name",
        "wft.step_role": "Approver Role",
        "wft.step_timeout": "Timeout (hours)",
        "wft.add_step": "Add Step",
        "wft.remove_step": "Remove",
        "wft.no_records": "No templates",
        "wft.saved_ok": "Template saved",
        "del.title": "Approval Delegation",
        "del.new_title": "New Delegation",
        "del.delegator": "Delegator",
        "del.delegate": "Delegate",
        "del.biz_types": "Business Types",
        "del.date_range": "Date Range",
        "del.status": "Status",
        "del.reason": "Reason",
        "del.active": "Active",
        "del.expired": "Expired",
        "del.cancelled": "Cancelled",
        "del.no_records": "No delegations",
        "del.cancel_btn": "Cancel Delegation",
        "del.all_types": "All Types",
        "del.created_ok": "Delegation created",
        "del.cancelled_ok": "Delegation cancelled",
    },
}


# ---------------------------------------------------------------------------
# Workflow business logic
# ---------------------------------------------------------------------------
def tr_wf(lang: str, key: str) -> str:
    lang = lang if lang in ("zh", "ja", "en") else "zh"
    return WF_TRANSLATIONS.get(lang, WF_TRANSLATIONS["zh"]).get(key, key)


def find_template_by_biz_type(biz_type: str, templates: list[dict[str, Any]]) -> dict[str, Any] | None:
    matches = [t for t in templates if str(t.get("biz_type", "")) == biz_type and str(t.get("status", "active")).lower() == "active"]
    return matches[0] if matches else None


def resolve_approver_for_step(step_config: dict[str, Any], initiator_user_id: str,
                               users: list[dict[str, Any]], delegations: list[dict[str, Any]],
                               entity_id: str) -> str | None:
    """Resolve who should approve this step, considering delegations."""
    role = str(step_config.get("approver_role", "")).strip()
    # Find users with this role in the entity
    candidates = []
    for u in users:
        u_roles = {str(r).strip().lower() for r in u.get("roles", [])}
        u_entity = str(u.get("entity_id", "")).strip()
        if role in u_roles or "system_admin" in u_roles:
            if not entity_id or u_entity == entity_id or "system_admin" in u_roles:
                candidates.append(u)

    if not candidates:
        # Fallback: system admins
        for u in users:
            if "system_admin" in {str(r).strip().lower() for r in u.get("roles", [])}:
                candidates.append(u)

    if not candidates:
        return None

    approver = candidates[0]
    approver_id = str(approver.get("user_id", ""))

    # Check delegation
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    biz_type = str(step_config.get("biz_type", "")).strip()
    for d in delegations:
        if str(d.get("status", "")) != "active":
            continue
        if str(d.get("delegator_user_id", "")) != approver_id:
            continue
        if not (d.get("start_date", "") <= now_str <= d.get("end_date", "")):
            continue
        d_biz_types = d.get("biz_types", [])
        if d_biz_types and biz_type not in d_biz_types:
            continue
        return str(d.get("delegate_user_id", ""))
    return approver_id


def create_workflow(
    biz_type: str,
    biz_id: str,
    initiator_user_id: str,
    title: str = "",
    biz_amount: float = 0,
    entity_id: str = "",
    get_templates_fn=None,
    get_users_fn=None,
    get_delegations_fn=None,
    save_workflows_fn=None,
    save_steps_fn=None,
    save_records_fn=None,
    send_message_fn=None,
    next_seq_id_fn=None,
    now_iso_fn=None,
) -> dict[str, Any] | None:
    """Create a new workflow instance from template."""
    templates = get_templates_fn()
    template = find_template_by_biz_type(biz_type, templates)
    if not template:
        return None

    wf_rows = (save_workflows_fn.__self__ if hasattr(save_workflows_fn, '__self__') else None)
    # Build workflow record
    wf = {
        "wf_id": "",
        "wf_name": title or f"{biz_type} - {biz_id}",
        "template_id": str(template.get("template_id", "")),
        "template_name": str(template.get("template_name", "")),
        "initiator_user_id": initiator_user_id,
        "initiator_name": "",
        "entity_id": entity_id,
        "entity_code": entity_id,
        "status": "pending",
        "current_step": 0,
        "total_steps": len(template.get("steps", [])),
        "biz_type": biz_type,
        "biz_id": biz_id,
        "biz_summary": title,
        "biz_amount": biz_amount,
        "timeout_hours": DEFAULT_TIMEOUT_HOURS,
        "started_at": "",
        "completed_at": "",
        "expires_at": "",
        "created_by": initiator_user_id,
        "created_at": now_iso_fn(),
        "updated_at": now_iso_fn(),
    }
    return wf


# Default timeout
DEFAULT_TIMEOUT_HOURS = 48


def create_workflow_full(
    biz_type: str,
    biz_id: str,
    initiator_user_id: str,
    initiator_name: str,
    title: str = "",
    biz_amount: float = 0,
    entity_id: str = "",
    template_id: str = "",
    load_templates_fn=None, load_wf_fn=None,
    save_wf_fn=None, save_steps_fn=None,
    send_msg_fn=None,
) -> dict[str, Any]:
    """Full workflow creation — match template, create instance + steps, notify."""
    templates = load_templates_fn() if callable(load_templates_fn) else []

    # Find template
    template = None
    if template_id:
        for t in templates:
            if str(t.get("template_id", "")) == template_id:
                template = t
                break
    if not template:
        template = find_template_by_biz_type(biz_type, templates)
    if not template:
        raise ValueError(f"No matching template found for biz_type: {biz_type}")

    steps_config = template.get("steps", [])
    if not steps_config:
        raise ValueError("Template has no steps defined")

    total_steps = len(steps_config)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
    deadline = (datetime.now(timezone.utc) + timedelta(hours=DEFAULT_TIMEOUT_HOURS)).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # Generate WF ID
    wf_rows = load_wf_fn() if callable(load_wf_fn) else []
    # Use the app's sequence ID generator
    wf_id = f"WF-{datetime.now(timezone.utc).strftime('%Y%m')}-{_next_wf_num(wf_rows):04d}"

    wf = {
        "wf_id": wf_id,
        "wf_name": title or f"{biz_type.title()} - {biz_id}",
        "template_id": str(template.get("template_id", "")),
        "template_name": str(template.get("template_name", "")),
        "initiator_user_id": initiator_user_id,
        "initiator_name": initiator_name,
        "entity_id": entity_id,
        "entity_code": entity_id,
        "status": "processing",
        "current_step": 1,
        "total_steps": total_steps,
        "biz_type": biz_type,
        "biz_id": biz_id,
        "biz_summary": title,
        "biz_amount": biz_amount,
        "timeout_hours": DEFAULT_TIMEOUT_HOURS,
        "started_at": now,
        "completed_at": "",
        "expires_at": deadline,
        "created_by": initiator_user_id,
        "created_at": now,
        "updated_at": now,
    }
    wf_rows.append(wf)
    if callable(save_wf_fn):
        save_wf_fn(wf_rows)

    # Create steps
    new_steps = []
    for i, step_cfg in enumerate(steps_config):
        step_num = i + 1
        if step_num == 1:
            step_deadline = (datetime.now(timezone.utc) + timedelta(hours=int(step_cfg.get("timeout_hours", DEFAULT_TIMEOUT_HOURS)))).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        else:
            step_deadline = ""
        step = {
            "step_id": f"WFS-{datetime.now(timezone.utc).strftime('%Y%m')}-{_next_step_num(new_steps):04d}",
            "wf_id": wf_id,
            "step_number": step_num,
            "step_name": str(step_cfg.get("step_name", f"Step {step_num}")),
            "approver_role": str(step_cfg.get("approver_role", "")),
            "approver_user_id": "",
            "approver_name": "",
            "delegated_from_user_id": "",
            "delegated_from_name": "",
            "status": "processing" if step_num == 1 else "pending",
            "action": "",
            "comment": "",
            "acted_at": "",
            "timeout_hours": int(step_cfg.get("timeout_hours", DEFAULT_TIMEOUT_HOURS)),
            "deadline_at": step_deadline,
            "created_at": now,
            "updated_at": now,
        }
        new_steps.append(step)

    # Append new steps to existing and save
    if new_steps and callable(save_steps_fn):
        save_steps_fn(new_steps)

    # Try to send notification to first approver (if send_msg_fn available)
    if send_msg_fn:
        try:
            send_msg_fn(
                msg_type="workflow_approval",
                title=f"[Approval] {wf['wf_name']}",
                content=f"<p>A new approval request requires your action.</p><p><strong>{wf['wf_name']}</strong></p><p>Amount: ¥{biz_amount:,.0f}</p>",
                recipient_user_id="",  # Will be filled when approver resolved
                sender_user_id=initiator_user_id,
                priority="high" if biz_amount > 100000 else "normal",
                biz_type=biz_type,
                biz_id=biz_id,
                workflow_id=wf_id,
                action_buttons=[
                    {"label": "Approve", "action": "approve", "style": "primary"},
                    {"label": "Reject", "action": "reject", "style": "danger"},
                ],
            )
        except Exception:
            pass  # Notification is best-effort

    return wf


def _next_wf_num(rows: list[dict[str, Any]]) -> int:
    prefix = f"WF-{datetime.now(timezone.utc).strftime('%Y%m')}-"
    max_num = 0
    for r in rows:
        v = str(r.get("wf_id", ""))
        if v.startswith(prefix):
            try:
                max_num = max(max_num, int(v.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return max_num + 1


def _next_step_num(rows: list[dict[str, Any]]) -> int:
    prefix = f"WFS-{datetime.now(timezone.utc).strftime('%Y%m')}-"
    max_num = 0
    for r in rows:
        v = str(r.get("step_id", ""))
        if v.startswith(prefix):
            try:
                max_num = max(max_num, int(v.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return max_num + 1


def execute_workflow_action(
    wf_id: str,
    action: str,
    operator_user_id: str,
    operator_name: str,
    comment: str = "",
    transfer_to_user_id: str = "",
    get_workflows_fn=None, save_workflows_fn=None,
    get_steps_fn=None, save_steps_fn=None,
    get_records_fn=None, save_records_fn=None,
    send_msg_fn=None,
    now_iso_fn=None,
) -> dict[str, Any]:
    """Execute approve/reject/transfer on a workflow."""
    wf_rows = get_workflows_fn()
    wf = None
    for w in wf_rows:
        if str(w.get("wf_id", "")) == wf_id:
            wf = w
            break
    if not wf:
        raise ValueError("Workflow not found")
    if wf.get("status") in ("approved", "rejected", "cancelled", "expired"):
        raise ValueError(f"Workflow is already {wf['status']}")

    step_rows = get_steps_fn()
    wf_steps = sorted([s for s in step_rows if str(s.get("wf_id", "")) == wf_id], key=lambda s: s.get("step_number", 0))
    current_step_num = int(wf.get("current_step", 1))
    current_step = None
    for s in wf_steps:
        if s.get("step_number") == current_step_num:
            current_step = s
            break
    if not current_step:
        raise ValueError("Current step not found")

    now = now_iso_fn()

    if action == "approve":
        current_step["status"] = "approved"
        current_step["action"] = "approve"
        current_step["comment"] = comment
        current_step["acted_at"] = now
        current_step["updated_at"] = now

        # Record
        rec_rows = get_records_fn()
        rec_rows.append({
            "record_id": f"WFR-{datetime.now(timezone.utc).strftime('%Y%m')}-{_next_rec_num(rec_rows):04d}",
            "wf_id": wf_id,
            "step_id": current_step["step_id"],
            "step_number": current_step_num,
            "action": "approve",
            "actor_user_id": operator_user_id,
            "actor_name": operator_name,
            "comment": comment,
            "from_status": "processing",
            "to_status": "approved",
            "created_at": now,
        })
        save_records_fn(rec_rows)

        if current_step_num >= wf["total_steps"]:
            # All steps done
            wf["status"] = "approved"
            wf["completed_at"] = now
            wf["updated_at"] = now
            # Notify initiator
            if send_msg_fn:
                try:
                    send_msg_fn(
                        msg_type="notification",
                        title=f"Approved: {wf['wf_name']}",
                        content=f"<p>Your request has been approved.</p>",
                        recipient_user_id=str(wf.get("initiator_user_id", "")),
                        biz_type=str(wf.get("biz_type", "")),
                        biz_id=str(wf.get("biz_id", "")),
                        workflow_id=wf_id,
                    )
                except Exception:
                    pass
        else:
            # Advance to next step
            wf["current_step"] = current_step_num + 1
            wf["updated_at"] = now
            next_step = None
            for s in wf_steps:
                if s.get("step_number") == current_step_num + 1:
                    next_step = s
                    break
            if next_step:
                next_step["status"] = "processing"
                next_step["deadline_at"] = (datetime.now(timezone.utc) + timedelta(hours=int(next_step.get("timeout_hours", DEFAULT_TIMEOUT_HOURS)))).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                next_step["updated_at"] = now

    elif action == "reject":
        current_step["status"] = "rejected"
        current_step["action"] = "reject"
        current_step["comment"] = comment
        current_step["acted_at"] = now
        current_step["updated_at"] = now
        wf["status"] = "rejected"
        wf["completed_at"] = now
        wf["updated_at"] = now

        rec_rows = get_records_fn()
        rec_rows.append({
            "record_id": f"WFR-{datetime.now(timezone.utc).strftime('%Y%m')}-{_next_rec_num(rec_rows):04d}",
            "wf_id": wf_id,
            "step_id": current_step["step_id"],
            "step_number": current_step_num,
            "action": "reject",
            "actor_user_id": operator_user_id,
            "actor_name": operator_name,
            "comment": comment,
            "from_status": "processing",
            "to_status": "rejected",
            "created_at": now,
        })
        save_records_fn(rec_rows)

        if send_msg_fn:
            try:
                send_msg_fn(
                    msg_type="notification",
                    title=f"Rejected: {wf['wf_name']}",
                    content=f"<p>Your request was rejected.</p><p>Reason: {comment}</p>",
                    recipient_user_id=str(wf.get("initiator_user_id", "")),
                    biz_type=str(wf.get("biz_type", "")),
                    biz_id=str(wf.get("biz_id", "")),
                    workflow_id=wf_id,
                )
            except Exception:
                pass

    elif action == "transfer":
        if not transfer_to_user_id:
            raise ValueError("transfer_to_user_id is required for transfer action")
        old_approver = current_step.get("approver_user_id", "")
        current_step["approver_user_id"] = transfer_to_user_id
        current_step["approver_name"] = ""
        current_step["delegated_from_user_id"] = old_approver
        current_step["updated_at"] = now

        rec_rows = get_records_fn()
        rec_rows.append({
            "record_id": f"WFR-{datetime.now(timezone.utc).strftime('%Y%m')}-{_next_rec_num(rec_rows):04d}",
            "wf_id": wf_id,
            "step_id": current_step["step_id"],
            "step_number": current_step_num,
            "action": "transfer",
            "actor_user_id": operator_user_id,
            "actor_name": operator_name,
            "comment": f"Transferred from {old_approver} to {transfer_to_user_id}",
            "from_status": "processing",
            "to_status": "processing",
            "created_at": now,
        })
        save_records_fn(rec_rows)

    else:
        raise ValueError(f"Unknown action: {action}")

    # Save
    save_steps_fn(step_rows)
    save_workflows_fn(wf_rows)
    return wf


def _next_rec_num(rows: list[dict[str, Any]]) -> int:
    prefix = f"WFR-{datetime.now(timezone.utc).strftime('%Y%m')}-"
    max_num = 0
    for r in rows:
        v = str(r.get("record_id", ""))
        if v.startswith(prefix):
            try:
                max_num = max(max_num, int(v.rsplit("-", 1)[-1]))
            except ValueError:
                pass
    return max_num + 1


def check_workflow_timeouts(
    get_workflows_fn=None, get_steps_fn=None, save_steps_fn=None,
    get_records_fn=None, save_records_fn=None,
    send_msg_fn=None, find_supervisor_fn=None,
) -> int:
    """Scan for timed-out steps and escalate. Returns count of escalations."""
    now = datetime.now(timezone.utc)
    wf_rows = get_workflows_fn()
    step_rows = get_steps_fn()
    escalated = 0

    for wf in wf_rows:
        if wf.get("status") != "processing":
            continue
        wf_id = str(wf.get("wf_id", ""))
        wf_steps = [s for s in step_rows if str(s.get("wf_id", "")) == wf_id and s.get("status") == "processing"]
        for step in wf_steps:
            deadline_str = str(step.get("deadline_at", ""))
            if not deadline_str:
                continue
            try:
                deadline = datetime.fromisoformat(deadline_str.replace("Z", "+00:00"))
                if now > deadline:
                    step["status"] = "timeout"
                    step["updated_at"] = now.strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    # Extend deadline
                    step["deadline_at"] = (now + timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S+00:00")
                    step["status"] = "processing"  # Keep processing, but record timeout

                    # Record timeout
                    rec_rows = get_records_fn()
                    rec_rows.append({
                        "record_id": f"WFR-{now.strftime('%Y%m')}-{_next_rec_num(rec_rows):04d}",
                        "wf_id": wf_id,
                        "step_id": step["step_id"],
                        "step_number": step["step_number"],
                        "action": "timeout",
                        "actor_user_id": "SYSTEM",
                        "actor_name": "System",
                        "comment": f"Step timed out at {deadline_str}",
                        "from_status": "processing",
                        "to_status": "timeout",
                        "created_at": now.strftime("%Y-%m-%dT%H:%M:%S+00:00"),
                    })
                    save_records_fn(rec_rows)

                    # Notify supervisor
                    if send_msg_fn and find_supervisor_fn:
                        approver_id = str(step.get("approver_user_id", ""))
                        supervisor = find_supervisor_fn(approver_id)
                        if supervisor:
                            try:
                                send_msg_fn(
                                    msg_type="system",
                                    title=f"[Escalation] Approval timeout: {wf.get('wf_name', '')}",
                                    content=f"<p>Step {step['step_number']} has timed out.</p><p>Workflow: {wf.get('wf_name', '')}</p>",
                                    recipient_user_id=str(supervisor.get("user_id", "")),
                                    biz_type=str(wf.get("biz_type", "")),
                                    biz_id=str(wf.get("biz_id", "")),
                                    workflow_id=wf_id,
                                )
                            except Exception:
                                pass
                    escalated += 1
            except (ValueError, TypeError):
                continue

    if escalated:
        save_steps_fn(step_rows)
    return escalated


def export_workflows_csv(wf_rows: list[dict[str, Any]], step_rows: list[dict[str, Any]]) -> bytes:
    """Generate CSV export of workflow history."""
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["WF ID", "Name", "Type", "Initiator", "Status", "Current Step",
                      "Total Steps", "Amount", "Created", "Completed"])
    for w in sorted(wf_rows, key=lambda r: str(r.get("created_at", "")), reverse=True):
        writer.writerow([
            w.get("wf_id", ""),
            w.get("wf_name", ""),
            w.get("biz_type", ""),
            w.get("initiator_name", ""),
            w.get("status", ""),
            w.get("current_step", ""),
            w.get("total_steps", ""),
            w.get("biz_amount", 0),
            str(w.get("created_at", ""))[:19],
            str(w.get("completed_at", ""))[:19] if w.get("completed_at") else "",
        ])
    return output.getvalue().encode("utf-8-sig")


# ---------------------------------------------------------------------------
# HTML page builders for workflow
# ---------------------------------------------------------------------------
def breadcrumb_wf(lang: str, items: list[tuple[str, str]], url_with_lang_fn, h_fn, tr_fn) -> str:
    """Render breadcrumb navigation for workflow pages."""
    h = h_fn
    if not items:
        return ""
    parts = ['<nav class="breadcrumb" aria-label="Breadcrumb">']
    for i, (label, url) in enumerate(items):
        if i > 0:
            parts.append('<span class="separator">/</span>')
        if url:
            parts.append(f'<a href="{h(url_with_lang_fn(url, lang))}">{h(label)}</a>')
        else:
            parts.append(f'<span class="current">{h(label)}</span>')
    parts.append('</nav>')
    return "".join(parts)


def wf_list_html(user: dict[str, Any], lang: str, wf_rows: list[dict[str, Any]],
                 step_rows: list[dict[str, Any]], query_params: dict[str, list[str]],
                 url_with_lang_fn, h_fn, tr_fn) -> str:
    """Workflow list page with filters and table."""
    h = h_fn
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "wf.list_title"), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, "wf.list_title"))}</h2></div>'

    # Filter bar
    status_filter = (query_params.get("status", [""])[0] or "").strip()
    body += f'''<div class="panel" style="margin-bottom:16px">
  <form method="GET" action="{h(url_with_lang_fn("/workflows", lang))}" class="form-grid">
    <input type="hidden" name="lang" value="{h(lang)}">
    <div class="form-field"><label>Status</label>
      <select name="status">
        <option value="">All</option>
        {''.join(f'<option value="{s}" {"selected" if s==status_filter else ""}>{tr_wf(lang, f"wf.status.{s}")}</option>'
                 for s in ["pending","processing","approved","rejected","cancelled","expired"])}
      </select>
    </div>
    <div class="form-field" style="display:flex;align-items:flex-end"><button type="submit">Filter</button></div>
  </form>
</div>'''

    # Toolbar
    body += f'''<div class="sap-toolbar" style="justify-content:flex-start;margin-bottom:12px">
  <a class="button" href="{h(url_with_lang_fn("/workflows/new", lang))}">{h(tr_wf(lang, "wf.new_title"))}</a>
  <a class="button secondary" href="{h(url_with_lang_fn("/workflows/templates", lang))}">{h(tr_wf(lang, "wft.title"))}</a>
  <a class="button ghost" href="{h(url_with_lang_fn("/workflows/export", lang))}">{h(tr_wf(lang, "wf.export_csv"))}</a>
</div>'''

    # Apply filters
    filtered = [w for w in wf_rows]
    user_entity_id = str(user.get("entity_id", "") or user.get("entity_code", ""))
    roles = {str(r).strip().lower() for r in user.get("roles", [])}
    if "system_admin" not in roles and "*" not in set(user.get("permissions", [])):
        filtered = [w for w in filtered if str(w.get("entity_id", "")) == user_entity_id]
    if status_filter:
        filtered = [w for w in filtered if w.get("status") == status_filter]
    filtered.sort(key=lambda w: str(w.get("created_at", "")), reverse=True)

    if not filtered:
        body += f'<div class="message-strip">{h(tr_wf(lang, "wf.no_records"))}</div>'
    else:
        body += '<div class="table-scroll"><table><thead><tr>'
        for col in ["wf.col_id", "wf.col_name", "wf.col_type", "wf.col_initiator", "wf.col_status", "wf.col_step", "wf.col_created"]:
            body += f'<th>{h(tr_wf(lang, col))}</th>'
        body += '<th style="width:60px">Action</th></tr></thead><tbody>'

        for w in filtered[:100]:
            detail_url = url_with_lang_fn(f"/workflows/{w['wf_id']}", lang)
            body += f'''<tr>
  <td style="font-family:monospace">{h(w.get("wf_id",""))}</td>
  <td><a href="{h(detail_url)}" style="color:var(--tacai-primary);text-decoration:none;font-weight:800">{h(w.get("wf_name",""))}</a></td>
  <td>{h(w.get("biz_type",""))}</td>
  <td>{h(w.get("initiator_name",""))}</td>
  <td><span class="status-badge status-{h((w.get("status","") or "unknown").replace("_","-"))}">{h(tr_wf(lang, f"wf.status.{w.get('status','')}"))}</span></td>
  <td>{w.get("current_step",0)}/{w.get("total_steps",0)}</td>
  <td style="white-space:nowrap">{h(str(w.get("created_at",""))[:16])}</td>
  <td><a class="button ghost" href="{h(detail_url)}" style="padding:4px 8px;font-size:.82rem">View</a></td>
</tr>'''
        body += "</tbody></table></div>"
        body += f'<div class="helper-text">{h(tr_wf(lang, "wf.records_total").format(total=min(len(filtered), 100)))}</div>'

    return body


def wf_detail_html(user: dict[str, Any], lang: str, wf_id: str,
                   wf_rows: list[dict[str, Any]], step_rows: list[dict[str, Any]],
                   rec_rows: list[dict[str, Any]],
                   url_with_lang_fn, h_fn, tr_fn) -> str:
    """Workflow detail page with step timeline and action buttons."""
    h = h_fn
    wf = None
    for w in wf_rows:
        if str(w.get("wf_id", "")) == wf_id:
            wf = w
            break
    if not wf:
        return f'<div class="message-strip message-error">Workflow not found: {h(wf_id)}</div>'

    wf_steps = sorted([s for s in step_rows if str(s.get("wf_id", "")) == wf_id], key=lambda s: s.get("step_number", 0))
    wf_records = sorted([r for r in rec_rows if str(r.get("wf_id", "")) == wf_id], key=lambda r: str(r.get("created_at", "")), reverse=True)

    status = wf.get("status", "unknown")
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "wf.list_title"), "/workflows"), (wf_id, "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'''{bc}<div class="sap-page-header">
  <p class="eyebrow">{h(wf_id)}</p>
  <h2>{h(wf.get("wf_name",""))}</h2>
  <div class="sap-object-meta" style="display:flex;gap:16px;flex-wrap:wrap;margin-top:8px">
    <span><span class="status-badge status-{h(status.replace('_','-'))}">{h(tr_wf(lang, f"wf.status.{status}"))}</span></span>
    <span><strong>{h(tr_wf(lang, "wf.col_type"))}:</strong> {h(wf.get("biz_type",""))}</span>
    <span><strong>{h(tr_wf(lang, "wf.initiated_by"))}:</strong> {h(wf.get("initiator_name",""))}</span>
    <span><strong>{h(tr_wf(lang, "wf.col_amount"))}:</strong> ¥{h(f"{wf.get('biz_amount',0):,.0f}")}</span>
    <span><strong>{h(tr_wf(lang, "wf.col_created"))}:</strong> {h(str(wf.get("created_at",""))[:19])}</span>
  </div>
</div>'''

    # Step timeline
    body += f'<div class="card" style="margin-bottom:16px"><h3>{h(tr_wf(lang, "wf.step_timeline"))}</h3>'
    current_step_num = wf.get("current_step", 1)
    for step in wf_steps:
        step_status = step.get("status", "pending")
        is_current = step.get("step_number") == current_step_num
        icon = ""
        if step_status == "approved":
            icon = "✅"
        elif step_status == "rejected":
            icon = "❌"
        elif step_status == "processing":
            icon = "⏳"
        elif step_status == "pending":
            icon = "○"
        elif step_status == "timeout":
            icon = "⏰"
        elif step_status == "escalated":
            icon = "⬆️"
        css_class = "current" if is_current else step_status
        body += f'''<div class="step-timeline-item {css_class}">
  <div style="display:flex;justify-content:space-between;align-items:center">
    <strong>{icon} Step {step.get("step_number")}: {h(step.get("step_name",""))}</strong>
    <span class="status-badge status-{h(step_status.replace('_','-'))}">{h(tr_wf(lang, f"wf.step_status.{step_status}"))}</span>
  </div>
  <div class="muted" style="font-size:.84rem">Approver: {h(step.get("approver_name") or step.get("approver_user_id") or step.get("approver_role",""))}</div>
  {f'<div class="muted" style="font-size:.84rem">Comment: {h(step.get("comment",""))}</div>' if step.get("comment") else ""}
  {f'<div class="muted" style="font-size:.82rem">Deadline: {h(str(step.get("deadline_at",""))[:19])}</div>' if step.get("deadline_at") else ""}
</div>'''
    body += "</div>"

    # Action buttons (only if processing and user is approver)
    if status == "processing":
        current_step = None
        for s in wf_steps:
            if s.get("step_number") == current_step_num:
                current_step = s
                break
        if current_step:
            body += f'''<div class="card" style="margin-bottom:16px">
  <h3>{h(tr_wf(lang, "wf.current_step"))}</h3>
  <form method="POST" action="{h(url_with_lang_fn(f"/workflows/{wf_id}/action", lang))}" style="margin-top:12px">
    <input type="hidden" name="action" value="approve">
    <div class="form-field"><label>{h(tr_wf(lang, "wf.comment_placeholder"))}</label><textarea name="comment" rows="2"></textarea></div>
    <div class="actions">
      <button type="submit" class="button success">{h(tr_wf(lang, "wf.action.approve"))}</button>
      <button type="button" class="button danger" onclick="this.form.action.value='reject';this.form.submit()">{h(tr_wf(lang, "wf.action.reject"))}</button>
    </div>
  </form>
  <form method="POST" action="{h(url_with_lang_fn(f"/workflows/{wf_id}/action", lang))}" style="margin-top:8px">
    <input type="hidden" name="action" value="transfer">
    <div class="form-grid">
      <div class="form-field"><label>{h(tr_wf(lang, "wf.transfer_to"))}</label><input type="text" name="transfer_to" placeholder="User ID"></div>
      <div class="form-field" style="display:flex;align-items:flex-end"><button type="submit" class="button warning">{h(tr_wf(lang, "wf.action.transfer"))}</button></div>
    </div>
  </form>
</div>'''

    # History
    if wf_records:
        body += f'<div class="card"><h3>{h(tr_wf(lang, "wf.history"))}</h3>'
        body += '<div class="table-scroll"><table><thead><tr><th>Step</th><th>Action</th><th>Actor</th><th>Comment</th><th>Time</th></tr></thead><tbody>'
        for r in wf_records:
            body += f'<tr><td>{r.get("step_number","")}</td><td>{h(r.get("action",""))}</td><td>{h(r.get("actor_name",""))}</td><td>{h(r.get("comment","")[:80])}</td><td style="white-space:nowrap">{h(str(r.get("created_at",""))[:19])}</td></tr>'
        body += "</tbody></table></div></div>"

    return body


def wf_new_html(user: dict[str, Any], lang: str, templates: list[dict[str, Any]],
                url_with_lang_fn, h_fn, tr_fn) -> str:
    """New workflow creation form."""
    h = h_fn
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "wf.list_title"), "/workflows"), (tr_wf(lang, "wf.new_title"), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, "wf.new_title"))}</h2></div>'
    active_templates = [t for t in templates if str(t.get("status", "")).lower() == "active"]
    if not active_templates:
        body += f'<div class="message-strip message-warning">{h(tr_wf(lang, "wf.no_template"))}</div>'
        return body

    body += f'''<div class="card">
  <form method="POST" action="{h(url_with_lang_fn("/workflows/new", lang))}">
    <div class="form-grid">
      <div class="form-field"><label>Template / Biz Type</label>
        <select name="template_id">
          {''.join(f'<option value="{h(t.get("template_id",""))}">{h(t.get("template_name",""))} ({h(t.get("biz_type",""))})</option>' for t in active_templates)}
        </select>
      </div>
      <div class="form-field"><label>Business ID</label><input type="text" name="biz_id" placeholder="EXP-001" required></div>
      <div class="form-field"><label>Title</label><input type="text" name="title" placeholder="Approval request title" required></div>
      <div class="form-field"><label>Amount (JPY)</label><input type="number" name="amount" value="0" step="0.01"></div>
    </div>
    <div class="sap-toolbar"><button type="submit" class="button">{h(tr_wf(lang, "wf.action.submit"))}</button></div>
  </form>
</div>'''
    return body


def wft_list_html(user: dict[str, Any], lang: str, templates: list[dict[str, Any]],
                  url_with_lang_fn, h_fn, tr_fn) -> str:
    """Template management page."""
    h = h_fn
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "wft.title"), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, "wft.title"))}</h2></div>'
    body += f'<div class="sap-toolbar" style="justify-content:flex-start;margin-bottom:12px"><a class="button" href="{h(url_with_lang_fn("/workflows/templates/new", lang))}">{h(tr_wf(lang, "wft.new_title"))}</a></div>'
    if not templates:
        body += f'<div class="message-strip">{h(tr_wf(lang, "wft.no_records"))}</div>'
    else:
        body += '<div class="table-scroll"><table><thead><tr>'
        for col in ["wft.col_name", "wft.col_biz_type", "wft.col_steps", "wft.col_status"]:
            body += f'<th>{h(tr_wf(lang, col))}</th>'
        body += '<th>Action</th></tr></thead><tbody>'
        for t in sorted(templates, key=lambda r: str(r.get("template_name", ""))):
            edit_url = url_with_lang_fn(f"/workflows/templates/{t['template_id']}", lang)
            body += f'''<tr>
  <td><a href="{h(edit_url)}" style="color:var(--tacai-primary)">{h(t.get("template_name",""))}</a></td>
  <td>{h(t.get("biz_type",""))}</td>
  <td>{len(t.get("steps",[]))}</td>
  <td><span class="status-badge status-{h(str(t.get("status","active")).replace('_','-'))}">{h(t.get("status","active"))}</span></td>
  <td><a class="button ghost" href="{h(edit_url)}" style="padding:4px 8px;font-size:.82rem">Edit</a></td>
</tr>'''
        body += "</tbody></table></div>"
    return body


def wft_form_html(user: dict[str, Any], lang: str, template: dict[str, Any] | None,
                  url_with_lang_fn, h_fn, tr_fn) -> str:
    """Template create/edit form."""
    h = h_fn
    is_new = template is None
    title_key = "wft.new_title" if is_new else "wft.edit_title"
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "wft.title"), "/workflows/templates"), (tr_wf(lang, title_key), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, title_key))}</h2></div>'

    t = template or {"template_id": "", "template_name": "", "biz_type": "", "status": "active", "steps": []}
    steps = t.get("steps", [])
    action_url = url_with_lang_fn("/workflows/templates/new" if is_new else f"/workflows/templates/{t['template_id']}", lang)

    body += f'''<div class="card">
  <form method="POST" action="{h(action_url)}" id="template-form">
    {f'<input type="hidden" name="template_id" value="{h(t["template_id"])}">' if not is_new else ""}
    <div class="form-grid">
      <div class="form-field"><label>Template Name</label><input type="text" name="template_name" value="{h(t.get("template_name",""))}" required></div>
      <div class="form-field"><label>Business Type</label><input type="text" name="biz_type" value="{h(t.get("biz_type",""))}" placeholder="expense, leave, etc." required></div>
      <div class="form-field"><label>Status</label>
        <select name="status">
          <option value="active" {"selected" if t.get("status")=="active" else ""}>Active</option>
          <option value="inactive" {"selected" if t.get("status")=="inactive" else ""}>Inactive</option>
        </select>
      </div>
    </div>
    <h4 style="margin-top:20px">Steps</h4>
    <div id="steps-container">'''

    for i, step in enumerate(steps):
        body += f'''<div class="step-row">
  <div class="form-grid">
    <div class="form-field"><label>Step Name</label><input type="text" name="step_name_{i}" value="{h(step.get("step_name",""))}" required></div>
    <div class="form-field"><label>Approver Role</label><input type="text" name="step_role_{i}" value="{h(step.get("approver_role",""))}" placeholder="manager, finance, hr_manager" required></div>
    <div class="form-field"><label>Timeout (hours)</label><input type="number" name="step_timeout_{i}" value="{step.get("timeout_hours",48)}" min="1" max="720"></div>
  </div>
  <button type="button" class="button danger" onclick="this.parentElement.remove()" style="margin-top:4px;font-size:.82rem;padding:4px 10px">Remove Step</button>
</div>'''

    body += f'''</div>
    <button type="button" class="button secondary" onclick="addStep()" style="margin-top:8px">{h(tr_wf(lang, "wft.add_step"))}</button>
    <div class="sap-toolbar"><button type="submit" class="button">{h(tr_wf(lang, "common.save"))}</button></div>
  </form>
</div>
<script>
let stepCount = {len(steps)};
function addStep() {{
  const container = document.getElementById('steps-container');
  const div = document.createElement('div');
  div.className = 'step-row';
  div.innerHTML = '<div class="form-grid">' +
    '<div class="form-field"><label>Step Name</label><input type="text" name="step_name_' + stepCount + '" required></div>' +
    '<div class="form-field"><label>Approver Role</label><input type="text" name="step_role_' + stepCount + '" placeholder="manager" required></div>' +
    '<div class="form-field"><label>Timeout (hours)</label><input type="number" name="step_timeout_' + stepCount + '" value="48" min="1" max="720"></div>' +
    '</div>' +
    '<button type="button" class="button danger" onclick="this.parentElement.remove()" style="margin-top:4px;font-size:.82rem;padding:4px 10px">Remove Step</button>';
  container.appendChild(div);
  stepCount++;
}}
</script>'''
    return body


def delegations_html(user: dict[str, Any], lang: str, del_rows: list[dict[str, Any]],
                     url_with_lang_fn, h_fn, tr_fn) -> str:
    """Delegation management page."""
    h = h_fn
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "del.title"), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, "del.title"))}</h2></div>'
    body += f'<div class="sap-toolbar" style="justify-content:flex-start;margin-bottom:12px"><a class="button" href="{h(url_with_lang_fn("/delegations/new", lang))}">{h(tr_wf(lang, "del.new_title"))}</a></div>'

    active_dels = [d for d in del_rows if d.get("status") == "active"]
    expired_dels = [d for d in del_rows if d.get("status") != "active"]

    if not del_rows:
        body += f'<div class="message-strip">{h(tr_wf(lang, "del.no_records"))}</div>'
        return body

    if active_dels:
        body += f'<h4>{h(tr_wf(lang, "del.active"))} ({len(active_dels)})</h4>'
        body += '<div class="table-scroll"><table><thead><tr><th>Delegator</th><th>Delegate</th><th>Biz Types</th><th>Dates</th><th>Reason</th><th>Action</th></tr></thead><tbody>'
        for d in active_dels:
            cancel_url = url_with_lang_fn(f"/delegations/{d['delegation_id']}/cancel", lang)
            body += f'''<tr>
  <td>{h(d.get("delegator_name",""))}</td>
  <td>{h(d.get("delegate_name",""))}</td>
  <td>{h(", ".join(d.get("biz_types",[])) or tr_wf(lang,"del.all_types"))}</td>
  <td>{h(d.get("start_date",""))} ~ {h(d.get("end_date",""))}</td>
  <td>{h(d.get("reason",""))}</td>
  <td><form method="POST" action="{h(cancel_url)}" style="display:inline"><button type="submit" class="button danger" style="font-size:.82rem;padding:4px 8px">{h(tr_wf(lang, "del.cancel_btn"))}</button></form></td>
</tr>'''
        body += "</tbody></table></div>"
    return body


def delegation_new_html(user: dict[str, Any], lang: str,
                        url_with_lang_fn, h_fn, tr_fn) -> str:
    """New delegation form."""
    h = h_fn
    bc = breadcrumb_wf(lang, [(tr_fn(lang, "nav.dashboard"), "/dashboard"), (tr_wf(lang, "del.title"), "/delegations"), (tr_wf(lang, "del.new_title"), "")], url_with_lang_fn, h_fn, tr_fn)
    body = f'{bc}<div class="sap-page-header"><h2>{h(tr_wf(lang, "del.new_title"))}</h2></div>'
    body += f'''<div class="card">
  <form method="POST" action="{h(url_with_lang_fn("/delegations/new", lang))}">
    <div class="form-grid">
      <div class="form-field"><label>{h(tr_wf(lang, "del.delegate"))} (User ID)</label><input type="text" name="delegate_id" required></div>
      <div class="form-field"><label>Start Date</label><input type="date" name="start_date" required></div>
      <div class="form-field"><label>End Date</label><input type="date" name="end_date" required></div>
      <div class="form-field"><label>{h(tr_wf(lang, "del.reason"))}</label><input type="text" name="reason" placeholder="Annual leave / Business trip"></div>
    </div>
    <div class="sap-toolbar"><button type="submit" class="button">{h(tr_wf(lang, "common.create"))}</button></div>
  </form>
</div>'''
    return body
