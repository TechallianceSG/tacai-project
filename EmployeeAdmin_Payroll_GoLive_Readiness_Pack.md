# EmployeeAdmin / Payroll Go-Live Readiness Pack

Date: 2026-06-23
Scope: `TAC-employeeadmin` and `TACAI-PRJ` Payroll only.

## 1. Go-Live Decision Summary

### Recommended go-live position

- **EmployeeAdmin**: can proceed to controlled internal UAT / pilot after employee master data cleanup.
- **Payroll**: can proceed to calculation demo / parallel-run UAT, but should not be used for official payroll close until P0 items are complete.

### Mandatory gates before official payroll use

1. EmployeeAdmin employee master records are payroll-ready.
2. Payroll Salary Profiles are created from EmployeeAdmin employees.
3. Payroll records store stable EmployeeAdmin `employee_id` plus employee/entity snapshots.
4. Duplicate active payroll records for the same employee/month are prevented or handled through batch/versioning.
5. Payroll close workflow has draft, review, approve, lock, and correction states.
6. Payroll module receives security hardening equivalent to EmployeeAdmin.
7. HR/payroll specialist confirms Japan, China, and Singapore statutory/manual calculation assumptions.

---

## 2. P0 Pre-Go-Live Checklist

P0 means go-live blocker for official payroll close.

| Area | Checklist item | Owner | Evidence required | Status |
|---|---|---|---|---|
| Employee Master | Complete required employee fields: employee number, name, country, legal entity, status, type, hire date, department, work email, work country, business line, profile status | HR | EmployeeAdmin data completion report / CSV import result | Open |
| Employee Master | Complete payroll bank fields: bank name, branch, account type, account number, account holder; SWIFT optional | HR / Finance | Employee detail payroll section or import validation result | Open |
| Employee Master | Confirm `entity_id + employee_number` uniqueness | HR / IT | Data quality report | Open |
| Employee Master | Confirm active employees, resigned employees, and probation employees are correctly classified | HR | Employee list and reports | Open |
| Employee Master | Confirm foreign employee visa and residence-card records for Japan payroll-relevant employees | HR | Visa expiry report / employee detail | Open |
| Employee Master | Confirm dispatch employee assignment records for haken/dispatch staff | HR / Dispatch Ops | Dispatch assignment report / history | Open |
| Employee Master | Confirm sensitive fields are not exposed through ordinary list/export views | IT / Security | Safe CSV and employee list review | Open |
| User / Permission | Confirm User_admin roles for System Admin, HR Manager, Finance/Payroll, Manager, Employee | IT / HR | User_admin role-permission screenshots or JSON review | Open |
| User / Permission | Confirm ordinary employee cannot access EmployeeAdmin or Payroll | IT | Browser UAT result | Open |
| User / Permission | Confirm Payroll access limited to authorized HR/Finance/Payroll users | IT / Finance | Browser UAT result | Open |
| Payroll Profile | Create Salary Profiles only from EmployeeAdmin payroll-eligible employees | Payroll Admin | Salary Profiles list | Open |
| Payroll Profile | Each Salary Profile includes `employee_id`, employee number snapshot, employee name snapshot, entity, country, work location, currency, payroll scheme, rates, deductions, and tax-reference inputs | Payroll Admin / IT | Salary Profile detail / data check | Open |
| Payroll Record | Prevent duplicate active payroll records for same employee and payroll month | IT | Unit/helper test and browser negative test | Open |
| Payroll Record | Add payroll batch/versioning or at minimum a correction/void workflow with audit | IT / Payroll Admin | Batch/version UAT result | Open |
| Payroll Close | Define payroll statuses: draft, reviewed, approved, locked, correction, voided | Product / Payroll Admin | SOP and UI status evidence | Open |
| Payroll Close | Lock approved payroll month from direct modification | IT / Payroll Admin | Browser negative test | Open |
| Payroll Calculation | Confirm Japan payroll items: base salary, allowances, transport, overtime, social insurance, pension, employment insurance, income tax, resident tax, manual adjustments | Payroll Specialist | Signed rule checklist | Open |
| Payroll Calculation | Confirm China payroll items: attendance, social insurance, housing fund, IIT estimate/reference, confirmed tax, additional deductions | Payroll Specialist | Signed rule checklist | Open |
| Payroll Calculation | Confirm Singapore payroll items: monthly/prorated salary, CPF employee/employer, manual deductions | Payroll Specialist | Signed rule checklist | Open |
| Payroll Calculation | Confirm estimated tax is reference-only and net pay uses confirmed tax only | Payroll Specialist / IT | Test case result | Open |
| Export | Payroll Register export includes month, country/template, generated timestamp, exported by, source batch/version | IT / Payroll Admin | CSV export sample | Open |
| Export | Audit export includes who/what/when/before/after fields and export audit event | IT / Auditor | Audit CSV sample | Open |
| Security | Payroll pages and CSV responses use no-store where appropriate | IT | Header smoke test | Open |
| Security | Payroll flash/session-adjacent cookies use HttpOnly/SameSite and Secure in HTTPS environment | IT | Header/cookie smoke test | Open |
| Security | Payroll POST body and Excel upload have size limits | IT | Negative upload test | Open |
| Security | Excel upload handles invalid ZIP/oversized XLSX safely | IT / Security | Negative upload test | Open |
| Security | Employee documents and onboarding documents are not served by raw filesystem path | IT / Security | Browser negative test | Open |
| Data Protection | My Number workflow is disabled or legally/security approved before production use | HR / Legal / Security | Written approval or feature-disabled evidence | Open |
| Backup | Back up EmployeeAdmin JSON, Payroll JSON, audit logs, and uploaded documents before UAT and before go-live | IT | Backup file list and restore check | Open |
| Operations | Define who can approve payroll close and who can reopen/correct | HR / Finance / Management | SOP sign-off | Open |

