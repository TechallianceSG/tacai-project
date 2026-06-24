# Customer and Supplier Master Data Enhancement Roadmap

## Purpose

This roadmap converts the customer/supplier master data analysis into an executable implementation sequence for TAC-timesheet and future TACAI shared master data work.

It should be used together with:

- [Supplier Master Data Specification](Supplier_Master_Data_Specification.md)
- [Customer Master Data Specification](Customer_Master_Data_Specification.md)
- [One-Time Supplier and Customer Workflow](One_Time_Party_Workflow.md)
- [OCR Master Data Draft Workflow](OCR_Master_Data_Draft_Workflow.md)

## Guiding principles

1. One-time parties keep business workflows moving but must not pollute formal master data.
2. OCR creates drafts only; it must not directly create active supplier/customer records.
3. Supplier bank information is payment-sensitive and must require human review.
4. Customer/project/timesheet historical snapshots must not be rewritten by later master-data changes.
5. Every state-changing master-data action must append audit logs.
6. Keep the MVP dependency-free unless the user approves a package/provider integration.
7. Keep UI labels trilingual where user-facing screens are added.

## Recommended implementation sequence

### Phase 0 — Decision confirmation

Duration: 0.5-1 day.

Confirm:

- Whether the first implementation remains inside TAC-timesheet or moves to a separate shared Master Data Management module.
- Whether `SUP-9999` and `CUS-9999` are final reserved one-time codes.
- Approval threshold for one-time supplier/customer use.
- Which roles can create, review, approve, and convert drafts.
- OCR strategy: manual text/JSON import first vs external OCR integration later.
- Whether uploaded source documents are stored in the module or only referenced.

Exit criteria:

- Business rule decisions are recorded in `memory/decisions.md`.
- MVP scope is agreed before coding.

### Phase 1 — Schema and local JSON foundation

Duration: 1-2 days.

Tasks:

1. Add planned JSON files if implemented inside TAC-timesheet:
   - `database/suppliers.json`
   - `database/customers.json`
   - `database/supplier_drafts.json`
   - `database/customer_drafts.json`
2. Add helper functions for load/save, ID generation, timestamps, soft delete, and status validation.
3. Add module audit keys:
   - `master_data.supplier`
   - `master_data.customer`
   - `master_data.supplier_draft`
   - `master_data.customer_draft`
   - `master_data.one_time_supplier_usage`
   - `master_data.one_time_customer_usage`
4. Add reserved-code validation for `SUP-9999` and `CUS-9999`.

Exit criteria:

- JSON files initialize safely.
- Syntax check passes.
- Audit helper can record new module keys.

### Phase 2 — Manual master/draft pages

Duration: 2-4 days.

Tasks:

1. Add supplier list/detail/create/edit pages.
2. Add customer list/detail/create/edit pages or carefully extend existing project/customer page.
3. Add draft list/detail/review pages.
4. Add draft statuses: `draft`, `needs_review`, `submitted`, `approved`, `converted`, `rejected`.
5. Add soft delete/deactivate behavior.
6. Add duplicate warning by exact normalized name and code/registration number.
7. Add trilingual labels.

Exit criteria:

- Users can create and edit manual supplier/customer drafts.
- Drafts can be submitted, approved, rejected, and converted.
- Audit logs are written for each state change.

### Phase 3 — One-time supplier/customer transaction support

Duration: 2-3 days.

Tasks:

1. Identify the first transaction forms where one-time parties should apply.
2. Add selector behavior for `SUP-9999` / `CUS-9999`.
3. Add one-time party detail sections.
4. Persist transaction-level one-time fields.
5. Add required name/reason validation.
6. Add attachment requirement hook where the transaction supports attachments.
7. Add repeat-use warning based on normalized one-time party name.
8. Add audit rows for one-time usage.

Exit criteria:

- Selecting a one-time code opens a required detail section.
- The transaction can proceed with clear manual party details.
- Repeat-use recommendation is shown when the same name appears 3 or more times.

### Phase 4 — OCR import MVP

Duration: 3-5 days.

Tasks:

1. Add a manual OCR import page or upload placeholder.
2. Store original document metadata/source reference.
3. Store `ocr_raw_text` and `ocr_extracted_fields` in draft records.
4. Map supplier invoice fields to supplier draft.
5. Map issued customer invoice fields to customer draft.
6. Show raw OCR text and editable mapped fields.
7. Add duplicate warning before submission.
8. Keep OCR-derived bank fields unverified until human confirmation.

Exit criteria:

- OCR/import creates a draft only.
- Draft fields are editable before approval.
- Raw OCR data is preserved for audit/review.

### Phase 5 — Approval, controls, and reporting

Duration: 2-4 days.

Tasks:

1. Add approval role checks based on User_admin session context where available.
2. Add amount-threshold approval for one-time party usage.
3. Add supplier bank-change audit action.
4. Add dashboard/report for one-time party usage.
5. Add master data completeness score.
6. Add warning/report for duplicate candidates and repeated one-time use.

Exit criteria:

- High-risk one-time and supplier-bank cases require review.
- Finance/Admin can review usage and audit history.

## MVP cut line

Recommended first coding MVP:

1. Documentation and decisions.
2. JSON schemas and audit module keys.
3. Manual supplier/customer drafts.
4. One-time code reservation and transaction-level field schema.
5. OCR raw text/JSON import to draft, without external OCR provider.

Defer:

- External OCR provider integration.
- Automatic bank verification.
- Fuzzy duplicate matching.
- Excel/PDF export.
- Cross-module centralized audit viewer.
- Full shared MDM extraction.

## Acceptance checklist

- [ ] `SUP-9999` and `CUS-9999` cannot be accidentally assigned as normal active partner codes.
- [ ] One-time party transaction details include name and business reason.
- [ ] OCR creates draft records only.
- [ ] Draft conversion requires human review/approval.
- [ ] Supplier bank data from OCR remains unverified until confirmed.
- [ ] Duplicate warnings appear before approval/conversion.
- [ ] All create/update/submit/approve/reject/convert actions append audit rows.
- [ ] Historical timesheet and invoice snapshots remain unchanged.
- [ ] User-facing labels are trilingual where screens are added.
- [ ] `python3 -m py_compile backend/app.py` passes after code changes.

## Key open items for product owner

1. Final approval threshold amount.
2. Initial implementation location: TAC-timesheet vs shared MDM module.
3. OCR provider decision.
4. Uploaded document storage location.
5. Reviewer and approver role mapping.
6. Whether supplier bank data should be masked in UI for non-Finance users.
