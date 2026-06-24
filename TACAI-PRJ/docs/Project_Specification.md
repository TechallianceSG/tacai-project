# TACAI Prj - Japan HR Finance System

## 1. Project overview

**Project name:** TACAI Prj  
**System type:** Japan HR Finance System  
**Primary users:** HR, Finance, Payroll Admin, Management, Auditor  
**Target region:** Japan  
**Main purpose:** Automate monthly payroll operations, employee payslip generation, payroll register maintenance, payroll export, and audit tracking.

The system must reduce repetitive manual HR operations by allowing HR to upload a monthly payroll Excel file once, then automatically generate:

1. Employee payslips.
2. Payroll Register / 給与花名冊.
3. Payroll history records.
4. Audit logs.
5. Excel and PDF exports.

## 2. Enhancement requirements

Based on the provided Japanese payslip template, TACAI Prj must support employee payslip generation and automatically maintain a monthly Payroll Register / 給与花名冊.

All payroll records, payslips, and audit logs must be retained in the database and exportable to Excel/PDF.

## Scope note

Expense reimbursement / 経費精算 is out of scope for TACAI-PRJ and will be developed as a separate application. Archived reference assets remain under `archive/reimbursement/` only for future standalone planning.

## Current 2026-06 multi-country payroll rollout status

TACAI-PRJ now supports a lightweight multi-country payroll MVP for Japan, Singapore, and China. The 2026-06 payroll employee lists for the three locations are **blocked by Employee Master completion**: the final June payroll population must be created after EmployeeAdmin employee master data is established.

Operational boundaries:

1. TACAI-PRJ must not recreate a local Employee Master.
2. EmployeeAdmin remains the authoritative employee master source.
3. Salary Profiles in TACAI-PRJ store only payroll-specific employee references, rates, country, work location, tax-reference settings, and calculation inputs.
4. Japan and Singapore payroll templates are treated as clarified business templates.
5. China currently has source Excel data and uses the standardized template draft below as the working version for business review.
6. Current exports are Excel-compatible UTF-8 CSV and HTML/printable preview; native `.xlsx`, PDF, ZIP bundle, and full batch/version history remain later production-phase work unless separately approved.

## 3. Core modules

### 3.1 Payroll Upload Module

HR uploads a monthly payroll Excel file.

Supported input type:

- `.xlsx`

Initial payroll fields identified from the Japanese payroll format:

| English field | Japanese label | Data type | Required |
|---|---|---:|---:|
| Employee No. | 社員No. | Text | Yes |
| Employee Name | 氏名 | Text | Yes |
| Payroll Month | 給与月 | Year-month | Yes |
| Base Salary | 基本給 | Decimal | Yes |
| Position Allowance | 役職手当 | Decimal | No |
| Attendance Allowance | 勤務手当 | Decimal | No |
| Housing Allowance | 住宅手当 | Decimal | No |
| Taxable Transportation Allowance | 課税通勤費 | Decimal | No |
| Non-taxable Transportation Allowance | 非課税通勤費 | Decimal | No |
| Overtime Allowance | 普通残業手当 | Decimal | No |
| Health Insurance | 健康保険 | Decimal | No |
| Pension | 厚生年金 | Decimal | No |
| Employment Insurance | 雇用保険 | Decimal | No |
| Income Tax | 所得税 | Decimal | No |

Recommended derived fields:

| English field | Japanese label | Formula |
|---|---|---|
| Gross Pay | 総支給額 | Sum of salary and allowance fields |
| Total Deduction | 控除合計 | Sum of insurance and tax fields |
| Net Pay | 差引支給額 | Gross Pay - Total Deduction |

#### China payroll standard template draft / 中国工资模板标准化草案

The China template should normalize source Excel data into the following fields. GPT may generate this as the first draft; business users should review and modify before official payroll close.

