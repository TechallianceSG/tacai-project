# Employee Onboarding Self-Service Plan

## 1. Purpose

Implementation status: Stage 1 core workflow, Stage 2 SMTP email delivery, Stage 3 browser hand-drawn electronic signature evidence capture, and Stage 3.5 signed-PDF generation plus candidate email verification/manual email fallback have been implemented. Encrypted My Number viewing, production legal review, and production storage hardening remain later slices.

This document defines the planned EmployeeAdmin onboarding self-service workflow for TAC HR operations.

The goal is to let HR send a secure onboarding link to a candidate / new employee, collect employee master information and required documents, support electronic or manual signing for HR-provided documents, and route the submitted onboarding package to HR for review before creating or updating the official Employee Master record.

This is a planning document, not legal advice. Employment contract, labor condition notice, NDA, personal information, My Number, and dispatch-related document handling should be reviewed by a Japan HR/labor specialist, social insurance labor consultant, tax advisor, or legal advisor before production use.

## 2. Confirmed Direction

### 2.1 Mail Sender

Near-term sender:

```text
HRadmin@tacjob.com
```

Recommended display name:

```text
TAC HR Admin
```

Recommended future migration target after TAC Tokyo Mail matures:

```text
HRadmin@tactokyo.com
onboarding@tactokyo.com
```

Implementation rule:

- Do not hard-code the sender in application logic.
- Read SMTP host, port, username, password, sender, reply-to, and TLS settings from configuration.
- Use an app-specific SMTP password if the mail provider supports it.
- Do not use `info@tacjob.com` for onboarding system mail.
- Keep the mail template generic; sensitive personal data and signed files should remain inside EmployeeAdmin, not inside the email body.

### 2.2 Onboarding Scope

The first planned onboarding workflow covers:

- Candidate/new employee basic information entry.
- Candidate/new employee work eligibility, visa/residence, payroll/bank, emergency contact, and dispatch-related intake fields.
- My Number entry with encryption and step-up access control.
- Upload of required onboarding documents.
- Employee-added optional additional documents.
- HR-uploaded employment contract, NDA, labor condition notice, and other required signing/acknowledgement documents.
- HR-controlled signing mode per document.
- Candidate electronic signature by hand-drawn mouse/touch signature where permitted.
- Candidate manual download/sign/scan upload option for special documents.
- Submission saved as an onboarding draft package.
- HR notification after candidate completion.
- HR review, return, approval, and import into Employee Master.
- Audit log for all state changes, document actions, My Number access, and signature events.

### 2.3 Key Principle

Candidate-submitted data must not directly overwrite official Employee Master data.

All candidate submissions become a draft / pending HR review package first. HR must approve before the official Employee Master record is created or updated.

## 3. Recommended Workflow

```text
1. HR creates an onboarding request in EmployeeAdmin.
2. HR enters candidate name, email, planned start date, employment type, and HR notes.
3. HR selects onboarding category: regular employee, dispatched/haken employee, contractor/other, or foreign employee path.
4. HR uploads manually confirmed documents, such as employment contract, NDA, labor condition notice, and other files.
5. HR selects a signing mode for each document.
6. System generates a secure one-time onboarding link.
7. System sends the link from TAC HR Admin <HRadmin@tacjob.com>.
8. Candidate opens the link and confirms identity and electronic delivery/signature consent.
9. Candidate reviews HR-provided documents in the browser.
10. Candidate signs eligible documents electronically with a hand-drawn signature pad, or downloads/signs/scans/uploads documents when manual signing is selected.
11. Candidate fills personal, employment, residence/visa, bank, emergency contact, My Number, and dispatch-related fields as required.
12. Candidate uploads required documents.
13. Candidate can add optional additional files, including an `other` document category for special cases.
14. Candidate submits the onboarding package.
15. System stores submission as pending HR review.
16. System emails HR a completion notification.
17. HR reviews data, files, signatures, My Number masked status, and evidence records.
18. HR approves, returns for correction, rejects, or cancels.
19. Approved package is imported into Employee Master.
20. Signed files and submitted attachments are retained as protected employee documents.
21. Audit logs are written for every important action.
```

