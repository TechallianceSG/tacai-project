# TAC-timesheet

TAC-timesheet is an independent local MVP for employee timesheet input, monthly time statistics, project/customer grouping, and future invoice preparation.

## Current status

Phase 1, Phase 2, Phase 3, and the Phase 4 audit baseline are implemented. Audit logging now covers master data, timesheet entries/workflow, month locks, and invoice draft actions.

Completed Phase 1 scope:

1. Timesheet dashboard, input, edit, list/filter, and soft delete.
2. Work-time validation and calculations.
3. Monthly summary by employee.

Completed Phase 2 scope:

1. Employee master data.
2. Project/customer master data.
3. Timesheet input using active employees and optional active projects.
4. Master-data snapshots copied into timesheet rows.
5. Monthly summaries by employee, project/customer, and organization.

Completed Phase 3 scope:

1. Timesheet submit, approve, reject, and reopen workflow.
2. Monthly closing panel.
3. Month lock storage in `database/month_locks.json`.
4. Locked-month protection for create/edit/delete/status transitions.

Phase 4 audit baseline:

1. Employee master create, update, and soft-delete actions append audit rows.
2. Project/customer master create, update, and soft-delete actions append audit rows.
3. Timesheet create, edit, soft-delete, submit, approve, reject, and reopen actions append audit rows.
4. Month lock actions append audit rows.
5. Invoice draft create and void actions append audit rows.
6. Audit rows are stored in `database/audit_logs.json`, include before/after snapshots, and can be reviewed at `/audit-logs`.

See [Phase 3 Implementation Plan](docs/Phase3_Implementation_Plan.md).

The app remains local-first and dependency-free.

## Portal/User_admin integration

TAC-timesheet is connected to TACAI Portal and protected by TACAI User Management.

- Portal URL: `http://127.0.0.1:8005`
- Timesheet URL: `http://127.0.0.1:8002/`
- User_admin URL: `http://127.0.0.1:8006`
- Required module permission: `timesheet.access`

All non-health Timesheet routes require a valid User_admin `tacai_session_id` cookie. Unauthenticated users are redirected to User_admin login with a local `next` return URL.

## Main features

### Timesheet input

- Employees enter/select employee number.
- Users select/input work date.
- Users enter start time and end time in 1-24 hour format:
  - `9:00`
  - `09:00`
  - `18:00`
  - `24:00`
- Users enter break minutes.
- Users can optionally choose a project/customer record.
- The system calculates:
  - Weekday.
  - Actual work minutes.
  - Overtime minutes using the employee default scheduled work time.

### Employee master

- Create, edit, list, and soft-delete employees.
- Fields:
  - Employee No.
  - Employee Name.
  - Department.
  - Email.
  - Default scheduled work minutes.

### Organization master

- Create, edit, list, and soft-delete three-level organization records:
  - Entity / legal entity.
  - Department.
  - Team.
- Timesheet rows snapshot Entity / Department / Team fields when the selected employee source provides organization assignment data.
- Team selection is not yet required on the Timesheet input form.

### Project/customer master

- Create, edit, list, and soft-delete projects/customers.
- Fields:
  - Project Code.
  - Project Name.
  - Customer Name.
  - Customer Code.
  - Dispatch Type.
  - Work Location.
  - Country / Prefecture.
  - Client approval required.
  - Billing enabled flag.
  - Billing rate per hour JPY.
  - Billing note.

### Statistics and approval workflow

The `/timesheets` page includes:

- Daily timesheet rows.
- Monthly summary by employee.
- Monthly summary by project/customer.
- Monthly summary by organization structure.
- Filters by employee, month, customer, project, and approval status.
- Submit, approve, reject, and reopen actions.
- Monthly closing panel and month lock action.
- CSV export using the current timesheet filters.
- Billing summary for approved, billing-enabled project work.
- Invoice draft creation from locked-month billing summaries.

## Project structure