---

## 3. P1 Strong Recommendations Before Broader Pilot

| Area | Recommendation | Reason |
|---|---|---|
| EmployeeAdmin | Redact or split `/employees.json` before production use | It can expose sensitive full employee records even with export permission |
| EmployeeAdmin | Add separate `documents.view` vs `documents.manage` permission | Some users may need read-only document review, not upload/edit/delete authority |
| EmployeeAdmin | Add malware scanning or at least quarantine workflow for uploaded documents | Employee identity/payroll documents are high-risk files |
| EmployeeAdmin | Add retention/disposal policy for documents and My Number-related artifacts | Required for privacy and Japan compliance governance |
| Payroll | Add EmployeeAdmin employee picker with employee_id binding | Reduces manual entry and employee-number ambiguity |
| Payroll | Add batch review screen with totals and variance vs prior month | Payroll operators need exception review before approval |
| Payroll | Add per-country pre-close validation reports | Japan/CN/SG have different statutory and operational checks |
| Payroll | Add native XLSX/PDF export after dependency/service approval | CSV is acceptable for MVP but not final payroll document maturity |
| Audit | Centralize audit viewer later across EmployeeAdmin, Payroll, Timesheet, Reimbursement | Cross-module traceability will become important as suite matures |

---

## 4. UAT Test Cases

### 4.1 Access Control UAT

| ID | Scenario | Role | Steps | Expected result | Priority |
|---|---|---|---|---|---|
| AC-01 | Unauthenticated EmployeeAdmin access | None | Open `/dashboard` on port 8004 | Redirect to User_admin login with `next` URL | P0 |
| AC-02 | Unauthenticated Payroll access | None | Open `/` on port 8001 | Redirect to User_admin login | P0 |
| AC-03 | System Admin access to EmployeeAdmin | System Admin | Login, open EmployeeAdmin dashboard, employees, reports, audit | All allowed pages load | P0 |
| AC-04 | HR Manager access to EmployeeAdmin | HR Manager | Login, open employees, onboarding, reports | Allowed according to role permissions | P0 |
| AC-05 | Payroll user access to Payroll | Payroll/Finance | Login, open salary profiles, input, register, payslips, audit logs | Allowed according to payroll permissions | P0 |
| AC-06 | Ordinary employee blocked from EmployeeAdmin | Employee | Login, open EmployeeAdmin URL | 403 or not visible from Portal | P0 |
| AC-07 | Ordinary employee blocked from Payroll | Employee | Login, open Payroll URL | 403 or not visible from Portal | P0 |
| AC-08 | User without document permission cannot open employee document | HR read-only or restricted user | Open protected document link | 403 | P0 |