## 4. Document Signing Model

### 4.1 HR-Controlled Signing Mode Per Document

Every HR-provided document should have a configurable signing mode.

Recommended signing modes:

```text
electronic_signature_required
electronic_signature_optional
manual_sign_upload_required
acknowledgement_only
no_signature_required
```

Meaning:

- `electronic_signature_required` — candidate must sign in the browser using mouse/touch hand-drawn signature.
- `electronic_signature_optional` — candidate can sign electronically or choose manual download/sign/scan upload.
- `manual_sign_upload_required` — candidate must download, sign manually, scan/photo, and upload the signed file.
- `acknowledgement_only` — candidate confirms receipt/understanding without a signature image.
- `no_signature_required` — document is for reference/download only.

This allows TAC to handle ordinary documents electronically while preserving manual signing for special documents or cases where HR/legal prefers wet signature or scan upload.

### 4.2 Document Types and Recommended Default Signing Modes

| Document | Include in onboarding? | Recommended MVP signing mode | Notes |
|---|---:|---|---|
| Employment contract / 雇用契約書 | Yes | `electronic_signature_optional` | HR uploads case-specific template; electronic signing is preferred when confirmed acceptable, manual upload remains available. |
| NDA / 秘密保持契約 | Yes | `electronic_signature_required` | Good first e-signature pilot document. |
| Labor condition notice / 労働条件通知書 | Yes | `electronic_signature_optional` or `manual_sign_upload_required` | Candidate must be able to download/save/print; manual signing/upload must be allowed. |
| Personal information handling consent | Recommended | `electronic_signature_required` or `acknowledgement_only` | Useful for privacy and document handling notice. |
| Company rule acknowledgement | Optional | `acknowledgement_only` | Later phase. |
| Dispatch/haken condition document | Optional / case-based | `electronic_signature_optional` or `manual_sign_upload_required` | Confirm detailed haken requirements before production reliance. |
| Other HR document | Optional | HR selects mode | Candidate can also upload under `other`. |

### 4.2.1 Tokyo dispatch pilot package

For the first three Tokyo dispatch onboarding tests, use TEST ONLY documents and a temporary HTTPS tunnel before sending links to real employees.

Minimum HR-provided package for each dispatch onboarding request:

1. Employment contract / 雇用契約書 — `electronic_signature_optional` for pilot safety.
2. NDA / 秘密保持契約 — `electronic_signature_required` as the primary e-signature pilot document.
3. Labor condition notice / 労働条件通知書 — `electronic_signature_optional` or `manual_sign_upload_required`; the candidate must be able to download/save/print it.
4. Dispatch/haken condition document — `manual_sign_upload_required` for the first pilot unless HR/legal confirms electronic-only handling.
5. Personal information handling consent — `electronic_signature_required` or `acknowledgement_only`.

Pilot scenarios:

- Test 1: mostly electronic signing, NDA required, contract optional e-sign.
- Test 2: manual signed upload required for labor and dispatch-condition documents.
- Test 3: mobile-first completion using phone touch signature and photo/PDF upload.

Before production reliance, Japan HR/legal/social-insurance-labor-consultant review must confirm that the final employment contract, labor-condition notice, and dispatch/haken documents may be electronically delivered/signed for the intended worker type and that the employee can retain downloadable copies.

### 4.3 Candidate-Added Files

The candidate upload page should include both required checklist slots and an additional-file area.

Required checklist examples:

- Residence card front/back.
- Passport, if applicable.
- Bank account proof.
- Address proof, if required.
- Signed manual document upload, when required.

Additional optional upload categories:

```text
other_signed_document
other_identity_document
other_bank_or_payroll_document
other_hr_requested_file
other
```

Candidate-facing instruction:

```text
If HR asked you to submit a document that is not listed above, please choose “Other” and upload it here with a short note.
```

## 5. Electronic Signature Planning

### 5.1 Recommended Signature Method

MVP method:

- Candidate views the PDF online.
- Candidate confirms electronic delivery/signature consent.
- Candidate signs with a hand-drawn signature pad using mouse, trackpad, or mobile touch screen.
- System records consent, signer name, email, timestamp, IP address, user agent, token ID, document ID, and document hash.
- System generates a signed evidence packet and, for PDF source documents, a generated signed PDF with an appended signature certificate page using approved `pypdf` + `reportlab`.
- HR verifies the signed document during review.

Typed-name acknowledgement can be used only as a fallback for low-risk acknowledgements, not as the primary method for employment contract/NDA signing.

### 5.2 Compliance Position for Japan

General direction:

- NDAs are usually suitable for electronic signing if both parties accept the method and the signature evidence is retained.
- Employment contract and labor-condition documents may be handled electronically in Japan when legal requirements are met, including employee consent and the ability for the employee to save/print the document.
- Labor condition notice / employment-condition delivery should include explicit electronic delivery consent and provide downloadable copies.
- For dispatch/Haken-related documents, confirm detailed requirements with a Japan HR/labor specialist before relying exclusively on electronic delivery.

Required compliance safeguards:

- Show an explicit consent checkbox before electronic signing.
- Require a hand-drawn signature for `electronic_signature_required` documents.
- Allow the candidate to download/save the document after signing.
- Preserve original PDF, signed PDF, signature evidence, and audit log.
- Keep document hashes to detect tampering.
- Keep HR review and final acceptance as separate steps.
- Always allow HR to select manual download/sign/scan upload for special documents.

### 5.3 Electronic Signature Consent Text Draft

English concept:

```text
I agree to receive and sign the onboarding documents electronically. I understand that I can download and save/print copies of the documents for my records. I confirm that the signature I draw on this page is my own signature and that I intend to sign the selected document electronically.
```

Japanese concept:

```text
私は、入社関連書類を電子的に受領し、電子署名することに同意します。署名後の書類をダウンロード・保存・印刷できることを確認しました。本画面で手書き入力する署名が私本人の署名であり、対象書類に電子的に署名する意思があることを確認します。
```

Chinese concept:

```text
我同意以电子方式接收并签署入职相关文件，并确认可以下载、保存或打印签署后的文件作为留存。我确认本页面手写输入的签名为本人签名，并确认本人有意以电子方式签署所选文件。
```

## 6. MVP Functional Scope

### 6.1 HR Side

HR can:

- Create onboarding request.
- Enter candidate name, email, planned start date, employment type, onboarding category, and notes.
- Upload case-specific employment contract PDF.
- Upload case-specific NDA PDF.
- Upload labor condition notice PDF.
- Upload other required HR documents.
- Select signing mode per document.
- Select required document checklist.
- Generate secure candidate link.
- Review the generated onboarding invitation email draft before sending.
- Keep default CC `hradmin@tacjob.com`, optionally enter up to three additional CC email addresses, confirm the recipient/CC/body/link expiry, and then send.
- Send onboarding invitation email through configured SMTP using `HRadmin@tacjob.com` by default; if SMTP is missing or fails, record the status and show HR the secure link for manual sending.
- View request status.
- View candidate-submitted data.
- View/download submitted attachments.
- View electronic signature evidence.
- View masked My Number status; decrypt only through step-up permission flow.
- Approve submission.
- Return submission for correction.
- Reject/cancel request.
- Import approved submission into Employee Master.

### 6.2 Candidate Side

Candidate can:

- Open secure onboarding link.
- Confirm identity and electronic delivery/signature consent.
- View/download HR-provided documents.
- Sign eligible documents through browser signature pad.
- For manual-sign documents, download/sign/scan or photo/upload the signed file.
- Fill onboarding information.
- Enter My Number when requested.
- Upload required documents.
- Add optional additional files using an `other` category.
- Save draft if allowed by token policy.
- Submit final package.
- See completion confirmation.
- Download signed documents if enabled.

### 6.3 System Side

System should:

