# TAC-salary Data Schema v2 — APAC Payroll

Last updated: 2026-06-24


## 2026-06-24 country payroll system metadata

The local MVP now treats country payroll system metadata as first-class scope fields. Existing and new batch, salary master, parameter, and payroll row objects should carry these fields where applicable:

```text
country_code
legal_entity_id / entity_id
payroll_system_code
payroll_area_code
rule_version_id
```

Standard country payroll systems:

| Country | User-facing system | `payroll_system_code` | `payroll_area_code` | Entity scope |
|---|---|---|---|---|
| JP | 日本薪资计算 / Japan Payroll | `JP_PAYROLL` | `JP_MONTHLY` | Japan entities only |
| SG | 新加坡薪资计算 / Singapore Payroll | `SG_PAYROLL` | `SG_MONTHLY` | Singapore entities only |
| CN | 中国薪资计算 / China Payroll | `CN_PAYROLL` | `CN_MONTHLY` | China entities only |

`entity_snapshot` should also include `legal_entity_id`, `payroll_system_code`, `payroll_area_code`, and `payroll_module_name` so historical payroll records remain understandable after master-data changes.

## 1. Purpose

This document defines the v2 local JSON data schema for TAC-salary as an APAC payroll system covering Japan, Singapore, and China.

The v2 schema replaces the earlier single salary-table mindset. The new design supports:

- JP/SG/CN first formal payroll rollout.
- Payroll batch creation by `country_code + entity_id + payroll_month`.
- Employee salary master and employee snapshots.
- Independent country payroll record files for JP/SG/CN.
- Employee net pay and employer cost reporting.
- System email payroll notices.
- PDF payslip download/versioning.
- Employee feedback and HR correction workflow.
- Two-level payroll confirmation.
- Payment preparation and payment completion tracking.
- Append-only audit logs.

All database files are local JSON arrays under `database/` for the local MVP. Future database migration should preserve the same logical objects and auditability.

---

## 2. General conventions

### 2.1 Country, currency, and date fields

Country codes:

- `JP` — Japan
- `SG` — Singapore
- `CN` — China

Default currencies:

- `JP` → `JPY`
- `SG` → `SGD`
- `CN` → `CNY`

Date/time formats:

- Month: `YYYY-MM`, for example `2026-06`.
- Date: `YYYY-MM-DD`.
- Timestamp: ISO-8601 string with timezone.

### 2.2 Amount fields

- Amount fields are stored as numbers.
- Currency is stored on batch and payroll row.
- Rounding policy should be stored in payroll parameters, not hidden in code.
- For JPY, decimal amounts should normally be rounded according to Japanese payroll policy.
- For SGD/CNY, decimal support should remain available.

### 2.3 Entity source of truth

Legal entities must be referenced from TACAI Master Data, not recreated inside TAC-salary.

Current Master Data records reviewed on 2026-06-23:

| Country | Entity ID | Entity Code | Entity Name | Currency | Status |
|---|---:|---|---|---|---|
| Japan | `ENT-0001` | `TAKK` | Tech Alliance KK / Tech Alliance株式会社 | JPY | active |
| Singapore | `ENT-0002` | `TASG` | Tech Alliance Consultancy Service Pte. Ltd | SGD | active |
| China | `ENT-0003` | `TANJ` | Tech Alliance Consultancy Nanjing Co. Ltd / 南京特谙斯企业咨询有限公司 | CNY | active |
| China | `ENT-0004` | `TAXA` | Tech Alliance Consultancy Xian Co. Ltd / 西安特谙斯企业咨询有限公司 | CNY | active |
| China | `ENT-0005` | `TASH` | Tech Alliance Consultancy Shanghai Co. Ltd / 上海特安企业管理有限公司 | CNY | active |

Business confirmation updated on 2026-06-23: China payroll scope includes all 3 active China legal entities currently present in Master Data: Nanjing, Xi'an, and Shanghai. The schema supports any number of legal entities and payroll batches should be created per China entity/month.

### 2.4 Employee source of truth

Employee master identity should be referenced from EmployeeAdmin.

Payroll records must store snapshots because historical payroll must not change when EmployeeAdmin changes later.

### 2.5 Status immutability

- Draft/calculated records can be edited by authorized payroll users.
- Confirmed/finalized/paid records must not be silently edited.
- Corrections after finalization should be created as a new adjustment, replacement version, or next-month correction record.
- Voided records remain retained for audit.

---

## 3. Database files

Recommended v2 files under `database/`:

