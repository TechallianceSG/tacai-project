# TAC-salary APAC Payroll System Initial Plan

Last updated: 2026-06-24


## 2026-06-24 update — country payroll system entry model

Following the latest product/architecture decision, the user-facing salary product is now organized as three country payroll systems on top of the shared payroll core:

- **日本薪资计算 / Japan Payroll** — default scope `country_code = JP`, `payroll_system_code = JP_PAYROLL`, `payroll_area_code = JP_MONTHLY`.
- **新加坡薪资计算 / Singapore Payroll** — default scope `country_code = SG`, `payroll_system_code = SG_PAYROLL`, `payroll_area_code = SG_MONTHLY`.
- **中国薪资计算 / China Payroll** — default scope `country_code = CN`, `payroll_system_code = CN_PAYROLL`, `payroll_area_code = CN_MONTHLY`.

Product rule: when a user enters a country payroll system, the UI and API queries default to that country. Entity selectors show only legal entities for that country; China payroll shows only China entities (`ENT-0003`, `ENT-0004`, `ENT-0005`) and China-related salary fields by default. The large workflow remains consistent across countries, but country fields, statutory parameters, calculation rules, reports, and future permissions remain country-specific.

UI/UX rule: TAC-salary should visually align with TAC-employeeadmin for operator consistency: navy header, pill navigation, card/object-page layout, consistent form grids, rounded inputs, status pills, query/filter panel, and responsive table behavior.

## 1. Planning position

TAC-salary should be rebuilt as a core APAC payroll product, not as a small Japan-only salary table.

The target business scope is:

- Japan payroll calculation and dispatch/haken salary operations.
- Singapore payroll calculation.
- China payroll calculation.
- Around 50 employees at the initial stage, with later growth expected.
- HR/Payroll users need a simple monthly workflow: prepare data, create monthly payroll sheet, calculate, review, correct, notify employees, handle feedback, finalize, pay, and archive payroll records.

This plan should be viewed through four expert lenses:

1. **APAC IT architect** — modular system, country rule separation, auditability, integration readiness.
2. **Payroll/compensation expert** — country-specific salary items, statutory deduction differences, month-end control.
3. **IT product expert** — simple HR workflow, clear status, low learning cost, field completeness.
4. **Process expert** — payroll close discipline, maker/checker review, employee feedback loop, final record retention.

Important compliance note: statutory payroll rules for Japan, Singapore, and China must be validated against official sources and/or a qualified payroll advisor before production payroll close. The system should support configuration and evidence retention, but legal interpretation must remain human-approved.

---

## 2. Core design principles

### 2.1 From one salary table to APAC payroll platform

The previous Japan-only salary table design is too limited for the new goal. TAC-salary should be redesigned around a shared payroll core plus independent country modules:

```text
TAC-salary/
  salary-core/   shared payroll batch, employee snapshot, workflow, audit, payslip, export logic
  salary-jp/     Japan payroll items and calculation rules
  salary-sg/     Singapore payroll items and calculation rules
  salary-cn/     China payroll items and calculation rules
```

### 2.2 Keep the monthly operation simple

The system should not become an enterprise payroll ERP at MVP stage. The first usable workflow should be:

1. Maintain payroll parameters and salary master data.
2. Create monthly empty payroll sheet by country/entity/month.
3. Run **Payroll Calculation**.
4. HR reviews and manually adjusts if needed.
5. Save draft and send first payslip/payroll notice to employees.
6. Employees provide feedback if anything is wrong.
7. HR corrects validated issues.
8. Finalize payroll.
9. Execute salary payment outside or through future bank file export.
10. Save final payroll record and audit history.

### 2.3 Country modules must be independent but consistent

Japan, Singapore, and China must have independent payroll sheets and field sets because their payroll requirements differ. However, common concepts should be consistent:

- payroll month
- country
- entity/legal employer
- employee ID
- employee snapshot
- earnings
- deductions
- employer cost
- net pay
- workflow status
- audit logs
- payslip version
- manual adjustment reason

### 2.4 Keep calculations explainable

Every calculated number should be traceable:

- source data used
- parameter/rule version used
- manual override amount and reason
- before/after values for audit
- calculation timestamp and user

---

## 3. Recommended system modules

## 3.1 salary-core — shared payroll engine and workflow

Shared functions:

