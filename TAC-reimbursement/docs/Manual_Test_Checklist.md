# Manual Test Checklist

This checklist is for local MVP implementation verification.

## 1. Startup

1. Start the reimbursement app on the planned port `8003`.
2. Confirm `/health` returns OK.
3. Confirm dashboard loads.

## 2. Manual claim entry

1. Create a new claim manually.
2. Enter employee, claim month, expense date, category, vendor, total amount, tax amount, tax rate, and business purpose.
3. Attach receipt/invoice file.
4. Save as `Draft`.
5. Edit the draft and confirm updates are saved.
6. Submit the claim.
7. Confirm submitted claim is no longer employee-editable unless rejected/reopened.

## 3. OCR-assisted New Claim input

1. Open `/claim-new`.
2. Confirm the standard form explains that OCR is an optional input aid inside New Claim.
3. Confirm the form includes all standard fields, the receipt/invoice attachment field, the embedded `Extract from receipt/invoice` action, and local OCR guidance.
4. Confirm local OCR capability: either Tesseract/Poppler are available with `tesseract --version`, `tesseract --list-langs`, and `pdftoppm -v`, or macOS Vision fallback is available through `/usr/bin/swift`.
5. Enter at least one manual field such as vendor or employee name before OCR.
6. Upload a supported Japanese receipt image and click `Extract from receipt/invoice`.
7. Confirm attachment is saved under the project-local `attachments/` directory.
8. Confirm the system opens the same standard reimbursement form as an editable Draft claim.
9. Confirm OCR-recognized values are prefilled into editable standard claim fields, not shown as a separate final form.
10. Confirm manual values entered before OCR are preserved and not overwritten by OCR suggestions.
11. Confirm the OCR review panel compares OCR suggestions with current standard claim values and shows local OCR notes.
12. Save the incomplete OCR-assisted claim as `Draft` without selecting OCR review confirmation and confirm the standard claim fields are saved in `database/claims.json`.
13. Confirm OCR status can remain `draft` after Draft save.
14. Correct at least one prefilled claim field manually.
15. Try to submit with missing required final claim fields and confirm validation fails.
16. Fill required final claim fields that OCR cannot reliably provide, especially employee number, claim month, and business purpose.
17. Try to submit without OCR review confirmation and confirm validation fails.
18. Select the OCR review confirmation control before submit.
19. Submit the claim.
20. Confirm OCR status becomes `confirmed` on submit after employee review.
21. Confirm submitted claim is no longer employee-editable unless rejected/reopened.
22. Confirm finance approval, reports, CSV export, and payment closing use the standard claim fields and do not depend on `ocr_draft` as the final source.
23. Upload a Japanese receipt PDF and confirm OCR processes the first page or shows a clear local PDF OCR error.
24. Temporarily test a missing-tool scenario if possible and confirm `ocr_status` becomes `not_available` with manual entry still usable.
25. Confirm navigation, dashboard, and claims pages no longer show a standalone OCR Upload action.
26. Confirm direct `/claim-ocr-new` access redirects to `/claim-new`.

## 4. Validation

1. Total amount must be greater than zero.
2. Tax amount cannot be negative.
3. Tax amount cannot exceed total amount.
4. Claim month must use `YYYY-MM`.
5. Expense date must use `YYYY-MM-DD`.
6. Qualified invoice number must be `T` followed by 13 digits when present.
7. Unsupported attachment types should be rejected.

## 5. Finance approval

1. Create and submit a claim from manual entry or OCR draft flow.
2. Confirm the submitted claim is no longer employee-editable.
3. Open `/finance-review` and confirm the submitted claim appears.
4. Open the claim detail from `/finance-claim?id=<claim_id>`.
5. Approve with finance notes.
6. Confirm status becomes `Approved`, `approved_at` is populated, `approved_by` is `Finance`, and an `approve` log exists.
7. Submit another claim.
8. Try to reject without reject reason and confirm validation fails.
9. Reject with reject reason.
10. Confirm status becomes `Rejected`, `rejected_at` is populated, `rejected_by` is `Finance`, `reject_reason` is saved, and a `reject` log exists.
11. Confirm rejected claim can be edited by employee.
12. Correct and resubmit rejected claim.
13. Confirm status returns to `Submitted`, `submitted_at` refreshes, a new `submit` log exists, and the claim appears again in `/finance-review`.
14. Confirm approved claim appears in month-end report once the report feature is implemented.

