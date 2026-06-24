# TACAI Core Platform - Master Data Management V1 Project Plan

Last updated: 2026-06-20

## 1. Executive summary

Master Data Management V1 establishes one centralized source of truth for TACAI organization master data:

- Legal Entity
- Department
- Team

The strategic purpose is to prevent every business module from maintaining duplicate organization structures. Employee Management, Timesheet, Payroll, Expense, and future Training Management should reference Master Data Management records by ID.

V1 is intentionally narrow. It implements the minimum organization hierarchy required to stabilize cross-module data entry and reporting.

```text
Entity -> Department -> Team
```

## 2. Design principle: SAP-style project thinking

This project should follow SAP implementation thinking rather than isolated screen-by-screen development.

### 2.1 Fit-to-standard first

Use a standard enterprise master-data model first:

```text
Company / Legal Entity
  -> Department / Organization Unit
    -> Team / Operational Unit
```

Avoid custom structures unless a real TACAI business exception requires them.

### 2.2 Single source of truth

Organization master data belongs only to Master Data Management.

Business modules may reference:

- `entity_id`
- `department_id`
- `team_id`

Business modules must not create, rename, delete, or duplicate organization structures locally.

### 2.3 Governance before transaction scale

V1 should prioritize:

- stable master IDs
- uniqueness rules
- status lifecycle
- soft delete
- audit history
- role-based and entity-scoped authorization
- trilingual labels: Simplified Chinese, Japanese, and English

This matches SAP-style master data governance: define the record lifecycle before integrating transaction-heavy modules.

### 2.4 Configuration over hardcoding

Entity, department, team lists should be data-driven from JSON files in V1 and later movable to a database.

Business modules should call APIs or read integration endpoints rather than hardcoding dropdown values.

### 2.5 Audit and traceability

All create, update, and soft-delete actions must write an immutable audit record. The audit log is part of the design, not an afterthought.

## 3. Source requirement analysis

The provided requirement defines a centralized TACAI Core Platform Master Data Management module with three V1 functions:

1. Entity Management
2. Department Management
3. Team Management

It also defines the core integration rule:

> Employee Management, Timesheet Management, Payroll Management, and Expense Management must reference Entity ID, Department ID, and Team ID. No module may create its own organization master data.

### 3.1 Strengths

- Clear V1 scope.
- Correct centralization of organization master data.
- Simple hierarchy suitable for current TACAI modules.
- Explicit audit requirement.
- Explicit role-based access requirement.
- Simplified Chinese/Japanese/English language support matches the current TACAI Core trilingual direction.

### 3.2 Gaps to close before implementation

The requirement is strong, but implementation planning should add the following details:

| Area | Gap | Proposed V1 decision |
|---|---|---|
| ID strategy | ID format not defined | Use stable internal IDs such as `ENT-0001`, `DEP-0001`, `TEAM-0001` or UUID-like strings; codes remain business-facing unique keys. |
| Code uniqueness scope | Department/team uniqueness scope not explicit | Entity Code globally unique; Department Code unique only within its parent Entity; Team Code unique only within its parent Department. |
| Status values | Status not defined | Use `active` and `inactive` for operator lifecycle. Legacy `deleted` remains hidden for backward compatibility, but new deactivation sets `status = inactive`. |
| Referential integrity | Parent inactive/deleted behavior not defined | Department requires active parent Entity when created; Team requires active parent Department when created. Inactivation should warn/block if active children exist, unless forced in later phase. |
| Effective dating | Not included | Defer effective dates to future phase. V1 uses current-state master data only. |
| Audit shape | Missing module/action names | Align with TACAI audit rules: `module`, `record_id`, `action`, `user`, `timestamp`, `before_value`, `after_value`; include entity context where available. |
| Authorization keys | Permission names not defined | Add `masterdata.access`, `masterdata.view`, `masterdata.maintain`, `masterdata.admin`; combine permissions with active User-Entity assignments. |
| API contract | Integration mechanism not defined | Provide entity-scoped read APIs for modules and guarded maintain APIs for authorized roles. |
| Portal order | User requested placement before User_admin | Add Master Data Management portal tile immediately before User Management and show the current login Entity in the Portal shell. |
| Login context | Login does not capture Entity | User_admin login should require Entity Code + Email + Password, and sessions should include `entity_id`/`entity_code`. |

