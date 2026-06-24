# Workflow Specification

## 1. Claim status model

| Status | Meaning | Editable by employee? | Finance action |
|---|---|---:|---|
| `Draft` | Claim is being prepared. | Yes | None |
| `Submitted` | Employee submitted claim for review. | No | Approve or reject |
| `Approved` | Finance approved claim for month-end report/payment. | No | Mark paid later |
| `Rejected` | Finance rejected claim and asks for correction. | Yes | None until resubmitted |
| `Paid` | Claim has been included in payment/payroll process. | No | Reference only |

## 2. Employee self-service flow

### Preferred OCR-assisted path

OCR-assisted input is not a separate reimbursement table or a separate final form. OCR is only a prefill step for the same standard reimbursement claim form used by manual entry.

1. Employee opens reimbursement self-service.
2. Employee opens `/claim-new`, the standard New Claim / 経費申請 form.
3. Employee may enter standard claim fields manually before OCR extraction; manual values already entered by the employee should be preserved.
4. Employee chooses a receipt/invoice image or PDF in the standard attachment field.
5. Employee clicks `Extract from receipt/invoice / 領収書・請求書から読み取る` inside the New Claim form.
6. System stores the attachment under this project and creates an editable Draft claim for the same standard form.
7. System runs local OCR. Tesseract/Poppler are used when installed; on macOS, if those tools are unavailable, the app falls back to Apple's local Vision OCR for image files and first-page PDFs. If local OCR fails, the attachment remains saved and the employee continues manual entry.
8. System maps recognized OCR values into blank standard claim fields as editable defaults while preserving non-empty manual input:
   - receipt date → `expense_date`
   - vendor → `vendor_name`
   - invoice/receipt number → `invoice_or_receipt_number`
   - qualified invoice registration number → `qualified_invoice_number`
   - tax rate → `tax_rate`
   - tax amount → `tax_amount`
   - amount excluding tax → `amount_excluding_tax`
   - total amount → `total_amount`
   - category → `category`
   - payment method → `payment_method`
   - employee name if present → `employee_name`
9. Employee stays in the same standard reimbursement form and compares OCR suggestions with current standard claim values.
10. Employee reviews and corrects prefilled OCR values.
11. Employee completes fields that OCR cannot reliably provide, especially employee number, department, claim month, and business purpose.
12. Employee may save as `Draft` without confirming OCR review; `ocr_status` can remain `draft` while work is incomplete.
13. Before submitting as `Submitted`, employee must confirm OCR review/correction when `ocr_status = draft`; `ocr_status` becomes `confirmed` on submit.
14. If OCR status is `failed` or `not_available`, the employee may manually complete all required fields and submit without OCR review confirmation.
15. The final saved claim fields are the employee-confirmed values in `database/claims.json`; `ocr_draft` remains reference/audit metadata only.

### Manual entry path

Manual entry uses the same `/claim-new` form without pressing the OCR extraction action.

1. Employee opens the New Claim form.
2. Employee enters required fields manually.
3. Employee attaches receipt/invoice file.
4. Employee saves as `Draft` or submits as `Submitted`.

## 3. Finance approval flow

1. Finance opens `/finance-review` to see submitted claims by default.
2. Finance opens `/finance-claim?id=<claim_id>` and checks employee, amount, receipt/invoice attachment, tax fields, OCR status, and business purpose.
3. Finance chooses:
   - Approve → `Submitted` becomes `Approved`, `approved_at` and `approved_by` are set, and finance notes are saved.
   - Reject → `Submitted` becomes `Rejected`, `rejected_at` and `rejected_by` are set, and reject reason is required.
4. Approval logs are written for submit, approve, and reject events in `database/approval_logs.json`.
5. Employee can edit rejected claims and resubmit them; resubmission refreshes `submitted_at` and returns the claim to the finance queue.

## 4. Month-end report flow

1. Finance opens `/finance-report` and selects target filters such as claim month, employee, department, category, tax rate, and payment method.
2. System lists approved active claims by default for the selected criteria.
3. System groups totals by:
   - employee
   - category
   - tax rate
   - payment method
4. Finance exports CSV from `/finance-report.csv` for payroll/payment calculation.
5. Export history is stored in `database/report_exports.json` when CSV is downloaded.
6. CSV export does not mark claims as paid; payment closing is a separate finance action.

## 5. Payment closing flow

1. Finance filters approved claims by claim month on `/finance-report`.
2. Finance confirms payment date and optional closing notes.
3. System creates a payment closing record in `database/payment_closings.json`.
4. System marks the included approved claims as `Paid` and sets `paid_at` to the UTC system event timestamp.
5. System writes `mark_paid` approval logs for each included claim.
6. The first payment close for a claim month locks that month from later claim create/edit/delete/approve/reject changes.

## 6. Validation rules

### Submitted required claim fields

`Submitted` claims must be complete and require:

- employee number
- employee name
- claim month
- expense date
- category
- total amount greater than zero
- currency
- business purpose
- receipt/invoice attachment
- OCR review confirmation when `ocr_status = draft`

`Draft` claims may be incomplete. Draft validation only checks fields that are present, so employees can save OCR-assisted work-in-progress before all required submission fields are known.

### Money rules

- JPY amounts should be whole yen.
- Tax amount cannot be negative.
- Tax amount cannot exceed total amount.
- Total amount must be greater than zero.

### Date rules

- expense date uses `YYYY-MM-DD`.
- claim month uses `YYYY-MM`.

### Japanese invoice/tax rules for MVP

- Tax rate options: `10%`, `8%`, `0%`, `mixed`, `unknown`.
- Qualified invoice registration number format should be validated when present: `T` followed by 13 digits.
- OCR extraction should not guess missing values.

## 7. Attachment rules

Initial allowed file types:

- `.jpg`
- `.jpeg`
- `.png`
- `.pdf`
- `.webp`

Suggested max size:

```text
5 MB per attachment
```

## 8. Audit events

At minimum, log:

- claim created
- claim updated
- attachment uploaded
- claim submitted — implemented as `submit` approval log for Submitted claims
- claim approved — implemented as `approve` approval log
- claim rejected — implemented as `reject` approval log with reject reason
- claim marked paid — implemented as `mark_paid` approval log during payment closing
- monthly report exported