```text
database/
  payroll_batches.json
  payroll_records_jp.json
  payroll_records_sg.json
  payroll_records_cn.json
  salary_master.json
  payroll_parameters.json
  payroll_notices.json
  payslip_documents.json
  employee_feedback.json
  payroll_confirmations.json
  payment_records.json
  payroll_import_runs.json
  audit_logs.json
```

Rationale:

- `payroll_batches.json` is shared across countries.
- `payroll_records_jp.json`, `payroll_records_sg.json`, and `payroll_records_cn.json` keep country payroll sheets independent.
- Shared workflow objects such as notices, PDF documents, confirmations, payment records, imports, and audit logs remain common.

Optional reporting/cache files can be generated later, but authoritative data should remain in the files above.

---

## 4. Enumerations

### 4.1 Payroll batch status

```text
not_started
batch_created
data_loaded
calculated
hr_review
first_confirmed
first_notice_sent
employee_feedback
corrected
second_confirmed
final_notice_sent
finalized
payment_prepared
paid
archived
voided
```

### 4.2 Payroll row status

```text
draft
calculated
needs_review
adjusted
first_notice_sent
feedback_received
corrected
confirmed
finalized
payment_prepared
paid
voided
```

### 4.3 Employment type

```text
regular
haken_dispatch
contract
part_time
foreign_national
executive
other
```

One employee can be both `foreign_national` and another employment type. If needed, store `employment_type` plus `foreign_national_flag`.

### 4.4 Calculation method

```text
automated
parameter_assisted
manual
manual_override
imported
```

### 4.5 Notice type and status

Notice types:

```text
first_notice
corrected_notice
final_notice
```

Notice statuses:

```text
pending
queued
sent
failed
cancelled
```

### 4.6 Confirmation level

```text
first_confirmation
second_confirmation
admin_dual_confirmation
```

Implementation note: even when Admin performs both confirmation functions, store two separate confirmation records.

---

## 5. `payroll_batches.json`

One record represents one monthly payroll batch for one country and one legal entity.

Unique key:

```text
country_code + entity_id + payroll_month + batch_version
```

Example:

```json
{
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "batch_version": 1,
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "entity_code_snapshot": "TAKK",
  "entity_name_snapshot": "Tech Alliance株式会社",
  "payroll_month": "2026-06",
  "payroll_period_start": "2026-06-01",
  "payroll_period_end": "2026-06-30",
  "payment_date": "2026-07-25",
  "currency": "JPY",
  "status": "batch_created",
  "employee_count": 0,
  "total_gross_pay": 0,
  "total_employee_deductions": 0,
  "total_net_pay": 0,
  "total_employer_cost": 0,
  "rule_version_id": "RULE-JP-2026-06-V001",
  "created_by": "USR-0001",
  "created_at": "2026-06-23T09:00:00+09:00",
  "data_loaded_by": null,
  "data_loaded_at": null,
  "calculated_by": null,
  "calculated_at": null,
  "first_confirmed_by": null,
  "first_confirmed_at": null,
  "second_confirmed_by": null,
  "second_confirmed_at": null,
  "finalized_by": null,
  "finalized_at": null,
  "payment_prepared_by": null,
  "payment_prepared_at": null,
  "paid_by": null,
  "paid_at": null,
  "archived_by": null,
  "archived_at": null,
  "voided_by": null,
  "voided_at": null,
  "void_reason": "",
  "warnings": [],
  "notes": ""
}
```

Required fields:

- `batch_id`
- `batch_version`
- `country_code`
- `entity_id`
- `payroll_month`
- `payroll_period_start`
- `payroll_period_end`
- `payment_date`
- `currency`
- `status`
- `created_by`
- `created_at`

Validation rules:

- `country_code` must be one of `JP`, `SG`, `CN`.
- `entity_id` must reference active legal entity master data.
- `currency` must match country/entity unless explicitly overridden with approval.
- Only one non-voided active batch should exist for the same `country_code + entity_id + payroll_month` unless `batch_version` is used for controlled replacement.

---

## 6. `salary_master.json`

One record represents an employee's effective salary setup. This is not the monthly payroll result; it is the source salary profile used to create monthly payroll rows.

Unique key recommendation:

```text
employee_id + effective_start_date + salary_master_version
```

Example:

```json
{
  "salary_master_id": "SM-EMP-0001-2026-04-V001",
  "salary_master_version": 1,
  "employee_id": "EMP-0001",
  "employee_no_snapshot": "E0001",
  "employee_name_snapshot": "Sample Employee",
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "currency": "JPY",
  "employment_type": "haken_dispatch",
  "foreign_national_flag": false,
  "salary_type": "monthly",
  "effective_start_date": "2026-04-01",
  "effective_end_date": null,
  "base_salary": 300000,
  "hourly_rate": 0,
  "daily_rate": 0,
  "fixed_allowances": [
    {
      "allowance_code": "COMMUTE_NON_TAXABLE",
      "allowance_name": "Non-taxable commuting allowance",
      "amount": 15000,
      "taxable_flag": false,
      "employer_cost_flag": true
    }
  ],
  "standard_monthly_hours": 160,
  "standard_daily_hours": 8,
  "payment_method": "bank_transfer",
  "bank_name_snapshot": "",
  "bank_branch_snapshot": "",
  "bank_account_type_snapshot": "",
  "bank_account_last4_snapshot": "1234",
  "tax_profile": {
    "tax_residency_status": "resident",
    "dependent_count": 0,
    "manual_tax_flag": false
  },
  "social_insurance_profile": {
    "enrolled_flag": true,
    "manual_social_insurance_flag": false
  },
  "country_profile": {
    "jp_social_insurance_grade": "",
    "sg_cpf_applicable_flag": false,
    "cn_city_code": ""
  },
  "status": "active",
  "created_by": "USR-0001",
  "created_at": "2026-06-23T09:00:00+09:00",
  "updated_by": "USR-0001",
  "updated_at": "2026-06-23T09:00:00+09:00",
  "notes": ""
}
```

Required fields:

- `salary_master_id`
- `employee_id`
- `country_code`
- `entity_id`
- `currency`
- `employment_type`
- `salary_type`
- `effective_start_date`
- `base_salary` or `hourly_rate` depending on salary type
- `status`

Validation rules:

- Salary master changes must be audited.
- Effective dates must not overlap for the same employee unless explicitly allowed for future-dated changes.
- Full bank account numbers should not be displayed in normal payroll screens. Store masked snapshots in payroll rows.

---

## 7. Common payroll row fields

Each country-specific payroll row file must include the common fields below, plus country-specific fields.

Common identity and snapshot:

```json
{
  "payroll_record_id": "PR-JP-2026-06-EMP-0001-V001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "record_version": 1,
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "entity_code_snapshot": "TAKK",
  "entity_name_snapshot": "Tech Alliance株式会社",
  "payroll_month": "2026-06",
  "currency": "JPY",
  "employee_id": "EMP-0001",
  "employee_no_snapshot": "E0001",
  "employee_name_snapshot": "Sample Employee",
  "employee_name_local_snapshot": "",
  "department_id_snapshot": "",
  "department_name_snapshot": "",
  "team_id_snapshot": "",
  "team_name_snapshot": "",
  "project_id_snapshot": "",
  "project_name_snapshot": "",
  "client_id_snapshot": "",
  "client_name_snapshot": "",
  "employment_type_snapshot": "haken_dispatch",
  "foreign_national_flag_snapshot": false,
  "salary_type_snapshot": "monthly",
  "join_date_snapshot": "2024-04-01",
  "resign_date_snapshot": null,
  "work_country_snapshot": "JP",
  "work_location_snapshot": "Tokyo",
  "salary_master_id": "SM-EMP-0001-2026-04-V001",
  "source_employee_updated_at": "2026-06-20T10:00:00+09:00",
  "source_salary_master_updated_at": "2026-06-20T10:00:00+09:00"
}
```

Common time/attendance:

```json
{
  "scheduled_work_days": 20,
  "actual_work_days": 20,
  "paid_leave_days": 1,
  "unpaid_leave_days": 0,
  "absence_days": 0,
  "normal_work_hours": 160,
  "overtime_hours": 0,
  "holiday_work_hours": 0,
  "late_night_hours": 0,
  "attendance_source": "timesheet",
  "attendance_source_record_ids": [],
  "attendance_manual_adjustment_flag": false,
  "attendance_manual_adjustment_reason": ""
}
```

Common earnings:

```json
{
  "base_pay": 300000,
  "overtime_pay": 0,
  "holiday_work_pay": 0,
  "late_night_pay": 0,
  "allowance_taxable_total": 0,
  "allowance_non_taxable_total": 15000,
  "bonus_total": 0,
  "commission_total": 0,
  "retroactive_pay": 0,
  "other_earning_total": 0,
  "gross_pay": 315000,
  "taxable_gross_pay": 300000
}
```

Common employee deductions:

```json
{
  "statutory_deduction_total": 0,
  "tax_total": 0,
  "social_insurance_employee_total": 0,
  "manual_deduction_total": 0,
  "other_deduction_total": 0,
  "deduction_total": 0,
  "net_pay": 315000
}
```

