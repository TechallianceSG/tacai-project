"""TACAI Pay JP — Session validation via User_admin."""

from typing import Any

import httpx
from fastapi import HTTPException, Request

from config import (
    REQUIRED_MODULE_PERMISSION,
    USER_ADMIN_INTERNAL_BASE_URL,
    USER_ADMIN_PUBLIC_BASE_URL,
    APP_BASE_URL,
)


async def get_current_user(request: Request) -> dict[str, Any]:
    """Validate tacai_session_id cookie against User_admin and return user dict.

    Raises 401 if not authenticated, 403 if missing tacaipay_jp.access permission.
    """
    session_id = request.cookies.get("tacai_session_id")
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated — no session cookie")

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{USER_ADMIN_INTERNAL_BASE_URL}/api/validate-session",
                json={"session_id": session_id},
                timeout=5.0,
            )
            data = resp.json()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"User_admin unreachable: {exc}")

    if not data.get("valid"):
        raise HTTPException(status_code=401, detail="Session invalid or expired")

    user: dict = data.get("user") or {}
    if not user:
        raise HTTPException(status_code=401, detail="No user data in session")

    # Check module access permission
    perms: list[str] = user.get("permissions") or []
    if REQUIRED_MODULE_PERMISSION not in perms:
        raise HTTPException(status_code=403, detail=f"Missing permission: {REQUIRED_MODULE_PERMISSION}")

    return user


def get_login_url(return_url: str = "/") -> str:
    """Build User_admin login URL with ?next= pointing back to this app."""
    from urllib.parse import quote

    next_url = f"{APP_BASE_URL}{return_url}"
    return f"{USER_ADMIN_PUBLIC_BASE_URL}/login?next={quote(next_url, safe='')}"


async def check_permission(request: Request, permission_key: str) -> bool:
    """Check if current session has a specific permission."""
    session_id = request.cookies.get("tacai_session_id")
    if not session_id:
        return False
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{USER_ADMIN_INTERNAL_BASE_URL}/api/check-permission",
                json={"session_id": session_id, "permission_key": permission_key},
                timeout=5.0,
            )
            data = resp.json()
        return bool(data.get("allowed"))
    except Exception:
        return False
