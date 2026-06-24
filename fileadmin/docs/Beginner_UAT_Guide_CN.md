# FileAdmin 新手用户测试指南（中文版）

Last updated: 2026-06-24

> 适用对象：第一次使用 FileAdmin / TACAI Portal 的测试人员。  
> 测试目标：按照本指南一步一步完成 FileAdmin 文件管理和模板生成测试，并记录结果。  
> 注意：当前 JP / CN / SG Offer Letter 模板是系统建议标准草稿，只用于流程测试，不是公司正式批准模板。

---

## 1. 测试前准备

### 1.1 你需要准备什么

请提前确认你有：

- 一台可以访问 TACAI 系统的电脑。
- 一个测试账号。
- 账号已经有 FileAdmin 权限。
- 浏览器：Chrome / Edge / Safari 均可。
- 测试记录方式：Excel、Notion、Word、截图文件夹都可以。

### 1.2 推荐测试账号

如果你不知道使用哪个账号，请先使用管理员或 HR Manager 测试账号。

| 角色 | 用途 |
|---|---|
| System Admin | 可以测试完整流程 |
| HR Manager | 可以测试 Offer Letter 生成和文档管理 |
| Finance / Manager | 用来检查普通管理角色权限是否合适 |
| 无 FileAdmin 权限用户 | 用来确认无权限用户不能访问 |

### 1.3 测试数据建议

请不要输入真实候选人身份证号、真实工资单、真实客户合同等敏感信息。  
可以使用下面的虚拟数据。

| 字段 | 日本测试示例 | 中国测试示例 | 新加坡测试示例 |
|---|---|---|---|
| Company Name | TAC Test KK | TAC China Test Co., Ltd. | TAC Singapore Test Pte. Ltd. |
| Candidate Name | Test Candidate JP | Test Candidate CN | Test Candidate SG |
| Candidate Email | jp.test@example.com | cn.test@example.com | sg.test@example.com |
| Position Title | Recruitment Consultant | HR Consultant | Talent Consultant |
| Start Date | 2026-07-01 | 2026-07-01 | 2026-07-01 |
| Work Location | Tokyo / Remote | Shanghai / Remote | Singapore / Hybrid |
| Salary Amount | 5000000 | 300000 | 90000 |
| Currency | JPY | CNY | SGD |
| Probation Period | 3 months | 按公司政策和法律审核 | 3 months |
| Response Deadline | 2026-06-30 | 2026-06-30 | 2026-06-30 |
| Hiring Manager Name | Test Manager | Test Manager | Test Manager |

---

## 2. 测试结果记录表

请复制下面表格到你的测试记录文件中。

| 编号 | 测试内容 | 测试结果 Pass / Fail | 问题说明 | 截图文件名 | 备注 |
|---|---|---|---|---|---|
| 01 | 登录 Portal |  |  |  |  |
| 02 | 进入 FileAdmin |  |  |  |  |
| 03 | 查看当前用户和当前法人 |  |  |  |  |
| 04 | 返回 Portal 按钮 |  |  |  |  |
| 05 | 中文 / 日文 / 英文切换 |  |  |  |  |
| 06 | 查看 Templates 模板库 |  |  |  |  |
| 07 | 生成 JP Offer Letter 草稿 |  |  |  |  |
| 08 | 生成 CN Offer Letter 草稿 |  |  |  |  |
| 09 | 生成 SG Offer Letter 草稿 |  |  |  |  |
| 10 | 下载生成文件 |  |  |  |  |
| 11 | 更新 Review Status |  |  |  |  |
| 12 | 查看 Audit Logs |  |  |  |  |
| 13 | 归档生成文档 |  |  |  |  |
| 14 | 无权限用户测试 |  |  |  |  |
| 15 | 总体评价 |  |  |  |  |

---

## 3. 测试步骤 01：登录 TACAI Portal

### 操作步骤

1. 打开浏览器。
2. 输入 TACAI Portal 地址。  
   - 本机测试通常类似：`http://127.0.0.1:8005`
   - 同 Wi-Fi 测试通常类似：`http://<你的电脑IP>:8005`
3. 进入登录页面。
4. 输入测试账号和密码。
5. 点击登录。

### 期望结果

你应该看到 Portal 首页 / Dashboard。页面中应该有多个模块入口。

### 通过标准

- 能成功登录。
- 没有 500 错误。
- 没有一直跳回登录页。

### 截图建议

截图保存为：`01_portal_login_success.png`

---

## 4. 测试步骤 02：进入 FileAdmin