Common employer cost:

```json
{
  "employer_social_insurance_total": 0,
  "employer_tax_or_levy_total": 0,
  "employer_benefit_cost_total": 0,
  "employer_other_cost_total": 0,
  "total_employer_cost": 315000,
  "total_company_cost": 315000
}
```

Calculation and control:

```json
{
  "calculation_method": "parameter_assisted",
  "rule_version_id": "RULE-JP-2026-06-V001",
  "calculation_status": "calculated",
  "calculated_by": "USR-0001",
  "calculated_at": "2026-06-23T09:10:00+09:00",
  "warning_count": 0,
  "warnings": [],
  "manual_adjustment_count": 0,
  "manual_adjustments": [],
  "hr_review_status": "pending",
  "employee_notice_status": "pending",
  "employee_feedback_status": "none",
  "payment_status": "not_prepared",
  "final_lock_flag": false,
  "status": "calculated",
  "notes": ""
}
```

Payment snapshot:

```json
{
  "payment_method": "bank_transfer",
  "bank_name_snapshot": "",
  "bank_branch_snapshot": "",
  "bank_account_type_snapshot": "",
  "bank_account_last4_snapshot": "1234",
  "payment_currency": "JPY",
  "payment_amount": 315000
}
```

---

## 8. `payroll_records_jp.json`

Japan payroll rows use all common payroll row fields plus Japan-specific fields.

Example country-specific section:

```json
{
  "jp": {
    "standard_monthly_hours": 160,
    "standard_daily_hours": 8,
    "legal_overtime_hours": 0,
    "non_statutory_overtime_hours": 0,
    "late_night_overtime_hours": 0,
    "statutory_holiday_hours": 0,
    "non_statutory_holiday_hours": 0,
    "overtime_rate": 1.25,
    "late_night_rate": 0.25,
    "holiday_rate": 1.35,
    "commuting_allowance_taxable": 0,
    "commuting_allowance_non_taxable": 15000,
    "health_insurance_employee": 0,
    "nursing_care_insurance_employee": 0,
    "pension_employee": 0,
    "employment_insurance_employee": 0,
    "income_tax_withholding": 0,
    "resident_tax": 0,
    "health_insurance_employer": 0,
    "nursing_care_insurance_employer": 0,
    "pension_employer": 0,
    "employment_insurance_employer": 0,
    "child_contribution_employer": 0,
    "workers_compensation_employer": 0,
    "social_insurance_grade_snapshot": "",
    "dependent_count_snapshot": 0,
    "tax_category_snapshot": "resident",
    "my_number_collected_flag_snapshot": false,
    "dispatch_assignment_id_snapshot": "",
    "dispatch_contract_id_snapshot": "",
    "client_site_snapshot": "",
    "haken_billing_reference_snapshot": ""
  }
}
```

Japan required first-rollout capabilities:

- Deep Japan payroll table structure.
- Overtime, late-night, statutory holiday, non-statutory holiday fields.
- Dispatch/haken assignment snapshots.
- Employee and employer-side social insurance fields.
- Resident tax and income tax withholding fields.
- Employer cost fields.

Compliance note: automate statutory calculation only after Japan payroll rule validation. Until then, fields can be manual or parameter-assisted.

---

## 9. `payroll_records_sg.json`

Singapore payroll rows use all common payroll row fields plus Singapore-specific fields.

Example country-specific section:

```json
{
  "sg": {
    "basic_salary": 5000,
    "gross_monthly_wage": 5000,
    "additional_wage": 0,
    "cpf_ordinary_wage": 5000,
    "cpf_additional_wage": 0,
    "employee_cpf": 0,
    "employer_cpf": 0,
    "cpf_calculation_method": "manual",
    "cpf_manual_override_reason": "Initial rollout manual CPF entry",
    "sdl": 0,
    "foreign_worker_levy": 0,
    "other_employer_levy": 0,
    "ir8a_income_category_snapshot": "",
    "citizenship_or_pr_status_snapshot": "",
    "work_pass_type_snapshot": "",
    "tax_residency_status_snapshot": "resident",
    "cpf_applicable_flag_snapshot": true
  }
}
```

Singapore required first-rollout capabilities:

- Full payroll sheet and workflow support.
- CPF employee and employer fields from launch.
- Manual or parameter-assisted CPF input acceptable initially.
- Employer cost reporting.
- PDF payslip and email notice support.

---

## 10. `payroll_records_cn.json`

