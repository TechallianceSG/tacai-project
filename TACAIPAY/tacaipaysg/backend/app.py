"""TACAI Pay SG - Singapore payroll MVP.

Dependency-free local web app for Singapore monthly payroll operations.
It follows the existing TACAI local app pattern: Python standard library only,
JSON storage, SAP/Fiori-inspired server-rendered UI, trilingual labels, audit logs.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import smtplib
import ssl
from calendar import monthrange
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formataddr
from html import escape
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO, StringIO
from pathlib import Path
from fpdf import FPDF
from typing import Any
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

# === PostgreSQL integration ===
import sys as _sys, os as _os
from pathlib import Path as _Path
_pg_project_root = _Path(_os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))))
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
DATABASE_DIR = ROOT_DIR / "database"
I18N_DIR = ROOT_DIR / "i18n"
PAYSLIP_DIR = ROOT_DIR / "payslips"
UNICODE_FONT_PATH = "/Library/Fonts/Arial Unicode.ttf"  # CJK + Latin support
SALARY_MASTER_PATH = DATABASE_DIR / "salary_master.json"
PAYROLL_BATCHES_PATH = DATABASE_DIR / "payroll_batches.json"
PAYROLL_RECORDS_PATH = DATABASE_DIR / "payroll_records_sg.json"
PAYROLL_PARAMETERS_PATH = DATABASE_DIR / "payroll_parameters.json"
PAYSLIPS_PATH = DATABASE_DIR / "payslips.json"
EMAIL_DELIVERIES_PATH = DATABASE_DIR / "payslip_email_deliveries.json"
AUDIT_LOGS_PATH = DATABASE_DIR / "audit_logs.json"
MONTHLY_SHEETS_PATH = DATABASE_DIR / "monthly_salary_sheets.json"
MONTHLY_RECORDS_PATH = DATABASE_DIR / "monthly_salary_records.json"
PAYROLL_CALENDAR_PATH = DATABASE_DIR / "payroll_calendar.json"
PAYROLL_RELEASE_BATCHES_PATH = DATABASE_DIR / "payroll_release_batches.json"
PAYROLL_LEDGER_PATH = DATABASE_DIR / "payroll_ledger.json"
ACTUARIAL_SHEETS_PATH = DATABASE_DIR / "actuarial_sheets.json"
ACTUARIAL_RECORDS_PATH = DATABASE_DIR / "actuarial_records.json"
ENTITIES_MASTER_PATH = ROOT_DIR.parent.parent / "TACAI-Core" / "masterdata" / "database" / "entities.json"
MASTERDATA_ENTITIES_PATH = ROOT_DIR.parent.parent / "TACAI-Core" / "masterdata" / "database" / "entities.json"

DEFAULT_LANG = "zh"
SUPPORTED_LANGS = {"zh", "ja", "en"}
DEFAULT_PORT = 8016
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
REQUIRED_MODULE_PERMISSION = "tacaipay_sg.access"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"


def _resolve_host(request_host: str | None = None) -> str:
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        return "127.0.0.1"
    return TACAI_PUBLIC_HOST


def resolve_portal_url(request_host: str | None = None, default_portal_url: str | None = None) -> str:
    from urllib.parse import urlparse as _urlparse
    portal = default_portal_url or PORTAL_BASE_URL
    if request_host and request_host in {"127.0.0.1", "localhost"}:
        parsed = _urlparse(portal)
        port = parsed.port or 3000
        return f"http://127.0.0.1:{port}{parsed.path if parsed.path else ''}"
    return portal


TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
MAX_POST_BYTES = 16 * 1024 * 1024  # 16MB for file uploads (Excel, PDF)
MAX_POST_FORM_BYTES = 2 * 1024 * 1024  # 2MB for regular form POSTs
EMPLOYEEADMIN_BASE_URL = (os.environ.get("EMPLOYEEADMIN_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8004").strip() or f"http://{TACAI_PUBLIC_HOST}:8004").rstrip("/")
EMPLOYEEADMIN_INTERNAL_BASE_URL = (os.environ.get("EMPLOYEEADMIN_INTERNAL_BASE_URL", EMPLOYEEADMIN_BASE_URL.replace(TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST, 1)).strip() or EMPLOYEEADMIN_BASE_URL).rstrip("/")
APP_BASE_URL = (os.environ.get("TACAIPAYSG_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:{DEFAULT_PORT}").strip() or f"http://{TACAI_PUBLIC_HOST}:{DEFAULT_PORT}").rstrip("/")
PORTAL_BASE_URL = (os.environ.get("TACAI_PORTAL_BASE_URL") or os.environ.get("PORTAL_BASE_URL") or f"http://{TACAI_PUBLIC_HOST}:8005").strip().rstrip("/")
USER_ADMIN_BASE_URL = (os.environ.get("USER_ADMIN_PUBLIC_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8006").strip() or f"http://{TACAI_PUBLIC_HOST}:8006").rstrip("/")
USER_ADMIN_INTERNAL_BASE_URL = (os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", f"http://{TACAI_INTERNAL_HOST}:8006").strip() or f"http://{TACAI_INTERNAL_HOST}:8006").rstrip("/")
USER_ACTOR = os.environ.get("TACAIPAYSG_ACTOR", "HR Payroll Admin").strip() or "HR Payroll Admin"

# Message Center integration
TACAIMSG_INTERNAL_BASE_URL = (os.environ.get("TACAIMSG_INTERNAL_BASE_URL", f"http://{TACAI_INTERNAL_HOST}:8012").strip() or f"http://{TACAI_INTERNAL_HOST}:8012").rstrip("/")
TACAIMSG_INTERNAL_TOKEN = os.environ.get("TACAIMSG_INTERNAL_TOKEN", "tacai-internal-token").strip()
TAC_PAYSG_MSG_CENTER_ENABLED = os.environ.get("TAC_PAYSG_MSG_CENTER_ENABLED", "1").strip().lower() not in {"0", "false", "no", "off"}

SMTP_HOST = os.environ.get("PAYSLIP_SMTP_HOST", "").strip()
SMTP_PORT = int(os.environ.get("PAYSLIP_SMTP_PORT", "587") or "587")
SMTP_USERNAME = os.environ.get("PAYSLIP_SMTP_USERNAME", "").strip()
SMTP_PASSWORD = os.environ.get("PAYSLIP_SMTP_PASSWORD", "")
SMTP_USE_TLS = os.environ.get("PAYSLIP_SMTP_USE_TLS", "1").strip().lower() not in {"0", "false", "no", "off"}
PAYSLIP_SENDER = os.environ.get("PAYSLIP_EMAIL_SENDER", "hradmin@tacjob.com").strip() or "hradmin@tacjob.com"
PAYSLIP_SENDER_NAME = os.environ.get("PAYSLIP_EMAIL_SENDER_NAME", "TAC Payroll SG").strip() or "TAC Payroll SG"
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

BATCH_STATUSES = [
    "draft",
    "calculated",
    "hr_reviewed",
    "approved",
    "finalized",
    "payslips_generated",
    "sent_to_employees",
    "employee_confirmed",
    "released_to_finance",
    "paid",
    "correction",
    "voided",
]
LOCKED_BATCH_STATUSES = {"approved", "finalized", "payslips_generated", "sent_to_employees", "employee_confirmed", "released_to_finance", "paid"}
SHEET_STATUSES = [
    "draft",
    "hr_confirmed",
    "calculated",
    "hr_reviewed",
    "manager_review",
    "finalized",
    "correction",
    "voided",
]
RECORD_STATUSES = ["draft", "hr_confirmed", "calculated", "hr_adjusted"]
RELEASE_STATUSES = [
    "pending_release",     # 待发放
    "payslips_generated",  # 工资单已生成
    "hr_confirmed",        # HR已确认工资单
    "email_draft_prepared",# 邮件草稿已准备
    "sending",             # 发送中
    "sent",                # 已发送
    "partially_sent",      # 部分发送（有失败）
    "paid",                # 已发放
]
SUPPORTED_CURRENCIES = ["SGD", "USD", "CNY", "INR", "TWD", "JPY"]
CURRENCY_LABELS = {
    "SGD": {"zh": "SGD - 新加坡元", "en": "SGD - Singapore Dollar", "ja": "SGD - シンガポールドル"},
    "USD": {"zh": "USD - 美元", "en": "USD - US Dollar", "ja": "USD - 米ドル"},
    "CNY": {"zh": "CNY - 人民币", "en": "CNY - Chinese Yuan", "ja": "CNY - 中国人民元"},
    "INR": {"zh": "INR - 印度卢比", "en": "INR - Indian Rupee", "ja": "INR - インドルピー"},
    "TWD": {"zh": "TWD - 新台币", "en": "TWD - Taiwan Dollar", "ja": "TWD - ニュー台湾ドル"},
    "JPY": {"zh": "JPY - 日元", "en": "JPY - Japanese Yen", "ja": "JPY - 日本円"},
}
SALARY_TYPES = {"monthly", "hourly", "daily", "monthly_hour"}
# Fields that only apply to hourly / monthly_hour types
HOURLY_TYPE_FIELDS = {"hourly", "monthly_hour"}
CPF_MODES = {"manual", "parameter_assisted"}

# ── Attendance field edit control by salary type ──
ATTENDANCE_FIELD_KEYS = {
    "actual_work_days", "actual_work_hours", "paid_leave_days",
    "unpaid_leave_days", "overtime_hours", "late_night_hours",
    "holiday_hours", "absence_days", "sick_leave_days", "standard_work_days",
    "standard_work_hours",
}

def attendance_editable_fields(salary_type: str) -> set[str]:
    """Return the set of attendance field keys editable for this salary type.
    - monthly: work days + all leave fields are editable
    - daily: work days only (leave fields are reference)
    - hourly / monthly_hour: work hours only (leave fields are reference)
    """
    if salary_type == "monthly":
        return {"actual_work_days", "paid_leave_days", "unpaid_leave_days", "sick_leave_days"}
    if salary_type == "daily":
        return {"actual_work_days"}
    # hourly, monthly_hour
    return {"actual_work_hours"}

# Backward-compat alias used by some callers
def attendance_editable_field(salary_type: str) -> str:
    """Return a single editable field for legacy callers."""
    if salary_type in ("hourly", "monthly_hour"):
        return "actual_work_hours"
    return "actual_work_days"


def attendance_input_attrs(field_key: str, salary_type: str, base_locked: bool) -> str:
    """Return HTML attribute string for an attendance field input.
    - If field is in the editable set for this salary type: no readonly, yellow highlight
    - Otherwise: readonly (disabled), gray background
    - base_locked: True if sheet is locked, overrides everything to readonly
    """
    if base_locked:
        return "readonly"
    editable = attendance_editable_fields(salary_type)
    if field_key in editable:
        return 'style="background:#FFFDE7;font-weight:600;border-color:#F9A825"'
    else:
        return 'readonly style="background:#F5F5F5;color:#BDBDBD;cursor:not-allowed"'

TRANSLATIONS = {
    "zh": {
        "app.title": "TACAI Pay SG 新加坡薪资",
        "nav.dashboard": "仪表盘",
        "nav.master": "薪资主数据",
        "nav.batches": "员工工资发放",
        "nav.actuarial": "工资精算",
        "nav.reports": "报表",
        "nav.parameters": "参数",
        "nav.audit": "审计",
        "action.save": "保存",
        "action.cancel": "取消",
        "action.create": "创建",
        "action.create_salary_master": "创建主薪资记录",
        "action.modify": "审核修改",
        "action.import_sg": "从 EmployeeAdmin 导入 SG 员工",
        "action.generate": "创建发放批次",
        "action.calculate": "启动工资计算",
        "action.hr_review": "HR 审核通过",
        "action.approve": "下一级审批通过",
        "action.finalize": "批准定案",
        "action.approve_finalize": "批准定案",
        "action.payslips": "生成工资单 PDF",
        "action.email": "发送邮件",
        "action.employee_confirm": "员工确认完成/无回复自动确认",
        "action.finance": "提交财务",
        "action.paid": "标记已发放",
        "action.void": "作废此工资表",
        "action.load_employees": "加载员工",
        "action.calculate_selected": "计算选中",
        "action.calculate_all": "全部计算",
        "action.save_all": "保存全部",
        "label.employee": "员工",
        "label.month": "工资月份",
        "label.entity": "法人实体代码",
        "label.status": "状态",
        "label.country": "国家",
        "label.salary_type": "薪资类型",
        "label.basic_salary": "基本薪资",
        "label.hourly_rate": "小时工资",
        "label.daily_rate": "日工资",
        "label.work_days": "出勤天数",
        "label.work_hours": "出勤小时",
        "label.gross": "应发工资",
        "label.deductions": "扣除合计",
        "label.net": "实发工资",
        "label.employer_cost": "雇主成本",
        "label.cpf_employee": "员工 CPF",
        "label.cpf_employer": "雇主 CPF",
        "label.sdl": "技能发展税 SDL",
        "label.fwl": "外籍劳工税 FWL",
        "label.other_deduction": "其他扣除",
        "label.income_tax": "所得税/预扣",
        "label.allowance": "津贴",
        "label.bonus": "奖金/追加支付",
        "label.performance_bonus": "月度绩效工资",
        "label.performance_reference": "绩效参考",
        "label.department": "部门",
        "label.team": "团队",
        "label.all": "全部",
        "label.email": "邮箱",
        "label.bank": "银行信息",
        "label.bank_branch_name": "分行名称",
        "label.bank_swift_code": "SWIFT代码",
        "label.bank_account_type": "账户类型",
        "label.bank_account_holder": "账户持有人",
        "label.ea_bank_reference": "员工主记录参考（只读）",
        "label.bank_match": "一致",
        "label.bank_diff": "已修改",
        "label.payroll_currency": "发薪币种",
        "label.currency_twd": "TWD - 新台币",
        "msg.no_records": "没有记录",
        "msg.saved": "已保存",
        "msg.create_salary_master_confirm": "现在创立新的薪资主记录，你确认吗？确认请按'确定'，其他键返回。",
        "msg.salary_master_created": "薪资主记录创建完成",
        "msg.imported": "导入完成",
        "msg.calculated": "工资计算完成",
        "nav.monthly_sheets": "月度薪资核算",
        "nav.calendars": "薪资日历",
        "action.create_sheet": "生成空工资表",
        "action.review_sheet": "月工资数据维护",
        "action.salary_review": "工资维护",
        "action.confirm_basic_info": "HR确认",
        "action.void_sheet": "作废此工资表",
        "action.delete_sheet": "删除此工资表",
        "action.select_all": "全选",
        "action.deselect_all": "取消全选",
        "action.apply_to_selected": "应用到选中",
        "action.detail_edit": "明细编辑",
        "action.return_to_draft": "退回修改",
        "action.hr_calculate": "执行薪资计算",
        "action.hr_approve": "HR审核通过",
        "action.send_manager_review": "发送经理审核",
        "action.manager_approve": "经理审核通过",
        "action.manager_reject": "经理退回",
        "action.import_attendance": "从考勤系统导入",
        "action.batch_set_attendance": "批量设置出勤",
        "action.recalculate": "重新计算",
        "action.calendar_create": "创建日历",
        "label.year": "年度",
        "label.attendance_source": "考勤来源",
        "label.manual_input": "手动输入",
        "label.from_timesheet": "从考勤系统",
        "label.standard_work_days": "当月满勤天数",
        "label.standard_work_hours": "当月满勤小时",
        "label.actual_work_days": "当月出勤天数",
        "label.actual_work_hours": "当月出勤小时",
        "label.paid_leave_days": "带薪假天数",
        "label.unpaid_leave_days": "无薪假天数",
        "label.sick_leave_days": "病假天数",
        "label.overtime_hours": "加班小时",
        "label.absence_days": "缺勤天数",
        "label.manager_review_status": "经理审核状态",
        "label.manager_comment": "经理审核意见",
        "label.calculation_version": "计算版本",
        "label.base_pay": "基本工资(计算)",
        "label.manager_review": "经理审核",
        "msg.create_sheet_confirm": "即将根据筛选条件生成空工资表。包含的员工记录将进入草稿状态，可后续编辑。确认请按确定，取消返回。",
        "msg.create_sheet_modal_title": "确认生成空工资表",
        "msg.create_sheet_modal_body": "即将根据筛选条件生成空工资表。<br>包含 <b>{count}</b> 名员工的记录将进入草稿状态。<br><br>是否继续？",
        "msg.review_save_modal_title": "确认保存工资复核",
        "msg.review_save_modal_body": "即将保存 <b>{count}</b> 条记录的修改。<br>已修改的字段将立即生效。<br><br>是否确认保存？",
        "msg.calculate_modal_title": "确认执行薪资计算",
        "msg.calculate_modal_body": "即将对 <b>{count}</b> 条选中记录执行薪资计算。<br>• 月薪：基本工资 × 出勤比例<br>• 时薪/日薪：按实际工时/天数计算<br>• 已计算的结果将被覆盖<br><br>是否开始计算？",
        "msg.sheet_created": "工资表已创建",
        "msg.basic_info_confirmed": "基础资料已确认",
        "msg.calculation_done": "薪资计算完成",
        "msg.manager_approved": "经理审核已通过",
        "msg.manager_rejected": "经理退回修改",
        "msg.attendance_imported": "考勤数据已导入",
        "msg.sheet_finalized": "工资表已确认，进入发放流程",
        "msg.sheet_voided": "工资表已作废",
        "msg.void_sheet_confirm": "确定要作废此工资表吗？所有明细记录也将被作废，此操作不可撤销。\n\n确认请按确定，取消返回。",
        "msg.sheet_deleted": "工资表已永久删除",
        "msg.delete_sheet_confirm": "确定要永久删除此工资表吗？此操作不可撤销，数据将从系统中彻底移除。\n\n确认请按确定，取消返回。",
        "msg.calculate_batch_confirm": "即将对此批次执行工资计算，已计算的数据将被覆盖。确认请按确定，取消返回。",
        "msg.calculate_sheet_confirm": "即将对此工资表执行薪资计算。\n\n• 月薪人员公式：基本工资 × (出勤天数 + 带薪假 + 病假) / 满勤天数\n• 时薪/日薪人员按实际工时/天数计算\n• 系统将根据出勤数据和薪资参数自动计算\n• 已计算的结果将被覆盖\n• 计算完成后会显示成功/警告统计\n\n确定要开始计算吗？",
        "msg.calculate_actuarial_confirm": "即将对所有选中记录执行精算计算。确认请按确定，取消返回。",
        "msg.calculate_actuarial_all_confirm": "即将对所有精算记录执行计算。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_hr_review_confirm": "即将把此批次从「已计算」推进到「HR审核通过」。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_approve_confirm": "即将把此批次从「HR审核通过」推进到「已审批」。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_finalize_confirm": "即将把此批次从「已审批」推进到「已定案」并锁定数据。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_payslips_confirm": "即将为此批次所有员工生成工资单PDF文件。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_email_confirm": "即将向此批次所有员工发送工资单电子邮件。实际邮件将被发送，此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_employee_confirm_confirm": "即将关闭员工确认窗口。未回复的员工将被自动确认为「无回复自动确认」。确认请按确定，取消返回。",
        "msg.batch_finance_confirm": "即将把此批次提交给财务部门。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_paid_confirm": "即将标记此批次为「已发放」。此操作不可撤销。确认请按确定，取消返回。",
        "msg.batch_void_confirm": "确定要作废此批次吗？所有明细记录也将被作废，此操作不可撤销。确认请按确定，取消返回。",
        "msg.release_email_confirm": "即将向所有选中员工发送工资单邮件。实际邮件将被发送，此操作不可撤销。请勾选下方确认框后点击发送按钮。确认请按确定，取消返回。",
        "msg.confirm_basic_info_confirm": "HR确认：即将锁定考勤数据和基础资料，进入计算准备状态。此操作可以退回修改。确认请按确定，取消返回。",
        "msg.sheet_hr_approve_confirm": "即将把此工资表从「已计算」推进到「HR审核通过」。此操作不可撤销。确认请按确定，取消返回。",
        "msg.sheet_send_manager_confirm": "即将把此工资表发送给经理审核。此操作不可撤销。确认请按确定，取消返回。",
        "msg.sheet_manager_approve_confirm": "即将通过经理审核。此操作不可撤销。确认请按确定，取消返回。",
        "msg.sheet_manager_reject_confirm": "即将退回此工资表至HR重新处理。确认请按确定，取消返回。",
        "msg.sheet_finalize_confirm": "即将批准并定案此工资表并进入发放流程。此操作不可撤销。确认请按确定，取消返回。",
        "msg.approve_finalize_confirm": "即将批准并定案此工资表，进入发放流程。此操作不可撤销。确认请按 Yes，取消返回。",
        "msg.return_to_draft_confirm": "即将把此工资表退回草稿状态，所有计算结果将被清除。确认请按确定，取消返回。",
        "msg.deactivate_salary_master_confirm": "即将停用此薪资主记录。停用后可以重新从EmployeeAdmin生成。确认请按确定，取消返回。",
        "msg.import_employeeadmin_confirm": "即将从EmployeeAdmin导入员工到薪资主数据。确认请按确定，取消返回。",
        "msg.create_batch_confirm": "确定要生成此批次吗？批次生成后将进入草稿状态，可后续加载员工数据并执行计算。确认请按确定，取消返回。",
        "msg.review_save_confirm": "确定要保存此次编辑吗？已修改的字段将立即生效。确认请按确定，取消返回。",
        "msg.actuarial_save_confirm": "确定要保存精算数据吗？所有修改将立即生效。确认请按确定，取消返回。",
        "msg.actuarial_load_confirm": "即将从工资表加载数据到精算表。现有精算数据将被覆盖。确认请按确定，取消返回。",
        "msg.modify_salary_master_confirm": "您即将进入薪资主数据审核修改模式，确认继续吗？",
        "msg.save_salary_master_confirm": "以下字段已发生变更，确认保存吗？",
        "msg.import_timesheet_confirm": "即将从考勤系统导入出勤数据。现有出勤数据将被覆盖。确认请按确定，取消返回。",
        "msg.batch_set_attendance_confirm": "即将批量设置所有员工的实际出勤天数和小时间。现有数据将被覆盖。确认请按确定，取消返回。",
        "action.return_to_prev": "退回上一步",
        "action.return_to_prev_hr": "退回修改",
        "label.return_reason": "退回原因（必填）",
        "msg.return_step_confirm": "即将退回上一步。当前阶段的处理结果将被清除。请输入退回原因。确认请按确定，取消返回。",
        "msg.batch_return_step_confirm": "即将退回上一步。当前阶段产生的计算结果和文件将被清除。请输入退回原因。确认请按确定，取消返回。",
        "progress.batch_draft": "草稿",
        "progress.batch_calculated": "已计算",
        "progress.batch_hr_reviewed": "HR审核",
        "progress.batch_finalized": "批准定案",
        "progress.batch_payslips_generated": "工资单已生成",
        "progress.batch_sent_to_employees": "已发送",
        "progress.batch_employee_confirmed": "员工已确认",
        "progress.batch_released_to_finance": "已提交财务",
        "progress.batch_paid": "已发放",
        "msg.batch_return_to_draft_confirm": "即将退回草稿状态，计算结果将被清除。请输入退回原因。确认请按确定，取消返回。",
        "label.locked": "已锁定",
        "msg.sheet_locked": "此工资表已定案锁定，无法修改。",
        # ── 员工工资发放 (Release) ──
        "nav.ledger": "工资台账",
        "nav.release": "工资发放",
        "action.release_payslips": "生成工资单 PDF",
        "action.release_hr_confirm": "HR确认工资单",
        "action.release_email_draft": "准备邮件草稿",
        "action.release_email_send": "确认并发送邮件",
        "action.release_resend": "重发",
        "action.release_paid": "标记已发放",
        "action.enter_release": "进入发放流程",
        "action.create_release_batch": "创建发放批次",
        "label.release_status": "发放状态",
        "label.email_draft_status": "邮件状态",
        "label.send_summary": "发送汇总",
        "label.sent_count": "已发送",
        "label.failed_count": "发送失败",
        "label.pending_send": "待发送",
        "label.select_employees": "选择发送员工",
        "label.email_preview": "邮件预览",
        "label.email_to": "收件人",
        "label.email_cc": "抄送",
        "label.email_subject": "邮件主题",
        "label.email_body": "邮件正文",
        "label.hr_confirm_checkbox": "我确认以上工资单信息无误，同意发送给勾选的员工",
        "msg.release_payslips_confirm": "即将为此发放批次中的所有员工生成工资单PDF。确认请按确定，取消返回。",
        "msg.payslip_gen_modal_title": "确认生成工资单 PDF",
        "msg.payslip_gen_modal_body": "即将为 <b>{count}</b> 名员工生成工资单 PDF。此操作不可撤销。是否继续？",
        "msg.payslip_gen_modal_yes": "Yes - 确认生成",
        "msg.payslip_gen_modal_no": "No - 取消",
        "msg.payslip_gen_count_feedback": "✅ 成功生成 {count} 份工资单 PDF",
        "msg.payslip_gen_select_prompt": "请至少选择一名员工",
        "label.pdf_status": "PDF",
        "msg.release_hr_confirm_confirm": "请确认所有工资单内容无误。确认后将锁定工资单，不可再修改。确认请按确定，取消返回。",
        "msg.release_email_send_confirm": "即将发送工资单邮件给选中的员工。请确认收件人和邮件内容无误。",
        "msg.release_resend_confirm": "即将重新发送此工资单邮件。确认请按确定，取消返回。",
        "msg.release_paid_confirm": "即将标记为已发放。此操作不可撤销。确认请按确定，取消返回。",
        "msg.no_email_recipients": "没有有效的邮箱地址，无法发送。",
        "msg.email_sent_summary": "发送完成：成功 {sent} 人，失败 {failed} 人。",
        "msg.email_draft_security_note": "请核实每位员工的邮箱地址和工资单内容。发送后员工将收到带PDF附件的邮件。",
        "msg.smtp_not_configured": "SMTP邮件服务未配置。员工需手动下载工资单，或请管理员配置SMTP后再发送。",
    },
    "ja": {
        "app.title": "TACAI Pay SG シンガポール給与",
        "nav.dashboard": "ダッシュボード",
        "nav.master": "給与マスタ",
        "nav.batches": "従業員給与支給",
        "nav.actuarial": "給与精算",
        "nav.reports": "レポート",
        "nav.parameters": "パラメータ",
        "nav.audit": "監査",
        "action.save": "保存",
        "action.cancel": "キャンセル",
        "action.create": "作成",
        "action.create_salary_master": "給与マスタレコードを作成",
        "action.modify": "データ確認修正",
        "action.import_sg": "EmployeeAdminからSG社員を取込",
        "action.generate": "支給バッチを作成",
        "action.calculate": "給与計算を実行",
        "action.hr_review": "HRレビュー完了",
        "action.approve": "次段階承認",
        "action.finalize": "承認確定",
        "action.approve_finalize": "承認確定",
        "action.payslips": "給与明細PDF生成",
        "action.email": "メール送信",
        "action.employee_confirm": "社員確認完了/未返信を自動確認",
        "action.finance": "財務へ提出",
        "action.paid": "支払済にする",
        "action.void": "この給与表を無効化",
        "action.load_employees": "社員読込",
        "action.calculate_selected": "選択計算",
        "action.calculate_all": "全員計算",
        "action.save_all": "全保存",
        "label.employee": "社員",
        "label.month": "給与月",
        "label.entity": "法人实体コード",
        "label.status": "ステータス",
        "label.country": "国",
        "label.salary_type": "給与タイプ",
        "label.basic_salary": "基本給",
        "label.hourly_rate": "時給",
        "label.daily_rate": "日給",
        "label.work_days": "出勤日数",
        "label.work_hours": "勤務時間",
        "label.gross": "総支給額",
        "label.deductions": "控除合計",
        "label.net": "差引支給額",
        "label.employer_cost": "会社負担額",
        "label.cpf_employee": "従業員CPF",
        "label.cpf_employer": "雇用主CPF",
        "label.sdl": "SDL",
        "label.fwl": "FWL",
        "label.other_deduction": "その他控除",
        "label.income_tax": "所得税/源泉",
        "label.allowance": "手当",
        "label.bonus": "賞与/追加支給",
        "label.performance_bonus": "月次業績給",
        "label.performance_reference": "業績参考値",
        "label.department": "部署",
        "label.team": "チーム",
        "label.all": "全て",
        "label.email": "メール",
        "label.bank": "銀行情報",
        "label.bank_branch_name": "支店名",
        "label.bank_swift_code": "SWIFTコード",
        "label.bank_account_type": "口座種類",
        "label.bank_account_holder": "口座名義人",
        "label.ea_bank_reference": "従業員マスタ参照（読取専用）",
        "label.bank_match": "一致",
        "label.bank_diff": "変更済",
        "label.payroll_currency": "支給通貨",
        "label.currency_twd": "TWD - ニュー台湾ドル",
        "msg.no_records": "データがありません",
        "msg.saved": "保存しました",
        "msg.create_salary_master_confirm": "新しい給与マスタレコードを作成します。よろしいですか？「OK」で確認、「キャンセル」で戻ります。",
        "msg.salary_master_created": "給与マスタレコードを作成しました",
        "msg.imported": "取込完了",
        "msg.calculated": "給与計算完了",
        "nav.monthly_sheets": "月次給与計算",
        "nav.calendars": "給与カレンダー",
        "action.create_sheet": "空給与表を生成",
        "action.review_sheet": "月次給与データ管理",
        "action.salary_review": "給与レビュー",
        "action.confirm_basic_info": "HR確認",
        "action.void_sheet": "給与表を無効化",
        "action.delete_sheet": "給与表を削除",
        "action.select_all": "全て選択",
        "action.deselect_all": "選択解除",
        "action.apply_to_selected": "選択に適用",
        "action.detail_edit": "詳細編集",
        "action.return_to_draft": "下書きに戻す",
        "action.hr_calculate": "給与計算を実行",
        "action.hr_approve": "HR承認完了",
        "action.send_manager_review": "マネージャー審査に送信",
        "action.manager_approve": "マネージャー承認",
        "action.manager_reject": "マネージャー差戻し",
        "action.import_attendance": "勤怠システムから取込",
        "action.batch_set_attendance": "一括出勤設定",
        "action.recalculate": "再計算",
        "action.calendar_create": "カレンダー作成",
        "label.year": "年度",
        "label.attendance_source": "勤怠ソース",
        "label.manual_input": "手動入力",
        "label.from_timesheet": "勤怠システムから",
        "label.standard_work_days": "月次所定勤務日数",
        "label.standard_work_hours": "月次所定勤務時間",
        "label.actual_work_days": "月次実働日数",
        "label.actual_work_hours": "月次実働時間",
        "label.paid_leave_days": "有給休暇日数",
        "label.unpaid_leave_days": "無給休暇日数",
        "label.sick_leave_days": "病気休暇日数",
        "label.overtime_hours": "残業時間",
        "label.absence_days": "欠勤日数",
        "label.manager_review_status": "マネージャー審査状況",
        "label.manager_comment": "マネージャー審査コメント",
        "label.calculation_version": "計算バージョン",
        "label.base_pay": "基本給(計算)",
        "label.manager_review": "マネージャー審査",
        "msg.create_sheet_confirm": "選択した条件で空の給与表を生成します。含まれる社員レコードは下書き状態になり、後で編集できます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.create_sheet_modal_title": "空給与表生成の確認",
        "msg.create_sheet_modal_body": "選択した条件で空の給与表を生成します。<br><b>{count}</b> 名の社員レコードが下書き状態で作成されます。<br><br>続行しますか？",
        "msg.review_save_modal_title": "給与レビュー保存の確認",
        "msg.review_save_modal_body": "<b>{count}</b> 件のレコード変更を保存します。<br>変更されたフィールドは即時に反映されます。<br><br>保存を確認しますか？",
        "msg.calculate_modal_title": "給与計算実行の確認",
        "msg.calculate_modal_body": "選択した <b>{count}</b> 件のレコードの給与計算を実行します。<br>• 月給：基本給 × 出勤比率<br>• 時給/日給：実働時間/日数で計算<br>• 既存の計算結果は上書きされます<br><br>計算を開始しますか？",
        "msg.sheet_created": "給与表を作成しました",
        "msg.basic_info_confirmed": "基本情報を確認しました",
        "msg.calculation_done": "給与計算が完了しました",
        "msg.manager_approved": "マネージャーが承認しました",
        "msg.manager_rejected": "マネージャーが差し戻しました",
        "msg.attendance_imported": "勤怠データを取り込みました",
        "msg.sheet_finalized": "給与表が確定され、支払フローに進みます",
        "msg.sheet_voided": "給与表を無効化しました",
        "msg.void_sheet_confirm": "この給与表を無効化しますか？全ての明細レコードも無効化され、元に戻せません。\n\n「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_deleted": "給与表を完全に削除しました",
        "msg.delete_sheet_confirm": "この給与表を完全に削除しますか？操作は元に戻せず、データは完全に削除されます。\n\n「OK」で確認、「キャンセル」で戻ります。",
        "msg.calculate_batch_confirm": "このバッチの給与計算を実行します。既存の計算結果は上書きされます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.calculate_sheet_confirm": "この給与表の給与計算を実行します。\n\n• 月給者計算式：基本給 × (出勤日数 + 有給休暇 + 病気休暇) / 所定勤務日数\n• 時給/日給者は実働時間/日数で計算\n• 勤怠データと給与パラメータに基づき自動計算\n• 既存の計算結果は上書きされます\n• 計算後、成功/警告の統計が表示されます\n\n計算を開始しますか？",
        "msg.calculate_actuarial_confirm": "選択したすべての記録に対してアクチュアリー計算を実行します。「OK」で確認、「キャンセル」で戻ります。",
        "msg.calculate_actuarial_all_confirm": "すべてのアクチュアリー記録を計算します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_hr_review_confirm": "このバッチを「計算済み」から「HRレビュー完了」に遷移します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_approve_confirm": "このバッチを「HRレビュー完了」から「承認済み」に遷移します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_finalize_confirm": "このバッチを「承認済み」から「確定」に遷移し、データをロックします。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_payslips_confirm": "このバッチの全従業員の給与明細PDFを生成します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_email_confirm": "このバッチの全従業員に給与明細メールを送信します。実際にメールが送信され、この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_employee_confirm_confirm": "従業員確認をクローズします。未返信の従業員は「未返信自動確認」になります。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_finance_confirm": "このバッチを財務部門にリリースします。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_paid_confirm": "このバッチを「支払済み」にマークします。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_void_confirm": "このバッチを無効化しますか？すべての明細レコードも無効化され、元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.release_email_confirm": "選択した全従業員に給与明細メールを送信します。実際にメールが送信され、元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.confirm_basic_info_confirm": "HR確認：勤怠データと基本情報をロックし、計算準備状態に移行します。この操作は後で差し戻せます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_hr_approve_confirm": "この給与表を「計算済み」から「HR承認済み」に遷移します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_send_manager_confirm": "この給与表をマネージャー審査に送信します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_manager_approve_confirm": "マネージャー承認を完了します。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_manager_reject_confirm": "この給与表をHRに差し戻します。「OK」で確認、「キャンセル」で戻ります。",
        "msg.sheet_finalize_confirm": "この給与表を承認・確定し、支払フローに進みます。この操作は取り消せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.approve_finalize_confirm": "この給与表を承認・確定し、支給フローに進みます。この操作は取り消せません。確認する場合は「はい」を押してください。",
        "msg.return_to_draft_confirm": "この給与表を下書き状態に戻します。すべての計算結果は消去されます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.deactivate_salary_master_confirm": "この給与マスタレコードを無効化します。無効化後もEmployeeAdminから再生成可能です。「OK」で確認、「キャンセル」で戻ります。",
        "msg.import_employeeadmin_confirm": "EmployeeAdminから従業員データを給与マスタに取り込みます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.create_batch_confirm": "このバッチを生成しますか？生成後は下書き状態になり、従業員データのロードと計算を実行できます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.review_save_confirm": "この編集を保存しますか？変更されたフィールドは即時に反映されます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.actuarial_save_confirm": "アクチュアリーデータを保存しますか？すべての変更は即時に反映されます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.actuarial_load_confirm": "給与表からアクチュアリー表にデータをロードします。既存のアクチュアリーデータは上書きされます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.modify_salary_master_confirm": "給与マスタの確認修正モードに入ります。変更内容は保存時に確認されます。続行しますか？",
        "msg.save_salary_master_confirm": "以下のフィールドが変更されました。保存してよろしいですか？",
        "msg.import_timesheet_confirm": "勤怠システムから出勤データを取り込みます。既存の出勤データは上書きされます。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_set_attendance_confirm": "全従業員の実働日数と時間を一括設定します。既存のデータは上書きされます。「OK」で確認、「キャンセル」で戻ります。",
        "action.return_to_prev": "前のステップに戻る",
        "action.return_to_prev_hr": "修正のために戻す",
        "label.return_reason": "戻す理由（必須）",
        "msg.return_step_confirm": "前のステップに戻ります。現在の段階の処理結果はクリアされます。戻す理由を入力してください。「OK」で確認、「キャンセル」で戻ります。",
        "msg.batch_return_step_confirm": "前のステップに戻ります。現在の段階で生成された計算結果とファイルはクリアされます。戻す理由を入力してください。「OK」で確認、「キャンセル」で戻ります。",
        "progress.batch_draft": "下書き",
        "progress.batch_calculated": "計算済",
        "progress.batch_hr_reviewed": "HRレビュー",
        "progress.batch_finalized": "承認確定",
        "progress.batch_payslips_generated": "給与明細生成済",
        "progress.batch_sent_to_employees": "送信済",
        "progress.batch_employee_confirmed": "従業員確認済",
        "progress.batch_released_to_finance": "財務提出済",
        "progress.batch_paid": "支払済",
        "msg.batch_return_to_draft_confirm": "下書き状態に戻ります。計算結果は消去されます。戻す理由を入力してください。「OK」で確認、「キャンセル」で戻ります。",
        "label.locked": "ロック済み",
        "msg.sheet_locked": "この給与表は確定ロックされています。変更できません。",
        # ── 従業員給与支給 (Release) ──
        "nav.ledger": "給与台帳",
        "nav.release": "給与支給",
        "action.release_payslips": "給与明細PDFを生成",
        "action.release_hr_confirm": "HR確認完了",
        "action.release_email_draft": "メール下書きを準備",
        "action.release_email_send": "確認してメール送信",
        "action.release_resend": "再送信",
        "action.release_paid": "支払済にする",
        "action.enter_release": "支給フローに進む",
        "action.create_release_batch": "支給バッチを作成",
        "label.release_status": "支給状況",
        "label.email_draft_status": "メール状況",
        "label.send_summary": "送信サマリー",
        "label.sent_count": "送信済",
        "label.failed_count": "送信失敗",
        "label.pending_send": "送信待ち",
        "label.select_employees": "送信先を選択",
        "label.email_preview": "メールプレビュー",
        "label.email_to": "宛先",
        "label.email_cc": "CC",
        "label.email_subject": "件名",
        "label.email_body": "本文",
        "label.hr_confirm_checkbox": "給与明細の内容が正確であることを確認し、選択した従業員に送信することに同意します",
        "msg.release_payslips_confirm": "この支給バッチの全従業員の給与明細PDFを生成します。「OK」で確認、「キャンセル」で戻ります。",
        "msg.payslip_gen_modal_title": "給与明細PDF生成の確認",
        "msg.payslip_gen_modal_body": "<b>{count}</b> 名の従業員の給与明細PDFを生成します。この操作は元に戻せません。続行しますか？",
        "msg.payslip_gen_modal_yes": "Yes - 生成する",
        "msg.payslip_gen_modal_no": "No - キャンセル",
        "msg.payslip_gen_count_feedback": "✅ {count} 件の給与明細PDFを生成しました",
        "msg.payslip_gen_select_prompt": "少なくとも1人の従業員を選択してください",
        "label.pdf_status": "PDF",
        "msg.release_hr_confirm_confirm": "すべての給与明細の内容が正しいことを確認してください。確認後はロックされ、変更できません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.release_email_send_confirm": "選択した従業員に給与明細メールを送信します。宛先と内容を確認してください。",
        "msg.release_resend_confirm": "この給与明細メールを再送信します。「OK」で確認、「キャンセル」で戻ります。",
        "msg.release_paid_confirm": "支払済としてマークします。この操作は元に戻せません。「OK」で確認、「キャンセル」で戻ります。",
        "msg.no_email_recipients": "有効なメールアドレスがありません。送信できません。",
        "msg.email_sent_summary": "送信完了：成功 {sent} 人、失敗 {failed} 人。",
        "msg.email_draft_security_note": "各従業員のメールアドレスと給与明細の内容を確認してください。送信後、従業員はPDF添付のメールを受信します。",
        "msg.smtp_not_configured": "SMTPメールサービスが設定されていません。従業員は手動で給与明細をダウンロードするか、管理者がSMTPを設定してから送信してください。",
    },
    "en": {
        "app.title": "TACAI Pay SG Singapore Payroll",
        "nav.dashboard": "Dashboard",
        "nav.master": "Salary Master",
        "nav.batches": "Employee Payroll Release",
        "nav.actuarial": "Salary Actuarial",
        "nav.reports": "Reports",
        "nav.parameters": "Parameters",
        "nav.audit": "Audit",
        "action.save": "Save",
        "action.cancel": "Cancel",
        "action.create": "Create",
        "action.create_salary_master": "Create Salary Master Records",
        "action.modify": "Review & Modify",
        "action.import_sg": "Import SG Employees from EmployeeAdmin",
        "action.generate": "Create Release Batch",
        "action.calculate": "Run Payroll Calculation",
        "action.hr_review": "HR Review Complete",
        "action.approve": "Next Approval Complete",
        "action.finalize": "Approve & Finalize",
        "action.approve_finalize": "Approve & Finalize",
        "action.payslips": "Generate Payslip PDFs",
        "action.email": "Send Emails",
        "action.employee_confirm": "Close Employee Confirmation",
        "action.finance": "Release to Finance",
        "action.paid": "Mark Paid",
        "action.void": "Void Batch",
        "action.load_employees": "Load Employees",
        "action.calculate_selected": "Calculate Selected",
        "action.calculate_all": "Calculate All",
        "action.save_all": "Save All",
        "label.employee": "Employee",
        "label.month": "Payroll Month",
        "label.entity": "Legal Entity Code",
        "label.status": "Status",
        "label.country": "Country",
        "label.salary_type": "Salary Type",
        "label.basic_salary": "Basic Salary",
        "label.hourly_rate": "Hourly Rate",
        "label.daily_rate": "Daily Rate",
        "label.work_days": "Work Days",
        "label.work_hours": "Work Hours",
        "label.gross": "Gross Pay",
        "label.deductions": "Total Deductions",
        "label.net": "Net Pay",
        "label.employer_cost": "Employer Cost",
        "label.cpf_employee": "Employee CPF",
        "label.cpf_employer": "Employer CPF",
        "label.sdl": "Skill Development Levy",
        "label.fwl": "Foreign Worker Levy",
        "label.other_deduction": "Other Deduction",
        "label.income_tax": "Income Tax / Withholding",
        "label.allowance": "Allowance",
        "label.bonus": "Bonus / Additional Pay",
        "label.performance_bonus": "Monthly Performance Bonus",
        "label.performance_reference": "Perf Reference",
        "label.department": "Department",
        "label.team": "Team",
        "label.all": "All",
        "label.email": "Email",
        "label.bank": "Bank",
        "label.bank_branch_name": "Branch Name",
        "label.bank_swift_code": "SWIFT Code",
        "label.bank_account_type": "Account Type",
        "label.bank_account_holder": "Account Holder",
        "label.ea_bank_reference": "EmployeeAdmin Reference (read-only)",
        "label.bank_match": "Match",
        "label.bank_diff": "Modified",
        "label.payroll_currency": "Payroll Currency",
        "label.currency_twd": "TWD - Taiwan Dollar",
        "msg.no_records": "No records",
        "msg.saved": "Saved",
        "msg.create_salary_master_confirm": "You are about to create new salary master records. Confirm? Press OK to confirm, Cancel to return.",
        "msg.salary_master_created": "Salary master records created",
        "msg.imported": "Import completed",
        "msg.calculated": "Payroll calculation completed",
        "nav.monthly_sheets": "Monthly Salary",
        "nav.calendars": "Payroll Calendar",
        "action.create_sheet": "Generate Empty Sheet",
        "action.review_sheet": "Maintain Monthly Data",
        "action.salary_review": "Salary Review",
        "action.confirm_basic_info": "HR Confirm",
        "action.void_sheet": "Void Sheet",
        "action.delete_sheet": "Delete Sheet",
        "action.select_all": "Select All",
        "action.deselect_all": "Deselect All",
        "action.apply_to_selected": "Apply to Selected",
        "action.detail_edit": "Detail Edit",
        "action.return_to_draft": "Return to Draft",
        "action.hr_calculate": "Run Salary Calculation",
        "action.hr_approve": "HR Approve",
        "action.send_manager_review": "Send to Manager Review",
        "action.manager_approve": "Manager Approve",
        "action.manager_reject": "Manager Reject",
        "action.import_attendance": "Import from Timesheet",
        "action.batch_set_attendance": "Batch Set Attendance",
        "action.recalculate": "Recalculate",
        "action.calendar_create": "Create Calendar",
        "label.year": "Year",
        "label.attendance_source": "Attendance Source",
        "label.manual_input": "Manual Input",
        "label.from_timesheet": "From Timesheet",
        "label.standard_work_days": "Standard Work Days",
        "label.standard_work_hours": "Standard Work Hours",
        "label.actual_work_days": "Actual Work Days",
        "label.actual_work_hours": "Actual Work Hours",
        "label.paid_leave_days": "Paid Leave Days",
        "label.unpaid_leave_days": "Unpaid Leave Days",
        "label.sick_leave_days": "Sick Leave Days",
        "label.overtime_hours": "Overtime Hours",
        "label.absence_days": "Absence Days",
        "label.manager_review_status": "Manager Review Status",
        "label.manager_comment": "Manager Comment",
        "label.calculation_version": "Calculation Version",
        "label.base_pay": "Base Pay (Calculated)",
        "label.manager_review": "Manager Review",
        "msg.create_sheet_confirm": "You are about to generate an empty salary sheet based on the selected filters. Employee records will be created in draft status and can be edited later. Press OK to confirm, Cancel to return.",
        "msg.create_sheet_modal_title": "Confirm Create Empty Sheet",
        "msg.create_sheet_modal_body": "You are about to generate an empty salary sheet.<br><b>{count}</b> employee records will be created in draft status.<br><br>Continue?",
        "msg.review_save_modal_title": "Confirm Save Review",
        "msg.review_save_modal_body": "You are about to save <b>{count}</b> record changes.<br>Modified fields will take effect immediately.<br><br>Confirm save?",
        "msg.calculate_modal_title": "Confirm Salary Calculation",
        "msg.calculate_modal_body": "You are about to run salary calculation for <b>{count}</b> selected records.<br>• Monthly: Basic Salary × attendance ratio<br>• Hourly/Daily: By actual hours/days<br>• Existing results will be overwritten<br><br>Start calculation?",
        "msg.sheet_created": "Salary sheet created successfully",
        "msg.basic_info_confirmed": "Basic info confirmed",
        "msg.calculation_done": "Salary calculation completed",
        "msg.manager_approved": "Manager approved",
        "msg.manager_rejected": "Manager rejected - returned for revision",
        "msg.attendance_imported": "Attendance data imported",
        "msg.sheet_finalized": "Sheet finalized - entering payment flow",
        "msg.sheet_voided": "Sheet voided successfully",
        "msg.void_sheet_confirm": "Are you sure you want to void this sheet? All detail records will also be voided. This action cannot be undone.\n\nPress OK to confirm, Cancel to return.",
        "msg.sheet_deleted": "Sheet permanently deleted",
        "msg.delete_sheet_confirm": "Are you sure you want to permanently delete this sheet? This action cannot be undone and data will be completely removed.\n\nPress OK to confirm, Cancel to return.",
        "msg.calculate_batch_confirm": "You are about to run payroll calculation for this batch. Existing results will be overwritten. Press OK to confirm, Cancel to return.",
        "msg.calculate_sheet_confirm": "You are about to run salary calculation for this sheet.\n\n• Monthly formula: Basic Salary × (Work Days + Paid Leave + Sick Leave) / Standard Days\n• Hourly/daily employees: calculated by actual hours/days worked\n• Automatic calculation based on attendance data and salary parameters\n• Existing calculation results will be overwritten\n• Success/warning statistics will be displayed after calculation\n\nProceed with calculation?",
        "msg.calculate_actuarial_confirm": "You are about to calculate all selected actuarial records. Press OK to confirm, Cancel to return.",
        "msg.calculate_actuarial_all_confirm": "You are about to calculate ALL actuarial records. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_hr_review_confirm": "You are about to move this batch from 'Calculated' to 'HR Reviewed'. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_approve_confirm": "You are about to move this batch from 'HR Reviewed' to 'Approved'. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_finalize_confirm": "You are about to move this batch from 'Approved' to 'Finalized' and lock all data. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_payslips_confirm": "You are about to generate payslip PDFs for all employees in this batch. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_email_confirm": "You are about to send payslip emails to all employees in this batch. Actual emails will be sent. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_employee_confirm_confirm": "You are about to close employee confirmation. Employees who have not responded will be auto-confirmed. Press OK to confirm, Cancel to return.",
        "msg.batch_finance_confirm": "You are about to release this batch to Finance. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_paid_confirm": "You are about to mark this batch as 'Paid'. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.batch_void_confirm": "Are you sure you want to void this batch? All detail records will also be voided. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.release_email_confirm": "You are about to send payslip emails to all selected employees. Actual emails will be sent. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.confirm_basic_info_confirm": "HR Confirm: You are about to lock attendance data and basic info, entering calculation-ready state. This action can be undone by returning to draft. Press OK to confirm, Cancel to return.",
        "msg.sheet_hr_approve_confirm": "You are about to move this sheet from 'Calculated' to 'HR Approved'. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.sheet_send_manager_confirm": "You are about to send this sheet to manager review. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.sheet_manager_approve_confirm": "You are about to complete manager approval for this sheet. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.sheet_manager_reject_confirm": "You are about to reject this sheet and return it to HR for revision. Press OK to confirm, Cancel to return.",
        "msg.sheet_finalize_confirm": "You are about to approve and finalize this sheet and enter the payment flow. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.approve_finalize_confirm": "You are about to approve and finalize this payroll sheet. This action cannot be undone. Click Yes to confirm.",
        "msg.return_to_draft_confirm": "You are about to return this sheet to draft status. All calculation results will be cleared. Press OK to confirm, Cancel to return.",
        "msg.deactivate_salary_master_confirm": "You are about to deactivate this salary master record. It can be regenerated from EmployeeAdmin later. Press OK to confirm, Cancel to return.",
        "msg.import_employeeadmin_confirm": "You are about to import employees from EmployeeAdmin into Salary Master. Press OK to confirm, Cancel to return.",
        "msg.create_batch_confirm": "Are you sure you want to create this batch? It will be created in draft status for subsequent employee loading and calculation. Press OK to confirm, Cancel to return.",
        "msg.review_save_confirm": "Save this review? Changes will take effect immediately. Press OK to confirm, Cancel to return.",
        "msg.actuarial_save_confirm": "Save actuarial data? All changes will take effect immediately. Press OK to confirm, Cancel to return.",
        "msg.actuarial_load_confirm": "You are about to load data from the payroll sheet into the actuarial sheet. Existing actuarial data will be overwritten. Press OK to confirm, Cancel to return.",
        "msg.modify_salary_master_confirm": "You are about to enter Salary Master review & modify mode. Continue?",
        "msg.save_salary_master_confirm": "The following fields have been changed. Confirm save?",
        "msg.import_timesheet_confirm": "You are about to import attendance data from the timesheet system. Existing attendance data will be overwritten. Press OK to confirm, Cancel to return.",
        "msg.batch_set_attendance_confirm": "You are about to batch set attendance days and hours for all employees. Existing data will be overwritten. Press OK to confirm, Cancel to return.",
        "action.return_to_prev": "Return to Previous Step",
        "action.return_to_prev_hr": "Return for Revision",
        "label.return_reason": "Return reason (required)",
        "msg.return_step_confirm": "You are about to return to the previous step. Current stage results will be cleared. Please enter the return reason. Press OK to confirm, Cancel to return.",
        "msg.batch_return_step_confirm": "You are about to return to the previous step. Results and files generated at the current stage will be cleared. Please enter the return reason. Press OK to confirm, Cancel to return.",
        "progress.batch_draft": "Draft",
        "progress.batch_calculated": "Calculated",
        "progress.batch_hr_reviewed": "HR Reviewed",
        "progress.batch_finalized": "Approved & Finalized",
        "progress.batch_payslips_generated": "Payslips",
        "progress.batch_sent_to_employees": "Sent",
        "progress.batch_employee_confirmed": "Confirmed",
        "progress.batch_released_to_finance": "Finance",
        "progress.batch_paid": "Paid",
        "msg.batch_return_to_draft_confirm": "You are about to return to draft status. Calculation results will be cleared. Please enter the return reason. Press OK to confirm, Cancel to return.",
        "label.locked": "Locked",
        "msg.sheet_locked": "This sheet is finalized and locked. No modifications allowed.",
        # ── Employee Payroll Release ──
        "nav.ledger": "Payroll Ledger",
        "nav.release": "Payroll Release",
        "action.release_payslips": "Generate Payslip PDFs",
        "action.release_hr_confirm": "HR Confirm Payslips",
        "action.release_email_draft": "Prepare Email Draft",
        "action.release_email_send": "Confirm and Send Emails",
        "action.release_resend": "Resend",
        "action.release_paid": "Mark as Paid",
        "action.enter_release": "Enter Release Flow",
        "action.create_release_batch": "Create Release Batch",
        "label.release_status": "Release Status",
        "label.email_draft_status": "Email Status",
        "label.send_summary": "Send Summary",
        "label.sent_count": "Sent",
        "label.failed_count": "Failed",
        "label.pending_send": "Pending",
        "label.select_employees": "Select Employees to Send",
        "label.email_preview": "Email Preview",
        "label.email_to": "To",
        "label.email_cc": "CC",
        "label.email_subject": "Subject",
        "label.email_body": "Body",
        "label.hr_confirm_checkbox": "I confirm the payslip information is correct and authorize sending to the selected employees",
        "msg.release_payslips_confirm": "You are about to generate payslip PDFs for all employees in this release batch. Press OK to confirm, Cancel to return.",
        "msg.payslip_gen_modal_title": "Confirm Payslip PDF Generation",
        "msg.payslip_gen_modal_body": "You are about to generate payslip PDFs for <b>{count}</b> employee(s). This action cannot be undone. Continue?",
        "msg.payslip_gen_modal_yes": "Yes - Generate",
        "msg.payslip_gen_modal_no": "No - Cancel",
        "msg.payslip_gen_count_feedback": "✅ Generated {count} payslip PDF(s) successfully",
        "msg.payslip_gen_select_prompt": "Please select at least one employee",
        "label.pdf_status": "PDF",
        "msg.release_hr_confirm_confirm": "Please verify all payslip content is correct. Confirming will lock payslips and prevent further modifications. Press OK to confirm, Cancel to return.",
        "msg.release_email_send_confirm": "You are about to send payslip emails to the selected employees. Please verify recipients and content.",
        "msg.release_resend_confirm": "You are about to resend this payslip email. Press OK to confirm, Cancel to return.",
        "msg.release_paid_confirm": "You are about to mark this batch as paid. This action cannot be undone. Press OK to confirm, Cancel to return.",
        "msg.no_email_recipients": "No valid email addresses found. Cannot send.",
        "msg.email_sent_summary": "Send complete: {sent} sent successfully, {failed} failed.",
        "msg.email_draft_security_note": "Please verify each employee's email address and payslip content. Employees will receive an email with PDF attachment after sending.",
        "msg.smtp_not_configured": "SMTP email service is not configured. Employees will need to download payslips manually, or an administrator should configure SMTP before sending.",
    },
}


def ensure_dirs() -> None:
    for path in (DATABASE_DIR, I18N_DIR, PAYSLIP_DIR):
        path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def money(value: Any) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(str(value).replace(",", "")), 2)
    except (TypeError, ValueError):
        return 0.0


def intish(value: Any) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def clean(value: Any) -> str:
    return str(value or "").strip()


def slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-") or "item"


def load_json(path: Path, default: Any) -> Any:
    if _PG_AVAILABLE:
        try:
            table = _db.path_to_table(path)
            result = _db.load_table(table)
            if result is not None:
                if not result and isinstance(default, list):
                    _db.save_table(table, default)
                    return default
                return result
        except Exception:
            pass
    # JSON fallback
    ensure_dirs()
    if not path.exists():
        save_json(path, default)
        return default
    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return default

def save_json(path: Path, data: Any) -> None:
    if _PG_AVAILABLE and isinstance(data, list):
        try:
            table = _db.path_to_table(path)
            _db.save_table(table, data)
            return
        except Exception:
            pass
    # JSON fallback
    ensure_dirs()
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    tmp.replace(path)

def append_audit(module: str, record_id: str, action: str, before: Any = None, after: Any = None, user: str = USER_ACTOR) -> None:
    logs = load_json(AUDIT_LOGS_PATH, [])
    logs.append({
        "audit_id": f"AUD-{len(logs) + 1:06d}",
        "module": module,
        "record_id": record_id,
        "action": action,
        "user": user,
        "timestamp": now_iso(),
        "before_value": before,
        "after_value": after,
    })
    save_json(AUDIT_LOGS_PATH, logs)


def t(lang: str, key: str, default: str = "") -> str:
    lang = lang if lang in SUPPORTED_LANGS else DEFAULT_LANG
    return TRANSLATIONS.get(lang, {}).get(key) or TRANSLATIONS["en"].get(key) or default or key


def parse_lang(query: dict[str, list[str]]) -> str:
    lang = clean((query.get("lang") or [DEFAULT_LANG])[0])
    return lang if lang in SUPPORTED_LANGS else DEFAULT_LANG


def with_lang(path: str, lang: str, **params: Any) -> str:
    params = {key: value for key, value in params.items() if value not in (None, "")}
    params["lang"] = lang
    return f"{path}?{urlencode(params)}"


def query_link(path: str, query: dict[str, list[str]], **updates: Any) -> str:
    params: dict[str, Any] = {}
    for key, values in query.items():
        if key in updates:
            continue
        value = values[-1] if values else ""
        if value:
            params[key] = value
    for key, value in updates.items():
        if value not in (None, ""):
            params[key] = value
    return f"{path}?{urlencode(params)}" if params else path


def first_present(*values: Any) -> Any:
    for value in values:
        if value not in (None, ""):
            return value
    return ""


def has_permission(user: dict[str, Any] | None, permission_key: str) -> bool:
    if not user:
        return False
    roles = {clean(role).lower() for role in user.get("roles", [])}
    permissions = {clean(permission) for permission in user.get("permissions", [])}
    return "system_admin" in roles or "*" in permissions or permission_key in permissions


def validate_user_admin_session(session_id: str, cookie_header: str = "") -> dict[str, Any] | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    # Forward browser cookies so User_admin can validate against its own session store
    if cookie_header:
        headers["Cookie"] = cookie_header
    request = Request(
        f"{USER_ADMIN_INTERNAL_BASE_URL}/api/validate-session",
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with urlopen(request, timeout=5) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, OSError) as exc:
        print(f"[tacaipaysg] User_admin validate-session unreachable ({USER_ADMIN_INTERNAL_BASE_URL}): {exc}", flush=True)
        return None
    except json.JSONDecodeError as exc:
        print(f"[tacaipaysg] User_admin validate-session bad JSON: {exc}", flush=True)
        return None
    if data.get("valid") and isinstance(data.get("user"), dict):
        user = data["user"]
        user["_session_id"] = session_id
        if isinstance(data.get("session"), dict):
            user["_session"] = data["session"]
        return user
    return None


def user_display_name(user: dict[str, Any] | None) -> str:
    if not user:
        return ""
    return clean(user.get("display_name") or user.get("user_name") or user.get("email") or user.get("user_id"))


def forbidden_html(message: str) -> str:
    return f"<div class='sap-page-header'><h1>Forbidden</h1></div><div class='card'><div class='message-strip warn'>{escape(message)}</div></div>"


def load_salary_master() -> list[dict[str, Any]]:
    return [normalize_salary_master(row) for row in load_json(SALARY_MASTER_PATH, [])]


def save_salary_master(rows: list[dict[str, Any]]) -> None:
    save_json(SALARY_MASTER_PATH, rows)


IN_SERVICE_STATUSES = {"", "active", "probation", "in_service", "employed", "onboarded"}
OUT_OF_SERVICE_STATUSES = {"resigned", "inactive", "terminated", "deleted", "voided", "left"}
EMPLOYEEADMIN_IDENTITY_FIELDS = {
    "employee_number",
    "employee_name",
    "email",
    "entity_id",
    "department",
    "department_id",
    "department_label",
    "team_id",
    "team_label",
    "employment_status",
    "employeeadmin_status",
    "employeeadmin_payroll_ready",
    "employeeadmin_readiness_percent",
    "employeeadmin_last_seen_at",
}


def normalize_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value in (None, ""):
        return default
    return clean(value).lower() in {"1", "true", "yes", "on", "ready"}


def _parse_bank_snapshot(value: Any) -> dict[str, Any]:
    """Parse employeeadmin_bank_snapshot from dict or JSON string."""
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


def normalize_salary_master(row: dict[str, Any]) -> dict[str, Any]:
    employee_id = clean(row.get("employee_id")) or clean(row.get("employee_number")) or f"SG-{int(datetime.now().timestamp())}"
    salary_type = clean(row.get("salary_type") or "monthly").lower()
    if salary_type not in SALARY_TYPES:
        salary_type = "monthly"
    cpf_mode = clean(row.get("cpf_input_mode") or "manual").lower()
    if cpf_mode not in CPF_MODES:
        cpf_mode = "manual"
    department_label = clean(row.get("department_label") or row.get("department"))
    employeeadmin_status = clean(row.get("employeeadmin_status") or row.get("employment_status") or "active")
    return {
        "salary_master_id": clean(row.get("salary_master_id")) or f"SM-SG-{slug(employee_id)}",
        "employee_id": employee_id,
        "employee_number": clean(row.get("employee_number")) or employee_id,
        "employee_name": clean(row.get("employee_name") or row.get("display_name")),
        "email": clean(row.get("email") or row.get("work_email")),
        "country_code": clean(row.get("country_code")) or "SG",
        "entity_id": clean(row.get("entity_id") or row.get("legal_entity_code") or "SG"),
        "department": department_label,
        "department_id": clean(row.get("department_id")),
        "department_label": department_label,
        "team_id": clean(row.get("team_id")),
        "team_label": clean(row.get("team_label")),
        "employment_status": clean(row.get("employment_status") or employeeadmin_status or "active"),
        "employeeadmin_status": employeeadmin_status,
        "employeeadmin_payroll_ready": normalize_bool(row.get("employeeadmin_payroll_ready") or row.get("payroll_ready"), False),
        "employeeadmin_readiness_percent": money(row.get("employeeadmin_readiness_percent") or row.get("payroll_readiness_percent")),
        "employeeadmin_last_seen_at": clean(row.get("employeeadmin_last_seen_at")),
        "salary_type": salary_type,
        "basic_salary": money(row.get("basic_salary")),
        "hourly_rate": money(row.get("hourly_rate")),
        "daily_rate": money(row.get("daily_rate")),
        "standard_work_days": money(row.get("standard_work_days") or 22),
        "standard_work_hours": money(row.get("standard_work_hours") or 176),
        "standard_monthly_hours": money(row.get("standard_monthly_hours") or 160),
        "overtime_hourly_rate": money(row.get("overtime_hourly_rate") or 0),
        "fixed_allowance": money(row.get("fixed_allowance")),
        "performance_bonus": money(row.get("performance_bonus")),
        "recurring_deductions": money(row.get("recurring_deductions")),
        "cpf_applicable": normalize_bool(row.get("cpf_applicable"), False),
        "cpf_input_mode": cpf_mode,
        "cpf_employee_manual": money(row.get("cpf_employee_manual") or row.get("cpf_employee")),
        "cpf_employer_manual": money(row.get("cpf_employer_manual") or row.get("cpf_employer")),
        "skill_development_levy": money(row.get("skill_development_levy")),
        "foreign_worker_levy": money(row.get("foreign_worker_levy")),
        "bank_name": clean(row.get("bank_name")),
        "bank_branch_name": clean(row.get("bank_branch_name")),
        "bank_swift_code": clean(row.get("bank_swift_code")),
        "bank_account_type": clean(row.get("bank_account_type") or "ordinary"),
        "bank_account_name": clean(row.get("bank_account_name")),
        "bank_account_number": clean(row.get("bank_account_number")),
        "employeeadmin_bank_snapshot": _parse_bank_snapshot(row.get("employeeadmin_bank_snapshot")),
        "payroll_currency": clean(row.get("payroll_currency") or "SGD"),
        "notes": clean(row.get("notes")),
        "active": normalize_bool(row.get("active"), True),
        "deactivated_at": clean(row.get("deactivated_at")),
        "deactivated_by": clean(row.get("deactivated_by")),
        "deactivation_reason": clean(row.get("deactivation_reason")),
        "created_at": clean(row.get("created_at")) or now_iso(),
        "updated_at": clean(row.get("updated_at")) or now_iso(),
        "source": clean(row.get("source") or "manual"),
    }


def is_active_employee_status(status: Any) -> bool:
    normalized = clean(status).lower()
    return normalized in IN_SERVICE_STATUSES and normalized not in OUT_OF_SERVICE_STATUSES


def salary_master_readiness(row: dict[str, Any]) -> dict[str, Any]:
    row = normalize_salary_master(row)
    missing: list[str] = []
    if not row.get("active"):
        return {"status": "inactive", "label_key": "status.inactive", "label": "Inactive", "missing": ["active"], "ready": False}
    if not is_active_employee_status(row.get("employeeadmin_status") or row.get("employment_status")):
        return {"status": "blocked", "label_key": "status.blocked", "label": "Blocked", "missing": ["employeeadmin_status"], "ready": False}
    for field in ["employee_id", "employee_number", "employee_name", "entity_id"]:
        if not row.get(field):
            missing.append(field)
    st = row.get("salary_type", "monthly")
    if st == "monthly" and not row.get("basic_salary"):
        missing.append("basic_salary")
    if st == "hourly" and not row.get("hourly_rate"):
        missing.append("hourly_rate")
    if st == "daily" and not row.get("daily_rate"):
        missing.append("daily_rate")
    if st == "monthly_hour" and (not row.get("basic_salary") or not row.get("hourly_rate")):
        if not row.get("basic_salary"):
            missing.append("basic_salary")
        if not row.get("hourly_rate"):
            missing.append("hourly_rate")
    if not row.get("bank_name"):
        missing.append("bank_name")
    if not row.get("bank_account_name"):
        missing.append("bank_account_name")
    if not row.get("bank_account_number"):
        missing.append("bank_account_number")
    if not row.get("bank_account_type"):
        missing.append("bank_account_type")
    if row.get("cpf_applicable") and row.get("cpf_input_mode") == "manual" and not row.get("cpf_employee_manual"):
        missing.append("cpf_employee_manual")
    if missing:
        return {"status": "incomplete", "label_key": "status.incomplete", "label": "Incomplete", "missing": missing, "ready": False}
    return {"status": "ready", "label_key": "status.ready", "label": "Ready", "missing": [], "ready": True}


def active_sg_salary_master(entity_id: str = "") -> list[dict[str, Any]]:
    sg_ids = set(sg_entity_ids())
    rows = []
    for row in load_salary_master():
        if not row.get("active") or row.get("entity_id") not in sg_ids:
            continue
        if not is_active_employee_status(row.get("employment_status")):
            continue
        if row.get("employeeadmin_status") and not is_active_employee_status(row.get("employeeadmin_status")):
            continue
        rows.append(row)
    if entity_id:
        rows = [row for row in rows if row.get("entity_id") == entity_id]
    return rows


# --- Entity label lookup (from masterdata) ---

_entity_map_cache: dict[str, dict[str, str]] | None = None


def _load_entity_map() -> dict[str, dict[str, str]]:
    """Load entity master from masterdata entities.json, keyed by entity_id."""
    global _entity_map_cache
    if _entity_map_cache is not None:
        return _entity_map_cache
    try:
        raw = load_json(MASTERDATA_ENTITIES_PATH, [])
    except Exception:
        raw = []
    _entity_map_cache = {}
    for e in raw:
        eid = e.get("entity_id", "")
        if eid:
            _entity_map_cache[eid] = {
                "code": e.get("entity_code", eid),
                "name_en": e.get("entity_name_en", ""),
                "name_ja": e.get("entity_name_ja", ""),
                "name_zh": e.get("entity_name_zh", ""),
                "country": e.get("country", ""),
            }
    return _entity_map_cache


def entity_label(entity_id: str, lang: str = "zh") -> str:
    """Return human-readable entity label: code - name (country)."""
    if not entity_id:
        return ""
    em = _load_entity_map()
    ent = em.get(entity_id)
    if not ent:
        return entity_id  # fallback to raw id if not found in masterdata
    code = ent["code"]
    if lang == "zh":
        name = ent["name_zh"] or ent["name_en"]
    elif lang == "ja":
        name = ent["name_ja"] or ent["name_en"]
    else:
        name = ent["name_en"]
    country = ent["country"]
    if name:
        label = f"{code} - {name}"
        if country:
            label += f" ({country})"
        return label
    if country:
        return f"{code} ({country})"
    return code


def entity_code(entity_id: str) -> str:
    """Return just the entity code (e.g., 'TASG') without the full name — for space-constrained views."""
    if not entity_id:
        return ""
    em = _load_entity_map()
    ent = em.get(entity_id)
    if not ent:
        return entity_id  # fallback to raw id if not found in masterdata
    return ent.get("code", entity_id)


def entity_options_html(entity_id_list: list[str], selected: str, lang: str = "zh") -> str:
    """Build <option> tags for an entity dropdown, with human-readable labels."""
    opts = []
    for eid in entity_id_list:
        label = entity_label(eid, lang)
        sel = " selected" if eid == selected else ""
        opts.append(f'<option value="{escape(eid)}"{sel}>{escape(label)}</option>')
    return "".join(opts)


def all_entity_options_html(selected: str, lang: str = "zh") -> str:
    """Build <option> tags for ALL entities from masterdata (not just SG salary master)."""
    em = _load_entity_map()
    opts = ['<option value="">-- Select Entity / 选择法人 --</option>']
    for eid in sorted(em.keys(), key=lambda x: em[x].get("code", "")):
        label = entity_label(eid, lang)
        sel = " selected" if eid == selected else ""
        opts.append(f'<option value="{escape(eid)}"{sel}>{escape(label)}</option>')
    return "".join(opts)


def currency_options(selected: str = "SGD", lang: str = "zh") -> str:
    """Build <option> tags for supported payroll currencies with human-readable labels."""
    opts = []
    for cur in SUPPORTED_CURRENCIES:
        label = CURRENCY_LABELS.get(cur, {}).get(lang, cur)
        sel = " selected" if cur == selected else ""
        opts.append(f'<option value="{escape(cur)}"{sel}>{escape(label)}</option>')
    return "".join(opts)


def sg_entity_ids() -> list[str]:
    """Return entity_id values for Singapore entities from masterdata."""
    try:
        entities = load_json(MASTERDATA_ENTITIES_PATH, [])
        return sorted([
            e["entity_id"] for e in entities
            if e.get("status") == "active" and e.get("country", "").strip().lower() in {"singapore", "sg"}
        ])
    except Exception:
        return ["ENT-0002"]  # fallback: TASG


def distinct_sg_entities() -> list[str]:
    """Return sorted distinct entity_id values from active SG salary master records."""
    sg_ids = set(sg_entity_ids())
    entities: set[str] = set()
    for row in load_salary_master():
        if not row.get("active") or row.get("entity_id") not in sg_ids:
            continue
        if not is_active_employee_status(row.get("employment_status")):
            continue
        if row.get("employeeadmin_status") and not is_active_employee_status(row.get("employeeadmin_status")):
            continue
        ent = clean(row.get("entity_id"))
        if ent:
            entities.add(ent)
    return sorted(entities)


def distinct_departments() -> list[str]:
    """Return sorted distinct department_label values from active SG salary master records."""
    sg_ids = set(sg_entity_ids())
    depts: set[str] = set()
    for row in load_salary_master():
        if not row.get("active") or row.get("entity_id") not in sg_ids:
            continue
        if not is_active_employee_status(row.get("employment_status")):
            continue
        if row.get("employeeadmin_status") and not is_active_employee_status(row.get("employeeadmin_status")):
            continue
        dept = clean(row.get("department_label") or row.get("department"))
        if dept:
            depts.add(dept)
    return sorted(depts)


def distinct_teams() -> list[str]:
    """Return sorted distinct team_label values from active SG salary master records."""
    sg_ids = set(sg_entity_ids())
    teams: set[str] = set()
    for row in load_salary_master():
        if not row.get("active") or row.get("entity_id") not in sg_ids:
            continue
        if not is_active_employee_status(row.get("employment_status")):
            continue
        if row.get("employeeadmin_status") and not is_active_employee_status(row.get("employeeadmin_status")):
            continue
        team = clean(row.get("team_label") or row.get("team_id"))
        if team:
            teams.add(team)
    return sorted(teams)


def load_batches() -> list[dict[str, Any]]:
    return load_json(PAYROLL_BATCHES_PATH, [])


def save_batches(rows: list[dict[str, Any]]) -> None:
    save_json(PAYROLL_BATCHES_PATH, rows)


def load_records() -> list[dict[str, Any]]:
    return load_json(PAYROLL_RECORDS_PATH, [])


def save_records(rows: list[dict[str, Any]]) -> None:
    save_json(PAYROLL_RECORDS_PATH, rows)


def load_parameters() -> list[dict[str, Any]]:
    return load_json(PAYROLL_PARAMETERS_PATH, default_parameters())


def default_parameters() -> list[dict[str, Any]]:
    return [
        {
            "parameter_id": "SG-CPF-MANUAL-SAFE",
            "country_code": "SG",
            "parameter_type": "sg_cpf",
            "effective_start_date": "2026-01-01",
            "effective_end_date": "2099-12-31",
            "status": "active",
            "description": "Reference placeholder. Validate statutory rates before production use.",
            "values": {
                "cpf_employee_rate": 0,
                "cpf_employer_rate": 0,
                "ordinary_wage_ceiling": 0,
                "additional_wage_ceiling": 0,
                "force_parameter_calculation": False,
            },
        }
    ]


def active_parameters() -> list[dict[str, Any]]:
    return [p for p in load_parameters() if p.get("country_code") == "SG" and p.get("status") == "active"]


def next_batch_id(month: str, entity_id: str) -> str:
    return f"PAYSG-{month.replace('-', '')}-{slug(entity_id)}"


def next_record_id(batch_id: str, employee_id: str) -> str:
    return f"{batch_id}-{slug(employee_id)}"


def find_batch(batch_id: str) -> dict[str, Any] | None:
    return next((b for b in load_batches() if b.get("batch_id") == batch_id), None)


def batch_records(batch_id: str) -> list[dict[str, Any]]:
    return [r for r in load_records() if r.get("batch_id") == batch_id]


def create_batch(month: str, entity_id: str, employee_ids: list[str] | None = None) -> tuple[dict[str, Any], int]:
    month = month or datetime.now().strftime("%Y-%m")
    entity_id = entity_id or "SG"
    batch_id = next_batch_id(month, entity_id)
    batches = load_batches()
    existing = next((b for b in batches if b.get("batch_id") == batch_id), None)
    if existing:
        return existing, 0
    all_employees = active_sg_salary_master(entity_id)
    if employee_ids is not None:
        id_set = set(employee_ids)
        employees = [e for e in all_employees if e.get("employee_id") in id_set]
    else:
        employees = all_employees
    batch = {
        "batch_id": batch_id,
        "country_code": "SG",
        "entity_id": entity_id,
        "payroll_month": month,
        "status": "draft",
        "version": 1,
        "employee_count": len(employees),
        "gross_total": 0,
        "deduction_total": 0,
        "net_total": 0,
        "employer_cost_total": 0,
        "currency_totals": {},
        "created_at": now_iso(),
        "updated_at": now_iso(),
        "created_by": USER_ACTOR,
        "notes": "",
    }
    records = load_records()
    for employee in employees:
        records.append(create_record_from_master(batch, employee))
    batches.append(batch)
    save_batches(batches)
    save_records(records)
    append_audit("tacaipaysg.batch", batch_id, "create_batch", None, batch)
    return batch, len(employees)


def create_record_from_master(batch: dict[str, Any], employee: dict[str, Any]) -> dict[str, Any]:
    _, days = monthrange(int(batch["payroll_month"][:4]), int(batch["payroll_month"][5:7]))
    work_days = min(employee.get("standard_work_days") or 22, days)
    return {
        "record_id": next_record_id(batch["batch_id"], employee["employee_id"]),
        "batch_id": batch["batch_id"],
        "payroll_month": batch["payroll_month"],
        "country_code": "SG",
        "entity_id": employee["entity_id"],
        "employee_id": employee["employee_id"],
        "employee_number": employee["employee_number"],
        "employee_name": employee["employee_name"],
        "email": employee["email"],
        "salary_type": employee["salary_type"],
        "basic_salary": employee["basic_salary"],
        "hourly_rate": employee["hourly_rate"],
        "daily_rate": employee["daily_rate"],
        "standard_work_days": employee["standard_work_days"],
        "standard_work_hours": employee["standard_work_hours"],
        "standard_monthly_hours": employee.get("standard_monthly_hours", employee["standard_work_hours"]),
        "overtime_hourly_rate": employee.get("overtime_hourly_rate", 0),
        "work_days": work_days,
        "work_hours": employee["standard_work_hours"],
        "actual_work_days": employee.get("actual_work_days", work_days),
        "actual_work_hours": employee.get("actual_work_hours", employee["standard_work_hours"]),
        "paid_leave_days": employee.get("paid_leave_days", 0),
        "unpaid_leave_days": employee.get("unpaid_leave_days", 0),
        "sick_leave_days": employee.get("sick_leave_days", 0),
        "overtime_hours": employee.get("overtime_hours", 0),
        "late_night_hours": employee.get("late_night_hours", 0),
        "holiday_hours": employee.get("holiday_hours", 0),
        "absence_days": employee.get("absence_days", 0),
        "fixed_allowance": employee["fixed_allowance"],
        "performance_bonus": employee["performance_bonus"],
        "bonus": 0,
        "other_payment": 0,
        "recurring_deductions": employee["recurring_deductions"],
        "other_deduction": 0,
        "income_tax": 0,
        "cpf_applicable": employee["cpf_applicable"],
        "cpf_input_mode": employee["cpf_input_mode"],
        "cpf_employee": employee["cpf_employee_manual"],
        "cpf_employer": employee["cpf_employer_manual"],
        "skill_development_levy": employee["skill_development_levy"],
        "foreign_worker_levy": employee["foreign_worker_levy"],
        "gross_pay": 0,
        "deduction_total": 0,
        "net_pay": 0,
        "employer_cost_total": 0,
        "status": "draft",
        "calculation_messages": [],
        "employee_confirmation_status": "pending",
        "employee_comment": "",
        "bank_name": employee["bank_name"],
        "bank_branch_name": employee.get("bank_branch_name", ""),
        "bank_swift_code": employee.get("bank_swift_code", ""),
        "bank_account_type": employee.get("bank_account_type", "ordinary"),
        "bank_account_name": employee["bank_account_name"],
        "bank_account_number": employee["bank_account_number"],
        "payroll_currency": employee["payroll_currency"],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }


def calculate_record(record: dict[str, Any], parameters: list[dict[str, Any]]) -> dict[str, Any]:
    messages: list[str] = []
    salary_type = clean(record.get("salary_type") or "monthly")
    if salary_type == "hourly":
        actual_hours = money(record.get("actual_work_hours") or record.get("work_hours") or 0)
        hourly_rate = money(record.get("hourly_rate"))
        ot_rate = money(record.get("overtime_hourly_rate")) or 0
        std_hours = money(record.get("standard_work_hours") or record.get("standard_monthly_hours") or 160)
        if ot_rate > 0:
            regular_hours = min(actual_hours, std_hours)
            ot_hours = max(0.0, actual_hours - std_hours)
            base = round(hourly_rate * regular_hours + ot_rate * ot_hours, 2)
            if ot_hours > 0:
                messages.append(f"Overtime: {ot_hours}h × {ot_rate}/h")
        else:
            base = round(hourly_rate * actual_hours, 2)
    elif salary_type == "daily":
        actual_days = money(record.get("actual_work_days") or record.get("work_days") or 0)
        base = money(record.get("daily_rate")) * actual_days
    elif salary_type == "monthly_hour":
        basic_salary = money(record.get("basic_salary"))
        hourly_rate = money(record.get("hourly_rate"))
        overtime_rate = money(record.get("overtime_hourly_rate"))
        standard_hours = money(record.get("standard_work_hours") or record.get("standard_monthly_hours") or 160)
        actual_hours = money(record.get("actual_work_hours") or record.get("work_hours") or 0)
        # Base salary: fully earned if actual_hours >= standard_hours, else prorated
        if actual_hours >= standard_hours:
            base_salary_earned = basic_salary
        else:
            base_salary_earned = round(basic_salary * actual_hours / max(standard_hours, 1), 2)
            messages.append(f"Basic salary prorated: {actual_hours}/{standard_hours} hours.")
        # Standard hours pay at hourly_rate
        regular_hours = min(actual_hours, standard_hours)
        regular_pay = round(hourly_rate * regular_hours, 2)
        # Overtime pay for hours exceeding standard_hours
        overtime_hours = max(0.0, actual_hours - standard_hours)
        overtime_pay = round(overtime_rate * overtime_hours, 2)
        if overtime_hours > 0:
            messages.append(f"Overtime: {overtime_hours}h × {overtime_rate}/h = {overtime_pay}")
        base = round(base_salary_earned + regular_pay + overtime_pay, 2)
    else:
        standard_days = money(record.get("standard_work_days")) or 22
        payable_days = money(record.get("work_days")) + money(record.get("paid_leave_days")) + money(record.get("sick_leave_days"))
        base = money(record.get("basic_salary")) * min(payable_days / max(standard_days, 1), 1)
    gross = base + money(record.get("fixed_allowance")) + money(record.get("performance_bonus")) + money(record.get("bonus")) + money(record.get("other_payment"))
    cpf_employee = money(record.get("cpf_employee"))
    cpf_employer = money(record.get("cpf_employer"))
    if not bool(record.get("cpf_applicable", False)):
        cpf_employee = 0
        cpf_employer = 0
        messages.append("CPF not applicable; CPF amounts set to zero.")
    elif clean(record.get("cpf_input_mode")) == "parameter_assisted":
        cpf_param = next((p for p in parameters if "cpf" in clean(p.get("parameter_type")).lower()), None)
        values = cpf_param.get("values", {}) if cpf_param else {}
        employee_rate = money(values.get("cpf_employee_rate"))
        employer_rate = money(values.get("cpf_employer_rate"))
        if employee_rate > 1:
            employee_rate = employee_rate / 100
        if employer_rate > 1:
            employer_rate = employer_rate / 100
        ordinary_ceiling = money(values.get("ordinary_wage_ceiling"))
        wage_base = min(gross, ordinary_ceiling) if ordinary_ceiling > 0 else gross
        if cpf_param and employee_rate and employer_rate:
            cpf_employee = round(wage_base * employee_rate, 2)
            cpf_employer = round(wage_base * employer_rate, 2)
            messages.append(f"CPF parameter-assisted by {cpf_param.get('parameter_id')}.")
        else:
            messages.append("CPF kept manual because no validated CPF parameter rate exists.")
    deduction_total = cpf_employee + money(record.get("recurring_deductions")) + money(record.get("other_deduction")) + money(record.get("income_tax"))
    employer_cost_total = gross + cpf_employer + money(record.get("skill_development_levy")) + money(record.get("foreign_worker_levy"))
    record.update({
        "base_pay_calculated": round(base, 2),
        "gross_pay": round(gross, 2),
        "cpf_employee": round(cpf_employee, 2),
        "cpf_employer": round(cpf_employer, 2),
        "deduction_total": round(deduction_total, 2),
        "net_pay": round(gross - deduction_total, 2),
        "employer_cost_total": round(employer_cost_total, 2),
        "status": "calculated",
        "calculation_messages": messages,
        "updated_at": now_iso(),
    })
    return record


def recalc_batch_totals(batch_id: str) -> None:
    batches = load_batches()
    records = batch_records(batch_id)
    for batch in batches:
        if batch.get("batch_id") == batch_id:
            batch["employee_count"] = len(records)
            batch["gross_total"] = round(sum(money(r.get("gross_pay")) for r in records), 2)
            batch["deduction_total"] = round(sum(money(r.get("deduction_total")) for r in records), 2)
            batch["net_total"] = round(sum(money(r.get("net_pay")) for r in records), 2)
            batch["employer_cost_total"] = round(sum(money(r.get("employer_cost_total")) for r in records), 2)
            batch["currency_totals"] = compute_currency_totals(records)
            batch["updated_at"] = now_iso()
    save_batches(batches)


def calculate_batch(batch_id: str) -> None:
    parameters = active_parameters()
    records = load_records()
    before = [r for r in records if r.get("batch_id") == batch_id]
    for record in records:
        if record.get("batch_id") == batch_id:
            calculate_record(record, parameters)
    save_records(records)
    batches = load_batches()
    for batch in batches:
        if batch.get("batch_id") == batch_id:
            batch["status"] = "calculated"
            batch["updated_at"] = now_iso()
    save_batches(batches)
    recalc_batch_totals(batch_id)
    append_audit("tacaipaysg.batch", batch_id, "calculate_batch", before, batch_records(batch_id))


# Valid transitions for the legacy batch system (only used for bridged finalized sheets)
VALID_BATCH_TRANSITIONS: dict[str, set[str]] = {
    "draft": {"calculated"},
    "calculated": {"hr_reviewed"},
    "hr_reviewed": {"finalized"},       # merged: approved + finalized → 批准定案
    "finalized": {"payslips_generated"},
    "payslips_generated": {"sent_to_employees"},
    "sent_to_employees": {"employee_confirmed"},
    "employee_confirmed": {"released_to_finance"},
    "released_to_finance": {"paid"},
    "any": {"correction", "voided"},
}

# ── Return targets for batch workflow (one step back) ──
BATCH_RETURN_TARGETS: dict[str, str] = {
    "calculated": "draft",
    "hr_reviewed": "calculated",
    "finalized": "hr_reviewed",         # merged: finalized returns to hr_reviewed
    "payslips_generated": "finalized",
    "sent_to_employees": "payslips_generated",
    "employee_confirmed": "sent_to_employees",
    "released_to_finance": "employee_confirmed",
    "paid": "released_to_finance",
}

def transition_batch(batch_id: str, to_status: str, action: str) -> bool:
    """Transition a legacy batch with status validation."""
    batches = load_batches()
    for batch in batches:
        if batch.get("batch_id") == batch_id:
            cur = batch.get("status", "draft")
            allowed = VALID_BATCH_TRANSITIONS.get(cur, set()) | VALID_BATCH_TRANSITIONS.get("any", set())
            if to_status not in allowed and cur != to_status:
                return False
            before = dict(batch)
            batch["status"] = to_status
            batch["updated_at"] = now_iso()
            save_batches(batches)
            append_audit("tacaipaysg.batch", batch_id, action, before, dict(batch))
            return True
    return False


def void_batch(batch_id: str) -> bool:
    """Void a batch and all its records. Only allowed for non-locked batches."""
    batch = find_batch(batch_id)
    if not batch:
        return False
    if batch.get("status") in LOCKED_BATCH_STATUSES and batch.get("status") != "voided":
        return False  # Can't void a batch that's already locked in payment flow
    batches = load_batches()
    records = load_records()
    before_batch = None
    for b in batches:
        if b.get("batch_id") == batch_id:
            before_batch = dict(b)
            b["status"] = "voided"
            b["updated_at"] = now_iso()
    save_batches(batches)
    before_records = []
    for r in records:
        if r.get("batch_id") == batch_id:
            before_records.append(dict(r))
            r["status"] = "voided"
            r["updated_at"] = now_iso()
    save_records(records)
    append_audit("tacaipaysg.batch", batch_id, "void_batch", before_batch, find_batch(batch_id))
    append_audit("tacaipaysg.record", batch_id, "void_batch_records", before_records, [r for r in records if r.get("batch_id") == batch_id])
    return True


def return_batch_to_prev_step(batch_id: str, comment: str = "") -> bool:
    """Return a batch to its previous status. One step back only."""
    batch = find_batch(batch_id)
    if not batch:
        return False
    cur_status = batch.get("status", "draft")
    if cur_status in ("draft", "correction", "voided", "paid"):
        return False  # Cannot return from draft, correction, voided, or paid status
    target = BATCH_RETURN_TARGETS.get(cur_status)
    if not target:
        return False

    # If locked, only allow return from approved or earlier
    if cur_status in LOCKED_BATCH_STATUSES and cur_status not in ("approved",):
        # For statuses like finalized, payslips_generated, etc., one step back is allowed
        pass

    batches = load_batches()
    before = None
    for b in batches:
        if b.get("batch_id") == batch_id:
            before = dict(b)
            b["status"] = target
            b["updated_at"] = now_iso()

    # Clear stage-specific results based on current status
    if cur_status == "calculated":
        # Clear calculation results on records
        records = load_records()
        for r in records:
            if r.get("batch_id") == batch_id:
                for key in ("gross_pay", "cpf_employee", "cpf_employer",
                            "skill_development_levy", "foreign_worker_levy",
                            "deduction_total", "net_pay", "employer_cost_total",
                            "base_pay_calculated", "calculation_messages"):
                    if key in r:
                        r[key] = 0 if key != "calculation_messages" else []
                r["updated_at"] = now_iso()
        save_records(records)
        # Recalculate batch totals (should be zero)
        recalc_batch_totals(batch_id)

    if cur_status == "payslips_generated":
        # Clear generated payslips
        payslips = load_json(PAYSLIPS_PATH, [])
        for ps in payslips:
            if ps.get("batch_id") == batch_id:
                ps["status"] = "voided"
                ps["file_name"] = ""
                ps["file_path"] = ""
        save_json(PAYSLIPS_PATH, payslips)

    if cur_status == "sent_to_employees":
        # Clear email deliveries
        deliveries = load_json(EMAIL_DELIVERIES_PATH, [])
        for d in deliveries:
            if d.get("batch_id") == batch_id:
                d["status"] = "voided"
        save_json(EMAIL_DELIVERIES_PATH, deliveries)
        # Also clear payslips
        payslips = load_json(PAYSLIPS_PATH, [])
        for ps in payslips:
            if ps.get("batch_id") == batch_id:
                ps["status"] = "voided"
                ps["file_name"] = ""
                ps["file_path"] = ""
        save_json(PAYSLIPS_PATH, payslips)

    save_batches(batches)
    after = find_batch(batch_id)
    after_val = dict(after) if after else {}
    after_val["_return_comment"] = comment
    append_audit("tacaipaysg.batch", batch_id, "return_step", before, after_val)
    return True


def update_record_from_form(record_id: str, form: dict[str, list[str]]) -> None:
    records = load_records()
    before = None
    after = None
    fields = ["work_days", "work_hours", "fixed_allowance", "performance_bonus", "bonus", "other_payment", "recurring_deductions", "other_deduction", "income_tax", "cpf_employee", "cpf_employer", "skill_development_levy", "foreign_worker_levy", "payroll_currency", "employee_confirmation_status", "employee_comment"]
    for record in records:
        if record.get("record_id") == record_id:
            before = dict(record)
            for field in fields:
                if field in form:
                    value = form[field][0]
                    record[field] = clean(value) if field in {"employee_confirmation_status", "employee_comment", "payroll_currency"} else money(value)
            record["updated_at"] = now_iso()
            after = dict(record)
    save_records(records)
    if after:
        append_audit("tacaipaysg.record", record_id, "update_record", before, after)


def fetch_employeeadmin_payroll_employees(session_id: str = "", **filters: Any) -> tuple[list[dict[str, Any]], str]:
    params = {"country_code": filters.pop("country_code", "SG")}
    params.update({key: value for key, value in filters.items() if value not in (None, "")})
    url = f"{EMPLOYEEADMIN_INTERNAL_BASE_URL}/api/payroll/employees?{urlencode(params)}"
    headers = {"Accept": "application/json"}
    if session_id:
        headers["Cookie"] = f"{USER_ADMIN_SESSION_COOKIE}={session_id}"
    try:
        req = Request(url, headers=headers)
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return [], f"EmployeeAdmin not available: {exc}"
    employees = payload.get("employees") if isinstance(payload, dict) else payload
    if not isinstance(employees, list):
        return [], "EmployeeAdmin response did not contain an employee list."
    return [emp for emp in employees if isinstance(emp, dict)], ""


def employeeadmin_identity_snapshot(emp: dict[str, Any]) -> dict[str, Any] | None:
    employee_id = clean(first_present(emp.get("employee_id"), emp.get("employee_number"), emp.get("employee_no")))
    if not employee_id:
        return None
    employment = emp.get("employment") if isinstance(emp.get("employment"), dict) else {}
    profile = emp.get("profile") if isinstance(emp.get("profile"), dict) else {}
    country = clean(first_present(employment.get("country_code"), emp.get("country_code"), emp.get("work_country"), emp.get("country"))).upper() or "SG"
    status = first_present(employment.get("employment_status"), employment.get("status"), emp.get("employment_status"), emp.get("status"), "active")
    department_label = first_present(emp.get("department_label"), employment.get("department_name"), emp.get("department"), emp.get("department_id"), employment.get("department_id"))
    return {
        "employee_id": employee_id,
        "employee_number": first_present(emp.get("employee_number"), emp.get("employee_no"), employee_id),
        "employee_name": first_present(emp.get("display_name"), emp.get("employee_name"), profile.get("display_name"), profile.get("full_name")),
        "email": first_present(emp.get("email"), profile.get("company_email"), profile.get("personal_email")),
        "country_code": country,
        "entity_id": first_present(employment.get("entity_id"), emp.get("entity_id"), "SG"),
        "department": department_label,
        "department_id": first_present(emp.get("department_id"), employment.get("department_id")),
        "department_label": department_label,
        "team_id": first_present(emp.get("team_id"), employment.get("team_id")),
        "team_label": first_present(emp.get("team_label"), employment.get("team_name")),
        "employment_status": status,
        "employeeadmin_status": status,
        "employeeadmin_payroll_ready": normalize_bool(emp.get("payroll_ready"), False),
        "employeeadmin_readiness_percent": emp.get("payroll_readiness_percent"),
        "employeeadmin_last_seen_at": now_iso(),
        "source": "employeeadmin",
    }


def payroll_defaults_from_employeeadmin(emp: dict[str, Any]) -> dict[str, Any]:
    payroll = emp.get("payroll") if isinstance(emp.get("payroll"), dict) else {}
    bank = payroll.get("bank") if isinstance(payroll.get("bank"), dict) else {}
    return {
        "salary_type": first_present(payroll.get("salary_type"), emp.get("salary_type"), "monthly"),
        "basic_salary": first_present(
            payroll.get("monthly_base_salary"),
            payroll.get("base_salary"),
            payroll.get("basic_salary"),
            emp.get("base_salary"),
            emp.get("basic_salary"),
        ),
        "hourly_rate": first_present(
            payroll.get("hourly_wage"),
            payroll.get("hourly_rate"),
            emp.get("hourly_wage"),
            emp.get("hourly_rate"),
        ),
        "daily_rate": first_present(
            payroll.get("daily_wage"),
            payroll.get("daily_rate"),
            emp.get("daily_wage"),
            emp.get("daily_rate"),
        ),
        "bank_name": first_present(payroll.get("bank_name"), bank.get("bank_name"), emp.get("bank_name")),
        "bank_branch_name": first_present(bank.get("branch_name"), ""),
        "bank_swift_code": first_present(bank.get("swift_code"), ""),
        "bank_account_type": first_present(bank.get("account_type"), "ordinary"),
        "bank_account_name": first_present(payroll.get("bank_account_name"), bank.get("account_holder"), emp.get("bank_account_name")),
        "bank_account_number": first_present(payroll.get("bank_account_number"), bank.get("account_number"), emp.get("bank_account_number")),
        "employeeadmin_bank_snapshot": dict(bank) if bank else {},
        "payroll_currency": first_present(payroll.get("payroll_currency"), emp.get("payroll_currency"), "SGD"),
    }


def employeeadmin_salary_master_row(emp: dict[str, Any]) -> dict[str, Any] | None:
    snapshot = employeeadmin_identity_snapshot(emp)
    if not snapshot:
        return None
    return normalize_salary_master({**snapshot, **payroll_defaults_from_employeeadmin(emp)})


def merge_employeeadmin_salary_master(existing: dict[str, Any] | None, emp: dict[str, Any], mode: str) -> dict[str, Any] | None:
    snapshot = employeeadmin_identity_snapshot(emp)
    if not snapshot:
        return None
    defaults = payroll_defaults_from_employeeadmin(emp)
    if existing is None:
        return normalize_salary_master({**snapshot, **defaults, "active": True})
    merged = dict(existing)
    for key, value in snapshot.items():
        if value not in (None, ""):
            merged[key] = value
    for key, value in defaults.items():
        if key == "employeeadmin_bank_snapshot":
            # Always refresh bank snapshot from EmployeeAdmin (reference only)
            if value:
                merged[key] = value
        elif merged.get(key) in (None, "", 0, 0.0) and value not in (None, ""):
            merged[key] = value
    if mode == "regenerate":
        merged["active"] = True
        merged["deactivated_at"] = ""
        merged["deactivated_by"] = ""
        merged["deactivation_reason"] = ""
    merged["source"] = "employeeadmin"
    merged["updated_at"] = now_iso()
    return normalize_salary_master(merged)


def import_from_employeeadmin(session_id: str = "") -> dict[str, Any]:
    # Fetch all active employees from EmployeeAdmin (no country_code filter)
    # Then filter by Singapore entity IDs on our side
    employees, error = fetch_employeeadmin_payroll_employees(session_id, country_code="")
    if error:
        return {"ok": False, "created": 0, "refreshed": 0, "regenerated": 0, "skipped": 0, "incomplete": 0, "message": error}
    sg_ids = set(sg_entity_ids())
    # Filter to only employees belonging to Singapore entities
    employees = [e for e in employees if e.get("entity_id") in sg_ids]
    rows = load_salary_master()
    index = {row["employee_id"]: i for i, row in enumerate(rows)}
    created = 0
    refreshed = 0
    regenerated = 0
    skipped = 0
    incomplete = 0
    before_summary = {row["employee_id"]: dict(row) for row in rows}
    for emp in employees:
        snapshot = employeeadmin_identity_snapshot(emp)
        if not snapshot or not is_active_employee_status(snapshot.get("employeeadmin_status")):
            skipped += 1
            continue
        employee_id = snapshot["employee_id"]
        current = rows[index[employee_id]] if employee_id in index else None
        mode = "create" if current is None else ("refresh" if current.get("active") else "regenerate")
        row = merge_employeeadmin_salary_master(current, emp, mode)
        if not row:
            skipped += 1
            continue
        if not row.get("basic_salary") or not (row.get("bank_name") and row.get("bank_account_number")):
            incomplete += 1
        if current is None:
            rows.append(row)
            index[employee_id] = len(rows) - 1
            created += 1
            append_audit("tacaipaysg.salary_master", employee_id, "create_salary_master", None, row)
        else:
            before = dict(current)
            rows[index[employee_id]] = row
            if mode == "regenerate":
                regenerated += 1
                append_audit("tacaipaysg.salary_master", employee_id, "regenerate_salary_master", before, row)
            else:
                refreshed += 1
                append_audit("tacaipaysg.salary_master", employee_id, "refresh_employeeadmin_snapshot", before, row)
    save_salary_master(rows)
    result = {
        "ok": True,
        "created": created,
        "refreshed": refreshed,
        "regenerated": regenerated,
        "skipped": skipped,
        "incomplete": incomplete,
        "message": f"EmployeeAdmin SG sync complete: created {created}, refreshed {refreshed}, regenerated {regenerated}, skipped {skipped}, incomplete {incomplete}.",
    }
    append_audit("tacaipaysg.salary_master", "employeeadmin", "import_employeeadmin_salary_master", before_summary, result)
    return result


def upsert_salary_master(form: dict[str, list[str]]) -> dict[str, Any]:
    employee_id = clean((form.get("employee_id") or [""])[0])
    row = normalize_salary_master({key: values[0] for key, values in form.items()})
    row["active"] = normalize_bool((form.get("active") or ["false"])[0], False)
    row["cpf_applicable"] = normalize_bool((form.get("cpf_applicable") or ["false"])[0], False)
    rows = load_salary_master()
    before = None
    replaced = False
    for i, current in enumerate(rows):
        if current.get("employee_id") == employee_id:
            before = current
            if current.get("source") == "employeeadmin":
                protected = normalize_salary_master(current)
                for field in EMPLOYEEADMIN_IDENTITY_FIELDS:
                    row[field] = protected.get(field, row.get(field))
                row["source"] = "employeeadmin"
            row["salary_master_id"] = current.get("salary_master_id", row["salary_master_id"])
            row["created_at"] = current.get("created_at", row["created_at"])
            row["updated_at"] = now_iso()
            rows[i] = normalize_salary_master(row)
            replaced = True
            break
    if not replaced:
        row["source"] = clean(row.get("source")) or "manual"
        rows.append(normalize_salary_master(row))
    save_salary_master(rows)
    action = "update_salary_master" if before else "create_salary_master"
    saved = normalize_salary_master(row)
    append_audit("tacaipaysg.salary_master", saved["employee_id"], action, before, saved)
    return saved


def create_salary_master_batch(employee_ids: list[str], session_id: str = "", entity_id: str = "") -> dict[str, Any]:
    """Create salary master records for selected employees from EmployeeAdmin.

    Creation rules:
    - Employee code must exist and employee must be active (在职).
    - If salary info is incomplete, only warn — still create the record.
    - Employees already in salary master are skipped.
    """
    if not employee_ids:
        return {"ok": False, "created": 0, "skipped": 0, "incomplete": 0, "message": "No employees selected."}

    # Fetch all active employees from EmployeeAdmin (no country_code filter)
    # Then filter by Singapore entity IDs on our side
    employees, error = fetch_employeeadmin_payroll_employees(
        session_id, country_code="",
    )
    if error:
        return {"ok": False, "created": 0, "skipped": 0, "incomplete": 0, "message": error}
    sg_ids = set(sg_entity_ids())
    employees = [e for e in employees if e.get("entity_id") in sg_ids]

    # Build lookup by employee_id
    emp_lookup: dict[str, dict[str, Any]] = {}
    for emp in employees:
        eid = clean(first_present(emp.get("employee_id"), emp.get("employee_number"), emp.get("employee_no")))
        if eid:
            emp_lookup[eid] = emp

    rows = load_salary_master()
    existing_ids = {r["employee_id"] for r in rows}

    created = 0
    skipped = 0
    incomplete = 0

    for employee_id in employee_ids:
        if not employee_id or employee_id in existing_ids:
            skipped += 1
            continue

        emp = emp_lookup.get(employee_id)
        if not emp:
            skipped += 1
            continue

        # Only requirement: employee is active (在职)
        snapshot = employeeadmin_identity_snapshot(emp)
        if not snapshot:
            skipped += 1
            continue
        if not is_active_employee_status(snapshot.get("employeeadmin_status")):
            skipped += 1
            continue

        # Create salary master row from EmployeeAdmin data
        row = employeeadmin_salary_master_row(emp)
        if not row:
            skipped += 1
            continue

        # Check payroll completeness — warn but still create
        readiness = salary_master_readiness(row)
        if not readiness["ready"]:
            incomplete += 1

        rows.append(row)
        existing_ids.add(employee_id)
        created += 1
        append_audit("tacaipaysg.salary_master", employee_id, "create_salary_master", None, row)

    save_salary_master(rows)

    parts = [f"Created {created} salary master record(s)."]
    if incomplete > 0:
        parts.append(f"{incomplete} record(s) have incomplete payroll info — please review and complete salary/bank fields.")
    if skipped > 0:
        parts.append(f"{skipped} employee(s) skipped (already exist, not found, or inactive).")
    message = " ".join(parts)

    return {"ok": True, "created": created, "skipped": skipped, "incomplete": incomplete, "message": message}


def deactivate_salary_master(employee_id: str, reason: str = "", user: str = USER_ACTOR) -> bool:
    rows = load_salary_master()
    for i, row in enumerate(rows):
        if row.get("employee_id") == employee_id:
            before = dict(row)
            row["active"] = False
            row["deactivated_at"] = now_iso()
            row["deactivated_by"] = user or USER_ACTOR
            row["deactivation_reason"] = clean(reason)
            row["updated_at"] = now_iso()
            rows[i] = normalize_salary_master(row)
            save_salary_master(rows)
            append_audit("tacaipaysg.salary_master", employee_id, "deactivate_salary_master", before, rows[i], user or USER_ACTOR)
            return True
    return False


def csv_response(rows: list[dict[str, Any]], headers: list[str]) -> bytes:
    out = StringIO()
    out.write("﻿")
    writer = csv.DictWriter(out, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8")


def pdf_escape(text: str) -> str:
    return clean(text).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def simple_pdf_bytes(lines: list[str]) -> bytes:
    """Generate a minimal PDF with ASCII-safe text lines. Non-latin-1 chars are stripped."""
    safe_lines = [line.encode("latin-1", "replace").decode("latin-1") for line in lines]
    stream = "BT /F1 11 Tf 50 790 Td 14 TL " + " ".join(f"({pdf_escape(line)}) Tj T*" for line in safe_lines) + " ET"
    stream_bytes = stream.encode("latin-1", "replace")
    objects = [
        "1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        "2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        "3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >> endobj",
        "4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        f"5 0 obj << /Length {len(stream_bytes)} >> stream\n{stream}\nendstream endobj",
    ]
    body = "%PDF-1.4\n"
    offsets: list[int] = [0]
    for obj in objects:
        offsets.append(len(body.encode("latin-1")))
        body += obj + "\n"
    xref_start = len(body.encode("latin-1"))
    body += f"xref\n0 {len(objects) + 1}\n0000000000 65535 f \n"
    for offset in offsets[1:]:
        body += f"{offset:010d} 00000 n \n"
    body += f"trailer << /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_start}\n%%EOF\n"
    return body.encode("latin-1", "replace")


def generate_payslips(batch_id: str, selected_record_ids: list[str] | None = None) -> int:
    payslips = load_json(PAYSLIPS_PATH, [])
    existing = {p.get("record_id"): p for p in payslips}
    count = 0
    all_records = batch_records(batch_id)
    if selected_record_ids:
        id_set = set(selected_record_ids)
        all_records = [r for r in all_records if r.get("record_id") in id_set]

    # Load salary master for full employee data (dept, bank, allowances, etc.)
    salary_master_list = load_json(SALARY_MASTER_PATH, [])
    master_by_emp_id = {sm.get("employee_id"): sm for sm in salary_master_list}

    # Get entity name from batch
    batch = find_batch(batch_id)
    entity_id = batch.get("entity_id", "") if batch else ""
    entity_name = entity_label(entity_id, "en").split(" - ")[-1].split(" (")[0] if " - " in entity_label(entity_id, "en") else "TAC Alliance"

    for record in all_records:
        filename = f"{slug(record['payroll_month'])}_{slug(record['employee_number'])}_{slug(record['record_id'])}.pdf"
        path = PAYSLIP_DIR / filename

        # Get full salary master data for this employee
        mr_data = master_by_emp_id.get(record.get("employee_id", ""), {})
        # Merge record data with master data for richer payslip
        ps_data = dict(record)
        ps_data["department_label"] = mr_data.get("department_label", "") or record.get("department_label", "")
        ps_data["team_label"] = mr_data.get("team_label", "") or record.get("team_label", "")

        # Generate type-aware payslip PDF
        pdf_bytes = payslip_pdf_bytes(ps_data=ps_data, mr_data=mr_data, entity_name=entity_name)
        path.write_bytes(pdf_bytes)

        payslip = {
            "payslip_id": f"PS-{record['record_id']}",
            "record_id": record["record_id"],
            "batch_id": batch_id,
            "employee_id": record["employee_id"],
            "employee_number": record.get("employee_number", ""),
            "employee_name": record.get("employee_name", ""),
            "employee_email": record.get("email"),
            "department_label": ps_data.get("department_label", ""),
            "file_name": filename,
            "file_path": str(path.relative_to(ROOT_DIR)),
            "status": "generated",
            "gross_pay": record.get("gross_pay", 0),
            "net_pay": record.get("net_pay", 0),
            "salary_type": record.get("salary_type", "monthly"),
            "payroll_month": record.get("payroll_month", ""),
            "created_at": now_iso(),
        }
        existing[record["record_id"]] = payslip
        count += 1
    save_json(PAYSLIPS_PATH, list(existing.values()))
    if count > 0:
        transition_batch(batch_id, "payslips_generated", "generate_payslips")
    return count


# ---------------------------------------------------------------------------
# Message Center integration helpers
# ---------------------------------------------------------------------------
def _tacaimsg_call(endpoint: str, payload: dict) -> dict:
    """Call tacaimsg internal API with token authentication."""
    url = f"{TACAIMSG_INTERNAL_BASE_URL}{endpoint}"
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "X-TACAI-Internal-Token": TACAIMSG_INTERNAL_TOKEN,
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError) as exc:
        return {"code": 0, "error": str(exc)}


def msg_center_available() -> bool:
    """Check if Message Center integration is enabled."""
    if not TAC_PAYSG_MSG_CENTER_ENABLED:
        return False
    try:
        result = _tacaimsg_call("/api/internal/messages/send-batch", {"messages": []})
        return result.get("code") is not None
    except Exception:
        return False


def _resolve_employees_to_users(employee_ids: list[str]) -> dict[str, dict | None]:
    """Resolve employee IDs to User Admin user accounts."""
    # Try tacaimsg internal API first
    result = _tacaimsg_call("/api/internal/users/resolve-employees", {"employee_ids": employee_ids})
    if result.get("code") == 200 and isinstance(result.get("data", {}).get("mapping"), dict):
        return result["data"]["mapping"]

    # Fallback: read User_admin users.json directly
    user_admin_users_path = ROOT_DIR.parent.parent / "TACAI-Core" / "User_admin" / "database" / "users.json"
    mapping: dict[str, dict | None] = {}
    try:
        users = json.loads(user_admin_users_path.read_text(encoding="utf-8"))
        if not isinstance(users, list):
            users = []
    except (FileNotFoundError, json.JSONDecodeError):
        users = []

    user_by_employee: dict[str, dict] = {}
    for u in users:
        linked = str(u.get("linked_employee_id", "")).strip()
        if linked:
            user_by_employee[linked] = u

    for eid in employee_ids:
        u = user_by_employee.get(str(eid).strip())
        if u:
            mapping[eid] = {
                "user_id": u.get("user_id", ""),
                "username": u.get("username", ""),
                "display_name": u.get("display_name", ""),
                "email": u.get("email", ""),
                "entity_id": u.get("entity_id", ""),
                "has_account": True,
            }
        else:
            mapping[eid] = {"has_account": False}
    return mapping


def publish_payslip_notifications_to_msg_center(batch_id: str, payslips: list[dict]) -> dict:
    """Publish payslip notifications to Message Center for employees with accounts.

    Args:
        batch_id: Payroll batch ID.
        payslips: List of payslip dicts (must have employee_id, employee_name, employee_email).

    Returns:
        Dict with sent_count, failed_count, skipped_no_account, results.
    """
    if not TAC_PAYSG_MSG_CENTER_ENABLED:
        return {"sent_count": 0, "failed_count": 0, "skipped_no_account": 0,
                "total": len(payslips), "results": [], "message": "Message Center integration disabled"}

    batches = load_json(PAYROLL_BATCHES_PATH, [])
    batch = next((b for b in batches if b.get("batch_id") == batch_id), None)
    if not batch:
        return {"sent_count": 0, "failed_count": 0, "skipped_no_account": 0,
                "total": len(payslips), "results": [], "message": "Batch not found"}

    payroll_month = batch.get("payroll_month", "")
    entity_id = batch.get("entity_id", "")
    entity_name = batch.get("entity_name", entity_id)
    currency = batch.get("currency", "SGD")

    # Collect employee IDs
    employee_ids = [str(p.get("employee_id", "")).strip() for p in payslips if p.get("employee_id")]

    # Resolve to user accounts
    user_mapping = _resolve_employees_to_users(employee_ids)

    # Build message payloads
    messages_payload = []
    skipped_eids = []

    for p in payslips:
        eid = str(p.get("employee_id", "")).strip()
        user_info = user_mapping.get(eid)
        if not user_info or not user_info.get("has_account"):
            skipped_eids.append(eid)
            continue

        employee_name = p.get("employee_name", eid)
        gross_pay = p.get("gross_pay", 0)
        deduction_total = p.get("deduction_total", 0)
        net_pay = p.get("net_pay", 0)

        # Build payslip view link
        payslip_url = f"{APP_BASE_URL}/release/detail?release_id={batch_id}&lang=en"

        content_html = f"""<div style="font-family: sans-serif; max-width: 600px;">
<h3 style="color: #1a56db;">{payroll_month} Payslip Notification</h3>
<p>Your payslip for {payroll_month} is ready. Summary:</p>
<table style="width:100%; border-collapse: collapse; margin: 12px 0; border: 1px solid #e5e7eb; border-radius: 8px;">
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Payroll Month</td><td style="padding: 8px 12px;">{payroll_month}</td></tr>
<tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Entity</td><td style="padding: 8px 12px;">{entity_name}</td></tr>
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Employee</td><td style="padding: 8px 12px;">{employee_name} ({eid})</td></tr>
<tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Gross Pay</td><td style="padding: 8px 12px; font-weight: 700;">{currency} {gross_pay:,.2f}</td></tr>
<tr style="background: #f9fafb;"><td style="padding: 8px 12px; font-weight: 600; color: #6b7280;">Deductions</td><td style="padding: 8px 12px;">{currency} {deduction_total:,.2f}</td></tr>
<tr><td style="padding: 8px 12px; font-weight: 600; color: #6b7280; font-size: 1.1em;">Net Pay</td><td style="padding: 8px 12px; font-weight: 700; font-size: 1.1em; color: #059669;">{currency} {net_pay:,.2f}</td></tr>
</table>
<p style="color: #6b7280; font-size: 0.9em;">This message was automatically sent by TACAI Payroll System. Contact HR for questions.</p>
</div>"""

        messages_payload.append({
            "recipient_user_id": user_info["user_id"],
            "msg_type": "salary_notification",
            "title": f"{payroll_month} Payslip - {entity_name}",
            "content": content_html,
            "priority": "normal",
            "biz_type": "salary_payslip",
            "biz_id": batch_id,
            "action_buttons": [{"label": "View Payslip", "url": payslip_url}],
            "template_variables": {
                "payroll_month": payroll_month,
                "entity_name": entity_name,
                "employee_id": eid,
                "employee_name": employee_name,
                "gross_pay": str(gross_pay),
                "net_pay": str(net_pay),
                "currency": currency,
            },
        })

    if not messages_payload:
        return {
            "sent_count": 0, "failed_count": 0,
            "skipped_no_account": len(skipped_eids),
            "total": len(payslips),
            "results": [],
            "message": "No employees with user accounts found",
            "skipped_employee_ids": skipped_eids,
        }

    # Call tacaimsg internal API
    result = _tacaimsg_call("/api/internal/messages/send-batch", {
        "messages": messages_payload,
        "sender_user_id": "SYSTEM",
        "sender_name": "TACAI Payroll SG",
    })

    if result.get("code") != 200:
        return {
            "sent_count": 0, "failed_count": len(messages_payload),
            "skipped_no_account": len(skipped_eids),
            "total": len(payslips),
            "results": [],
            "message": f"Message Center API error: {result.get('error', 'unknown')}",
            "skipped_employee_ids": skipped_eids,
        }

    data = result.get("data", {})
    data["skipped_employee_ids"] = skipped_eids
    return data


def send_payslip_emails(batch_id: str) -> tuple[int, int]:
    payslips = [p for p in load_json(PAYSLIPS_PATH, []) if p.get("batch_id") == batch_id]
    deliveries = load_json(EMAIL_DELIVERIES_PATH, [])
    sent = 0
    failed = 0
    for payslip in payslips:
        email = clean(payslip.get("employee_email"))
        delivery = {
            "delivery_id": f"DEL-{len(deliveries) + 1:06d}",
            "payslip_id": payslip.get("payslip_id"),
            "batch_id": batch_id,
            "recipient": email,
            "status": "queued",
            "message": "",
            "created_at": now_iso(),
            "sent_at": "",
        }
        if not EMAIL_PATTERN.match(email):
            delivery["status"] = "failed"
            delivery["message"] = "Invalid or missing employee email."
            failed += 1
            deliveries.append(delivery)
            continue
        pdf_path = ROOT_DIR / clean(payslip.get("file_path"))
        if not pdf_path.exists() or PAYSLIP_DIR not in pdf_path.resolve().parents:
            delivery["status"] = "failed"
            delivery["message"] = "Payslip PDF not found or invalid path."
            failed += 1
            deliveries.append(delivery)
            continue
        if not SMTP_HOST:
            delivery["status"] = "queued"
            delivery["message"] = "SMTP not configured; kept in queue."
            deliveries.append(delivery)
            continue
        try:
            msg = EmailMessage()
            msg["From"] = formataddr((PAYSLIP_SENDER_NAME, PAYSLIP_SENDER))
            msg["To"] = email
            msg["Subject"] = "TACAI Pay SG Payslip"
            msg.set_content("Dear employee,\n\nPlease find your Singapore payslip attached.\n\nRegards,\nTAC Payroll SG")
            msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)
            if SMTP_USE_TLS:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                    server.starttls(context=ssl.create_default_context())
                    if SMTP_USERNAME:
                        server.login(SMTP_USERNAME, SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as server:
                    if SMTP_USERNAME:
                        server.login(SMTP_USERNAME, SMTP_PASSWORD)
                    server.send_message(msg)
            delivery["status"] = "sent"
            delivery["sent_at"] = now_iso()
            sent += 1
        except Exception as exc:  # SMTP errors vary by backend.
            delivery["status"] = "failed"
            delivery["message"] = str(exc)
            failed += 1
        deliveries.append(delivery)
    save_json(EMAIL_DELIVERIES_PATH, deliveries)
    # Push to Message Center in parallel
    msg_result = publish_payslip_notifications_to_msg_center(batch_id, payslips)
    transition_batch(batch_id, "sent_to_employees", "send_payslip_emails")
    return sent, failed


def close_employee_confirmation(batch_id: str) -> dict[str, int]:
    records = load_records()
    before = [dict(r) for r in records if r.get("batch_id") == batch_id]
    confirmed = 0
    auto_confirmed = 0
    change_requested = 0
    for record in records:
        if record.get("batch_id") != batch_id:
            continue
        status = clean(record.get("employee_confirmation_status") or "pending")
        if status == "change_requested":
            change_requested += 1
        elif status == "confirmed":
            confirmed += 1
        else:
            record["employee_confirmation_status"] = "no_response_auto_confirmed"
            record["updated_at"] = now_iso()
            auto_confirmed += 1
    save_records(records)
    result = {"confirmed": confirmed, "auto_confirmed": auto_confirmed, "change_requested": change_requested}
    transition_batch(batch_id, "employee_confirmed", "close_employee_confirmation")
    append_audit("tacaipaysg.record", batch_id, "close_employee_confirmation", before, result)
    return result



# ── Salary Actuarial (工资精算) Data Functions ──────────────────

def load_actuarial_sheets() -> list[dict[str, Any]]:
    return load_json(ACTUARIAL_SHEETS_PATH, [])

def save_actuarial_sheets(rows: list[dict[str, Any]]) -> None:
    save_json(ACTUARIAL_SHEETS_PATH, rows)

def load_actuarial_records() -> list[dict[str, Any]]:
    return load_json(ACTUARIAL_RECORDS_PATH, [])

def save_actuarial_records(rows: list[dict[str, Any]]) -> None:
    save_json(ACTUARIAL_RECORDS_PATH, rows)

def find_actuarial_sheet(sheet_id: str) -> dict[str, Any] | None:
    return next((s for s in load_actuarial_sheets() if s.get("sheet_id") == sheet_id), None)

def actuarial_records_for_sheet(sheet_id: str) -> list[dict[str, Any]]:
    return [r for r in load_actuarial_records() if r.get("sheet_id") == sheet_id]

def next_actuarial_sheet_id(month: str, entity_id: str) -> str:
    return f"ACT-{month.replace('-', '')}-{slug(entity_id)}"

def create_actuarial_record(sheet_id: str, employee: dict[str, Any], month: str) -> dict[str, Any]:
    _, days = monthrange(int(month[:4]), int(month[5:7]))
    work_days = min(employee.get("standard_work_days") or 22, days)
    return {
        "record_id": f"{sheet_id}-{slug(employee['employee_id'])}",
        "sheet_id": sheet_id,
        "payroll_month": month,
        "country_code": "SG",
        "entity_id": employee.get("entity_id", ""),
        "employee_id": employee["employee_id"],
        "employee_number": employee.get("employee_number", ""),
        "employee_name": employee.get("employee_name", ""),
        "salary_type": employee.get("salary_type", "monthly"),
        "basic_salary": employee.get("basic_salary", 0),
        "hourly_rate": employee.get("hourly_rate", 0),
        "daily_rate": employee.get("daily_rate", 0),
        "standard_work_days": employee.get("standard_work_days", 22),
        "standard_work_hours": employee.get("standard_work_hours", 176),
        "work_days": work_days,
        "work_hours": employee.get("standard_work_hours", 176),
        "fixed_allowance": employee.get("fixed_allowance", 0),
        "performance_bonus": employee.get("performance_bonus", 0),
        "bonus": 0,
        "other_payment": 0,
        "recurring_deductions": employee.get("recurring_deductions", 0),
        "other_deduction": 0,
        "income_tax": 0,
        "cpf_applicable": employee.get("cpf_applicable", False),
        "cpf_input_mode": employee.get("cpf_input_mode", "manual"),
        "cpf_employee": employee.get("cpf_employee_manual", 0),
        "cpf_employer": employee.get("cpf_employer_manual", 0),
        "skill_development_levy": employee.get("skill_development_levy", 0),
        "foreign_worker_levy": employee.get("foreign_worker_levy", 0),
        "payroll_currency": employee.get("payroll_currency", "SGD"),
        "gross_pay": 0,
        "deduction_total": 0,
        "net_pay": 0,
        "employer_cost_total": 0,
        "status": "draft",
        "calculation_messages": [],
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

def calculate_actuarial_record(record: dict[str, Any]) -> dict[str, Any]:
    """Simple calculation for actuarial records - same logic as payroll calculation."""
    messages: list[str] = []
    salary_type = clean(record.get("salary_type") or "monthly")
    actual_hours = money(record.get("work_hours"))
    actual_days = money(record.get("work_days"))
    base = 0.0

    if salary_type == "hourly":
        std_mh = money(record.get("standard_monthly_hours")) or 160
        ot_rate = money(record.get("overtime_hourly_rate")) or 0
        hr = money(record.get("hourly_rate"))
        reg = min(actual_hours, std_mh)
        ot = max(0.0, actual_hours - std_mh)
        base = round(hr * reg, 2)
        if ot > 0 and ot_rate > 0:
            base = round(base + ot_rate * ot, 2)

    elif salary_type == "monthly_hour":
        std_mh = money(record.get("standard_monthly_hours")) or 160
        ot_rate = money(record.get("overtime_hourly_rate")) or 0
        mr = money(record.get("basic_salary"))
        hr = money(record.get("hourly_rate"))
        ratio = min(actual_hours / max(std_mh, 1), 1.0)
        monthly_part = round(mr * ratio, 2)
        hourly_part = round(hr * actual_hours, 2)
        ot = max(0.0, actual_hours - std_mh)
        ot_pay = round(ot_rate * ot, 2) if ot > 0 and ot_rate > 0 else 0
        base = round(monthly_part + hourly_part + ot_pay, 2)

    elif salary_type == "daily":
        base = money(record.get("daily_rate")) * actual_days

    else:  # monthly
        std_days = money(record.get("standard_work_days")) or 22
        base = money(record.get("basic_salary")) * min(actual_days / max(std_days, 1), 1) if std_days > 0 else money(record.get("basic_salary"))

    gross = round(base + money(record.get("fixed_allowance")) + money(record.get("performance_bonus")) + money(record.get("bonus")) + money(record.get("other_payment")), 2)
    deduction_total = round(money(record.get("cpf_employee")) + money(record.get("recurring_deductions")) + money(record.get("other_deduction")) + money(record.get("income_tax")), 2)
    employer_cost = round(gross + money(record.get("cpf_employer")) + money(record.get("skill_development_levy")) + money(record.get("foreign_worker_levy")), 2)
    record.update({
        "base_pay_calculated": round(base, 2),
        "gross_pay": gross,
        "deduction_total": deduction_total,
        "net_pay": round(gross - deduction_total, 2),
        "employer_cost_total": employer_cost,
        "calculation_messages": messages,
        "updated_at": now_iso(),
    })
    return record

def update_actuarial_record_from_form(record_id: str, form: dict[str, list[str]]) -> None:
    records = load_actuarial_records()
    money_fields = ["work_days", "work_hours", "fixed_allowance", "performance_bonus", "bonus", "other_payment", "recurring_deductions", "other_deduction", "income_tax", "cpf_employee", "cpf_employer", "skill_development_levy", "foreign_worker_levy"]
    for record in records:
        if record.get("record_id") == record_id:
            for field in money_fields:
                if field in form:
                    record[field] = money(form[field][0])
            if "payroll_currency" in form:
                record["payroll_currency"] = clean(form["payroll_currency"][0])
            record["updated_at"] = now_iso()
    save_actuarial_records(records)


# ── Monthly Salary Sheet (月度薪资核算) ──────────────────────────


def load_sheets() -> list[dict[str, Any]]:
    return load_json(MONTHLY_SHEETS_PATH, [])

def save_sheets(rows: list[dict[str, Any]]) -> None:
    save_json(MONTHLY_SHEETS_PATH, rows)

def load_monthly_records() -> list[dict[str, Any]]:
    return load_json(MONTHLY_RECORDS_PATH, [])

def save_monthly_records(rows: list[dict[str, Any]]) -> None:
    save_json(MONTHLY_RECORDS_PATH, rows)

def load_calendars() -> list[dict[str, Any]]:
    return load_json(PAYROLL_CALENDAR_PATH, [])

def save_calendars(rows: list[dict[str, Any]]) -> None:
    save_json(PAYROLL_CALENDAR_PATH, rows)

def load_release_batches() -> list[dict[str, Any]]:
    return load_json(PAYROLL_RELEASE_BATCHES_PATH, [])

def save_release_batches(rows: list[dict[str, Any]]) -> None:
    save_json(PAYROLL_RELEASE_BATCHES_PATH, rows)

def next_release_id(month: str, entity_id: str, country_code: str = "SG") -> str:
    return f"REL-{country_code}-{month.replace('-', '')}-{slug(entity_id)}"

def load_ledger() -> list[dict[str, Any]]:
    return load_json(PAYROLL_LEDGER_PATH, [])

def save_ledger(rows: list[dict[str, Any]]) -> None:
    save_json(PAYROLL_LEDGER_PATH, rows)

def generate_ledger_entry(release_id: str) -> str | None:
    """Auto-generate a payroll ledger entry when a release batch is marked as paid."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release or release.get("status") != "paid":
        return None

    ledger = load_ledger()
    # Check if already exists
    existing = next((le for le in ledger if le.get("release_id") == release_id), None)
    if existing:
        return existing.get("ledger_id")

    ledger_id = f"LED-{release.get('country_code', 'SG')}-{release['payroll_month'].replace('-', '')}-{slug(release['entity_id'])}"
    entry = {
        "ledger_id": ledger_id,
        "release_id": release_id,
        "source_sheet_id": release.get("source_sheet_id", ""),
        "payroll_month": release["payroll_month"],
        "entity_id": release["entity_id"],
        "country_code": release.get("country_code", "SG"),
        "employee_count": release.get("employee_count", 0),
        "gross_total": release.get("gross_total", 0),
        "deduction_total": release.get("deduction_total", 0),
        "net_total": release.get("net_total", 0),
        "employer_cost_total": release.get("employer_cost_total", 0),
        "currency_totals": release.get("currency_totals", {}),
        "email_sent_count": release.get("email_sent_count", 0),
        "email_failed_count": release.get("email_failed_count", 0),
        "paid_at": now_iso(),
        "created_at": now_iso(),
    }
    ledger.append(entry)
    save_ledger(ledger)
    append_audit("tacaipaysg.ledger", ledger_id, "ledger_entry_created", None, entry)
    return ledger_id

def release_detail_html(lang: str, release_id: str) -> str:
    """Detail view of a payroll release batch with payslip/email actions."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release:
        return "<div class='card'>Release batch not found.</div>"

    # Load payslips for this release
    all_payslips = load_json(PAYSLIPS_PATH, [])
    payslips = [p for p in all_payslips if p.get("release_id") == release_id]
    status = release.get("status", "pending_release")

    # Build action buttons based on status
    actions = []
    gen_form = ""  # PDF generation form with employee selection
    if status == "pending_release":
        pass  # No void action in release — batches should progress forward, not be voided
    elif status == "payslips_generated":
        actions.append(f"<form method='post' action='{with_lang('/release/hr-confirm', lang, release_id=release_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.release_hr_confirm_confirm'))})\"><button style='font-size:16px;min-width:200px'>{t(lang, 'action.release_hr_confirm')}</button></form>")
        actions.append(f"<button class='secondary' onclick=\"document.getElementById('release-regenerate-modal-count').textContent='{len(payslips)}';showConfirmModal('release-regenerate-modal')\">{t(lang, 'action.release_payslips')} (regenerate)</button>")
        actions.append(f"<form method='post' action='{with_lang('/release/return-to-pending', lang, release_id=release_id)}' style='display:inline' onsubmit=\"return confirm('确定要退回待发放状态吗？已生成的PDF将被清除。 / Return to pending? Generated PDFs will be cleared.')\"><button class='secondary' style='font-size:12px'>← {t(lang,'action.return_to_prev')}</button></form>")
    elif status == "hr_confirmed":
        actions.append(f"<a class='button' href='{with_lang('/release/email-draft', lang, release_id=release_id)}' style='font-size:16px;min-width:200px'>{t(lang, 'action.release_email_draft')}</a>")
        actions.append(f"<form method='post' action='{with_lang('/release/return-to-pending', lang, release_id=release_id)}' style='display:inline' onsubmit=\"return confirm('确定要退回待发放状态吗？HR确认将被清除。 / Return to pending? HR confirmation will be cleared.')\"><button class='secondary' style='font-size:12px'>← {t(lang,'action.return_to_prev')}</button></form>")
    elif status in ("email_draft_prepared", "sending", "partially_sent"):
        actions.append(f"<a class='button' href='{with_lang('/release/email-send', lang, release_id=release_id)}' style='font-size:16px;min-width:200px'>{t(lang, 'action.release_email_send')}</a>")
        if status == "partially_sent":
            actions.append(f"<form method='post' action='{with_lang('/release/email-resend-all', lang, release_id=release_id)}' style='display:inline' onsubmit=\"return confirm('确定要重发所有失败的邮件吗？ / Resend all failed emails?')\"><button class='secondary' style='font-size:16px;min-width:200px'>🔄 Resend All Failed</button></form>")
        actions.append(f"<form method='post' action='{with_lang('/release/return-to-pending', lang, release_id=release_id)}' style='display:inline' onsubmit=\"return confirm('确定要退回待发放状态吗？ / Return to pending?')\"><button class='secondary' style='font-size:12px'>← {t(lang,'action.return_to_prev')}</button></form>")
    elif status == "sent":
        actions.append(f"<form method='post' action='{with_lang('/release/paid', lang, release_id=release_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.release_paid_confirm'))})\"><button class='danger' style='font-size:16px;min-width:200px'>{t(lang, 'action.release_paid')}</button></form>")

    # ── Employee filter + selection + PDF generation card (for pending_release status) ──
    if status == "pending_release":
        # Gather distinct departments and teams from payslips
        dept_set: dict[str, str] = {}
        team_set: dict[str, str] = {}
        for ps_item in payslips:
            d = clean(ps_item.get('department_label', ''))
            tm = clean(ps_item.get('team_label', ''))
            if d and d not in dept_set: dept_set[d] = slug(d)
            if tm and tm not in team_set: team_set[tm] = slug(tm)
        dept_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(dept_set.items()))
        team_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(team_set.items()))

        # Build gen rows separately to avoid nested f-string issues
        gen_rows_parts = []
        for ps_item in payslips:
            gen_rows_parts.append(
                '<tr class="gen-row" data-dept="' + escape(slug(ps_item.get('department_label',''))) + '" data-team="' + escape(slug(ps_item.get('team_label',''))) + '" data-name="' + escape(ps_item.get('employee_name','').lower()) + '" data-number="' + escape(ps_item.get('employee_number','').lower()) + '">'
                '<td><input type="checkbox" class="gen-select" name="payslip_ids" value="' + escape(ps_item['payslip_id']) + '" checked style="width:auto;min-width:auto"></td>'
                '<td>' + escape(ps_item.get('employee_number','')) + '</td>'
                '<td>' + escape(ps_item.get('employee_name','')) + '</td>'
                '<td>' + escape(ps_item.get('department_label','')) + '</td>'
                '<td>' + escape(ps_item.get('salary_type','monthly')) + '</td>'
                '<td class="right">' + money_fmt(ps_item.get('gross_pay')) + '</td>'
                '<td class="right"><strong>' + money_fmt(ps_item.get('net_pay')) + '</strong></td>'
                '<td>' + ('OK' if ps_item.get('file_name') else '-') + '</td>'
                '</tr>'
            )
        gen_rows_html = ''.join(gen_rows_parts)
        gen_form = f"""
<div class="card" style="border-left:4px solid var(--sap-accent)">
<div class="section-header"><h3>📄 {t(lang, 'action.release_payslips')} — Select employees / 选择员工生成工资单</h3></div>
<div class="sap-toolbar" style="margin-bottom:8px;flex-wrap:wrap;gap:8px">
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('.gen-select').forEach(c=>{{c.checked=true}});updateGenCount()">Select All</button>
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('.gen-select').forEach(c=>{{c.checked=false}});updateGenCount()">Deselect All</button>
  <span style="font-weight:800;color:var(--blue);margin-left:8px" id="gen-count">{len(payslips)} selected</span>
</div>
<div class="search-bar" style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap">
  <input id="gen-name-search" type="text" placeholder="Search name or number..." oninput="applyGenFilters()" style="min-width:140px;flex:1">
  <select id="gen-dept-filter" onchange="applyGenFilters()" style="min-width:120px"><option value="">All Depts</option>{dept_opts}</select>
  <select id="gen-team-filter" onchange="applyGenFilters()" style="min-width:120px"><option value="">All Teams</option>{team_opts}</select>
  <button type="button" class="secondary" style="font-size:11px" onclick="clearGenFilters()">Clear</button>
</div>
<form id="release-gen-form" method="post" action="{with_lang('/release/payslips', lang, release_id=release_id)}">
<div class="table-scroll" style="max-height:400px"><table><thead><tr>
<th style="width:30px"><input type="checkbox" id="gen-select-all" checked style="width:auto;min-width:auto" onclick="var c=this.checked;document.querySelectorAll('.gen-select').forEach(x=>{{if(x.closest('.gen-row').style.display!=='none')x.checked=c}});updateGenCount()"></th>
<th>No.</th><th>Name</th><th>Dept</th><th>Type</th><th>Gross</th><th>Net</th><th>PDF</th>
</tr></thead><tbody>{gen_rows_html}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(payslips)} employee(s). Existing PDFs will be overwritten.</div>
<div class="sap-toolbar end" style="margin-top:12px"><button type="button" style="font-size:16px;min-width:200px" onclick="handleReleaseGenSubmit()">📄 {t(lang, 'action.release_payslips')} (Selected)</button></div>
</form>
<script>
function handleReleaseGenSubmit(){{var sel=document.querySelectorAll('.gen-select:checked').length;if(sel===0){{alert({json.dumps(t(lang, 'msg.payslip_gen_select_prompt'))});return}}document.getElementById('release-gen-modal-count').textContent=sel;showConfirmModal('release-gen-modal')}}
function applyGenFilters(){{var nvEl=document.getElementById('gen-name-search');var nv=nvEl?nvEl.value.toLowerCase().trim():'';var dvEl=document.getElementById('gen-dept-filter');var dv=dvEl?dvEl.value:'';var tvEl=document.getElementById('gen-team-filter');var tv=tvEl?tvEl.value:'';document.querySelectorAll('.gen-row').forEach(function(r){{var m=(!nv||r.getAttribute('data-name').indexOf(nv)>=0||r.getAttribute('data-number').indexOf(nv)>=0)&&(!dv||r.getAttribute('data-dept')===dv)&&(!tv||r.getAttribute('data-team')===tv);r.style.display=m?'':'none';if(!m){{var cb=r.querySelector('.gen-select');if(cb)cb.checked=false}}}});updateGenCount()}}
function clearGenFilters(){{var el=document.getElementById('gen-name-search');if(el)el.value='';el=document.getElementById('gen-dept-filter');if(el)el.value='';el=document.getElementById('gen-team-filter');if(el)el.value='';applyGenFilters()}}
function updateGenCount(){{var sel=document.querySelectorAll('.gen-select:checked').length;var el=document.getElementById('gen-count');if(el)el.textContent=sel+' selected'}}
document.querySelectorAll('.gen-select').forEach(function(cb){{cb.addEventListener('change',updateGenCount)}});
</script>
<!-- Confirm Modal -->
<div class="modal-overlay" id="release-gen-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">⚠️</div>
<p><strong>{t(lang, 'msg.payslip_gen_modal_title')}</strong></p>
<p>{t(lang, 'msg.payslip_gen_modal_body').replace('{count}', '<span class="modal-count" id="release-gen-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no default-no" onclick="hideModal('release-gen-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes" onclick="submitGenForm('release-gen-form','release-gen-modal')">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
</div>"""

    # Build payslip table
    deliveries = load_json(EMAIL_DELIVERIES_PATH, [])
    delivery_by_ps = {}
    for d in deliveries:
        pid = d.get("payslip_id", "")
        if pid not in delivery_by_ps or d.get("sent_at", "") > delivery_by_ps[pid].get("sent_at", ""):
            delivery_by_ps[pid] = d
    trs = []
    for ps in payslips:
        ps_status = ps.get("status", "pending")
        hr_confirmed = "✅" if ps.get("hr_confirmed") else "⏳"
        email_status = ps.get("email_draft_status", "not_prepared")
        email_badge_map = {"not_prepared": "—", "draft_prepared": "📝", "sent": "📤", "send_failed": "❌"}
        email_badge = email_badge_map.get(email_status, email_status)
        # HTML view + PDF download links
        view_link = f" <a href='{with_lang('/payslip/view', lang, payslip_id=ps['payslip_id'])}' target='_blank' class='button secondary' style='font-size:11px;padding:2px 6px;min-height:auto'>📋</a>"
        pdf_link = ""
        if ps.get("file_name"):
            pdf_link = f" <a href='{with_lang('/payslip/download', lang, payslip_id=ps['payslip_id'])}' target='_blank' class='button secondary' style='font-size:11px;padding:2px 6px;min-height:auto'>📄</a>"
        # Email log detail
        delivery = delivery_by_ps.get(ps["payslip_id"], {})
        email_detail = ""
        if delivery.get("sent_at"):
            email_detail = f"<br><span style='font-size:10px;color:var(--muted)'>{delivery['sent_at'][:19].replace('T',' ')}</span>"
        if email_status == "send_failed" and delivery.get("message"):
            email_detail += f"<br><span style='font-size:10px;color:var(--red)'>{escape(delivery['message'][:60])}</span>"
        # Resend button for failed emails
        resend_action = ""
        if email_status == "send_failed":
            resend_action = f" <form method='post' action='{with_lang('/release/email-resend', lang, release_id=release_id, payslip_id=ps['payslip_id'])}' style='display:inline' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.release_resend_confirm'))})\"><button class='secondary' style='font-size:11px;padding:2px 6px;min-height:auto'>🔄</button></form>"
        trs.append(f"<tr><td>{escape(ps.get('employee_number',''))}</td><td>{escape(ps.get('employee_name',''))}{view_link}{pdf_link}</td><td>{escape(ps.get('department_label',''))}</td><td>{escape(ps.get('employee_email',''))}</td><td class='right'>{money_fmt(ps.get('gross_pay'))}</td><td class='right'><strong>{money_fmt(ps.get('net_pay'))}</strong></td><td>{status_badge(ps_status)}</td><td>{hr_confirmed}</td><td>{email_badge}{resend_action}{email_detail}</td></tr>")

    # Batch resend button for partially_sent
    batch_resend_action = ""
    if status in ("partially_sent", "sending"):
        batch_resend_action = f"<form method='post' action='{with_lang('/release/email-resend-all', lang, release_id=release_id)}' style='display:inline' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.release_resend_confirm'))})\"><button class='secondary' style='font-size:12px'>🔄 {t(lang, 'action.release_resend')} All Failed</button></form>"

    table = f"<p class='muted'>{t(lang,'msg.no_records')}</p>" if not trs else f"<div class='table-scroll'><table><thead><tr><th>No.</th><th>Name</th><th>Dept</th><th>Email</th><th>Gross</th><th>Net</th><th>Payslip</th><th>HR OK</th><th>Email Status</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"

    # Summary metrics
    sent_count = release.get("email_sent_count", 0)
    failed_count = release.get("email_failed_count", 0)
    msg_sent = release.get("msg_center_sent_count", 0)
    msg_failed = release.get("msg_center_failed_count", 0)
    msg_skipped = release.get("msg_center_skipped_no_account", 0)
    entity_display = entity_label(release.get("entity_id", ""), lang)

    # Get source sheet for back-link
    source_sheet_id = release.get("source_sheet_id", "")

    currency_totals = release.get("currency_totals") or {}
    currency_summary = ""
    if len(currency_totals) > 1:
        cur_parts = []
        for cur in sorted(currency_totals.keys()):
            ct = currency_totals[cur]
            cur_parts.append(f'<div class="metric-card" style="flex:1;min-width:120px"><div>{escape(cur)}</div><div class="value" style="font-size:20px">Net {money_fmt(ct.get("net"))}</div><div class="muted">Gross {money_fmt(ct.get("gross"))} · {ct.get("count",0)} emp</div></div>')
        currency_summary = f'<div class="card" style="padding:12px"><div style="display:flex;gap:12px;flex-wrap:wrap">{"".join(cur_parts)}</div></div>'

    return f"""
<div class="sap-page-header"><h1>{escape(release_id)}</h1><div class="sap-info-strip"><span>📅 {escape(release.get('payroll_month',''))}</span><span>🏢 {escape(entity_display)}</span><span>{status_badge(status)}</span><span>👥 {release.get('employee_count',0)} employees</span><span>🔗 <a href='{with_lang('/monthly-sheets/detail', lang, sheet_id=source_sheet_id)}'>Source Sheet</a></span><span>📤 Email {sent_count} sent</span><span>📬 Msg Center {msg_sent} sent</span></div></div>
<div class="card">{release_progress_bar(lang, status)}</div>
<div class="grid">
  <div class="metric-card"><div>💰 {t(lang,'label.gross')}</div><div class="value">{money_fmt(release.get('gross_total'))}</div></div>
  <div class="metric-card"><div>💵 {t(lang,'label.net')}</div><div class="value">{money_fmt(release.get('net_total'))}</div></div>
  <div class="metric-card"><div>🏢 {t(lang,'label.employer_cost')}</div><div class="value">{money_fmt(release.get('employer_cost_total'))}</div></div>
  <div class="metric-card"><div>📤 Email Sent</div><div class="value">{sent_count}</div><div class="muted">{failed_count} failed</div></div>
  <div class="metric-card"><div>📬 Msg Center</div><div class="value">{msg_sent}</div><div class="muted">{msg_skipped} no account, {msg_failed} failed</div></div>
</div>
{currency_summary}
<div class="card"><div class="sap-toolbar" style="justify-content:space-between"><div style="display:flex;gap:8px;flex-wrap:wrap">{''.join(actions)}</div><div style="display:flex;gap:8px;flex-wrap:wrap"><a class="button secondary" href="{with_lang('/reports/payroll.csv', lang, batch_id=source_sheet_id)}">📥 Payroll</a><a class="button secondary" href="{with_lang('/reports/bank.csv', lang, release_id=release_id)}">🏦 Bank</a><a class="button secondary" href="{with_lang('/reports/cost.csv', lang, release_id=release_id)}">📊 Cost</a></div></div></div>
{gen_form}
<!-- Hidden form + modal for quick regenerate all -->
<form id="release-regenerate-form" method="post" action="{with_lang('/release/payslips', lang, release_id=release_id)}" style="display:none"></form>
<div class="modal-overlay" id="release-regenerate-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">⚠️</div>
<p><strong>{t(lang, 'msg.payslip_gen_modal_title')}</strong></p>
<p>{t(lang, 'msg.payslip_gen_modal_body').replace('{count}', '<span class="modal-count" id="release-regenerate-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no default-no" onclick="hideModal('release-regenerate-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes" onclick="submitGenForm('release-regenerate-form','release-regenerate-modal')">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
<div class="card">{table}<div class="helper-text" style="margin-top:8px">{len(payslips)} record(s) total</div></div>"""


def ledger_list_html(lang: str) -> str:
    """Payroll ledger list page — historical record of all paid releases."""
    entries = load_ledger()
    entries.sort(key=lambda e: e.get("paid_at", ""), reverse=True)
    if not entries:
        return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.ledger')}</h1><div class="sap-info-strip"><span>📒 Historical records of completed payroll releases / 已完成工资发放的历史记录</span></div></div>
<div class="card"><p class="muted">{t(lang,'msg.no_records')}</p></div>"""

    trs = []
    for e in entries:
        entity_display = entity_label(e.get("entity_id", ""), lang)
        trs.append(f"""<tr>
<td><a href='{with_lang('/ledger/detail', lang, ledger_id=e['ledger_id'])}'>{escape(e['ledger_id'])}</a></td>
<td>{escape(e.get('payroll_month',''))}</td>
<td>{escape(entity_display)}</td>
<td class='right'>{e.get('employee_count',0)}</td>
<td class='right'>{money_fmt(e.get('gross_total'))}</td>
<td class='right'><strong>{money_fmt(e.get('net_total'))}</strong></td>
<td class='right'>{money_fmt(e.get('employer_cost_total'))}</td>
<td class='right'>{e.get('email_sent_count',0)}</td>
<td>{escape(e.get('paid_at','')[:10])}</td>
</tr>""")

    total_net = sum(e.get('net_total', 0) for e in entries)
    total_employer = sum(e.get('employer_cost_total', 0) for e in entries)
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.ledger')}</h1><div class="sap-info-strip"><span>📒 {len(entries)} completed releases</span><span>💰 Net {money_fmt(total_net)} paid</span><span>🏢 Cost {money_fmt(total_employer)}</span></div></div>
<div class="card"><div class='table-scroll'><table><thead><tr>
  <th>Ledger ID</th><th>Month</th><th>Entity</th><th>Emp</th><th>Gross</th><th>Net</th><th>Cost</th><th>Sent</th><th>Paid Date</th>
</tr></thead><tbody>{''.join(trs)}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(entries)} record(s) total</div></div>"""


def ledger_detail_html(lang: str, ledger_id: str) -> str:
    """Detail view of a single ledger entry."""
    entries = load_ledger()
    entry = next((e for e in entries if e.get("ledger_id") == ledger_id), None)
    if not entry:
        return "<div class='card'>Ledger entry not found.</div>"

    entity_display = entity_label(entry.get("entity_id", ""), lang)
    release_id = entry.get("release_id", "")
    currency_totals = entry.get("currency_totals") or {}
    currency_cards = ""
    if currency_totals:
        cards = []
        for cur in sorted(currency_totals.keys()):
            ct = currency_totals[cur]
            cards.append(f"<div class='metric-card'><div>{escape(cur)}</div><div class='value' style='font-size:16px'>Net {money_fmt(ct.get('net'))}</div><div class='muted'>Gross {money_fmt(ct.get('gross'))} · Cost {money_fmt(ct.get('employer_cost'))} · {ct.get('count',0)} emp</div></div>")
        currency_cards = f"<div class='grid'>{''.join(cards)}</div>"

    return f"""
<div class="sap-page-header"><h1>{escape(ledger_id)}</h1><div class="sap-info-strip"><span>📅 {escape(entry.get('payroll_month',''))}</span><span>🏢 {escape(entity_display)}</span><span>✅ Paid: {escape(entry.get('paid_at','')[:10])}</span><span>👥 {entry.get('employee_count',0)} employees</span></div></div>
<div class="grid">
  <div class="metric-card"><div>💰 {t(lang,'label.gross')}</div><div class="value">{money_fmt(entry.get('gross_total'))}</div></div>
  <div class="metric-card"><div>💵 {t(lang,'label.net')}</div><div class="value">{money_fmt(entry.get('net_total'))}</div></div>
  <div class="metric-card"><div>🏢 {t(lang,'label.employer_cost')}</div><div class="value">{money_fmt(entry.get('employer_cost_total'))}</div></div>
  <div class="metric-card"><div>📤 Emails Sent</div><div class="value">{entry.get('email_sent_count',0)}</div></div>
</div>
{currency_cards}
<div class="card">
  <div class="sap-toolbar">
    <a class='button secondary' href='{with_lang('/ledger', lang)}'>← {t(lang,'nav.ledger')}</a>
    <a class='button secondary' href='{with_lang('/release/detail', lang, release_id=release_id)}'>📋 View Release</a>
    <a class='button secondary' href='{with_lang('/reports/payroll.csv', lang, batch_id=release_id)}'>📥 Payroll CSV</a>
    <a class='button secondary' href='{with_lang('/reports/cost.csv', lang, batch_id=release_id)}'>📊 Cost CSV</a>
  </div>
</div>"""


def cost_report_html(lang: str) -> str:
    """Cost analysis report page — employer cost breakdown by month and entity."""
    ledger = load_ledger()
    release_batches = load_release_batches()

    # Combine paid release data for cost analysis
    paid_releases = [rb for rb in release_batches if rb.get("status") == "paid"]
    paid_releases.sort(key=lambda r: r.get("payroll_month", ""), reverse=True)

    if not paid_releases and not ledger:
        return f"""
<div class="sap-page-header"><h1>Cost Report / 成本报表</h1><div class="sap-info-strip"><span>📊 No paid releases yet — cost data will appear here after payroll is completed.</span></div></div>
<div class="card"><p class="muted">{t(lang, 'msg.no_records')}</p></div>"""

    # Monthly cost summary
    monthly: dict[str, dict[str, float]] = {}
    for rb in paid_releases:
        month = rb.get("payroll_month", "")
        if month not in monthly:
            monthly[month] = {"gross": 0, "employer_cost": 0, "count": 0}
        monthly[month]["gross"] += money(rb.get("gross_total"))
        monthly[month]["employer_cost"] += money(rb.get("employer_cost_total"))
        monthly[month]["count"] += rb.get("employee_count", 0)

    # Entity cost summary
    entity_cost: dict[str, dict[str, float]] = {}
    for rb in paid_releases:
        eid = rb.get("entity_id", "Unknown")
        if eid not in entity_cost:
            entity_cost[eid] = {"gross": 0, "employer_cost": 0, "count": 0}
        entity_cost[eid]["gross"] += money(rb.get("gross_total"))
        entity_cost[eid]["employer_cost"] += money(rb.get("employer_cost_total"))
        entity_cost[eid]["count"] += rb.get("employee_count", 0)

    # Monthly table
    month_trs = []
    for month in sorted(monthly.keys(), reverse=True)[:12]:
        m = monthly[month]
        cost_pct = f"{(m['employer_cost'] / m['gross'] * 100):.1f}%" if m['gross'] > 0 else "0%"
        month_trs.append(f"<tr><td>{escape(month)}</td><td class='right'>{int(m['count'])}</td><td class='right'>{money_fmt(m['gross'])}</td><td class='right'>{money_fmt(m['employer_cost'])}</td><td class='right'>{cost_pct}</td></tr>")

    # Entity table
    entity_trs = []
    for eid in sorted(entity_cost.keys()):
        ec = entity_cost[eid]
        ed = entity_label(eid, lang)
        cost_pct = f"{(ec['employer_cost'] / ec['gross'] * 100):.1f}%" if ec['gross'] > 0 else "0%"
        entity_trs.append(f"<tr><td>{escape(ed)}</td><td class='right'>{int(ec['count'])}</td><td class='right'>{money_fmt(ec['gross'])}</td><td class='right'>{money_fmt(ec['employer_cost'])}</td><td class='right'>{cost_pct}</td></tr>")

    total_gross = sum(m["gross"] for m in monthly.values())
    total_cost = sum(m["employer_cost"] for m in monthly.values())
    total_pct = f"{(total_cost / total_gross * 100):.1f}%" if total_gross > 0 else "0%"

    return f"""
<div class="sap-page-header"><h1>Cost Report / 成本报表</h1><div class="sap-info-strip"><span>💰 Gross {money_fmt(total_gross)}</span><span>🏢 Cost {money_fmt(total_cost)}</span><span>📊 {total_pct} ratio</span><span>🔄 {len(paid_releases)} cycles</span></div></div>
<div class="grid">
  <div class="metric-card"><div>Total Gross Pay</div><div class="value">{money_fmt(total_gross)}</div></div>
  <div class="metric-card"><div>Total Employer Cost</div><div class="value">{money_fmt(total_cost)}</div></div>
  <div class="metric-card"><div>Cost Ratio</div><div class="value">{total_pct}</div></div>
  <div class="metric-card"><div>Payroll Cycles</div><div class="value">{len(paid_releases)}</div></div>
</div>
<div class="card"><div class="section-header"><h3>By Month / 按月份</h3></div>
<div class='table-scroll'><table><thead><tr><th>Month</th><th>Employees</th><th>Gross Pay</th><th>Employer Cost</th><th>Cost %</th></tr></thead><tbody>{''.join(month_trs)}</tbody></table></div>
</div>
<div class="card"><div class="section-header"><h3>By Entity / 按法人</h3></div>
<div class='table-scroll'><table><thead><tr><th>Entity</th><th>Employees</th><th>Gross Pay</th><th>Employer Cost</th><th>Cost %</th></tr></thead><tbody>{''.join(entity_trs)}</tbody></table></div>
</div>"""


def payslip_pdf_bytes(ps_data: dict[str, Any], mr_data: dict[str, Any], entity_name: str = "Tech Alliance Consultancy Service Pte. Ltd") -> bytes:
    """Generate a company-branded payslip PDF using fpdf2 with CJK support.

    Layout adapts to salary_type:
      - monthly: Basic Salary + Allowances + Work Days
      - hourly: Hourly Rate × Actual Hours + Overtime (if ot_rate>0)
      - daily: Daily Rate × Actual Days
      - monthly_hour: Basic Salary + Hourly Rate × Standard Hours + Overtime
    """
    employee_name = str(ps_data.get('employee_name', ''))
    employee_number = str(ps_data.get('employee_number', ''))
    department = str(ps_data.get('department_label', ''))
    payroll_month = str(ps_data.get('payroll_month', ''))
    currency = str(ps_data.get('payroll_currency', 'SGD'))

    salary_type = str(mr_data.get('salary_type', 'monthly'))
    basic_salary = money(mr_data.get('basic_salary', 0))
    hourly_rate = money(mr_data.get('hourly_rate', 0))
    daily_rate = money(mr_data.get('daily_rate', 0))
    overtime_rate = money(mr_data.get('overtime_hourly_rate', 0))
    actual_hours = money(mr_data.get('actual_work_hours', 0))
    actual_days = money(mr_data.get('actual_work_days', 0))
    standard_hours = money(mr_data.get('standard_work_hours', 176))
    standard_days = money(mr_data.get('standard_work_days', 22))
    paid_leave = money(mr_data.get('paid_leave_days', 0))
    sick_leave = money(mr_data.get('sick_leave_days', 0))
    overtime_hours = money(mr_data.get('overtime_hours', 0))

    position_allowance = money(mr_data.get('position_allowance', 0))
    fixed_allowance = money(mr_data.get('fixed_allowance', 0))
    housing_allowance = money(mr_data.get('housing_allowance', 0))
    commute_allowance = money(mr_data.get('commute_allowance', 0))
    performance_bonus = money(mr_data.get('performance_bonus', 0))
    bonus = money(mr_data.get('bonus', 0))
    other_payment = money(mr_data.get('other_payment', 0))
    other_earnings = money(mr_data.get('other_earnings', 0))

    gross_pay = money(ps_data.get('gross_pay', 0))
    deduction_total = money(ps_data.get('deduction_total', 0))
    net_pay = money(ps_data.get('net_pay', 0))
    cpf_employee = money(mr_data.get('cpf_employee', 0))
    cpf_employer = money(mr_data.get('cpf_employer', 0))
    income_tax = money(mr_data.get('income_tax', 0))
    other_deduction = money(mr_data.get('other_deduction', 0))
    recurring_deductions = money(mr_data.get('recurring_deductions', 0))
    employer_cost_total = money(mr_data.get('employer_cost_total', 0))
    sdl = money(mr_data.get('skill_development_levy', 0))
    fwl = money(mr_data.get('foreign_worker_levy', 0))

    bank_name = str(clean(mr_data.get('bank_name', '')))
    bank_branch = str(clean(mr_data.get('bank_branch_name', '')))
    bank_account = str(clean(mr_data.get('bank_account_number', '')))
    bank_account_type = str(clean(mr_data.get('bank_account_type', '')))

    cpf_applicable = mr_data.get('cpf_applicable', False)

    def fmt_amt(amount: float) -> str:
        return f"{currency} {amount:,.2f}"

    pdf = FPDF()
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_page()

    # Register Unicode font (Arial Unicode supports CJK + Latin)
    font_path = UNICODE_FONT_PATH
    if not Path(font_path).exists():
        font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    if Path(font_path).exists():
        pdf.add_font("ArialUni", "", font_path, uni=True)
        pdf.add_font("ArialUni", "B", font_path, uni=True)
        font_name = "ArialUni"
    else:
        font_name = "Helvetica"

    col1 = 14
    col2 = 120

    def section_title(text: str) -> None:
        pdf.set_font(font_name, "B", 11)
        pdf.set_fill_color(230, 238, 250)
        pdf.cell(0, 8, f"  {text}", ln=True, fill=True)
        pdf.ln(2)

    def info_row(label: str, value: str) -> None:
        pdf.set_font(font_name, "B", 9)
        pdf.set_x(col1)
        pdf.cell(40, 5, label + ":")
        pdf.set_font(font_name, "", 9)
        pdf.cell(0, 5, value, ln=True)

    def item_row(label: str, amount: float, indent: bool = False) -> None:
        x0 = col1 + (10 if indent else 0)
        pdf.set_font(font_name, "", 9)
        pdf.set_x(x0)
        pdf.cell(90, 5, label)
        pdf.cell(30, 5, fmt_amt(amount), align="R", ln=True)

    def total_row(label: str, amount: float) -> None:
        pdf.set_font(font_name, "B", 10)
        pdf.set_x(col1)
        pdf.cell(90, 6, label)
        pdf.cell(30, 6, fmt_amt(amount), align="R", ln=True)
        pdf.ln(1)

    # ── Header ──
    pdf.set_font(font_name, "B", 16)
    pdf.cell(0, 9, "TAC Alliance", ln=True, align="C")
    pdf.set_font(font_name, "", 9)
    pdf.cell(0, 5, f"PAYSLIP / 工资单", ln=True, align="C")
    pdf.cell(0, 5, entity_name, ln=True, align="C")
    pdf.ln(4)
    pdf.set_draw_color(10, 110, 209)
    pdf.set_line_width(0.6)
    pdf.line(col1, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(4)
    info_row("Payroll Month", payroll_month)
    info_row("Employee", employee_name)
    info_row("Employee No", employee_number)
    info_row("Department", department)
    info_row("Salary Type", salary_type)
    pdf.ln(2)

    # ── EARNINGS ──
    section_title("EARNINGS / 应发")

    if salary_type == "monthly":
        item_row("Basic Salary", basic_salary)
        if position_allowance > 0:
            item_row("Position Allowance", position_allowance)
        if fixed_allowance > 0:
            item_row("Fixed Allowance", fixed_allowance)
        if commute_allowance > 0:
            item_row("Commute Allowance", commute_allowance)
        if housing_allowance > 0:
            item_row("Housing Allowance", housing_allowance)
    elif salary_type == "hourly":
        item_row(f"Base Hourly Pay ({hourly_rate:,.2f} x {actual_hours:.0f}h)", round(hourly_rate * actual_hours, 2))
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                item_row(f"Overtime Pay ({ot_hours:.0f}h x {overtime_rate:,.2f})", round(overtime_rate * ot_hours, 2))
    elif salary_type == "daily":
        item_row(f"Base Daily Pay ({daily_rate:,.2f} x {actual_days:.0f}d)", round(daily_rate * actual_days, 2))
    elif salary_type == "monthly_hour":
        ratio = min(actual_hours / max(standard_hours, 1), 1.0)
        monthly_part = round(basic_salary * ratio, 2)
        item_row("Basic Salary (monthly)", monthly_part)
        regular_hours = min(actual_hours, standard_hours)
        hourly_part = round(hourly_rate * regular_hours, 2)
        item_row(f"Hourly Pay ({regular_hours:.0f}h x {hourly_rate:,.2f})", hourly_part)
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                item_row(f"Overtime Pay ({ot_hours:.0f}h x {overtime_rate:,.2f})", round(overtime_rate * ot_hours, 2))

    if paid_leave > 0:
        item_row(f"Paid Leave ({paid_leave:.0f} days)", 0)
    if sick_leave > 0:
        item_row(f"Sick Leave ({sick_leave:.0f} days)", 0)
    if overtime_hours > 0 and salary_type == "monthly":
        item_row(f"Overtime ({overtime_hours:.0f}h)", 0)

    # Common allowances and extras (always show for review completeness)
    if fixed_allowance > 0 and salary_type != "monthly":
        item_row("Fixed Allowance", fixed_allowance)
    if position_allowance > 0 and salary_type != "monthly":
        item_row("Position Allowance", position_allowance)
    if housing_allowance > 0 and salary_type != "monthly":
        item_row("Housing Allowance", housing_allowance)
    if commute_allowance > 0 and salary_type != "monthly":
        item_row("Commute Allowance", commute_allowance)
    # Always show these for review visibility
    item_row("Performance Bonus", performance_bonus)
    if bonus > 0:
        item_row("Bonus", bonus)
    item_row("Other Payment", other_payment)
    if other_earnings > 0:
        item_row("Other Earnings", other_earnings)

    pdf.ln(1)
    total_row("GROSS PAY", gross_pay)
    pdf.line(col1, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(3)

    # ── DEDUCTIONS (always show for review completeness) ──
    section_title("DEDUCTIONS / 扣除")
    if cpf_applicable and cpf_employee > 0:
        item_row("CPF Employee", cpf_employee)
    if income_tax > 0:
        item_row("Income Tax", income_tax)
    if recurring_deductions > 0:
        item_row("Recurring Deductions", recurring_deductions)
    # Always show Other Deduction
    item_row("Other Deduction", other_deduction)
    pdf.ln(1)
    total_row("TOTAL DEDUCTION", deduction_total)
    pdf.line(col1, pdf.get_y(), 196, pdf.get_y())
    pdf.ln(3)

    # ── NET PAY ──
    section_title("NET PAY / 实发")
    pdf.set_font(font_name, "B", 14)
    pdf.set_x(col1)
    pdf.cell(90, 8, "NET PAY / 实发")
    pdf.cell(30, 8, fmt_amt(net_pay), align="R", ln=True)
    pdf.set_font(font_name, "", 9)
    pdf.ln(3)

    # ── EMPLOYER COSTS ──
    has_employer = (cpf_employer > 0 or sdl > 0 or fwl > 0)
    if has_employer:
        section_title("EMPLOYER COSTS / 雇主成本")
        if cpf_applicable and cpf_employer > 0:
            item_row("CPF Employer", cpf_employer)
        if sdl > 0:
            item_row("SDL (Skill Development Levy)", sdl)
        if fwl > 0:
            item_row("FWL (Foreign Worker Levy)", fwl)
        pdf.ln(1)
        total_row("TOTAL EMPLOYER COST", employer_cost_total)
        pdf.line(col1, pdf.get_y(), 196, pdf.get_y())
        pdf.ln(3)

    # ── BANK INFO ──
    if bank_name or bank_account:
        section_title("BANK / 银行信息")
        if bank_name:
            bank_line = f"Bank: {bank_name}"
            if bank_branch:
                bank_line += f" / {bank_branch}"
            info_row("Bank", bank_line.replace("Bank: ", ""))
        if bank_account:
            acct_line = bank_account
            if bank_account_type:
                acct_line += f" ({bank_account_type})"
            info_row("Account", acct_line)

    # ── Footer ──
    pdf.ln(6)
    pdf.set_font(font_name, "", 7)
    pdf.set_text_color(128, 128, 128)
    pdf.cell(0, 4, f"Generated: {now_iso()[:19].replace('T', ' ')}", ln=True, align="C")
    pdf.cell(0, 4, "This is a computer-generated payslip. For queries, contact HR: hr@tacjob.com", ln=True, align="C")

    return bytes(pdf.output())


def payslip_widget_html(lang: str, payslip_id: str, session_id: str = "", request_host: str = "127.0.0.1") -> str:
    """Embed the Vue3 payslip widget inside the backend page layout.
    The Vue app mounts into #payslip-widget and loads data via /api/payslip/view.
    """
    config = json.dumps({"payslip_id": payslip_id, "lang": lang, "session_id": session_id}, ensure_ascii=False)
    # Dev mode: load from Vite dev server; Production: load built files
    vue_dev = os.environ.get("VUE_PAYSLIP_DEV", "1") == "1"
    if vue_dev:
        vite_host = request_host if request_host not in ("127.0.0.1", "localhost", "::1") else "127.0.0.1"
        scripts = f"""<script type="module" src="http://{vite_host}:5173/@vite/client"></script>
<script type="module" src="http://{vite_host}:5173/src/main-payslip.js"></script>"""
    else:
        scripts = """<script type="module" src="/payslip-app/assets/main-payslip.js"></script>"""
    return f"""<script>window.__PAYSLIP_CONFIG__ = {config};</script>
<style>
.payslip-container{{max-width:700px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','Noto Sans JP',Arial,sans-serif;font-size:13px;color:#1a1a2e;line-height:1.5}}
.payslip-header{{background:linear-gradient(135deg,#14213d 0%,#1a3a5c 100%);color:white;padding:24px 28px;border-radius:12px 12px 0 0}}
.payslip-header h2{{margin:0 0 4px;font-size:20px;font-weight:850}}
.payslip-header .subtitle{{opacity:.85;font-size:13px}}
.payslip-body{{background:white;border:1px solid #e0e5ec;border-top:none;padding:24px 28px;border-radius:0 0 12px 12px}}
.payslip-body h3{{font-size:14px;color:var(--navy);border-bottom:2px solid var(--blue);padding-bottom:6px;margin:18px 0 10px}}
.payslip-body h3:first-child{{margin-top:0}}
.payslip-info{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;margin-bottom:16px;padding:12px 16px;background:#f8fafc;border-radius:8px}}
.payslip-info .label{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.03em}}
.payslip-info .value{{font-weight:700;font-size:14px}}
.payslip-table{{width:100%;border-collapse:collapse;margin:8px 0}}
.payslip-table td{{padding:6px 12px;border-bottom:1px solid #f0f2f5}}
.payslip-table .right{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.payslip-table .total-row td{{font-weight:850;font-size:15px;border-top:2px solid var(--navy);padding-top:10px;color:var(--blue)}}
.payslip-table .net-row td{{font-weight:850;font-size:18px;color:var(--green);padding:12px;background:#ecfdf5;border-radius:8px}}
.payslip-footer{{margin-top:20px;text-align:center;color:var(--muted);font-size:11px;border-top:1px solid #e0e5ec;padding-top:14px}}
@media print{{body{{background:white;margin:0;padding:0}}.site-header,.primary-nav,main>*:not(.payslip-container){{display:none!important}}.payslip-container{{max-width:100%;box-shadow:none}}.payslip-body{{border:none}}}}
@media(max-width:760px){{.payslip-container{{max-width:100%}}.payslip-header{{padding:20px 18px}}.payslip-body{{padding:20px 18px}}.payslip-info{{grid-template-columns:1fr}}}}
</style>
<div id="payslip-widget"></div>
{scripts}"""


def payslip_json_view(lang: str, payslip_id: str) -> dict[str, Any]:
    """Return payslip data as JSON for Vue3 frontend consumption."""
    all_payslips = load_json(PAYSLIPS_PATH, [])
    ps = next((p for p in all_payslips if p.get("payslip_id") == payslip_id), None)
    if not ps:
        return {"error": "Payslip not found.", "payslip_id": payslip_id}

    # Load monthly record for full salary detail
    monthly_records = load_monthly_records()
    mr = next((r for r in monthly_records if r.get("record_id") == ps.get("record_id", "")), {})

    # Load entity name
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == ps.get("release_id")), None)
    entity_name = "TAC Alliance"
    entity_full = entity_name
    if release:
        entity_full = entity_label(release.get("entity_id", ""), lang)
        entity_name = entity_full.split(" - ")[-1].split(" (")[0] if " - " in entity_full else entity_full

    currency = str(ps.get("currency") or mr.get("payroll_currency") or "SGD")

    # Build earnings detail as structured data
    earnings_items = []
    salary_type = mr.get("salary_type", "monthly")
    basic_salary = money(mr.get("basic_salary", 0))
    hourly_rate = money(mr.get("hourly_rate", 0))
    daily_rate = money(mr.get("daily_rate", 0))
    overtime_rate = money(mr.get("overtime_hourly_rate", 0))
    actual_hours = money(mr.get("actual_work_hours", 0))
    actual_days = money(mr.get("actual_work_days", 0))
    standard_hours = money(mr.get("standard_work_hours", 176))
    standard_days = money(mr.get("standard_work_days", 22))
    paid_leave = money(mr.get("paid_leave_days", 0))
    sick_leave = money(mr.get("sick_leave_days", 0))
    overtime_hours = money(mr.get("overtime_hours", 0))

    position_allowance = money(mr.get("position_allowance", 0))
    fixed_allowance = money(mr.get("fixed_allowance", 0))
    housing_allowance = money(mr.get("housing_allowance", 0))
    commute_allowance = money(mr.get("commute_allowance", 0))
    performance_bonus = money(mr.get("performance_bonus", 0))
    bonus = money(mr.get("bonus", 0))
    other_payment = money(mr.get("other_payment", 0))
    other_earnings = money(mr.get("other_earnings", 0))

    # Build earnings
    if salary_type == "monthly":
        earnings_items.append({"label": "Basic Salary / 基本工资", "amount": basic_salary, "type": "salary"})
        if position_allowance > 0:
            earnings_items.append({"label": "Position Allowance / 岗位津贴", "amount": position_allowance, "type": "allowance"})
        if fixed_allowance > 0:
            earnings_items.append({"label": "Fixed Allowance / 固定津贴", "amount": fixed_allowance, "type": "allowance"})
        if commute_allowance > 0:
            earnings_items.append({"label": "Commute Allowance / 交通津贴", "amount": commute_allowance, "type": "allowance"})
        if housing_allowance > 0:
            earnings_items.append({"label": "Housing Allowance / 住房津贴", "amount": housing_allowance, "type": "allowance"})
        if paid_leave > 0:
            earnings_items.append({"label": "Paid Leave", "amount": paid_leave, "type": "leave", "days": paid_leave, "note": f"{paid_leave:.0f} days"})
        if sick_leave > 0:
            earnings_items.append({"label": "Sick Leave", "amount": sick_leave, "type": "leave", "days": sick_leave, "note": f"{sick_leave:.0f} days"})
    elif salary_type == "hourly":
        base_pay = round(hourly_rate * actual_hours, 2)
        earnings_items.append({"label": "Hourly Rate × Hours", "amount": 0, "type": "info", "note": f"{hourly_rate:,.2f} × {actual_hours:.0f}h"})
        earnings_items.append({"label": "Base Hourly Pay", "amount": base_pay, "type": "salary"})
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                ot_pay = round(overtime_rate * ot_hours, 2)
                earnings_items.append({"label": "Overtime Pay", "amount": ot_pay, "type": "overtime", "note": f"{ot_hours:.0f}h × {overtime_rate:,.2f}"})
    elif salary_type == "daily":
        base_pay = round(daily_rate * actual_days, 2)
        earnings_items.append({"label": "Daily Rate × Days", "amount": 0, "type": "info", "note": f"{daily_rate:,.2f} × {actual_days:.0f}d"})
        earnings_items.append({"label": "Base Daily Pay", "amount": base_pay, "type": "salary"})
    elif salary_type == "monthly_hour":
        ratio = min(actual_hours / max(standard_hours, 1), 1.0)
        monthly_part = round(basic_salary * ratio, 2)
        earnings_items.append({"label": "Basic Salary (monthly portion)", "amount": monthly_part, "type": "salary"})
        regular_hours = min(actual_hours, standard_hours)
        hourly_part = round(hourly_rate * regular_hours, 2)
        earnings_items.append({"label": "Hourly Pay (standard)", "amount": hourly_part, "type": "salary", "note": f"{regular_hours:.0f}h × {hourly_rate:,.2f}"})
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                ot_part = round(overtime_rate * ot_hours, 2)
                earnings_items.append({"label": "Overtime Pay", "amount": ot_part, "type": "overtime", "note": f"{ot_hours:.0f}h × {overtime_rate:,.2f}"})

    # Common extras
    if salary_type != "monthly" and fixed_allowance > 0:
        earnings_items.append({"label": "Fixed Allowance", "amount": fixed_allowance, "type": "allowance"})
    earnings_items.append({"label": "Performance Bonus / 绩效奖金", "amount": performance_bonus, "type": "bonus"})
    if bonus > 0:
        earnings_items.append({"label": "Bonus / 奖金", "amount": bonus, "type": "bonus"})
    earnings_items.append({"label": "Other Payment / 其他支付", "amount": other_payment, "type": "other"})
    if other_earnings > 0:
        earnings_items.append({"label": "Other Earnings", "amount": other_earnings, "type": "other"})

    # Deductions
    deduction_items = []
    cpf_applicable = mr.get("cpf_applicable", False)
    cpf_employee = money(mr.get("cpf_employee", 0))
    income_tax = money(mr.get("income_tax", 0))
    recurring_deductions = money(mr.get("recurring_deductions", 0))
    other_deduction = money(mr.get("other_deduction", 0))
    if cpf_applicable and cpf_employee > 0:
        deduction_items.append({"label": "CPF Employee", "amount": cpf_employee, "type": "cpf"})
    if income_tax > 0:
        deduction_items.append({"label": "Income Tax", "amount": income_tax, "type": "tax"})
    if recurring_deductions > 0:
        deduction_items.append({"label": "Recurring Deductions", "amount": recurring_deductions, "type": "deduction"})
    deduction_items.append({"label": "Other Deduction / 其他扣除", "amount": other_deduction, "type": "other"})

    # Employer costs
    employer_items = []
    cpf_employer = money(mr.get("cpf_employer", 0))
    sdl = money(mr.get("skill_development_levy", 0))
    fwl = money(mr.get("foreign_worker_levy", 0))
    if cpf_applicable and cpf_employer > 0:
        employer_items.append({"label": "CPF Employer", "amount": cpf_employer, "type": "cpf"})
    if sdl > 0:
        employer_items.append({"label": "SDL (Skill Development Levy)", "amount": sdl, "type": "levy"})
    if fwl > 0:
        employer_items.append({"label": "FWL (Foreign Worker Levy)", "amount": fwl, "type": "levy"})

    # Bank info
    bank_info = None
    bank_name = str(clean(mr.get("bank_name", "")))
    bank_account = str(clean(mr.get("bank_account_number", "")))
    if bank_name or bank_account:
        bank_info = {
            "bank_name": bank_name,
            "bank_branch": str(clean(mr.get("bank_branch_name", ""))),
            "bank_account": bank_account,
            "bank_account_type": str(clean(mr.get("bank_account_type", ""))),
        }

    # PDF available
    pdf_available = bool(ps.get("file_name"))

    # Calculation messages for review visibility
    calc_messages = mr.get("calculation_messages", [])

    return {
        "payslip_id": payslip_id,
        "record_id": ps.get("record_id", ""),
        "employee_name": str(ps.get("employee_name", "")),
        "employee_number": str(ps.get("employee_number", "")),
        "department": str(ps.get("department_label", "")),
        "payroll_month": str(ps.get("payroll_month", "")),
        "salary_type": salary_type,
        "currency": currency,
        "entity_name": entity_name,
        "entity_full": entity_full,
        "gross_pay": money(ps.get("gross_pay", 0)),
        "deduction_total": money(ps.get("deduction_total", 0)),
        "net_pay": money(ps.get("net_pay", 0)),
        "employer_cost_total": money(mr.get("employer_cost_total", 0)),
        "earnings": earnings_items,
        "deductions": deduction_items,
        "employer_costs": employer_items,
        "bank_info": bank_info,
        "pdf_available": pdf_available,
        "status": str(ps.get("status", "")),
        "calculation_messages": calc_messages,
        "created_at": str(ps.get("created_at", "")),
    }


def payslip_html_view(lang: str, payslip_id: str) -> str:
    """Render an HTML payslip report with the same layout as the PDF version.
    HR can view this before/after PDF generation for verification.
    """
    all_payslips = load_json(PAYSLIPS_PATH, [])
    ps = next((p for p in all_payslips if p.get("payslip_id") == payslip_id), None)
    if not ps:
        return "<div class='card'><p class='muted'>Payslip not found.</p></div>"

    # Load monthly record for full salary detail
    monthly_records = load_monthly_records()
    mr = next((r for r in monthly_records if r.get("record_id") == ps.get("record_id", "")), {})

    # Load entity name
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == ps.get("release_id")), None)
    entity_name = "TAC Alliance"
    if release:
        entity_display = entity_label(release.get("entity_id", ""), lang)
        entity_name = entity_display.split(" - ")[-1].split(" (")[0] if " - " in entity_display else entity_display

    # Extract data (same as payslip_pdf_bytes)
    employee_name = ps.get('employee_name', '')
    employee_number = ps.get('employee_number', '')
    department = ps.get('department_label', '')
    payroll_month = ps.get('payroll_month', '')
    currency = ps.get('currency', mr.get('payroll_currency', 'SGD'))

    salary_type = mr.get('salary_type', 'monthly')
    basic_salary = money(mr.get('basic_salary', 0))
    hourly_rate = money(mr.get('hourly_rate', 0))
    daily_rate = money(mr.get('daily_rate', 0))
    overtime_rate = money(mr.get('overtime_hourly_rate', 0))
    actual_hours = money(mr.get('actual_work_hours', 0))
    actual_days = money(mr.get('actual_work_days', 0))
    standard_hours = money(mr.get('standard_work_hours', 176))
    standard_days = money(mr.get('standard_work_days', 22))
    paid_leave = money(mr.get('paid_leave_days', 0))
    sick_leave = money(mr.get('sick_leave_days', 0))
    overtime_hours = money(mr.get('overtime_hours', 0))

    position_allowance = money(mr.get('position_allowance', 0))
    fixed_allowance = money(mr.get('fixed_allowance', 0))
    housing_allowance = money(mr.get('housing_allowance', 0))
    commute_allowance = money(mr.get('commute_allowance', 0))
    performance_bonus = money(mr.get('performance_bonus', 0))
    bonus = money(mr.get('bonus', 0))
    other_payment = money(mr.get('other_payment', 0))
    other_earnings = money(mr.get('other_earnings', 0))

    gross_pay = money(ps.get('gross_pay', 0))
    deduction_total = money(ps.get('deduction_total', 0))
    net_pay = money(ps.get('net_pay', 0))
    cpf_employee = money(mr.get('cpf_employee', 0))
    cpf_employer = money(mr.get('cpf_employer', 0))
    income_tax = money(mr.get('income_tax', 0))
    other_deduction = money(mr.get('other_deduction', 0))
    recurring_deductions = money(mr.get('recurring_deductions', 0))
    employer_cost_total = money(mr.get('employer_cost_total', 0))
    sdl = money(mr.get('skill_development_levy', 0))
    fwl = money(mr.get('foreign_worker_levy', 0))

    bank_name = str(clean(mr.get('bank_name', '')))
    bank_branch = str(clean(mr.get('bank_branch_name', '')))
    bank_account = str(clean(mr.get('bank_account_number', '')))
    bank_account_type = str(clean(mr.get('bank_account_type', '')))
    cpf_applicable = mr.get('cpf_applicable', False)

    def fmt(amount):
        return f"{currency} {amount:,.2f}"

    lang_label = {"zh": "中文", "ja": "日本語", "en": "English"}.get(lang, "English")

    # ── Build earnings detail ──
    earnings_rows = []
    if salary_type == "monthly":
        earnings_rows.append(f"<tr><td>Basic Salary / 基本工资</td><td class='right'>{fmt(basic_salary)}</td></tr>")
        if position_allowance > 0:
            earnings_rows.append(f"<tr><td>Position Allowance / 岗位津贴</td><td class='right'>{fmt(position_allowance)}</td></tr>")
        if fixed_allowance > 0:
            earnings_rows.append(f"<tr><td>Fixed Allowance / 固定津贴</td><td class='right'>{fmt(fixed_allowance)}</td></tr>")
        if commute_allowance > 0:
            earnings_rows.append(f"<tr><td>Commute Allowance / 交通津贴</td><td class='right'>{fmt(commute_allowance)}</td></tr>")
        if housing_allowance > 0:
            earnings_rows.append(f"<tr><td>Housing Allowance / 住房津贴</td><td class='right'>{fmt(housing_allowance)}</td></tr>")
        if paid_leave > 0:
            earnings_rows.append(f"<tr><td class='muted'>  Paid Leave: {paid_leave:.0f} days</td><td></td></tr>")
        if sick_leave > 0:
            earnings_rows.append(f"<tr><td class='muted'>  Sick Leave: {sick_leave:.0f} days</td><td></td></tr>")
    elif salary_type == "hourly":
        earnings_rows.append(f"<tr><td class='muted'>Hourly Rate × Actual Hours: {hourly_rate:,.2f} × {actual_hours:.0f}h</td><td></td></tr>")
        earnings_rows.append(f"<tr><td>Base Hourly Pay</td><td class='right'>{fmt(round(hourly_rate * actual_hours, 2))}</td></tr>")
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                earnings_rows.append(f"<tr><td class='muted'>  Overtime ({ot_hours:.0f}h × {overtime_rate:,.2f})</td><td></td></tr>")
                earnings_rows.append(f"<tr><td>Overtime Pay</td><td class='right'>{fmt(round(overtime_rate * ot_hours, 2))}</td></tr>")
    elif salary_type == "daily":
        earnings_rows.append(f"<tr><td class='muted'>Daily Rate × Actual Days: {daily_rate:,.2f} × {actual_days:.0f}d</td><td></td></tr>")
        earnings_rows.append(f"<tr><td>Base Daily Pay</td><td class='right'>{fmt(round(daily_rate * actual_days, 2))}</td></tr>")
    elif salary_type == "monthly_hour":
        ratio = min(actual_hours / max(standard_hours, 1), 1.0)
        monthly_part = round(basic_salary * ratio, 2)
        earnings_rows.append(f"<tr><td>Basic Salary (monthly portion)</td><td class='right'>{fmt(monthly_part)}</td></tr>")
        regular_hours = min(actual_hours, standard_hours)
        hourly_part = round(hourly_rate * regular_hours, 2)
        earnings_rows.append(f"<tr><td class='muted'>  Hourly: {regular_hours:.0f}h × {hourly_rate:,.2f}</td><td></td></tr>")
        earnings_rows.append(f"<tr><td>Hourly Pay (standard)</td><td class='right'>{fmt(hourly_part)}</td></tr>")
        if overtime_rate > 0:
            ot_hours = max(0, actual_hours - standard_hours)
            if ot_hours > 0:
                ot_part = round(overtime_rate * ot_hours, 2)
                earnings_rows.append(f"<tr><td class='muted'>  Overtime: {ot_hours:.0f}h × {overtime_rate:,.2f}</td><td></td></tr>")
                earnings_rows.append(f"<tr><td>Overtime Pay</td><td class='right'>{fmt(ot_part)}</td></tr>")

    # Common allowances and extras (always show for completeness)
    if fixed_allowance > 0 and salary_type != "monthly":
        earnings_rows.append(f"<tr><td>Fixed Allowance</td><td class='right'>{fmt(fixed_allowance)}</td></tr>")
    # Always show Performance Bonus, Other Payment, Other Deduction for review visibility
    earnings_rows.append(f"<tr><td>Performance Bonus / 绩效奖金</td><td class='right'>{fmt(performance_bonus)}</td></tr>")
    if bonus > 0:
        earnings_rows.append(f"<tr><td>Bonus / 奖金</td><td class='right'>{fmt(bonus)}</td></tr>")
    earnings_rows.append(f"<tr><td>Other Payment / 其他支付</td><td class='right'>{fmt(other_payment)}</td></tr>")
    if other_earnings > 0:
        earnings_rows.append(f"<tr><td>Other Earnings</td><td class='right'>{fmt(other_earnings)}</td></tr>")

    # Deductions — always show section for review completeness
    deduction_rows = []
    if cpf_applicable and cpf_employee > 0:
        deduction_rows.append(f"<tr><td>CPF Employee</td><td class='right'>{fmt(cpf_employee)}</td></tr>")
    if income_tax > 0:
        deduction_rows.append(f"<tr><td>Income Tax</td><td class='right'>{fmt(income_tax)}</td></tr>")
    if recurring_deductions > 0:
        deduction_rows.append(f"<tr><td>Recurring Deductions</td><td class='right'>{fmt(recurring_deductions)}</td></tr>")
    # Always show Other Deduction
    deduction_rows.append(f"<tr><td>Other Deduction / 其他扣除</td><td class='right'>{fmt(other_deduction)}</td></tr>")

    # Employer costs
    employer_rows = []
    has_employer = cpf_employer > 0 or sdl > 0 or fwl > 0
    if has_employer:
        if cpf_applicable and cpf_employer > 0:
            employer_rows.append(f"<tr><td>CPF Employer</td><td class='right'>{fmt(cpf_employer)}</td></tr>")
        if sdl > 0:
            employer_rows.append(f"<tr><td>SDL (Skill Development Levy)</td><td class='right'>{fmt(sdl)}</td></tr>")
        if fwl > 0:
            employer_rows.append(f"<tr><td>FWL (Foreign Worker Levy)</td><td class='right'>{fmt(fwl)}</td></tr>")

    # Bank info
    bank_rows = ""
    if bank_name or bank_account:
        bank_parts = []
        if bank_name:
            bank_line = f"Bank: {bank_name}"
            if bank_branch:
                bank_line += f" / {bank_branch}"
            bank_parts.append(f"<tr><td>Bank</td><td>{escape(bank_line)}</td></tr>")
        if bank_account:
            acct_line = bank_account
            if bank_account_type:
                acct_line += f" ({bank_account_type})"
            bank_parts.append(f"<tr><td>Account</td><td>{escape(acct_line)}</td></tr>")
        bank_rows = "".join(bank_parts)

    # PDF download link (if available)
    pdf_download = ""
    if ps.get("file_name"):
        pdf_download = f"<a class='button' href='{with_lang('/payslip/download', lang, payslip_id=payslip_id)}' target='_blank' style='margin-top:12px'>📥 Download PDF</a>"

    return f"""
<style>
.payslip-container{{max-width:700px;margin:0 auto;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','Noto Sans JP',Arial,sans-serif;font-size:13px;color:#1a1a2e;line-height:1.5}}
.payslip-header{{background:linear-gradient(135deg,#14213d 0%,#1a3a5c 100%);color:white;padding:24px 28px;border-radius:12px 12px 0 0}}
.payslip-header h2{{margin:0 0 4px;font-size:20px;font-weight:850}}
.payslip-header .subtitle{{opacity:.85;font-size:13px}}
.payslip-body{{background:white;border:1px solid #e0e5ec;border-top:none;padding:24px 28px;border-radius:0 0 12px 12px}}
.payslip-body h3{{font-size:14px;color:var(--navy);border-bottom:2px solid var(--blue);padding-bottom:6px;margin:18px 0 10px}}
.payslip-body h3:first-child{{margin-top:0}}
.payslip-info{{display:grid;grid-template-columns:1fr 1fr;gap:6px 24px;margin-bottom:16px;padding:12px 16px;background:#f8fafc;border-radius:8px}}
.payslip-info .label{{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.03em}}
.payslip-info .value{{font-weight:700;font-size:14px}}
.payslip-table{{width:100%;border-collapse:collapse;margin:8px 0}}
.payslip-table td{{padding:6px 12px;border-bottom:1px solid #f0f2f5}}
.payslip-table .right{{text-align:right;font-variant-numeric:tabular-nums;font-weight:600}}
.payslip-table .total-row td{{font-weight:850;font-size:15px;border-top:2px solid var(--navy);padding-top:10px;color:var(--blue)}}
.payslip-table .net-row td{{font-weight:850;font-size:18px;color:var(--green);padding:12px;background:#ecfdf5;border-radius:8px}}
.payslip-footer{{margin-top:20px;text-align:center;color:var(--muted);font-size:11px;border-top:1px solid #e0e5ec;padding-top:14px}}
@media print{{
body{{background:white;margin:0;padding:0}}
.site-header,.primary-nav,main>*:not(.payslip-container){{display:none!important}}
.payslip-container{{max-width:100%;box-shadow:none}}
.payslip-body{{border:none}}
}}
</style>
<div class="payslip-container">
<div class="payslip-header">
<h2>📄 Payslip / 工资单</h2>
<div class="subtitle">{escape(entity_name)}</div>
</div>
<div class="payslip-body">
<div class="payslip-info">
<div><div class="label">Payroll Month / 月份</div><div class="value">{escape(payroll_month)}</div></div>
<div><div class="label">Employee / 员工</div><div class="value">{escape(employee_name)}</div></div>
<div><div class="label">Employee No / 工号</div><div class="value">{escape(employee_number)}</div></div>
<div><div class="label">Department / 部门</div><div class="value">{escape(department)}</div></div>
<div><div class="label">Salary Type / 薪资类型</div><div class="value">{escape(salary_type)}</div></div>
<div><div class="label">Currency / 币种</div><div class="value">{escape(currency)}</div></div>
</div>

<h3>💰 Earnings / 应发</h3>
<table class="payslip-table">
{''.join(earnings_rows) if earnings_rows else '<tr><td class="muted">No earnings data</td><td></td></tr>'}
<tr class="total-row"><td>GROSS PAY / 应发合计</td><td class="right">{fmt(gross_pay)}</td></tr>
</table>

<h3>📉 Deductions / 扣除</h3>
<table class="payslip-table">
{''.join(deduction_rows) if deduction_rows else '<tr><td class="muted">No deductions</td><td></td></tr>'}
<tr class="total-row"><td>TOTAL DEDUCTION / 扣除合计</td><td class="right">{fmt(deduction_total)}</td></tr>
</table>

<table class="payslip-table" style="margin-top:12px">
<tr class="net-row"><td>💵 NET PAY / 实发</td><td class="right">{fmt(net_pay)}</td></tr>
</table>

{"<h3>🏢 Employer Costs / 雇主成本</h3><table class='payslip-table'>" + "".join(employer_rows) + f"<tr class='total-row'><td>TOTAL EMPLOYER COST</td><td class='right'>{fmt(employer_cost_total)}</td></tr></table>" if has_employer else ""}

{"<h3>🏦 Bank Info / 银行信息</h3><table class='payslip-table'>" + bank_rows + "</table>" if bank_rows else ""}

<div class="payslip-footer">
<p>Generated: {now_iso()[:19].replace('T', ' ')} · Computer-generated payslip · For queries contact HR: hr@tacjob.com</p>
{pdf_download}
</div>
</div>
</div>
"""


def release_csv_rows(release_id: str) -> list[dict[str, Any]]:
    """Build CSV rows for a release batch, joining payslip data with monthly record bank info."""
    all_payslips = load_json(PAYSLIPS_PATH, [])
    payslips = [p for p in all_payslips if p.get("release_id") == release_id]
    if not payslips:
        return []
    # Load monthly records to get bank info
    monthly_records = load_monthly_records()
    record_by_id = {r.get("record_id"): r for r in monthly_records}
    rows = []
    for ps in payslips:
        mr = record_by_id.get(ps.get("record_id", ""), {})
        rows.append({
            "payroll_month": ps.get("payroll_month", ""),
            "entity_id": mr.get("entity_id", ""),
            "employee_number": ps.get("employee_number", ""),
            "employee_name": ps.get("employee_name", ""),
            "salary_type": mr.get("salary_type", ""),
            "department_label": ps.get("department_label", ""),
            "work_days": mr.get("actual_work_days", mr.get("work_days", "")),
            "work_hours": mr.get("actual_work_hours", mr.get("work_hours", "")),
            "gross_pay": ps.get("gross_pay", 0),
            "cpf_employee": mr.get("cpf_employee", 0),
            "cpf_employer": mr.get("cpf_employer", 0),
            "income_tax": mr.get("income_tax", 0),
            "other_deduction": mr.get("other_deduction", 0),
            "deduction_total": ps.get("deduction_total", 0),
            "net_pay": ps.get("net_pay", 0),
            "employer_cost_total": mr.get("employer_cost_total", 0),
            "skill_development_levy": mr.get("skill_development_levy", 0),
            "foreign_worker_levy": mr.get("foreign_worker_levy", 0),
            "payroll_currency": ps.get("currency", "SGD"),
            "bank_name": mr.get("bank_name", ""),
            "bank_branch_name": mr.get("bank_branch_name", ""),
            "bank_swift_code": mr.get("bank_swift_code", ""),
            "bank_account_type": mr.get("bank_account_type", ""),
            "bank_account_name": mr.get("bank_account_name", ""),
            "bank_account_number": mr.get("bank_account_number", ""),
        })
    return rows


def generate_release_payslips(release_id: str, selected_ids: list[str] | None = None) -> int:
    """Generate PDF payslips for employees in a release batch.

    If selected_ids is provided, only those payslips are generated.
    Otherwise, all payslips in the release are generated.
    """
    all_payslips = load_json(PAYSLIPS_PATH, [])
    payslips = [p for p in all_payslips if p.get("release_id") == release_id]
    if selected_ids:
        id_set = set(selected_ids)
        payslips = [p for p in payslips if p.get("payslip_id") in id_set]
    if not payslips:
        return 0

    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release:
        return 0

    entity_display = entity_label(release.get("entity_id", ""), "en")
    entity_name = entity_display.split(" - ")[-1].split(" (")[0] if " - " in entity_display else "TAC Alliance"

    # Load monthly records for full salary data (bank info, allowances, attendance etc.)
    monthly_records = load_monthly_records()
    record_by_id = {r.get("record_id"): r for r in monthly_records}

    count = 0
    for ps in payslips:
        filename = f"{slug(release['payroll_month'])}_{slug(ps['employee_number'])}_{slug(ps['payslip_id'])}.pdf"
        path = PAYSLIP_DIR / filename
        mr = record_by_id.get(ps.get("record_id", ""), {})
        # Generate type-aware payslip with full salary detail
        pdf_bytes = payslip_pdf_bytes(
            ps_data=ps,
            mr_data=mr,
            entity_name=entity_name,
        )
        path.write_bytes(pdf_bytes)
        ps["file_name"] = filename
        ps["file_path"] = str(path.relative_to(ROOT_DIR))
        ps["status"] = "generated"
        ps["updated_at"] = now_iso()
        count += 1

    # Update release batch status
    for rb in release_batches:
        if rb.get("release_id") == release_id:
            rb["status"] = "payslips_generated"
            rb["payslip_count"] = count
            rb["updated_at"] = now_iso()
            break

    save_json(PAYSLIPS_PATH, all_payslips)
    save_release_batches(release_batches)
    append_audit("tacaipaysg.release", release_id, "payslips_generated",
                  None, {"payslip_count": count})
    return count


def return_release_to_pending(release_id: str) -> bool:
    """Return a release batch to pending_release status, clearing generated PDFs."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release or release.get("status") in ("pending_release", "paid"):
        return False
    # Clear payslip file references
    all_payslips = load_json(PAYSLIPS_PATH, [])
    for ps in all_payslips:
        if ps.get("release_id") == release_id:
            ps["file_name"] = ""
            ps["file_path"] = ""
            ps["status"] = "pending"
            ps["hr_confirmed"] = False
            ps["email_draft_status"] = "not_prepared"
            ps["updated_at"] = now_iso()
    save_json(PAYSLIPS_PATH, all_payslips)
    # Reset release batch
    for rb in release_batches:
        if rb.get("release_id") == release_id:
            rb["status"] = "pending_release"
            rb["payslip_count"] = 0
            rb["email_sent_count"] = 0
            rb["email_failed_count"] = 0
            rb["updated_at"] = now_iso()
            break
    save_release_batches(release_batches)
    append_audit("tacaipaysg.release", release_id, "return_to_pending", None, {"previous_status": release.get("status")})
    return True


def void_release_batch(release_id: str) -> bool:
    """Void a release batch (only from pending_release status)."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release or release.get("status") != "pending_release":
        return False
    for rb in release_batches:
        if rb.get("release_id") == release_id:
            rb["status"] = "voided"
            rb["updated_at"] = now_iso()
            break
    save_release_batches(release_batches)
    # Void all payslips for this release
    all_payslips = load_json(PAYSLIPS_PATH, [])
    for ps in all_payslips:
        if ps.get("release_id") == release_id:
            ps["status"] = "voided"
            ps["updated_at"] = now_iso()
    save_json(PAYSLIPS_PATH, all_payslips)
    append_audit("tacaipaysg.release", release_id, "void_release_batch", None, {})
    return True


def hr_confirm_release_payslips(release_id: str) -> bool:
    """HR confirms all payslips for a release batch."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release or release.get("status") != "payslips_generated":
        return False

    all_payslips = load_json(PAYSLIPS_PATH, [])
    for ps in all_payslips:
        if ps.get("release_id") == release_id:
            ps["hr_confirmed"] = True
            ps["updated_at"] = now_iso()

    release["status"] = "hr_confirmed"
    release["updated_at"] = now_iso()
    save_json(PAYSLIPS_PATH, all_payslips)
    save_release_batches(release_batches)
    append_audit("tacaipaysg.release", release_id, "payslip_hr_confirmed",
                  None, {"status": "hr_confirmed"})
    return True


def mark_release_paid(release_id: str) -> bool:
    """Mark a release batch as paid."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release or release.get("status") != "sent":
        return False

    release["status"] = "paid"
    release["updated_at"] = now_iso()
    save_release_batches(release_batches)
    append_audit("tacaipaysg.release", release_id, "release_completed",
                  None, {"status": "paid"})
    # Auto-generate ledger entry
    generate_ledger_entry(release_id)
    return True


def release_email_draft_html(lang: str, release_id: str) -> str:
    """Email draft preparation page — select employees and preview email."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release:
        return "<div class='card'>Release batch not found.</div>"

    all_payslips = load_json(PAYSLIPS_PATH, [])
    payslips = [p for p in all_payslips if p.get("release_id") == release_id and p.get("hr_confirmed")]
    if not payslips:
        return f"<div class='card'><p class='muted'>{t(lang, 'msg.no_records')}</p><p>No confirmed payslips found. Please generate and confirm payslips first.</p></div>"

    # Build employee selection table
    trs = []
    for ps in payslips:
        has_email = bool(EMAIL_PATTERN.match(ps.get("employee_email", "")))
        email_display = escape(ps.get("employee_email", "")) if has_email else f"<span style='color:var(--red)'>{escape(ps.get('employee_email', 'N/A'))} ⚠</span>"
        trs.append(f"""<tr>
<td><input type='checkbox' name='select_{escape(ps['payslip_id'])}' value='1' {'checked' if has_email else 'disabled'} style='width:auto;min-width:auto'></td>
<td>{escape(ps.get('employee_number',''))}</td>
<td>{escape(ps.get('employee_name',''))}</td>
<td>{escape(ps.get('department_label',''))}</td>
<td>{email_display}</td>
<td class='right'>{money_fmt(ps.get('net_pay'))}</td>
</tr>""")

    payroll_month = release.get("payroll_month", "")
    email_subject = f"TAC Payroll SG - Payslip {payroll_month} / 工资单"
    email_body = f"""Dear {{{{employee_name}}}},

Please find your payslip for {payroll_month} attached.

如有疑问请联系HR。
ご不明な点がございましたら、人事部までお問い合わせください。

Regards,
TAC Payroll SG"""

    entity_display = entity_label(release.get("entity_id", ""), lang)
    smtp_note = f"<div class='message-strip message-warning'>{t(lang, 'msg.smtp_not_configured')}</div>" if not SMTP_HOST else ""

    return f"""
<div class="sap-page-header"><h1>{t(lang, 'action.release_email_draft')}: {escape(release_id)}</h1><div class="sap-info-strip"><span>📅 {escape(payroll_month)}</span><span>🏢 {escape(entity_display)}</span><span>📧 Select employees to receive payslip emails</span></div></div>
{smtp_note}
<div class="card"><div class="section-header"><h3>{t(lang, 'label.select_employees')}</h3></div>
<div class="sap-toolbar" style="margin-bottom:8px">
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('input[name^=select_]').forEach(c=>{{if(!c.disabled)c.checked=true}});updateEmailCount()">✅ Select All</button>
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('input[name^=select_]').forEach(c=>{{if(!c.disabled)c.checked=false}});updateEmailCount()">⬜ Deselect All</button>
  <span class="muted" style="font-size:12px;margin-left:8px" id="email-count">{len(payslips)} selected</span>
</div>
<form method="post" action="{with_lang('/release/email-draft/prepare', lang, release_id=release_id)}">
<div class='table-scroll'><table><thead><tr><th style='width:30px'><input type='checkbox' id='select-all' checked style='width:auto;min-width:auto' onclick=\"var c=this.checked;document.querySelectorAll('input[name^=select_]').forEach(x=>{{if(!x.disabled)x.checked=c}});updateEmailCount()\"></th><th>No.</th><th>Name</th><th>Dept</th><th>Email</th><th>Net Pay</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(payslips)} employee(s). Uncheck to skip sending.</div>
<script>
function updateEmailCount(){{var sel=document.querySelectorAll('input[name^=select_]:checked').length;var el=document.getElementById('email-count');if(el)el.textContent=sel+' selected'}}
document.querySelectorAll('input[name^=select_]').forEach(function(cb){{cb.addEventListener('change',updateEmailCount)}});
</script></div>
<div class="card"><div class="section-header"><h3>{t(lang, 'label.email_preview')}</h3></div>
<div class="field"><label>{t(lang, 'label.email_subject')}</label><input value="{escape(email_subject)}" readonly></div>
<div class="field"><label>{t(lang, 'label.email_body')}</label><textarea rows="10" readonly style="font-family:monospace;">{escape(email_body)}</textarea></div>
<p class="message-strip message-info">{t(lang, 'msg.email_draft_security_note')}</p>
</div>
<div class="card"><div class="sap-toolbar">
<a class="button secondary" href="{with_lang('/release/detail', lang, release_id=release_id)}">← {t(lang, 'action.cancel')}</a>
<button style="font-size:16px;min-width:200px">{t(lang, 'action.release_email_send')}</button>
</div></div>
</form>"""


def release_email_send_html(lang: str, release_id: str, selected_ids: list[str] | None = None) -> str:
    """Email send confirmation page."""
    release_batches = load_release_batches()
    release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if not release:
        return "<div class='card'>Release batch not found.</div>"

    all_payslips = load_json(PAYSLIPS_PATH, [])
    all_release_payslips = [p for p in all_payslips if p.get("release_id") == release_id and p.get("hr_confirmed")]

    selected = all_release_payslips
    if selected_ids:
        selected = [p for p in all_release_payslips if p.get("payslip_id") in selected_ids]

    valid = [p for p in selected if EMAIL_PATTERN.match(p.get("employee_email", ""))]
    invalid = [p for p in selected if not EMAIL_PATTERN.match(p.get("employee_email", ""))]

    trs = []
    for ps in valid:
        trs.append(f"<tr><td>{escape(ps.get('employee_number',''))}</td><td>{escape(ps.get('employee_name',''))}</td><td>{escape(ps.get('employee_email',''))}</td><td class='right'>{money_fmt(ps.get('net_pay'))}</td><td>✅</td></tr>")
    for ps in invalid:
        trs.append(f"<tr style='color:var(--muted)'><td>{escape(ps.get('employee_number',''))}</td><td>{escape(ps.get('employee_name',''))}</td><td style='color:var(--red)'>{escape(ps.get('employee_email',''))}</td><td class='right'>{money_fmt(ps.get('net_pay'))}</td><td>❌</td></tr>")

    payroll_month = release.get("payroll_month", "")
    entity_display = entity_label(release.get("entity_id", ""), lang)
    smtp_note = f"<div class='message-strip message-warning'>{t(lang, 'msg.smtp_not_configured')}</div>" if not SMTP_HOST else ""

    # Build form with hidden inputs for selected IDs
    hidden_inputs = "".join(f"<input type='hidden' name='payslip_ids' value='{escape(p['payslip_id'])}'>" for p in valid)

    return f"""
<div class="sap-page-header"><h1>{t(lang, 'action.release_email_send')}: {escape(release_id)}</h1><div class="sap-info-strip"><span>📅 {escape(payroll_month)}</span><span>🏢 {escape(entity_display)}</span><span>⚠️ Actual emails will be sent — review carefully</span></div></div>
{smtp_note}
<div class="card"><div class="section-header"><h3>{t(lang, 'label.send_summary')}</h3></div>
<div class="grid">
  <div class="metric-card"><div>{t(lang, 'label.select_employees')}</div><div class="value">{len(selected)}</div></div>
  <div class="metric-card"><div>Valid / 有效</div><div class="value" style="color:var(--green)">{len(valid)}</div></div>
  <div class="metric-card"><div>Invalid / 无效</div><div class="value" style="color:var(--red)">{len(invalid)}</div></div>
</div></div>
<div class="card"><div class="section-header"><h3>{t(lang, 'label.email_preview')}</h3></div>
<div class="field"><label>{t(lang, 'label.email_subject')}</label><input value="TAC Payroll SG - Payslip {escape(payroll_month)} / 工资单" readonly></div>
<div class="field"><label>From</label><input value="{escape(PAYSLIP_SENDER_NAME)} <{escape(PAYSLIP_SENDER)}>" readonly></div>
<p class="message-strip message-info">{t(lang, 'msg.email_draft_security_note')}</p>
</div>
<div class="card"><div class="section-header"><h3>{t(lang, 'label.email_to')} ({len(valid)} employees)</h3></div>
<div class='table-scroll'><table><thead><tr><th>No.</th><th>Name</th><th>Email</th><th>Net Pay</th><th>OK</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>
</div>
<div class="card"><form method="post" action="{with_lang('/release/email-send/confirm', lang, release_id=release_id)}" onsubmit="return confirm({json.dumps(t(lang, 'msg.release_email_confirm'))})">
{hidden_inputs}
<div class="checkbox-field" style="margin-bottom:16px"><input type="checkbox" name="email_review_confirmed" value="1" required style="width:auto;min-width:auto"><label style="font-weight:800">{t(lang, 'label.hr_confirm_checkbox')}</label></div>
<div class="sap-toolbar">
<a class="button secondary" href="{with_lang('/release/detail', lang, release_id=release_id)}">← {t(lang, 'action.cancel')}</a>
<button class="danger" style="font-size:16px;min-width:200px" {'disabled' if not valid else ''}>{t(lang, 'action.release_email_send')} ({len(valid)} employees)</button>
</div>
</form></div>"""


def send_release_emails(release_id: str, payslip_ids: list[str]) -> tuple[int, int]:
    """Send payslip emails to selected employees. Returns (sent, failed)."""
    all_payslips = load_json(PAYSLIPS_PATH, [])
    deliveries = load_json(EMAIL_DELIVERIES_PATH, [])
    sent = 0
    failed = 0

    for ps in all_payslips:
        if ps.get("payslip_id") not in payslip_ids:
            continue
        if ps.get("release_id") != release_id:
            continue

        email = clean(ps.get("employee_email"))
        delivery = {
            "delivery_id": f"DEL-{len(deliveries) + 1:06d}",
            "payslip_id": ps.get("payslip_id"),
            "release_id": release_id,
            "recipient": email,
            "employee_name": ps.get("employee_name", ""),
            "department": ps.get("department_label", ""),
            "subject_snapshot": f"TAC Payroll SG - Payslip {ps.get('payroll_month', '')} / 工资单",
            "retry_count": 0,
            "status": "queued",
            "message": "",
            "created_at": now_iso(),
            "sent_at": "",
        }

        if not EMAIL_PATTERN.match(email):
            delivery["status"] = "failed"
            delivery["message"] = "Invalid or missing employee email."
            ps["email_draft_status"] = "send_failed"
            failed += 1
            deliveries.append(delivery)
            continue

        pdf_path = ROOT_DIR / clean(ps.get("file_path", ""))
        if not pdf_path.exists() or PAYSLIP_DIR not in pdf_path.resolve().parents:
            delivery["status"] = "failed"
            delivery["message"] = "Payslip PDF not found."
            ps["email_draft_status"] = "send_failed"
            failed += 1
            deliveries.append(delivery)
            continue

        if not SMTP_HOST:
            delivery["status"] = "queued"
            delivery["message"] = "SMTP not configured; kept in queue."
            ps["email_draft_status"] = "draft_prepared"
            deliveries.append(delivery)
            continue

        try:
            msg = EmailMessage()
            msg["From"] = formataddr((PAYSLIP_SENDER_NAME, PAYSLIP_SENDER))
            msg["To"] = email
            msg["Subject"] = delivery["subject_snapshot"]
            body = f"Dear {ps.get('employee_name', 'employee')},\n\nPlease find your payslip for {ps.get('payroll_month', '')} attached.\n\n如有疑问请联系HR。\nご不明な点がございましたら、人事部までお問い合わせください。\n\nRegards,\nTAC Payroll SG"
            msg.set_content(body)
            msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)

            if SMTP_USE_TLS:
                with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                    server.starttls(context=ssl.create_default_context())
                    if SMTP_USERNAME:
                        server.login(SMTP_USERNAME, SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as server:
                    if SMTP_USERNAME:
                        server.login(SMTP_USERNAME, SMTP_PASSWORD)
                    server.send_message(msg)

            delivery["status"] = "sent"
            delivery["sent_at"] = now_iso()
            ps["email_draft_status"] = "sent"
            sent += 1
        except Exception as exc:
            delivery["status"] = "failed"
            delivery["message"] = str(exc)
            ps["email_draft_status"] = "send_failed"
            failed += 1

        ps["updated_at"] = now_iso()
        deliveries.append(delivery)

    save_json(PAYSLIPS_PATH, all_payslips)
    save_json(EMAIL_DELIVERIES_PATH, deliveries)

    # Push to Message Center in parallel with email delivery
    # Collect payslips that had valid email delivery attempted
    msg_payslips = [p for p in all_payslips if p.get("payslip_id") in payslip_ids and p.get("release_id") == release_id]
    batch_id = msg_payslips[0].get("batch_id", "") if msg_payslips else ""
    msg_center_result = publish_payslip_notifications_to_msg_center(batch_id, msg_payslips)

    # Update release batch counts
    release_batches = load_release_batches()
    for rb in release_batches:
        if rb.get("release_id") == release_id:
            rb["email_sent_count"] = (rb.get("email_sent_count", 0) + sent)
            rb["email_failed_count"] = (rb.get("email_failed_count", 0) + failed)
            rb["status"] = "sent" if failed == 0 else "partially_sent"
            rb["updated_at"] = now_iso()
            # Record message center delivery stats
            rb["msg_center_sent_count"] = msg_center_result.get("sent_count", 0)
            rb["msg_center_failed_count"] = msg_center_result.get("failed_count", 0)
            rb["msg_center_skipped_no_account"] = msg_center_result.get("skipped_no_account", 0)
            rb["msg_center_message"] = msg_center_result.get("message", "")
            break
            break
    save_release_batches(release_batches)

    append_audit("tacaipaysg.release", release_id, "email_sent",
                  None, {"sent": sent, "failed": failed})

    return sent, failed


def resend_single_payslip_email(payslip_id: str) -> tuple[bool, str]:
    """Resend a single payslip email. Returns (success, message)."""
    all_payslips = load_json(PAYSLIPS_PATH, [])
    ps = next((p for p in all_payslips if p.get("payslip_id") == payslip_id), None)
    if not ps:
        return False, "Payslip not found."

    email = clean(ps.get("employee_email"))
    if not EMAIL_PATTERN.match(email):
        return False, "Invalid employee email."

    pdf_path = ROOT_DIR / clean(ps.get("file_path", ""))
    if not pdf_path.exists():
        return False, "Payslip PDF not found."

    if not SMTP_HOST:
        return False, "SMTP not configured."

    try:
        msg = EmailMessage()
        msg["From"] = formataddr((PAYSLIP_SENDER_NAME, PAYSLIP_SENDER))
        msg["To"] = email
        msg["Subject"] = f"TAC Payroll SG - Payslip {ps.get('payroll_month', '')} / 工资单"
        body = f"Dear {ps.get('employee_name', 'employee')},\n\nPlease find your payslip for {ps.get('payroll_month', '')} attached.\n\n如有疑问请联系HR。\nご不明な点がございましたら、人事部までお問い合わせください。\n\nRegards,\nTAC Payroll SG"
        msg.set_content(body)
        msg.add_attachment(pdf_path.read_bytes(), maintype="application", subtype="pdf", filename=pdf_path.name)

        if SMTP_USE_TLS:
            with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=20) as server:
                server.starttls(context=ssl.create_default_context())
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)
        else:
            with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=20, context=ssl.create_default_context()) as server:
                if SMTP_USERNAME:
                    server.login(SMTP_USERNAME, SMTP_PASSWORD)
                server.send_message(msg)

        ps["email_draft_status"] = "sent"
        ps["updated_at"] = now_iso()
        save_json(PAYSLIPS_PATH, all_payslips)

        # Update email delivery record
        deliveries = load_json(EMAIL_DELIVERIES_PATH, [])
        for d in deliveries:
            if d.get("payslip_id") == payslip_id and d.get("status") == "failed":
                d["status"] = "sent"
                d["sent_at"] = now_iso()
                d["retry_count"] = d.get("retry_count", 0) + 1
                d["message"] = "Resent successfully."
                break
        else:
            deliveries.append({
                "delivery_id": f"DEL-{len(deliveries) + 1:06d}",
                "payslip_id": payslip_id,
                "release_id": ps.get("release_id", ""),
                "recipient": email,
                "employee_name": ps.get("employee_name", ""),
                "department": ps.get("department_label", ""),
                "subject_snapshot": f"TAC Payroll SG - Payslip {ps.get('payroll_month', '')} / 工资单",
                "retry_count": 1,
                "status": "sent",
                "message": "Resent.",
                "created_at": now_iso(),
                "sent_at": now_iso(),
            })
        save_json(EMAIL_DELIVERIES_PATH, deliveries)

        # Update release batch failed count
        release_id = ps.get("release_id", "")
        if release_id:
            release_batches = load_release_batches()
            for rb in release_batches:
                if rb.get("release_id") == release_id:
                    rb["email_failed_count"] = max(0, rb.get("email_failed_count", 0) - 1)
                    rb["email_sent_count"] = rb.get("email_sent_count", 0) + 1
                    if rb.get("email_failed_count", 0) == 0 and rb.get("status") == "partially_sent":
                        rb["status"] = "sent"
                    rb["updated_at"] = now_iso()
                    break
            save_release_batches(release_batches)

        append_audit("tacaipaysg.release", release_id, "email_resent",
                      None, {"payslip_id": payslip_id, "recipient": email})
        return True, "Sent successfully."
    except Exception as exc:
        return False, str(exc)


def batch_resend_failed_emails(release_id: str) -> tuple[int, int]:
    """Resend all failed payslip emails in a release batch. Returns (sent, failed)."""
    all_payslips = load_json(PAYSLIPS_PATH, [])
    failed_ps = [p for p in all_payslips if p.get("release_id") == release_id and p.get("email_draft_status") == "send_failed"]
    sent = 0
    failed = 0
    for ps in failed_ps:
        ok, _ = resend_single_payslip_email(ps["payslip_id"])
        if ok:
            sent += 1
        else:
            failed += 1
    return sent, failed


def next_sheet_id(month: str, entity_id: str, country_code: str = "SG") -> str:
    return f"MSS-{country_code}-{month.replace('-', '')}-{slug(entity_id)}"

def next_monthly_record_id(sheet_id: str, employee_id: str) -> str:
    return f"{sheet_id}-{slug(employee_id)}"

def find_sheet(sheet_id: str) -> dict[str, Any] | None:
    return next((s for s in load_sheets() if s.get("sheet_id") == sheet_id), None)

def sheet_records(sheet_id: str) -> list[dict[str, Any]]:
    return [r for r in load_monthly_records() if r.get("sheet_id") == sheet_id]

def get_calendar_month_days(country_code: str, year: int, month: int) -> tuple[int, int]:
    """Return (standard_work_days, standard_work_hours) for a given country/year/month from payroll calendar."""
    calendars = load_calendars()
    cal = next((c for c in calendars if c.get("country_code") == country_code.upper() and c.get("year") == year and c.get("status") == "active"), None)
    if not cal:
        _, days_in_month = monthrange(year, month)
        return min(22, days_in_month), min(176, days_in_month * 8)
    month_key = f"{month:02d}"
    month_data = cal.get("months", {}).get(month_key)
    if not month_data:
        _, days_in_month = monthrange(year, month)
        return min(22, days_in_month), min(176, days_in_month * 8)
    work_days = int(month_data.get("standard_work_days", 22))
    work_hours = work_days * 8
    return work_days, work_hours

def create_monthly_sheet(payroll_month: str, entity_id: str, country_code: str = "SG", attendance_source: str = "manual", employee_ids: list[str] | None = None, standard_work_days: int = 0) -> tuple[dict[str, Any], int]:
    """Create a monthly salary sheet from active salary master records."""
    payroll_month = payroll_month or datetime.now().strftime("%Y-%m")
    # Entity comes from form dropdown (master data), no longer defaults to "SG"
    sheet_id = next_sheet_id(payroll_month, entity_id, country_code)
    sheets = load_sheets()
    existing = next((s for s in sheets if s.get("sheet_id") == sheet_id), None)
    if existing:
        return existing, 0
    all_employees = active_sg_salary_master(entity_id)
    if employee_ids is not None:
        id_set = set(employee_ids)
        employees = [e for e in all_employees if e.get("employee_id") in id_set]
    else:
        employees = all_employees
    year, month = int(payroll_month[:4]), int(payroll_month[5:7])
    std_days, std_hours = get_calendar_month_days(country_code, year, month)
    # Allow manual override of standard work days; recalc std_hours accordingly
    if standard_work_days > 0:
        std_days = standard_work_days
        std_hours = standard_work_days * 8
    sheet = {
        "sheet_id": sheet_id,
        "country_code": country_code,
        "entity_id": entity_id,
        "payroll_month": payroll_month,
        "status": "draft",
        "version": 1,
        "employee_count": len(employees),
        "standard_work_days": std_days,
        "standard_work_hours": std_hours,
        "attendance_source": attendance_source,
        "attendance_locked": False,
        "basic_info_confirmed_at": "",
        "basic_info_confirmed_by": "",
        "calculated_at": "",
        "calculated_by": "",
        "gross_total": 0,
        "deduction_total": 0,
        "net_total": 0,
        "employer_cost_total": 0,
        "currency_totals": {},
        "created_at": now_iso(),
        "created_by": USER_ACTOR,
        "updated_at": now_iso(),
        "notes": "",
    }
    records = load_monthly_records()
    for employee in employees:
        records.append(_create_monthly_record(sheet, employee, attendance_source))
    sheets.append(sheet)
    save_sheets(sheets)
    save_monthly_records(records)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "create_sheet", None, sheet)
    return sheet, len(employees)

def _create_monthly_record(sheet: dict[str, Any], employee: dict[str, Any], attendance_source: str = "manual") -> dict[str, Any]:
    """Create an individual monthly salary record from a salary master entry."""
    std_days = sheet.get("standard_work_days", 22)
    std_hours = sheet.get("standard_work_hours", 176)
    return {
        "record_id": next_monthly_record_id(sheet["sheet_id"], employee["employee_id"]),
        "sheet_id": sheet["sheet_id"],
        "payroll_month": sheet["payroll_month"],
        "country_code": sheet["country_code"],
        "entity_id": employee.get("entity_id", sheet["entity_id"]),
        "employee_id": employee["employee_id"],
        "employee_number": employee["employee_number"],
        "employee_name": employee["employee_name"],
        "email": employee.get("email", ""),
        "department_label": employee.get("department_label", ""),
        "team_label": employee.get("team_label", ""),
        "salary_type": employee.get("salary_type", "monthly"),
        "bank_name": employee.get("bank_name", ""),
        "bank_branch_name": employee.get("bank_branch_name", ""),
        "bank_swift_code": employee.get("bank_swift_code", ""),
        "bank_account_type": employee.get("bank_account_type", "ordinary"),
        "bank_account_name": employee.get("bank_account_name", ""),
        "bank_account_number": employee.get("bank_account_number", ""),
        "payroll_currency": employee.get("payroll_currency", "SGD"),
        "basic_salary": employee.get("basic_salary", 0),
        "hourly_rate": employee.get("hourly_rate", 0),
        "daily_rate": employee.get("daily_rate", 0),
        "standard_monthly_hours": employee.get("standard_monthly_hours", 160),
        "overtime_hourly_rate": employee.get("overtime_hourly_rate", 0),
        "standard_work_days": std_days,
        "standard_work_hours": std_hours,
        "actual_work_days": std_days,
        "actual_work_hours": 0,
        "paid_leave_days": 0,
        "unpaid_leave_days": 0,
        "sick_leave_days": 0,
        "overtime_hours": 0,
        "late_night_hours": 0,
        "holiday_hours": 0,
        "absence_days": 0,
        "attendance_source": attendance_source,
        "timesheet_ref": "",
        "fixed_allowance": employee.get("fixed_allowance", 0),
        "performance_bonus": 0,
        "performance_reference": employee.get("performance_bonus", 0),
        "bonus": 0,
        "other_payment": 0,
        "recurring_deductions": employee.get("recurring_deductions", 0),
        "other_deduction": 0,
        "income_tax": 0,
        "cpf_applicable": employee.get("cpf_applicable", False),
        "cpf_input_mode": employee.get("cpf_input_mode", "manual"),
        "cpf_employee_manual": employee.get("cpf_employee_manual", 0),
        "cpf_employer_manual": employee.get("cpf_employer_manual", 0),
        "skill_development_levy": employee.get("skill_development_levy", 0),
        "foreign_worker_levy": employee.get("foreign_worker_levy", 0),
        "base_pay_calculated": 0,
        "gross_pay": 0,
        "cpf_employee": 0,
        "cpf_employer": 0,
        "deduction_total": 0,
        "net_pay": 0,
        "employer_cost_total": 0,
        "calculation_messages": [],
        "status": "draft",
        "hr_confirmed_at": "",
        "hr_confirmed_by": "",
        "manager_review_status": "pending",
        "manager_review_comment": "",
        "version": 1,
        "created_at": now_iso(),
        "updated_at": now_iso(),
    }

def update_monthly_record_from_form(record_id: str, form: dict[str, list[str]]) -> bool:
    """Update a monthly salary record's attendance and input fields from form data.
    Only allowed when the parent sheet is in draft or hr_confirmed status.
    Returns True on success, False if locked."""
    records = load_monthly_records()
    record = next((r for r in records if r.get("record_id") == record_id), None)
    if not record:
        return False
    # Check parent sheet status — only allow edits in draft/hr_confirmed
    sheet_id = record.get("sheet_id", "")
    sheet = find_sheet(sheet_id)
    if not sheet or sheet.get("status") not in ("draft", "hr_confirmed"):
        return False
    before = dict(record)
    fields = [
        "actual_work_days", "actual_work_hours", "paid_leave_days", "unpaid_leave_days",
        "sick_leave_days",
        "overtime_hours", "late_night_hours", "holiday_hours", "absence_days",
        "fixed_allowance", "performance_bonus", "bonus", "other_payment",
        "recurring_deductions", "other_deduction", "income_tax",
        "cpf_employee_manual", "cpf_employer_manual",
        "skill_development_levy", "foreign_worker_levy",
        "standard_work_days", "standard_work_hours",
    ]
    for field in fields:
        if field in form:
            record[field] = money(form[field][0])
    if "payroll_currency" in form:
        record["payroll_currency"] = clean(form["payroll_currency"][0])
    record["updated_at"] = now_iso()
    save_monthly_records(records)
    append_audit("tacaipaysg.monthly_record", record_id, "update_record", before,
                  next(r for r in load_monthly_records() if r.get("record_id") == record_id))
    return True


def save_monthly_sheet_review(sheet_id: str, form: dict[str, list[str]]) -> int:
    """Bulk save review edits for all records in a monthly sheet.
    Only saves when sheet status is draft or hr_confirmed (editable states)."""
    sheet = find_sheet(sheet_id)
    if not sheet or sheet.get("status") not in ("draft", "hr_confirmed"):
        return 0  # Sheet is locked, refuse to save
    editable_fields = [
        "actual_work_days", "actual_work_hours", "paid_leave_days", "unpaid_leave_days",
        "sick_leave_days",
        "overtime_hours", "late_night_hours", "holiday_hours", "absence_days",
        "standard_work_days", "standard_work_hours",
        "fixed_allowance", "performance_bonus", "bonus", "other_payment",
        "recurring_deductions", "other_deduction", "income_tax",
        "cpf_employee_manual", "cpf_employer_manual",
    ]
    records = load_monthly_records()
    count = 0
    for record in records:
        if record.get("sheet_id") != sheet_id:
            continue
        before = dict(record)
        changed = False
        for field in editable_fields:
            form_key = f"{field}_{record['record_id']}"
            if form_key in form:
                new_val = money(form[form_key][0])
                if record.get(field) != new_val:
                    record[field] = new_val
                    changed = True
        # String fields (not monetary)
        for field in ["payroll_currency"]:
            form_key = f"{field}_{record['record_id']}"
            if form_key in form:
                new_val = clean(form[form_key][0])
                if record.get(field) != new_val:
                    record[field] = new_val
                    changed = True
        if changed:
            record["updated_at"] = now_iso()
            count += 1
            append_audit("tacaipaysg.monthly_record", record["record_id"], "review_update", before, dict(record))
    save_monthly_records(records)
    return count


def batch_set_attendance(sheet_id: str, work_days: float, work_hours: float) -> int:
    """Set actual work days/hours for all records in a sheet."""
    records = load_monthly_records()
    count = 0
    for record in records:
        if record.get("sheet_id") == sheet_id:
            record["actual_work_days"] = work_days
            record["actual_work_hours"] = work_hours
            record["updated_at"] = now_iso()
            count += 1
    save_monthly_records(records)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "batch_set_attendance", None, {"work_days": work_days, "work_hours": work_hours, "count": count})
    return count

def confirm_basic_info(sheet_id: str, user: str = USER_ACTOR) -> bool:
    """Confirm basic info for a monthly sheet — locks attendance and moves to hr_confirmed."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "draft":
                return False
            before = dict(sheet)
            sheet["status"] = "hr_confirmed"
            sheet["attendance_locked"] = True
            sheet["basic_info_confirmed_at"] = now_iso()
            sheet["basic_info_confirmed_by"] = user
            sheet["updated_at"] = now_iso()
            sheet["version"] = 1
            save_sheets(sheets)
            # Snapshot records as version 1
            records = load_monthly_records()
            for record in records:
                if record.get("sheet_id") == sheet_id:
                    record["status"] = "hr_confirmed"
                    record["hr_confirmed_at"] = now_iso()
                    record["hr_confirmed_by"] = user
                    record["version"] = 1
                    record["updated_at"] = now_iso()
            save_monthly_records(records)
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "confirm_basic_info", before, dict(sheet))
            return True
    return False

def return_sheet_to_draft(sheet_id: str, comment: str = "") -> bool:
    """Return a sheet from hr_confirmed back to draft. One step back only."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "hr_confirmed":
                return False
            before = dict(sheet)
            sheet["status"] = "draft"
            sheet["attendance_locked"] = False
            sheet["basic_info_confirmed_at"] = ""
            sheet["basic_info_confirmed_by"] = ""
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            records = load_monthly_records()
            for record in records:
                if record.get("sheet_id") == sheet_id:
                    record["status"] = "draft"
                    record["hr_confirmed_at"] = ""
                    record["hr_confirmed_by"] = ""
                    record["updated_at"] = now_iso()
            save_monthly_records(records)
            after_val = dict(sheet)
            after_val["_return_comment"] = comment
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "return_to_draft", before, after_val)
            return True
    return False


def return_sheet_to_hr_confirmed(sheet_id: str, comment: str = "") -> bool:
    """Return a sheet from calculated back to hr_confirmed. One step back only."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "calculated":
                return False
            before = dict(sheet)
            sheet["status"] = "hr_confirmed"
            sheet["calculated_at"] = ""
            sheet["calculated_by"] = ""
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            records = load_monthly_records()
            for record in records:
                if record.get("sheet_id") == sheet_id:
                    record["status"] = "hr_confirmed"
                    # Clear calculated results
                    for key in ("base_pay_calculated", "cpf_employee", "cpf_employer",
                                "skill_development_levy", "foreign_worker_levy",
                                "gross_pay", "deduction_total", "net_pay", "employer_cost_total",
                                "calculation_messages"):
                        if key in record:
                            record[key] = 0 if key != "calculation_messages" else []
                    record["updated_at"] = now_iso()
            save_monthly_records(records)
            after_val = dict(sheet)
            after_val["_return_comment"] = comment
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "return_to_hr_confirmed", before, after_val)
            return True
    return False


def return_sheet_to_calculated(sheet_id: str, comment: str = "") -> bool:
    """Return a sheet from hr_reviewed back to calculated. One step back only."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "hr_reviewed":
                return False
            before = dict(sheet)
            sheet["status"] = "calculated"
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            after_val = dict(sheet)
            after_val["_return_comment"] = comment
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "return_to_calculated", before, after_val)
            return True
    return False


def return_sheet_to_hr_reviewed(sheet_id: str, comment: str = "") -> bool:
    """Return a sheet from manager_review back to hr_reviewed (HR-initiated, not manager reject)."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "manager_review":
                return False
            before = dict(sheet)
            sheet["status"] = "hr_reviewed"
            sheet["manager_review_sent_at"] = ""
            sheet["manager_review_sent_by"] = ""
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            # Reset manager review status on records
            records = load_monthly_records()
            for r in records:
                if r.get("sheet_id") == sheet_id:
                    r["manager_review_status"] = "pending"
                    r["manager_review_comment"] = ""
                    r["updated_at"] = now_iso()
            save_monthly_records(records)
            after_val = dict(sheet)
            after_val["_return_comment"] = comment
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "return_to_hr_reviewed", before, after_val)
            return True
    return False


def return_sheet_to_manager_review(sheet_id: str, comment: str = "") -> bool:
    """Return a sheet from finalized back to manager_review. One step back only.

    Only allowed if no payslips have been generated yet in the release batch.
    """
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "finalized":
                return False
            # Prevent return if release batch has progressed past pending
            release_id = next_release_id(sheet.get("payroll_month", ""), sheet.get("entity_id", ""), sheet.get("country_code", "SG"))
            release_batches = load_release_batches()
            existing_release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
            if existing_release and existing_release.get("status") != "pending_release":
                return False  # Cannot return once payslips have been generated
            before = dict(sheet)
            sheet["status"] = "manager_review"
            sheet["manager_approved_at"] = ""
            sheet["manager_approved_by"] = ""
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            # Reset manager approval status on records
            records = load_monthly_records()
            for r in records:
                if r.get("sheet_id") == sheet_id:
                    r["manager_review_status"] = "pending"
                    r["manager_review_comment"] = ""
                    r["updated_at"] = now_iso()
            save_monthly_records(records)
            after_val = dict(sheet)
            after_val["_return_comment"] = comment
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "return_to_manager_review", before, after_val)
            return True
    return False


def calculate_monthly_record(record: dict[str, Any], parameters: list[dict[str, Any]]) -> dict[str, Any]:
    """Calculate payroll for a single monthly record. Supports monthly, hourly, daily, monthly_hour."""
    messages: list[str] = []
    salary_type = clean(record.get("salary_type") or "monthly")
    actual_hours = money(record.get("actual_work_hours"))
    actual_days = money(record.get("actual_work_days"))
    base = 0.0
    overtime_pay = 0.0

    # ── Base pay calculation ──
    if salary_type == "hourly":
        std_monthly_hours = money(record.get("standard_monthly_hours")) or 160
        ot_rate = money(record.get("overtime_hourly_rate")) or 0
        hourly_rate = money(record.get("hourly_rate"))
        if ot_rate > 0:
            # Overtime rate defined → split regular vs OT hours
            regular_hours = min(actual_hours, std_monthly_hours)
            ot_hours_calc = max(0.0, actual_hours - std_monthly_hours)
            base = round(hourly_rate * regular_hours, 2)
            overtime_pay = round(ot_rate * ot_hours_calc, 2)
            messages.append(f"Hourly: {regular_hours}h × {money_fmt(hourly_rate)} = {money_fmt(base)}")
            if overtime_pay > 0:
                messages.append(f"OT: {ot_hours_calc}h × {money_fmt(ot_rate)} = {money_fmt(overtime_pay)}")
        else:
            # No overtime rate → all actual hours at regular rate
            base = round(hourly_rate * actual_hours, 2)
            messages.append(f"Hourly: {actual_hours}h × {money_fmt(hourly_rate)} = {money_fmt(base)}")

    elif salary_type == "monthly_hour":
        std_monthly_hours = money(record.get("standard_monthly_hours")) or 160
        ot_rate = money(record.get("overtime_hourly_rate")) or 0
        monthly_rate = money(record.get("basic_salary"))
        hourly_rate = money(record.get("hourly_rate"))
        # Monthly portion: fully earned if actual hours >= standard, else pro-rated
        ratio = min(actual_hours / max(std_monthly_hours, 1), 1.0)
        monthly_part = round(monthly_rate * ratio, 2)
        # Hourly portion: standard hours only (up to std_monthly_hours) × hourly_rate
        regular_hours = min(actual_hours, std_monthly_hours)
        hourly_part = round(hourly_rate * regular_hours, 2)
        # Overtime: hours exceeding standard × overtime_rate
        ot_hours_calc = max(0.0, actual_hours - std_monthly_hours)
        if ot_hours_calc > 0 and ot_rate > 0:
            overtime_pay = round(ot_rate * ot_hours_calc, 2)
        base = round(monthly_part + hourly_part, 2)
        messages.append(f"Monthly part: {money_fmt(monthly_rate)} × {actual_hours}/{std_monthly_hours}h = {money_fmt(monthly_part)}")
        messages.append(f"Hourly part: {regular_hours}h × {money_fmt(hourly_rate)} = {money_fmt(hourly_part)}")
        if overtime_pay > 0:
            messages.append(f"OT: {ot_hours_calc}h × {money_fmt(ot_rate)} = {money_fmt(overtime_pay)}")

    elif salary_type == "daily":
        base = money(record.get("daily_rate")) * actual_days
        messages.append(f"Daily: {actual_days}d × {money_fmt(record.get('daily_rate'))} = {money_fmt(base)}")

    else:  # monthly
        standard_days = money(record.get("standard_work_days")) or 22
        paid_leave = money(record.get("paid_leave_days"))
        sick_leave = money(record.get("sick_leave_days"))
        payable_days = actual_days + paid_leave + sick_leave
        base = money(record.get("basic_salary")) * min(payable_days / max(standard_days, 1), 1)
        messages.append(f"Monthly: {money_fmt(record.get('basic_salary'))} × ({actual_days}work + {paid_leave}paid_leave + {sick_leave}sick_leave)/{standard_days}d = {money_fmt(base)}")
        # Overtime for monthly: derived from hourly rate × 1.25
        ot_hours_calc = money(record.get("overtime_hours"))
        if ot_hours_calc > 0:
            derived_hourly = money(record.get("basic_salary")) / max(money(record.get("standard_work_hours")) or 176, 1)
            overtime_pay = round(derived_hourly * 1.25 * ot_hours_calc, 2)
            if overtime_pay > 0:
                messages.append(f"OT: {ot_hours_calc}h × {money_fmt(derived_hourly)} × 1.25 = {money_fmt(overtime_pay)}")

    gross = base + overtime_pay + money(record.get("fixed_allowance")) + money(record.get("performance_bonus")) + money(record.get("bonus")) + money(record.get("other_payment"))

    # CPF calculation
    cpf_employee = money(record.get("cpf_employee_manual"))
    cpf_employer = money(record.get("cpf_employer_manual"))
    if not bool(record.get("cpf_applicable", False)):
        cpf_employee = 0
        cpf_employer = 0
        messages.append("CPF not applicable; CPF amounts set to zero.")
    elif clean(record.get("cpf_input_mode")) == "parameter_assisted":
        cpf_param = next((p for p in parameters if "cpf" in clean(p.get("parameter_type")).lower()), None)
        values = cpf_param.get("values", {}) if cpf_param else {}
        employee_rate = money(values.get("cpf_employee_rate"))
        employer_rate = money(values.get("cpf_employer_rate"))
        if employee_rate > 1: employee_rate /= 100
        if employer_rate > 1: employer_rate /= 100
        ordinary_ceiling = money(values.get("ordinary_wage_ceiling"))
        wage_base = min(gross, ordinary_ceiling) if ordinary_ceiling > 0 else gross
        if cpf_param and employee_rate and employer_rate:
            cpf_employee = round(wage_base * employee_rate, 2)
            cpf_employer = round(wage_base * employer_rate, 2)
            messages.append(f"CPF parameter-assisted by {cpf_param.get('parameter_id')}.")
        else:
            messages.append("CPF kept manual because no validated CPF parameter rate exists.")

    deduction_total = cpf_employee + money(record.get("recurring_deductions")) + money(record.get("other_deduction")) + money(record.get("income_tax"))
    employer_cost_total = gross + cpf_employer + money(record.get("skill_development_levy")) + money(record.get("foreign_worker_levy"))

    record.update({
        "base_pay_calculated": round(base, 2),
        "gross_pay": round(gross, 2),
        "cpf_employee": round(cpf_employee, 2),
        "cpf_employer": round(cpf_employer, 2),
        "deduction_total": round(deduction_total, 2),
        "net_pay": round(gross - deduction_total, 2),
        "employer_cost_total": round(employer_cost_total, 2),
        "status": "calculated",
        "version": 2,
        "calculation_messages": messages,
        "updated_at": now_iso(),
    })
    return record

def calculate_monthly_sheet(sheet_id: str, record_ids: list[str] | None = None) -> tuple[int, int, list[dict[str, Any]]]:
    """Calculate payroll for records in a monthly sheet.
    If record_ids is provided, only those records are calculated.
    Returns (total_count, warning_count, warning_details).
    warning_details: list of dicts with employee_name, employee_number, salary_type, warnings (list of str)."""
    sheets = load_sheets()
    sheet = next((s for s in sheets if s.get("sheet_id") == sheet_id), None)
    if not sheet or sheet.get("status") != "hr_confirmed":
        return 0, 0, [{"employee_name": "System", "salary_type": "", "warnings": ["Sheet must be in hr_confirmed status."]}]
    parameters = active_parameters()
    records = load_monthly_records()
    target_ids = set(record_ids) if record_ids else None
    before = [dict(r) for r in records if r.get("sheet_id") == sheet_id]
    calculated = 0
    warning_details: list[dict[str, Any]] = []
    for record in records:
        if record.get("sheet_id") != sheet_id:
            continue
        if target_ids and record.get("record_id") not in target_ids:
            continue
        calculate_monthly_record(record, parameters)
        calculated += 1
        # ── Collect warnings from calculation messages ──
        msgs = record.get("calculation_messages", [])
        record_warnings: list[str] = []
        for m in msgs:
            if "CPF" in m or "zero" in m.lower() or "missing" in m.lower():
                record_warnings.append(m)
        # ── Additional logical checks for potential issues ──
        salary_type = clean(record.get("salary_type") or "monthly")
        actual_days = money(record.get("actual_work_days"))
        actual_hours = money(record.get("actual_work_hours"))
        gross_pay = money(record.get("gross_pay"))
        basic_salary = money(record.get("basic_salary"))
        hourly_rate = money(record.get("hourly_rate"))
        daily_rate = money(record.get("daily_rate"))
        overtime_hours = money(record.get("overtime_hours"))
        ot_rate = money(record.get("overtime_hourly_rate"))
        net_pay = money(record.get("net_pay"))
        paid_leave = money(record.get("paid_leave_days"))
        unpaid_leave = money(record.get("unpaid_leave_days"))
        sick_leave = money(record.get("sick_leave_days"))
        std_days = money(record.get("standard_work_days")) or 22

        # Check 1: Zero attendance for the primary attendance metric
        if salary_type in ("monthly", "daily") and actual_days == 0:
            record_warnings.append("出勤天数为0 / Work days is 0 — 可能导致基本工资为0")
        if salary_type == "monthly" and actual_days == 0 and paid_leave == 0 and sick_leave == 0:
            record_warnings.append("月薪人员无出勤、无带薪假、无病假 / Monthly: no work days, paid leave, or sick leave — 应发工资将为0")
        if salary_type in ("hourly", "monthly_hour") and actual_hours == 0:
            record_warnings.append("出勤小时为0 / Work hours is 0 — 可能导致基本工资为0")

        # Check 2: Zero gross pay
        if gross_pay == 0:
            record_warnings.append("应发工资(Gross)为0 / Gross pay is 0 — 请核实出勤数据和基本工资/费率")

        # Check 3: Zero basic salary / rate
        if salary_type == "monthly" and basic_salary == 0:
            record_warnings.append("月基本工资为0 / Basic salary is 0 — 请检查薪资主数据")
        if salary_type == "monthly_hour" and basic_salary == 0 and hourly_rate == 0:
            record_warnings.append("月基本工资和小时费率均为0 / Both basic salary and hourly rate are 0 — 请检查薪资主数据")
        elif salary_type in ("hourly", "monthly_hour") and hourly_rate == 0:
            record_warnings.append("小时工资率为0 / Hourly rate is 0 — 请检查薪资主数据")
        if salary_type == "daily" and daily_rate == 0:
            record_warnings.append("日工资率为0 / Daily rate is 0 — 请检查薪资主数据")

        # Check 4: Overtime hours but no overtime rate
        if overtime_hours > 0 and ot_rate == 0 and salary_type in ("hourly", "monthly_hour"):
            record_warnings.append(f"有加班小时({overtime_hours}h)但加班费率未设置 / OT hours present but no OT rate")

        # Check 5: Negative net pay
        if net_pay < 0:
            record_warnings.append(f"实发工资(Net)为负数({money_fmt(net_pay)}) / Net pay is negative — 扣除项超过应发工资")

        # Check 6: Payable days exceed standard days (data anomaly)
        if salary_type == "monthly":
            payable_days = actual_days + paid_leave + sick_leave
            if payable_days > std_days:
                record_warnings.append(f"计算天数({payable_days})超过满勤天数({std_days}) / Payable days exceed standard days — 可能数据有误")

        # Check 7: Leave consistency - unpaid leave present but work days = standard
        if unpaid_leave > 0 and actual_days >= std_days - 1:
            record_warnings.append(f"有无薪假({unpaid_leave}d)但出勤天数接近满勤({actual_days}/{std_days}) / Unpaid leave present but work days near standard — 可能存在数据不一致")

        # Check 8: Sick leave without paid leave or work days (possible data issue)
        if sick_leave > 0 and salary_type in ("hourly", "daily"):
            record_warnings.append(f"病假({sick_leave}d)对{ salary_type }类型仅供参考，不参与计算 / Sick leave is reference-only for {salary_type} type")

        if record_warnings:
            warning_details.append({
                "record_id": record.get("record_id"),
                "employee_name": record.get("employee_name", ""),
                "employee_number": record.get("employee_number", ""),
                "salary_type": salary_type,
                "warnings": record_warnings,
            })
    save_monthly_records(records)
    # Update sheet — only transition to calculated if ALL records are done
    sheet_recs = [r for r in records if r.get("sheet_id") == sheet_id]
    all_calculated = all(r.get("status") == "calculated" for r in sheet_recs)
    for s in sheets:
        if s.get("sheet_id") == sheet_id:
            if all_calculated:
                s["status"] = "calculated"
            s["calculated_at"] = now_iso()
            s["calculated_by"] = USER_ACTOR
            s["version"] = 2
            s["employee_count"] = len(sheet_recs)
            s["gross_total"] = round(sum(money(r.get("gross_pay")) for r in sheet_recs), 2)
            s["deduction_total"] = round(sum(money(r.get("deduction_total")) for r in sheet_recs), 2)
            s["net_total"] = round(sum(money(r.get("net_pay")) for r in sheet_recs), 2)
            s["employer_cost_total"] = round(sum(money(r.get("employer_cost_total")) for r in sheet_recs), 2)
            s["currency_totals"] = compute_currency_totals(sheet_recs)
            s["updated_at"] = now_iso()
            # Store calculation summary for detail page feedback
            s["last_calculation_summary"] = {
                "total": calculated,
                "warnings_count": len(warning_details),
                "warning_details": warning_details,
                "timestamp": now_iso(),
            }
    save_sheets(sheets)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "calculate_sheet", before, [dict(r) for r in sheet_recs])
    return calculated, len(warning_details), warning_details

def hr_approve_sheet(sheet_id: str) -> bool:
    """HR approves calculated sheet → hr_reviewed."""
    return _transition_sheet(sheet_id, "calculated", "hr_reviewed", "hr_approve")

def send_manager_review(sheet_id: str) -> bool:
    """Send sheet to manager review."""
    return _transition_sheet(sheet_id, "hr_reviewed", "manager_review", "send_manager_review")

def manager_approve_sheet(sheet_id: str, comment: str = "") -> bool:
    """Manager approves and finalizes sheet — merged step: 批准定案.

    Transitions sheet directly from manager_review to finalized,
    and executes the bridge to legacy batch + release batch.
    """
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "manager_review":
                return False
            before = dict(sheet)
            # ── 1. Advance sheet status to finalized (批准定案) ──
            sheet["status"] = "finalized"
            sheet["updated_at"] = now_iso()
            sheet["manager_approved_at"] = now_iso()
            sheet["manager_approved_by"] = USER_ACTOR
            save_sheets(sheets)
            # ── 2. Update records with manager approval ──
            records = load_monthly_records()
            for r in records:
                if r.get("sheet_id") == sheet_id:
                    r["manager_review_status"] = "approved"
                    r["manager_review_comment"] = comment
                    r["updated_at"] = now_iso()
            save_monthly_records(records)
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "manager_approve_finalize", before, dict(sheet))
            # ── 3. Bridge to legacy batch system ──
            batch_id = f"PAYSG-{sheet['payroll_month'].replace('-', '')}-{slug(sheet['entity_id'])}"
            batches = load_batches()
            existing_batch = next((b for b in batches if b.get("batch_id") == batch_id), None)
            sheet_recs = sheet_records(sheet_id)
            if not existing_batch:
                batch = {
                    "batch_id": batch_id,
                    "country_code": sheet["country_code"],
                    "entity_id": sheet["entity_id"],
                    "payroll_month": sheet["payroll_month"],
                    "status": "finalized",
                    "version": 1,
                    "employee_count": len(sheet_recs),
                    "gross_total": sheet.get("gross_total", 0),
                    "deduction_total": sheet.get("deduction_total", 0),
                    "net_total": sheet.get("net_total", 0),
                    "employer_cost_total": sheet.get("employer_cost_total", 0),
                    "currency_totals": sheet.get("currency_totals", {}),
                    "created_at": now_iso(),
                    "updated_at": now_iso(),
                    "created_by": USER_ACTOR,
                    "notes": f"Bridged from monthly sheet {sheet_id}",
                }
                batches.append(batch)
                # Create legacy records for payslip/email/payment flow
                legacy_records = load_records()
                for sr in sheet_recs:
                    _, days = monthrange(int(sheet["payroll_month"][:4]), int(sheet["payroll_month"][5:7]))
                    legacy_records.append({
                        "record_id": f"{batch_id}-{slug(sr['employee_id'])}",
                        "batch_id": batch_id,
                        "payroll_month": sheet["payroll_month"],
                        "country_code": sheet["country_code"],
                        "entity_id": sr["entity_id"],
                        "employee_id": sr["employee_id"],
                        "employee_number": sr["employee_number"],
                        "employee_name": sr["employee_name"],
                        "email": sr["email"],
                        "salary_type": sr["salary_type"],
                        "basic_salary": sr["basic_salary"],
                        "hourly_rate": sr["hourly_rate"],
                        "daily_rate": sr["daily_rate"],
                        "standard_work_days": sr["standard_work_days"],
                        "standard_work_hours": sr["standard_work_hours"],
                        "work_days": sr["actual_work_days"],
                        "work_hours": sr["actual_work_hours"],
                        "fixed_allowance": sr["fixed_allowance"],
                        "performance_bonus": sr["performance_bonus"],
                        "bonus": sr["bonus"],
                        "other_payment": sr["other_payment"],
                        "recurring_deductions": sr["recurring_deductions"],
                        "other_deduction": sr["other_deduction"],
                        "income_tax": sr["income_tax"],
                        "cpf_applicable": sr["cpf_applicable"],
                        "cpf_input_mode": sr["cpf_input_mode"],
                        "cpf_employee": sr["cpf_employee"],
                        "cpf_employer": sr["cpf_employer"],
                        "skill_development_levy": sr["skill_development_levy"],
                        "foreign_worker_levy": sr["foreign_worker_levy"],
                        "gross_pay": sr["gross_pay"],
                        "deduction_total": sr["deduction_total"],
                        "net_pay": sr["net_pay"],
                        "employer_cost_total": sr["employer_cost_total"],
                        "base_pay_calculated": sr["base_pay_calculated"],
                        "status": "calculated",
                        "calculation_messages": sr.get("calculation_messages", []),
                        "employee_confirmation_status": "pending",
                        "employee_comment": "",
                        "bank_name": sr["bank_name"],
                        "bank_branch_name": sr.get("bank_branch_name", ""),
                        "bank_swift_code": sr.get("bank_swift_code", ""),
                        "bank_account_type": sr.get("bank_account_type", "ordinary"),
                        "bank_account_name": sr["bank_account_name"],
                        "bank_account_number": sr["bank_account_number"],
                        "payroll_currency": sr.get("payroll_currency", "SGD"),
                        "created_at": now_iso(),
                        "updated_at": now_iso(),
                    })
                save_records(legacy_records)
            save_batches(batches)
            # ── 4. Auto-create release batch ──
            create_release_batch(sheet_id)
            return True
    return False

def manager_reject_sheet(sheet_id: str, comment: str = "") -> bool:
    """Manager rejects sheet back to HR."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != "manager_review":
                return False
            before = dict(sheet)
            sheet["status"] = "hr_reviewed"
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            records = load_monthly_records()
            for r in records:
                if r.get("sheet_id") == sheet_id:
                    r["manager_review_status"] = "rejected"
                    r["manager_review_comment"] = comment
                    r["updated_at"] = now_iso()
            save_monthly_records(records)
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "manager_reject", before, dict(sheet))
            return True
    return False

def create_release_batch(sheet_id: str) -> str | None:
    """Create a payroll release batch from a finalized monthly salary sheet.

    Returns the release_id on success, None on failure.
    """
    sheet = find_sheet(sheet_id)
    if not sheet or sheet.get("status") != "finalized":
        return None

    release_id = next_release_id(sheet["payroll_month"], sheet["entity_id"], sheet.get("country_code", "SG"))
    release_batches = load_release_batches()
    existing = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
    if existing:
        return release_id  # Already exists

    sheet_recs = sheet_records(sheet_id)

    # Build per-currency totals
    currency_totals: dict[str, dict[str, float]] = {}
    for sr in sheet_recs:
        cur = sr.get("payroll_currency", "SGD")
        if cur not in currency_totals:
            currency_totals[cur] = {"gross": 0, "deduction": 0, "net": 0, "employer_cost": 0, "count": 0}
        currency_totals[cur]["gross"] += money(sr.get("gross_pay"))
        currency_totals[cur]["deduction"] += money(sr.get("deduction_total"))
        currency_totals[cur]["net"] += money(sr.get("net_pay"))
        currency_totals[cur]["employer_cost"] += money(sr.get("employer_cost_total"))
        currency_totals[cur]["count"] += 1

    release_batch = {
        "release_id": release_id,
        "source_sheet_id": sheet_id,
        "country_code": sheet.get("country_code", "SG"),
        "entity_id": sheet["entity_id"],
        "payroll_month": sheet["payroll_month"],
        "status": "pending_release",
        "employee_count": len(sheet_recs),
        "payslip_count": 0,
        "email_sent_count": 0,
        "email_failed_count": 0,
        "gross_total": sheet.get("gross_total", 0),
        "deduction_total": sheet.get("deduction_total", 0),
        "net_total": sheet.get("net_total", 0),
        "employer_cost_total": sheet.get("employer_cost_total", 0),
        "currency_totals": currency_totals,
        "created_at": now_iso(),
        "created_by": USER_ACTOR,
        "updated_at": now_iso(),
        "notes": "",
    }
    release_batches.append(release_batch)
    save_release_batches(release_batches)

    # Create payslip stubs for each employee
    payslips = load_json(PAYSLIPS_PATH, [])
    existing_ps = {p.get("record_id"): p for p in payslips}
    for sr in sheet_recs:
        ps_id = f"PS-{release_id}-{slug(sr['employee_id'])}"
        if ps_id not in existing_ps:
            payslips.append({
                "payslip_id": ps_id,
                "release_id": release_id,
                "sheet_id": sheet_id,
                "record_id": sr["record_id"],
                "employee_id": sr["employee_id"],
                "employee_number": sr["employee_number"],
                "employee_name": sr["employee_name"],
                "employee_email": sr.get("email", ""),
                "department_label": sr.get("department_label", ""),
                "team_label": sr.get("team_label", ""),
                "payroll_month": sheet["payroll_month"],
                "currency": sr.get("payroll_currency", "SGD"),
                "gross_pay": sr.get("gross_pay", 0),
                "net_pay": sr.get("net_pay", 0),
                "deduction_total": sr.get("deduction_total", 0),
                "status": "pending",
                "hr_confirmed": False,
                "email_draft_status": "not_prepared",
                "email_draft_prepared_at": "",
                "email_draft_prepared_by": "",
                "file_name": "",
                "file_path": "",
                "created_at": now_iso(),
                "updated_at": now_iso(),
            })
    save_json(PAYSLIPS_PATH, list(existing_ps.values()) + [p for p in payslips if p.get("payslip_id") not in existing_ps])

    append_audit("tacaipaysg.release", release_id, "release_batch_created",
                  None, {"release_id": release_id, "source_sheet_id": sheet_id, "employee_count": len(sheet_recs)})

    return release_id


def finalize_sheet(sheet_id: str) -> bool:
    """[DEPRECATED] Finalize is now merged into manager_approve_sheet (批准定案).

    Kept for backward compatibility — redirects to manager_approve_sheet
    if the sheet is still in manager_review status.
    """
    sheet = find_sheet(sheet_id)
    if not sheet:
        return False
    cur_status = sheet.get("status", "")
    # If still at manager_review (not yet finalized by the new flow), try manager_approve
    if cur_status == "manager_review":
        return manager_approve_sheet(sheet_id)
    # If already finalized, just ensure release batch exists
    if cur_status == "finalized":
        create_release_batch(sheet_id)
        return True
    return False

def _transition_sheet(sheet_id: str, from_status: str, to_status: str, action: str) -> bool:
    """Generic sheet status transition."""
    sheets = load_sheets()
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") != from_status:
                return False
            before = dict(sheet)
            sheet["status"] = to_status
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            append_audit("tacaipaysg.monthly_sheet", sheet_id, action, before, dict(sheet))
            return True
    return False


def void_sheet(sheet_id: str) -> tuple[bool, int]:
    """Void a monthly salary sheet and all its records.
    Only allowed for sheets in draft, hr_confirmed, or correction status.
    Sheets in calculated/hr_reviewed/manager_review/finalized must be
    returned to draft first (or use correction status).
    Returns (success, voided_record_count)."""
    sheets = load_sheets()
    records = load_monthly_records()
    sheet_found = False
    voidable_statuses = {"draft", "hr_confirmed", "correction"}
    for sheet in sheets:
        if sheet.get("sheet_id") == sheet_id:
            if sheet.get("status") not in voidable_statuses:
                return False, 0
            before = dict(sheet)
            sheet["status"] = "voided"
            sheet["updated_at"] = now_iso()
            save_sheets(sheets)
            append_audit("tacaipaysg.monthly_sheet", sheet_id, "void_sheet", before, dict(sheet))
            sheet_found = True
            break
    if not sheet_found:
        return False, 0
    # Void all associated records
    count = 0
    for record in records:
        if record.get("sheet_id") == sheet_id:
            record["status"] = "voided"
            record["updated_at"] = now_iso()
            count += 1
    save_monthly_records(records)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "void_sheet_records", None, {"voided_count": count})
    return True, count


def delete_sheet(sheet_id: str) -> bool:
    """Physically delete a monthly salary sheet and all its records.
    Only allowed for sheets in 'voided' status — active sheets must be voided first.
    This is a hard delete that removes data from JSON storage permanently."""
    sheets = load_sheets()
    records = load_monthly_records()
    sheet = next((s for s in sheets if s.get("sheet_id") == sheet_id), None)
    if not sheet:
        return False
    # Only allow deletion of voided sheets for safety
    if sheet.get("status") != "voided":
        return False
    # Remove sheet
    sheets = [s for s in sheets if s.get("sheet_id") != sheet_id]
    save_sheets(sheets)
    # Remove all associated records
    deleted_count = 0
    remaining_records = []
    for record in records:
        if record.get("sheet_id") == sheet_id:
            deleted_count += 1
        else:
            remaining_records.append(record)
    save_monthly_records(remaining_records)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "delete_sheet", dict(sheet), {"deleted_record_count": deleted_count})
    return True


# ── Timesheet Integration ────────────────────────────────────────

TIMESHEET_INTERNAL_BASE_URL = (os.environ.get("TIMESHEET_INTERNAL_BASE_URL", f"http://{TACAI_INTERNAL_HOST}:8002").strip() or f"http://{TACAI_INTERNAL_HOST}:8002").rstrip("/")

def fetch_timesheet_attendance(session_id: str, month: str, entity_id: str, country_code: str = "SG") -> tuple[dict[str, dict[str, Any]], str]:
    """Fetch monthly attendance summary from TAC-timesheet."""
    url = f"{TIMESHEET_INTERNAL_BASE_URL}/api/payroll/attendance-summary"
    params = {"country_code": country_code, "month": month, "entity_id": entity_id}
    headers = {"Accept": "application/json"}
    if session_id:
        headers["Cookie"] = f"{USER_ADMIN_SESSION_COOKIE}={session_id}"
    try:
        req = Request(f"{url}?{urlencode(params)}", headers=headers)
        with urlopen(req, timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (URLError, TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {}, f"Timesheet not available: {exc}"
    if not payload.get("ok"):
        return {}, payload.get("error", "Unknown timesheet error")
    employees = payload.get("employees", [])
    result = {}
    for emp in employees:
        eid = clean(emp.get("employee_id"))
        if eid:
            result[eid] = {
                "actual_work_days": money(emp.get("total_work_days")),
                "actual_work_hours": money(emp.get("total_work_hours")),
                "overtime_hours": money(emp.get("total_overtime_hours")),
                "late_night_hours": money(emp.get("total_late_night_hours")),
                "holiday_hours": money(emp.get("total_holiday_hours")),
                "paid_leave_days": money(emp.get("total_paid_leave_days")),
                "unpaid_leave_days": money(emp.get("total_unpaid_leave_days")),
                "absence_days": money(emp.get("absence_days")),
            }
    return result, ""

def import_attendance_from_timesheet(sheet_id: str, session_id: str) -> tuple[int, str]:
    """Import attendance data from TAC-timesheet into a monthly sheet."""
    sheet = find_sheet(sheet_id)
    if not sheet:
        return 0, "Sheet not found"
    attendance_map, error = fetch_timesheet_attendance(session_id, sheet["payroll_month"], sheet["entity_id"], sheet["country_code"])
    if error:
        return 0, error
    if not attendance_map:
        return 0, "No attendance data returned from timesheet"
    records = load_monthly_records()
    count = 0
    for record in records:
        if record.get("sheet_id") != sheet_id:
            continue
        eid = record.get("employee_id")
        if eid in attendance_map:
            att = attendance_map[eid]
            for key in ["actual_work_days", "actual_work_hours", "overtime_hours", "late_night_hours", "holiday_hours", "paid_leave_days", "unpaid_leave_days", "absence_days"]:
                record[key] = att.get(key, record.get(key, 0))
            record["attendance_source"] = "timesheet"
            record["updated_at"] = now_iso()
            count += 1
    save_monthly_records(records)
    # Update sheet attendance_source
    sheets = load_sheets()
    for s in sheets:
        if s.get("sheet_id") == sheet_id:
            s["attendance_source"] = "timesheet"
            s["updated_at"] = now_iso()
    save_sheets(sheets)
    append_audit("tacaipaysg.monthly_sheet", sheet_id, "import_attendance", None, {"count": count, "source": "timesheet"})
    return count, ""

# ── Payroll Calendar Functions ────────────────────────────────────

def compute_calendar_months(year: int, holidays: list[dict[str, str]]) -> dict[str, dict[str, int]]:
    """Auto-compute monthly standard work days from holidays for a given year."""
    from calendar import monthrange as mr, SATURDAY, SUNDAY
    from datetime import date as dt_date
    holiday_dates = set()
    for h in holidays:
        d = clean(h.get("date", ""))
        if d:
            holiday_dates.add(d)
    months = {}
    for m in range(1, 13):
        total_days, first_weekday = mr(year, m)
        weekend_count = 0
        holiday_count = 0
        for day in range(1, total_days + 1):
            d = dt_date(year, m, day)
            if d.weekday() in (SATURDAY, SUNDAY):
                weekend_count += 1
            elif d.isoformat() in holiday_dates:
                holiday_count += 1
        work_days = total_days - weekend_count - holiday_count
        months[f"{m:02d}"] = {
            "calendar_days": total_days,
            "weekend_days": weekend_count,
            "public_holidays": holiday_count,
            "standard_work_days": work_days,
        }
    return months

def money_fmt(value: Any) -> str:
    return f"{money(value):,.2f}"


def compute_currency_totals(records: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Group payroll records by currency and compute per-currency totals."""
    totals: dict[str, dict[str, Any]] = {}
    for r in records:
        cur = r.get("payroll_currency") or "SGD"
        if cur not in totals:
            totals[cur] = {"gross": 0.0, "deduction": 0.0, "net": 0.0, "employer_cost": 0.0, "count": 0}
        totals[cur]["gross"] += money(r.get("gross_pay"))
        totals[cur]["deduction"] += money(r.get("deduction_total"))
        totals[cur]["net"] += money(r.get("net_pay"))
        totals[cur]["employer_cost"] += money(r.get("employer_cost_total"))
        totals[cur]["count"] += 1
    for cur in totals:
        for k in ("gross", "deduction", "net", "employer_cost"):
            totals[cur][k] = round(totals[cur][k], 2)
    return totals


def page(lang: str, title: str, body: str, user: dict[str, Any] | None = None, current_path: str = "/", current_query: dict[str, list[str]] | None = None, portal_url: str | None = None) -> bytes:
    current_query = current_query or {}
    nav_links = [
        ("/", "nav.dashboard"),
        ("/salary-master", "nav.master"),
        ("/monthly-sheets", "nav.monthly_sheets"),
        ("/batches", "nav.batches"),
        ("/ledger", "nav.ledger"),
        ("/calendars", "nav.calendars"),
        ("/reports", "nav.reports"),
        ("/parameters", "nav.parameters"),
        ("/audit", "nav.audit"),
    ]
    nav = "".join(
        f'<a class="{escape("active" if (path == current_path or (path != "/" and current_path.startswith(path))) else "")}" href="{with_lang(path, lang)}">{escape(t(lang, key))}</a>'
        for path, key in nav_links
    )
    langs = " ".join(
        f'<a class="pill {escape("active" if code == lang else "")}" href="{escape(query_link(current_path, current_query, lang=code))}">{code.upper()}</a>'
        for code in ["zh", "ja", "en"]
    )
    user_chip = ""
    if user:
        user_chip = f"<span class='current-user-chip'><strong>{escape(user_display_name(user))}</strong><small>User_admin</small></span>"
    notice = clean((current_query.get("notice") or [""])[0])
    notice_type = clean((current_query.get("notice_type") or ["success"])[0])
    notice_class = "message-warning" if notice_type in {"warning", "warn", "error"} else "message-success"
    notice_html = f'<section class="message-strip {notice_class}" role="status">{escape(notice)}</section>' if notice else ""
    portal_html = f'<a class="portal-link" href="{escape(portal_url or PORTAL_BASE_URL)}"><span class="portal-icon">⌂</span> Back to Portal</a>'
    html = f"""<!doctype html>
<html lang="{escape(lang)}">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{escape(title)}</title>
<style>
:root{{--navy:#14213d;--blue:#0a6ed1;--bg:#f6f8fb;--card:#fff;--line:#d8dee9;--text:#17202a;--muted:#65758b;--green:#0f766e;--amber:#b45309;--red:#b91c1c;}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','Noto Sans SC','Noto Sans JP',Arial,sans-serif;font-size:14px}} a{{color:var(--blue);text-decoration:none}}
.site-header{{background:var(--navy);color:white;padding:20px 32px}} .brand{{font-size:20px;font-weight:850;margin-bottom:4px}} .subtitle{{color:#dbeafe;margin:0}}
.primary-nav{{display:flex;align-items:center;gap:8px;flex-wrap:wrap;padding:10px 32px;background:white;border-bottom:1px solid var(--line);box-shadow:0 1px 2px rgba(15,23,42,.04)}}
.primary-nav a{{display:inline-flex;align-items:center;justify-content:center;min-height:34px;color:#223548;background:#f7f9fb;border:1px solid transparent;padding:0 13px;border-radius:8px;font-size:.92rem;font-weight:760;white-space:nowrap}}
.primary-nav a:hover{{background:#eef6ff;border-color:#91c8f6;color:var(--blue)}} .primary-nav a.active{{background:#e5f2fd;border-color:var(--blue);color:var(--blue);box-shadow:inset 0 -2px 0 var(--blue)}}
.primary-nav a.portal-link{{gap:.35rem;color:#0b4f8a;background:linear-gradient(180deg,#f8fbff 0%,#eaf4ff 100%);border-color:#9cc7f2}} .portal-icon{{font-size:1rem}}
.nav-spacer{{flex:1}} .language-switcher{{display:flex;align-items:center;gap:6px;flex-wrap:wrap}} .pill{{display:inline-flex;align-items:center;justify-content:center;min-height:30px;padding:0 10px;border-radius:8px;background:#eef2f7;color:#223548;border:1px solid #d6e0eb;font-size:.8rem;font-weight:800}} .pill.active{{background:#e5f2fd;border-color:var(--blue);color:var(--blue)}}
.current-user-chip{{display:grid;gap:2px;min-width:160px;padding:7px 10px;background:#fff;border:1px solid #d6e4f2;border-radius:12px;color:var(--navy);box-shadow:0 1px 2px rgba(15,23,42,.04)}} .current-user-chip strong{{font-size:.9rem}} .current-user-chip small{{color:var(--muted);font-size:.76rem}}
main{{max-width:1280px;margin:0 auto;padding:28px 20px 48px}} .grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}} .form-grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:14px}}
.card,.panel,.object-page{{background:var(--card);border:1px solid var(--line);border-radius:14px;box-shadow:0 1px 2px rgba(15,23,42,.04);padding:18px;margin-bottom:16px}} .sap-page-header,.object-header{{background:linear-gradient(135deg,#ffffff 0%,#eef4ff 100%);border:1px solid var(--line);border-radius:16px;padding:20px;margin-bottom:18px}} .sap-page-header h1,.object-header h1{{margin:0 0 8px;color:var(--navy)}} .muted{{color:var(--muted)}} .sap-info-strip{{display:flex;gap:24px;flex-wrap:wrap;font-size:14px;color:var(--navy);margin-top:6px}} .sap-info-strip span{{display:inline-flex;align-items:center;gap:4px}}
.metric-card{{background:#fff;border:1px solid var(--line);border-radius:12px;padding:16px}} .metric-card .value{{font-size:28px;font-weight:850;margin-top:8px;color:var(--navy)}} a.metric-card{{display:block;color:inherit;text-decoration:none;transition:box-shadow .15s,transform .15s,border-color .15s;cursor:pointer}} a.metric-card:hover{{box-shadow:0 4px 12px rgba(10,110,209,.14);border-color:var(--blue);transform:translateY(-1px)}} a.metric-card:hover .value{{color:var(--blue)}} .sap-toolbar{{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}} .sap-toolbar.end{{justify-content:flex-end}}
button,.button,input[type=submit]{{display:inline-flex;align-items:center;justify-content:center;border:1px solid #085caf;background:var(--blue);color:white;border-radius:8px;padding:9px 13px;cursor:pointer;font-weight:760;font:inherit}} .button.secondary,button.secondary{{background:#fff;color:var(--blue)}} .button.danger,button.danger{{background:var(--red);border-color:#900}}
.table-scroll{{overflow:auto;background:#fff;border:1px solid var(--line);border-radius:12px}} table{{width:100%;border-collapse:collapse;min-width:900px}} th,td{{padding:10px 12px;border-bottom:1px solid #edf0f4;text-align:left;vertical-align:top}} th{{background:#f2f6fa;color:#31465d;font-size:12px;text-transform:uppercase;letter-spacing:.02em}} .right{{text-align:right;font-variant-numeric:tabular-nums}}
.badge{{display:inline-block;border-radius:14px;padding:3px 8px;background:#edf5ff;color:#0a4f93;font-size:12px;font-weight:800}} .badge.paid,.badge.approved,.badge.active{{background:#e4f7e7;color:#107e3e}} .badge.draft{{background:#fdf4d9;color:#8a5a00}} .badge.voided,.badge.failed,.badge.inactive{{background:#ffeaf0;color:#b00}}
.progress-bar{{display:flex;align-items:center;gap:4px;padding:16px 0;flex-wrap:wrap}} .progress-step{{display:flex;align-items:center;gap:8px}} .progress-circle{{width:28px;height:28px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:13px;font-weight:800;flex-shrink:0}} .progress-circle.done{{background:var(--green);color:white}} .progress-circle.current{{background:var(--blue);color:white;box-shadow:0 0 0 4px rgba(10,110,209,.25)}} .progress-circle.pending{{background:#e2e8f0;color:#94a3b8}} .progress-line{{width:24px;height:2px;background:var(--line);flex-shrink:0}} .progress-line.done{{background:var(--green)}} .progress-label{{font-size:.78rem;font-weight:760;white-space:nowrap}} .progress-label.done{{color:var(--green)}} .progress-label.current{{color:var(--blue)}} .progress-label.pending{{color:#94a3b8}}
.search-bar{{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;padding:12px 16px;background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);border:1px solid var(--line);border-radius:12px;margin-bottom:12px}}
.search-bar .field{{margin:0;flex:1;min-width:140px}}
.search-bar input,.search-bar select{{font-size:13px}}
.batch-panel{{display:flex;gap:10px;flex-wrap:wrap;align-items:flex-end;padding:12px 16px;background:#fffbeb;border:1px solid #fcd34d;border-radius:12px;margin-bottom:12px}}
.batch-panel .field{{margin:0}}
.batch-panel input{{font-size:13px;width:80px;text-align:right}}
.batch-panel .btn-group{{display:flex;gap:4px;flex-wrap:wrap}}
.batch-panel .btn-sm{{font-size:11px;padding:4px 8px;min-height:auto;border-radius:6px}}
.detail-link{{display:inline-flex;align-items:center;gap:2px;font-size:11px;padding:2px 8px;border-radius:4px;background:#eef2ff;color:var(--blue);border:1px solid #c7d2fe;text-decoration:none;white-space:nowrap}}
.detail-link:hover{{background:#dbeafe;border-color:var(--blue)}}
label{{display:block;font-weight:800;margin-bottom:5px;color:#334155}} input,select,textarea{{width:100%;border:1px solid var(--line);border-radius:8px;padding:9px 10px;background:#fff;font:inherit}} textarea{{min-height:88px;resize:vertical}} input:focus,select:focus,textarea:focus{{outline:3px solid rgba(10,110,209,.18);border-color:var(--blue)}} .field{{margin-bottom:10px}}
.message-strip{{background:#eff6ff;border-left:4px solid var(--blue);padding:12px 14px;border-radius:8px;margin:10px 0 16px}} .message-warning,.warn{{background:#fffbeb;border-left-color:var(--amber)}} .message-success{{background:#ecfdf5;border-left-color:var(--green)}} .section-header{{padding:.78rem 1rem;border-bottom:1px solid var(--line);background:linear-gradient(180deg,#f8fafc 0%,#f1f5f9 100%);margin:-18px -18px 16px;border-radius:14px 14px 0 0}} .section-header h2,.section-header h3{{margin:0;color:var(--navy)}}
.employee-picker{{border:1px solid #d6e4f2;background:#f8fbff;border-radius:14px;padding:16px;margin-bottom:16px}} .helper-text{{font-size:.85rem;color:var(--muted);margin-top:4px}}
@media(max-width:760px){{.site-header{{padding:16px 18px}}.primary-nav{{flex-wrap:nowrap;overflow-x:auto;padding:8px 12px}}.primary-nav a{{flex:0 0 auto}}.nav-spacer{{display:none}}.language-switcher{{flex:0 0 auto}}main{{padding:18px 12px 36px}}.grid,.form-grid{{grid-template-columns:1fr}}.sap-toolbar{{align-items:stretch;flex-direction:column}}.sap-toolbar .button,.sap-toolbar button{{width:100%;text-align:center}}table{{min-width:760px}}}}
/* ── Confirm Modal ── */
.modal-overlay{{display:none;position:fixed;z-index:9999;left:0;top:0;width:100%;height:100%;background:rgba(15,23,42,.55);align-items:center;justify-content:center}}
.modal-overlay.active{{display:flex}}
.modal-dialog{{background:#fff;border-radius:16px;box-shadow:0 20px 60px rgba(15,23,42,.25);max-width:460px;width:92%;padding:0;overflow:hidden;animation:modalIn .18s ease-out}}
@keyframes modalIn{{from{{opacity:0;transform:translateY(-18px) scale(.96)}}to{{opacity:1;transform:translateY(0) scale(1)}}}}
.modal-body{{padding:28px 24px 20px;text-align:center}}
.modal-body .modal-icon{{font-size:40px;margin-bottom:10px}}
.modal-body p{{margin:8px 0 0;color:var(--text);font-size:15px;line-height:1.55}}
.modal-body .modal-count{{font-weight:850;color:var(--blue);font-size:18px}}
.modal-footer{{display:flex;gap:10px;padding:0 24px 24px;justify-content:center}}
.modal-footer button{{min-width:110px;padding:11px 20px;font-size:15px;border-radius:10px;font-weight:760;cursor:pointer;transition:all .12s}}
.modal-footer .btn-no{{background:#fff;color:var(--text);border:2px solid var(--line)}}
.modal-footer .btn-no:hover{{border-color:var(--muted);background:#f8fafc}}
.modal-footer .btn-no.default-no{{border-color:var(--blue);box-shadow:0 0 0 4px rgba(10,110,209,.18);color:var(--blue)}}
.modal-footer .btn-yes{{background:var(--blue);color:#fff;border:2px solid #085caf}}
.modal-footer .btn-yes:hover{{background:#085caf}}
.modal-footer .btn-yes.default-yes{{box-shadow:0 0 0 4px rgba(10,110,209,.18);border-color:#085caf;outline:none}}
.modal-footer .btn-no.default-no{{border-color:var(--blue);box-shadow:0 0 0 4px rgba(10,110,209,.18);color:var(--blue)}}
.sticky-col{{position:sticky;z-index:2;box-shadow:2px 0 4px rgba(0,0,0,.06)}}
.name-cell{{box-shadow:2px 0 6px rgba(0,0,0,.12)!important}}
.missing-data td{{border-bottom-color:#F9A825!important}}
.missing-data .sticky-col{{background:#FFF9C4!important}}
</style>
</head><body><header class="site-header"><div class="brand">TACAI Pay SG</div><p class="subtitle">{escape(t(lang,'app.title'))}</p></header><nav class="primary-nav">{portal_html}{nav}<span class="nav-spacer"></span><span class="language-switcher">{user_chip}{langs}</span></nav><main>{notice_html}{body}</main>
<script>
function showConfirmModal(modalId){{
  var overlay = document.getElementById(modalId);
  if(overlay){{ overlay.classList.add('active');
    var noBtn = overlay.querySelector('.btn-no');
    if(noBtn) setTimeout(function(){{ noBtn.focus() }}, 100);
  }}
}}
function hideModal(modalId){{
  var overlay = document.getElementById(modalId);
  if(overlay) overlay.classList.remove('active');
}}
function submitGenForm(formId, modalId){{
  hideModal(modalId);
  document.getElementById(formId).submit();
}}
// Close modal on overlay click (outside dialog)
document.addEventListener('click', function(e){{
  if(e.target.classList.contains('modal-overlay')) e.target.classList.remove('active');
}});
// Close modal on Escape key
document.addEventListener('keydown', function(e){{
  if(e.key==='Escape'){{
    document.querySelectorAll('.modal-overlay.active').forEach(function(m){{ m.classList.remove('active') }});
  }}
}});
</script>
</body></html>"""
    return html.encode("utf-8")


def status_badge(status: str) -> str:
    return f'<span class="badge {escape(status)}">{escape(status)}</span>'


def dashboard_html(lang: str) -> str:
    masters = load_salary_master()
    batches = load_batches()
    records = load_records()
    latest = sorted(batches, key=lambda b: b.get("updated_at", ""), reverse=True)[:5]
    active_masters = sum(1 for m in masters if m.get('active'))
    body = f"""
<div class="sap-page-header"><h1>{t(lang,'app.title')}</h1><div class="sap-info-strip"><span>📋 {len(masters)} salary profiles ({active_masters} active)</span><span>📦 {len(batches)} payroll batches</span><span>💰 SGD {money_fmt(sum(money(r.get('net_pay')) for r in records))} net paid</span></div></div>
<div class="grid">
  <a class="metric-card" href="{with_lang('/salary-master', lang)}"><div>👥 {t(lang,'nav.master')}</div><div class="value">{len(masters)}</div><div class="muted">{active_masters} active · {len(masters)-active_masters} inactive</div></a>
  <a class="metric-card" href="{with_lang('/batches/new', lang)}"><div>📦 {t(lang,'nav.batches')}</div><div class="value">{len(batches)}</div><div class="muted">Create new payroll batch</div></a>
  <a class="metric-card" href="{with_lang('/monthly-sheets', lang)}"><div>📊 Monthly Sheets</div><div class="value">{len(batches)}</div><div class="muted">View & manage sheets</div></a>
  <div class="metric-card"><div>💰 Net Pay Total</div><div class="value">SGD {money_fmt(sum(money(r.get('net_pay')) for r in records))}</div><div class="muted">All processed records</div></div>
</div>
<div class="card"><h2>{t(lang,'nav.batches')}</h2><div class="sap-toolbar"><a class="button" href="{with_lang('/batches/new', lang)}">{t(lang,'action.generate')}</a></div>{batches_table(lang, latest, total=len(batches))}</div>
"""
    return body


def batches_table(lang: str, rows: list[dict[str, Any]], total: int | None = None) -> str:
    if not rows:
        return f"<p class='muted'>{t(lang,'msg.no_records')}</p>"
    trs = []
    for b in rows:
        # Compact per-currency totals for list view
        b_ct = b.get("currency_totals") or {}
        if b_ct:
            cur_parts = [f"{escape(cur)} {money_fmt(b_ct[cur].get('net'))}" for cur in sorted(b_ct.keys())]
            cur_display = " &nbsp;|&nbsp; ".join(cur_parts)
        else:
            cur_display = f"Gross {money_fmt(b.get('gross_total'))} / Net {money_fmt(b.get('net_total'))}"
        trs.append(f"<tr><td><a href='{with_lang('/batches/detail', lang, batch_id=b.get('batch_id'))}'>{escape(b.get('batch_id',''))}</a></td><td>{escape(b.get('payroll_month',''))}</td><td>{escape(entity_label(b.get('entity_id',''), lang))}</td><td>{status_badge(b.get('status',''))}</td><td class='right'>{b.get('employee_count',0)}</td><td class='right'>{cur_display}</td></tr>")
    count_html = f"<div class='helper-text' style='margin-top:8px'>{f'Showing latest {len(rows)} of {total} batches' if total is not None else f'{len(rows)} batch(es) total'}</div>"
    return f"<div class='table-scroll'><table><thead><tr><th>ID</th><th>{t(lang,'label.month')}</th><th>{t(lang,'label.entity')}</th><th>{t(lang,'label.status')}</th><th>Count</th><th>Currency Totals (Net)</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>{count_html}"


def salary_master_html(lang: str, query: dict[str, list[str]] | None = None) -> str:
    all_rows = load_salary_master()
    query = query or {}
    # Extract filter values
    filter_entity = clean((query.get("entity") or [""])[0])
    filter_department = clean((query.get("department") or [""])[0])
    filter_team = clean((query.get("team") or [""])[0])
    filter_q = clean((query.get("q") or [""])[0])
    # Apply filters (dropdowns use exact match, AND logic)
    rows = all_rows
    if filter_entity:
        rows = [r for r in rows if r.get("entity_id") == filter_entity]
    if filter_department:
        rows = [r for r in rows if r.get("department_label") == filter_department or r.get("department") == filter_department]
    if filter_team:
        rows = [r for r in rows if r.get("team_label") == filter_team]
    if filter_q:
        q_lower = filter_q.lower()
        rows = [r for r in rows if (r.get("employee_number") and q_lower in r["employee_number"].lower()) or (r.get("employee_name") and q_lower in r["employee_name"].lower())]
    has_filter = any([filter_entity, filter_department, filter_team, filter_q])
    # Build filtered CSV link
    csv_params = {}
    if filter_entity: csv_params["entity"] = filter_entity
    if filter_department: csv_params["department"] = filter_department
    if filter_team: csv_params["team"] = filter_team
    if filter_q: csv_params["q"] = filter_q
    # Build department and team dropdown options
    dept_opts = '<option value="">All Departments</option>' + "".join(f'<option value="{escape(d)}" {"selected" if filter_department==d else ""}>{escape(d)}</option>' for d in distinct_departments())
    team_opts = '<option value="">All Teams</option>' + "".join(f'<option value="{escape(t)}" {"selected" if filter_team==t else ""}>{escape(t)}</option>' for t in distinct_teams())
    # Clear filter link
    clear_link = f'<a class="button secondary" href="{with_lang("/salary-master", lang)}" style="padding:6px 12px;font-size:13px">Clear</a>' if has_filter else ""
    # Filter bar
    filter_bar = f"""
<form method="get" action="/salary-master" class="sap-toolbar" style="margin-bottom:14px;padding:12px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;flex-wrap:wrap;gap:8px;align-items:end">
  <input type="hidden" name="lang" value="{escape(lang)}">
  <div class="field" style="margin:0;flex:1;min-width:140px"><label style="font-size:11px;margin-bottom:1px">{t(lang,'label.entity')}</label><select name="entity" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()"><option value="">All</option>{entity_options_html(distinct_sg_entities(), filter_entity, lang)}</select></div>
  <div class="field" style="margin:0;flex:1;min-width:140px"><label style="font-size:11px;margin-bottom:1px">Department</label><select name="department" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()">{dept_opts}</select></div>
  <div class="field" style="margin:0;flex:1;min-width:120px"><label style="font-size:11px;margin-bottom:1px">Team</label><select name="team" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()">{team_opts}</select></div>
  <div class="field" style="margin:0;flex:2;min-width:160px"><label style="font-size:11px;margin-bottom:1px">No. / Name</label><input name="q" placeholder="Employee number or name" value="{escape(filter_q)}" style="padding:5px 7px;font-size:13px"></div>
  <button style="padding:5px 12px;font-size:13px;margin-bottom:1px">Search</button>
  {clear_link}
</form>"""
    # Summary line
    summary = f'<div class="helper-text" style="margin:-8px 0 10px">Showing {len(rows)} of {len(all_rows)} employees{escape(" (filtered)" if has_filter else "")}</div>'
    trs = []
    for r in rows:
        readiness = salary_master_readiness(r)
        org_display = " / ".join(part for part in [r.get("department_label") or r.get("department"), r.get("team_label")] if part)
        deactivate = ""
        if r.get("active"):
            deactivate = f"<form method='post' action='{with_lang('/salary-master/deactivate', lang)}' class='sap-toolbar' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.deactivate_salary_master_confirm'))})\"><input type='hidden' name='employee_id' value='{escape(r['employee_id'])}'><input name='reason' placeholder='Deactivate reason' style='min-width:160px'><button class='danger'>Deactivate</button></form>"
        trs.append(f"<tr><td><a href='{with_lang('/salary-master/edit', lang, employee_id=r['employee_id'])}'>{escape(r['employee_number'])}</a></td><td>{escape(r['employee_name'])}</td><td>{escape(entity_label(r['entity_id'], lang))}</td><td>{escape(org_display)}</td><td>{escape(r.get('salary_type',''))}</td><td class='right'>{money_fmt(r['basic_salary'])}</td><td class='right'>{money_fmt(r['hourly_rate'])}</td><td class='right'>{money_fmt(r['daily_rate'])}</td><td>{escape(r.get('employeeadmin_status',''))}</td><td>{status_badge(readiness['status'])}</td><td>{status_badge('active' if r.get('active') else 'inactive')}</td><td>{deactivate}</td></tr>")
    table = f"<p class='muted'>{t(lang,'msg.no_records')}</p>" if not rows else f"<div class='table-scroll'><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>{t(lang,'label.entity')}</th><th>Department / Team</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.basic_salary')}</th><th>{t(lang,'label.hourly_rate')}</th><th>{t(lang,'label.daily_rate')}</th><th>EmployeeAdmin</th><th>Readiness</th><th>{t(lang,'label.status')}</th><th>Action</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.master')}</h1><div class="sap-info-strip"><span>📋 {len(all_rows)} employees total</span><span>🟢 {sum(1 for r in all_rows if r.get('active'))} active</span><span>🔴 {sum(1 for r in all_rows if not r.get('active'))} inactive</span></div></div>
<div class="card"><div class="sap-toolbar"><a class="button" href="{with_lang('/salary-master/new', lang)}">{t(lang,'action.create_salary_master')}</a><a class="button secondary" href="{with_lang('/salary-master/modify', lang)}" onclick="return confirm({json.dumps(t(lang, 'msg.modify_salary_master_confirm'))})">{t(lang,'action.modify')}</a><a class="button secondary" href="{with_lang('/salary-master.csv', lang, **csv_params)}">CSV</a></div>{filter_bar}{summary}{table}</div>
"""


def salary_master_modify_html(lang: str, query: dict[str, list[str]] | None = None) -> str:
    """Employee selection page for the dedicated Modify flow — pick one salary master record to edit."""
    all_rows = load_salary_master()
    query = query or {}
    filter_entity = clean((query.get("entity") or [""])[0])
    filter_department = clean((query.get("department") or [""])[0])
    filter_team = clean((query.get("team") or [""])[0])
    # Build filter dropdowns from actual data
    entities = sorted({r.get("entity_id", "") for r in all_rows if r.get("entity_id")})
    departments = sorted({r.get("department_label") or r.get("department", "") for r in all_rows if r.get("department_label") or r.get("department")})
    teams = sorted({r.get("team_label") or "" for r in all_rows if r.get("team_label")})
    # Apply filters (dropdowns use exact match)
    rows = all_rows
    if filter_entity:
        rows = [r for r in rows if r.get("entity_id") == filter_entity]
    if filter_department:
        rows = [r for r in rows if r.get("department_label") == filter_department or r.get("department") == filter_department]
    if filter_team:
        rows = [r for r in rows if r.get("team_label") == filter_team]
    has_filter = any([filter_entity, filter_department, filter_team])
    # Entity dropdown options
    entity_opts = '<option value="">All Entities</option>' + entity_options_html(entities, filter_entity, lang)
    dept_opts = '<option value="">All Departments</option>' + "".join(f'<option value="{escape(d)}" {"selected" if filter_department==d else ""}>{escape(d)}</option>' for d in departments)
    team_opts = '<option value="">All Teams</option>' + "".join(f'<option value="{escape(t)}" {"selected" if filter_team==t else ""}>{escape(t)}</option>' for t in teams)
    # Filter bar
    filter_bar = f"""
<form method="get" action="/salary-master/modify" class="sap-toolbar" style="margin-bottom:14px;padding:12px;background:#f8fafc;border:1px solid var(--line);border-radius:10px;flex-wrap:wrap;gap:10px;align-items:end">
  <input type="hidden" name="lang" value="{escape(lang)}">
  <div class="field" style="margin:0;flex:1;min-width:160px"><label style="font-size:11px;margin-bottom:1px">{t(lang,'label.entity')}</label><select name="entity" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()">{entity_opts}</select></div>
  <div class="field" style="margin:0;flex:1;min-width:180px"><label style="font-size:11px;margin-bottom:1px">Department</label><select name="department" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()">{dept_opts}</select></div>
  <div class="field" style="margin:0;flex:1;min-width:140px"><label style="font-size:11px;margin-bottom:1px">Team</label><select name="team" style="padding:5px 7px;font-size:13px" onchange="this.form.submit()">{team_opts}</select></div>
  <noscript><button style="padding:5px 12px;font-size:13px">Filter</button></noscript>
  {f'<a class="button secondary" href="{with_lang("/salary-master/modify", lang)}" style="padding:5px 12px;font-size:13px">Clear</a>' if has_filter else ""}
</form>"""
    summary = f'<div class="helper-text" style="margin:-4px 0 10px">{len(rows)} employee(s) matching{escape(" (filtered)" if has_filter else "")} — click <b>Edit</b> to modify payroll fields</div>'
    trs = []
    for r in rows:
        readiness = salary_master_readiness(r)
        org_display = " / ".join(part for part in [r.get("department_label") or r.get("department"), r.get("team_label")] if part)
        readiness_class = "badge ready" if readiness["ready"] else "badge"
        trs.append(f"<tr><td>{escape(r['employee_number'])}</td><td>{escape(r['employee_name'])}</td><td>{escape(entity_label(r.get('entity_id',''), lang))}</td><td>{escape(org_display)}</td><td>{escape(r.get('salary_type',''))}</td><td class='right'>{money_fmt(r['basic_salary'])}</td><td class='right'>{money_fmt(r['hourly_rate'])}</td><td class='right'>{money_fmt(r['daily_rate'])}</td><td><span class='{readiness_class}'>{escape(readiness['label'])}</span></td><td><span class='badge {'active' if r.get('active') else 'inactive'}'>{'active' if r.get('active') else 'inactive'}</span></td><td><a class='button' href='{with_lang('/salary-master/edit', lang, employee_id=r['employee_id'], _from='modify')}' style='font-size:12px;padding:5px 10px'>Edit</a></td></tr>")
    table = f"<p class='muted'>{t(lang,'msg.no_records')}</p>" if not rows else f"<div class='table-scroll'><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>{t(lang,'label.entity')}</th><th>Department / Team</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.basic_salary')}</th><th>{t(lang,'label.hourly_rate')}</th><th>{t(lang,'label.daily_rate')}</th><th>Readiness</th><th>Active</th><th>Action</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.master')} — Modify</h1><div class="muted">Select an employee below to review and modify their payroll master data. Changes are saved with audit trail.</div></div>
<div class="card">
  <div class="sap-toolbar"><a class="button secondary" href="{with_lang('/salary-master', lang)}">← Back to Browse</a><a class="button" href="{with_lang('/salary-master/new', lang)}">{t(lang,'action.create_salary_master')}</a></div>
  {filter_bar}{summary}{table}
</div>
"""


BANK_ACCOUNT_TYPES = ["ordinary", "current", "savings"]
BANK_ACCOUNT_TYPE_LABELS = {
    "ordinary": {"zh": "普通账户", "en": "Ordinary Account", "ja": "普通口座"},
    "current": {"zh": "活期账户", "en": "Current Account", "ja": "当座口座"},
    "savings": {"zh": "储蓄账户", "en": "Savings Account", "ja": "貯蓄口座"},
}


def build_bank_comparison_html(lang: str, r: dict[str, Any]) -> str:
    """Build a bank info comparison section showing EmployeeAdmin reference (read-only)
    alongside editable salary master bank fields with match/diff indicators."""
    ea_bank = r.get("employeeadmin_bank_snapshot") if isinstance(r.get("employeeadmin_bank_snapshot"), dict) else {}

    # Mapping: (salary_master_field, ea_snapshot_key, label_key, is_select)
    bank_fields = [
        ("bank_name", "bank_name", "label.bank", False),
        ("bank_branch_name", "branch_name", "label.bank_branch_name", False),
        ("bank_swift_code", "swift_code", "label.bank_swift_code", False),
        ("bank_account_type", "account_type", "label.bank_account_type", True),
        ("bank_account_name", "account_holder", "label.bank_account_holder", False),
        ("bank_account_number", "account_number", "Bank Account No.", False),
    ]

    # Build EmployeeAdmin reference row (read-only)
    ea_ref_cells = []
    for sm_field, ea_key, label_key, _ in bank_fields:
        ea_val = ea_bank.get(ea_key, "") if ea_bank else ""
        label = t(lang, label_key) if label_key.startswith("label.") else label_key
        ea_ref_cells.append(f"<div class='field' style='margin:0;padding:4px 6px;background:#f8fafc;border-radius:4px'><label style='font-size:10px;color:var(--muted);margin:0'>{escape(label)} (EA)</label><div style='font-size:12px;color:var(--muted)'>{escape(str(ea_val)) if ea_val else '—'}</div></div>")

    ea_ref_row = f"""
    <div class="message-strip info" style="margin-bottom:4px"><b>{t(lang, 'label.ea_bank_reference')}</b></div>
    <div class="form-grid" style="margin-bottom:8px">{''.join(ea_ref_cells)}</div>"""

    # Build editable salary master row with match indicators
    sm_cells = []
    for sm_field, ea_key, label_key, is_select in bank_fields:
        sm_val = r.get(sm_field, "")
        ea_val = ea_bank.get(ea_key, "") if ea_bank else ""
        # Determine match status
        sm_str = str(sm_val).strip() if sm_val else ""
        ea_str = str(ea_val).strip() if ea_val else ""
        if not ea_bank:
            match_icon = ""
            match_class = ""
        elif sm_str == ea_str:
            match_icon = f" ✅<small style='color:var(--sap-green)'>{t(lang, 'label.bank_match')}</small>"
            match_class = ""
        else:
            match_icon = f" ⚠️<small style='color:var(--amber)'>{t(lang, 'label.bank_diff')}</small>"
            match_class = " style='border-color:var(--amber)'"

        label = t(lang, label_key) if label_key.startswith("label.") else label_key
        if is_select:
            # Account type dropdown
            opts = "".join(
                f"<option value='{at}' {'selected' if at == sm_str else ''}>{escape(BANK_ACCOUNT_TYPE_LABELS.get(at, {}).get(lang, at))}</option>"
                for at in BANK_ACCOUNT_TYPES
            )
            input_html = f"<select id='{sm_field}' name='{sm_field}'{match_class}>{opts}</select>"
        else:
            input_html = f"<input id='{sm_field}' name='{sm_field}' value='{escape(sm_str)}'{match_class}>"

        sm_cells.append(f"<div class='field' style='margin:0'><label style='font-size:11px;margin:0'>{escape(label)}</label>{input_html}{match_icon}</div>")

    sm_row = f"""
    <div class="message-strip" style="margin-bottom:4px"><b>Salary Master (可修改)</b> — 员工要求更改发薪银行时在此修改，不会同步回员工主记录</div>
    <div class="form-grid">{''.join(sm_cells)}</div>"""

    return f"""
<div class="card" style="padding:12px 16px;margin-bottom:12px">
{ea_ref_row}
{sm_row}
</div>"""


def salary_form_html(lang: str, row: dict[str, Any] | None = None, from_modify: bool = False) -> str:
    is_new = row is None
    r = normalize_salary_master(row or {})
    if is_new:
        r.update({"employee_id": "", "employee_number": "", "employee_name": "", "email": "", "entity_id": "SG", "department": "", "department_label": "", "source": "manual"})
    checked = "checked" if r.get("active") else ""
    cpf_checked = "checked" if r.get("cpf_applicable") else ""
    identity_readonly = "readonly" if (not is_new and r.get("source") == "employeeadmin") else ""
    readiness = salary_master_readiness(r)
    org_display = " / ".join(part for part in [r.get("department_label") or r.get("department"), r.get("team_label")] if part) or "From EmployeeAdmin after selection"
    opts = "".join(f"<option value='{s}' {'selected' if r['salary_type']==s else ''}>{s}</option>" for s in sorted(SALARY_TYPES))
    cpf_opts = "".join(f"<option value='{s}' {'selected' if r['cpf_input_mode']==s else ''}>{s}</option>" for s in sorted(CPF_MODES))
    employee_picker = ""
    if is_new:
        employee_picker = f"""
<div class="employee-picker">
  <div class="section-header"><h3>EmployeeAdmin 员工选择 / Employee selection</h3></div>
  <div class="message-strip">Recommended flow: select an active SG employee from EmployeeAdmin first, then complete payroll-specific salary/CPF/bank fields. Department and team are displayed from EmployeeAdmin as references.</div>
  <div class="form-grid">
    <div class="field"><label>{t(lang,'label.entity')}</label><select id="employee_filter_entity">{entity_options_html(distinct_sg_entities(), 'SG', lang)}</select></div>
    <div class="field"><label>Department</label><select id="employee_filter_department"><option value="">All Departments</option>{''.join(f'<option value="{escape(d)}">{escape(d)}</option>' for d in distinct_departments())}</select></div>
    <div class="field"><label>Employee No. / Name</label><input id="employee_filter_q" placeholder="员工号 / 姓名"></div>
    <div class="field"><label>&nbsp;</label><button type="button" class="secondary" onclick="loadSgEmployees()">Search</button></div>
  </div>
  <div class="field"><label>{t(lang,'label.employee')}</label><select id="employee_picker_select" onchange="applySgEmployee()"><option value="">Search employees from EmployeeAdmin</option></select><div class="helper-text" id="employee_picker_help">SG payroll only imports/selects active employees whose country_code is SG.</div></div>
</div>
"""
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.master')}{' — ' + t(lang,'action.save') if not is_new else ''}</h1><div class="muted">{f'<b>Editing: {escape(r.get("employee_name",""))} ({escape(r.get("employee_number",""))})</b> · ' if not is_new and from_modify else ''}SG payroll master keeps country_code fixed to SG. Payroll fields are maintained here; employee identity is sourced from EmployeeAdmin.</div></div>
<div class="message-strip {'warn' if not readiness['ready'] else 'message-success'}">Readiness: <b>{escape(readiness['label'])}</b>{' · Missing: ' + escape(', '.join(readiness['missing'])) if readiness['missing'] else ''}</div>
<form id="salary-master-form" class="card" method="post" action="{with_lang('/salary-master/save', lang)}" onsubmit="return confirmSaveChanges()">
{employee_picker}
{'<input type="hidden" name="_from" value="modify">' if from_modify else ''}
<input type="hidden" id="source" name="source" value="{escape(r.get('source') or 'manual')}">
<input type="hidden" id="department_id" name="department_id" value="{escape(r.get('department_id',''))}">
<input type="hidden" id="department_label" name="department_label" value="{escape(r.get('department_label',''))}">
<input type="hidden" id="team_id" name="team_id" value="{escape(r.get('team_id',''))}">
<input type="hidden" id="team_label" name="team_label" value="{escape(r.get('team_label',''))}">
<input type="hidden" id="employeeadmin_status" name="employeeadmin_status" value="{escape(r.get('employeeadmin_status',''))}">
<input type="hidden" id="employeeadmin_payroll_ready" name="employeeadmin_payroll_ready" value="{escape(str(r.get('employeeadmin_payroll_ready', False)).lower())}">
<input type="hidden" id="employeeadmin_readiness_percent" name="employeeadmin_readiness_percent" value="{money_fmt(r.get('employeeadmin_readiness_percent'))}">
<div class="section-header"><h3>Employee reference / 员工主数据引用</h3></div>
<div class="form-grid">
<div class="field"><label>Employee ID</label><input id="employee_id" name="employee_id" value="{escape(r['employee_id'])}" {identity_readonly} required></div>
<div class="field"><label>Employee No.</label><input id="employee_number" name="employee_number" value="{escape(r['employee_number'])}" {identity_readonly} required></div>
<div class="field"><label>{t(lang,'label.employee')}</label><input id="employee_name" name="employee_name" value="{escape(r['employee_name'])}" {identity_readonly} required></div>
<div class="field"><label>{t(lang,'label.email')}</label><input id="email" name="email" value="{escape(r['email'])}" {identity_readonly}></div>
<div class="field"><label>{t(lang,'label.entity')}</label>{'<input type="hidden" name="entity_id" value="' + escape(r.get('entity_id','SG')) + '"><select id="entity_id" disabled>' + entity_options_html(distinct_sg_entities(), r.get('entity_id','SG'), lang) + '</select>' if identity_readonly else '<select id="entity_id" name="entity_id">' + entity_options_html(distinct_sg_entities(), r.get('entity_id','SG'), lang) + '</select>'}</div>
<div class="field"><label>Department / Team reference</label><input id="org_reference" value="{escape(org_display)}" readonly><div class="helper-text">Department and team are referenced from EmployeeAdmin, not maintained as payroll master fields.</div></div>
</div>
<div class="section-header"><h3>Payroll fields / 薪资主数据</h3></div>
<div class="form-grid">
<div class="field"><label>{t(lang,'label.salary_type')}</label><select id="salary_type" name="salary_type">{opts}</select></div>
<div class="field"><label>{t(lang,'label.basic_salary')}</label><input id="basic_salary" name="basic_salary" value="{money_fmt(r['basic_salary'])}"></div>
<div class="field"><label>{t(lang,'label.hourly_rate')}</label><input id="hourly_rate" name="hourly_rate" value="{money_fmt(r['hourly_rate'])}"></div>
<div class="field"><label>{t(lang,'label.daily_rate')}</label><input id="daily_rate" name="daily_rate" value="{money_fmt(r['daily_rate'])}"></div>
<div class="field" id="fld_std_monthly_hrs"><label>Std Monthly Hours <small>(hourly / monthly_hour)</small></label><input name="standard_monthly_hours" value="{money_fmt(r.get('standard_monthly_hours', 160))}"></div>
<div class="field" id="fld_ot_rate"><label>Overtime Rate <small>(>std hours, hourly / monthly_hour)</small></label><input name="overtime_hourly_rate" value="{money_fmt(r.get('overtime_hourly_rate', 0))}"></div>
<div class="field"><label>Standard Work Days</label><input name="standard_work_days" value="{money_fmt(r['standard_work_days'])}"></div>
<div class="field"><label>Standard Work Hours <small>(monthly OT ref)</small></label><input name="standard_work_hours" value="{money_fmt(r['standard_work_hours'])}"></div>
<div class="field"><label>{t(lang,'label.allowance')}</label><input name="fixed_allowance" value="{money_fmt(r['fixed_allowance'])}"></div>
<div class="field"><label>{t(lang,'label.performance_bonus')}</label><input name="performance_bonus" value="{money_fmt(r['performance_bonus'])}"></div>
<div class="field"><label>Recurring Deductions</label><input name="recurring_deductions" value="{money_fmt(r['recurring_deductions'])}"></div>
<div class="field"><label>CPF Input Mode</label><select name="cpf_input_mode">{cpf_opts}</select></div>
<div class="field"><label>{t(lang,'label.cpf_employee')} Manual</label><input name="cpf_employee_manual" value="{money_fmt(r['cpf_employee_manual'])}"></div>
<div class="field"><label>{t(lang,'label.cpf_employer')} Manual</label><input name="cpf_employer_manual" value="{money_fmt(r['cpf_employer_manual'])}"></div>
<div class="field"><label>{t(lang,'label.sdl')}</label><input name="skill_development_levy" value="{money_fmt(r['skill_development_levy'])}"></div>
<div class="field"><label>{t(lang,'label.fwl')}</label><input name="foreign_worker_levy" value="{money_fmt(r['foreign_worker_levy'])}"></div>
<div class="field"><label>{t(lang,'label.payroll_currency')}</label><select id="payroll_currency" name="payroll_currency">{currency_options(r.get('payroll_currency') or 'SGD')}</select></div>
</div>
<div class="section-header"><h3>Bank Information / 银行信息</h3></div>
<input type="hidden" id="employeeadmin_bank_snapshot" name="employeeadmin_bank_snapshot" value="{escape(json.dumps(r.get('employeeadmin_bank_snapshot') if isinstance(r.get('employeeadmin_bank_snapshot'), dict) else {}, ensure_ascii=False))}">
{build_bank_comparison_html(lang, r)}
<div class="field"><label>Notes</label><textarea name="notes">{escape(r['notes'])}</textarea></div>
<label><input style="width:auto" type="checkbox" name="active" {checked}> Active</label>
<label><input style="width:auto" type="checkbox" name="cpf_applicable" {cpf_checked}> CPF Applicable</label>
<div class="sap-toolbar">{'<a class="button secondary" href="' + with_lang('/salary-master/modify', lang) + '">← Back to Selection</a>' if from_modify else ''}<button>{t(lang,'action.save')}</button><a class="button secondary" href="{with_lang('/salary-master/modify' if from_modify else '/salary-master', lang)}">{t(lang,'action.cancel')}</a></div>
</form>
<script>
var _origVals={{}};
(function(){{ var f=document.getElementById('salary-master-form'); if(!f)return; f.querySelectorAll('input[name],select[name]').forEach(function(el){{ if(el.type==='hidden'&&el.name.indexOf('bank')<0)return; _origVals[el.name]=el.type==='checkbox'?el.checked:el.value; }}); }})();
function confirmSaveChanges(){{
  var f=document.getElementById('salary-master-form'); if(!f)return true;
  var ch=[];
  f.querySelectorAll('input[name],select[name]').forEach(function(el){{
    if(el.type==='hidden'&&el.name.indexOf('bank')<0)return;
    var o=_origVals[el.name]; var c=el.type==='checkbox'?el.checked:el.value;
    if(String(o)!==String(c)) ch.push(el.name.replace(/_/g,' '));
  }});
  if(ch.length===0){{ return confirm('No changes detected. Save anyway?'); }}
  return confirm({json.dumps(t(lang, "msg.save_salary_master_confirm"))}+'\n\nChanged / 变更:\n - '+ch.join('\n - '));
}}
function updateSalaryFields(){{var st=document.getElementById('salary_type').value;var m=st==='monthly';var h=st==='hourly';var d=st==='daily';var mx=st==='monthly_hour';document.getElementById('basic_salary').parentElement.style.display=(m||mx)?'':'none';document.getElementById('hourly_rate').parentElement.style.display=(h||mx)?'':'none';document.getElementById('daily_rate').parentElement.style.display=d?'':'none';var sf=(h||mx);var fe=document.getElementById('fld_std_monthly_hrs');if(fe)fe.style.display=sf?'':'none';var fo=document.getElementById('fld_ot_rate');if(fo)fo.style.display=sf?'':'none'}}
document.getElementById('salary_type').addEventListener('change',updateSalaryFields);
updateSalaryFields();
let sgEmployees = [];
function setField(id, value) {{ const el = document.getElementById(id); if (el && value !== undefined && value !== null && value !== '') el.value = value; }}
async function loadSgEmployees() {{
  const params = new URLSearchParams({{lang: {json.dumps(lang)}, country_code: 'SG'}});
  const entity = document.getElementById('employee_filter_entity')?.value || 'SG';
  const department = document.getElementById('employee_filter_department')?.value || '';
  const q = document.getElementById('employee_filter_q')?.value || '';
  if (entity) params.set('entity_id', entity);
  if (department) params.set('department', department);
  if (q) params.set('q', q);
  const help = document.getElementById('employee_picker_help');
  const select = document.getElementById('employee_picker_select');
  if (!select) return;
  select.innerHTML = '<option value="">Loading...</option>';
  try {{
    const res = await fetch('/api/employeeadmin-employees?' + params.toString(), {{credentials: 'same-origin'}});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'EmployeeAdmin unavailable');
    sgEmployees = data.employees || [];
    select.innerHTML = '<option value="">Select EmployeeAdmin employee</option>' + sgEmployees.map((emp, idx) => {{
      const readiness = emp.payroll_readiness_status || (emp.payroll_ready ? 'ready' : 'incomplete');
      const org = [emp.entity_id, emp.department_label || emp.department, emp.team_label].filter(Boolean).join(' / ');
      return `<option value="${{idx}}">${{emp.employee_number || emp.employee_no || emp.employee_id || ''}} - ${{emp.display_name || emp.employee_name || ''}} - ${{org}} - ${{emp.status || ''}} - ${{readiness}}</option>`;
    }}).join('');
    if (help) help.textContent = `${{sgEmployees.length}} SG employees loaded from EmployeeAdmin.`;
  }} catch (err) {{
    sgEmployees = [];
    select.innerHTML = '<option value="">EmployeeAdmin unavailable</option>';
    if (help) help.textContent = err.message;
  }}
}}
function applySgEmployee() {{
  const select = document.getElementById('employee_picker_select');
  const emp = sgEmployees[Number(select?.value)];
  if (!emp) return;
  const payroll = emp.payroll || {{}};
  const bank = payroll.bank || {{}};
  setField('source', 'employeeadmin');
  setField('employee_id', emp.employee_id || emp.employee_number || emp.employee_no);
  setField('employee_number', emp.employee_number || emp.employee_no || emp.employee_id);
  setField('employee_name', emp.display_name || emp.employee_name);
  setField('email', emp.email);
  setField('entity_id', emp.entity_id || 'SG');
  setField('department_id', emp.department_id);
  setField('department_label', emp.department_label || emp.department || emp.department_id);
  setField('team_id', emp.team_id);
  setField('team_label', emp.team_label);
  setField('employeeadmin_status', emp.status || emp.employment_status || 'active');
  setField('employeeadmin_payroll_ready', emp.payroll_ready ? 'true' : 'false');
  setField('employeeadmin_readiness_percent', emp.payroll_readiness_percent || 0);
  setField('org_reference', [emp.department_label || emp.department || emp.department_id, emp.team_label].filter(Boolean).join(' / '));
  setField('salary_type', payroll.salary_type || emp.salary_type || 'monthly');
  setField('basic_salary', payroll.base_salary || payroll.basic_salary || emp.base_salary || emp.basic_salary);
  setField('hourly_rate', payroll.hourly_rate || emp.hourly_rate);
  setField('daily_rate', payroll.daily_rate || emp.daily_rate);
  setField('bank_name', payroll.bank_name || bank.bank_name || emp.bank_name);
  setField('bank_branch_name', bank.branch_name || '');
  setField('bank_swift_code', bank.swift_code || '');
  setField('bank_account_type', bank.account_type || 'ordinary');
  setField('bank_account_name', payroll.bank_account_name || bank.account_holder || emp.bank_account_name);
  setField('bank_account_number', payroll.bank_account_number || bank.account_number || emp.bank_account_number);
  // Store full bank snapshot from EmployeeAdmin as hidden JSON field
  const bankSnapshot = document.getElementById('employeeadmin_bank_snapshot');
  if (bankSnapshot && bank) {{ bankSnapshot.value = JSON.stringify(bank); }}
}}
if (document.getElementById('employee_picker_select')) loadSgEmployees();
</script>
"""


def salary_master_create_html(lang: str) -> str:
    """Batch create salary master records from EmployeeAdmin.

    Entity dropdown triggers automatic employee search from EmployeeAdmin.
    Department/Team filters work client-side on already-fetched results.
    Checkboxes with Select All / Deselect All / Toggle All.
    Confirmation dialog before submission.
    """
    entity_opts = all_entity_options_html("", lang)

    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.master')} — {t(lang,'action.create_salary_master')}</h1>
<div class="muted">选择法人实体后自动从 EmployeeAdmin 搜索在职员工。可通过部门/团队下拉进一步筛选。勾选员工后点击「{t(lang,'action.create_salary_master')}」创建薪资主记录。 / Select an entity to auto-search active employees from EmployeeAdmin. Use department/team dropdowns to further filter. Check employees and click "{t(lang,'action.create_salary_master')}" to create.</div></div>
<form class="card" method="post" action="{with_lang('/salary-master/create', lang)}" onsubmit="return confirmCreateSalaryMaster()">
<input type="hidden" id="selected_entity_id" name="entity_id" value="">
<div class="section-header"><h3>Step 1: Filter Employees / 筛选员工</h3></div>
<div class="message-strip">选择<b>法人实体</b>后自动加载在职员工。部门/团队下拉会根据加载结果动态填充，选择后可筛选列表。 / Select an <b>Entity</b> to auto-load active employees. Department/Team dropdowns are populated from results and can be used to filter.</div>
<div class="form-grid">
  <div class="field"><label>{t(lang,'label.entity')} <span style="color:#b91c1c">*</span></label><select id="filter_entity" onchange="onEntityChange()">{entity_opts}</select><div class="helper-text">选择后自动从 EmployeeAdmin 加载 / Auto-loads on select</div></div>
  <div class="field"><label>Department / 部门</label><select id="filter_department" onchange="applyLocalFilter()"><option value="">All Departments / 全部部门</option></select></div>
  <div class="field"><label>Team / 团队</label><select id="filter_team" onchange="applyLocalFilter()"><option value="">All Teams / 全部团队</option></select></div>
</div>
<div id="employee_section" style="display:none">
  <div class="section-header"><h3>Step 2: Select Employees / 选择员工 (<span id="employee_count_span">0</span> employees)</h3></div>
  <div id="existing_warning" class="message-strip warn" style="display:none"></div>
  <div class="sap-toolbar">
    <button type="button" class="secondary" onclick="selectAllCreate()">Select All / 全选</button>
    <button type="button" class="secondary" onclick="deselectAllCreate()">Deselect All / 全部取消</button>
    <button type="button" class="secondary" onclick="toggleAllCreate()">Toggle All / 反选</button>
  </div>
  <div class="table-scroll"><table><thead><tr><th>Select</th><th>No.</th><th>{t(lang,'label.employee')}</th><th>{t(lang,'label.entity')}</th><th>Department / Team</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.basic_salary')}</th><th>{t(lang,'label.hourly_rate')}</th><th>{t(lang,'label.daily_rate')}</th><th>Status</th><th>Payroll Ready</th></tr></thead><tbody id="employee_tbody_create"></tbody></table></div>
  <div class="helper-text" style="margin-top:8px" id="employee_summary_create"></div>
</div>
<div class="sap-toolbar end" style="margin-top:18px">
  <a class="button secondary" href="{with_lang('/salary-master', lang)}">{t(lang,'action.cancel')}</a>
  <button type="submit" id="create_btn" style="font-size:16px;min-width:240px;min-height:48px" disabled>{t(lang,'action.create_salary_master')}</button>
</div>
</form>
<script>
let allCreateEmployees = [];
// Existing salary master employee IDs — embedded server-side
let existingSalaryMasterIds = new Set({json.dumps([r["employee_id"] for r in load_salary_master()])});

// When entity changes → auto-fetch employees from EmployeeAdmin
function onEntityChange() {{
  const entity = document.getElementById('filter_entity').value;
  document.getElementById('selected_entity_id').value = entity;
  if (!entity) {{
    document.getElementById('filter_department').innerHTML = '<option value="">All Departments / 全部部门</option>';
    document.getElementById('filter_team').innerHTML = '<option value="">All Teams / 全部团队</option>';
    document.getElementById('employee_section').style.display = 'none';
    document.getElementById('create_btn').disabled = true;
    allCreateEmployees = [];
    return;
  }}
  loadCreateEmployees(entity);
}}

// Fetch employees from EmployeeAdmin for the given entity
async function loadCreateEmployees(entity) {{
  const tbody = document.getElementById('employee_tbody_create');
  const section = document.getElementById('employee_section');
  const countEl = document.getElementById('employee_count_span');
  const summaryEl = document.getElementById('employee_summary_create');
  const createBtn = document.getElementById('create_btn');
  const warningEl = document.getElementById('existing_warning');

  document.getElementById('selected_entity_id').value = entity;
  tbody.innerHTML = '<tr><td colspan="10">Loading from EmployeeAdmin...</td></tr>';
  section.style.display = 'block';
  createBtn.disabled = true;

  const params = new URLSearchParams({{lang: {json.dumps(lang)}, entity_id: entity}});

  try {{
    const res = await fetch('/api/employeeadmin-employees?' + params.toString(), {{credentials: 'same-origin'}});
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || 'EmployeeAdmin unavailable');
    allCreateEmployees = data.employees || [];

    // Populate department dropdown from results
    const depts = [...new Set(allCreateEmployees.map(e => e.department_label || e.department || '').filter(Boolean))].sort();
    const deptSelect = document.getElementById('filter_department');
    deptSelect.innerHTML = '<option value="">All Departments / 全部部门</option>' + depts.map(d => `<option value="${{d}}">${{d}}</option>`).join('');

    // Populate team dropdown from results
    const teams = [...new Set(allCreateEmployees.map(e => e.team_label || '').filter(Boolean))].sort();
    const teamSelect = document.getElementById('filter_team');
    teamSelect.innerHTML = '<option value="">All Teams / 全部团队</option>' + teams.map(t => `<option value="${{t}}">${{t}}</option>`).join('');

    // Render filtered list
    applyLocalFilter();
  }} catch (err) {{
    tbody.innerHTML = `<tr><td colspan="10">Error: ${{err.message}}</td></tr>`;
    createBtn.disabled = true;
    allCreateEmployees = [];
  }}
}}

// Apply department/team filter client-side and re-render table
function applyLocalFilter() {{
  const department = document.getElementById('filter_department').value;
  const team = document.getElementById('filter_team').value;
  const tbody = document.getElementById('employee_tbody_create');
  const countEl = document.getElementById('employee_count_span');
  const summaryEl = document.getElementById('employee_summary_create');
  const createBtn = document.getElementById('create_btn');
  const warningEl = document.getElementById('existing_warning');

  let filtered = allCreateEmployees;
  if (department) filtered = filtered.filter(e => (e.department_label || e.department || '') === department);
  if (team) filtered = filtered.filter(e => (e.team_label || '') === team);

  // Only show active employees
  filtered = filtered.filter(e => {{
    const status = (e.status || e.employment_status || '').toLowerCase();
    return status === 'active' || status === 'probation' || status === 'in_service' || status === 'employed' || status === 'onboarded' || status === '';
  }});

  countEl.textContent = filtered.length;

  // Count existing in salary master
  let existingCount = 0;
  filtered.forEach(e => {{
    const eid = e.employee_id || e.employee_number || e.employee_no || '';
    if (existingSalaryMasterIds.has(eid)) existingCount++;
  }});

  if (existingCount > 0) {{
    warningEl.style.display = 'block';
    warningEl.textContent = `${{existingCount}} employee(s) already exist in Salary Master and will be skipped during creation. / ${{existingCount}} 名员工已存在于薪资主数据中，创建时将被跳过。`;
  }} else {{
    warningEl.style.display = 'none';
  }}

  if (filtered.length === 0) {{
    tbody.innerHTML = '<tr><td colspan="10">No active employees found matching filters. / 未找到符合条件的在职员工。</td></tr>';
    summaryEl.textContent = '0 employee(s) loaded.';
    createBtn.disabled = true;
  }} else {{
    tbody.innerHTML = filtered.map((emp, idx) => {{
      const status = emp.status || emp.employment_status || '';
      const ready = emp.payroll_ready ? 'Ready' : 'Incomplete';
      const org = [(emp.department_label || emp.department || ''), (emp.team_label || '')].filter(Boolean).join(' / ');
      const empId = emp.employee_id || emp.employee_number || emp.employee_no || '';
      const empNo = emp.employee_number || emp.employee_no || '';
      const empName = emp.display_name || emp.employee_name || '';
      const alreadyExists = existingSalaryMasterIds.has(empId);
      const entityLabel = (emp.entity_id || '');
      // Extract payroll data from EmployeeAdmin response
      const payroll = emp.payroll || {{}};
      const salaryType = payroll.salary_type || '';
      const basicSalary = payroll.basic_salary || payroll.monthly_base_salary || payroll.base_salary || '';
      const hourlyRate = payroll.hourly_rate || payroll.hourly_wage || '';
      const dailyRate = payroll.daily_rate || payroll.daily_wage || '';
      // Format salary display
      const fmtMoney = (v) => v ? Number(v).toLocaleString('en-US', {{minimumFractionDigits: 2, maximumFractionDigits: 2}}) : '-';
      // Pre-check all that don't already exist; disable those that do
      const checked = alreadyExists ? '' : 'checked';
      const disabledAttr = alreadyExists ? 'disabled' : '';
      const rowStyle = alreadyExists ? 'style="opacity:0.5;background:#f5f5f5"' : '';
      const note = alreadyExists ? ' <span class="badge" style="font-size:10px">Already exists</span>' : '';
      return `<tr ${{rowStyle}}>
        <td><input type="checkbox" name="employee_id" value="${{empId}}" ${{checked}} ${{disabledAttr}} style="width:auto"></td>
        <td>${{empNo}}${{note}}</td>
        <td>${{empName}}</td>
        <td>${{entityLabel}}</td>
        <td>${{org}}</td>
        <td>${{salaryType || 'monthly'}}</td>
        <td class="right">${{fmtMoney(basicSalary)}}</td>
        <td class="right">${{fmtMoney(hourlyRate)}}</td>
        <td class="right">${{fmtMoney(dailyRate)}}</td>
        <td><span class="badge ${{status === 'active' ? 'active' : ''}}">${{status || 'active'}}</span></td>
        <td><span class="badge ${{ready === 'Ready' ? 'active' : ''}}">${{ready}}</span></td>
      </tr>`;
    }}).join('');
    createBtn.disabled = false;
    summaryEl.textContent = `${{filtered.length}} employee(s) loaded from EmployeeAdmin. ${{existingCount}} already in Salary Master (disabled).`;
  }}
}}

function selectAllCreate() {{
  document.querySelectorAll('#employee_tbody_create input[name=employee_id]:not([disabled])').forEach(c => c.checked = true);
}}
function deselectAllCreate() {{
  document.querySelectorAll('#employee_tbody_create input[name=employee_id]:not([disabled])').forEach(c => c.checked = false);
}}
function toggleAllCreate() {{
  document.querySelectorAll('#employee_tbody_create input[name=employee_id]:not([disabled])').forEach(c => c.checked = !c.checked);
}}
function confirmCreateSalaryMaster() {{
  const checked = document.querySelectorAll('#employee_tbody_create input[name=employee_id]:checked');
  if (checked.length === 0) {{
    alert('Please select at least one employee to create. / 请至少选择一名员工。');
    return false;
  }}
  return confirm({json.dumps(t(lang, 'msg.create_salary_master_confirm'))});
}}
</script>
"""


def new_batch_html(lang: str, entity_id: str = "SG", month: str = "") -> str:
    month = month or datetime.now().strftime("%Y-%m")
    employees = active_sg_salary_master(entity_id)
    if not employees:
        return f"""
<div class="sap-page-header"><h1>{t(lang,'action.generate')}</h1></div>
<div class="card"><div class="message-strip warn">No active SG salary master employees found for entity "{escape(entity_label(entity_id, lang))}". Please import employees from EmployeeAdmin first.</div>
<div class="sap-toolbar"><a class="button secondary" href="{with_lang('/salary-master', lang)}">Go to Salary Master</a></div></div>
"""
    employee_rows = []
    for emp in employees:
        readiness = salary_master_readiness(emp)
        readiness_badge = "ready" if readiness["ready"] else ("incomplete" if readiness["status"] == "incomplete" else "inactive")
        org_display = " / ".join(part for part in [emp.get("department_label") or emp.get("department"), emp.get("team_label")] if part)
        checked = "checked"  # Pre-select ALL active employees; user can uncheck if needed
        employee_rows.append(f"""
<tr>
  <td><label style="display:flex;align-items:center;gap:8px;margin:0"><input type="checkbox" name="employee_id" value="{escape(emp['employee_id'])}" {checked} style="width:auto"> {escape(emp['employee_number'])}</label></td>
  <td>{escape(emp['employee_name'])}</td>
  <td>{escape(org_display)}</td>
  <td>{escape(emp.get('salary_type',''))}</td>
  <td class="right">{money_fmt(emp['basic_salary'])}</td>
  <td><span class="badge {readiness_badge}">{escape(readiness['label'])}</span></td>
  <td class="right"><a href="{with_lang('/salary-master/edit', lang, employee_id=emp['employee_id'])}" class="button secondary" style="font-size:12px;padding:4px 8px">Edit</a></td>
</tr>""")

    return f"""
<div class="sap-page-header"><h1>{t(lang,'action.generate')} — Step 1: Select Employees</h1><div class="muted">Choose payroll month, entity, and which employees to include in this payroll batch.</div></div>
<form class="card" method="post" action="{with_lang('/batches/confirm', lang)}">
<div class="section-header"><h3>Batch settings / 批次设置</h3></div>
<div class="form-grid">
  <div class="field"><label>{t(lang,'label.month')}</label><input name="payroll_month" type="month" value="{escape(month)}" required></div>
  <div class="field"><label>{t(lang,'label.entity')}</label><select name="entity_id" required>{entity_options_html(distinct_sg_entities(), entity_id, lang)}</select></div>
  <div class="field"><label>Created by</label><input value="{escape(USER_ACTOR)}" readonly></div>
</div>
<div class="section-header"><h3>Eligible employees ({len(employees)} active) / 可选员工</h3></div>
<div class="message-strip">Select employees to include in this payroll batch. Only "Ready" employees are pre-selected. Use the Edit link to fix incomplete records.</div>
<div class="sap-toolbar">
  <button type="button" class="secondary" onclick="document.querySelectorAll('input[name=employee_id]').forEach(c=>c.checked=true)">Select All</button>
  <button type="button" class="secondary" onclick="document.querySelectorAll('input[name=employee_id]').forEach(c=>c.checked=!c.checked)">Toggle All</button>
</div>
<div class="table-scroll"><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>Department / Team</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.basic_salary')}</th><th>Readiness</th><th>Action</th></tr></thead><tbody>{''.join(employee_rows)}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(employees)} employee(s) eligible</div>
<div class="sap-toolbar end"><a class="button secondary" href="{with_lang('/batches', lang)}">{t(lang,'action.cancel')}</a><button>{t(lang,'action.generate')} → Review</button></div>
</form>
<script>
document.querySelectorAll('input[name=employee_id]').forEach(cb => {{
  cb.addEventListener('change', function() {{
    const total = document.querySelectorAll('input[name=employee_id]').length;
    const selected = document.querySelectorAll('input[name=employee_id]:checked').length;
    document.getElementById('selection_count').textContent = selected + '/' + total;
  }});
}});
</script>
"""


def batch_confirm_html(lang: str, form: dict[str, list[str]]) -> str:
    month = clean((form.get("payroll_month") or [""])[0])
    entity_id = clean((form.get("entity_id") or ["SG"])[0])
    selected_ids = form.get("employee_id", [])
    if not selected_ids:
        return f"""
<div class="sap-page-header"><h1>No Employees Selected</h1></div>
<div class="card"><div class="message-strip warn">Please select at least one employee to create a payroll batch.</div>
<div class="sap-toolbar"><a class="button" href="{with_lang('/batches/new', lang)}">Go Back</a></div></div>
"""
    all_employees = active_sg_salary_master(entity_id)
    id_set = set(selected_ids)
    selected = [e for e in all_employees if e.get("employee_id") in id_set]
    employee_rows = []
    total_gross_est = 0.0
    for emp in selected:
        salary_type = emp.get("salary_type", "monthly")
        if salary_type == "hourly":
            est_base = emp.get("hourly_rate", 0) * emp.get("standard_work_hours", 176)
        elif salary_type == "daily":
            est_base = emp.get("daily_rate", 0) * emp.get("standard_work_days", 22)
        else:
            est_base = emp.get("basic_salary", 0)
        est_gross = est_base + emp.get("fixed_allowance", 0) + emp.get("performance_bonus", 0)
        total_gross_est += est_gross
        employee_rows.append(f"<tr><td>{escape(emp['employee_number'])}</td><td>{escape(emp['employee_name'])}</td><td>{escape(emp.get('salary_type',''))}</td><td class='right'>{money_fmt(est_gross)}</td></tr>")

    return f"""
<div class="sap-page-header"><h1>{t(lang,'action.generate')} — Step 2: Confirm</h1><div class="muted">Review the batch details below before creating. Once created, you can proceed with calculation.</div></div>
<div class="card">
<div class="section-header"><h3>Batch summary / 批次汇总</h3></div>
<div class="grid">
  <div class="metric-card"><div>{t(lang,'label.month')}</div><div class="value">{escape(month)}</div></div>
  <div class="metric-card"><div>{t(lang,'label.entity')}</div><div class="value">{escape(entity_label(entity_id, lang))}</div></div>
  <div class="metric-card"><div>Employees selected</div><div class="value">{len(selected)}</div></div>
  <div class="metric-card"><div>Est. Gross Total</div><div class="value">SGD {money_fmt(total_gross_est)}</div></div>
</div>
</div>
<div class="card">
<div class="section-header"><h3>Selected employees / 已选员工</h3></div>
<div class="table-scroll"><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>{t(lang,'label.salary_type')}</th><th>Est. Gross</th></tr></thead><tbody>{''.join(employee_rows)}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(selected)} employee(s) selected</div>
</div>
<form method="post" action="{with_lang('/batches/create', lang)}" onsubmit="return confirm({json.dumps(t(lang, 'msg.create_batch_confirm'))})">
  <input type="hidden" name="payroll_month" value="{escape(month)}">
  <input type="hidden" name="entity_id" value="{escape(entity_id)}">
  {''.join(f'<input type="hidden" name="employee_id" value="{escape(eid)}">' for eid in selected_ids)}
  <div class="sap-toolbar end">
    <a class="button secondary" href="{with_lang('/batches/new', lang)}">{t(lang,'action.cancel')}</a>
    <button class="secondary" formaction="{with_lang('/batches/new', lang)}">← Back</button>
    <button style="font-size:16px;min-width:200px;min-height:48px">✓ Confirm & Create Batch</button>
  </div>
</form>
"""


def batch_detail_html(lang: str, batch_id: str) -> str:
    batch = find_batch(batch_id)
    if not batch:
        return f"<div class='card'>Batch not found.</div>"
    records = batch_records(batch_id)
    bstatus = batch.get("status", "draft")
    is_voided = bstatus == "voided"

    # Load payslips for PDF view links
    all_payslips = load_json(PAYSLIPS_PATH, [])
    payslip_by_record = {p.get("record_id"): p for p in all_payslips if p.get("batch_id") == batch_id and p.get("file_name")}

    actions = []
    if not is_voided:
        if bstatus == "finalized":
            actions.append(f"<a class='button' href='#gen-payslip-section' style='font-size:16px;min-width:180px'>📄 {t(lang,'action.payslips')}</a>")
        elif bstatus == "payslips_generated":
            actions.append(f"<form method='post' action='{with_lang('/batches/email', lang, batch_id=batch_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.batch_email_confirm'))})\"><button style='font-size:16px;min-width:180px'>{t(lang,'action.email')}</button></form>")
        elif bstatus == "sent_to_employees":
            actions.append(f"<form method='post' action='{with_lang('/batches/employee-confirm', lang, batch_id=batch_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.batch_employee_confirm_confirm'))})\"><button class='secondary'>{t(lang,'action.employee_confirm')}</button></form>")
            actions.append(f"<form method='post' action='{with_lang('/batches/finance', lang, batch_id=batch_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.batch_finance_confirm'))})\"><button class='danger'>{t(lang,'action.finance')}</button></form>")
        elif bstatus == "released_to_finance":
            actions.append(f"<form method='post' action='{with_lang('/batches/paid', lang, batch_id=batch_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.batch_paid_confirm'))})\"><button class='danger' style='font-size:16px;min-width:180px'>{t(lang,'action.paid')}</button></form>")
        # Return to previous step buttons for non-terminal statuses
        if bstatus in BATCH_RETURN_TARGETS and bstatus not in ("paid",):
            return_target = BATCH_RETURN_TARGETS[bstatus]
            return_msg = json.dumps(t(lang, 'msg.batch_return_step_confirm'))
            actions.append(f"<form method='post' action='{with_lang('/batches/return-step', lang, batch_id=batch_id)}' style='display:flex;gap:8px' onsubmit='return confirm({return_msg})'><input name='comment' placeholder='{t(lang, 'label.return_reason')}' style='min-width:200px' required><button class='secondary'>{t(lang,'action.return_to_prev')} ← {escape(return_target)}</button></form>")
        # Void only allowed for non-locked, non-finalized batches
        if bstatus not in LOCKED_BATCH_STATUSES:
            actions.append(f"<form method='post' action='{with_lang('/batches/void', lang, batch_id=batch_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.batch_void_confirm'))})\"><button class='danger'>{t(lang,'action.void')}</button></form>")
        # Allow regenerate in payslips_generated and beyond
        if bstatus == "payslips_generated":
            actions.append(f"<a class='button secondary' href='#gen-payslip-section' style='font-size:12px'>📄 {t(lang, 'action.payslips')} (regenerate)</a>")

    # ── Load salary master to enrich records with dept/team/entity ──
    salary_master_list = load_json(SALARY_MASTER_PATH, [])
    master_by_emp_id = {sm.get("employee_id"): sm for sm in salary_master_list}

    # ── Build gen_form for finalized / payslips_generated status ──
    gen_form = ""
    if bstatus in ("finalized", "payslips_generated") and records:
        entity_set: dict[str, str] = {}
        dept_set: dict[str, str] = {}
        team_set: dict[str, str] = {}
        # Enrich each record with dept/team/entity from salary master (synced from EmployeeAdmin)
        for r in records:
            sm = master_by_emp_id.get(r.get("employee_id", ""), {})
            # Use salary master data as source of truth for org info
            ent_id = sm.get("entity_id", "") or r.get("entity_id", "")
            dept = sm.get("department_label", "") or r.get("department_label", "")
            team = sm.get("team_label", "") or r.get("team_label", "")
            if ent_id and ent_id not in entity_set: entity_set[ent_id] = ent_id
            if dept and dept not in dept_set: dept_set[dept] = slug(dept)
            if team and team not in team_set: team_set[team] = slug(team)
            # Store enriched values on the record for later use
            r["_ent_id"] = ent_id
            r["_dept"] = dept
            r["_team"] = team
        entity_opts = "".join(f'<option value="{escape(e)}">{escape(entity_label(e, lang))}</option>' for e in sorted(entity_set.keys()))
        dept_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(dept_set.items()))
        team_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(team_set.items()))

        gen_rows_parts = []
        for r in records:
            ps = payslip_by_record.get(r.get('record_id'))
            has_pdf = "✅" if ps else "-"
            dept_display = r.get("_dept", "")
            if r.get("_team"): dept_display += " / " + r["_team"]
            gen_rows_parts.append(
                '<tr class="gen-row" data-entity="' + escape(r.get('_ent_id','')) + '" data-dept="' + escape(slug(r.get('_dept',''))) + '" data-team="' + escape(slug(r.get('_team',''))) + '" data-name="' + escape(r.get('employee_name','').lower()) + '" data-number="' + escape(r.get('employee_number','').lower()) + '">'
                '<td><input type="checkbox" class="gen-select" name="selected_ids" value="' + escape(r['record_id']) + '" checked style="width:auto;min-width:auto"></td>'
                '<td>' + escape(r.get('employee_number','')) + '</td>'
                '<td>' + escape(r.get('employee_name','')) + '</td>'
                '<td>' + escape(r.get('entity_id','')) + '</td>'
                '<td>' + escape(dept_display) + '</td>'
                '<td>' + escape(r.get('salary_type','monthly')) + '</td>'
                '<td class="right">' + money_fmt(r.get('gross_pay')) + '</td>'
                '<td class="right"><strong>' + money_fmt(r.get('net_pay')) + '</strong></td>'
                '<td>' + has_pdf + '</td>'
                '</tr>'
            )
        gen_rows_html = ''.join(gen_rows_parts)
        select_all_label = {"zh": "全选", "ja": "全て選択", "en": "Select All"}.get(lang, "Select All")
        deselect_all_label = {"zh": "取消全选", "ja": "選択解除", "en": "Deselect All"}.get(lang, "Deselect All")
        search_placeholder = {"zh": "搜索姓名/工号...", "ja": "名前・番号で検索...", "en": "Search name or number..."}.get(lang, "Search name or number...")
        all_entities_label = {"zh": "全部法人", "ja": "全法人", "en": "All Entities"}.get(lang, "All Entities")
        all_depts_label = {"zh": "全部部门", "ja": "全部門", "en": "All Depts"}.get(lang, "All Depts")
        all_teams_label = {"zh": "全部Team", "ja": "全Team", "en": "All Teams"}.get(lang, "All Teams")
        clear_label = {"zh": "清除", "ja": "クリア", "en": "Clear"}.get(lang, "Clear")
        gen_form = f"""
<div class="card" id="gen-payslip-section" style="border-left:4px solid var(--sap-accent)">
<div class="section-header"><h3>📄 {t(lang, 'action.payslips')} — Select employees / 选择员工生成工资单</h3></div>
<div class="sap-toolbar" style="margin-bottom:8px;flex-wrap:wrap;gap:8px">
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('#gen-payslip-section .gen-select').forEach(function(c){{c.checked=true}});updateBatchGenCount()">{select_all_label}</button>
  <button type="button" class="secondary" style="font-size:12px" onclick="document.querySelectorAll('#gen-payslip-section .gen-select').forEach(function(c){{c.checked=false}});updateBatchGenCount()">{deselect_all_label}</button>
  <span style="font-weight:800;color:var(--blue);margin-left:8px" id="batch-gen-count">{len(records)} selected</span>
</div>
<div class="search-bar" style="margin-bottom:10px;display:flex;gap:8px;flex-wrap:wrap">
  <input id="batch-gen-name-search" type="text" placeholder="{search_placeholder}" oninput="applyBatchGenFilters()" style="min-width:140px;flex:1">
  <select id="batch-gen-entity-filter" onchange="applyBatchGenFilters()" style="min-width:130px"><option value="">{all_entities_label}</option>{entity_opts}</select>
  <select id="batch-gen-dept-filter" onchange="applyBatchGenFilters()" style="min-width:120px"><option value="">{all_depts_label}</option>{dept_opts}</select>
  <select id="batch-gen-team-filter" onchange="applyBatchGenFilters()" style="min-width:120px"><option value="">{all_teams_label}</option>{team_opts}</select>
  <button type="button" class="secondary" style="font-size:11px" onclick="clearBatchGenFilters()">{clear_label}</button>
</div>
<form id="gen-payslips-form" method="post" action="{with_lang('/batches/payslips', lang, batch_id=batch_id)}">
<div class="table-scroll" style="max-height:400px"><table><thead><tr>
<th style="width:30px"><input type="checkbox" id="batch-gen-select-all" checked style="width:auto;min-width:auto" onclick="var c=this.checked;document.querySelectorAll('#gen-payslip-section .gen-select').forEach(function(x){{if(x.closest('.gen-row').style.display!=='none')x.checked=c}});updateBatchGenCount()"></th>
<th>No.</th><th>{t(lang,'label.employee')}</th><th>Entity</th><th>{t(lang,'label.department')}</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.gross')}</th><th>{t(lang,'label.net')}</th><th>{t(lang,'label.pdf_status')}</th>
</tr></thead><tbody>{gen_rows_html}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(records)} employee(s). Existing PDFs will be overwritten.</div>
<div class="sap-toolbar end" style="margin-top:12px"><button type="button" style="font-size:16px;min-width:200px" onclick="handleBatchGenSubmit()">📄 {t(lang, 'action.payslips')} (Selected)</button></div>
</form>
<!-- Confirm Modal -->
<div class="modal-overlay" id="gen-payslips-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">⚠️</div>
<p><strong>{t(lang, 'msg.payslip_gen_modal_title')}</strong></p>
<p>{t(lang, 'msg.payslip_gen_modal_body').replace('{count}', '<span class="modal-count" id="batch-gen-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no default-no" onclick="hideModal('gen-payslips-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes" onclick="submitGenForm('gen-payslips-form','gen-payslips-modal')">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
<script>
function handleBatchGenSubmit(){{
var sel=document.querySelectorAll('#gen-payslip-section .gen-select:checked').length;
if(sel===0){{alert({json.dumps(t(lang, 'msg.payslip_gen_select_prompt'))});return}}
document.getElementById('batch-gen-modal-count').textContent=sel;
showConfirmModal('gen-payslips-modal');
}}
function applyBatchGenFilters(){{var nv=(document.getElementById('batch-gen-name-search')?document.getElementById('batch-gen-name-search').value:'').toLowerCase().trim();var ev=document.getElementById('batch-gen-entity-filter')?document.getElementById('batch-gen-entity-filter').value:'';var dv=document.getElementById('batch-gen-dept-filter')?document.getElementById('batch-gen-dept-filter').value:'';var tv=document.getElementById('batch-gen-team-filter')?document.getElementById('batch-gen-team-filter').value:'';document.querySelectorAll('#gen-payslip-section .gen-row').forEach(function(r){{var m=(!nv||r.getAttribute('data-name').indexOf(nv)>=0||r.getAttribute('data-number').indexOf(nv)>=0)&&(!ev||r.getAttribute('data-entity')===ev)&&(!dv||r.getAttribute('data-dept')===dv)&&(!tv||r.getAttribute('data-team')===tv);r.style.display=m?'':'none';if(!m){{var cb=r.querySelector('.gen-select');if(cb)cb.checked=false}}}});updateBatchGenCount()}}
function clearBatchGenFilters(){{var el=document.getElementById('batch-gen-name-search');if(el)el.value='';el=document.getElementById('batch-gen-entity-filter');if(el)el.value='';el=document.getElementById('batch-gen-dept-filter');if(el)el.value='';el=document.getElementById('batch-gen-team-filter');if(el)el.value='';applyBatchGenFilters()}}
function updateBatchGenCount(){{var sel=document.querySelectorAll('#gen-payslip-section .gen-select:checked').length;var el=document.getElementById('batch-gen-count');if(el)el.textContent=sel+' selected'}}
document.querySelectorAll('#gen-payslip-section .gen-select').forEach(function(cb){{cb.addEventListener('change',updateBatchGenCount)}});
</script>
</div>"""

    # ── Build records table ──
    show_pdf_col = bstatus in ("payslips_generated", "sent_to_employees", "employee_confirmed", "released_to_finance", "paid")
    trs = []
    for r in records:
        ps = payslip_by_record.get(r.get("record_id"))
        view_link = ""
        pdf_link = ""
        if ps:
            pid = ps.get("payslip_id", "")
            view_link = f" <a href='{with_lang('/payslip/view', lang, payslip_id=pid)}' target='_blank' class='button secondary' style='font-size:11px;padding:2px 6px;min-height:auto'>📋</a>"
            if ps.get("file_name"):
                pdf_link = f" <a href='{with_lang('/payslip/download', lang, payslip_id=pid)}' target='_blank' class='button secondary' style='font-size:11px;padding:2px 6px;min-height:auto'>📄</a>"
        elif show_pdf_col:
            view_link = "-"
            pdf_link = "-"
        view_cell = f"<td>{view_link}{pdf_link}</td>" if show_pdf_col else ""
        trs.append(f"<tr><td><a href='{with_lang('/records/edit', lang, record_id=r['record_id'])}'>{escape(r['employee_number'])}</a></td><td>{escape(r['employee_name'])}</td><td>{escape(r['salary_type'])}</td><td class='right'>{money_fmt(r['work_days'])}</td><td class='right'>{money_fmt(r['work_hours'])}</td><td class='right'>{money_fmt(r['gross_pay'])}</td><td class='right'>{money_fmt(r['cpf_employee'])}</td><td class='right'>{money_fmt(r['deduction_total'])}</td><td class='right'>{money_fmt(r['net_pay'])}</td><td class='right'>{money_fmt(r['employer_cost_total'])}</td>{view_cell}<td>{status_badge(r.get('employee_confirmation_status','pending'))}</td></tr>")
    pdf_th = f"<th>{t(lang,'label.pdf_status')}</th>" if show_pdf_col else ""
    table = f"<p>{t(lang,'msg.no_records')}</p>" if not records else f"<div class='table-scroll'><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.work_days')}</th><th>{t(lang,'label.work_hours')}</th><th>{t(lang,'label.gross')}</th><th>{t(lang,'label.cpf_employee')}</th><th>{t(lang,'label.deductions')}</th><th>{t(lang,'label.net')}</th><th>{t(lang,'label.employer_cost')}</th>{pdf_th}<th>Confirm</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"

    # Per-currency salary summary for batch
    batch_ct = batch.get("currency_totals") or {}
    if batch_ct:
        currency_cards = []
        for cur in sorted(batch_ct.keys()):
            ct = batch_ct[cur]
            employee_word = {"zh": "人", "ja": "人", "en": "emp"}.get(lang, "emp")
            currency_cards.append(
                f"<div class='metric-card'><div style='font-weight:600;color:var(--sap-accent)'>{escape(cur)}</div>"
                f"<div class='value' style='font-size:16px'>{t(lang,'label.gross')} {money_fmt(ct.get('gross'))} &nbsp;/&nbsp; {t(lang,'label.net')} {money_fmt(ct.get('net'))}</div>"
                f"<div class='muted'>{t(lang,'label.employer_cost')} {money_fmt(ct.get('employer_cost'))} &nbsp;·&nbsp; {ct.get('count',0)} {employee_word}</div>"
                f"</div>"
            )
        batch_summary = f"<div class='grid'>{''.join(currency_cards)}</div>"
    else:
        batch_summary = f"<div class='grid'><div class='metric-card'><div>{t(lang,'label.gross')}</div><div class='value'>{money_fmt(batch.get('gross_total'))}</div></div><div class='metric-card'><div>{t(lang,'label.net')}</div><div class='value'>{money_fmt(batch.get('net_total'))}</div></div><div class='metric-card'><div>{t(lang,'label.employer_cost')}</div><div class='value'>{money_fmt(batch.get('employer_cost_total'))}</div></div></div>"

    progress_html = batch_progress_bar(lang, bstatus)
    return f"""
<div class="sap-page-header"><h1>{escape(batch_id)}</h1><div>{t(lang,'label.month')}: {escape(batch['payroll_month'])} · {t(lang,'label.status')}: {status_badge(batch['status'])}</div></div>
{batch_summary}
<div class="card">{progress_html}</div>
<div class="card"><div class="sap-toolbar">{''.join(actions)}<a class="button secondary" href="{with_lang('/reports/payroll.csv', lang, batch_id=batch_id)}">Payroll CSV</a><a class="button secondary" href="{with_lang('/reports/bank.csv', lang, batch_id=batch_id)}">Bank CSV</a></div>{table}<div class="helper-text" style="margin-top:8px">{len(records)} record(s) total</div></div>
{gen_form}
"""


def record_form_html(lang: str, record_id: str) -> str:
    record = next((r for r in load_records() if r.get("record_id") == record_id), None)
    if not record:
        return "<div class='card'>Record not found.</div>"
    fields = ["work_days", "work_hours", "fixed_allowance", "performance_bonus", "bonus", "other_payment", "recurring_deductions", "other_deduction", "income_tax", "cpf_employee", "cpf_employer", "skill_development_levy", "foreign_worker_levy"]
    inputs = "".join(f"<div class='field'><label>{escape(field.replace('_',' ').title())}</label><input name='{field}' value='{money_fmt(record.get(field))}'></div>" for field in fields)
    inputs += f"<div class='field'><label>Payroll Currency</label><select name='payroll_currency'>{currency_options(record.get('payroll_currency','SGD'))}</select></div>"
    status = clean(record.get("employee_confirmation_status") or "pending")
    opts = "".join(f"<option value='{s}' {'selected' if s==status else ''}>{s}</option>" for s in ["pending", "confirmed", "change_requested", "no_response_auto_confirmed"])
    messages = "".join(f"<li>{escape(m)}</li>" for m in record.get("calculation_messages", []))
    return f"""
<div class="sap-page-header"><h1>{escape(record['employee_name'])}</h1><div>{escape(record['record_id'])}</div></div>
<form class="card" method="post" action="{with_lang('/records/save', lang, record_id=record_id)}"><div class="form-grid">{inputs}<div class='field'><label>Employee Confirmation</label><select name='employee_confirmation_status'>{opts}</select></div></div><div class='field'><label>Employee Comment / HR Memo</label><textarea name='employee_comment'>{escape(record.get('employee_comment',''))}</textarea></div><div class="message-strip"><b>Calculation Messages</b><ul>{messages}</ul></div><div class="sap-toolbar"><button>{t(lang,'action.save')}</button><a class="button secondary" href="{with_lang('/batches/detail', lang, batch_id=record['batch_id'])}">{t(lang,'action.cancel')}</a></div></form>
"""


def reports_html(lang: str) -> str:
    batches = load_batches()
    rows = "".join(f"<tr><td>{escape(b['batch_id'])}</td><td>{escape(b['payroll_month'])}</td><td>{status_badge(b['status'])}</td><td class='right'>{money_fmt(b.get('net_total'))}</td><td><a href='{with_lang('/reports/payroll.csv', lang, batch_id=b['batch_id'])}'>Payroll CSV</a> · <a href='{with_lang('/reports/cost.csv', lang, batch_id=b['batch_id'])}'>Cost CSV</a> · <a href='{with_lang('/reports/bank.csv', lang, batch_id=b['batch_id'])}'>Bank CSV</a></td></tr>" for b in batches)
    return f"<div class='sap-page-header'><h1>{t(lang,'nav.reports')}</h1></div><div class='card'><div class='table-scroll'><table><thead><tr><th>Batch</th><th>{t(lang,'label.month')}</th><th>{t(lang,'label.status')}</th><th>{t(lang,'label.net')}</th><th>Exports</th></tr></thead><tbody>{rows}</tbody></table></div><div class='helper-text' style='margin-top:8px'>{len(batches)} batch(es) total</div></div>"


def parameters_html(lang: str) -> str:
    rows = active_parameters()
    body = "".join(f"<tr><td>{escape(p.get('parameter_id',''))}</td><td>{escape(p.get('parameter_type',''))}</td><td>{escape(p.get('effective_start_date',''))}</td><td>{escape(p.get('status',''))}</td><td><pre>{escape(json.dumps(p.get('values',{}), ensure_ascii=False, indent=2))}</pre></td></tr>" for p in rows)
    return f"<div class='sap-page-header'><h1>{t(lang,'nav.parameters')}</h1></div><div class='message-strip warn'>CPF/SDL/FWL rates are configuration controlled. Validate Singapore statutory rates before production payroll use.</div><div class='card'><div class='table-scroll'><table><thead><tr><th>ID</th><th>Type</th><th>Effective</th><th>Status</th><th>Values</th></tr></thead><tbody>{body}</tbody></table></div><div class='helper-text' style='margin-top:8px'>{len(rows)} active parameter(s)</div></div>"


def audit_html(lang: str) -> str:
    all_logs = load_json(AUDIT_LOGS_PATH, [])
    total = len(all_logs)
    rows = list(reversed(all_logs))[:200]
    body = "".join(f"<tr><td>{escape(r.get('timestamp',''))}</td><td>{escape(r.get('module',''))}</td><td>{escape(r.get('record_id',''))}</td><td>{escape(r.get('action',''))}</td><td>{escape(r.get('user',''))}</td></tr>" for r in rows)
    return f"<div class='sap-page-header'><h1>{t(lang,'nav.audit')}</h1></div><div class='card'><div class='table-scroll'><table><thead><tr><th>Time</th><th>Module</th><th>Record</th><th>Action</th><th>User</th></tr></thead><tbody>{body}</tbody></table></div><div class='helper-text' style='margin-top:8px'>Showing latest {len(rows)} of {total} audit entries</div></div>"


# ── Monthly Salary Sheet HTML Generators ──────────────────────────

def monthly_sheets_list_html(lang: str) -> str:
    """List all monthly salary sheets."""
    sheets = load_sheets()
    if not sheets:
        return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.monthly_sheets')}</h1><div class="muted">Enhanced monthly salary calculation workflow with attendance confirmation, versioned calculation, and manager review.</div></div>
<div class="card"><div class="sap-toolbar"><a class="button" href="{with_lang('/monthly-sheets/new', lang)}">{t(lang,'action.create_sheet')}</a></div><p class="muted">{t(lang,'msg.no_records')}</p></div>"""
    trs = []
    for s in sorted(sheets, key=lambda x: x.get("payroll_month", ""), reverse=True):
        sheet_status = s.get("status", "draft")
        detail_url = with_lang('/monthly-sheets/detail', lang, sheet_id=s.get('sheet_id'))
        review_url = with_lang('/monthly-sheets/review', lang, sheet_id=s.get('sheet_id'))
        # Status-aware action button
        if sheet_status in ("draft", "hr_confirmed"):
            action_btn = f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{review_url}'>{t(lang,'action.review_sheet')}</a>"
        elif sheet_status == "manager_review":
            action_btn = f"<a class='button' style='font-size:12px;padding:4px 8px;background:var(--amber);border-color:var(--amber)' href='{detail_url}'>{t(lang,'action.approve_finalize')}</a>"
        elif sheet_status == "hr_reviewed":
            action_btn = f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>{t(lang,'action.send_manager_review')}</a>"
        elif sheet_status == "calculated":
            action_btn = f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>{t(lang,'action.hr_approve')}</a>"
        elif sheet_status == "voided":
            delete_url = with_lang('/monthly-sheets/delete', lang, sheet_id=s.get('sheet_id'))
            action_btn = f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>查看</a>" if lang == "zh" else (f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>表示</a>" if lang == "ja" else f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>View</a>")
            action_btn += f"<form method='post' action='{delete_url}' style='display:inline;margin-left:4px' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.delete_sheet_confirm'))})\"><button class='danger' style='font-size:11px;padding:3px 6px'>{t(lang,'action.delete_sheet')}</button></form>"
        else:
            action_btn = f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>查看</a>" if lang == "zh" else (f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>表示</a>" if lang == "ja" else f"<a class='button secondary' style='font-size:12px;padding:4px 8px' href='{detail_url}'>View</a>")
        # Compact per-currency totals for list view
        ct = s.get("currency_totals") or {}
        if ct:
            cur_parts = []
            for cur in sorted(ct.keys()):
                cur_parts.append(f"{escape(cur)} {money_fmt(ct[cur].get('net'))}")
            cur_display = " &nbsp;|&nbsp; ".join(cur_parts)
        else:
            cur_display = f"Gross {money_fmt(s.get('gross_total'))} / Net {money_fmt(s.get('net_total'))}"
        trs.append(f"<tr><td><a href='{detail_url}'>{escape(s.get('sheet_id',''))}</a></td><td>{escape(s.get('payroll_month',''))}</td><td>{escape(entity_label(s.get('entity_id',''), lang))}</td><td>{escape(s.get('country_code',''))}</td><td>{status_badge(sheet_status)}</td><td class='right'>{s.get('employee_count',0)}</td><td class='right'>{cur_display}</td><td>{escape(s.get('attendance_source','manual'))}</td><td>{action_btn}</td></tr>")
    actions_label = {"zh": "操作", "ja": "操作", "en": "Actions"}.get(lang, "Actions")
    table = f"<div class='table-scroll'><table><thead><tr><th>Sheet ID</th><th>{t(lang,'label.month')}</th><th>{t(lang,'label.entity')}</th><th>{t(lang,'label.country')}</th><th>{t(lang,'label.status')}</th><th>Count</th><th>Currency Totals (Net)</th><th>Attendance</th><th>{actions_label}</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    draft_count = sum(1 for s in sheets if s.get('status') == 'draft')
    calc_count = sum(1 for s in sheets if s.get('status') in ('calculated', 'hr_reviewed'))
    finalized_count = sum(1 for s in sheets if s.get('status') == 'finalized')
    voided_count = sum(1 for s in sheets if s.get('status') == 'voided')
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.monthly_sheets')}</h1><div class="sap-info-strip"><span>📊 {len(sheets)} sheets total</span><span>📝 {draft_count} draft</span><span>🔢 {calc_count} in calculation</span><span>✅ {finalized_count} finalized</span>{'<span>🗑️ ' + str(voided_count) + ' voided</span>' if voided_count else ''}</div></div>
<div class="card"><div class="sap-toolbar"><a class="button" href="{with_lang('/monthly-sheets/new', lang)}">{t(lang,'action.create_sheet')}</a></div>{table}<div class='helper-text' style='margin-top:8px'>{len(sheets)} sheet(s) total</div></div>"""


def new_monthly_sheet_html(lang: str, entity_id: str = "", month: str = "", filter_department: str = "", filter_team: str = "") -> str:
    """Form to create a new monthly salary sheet.

    Entity is selected from a dropdown populated by master data.
    After entity selection, employees are loaded with checkboxes for selective inclusion.
    Department and Team filters allow narrowing down the employee list.
    SG is NOT a controlling item — entity drives the employee list.
    """
    month = month or datetime.now().strftime("%Y-%m")

    # Build entity dropdown from master data (NOT hardcoded to SG)
    entities = distinct_sg_entities()
    ent_opts = ""
    for ent in entities:
        selected = "selected" if ent == entity_id else ""
        ent_opts += f"<option value='{escape(ent)}' {selected}>{escape(entity_label(ent, lang))}</option>"

    # Only load employees when an entity has been selected
    all_employees = active_sg_salary_master(entity_id) if entity_id else []

    # Build department and team dropdown options from loaded employees
    dept_set: set[str] = set()
    team_set: set[str] = set()
    for emp in all_employees:
        dept = clean(emp.get("department_label") or emp.get("department"))
        team = clean(emp.get("team_label"))
        if dept:
            dept_set.add(dept)
        if team:
            team_set.add(team)

    # Apply department and team filters
    employees = all_employees
    if filter_department:
        employees = [e for e in employees if (e.get("department_label") or e.get("department")) == filter_department]
    if filter_team:
        employees = [e for e in employees if e.get("team_label") == filter_team]

    # Build filter dropdowns
    dept_opts = '<option value="">All Departments</option>' + "".join(
        f'<option value="{escape(d)}" {"selected" if filter_department==d else ""}>{escape(d)}</option>'
        for d in sorted(dept_set)
    )
    team_opts = '<option value="">All Teams</option>' + "".join(
        f'<option value="{escape(t)}" {"selected" if filter_team==t else ""}>{escape(t)}</option>'
        for t in sorted(team_set)
    )
    has_filter = bool(filter_department or filter_team)

    year = int(month[:4])
    mo = int(month[5:7])
    std_days, std_hours = get_calendar_month_days("SG", year, mo)
    calendar_info = f"<strong>{std_days}</strong> days / <strong>{std_hours}</strong> hours (from SG payroll calendar)"

    # Build employee selection table (only when entity is selected)
    employee_section = ""
    if entity_id and all_employees:
        if not employees:
            employee_section = f"""
<div class="section-header"><h3>Eligible employees / 可选员工</h3></div>
<div class="message-strip warn">No employees match the selected Department / Team filters. <a href="{with_lang('/monthly-sheets/new', lang, entity_id=entity_id, month=month)}">Clear filters</a> to see all {len(all_employees)} eligible employees.</div>"""
        else:
            employee_rows = []
            for emp in employees:
                readiness = salary_master_readiness(emp)
                org_display = " / ".join(part for part in [emp.get("department_label") or emp.get("department"), emp.get("team_label")] if part)
                checked = "checked" if readiness["ready"] else ""
                employee_rows.append(f"""
<tr>
  <td><label style="display:flex;align-items:center;gap:8px;margin:0"><input type="checkbox" name="employee_id" value="{escape(emp['employee_id'])}" {checked} style="width:auto"> {escape(emp['employee_number'])}</label></td>
  <td>{escape(emp['employee_name'])}</td>
  <td>{escape(org_display)}</td>
  <td>{escape(emp.get('salary_type',''))}</td>
  <td class="right">{money_fmt(emp['basic_salary'])}</td>
  <td><span class="badge {readiness['status']}">{escape(readiness['label'])}</span></td>
</tr>""")
            filter_note = f" (filtered from {len(all_employees)} total)" if has_filter else ""
            employee_section = f"""
<div class="section-header"><h3>Eligible employees ({len(employees)}{filter_note}) / 可选员工</h3></div>
<div class="message-strip">Select employees to include. Only "Ready" employees are pre-selected. Use checkboxes to choose specific employees.</div>
<div class="sap-toolbar">
  <button type="button" class="secondary" onclick="document.querySelectorAll('input[name=employee_id]').forEach(c=>c.checked=true)">Select All / 全选</button>
  <button type="button" class="secondary" onclick="document.querySelectorAll('input[name=employee_id]').forEach(c=>c.checked=!c.checked)">Toggle All / 反选</button>
</div>
<div class="table-scroll"><table><thead><tr><th>No.</th><th>{t(lang,'label.employee')}</th><th>Department / Team</th><th>{t(lang,'label.salary_type')}</th><th>{t(lang,'label.basic_salary')}</th><th>Readiness</th></tr></thead><tbody>{''.join(employee_rows)}</tbody></table></div>
<div class="helper-text" style="margin-top:8px">{len(employees)} employee(s) eligible{filter_note}</div>"""
    elif entity_id and not all_employees:
        employee_section = f"""
<div class="section-header"><h3>Employees / 员工</h3></div>
<div class="message-strip warn">No active SG salary master employees found for entity "{escape(entity_label(entity_id, lang))}". Please import employees from EmployeeAdmin first.</div>
<div class="sap-toolbar"><a class="button secondary" href="{with_lang('/salary-master', lang)}">Go to Salary Master</a></div>"""
    else:
        employee_section = f"""
<div class="section-header"><h3>Employees / 员工</h3></div>
<div class="message-strip info">Please select an Entity above to load eligible employees from Salary Master. / 请先在上方选择一个法人/公司，系统将从薪资主数据中加载对应的员工列表。</div>"""

    # onchange handler for entity dropdown: reload page with selected entity, preserving other params
    entity_onchange = f"var m=document.querySelector('input[name=payroll_month]').value;window.location='{with_lang('/monthly-sheets/new', lang)}&entity_id='+this.value+'&month='+m"

    return f"""
<div class="sap-page-header"><h1>{t(lang,'action.create_sheet')}</h1><div class="sap-info-strip"><span>🏢 Select entity → filter by department/team → select employees → generate sheet</span></div></div>
<form class="card" method="get" action="{with_lang('/monthly-sheets/new', lang)}">
<input type="hidden" name="month" value="{escape(month)}">
<input type="hidden" name="entity_id" value="{escape(entity_id)}">
<div class="section-header"><h3>Filter employees / 筛选员工</h3></div>
<div class="form-grid">
  <div class="field"><label>{t(lang,'label.entity')} <span style="color:var(--sap-red)">*</span></label>
    <select name="entity_id" required onchange="{entity_onchange}">
      <option value="">-- {t(lang,'label.entity')} / 请选择法人 --</option>
      {ent_opts}
    </select>
    <div class="helper-text">Entity list from Salary Master / 下拉选项来源于薪资主数据中的法人</div></div>
  <div class="field"><label>Department</label><select name="filter_department" onchange="this.form.submit()">{dept_opts if entity_id else '<option value="">-- Select entity first --</option>'}</select></div>
  <div class="field"><label>Team</label><select name="filter_team" onchange="this.form.submit()">{team_opts if entity_id else '<option value="">-- Select entity first --</option>'}</select></div>
</div>
{'' if entity_id else '<noscript><button style="margin-bottom:12px">Load Employees</button></noscript>'}
</form>
<form id="create-sheet-form" class="card" method="post" action="{with_lang('/monthly-sheets/create', lang)}">
<div class="section-header"><h3>Sheet settings / 工资表设置</h3></div>
<div class="form-grid">
  <div class="field"><label>{t(lang,'label.month')}</label><input name="payroll_month" type="month" value="{escape(month)}" required></div>
  <div class="field"><label>{t(lang,'label.entity')} <span style="color:var(--sap-red)">*</span></label>
    <input type="hidden" name="entity_id" value="{escape(entity_id)}">
    <div style="padding:9px 10px;background:#f8fafc;border:1px solid var(--line);border-radius:8px;font-weight:600">{escape(entity_label(entity_id, lang)) if entity_id else '—'}</div></div>
  <div class="field"><label>{t(lang,'label.attendance_source')}</label>
    <select name="attendance_source"><option value="manual">{t(lang,'label.manual_input')}</option><option value="timesheet">{t(lang,'label.from_timesheet')}</option></select></div>
  <div class="field"><label>{t(lang,'label.standard_work_days')}</label><input name="standard_work_days" value="{std_days}"><div class="helper-text">{calendar_info} / 可手动修改</div></div>
</div>
{employee_section}
<div class="sap-toolbar end"><a class="button secondary" href="{with_lang('/monthly-sheets', lang)}">{t(lang,'action.cancel')}</a><button type="button" style="font-size:16px;min-width:200px;min-height:48px" {'disabled' if not entity_id else ''} onclick="var cnt=document.querySelectorAll('input[name=employee_id]:checked').length;document.getElementById('create-sheet-modal-count').textContent=cnt;showConfirmModal('create-sheet-modal')">{t(lang,'action.create_sheet')}</button></div>
</form>
<!-- Create Sheet Confirm Modal (Default No) -->
<div class="modal-overlay" id="create-sheet-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">⚠️</div>
<p><strong>{t(lang, 'msg.create_sheet_modal_title')}</strong></p>
<p>{t(lang, 'msg.create_sheet_modal_body').replace('{count}', '<span class="modal-count" id="create-sheet-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no default-no" onclick="hideModal('create-sheet-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes" onclick="submitGenForm('create-sheet-form','create-sheet-modal')">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
"""


def payroll_progress_bar(lang: str, current_status: str) -> str:
    """Render a SAP-style progress bar for the monthly salary calculation workflow."""
    steps = [
        ("draft", "草稿" if lang == "zh" else ("下書き" if lang == "ja" else "Draft")),
        ("hr_confirmed", "HR确认" if lang == "zh" else ("HR確認" if lang == "ja" else "HR Confirmed")),
        ("calculated", "已计算" if lang == "zh" else ("計算済" if lang == "ja" else "Calculated")),
        ("hr_reviewed", "HR审核" if lang == "zh" else ("HRレビュー" if lang == "ja" else "HR Reviewed")),
        ("manager_review", "经理审核" if lang == "zh" else ("マネージャー" if lang == "ja" else "Manager Review")),
        ("finalized", "批准定案" if lang == "zh" else ("承認確定" if lang == "ja" else "Approved & Finalized")),
    ]
    status_order = [s[0] for s in steps]
    current_idx = status_order.index(current_status) if current_status in status_order else -1

    parts = ['<div class="progress-bar">']
    for i, (key, label) in enumerate(steps):
        if i > 0:
            line_class = "done" if i <= current_idx else ""
            parts.append(f'<div class="progress-line {line_class}"></div>')
        if i < current_idx:
            circle = "✓"
            cls = "done"
        elif i == current_idx:
            circle = str(i + 1)
            cls = "current"
        else:
            circle = str(i + 1)
            cls = "pending"
        parts.append(f'<div class="progress-step"><div class="progress-circle {cls}">{circle}</div><span class="progress-label {cls}">{label}</span></div>')
    parts.append('</div>')
    return ''.join(parts)


def release_progress_bar(lang: str, current_status: str) -> str:
    """Render a SAP-style progress bar for the payroll release workflow."""
    steps = [
        ("pending_release", "待发放" if lang == "zh" else ("支給予定" if lang == "ja" else "Pending")),
        ("payslips_generated", "工资单已生成" if lang == "zh" else ("給与明細生成済" if lang == "ja" else "Payslips")),
        ("hr_confirmed", "HR已确认" if lang == "zh" else ("HR確認済" if lang == "ja" else "Confirmed")),
        ("sent", "已发送" if lang == "zh" else ("送信済" if lang == "ja" else "Sent")),
        ("paid", "已发放" if lang == "zh" else ("支払済" if lang == "ja" else "Paid")),
    ]
    status_order = [s[0] for s in steps]
    # Map intermediate statuses to their canonical position
    status_map = {
        "pending_release": 0,
        "payslips_generated": 1,
        "hr_confirmed": 2,
        "email_draft_prepared": 2,
        "sending": 3,
        "partially_sent": 3,
        "sent": 3,
        "paid": 4,
    }
    current_idx = status_map.get(current_status, -1)

    parts = ['<div class="progress-bar">']
    for i, (key, label) in enumerate(steps):
        if i > 0:
            line_class = "done" if i <= current_idx else ""
            parts.append(f'<div class="progress-line {line_class}"></div>')
        if i < current_idx:
            circle = "✓"
            cls = "done"
        elif i == current_idx:
            circle = str(i + 1)
            cls = "current"
        else:
            circle = str(i + 1)
            cls = "pending"
        parts.append(f'<div class="progress-step"><div class="progress-circle {cls}">{circle}</div><span class="progress-label {cls}">{label}</span></div>')
    parts.append('</div>')
    return ''.join(parts)


def batch_progress_bar(lang: str, current_status: str) -> str:
    """Render a SAP-style progress bar for the batch payroll workflow.

    Split into two groups with independent numbering:
      - 核算 (Calculation): steps 1-4  (draft → calculated → hr_reviewed → finalized)
      - 发放 (Payment):     steps 1-5  (payslips_generated → ... → paid)
    """
    calc_steps = [
        ("draft", t(lang, "progress.batch_draft")),
        ("calculated", t(lang, "progress.batch_calculated")),
        ("hr_reviewed", t(lang, "progress.batch_hr_reviewed")),
        ("finalized", t(lang, "progress.batch_finalized")),
    ]
    pay_steps = [
        ("payslips_generated", t(lang, "progress.batch_payslips_generated")),
        ("sent_to_employees", t(lang, "progress.batch_sent_to_employees")),
        ("employee_confirmed", t(lang, "progress.batch_employee_confirmed")),
        ("released_to_finance", t(lang, "progress.batch_released_to_finance")),
        ("paid", t(lang, "progress.batch_paid")),
    ]
    all_steps = calc_steps + pay_steps
    status_order = [s[0] for s in all_steps]
    # Map terminal/utility statuses
    if current_status == "correction":
        current_idx = -1
    elif current_status == "voided":
        current_idx = -1
    else:
        current_idx = status_order.index(current_status) if current_status in status_order else -1

    calc_label = {"zh": "核算", "ja": "計算", "en": "Calc"}.get(lang, "Calc")
    pay_label = {"zh": "发放", "ja": "支給", "en": "Pay"}.get(lang, "Pay")

    parts = ['<div class="progress-bar" style="flex-wrap:wrap;gap:2px">']
    # ── 核算 group (steps 1–4) ──
    parts.append(f'<span class="progress-label" style="font-size:.7rem;color:var(--muted);margin-right:4px;min-width:32px">{calc_label}</span>')
    for i, (key, label) in enumerate(calc_steps):
        if i > 0:
            line_class = "done" if i <= current_idx else ""
            parts.append(f'<div class="progress-line {line_class}"></div>')
        if i < current_idx:
            circle, cls = "✓", "done"
        elif i == current_idx:
            circle, cls = str(i + 1), "current"
        else:
            circle, cls = str(i + 1), "pending"
        parts.append(f'<div class="progress-step"><div class="progress-circle {cls}">{circle}</div><span class="progress-label {cls}">{label}</span></div>')
    # ── Divider ──
    parts.append('<div style="width:2px;height:28px;background:var(--line);margin:0 8px;flex-shrink:0"></div>')
    # ── 发放 group (steps 1–5, renumbered) ──
    parts.append(f'<span class="progress-label" style="font-size:.7rem;color:var(--muted);margin-right:4px;min-width:32px">{pay_label}</span>')
    pay_offset = len(calc_steps)
    for i, (key, label) in enumerate(pay_steps):
        global_i = pay_offset + i
        if i > 0:
            line_class = "done" if global_i <= current_idx else ""
            parts.append(f'<div class="progress-line {line_class}"></div>')
        if global_i < current_idx:
            circle, cls = "✓", "done"
        elif global_i == current_idx:
            circle, cls = str(i + 1), "current"   # renumbered: 1,2,3,4,5
        else:
            circle, cls = str(i + 1), "pending"
        parts.append(f'<div class="progress-step"><div class="progress-circle {cls}">{circle}</div><span class="progress-label {cls}">{label}</span></div>')
    parts.append('</div>')
    return ''.join(parts)



def monthly_sheet_detail_html(lang: str, sheet_id: str) -> str:
    """Detail view of a monthly salary sheet with employee records."""
    sheet = find_sheet(sheet_id)
    if not sheet:
        return "<div class='card'>Sheet not found.</div>"
    records = sheet_records(sheet_id)
    status = sheet.get("status", "draft")

    # Build action buttons based on status
    actions = []
    if status == "draft":
        actions.append(f"<a class='button' href='{with_lang('/monthly-sheets/review', lang, sheet_id=sheet_id)}'>{t(lang,'action.review_sheet')}</a>")
        confirm_msg = json.dumps(t(lang, 'msg.confirm_basic_info_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/confirm-basic-info', lang, sheet_id=sheet_id)}' onsubmit='return confirm({confirm_msg})'><button style='font-size:16px;min-width:180px'>{t(lang,'action.confirm_basic_info')}</button></form>")
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/void', lang, sheet_id=sheet_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.void_sheet_confirm'))})\"><button class='danger' style='font-size:12px'>{t(lang,'action.void_sheet')}</button></form>")
    elif status == "hr_confirmed":
        # Review button greyed out — data is locked after HR确认
        actions.append(f"<a class='button secondary' style='opacity:.5;pointer-events:none'>{t(lang,'action.review_sheet')} 🔒</a>")
        calc_modal_id = "calculate-sheet-modal"
        actions.append(f"""<form id="calculate-sheet-form" method='post' action='{with_lang('/monthly-sheets/calculate', lang)}' style='display:inline'><input type='hidden' name='sheet_id' value='{escape(sheet_id)}'><input type='hidden' name='selected_ids' value=''></form><button style='font-size:16px;min-width:180px' onclick="var ids=[];document.querySelectorAll('.calc-select:checked').forEach(function(c){{ids.push(c.name.replace('calc_',''))}});document.querySelector('#calculate-sheet-form [name=selected_ids]').value=ids.join(',');var cnt=ids.length;if(cnt===0){{document.getElementById('calculate-modal-count').textContent='{len(records)} (ALL)';}}else{{document.getElementById('calculate-modal-count').textContent=cnt;}}showConfirmModal('{calc_modal_id}')">{t(lang,'action.hr_calculate')}</button>""")
        return_msg = json.dumps(t(lang, 'msg.return_step_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/return-draft', lang, sheet_id=sheet_id)}' style='display:flex;gap:8px' onsubmit='return confirm({return_msg})'><input name='comment' placeholder='{t(lang, 'label.return_reason')}' style='min-width:200px' required><button class='secondary'>{t(lang,'action.return_to_draft')}</button></form>")
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/void', lang, sheet_id=sheet_id)}' onsubmit=\"return confirm({json.dumps(t(lang, 'msg.void_sheet_confirm'))})\"><button class='danger' style='font-size:12px'>{t(lang,'action.void_sheet')}</button></form>")
    elif status == "calculated":
        report_url = with_lang('/monthly-sheets/report', lang, sheet_id=sheet_id)
        actions.append(f"<a class='button' href='{report_url}' target='_blank' style='font-size:16px;min-width:180px;background:var(--blue);color:#fff'>📊 {t(lang,'action.view_report') if t(lang,'action.view_report') != 'action.view_report' else 'View Report / 查看报表'}</a>")
        hr_appr_msg = json.dumps(t(lang, 'msg.sheet_hr_approve_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/hr-approve', lang, sheet_id=sheet_id)}' onsubmit='return confirm({hr_appr_msg})'><button style='font-size:16px;min-width:180px'>{t(lang,'action.hr_approve')}</button></form>")
        return_msg = json.dumps(t(lang, 'msg.return_step_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/return-step', lang, sheet_id=sheet_id, to_status='hr_confirmed')}' style='display:flex;gap:8px' onsubmit='return confirm({return_msg})'><input name='comment' placeholder='{t(lang, 'label.return_reason')}' style='min-width:200px' required><button class='secondary'>{t(lang,'action.return_to_prev')} ← hr_confirmed</button></form>")
    elif status == "hr_reviewed":
        report_url = with_lang('/monthly-sheets/report', lang, sheet_id=sheet_id)
        actions.append(f"<a class='button' href='{report_url}' target='_blank' style='font-size:16px;min-width:180px;background:var(--blue);color:#fff'>📊 {t(lang,'action.view_report') if t(lang,'action.view_report') != 'action.view_report' else 'View Report / 查看报表'}</a>")
        send_mgr_msg = json.dumps(t(lang, 'msg.sheet_send_manager_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/send-manager-review', lang, sheet_id=sheet_id)}' onsubmit='return confirm({send_mgr_msg})'><button style='font-size:16px;min-width:180px'>{t(lang,'action.send_manager_review')}</button></form>")
        return_msg = json.dumps(t(lang, 'msg.return_step_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/return-step', lang, sheet_id=sheet_id, to_status='calculated')}' style='display:flex;gap:8px' onsubmit='return confirm({return_msg})'><input name='comment' placeholder='{t(lang, 'label.return_reason')}' style='min-width:200px' required><button class='secondary'>{t(lang,'action.return_to_prev')} ← calculated</button></form>")
    elif status == "manager_review":
        report_url = with_lang('/monthly-sheets/report', lang, sheet_id=sheet_id)
        actions.append(f"<a class='button' href='{report_url}' target='_blank' style='font-size:16px;min-width:180px;background:var(--blue);color:#fff'>📊 {t(lang,'action.view_report') if t(lang,'action.view_report') != 'action.view_report' else 'View Report / 查看报表'}</a>")
        # ── 批准定案 (Modal confirmation, default NO) ──
        approve_final_modal_id = "approve-finalize-modal"
        actions.append(f"""
        <div class="modal-overlay" id="{approve_final_modal_id}">
          <div class="modal-dialog">
            <div class="modal-body">
              <div class="modal-icon">⚠️</div>
              <p><strong>{t(lang, 'action.approve_finalize')}</strong></p>
              <p>{t(lang, 'msg.approve_finalize_confirm')}</p>
            </div>
            <div class="modal-footer">
              <button class="btn-no default-no" onclick="hideModal('{approve_final_modal_id}')" autofocus>{t(lang, 'msg.payslip_gen_modal_no')}</button>
              <button class="btn-yes" onclick="document.getElementById('approve-finalize-form').submit()">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
            </div>
          </div>
        </div>
        <form id="approve-finalize-form" method='post' action='{with_lang('/monthly-sheets/manager-approve', lang, sheet_id=sheet_id)}'>
          <input name='comment' placeholder='{t(lang, "label.comment_optional") if t(lang, "label.comment_optional") else "Comment (optional)"}' style='min-width:200px'>
        </form>
        <button class='danger' style='font-size:16px;min-width:180px' onclick="showConfirmModal('{approve_final_modal_id}')">{t(lang,'action.approve_finalize')}</button>
        """)
        # ── 经理退回 ──
        mgr_rej_msg = json.dumps(t(lang, 'msg.sheet_manager_reject_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/manager-reject', lang, sheet_id=sheet_id)}' style='display:flex;gap:8px' onsubmit='return confirm({mgr_rej_msg})'><input name='comment' placeholder='Rejection reason' style='min-width:200px'><button class='danger'>{t(lang,'action.manager_reject')}</button></form>")
        # ── HR-initiated return to hr_reviewed ──
        return_msg = json.dumps(t(lang, 'msg.return_step_confirm'))
        actions.append(f"<form method='post' action='{with_lang('/monthly-sheets/return-step', lang, sheet_id=sheet_id, to_status='hr_reviewed')}' style='display:flex;gap:8px' onsubmit='return confirm({return_msg})'><input name='comment' placeholder='{t(lang, 'label.return_reason')}' style='min-width:200px' required><button class='secondary'>{t(lang,'action.return_to_prev')} ← hr_reviewed</button></form>")
    elif status == "finalized":
        report_url = with_lang('/monthly-sheets/report', lang, sheet_id=sheet_id)
        actions.append(f"<a class='button' href='{report_url}' target='_blank' style='font-size:16px;min-width:180px;background:var(--blue);color:#fff'>📊 {t(lang,'action.view_report') if t(lang,'action.view_report') != 'action.view_report' else 'View Report / 查看报表'}</a>")
        # Release batch is auto-created by finalize_sheet(), always exists here
        release_id = next_release_id(sheet.get("payroll_month", ""), sheet.get("entity_id", ""), sheet.get("country_code", "SG"))
        release_batches = load_release_batches()
        existing_release = next((rb for rb in release_batches if rb.get("release_id") == release_id), None)
        if existing_release:
            release_link = f"<a class='button' href='{with_lang('/release/detail', lang, release_id=release_id)}' style='font-size:16px;min-width:200px'>{t(lang, 'action.enter_release')} →</a>"
            actions.append(release_link)

    # Batch set attendance (draft) / filter bar (hr_confirmed)
    batch_form = ""
    if status == "draft":
        batch_form = f"""
<div class="card"><div class="section-header"><h3>{t(lang,'action.batch_set_attendance')}</h3></div>
<form method="post" action="{with_lang('/monthly-sheets/batch-set-attendance', lang, sheet_id=sheet_id)}" class="sap-toolbar" onsubmit="return confirm({json.dumps(t(lang, 'msg.batch_set_attendance_confirm'))})">
  <div class="field" style="margin:0"><label>{t(lang,'label.actual_work_days')}</label><input name="work_days" value="{money_fmt(sheet.get('standard_work_days',22))}" style="width:100px"></div>
  <div class="field" style="margin:0"><label>{t(lang,'label.actual_work_hours')}</label><input name="work_hours" value="{money_fmt(sheet.get('standard_work_hours',176))}" style="width:100px"></div>
  <button class="secondary" style="margin-top:22px">{t(lang,'action.batch_set_attendance')}</button>
</form></div>"""

    # Build records table
    trs = []
    dept_set: dict[str, str] = {}
    team_set: dict[str, str] = {}
    for r in records:
        dept = r.get("department_label", "") or ""
        team = r.get("team_label", "") or ""
        if dept and dept not in dept_set: dept_set[dept] = slug(dept)
    # Gather filter values from records for dept/team
    for r in records:
        d = r.get("department_label", "") or ""
        tm = r.get("team_label", "") or ""
        if d and d not in dept_set: dept_set[d] = slug(d)
        if tm and tm not in team_set: team_set[tm] = slug(tm)
    dept_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(dept_set.items()))
    team_opts = "".join(f'<option value="{escape(s)}">{escape(l)}</option>' for l, s in sorted(team_set.items()))

    for r in records:
        dept = r.get("department_label", "") or ""
        team = r.get("team_label", "") or ""
        dept_display = f"{dept} / {team}" if team else dept
        calculated_info = ""
        if r.get("status") in ("calculated", "hr_adjusted"):
            calculated_info = f"<td class='right'>{money_fmt(r.get('base_pay_calculated'))}</td><td class='right'>{money_fmt(r.get('gross_pay'))}</td><td class='right'>{money_fmt(r.get('cpf_employee'))}</td><td class='right'>{money_fmt(r.get('deduction_total'))}</td><td class='right'><strong>{money_fmt(r.get('net_pay'))}</strong></td><td class='right'>{money_fmt(r.get('employer_cost_total'))}</td><td class='right'>{money_fmt(r.get('performance_bonus', 0))}</td><td class='right'>{money_fmt(r.get('other_payment', 0))}</td><td class='right'>{money_fmt(r.get('other_deduction', 0))}</td>"
        # Checkbox for hr_confirmed; editable link for draft
        chk = f"<td><input type='checkbox' class='calc-select' name='calc_{escape(r['record_id'])}' value='1' checked data-dept='{escape(slug(dept))}' data-team='{escape(slug(team))}' data-name='{escape(r['employee_name'].lower())}' data-number='{escape(r['employee_number'].lower())}' style='width:auto;min-width:auto'></td>" if status == "hr_confirmed" else ""
        if status in ("draft", "hr_confirmed"):
            emp_link = f"<a href='{with_lang('/monthly-records/edit', lang, record_id=r['record_id'])}'>{escape(r['employee_number'])}</a>"
        else:
            emp_link = f"<span>{escape(r['employee_number'])}</span>"
        trs.append(f"<tr class='data-row' data-dept='{escape(slug(dept))}' data-team='{escape(slug(team))}' data-name='{escape(r['employee_name'].lower())}' data-number='{escape(r['employee_number'].lower())}'>{chk}<td>{emp_link}</td><td>{escape(r['employee_name'])}</td><td>{escape(r.get('salary_type',''))}</td><td>{escape(dept_display)}</td><td class='right'>{money_fmt(r['basic_salary'])}</td><td class='right'>{money_fmt(r['standard_work_days'])}</td><td class='right'>{money_fmt(r['actual_work_days'])}</td><td class='right'>{money_fmt(r['actual_work_hours'])}</td><td class='right'>{money_fmt(r['paid_leave_days'])}</td><td class='right'>{money_fmt(r.get('sick_leave_days', 0))}</td><td class='right'>{money_fmt(r['overtime_hours'])}</td>{calculated_info}<td>{status_badge(r.get('manager_review_status','pending'))}</td></tr>")

    # Filter bar for hr_confirmed
    filter_bar = ""
    if status == "hr_confirmed":
        filter_bar = f"""
<div class="search-bar" style="margin-bottom:12px">
  <div class="field"><label>🔍 {t(lang,'label.employee')} / No.</label><input id="name-search" type="text" placeholder="输入姓名或工号筛选..." oninput="applyFilters()" style="min-width:160px"></div>
  <div class="field"><label>🏢 Dept</label><select id="dept-filter" onchange="applyFilters()"><option value="">-- All --</option>{dept_opts}</select></div>
  <div class="field"><label>👥 Team</label><select id="team-filter" onchange="applyFilters()"><option value="">-- All --</option>{team_opts}</select></div>
  <div class="field" style="max-width:70px"><label>&nbsp;</label><button type="button" class="secondary" style="font-size:11px;width:100%" onclick="clearFilters()">✕</button></div>
  <div class="field" style="max-width:120px"><label>&nbsp;</label><span id="sel-count" style="font-weight:800;color:var(--blue)">{len(records)} selected</span></div>
</div>"""

    calculated_header = ""
    if status in ("calculated", "hr_reviewed", "manager_review", "finalized"):
        calculated_header = f"<th>Base Pay</th><th>{t(lang,'label.gross')}</th><th>{t(lang,'label.cpf_employee')}</th><th>{t(lang,'label.deductions')}</th><th>{t(lang,'label.net')}</th><th>{t(lang,'label.employer_cost')}</th><th>Perf Bonus</th><th>Other Pay</th><th>Other Ded</th>"

    chk_header = "<th style='width:30px'><input type='checkbox' id='select-all' checked style='width:auto;min-width:auto' onclick=\"var c=this.checked;document.querySelectorAll('.calc-select').forEach(function(x){if(x.closest('.data-row').style.display!=='none')x.checked=c});updateSelCount()\"></th>" if status == "hr_confirmed" else ""
    table = f"<p class='muted'>{t(lang,'msg.no_records')}</p>" if not records else f"{filter_bar}<div class='table-scroll' style='max-width:100%;overflow-x:auto'><table id='detail-table' style='min-width:1600px;width:auto;white-space:nowrap'><thead><tr>{chk_header}<th>No.</th><th>{t(lang,'label.employee')}</th><th>Type</th><th>Dept/Team</th><th>Base Salary</th><th>Std Days</th><th>Work Days</th><th>Work Hrs</th><th>Pd Leave</th><th>Sick</th><th>OT</th>{calculated_header}<th>Review</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"

    # Version info
    version_info = ""
    if sheet.get("basic_info_confirmed_at"):
        version_info += f"<div class='metric-card'><div>Version 1 (Confirmed)</div><div class='value' style='font-size:16px'>{escape(sheet.get('basic_info_confirmed_at',''))}</div><div class='muted'>by {escape(sheet.get('basic_info_confirmed_by',''))}</div></div>"
    if sheet.get("calculated_at"):
        version_info += f"<div class='metric-card'><div>Version 2 (Calculated)</div><div class='value' style='font-size:16px'>{escape(sheet.get('calculated_at',''))}</div><div class='muted'>by {escape(sheet.get('calculated_by',''))}</div></div>"

    csv_batch_id = f'PAYSG-{sheet.get("payroll_month","").replace("-","")}-{slug(sheet.get("entity_id",""))}'
    entity_display = entity_label(sheet.get('entity_id', ''), lang)

    # Per-currency salary summary
    currency_totals = sheet.get("currency_totals") or {}
    if currency_totals:
        currency_cards = []
        for cur in sorted(currency_totals.keys()):
            ct = currency_totals[cur]
            employee_word = {"zh": "人", "ja": "人", "en": "emp"}.get(lang, "emp")
            currency_cards.append(
                f"<div class='metric-card'><div style='font-weight:600;color:var(--sap-accent)'>{escape(cur)}</div>"
                f"<div class='value' style='font-size:16px'>{t(lang,'label.gross')} {money_fmt(ct.get('gross'))} &nbsp;/&nbsp; {t(lang,'label.net')} {money_fmt(ct.get('net'))}</div>"
                f"<div class='muted'>{t(lang,'label.employer_cost')} {money_fmt(ct.get('employer_cost'))} &nbsp;·&nbsp; {ct.get('count',0)} {employee_word}</div>"
                f"</div>"
            )
        currency_summary = f"<div class='grid'>{''.join(currency_cards)}</div>"
    else:
        currency_summary = f"<div class='grid'><div class='metric-card'><div>{t(lang,'label.gross')}</div><div class='value'>{money_fmt(sheet.get('gross_total'))}</div></div><div class='metric-card'><div>{t(lang,'label.net')}</div><div class='value'>{money_fmt(sheet.get('net_total'))}</div></div><div class='metric-card'><div>{t(lang,'label.employer_cost')}</div><div class='value'>{money_fmt(sheet.get('employer_cost_total'))}</div></div><div class='metric-card'><div>Employees</div><div class='value'>{sheet.get('employee_count',0)}</div></div></div>"

    locked_banner = ""
    if status == "finalized":
        locked_banner = f"<div class='message-strip message-warning' style='margin-bottom:16px'><strong>🔒 {t(lang, 'label.locked')}</strong> — {t(lang, 'msg.sheet_locked')}</div>"

    progress_html = payroll_progress_bar(lang, status)

    # ── Calculation result summary card ──
    calc_summary_html = ""
    calc_summary = sheet.get("last_calculation_summary")
    if calc_summary and status in ("calculated", "hr_reviewed", "manager_review", "finalized"):
        total = calc_summary.get("total", 0)
        warn_count = calc_summary.get("warnings_count", 0)
        success_count = total - warn_count
        calc_ts = calc_summary.get("timestamp", "")[:19].replace("T", " ")
        warn_details = calc_summary.get("warning_details", [])
        # Build summary card
        summary_lines = []
        summary_lines.append(f'<div style="font-size:14px;margin-bottom:8px"><b>📊 计算结果摘要 / Calculation Summary</b> <span style="color:var(--muted);font-size:11px">({calc_ts})</span></div>')
        summary_lines.append(f'<div style="display:flex;gap:16px;flex-wrap:wrap;margin-bottom:8px">')
        summary_lines.append(f'<div class="metric-card" style="flex:1;min-width:120px"><div>总处理 / Total</div><div class="value">{total}</div></div>')
        if success_count > 0:
            summary_lines.append(f'<div class="metric-card" style="flex:1;min-width:120px"><div>✅ 计算成功 / Success</div><div class="value" style="color:var(--green)">{success_count}</div></div>')
        if warn_count > 0:
            summary_lines.append(f'<div class="metric-card" style="flex:1;min-width:120px"><div>⚠️ 需要注意 / Warnings</div><div class="value" style="color:var(--amber)">{warn_count}</div></div>')
        summary_lines.append(f'</div>')
        if warn_details:
            summary_lines.append(f'<details style="margin-top:8px"><summary style="cursor:pointer;color:var(--amber);font-weight:600">⚠️ 查看潜在问题明细 / View Warning Details ({warn_count} records)</summary>')
            summary_lines.append(f'<div class="table-scroll" style="margin-top:8px;max-height:300px"><table style="font-size:12px"><thead><tr><th>#</th><th>Name</th><th>Type</th><th>Warnings / 警告信息</th></tr></thead><tbody>')
            for i, wd in enumerate(warn_details, 1):
                name = escape(wd.get("employee_name", ""))
                stype = escape(wd.get("salary_type", ""))
                warns = "<br>".join(escape(w) for w in wd.get("warnings", []))
                summary_lines.append(f'<tr><td>{i}</td><td>{name}</td><td>{stype}</td><td style="color:var(--amber)">{warns}</td></tr>')
            summary_lines.append(f'</tbody></table></div></details>')
        calc_summary_html = f'<div class="card" style="border-left:4px solid var(--sap-accent)">{"".join(summary_lines)}</div>'

    return f"""
<div class="sap-page-header"><h1>{escape(sheet_id)}</h1><div class="sap-info-strip"><span>📅 {escape(sheet.get('payroll_month',''))}</span><span>🏢 {escape(entity_display)}</span><span>{status_badge(status)}</span><span>👥 {sheet.get('employee_count',0)} employees</span><span>v{sheet.get('version',1)}</span></div></div>
<div class="card">{progress_html}</div>
{locked_banner}
{currency_summary}
<div class="card"><div class="sap-toolbar" style="justify-content:space-between"><div style="display:flex;gap:8px;flex-wrap:wrap">{''.join(actions)}</div><a class="button secondary" href="{with_lang('/reports/payroll.csv', lang, batch_id=csv_batch_id)}">📥 Payroll CSV</a></div></div>
{calc_summary_html}
{batch_form}
<div class="card">{table}<div class="helper-text" style="margin-top:8px">{len(records)} record(s) total · {escape(sheet.get('attendance_source','manual'))} attendance</div></div>
{'''<script>
function applyFilters(){var nv=(document.getElementById("name-search")?.value||"").toLowerCase().trim();var dv=document.getElementById("dept-filter")?.value||"";var tv=document.getElementById("team-filter")?.value||"";var rows=document.querySelectorAll(".data-row");var vis=0;rows.forEach(function(r){var nm=r.getAttribute("data-name")||"";var nu=r.getAttribute("data-number")||"";var m=(!nv||nm.includes(nv)||nu.includes(nv))&&(!dv||r.getAttribute("data-dept")===dv)&&(!tv||r.getAttribute("data-team")===tv);r.style.display=m?"":"none";if(!m){var cb=r.querySelector(".calc-select");if(cb)cb.checked=false}if(m)vis++});var sc=document.getElementById("sel-count");if(sc)sc.textContent=vis+" visible";updateSelCount()}
function clearFilters(){var ns=document.getElementById("name-search");if(ns)ns.value="";var df=document.getElementById("dept-filter");if(df)df.value="";var tf=document.getElementById("team-filter");if(tf)tf.value="";applyFilters();document.querySelectorAll(".calc-select").forEach(function(cb){cb.checked=true});updateSelCount()}
function updateSelCount(){var sel=document.querySelectorAll(".calc-select:checked").length;var sc=document.getElementById("sel-count");if(sc)sc.textContent=sel+" selected"}
document.querySelectorAll(".calc-select").forEach(function(cb){cb.addEventListener("change",updateSelCount)});
</script>''' if status == "hr_confirmed" else ""}
<!-- Calculate Confirm Modal (Default No) -->
<div class="modal-overlay" id="calculate-sheet-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">🔢</div>
<p><strong>{t(lang, 'msg.calculate_modal_title')}</strong></p>
<p>{t(lang, 'msg.calculate_modal_body').replace('{count}', '<span class="modal-count" id="calculate-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no default-no" onclick="hideModal('calculate-sheet-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes" onclick="submitGenForm('calculate-sheet-form','calculate-sheet-modal')">{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
"""
def monthly_sheet_report_html(lang: str, sheet_id: str) -> str:
    """Clean HTML payroll report for review/approval reference.
    Shows all calculated data in a printer-friendly table with status badge and currency totals.
    Accessible from calculated, hr_reviewed, manager_review, and finalized statuses.
    """
    sheet = find_sheet(sheet_id)
    if not sheet:
        return "<div class='card'>Sheet not found.</div>"
    records = sheet_records(sheet_id)
    status = sheet.get("status", "draft")
    entity_display = entity_label(sheet.get("entity_id", ""), lang)
    payroll_month = sheet.get("payroll_month", "")

    # Build type-aware table
    trs = []
    for r in records:
        dept = r.get("department_label", "") or ""
        team = r.get("team_label", "") or ""
        dept_display = f"{dept} / {team}" if team else dept
        st = r.get("salary_type", "monthly")
        # Calculated info (show for calculated/hr_adjusted records)
        if r.get("status") in ("calculated", "hr_adjusted"):
            calc_cells = (
                f"<td class='right'>{money_fmt(r.get('base_pay_calculated'))}</td>"
                f"<td class='right'>{money_fmt(r.get('gross_pay'))}</td>"
                f"<td class='right'>{money_fmt(r.get('cpf_employee'))}</td>"
                f"<td class='right'>{money_fmt(r.get('deduction_total'))}</td>"
                f"<td class='right'><strong>{money_fmt(r.get('net_pay'))}</strong></td>"
                f"<td class='right'>{money_fmt(r.get('employer_cost_total'))}</td>"
                f"<td class='right'>{money_fmt(r.get('performance_bonus', 0))}</td>"
                f"<td class='right'>{money_fmt(r.get('other_payment', 0))}</td>"
                f"<td class='right'>{money_fmt(r.get('other_deduction', 0))}</td>"
            )
        else:
            calc_cells = "<td colspan='9' class='muted' style='text-align:center'>— 尚未计算 / Not yet calculated —</td>"
        trs.append(
            f"<tr>"
            f"<td>{escape(r.get('employee_number', ''))}</td>"
            f"<td>{escape(r.get('employee_name', ''))}</td>"
            f"<td>{escape(st)}</td>"
            f"<td>{escape(dept_display)}</td>"
            f"<td class='right'>{money_fmt(r.get('basic_salary'))}</td>"
            f"<td class='right'>{money_fmt(r.get('hourly_rate'))}</td>"
            f"<td class='right'>{money_fmt(r.get('daily_rate'))}</td>"
            f"<td class='right'>{money_fmt(r.get('standard_work_days'))}</td>"
            f"<td class='right'>{money_fmt(r.get('actual_work_days'))}</td>"
            f"<td class='right'>{money_fmt(r.get('actual_work_hours'))}</td>"
            f"<td class='right'>{money_fmt(r.get('paid_leave_days'))}</td>"
            f"<td class='right'>{money_fmt(r.get('sick_leave_days', 0))}</td>"
            f"<td class='right'>{money_fmt(r.get('overtime_hours'))}</td>"
            f"{calc_cells}"
            f"<td>{escape(r.get('payroll_currency', 'SGD'))}</td>"
            f"</tr>"
        )

    table_html = (
        f"<div class='table-scroll' style='max-width:100%;overflow-x:auto'>"
        f"<table style='min-width:1500px;width:auto;white-space:nowrap;font-size:12px'>"
        f"<thead><tr>"
        f"<th>No.</th><th>Name</th><th>Type</th><th>Dept/Team</th>"
        f"<th>Base Salary</th><th>Hourly Rate</th><th>Daily Rate</th>"
        f"<th>Std Days</th><th>Work Days</th><th>Work Hrs</th>"
        f"<th>Pd Leave</th><th>Sick</th><th>OT</th>"
        f"<th>Base Pay</th><th>Gross</th><th>CPF</th><th>Deductions</th><th>Net</th><th>Emp Cost</th>"
        f"<th>Perf Bonus</th><th>Other Pay</th><th>Other Ded</th>"
        f"<th>Currency</th>"
        f"</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    ) if records else "<p class='muted'>No records.</p>"

    # Currency totals
    currency_totals = sheet.get("currency_totals") or {}
    if currency_totals:
        cur_cards = []
        for cur in sorted(currency_totals.keys()):
            ct = currency_totals[cur]
            cur_cards.append(
                f"<div class='metric-card' style='flex:1;min-width:140px'>"
                f"<div style='font-weight:600;color:var(--sap-accent)'>{escape(cur)}</div>"
                f"<div class='value' style='font-size:14px'>Gross {money_fmt(ct.get('gross'))} / Net {money_fmt(ct.get('net'))}</div>"
                f"<div class='muted'>Emp Cost {money_fmt(ct.get('employer_cost'))} · {ct.get('count',0)} emp</div>"
                f"</div>"
            )
        currency_html = f"<div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px'>{''.join(cur_cards)}</div>"
    else:
        currency_html = (
            f"<div style='display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px'>"
            f"<div class='metric-card'><div>Gross</div><div class='value'>{money_fmt(sheet.get('gross_total'))}</div></div>"
            f"<div class='metric-card'><div>Net</div><div class='value'>{money_fmt(sheet.get('net_total'))}</div></div>"
            f"<div class='metric-card'><div>Employer Cost</div><div class='value'>{money_fmt(sheet.get('employer_cost_total'))}</div></div>"
            f"<div class='metric-card'><div>Employees</div><div class='value'>{sheet.get('employee_count', 0)}</div></div>"
            f"</div>"
        )

    back_url = with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id)

    return f"""
<style>
@media print{{
  body{{background:white;margin:0;padding:0}}
  .site-header,.primary-nav,.report-toolbar{{display:none!important}}
  .report-card{{box-shadow:none;border:1px solid #ccc}}
}}
.report-toolbar{{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:12px}}
</style>
<div class="sap-page-header">
  <h1>📊 Payroll Report / 工资报表</h1>
  <div class="sap-info-strip">
    <span>📅 {escape(payroll_month)}</span>
    <span>🏢 {escape(entity_display)}</span>
    <span>{status_badge(status)}</span>
    <span>👥 {sheet.get('employee_count', 0)} employees</span>
    <span>v{sheet.get('version', 1)}</span>
  </div>
</div>
<div class="report-toolbar">
  <a class="button secondary" href="{back_url}">← Back to Sheet / 返回工资表</a>
  <button class="button secondary" onclick="window.print()">🖨️ Print / 打印</button>
</div>
{currency_html}
<div class="card report-card">
  {table_html}
  <div class='helper-text' style='margin-top:8px'>{len(records)} record(s) total</div>
</div>
"""


def monthly_sheet_review_html(lang: str, sheet_id: str) -> str:
    """Bulk edit page for monthly salary records — review & input key data (attendance, allowance, etc.)."""
    sheet = find_sheet(sheet_id)
    if not sheet:
        return "<div class='card'>Sheet not found.</div>"
    records = sheet_records(sheet_id)
    status = sheet.get("status", "draft")
    # Only draft and hr_confirmed are editable; calculated and beyond are read-only
    is_editable = status in ("draft", "hr_confirmed")
    readonly_attr = "" if is_editable else "readonly"
    locked_note = "" if is_editable else f"<div class='message-strip warn'>Sheet status is <b>{escape(status)}</b> — data is locked. Return to draft to modify. / 工资表状态为 <b>{escape(status)}</b>，数据已锁定，如需修改请先退回draft。</div>"

    # Editable fields definition: (field_key, display_label_zh, display_label_en, width, category)
    # Categories: "attendance"=high-freq yellow, "allowance"=medium-freq green, "deduction"=amber
    editable_fields = [
        # ── High frequency: attendance & core pay ──
        ("actual_work_days", "出勤天数", "Work Days", "70", "attendance"),
        ("actual_work_hours", "出勤小时", "Work Hours", "70", "attendance"),
        ("overtime_hours", "加班小时", "OT Hours", "70", "attendance"),
        ("paid_leave_days", "带薪假", "Paid Leave", "65", "attendance"),
        ("sick_leave_days", "病假", "Sick Leave", "65", "attendance"),
        ("unpaid_leave_days", "无薪假", "Unpaid Leave", "65", "attendance"),
        # ── Medium frequency: allowances & bonuses ──
        ("performance_bonus", "绩效工资", "Perf Bonus", "90", "allowance"),
        ("fixed_allowance", "固定津贴", "Allowance", "90", "allowance"),
        ("other_payment", "其他支付", "Other Pay", "90", "allowance"),
        ("bonus", "奖金", "Bonus", "85", "allowance"),
        # ── Deductions (excluding CPF — most SG consultants have no CPF) ──
        ("other_deduction", "其他扣除", "Other Ded", "90", "deduction"),
        ("income_tax", "所得税", "Income Tax", "85", "deduction"),
        ("recurring_deductions", "固定扣除", "Recur Ded", "85", "deduction"),
        # ── Rarely used: extra attendance ──
        ("late_night_hours", "深夜小时", "Late Night", "65", "attendance"),
        ("holiday_hours", "假日小时", "Holiday Hrs", "65", "attendance"),
        ("absence_days", "缺勤天数", "Absence", "65", "attendance"),
    ]

    # ── Gather unique filter values ──
    dept_set: dict[str, str] = {}
    team_set: dict[str, str] = {}
    for r in records:
        dept = r.get("department_label", "")
        team = r.get("team_label", "")
        if dept and dept not in dept_set:
            dept_set[dept] = slug(dept)
        if team and team not in team_set:
            team_set[team] = slug(team)
        label = f"{dept} / {team}" if team else dept
        if label and label not in dept_set:
            dept_set[label] = slug(label)
    dept_options = "".join(f'<option value="{escape(slug)}">{escape(label)}</option>' for label, slug in sorted(dept_set.items(), key=lambda x: x[0].lower()))
    team_options = "".join(f'<option value="{escape(slug)}">{escape(label)}</option>' for label, slug in sorted(team_set.items(), key=lambda x: x[0].lower()))

    # ── Build table rows ──
    trs = []
    missing_data_count = 0
    for idx, r in enumerate(records):
        dept = r.get("department_label", "")
        team = r.get("team_label", "")
        # Extract short codes: "TECH - Technical Department" → "TECH", "SAAS - SAAS engineering" → "SAAS"
        dept_short = dept.split(" - ")[0].strip() if " - " in dept else dept
        team_short = team.split(" - ")[0].strip() if " - " in team else team
        dept_label = f"{dept_short} / {team_short}" if team_short else dept_short
        dept_slug = slug(dept_label)
        team_slug = slug(team_short)
        dept_only_slug = slug(dept)
        detail_url = with_lang("/monthly-records/edit", lang, record_id=r["record_id"])

        # ── Smart validation: detect missing critical data per salary type ──
        st = r.get("salary_type", "monthly")
        basic_salary = money(r.get("basic_salary", 0))
        hourly_rate = money(r.get("hourly_rate", 0))
        daily_rate = money(r.get("daily_rate", 0))
        actual_days = money(r.get("actual_work_days", 0))
        actual_hours = money(r.get("actual_work_hours", 0))
        missing_fields = []
        if st == "monthly" and basic_salary <= 0:
            missing_fields.append("月薪为0/空")
        if st == "hourly" and (hourly_rate <= 0 or actual_hours <= 0):
            if hourly_rate <= 0: missing_fields.append("小时单价为0/空")
            if actual_hours <= 0: missing_fields.append("出勤小时为0")
        if st == "daily" and (daily_rate <= 0 or actual_days <= 0):
            if daily_rate <= 0: missing_fields.append("日薪单价为0/空")
            if actual_days <= 0: missing_fields.append("出勤天数为0")
        if st == "monthly_hour" and actual_hours <= 0:
            missing_fields.append("出勤小时为0")
        has_missing = len(missing_fields) > 0
        if has_missing:
            missing_data_count += 1
        missing_label = "; ".join(missing_fields) if missing_fields else ""
        row_class = "data-row missing-data" if has_missing else "data-row"
        row_style = "background:#FFF9C4" if has_missing else ""  # Yellow highlight for missing data

        cells = []
        # Checkbox (sticky)
        cells.append(f"<td class='sticky-col' style='left:0;background:{'#FFF9C4' if has_missing else '#fff'}'><input type='checkbox' class='row-select' data-dept='{escape(dept_only_slug)}' data-team='{escape(team_slug)}' data-name='{escape(r['employee_name'].lower())}' data-number='{escape(r['employee_number'].lower())}' style='width:auto;min-width:auto'></td>")
        # Fixed info (sticky)
        sticky_bg = "#FFF9C4" if has_missing else "#fff"
        cells.append(f"<td class='sticky-col fixed-cell' style='left:34px;background:{sticky_bg}'><a class='detail-link' href='{detail_url}' target='_blank' title='{t(lang, 'action.detail_edit')}'>{escape(r['employee_number'])}</a></td>")
        cells.append(f"<td class='sticky-col fixed-cell name-cell' style='left:114px;background:{sticky_bg}' title='{escape(missing_label)}'>{escape(r['employee_name'])}</td>")
        cells.append(f"<td class='fixed-cell'>{escape(dept_short)}</td>")
        cells.append(f"<td class='fixed-cell'>{escape(team_short)}</td>")
        cells.append(f"<td class='fixed-cell'>{escape(r.get('salary_type',''))}</td>")
        cells.append(f"<td class='fixed-cell right'>{money_fmt(basic_salary)}</td>")
        cells.append(f"<td class='fixed-cell right' style='color:var(--muted)'>{money_fmt(hourly_rate)}</td>")
        cells.append(f"<td class='fixed-cell right' style='color:var(--muted)'>{money_fmt(daily_rate)}</td>")
        # Standard work days (attendance field)
        std_days_val = money_fmt(r.get('standard_work_days', sheet.get('standard_work_days', 22)))
        std_days_attrs = attendance_input_attrs("standard_work_days", r.get('salary_type', 'monthly'), not is_editable)
        cells.append(f"<td><input name='standard_work_days_{r['record_id']}' value='{std_days_val}' style='width:60px;min-width:60px;text-align:right;padding:4px 6px;font-size:13px' class='grid-input' {std_days_attrs}></td>")
        # Editable fields with category-based hint colors
        for field_key, _, _, width, category in editable_fields:
            val = money_fmt(r.get(field_key, 0))
            if category == "attendance":
                field_attrs = attendance_input_attrs(field_key, r.get('salary_type', 'monthly'), not is_editable)
            elif not is_editable:
                field_attrs = "readonly style='background:#F5F5F5;color:#BDBDBD;cursor:not-allowed'"
            elif category == "allowance":
                field_attrs = "style='background:#E8F5E9;font-weight:600;border-color:#43A047'"
            elif category == "deduction":
                field_attrs = "style='background:#FFF3E0;font-weight:600;border-color:#EF6C00'"
            else:
                field_attrs = readonly_attr
            cells.append(f"<td><input name='{field_key}_{r['record_id']}' value='{val}' style='width:{width}px;min-width:{width}px;text-align:right;padding:4px 6px;font-size:13px' class='grid-input' {field_attrs}></td>")
        # Currency
        cur_val = r.get("payroll_currency", "SGD")
        cur_opts = "".join(f"<option value='{c}' {'selected' if c == cur_val else ''}>{escape(c)}</option>" for c in SUPPORTED_CURRENCIES)
        cur_select = f"<td><select name='payroll_currency_{r['record_id']}' style='width:72px;min-width:72px;padding:3px 4px;font-size:12px' class='grid-input' {readonly_attr}>{cur_opts}</select></td>" if is_editable else f"<td class='fixed-cell'>{escape(cur_val)}</td>"
        cells.append(cur_select)
        trs.append(f"<tr class='{row_class}' style='{row_style}' data-dept='{escape(dept_only_slug)}' data-team='{escape(team_slug)}' data-name='{escape(r['employee_name'].lower())}' data-number='{escape(r['employee_number'].lower())}' data-missing='{'1' if has_missing else '0'}'>{''.join(cells)}</tr>")

    if not records:
        tr_html = f"<p class='muted'>{t(lang,'msg.no_records')}</p>"
    else:
        header_cells = "<th class='sticky-col' style='width:30px;left:0;z-index:4;background:#f1f5f9'><input type='checkbox' id='select-all' title='Select/Deselect All' style='width:auto;min-width:auto'></th><th class='sticky-col' style='left:34px;z-index:4;background:#f1f5f9'>No.</th><th class='sticky-col' style='left:114px;z-index:4;background:#f1f5f9'>Name</th><th>Dept</th><th>Team</th><th>Type</th><th>Basic<br>Salary</th><th>Hourly<br>Rate</th><th>Daily<br>Rate</th><th>Std Days</th>"
        # Section group headers with color-coded backgrounds
        group_header = ("<tr style='font-size:10px;text-align:center;font-weight:700;text-transform:uppercase;letter-spacing:.05em'>"
            "<td colspan='10' style='background:#fff;position:sticky;left:0;z-index:3'></td>"
            "<td colspan='6' style='background:#FFFDE7;color:#F9A825;border-bottom:2px solid #F9A825'>📋 Attendance / 考勤</td>"
            "<td colspan='4' style='background:#E8F5E9;color:#43A047;border-bottom:2px solid #43A047'>💰 Allowances / 津贴奖金</td>"
            "<td colspan='3' style='background:#FFF3E0;color:#EF6C00;border-bottom:2px solid #EF6C00'>📉 Deductions / 扣除</td>"
            "<td style='background:#fff'></td></tr>")
        for _, label_zh, label_en, _, _ in editable_fields:
            header_cells += f"<th>{escape(label_zh)}<br><small>{escape(label_en)}</small></th>"
        header_cells += "<th>Currency<br><small>币种</small></th>"
        tr_html = f"<div class='table-scroll' style='max-height:65vh'><table id='review-table'><thead>{group_header}<tr>{header_cells}</tr></thead><tbody>{''.join(trs)}</tbody></table></div>"

    back_url = with_lang('/monthly-sheets/detail', lang, sheet_id=sheet_id)
    list_url = with_lang('/monthly-sheets', lang)
    save_btn_html = ""
    if is_editable:
        rec_count = len(records)
        save_label = t(lang, 'action.save')
        save_btn_html = f"<button type='button' style='font-size:16px;min-width:200px;min-height:48px' onclick=\"document.getElementById('review-save-modal-count').textContent={rec_count};showConfirmModal('review-save-modal')\">{save_label} ({rec_count} records)</button>"

    # ── Search bar + Batch operations panel ──
    search_batch_html = ""
    if is_editable:
        std_days_default = money_fmt(sheet.get('standard_work_days', 22))
        std_hours_default = money_fmt(sheet.get('standard_work_hours', 176))
        search_batch_html = f"""
<div class="search-bar">
  <div class="field">
    <label>🔍 {t(lang, 'label.employee')} / No. — 模糊搜索</label>
    <input id="name-search" type="text" placeholder="输入姓名或工号筛选..." oninput="applyAllFilters()" style="min-width:180px">
  </div>
  <div class="field">
    <label>🏢 {t(lang, 'label.department') if lang == 'zh' else ('Department' if lang == 'en' else '部署')}</label>
    <select id="dept-filter" onchange="applyAllFilters()">
      <option value="">-- {t(lang,'label.all') if lang == 'zh' else ('All' if lang == 'en' else '全て')} --</option>
      {dept_options}
    </select>
  </div>
  <div class="field">
    <label>👥 Team / 团队</label>
    <select id="team-filter" onchange="applyAllFilters()">
      <option value="">-- {t(lang,'label.all') if lang == 'zh' else ('All' if lang == 'en' else '全て')} --</option>
      {team_options}
    </select>
  </div>
  <div class="field" style="max-width:80px">
    <label>&nbsp;</label>
    <button type="button" class="secondary" style="font-size:12px;width:100%" onclick="clearFilters()">✕ 清除</button>
  </div>
  <div class="field" style="max-width:140px">
    <label>⚠️ 数据缺失</label>
    <button type="button" id="missing-filter-btn" class="secondary" style="font-size:12px;width:100%;background:#FFF9C4;border-color:#F9A825" onclick="toggleMissingFilter()">📌 显示缺失 ({missing_data_count})</button>
  </div>
</div>
<div class="batch-panel">
  <div class="field">
    <label style="font-size:11px">📋 出勤天数</label>
    <input id="batch-work-days" type="number" step="0.5" value="{std_days_default}">
  </div>
  <div class="field">
    <label style="font-size:11px">📋 出勤小时</label>
    <input id="batch-work-hours" type="number" step="0.5" value="{std_hours_default}">
  </div>
  <div class="field">
    <label style="font-size:11px">📋 满勤天数</label>
    <input id="batch-std-days" type="number" step="0.5" value="{std_days_default}">
  </div>
  <div class="btn-group">
    <button type="button" class="btn-sm" onclick="applyToSelected('actual_work_days',document.getElementById('batch-work-days').value)" title="设置选中行的出勤天数">出勤 = 设定值</button>
    <button type="button" class="btn-sm secondary" onclick="applyToSelected('actual_work_hours',document.getElementById('batch-work-hours').value)" title="设置选中行的出勤小时">工时 = 设定值</button>
    <button type="button" class="btn-sm secondary" onclick="applyToSelected('standard_work_days',document.getElementById('batch-std-days').value)" title="设置选中行的满勤天数">满勤 = 设定值</button>
  </div>
  <span style="color:var(--line)">|</span>
  <div class="btn-group">
    <button type="button" class="btn-sm secondary" onclick="applyToSelected('actual_work_days',document.getElementById('batch-std-days').value)" title="出勤天数 = 满勤天数（全勤）">出勤 = 满勤</button>
    <button type="button" class="btn-sm secondary" onclick="applyToSelected('actual_work_hours',document.getElementById('batch-work-hours').value);applyToSelected('overtime_hours','0');applyToSelected('late_night_hours','0');applyToSelected('holiday_hours','0')" title="按设定值设出勤小时，清零加班">快速全勤</button>
  </div>
  <span style="color:var(--line)">|</span>
  <div class="btn-group">
    <button type="button" class="btn-sm secondary" style="background:#fef2f2;border-color:#fca5a5;color:var(--red)" onclick="applyToSelected('overtime_hours','0');applyToSelected('paid_leave_days','0');applyToSelected('unpaid_leave_days','0');applyToSelected('absence_days','0');applyToSelected('late_night_hours','0');applyToSelected('holiday_hours','0')">清零考勤</button>
    <button type="button" class="btn-sm secondary" style="background:#fef2f2;border-color:#fca5a5;color:var(--red)" onclick="applyToSelected('fixed_allowance','0');applyToSelected('performance_bonus','0');applyToSelected('bonus','0');applyToSelected('other_payment','0');applyToSelected('recurring_deductions','0');applyToSelected('other_deduction','0');applyToSelected('income_tax','0')">清零调整</button>
  </div>
</div>
<div class="helper-text" style="margin-bottom:8px">💡 勾选行 → 点击批量按钮应用。支持按姓名/工号模糊搜索 + 部门/团队筛选。点击工号进入明细编辑。</div>"""

    entity_display = entity_label(sheet.get('entity_id', ''), lang)

    # JavaScript for combined search, filters, batch operations, keyboard nav
    js_script = f"""
<script>
var missingFilterOn = false;
// ── Combined filter function ──
function applyAllFilters() {{
  var nameVal = (document.getElementById('name-search')?.value || '').toLowerCase().trim();
  var deptVal = document.getElementById('dept-filter')?.value || '';
  var teamVal = document.getElementById('team-filter')?.value || '';
  var rows = document.querySelectorAll('.data-row');
  var visibleCount = 0;
  rows.forEach(function(r) {{
    var name = r.getAttribute('data-name') || '';
    var number = r.getAttribute('data-number') || '';
    var dept = r.getAttribute('data-dept') || '';
    var team = r.getAttribute('data-team') || '';
    var isMissing = r.getAttribute('data-missing') === '1';
    var nameMatch = !nameVal || name.includes(nameVal) || number.includes(nameVal);
    var deptMatch = !deptVal || dept === deptVal;
    var teamMatch = !teamVal || team === teamVal;
    var missingMatch = !missingFilterOn || isMissing;
    if (nameMatch && deptMatch && teamMatch && missingMatch) {{
      r.style.display = '';
      visibleCount++;
    }} else {{
      r.style.display = 'none';
      r.querySelector('.row-select').checked = false;
    }}
  }});
  updateSelectAll();
  document.getElementById('visible-count').textContent = visibleCount;
}}

function clearFilters() {{
  var ns = document.getElementById('name-search'); if (ns) ns.value = '';
  var df = document.getElementById('dept-filter'); if (df) df.value = '';
  var tf = document.getElementById('team-filter'); if (tf) tf.value = '';
  missingFilterOn = false;
  var mfb = document.getElementById('missing-filter-btn');
  if(mfb){{ mfb.textContent = '📌 显示缺失 ({missing_data_count})'; mfb.style.background='#FFF9C4'; }}
  applyAllFilters();
}}

// Toggle missing data filter
function toggleMissingFilter() {{
  missingFilterOn = !missingFilterOn;
  var btn = document.getElementById('missing-filter-btn');
  if(missingFilterOn) {{
    btn.textContent = '📌 仅显示缺失 (ON)';
    btn.style.background = '#FFCC80';
    btn.style.borderColor = '#EF6C00';
  }} else {{
    btn.textContent = '📌 显示缺失 ({missing_data_count})';
    btn.style.background = '#FFF9C4';
    btn.style.borderColor = '#F9A825';
  }}
  applyAllFilters();
}}

// Select / Deselect All
document.getElementById('select-all').addEventListener('change', function() {{
  var vis = getVisibleRows();
  vis.forEach(function(r) {{ r.querySelector('.row-select').checked = this.checked; }}.bind(this));
}});

function getVisibleRows() {{
  var all = document.querySelectorAll('.data-row');
  var vis = [];
  all.forEach(function(r) {{ if (r.style.display !== 'none') vis.push(r); }});
  return vis;
}}

function getSelectedRows() {{
  var checks = document.querySelectorAll('.row-select:checked');
  var rows = [];
  checks.forEach(function(c) {{
    var tr = c.closest('.data-row');
    if (tr && tr.style.display !== 'none') rows.push(tr);
  }});
  return rows;
}}

function updateSelectAll() {{
  var vis = getVisibleRows();
  var sel = getSelectedRows();
  document.getElementById('select-all').checked = vis.length > 0 && sel.length === vis.length;
  document.getElementById('select-all').indeterminate = sel.length > 0 && sel.length < vis.length;
}}

// Listen for checkbox changes
document.querySelectorAll('.row-select').forEach(function(cb) {{
  cb.addEventListener('change', updateSelectAll);
}});

// Apply value to selected rows (or all visible if none selected)
function applyToSelected(field, val) {{
  var sel = getSelectedRows();
  var targets = sel.length > 0 ? sel : getVisibleRows();
  targets.forEach(function(tr) {{
    var inputs = tr.querySelectorAll('input[name^=' + field + '_]');
    inputs.forEach(function(inp) {{ inp.value = val; }});
  }});
}}

// Keyboard navigation: arrow keys move between grid-input fields
document.addEventListener('keydown', function(e) {{
  if (!e.target.classList.contains('grid-input')) return;
  var cell = e.target.closest('td');
  if (!cell) return;
  var row = cell.closest('tr');
  if (!row) return;
  var table = document.getElementById('review-table');
  if (!table) return;

  var allRows = Array.from(table.querySelectorAll('tbody .data-row')).filter(function(r) {{ return r.style.display !== 'none'; }});
  var rowIdx = allRows.indexOf(row);
  if (rowIdx < 0) return;

  var cells = Array.from(row.querySelectorAll('td'));
  var colIdx = cells.indexOf(cell);

  switch(e.key) {{
    case 'ArrowUp':
      e.preventDefault();
      if (rowIdx > 0) {{
        var prevCells = allRows[rowIdx-1].querySelectorAll('td');
        if (prevCells[colIdx]) {{
          var inp = prevCells[colIdx].querySelector('input.grid-input');
          if (inp) {{ inp.focus(); inp.select(); }}
        }}
      }}
      break;
    case 'ArrowDown':
      e.preventDefault();
      if (rowIdx < allRows.length - 1) {{
        var nextCells = allRows[rowIdx+1].querySelectorAll('td');
        if (nextCells[colIdx]) {{
          var inp = nextCells[colIdx].querySelector('input.grid-input');
          if (inp) {{ inp.focus(); inp.select(); }}
        }}
      }}
      break;
    case 'ArrowLeft':
      if (e.target.selectionStart === 0 && colIdx > 0) {{
        e.preventDefault();
        for (var i = colIdx-1; i >= 0; i--) {{
          var inp = cells[i].querySelector('input.grid-input');
          if (inp) {{ inp.focus(); inp.select(); break; }}
        }}
      }}
      break;
    case 'ArrowRight':
      if (e.target.selectionStart === e.target.value.length && colIdx < cells.length - 1) {{
        e.preventDefault();
        for (var i = colIdx+1; i < cells.length; i++) {{
          var inp = cells[i].querySelector('input.grid-input');
          if (inp) {{ inp.focus(); inp.select(); break; }}
        }}
      }}
      break;
    case 'Tab':
      // Tab works naturally but we ensure Shift+Tab goes to prev editable cell
      break;
  }}
}});
</script>"""

    return f"""
<div class="sap-page-header"><h1>{t(lang,'action.review_sheet')} — {escape(sheet_id)}</h1><div class="sap-info-strip"><span>📅 {escape(sheet.get('payroll_month',''))}</span><span>🏢 {escape(entity_display)}</span><span>{status_badge(status)}</span><span>👁️ Visible: <strong id="visible-count">{len(records)}</strong> / {len(records)}</span></div></div>
<div class="card">
<div class="sap-toolbar" style="justify-content:space-between">
  <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center">
    <a class="button secondary" href="{list_url}">← {t(lang,'nav.monthly_sheets')}</a>
    <a class="button secondary" href="{back_url}">{t(lang,'label.status')} Detail</a>
  </div>
  <span class="muted" style="font-size:12px">{'✏️ Edit attendance & payroll fields → Save All. ↑↓←→ to navigate cells.' if is_editable else '🔒 Read-only — sheet is locked.'}</span>
</div>
{locked_note}
<div class="color-legend" style="display:flex;gap:16px;flex-wrap:wrap;padding:8px 12px;background:#fafbfc;border-radius:8px;margin-bottom:8px;font-size:11px;align-items:center">
  <span style="font-weight:600;color:var(--muted)">字段提示 / Legend:</span>
  <span style="background:#FFFDE7;padding:2px 8px;border-radius:4px;border:1px solid #F9A825">🟡 考勤字段 (Attendance)</span>
  <span style="background:#E8F5E9;padding:2px 8px;border-radius:4px;border:1px solid #43A047">🟢 津贴奖金 (Allowances)</span>
  <span style="background:#FFF3E0;padding:2px 8px;border-radius:4px;border:1px solid #EF6C00">🟠 扣除项 (Deductions)</span>
  <span style="background:#F5F5F5;padding:2px 8px;border-radius:4px;border:1px solid #BDBDBD;color:#BDBDBD">⬜ 只读/不适用 (Read-only)</span>
</div>
{search_batch_html}
<form id="review-save-form" method="post" action="{with_lang('/monthly-sheets/review-save', lang, sheet_id=sheet_id)}">
{tr_html}
<div class='helper-text' style='margin-top:8px'><span id="visible-count">{len(records)}</span> / {len(records)} record(s) visible</div>
<div class="sap-toolbar end" style="margin-top:16px">
  <a class="button secondary" href="{back_url}">{t(lang,'action.cancel')}</a>
  {save_btn_html}
</div>
</form>
<!-- Review Save Confirm Modal (Default Yes) -->
<div class="modal-overlay" id="review-save-modal">
<div class="modal-dialog">
<div class="modal-body">
<div class="modal-icon">💾</div>
<p><strong>{t(lang, 'msg.review_save_modal_title')}</strong></p>
<p>{t(lang, 'msg.review_save_modal_body').replace('{count}', '<span class="modal-count" id="review-save-modal-count">0</span>')}</p>
</div>
<div class="modal-footer">
<button class="btn-no" onclick="hideModal('review-save-modal')">{t(lang, 'msg.payslip_gen_modal_no')}</button>
<button class="btn-yes default-yes" onclick="submitGenForm('review-save-form','review-save-modal')" autofocus>{t(lang, 'msg.payslip_gen_modal_yes')}</button>
</div></div></div>
</div>
{js_script}"""


def monthly_record_form_html(lang: str, record_id: str) -> str:
    """Edit form for a single monthly salary record (attendance + inputs)."""
    record = next((r for r in load_monthly_records() if r.get("record_id") == record_id), None)
    if not record:
        return "<div class='card'>Record not found.</div>"

    sheet = find_sheet(record.get("sheet_id", ""))
    is_locked = sheet and sheet.get("status") not in ("draft",)

    readonly_attr = "readonly" if is_locked else ""
    locked_note = ""
    if is_locked:
        locked_note = f"<div class='message-strip warn'>Attendance is locked because sheet status is <b>{escape(sheet.get('status',''))}</b>. Return to draft to modify.</div>"

    attendance_fields = [
        # High frequency: core attendance
        ("actual_work_days", "出勤天数", "Work Days", "attendance"),
        ("actual_work_hours", "出勤小时", "Work Hours", "attendance"),
        ("overtime_hours", "加班小时", "OT Hours", "attendance"),
        ("paid_leave_days", "带薪假", "Paid Leave", "attendance"),
        ("sick_leave_days", "病假", "Sick Leave", "attendance"),
        ("unpaid_leave_days", "无薪假", "Unpaid Leave", "attendance"),
        # Less frequent attendance
        ("late_night_hours", "深夜小时", "Late Night", "attendance"),
        ("holiday_hours", "假日小时", "Holiday Hrs", "attendance"),
        ("absence_days", "缺勤天数", "Absence", "attendance"),
        # Reference
        ("standard_work_days", "满勤天数", "Std Work Days", "attendance"),
        ("standard_work_hours", "满勤小时", "Std Work Hrs", "attendance"),
    ]
    # Ordered by input frequency: allowances first, then deductions
    allowance_fields = [
        ("performance_bonus", "绩效工资", "Perf Bonus"),
        ("fixed_allowance", "固定津贴", "Allowance"),
        ("other_payment", "其他支付", "Other Pay"),
        ("bonus", "奖金", "Bonus"),
    ]
    deduction_fields = [
        ("other_deduction", "其他扣除", "Other Ded"),
        ("income_tax", "所得税", "Income Tax"),
        ("recurring_deductions", "固定扣除", "Recur Deduct"),
    ]
    other_fields = ["skill_development_levy", "foreign_worker_levy"]

    salary_type = record.get('salary_type', 'monthly')
    attendance_inputs = ""
    for field_key, label_zh, label_en, category in attendance_fields:
        field_attrs = attendance_input_attrs(field_key, salary_type, is_locked)
        label_display = f"{label_zh} / {label_en}"
        attendance_inputs += f"<div class='field'><label>{escape(label_display)}</label><input name='{field_key}' value='{money_fmt(record.get(field_key))}' {field_attrs}></div>"
    # Allowance inputs with green hint
    allowance_inputs = ""
    for field_key, label_zh, label_en in allowance_fields:
        if is_locked:
            attrs = "readonly style='background:#F5F5F5;color:#BDBDBD;cursor:not-allowed'"
        else:
            attrs = "style='background:#E8F5E9;font-weight:600;border-color:#43A047'"
        label_display = f"{label_zh} / {label_en}"
        allowance_inputs += f"<div class='field'><label>{escape(label_display)}</label><input name='{field_key}' value='{money_fmt(record.get(field_key))}' {attrs}></div>"
    # Deduction inputs with amber hint
    deduction_inputs = ""
    for field_key, label_zh, label_en in deduction_fields:
        if is_locked:
            attrs = "readonly style='background:#F5F5F5;color:#BDBDBD;cursor:not-allowed'"
        else:
            attrs = "style='background:#FFF3E0;font-weight:600;border-color:#EF6C00'"
        label_display = f"{label_zh} / {label_en}"
        deduction_inputs += f"<div class='field'><label>{escape(label_display)}</label><input name='{field_key}' value='{money_fmt(record.get(field_key))}' {attrs}></div>"
    other_inputs = "".join(f"<div class='field'><label>{escape(field.replace('_',' ').title())}</label><input name='{field}' value='{money_fmt(record.get(field))}' {'readonly' if is_locked else ''}></div>" for field in other_fields)
    perf_ref_display = f"<div class='field'><label>{t(lang,'label.performance_reference')}</label><input value='{money_fmt(record.get('performance_reference', 0))}' readonly style='color:var(--muted)'></div>"
    cur_val = record.get("payroll_currency", "SGD")
    cur_options = "".join(f"<option value='{c}' {'selected' if c == cur_val else ''}>{escape(c)}</option>" for c in SUPPORTED_CURRENCIES)
    if cur_val not in SUPPORTED_CURRENCIES:
        cur_options += f"<option value='{escape(cur_val)}' selected>{escape(cur_val)}</option>"

    calc_info = ""
    if record.get("calculation_messages"):
        messages = "".join(f"<li>{escape(m)}</li>" for m in record.get("calculation_messages", []))
        calc_info = f"""
<div class="card"><div class="section-header"><h3>Calculation Result / 计算结果 (Version {record.get('version',1)})</h3></div>
<div class="grid">
  <div class="metric-card"><div>{t(lang,'label.base_pay')}</div><div class="value">{money_fmt(record.get('base_pay_calculated'))}</div></div>
  <div class="metric-card"><div>{t(lang,'label.gross')}</div><div class="value">{money_fmt(record.get('gross_pay'))}</div></div>
  <div class="metric-card"><div>{t(lang,'label.cpf_employee')}</div><div class="value">{money_fmt(record.get('cpf_employee'))}</div></div>
  <div class="metric-card"><div>{t(lang,'label.deductions')}</div><div class="value">{money_fmt(record.get('deduction_total'))}</div></div>
  <div class="metric-card"><div>{t(lang,'label.net')}</div><div class="value" style="font-size:32px">{money_fmt(record.get('net_pay'))}</div></div>
  <div class="metric-card"><div>{t(lang,'label.employer_cost')}</div><div class="value">{money_fmt(record.get('employer_cost_total'))}</div></div>
</div>
<div class="message-strip"><b>Calculation Messages</b><ul>{messages}</ul></div></div>"""

    # Pre-compute nav variables (avoid backslashes in f-string)
    sheet_id = record.get('sheet_id', '')
    record_id_list = [r['record_id'] for r in sheet_records(sheet_id)]
    total_records = len(record_id_list)
    current_idx = record_id_list.index(record_id) if record_id in record_id_list else 0
    base_url_template = with_lang("/monthly-records/edit", lang, record_id="__RID__")
    prev_disabled = "disabled" if current_idx <= 0 else ""
    next_disabled = "disabled" if current_idx >= total_records - 1 else ""
    prev_label = {"zh": "上一条", "ja": "前へ", "en": "Prev"}.get(lang, "Prev")
    next_label = {"zh": "下一条", "ja": "次へ", "en": "Next"}.get(lang, "Next")
    current_idx_display = f"{current_idx + 1} / {total_records}"

    return f"""
<div class="sap-page-header"><h1>{escape(record['employee_name'])}</h1><div>{escape(record['employee_number'])} · {escape(record.get('payroll_month',''))} · {escape(sheet_id)}</div></div>
{locked_note}
{calc_info}
<form class="card" method="post" action="{with_lang('/monthly-records/save', lang, record_id=record_id)}">
<div class="section-header"><h3>{t(lang,'label.employee')} Info / 基本信息</h3></div>
<div class="form-grid">
  <div class="field"><label>No.</label><input value="{escape(record['employee_number'])}" readonly></div>
  <div class="field"><label>Name</label><input value="{escape(record['employee_name'])}" readonly></div>
  <div class="field"><label>{t(lang,'label.salary_type')}</label><input value="{escape(record.get('salary_type',''))}" readonly></div>
  <div class="field"><label>{t(lang,'label.basic_salary')}</label><input value="{money_fmt(record.get('basic_salary'))}" readonly></div>
  <div class="field"><label>Department</label><input value="{escape(record.get('department_label',''))}" readonly></div>
  <div class="field"><label>Team</label><input value="{escape(record.get('team_label',''))}" readonly></div>
  <div class="field"><label>{t(lang,'label.payroll_currency')}</label><select name="payroll_currency">{cur_options}</select></div>
</div>
<div class="color-legend" style="display:flex;gap:12px;flex-wrap:wrap;padding:6px 10px;background:#fafbfc;border-radius:8px;margin-bottom:12px;font-size:11px;align-items:center">
  <span style="font-weight:600;color:var(--muted)">字段提示 / Legend:</span>
  <span style="background:#FFFDE7;padding:2px 8px;border-radius:4px;border:1px solid #F9A825">🟡 考勤</span>
  <span style="background:#E8F5E9;padding:2px 8px;border-radius:4px;border:1px solid #43A047">🟢 津贴奖金</span>
  <span style="background:#FFF3E0;padding:2px 8px;border-radius:4px;border:1px solid #EF6C00">🟠 扣除项</span>
</div>
<div class="section-header"><h3>📋 Attendance / 考勤</h3></div>
<div class="form-grid">{attendance_inputs}</div>
<div class="section-header"><h3>💚 Allowances & Bonuses / 津贴与奖金</h3></div>
<div class="form-grid">{allowance_inputs}</div>
<div class="section-header"><h3>🧡 Deductions / 扣除项</h3></div>
<div class="form-grid">{deduction_inputs}</div>
<div class="section-header"><h3>📎 Other / 其他</h3></div>
<div class="form-grid">{other_inputs}{perf_ref_display}</div>
<div class="sap-toolbar"><button>{t(lang,'action.save')}</button><a class="button secondary" href="{with_lang('/monthly-sheets/detail', lang, sheet_id=record.get('sheet_id',''))}">{t(lang,'action.cancel')}</a></div>
</form>
<script>
// Arrow key navigation between records
var recordList = {json.dumps(record_id_list)};
var currentIdx = recordList.indexOf({json.dumps(record_id)});
var baseUrl = {json.dumps(base_url_template)};
function goToRecord(delta) {{
  var newIdx = currentIdx + delta;
  if (newIdx >= 0 && newIdx < recordList.length) {{
    window.location.href = baseUrl.replace('__RID__', recordList[newIdx]);
  }}
}}
document.addEventListener('keydown', function(e) {{
  if (e.target.tagName === 'INPUT' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'SELECT') return;
  if (e.key === 'ArrowLeft' && !e.ctrlKey && !e.metaKey) {{ goToRecord(-1); }}
  if (e.key === 'ArrowRight' && !e.ctrlKey && !e.metaKey) {{ goToRecord(1); }}
}});
</script>
<div style="display:flex;gap:8px;justify-content:center;margin-top:12px">
<button class="secondary" onclick="goToRecord(-1)" {prev_disabled}>← {prev_label}</button>
<span style="padding:8px;font-weight:600">{current_idx_display}</span>
<button class="secondary" onclick="goToRecord(1)" {next_disabled}>{next_label}</button>
</div>
"""


# ── Payroll Calendar HTML Generators ──────────────────────────────

def calendars_list_html(lang: str) -> str:
    """List all payroll calendars."""
    calendars = load_calendars()
    if not calendars:
        return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.calendars')}</h1><div class="muted">Manage multi-country payroll calendars with public holidays and auto-computed monthly standard work days.</div></div>
<div class="card"><div class="sap-toolbar"><a class="button" href="{with_lang('/calendars/new', lang)}">{t(lang,'action.calendar_create')}</a></div><p class="muted">{t(lang,'msg.no_records')}</p></div>"""
    trs = []
    for c in calendars:
        trs.append(f"<tr><td><a href='{with_lang('/calendars/edit', lang, calendar_id=c.get('calendar_id'))}'>{escape(c.get('calendar_id',''))}</a></td><td>{escape(c.get('country_code',''))}</td><td>{c.get('year','')}</td><td>{status_badge(c.get('status','active'))}</td><td>{escape(c.get('label',''))}</td></tr>")
    table = f"<div class='table-scroll'><table><thead><tr><th>ID</th><th>{t(lang,'label.country')}</th><th>{t(lang,'label.year')}</th><th>{t(lang,'label.status')}</th><th>Label</th></tr></thead><tbody>{''.join(trs)}</tbody></table></div>"
    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.calendars')}</h1><div class="muted">Manage multi-country payroll calendars with public holidays and auto-computed monthly standard work days.</div></div>
<div class="card"><div class="sap-toolbar"><a class="button" href="{with_lang('/calendars/new', lang)}">{t(lang,'action.calendar_create')}</a></div>{table}<div class='helper-text' style='margin-top:8px'>{len(calendars)} calendar(s) total</div></div>"""


def calendar_form_html(lang: str, calendar: dict[str, Any] | None = None) -> str:
    """Create or edit a payroll calendar."""
    is_new = calendar is None
    c = calendar or {"calendar_id": "", "country_code": "SG", "year": datetime.now().year, "status": "active", "label": "", "public_holidays": []}
    holidays_json = json.dumps(c.get("public_holidays", []), ensure_ascii=False, indent=2)
    months_display = ""
    if not is_new and c.get("months"):
        rows = ""
        for mk in sorted(c["months"].keys()):
            md = c["months"][mk]
            rows += f"<tr><td>{mk}</td><td class='right'>{md.get('calendar_days','')}</td><td class='right'>{md.get('weekend_days','')}</td><td class='right'>{md.get('public_holidays','')}</td><td class='right'><strong>{md.get('standard_work_days','')}</strong></td></tr>"
        months_display = f"<div class='card'><div class='section-header'><h3>Monthly Breakdown</h3></div><div class='table-scroll'><table><thead><tr><th>Month</th><th>Calendar Days</th><th>Weekend Days</th><th>Public Holidays</th><th>Standard Work Days</th></tr></thead><tbody>{rows}</tbody></table></div></div>"

    return f"""
<div class="sap-page-header"><h1>{t(lang,'action.calendar_create') if is_new else 'Edit Calendar'}</h1></div>
<form class="card" method="post" action="{with_lang('/calendars/save', lang)}">
<input type="hidden" name="calendar_id" value="{escape(c.get('calendar_id',''))}">
<div class="form-grid">
  <div class="field"><label>{t(lang,'label.country')}</label>
    <select name="country_code"><option value="SG" {'selected' if c.get('country_code')=='SG' else ''}>SG - Singapore</option><option value="JP" {'selected' if c.get('country_code')=='JP' else ''}>JP - Japan</option><option value="CN" {'selected' if c.get('country_code')=='CN' else ''}>CN - China</option></select></div>
  <div class="field"><label>{t(lang,'label.year')}</label><input name="year" type="number" value="{c.get('year', datetime.now().year)}" required></div>
  <div class="field"><label>Label</label><input name="label" value="{escape(c.get('label',''))}" placeholder="e.g. Singapore 2026 Payroll Calendar"></div>
  <div class="field"><label>{t(lang,'label.status')}</label>
    <select name="status"><option value="active" {'selected' if c.get('status')=='active' else ''}>Active</option><option value="inactive" {'selected' if c.get('status')=='inactive' else ''}>Inactive</option></select></div>
</div>
<div class="field"><label>Public Holidays (JSON array)</label><textarea name="public_holidays_json" style="min-height:200px;font-family:monospace">{escape(holidays_json)}</textarea>
<div class="helper-text">Format: [{"{"}"date": "2026-01-01", "name": "New Year's Day"{"}"}, ...]. System auto-computes monthly work days from holidays.</div></div>
<div class="sap-toolbar"><button>{t(lang,'action.save')}</button><a class="button secondary" href="{with_lang('/calendars', lang)}">{t(lang,'action.cancel')}</a></div>
</form>
{months_display}"""


# ── Salary Actuarial HTML Generator ──────────────────────────

def actuarial_html(lang: str, query: dict[str, list[str]] | None = None) -> str:
    query = query or {}
    month = clean((query.get("month") or [datetime.now().strftime("%Y-%m")])[0])
    entity_id = clean((query.get("entity_id") or ["SG"])[0])
    # Find or create sheet
    sheet_id = next_actuarial_sheet_id(month, entity_id)
    sheet = find_actuarial_sheet(sheet_id)
    records = actuarial_records_for_sheet(sheet_id) if sheet else []
    masters = active_sg_salary_master(entity_id)
    # Build entity options from master data
    entities = sorted({r.get("entity_id", "") for r in load_salary_master() if r.get("entity_id")})
    entity_opts = entity_options_html(entities, entity_id, lang)
    
    # If sheet doesn't exist yet, show load form
    if not sheet:
        return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.actuarial')}</h1><div class="muted">Create a new actuarial sheet by loading employees from salary master. Edit payroll fields directly and calculate.</div></div>
<div class="card">
<div class="section-header"><h3>Load Employees / 加载员工</h3></div>
<form method="post" action="{with_lang('/salary-actuarial/load', lang)}" onsubmit="return confirm({json.dumps(t(lang, 'msg.actuarial_load_confirm'))})">
<div class="form-grid">
<div class="field"><label>{t(lang,'label.month')}</label><input name="payroll_month" type="month" value="{escape(month)}" required></div>
<div class="field"><label>{t(lang,'label.entity')}</label><select name="entity_id">{entity_opts}</select></div>
</div>
<div class="message-strip">{len(masters)} active SG salary master employees available for entity "{escape(entity_label(entity_id, lang))}".</div>
<div class="sap-toolbar"><button>{t(lang,'action.load_employees')}</button></div>
</form>
</div>
"""

    # Build the editable grid
    SALARY_TYPES_LIST = sorted(SALARY_TYPES)
    trs = []
    for i, r in enumerate(records):
        st_opts = "".join(f'<option value="{s}" {"selected" if r.get("salary_type","monthly")==s else ""}>{s}</option>' for s in SALARY_TYPES_LIST)
        cur_opts = currency_options(r.get("payroll_currency", "SGD"))
        trs.append(f"""<tr>
<td style="text-align:center"><input type="checkbox" name="calc_{r['record_id']}" value="1" style="width:auto" checked></td>
<td>{escape(r['employee_number'])}<input type="hidden" name="record_id" value="{escape(r['record_id'])}"></td>
<td style="white-space:nowrap">{escape(r['employee_name'])}</td>
<td><select name="salary_type_{r['record_id']}" style="padding:3px 4px;font-size:12px;width:90px" onchange="this.form.submit()">{st_opts}</select></td>
<td><input name="work_days_{r['record_id']}" value="{money_fmt(r.get('work_days',22))}" style="width:55px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td><input name="work_hours_{r['record_id']}" value="{money_fmt(r.get('work_hours',176))}" style="width:60px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td class="right" style="font-size:12px">{escape(r.get('salary_type','monthly') == 'monthly' and money_fmt(r.get('basic_salary',0)) or '0')}</td>
<td><input name="fixed_allowance_{r['record_id']}" value="{money_fmt(r.get('fixed_allowance',0))}" style="width:65px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td><input name="performance_bonus_{r['record_id']}" value="{money_fmt(r.get('performance_bonus',0))}" style="width:65px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td><input name="bonus_{r['record_id']}" value="{money_fmt(r.get('bonus',0))}" style="width:60px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td><input name="cpf_employee_{r['record_id']}" value="{money_fmt(r.get('cpf_employee',0))}" style="width:70px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td><input name="other_deduction_{r['record_id']}" value="{money_fmt(r.get('other_deduction',0))}" style="width:60px;padding:3px 4px;font-size:12px;text-align:right"></td>
<td class="right" style="font-weight:750;font-size:13px">{money_fmt(r.get('gross_pay',0))}</td>
<td class="right" style="font-weight:750;font-size:13px;color:var(--red)">{money_fmt(r.get('deduction_total',0))}</td>
<td class="right" style="font-weight:850;font-size:14px;color:var(--navy)">{money_fmt(r.get('net_pay',0))}</td>
<td class="right" style="font-size:12px;color:var(--muted)">{money_fmt(r.get('employer_cost_total',0))}</td>
<td><select name="payroll_currency_{r['record_id']}" style="padding:3px 4px;font-size:12px;width:72px">{cur_opts}</select></td>
</tr>""")

    table_html = f"""<div class="table-scroll" style="max-height:70vh;overflow-y:auto">
<table style="min-width:1500px">
<thead><tr style="position:sticky;top:0;z-index:10">
<th style="width:30px">☑</th><th>No.</th><th>Name</th><th style="width:90px">Type</th>
<th style="width:55px">Days</th><th style="width:60px">Hrs</th><th style="width:65px">Basic</th>
<th style="width:65px">Allow</th><th style="width:65px">Perf</th><th style="width:60px">Bonus</th>
<th style="width:70px">CPF</th><th style="width:60px">OthDed</th>
<th style="width:70px">Gross</th><th style="width:70px">Ded</th><th style="width:80px">Net</th>
<th style="width:70px">EmpCost</th><th style="width:72px">Cur</th>
</tr></thead>
<tbody>{''.join(trs)}</tbody></table></div>"""

    return f"""
<div class="sap-page-header"><h1>{t(lang,'nav.actuarial')}</h1><div class="muted">Sheet: {escape(sheet_id)} · Month: {escape(month)} · Entity: {escape(entity_label(entity_id, lang))} · {len(records)} employees</div></div>
<div class="card">
<div class="sap-toolbar" style="flex-wrap:wrap;gap:8px">
<form method="post" action="{with_lang('/salary-actuarial/save', lang)}" style="display:contents" onsubmit="return confirm({json.dumps(t(lang, 'msg.actuarial_save_confirm'))})">
<input type="hidden" name="sheet_id" value="{escape(sheet_id)}">
<button class="secondary" style="background:#e4f7e7;border-color:#107e3e;color:#107e3e">{t(lang,'action.save_all')}</button>
</form>
<form method="post" action="{with_lang('/salary-actuarial/calculate', lang)}" style="display:contents" onsubmit="return collectChecked(this, 'calc_all') && confirm({json.dumps(t(lang, 'msg.calculate_actuarial_confirm'))})">
<input type="hidden" name="sheet_id" value="{escape(sheet_id)}">
<input type="hidden" name="mode" value="checked">
<button style="background:var(--blue)">{t(lang,'action.calculate_selected')}</button>
</form>
<form method="post" action="{with_lang('/salary-actuarial/calculate', lang)}" style="display:contents" onsubmit="return confirm({json.dumps(t(lang, 'msg.calculate_actuarial_all_confirm'))})">
<input type="hidden" name="sheet_id" value="{escape(sheet_id)}">
<input type="hidden" name="mode" value="all">
<button class="danger">{t(lang,'action.calculate_all')}</button>
</form>
<a class="button secondary" href="{with_lang('/salary-actuarial', lang)}?month={escape(month)}&entity_id={escape(entity_id)}">Reload</a>
</div>
<form method="post" action="{with_lang('/salary-actuarial/save', lang)}" id="actuarial_form" onsubmit="return confirm({json.dumps(t(lang, 'msg.actuarial_save_confirm'))})">
<input type="hidden" name="sheet_id" value="{escape(sheet_id)}">
{table_html}
</form>
<div class="helper-text" style="margin-top:10px">{len(records)} record(s) total · Edit fields inline → Save → Calculate</div>
</div>
<script>
function collectChecked(form, hiddenName) {{
    // Add all checked record_ids as hidden inputs
    document.querySelectorAll('input[type=checkbox][name^=calc_]').forEach(cb => {{
        if (cb.checked) {{
            var input = document.createElement('input');
            input.type = 'hidden';
            input.name = hiddenName;
            input.value = cb.name.replace('calc_', '');
            form.appendChild(input);
        }}
    }});
    return true;
}}
</script>
"""


class Handler(BaseHTTPRequestHandler):

    server_version = "TACAIPaySG/0.1"

    @property
    def request_host(self) -> str:
        raw = self.headers.get("Host", "")
        return raw.split(":", 1)[0] if raw else "127.0.0.1"

    def send_bytes(self, content: bytes, content_type: str = "text/html; charset=utf-8", status: int = 200, filename: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(content)))
        if filename:
            self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, status: int, payload: dict[str, Any]) -> None:
        self.send_bytes(json.dumps(payload, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8", status=status)

    def send_page(self, lang: str, title: str, body: str, user: dict[str, Any] | None = None, status: int = 200) -> None:
        parsed = urlparse(self.path)
        self.send_bytes(page(lang, title, body, user, parsed.path or "/", parse_qs(parsed.query), portal_url=resolve_portal_url(self.request_host)), status=status)

    def redirect(self, location: str) -> None:
        self.send_response(303)
        self.send_header("Location", location)
        self.end_headers()

    def read_form(self) -> dict[str, list[str]]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        limit = MAX_POST_BYTES if "/upload" in self.path or "/import" in self.path else MAX_POST_FORM_BYTES
        if length > limit:
            self.send_json(413, {"error": f"Request body exceeds {limit // 1024 // 1024}MB limit"})
            raise ValueError("Request body too large")
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        return parse_qs(raw, keep_blank_values=True)

    def current_session_id(self) -> str:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        morsel = cookie.get(USER_ADMIN_SESSION_COOKIE)
        return morsel.value if morsel else ""

    def current_user(self) -> dict[str, Any] | None:
        cookie_header = self.headers.get("Cookie", "")
        return validate_user_admin_session(self.current_session_id(), cookie_header)

    def user_admin_login_url(self, next_path: str) -> str:
        # Ensure next URL uses the same host the user is currently accessing
        host = self.headers.get("Host", "").split(":")[0] if self.headers.get("Host") else ""
        public_host = host if host and host not in {"127.0.0.1", "localhost", "::1"} else TACAI_PUBLIC_HOST
        base = f"http://{public_host}:{DEFAULT_PORT}" if public_host else APP_BASE_URL
        next_url = f"{base}{next_path if next_path.startswith('/') else '/' + next_path}"
        user_admin_base = f"http://{public_host}:{int(os.environ.get('AUTH_PORT', '8006'))}" if public_host else USER_ADMIN_BASE_URL
        return f"{user_admin_base}/login?next={quote(next_url, safe='')}"

    def require_user(self, lang: str, permission_key: str = REQUIRED_MODULE_PERMISSION) -> dict[str, Any] | None:
        # Cache validated user on the handler instance for the duration of this request
        if hasattr(self, "_cached_user"):
            user = self._cached_user
        else:
            user = self.current_user()
            self._cached_user = user
        if not user:
            self.redirect(self.user_admin_login_url(self.path))
            return None
        if not has_permission(user, REQUIRED_MODULE_PERMISSION):
            self.send_page(lang, "Forbidden", forbidden_html(f"Missing {REQUIRED_MODULE_PERMISSION} permission."), user, status=403)
            return None
        if permission_key and not has_permission(user, permission_key):
            self.send_page(lang, "Forbidden", forbidden_html(f"Missing {permission_key} permission."), user, status=403)
            return None
        return user

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = parse_lang(query)
        path = parsed.path
        if path == "/health":
            self.send_bytes(b'{"status":"ok","app":"tacaipaysg"}', "application/json")
            return
        if path == "/api/employeeadmin-employees":
            user = self.require_user(lang, "tacaipay_sg.manage")
            if not user:
                return
            employees, error = fetch_employeeadmin_payroll_employees(
                self.current_session_id(),
                country_code="SG",
                entity_id=clean((query.get("entity_id") or [""])[0]),
                department=clean((query.get("department") or query.get("department_id") or [""])[0]),
                q=clean((query.get("q") or [""])[0]),
            )
            self.send_json(503 if error else 200, {"error": error, "employees": []} if error else {"employees": employees})
            return
        if path == "/api/payslip/view":
            # Support session_id from query param for cross-origin Vue app access
            session_id = clean((query.get("session_id") or [""])[0])
            if session_id:
                user = validate_user_admin_session(session_id, self.headers.get("Cookie", ""))
                if not user or not has_permission(user, "tacaipay_sg.reports.view"):
                    self.send_json(401, {"error": "Invalid session or insufficient permissions."})
                    return
            else:
                user = self.require_user(lang, "tacaipay_sg.reports.view")
                if not user:
                    return
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            data = payslip_json_view(lang, payslip_id)
            if data.get("error"):
                self.send_json(404, data)
            else:
                self.send_json(200, data)
            return
        permission = {
            "/salary-master/new": "tacaipay_sg.manage",
            "/salary-master/edit": "tacaipay_sg.manage",
            "/salary-master/modify": "tacaipay_sg.manage",
            "/salary-master.csv": "tacaipay_sg.reports.view",
            "/batches/new": "tacaipay_sg.manage",
            "/records/edit": "tacaipay_sg.manage",
            "/monthly-sheets/new": "tacaipay_sg.manage",
            "/monthly-sheets/detail": "tacaipay_sg.view",
            "/monthly-sheets/report": "tacaipay_sg.view",
            "/monthly-sheets/review": "tacaipay_sg.manage",
            "/monthly-records/edit": "tacaipay_sg.manage",
            "/calendars": "tacaipay_sg.view",
            "/calendars/new": "tacaipay_sg.manage",
            "/calendars/edit": "tacaipay_sg.manage",
            "/reports": "tacaipay_sg.reports.view",
            "/reports/payroll.csv": "tacaipay_sg.reports.view",
            "/reports/cost.csv": "tacaipay_sg.reports.view",
            "/reports/bank.csv": "tacaipay_sg.reports.view",
            "/parameters": "tacaipay_sg.manage",
            "/audit": "tacaipay_sg.audit.view",
            "/payslip/view": "tacaipay_sg.reports.view",
            "/payslip/download": "tacaipay_sg.reports.view",
        }.get(path, "tacaipay_sg.view")
        user = self.require_user(lang, permission)
        if not user:
            return
        if path == "/":
            self.send_page(lang, t(lang, "app.title"), dashboard_html(lang), user)
        elif path == "/salary-master":
            self.send_page(lang, t(lang, "nav.master"), salary_master_html(lang, query), user)
        elif path == "/salary-master/modify":
            self.send_page(lang, t(lang, "nav.master"), salary_master_modify_html(lang, query), user)
        elif path == "/salary-master/new":
            self.send_page(lang, t(lang, "nav.master"), salary_master_create_html(lang), user)
        elif path == "/salary-master/edit":
            employee_id = clean((query.get("employee_id") or [""])[0])
            from_modify = clean((query.get("_from") or [""])[0]) == "modify"
            row = next((r for r in load_salary_master() if r.get("employee_id") == employee_id), None)
            self.send_page(lang, t(lang, "nav.master"), salary_form_html(lang, row, from_modify), user)
        elif path == "/salary-master.csv":
            rows = load_salary_master()
            # Apply same filters as salary_master_html for filtered CSV export
            f_entity = clean((query.get("entity") or [""])[0])
            f_department = clean((query.get("department") or [""])[0])
            f_team = clean((query.get("team") or [""])[0])
            f_q = clean((query.get("q") or [""])[0])
            if f_entity:
                rows = [r for r in rows if r.get("entity_id") == f_entity]
            if f_department:
                rows = [r for r in rows if (r.get("department_label") and f_department.lower() in r["department_label"].lower()) or (r.get("department") and f_department.lower() in r["department"].lower())]
            if f_team:
                rows = [r for r in rows if r.get("team_label") and f_team.lower() in r["team_label"].lower()]
            if f_q:
                q_lower = f_q.lower()
                rows = [r for r in rows if (r.get("employee_number") and q_lower in r["employee_number"].lower()) or (r.get("employee_name") and q_lower in r["employee_name"].lower())]
            headers = list(normalize_salary_master({}).keys())
            self.send_bytes(csv_response(rows, headers), "text/csv; charset=utf-8", filename="tacaipaysg_salary_master.csv")
        elif path == "/batches":
            all_batches = load_batches()
            self.send_page(lang, t(lang, "nav.batches"), f"<div class='sap-page-header'><h1>{t(lang,'nav.batches')}</h1><div class='sap-toolbar'><a class='button' href='{with_lang('/batches/new', lang)}'>{t(lang,'action.generate')}</a></div></div><div class='card'>{batches_table(lang, all_batches, total=len(all_batches))}</div>", user)
        elif path == "/batches/new":
            entity_id = clean((query.get("entity_id") or ["SG"])[0])
            month = clean((query.get("month") or [""])[0])
            self.send_page(lang, t(lang, "action.generate"), new_batch_html(lang, entity_id, month), user)
        elif path == "/batches/detail":
            self.send_page(lang, t(lang, "nav.batches"), batch_detail_html(lang, clean((query.get("batch_id") or [""])[0])), user)
        elif path == "/records/edit":
            self.send_page(lang, "Record", record_form_html(lang, clean((query.get("record_id") or [""])[0])), user)
        elif path == "/reports":
            self.send_page(lang, t(lang, "nav.reports"), reports_html(lang), user)
        elif path in {"/reports/payroll.csv", "/reports/cost.csv", "/reports/bank.csv"}:
            batch_id = clean((query.get("batch_id") or [""])[0])
            release_id = clean((query.get("release_id") or [""])[0])
            if release_id:
                # Export from release data (with bank info from monthly records)
                rows = release_csv_rows(release_id)
            else:
                rows = batch_records(batch_id)
            if path.endswith("bank.csv"):
                headers = ["employee_number", "employee_name", "bank_name", "bank_branch_name", "bank_swift_code", "bank_account_type", "bank_account_name", "bank_account_number", "payroll_currency", "net_pay"]
            elif path.endswith("cost.csv"):
                headers = ["payroll_month", "entity_id", "employee_number", "employee_name", "department_label", "gross_pay", "cpf_employer", "skill_development_levy", "foreign_worker_levy", "employer_cost_total", "payroll_currency"]
            else:
                headers = ["payroll_month", "entity_id", "employee_number", "employee_name", "salary_type", "work_days", "work_hours", "gross_pay", "cpf_employee", "income_tax", "other_deduction", "deduction_total", "net_pay", "employer_cost_total"]
            self.send_bytes(csv_response(rows, headers), "text/csv; charset=utf-8", filename=f"{slug(batch_id or release_id)}_{Path(path).stem}.csv")
        elif path == "/parameters":
            self.send_page(lang, t(lang, "nav.parameters"), parameters_html(lang), user)
        elif path == "/audit":
            self.send_page(lang, t(lang, "nav.audit"), audit_html(lang), user)
        elif path == "/monthly-sheets":
            self.send_page(lang, t(lang, "nav.monthly_sheets"), monthly_sheets_list_html(lang), user)
        elif path == "/monthly-sheets/new":
            entity_id = clean((query.get("entity_id") or [""])[0])
            month = clean((query.get("month") or [""])[0])
            filter_department = clean((query.get("filter_department") or [""])[0])
            filter_team = clean((query.get("filter_team") or [""])[0])
            self.send_page(lang, t(lang, "action.create_sheet"), new_monthly_sheet_html(lang, entity_id, month, filter_department, filter_team), user)
        elif path == "/monthly-sheets/detail":
            self.send_page(lang, t(lang, "nav.monthly_sheets"), monthly_sheet_detail_html(lang, clean((query.get("sheet_id") or [""])[0])), user)
        elif path == "/monthly-sheets/report":
            self.send_page(lang, t(lang, "nav.monthly_sheets"), monthly_sheet_report_html(lang, clean((query.get("sheet_id") or [""])[0])), user)
        elif path == "/monthly-sheets/review":
            self.send_page(lang, t(lang, "action.review_sheet"), monthly_sheet_review_html(lang, clean((query.get("sheet_id") or [""])[0])), user)
        elif path == "/monthly-records/edit":
            self.send_page(lang, t(lang, "label.employee"), monthly_record_form_html(lang, clean((query.get("record_id") or [""])[0])), user)
        elif path == "/calendars":
            self.send_page(lang, t(lang, "nav.calendars"), calendars_list_html(lang), user)
        elif path == "/calendars/new":
            self.send_page(lang, t(lang, "action.calendar_create"), calendar_form_html(lang, None), user)
        elif path == "/calendars/edit":
            cal_id = clean((query.get("calendar_id") or [""])[0])
            cal = next((c for c in load_calendars() if c.get("calendar_id") == cal_id), None)
            self.send_page(lang, "Edit Calendar", calendar_form_html(lang, cal), user)
        elif path == "/salary-actuarial":
            self.send_page(lang, t(lang, "nav.actuarial"), actuarial_html(lang, query), user)
        elif path == "/release/detail":
            self.send_page(lang, t(lang, "nav.release"), release_detail_html(lang, clean((query.get("release_id") or [""])[0])), user)
        elif path == "/release/email-draft":
            self.send_page(lang, t(lang, "action.release_email_draft"), release_email_draft_html(lang, clean((query.get("release_id") or [""])[0])), user)
        elif path == "/release/email-send":
            release_id = clean((query.get("release_id") or [""])[0])
            self.send_page(lang, t(lang, "action.release_email_send"), release_email_send_html(lang, release_id), user)
        elif path == "/ledger":
            self.send_page(lang, t(lang, "nav.ledger"), ledger_list_html(lang), user)
        elif path == "/ledger/detail":
            self.send_page(lang, t(lang, "nav.ledger"), ledger_detail_html(lang, clean((query.get("ledger_id") or [""])[0])), user)
        elif path == "/reports/cost-report":
            self.send_page(lang, "Cost Report", cost_report_html(lang), user)
        elif path == "/payslip/view":
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            # Embed Vue3 payslip widget within the original page layout (same origin)
            self.send_page(lang, "Payslip View", payslip_widget_html(lang, payslip_id, self.current_session_id(), self.request_host), user)
        elif path == "/payslip/download":
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            all_payslips = load_json(PAYSLIPS_PATH, [])
            ps = next((p for p in all_payslips if p.get("payslip_id") == payslip_id), None)
            if ps and ps.get("file_path"):
                file_path = ROOT_DIR / ps["file_path"]
                if file_path.exists():
                    self.send_bytes(file_path.read_bytes(), "application/pdf", filename=ps.get("file_name", f"{payslip_id}.pdf"))
                    return
            self.send_bytes(b"Payslip not found", status=404)
        else:
            self.send_page(lang, "Not found", "<div class='card'>Not found</div>", user, status=404)

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        lang = parse_lang(query)
        path = parsed.path
        permission = {
            "/salary-master/save": "tacaipay_sg.manage",
            "/salary-master/create": "tacaipay_sg.manage",
            "/salary-master/import-employeeadmin": "tacaipay_sg.manage",
            "/salary-master/deactivate": "tacaipay_sg.manage",
            "/batches/create": "tacaipay_sg.manage",
            "/batches/confirm": "tacaipay_sg.manage",
            "/batches/calculate": "tacaipay_sg.manage",
            "/batches/hr-review": "tacaipay_sg.approve",
            "/batches/approve": "tacaipay_sg.approve",
            "/batches/finalize": "tacaipay_sg.approve",
            "/batches/payslips": "tacaipay_sg.manage",
            "/batches/email": "tacaipay_sg.manage",
            "/batches/employee-confirm": "tacaipay_sg.manage",
            "/batches/finance": "tacaipay_sg.release_payment",
            "/batches/paid": "tacaipay_sg.release_payment",
            "/batches/return-step": "tacaipay_sg.manage",
            "/batches/void": "tacaipay_sg.manage",
            "/salary-actuarial/load": "tacaipay_sg.manage",
            "/salary-actuarial/save": "tacaipay_sg.manage",
            "/salary-actuarial/calculate": "tacaipay_sg.calculate",
            "/records/save": "tacaipay_sg.manage",
            "/monthly-sheets/create": "tacaipay_sg.manage",
            "/monthly-sheets/confirm-basic-info": "tacaipay_sg.manage",
            "/monthly-sheets/return-draft": "tacaipay_sg.manage",
            "/monthly-sheets/calculate": "tacaipay_sg.calculate",
            "/monthly-sheets/hr-approve": "tacaipay_sg.approve",
            "/monthly-sheets/send-manager-review": "tacaipay_sg.approve",
            "/monthly-sheets/manager-approve": "tacaipay_sg.manager_review",
            "/monthly-sheets/manager-reject": "tacaipay_sg.manager_review",
            "/monthly-sheets/finalize": "tacaipay_sg.approve",
            "/monthly-sheets/void": "tacaipay_sg.manage",
            "/monthly-sheets/delete": "tacaipay_sg.manage",
            "/monthly-sheets/batch-set-attendance": "tacaipay_sg.manage",
            "/monthly-sheets/review-save": "tacaipay_sg.manage",
            "/monthly-sheets/return-step": "tacaipay_sg.manage",
            "/monthly-records/save": "tacaipay_sg.manage",
            "/calendars/save": "tacaipay_sg.manage",
            "/release/create-from-sheet": "tacaipay_sg.manage",
            "/release/payslips": "tacaipay_sg.manage",
            "/release/return-to-pending": "tacaipay_sg.manage",
            "/release/void": "tacaipay_sg.manage",
            "/release/hr-confirm": "tacaipay_sg.approve",
            "/release/email-draft/prepare": "tacaipay_sg.manage",
            "/release/email-send/confirm": "tacaipay_sg.manage",
            "/release/paid": "tacaipay_sg.release_payment",
            "/release/email-resend": "tacaipay_sg.manage",
            "/release/email-resend-all": "tacaipay_sg.manage",
            "/payslip/download": "tacaipay_sg.reports.view",
            "/payslip/view": "tacaipay_sg.reports.view",
        }.get(path, "tacaipay_sg.manage")
        user = self.require_user(lang, permission)
        if not user:
            return
        form = self.read_form()
        if path == "/salary-master/save":
            saved = upsert_salary_master(form)
            from_modify = clean((form.get("_from") or [""])[0]) == "modify"
            target = "/salary-master/modify" if from_modify else "/salary-master"
            name = clean(saved.get("employee_name") or saved.get("employee_number", ""))
            notice = f"{name} — {t(lang, 'msg.saved')}" if name else t(lang, "msg.saved")
            self.redirect(with_lang(target, lang, notice=notice, notice_type="success"))
        elif path == "/salary-master/create":
            employee_ids = form.get("employee_id", [])
            entity_id = clean((form.get("entity_id") or [""])[0])
            result = create_salary_master_batch(employee_ids, self.current_session_id(), entity_id)
            notice = result.get("message", "")
            notice_type = "success" if result.get("ok") else "warning"
            self.redirect(with_lang("/salary-master", lang, notice=notice, notice_type=notice_type))
        elif path == "/salary-master/import-employeeadmin":
            result = import_from_employeeadmin(self.current_session_id())
            self.redirect(with_lang("/salary-master", lang, notice=result.get("message", ""), notice_type="success" if result.get("ok") else "warning"))
        elif path == "/salary-master/deactivate":
            employee_id = clean((form.get("employee_id") or [""])[0])
            reason = clean((form.get("reason") or [""])[0])
            ok = deactivate_salary_master(employee_id, reason, user_display_name(user))
            notice = "Salary master deactivated. It can be regenerated from EmployeeAdmin if the employee is active." if ok else "Salary master not found."
            self.redirect(with_lang("/salary-master", lang, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/batches/create":
            month = clean((form.get("payroll_month") or [""])[0])
            entity_id = clean((form.get("entity_id") or ["SG"])[0])
            employee_ids = form.get("employee_id", [])
            batch, _count = create_batch(month, entity_id, employee_ids if employee_ids else None)
            self.redirect(with_lang("/batches/detail", lang, batch_id=batch["batch_id"], notice=f"Batch created with {_count} employee(s).", notice_type="success"))
        elif path == "/batches/confirm":
            self.send_page(lang, t(lang, "action.generate"), batch_confirm_html(lang, form), user)
        elif path == "/batches/calculate":
            batch_id = clean((query.get("batch_id") or [""])[0])
            calculate_batch(batch_id)
            self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/hr-review":
            batch_id = clean((query.get("batch_id") or [""])[0]); transition_batch(batch_id, "hr_reviewed", "hr_review"); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/approve":
            # Merged step: approve → finalized (批准定案)
            batch_id = clean((query.get("batch_id") or [""])[0]); transition_batch(batch_id, "finalized", "approve_finalize"); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/finalize":
            batch_id = clean((query.get("batch_id") or [""])[0]); transition_batch(batch_id, "finalized", "finalize"); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/finance":
            batch_id = clean((query.get("batch_id") or [""])[0]); transition_batch(batch_id, "released_to_finance", "release_to_finance"); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/paid":
            batch_id = clean((query.get("batch_id") or [""])[0]); transition_batch(batch_id, "paid", "mark_paid"); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/return-step":
            batch_id = clean((query.get("batch_id") or [""])[0])
            comment = clean((form.get("comment") or [""])[0])
            ok = return_batch_to_prev_step(batch_id, comment)
            if ok:
                batch = find_batch(batch_id)
                notice = f"Batch returned to {batch.get('status', 'unknown')}." if batch else "Batch returned."
                notice_type = "success"
            else:
                notice = "Cannot return batch from current status. Only one step back is allowed."
                notice_type = "warning"
            self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id, notice=notice, notice_type=notice_type))
        elif path == "/batches/void":
            batch_id = clean((query.get("batch_id") or [""])[0])
            ok = void_batch(batch_id)
            notice = "Batch voided successfully." if ok else "Cannot void this batch (locked or not found)."
            self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/batches/payslips":
            batch_id = clean((query.get("batch_id") or [""])[0])
            selected_ids = form.get("selected_ids", [])
            count = generate_payslips(batch_id, selected_record_ids=selected_ids if selected_ids else None)
            notice = t(lang, "msg.payslip_gen_count_feedback").format(count=count)
            self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id, notice=notice, notice_type="success"))
        elif path == "/batches/email":
            batch_id = clean((query.get("batch_id") or [""])[0]); send_payslip_emails(batch_id); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/batches/employee-confirm":
            batch_id = clean((query.get("batch_id") or [""])[0]); close_employee_confirmation(batch_id); self.redirect(with_lang("/batches/detail", lang, batch_id=batch_id))
        elif path == "/records/save":
            record_id = clean((query.get("record_id") or [""])[0]); update_record_from_form(record_id, form)
            record = next((r for r in load_records() if r.get("record_id") == record_id), {})
            self.redirect(with_lang("/batches/detail", lang, batch_id=record.get("batch_id", "")))
        elif path == "/monthly-sheets/create":
            month = clean((form.get("payroll_month") or [""])[0])
            entity_id = clean((form.get("entity_id") or [""])[0])
            country_code = "SG"
            attendance_source = clean((form.get("attendance_source") or ["manual"])[0])
            employee_ids = form.get("employee_id", [])
            std_days = intish((form.get("standard_work_days") or ["0"])[0])
            try:
                sheet, count = create_monthly_sheet(month, entity_id, country_code, attendance_source, employee_ids if employee_ids else None, std_days)
                if count == 0:
                    self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet["sheet_id"], notice=f"Sheet already exists — {sheet['sheet_id']}. No new records created. / 工资表已存在，未创建新记录。", notice_type="warning"))
                else:
                    self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet["sheet_id"], notice=f"Sheet created with {count} employee(s). / 成功创建工资表，共 {count} 条员工记录。", notice_type="success"))
            except Exception as e:
                self.redirect(with_lang("/monthly-sheets", lang, notice=f"Failed to create sheet: {escape(str(e))} / 创建工资表失败：{escape(str(e))}", notice_type="warning"))
        elif path == "/monthly-sheets/confirm-basic-info":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok = confirm_basic_info(sheet_id, user_display_name(user))
            notice = t(lang, "msg.basic_info_confirmed") if ok else "Sheet not in draft status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/return-draft":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            comment = clean((form.get("comment") or [""])[0])
            ok = return_sheet_to_draft(sheet_id, comment)
            notice = "Sheet returned to draft." if ok else "Cannot return to draft from current status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/calculate":
            sheet_id = clean((form.get("sheet_id") or [""])[0])
            ids_str = clean((form.get("selected_ids") or [""])[0])
            record_ids = [rid for rid in ids_str.split(",") if rid.strip()] if ids_str else None
            try:
                total, warn_count, warn_details = calculate_monthly_sheet(sheet_id, record_ids)
                if total > 0:
                    success_count = total - warn_count
                    parts = [f"计算完成 — 共处理 {total} 条记录"]
                    if success_count > 0:
                        parts.append(f"✅ {success_count} 条计算成功")
                    if warn_count > 0:
                        parts.append(f"⚠️ {warn_count} 条存在潜在问题，请逐条核实")
                    notice = " · ".join(parts)
                    notice_type = "success" if warn_count == 0 else "warning"
                else:
                    notice = "未计算任何记录。 / No records calculated."
                    notice_type = "warning"
                self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type=notice_type))
            except Exception as e:
                self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=f"计算失败 / Calculation failed: {escape(str(e))}", notice_type="warning"))
        elif path == "/monthly-sheets/hr-approve":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok = hr_approve_sheet(sheet_id)
            notice = "HR approved." if ok else "Sheet must be in calculated status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/send-manager-review":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok = send_manager_review(sheet_id)
            notice = "Sent to manager review." if ok else "Sheet must be in hr_reviewed status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/manager-approve":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            comment = clean((form.get("comment") or [""])[0])
            ok = manager_approve_sheet(sheet_id, comment)
            notice = t(lang, "msg.sheet_finalized") if ok else "Sheet must be in manager_review status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/manager-reject":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            comment = clean((form.get("comment") or [""])[0])
            ok = manager_reject_sheet(sheet_id, comment)
            notice = t(lang, "msg.manager_rejected") if ok else "Sheet must be in manager_review status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="warning" if ok else "warning"))
        elif path == "/monthly-sheets/finalize":
            # [DEPRECATED] Redirect to manager_approve which now handles finalization (批准定案)
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok = finalize_sheet(sheet_id)
            notice = t(lang, "msg.sheet_finalized") if ok else "Sheet must be in manager_review or finalized status."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/void":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok, voided_count = void_sheet(sheet_id)
            if ok:
                notice = f"{t(lang, 'msg.sheet_voided')} — {voided_count} record(s) voided. / {voided_count} 条记录已作废。"
                notice_type = "success"
            else:
                notice = "Cannot void this sheet. Only sheets in draft/hr_confirmed/correction status can be voided. / 只能作废草稿/HR确认/修正状态的工资表。"
                notice_type = "warning"
            self.redirect(with_lang("/monthly-sheets", lang, notice=notice, notice_type=notice_type))
        elif path == "/monthly-sheets/delete":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            ok = delete_sheet(sheet_id)
            notice = t(lang, "msg.sheet_deleted") if ok else "Cannot delete this sheet. Only voided sheets can be permanently deleted. Please void the sheet first."
            self.redirect(with_lang("/monthly-sheets", lang, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/batch-set-attendance":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            work_days = money((form.get("work_days") or ["22"])[0])
            work_hours = money((form.get("work_hours") or ["176"])[0])
            count = batch_set_attendance(sheet_id, work_days, work_hours)
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=f"Set attendance for {count} record(s).", notice_type="success"))
        elif path == "/monthly-sheets/return-step":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            to_status = clean((query.get("to_status") or [""])[0])
            comment = clean((form.get("comment") or [""])[0])
            ok = False
            if to_status == "hr_confirmed":
                ok = return_sheet_to_hr_confirmed(sheet_id, comment)
            elif to_status == "calculated":
                ok = return_sheet_to_calculated(sheet_id, comment)
            elif to_status == "hr_reviewed":
                ok = return_sheet_to_hr_reviewed(sheet_id, comment)
            elif to_status == "manager_review":
                ok = return_sheet_to_manager_review(sheet_id, comment)
            notice = f"Returned to {to_status}." if ok else f"Cannot return to {to_status} from current status. Only one step back is allowed."
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/monthly-sheets/review-save":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            count = save_monthly_sheet_review(sheet_id, form)
            self.redirect(with_lang("/monthly-sheets/review", lang, sheet_id=sheet_id, notice=f"Saved {count} record(s).", notice_type="success"))
        elif path == "/monthly-records/save":
            record_id = clean((query.get("record_id") or [""])[0])
            update_monthly_record_from_form(record_id, form)
            record = next((r for r in load_monthly_records() if r.get("record_id") == record_id), {})
            self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=record.get("sheet_id", ""), notice=t(lang, "msg.saved"), notice_type="success"))
        elif path == "/calendars/save":
            calendar_id = clean((form.get("calendar_id") or [""])[0])
            country_code = clean((form.get("country_code") or ["SG"])[0])
            year = intish(form.get("year") or [datetime.now().year])
            label = clean((form.get("label") or [""])[0])
            status = clean((form.get("status") or ["active"])[0])
            holidays_json = clean((form.get("public_holidays_json") or ["[]"])[0])
            try:
                holidays = json.loads(holidays_json) if holidays_json else []
                if not isinstance(holidays, list):
                    holidays = []
            except json.JSONDecodeError:
                holidays = []
            months = compute_calendar_months(year, holidays)
            calendars = load_calendars()
            if calendar_id:
                for c in calendars:
                    if c.get("calendar_id") == calendar_id:
                        c["country_code"] = country_code
                        c["year"] = year
                        c["status"] = status
                        c["label"] = label
                        c["public_holidays"] = holidays
                        c["months"] = months
                        c["updated_at"] = now_iso()
                        break
            else:
                new_id = f"CAL-{country_code}-{year}"
                calendars.append({
                    "calendar_id": new_id,
                    "country_code": country_code,
                    "year": year,
                    "status": status,
                    "label": label,
                    "public_holidays": holidays,
                    "months": months,
                    "created_at": now_iso(),
                    "created_by": user_display_name(user),
                    "updated_at": now_iso(),
                })
            save_calendars(calendars)
            append_audit("tacaipaysg.calendar", calendar_id or "new", "save_calendar", None, {"country_code": country_code, "year": year})
            self.redirect(with_lang("/calendars", lang, notice=t(lang, "msg.saved"), notice_type="success"))
        elif path == "/salary-actuarial/load":
            month = clean((form.get("payroll_month") or [datetime.now().strftime("%Y-%m")])[0])
            entity_id = clean((form.get("entity_id") or ["SG"])[0])
            sheet_id = next_actuarial_sheet_id(month, entity_id)
            # Create sheet if not exists
            sheets = load_actuarial_sheets()
            if not find_actuarial_sheet(sheet_id):
                sheets.append({
                    "sheet_id": sheet_id, "country_code": "SG", "entity_id": entity_id,
                    "payroll_month": month, "status": "draft", "employee_count": 0,
                    "gross_total": 0, "net_total": 0, "employer_cost_total": 0,
                    "created_at": now_iso(), "updated_at": now_iso(), "created_by": USER_ACTOR,
                })
                save_actuarial_sheets(sheets)
            # Load employees from salary master
            employees = active_sg_salary_master(entity_id)
            records = load_actuarial_records()
            existing_ids = {r["employee_id"]: r for r in records if r.get("sheet_id") == sheet_id}
            new_count = 0
            for emp in employees:
                eid = emp["employee_id"]
                if eid not in existing_ids:
                    records.append(create_actuarial_record(sheet_id, emp, month))
                    new_count += 1
            save_actuarial_records(records)
            # Update sheet count
            sheet_records = [r for r in records if r.get("sheet_id") == sheet_id]
            for s in sheets:
                if s.get("sheet_id") == sheet_id:
                    s["employee_count"] = len(sheet_records)
                    s["updated_at"] = now_iso()
            save_actuarial_sheets(sheets)
            self.redirect(with_lang("/salary-actuarial", lang, month=month, entity_id=entity_id, notice=f"Loaded {new_count} new employees. {len(sheet_records)} total.", notice_type="success"))
        elif path == "/salary-actuarial/save":
            sheet_id = clean((form.get("sheet_id") or [""])[0])
            records = load_actuarial_records()
            saved = 0
            # Parse all field values from form
            for record in records:
                if record.get("sheet_id") != sheet_id:
                    continue
                rid = record["record_id"]
                prefix = f"work_days_{rid}"
                if prefix in form:
                    record["work_days"] = money(form[prefix][0])
                for field in ["work_hours", "fixed_allowance", "performance_bonus", "bonus", "other_payment", "recurring_deductions", "other_deduction", "income_tax", "cpf_employee", "cpf_employer", "skill_development_levy", "foreign_worker_levy"]:
                    key = f"{field}_{rid}"
                    if key in form:
                        record[field] = money(form[key][0])
                for field in ["salary_type", "payroll_currency"]:
                    key = f"{field}_{rid}"
                    if key in form:
                        record[field] = clean(form[key][0])
                record["updated_at"] = now_iso()
                saved += 1
            save_actuarial_records(records)
            self.redirect(with_lang("/salary-actuarial", lang, month="", entity_id="", notice=f"{saved} record(s) saved.", notice_type="success"))
        elif path == "/salary-actuarial/calculate":
            sheet_id = clean((form.get("sheet_id") or [""])[0])
            mode = clean((form.get("mode") or ["checked"])[0])
            records = load_actuarial_records()
            # Collect which record_ids to calculate
            calc_ids = set()
            if mode == "all":
                for r in records:
                    if r.get("sheet_id") == sheet_id:
                        calc_ids.add(r["record_id"])
            else:
                for key in form:
                    if key == "calc_all":
                        for rid in form[key]:
                            calc_ids.add(rid)
                # Also check checkbox-style
                for key in form:
                    if key.startswith("calc_") and form[key][0] == "1":
                        calc_ids.add(key.replace("calc_", ""))
            calculated = 0
            for record in records:
                if record.get("record_id") in calc_ids:
                    calculate_actuarial_record(record)
                    calculated += 1
            save_actuarial_records(records)
            self.redirect(with_lang("/salary-actuarial", lang, month="", entity_id="", notice=f"{calculated} record(s) calculated.", notice_type="success"))
        elif path == "/release/create-from-sheet":
            sheet_id = clean((query.get("sheet_id") or [""])[0])
            release_id = create_release_batch(sheet_id)
            if release_id:
                self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=f"Release batch {release_id} created.", notice_type="success"))
            else:
                self.redirect(with_lang("/monthly-sheets/detail", lang, sheet_id=sheet_id, notice="Cannot create release batch. Sheet must be in finalized status.", notice_type="warning"))
        elif path == "/release/payslips":
            release_id = clean((query.get("release_id") or [""])[0])
            selected_ids = form.get("payslip_ids", [])
            count = generate_release_payslips(release_id, selected_ids=selected_ids if selected_ids else None)
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=f"✅ Generated {count} payslip PDF(s).", notice_type="success"))
        elif path == "/release/return-to-pending":
            release_id = clean((query.get("release_id") or [""])[0])
            ok = return_release_to_pending(release_id)
            notice = "Release batch returned to pending." if ok else "Cannot return to pending."
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/release/void":
            release_id = clean((query.get("release_id") or [""])[0])
            ok = void_release_batch(release_id)
            notice = "Release batch voided." if ok else "Cannot void this release batch."
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/release/hr-confirm":
            release_id = clean((query.get("release_id") or [""])[0])
            ok = hr_confirm_release_payslips(release_id)
            notice = "Payslips confirmed by HR." if ok else "Cannot confirm. Ensure payslips have been generated first."
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/release/email-draft/prepare":
            release_id = clean((query.get("release_id") or [""])[0])
            # Collect selected payslip IDs from form
            selected = []
            for key in form:
                if key.startswith("select_") and form[key][0] == "1":
                    selected.append(key.replace("select_", ""))
            if not selected:
                self.redirect(with_lang("/release/email-draft", lang, release_id=release_id, notice=t(lang, "msg.no_email_recipients"), notice_type="warning"))
                return
            self.send_page(lang, t(lang, "action.release_email_send"), release_email_send_html(lang, release_id, selected), user)
        elif path == "/release/email-send/confirm":
            release_id = clean((query.get("release_id") or [""])[0])
            confirmed = clean((form.get("email_review_confirmed") or [""])[0])
            if confirmed != "1":
                self.redirect(with_lang("/release/email-send", lang, release_id=release_id, notice="Please confirm the checkbox before sending.", notice_type="warning"))
                return
            payslip_ids = form.get("payslip_ids", [])
            if not payslip_ids:
                self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=t(lang, "msg.no_email_recipients"), notice_type="warning"))
                return
            sent, failed = send_release_emails(release_id, payslip_ids)
            notice = t(lang, "msg.email_sent_summary").replace("{sent}", str(sent)).replace("{failed}", str(failed))
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if failed == 0 else "warning"))
        elif path == "/release/paid":
            release_id = clean((query.get("release_id") or [""])[0])
            ok = mark_release_paid(release_id)
            notice = "Release batch marked as paid." if ok else "Cannot mark as paid. Ensure all emails have been sent."
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if ok else "warning"))
        elif path == "/release/email-resend":
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            ok, msg = resend_single_payslip_email(payslip_id)
            release_id = clean((query.get("release_id") or [""])[0])
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=msg, notice_type="success" if ok else "warning"))
        elif path == "/release/email-resend-all":
            release_id = clean((query.get("release_id") or [""])[0])
            sent, failed = batch_resend_failed_emails(release_id)
            notice = f"Batch resend complete: {sent} sent, {failed} failed."
            self.redirect(with_lang("/release/detail", lang, release_id=release_id, notice=notice, notice_type="success" if failed == 0 else "warning"))
        elif path == "/payslip/download":
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            all_payslips = load_json(PAYSLIPS_PATH, [])
            ps = next((p for p in all_payslips if p.get("payslip_id") == payslip_id), None)
            if ps and ps.get("file_path"):
                file_path = ROOT_DIR / ps["file_path"]
                if file_path.exists():
                    self.send_bytes(file_path.read_bytes(), "application/pdf", filename=ps.get("file_name", f"{payslip_id}.pdf"))
                    return
            self.send_bytes(b"Payslip not found", status=404)
        elif path == "/payslip/view":
            payslip_id = clean((query.get("payslip_id") or [""])[0])
            # Embed Vue3 payslip widget within the original page layout (same origin)
            self.send_page(lang, "Payslip View", payslip_widget_html(lang, payslip_id, self.current_session_id(), self.request_host), user)
        else:
            self.send_bytes(b"Not found", status=404)


def seed_demo_data() -> None:
    ensure_dirs()
    load_parameters()
    if not SALARY_MASTER_PATH.exists():
        sample = normalize_salary_master({
            "employee_id": "SG-DEMO-001",
            "employee_number": "SG001",
            "employee_name": "Demo Singapore Employee",
            "email": "employee@example.com",
            "entity_id": "SG",
            "salary_type": "monthly",
            "basic_salary": 6000,
            "fixed_allowance": 300,
            "performance_bonus": 200,
            "cpf_employee_manual": 1200,
            "cpf_employer_manual": 1020,
            "skill_development_levy": 11.25,
            "bank_name": "DBS",
            "bank_branch_name": "Marina Bay",
            "bank_swift_code": "DBSSSGSG",
            "bank_account_type": "ordinary",
            "bank_account_name": "Demo Singapore Employee",
            "bank_account_number": "001-234567-8",
            "source": "demo",
        })
        save_salary_master([sample])
    for path, default in [(PAYROLL_BATCHES_PATH, []), (PAYROLL_RECORDS_PATH, []), (PAYSLIPS_PATH, []), (EMAIL_DELIVERIES_PATH, []), (AUDIT_LOGS_PATH, []), (MONTHLY_SHEETS_PATH, []), (MONTHLY_RECORDS_PATH, [])]:
        if not path.exists():
            save_json(path, default)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run TACAI Pay SG local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args()
    seed_demo_data()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"TACAI Pay SG running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
