"""Онлайн-табло Внуково: публичный JSON vnukovo.ru.

Сайт сначала ставит js-cookie, а список рейсов приходит строкой,
собранной посимвольным XOR с ключом, который страница сама публикует.
"""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.request
from datetime import date, datetime, timedelta
from urllib.parse import quote, urlencode

from app.flights import as_text, flight_date, make_flight, parse_airport_time, tidy_flight_number
from app.http_client import USER_AGENT, SourceError

SOURCE_URL = "https://www.vnukovo.ru/ru/for-passengers/reysi/online-tablo/"
API = "https://www.vnukovo.ru/rest/flights/online"
KEY = "d87ea039-6704-4aec-84c3-c7b40b997f08"
_COOKIE: dict[str, object] = {"value": "", "until": 0.0}


def fetch(direction: str, day: date) -> dict:
    bound = "departure" if direction == "departure" else "arrival"
    cursor = datetime(day.year, day.month, day.day)
    end = cursor + timedelta(days=1)
    seen: set[object] = set()
    rows: list[dict] = []
    notice = ""
    for _ in range(8):
        try:
            results = _window(bound, cursor)
        except SourceError:
            if rows:
                notice = "Показана только часть дня: табло Внуково оборвало ответ."
                break
            raise
        for row in results.get("flights") or []:
            if not isinstance(row, dict):
                continue
            ident = row.get("flt_id")
            if ident in seen:
                continue
            seen.add(ident)
            rows.append(row)
        nxt = _moment(results.get("dateTo"))
        if nxt is None or nxt <= cursor or nxt >= end:
            break
        cursor = nxt
    else:
        notice = "Показана только часть дня: табло Внуково отдало неполную выборку."
    return {
        "flights": parse_rows(rows, day),
        "source_url": SOURCE_URL,
        "notice": notice,
    }


def parse_rows(rows: list, day: date | None) -> list[dict]:
    flights = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        flight = _flight(row)
        if day is not None and flight_date(flight.get("scheduled")) != day:
            continue
        flights.append(flight)
    flights.sort(key=lambda item: item.get("scheduled") or "9999")
    return flights


def decode_board(value: str, key: str = KEY) -> dict:
    raw = base64.b64decode(value)
    secret = key.encode("ascii")
    opened = bytes(byte ^ secret[index % len(secret)] for index, byte in enumerate(raw))
    payload = json.loads(opened.decode("utf-8"))
    if not isinstance(payload, dict):
        raise SourceError("Табло Внуково вернуло неожиданный ответ")
    return payload


def _flight(row: dict) -> dict:
    number = tidy_flight_number(row.get("flt_number"))
    status = as_text(row.get("status"))
    if row.get("cancelled") and "отмен" not in status.lower():
        status = "Отменён"
    elif row.get("delayed") and not status:
        status = "Задержан"
    aircraft = row.get("aircraft") if isinstance(row.get("aircraft"), dict) else {}
    return make_flight(
        flight=number,
        airline=as_text(row.get("airline_name")),
        airline_code=number.split(" ", 1)[0] if " " in number else "",
        city=as_text(row.get("fls_city_name")),
        city_code=as_text(row.get("fls_iata")).upper(),
        scheduled=_clock(row.get("st")),
        estimated=_clock(row.get("et")),
        actual=_clock(row.get("at")),
        terminal=as_text(row.get("terminal")),
        gate=_places(row.get("gates")),
        belt=_places(row.get("belt")),
        status=status,
        aircraft=as_text(aircraft.get("name")) or as_text(aircraft.get("icao")),
        codeshare=_shares(row.get("codeshare")),
    )


def _window(bound: str, start: datetime) -> dict:
    query = urlencode({"bound": bound, "limit": 0, "from": start.strftime("%Y-%m-%d %H:%M:%S")})
    payload = _get_json(f"{API}?{query}")
    if isinstance(payload.get("object"), str):
        payload = decode_board(payload["object"])
    results = payload.get("results")
    if not isinstance(results, dict):
        raise SourceError("Табло Внуково вернуло неожиданный ответ")
    return results


