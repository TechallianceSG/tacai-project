-- ============================================================
-- TACAI Project: PostgreSQL Unified Schema
-- ============================================================

-- ============================================================
-- 考勤 (ts*)
-- ============================================================

-- 8 cols, 41 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS ts_audit_logs (
audit_id TEXT NOT NULL,
module TEXT,
record_id TEXT,
action TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (audit_id)
);

-- 9 cols, 2 rows, pk=employee_id
CREATE TABLE IF NOT EXISTS ts_employees (
employee_no TEXT,
employee_name TEXT,
department TEXT,
email TEXT,
default_scheduled_work_minutes INTEGER,
employee_id TEXT NOT NULL,
record_status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (employee_id)
);

-- 16 cols, 36 rows, pk=lock_id
CREATE TABLE IF NOT EXISTS ts_month_locks (
period_id TEXT,
lock_id TEXT NOT NULL,
work_month TEXT,
period_year INTEGER,
period_month INTEGER,
status TEXT,
lock_status TEXT,
opened_at TIMESTAMPTZ,
opened_by TEXT,
closed_at TIMESTAMPTZ,
closed_by TEXT,
locked_at TIMESTAMPTZ,
locked_by TEXT,
notes TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (lock_id)
);

-- 16 cols, 4 rows, pk=project_code
CREATE TABLE IF NOT EXISTS ts_projects (
project_code TEXT NOT NULL,
project_name TEXT,
customer_name TEXT,
customer_code TEXT,
dispatch_type TEXT,
work_location TEXT,
country TEXT,
prefecture TEXT,
client_approval_required BOOLEAN,
billing_enabled BOOLEAN,
project_id TEXT,
record_status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
billing_rate_per_hour_yen INTEGER,
billing_note TEXT,
    PRIMARY KEY (project_code)
);

-- 93 cols, 10 rows, pk=record_id
CREATE TABLE IF NOT EXISTS ts_timesheet_entries (
employee_no TEXT,
employee_name TEXT,
department TEXT,
entity_id TEXT,
entity_code TEXT,
entity_name TEXT,
department_id TEXT,
department_code TEXT,
department_name TEXT,
team_id TEXT,
team_code TEXT,
team_name TEXT,
customer_name TEXT,
project_code TEXT,
project_name TEXT,
dispatch_type TEXT,
work_location TEXT,
country TEXT,
prefecture TEXT,
business_trip_flag BOOLEAN,
visa_status TEXT,
client_approval_required BOOLEAN,
work_date DATE,
attendance_status TEXT,
start_time TEXT,
end_time TEXT,
break_minutes INTEGER,
scheduled_work_minutes INTEGER,
night_work_minutes INTEGER,
is_legal_holiday BOOLEAN,
is_company_holiday BOOLEAN,
is_late BOOLEAN,
is_early_leave BOOLEAN,
late_minutes INTEGER,
early_leave_minutes INTEGER,
approval_status TEXT,
approved_by TEXT,
approved_at TEXT,
employee_remarks TEXT,
manager_remarks TEXT,
record_id TEXT NOT NULL,
record_status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
employee_master_id TEXT,
employee_source TEXT,
employment_type TEXT,
employment_status TEXT,
customer_code TEXT,
billing_note TEXT,
dispatch_assignment_source TEXT,
dispatch_assignment_history_id TEXT,
dispatch_contract_type TEXT,
dispatch_assignment_location TEXT,
dispatch_work_description TEXT,
dispatch_start_date TEXT,
dispatch_end_date TEXT,
dispatch_supervisor_name TEXT,
dispatch_supervisor_title TEXT,
dispatch_supervisor_phone TEXT,
dispatch_supervisor_email TEXT,
billing_enabled BOOLEAN,
billing_rate_per_hour_yen INTEGER,
dispatch_assignment_matched BOOLEAN,
submitted_at TEXT,
submitted_by TEXT,
rejected_at TEXT,
rejected_by TEXT,
reject_reason TEXT,
reopened_at TEXT,
reopened_by TEXT,
weekday TEXT,
gross_work_minutes INTEGER,
cross_midnight_flag BOOLEAN,
actual_work_minutes INTEGER,
overtime_minutes INTEGER,
legal_holiday_work_minutes INTEGER,
company_holiday_work_minutes INTEGER,
holiday_work_minutes INTEGER,
break_required_minutes INTEGER,
break_shortage_minutes INTEGER,
break_warning TEXT,
employee_no_snapshot TEXT,
employee_name_snapshot TEXT,
entered_by TEXT,
entered_by_user_id TEXT,
entered_by_name TEXT,
entry_mode TEXT,
on_behalf_of_employee_no TEXT,
entry_source TEXT,
assistance_reason TEXT,
assistance_note TEXT,
employee_id TEXT,
    PRIMARY KEY (record_id)
);

