"""Shared helpers for parameter-assisted payroll engines.

These helpers intentionally avoid external dependencies and official statutory
claims. Country modules only automate values when an active parameter record is
provided by payroll users or validated configuration.
"""

from __future__ import annotations


def money(value: object) -> float:
    if value in (None, ""):
        return 0.0
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return 0.0


def rate(value: object) -> float:
    """Return a decimal rate, accepting either 0.1 or 10 for 10%."""
    numeric = money(value)
    if abs(numeric) > 1:
        return numeric / 100
    return numeric


def clean_text(value: object) -> str:
    return str(value or "").strip()


def normalize_city(value: object) -> str:
    city = clean_text(value).upper().replace("'", "")
    if city == "XI'AN":
        return "XIAN"
    return city


def message(record: dict, text: str) -> None:
    messages = list(record.get("calculation_messages") or [])
    if text not in messages:
        messages.append(text)
    record["calculation_messages"] = messages


def parameter_values(parameter: dict | None) -> dict:
    if not parameter:
        return {}
    values = parameter.get("values")
    return values if isinstance(values, dict) else {}


def parameter_label(parameter: dict | None) -> str:
    if not parameter:
        return "no-parameter"
    return clean_text(parameter.get("rule_version_id") or parameter.get("parameter_id") or "active-parameter")


def parameter_type_matches(parameter: dict, tokens: tuple[str, ...]) -> bool:
    parameter_type = clean_text(parameter.get("parameter_type")).lower()
    return any(token in parameter_type for token in tokens)


def pick_parameter(parameters: list[dict], *tokens: str, city_code: str = "") -> dict | None:
    """Pick the most specific active parameter from a pre-filtered list."""
    normalized_city = normalize_city(city_code)
    candidates = []
    for parameter in parameters:
        if tokens and not parameter_type_matches(parameter, tuple(token.lower() for token in tokens)):
            continue
        parameter_city = normalize_city(parameter.get("city_code"))
        if normalized_city and parameter_city and parameter_city != normalized_city:
            continue
        specificity = 0
        if parameter_city:
            specificity += 2
        if clean_text(parameter.get("entity_id")):
            specificity += 1
        candidates.append((specificity, clean_text(parameter.get("effective_start_date")), clean_text(parameter.get("updated_at")), parameter))
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (item[0], item[1], item[2]), reverse=True)[0][3]


def apply_rate(amount: object, rate_value: object) -> float:
    return round(money(amount) * rate(rate_value), 2)


def cap_amount(amount: float, ceiling: object) -> float:
    limit = money(ceiling)
    if limit > 0:
        return min(amount, limit)
    return amount
