# Customer Billing Workflow Specification

## Scope

Customer Billing supports invoice/request note creation and accounts receivable tracking for:

- Haken / dispatch billing
- Recruitment placement billing
- RPO billing
- Other customer billing

## Billing lifecycle

1. Draft
2. Issued
3. Sent
4. Partially Paid
5. Paid
6. Cancelled

Draft records may be edited. Issued and sent records should not be overwritten directly; finance should use copy, cancel, or payment registration actions.

## Creation modes

MVP supports:

- Manual creation
- Copy from historical billing record
- OCR-assisted historical invoice input from PDF/image/Word/text source files

OCR-assisted creation flow:

1. Finance clicks `New Billing` and chooses `Create from Scan` / source document creation.
2. Finance uploads one PDF/JPG/PNG/WEBP/DOCX/DOC/RTF/TXT/MD source file or provides pasted extracted text.
3. System stores the source file under controlled local storage, hashes it, extracts text, and creates an OCR draft.
4. System suggests invoice fields, customer match, line items, totals, tax, and warnings.
5. Finance reviews/corrects all fields and must select a Customer Master record from TACAI Master Data.
6. If possible duplicate records are detected, finance must explicitly acknowledge the duplicate warning before saving.
7. Confirmation creates a normal Customer Billing `Draft` record with `source_type = ocr_import`, a link to the OCR draft, and the uploaded source scan/document retained as a billing attachment.
8. Issuing, sending, cancelling, and payment registration continue through the standard billing lifecycle actions.

Template-specific PDF generation and customer-specific templates are deferred.

## Payment tracking

Finance manually registers payments after confirming bank receipt.

Payment registration updates:

- `paid_amount`
- `balance_amount`
- `payment_status`
- billing status where appropriate

## Audit

Every create, update, issue, send, cancel, copy, payment registration, OCR upload, OCR confirmation, and OCR discard action appends an audit log. Confirmed OCR imports also append billing history on the created draft record.
