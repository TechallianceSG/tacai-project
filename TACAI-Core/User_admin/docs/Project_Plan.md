# TACAI User Management Project Plan

## Project Objective

Build TACAI User Management as the shared identity, authentication, authorization, role, permission, session, and audit platform service for the full TACAI workspace.

This service is not limited to modules inside `TACAI-Core`. It must become the common user management layer for both TACAI-Core functions and existing TAC business applications:

- `TAC-employeeadmin` — Employee Management.
- `TAC-reimbursement` — Employee Reimbursement / Expense.
- `TAC-timesheet` — Timesheet Management.
- `TACAI-PRJ` — Payroll / HR Finance.
- Future TACAI-Core modules.
- Future Training Management.
- Future Vendor Expense Management.
- Future Client Revenue Management.

No business module should implement its own independent login/authentication system after integration.

## Product Principles

1. **Core shared service** — User Management is a platform service for all TACAI/TAC business modules, not a standalone business module.
2. **Central authentication** — login/session/password logic lives in User Management.
3. **Central authorization** — module access, role checks, and permission checks are resolved through User Management.
4. **RBAC first** — use User -> Role -> Permission.
5. **Business-module adapters** — each existing TAC app should integrate through a small adapter layer rather than duplicating login logic.
6. **Security by design** — never store plaintext passwords; audit all security-sensitive actions.
7. **Trilingual UI direction** — Simplified Chinese, Japanese, and English labels where useful, aligned with EmployeeAdmin and Master Data Management.
8. **Entity-scoped access** — login sessions should include the selected Entity so every module can filter and authorize data by Entity.
9. **Dependency-light first** — start with local JSON and reusable service functions; defer production DB/SSO until approved.
10. **Incremental integration** — do not break existing standalone apps; integrate one module at a time behind clearly defined checks.

## Phase 0 — Shared Service Foundation and Integration Contract

Status: implemented foundation.

Implemented scope:

- Local Python standard-library app in `backend/app.py`.
- `/health` endpoint.
- Simplified Chinese/Japanese/English i18n direction; current foundation started from English/Japanese and is being extended to `zh`.
- Local JSON persistence.
- Seeded V1 roles and permissions.
- Current user, session validation, role check, permission check, and module access APIs.
- Cross-project integration contract documentation.

## Phase 1 — User Authentication and Password Management

Status: implemented foundation.

Implemented scope:

- Seeded local System Admin bootstrap user.
- Email + password login.
- Planned enhancement: Entity Code + Email + Password login so sessions carry current Entity context.
- Password hash verification using PBKDF2-SHA256.
- Password hash stored in `users.json`; plaintext password is not stored in JSON.
- Failed login count.
- Account lock after repeated failed login attempts.
- Session creation and validation.
- Logout.
- Password change page.
- Login/logout/password/audit events.

Deferred Phase 1 items:

- User create/edit forms.
- Password reset workflow.
- Production password hashing/security review.

## Phase 2 — Role, Permission, and Authorization Service

Status: partially implemented foundation.

Implemented scope:

- V1 roles seeded.
- Permission catalog seeded.
- Role-permission mapping seeded.
- User-role mapping seeded for System Admin.
- Effective permissions resolve from active roles.
- APIs for role, permission, and module access checks.
- User list, role list, and dashboard visibility.

Deferred Phase 2 items:

- Role assignment UI.
- Permission management UI.
- User-role assignment workflow.

## Phase 3 — Integration Adapter for `TAC-employeeadmin`

Status: planned.

Reason:

`TAC-employeeadmin` contains employee master, payroll, visa, dispatch, skills, document metadata, and local document files. It should be the first business app to consume centralized user/session/role checks.

## Phase 4 — Integration Adapter for `TAC-timesheet`

Status: planned.

## Phase 5 — Integration Adapter for `TAC-reimbursement`

Status: planned.

## Phase 6 — Integration Adapter for `TACAI-PRJ`

Status: planned.

## Phase 7 — System Admin Dashboard and Security Hardening

Status: partially implemented dashboard foundation.

Implemented scope:

- Dashboard total users.
- Active users.
- Locked users.
- Active sessions.
- Recent logins.
- Recent failed logins.
- Role distribution.

Deferred:

- Security hardening review.
- HTTPS deployment notes.
- Production deployment model.

## Phase 8 — Entity-based Login and Authorization

Status: foundation implemented on 2026-06-19; strict downstream module filtering remains next-phase work.

Goal: make User_admin the source of both user identity and current Entity context for Portal and business modules.

Implemented foundation:

- Added `database/user_entity_mapping.json` so each user can be assigned to one or more active Entities.
- Required Entity Code on the login form together with Email and Password.
- Validates that the selected Entity exists in Masterdata, is active, and is assigned to non-System Admin users.
- Stores `entity_id`, `entity_code`, and trilingual Entity names in `user_sessions.json`.
- Returns current Entity context from `/api/validate-session` as `user.entity`, while keeping flat compatibility fields.
- Keeps System Admin powerful, but still requires selecting an active Entity at login in the local MVP; `ALL_ENTITIES` runtime mode remains deferred.
- Evaluates module access through a valid Entity-bearing session plus required permission; business modules still need their own strict Entity data filtering.
- Adds audit details for Entity-scoped login success/failure and session creation.

Recommended validation examples:

| Scenario | Expected result |
|---|---|
| User enters valid Entity Code, valid credentials, and has active assignment | Login succeeds. |
| User enters valid credentials but an unassigned Entity Code | Login fails. |
| User enters inactive/deleted Entity Code | Login fails. |
| System Admin enters any active Entity Code | Login succeeds. |
| Business module calls `/api/validate-session` | Response includes user, roles, permissions, `entity_id`, and `entity_code`. |

## Planned Local Port

```text
8006
```