### 4.2 Employee Master UAT

| ID | Scenario | Steps | Expected result | Priority |
|---|---|---|---|---|
| EM-01 | Create payroll-ready Japan employee | Create employee with required master fields and bank fields | Save succeeds; detail shows correct data; audit created | P0 |
| EM-02 | Create employee missing required country/work/business-line | Submit missing fields | Validation blocks save | P0 |
| EM-03 | Create employee missing required bank field for payroll-ready standard | Submit missing bank fields | Validation or data readiness report flags missing values | P0 |
| EM-04 | Duplicate employee number in same legal entity | Create second employee with same employee number/entity | Save/import blocks duplicate | P0 |
| EM-05 | Same employee number across different legal entities | Create same employee number under different entity | Allowed if entity differs | P0 |
| EM-06 | CSV import invalid legal entity code | Upload CSV with unknown legal_entity_code | Entire batch blocked; row/field errors shown | P0 |
| EM-07 | CSV import invalid department code under entity | Upload CSV with wrong department_code | Entire batch blocked; clear error shown | P0 |
| EM-08 | Valid JP/CN/SG CSV import | Upload valid rows in one supported header language | Import succeeds; backup created; audit event created | P0 |
| EM-09 | Safe CSV export | Export employees CSV | Sensitive fields excluded | P0 |
| EM-10 | Data quality report | Open duplicate/data completion reports | Missing fields and duplicates display correctly | P0 |
| EM-11 | Resigned employees hidden by default | Open employee list | Resigned hidden unless filter/check enabled | P1 |
| EM-12 | Entity/department/team display labels | Open list/detail/report | Master Data labels resolve correctly | P1 |

### 4.3 Onboarding UAT

| ID | Scenario | Steps | Expected result | Priority |
|---|---|---|---|---|
| ONB-01 | HR creates onboarding request | Create request with candidate email and planned start date | Request created; audit logged | P1 |
| ONB-02 | HR prepares email draft | Open email draft page | Candidate, default CC, optional CC, body, expiry visible | P1 |
| ONB-03 | Invalid CC validation | Add invalid or duplicate CC | Send blocked with validation error | P1 |
| ONB-04 | SMTP send success | Confirm draft send | Link email and verification code email sent as configured; audit logged | P1 |
| ONB-05 | Manual package fallback | Generate manual package | Fresh link and one-time code shown only to HR, not persisted plaintext | P1 |
| ONB-06 | Candidate opens token before verification | Open token link | Verification code page shown before form/document access | P1 |
| ONB-07 | Candidate uploads required documents | Upload required files within limits | Files accepted; readiness checklist updates | P1 |
| ONB-08 | Candidate formal submit with missing required document | Submit incomplete package | Submit blocked; draft save still allowed | P1 |
| ONB-09 | Browser signature evidence | Sign eligible HR document | Evidence generated; hash/audit stored | P1 |
| ONB-10 | HR approves and imports | HR review, approve, import | Employee Master created/updated; documents copied; audit logged | P1 |

### 4.4 Payroll Profile and Calculation UAT

| ID | Scenario | Steps | Expected result | Priority |
|---|---|---|---|---|
| PAY-01 | Create Salary Profile from EmployeeAdmin employee | Select employee, set country/scheme/rates | Profile saves with employee_id and snapshots | P0 |
| PAY-02 | Japan simple monthly calculation | Create JP profile, input month and additions/deductions | Gross, deductions, net pay calculate with Decimal whole yen | P0 |
| PAY-03 | China monthly prorated calculation | Input working days and attendance days | Base pay prorated correctly; warnings if missing tax inputs | P0 |
| PAY-04 | China contractor daily calculation | Input daily rate and attendance days | Base pay = daily rate × days | P0 |
| PAY-05 | China contractor hourly calculation | Input hourly rate and hours | Hourly pay and gross calculate correctly | P0 |
| PAY-06 | Singapore prorated calculation | Input monthly salary, working days, attendance | Base pay prorated; CPF employee reduces net; employer CPF does not reduce net | P0 |
| PAY-07 | Negative amount blocked | Enter negative salary/deduction | Validation error | P0 |
| PAY-08 | Invalid payroll month blocked | Enter malformed month | Validation error | P0 |
| PAY-09 | Estimated tax reference not applied by default | Calculate with estimated tax but no confirmation/apply flag | Net pay does not use estimated tax | P0 |
| PAY-10 | Confirmed tax affects net pay | Enter confirmed tax | Net pay reduced by confirmed tax | P0 |
| PAY-11 | Apply estimated tax explicitly | Use apply estimate flag where allowed | Audit/record clearly shows estimate applied as confirmed | P1 |