China payroll rows use all common payroll row fields plus China-specific fields.

Initial China city scope:

- Shanghai — `SHANGHAI`
- Nanjing — `NANJING`
- Xi'an — `XIAN`
- Wuhu — `WUHU`

Example country-specific section:

```json
{
  "cn": {
    "city_code": "SHANGHAI",
    "residence_city_snapshot": "Shanghai",
    "work_city_snapshot": "Shanghai",
    "base_salary": 30000,
    "social_insurance_base": 30000,
    "housing_fund_base": 30000,
    "pension_employee": 0,
    "medical_employee": 0,
    "unemployment_employee": 0,
    "housing_fund_employee": 0,
    "pension_employer": 0,
    "medical_employer": 0,
    "unemployment_employer": 0,
    "work_injury_employer": 0,
    "maternity_employer": 0,
    "housing_fund_employer": 0,
    "taxable_income_current_month": 0,
    "cumulative_taxable_income": 0,
    "individual_income_tax": 0,
    "special_additional_deduction": 0,
    "after_tax_adjustment": 0,
    "social_insurance_calculation_method": "manual",
    "housing_fund_calculation_method": "manual",
    "iit_calculation_method": "manual"
  }
}
```

China required first-rollout capabilities:

- Full payroll sheet and workflow support.
- City-level parameter support for Shanghai, Nanjing, Xi'an, and Wuhu.
- Employee and employer-side social insurance/housing fund fields.
- Individual income tax fields.
- Employer cost reporting.
- PDF payslip and email notice support.

Compliance note: China statutory calculations vary by city and policy period. Manual or parameter-assisted entries are acceptable initially; automation requires validated city parameter tables.

---

## 11. `payroll_parameters.json`

Stores effective payroll rule/parameter versions by country/entity/city where applicable.

Example:

```json
{
  "parameter_id": "PARAM-CN-SHANGHAI-2026-06-V001",
  "rule_version_id": "RULE-CN-SHANGHAI-2026-06-V001",
  "country_code": "CN",
  "entity_id": "ENT-0005",
  "city_code": "SHANGHAI",
  "currency": "CNY",
  "effective_start_date": "2026-06-01",
  "effective_end_date": null,
  "parameter_type": "city_social_insurance",
  "calculation_method": "manual",
  "rounding_policy": {
    "amount_decimal_places": 2,
    "rounding_method": "standard"
  },
  "values": {
    "pension_employee_rate": null,
    "pension_employer_rate": null,
    "medical_employee_rate": null,
    "medical_employer_rate": null,
    "housing_fund_employee_rate": null,
    "housing_fund_employer_rate": null
  },
  "status": "draft",
  "approved_by": null,
  "approved_at": null,
  "source_reference": "Manual setup pending official validation",
  "created_by": "USR-0001",
  "created_at": "2026-06-23T09:00:00+09:00",
  "updated_by": "USR-0001",
  "updated_at": "2026-06-23T09:00:00+09:00",
  "notes": ""
}
```

Parameter scopes:

- Japan: country/entity level, plus payroll item/rate versions.
- Singapore: country/entity level, CPF fields from launch; automation later.
- China: country/entity/city level for Shanghai, Nanjing, Xi'an, and Wuhu.

Validation rules:

- Parameters used in finalized payroll should not be edited in place.
- Create a new version for changed parameters.
- Parameter approval should be audited.

---

## 12. `payroll_notices.json`

One record represents an email notice event for one employee payroll row and one notice version.

Example:

```json
{
  "notice_id": "NOTICE-PR-JP-2026-06-EMP-0001-001",
  "payroll_record_id": "PR-JP-2026-06-EMP-0001-V001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "notice_type": "first_notice",
  "notice_version": 1,
  "channel": "system_email",
  "recipient_employee_id": "EMP-0001",
  "recipient_email_snapshot": "employee@example.com",
  "email_subject_snapshot": "Payroll Notice 2026-06",
  "email_body_template_id": "TPL-PAYSLIP-JP-001",
  "payslip_document_id": "PDF-PR-JP-2026-06-EMP-0001-001",
  "status": "sent",
  "queued_by": "USR-0001",
  "queued_at": "2026-06-23T10:00:00+09:00",
  "sent_by": "USR-0001",
  "sent_at": "2026-06-23T10:01:00+09:00",
  "failed_at": null,
  "failure_reason": "",
  "employee_acknowledged_at": null,
  "notes": ""
}
```

Rules:

- First notice and final notice must be distinguishable.
- Email sending must be audited.
- Failed email delivery must be visible to HR.
- Sending final notice should not overwrite first notice history.
- Do not store email passwords in JSON data files. Sender configuration should use environment variables or a protected configuration file later.

