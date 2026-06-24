# OCR-Assisted Historical Invoice Input Project Plan

Last updated: 2026-06-21

## 1. Background and Goal

Customer Billing currently supports manual billing creation, historical copy, status workflow, payment registration, AR reports, and audit logs. The next operational need is to input prior-year invoices efficiently from existing source documents such as PDF invoices, JPG/PNG scanned invoices, and Word documents.

The goal is not to fully automate accounting entry. The goal is to provide an OCR-assisted input workflow that extracts likely billing fields, pre-fills the normal billing form, highlights uncertainty, requires user review, and preserves auditability.

Primary use case:

- Finance/Admin obtains prior-year invoice/request note files.
- User uploads or selects files in Customer Billing.
- OCR/document extraction reads invoice data.
- System maps extracted fields into Customer Billing draft fields.
- User reviews customer match, dates, amounts, tax, line items, and original invoice number.
- User saves a reviewed draft or imports a historical issued/sent/paid record through controlled workflow.

## 2. Expert-Dimension Planning

### 2.1 Product Expert View

#### User value

- Reduce repetitive manual entry for prior-year invoices.
- Improve speed when backfilling historical AR records.
- Reduce typing errors in invoice number, customer name, dates, total, tax, and line items.
- Keep current Customer Billing UI style and workflow familiar.

#### UX principles

- OCR should assist, not replace, user review.
- The upload entry point should be close to the existing billing creation flow.
- Users should see extracted data and original source context side-by-side when possible.
- Low-confidence fields should be visually flagged.
- Manual edits always override OCR suggestions.
- Existing manual entry remains available if OCR fails.

#### Recommended UI placement

1. Billing list page
   - Add page-level secondary action: `OCR Import` / `Import from Invoice` near `New Billing`.
   - Keep `New Billing` as the primary manual path.

2. OCR upload page
   - Route: `GET /billings/ocr/new`
   - Layout: SAP/Fiori-style page header and upload card.
   - Inputs:
     - Source file upload: PDF, JPG, JPEG, PNG, WEBP, DOCX, DOC, RTF, TXT/MD if useful.
     - Optional source language hint: Japanese / English / Auto.
     - Import mode: prior-year invoice backfill / current invoice draft.
     - Optional pasted text area for cases where OCR was performed externally.

3. OCR review page
   - Route: `GET /billings/ocr/review?id=...`
   - Left or top section: source metadata and OCR status.
   - Main section: normal billing fields prefilled from extraction.
   - Customer matching section: matched Master Data customer or manual selection required.
   - Line items section: extracted line rows with editable fields.
   - Validation section: extracted total vs recalculated total, tax mismatch warnings, duplicate warnings.
   - Toolbar actions:
     - `Save as Draft`
     - `Save as Historical Issued` if approved later
     - `Discard OCR Draft`
     - `Back to Billings`

4. Billing form integration
   - Existing manual form should support a prefill object from OCR.
   - OCR suggestions should not create final records until user saves.

#### MVP feature boundary

MVP should support:

- Single-file upload per OCR draft.
- PDF/image OCR for Japanese and English invoices.
- Word/text extraction for DOCX/DOC/RTF/TXT where possible.
- Field extraction into billing header, customer matching hints, line items, totals, tax, original invoice number.
- Manual review and save as Customer Billing draft.
- OCR source metadata and audit trail.
- Duplicate warning.

MVP should defer:

- Batch upload of many invoices.
- Automatic accounting software import.
- Cloud OCR APIs unless explicitly approved.
- Fully automatic customer creation.
- Fully automatic posting as Paid without human review.
- Customer-specific templates.

### 2.2 Architecture Expert View

#### Current architecture constraints

- Customer Billing is dependency-free Python standard-library unless dependencies are approved.
- HTML/CSS/rendering and routing are in `backend/app.py`.
- Current form parser handles URL-encoded forms only; no multipart upload support exists yet.
- Customer Master is owned by TACAI Master Data and must not be created locally.
- Audit logs are append-only.
- Money must be stored as integer JPY yen or decimal strings; no floats.

#### Reusable existing resources

Recommended reuse from existing suite resources:

1. TAC-reimbursement OCR prompt
   - `TAC-reimbursement/prompts/OCR_Receipt_Prompt.md`
   - Reuse structure: JSON-only extraction, no guessing, manual review flag, qualified invoice fields.

