# VendorPayables Project Plan

## Purpose

Build a lightweight supplier payment / vendor payables management MVP for Japan SME outsourcing, recruitment, RPO, haken, and headhunting businesses.

This project is separate from employee reimbursement. It handles external supplier invoices and payment requests such as recruitment media fees, outsourcing project costs, SaaS fees, and professional services.

## Goals

- Prevent missed supplier payments.
- Record invoice/request intake and payment dates.
- Keep payable records searchable by vendor, status, category, and due date.
- Preserve attachment files and audit history.
- Support Japanese, English, and Chinese business users.
- Prepare for future OCR/AI-assisted input without making OCR mandatory.

## MVP Scope

### Phase 1 — Skeleton and documentation

- Create project directory and docs.
- Create JSON database files.
- Create trilingual i18n files.
- Implement local Python standard-library web app skeleton.

### Phase 2 — Manual payable entry

- Dashboard.
- Payables list.
- New/edit/detail payable pages.
- Required dates:
  - invoice date
  - received date
  - payment due date
  - actual payment date
- Status flow.
- Validation rules.

### Phase 3 — Vendor master

- Vendor list.
- Add/edit vendor.
- Active/inactive vendor status.
- Vendor snapshot copied into payable records.

### Phase 4 — Attachments

- Upload invoice/request files.
- Supported MVP file types: PDF, JPG, JPEG, PNG, WEBP.
- Store file metadata in payable records.

### Phase 5 — Audit and exports

- Append-only audit logs.
- CSV export for finance review.
- Export history.

### Phase 6 — OCR/AI later

- Extract invoice data from PDF/JPG/PNG.
- Show extracted values as draft suggestions in the same payable form.
- Finance confirmation required before submit/approval/payment.

## Out of Scope for MVP

- Full accounting ledger.
- Bank transfer file generation.
- Complex multi-level approval.
- Production RDBMS.
- Cloud OCR or paid AI extraction.
- Automatic tax filing.
