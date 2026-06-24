# Business Rules

## Business positioning

VendorPayables manages external supplier payment requests. It does not manage employee daily reimbursement.

Typical supplier categories:

- Recruitment media fees
- Outsourcing project costs
- SaaS / system fees
- Professional services
- Office and admin costs
- Other supplier invoices

## Japan AP considerations

### Qualified invoice registration

For Japan consumption tax compliance, vendors may have a qualified invoice issuer number (`適格請求書発行事業者登録番号`). MVP stores this value but does not validate it against government services.

Recommended format check: `T` followed by 13 digits.

### Consumption tax

Supported tax rates:

- `10%`
- `8%`
- `0%`
- `mixed`
- `unknown`

Tax amount must not be negative and must not exceed total amount.

### Withholding tax

Most company-to-company vendor payments do not use withholding tax. MVP stores withholding tax amount as optional and defaults to `0`.

### Payment terms

Vendor master stores free-text payment terms such as:

- 月末締め翌月末払い
- 請求書受領後30日以内
- 20日締め翌月10日払い

MVP does not automatically calculate payment due date from payment terms; finance users enter due date manually.

## Required fields

Draft records can be incomplete.

Submitted records require:

- vendor name or vendor ID
- received date
- payment due date
- total amount greater than zero
- currency

Paid records require:

- actual payment date

## Money rules

- Store JPY amounts as integer yen.
- Do not use floats for money.
- Total amount must be greater than or equal to zero for drafts and greater than zero for submitted records.
- Tax amount cannot be negative.
- Tax amount cannot exceed total amount.

## Record preservation

- Prefer cancel/soft delete instead of physical delete.
- Audit logs are append-only and must never be deleted.
- Paid records should be treated as reference-only except for finance notes.