2. TAC-reimbursement OCR workflow/schema pattern
   - `TAC-reimbursement/docs/Workflow_Specification.md`
   - `TAC-reimbursement/docs/Data_Schema.md`
   - Reuse principle: OCR draft is advisory; final business record fields remain source of truth.

3. TAC-reimbursement local OCR implementation
   - `TAC-reimbursement/backend/app.py`
   - Reuse ideas: Tesseract/Poppler, macOS Vision fallback, OCR timeout, Unicode normalization, safe attachment paths.

4. macOS Vision fallback
   - `TAC-reimbursement/backend/macos_vision_ocr.swift`
   - Useful for local Japanese/English OCR without cloud APIs.

5. InterviewReady document loader
   - `InterviewReady/core/document_loader.py`
   - Reuse concepts for PDF/Word/text extraction, especially DOCX/DOC/RTF/TXT.

6. TAC-employeeadmin upload metadata/hash pattern
   - `TAC-employeeadmin/backend/app.py`
   - Reuse ideas: multipart parsing, SHA-256, safe storage under a fixed document root, metadata separation.

#### Recommended architecture

Use a two-layer import model:

1. OCR draft layer
   - Stores source file metadata, raw extracted text, extracted structured fields, confidence/warnings, and review status.
   - Does not count as a billing record until confirmed.

2. Billing record layer
   - Existing `customer_billings.json` remains the source of truth for confirmed billing records.
   - OCR-confirmed records are created through the same validation/calculation logic as manual billing where possible.

#### Recommended new storage

Add a dedicated OCR/import storage area:

```text
customerbilling/database/ocr_invoice_drafts.json
customerbilling/docs/ocr_uploads/            # or customerbilling/storage/ocr_uploads/ if introduced
```

Recommended OCR draft fields:

```json
{
  "ocr_draft_id": "OCR-2026-0001",
  "record_status": "active",
  "ocr_status": "uploaded | extracted | review_required | confirmed | failed | discarded",
  "source_file": {
    "original_filename": "invoice_2023_001.pdf",
    "stored_filename": "OCR-2026-0001.pdf",
    "relative_path": "docs/ocr_uploads/OCR-2026-0001.pdf",
    "content_type": "application/pdf",
    "size_bytes": 123456,
    "sha256": "...",
    "uploaded_at": "...",
    "uploaded_by": "..."
  },
  "source_document_type": "pdf | image | word | text",
  "source_language_hint": "auto | ja | en",
  "raw_text": "...",
  "extracted": {
    "original_invoice_no": "...",
    "document_type": "invoice",
    "issue_date": "2023-04-30",
    "due_date": "2023-05-31",
    "customer_name": "...",
    "customer_registration_number": "...",
    "business_type": "haken_dispatch",
    "currency": "JPY",
    "qualified_invoice_registration_number": "T...",
    "subtotal_amount": "100000",
    "tax_amount": "10000",
    "total_amount": "110000",
    "line_items": []
  },
  "customer_match": {
    "matched_customer_id": "...",
    "match_method": "exact_name | normalized_name | manual | none",
    "confidence": "high | medium | low",
    "candidate_customer_ids": []
  },
  "warnings": [],
  "duplicate_check": {
    "status": "none | possible | duplicate",
    "matched_billing_ids": []
  },
  "created_at": "...",
  "updated_at": "...",
  "confirmed_at": "...",
  "confirmed_by": "...",
  "created_billing_id": "..."
}
```

Recommended additions to confirmed billing records:

```json
{
  "source_type": "manual | copy | ocr_import",
  "source_ocr_draft_id": "OCR-2026-0001",
  "original_invoice_no": "INV-2023-001",
  "original_issue_year": "2023",
  "imported_historical": true,
  "source_file_hash": "..."
}
```

#### OCR engine strategy

Recommended phased strategy:

- Phase 1 local-first:
  - Images: Tesseract if installed; macOS Vision fallback on Mac.
  - PDFs: text extraction if embedded text exists; otherwise convert/render first page or selected pages, then OCR.
  - Word/Text: document text extraction using InterviewReady-style loader logic.

- Phase 2 optional enhancement:
  - Add user-approved dependency or external OCR provider if local OCR quality is insufficient.
  - Possible future cloud OCR should be configurable and off by default due to document privacy.

#### New backend routes

Recommended routes:

- `GET /billings/ocr/new`
  - Upload/start page.

- `POST /billings/ocr/upload`
  - Requires `client_revenue.manage`.
  - Parses upload, saves source file metadata, runs extraction or queues extraction, creates OCR draft.

