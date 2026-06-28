"""Japan payroll calculation helpers for TACAIPAY JP.

The MVP engine is parameter-assisted. Statutory/tax results should be reviewed by
HR/payroll specialists before final approval.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, List, Tuple


def money(value: Any) -> int:
    """Return a non-negative JPY integer rounded half-up."""
    try:
        amount = Decimal(str(value or 0)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except Exception:
        amount = Decimal("0")
    return int(amount)


def rate(value: Any, default: str = "0") -> Decimal:
    try:
        return Decimal(str(value if value is not None else default))
    except Exception:
        return Decimal(default)


def list_total(items: List[Dict[str, Any]]) -> int:
    return sum(money(item.get("amount")) for item in items)


def default_attendance(parameters: Dict[str, Any]) -> Dict[str, int]:
    standard_days = int(parameters.get("standard_monthly_work_days") or 20)
    standard_hours = int(parameters.get("standard_monthly_work_hours") or 160)
    return {
        "work_days": standard_days,
        "paid_leave_days": 0,
        "absence_days": 0,
        "regular_hours": standard_hours,
        "overtime_hours": 0,
        "late_night_hours": 0,
        "holiday_hours": 0,
    }


def calculate_payroll_record(record: Dict[str, Any], parameters: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """Calculate earnings/deductions/employer costs for one payroll record.

    Inputs are intentionally simple for the first release:
    - monthly, hourly, daily salary types
    - attendance-driven absence deduction and overtime additions
    - fixed recurring additions/deductions from salary master snapshot
    - statutory items are parameter-assisted and auditable
    """
    messages: List[str] = []
    profile = record.get("salary_master_snapshot") or {}
    attendance = default_attendance(parameters)
    attendance.update(record.get("attendance") or {})

    salary_type = profile.get("salary_type") or "monthly"
    standard_days = max(int(profile.get("standard_work_days") or parameters.get("standard_monthly_work_days") or 20), 1)
    standard_hours = max(int(profile.get("standard_work_hours") or parameters.get("standard_monthly_work_hours") or 160), 1)
    work_days = max(int(attendance.get("work_days") or 0), 0)
    regular_hours = max(int(attendance.get("regular_hours") or 0), 0)
    absence_days = max(int(attendance.get("absence_days") or 0), 0)
    overtime_hours = max(int(attendance.get("overtime_hours") or 0), 0)
    late_night_hours = max(int(attendance.get("late_night_hours") or 0), 0)
    holiday_hours = max(int(attendance.get("holiday_hours") or 0), 0)

    monthly_base = money(profile.get("base_salary"))
    hourly_rate = money(profile.get("hourly_rate"))
    daily_rate = money(profile.get("daily_rate"))
    transportation = money(profile.get("transportation_allowance"))

    overtime_multiplier = rate(parameters.get("overtime_multiplier"), "1.25")
    late_night_multiplier = rate(parameters.get("late_night_multiplier"), "0.25")
    holiday_multiplier = rate(parameters.get("holiday_multiplier"), "1.35")

    earnings: List[Dict[str, Any]] = []
    deductions: List[Dict[str, Any]] = []
    employer_costs: List[Dict[str, Any]] = []

    base_pay = 0
    base_hourly_for_premiums = hourly_rate
    if salary_type == "monthly":
        base_pay = monthly_base
        base_hourly_for_premiums = money(Decimal(monthly_base) / Decimal(standard_hours)) if monthly_base else 0
        messages.append("Monthly salary used as base pay; absence deduction is calculated separately.")
    elif salary_type == "hourly":
        base_pay = money(Decimal(hourly_rate) * Decimal(regular_hours))
        messages.append("Hourly salary calculated from regular hours.")
    elif salary_type == "daily":
        base_pay = money(Decimal(daily_rate) * Decimal(work_days))
        base_hourly_for_premiums = money(Decimal(daily_rate) / Decimal(max(int(parameters.get("standard_daily_work_hours") or 8), 1))) if daily_rate else 0
        messages.append("Daily salary calculated from work days.")
    else:
        base_pay = monthly_base
        messages.append("Manual/mixed salary type uses base salary and requires HR confirmation.")

    earnings.append({"code": "base_pay", "name_key": "item.base_pay", "amount": base_pay})

    if transportation:
        earnings.append({"code": "transportation", "name_key": "item.transportation", "amount": transportation})

    overtime_pay = money(Decimal(base_hourly_for_premiums) * Decimal(overtime_hours) * overtime_multiplier)
    late_night_pay = money(Decimal(base_hourly_for_premiums) * Decimal(late_night_hours) * late_night_multiplier)
    holiday_pay = money(Decimal(base_hourly_for_premiums) * Decimal(holiday_hours) * holiday_multiplier)
    if overtime_pay:
        earnings.append({"code": "overtime", "name_key": "item.overtime", "amount": overtime_pay})
    if late_night_pay:
        earnings.append({"code": "late_night", "name_key": "item.late_night", "amount": late_night_pay})
    if holiday_pay:
        earnings.append({"code": "holiday", "name_key": "item.holiday", "amount": holiday_pay})

    for item in profile.get("fixed_earnings") or []:
        amount = money(item.get("amount"))
        if amount:
            earnings.append({"code": item.get("code") or "fixed_earning", "label": item.get("label") or item.get("name") or "Fixed earning", "amount": amount})

    for item in record.get("variable_earnings") or []:
        amount = money(item.get("amount"))
        if amount:
            earnings.append({"code": item.get("code") or "variable_earning", "label": item.get("label") or item.get("name") or "Variable earning", "amount": amount})

    if salary_type == "monthly" and absence_days:
        absence_amount = money(Decimal(monthly_base) / Decimal(standard_days) * Decimal(absence_days))
        deductions.append({"code": "absence", "name_key": "item.absence", "amount": absence_amount})
        messages.append("Absence deduction estimated by monthly base / standard work days.")

    for item in profile.get("fixed_deductions") or []:
        amount = money(item.get("amount"))
        if amount:
            deductions.append({"code": item.get("code") or "fixed_deduction", "label": item.get("label") or item.get("name") or "Fixed deduction", "amount": amount})

    for item in record.get("variable_deductions") or []:
        amount = money(item.get("amount"))
        if amount:
            deductions.append({"code": item.get("code") or "variable_deduction", "label": item.get("label") or item.get("name") or "Variable deduction", "amount": amount})

    gross_before_statutory = list_total(earnings)
    social_base = gross_before_statutory

    if profile.get("health_insurance_enrolled", True):
        employee_amount = money(Decimal(social_base) * rate(parameters.get("health_insurance_employee_rate"), "0.0491"))
        employer_amount = money(Decimal(social_base) * rate(parameters.get("health_insurance_employer_rate"), "0.0491"))
        if employee_amount:
            deductions.append({"code": "health_insurance", "name_key": "item.health_insurance", "amount": employee_amount})
        if employer_amount:
            employer_costs.append({"code": "employer_health_insurance", "name_key": "item.employer_health_insurance", "amount": employer_amount})

    if profile.get("pension_enrolled", True):
        employee_amount = money(Decimal(social_base) * rate(parameters.get("pension_employee_rate"), "0.0915"))
        employer_amount = money(Decimal(social_base) * rate(parameters.get("pension_employer_rate"), "0.0915"))
        if employee_amount:
            deductions.append({"code": "pension", "name_key": "item.pension", "amount": employee_amount})
        if employer_amount:
            employer_costs.append({"code": "employer_pension", "name_key": "item.employer_pension", "amount": employer_amount})

    if profile.get("employment_insurance_enrolled", True):
        employee_amount = money(Decimal(gross_before_statutory) * rate(parameters.get("employment_insurance_employee_rate"), "0.006"))
        employer_amount = money(Decimal(gross_before_statutory) * rate(parameters.get("employment_insurance_employer_rate"), "0.0095"))
        if employee_amount:
            deductions.append({"code": "employment_insurance", "name_key": "item.employment_insurance", "amount": employee_amount})
        if employer_amount:
            employer_costs.append({"code": "employer_employment_insurance", "name_key": "item.employer_employment_insurance", "amount": employer_amount})

    manual_income_tax = money(record.get("manual_income_tax") or profile.get("default_income_tax"))
    manual_resident_tax = money(record.get("manual_resident_tax") or profile.get("default_resident_tax"))
    if manual_income_tax:
        deductions.append({"code": "income_tax", "name_key": "item.income_tax", "amount": manual_income_tax})
    else:
        messages.append("Income tax is manual/parameter-assisted in MVP; HR must confirm before final approval.")
    if manual_resident_tax:
        deductions.append({"code": "resident_tax", "name_key": "item.resident_tax", "amount": manual_resident_tax})
    else:
        messages.append("Resident tax is manual in MVP; enter municipality notice amount if applicable.")

    gross_total = list_total(earnings)
    deduction_total = list_total(deductions)
    employer_cost_total = list_total(employer_costs)
    net_pay = max(gross_total - deduction_total, 0)

    result = {
        "attendance": attendance,
        "earnings": earnings,
        "deductions": deductions,
        "employer_costs": employer_costs,
        "gross_total": gross_total,
        "deduction_total": deduction_total,
        "net_pay": net_pay,
        "employer_cost_total": employer_cost_total,
        "company_total_cost": gross_total + employer_cost_total,
    }
    return result, messages
