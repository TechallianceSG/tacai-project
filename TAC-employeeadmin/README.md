# TAC-employeeadmin

TAC-employeeadmin is a standalone local MVP project for employee administration.

The product goal is to build a bilingual English/Japanese Employee Management module as the master data foundation for Payroll, Timesheet, Expense, Invoice, Training, and Dispatch Compliance management.

## Core modules

- Employee Profile.
- Employment Information.
- Payroll Information.
- Visa Management.
- Dispatch Compliance.
- Skills & Language Profile.
- Document Management.
- Search & Dashboard.
- Audit Trail.

## Implemented phases

### Phase 1 — Employee Master

- English/Japanese/Simplified Chinese UI labels from `i18n/en.json`, `i18n/ja.json`, and `i18n/zh.json`.
- Language switching with `?lang=en`, `?lang=ja`, and `?lang=zh`.
- Dashboard baseline: total employees, active employees, new joiners this month.
- Employee list with keyword search, filters, and permission-aware View/Edit actions.
- Employee create/edit/detail screens.
- Employee Profile and Employment Information fields.
- Internal system IDs remain stable and generated as `EMP-0001`, `EMP-0002`, etc. for routes/audit/document links.
- Editable employee numbers are required, manually entered, unique, searchable, and shown to operators as the primary employee identifier.
- Local audit trail for create/update/status-change events.

### Phase 2 — Payroll, Visa, Dispatch Compliance

- Payroll Information section with independent edit route, including optional bank SWIFT Code for overseas employee payments.
- Visa Management section with independent edit route.
- Dispatch Compliance section with independent edit route.
- Dashboard additions: dispatch employees, foreign employees, visa expiry alerts, probation alerts, and alert table.
- Audit actions for payroll, visa, and dispatch updates.
- Sensitive payroll, bank, residence card, and passport fields are intentionally not shown in employee list views.

### UI polish — Employee detail object page

- Employee detail pages use an SAP/Fiori-inspired object page header.
- Read-only employee fields are grouped into framed sections.
- Short fields use responsive multi-column cards on desktop; longer notes, addresses, skill lists, and timestamps span the full row.
- Document rows remain tabular with authorized Open/Download actions and horizontal scrolling where needed.

### Phase 3A — Skills & Language Profile

- Skills & Language Profile section with independent edit route.
- Japanese level and English level enum fields.
- Native languages, additional languages, IT skills, engineering skills, certifications, and industry experience stored as arrays from comma-separated inputs.
- Employee list filters for Japanese level, English level, and skill keyword.
- Audit action for skills/language updates.

### Phase 3B — Document Management

- Local document management with independent edit/upload route.
- Document records are embedded under each employee as local JSON metadata.
- Supported metadata: document type, title, issuer, document date, expiry date, received date, storage reference, status, notes, original filename, stored filename, content type, file size, upload time, and uploader.
- Add/edit/delete document metadata rows and upload multiple local files.
- Uploaded files are stored under `docs/empdoc/` and ignored by git.
- Stored filenames use a stable internal-system-ID/date/sequence format such as `E001202606160001.pdf`; files are not renamed when an editable employee number changes.
- Audit action for document metadata/upload updates.
- Uploaded files can be opened inline or downloaded through authenticated employee document routes by users with `employee_management.documents.manage` or `system_admin`.

### Phase 4 — Reporting, Advanced Dashboard, and Data Quality

- Dashboard metric cards link to employee list and report drill-downs.
- Reports index at `/reports`.
- Missing required data, visa expiry, probation ending, dispatch assignment, document expiry, missing document, data quality, data completion, and required document matrix reports.
- Safe employee master CSV export at `/exports/employees.csv`.
- Duplicate employee number and duplicate email checks.
- Computed employee data completion and required document readiness indicators on the employee object page and dashboard.
- Inferred required document matrix based on employee status and nationality.
- SAP/Fiori-inspired object-page styling applied to payroll, visa, dispatch, skills/language, and documents edit forms.
- SAP/Fiori-inspired typography polish increases form labels, input text, read-only field values, and mobile touch targets for better desktop/mobile readability.
- Low-risk validation hardening for emergency contact email and resignation date order.
- Backward-compatible audit records now include project-required fields with redacted before/after snapshots.

### Labor Contract Renewal Tracking

