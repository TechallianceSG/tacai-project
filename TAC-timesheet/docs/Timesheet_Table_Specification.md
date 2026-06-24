# TAC-timesheet Table Specification

## Purpose

TAC-timesheet stores employee work-time records for an independent local timesheet system. Phase 1 and Phase 2 are implemented: employee/project master data is available, timesheet rows snapshot selected master values, and monthly statistics can be grouped by employee and by project/customer. Phase 3 is planned for approval workflow and monthly lock.

## Storage

All storage uses UTF-8 JSON arrays:

```text
database/employees.json
database/projects.json
database/entities.json
database/departments.json
database/teams.json
database/timesheet_entries.json
database/month_locks.json
database/invoice_drafts.json
database/audit_logs.json
```

Durations are saved as integer minutes and displayed as hours/minutes in the UI.

## Audit Logs

File:

```text
database/audit_logs.json
```

Phase 4 audit logging appends one record whenever covered business data changes. Current coverage includes employee/project master data, timesheet entries/workflow, month locks, and invoice draft create/void actions. Audit rows are append-only operational history and should not be deleted.

Required fields:

| Field | Description |
|---|---|
| `audit_id` | System-generated audit row ID. |
| `module` | Source module, for example `master_data.employee` or `master_data.project`. |
| `record_id` | Source record ID. |
| `action` | `create`, `update`, or `soft_delete`. |
| `user` | User_admin actor label when available, falling back to `local_user`. |
| `timestamp` | UTC ISO datetime when the change was written. |
| `before_value` | Record snapshot before the change, or `{}` for create. |
| `after_value` | Record snapshot after the change, or `{}` if not applicable. |

Covered modules/actions:

- `master_data.employee`: `create`, `update`, `soft_delete`.
- `master_data.project`: `create`, `update`, `soft_delete`.
- `master_data.entity`: `create`, `update`, `soft_delete`.
- `master_data.department`: `create`, `update`, `soft_delete`.
- `master_data.team`: `create`, `update`, `soft_delete`.
- `timesheet.entry`: `create`, `update`, `soft_delete`, `submit`, `approve`, `reject`, `reopen`.
- `timesheet.month_lock`: `lock`.
- `timesheet.invoice_draft`: `create`, `void`.

The read-only `/audit-logs` page filters audit rows by module, record ID, action, and user.

## Employee Master

Primary source:

```text
TAC-employeeadmin /api/timesheet/employees
```

Fallback/offline file:

```text
database/employees.json
```

TAC-timesheet uses TAC-employeeadmin as the employee master when available. The EmployeeAdmin endpoint returns only a safe allowlist of fields for Timesheet selection. Local `database/employees.json` remains fallback/offline data and is not the source of truth while EmployeeAdmin is reachable.

| Field | Required | Description |
|---|---:|---|
| `employee_id` | Auto | System-generated ID, e.g. `emp-...`. |
| `employee_no` | Yes | Unique active employee number used in timesheets. |
| `employee_name` | Yes | Employee name. |
| `department` | No | Department/team. |
| `email` | No | Optional email; must contain `@` when provided. |
| `default_scheduled_work_minutes` | Yes | Default scheduled work minutes; default `480`. |
| `record_status` | Auto | `Active` or `Deleted`. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |
| `entity_id`, `entity_code`, `entity_name` | No | Optional organization assignment fields returned by EmployeeAdmin or fallback data. |
| `department_id`, `department_code`, `department_name` | No | Optional structured department assignment. Legacy `department` remains supported. |
| `team_id`, `team_code`, `team_name` | No | Optional Team assignment used for Timesheet organization snapshots. |

Validation:

- `employee_id` is the stable EmployeeAdmin employee master ID when available.
- `employee_no` is required for display/input compatibility and is unique within the current legal Entity, not globally.
- New access-control logic should prefer `employee_id` / `employee_master_id`; fallback to `entity_id + employee_no` is retained for older rows.
- `employee_name` is required.
- `default_scheduled_work_minutes` must be a non-negative integer.
- Employee deletion is soft delete only.
- Employee create, update, and soft delete append audit rows to `database/audit_logs.json`.

