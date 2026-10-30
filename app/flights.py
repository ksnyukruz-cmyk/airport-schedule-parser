"""Общий вид рейса для всех источников."""

from __future__ import annotations

import re
from datetime import datetime
from zoneinfo import ZoneInfo

MOSCOW = ZoneInfo("Europe/Moscow")

FLIGHT_DEFAULTS = {
    "flight": "",
    "airline": "",
    "airline_code": "",
    "city": "",
    "city_code": "",
    "scheduled": None,
    "estimated": None,
    "actual": None,
    "terminal": "",
    "gate": "",
    "belt": "",
    "status": "",
    "aircraft": "",
    "codeshare": [],
}


def make_flight(**kwargs) -> dict:
    flight = {
        "flight": "",
        "airline": "",
        "airline_code": "",
        "city": "",
        "city_code": "",
        "scheduled": None,
        "estimated": None,
        "actual": None,
        "terminal": "",
        "gate": "",
        "belt": "",
        "status": "",
        "aircraft": "",
        "codeshare": [],
    }
    flight.update(kwargs)
    shares = flight.get("codeshare") or []
    if isinstance(shares, str):
        shares = [shares]
    primary = flight.get("flight") or ""
    flight["codeshare"] = [item for item in shares if item and item != primary]
    if _same_moment(flight.get("scheduled"), flight.get("estimated")):
        flight["estimated"] = None
    return flight


def as_text(value) -> str:
    if value is None or value == {}:
        return ""
    if isinstance(value, list):
        parts = [as_text(item) for item in value]
        return ", ".join(part for part in parts if part)
    if isinstance(value, dict):
        for key in ("name", "ru", "value", "code"):
            if value.get(key):
                return as_text(value[key])
        return ""
    text = str(value).replace("\xa0", " ").strip()
    if text in {"{}", "None", "null"}:
        return ""
    return re.sub(r"\s+", " ", text)


def tidy_flight_number(value) -> str:
    return as_text(value).upper()


def parse_airport_time(value) -> str | None:
    text = as_text(value)
    if not text:
        return None
    text = text.replace("Z", "+00:00")
    if text.endswith(".000"):
        text = text[:-4]
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=MOSCOW)
    return moment.isoformat(timespec="minutes")


def flight_date(value: str | None):
    if not value:
        return None
    try:
        moment = datetime.fromisoformat(value)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=MOSCOW)
    return moment.astimezone(MOSCOW).date()


def _same_moment(left, right) -> bool:
    if not left or not right:
        return False
    return str(left)[:16] == str(right)[:16]
