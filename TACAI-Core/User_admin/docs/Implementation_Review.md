# User Management Implementation Review and Revised Plan

## Reason for Review

The original User_admin plan correctly defined TACAI User Management as a shared core service, but the integration scope must be clarified: it is not only for functions inside `TACAI-Core`. It must also serve existing TAC projects:

- `TAC-employeeadmin`.
- `TAC-reimbursement`.
- `TAC-timesheet`.
- `TACAI-PRJ`.

## Revised Direction

User Management should be implemented as the common identity and authorization layer for the whole TACAI workspace.

## Key Changes to Plan

1. Add explicit cross-project integration order.
2. Add module adapter contract.
3. Add baseline permission catalog for current and future modules.
4. Make `TAC-employeeadmin` the first integration target because it contains the most sensitive employee/payroll/visa/document data.
5. Keep existing business modules operational during migration.
6. Replace fixed audit actors with current User Management user during integration.

## Recommended Next Step

Implement User Management core first:

- local app skeleton.
- `/health`.
- i18n.
- seed roles/permissions.
- login/logout.
- session validation.
- permission check endpoint.
- audit logging.

Only after this core is verified should `TAC-employeeadmin` be modified to consume User Management.
