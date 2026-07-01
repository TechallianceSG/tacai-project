# TACAI Pay SG

Singapore payroll MVP for TACAI recruitment, IT staffing, dispatch and payroll operations.

## Scope

This module is designed for Singapore payroll operations and references the existing EmployeeAdmin / TACAI payroll UX style:

- Generate Salary Master from active SG employees in EmployeeAdmin; EmployeeAdmin remains the source for employee identity, entity, department and team references.
- Maintain local payroll execution master data: salary type, basic salary, hourly/daily rates, allowances, recurring deductions, CPF mode, SDL/FWL, bank data and payroll notes.
- EmployeeAdmin import is merge-safe: it refreshes employee identity/status/organization snapshots without overwriting locally maintained payroll, CPF or bank fields.
- Salary Master records are not deleted. If a record is wrong, deactivate it; if the EmployeeAdmin employee is still active, the same record can be regenerated/reactivated without creating a duplicate.
- Generate one monthly payroll row per active SG salary master employee who is still active/in service.
- Enter/review monthly attendance values and deductions.
- Run payroll calculation for monthly, hourly and daily employees.
- Support manual CPF by default and parameter-assisted CPF only when validated parameters are configured.
- HR review, next-level approval, finalization, payslip generation, employee email queue/send, finance release and paid statuses.
- Generate payroll, employer cost and bank payment CSV reports.
- Generate simple PDF payslips without external dependencies.
- Maintain append-only audit logs.
- Provide Chinese, Japanese and English UI labels.

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Project/TACAIPAY/tacaipaysg
python3 backend/app.py --host 127.0.0.1 --port 8016
```

Health check:

```bash
curl -s http://127.0.0.1:8016/health
```

## Portal and User_admin integration

TACAI Pay SG is registered in Portal as module key `tacaipay_sg` and is intended to be opened from:

```text
http://127.0.0.1:8005/dashboard
```

The direct module URL is:

```text
http://127.0.0.1:8016/
```

All non-health routes require a valid User_admin `tacai_session_id` and `tacaipay_sg.access` permission.

Permission keys:

- `tacaipay_sg.access`
- `tacaipay_sg.view`
- `tacaipay_sg.manage`
- `tacaipay_sg.calculate`
- `tacaipay_sg.approve`
- `tacaipay_sg.release_payment`
- `tacaipay_sg.reports.view`
- `tacaipay_sg.audit.view`

Syntax check:

```bash
python3 -m py_compile backend/app.py
```

## Data files

Local JSON files are stored in [database/](database/):

- `salary_master.json`
- `payroll_batches.json`
- `payroll_records_sg.json`
- `payroll_parameters.json`
- `payslips.json`
- `payslip_email_deliveries.json`
- `audit_logs.json`

Generated payslip PDFs are stored in [payslips/](payslips/).

## Important compliance note

Singapore statutory values such as CPF rates, wage ceilings, SDL and FWL must be validated before production use. The MVP defaults to manual-safe CPF handling and only performs parameter-assisted calculation when active parameters contain validated rates.
