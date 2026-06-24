# Remote Consultant Access Runbook

Last updated: 2026-06-21

## 1. What has been prepared locally

The local TACAI pilot apps are configured to support public HTTPS domain access while keeping backend service validation on loopback.

Public pilot domains:

| Domain | Purpose | Local target |
|---|---|---:|
| `https://ai.tactokyo.com` | TACAI Portal | `127.0.0.1:8005` |
| `https://timesheet.tactokyo.com` | Timesheet self-service | `127.0.0.1:8002` |
| `https://expense.tactokyo.com` | Expense/Reimbursement self-service | `127.0.0.1:8003` |
| `https://useradmin.tactokyo.com` | User_admin login/admin | `127.0.0.1:8006` |

Remote consultant business scope:

- Can use Timesheet self-entry and own monthly view.
- Can input Expense/Reimbursement claims.
- Can query only their own Expense/Reimbursement claims and vouchers.
- Cannot access finance review, payment, reports, payroll, employee master, billing, candidate/interview data, or user administration unless separately granted.

## 2. Local MacBook startup environment

Use [deployment/remote-access/macbook-pilot-env.example](deployment/remote-access/macbook-pilot-env.example) as the baseline.

Required environment values for the MacBook pilot:

```bash
export TACAI_PUBLIC_HOST="127.0.0.1"
export TACAI_INTERNAL_HOST="127.0.0.1"
export PORTAL_PUBLIC_BASE_URL="https://ai.tactokyo.com"
export TIMESHEET_PUBLIC_BASE_URL="https://timesheet.tactokyo.com"
export EXPENSE_PUBLIC_BASE_URL="https://expense.tactokyo.com"
export USER_ADMIN_PUBLIC_BASE_URL="https://useradmin.tactokyo.com"
export USER_ADMIN_INTERNAL_BASE_URL="http://127.0.0.1:8006"
export TACAI_ALLOWED_PUBLIC_HOSTS="ai.tactokyo.com,timesheet.tactokyo.com,expense.tactokyo.com,useradmin.tactokyo.com"
export TACAI_COOKIE_DOMAIN=".tactokyo.com"
export TACAI_COOKIE_SECURE="true"
```

Start these four services on the MacBook:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Core/User_admin
python3 backend/app.py --host 127.0.0.1 --port 8006

cd /Users/terencewang/Documents/claude-project/TACAI-Core/tacai-portal
python3 backend/app.py --host 127.0.0.1 --port 8005

cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 backend/app.py --host 127.0.0.1 --port 8002

cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
python3 backend/app.py --host 127.0.0.1 --port 8003
```

Keep the MacBook plugged in and disable sleep during remote test windows.

## 3. Manual DNS / Cloudflare steps you must do

Current continuation checkpoint on 2026-06-21:

- Local services are running on loopback and passed health checks.
- `cloudflared` was not present on the MacBook.
- Homebrew was not present on the MacBook.
- Attempted direct GitHub release download for the Apple Silicon `cloudflared` package, but the current network returned incomplete/empty responses, so `cloudflared` installation is still pending.
- The pilot hostnames `ai.tactokyo.com`, `timesheet.tactokyo.com`, `expense.tactokyo.com`, and `useradmin.tactokyo.com` are currently unresolved in DNS.

These steps require access to the `tactokyo.com` DNS provider and/or Cloudflare account. They cannot be completed from the local code workspace alone.

### 3.1 Confirm DNS management

Confirm where `tactokyo.com` DNS is managed:

- Existing domain registrar DNS, or
- Cloudflare DNS, or
- Another DNS provider.

If using Cloudflare Tunnel + Cloudflare Access, it is easiest if Cloudflare manages the DNS zone for `tactokyo.com`.

### 3.2 Create tunnel public hostnames

Create a Cloudflare Tunnel on the Nanjing MacBook and map:

```text
ai.tactokyo.com         -> http://127.0.0.1:8005
timesheet.tactokyo.com  -> http://127.0.0.1:8002
expense.tactokyo.com    -> http://127.0.0.1:8003
useradmin.tactokyo.com  -> http://127.0.0.1:8006
```

Template file:

- [cloudflare-tunnel-config.example.yml](deployment/remote-access/cloudflare-tunnel-config.example.yml)

If Cloudflare creates CNAME records automatically, confirm the records appear in DNS. If not, manually create the CNAME records Cloudflare gives you.

### 3.3 Enable access policies

In Cloudflare Access or the equivalent access gateway:

1. Allow `ai.tactokyo.com`, `timesheet.tactokyo.com`, and `expense.tactokyo.com` only for the approved Japan/India/China pilot tester emails.
2. Restrict `useradmin.tactokyo.com` to only admin/operator emails.
3. Do not allow anonymous public access during the pilot.
4. Keep HTTPS enabled.

Recommended pilot allowlist:

- Japan consultant 1 email
- Japan consultant 2 email
- India consultant 1 email
- India consultant 2 email
- China/Nanjing consultant 1 email
- China/Nanjing consultant 2 email
- Admin/operator email(s)

## 4. User_admin setup before inviting consultants

Create named accounts. Do not use shared accounts.

For ordinary remote consultants, assign the new narrow role:

```text
remote_consultant
```

This role is designed for:

- `timesheet.access`
- `timesheet.submit`
- `timesheet.edit_own`
- `reimbursement.access`
- `reimbursement.submit`
- `reimbursement.view_own`

Do not assign broad `employee`, `manager`, `finance`, or `system_admin` roles to ordinary remote consultants unless there is a separate business reason.

Important: each consultant account should include or be linked to the correct `employee_no`. Reimbursement self-service blocks claim creation when the User_admin account cannot resolve an employee number.

## 5. How remote consultants access after completion

### Normal access through Portal

Remote consultants in Japan, India, or China should:

1. Open `https://ai.tactokyo.com`.
2. Pass the outer Cloudflare Access / access gateway email check.
3. Log in with their own User_admin email/password.
4. Confirm the Portal only shows allowed modules:
   - Timesheet
   - Expense