---

## 13. `payslip_documents.json`

One record represents a generated payslip file, normally PDF.

Example:

```json
{
  "payslip_document_id": "PDF-PR-JP-2026-06-EMP-0001-001",
  "payroll_record_id": "PR-JP-2026-06-EMP-0001-V001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "employee_id": "EMP-0001",
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "payroll_month": "2026-06",
  "document_type": "payslip_pdf",
  "document_version": 1,
  "notice_type": "first_notice",
  "file_name": "payslip_EMP-0001_2026-06_v1.pdf",
  "file_path": "database/payslips/JP/2026-06/payslip_EMP-0001_2026-06_v1.pdf",
  "sha256": "",
  "generated_by": "USR-0001",
  "generated_at": "2026-06-23T09:59:00+09:00",
  "download_count": 0,
  "latest_downloaded_at": null,
  "status": "active",
  "notes": ""
}
```

Rules:

- PDF regeneration creates a new document version.
- Old versions are retained.
- Downloads should be audited or counted at minimum.
- Sensitive PDF files should not be exposed without authenticated access.

---

## 14. `employee_feedback.json`

One record represents employee feedback on a payroll notice/payslip.

Example:

```json
{
  "feedback_id": "FB-PR-JP-2026-06-EMP-0001-001",
  "payroll_record_id": "PR-JP-2026-06-EMP-0001-V001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "employee_id": "EMP-0001",
  "notice_id": "NOTICE-PR-JP-2026-06-EMP-0001-001",
  "feedback_type": "question",
  "feedback_status": "submitted",
  "message": "Please check unpaid leave days.",
  "submitted_at": "2026-06-23T11:00:00+09:00",
  "reviewed_by": null,
  "reviewed_at": null,
  "resolution": "",
  "correction_required_flag": false,
  "correction_payroll_record_version": null,
  "closed_by": null,
  "closed_at": null
}
```

Feedback statuses:

```text
submitted
under_review
accepted_correction_required
rejected_no_change
corrected
closed
```

Rules:

- Accepted employee feedback that changes payroll must create manual adjustment/correction records.
- Rejected feedback should keep HR explanation.
- Feedback history is retained.

---

## 15. `payroll_confirmations.json`

Two-level confirmation records for payroll close.

Example:

```json
{
  "confirmation_id": "CONF-PB-JP-ENT-0001-2026-06-001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "confirmation_level": "first_confirmation",
  "confirmed_by": "USR-0001",
  "confirmed_at": "2026-06-24T09:00:00+09:00",
  "confirming_role_snapshot": "payroll_maker",
  "admin_dual_confirm_flag": false,
  "checklist": {
    "employee_count_checked": true,
    "warnings_reviewed": true,
    "manual_adjustments_reviewed": true,
    "employer_cost_reviewed": true,
    "employee_feedback_closed": true,
    "payslip_ready": true
  },
  "comment": "First confirmation completed.",
  "created_at": "2026-06-24T09:00:00+09:00"
}
```

Rules:

- Finalization requires first and second confirmation.
- Admin may perform both confirmations only if permission allows.
- Admin dual confirmation still creates two separate records.
- Confirmation actions are audit-triggering events.

---

## 16. `payment_records.json`

Payment records track payment preparation and completion. Initial MVP can use manual payment status; bank file export can be later.

Example:

```json
{
  "payment_record_id": "PAY-PB-JP-ENT-0001-2026-06-001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "payroll_month": "2026-06",
  "currency": "JPY",
  "payment_method": "bank_transfer",
  "payment_date": "2026-07-25",
  "employee_count": 20,
  "total_net_pay": 6000000,
  "total_employer_cost": 7200000,
  "payment_status": "prepared",
  "prepared_by": "USR-0001",
  "prepared_at": "2026-06-25T09:00:00+09:00",
  "approved_by": null,
  "approved_at": null,
  "paid_by": null,
  "paid_at": null,
  "bank_file_document_id": null,
  "manual_payment_reference": "",
  "notes": ""
}
```

Payment statuses:

```text
not_prepared
prepared
approved
paid
failed
cancelled
```

Rules:

- Payment amount should reconcile to finalized payroll rows.
- Marking paid should be audited.
- Bank file export should be versioned and audited when added.

---

## 17. `payroll_import_runs.json`

Tracks source data loading from EmployeeAdmin, Timesheet/attendance, or manual import.

Example:

