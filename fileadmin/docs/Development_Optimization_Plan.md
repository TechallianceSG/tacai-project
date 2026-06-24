# FileAdmin 开发优化与企业级增强计划

Last updated: 2026-06-23

## 1. 目标

FileAdmin 当前已经具备轻量 MVP 能力：文档台账、合同提醒、多文件附件、版本兼容、User_admin 权限、Portal 集成和审计日志。

下一阶段目标是把 FileAdmin 从“可用 MVP”提升为“可控、可审计、可扩展的企业文档管理系统”。

## 2. 开发层面 1-6 优先优化项

### 1. JSON 写入安全

问题：当前本地 JSON 存储如果多人同时操作，可能出现并发覆盖或写入中断导致 JSON 损坏。

要求：

- 所有 JSON 写入必须通过统一保存函数。
- 写入时使用线程锁。
- 先写 `.tmp` 文件，再用 `os.replace` 原子替换。
- 写入前后保持 UTF-8 和 JSON array 格式。

状态：P0，已纳入实现。

### 2. 附件级权限控制

问题：有 `fileadmin.download` 权限不代表可以下载所有文件。

要求：

- 下载附件前必须找到所属文档记录。
- 检查用户是否能查看该文档。
- 检查用户是否能下载该附件。
- 结合 Entity、保密等级、业务线、角色、owner 判断。

状态：P0，已纳入实现。

### 3. 上传文件类型和安全校验

问题：企业文档管理不能允许任意文件上传。

要求：

- 限制最大上传大小。
- 增加扩展名白名单。
- 增加 MIME 类型白名单。
- 禁止可执行、脚本、HTML、应用安装包等高风险文件。
- 保存前再次安全化文件名。

状态：P0，已纳入实现。

### 4. 审计日志不可篡改增强

问题：JSON array 审计日志业务上是 append-only，但技术上仍可被改写。

要求：

- 每条 audit event 增加 `previous_hash` 和 `event_hash`。
- event hash 基于审计事件核心字段和 previous hash 计算。
- 下载审计记录更多上下文：document title、file title、confidentiality、user、IP、user agent。
- 后续可迁移为 JSONL append-only 存储。

状态：P0/P1，当前先实现 hash chain 字段。

### 5. 新旧数据模型迁移统一

问题：当前兼容旧 MVP，存在 `documents.json` / `document_versions.json` 和新模型 `document_records.json` / `file_attachments.json`。

要求：

- 短期保留兼容，不破坏现有功能。
- 新上传文件以 `file_attachments.json` 为主。
- 文档记录同步写入 `document_records.json`。
- 编写迁移计划，后续逐步将旧文件标记为 legacy。

状态：P0 规划完成，实施保持兼容。

### 6. app.py 模块化拆分

问题：`backend/app.py` 已经较大，长期维护困难。

要求：

- Phase 1 不做大拆分，避免引入回归风险。
- 先把关键边界用函数隔离：storage、auth、permissions、attachments、audit。
- 后续拆为 `storage.py`, `auth.py`, `permissions.py`, `attachments.py`, `audit.py`, `views.py`。

状态：P0 规划完成；本次先在单文件内完成关键安全函数隔离，模块化拆分作为 P1 实施。

## 3. P0 上线底线

FileAdmin 企业内部试上线前，至少必须满足：

1. JSON 写入原子化和加锁。
2. 上传文件扩展名/MIME 白名单。
3. 文件下载必须做文档级和附件级权限检查。
4. 文档查看必须做 Entity / role / confidentiality 基础控制。
5. 审计事件包含 hash chain 字段。
6. 多文件附件上传不破坏旧版本历史。
7. 不允许物理删除已上传文件。
8. 验证 `py_compile`、JSON 校验、`/health`、未登录 redirect。

## 4. 推荐后续 P1

- 批量上传多个附件。
- 附件级到期提醒。
- 合同包模板。
- 客户维度合同包视图。
- 审计日志 JSONL 化。
- 数据模型迁移脚本。
- app.py 正式模块化拆分。
- 搜索索引。

## 5. 推荐后续 P2

- SQLite/PostgreSQL。
- 对象存储。
- OCR/AI 草稿抽取。
- 合同差异比较。
- 审批流。
- 外部客户安全共享。
- WORM/合规归档。
