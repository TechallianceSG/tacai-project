# Remote Consultant Access Implementation Plan

Last updated: 2026-06-21

## 1. Purpose

This document defines the global access plan for letting remote consultants and pilot users outside the Nanjing company LAN access the TACAI local MVP suite that is currently hosted on a MacBook inside the Nanjing office network.

Planned pilot users:

- Japan: approximately 2 users
- India: approximately 2 users
- Nanjing office: approximately 2 users

Primary domain strategy:

- Main AI/business portal: `https://ai.tactokyo.com`
- Timesheet direct entry: `https://timesheet.tactokyo.com`
- Expense/reimbursement direct entry, if useful for consultants: `https://expense.tactokyo.com`
- Keep `www.tactokyo.com` for the public/company website unless a separate business decision changes it.

Current pilot scope is controlled remote access for ordinary consultants/employees. The main remote-user business functions are:

1. Timesheet self-entry and own monthly timesheet view.
2. Expense/reimbursement self-service claim input and own claim query.

The target is a controlled pilot for about 30-40 days. If the pilot is stable and users are familiar with the workflow, the planned next step is migration from the Nanjing MacBook pilot host to the existing Tencent Cloud server deployed in Tokyo.

## 2. Architecture principles

From a Japan business architect and IT infrastructure perspective, the access design should follow these principles:

1. **Portal first**: users normally enter through `ai.tactokyo.com`, then open Timesheet and Expense/Reimbursement from the TACAI Portal. Other modules remain hidden unless their role requires access.
2. **Direct module domains only where operationally useful**: `timesheet.tactokyo.com` can be used for attendance-only users, and `expense.tactokyo.com` can be used for reimbursement-only users. Governance still comes from User_admin roles and permissions.
3. **Self-service boundary for remote consultants**: ordinary remote consultants should only create/view their own timesheets and reimbursement claims. They must not see other employees' records, finance review queues, payroll, employee master, billing, or candidate data.
4. **No raw LAN exposure**: do not expose the MacBook directly to the internet by simple router port-forwarding unless there is no alternative and a firewall/VPN/reverse proxy is properly configured.
5. **Zero-trust access for pilot**: because the MacBook is in a company LAN and external users are in Japan/India, use identity-gated access before the app login whenever practical.
6. **Japan compliance first**: timesheet, reimbursement receipts, payroll, employee, candidate, and billing data can include personal information or business-sensitive records. Follow minimum-access, audit logging, retention, and clear cross-border access rules.
7. **MacBook is pilot/staging infrastructure**: it is acceptable for a small 30-40 day test, but not a long-term production hosting platform.
8. **Tokyo Tencent Cloud is the next hosting target**: after successful pilot validation, migrate to the existing Tokyo Tencent Cloud server for more stable external access, backup, monitoring, and operations.

## 3. Recommended pilot architecture

### 3.1 Recommended option: secure tunnel + DNS + access gateway

For the first remote pilot, the preferred approach is:

```text
Remote users
  -> HTTPS custom domain, e.g. ai.tactokyo.com / timesheet.tactokyo.com / expense.tactokyo.com
  -> DNS / edge access gateway
  -> Zero-trust access rule for approved tester emails
  -> Encrypted tunnel from edge to Nanjing MacBook
  -> Local reverse proxy on MacBook
  -> TACAI local apps on 127.0.0.1 ports
```

Why this is preferred:

- No inbound port needs to be opened on the Nanjing office router.
- Dynamic office IP is acceptable.
- TLS certificates are handled at the edge or reverse proxy.
- The pilot can be limited to named tester emails from Japan, India, and Nanjing.
- The exposure can be disabled quickly if needed.
- Timesheet and reimbursement can be tested remotely before committing to server migration.

Recommended technologies can be selected based on availability:

- **Cloudflare Tunnel + Cloudflare Access**: best fit if `tactokyo.com` DNS can be managed in Cloudflare and the Nanjing network can keep a stable outbound connection.
- **VPS reverse proxy + WireGuard/Tailscale tunnel**: fallback if Cloudflare is not acceptable or connectivity from Nanjing to Cloudflare is unstable.
- **Tailscale-only pilot**: acceptable for internal technical testers, but less convenient because every tester needs a client install and account setup.

