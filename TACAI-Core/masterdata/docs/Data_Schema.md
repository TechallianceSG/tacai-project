# TACAI Master Data Management V1 - Data Schema

Last updated: 2026-06-20

## 1. V1 database files

Planned local JSON files:

```text
database/
├── entities.json
├── departments.json
├── teams.json
├── customers.json
├── vendors.json
├── system_parameters.json
├── audit_logs.json
└── masterdata_versions.json
```

V1 uses JSON for local MVP storage. The schema should be designed so it can later migrate to a relational database without changing business semantics.

## 2. Common field conventions

All master records should use these conventions:

| Field | Type | Notes |
|---|---|---|
| `created_at` | string | ISO-like local timestamp. |
| `updated_at` | string | ISO-like local timestamp. |
| `status` | string | `active`, `inactive`, or legacy `deleted`. |

Current governance behavior uses `inactive` for deactivation. Physical deletion is not used. Legacy `deleted` records may remain hidden for backward compatibility, but new operator deactivation should set `status` to `inactive` so records remain visible, traceable, and restorable.

## 3. Entity schema

File: `database/entities.json`

`Entity` means an independent legal company / legal employer. It must not be used for departments, teams, projects, customers, work sites, or cost centers.

```json
[
  {
    "entity_id": "ENT-0001",
    "entity_code": "TAKK",
    "entity_type": "legal_entity",
    "legal_name": "テックアライアンス株式会社",
    "entity_name_en": "Tech Alliance KK",
    "entity_name_ja": "テックアライアンス株式会社",
    "entity_name_zh": "Tech Alliance 日本株式会社",
    "registration_number": "",
    "tax_registration_number": "",
    "country": "Japan",
    "currency": "JPY",
    "status": "active",
    "created_at": "2026-06-18T00:00:00",
    "updated_at": "2026-06-18T00:00:00"
  }
]
```

Validation rules:

- `entity_id` is required and immutable.
- `entity_code` is required and unique.
- `entity_type` is fixed to `legal_entity` in the MVP.
- `legal_name` is required and should hold the official registered company/legal employer name.
- `entity_name_en` is required.
- `entity_name_ja` is recommended for Japanese UI.
- `entity_name_zh` is recommended for Simplified Chinese UI.
- `registration_number` is optional in MVP but should store company/legal registration number when available.
- `tax_registration_number` is optional in MVP but should store tax/qualified invoice/social registration references when available.
- `country` is required in V1 until Country Master is added.
- `currency` is required in V1 until Currency Master is added.
- `status` must be `active`, `inactive`, or `deleted`.

## 4. Department schema

File: `database/departments.json`

```json
[
  {
    "department_id": "DEP-0001",
    "department_code": "RECRUITMENT",
    "department_name_en": "Recruitment",
    "department_name_ja": "採用",
    "department_name_zh": "招聘部",
    "entity_id": "ENT-0001",
    "status": "active",
    "created_at": "2026-06-18T00:00:00",
    "updated_at": "2026-06-18T00:00:00"
  }
]
```

Validation rules:

- `department_id` is required and immutable.
- `department_code` is required and unique within the parent `entity_id`.
- `department_name_en` is required.
- `department_name_ja` is recommended for Japanese UI.
- `department_name_zh` is recommended for Simplified Chinese UI.
- `entity_id` is required and must reference an existing non-deleted entity.
- `status` must be `active`, `inactive`, or `deleted`.

## 5. Team schema

File: `database/teams.json`

```json
[
  {
    "team_id": "TEAM-0001",
    "team_code": "JP-RECRUITMENT",
    "team_name_en": "Japan Recruitment Team",
    "team_name_ja": "日本採用チーム",
    "team_name_zh": "日本招聘团队",
    "department_id": "DEP-0001",
    "status": "active",
    "created_at": "2026-06-18T00:00:00",
    "updated_at": "2026-06-18T00:00:00"
  }
]
```

Validation rules:

- `team_id` is required and immutable.
- `team_code` is required and unique within the parent `department_id`.
- `team_name_en` is required.
- `team_name_ja` is recommended for Japanese UI.
- `team_name_zh` is recommended for Simplified Chinese UI.
- `department_id` is required and must reference an existing non-deleted department.
- `status` must be `active`, `inactive`, or `deleted`.

## 6. Customer Master schema

File: `database/customers.json`

