# TACAI User Management Permission Catalog V1

## User Management

- `user_management.access` — access User Management.
- `user_management.manage_users` — create/edit/deactivate users.
- `user_management.manage_roles` — manage role assignments.
- `user_management.manage_permissions` — manage permissions and role-permission mappings.
- `user_management.audit.view` — view user management audit logs.

## Master Data Management — `TACAI-Core/masterdata`

- `masterdata.access` — access Master Data Management.
- `masterdata.view` — view Entity, Department, and Team master data.
- `masterdata.maintain` — create/update/soft-delete master data.
- `masterdata.admin` — reserved for advanced Master Data governance and settings.

Entity-scoped access is an additional authorization dimension, not a replacement for RBAC. The target access check is a valid User_admin session, an active selected Entity assignment, and the required `masterdata.*` permission. `masterdata.admin` may support cross-entity governance in later phases, but the local MVP still records one selected Entity in the active session.

## Employee Management — `TAC-employeeadmin`

- `employee_management.access` — access Employee Management.
- `employee_management.view` — view employee records.
- `employee_management.edit` — create/edit employee master records.
- `employee_management.payroll.view` — view payroll-related employee data.
- `employee_management.payroll.edit` — edit payroll-related employee data.
- `employee_management.visa.view` — view visa/residence/passport metadata.
- `employee_management.visa.edit` — edit visa/residence/passport metadata.
- `employee_management.documents.manage` — manage employee document metadata/uploads.
- `employee_management.reports.view` — view employee management reports.
- `employee_management.export` — export safe employee data.

## Timesheet — `TAC-timesheet`

- `timesheet.access` — access Timesheet Management.
- `timesheet.submit` — submit own timesheet.
- `timesheet.edit_own` — edit own timesheet.
- `timesheet.approve` — approve timesheets.
- `timesheet.team_view` — view team timesheets.
- `timesheet.billing.view` — view billing/invoice-related timesheet data, if enabled.

## Reimbursement / Expense — `TAC-reimbursement`

- `reimbursement.access` — access reimbursement module.
- `reimbursement.submit` — submit own reimbursement claim.
- `reimbursement.view_own` — view own reimbursement claims.
- `reimbursement.approve` — approve reimbursement claims.
- `reimbursement.payment` — process expense payment.
- `reimbursement.reports.view` — view reimbursement reports.

## Payroll / HR Finance — `TACAI-PRJ`

- `payroll.access` — access payroll module.
- `payroll.view` — view payroll data.
- `payroll.edit` — edit payroll data.
- `payroll.reports.view` — view payroll reports.
- `financial_reports.view` — view financial reports.

## InterviewReady — `InterviewReady`

- `interview_ready.access` — access InterviewReady from TACAI Portal and direct module URL.
- `interview_ready.jd_insight` — run JD Insight analysis.
- `interview_ready.resume_match` — run Resume Match analysis.
- `interview_ready.mock_interview` — generate mock interview questions and coaching guidance.
- `interview_ready.japan_risk` — run Japan interview communication risk analysis.
- `interview_ready.report.view` — view generated InterviewReady reports/history.
- `interview_ready.report.export` — export or download InterviewReady report outputs.
- `interview_ready.audit.view` — view InterviewReady audit records after the audit viewer is added.

Default V1 access direction: System Admin and HR Manager receive business analysis permissions. Finance, Manager, and Employee do not receive InterviewReady access by default because candidate resumes, client JD notes, and interview feedback are recruitment-sensitive data.

## Future Training

- `training.access`.
- `training.manage`.
- `training.view_own`.

## Future Vendor Expense

- `vendor_expense.access`.
- `vendor_expense.submit`.
- `vendor_expense.approve`.
- `vendor_expense.payment`.

## Client Revenue / Customer Billing

- `client_revenue.access` — access Customer Billing / Client Revenue.
- `client_revenue.view` — view customer billing and customer master records.
- `client_revenue.manage` — manage billing documents, status changes, and payment registration.
- `client_revenue.reports.view` — view AR reports.
- `client_revenue.customer_master.maintain` — create, update, deactivate, and restore Customer Master records in TACAI Master Data.

Customer Master is maintained in `TACAI-Core/masterdata` but is finance/client-revenue owned. It should not use `masterdata.maintain`, because HR Manager has that permission for organization masters.

## V1 Role Mapping Direction

### System Admin

All permissions.

### HR Manager

- Employee Management permissions.
- Timesheet access/view as needed.
- Reimbursement access/approval as needed.
- Payroll view/edit if approved for HR payroll workflows.
- Master Data access/view/maintain for Entity, Department, and Team.
- No user management role/permission administration.

### Finance

- Payroll access/view/edit as approved.
- Reimbursement payment.
- Financial reports.
- Master Data access/view only.
- No employee master edit by default.

### Manager

- Timesheet approval.
- Team view.
- Reimbursement approval.
- Master Data access/view only.
- No payroll data access.

### Employee

- View own profile.
- Submit own timesheet.
- Submit own reimbursement.
- View own payslip.
- Master Data access/view only.
- No access to other employees by default.