### 4.5 Payroll Close UAT

| ID | Scenario | Steps | Expected result | Priority |
|---|---|---|---|---|
| CLOSE-01 | Save first active record for employee/month | Save payroll record | Record saved active; audit logged | P0 |
| CLOSE-02 | Duplicate active prevention | Try to save second active record for same employee/month | Save blocked or creates new version after workflow confirmation | P0 |
| CLOSE-03 | Void payroll record | Void an active record | Status becomes voided; before/after audit written | P0 |
| CLOSE-04 | Payroll batch totals review | Open register for month/country | Totals match saved records | P0 |
| CLOSE-05 | Approve payroll batch | Reviewer approves batch | Status becomes approved; approval actor/time recorded | P0 |
| CLOSE-06 | Lock payroll batch | Payroll admin locks approved batch | Direct edits blocked | P0 |
| CLOSE-07 | Correction after lock | Create correction batch/version | Previous active version superseded only through auditable correction | P0 |
| CLOSE-08 | Export payroll register | Export CSV | File contains month/country/exported_at/exported_by/batch/version metadata | P0 |
| CLOSE-09 | Export audit logs | Export audit CSV | Export itself creates audit record | P0 |

### 4.6 Security / Technical UAT

| ID | Scenario | Steps | Expected result | Priority |
|---|---|---|---|---|
| SEC-01 | EmployeeAdmin response headers | Check HTML/JSON headers | `Cache-Control: no-store`, nosniff, referrer policy present | P0 |
| SEC-02 | Payroll response headers | Check HTML/CSV headers | Payroll hardened consistently with EmployeeAdmin | P0 |
| SEC-03 | Payroll large POST body | Submit body beyond configured limit | Request rejected safely | P0 |
| SEC-04 | Payroll oversized XLSX | Upload oversized file | Request rejected safely | P0 |
| SEC-05 | Invalid XLSX/ZIP | Upload malformed XLSX | Error shown; no crash; audit validation failure if applicable | P0 |
| SEC-06 | EmployeeAdmin upload limits | Upload disallowed extension or too-large file | Rejected with clear error | P0 |
| SEC-07 | Raw document path access | Try direct raw docs path | Not served | P0 |
| SEC-08 | Cookie attributes | Inspect flash/session-adjacent cookies | HttpOnly/SameSite; Secure in HTTPS environment | P0 |
| SEC-09 | CSRF origin check | Submit POST from unauthorized origin | Request blocked | P1 |
| SEC-10 | Backup/restore drill | Backup JSON/doc folders, restore to test copy | Restore successful | P0 |

---

## 5. Payroll Close SOP

### 5.1 Roles

| Role | Responsibility |
|---|---|
| HR Operator | Maintains EmployeeAdmin employee master, onboarding, visa, employment status, dispatch data |
| Payroll Admin | Maintains Salary Profiles, prepares monthly payroll input, reviews calculation warnings |
| Finance Reviewer | Reviews payroll totals, deductions, bank/payment readiness, export files |
| HR/Payroll Approver | Approves payroll batch before lock |
| IT Admin | Maintains access, backup, security controls, system availability |
| Auditor / Management | Reviews audit logs, close evidence, exceptions |

### 5.2 Monthly Payroll Close Timeline

