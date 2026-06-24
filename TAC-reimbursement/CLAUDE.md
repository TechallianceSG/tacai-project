# CLAUDE.md

This file provides guidance to Claude Code when working with the TAC-reimbursement project.

Project Name: TAC-reimbursement

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.


This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.


## Project overview

TAC-reimbursement is a standalone Japan employee reimbursement self-service MVP. It is separate from TACAI-PRJ and TAC-timesheet.

Employees submit receipt/invoice claims. The preferred input is image/PDF upload with OCR-assisted data extraction. Manual entry remains available. Finance performs one-level approval. Month-end reports support payroll and salary payment calculation.

## Current state

Phase 1 manual entry MVP is implemented. The app supports dashboard, claim list, manual claim entry/edit, attachment upload, Draft/Submitted statuses, validation, and soft delete for editable claims.

## Development rules

- Do not mix this project into TACAI-PRJ or TAC-timesheet.
- Keep the MVP local-first and dependency-free unless the user approves dependencies.
- Store money as integer JPY yen or decimal strings; do not use floats for money.
- Keep receipt/invoice attachments under this project only.
- Keep labels bilingual where useful: English plus Japanese, and Chinese notes where helpful for planning.
- OCR output must be treated as a draft; users must confirm extracted fields before submission.
- One-level finance approval is in scope for MVP.
- Login/roles are now integrated through TACAI-Core/User_admin for Portal access; do not add a separate reimbursement login system.
- All non-health routes should require User_admin `tacai_session_id` validation and `reimbursement.access`.
- Production database, cloud OCR, and payroll integration remain later-phase decisions unless requested.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
python3 backend/app.py --host 127.0.0.1 --port 8003
```

Health check:

```bash
curl -s http://127.0.0.1:8003/health
```

Local OCR tool checks:

```bash
tesseract --version
tesseract --list-langs
pdftoppm -v
swift --version
```

On macOS, the app falls back to Apple's local Vision OCR via `backend/macos_vision_ocr.swift` when Tesseract/Poppler are not installed.

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

## Important documents

- `docs/Project_Plan.md` — staged implementation plan.
- `docs/Workflow_Specification.md` — claim submission and approval workflow.
- `docs/Data_Schema.md` — proposed JSON schemas.
- `docs/Reporting_Plan.md` — month-end report fields.
- `prompts/OCR_Receipt_Prompt.md` — OCR extraction prompt draft.




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

Future centralized audit viewer may be added.