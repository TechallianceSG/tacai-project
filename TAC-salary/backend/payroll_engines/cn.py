"""China payroll city parameter-assisted calculation hooks."""

from __future__ import annotations

from .core import apply_rate, money, message, normalize_city, parameter_label, parameter_values, pick_parameter, rate

SUPPORTED_CITY_CODES = {"SHANGHAI", "NANJING", "XIAN", "WUHU"}


def _resolve_city(cn_fields: dict, record: dict) -> str:
    for value in (
        cn_fields.get("city_code"),
        cn_fields.get("social_insurance_city"),
        cn_fields.get("housing_fund_city"),
        cn_fields.get("work_city"),
        record.get("employee_snapshot", {}).get("work_city"),
    ):
        city = normalize_city(value)
        if city in SUPPORTED_CITY_CODES:
            return city
    return ""


def apply(record: dict, parameters: list[dict]) -> dict:
    cn_fields = dict(record.get("cn_fields") or {})
    deductions = dict(record.get("deductions") or {})
    employer_costs = dict(record.get("employer_costs") or {})
    city = _resolve_city(cn_fields, record)
    if city:
        cn_fields["city_code"] = city
    else:
        message(record, "CN city parameter calculation skipped; city_code is missing or unsupported.")
        record["cn_fields"] = cn_fields
        return record

    parameter = pick_parameter(parameters, "cn_city", "cn_social", "manual_cn_city", city_code=city)
    if not parameter:
        message(record, f"CN {city} social insurance/housing fund/IIT kept as manual amounts; no active city parameter found.")
        record["cn_fields"] = cn_fields
        return record

    values = parameter_values(parameter)
    earnings = dict(record.get("earnings") or {})
    gross = sum(money(value) for value in earnings.values())
    si_base = money(values.get("social_insurance_base")) or gross
    hf_base = money(values.get("housing_fund_base")) or si_base
    calculated = False

    if "social_insurance_employee_rate" in values:
        cn_fields["social_insurance_employee"] = apply_rate(si_base, values.get("social_insurance_employee_rate"))
        deductions["social_insurance_employee"] = cn_fields["social_insurance_employee"]
        calculated = True
    if "social_insurance_employer_rate" in values:
        cn_fields["social_insurance_employer"] = apply_rate(si_base, values.get("social_insurance_employer_rate"))
        employer_costs["social_insurance_employer"] = cn_fields["social_insurance_employer"]
        calculated = True
    if "housing_fund_employee_rate" in values:
        cn_fields["housing_fund_employee"] = apply_rate(hf_base, values.get("housing_fund_employee_rate"))
        deductions["housing_fund_employee"] = cn_fields["housing_fund_employee"]
        calculated = True
    if "housing_fund_employer_rate" in values:
        cn_fields["housing_fund_employer"] = apply_rate(hf_base, values.get("housing_fund_employer_rate"))
        employer_costs["housing_fund_employer"] = cn_fields["housing_fund_employer"]
        calculated = True

    threshold = money(values.get("iit_monthly_threshold"))
    special_deduction = money(cn_fields.get("special_additional_deduction"))
    taxable_income = money(values.get("taxable_income_current_month")) or max(0.0, gross - money(deductions.get("social_insurance_employee")) - money(deductions.get("housing_fund_employee")) - special_deduction - threshold)
    iit_rate = rate(values.get("iit_rate"))
    quick_deduction = money(values.get("iit_quick_deduction"))
    if iit_rate > 0:
        cn_fields["taxable_income_current_month"] = taxable_income
        cn_fields["individual_income_tax"] = max(0.0, round(taxable_income * iit_rate - quick_deduction, 2))
        deductions["individual_income_tax"] = cn_fields["individual_income_tax"]
        calculated = True

    if calculated:
        cn_fields["calculation_method"] = "parameter_assisted"
        cn_fields["city_parameter_id"] = parameter.get("parameter_id", "")
        cn_fields["social_insurance_base"] = si_base
        cn_fields["housing_fund_base"] = hf_base
        message(record, f"CN {city} social insurance/housing fund/IIT calculated by {parameter_label(parameter)}.")
    else:
        message(record, f"CN city parameter {parameter_label(parameter)} has no supported rate values; manual values kept.")

    record["cn_fields"] = cn_fields
    record["deductions"] = deductions
    record["employer_costs"] = employer_costs
    return record