```text
TAC-timesheet
├── backend
│   └── app.py
├── database
│   ├── employees.json
│   ├── projects.json
│   ├── timesheet_entries.json
│   ├── month_locks.json
│   ├── invoice_drafts.json
│   └── audit_logs.json
├── docs
│   ├── Timesheet_Table_Specification.md
│   ├── Phase3_Implementation_Plan.md
│   ├── Manual_Test_Checklist.md
│   ├── Supplier_Master_Data_Specification.md
│   ├── Customer_Master_Data_Specification.md
│   ├── One_Time_Party_Workflow.md
│   ├── OCR_Master_Data_Draft_Workflow.md
│   └── Master_Data_Enhancement_Roadmap.md
├── frontend
├── memory
├── prompts
├── CLAUDE.md
└── README.md
```

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 backend/app.py --host 127.0.0.1 --port 8002
```

Open:

```text
http://127.0.0.1:8002
```

Health check:

```text
http://127.0.0.1:8002/health
```

Manual verification checklist:

- [Manual Test Checklist](docs/Manual_Test_Checklist.md)

Customer/supplier master data planning:

- [Supplier Master Data Specification](docs/Supplier_Master_Data_Specification.md)
- [Customer Master Data Specification](docs/Customer_Master_Data_Specification.md)
- [One-Time Supplier and Customer Workflow](docs/One_Time_Party_Workflow.md)
- [OCR Master Data Draft Workflow](docs/OCR_Master_Data_Draft_Workflow.md)
- [Customer and Supplier Master Data Enhancement Roadmap](docs/Master_Data_Enhancement_Roadmap.md)

## Main pages

- `/` — dashboard.
- `/timesheet-new` — timesheet input.
- `/timesheets` — daily rows plus monthly summaries.
- `/timesheets.csv` — CSV export using the same filters as `/timesheets`.
- `/employees` — read-only employee source page for TAC-employeeadmin/fallback status.
- `/projects` — project/customer master list.
- `/project-new` — create project/customer.
- `/organization` — three-level organization master overview.
- `/entities` — entity master list.
- `/departments` — department master list.
- `/teams` — team master list.
- `/billing` — approved billable work summary by month/customer/project.
- `/invoices` — invoice draft list and void action.
- `/audit-logs` — read-only audit log viewer with filters by module, record ID, action, and user.

## Database files

- `database/timesheet_entries.json` — active and soft-deleted timesheet rows.
- `database/employees.json` — local fallback employee records only; EmployeeAdmin is the primary employee master source.
- `database/projects.json` — project/customer master records.
- `database/entities.json` — organization entity master records.
- `database/departments.json` — organization department master records.
- `database/teams.json` — organization team master records.
- `database/month_locks.json` — monthly lock records created by Phase 3 closing workflow.
- `database/invoice_drafts.json` — invoice draft records created from locked billing summaries.
- `database/audit_logs.json` — append-only Phase 4 audit records for master data, timesheet entries/workflow, month locks, and invoice draft actions.

All files are UTF-8 JSON. Work durations are saved as integer minutes to avoid floating-point errors.

## Snapshot behavior

When a timesheet row is saved, the app copies selected employee and project master values into that row. This means future changes to employee/project masters do not silently rewrite historical timesheet rows, which is important for audit and future invoicing.

## Trilingual UI and EmployeeAdmin integration

TAC-timesheet supports Chinese, Japanese, and English UI labels through `?lang=zh`, `?lang=ja`, and `?lang=en` plus a language switcher in the navigation. The main shell and timesheet input page use a SAP/Fiori-inspired layout with an object header, section cards, status badges, message strips, and toolbar actions.

Employee master selection is integrated with TAC-employeeadmin when that service is available. TAC-timesheet calls the safe authenticated EmployeeAdmin endpoint `/api/timesheet/employees`, snapshots the selected employee number/name/department into timesheet rows, and keeps local `database/employees.json` as fallback/offline data only. Backend EmployeeAdmin API calls use the internal loopback host by default, while browser navigation links continue to use the public host. Existing historical timesheet rows are not rewritten. Timesheet no longer exposes employee master create/edit/delete navigation; employee maintenance belongs in TAC-employeeadmin.

## Current limitations

- Authentication and module access use TACAI Portal/User_admin; fine-grained approval actors still rely on current local workflow fields until feature-level User_admin permissions are expanded.
- No Excel export yet.
- Cross-midnight shifts are not supported yet.
- Automatic night-work calculation is not implemented yet.
