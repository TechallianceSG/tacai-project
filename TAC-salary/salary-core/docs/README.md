# Salary Core Module

Last updated: 2026-06-23

`salary-core` owns the shared APAC payroll workflow and reusable payroll objects. It must not contain country-specific statutory formulas directly; those belong in `salary-jp`, `salary-sg`, and `salary-cn`.

## Core responsibilities

- Payroll period creation by `country_code + entity_id + payroll_month`.
- Payroll batch creation and lifecycle status control.
- Employee snapshot capture from EmployeeAdmin.
- Salary Profile linking by stable `employee_id`.
- Common earnings/deductions/net pay/employer cost structures.
- Manual adjustment records with reason and approval.
- First notice, employee feedback, correction, final notice workflow.
- Two-level payroll confirmation.
- Payment preparation and paid status tracking.
- Payslip PDF versioning and download audit.
- System email delivery tracking.
- Append-only audit logging.

## Standard monthly workflow

1. Maintain Salary Profiles and payroll parameters.
2. Create payroll period and batch by country/entity/month.
3. Load employee population and snapshots.
4. Run calculation using country module logic plus manual parameters.
5. HR reviews and adjusts with reasons.
6. Send first notice and PDF payslip by system email.
7. Collect employee feedback.
8. Correct validated issues.
9. Send final notice.
10. Complete first confirmation.
11. Complete second confirmation.
12. Finalize and lock payroll.
13. Prepare/execute payment.
14. Archive payroll history.

## Core status model

Recommended batch statuses:

- `draft_created`
- `data_loaded`
- `calculated`
- `hr_review`
- `first_notice_sent`
- `employee_feedback`
- `corrected`
- `final_review`
- `first_confirmed`
- `second_confirmed`
- `finalized`
- `payment_prepared`
- `paid`
- `archived`
- `voided`

## Common formulas

```text
gross_pay = base salary + allowances + variable earnings + overtime/bonus/other earnings
employee_deductions = statutory employee deductions + payroll deductions + other approved deductions
net_pay = gross_pay - employee_deductions + manual_adjustments_total
employer_cost = gross_pay + employer-side statutory/contribution costs + other employer costs
```

## Confirmation rule

Payroll finalization requires two separate confirmation actions.

Admin may perform both actions only when permission allows it. Even then, the system must write two separate audit logs:

- `first_confirmation_completed`
- `second_confirmation_completed`

## Related documents

- `../../docs/Project_Plan.md`
- `../../docs/Data_Schema.md`
- `../../docs/Salary_Table_Specification.md`