### 3.2 Not recommended for this pilot

Avoid these as default choices:

- Opening router ports directly to the MacBook.
- Publishing local Python app ports directly to the internet.
- Using temporary public tunnel URLs as official business URLs.
- Sharing a single test account among all Japan/India/Nanjing testers.
- Giving ordinary remote users access to payroll, employee master, billing, candidate data, finance review queues, or other employees' reimbursement/timesheet records.

## 4. Domain and route plan

### 4.1 Primary pilot domains

| Domain | Purpose | Initial audience | Backend target |
|---|---|---|---|
| `ai.tactokyo.com` | Main TACAI Portal | All approved pilot users | Portal, local port `8005` |
| `timesheet.tactokyo.com` | Direct Timesheet entry and own monthly view | Employees, dispatch workers, consultants, managers | TAC-timesheet, local port `8002` |
| `expense.tactokyo.com` | Direct reimbursement claim input and own claim query | Employees and remote consultants | TAC-reimbursement, local port `8003` |

### 4.2 Optional admin/module domains

These should be enabled only when needed and only for admin/HR/finance/recruitment users:

| Domain | Purpose | Backend target | Exposure recommendation |
|---|---|---|---|
| `useradmin.tactokyo.com` | User_admin login/RBAC management | User_admin, local port `8006` | Admin only, strongly restricted |
| `employee.tactokyo.com` | EmployeeAdmin | TAC-employeeadmin, local port `8004` | HR/Admin only |
| `payroll.tactokyo.com` | Payroll/HR finance | TACAI-PRJ, local port `8001` | HR/Finance only |
| `interview.tactokyo.com` | InterviewReady | InterviewReady, local port `8000` | HR/recruitment only |
| `billing.tactokyo.com` | Customer Billing / AR | customerbilling, local port `8009` | Finance/Admin only |

### 4.3 Portal navigation rule

Even if direct subdomains exist, the official user journey should be:

1. User opens `https://ai.tactokyo.com`.
2. User logs in through User_admin-controlled authentication.
3. Portal shows only modules allowed by role/permission.
4. Ordinary remote consultants see only Timesheet and Expense/Reimbursement self-service modules unless explicitly approved otherwise.
5. User opens Timesheet or Expense/Reimbursement.
6. Direct module domains remain convenience links, not a replacement for RBAC.

## 5. Authentication, authorization, and session design

### 5.1 Two-layer access for pilot

Use two layers:

1. **Outer access control**: zero-trust gateway allows only approved tester emails or approved network ranges.
2. **Application access control**: User_admin login, session validation, Entity context, and module permissions.

This is important because the local MVP apps are business apps, not anonymous public websites.

### 5.2 Pilot account model

Create named users, not shared users:

- Japan tester 1 / Japan tester 2
- India tester 1 / India tester 2
- Nanjing tester 1 / Nanjing tester 2

Each user should have:

- Real email or controlled test email.
- Country/location note for support and audit.
- Role appropriate to the test case.
- Minimum permissions only.

Recommended initial roles:

- Ordinary employee/consultant testers: Portal + Timesheet self-entry + own timesheet view + reimbursement claim input + own reimbursement query.
- One HR/admin tester: Portal + Timesheet admin/proxy entry, if the business test requires it.
- One Finance/admin tester: Reimbursement finance review access only if the business test requires internal back-office validation; this should not be given to ordinary remote consultants.
- Avoid payroll, employee master, billing, candidate modules, finance review queues, and other-employee records for ordinary remote testers.

### 5.3 Reimbursement self-service boundary

For remote consultant reimbursement access, the pilot rule is:

1. Remote consultant can create a reimbursement claim for themselves.
2. Remote consultant can upload or attach supporting receipt/invoice files if the current module supports it.
3. Remote consultant can query only their own reimbursement claims and status.
4. Remote consultant cannot view all claims, finance review queues, payment reports, or other employees' claims.
5. Finance/admin users can review claims only through separate restricted permissions and preferably from the Portal/admin network.
6. Audit logs must record create/update/status actions and should be checked during the pilot.

