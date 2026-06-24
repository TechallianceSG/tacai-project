# TAC-employeeadmin Requirements

## Objective

TAC-employeeadmin will be the bilingual English/Japanese employee master data foundation for Payroll, Timesheet, Expense, Invoice, Training, and Dispatch Compliance management.

## Required Core Modules

1. Employee Profile.
2. Employment Information.
3. Payroll Information.
4. Visa Management.
5. Dispatch Compliance.
6. Skills & Language Profile.
7. Document Management.
8. Search & Dashboard.
9. Audit Trail.
10. Employee History & Change Traceability.

## Language Requirements

- UI language switching between English and Japanese is required.
- All UI labels must use i18n resources.
- Stored enum values must be language-neutral stable keys.
- Validation messages and dashboard labels should also be translatable.

## Personal Information

- Internal system ID.
- Employee number: required, editable, unique, and operator-facing.
- Name.
- Gender.
- Date of birth.
- Nationality.
- Address.
- Email.
- Phone.
- Emergency contact.
- Photo.

## Employment Information

- Join date.
- Employment type.
- Entity master-data reference.
- Department master-data reference.
- Team master-data reference.
- Position.
- Manager.
- Office location.
- Assignment.
- Status.
- Resignation information.

## Payroll Information

- Bank information.
- Salary type.
- Salary amount.
- Transportation allowance.
- Bonus eligibility.
- Social insurance.
- Pension.
- Employment insurance.

## Visa Management

- Visa type.
- Residence status.
- Expiry date.
- Residence card number.
- Passport information.
- Renewal reminder.

## Dispatch Compliance

- Client name.
- Assignment location.
- Dispatch start/end date.
- Contract type.
- Work description.
- Supervisor information.

## Language Profile

- Japanese level: N1/N2/N3/N4/N5 or Native.
- Native language(s).
- English level: Native/Business/Fluent/Intermediate/Basic.
- Additional languages.

## Skills Profile

- Primary skill.
- Secondary skill.
- Years of experience.
- IT skills: AWS, Azure, SAP, Java, Python, Security, Data, AI, etc.
- Engineering skills.
- Certifications.
- Industry experience.

## Document Management

- Employment contract.
- NDA.
- Residence card.
- Passport.
- My Number related documents.
- Offer letter.
- Certificates.

## Employee History & Change Traceability

- Employment history records for department, position, manager, status, assignment, probation, and resignation changes.
- Visa history records for visa type, residence status, expiry, passport, and renewal reminder changes.
- Dispatch assignment history records for client, location, dates, contract type, work description, and supervisor changes.
- Automatic history snapshots when key current employee sections change.
- Manual history record maintenance for authorized HR/compliance users.
- Local history attachments with protected access routes.
- Audit logging for manual history create/update actions.

## Dashboard

- Total employees.
- Active employees.
- Dispatch employees.
- Foreign employees.
- Visa expiry alerts.
- Probation alerts.
- New joiners.