- Payroll period management.
- Payroll batch creation by country/entity/month.
- Employee snapshot capture at payroll calculation time.
- Common payroll workflow status.
- Common payslip generation status and versioning.
- Manual adjustment framework.
- Audit logging.
- Import/export templates.
- Integration interfaces with EmployeeAdmin, Timesheet, Leave/Attendance, Reimbursement if needed later.

Suggested shared objects:

- `payroll_period`
- `payroll_batch`
- `payroll_employee_snapshot`
- `payroll_line_common`
- `payroll_adjustment`
- `payslip_notice`
- `payroll_audit_log`
- `payroll_rule_version`

## 3.2 salary-jp — Japan payroll module

Japan module should support:

- Japan legal entity payroll.
- Dispatch/haken employee payroll needs.
- Standard working time, overtime, late-night overtime, holiday work, and statutory holiday concepts.
- Allowances and taxable/non-taxable items.
- Social insurance, pension, employment insurance, income tax, resident tax placeholders/configuration.
- Commuting allowance and other Japan-specific treatment.
- Payslip fields suitable for Japanese employees and dispatch business records.

Initial calculation depth should be controlled: support the data structure and manual/parameter-driven calculation first; automate statutory rules only after rule sources and validation are confirmed.

## 3.3 salary-sg — Singapore payroll module

Singapore module should support:

- Singapore legal entity payroll.
- Monthly salary, allowances, overtime or additional pay where applicable.
- Employee CPF/employer CPF configuration if applicable by employee status.
- Levy/foreign-worker related fields as future-ready optional fields where relevant.
- Tax reporting support fields, while annual filing automation can be later phase.
- SGD currency and Singapore bank/payment fields.

## 3.4 salary-cn — China payroll module

China module should support:

- China legal entity payroll.
- City-based social insurance/housing fund parameter differences.
- Individual income tax taxable income handling and cumulative tax method support as a later controlled rule.
- Allowances, bonuses, overtime, leave deductions, and special additional deduction placeholders if needed.
- CNY currency and China bank/payment fields.

---

## 4. Monthly payroll process design

## 4.1 Payroll status flow

Recommended status model:

1. `not_started` — period exists but no batch created.
2. `draft_created` — empty payroll sheet created.
3. `data_loaded` — employee/salary/attendance source data loaded.
4. `calculated` — system calculation executed.
5. `hr_review` — HR is checking and editing.
6. `first_notice_sent` — first payslip/payroll notice sent to employees.
7. `employee_feedback` — waiting for or reviewing employee feedback.
8. `corrected` — HR made validated corrections.
9. `final_review` — payroll owner checks final version.
10. `finalized` — payroll locked for payment.
11. `payment_prepared` — bank/payment export or manual payment list prepared.
12. `paid` — payment completed.
13. `archived` — payroll record retained and closed.
14. `voided` — cancelled/replaced batch, retained for audit.

Rules:

- Finalized/paid payroll records must not be silently edited.
- Corrections after finalization should create an adjustment record or replacement version.
- Voided records remain visible in audit/history.

## 4.2 Simple HR screen flow

Recommended screens for MVP:

1. **Payroll Dashboard**
   - Open periods by country/entity/month.
   - Status summary.
   - Missing data warnings.
   - Pending employee feedback count.

2. **Payroll Parameters**
   - Country parameter sets.
   - Entity parameter sets.
   - Effective date and rule version.
   - Manual approval flag for parameter changes.

3. **Employee Salary Master**
   - Base salary.
   - Salary type.
   - Fixed allowances.
   - Bank/payment details reference.
   - Country-specific payroll flags.

4. **Create Monthly Payroll**
   - Select country, entity, payroll month.
   - Select employee population.
   - Create empty payroll sheet.

5. **Payroll Sheet**
   - Table view with one row per employee.
   - Run calculation.
   - Show source data, calculated fields, manual adjustments, net pay.
   - Bulk warnings and row-level warnings.

6. **Payroll Detail/Object Page**
   - One employee/month detail.
   - Calculation breakdown.
   - Adjustment history.
   - Employee feedback records.
   - Payslip notice status.

7. **Payslip Notice Center**
   - Send first notice.
   - Track employee acknowledgement/feedback.
   - Send final notice.

8. **Payroll Close & Payment**
   - Final review checklist.
   - Lock payroll.
   - Export payment list or bank file later.
   - Mark paid.

9. **Audit Viewer**
   - Read-only audit logs.
   - Filter by batch, employee, country, user, action.

---

## 5. Data source and integration plan

## 5.1 Required source data

TAC-salary should not ask HR to re-enter everything every month. It should pull or import:

- **Employee master** from EmployeeAdmin:
  - employee ID
  - employee number
  - name
  - entity/legal employer
  - work country
  - employment type
  - join/resign date
  - department/project/client if relevant
  - bank/payment information

- **Salary master** from TAC-salary:
  - base salary
  - salary type
  - fixed allowances
  - country payroll flags
  - tax/social insurance flags
  - effective date

- **Attendance/timesheet data** from Timesheet or import:
  - working days/hours
  - absence days
  - paid leave/unpaid leave
  - overtime hours
  - late-night overtime hours for Japan
  - holiday work hours

- **Manual input/adjustment data**:
  - special allowance
  - bonus
  - deduction
  - reimbursement taxable adjustment if needed
  - prior-month correction

## 5.2 Snapshot rule

Payroll records must keep snapshots. Even if EmployeeAdmin or salary master changes later, the historical payroll record should preserve what was used at calculation time.

Snapshot fields should include:

- employee name
- employee number
- entity
- country
- department/project/client if used for cost allocation
- employment type
- salary type
- base salary
- bank account display snapshot if used for payment export
- rule version

---

## 6. Initial field design

This section is intentionally broad because the initial design must be complete enough for dispatch management and APAC payroll growth.

## 6.1 Common payroll batch fields

- `batch_id`
- `country_code` — `JP`, `SG`, `CN`
- `entity_id`
- `entity_name_snapshot`
- `payroll_month`
- `payroll_period_start`
- `payroll_period_end`
- `payment_date`
- `currency`
- `status`
- `rule_version_id`
- `created_by`
- `created_at`
- `calculated_by`
- `calculated_at`
- `finalized_by`
- `finalized_at`
- `paid_by`
- `paid_at`
- `void_reason`
- `notes`

## 6.2 Common employee payroll row fields

Identity and scope:

- `payroll_record_id`
- `batch_id`
- `employee_id`
- `employee_no_snapshot`
- `employee_name_snapshot`
- `country_code`
- `entity_id`
- `department_snapshot`
- `project_snapshot`
- `client_snapshot`
- `employment_type_snapshot`
- `salary_type`
- `currency`

Base and attendance:

- `base_salary`
- `daily_rate`
- `hourly_rate`
- `scheduled_work_days`
- `actual_work_days`
- `paid_leave_days`
- `unpaid_leave_days`
- `absence_days`
- `normal_work_hours`
- `overtime_hours`
- `holiday_work_hours`
- `late_night_hours`

Earnings:

- `base_pay`
- `overtime_pay`
- `holiday_work_pay`
- `late_night_pay`
- `allowance_total`
- `bonus_total`
- `commission_total`
- `retroactive_pay`
- `gross_pay`

Deductions:

- `statutory_deduction_total`
- `tax_total`
- `social_insurance_total`
- `other_deduction_total`
- `manual_deduction_total`
- `deduction_total`

Net/payment:

- `net_pay`
- `payment_method`
- `bank_name_snapshot`
- `bank_branch_snapshot`
- `bank_account_type_snapshot`
- `bank_account_last4_snapshot`
- `payment_status`

Control:

- `calculation_status`
- `warning_count`
- `manual_adjustment_count`
- `employee_notice_status`
- `employee_feedback_status`
- `hr_review_status`
- `final_lock_flag`
- `record_version`
- `notes`

## 6.3 Japan-specific payroll fields

Japan salary table should include enough fields for payroll and dispatch/haken review:

- `jp_standard_monthly_hours`
- `jp_standard_daily_hours`
- `jp_legal_overtime_hours`
- `jp_non_statutory_overtime_hours`
- `jp_late_night_overtime_hours`
- `jp_statutory_holiday_hours`
- `jp_non_statutory_holiday_hours`
- `jp_overtime_rate`
- `jp_late_night_rate`
- `jp_holiday_rate`
- `jp_commuting_allowance_taxable`
- `jp_commuting_allowance_non_taxable`
- `jp_health_insurance_employee`
- `jp_nursing_care_insurance_employee`
- `jp_pension_employee`
- `jp_employment_insurance_employee`
- `jp_income_tax_withholding`
- `jp_resident_tax`
- `jp_social_insurance_grade`
- `jp_dependent_count_snapshot`
- `jp_tax_category_snapshot`
- `jp_my_number_collected_flag_snapshot` — do not expose sensitive number in payroll table.
- `jp_dispatch_contract_id_snapshot`
- `jp_client_site_snapshot`
- `jp_dispatch_assignment_id_snapshot`