- Generate secure tokens.
- Store only token hashes.
- Enforce token expiry.
- Store request/submission statuses.
- Validate file type and file size.
- Store original, manually uploaded, and signed document versions.
- Hash documents before and after signing.
- Generate signature evidence records.
- Encrypt My Number values before persistence.
- Mask My Number by default in all HR screens.
- Require HR/Admin permission plus separate step-up password to decrypt/view My Number.
- Write My Number view audit logs.
- Send candidate onboarding email.
- Send HR completion notification.
- Write audit logs.
- Keep submitted packages separate from Employee Master until HR approval.

## 7. Candidate Onboarding Form Fields

The onboarding form should be based on EmployeeAdmin employee master data and Japan HR/dispatch operations.

### 7.1 Basic Profile

Maps mainly to `profile`:

- Full legal name.
- Display name.
- Name in kana.
- English name, if applicable.
- Date of birth.
- Gender, if collected.
- Nationality.
- Personal email.
- Phone number.
- Current residential address.
- Emergency contact name.
- Emergency contact relationship.
- Emergency contact phone.
- Emergency contact email.

### 7.2 Employment Intake

Maps mainly to `employment`, with HR confirmation before import:

- Planned start date.
- Employment type: regular employee, contract employee, dispatch/haken employee, part-time, contractor/other.
- Position/title.
- Work location / office location.
- Entity / department / team: normally selected or confirmed by HR.
- Manager/supervisor: normally selected or confirmed by HR.
- Probation period applicability and expected end date.
- Assignment note.
- Work schedule category, if used by HR.

### 7.3 Dispatch / Haken Information

Maps mainly to `dispatch_compliance` and dispatch history where applicable:

- Dispatch employee flag.
- Client company / dispatch destination.
- Assignment location.
- Dispatch start date.
- Dispatch end date, if known.
- Job description / work content.
- Commanding supervisor at client site.
- Client supervisor contact.
- Complaint/contact window, if required by HR.
- Contract type / dispatch category.
- Working condition document status.

Many of these fields may be HR-only or HR-confirmed fields rather than candidate-editable fields.

### 7.4 Visa / Residence Information

Maps mainly to `visa`:

- Foreign employee flag.
- Residence status.
- Residence card number, if collected.
- Residence card expiry date.
- Permission to work status.
- Passport number, if collected.
- Passport expiry date.
- Visa/residence notes.
- Residence card front/back upload.
- Passport upload, if required.

### 7.5 Payroll / Bank Information

Maps mainly to `payroll` and sensitive payroll fields:

- Bank name.
- Branch name.
- Branch code, if used.
- Account type.
- Account number.
- Account holder name.
- Bankbook/card image upload, if required.
- Commuting allowance information, if collected at onboarding.
- Dependent/family support status, if used by HR/payroll.

Sensitive handling:

- Treat bank data as sensitive.
- Do not include bank data in broad exports.
- Redact bank data in audit snapshots.

### 7.6 My Number Handling

Confirmed direction:

- Employee may enter My Number in the onboarding form.
- The value must be encrypted before storage.
- The value must be masked by default in every UI.
- Only authorized HR/Admin users may request decryption/viewing.
- Viewing requires a separate step-up password or credential challenge governed by User_admin / user management policy.
- Every view/decrypt attempt must be audit logged, including success/failure.
- My Number must not appear in general CSV exports, list views, reports, email bodies, audit snapshots, or logs.
- When the Individual Number-related purpose is no longer needed and the legal retention period has passed, My Number must be deleted/disposed of promptly.

Recommended storage fields:

```json
{
  "my_number": {
    "encrypted_value": "...",
    "encryption_key_id": "KEY-0001",
    "last4": "1234",
    "collection_status": "submitted",
    "collected_at": "2026-06-21T12:00:00+09:00",
    "verified_by": "USR-0001",
    "verified_at": "2026-06-22T09:00:00+09:00"
  }
}
```

Do not store plaintext My Number in JSON, audit logs, or temporary debug files.

## 8. Document Checklist

### 8.1 HR-Provided Documents

