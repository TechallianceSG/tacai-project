# Supplier Master Data Specification

## Purpose

This document defines the planned supplier master data enhancement for TAC-timesheet and future TACAI business modules. The goal is to support normal suppliers, one-time suppliers, OCR-assisted supplier draft creation, approval, audit traceability, and later downstream payment/procurement workflows while preserving the current local-first, dependency-free MVP direction.

The first implementation target should be planning and data design. The supplier master should not immediately replace existing project/customer master behavior until the required data migration and UI changes are approved.

## Business objectives

1. Avoid blocking business transactions when a formal supplier master record does not exist yet.
2. Improve supplier master quality by using invoice OCR to prepare drafts instead of directly creating active records.
3. Reduce payment and fraud risk around supplier bank information.
4. Preserve audit evidence for supplier create, update, status change, bank change, OCR conversion, and one-time supplier usage.
5. Support Japan business operations, including invoice registration number tracking where applicable.

## Supplier categories

| Category | Description | Typical examples |
|---|---|---|
| Recruitment Channel | Recruiting media, job boards, candidate sourcing channels | Job board invoice supplier |
| IT / SaaS | Software, cloud, subscriptions | ATS, AI tool, storage |
| Office / Admin | Office operations and administration | Supplies, courier, rental |
| Legal / Accounting | Professional service vendors | Accountant, legal office |
| Contractor / Freelancer | External individual or company service provider | Freelance recruiter, consultant |
| Travel / Expense | Travel or expense-related suppliers | Hotel, transport agency |
| Other | Fallback category | Needs review later |

## Supplier code rules

| Supplier type | Code rule | Example |
|---|---|---|
| Formal supplier | Sequential active supplier code | `SUP-0001` |
| One-time supplier | Fixed one-time supplier code | `SUP-9999` |

Rules:

- `SUP-9999` is a fixed one-time supplier placeholder.
- Do not generate many pseudo-master records for each temporary supplier.
- When `SUP-9999` is selected in a downstream transaction, the transaction must store one-time supplier name, description, attachment, and payment-related details on the transaction itself.
- Repeated use of the same one-time supplier name should trigger a conversion recommendation to formal supplier master.

## Formal supplier data model

Planned JSON fields:

| Field | Required | Description |
|---|---:|---|
| `supplier_id` | Auto | Stable system ID, e.g. `sup-...`. |
| `supplier_code` | Yes | Unique active supplier code, e.g. `SUP-0001`. |
| `supplier_name` | Yes | Legal or invoice name. |
| `supplier_name_kana` | No | Kana/search name for Japanese operations. |
| `supplier_type` | Yes | Controlled supplier category. |
| `is_one_time` | Auto | `false` for normal supplier master rows; `true` only for fixed placeholder if represented in the master list. |
| `invoice_registration_number` | No | Japan qualified invoice issuer number, e.g. `T1234567890123`. |
| `corporate_number` | No | Corporate number where available. |
| `country` | Yes | Default `Japan`. |
| `prefecture` | No | Japanese prefecture or region. |
| `address` | No | Supplier address. |
| `contact_name` | No | Main contact person. |
| `contact_email` | No | Contact email. |
| `contact_phone` | No | Contact phone. |
| `payment_terms` | No | Example: `月末締め翌月末払い`. |
| `bank_name` | Conditional | Required before payment activation when bank transfer is used. |
| `bank_branch` | Conditional | Required before payment activation when available. |
| `bank_account_type` | Conditional | Ordinary/current/etc. |
| `bank_account_number` | Conditional | Bank account number. |
| `bank_account_holder` | Conditional | Account holder name. |
| `status` | Auto | `draft`, `pending_review`, `active`, `inactive`, or `rejected`. |
| `source` | Auto | `manual`, `ocr`, or `import`. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |
| `record_status` | Auto | `Active` or `Deleted` for soft-delete compatibility. |

## Draft supplier data model

OCR or manual draft data should be stored separately from formal active suppliers.

