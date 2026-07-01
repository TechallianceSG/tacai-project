"""Salary Master CRUD router — 薪资主数据"""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from auth import get_current_user, check_permission
from database import fetch_all, fetch_one, execute, execute_returning
from datetime import datetime, timezone

router = APIRouter(prefix="/api/salary-master", tags=["Salary Master"])

TABLE = "pay_jp_salary_master"
EDITABLE_COLS = ["employee_number","salary_type","basic_salary","hourly_rate","daily_rate",
    "standard_work_days","standard_work_hours","standard_monthly_hours",
    "overtime_hourly_rate","commute_allowance","housing_allowance",
    "family_allowance","position_allowance","fixed_allowance",
    "fixed_overtime_hours","fixed_overtime_amount","performance_bonus",
    "transport_allowance","phone_allowance","project_bonus",
    "recurring_deductions",
    "social_insurance_eligible","employment_insurance_eligible",
    "dependents_count","prefecture_code",
    "bank_name","bank_branch_name","bank_account_type",
    "bank_account_name","bank_account_number","notes"]

def now_iso():
    return datetime.now(timezone.utc).isoformat()

@router.get("/")
async def list_master(entity_id: Optional[str]=None, salary_type: Optional[str]=None,
                      active: Optional[bool]=None, search: Optional[str]=None):
    where = ["1=1"]; params = []
    if entity_id: where.append("entity_id=%s"); params.append(entity_id)
    if salary_type: where.append("salary_type=%s"); params.append(salary_type)
    if active is not None: where.append("active=%s"); params.append(active)
    if search: where.append("(employee_name ILIKE %s OR employee_number ILIKE %s OR department_label ILIKE %s)"); params.extend([f"%{search}%"]*3)
    sql = f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY employee_number"
    rows = fetch_all(sql, tuple(params) if params else None)
    return {"data": rows, "count": len(rows)}

@router.get("/importable-employees")
async def list_importable_employees():
    """Return employees from EmployeeAdmin with import status."""
    ea_employees = fetch_all(
        "SELECT employee_id, employee_number, email, payroll FROM emp_employees WHERE payroll IS NOT NULL ORDER BY employee_number"
    )
    existing = fetch_all("SELECT employee_id FROM pay_jp_salary_master")
    existing_ids = {r["employee_id"] for r in existing}

    result = []
    for emp in ea_employees:
        payroll = emp.get("payroll", {})
        if isinstance(payroll, str):
            import json; payroll = json.loads(payroll)
        result.append({
            "employee_id": emp["employee_id"],
            "employee_number": emp.get("employee_number", ""),
            "employee_name": payroll.get("employee_name", ""),
            "email": emp.get("email", ""),
            "department_label": payroll.get("department_label", ""),
            "entity_id": payroll.get("entity_id", ""),
            "already_imported": emp["employee_id"] in existing_ids,
        })
    return {"data": result, "count": len(result)}