## 4. Target module structure

```text
TACAI-Core/
├── masterdata/
│   ├── backend/                  # future implementation
│   ├── database/
│   │   ├── entities.json
│   │   ├── departments.json
│   │   ├── teams.json
│   │   └── audit_logs.json
│   ├── docs/
│   │   ├── Project_Plan.md
│   │   ├── Data_Schema.md
│   │   └── Portal_Integration_Plan.md
│   ├── frontend/                 # optional CSS/static assets later
│   ├── i18n/                     # Simplified Chinese/Japanese/English labels
│   ├── memory/
│   ├── archive/
│   ├── CLAUDE.md
│   └── README.md
├── tacai-portal/
└── User_admin/
```

## 5. Business process design

### 5.1 Entity Management

Purpose: manage legal entities in the group.

Examples:

- Tech Alliance KK
- Tech Alliance SG

Fields:

- Entity ID
- Entity Code
- Entity Name (English)
- Entity Name (Japanese)
- Entity Name (Simplified Chinese)
- Country
- Currency
- Status
- Created Date
- Updated Date

Rules:

- Entity Code must be unique.
- Deactivation only; operator actions set `status = inactive` rather than physically deleting records.
- Audit log and version history are required.
- Department records must reference an existing Entity.

### 5.2 Department Management

Purpose: manage departments under entities.

Examples:

- Recruitment
- Sales
- Finance
- HR
- Operations

Fields:

- Department ID
- Department Code
- Department Name (English)
- Department Name (Japanese)
- Department Name (Simplified Chinese)
- Parent Entity
- Status
- Created Date
- Updated Date

Rules:

- Department belongs to one Entity.
- Department Code must be unique within the parent Entity only; different Entities may reuse the same Department Code such as `HR` or `FINANCE`.
- Deactivation only; operator actions set `status = inactive` rather than physically deleting records.
- Audit log and version history are required.
- Team records must reference an existing Department.

### 5.3 Team Management

Purpose: manage operational teams.

Examples:

- Japan Recruitment Team
- India Delivery Team

Fields:

- Team ID
- Team Code
- Team Name (English)
- Team Name (Japanese)
- Team Name (Simplified Chinese)
- Parent Department
- Status
- Created Date
- Updated Date

Rules:

- Team belongs to one Department.
- Team Code must be unique within the parent Department only.
- Deactivation only; operator actions set `status = inactive` rather than physically deleting records.
- Audit log and version history are required.


### 5.6 System Parameters

Purpose: centralize shared runtime configuration that should not be owned by individual business modules.

Implemented first parameter:

- `email.onboarding.smtp` — outbound SMTP settings for EmployeeAdmin onboarding invitation, verification, HR notification, and return-to-candidate emails.

Rules:

- Master Data owns the maintenance UI and `database/system_parameters.json`.
- EmployeeAdmin must not render or update System Parameters locally.
- EmployeeAdmin reads runtime settings through `GET /api/master-data/system-parameters/outbound-email-onboarding` with `X-TACAI-Internal-Token`.
- The actual SMTP password is resolved from a server-side environment variable or secret reference and is never displayed in UI or audit logs.
- Updates are audited as `system_parameters` records; test email events are audit-only operational events.


## 6. Security and authorization design

Authentication source: TACAI-Core/User_admin.

Planned role access:

| Role | Access |
|---|---|
| System Admin | Full access: view, create, update, soft delete, manage future settings. |
| HR Manager | View and maintain Entity/Department/Team records. |
| Normal User / Employee | View only. |

Recommended permission keys:

