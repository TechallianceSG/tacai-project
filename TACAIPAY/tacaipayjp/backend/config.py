"""TACAI Pay JP — Backend configuration from environment variables."""

import os

# Database
DB_HOST = os.environ.get("DB_HOST", "localhost").strip()
DB_PORT = int(os.environ.get("DB_PORT", "5432"))
DB_NAME = os.environ.get("DB_NAME", "tacai_dev").strip()
DB_USER = os.environ.get("DB_USER", "tacai_user").strip()
DB_PASS = os.environ.get("DB_PASS", "tacai123").strip()

# Server
DEFAULT_PORT = int(os.environ.get("TACAIPAYJP_PORT", "8017"))

# Host resolution
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"

# User_admin auth
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get(
    "USER_ADMIN_INTERNAL_BASE_URL",
    f"http://{TACAI_INTERNAL_HOST}:8006"
).strip().rstrip("/")

USER_ADMIN_PUBLIC_BASE_URL = os.environ.get(
    "USER_ADMIN_PUBLIC_BASE_URL",
    f"http://{TACAI_PUBLIC_HOST}:8006"
).strip().rstrip("/")

# Portal
PORTAL_BASE_URL = os.environ.get(
    "TACAI_PORTAL_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:8005"
).strip().rstrip("/")

# App
APP_BASE_URL = os.environ.get(
    "TACAIPAYJP_BASE_URL", f"http://{TACAI_PUBLIC_HOST}:{DEFAULT_PORT}"
).strip().rstrip("/")

# Required permissions
REQUIRED_MODULE_PERMISSION = "tacaipay_jp.access"

# Audit
USER_ACTOR = os.environ.get("TACAIPAYJP_ACTOR", "HR Payroll Admin").strip() or "HR Payroll Admin"
