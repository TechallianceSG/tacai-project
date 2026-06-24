# TAC Tokyo Mail Project Plan

## 1. Project Overview

Project name: **TAC Tokyo Mail**  
Workspace directory: `tactokyomail/`  
Primary domain candidate: `tactokyo.com`  
Recommended mail domain: `tactokyo.com`  
Recommended webmail host: `mail.tactokyo.com`

TAC Tokyo Mail is a planned internal email infrastructure project for TAC operations. The first goal is not to replace the existing mature `tacjob.com` email environment. Instead, `tactokyo.com` should be used as a controlled new mail domain for internal operation, AI system integration, and dispatched / onboarding employee workflows.

## 2. Strategic Positioning

### 2.1 Keep Existing Email Stable

The current mature email service for `tacjob.com` should remain unchanged during the initial phases.

Reasons:

- Avoid disrupting current customer and business communication.
- Protect the reputation of the existing production email domain.
- Allow `tactokyo.com` to build domain reputation gradually.
- Reduce rollout risk while testing self-hosted mail operations.

### 2.2 New Domain Purpose

`tactokyo.com` should be positioned as a dedicated operational mail domain for:

- AI platform notifications.
- Employee onboarding workflows.
- Dispatched employee communication.
- Timesheet, reimbursement, payroll, and HR workflow reminders.
- Internal support mailboxes.
- Controlled pilot use before broader adoption.

Recommended initial email examples after `tactokyo.com` is mature:

- `admin@tactokyo.com`
- `hr@tactokyo.com`
- `onboarding@tactokyo.com`
- `noreply@tactokyo.com`
- `timesheet@tactokyo.com`
- `reimbursement@tactokyo.com`
- `payroll@tactokyo.com`
- `support@tactokyo.com`
- `test.employee@tactokyo.com`

### 2.3 Two-Step Mail Transition Strategy

TAC should use a two-step strategy for HR and employee communication.

Step 1 — near-term internal HR communication:

- Create and use `hradmin@tacjob.com` for HR/admin system communication, onboarding links, and employee intake notices.
- Keep the sender on the existing mature `tacjob.com` mail infrastructure to avoid delaying EmployeeAdmin and AI platform workflows while `tactokyo.com` is still being prepared.
- Use a display name such as `TAC HR Admin` or `TAC HR System` so employees understand the sender.
- Avoid using `info@tacjob.com` for system mail except temporary testing, because `info@` should remain a general business/customer contact address.

Step 2 — later migration to TAC Tokyo Mail:

- After `tactokyo.com` DNS, sending reputation, Webmail/IMAP needs, security, and operations are mature, migrate HR/admin system sending to `hradmin@tactokyo.com`, `onboarding@tactokyo.com`, or other dedicated `tactokyo.com` accounts.
- Keep the application mail configuration abstracted so the sender domain can be changed through configuration rather than code changes.
- During migration, keep `Reply-To` and forwarding policies clear so employee replies are not lost.

This transition keeps current HR communication reliable while still preserving the long-term goal of an independent `tactokyo.com` mail environment.

## 3. Business Goals

### 3.1 Internal Use

Build a self-controlled mail environment for TAC internal workflows while reducing dependency on paid per-user mail platforms for non-core or high-volume employee accounts.

Expected benefits:

- Lower long-term mailbox cost for dispatched employees.
- Better integration with TAC internal systems.
- Better control over account lifecycle.
- Easier creation and suspension of employee mail accounts.
- Dedicated domain for operational and system messages.

### 3.2 AI Platform Integration

Use the mail system as an infrastructure layer for the AI recruitment / HR platform.

Initial AI integration should focus on controlled sending, not unrestricted reading.

Recommended first integrations:

- AI-generated email drafts for HR review.
- System notifications through SMTP.
- Onboarding reminder emails.
- Missing-document reminder emails.
- Timesheet submission reminders.
- Reimbursement workflow reminders.
- Contract renewal or visa-status reminder emails.

Later integrations may include:

- Inbound document mailbox parsing.
- Receipt / document extraction workflows.
- Candidate and employee communication logging.
- AI-assisted email classification.
- AI-assisted reply draft generation.

### 3.3 Dispatched Employee Use

Provide mail accounts for dispatched employees, expatriate employees, onboarding employees, or project-based staff where TAC needs controlled communication and lifecycle management.

Important employee lifecycle states:

- `pending_activation`
- `active`
- `suspended`
- `forwarding_only`
- `archived`
- `deleted`

Recommended lifecycle flow:

1. Employee confirmed for onboarding.
2. Mailbox is created by HR/admin or automatically by the employee administration system.
3. Initial credential is delivered through a secure channel.
4. Employee must change password at first login.
5. Account remains active during assignment/employment.
6. Account is suspended when employment or assignment ends.
7. Mail forwarding or archival is configured if needed.
8. Mailbox is retained according to company retention policy.
9. Mailbox is archived or deleted after retention period.

