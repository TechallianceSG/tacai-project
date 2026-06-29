# CLAUDE.md — TACAI-Project

> **三大核心原则 / THREE CORE PRINCIPLES**

| # | 原则 | 含义 |
|---|------|------|
| 1 | **编程效率第一** | 速度优先于流程。并行执行、跳过非必要确认、直奔结果。 |
| 2 | **Claude Code 最高权限** | 本项目内所有操作默认授权，无需逐次审批。 |
| 3 | **默认 YES** | 所有权限提示默认回答 Yes。遇到确认框 = 直接通过。 |

---

Project Root: `/Users/terencewang/Documents/claude-project/TACAI-Project`

Before any task:
1. Work inside this project root — do not access sibling projects unless explicitly requested.
2. Do not load memory from other projects.

---

# EXECUTION PRINCIPLE — 最高権限・デフォルトYES

**一句话：别问，直接做。遇到确认就点Yes。用户只要结果。**

## 1. 默认行为：直接执行，无需确认

以下所有操作 **无条件直接执行，0次确认**：

| 类别 | 范围 |
|------|------|
| 文件读写 | 项目内所有文件 Read / Write / Edit（含创建、删除、重命名） |
| 代码搜索 | grep, find, ls, cat, head, tail, wc, glob, 所有只读操作 |
| 代码编译 | python3 -m py_compile, python3 -c 语法验证 |
| 本地运行 | 所有 TAC-* 子项目的 python3 backend/app.py 启动 |
| 本地测试 | curl health check, python3 -m pytest, python3 -m unittest |
| 进程管理 | lsof 端口检查, kill / pkill 本地开发进程 |
| 包管理 | pip install / pip list（项目相关依赖） |
| JSON处理 | python3 -m json.tool 项目内 JSON 验证 |
| 网络查询 | 本地 IP 获取、本地服务状态确认、curl 本地 API |
| 记忆管理 | memory/ 目录下文件创建、更新、归档 |
| Git 只读 | git status, git diff, git log, git show, git branch, git remote -v |
| Git 写入 | git add, git commit, git checkout, git switch, git stash, git restore, git reset（不含 push） |
| 临时文件 | 项目内任何缓存、临时文件、生成文件的删除 |
| 配置修改 | 端口号、参数、本地配置文件的修改 |
| Shell脚本 | 项目内 .sh 文件的执行 |

## 2. 需要一言告知（告知即执行，不等回复）

- 安装新的系统级依赖（pip install 新包）
- 修改端口分配方案
- 创建新的子目录结构

## 3. 唯一需要明确确认的操作

以下操作 **必须事先征得用户同意**：

- `git push` / 远程仓库推送
- 外部服务数据发送（外部 API 调用、文件上传到外部）
- git 历史删除 / force push
- `~/.claude/` 全局配置修改
- 生产环境 / 生产数据库操作
- `sudo` 系统级安装

## 4. 沟通风格

- **执行前**：一句话告知（不是询问），然后立即执行。
  - ✅ `"提取 salary_calc 函数到独立模块..."`
  - ❌ `"Shall I extract the salary_calc function?"`
- **执行中**：并行执行所有独立步骤，不等待。
- **执行后**：简洁报告。成功 → 一句话。失败 → 原因 + 自动修复。

## 5. 错误处理

- 可预见错误（端口占用、文件缺失等）→ **直接修复**，不询问。
- 意外错误 → 先试一个修复方案，失败再报告。
- 同一操作失败 3 次 → 停，报告，不进入死循环。

## 6. Plan Mode 规则

- 非平凡任务（多文件、新功能、架构变更）→ 先用 EnterPlanMode 制定计划。
- 计划批准后 → 全自动执行，不再有任何确认。
- 计划执行中需要微调 → 直接调整继续，事后说明。

## 7. 总结

```
用户发任务 → 计划(如需) → 批准 → 全速执行到底 → 报告结果
中间没有任何 Yes/No 确认。用户不是瓶颈，结果才是。
```

---

## Current workspace state

This workspace contains multiple independent local projects rather than one root application:

- [TAC-timesheet/](TAC-timesheet/) — Japan dispatch, expatriate, and client-site timesheet management MVP.
- [TACAI-PRJ/](TACAI-PRJ/) — Japan HR finance/payroll MVP.
- [TAC-reimbursement/](TAC-reimbursement/) — standalone Japan employee reimbursement self-service MVP, currently planning/skeleton only.
- [TAC-employeeadmin/](TAC-employeeadmin/) — standalone employee administration MVP skeleton.
- [TAC-salary/](TAC-salary/) — standalone salary and payroll calculation MVP skeleton.
- [InterviewReady/](InterviewReady/) — interview preparation app with Python package metadata and tests.

