#!/usr/bin/env python3
"""TACAI Portal local web app.

A lightweight standard-library portal for the future unified TACAI login window.
"""

from __future__ import annotations

import argparse
import html
import json
import os
from datetime import datetime, timezone
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import URLError
from urllib.parse import parse_qs, quote, urlencode, urlparse
from urllib.request import Request, urlopen

BASE_DIR = Path(__file__).resolve().parents[1]
DATABASE_DIR = BASE_DIR / "database"
FRONTEND_DIR = BASE_DIR / "frontend"
AUDIT_LOG_FILE = DATABASE_DIR / "audit_logs.json"
MODULES_FILE = DATABASE_DIR / "modules.json"
USER_ADMIN_SESSION_COOKIE = "tacai_session_id"
LANGUAGE_COOKIE = "tacai_portal_lang"
MODULE_NAME = "tacai-portal"
TACAI_PUBLIC_HOST = os.environ.get("TACAI_PUBLIC_HOST", "127.0.0.1").strip() or "127.0.0.1"
TACAI_INTERNAL_HOST = os.environ.get("TACAI_INTERNAL_HOST", "127.0.0.1").strip() or "127.0.0.1"
LOCAL_ALLOWED_HOSTS = {"127.0.0.1", "localhost", TACAI_PUBLIC_HOST, TACAI_INTERNAL_HOST}
LOCAL_ALLOWED_PORTS = {8000, 8001, 8002, 8003, 8004, 8005, 8006, 8007, 8008, 8009, 8011, 8012, 8015, 8016, 8017, 8018}
CONFIGURED_PUBLIC_HOSTS = {host.strip().lower() for host in os.environ.get("TACAI_ALLOWED_PUBLIC_HOSTS", "").split(",") if host.strip()}


def local_base_url(port: int) -> str:
    return f"http://{TACAI_PUBLIC_HOST}:{port}"


def internal_base_url(port: int) -> str:
    return f"http://{TACAI_INTERNAL_HOST}:{port}"


def public_base_url(env_name: str, fallback_port: int) -> str:
    return os.environ.get(env_name, local_base_url(fallback_port)).strip().rstrip("/")


def base_url_host(value: str) -> str:
    parsed = urlparse(value)
    return (parsed.hostname or "").lower()


PORTAL_BASE_URL = public_base_url("PORTAL_PUBLIC_BASE_URL", 8005)
USER_ADMIN_BASE_URL = public_base_url("USER_ADMIN_PUBLIC_BASE_URL", 8006)
USER_ADMIN_INTERNAL_BASE_URL = os.environ.get("USER_ADMIN_INTERNAL_BASE_URL", internal_base_url(8006)).strip().rstrip("/")
TACAIMSG_BASE_URL = public_base_url("TACAIMSG_PUBLIC_BASE_URL", 8012)
TACAIMSG_MESSAGES_PATH = BASE_DIR.parent / "tacaimsg" / "database" / "messages.json"
PUBLIC_ALLOWED_HOSTS = CONFIGURED_PUBLIC_HOSTS | {host for host in [base_url_host(PORTAL_BASE_URL), base_url_host(USER_ADMIN_BASE_URL)] if host}
SUPPORTED_LANGUAGES = {"ja", "zh", "en"}
DEFAULT_LANGUAGE = "ja"
LANGUAGE_LABELS = {
    "ja": "日本語",
    "zh": "中文",
    "en": "English",
}