## Project / Customer Master

File:

```text
database/projects.json
```

| Field | Required | Description |
|---|---:|---|
| `project_id` | Auto | System-generated ID, e.g. `prj-...`. |
| `project_code` | Yes | Unique active project code. |
| `project_name` | Yes | Project name. |
| `customer_name` | Yes | Customer/client name. |
| `customer_code` | No | Optional customer code. |
| `dispatch_type` | Yes | `Expatriate`, `Dispatch`, `Client Site`, `Remote Support`, or `Other`. |
| `work_location` | Yes | `Office`, `Customer Site`, `Remote`, `Business Trip`, or `Other`. |
| `country` | Yes | Defaults to `Japan`. |
| `prefecture` | No | Tokyo, Osaka, etc. |
| `client_approval_required` | No | Whether customer confirmation is required. |
| `billing_enabled` | No | Whether approved rows for this project are included in billing summary. |
| `billing_rate_per_hour_yen` | No | Hourly billing rate in JPY; default `0`. |
| `billing_note` | No | Optional billing memo. |
| `record_status` | Auto | `Active` or `Deleted`. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |

Validation:

- `project_code` is required and unique among active projects.
- `project_name` is required.
- `customer_name` is required.
- `dispatch_type` and `work_location` must match allowed enum values.
- Project deletion is soft delete only.
- Project create, update, and soft delete append audit rows to `database/audit_logs.json`.

## Organization Master

Files:

```text
database/entities.json
database/departments.json
database/teams.json
```

The organization master is currently limited to three levels: Entity -> Department -> Team. Entity, Department, and Team records use soft delete and append audit rows to `database/audit_logs.json`.

Timesheet input does not require users to manually select a Team yet. Instead, new and edited Timesheet rows snapshot organization fields when the selected employee source provides `team_id`, `department_id`, or direct organization code/name fields. Organization master changes do not automatically rewrite historical Timesheet rows.

## Ordinary Employee Clock Entry

The mobile/desktop ordinary employee entry page is available at `/clock-entry`. It is intentionally simpler than the HR/Admin full Timesheet form.

Ordinary employees only enter:

- `work_date`
- `start_time`
- `end_time`
- `break_minutes`

`work_date` defaults to the current day but may be changed to any current-month date or previous-month date while the target month is not locked. `attendance_status` defaults to `Worked`, and `project_code` remains optional/blank. The employee number is resolved from the current User_admin account or by matching the User_admin email to the EmployeeAdmin safe employee payload.

Ordinary employee edit window rules:

1. Current-month unlocked records may be created or edited while Draft/Rejected.
2. Previous-month unlocked records may be created or edited while Draft/Rejected.
3. Previous-month locked records are read-only.
4. Submitted and Approved records are read-only from `/clock-entry` even when the month is open.
5. Older months are read-only for ordinary employees by default and require HR/Admin correction from the full Timesheet workflow if business approval is needed.

The `/my-timesheet` page gives ordinary employees a self-service monthly view for current month and previous month, including total work, overtime, status counts, missing weekday links, and daily record cards. Missing weekdays are a Monday-Friday convenience check in this milestone; Japan holiday calendar deduction remains future scope.

When a user has proxy submit permission, `/clock-entry` also shows an employee selector and assisted-entry source/reason fields. Ordinary employees still cannot select another employee: their employee number is resolved from User_admin/EmployeeAdmin linkage. Admin/HR/Finance proxy clock entry can use any open Timesheet accounting period while retaining Submitted/Approved read-only checks and assisted-entry metadata.

For dispatched employees, TAC-timesheet calls TAC-employeeadmin `/api/timesheet/dispatch-assignment?employee_no=<employee_no>&work_date=<YYYY-MM-DD>` during enrichment. If EmployeeAdmin has a matching dispatch assignment for the selected date, Timesheet snapshots the returned customer/project display values. If no matching assignment exists, customer/project fields remain blank and HR/Admin can adjust later in the full Timesheet edit page.

