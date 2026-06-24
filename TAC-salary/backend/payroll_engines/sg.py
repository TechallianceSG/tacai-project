"""Singapore payroll CPF parameter-assisted calculation hooks."""

from __future__ import annotations

from .core import cap_amount, money, message, parameter_label, parameter_values, pick_parameter, rate


def apply(record: dict, parameters: list[dict]) -> dict:
    sg_fields = dict(record.get("sg_fields") or {})
    deductions = dict(record.get("deductions") or {})
    employer_costs = dict(record.get("employer_costs") or {})

    cpf_applicable = bool(sg_fields.get("cpf_applicable", True))
    if not cpf_applicable:
        sg_fields["cpf_employee"] = 0.0
        sg_fields["cpf_employer"] = 0.0
        deductions["cpf_employee"] = 0.0
        employer_costs["cpf_employer"] = 0.0
        message(record, "SG CPF set to zero because cpf_applicable is false.")
    else:
        parameter = pick_parameter(parameters, "sg_cpf", "cpf")
        input_mode = str(sg_fields.get("cpf_input_mode") or "manual").strip().lower()
        manual_employee = money(sg_fields.get("cpf_employee"))
        manual_employer = money(sg_fields.get("cpf_employer"))
        if not parameter:
            deductions["cpf_employee"] = manual_employee
            employer_costs["cpf_employer"] = manual_employer
            message(record, "SG CPF kept as manual amount; no active SG CPF parameter found.")
        else:
            values = parameter_values(parameter)
            force = bool(values.get("force_parameter_calculation", False))
            should_calculate = force or input_mode in {"parameter_assisted", "automated_validated", "auto"} or (manual_employee == 0 and manual_employer == 0)
            employee_rate = rate(values.get("cpf_employee_rate", values.get("employee_cpf_rate")))
            employer_rate = rate(values.get("cpf_employer_rate", values.get("employer_cpf_rate")))
            if should_calculate and employee_rate > 0 and employer_rate > 0:
                earnings = dict(record.get("earnings") or {})
                gross = sum(money(value) for value in earnings.values())
                ordinary_wage = money(sg_fields.get("cpf_ordinary_wage")) or gross
                additional_wage = money(sg_fields.get("cpf_additional_wage"))
                wage_base = cap_amount(ordinary_wage, values.get("ordinary_wage_ceiling")) + cap_amount(additional_wage, values.get("additional_wage_ceiling"))
                sg_fields["cpf_ordinary_wage"] = ordinary_wage
                sg_fields["cpf_additional_wage"] = additional_wage
                sg_fields["cpf_wage_base"] = wage_base
                sg_fields["cpf_employee"] = round(wage_base * employee_rate, 2)
                sg_fields["cpf_employer"] = round(wage_base * employer_rate, 2)
                sg_fields["cpf_calculation_method"] = "parameter_assisted"
                sg_fields["cpf_parameter_id"] = parameter.get("parameter_id", "")
                deductions["cpf_employee"] = sg_fields["cpf_employee"]
                employer_costs["cpf_employer"] = sg_fields["cpf_employer"]
                message(record, f"SG CPF calculated by {parameter_label(parameter)}.")
            elif should_calculate:
                deductions["cpf_employee"] = manual_employee
                employer_costs["cpf_employer"] = manual_employer
                message(record, f"SG CPF parameter {parameter_label(parameter)} is missing employee/employer rates; manual CPF kept.")
            else:
                deductions["cpf_employee"] = manual_employee
                employer_costs["cpf_employer"] = manual_employer
                message(record, "SG CPF manual input mode kept existing CPF amounts.")

    employer_costs["employer_other_cost"] = money(sg_fields.get("skill_development_levy")) + money(sg_fields.get("foreign_worker_levy"))
    record["sg_fields"] = sg_fields
    record["deductions"] = deductions
    record["employer_costs"] = employer_costs
    return record
