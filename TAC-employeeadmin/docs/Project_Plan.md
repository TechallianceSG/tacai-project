# TAC-employeeadmin Project Plan

## Project Objectives

Build a bilingual English/Japanese Employee Management module as the master data foundation for the wider TAC business system landscape:

- Payroll management.
- Timesheet management.
- Expense/reimbursement management.
- Invoice and billing support.
- Training management.
- Dispatch compliance management.

TAC-employeeadmin owns employee master data and employee administration workflows. Other projects may later consume this data, but this project should remain standalone until integration is explicitly requested.

## Product Principles

1. **Employee master first** — create a reliable single source of truth for employee data before building integrations.
2. **Bilingual by design** — UI labels must support English and Japanese through i18n resources.
3. **Local-first MVP** — keep the first version dependency-free and local-data based unless dependencies or production infrastructure are approved.
4. **Auditability** — employee master changes affect payroll, compliance, and dispatch operations, so key changes must be traceable.
5. **Sensitive data protection** — personal, payroll, visa, My Number related, and identity document data must be handled as sensitive information.
6. **Integration-ready, not integration-first** — keep immutable internal system IDs for integration stability while exposing editable business employee numbers for operators; defer live integration until business flows are confirmed.

## Core Modules

1. Employee Profile.
2. Employment Information.
3. Payroll Information.
4. Visa Management.
5. Dispatch Compliance.
6. Skills & Language Profile.
7. Document Management.
8. Search & Dashboard.
9. Audit Trail.

## Language Requirements

- UI supports English and Japanese.
- Language switching uses `?lang=en` and `?lang=ja`.
- UI labels, navigation text, button text, status names, validation messages, dashboard labels, and audit action labels use i18n resources.
- Current resource files:
  - `i18n/en.json`.
  - `i18n/ja.json`.
  - `i18n/zh.json`.
- Data values use stable internal enum keys, not translated display strings.

## Phase 1 — Employee Master MVP

Status: implemented.

Implemented scope:

- i18n foundation.
- Employee list/detail/create/edit.
- Employee Profile and Employment Information.
- Dashboard baseline.
- Search/filter baseline.
- Audit trail baseline.
- Local JSON persistence.

## Phase 2 — Payroll, Visa, and Dispatch Compliance Data

Status: implemented.

Implemented scope:

- Payroll information section, including optional bank SWIFT Code for overseas employee payments.
- Visa management section.
- Dispatch compliance section.
- Independent edit routes for payroll, visa, and dispatch.
- Dashboard metrics and alerts for dispatch employees, foreign employees, visa expiry, and probation.
- Audit actions: `payroll_updated`, `visa_updated`, `dispatch_updated`.
- Sensitive fields hidden from employee list views.

## Phase 3A — Skills & Language Profile

Status: implemented.

Goal: support employee capability search and staffing/training suitability data.

Implemented scope:

- Language profile:
  - Japanese level.
  - English level.
  - Native languages.
  - Additional languages.
  - Language notes.
- Skills profile:
  - Primary skill.
  - Secondary skill.
  - Years of experience.
  - IT skills.
  - Engineering skills.
  - Certifications.
  - Industry experience.
  - Skills notes.
- Independent edit route:
  - `/employees/<employee_id>/skills/edit`.
- Employee list filters:
  - Japanese level.
  - English level.
  - Skill keyword.
- Audit action:
  - `skills_language_updated`.

Phase 3A acceptance criteria status:

- User can edit skills/language independently: done.
- User can search/filter employees by skills and language levels: done.
- Changes are audit logged: done.
- English/Japanese labels are implemented: done.

## Phase 3B — Document Management

Status: implemented as metadata-only MVP.

Goal: track required employee document metadata without file upload risk.

Implemented scope:

- Embedded per-employee document metadata records.
- Supported metadata:
  - Document ID.
  - Document type.
  - Title.
  - Issuer.
  - Document date.
  - Expiry date.
  - Received date.
  - Storage reference.
  - Status.
  - Notes.
- Independent edit route:
  - `/employees/<employee_id>/documents/edit`.