## Admin / HR / Finance assisted entry

The full `/timesheet-new` and `/timesheet-edit` workflow supports Japan operations where employees at customer sites, business-trip locations, or other offsite locations may not have network access and submit attendance sheets by email. Authorized Admin, HR, Finance, or manager users may enter those rows on behalf of the employee.

Permission model:

- `timesheet.submit_self`: ordinary self-entry permission for `/clock-entry` and own full-form entries.
- `timesheet.proxy_submit`: create a timesheet for another active employee.
- `timesheet.edit_own`: edit own Draft/Rejected open-period rows.
- `timesheet.proxy_edit`: edit another employee's Draft/Rejected open-period rows.
- `timesheet.delete` or `timesheet.proxy_edit`: soft-delete another employee's deletable open-period rows.
- Legacy `timesheet.submit` is temporarily accepted as a compatibility fallback for self/proxy submit while User_admin role templates are refined.

Assisted/proxy entry rules:

1. The selected employee must exist in the active Employee Master when EmployeeAdmin/local employees are available.
2. `work_date` must be valid and the derived Timesheet accounting period must be Open.
3. Closed periods block proxy create, edit, soft delete, and workflow changes through the same month-lock checks used elsewhere.
4. Proxy create/edit requires an assistance reason such as email attendance sheet, offsite without network access, HR/Finance assisted entry, manager correction, or other.
5. Proxy records save row-level metadata (`entry_mode`, `entry_source`, `entered_by*`, `on_behalf_of_employee_no`, `assistance_reason`, and `assistance_note`) and the audit log still stores full before/after snapshots.

## Timesheet Entries

File:

```text
database/timesheet_entries.json
```

### Employee input fields

| Field | Required | Description |
|---|---:|---|
| `employee_no` | Yes | Selected/entered employee number. |
| `project_code` | No | Optional selected project code. |
| `work_date` | Yes | `YYYY-MM-DD`. |
| `start_time` | Yes | 1-24 hour format, for example `9:00`, `09:00`, `18:00`. |
| `end_time` | Yes | 1-24 hour format, including `24:00`. |
| `break_minutes` | Yes | Non-negative integer minutes. |
| `employee_remarks` | No | Optional daily note. |

### Snapshot fields copied from masters

When saving a timesheet row, the app copies master data into the timesheet record:

From Employee Master:

- `employee_id` / `employee_master_id` for EmployeeAdmin-backed rows when available.
- `employee_no_snapshot` and `employee_name_snapshot` for historical display when employee master data changes later.
- `employee_name`
- `department`
- `scheduled_work_minutes`
- `employee_source`, `employment_type`, and `employment_status` for new integrated rows when available.

From Organization Master / employee organization assignment when available:

- `entity_id`
- `entity_code`
- `entity_name`
- `department_id`
- `department_code`
- `department_name`
- `team_id`
- `team_code`
- `team_name`

From EmployeeAdmin dispatch assignment when `project_code` is blank and a date-matching assignment exists:

- `customer_name` from EmployeeAdmin `client_name`.
- `project_name` from EmployeeAdmin `project_name`, `work_description`, or `assignment_location` fallback.
- `dispatch_type` defaults to `Dispatch`.
- `work_location` defaults to `Customer Site`.
- `country` defaults to `Japan`.
- `dispatch_assignment_matched`.
- `dispatch_assignment_source`.
- `dispatch_assignment_history_id`.
- `dispatch_contract_type`.
- `dispatch_assignment_location`.
- `dispatch_work_description`.
- `dispatch_start_date`.
- `dispatch_end_date`.
- `dispatch_supervisor_name`.
- `dispatch_supervisor_title`.
- `dispatch_supervisor_phone`.
- `dispatch_supervisor_email`.