### 5.4 Cross-subdomain session consideration

If users will move between `ai.tactokyo.com`, `timesheet.tactokyo.com`, `expense.tactokyo.com`, and other module subdomains, the app should eventually use a secure shared cookie design:

- Cookie domain: `.tactokyo.com`
- `Secure`: true
- `HttpOnly`: true where practical
- `SameSite`: `Lax` for normal portal navigation
- HTTPS only

If this is not yet implemented, the short-term pilot can still use portal-first navigation, but users may need to log in again on some subdomains. That should be treated as an MVP limitation to improve before wider rollout and before Tokyo Tencent Cloud migration.

## 6. Japan compliance and business controls

For Japan operations, timesheets and reimbursement records are business records and may contain personal information, commuting/transportation details, customer-site context, bank/payment context, or receipt images. The pilot must be treated as controlled processing.

### 6.1 Required controls

- Use named accounts and role-based permissions.
- Keep app audit logs append-only.
- Keep access logs from the edge gateway or reverse proxy.
- Keep the MacBook disk protected by OS login password and disk encryption.
- Back up local JSON databases and reimbursement attachment folders before and after remote test sessions.
- Do not expose My Number or highly sensitive payroll data in remote pilot tests unless absolutely necessary.
- Use test/minimized data for Japan/India remote users where possible.
- Ensure ordinary consultants can query only their own timesheet and reimbursement records.
- Avoid showing finance review, all-employee claim list, payment reports, or accounting exports to ordinary consultants.
- Obtain basic NDA/confidentiality acknowledgement for external consultants if they see real business data.

### 6.2 Cross-border access note

Japan users and India users accessing a Nanjing-hosted system means personal/business data may be viewed cross-border. For MVP testing this is manageable if:

- Data scope is minimized.
- Testers are authorized.
- Access is logged.
- Real employee payroll/HR master data is restricted.
- Reimbursement receipt/attachment access is limited to the claim owner and authorized finance/admin users.
- There is a clear business purpose for each user's access.

## 7. MacBook hosting requirements

Because the current host is a MacBook in the Nanjing office network, configure it like a small server during test windows:

1. Reserve a stable LAN IP in the Nanjing router or DHCP server.
2. Disable sleep while plugged in.
3. Enable automatic restart after power failure if available.
4. Run apps with a non-admin OS account where practical.
5. Bind local apps to `127.0.0.1` when using a tunnel/reverse proxy; avoid unnecessary `0.0.0.0` exposure.
6. Allow only the reverse proxy/tunnel process to accept external traffic.
7. Store environment variables and tunnel credentials outside source code.
8. Create daily timestamped backups of each in-scope module's `database/` JSON files during pilot.
9. Include reimbursement upload/attachment folders in the backup routine.
10. Keep a simple restart runbook for Portal, User_admin, Timesheet, and Reimbursement.

## 8. Implementation phases

### Phase 0 — Pilot scope confirmation

Owner: Business + architecture

Tasks:

- Confirm the six pilot users and their email addresses.
- Confirm first remote test scope:
  - Portal
  - User_admin login/session validation
  - Timesheet `/clock-entry`
  - Timesheet `/my-timesheet`
  - Reimbursement claim input
  - Reimbursement own claim query/status view
- Confirm that ordinary remote consultants must not access:
  - all-employee reimbursement list
  - finance reimbursement review
  - reimbursement payment/reporting pages
  - payroll
  - employee master
  - customer billing
  - candidate/interview data
- Confirm whether HR/Admin proxy timesheet entry is included.
- Confirm whether Finance/admin reimbursement review is included for one internal tester only.
- Confirm whether Japan/India users use real data or prepared pilot data.
- Confirm pilot dates and support window across Japan/India/Nanjing time zones.
- Confirm target decision window: migrate to Tokyo Tencent Cloud after about 30-40 days if pilot is stable.

Exit criteria:

- Pilot user list approved.
- Module list approved: Timesheet + Reimbursement self-service.
- Data sensitivity level approved.
- Tokyo Tencent Cloud migration target confirmed.

### Phase 1 — Domain and DNS setup

Owner: IT infrastructure

Tasks:

- Keep `www.tactokyo.com` unchanged unless separately approved.
- Create DNS records for:
  - `ai.tactokyo.com`
  - `timesheet.tactokyo.com`
  - `expense.tactokyo.com`
- Optionally reserve records for admin/module domains but do not publish broadly until needed.
- If using Cloudflare Tunnel, point subdomains to the tunnel CNAME records.
- If using VPS reverse proxy, point subdomains to the VPS public IP.
- Enable HTTPS certificates.

Exit criteria:

- `ai.tactokyo.com`, `timesheet.tactokyo.com`, and `expense.tactokyo.com` resolve correctly.
- HTTPS certificate is valid.
- Non-approved domains are not accidentally exposed.

### Phase 2 — Nanjing MacBook host preparation

Owner: Local IT / system operator

Tasks:

- Confirm MacBook can run continuously during pilot windows.
- Disable sleep while on power.
- Confirm local services start cleanly:
  - TAC-timesheet `8002`
  - TAC-reimbursement `8003`
  - Portal `8005`
  - User_admin `8006`
  - InterviewReady `8000` only if needed
  - TACAI-PRJ `8001` only if needed
  - TAC-employeeadmin `8004` only if needed
  - MasterData `8007` only if needed
  - Customer Billing `8009` only if needed
- Start only modules required by the pilot.
- Back up all in-scope `database/` folders.
- Back up reimbursement upload/attachment folders.
- Record a restart procedure.

Exit criteria:

- Local LAN access works.
- Required health checks return OK for Portal, User_admin, Timesheet, and Reimbursement.
- Backup copy exists before exposing remote access.

### Phase 3 — Tunnel / reverse proxy setup

Owner: IT infrastructure

Recommended pilot path:

- Install and authenticate the tunnel client on the MacBook.
- Configure ingress routing:

```text
ai.tactokyo.com         -> http://127.0.0.1:8005
timesheet.tactokyo.com  -> http://127.0.0.1:8002
expense.tactokyo.com    -> http://127.0.0.1:8003
useradmin.tactokyo.com  -> http://127.0.0.1:8006  (admin only, optional)
```

Optional later routes:

```text
employee.tactokyo.com   -> http://127.0.0.1:8004
payroll.tactokyo.com    -> http://127.0.0.1:8001
interview.tactokyo.com  -> http://127.0.0.1:8000
billing.tactokyo.com    -> http://127.0.0.1:8009
```

Security settings:

- Require HTTPS.
- Require approved tester email authentication at the access gateway.
- Block unknown users before they reach the Python apps.
- Restrict `useradmin.tactokyo.com` to admin/operator emails only.
- Ensure `expense.tactokyo.com` exposes self-service claim input/query only to ordinary consultant roles.
- Enable access logs.

Exit criteria:

- External network can reach only the approved pilot domains.
- Unapproved email/user is blocked before app login.
- Approved tester can reach Portal login.
- Ordinary consultant account can access Timesheet/Reimbursement self-service but cannot access finance/admin pages.

### Phase 4 — App public URL and cookie alignment

Owner: Application + architecture

Tasks:

- Set public browser URLs to domain names instead of LAN IPs.
- Keep backend-to-backend validation URLs on `127.0.0.1` where services run on the same MacBook.
- Ensure Portal service registry points browser users to external HTTPS domains:
  - Portal: `https://ai.tactokyo.com`
  - Timesheet: `https://timesheet.tactokyo.com`
  - Reimbursement: `https://expense.tactokyo.com`
- Ensure User_admin validation remains internal and reliable.
- Review session cookie behavior across subdomains.
- Plan/update cookie configuration for `.tactokyo.com` before larger rollout.
- Confirm CORS is not opened broadly; prefer same-site navigation and server-side session validation.
- Verify ordinary reimbursement queries are filtered by current user/employee identity.

