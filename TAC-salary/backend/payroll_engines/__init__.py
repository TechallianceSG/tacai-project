"""Country payroll engine registry."""

from __future__ import annotations

from . import cn, jp, sg

ENGINES = {
    "JP": jp.apply,
    "SG": sg.apply,
    "CN": cn.apply,
}


def apply_country_engine(record: dict, parameters: list[dict] | None = None) -> dict:
    engine = ENGINES.get(str(record.get("country_code") or "").upper())
    if not engine:
        return record
    return engine(record, list(parameters or []))