## 6.4 Singapore-specific payroll fields

- `sg_basic_salary`
- `sg_gross_monthly_wage`
- `sg_additional_wage`
- `sg_cpf_ordinary_wage`
- `sg_cpf_additional_wage`
- `sg_employee_cpf`
- `sg_employer_cpf`
- `sg_sdl`
- `sg_fwl_or_levy_placeholder`
- `sg_ir8a_income_category_snapshot`
- `sg_pr_or_citizenship_status_snapshot`
- `sg_work_pass_type_snapshot`
- `sg_tax_residency_status_snapshot`

## 6.5 China-specific payroll fields

- `cn_base_salary`
- `cn_city_code`
- `cn_social_insurance_base`
- `cn_housing_fund_base`
- `cn_pension_employee`
- `cn_medical_employee`
- `cn_unemployment_employee`
- `cn_housing_fund_employee`
- `cn_pension_employer`
- `cn_medical_employer`
- `cn_unemployment_employer`
- `cn_work_injury_employer`
- `cn_maternity_employer`
- `cn_housing_fund_employer`
- `cn_taxable_income_current_month`
- `cn_cumulative_taxable_income`
- `cn_individual_income_tax`
- `cn_special_additional_deduction`
- `cn_after_tax_adjustment`
- `cn_residence_city_snapshot`
- `cn_work_city_snapshot`

---

## 7. Payroll parameters and rule versioning

The system needs parameter maintenance before reliable calculations.

Recommended parameter structure:

- Country-level parameters.
- Entity-level parameters.
- City/prefecture-level parameters where needed.
- Employee-level flags.
- Effective start/end dates.
- Rule version ID.
- Approval status.
- Parameter change audit.

Parameter examples:

- Japan overtime rates and salary item rules.
- Japan social insurance/tax placeholders by period.
- Singapore CPF rate tables by employee age/status if applicable.
- China city social insurance and housing fund rates.
- Payroll calendar and payment date rules.

MVP rule: if a statutory formula is not validated, the system should allow manual entry or reviewed parameter entry rather than pretending automation is correct.

---

## 8. Audit, permission, and security requirements

## 8.1 Audit logging

Every payroll-relevant change must append an audit log with required fields:

- `module`
- `record_id`
- `action`
- `user`
- `timestamp`
- `before_value`
- `after_value`

Additional recommended fields:

- `country_code`
- `entity_id`
- `batch_id`
- `employee_id`
- `reason`
- `source_ip`
- `request_id`

Audit logs must never be deleted and should be read-only from UI/API.

## 8.2 Permission model

Suggested permissions:

- `salary.access`
- `salary.view`
- `salary.batch.create`
- `salary.calculate`
- `salary.adjust`
- `salary.review`
- `salary.notice.send`
- `salary.finalize`
- `salary.payment.prepare`
- `salary.payment.mark_paid`
- `salary.parameters.manage`
- `salary.salary_master.manage`
- `salary.audit.view`
- `salary.jp.manage`
- `salary.sg.manage`
- `salary.cn.manage`

Suggested control principle:

- HR/Payroll maker can prepare and calculate.
- Payroll checker/manager approves finalization.
- Finance can view payment list and mark paid if assigned.
- Ordinary employee can only view own payslip/notice in future employee self-service.

## 8.3 Sensitive data

Payroll contains highly sensitive personal and compensation data. Minimum controls:

- No public unauthenticated access.
- No-store/cache-control headers.
- Role-based access.
- Entity/country scope checks.
- Do not expose national IDs/My Number/full bank account numbers in normal payroll tables.
- Keep bank details masked in payroll snapshots unless export is explicitly authorized.
- Keep payroll exports controlled and audited.

---

## 9. MVP implementation roadmap

## Phase 0 — Rebuild planning and data model confirmation

Goal: confirm the new APAC salary architecture before expanding code.

Deliverables:

- This APAC payroll plan.
- Country module boundaries.
- Initial common and country-specific field list.
- Payroll workflow status model.
- Open business questions list.

## Phase 1 — Core payroll batch MVP

Goal: create a simple but correct monthly payroll operation foundation.

Deliverables:

- Payroll dashboard.
- Create payroll batch by country/entity/month.
- Create employee rows from selected population.
- Employee payroll snapshot.
- Manual salary master fields.
- Manual or simple calculation for gross/deduction/net.
- Draft/calculated/HR review/finalized status.
- Audit logging.

