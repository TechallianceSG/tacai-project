# TACAI Portal

TACAI Portal is the future unified login window for TACAI modules.

Initial navigation structure:

```text
TACAI Portal
├── Dashboard
├── Employee Mgmt
├── TAC Payroll
├── Timesheet
├── Payroll (legacy comparison)
├── Expense
├── InterviewReady
└── User Management
```

## Current scope

This first skeleton provides:

- User_admin-backed Portal authentication
- Permission-based module navigation using User_admin permissions
- Centralized module configuration in `database/modules.json`
- Centralized local service reference in `database/services.json`
- Dashboard shell
- Connected launchers for Employee Mgmt, TAC Payroll, Timesheet, legacy Payroll, Expense, InterviewReady, Master Data Management, and User Management
- Optional same-Wi-Fi mobile testing by setting `TACAI_PUBLIC_HOST` and binding services to `0.0.0.0`
- Append-only audit log JSON file
- Python standard-library backend with no external dependencies

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal
python3 backend/app.py --host 127.0.0.1 --port 8005
```

Open:

```text
http://127.0.0.1:8005
```

Health check:

```bash
curl -s http://127.0.0.1:8005/health
```

## Main Portal module details

| Module | Port | Local URL | Portal permission |
| --- | ---: | --- | --- |
| InterviewReady | 8000 | `http://127.0.0.1:8000/` | `interview_ready.access` |
| Payroll (legacy comparison) | 8001 | `http://127.0.0.1:8001/` | `payroll.access` |
| TAC Payroll | 8015 | `http://127.0.0.1:8015/` | `payroll.access` |
| Timesheet | 8002 | `http://127.0.0.1:8002/` | `timesheet.access` |
| Expense | 8003 | `http://127.0.0.1:8003/` | `reimbursement.access` |
| Employee Mgmt | 8004 | `http://127.0.0.1:8004/dashboard` | `employee_management.access` |
| TACAI Portal | 8005 | `http://127.0.0.1:8005/` | Login + entity context |
| User Management | 8006 | `http://127.0.0.1:8006/dashboard` | `user_management.access` |
| Master Data Management | 8007 | `http://127.0.0.1:8007/dashboard` | `masterdata.access` |
| Vendor Payments | 8008 | `http://127.0.0.1:8008/` | `vendor_expense.access` |
| Customer Billing | 8009 | `http://127.0.0.1:8009/` | `client_revenue.access` |

For Wi-Fi testing, open the main Portal with the same LAN host used by the services, for example `http://<LAN_IP>:8005`. Do not mix `127.0.0.1`, `localhost`, and the LAN IP in the same browser session because the `tacai_session_id` cookie is host-scoped.

## LAN / mobile testing

For a phone or another computer on the same Wi-Fi, keep localhost as the default for normal development and explicitly expose the services only for this test session.

Get the current Mac Wi-Fi IP:

```bash
ipconfig getifaddr en0
```

Example from the current test network:

```text
192.168.0.27
```

Start the TACAI LAN test services from the workspace root:

```bash
cd /Users/terencewang/Documents/claude-project
./start_tacai_lan.sh
```

The launcher detects the LAN IP, sets browser-facing public URLs such as `TACAI_PUBLIC_HOST=<LAN_IP>`, keeps internal backend calls on `127.0.0.1`, and starts the services with `--host 0.0.0.0` so same-Wi-Fi devices can connect.

Open from another device on the same Wi-Fi:

```text
http://<LAN_IP>:8005
```

For the current test network, that is:

```text
http://192.168.0.27:8005
```

Useful launcher commands:

```bash
./start_tacai_lan.sh status
./start_tacai_lan.sh stop
./start_tacai_lan.sh restart
```

If macOS asks whether Python can accept incoming network connections, allow it for this local Wi-Fi test.

## User_admin authentication

Portal authentication is handled by TACAI User Management.

Login flow:

```text
Portal /login
  -> http://127.0.0.1:8006/login?next=http%3A%2F%2F127.0.0.1%3A8005%2Fdashboard
  -> User_admin sets tacai_session_id
  -> User_admin redirects back to Portal /dashboard
  -> Portal validates tacai_session_id through User_admin /api/validate-session
```

Logout flow:

```text
Portal logout button
  -> http://127.0.0.1:8006/logout?next=http%3A%2F%2F127.0.0.1%3A8005%2Flogin
  -> User_admin clears tacai_session_id
  -> User_admin redirects back to Portal login
```

After changing User_admin roles or permissions, testers should log out and log in again. If a browser still shows an old permission set, clear the `tacai_session_id` cookie for the test host and retry.

## Connected modules

User Management currently opens the actual TACAI User Management app:

```text
http://127.0.0.1:8006/dashboard
```

Run User_admin separately when testing that link:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006
```

## Login

Use a User_admin account to sign in. Portal no longer uses its local demo account as the primary login path.

## Project structure

```text
tacai-portal/
├── backend/
│   └── app.py
├── database/
│   ├── audit_logs.json
│   └── users.json
├── docs/
│   ├── Data_Schema.md
│   ├── Integration_Roadmap.md
│   ├── Manual_Test_Checklist.md
│   └── Project_Plan.md
├── frontend/
│   └── app.css
├── memory/
│   ├── changelog.md
│   ├── current_tasks.md
│   ├── decisions.md
│   └── project_status.md
├── archive/
├── CLAUDE.md
├── README.md
└── .gitignore
```
