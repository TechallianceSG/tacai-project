# CLAUDE.md

This file provides guidance to Claude Code when working with the TAC-timesheet project.


Project Name: TAC-timesheet

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.


## Project overview

TAC-timesheet is a local-first Japan dispatch, expatriate, and client-site timesheet management MVP. It saves employee, project/customer, and timesheet rows in JSON and provides a Python standard-library web UI for input, editing, filtering, and summary totals.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 backend/app.py --host 127.0.0.1 --port 8002
```

Health check:

```bash
curl -s http://127.0.0.1:8002/health
```

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

No dependency installation, build, lint, or test suite is defined yet. The MVP uses only Python standard library modules.

## Architecture

- `backend/app.py` is the application entry point and contains:
  - HTTP route handling.
  - HTML rendering.
  - timesheet validation.
  - work-time calculation.
  - JSON load/save helpers.
- `database/timesheet_entries.json` stores the timesheet table as a JSON array.
- `database/employees.json` stores local fallback employee records only; TAC-employeeadmin is the primary employee master source.
- `database/projects.json` stores project/customer master records.
- `database/month_locks.json` stores Phase 3 monthly closing lock records.
- `database/invoice_drafts.json` stores invoice draft records.
- `database/audit_logs.json` stores append-only Phase 4 audit records for master data, timesheet entries/workflow, month locks, and invoice drafts.
- Master data routes include project/customer maintenance via `/projects` and `/project-new`; `/employees` is now a read-only employee source page and employee maintenance belongs in TAC-employeeadmin.
- Billing, invoice, and audit routes include `/billing`, `/invoices`, and `/audit-logs`.
- Timesheet rows snapshot selected employee/project/billing master data for audit and future invoicing.
- Employee selection is integrated with TAC-employeeadmin through its safe authenticated `/api/timesheet/employees` endpoint, with local `database/employees.json` retained as fallback/offline data; backend EmployeeAdmin API calls use the internal loopback host while browser navigation uses the public host.
- `docs/Timesheet_Table_Specification.md` documents the table schema and business rules.
- `docs/Phase3_Implementation_Plan.md` documents the recommended approval workflow and monthly lock implementation plan.
- `docs/Manual_Test_Checklist.md` is the manual verification checklist to run after each milestone.
- `docs/Supplier_Master_Data_Specification.md`, `docs/Customer_Master_Data_Specification.md`, `docs/One_Time_Party_Workflow.md`, `docs/OCR_Master_Data_Draft_Workflow.md`, and `docs/Master_Data_Enhancement_Roadmap.md` document the planned customer/supplier master data, one-time party, OCR draft, and implementation roadmap enhancements.

## Development rules

- Keep the MVP dependency-free unless the user approves adding a package manifest.
- Store work durations as integer minutes, not floats.
- Preserve audit fields (`created_at`, `updated_at`, `record_status`) on updates.
- Use soft delete for timesheet rows instead of physically removing records.
- Keep TAC-timesheet UI labels trilingual where useful: Simplified Chinese, Japanese, and English.
- Login/roles are now integrated through TACAI-Core/User_admin for Portal access; do not add a separate Timesheet login system.
- All non-health routes should require User_admin `tacai_session_id` validation and `timesheet.access`.
- Do not add Excel export or payroll integration unless requested as a later phase.


## MEMORY MANAGEMENT

The project must maintain a small active context window.
Memory Structure
1. memory/
2. archive/

File Size Policy
Green Zone
0KB - 30KB
Normal operation.
Yellow Zone
30KB - 100KB
Monitor growth and prepare for summarization.
Red Zone
Over 100KB
Archive and compress immediately.
Archive Rules
When any file under `/memory` exceeds 100KB:
Create archive copy.
Generate concise summary.
Replace active memory file with summary.
Never delete archive records.
Archive Naming Convention
1. archive/<module>/<filename>_YYYY_MM.md

Example:
1. archive/project_status/project_status_2026_06.md
2. archive/recruitment/recruitment_2026_06.md
3. archive/payroll/payroll_2026_06.md

Loading Rules
Do not automatically load archive files.
Only load:
CLAUDE.md
memory/project_status.md
related module memory file
Archive files should only be opened when explicitly requested.
Memory Update Rules
After every major task:
Update project_status.md
Update related module memory
Update decisions.md (if architectural decisions were made)
Update changelog.md (if system changes occurred)
Historical Preservation Policy
Never delete historical records.
When summarizing:
Preserve key decisions
Preserve business rules
Preserve architecture decisions
Preserve implementation status
Preserve unresolved issues
Archive files are the source of truth for historical details.


## Startup Loading Priority

On project startup, load files in this order:

1. CLAUDE.md
2. memory/project_status.md
3. memory/current_tasks.md
4. Related module memory

Do not load archive files automatically.





# Audit Rules

All modules must implement audit logging.

Required fields:

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

Audit logs must never be deleted.

Audit logs are read-only.

The local `/audit-logs` viewer provides the Phase 4 audit baseline; a future cross-module centralized audit viewer may still be added.