### 操作步骤

1. 在 Portal Dashboard 中找到 FileAdmin / 文件管理模块。
2. 点击 FileAdmin。
3. 等待页面打开。

### 期望结果

进入 FileAdmin Dashboard。顶部应该看到：

- FileAdmin 标题。
- 导航菜单。
- 返回主 Portal 按钮。
- 语言切换按钮。
- 当前用户信息。

### 通过标准

- 能进入 FileAdmin 页面。
- 页面不是空白。
- 没有权限错误。

### 如果失败怎么办

| 现象 | 可能原因 | 处理建议 |
|---|---|---|
| 显示 Forbidden | 当前账号没有 FileAdmin 权限 | 请管理员检查 User_admin 权限 |
| 页面打不开 | FileAdmin 服务未启动 | 请开发/管理员启动 FileAdmin |
| 跳回登录页 | 登录状态失效 | 重新登录 Portal |

### 截图建议

截图保存为：`02_fileadmin_dashboard.png`

---

## 5. 测试步骤 03：确认当前用户和当前法人

### 操作步骤

1. 看 FileAdmin 页面顶部右侧。
2. 找到当前用户显示区域。
3. 检查是否显示：
   - 当前用户。
   - 当前法人 / Entity。

### 期望结果

中文界面下应显示类似：

```text
当前用户
UAT User
当前法人: TAKK - TAC Japan KK
```

### 通过标准

- 用户名和当前登录账号一致。
- Entity 信息正确，或没有 Entity 时显示“无当前法人”。

### 截图建议

截图保存为：`03_current_user_entity.png`

---

## 6. 测试步骤 04：测试返回 Portal 按钮

### 操作步骤

1. 在 FileAdmin 页面顶部找到“返回主 Portal”。
2. 点击它。
3. 确认是否返回 Portal Dashboard。
4. 再从 Portal 回到 FileAdmin。

### 期望结果

可以从 FileAdmin 返回 Portal，并且登录状态不会丢失。

### 通过标准

- 点击后能回到 Portal。
- 不需要重新登录，或重新登录后能正常回到系统。

### 截图建议

截图保存为：`04_back_to_portal.png`

---

## 7. 测试步骤 05：测试中文 / 日文 / 英文切换

### 操作步骤

1. 进入 FileAdmin。
2. 点击顶部语言按钮：中文。
3. 检查导航和用户显示。
4. 点击：日本語。
5. 检查导航和用户显示。
6. 点击：English。
7. 检查导航和用户显示。

### 期望结果

| 语言 | 返回 Portal | 当前用户 | 当前法人 |
|---|---|---|---|
| 中文 | 返回主 Portal | 当前用户 | 当前法人 |
| 日文 | Portalへ戻る | 現在のユーザー | 現在の法人 |
| 英文 | Back to Portal | Current User | Current Entity |

### 通过标准

- 三种语言都能切换。
- 页面不会报错。
- 主要导航和按钮能读懂。

### 截图建议

- `05_language_zh.png`
- `05_language_ja.png`
- `05_language_en.png`

---

## 8. 测试步骤 06：查看 Templates 模板库

### 操作步骤

1. 在 FileAdmin 顶部菜单点击“模板生成 / Templates”。
2. 查看模板列表。
3. 检查是否有以下模板：
   - Japan Offer Letter
   - China Offer Letter
   - Singapore Offer Letter

### 期望结果

模板列表中应显示 JP / CN / SG 三个系统建议标准模板。

每个模板都应该能看出：

- system-suggested standard。
- not formal approved。
- requires human review。
- active / current。

### 通过标准

- 三个模板都能看到。
- 有权限账号能看到 Generate Draft 按钮。
- 页面有明确提示：当前模板不是正式批准模板。

### 截图建议

截图保存为：`06_template_library.png`

---

## 9. 测试步骤 07：生成 JP Offer Letter 草稿

### 操作步骤

1. 在 Templates 页面找到 JP Offer Letter。
2. 点击 Generate Draft。
3. 进入生成表单。
4. 填写测试数据：

| 字段 | 输入 |
|---|---|
| Company Name | TAC Test KK |
| Candidate Name | Test Candidate JP |
| Candidate Email | jp.test@example.com |
| Position Title | Recruitment Consultant |
| Start Date | 2026-07-01 |
| Work Location | Tokyo / Remote |
| Salary Amount | 5000000 |
| Currency | JPY |
| Probation Period | 3 months |
| Response Deadline | 2026-06-30 |
| Hiring Manager Name | Test Manager |
| Additional Notes | UAT test only |