- `GET /billings/ocr/review?id=OCR-...`
  - Requires `client_revenue.manage`.
  - Shows extracted fields and editable review form.

- `POST /billings/ocr/confirm`
  - Requires `client_revenue.manage`.
  - Validates reviewed fields, creates billing draft or controlled historical record, links OCR draft.

- `POST /billings/ocr/discard`
  - Requires `client_revenue.manage`.
  - Soft-discards OCR draft; does not delete audit history.

#### Security and compliance controls

- Enforce upload size limit, recommended MVP max 5 MB to 10 MB.
- Allow only approved extensions/content types.
- Generate stored filenames; never trust user filename for path.
- Store SHA-256 for duplicate/source verification.
- Resolve paths under fixed project storage root to prevent path traversal.
- Audit every OCR draft creation, extraction failure, review confirmation, discard, and billing creation.
- Do not delete OCR audit records.
- Do not create local Customer Master records.

### 2.3 Business Expert View

#### Business purpose

This feature supports historical billing backfill for Japan dispatch, recruitment placement, and RPO business. Prior-year invoices may be needed for AR visibility, payment tracking, reporting continuity, audit review, and migration from older manual files.

#### Business rules for prior-year invoices

1. Prior-year issue dates are allowed.
2. Original invoice/request note number should be preserved separately from the internal Customer Billing `billing_no`.
3. Internal `billing_no` should remain a Customer Billing system identifier unless a later decision allows historical numbering override.
4. Customer must be matched to TACAI Master Data before final save.
5. If no customer match exists, user should create or correct the Customer Master in TACAI Master Data first.
6. OCR totals must be validated against calculated line totals.
7. If tax or total mismatch exists, system should require manual confirmation or correction.
8. Duplicate warning should trigger on:
   - Same source file hash.
   - Same customer + original invoice number.
   - Same customer + issue date + total amount.
9. Historical paid invoices should not silently become paid; payment state must be explicitly reviewed.
10. If importing as Paid, the system should create a payment entry with payment date/method/reference and audit it.

#### Japan invoice considerations

- Preserve qualified invoice registration number if present.
- Extract and validate consumption tax amount/rate where possible.
- Support Japanese and English invoices first.
- Chinese can remain optional/future, consistent with Customer Billing MVP direction.
- Keep amounts in JPY integer yen; if foreign currency appears, mark for manual review unless a later currency strategy is approved.

#### Status handling recommendation

MVP default:

- OCR confirmation creates a `Draft` billing record.
- User then uses existing status actions to issue/send/cancel.

Optional controlled historical mode after MVP:

- Allow import as `Issued`, `Sent`, `Partially Paid`, or `Paid` only after explicit user selection and audit confirmation.
- If `Paid`, require payment date and amount.

This avoids accidental posting of old invoices as active receivables without review.

### 2.4 Process Expert View

#### Target workflow

1. Start import
   - User opens Billings page and clicks `OCR Import`.

2. Upload/select source
   - User uploads one prior invoice file: PDF/JPG/PNG/WEBP/DOCX/DOC/RTF/TXT.
   - User chooses language hint and import purpose.

3. Extract text
   - System extracts embedded text if available.
   - If image/scanned PDF, system runs OCR.
   - If OCR fails, keep attachment metadata and allow manual entry.

4. Structured parsing
   - System maps raw text into invoice fields:
     - original invoice number
     - customer name
     - issue date
     - due date
     - document type
     - business type if inferable
     - qualified invoice number
     - subtotal/tax/total
     - line items
     - notes/warnings

5. Customer matching
   - System compares extracted customer name/registration/address/email with Master Data customers.
   - If one strong match exists, preselect it.
   - If multiple/none, user must select manually.

6. Review and correction
   - User reviews the OCR draft in a form similar to current billing form.
   - OCR-suggested values are editable.
   - Warnings display for low confidence, missing fields, tax mismatch, duplicate risk.

7. Confirm/save
   - MVP: user saves as Draft.
   - Future historical mode: user may save with reviewed historical status.

8. Audit and traceability
   - OCR draft remains linked to the billing record.
   - Audit logs record upload, extraction, confirmation, and billing creation.

#### Exception paths

- OCR unavailable:
  - Show message: OCR engine not available; continue with manual entry.

- Unsupported file:
  - Reject with clear supported formats.

