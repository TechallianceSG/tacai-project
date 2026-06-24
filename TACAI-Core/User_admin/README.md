# TACAI User Management

TACAI User Management is the shared authentication and authorization core service for the TACAI workspace.

It is intended to serve:

- `TAC-employeeadmin`.
- `TAC-timesheet`.
- `TAC-reimbursement`.
- `TACAI-PRJ`.
- TACAI-Core internal modules.
- Future TACAI modules.

## Implemented Phase 0 + Sprint 1 Foundation

- Python standard-library local web app in `backend/app.py`.
- `/health` endpoint.
- English/Japanese i18n resources.
- Seeded V1 roles.
- Seeded permission catalog for current and future TAC modules.
- Seeded System Admin local bootstrap user.
- Password hash verification with PBKDF2-SHA256.
- Login and logout.
- Session creation and validation.
- Current user API.
- Permission, role, and module access check APIs.
- Failed login count and account lock.
- Password change page.
- System Admin dashboard.
- User list, role list, and audit log pages.
- Append-only user audit log records.

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006
```

## Health check

```bash
curl -s http://127.0.0.1:8006/health
```

Expected response:

```text
OK
```

## Portal login return support

User_admin login supports a local `next` parameter so TACAI Portal can send users to User_admin and receive them back after successful login.

Example:

```text
http://127.0.0.1:8006/login?next=http%3A%2F%2F127.0.0.1%3A8005%2Fdashboard
```

For safety, `next` only accepts relative paths or local TACAI development hosts/ports.

User_admin logout also supports a safe local `next` parameter so Portal can return users to its login entry after clearing the User_admin session:

```text
http://127.0.0.1:8006/logout?next=http%3A%2F%2F127.0.0.1%3A8005%2Flogin
```

## Initial local login

Local MVP bootstrap user:

```text
admin@tacai.local
```

The bootstrap password is for local MVP startup only. Change it from `/change-password` after first login.

## Main pages

- `/login` — login page.
- `/dashboard` — System Admin dashboard.
- `/users` — user list.
- `/roles` — role list.
- `/audit-logs` — user audit logs.
- `/change-password` — password change.

## API endpoints

- `GET /api/current-user`.
- `POST /api/validate-session`.
- `POST /api/check-permission`.
- `POST /api/check-role`.
- `POST /api/check-module-access`.
- `GET /api/roles`.
- `GET /api/permissions`.

## Database files

- `database/users.json`.
- `database/roles.json`.
- `database/permissions.json`.
- `database/user_role_mapping.json`.
- `database/role_permission_mapping.json`.
- `database/user_sessions.json`.
- `database/user_audit_logs.json`.

## Security notes

- Password hashes only; plaintext passwords are not stored in JSON.
- Sessions are local MVP session records.
- HTTPS, MFA, SSO, and production database are deferred until approved.
