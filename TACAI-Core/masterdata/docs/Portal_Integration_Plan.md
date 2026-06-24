# TACAI Portal Integration Plan - Master Data Management

Last updated: 2026-06-19

## 1. Objective

Integrate TACAI Core Platform Master Data Management into TACAI Portal and User_admin so it becomes the central organization master-data module for all TACAI business systems.

No code changes are implemented in this planning step.

## 2. Portal placement

User requested that Master Data Management should be placed before User_admin/User Management.

Recommended Portal module order:

```text
Dashboard
Employee Mgmt
Timesheet
Payroll
Expense
Master Data Management
User Management
```

## 3. Planned Portal module configuration

Recommended module entry for future `tacai-portal/database/modules.json` update:

```json
{
  "module_key": "masterdata",
  "label": "Master Data Management",
  "labels": {
    "ja": "マスターデータ管理",
    "zh": "主数据管理",
    "en": "Master Data Management"
  },
  "description": "Centralized organization master data for Entity, Department, and Team",
  "descriptions": {
    "ja": "法人、部門、チームの組織マスターデータを一元管理",
    "zh": "统一管理法人、部门、团队等组织主数据",
    "en": "Centrally manage organization master data for entities, departments, and teams"
  },
  "url": "http://127.0.0.1:8007/dashboard",
  "status": "Connected module",
  "statuses": {
    "ja": "連携済み",
    "zh": "已连接模块",
    "en": "Connected module"
  },
  "required_permission": "masterdata.access",
  "enabled": true
}
```

Recommended service registry entry for future `tacai-portal/database/services.json` update:

```json
"masterdata": {
  "name": "Master Data Management",
  "url": "http://127.0.0.1:8007",
  "health": "http://127.0.0.1:8007/health",
  "required_permission": "masterdata.access"
}
```

## 4. User_admin integration

User_admin should become the access-control authority for Master Data Management.

The target authorization model is:

```text
valid User_admin session
AND active selected Entity assignment
AND required RBAC permission
```

Entity context must come from the User_admin session validation response, not from Portal or module URL query parameters.

Recommended permission catalog additions:

| Permission key | Description |
|---|---|
| `masterdata.access` | Access Master Data Management module. |
| `masterdata.view` | View entity, department, and team master data. |
| `masterdata.maintain` | Create, update, and soft-delete master data. |
| `masterdata.admin` | Reserved for advanced MDM administration. |

Recommended role mapping:

| Role | Access |
|---|---|
| System Admin | Full access. |
| HR Manager | View and maintain. |
| Finance | View only. |
| Manager | View only. |
| Employee / Normal User | View only; Portal tile is visible. |

Confirmed decision:

- Employee / Normal User roles should see the Master Data Management tile in Portal and have read-only access.
- User_admin now requires `Entity Code + Email + Password` at login and stores one selected current Entity in the session.
- `/api/validate-session` returns Entity context as `user.entity`, with flat `entity_id`, `entity_code`, and `entity_name` compatibility fields.
- Portal displays the current Entity in the shell/header and rejects protected pages when Entity context is missing.
- Portal may propagate `lang=ja|zh|en` to module launch URLs, but must not propagate `entity_id` or `entity_code` in URLs.

## 5. Business module integration contract

Each module should reference Master Data Management IDs:

| Module | Required fields |
|---|---|
| Employee Management | `entity_id`, `department_id`, `team_id` |
| Timesheet Management | `entity_id`, `department_id`, `team_id` |
| Payroll Management | `entity_id`, `department_id`, `team_id` |
| Expense Management | `entity_id`, `department_id`, `team_id` |

No business module may maintain its own Entity/Department/Team master records after integration.

## 6. Recommended integration sequence

1. Build Master Data Management service skeleton on port `8007`.
2. Add User_admin permissions.
3. Add Portal service entry.
4. Add Portal module tile before User Management.
5. Verify Portal visibility for System Admin and HR Manager.
6. Add MDM read APIs for dropdowns.
7. Integrate Employee Management first.
8. Integrate Timesheet, Payroll, and Expense.
9. Deprecate local organization master data in business modules.
10. Verify all create/update/soft-delete MDM actions generate audit logs.

## 7. Manual test scenarios

Portal tests:

- Portal displays Master Data Management before User Management.
- System Admin sees Master Data Management tile.
- HR Manager sees Master Data Management tile.
- Finance, Manager, and Employee view-only roles can see the tile and access read-only screens.
- Unauthorized roles do not see the tile or are denied with a clear message.

MDM tests:

- Create Entity.
- Create Department under Entity.
- Create Team under Department.
- Update names in Simplified Chinese/Japanese/English.
- Soft delete records.
- Confirm audit logs for every change.

Business module tests:

- Employee Management can select Entity/Department/Team from MDM.
- Timesheet can reference Entity/Department/Team.
- Payroll can reference Entity/Department/Team.
- Expense can reference Entity/Department/Team.
- Local module-specific organization creation is disabled or removed.
