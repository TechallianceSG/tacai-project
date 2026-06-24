# TACAI Portal Project Plan

## Purpose

TACAI Portal will become the unified entry point for TACAI business modules.

Target navigation:

1. Dashboard
2. Employee Mgmt
3. Timesheet
4. Payroll
5. Expense
6. Master Data Management
7. User Management

Portal should display the current login Entity after User_admin adds Entity-scoped sessions. Portal remains the launcher, while User_admin remains the source of identity, permissions, and Entity context.

## Phase 1 — Portal skeleton

Status: complete

- Create standalone project directory.
- Add standard-library Python local web backend.
- Add local login page.
- Add dashboard shell and future module placeholders.
- Add local JSON user store.
- Add audit log file with required audit fields.

## Phase 2 — Authentication foundation

Status: planned

- Replace local demo password with user onboarding/reset flow.
- Add password change flow.
- Add session timeout.
- Define role-based access control model.
- Add CSRF protection for state-changing forms.

## Phase 3 — Module routing

Status: planned

- Decide whether modules are linked as separate local apps, reverse-proxied apps, or integrated backend routes.
- Add environment-based module URLs.
- Add unavailable-module handling.
- Add centralized navigation metadata.

## Phase 4 — User Management integration

Status: planned

- Connect Portal users and User Management users.
- Define role and permission schema.
- Validate User_admin `tacai_session_id` on protected Portal pages.
- Filter module cards by User_admin permissions.
- Add audit viewer or export for portal-level events.

## Phase 4B — Entity context integration

Status: planned.

- Read `entity_id`, `entity_code`, and display name from User_admin `/api/validate-session`.
- Show current Entity in Portal header/dashboard.
- Keep module URLs stable, but require connected modules to read Entity context from the same User_admin session.
- Require logout/re-login to switch Entity in the local MVP.
- Defer an `ALL_ENTITIES` Portal view until cross-entity reporting requirements are confirmed.

## Phase 5 — Production readiness

Status: planned

- Replace JSON persistence if multi-user concurrency is required.
- Add secure password hashing using a dedicated password hashing algorithm.
- Add HTTPS deployment plan.
- Add backup/restore plan for audit logs and user data.
