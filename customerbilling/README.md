# Customer Billing

Customer Billing is a local-first Billing & Accounts Receivable MVP for TACAI.

It supports Japanese/English invoice and request note creation, manual payment registration, AR aging reports, and append-only audit logs for haken/dispatch, recruitment placement, and RPO billing. Customer Master is owned by TACAI Master Data and consumed by this module through Master Data APIs.

## Run locally

```bash
cd /Users/terencewang/Documents/claude-project/customerbilling
python3 backend/app.py --host 127.0.0.1 --port 8009
```

## Health check

```bash
curl -s http://127.0.0.1:8009/health
```

## Syntax check

```bash
python3 -m py_compile backend/app.py
```

## Portal integration

- Portal URL: `http://127.0.0.1:8009/`
- Health URL: `http://127.0.0.1:8009/health`
- Required permission: `client_revenue.access`
- Intended Portal placement: after Vendor Payments and before InterviewReady.
- Customer source of truth: `TACAI-Core/masterdata/database/customers.json` via Master Data `/api/customers` on port `8007`.
- Local `database/customers.json` is legacy/migration-only and is no longer the active customer source.