```json
{
  "import_run_id": "IMP-PB-JP-ENT-0001-2026-06-001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "import_type": "timesheet_attendance",
  "source_system": "TAC-timesheet",
  "source_file_name": "",
  "source_record_count": 20,
  "success_count": 20,
  "warning_count": 0,
  "error_count": 0,
  "warnings": [],
  "errors": [],
  "imported_by": "USR-0001",
  "imported_at": "2026-06-23T09:05:00+09:00",
  "notes": ""
}
```

Import types:

```text
employee_master
salary_master
attendance
timesheet_attendance
manual_adjustment
country_parameter
```

Rules:

- Source import should never silently overwrite finalized payroll rows.
- Import errors must be visible before calculation/finalization.

---

## 18. `audit_logs.json`

Audit records are append-only and read-only from application UI/API except system appends.

Required fields from project audit rules:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Recommended v2 audit record:

```json
{
  "audit_id": "AUD-20260623-000001",
  "module": "salary",
  "submodule": "payroll_batch",
  "record_id": "PB-JP-ENT-0001-2026-06-V001",
  "batch_id": "PB-JP-ENT-0001-2026-06-V001",
  "payroll_record_id": null,
  "country_code": "JP",
  "entity_id": "ENT-0001",
  "employee_id": null,
  "action": "create_batch",
  "user": "USR-0001",
  "user_display_snapshot": "System Admin",
  "timestamp": "2026-06-23T09:00:00+09:00",
  "before_value": null,
  "after_value": {
    "status": "batch_created"
  },
  "reason": "Create June payroll batch",
  "source_ip": "127.0.0.1",
  "request_id": "REQ-20260623-000001"
}
```

Audit-triggering events include:

- salary master create/update/deactivate
- parameter create/update/approve/deactivate
- payroll batch create/void/archive
- data import
- calculation run
- manual adjustment
- employee feedback resolution
- payslip PDF generation/download
- first notice email send
- final notice email send
- first confirmation
- second confirmation
- finalization
- payment preparation
- mark paid
- post-finalization correction/replacement

---

## 19. Calculation summary formulas

### 19.1 Common formula

```text
gross_pay = base_pay
          + overtime_pay
          + holiday_work_pay
          + late_night_pay
          + allowance_taxable_total
          + allowance_non_taxable_total
          + bonus_total
          + commission_total
          + retroactive_pay
          + other_earning_total

employee_deduction_total = statutory_deduction_total
                         + tax_total
                         + social_insurance_employee_total
                         + manual_deduction_total
                         + other_deduction_total

net_pay = gross_pay - employee_deduction_total

total_employer_cost = gross_pay
                    + employer_social_insurance_total
                    + employer_tax_or_levy_total
                    + employer_benefit_cost_total
                    + employer_other_cost_total
```

Country modules may add more detailed formulas, but final row totals should map back to these common totals.

### 19.2 Manual override rule

Any manual override must store:

- adjusted field name
- before amount
- after amount
- adjustment amount
- reason
- adjusted by
- adjusted at
- approval status if required

Manual override example inside `manual_adjustments`:

```json
{
  "adjustment_id": "ADJ-PR-JP-2026-06-EMP-0001-001",
  "field_name": "unpaid_leave_days",
  "before_value": 1,
  "after_value": 0,
  "amount_impact": 15000,
  "reason": "Employee feedback accepted; leave record was incorrect.",
  "adjusted_by": "USR-0001",
  "adjusted_at": "2026-06-23T14:00:00+09:00",
  "approval_status": "approved"
}
```

---

## 20. Security and privacy requirements

Minimum requirements:

- No unauthenticated payroll access.
- Role-based permission checks.
- Entity/country scope checks.
- No-store/cache-control headers on payroll pages and downloads.
- Mask full bank account numbers in normal views.
- Do not expose national ID/My Number/full identity numbers in payroll rows.
- Restrict PDF payslip download to authorized HR/payroll users and the target employee in future employee self-service.
- Audit exports/downloads/sensitive actions.

Suggested permissions:

- `salary.access`
- `salary.view`
- `salary.batch.create`
- `salary.calculate`
- `salary.adjust`
- `salary.review`
- `salary.confirm.first`
- `salary.confirm.second`
- `salary.notice.send`
- `salary.payslip.download`
- `salary.finalize`
- `salary.payment.prepare`
- `salary.payment.mark_paid`
- `salary.parameters.manage`
- `salary.salary_master.manage`
- `salary.audit.view`
- `salary.jp.manage`
- `salary.sg.manage`
- `salary.cn.manage`

---

## 21. Migration from v1 files