def _get_json(url: str) -> dict:
    last_error = "Табло Внуково не ответило"
    for _ in range(2):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "application/json",
                "Accept-Language": "ru",
                "Cookie": _cookies(),
                "Referer": SOURCE_URL,
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                raw = response.read()
        except Exception as error:
            last_error = "Табло Внуково не ответило"
            _COOKIE["value"] = ""
            raise SourceError(last_error) from error
        text = raw.decode("utf-8", "replace").lstrip()
        if text.startswith("<"):
            _COOKIE["value"] = ""
            last_error = "Табло Внуково не пустило запрос"
            continue
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as error:
            raise SourceError("Табло Внуково вернуло неожиданный ответ") from error
        if not isinstance(payload, dict):
            raise SourceError("Табло Внуково вернуло неожиданный ответ")
        return payload
    raise SourceError(last_error)


def _cookies() -> str:
    cached = _COOKIE["value"]
    if isinstance(cached, str) and cached and time.monotonic() < float(_COOKIE["until"]):
        return cached
    jar = _pass_check()
    _COOKIE["value"] = jar
    _COOKIE["until"] = time.monotonic() + 1200
    return jar


def _pass_check() -> str:
    class Stay(urllib.request.HTTPErrorProcessor):
        def http_response(self, request, response):
            return response

        https_response = http_response

    opener = urllib.request.build_opener(Stay)
    first = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "ru"},
    )
    try:
        with opener.open(first, timeout=25) as response:
            planted = response.headers.get("Set-Cookie") or ""
    except Exception as error:
        raise SourceError("Табло Внуково не ответило") from error
    match = re.search(r"__js_p_=([^;]+)", planted)
    if match is None:
        raise SourceError("Табло Внуково не пустило запрос")
    token = match.group(1)
    code = int(token.split(",")[0])
    jar = f"__js_p_={token}; __jhash_={_jhash(code)}; __jua_={quote(USER_AGENT, safe='')}"
    second = urllib.request.Request(
        SOURCE_URL,
        headers={"User-Agent": USER_AGENT, "Cookie": jar, "Referer": SOURCE_URL},
    )
    try:
        with opener.open(second, timeout=25) as response:
            passed = response.headers.get("Set-Cookie") or ""
    except Exception as error:
        raise SourceError("Табло Внуково не ответило") from error
    hashed = re.search(r"__hash_=([^;]+)", passed)
    if hashed is None:
        raise SourceError("Табло Внуково не пустило запрос")
    return jar + "; __hash_=" + hashed.group(1)


def _jhash(code: int) -> int:
    x = 123456789
    k = 0
    for i in range(1677696):
        mixed = _int32(_int32(x + code) ^ _int32(x + _mod(x, 3) + _mod(x, 17) + code) ^ i)
        x = _mod(mixed, 16776960)
        if _mod(x, 117) == 0:
            k = _mod(k + 1, 1111)
    return k


def _int32(value: int) -> int:
    value &= 0xFFFFFFFF
    if value >= 0x80000000:
        value -= 0x100000000
    return value


def _mod(value: int, divisor: int) -> int:
    return value - divisor * int(value / divisor)


def _clock(value) -> str | None:
    text = as_text(value)
    if not text:
        return None
    return parse_airport_time(text.replace(" ", "T", 1))


def _moment(value) -> datetime | None:
    text = as_text(value)
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace(" ", "T", 1))
    except ValueError:
        return None


def _places(value) -> str:
    if isinstance(value, list):
        return ", ".join(part for part in (as_text(item) for item in value) if part)
    return as_text(value)


def _shares(value) -> list[str]:
    if not isinstance(value, list):
        return []
    shares = []
    for item in value:
        if isinstance(item, str):
            shares.append(tidy_flight_number(item))
        elif isinstance(item, dict):
            shares.append(tidy_flight_number(item.get("flt_number") or item.get("number") or ""))
    return [item for item in shares if item]
