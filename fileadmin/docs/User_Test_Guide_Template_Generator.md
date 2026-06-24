# FileAdmin 用户测试文档 — 模板生成与文件管理

Last updated: 2026-06-24

## 1. 测试目的

验证 FileAdmin 当前版本是否满足以下目标：

1. 中 / 日 / 英三语界面可切换，核心导航、按钮、提示和 Template Generator 页面可读。
2. FileAdmin 页面顶部能显示当前登录用户和当前法人 / Entity。
3. FileAdmin 页面顶部有明显的“返回主 Portal / Portalへ戻る / Back to Portal”入口。
4. 系统建议标准模板可完成流程测试：选择模板、填写参数、生成草稿、进入 FileAdmin 文件台账、下载、review、归档、审计。
5. 生成的模板文件仅作为 workflow-test 草稿，不被误认为正式公司批准模板。

## 2. 测试范围

### 2.1 本轮包含

- FileAdmin 登录后页面导航。
- 语言切换：中文、日文、英文。
- 当前用户和 Entity 显示。
- 返回 TACAI Portal。
- 文档台账基本浏览。
- Template Generator：JP / CN / SG Offer Letter 系统建议模板。
- 生成文件保存为 FileAdmin DocumentRecord + FileAttachment。
- 生成记录 review status 更新。
- 下载生成文件。
- 归档生成文档。
- Audit log 检查。

### 2.2 本轮不包含

- 正式公司模板审批。
- 法务最终条款确认。
- Word / PDF 高保真格式输出。
- 电子签名流程。
- 邮件发送。
- OCR / AI 自动抽取。

## 3. 测试准备

### 3.1 服务准备

启动 Portal / User_admin / FileAdmin 所需服务。FileAdmin 默认端口：

```bash
python3 /Users/terencewang/Documents/claude-project/fileadmin/backend/app.py --host 127.0.0.1 --port 8011
```

健康检查：

```bash
curl -s http://127.0.0.1:8011/health
```

期望：返回 `OK`。

### 3.2 测试账号建议

建议至少使用以下角色测试：

| 测试角色 | 目的 |
|---|---|
| System Admin | 验证完整权限流程 |
| HR Manager | 验证 HR / Offer Letter 常规使用流程 |
| Finance / Manager | 验证是否能查看、下载或受权限限制 |
| 无 FileAdmin 权限用户 | 验证拒绝访问 |

测试账号以 User_admin 中实际配置为准。

### 3.3 测试数据

本轮可使用虚拟数据，避免输入真实个人敏感信息。

建议示例：

| 字段 | 示例 |
|---|---|
| Company Name | TAC Test KK / TAC China Test / TAC SG Test |
| Candidate Name | Test Candidate JP / Test Candidate CN / Test Candidate SG |
| Candidate Email | test.candidate@example.com |
| Position Title | Recruitment Consultant / HR Consultant |
| Start Date | 2026-07-01 |
| Work Location | Tokyo / Shanghai / Singapore |
| Salary Amount | 5000000 / 300000 / 90000 |
| Currency | JPY / CNY / SGD |
| Probation Period | 3 months |
| Response Deadline | 2026-06-30 |
| Hiring Manager Name | Test Manager |

## 4. 测试流程总览

```text
登录 Portal
  ↓
进入 FileAdmin
  ↓
确认当前用户、Entity、返回 Portal 按钮
  ↓
切换中文 / 日文 / 英文
  ↓
进入 Templates
  ↓
选择 JP / CN / SG 系统建议模板
  ↓
填写参数并生成草稿
  ↓
打开生成记录和 FileAdmin 文档详情
  ↓
下载生成文件
  ↓
更新 Review Status
  ↓
查看 Audit Log
  ↓
归档生成文档
  ↓
返回 Portal
```

## 5. 详细测试用例

### TC-01：从 Portal 进入 FileAdmin

| 项目 | 内容 |
|---|---|
| 前提 | 用户已登录 Portal，并拥有 FileAdmin 权限 |
| 步骤 | 1. 打开 TACAI Portal。2. 点击 FileAdmin 模块。 |
| 期望结果 | 进入 FileAdmin Dashboard；页面顶部显示 FileAdmin 标题、导航、语言切换、当前用户、当前 Entity、返回 Portal 按钮。 |
| 通过标准 | 能正常进入，无 403/500 错误。 |

