# TACAI User Management Architecture

## Position in TACAI Workspace

TACAI User Management is the shared identity and authorization core for the whole TACAI workspace.

It is located under:

```text
TACAI-Core/User_admin
```

It is **not** only for TACAI-Core internal pages. It is intended to serve:

- `TAC-employeeadmin` — employee master/admin.
- `TAC-reimbursement` — employee reimbursement and expense.
- `TAC-timesheet` — timesheet and approval.
- `TACAI-PRJ` — payroll and HR finance.
- TACAI-Core internal modules.
- Future Training Management.
- Future Vendor Expense Management.
- Future Client Revenue Management.

## Logical Architecture

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
          ┌───────────────────┼────────────────────┐
          │                   │                    │
          ▼                   ▼                    ▼
  TAC-employeeadmin     TAC-timesheet       TAC-reimbursement
  Employee Master       Timesheet           Expense/Reimbursement
  Payroll/Visa Docs     Approval            Approval/Payment
          │                   │                    │
          └───────────────────┼────────────────────┘
                              ▼
                         TACAI-PRJ
                         Payroll / HR Finance
                              │
                              ▼
                         Future Modules
                         Training / Vendor Expense / Client Revenue
```

## Core Service Responsibilities

### Authentication

- Email + password login.
- Logout.
- Validate session.
- Password reset/change.
- Failed login tracking.
- Account lock.

### Authorization

- Check role.
- Check permission.
- Check module access.
- Resolve effective permissions from all assigned roles.

### User Profile

- User master data.
- Status.
- Language preference.
- Login metadata.

### Role Management

V1 roles:

- System Admin.
- HR Manager.
- Finance.
- Manager.
- Employee.

### Permission Management

- Module/action permission catalog.
- Role-permission mapping.
- User-role assignment.

### Session Management

- Session ID.
- Login time.
- Logout time.
- IP address.
- Browser.
- Device.
- Expiration.

### Audit Log

- Append-only security audit records.
- Login/logout audit.
- Password change audit.
- User creation/deactivation audit.
- Role/permission assignment audit.
- Session/security action audit.

## Business Module Integration Pattern

Each business module should integrate through a small adapter layer.

The adapter should provide:

```text
require_current_user(request)
require_permission(request, permission_key)
require_role(request, role_key)
require_module_access(request, module_key)
audit_with_current_user(action, before_value, after_value)
```

Business modules should not inspect password hashes or implement password validation. They should only validate sessions and permissions through User Management.

## Local MVP Architecture Direction

Initial implementation:

- Dependency-light.
- Python standard-library local web app.
- Local JSON database under `database/`.
- HTTP endpoints or service helper functions suitable for later adapters.

Production future:

- Production database.
- HTTPS deployment.
- MFA/SSO.
- Centralized deployment.
- Stronger session/token infrastructure.
