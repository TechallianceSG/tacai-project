# TACAI User Management Cross-Project Integration Roadmap

## Purpose

This document clarifies how `TACAI-Core/User_admin` will become the shared user management service for existing and future TACAI/TAC modules.

The target is not only TACAI-Core internal functionality. User Management must also serve:

- `TAC-employeeadmin`.
- `TAC-reimbursement`.
- `TAC-timesheet`.
- `TACAI-PRJ`.

## Guiding Rules

1. Build User Management core first.
2. Do not duplicate authentication logic in business modules.
3. Add integration adapters to business modules gradually.
4. Preserve each module's existing local MVP workflows during transition.
5. Enforce permissions on sensitive data first.
6. Add Entity context to login/session validation before strict cross-module data isolation.
7. Replace fixed audit actors with current user identity where practical.

## Integration Order

### 1. User Management Core

Deliver:

- Login/logout.
- Session validation.
- Current user lookup.
- Role and permission resolution.
- Audit logging.
- Seeded V1 roles and permissions.

### 2. `TAC-employeeadmin`

Reason for first integration:

- Contains employee master data.
- Contains payroll/bank data.
- Contains visa/passport/residence status data.
- Contains employee document metadata and uploaded files.
- Already has audit logging that should later use current user identity.

Required checks:

- Session required before access.
- Employee Management access permission.
- Employee edit permission.
- Payroll view/edit permission.
- Document manage permission.
- Report/export permission.

### 3. `TAC-timesheet`

Reason:

- Timesheet approvals require manager/team permissions.
- Employees should only submit or view own timesheets unless authorized.

Required checks:

- Session required before access.
- Submit timesheet permission.
- Approve timesheet permission.
- Team view permission.
- Billing/invoice permission if applicable.

### 4. `TAC-reimbursement`

Reason:

- Expense submission, approval, and payment need clear role separation.

Required checks:

- Session required before access.
- Submit own reimbursement permission.
- Approve reimbursement permission.
- Expense payment permission.
- Financial report permission.

### 5. `TACAI-PRJ`

Reason:

- Payroll/HR finance workflows contain sensitive salary/payment data.

Required checks:

- Session required before access.
- Payroll view permission.
- Payroll edit permission.
- Financial report permission.
- HR finance admin permission.

### 6. Future Modules

Future modules must integrate with User Management from the first implementation:

- Training Management.
- Vendor Expense Management.
- Client Revenue Management.

## Adapter Pattern

Each module should add a small adapter layer that calls User Management.

Adapter responsibilities:

```text
get_current_user(request)
get_current_entity(request)
require_session(request)
require_entity_assignment(request, entity_id)
require_permission(request, permission_key)
require_role(request, role_key)
require_module_access(request, module_key)
audit_actor_from_session(request)
audit_entity_from_session(request)
```

The adapter should keep module code simple and avoid direct password/session implementation inside business modules.

## Local MVP Integration Options

### Option A — HTTP API Calls

Each business app calls User Management over local HTTP.

Pros:

- Clear service boundary.
- Closer to future deployment.

Cons:

- Requires User Management service to run alongside each business app.
- More local startup coordination.

### Option B — Shared Service Helper Library

Business apps import shared helper functions or copy a small adapter during local MVP.

Pros:

- Easier local MVP integration.
- Fewer running services.

Cons:

- Can blur service boundaries.
- Must avoid duplicating authentication logic long term.

### Recommended path

Start with HTTP-style service endpoints in User Management, while keeping helper functions internally reusable. Business modules should use a thin adapter that can later switch between local HTTP and production deployment.

## Permission Key Baseline

Recommended initial permission keys:

```text
user_management.access
user_management.manage_users
user_management.manage_roles
user_management.manage_permissions
employee_management.access
employee_management.edit
employee_management.payroll.view
employee_management.payroll.edit
employee_management.documents.manage
employee_management.reports.view
employee_management.export
timesheet.access
timesheet.submit
timesheet.edit_own
timesheet.approve
timesheet.team_view
reimbursement.access
reimbursement.submit
reimbursement.view_own
reimbursement.approve
reimbursement.payment
payroll.access
payroll.view
payroll.edit
financial_reports.view
```

## Key Migration Risks

- Existing apps currently assume local standalone access.
- Existing audit logs may use fixed actors like `Admin`.
- Sensitive pages must not be exposed during partial integration.
- Session/cookie strategy must work across local ports.
- Development fallback mode must not become production behavior.

## Recommended First Implementation Milestone

Before touching business modules, implement and verify in User Management:

1. `/health`.
2. login/logout.
3. session validation.
4. current user endpoint.
5. permission check endpoint.
6. seeded roles/permissions.
7. audit log.
8. System Admin dashboard placeholder.

Then integrate `TAC-employeeadmin` first.

## Entity-based Login and Authorization Milestone

Before strict Entity data isolation is enabled in business modules, User Management should add an Entity-scoped login/session model:

1. Add `user_entity_mapping.json` for User -> Entity assignment.
2. Add Entity Code to the login form.
3. Validate selected Entity exists, is active, and is assigned to the user.
4. Store `entity_id` and `entity_code` on each active session.
5. Return Entity context from `/api/validate-session`.
6. Require modules to combine permission checks with current Entity context.
7. Backfill existing business records to a default Entity before enforcing filtering.

Recommended MVP decision: even System Admin selects one active Entity at login. A cross-entity or `ALL_ENTITIES` mode should be designed separately later.