-- ============================================================
-- 员工管理 (emp*)
-- ============================================================

-- 14 cols, 259 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS emp_audit_logs (
audit_id TEXT NOT NULL,
employee_id TEXT,
actor TEXT,
action TEXT,
section TEXT,
changed_fields JSONB,
summary JSONB,
created_at TIMESTAMPTZ,
module TEXT,
record_id TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (audit_id)
);

-- 26 cols, 17 rows, pk=document_id
CREATE TABLE IF NOT EXISTS emp_employee_onboarding_documents (
document_id TEXT NOT NULL,
onboarding_request_id TEXT,
document_type TEXT,
direction TEXT,
signing_mode TEXT,
status TEXT,
title TEXT,
original_filename TEXT,
stored_filename TEXT,
storage_reference TEXT,
signed_stored_filename TEXT,
signed_storage_reference TEXT,
signed_pdf_stored_filename TEXT,
signed_pdf_storage_reference TEXT,
signed_pdf_content_type TEXT,
signed_pdf_file_size_bytes TEXT,
signed_pdf_created_at TEXT,
signed_pdf_status TEXT,
content_type TEXT,
file_size_bytes TEXT,
sha256_original TEXT,
sha256_signed TEXT,
sha256_signed_pdf TEXT,
uploaded_by TEXT,
uploaded_at TIMESTAMPTZ,
notes TEXT,
    PRIMARY KEY (document_id)
);

-- 42 cols, 6 rows, pk=onboarding_request_id
CREATE TABLE IF NOT EXISTS emp_employee_onboarding_requests (
onboarding_request_id TEXT NOT NULL,
candidate_name TEXT,
candidate_email TEXT,
planned_start_date TIMESTAMPTZ,
employment_type TEXT,
onboarding_category TEXT,
status TEXT,
token_hash TEXT,
token_expiry TIMESTAMPTZ,
token_created_at TIMESTAMPTZ,
token_last_used_at TIMESTAMPTZ,
created_by TEXT,
created_at TIMESTAMPTZ,
updated_by TEXT,
updated_at TIMESTAMPTZ,
sent_at TIMESTAMPTZ,
email_sender TEXT,
email_status TEXT,
email_draft_status TEXT,
email_draft_prepared_by TEXT,
email_draft_prepared_at TEXT,
email_review_confirmed_by TEXT,
email_review_confirmed_at TEXT,
email_to TEXT,
email_cc_default TEXT,
email_cc_additional TEXT,
email_sent_to_snapshot TEXT,
email_sent_cc_snapshot TEXT,
email_subject_snapshot TEXT,
email_template_version TEXT,
verification_code_hash TEXT,
verification_code_created_at TIMESTAMPTZ,
verification_code_expiry TIMESTAMPTZ,
verification_attempts TEXT,
verification_locked_until TEXT,
verification_last_sent_at TIMESTAMPTZ,
verification_delivery_status TEXT,
verification_verified_at TEXT,
verification_session_id_hash TEXT,
hr_notes TEXT,
review_notes TEXT,
imported_employee_id TEXT,
    PRIMARY KEY (onboarding_request_id)
);

-- 14 cols, 46 rows, pk=employee_id
CREATE TABLE IF NOT EXISTS emp_employees (
employee_id TEXT NOT NULL,
employee_number TEXT,
profile JSONB,
employment JSONB,
payroll JSONB,
visa JSONB,
dispatch_compliance JSONB,
language_profile JSONB,
skills_profile JSONB,
documents JSONB,
employment_history JSONB,
visa_history JSONB,
dispatch_assignment_history JSONB,
metadata JSONB,
    PRIMARY KEY (employee_id)
);

-- 18 cols, 1 rows, pk=parameter_id
CREATE TABLE IF NOT EXISTS emp_system_parameters (
parameter_id TEXT NOT NULL,
module TEXT,
category TEXT,
subcategory TEXT,
scenario TEXT,
display_name TEXT,
description TEXT,
enabled BOOLEAN,
value_type TEXT,
value JSONB,
secret_status TEXT,
environment TEXT,
status TEXT,
sort_order INTEGER,
created_at TIMESTAMPTZ,
created_by TEXT,
updated_at TIMESTAMPTZ,
updated_by TEXT,
    PRIMARY KEY (parameter_id)
);

