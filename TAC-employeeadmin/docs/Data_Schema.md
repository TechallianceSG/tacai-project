# TAC-employeeadmin Data Schema Draft

This document defines the local JSON schemas for the employee administration MVP. The schema is bilingual UI friendly: stored data uses stable keys/enums, while display labels come from i18n resources.

## Data Files

Current files:

- `database/employees.json` — employee master records.
- `database/audit_logs.json` — audit trail records.
- `i18n/en.json` — English UI labels.
- `i18n/ja.json` — Japanese UI labels.
- `i18n/zh.json` — Simplified Chinese UI labels.

Phase 7 onboarding self-service files:

- `database/employee_onboarding_requests.json` — HR-created onboarding requests and secure token metadata.
- `database/employee_onboarding_submissions.json` — candidate-submitted onboarding draft form data.
- `database/employee_onboarding_documents.json` — HR-provided, candidate-uploaded, manually signed/uploaded, and electronically signed onboarding document metadata.
- `database/employee_onboarding_signatures.json` — electronic signature consent/evidence records.
- `database/employee_onboarding_mynumber_access_logs.json` — step-up access logs for encrypted My Number viewing.

Phase 7 Stage 2/3 implementation notes:

- Onboarding requests store SMTP/email-review status fields such as `email_sender`, `email_status`, `email_draft_status`, `email_draft_prepared_by`, `email_draft_prepared_at`, `email_review_confirmed_by`, `email_review_confirmed_at`, `email_to`, `email_cc_default`, `email_cc_additional`, `email_sent_to_snapshot`, `email_sent_cc_snapshot`, `email_subject_snapshot`, `email_template_version`, `sent_at`, token hash, token expiry, and token timestamps. Raw candidate tokens are never persisted.
- SMTP configuration is read from Master Data System Parameters (`email.onboarding.smtp`) through the internal API on port `8007`; the SMTP password is resolved by the Master Data process from the configured environment variable or secret reference such as `ONBOARDING_SMTP_PASSWORD`.
- Browser electronic signatures are stored as signature evidence metadata in `employee_onboarding_signatures.json` plus an HTML evidence packet under `docs/onboarding/<request>/evidence/`.
- The evidence packet records signer name/email, timestamp, user agent, document IDs, original document hash, and the hand-drawn signature image. The evidence packet hash is stored as `document_sha256_after` / `sha256_signed` for the MVP.
- HR can open original onboarding documents and signature evidence through authenticated onboarding document routes; raw `docs/onboarding/` paths are not served directly.
- Employee Master import copies onboarding files and signature evidence packets into protected employee document storage under `docs/empdoc/`.
- Stage 3.5 adds `signed_pdf_stored_filename`, `signed_pdf_storage_reference`, `signed_pdf_content_type`, `signed_pdf_file_size_bytes`, `signed_pdf_created_at`, `signed_pdf_status`, and `sha256_signed_pdf` to onboarding document metadata. Existing `signed_*` fields remain the HTML evidence packet reference for backward compatibility.
- Stage 3.5 adds candidate email verification request fields including verification code hash, expiry, attempts, lockout, delivery status, verified timestamp, and verification session hash. Plaintext verification codes and plaintext candidate tokens are not persisted.
- Candidate self-service excludes Dispatch Compliance/client assignment fields from candidate input; those fields remain Employee Master/internal operations data for HR/dispatch teams after review. Candidate document readiness is computed from onboarding documents at runtime and is not stored as a separate score.

## Implemented Scope

Phase 1 implemented:

- `employee_id` — internal system ID.
- `employee_number` — editable employee number.
- `profile`.
- `employment`.
- `metadata`.

Phase 2 implemented:

- `payroll`.
- `visa`.
- `dispatch_compliance`.

Phase 3A implemented:

- `language_profile`.
- `skills_profile`.

Phase 3B implemented:

- `documents` metadata array.

Phase 4 implemented:

- Derived read-only reporting pages.
- Safe employee master CSV export.
- Data quality checks for duplicate employee numbers and company email addresses.
- Computed data completion and required document matrix reports.
- Backward-compatible audit log fields required by project audit rules.