The root directory is not a git repository and has no root-level package manifest.

## Commands

### TAC-timesheet

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 backend/app.py --host 127.0.0.1 --port 8002
```

Health check:

```bash
curl -s http://127.0.0.1:8002/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-timesheet
python3 -m py_compile backend/app.py
```

### TACAI-PRJ

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TACAI-PRJ
python3 backend/app.py --host 127.0.0.1 --port 8001
```

### TAC-reimbursement

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-reimbursement
python3 backend/app.py --host 127.0.0.1 --port 8003
```

Health check:

```bash
curl -s http://127.0.0.1:8003/health
```

### TAC-employeeadmin

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 backend/app.py --host 127.0.0.1 --port 8004
```

Health check:

```bash
curl -s http://127.0.0.1:8004/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-employeeadmin
python3 -m py_compile backend/app.py
```

### TAC-salary

Run locally:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 backend/app.py --host 127.0.0.1 --port 8005
```

Health check:

```bash
curl -s http://127.0.0.1:8005/health
```

Syntax check:

```bash
cd /Users/terencewang/Documents/claude-project/TAC-salary
python3 -m py_compile backend/app.py
```

### InterviewReady

See [InterviewReady/CLAUDE.md](InterviewReady/CLAUDE.md) and [InterviewReady/pyproject.toml](InterviewReady/pyproject.toml) for project-specific commands.

## Architecture

### TAC-timesheet

- [TAC-timesheet/backend/app.py](TAC-timesheet/backend/app.py) is a Python standard-library local web app.
- [TAC-timesheet/database/timesheet_entries.json](TAC-timesheet/database/timesheet_entries.json) stores the timesheet table as a JSON array.
- [TAC-timesheet/database/employees.json](TAC-timesheet/database/employees.json) and [TAC-timesheet/database/projects.json](TAC-timesheet/database/projects.json) are placeholder master-data files.
- [TAC-timesheet/docs/Timesheet_Table_Specification.md](TAC-timesheet/docs/Timesheet_Table_Specification.md) documents fields, enum values, validation, and calculation rules.

### TACAI-PRJ

- [TACAI-PRJ/backend/app.py](TACAI-PRJ/backend/app.py) is a Python standard-library local web app for HR/payroll workflows.
- [TACAI-PRJ/database/](TACAI-PRJ/database/) stores local JSON data.

### TAC-reimbursement

- [TAC-reimbursement/backend/app.py](TAC-reimbursement/backend/app.py) is a Python standard-library local web app for manual reimbursement claim entry and attachment upload.
- [TAC-reimbursement/README.md](TAC-reimbursement/README.md) defines the standalone reimbursement self-service scope.
- [TAC-reimbursement/docs/Project_Plan.md](TAC-reimbursement/docs/Project_Plan.md) documents the implementation phases.
- [TAC-reimbursement/docs/Data_Schema.md](TAC-reimbursement/docs/Data_Schema.md) documents planned JSON schemas.
- [TAC-reimbursement/prompts/OCR_Receipt_Prompt.md](TAC-reimbursement/prompts/OCR_Receipt_Prompt.md) documents the receipt/invoice extraction prompt draft.

### TAC-employeeadmin

- [TAC-employeeadmin/backend/app.py](TAC-employeeadmin/backend/app.py) is a Python standard-library local web app skeleton for employee administration.
- [TAC-employeeadmin/database/employees.json](TAC-employeeadmin/database/employees.json) stores placeholder employee master data as a JSON array.
- [TAC-employeeadmin/README.md](TAC-employeeadmin/README.md) defines the initial standalone employee administration scope.
- [TAC-employeeadmin/docs/Project_Plan.md](TAC-employeeadmin/docs/Project_Plan.md) documents the initial implementation phases.
- [TAC-employeeadmin/docs/Data_Schema.md](TAC-employeeadmin/docs/Data_Schema.md) documents the draft employee data schema.

### TAC-salary

- [TAC-salary/backend/app.py](TAC-salary/backend/app.py) is a Python standard-library local web app skeleton for salary and payroll calculation workflows.
- [TAC-salary/frontend/index.html](TAC-salary/frontend/index.html) is a local manual salary entry UI.
- [TAC-salary/database/salary_records.json](TAC-salary/database/salary_records.json) stores salary records as a JSON array.
- [TAC-salary/database/audit_logs.json](TAC-salary/database/audit_logs.json) stores append-only audit logs as a JSON array.
- [TAC-salary/docs/Project_Plan.md](TAC-salary/docs/Project_Plan.md) documents implementation phases.
- [TAC-salary/docs/Data_Schema.md](TAC-salary/docs/Data_Schema.md) documents the draft salary data schema.
- [TAC-salary/docs/Salary_Table_Specification.md](TAC-salary/docs/Salary_Table_Specification.md) documents salary fields, statuses, validation, and calculation rules.

## Local port convention

- InterviewReady: `8000`
- TACAI-PRJ: `8001`
- TAC-timesheet: `8002`
- TAC-reimbursement: `8003` planned
- TAC-employeeadmin: `8004` planned
- TAC-salary: `8005` planned

Project Name: TAC-timesheet

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.




# MEMORY MANAGEMENT

The project must maintain a small active context window.
Memory Structure
1. memory/
2. archive/

File Size Policy
Green Zone
0KB - 30KB
Normal operation.
Yellow Zone
30KB - 100KB
Monitor growth and prepare for summarization.
Red Zone
Over 100KB
Archive and compress immediately.
Archive Rules
When any file under `/memory` exceeds 100KB:
Create archive copy.
Generate concise summary.
Replace active memory file with summary.
Never delete archive records.
Archive Naming Convention
1. archive/<module>/<filename>_YYYY_MM.md

Example:
1. archive/project_status/project_status_2026_06.md
2. archive/recruitment/recruitment_2026_06.md
3. archive/payroll/payroll_2026_06.md

Loading Rules
Do not automatically load archive files.
Only load:
CLAUDE.md
memory/project_status.md
related module memory file
Archive files should only be opened when explicitly requested.
Memory Update Rules
After every major task:
Update project_status.md
Update related module memory
Update decisions.md (if architectural decisions were made)
Update changelog.md (if system changes occurred)
Historical Preservation Policy
Never delete historical records.
When summarizing:
Preserve key decisions
Preserve business rules
Preserve architecture decisions
Preserve implementation status
Preserve unresolved issues
Archive files are the source of truth for historical details.


## Startup Loading Priority

On project startup, load files in this order:

1. CLAUDE.md
2. memory/project_status.md
3. memory/current_tasks.md
4. Related module memory

Do not load archive files automatically.




# Audit Rules

All modules must implement audit logging.

Required fields:

- module
- record_id
- action
- user
- timestamp
- before_value
- after_value

Audit logs must never be deleted.

Audit logs are read-only.

Future centralized audit viewer may be added.

When memory exceeds 100KB:
   - archive
   - summarize
   - preserve history

Prefer modular architecture.


# UI / Report Standards

## Row Count Requirement (ALL pages)

Every report page, list page, and data table MUST show a total record count at the bottom of the results. This applies to:
- Browse/list pages (salary master, batches, monthly sheets, etc.)
- Report pages (payroll reports, cost reports, etc.)
- Audit log pages (show "Showing latest X of Y total entries")
- Parameter/config pages
- Any page that displays a list of records

Implementation pattern:
```html
<div class='helper-text' style='margin-top:8px'>{count} record(s) total</div>
```

Place immediately after the `</table></div>` closing tags, inside the card div for tables, or after the data content for non-table lists.

For filtered views, show: "Showing X of Y records (filtered)"

## Entity Display Convention (法人实体代码表示规范)

All modules MUST display legal entity as human-readable labels, never as raw entity_id codes (e.g., "ENT-0002").

### Label standard

| Lang | Label |
|------|-------|
| zh | 法人实体代码 |
| ja | 法人实体コード |
| en | Legal Entity Code |

Do NOT use abbreviated or abstract labels like "法人/公司", "Entity", or "法人/会社" for the entity field.

### Display format

Entity values in tables, dropdowns, and headers must be shown as:

```
{entity_code} - {entity_name} ({country})
```

Example:
- `TASG - Tech Alliance Consultancy Service Pte. Ltd (Singapore)`
- `TANJ - 南京特谙斯企业咨询有限公司 (中国)`
- `TAKK - Tech Alliance株式会社 (Japan)`

### Dropdown requirement

Entity filter/selection MUST use a `<select>` dropdown with human-readable labels, NOT a free-text `<input>`. The dropdown options must be derived from the salary master's distinct entity_id values, resolved against masterdata entities.json for labels.

### Source of truth

`TACAI-Core/masterdata/database/entities.json` is the authoritative entity master. All modules should resolve entity_id → display label from this source.

### Implementation pattern

```python
def entity_label(entity_id: str, lang: str = "zh") -> str:
    """Return human-readable entity label: code - name (country)."""
    # Load from masterdata entities.json, fallback to raw entity_id
    # Format: {entity_code} - {entity_name} ({country})
