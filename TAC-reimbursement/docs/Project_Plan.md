# TAC-reimbursement Project Plan

## 1. Project goal

Build a standalone Japan employee reimbursement self-service system. Employees upload receipt/invoice images or PDFs, confirm extracted reimbursement data, submit claims, and finance performs one-level approval. At month end, finance exports reports for payroll and salary payment calculation.

This system is separate from TACAI-PRJ. TACAI-PRJ may later consume approved reimbursement totals, but the reimbursement workflow itself should live here.

## 2. MVP principles

1. Local-first MVP.
2. No production authentication in the first step unless explicitly requested.
3. Receipt/invoice OCR output is always a draft and must be confirmed by the employee.
4. Manual entry must remain available even when OCR fails.
5. Finance approval is one-level only in MVP.
6. Month-end report should support payroll calculation and payment preparation.
7. Keep money safe: no floating-point calculations for yen amounts.

## 3. Main users

| User | Main responsibility |
|---|---|
| Employee | Upload receipt/invoice, review OCR fields, submit reimbursement claim. |
| Finance reviewer | Check claim, approve/reject, add finance notes. |
| Payroll/finance admin | Export approved monthly report for salary/payment processing. |
| Admin, later phase | Manage users, roles, master data, system settings. |

## 4. Phase plan

### Phase 0 — Planning and skeleton

Status: done.

Deliverables:

- Project directory.
- README and CLAUDE guidance.
- Initial data schema plan.
- Workflow plan.
- OCR prompt draft.
- Report plan.

### Phase 1 — Manual claim entry MVP

Status: implemented.

Goal: allow employees/admins to create reimbursement claims manually and attach receipt files.

Tasks:

1. Build local web app shell.
2. Add claim list page.
3. Add claim create/edit page.
4. Add attachment upload placeholder/storage.
5. Store claims in `database/claims.json`.
6. Validate required fields and money fields.
7. Support draft and submit actions.

Suggested local port:

```text
8003
```

### Phase 2 — Embedded OCR input in New Claim

Goal: let employees use OCR from inside the standard `New Claim / 経費申請` form. The employee uploads a receipt/invoice attachment in the same form, runs OCR or local mock extraction, receives extracted values in the original manual fields, then reviews/corrects before final submission.

Tasks:

1. Add OCR extraction action inside the standard New Claim form.
2. Store the uploaded receipt/invoice under `attachments/` and use it as the same claim attachment.
3. Add OCR result draft structure as reference/audit metadata only.
4. Map OCR draft values into blank standard claim fields as editable defaults while preserving manual input.
5. Add prompt-based extraction spec.
6. Mark extracted fields as low/medium/high confidence if available.
7. Require employee confirmation before submission when OCR was used.
8. Remove the standalone OCR upload entry from navigation and user workflows.

Implementation note:

- If no OCR provider is selected, start with a mock/manual OCR draft workflow.
- Real OCR provider/API selection should be approved separately.

### Phase 3 — Finance approval workflow

Goal: finance performs one-level review.

Tasks:

1. Add statuses: `Draft`, `Submitted`, `Approved`, `Rejected`, `Paid`.
2. Add submit action for employees.
3. Add approve/reject action for finance.
4. Add finance notes and reject reason.
5. Add approval log records in `database/approval_logs.json`.
6. Block edits after approval unless reopened by finance.

### Phase 4 — Month-end report

Goal: export approved reimbursement data for payroll/salary payment calculation.

Tasks:

1. Add monthly report filter by claim month/payment month.
2. Add summary by employee.
3. Add summary by expense category and tax rate.
4. Add CSV export.
5. Store export history in `database/report_exports.json`.

### Phase 5 — Integration and hardening

Goal: prepare for real operation.

Later tasks:

1. Login and roles.
2. Employee master import/sync.
3. Payroll system export mapping.
4. Real OCR provider integration.
5. Attachment security and retention policy.
6. Audit log hardening.
7. Production database.
8. Backup and restore.

## 5. Recommended first implementation sequence

1. Confirm fields and approval rules.
2. Implement local web app shell.
3. Implement manual reimbursement claim CRUD.
4. Implement attachment storage.
5. Implement draft/submit workflow.
6. Implement OCR draft flow.
7. Implement finance approval.
8. Implement monthly CSV report.

## 6. Open decisions

1. Should employee master be maintained inside this app or imported from TACAI-PRJ later?
2. Which OCR provider should be used, if any?
3. Should approved reimbursements be paid through payroll or as separate bank transfer?
4. Should month-end reports include only `Approved` claims or only `Paid` claims?
5. Should tax handling follow Japanese qualified invoice rules strictly in MVP?
6. Which attachment file types and max size should be allowed?
