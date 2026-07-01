"""Standard Remuneration Grades CRUD router."""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from auth import get_current_user
from database import fetch_all, fetch_one, execute, execute_returning

router = APIRouter(prefix="/api/parameters/remuneration-grades", tags=["Remuneration Grades"])

TABLE = "pay_jp_standard_remuneration_grades"
COLUMNS = ["grade_type","grade_number","min_monthly_amount","max_monthly_amount","standard_monthly_amount","applicable_from","applicable_to","is_current"]

@router.get("/")
async def list_grades(grade_type: Optional[str]=None, is_current: Optional[bool]=None):
    where = ["1=1"]; params = []
    if grade_type: where.append("grade_type=%s"); params.append(grade_type)
    if is_current is not None: where.append("is_current=%s"); params.append(is_current)
    sql = f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY grade_type, grade_number"
    rows = fetch_all(sql, tuple(params) if params else None)
    return {"data": rows, "count": len(rows)}

@router.get("/{grade_id}")
async def get_grade(grade_id: int):
    row = fetch_one(f"SELECT * FROM {TABLE} WHERE id=%s", (grade_id,))
    if not row: raise HTTPException(404, "Not found")
    return row

@router.post("/")
async def create_grade(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    cols = ",".join(COLUMNS); ph = ",".join(["%s"]*len(COLUMNS))
    vals = tuple(body.get(c) for c in COLUMNS)
    row = execute_returning(f"INSERT INTO {TABLE}({cols}) VALUES({ph}) RETURNING *", vals)
    return row

@router.put("/{grade_id}")
async def update_grade(grade_id: int, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    sets = ",".join(f"{c}=%s" for c in COLUMNS)
    vals = tuple(body.get(c) for c in COLUMNS) + (grade_id,)
    row = execute_returning(f"UPDATE {TABLE} SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *", vals)
    if not row: raise HTTPException(404, "Not found")
    return row

@router.delete("/{grade_id}")
async def delete_grade(grade_id: int, request: Request):
    user = await get_current_user(request)
    execute(f"DELETE FROM {TABLE} WHERE id=%s", (grade_id,))
    return {"ok": True}
