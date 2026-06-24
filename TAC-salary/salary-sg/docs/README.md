# Singapore Salary Module

Last updated: 2026-06-23

`salary-sg` owns Singapore-specific payroll fields, CPF placeholders/manual input, payment snapshots, and Singapore payroll reporting support.

Singapore goes live together with Japan and China in the first formal TAC-salary rollout. It is not only a future placeholder. CPF automation can be added later after validation, but CPF fields must exist from launch.

## Initial legal entity

From Master Data:

| Entity ID | Entity Code | Entity Name | Currency |
| --- | --- | --- | --- |
| `ENT-0002` | `TASG` | Tech Alliance Consultancy Service Pte. Ltd | SGD |

## Employee population

Singapore payroll must support:

- regular employees;
- contract employees;
- part-time employees if any;
- foreign national employees;
- CPF-applicable and non-CPF-applicable employees.

## First-rollout payroll field groups

### Identity and profile snapshots

- employee ID and employee number snapshot;
- legal entity snapshot;
- employment type and worker type;
- work pass/citizenship/PR status snapshot where maintained;
- tax residency status snapshot;
- payment method and masked bank snapshot.

### Earnings

- basic salary;
- gross monthly wage;
- ordinary wage amount;
- additional wage amount;
- fixed allowances;
- variable allowance;
- bonus;
- other taxable earning;
- other non-taxable earning;
- gross pay;
- taxable gross pay.

### Employee deductions

- CPF employee manual amount;
- other statutory/manual deduction;
- salary advance repayment if any;
- other deduction with reason;
- total employee deductions.

### Employer costs

- CPF employer manual amount;
- skill development levy manual amount if applicable;
- foreign worker levy or local charge placeholder if applicable;
- other employer cost with reason;
- total employer cost.

### CPF fields from launch

- CPF applicable flag;
- ordinary wage;
- additional wage;
- employee CPF manual amount;
- employer CPF manual amount;
- employee CPF rate snapshot placeholder;
- employer CPF rate snapshot placeholder;
- CPF calculation mode: `manual`, `parameter_assisted`, or `automated_validated`.

## Calculation depth

Initial automated calculation can include:

- common arithmetic for gross pay, deductions, net pay, and employer cost;
- CPF manual amount inclusion in deductions/employer cost;
- validation warnings when CPF-applicable employee has missing CPF amounts.

CPF formula automation should be deferred until rules, employee categories, wage caps, and test cases are validated.

## Audit and evidence

Singapore payroll must audit:

- CPF manual entry/update;
- salary/profile snapshot load;
- calculation run;
- manual adjustment with reason;
- first notice and final notice email;
- PDF payslip generation/download;
- first and second confirmation;
- finalization and payment status.
