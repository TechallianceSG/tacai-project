# Data Schema

All MVP storage is planned as UTF-8 JSON arrays.

## 1. `database/claims.json`

`database/claims.json` is the only final reimbursement claim table for the MVP. Manual entry and OCR-assisted entry must both save into the same claim fields. OCR must not create a separate final business table or a separate final field set.

Planned claim fields:

| Field | Description |
|---|---|
| `claim_id` | System-generated ID. |
| `claim_no` | Human-readable claim number, e.g. `R-2026-0001`. |
| `status` | `Draft`, `Submitted`, `Approved`, `Rejected`, or `Paid`. |
| `employee_no` | Employee number. |
| `employee_name` | Employee name at submission time. |
| `department` | Department at submission time. |
| `entity_id` | Current User_admin Entity ID snapshot. New claims are scoped by this field. |
| `entity_code` | Current User_admin Entity code snapshot. |
| `entity_name` | Current User_admin Entity name snapshot. |
| `claim_month` | Target reimbursement month, `YYYY-MM`. |
| `expense_date` | Expense date, `YYYY-MM-DD`. |
| `category` | Expense category. |
| `vendor_name` | Store/vendor name. |
| `invoice_or_receipt_number` | Receipt/invoice number. |
| `qualified_invoice_number` | Japanese qualified invoice registration number, if present. |
| `is_qualified_invoice` | `yes`, `no`, or `unknown`. |
| `currency` | Default `JPY`. |
| `total_amount` | Total amount including tax, integer yen or decimal string if needed later. |
| `amount_excluding_tax` | Amount before consumption tax, stored separately for payroll/accounting checks. |
| `tax_amount` | Consumption tax amount. |
| `tax_rate` | `10%`, `8%`, `0%`, `mixed`, or `unknown`. |
| `payment_method` | Employee paid, company card, bank transfer, etc. |
| `business_purpose` | Business reason for reimbursement. |
| `notes` | Employee notes. |
| `finance_notes` | Finance reviewer notes saved during approve/reject. Preserved for employee correction context. |
| `reject_reason` | Required when rejected. Preserved while employee corrects and resubmits unless a later approval clears it. |
| `attachment` | Receipt/invoice attachment metadata. |
| `ocr_status` | `not_run`, `draft`, `confirmed`, `failed`, or `not_available`. `draft` means OCR-prefilled values still need employee review; `confirmed` means the employee reviewed/corrected the standard claim form. |
| `ocr_draft` | Extracted OCR draft fields retained as reference/audit metadata only. These values are not the final reimbursement fields; final values are the standard claim fields saved after employee review. |
| `submitted_at` | UTC ISO datetime. |
| `approved_at` | UTC ISO datetime. |
| `approved_by` | Finance reviewer label/user ID. |
| `rejected_at` | UTC ISO datetime. |
| `rejected_by` | Finance reviewer label/user ID. |
| `paid_at` | UTC ISO datetime when the claim is marked `Paid` by payment closing. |
| `record_status` | `Active` or `Deleted` for soft delete. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |

## 2. Attachment object

```json
{
  "original_filename": "receipt.jpg",
  "stored_filename": "claim-id-receipt.jpg",
  "relative_path": "attachments/claim-id-receipt.jpg",
  "content_type": "image/jpeg",
  "size_bytes": 123456,
  "uploaded_at": "2026-06-15T00:00:00+00:00"
}
```

## 3. OCR draft object

OCR draft values are review aids only. They may be `null` when unavailable or unclear. `requires_manual_review` remains `true`; `ocr_status = confirmed` records employee review/correction of the standard claim form, not guaranteed OCR accuracy.

OCR draft fields should be mapped into editable standard claim fields for employee review. After the employee saves or submits, payroll/reporting/approval workflows must use the standard claim fields, not `ocr_draft`, as the final source of truth.

Employee/claim context entered on the OCR upload page, such as `employee_no`, `employee_name`, `department`, `claim_month`, `business_purpose`, and `notes`, is stored directly in the standard claim fields above. These values are not part of `ocr_draft` because they are employee-provided final-field context rather than extracted receipt/invoice data.

