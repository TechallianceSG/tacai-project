# Accounting Rules

## Purpose

This document records initial payroll accounting rules for TACAI Prj.

## Payroll calculation groups

### Payment items / 支給項目

- Base Salary / 基本給
- Position Allowance / 役職手当
- Attendance Allowance / 勤務手当
- Housing Allowance / 住宅手当
- Taxable Transportation Allowance / 課税通勤費
- Non-taxable Transportation Allowance / 非課税通勤費
- Overtime Allowance / 普通残業手当

### Deduction items / 控除項目

- Health Insurance / 健康保険
- Pension / 厚生年金
- Employment Insurance / 雇用保険
- Income Tax / 所得税

## Derived values

### Gross Pay / 総支給額

Gross Pay = Base Salary + Position Allowance + Attendance Allowance + Housing Allowance + Taxable Transportation Allowance + Non-taxable Transportation Allowance + Overtime Allowance

### Total Deduction / 控除合計

Total Deduction = Health Insurance + Pension + Employment Insurance + Income Tax

### Net Pay / 差引支給額

Net Pay = Gross Pay - Total Deduction

## Data precision rules

1. Use decimal arithmetic for all monetary calculations.
2. Store JPY amounts as whole yen unless business rules later require decimals.
3. Empty monetary cells should be treated as zero after validation.
4. Negative values are not allowed by default and must be explicitly approved as correction entries.

## Payroll correction rules

1. Do not overwrite existing payroll records.
2. Re-uploaded payroll data for the same payroll month must create a new upload batch version.
3. Previous active records should be marked as superseded only after the new batch passes validation.
4. All correction actions must be recorded in the audit log.

## Country payroll accounting mappings

### Japan

Japan remains aligned to the original payslip-style canonical fields:

- Payments: base salary, position allowance, attendance allowance, housing allowance, taxable/non-taxable transportation allowance, overtime allowance, and additional payment.
- Deductions: health insurance, pension, employment insurance, confirmed income tax, resident tax where configured, and additional deduction.
- Resident tax is a manual/fixed monthly amount and is not automatically derived from monthly gross pay.
- Japan income-tax reference estimates are configuration-driven; if no withholding table is configured, HR must enter or confirm the final tax amount.

### China standardized payroll draft

China payroll should use the standardized draft fields in `Project_Specification.md` and map to accounting as follows:

- Payments: calculated base/attendance pay, hourly pay when applicable, and additional payment.
- Employee deductions: employee social insurance, employee housing fund, confirmed individual income tax, and additional deduction.
- Tax-reference-only items: estimated IIT, cumulative taxable income, prior YTD income/deductions/tax withheld, special additional deductions, and other tax-before-deduction inputs.
- Employer-cost items may be added later as report-only fields; they should not reduce employee net pay unless explicitly defined as employee deductions.
- City affects social insurance/housing-fund assumptions and reference notes; it does not change IIT rate tables.

### Singapore standardized payroll draft

Singapore payroll should map to accounting as follows:

- Payments: monthly salary/prorated basic salary, hourly pay when applicable, and additional payment.
- Employee deductions: employee CPF and additional deduction.
- Employer CPF is an employer cost/reporting item and does not reduce employee net pay in the current MVP.
- Tax handling for Singapore is not automated in this MVP; any employee deduction must be entered and confirmed by HR if required by the business process.

## Tax confirmation rules

1. Estimated tax is reference-only and must be stored separately from confirmed tax.
2. Net pay uses confirmed/applied tax only.
3. If HR applies an estimate as final tax, the audit log must show that the confirmed deduction was created from an estimate.
4. Do not invent missing statutory data. Missing tax/social-insurance inputs must appear as warnings or HR notes.

## Export rules

1. Payroll Register exports must include payroll month/filter, export timestamp, exporting user, and selected country template.
2. Audit Log exports must include enough information to trace who changed what and when.
3. Current MVP exports are Excel-compatible UTF-8 CSV and HTML/printable payslip preview.
4. Native `.xlsx`, PDF payslip, merged PDF, and ZIP bundle exports are later-phase items unless an export dependency/service is approved.

## Scope note

Expense reimbursement / 経費精算 is out of scope for TACAI Prj and will be developed as a separate application. Archived reference assets remain under `archive/reimbursement/` only for future standalone planning.