-- ============================================================
-- 费用报销 (rmb*)
-- ============================================================

-- 35 cols, 8 rows, pk=None
CREATE TABLE IF NOT EXISTS rmb_claims (
status TEXT,
employee_no TEXT,
employee_name TEXT,
department TEXT,
claim_month TEXT,
expense_date TEXT,
category TEXT,
vendor_name TEXT,
invoice_or_receipt_number TEXT,
qualified_invoice_number TEXT,
is_qualified_invoice TEXT,
currency TEXT,
total_amount INTEGER,
amount_excluding_tax INTEGER,
tax_amount INTEGER,
tax_rate TEXT,
payment_method TEXT,
business_purpose TEXT,
notes TEXT,
finance_notes TEXT,
reject_reason TEXT,
attachment JSONB,
ocr_status TEXT,
ocr_draft JSONB,
claim_id TEXT,
claim_no TEXT,
record_status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
submitted_at TEXT,
approved_at TEXT,
approved_by TEXT,
rejected_at TEXT,
rejected_by TEXT,
paid_at TEXT
);

-- ============================================================
-- 薪资SG (pay_sg*)
-- ============================================================

-- 8 cols, 649 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS pay_sg_audit_logs (
audit_id TEXT NOT NULL,
module TEXT,
record_id TEXT,
action TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (audit_id)
);

-- 67 cols, 30 rows, pk=record_id
CREATE TABLE IF NOT EXISTS pay_sg_monthly_salary_records (
record_id TEXT NOT NULL,
sheet_id TEXT,
payroll_month TEXT,
country_code TEXT,
entity_id TEXT,
employee_id TEXT,
employee_number TEXT,
employee_name TEXT,
email TEXT,
department_label TEXT,
team_label TEXT,
salary_type TEXT,
bank_name TEXT,
bank_branch_name TEXT,
bank_swift_code TEXT,
bank_account_type TEXT,
bank_account_name TEXT,
bank_account_number TEXT,
payroll_currency TEXT,
basic_salary NUMERIC,
hourly_rate NUMERIC,
daily_rate NUMERIC,
standard_monthly_hours NUMERIC,
overtime_hourly_rate NUMERIC,
standard_work_days NUMERIC,
standard_work_hours NUMERIC,
actual_work_days NUMERIC,
actual_work_hours NUMERIC,
paid_leave_days NUMERIC,
unpaid_leave_days NUMERIC,
sick_leave_days NUMERIC,
overtime_hours NUMERIC,
late_night_hours NUMERIC,
holiday_hours NUMERIC,
absence_days NUMERIC,
attendance_source TEXT,
timesheet_ref TEXT,
fixed_allowance NUMERIC,
performance_bonus NUMERIC,
performance_reference NUMERIC,
bonus NUMERIC,
other_payment NUMERIC,
recurring_deductions NUMERIC,
other_deduction NUMERIC,
income_tax NUMERIC,
cpf_applicable BOOLEAN,
cpf_input_mode TEXT,
cpf_employee_manual NUMERIC,
cpf_employer_manual NUMERIC,
skill_development_levy NUMERIC,
foreign_worker_levy NUMERIC,
base_pay_calculated NUMERIC,
gross_pay NUMERIC,
cpf_employee INTEGER,
cpf_employer INTEGER,
deduction_total NUMERIC,
net_pay NUMERIC,
employer_cost_total NUMERIC,
calculation_messages JSONB,
status TEXT,
hr_confirmed_at TEXT,
hr_confirmed_by TEXT,
manager_review_status TEXT,
manager_review_comment TEXT,
version INTEGER,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (record_id)
);

