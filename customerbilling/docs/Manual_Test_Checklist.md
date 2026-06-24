# Customer Billing Manual Test Checklist

## Startup

- [ ] Start User_admin on port 8006.
- [ ] Start TACAI Portal on port 8005.
- [ ] Start Customer Billing on port 8009.
- [ ] Confirm `/health` returns `OK`.

## Portal

- [ ] Log in through User_admin as System Admin or Finance.
- [ ] Open TACAI Portal.
- [ ] Confirm module order: Vendor Payments, Customer Billing, InterviewReady.
- [ ] Open Customer Billing from Portal.

## Customer master

- [ ] Create a customer.
- [ ] Edit the customer.
- [ ] Confirm audit log entry.
- [ ] Soft deactivate a customer.

## Billing

- [ ] Open `New Billing` and confirm the unified creation page appears.
- [ ] Choose manual mode and create Japanese haken/dispatch billing.
- [ ] Choose manual mode and create English recruitment placement billing.
- [ ] Create RPO billing.
- [ ] Confirm tax and totals calculate.
- [ ] Issue a billing record.
- [ ] Mark a billing record as sent.
- [ ] Copy an historical billing record to a new draft.
- [ ] Confirm copied records do not inherit old OCR source scan attachments.
- [ ] Cancel a billing record.

## OCR-assisted historical invoice input

- [ ] Open `New Billing` and click `Import Previous Invoice / OCR Assist`.
- [ ] Upload a Japanese PDF invoice and confirm an OCR draft review page opens.
- [ ] Upload a scanned JPG/PNG invoice and confirm OCR failure/fallback warnings are understandable if the local OCR engine is unavailable.
- [ ] Upload a DOCX/Word invoice and confirm text extraction suggestions appear.
- [ ] Confirm uploaded file metadata, OCR status, engine, warnings, and raw text preview are visible.
- [ ] Confirm Customer Master selection is required before saving.
- [ ] Confirm original invoice number is stored separately from internal billing number.
- [ ] Confirm saving creates a normal Billing Draft linked to the OCR draft.
- [ ] Confirm the uploaded source scan/document appears on Billing Detail as a retained attachment.
- [ ] Confirm the attachment view/download link works only through the controlled billing attachment route.
- [ ] Confirm duplicate warning appears for re-uploading the same source file or same original invoice details.
- [ ] Confirm duplicate warning acknowledgement is required before saving when duplicates are detected.
- [ ] Confirm discarding an OCR draft soft-disables the draft and writes an audit log.

## Payment tracking

- [ ] Register partial payment.
- [ ] Register full payment.
- [ ] Confirm balance updates.
- [ ] Confirm status changes to Partially Paid and Paid.

## Reports and audit

- [ ] Confirm AR aging report displays balances.
- [ ] Confirm billing by business type report displays totals.
- [ ] Confirm audit page shows recent state changes.