- Add/edit/delete document metadata rows.
- Audit action:
  - `documents_updated`.

Phase 3B acceptance criteria status:

- User can track document metadata per employee: done.
- Document actions are audit logged: done.
- File upload is not implemented by design: done.

Phase 3B limitation:

- Document file upload is deferred until login/RBAC, storage policy, file validation, and security controls are approved.

## Phase 4 — Reporting, Advanced Dashboard, and Data Quality

Status: implemented.

Goal: improve operational visibility and data governance.

Implemented scope:

- Dashboard drill-down links from metric cards to employee list and report pages.
- Reports index at `/reports`.
- Missing required data report.
- Visa expiry report using the 90-day alert window.
- Probation ending report using the 30-day alert window.
- Dispatch assignment report.
- Document expiry report and explicit missing document report for metadata-only document records.
- Data quality report for duplicate employee numbers and duplicate email addresses.
- Data completion report and employee object-page completion indicators.
- Required document matrix report inferred from employee status and nationality.
- Safe CSV export at `/exports/employees.csv` for non-sensitive employee master fields.
- Low-risk validation hardening for emergency contact email and resignation/last-working-date ordering.
- Backward-compatible audit log fields aligned with project audit rules, using redacted before/after changed-field snapshots.

Phase 4 limitations:

- The explicit missing document report still shows document metadata rows manually marked `missing`; the separate required document matrix report provides inferred missing-document coverage.
- Safe CSV export intentionally excludes sensitive payroll, bank, residence card, passport, document storage, My Number-related, DOB, and address data.

## Phase 4B — Local Employee Document Upload

Status: implemented.

Goal: allow local employee document files to be uploaded after employee master data creation while preserving metadata-based management and query workflows.

Implemented scope:

- Employee creation redirects to the employee document edit/upload page.
- `/employees/<employee_id>/documents/edit` supports metadata editing and multiple local file uploads.
- Uploaded files are stored under `docs/empdoc/`.
- Stored filenames follow an internal-system-ID/date/sequence format such as `E001202606160001.pdf`, and are not renamed when editable employee numbers change.
- Employee records store relative file references in document metadata.
- Uploaded file metadata includes original filename, stored filename, content type, file size, upload timestamp, and uploader.
- File validation limits upload count, file size, request size, and allowed extensions.
- Files can be opened or downloaded only through authenticated employee/document routes with document management permission.
- `docs/empdoc/` is git-ignored because it contains sensitive local employee documents.

Phase 4B limitations:

- Document file access is authenticated and permission-gated, but encryption at rest, malware scanning, cloud storage, and retention workflow are not implemented yet.
- This is local MVP storage only.

## Phase 5 — Employee History and Change Traceability

Status: implemented.

Goal: preserve operational employee history for HR, visa, and dispatch compliance review without introducing external dependencies or a production database.

Implemented Step 1 through Step 5 scope:

1. **History data model** — employee records now include `employment_history`, `visa_history`, and `dispatch_assignment_history` arrays.
2. **Automatic history capture** — updates to employment, visa, and dispatch trigger fields append auto history snapshots with effective dates, event types, changed fields, previous values, actor, and timestamp.
3. **Manual history maintenance** — authorized users can add or edit history records independently from the current employee master sections.
4. **History attachments** — history records can carry local attachment metadata/files, using the same protected local document storage pattern under `docs/empdoc/`.
5. **Audit, i18n, and UI integration** — employee detail pages show history sections; history create/update actions are audit logged; English, Japanese, and Simplified Chinese labels are available.

Implemented routes:

- `/employees/<employee_id>/history/employment/new` and `/edit` for employment history.
- `/employees/<employee_id>/history/visa/new` and `/edit` for visa history.
- `/employees/<employee_id>/history/dispatch/new` and `/edit` for dispatch assignment history.
- `/employees/<employee_id>/history/<history_type>/<history_id>/attachments/<attachment_id>/open`.
- `/employees/<employee_id>/history/<history_type>/<history_id>/attachments/<attachment_id>/download`.

Phase 5 limitations:

