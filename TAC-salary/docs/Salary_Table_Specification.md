# TAC-salary APAC Payroll Table Specification v2

Last updated: 2026-06-23

## 1. Purpose

This specification defines the first formal APAC payroll sheet design for TAC-salary. It replaces the earlier single Japan/manual salary table concept.

The system must support:

- Japan payroll with deeper haken/dispatch and overtime-related requirements;
- Singapore payroll with CPF fields from launch, initially manual/parameter-assisted;
- China payroll with city-level social insurance and housing fund fields for Shanghai, Nanjing, Xi'an, and Wuhu;
- employee net pay calculation;
- employer cost reporting;
- first and final payroll notices by system email;
- downloadable PDF payslips;
- two-level payroll finalization;
- audit history for all payroll changes.

---

## 2. Payroll sheet unit

A payroll sheet is created by:

```text
country_code + entity_id + payroll_month + payroll_type
```

Example:

```text
JP + ENT-0001 + 2026-06 + regular_monthly
SG + ENT-0002 + 2026-06 + regular_monthly
CN + ENT-0003 + 2026-06 + regular_monthly
```

Validation:

- Do not create two active regular monthly batches for the same country/entity/month.
- Voided or replacement batches must remain visible in history.
- Finalized batches are locked from direct edits.

---

## 3. Common payroll sheet columns

These columns should exist for JP/SG/CN payroll sheets.

### 3.1 Identity and control fields

| Field | Required | Notes |
| --- | --- | --- |
| `payroll_record_id` | Yes | Unique employee/month/batch record ID. |
| `batch_id` | Yes | Payroll batch ID. |
| `payroll_month` | Yes | `YYYY-MM`. |
| `country_code` | Yes | `JP`, `SG`, or `CN`. |
| `entity_id` | Yes | Legal employer from Master Data. |
| `entity_code` | Yes | Snapshot from Master Data. |
| `currency` | Yes | `JPY`, `SGD`, `CNY`. |
| `employee_id` | Yes | Stable EmployeeAdmin employee ID. |
| `employee_no` | Yes | Snapshot for business display. |
| `employee_name` | Yes | Snapshot for business display. |
| `employment_type` | Yes | Regular, contract, part-time, haken/dispatched, etc. |
| `worker_type` | Yes | Direct, dispatched/haken, foreign national flags where needed. |
| `department` | Recommended | Snapshot. |
| `work_city` | Country-dependent | Required for China, useful for all. |
| `join_date` | Recommended | Used for monthly eligibility checks. |
| `resign_date` | Optional | Used for monthly eligibility checks. |
| `status` | Yes | Row status. |

### 3.2 Source data columns

| Field | Required | Notes |
| --- | --- | --- |
| `salary_profile_id` | Yes | Salary master version used. |
| `attendance_days` | Recommended | From timesheet/attendance or manual entry. |
| `paid_leave_days` | Recommended | For validation and employee feedback. |
| `unpaid_leave_days` | Recommended | Affects deduction. |
| `absence_days` | Recommended | Affects deduction. |
| `standard_working_hours` | Country-dependent | Important for Japan overtime. |
| `actual_working_hours` | Country-dependent | Important for Japan overtime. |
| `overtime_hours` | Country-dependent | Required for Japan; optional/manual elsewhere. |
| `late_night_overtime_hours` | JP required | Japan-specific. |
| `holiday_work_hours` | JP required | Japan-specific. |
| `source_warning_count` | Recommended | Missing/inconsistent source data count. |

### 3.3 Earnings columns

| Field | Required | Notes |
| --- | --- | --- |
| `base_salary` | Yes | Base monthly/hourly amount. |
| `position_allowance` | Optional | Fixed or monthly input. |
| `commuting_allowance` | Optional | Tax treatment differs by country. |
| `housing_allowance` | Optional | Common APAC allowance. |
| `overtime_pay` | Country-dependent | Required for Japan. |
| `late_night_overtime_pay` | JP required | Japan late-night overtime. |
| `holiday_work_pay` | JP required | Japan holiday/statutory holiday work. |
| `bonus` | Optional | Country-specific tax treatment later. |
| `other_taxable_earning` | Optional | Manual/parameter-assisted. |
| `other_non_taxable_earning` | Optional | Must be separated from taxable earnings. |
| `gross_pay` | Yes | Total employee earnings before deductions. |
| `taxable_gross_pay` | Yes | Gross pay after non-taxable treatment. |

### 3.4 Employee deduction columns

