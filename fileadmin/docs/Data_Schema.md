# FileAdmin 数据 Schema 初稿

Last updated: 2026-06-24

## 0. Template Generator MVP 数据文件（已实现）

第一阶段模板生成使用以下 JSON 文件：

```text
database/document_templates.json         # 模板主数据：国家、语言、版本、状态、source_path
database/template_parameters.json        # 每个模板的参数定义、必填校验、排序、默认值
database/template_country_rules.json     # JP/CN/SG 国家默认规则，例如默认币种、review_required
database/template_generation_runs.json   # 每次生成的运行记录、参数快照、review status、生成文件关联
```

生成文件作为 FileAdmin 附件保存，不单独绕过文档管理：

```text
attachments/template_generated/<country_code>/<document_id>/<file_id>__<generation_id>__<template_code>.html
```

生成后的 `documents.json` / `document_records.json` 中，`template` 字段会记录：

- `is_template_generated`
- `template_id`
- `template_code_snapshot`
- `template_version_snapshot`
- `generation_id`
- `generation_status`
- `review_status`
- `template_source_type`
- `formal_approval_required_later`

## 1. 核心设计更新

FileAdmin 必须支持真实业务中的“一个合同 / 一个文档包包含多个文件”。因此数据模型采用：

```text
DocumentRecord 1 ---- N FileAttachment
DocumentRecord 1 ---- N Reminder
DocumentRecord 1 ---- N AuditLog
FileAttachment 1 ---- N AuditLog
```

也就是说：

- `document_records.json` / `documents.json`：保存业务文档记录，也可以理解为合同包、文书包、文件台账主记录。
- `file_attachments.json`：保存实际上传的多个文件。每个文件都有独立描述、版本、正式版标记、当前有效标记。
- `reminders.json` / `contract_reminders.json`：保存到期、自动续约、复核提醒。
- `audit_logs.json`：保存 append-only 审计日志。

> 说明：早期草案中的 `documents.json` 和 `document_versions.json` 可在实现时继续保留为兼容命名，但正式业务概念应按“文档记录 + 多文件附件”理解，避免误解为一条记录只能有一个文件。

## 2. 推荐 MVP 数据文件

```text
database/document_records.json      # 文档记录 / 合同包主记录
database/file_attachments.json      # 多文件附件记录
database/reminders.json             # 记录级或文件级提醒
database/document_categories.json   # 分类配置
database/folders.json               # 可选展示文件夹
database/audit_logs.json            # append-only 审计日志
```

## 3. 附件存储路径

推荐路径：

```text
attachments/<business_area>/<document_id>/<file_id>__<version_no>__<safe_original_filename>
```

示例：

```text
attachments/contracts/DOC-2026-0001/FILE-2026-0001__v1__ABC_dispatch_basic_agreement_signed.pdf
attachments/contracts/DOC-2026-0001/FILE-2026-0002__v1__ABC_unit_price_amendment.pdf
```

关键规则：

- 文件名必须安全化，禁止路径穿越。
- 上传后不得覆盖原文件。
- 新版本必须生成新 `file_id` 或新版本记录，并保留历史。
- 已签署正式版不得物理删除，只能归档。

## 4. document_records.json

用途：文档记录 / 合同包主台账。它表示业务上的一组文件，而不是单个文件。

```json
[
  {
    "document_id": "DOC-2026-0001",
    "document_no": "FA-DOC-0001",
    "title": "ABC株式会社 派遣基本契約書一式",
    "business_line": "dispatch",
    "document_category": "client_contract",
    "document_subcategory": "dispatch_basic_agreement",
    "entity_id": "TAKK",
    "entity_name_snapshot": "TAC Japan KK",
    "status": "active",
    "customer_id": "CUST-0001",
    "customer_snapshot": {
      "customer_name": "ABC株式会社",
      "customer_name_en": "ABC Corporation",
      "customer_owner": "Sales Manager"
    },
    "counterparty_contact": {
      "name": "山田太郎",
      "email": "taro.yamada@example.co.jp",
      "department": "人事部"
    },
    "contract": {
      "is_contract": true,
      "contract_start_date": "2026-07-01",
      "contract_end_date": "2027-06-30",
      "auto_renewal": true,
      "renewal_notice_days": 60,
      "termination_notice_days": 60,
      "payment_terms": "月末締め翌月末払い",
      "risk_notes": "自动更新前 60 天确认是否续约。"
    },
    "owner_user_id": "USR-0001",
    "owner_name_snapshot": "Admin User",
    "access_scope": "sales_hr_finance",
    "confidentiality_level": "contract_confidential",
    "record_revision": "R1",
    "tags": ["派遣", "基本契約", "重要顧客"],
    "summary": "客户派遣基本合同包，包含基本契约、个别契约模板、补充协议。",
    "created_by": "USR-0001",
    "created_at": "2026-06-23T10:00:00+09:00",
    "updated_by": "USR-0001",
    "updated_at": "2026-06-23T10:00:00+09:00",
    "archived": false,
    "archive_reason": ""
  }
]
```