Recommended first implementation choice:

- Build `salary-core` first.
- Support all three country codes in the data model.
- Only automate simple arithmetic at first.
- Keep country-specific statutory values manually maintainable until verified.

## Phase 2 — Japan module first production-grade depth

Goal: make Japan payroll table strong enough for dispatch/haken operations.

Deliverables:

- Japan salary item setup.
- Japan overtime/late-night/holiday hour fields.
- Timesheet data import or internal interface.
- Japan allowance and deduction breakdown.
- Draft Japan payslip layout.
- Japan payroll close checklist.

## Phase 3 — Singapore and China module setup

Goal: add independent SG/CN payroll sheets without mixing country rules.

Deliverables:

- Singapore payroll fields and parameter structure.
- China payroll fields and city-parameter structure.
- SG/CN sample payroll records.
- Manual calculation support plus placeholders for statutory automation.

## Phase 4 — Employee notice and feedback loop

Goal: support the HR-to-employee confirmation cycle.

Deliverables:

- First payroll notice/payslip version.
- Employee feedback status and comment capture.
- HR correction workflow.
- Final payroll notice.
- Payslip version history.

## Phase 5 — Payment and final archive

Goal: preserve final payroll records and prepare payment operations.

Deliverables:

- Finalization lock.
- Payment preparation list.
- CSV export or bank-file-ready structure.
- Mark paid workflow.
- Final archive and read-only history.

## Phase 6 — Rule automation hardening

Goal: carefully automate statutory calculations only after validation.

Deliverables:

- Rule versioning by country.
- Calculation test cases.
- Payroll specialist sign-off for each automated rule.
- Regression test pack for JP/SG/CN.

---

## 10. Recommended non-complex MVP scope

To avoid overbuilding, the first practical version should include:

- Country/entity/month payroll batch creation.
- Employee salary master.
- Employee snapshot.
- Payroll sheet table.
- Run calculation button.
- Manual adjustment with reason.
- Draft/first notice/finalized/paid statuses.
- Basic payslip notice output.
- Audit log.

Defer these until later:

- Fully automated statutory tax engines.
- Direct bank integration.
- Accounting system integration.
- Employee mobile self-service app.
- Advanced approval matrix.
- Multi-language payslip formatting beyond essential labels.
- AI payroll anomaly checker.

---

## 11. Confirmed business requirements as of 2026-06-23

The following requirements are now confirmed and should drive the v2 design.

### 11.1 Country rollout priority

Japan, Singapore, and China should all go live in the first formal payroll system rollout.

- Japan must be implemented deeply.
- Singapore and China must also be implemented for launch because payroll importance is equal across countries.
- The system should not treat SG/CN as only future placeholders. They can start with more manual statutory input, but their payroll sheets, workflows, employer cost reporting, payslip/PDF, audit, and close process must be real from Phase 1.

### 11.2 Legal entity scope

Initial legal entity structure should follow Master Data:

- Japan: 1 entity.
- Singapore: 1 entity.
- China: 3 entities.

Implementation note: payroll batches must be created by `country_code + entity_id + payroll_month`, not only by country/month. For China, this means separate payroll batches for the Nanjing, Xi'an, and Shanghai legal entities when all are in scope.

Current Master Data reference as of 2026-06-23:

| Entity ID | Entity Code | Country in Master Data | Entity Name | Currency | Payroll treatment |
| --- | --- | --- | --- | --- | --- |
| `ENT-0001` | `TAKK` | `Japan` | Tech Alliance KK / Tech Alliance株式会社 | JPY | JP entity |
| `ENT-0002` | `TASG` | `Singapore` | Tech Alliance Consultancy Service Pte. Ltd | SGD | SG entity |
| `ENT-0003` | `TANJ` | `中国` | 南京特谙斯企业咨询有限公司 | CNY | CN payroll entity |
| `ENT-0004` | `TAXA` | `CHINA` | 西安特谙斯企业咨询有限公司 | CNY | CN payroll entity |
| `ENT-0005` | `TASH` | `CHINA` | 上海特安企业管理有限公司 | CNY | CN payroll entity |

Business confirmation updated on 2026-06-23: all 3 active China legal entities are in payroll scope. Payroll should create and close China payroll by legal entity, not as one combined China payroll sheet.

### 11.3 Employee population

The employee population includes all major worker types:

- dispatched/haken employees
- regular employees
- contract employees
- part-time employees
- foreign national employees

