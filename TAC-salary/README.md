# TAC-salary

TAC-salary is the TACAI APAC payroll planning and MVP module under `claude-project`.

## Scope

TAC-salary has been repositioned from a limited Japan salary-table MVP into a core APAC payroll system covering:

- Japan payroll calculation and haken/dispatch salary operations;
- Singapore payroll calculation with CPF fields from launch;
- China payroll calculation with city-level social insurance and housing fund fields;
- employee net pay calculation;
- employer cost reporting;
- monthly payroll batch creation by country/entity/month;
- HR review, manual correction, employee notice, feedback, final notice, two-level finalization, payment tracking, and archive;
- system email payroll notices and downloadable PDF payslips;
- append-only audit logging.

Initial employee population includes dispatched/haken employees, regular employees, contract employees, part-time employees, and foreign national employees.

## Architecture direction

The recommended v2 architecture is:

```text
salary-core/   shared payroll batch, workflow, snapshot, notice, PDF, payment, employer cost, and audit logic
salary-jp/     Japan-specific fields, overtime/late-night/holiday and haken/dispatch requirements
salary-sg/     Singapore-specific fields and CPF manual/parameter-assisted launch support
salary-cn/     China-specific city-level social insurance, housing fund, and IIT placeholders
```

Payroll batches should be controlled by:

```text
country_code + entity_id + payroll_month + payroll_type
```

## Key documents

- `docs/Project_Plan.md` — APAC payroll rebuild plan.
- `docs/Data_Schema.md` — APAC payroll v2 JSON data model.
- `docs/Salary_Table_Specification.md` — first-rollout APAC payroll table specification.
- `docs/Implementation_Steps_v2.md` — implementation sequence for the local APAC payroll MVP.
- `salary-core/docs/README.md` — shared workflow and common payroll rules.
- `salary-jp/docs/README.md` — Japan payroll module requirements.
- `salary-sg/docs/README.md` — Singapore payroll module requirements.
- `salary-cn/docs/README.md` — China payroll module requirements.

## Current local MVP command

```bash
cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 backend/app.py --host 127.0.0.1 --port 8005
```

Open <http://127.0.0.1:8005>.

## Health check

```bash
curl -s http://127.0.0.1:8005/health
```

## Syntax check

```bash
python3 -m py_compile backend/app.py
```

## Compliance notes

Japan payroll, Singapore CPF, and China social insurance/housing fund/IIT rules must be validated against official sources and/or qualified payroll advisors before production automation. Until validated, statutory values should be manually maintained or parameter-assisted with rule versioning, human approval, and audit history.