- Employment Information includes direct HR input fields for labor contract start date and labor contract end date.
- Japan 正社员/permanent employees can use `2099-12-12` as the practical open-ended contract end date; the UI displays it as open-ended/permanent instead of a normal renewal date.
- Dashboard and `/reports/labor-contract-renewals` track finite labor contracts already due or within the 90-day renewal alert window.
- CSV import templates, field guides, samples, and safe export include optional labor contract start/end date columns.
- Labor contract dates are separate from Dispatch Compliance assignment start/end dates.

### Phase 5 — Employee History and Change Traceability

- Employee records include employment, visa, and dispatch assignment history arrays.
- Updates to employment, visa, and dispatch trigger fields append automatic history snapshots.
- Authorized users can manually add/edit history records from employee detail pages.
- History records support local attachment upload and protected Open/Download actions through application routes.
- History create/update actions are audit logged, and all history labels are available in English, Japanese, and Simplified Chinese.

### Phase 7 — Employee Onboarding Self-Service

- HR users can create secure onboarding requests, upload case-specific HR documents, and select per-document signing modes.
- SMTP invitation, HR completion notification, and return-to-candidate correction emails use Master Data email configuration and default to `HRadmin@tacjob.com`; onboarding invitations now require HR to review the generated email draft, confirm the candidate recipient, keep default CC `hradmin@tacjob.com`, optionally add up to three extra CC addresses, and then send.
- Candidates access the self-service form by token, review/download HR documents, upload required or `other` documents, and submit a draft package for HR review.
- Browser hand-drawn electronic signature supports mouse/touch canvas capture, consent checkbox, server-side base64 PNG validation, signature evidence metadata, protected HTML evidence packets, and audit logging.
- Stage 3.5 generates a signed PDF for PDF source documents by appending a signature certificate page while preserving the original PDF and HTML evidence packet.
- Stage 3.5 gates candidate token access with a one-time email verification code before form, document, upload, or signature access; HR can prepare a manual email package with a fresh link and one-time code if SMTP is unavailable.
- HR review can open/download onboarding documents and signature evidence, approve/return packages, and import approved submissions into Employee Master while copying onboarding files and signature evidence into protected employee document storage.
- Candidate self-service intentionally excludes Dispatch Compliance/client assignment fields; those are maintained internally by HR/dispatch operations after review because candidates often do not know the final dispatch/project assignment.
- Candidate document upload now shows a required-document checklist, already uploaded candidate files, selected-file preview, upload limits, and submit-time missing-document/signature checks while still allowing draft saves.
- Encrypted My Number viewing and production legal/storage hardening remain later slices.

## Portal/User_admin integration

TAC-employeeadmin is connected to TACAI Portal and protected by TACAI User Management.

- Portal URL: `http://127.0.0.1:8005`
- Employee Mgmt URL: `http://127.0.0.1:8004/dashboard`
- User_admin URL: `http://127.0.0.1:8006`
- Required module permission: `employee_management.access`

All non-health EmployeeAdmin routes require a valid User_admin `tacai_session_id` cookie. Unauthenticated users are redirected to User_admin login with a local `next` return URL.

## Run locally

Install approved Python dependencies when using signed PDF generation:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 -m pip install -r requirements.txt
```

System Parameters are now owned by Master Data on port `8007`. To let EmployeeAdmin send onboarding email, start Master Data with the same internal token and the SMTP password environment variable referenced by `email.onboarding.smtp`, then start EmployeeAdmin with the token. For stable onboarding verification across restarts, also set a private `ONBOARDING_VERIFICATION_SECRET` for the EmployeeAdmin process:

```bash
export MASTERDATA_INTERNAL_API_TOKEN="dev-local-token"
export ONBOARDING_SMTP_PASSWORD="<smtp-app-password>"  # for the Master Data process
export ONBOARDING_VERIFICATION_SECRET="<private-random-secret>"  # for EmployeeAdmin
```

EmployeeAdmin reads onboarding SMTP settings from Master Data and no longer stores or edits active System Parameters locally.

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 backend/app.py --host 127.0.0.1 --port 8004
```

## Public-internet employee self-service pilot

