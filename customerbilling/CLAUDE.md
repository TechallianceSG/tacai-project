# CLAUDE.md

This file provides guidance to Claude Code when working with the Customer Billing project.

Project Name: customerbilling

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Project overview

Customer Billing is a standalone local-first Billing & Accounts Receivable MVP for Japan SME dispatch, recruitment, RPO, and headhunting businesses.

It manages customer invoice/request note creation, manual payment tracking, AR reports, and audit logs. It is the client revenue counterpart to VendorPayables. Customer Master is owned by TACAI-Core/masterdata and read by this module through Master Data APIs.

## Commands

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/customerbilling
python3 backend/app.py --host 127.0.0.1 --port 8009
```

Health check:

```bash
curl -s http://127.0.0.1:8009/health
```

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

JSON validation:

```bash
python3 -m json.tool database/customer_billings.json
python3 -m json.tool database/customers.json
python3 -m json.tool database/company_profile.json
python3 -m json.tool database/audit_logs.json
python3 -m json.tool database/report_exports.json
```

## Architecture

- `backend/app.py` is a Python standard-library local web app.
- `database/customer_billings.json` stores invoice/request note records as a JSON array.
- `database/customers.json` is retained only as a legacy/migration source; active customer master data lives in `TACAI-Core/masterdata/database/customers.json`.
- `database/company_profile.json` stores issuer tax/registration and bank information.
- `database/audit_logs.json` stores append-only audit records.
- `database/report_exports.json` stores export/report history.
- `i18n/` stores Japanese, English, and Chinese labels.

## Portal integration

- TACAI Portal module label: `Customer Billing` / `顧客請求` / `客户请款`.
- Portal URL: `http://127.0.0.1:8009/`.
- Portal visibility permission: `client_revenue.access`.
- Finance role users are intended to see and use this module.

## Development rules

- Keep the MVP dependency-free unless the user approves dependencies.
- Store money as integer JPY yen or decimal strings; do not use floats for money.
- Japanese and English invoice/request formats are first priority; Chinese remains available as optional labels/templates.
- Customer master data is maintained in TACAI Master Data; Customer Billing must not create or edit local customer master records.
- Issued billing records must keep customer snapshots and must not be overwritten when Master Data customer records change.
- Issued records should not be overwritten directly; use copy, cancel, payment registration, or status actions.
- Use soft cancel/deactivate behavior; do not physically delete business or audit records.
- All non-health routes must require User_admin `tacai_session_id` validation and `client_revenue.access`.

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
