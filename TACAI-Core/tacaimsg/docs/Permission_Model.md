# TACAI Message Center — Permission Model

## Overview

tacaimsg uses a role-based access control (RBAC) model with 8 granular permissions, validated
against TACAI User_admin session data. All permissions follow the `tacaimsg.<action>` naming
convention.

## Permission Catalog

| Permission Key | Scope | Required for |
|---|---|---|
| `tacaimsg.access` | Module entry | Access Message Center at all (Portal visibility gate) |
| `tacaimsg.view` | Read messages | Inbox, message detail, search, mark read/confirm |
| `tacaimsg.workflow` | Workflow CRUD | List, create, view workflows and workflow detail |
| `tacaimsg.approve` | Approval actions | Execute approve/reject/transfer on workflow steps |
| `tacaimsg.admin` | Template management | Create/edit workflow templates (admin function) |
| `tacaimsg.notify` | Send notifications | Create and send notification messages (Phase C) |
| `tacaimsg.delegate` | Delegation management | Create, view, cancel approval delegations |
| `tacaimsg.audit.view` | Audit log access | View audit trail of all message center actions |

## Role-Based Defaults

### System Admin (`system_admin` role)
- **Bypasses all permission checks** — full access to every feature.
- Can view all entities' data (not entity-scoped).

### Standard User (no special role)
- Requires individual permissions assigned by User_admin.
- Data scoped to their own entity (entity_id from session).

### Workflow Approver (e.g., `manager`, `finance`, `hr_manager` roles)
- Needs `tacaimsg.workflow` to see workflows list.
- Needs `tacaimsg.approve` to execute approval actions.
- Typically also needs `tacaimsg.view` for message inbox.

### Delegator
- Needs `tacaimsg.delegate` to create/manage delegations.
- Delegations auto-redirect workflow approval steps.

## Permission Hierarchy

```
tacaimsg.access          ← Gate: required for ALL other permissions
├── tacaimsg.view        ← Read-only message access
├── tacaimsg.workflow    ← Workflow list/detail access
│   └── tacaimsg.approve ← Execute approval actions
├── tacaimsg.admin       ← Template management
├── tacaimsg.notify      ← Send notifications (Phase C)
├── tacaimsg.delegate    ← Delegation management
└── tacaimsg.audit.view  ← Audit log access
```

## Implementation Notes

- Permission checks are performed by `has_permission(user, key)` in `app.py`.
- `system_admin` role always returns `True` for all permission checks.
- Wildcard `*` in the user's permissions set grants access to everything.
- `tacaimsg.access` is checked by `require_user()` for the top-level nav gate.
- Each sub-page route calls `require_user(specific_permission)` for granular control.
- Audit logs capture `user_name_snapshot` at time of action regardless of permission level.

## Data Scoping

- Non-admin users can only see messages sent to their `user_id`.
- Non-admin users can only see workflows in their `entity_id`.
- System admins see all data across all entities.
- Audit logs are viewable only by users with `tacaimsg.audit.view`.

## User_admin Integration

- Permissions are sourced from User_admin `/api/validate-session` response.
- The `user.permissions` list and `user.roles` list are both checked.
- No local permission storage — User_admin is the single source of truth.