- History records are local JSON records, not a temporal database or immutable event store.
- History attachment files are protected by application routes and permissions, but encryption at rest, malware scanning, retention workflows, and cloud storage are still later-phase decisions.
- Manual history record deletion is intentionally not implemented for auditability.

## Phase 6 — Integration Readiness

Goal: prepare employee master data for controlled integration with other TAC systems.

Implemented integration-ready foundations:

- EmployeeAdmin stores canonical organization references as `employment.entity_id`, `employment.department_id`, and `employment.team_id`.
- Employee create/edit screens use Master Data Entity → Department → Team cascading selectors when the Master Data service is available.
- Local authenticated proxy endpoints expose Master Data options to the EmployeeAdmin UI: `/api/masterdata/entities`, `/api/masterdata/departments`, and `/api/masterdata/teams`.
- The old free-text `employment.department` fallback field has been removed from forms, active employee records, list filters, reports, safe CSV export, and employment history records.
- Existing legacy department text is not auto-mapped to canonical organization IDs; operators should align records manually after Master Data is running.

Potential integrations:

- Payroll: employee payroll master fields.
- Timesheet: employee ID, employee number, entity ID, department ID, team ID, department display value derived from the canonical department ID, assignment, and manager.
- Expense: employee ID, department, bank/payment metadata if needed.
- Invoice: assignment/client/dispatch data.
- Training: skills, certifications, training eligibility.
- Dispatch compliance: client-site assignment and supervisor details.

## Phase 7 — Employee Onboarding Self-Service with Contract/NDA E-Signature

Status: Stage 1 core workflow, Stage 2 SMTP email delivery, Stage 3 browser hand-drawn electronic signature evidence capture, Stage 3.5 signed-PDF generation plus candidate email verification/manual email fallback, and Stage 3.6 HR email draft confirmation with default/extra CC handling are implemented. Encrypted My Number viewing and production/legal hardening remain later slices.

Planning document:

- `docs/Employee_Onboarding_Self_Service_Plan.md`

Goal: let HR create a secure onboarding request, send a link from the configured HR/admin mailbox, collect candidate/new-employee data and required documents, support browser-based electronic signature for HR-provided employment contract and NDA PDFs, and route the completed package to HR for review before Employee Master import.

Implemented Stage 1 scope:

- HR onboarding request creation.
- Configurable SMTP sender baseline, initially `HRadmin@tacjob.com`, using environment-provided SMTP host, port, username, password, sender, reply-to, HR notification email, and TLS settings.
- HR upload of manually confirmed employment contract, NDA, labor condition notice, and other case-specific PDFs.
- Secure token link for candidate access.
- Candidate electronic delivery/signature consent.
- Per-document signing mode: electronic signature required, electronic signature optional, manual sign/upload required, acknowledgement-only, or no signature required.
- Browser review/download of HR-provided documents.
- Browser signature pad for mouse/touch handwritten-on-screen signature, with consent checkbox, base64 PNG capture, server-side validation, immutable HTML evidence packet, SHA-256 evidence hash, audit log, and HR evidence open link.
- Signed PDF generation for PDF source documents using approved `pypdf` + `reportlab`: the original PDF is preserved and a signature certificate page is appended to a generated signed PDF.
- Manual download/sign/scan upload option for special documents, including labor condition notice when needed.
- Candidate onboarding data form based on EmployeeAdmin employee master, Japan HR, visa/residence, payroll/bank, emergency contact, and My Number needs; Dispatch Compliance/client assignment fields are intentionally excluded from candidate self-service and remain HR/internal operations data after review.
- Candidate required document upload plus optional `other` document upload, with a visible required-document checklist, already-uploaded candidate file table, selected-file preview, upload limits guidance, and submit-time checks for missing required documents/signatures while draft saves remain allowed.
- My Number entry with encryption, masked default display, HR/Admin-only step-up viewing, and access logging.
- Draft submission saved separately from official Employee Master data.
- Candidate invitation email, HR completion notification email, and return-to-candidate correction email through SMTP when configured; onboarding invitation email now has an HR review/confirmation step before sending, with default CC `hradmin@tacjob.com`, up to three HR-entered additional CC addresses, recipient snapshots, email draft status, and audit logs. When SMTP is not configured or sending fails, the app keeps a manual secure link fallback and records email status.
- HR manual email package fallback creates a fresh secure candidate link plus one-time verification code for manual delivery to the registered candidate email; plaintext link/code are shown only to authenticated HR and are not stored. Candidate token access is gated by email verification before form/document/signature access.
- HR review, return, approval, rejection, and import workflow.
- Signed document/evidence retention and audit logging.

