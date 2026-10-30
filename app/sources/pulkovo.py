"""Табло Пулково: публичный JSON pulkovoairport.ru."""

from __future__ import annotations

from datetime import date

from app.flights import as_text, flight_date, make_flight, parse_airport_time, tidy_flight_number
from app.http_client import SourceError, get_json

SOURCE_URL = "https://pulkovoairport.ru/"
API = "https://pulkovoairport.ru/api/"

STATUS_RU = {
    "SKD": "По расписанию",
    "DLY": "Задержан",
    "UOD": "Задержан",
    "XLD": "Отменён",
    "CNL": "Отменён",
    "CAN": "Отменён",
    "OFB": "Вылетел",
    "DEP": "Вылетел",
    "ONB": "Прибыл",
    "ARR": "Прибыл",
    "TDN": "Приземлился",
    "LAN": "Приземлился",
    "INB": "В пути",
    "UOT": "Ожидается",
    "RFB": "Идёт посадка",
    "BRD": "Идёт посадка",
    "GCL": "Посадка закончена",
    "CHK": "Регистрация",
}


def fetch(direction: str, day: date) -> dict:
    kind = "departure" if direction == "departure" else "arrival"
    payload = get_json(f"{API}?col=1000&type={kind}")
    if not isinstance(payload, list):
        raise SourceError("Пулково вернуло неожиданный ответ")
    flights = parse_rows(payload, direction, day)
    notice = ""
    if len(payload) >= 1000:
        notice = "Табло Пулково отдало максимум выборки, часть рейсов могла не попасть в список."
    return {"flights": flights, "source_url": SOURCE_URL, "notice": notice}


def parse_rows(rows: list, direction: str, day: date | None) -> list[dict]:
    prefix = "OD" if direction == "departure" else "OA"
    flights = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        flight = _flight(row, prefix, direction)
        if day is not None and flight_date(flight.get("scheduled")) != day:
            continue
        flights.append(flight)
    flights.sort(key=lambda item: item.get("scheduled") or "9999")
    return flights


def _flight(row: dict, prefix: str, direction: str) -> dict:
    if direction == "departure":
        city = as_text(row.get("OD_RAP_DESTINATION_NAME_RU")) or as_text(row.get("OD_RAP_NEXT_NAME_RU"))
        city_code = as_text(row.get("OD_RAP_CODE_DESTINATION")) or as_text(row.get("OD_RAP_CODE_NEXT"))
        scheduled = parse_airport_time(row.get("OD_STD"))
        estimated = parse_airport_time(row.get("OD_ETD"))
        gate = as_text(row.get("OD_GATES"))
        belt = ""
    else:
        city = as_text(row.get("OA_RAP_ORIGIN_NAME_RU")) or as_text(row.get("OA_RAP_PREVIOUS_NAME_RU"))
        city_code = as_text(row.get("OA_RAP_CODE_ORIGIN")) or as_text(row.get("OA_RAP_CODE_PREVIOUS"))
        scheduled = parse_airport_time(row.get("OA_STA"))
        estimated = parse_airport_time(row.get("OA_ETA"))
        gate = ""
        belt = as_text(row.get("OA_BAGGAGEBELTS"))
    code = as_text(row.get(f"{prefix}_RFS_CODE")).upper()
    status = as_text(row.get(f"{prefix}_STATUS_RU")) or STATUS_RU.get(code, code)
    return make_flight(
        flight=tidy_flight_number(row.get(f"{prefix}_FLIGHT_NUMBER")),
        airline=as_text(row.get(f"{prefix}_RAL_NAME_RUS")) or as_text(row.get(f"{prefix}_RAL_NAME_EN")),
        airline_code=as_text(row.get(f"{prefix}_RAL_CODE")),
        city=city,
        city_code=city_code,
        scheduled=scheduled,
        estimated=estimated,
        actual=parse_airport_time(row.get(f"{prefix}_ATA") or row.get(f"{prefix}_ATD")),
        terminal=as_text(row.get(f"{prefix}_RTRM_CODE")),
        gate=gate,
        belt=belt,
        status=status,
        aircraft=as_text(row.get(f"{prefix}_RACT_ICAO_CODE")) or as_text(row.get(f"{prefix}_RACT_CODE")),
    )