| Field | Required | Notes |
| --- | --- | --- |
| `income_tax` | Yes | Manual/parameter-assisted until validated. |
| `resident_tax` | JP/CN optional | Japan resident tax; China can use IIT in country fields. |
| `health_insurance` | JP/CN optional | Employee side. |
| `pension` | JP/CN optional | Employee side. |
| `employment_insurance` | JP/CN optional | Employee side. |
| `cpf_employee` | SG required field | Manual value acceptable initially. |
| `china_social_insurance_employee` | CN required field | Can aggregate city-level employee social insurance. |
| `china_housing_fund_employee` | CN required field | Manual/parameter-assisted. |
| `salary_advance_repayment` | Optional | Future payroll operations. |
| `other_deduction` | Optional | Must require reason when non-zero. |
| `total_employee_deductions` | Yes | Sum of employee deductions. |

### 3.5 Employer cost columns

| Field | Required | Notes |
| --- | --- | --- |
| `base_employer_cost` | Yes | Usually starts with gross pay. |
| `health_insurance_employer` | JP/CN optional | Employer side. |
| `pension_employer` | JP/CN optional | Employer side. |
| `employment_insurance_employer` | JP/CN optional | Employer side. |
| `workers_comp_employer` | JP/CN optional | Employer side. |
| `child_care_contribution_employer` | JP optional | Japan employer-side contribution placeholder. |
| `cpf_employer` | SG required field | Manual value acceptable initially. |
| `china_social_insurance_employer` | CN required field | Can aggregate employer social insurance. |
| `china_housing_fund_employer` | CN required field | Manual/parameter-assisted. |
| `levy_or_local_charge` | SG/CN optional | For SG foreign worker/local charges or CN local charges if needed. |
| `other_employer_cost` | Optional | Must require reason when non-zero. |
| `total_employer_cost` | Yes | Gross pay + employer costs. |

### 3.6 Result and payment columns

| Field | Required | Notes |
| --- | --- | --- |
| `manual_adjustments_total` | Yes | Sum of approved manual adjustments. |
| `net_pay` | Yes | Employee payable amount. |
| `payment_method` | Yes | Usually bank transfer. |
| `payment_amount` | Yes | Usually equals net pay. |
| `payment_status` | Yes | Row-level payment status. |
| `paid_at` | Optional | Payment completion timestamp. |

---

## 4. Country-specific columns

## 4.1 Japan payroll sheet

Japan should be the deepest first implementation.

Required Japan-specific field groups:

1. Work time and overtime:
   - standard working days/hours;
   - actual working days/hours;
   - overtime hours;
   - late-night hours;
   - holiday work hours;
   - statutory holiday work hours;
   - overtime/late-night/holiday rate snapshots.

2. Allowance tax treatment:
   - commuting allowance taxable amount;
   - commuting allowance non-taxable amount;
   - other taxable/non-taxable allowance split.

3. Social insurance/tax placeholders:
   - health insurance standard monthly remuneration;
   - pension standard monthly remuneration;
   - care insurance applicable flag;
   - employment insurance flag;
   - resident tax city;
   - income tax manual/parameter value.

4. Haken/dispatch references:
   - dispatch client ID/name snapshot;
   - assignment ID;
   - worksite/project reference;
   - billing reference where needed later.

5. Payslip suitability:
   - Japanese display labels;
   - first notice and final notice version;
   - PDF download audit.

Japan calculation note:

- Overtime/late-night/holiday calculation should be explainable and source-linked.
- Statutory deduction automation must be validated before production use.

## 4.2 Singapore payroll sheet

Singapore first rollout should include complete fields but allow manual CPF values initially.

Required Singapore-specific field groups:

1. CPF and contribution fields:
   - CPF applicable flag;
   - CPF employee manual amount;
   - CPF employer manual amount;
   - ordinary wage amount;
   - additional wage amount;
   - employee/employer rate snapshot placeholders.

2. Employee status fields:
   - citizen/PR/foreign status manual category;
   - tax resident flag;
   - foreign worker levy manual amount if applicable;
   - skill development levy manual amount if applicable.

3. Payment/report fields:
   - SGD payment amount;
   - Singapore bank/payment snapshot;
   - IRAS/reporting category placeholder.

Singapore calculation note:

- CPF fields exist from launch.
- Full CPF automation is a later phase after rule validation.

## 4.3 China payroll sheet

China first rollout must support city-level parameters.

Required China-specific field groups:

1. City configuration:
   - work city;
   - social insurance city;
   - housing fund city;
   - supported cities: Shanghai, Nanjing, Xi'an, Wuhu.

2. Employee-side social insurance/housing fund:
   - pension employee;
   - medical employee;
   - unemployment employee;
   - housing fund employee.

