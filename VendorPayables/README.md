# VendorPayables

VendorPayables is a lightweight supplier payment / accounts payable MVP for Japan SME outsourcing, recruitment, RPO, haken, and headhunting businesses.

## Purpose

This project manages external supplier invoices and payment requests, including:

- recruitment website and job media fees
- outsourcing project costs
- SaaS and system usage fees
- professional service fees
- office and administrative supplier invoices

It is separate from employee reimbursement. Employee daily expense claims belong in reimbursement; supplier invoices belong here.

## MVP Features

- Vendor selection from TACAI-Core Master Data Management
- Manual vendor payable entry
- Invoice/request attachment upload
- Invoice date, received date, payment due date, and actual payment date tracking
- Draft, Submitted, Approved, Scheduled, Paid, Rejected, and Cancelled statuses
- SAP-like dashboard, list, detail, and form pages
- English, Japanese, and Chinese UI labels
- CSV export
- Append-only audit logging
- OCR/AI extraction planned as a later phase

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/VendorPayables
python3 backend/app.py --host 127.0.0.1 --port 8008
```

Open:

```text
http://127.0.0.1:8008/
```

Health check:

```bash
curl -s http://127.0.0.1:8008/health
```

## Syntax check

```bash
python3 -m py_compile backend/app.py
```

## Storage

VendorPayables transaction storage is local to this project. Vendor Master is maintained in `../TACAI-Core/masterdata/database/vendors.json`.

- `database/vendor_payables.json`
- `database/vendors.deprecated.json` — retained only as migration history if present
- `database/audit_logs.json`
- `database/report_exports.json`
- `attachments/`

## Port

Default local port: `8008`.