### TC-02：当前用户显示

| 项目 | 内容 |
|---|---|
| 前提 | 已进入 FileAdmin |
| 步骤 | 查看页面顶部右侧用户信息区域。 |
| 期望结果 | 显示当前用户名称，以及当前法人 / Entity；中文显示“当前用户 / 当前法人”，日文显示“現在のユーザー / 現在の法人”，英文显示“Current User / Current Entity”。 |
| 通过标准 | 用户名与登录账号一致；Entity 信息不为空时正确显示。 |

### TC-03：返回 TACAI Portal

| 项目 | 内容 |
|---|---|
| 前提 | 已进入 FileAdmin 任意页面 |
| 步骤 | 点击顶部“返回主 Portal / Portalへ戻る / Back to Portal”。 |
| 期望结果 | 返回 Portal Dashboard。 |
| 通过标准 | 不丢失登录状态；返回 URL 正确。 |

### TC-04：三语切换

| 项目 | 内容 |
|---|---|
| 前提 | 已进入 FileAdmin |
| 步骤 | 依次点击 中文 / 日本語 / English。 |
| 期望结果 | 导航、页面标题、关键按钮、Template Generator 页面提示切换到对应语言。 |
| 通过标准 | 切换后页面可读，URL 或 cookie 保持语言选择；刷新后语言保持。 |

### TC-05：模板库显示

| 项目 | 内容 |
|---|---|
| 前提 | 用户拥有 `fileadmin.view` 权限 |
| 步骤 | 打开 `/templates`。 |
| 期望结果 | 显示 JP / CN / SG Offer Letter 系统建议标准模板；每条显示国家、语言、业务线、状态、system-suggested、review-required、not formal approved。 |
| 通过标准 | 三个模板均可见；有权限用户能看到 Generate Draft 按钮。 |

### TC-06：生成 JP Offer Letter 草稿

| 项目 | 内容 |
|---|---|
| 前提 | 用户拥有 `fileadmin.create` 和 `fileadmin.upload` 权限 |
| 步骤 | 1. 进入 `/templates`。2. 选择 JP Offer Letter。3. 填写必填参数。4. 点击 Generate Draft and Save to FileAdmin。 |
| 期望结果 | 生成成功并跳转到 generation run detail；显示 pending review；可打开 FileAdmin Document。 |
| 数据检查 | `documents.json`、`document_records.json`、`file_attachments.json`、`document_versions.json`、`template_generation_runs.json` 均新增相关记录。 |
| 通过标准 | 文件被保存到 `attachments/template_generated/JP/...`；文档状态为 draft；review_status 为 pending。 |

### TC-07：生成 CN Offer Letter 草稿

同 TC-06，但选择 CN Offer Letter，语言应为中文，默认币种 CNY。

### TC-08：生成 SG Offer Letter 草稿

同 TC-06，但选择 SG Offer Letter，语言应为英文，默认币种 SGD。

### TC-09：必填参数校验

| 项目 | 内容 |
|---|---|
| 前提 | 打开任一模板生成页 |
| 步骤 | 删除 Candidate Name 或 Start Date 等必填字段后提交。 |
| 期望结果 | 系统提示缺少必填参数；不创建 document、attachment、generation run。 |
| 通过标准 | 没有半成品记录或空文件产生。 |

### TC-10：打开生成文档详情

| 项目 | 内容 |
|---|---|
| 前提 | 已成功生成模板草稿 |
| 步骤 | 在 generation run detail 点击 Open FileAdmin Document。 |
| 期望结果 | 文档详情页显示 Template Generation 面板，包含 generation_id、template code、template version、review status、source type、formal approval later。 |
| 通过标准 | 用户能清楚看到该文件是系统建议草稿，非正式批准模板。 |

### TC-11：下载生成草稿

| 项目 | 内容 |
|---|---|
| 前提 | 已成功生成模板草稿，用户拥有 `fileadmin.download` 权限 |
| 步骤 | 点击 Download Generated Draft 或文档详情页附件 Download。 |
| 期望结果 | 下载 HTML 文件；文件内容包含 DRAFT / NOT FORMAL APPROVED 警示。 |
| 通过标准 | 下载成功；audit log 中出现 `file_downloaded`。 |