TRANSLATIONS = {
    "ja": {
        "app.title": "TACAI Portal",
        "app.subtitle": "TACAI 業務モジュールへの統一入口",
        "login.title": "TACAI Portal",
        "login.subtitle": "TACAI の各業務システムへ安全にアクセスするための統一ログイン入口です。",
        "login.auth_note": "認証は TACAI User Management が担当します。ログイン後、あなたの権限に応じたモジュールだけを表示します。",
        "login.button": "TACAI User Management でログイン",
        "login.hint": "ログイン完了後、Portal ダッシュボードへ自動的に戻ります。",
        "unavailable.title": "User Management に接続できません",
        "unavailable.subtitle": "Portal は User_admin でログイン状態を確認しますが、現在サービスに接続できません。",
        "unavailable.hint": "ローカル検証では、先に以下のコマンドで User_admin を起動してください。",
        "unavailable.retry": "Portal を再試行",
        "dashboard.eyebrow": "Unified Entry",
        "dashboard.title": "ダッシュボード",
        "dashboard.hero_title": "TACAI Portal へようこそ",
        "dashboard.hero_text": "TACAI Portal は Employee Mgmt、Timesheet、Payroll、Expense、Message Center、User Management などの業務モジュールを一か所から開くための入口です。表示されるモジュールは User Management の権限設定に基づきます。",
        "dashboard.empty": "利用可能なモジュールがありません。システム管理者へお問い合わせください。",
        "logout": "ログアウト",
        "future_module.eyebrow": "Module Entry",
        "future_module.title_suffix": "TACAI Portal",
        "future_module.reserved": "このモジュール入口は準備済みです",
        "future_module.text": "Portal のナビゲーション構造を維持し、今後のモジュール統合に備えています。",
        "back_dashboard": "ダッシュボードへ戻る",
        "not_found.title": "ページが見つかりません",
        "not_found.text": "指定された Portal ページは存在しません。",
        "forbidden.title": "アクセスできません",
        "forbidden.text": "リクエスト元を確認できないため、操作を拒否しました。",
        "language.label": "表示言語",
        "entity.current": "現在の法人",
        "entity.required.title": "法人コンテキストが必要です",
        "entity.required.text": "現在のセッションには法人情報がありません。User Management から法人コードを指定して再ログインしてください。",
    },
    "zh": {
        "app.title": "TACAI Portal",
        "app.subtitle": "TACAI 业务模块统一入口",
        "login.title": "TACAI Portal",
        "login.subtitle": "用于安全进入 TACAI 各业务系统的统一登录入口。",
        "login.auth_note": "身份认证由 TACAI User Management 负责。登录后，Portal 会按照你的权限显示可访问模块。",
        "login.button": "使用 TACAI User Management 登录",
        "login.hint": "登录完成后会自动返回 Portal 仪表盘。",
        "unavailable.title": "无法连接 User Management",
        "unavailable.subtitle": "Portal 需要通过 User_admin 验证登录状态，但当前服务不可达。",
        "unavailable.hint": "本地验证时，请先用以下命令启动 User_admin。",
        "unavailable.retry": "重试 Portal",
        "dashboard.eyebrow": "统一入口",
        "dashboard.title": "仪表盘",
        "dashboard.hero_title": "欢迎使用 TACAI Portal",
        "dashboard.hero_text": "TACAI Portal 是 Employee Mgmt、Timesheet、Payroll、Expense、Message Center、User Management 等业务模块的统一入口。页面只会显示 User Management 权限设置允许你访问的模块。",
        "dashboard.empty": "当前没有可用模块。请联系系统管理员。",
        "logout": "退出登录",
        "future_module.eyebrow": "模块入口",
        "future_module.title_suffix": "TACAI Portal",
        "future_module.reserved": "此模块入口已预留",
        "future_module.text": "该页面用于保持 Portal 导航结构完整，并为后续模块集成做好准备。",
        "back_dashboard": "返回仪表盘",
        "not_found.title": "页面不存在",
        "not_found.text": "请求的 Portal 页面不存在。",
        "forbidden.title": "访问被拒绝",
        "forbidden.text": "请求来源未通过本地安全检查，操作已被拒绝。",
        "language.label": "显示语言",
        "entity.current": "当前法人",
        "entity.required.title": "需要法人上下文",
        "entity.required.text": "当前会话没有法人信息。请从 User Management 使用法人代码重新登录。",
    },
    "en": {
        "app.title": "TACAI Portal",
        "app.subtitle": "Unified entry point for TACAI business modules",
        "login.title": "TACAI Portal",
        "login.subtitle": "A secure unified login entry for TACAI business systems.",
        "login.auth_note": "Authentication is handled by TACAI User Management. After sign-in, Portal shows only the modules allowed by your permissions.",
        "login.button": "Sign in with TACAI User Management",
        "login.hint": "After login, User Management returns you to the Portal dashboard.",
        "unavailable.title": "User Management is unavailable",
        "unavailable.subtitle": "Portal validates your login through User_admin, but the service is not reachable right now.",
        "unavailable.hint": "For local testing, start User_admin first with the command below.",
        "unavailable.retry": "Retry Portal",
        "dashboard.eyebrow": "Unified Entry",
        "dashboard.title": "Dashboard",
        "dashboard.hero_title": "Welcome to TACAI Portal",
        "dashboard.hero_text": "TACAI Portal is the unified entry point for Employee Mgmt, Timesheet, Payroll, Expense, Message Center, User Management, and other TACAI modules. The modules shown here are filtered by User Management permissions.",
        "dashboard.empty": "No available modules. Please contact a system administrator.",
        "logout": "Logout",
        "future_module.eyebrow": "Module Entry",
        "future_module.title_suffix": "TACAI Portal",
        "future_module.reserved": "This module entry is ready",
        "future_module.text": "This page keeps the Portal navigation structure ready for future module integration.",
        "back_dashboard": "Back to dashboard",
        "not_found.title": "Page not found",
        "not_found.text": "The requested Portal page does not exist.",
        "forbidden.title": "Access denied",
        "forbidden.text": "The request origin could not be verified, so the action was rejected.",
        "language.label": "Language",
        "entity.current": "Current Entity",
        "entity.required.title": "Entity context required",
        "entity.required.text": "This session does not include Entity context. Please sign in again through User Management with an Entity Code.",
    },
}

