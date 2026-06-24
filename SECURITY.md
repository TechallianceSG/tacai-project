# Security and privacy policy

This is a private business application monorepo. Treat all HR, payroll, reimbursement, customer/vendor, authentication, and document data as sensitive.

## Do not commit

- Real employee, candidate, customer, vendor, payroll, banking, or reimbursement records.
- Passwords, password hashes, API keys, tokens, SSH keys, certificates, or environment files.
- Runtime JSON databases from local MVP modules.
- Uploaded attachments, payslips, invoices, resumes, identity documents, or OCR source files.
- Local logs, PID files, machine-specific Claude/MCP settings, or archived operational memory.

## Commit instead

- Source code.
- Markdown documentation.
- Data schemas and field specifications.
- Sanitized `.example.json` files.
- Tests and small non-sensitive fixtures.
- Prompt templates that do not contain real personal data.

## Before pushing

Run:

```bash
git status --short
git diff --cached --name-only
```

Confirm that no sensitive data or binary personal/business documents are staged.
