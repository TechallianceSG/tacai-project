# Reporting Plan

## 1. Month-end report purpose

The month-end reimbursement report should give finance and payroll enough information to calculate employee reimbursement amounts and include them in salary/payment processing.

## 2. Report source data

Initial report should include claims with status:

```text
Approved
```

Later, if payment tracking is implemented, payroll may use status:

```text
Paid
```

This decision should be confirmed before payroll integration.

## 3. Default monthly report filters

- claim month
- employee number
- department
- approval status
- category
- tax rate
- payment method

## 4. CSV columns

Recommended initial CSV columns:

```text
claim_no
status
employee_no
employee_name
department
claim_month
expense_date
category
vendor_name
invoice_or_receipt_number
qualified_invoice_number
is_qualified_invoice
currency
total_amount
tax_amount
tax_rate
payment_method
business_purpose
attachment_filename
approved_at
approved_by
finance_notes
```

## 5. Summary totals

Monthly report page should show:

- total claim count
- total amount
- total tax amount
- total by employee
- total by category
- total by tax rate
- total by payment method

## 6. Payroll handoff questions

1. Should reimbursements be paid together with salary or separately?
2. Does payroll need one total per employee or detailed claim rows?
3. Should rejected/draft/submitted claims be excluded completely?
4. Should finance export report after approval or after marking claims as paid?
5. Is Japanese consumption tax information required in payroll handoff or only accounting handoff?
