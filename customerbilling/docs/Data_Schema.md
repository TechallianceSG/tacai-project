# Customer Billing Data Schema

## `database/customer_billings.json`

JSON array of invoice/request note records.

Key fields:

- `billing_id`
- `billing_no`
- `record_status`
- `status`: `Draft`, `Issued`, `Sent`, `Partially Paid`, `Paid`, `Cancelled`
- `document_type`: `invoice`, `request_note`
- `language`: `ja`, `en`, `zh`
- `business_type`: `haken_dispatch`, `recruitment_placement`, `rpo`, `other`
- `customer_id`
- `customer_snapshot`
- `customer_name_snapshot`
- `issue_date`
- `due_date`
- `service_period_from`
- `service_period_to`
- `line_items`
- `subtotal_amount`
- `tax_amount`
- `total_amount`
- `paid_amount`
- `balance_amount`
- `payment_status`
- `payments`
- `company_profile_snapshot`
- `bank_info_snapshot`
- `qualified_invoice_registration_number`
- `history`
- `source_type`: `manual`, `copy`, `ocr_import`
- `source_ocr_draft_id`
- `source_file_hash`
- `original_invoice_no`
- `original_issue_year`
- `imported_historical`
- `attachments`: retained source/supporting files linked to the billing record

Money values are integer JPY yen.

### Billing `attachments`

Confirmed OCR-created billing records retain the uploaded source scan/document as a billing attachment. Manual records use an empty array unless attachments are added later.

Attachment fields:

- `attachment_id`: billing-local ID such as `ATT-001`
- `attachment_type`: `source_invoice_scan`
- `source`: `ocr_import`
- `original_filename`
- `stored_filename`
- `relative_path`: controlled path under `storage/ocr_uploads/`
- `content_type`
- `size_bytes`
- `sha256`
- `uploaded_at`
- `uploaded_by`
- `linked_from_ocr_draft_id`
- `linked_at`

Attachment file serving must resolve `relative_path` under the controlled OCR upload folder and must never accept a raw filesystem path from the browser.

## `database/ocr_invoice_drafts.json`

JSON array of OCR-assisted invoice import draft records. OCR drafts are review records only; confirmed billing records remain in `database/customer_billings.json`.

Key fields:

- `ocr_draft_id`
- `record_status`: `Active` or `Inactive`
- `ocr_status`: `review_required`, `confirmed`, `discarded`, `failed`
- `source_file`
  - `original_filename`
  - `stored_filename`
  - `relative_path`
  - `content_type`
  - `size_bytes`
  - `sha256`
  - `uploaded_at`
  - `uploaded_by`
- `source_document_type`: `pdf`, `jpg`, `jpeg`, `png`, `webp`, `docx`, `doc`, `rtf`, `txt`, `md`, `markdown`
- `source_language_hint`: `auto`, `ja`, `en`
- `import_mode`: `historical_backfill`, `current_draft`
- `raw_text`
- `ocr_engine`: `pdftotext`, `tesseract`, `macos_vision`, `docx_xml`, `textutil`, `text_decode`, `pasted_text`, `not_available`
- `extracted`: OCR/parser suggestions for invoice number, dates, customer name, currency, totals, tax, and line items
- `customer_match`: Master Data customer matching result and candidate IDs
- `duplicate_check`: possible matched billing IDs by file hash, original invoice number, or customer/date/total
- `warnings`
- `confirmed_at`
- `confirmed_by`
- `created_billing_id`
- `created_at`, `created_by`, `updated_at`, `updated_by`

Uploaded source files are stored under `storage/ocr_uploads/` with generated filenames. File paths must remain inside this controlled storage folder.

## Customer Master source

Active Customer Master records are owned by TACAI Master Data:

```text
TACAI-Core/masterdata/database/customers.json
```

Customer Billing reads them through Master Data APIs:

```text
GET http://127.0.0.1:8007/api/customers
GET http://127.0.0.1:8007/api/customers/<customer_id>
```

`database/customers.json` in this module is retained only as a legacy/migration source and is no longer authoritative.

Customer fields consumed by Customer Billing:

- `customer_id`
- `customer_code`
- `customer_name`
- `customer_name_en`
- `customer_name_zh`
- `customer_registration_number`
- `billing_address`
- `billing_contact_name`
- `billing_contact_email`
- `default_language`
- `default_payment_terms_days`
- `default_tax_rate`
- `business_types`
- `status`

## `database/company_profile.json`

Issuer-side company profile used for qualified invoice and bank snapshots.

Key fields:

- `company_name_ja`
- `company_name_en`
- `company_registration_number`
- `qualified_invoice_registration_number`
- `address_ja`
- `address_en`
- `bank_name`
- `bank_branch`
- `bank_account_type`
- `bank_account_number`
- `bank_account_name`
- `default_tax_rate`
- `default_payment_terms_days`

## `database/audit_logs.json`

Append-only audit log array with project-standard fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`
