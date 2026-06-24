# CLAUDE.md

This file provides guidance to Claude Code when working with the TAC-employeeadmin project.

Project Name: TAC-employeeadmin

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Project overview

TAC-employeeadmin is a standalone local MVP project for employee administration. It is separate from TACAI-PRJ, TAC-timesheet, TAC-reimbursement, and InterviewReady.

The initial project state is a clean skeleton with a dependency-free Python standard-library local web app. Employee administration requirements, data fields, approval workflows, and integrations should be confirmed before implementation.

## Development rules

- Do not mix this project into TACAI-PRJ, TAC-timesheet, TAC-reimbursement, or InterviewReady.
- Keep the MVP local-first and dependency-free unless the user approves dependencies.
- Store local data under this project only.
- Keep labels trilingual where useful: Simplified Chinese, English, and Japanese. Chinese is important because many operators are Chinese speakers.
- Treat this project as independent employee master/admin functionality unless the user explicitly requests integration.
- Authentication is now integrated with TACAI-Core/User_admin for Portal access; production database, HR/payroll integration, and external API integration remain later-phase decisions unless requested.
- All non-health routes should require User_admin `tacai_session_id` validation and `employee_management.access`.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 backend/app.py --host 127.0.0.1 --port 8004
```

Health check:

```bash
curl -s http://127.0.0.1:8004/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 -m py_compile backend/app.py
```

## Important documents

- `README.md` — project overview and local run commands.
- `docs/Requirements.md` — product objectives and module requirements.
- `docs/Project_Plan.md` — staged implementation roadmap and MVP plan.
- `docs/Data_Schema.md` — employee data schema draft, enums, audit log draft, and i18n resource draft.

## MEMORY MANAGEMENT

The project must maintain a small active context window.

Memory Structure

1. memory/
2. archive/

File Size Policy

Green Zone: 0KB - 30KB, normal operation.
Yellow Zone: 30KB - 100KB, monitor growth and prepare for summarization.
Red Zone: Over 100KB, archive and compress immediately.

Archive Rules

When any file under `/memory` exceeds 100KB:

1. Create archive copy.
2. Generate concise summary.
3. Replace active memory file with summary.
4. Never delete archive records.

Archive Naming Convention

```text
archive/<module>/<filename>_YYYY_MM.md
```

Loading Rules

Do not automatically load archive files.
Only load:

1. CLAUDE.md
2. memory/project_status.md
3. memory/current_tasks.md
4. Related module memory

Memory Update Rules

After every major task:

1. Update project_status.md.
2. Update related module memory.
3. Update decisions.md if architectural decisions were made.
4. Update changelog.md if system changes occurred.

Historical Preservation Policy

Never delete historical records. When summarizing, preserve key decisions, business rules, architecture decisions, implementation status, and unresolved issues.





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