| Field | Chinese label | Required | Notes |
|---|---|---:|---|
| payroll_month | 工资月份 | Yes | `YYYY-MM` |
| employee_no | 员工编号 | Yes | Must match EmployeeAdmin once master data is ready |
| employee_name | 员工姓名 | Yes | For display and review |
| entity | 公司主体 | Yes | China legal/payroll entity |
| country | 国家/地区 | Yes | `CN` |
| work_location_country | 实际工作地 | No | Usually `CN`; India remote can remain metadata under SG rule if approved |
| tax_reference_city | 个税/社保参考城市 | No | City affects social insurance/housing fund assumptions, not IIT rates |
| currency | 币种 | Yes | `CNY` |
| payroll_scheme | 薪资规则 | Yes | `cn_consultant_monthly`, `cn_dispatch_monthly_prorated`, `cn_contractor_daily`, or `cn_contractor_hourly` |
| monthly_salary | 月薪 | Conditional | Monthly consultant/dispatch schemes |
| daily_rate | 日薪单价 | Conditional | Daily contractor scheme |
| hourly_rate | 小时单价 | Conditional | Hourly contractor or overtime-style inputs |
| monthly_working_days | 当月应工作日 | Yes | Used for prorated monthly calculation |
| attendance_days | 出勤天数 | Yes | Payroll-period attendance basis |
| attendance_hours | 出勤小时 | No | Required for hourly scheme |
| calculated_base_pay | 基本/出勤工资 | System | Calculated by backend |
| hourly_pay | 小时工资金额 | System | Calculated by backend when applicable |
| additional_payment | 追加支给 | No | Bonus/allowance/manual additions |
| cn_social_insurance | 社保个人部分 | No | Employee deduction |
| cn_housing_fund | 公积金个人部分 | No | Employee deduction |
| cn_special_additional_deductions | 专项附加扣除 | No | Tax-reference basis |
| cn_other_deductions | 其他税前扣除 | No | Tax-reference basis |
| estimated_income_tax | 估算个税 | System | Reference only |
| confirmed_income_tax | 确认个税 | Yes at close | Only confirmed/applied tax affects net pay |
| additional_deduction | 追加扣除 | No | Manual deduction |
| gross_pay | 应发合计 | System | Calculated by backend |
| total_deduction | 扣除合计 | System | Includes confirmed tax and employee deductions |
| net_pay | 实发工资 | System | Gross minus total deduction |
| record_status | 记录状态 | System | active/voided/future superseded |
| notes | 备注 | No | HR review notes |

China IIT is reference-only until HR or payroll vendor confirms the final monthly deduction. Missing fields must be reported as warnings rather than silently invented.

### 3.2 Payroll Register Module / 給与花名冊

The Payroll Register must be generated and maintained automatically after each successful payroll upload.

Minimum functions:

1. Create one payroll register record per employee per payroll month.
2. Prevent duplicate active payroll records for the same employee and payroll month.
3. Support versioning when HR re-uploads corrected payroll data.
4. Keep prior versions for audit purposes.
5. Show monthly totals by payment item and deduction item.
6. Export payroll register to Excel and PDF.
7. Support filtering by payroll month, employee number, employee name, department, and upload batch.

### 3.3 Payslip Generation Module

For each employee payroll record, the system must generate a payslip based on the Japanese payslip template.

Minimum functions:

1. Generate individual employee payslip.
2. Display salary items, allowance items, deduction items, gross pay, total deduction, and net pay.
3. Export individual payslip to PDF.
4. Export all payslips for a payroll month as a ZIP or merged PDF.
5. Retain generated payslip metadata and file path in the database.

### 3.4 Export Module

Target production export formats:

1. Payroll Register Excel.
2. Payroll Register PDF.
3. Individual Payslip PDF.
4. Monthly Payslip bundle.
5. Audit Log Excel.

Current dependency-free MVP export scope:

1. Payroll Register UTF-8 CSV, country-specific and Excel-compatible.
2. Audit Log UTF-8 CSV, append-only and Excel-compatible.
3. Payslip HTML preview / printable browser view.

Exports must include generated timestamp, exporting user, and source payroll month or filter criteria where applicable. Native `.xlsx`, PDF, merged PDF, and ZIP bundle require a later dependency or export-service decision.

### 3.5 Audit Log Module

Every important operation must create an audit log record.

Events to log:

1. Payroll file upload.
2. Payroll data validation failure.
3. Payroll batch import success.
4. Payroll correction / re-upload.
5. Payslip generation.
6. Payroll register export.
7. Payslip export.
8. User login and logout.
9. Admin configuration change.

Minimum audit fields:

| Field | Description |
|---|---|
| Audit ID | Unique audit ID |
| Event type | Operation name |
| Entity type | Payroll batch, payslip, user, export |
| Entity ID | Related record ID |
| Performed by | User ID / username |
| Performed at | Timestamp |
| Before value | JSON snapshot before change, where applicable |
| After value | JSON snapshot after change, where applicable |
| IP address | Optional |
| User agent | Optional |

## 4. Database retention requirements

The database must retain:

1. Employee references copied from the authoritative TAC-employeeadmin source when needed for payroll records.
2. Payroll upload batches.
3. Payroll records.
4. Payroll register rows.
5. Payslip generation records.
6. Export history.
7. Audit logs.

No payroll data should be overwritten without version history. If a correction is uploaded, create a new batch/version and mark the previous version as superseded.

## 5. Suggested database entities

### 5.1 employee references

Employee master data is maintained in TAC-employeeadmin. TACAI-PRJ should only store payroll-specific employee references when needed for payroll records.

- employee_id (external TAC-employeeadmin reference, when available)
- employee_no
- employee_name
- payroll_month
- source_system
- captured_at

### 5.2 payroll_upload_batches

- id
- payroll_month
- source_file_name
- uploaded_by
- uploaded_at
- status
- validation_error_count
- imported_record_count
- batch_version
- notes

### 5.3 payroll_records

- id
- batch_id
- employee_id
- employee_no
- employee_name
- payroll_month
- base_salary
- position_allowance
- attendance_allowance
- housing_allowance
- taxable_transportation_allowance
- non_taxable_transportation_allowance
- overtime_allowance
- health_insurance
- pension
- employment_insurance
- income_tax
- gross_pay
- total_deduction
- net_pay
- record_status
- version_no
- created_at
- updated_at

### 5.4 payslips

- id
- payroll_record_id
- employee_id
- payroll_month
- payslip_no
- generated_file_path
- generated_at
- generated_by
- export_count

### 5.5 export_history

- id
- export_type
- file_path
- filter_criteria_json
- generated_by
- generated_at

### 5.6 audit_logs

- id
- event_type
- entity_type
- entity_id
- performed_by
- performed_at
- before_value_json
- after_value_json
- ip_address
- user_agent

## 6. Validation rules

Payroll upload validation must check:

1. Payroll Month exists and follows `YYYY-MM` or equivalent normalized format.
2. Employee No. is present.
3. Employee Name is present.
4. Monetary values are numeric and not negative unless explicitly allowed.
5. Duplicate Employee No. rows in the same upload are flagged.
6. Gross Pay, Total Deduction, and Net Pay are recalculated by the system.
7. If uploaded totals differ from calculated totals, show warning or validation error depending on configuration.
8. Same employee and same payroll month cannot have more than one active payroll record.

## 7. UI requirements

### 7.1 HR upload screen

- Upload monthly payroll Excel.
- Preview parsed rows.
- Show validation errors and warnings.
- Confirm import.
- Show import result summary.

### 7.2 Payroll Register screen

- Search by payroll month, employee number, employee name, department.
- Show monthly register table.
- Show totals by salary item, allowance item, deduction item, gross pay, total deduction, and net pay.
- Export Excel/PDF.

### 7.3 Payslip screen

- Search by payroll month and employee.
- Preview individual payslip.
- Export individual PDF.
- Export monthly payslip bundle.

### 7.4 Audit Log screen

- Search by date range, user, event type, entity type.
- Export audit logs.

## 8. Non-functional requirements

1. All payroll and financial data must be stored securely.
2. All monetary calculations must use decimal arithmetic, not floating-point arithmetic.
3. All date/time values should be stored with timezone awareness.
4. Exported files must be reproducible from retained database records.
5. The system must support Japanese labels and English labels where appropriate.
6. The system must maintain auditability for payroll correction history.
7. Access to payroll data must be role-based.

## 9. Initial implementation phases

### Phase 1 - Foundation

- Define database schema.
- Create payroll Excel parser.
- Create payroll validation logic.
- Store payroll upload batches and payroll records.

### Phase 2 - Payroll Register

- Generate Payroll Register / 給与花名冊 from stored records.
- Add search/filter.
- Add Excel export.

### Phase 3 - Payslip

- Create payslip template renderer.
- Generate individual payslip PDF.
- Generate monthly payslip bundle.

### Phase 4 - Audit

- Add audit log framework.
- Add audit export.

### Phase 5 - User management and hardening

- Add roles and permissions.
- Add security controls.
- Add backup and retention policy.

## 10. Open questions

1. Which tech stack should be used for frontend and backend?
2. Which database should be used for production?
3. Should payroll register corrections require approval before becoming active?
4. Should payslips be emailed to employees or only exported by HR?
5. Should employee master data be uploaded from Excel or maintained inside the system?
6. What is the exact Japanese payslip template layout to reproduce in PDF?
