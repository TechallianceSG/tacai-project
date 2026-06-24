# FileAdmin 实施步骤规划

Last updated: 2026-06-24

## 0. 当前进度（2026-06-24）

Phase 5 可复用模板自动生成已完成第一阶段 MVP：

- [x] 新增 Template Generator 页面与路由。
- [x] 新增 `document_templates.json`, `template_parameters.json`, `template_country_rules.json`, `template_generation_runs.json`。
- [x] 首批种子模板：JP / CN / SG Offer Letter 系统建议标准草稿。
- [x] 输入参数后生成 HTML 草稿，并自动进入 FileAdmin 文档台账和附件管理。
- [x] 保存模板版本快照、参数快照、生成用户、生成时间和 review status。
- [x] 生成草稿可下载、可 review、可随 FileAdmin 文档归档，并写入 audit log。

后续：正式公司现用模板需在流程验证后，与系统建议模板合并并审批为最终版本。

## 1. 推荐执行顺序

```text
Phase 0 规划与目录
  ↓
Phase 1 本地文件台账 MVP
  ↓
Phase 2 合同提醒 + 版本管理稳定化
  ↓
Phase 3 Portal / User_admin 集成
  ↓
Phase 4 模板治理 / 合同治理增强
  ↓
Phase 5 可复用模板自动生成
  ↓
Phase 6 OCR/AI 辅助和跨模块关联
```

## 2. Phase 0 — 当前准备阶段

### 目标

建立项目骨架和业务设计，先统一“做什么、不做什么、怎样上线”。

### 任务

- [x] 创建 `fileadmin/` 目录。
- [x] 创建 `backend/`, `database/`, `attachments/`, `templates/`, `audit/`, `docs/`, `memory/` 等目录。
- [x] 编写 README。
- [x] 编写项目计划。
- [x] 编写架构/业务设计。
- [x] 编写数据 schema 初稿。
- [x] 编写实施步骤。

### 输出物

- `fileadmin/README.md`
- `fileadmin/docs/Project_Plan.md`
- `fileadmin/docs/Architecture_Design.md`
- `fileadmin/docs/Data_Schema.md`
- `fileadmin/docs/Implementation_Steps.md`

## 3. Phase 1 — 本地文件台账 MVP

### 目标

用最少功能实现企业文件可控管理：登记、上传、版本、到期提醒、审计。

### 建议实现步骤

1. **初始化 JSON 数据文件**
   - `database/document_records.json` — 文档记录 / 合同包主记录
   - `database/file_attachments.json` — 同一记录下的多个实际文件附件
   - `database/folders.json`
   - `database/document_categories.json`
   - `database/reminders.json`
   - `database/audit_logs.json`

2. **实现基础 Web App**
   - `backend/app.py`
   - `/health`
   - `/` dashboard
   - `/documents`
   - `/documents/new`
   - `/documents/<document_id>`
   - `/documents/<document_id>/versions/new`
   - `/reminders`
   - `/audit`

3. **文件登记表单**
   - 标题、分类、业务线、客户/供应商/项目、Entity、负责人。
   - 文件状态、保密等级、语言、合同期间、提醒规则。
   - 是否为对外模板、是否当前有效版本。

4. **多文件上传与版本管理**
   - 一个 `document_id` 下允许上传多个实际文件。
   - 上传原始文件到 `attachments/<category>/<document_id>/`。
   - 每个文件附件必须单独记录标题、说明、文件类型、文件角色、版本号、是否当前有效、是否正式签署版。
   - 计算 SHA-256 hash。
   - 记录文件大小、原始文件名、上传用户、上传时间。
   - 新版本不得覆盖旧版本；同一文件角色只允许一个当前有效附件。

5. **到期提醒页面**
   - 按剩余天数分组：已过期、7 天内、14 天内、30 天内、60 天内、90 天内。
   - 显示负责人、客户、合同类型、到期日、提醒状态。

6. **审计日志**
   - 新增文件、上传版本、修改元数据、归档、恢复、提醒确认都要记录。
   - 审计字段必须包含：`module`, `record_id`, `action`, `user`, `timestamp`, `before_value`, `after_value`。

### 验收标准

- 可以登记 10 条文档记录 / 合同包并上传附件。
- 可以在同一文档记录下上传至少 3 个不同文件，并分别填写描述。
- 可以为同一文件角色上传至少 2 个版本。
- Dashboard 显示临近到期合同。
- 审计日志能看到所有状态变更。
- `python3 -m py_compile backend/app.py` 通过。
- `/health` 返回 OK。

## 4. Phase 2 — 合同提醒与版本治理稳定化

### 目标

让 FileAdmin 真正支撑合同到期与对外文书版本治理。

### 任务

- 增加合同提醒规则：90/60/30/14/7 天，支持单个合同自定义。
- 增加提醒确认：负责人确认“已联系客户/已续约/不续约/待确认”。
- 增加合同状态流转：draft → active → expiring → expired → renewed / terminated / archived。
- 增加模板状态流转：draft → review → approved → active → replaced → archived。
- 增加“当前有效模板”视图。
- 增加基础 CSV 导出：合同台账、到期列表、模板版本清单。

### 验收标准