-- 27 cols, 2 rows, pk=sheet_id
CREATE TABLE IF NOT EXISTS pay_sg_monthly_salary_sheets (
sheet_id TEXT NOT NULL,
country_code TEXT,
entity_id TEXT,
payroll_month TEXT,
status TEXT,
version INTEGER,
employee_count INTEGER,
standard_work_days INTEGER,
standard_work_hours INTEGER,
attendance_source TEXT,
attendance_locked BOOLEAN,
basic_info_confirmed_at TEXT,
basic_info_confirmed_by TEXT,
calculated_at TEXT,
calculated_by TEXT,
gross_total NUMERIC,
deduction_total NUMERIC,
net_total NUMERIC,
employer_cost_total NUMERIC,
currency_totals JSONB,
created_at TIMESTAMPTZ,
created_by TEXT,
updated_at TIMESTAMPTZ,
notes TEXT,
last_calculation_summary JSONB,
manager_approved_at TIMESTAMPTZ,
manager_approved_by TEXT,
    PRIMARY KEY (sheet_id)
);

-- 16 cols, 2 rows, pk=batch_id
CREATE TABLE IF NOT EXISTS pay_sg_payroll_batches (
batch_id TEXT NOT NULL,
country_code TEXT,
entity_id TEXT,
payroll_month TEXT,
status TEXT,
version INTEGER,
employee_count INTEGER,
gross_total NUMERIC,
deduction_total NUMERIC,
net_total NUMERIC,
employer_cost_total NUMERIC,
currency_totals JSONB,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
created_by TEXT,
notes TEXT,
    PRIMARY KEY (batch_id)
);

-- 48 cols, 30 rows, pk=record_id
CREATE TABLE IF NOT EXISTS pay_sg_payroll_records_sg (
record_id TEXT NOT NULL,
batch_id TEXT,
payroll_month TEXT,
country_code TEXT,
entity_id TEXT,
employee_id TEXT,
employee_number TEXT,
employee_name TEXT,
email TEXT,
salary_type TEXT,
basic_salary NUMERIC,
hourly_rate NUMERIC,
daily_rate NUMERIC,
standard_work_days NUMERIC,
standard_work_hours NUMERIC,
work_days NUMERIC,
work_hours NUMERIC,
fixed_allowance NUMERIC,
performance_bonus NUMERIC,
bonus NUMERIC,
other_payment NUMERIC,
recurring_deductions NUMERIC,
other_deduction NUMERIC,
income_tax NUMERIC,
cpf_applicable BOOLEAN,
cpf_input_mode TEXT,
cpf_employee INTEGER,
cpf_employer INTEGER,
skill_development_levy NUMERIC,
foreign_worker_levy NUMERIC,
gross_pay NUMERIC,
deduction_total NUMERIC,
net_pay NUMERIC,
employer_cost_total NUMERIC,
base_pay_calculated NUMERIC,
status TEXT,
calculation_messages JSONB,
employee_confirmation_status TEXT,
employee_comment TEXT,
bank_name TEXT,
bank_branch_name TEXT,
bank_swift_code TEXT,
bank_account_type TEXT,
bank_account_name TEXT,
bank_account_number TEXT,
payroll_currency TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (record_id)
);

-- 19 cols, 1 rows, pk=release_id
CREATE TABLE IF NOT EXISTS pay_sg_payroll_release_batches (
release_id TEXT NOT NULL,
source_sheet_id TEXT,
country_code TEXT,
entity_id TEXT,
payroll_month TEXT,
status TEXT,
employee_count INTEGER,
payslip_count INTEGER,
email_sent_count INTEGER,
email_failed_count INTEGER,
gross_total NUMERIC,
deduction_total NUMERIC,
net_total NUMERIC,
employer_cost_total NUMERIC,
currency_totals JSONB,
created_at TIMESTAMPTZ,
created_by TEXT,
updated_at TIMESTAMPTZ,
notes TEXT,
    PRIMARY KEY (release_id)
);

-- 8 cols, 30 rows, pk=batch_id
CREATE TABLE IF NOT EXISTS pay_sg_payslip_email_deliveries (
delivery_id TEXT,
payslip_id TEXT,
batch_id TEXT NOT NULL,
recipient TEXT,
status TEXT,
message TEXT,
created_at TIMESTAMPTZ,
sent_at TIMESTAMPTZ,
    PRIMARY KEY (batch_id)
);

-- 26 cols, 45 rows, pk=record_id
CREATE TABLE IF NOT EXISTS pay_sg_payslips (
payslip_id TEXT,
record_id TEXT NOT NULL,
batch_id TEXT,
employee_id TEXT,
employee_email TEXT,
file_name TEXT,
file_path TEXT,
status TEXT,
created_at TIMESTAMPTZ,
employee_number TEXT,
employee_name TEXT,
department_label TEXT,
gross_pay NUMERIC,
net_pay NUMERIC,
salary_type TEXT,
payroll_month TEXT,
updated_at TIMESTAMPTZ,
release_id TEXT,
sheet_id TEXT,
team_label TEXT,
currency TEXT,
deduction_total NUMERIC,
hr_confirmed BOOLEAN,
email_draft_status TEXT,
email_draft_prepared_at TEXT,
email_draft_prepared_by TEXT,
    PRIMARY KEY (record_id)
);

