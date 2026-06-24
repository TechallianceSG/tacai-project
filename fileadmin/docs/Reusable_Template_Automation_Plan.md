# FileAdmin 可复用模板自动生成需求与实施计划

Last updated: 2026-06-24

## 0. 当前实现状态（2026-06-24）

已完成第一阶段 Template Generator MVP：

- 在 FileAdmin 中新增 `/templates` 模板库、`/templates/generate` 参数生成页、`/templates/runs/detail` 生成记录页。
- 首批只启用系统建议标准模板：JP / CN / SG Offer Letter workflow-test 草稿。
- 生成结果会自动创建 FileAdmin `DocumentRecord`，并作为 `FileAttachment` / `DocumentVersion` 保存到 `attachments/template_generated/` 下。
- 生成记录保存到 `database/template_generation_runs.json`，包含模板版本快照、参数快照、生成用户、生成文件和 review status。
- 生成文件默认 `generated_draft` / `review`，必须人工 review；这不是正式公司批准模板。
- 正式公司现用模板需在流程跑通后，与系统建议标准合并，形成最终批准版本后再上线使用。

## 1. 需求定位

在 FileAdmin 中增加一个独立的“模板自动生成”能力，用于管理和生成可重复使用的业务文书，例如：

- 按国家/地区的 Offer Letter。
- 按国家/地区的猎头/人材紹介/Recruitment Agreement。
- 按国家/地区的派遣/劳务派遣/Dispatch Agreement。
- RPO 服务合同、服务说明书、NDA、报价书、候选人推荐信、员工入职通知等。

核心目标不是替代法务或 HR 审核，而是把高频、可参数化、可版本治理的文书从“复制旧文件再手工改”升级为“选择国家 + 选择模板 + 输入参数 + 系统生成草稿 + 人工复核 + 归档审计”。

## 2. 多专家视角分析

### 2.1 文件管理专家视角

#### 当前痛点

1. 模板散落在个人电脑、旧邮件、共享盘或聊天记录中，无法确认哪个版本是最新有效版本。
2. 同一国家、同一业务类型存在多个相似模板，容易误用旧条款。
3. 文件生成后没有统一台账，不容易追踪是谁生成、何时生成、基于哪个模板版本生成。
4. 生成文件与客户、候选人、员工、Entity、业务线之间缺少结构化关联。

#### 文件治理原则

- 每一个模板必须有唯一 `template_id`、国家/地区、语言、业务线、适用 Entity、状态、版本号和负责人。
- 每一次生成必须形成 `generated_document_id`，并记录模板版本、输入参数快照、生成时间、生成用户和复核状态。
- 模板源文件、生成文件、最终签署版必须分开管理：
  - 模板源文件：可复用资产。
  - 生成草稿：系统生成、待人工确认。
  - 正式文件：人工确认/签署后的当前有效文件。
- 模板历史版本不得覆盖；旧版本只可归档或标记 replaced。
- 生成文件应自动进入 FileAdmin 文档台账，并可挂载到对应 DocumentRecord / FileAttachment。

### 2.2 效率提升专家视角

#### 高价值场景

| 场景 | 现状 | 自动化价值 |
|---|---|---|
| Offer Letter | HR 每次复制旧 offer 改姓名、工资、入职日 | 2-5 分钟生成草稿，减少错填 |
| 猎头合同 | Sales/Consultant 反复修改客户名、费率、返金条款 | 标准化合同版本和商业条款 |
| 派遣合同 | 需要客户、派遣期间、工作地点、单价、岗位等多字段 | 减少派遣法相关字段遗漏 |
| RPO 合同/服务说明 | 项目名称、服务范围、SLA、费用结构重复改写 | 快速生成客户初版 |
| NDA/报价书 | 高频标准文件 | 提升响应速度 |

#### 推荐效率指标

- 高频模板生成时间从 20-60 分钟降到 3-10 分钟。
- 模板误用/旧版本误用减少到可审计、可追责。
- 关键字段遗漏通过必填参数校验减少。
- HR/Sales/Finance 能从同一入口找到当前有效模板。