DEFAULT_MODULES = [
    {
        "module_key": "dashboard",
        "label": "Dashboard",
        "labels": {"ja": "ダッシュボード", "zh": "仪表盘", "en": "Dashboard"},
        "description": "統合ダッシュボード / Unified dashboard",
        "descriptions": {
            "ja": "TACAI モジュールの統合ホーム",
            "zh": "TACAI 模块统一首页",
            "en": "Unified home for TACAI modules",
        },
        "url": "/dashboard",
        "status": "Portal home",
        "statuses": {"ja": "Portal ホーム", "zh": "Portal 首页", "en": "Portal home"},
        "required_permission": "",
        "enabled": True,
    },
    {
        "module_key": "tacaimsg",
        "label": "Message Center",
        "labels": {"ja": "メッセージセンター", "zh": "消息中心", "en": "Message Center"},
        "description": "メッセージ通知・承認ワークフロー",
        "descriptions": {
            "ja": "メッセージ受信箱、承認ワークフロー、通知管理",
            "zh": "消息收件箱、审批工作流、通知管理",
            "en": "Message inbox, approval workflows, and notification management",
        },
        "url": f"{TACAIMSG_BASE_URL}/dashboard",
        "status": "Connected module",
        "statuses": {"ja": "連携済み", "zh": "已连接模块", "en": "Connected module"},
        "required_permission": "tacaimsg.access",
        "enabled": True,
    },
    {
        "module_key": "selfservice",
        "label": "Employee Self-Service",
        "labels": {"ja": "従業員セルフサービス", "zh": "员工自助", "en": "Employee Self-Service"},
        "description": "休暇申請・承認管理",
        "descriptions": {
            "ja": "休暇申請（私用・病気・振替）、上司承認、HR承認、自動タイムアウト",
            "zh": "请假申请（事假/病假/调休）、主管审批、HR审批、超时自动处理",
            "en": "Leave requests (personal/sick/compensatory), supervisor approval, HR approval, auto-timeout",
        },
        "url": f"{public_base_url('SELFSERVICE_PUBLIC_BASE_URL', 8018)}/dashboard",
        "status": "Connected module",
        "statuses": {"ja": "連携済み", "zh": "已连接模块", "en": "Connected module"},
        "required_permission": "selfservice.access",
        "enabled": True,
    },
    {
        "module_key": "user_management",
        "label": "User Management",
        "labels": {"ja": "ユーザー管理", "zh": "用户管理", "en": "User Management"},
        "description": "ユーザー・ロール・権限管理",
        "descriptions": {
            "ja": "ユーザー、ロール、権限、セッションを管理",
            "zh": "管理用户、角色、权限和会话",
            "en": "Manage users, roles, permissions, and sessions",
        },
        "url": f"{USER_ADMIN_BASE_URL}/dashboard",
        "status": "Connected module",
        "statuses": {"ja": "連携済み", "zh": "已连接模块", "en": "Connected module"},
        "required_permission": "user_management.access",
        "enabled": True,
    },
]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default):
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def get_msg_center_unread_count(user_id: str) -> int:
    """Read tacaimsg messages.json and count unread messages for a user.

    Falls back gracefully if the messages file is unavailable.
    """
    try:
        messages = read_json(TACAIMSG_MESSAGES_PATH, [])
        return sum(1 for m in messages
                   if str(m.get("recipient_user_id", "")) == str(user_id)
                   and m.get("status") == "unread")
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return 0


def normalize_lang(value: str | None) -> str:
    if value in SUPPORTED_LANGUAGES:
        return value
    return DEFAULT_LANGUAGE


def translate(lang: str, key: str) -> str:
    normalized = normalize_lang(lang)
    return TRANSLATIONS.get(normalized, {}).get(key) or TRANSLATIONS["en"].get(key, key)


def localized_value(item: dict, plural_field: str, fallback_field: str, lang: str) -> str:
    values = item.get(plural_field, {})
    if isinstance(values, dict):
        value = values.get(normalize_lang(lang)) or values.get("en") or values.get(DEFAULT_LANGUAGE)
        if value:
            return str(value)
    return str(item.get(fallback_field, ""))


def module_label(item: dict, lang: str) -> str:
    return localized_value(item, "labels", "label", lang)


def module_description(item: dict, lang: str) -> str:
    return localized_value(item, "descriptions", "description", lang)


def module_status(item: dict, lang: str) -> str:
    return localized_value(item, "statuses", "status", lang)


def current_entity(user: dict) -> dict:
    entity = user.get("entity") if isinstance(user.get("entity"), dict) else {}
    if entity:
        return entity
    entity_id = str(user.get("entity_id", "")).strip()
    entity_code = str(user.get("entity_code", "")).strip()
    if not entity_id or not entity_code:
        return {}
    return {
        "entity_id": entity_id,
        "entity_code": entity_code,
        "entity_name_en": str(user.get("entity_name", "")),
    }


