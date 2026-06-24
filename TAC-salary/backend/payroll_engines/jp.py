"""Japan payroll parameter-assisted calculation hooks."""

from __future__ import annotations

from .core import apply_rate, money, message, parameter_label, parameter_values, pick_parameter, rate


def _hourly_basis(record: dict, values: dict) -> float:
    if money(values.get("hourly_rate")) > 0:
        return money(values.get("hourly_rate"))
    rule = dict(record.get("salary_calculation_rule_snapshot") or {})
    if money(rule.get("hourly_rate")) > 0:
        return money(rule.get("hourly_rate"))
    standard_hours = money(values.get("standard_hours_per_month")) or money(rule.get("standard_hours_per_month"))
    base_rate = money(rule.get("base_rate")) or money(record.get("earnings", {}).get("base_salary"))
    if standard_hours > 0 and base_rate > 0:
        return round(base_rate / standard_hours, 4)
    return 0.0


def _calculate_overtime(record: dict, parameters: list[dict]) -> None:
    jp_fields = dict(record.get("jp_fields") or {})
    earnings = dict(record.get("earnings") or {})
    parameter = pick_parameter(parameters, "jp_overtime", "jp_statutory")
    values = parameter_values(parameter)
    hourly_rate = _hourly_basis(record, values)
    overtime_hours = money(jp_fields.get("overtime_hours"))
    late_night_hours = money(jp_fields.get("late_night_hours"))
    holiday_hours = money(jp_fields.get("holiday_work_hours"))
    statutory_holiday_hours = money(jp_fields.get("statutory_holiday_work_hours"))

    if not parameter:
        if any((overtime_hours, late_night_hours, holiday_hours, statutory_holiday_hours)):
            message(record, "JP overtime kept as manual amount; no active JP overtime parameter found.")
        return
    if hourly_rate <= 0:
        message(record, f"JP overtime parameter {parameter_label(parameter)} found, but hourly basis is missing.")
        return

    calculated_any = False
    rate_map = (
        ("overtime_pay", overtime_hours, "overtime_multiplier"),
        ("late_night_overtime_pay", late_night_hours, "late_night_multiplier"),
        ("holiday_work_pay", holiday_hours, "holiday_work_multiplier"),
        ("statutory_holiday_work_pay", statutory_holiday_hours, "statutory_holiday_work_multiplier"),
    )
    for field, hours, multiplier_key in rate_map:
        multiplier = money(values.get(multiplier_key))
        if hours > 0 and multiplier > 0:
            earnings[field] = round(hours * hourly_rate * multiplier, 2)
            calculated_any = True
    if calculated_any:
        jp_fields["overtime_hourly_basis"] = hourly_rate
        jp_fields["overtime_calculation_method"] = "parameter_assisted"
        jp_fields["overtime_parameter_id"] = parameter.get("parameter_id", "")
        record["jp_fields"] = jp_fields
        record["earnings"] = earnings
        message(record, f"JP overtime calculated by {parameter_label(parameter)}.")


def _calculate_deductions(record: dict, parameters: list[dict]) -> None:
    parameter = pick_parameter(parameters, "jp_social", "jp_tax", "jp_statutory")
    if not parameter:
        message(record, "JP social insurance/tax kept as manual amounts; no active JP statutory parameter found.")
        return
    values = parameter_values(parameter)
    earnings = dict(record.get("earnings") or {})
    deductions = dict(record.get("deductions") or {})
    employer_costs = dict(record.get("employer_costs") or {})
    jp_fields = dict(record.get("jp_fields") or {})
    gross_base = sum(money(earnings.get(field)) for field in ("base_salary", "position_allowance", "commute_allowance", "housing_allowance", "other_allowance", "overtime_pay", "late_night_overtime_pay", "holiday_work_pay", "statutory_holiday_work_pay"))
    contribution_base = money(values.get("standard_monthly_remuneration")) or gross_base

    rate_fields = {
        "health_insurance": "health_insurance_employee_rate",
        "pension_insurance": "pension_insurance_employee_rate",
        "employment_insurance": "employment_insurance_employee_rate",
        "income_tax": "income_tax_rate",
    }
    employer_rate_fields = {
        "employer_health_insurance": "health_insurance_employer_rate",
        "employer_pension_insurance": "pension_insurance_employer_rate",
        "employer_employment_insurance": "employment_insurance_employer_rate",
        "employer_workers_compensation": "workers_compensation_employer_rate",
    }
    calculated = False
    for target, source in rate_fields.items():
        if source in values:
            deductions[target] = apply_rate(contribution_base, values[source])
            calculated = True
    if "resident_tax_monthly" in values:
        deductions["resident_tax"] = money(values.get("resident_tax_monthly"))
        calculated = True
    for target, source in employer_rate_fields.items():
        if source in values:
            employer_costs[target] = apply_rate(contribution_base, values[source])
            calculated = True
    if calculated:
        jp_fields["statutory_calculation_method"] = "parameter_assisted"
        jp_fields["statutory_parameter_id"] = parameter.get("parameter_id", "")
        jp_fields["standard_monthly_remuneration"] = contribution_base
        record["jp_fields"] = jp_fields
        record["deductions"] = deductions
        record["employer_costs"] = employer_costs
        message(record, f"JP social insurance/tax calculated by {parameter_label(parameter)}.")
    else:
        message(record, f"JP parameter {parameter_label(parameter)} has no supported social insurance/tax rate values.")


def apply(record: dict, parameters: list[dict]) -> dict:
    _calculate_overtime(record, parameters)
    _calculate_deductions(record, parameters)
    return record
