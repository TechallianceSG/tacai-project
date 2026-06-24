# Japan Salary Module

Last updated: 2026-06-23

`salary-jp` owns Japan-specific payroll fields, calculation rules, parameter references, and haken/dispatch payroll requirements.

Japan is a deep first-rollout country. The module should support real monthly payroll workflow from launch, while statutory automation is added only after official rule validation and payroll specialist sign-off.

## Initial legal entity

From Master Data:

| Entity ID | Entity Code | Entity Name | Currency |
| --- | --- | --- | --- |
| `ENT-0001` | `TAKK` | Tech Alliance KK / Tech Alliance株式会社 | JPY |

## Employee population

Japan payroll must support:

- regular employees;
- contract employees;
- part-time employees;
- dispatched/haken employees;
- foreign national employees where applicable.

## First-rollout payroll field groups

### Identity and haken/dispatch snapshots

- employee ID and employee number snapshot;
- legal entity snapshot;
- department/team snapshot;
- employment type and worker type;
- dispatch client ID/name snapshot;
- dispatch assignment ID;
- client site/worksite snapshot;
- work country/city.

### Work time and attendance

- standard monthly working days;
- standard monthly working hours;
- actual working days;
- actual working hours;
- paid leave days;
- unpaid leave days;
- absence days;
- overtime hours;
- late-night overtime hours;
- holiday work hours;
- statutory holiday work hours.

### Earnings

- base salary;
- hourly/daily rate if applicable;
- position allowance;
- commuting allowance taxable amount;
- commuting allowance non-taxable amount;
- housing allowance;
- overtime pay;
- late-night overtime pay;
- holiday work pay;
- bonus;
- other taxable earning;
- other non-taxable earning;
- gross pay;
- taxable gross pay.

### Employee deductions

- health insurance employee amount;
- nursing/care insurance employee amount where applicable;
- pension employee amount;
- employment insurance employee amount;
- income tax withholding;
- resident tax;
- other deduction with reason;
- total employee deductions.

### Employer costs

- health insurance employer amount;
- nursing/care insurance employer amount where applicable;
- pension employer amount;
- employment insurance employer amount;
- workers compensation employer amount;
- child care contribution employer amount;
- other employer cost with reason;
- total employer cost.

## Calculation depth

Initial automated calculation can include:

- common arithmetic for gross pay, deductions, net pay, and employer cost;
- simple overtime amount if hourly rate and overtime hours are confirmed;
- warning generation for missing attendance/salary/profile data.

Do not treat statutory social insurance, tax withholding, resident tax, or legally sensitive rates as production-ready automation until validated.

## Audit and evidence

Japan payroll must audit:

- source data load;
- calculation run;
- overtime/late-night/holiday adjustments;
- manual deduction/allowance adjustments;
- first notice sent;
- employee feedback resolution;
- final notice sent;
- first and second confirmation;
- finalization;
- payment status;
- payslip generation/download.