Phase 7 constraints:

- Candidate submissions must not directly overwrite official Employee Master data.
- Employment contract and labor-condition electronic delivery/signature policy must be confirmed with Japan HR/labor/legal specialists before production reliance.
- My Number value collection is included only with encryption, masked default display, HR/Admin-only step-up viewing, strict audit logging, and retention/disposal controls.
- Labor condition notice is included, but manual download/sign/scan upload must remain available when HR chooses not to use electronic signature for that document.
- External certified e-signature provider integration is deferred until production/legal needs are confirmed.

## Labor Contract Renewal Tracking

Status: implemented as an Employee Master enhancement on 2026-06-23.

Goal: let HR directly enter labor contract start and end dates in EmployeeAdmin and track renewal risk without confusing labor contract validity with dispatch/client assignment periods.

Implemented scope:

- Employment Information now stores `employment.contract.start_date` and `employment.contract.end_date` as first-class HR fields.
- Employee create/edit and detail pages show the labor contract period separately from assignment/resignation fields.
- Japan HR can enter `2099-12-12` as the practical open-ended/permanent end date for 正社员; the UI displays that value as open-ended/permanent and excludes it from renewal alerts.
- Dashboard adds a labor contract renewal alert metric for finite contracts already due or within the 90-day window.
- `/reports/labor-contract-renewals` shows active/probation/on-leave employees with finite labor contract end dates due within the alert window.
- Employee CSV import template/field guide/sample and safe export include optional labor contract start/end date columns in English, Japanese, and Simplified Chinese.
- Employment history and audit continue to record changes because the contract fields are part of Employment Information.

Rollout order:

1. Direct HR input fields and employee detail display.
2. Renewal dashboard/report tracking.
3. CSV import/export support and field-guide documentation.
4. Future linkage to employment contract documents and onboarding import after HR/legal workflow confirmation.

Constraints:

- Labor contract dates are not dispatch assignment dates. Dispatch/client project periods remain under Dispatch Compliance.
- `2099-12-12` is an HR data-entry convention for open-ended/permanent tracking, not an ordinary renewal date.
- Automated renewal emails and separate approval workflows remain future scope.

## Out of Scope Until Approved

- Production database.
- Login and role-based access control.
- Live integration with sibling TAC projects.
- External HR/payroll APIs.
- Cloud document storage.
- Cloud/production document storage and unrestricted document file serving.
- OCR extraction for documents.
- Automated email reminders outside the approved onboarding workflow.
- My Number plaintext storage, broad export, ordinary report display, or access without HR/Admin step-up permission.
- External certified e-signature provider integration.

## Key Open Questions

1. Should document file upload be added after RBAC/storage/security policy is approved?
2. Should `/employees.json` be redacted once login/RBAC is introduced?
3. Should Phase 4 reporting include document expiry/missing document dashboard alerts?
4. Should Skills & Language Profile tags be normalized to managed master data lists later?

## Master Data System Parameters ownership update

Status: implemented on 2026-06-21.

System Parameters maintenance moved from EmployeeAdmin to `TACAI-Core/masterdata` on port `8007`. EmployeeAdmin no longer shows the System Parameters navigation item and no longer updates local System Parameters data. The old EmployeeAdmin GET URL redirects users to Master Data for continuity, while old POST maintenance endpoints are no longer active.

EmployeeAdmin onboarding email delivery now consumes `email.onboarding.smtp` through the Master Data internal API using `MASTERDATA_INTERNAL_API_TOKEN`. If Master Data is unavailable, onboarding email sending fails safely as not configured and HR can continue using the manual-link fallback.
