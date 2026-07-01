# TACAI Pay SG Design

## Product objective

Build a practical Singapore payroll system for a medium-sized recruitment, IT staffing and dispatch company. The system should let HR operations generate monthly payroll from EmployeeAdmin master data, calculate payroll, obtain approvals, issue payslips, release payment files to Finance and produce cost reports.

## Main workflow

1. **Salary Master**
   - Generate salary master records from EmployeeAdmin only when country/work country is `SG` and the employee is active/in service.
   - EmployeeAdmin remains the source of truth for employee identity, legal entity, department, team and employment status. TACAI Pay SG stores only the required employee reference snapshot plus payroll execution master values.
   - Maintain payroll-specific values locally: salary type, basic salary, hourly/daily rate, allowances, deductions, CPF handling, SDL/FWL, bank data and payroll notes.
   - EmployeeAdmin sync is merge-safe: it refreshes employee identity/status/organization references but does not overwrite locally maintained payroll fields.
   - Salary master records are not physically deleted. Incorrect records are deactivated with audit trail; if the EmployeeAdmin employee remains active, the same salary master can be regenerated/reactivated.
   - Readiness indicators show whether a salary master is ready, incomplete, blocked by EmployeeAdmin status or inactive.

2. **Monthly Payroll Batch**
   - HR creates batch by month and SG entity.
   - System creates one payroll row per active SG salary master employee whose EmployeeAdmin/employment status is still active/in service.
   - Static data is copied from salary master for auditability.

3. **Input and Calculation**
   - HR reviews work days/hours, allowances, bonus, deductions, CPF manual values, SDL and FWL.
   - Calculation supports monthly prorated, hourly and daily salary types.
   - CPF is manual-safe by default; parameter-assisted mode requires validated active payroll parameters.

4. **Review and Approval**
   - Batch statuses: `draft`, `calculated`, `hr_reviewed`, `approved`, `finalized`, `payslips_generated`, `sent_to_employees`, `employee_confirmed`, `released_to_finance`, `paid`, `correction`, `voided`.
   - Each important transition writes an audit entry.

5. **Payslips and Employee Confirmation**
   - System generates dependency-free PDF payslips.
   - Email delivery is queued when SMTP is not configured; sent/failed when SMTP is configured.
   - HR can mark employee confirmation status per row.

6. **Finance and Reports**
   - Reports include payroll register CSV, employer cost CSV and bank payment CSV.
   - Paid status closes the operational lifecycle for the month.

## Singapore payroll items

Earnings:

- Base pay
- Fixed allowance
- Bonus/additional pay
- Other payment

Deductions:

- Employee CPF
- Recurring deductions
- Other deduction
- Income tax / withholding placeholder

Employer costs:

- Gross pay
- Employer CPF
- Skill Development Levy (SDL)
- Foreign Worker Levy (FWL)

## Architecture

- Python standard library only.
- Server-rendered SAP/Fiori-inspired UI.
- JSON local storage for MVP speed and audit visibility.
- Append-only audit logs with required fields: module, record_id, action, user, timestamp, before_value, after_value.
- Trilingual labels: Simplified Chinese, Japanese and English.
- Designed to later integrate with EmployeeAdmin, Timesheet, Portal/User_admin and Finance modules.
