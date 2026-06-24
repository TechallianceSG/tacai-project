# TAC-reimbursement

TAC-reimbursement is a standalone local-first MVP for Japan employee expense reimbursement and receipt/invoice self-service.

## Purpose

Employees in Japan can submit reimbursement claims through a self-service system. The preferred workflow is receipt/invoice image upload with OCR-assisted extraction that pre-fills the same standard reimbursement form used by manual entry. OCR is only an input aid; employees review, correct, and complete the standard claim fields before saving or submitting. Manual entry is also supported, with the receipt/invoice kept as an attachment. Finance reviews claims through a one-level approval workflow, then exports month-end reports for payroll and salary payment calculation.

## Initial scope

1. Employee self-service reimbursement claim submission.
2. Receipt/invoice image or PDF attachment upload.
3. OCR-assisted extraction plan for key fields:
   - receipt/invoice date
   - vendor name
   - qualified invoice registration number
   - tax rate
   - tax amount
   - total amount
   - currency
   - payment method
   - expense category
4. Manual entry fallback when OCR is unavailable or uncertain.
5. One-level finance approval.
6. Month-end finance/payroll report.
7. Local JSON-backed MVP first; production database and authentication are later decisions.

## Project structure

```text
TAC-reimbursement
├── backend          # Local Python standard-library web app
├── frontend         # Reserved for future UI assets; no code yet
├── database         # Local JSON data files
├── docs             # Product plan and specifications
├── prompts          # OCR/extraction prompts
├── attachments      # Local receipt/invoice attachment storage placeholder
├── memory           # Project status and decisions
├── archive          # Historical project records if needed
├── CLAUDE.md
└── README.md
```

## Current status

Phase 1 manual entry MVP is implemented.

Implemented:

- Local Python standard-library web app.
- Dashboard, claim list, new claim, and edit claim pages.
- Manual reimbursement claim entry.
- Embedded New Claim OCR input: employees can attach a receipt/invoice in the standard claim form, run local OCR for Japanese/English images or first-page PDFs, extract draft values into the original fields, then review/correct/confirm before submission. The app uses Tesseract/Poppler when installed and falls back to macOS Vision OCR on supported Macs.
- Receipt/invoice attachment upload under `attachments/`.
- Draft, Submitted, Approved, Rejected, and Paid status model.
- Finance review page with approve/reject actions, finance notes, rejection reason, and approval logs.
- Rejected claim correction and resubmission.
- Month-end finance report for approved claims with filters, grouped totals, CSV export, and export history.
- Paid status/payment closing from the finance report, with payment closing history and month lock protection.
- Soft delete for editable claims.
- Validation for dates, money, tax totals, tax rate, category, payment method, and qualified invoice number.

Not implemented yet:

- Cloud OCR provider/API integration.
- Fine-grained role actions beyond module access.
- Payroll/payment system integration.

## Portal/User_admin integration

TAC-reimbursement is connected to TACAI Portal and protected by TACAI User Management.

- Portal URL: `http://127.0.0.1:8005`
- Expense URL: `http://127.0.0.1:8003/`
- User_admin URL: `http://127.0.0.1:8006`
- Required module permission: `reimbursement.access`

All non-health reimbursement routes require a valid User_admin `tacai_session_id` cookie. Unauthenticated users are redirected to User_admin login with a local `next` return URL.

Local OCR notes:

- On macOS, the app can use Apple's built-in Vision OCR through the included Swift helper when Homebrew/Tesseract is unavailable.
- For stronger OCR and non-macOS environments, install Tesseract and Poppler:

```bash
brew install tesseract
brew install tesseract-lang
brew install poppler
```

Verify optional Tesseract/Poppler tools:

```bash
tesseract --version
tesseract --list-langs
pdftoppm -v
```

`tesseract --list-langs` should include `jpn` and `eng` for Japanese invoice OCR.

## Key documents

- [Project Plan](docs/Project_Plan.md)
- [Workflow Specification](docs/Workflow_Specification.md)
- [Data Schema](docs/Data_Schema.md)
- [Reporting Plan](docs/Reporting_Plan.md)
- [Manual Test Checklist](docs/Manual_Test_Checklist.md)
- [OCR Receipt Prompt](prompts/OCR_Receipt_Prompt.md)

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
python3 backend/app.py --host 127.0.0.1 --port 8003
```

Open:

```text
http://127.0.0.1:8003
```

Health check:

```text
http://127.0.0.1:8003/health
```

## Main pages

- `/` — dashboard.
- `/claim-new` — standard reimbursement claim entry with attachment upload and optional embedded OCR extraction.
- `/claims` — claim list, filters, totals, OCR status, edit/delete actions.
- `/finance-review` — finance review queue, filters, and approval status overview.
- `/finance-claim?id=<claim_id>` — finance detail page with approve/reject actions and approval history.
- `/finance-report` — month-end approved/paid claim report with filters, summaries, CSV export link, export history, payment closing panel, and payment closing history.
- `/finance-report.csv` — CSV export using the current report filters; writes export history to `database/report_exports.json`.

## Recommended implementation order

1. Confirm MVP scope and fields. Done.
2. Build local standard-library web app shell. Done.
3. Implement manual claim entry and attachment upload. Done.
4. Add embedded New Claim OCR extraction that pre-fills the standard reimbursement form. Done.
5. Add finance approval workflow. Done.
6. Add month-end CSV report. Done.
7. Add login/roles and production hardening later.
