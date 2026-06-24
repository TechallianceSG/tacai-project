# CLAUDE.md

This file provides guidance to Claude Code when working with the VendorPayables project.

Project Name: VendorPayables

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Project overview

VendorPayables is a standalone local-first vendor payables / supplier payment management MVP for Japan SME outsourcing, recruitment, RPO, haken, and headhunting businesses.

It is separate from employee reimbursement. It manages external supplier invoices and payment requests such as recruitment media fees, outsourcing project costs, SaaS fees, professional service fees, and office/admin supplier invoices.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/VendorPayables
python3 backend/app.py --host 127.0.0.1 --port 8008
```

Health check:

```bash
curl -s http://127.0.0.1:8008/health
```

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

JSON validation:

```bash
python3 -m json.tool database/vendor_payables.json
python3 -m json.tool ../TACAI-Core/masterdata/database/vendors.json
python3 -m json.tool database/audit_logs.json
python3 -m json.tool database/report_exports.json
```

## Portal integration

- TACAI Portal module label: `Vendor Payments` / `仕入先支払` / `供应商付款`.
- Portal URL: `http://127.0.0.1:8008/`.
- Portal visibility permission: `vendor_expense.access`.
- Finance role users are intended to see this module in TACAI Portal.

## Architecture

- `backend/app.py` is a Python standard-library web app.
- `database/vendor_payables.json` stores vendor payable records as a JSON array.
- Vendor Master is maintained in `../TACAI-Core/masterdata/database/vendors.json`; `database/vendors.deprecated.json` is retained only as migration history if present.
- `database/audit_logs.json` stores append-only audit logs.
- `database/report_exports.json` stores export history.
- `attachments/` stores uploaded invoice/request files.
- `i18n/` stores English, Japanese, and Chinese UI labels.

## Development rules

- Keep the MVP dependency-free unless the user approves dependencies.
- Store money as integer JPY yen or decimal strings; do not use floats for money.
- Vendor master data lives in TACAI-Core/masterdata; do not add local VendorPayables vendor CRUD.
- Payable records should snapshot vendor code, vendor name, qualified invoice number, and payment terms for audit/history.
- Use soft cancel/delete behavior; do not physically delete business or audit records.
- OCR/AI output must be treated as draft assistance only; finance users must confirm extracted values.
- Keep UI labels trilingual where useful: Japanese, English, and Simplified Chinese.
- Use SAP-like enterprise UI conventions consistent with TAC MVP modules.

## Audit Rules

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

## MEMORY MANAGEMENT

The project must maintain a small active context window.

Loading priority:

1. CLAUDE.md
2. memory/project_status.md
3. memory/current_tasks.md
4. Related module memory

Do not load archive files automatically.

After every major task update:

- memory/project_status.md
- memory/current_tasks.md
- memory/decisions.md if architectural decisions were made
- memory/changelog.md if system changes occurred