The old files can remain during transition:

- `salary_records.json`
- `employees.json`
- `audit_logs.json`

Migration direction:

1. Keep `audit_logs.json` and extend the schema append-only.
2. Treat old `salary_records.json` as legacy test data unless explicitly migrated.
3. Create new v2 files rather than forcing all country data into one flat record.
4. Add migration notes for any historical salary records that must be retained.

Old `salary_records.json` fields map approximately as follows:

| Old field | New location |
| --- | --- |
| `id` | country payroll row `payroll_record_id` |
| `employee_id` | `employee_id` |
| `salary_month` | `payroll_month` |
| `country` | `country_code` |
| `currency` | `currency` |
| `base_salary` | `base_pay` |
| `position_allowance` | `allowance_taxable_total` or detailed allowance list |
| `commute_allowance` | JP commuting allowance or common allowance fields |
| `housing_allowance` | `allowance_taxable_total` or detailed allowance list |
| `other_allowance` | `other_earning_total` |
| `overtime_pay` | `overtime_pay` |
| `gross_salary` | `gross_pay` |
| `health_insurance` | country employee health/social insurance field |
| `pension_insurance` | country employee pension/social insurance field |
| `employment_insurance` | country employee employment/unemployment insurance field |
| `income_tax` | `tax_total` or country tax field |
| `resident_tax` | JP `resident_tax` |
| `other_deduction` | `other_deduction_total` |
| `total_deductions` | `deduction_total` |
| `net_salary` | `net_pay` |
| `status` | `status` |

---

## 22. Next implementation documents

After this v2 data schema, create or update:

1. `docs/Salary_Table_Specification_JP.md`
2. `docs/Salary_Table_Specification_SG.md`
3. `docs/Salary_Table_Specification_CN.md`
4. Payroll workflow UI plan.
5. Payroll email sender and PDF payslip generation plan.
6. Payroll calculation test case pack for JP/SG/CN.

---

## 23. 2026-06-24 implementation alignment

The local MVP now implements the roadmap steps 1-6 in dependency-free form:

- `salary_profiles_with_employeeadmin()` attempts EmployeeAdmin payroll employee loading and explicitly records salary-master fallback/import warnings in `payroll_import_runs.json`.
- v2 routes enforce User_admin-compatible permission checks in strict mode while keeping soft local development mode. Existing `payroll.*` permissions are primary; `salary.*` permissions are accepted as TAC-salary aliases.
- Payment, reports, payslip text documents, first/final notices, employee feedback, payroll parameters, and manual record field updates have API/UI coverage.
- Payslips are currently text documents with metadata and SHA-256 hash. True PDF generation remains deferred until a PDF library/dependency is approved.
- Notice sending uses SMTP environment variables when configured; otherwise records `manual_send_pending` notices and does not fake sent status.
- JP/SG/CN country fields are manual/parameter-assisted only. Statutory automation remains blocked pending rule validation.
- Payment close now aligns batch, payment record, and row-level payment statuses; prepared/paid/archived batches support audited payment CSV export, and paid batches can be archived with locked read-only history metadata.

## 24. 2026-06-24 country/entity module fields

The runtime now treats each visible country payroll system as a scoped module over the shared payroll core. These fields should be present on new batch, salary master, parameter, and country payroll row records where applicable:

```text
country_code
legal_entity_id
entity_id
payroll_system_code
payroll_area_code
rule_version_id
```

Country module defaults:

| `country_code` | `payroll_system_code` | `payroll_area_code` | Scoped entities | Currency |
| --- | --- | --- | --- | --- |
| `JP` | `JP_PAYROLL` | `JP_MONTHLY` | `ENT-0001` | JPY |
| `SG` | `SG_PAYROLL` | `SG_MONTHLY` | `ENT-0002` | SGD |
| `CN` | `CN_PAYROLL` | `CN_MONTHLY` | `ENT-0003`, `ENT-0004`, `ENT-0005` | CNY |

Rules:

- `entity_id` and `legal_entity_id` should match the payroll legal employer in this MVP.
- `payroll_system_code` is derived from `country_code` and controls the visible country payroll module.
- `payroll_area_code` starts as one monthly area per country and can later split by entity/pay group if needed.
- `rule_version_id` defaults to `RULE-<country>-<YYYY-MM>-V001` unless a specific validated rule version is selected.
- Country module UI routes `/payroll/jp`, `/payroll/sg`, and `/payroll/cn` must call APIs with `country_code` scope so lists, entity selectors, reports, payslips, notices, feedback, parameters, and audit views default to the selected country.
