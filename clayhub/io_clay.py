"""Read Clay CSV exports and webhook payloads."""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any

from .models import Lead
from .normalize import normalize_lead

_COLUMNS = {
    "row id": "row_id", "first name": "first_name", "last name": "last_name",
    "email": "email", "job title": "title", "title": "title",
    "company name": "company", "company": "company", "company domain": "domain",
    "domain": "domain", "linkedin url": "linkedin_url", "country": "country",
    "employee count": "employees", "employees": "employees", "industry": "industry", "phone": "phone",
}


def _lead(row: dict[str, Any], fallback_id: str) -> Lead:
    values = {}
    for key, value in row.items():
        field = _COLUMNS.get(str(key).strip().lower().replace("_", " "))
        if field:
            values[field] = "" if value is None else value
    row_id = str(values.pop("row_id", "") or fallback_id)
    employees = values.get("employees")
    if employees not in (None, ""):
        try:
            values["employees"] = int(str(employees).replace(",", "").strip())
        except (TypeError, ValueError):
            values["employees"] = None
    else:
        values["employees"] = None
    for key in ("first_name", "last_name", "email", "title", "company", "domain", "linkedin_url", "country", "industry", "phone"):
        values[key] = str(values.get(key) or "").strip()
    return normalize_lead(Lead(row_id=row_id, **values))


def read_clay_csv(path: str) -> list[Lead]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [_lead(row, str(index)) for index, row in enumerate(csv.DictReader(handle), start=2)]


def read_clay_webhook(payload: dict | list) -> list[Lead]:
    rows = payload if isinstance(payload, list) else payload.get("rows", [payload])
    if not isinstance(rows, list):
        raise ValueError("Webhook 'rows' must be a list")
    return [_lead(row, str(index)) for index, row in enumerate(rows, start=1) if isinstance(row, dict)]
