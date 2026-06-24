# TACAI Portal / User_admin Integration Manual Test Checklist

Last updated: 2026-06-24

## Test ports

| Service | URL | Health | Permission |
| --- | --- | --- | --- |
| User_admin | `http://127.0.0.1:8006` | `http://127.0.0.1:8006/health` | Identity/RBAC source |
| Portal | `http://127.0.0.1:8005` | `http://127.0.0.1:8005/health` | Authenticated users |
| Employee Mgmt | `http://127.0.0.1:8004/dashboard` | `http://127.0.0.1:8004/health` | `employee_management.access` |
| Timesheet | `http://127.0.0.1:8002/` | `http://127.0.0.1:8002/health` | `timesheet.access` |
| Expense | `http://127.0.0.1:8003/` | `http://127.0.0.1:8003/health` | `reimbursement.access` |
| Payroll (legacy comparison) | `http://127.0.0.1:8001/` | `http://127.0.0.1:8001/health` | `payroll.access` |
| TAC Payroll | `http://127.0.0.1:8015/` | `http://127.0.0.1:8015/health` | `payroll.access` |
| Master Data | `http://127.0.0.1:8007/dashboard` | `http://127.0.0.1:8007/health` | `masterdata.access` |

For same-Wi-Fi mobile testing, replace the browser-facing host with the Mac LAN IP, for example `http://192.168.2.9:8005`.

## Test users

Use the existing System Admin account for full-access testing:

| Role | Email | Password | Expected Portal modules |
| --- | --- | --- | --- |
| System Admin | `admin@tacai.local` | Your current admin password | All enabled modules |
| HR Manager | `hr.manager@tacai.local` | `Test1234` | Employee Mgmt, TAC Payroll, Timesheet, Expense, Payroll, InterviewReady |
| Finance | `finance@tacai.local` | `Test1234` | TAC Payroll, Payroll, Expense, Vendor Payments |
| Manager | `manager@tacai.local` | `Test1234` | Timesheet, Expense |
| Employee | `employee@tacai.local` | `Test1234` | Employee Mgmt, Timesheet, Expense |

## Services

Start these apps as needed:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006

cd /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal
python3 backend/app.py --host 127.0.0.1 --port 8005

cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 backend/app.py --host 127.0.0.1 --port 8004

cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 backend/app.py --host 127.0.0.1 --port 8002

cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
python3 backend/app.py --host 127.0.0.1 --port 8003

cd /Users/terencewang/Documents/claude-project/TACAI-PRJ
python3 backend/app.py --host 127.0.0.1 --port 8001

cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 backend/app.py --host 127.0.0.1 --port 8015

cd /Users/terencewang/Documents/claude-project/TACAI-Core/masterdata
python3 backend/app.py --host 127.0.0.1 --port 8007
```

For same-Wi-Fi mobile testing, use the Mac LAN IP as `TACAI_PUBLIC_HOST` and bind to all interfaces:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-PRJ
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8001

cd /Users/terencewang/Documents/claude-project/TAC-salary
TACAI_PUBLIC_HOST=192.168.2.9 SALARY_PUBLIC_BASE_URL=http://192.168.2.9:8015 python3 backend/app.py --host 0.0.0.0 --port 8015

cd /Users/terencewang/Documents/claude-project/TAC-timesheet
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8002

cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8003

cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8004

cd /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8005

cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8006

cd /Users/terencewang/Documents/claude-project/TACAI-Core/masterdata
TACAI_PUBLIC_HOST=192.168.2.9 python3 backend/app.py --host 0.0.0.0 --port 8007
```

Open Portal on the phone at `http://192.168.2.9:8005`.

## Health checks

```bash
curl -s http://127.0.0.1:8006/health
curl -s http://127.0.0.1:8005/health
curl -s http://127.0.0.1:8004/health
curl -s http://127.0.0.1:8002/health
curl -s http://127.0.0.1:8003/health
curl -s http://127.0.0.1:8001/health
curl -s http://127.0.0.1:8015/health
curl -s http://127.0.0.1:8007/health
```

LAN/mobile health checks use the Mac IP:

```bash
curl -s http://192.168.2.9:8001/health
curl -s http://192.168.2.9:8015/health
curl -s http://192.168.2.9:8002/health
curl -s http://192.168.2.9:8003/health
curl -s http://192.168.2.9:8004/health
curl -s http://192.168.2.9:8005/health
curl -s http://192.168.2.9:8006/health
curl -s http://192.168.2.9:8007/health
```

Expected:

- User_admin: `OK`
- Portal: JSON `status=ok`
- EmployeeAdmin: `OK`
- Timesheet: `OK`
- Expense/Reimbursement: `OK`
- Payroll/TACAI-PRJ legacy comparison: `OK`
- TAC Payroll/TAC-salary: JSON `status=ok`
- Master Data: `OK`

## Login flow

1. Open `http://127.0.0.1:8005`.
2. Click `Sign in with TACAI User Management`.
3. Login at User_admin.
4. Confirm redirect back to `http://127.0.0.1:8005/dashboard`.
5. Confirm the Portal header shows the User_admin display name.

## Permission-based Portal navigation

1. Login as System Admin.
2. Confirm Portal shows enabled modules from `database/modules.json`:
   - Dashboard
   - Employee Mgmt
   - TAC Payroll
   - Timesheet
   - Payroll
   - Expense
   - Master Data Management
   - User Management
3. Login as a non-admin user.
4. Confirm only modules covered by that user's permissions appear.

## Direct module access protection

Without logging in, visit:

```text
http://127.0.0.1:8004/dashboard
http://127.0.0.1:8002/
http://127.0.0.1:8003/
http://127.0.0.1:8001/
http://127.0.0.1:8015/
```

Expected:

- Each redirects to User_admin login with a `next` parameter.

## Module permission protection

With a logged-in user lacking a module permission, visit the module URL directly.

Expected:

- The module returns `403 Forbidden` or equivalent no-access page.

## Logout flow

1. Login through Portal.
2. Click Portal `Logout`.
3. Confirm User_admin clears `tacai_session_id`.
4. Confirm redirect back to Portal login.
5. Visit Portal dashboard directly.
6. Confirm redirect to User_admin login.

## Mobile / tablet responsive UI checks

Check at approximately 375px, 430px, 768px, 1024px, and desktop width:

1. Portal login and dashboard do not clip horizontally.
2. Portal module cards are large enough to tap and stack cleanly on phones.
3. User_admin user/role/permission pages keep actions tappable and tables scroll inside the page.
4. Master Data entity/department/team pages keep forms one-column on phones and tables scroll instead of clipping.
5. Employee Admin, Timesheet, Expense, and Payroll dashboards render without horizontal page overflow.
6. Main forms stack to one column and action buttons are full-width/tappable on phones.
7. Dense tables remain readable through local horizontal scrolling.
8. Language switchers and logout/session controls do not overflow the header/nav.

## Regression checks

Run syntax checks:

```bash
python3 -m py_compile \
  /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal/backend/app.py \
  /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin/backend/app.py \
  /Users/terencewang/Documents/claude-project/TAC-employeeadmin/backend/app.py \
  /Users/terencewang/Documents/claude-project/TAC-timesheet/backend/app.py \
  /Users/terencewang/Documents/claude-project/TAC-reimbursement/backend/app.py \
  /Users/terencewang/Documents/claude-project/TACAI-PRJ/backend/app.py
```

Validate Portal module config:

```bash
python3 -m json.tool /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal/database/modules.json
```
