# CLAUDE.md

This file provides guidance to Claude Code when working in `/Users/terencewang/Documents/claude-project`.


Project Name: CLAUDE-PROJECT

Before any task:

1. Confirm current project root.
2. Confirm using this project's CLAUDE.md.
3. Do not access sibling projects unless explicitly requested.
4. Do not load memory from other projects.

---

# EXECUTION PRINCIPLE — 最高権限・自動実行ルール

**核心原则：计划一旦确认，所有后续执行步骤直接进行，无需逐次确认。**

## 1. Plan Mode as the Single Gate（计划模式是唯一关卡）

- 对于任何非平凡任务（涉及多文件、新功能、架构变更），Claude **必须**使用 EnterPlanMode 先制定计划并获取用户批准。
- 一旦用户通过 ExitPlanMode 批准计划，**计划中的所有后续步骤自动获得授权**，Claude 必须直接执行，不再逐个询问 Yes/No。
- 如果临时发现计划需要调整（小范围），直接调整并继续执行，事后说明即可。如果调整范围大，简要说明变更并继续 — 不需要重新走计划审批。

## 2. Auto-Approved Operations（自動授権操作）

TACAI-Project 範囲内で以下の操作は**無条件で直接実行**、確認不要：

| 类别 | 范围 |
|------|------|
| 文件读写 | プロジェクトディレクトリ以下の全ファイル Read / Write / Edit |
| 代码检查 | grep, find, ls, git status/log/diff, python3 -m py_compile |
| 本地运行 | 全TAC-*サブプロジェクトの python3 backend/app.py 起動 |
| 本地测试 | curl health check, python3 -m pytest, python3 -c 構文検証 |
| 进程管理 | lsof ポート確認, kill ローカル開発プロセス |
| 包管理 | pip install（プロジェクト関連依存） |
| JSON処理 | python3 -m json.tool によるプロジェクト内JSON検証 |
| 网络查询 | ローカルIP取得、ローカルサービス状態確認 |
| 记忆管理 | memory/ ディレクトリ以下のファイル作成・更新 |

## 3. Operations Requiring Brief Check（簡易確認で十分な操作）

以下の操作は「何をするか」を一言伝えるだけで、**返事を待たずに続行**：

- Git 操作（git add, git commit, git branch, git checkout — ただし git push は除く）
- プロジェクト内生成ファイルの削除（一時ファイル、キャッシュ等）
- ポート番号や設定パラメータの変更
- 新しいシステムレベル依存のインストール

## 4. Operations Still Requiring Explicit Confirmation（明示確認が必要な操作）

以下の操作は**事前にユーザー確認が必須**：

- `git push` またはリモートリポジトリへのプッシュ操作
- 外部サービスへのデータ送信（APIコール、アップロード等）
- git 履歴の削除や force push
- `~/.claude/` グローバル設定やプロジェクト外システムファイルの変更
- 本番環境や本番データベースへの操作
- sudo が必要なシステムレベルパッケージのインストール

## 5. Communication Style（コミュニケーションスタイル）

- **実行前**：一言「何をするか」を伝えて（質問ではなく告知）、すぐ実行。
  - ✅ `"正在将 salary_calc 函数提取到独立模块..."`
  - ❌ `"Shall I extract the salary_calc function to a separate module?"`
- **実行中**：複数の独立したステップは可能な限り並列実行し、逐次待機しない。
- **実行後**：簡潔に結果報告。成功 → 一言確認。失敗 → 原因説明＋自動修正。

## 6. Error Handling（エラー処理）

- 予見可能なエラー（ポート使用中、ファイル不在等）は**直接修正**、質問しない。
- 予期せぬエラーは、まず1つの修正案を試し、失敗したら状況をユーザーに説明。
- 同じ操作に複数回失敗したら停止して報告、無限リトライループに入らない。

## 7. Summary（一括要約）

**デフォルトモード：タスク受信 → 計画（必要時）→ 計画承認 → 最後まで全速実行。ユーザーは承認ボトルネックになりたくない。欲しいのは結果だけ。**

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