Implementation note: payroll records must snapshot employee type, work country, legal entity, tax/social-insurance flags, and dispatch/client assignment fields where applicable.

### 11.4 Employee net pay and employer cost

The system must support both:

- employee gross/deduction/net pay calculation; and
- employer cost reporting.

Employer cost should be included from the v2 data model, even where early country statutory items are manually entered.

### 11.5 Payslip and payroll notice

Initial payroll notice channel:

- system email should be supported first;
- downloadable PDF payslip is also required.

Implementation note: payslip generation should keep version history for first notice and final notice. Email sending must be audited and should store delivery status.

### 11.6 Payroll finalization control

Payroll finalization requires two levels of confirmation.

- Normal operation should support maker/checker or first/second confirmation.
- Admin can perform both functions when business policy allows, but the audit log must still record two separate confirmation actions.

### 11.7 China city scope

Initial China city parameter scope:

- Shanghai
- Nanjing
- Xi'an
- Wuhu

Implementation note: China payroll parameters must support city-level social insurance and housing fund configuration.

### 11.8 Singapore CPF handling

Singapore CPF fields should exist from the first v2 data model, but CPF values can initially be manually entered or parameter-assisted.

Implementation note: automated CPF calculation can be a later enhancement after validation, but payroll rows must preserve employee CPF and employer CPF fields from launch.

---

## 12. Updated initial recommendation

Recommended direction:

1. Treat TAC-salary as a fresh APAC payroll rebuild.
2. Keep `salary-core` as the common monthly payroll workflow engine.
3. Keep `salary-jp`, `salary-sg`, and `salary-cn` as independent country calculation modules.
4. Launch JP/SG/CN together in the first formal rollout, with country-specific fields and workflow support for all three.
5. Automate Japan deeply from the beginning where rules are clear; support Singapore and China with complete data structures plus manual/parameter-assisted statutory entries first, then deepen automation after validation.
6. Include both employee net pay and employer cost reporting in the first v2 schema.
7. Support system email payroll notices and downloadable PDF payslips from the first formal workflow.
8. Require two-step payroll finalization, while allowing Admin to execute both steps with full audit trail.
9. Keep HR operations simple: create monthly sheet, calculate, review, adjust, notify, correct, finalize, pay, archive.
10. Preserve auditability and snapshots from the first implementation slice.

---

## 13. 2026-06-24 country/entity payroll system refinement

The product direction is now refined from a single APAC payroll workspace into a **shared payroll platform with three visible country payroll systems**:

```text
TAC Salary Platform
├── 日本薪资计算 / Japan Salary Calculation
├── 新加坡薪资计算 / Singapore Salary Calculation
└── 中国薪资计算 / China Salary Calculation
```

Implementation principle:

- The backend keeps shared core workflow objects: payroll batches, salary master, employee snapshots, reports, payslips, notices, payment, feedback, confirmations, and audit logs.
- The UI presents separate country payroll modules so operators do not see unrelated country fields by default.
- Each module defaults to its own `country_code`, `payroll_system_code`, `payroll_area_code`, legal entities, currency, and country-specific fields.
- Entering 中国薪资计算 defaults to `country_code = CN` and shows only China entities (`ENT-0003`, `ENT-0004`, `ENT-0005`) and China salary/payroll records.
- Entering 日本薪资计算 defaults to `country_code = JP` and shows only Japan entity/payroll data.
- Entering 新加坡薪资计算 defaults to `country_code = SG` and shows only Singapore entity/payroll data.
- Global platform view remains available for cross-country overview and administration.

Runtime-aligned system codes:

| Country | User-facing module | `payroll_system_code` | `payroll_area_code` | Default currency |
| --- | --- | --- | --- | --- |
| JP | 日本薪资计算 / Japan Salary Calculation | `JP_PAYROLL` | `JP_MONTHLY` | JPY |
| SG | 新加坡薪资计算 / Singapore Salary Calculation | `SG_PAYROLL` | `SG_MONTHLY` | SGD |
| CN | 中国薪资计算 / China Salary Calculation | `CN_PAYROLL` | `CN_MONTHLY` | CNY |

UI/UX consistency rule:

- TAC-salary should follow TAC-employeeadmin visual conventions where practical: navy header, rounded white cards, pill navigation, soft-blue object headers, compact metric cards, consistent table spacing, trilingual labels, and simple advanced filtering.
- Country modules should share the same navigation and workflow so HR/payroll users learn one process, while country-specific fields are only displayed inside the relevant module.