```json
[
  {
    "customer_id": "CUS-0001",
    "customer_code": "ABC",
    "customer_name": "ABC株式会社",
    "customer_name_en": "ABC Corporation",
    "customer_name_zh": "ABC公司",
    "customer_registration_number": "",
    "billing_address": "Tokyo, Japan",
    "billing_contact_name": "Accounting Team",
    "billing_contact_email": "accounting@example.com",
    "default_language": "ja",
    "default_payment_terms_days": 30,
    "default_tax_rate": "10%",
    "business_types": ["haken_dispatch", "recruitment_placement", "rpo"],
    "notes": "",
    "status": "active",
    "created_at": "2026-06-21T00:00:00+00:00",
    "created_by": "finance@example.com",
    "updated_at": "2026-06-21T00:00:00+00:00",
    "updated_by": "finance@example.com"
  }
]
```

Validation rules:

- `customer_id` is required and immutable.
- `customer_code` is required and unique among non-deleted customers.
- `customer_name` is required as the default/Japanese billing name.
- `default_language` must be `ja`, `en`, or `zh`.
- `default_payment_terms_days` must be a positive integer.
- `default_tax_rate` must be `10%`, `8%`, `0%`, `mixed`, or `unknown`.
- `status` must be `active`, `inactive`, or `deleted`.
- Customer Master writes are governed by `client_revenue.customer_master.maintain` or `client_revenue.manage`; organization master permissions remain under `masterdata.*`.
- Customer Billing stores `customer_id` plus a billing-time `customer_snapshot`; historical billing records must not be overwritten when Customer Master changes.

## 7. Vendor Master schema

File: `database/vendors.json`

Vendor Master is the centralized supplier master used by VendorPayables and future procurement, outsourcing-cost, contract, and accounting workflows.

```json
[
  {
    "vendor_id": "VEN-0001",
    "vendor_code": "V-0001",
    "vendor_name_en": "Example Recruiting Media Co., Ltd.",
    "vendor_name_ja": "エグザンプル求人メディア株式会社",
    "vendor_name_zh": "Example 招聘媒体株式会社",
    "vendor_name_kana": "エグザンプルキュウジンメディア",
    "vendor_type": "recruitment_media",
    "supplier_record_mode": "standard_vendor",
    "entity_id": "ENT-0001",
    "country": "Japan",
    "postal_code": "100-0001",
    "address": "Tokyo, Japan",
    "qualified_invoice_number": "T1234567890123",
    "is_qualified_invoice_vendor": "yes",
    "contact_person": "Yamada Taro",
    "email": "billing@example.co.jp",
    "phone": "03-0000-0000",
    "bank_name": "三菱UFJ銀行",
    "bank_branch": "東京支店",
    "bank_account_type": "ordinary",
    "bank_account_number_masked": "****5678",
    "bank_account_holder": "エグザンプルキュウジンメディアカブシキガイシャ",
    "payment_terms": "月末締め翌月末払い",
    "default_currency": "JPY",
    "notes": "",
    "status": "active",
    "created_at": "2026-06-21T00:00:00+00:00",
    "updated_at": "2026-06-21T00:00:00+00:00"
  }
]
```

Validation rules:

- `vendor_id` is required and immutable.
- `vendor_code` is required and unique within `entity_id` among non-deleted vendors.
- `vendor_name_en` is required. Japanese and Chinese names are recommended.
- `entity_id` is required and must reference an active Entity.
- `vendor_type` should be one of `recruitment_media`, `outsourcing_partner`, `saas_system`, `professional_service`, `office_admin`, or `other`.
- `supplier_record_mode` should be `standard_vendor` for normal recurring suppliers or `one_time_vendor` for the shared one-time supplier code such as `ONETIME`.
- `qualified_invoice_number` is optional but recommended for Japan consumption tax checks. If entered, it should be `T` followed by 13 digits.
- Bank account numbers should be masked in the MVP.
- `status` must be `active`, `inactive`, or `deleted`; new deactivation should use `inactive`.
- VendorPayables stores `vendor_id` plus payable-time vendor snapshots; historical payment records must not be overwritten when Vendor Master changes.

## 8. System Parameters schema

File: `database/system_parameters.json`

System Parameters are shared runtime configuration records owned by Master Data. The first implemented parameter is `email.onboarding.smtp`, consumed by EmployeeAdmin onboarding email delivery.

```json
[
  {
    "parameter_id": "email.onboarding.smtp",
    "module": "masterdata.system_parameters",
    "category": "communication",
    "subcategory": "outbound_email",
    "scenario": "onboarding",
    "enabled": true,
    "value_type": "object",
    "value": {
      "sender_display_name": "TAC HR Admin",
      "sender_email": "hradmin@tacjob.com",
      "reply_to_email": "hradmin@tacjob.com",
      "hr_notification_email": "hradmin@tacjob.com",
      "smtp_host": "smtp.mxhichina.com",
      "smtp_port": 465,
      "smtp_username": "hradmin@tacjob.com",
      "smtp_use_tls": true,
      "smtp_use_ssl": false,
      "smtp_timeout_seconds": 15,
      "password_config_mode": "environment",
      "password_secret_ref": "ONBOARDING_SMTP_PASSWORD"
    },
    "secret_status": "missing",
    "environment": "local",
    "status": "active",
    "created_at": "2026-06-21T00:00:00+00:00",
    "updated_at": "2026-06-21T00:00:00+00:00"
  }
]
```

