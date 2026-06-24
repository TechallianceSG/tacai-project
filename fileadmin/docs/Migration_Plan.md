# FileAdmin 数据模型迁移计划

Last updated: 2026-06-23

## 1. 背景

FileAdmin Phase 1 初始实现使用：

- `documents.json`
- `document_versions.json`
- `contract_reminders.json`

后续根据业务需求，明确采用企业文档管理更合理的模型：

- `document_records.json`
- `file_attachments.json`
- `reminders.json`
- `audit_logs.json`

当前代码为避免破坏 MVP，采取兼容策略：新上传附件写入 `file_attachments.json`，同时继续写入 `document_versions.json` 作为 legacy version 记录。

## 2. 当前策略

### 2.1 短期兼容

- `documents.json` 继续作为旧 MVP 文档主表。
- `document_records.json` 作为新模型 shadow 表，同步保存文档记录。
- `document_versions.json` 继续作为旧版本历史表。
- `file_attachments.json` 作为新附件主表。

### 2.2 新功能主表

所有新开发功能应优先读取：

```text
document_records.json
file_attachments.json
reminders.json
audit_logs.json
```

其中上传、下载、附件列表、附件级权限应以 `file_attachments.json` 为准。

## 3. 迁移阶段

### Stage 1 — 双写兼容，当前阶段

- 创建文档时写入 `documents.json` 和 `document_records.json`。
- 上传附件时写入 `file_attachments.json` 和 `document_versions.json`。
- 详情页优先显示 `file_attachments.json`，没有附件时仍显示 legacy version history。

### Stage 2 — 迁移脚本

创建脚本：

```text
fileadmin/scripts/migrate_legacy_documents.py
```

功能：

- 读取 `documents.json`。
- 将缺失记录补入 `document_records.json`。
- 读取 `document_versions.json`。
- 对没有 `file_id` 的旧 version 生成 `file_attachments.json` 记录。
- 生成迁移报告。
- 不删除旧文件。

### Stage 3 — 读新表，旧表只兼容

- 文档列表和详情页改为优先读取 `document_records.json`。
- 附件列表只读取 `file_attachments.json`。
- `document_versions.json` 只用于旧数据 fallback。

### Stage 4 — Legacy 标记

- 文档中标记 `documents.json` 和 `document_versions.json` 为 legacy compatibility files。
- 不再新增直接依赖旧表的新功能。

## 4. 迁移安全原则

1. 不删除历史文件。
2. 不覆盖旧 JSON。
3. 迁移前备份 `database/` 和 `attachments/`。
4. 迁移脚本必须可重复运行。
5. 迁移脚本必须输出差异报告。
6. 迁移后运行 JSON 校验和基本 smoke test。

## 5. 企业级数据库迁移方向

后续如果迁移到 SQLite/PostgreSQL，建议表结构：

```text
document_records
file_attachments
reminders
document_categories
folders
audit_logs
ocr_document_drafts
```

主键继续使用当前业务 ID，例如 `FA-2026-0001`, `FILE-2026-0001`，避免破坏跨模块引用和审计历史。