### 4.1 document_records 必填字段

- `document_id`
- `title`
- `business_line`
- `document_category`
- `entity_id`
- `status`
- `owner_user_id`
- `confidentiality_level`
- `created_by`
- `created_at`

### 4.2 合同类必填字段

当 `contract.is_contract = true` 或 `document_category = client_contract/vendor_contract`：

- `contract.contract_start_date`
- `contract.contract_end_date` 或后续 `open_ended = true`
- `contract.auto_renewal`
- `owner_user_id`
- 至少一个提醒规则

## 5. file_attachments.json

用途：实际上传文件的 metadata。一条 `document_id` 可以关联多个 `file_id`。

```json
[
  {
    "file_id": "FILE-2026-0001",
    "document_id": "DOC-2026-0001",
    "file_title": "派遣基本契約書 双方盖章版",
    "file_description": "ABC株式会社与本公司签署的派遣基本契约 PDF 扫描件，双方盖章完成。",
    "file_type": "contract_signed_pdf",
    "file_role": "main_contract",
    "version_no": "v1.0",
    "file_status": "active",
    "is_current": true,
    "is_signed": true,
    "is_original_scan": true,
    "language": "ja",
    "confidentiality_level": "contract_confidential",
    "original_filename": "ABC_dispatch_basic_agreement_signed.pdf",
    "stored_filename": "FILE-2026-0001__v1__ABC_dispatch_basic_agreement_signed.pdf",
    "storage_path": "attachments/contracts/DOC-2026-0001/FILE-2026-0001__v1__ABC_dispatch_basic_agreement_signed.pdf",
    "mime_type": "application/pdf",
    "file_extension": ".pdf",
    "file_size_bytes": 2457600,
    "checksum_sha256": "",
    "file_effective_start_date": "2026-07-01",
    "file_effective_end_date": "2027-06-30",
    "uploaded_by": "USR-0001",
    "uploaded_at": "2026-06-23T10:05:00+09:00",
    "updated_by": "USR-0001",
    "updated_at": "2026-06-23T10:05:00+09:00",
    "archived": false,
    "deleted": false,
    "notes": "正式签署版，作为当前有效主合同。"
  },
  {
    "file_id": "FILE-2026-0002",
    "document_id": "DOC-2026-0001",
    "file_title": "2026年度 单价补充协议",
    "file_description": "2026 年度派遣单价补充协议，适用于 2026-07-01 至 2027-06-30。",
    "file_type": "amendment",
    "file_role": "price_amendment",
    "version_no": "v1.0",
    "file_status": "active",
    "is_current": true,
    "is_signed": true,
    "is_original_scan": true,
    "language": "ja",
    "confidentiality_level": "contract_confidential",
    "original_filename": "ABC_unit_price_amendment_2026.pdf",
    "stored_filename": "FILE-2026-0002__v1__ABC_unit_price_amendment_2026.pdf",
    "storage_path": "attachments/contracts/DOC-2026-0001/FILE-2026-0002__v1__ABC_unit_price_amendment_2026.pdf",
    "mime_type": "application/pdf",
    "file_extension": ".pdf",
    "file_size_bytes": 850000,
    "checksum_sha256": "",
    "file_effective_start_date": "2026-07-01",
    "file_effective_end_date": "2027-06-30",
    "uploaded_by": "USR-0001",
    "uploaded_at": "2026-06-23T10:10:00+09:00",
    "updated_by": "USR-0001",
    "updated_at": "2026-06-23T10:10:00+09:00",
    "archived": false,
    "deleted": false,
    "notes": "单价补充协议，与主合同一起生效。"
  }
]
```

