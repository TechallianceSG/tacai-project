"""Auth router — session check and login redirect."""
from fastapi import APIRouter, Request
from auth import get_current_user, get_login_url

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.get("/me")
async def auth_me(request: Request):
    user = await get_current_user(request)
    return {"authenticated": True, "user": user}

@router.get("/login-url")
async def login_url(request: Request):
    return_url = request.query_params.get("next", "/dashboard")
    return {"login_url": get_login_url(return_url)}
