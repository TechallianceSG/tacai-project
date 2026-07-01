"""Japan payroll calculation engine — 給与計算エンジン"""

def calc_monthhour_pay(employee: dict, actual_hours: float) -> dict:
    """
    Monthhour salary type — parameterized from employee master data.

    派遣業界標準の「月時給制」:
    - 基準時間: from employee.standard_monthly_hours (default 160h)
    - 基本給: from employee.basic_salary (default 80000)
    - 時給: from employee.hourly_rate (default 1000)
    - 残業時給: from employee.overtime_hourly_rate (default 1500)

    計算式:
      actual <= std_hours: basic × actual/std_hours + hourly_rate × actual
      actual >  std_hours: basic + hourly_rate × std_hours + overtime_rate × (actual - std_hours)
    """
    basic = float(employee.get("basic_salary") or 80000)
    hourly_rate = float(employee.get("hourly_rate") or 1000)
    overtime_rate = float(employee.get("overtime_hourly_rate") or 1500)
    std_hours = float(employee.get("standard_monthly_hours") or 160)
    messages = []

    if actual_hours <= std_hours:
        base = round(basic * actual_hours / std_hours, 0)
        hourly_part = round(hourly_rate * actual_hours, 0)
        overtime_pay = 0.0
        messages.append(f"月時給: 基本給 {basic:,.0f}円 × {actual_hours}h/{std_hours}h = {base:,.0f}円")
        messages.append(f"時給部分: {hourly_rate:,.0f}円 × {actual_hours}h = {hourly_part:,.0f}円")
    else:
        base = basic
        hourly_part = round(hourly_rate * std_hours, 0)
        ot_hours = actual_hours - std_hours
        overtime_pay = round(overtime_rate * ot_hours, 0)
        messages.append(f"月時給: 基本給 {basic:,.0f}円 (全額支給)")
        messages.append(f"時給部分: {hourly_rate:,.0f}円 × {std_hours}h = {hourly_part:,.0f}円")
        messages.append(f"残業: {overtime_rate:,.0f}円 × {ot_hours}h = {overtime_pay:,.0f}円")

    gross = base + hourly_part + overtime_pay
    messages.append(f"支給総額: {gross:,.0f}円")

    return {
        "base_pay": int(round(base)),
        "hourly_part": int(round(hourly_part)),
        "overtime_pay": int(round(overtime_pay)),
        "gross_pay": int(round(gross)),
        "standard_hours": int(std_hours),
        "actual_hours": actual_hours,
        "messages": messages,
    }


def calc_salary_preview(employee: dict, actual_hours: float = None, actual_days: float = None) -> dict:
    """Preview salary calculation for any salary type.

    Args:
        employee: salary master record dict
        actual_hours: actual worked hours (for hourly/monthhour)
        actual_days: actual worked days (for monthly/daily)
    """
    salary_type = (employee.get("salary_type") or "monthly").strip()

    if salary_type == "monthhour":
        actual_hours = actual_hours or 0
        return calc_monthhour_pay(employee=employee, actual_hours=actual_hours)

    elif salary_type == "monthly":
        actual_days = actual_days or 22
        std_days = float(employee.get("standard_work_days") or 22)
        basic = float(employee.get("basic_salary") or 0)
        base = round(basic * min(actual_days / max(std_days, 22), 1.0), 0)
        return {
            "base_pay": int(round(base)), "gross_pay": int(round(base)),
            "messages": [f"月給: {basic:,.0f} × {actual_days}d/{std_days}d = {base:,.0f}"]
        }

    elif salary_type == "hourly":
        actual_hours = actual_hours or 160
        rate = float(employee.get("hourly_rate") or 0)
        base = round(rate * actual_hours, 0)
        return {
            "base_pay": int(round(base)), "gross_pay": int(round(base)),
            "messages": [f"時給: {rate:,.0f}円 × {actual_hours}h = {base:,.0f}"]
        }

    elif salary_type == "daily":
        actual_days = actual_days or 1
        rate = float(employee.get("daily_rate") or 0)
        base = round(rate * actual_days, 0)
        return {
            "base_pay": int(round(base)), "gross_pay": int(round(base)),
            "messages": [f"日給: {rate:,.0f}円 × {actual_days}d = {base:,.0f}"]
        }

    elif salary_type == "monthly_fixed_ot":
        actual_days = actual_days or 22
        std_days = float(employee.get("standard_work_days") or 22)
        basic = float(employee.get("basic_salary") or 0)
        fixed_ot = float(employee.get("fixed_overtime_amount") or 0)
        base = round(basic * min(actual_days / max(std_days, 22), 1.0), 0)
        gross = base + fixed_ot
        return {
            "base_pay": int(round(base)), "fixed_ot": int(round(fixed_ot)), "gross_pay": int(round(gross)),
            "messages": [f"月給: {basic:,.0f} × {actual_days}d/{std_days}d = {base:,.0f}", f"固定残業代: {fixed_ot:,.0f}"]
        }

    return {"base_pay": 0, "gross_pay": 0, "messages": [f"Unknown salary_type: {salary_type}"]}