3. Employer-side social insurance/housing fund:
   - pension employer;
   - medical employer;
   - unemployment employer;
   - work injury employer;
   - maternity employer;
   - housing fund employer.

4. IIT/tax placeholders:
   - individual income tax;
   - cumulative taxable income YTD;
   - cumulative tax paid YTD;
   - special additional deduction manual amount.

China calculation note:

- Social insurance and housing fund vary by city and policy year.
- Manual/parameter-assisted entries are acceptable before validated automation.

---

## 5. Row statuses

Recommended row status values:

- `draft`
- `data_loaded`
- `calculated`
- `needs_review`
- `adjusted`
- `first_notice_sent`
- `feedback_received`
- `corrected`
- `final_notice_sent`
- `ready_for_confirmation`
- `finalized`
- `payment_prepared`
- `paid`
- `voided`

Rules:

- A row cannot be `finalized` before the batch is in final review/confirmation flow.
- A row cannot be paid before the batch is finalized or payment-approved.
- Direct row edits after finalization are not allowed.

---

## 6. Batch statuses

Recommended batch status values:

1. `draft_created`
2. `data_loaded`
3. `calculated`
4. `hr_review`
5. `first_notice_sent`
6. `employee_feedback`
7. `corrected`
8. `final_review`
9. `first_confirmed`
10. `second_confirmed`
11. `finalized`
12. `payment_prepared`
13. `paid`
14. `archived`
15. `voided`

Two-level confirmation:

- First confirmation records user, timestamp, and comment.
- Second confirmation records user, timestamp, and comment.
- Admin can perform both if permitted, but the system must record two separate audit actions.

---

## 7. Calculation rules

Common result formula:

```text
gross_pay = base_salary
          + fixed_allowances
          + variable_earnings
          + overtime/holiday/bonus earnings
          + other taxable/non-taxable earnings

employee_deductions = statutory_employee_deductions
                    + payroll_deductions
                    + other approved deductions

net_pay = gross_pay - employee_deductions + manual_adjustments_total

employer_cost = gross_pay
              + employer_statutory_contributions
              + employer CPF / city social insurance / housing fund
              + other employer costs
```

Each payroll record should preserve:

- source data snapshot;
- rule/parameter version;
- calculated timestamp;
- calculated user/system;
- warnings;
- manual override reason.

---

## 8. Required validations

Payroll batch validations:

- `country_code`, `entity_id`, and `payroll_month` are required.
- Active batch uniqueness by country/entity/month/payroll type.
- Entity must exist in Master Data and be active.
- Currency must match entity/country unless approved exception exists.
- China payroll must have city fields.

Payroll row validations:

- `employee_id` is required and should exist in EmployeeAdmin.
- Employee snapshot must include legal entity and employee type.
- Salary Profile must be active for payroll month.
- Non-zero manual adjustment must have reason and user.
- Negative net pay requires explicit warning/approval.
- Missing bank/payment data must block finalization or require approved manual exception.

Notice/payment validations:

- First notice cannot be sent before calculation.
- Final notice should be sent after corrections/final review.
- Finalization requires two confirmation actions.
- Payment preparation requires finalized batch.

---

## 9. Compliance notes

- Japan payroll rules, Singapore CPF, and China social insurance/housing fund/IIT rules must be validated against official sources and/or qualified payroll advisors before production automation.
- Until validated, statutory deductions and employer contributions should be manually maintained or parameter-assisted with human approval.
- Audit records must be retained and must not be deleted.
- Important payroll and haken compliance decisions should be stored in `memory/decisions.md`.

---

## 10. 2026-06-24 MVP implementation notes

The current local implementation supports the first six roadmap steps as an auditable MVP:

1. Employee loading no longer blocks on a missing helper. EmployeeAdmin payroll snapshots are attempted when a session cookie is available; otherwise salary-master fallback is explicit and import-run audited.
2. User_admin-compatible route permissions use `payroll.*` as the primary namespace and accept planned `salary.*` aliases inside TAC-salary.
3. Payment preparation/paid status and net-pay/employer-cost reports are wired to API and UI.
4. Payslip generation/download is dependency-free text for now; true PDF generation is a deferred requirement.
5. First/final notices are recorded and audited; without SMTP configuration they remain `manual_send_pending`.
6. JP/SG/CN country-specific payroll fields are available for manual/parameter-assisted input, including SG CPF fields and CN city code validation for Shanghai, Nanjing, Xi'an, and Wuhu.
7. Payment close now keeps row-level payment statuses aligned with batch/payment records, supports audited payment CSV export, and archives paid batches as locked read-only history.

Statutory calculations remain manual/parameter-assisted until validated by official sources or payroll specialists.