Validation and security rules:

- `parameter_id` is required and immutable.
- `email.onboarding.smtp` supports `environment` and `secret_ref` password modes in the dependency-free MVP.
- `password_secret_ref` names the environment variable that contains the runtime SMTP/app password.
- SMTP port must be between `1` and `65535`; timeout must be between `1` and `120` seconds.
- Sender, reply-to, HR notification, and test-recipient emails must use valid email format when supplied.
- The UI must never render plaintext SMTP passwords.
- Audit and version snapshots must sanitize secret fields.
- EmployeeAdmin consumes this setting through the internal-token API, not through local JSON ownership.


## 9. Audit log schema

File: `database/audit_logs.json`

```json
[
  {
    "module": "masterdata",
    "record_id": "ENT-0001",
    "action": "create_entity",
    "user": "admin@tacai.local",
    "timestamp": "2026-06-18T00:00:00",
    "before_value": null,
    "after_value": {
      "entity_id": "ENT-0001",
      "entity_code": "TAKK",
      "entity_name_en": "Tech Alliance KK",
      "status": "active"
    }
  }
]
```

Rules:

- Audit logs are append-only.
- Audit logs must never be deleted.
- All create, update, and soft-delete actions must write an audit record.
- `before_value` should contain the full previous record for update/delete.
- `after_value` should contain the full new record for create/update/delete.

## 9. Version history schema

File: `database/masterdata_versions.json`

```json
[
  {
    "version_id": "VER-000001",
    "record_type": "entity",
    "record_id": "ENT-0001",
    "version_number": 1,
    "action": "baseline",
    "changed_by": "admin@tacai.local",
    "changed_at": "2026-06-20T00:00:00+00:00",
    "change_reason": "System baseline created before first governed change.",
    "changed_fields": ["entity_code", "entity_name_en", "status"],
    "restored_from_version_id": "",
    "data_snapshot": {}
  }
]
```

Rules:

- Every create/update/deactivate/restore writes a version snapshot.
- Existing records without versions receive a baseline snapshot before their first governed change.
- Restore creates a new version whose `data_snapshot` is copied from the selected historical version; it does not delete intermediate history.
- Update/deactivate/restore require a business change reason and explicit acknowledgement of master-data impact.
- Audit logs reference the related `version_id` when available.

## 10. Integration reference fields for business modules

Business modules should store only references to MDM IDs:

```json
{
  "entity_id": "ENT-0001",
  "department_id": "DEP-0001",
  "team_id": "TEAM-0001"
}
```

Display names should be resolved from Master Data Management, not copied permanently into business records unless needed for historical snapshots.

## 10. Trilingual display and uniqueness rules

Master Data Management UI should support Simplified Chinese, Japanese, and English:

```text
i18n/en.json
i18n/ja.json
i18n/zh.json
```

Name fields should follow this pattern:

| Record | English | Japanese | Simplified Chinese |
|---|---|---|---|
| Entity | `entity_name_en` | `entity_name_ja` | `entity_name_zh` |
| Department | `department_name_en` | `department_name_ja` | `department_name_zh` |
| Team | `team_name_en` | `team_name_ja` | `team_name_zh` |

Language fallback rule:

1. Display the current language field when present.
2. Fallback to English when the current language field is blank.
3. Fallback to the business code when all names are blank.

Uniqueness rules:

- `entity_code` is globally unique among non-deleted entities.
- `department_code` is unique only within the same `entity_id` among non-deleted departments.
- `team_code` is unique only within the same `department_id` among non-deleted teams.

## 11. Entity context for integration

Business modules and User_admin sessions should use these fields to enforce entity-scoped access:

```json
{
  "entity_id": "ENT-0001",
  "entity_code": "TAJP"
}
```

User_admin should validate the selected Entity during login and return the current Entity from `/api/validate-session`. Masterdata and business modules should treat `entity_id` from the session as the default data scope.

## 12. Future schema extensions

Reserved future master files:

```text
database/employment_types.json
database/visa_types.json
database/countries.json
database/currencies.json
database/skill_categories.json
database/training_categories.json
```

Future fields to consider:

- `effective_from`
- `effective_to`
- `created_by`
- `updated_by`
- `approved_by`
- `approval_status`
- `external_system_code`