5. 点击 Generate Draft and Save to FileAdmin。

### 期望结果

系统跳转到 Template Generation Run 页面。你应该看到：

- Generation ID。
- Template Code。
- Status。
- Review Status = pending。
- Open FileAdmin Document 按钮。
- Download Generated Draft 按钮。

### 通过标准

- 草稿生成成功。
- 没有报错。
- 能打开 FileAdmin Document。

### 截图建议

- `07_jp_generate_form.png`
- `07_jp_generation_success.png`

---

## 10. 测试步骤 08：生成 CN Offer Letter 草稿

### 操作步骤

1. 回到 Templates 页面。
2. 找到 CN Offer Letter。
3. 点击 Generate Draft。
4. 填写测试数据：

| 字段 | 输入 |
|---|---|
| Company Name | TAC China Test Co., Ltd. |
| Candidate Name | Test Candidate CN |
| Candidate Email | cn.test@example.com |
| Position Title | HR Consultant |
| Start Date | 2026-07-01 |
| Work Location | Shanghai / Remote |
| Salary Amount | 300000 |
| Currency | CNY |
| Probation Period | 按公司政策和法律审核 |
| Response Deadline | 2026-06-30 |
| Hiring Manager Name | Test Manager |
| Additional Notes | UAT test only |

5. 点击 Generate Draft and Save to FileAdmin。

### 期望结果

成功生成中文 Offer Letter 草稿，并进入 generation run detail。

### 通过标准

- 默认币种或填写币种为 CNY。
- 生成内容中有中文模板内容。
- 有非正式模板警示。

### 截图建议

截图保存为：`08_cn_generation_success.png`

---

## 11. 测试步骤 09：生成 SG Offer Letter 草稿

### 操作步骤

1. 回到 Templates 页面。
2. 找到 SG Offer Letter。
3. 点击 Generate Draft。
4. 填写测试数据：

| 字段 | 输入 |
|---|---|
| Company Name | TAC Singapore Test Pte. Ltd. |
| Candidate Name | Test Candidate SG |
| Candidate Email | sg.test@example.com |
| Position Title | Talent Consultant |
| Start Date | 2026-07-01 |
| Work Location | Singapore / Hybrid |
| Salary Amount | 90000 |
| Currency | SGD |
| Probation Period | 3 months |
| Response Deadline | 2026-06-30 |
| Hiring Manager Name | Test Manager |
| Additional Notes | UAT test only |

5. 点击 Generate Draft and Save to FileAdmin。

### 期望结果

成功生成英文 Offer Letter 草稿，并进入 generation run detail。

### 通过标准

- 默认币种或填写币种为 SGD。
- 生成内容中有英文模板内容。
- 有非正式模板警示。

### 截图建议

截图保存为：`09_sg_generation_success.png`

---

## 12. 测试步骤 10：下载生成文件

### 操作步骤

1. 在 Template Generation Run 页面点击 Download Generated Draft。
2. 或者进入 FileAdmin Document 页面，在附件列表中点击 Download。
3. 打开下载的 HTML 文件。

### 期望结果

下载文件中应包含醒目警示：

```text
DRAFT - SYSTEM-SUGGESTED STANDARD - REQUIRES HUMAN REVIEW - NOT A FORMAL APPROVED TEMPLATE
```

### 通过标准

- 文件能下载。
- 文件能打开。
- 文件内容是刚刚输入的测试数据。
- 文件明确显示不是正式批准模板。

### 截图建议

截图保存为：`10_download_generated_draft.png`

---

## 13. 测试步骤 11：更新 Review Status

### 操作步骤

1. 回到 Template Generation Run 页面。
2. 找到 Review Generated Draft 区域。
3. 将 Review Status 从 `pending` 改成：
   - `reviewed`，或
   - `approved_generated`
4. 在 Review Notes 中输入：

```text
UAT reviewed by tester. This is not formal template approval.
```

5. 点击 Update Review。

### 期望结果

页面刷新后 Review Status 更新成功。

### 通过标准

- Review Status 显示新状态。
- 打开 FileAdmin Document，Template Generation 面板中状态也同步变化。

### 截图建议

截图保存为：`11_review_status_updated.png`

---

## 14. 测试步骤 12：查看 Audit Logs

### 操作步骤

1. 在顶部导航点击 Audit / 审计。
2. 查看最新 audit log。
3. 搜索或观察是否出现以下事件：
   - document_created
   - template_generated
   - generated_file_created
   - file_downloaded
   - template_review_status_changed