Exit criteria:

- Portal opens Timesheet and Reimbursement links using `https://*.tactokyo.com`.
- Backend session validation still works locally.
- Users do not see LAN IP addresses in normal navigation.
- Ordinary consultant cannot query another employee's reimbursement claim.

### Phase 5 — Pilot test execution

Owner: Business operations + IT support

Test matrix:

| Test area | Japan users | India users | Nanjing users |
|---|---:|---:|---:|
| Open `ai.tactokyo.com` | Yes | Yes | Yes |
| Outer access gateway login | Yes | Yes | Yes |
| User_admin login | Yes | Yes | Yes |
| Portal module visibility | Yes | Yes | Yes |
| Timesheet clock entry | Yes | Yes | Yes |
| My Timesheet monthly view | Yes | Yes | Yes |
| Direct `timesheet.tactokyo.com` | Yes | Yes | Yes |
| Reimbursement claim input | Yes | Yes | Yes |
| Own reimbursement query/status | Yes | Yes | Yes |
| Direct `expense.tactokyo.com` | Yes | Yes | Yes |
| Deny other employees' reimbursement records | Yes | Yes | Yes |
| Permission denial for unauthorized modules | Yes | Yes | Yes |
| Logout/session expiry | Yes | Yes | Yes |
| Audit log check | Operator | Operator | Operator |

Operational checks:

- Page load speed from Japan and India.
- Timesheet form save reliability.
- Reimbursement claim save reliability.
- Reimbursement attachment/upload behavior, if enabled.
- Date/time behavior and Japan working date expectations.
- Mobile browser layout for ordinary timesheet and reimbursement entry.
- Error messages when access is denied.
- Audit records after create/edit/submit tests.
- Whether users can operate smoothly enough for 30-40 days before migration.

Exit criteria:

- All six pilot users can complete assigned Timesheet and Reimbursement self-service test cases.
- No unauthorized module access observed.
- No ordinary consultant can view another person's reimbursement claim.
- Audit logs and backups are confirmed.
- Known issues are documented with severity and next action.

### Phase 6 — 30-40 day stabilization on MacBook pilot

Owner: Architecture + business owner

During the pilot period:

1. Keep user count small and controlled.
2. Review access logs and application audit logs weekly.
3. Track issues separately for:
   - connectivity
   - login/session behavior
   - timesheet business flow
   - reimbursement input/query flow
   - mobile usability
   - backup/restore
4. Avoid adding sensitive payroll, employee master, customer billing, or candidate modules to ordinary remote users.
5. Prepare Tencent Cloud Tokyo migration checklist in parallel.

Exit criteria:

- Remote access is stable enough for normal working use.
- Timesheet and reimbursement pilot users understand the workflow.
- Critical permission boundaries are verified.
- Backup and restore approach is clear.
- Business owner approves migration to Tokyo Tencent Cloud.

### Phase 7 — Migration to Tencent Cloud Tokyo server

Owner: IT infrastructure + application owner

Target after approximately 30-40 successful pilot days:

- Move from Nanjing MacBook pilot/staging host to the existing Tencent Cloud server deployed in Tokyo.
- Treat Tokyo Tencent Cloud as the production-like external access environment.

Recommended migration tasks:

1. Prepare server baseline:
   - OS patching
   - firewall/security group
   - non-root application user
   - Nginx or equivalent reverse proxy
   - HTTPS certificates
   - process manager/service restart strategy
   - log rotation
   - backup storage
2. Deploy required modules first:
   - Portal `8005`
   - User_admin `8006`
   - TAC-timesheet `8002`
   - TAC-reimbursement `8003`
3. Copy required data from MacBook:
   - User_admin data
   - Timesheet database
   - Reimbursement database
   - Reimbursement attachments/uploads
   - relevant audit logs
4. Point DNS to Tokyo server or edge gateway:
   - `ai.tactokyo.com`
   - `timesheet.tactokyo.com`
   - `expense.tactokyo.com`