-- 50 cols, 15 rows, pk=employee_id
CREATE TABLE IF NOT EXISTS pay_sg_salary_master (
salary_master_id TEXT,
employee_id TEXT NOT NULL,
employee_number TEXT,
employee_name TEXT,
email TEXT,
country_code TEXT,
entity_id TEXT,
department TEXT,
department_id TEXT,
department_label TEXT,
team_id TEXT,
team_label TEXT,
employment_status TEXT,
employeeadmin_status TEXT,
employeeadmin_payroll_ready BOOLEAN,
employeeadmin_readiness_percent NUMERIC,
employeeadmin_last_seen_at TIMESTAMPTZ,
salary_type TEXT,
basic_salary NUMERIC,
hourly_rate NUMERIC,
daily_rate NUMERIC,
standard_work_days NUMERIC,
standard_work_hours NUMERIC,
standard_monthly_hours NUMERIC,
overtime_hourly_rate NUMERIC,
fixed_allowance NUMERIC,
performance_bonus NUMERIC,
recurring_deductions NUMERIC,
cpf_applicable BOOLEAN,
cpf_input_mode TEXT,
cpf_employee_manual NUMERIC,
cpf_employer_manual NUMERIC,
skill_development_levy NUMERIC,
foreign_worker_levy NUMERIC,
bank_name TEXT,
bank_branch_name TEXT,
bank_swift_code TEXT,
bank_account_type TEXT,
bank_account_name TEXT,
bank_account_number TEXT,
employeeadmin_bank_snapshot JSONB,
payroll_currency TEXT,
notes TEXT,
active BOOLEAN,
deactivated_at TEXT,
deactivated_by TEXT,
deactivation_reason TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
source TEXT,
    PRIMARY KEY (employee_id)
);

-- ============================================================
-- 薪资JP (pay_jp*)
-- ============================================================

-- 12 cols, 19 rows, pk=item_id
CREATE TABLE IF NOT EXISTS pay_jp_payroll_item_definitions (
item_id TEXT NOT NULL,
code TEXT,
category TEXT,
sub_category TEXT,
labels JSONB,
taxable BOOLEAN,
social_insurance_base BOOLEAN,
employment_insurance_base BOOLEAN,
payslip_visible BOOLEAN,
requires_reason BOOLEAN,
display_order INTEGER,
status TEXT,
    PRIMARY KEY (item_id)
);

-- 20 cols, 1 rows, pk=entity_id
CREATE TABLE IF NOT EXISTS pay_jp_payroll_parameters (
parameter_id TEXT,
country_code TEXT,
entity_id TEXT NOT NULL,
status TEXT,
effective_start TIMESTAMPTZ,
effective_end TIMESTAMPTZ,
rule_version_id TEXT,
standard_monthly_work_days INTEGER,
standard_monthly_work_hours INTEGER,
standard_daily_work_hours INTEGER,
overtime_multiplier TEXT,
late_night_multiplier TEXT,
holiday_multiplier TEXT,
health_insurance_employee_rate TEXT,
health_insurance_employer_rate TEXT,
pension_employee_rate TEXT,
pension_employer_rate TEXT,
employment_insurance_employee_rate TEXT,
employment_insurance_employer_rate TEXT,
notes TEXT,
    PRIMARY KEY (entity_id)
);

-- ============================================================
-- 用户管理 (ua*)
-- ============================================================

-- 6 cols, 86 rows, pk=permission_id
CREATE TABLE IF NOT EXISTS ua_permissions (
permission_id TEXT NOT NULL,
permission_key TEXT,
module TEXT,
action TEXT,
description TEXT,
active BOOLEAN,
    PRIMARY KEY (permission_id)
);

-- 4 cols, 291 rows, pk=mapping_id
CREATE TABLE IF NOT EXISTS ua_role_permission_mapping (
mapping_id TEXT NOT NULL,
role_id TEXT,
permission_id TEXT,
active BOOLEAN,
    PRIMARY KEY (mapping_id)
);