Phase 5 implemented:

- `employment_history`.
- `visa_history`.
- `dispatch_assignment_history`.
- Local history attachment metadata/files.
- Auto history snapshots for employment, visa, and dispatch changes.

Integration-ready organization references implemented:

- `employment.entity_id`.
- `employment.department_id`.
- `employment.team_id`.

For the 2026-06-22 low-standard JP/CN/SG employee master entry flow, `employment.department` is reintroduced as a required plain-text tracking field for quick employee data preparation and CSV import. `employment.entity_id` is the required Master Data-controlled legal entity reference; `employment.department_id` and `employment.team_id` remain optional structured organization links.

## `database/employees.json`

Top-level format: JSON array of employee records.

```json
[
  {
    "employee_id": "EMP-0001",
    "employee_number": "TAC-2026-001",
    "profile": {},
    "employment": {},
    "payroll": {},
    "visa": {},
    "dispatch_compliance": {},
    "language_profile": {},
    "skills_profile": {},
    "documents": [],
    "employment_history": [],
    "visa_history": [],
    "dispatch_assignment_history": [],
    "metadata": {}
  }
]
```

## Employee Record Sections

### `employment`

```json
{
  "country_code": "JP",
  "legal_entity": "JP",
  "work_country": "JP",
  "business_line": "recruitment",
  "department": "Recruitment",
  "join_date": "YYYY-MM-DD",
  "employment_type": "employee",
  "entity_id": "ENT-0001",
  "department_id": "DEPT-0001 or blank",
  "team_id": "TEAM-0001 or blank",
  "position": "Consultant",
  "manager_employee_id": "TAC-2026-001",
  "office_location": "Tokyo",
  "assignment": "Internal HR",
  "status": "active",
  "probation_end_date": "YYYY-MM-DD or blank",
  "contract": {
    "start_date": "YYYY-MM-DD or blank",
    "end_date": "YYYY-MM-DD or blank; 2099-12-12 means open-ended/permanent for Japan HR tracking"
  },
  "resignation": {
    "resignation_date": "YYYY-MM-DD or blank",
    "last_working_date": "YYYY-MM-DD or blank",
    "reason": ""
  }
}
```

`country_code` and `work_country` use `JP`, `CN`, or `SG`. `business_line` uses `recruitment`, `rpo`, `haken`, `payroll`, `internal`, or `ai_platform`. `entity_id` is the required canonical legal entity reference from Master Data and represents 所属法人. CSV import accepts operator-facing `legal_entity_code` and resolves it to `employment.entity_id`. `department` remains the low-standard required text department used for quick JP/CN/SG entry and import tracking; `department_id` and `team_id` remain optional canonical organization references. UI list/detail/report/API/CSV display can resolve labels from Master Data IDs while keeping the low-standard text fields for import readiness.

`employment.contract.start_date` and `employment.contract.end_date` are first-class HR labor-contract tracking dates. They are independent from `dispatch_compliance.dispatch_start_date` and `dispatch_compliance.dispatch_end_date`, which track client/project dispatch assignments. Japan HR may enter `2099-12-12` as a practical open-ended/permanent end date for 正社员; the UI displays that value as open-ended/permanent and excludes it from labor contract renewal alerts.

Employee number uniqueness rule:

- `employee_id` is the system-stable internal ID and is globally unique.
- `employee_number` is the business employee number and must be unique only within the same `employment.entity_id` legal entity.
- Different legal entities may reuse the same employee number.
- Downstream modules should reference `employee_id` and keep `employee_number`/entity values as historical snapshots.

EmployeeAdmin exposes employee master records to platform modules through authenticated APIs:

- `/api/timesheet/employees` — compatibility payload for Timesheet and Payroll lookups.
- `/api/useradmin/employees` — user-account linking payload for User_admin; supports `entity_id` and `q` filters.

Expected Master Data objects use these fields:

- Entity: `entity_id`, `entity_code`, `entity_name_en`, `entity_name_ja`, `entity_name_zh`.
- Department: `department_id`, `entity_id`, `department_code`, `department_name_en`, `department_name_ja`, `department_name_zh`.
- Team: `team_id`, `department_id`, `team_code`, `team_name_en`, `team_name_ja`, `team_name_zh`.

EmployeeAdmin proxies Master Data options through authenticated local endpoints: `/api/masterdata/entities`, `/api/masterdata/departments?entity_id=<entity_id>`, and `/api/masterdata/teams?department_id=<department_id>`.

### `payroll`

```json
{
  "bank": {
    "bank_name": "",
    "branch_name": "",
    "swift_code": "",
    "account_type": "ordinary",
    "account_number": "",
    "account_holder": ""
  },
  "salary_type": "monthly",
  "payroll_currency": "SGD",
  "monthly_base_salary": "",
  "daily_wage": "",
  "hourly_wage": "",
  "salary_amount_yen": "",
  "transportation_allowance_yen": "",
  "bonus_eligible": false,
  "social_insurance_enrolled": false,
  "pension_enrolled": false,
  "employment_insurance_enrolled": false,
  "notes": ""
}
```

**Salary type → required wage field mapping (data completeness):**

| `salary_type` | Required field | Description |
|---------------|---------------|-------------|
| `monthly` | `payroll.monthly_base_salary` | Monthly base salary amount (non-negative integer) |
| `daily` | `payroll.daily_wage` | Daily wage amount (non-negative integer) |
| `hourly` | `payroll.hourly_wage` | Hourly wage amount (non-negative integer) |
| `annual` | (none) | Annual salary is self-contained |

If `salary_type` is `monthly`, `daily`, or `hourly`, the corresponding wage field is required for data completeness. The system validates that the required wage field is non-empty when the matching salary type is selected.

**Supported currencies for `payroll.payroll_currency`:**

| Code | Currency |
|------|----------|
| `SGD` | Singapore Dollar |
| `USD` | US Dollar |
| `CNY` | Chinese Yuan |
| `INR` | Indian Rupee |
| `TWD` | Taiwan Dollar |
| `JPY` | Japanese Yen |

`payroll.payroll_currency` is a dropdown selection. Values outside the supported list are rejected with a validation error.

**Money field validation:**

All payroll money fields (`monthly_base_salary`, `daily_wage`, `hourly_wage`, `salary_amount_yen`, `transportation_allowance_yen`) must be blank or a non-negative integer string. Floating-point values are not accepted.

`payroll.bank.swift_code` is an optional SWIFT/BIC code for overseas salary or reimbursement payments. It can be entered by the employee during onboarding self-service or completed later by HR in the payroll edit screen. It is intentionally not part of the required JP/CN/SG employee master import fields.

## 2026-06-22 JP/CN/SG Common Required Fields and CSV Import

The first-stage employee master entry standard now uses 12 required employee-master fields plus required basic payroll bank fields and one optional overseas-payment field. Manager employee number is optional and is not part of the CSV template. Department is Master Data controlled through `department_code` scoped under the selected `legal_entity_code`.

