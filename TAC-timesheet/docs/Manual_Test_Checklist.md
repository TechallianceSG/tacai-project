# Manual Test Checklist

Use this checklist after each TAC-timesheet milestone. Prefer unique employee numbers, project codes, and work dates for every test run to avoid duplicate validation conflicts.

## 1. Startup and health

1. Start the app:

   ```bash
   cd /Users/terencewang/Documents/claude-project/TAC-timesheet
   python3 backend/app.py --host 127.0.0.1 --port 8002
   ```

2. Open or check:

   - `http://127.0.0.1:8002/health` returns `OK`.
   - `http://127.0.0.1:8002/` loads the dashboard.
   - `http://127.0.0.1:8002/timesheets` loads the timesheet list.
   - `http://127.0.0.1:8002/employees` loads employee master.
   - `http://127.0.0.1:8002/projects` loads project/customer master.
   - `http://127.0.0.1:8002/audit-logs` loads the read-only audit viewer.

## 2. Language and EmployeeAdmin integration

1. Open `/?lang=zh`, `/?lang=ja`, and `/?lang=en`; confirm navigation and dashboard labels switch language.
2. Open `/timesheet-new?lang=zh`, `/timesheet-new?lang=ja`, and `/timesheet-new?lang=en`; confirm the main form labels switch language.
3. Start TAC-employeeadmin on port `8004` and confirm `/api/timesheet/employees` is protected by User_admin session validation.
4. After login, confirm Timesheet employee selectors show employees from TAC-employeeadmin.
5. Stop TAC-employeeadmin or make it unavailable; confirm Timesheet shows fallback warning and can use local `database/employees.json` records.
6. Confirm new EmployeeAdmin-backed timesheet rows snapshot employee number, name, department, source, and EmployeeAdmin employee ID when available.

## 3. Employee source page

1. Confirm the main Timesheet navigation no longer shows an Employees maintenance module.
2. Open `/employees?lang=zh` directly and confirm it is a read-only employee source/status page.
3. Confirm the page links to TAC-employeeadmin for employee master maintenance.
4. Confirm direct access to `/employee-new` and `/employee-edit` shows that employee master is managed in TAC-employeeadmin instead of opening a Timesheet employee CRUD form.
5. Confirm direct POST attempts to `/employee-new`, `/employee-edit`, or `/employee-delete` do not create/update/delete employee master data from Timesheet.

## 4. Project/customer master

1. Create a project with a unique Project Code.
2. Confirm the project appears in the project list.
3. Try creating another active project with the same Project Code; confirm validation blocks it.
4. Edit project name, customer name, dispatch type, work location, country/prefecture, and billing flag.
5. Confirm edits are saved and `created_at` is preserved.
6. Confirm create/update audit rows were appended to `database/audit_logs.json`.
7. Soft-delete the project.
8. Confirm a soft-delete audit row was appended to `database/audit_logs.json`.
9. Confirm the deleted project no longer appears in active timesheet project selectors.

## 5. Organization master and Timesheet organization snapshots

1. Create an Entity, Department, and Team from `/organization`, `/entities`, `/departments`, and `/teams`.
2. Confirm create/update/soft-delete actions append `master_data.entity`, `master_data.department`, and `master_data.team` audit rows.
3. Save a Timesheet row using an employee source record that carries `team_id`, `department_id`, or organization code/name fields.
4. Confirm the saved row in `database/timesheet_entries.json` includes `entity_*`, `department_*`, and `team_*` snapshot fields when available.
5. Confirm legacy rows without organization fields still load and appear as `Unassigned` in the organization monthly summary.
6. Export `/timesheets.csv` and confirm it includes both legacy `department` and structured organization fields.
7. Confirm changing organization master records does not automatically rewrite historical Timesheet rows.

## 6. Mobile clock entry and dispatch assignment auto-fill

1. Open `/clock-entry?lang=zh` on a mobile-width browser and confirm the page shows date selection, start time, end time, break minutes, date/status badges, and read-only dispatch assignment fields.
2. Confirm an unlinked User_admin account shows a clear employee-linking warning instead of an all-employee selector.
3. With a User_admin account linked to an EmployeeAdmin employee, enter `09:00`, `18:00`, and `60`; confirm the row saves as a Draft timesheet record.
4. Confirm the saved row appended a `timesheet.entry` audit row.
5. Open `/clock-entry?work_date=<current-month-date>` and confirm a current-month date can be created/edited while Draft or Rejected.
6. Open `/clock-entry?work_date=<previous-month-date>` and confirm a previous-month date can be created/edited while the month is not locked.
7. Lock the previous month and confirm `/clock-entry?work_date=<locked-month-date>` is read-only and cannot save changes.
8. For an employee/date with a matching EmployeeAdmin dispatch assignment, confirm the Timesheet row snapshots `customer_name`, `project_name`, `dispatch_assignment_matched`, date range, and dispatch metadata while leaving `project_code` blank.
9. For an employee/date without a matching dispatch assignment, confirm the row still saves and customer/project fields stay blank.
10. Re-open `/clock-entry` for the same date and confirm it edits the existing Draft/Rejected blank-project record rather than creating a duplicate.
11. Submit or approve the row and confirm `/clock-entry` becomes read-only for that date.
12. Open `/my-timesheet?lang=zh` and confirm the employee can switch between current month and previous month, see summary cards, status counts, missing weekday links, and daily record cards.
13. Confirm missing weekday links open `/clock-entry?work_date=...` for direct input.
14. Confirm HR/Admin can open the full `/timesheet-edit` page later and select a real Timesheet project if needed.

