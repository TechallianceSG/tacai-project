# TACAI Portal Integration Roadmap

Last updated: 2026-06-19

## Current integration status

Completed:

1. TACAI Portal runs on `8005`.
2. User_admin runs on `8006`.
3. Portal `User Management` opens the actual User_admin dashboard.
4. User_admin login supports a safe local `next` return parameter.
5. User_admin logout supports a safe local `next` return parameter.
6. Portal protected pages validate User_admin `tacai_session_id` through User_admin `/api/validate-session`.
7. Portal module navigation is driven by `database/modules.json`.
8. Portal filters module visibility using User_admin permissions.
9. Employee Mgmt, Timesheet, Expense, and Payroll launchers are connected.
10. Employee Mgmt, Timesheet, Expense, and Payroll now enforce User_admin session/module access before serving business pages.
11. Master Data Management is connected on port `8007` and appears before User Management.
12. Entity-scoped login/session context is implemented in User_admin foundation; Portal now requires `user.entity` from `/api/validate-session` before serving protected pages.
13. InterviewReady is registered as a connected module on port `8000`, placed between Expense and Master Data Management, and controlled by `interview_ready.access`.

## Step 5 — Permission-based Portal navigation

Goal: Show Portal modules only when the logged-in User_admin user has access.

Implementation tasks:

1. Define required module permission keys:
   - `user_management.access`
   - `employee_management.access`
   - `timesheet.access`
   - `payroll.access`
   - `reimbursement.access`
2. Add required permission metadata to each Portal navigation item.
3. Filter Portal cards/sidebar based on User_admin `permissions` returned by `/api/validate-session`.
4. Keep Dashboard visible for any authenticated user.
5. Add a clear `No available modules` state if the user has no module permissions.

Validation:

- System Admin sees all modules.
- HR Manager sees only employee/timesheet-related modules according to assigned permissions.
- Employee sees only employee-appropriate modules.

## Step 6 — Centralized module configuration

Goal: Remove hardcoded module URLs from Portal code.

Implementation tasks:

1. Create `database/modules.json` or `config/modules.json`.
2. Store module metadata:
   - module key
   - display label
   - description
   - URL
   - status
   - required permission
   - enabled flag
3. Load module configuration at runtime.
4. Keep disabled modules hidden or marked as unavailable.

Validation:

- Changing a module URL in JSON updates the Portal without code changes.
- Disabled modules do not appear in navigation.

## Step 7 — Employee Mgmt integration

Goal: Connect Portal `Employee Mgmt` to the actual TAC EmployeeAdmin module.

Implementation tasks:

1. Point Portal Employee Mgmt to `http://127.0.0.1:8004/dashboard` or `/employees`.
2. Add User_admin session validation to `TAC-employeeadmin`.
3. Protect all EmployeeAdmin pages with `tacai_session_id` validation.
4. Require `employee_management.access` for basic access.
5. Add finer permission checks later:
   - `employee_management.view`
   - `employee_management.edit`
   - `employee_management.payroll.view`
   - `employee_management.visa.view`
   - `employee_management.documents.manage`

Validation:

- User with `employee_management.access` can enter EmployeeAdmin.
- User without access is redirected to User_admin login or shown 403.
- Direct URL access to EmployeeAdmin is also protected.

## Step 8 — Timesheet, Payroll, and Expense integration

Goal: Connect remaining TAC modules using the same pattern.

Recommended order:

1. Timesheet on `8002` with `timesheet.access`.
2. Expense/Reimbursement on `8003` with `reimbursement.access`.
3. Payroll/HR Finance on `8001` with `payroll.access`.

For each module:

1. Add Portal module URL.
2. Add module-level permission visibility.
3. Add in-module User_admin session validation.
4. Add in-module feature-level permission checks.
5. Add audit logs for permission-sensitive actions.

## Step 9 — Entity context display and launch behavior

Status: foundation implemented on 2026-06-19 for Portal/User_admin session context; downstream business module data filtering remains Step 10.

Goal: Make Portal visibly entity-aware after User_admin adds Entity-scoped sessions.

Implemented tasks:

1. Read `entity_id`, `entity_code`, and Entity display name from User_admin `/api/validate-session`.
2. Show the current Entity in the Portal header and dashboard.
3. Keep Dashboard visible for any authenticated session with a valid Entity.
4. Launch connected modules with the same `tacai_session_id`; modules must read Entity context from User_admin rather than from query strings.
5. Preserve `lang=ja|zh|en` when launching connected modules, including absolute local module URLs.
6. Do not append `entity_id` or `entity_code` to Portal/module URLs; Entity context is session-sourced only.
7. Require logout/re-login to switch Entity in the local MVP.
8. Add clear messaging if a session is valid but missing Entity context after the User_admin migration.

Validation:

- Portal shows current Entity after login.
- Employee Mgmt, Timesheet, Payroll, Expense, and Master Data open under the same Entity context.
- A session without Entity context is rejected or sent back to User_admin login after the migration cutover.

## Step 10 — Business module entity-scope rollout

Goal: All connected modules should filter and create data under the current login Entity.

Recommended order:

1. Master Data Management.
2. Employee Mgmt.
3. Timesheet.
4. Payroll.
5. Expense.

Validation:

- Entity A login cannot see Entity B operational data.
- Audit logs include current Entity context where available.
- Existing records are backfilled to a default Entity before strict filtering is enabled.

## Step 11 — Cleanup and hardening

Goal: Prepare the local MVP for safer operation.

Tasks:

1. Remove or archive Portal legacy local user/session code after confirming no fallback is needed.
2. Add manual test checklist for Portal/User_admin integration.
3. Add unavailable-service handling when User_admin is down.
4. Add clearer error page for expired sessions.
5. Add CSRF protection for state-changing forms.
6. Add secure deployment notes for production HTTPS/cookies.
7. Consider shared local config for service URLs and ports.

## Step 10 — Future production decisions

Pending decisions:

1. Whether TACAI modules remain separate services or become a single app.
2. Whether Portal should reverse-proxy modules or open them directly by URL.
3. Whether User_admin becomes a true SSO/OIDC-style provider in the future.
4. Whether JSON storage remains acceptable or should move to a database.
5. How audit logs will be centralized across modules.