### 期望结果

操作记录可以在审计日志中看到。

### 通过标准

- 审计日志有时间、action、record、user。
- 不应允许删除 audit log。

### 截图建议

截图保存为：`12_audit_logs.png`

---

## 15. 测试步骤 13：归档生成文档

### 操作步骤

1. 打开刚生成的 FileAdmin Document。
2. 滚动到 Archive Document 区域。
3. 在 Archive Reason 输入：

```text
UAT cleanup after template generation test.
```

4. 点击 Archive Only。

### 期望结果

文档被归档，但文件和审计记录保留。

### 通过标准

- 文档状态变为 archived。
- 不会物理删除文件。
- Generation Run 状态同步为 archived。
- Audit Log 有 document_archived / template_run_archived。

### 截图建议

截图保存为：`13_archive_document.png`

---

## 16. 测试步骤 14：无权限用户测试

### 操作步骤

1. 退出当前账号。
2. 使用无 FileAdmin 权限的测试账号登录。
3. 尝试打开 FileAdmin。
4. 尝试直接访问 `/templates`。

### 期望结果

无权限用户不能访问 FileAdmin 或模板库。

### 通过标准

- 显示 Forbidden，或跳转登录 / 权限不足页面。
- 不能下载生成文件。
- 不能生成模板。

### 截图建议

截图保存为：`14_no_permission.png`

---

## 17. 测试步骤 15：填写总体评价

请测试人员回答以下问题：

1. 你是否能不依赖开发人员，自己完成 JP / CN / SG 模板生成？
2. 页面上是否清楚显示“当前用户”和“当前法人”？
3. “返回主 Portal”是否容易找到？
4. 语言切换是否足够清楚？
5. 你是否理解当前模板不是正式批准模板？
6. 生成的文件是否容易在 FileAdmin 中找到？
7. Review Status 是否容易理解？
8. 你认为下一版最需要改善什么？

建议记录格式：

```text
测试人：
测试日期：
账号角色：
总体结果：Pass / Fail / Pass with Issues
主要问题：
建议改善：
是否建议进入下一阶段正式模板合并：Yes / No
```

---

## 18. 新手常见问题

### Q1：我看不到 FileAdmin 入口怎么办？

可能是账号没有权限，或 Portal 配置中没有显示 FileAdmin。请联系管理员确认 User_admin 权限。

### Q2：我能进入 FileAdmin，但看不到 Generate Draft 按钮怎么办？

可能缺少 `fileadmin.create` 或 `fileadmin.upload` 权限。请管理员检查账号权限。

### Q3：生成文件后在哪里找？

生成成功后会进入 Template Generation Run 页面。点击 Open FileAdmin Document 可以打开文档台账记录。也可以在 Documents / 文件台账中搜索候选人姓名或标题。

### Q4：生成的文件可以直接发给候选人吗？

不可以。当前模板是 workflow-test 草稿，不是正式批准模板。必须经过 HR / 法务 / 业务负责人确认，并在下一阶段形成正式模板后才能对外使用。

### Q5：为什么文件是 HTML？

当前 MVP 先用 HTML 草稿验证流程。后续正式版本可以考虑 Word / PDF 输出。

### Q6：归档是不是删除？

不是。归档只是把状态改为 archived，文件和 audit log 仍保留。

---

## 19. UAT 通过标准

本轮测试可以认为通过，如果满足：

- 新手能根据本指南完成登录、进入 FileAdmin、语言切换、模板生成、下载、review、归档。
- 顶部能清楚看到当前用户和当前法人。
- 顶部能清楚找到返回 Portal 按钮。
- JP / CN / SG 三个模板至少各成功生成一次。
- 生成文件都进入 FileAdmin 文档台账。
- 下载文件包含非正式模板警示。
- Audit Logs 能看到关键操作记录。
- 测试人员理解当前模板只用于流程测试，不是正式批准模板。

---

## 20. 下一阶段建议

UAT 完成后，请收集：

1. 公司当前正式 Offer Letter 模板。
2. 各国家实际业务条款差异。
3. HR / 法务 / 业务负责人修改意见。
4. 字段是否足够，例如客户名称、地址、候选人地址、邮箱、薪资结构、奖金、福利、试用期、工作地点等。
5. 是否需要 Word / PDF 输出。
6. 是否需要审批流：draft → reviewed → approved template → active。

收集后，再把“现在正式使用的模板”和“系统建议模板”合并成最终测试版。