| Permission key | Purpose |
|---|---|
| `masterdata.access` | Can open Master Data Management module. |
| `masterdata.view` | Can view Entity, Department, and Team lists/details. |
| `masterdata.maintain` | Can create/update/soft-delete records. |
| `masterdata.admin` | Reserved for future advanced governance/settings. |

### 6.1 Entity-based login and authorization direction

Master Data Management must participate in an entity-scoped TACAI security model. User_admin login should collect Entity Code, Email, and Password. After login, User_admin sessions should include the current Entity context:

```json
{
  "entity_id": "ENT-0001",
  "entity_code": "TAJP",
  "entity_name": "Tech Alliance Japan KK"
}
```

Authorization should be evaluated as:

```text
valid session
AND active assignment to current entity
AND required role/permission
```

Recommended V1 rules:

- System Admin must still choose an active Entity at login; V1 does not introduce an `ALL_ENTITIES` runtime mode.
- System Admin and `masterdata.admin` users may view/maintain cross-entity master data where needed.
- Non-admin users operate inside the selected login Entity only.
- Department and Team pages default to the current login Entity.
- Audit records should include entity context where available.

## 7. Integration design

### 7.1 Portal integration

Add Master Data Management to TACAI Portal module navigation before User Management.

Recommended Portal order:

```text
Dashboard
Employee Mgmt
Timesheet
Payroll
Expense
Master Data Management
User Management
```

Portal module metadata should include:

- `module_key`: `masterdata`
- label EN: `Master Data Management`
- label JA: `マスターデータ管理`
- label ZH: `主数据管理`
- URL: `http://127.0.0.1:8007/dashboard`
- required permission: `masterdata.access`
- enabled: `true`

### 7.2 User_admin integration

User_admin must include MDM permission keys and role-permission assignments.

Recommended V1 assignment:

| Role | Permissions |
|---|---|
| System Admin | `masterdata.access`, `masterdata.view`, `masterdata.maintain`, `masterdata.admin` |
| HR Manager | `masterdata.access`, `masterdata.view`, `masterdata.maintain` |
| Finance | `masterdata.access`, `masterdata.view` |
| Manager | `masterdata.access`, `masterdata.view` |
| Employee | `masterdata.access`, `masterdata.view` |

Confirmed business decision: Employee / Normal User roles should see the Master Data Management Portal tile, but only with read-only access.

Recommended for data-entry testing: allow System Admin and HR Manager maintain access; allow Finance, Manager, and Employee roles view only.

### 7.3 Business module integration

Each business module should reference MDM IDs:

| Module | Required references |
|---|---|
| Employee Management | `entity_id`, `department_id`, `team_id` |
| Timesheet Management | `entity_id`, `department_id`, `team_id` |
| Payroll Management | `entity_id`, `department_id`, `team_id` |
| Expense Management | `entity_id`, `department_id`, `team_id` |
| Future Training Management | `entity_id`, `department_id`, `team_id` |

Business modules should use MDM read APIs/dropdown endpoints instead of local organization lists.

## 8. Planned API surface

V1 implementation should expose read APIs for module dropdowns and UI pages for maintenance.

Recommended endpoints:

| Endpoint | Method | Purpose | Permission |
|---|---|---|---|
| `/health` | GET | Service health | none |
| `/dashboard` | GET | MDM dashboard | `masterdata.access` |
| `/entities` | GET | Entity list page | `masterdata.view` |
| `/departments` | GET | Department list page | `masterdata.view` |
| `/teams` | GET | Team list page | `masterdata.view` |
| `/api/entities` | GET | Active entity data for dropdowns | `masterdata.view` or valid session |
| `/api/departments` | GET | Active department data; filter by entity | `masterdata.view` or valid session |
| `/api/teams` | GET | Active team data; filter by department | `masterdata.view` or valid session |
| `/entities/create` | POST | Create entity | `masterdata.maintain` |
| `/entities/<id>/edit` | POST | Update entity | `masterdata.maintain` |
| `/entities/<id>/delete` | POST | Soft delete entity | `masterdata.maintain` |
| Equivalent department/team POST routes | POST | Maintain child records | `masterdata.maintain` |