```json
{
  "receipt_date": "YYYY-MM-DD or null",
  "vendor_name": "string or null",
  "vendor_address": "string or null",
  "invoice_or_receipt_number": "string or null",
  "qualified_invoice_number": "string or null",
  "currency": "JPY",
  "total_amount": 0,
  "amount_excluding_tax": 0,
  "tax_amount": 0,
  "tax_rate": "10% | 8% | 0% | mixed | unknown | null",
  "payment_method": "string or null",
  "expense_category": "transportation | client_visit | meal | office_expense | communication | accommodation | other | unknown",
  "employee_name_if_present": "string or null",
  "confidence_notes": ["string"],
  "requires_manual_review": true
}
```

## 4. `database/employees.json`

Initial employee master fields:

| Field | Description |
|---|---|
| `employee_id` | System-generated ID. |
| `employee_no` | Employee number. |
| `employee_name` | Employee name. |
| `department` | Department. |
| `email` | Email. |
| `active_status` | `Active` or `Inactive`. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |

## 5. `database/approval_logs.json`

Approval logs are retained as workflow history for claim detail pages. The standard immutable audit source is `database/audit_logs.json` below.

Approval log fields:

| Field | Description |
|---|---|
| `log_id` | System-generated ID. |
| `claim_id` | Related claim. |
| `claim_no` | Optional snapshot of human-readable claim number for audit readability. |
| `action` | `submit`, `approve`, `reject`, `mark_paid`, etc. |
| `actor` | User label or user ID. |
| `action_at` | UTC ISO datetime. |
| `before_status` | Previous status. |
| `after_status` | New status. |
| `notes` | Optional action note. |

## 6. `database/report_exports.json`

Export history fields. `filter_json` is stored as a JSON object inside the local JSON array so filters can be inspected without parsing a string:

| Field | Description |
|---|---|
| `export_id` | System-generated ID. |
| `report_month` | Target month. |
| `report_type` | `payroll_reimbursement_csv`, etc. |
| `file_name` | Export file name. |
| `filter_json` | Export filter criteria. |
| `row_count` | Number of exported rows. |
| `total_amount` | Total exported amount. |
| `created_by` | Exporting user label/user ID. |
| `created_at` | UTC ISO datetime. |
| `entity_id` | User_admin Entity ID snapshot for the export. |
| `entity_code` | User_admin Entity code snapshot for the export. |
| `entity_name` | User_admin Entity name snapshot for the export. |

## 7. `database/payment_closings.json`

Payment closing batch records. CSV export history remains separate in `report_exports.json`; payment closing marks approved claims as paid and locks the claim month from further mutation.

| Field | Description |
|---|---|
| `closing_id` | System-generated payment closing ID. |
| `claim_month` | Closed reimbursement month, `YYYY-MM`. |
| `payment_date` | Business payment date, `YYYY-MM-DD`. |
| `notes` | Optional finance closing note. |
| `claim_ids` | Claim IDs included in the payment close. |
| `claim_count` | Number of included claims. |
| `total_amount` | Total paid amount. |
| `total_tax_amount` | Total tax amount included in the paid claims. |
| `closed_by` | Closing actor label/user ID. |
| `closed_at` | UTC ISO datetime when the system marked claims paid. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |
| `entity_id` | User_admin Entity ID snapshot for the payment closing batch. |
| `entity_code` | User_admin Entity code snapshot for the payment closing batch. |
| `entity_name` | User_admin Entity name snapshot for the payment closing batch. |

## 8. `database/audit_logs.json`

Standard audit logs are append-only and read-only. They are the compliance audit source for Reimbursement business mutations. `approval_logs.json` remains workflow history for the claim detail UI.

Required fields:

| Field | Description |
|---|---|
| `module` | Business module name, e.g. `reimbursement.claim`, `reimbursement.report_export`, or `reimbursement.payment_closing`. |
| `record_id` | Source business record ID. |
| `action` | Business action such as `create_draft`, `create_ocr_draft`, `submit`, `resubmit`, `update_draft`, `approve`, `reject`, `soft_delete`, `export_csv`, `create_payment_closing`, or `mark_paid`. |
| `user` | User_admin actor label when available. |
| `timestamp` | UTC ISO datetime. |
| `before_value` | Snapshot before mutation, or `{}` for create actions. |
| `after_value` | Snapshot after mutation, or `{}` if not applicable. |

Additional fields:

| Field | Description |
|---|---|
| `audit_id` | System-generated audit row ID. |
| `entity_id` | User_admin Entity ID snapshot. |
| `entity_code` | User_admin Entity code snapshot. |
| `entity_name` | User_admin Entity name snapshot. |

The `/audit-logs` page is read-only, filterable, and scoped to the current User_admin Entity for non-system users.
