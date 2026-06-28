#!/usr/bin/env python3
"""Dependency-free TAC-salary APAC payroll v2 smoke test.

The test imports backend/app.py, redirects all JSON stores and payslip output to a
temporary directory, and exercises the local MVP workflow without mutating the
real project database.
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = PROJECT_ROOT / "backend" / "app.py"


def load_app():
    spec = importlib.util.spec_from_file_location("tac_salary_app", APP_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load backend/app.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def redirect_database(app, root: Path) -> None:
    data_dir = root / "database"
    payslip_dir = root / "payslips"
    mapping = {
        "SALARY_FILE": data_dir / "salary_records.json",
        "EMPLOYEE_FILE": data_dir / "employees.json",
        "AUDIT_FILE": data_dir / "audit_logs.json",
        "PAYROLL_BATCHES_FILE": data_dir / "payroll_batches.json",
        "PAYROLL_RECORDS_JP_FILE": data_dir / "payroll_records_jp.json",
        "PAYROLL_RECORDS_SG_FILE": data_dir / "payroll_records_sg.json",
        "PAYROLL_RECORDS_CN_FILE": data_dir / "payroll_records_cn.json",
        "SALARY_MASTER_FILE": data_dir / "salary_master.json",
        "PAYROLL_PARAMETERS_FILE": data_dir / "payroll_parameters.json",
        "PAYROLL_NOTICES_FILE": data_dir / "payroll_notices.json",
        "PAYSLIP_DOCUMENTS_FILE": data_dir / "payslip_documents.json",
        "EMPLOYEE_FEEDBACK_FILE": data_dir / "employee_feedback.json",
        "PAYROLL_CONFIRMATIONS_FILE": data_dir / "payroll_confirmations.json",
        "PAYMENT_RECORDS_FILE": data_dir / "payment_records.json",
        "PAYROLL_IMPORT_RUNS_FILE": data_dir / "payroll_import_runs.json",
    }
    app.PROJECT_ROOT = root
    app.DATA_DIR = data_dir
    app.PAYSLIP_DIR = payslip_dir
    for name, path in mapping.items():
        setattr(app, name, path)
    app.ALL_JSON_FILES = tuple(mapping.values())
    app.PAYROLL_RECORD_FILES = {
        "JP": app.PAYROLL_RECORDS_JP_FILE,
        "SG": app.PAYROLL_RECORDS_SG_FILE,
        "CN": app.PAYROLL_RECORDS_CN_FILE,
    }
    app.ensure_database()


def create_profile(app, country: str, entity_id: str, employee_id: str, city_code: str = "") -> dict:
    payload = {
        "country_code": country,
        "entity_id": entity_id,
        "employee_id": employee_id,
        "employee_name": f"Smoke {employee_id}",
        "employee_no": employee_id,
        "base_salary": 10000,
        "position_allowance": 100,
        "commute_allowance": 50,
        "housing_allowance": 0,
        "other_allowance": 0,
        "effective_from": "2099-01-01",
        "contract_start_date": "2099-01-01",
        "rule_type": "monthly_fixed",
        "base_rate": 10000,
        "status": "active",
        "user": "smoke_test",
    }
    if country == "JP":
        payload.update({"overtime_hours": 10, "late_night_hours": 2, "holiday_work_hours": 1})
    if country == "SG":
        payload.update({"cpf_input_mode": "parameter_assisted", "cpf_ordinary_wage": 10000, "cpf_employee": 100, "cpf_employer": 120})
    if country == "CN":
        payload.update({"city_code": city_code or "SHANGHAI", "social_insurance_employee": 90, "housing_fund_employee": 80, "individual_income_tax": 70, "social_insurance_employer": 150, "housing_fund_employer": 110})
    record = app.normalize_salary_master(payload)
    records = app.read_json(app.SALARY_MASTER_FILE)
    records.append(record)
    app.write_json(app.SALARY_MASTER_FILE, records)
    return record


def main() -> None:
    app = load_app()
    with tempfile.TemporaryDirectory(prefix="tac-salary-smoke-") as tmp:
        redirect_database(app, Path(tmp))
        create_profile(app, "JP", "ENT-0001", "EMP-JP-001")
        create_profile(app, "SG", "ENT-0002", "EMP-SG-001")
        create_profile(app, "CN", "ENT-0005", "EMP-CN-001", "SHANGHAI")

        jp_batch = app.create_batch({"country_code": "JP", "entity_id": "ENT-0001", "payroll_month": "2099-01", "user": "smoke_test"})
        sg_batch = app.create_batch({"country_code": "SG", "entity_id": "ENT-0002", "payroll_month": "2099-01", "user": "smoke_test"})
        cn_batch = app.create_batch({"country_code": "CN", "entity_id": "ENT-0005", "payroll_month": "2099-01", "user": "smoke_test"})
        app.create_parameter({"country_code": "JP", "entity_id": "ENT-0001", "effective_start_date": "2099-01-01", "parameter_type": "jp_overtime_statutory", "status": "active", "values": {"standard_hours_per_month": 160, "overtime_multiplier": 1.25, "late_night_multiplier": 1.5, "holiday_work_multiplier": 1.35, "health_insurance_employee_rate": 0.05, "health_insurance_employer_rate": 0.05}, "user": "smoke_test"})
        app.create_parameter({"country_code": "SG", "entity_id": "ENT-0002", "effective_start_date": "2099-01-01", "parameter_type": "sg_cpf", "status": "active", "values": {"cpf_employee_rate": 0.08, "cpf_employer_rate": 0.17, "ordinary_wage_ceiling": 20000}, "user": "smoke_test"})
        app.create_parameter({"country_code": "CN", "entity_id": "ENT-0005", "city_code": "SHANGHAI", "effective_start_date": "2099-01-01", "parameter_type": "cn_city_social_housing_iit", "status": "active", "values": {"social_insurance_employee_rate": 0.10, "social_insurance_employer_rate": 0.20, "housing_fund_employee_rate": 0.07, "housing_fund_employer_rate": 0.07, "iit_monthly_threshold": 5000, "iit_rate": 0.03}, "user": "smoke_test"})

        loaded = app.load_employees_for_batch(jp_batch["batch_id"], {"user": "smoke_test", "allow_salary_master_fallback": True})
        assert loaded["loaded_count"] == 1, loaded
        calculated = app.calculate_batch(jp_batch["batch_id"], {"user": "smoke_test"})
        assert calculated["records"][0]["contract_snapshot"]["contract_start_date"] == "2099-01-01", calculated["records"][0]
        assert calculated["records"][0]["salary_calculation_rule_snapshot"]["rule_type"] == "monthly_fixed", calculated["records"][0]
        assert calculated["records"][0]["earnings"]["overtime_pay"] > 0, calculated["records"][0]
        assert calculated["records"][0]["deductions"]["health_insurance"] > 0, calculated["records"][0]
        assert any("JP overtime calculated" in message for message in calculated["records"][0]["calculation_messages"]), calculated["records"][0]
        record_id = calculated["records"][0]["payroll_record_id"]

        sg_loaded = app.load_employees_for_batch(sg_batch["batch_id"], {"user": "smoke_test", "allow_salary_master_fallback": True})
        assert sg_loaded["loaded_count"] == 1, sg_loaded
        sg_calculated = app.calculate_batch(sg_batch["batch_id"], {"user": "smoke_test"})
        assert sg_calculated["records"][0]["deductions"]["cpf_employee"] == 800.0, sg_calculated["records"][0]
        assert sg_calculated["records"][0]["employer_costs"]["cpf_employer"] == 1700.0, sg_calculated["records"][0]
        assert any("SG CPF calculated" in message for message in sg_calculated["records"][0]["calculation_messages"]), sg_calculated["records"][0]

        cn_loaded = app.load_employees_for_batch(cn_batch["batch_id"], {"user": "smoke_test", "allow_salary_master_fallback": True})
        assert cn_loaded["loaded_count"] == 1, cn_loaded
        cn_calculated = app.calculate_batch(cn_batch["batch_id"], {"user": "smoke_test"})
        assert cn_calculated["records"][0]["deductions"]["social_insurance_employee"] > 0, cn_calculated["records"][0]
        assert cn_calculated["records"][0]["deductions"]["housing_fund_employee"] > 0, cn_calculated["records"][0]
        assert cn_calculated["records"][0]["deductions"]["individual_income_tax"] > 0, cn_calculated["records"][0]
        assert any("CN SHANGHAI" in message for message in cn_calculated["records"][0]["calculation_messages"]), cn_calculated["records"][0]

        app.update_payroll_record(record_id, {"deductions": {"income_tax": 100}, "jp_fields": {"late_night_hours": 1.5}, "user": "smoke_test"})
        app.adjust_record(record_id, {"amount": -25, "reason": "Smoke correction", "user": "smoke_test"})
        app.calculate_batch(jp_batch["batch_id"], {"user": "smoke_test"})
        app.create_notices(jp_batch["batch_id"], "first", {"user": "smoke_test"})
        app.create_confirmation(jp_batch["batch_id"], "first", {"user": "first_checker"})
        app.create_confirmation(jp_batch["batch_id"], "second", {"user": "second_checker"})
        app.create_notices(jp_batch["batch_id"], "final", {"user": "smoke_test"})
        app.finalize_batch(jp_batch["batch_id"], {"user": "smoke_test"})
        try:
            app.adjust_record(record_id, {"amount": 1, "reason": "Should fail", "user": "smoke_test"})
        except ValueError:
            pass
        else:
            raise AssertionError("Finalized payroll record accepted direct adjustment")
        payment = app.prepare_payment(jp_batch["batch_id"], {"payment_method": "manual_bank_transfer", "reference_number": "SMOKE-PREP", "user": "smoke_test"})
        assert payment["payment_status"] == "prepared", payment
        prepared_rows = app.batch_records(jp_batch["batch_id"], "JP")
        assert prepared_rows[0]["status"] == "payment_prepared", prepared_rows[0]
        export_name, export_content = app.payment_export_csv(jp_batch["batch_id"], "smoke_test")
        assert export_name.endswith(".csv") and "EMP-JP-001" in export_content, export_content
        paid = app.mark_payment_paid(jp_batch["batch_id"], {"reference_number": "SMOKE-PAID", "user": "smoke_test"})
        assert paid["payment_status"] == "paid", paid
        paid_rows = app.batch_records(jp_batch["batch_id"], "JP")
        assert paid_rows[0]["status"] == "paid", paid_rows[0]
        archived = app.archive_batch(jp_batch["batch_id"], {"user": "smoke_test"})
        assert archived["status"] == "archived", archived
        payslips = app.generate_payslips(jp_batch["batch_id"], {"user": "smoke_test"})
        assert payslips["generated_count"] == 1, payslips
        app.create_parameter({"country_code": "CN", "entity_id": "ENT-0005", "city_code": "SHANGHAI", "parameter_type": "manual_cn_city", "values": {"note": "smoke"}, "user": "smoke_test"})
        feedback = app.create_feedback({"batch_id": jp_batch["batch_id"], "employee_id": "EMP-JP-001", "message": "Smoke feedback", "user": "EMP-JP-001"})
        app.resolve_feedback(feedback["feedback_id"], {"resolution": "Smoke resolved", "user": "smoke_test"})
        report = app.payroll_report("net-pay")
        assert report["rows"], report
        assert app.read_json(app.AUDIT_FILE), "Audit log should not be empty"
        for path in app.ALL_JSON_FILES:
            data = json.loads(path.read_text(encoding="utf-8"))
            assert isinstance(data, list), f"{path} is not a JSON array"
    print("TAC-salary v2 smoke test passed")


if __name__ == "__main__":
    main()
