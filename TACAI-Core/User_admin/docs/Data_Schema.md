# TACAI User Management Data Schema V1

## Data Files

```text
database/
├── users.json
├── roles.json
├── permissions.json
├── user_role_mapping.json
├── user_entity_mapping.json
├── role_permission_mapping.json
├── user_sessions.json
└── user_audit_logs.json
```

## `users.json`

Top-level format: JSON array.

```json
[
  {
    "user_id": "USR-0001",
    "username": "terence",
    "display_name": "Terence",
    "email": "terence@example.com",
    "phone": "",
    "department": "",
    "position": "",
    "user_type": "employee",
    "linked_employee_id": "EMP-0001",
    "linked_employee_no": "TAKK240401",
    "linked_employee_name": "Terence",
    "linked_entity_id": "ENT-0001",
    "linked_entity_code": "TAKK",
    "linked_entity_name": "Tech Alliance KK",
    "linked_department_id": "DEP-0001",
    "linked_department_code": "PMO",
    "linked_department_name": "PMO",
    "status": "active",
    "language_preference": "en",
    "password_hash": "",
    "password_last_changed": "",
    "last_login": "",
    "failed_login_count": 0,
    "account_locked": false,
    "account_locked_date": "",
    "created_at": "",
    "updated_at": "",
    "deleted": false
  }
]
```

## User Status Values

- `active`.
- `inactive`.
- `locked`.
- `suspended`.
- `deleted` — soft delete.

## User Type and Employee Link Rules

- `user_type` must be one of `employee`, `admin`, `external`, or `system`.
- `employee` users must have `linked_employee_id` referencing TAC-employeeadmin `employee_id`.
- User_admin forms may resolve this link by manually entering or selecting EmployeeAdmin `employee_number`; if provided, the employee number must exist in EmployeeAdmin master data.
- `admin`, `external`, and `system` users may leave `linked_employee_id` blank.
- `linked_employee_id` is the stable link. `linked_employee_no`, `linked_employee_name`, `linked_entity_id`, `linked_entity_code`, `linked_entity_name`, `linked_department_id`, `linked_department_code`, and `linked_department_name` are denormalized display/snapshot fields.
- One active employee should be linked to at most one active User_admin account.
- When an employee link is saved, User_admin should ensure the employee's legal Entity is present in `user_entity_mapping` so login can resolve the correct legal-company context.
- `/api/validate-session` returns `employee_context` for linked users. Business modules should prefer `employee_context.employee_id` for access control and keep employee number/entity snapshots only for historical records.

## `roles.json`

V1 supported roles only:

```json
[
  {
    "role_id": "ROLE-SYSTEM-ADMIN",
    "role_name": "System Admin",
    "role_key": "system_admin",
    "description": "Full access to User Management and all modules.",
    "active": true
  }
]
```

V1 role keys:

- `system_admin`.
- `hr_manager`.
- `finance`.
- `manager`.
- `employee`.

## `permissions.json`

```json
[
  {
    "permission_id": "PERM-0001",
    "permission_key": "employee_management.access",
    "module": "employee_management",
    "action": "access",
    "description": "Access Employee Management"
  }
]
```

## `user_role_mapping.json`

One user can have multiple roles.

```json
[
  {
    "mapping_id": "URM-0001",
    "user_id": "USR-0001",
    "role_id": "ROLE-SYSTEM-ADMIN",
    "assigned_at": "",
    "assigned_by": "Admin",
    "active": true
  }
]
```

## `user_entity_mapping.json`

User_admin should assign users to one or more Master Data Management Entities. Login must select one active Entity context.

```json
[
  {
    "mapping_id": "UEM-0001",
    "user_id": "USR-0001",
    "entity_id": "ENT-0001",
    "entity_code": "TAJP",
    "active": true,
    "is_default": true,
    "assigned_at": "",
    "assigned_by": "Admin"
  }
]
```

Rules:

- A user may have multiple active Entity assignments.
- Login requires Entity Code + Email + Password.
- The selected Entity must exist in Master Data Management and must be active.
- Non-System Admin users must have an active mapping to the selected Entity.
- System Admin may select any active Entity in the local MVP, but the session still stores one current Entity.
- `ALL_ENTITIES` session mode is deferred.

## `role_permission_mapping.json`

```json
[
  {
    "mapping_id": "RPM-0001",
    "role_id": "ROLE-SYSTEM-ADMIN",
    "permission_id": "PERM-0001",
    "active": true
  }
]
```

## `user_sessions.json`

```json
[
  {
    "session_id": "SES-0001",
    "user_id": "USR-0001",
    "entity_id": "ENT-0001",
    "entity_code": "TAJP",
    "login_time": "",
    "logout_time": "",
    "ip_address": "",
    "browser": "",
    "device": "",
    "active": true,
    "expires_at": ""
  }
]
```

## `user_audit_logs.json`

Audit records are append-only and must never be deleted.

```json
[
  {
    "audit_id": "AUD-000001",
    "module": "user_management",
    "record_id": "USR-0001",
    "user": "Admin",
    "action": "user_created",
    "timestamp": "",
    "before_value": {},
    "after_value": {}
  }
]
```

Required fields:

- `module`.
- `record_id`.
- `action`.
- `user`.
- `timestamp`.
- `before_value`.
- `after_value`.

## Password Storage Rule

- Store password hashes only.
- Never store plaintext passwords.
- Password hashing policy must be confirmed before production use.

## Session Entity Context

`/api/validate-session` should return the selected login Entity context together with user, role, and permission data:

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
      "entity_code": "TAJP",
      "entity_name_en": "Tech Alliance Japan KK",
      "entity_name_ja": "テックアライアンス株式会社",
      "entity_name_zh": "Tech Alliance 日本株式会社"
    },
    "entity_id": "ENT-0001",
    "entity_code": "TAJP",
    "entity_name": "Tech Alliance Japan KK"
  }
}
```

Business modules should treat this Entity context as the default data scope.

## Language Values

- `en` — English.
- `ja` — Japanese.
- `zh` — Simplified Chinese.
