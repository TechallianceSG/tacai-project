# TACAIPAY JP Data Schema

TACAIPAY JP is a local-first Japanese payroll MVP for dispatch, recruiting, RPO, and payroll-management companies.

## Storage

All tables are JSON arrays under `database/`. Records use stable IDs and append-only audit logs.

## Core Tables

### `salary_master.json`

One active payroll profile per employee. Employee data should come from EmployeeAdmin when possible.

Key fields:

- `profile_id`
- `employee_id` — immutable EmployeeAdmin ID; primary integration key
- `employee_number`, `display_name`, `email`
- `entity_id`, `department_id`, `employment_type`, `country_code`
- `salary_type` — `monthly`, `hourly`, `daily`, `mixed`, `manual`
- `base_salary`, `hourly_rate`, `daily_rate`, `transportation_allowance`
- `standard_work_days`, `standard_work_hours`
- `fixed_earnings[]`, `fixed_deductions[]`
- `health_insurance_enrolled`, `pension_enrolled`, `employment_insurance_enrolled`
- `default_income_tax`, `default_resident_tax`
- `bank` — sensitive; redact in audit/list views
- `status`, `effective_from`, `effective_to`

### `payroll_batches.json`

One monthly payroll run per entity/month/type.

Key fields:

- `batch_id`
- `entity_id`, `payroll_month`, `payroll_type`
- `period_start`, `period_end`, `payment_date`
- `status`, `version_no`, `active_status`
- `record_count`, `gross_total`, `deduction_total`, `net_total`, `employer_cost_total`, `company_total_cost`
- lifecycle metadata: `created_by`, `loaded_by`, `calculated_by`, `finalized_by`, `payment_prepared_by`, `paid_by`

Status flow:

```text
draft_created -> master_loaded -> calculated -> hr_reviewed -> first_approved -> final_approved -> finalized -> payment_prepared -> paid
```

### `payroll_records.json`

One employee payroll row per batch.

Key fields:

- `record_id`, `batch_id`, `entity_id`, `payroll_month`
- `employee_id`, `employee_number`, `display_name`
- `employee_snapshot`, `salary_master_snapshot`
- `attendance` — work days/hours, absence, overtime, late night, holiday
- `variable_earnings[]`, `variable_deductions[]`
- `manual_income_tax`, `manual_resident_tax`
- calculated arrays: `earnings[]`, `deductions[]`, `employer_costs[]`
- totals: `gross_total`, `deduction_total`, `net_pay`, `employer_cost_total`, `company_total_cost`
- `calculation_messages[]`
- `status`, `employee_feedback_status`, `payment_status`

### `payroll_item_definitions.json`

Configurable payroll item catalog. Items include trilingual labels and flags:

- `category`: `earning`, `deduction`, `employer_cost`
- `sub_category`: `base`, `allowance`, `overtime`, `statutory`, `attendance`, `manual`, `adjustment`
- `taxable`, `social_insurance_base`, `employment_insurance_base`, `payslip_visible`, `requires_reason`

### `payroll_parameters.json`

Japan calculation parameters. MVP values are parameter-assisted, not official tax/social-insurance automation.

Examples:

- standard monthly/daily work hours
- overtime/late-night/holiday multipliers
- employee/employer health insurance, pension, employment insurance rates
- rule version and effective dates

### Other Tables

- `payslip_documents.json` — generated HTML payslip metadata
- `payslip_feedback.json` — employee confirmation/correction requests
- `payroll_confirmations.json` — HR/final confirmation evidence
- `payment_records.json` — payment preparation/paid metadata
- `report_exports.json` — CSV/report export history
- `email_deliveries.json` — dry-run/queued payslip email records
- `audit_logs.json` — append-only audit trail

## Legal/Payroll Caution

The first release is a practical workflow system. Japanese statutory tax/social-insurance values are parameter-assisted estimates or manual inputs. Final payroll must be reviewed by HR/payroll/tax specialists before approval and payment.