def has_entity_context(user: dict | None) -> bool:
    entity = current_entity(user or {})
    return bool(entity.get("entity_id") and entity.get("entity_code"))


def current_entity_label(user: dict, lang: str = DEFAULT_LANGUAGE) -> str:
    entity = current_entity(user)
    entity_code = str(entity.get("entity_code", "")).strip()
    entity_name = str(entity.get(f"entity_name_{normalize_lang(lang)}") or entity.get("entity_name_en") or entity.get("entity_name") or "").strip()
    if entity_code and entity_name:
        return f"{entity_code} - {entity_name}"
    return entity_code or entity_name


def with_lang(path_or_url: str, lang: str) -> str:
    normalized = normalize_lang(lang)
    parsed = urlparse(path_or_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query["lang"] = [normalized]
    return parsed._replace(query=urlencode(query, doseq=True)).geturl()


def public_local_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme in {"http", "https"} and parsed.hostname in {"127.0.0.1", "localhost"} and parsed.port in LOCAL_ALLOWED_PORTS:
        env_by_port = {
            8000: "INTERVIEW_READY_PUBLIC_BASE_URL",
            8001: "PAYROLL_PUBLIC_BASE_URL",
            8002: "TIMESHEET_PUBLIC_BASE_URL",
            8003: "EXPENSE_PUBLIC_BASE_URL",
            8004: "EMPLOYEE_ADMIN_PUBLIC_BASE_URL",
            8005: "PORTAL_PUBLIC_BASE_URL",
            8006: "USER_ADMIN_PUBLIC_BASE_URL",
            8007: "MASTERDATA_PUBLIC_BASE_URL",
            8008: "VENDOR_PAYABLES_PUBLIC_BASE_URL",
            8009: "CUSTOMER_BILLING_PUBLIC_BASE_URL",
            8011: "FILEADMIN_PUBLIC_BASE_URL",
            8012: "TACAIMSG_PUBLIC_BASE_URL",
            8015: "TAC_PAYROLL_PUBLIC_BASE_URL",
            8016: "TACAIPAYSG_PUBLIC_BASE_URL",
            8017: "TACAIPAYJP_PUBLIC_BASE_URL",
            8018: "SELFSERVICE_PUBLIC_BASE_URL",
        }
        env_name = env_by_port.get(parsed.port)
        if env_name and os.environ.get(env_name, "").strip():
            base = os.environ[env_name].strip().rstrip("/")
            path = parsed.path if parsed.path else ""
            return f"{base}{path}" + (("?" + parsed.query) if parsed.query else "")
        return parsed._replace(netloc=f"{TACAI_PUBLIC_HOST}:{parsed.port}").geturl()
    return url


def portal_url(path: str, lang: str) -> str:
    return f"{PORTAL_BASE_URL}{with_lang(path, lang)}"


def user_admin_login_url(lang: str) -> str:
    next_url = portal_url("/dashboard", lang)
    return f"{USER_ADMIN_BASE_URL}/login?next={quote(next_url, safe='')}"


def user_admin_logout_url(lang: str) -> str:
    next_url = portal_url("/login", lang)
    return f"{USER_ADMIN_BASE_URL}/logout?next={quote(next_url, safe='')}"


def language_switcher(current_path: str, lang: str) -> str:
    parsed = urlparse(current_path)
    query = parse_qs(parsed.query, keep_blank_values=True)
    links = []
    for code in ("ja", "zh", "en"):
        query["lang"] = [code]
        href = parsed.path + "?" + urlencode(query, doseq=True)
        classes = "active" if code == normalize_lang(lang) else ""
        links.append(
            f'<a class="{classes}" href="{html.escape(href)}">{html.escape(LANGUAGE_LABELS[code])}</a>'
        )
    return f"""
    <div class="language-switcher" aria-label="{html.escape(translate(lang, 'language.label'))}">
      <span>{html.escape(translate(lang, 'language.label'))}</span>
      {' '.join(links)}
    </div>
    """


def load_modules() -> list[dict]:
    modules = read_json(MODULES_FILE, DEFAULT_MODULES)
    if not isinstance(modules, list):
        return DEFAULT_MODULES
    normalized = []
    for item in modules:
        if not isinstance(item, dict) or not item.get("enabled", True):
            continue
        normalized.append(
            {
                "module_key": str(item.get("module_key", "")),
                "label": str(item.get("label", "")),
                "labels": item.get("labels", {}) if isinstance(item.get("labels", {}), dict) else {},
                "description": str(item.get("description", "")),
                "descriptions": item.get("descriptions", {}) if isinstance(item.get("descriptions", {}), dict) else {},
                "url": public_local_url(str(item.get("url", "#"))),
                "status": str(item.get("status", "")),
                "statuses": item.get("statuses", {}) if isinstance(item.get("statuses", {}), dict) else {},
                "required_permission": str(item.get("required_permission", "")),
                "enabled": bool(item.get("enabled", True)),
            }
        )
    return normalized or DEFAULT_MODULES


def visible_modules_for(user: dict) -> list[dict]:
    permissions = set(user.get("permissions", []))
    roles = set(user.get("roles", []))
    is_system_admin = "system_admin" in roles
    visible = []
    for item in load_modules():
        required_permission = item.get("required_permission", "")
        if not required_permission or is_system_admin or required_permission in permissions:
            visible.append(item)
    return visible


def write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)
        file.write("\n")


