# Customer Billing Business Rules

## Language

- Japanese and English are primary invoice/request note languages.
- Chinese is available as an optional future/customer-request language.

## Qualified invoice basics

MVP records and displays:

- Company qualified invoice registration number.
- Company registration/tax number if configured.
- Customer name.
- Issue date.
- Payment due date.
- Consumption tax amount.
- Tax-included total.
- Bank account information.

## Tax

- Default tax rate is 10%.
- Supported labels: 10%, 8%, 0%, mixed, unknown.
- Money is stored as integer JPY yen.

## Customer Master

- Customer Master is maintained in TACAI Master Data, not inside Customer Billing.
- Customer Billing reads active customers from Master Data `/api/customers` and stores customer snapshots on billing records.
- Changes to Master Data Customer Master must not rewrite historical billing snapshots.
- Deactivated customers should not appear for new billing selection, but old billing records remain visible through their stored snapshots.

## Record control

- Draft billing records can be edited.
- Issued/sent billing records cannot be overwritten directly in the MVP.
- Use copy, cancel, or payment registration for post-issue activity.
- Business records and audit logs are not physically deleted.

## OCR-assisted historical invoice input

- OCR import is an assistant workflow, not automatic posting.
- OCR-confirmed records are created as normal Customer Billing `Draft` records in the MVP.
- Prior-year `issue_date` values are allowed for historical backfill.
- Original source invoice numbers are stored in `original_invoice_no`; internal `billing_no` remains the Customer Billing system number.
- Uploaded source files are retained locally under controlled OCR storage with SHA-256 hash metadata for traceability and duplicate warning.
- After OCR confirmation, the uploaded source file is also linked to the created Billing Draft as a retained `source_invoice_scan` attachment.
- Supported MVP formats are PDF, JPG/JPEG, PNG, WEBP, DOCX, DOC, RTF, TXT, MD, and Markdown, with a 10 MB limit.
- OCR must not create local Customer Master records. The user must match/select a TACAI Master Data customer before saving.
- Duplicate warnings should be shown for same source hash, same customer + original invoice number, or same customer + issue date + total amount.
- If duplicate warnings exist, finance must explicitly acknowledge them before saving the OCR-confirmed Billing Draft.
- OCR/parser warnings must be reviewed manually before saving.
- If extracted subtotal, tax, and total do not reconcile, the user must correct the line items before relying on the record.