### 5.1 file_attachments 必填字段

- `file_id`
- `document_id`
- `file_title`
- `file_description`
- `file_type`
- `file_role`
- `version_no`
- `is_current`
- `is_signed`
- `original_filename`
- `storage_path`
- `file_size_bytes`
- `uploaded_by`
- `uploaded_at`

### 5.2 文件级描述字段

MVP 界面中，每个上传文件至少要能单独填写：

- 文件显示标题。
- 文件说明。
- 文件类型。
- 文件角色。
- 版本号。
- 是否当前有效。
- 是否正式签署 / 盖章版。
- 语言。
- 保密等级。

## 6. reminders.json

用途：合同到期、自动续约、文件级有效期等提醒。

`file_id` 可以为空：

- `file_id = null`：文档记录级提醒，例如合同整体到期。
- `file_id = FILE-...`：附件级提醒，例如某份 NDA 或单价表单独到期。

```json
[
  {
    "reminder_id": "REM-2026-0001",
    "document_id": "DOC-2026-0001",
    "file_id": null,
    "reminder_type": "contract_expiry",
    "target_date": "2027-06-30",
    "remind_on": "2027-04-01",
    "days_before": 90,
    "status": "open",
    "priority": "high",
    "assigned_user_id": "USR-0001",
    "assigned_user_name_snapshot": "Admin User",
    "message": "ABC株式会社 派遣基本契約書将在 90 天后到期，请确认续约。",
    "action_result": "",
    "acknowledged_by": "",
    "acknowledged_at": "",
    "completed_by": "",
    "completed_at": "",
    "created_at": "2026-06-23T10:00:00+09:00",
    "updated_at": "2026-06-23T10:00:00+09:00"
  }
]
```

## 7. document_categories.json

```json
[
  {
    "category_code": "contract_client_dispatch",
    "category_name_ja": "派遣顧客契約",
    "category_name_en": "Dispatch Client Contract",
    "category_name_zh": "派遣客户合同",
    "business_line": "dispatch",
    "default_confidentiality_level": "contract_confidential",
    "requires_contract_fields": true,
    "requires_expiry_reminder": true,
    "allows_multiple_attachments": true,
    "is_active": true,
    "sort_order": 10
  }
]
```

## 8. audit_logs.json

用途：append-only 审计日志。审计日志不得删除，不做物理覆盖。

必须符合全局 Audit Rules：

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

```json
[
  {
    "audit_id": "AUD-2026-000001",
    "module": "fileadmin",
    "record_id": "DOC-2026-0001",
    "record_type": "document",
    "action": "upload_file",
    "user": "USR-0001",
    "user_name_snapshot": "Admin User",
    "timestamp": "2026-06-23T10:05:00+09:00",
    "before_value": null,
    "after_value": {
      "document_id": "DOC-2026-0001",
      "file_id": "FILE-2026-0001",
      "file_title": "派遣基本契約書 双方盖章版",
      "version_no": "v1.0"
    },
    "ip_address": "127.0.0.1",
    "user_agent": "",
    "notes": "上传合同包中的主合同文件。"
  }
]
```

### 8.1 action enum 初稿

```text
document_created
document_updated
document_archived
document_restored
file_uploaded
file_metadata_updated
file_marked_current
file_status_changed
file_archived
file_downloaded
contract_reminder_created
contract_reminder_acknowledged
contract_reminder_completed
contract_reminder_waived
template_status_changed
confidentiality_changed
csv_exported
```

## 9. 推荐枚举

### 9.1 business_line

```text
dispatch
recruitment
rpo
it_service
corporate
finance
hr
other
```

### 9.2 document_category

```text
client_contract
vendor_contract
employee_document
candidate_document
external_letter
internal_policy
invoice_evidence
project_document
template
other
```

### 9.3 file_type

```text
contract_draft_word
contract_review_pdf
contract_signed_pdf
amendment
nda
quotation
purchase_order
delivery_note
inspection_acceptance
email_confirmation_pdf
external_letter_pdf
template_word
other
```

### 9.4 file_role

```text
main_contract
individual_contract
amendment
nda
price_table
purchase_order
signed_scan
legal_review
email_evidence
template
other
```

### 9.5 document status

```text
draft
active
expiring
expired
renewed
terminated
archived
```