- Employment contract / 雇用契約書.
- NDA / 秘密保持契約.
- Labor condition notice / 労働条件通知書.
- Personal information handling consent.
- Company rule acknowledgement, optional.
- Dispatch/haken condition document, if applicable.
- Other HR-provided case-specific document.

HR uploads templates manually in MVP because content may differ by employee, employment type, dispatch destination, role, compensation, and contract terms.

### 8.2 Candidate-Uploaded Documents

- Residence card front/back, if applicable.
- Passport, if applicable.
- Bank account proof.
- Address proof, if required.
- Resume/CV, if required.
- Signed manually downloaded labor condition notice, if manual signing is selected.
- Signed manually downloaded employment contract/NDA, if manual signing is selected.
- Other HR-requested documents.
- Candidate-added `other` files.

If browser e-signature is used for a document, candidate-uploaded signed versions may be replaced by system-generated signed PDFs and signature evidence records.

## 9. Status Model

### 9.1 Onboarding Request Status

```text
draft
ready_to_send
sent
opened
consent_confirmed
in_progress
submitted
pending_hr_review
returned_to_candidate
resubmitted
approved
imported_to_employee_master
rejected
expired
cancelled
```

### 9.2 Document Status

```text
uploaded_by_hr
available_for_candidate
viewed_by_candidate
downloaded_by_candidate
manual_signature_requested
manual_signed_upload_received
signed_by_candidate
submitted_by_candidate
pending_hr_review
accepted
rejected
needs_resubmission
archived_to_employee_master
```

### 9.3 Signature Status

```text
not_required
pending
consent_confirmed
signature_captured
signed_pdf_generated
manual_sign_upload_selected
manual_signed_file_uploaded
hr_verified
rejected
```

### 9.4 My Number Status

```text
not_requested
requested
submitted_encrypted
verified
rejected_for_correction
deleted_after_retention
not_required
```

## 10. Planned Data Files for Local MVP

If the local JSON architecture continues, add separate files under `database/`:

```text
database/employee_onboarding_requests.json
database/employee_onboarding_submissions.json
database/employee_onboarding_documents.json
database/employee_onboarding_signatures.json
database/employee_onboarding_mynumber_access_logs.json
```

Files should remain separate from `database/employees.json` until HR approval/import.

### 10.1 Request Example

```json
{
  "onboarding_request_id": "ONB-0001",
  "candidate_name": "Taro Yamada",
  "candidate_email": "candidate@example.com",
  "planned_start_date": "2026-07-01",
  "employment_type": "dispatch_employee",
  "onboarding_category": "haken_employee",
  "status": "sent",
  "token_hash": "sha256-token-hash",
  "token_expiry": "2026-07-08T23:59:59+09:00",
  "created_by": "USR-0001",
  "created_at": "2026-06-21T10:00:00+09:00",
  "sent_at": "2026-06-21T10:05:00+09:00",
  "sender_email": "HRadmin@tacjob.com"
}
```

### 10.2 Submission Example

```json
{
  "submission_id": "ONB-SUB-0001",
  "onboarding_request_id": "ONB-0001",
  "status": "pending_hr_review",
  "form_data": {
    "full_name": "Taro Yamada",
    "full_name_kana": "ヤマダ タロウ",
    "personal_email": "candidate@example.com",
    "phone": "090-xxxx-xxxx",
    "address": "Tokyo...",
    "nationality": "Japan",
    "my_number": {
      "encrypted_value": "...",
      "encryption_key_id": "KEY-0001",
      "last4": "1234",
      "collection_status": "submitted"
    }
  },
  "submitted_at": "2026-06-21T12:00:00+09:00"
}
```

### 10.3 Document Example

```json
{
  "document_id": "ONB-DOC-0001",
  "onboarding_request_id": "ONB-0001",
  "document_type": "labor_condition_notice",
  "direction": "hr_to_candidate",
  "signing_mode": "electronic_signature_optional",
  "status": "manual_signed_upload_received",
  "original_filename": "labor_condition_notice.pdf",
  "stored_filename": "ONB0001-DOC0001.pdf",
  "signed_stored_filename": "ONB0001-DOC0001-manual-signed.pdf",
  "content_type": "application/pdf",
  "file_size_bytes": 238421,
  "sha256_original": "...",
  "sha256_signed": "...",
  "uploaded_by": "USR-0001",
  "uploaded_at": "2026-06-21T10:02:00+09:00"
}
```