- Duplicate warning:
  - Let user open possible existing record, discard OCR draft, or continue with explicit confirmation.

- Customer not found:
  - Prompt user to maintain Customer Master in TACAI Master Data, then return.

- More than current line-item capacity:
  - MVP should either expand line item handling or warn and summarize lines.
  - Recommended: implement dynamic line item handling before production OCR import.

## 3. Phased Delivery Plan

### Phase 0 — Decision and design finalization

Deliverables:

- Confirm local OCR vs dependency/cloud strategy.
- Confirm file retention policy.
- Confirm whether MVP saves OCR imports only as Draft.
- Confirm original invoice number storage rule.
- Confirm max file size and supported formats.

Recommended decisions:

- Local-first OCR and document text extraction.
- Store source files locally under a controlled folder.
- MVP creates Draft only.
- Preserve original invoice number in `original_invoice_no`.
- Support PDF/JPG/JPEG/PNG/WEBP/DOCX/DOC/RTF/TXT initially.

### Phase 1 — OCR/import planning docs and schema docs

Deliverables:

- Update `docs/Workflow_Specification.md` with OCR-assisted creation mode.
- Update `docs/Data_Schema.md` with OCR draft schema and billing source metadata.
- Update `docs/Business_Rules.md` with prior-year invoice rules.
- Update `docs/Manual_Test_Checklist.md` with OCR test cases.
- Update memory decisions after approval.

### Phase 2 — Upload and OCR draft foundation

Deliverables:

- Add upload route and safe storage.
- Add `ocr_invoice_drafts.json` helpers.
- Add OCR draft list/review route skeleton.
- Add audit logging for upload/draft creation/discard.
- Add duplicate detection based on source hash and original invoice fields.

### Phase 3 — Extraction engine MVP

Deliverables:

- Reuse/adapt TAC-reimbursement OCR logic for image/PDF.
- Reuse/adapt InterviewReady document text extraction for Word/text formats.
- Normalize text with Japanese/English-friendly handling.
- Implement invoice field parser for Customer Billing:
  - customer name
  - original invoice number
  - issue date/due date
  - tax registration number
  - subtotal/tax/total
  - line items
- Add parser warnings and confidence indicators.

### Phase 4 — Review UI and billing prefill

Deliverables:

- Add OCR review page aligned with current Customer Billing/Timesheet UI.
- Add customer matching against Master Data.
- Prefill billing form sections from OCR draft.
- Add total/tax validation warnings.
- Add save-as-draft confirmation path.

### Phase 5 — Historical import controls

Deliverables:

- Add optional historical import mode after Draft MVP is stable.
- Allow controlled status selection only with explicit confirmation.
- If importing paid invoices, require reviewed payment entry.
- Audit status/payment creation.

### Phase 6 — Manual testing and operational hardening

Deliverables:

- Test Japanese PDF invoice with embedded text.
- Test scanned JPG invoice.
- Test English PDF invoice.
- Test Word invoice.
- Test OCR failure fallback.
- Test duplicate warning.
- Test no customer match.
- Test permission failures.
- Test audit log entries.
- Test mobile/narrow screen review page.

## 4. Recommended MVP Acceptance Criteria

MVP is acceptable when:

- Finance/Admin can upload one historical invoice file.
- System extracts text or gracefully fails with manual fallback.
- System creates an OCR draft with source metadata and audit log.
- Review page shows extracted data, warnings, and editable billing fields.
- Customer must be selected from Master Data before saving.
- User can save reviewed OCR draft into a normal Customer Billing Draft.
- Billing record stores `source_type = ocr_import`, `source_ocr_draft_id`, `original_invoice_no`, and prior-year issue date.
- Duplicate warnings are shown before save.
- Python syntax and health checks pass.
- Existing manual billing flow still works.

## 5. Open Decisions for User Approval

1. Should MVP create OCR imports as `Draft` only, or allow direct historical `Issued/Paid` import?
2. Should uploaded source files be retained locally for audit, or only extracted text/metadata retained?
3. Is local OCR acceptable initially, or should cloud/LLM OCR be considered after approval?
4. What max file size should be allowed: 5 MB, 10 MB, or higher?
5. Should line-item handling be expanded dynamically before OCR import implementation?

## 6. Recommended Next Step

Recommended next action is Phase 0/1:

- Review and approve the five open decisions.
- Then update Customer Billing workflow/schema/business-rule/test docs.
- After documentation approval, implement upload + OCR draft foundation before extraction quality improvements.