| Field | Required | Description |
|---|---:|---|
| `draft_id` | Auto | Draft ID, e.g. `supplier-draft-...`. |
| `draft_type` | Auto | `supplier`. |
| `source_document_id` | No | Uploaded document ID. |
| `source_type` | Yes | `supplier_invoice`, `receipt`, `quotation`, `contract`, or `manual`. |
| `ocr_raw_text` | No | Original extracted text. |
| `ocr_extracted_fields` | No | Raw structured OCR result. |
| `confidence_score` | No | Overall OCR confidence if available. |
| `duplicate_candidates` | No | Candidate active suppliers found by matching. |
| `review_notes` | No | Human review notes. |
| `status` | Auto | `ocr_imported`, `needs_review`, `duplicate_suspected`, `submitted`, `approved`, `converted`, or `rejected`. |
| `reviewed_by` | No | User_admin actor label. |
| `approved_by` | No | User_admin actor label. |
| `converted_supplier_id` | No | Formal supplier ID after conversion. |
| `created_at` | Auto | UTC ISO datetime. |
| `updated_at` | Auto | UTC ISO datetime. |

## Validation rules

- `supplier_name` is required for formal suppliers and supplier drafts.
- Active supplier codes must be unique.
- `SUP-9999` must remain reserved for one-time supplier use.
- Bank fields from OCR must never become active without human confirmation.
- Bank information creation or change should require review/approval before payment use.
- Inactive or deleted suppliers must not be selectable for new formal transactions.
- Supplier deletion should be soft delete only.
- If the same one-time supplier name appears 3 or more times, the UI should recommend formal supplier creation.
- If a one-time supplier transaction exceeds the configured threshold, approval is required before payment-sensitive downstream processing.

## Duplicate detection rules

Before approving a draft or creating a supplier, check likely duplicates by:

1. Exact or normalized supplier name.
2. Similar supplier name.
3. Invoice registration number.
4. Corporate number.
5. Bank account holder and account number.
6. Address similarity.
7. Contact email or phone.

A duplicate warning should not automatically block creation in MVP, but it should require a reviewer note.

## Status lifecycle

```text
manual create / OCR import
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

Formal active suppliers can later move to `inactive` by soft deactivation. Historical transactions should keep snapshots and not be rewritten.

## Audit logging

Supplier master changes must append audit rows to `database/audit_logs.json` or a future centralized audit store. Required fields follow the project rule:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Recommended module/action keys:

| Module | Actions |
|---|---|
| `master_data.supplier` | `create`, `update`, `soft_delete`, `deactivate`, `activate`, `bank_change` |
| `master_data.supplier_draft` | `ocr_import`, `update`, `submit`, `approve`, `reject`, `convert` |
| `master_data.one_time_supplier_usage` | `use`, `approve`, `reject`, `convert_recommended` |

## MVP implementation scope

P0:

1. Reserve `SUP-9999` one-time supplier logic.
2. Define transaction-level one-time supplier fields.
3. Add supplier draft model and status rules.
4. Add append-only audit coverage for supplier draft and master changes.

P1:

1. Add supplier list and manual draft creation page.
2. Add OCR upload placeholder/import endpoint that can store raw text and extracted JSON once OCR provider selection is approved.
3. Add duplicate warning by exact name and registration number.
4. Add manual approve/convert flow.

P2:

1. Add bank-change approval.
2. Add threshold-based one-time supplier approval.
3. Add confidence score and field-level OCR review UI.
4. Add duplicate scoring and merge support.

## Open decisions

1. Confirm the payment approval threshold for one-time suppliers, e.g. 50,000 JPY or 100,000 JPY.
2. Confirm whether supplier master belongs inside TAC-timesheet or should be a future shared Master Data Management module.
3. Confirm OCR provider strategy: local/manual OCR import first, external OCR later, or no external service until approved.
4. Confirm whether supplier bank information is in scope for the first implementation or only documented for later payment modules.