5. Open Timesheet for daily/monthly timesheet work.
6. Open Expense for reimbursement input and own claim query.
7. Log out after use.

### Direct module access

If users only need one module, they may also open:

- `https://timesheet.tactokyo.com`
- `https://expense.tactokyo.com`

If not logged in, they should be redirected to User_admin login and then returned to the requested module.

## 6. What remote consultants must not be able to access

Ordinary remote consultant users must not be able to:

- See another employee's reimbursement claims.
- Open another employee's reimbursement voucher/receipt.
- Edit or delete another employee's reimbursement claim.
- Open Finance Review.
- Open Finance Report or CSV export.
- Close payments.
- Open Payroll.
- Open Employee Management.
- Open Master Data Management.
- Open Customer Billing.
- Open Vendor Payments.
- Open InterviewReady/candidate data.
- Open User Management admin pages.

## 7. Smoke test checklist

Before inviting Japan/India users, test from a non-LAN network such as mobile tethering:

1. `https://ai.tactokyo.com/health` or Portal home responds through tunnel.
2. `https://timesheet.tactokyo.com/health` returns `OK`.
3. `https://expense.tactokyo.com/health` returns `OK`.
4. User_admin login works.
5. A remote consultant sees only Timesheet and Expense in Portal.
6. Consultant can create a Timesheet entry.
7. Consultant can create a Reimbursement claim.
8. Consultant can see their own claim in `/claims`.
9. Consultant cannot see another user's claim.
10. Consultant cannot open `/finance-review` or `/finance-report`.
11. Consultant cannot download another user's voucher.

## 8. Tokyo Tencent Cloud migration after 30-40 days

After the MacBook pilot is stable and users are familiar with the workflow, migrate to the existing Tencent Cloud Tokyo server.

Manual cloud/DNS steps:

1. Prepare the Tokyo server security group:
   - allow `80` and `443` inbound.
   - restrict SSH to admin IPs.
2. Install Nginx and TLS certificates.
3. Deploy Portal, User_admin, Timesheet, and Reimbursement on local ports `8005`, `8006`, `8002`, and `8003`.
4. Copy from MacBook:
   - User_admin JSON data.
   - Portal module/service JSON data.
   - Timesheet database JSON files.
   - Reimbursement database JSON files.
   - Reimbursement `attachments/` and `expensebill/` folders.
   - Audit logs.
5. Point DNS A/CNAME records to the Tokyo server or edge endpoint.
6. Use [nginx-tokyo-tencent.example.conf](deployment/remote-access/nginx-tokyo-tencent.example.conf) as the reverse proxy baseline.
7. Repeat the same smoke test checklist.
8. Keep the MacBook as a short rollback fallback, but stop using it as the official external endpoint after cutover.