-- 7 cols, 7 rows, pk=role_id
CREATE TABLE IF NOT EXISTS ua_roles (
role_id TEXT NOT NULL,
role_key TEXT,
role_name TEXT,
description_key TEXT,
active BOOLEAN,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (role_id)
);

-- 8 cols, 271 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS ua_user_audit_logs (
audit_id TEXT NOT NULL,
module TEXT,
record_id TEXT,
user TEXT,
action TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (audit_id)
);

-- 11 cols, 10 rows, pk=mapping_id
CREATE TABLE IF NOT EXISTS ua_user_entity_mapping (
mapping_id TEXT NOT NULL,
user_id TEXT,
entity_id TEXT,
entity_code TEXT,
entity_name_en TEXT,
entity_name_ja TEXT,
entity_name_zh TEXT,
is_default BOOLEAN,
active BOOLEAN,
assigned_at TIMESTAMPTZ,
assigned_by TEXT,
    PRIMARY KEY (mapping_id)
);

-- 7 cols, 20 rows, pk=mapping_id
CREATE TABLE IF NOT EXISTS ua_user_role_mapping (
mapping_id TEXT NOT NULL,
user_id TEXT,
role_id TEXT,
assigned_at TIMESTAMPTZ,
assigned_by TEXT,
active BOOLEAN,
created_at TIMESTAMPTZ,
    PRIMARY KEY (mapping_id)
);

-- 14 cols, 168 rows, pk=user_id
CREATE TABLE IF NOT EXISTS ua_user_sessions (
session_id TEXT,
user_id TEXT NOT NULL,
login_time TIMESTAMPTZ,
logout_time TIMESTAMPTZ,
ip_address TEXT,
browser TEXT,
device TEXT,
active BOOLEAN,
expires_at TIMESTAMPTZ,
entity_id TEXT,
entity_code TEXT,
entity_name_en TEXT,
entity_name_ja TEXT,
entity_name_zh TEXT,
    PRIMARY KEY (user_id)
);

-- 29 cols, 10 rows, pk=user_id
CREATE TABLE IF NOT EXISTS ua_users (
user_id TEXT NOT NULL,
username TEXT,
display_name TEXT,
email TEXT,
phone TEXT,
department TEXT,
position TEXT,
status TEXT,
language_preference TEXT,
password_hash TEXT,
password_last_changed TIMESTAMPTZ,
last_login TIMESTAMPTZ,
failed_login_count INTEGER,
account_locked BOOLEAN,
account_locked_date TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
deleted BOOLEAN,
user_type TEXT,
linked_employee_id TEXT,
linked_employee_no TEXT,
linked_employee_name TEXT,
linked_entity_id TEXT,
linked_entity_code TEXT,
linked_entity_name TEXT,
linked_department_id TEXT,
linked_department_code TEXT,
linked_department_name TEXT,
created_by TEXT,
    PRIMARY KEY (user_id)
);

-- ============================================================
-- 主数据 (md*)
-- ============================================================

-- 12 cols, 38 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS md_audit_logs (
audit_id TEXT NOT NULL,
module TEXT,
record_type TEXT,
record_id TEXT,
action TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
change_reason TEXT,
changed_fields JSONB,
version_id TEXT,
    PRIMARY KEY (audit_id)
);

-- 9 cols, 15 rows, pk=department_id
CREATE TABLE IF NOT EXISTS md_departments (
department_id TEXT NOT NULL,
department_code TEXT,
department_name_en TEXT,
department_name_ja TEXT,
department_name_zh TEXT,
entity_id TEXT,
status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (department_id)
);

-- 14 cols, 5 rows, pk=entity_id
CREATE TABLE IF NOT EXISTS md_entities (
entity_id TEXT NOT NULL,
entity_code TEXT,
entity_name_en TEXT,
entity_name_ja TEXT,
country TEXT,
currency TEXT,
status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
entity_name_zh TEXT,
entity_type TEXT,
legal_name TEXT,
registration_number TEXT,
tax_registration_number TEXT,
    PRIMARY KEY (entity_id)
);

-- 11 cols, 22 rows, pk=record_id
CREATE TABLE IF NOT EXISTS md_masterdata_versions (
version_id TEXT,
record_type TEXT,
record_id TEXT NOT NULL,
version_number INTEGER,
action TEXT,
changed_by TEXT,
changed_at TIMESTAMPTZ,
change_reason TEXT,
changed_fields JSONB,
restored_from_version_id TEXT,
data_snapshot JSONB,
    PRIMARY KEY (record_id)
);