### 2.3 流程专家视角

#### 推荐流程

```text
模板维护
  ↓
模板审批/生效
  ↓
用户选择模板
  ↓
系统显示参数表单
  ↓
用户填写/从主数据带入参数
  ↓
系统校验必填字段和国家规则
  ↓
生成草稿文件
  ↓
人工复核/修改
  ↓
确认正式版本
  ↓
归档到 FileAdmin 文档记录
  ↓
后续签署版上传、版本和审计管理
```

#### 流程角色

| 角色 | 责任 |
|---|---|
| Template Admin | 维护模板、参数定义、国家适用范围、版本状态 |
| HR Manager | Offer Letter、人事类通知模板复核 |
| Sales/Consultant Manager | 猎头合同、客户提案、RPO/IT 服务模板复核 |
| Finance | 付款条款、费用、税务/发票相关字段复核 |
| System Admin | 权限、审计、系统配置 |
| Legal/External Advisor | 关键合同模板定期法务确认 |

#### 控制点

- `draft` 模板不可用于正式生成，只能内部测试。
- 只有 `active` 模板可被普通业务用户选择。
- 生成文件默认是 `generated_draft`，必须人工确认后才能标记为 `approved_generated` 或上传签署版。
- 高风险模板，例如派遣合同、劳动合同、跨境雇佣文件，必须增加复核状态。
- 所有生成、修改、下载、确认、归档都写 append-only audit log。

### 2.4 IT 架构专家视角

#### MVP 技术路线

保持 FileAdmin 现有轻量架构：

- Python 标准库 Web App。
- 本地 JSON 数据。
- 本地文件存储。
- User_admin 权限与 Portal 入口。
- 生成文件先支持文本/Markdown/HTML 草稿，后续再支持 DOCX/PDF。

#### 推荐模块边界

在 FileAdmin 内增加独立子功能：`Template Generator`。

```text
fileadmin/
├── templates/                         # 模板资产，可存 .md/.html/.docx 占位
├── generated/                         # 系统生成的草稿/正式输出文件
├── database/
│   ├── document_templates.json        # 模板主数据
│   ├── template_parameters.json       # 模板参数定义
│   ├── template_generation_runs.json  # 每次生成记录
│   └── template_country_rules.json    # 国家/业务规则配置
└── docs/
    └── Reusable_Template_Automation_Plan.md
```

#### 模板引擎建议

MVP 建议先采用简单占位符替换，避免过早引入复杂依赖：

```text
{{company_name}}
{{customer_name}}
{{candidate_name}}
{{employee_name}}
{{start_date}}
{{salary_amount}}
{{currency}}
{{work_location}}
```

后续可升级：

- 条件段落：例如 Japan dispatch / Singapore employment / China labor contract 不同条款。
- 多语言标签：中文、日文、英文。
- DOCX/PDF 生成。
- 从 EmployeeAdmin、MasterData、Customer Billing、InterviewReady 引入主数据。
- AI 辅助改写/翻译，但必须人工确认。

### 2.5 产品专家视角

#### MVP 用户体验

1. 左侧/顶部新增入口：`Templates / 模板生成`。
2. 页面 1：模板库
   - 按国家、业务线、文件类型、语言、状态筛选。
   - 标记“当前有效模板”。
3. 页面 2：生成新文件
   - 选择国家：Japan / China / Singapore。
   - 选择模板类型：Offer Letter / Recruitment Contract / Dispatch Contract / RPO / NDA / Quotation。
   - 自动显示该模板需要填写的参数。
   - 可从客户主数据、员工主数据、候选人信息中带入字段。
4. 页面 3：生成预览
   - 显示生成后的 HTML/Markdown 预览。
   - 标记“草稿，需人工复核”。
5. 页面 4：保存到 FileAdmin
   - 保存为 DocumentRecord。
   - 生成文件作为 FileAttachment。
   - 后续上传签署版作为新附件/新版本。

#### 产品边界

MVP 不做：

- 自动发送 offer 或合同给外部客户/候选人。
- 电子签名。
- 在线 Word 协作编辑。
- 自动法律判断。
- 无人工确认的自动正式发文。

