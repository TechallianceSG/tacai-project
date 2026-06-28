# TACAIPAY JP MVP Test Plan

## Automated Smoke Test

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Project/TACAIPAY/tacaipayjp
python3 -m py_compile backend/app.py backend/jp_payroll_engine.py
python3 tests/smoke_mvp.py
```

The smoke test uses temporary database and payslip directories, so it does not modify real local data.

Automated coverage includes:

- monthly/hourly/daily payroll calculation
- overtime, late-night, absence, manual income tax, manual resident tax
- payroll batch totals
- printable HTML payslip rendering
- UTF-8 BOM CSV export and CSV injection protection
- HTTP API monthly payroll flow from salary master through paid status
- guarded workflow transitions and duplicate payslip prevention
- email dry-run recipient resolution and `missing_recipient` handling
- finalized batch update rejection
- payslip path containment under the controlled payslip directory
- audit log creation for major workflow actions

## Manual End-to-End Test

1. Start app:

```bash
python3 backend/app.py --host 127.0.0.1 --port 8017
```

2. Open `http://127.0.0.1:8017/`.
3. Switch UI language among Japanese, Chinese, and English.
4. Add three salary profiles:
   - monthly employee with email
   - hourly employee with email
   - daily employee, optionally with missing email to confirm dry-run warnings
5. Create a payroll batch for the current month.
6. Load salary master into the batch.
7. Edit attendance/manual tax/resident-tax input for at least one record.
8. Run calculation.
9. Confirm calculation messages include statutory/manual tax notes.
10. HR review.
11. First approve.
12. Generate HTML payslips.
13. Open one payslip and use browser print/save as PDF if needed.
14. Run payslip email dry-run.
15. Confirm delivery records show real employee email or `missing_recipient`.
16. Final approve.
17. Finalize.
18. Attempt to edit a finalized record and confirm it is rejected.
19. Prepare payment and mark paid.
20. Export finance/payment CSV.
21. Review reports and audit logs.

## Acceptance Criteria

- Default standalone port is `8017`, avoiding the temporary remote gateway on `8010`.
- Portal/User_admin data includes `TACAI Pay JP` with `tacaipay_jp.access` permission metadata.
- One record per employee per monthly batch.
- Monthly, hourly, and daily salary types calculate different base pay correctly.
- Overtime, late-night, holiday, absence, fixed/variable items are visible in records or payslip.
- Statutory items are calculated from parameters and marked as needing specialist confirmation.
- Batch workflow is sequentially guarded from master load through paid status.
- `final_approve` does not lock records; only `finalize` sets finalized record status.
- Finalized/paid batches cannot be casually overwritten.
- Payslip files are stored only under the controlled `payslips/` directory.
- Payslips are clearly labeled as printable HTML, not automated PDF output.
- Email dry-run resolves employee recipients or records `missing_recipient`.
- CSV exports use UTF-8 BOM and protect against CSV injection.
- Audit logs are created for create/import/load/calculate/approve/payslip/payment/export actions.

## Deferred Beyond MVP

- Official Japan tax table automation
- e-Tax/eLTAX/Mynaportal integration
- Live SMTP delivery
- Bank API transfer submission
- Automated PDF generation dependency
- Production statutory parameter sign-off
