"""Social Insurance Rates CRUD router."""
from fastapi import APIRouter, Request, HTTPException, Query
from typing import Optional
from auth import get_current_user
from database import fetch_all, fetch_one, execute, execute_returning

router = APIRouter(prefix="/api/parameters/social-insurance-rates", tags=["Social Insurance"])

TABLE = "pay_jp_social_insurance_rates"
COLUMNS = ["rate_type","prefecture","employee_rate","employer_rate","applicable_from","applicable_to","is_current","notes"]

@router.get("/")
async def list_rates(rate_type: Optional[str]=None, prefecture: Optional[str]=None, is_current: Optional[bool]=None):
    where = ["1=1"]; params = []
    if rate_type: where.append("rate_type=%s"); params.append(rate_type)
    if prefecture: where.append("prefecture=%s"); params.append(prefecture)
    if is_current is not None: where.append("is_current=%s"); params.append(is_current)
    sql = f"SELECT * FROM {TABLE} WHERE {' AND '.join(where)} ORDER BY rate_type, prefecture NULLS FIRST"
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
    cols = ",".join(COLUMNS)
    ph = ",".join(["%s"]*len(COLUMNS))
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
    # Soft delete: set applicable_to = today
    execute(f"UPDATE {TABLE} SET applicable_to=CURRENT_DATE, is_current=false, updated_at=NOW() WHERE id=%s", (rate_id,))
    return {"ok": True}