## 3. 日本、中国、新加坡运营需求

### 3.1 共通要求

- 国家/地区是模板主维度之一，不能只用语言区分。
- 同一国家内应支持不同 Entity / legal employer。
- 模板必须支持多语言版本，但业务规则以国家/地区和法律主体为准。
- 模板生成要保留参数快照，避免未来主数据变化影响历史文件。
- 任何合同和 offer 模板必须经过本地 HR/Finance/Legal 或外部顾问确认后才能标记为 `active`。

### 3.2 Japan 日本

重点业务：派遣、人材紹介、RPO、IT/SES、雇佣/Offer。

优先模板：

- 日文 Offer Letter / 内定通知。
- 労働条件通知書相关模板。
- 派遣基本契約書。
- 派遣個別契約書 / 注文書 / 注文請書。
- 人材紹介基本契約書。
- NDA。
- 見積書 / サービス説明書。

关键参数示例：

- Legal Entity：日本法人。
- 客户名称、客户地址、联系人、部门、邮箱。
- 候选人/员工姓名、地址、邮箱、入社日。
- 雇佣形态、职位、工作地点、工资/时薪、交通费、试用期。
- 派遣期间、业务内容、就业场所、指挥命令者、派遣单价、抵触日/相关备注。
- 付款条件、消费税处理、自动更新/解约通知期限。

合规提醒：

- 派遣相关模板必须由日本业务负责人确认字段完整性。
- 劳动条件、派遣条件、费用和税务字段不能由 AI 或系统自动决定。
- 模板状态需要强控制，防止旧版派遣合同或旧版 offer 被误用。

### 3.3 China 中国

重点业务：本地雇佣、RPO、猎头、客户服务合同、员工通知。

优先模板：

- 中文 Offer Letter / 录用通知书。
- 劳动合同补充信息模板或入职确认类文件。
- 猎头服务合同。
- RPO 服务合同。
- NDA / 保密协议。
- 客户报价/服务说明。

关键参数示例：

- Legal Entity：中国各法人，例如南京、西安、上海等实体。
- 城市：上海、南京、西安、芜湖等运营城市。
- 客户名称、统一社会信用代码、地址、联系人、邮箱。
- 候选人/员工姓名、身份证/证件字段是否需要由 EmployeeAdmin 控制，模板生成尽量避免直接暴露高敏信息。
- 入职日期、岗位、工作地点、薪资结构、试用期、社保公积金城市规则说明。
- 服务费率、付款节点、退款/保证期条款。

合规提醒：

- 中国不同城市和不同法人可能存在不同入职/社保/公积金操作规则，模板应按 legal entity + city 做参数化。
- 高敏个人信息不建议直接进入通用模板生成日志；如必须使用，应按 EmployeeAdmin 高敏数据策略处理。
- 劳动合同正式文本建议保持人工/法务确认，系统先生成 offer、服务合同和标准通知草稿。

### 3.4 Singapore 新加坡

重点业务：本地雇佣、招聘服务、RPO、客户服务合同。

优先模板：

- English Offer Letter。
- Employment key terms / appointment letter draft。
- Recruitment Agreement。
- RPO / HR service agreement。
- NDA。
- Service quotation。

关键参数示例：

- Legal Entity：Singapore entity。
- Candidate/employee name, address/email, start date, job title, work location。
- Salary, currency SGD, CPF-related note if applicable, leave/probation notice fields。
- Client company, UEN if available, address, contact person, fee rate, guarantee/replacement period。
- GST/tax wording and payment terms if relevant。

合规提醒：

- Offer 和雇佣条款需要遵循本地 HR/Employment Act/CPF 相关确认流程。
- 新加坡英文模板可作为 APAC 英文模板基线，但不能直接复用为日本或中国合同模板。
- 币种、税、CPF/GST 相关字段应结构化，避免手工漏改。

## 4. 推荐模板分类