-- 18 cols, 1 rows, pk=parameter_id
CREATE TABLE IF NOT EXISTS md_system_parameters (
parameter_id TEXT NOT NULL,
module TEXT,
category TEXT,
subcategory TEXT,
scenario TEXT,
display_name TEXT,
description TEXT,
enabled BOOLEAN,
value_type TEXT,
value JSONB,
secret_status TEXT,
environment TEXT,
status TEXT,
sort_order INTEGER,
created_at TIMESTAMPTZ,
created_by TEXT,
updated_at TIMESTAMPTZ,
updated_by TEXT,
    PRIMARY KEY (parameter_id)
);

-- 9 cols, 6 rows, pk=department_id
CREATE TABLE IF NOT EXISTS md_teams (
team_id TEXT,
team_code TEXT,
team_name_en TEXT,
team_name_ja TEXT,
team_name_zh TEXT,
department_id TEXT NOT NULL,
status TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (department_id)
);

-- ============================================================
-- 门户 (pt*)
-- ============================================================

-- 7 cols, 4 rows, pk=record_id
CREATE TABLE IF NOT EXISTS pt_audit_logs (
module TEXT,
record_id TEXT NOT NULL,
action TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (record_id)
);

-- 10 cols, 11 rows, pk=module_key
CREATE TABLE IF NOT EXISTS pt_modules (
module_key TEXT NOT NULL,
label TEXT,
labels JSONB,
description TEXT,
descriptions JSONB,
url TEXT,
status TEXT,
statuses JSONB,
required_permission TEXT,
enabled BOOLEAN,
    PRIMARY KEY (module_key)
);

-- 4 cols, 11 rows, pk=None
CREATE TABLE IF NOT EXISTS pt_services (
name TEXT,
url TEXT,
health TEXT,
required_permission TEXT
);

-- 9 cols, 1 rows, pk=None
CREATE TABLE IF NOT EXISTS pt_users (
id TEXT,
username TEXT,
display_name TEXT,
role TEXT,
active BOOLEAN,
password_salt TEXT,
password_hash TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ
);

-- ============================================================
-- 消息中心 (msg*)
-- ============================================================

-- 8 cols, 1 rows, pk=template_id
CREATE TABLE IF NOT EXISTS msg_workflow_templates (
template_id TEXT NOT NULL,
template_name TEXT,
biz_type TEXT,
status TEXT,
steps JSONB,
created_by TEXT,
created_at TIMESTAMPTZ,
updated_at TIMESTAMPTZ,
    PRIMARY KEY (template_id)
);

-- ============================================================
-- 面试系统 (iv*)
-- ============================================================

-- 22 cols, 2 rows, pk=user_id
CREATE TABLE IF NOT EXISTS iv_analysis_runs (
analysis_id TEXT,
entity_id TEXT,
entity_code TEXT,
entity_name_en TEXT,
department TEXT,
team TEXT,
user_id TEXT NOT NULL,
user_display_name TEXT,
created_by TEXT,
feature TEXT,
feature_label TEXT,
candidate_name TEXT,
client_company TEXT,
target_role TEXT,
source TEXT,
candidate_consent_status TEXT,
input_summary JSONB,
result_summary JSONB,
report_path TEXT,
report_relative_path TEXT,
created_at TIMESTAMPTZ,
status TEXT,
    PRIMARY KEY (user_id)
);

-- 8 cols, 2 rows, pk=audit_id
CREATE TABLE IF NOT EXISTS iv_interview_ready_audit_logs (
audit_id TEXT NOT NULL,
module TEXT,
record_id TEXT,
action TEXT,
user TEXT,
timestamp TIMESTAMPTZ,
before_value JSONB,
after_value JSONB,
    PRIMARY KEY (audit_id)
);

-- 12 cols, 2 rows, pk=report_id
CREATE TABLE IF NOT EXISTS iv_report_index (
report_id TEXT NOT NULL,
analysis_id TEXT,
feature TEXT,
candidate_name TEXT,
client_company TEXT,
target_role TEXT,
created_at TIMESTAMPTZ,
created_by TEXT,
entity_code TEXT,
report_path TEXT,
report_relative_path TEXT,
status TEXT,
    PRIMARY KEY (report_id)
);

-- ============================================================
-- 员工自助 (ss*)
-- ============================================================