@router.post("/import-selected")
async def import_selected(request: Request):
    """Import selected employees from EmployeeAdmin into salary master."""
    user = await get_current_user(request)
    body = await request.json()
    selected_ids = body.get("employee_ids", [])

    if not selected_ids:
        raise HTTPException(400, "No employee_ids provided")

    existing = fetch_all("SELECT employee_id FROM pay_jp_salary_master")
    existing_ids = {r["employee_id"] for r in existing}
    imported = 0
    skipped = 0

    all_records = fetch_all("SELECT salary_master_id FROM pay_jp_salary_master ORDER BY salary_master_id DESC LIMIT 1")
    next_num = 1
    if all_records:
        last_id = all_records[0].get("salary_master_id", "SM-JP-0000")
        try:
            next_num = int(last_id.split("-")[-1]) + 1
        except (ValueError, IndexError):
            next_num = len(existing) + 1

    for emp_id in selected_ids:
        if emp_id in existing_ids:
            skipped += 1
            continue

        ea = fetch_one("SELECT * FROM emp_employees WHERE employee_id=%s", (emp_id,))
        if not ea:
            continue

        payroll = ea.get("payroll", {})
        if isinstance(payroll, str):
            import json; payroll = json.loads(payroll)

        sm_id = f"SM-JP-{next_num:04d}"
        next_num += 1

        rec = {
            "salary_master_id": sm_id,
            "employee_id": ea["employee_id"],
            "employee_number": ea.get("employee_number", ""),
            "employee_name": payroll.get("employee_name", ea.get("display_name", "")),
            "email": ea.get("email", ""),
            "entity_id": payroll.get("entity_id", "ENT-0004"),
            "department_label": payroll.get("department_label", ""),
            "team_label": payroll.get("team_label", ""),
            "salary_type": payroll.get("salary_type", "monthly"),
            "basic_salary": float(payroll.get("basic_salary", 0) or 0),
            "hourly_rate": float(payroll.get("hourly_rate", 0) or 0),
            "daily_rate": float(payroll.get("daily_rate", 0) or 0),
            "standard_work_days": int(payroll.get("standard_work_days", 22) or 22),
            "standard_work_hours": int(payroll.get("standard_work_hours", 176) or 176),
            "standard_monthly_hours": int(payroll.get("standard_monthly_hours", 160) or 160),
            "commute_allowance": float(payroll.get("commute_allowance", 0) or 0),
            "transport_allowance": float(payroll.get("transport_allowance", 0) or 0),
            "phone_allowance": float(payroll.get("phone_allowance", 0) or 0),
            "project_bonus": float(payroll.get("project_bonus", 0) or 0),
            "social_insurance_eligible": payroll.get("social_insurance_eligible", True),
            "employment_insurance_eligible": payroll.get("employment_insurance_eligible", True),
            "age_at_fiscal_year_start": int(payroll.get("age_at_fiscal_year_start", 0) or 0),
            "active": True,
            "source": "employeeadmin",
            "created_at": now_iso(), "updated_at": now_iso(),
        }
        cols = list(rec.keys())
        ph = ",".join(["%s"] * len(cols))
        vals = tuple(rec.get(c) for c in cols)
        execute(f"INSERT INTO {TABLE}({','.join(cols)}) VALUES({ph})", vals)
        imported += 1

    return {"ok": True, "imported": imported, "skipped": skipped}


@router.get("/{sm_id}")
async def get_master(sm_id: str):
    row = fetch_one(f"SELECT * FROM {TABLE} WHERE salary_master_id=%s", (sm_id,))
    if not row: raise HTTPException(404, "Not found")
    return row

@router.post("/")
async def create_master(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    # Auto-generate salary_master_id
    rows = fetch_all(f"SELECT COUNT(*) as c FROM {TABLE}")
    next_num = rows[0]["c"] + 1
    body["salary_master_id"] = f"SM-JP-{next_num:04d}"
    body["created_at"] = now_iso()
    body["updated_at"] = now_iso()

    cols = list(body.keys())
    ph = ",".join(["%s"]*len(cols))
    vals = tuple(body.get(c) for c in cols)
    row = execute_returning(f"INSERT INTO {TABLE}({','.join(cols)}) VALUES({ph}) RETURNING *", vals)
    return row

@router.put("/{sm_id}")
async def update_master(sm_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    # Only allow updating editable columns
    updates = {k: v for k, v in body.items() if k in EDITABLE_COLS}
    if not updates: raise HTTPException(400, "No editable fields provided")
    # employee_number change requires special permission
    if "employee_number" in updates:
        has_perm = await check_permission(request, "tacaipay_jp.salary_master.edit_employee_number")
        if not has_perm:
            raise HTTPException(403, "Permission denied: edit_employee_number required to change employee number")
    updates["updated_at"] = now_iso()
    sets = ",".join(f"{k}=%s" for k in updates.keys())
    vals = tuple(updates.values()) + (sm_id,)
    row = execute_returning(f"UPDATE {TABLE} SET {sets} WHERE salary_master_id=%s RETURNING *", vals)
    if not row: raise HTTPException(404, "Not found")
    return row

@router.delete("/{sm_id}")
async def deactivate_master(sm_id: str, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    reason = body.get("reason", "deactivated")
    user_name = user.get("display_name", "system")
    execute(f"UPDATE {TABLE} SET active=false, deactivated_at=%s, deactivated_by=%s, deactivation_reason=%s, updated_at=%s WHERE salary_master_id=%s",
            (now_iso(), user_name, reason, now_iso(), sm_id))
    return {"ok": True}

# ── Calculation preview ──
from services.calculation import calc_salary_preview

@router.get("/{sm_id}/calc-preview")
async def calc_preview(sm_id: str, actual_hours: float=160, actual_days: float=22):
    """Preview salary calculation for a given employee."""
    row = fetch_one(f"SELECT * FROM {TABLE} WHERE salary_master_id=%s", (sm_id,))
    if not row: raise HTTPException(404, "Not found")
    result = calc_salary_preview(row, actual_hours=actual_hours, actual_days=actual_days)
    result["employee"] = {"name": row["employee_name"], "number": row["employee_number"], "salary_type": row["salary_type"]}
    return result