```text
offer_letter_jp
offer_letter_cn
offer_letter_sg
recruitment_agreement_jp
recruitment_agreement_cn
recruitment_agreement_sg
dispatch_basic_agreement_jp
dispatch_individual_agreement_jp
rpo_service_agreement_jp
rpo_service_agreement_cn
rpo_service_agreement_sg
nda_jp
nda_cn
nda_sg
quotation_jp
quotation_cn
quotation_sg
candidate_recommendation_letter
client_service_proposal
employee_notice
```

## 5. 数据模型初稿

### 5.1 document_templates.json

```json
[
  {
    "template_id": "TPL-2026-0001",
    "template_code": "offer_letter_jp_standard_v1",
    "template_name": "Japan Standard Offer Letter",
    "country_code": "JP",
    "language": "ja",
    "business_line": "hr",
    "document_category": "offer_letter",
    "entity_scope": ["TAKK"],
    "status": "active",
    "version_no": "v1.0",
    "is_current": true,
    "source_format": "markdown",
    "source_path": "templates/JP/offer_letter_jp_standard_v1.md",
    "output_formats": ["html", "markdown"],
    "owner_user_id": "USR-0001",
    "review_required": true,
    "legal_review_status": "approved",
    "effective_start_date": "2026-07-01",
    "effective_end_date": "",
    "created_by": "USR-0001",
    "created_at": "2026-06-24T10:00:00+09:00",
    "updated_by": "USR-0001",
    "updated_at": "2026-06-24T10:00:00+09:00",
    "notes": "MVP sample schema. Actual template text must be approved before active use."
  }
]
```

### 5.2 template_parameters.json

```json
[
  {
    "parameter_id": "TPAR-2026-0001",
    "template_id": "TPL-2026-0001",
    "parameter_key": "candidate_name",
    "label_zh": "候选人姓名",
    "label_ja": "候補者氏名",
    "label_en": "Candidate Name",
    "input_type": "text",
    "required": true,
    "source_hint": "manual_or_interviewready_candidate",
    "validation_rule": "non_empty",
    "sort_order": 10
  }
]
```

### 5.3 template_generation_runs.json

```json
[
  {
    "generation_id": "TGEN-2026-0001",
    "template_id": "TPL-2026-0001",
    "template_code_snapshot": "offer_letter_jp_standard_v1",
    "template_version_snapshot": "v1.0",
    "country_code": "JP",
    "language": "ja",
    "generated_document_id": "DOC-2026-0101",
    "generated_file_id": "FILE-2026-0101",
    "status": "generated_draft",
    "parameter_values_snapshot": {
      "candidate_name": "山田太郎",
      "start_date": "2026-08-01",
      "job_title": "Recruitment Consultant"
    },
    "generated_output_path": "generated/JP/TGEN-2026-0001__offer_letter_jp_standard_v1.html",
    "review_required": true,
    "review_status": "pending",
    "reviewed_by": "",
    "reviewed_at": "",
    "created_by": "USR-0001",
    "created_at": "2026-06-24T10:05:00+09:00"
  }
]
```

### 5.4 template_country_rules.json

```json
[
  {
    "rule_id": "TRULE-2026-JP-OFFER-001",
    "country_code": "JP",
    "document_category": "offer_letter",
    "required_parameters": ["candidate_name", "start_date", "job_title", "work_location", "salary_amount", "currency"],
    "default_currency": "JPY",
    "review_required": true,
    "legal_review_required_for_activation": true,
    "notes": "Country rule configuration for validation, not legal advice."
  }
]
```

## 6. 权限建议

新增权限 namespace：

```text
fileadmin.templates.view
fileadmin.templates.generate
fileadmin.templates.manage
fileadmin.templates.approve
fileadmin.templates.audit.view
```

角色建议：

| 角色 | 权限建议 |
|---|---|
| System Admin | 全部权限 |
| Document Admin | view/generate/manage/audit |
| HR Manager | HR/offer 模板 view/generate，部分 approve |
| Sales/Consultant Manager | 客户合同/猎头/RPO 模板 view/generate |
| Finance | 付款/费用/税务字段相关模板 view/review |
| Employee/Consultant | 默认无模板管理权限；如需生成，限定低风险模板 |

