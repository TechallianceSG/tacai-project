# CLAUDE.md

This file provides guidance to Claude Code when working in `/Users/terencewang/Documents/claude-project/TACAI-Core/masterdata`.

Project Name: TACAI-Core/masterdata

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

## Purpose

`masterdata` is the TACAI Core Platform Master Data Management module.

It centrally owns organization master data for TACAI business modules:

- Entity Management
- Department Management
- Team Management
- Customer Master for Customer Billing / Client Revenue
- Vendor Master for VendorPayables / supplier payments

Business modules must reference these centralized records instead of maintaining their own organization structures. Customer Billing must read customer master data from this module and keep billing-time snapshots on issued documents. VendorPayables must read vendor master data from this module and keep payable-time vendor snapshots on payment records.

## Scope V1

V1 implements only:

- Legal Entity master
- Department master
- Team master
- Customer Master for client revenue / customer billing
- Vendor Master for supplier payments / vendor payables
- English, Japanese, and Chinese labels
- Local JSON storage planning
- Audit logging planning
- Portal integration planning
- User_admin role/permission integration planning

Reserved for future phases:

- Employment Type Master
- Visa Type Master
- Country Master
- Currency Master
- Skill Category Master
- Training Category Master

## Planned local port convention

Recommended local port:

```text
8007
```

This keeps TACAI Core services side by side:

- TACAI Portal: `8005`
- TACAI User Management: `8006`
- TACAI Master Data Management: `8007`

## Commands

A runnable local MVP exists in `backend/app.py` using only Python standard-library modules. Keep future changes dependency-free unless the user approves external packages.

Run command:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/masterdata
python3 backend/app.py --host 127.0.0.1 --port 8007
```

Health check:

```bash
curl -s http://127.0.0.1:8007/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/masterdata
python3 -m py_compile backend/app.py
```

## Architecture

- `backend/app.py` — Python standard-library local web app with User_admin-backed session validation, Entity Management CRUD, and Department Management CRUD.
- `database/entities.json` — legal entity master data.
- `database/departments.json` — department master data.
- `database/teams.json` — team master data.
- `database/customers.json` — customer/client master data used by Customer Billing.
- `database/vendors.json` — supplier/vendor master data used by VendorPayables.
- `database/audit_logs.json` — append-only MDM audit trail.
- `docs/Project_Plan.md` — SAP-style implementation plan.
- `docs/Data_Schema.md` — planned JSON schemas and validation rules.
- `docs/Portal_Integration_Plan.md` — TACAI Portal and User_admin integration plan.

## Portal integration rule

In TACAI Portal navigation, Master Data Management should be placed before User Management.

Recommended order:

1. Dashboard
2. Employee Mgmt
3. Timesheet
4. Payroll
5. Expense
6. Master Data Management
7. User Management

## Security and authorization direction

Authentication and authorization should use TACAI-Core/User_admin.

Planned access model:

- System Admin: full access
- HR Manager: view and maintain organization masters
- Finance: view Customer Master, maintain customer/client revenue master data through `client_revenue.customer_master.maintain`, and maintain Vendor Master through `masterdata.maintain`
- Normal User / Employee: view only where permitted

All create, update, and soft-delete operations must be audited.

## Audit rules

All state-changing MDM events must append audit logs with these fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Audit logs must never be deleted and should be treated as read-only history.

## Development rules

- Keep V1 local-first and dependency-free unless the user approves dependencies.
- Store local data under this project only.
- Master Data Management is the sole source of truth for entity, department, and team organization data.
- Do not let Employee Management, Timesheet, Payroll, or Expense create their own organization master data after integration.
- Use soft delete/status changes only; do not physically delete master records unless explicitly approved.
- Preserve auditability for all changes.
- Keep UI labels bilingual where useful: English and Japanese. Chinese planning notes are acceptable in documentation.

## Memory management

After every major task:

1. Update `memory/project_status.md`.
2. Update `memory/current_tasks.md`.
3. Update `memory/decisions.md` if architectural decisions were made.
4. Update `memory/changelog.md` if system changes occurred.

Do not automatically load archive files. Archive files should only be opened when explicitly requested.
