# TACAI Portal Data Schema

## database/users.json

Array of portal user records.

```json
{
  "id": "user-admin-local",
  "username": "admin",
  "display_name": "TACAI Administrator",
  "role": "portal_admin",
  "active": true,
  "password_salt": "tacai-portal-local-demo",
  "password_hash": "sha256-hash",
  "created_at": "2026-06-17T00:00:00+00:00",
  "updated_at": "2026-06-17T00:00:00+00:00"
}
```

### Fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | string | yes | Stable user record ID. |
| `username` | string | yes | Login ID, compared case-insensitively. |
| `display_name` | string | yes | Display name shown in the portal. |
| `role` | string | yes | Initial portal role. |
| `active` | boolean | yes | Whether the user may log in. |
| `password_salt` | string | yes | Local MVP password salt. |
| `password_hash` | string | yes | SHA-256 hash for local MVP only. |
| `created_at` | string | yes | ISO-8601 timestamp. |
| `updated_at` | string | yes | ISO-8601 timestamp. |

## database/audit_logs.json

Append-only array of audit log records.

```json
{
  "module": "tacai-portal",
  "record_id": "session-or-user-id",
  "action": "login_success",
  "user": "admin",
  "timestamp": "2026-06-17T00:00:00+00:00",
  "before_value": null,
  "after_value": {
    "username": "admin"
  }
}
```

### Required audit fields

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `module` | string | yes | Module name. |
| `record_id` | string | yes | Record/session/user identifier related to the action. |
| `action` | string | yes | Action name. |
| `user` | string | yes | User who performed the action. |
| `timestamp` | string | yes | UTC ISO-8601 timestamp. |
| `before_value` | any | yes | State before action. |
| `after_value` | any | yes | State after action. |

Audit logs must be treated as read-only history and must not be deleted.
