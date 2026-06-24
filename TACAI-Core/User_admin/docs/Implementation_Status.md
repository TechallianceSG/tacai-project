# TACAI User Management Implementation Status

## Updated

2026-06-19

## Implemented

Phase 0 + Sprint 1 foundation and the local admin workflow slice are implemented in `backend/app.py`.

Implemented capabilities:

- Local Python standard-library web app.
- `/health` endpoint.
- Simplified Chinese/Japanese/English i18n resource direction; English/Japanese existed first and `zh` support is being added in the trilingual foundation step.
- Local JSON persistence.
- Seeded V1 roles.
- Seeded permission catalog.
- Seeded System Admin local bootstrap user.
- Password hash verification using PBKDF2-SHA256.
- Entity Code + Email + Password login.
- User-Entity assignment storage in `database/user_entity_mapping.json`.
- Login/logout.
- Session creation, selected Entity storage, expiration timestamp, and validation.
- Current user API.
- Role check API.
- Permission check API.
- Module access check API.
- Failed login count.
- Account lock after repeated failed login attempts.
- Password change page.
- System Admin dashboard with user/session/audit metrics.
- User list.
- User create/edit forms.
- User deactivation and active-session revocation.
- User-role assignment from the user edit form.
- Role list.
- Role-permission management UI for non-System Admin roles.
- Last active System Admin lockout protection.
- Audit log page.
- Append-only user audit logs.

## Verified

- Python syntax check.
- JSON validation.
- App startup on port 8005.
- `/health` response.
- Login with seeded System Admin account.
- Session cookie creation.
- Current user API.
- Validate session API.
- Check role API.
- Check permission API.
- Check module access API.
- English pages.
- Japanese dashboard.
- Invalid login handling.

Latest admin workflow verification completed:

- Authenticated smoke page checks returned HTTP 200 for dashboard, users, user create/edit, roles, role-permission management, audit logs, and Japanese users/roles pages.
- Smoke test created a local test user, updated profile and role assignments, then deactivated that test user.
- Smoke test confirmed audit records for `user_created`, `user_updated`, `user_roles_updated`, and `user_deactivated`.
- Role-permission management page renders; permission update scenarios should still be reviewed manually before business-module integration.

## Deferred

- Password reset workflow.
- Password expiration enforcement.
- Production-grade password policy review.
- `/auth` and `/authz` API alias alignment.
- MFA.
- SSO.
- HTTPS deployment configuration.
- Production database.
- Integration into `TAC-employeeadmin`, `TAC-timesheet`, `TAC-reimbursement`, and `TACAI-PRJ`.