## 9. Implementation roadmap

### Phase 0 — Blueprint and governance

Status: planning stage.

Deliverables:

- Save project planning files under `TACAI-Core/masterdata`.
- Confirm V1 scope: Entity, Department, Team only.
- Confirm Portal placement before User Management.
- Confirm local port `8007`.
- Confirm permission keys and role mapping.
- Confirmed normal Employee role should see the Master Data tile with read-only access.

### Phase 1 — Foundation skeleton

Deliverables:

- Create dependency-free Python backend skeleton.
- Add `/health` endpoint.
- Add i18n resources for Simplified Chinese/Japanese/English.
- Create seed JSON files:
  - `entities.json`
  - `departments.json`
  - `teams.json`
  - `audit_logs.json`
- Add layout shell matching TACAI Core style.
- Add User_admin session validation integration.

### Phase 2 — Entity Management

Deliverables:

- Entity list/detail/create/edit/soft-delete pages.
- Entity Code uniqueness validation.
- Required field validation.
- Audit logging for create/update/soft delete.
- Simplified Chinese/Japanese/English display labels.

### Phase 3 — Department Management

Deliverables:

- Department list/detail/create/edit/soft-delete pages.
- Parent Entity selection.
- Department Code uniqueness validation.
- Parent Entity existence/status validation.
- Audit logging for create/update/soft delete.

### Phase 4 — Team Management

Deliverables:

- Team list/detail/create/edit/soft-delete pages.
- Parent Department selection.
- Team Code uniqueness validation.
- Parent Department existence/status validation.
- Audit logging for create/update/soft delete.

### Governance Phase 1/2 — Controlled master-data change and recovery

Status: implemented on 2026-06-20.

Deliverables:

- Entity/Department/Team edits show a master-data impact warning.
- Updates, deactivations, and restores require a business change reason and explicit acknowledgement.
- Deactivation sets `status = inactive`; records are not physically deleted and new operator actions do not set `deleted`.
- `database/masterdata_versions.json` stores immutable version snapshots for create/update/deactivate/restore.
- Existing records without versions receive a baseline snapshot before their first governed change.
- Detail pages show version history and per-version field comparisons.
- Restoring a historical version creates a new version and audit entry; it never removes intermediate history.
- Audit logs include change reason, changed fields, and the related `version_id` when available.

### Phase 5 — Portal and User_admin integration

Deliverables:

- Add Master Data Management service to Portal service registry.
- Add Master Data Management module tile before User Management.
- Add `masterdata.*` permissions to User_admin permission catalog.
- Map System Admin and HR Manager permissions.
- Verify Portal module visibility by role.

### Phase 6 — Business module read integration

Deliverables:

- Employee Management uses MDM references for entity/department/team.
- Timesheet uses MDM references for entity/department/team.
- Payroll uses MDM references for entity/department/team.
- Expense uses MDM references for entity/department/team.
- Remove or deprecate local organization master data in business modules.
- Add migration plan for existing records.

### Phase 7 — Manual testing and stabilization

Deliverables:

- Manual test checklist.
- Role access verification.
- Data entry scenarios:
  - Create entity.
  - Create department under entity.
  - Create team under department.
  - Use records in Employee/Timesheet/Payroll/Expense.
- Audit verification.
- Soft-delete behavior verification.
- Language switching verification.

## 9.1 Enhancement roadmap — trilingual and entity-scoped authorization

### Enhancement Step 1 — Blueprint update

Status: completed foundation on 2026-06-19.

Deliverables:

- Update Master Data Management project plan and schema for Simplified Chinese/Japanese/English UI support.
- Update Department uniqueness from global uniqueness to `(entity_id, department_code)` uniqueness.
- Update Team uniqueness from global uniqueness to `(department_id, team_code)` uniqueness.
- Document User_admin Entity Code login and User-Entity assignment model.
- Document Portal current Entity display and entity-scoped module launching.

Step 1 completion criteria:

