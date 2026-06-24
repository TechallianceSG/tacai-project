# TACAI User Management API Requirements

## Purpose

These APIs define the shared contract that TACAI-Core and existing TAC business modules must call for authentication and authorization.

Target consumers:

- `TAC-employeeadmin`.
- `TAC-reimbursement`.
- `TAC-timesheet`.
- `TACAI-PRJ`.
- Future TACAI modules.

## Authentication Service

Required V1 operations:

- Login.
- Logout.
- Validate Session.
- Reset Password.
- Change Password.
- Get Current User.

### Planned Endpoint Shape

```text
POST /auth/login
POST /auth/logout
GET  /auth/current-user
POST /auth/validate-session
POST /auth/reset-password
POST /auth/change-password
```

## Authorization Service

Required V1 operations:

- Check Permission.
- Check Role.
- Check Module Access.
- Resolve Current User Permissions.

### Planned Endpoint Shape

```text
POST /authz/check-permission
POST /authz/check-role
POST /authz/check-module-access
GET  /authz/current-permissions
```

## Session Contract

Integrated modules must provide the User_admin `tacai_session_id` value to User Management. In the local MVP this is usually read from the shared `tacai_session_id` cookie and sent to `/api/validate-session`.

Entity Code is mandatory for new sessions. A valid session must include the selected current Entity. Consuming modules should not validate sessions independently and must treat `user.entity` from User_admin as the only trusted Entity context.

Example `/api/validate-session` response:

```json
{
  "valid": true,
  "user": {
    "user_id": "USR-0001",
    "email": "admin@tacai.local",
    "roles": ["system_admin"],
    "permissions": ["masterdata.access"],
    "entity": {
      "entity_id": "ENT-0001",
      "entity_code": "TAKK",
      "entity_name_en": "Tech Alliance KK",
      "entity_name_ja": "Tech Alliance株式会社",
      "entity_name_zh": "Tech Alliance KK"
    }
  }
}
```

## Permission Key Convention

Use stable permission keys:

```text
<module_key>.<action_key>
```

Examples:

```text
employee_management.access
employee_management.edit
employee_management.payroll.view
employee_management.documents.manage
timesheet.submit
timesheet.approve
timesheet.team_view
reimbursement.submit
reimbursement.approve
reimbursement.payment
payroll.view
payroll.edit
financial_reports.view
user_management.manage_users
user_management.manage_roles
```

## Module Access Keys

Recommended module keys:

- `user_management`.
- `employee_management`.
- `timesheet`.
- `reimbursement`.
- `payroll`.
- `financial_reports`.
- `training`.
- `vendor_expense`.
- `client_revenue`.

## Integration Contract by Project

### `TAC-employeeadmin`

Must call User Management to:

- Validate current session before access.
- Check `employee_management.access` for employee pages.
- Check `employee_management.edit` for create/edit.
- Check `employee_management.payroll.view` / `payroll.edit` for payroll fields.
- Check `employee_management.documents.manage` for employee documents.
- Check export/report permissions for sensitive reports.

### `TAC-timesheet`

Must call User Management to:

- Validate current session.
- Check `timesheet.submit` for own timesheet submission.
- Check `timesheet.approve` for approval.
- Check `timesheet.team_view` for team views.
- Restrict employee users to their own records.

### `TAC-reimbursement`

Must call User Management to:

- Validate current session.
- Check `reimbursement.submit` for own expense submissions.
- Check `reimbursement.approve` for approvals.
- Check `reimbursement.payment` for payment processing.
- Restrict employee users to their own claims.

### `TACAI-PRJ`

Must call User Management to:

- Validate current session.
- Check `payroll.view` for payroll pages.
- Check `payroll.edit` for payroll changes.
- Check `financial_reports.view` for reports.
- Restrict payroll-sensitive data to authorized roles only.

## Audit Contract

Integrated modules should include current user identity in their own audit logs after integration.

Required audit fields:

- module.
- record_id.
- action.
- user.
- timestamp.
- before_value.
- after_value.

User Management audit APIs may later centralize cross-module audit ingestion, but V1 can start with local audit logs plus current-user attribution.