## 7. Timesheet CRUD and calculations

1. Create a normal row, for example `09:00` to `18:00` with `60` break minutes.
2. Confirm actual work is `8h 00m`.
3. Create an overtime row, for example `09:00` to `20:00` with `60` break minutes.
4. Confirm overtime is calculated from the employee default scheduled work minutes.
5. Try creating a duplicate active row for the same employee, work date, and project; confirm validation blocks it.
6. Confirm the successful create action appended a `timesheet.entry` audit row.
7. Edit a `Draft` row and confirm the updated values are shown.
8. Confirm the edit action appended a `timesheet.entry` audit row.
9. Soft-delete a `Draft` row and confirm it disappears from normal lists and summaries.
10. Confirm the soft-delete action appended a `timesheet.entry` audit row.

## 8. Approval workflow

1. Submit a `Draft` row.
2. Confirm the row becomes `Submitted`.
3. Confirm a `Submitted` row cannot be edited or soft-deleted.
4. Approve a `Submitted` row.
5. Confirm the row becomes `Approved`.
6. Reopen an `Approved` row.
7. Confirm the row returns to `Draft`.
8. Submit the row again.
9. Reject the submitted row with a reason.
10. Confirm the row becomes `Rejected` and the reject reason appears.
11. Edit the `Rejected` row and submit it again.
12. Confirm `submit`, `approve`, `reopen`, and `reject` actions appended `timesheet.entry` audit rows.

## 9. Monthly lock

1. Choose a test month with active rows.
2. Confirm lock is unavailable while any row in the month is `Draft`, `Submitted`, or `Rejected`.
3. Approve all active rows in that month.
4. Lock the month from the monthly closing panel.
5. Confirm `database/month_locks.json` contains a lock record.
6. Confirm a `timesheet.month_lock` audit row was appended.
7. Confirm locked-month rows show no mutation actions.
8. Try creating a new row in the locked month; confirm validation blocks it.
9. Try editing, soft-deleting, submitting, approving, rejecting, or reopening a locked-month row; confirm validation blocks it.

## 10. Timesheet accounting period open/close

1. Restart TAC-timesheet and confirm `database/month_locks.json` contains 12 period records for 2026.
2. Open `/timesheets?work_month=2026-01` and confirm the period status is Closed.
3. Open `/timesheets?work_month=2026-04` and confirm the period status is Closed.
4. Open `/timesheets?work_month=2026-05` and confirm the period status is Open.
5. Open `/timesheets?work_month=2026-12` and confirm the period status is Open.
6. As HR/Admin, close an open period with no active rows and confirm it becomes Closed.
7. Create a Draft row in an open period and confirm close is blocked until active rows are Approved.
8. Approve all active rows in an open period, close the period, and confirm a `timesheet.accounting_period` close audit row was appended.
9. Confirm creating/editing/submitting rows in a Closed period is blocked.
10. Open a Closed period with no active invoice drafts and confirm a `timesheet.accounting_period` open audit row was appended.
11. Create an invoice draft for a Closed period and confirm reopening that period is blocked until the invoice draft is voided.

## 11. CSV export regression

1. Open `/timesheets` without filters and export CSV.
2. Filter by work month and export CSV.
3. Filter by approval status and export CSV.
4. Confirm soft-deleted rows are excluded.
5. Confirm Japanese text is readable in the CSV.

## 12. Billing regression

1. Create or edit a billing-enabled project with a non-zero hourly JPY rate.
2. Create and approve timesheet rows under that project.
3. Open `/billing` and confirm only approved, billable rows contribute to the billing amount.
4. Confirm Draft, Submitted, Rejected, and Deleted rows do not contribute.
5. Confirm billing-disabled projects are excluded from billable totals.

## 13. Invoice draft regression

1. Confirm invoice draft creation is unavailable before the target month is locked.
2. Lock a fully approved month.
3. Create an invoice draft from `/billing`.
4. Confirm the draft appears under `/invoices` with correct customer, project, minutes, subtotal, tax, and total.
5. Confirm a `timesheet.invoice_draft` create audit row was appended.
6. Try creating a duplicate active draft for the same month/customer/project; confirm validation blocks it.
7. Void an invoice draft and confirm the status changes to `Voided`.
8. Confirm a `timesheet.invoice_draft` void audit row was appended.
9. Confirm source timesheet rows are unchanged.

## 14. Final regression after each milestone

1. Run syntax check:

   ```bash
   python3 -m py_compile backend/app.py
   ```

2. Confirm these pages still load:

   - `/`
   - `/timesheets`
   - `/employees`
   - `/projects`
   - `/audit-logs`

3. Confirm `/audit-logs` filters work for module, record ID, action, and user.
4. Confirm JSON database files remain valid arrays.