def append_audit_log(
    *,
    record_id: str,
    action: str,
    user: str,
    before_value,
    after_value,
) -> None:
    logs = read_json(AUDIT_LOG_FILE, [])
    logs.append(
        {
            "module": MODULE_NAME,
            "record_id": record_id,
            "action": action,
            "user": user,
            "timestamp": utc_now_iso(),
            "before_value": before_value,
            "after_value": after_value,
        }
    )
    write_json(AUDIT_LOG_FILE, logs)


def page_shell(title: str, body: str, lang: str = DEFAULT_LANGUAGE) -> str:
    return f"""<!doctype html>
<html lang="{html.escape(normalize_lang(lang))}">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)}</title>
  <link rel="stylesheet" href="/static/app.css">
</head>
<body>
{body}
</body>
</html>
"""


def user_admin_available() -> bool:
    try:
        with urlopen(f"{USER_ADMIN_INTERNAL_BASE_URL}/health", timeout=2) as response:
            return response.read().decode("utf-8").strip() == "OK"
    except (OSError, URLError):
        return False


def render_user_admin_unavailable(lang: str, current_path: str) -> str:
    body = f"""
<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">TACAI</div>
    {language_switcher(current_path, lang)}
    <h1>{html.escape(translate(lang, 'unavailable.title'))}</h1>
    <p class="muted">{html.escape(translate(lang, 'unavailable.subtitle'))}</p>
    <p class="hint">{html.escape(translate(lang, 'unavailable.hint'))}</p>
    <pre>cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006</pre>
    <p><a class="button-link" href="{html.escape(with_lang('/', lang))}">{html.escape(translate(lang, 'unavailable.retry'))}</a></p>
  </section>
</main>
"""
    return page_shell(translate(lang, "unavailable.title"), body, lang)


# Paths to User_admin database files (for role/permission resolution)
_USER_ADMIN_DB = BASE_DIR.parent / "User_admin" / "database"
_USER_ADMIN_USERS_PATH = _USER_ADMIN_DB / "users.json"
_USER_ADMIN_ROLES_PATH = _USER_ADMIN_DB / "roles.json"
_USER_ADMIN_PERMISSIONS_PATH = _USER_ADMIN_DB / "permissions.json"
_USER_ADMIN_URM_PATH = _USER_ADMIN_DB / "user_role_mapping.json"
_USER_ADMIN_RPM_PATH = _USER_ADMIN_DB / "role_permission_mapping.json"


def _resolve_user_roles_and_permissions(user_id: str) -> tuple[list[str], list[str]]:
    """Resolve role_keys and permission_keys for a user from User_admin mapping files."""
    role_keys: list[str] = []
    permission_keys: list[str] = []

    # Build role_id → role_key lookup
    role_id_to_key: dict[str, str] = {}
    try:
        roles = read_json(_USER_ADMIN_ROLES_PATH, [])
        for r in roles:
            rid = str(r.get("role_id", "")).strip()
            rkey = str(r.get("role_key", "")).strip()
            if rid and rkey:
                role_id_to_key[rid] = rkey
    except Exception:
        pass

    # Read user-role mappings
    try:
        urm = read_json(_USER_ADMIN_URM_PATH, [])
        user_role_ids: set[str] = set()
        for m in urm:
            if str(m.get("user_id", "")) == user_id and m.get("active", True):
                user_role_ids.add(str(m.get("role_id", "")).strip())
        role_keys = [role_id_to_key[rid] for rid in user_role_ids if rid in role_id_to_key]
    except Exception:
        pass

    # Read role-permission mappings and permission definitions
    try:
        rpm = read_json(_USER_ADMIN_RPM_PATH, [])
        permissions = read_json(_USER_ADMIN_PERMISSIONS_PATH, [])
        perm_id_to_key: dict[str, str] = {}
        for p in permissions:
            pid = str(p.get("permission_id", "")).strip()
            pkey = str(p.get("permission_key", "")).strip()
            if pid and pkey:
                perm_id_to_key[pid] = pkey

        # Get all permission_ids for the user's roles
        user_role_ids = {rid for rid in role_id_to_key if role_id_to_key[rid] in role_keys}
        for m in rpm:
            if str(m.get("role_id", "")) in user_role_ids and m.get("active", True):
                pkey = perm_id_to_key.get(str(m.get("permission_id", "")).strip(), "")
                if pkey:
                    permission_keys.append(pkey)
    except Exception:
        pass

    return role_keys, permission_keys


