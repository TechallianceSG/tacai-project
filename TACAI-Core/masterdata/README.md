# TACAI Core Platform - Master Data Management V1

Master Data Management is a TACAI Core Platform module for centralized organization master data.

## Objective

Create a centralized Master Data Management module under TACAI Core Platform.

This module provides shared master data for:

- Employee Management
- Timesheet Management
- Payroll Management
- Expense Management
- Customer Billing / Client Revenue
- Future Training Management

Business modules must not maintain their own organization structures. Customer Billing must reference Customer Master records here and keep historical customer snapshots on billing documents.

## Module structure

```text
TACAI Core Platform
├── Master Data Management
│   ├── Entity Management
│   ├── Department Management
│   ├── Team Management
│   ├── Customer Master
│   └── System Parameters
├── User Management
├── Audit Log
└── Language Engine
```

In TACAI Portal, Master Data Management should be displayed before User Management.

## V1 scope

V1 implements:

- Entity master implemented in Phase 2
- Department master implemented in Phase 3
- Team master implemented in Phase 4
- Customer Master implemented for Customer Billing / Client Revenue
- English and Japanese language support
- User_admin-backed access control
- Append-only audit logging
- Governed update/deactivate/restore flow with change reason, acknowledgement, version history, field comparison, and restore-as-new-version
- Portal launcher integration planning
- System Parameters ownership for outbound onboarding email settings consumed by EmployeeAdmin

## Local service

Phase 1, Phase 2, and Phase 3 backend code has been implemented for the local MVP. The module now provides a dependency-free Python backend, User_admin-backed session validation, bilingual English/Japanese UI labels, local JSON files, Entity Management CRUD, and Department Management CRUD with soft delete and audit logging.

Local port:

```text
8007
```

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/masterdata
python3 backend/app.py --host 127.0.0.1 --port 8007
```

Open:

```text
http://127.0.0.1:8007/dashboard
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

## Database files

```text
database/
├── entities.json
├── departments.json
├── teams.json
├── customers.json
├── vendors.json
├── system_parameters.json
├── audit_logs.json
└── masterdata_versions.json
```

## Documentation

- [Project_Plan.md](docs/Project_Plan.md) — SAP-style project plan and implementation steps.
- [Data_Schema.md](docs/Data_Schema.md) — planned data fields, validations, and JSON shape.
- [Portal_Integration_Plan.md](docs/Portal_Integration_Plan.md) — Portal/User_admin/business-module integration plan.

## System Parameters

Master Data now owns shared System Parameters. The first parameter is `email.onboarding.smtp`, used by EmployeeAdmin onboarding email delivery. Authorized operators can open it from the Master Data Dashboard System Parameters card or maintain it directly in Master Data:

```text
http://127.0.0.1:8007/master-data/system-parameters?lang=en
```

EmployeeAdmin no longer renders or updates the System Parameters UI. It reads the runtime SMTP settings through the Master Data internal API:

```text
GET /api/master-data/system-parameters/outbound-email-onboarding
Header: X-TACAI-Internal-Token: <MASTERDATA_INTERNAL_API_TOKEN>
```

Required runtime environment for the local MVP:

- `MASTERDATA_INTERNAL_API_TOKEN` — shared internal token for service-to-service reads.
- `ONBOARDING_SMTP_PASSWORD` — SMTP/app password when the parameter uses `password_config_mode=environment` and `password_secret_ref=ONBOARDING_SMTP_PASSWORD`.

The UI never displays the actual SMTP password, and audit/version snapshots must not store plaintext secrets.