| CSV field | Internal path / behavior | Rule |
|---|---|---|
| `employee_id` | `employee_number` | Required business employee number. |
| `full_name` | `profile.name.display_name` | Required display/formal name. |
| `country_code` | `employment.country_code` | Required; `JP`, `CN`, or `SG`. |
| `legal_entity_code` | resolves Master Data `entity_code` to `employment.entity_id` | Required; must match Master Data Entity Code. |
| `employment_status` | `employment.status` | Required employment status enum. |
| `employment_type` | `employment.employment_type` | Required employment type enum. |
| `hire_date` | `employment.join_date` | Required `YYYY-MM-DD`. |
| `department_code` | resolves Master Data `department_code` to `employment.department_id` | Required; must exist under the selected Entity. |
| `work_email` | `profile.email` | Required unique company email. |
| `work_country` | `employment.work_country` | Required; `JP`, `CN`, or `SG`. |
| `business_line` | `employment.business_line` | Required business-line enum. |
| `profile_status` | `metadata.profile_status` | Required completion status enum. |
| `bank_name` | `payroll.bank.bank_name` | Required payroll bank name. |
| `bank_branch_name` | `payroll.bank.branch_name` | Required payroll bank branch name. |
| `bank_account_type` | `payroll.bank.account_type` | Required; `ordinary`, `current`, or `savings`. |
| `bank_account_number` | `payroll.bank.account_number` | Required; 1-20 digits. |
| `bank_account_holder` | `payroll.bank.account_holder` | Required account holder name. |
| `bank_swift_code` | `payroll.bank.swift_code` | Optional SWIFT/BIC code for overseas payments; may be blank and can be completed later by HR. |
| `labor_contract_start_date` | `employment.contract.start_date` | Optional labor contract start date in `YYYY-MM-DD`; separate from dispatch assignment dates. |
| `labor_contract_end_date` | `employment.contract.end_date` | Optional labor contract end date in `YYYY-MM-DD`; use `2099-12-12` for Japan 正社员/open-ended contracts. |

CSV template, field guide, and sample downloads support English, Japanese, and Simplified Chinese headers with `header_lang=en|ja|zh`, for example `/exports/employees-import-template.csv?header_lang=zh`. CSV import accepts any one complete supported header language. CSV import is all-or-nothing: any row/field error blocks the entire batch. A successful import writes a pre-import backup under `database/backups/` and records a metadata-only audit event. Backups may contain bank information after payroll-ready imports, so they must remain local and protected.

### `language_profile`

```json
{
  "japanese_level": "N2",
  "english_level": "business",
  "native_languages": ["Chinese"],
  "additional_languages": ["Japanese", "English"],
  "notes": ""
}
```

### `skills_profile`

```json
{
  "primary_skill": "Python",
  "secondary_skill": "AWS",
  "years_of_experience": "5",
  "it_skills": ["Python", "AWS", "AI"],
  "engineering_skills": ["Backend"],
  "certifications": ["AWS SAA"],
  "industry_experience": ["Finance"],
  "notes": ""
}
```

Tag-like fields are edited as comma-separated inputs and stored as JSON arrays.

### Local document upload storage

Uploaded employee files are stored under:

```text
docs/empdoc/
```

The folder is ignored by git and should be treated as sensitive local application data. Employee records store relative paths only, for example:

```text
docs/empdoc/E001202606160001.pdf
```

Stored filenames are generated by the app using the internal-system-ID/date/sequence format. They do not change when the editable employee number is updated:

```text
E001yyyymmdd0001.ext
```

`EMP-0001` is the internal system ID and maps to filename prefix `E001`; the final 4-digit sequence increments per internal employee record.

File access uses authenticated employee document routes based on internal `employee_id` and `document_id`:

```text
/employees/EMP-0001/documents/DOC-0001/open
/employees/EMP-0001/documents/DOC-0001/download
```

`storage_reference` remains metadata only. The app does not serve raw `docs/empdoc/` paths directly; file access requires document management permission and safe path validation under `docs/empdoc/`.

### `documents`

Phase 3B started as metadata-only document management. Phase 4B adds local file upload while keeping metadata as the query/control layer.

```json
[
  {
    "document_id": "DOC-0001",
    "document_type": "employment_contract",
    "title": "Employment Contract",
    "issuer": "TAC",
    "document_date": "YYYY-MM-DD or blank",
    "expiry_date": "YYYY-MM-DD or blank",
    "received_date": "YYYY-MM-DD or blank",
    "storage_reference": "docs/empdoc/E001202606160001.pdf",
    "status": "on_file",
    "notes": "",
    "original_filename": "Employment Contract.pdf",
    "stored_filename": "E001202606160001.pdf",
    "content_type": "application/pdf",
    "file_size_bytes": "238421",
    "uploaded_at": "2026-06-16T00:00:00+00:00",
    "uploaded_by": "Admin"
  }
]
```

