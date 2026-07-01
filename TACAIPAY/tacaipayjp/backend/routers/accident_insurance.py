"""Workers Accident Insurance Rates CRUD router."""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from auth import get_current_user
from database import fetch_all, fetch_one, execute, execute_returning

router = APIRouter(prefix="/api/parameters/accident-insurance-rates", tags=["Accident Insurance"])

TABLE = "pay_jp_accident_insurance_rates"
COLUMNS = ["industry_code","industry_name_ja","industry_name_en","rate","applicable_from","applicable_to","is_current","notes"]

@router.get("/")
async def list_rates(industry_code: Optional[str]=None, is_current: Optional[bool]=None):
    where = ["1=1"]; params = []
    if industry_code: where.append("industry_code=%s"); params.append(industry_code)
    if is_current is not None: where.append("is_current=%s"); params.append(is_current)
    sql = f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY industry_code"
    rows = fetch_all(sql, tuple(params) if params else None)
    return {"data": rows, "count": len(rows)}

@router.get("/{rate_id}")
async def get_rate(rate_id: int):
    row = fetch_one(f"SELECT * FROM {TABLE} WHERE id=%s", (rate_id,))
    if not row: raise HTTPException(404, "Not found")
    return row

@router.post("/")
async def create_rate(request: Request):
    user = await get_current_user(request)
    body = await request.json()
    cols = ",".join(COLUMNS); ph = ",".join(["%s"]*len(COLUMNS))
    vals = tuple(body.get(c) for c in COLUMNS)
    row = execute_returning(f"INSERT INTO {TABLE}({cols}) VALUES({ph}) RETURNING *", vals)
    return row

@router.put("/{rate_id}")
async def update_rate(rate_id: int, request: Request):
    user = await get_current_user(request)
    body = await request.json()
    sets = ",".join(f"{c}=%s" for c in COLUMNS)
    vals = tuple(body.get(c) for c in COLUMNS) + (rate_id,)
    row = execute_returning(f"UPDATE {TABLE} SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *", vals)
    if not row: raise HTTPException(404, "Not found")
    return row

@router.delete("/{rate_id}")
async def delete_rate(rate_id: int, request: Request):
    user = await get_current_user(request)
    execute(f"DELETE FROM {TABLE} WHERE id=%s", (rate_id,))
    return {"ok": True}
