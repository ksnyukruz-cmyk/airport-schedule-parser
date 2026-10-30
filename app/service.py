"""Сбор табло и короткий кэш, чтобы не дёргать аэропорты на каждый клик."""

from __future__ import annotations

import time
from datetime import date, datetime

from app.flights import MOSCOW
from app.http_client import SourceError
from app.sources import dme, pulkovo, svo

AIRPORTS = {
    "SVO": {
        "code": "SVO",
        "name": "Шереметьево",
        "city": "Москва",
        "supports_date": True,
        "source_name": "Официальное табло Шереметьево",
    },
    "DME": {
        "code": "DME",
        "name": "Домодедово",
        "city": "Москва",
        "supports_date": False,
        "source_name": "Онлайн-табло Домодедово",
    },
    "LED": {
        "code": "LED",
        "name": "Пулково",
        "city": "Санкт-Петербург",
        "supports_date": True,
        "source_name": "Официальное табло Пулково",
    },
}

FETCHERS = {
    "SVO": svo.fetch,
    "DME": dme.fetch,
    "LED": pulkovo.fetch,
}

TTL_SECONDS = 60
_cache: dict[tuple, tuple[float, dict]] = {}


def list_airports() -> list[dict]:
    return [dict(item) for item in AIRPORTS.values()]


def today_moscow() -> date:
    return datetime.now(MOSCOW).date()


def get_schedule(code: str, direction: str, day: date, refresh: bool = False) -> dict:
    airport = AIRPORTS.get(code.upper())
    if airport is None:
        raise KeyError(code)
    if direction not in {"departure", "arrival"}:
        raise ValueError(direction)
    if not airport["supports_date"]:
        day = today_moscow()
    key = (airport["code"], direction, day.isoformat())
    now = time.monotonic()
    cached = _cache.get(key)
    if cached and not refresh and now - cached[0] < TTL_SECONDS:
        return cached[1]
    try:
        loaded = FETCHERS[airport["code"]](direction, day)
    except SourceError as error:
        if cached:
            stale = dict(cached[1])
            stale["stale"] = True
            stale["warning"] = "Показаны сохранённые данные: источник временно недоступен."
            return stale
        raise SourceError(str(error)) from error
    board = {
        "airport": dict(airport),
        "direction": direction,
        "date": day.isoformat(),
        "fetched_at": datetime.now(MOSCOW).isoformat(timespec="seconds"),
        "source_name": airport["source_name"],
        "source_url": loaded["source_url"],
        "notice": loaded.get("notice") or "",
        "stale": False,
        "warning": "",
        "flights": loaded["flights"],
    }
    _cache[key] = (now, board)
    return board