### 9.6 file status

```text
draft
review
approved
active
replaced
archived
```

### 9.7 confidentiality_level

```text
public_internal
business_confidential
contract_confidential
personal_data
highly_sensitive
```

## 10. 数据质量规则

1. 一个 `document_id` 可以对应多个 `file_id`。
2. 同一 `document_id + file_role` 下建议只有一个 `is_current = true` 的附件。
3. 已签署文件不允许物理删除。
4. 任何文件 metadata 修改必须写审计。
5. 任何文件上传、下载、归档必须写审计。
6. 文档记录必须保留客户快照，避免未来客户主数据变更影响历史合同。
7. OCR/AI 字段只能作为草稿建议，人工确认后才能写入正式字段。

## 11. 迁移到正式数据库时的映射

如果后续从 JSON 迁移到 SQLite/PostgreSQL，可按以下表映射：

- `document_records`
- `file_attachments`
- `document_categories`
- `reminders`
- `folders`
- `audit_logs`
- `ocr_document_drafts`
- `document_templates`
- `template_parameters`
- `template_generation_runs`
- `template_country_rules`

主键保持现在的业务 ID，避免迁移后破坏跨模块引用。

## 12. 可复用模板自动生成数据模型

用途：支持按国家/地区、语言、业务线和 Entity 管理可复用模板，并根据输入参数生成 Offer Letter、猎头合同、派遣合同、RPO/NDA/报价等草稿文件。

推荐新增数据文件：

```text
database/document_templates.json        # 模板主数据与版本状态
database/template_parameters.json       # 每个模板的参数定义
database/template_generation_runs.json  # 每次生成的模板版本、参数快照和输出记录
database/template_country_rules.json    # JP/CN/SG 国家规则、必填参数、默认币种和复核要求
```

推荐新增文件目录：

```text
templates/<country_code>/<template_code>.md
generated/<country_code>/<generation_id>__<template_code>.html
```

### 12.1 document_templates.json 核心字段

- `template_id`
- `template_code`
- `template_name`
- `country_code`：`JP` / `CN` / `SG`
- `language`：`ja` / `zh` / `en`
- `business_line`
- `document_category`：例如 `offer_letter`, `recruitment_agreement`, `dispatch_agreement`, `rpo_agreement`, `nda`, `quotation`
- `entity_scope`
- `status`：`draft`, `review`, `active`, `replaced`, `archived`
- `version_no`
- `is_current`
- `source_format`
- `source_path`
- `output_formats`
- `review_required`
- `legal_review_status`
- `effective_start_date`
- `effective_end_date`
- `owner_user_id`
- `created_by`, `created_at`, `updated_by`, `updated_at`

### 12.2 template_parameters.json 核心字段

- `parameter_id`
- `template_id`
- `parameter_key`
- `label_zh`, `label_ja`, `label_en`
- `input_type`
- `required`
- `source_hint`：manual / customer_master / employee_admin / interviewready_candidate / session_entity
- `validation_rule`
- `sort_order`

### 12.3 template_generation_runs.json 核心字段

- `generation_id`
- `template_id`
- `template_code_snapshot`
- `template_version_snapshot`
- `country_code`
- `language`
- `generated_document_id`
- `generated_file_id`
- `status`：`generated_draft`, `review_pending`, `reviewed`, `approved_generated`, `archived`
- `parameter_values_snapshot`
- `generated_output_path`
- `review_required`
- `review_status`
- `reviewed_by`, `reviewed_at`
- `created_by`, `created_at`

### 12.4 template_country_rules.json 核心字段

- `rule_id`
- `country_code`
- `document_category`
- `required_parameters`
- `default_currency`
- `review_required`
- `legal_review_required_for_activation`
- `notes`

### 12.5 数据质量规则

1. 只有 `status = active` 且 `is_current = true` 的模板可供普通用户生成文件。
2. 每次生成必须保存模板版本快照和参数快照，不能只保存生成后的文本。
3. 生成文件默认是草稿，必须人工确认后才可外发或签署。
4. 高风险模板，例如派遣合同、劳动合同、跨境雇佣文件，必须启用复核。
5. 国家/地区规则不能只靠语言判断；必须使用 `country_code` 和 `entity_scope`。
6. 模板创建、激活、生成、复核、下载、归档必须写 `audit_logs.json`。