### Employee history arrays

Phase 5 adds local history arrays for operational traceability:

- `employment_history` — employment status, canonical entity/department/team IDs, position, manager, assignment, probation, and resignation history.
- `visa_history` — visa, residence status, passport, expiry, and renewal reminder history.
- `dispatch_assignment_history` — client assignment, dispatch dates, work description, contract type, and supervisor history.

Each history record uses a stable `history_id`, an `event_type`, `effective_date`, `changed_at`, `changed_by`, `source`, `changed_fields`, `previous_values`, `notes`, and optional `attachments`. Automatic records use `source: "auto"`; manually created/edited records use `source: "manual"`; migration/bootstrap records may use `source: "migration"`.

### Timesheet dispatch assignment API

EmployeeAdmin exposes a safe authenticated Timesheet integration endpoint:

```text
/api/timesheet/dispatch-assignment?employee_id=<employee_id>&work_date=<YYYY-MM-DD>
/api/timesheet/dispatch-assignment?employee_no=<employee_no>&entity_id=<entity_id>&work_date=<YYYY-MM-DD>
```

The endpoint returns only a safe dispatch-assignment allowlist for the requested employee/date. It does not expose payroll, visa identity, document, or personal sensitive sections.

Matching rules:

1. Prefer the immutable `employee_id` when supplied; otherwise match visible employees by operator-facing `employee_number`, optionally scoped by `entity_id`.
2. If `employee_no` is ambiguous across legal entities and no `entity_id` is supplied, return `409` and require `employee_id` or `entity_id`.
3. Prefer `dispatch_assignment_history` records where `work_date` falls between `dispatch_start_date` and `dispatch_end_date`.
4. Blank `dispatch_end_date` is treated as open-ended.
5. If multiple history rows match, the latest `dispatch_start_date` and then latest change metadata wins.
6. If no history row matches, fallback to current `dispatch_compliance` using the same date-window rule.
7. If no assignment matches, return `assignment.matched: false` so Timesheet can save a blank project/customer row for HR/Admin follow-up.

Safe assignment response fields include `client_name`, optional `project_name`, `assignment_location`, dispatch start/end dates, `contract_type`, `work_description`, and supervisor contact fields.

Example employment history record:

```json
{
  "history_id": "EMPLOYMENT-HIST-0001",
  "event_type": "department_change",
  "effective_date": "2026-06-18",
  "changed_at": "2026-06-18T00:00:00+00:00",
  "changed_by": "Admin",
  "source": "auto",
  "changed_fields": ["employment.department_id"],
  "previous_values": {"employment.department_id": "DEP-0000"},
  "join_date": "2026-04-01",
  "employment_type": "employee",
  "entity_id": "ENT-0001",
  "department_id": "DEPT-0001",
  "team_id": "TEAM-0001",
  "position": "Consultant",
  "manager_employee_id": "TAC-2026-001",
  "office_location": "Tokyo",
  "assignment": "Internal HR",
  "status": "active",
  "probation_end_date": "2026-09-30",
  "resignation": {
    "resignation_date": "",
    "last_working_date": "",
    "reason": ""
  },
  "notes": "",
  "attachments": []
}
```

History attachment metadata reuses the document metadata shape with `attachment_id` instead of `document_id`. Stored files remain under `docs/empdoc/` and are opened/downloaded only through authenticated history attachment routes.

## Planned Phase 7 Onboarding Self-Service Schemas

Detailed workflow planning is maintained in `docs/Employee_Onboarding_Self_Service_Plan.md`.

Planned onboarding request records should remain separate from official employee master records until HR approval/import.

### `database/employee_onboarding_requests.json`

Top-level format: JSON array.

Core fields:

- `onboarding_request_id` — stable request ID, e.g. `ONB-0001`.
- `candidate_name`.
- `candidate_email`.
- `planned_start_date`.
- `employment_type`.
- `status` — `draft`, `ready_to_send`, `sent`, `opened`, `consent_confirmed`, `in_progress`, `submitted`, `pending_hr_review`, `returned_to_candidate`, `resubmitted`, `approved`, `imported_to_employee_master`, `rejected`, `expired`, or `cancelled`.
- `token_hash` — hash only; raw token must not be stored.
- `token_expiry`.
- `created_by`, `created_at`, `sent_at`.