For the Tokyo dispatch onboarding pilot, do not send employees a `http://127.0.0.1:8004/...` link. That address works only on the machine running EmployeeAdmin. Use a temporary HTTPS tunnel or a real HTTPS reverse proxy so phones on mobile data and computers outside the office WiFi can open the same link.

Recommended temporary tunnel setup:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
export EMPLOYEE_ADMIN_PUBLIC_BASE_URL="https://<temporary-https-tunnel-domain>"
export TACAI_ALLOWED_PUBLIC_HOSTS="<temporary-https-tunnel-domain>"
export MASTERDATA_INTERNAL_API_TOKEN="dev-local-token"
export ONBOARDING_VERIFICATION_SECRET="<private-random-secret>"
python3 backend/app.py --host 127.0.0.1 --port 8004
```

Then point Cloudflare Tunnel, ngrok, or another approved HTTPS tunnel to `http://127.0.0.1:8004`. Keep Master Data running with the same `MASTERDATA_INTERNAL_API_TOKEN` and SMTP password configuration if email delivery is used. If the proxy has an upload body limit, set it to at least `25 MB` to match the EmployeeAdmin onboarding upload limit.

External-access checklist before sending a real onboarding link:

1. `/health` works through the HTTPS tunnel URL.
2. HR onboarding detail page shows the public link readiness checks as complete or expected for the test.
3. The generated candidate link starts with `https://<temporary-https-tunnel-domain>/onboarding/token/...`.
4. A phone with WiFi disabled can open the link, receive/enter the verification code, sign, upload, save draft, and submit.
5. A desktop browser outside the office network can repeat the same flow.
6. HR can review signature evidence, signed PDF status, manual signed uploads, and audit logs after submission.

## Health check

```bash
curl -s http://127.0.0.1:8004/health
```

Expected response:

```text
OK
```

## Main routes

- `/` — dashboard.
- `/?lang=ja` — Japanese dashboard.
- `/employees` — employee list, search, and filters.
- `/employees/new` — create employee.
- `/onboarding` — Phase 7 onboarding request list for HR users.
- `/onboarding/new` — create a secure onboarding request.
- `/onboarding/ONB-0001` — onboarding request detail, candidate link preparation, and HR document upload.
- `/onboarding/ONB-0001/email-draft` — HR preview/confirmation page for the candidate invitation email before sending; default CC is `hradmin@tacjob.com` and HR can add up to three extra CC addresses.
- `/onboarding/ONB-0001/review` — HR review, approval, return, and Employee Master import.
- `/onboarding/token/<token>` — candidate self-service onboarding form through a secure token link.
- `/master-data/system-parameters` — redirects to Master Data System Parameters on port `8007`; EmployeeAdmin no longer renders this feature locally.
- `/employees/EMP-0001` — employee detail.
- `/employees/EMP-0001/edit` — edit employee profile/employment information.
- `/employees/EMP-0001/payroll/edit` — edit payroll information.
- `/employees/EMP-0001/visa/edit` — edit visa management information.
- `/employees/EMP-0001/dispatch/edit` — edit dispatch compliance information.
- `/employees/EMP-0001/skills/edit` — edit skills and language profile.
- `/employees/EMP-0001/documents/edit` — edit document metadata and upload local employee documents.
- `/employees/EMP-0001/documents/DOC-0001/open` — open an uploaded employee document inline when authorized.
- `/employees/EMP-0001/documents/DOC-0001/download` — download an uploaded employee document when authorized.
- `/employees/EMP-0001/history/employment/new` — add employment history when authorized.
- `/employees/EMP-0001/history/employment/EMPLOYMENT-HIST-0001/edit` — edit employment history when authorized.
- `/employees/EMP-0001/history/visa/new` — add visa history when authorized.
- `/employees/EMP-0001/history/dispatch/new` — add dispatch assignment history when authorized.
- `/employees/EMP-0001/history/visa/VISA-HIST-0001/attachments/ATT-0001/open` — open a history attachment when authorized.
- `/employees/EMP-0001/history/visa/VISA-HIST-0001/attachments/ATT-0001/download` — download a history attachment when authorized.
- `/reports` — Phase 4 reports index.
- `/reports/missing-required-data` — missing required employee data report.
- `/reports/visa-expiry` — visa expiry report.
- `/reports/probation-ending` — probation ending report.
- `/reports/labor-contract-renewals` — labor contract renewal report for finite contracts due within 90 days or already due.
- `/reports/dispatch-assignments` — dispatch assignment report.
- `/reports/document-expiry` — document expiry report.
- `/reports/missing-documents` — explicit missing document metadata report.
- `/reports/data-quality` — duplicate employee number/email report.
- `/reports/data-completion` — employee data completion and missing field report.
- `/reports/required-document-matrix` — inferred required document readiness report.
- `/exports/employees.csv` — safe non-sensitive employee CSV export.
- `/audit-logs` — audit log table.
- `/employees.json` — local employee JSON endpoint. This is local diagnostic/export data and includes sensitive Phase 2/3 fields.
- `/api/masterdata/entities` — authenticated local proxy for Master Data entity options.
- `/api/masterdata/departments?entity_id=<entity_id>` — authenticated local proxy for Master Data department options filtered by entity.
- `/api/masterdata/teams?department_id=<department_id>` — authenticated local proxy for Master Data team options filtered by department.
- `/api/timesheet/employees` — safe authenticated employee lookup endpoint for TAC-timesheet. Returns employee ID, employee number, display name, email, entity ID, department ID, team ID, department display value derived from the canonical department ID, employment type, and status for selectable employees.
- `/api/timesheet/dispatch-assignment?employee_id=<employee_id>&work_date=<YYYY-MM-DD>` — safe authenticated employee/date dispatch assignment lookup. Legacy `employee_no` remains supported; pass `entity_id` or `employee_id` when employee numbers may repeat across legal entities.
- `/audit_logs.json` — local audit log JSON endpoint.