### 10.4 Signature Example

```json
{
  "signature_id": "SIG-0001",
  "onboarding_request_id": "ONB-0001",
  "document_id": "ONB-DOC-0001",
  "signer_name": "Taro Yamada",
  "signer_email": "candidate@example.com",
  "signature_method": "drawn_signature_pad",
  "consent_text_version": "electronic_signature_consent_v1",
  "signed_at": "2026-06-21T12:05:00+09:00",
  "ip_address": "redacted-or-stored-securely",
  "user_agent": "browser user agent",
  "token_id_reference": "ONB-0001",
  "document_sha256_before": "...",
  "document_sha256_after": "...",
  "evidence_status": "captured"
}
```

### 10.5 My Number Access Log Example

```json
{
  "access_log_id": "MYNUM-ACCESS-0001",
  "employee_id": "EMP-0001",
  "onboarding_request_id": "ONB-0001",
  "action": "my_number_viewed",
  "requested_by": "USR-0001",
  "role_at_access": "HR_ADMIN",
  "step_up_result": "success",
  "reason": "tax_and_social_insurance_processing",
  "accessed_at": "2026-06-22T09:30:00+09:00"
}
```

## 11. File Storage Plan

### 11.1 Local MVP Storage

Use a separate sensitive storage folder for onboarding files:

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

Rules:

- The folder must be git-ignored.
- Files must not be served directly by raw path.
- Access must go through authenticated EmployeeAdmin routes for HR, or token-validated candidate routes for candidate-specific downloads.
- Store generated filenames, not user-provided filenames.
- Preserve original filename only as metadata.
- Keep manually signed scanned uploads and electronically signed PDFs under separate metadata statuses.

### 11.2 Future Storage

Later production storage should consider:

- AWS S3 or equivalent object storage.
- Server-side encryption.
- Per-object access controls.
- Lifecycle/retention rules.
- Malware scanning.
- Backup and restore process.

## 12. Security Requirements

Minimum MVP controls:

- HTTPS in deployed environment.
- High-entropy random token.
- Store token hash, not raw token.
- Token expiry, default 7 days unless HR extends.
- Token tied to a single onboarding request.
- Rate limit token access if available.
- Candidate cannot browse other requests.
- HR pages require User_admin session and `employee_management.access`.
- HR upload/review routes should require stronger edit/document permission.
- File extension and MIME-type checks.
- Per-file and total-request size limits.
- Generated server filenames.
- Safe path validation.
- No raw public file serving.
- Sensitive values redacted in audit snapshots.
- Email body should contain only the secure link and high-level instructions.

Recommended signature evidence controls:

- Hash original PDF before signing.
- Hash signed PDF after signing.
- Record consent text version.
- Record signing timestamp.
- Record signer email/name.
- Record token/request reference.
- Record IP/user-agent according to privacy policy.
- Keep evidence immutable after HR approval.

Required My Number controls:

- Encrypt before storage.
- Keep encryption key separate from application data.
- Mask by default; show only last 4 digits if needed.
- Require HR/Admin permission plus separate step-up password before decrypt/view.
- Log every decrypt/view attempt with user, timestamp, reason, result, and record reference.
- Do not expose My Number in CSV, broad exports, audit snapshots, emails, or diagnostic JSON endpoints.
- Delete/dispose promptly when processing purpose is complete and legal retention period has passed.

## 13. Audit Requirements

Every major action must write an audit log with project-required fields:

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

Required onboarding audit events:

```text
onboarding_request_created
onboarding_contract_uploaded
onboarding_nda_uploaded
onboarding_labor_condition_notice_uploaded
onboarding_other_document_uploaded
onboarding_signing_mode_selected
onboarding_email_draft_prepared
onboarding_email_review_confirmed
onboarding_email_sent
onboarding_email_send_failed
onboarding_link_opened
electronic_delivery_consent_confirmed
document_viewed_by_candidate
document_downloaded_by_candidate
document_signed_by_candidate
manual_sign_upload_selected
manual_signed_file_uploaded
candidate_form_saved
candidate_file_uploaded
candidate_other_file_uploaded
candidate_submission_completed
hr_completion_notification_sent
hr_review_started
submission_returned_to_candidate
submission_approved
submission_rejected
employee_master_created_from_onboarding
employee_master_updated_from_onboarding
signed_document_archived
my_number_submitted_encrypted
my_number_view_requested
my_number_view_step_up_failed
my_number_viewed
my_number_deleted_after_retention
onboarding_request_expired
onboarding_request_cancelled
```

## 14. HR Review and Import Rules

HR review should show:

- Candidate identity and contact information.
- Completion status.
- Submitted form data.
- Uploaded candidate documents.
- Candidate-added other files.
- HR-provided documents.
- Signing mode per document.
- Signed document versions or manual signed uploads.
- Signature evidence summary.
- My Number collection status and masked last 4 digits only.
- Missing or rejected items.
- Data mapping preview into Employee Master.

Import rules:

- Do not overwrite existing Employee Master records silently.
- If matching by email or employee number finds an existing employee, show an update preview.
- If no match exists, create a new employee record with a new internal `employee_id` and operator-facing `employee_number` assigned by HR/system rule.
- Signed contract/NDA, labor condition notice, and submitted documents should be attached to the employee document management section after approval.
- Original onboarding submission should remain preserved for traceability.

## 15. Retention Policy Planning for Japan

Retention rules must be configurable by document category and should be reviewed before production use.

Official-reference planning baseline:

| Record category | Planning retention baseline | Notes |
|---|---:|---|
| Worker roster, wage ledger, important employment/labor documents | 5 years | Labor Standards Act Article 109 requires retention of worker rosters, wage ledgers, and important labor-related documents. |
| Employment contract / labor condition notice / payroll-related employee records | 5 years baseline | Start point may differ by record type, such as retirement/dismissal, last entry, or contract termination. |
| Worker dispatch / haken management records | 3 years | Dispatch management record retention is generally 3 years from dispatch end. |
| My Number / Individual Number | Until Individual Number-related processing is no longer necessary and the legal retention period has passed, then delete/dispose promptly | Do not retain simply because storage is available. |
| Rejected/cancelled onboarding package | Business/legal decision needed | Recommended short retention unless required for dispute/audit handling. |
| Signed contract/NDA and evidence package | Align with contract/employment record retention | Longer retention may be considered for dispute defense; confirm with advisor. |

System requirements:

- Store retention category per document.
- Store retention start date and calculated disposal review date.
- Do not auto-delete audit logs.
- Do not auto-delete legal records without HR/admin review.
- My Number disposal should be explicitly tracked and logged.

## 16. AI Integration Roadmap

AI should be assistive, not authoritative.

### MVP / Pilot

- No AI auto-approval.
- HR reviews all submissions manually.
- AI must not decrypt or process My Number.

### Later AI Assistance

AI may help with:

- Missing field detection.
- Document category suggestion.
- OCR extraction from residence card or bank documents.
- Name/date consistency checks between form and documents.
- HR review summary.
- Return-to-candidate email draft generation.

AI must not:

- Approve employment contracts automatically.
- Change Employee Master without HR approval.
- Read unrestricted employee mailboxes.
- Process My Number data unless a separate stronger control design is approved.

## 17. Implementation Phases

### Phase A — Business and Legal Confirmation

Goal: confirm exact required fields, document list, signing modes, and retention rules.

Deliverables:

- Final onboarding form field list.
- Contract/NDA/labor condition notice handling policy.
- Electronic delivery/signature consent text.
- Manual sign/upload fallback rules.
- My Number encryption and step-up access policy.
- Document retention policy.

### Phase B — Onboarding Request and Candidate Form MVP

