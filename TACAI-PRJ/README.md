# TACAI Prj

Japan HR Finance System for payroll upload, employee payslip generation, Payroll Register / 給与花名冊 maintenance, payroll exports, and audit logs.

Project Name: TACAI-PRJ

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Project structure

```text
TACAI-PRJ
├── docs
│   ├── Project_Specification.md
│   ├── Payroll_Sample.xlsx
│   └── Accounting_Rules.md
├── frontend
├── backend
├── database
├── prompts
│   └── Payroll_Parser_Prompt.md
├── archive
│   └── reimbursement
├── memory
│   ├── project_memory.md
│   ├── coding_rules.md
│   └── development_log.md
└── README.md
```

## Run locally

TACAI runs separately from InterviewReady.

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-PRJ
python3 backend/app.py --host 127.0.0.1 --port 8001
```

Open:

```text
http://127.0.0.1:8001
```

Recommended local addresses:

- InterviewReady: `http://127.0.0.1:8000`
- TACAI Prj: `http://127.0.0.1:8001`

## Portal/User_admin integration

TACAI-PRJ Payroll is connected to TACAI Portal and protected by TACAI User Management.

- Portal URL: `http://127.0.0.1:8005`
- Payroll URL: `http://127.0.0.1:8001/`
- User_admin URL: `http://127.0.0.1:8006`
- Required module permission: `payroll.access`

All non-health payroll routes require a valid User_admin `tacai_session_id` cookie. Unauthenticated users are redirected to User_admin login with a local `next` return URL. The legacy local payroll login code is retained temporarily for historical fallback but is no longer the primary Portal path.

## Payroll input workflow

1. HR completes or imports EmployeeAdmin employee master data first; TACAI-PRJ does not maintain a local Employee Master.
2. HR creates payroll-specific Salary Profiles for employee references, country, work location, currency, rates, payroll scheme, and tax-reference inputs.
3. HR works in the monthly payroll input form using Salary Profiles, manual entry, or one Excel payroll/payslip row to fill the form.
4. HR reviews, edits, clears input values, adds payment/deduction items, and confirms tax amounts where needed.
5. HR confirms the form to save it into local payroll records.
6. Saved records appear in Payroll Register / 給与花名冊 and Payslips / 給与明細.
7. Payroll pages include a return button to the main Portal at `http://127.0.0.1:8005`.

## June 2026 payroll rollout status

- Japan, Singapore, and China June payroll employee lists are pending EmployeeAdmin Employee Master completion.
- Japan and Singapore payroll templates are treated as clarified business templates.
- China payroll has a standardized draft template in [Project Specification](docs/Project_Specification.md) and [Payroll Parser Prompt](prompts/Payroll_Parser_Prompt.md); business users should review and modify it before official payroll close.
- Do not create fake employee master records in TACAI-PRJ. Use Salary Profiles only for payroll-specific rates and references.

## Country-specific payroll reports

Payroll Register supports country-specific views and CSV exports:

- `country=CN` — Chinese payroll report template for China payroll items, attendance days, working days, hours, social insurance, housing fund, IIT, gross/net pay.
- `country=JP` — Japanese 給与台帳 template for Japan payroll items, working days, attendance days, working hours, hourly rate/pay, social insurance, income tax, resident tax, gross/net pay.
- `country=SG` — English Singapore Payroll Report template for monthly salary, attendance days/hours, CPF employee/employer fields, gross/net pay.
- `country=ALL` — common cross-country payroll summary.

CSV downloads use the same country filter and localized template as the register view. CSV files are UTF-8 with BOM and are intended to open cleanly in Excel. Native `.xlsx`, PDF payslips, merged PDF, and ZIP payslip bundles remain later-phase items unless an export dependency/service is approved.

Audit Logs also support CSV export for compliance review; the export event is itself written back to the append-only audit log.

## Main requirements

- Upload monthly Japanese payroll Excel files.
- Manually input monthly payroll items when HR does not have an Excel file.
- Preview system-filled/calculated payroll numbers for HR confirmation.
- Confirm payroll input into local payroll records.
- Generate employee payslips.
- Automatically generate and maintain Payroll Register / 給与花名冊.
- Retain payroll records, payslips, and audit logs in the database.
- Export payroll register and audit logs to Excel-compatible CSV in the current MVP; native Excel/PDF exports are planned later-phase items.

## Key documents

- [Project Specification](docs/Project_Specification.md)
- [Accounting Rules](docs/Accounting_Rules.md)
- [Payroll Parser Prompt](prompts/Payroll_Parser_Prompt.md)

## Scope note

Expense reimbursement / 経費精算 is no longer part of TACAI-PRJ. Archived reimbursement reference assets are kept under [archive/reimbursement](archive/reimbursement/) for a future standalone reimbursement application.


# MEMORY MANAGEMENT

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