From Project Master when `project_code` is selected by HR/Admin:

- `customer_name`
- `project_name`
- `dispatch_type`
- `work_location`
- `country`
- `prefecture`
- `client_approval_required`
- `customer_code`
- `billing_enabled`
- `billing_rate_per_hour_yen`
- `billing_note`

Project Master enrichment is authoritative when `project_code` is present. EmployeeAdmin dispatch assignment enrichment is a project-optional fallback for ordinary employee clock entries.

This snapshot behavior protects historical reporting, billing summaries, and future invoicing if master records change later.

### Calculated/audit fields

| Field | Description |
|---|---|
| `weekday` | Calculated from work date. |
| `actual_work_minutes` | `end_time - start_time - break_minutes`. |
| `overtime_minutes` | `max(0, actual_work_minutes - scheduled_work_minutes)`. |
| `holiday_work_minutes` | Reserved for later holiday logic. |
| `record_id` | System-generated ID, e.g. `ts-...`. |
| `record_status` | `Active` or `Deleted`. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |
| `entry_mode` | `self` for ordinary self-entry or `proxy` for Admin/HR/Finance/manager assisted entry. |
| `entry_source` | `web_self`, `web_proxy`, or `email_manual`. |
| `entered_by` | Audit actor label that created the row. |
| `entered_by_user_id` | User_admin ID of the actor when available. |
| `entered_by_name` | Display name/email of the actor when available. |
| `on_behalf_of_employee_no` | Employee number the row was entered for; equals `employee_no` and makes proxy intent explicit. |
| `assistance_reason` | Required reason for proxy create/edit, e.g. email attendance sheet or offsite no network. |
| `assistance_note` | Optional free-text proxy/assistance note. |
| `last_modified_by`, `last_modified_by_user_id`, `last_modified_by_name` | Last actor metadata for edits. |
| `last_modified_entry_mode` | `self` or `proxy` classification for the latest edit. |

### Phase 3 approval workflow fields

| Field | Description |
|---|---|
| `approval_status` | `Draft`, `Submitted`, `Approved`, or `Rejected`. Missing legacy values are displayed as `Draft`. |
| `submitted_at` | UTC ISO datetime when the row was submitted. |
| `submitted_by` | Actor label for submit action; local MVP uses `local_user`. |
| `approved_at` | UTC ISO datetime when the row was approved. |
| `approved_by` | Actor label for approval action; local MVP uses `local_user`. |
| `rejected_at` | UTC ISO datetime when the row was rejected. |
| `rejected_by` | Actor label for reject action; local MVP uses `local_user`. |
| `reject_reason` | Optional reason shown on the timesheet list. |
| `reopened_at` | UTC ISO datetime when the row was reopened. |
| `reopened_by` | Actor label for reopen action; local MVP uses `local_user`. |

Normal timesheet create/edit forms do not directly set workflow fields. Status changes must go through submit/approve/reject/reopen actions. Timesheet create, edit, soft-delete, and workflow actions append audit rows to `database/audit_logs.json`.

## Timesheet Accounting Periods

File:

```text
database/month_locks.json
```

The file now stores explicit monthly Timesheet accounting periods while preserving the previous month-lock compatibility fields.

| Field | Description |
|---|---|
| `period_id` | System-generated period ID, e.g. `period-202606`. |
| `lock_id` | Backward-compatible ID; equals `period_id` for generated period records. |
| `work_month` | Timesheet period month in `YYYY-MM` format. |
| `period_year` | Period year as an integer. |
| `period_month` | Period month as an integer. |
| `status` | `Open` or `Closed`. |
| `lock_status` | `Open` or `Locked`; closed periods use `Locked` for compatibility with existing lock checks. |
| `opened_at` / `opened_by` | Last open timestamp and actor. |
| `closed_at` / `closed_by` | Last close timestamp and actor. |
| `locked_at` / `locked_by` | Backward-compatible close timestamp and actor. |
| `notes` | Optional open/close note. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |

