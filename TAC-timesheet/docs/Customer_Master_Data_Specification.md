# Customer Master Data Specification

## Purpose

This document defines the planned customer master data enhancement for TAC-timesheet and future TACAI business modules. It covers formal customers, one-time customers, OCR-assisted customer draft creation from issued invoices, validation, approval, audit logging, and downstream billing support.

TAC-timesheet currently stores project/customer records in `database/projects.json`. This document describes the recommended next architecture for separating reusable customer master data from project/work records while preserving existing historical timesheet snapshots.

## Business objectives

1. Support customer data quality for Japan dispatch, RPO, recruitment, and payroll-management operations.
2. Allow temporary customer billing or transaction processing without blocking business workflows.
3. Use previously issued invoices to recover and enrich structured customer master data.
4. Prevent repeated use of one-time customer data where a formal client relationship exists.
5. Preserve audit history for customer create, update, approval, deactivation, and OCR conversion.

## Customer categories

| Category | Description |
|---|---|
| Recruitment Client | Permanent placement or recruiting-service client. |
| RPO Client | Recruitment process outsourcing client. |
| Haken Client | Dispatch client under Japan haken operations. |
| Payroll Client | Payroll or HR administration service client. |
| One-time Client | Temporary or non-recurring customer. |
| Internal / Group Company | Internal billing or group-company service recipient. |
| Other | Fallback category requiring later review. |

## Customer code rules

| Customer type | Code rule | Example |
|---|---|---|
| Formal customer | Sequential active customer code | `CUS-0001` |
| One-time customer | Fixed one-time customer code | `CUS-9999` |

Rules:

- `CUS-9999` is a fixed one-time customer placeholder.
- One-time customer-specific name, billing title, address, contact, and business reason must be saved at transaction level.
- Repeated use of the same one-time customer name should recommend conversion to formal customer master.
- Long-term haken, RPO, payroll, or contract customers should not remain under `CUS-9999`.

## Formal customer data model

Planned JSON fields:

| Field | Required | Description |
|---|---:|---|
| `customer_id` | Auto | Stable system ID, e.g. `cus-...`. |
| `customer_code` | Yes | Unique active customer code, e.g. `CUS-0001`. |
| `customer_name` | Yes | Legal or commonly used customer name. |
| `customer_name_kana` | No | Kana/search name for Japanese operations. |
| `customer_type` | Yes | Controlled customer category. |
| `is_one_time` | Auto | `false` for normal master rows; `true` only for fixed placeholder if represented. |
| `invoice_registration_number` | No | Customer registration/tax reference if available. |
| `country` | Yes | Default `Japan`. |
| `prefecture` | No | Japanese prefecture or region. |
| `address` | No | Billing or legal address. |
| `billing_contact_name` | No | Billing contact. |
| `billing_contact_email` | No | Billing email. |
| `business_contact_name` | No | Sales/business contact. |
| `business_contact_email` | No | Sales/business email. |
| `payment_terms` | No | Example: `月末締め翌月末払い`. |
| `invoice_delivery_method` | No | `email`, `postal`, `portal`, or `other`. |
| `status` | Auto | `draft`, `pending_review`, `active`, `inactive`, or `rejected`. |
| `source` | Auto | `manual`, `issued_invoice_ocr`, or `import`. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |
| `record_status` | Auto | `Active` or `Deleted` for soft-delete compatibility. |

## Relationship with project/customer master

Current TAC-timesheet has project/customer records in `database/projects.json` with fields such as `project_code`, `project_name`, `customer_name`, `customer_code`, billing flags, and rate information.

Recommended future direction:

1. Keep project/work records separate from customer master records.
2. Project records should reference `customer_id` / `customer_code` where available.
3. Timesheet rows should continue to snapshot customer/project names when saved.
4. Historical timesheet rows must not be rewritten when customer master records change.
5. During migration, existing `projects.json` customer fields can be used to seed customer drafts.

## Customer draft data model

OCR and manual drafts should be stored separately before becoming active customer master rows.

