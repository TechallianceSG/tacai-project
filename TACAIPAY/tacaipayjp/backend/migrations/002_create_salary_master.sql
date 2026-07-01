-- TACAI Pay JP — Salary Master table (薪资主数据)
DROP TABLE IF EXISTS pay_jp_salary_master CASCADE;
CREATE TABLE pay_jp_salary_master (
    id                  SERIAL PRIMARY KEY,
    salary_master_id    VARCHAR(50)  NOT NULL UNIQUE,
    employee_id         VARCHAR(50)  NOT NULL,
    employee_number     VARCHAR(50)  NOT NULL,
    employee_name       VARCHAR(200) NOT NULL,
    email               VARCHAR(200),
    country_code        VARCHAR(5)   DEFAULT 'JP',
    entity_id           VARCHAR(50),
    department          VARCHAR(100),
    department_id       VARCHAR(50),
    department_label    VARCHAR(200),
    team_id             VARCHAR(50),
    team_label          VARCHAR(200),
    employment_status   VARCHAR(30)  DEFAULT 'active',
    employeeadmin_status VARCHAR(30),
    employeeadmin_payroll_ready BOOLEAN DEFAULT false,
    employeeadmin_readiness_percent NUMERIC DEFAULT 0,
    employeeadmin_last_seen_at TIMESTAMP,

    -- Salary type & base
    salary_type         VARCHAR(20)  NOT NULL DEFAULT 'monthly',
    basic_salary        NUMERIC(12,2) DEFAULT 0,
    hourly_rate         NUMERIC(12,2) DEFAULT 0,
    daily_rate          NUMERIC(12,2) DEFAULT 0,
    standard_work_days  NUMERIC(5,1)  DEFAULT 22,
    standard_work_hours NUMERIC(6,1)  DEFAULT 176,
    standard_monthly_hours NUMERIC(6,1) DEFAULT 160,
    overtime_hourly_rate NUMERIC(12,2) DEFAULT 0,

    -- JP allowances (各種手当)
    commute_allowance   NUMERIC(12,2) DEFAULT 0,   -- 通勤手当
    housing_allowance   NUMERIC(12,2) DEFAULT 0,   -- 住宅手当
    family_allowance    NUMERIC(12,2) DEFAULT 0,   -- 家族手当
    position_allowance  NUMERIC(12,2) DEFAULT 0,   -- 役職手当
    fixed_allowance     NUMERIC(12,2) DEFAULT 0,   -- その他固定手当
    performance_bonus   NUMERIC(12,2) DEFAULT 0,   -- 绩效工资 参考値

    -- Fixed overtime (固定残業代 / みなし残業)
    fixed_overtime_hours  NUMERIC(6,1)  DEFAULT 0,    -- みなし残業時間数
    fixed_overtime_amount NUMERIC(12,2) DEFAULT 0,    -- 固定残業代 月額

    -- Deductions
    recurring_deductions NUMERIC(12,2) DEFAULT 0,   -- 定期控除（社宅費など）

    -- Social insurance (社保加入判定)
    social_insurance_eligible   BOOLEAN DEFAULT true,    -- 社会保険 加入対象
    employment_insurance_eligible BOOLEAN DEFAULT true,  -- 雇用保険 加入対象
    social_insurance_grade_health NUMERIC(5,0),         -- 健保等級
    social_insurance_grade_pension NUMERIC(5,0),        -- 厚生年金等級
    standard_monthly_remuneration NUMERIC(12,2),        -- 標準報酬月額

    -- Tax (税関連)
    dependents_count    INTEGER DEFAULT 0,              -- 扶養家族数
    monthly_resident_tax NUMERIC(12,2) DEFAULT 0,       -- 住民税 月額
    prefecture_code     VARCHAR(5)  DEFAULT '13',        -- 都道府県コード（健保料率用）

    -- Age (for nursing care insurance)
    age_at_fiscal_year_start INTEGER DEFAULT 0,         -- 年度初めの年齢

    -- Bank info
    bank_name           VARCHAR(100),
    bank_branch_name    VARCHAR(100),
    bank_account_type   VARCHAR(20),
    bank_account_name   VARCHAR(200),
    bank_account_number VARCHAR(50),

    -- Currency & status
    payroll_currency    VARCHAR(10) DEFAULT 'JPY',
    active              BOOLEAN DEFAULT true,
    deactivated_at      TIMESTAMP,
    deactivated_by      VARCHAR(100),
    deactivation_reason TEXT,
    notes               TEXT,
    source              VARCHAR(30) DEFAULT 'manual',
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_pjp_sm_employee ON pay_jp_salary_master(employee_id);
CREATE INDEX idx_pjp_sm_entity ON pay_jp_salary_master(entity_id);
CREATE INDEX idx_pjp_sm_active ON pay_jp_salary_master(active) WHERE active = true;
CREATE INDEX idx_pjp_sm_type ON pay_jp_salary_master(salary_type);