### TC-12：更新 Review Status

| 项目 | 内容 |
|---|---|
| 前提 | 用户拥有 `fileadmin.upload` 或 `fileadmin.archive` 权限 |
| 步骤 | 在 generation run detail 将 review status 改为 `reviewed` 或 `approved_generated`，填写 review notes 后提交。 |
| 期望结果 | generation run review_status 更新；文档详情 Template Generation 面板同步显示；附件状态对应更新。 |
| 通过标准 | audit log 中出现 `template_review_status_changed`。 |

### TC-13：归档生成文档

| 项目 | 内容 |
|---|---|
| 前提 | 用户拥有 `fileadmin.archive` 权限 |
| 步骤 | 在生成文档详情页填写 Archive Reason 并归档。 |
| 期望结果 | 文档状态变为 archived；文件不物理删除；generation run status 同步为 archived。 |
| 通过标准 | audit log 中出现 `document_archived` 和 `template_run_archived`。 |

### TC-14：无权限访问

| 项目 | 内容 |
|---|---|
| 前提 | 使用无 FileAdmin 权限账号 |
| 步骤 | 访问 `/dashboard` 或 `/templates`。 |
| 期望结果 | 系统重定向登录或显示 Forbidden。 |
| 通过标准 | 无权限用户不能查看模板、下载文件或生成文件。 |

### TC-15：语言下的返回 Portal 和用户显示

| 项目 | 内容 |
|---|---|
| 前提 | 分别切换到 zh / ja / en |
| 步骤 | 检查顶部用户显示和 Portal 返回按钮文案。 |
| 期望结果 | zh：返回主 Portal、当前用户、当前法人；ja：Portalへ戻る、現在のユーザー、現在の法人；en：Back to Portal、Current User、Current Entity。 |
| 通过标准 | 文案正确，点击行为一致。 |

## 6. 测试记录表

| Case ID | 测试人 | 日期 | 环境 | 结果 Pass/Fail | 问题描述 | 截图/证据 | 修复后复测 |
|---|---|---|---|---|---|---|---|
| TC-01 |  |  |  |  |  |  |  |
| TC-02 |  |  |  |  |  |  |  |
| TC-03 |  |  |  |  |  |  |  |
| TC-04 |  |  |  |  |  |  |  |
| TC-05 |  |  |  |  |  |  |  |
| TC-06 |  |  |  |  |  |  |  |
| TC-07 |  |  |  |  |  |  |  |
| TC-08 |  |  |  |  |  |  |  |
| TC-09 |  |  |  |  |  |  |  |
| TC-10 |  |  |  |  |  |  |  |
| TC-11 |  |  |  |  |  |  |  |
| TC-12 |  |  |  |  |  |  |  |
| TC-13 |  |  |  |  |  |  |  |
| TC-14 |  |  |  |  |  |  |  |
| TC-15 |  |  |  |  |  |  |  |

## 7. 测试建议

1. **先用虚拟数据测试**：不要在 workflow-test 阶段输入真实候选人身份证号、真实薪资附件或客户机密合同。
2. **每个国家至少跑一次完整流程**：JP、CN、SG 各生成一份 Offer Letter 草稿。
3. **截图留证**：建议保存模板库、生成页、生成结果、文档详情、下载文件内容、audit log 的截图。
4. **重点看警示是否明显**：所有生成文件都应清楚显示 system-suggested / not formal approved / review required。
5. **测试不同角色**：System Admin、HR Manager、Finance、Manager、无权限用户分别测试。
6. **记录模板调整意见**：UAT 后把正式公司现用模板和系统建议模板的差异整理出来，作为下一阶段正式模板合并和审批输入。

## 8. UAT 通过标准

本轮 UAT 通过条件：

- 三语切换可用，核心页面无明显中文残留误导（模板正式名称除外）。
- 当前用户和当前 Entity 在 FileAdmin 顶部清楚显示。
- 返回 TACAI Portal 按钮可用。
- JP / CN / SG 三个模板均可生成草稿。
- 生成草稿进入 FileAdmin 文档台账和附件表。
- 下载、review、归档和 audit 均可追踪。
- 用户明确理解：当前模板不是正式批准模板，只用于流程测试。