5. Verify app public URLs and backend internal URLs on Tokyo server.
6. Run smoke tests from Japan, India, and Nanjing.
7. Keep MacBook as fallback for a short rollback window, but stop using it as the official external endpoint after cutover.

Production recommendation:

- Do not use a personal MacBook as the long-term production host.
- Use Tokyo Tencent Cloud for stable access, especially for Japan users and Japan business operations.
- Before adding more users or sensitive modules, strengthen backup, monitoring, TLS, WAF/security group rules, user lifecycle controls, and audit review.

## 9. Risk register

| Risk | Impact | Mitigation |
|---|---|---|
| MacBook sleeps, loses power, or disconnects | Remote users cannot access system | Disable sleep, power adapter, restart runbook, pilot support window |
| Nanjing network blocks or degrades tunnel | Japan/India users cannot connect reliably | Test early; keep VPS reverse proxy + WireGuard fallback; migrate to Tokyo Tencent Cloud after pilot |
| Direct app exposure without gateway | Unauthorized access risk | Use zero-trust access and HTTPS; avoid router port-forwarding |
| Shared test account | Poor auditability | Named accounts only |
| Cross-subdomain login friction | User confusion | Portal-first MVP; plan `.tactokyo.com` secure cookie alignment |
| Reimbursement claim privacy leak | Ordinary consultant may see another employee's claim or receipt | Enforce own-record query filter, test negative cases, keep finance pages restricted |
| Receipt/attachment data exposure | Personal or business-sensitive receipt data may leak | Use HTTPS, access gateway, per-user authorization, backup encryption where possible |
| Real HR/payroll data exposed to pilot users | Compliance/business risk | Minimum permissions, test data, NDA, audit logs |
| No backup before pilot | Data loss or hard-to-rollback test data | Backup all in-scope JSON databases and reimbursement attachments before and after pilot |
| Time zone confusion | Wrong work date or support timing | Use Japan business date rules for timesheet; publish support window |
| Migration cutover issues | Users lose access during move to Tokyo server | Prepare migration checklist, DNS rollback plan, MacBook fallback window, post-cutover smoke tests |

## 10. Immediate recommended next actions

Local application configuration has been prepared for the pilot domains. Operational details and manual DNS steps are in `Remote_Consultant_Access_Runbook.md`; example templates are under `deployment/remote-access/`.

1. Confirm whether Cloudflare can manage DNS for `tactokyo.com` or whether current DNS provider must be kept.
2. Confirm first remote pilot scope as Portal + Timesheet self-service + Reimbursement self-service.
3. Confirm reimbursement permission boundary: ordinary consultants can only input and query their own claims.
4. Prepare the six named pilot users in User_admin with the `remote_consultant` role or equivalent minimum permissions.
5. Configure `ai.tactokyo.com`, `timesheet.tactokyo.com`, `expense.tactokyo.com`, and restricted `useradmin.tactokyo.com` through Cloudflare Tunnel or a secure reverse proxy.
6. Start MacBook services with the environment variables shown in `deployment/remote-access/macbook-pilot-env.example`.
7. Run a Nanjing mobile-network test before inviting Japan/India users.
8. Run Japan and India pilot tests with the runbook checklist.
9. During the 30-40 day pilot, prepare the Tokyo Tencent Cloud migration checklist and backup/data transfer plan.
10. After pilot acceptance, migrate official remote access to the Tokyo Tencent Cloud server.

## 11. Decision summary

Current recommended decision:

- Use `ai.tactokyo.com` as the official TACAI Portal entry.
- Use `timesheet.tactokyo.com` as the direct Timesheet domain.
- Use `expense.tactokyo.com` as the direct Expense/Reimbursement self-service domain.
- Ordinary remote consultants can use Timesheet and Reimbursement only for their own records.
- Keep MacBook hosting only as controlled 30-40 day pilot/staging infrastructure.
- Use secure tunnel or VPS reverse proxy instead of direct router port-forwarding.
- Require outer access control plus User_admin app login.
- After the pilot succeeds and users are familiar with the flow, migrate to the existing Tencent Cloud Tokyo server for production-like external access.
