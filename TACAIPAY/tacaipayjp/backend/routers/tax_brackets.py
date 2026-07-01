"""Withholding Tax Brackets CRUD router."""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from auth import get_current_user
from database import fetch_all, fetch_one, execute, execute_returning

router = APIRouter(prefix="/api/parameters/tax-brackets", tags=["Tax Brackets"])

TABLE = "pay_jp_withholding_tax_brackets"
COLUMNS = ["table_type","min_salary","max_salary","tax_dep_0","tax_dep_1","tax_dep_2","tax_dep_3","tax_dep_4","tax_dep_5","tax_dep_6","tax_dep_7","applicable_from","applicable_to","is_current"]

@router.get("/")
async def list_brackets(table_type: Optional[str]=None, is_current: Optional[bool]=None):
    where = ["1=1"]; params = []
    if table_type: where.append("table_type=%s"); params.append(table_type)
    if is_current is not None: where.append("is_current=%s"); params.append(is_current)
    sql = f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY table_type, min_salary"
    rows = fetch_all(sql, tuple(params) if params else None)
    return {"data": rows, "count": len(rows)}

@router.get("/{bracket_id}")
async def get_bracket(bracket_id: int):
    row = fetch_one(f"SELECT * FROM {TABLE} WHERE id=%s", (bracket_id,))
    if not row: raise HTTPException(404, "Not found")
    return row

@router.post("/")
async def create_bracket(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    cols = ",".join(COLUMNS); ph = ",".join(["%s"]*len(COLUMNS))
    vals = tuple(body.get(c) for c in COLUMNS)
    row = execute_returning(f"INSERT INTO {TABLE}({cols}) VALUES({ph}) RETURNING *", vals)
    return row

@router.put("/{bracket_id}")
async def update_bracket(bracket_id: int, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    sets = ",".join(f"{c}=%s" for c in COLUMNS)
    vals = tuple(body.get(c) for c in COLUMNS) + (bracket_id,)
    row = execute_returning(f"UPDATE {TABLE} SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *", vals)
    if not row: raise HTTPException(404, "Not found")
    return row

@router.delete("/{bracket_id}")
async def delete_bracket(bracket_id: int, request: Request):
    user = await get_current_user(request)
    execute(f"DELETE FROM {TABLE} WHERE id=%s", (bracket_id,))
    return {"ok": True}
