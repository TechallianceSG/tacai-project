-- TACAI Pay JP — Migration 003: Add allowance fields
-- Date: 2026-07-01
-- Purpose: Add transport allowance, phone allowance, and project bonus fields
--          to salary master and monthly salary records tables.

-- Salary Master table
ALTER TABLE pay_jp_salary_master
  ADD COLUMN IF NOT EXISTS transport_allowance NUMERIC(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS phone_allowance NUMERIC(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS project_bonus NUMERIC(12,2) DEFAULT 0;

-- Monthly Salary Records table
ALTER TABLE pay_jp_monthly_salary_records
  ADD COLUMN IF NOT EXISTS transport_allowance NUMERIC(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS phone_allowance NUMERIC(12,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS project_bonus NUMERIC(12,2) DEFAULT 0;
