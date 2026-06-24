# TACAI Module Integration Contract

## Purpose

This contract defines the minimum behavior every TACAI/TAC business module must follow when integrating with `TACAI-Core/User_admin`.

## Required Module Behavior

Every integrated module must:

1. Validate the current session before protected route access.
2. Resolve the current user from User Management.
3. Check permissions before sensitive actions.
4. Check roles only through User Management.
5. Use current user identity and Entity context in audit records.
6. Treat `user.entity` from User Management as the only trusted Entity context.
7. Never accept `entity_id` or `entity_code` from query strings/forms as an authorization source.
8. Never implement its own password validation.
9. Never store user passwords.
10. Never bypass User Management for production access.

## Required Adapter Functions

Each module should expose or implement a small adapter wrapper:

```text
require_current_user(request)
require_permission(request, permission_key)
require_role(request, role_key)
require_module_access(request, module_key)
current_audit_user(request)
```

## User Context Shape

User Management should return a current user payload with at least:

```json
{
  "user_id": "USR-0001",
  "username": "terence",
  "display_name": "Terence",
  "email": "terence@example.com",
  "language_preference": "en",
  "roles": ["system_admin", "hr_manager"],
  "permissions": ["employee_management.access"],
  "entity": {
    "entity_id": "ENT-0001",
    "entity_code": "TAKK",
    "entity_name_en": "Tech Alliance KK",
    "entity_name_ja": "Tech Alliance株式会社",
    "entity_name_zh": "Tech Alliance KK"
  }
}
```

## Permission Check Request Shape

```json
{
  "session_id": "SES-0001",
  "permission_key": "employee_management.edit"
}
```

## Permission Check Response Shape

```json
{
  "allowed": true,
  "user_id": "USR-0001",
  "permission_key": "employee_management.edit",
  "reason": "role_permission_match"
}
```

## Module Access Request Shape

```json
{
  "session_id": "SES-0001",
  "module_key": "timesheet"
}
```

## Module Access Response Shape

```json
{
  "allowed": true,
  "user_id": "USR-0001",
  "module_key": "timesheet"
}
```

## Optional Session Activity Reporting

Integrated modules may include optional activity metadata when calling `/api/validate-session` or `/api/check-module-access`:

```json
{
  "session_id": "SES-0001",
  "module_key": "timesheet",
  "module_path": "/timesheets"
}
```

`module_key` is used by User_admin current-user monitoring to show which module the user most recently opened. `module_path` should contain only a path without query strings, request bodies, cookies, or sensitive parameters. Modules that do not report activity remain valid, but `/login-sessions` displays their current module as not reported.

## Audit Integration

After integration, business modules should record audit user from User Management.

Required audit fields:

- module.
- record_id.
- action.
- user.
- timestamp.
- before_value.
- after_value.

## Development Fallback Rule

A local development fallback actor may be used only before integration and must be clearly documented as non-production behavior.

Once a module is integrated, fixed actors such as `Admin` should be replaced with the current user from User Management where practical.
