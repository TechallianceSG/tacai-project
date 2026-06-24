# TAC-salary APAC Payroll v2 Implementation Steps

Last updated: 2026-06-23

This document converts the APAC payroll plan into an implementation sequence for the local MVP.

Scope confirmed:

- Japan: 1 entity — `ENT-0001` / `TAKK`.
- Singapore: 1 entity — `ENT-0002` / `TASG`.
- China: 3 entities — `ENT-0003` / `TANJ`, `ENT-0004` / `TAXA`, `ENT-0005` / `TASH`.
- JP/SG/CN all go live in the first formal payroll rollout.
- Employee net pay and employer cost are both required.
- System email notice and PDF payslip download are required.
- Payroll finalization requires two confirmation actions.

---

## 1. Implementation principles

1. Keep the local MVP dependency-free unless a later explicit decision approves dependencies.
2. Reuse TACAI User_admin for authentication and permissions.
3. Reuse Master Data as legal entity source of truth.
4. Reuse EmployeeAdmin as employee source of truth and snapshot data into payroll records.
5. Store payroll records by country-specific files while sharing workflow objects.
6. Do not automate statutory payroll rules until validated by official sources and/or payroll specialist sign-off.
7. Keep all state-changing actions audited.
8. Do not silently edit finalized payroll records.

---

## 2. Target local database files

Create these files under `database/`:

```text
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

Existing legacy files:

- `salary_records.json` should be retained as legacy/test data until migrated or archived.
- `employees.json` should be treated as placeholder/legacy; EmployeeAdmin should become source of truth.
- `audit_logs.json` remains append-only.

---

## 3. Phase 1 — Data foundation

Goal: make the v2 data files and helper functions available without changing all UI at once.

Tasks:

1. Add JSON file constants and safe load/save helpers for all v2 files.
2. Add ID generation helpers:
   - `PB-{country}-{entity_id}-{YYYY-MM}-V001`
   - `PR-{country}-{entity_id}-{YYYY-MM}-{employee_id}`
   - `NOTICE-{YYYYMM}-{sequence}`
   - `CONF-{YYYYMM}-{sequence}`
   - `PAY-{YYYYMM}-{sequence}`
3. Add normalized country/entity validation helpers.
4. Add batch uniqueness validation by `country_code + entity_id + payroll_month + batch_version`.
5. Add shared audit append helper with required audit fields.

Deliverable:

- Backend can load and write the v2 files safely.
- Syntax check passes.

---

## 4. Phase 2 — Payroll dashboard and batch creation

Goal: HR can create monthly payroll batches by country/entity/month.

Routes/pages to add or refactor:

- `GET /dashboard` — payroll summary.
- `GET /batches` — payroll batch list.
- `GET /batches/new` — create batch form.
- `POST /batches` — create batch.
- `GET /batches/{batch_id}` — batch detail.

Batch creation form fields:

- country code;
- entity ID;
- payroll month;
- payroll period start/end;
- payment date;
- payroll type;
- notes.

Validation:

- Entity must exist in Master Data or local entity snapshot cache.
- Currency must match country/entity.
- Do not create duplicate active batch for the same country/entity/month/version.

Audit actions:

- `payroll_batch_created`
- `payroll_batch_voided`

---

## 5. Phase 3 — Salary master and employee snapshot loading

Goal: payroll can load employee rows from EmployeeAdmin and salary master.

Routes/pages:

- `GET /salary-master`
- `GET /salary-master/new`
- `POST /salary-master`
- `GET /batches/{batch_id}/load-employees`
- `POST /batches/{batch_id}/load-employees`

Salary master fields:

- employee ID;
- entity ID;
- country code;
- effective from/to;
- salary type;
- base salary;
- fixed allowances;
- payroll flags;
- country profile section.

Employee snapshot fields:

- employee ID / employee number / display name;
- legal entity;
- department;
- employment type / worker type;
- work country and city;
- join/resign date;
- dispatch/client assignment where applicable;
- masked bank/payment reference.

Audit actions:

- `salary_master_created`
- `salary_master_updated`
- `payroll_employees_loaded`

---

## 6. Phase 4 — Payroll calculation MVP

Goal: support explainable payroll calculation for JP/SG/CN using common arithmetic and country fields.

Routes/pages:

- `POST /batches/{batch_id}/calculate`
- `GET /batches/{batch_id}/records`
- `GET /records/{payroll_record_id}`
- `POST /records/{payroll_record_id}/adjust`

Initial calculation:

```text
gross_pay = base salary + allowances + overtime/bonus/other earnings
total_employee_deductions = employee statutory/manual deductions + other deductions
net_pay = gross_pay - total_employee_deductions + manual_adjustments_total
total_employer_cost = gross_pay + employer statutory/manual costs + other employer costs
```

Country handling:

- JP: include overtime, late-night, holiday, haken references.
- SG: include CPF employee/employer manual fields.
- CN: include city, social insurance, housing fund, IIT manual/parameter fields.

Audit actions:

- `payroll_calculated`
- `payroll_record_adjusted`

---

## 7. Phase 5 — Notice, PDF payslip, and feedback

Goal: HR can send first notice, collect feedback, correct records, and send final notice.

Routes/pages:

- `GET /batches/{batch_id}/notices`
- `POST /batches/{batch_id}/notices/first`
- `POST /batches/{batch_id}/notices/final`
- `GET /payslips/{payslip_id}/download`
- `GET /feedback`
- `POST /feedback/{feedback_id}/resolve`

Initial email approach:

- Store delivery records in `payroll_notices.json` and/or `payslip_documents.json` metadata.
- Use environment variables for sender configuration.
- Do not store email passwords in JSON.
- If SMTP is not yet configured, support `queued` / `manual_send_pending` status.

Initial PDF approach:

- Generate simple payslip document metadata first.
- If true PDF generation is deferred, store HTML/text payslip source and mark PDF generation as pending.
- Every generated/downloaded payslip must be audited.

Audit actions:

- `payroll_first_notice_sent`
- `payroll_final_notice_sent`
- `payslip_generated`
- `payslip_downloaded`
- `employee_feedback_submitted`
- `employee_feedback_resolved`

---

## 8. Phase 6 — Two-level confirmation and finalization

Goal: payroll cannot finalize without two confirmation actions.

Routes/pages:

- `POST /batches/{batch_id}/confirm/first`
- `POST /batches/{batch_id}/confirm/second`
- `POST /batches/{batch_id}/finalize`

Rules:

- First confirmation and second confirmation are separate records in `payroll_confirmations.json`.
- Admin can perform both only with `salary.admin.override` permission.
- Finalization locks batch and records.
- Post-finalization changes must use adjustment/replacement flow.

Audit actions:

- `payroll_first_confirmation_completed`
- `payroll_second_confirmation_completed`
- `payroll_finalized`

---

## 9. Phase 7 — Payment tracking and employer cost report

Goal: payroll can prepare payment and report employee net pay plus employer cost.

Routes/pages:

- `GET /batches/{batch_id}/payment`
- `POST /batches/{batch_id}/payment/prepare`
- `POST /batches/{batch_id}/payment/mark-paid`
- `GET /reports/employer-cost`
- `GET /reports/net-pay`

Payment fields:

- total employee count;
- total net pay;
- total employer cost;
- payment method;
- payment status;
- paid by/at;
- reference number;
- optional export file metadata.

Audit actions:

- `payroll_payment_prepared`
- `payroll_payment_marked_paid`
- `payroll_report_viewed`

---

## 10. Phase 8 — Permissions and tests

Suggested User_admin permissions:

- `salary.access`
- `salary.view`
- `salary.profile.manage`
- `salary.parameter.manage`
- `salary.batch.create`
- `salary.calculate`
- `salary.adjust`
- `salary.notice.send`
- `salary.feedback.manage`
- `salary.confirm.first`
- `salary.confirm.second`
- `salary.payment.manage`
- `salary.reports.view`
- `salary.audit.view`
- `salary.admin.override`

Minimum tests:

1. Batch uniqueness by country/entity/month.
2. Gross/deduction/net/employer cost arithmetic.
3. JP/SG/CN records are written to the correct country file.
4. First and second confirmations are separate records.
5. Admin dual confirmation writes separate audit actions.
6. Finalized records cannot be directly edited.
7. Payment cannot be prepared before finalization.
8. Audit logs append and are not overwritten.

---

## 11. Recommended next implementation order

1. Create v2 empty JSON database files.
2. Add backend constants/load/save helpers for v2 files.
3. Add batch list/create/detail.
4. Add salary master page.
5. Add employee row load/create from salary master first, then EmployeeAdmin integration.
6. Add calculation and record adjustment.
7. Add confirmations and finalization.
8. Add notice/PDF metadata and feedback workflow.
9. Add payment tracking and employer cost reports.
10. Add permissions and tests.

---

## 12. 2026-06-24 late workflow completion note

The local MVP now completes the planned payment/archive tail of the payroll close workflow:

- payment preparation updates the payment record, batch header, and payroll row statuses;
- mark-paid updates the payment record, batch header, and payroll row statuses to paid;
- payment CSV export is available for prepared/paid/archived batches and is audited;
- paid batches can be archived as locked read-only payroll history with archive metadata;
- the frontend Payment tab exposes Prepare Payment, Export Payment CSV, Mark Paid, and Archive Batch actions.

Verification passed: backend syntax check, dependency-free v2 smoke test, JSON array validation, and frontend JavaScript syntax check.
