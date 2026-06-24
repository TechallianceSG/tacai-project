# China Salary Module

Last updated: 2026-06-23

`salary-cn` owns China-specific payroll fields, city-level social insurance/housing fund parameters, individual income tax placeholders, and China employer cost reporting.

China goes live together with Japan and Singapore in the first formal TAC-salary rollout. City-level fields must exist from launch. Full statutory automation should wait for validated official/policy sources and payroll specialist sign-off.

## Initial legal entity scope

Business confirmation updated on 2026-06-23: China payroll scope includes all 3 active China legal entities in Master Data.

| Entity ID | Entity Code | Entity Name | Currency | Payroll note |
| --- | --- | --- | --- | --- |
| `ENT-0003` | `TANJ` | 南京特谙斯企业咨询有限公司 | CNY | CN Nanjing payroll entity |
| `ENT-0004` | `TAXA` | 西安特谙斯企业咨询有限公司 | CNY | CN Xi'an payroll entity |
| `ENT-0005` | `TASH` | 上海特安企业管理有限公司 | CNY | CN Shanghai payroll entity |

Payroll batches should be created separately by `CN + entity_id + payroll_month` for each active China legal entity in scope.

## Initial city scope

China payroll parameters must support:

- Shanghai;
- Nanjing;
- Xi'an;
- Wuhu.

Each payroll record should preserve both work city and social-insurance/housing-fund city because they may differ.

## Employee population

China payroll must support:

- regular employees;
- contract employees;
- part-time employees if any;
- foreign national employees if any;
- employees with different social insurance/housing fund city settings.

## First-rollout payroll field groups

### Identity and city snapshots

- employee ID and employee number snapshot;
- legal entity snapshot;
- employment type and worker type;
- work city;
- social insurance city;
- housing fund city;
- payment method and masked bank snapshot.

### Earnings

- base salary;
- fixed allowances;
- variable allowances;
- overtime pay if applicable;
- bonus;
- other taxable earning;
- other non-taxable earning;
- gross pay;
- taxable gross pay.

### Employee deductions

- pension employee;
- medical employee;
- unemployment employee;
- housing fund employee;
- individual income tax;
- special additional deduction manual amount;
- salary advance repayment if any;
- other deduction with reason;
- total employee deductions.

### Employer costs

- pension employer;
- medical employer;
- unemployment employer;
- work injury employer;
- maternity employer;
- housing fund employer;
- other employer cost with reason;
- total employer cost.

### IIT/YTD fields

- taxable income current month;
- cumulative taxable income YTD;
- cumulative tax paid YTD;
- individual income tax current month;
- special additional deduction manual amount.

## City parameter model

Each city parameter set should be effective-dated and versioned. Initial parameter object should include:

- country code `CN`;
- entity ID or `all_entities` scope;
- city code/name;
- effective from/to;
- employee contribution bases;
- employer contribution bases;
- employee rates/manual amounts;
- employer rates/manual amounts;
- housing fund base/rate/manual amounts;
- source reference;
- approval user/time.

## Calculation depth

Initial automated calculation can include:

- common arithmetic for gross pay, deductions, net pay, and employer cost;
- manual/parameter-assisted social insurance and housing fund values;
- warning generation when CN record lacks city, social insurance, housing fund, or IIT values.

Full China social insurance/housing fund/IIT formula automation should be deferred until city policy sources and test cases are validated.

## Audit and evidence

China payroll must audit:

- city parameter creation/update/approval;
- manual social insurance/housing fund values;
- salary/profile snapshot load;
- calculation run;
- manual adjustment with reason;
- employee feedback resolution;
- first and final notices;
- PDF payslip generation/download;
- first and second confirmation;
- finalization and payment status.