Goal: run self-service form with secure link, file upload, and HR review.

Deliverables:

- HR request creation.
- Secure token link.
- Candidate form based on EmployeeAdmin employee master fields.
- Candidate required and optional document upload.
- My Number encrypted capture.
- Submission status.
- HR review list/detail.

### Phase C — Contract/NDA/Labor Condition Signing MVP

Goal: avoid unnecessary print/download/sign/scan while preserving manual fallback.

Deliverables:

- Browser PDF review flow.
- Per-document signing mode.
- Signature pad.
- Consent checkbox.
- Signature evidence record.
- Signed PDF or signature evidence packet generation.
- Manual sign/upload option.
- HR signature verification UI.

### Phase D — Email Automation

Goal: send links and completion notifications through configured SMTP.

Deliverables:

- Configurable SMTP sender using `HRadmin@tacjob.com` initially.
- Candidate invitation email.
- HR completion email.
- Return-to-candidate email.
- Email send audit logs.

### Phase E — HR Approval and Employee Master Import

Goal: convert approved onboarding package into official Employee Master data.

Deliverables:

- Data mapping preview.
- Create/update employee record.
- Attach signed documents to employee document management.
- Preserve encrypted My Number with restricted access policy.
- Immutable audit trail.

### Phase F — Pilot and Production Hardening

Goal: run a small controlled pilot and prepare for broader use.

Deliverables:

- 3-5 candidate pilot.
- HR operator feedback.
- Candidate UX feedback.
- File/security review.
- My Number access test and audit review.
- Backup/restore test.
- Decision on external e-signature provider for production.

## 18. Recommended MVP Sequence

Recommended practical order:

1. Build onboarding request and candidate form.
2. Add file upload and HR review.
3. Add SMTP invitation/completion emails using `HRadmin@tacjob.com`.
4. Add My Number encrypted storage and restricted-view audit design before collecting real My Number data.
5. Add per-document signing mode.
6. Add browser signature pad for NDA first.
7. Add employment contract and labor condition notice electronic/manual signing after HR/legal confirmation.
8. Add Employee Master import.
9. Pilot with a small group.
10. Decide whether external e-signature service is required.

NDA can be the first e-sign test because it is usually lower operational risk than employment contract/labor-condition documents.

## 19. Open Questions

- Confirm SMTP settings and app password for `HRadmin@tacjob.com`.
- Confirm whether sender casing should be displayed as `HRadmin@tacjob.com` or normalized to `hradmin@tacjob.com` in email templates.
- Which exact employment contract, NDA, and labor condition notice templates will HR upload in MVP?
- Which documents should default to electronic signature required, optional, manual sign/upload, acknowledgement-only, or no signature?
- What exact My Number step-up password mechanism should User_admin provide?
- What retention start date should be used for each document category in TAC operations?
- Which uploaded documents should become permanent employee documents after approval?
- Should candidate forms support Chinese/Japanese/English in the first release?

## 20. Reference Sources for Retention and My Number Planning

- Japanese Law Translation — Labor Standards Act, including Articles 107-109 for worker roster, wage ledger, and important record retention: https://www.japaneselawtranslation.go.jp/en/laws/link/2236
- Japanese Law Translation — Ordinance for Enforcement of the Labor Standards Act, retention start-point rules for worker roster, wage ledger, and important labor-related documents: https://www.japaneselawtranslation.go.jp/ja/laws/view/343
- Digital Agency — My Number FAQ for private-sector handling and disposal timing: https://www.digital.go.jp/en/policies/mynumber_faq_04
- Personal Information Protection Commission — FAQ on Individual Number disposal timing: https://www.ppc.go.jp/all_faq_index/faq5-q6-5
- Japanese Law Translation — Worker Dispatching Act, Article 37(2), dispatch management record retention: https://www.japaneselawtranslation.go.jp/en/laws/view/75/en
- Japanese Law Translation — Worker Dispatching Act regulations, retention period start from dispatch end: https://www.japaneselawtranslation.go.jp/en/laws/view/170/en