- 任意合同可看到下一次提醒日和提醒历史。
- 对外模板只能有一个 `active_current` 版本。
- 过期合同不会从系统消失，只进入 expired/archived 状态。

## 5. Phase 3 — TACAI Portal / User_admin 集成

### 目标

FileAdmin 从独立本地 MVP 变成 TACAI Portal 内部模块。

### 任务

- 使用端口 `8011`。
- Portal 增加模块注册：FileAdmin / Document Management。
- User_admin 增加权限：
  - `fileadmin.access`
  - `fileadmin.view`
  - `fileadmin.manage`
  - `fileadmin.contracts.manage`
  - `fileadmin.templates.manage`
  - `fileadmin.audit.view`
- 后端读取 `tacai_session_id` 并调用 User_admin 验证。
- 使用 session 的 Entity context 做默认数据范围过滤。
- UI 风格对齐 TAC-timesheet / TACAI suite。

### 验收标准

- 没有登录时跳转 User_admin。
- 没有 `fileadmin.access` 时返回 403。
- 有权限用户可从 Portal 打开 FileAdmin。
- 审计记录当前用户和 Entity。

## 6. Phase 4 — 文件治理增强

### 目标

让系统更适合日本派遣、猎头和 IT 服务公司的日常运营。

### 任务

- 客户合同包页面：按客户聚合合同、订单、报价、NDA、交付物。
- 派遣合同包页面：基本契约、个别契约、通知书、抵触日/期间信息。
- IT 服务项目文件包：合同、注文、报价、验收、交付物。
- 猎头客户文件包：人材紹介契约、返金条款、候选人推荐协议。
- 模板库：按语言、业务线、版本、有效状态检索。

## 7. Phase 5 — 可复用模板自动生成

### 目标

支持日本、中国、新加坡高频业务模板的参数化生成，减少重复手工改写和旧模板误用。

### 任务

- 新增模板库：按国家、语言、业务线、Entity、文件类型、版本和状态管理模板。
- 新增模板参数定义：维护占位符、必填字段、字段标签、校验规则和数据来源提示。
- 实现简单模板替换：先支持 Markdown/HTML 草稿生成，后续再支持 DOCX/PDF。
- 新增生成记录：保存模板版本快照、参数快照、生成用户、生成时间和输出路径。
- 生成文件自动归档为 FileAdmin 的 DocumentRecord / FileAttachment。
- 配置 JP/CN/SG 国家规则：默认币种、必填参数、复核要求和高风险模板控制。
- 增加模板权限：`fileadmin.templates.view`, `fileadmin.templates.generate`, `fileadmin.templates.manage`, `fileadmin.templates.approve`, `fileadmin.templates.audit.view`。
- 所有模板创建、激活、生成、复核、下载、归档操作写审计。

### 第一批建议模板

- JP/CN/SG Offer Letter。
- JP/CN/SG Recruitment Agreement。
- JP Dispatch Basic Agreement。
- JP Dispatch Individual Agreement。
- SG/CN RPO 或 NDA，按实际业务优先级选择。

### 验收标准

- 至少 9 个模板完成登记，其中至少 3 个处于 active/current 状态。
- JP/CN/SG 每个国家至少跑通一个模板生成 UAT。
- 生成文件可在 FileAdmin 文档详情中作为附件查看/下载。
- 生成页面明确提示“草稿，需人工复核”。
- 高风险模板必须复核后才能标记正式。

详细计划见 `docs/Reusable_Template_Automation_Plan.md`。

## 8. Phase 6 — AI/OCR 辅助

### 目标

减少人工录入工作量，但保持人工最终确认。

### 任务

- 添加 OCR/文本抽取草稿表。
- 根据合同文件建议客户名、合同期间、自动更新、通知期限、金额、付款条件。
- 自动生成文档摘要。
- 新旧版本差异比较。
- 风险提示：自动续约、返金、违约金、再委托、个人信息、保密期限。

### 安全边界

- 不默认把正式合同全文发送到外部服务。
- AI 字段必须显示来源与置信度。
- AI 草稿必须经人工确认。

## 9. 30 天轻量上线计划

| 时间 | 重点 | 输出 |
|---|---|---|
| 第 1 周 | 数据 schema + MVP Web App 骨架 | `/health`, dashboard, 文件列表 |
| 第 2 周 | 文件登记 + 上传 + 版本 | 可录入真实合同和模板 |
| 第 3 周 | 到期提醒 + 审计 + CSV | 可用于合同管理会议 |
| 第 4 周 | UAT + 字段调整 + Portal 集成准备 | 内部试上线 checklist |

## 10. 第一批试录入建议

- 3 份派遣客户基本契约。
- 3 份个别契约/注文书。
- 2 份猎头客户契约。
- 1 份 IT 服务/SES 合同。
- 1 份 RPO/SLA 合同。
- 5 个对外模板：会社案内、报价书、NDA、服务说明书、候选人推荐邮件模板。

## 11. 暂缓事项

- 客户外部文件共享门户。
- 大文件对象存储。
- 全文搜索引擎。
- 在线编辑 Office 文档。
- 复杂审批流引擎。
- 与 freee/Money Forward/Yayoi 等系统直接集成。