- The common language set is `ja`, `zh`, and `en`.
- Entity, Department, and Team records define English, Japanese, and Simplified Chinese display-name fields.
- The language fallback rule is current language field, then English, then business code.
- Entity context is session-sourced from User_admin; Portal and modules must not trust `entity_id` query parameters for authorization.
- Entity-scoped enforcement is staged after User_admin can return selected Entity context from `/api/validate-session`.

### Enhancement Step 2 — Masterdata trilingual UI

Deliverables:

- Add `i18n/zh.json`.
- Add `?lang=zh` language switching.
- Add Chinese labels for dashboard, entity, department, team, validation, buttons, statuses, and audit action display.
- Add Chinese name fields for Entity, Department, and Team.

### Enhancement Step 3 — Entity-scoped Department and Team management

Status: Department foundation implemented on 2026-06-19; Team CRUD remains pending.

Deliverables:

- Department list filter by Entity. Completed for non-`masterdata.admin` sessions.
- Department create/edit validates `(entity_id, department_code)` uniqueness. Completed.
- Team list filter by Entity and Department. API filtering foundation added; full Team CRUD remains pending.
- Team create/edit validates parent Department belongs to the selected/current Entity. Pending Team CRUD.

### Enhancement Step 4 — User_admin Entity login

Status: foundation implemented on 2026-06-19.

Deliverables:

- Add User-Entity assignment data model. Completed with `User_admin/database/user_entity_mapping.json`.
- Add Entity Code to login. Completed.
- Store `entity_id` and `entity_code` in sessions. Completed, with trilingual Entity names.
- Return Entity context from `/api/validate-session`. Completed as `user.entity`, with flat compatibility fields.

### Enhancement Step 5 — Portal and business module entity context

Deliverables:

- Portal header shows current Entity.
- Masterdata, EmployeeAdmin, Timesheet, Payroll, and Expense use the current session Entity for filtering and data creation.
- Existing records are backfilled to a default Entity before strict filtering is enforced.

## 10. SAP-style work packages

### 10.1 Discover

- Confirm organization hierarchy with business owner.
- Confirm initial seed values for entities/departments/teams.
- Confirm roles allowed to maintain data.
- Confirm reporting expectations.

### 10.2 Design

- Finalize master-data schemas.
- Finalize authorization matrix.
- Finalize Portal order and labels.
- Finalize integration API contract.

### 10.3 Realize

- Build backend/UI in phases.
- Implement audit logging from the start.
- Implement User_admin validation from the start.
- Implement APIs for module consumption.

### 10.4 Validate

- Run local service health checks.
- Run role-by-role Portal visibility checks.
- Run create/update/soft-delete tests.
- Validate every audit record.
- Validate business modules only reference MDM IDs.

### 10.5 Deploy / Cutover

- Seed initial organization master data.
- Freeze local organization maintenance in business modules.
- Map existing business records to MDM IDs.
- Keep rollback backup of JSON files before migration.

### 10.6 Hypercare

- Monitor audit logs.
- Collect missing master-data requests.
- Adjust validation rules if operational gaps appear.
- Prepare V1.1 backlog.

## 11. V1 success criteria

V1 is complete when:

1. Master Data Management runs as a TACAI Core module.
2. Portal shows Master Data Management before User Management.
3. User_admin controls access by role/permission.
4. System Admin and HR Manager can maintain entity/department/team records.
5. Normal users can see the Master Data Management Portal tile and view master data only.
6. Employee Management, Timesheet, Payroll, and Expense can reference MDM IDs.
7. No business module maintains its own organization master data.
8. All create/update/soft-delete actions create audit logs.
9. Simplified Chinese, Japanese, and English labels are available.

## 12. Future expansion backlog

Reserved future masters:

- Employment Type Master
- Visa Type Master
- Country Master
- Currency Master
- Skill Category Master
- Training Category Master

Future governance features:

- Effective dating
- Approval workflow for master-data changes
- Import/export
- Central audit viewer
- Database migration
- API versioning
- Cross-module impact analysis before inactivation/deletion
