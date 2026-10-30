"""Табло Шереметьево: публичный JSON сайта svo.aero."""

from __future__ import annotations

import urllib.parse
from datetime import date

from app.flights import as_text, make_flight, parse_airport_time
from app.http_client import SourceError, get_json

HOME = "SVO"
SOURCE_URL = "https://www.svo.aero/ru/timetable"
API = "https://www.svo.aero/bitrix/timetable/"
PAGE_SIZE = 100
MAX_PAGES = 12


def fetch(direction: str, day: date) -> dict:
    items = []
    total = None
    for page in range(1, MAX_PAGES + 1):
        payload = _load_page(direction, day, page)
        batch = payload.get("items") or []
        if total is None:
            total = (payload.get("pagination") or {}).get("totalItems")
        items.extend(batch)
        if not batch:
            break
        if total is not None and len(items) >= total:
            break
        if len(batch) < PAGE_SIZE:
            break
    flights = parse_items(items, direction)
    notice = ""
    if total and len(items) < total:
        notice = "Показана только часть рейсов: табло Шереметьево отдало неполную выборку."
    return {
        "flights": flights,
        "source_url": SOURCE_URL,
        "notice": notice,
    }


def parse_items(items: list, direction: str) -> list[dict]:
    flights = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        marker = item.get("i_id") or id(item)
        if marker in seen:
            continue
        seen.add(marker)
        flights.append(_flight(item, direction))
    flights.sort(key=lambda row: row.get("scheduled") or "9999")
    return flights


def _load_page(direction: str, day: date, page: int) -> dict:
    query = urllib.parse.urlencode(
        {
            "direction": direction,
            "dateStart": f"{day.isoformat()}T00:00:00",
            "dateEnd": f"{day.isoformat()}T23:59:59",
            "perPage": PAGE_SIZE,
            "page": page,
        }
    )
    payload = get_json(f"{API}?{query}")
    if not isinstance(payload, dict):
        raise SourceError("Шереметьево вернуло неожиданный ответ")
    return payload


def _flight(item: dict, direction: str) -> dict:
    company = item.get("co") if isinstance(item.get("co"), dict) else {}
    airline_code = as_text(company.get("code"))
    number = as_text(item.get("flt"))
    flight_no = " ".join(part for part in (airline_code, number) if part)
    place = _counterpart(item, direction)
    scheduled = parse_airport_time(item.get("t_st"))
    estimated = parse_airport_time(item.get("t_et"))
    actual = parse_airport_time(item.get("t_at"))
    if actual is None:
        actual_key = "t_otpr" if direction == "departure" else "t_prb"
        actual = parse_airport_time(item.get(actual_key))
    gate = as_text(item.get("gate_id")) or as_text(item.get("old_gate_id"))
    if direction == "arrival":
        gate = ""
    return make_flight(
        flight=flight_no,
        airline=as_text(company.get("name")),
        airline_code=airline_code,
        city=as_text(place.get("city")) or as_text(place.get("description")),
        city_code=as_text(place.get("iata")),
        scheduled=scheduled,
        estimated=estimated,
        actual=actual,
        terminal=as_text(item.get("term")),
        gate=gate,
        belt=as_text(item.get("bbel_id")) if direction == "arrival" else "",
        status=as_text(item.get("vip_status_rus")) or as_text(item.get("vip_status")),
        aircraft=as_text(item.get("aircraft_type_name")),
        codeshare=_codeshare(item, flight_no),
    )


def _counterpart(item: dict, direction: str) -> dict:
    points = []
    for key in ("mar1", "mar2", "mar3", "mar4", "mar5"):
        point = item.get(key)
        if isinstance(point, dict) and point.get("iata"):
            points.append(point)
    if not points:
        return {}
    home_index = next((index for index, point in enumerate(points) if point.get("iata") == HOME), None)
    if direction == "departure":
        if home_index is not None:
            tail = [point for point in points[home_index + 1 :] if point.get("iata") != HOME]
            if tail:
                return tail[-1]
        for point in reversed(points):
            if point.get("iata") != HOME:
                return point
    else:
        if home_index is not None and home_index > 0:
            return points[home_index - 1]
        for point in points:
            if point.get("iata") != HOME:
                return point
    return {}


def _codeshare(item: dict, primary: str) -> list[str]:
    raw = item.get("main_flight")
    if isinstance(raw, dict):
        text = " ".join(
            part
            for part in (as_text(raw.get("code") or raw.get("airline")), as_text(raw.get("flt") or raw.get("number")))
            if part
        )
    else:
        text = as_text(raw)
    if text and text != primary:
        return [text]
    return []