def validate_user_admin_session(session_id: str) -> dict | None:
    if not session_id:
        return None
    payload = json.dumps({"session_id": session_id}).encode("utf-8")
    request = Request(
        f"{USER_ADMIN_INTERNAL_BASE_URL}/api/validate-session",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(request, timeout=3) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (OSError, URLError, json.JSONDecodeError):
        return None
    if data.get("valid") and isinstance(data.get("user"), dict):
        user = data["user"]
        if isinstance(data.get("session"), dict):
            user["_session"] = data["session"]

        # Enrich user with resolved roles and permissions from mapping files
        # (User_admin may return empty roles/permissions on the user object itself,
        #  because role assignments are stored in separate mapping tables.)
        user_id = str(user.get("user_id", ""))
        if user_id:
            resolved_roles, resolved_perms = _resolve_user_roles_and_permissions(user_id)
            if resolved_roles:
                # Merge resolved roles with any existing ones
                existing_roles = set(user.get("roles", []))
                existing_roles.update(resolved_roles)
                user["roles"] = list(existing_roles)
            if resolved_perms:
                existing_perms = set(user.get("permissions", []))
                existing_perms.update(resolved_perms)
                user["permissions"] = list(existing_perms)
        return user
    return None


def render_login(lang: str, current_path: str, error: str = "") -> str:
    error_html = f'<div class="alert">{html.escape(error)}</div>' if error else ""
    body = f"""
<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">TACAI</div>
    {language_switcher(current_path, lang)}
    <h1>{html.escape(translate(lang, 'login.title'))}</h1>
    <p class="muted">{html.escape(translate(lang, 'login.subtitle'))}</p>
    {error_html}
    <p class="muted">{html.escape(translate(lang, 'login.auth_note'))}</p>
    <p><a class="button-link" href="{html.escape(user_admin_login_url(lang))}">{html.escape(translate(lang, 'login.button'))}</a></p>
    <p class="hint">{html.escape(translate(lang, 'login.hint'))}</p>
  </section>
</main>
"""
    return page_shell(translate(lang, "login.title"), body, lang)


def current_user_chip(user: dict, lang: str) -> str:
    session = user.get("_session") if isinstance(user.get("_session"), dict) else {}
    account = user.get("username") or user.get("email") or user.get("display_name") or "user"
    display_name = user.get("display_name") or account
    entity_code = user.get("entity_code") or session.get("entity", {}).get("entity_code", "")
    login_time = session.get("login_time_jst") or session.get("login_time") or "-"
    return f'''
    <div class="current-user-chip" title="Login: {html.escape(str(login_time))}">
      <strong>👤 {html.escape(str(account))}</strong>
      <span>{html.escape(str(display_name))}{(' · ' + html.escape(str(entity_code))) if entity_code else ''}</span>
      <small>Login: {html.escape(str(login_time))}</small>
    </div>
    '''


def render_dashboard(user: dict, lang: str, current_path: str) -> str:
    user_id = str(user.get("user_id", ""))
    unread_count = get_msg_center_unread_count(user_id)
    modules = visible_modules_for(user)
    cards = "\n".join(
        f"""
      <a class="module-card" href="{html.escape(with_lang(item['url'], lang))}">
        <span class="status">{html.escape(module_status(item, lang))}</span>
        <strong>{html.escape(module_label(item, lang))}{' <span style="background:#dc2626;color:#fff;border-radius:12px;padding:1px 8px;font-size:0.75rem;margin-left:6px;font-weight:700">' + str(unread_count) + '</span>' if item.get('module_key') == 'tacaimsg' and unread_count > 0 else ''}</strong>
        <small>{html.escape(module_description(item, lang))}</small>
      </a>
"""
        for item in modules
    )
    if not cards:
        cards = f'<div class="empty-state">{html.escape(translate(lang, "dashboard.empty"))}</div>'
    entity_label = current_entity_label(user, lang)
    entity_html = f'<span class="signed-in">{html.escape(translate(lang, "entity.current"))}: {html.escape(entity_label)}</span>' if entity_label else ""
    nav = "\n".join(
        f'<a href="{html.escape(with_lang(item["url"], lang))}">{html.escape(module_label(item, lang))}{" 🔴" if item.get("module_key") == "tacaimsg" and unread_count > 0 else ""}</a>' for item in modules
    )
    # Unread badge in header
    unread_badge = ""
    if unread_count > 0:
        unread_badge = f'<a href="{html.escape(with_lang(TACAIMSG_BASE_URL + "/messages/inbox", lang))}" style="background:#dc2626;color:#fff;border-radius:20px;padding:4px 12px;text-decoration:none;font-weight:700;font-size:0.85rem;display:inline-flex;align-items:center;gap:4px" title="Unread messages">📬 {unread_count}</a>'
    body = f"""
<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-title">{html.escape(translate(lang, 'app.title'))}</div>
    <p class="sidebar-subtitle">{html.escape(translate(lang, 'app.subtitle'))}</p>
    <nav>
      {nav}
    </nav>
  </aside>
  <main class="content">
    <header class="topbar">
      <div>
        <p class="eyebrow">{html.escape(translate(lang, 'dashboard.eyebrow'))}</p>
        <h1>{html.escape(translate(lang, 'dashboard.title'))}</h1>
      </div>
      <div class="topbar-actions">
        {unread_badge}
        {entity_html}
        {language_switcher(current_path, lang)}
        {current_user_chip(user, lang)}
        <form method="post" action="{user_admin_logout_url(lang)}">
          <button class="secondary" type="submit">{html.escape(translate(lang, 'logout'))}</button>
        </form>
      </div>
    </header>
    <section class="hero">
      <h2>{html.escape(translate(lang, 'dashboard.hero_title'))}</h2>
      <p>{html.escape(translate(lang, 'dashboard.hero_text'))}</p>
    </section>
    <section class="module-grid">
      {cards}
    </section>
  </main>
</div>
"""
    return page_shell(translate(lang, "dashboard.title"), body, lang)


def render_module_placeholder(user: dict, module_key: str, lang: str, current_path: str) -> str:
    modules = visible_modules_for(user)
    item = next((nav_item for nav_item in modules if nav_item["module_key"] == module_key), None)
    title = module_label(item, lang) if item else module_key.replace("-", " ").replace("_", " ").title()
    entity_label = current_entity_label(user, lang)
    entity_html = f'<span class="signed-in">{html.escape(translate(lang, "entity.current"))}: {html.escape(entity_label)}</span>' if entity_label else ""
    nav = "\n".join(
        f'<a href="{html.escape(with_lang(nav_item["url"], lang))}">{html.escape(module_label(nav_item, lang))}</a>' for nav_item in modules
    )
    body = f"""
<div class="app-shell">
  <aside class="sidebar">
    <div class="sidebar-title">{html.escape(translate(lang, 'app.title'))}</div>
    <p class="sidebar-subtitle">{html.escape(translate(lang, 'app.subtitle'))}</p>
    <nav>
      {nav}
    </nav>
  </aside>
  <main class="content">
    <header class="topbar">
      <div>
        <p class="eyebrow">{html.escape(translate(lang, 'future_module.eyebrow'))}</p>
        <h1>{html.escape(title)}</h1>
      </div>
      <div class="topbar-actions">
        {entity_html}
        {language_switcher(current_path, lang)}
        {current_user_chip(user, lang)}
        <form method="post" action="{user_admin_logout_url(lang)}">
          <button class="secondary" type="submit">{html.escape(translate(lang, 'logout'))}</button>
        </form>
      </div>
    </header>
    <section class="hero">
      <h2>{html.escape(translate(lang, 'future_module.reserved'))}</h2>
      <p>{html.escape(translate(lang, 'future_module.text'))}</p>
      <p><a href="{html.escape(with_lang('/dashboard', lang))}">{html.escape(translate(lang, 'back_dashboard'))}</a></p>
    </section>
  </main>
</div>
"""
    return page_shell(f"{title} - {translate(lang, 'future_module.title_suffix')}", body, lang)


def render_entity_required(lang: str) -> str:
    body = f"""
<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">TACAI</div>
    <h1>{html.escape(translate(lang, 'entity.required.title'))}</h1>
    <p class="muted">{html.escape(translate(lang, 'entity.required.text'))}</p>
    <p><a class="button-link" href="{html.escape(user_admin_logout_url(lang))}">{html.escape(translate(lang, 'logout'))}</a></p>
  </section>
</main>
"""
    return page_shell(translate(lang, "entity.required.title"), body, lang)


def render_simple_page(lang: str, title_key: str, text_key: str, status: HTTPStatus) -> tuple[str, HTTPStatus]:
    title = translate(lang, title_key)
    body = f"""
<main class="login-page">
  <section class="login-card">
    <div class="brand-mark">TACAI</div>
    <h1>{html.escape(title)}</h1>
    <p class="muted">{html.escape(translate(lang, text_key))}</p>
    <p><a class="button-link" href="{html.escape(with_lang('/', lang))}">{html.escape(translate(lang, 'back_dashboard'))}</a></p>
  </section>
</main>
"""
    return page_shell(title, body, lang), status


class PortalHandler(BaseHTTPRequestHandler):
    server_version = "TACAIPortal/0.1"

    def csrf_origin_allowed(self) -> bool:
        source = self.headers.get("Origin") or self.headers.get("Referer")
        if not source:
            return True
        parsed = urlparse(source)
        host = (parsed.hostname or "").lower()
        if host in LOCAL_ALLOWED_HOSTS and parsed.port in LOCAL_ALLOWED_PORTS:
            return True
        return parsed.scheme == "https" and host in PUBLIC_ALLOWED_HOSTS and parsed.port in {None, 443}

    def log_message(self, format: str, *args) -> None:  # noqa: A002 - inherited API name
        return

    def language_from_request(self, parsed) -> str:
        query = parse_qs(parsed.query, keep_blank_values=True)
        query_lang = query.get("lang", [None])[0]
        if query_lang in SUPPORTED_LANGUAGES:
            return query_lang
        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie(cookie_header)
        lang_cookie = cookies.get(LANGUAGE_COOKIE)
        if lang_cookie:
            return normalize_lang(lang_cookie.value)
        return DEFAULT_LANGUAGE

    def current_user(self) -> dict | None:
        cookie_header = self.headers.get("Cookie", "")
        cookies = SimpleCookie(cookie_header)
        session_cookie = cookies.get(USER_ADMIN_SESSION_COOKIE)
        if not session_cookie:
            return None
        return validate_user_admin_session(session_cookie.value)

    def send_html(self, html_text: str, status: HTTPStatus = HTTPStatus.OK, lang: str = DEFAULT_LANGUAGE) -> None:
        payload = html_text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Set-Cookie", f"{LANGUAGE_COOKIE}={normalize_lang(lang)}; SameSite=Lax; Path=/")
        self.end_headers()
        self.wfile.write(payload)

    def send_json(self, data: dict, status: HTTPStatus = HTTPStatus.OK) -> None:
        payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def redirect(self, location: str, lang: str = DEFAULT_LANGUAGE) -> None:
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        self.send_header("Set-Cookie", f"{LANGUAGE_COOKIE}={normalize_lang(lang)}; SameSite=Lax; Path=/")
        self.end_headers()

    def require_user(self, lang: str, current_path: str) -> dict | None:
        user = self.current_user()
        if user and has_entity_context(user):
            return user
        if user and not has_entity_context(user):
            self.send_html(render_entity_required(lang), HTTPStatus.FORBIDDEN, lang)
            return None
        if not user_admin_available():
            self.send_html(render_user_admin_unavailable(lang, current_path), HTTPStatus.SERVICE_UNAVAILABLE, lang)
            return None
        self.redirect(user_admin_login_url(lang), lang)
        return None

    def do_GET(self) -> None:  # noqa: N802 - inherited API name
        parsed = urlparse(self.path)
        path = parsed.path
        lang = self.language_from_request(parsed)

        if path == "/health":
            self.send_json({"status": "ok", "module": MODULE_NAME})
            return

        if path == "/static/app.css":
            css_path = FRONTEND_DIR / "app.css"
            payload = css_path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/css; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        if path == "/":
            if self.current_user():
                self.redirect(with_lang("/dashboard", lang), lang)
            else:
                self.send_html(render_login(lang, self.path), lang=lang)
            return

        if path == "/login":
            if self.current_user():
                self.redirect(with_lang("/dashboard", lang), lang)
            elif not user_admin_available():
                self.send_html(render_user_admin_unavailable(lang, self.path), HTTPStatus.SERVICE_UNAVAILABLE, lang)
            else:
                self.redirect(user_admin_login_url(lang), lang)
            return

        if path == "/dashboard":
            user = self.require_user(lang, self.path)
            if user:
                self.send_html(render_dashboard(user, lang, self.path), lang=lang)
            return

        if path.startswith("/modules/"):
            user = self.require_user(lang, self.path)
            if user:
                module_key = path.removeprefix("/modules/")
                self.send_html(render_module_placeholder(user, module_key, lang, self.path), lang=lang)
            return

        html_text, status = render_simple_page(lang, "not_found.title", "not_found.text", HTTPStatus.NOT_FOUND)
        self.send_html(html_text, status, lang)

    def do_POST(self) -> None:  # noqa: N802 - inherited API name
        parsed = urlparse(self.path)
        path = parsed.path
        lang = self.language_from_request(parsed)

        if not self.csrf_origin_allowed():
            html_text, status = render_simple_page(lang, "forbidden.title", "forbidden.text", HTTPStatus.FORBIDDEN)
            self.send_html(html_text, status, lang)
            return

        if path == "/login":
            self.redirect(user_admin_login_url(lang), lang)
            return

        if path == "/logout":
            self.redirect(user_admin_logout_url(lang), lang)
            return

        html_text, status = render_simple_page(lang, "not_found.title", "not_found.text", HTTPStatus.NOT_FOUND)
        self.send_html(html_text, status, lang)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run TACAI Portal local app")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8005)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    server = ThreadingHTTPServer((args.host, args.port), PortalHandler)
    print(f"TACAI Portal running on http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping TACAI Portal")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