Every year has 12 Timesheet accounting periods. The app syncs the current year, 2026, and years found in existing Timesheet/Invoice records so missing periods are created automatically on startup or first period lookup.

Default seed rule:

- `2026-01` through `2026-04` are `Closed`.
- `2026-05` through `2026-12` are `Open`.
- Other newly-created year/month periods default to `Open`.

A closed period blocks new rows, edits, soft deletes, and workflow transitions for that month. Opening or closing a period appends `timesheet.accounting_period` audit rows to `database/audit_logs.json`.

## Time input rules

Phase 2 accepts 1-24 hour format:

- Valid: `1:00`, `01:00`, `9:00`, `09:00`, `18:00`, `24:00`.
- Invalid: `0:00`, `24:01`, `24:30`, non-numeric values.
- `24:00` is treated as the end of the same day.
- Cross-midnight shifts are not supported yet; `end_time` must be later than `start_time`.

## Timesheet validation rules

1. `employee_no` is required.
2. If active employees exist, `employee_no` must exist in Employee Master.
3. If `project_code` is selected, it must exist in Project Master.
4. `work_date` must use `YYYY-MM-DD`.
5. `start_time` and `end_time` are required.
6. `end_time` must be later than `start_time`.
7. `break_minutes` must be a non-negative integer.
8. Actual work minutes cannot be negative.
9. Duplicate active records are blocked for the same employee, work date, and project key.
10. New rows cannot be created for a closed Timesheet accounting period.
11. `Submitted` and `Approved` rows cannot be edited or soft-deleted unless reopened or rejected first.
12. Rows in closed Timesheet accounting periods cannot be edited, soft-deleted, or changed through workflow actions.
13. Proxy create/edit requires proxy permission and an assistance reason; ordinary self-entry cannot select another employee without proxy permission.

## Phase 3 approval and lock rules

1. New rows start as `Draft`.
2. `Draft` and `Rejected` rows can be submitted.
3. Only `Submitted` rows can be approved.
4. Only `Submitted` rows can be rejected.
5. `Submitted` and `Approved` rows can be reopened to `Draft` while the Timesheet accounting period is open.
6. A period can be closed when it is open and every active row in that month is `Approved`; empty periods may also be closed because yearly period calendars exist independently of Timesheet rows.
7. Soft-deleted rows are ignored when checking whether a period can be closed.
8. Closing a period updates its period record in `database/month_locks.json`; it does not rewrite all timesheet rows.
9. A closed period can be reopened by HR/Admin unless active invoice drafts already exist for that `work_month`.

## Calculation rules

```text
actual_work_minutes = end_time - start_time - break_minutes
overtime_minutes = max(0, actual_work_minutes - scheduled_work_minutes)
```

The scheduled work time comes from the selected employee master record when available; otherwise it defaults to `480` minutes.

## CSV export

The `/timesheets.csv` endpoint exports active, non-deleted timesheet rows as UTF-8 CSV using the same filters as `/timesheets`:

- `employee_no`
- `work_month`
- `customer_name`
- `project_code`
- `project_name`
- `approval_status`

The export includes raw minute fields, approval status, audit timestamps, remarks, the legacy `department` field, and structured organization snapshot fields (`entity_*`, `department_*`, and `team_*`). Soft-deleted rows are excluded.

## Monthly summaries

The `/timesheets` page calculates three summary tables.

### Monthly summary by employee

Grouped by:

- `work_month = work_date[:7]`
- `employee_no`

Columns:

- Month.
- Employee No.
- Employee Name.
- Entry count / work days.
- Actual work total.
- Overtime total.

### Monthly summary by project/customer

Grouped by:

- `work_month = work_date[:7]`
- `customer_name`
- `project_code`
- `project_name`

Columns:

- Month.
- Customer.
- Project Code.
- Project Name.
- Entry count / work days.
- Actual work total.
- Overtime total.
- Night work total.
- Holiday work total.
- Break shortage count.

