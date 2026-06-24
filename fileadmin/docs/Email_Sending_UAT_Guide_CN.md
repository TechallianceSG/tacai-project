# FileAdmin 邮件发送 UAT 测试指南（中文版）

Last updated: 2026-06-24

## 1. 测试目的

验证 FileAdmin 在文件生成、确认后，可以通过系统创建邮件发送记录，并在默认 `dry_run` 模式下完成发送前检查、收件人确认、附件关联和审计留痕。

> 当前默认模式是 `dry_run`：不会真实发送邮件给客户或人选。只有显式配置 `FILEADMIN_EMAIL_SEND_MODE=smtp` 后才会真实发送。

## 2. 前提条件

1. FileAdmin 服务已启动。
2. 测试账号具备 FileAdmin 查看、下载、上传或归档权限。
3. 已有一个可以发送的文件：
   - 普通附件：`file_status` 为 `approved`、`active` 或 `signed`；或
   - Template Generator 生成文件：Review Status 已更新为 `approved_generated`。
4. 不使用真实客户或候选人邮箱，优先使用测试邮箱。

## 3. 测试流程

```text
生成或上传文件
  ↓
确认 / review 文件
  ↓
打开 FileAdmin Document Detail
  ↓
点击 Send Email
  ↓
填写收件人、主题、正文
  ↓
勾选合规确认
  ↓
创建 Email Sending Record
  ↓
查看 Email Detail
  ↓
查看 Audit Logs
```

## 4. 测试数据建议

| 字段 | 示例 |
|---|---|
| To | test.candidate@example.com |
| Cc | hr.test@example.com |
| Subject | Offer Letter - Test Candidate |
| Body | Dear Test Candidate, please find attached the offer letter draft for review. |
| Notes | UAT dry-run only |

## 5. 测试用例

### TC-EMAIL-01：确认未审核文件不能发送

1. 找一个 `draft` 或 `review` 状态文件。
2. 打开文档详情页。
3. 检查是否没有 Send Email 按钮，或直接访问 `/emails/new?...` 被拒绝。

期望：系统拒绝发送未确认文件。

### TC-EMAIL-02：确认 approved_generated 文件可以创建 dry-run 发送记录

1. 生成一份 Offer Letter。
2. 在 generation run detail 中将 Review Status 更新为 `approved_generated`。
3. 打开 FileAdmin Document。
4. 在附件列表点击 Send Email。
5. 填写 To、Subject、Body。
6. 勾选合规确认。
7. 提交。

期望：进入 Email Detail，状态为 `dry_run`。

### TC-EMAIL-03：收件人邮箱校验

1. 打开发送页面。
2. 在 To 输入 `wrong-email-format`。
3. 提交。

期望：系统报错，不创建发送记录。

### TC-EMAIL-04：未勾选合规确认不能发送

1. 打开发送页面。
2. 填写正常 To、Subject、Body。
3. 不勾选合规确认。
4. 提交。

期望：系统提示必须确认合规 checkbox。

### TC-EMAIL-05：查看邮件发送记录列表

1. 点击顶部 Emails / 邮件发送。
2. 查看邮件发送记录。

期望：可以看到刚创建的 dry-run 记录，包括状态、文档、收件人、主题和详情按钮。

### TC-EMAIL-06：查看 Audit Logs

1. 打开 Audit Logs。
2. 查找 `email_dry_run_created`。

期望：能看到 email 发送记录对应的 audit log。

## 6. SMTP 测试（后续可选）

只有在内部测试邮箱确认可用后才启用 SMTP。配置示例：

```bash
FILEADMIN_EMAIL_SEND_MODE=smtp
FILEADMIN_SMTP_HOST=smtp.example.com
FILEADMIN_SMTP_PORT=587
FILEADMIN_SMTP_USERNAME=test@example.com
FILEADMIN_SMTP_PASSWORD=***
FILEADMIN_SMTP_USE_TLS=true
FILEADMIN_EMAIL_FROM=no-reply@example.com
FILEADMIN_EMAIL_FROM_NAME="TACAI FileAdmin"
```

SMTP 测试必须先只发到内部测试邮箱，不允许直接发真实客户或候选人。

## 7. 通过标准

- 未审核文件不能发送。
- `approved_generated` / `approved` / `active` / `signed` 文件可以创建发送记录。
- 默认 dry-run 不真实发送邮件。
- 收件人邮箱格式错误会被拒绝。
- 必须勾选合规确认。
- Email Detail 能看到发送记录。
- Audit Logs 能看到 `email_dry_run_created`。
- 测试人员理解：正式外发前必须完成模板审批、文件确认和邮件收件人确认。