| Timing | Activity | Owner |
|---|---|---|
| T-7 to T-5 business days | Confirm active employee population, joiners, leavers, entity, department, bank data | HR |
| T-5 to T-4 | Confirm attendance, dispatch assignment, allowances, reimbursements if applicable | HR / Payroll Admin |
| T-4 to T-3 | Create/update Salary Profiles and payroll inputs | Payroll Admin |
| T-3 | Generate draft payroll records and review country-specific warnings | Payroll Admin |
| T-2 | Finance review: totals, deductions, bank/payment readiness | Finance Reviewer |
| T-1 | HR/Payroll approval and batch lock | Approver |
| Pay day | Export final register/payment support files and retain evidence | Payroll Admin / Finance |
| T+1 to T+3 | Handle corrections through correction batch only | Payroll Admin / Approver |

### 5.3 SOP Steps

#### Step 1 — Employee Master Freeze Preparation

1. HR opens EmployeeAdmin dashboard and reports.
2. HR reviews:
   - missing required data report
   - data quality report
   - visa expiry report
   - probation ending report
   - dispatch assignment report
   - required document matrix
3. HR fixes missing payroll-ready fields.
4. HR confirms employee population for payroll month:
   - active employees
   - new joiners
   - leavers
   - mid-month join/termination cases
   - dispatch/contractor cases
5. HR exports safe employee CSV for review if needed.
6. IT backs up EmployeeAdmin JSON and document folders.

Exit criteria:

- No payroll-blocking missing fields.
- No duplicate employee numbers within same entity.
- Bank/payment fields complete for payroll-paid employees.

#### Step 2 — Salary Profile Preparation

1. Payroll Admin opens Payroll Salary Profiles.
2. For each payroll-eligible employee, create/update Salary Profile from EmployeeAdmin employee lookup.
3. Confirm profile fields:
   - EmployeeAdmin `employee_id`
   - employee number/name snapshot
   - entity/country/work location
   - currency
   - payroll scheme
   - monthly salary / daily rate / hourly rate
   - standard working days
   - Japan social insurance/pension/employment insurance/resident tax where applicable
   - China social insurance/housing fund/IIT reference fields where applicable
   - Singapore CPF employee/employer fields where applicable
4. Save profile and confirm audit log.

Exit criteria:

- Every payroll-eligible employee has one active Salary Profile.
- No obsolete active profile exists for resigned/non-payroll employees unless explicitly justified.

#### Step 3 — Draft Payroll Calculation

1. Payroll Admin opens Payroll Input.
2. Select Salary Profile or import/payroll input source.
3. Enter payroll month and attendance/payment/deduction values.
4. Review calculation preview:
   - gross pay
   - total deduction
   - net pay
   - estimated tax/reference warnings
   - confirmed tax fields
5. Confirm that estimated tax is not treated as final unless explicitly approved.
6. Save draft payroll record.

Exit criteria:

- Draft records exist for all payroll-eligible employees.
- No negative/unexplained values.
- No duplicate active employee/month records.

#### Step 4 — Payroll Register Review

1. Payroll Admin opens Payroll Register filtered by month and country.
2. Review per-employee lines.
3. Review totals by:
   - salary/payment items
   - deduction items
   - gross pay
   - net pay
   - country/entity
4. Compare with prior month or expected manual control totals.
5. Investigate variances and correction notes.
6. Finance Reviewer performs second review.

Exit criteria:

- Register totals accepted by Payroll Admin and Finance Reviewer.
- Exceptions documented.
- Corrections made through auditable update/version process.

#### Step 5 — Approval and Lock

1. HR/Payroll Approver reviews final draft batch.
2. Approver confirms:
   - employee population
   - calculation totals
   - statutory/manual deductions
   - bank/payment readiness
   - audit logs present
3. Approver marks batch approved.
4. Payroll Admin locks batch.
5. After lock, direct edits are blocked.

Exit criteria:

- Payroll batch status is locked.
- Approval actor/time are recorded.
- Locked register export is reproducible.

#### Step 6 — Export and Evidence Retention

1. Export Payroll Register CSV by country/month.
2. Export Audit Logs CSV.
3. Save final files in controlled payroll evidence folder.
4. Retain:
   - payroll register export
   - audit export
   - approval evidence
   - exception notes
   - backup snapshot
5. Confirm exported file metadata includes exported timestamp and exporting user.

Exit criteria:

- All final files stored and backed up.
- Export event is audit logged.

#### Step 7 — Post-Close Corrections