Recommended `onboarding_category` values:

- `regular_employee`
- `dispatch_employee`
- `contractor`
- `foreign_employee`
- `other`

For `employment_type = dispatch` or `onboarding_category = dispatch_employee`, the HR readiness checklist should confirm these HR-to-candidate documents before sending the employee self-service link:

- `employment_contract`
- `nda`
- `labor_condition_notice`
- `dispatch_condition_notice`

Public self-service URL configuration is environment/deployment state, not JSON business data. Use `EMPLOYEE_ADMIN_PUBLIC_BASE_URL` and `TACAI_ALLOWED_PUBLIC_HOSTS` for temporary HTTPS tunnel or production HTTPS domains.

### `database/employee_onboarding_submissions.json`

Core fields:

- `submission_id`.
- `onboarding_request_id`.
- `status`.
- `form_data` — candidate-provided draft profile/employment/visa/bank/emergency-contact information.
- `submitted_at`.
- `reviewed_by`, `reviewed_at`, `review_notes` when HR reviews.

### `database/employee_onboarding_documents.json`

Core fields:

- `document_id`.
- `onboarding_request_id`.
- `document_type` — `employment_contract`, `nda`, `labor_condition_notice`, `personal_information_consent`, `dispatch_condition_notice`, `residence_card`, `passport`, `bank_proof`, `address_proof`, `resume`, `other_signed_document`, `other_identity_document`, `other_bank_or_payroll_document`, `other_hr_requested_file`, or `other`.
- `direction` — `hr_to_candidate`, `candidate_to_hr`, `manual_signed_upload`, or `system_generated_signed`.
- `signing_mode` — `electronic_signature_required`, `electronic_signature_optional`, `manual_sign_upload_required`, `acknowledgement_only`, or `no_signature_required`.
- `status`.
- `original_filename`.
- `stored_filename`.
- `signed_stored_filename`, when applicable.
- `content_type`.
- `file_size_bytes`.
- `sha256_original`.
- `sha256_signed`, when applicable.
- `uploaded_by`, `uploaded_at`.

### `database/employee_onboarding_signatures.json`

Core fields:

- `signature_id`.
- `onboarding_request_id`.
- `document_id`.
- `signer_name`.
- `signer_email`.
- `signature_method` — `drawn_signature_pad`, `manual_signed_upload`, `typed_name_acknowledgement`, or later `external_provider`.
- `consent_text_version`.
- `signed_at`.
- `ip_address` and `user_agent`, handled according to privacy policy.
- `document_sha256_before`.
- `document_sha256_after`.
- `evidence_status`.

### My Number fields inside onboarding submissions

My Number may be entered by the candidate only if the encrypted-storage and restricted-view controls are implemented.

Recommended structure inside `form_data`:

```json
{
  "my_number": {
    "encrypted_value": "...",
    "encryption_key_id": "KEY-0001",
    "last4": "1234",
    "collection_status": "submitted_encrypted",
    "collected_at": "2026-06-21T12:00:00+09:00",
    "verified_by": "USR-0001",
    "verified_at": "2026-06-22T09:00:00+09:00"
  }
}
```

Rules:

- Never store plaintext My Number in JSON, audit logs, debug logs, CSV, reports, or email.
- Display only masked value by default.
- Decrypt/view only for authorized HR/Admin users after a separate step-up password or credential challenge.
- Every decrypt/view attempt must be logged.
- Delete/dispose when Individual Number processing is no longer required and applicable statutory retention has passed.

### `database/employee_onboarding_mynumber_access_logs.json`

Core fields:

- `access_log_id`.
- `employee_id`, if already imported.
- `onboarding_request_id`.
- `action` — `my_number_view_requested`, `my_number_view_step_up_failed`, `my_number_viewed`, or `my_number_deleted_after_retention`.
- `requested_by`.
- `role_at_access`.
- `step_up_result`.
- `reason`.
- `accessed_at`.