## 7. 分阶段实施计划

### Phase T0 — 需求确认与模板盘点

目标：确定第一批高频模板。

任务：

- 盘点日本、中国、新加坡现有 offer、猎头合同、派遣合同、RPO、NDA、报价模板。
- 标记每个模板的国家、语言、Entity、业务线、负责人、当前有效性。
- 确定第一批 9 个 MVP 模板：
  - JP/CN/SG Offer Letter。
  - JP/CN/SG Recruitment Agreement。
  - JP Dispatch Basic Agreement。
  - JP Dispatch Individual Agreement。
  - SG/CN RPO 或 NDA 二选一按业务优先级。

### Phase T1 — 模板库治理

目标：先让模板成为可控资产。

任务：

- 增加模板库列表页。
- 增加模板主数据 JSON。
- 管理模板状态：draft / review / active / replaced / archived。
- 显示当前有效版本。
- 写模板状态变更审计。

### Phase T2 — 参数化生成 MVP

目标：可以生成草稿。

任务：

- 增加模板参数定义。
- 实现简单占位符替换。
- 支持 HTML/Markdown 预览。
- 生成结果保存到 `generated/`。
- 生成记录写入 `template_generation_runs.json`。
- 生成文件自动关联到 FileAdmin DocumentRecord / FileAttachment。

### Phase T3 — 国家规则与人工复核

目标：降低漏填和误用风险。

任务：

- 配置 JP/CN/SG 必填参数。
- 按国家默认币种和常用字段。
- 增加 `review_required` 和 `review_status`。
- 高风险模板必须复核后才能标记正式。
- 增加生成草稿 watermark/提示：`Draft - requires human review`。

### Phase T4 — 主数据联动

目标：减少重复输入。

任务：

- 从 MasterData 带入客户名称、地址、联系人、邮箱。
- 从 EmployeeAdmin 带入员工/候选人基础信息，但高敏字段受限。
- 从 User_admin session 带入 Entity / user / role。
- 从 Customer Billing 或合同台账带入付款条件和客户快照。

### Phase T5 — 输出格式升级

目标：贴近真实业务文件交付。

任务：

- 支持 DOCX 模板或 HTML-to-PDF 输出。
- 支持多语言模板包。
- 支持生成 PDF 草稿。
- 支持签署版上传后自动归档到同一文档包。

## 8. MVP 验收标准

- 至少有 9 个模板完成登记，其中至少 3 个处于 `active` 状态。
- 用户可按国家、语言、文件类型筛选模板。
- 用户可用一个 active 模板填写参数并生成草稿。
- 生成记录保留模板版本快照和参数快照。
- 生成文件能在 FileAdmin 文档详情页作为附件查看/下载。
- 所有模板创建、激活、生成、下载、复核、归档动作写审计。
- JP/CN/SG 每个国家至少跑通一个模板生成 UAT。
- 生成页面明确提示：系统生成的是草稿，必须人工确认后才能外发或签署。

## 9. 风险与控制

| 风险 | 控制 |
|---|---|
| 旧模板误用 | 只有 active/current 模板可生成；旧模板 archived/replaced |
| 法律条款不适用 | 激活前必须本地 HR/Legal/业务负责人确认 |
| 参数填错 | 必填校验、国家规则、预览确认 |
| 个人信息泄露 | 最小化参数、限制高敏字段、下载/生成审计 |
| 生成文件被当正式文件直接发送 | 草稿水印/提示、复核状态、权限控制 |
| 多国家模板混用 | country_code + entity_scope + language + business_line 联合筛选 |
| 模板版本不可追溯 | 生成记录保存模板版本和参数快照 |

## 10. 推荐下一步

1. 先确认第一批模板清单和优先级。
2. 将现有模板文件放入 `fileadmin/templates/`，按国家/业务线归类。
3. 为每个模板定义参数清单。
4. 选择一个低风险模板做 POC，例如 SG NDA 或 JP Offer Letter 草稿。
5. 再扩展到猎头合同和派遣合同。
6. 派遣合同、劳动合同类模板在上线前必须经过业务/法务确认。
