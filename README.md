# CLAUDE-PROJECT

Private monorepo for TAC local-first business MVPs and related planning assets.

## Repository architecture

This workspace is organized as a monorepo containing multiple independent local projects:

- `TACAI-Core/` — shared platform services such as User Administration, Master Data, and Portal.
- `TAC-employeeadmin/` — employee administration MVP.
- `TAC-timesheet/` — timesheet management MVP.
- `TACAI-PRJ/` — HR finance / payroll workflow MVP.
- `TAC-reimbursement/` — reimbursement self-service MVP.
- `TAC-salary/` — salary and payroll calculation MVP.
- `VendorPayables/` — vendor payable workflow MVP.
- `customerbilling/` — customer billing workflow MVP.
- `fileadmin/` — file administration and document management MVP.
- `InterviewReady/` — interview readiness tooling.
- `deployment/` and `tactokyomail/` — deployment/runbook and mail-related planning assets.

Each module keeps its own README, docs, local run commands, and data schema notes. The repository root is used only for shared documentation, cross-module coordination, and GitHub source control.

## Privacy and data policy

This repository is intended to store source code, documentation, prompts, tests, templates, and schemas. It must not store real HR, payroll, reimbursement, customer/vendor, banking, password, resume, payslip, invoice, attachment, runtime log, or local machine configuration data.

The root `.gitignore` intentionally excludes local JSON databases, attachments, binary office documents, logs, project memory archives, and local Claude/MCP configuration.

## Local-first approach

Most MVP modules use Python standard-library web apps and local JSON files during development. Before sharing or deploying any module, create sanitized sample data or `.example.json` files instead of committing real runtime data.

## GitHub setup

Recommended GitHub settings:

1. Create the repository as **Private**.
2. Do not initialize with README, `.gitignore`, or license when pushing this local monorepo for the first time.
3. Use `main` as the default branch.
4. Review `git status` and staged files before every push.
