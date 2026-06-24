# TACAI User Management Requirements

## Scope

TACAI User Management is the shared core user service for the TACAI workspace. It is a platform service, not a standalone business module.

It must serve both TACAI-Core internal functions and existing TAC applications:

- `TAC-employeeadmin`.
- `TAC-reimbursement`.
- `TAC-timesheet`.
- `TACAI-PRJ`.

It must also support future TACAI modules:

- Training Management.
- Vendor Expense Management.
- Client Revenue Management.

## Core Capabilities

1. Authentication.
2. Authorization.
3. User Profile.
4. Role Management.
5. Permission Management.
6. Session Management.
7. Audit Logging.
8. System Admin Dashboard.

## Required Integrations

All TACAI/TAC business modules must use User Management for authentication and authorization:

- Employee Management from `TAC-employeeadmin`.
- Timesheet Management from `TAC-timesheet`.
- Payroll / HR Finance from `TACAI-PRJ`.
- Employee Reimbursement / Expense from `TAC-reimbursement`.
- Future Training Management.
- Future Vendor Expense Management.
- Future Client Revenue Management.

No business module should implement its own login system after integration.

## Language Requirements

- English UI labels.
- Japanese UI labels.
- Global language switch.
- No hardcoded labels.
- All labels must come from i18n resources.

## V1 Role Requirements

Only these roles are supported in V1:

- System Admin.
- HR Manager.
- Finance.
- Manager.
- Employee.

## RBAC Requirement

Use RBAC:

```text
User -> Role -> Permission
```

One user can have multiple roles.

## Module Permission Requirements

User Management must support permissions for:

- User Management.
- Employee Management.
- Timesheet.
- Payroll.
- Employee Reimbursement / Expense.
- Financial Reports.
- Future Training.
- Future Vendor Expense.
- Future Client Revenue.

## Authentication Requirements

V1:

- Email + password.
- Password hash only.
- Never store plain text passwords.

Future V2:

- MFA.
- Microsoft Authenticator.
- Google Authenticator.
- SSO.
- Azure AD.
- Google Workspace.

## Password Policy

- Minimum 8 characters.
- Must include uppercase, lowercase, and number.
- Password expiration is 180 days.

## Session Requirements

Track:

- Session ID.
- Login time.
- Logout time.
- IP address.
- Browser.
- Device.

## Audit Requirements

All actions must be logged. Audit records are append-only and must never be deleted.

Required audit fields:

- module.
- record_id.
- user.
- action.
- timestamp.
- before_value.
- after_value.

Example audited actions:

- User login.
- User logout.
- Password change.
- Role assignment.
- User creation.
- User deactivation.
- Permission check failures.
- Session invalidation.

## Security Requirements

- Store password hashes only.
- Never store plain text passwords.
- Implement session timeout.
- Implement account lock after repeated login failures.
- Implement audit logging.
- Support HTTPS deployment in production.

## Dashboard Requirements

System Admin Dashboard must show:

- Total users.
- Active users.
- Locked users.
- Recent logins.
- Recent failed logins.
- Role distribution.

## Migration Requirements

Integration must be incremental:

1. Build and verify User Management core first.
2. Integrate `TAC-employeeadmin` first due to sensitive employee/payroll/visa/document data.
3. Integrate `TAC-timesheet` for approval permissions.
4. Integrate `TAC-reimbursement` for expense approval/payment permissions.
5. Integrate `TACAI-PRJ` for payroll/HR finance permissions.
6. Future modules must integrate from the beginning.
