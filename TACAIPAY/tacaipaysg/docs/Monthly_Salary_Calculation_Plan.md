# 月度薪资核算 (Monthly Salary Calculation) — 实施规划

> 版本: 1.0 | 日期: 2026-06-25 | 模块: tacaipaysg (TACAI Pay SG)
>
> 本文档从**亚太薪酬专家**、**IT架构专家**、**产品专家**三个视角，对"月度薪资核算"功能进行完整规划。

---

## 目录

1. [现状分析](#1-现状分析)
2. [亚太薪酬专家视角](#2-亚太薪酬专家视角)
3. [IT架构专家视角](#3-it架构专家视角)
4. [产品专家视角](#4-产品专家视角)
5. [实施路线图](#5-实施路线图)
6. [数据模型设计](#6-数据模型设计)
7. [状态机设计](#7-状态机设计)
8. [API / 路由设计](#8-api--路由设计)
9. [UI 页面设计](#9-ui-页面设计)
10. [跨模块集成方案](#10-跨模块集成方案)
11. [测试与验收标准](#11-测试与验收标准)

---

## 1. 现状分析

### 已实现功能

| 模块 | 功能 | 状态 |
|------|------|------|
| Salary Master | 从 EmployeeAdmin 导入 SG 员工 | ✅ 已完成 |
| Salary Master | 手动创建 / 修改 / 停用薪资主记录 | ✅ 已完成 |
| Salary Master | 搜索 / 筛选 (Entity, Department, Team, No./Name) | ✅ 已完成 |
| Salary Master | CSV 导出 (支持筛选) | ✅ 已完成 |
| Monthly Batch | 3 步骤创建 (选员工 → 确认 → 创建) | ✅ 已完成 |
| Monthly Batch | 工资计算 (monthly/hourly/daily + CPF + SDL/FWL) | ✅ 已完成 |
| Monthly Batch | 状态流转 (draft → calculated → ... → paid) | ✅ 已完成 |
| Monthly Batch | PDF 工资单生成 + 邮件发送 | ✅ 已完成 |
| Monthly Batch | CSV 报表 (Payroll/Cost/Bank) | ✅ 已完成 |
| Parameters | CPF 参数管理 | ✅ 基础完成 |
| Audit | 审计日志 | ✅ 已完成 |

### 待完善 / 缺失功能

| 功能 | 现状 | Gap |
|------|------|-----|
| 考勤数据集成 | TAC-timesheet 模块已建成，但未与 Payroll 对接 | **需新建集成** |
| 月度满勤天数参数 | 当前硬编码 standard_work_days=22 | **需参数化，按国家/年度自动计算** |
| 基础资料确认流程 | 当前 batch 创建即进入 draft → calculate 流程，缺少 HR 确认考勤环节 | **需插入新的确认环节** |
| 薪资核算后版本对比 | 当前计算直接覆盖原记录 | **需版本化** |
| 经理二级审核 | 当前只有 HR review → approve | **需增加 manager review 环节** |
| 多国满勤日历 | 无 | **需为 JP/SG/CN 建立年度满勤日历** |

---

## 2. 亚太薪酬专家视角

### 2.1 业务需求分析

月度薪资核算是亚太区薪酬管理的核心月度运营流程。以新加坡为例，典型月度流程为：

```
月初 (1-5日):   HR 创建当月空工资表，导入员工主数据
月初 (5-10日):  HR 确认考勤数据（出勤天数、请假、加班等）
月中 (10-15日): HR 确认基础资料 → 执行薪资计算
月中 (15-20日): HR 审核计算结果 → 发送经理二级审核
月末 (20-25日): 经理审核通过 → 进入工资发放流程
月末 (25-28日): 发放工资 → 生成工资单
```

### 2.2 关键业务规则

#### 2.2.1 月度满勤天数

不同国家/地区每月满勤天数不同，需建立**薪资参数**自动计算：

| 国家 | 满勤计算规则 | 示例 (2026年) |
|------|-------------|--------------|
| 新加坡 (SG) | 当月工作日 = 当月总天数 - 周六 - 周日 - 公共假期 | 2026-01: 22天 |
| 日本 (JP) | 当月工作日 = 当月总天数 - 周六 - 周日 - 祝日 | 2026-01: 20天 |
| 中国 (CN) | 当月工作日 = 当月总天数 - 周六 - 周日 - 法定节假日 | 2026-01: 22天 |

**参数设置建议**：
- 每年年初由系统管理员导入当年公共假期
- 系统自动计算每月满勤天数
- HR 可在特殊月份手动覆盖

#### 2.2.2 考勤数据来源

| 数据项 | 当前来源 | 目标来源 |
|--------|---------|---------|
| 当月出勤天数 | 手动输入 | TAC-timesheet 月度汇总 |
| 加班小时 | 无 | TAC-timesheet 加班记录 |
| 请假天数 | 无 | 未来请假模块 |
| 迟到/早退 | 无 | 未来考勤模块 |

#### 2.2.3 薪资计算规则 (SG)

```
月薪员工:
  基本工资 = basic_salary × (当月出勤天数 / 当月满勤天数)
  应发合计 = 基本工资 + 固定津贴 + 绩效工资 + 奖金 + 其他支付
  扣除合计 = 员工CPF + 定期扣除 + 其他扣除 + 所得税
  实发工资 = 应发合计 - 扣除合计
  雇主成本 = 应发合计 + 雇主CPF + SDL + FWL

时薪员工:
  基本工资 = hourly_rate × 出勤小时
  (其余同上)

日薪员工:
  基本工资 = daily_rate × 出勤天数
  (其余同上)
```

#### 2.2.4 审批层级

| 步骤 | 角色 | 权限 | 说明 |
|------|------|------|------|
| 创建空工资表 | HR Officer | `tacaipay_sg.manage` | 选择月份 + 法人 |
| 确认考勤 & 基础资料 | HR Officer | `tacaipay_sg.manage` | 状态: draft → hr_confirmed |
| 执行薪资计算 | HR Officer | `tacaipay_sg.calculate` | 状态: hr_confirmed → calculated |
| HR 审核计算结果 | HR Manager | `tacaipay_sg.approve` | 状态: calculated → hr_reviewed |
| 经理二级审核 | Dept Manager | `tacaipay_sg.manager_review` | 状态: hr_reviewed → manager_approved |
| 进入发放流程 | Finance | `tacaipay_sg.release_payment` | 状态: manager_approved → finalized → ... |

### 2.3 合规注意事项

1. **新加坡 CPF**：费率需按法定年龄/薪资段计算，当前为 manual-safe 模式
2. **SDL/FWL**：需按员工身份（公民/PR/外籍）区别处理
3. **审计追踪**：每一步操作必须有审计日志
4. **数据保护**：薪资数据仅限授权人员访问
5. **版本保留**：计算前后的版本均需保留，不可覆盖

---

## 3. IT架构专家视角

### 3.1 架构原则

- **保持现有架构不变**：Python 标准库 + JSON 存储 + Server-rendered HTML
- **增量演进**：不重构现有 batch/record 结构，在其基础上扩展
- **模块解耦**：考勤集成通过 HTTP API，不直接读取 timesheet 数据库
- **版本化设计**：薪资计算引入版本号机制
- **审计完整性**：所有状态变更写入 audit log

### 3.2 新增数据表

#### 3.2.1 `monthly_salary_sheets.json` — 月度工资表头

```json
{
  "sheet_id": "MSS-SG-2026-06",
  "country_code": "SG",
  "entity_id": "ENT-0002",
  "payroll_month": "2026-06",
  "status": "draft",
  "version": 1,
  "employee_count": 45,
  "standard_work_days": 22,
  "standard_work_hours": 176,
  "attendance_source": "manual",
  "attendance_locked": false,
  "basic_info_confirmed_at": null,
  "basic_info_confirmed_by": null,
  "calculated_at": null,
  "calculated_by": null,
  "created_at": "2026-06-25T10:00:00+00:00",
  "created_by": "HR Officer",
  "updated_at": "2026-06-25T10:00:00+00:00",
  "notes": ""
}
```

#### 3.2.2 `monthly_salary_records.json` — 月度工资表明细

```json
{
  "record_id": "MSS-SG-2026-06-EMP-0035",
  "sheet_id": "MSS-SG-2026-06",
  "payroll_month": "2026-06",
  "country_code": "SG",
  "entity_id": "ENT-0002",

  "_snapshot_from_master": {
    "employee_id": "EMP-0035",
    "employee_number": "TASG251215",
    "employee_name": "KuanHua Tseng",
    "email": "khtseng@example.com",
    "department_label": "Engineering",
    "team_label": "Backend",
    "salary_type": "monthly",
    "bank_name": "DBS",
    "bank_account_name": "KuanHua Tseng",
    "bank_account_number": "001-234567-8"
  },

  "_attendance": {
    "standard_work_days": 22,
    "standard_work_hours": 176,
    "actual_work_days": 21,
    "actual_work_hours": 168,
    "paid_leave_days": 1,
    "unpaid_leave_days": 0,
    "overtime_hours": 0,
    "late_night_hours": 0,
    "holiday_hours": 0,
    "absence_days": 0,
    "attendance_source": "manual",
    "timesheet_ref": null
  },

  "_input_values": {
    "basic_salary": 6000.00,
    "hourly_rate": 0.00,
    "daily_rate": 0.00,
    "fixed_allowance": 300.00,
    "performance_bonus": 200.00,
    "bonus": 0.00,
    "other_payment": 0.00,
    "recurring_deductions": 0.00,
    "other_deduction": 0.00,
    "income_tax": 0.00,
    "cpf_applicable": true,
    "cpf_input_mode": "manual",
    "cpf_employee_manual": 1200.00,
    "cpf_employer_manual": 1020.00,
    "skill_development_levy": 11.25,
    "foreign_worker_levy": 0.00
  },

  "_calculated_result": {
    "base_pay_calculated": 5727.27,
    "gross_pay": 6227.27,
    "cpf_employee": 1200.00,
    "cpf_employer": 1020.00,
    "deduction_total": 1200.00,
    "net_pay": 5027.27,
    "employer_cost_total": 7258.52,
    "calculation_messages": ["Base pay prorated: 6000 × 21/22 = 5727.27"]
  },

  "status": "draft",
  "hr_confirmed_at": null,
  "hr_confirmed_by": null,
  "manager_review_status": "pending",
  "manager_review_comment": "",
  "created_at": "2026-06-25T10:00:00+00:00",
  "updated_at": "2026-06-25T10:00:00+00:00"
}
```

#### 3.2.3 `payroll_calendar.json` — 薪资日历参数 (新增)

```json
{
  "calendar_id": "CAL-SG-2026",
  "country_code": "SG",
  "year": 2026,
  "status": "active",
  "months": {
    "01": { "calendar_days": 31, "weekend_days": 9, "public_holidays": 1, "standard_work_days": 21 },
    "02": { "calendar_days": 28, "weekend_days": 8, "public_holidays": 0, "standard_work_days": 20 },
    "03": { "calendar_days": 31, "weekend_days": 9, "public_holidays": 0, "standard_work_days": 22 },
    "04": { "calendar_days": 30, "weekend_days": 8, "public_holidays": 1, "standard_work_days": 21 },
    "05": { "calendar_days": 31, "weekend_days": 10, "public_holidays": 1, "standard_work_days": 20 },
    "06": { "calendar_days": 30, "weekend_days": 8, "public_holidays": 0, "standard_work_days": 22 },
    "07": { "calendar_days": 31, "weekend_days": 8, "public_holidays": 0, "standard_work_days": 23 },
    "08": { "calendar_days": 31, "weekend_days": 10, "public_holidays": 1, "standard_work_days": 20 },
    "09": { "calendar_days": 30, "weekend_days": 8, "public_holidays": 0, "standard_work_days": 22 },
    "10": { "calendar_days": 31, "weekend_days": 9, "public_holidays": 0, "standard_work_days": 22 },
    "11": { "calendar_days": 30, "weekend_days": 9, "public_holidays": 1, "standard_work_days": 20 },
    "12": { "calendar_days": 31, "weekend_days": 9, "public_holidays": 1, "standard_work_days": 21 }
  },
  "public_holidays": [
    { "date": "2026-01-01", "name": "New Year's Day" },
    { "date": "2026-02-17", "name": "Chinese New Year" },
    { "date": "2026-04-03", "name": "Good Friday" }
  ],
  "created_at": "2026-01-01T00:00:00+00:00",
  "created_by": "System Admin",
  "updated_at": "2026-01-01T00:00:00+00:00"
}
```

### 3.3 状态机设计

#### 3.3.1 月度工资表 (Sheet) 状态流

```
                    ┌──────────┐
                    │  draft   │  ← 创建空工资表
                    │  草稿    │
                    └────┬─────┘
                         │ HR 确认考勤 + 基础资料
                         ▼
                  ┌──────────────┐
                  │ hr_confirmed │  ← 基础资料已确认
                  │  HR已确认    │     (可退回修改)
                  └──────┬───────┘
                         │ HR 执行薪资计算
                         ▼
                  ┌──────────────┐
                  │  calculated  │  ← 计算完成
                  │  已计算      │     (可逐条修改后重算)
                  └──────┬───────┘
                         │ HR 审核通过
                         ▼
                  ┌──────────────┐
                  │ hr_reviewed  │  ← HR审核完成
                  │  HR已审核    │
                  └──────┬───────┘
                         │ 发送经理审核
                         ▼
                  ┌──────────────────┐
                  │ manager_review   │  ← 经理审核中
                  │  经理审核中       │
                  └──────┬───────────┘
                         │ 经理审核通过
                         ▼
                  ┌──────────────────┐
                  │ manager_approved │  ← 经理审核通过
                  │  经理已批准       │
                  └──────┬───────────┘
                         │ 进入发放流程
                         ▼
                  ┌──────────────┐
                  │  finalized   │  → payslips → paid
                  │  已确认       │
                  └──────────────┘

  异常路径:
  hr_confirmed → draft          (HR 退回)
  calculated   → hr_confirmed   (HR 退回重确认)
  hr_reviewed  → calculated     (HR 退回重算)
  manager_review → hr_reviewed  (经理退回)
  任意状态     → correction     (标记为修正中)
```

### 3.4 与现有 Batch/Record 的关系

**策略：共存演进，不破坏现有流程**

- 现有 `payroll_batches.json` + `payroll_records_sg.json` 保持不变
- 新增 `monthly_salary_sheets.json` + `monthly_salary_records.json` 为增强版
- 在 UI 层面提供切换入口 (现有 "月度工资表" → 增强版 "月度薪资核算")
- 增强版稳定后，逐步将旧版功能迁移

### 3.5 跨模块集成架构

```
┌──────────────────┐     HTTP API      ┌──────────────────┐
│  TAC-timesheet   │ ────────────────→ │   tacaipaysg     │
│  (Port 8002)     │  月度考勤汇总     │   (Port 8016)    │
└──────────────────┘                   └────────┬─────────┘
                                                │
┌──────────────────┐     HTTP API              │
│ TAC-employeeadmin│ ──────────────────────────┤
│  (Port 8004)     │  员工主数据                │
└──────────────────┘                            │
                                                │
┌──────────────────┐     HTTP API              │
│  User_admin      │ ──────────────────────────┤
│  (Port 8006)     │  用户认证 + 权限           │
└──────────────────┘                            │
                                                │
┌──────────────────┐     HTTP API              │
│  masterdata      │ ──────────────────────────┤
│  (Port 8007)     │  法人/部门/团队主数据      │
└──────────────────┘                            │
```

**TAC-timesheet → tacaipaysg 集成 API:**
```
GET /api/payroll/attendance-summary?country_code=SG&month=2026-06&entity_id=ENT-0002
→ 返回每位员工的月度考勤汇总
```

---

## 4. 产品专家视角

### 4.1 用户故事

#### 故事 1: HR 创建月度工资表
> **作为** HR Officer，
> **我想要** 选择一个月份和法人，一键生成当月空工资表，
> **以便** 快速启动月度薪资核算流程，不需要逐个添加员工。

**验收标准:**
- 输入年度 + 月份 + 法人 → 生成空工资表
- 自动带入所有在职员工的：员工编号、姓名、邮箱、部门、团队、薪资类型、银行信息
- 自动匹配当月满勤天数（从薪资日历获取）
- 状态初始为 "草稿"

#### 故事 2: HR 确认考勤与基础资料
> **作为** HR Officer，
> **我想要** 在工资表上逐条确认员工的考勤数据（出勤天数、请假等）和基础薪资数据，
> **以便** 确保薪资计算的基础数据准确无误。

**验收标准:**
- 从 TAC-timesheet 自动拉取考勤数据（如有）
- 支持手动修改出勤天数、请假天数等
- 月薪人员可查看基本工资 / 当月满勤天数 / 当月出勤天数
- 点击"基础资料确认"后，状态变为 "HR已确认"
- 确认后自动保存一个版本快照

#### 故事 3: HR 执行薪资计算
> **作为** HR Officer，
> **我想要** 在确认基础资料后执行薪资计算，
> **以便** 自动生成每位员工的应发工资、扣除、实发工资和雇主成本。

**验收标准:**
- 只有状态为 "HR已确认" 的工资表才能执行计算
- 计算生成核算后版本，附带计算说明
- 计算结果以新版本保存，不覆盖原始录入数据
- HR 可以查看计算结果并对特殊情况进行修改

#### 故事 4: 经理二级审核
> **作为** Department Manager，
> **我想要** 审核 HR 提交的本部门月度薪资表，
> **以便** 确保薪资计算无误后进入发放流程。

**验收标准:**
- HR 审核完成后可"发送经理审核"
- 经理看到本部门的员工薪资汇总
- 经理可批准或退回（附退回原因）
- 支持按部门筛选，经理只能看到自己部门的员工

#### 故事 5: 薪资日历管理
> **作为** System Admin，
> **我想要** 每年维护各国公共假期和月度满勤天数，
> **以便** 系统自动计算每月标准出勤天数。

**验收标准:**
- 支持按国家/年度管理公共假期
- 自动计算每月满勤天数
- HR 可在特殊月份手动覆盖

### 4.2 功能优先级 (MoSCoW)

| 优先级 | 功能 | 说明 |
|--------|------|------|
| **Must** | 月度工资表创建（从 Salary Master 带出基本信息） | 核心流程入口 |
| **Must** | 考勤数据录入 / 确认（手动模式） | 无考勤系统时的保底方案 |
| **Must** | 基础资料确认 → HR已确认状态 | 流程关键节点 |
| **Must** | 薪资计算（月薪/时薪/日薪） | 核心功能 |
| **Must** | HR 审核 → 经理二级审核 | 审批流程 |
| **Must** | 全流程审计日志 | 合规要求 |
| **Should** | 从 TAC-timesheet 自动拉取考勤数据 | 自动化提升 |
| **Should** | 薪资日历参数管理（满勤天数自动计算） | 减少人工错误 |
| **Should** | 计算结果版本对比 | 可追溯性 |
| **Could** | 批量修改考勤数据 | 效率提升 |
| **Could** | 异常标记（如 0 出勤、薪资变动 >20%） | 风险控制 |
| **Won't (now)** | 完整的加班费自动计算 | 依赖考勤系统完善 |
| **Won't (now)** | JP/CN 薪资计算引擎 | 后续扩展 |

### 4.3 用户操作流程

```
Step 1: 创建月度工资表
┌─────────────────────────────────────────────────┐
│  月度薪资核算 > 新建                              │
│                                                 │
│  年度: [2026 ▼]  月份: [06 ▼]                    │
│  法人: [ENT-0002 TASG ▼]                        │
│  考勤来源: ○ 手动输入  ○ 从考勤系统导入            │
│                                                 │
│  当月满勤天数: [22] (来自薪资日历，可手动覆盖)      │
│  当月满勤小时: [176]                             │
│                                                 │
│  [取消]  [生成空工资表]                           │
└─────────────────────────────────────────────────┘

Step 2: 确认考勤 & 基础资料
┌─────────────────────────────────────────────────┐
│  MSS-SG-2026-06 | 状态: 草稿                     │
│                                                 │
│  员工列表:                                       │
│  ┌─────────────────────────────────────────────┐│
│  │ 编号     │ 姓名      │ 类型  │ 基本工资 │ 满勤│ 出勤│ 请假││
│  │ TASG251215│ KuanHua  │ 月薪 │ 6,000  │22  │ 21  │ 1  ││
│  │ TASG251216│ Alice    │ 月薪 │ 5,500  │22  │ 22  │ 0  ││
│  │ TASG251217│ Bob      │ 时薪 │ $25/hr │176 │ 160 │ 0  ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  [导入考勤数据(from Timesheet)] [批量设置出勤天数]  │
│  [保存草稿]  [基础资料确认 → 状态变更为HR已确认]    │
└─────────────────────────────────────────────────┘

Step 3: 薪资计算
┌─────────────────────────────────────────────────┐
│  MSS-SG-2026-06 | 状态: HR已确认                 │
│                                                 │
│  [执行薪资计算]                                  │
│                                                 │
│  计算结果 (版本 2):                              │
│  ┌─────────────────────────────────────────────┐│
│  │ 姓名      │ 应发   │ CPF   │ 扣除  │ 实发    ││
│  │ KuanHua  │6,227  │1,200 │1,200 │5,027   ││
│  │ Alice    │5,800  │1,100 │1,100 │4,700   ││
│  │ Bob      │4,000  │800   │800   │3,200   ││
│  └─────────────────────────────────────────────┘│
│  汇总: 应发 16,027 | 实发 12,927 | 雇主成本 19,080│
│                                                 │
│  [返回修改]  [HR审核通过]                         │
└─────────────────────────────────────────────────┘

Step 4: 经理审核
┌─────────────────────────────────────────────────┐
│  MSS-SG-2026-06 | 状态: HR已审核                 │
│                                                 │
│  [发送经理审核] → 状态变更为 经理审核中            │
│                                                 │
│  经理视图 (部门筛选):                             │
│  ┌─────────────────────────────────────────────┐│
│  │ 部门: Engineering                           ││
│  │ 姓名      │ 应发   │ 实发   │ 备注           ││
│  │ KuanHua  │6,227  │5,027  │               ││
│  │ Alice    │5,800  │4,700  │               ││
│  └─────────────────────────────────────────────┘│
│                                                 │
│  审核意见: [_______________]                     │
│  [退回HR修改]  [审核通过]                         │
└─────────────────────────────────────────────────┘
```

---

## 5. 实施路线图

### Phase 1: 核心数据模型 + 创建空工资表 (2-3 天)

**目标**: 建立新的数据表，实现从 Salary Master 生成月度空工资表

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 1.1 | 创建 `monthly_salary_sheets.json` 和 `monthly_salary_records.json` 数据文件 | 新建 |
| 1.2 | 实现 `normalize_monthly_sheet()` / `normalize_monthly_record()` 数据规范化函数 | `app.py` |
| 1.3 | 实现 `create_monthly_sheet()` — 从 Salary Master 生成空工资表 | `app.py` |
| 1.4 | 实现 `load_sheets()` / `save_sheets()` / `load_monthly_records()` / `save_monthly_records()` | `app.py` |
| 1.5 | 新建 "月度薪资核算" 列表页 (`/monthly-sheets`) | `app.py` |
| 1.6 | 新建创建工资表页面 (`/monthly-sheets/new`) | `app.py` |
| 1.7 | 三语翻译补充 (zh/ja/en) | `TRANSLATIONS` dict |

### Phase 2: 考勤录入 + 基础资料确认 (2-3 天)

**目标**: 实现 HR 确认考勤数据和工作流状态变更

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 2.1 | 实现工资表明细页面 (`/monthly-sheets/detail`) — 员工列表 + 可编辑考勤字段 | `app.py` |
| 2.2 | 实现单条记录编辑 (`/monthly-records/edit`) — 出勤天数、请假天数等 | `app.py` |
| 2.3 | 实现 `confirm_basic_info()` — 基础资料确认 → 状态变更为 `hr_confirmed` | `app.py` |
| 2.4 | 实现版本快照保存 (确认时自动保存 version 1) | `app.py` |
| 2.5 | 实现批量设置出勤天数 / 满勤天数 | `app.py` |
| 2.6 | 实现退回功能 (`hr_confirmed` → `draft`) | `app.py` |

### Phase 3: 薪资计算 + HR 审核 (2-3 天)

**目标**: 实现薪资计算引擎和 HR 审核流程

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 3.1 | 实现 `calculate_monthly_sheet()` — 月度薪资计算（增强版） | `app.py` |
| 3.2 | 计算结果以新版本保存 (version 2)，保留原始录入版本 | `app.py` |
| 3.3 | 实现计算结果页面 — 显示计算前后对比 | `app.py` |
| 3.4 | 支持 HR 对计算结果进行逐条微调 | `app.py` |
| 3.5 | 实现 HR 审核通过 → `hr_reviewed` 状态 | `app.py` |
| 3.6 | 实现退回重算功能 (`hr_reviewed` → `hr_confirmed`) | `app.py` |

### Phase 4: 经理审核 + 发放流程对接 (2-3 天)

**目标**: 实现二级审核和与现有发放流程对接

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 4.1 | 新增 `tacaipay_sg.manager_review` 权限 | `app.py` |
| 4.2 | 实现发送经理审核 → `manager_review` 状态 | `app.py` |
| 4.3 | 实现经理审核页面 (部门筛选视图) | `app.py` |
| 4.4 | 实现经理批准 / 退回 + 审核意见 | `app.py` |
| 4.5 | 实现 `manager_approved` → `finalized` 对接现有发放流程 | `app.py` |
| 4.6 | 工资表关闭后同步回现有 `payroll_batches` (兼容) | `app.py` |

### Phase 5: 薪资日历参数 (2-3 天)

**目标**: 建立多国薪资日历参数系统

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 5.1 | 创建 `payroll_calendar.json` 数据模型 | 新建 |
| 5.2 | 实现薪资日历管理页面 (`/calendars`) | `app.py` |
| 5.3 | 实现日历创建/编辑 — 公共假期录入 | `app.py` |
| 5.4 | 实现自动计算每月满勤天数 | `app.py` |
| 5.5 | 创建工资表时自动匹配满勤天数 | `app.py` |

### Phase 6: TAC-timesheet 考勤集成 (2-3 天)

**目标**: 从 TAC-timesheet 自动拉取月度考勤汇总

| 任务 | 描述 | 涉及文件 |
|------|------|---------|
| 6.1 | 在 TAC-timesheet 新增 `/api/payroll/attendance-summary` 端点 | timesheet `app.py` |
| 6.2 | 在 tacaipaysg 实现 `fetch_timesheet_attendance()` 集成函数 | `app.py` |
| 6.3 | 创建工资表时可选"从考勤系统导入" | `app.py` |
| 6.4 | 考勤数据映射 (timesheet 字段 → payroll 字段) | `app.py` |
| 6.5 | 异常处理 (timesheet 不可用时的 fallback) | `app.py` |

### Phase 7: 测试 + 文档 + 验收 (1-2 天)

| 任务 | 描述 |
|------|------|
| 7.1 | 端到端手动测试 (按测试清单) |
| 7.2 | 三语 UI 验证 |
| 7.3 | 审计日志完整性验证 |
| 7.4 | 更新 README 和设计文档 |
| 7.5 | 更新 `memory/tacaipaysg.md` |

---

## 6. 数据模型设计

### 6.1 新增 JSON 文件

| 文件 | 用途 | 索引键 |
|------|------|--------|
| `monthly_salary_sheets.json` | 月度工资表头 | `sheet_id` |
| `monthly_salary_records.json` | 月度工资表明细 | `record_id` |
| `payroll_calendar.json` | 多国薪资日历 | `calendar_id` |

### 6.2 Sheet 状态枚举

```python
SHEET_STATUSES = [
    "draft",              # 草稿
    "hr_confirmed",       # HR已确认（基础资料确认完毕）
    "calculated",         # 已计算
    "hr_reviewed",        # HR已审核
    "manager_review",     # 经理审核中
    "manager_approved",   # 经理已批准
    "finalized",          # 已确认（对接现有发放流程）
    "correction",         # 修正中
    "voided",             # 已作废
]
```

### 6.3 Record 状态枚举

```python
RECORD_STATUSES = [
    "draft",              # 草稿
    "hr_confirmed",       # HR已确认
    "calculated",         # 已计算
    "hr_adjusted",        # HR调整后
]
```

---

## 7. 状态机设计

### 7.1 Sheet 状态转换表

| 当前状态 | 允许转换到 | 触发动作 | 所需权限 |
|---------|-----------|---------|---------|
| `draft` | `hr_confirmed` | 基础资料确认 | `tacaipay_sg.manage` |
| `hr_confirmed` | `draft` | 退回修改 | `tacaipay_sg.manage` |
| `hr_confirmed` | `calculated` | 执行薪资计算 | `tacaipay_sg.calculate` |
| `calculated` | `hr_confirmed` | 退回重确认 | `tacaipay_sg.manage` |
| `calculated` | `hr_reviewed` | HR审核通过 | `tacaipay_sg.approve` |
| `hr_reviewed` | `calculated` | 退回重算 | `tacaipay_sg.approve` |
| `hr_reviewed` | `manager_review` | 发送经理审核 | `tacaipay_sg.approve` |
| `manager_review` | `hr_reviewed` | 经理退回 | `tacaipay_sg.manager_review` |
| `manager_review` | `manager_approved` | 经理批准 | `tacaipay_sg.manager_review` |
| `manager_approved` | `finalized` | 最终确认 | `tacaipay_sg.approve` |
| `manager_approved` | `hr_reviewed` | 退回HR | `tacaipay_sg.manager_review` |
| any | `correction` | 标记修正 | `tacaipay_sg.manage` |
| any | `voided` | 作废 | `tacaipay_sg.manage` |

### 7.2 版本管理规则

```
版本 1: 基础资料确认时保存 (hr_confirmed)
  - 包含: 员工快照 + 考勤数据 + 输入值
  - 不可修改 (immutable snapshot)

版本 2: 薪资计算后保存 (calculated)
  - 包含: 版本1 全部 + 计算结果
  - HR 可在 calculated 状态微调后重新计算 (版本 2.x)

版本 3 (如需要): 经理退回后重算
  - 退回 → 修改 → 重新确认 → 重新计算
```

---

## 8. API / 路由设计

### 8.1 新增 GET 路由

| 路由 | 页面 | 权限 |
|------|------|------|
| `/monthly-sheets` | 月度薪资核算列表 | `tacaipay_sg.view` |
| `/monthly-sheets/new` | 新建月度工资表 | `tacaipay_sg.manage` |
| `/monthly-sheets/detail?sheet_id=X` | 工资表明细（员工列表） | `tacaipay_sg.view` |
| `/monthly-records/edit?record_id=X` | 单条记录编辑 | `tacaipay_sg.manage` |
| `/monthly-sheets/calculate?sheet_id=X` | 计算结果页面 | `tacaipay_sg.view` |
| `/calendars` | 薪资日历列表 | `tacaipay_sg.view` |
| `/calendars/new` | 新建薪资日历 | `tacaipay_sg.manage` |
| `/calendars/edit?calendar_id=X` | 编辑薪资日历 | `tacaipay_sg.manage` |

### 8.2 新增 POST 路由

| 路由 | 动作 | 权限 |
|------|------|------|
| `/monthly-sheets/create` | 创建空工资表 | `tacaipay_sg.manage` |
| `/monthly-sheets/confirm-basic-info` | 基础资料确认 | `tacaipay_sg.manage` |
| `/monthly-sheets/calculate` | 执行薪资计算 | `tacaipay_sg.calculate` |
| `/monthly-sheets/hr-approve` | HR审核通过 | `tacaipay_sg.approve` |
| `/monthly-sheets/send-manager-review` | 发送经理审核 | `tacaipay_sg.approve` |
| `/monthly-sheets/manager-approve` | 经理批准 | `tacaipay_sg.manager_review` |
| `/monthly-sheets/manager-reject` | 经理退回 | `tacaipay_sg.manager_review` |
| `/monthly-sheets/finalize` | 最终确认 | `tacaipay_sg.approve` |
| `/monthly-records/save` | 保存单条记录 | `tacaipay_sg.manage` |
| `/monthly-sheets/batch-set-attendance` | 批量设置考勤 | `tacaipay_sg.manage` |
| `/calendars/save` | 保存薪资日历 | `tacaipay_sg.manage` |
| `/monthly-sheets/import-timesheet` | 从考勤系统导入 | `tacaipay_sg.manage` |

---

## 9. UI 页面设计

### 9.1 导航变更

在现有导航栏增加一项:

```
Dashboard | 薪资主数据 | 月度薪资核算 (新) | 月度工资表 (旧) | 报表 | 参数 | 审计
```

或者将 "月度工资表" 改为下拉菜单:
```
月度薪资 ▼
├── 薪资核算 (新流程)
└── 工资表 (现有流程)
```

### 9.2 页面布局 (遵循 SAP/Fiori 风格)

所有新页面遵循现有 UI 模式:
- `sap-page-header` — 页面标题 + 副标题
- `card` — 内容卡片
- `section-header` — 段落标题
- `form-grid` — 表单布局
- `table-scroll` — 数据表格
- `sap-toolbar` — 操作按钮栏
- `metric-card` — KPI 指标卡
- `message-strip` — 提示信息
- `badge` — 状态标签

---

## 10. 跨模块集成方案

### 10.1 TAC-timesheet → tacaipaysg 考勤集成

**TAC-timesheet 新增端点:**
```python
# TAC-timesheet/backend/app.py
GET /api/payroll/attendance-summary?country_code=SG&month=2026-06&entity_id=ENT-0002

Response:
{
  "month": "2026-06",
  "employees": [
    {
      "employee_id": "EMP-0035",
      "employee_number": "TASG251215",
      "total_work_days": 21,
      "total_work_hours": 168,
      "total_overtime_hours": 5.5,
      "total_late_night_hours": 2.0,
      "total_holiday_hours": 0,
      "total_paid_leave_days": 1,
      "total_unpaid_leave_days": 0,
      "absence_days": 0
    }
  ]
}
```

**tacaipaysg 集成函数:**
```python
def fetch_timesheet_attendance(month, entity_id, session_id):
    """从 TAC-timesheet 拉取月度考勤汇总"""
    url = f"{TIMESHEET_INTERNAL_BASE_URL}/api/payroll/attendance-summary"
    params = {"country_code": "SG", "month": month, "entity_id": entity_id}
    # HTTP GET → 解析 → 返回考勤映射
```

### 10.2 与现有 Batch 流程的兼容

- 增强版工资表在 `manager_approved` → `finalized` 后，自动创建一条对应的 `payroll_batches` 记录
- 使得后续的 payslip 生成、邮件发送、财务发放等现有流程无缝衔接

---

## 11. 测试与验收标准

### 11.1 手动测试清单

#### Phase 1 测试
- [ ] 创建月度空工资表，验证员工数量与 Salary Master 一致
- [ ] 验证带入字段完整性 (编号、姓名、类型、基本工资、满勤天数等)
- [ ] 验证当月满勤天数自动匹配
- [ ] 验证不同法人数据隔离

#### Phase 2 测试
- [ ] 修改单条记录的出勤天数、请假天数
- [ ] 批量设置出勤天数
- [ ] 基础资料确认 → 状态变为 `hr_confirmed`
- [ ] 版本快照保存验证
- [ ] 退回功能 → `hr_confirmed` → `draft`
- [ ] 确认后不可修改原始录入（除非退回）

#### Phase 3 测试
- [ ] 月薪员工计算: base × work_days/standard_days
- [ ] 时薪员工计算: rate × hours
- [ ] 日薪员工计算: rate × days
- [ ] CPF 计算 (manual / parameter_assisted)
- [ ] SDL / FWL 计算
- [ ] 汇总数据验证 (应发/实发/雇主成本合计)
- [ ] 计算结果版本独立保存
- [ ] HR 微调后重算

#### Phase 4 测试
- [ ] 发送经理审核 → 状态变更
- [ ] 经理部门筛选视图
- [ ] 经理批准 / 退回 + 审核意见
- [ ] 退回后重走流程
- [ ] 对接现有发放流程

#### Phase 5 测试
- [ ] 创建 SG/JP/CN 薪资日历
- [ ] 公共假期录入
- [ ] 自动计算月度满勤天数
- [ ] 手动覆盖满勤天数

#### Phase 6 测试
- [ ] 从 TAC-timesheet 拉取考勤数据
- [ ] Timesheet 不可用时的 fallback
- [ ] 考勤数据覆盖 / 合并逻辑

### 11.2 审计日志验证

每个状态变更必须记录:
```json
{
  "module": "tacaipaysg.monthly_sheet",
  "record_id": "MSS-SG-2026-06",
  "action": "confirm_basic_info",
  "user": "HR Officer",
  "timestamp": "2026-06-25T10:30:00+00:00",
  "before_value": { "status": "draft" },
  "after_value": { "status": "hr_confirmed" }
}
```

### 11.3 权限验证矩阵

| 操作 | 所需权限 | HR Officer | HR Manager | Dept Manager | Finance |
|------|---------|-----------|-----------|-------------|---------|
| 创建工资表 | `manage` | ✅ | ✅ | ❌ | ❌ |
| 确认基础资料 | `manage` | ✅ | ✅ | ❌ | ❌ |
| 执行计算 | `calculate` | ✅ | ✅ | ❌ | ❌ |
| HR审核 | `approve` | ❌ | ✅ | ❌ | ❌ |
| 经理审核 | `manager_review` | ❌ | ❌ | ✅ | ❌ |
| 财务放行 | `release_payment` | ❌ | ❌ | ❌ | ✅ |

---

## 附录 A: 文件变更清单

| 文件 | 操作 | Phase |
|------|------|-------|
| `TACAIPAY/tacaipaysg/database/monthly_salary_sheets.json` | 新建 | P1 |
| `TACAIPAY/tacaipaysg/database/monthly_salary_records.json` | 新建 | P1 |
| `TACAIPAY/tacaipaysg/database/payroll_calendar.json` | 新建 | P5 |
| `TACAIPAY/tacaipaysg/backend/app.py` | 修改 | P1-P6 |
| `TACAIPAY/tacaipaysg/i18n/zh.json` | 修改 | P1 |
| `TACAIPAY/tacaipaysg/i18n/ja.json` | 修改 | P1 |
| `TACAIPAY/tacaipaysg/i18n/en.json` | 修改 | P1 |
| `TACAIPAY/tacaipaysg/docs/SG_Payroll_Design.md` | 更新 | P7 |
| `TACAIPAY/tacaipaysg/README.md` | 更新 | P7 |
| `TAC-timesheet/backend/app.py` | 修改 (新增API) | P6 |
| `memory/tacaipaysg.md` | 更新 | P7 |

## 附录 B: 与现有功能的共存策略

1. **新老并存**: 现有 `/batches` 路由和页面保持不变，新增 `/monthly-sheets` 路由
2. **导航区分**: "月度工资表" (旧) vs "月度薪资核算" (新)
3. **发放流程复用**: 新流程 `finalized` 后自动对接现有 `payroll_batches`，复用 payslip 生成 / 邮件 / 财务发放
4. **渐进迁移**: 新流程稳定后，可将旧 batch 流程标记为 deprecated

---

> 📅 本文档由 **亚太薪酬专家 + IT架构专家 + 产品专家** 三方视角共同制定。
> 总预估工期: **14-20 天** (7 个 Phase，每 Phase 2-3 天)。
