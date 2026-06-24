# One-Time Supplier and Customer Workflow

## Purpose

This workflow defines how TAC-timesheet and future TACAI modules should support one-time suppliers and one-time customers without polluting formal master data.

The key principle is:

> Use one reserved code for one-time party selection, then store the real party details on the transaction where the business event occurs.

## Reserved codes

| Party type | Reserved code | Meaning |
|---|---|---|
| Supplier | `SUP-9999` | One-time supplier placeholder. |
| Customer | `CUS-9999` | One-time customer placeholder. |

These codes are not normal recurring business partners. They exist to keep workflows moving when formal master data is not yet available or not justified.

## When to use one-time supplier

Allowed examples:

- Low-frequency supplier invoice.
- Temporary expense or reimbursement supplier.
- One-off professional service.
- A supplier invoice arrives before formal supplier onboarding is completed.

Not recommended:

- Recurring vendor.
- Supplier with repeated bank transfers.
- Critical supplier for payroll, haken, RPO, or recurring operations.
- Supplier requiring contract or compliance review.

## When to use one-time customer

Allowed examples:

- One-time billing customer.
- Temporary project customer.
- Historical invoice recovery when customer master does not exist yet.

Not recommended:

- Haken client.
- RPO client.
- Payroll client.
- Recruitment client with ongoing relationship.
- Customer with signed long-term contract.

## One-time supplier transaction fields

When `SUP-9999` is selected, the transaction must capture the real one-time supplier details.

| Field | Required | Description |
|---|---:|---|
| `party_code` | Auto | `SUP-9999`. |
| `party_type` | Auto | `supplier`. |
| `is_one_time` | Auto | `true`. |
| `one_time_name` | Yes | Supplier name from invoice/receipt. |
| `one_time_description` | Yes | Business reason for using a one-time supplier. |
| `one_time_address` | No | Address if available. |
| `one_time_contact` | No | Contact person/email/phone if available. |
| `one_time_tax_number` | No | Invoice registration number or tax reference if available. |
| `one_time_invoice_number` | No | Supplier invoice/receipt number. |
| `one_time_invoice_date` | No | Supplier invoice/receipt date. |
| `one_time_bank_name` | Conditional | Required if bank transfer payment is in scope. |
| `one_time_bank_branch` | Conditional | Bank branch if available. |
| `one_time_bank_account_type` | Conditional | Ordinary/current/etc. |
| `one_time_bank_account_number` | Conditional | Bank account number. |
| `one_time_bank_account_holder` | Conditional | Account holder name. |
| `attachment_ids` | Recommended | Invoice, receipt, contract, quotation, or supporting document. |
| `approval_required` | Auto | Based on amount/risk rules. |
| `approval_status` | Auto | `not_required`, `pending`, `approved`, or `rejected`. |

## One-time customer transaction fields

When `CUS-9999` is selected, the transaction must capture the real one-time customer details.

| Field | Required | Description |
|---|---:|---|
| `party_code` | Auto | `CUS-9999`. |
| `party_type` | Auto | `customer`. |
| `is_one_time` | Auto | `true`. |
| `one_time_name` | Yes | Customer display or legal name. |
| `one_time_description` | Yes | Business reason for using a one-time customer. |
| `one_time_billing_title` | Conditional | Required if an invoice is issued. |
| `one_time_address` | No | Billing address if available. |
| `one_time_contact` | No | Billing/business contact. |
| `one_time_email` | No | Invoice delivery email. |
| `one_time_tax_number` | No | Customer tax/reference number if available. |
| `one_time_payment_terms` | No | Payment terms, e.g. `月末締め翌月末払い`. |
| `attachment_ids` | No | Order, contract, customer confirmation, or email evidence. |
| `approval_required` | Auto | Based on amount/risk rules. |
| `approval_status` | Auto | `not_required`, `pending`, `approved`, or `rejected`. |

## Approval rules

Recommended MVP rules:

| Rule | Supplier | Customer |
|---|---|---|
| Name and reason required | Yes | Yes |
| Attachment required | Yes if payment-sensitive | Recommended if billing-sensitive |
| Amount threshold approval | Yes | Yes if billing/credit risk applies |
| Bank information review | Yes | Not normally applicable |
| Repeat-use conversion warning | Yes | Yes |
| Audit log required | Yes | Yes |

Open threshold decision:

- Option A: approval required above 50,000 JPY.
- Option B: approval required above 100,000 JPY.
- Option C: configurable threshold by module/entity.

Recommended starting point: 100,000 JPY for MVP, with manual override for Finance/Admin.

## Repeat-use conversion rule

If the same normalized one-time party name appears 3 or more times, the system should show:

```text
This one-time supplier/customer appears repeatedly. Please consider creating a formal master record.
```

Later enhancement:

- Force conversion before additional use after a configurable number of uses.
- Show candidate draft pre-filled from prior one-time transaction fields.

## Process flow

```text
User selects supplier/customer field
        ↓
Chooses SUP-9999 or CUS-9999
        ↓
System expands one-time party section
        ↓
User enters name, reason, and required transaction details
        ↓
System evaluates amount/risk/attachment rules
        ↓
If approval required: route to reviewer
        ↓
Approved one-time party details continue into downstream process
        ↓
Audit row records one-time usage and approval decision
        ↓
If repeated use detected: recommend formal master creation
```

## UI behavior

When a user selects `SUP-9999` or `CUS-9999`, the UI should:

1. Show a clear warning that this is not a formal master record.
2. Expand the one-time party detail section.
3. Mark required fields with trilingual labels where possible.
4. Show attachment and approval requirements.
5. Show duplicate/repeat-use warnings if a similar one-time name exists.

Suggested labels:

| Chinese | Japanese | English |
|---|---|---|
| 一次性供应商 | 一時仕入先 | One-time supplier |
| 一次性客户 | 一時顧客 | One-time customer |
| 业务原因 | 業務理由 | Business reason |
| 转正式主数据建议 | 正式マスタ化の推奨 | Formal master recommendation |

## Audit logging

Every one-time usage should append audit evidence.

Supplier module key:

```text
master_data.one_time_supplier_usage
```

Customer module key:

```text
master_data.one_time_customer_usage
```

Recommended actions:

- `use`
- `submit`
- `approve`
- `reject`
- `convert_recommended`
- `converted_to_master`

Required audit fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

## Implementation tasks

P0:

1. Reserve `SUP-9999` and `CUS-9999` in validation rules.
2. Define reusable one-time party field schema.
3. Add UI expansion behavior in the relevant transaction forms.
4. Persist one-time party details at transaction level.
5. Append audit rows for one-time party usage.

P1:

1. Add threshold approval logic.
2. Add repeat-use detection by normalized name.
3. Add conversion recommendation banner.
4. Add manual conversion from one-time details to draft supplier/customer.

P2:

1. Add configurable thresholds by entity/module.
2. Add dashboard/report for one-time party usage.
3. Add forced conversion policy after repeated use.
