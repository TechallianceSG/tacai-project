# OCR Master Data Draft Workflow

## Purpose

This workflow defines how OCR should assist supplier and customer master data creation without directly changing formal master records.

The key principle is:

> OCR creates a draft. A human reviews, resolves duplicates, approves, and converts the draft into formal master data.

## Scope

In scope:

- Supplier invoice, receipt, quotation, and contract OCR for supplier draft creation.
- Previously issued customer invoice OCR for customer draft creation.
- Raw OCR text and extracted JSON preservation.
- Human review and approval.
- Duplicate candidate warnings.
- Audit logging for import, review, approval, rejection, and conversion.

Out of scope for first MVP unless separately approved:

- Fully automatic supplier/customer creation.
- Automatic payment bank master activation.
- External OCR service integration without approval.
- Automatic legal/tax registration verification.
- Automatic merge of duplicate master records.

## OCR sources

| Draft type | Source document | Purpose |
|---|---|---|
| Supplier draft | Supplier invoice | Extract supplier identity, tax, address, bank, payment terms. |
| Supplier draft | Receipt | Extract low-volume supplier name and invoice/receipt evidence. |
| Supplier draft | Quotation/contract | Extract onboarding information before invoice arrives. |
| Customer draft | Previously issued invoice | Recover customer name, billing title, address, payment terms. |
| Customer draft | Contract/order | Extract long-term customer details. |

## Supplier OCR fields

| Field | Notes |
|---|---|
| Supplier name | Required before draft submission. |
| Supplier address | Optional but useful for duplicate checks. |
| Phone/email | Optional. |
| Invoice number | Useful for document reference. |
| Invoice date | Useful for document reference. |
| Japan invoice registration number | `T` + 13 digits if present. |
| Corporate number | Optional. |
| Bank name | Requires human review. |
| Bank branch | Requires human review. |
| Account type | Requires human review. |
| Account number | Requires human review. |
| Account holder | Requires human review. |
| Total amount | Useful for threshold/risk review. |
| Consumption tax amount | Useful for Japan tax review. |
| Currency | Defaults to JPY if clear. |
| Payment due date / terms | Optional. |
| Line descriptions | Optional supporting evidence. |

## Customer OCR fields

| Field | Notes |
|---|---|
| Customer name | Required before draft submission. |
| Billing title | Required if used for invoicing. |
| Customer address | Optional but useful. |
| Contact/Attn | Optional. |
| Billing email | Optional if found in invoice/email source. |
| Payment terms | Useful for billing setup. |
| Project/service description | Useful to link customer to project records. |
| Currency | Defaults to JPY if clear. |
| Historical invoice amount | Useful for confidence and history. |
| Tax treatment | Useful for Japan billing/tax review. |

## Draft statuses

| Status | Meaning |
|---|---|
| `ocr_imported` | OCR text/data imported. |
| `needs_review` | Human review required. |
| `duplicate_suspected` | Possible existing master record found. |
| `submitted` | Reviewer submitted draft for approval. |
| `approved` | Approver accepted the draft. |
| `converted` | Draft was converted to formal master data. |
| `rejected` | Draft was rejected and will not convert. |

## Process flow

```text
Upload document
        ↓
Save original file metadata / document reference
        ↓
Run OCR or import OCR text/JSON
        ↓
Create supplier/customer draft
        ↓
Map extracted fields to draft fields
        ↓
Run duplicate checks
        ↓
Human reviews fields and confidence
        ↓
Submit for approval
        ↓
Approve or reject
        ↓
If approved: convert to formal supplier/customer master
        ↓
Append audit logs for each key action
```

## OCR storage model

Recommended draft object:

```json
{
  "draft_id": "draft-...",
  "draft_type": "supplier",
  "source_document_id": "doc-...",
  "source_type": "supplier_invoice",
  "ocr_raw_text": "...",
  "ocr_extracted_fields": {},
  "confidence_score": 0.86,
  "duplicate_candidates": [],
  "status": "needs_review",
  "reviewed_by": "",
  "approved_by": "",
  "converted_master_id": "",
  "created_at": "",
  "updated_at": ""
}
```

## Duplicate detection

Supplier duplicate signals:

1. Supplier name exact/normalized match.
2. Invoice registration number match.
3. Corporate number match.
4. Bank account number + account holder match.
5. Address similarity.
6. Contact email/phone match.

Customer duplicate signals:

1. Customer name exact/normalized match.
2. Existing `customer_code` in project/customer records.
3. Billing title match.
4. Address similarity.
5. Billing email/contact match.
6. Historical issued invoice customer name match.

MVP recommendation:

- Start with exact normalized name and code/registration-number matching.
- Add fuzzy matching later after data quality is better understood.

## Human review requirements

Reviewers must be able to:

1. See original document or file name/reference.
2. See raw OCR text.
3. Edit mapped fields before submission.
4. See low-confidence or missing fields.
5. See duplicate candidates.
6. Add review notes.
7. Submit, reject, or convert after approval.

Supplier-specific safety rule:

- Bank information extracted by OCR must be shown as unverified until a human confirms it.
- Bank information change or activation should be logged with action `bank_change` or equivalent.

## Audit logging

Recommended module keys:

| Draft type | Module key |
|---|---|
| Supplier OCR draft | `master_data.supplier_draft` |
| Customer OCR draft | `master_data.customer_draft` |

Recommended actions:

- `ocr_import`
- `update`
- `duplicate_warning`
- `submit`
- `approve`
- `reject`
- `convert`

Required audit fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

## Implementation phases

### Phase 1 — Draft foundation

1. Add supplier/customer draft JSON schema.
2. Add draft list and draft detail pages.
3. Add manual draft creation and update.
4. Add status transitions and audit logging.

### Phase 2 — OCR import MVP

1. Add document upload metadata or file reference model.
2. Add OCR raw text/JSON import field.
3. Map OCR fields into draft fields.
4. Add duplicate warning by exact matches.
5. Keep all OCR output editable before approval.

### Phase 3 — Approval and conversion

1. Add submit/approve/reject transitions.
2. Convert approved supplier draft to formal supplier.
3. Convert approved customer draft to formal customer.
4. Link draft to converted master ID.
5. Preserve source OCR/document references.

### Phase 4 — Intelligent assistance

1. Add field-level confidence display.
2. Add OCR prompt/template library.
3. Add fuzzy duplicate scoring.
4. Add completeness score.
5. Add conversion recommendations from repeated one-time party usage.

## OCR prompt draft direction

For supplier invoice OCR, the prompt should ask for:

- issuer/supplier name;
- address;
- invoice registration number;
- invoice number/date;
- amount/tax/currency;
- bank information;
- payment terms;
- raw uncertain fields with confidence notes.

For issued customer invoice OCR, the prompt should ask for:

- invoice recipient/customer name;
- billing title/address;
- contact/attention line;
- payment terms;
- project/service description;
- amount/tax/currency;
- uncertainty notes.

## Open decisions

1. Confirm whether OCR is initially manual text/JSON import or integrated with an OCR provider.
2. Confirm where uploaded source documents should be stored.
3. Confirm whether customer OCR should prefer structured invoice data when the invoice was system-generated.
4. Confirm reviewer/approver roles from User_admin.
5. Confirm whether supplier bank data is displayed masked except to Finance/Admin users.