1. If an issue is found after lock, do not edit locked record directly.
2. Create a correction batch/version.
3. Document correction reason.
4. Finance/HR reviews correction.
5. Approver approves correction.
6. System supersedes prior active version only after new version is approved.
7. Export correction evidence and audit log.

Exit criteria:

- Original record remains historically visible.
- Corrected record is traceable.
- Audit explains before/after and approver.

---

## 6. Security Hardening Implementation Requirements for Payroll

The Payroll module should be brought closer to EmployeeAdmin before official go-live.

### Required changes

1. Add common response headers:
   - `Cache-Control: no-store` for HTML/JSON/payroll-sensitive pages.
   - `X-Content-Type-Options: nosniff`.
   - `Referrer-Policy: same-origin`.
   - `Permissions-Policy: camera=(), microphone=(), geolocation=()`.
   - Consider `Content-Security-Policy` with `frame-ancestors 'self'`.
2. Flash cookies:
   - Add `HttpOnly`.
   - Keep `SameSite=Lax`.
   - Add `Secure` when served through HTTPS.
3. Request limits:
   - Cap non-multipart POST body.
   - Cap multipart upload body.
   - Cap individual Excel file size.
4. Excel safety:
   - Reject malformed XLSX cleanly.
   - Check ZIP member count and uncompressed size to reduce zip-bomb risk.
5. Permission granularity:
   - Separate `payroll.audit.view` / `payroll.audit.export` from general reports if needed.
6. Audit:
   - Log validation failures, save, void, export, approve, lock, correction.

---

## 7. Architecture Implementation Requirements for Official Payroll

### Payroll record minimum fields

Each official payroll record should store:

- `record_id`
- `batch_id`
- `version_no`
- `record_status`
- `employee_id`
- `entity_id`
- `employee_number_snapshot`
- `employee_name_snapshot`
- `department_snapshot`
- `country`
- `work_location_country`
- `currency`
- `salary_profile_id`
- `payroll_month`
- `period_start`
- `period_end`
- payment fields
- deduction fields
- reference tax fields
- confirmed tax fields
- `gross_pay`
- `total_deduction`
- `net_pay`
- `created_by`, `created_at`
- `approved_by`, `approved_at`
- `locked_by`, `locked_at`
- `superseded_by`
- `correction_reason`

### Payroll batch minimum fields

- `batch_id`
- `payroll_month`
- `entity_id` or `country`
- `batch_status`
- `version_no`
- `created_by`, `created_at`
- `reviewed_by`, `reviewed_at`
- `approved_by`, `approved_at`
- `locked_by`, `locked_at`
- `record_count`
- `gross_total`
- `deduction_total`
- `net_total`
- `notes`

### Active uniqueness rule

For official payroll, active payroll records should be unique by:

```text
entity_id + employee_id + payroll_month + active_status
```

Correction should create a new version rather than overwriting the prior record.

---

## 8. Final Go-Live Sign-Off Template

| Sign-off area | Responsible person | Decision | Date | Notes |
|---|---|---|---|---|
| Employee master completeness | HR Lead | Pending |  |  |
| Payroll calculation rules | Payroll Specialist | Pending |  |  |
| Japan statutory/manual assumptions | Japan Payroll Specialist | Pending |  |  |
| China payroll assumptions | China Payroll Specialist | Pending |  |  |
| Singapore payroll assumptions | Singapore Payroll Specialist | Pending |  |  |
| Access control | IT Admin | Pending |  |  |
| Security hardening | Security / IT | Pending |  |  |
| Backup and restore | IT Admin | Pending |  |  |
| UAT completion | Product Owner | Pending |  |  |
| Final go-live approval | Management | Pending |  |  |

## 9. Recommended Immediate Next Actions

1. Complete EmployeeAdmin employee master/bank data.
2. Create Payroll Salary Profiles from EmployeeAdmin employees.
3. Clean or void duplicate/legacy Payroll test records.
4. Implement Payroll duplicate guard and batch/version model.
5. Harden Payroll response headers, cookies, body limits, and Excel upload handling.
6. Run the UAT test cases in this pack.
7. Obtain HR/Payroll/IT sign-off before official payroll close.
