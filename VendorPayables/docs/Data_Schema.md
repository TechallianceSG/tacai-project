# Data Schema

All MVP storage is UTF-8 JSON arrays under `database/`.

## 1. `database/vendor_payables.json`

Stores supplier invoice/payment request records.

| Field | Description |
|---|---|
| `payable_id` | System-generated internal ID. |
| `payable_no` | Human-readable payable number, e.g. `VP-2026-0001`. |
| `status` | `Draft`, `Submitted`, `Approved`, `Scheduled`, `Paid`, `Rejected`, or `Cancelled`. |
| `supplier_record_mode` | `standard_vendor` for recurring/normal suppliers, or `one_time_vendor` for temporary suppliers using the shared ONETIME code. |
| `vendor_id` | Related vendor master ID. Required for `standard_vendor`; optional for `one_time_vendor` when the virtual ONETIME snapshot is used. |
| `vendor_code_snapshot` | Vendor code copied from Master Data Management at payable creation/update time, or `ONETIME` for one-time supplier payments. |
| `vendor_name_snapshot` | Vendor name copied from Master Data Management at payable creation/update time, or One-time Vendor label. |
| `qualified_invoice_number_snapshot` | Qualified invoice number copied from Master Data Management. |
| `payment_terms_snapshot` | Payment terms copied from Master Data Management. |
| `request_title` | Short title or description of the payment request. |
| `business_purpose` | Business purpose / reason. |
| `invoice_number` | Supplier invoice/request number. |
| `invoice_date` | Invoice issue date, `YYYY-MM-DD`. |
| `received_date` | Date finance received the invoice/request, `YYYY-MM-DD`. |
| `payment_due_date` | Required payment due date, `YYYY-MM-DD`. |
| `actual_payment_date` | Actual payment date, `YYYY-MM-DD`, required when status is `Paid`. |
| `currency` | Default `JPY`. |
| `amount_excluding_tax` | Amount before consumption tax. Store as integer yen or decimal string. |
| `tax_rate` | `10%`, `8%`, `0%`, `mixed`, or `unknown`. |
| `tax_amount` | Consumption tax amount. |
| `total_amount` | Total amount including tax. |
| `withholding_tax_amount` | Withholding tax amount, normally `0` for company vendors. |
| `payment_method` | Bank transfer, card, cash, other. |
| `expense_category` | Recruitment media, outsourcing cost, SaaS, professional service, admin, other. |
| `related_client_name` | Optional related client name. |
| `related_project_name` | Optional related project name. |
| `department` | Internal department or cost center. |
| `qualified_invoice_number` | Japanese qualified invoice issuer registration number on the payable. |
| `one_time_vendor_name` | Actual supplier name for one-time supplier payments. Required when `supplier_record_mode` is `one_time_vendor`. |
| `one_time_vendor_address` | Actual supplier address for one-time supplier payments, if available. |
| `one_time_qualified_invoice_number` | Qualified invoice number for the actual one-time supplier, if available. |
| `one_time_bank_account_text` | Reviewed bank account text for one-time supplier payments. |
| `one_time_reason` | Reason code for using one-time supplier mode. |
| `one_time_reviewed` | Boolean confirmation that one-time supplier identity/payment details were reviewed. |
| `attachment` | Attachment metadata object or `null`. |
| `ocr_status` | `not_run`, `draft`, `confirmed`, `failed`, or `not_available`. |
| `ocr_draft` | OCR/AI extracted draft values for reference only. |
| `approval_notes` | Approval notes. |
| `finance_notes` | Finance notes. |
| `created_by` | User label. |
| `created_at` | UTC ISO datetime. |
| `updated_at` | UTC ISO datetime. |
| `submitted_at` | UTC ISO datetime. |
| `approved_by` | Approver label. |
| `approved_at` | UTC ISO datetime. |
| `scheduled_at` | UTC ISO datetime. |
| `paid_by` | Payment marker label. |
| `paid_at` | UTC ISO datetime. |
| `cancelled_at` | UTC ISO datetime. |
| `cancel_reason` | Cancel reason. |
| `record_status` | `Active` or `Deleted`. |

## 2. Attachment object

```json
{
  "original_filename": "invoice.pdf",
  "stored_filename": "VP-2026-0001-invoice.pdf",
  "relative_path": "attachments/VP-2026-0001-invoice.pdf",
  "content_type": "application/pdf",
  "size_bytes": 123456,
  "uploaded_at": "2026-06-21T00:00:00+00:00"
}
```

## 3. Vendor Master source

Vendor Master is no longer stored as an active local VendorPayables master table. The source of truth is:

```text
TACAI-Core/masterdata/database/vendors.json
```

The former local file has been deprecated as:

```text
database/vendors.deprecated.json
```

VendorPayables should read active vendors from Master Data Management and write only payable-time snapshots into `vendor_payables.json`. Historical payment records must not be overwritten when Vendor Master changes.

## 4. `database/audit_logs.json`

Append-only audit logs.

| Field | Description |
|---|---|
| `audit_id` | System-generated audit ID. |
| `module` | Module name, e.g. `vendor_payables`. |
| `record_id` | Related record ID. |
| `action` | Create, update, submit, approve, reject, schedule, pay, cancel, export, upload. |
| `user` | Actor label. |
| `timestamp` | UTC ISO datetime. |
| `before_value` | Before value object or `null`. |
| `after_value` | After value object or `null`. |

## 5. `database/report_exports.json`

Stores CSV export history.

| Field | Description |
|---|---|
| `export_id` | System-generated export ID. |
| `report_type` | Report type, e.g. `vendor_payables_csv`. |
| `file_name` | Download file name. |
| `filter_json` | Export filter criteria. |
| `row_count` | Number of exported rows. |
| `total_amount` | Total exported payable amount. |
| `created_by` | Exporting user label. |
| `created_at` | UTC ISO datetime. |
