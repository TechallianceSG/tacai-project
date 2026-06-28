# TACAIPAY JP

Japan payroll MVP for TACAI, focused on dispatch, recruiting, RPO, and payroll-management businesses.

## Run

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-Project/TACAIPAY/tacaipayjp
python3 backend/app.py --host 127.0.0.1 --port 8017
```

Open `http://127.0.0.1:8017/`.

Port `8017` is used for the standalone JP payroll module so it does not conflict with the temporary remote gateway convention on `8010`.

## Verify

```bash
python3 -m py_compile backend/app.py backend/jp_payroll_engine.py
python3 tests/smoke_mvp.py
```

The smoke test uses temporary database and payslip directories. It covers both function-level payroll calculation and HTTP-level monthly payroll workflow.

## Scope

This MVP provides:

- EmployeeAdmin import/local salary master
- Monthly payroll batches
- One payroll record per employee per month
- Monthly/hourly/daily salary calculation
- Attendance, overtime, late-night, holiday, absence, manual tax/resident-tax inputs
- Parameter-assisted Japan statutory deductions/employer costs
- Guarded workflow: master load → calculate → HR review → first approval → HTML payslip generation → email dry-run → final approval → finalization → payment prepare/paid
- HTML payslip generation with browser print/save-to-PDF guidance
- Email dry-run records with real employee-recipient resolution or `missing_recipient` status
- Payment prepare/paid workflow
- Finance/payment CSV exports
- Cost summary reports and audit logs
- Portal/User_admin registration metadata for `tacaipay_jp.access`

Japanese statutory tax/social-insurance values are parameter-assisted and must be confirmed by HR/payroll/tax specialists before final approval/payment. Live SMTP sending, official Japan tax table automation, bank API submission, and automated PDF generation remain out of this MVP scope.
