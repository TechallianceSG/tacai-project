# CLAUDE.md

This file provides guidance to Claude Code when working with the TACAI-Core/User_admin project.

Project Name: TACAI-Core/User_admin

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Project overview

User_admin implements the TACAI User Management shared core service. It is **not** a standalone business module. It is a platform service used by TACAI business modules for authentication, authorization, role management, permission control, login security, session management, and audit logging.

Target consuming modules include both TACAI-Core internal functions and existing TAC business projects:

- `TAC-employeeadmin` — Employee Management, payroll/visa/document-sensitive employee data.
- `TAC-reimbursement` — Employee Reimbursement / Expense.
- `TAC-timesheet` — Timesheet Management and approval.
- `TACAI-PRJ` — Payroll / HR Finance.
- Future Training Management.
- Future Vendor Expense Management.
- Future Client Revenue Management.

This project is independent from TAC-timesheet, TACAI-PRJ, TAC-reimbursement, TAC-employeeadmin, InterviewReady, and other sibling projects unless the user explicitly requests integration. However, the design intent is that these TAC business modules must eventually call User Management APIs instead of implementing or keeping their own login systems.

Primary specification and planning files:

- `docs/Enterprise_Specification_V1.md` — TACAI User Management System Enterprise Specification V1.0.
- `docs/Project_Plan.md` — revised cross-project implementation phases.
- `docs/Integration_Roadmap.md` — integration order for TAC-employeeadmin, TAC-timesheet, TAC-reimbursement, and TACAI-PRJ.
- `docs/Module_Integration_Contract.md` — minimum adapter/API contract for each business module.
- `docs/Permission_Catalog_V1.md` — baseline permission keys for current and future modules.

## Initial directory structure

- `backend/` — planned Python standard-library local web app entry point and route handling.
- `database/` — planned local JSON data files for users, roles, permissions, sessions, and audit logs.
- `docs/` — requirements, data schema, project plan, manual test checklist, and security notes.
- `frontend/` — reserved for static assets if the MVP grows beyond inline HTML.
- `i18n/` — bilingual UI labels, initially English/Japanese where useful.
- `prompts/` — prompt drafts or AI-assisted workflow notes if needed later.
- `memory/` — active project memory files.
- `archive/` — archived memory summaries and historical records.

## Planned commands

A runnable local MVP exists in `backend/app.py` using only Python standard-library modules.

Local port:

```text
8006
```

Run command:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006
```

Health check:

```bash
curl -s http://127.0.0.1:8006/health
```

Portal return-login smoke test:

```bash
curl -i "http://127.0.0.1:8006/login?next=http%3A%2F%2F127.0.0.1%3A8005%2Fdashboard"
```

Portal return-logout smoke test:

```bash
curl -i -X POST "http://127.0.0.1:8006/logout?next=http%3A%2F%2F127.0.0.1%3A8005%2Flogin"
```

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

No dependency installation, build, lint, or test suite is defined yet. Keep the MVP dependency-free unless the user approves adding package manifests or external libraries.

## Architecture direction

The first implementation should remain dependency-free and local-first unless the user approves otherwise.

Required modules:

- Authentication.
- Authorization.
- User Profile.
- Role Management.
- Permission Management.
- Session Management.
- Audit Log.
- System Admin Dashboard.

Required V1 roles:

- System Admin.
- HR Manager.
- Finance.
- Manager.
- Employee.

Required permission model:

```text
User -> Role -> Permission
```

Required local data files:

- `database/users.json` — user master records.
- `database/roles.json` — V1 role definitions.
- `database/permissions.json` — permission definitions or module/action matrix.
- `database/user_role_mapping.json` — user-role assignment records.
- `database/role_permission_mapping.json` — role-permission assignment records.
- `database/user_sessions.json` — login/session records.
- `database/user_audit_logs.json` — append-only user management audit trail.

## Development rules

- Keep the MVP dependency-free unless the user approves dependencies.
- Store local data under this project only.
- Keep labels bilingual where useful: English plus Japanese, and Chinese planning notes where helpful.
- Do not mix User_admin code/data with TAC-timesheet, TACAI-PRJ, TAC-reimbursement, TAC-employeeadmin, or InterviewReady unless explicitly requested.
- Treat user identity, password hashes, roles, permissions, sessions, and audit logs as sensitive data.
- Store password hashes only; never store plaintext passwords.
- V1 authentication is Email + Password.
- V1 local MVP password policy: 6 to 10 characters, must include uppercase English letter, lowercase English letter, and number. Password expiration enforcement remains deferred.
- Implement session timeout and account lock after repeated login failures.
- Use RBAC: User -> Role -> Permission.
- One user can have multiple roles.
- Use soft delete or status flags for user records instead of physical deletion unless the user explicitly approves deletion.
- Preserve auditability for login, logout, password changes, user changes, role assignments, permission changes, session changes, and user deactivation.
- All UI labels must support English and Japanese through i18n resource files; do not hardcode labels.
- Do not implement MFA, SSO, Azure AD, Google Workspace, or live integration until explicitly requested.

## MEMORY MANAGEMENT

The project must maintain a small active context window.

Memory Structure:

1. `memory/`
2. `archive/`

File Size Policy:

- Green Zone: 0KB - 30KB, normal operation.
- Yellow Zone: 30KB - 100KB, monitor growth and prepare for summarization.
- Red Zone: Over 100KB, archive and compress immediately.

Archive Rules:

When any file under `memory/` exceeds 100KB:

1. Create archive copy.
2. Generate concise summary.
3. Replace active memory file with summary.
4. Never delete archive records.

Archive Naming Convention:

```text
archive/<module>/<filename>_YYYY_MM.md
```

Loading Rules:

Do not automatically load archive files.

Only load:

1. `CLAUDE.md`.
2. `memory/project_status.md`.
3. `memory/current_tasks.md`.
4. Related module memory.

Memory Update Rules:

After every major task:

1. Update `memory/project_status.md`.
2. Update related module memory.
3. Update `memory/decisions.md` if architectural decisions were made.
4. Update `memory/changelog.md` if system changes occurred.

Historical Preservation Policy:

Never delete historical records. When summarizing, preserve key decisions, business rules, architecture decisions, implementation status, and unresolved issues.

## Audit Rules

All modules must implement audit logging.

Required fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Audit logs must never be deleted.

Audit logs are read-only.

Future centralized audit viewer may be added.
