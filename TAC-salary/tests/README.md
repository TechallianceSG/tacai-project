# Tests

TAC-salary keeps tests dependency-free for the local MVP.

## Smoke workflow

Run from the project root:

```bash
python3 tests/smoke_v2.py
```

The smoke test imports `backend/app.py`, redirects all JSON database paths and payslip output to a temporary directory, and verifies the APAC payroll v2 workflow without mutating the real `database/` files:

1. Create JP/SG/CN salary master profiles.
2. Create JP/SG/CN payroll batches.
3. Load JP employees with salary-master fallback when EmployeeAdmin is unavailable.
4. Calculate payroll, update country/manual fields, and add an adjustment.
5. Queue first notice, complete first and second confirmation, queue final notice, and finalize.
6. Verify finalized records reject direct adjustment.
7. Prepare payment and mark paid.
8. Generate a dependency-free text payslip.
9. Create CN city parameter data.
10. Submit/resolve employee feedback.
11. Generate net-pay report.
12. Verify all local JSON files remain arrays and audit logs are appended.

## Syntax check

```bash
python3 -m py_compile backend/app.py
```

## Runtime smoke

```bash
python3 backend/app.py --host 127.0.0.1 --port 8005
curl -s http://127.0.0.1:8005/health
curl -s http://127.0.0.1:8005/api/v2/dashboard
```