### Monthly summary by organization

Grouped by:

- `work_month = work_date[:7]`
- Entity code/name, or `Unassigned` when missing.
- Department code/name, falling back to legacy `department` or `Unassigned`.
- Team code/name, or `Unassigned` when missing.

Columns:

- Month.
- Entity.
- Department.
- Team.
- Entry count / work days.
- Actual work total.
- Overtime total.
- Night work total.
- Holiday work total.
- Break shortage count.

These totals prepare the system for organization-level operations review, billing analysis, and later EmployeeAdmin organization assignment integration.

## Billing summary

The `/billing` page calculates a derived billing summary from active timesheet rows.

Rules:

1. Only `Approved` rows are billable.
2. Only rows for billing-enabled projects are included.
3. Soft-deleted rows are excluded.
4. Billing is hourly JPY only in this milestone.
5. `billable_minutes = actual_work_minutes`.
6. `billing_amount_yen = round(billable_minutes * billing_rate_per_hour_yen / 60)`.
7. Tax, overtime premium, invoice status, and payment tracking are out of scope for the billing summary milestone.
8. The billing page warns when a rate is `0` or the month is not locked.
9. Locked billing summary rows can be converted into invoice drafts.

Grouped by:

- `work_month`
- `customer_name`
- `project_code`
- `project_name`
- `billing_rate_per_hour_yen`

## Invoice drafts

File:

```text
database/invoice_drafts.json
```

Invoice drafts are created from locked-month billing summaries. Drafts snapshot the billing values at creation time and do not automatically change when project rates or source rows are later edited.

| Field | Description |
|---|---|
| `invoice_id` | System-generated draft ID. |
| `invoice_no` | Local invoice number, e.g. `INV-202806-0001`. |
| `invoice_status` | `Draft` or `Voided`. |
| `work_month` | Source work month in `YYYY-MM` format. |
| `customer_name` | Snapshot customer name. |
| `customer_code` | Snapshot customer code. |
| `project_code` | Snapshot project code. |
| `project_name` | Snapshot project name. |
| `billing_rate_per_hour_yen` | Snapshot hourly rate. |
| `billable_minutes` | Snapshot billable minutes. |
| `subtotal_yen` | Invoice subtotal. |
| `tax_rate_percent` | Tax rate; currently `0`. |
| `tax_yen` | Tax amount; currently `0`. |
| `total_yen` | Total amount; currently equals subtotal. |
| `source_record_ids` | Timesheet record IDs used for traceability. |
| `created_by` | Local actor label. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |
| `voided_at` | UTC ISO datetime when voided. |
| `voided_by` | Local actor label when voided. |
| `void_reason` | Optional void reason. |

Rules:

1. Invoice draft creation requires a locked month.
2. One active draft is allowed per `work_month + customer_name + project_code`.
3. Voided drafts remain in JSON for audit history.
4. Invoice draft create and void actions append audit rows to `database/audit_logs.json`.
5. PDF generation, email sending, payment tracking, and tax calculation are out of scope for this milestone.

## Implementation phases

Completed:

- Phase 1: timesheet input, edit, list/filter, validation, calculations, soft delete, and monthly summary by employee.
- Phase 2: employee master, project/customer master, timesheet selectors, master-data snapshots, and monthly summary by project/customer.

Completed post-Phase 3 enhancements:

- Manual verification checklist.
- Filtered CSV export at `/timesheets.csv`.
- Billing rates and billing summary.
- Invoice draft table.

Phase 4 audit baseline:

- Employee master create/update/soft-delete audit logging.
- Project/customer master create/update/soft-delete audit logging.
- Timesheet create/update/soft-delete and workflow audit logging.
- Month lock audit logging.
- Invoice draft create/void audit logging.
- Read-only `/audit-logs` viewer with filters.

Later phases can add:

- Excel export if a dependency or XLSX writer approach is approved.
- Cross-midnight shift support.
- Automatic night-work calculation.
- Login and role-based permissions.