### Planned onboarding file storage

Local MVP onboarding files should use a separate git-ignored sensitive folder:

```text
docs/onboarding/
```

Recommended layout:

```text
docs/onboarding/ONB-0001/hr/
docs/onboarding/ONB-0001/candidate/
docs/onboarding/ONB-0001/signed/
docs/onboarding/ONB-0001/evidence/
```

Files must not be served directly by raw path. HR access must require User_admin authentication and appropriate EmployeeAdmin permission; candidate access must require a valid token scoped to the onboarding request.

## Required Fields

The local app requires these Phase 1 fields for employee create/edit:

- `employee_number`.
- `profile.name.display_name`.
- `profile.email`.
- `employment.join_date`.
- `employment.employment_type`.
- `employment.department_id`.
- `employment.status`.

Department is satisfied only by canonical Master Data `employment.department_id`; the old free-text `employment.department` fallback is no longer accepted. `profile.email` is the required company email. `profile.email_p` is an optional personal email; when provided, it is validated as an email address, shown in detail/search, redacted in audit snapshots, and excluded from safe CSV by default.

Phase 2/3 fields are optional unless validation applies to a provided value.

## Employee Identifier Rules

`employee_id` is the internal system ID. It is generated server-side, immutable, not user-editable, used for routes/audit/document/history references, and not reused.

Internal ID format:

```text
EMP-0001
EMP-0002
```

`employee_number` is the business employee number. It is manually entered, required, editable by authorized users, unique among visible employee records, searchable, and shown/exported as the primary operator-facing employee identifier.

## Enum Keys

### Japanese level

- blank
- `native`
- `N1`
- `N2`
- `N3`
- `N4`
- `N5`
- `none`

### English level

- blank
- `native`
- `business`
- `fluent`
- `intermediate`
- `basic`
- `none`

### Document type

- blank
- `employment_contract`
- `nda`
- `residence_card`
- `passport`
- `my_number_related`
- `offer_letter`
- `certificate`
- `other`

### Document status

- blank
- `on_file`
- `missing`
- `expired`
- `pending_renewal`
- `not_required`

Other implemented enums include employment status/type, gender, salary type, bank account type, and dispatch contract type.

## Money Handling

- All payroll money fields (`payroll.monthly_base_salary`, `payroll.daily_wage`, `payroll.hourly_wage`, `payroll.salary_amount_yen`, `payroll.transportation_allowance_yen`) are stored as blank or non-negative integer strings.
- Each money field represents the amount in the currency specified by `payroll.payroll_currency`.
- Do not use floating point values for salary, allowance, or bonus amounts.

## Audit Logs

Implemented audit actions:

- `employee_created`
- `employee_updated`
- `employee_status_changed`
- `payroll_updated`
- `visa_updated`
- `dispatch_updated`
- `skills_language_updated`
- `documents_updated`
- `employment_history_created`
- `employment_history_updated`
- `visa_history_created`
- `visa_history_updated`
- `dispatch_history_created`
- `dispatch_history_updated`

Automatic history snapshots appended during current-section updates are included in the parent employee/visa/dispatch audit entry. Manual history create/update routes use the history-specific audit actions above.

Audit actor before login/roles exist:

```text
Admin
```

New Phase 4 audit records preserve existing fields and also include the project-required audit fields:

- `module`.
- `record_id`.
- `action`.
- `user`.
- `timestamp`.
- `before_value`.
- `after_value`.

`before_value` and `after_value` store changed-field snapshots only. Sensitive payroll, bank, visa identity, document storage, document notes, My Number-related, address, DOB, emergency contact, and personal email (`profile.email_p`) paths are redacted instead of copied into the audit log.

## Phase 4 Reports and Safe CSV Export

Phase 4 reports are derived read-only views from `database/employees.json`:

- `/reports/missing-required-data` — missing Phase 1 required fields.
- `/reports/visa-expiry` — foreign employee visa expiry alerts within 90 days or already due.
- `/reports/probation-ending` — active/probation employee probation dates within 30 days or already due.
- `/reports/labor-contract-renewals` — active/probation/on-leave employees with finite labor contract end dates within 90 days or already due; open-ended `2099-12-12` contracts are excluded.
- `/reports/dispatch-assignments` — dispatch employees and client assignment metadata.
- `/reports/document-expiry` — document metadata expiry within 90 days or already due.
- `/reports/missing-documents` — document metadata rows explicitly marked `missing`.
- `/reports/data-quality` — duplicate employee number and duplicate company email checks.

Safe CSV export route:

```text
/exports/employees.csv
```

Safe CSV columns:

- `employee_number`.
- `display_name`.
- `email` — company email.
- `phone`.
- `entity_id`.
- `entity_label`.
- `department_id`.
- `department_label`.
- `team_id`.
- `team_label`.
- `position`.
- `manager_employee_id`.
- `office_location`.
- `assignment`.
- `employment_type`.
- `status`.
- `join_date`.
- `probation_end_date`.
- `labor_contract_start_date`.
- `labor_contract_end_date`.
- `nationality`.
- `japanese_level`.
- `english_level`.
- `primary_skill`.
- `secondary_skill`.

Excluded from reports/CSV list views: salary, bank account, residence card number, passport number, personal email, document storage reference, document notes, My Number-related data, date of birth, and address.

## Computed Completion and Required Documents

Employee data completion is computed at runtime and is not stored in `database/employees.json`. It starts from the Phase 1 required fields and adds context-sensitive reporting checks for foreign employees and dispatch employees. These checks are visibility/reporting helpers only and do not change create/edit validation rules.

The required document matrix is also computed at runtime:

- Base required documents: employment contract, NDA, and offer letter.
- Active or probation employees: My Number related document metadata is expected.
- Foreign employees: residence card and passport document metadata are expected.

A required document is treated as complete when a matching document type has status `on_file` or `not_required`. The legacy missing document report still shows explicit document metadata rows marked `missing`; `/reports/required-document-matrix` shows inferred requirements.

## I18n Resources

Current files:

- `i18n/en.json`
- `i18n/ja.json`
- `i18n/zh.json`

Rules:

- The app chooses language using `?lang=en`, `?lang=ja`, or `?lang=zh`.
- Invalid or missing language falls back to English.
- Stored enum values remain stable keys.
- UI labels, navigation, buttons, statuses, validation messages, dashboard labels, field labels, document labels, skill/language labels, and audit action labels come from i18n resources.

## Sensitive Data Notes

Sensitive fields include:

- Date of birth.
- Address.
- Bank account data.
- Salary amount.
- Residence card number.
- Passport number.
- My Number related document metadata/files.
- Uploaded identity documents.
- Personal email (`profile.email_p`).

For MVP, keep data local under this project. Employee list views, Phase 4 reports, and the safe CSV export intentionally avoid exposing payroll, bank, residence card, passport, personal email, document storage, My Number-related, DOB, and address fields. Document and history attachment file content is stored locally under `docs/empdoc/` and is not opened or downloaded by default. The local `/employees.json` endpoint still contains complete local records, including history arrays and local file references, and should be treated as a local diagnostic/export endpoint only. Before production use, add access control, encryption/storage policy, backup policy, retention rules, and malware scanning.

## Master Data System Parameters integration

EmployeeAdmin no longer owns `database/system_parameters.json` as an active configuration store. Onboarding email delivery calls Master Data:

```text
GET /api/master-data/system-parameters/outbound-email-onboarding
Header: X-TACAI-Internal-Token: <MASTERDATA_INTERNAL_API_TOKEN>
```

The response is normalized into the existing onboarding email runtime shape used by `smtp_configured()` and `send_onboarding_email()`. If Master Data is unavailable or the token/password is missing, EmployeeAdmin fails safely as SMTP not configured and keeps the manual-link fallback behavior.