## 4. Recommended Technical Approach

### 4.1 Do Not Build SMTP/IMAP/POP3 From Scratch

The project should not implement a mail server protocol stack from scratch. SMTP, IMAP, POP3, spam filtering, queue handling, TLS, DKIM, authentication, and mail storage are mature but operationally sensitive components.

Recommended approach:

- Use a mature open-source mail suite as the foundation.
- Build TAC-specific automation and AI integration around it.
- Avoid modifying core mail server source code unless absolutely necessary.

### 4.2 Recommended Mail Platform

Primary recommendation: **mailcow: dockerized**

Reasons:

- Open-source email/groupware suite.
- Docker-based deployment.
- Includes web management interface.
- Includes Postfix, Dovecot, Rspamd, SOGo, MariaDB, Redis, and related services.
- Suitable for small and medium internal company mail operations.
- Supports webmail, SMTP, IMAP, POP3, DKIM, spam filtering, and admin workflows.

Alternative options:

- Mailu
- docker-mailserver + Roundcube

### 4.3 Recommended Initial Architecture

```text
Users / Employees / HR / Lark External Mail Client
        |
        | Webmail / IMAP / SMTP
        v
mail.tactokyo.com
        |
        v
Japan Tencent Cloud Server
        |
        | mailcow or equivalent mail suite
        | - Webmail
        | - SMTP submission
        | - IMAP
        | - POP3 optional
        | - DKIM/SPF/DMARC support
        | - Spam filtering
        | - Admin UI
        |
        +--> Encrypted backup to US Tencent Cloud Server
        +--> Optional backup MX on US Tencent Cloud Server
```

Recommended roles:

- Japan server: primary mail server.
- US server: encrypted backup destination and later backup MX.

Avoid placing the initial mail service directly on the same runtime surface as sensitive ATS systems unless isolation, firewalling, and backup are properly configured.

## 5. Domain and DNS Plan

### 5.1 Recommended Hostnames

Use `tactokyo.com` for email addresses and service hostnames.

Recommended names:

- Mail address domain: `tactokyo.com`
- Webmail: `mail.tactokyo.com`
- SMTP: `smtp.tactokyo.com`
- IMAP: `imap.tactokyo.com`
- Optional US backup host: `mail-us.tactokyo.com`

Note: `www.tactokyo.com` should be reserved for a website, not used as the main email domain.

### 5.2 Required DNS Records

Initial records:

```text
A     mail.tactokyo.com       -> Japan server IP
A     smtp.tactokyo.com       -> Japan server IP, or CNAME to mail.tactokyo.com
A     imap.tactokyo.com       -> Japan server IP, or CNAME to mail.tactokyo.com
MX    tactokyo.com            -> mail.tactokyo.com priority 10
TXT   tactokyo.com            -> SPF record
TXT   default._domainkey      -> DKIM public key
TXT   _dmarc.tactokyo.com     -> DMARC policy
PTR   Japan server IP         -> mail.tactokyo.com
```

Later backup records:

```text
A     mail-us.tactokyo.com    -> US server IP
MX    tactokyo.com            -> mail-us.tactokyo.com priority 20
PTR   US server IP            -> mail-us.tactokyo.com
```

### 5.3 Recommended DMARC Rollout

Start safely:

```text
v=DMARC1; p=none; rua=mailto:dmarc@tactokyo.com
```

After stable authentication and monitoring:

```text
v=DMARC1; p=quarantine; rua=mailto:dmarc@tactokyo.com
```

Only after confidence is high:

```text
v=DMARC1; p=reject; rua=mailto:dmarc@tactokyo.com
```

## 6. Functional Scope

### 6.1 MVP Scope

MVP should include:

- `tactokyo.com` email domain setup.
- Webmail access.
- IMAP over TLS.
- SMTP submission over TLS.
- POP3 over TLS as optional compatibility.
- Admin mailbox creation and suspension.
- DKIM/SPF/DMARC setup.
- TLS certificate setup.
- Basic spam filtering.
- Basic outbound rate limits.
- Initial backup routine.
- Test accounts for HR/admin/system usage.
- SMTP credentials for AI platform and internal systems.

### 6.2 Out of Scope for MVP

Do not include in MVP:

- Replacement of `tacjob.com` email.
- Large-scale marketing email.
- Cold outbound sales campaigns.
- Full active-active two-region mailbox replication.
- AI access to all employee mailboxes.
- Custom SMTP/IMAP/POP3 server implementation.
- Customer-facing commercial mailbox SaaS.

## 7. AI System Integration Plan

### 7.1 Phase 1: Outbound SMTP Integration

Internal systems should send through authenticated SMTP accounts.

Near-term sender account while `tactokyo.com` is being prepared:

- `hradmin@tacjob.com` for EmployeeAdmin, onboarding, and HR intake communication.

Recommended future `tactokyo.com` system accounts:

- `hradmin@tactokyo.com`
- `noreply@tactokyo.com`
- `onboarding@tactokyo.com`
- `timesheet@tactokyo.com`
- `reimbursement@tactokyo.com`
- `payroll@tactokyo.com`

Each system should have separate credentials and sending limits. Application code should read SMTP host, port, username, password, sender, and reply-to from configuration so the system can migrate from `hradmin@tacjob.com` to `tactokyo.com` without code rewrites.

Benefits:

- Easier audit.
- Easier credential revocation.
- Easier rate limiting.
- Clear ownership per workflow.

### 7.2 Phase 2: AI Draft Generation

AI should generate draft emails for HR/admin review before sending.

Recommended workflow:

```text
Business event
  -> AI generates email draft
  -> HR/admin reviews and approves
  -> System sends through SMTP
  -> Send result is logged
  -> Related employee/candidate/project record is updated
```

### 7.3 Phase 3: Controlled Inbound Mail Parsing

Only dedicated process mailboxes should be parsed by AI.

Possible mailboxes:

- `documents@tactokyo.com`
- `expense@tactokyo.com`
- `onboarding@tactokyo.com`

Do not initially allow AI to read all employee mailboxes.

Required controls:

- Explicit mailbox allowlist.
- Audit log of every AI access.
- Attachment type restrictions.
- Sensitive-data handling policy.
- Human review for high-risk outputs.

## 8. Employee Mailbox Policy

### 8.1 Account Naming

Recommended format:

```text
firstname.lastname@tactokyo.com
```

If duplicate names exist:

```text
firstname.lastname2@tactokyo.com
```

The email address should be mapped internally to a stable employee ID.

### 8.2 Initial Pilot Users

Recommended pilot size:

- 3-5 admin/system accounts.
- 5-20 dispatched employee test accounts.

Pilot users should include:

- HR admin.
- AI/system notification account.
- One onboarding mailbox.
- Several employee test accounts.

### 8.3 Password and Authentication

Minimum requirements:

- Strong initial password.
- Mandatory password change at first login if supported by selected platform/workflow.
- No shared employee passwords.
- Separate app credentials for systems.
- Disable or rotate credentials when employees leave.
- Enable MFA if available and practical.

## 9. Security Requirements

Minimum production requirements:

- HTTPS for webmail/admin.
- TLS for SMTP/IMAP/POP3.
- Disable plaintext authentication without TLS.
- Firewall only required ports.
- Fail2ban or equivalent brute-force protection.
- Strong admin password and restricted admin access.
- No open relay.
- Outbound sending rate limits.
- Spam and abuse monitoring.
- Daily backup.
- Regular restore test.
- Admin operation logging.
- Mail logs retained according to policy.
- Security update process.

Required public ports:

```text
25   SMTP server-to-server mail transfer
465  SMTPS, if enabled
587  SMTP submission for clients/systems
993  IMAPS
995  POP3S, optional
80   HTTP for certificate challenge / redirect
443  HTTPS webmail/admin
```

## 10. Audit and Compliance Requirements

Because this project may support recruitment, dispatch, payroll, onboarding, and employee administration workflows, it should respect Japan labor, dispatch, and privacy compliance expectations.

Audit logs should include:

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

Important audit events:

- Mailbox created.
- Mailbox suspended.
- Mailbox deleted or archived.
- Password reset.
- Forwarding enabled/disabled.
- System SMTP credential created/rotated/revoked.
- AI access to mailbox or attachment.
- AI-generated draft approved/sent.
- Admin login.
- Failed login threshold exceeded.

Audit logs must be read-only and must not be deleted.

## 11. Backup and Disaster Recovery

### 11.1 Backup Targets

Recommended:

- Primary backup: encrypted backup stored on US Tencent Cloud server.
- Optional additional backup: object storage or offline backup.

### 11.2 Backup Content

Back up:

- Mailbox data.
- Mail server configuration.
- DKIM keys.
- Database.
- User/account configuration.
- TLS-related configuration where appropriate.
- Audit logs.

### 11.3 Recovery Objectives

Initial targets:

- RPO: 24 hours for MVP.
- RTO: 1 business day for MVP.

Future targets after production adoption:

- RPO: 1-4 hours.
- RTO: less than 4 hours.

### 11.4 Backup MX

The US server can later act as backup MX.

Purpose:

- Temporarily receive mail if Japan server is unavailable.
- Queue and forward mail when primary server returns.

Backup MX is not the same as full active-active mailbox replication.

## 12. Rollout Phases

### Phase 0: Feasibility Check

Tasks:

- Confirm ownership and DNS control of `tactokyo.com`.
- Confirm Tencent Cloud allows SMTP port 25.
- Confirm ability to set reverse DNS / PTR.
- Check Japan and US server IP reputation.
- Confirm server resources.
- Decide whether mail service should run on existing server or a dedicated VPS.

Deliverables:

- Feasibility checklist.
- Go/no-go decision for MVP deployment.

### Phase 1: Single-Node MVP

Tasks:

- Deploy mailcow or selected mail suite on Japan server.
- Configure `mail.tactokyo.com`.
- Configure TLS.
- Configure SPF/DKIM/DMARC.
- Create test accounts.
- Test Webmail, IMAP, SMTP, and optional POP3.
- Test sending to Gmail, Outlook, Yahoo, Lark, and current `tacjob.com` mailbox.

Deliverables:

- Working internal mail service.
- Test result report.
- Initial operations runbook.

### Phase 2: Internal System Sending

Tasks:

- Create system mailboxes.
- Configure SMTP credentials for AI platform and internal apps.
- Add sending limits.
- Log mail send events in business systems.
- Create template-based notification flows.

Deliverables:

- AI/platform outbound mail integration.
- Basic send audit log.
- Notification templates.

### Phase 3: Employee Pilot

Tasks:

- Create 5-20 pilot employee mailboxes.
- Define employee onboarding/offboarding mailbox lifecycle.
- Test Webmail and Lark/mobile client access.
- Collect usability feedback.
- Monitor spam, delivery, and login issues.

Deliverables:

- Employee pilot report.
- Revised mailbox policy.
- Security and support checklist.

### Phase 4: Backup and Disaster Recovery

Tasks:

- Configure encrypted backup to US server.
- Test restore process.
- Configure backup MX if feasible.
- Document failover procedure.

Deliverables:

- Backup schedule.
- Restore test evidence.
- DR procedure.

### Phase 5: Controlled AI Mail Processing

Tasks:

- Create dedicated inbound mailboxes.
- Implement AI allowlist access.
- Add attachment processing rules.
- Add audit logs for AI mailbox access.
- Add human review for sensitive outputs.

Deliverables:

- Controlled AI inbound processing prototype.
- Audit trail.
- Privacy and data handling checklist.

## 13. Success Metrics

MVP success metrics:

- Webmail login works reliably.
- IMAP/SMTP works with common clients.
- Lark external mailbox connection works if required.
- SPF/DKIM/DMARC pass for outbound email.
- Gmail and Outlook test delivery is acceptable.
- No open relay exposure.
- Backups complete successfully.
- Restore process is tested at least once.
- AI platform can send through authenticated SMTP.

Pilot success metrics:

- 5-20 employee accounts operate without major issues.
- HR can create/suspend accounts using documented process.
- Employee onboarding emails are delivered successfully.
- System notification mail is logged and traceable.
- No severe spam/abuse incident occurs during pilot.

## 14. Key Risks and Mitigation

| Risk | Impact | Mitigation |
|---|---|---|
| New domain has low sending reputation | Emails may enter spam | Warm up slowly, configure SPF/DKIM/DMARC, avoid bulk mail |
| Cloud IP is blocked or poor reputation | Delivery failure | Check blacklist, configure PTR, consider SMTP relay for critical mail |
| Port 25 blocked | Cannot send server-to-server mail directly | Confirm with Tencent Cloud before deployment |
| Mailbox account compromised | Spam abuse and domain damage | Strong passwords, rate limits, fail2ban, monitoring |
| AI accesses sensitive mail improperly | Privacy/compliance risk | Use allowlisted process mailboxes only, log all access |
| Mail service affects website/ATS resources | Business system instability | Prefer dedicated server or strong isolation |
| Backup exists but restore not tested | False sense of safety | Schedule regular restore tests |

## 15. Initial Open Questions

- Is `tactokyo.com` already registered and under TAC DNS control?
- Which Tencent Cloud server should host the MVP?
- Can Tencent Cloud provide PTR / reverse DNS for the selected IP?
- Is SMTP port 25 open on both Japan and US servers?
- Should a dedicated VPS be created for mail instead of reusing website/ATS servers?
- What is the first pilot user count?
- Should POP3 be enabled, or should the project standardize on IMAP + SMTP?
- What retention period should apply to dispatched employee mailboxes?
- Which AI platform module should send the first emails?

## 16. Recommended Immediate Next Steps

1. Confirm `tactokyo.com` DNS ownership.
2. Confirm server candidate and IP reputation.
3. Confirm port 25 and PTR availability with Tencent Cloud.
4. Decide between mailcow and Mailu for MVP.
5. Prepare DNS records but do not switch production mail until testing.
6. Deploy MVP on Japan server.
7. Create test accounts and run delivery tests.
8. Integrate one internal system SMTP flow.
9. Pilot with a small employee group.
10. Add backup and disaster recovery before broader rollout.
