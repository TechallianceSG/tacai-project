# TACAI User Management System — Enterprise Specification V1.0

## Project Name

TACAI User Management

## Purpose

User Management is a shared core service used by all TACAI modules and existing TAC business applications.

This module provides:

- User Authentication.
- User Authorization.
- Role Management.
- Permission Control.
- Login Security.
- Session Management.
- Audit Logging.

This is **not** a standalone business module. It is a platform service used by:

- `TAC-employeeadmin` — Employee Management.
- `TAC-reimbursement` — Employee Reimbursement / Expense.
- `TAC-timesheet` — Timesheet Management.
- `TACAI-PRJ` — Payroll / HR Finance.
- TACAI-Core internal functions.
- Future Training Management.
- Future Vendor Expense Management.
- Future Client Revenue Management.

## Architecture

```text
TACAI User Management
├── Authentication
├── Authorization
├── User Profile
├── Role Management
├── Permission Management
├── Session Management
└── Audit Log
        │
        ▼
TAC-employeeadmin
TAC-timesheet
TAC-reimbursement
TACAI-PRJ
TACAI-Core modules
Future Training
Future Vendor Expense
Future Client Revenue
```

## Supported Languages

All UI labels must support:

- English.
- Japanese.

Rules:

- Language switching must be available globally.
- No hardcoded labels.
- Use i18n resource files.

## User Roles — V1

Only support the following roles in V1.

### System Admin

Permissions:

- Full Access.
- User Management.
- Role Management.
- All Modules.

### HR Manager

Permissions:

- Employee Management.
- Payroll.
- Timesheet.
- Employee Reimbursement.

Restrictions:

- Cannot manage system users.

### Finance

Permissions:

- Payroll.
- Expense Payment.
- Financial Reports.

Restrictions:

- Cannot edit employee master data.

### Manager

Permissions:

- Timesheet Approval.
- Expense Approval.
- Team View.

Restrictions:

- Cannot access payroll data.

### Employee

Permissions:

- View Own Profile.
- Submit Timesheet.
- Submit Expense.
- View Own Payslip.

Restrictions:

- Cannot access other employees.

## User Master Fields

### Basic Information

- User ID.
- Username.
- Display Name.
- Email.
- Phone.
- Department.
- Position.
- Status.
- Language Preference.
- Created Date.
- Updated Date.

### Login Information

- Username.
- Password Hash.
- Password Last Changed.
- Last Login.
- Failed Login Count.
- Account Locked.
- Account Locked Date.

### User Status

- Active.
- Inactive.
- Locked.
- Suspended.
- Deleted — soft delete.

## Role Assignment

One user can have multiple roles.

Example:

```text
Terence
├── System Admin
└── HR Manager
```

## Permission Model

Use RBAC — Role Based Access Control.

Structure:

```text
User
 ↓
Role
 ↓
Permission
```

## Authentication

### V1

- Email + Password.

### Future V2

- MFA.
- Microsoft Authenticator.
- Google Authenticator.
- SSO.
- Azure AD.
- Google Workspace.

## Password Policy

- Minimum 8 characters.
- Must contain:
  - Uppercase.
  - Lowercase.
  - Number.
- Password expiration: 180 days.

## Session Management

Track:

- Session ID.
- Login Time.
- Logout Time.
- IP Address.
- Browser.
- Device.

## Audit Log Requirements

All actions must be logged.

Required fields:

- module.
- record_id.
- user.
- action.
- timestamp.
- before_value.
- after_value.

Examples:

- User Login.
- User Logout.
- Password Change.
- Role Assignment.
- User Creation.
- User Deactivation.

Audit records must never be deleted.

## Database Structure

```text
database/
├── users.json
├── roles.json
├── permissions.json
├── user_role_mapping.json
├── role_permission_mapping.json
├── user_sessions.json
└── user_audit_logs.json
```

## API Requirements

### Authentication Service

- Login.
- Logout.
- Validate Session.
- Reset Password.
- Change Password.
- Get Current User.

### Authorization Service

- Check Permission.
- Check Role.
- Check Module Access.

## Integration Requirements

### `TAC-employeeadmin`

- Must validate current user before access.
- Must check Employee Management permissions.
- Must check payroll/visa/document permissions for sensitive employee sections.

### `TAC-timesheet`

- Must validate current user.
- Must check submit/approval/team-view permissions.

### `TAC-reimbursement`

- Must validate current user.
- Must check submit/approval/payment permissions.

### `TACAI-PRJ`

- Must validate current user.
- Must check payroll and financial report permissions.

### Future Modules

- Future modules must use User Management APIs.
- No module should implement its own login system.

## Security Requirements

- Store password hashes only.
- Never store plain text passwords.
- Implement session timeout.
- Implement account lock after repeated login failures.
- Implement audit logging.
- Support HTTPS deployment.

## Dashboard

### System Admin Dashboard

- Total Users.
- Active Users.
- Locked Users.
- Recent Logins.
- Recent Failed Logins.
- Role Distribution.

## Development Priority

### Phase 0

- Shared service foundation.
- Integration contract.
- Permission catalog.

### Phase 1

- Database Design.
- User Authentication.
- Login Page.
- Password Management.

### Phase 2

- Role Management.
- Permission Management.
- Session Management.

### Phase 3

- Integration with `TAC-employeeadmin`.

### Phase 4

- Integration with `TAC-timesheet`.

### Phase 5

- Integration with `TAC-reimbursement`.

### Phase 6

- Integration with `TACAI-PRJ`.

### Phase 7

- Audit Log.
- Security Hardening.
- Admin Dashboard.

## Development Rules

- Keep dependency-light architecture.
- Use reusable service design.
- All modules must call User Management.
- Do not duplicate authentication logic in business modules.
- All future TACAI modules must integrate with this User Management service.