## 6. Month-end report

1. Approve at least one claim for a target claim month.
2. Create or keep Draft, Submitted, Rejected, and Deleted claims and confirm they are excluded from the default report.
3. Open `/finance-report`.
4. Filter approved claims by claim month.
5. Filter by employee number, department, category, tax rate, and payment method.
6. Confirm total claim count, total amount, and total tax amount match the visible detail rows.
7. Confirm grouped totals by employee.
8. Confirm grouped totals by category.
9. Confirm grouped totals by tax rate.
10. Confirm grouped totals by payment method.
11. Export CSV from `/finance-report.csv`.
12. Confirm CSV header order matches `docs/Reporting_Plan.md`.
13. Confirm CSV uses raw integer yen values and preserves Japanese text.
14. Confirm formula-like cell values are safely prefixed.
15. Confirm export history is recorded in `database/report_exports.json` and appears on `/finance-report`.

## 7. Payment closing

1. Approve at least one claim for a target claim month.
2. Open `/finance-report?claim_month=YYYY-MM`.
3. Confirm the payment closing panel appears for approved claims.
4. Enter payment date and optional closing notes.
5. Close payment.
6. Confirm included claims become `Paid`.
7. Confirm `paid_at` is populated.
8. Confirm `mark_paid` approval logs are written for each included claim.
9. Confirm `database/payment_closings.json` contains one closing record with claim IDs, count, totals, payment date, closed_by, and closed_at.
10. Confirm `/finance-report?claim_month=YYYY-MM&approval_status=Paid` shows the paid claims.
11. Re-run close for the same claim month and confirm validation fails.
12. Try to create, edit, delete, approve, or reject claims in the payment-closed month and confirm each mutation is blocked.
13. Confirm claims in a different month still work.
14. Confirm CSV export does not mark claims paid and only writes `database/report_exports.json`.

## 8. Permission, Entity, and audit hardening

1. Confirm `/health` remains public.
2. Confirm every non-health route redirects unauthenticated users to User_admin or returns 403.
3. Confirm a user without `reimbursement.access` cannot open the module.
4. Confirm an employee with `reimbursement.submit` / `reimbursement.view_own` can see and mutate only their own editable claims.
5. Confirm employee number and Entity cannot be spoofed by form or query parameters.
6. Confirm finance approvers with `reimbursement.approve` see only current-Entity submitted claims.
7. Confirm direct access to another Entity claim, voucher, finance detail, report row, or payment close target is blocked.
8. Confirm reports and CSV export include only current-Entity rows.
9. Confirm payment close marks only current-Entity Approved claims as Paid.
10. Confirm `database/audit_logs.json` receives required audit fields for create, OCR draft, update, submit/resubmit, approve, reject, soft delete, CSV export, payment close, and mark-paid actions.
11. Confirm `/audit-logs` is visible only to System Admin, `reimbursement.audit.view`, or the temporary `reimbursement.reports.view` fallback, and is read-only.
12. Confirm `/audit-logs` rows are scoped to the current Entity for non-system users.
13. Confirm legacy records without Entity fields are visible/editable only to their matching employee owner or System Admin, and receive Entity metadata when the owner saves/resubmits.

## 9. Wi-Fi / LAN testing

1. Start Portal/User_admin with public URLs reachable from Wi-Fi clients.
2. Start Reimbursement with `--host 0.0.0.0 --port 8003` and `TACAI_PUBLIC_HOST`, `EXPENSE_PUBLIC_BASE_URL`, `PORTAL_PUBLIC_BASE_URL`, and `USER_ADMIN_PUBLIC_BASE_URL` set to the Mac LAN IP.
3. From a Wi-Fi client, open `http://<LAN_IP>:8003/health` and confirm `OK`.
4. From a Wi-Fi client, open `http://<LAN_IP>:8003/`, login through User_admin if redirected, and verify the language selector, claim pages, finance pages, reports, and audit page according to permissions.

## 10. Regression

1. Existing claim data remains valid JSON.
2. Attachment paths remain relative to the project.
3. Draft, submitted, approved, rejected, and paid claims display correctly.