| Field | Required | Description |
|---|---:|---|
| `draft_id` | Auto | Draft ID, e.g. `customer-draft-...`. |
| `draft_type` | Auto | `customer`. |
| `source_document_id` | No | Uploaded invoice/document ID. |
| `source_type` | Yes | `issued_invoice`, `contract`, `order`, `manual`, or `import`. |
| `ocr_raw_text` | No | Original OCR text. |
| `ocr_extracted_fields` | No | Structured OCR result. |
| `confidence_score` | No | Overall OCR confidence if available. |
| `duplicate_candidates` | No | Candidate customers found by matching. |
| `review_notes` | No | Human review notes. |
| `status` | Auto | `ocr_imported`, `needs_review`, `duplicate_suspected`, `submitted`, `approved`, `converted`, or `rejected`. |
| `reviewed_by` | No | User_admin actor label. |
| `approved_by` | No | User_admin actor label. |
| `converted_customer_id` | No | Formal customer ID after conversion. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |

## Customer OCR sources

Preferred customer data sources:

1. Existing issued invoices created by TAC-timesheet or related modules.
2. Historical invoice PDF or scanned invoice image.
3. Customer contract/order files.
4. Manual entry by HR/Admin/Finance.
5. CSV/Excel import as a later phase.

If an invoice was generated by the system and structured invoice data exists, use structured source data before OCR. OCR should be used mainly for scanned documents, legacy PDFs, and external files.

## Validation rules

- `customer_name` is required for formal customers and customer drafts.
- Active customer codes must be unique.
- `CUS-9999` must remain reserved for one-time customer use.
- Formal haken, RPO, payroll, and long-term recruitment clients should be converted to active customer master.
- Inactive or deleted customers must not be selectable for new formal projects or billing transactions.
- Customer deletion should be soft delete only.
- If the same one-time customer name appears 3 or more times, the UI should recommend formal customer creation.
- If customer data comes from OCR, low-confidence fields should be explicitly reviewed before approval.

## Duplicate detection rules

Before approving or converting a customer draft, check likely duplicates by:

1. Exact or normalized customer name.
2. Similar customer name.
3. Existing `customer_code` in project records.
4. Address similarity.
5. Billing email.
6. Contact phone/email.
7. Historical invoice customer name.

A duplicate warning should require a reviewer note before conversion.

## Status lifecycle

```text
manual create / issued invoice OCR
        ↓
draft / ocr_imported
        ↓
needs_review
        ↓
submitted
        ↓
approved → converted → active
        ↘
        rejected
```

Active customers can later be deactivated. Historical timesheet, billing, and invoice draft snapshots must remain unchanged.

## Audit logging

Customer master changes must append audit rows to `database/audit_logs.json` or a future centralized audit store.

Recommended module/action keys:

| Module | Actions |
|---|---|
| `master_data.customer` | `create`, `update`, `soft_delete`, `deactivate`, `activate` |
| `master_data.customer_draft` | `ocr_import`, `update`, `submit`, `approve`, `reject`, `convert` |
| `master_data.one_time_customer_usage` | `use`, `approve`, `reject`, `convert_recommended` |

## MVP implementation scope

P0:

1. Reserve `CUS-9999` one-time customer logic.
2. Define transaction-level one-time customer fields.
3. Add customer draft model and status rules.
4. Add append-only audit coverage for customer draft and customer master changes.

P1:

1. Add customer list/manual draft page or extend existing project/customer maintenance carefully.
2. Add issued-invoice OCR/import draft flow.
3. Add duplicate warning by exact name and existing project `customer_code`.
4. Add manual approve/convert flow.

P2:

1. Separate customer master from project master with `customer_id` references.
2. Add customer completeness score.
3. Add customer merge/duplicate resolution.
4. Add import/export support after explicit approval.

## Open decisions

1. Confirm whether customer master remains inside TAC-timesheet first or moves to a shared Master Data Management module later.
2. Confirm whether existing `projects.json` records should seed customer drafts.
3. Confirm conversion threshold for one-time customers, e.g. 3 uses within 12 months.
4. Confirm OCR provider strategy and whether system-generated invoice data should bypass OCR.