## Master Data integration

EmployeeAdmin is integration-ready for organization master data managed by the separate Master Data service on local port `8007`.

- Employee employment records store canonical `employment.entity_id`, `employment.department_id`, and `employment.team_id` values when selected.
- Employee list, detail, reports, safe CSV export, and Timesheet employee lookup resolve Entity/Department/Team display labels from Master Data IDs; storage remains ID-only.
- The old free-text `employment.department` fallback field is no longer shown, saved, exported, or kept in active employee records.
- EmployeeAdmin forwards the User_admin `tacai_session_id` cookie when proxying Master Data API calls.
- EmployeeAdmin reads onboarding SMTP settings from Master Data System Parameters through `GET /api/master-data/system-parameters/outbound-email-onboarding` with `MASTERDATA_INTERNAL_API_TOKEN`.
- Expected upstream endpoints are `GET /api/entities`, `GET /api/departments?entity_id=<entity_id>`, and `GET /api/teams?department_id=<department_id>`.
- Existing legacy department text was intentionally cleaned from active employee records; authorized operators should select the correct entity, department, and team after the Master Data service is running.

## System check

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 -m py_compile backend/app.py
python3 -m json.tool database/employees.json
python3 -m json.tool database/audit_logs.json
python3 -m json.tool i18n/en.json
python3 -m json.tool i18n/ja.json
python3 -m json.tool i18n/zh.json
curl -s http://127.0.0.1:8004/health
```

## Local employee document files

Uploaded employee documents are stored locally under:

```text
docs/empdoc/
```

Stored filenames are generated by the app and follow this pattern:

```text
E001yyyymmdd0001.ext
```

Example:

```text
E001202606160001.pdf
```

The employee JSON record stores the relative `storage_reference` path. Raw storage paths are not served directly; authorized users open or download files through `/employees/<employee_id>/documents/<document_id>/open` and `/download` routes, where `<employee_id>` is the internal system ID rather than the editable employee number. The `docs/empdoc/` folder is ignored by git because it may contain sensitive employee documents.

## Data files

- `database/employees.json` — local employee master records.
- `database/audit_logs.json` — local audit trail.
- `i18n/en.json` — English UI labels.
- `i18n/ja.json` — Japanese UI labels.
- `i18n/zh.json` — Simplified Chinese UI labels.

## Documents

- `docs/Requirements.md` — product objectives and module requirements.
- `docs/Project_Plan.md` — phased roadmap and MVP plan.
- `docs/Data_Schema.md` — local JSON data schema draft and implemented Phase 1 through Phase 5 structures.
- `docs/Employee_Onboarding_Self_Service_Plan.md` — planned employee onboarding self-service, contract/NDA electronic signature, HR review, and Employee Master import workflow.
