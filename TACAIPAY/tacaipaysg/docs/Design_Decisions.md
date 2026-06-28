# TACAIPAY SG — Design Decisions / 设计定义

## Performance Bonus 绩效工资 — 薪资主数据 → 月度工资表 数据流

### 规则定义

| 字段 | 来源 | 初始值 | 说明 |
|------|------|--------|------|
| `performance_reference` (绩效参考) | 薪资主数据 `performance_bonus` | 薪资主数据中的值 | **只读参考值**，提示HR该员工在薪资主数据中登记的月度绩效工资标准 |
| `performance_bonus` (绩效工资) | — | **0** | **每月由HR手工输入**，根据当月实际绩效评定结果填写 |

### 设计原因

1. **计算准确性**：绩效工资是月度浮动项，每月金额可能不同。若自动带入薪资主数据的值，HR可能在未核实当月实际绩效的情况下直接使用默认值，导致工资计算错误。
2. **强制确认机制**：将 `performance_bonus` 默认为 0，要求HR每月主动输入，确保绩效工资经过人工确认后再参与计算。
3. **审计可追溯**：`performance_reference` 保存薪资主数据的参考标准，`performance_bonus` 保存当月实际发放值，两者对比可清晰看到差异。

### 数据流

```
薪资主数据 (Salary Master)
  └─ performance_bonus: 500  (员工登记的月度绩效标准)
       │
       ▼
月度工资表创建 (Create Monthly Sheet)
  ├─ performance_reference: 500  ← 从薪资主数据带入，作为参考
  └─ performance_bonus: 0        ← 强制为0，等待HR手工输入当月实际值
       │
       ▼
HR 在 Payroll Input 界面
  └─ 根据当月实际绩效，手工输入 performance_bonus: 450
       │
       ▼
工资计算 (Calculation)
  └─ gross = base + allowance + performance_bonus + bonus + other_payment
```

### 适用范围

- 月度薪资核算（Monthly Salary Sheet）创建流程
- 所有薪资类型（monthly / hourly / daily / monthly_hour）
- 国家：SG

### 非 Bug 声明

此行为是**刻意设计（by design）**，不是系统Bug。代码审查和测试时请勿将其标记为问题。

---

*最后更新：2026-06-26*