```

Filter dropdowns should use exact matching (`==`), not substring matching (`.lower() in`), since the dropdown provides exact entity_id values.

### Affected modules

- `TACAIPAY/tacaipaysg/` — implemented (2026-06-25)
- All future payroll modules (tacaipayjp, tacaipaycn, etc.)
- Any module displaying entity data in tables or filters


# business thinking

Business Focus:
- Recruitment Agency
- RPO
- Haken Business
- Payroll Management
- AI Recruitment Platform

Rules:

1. Follow Japan labor law and haken compliance.
2. Maintain reusable templates.
3. Store important decisions in memory/decisions.md.
4. Store business knowledge in skills/.


Think as:
   - IT Product Expert
   - IT Architecture Expert
   - HR Management Expert
   - Compensation and Benefits Expert
   - UI/UX Expert
   - SAP Product Development Expert
   - Software Architect
   - Recruitment Consultant
   - Business Operations Manager

Development thinking script:
When helping with product design, architecture, coding, testing, or documentation, Claude must evaluate the work from these perspectives:

1. IT Product Expert — clarify user value, MVP scope, workflow completeness, priorities, acceptance criteria, and business impact.
2. IT Architecture Expert — ensure modular architecture, maintainability, data integrity, scalability, security, auditability, and integration readiness.
3. HR Management Expert — consider HR operations, employee lifecycle, approval flows, compliance, permissions, data privacy, and Japan labor/haken requirements.
4. Compensation and Benefits Expert — consider payroll accuracy, salary rules, allowances, deductions, reimbursements, benefits, statutory calculations, and audit trails.
5. UI/UX Expert — keep interfaces simple, consistent, accessible, efficient for operations users, and suitable for Japanese business workflows.
6. SAP Product Development Expert — think in enterprise-grade master data, transaction data, approval status, audit logs, role authorization, configuration tables, and future ERP integration patterns.

Before implementing changes, Claude should briefly check whether the change affects product scope, architecture, HR/payroll compliance, UI/UX, audit logs, or future SAP/ERP integration.


# 数据库开发规范

### 连接方式
- 必须使用环境变量读取数据库配置
- 禁止硬编码任何数据库连接信息
- 三环境配置：.env.dev / .env.stg / .env.prd

### 表命名规范
| 模块 | 前缀 | 示例 |
|------|------|------|
| 员工管理 | emp_ | emp_user, emp_department |
| 考勤 | ts_ | ts_attendance, ts_leave |
| 薪资 | pay_ | pay_salary, pay_payslip |
| 费用报销 | rmb_ | rmb_expense, rmb_approval |
| 客户发票 | inv_ | inv_invoice, inv_customer |
| 文档管理 | doc_ | doc_file, doc_category |
| 主数据 | md_ | md_company, md_department |
| 面试系统 | iv_ | iv_candidate, iv_interview |
| 员工自助 | ss_ | ss_profile, ss_request |

### 字段命名规范
| 字段 | 类型 | 说明 |
|------|------|------|
| id | SERIAL | 主键，自增 |
| created_at | TIMESTAMP | 创建时间 |
| updated_at | TIMESTAMP | 更新时间 |
| deleted_at | TIMESTAMP | 软删除（NULLABLE） |

### 新建表流程
1. 表名必须加模块前缀
2. 字段命名遵循统一规范
3. 先写文档确认，再创建表
4. 必须包含 created_at 和 updated_at
5. 提交时附带 SQL 迁移脚本

### 禁止事项
- 禁止创建无前缀的表名
- 禁止硬编码数据库连接
- 禁止直接操作 PRD 数据库
- 禁止删除已有表

### 示例
```sql
CREATE TABLE inv_invoice (
    id SERIAL PRIMARY KEY,
    invoice_no VARCHAR(50) NOT NULL,
    customer_id INTEGER NOT NULL,
    amount DECIMAL(12,2) NOT NULL,
    status VARCHAR(20) DEFAULT 'draft',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```
