# CLAUDE.md

This file provides guidance to Claude Code when working in `/Users/terencewang/Documents/claude-project/TAC-salary`.

Project Name: TAC-salary

Before any task:

1. Confirm current project root: `/Users/terencewang/Documents/claude-project/TAC-salary`.
2. Confirm using this project's `CLAUDE.md`.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Startup loading priority

1. `CLAUDE.md`
2. `memory/project_status.md`
3. `memory/current_tasks.md`
4. Related module memory, usually `memory/salary.md`

Do not load archive files automatically.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 backend/app.py --host 127.0.0.1 --port 8005
```

Health check:

```bash
curl -s http://127.0.0.1:8005/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 -m py_compile backend/app.py
```

## Architecture

- `backend/app.py` is a Python standard-library local web app.
- `frontend/index.html` is the local manual salary entry UI.
- `database/salary_records.json` stores salary records as a JSON array.
- `database/employees.json` stores employee master placeholders as a JSON array.
- `database/audit_logs.json` stores append-only audit logs as a JSON array.
- `docs/Data_Schema.md` documents planned JSON schemas.
- `docs/Project_Plan.md` documents implementation phases.
- `docs/Salary_Table_Specification.md` documents salary fields, statuses, validation, and calculation rules.

## Memory management

Memory structure:

- `memory/`
- `archive/`

File size policy:

- Green: 0KB-30KB, normal operation.
- Yellow: 30KB-100KB, monitor and prepare summarization.
- Red: over 100KB, archive and compress immediately.

When any file under `memory/` exceeds 100KB:

1. Create archive copy under `archive/<module>/<filename>_YYYY_MM.md`.
2. Generate concise summary.
3. Replace active memory file with the summary.
4. Never delete archive records.

After every major task:

- Update `memory/project_status.md`.
- Update related module memory.
- Update `memory/decisions.md` if architectural decisions were made.
- Update `memory/changelog.md` if system changes occurred.

## Audit rules

All modules must implement audit logging with these required fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Audit logs must never be deleted. Audit logs are read-only from the application UI/API except for append-only system writes.

## Business rules

Think as:

- Software Architect
- Recruitment Consultant
- Business Operations Manager

Business focus:

- Recruitment Agency
- RPO
- Haken Business
- Payroll Management
- AI Recruitment Platform

Rules:

1. Follow Japan labor law and haken compliance.
2. Maintain reusable templates.
3. Store important decisions in `memory/decisions.md`.
4. Store business knowledge in future `skills/` or docs files.
5. Prefer modular salary architecture with reusable core logic and country-specific rule modules.
