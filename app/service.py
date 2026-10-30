"""Сбор табло и короткий кэш, чтобы не дёргать источники на каждый клик."""

from __future__ import annotations

import json
import time
from datetime import date, datetime
from pathlib import Path

from app.flights import MOSCOW
from app.http_client import SourceError
from app.sources import dme, live, pulkovo, svo

DATA = Path(__file__).resolve().parent / "data" / "airports.json"

OFFICIAL = {
    "SVO": {
        "fetch": svo.fetch,
        "supports_date": True,
        "source_name": "Официальное табло Шереметьево",
    },
    "DME": {
        "fetch": dme.fetch,
        "supports_date": False,
        "source_name": "Онлайн-табло Домодедово",
    },
    "LED": {
        "fetch": pulkovo.fetch,
        "supports_date": True,
        "source_name": "Официальное табло Пулково",
    },
}

TTL_SECONDS = 60
_cache: dict[tuple, tuple[float, dict]] = {}


def _catalog() -> dict[str, dict]:
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    airports = {}
    for row in rows:
        airport = dict(row)
        official = OFFICIAL.get(airport["code"])
        if official:
            airport["supports_date"] = official["supports_date"]
            airport["kind"] = "official"
            airport["source_name"] = official["source_name"]
        else:
            airport["supports_date"] = False
            airport["kind"] = "live"
            airport["source_name"] = "Живые рейсы рядом с аэропортом"
        airports[airport["code"]] = airport
    return airports


AIRPORTS = _catalog()


def list_airports() -> list[dict]:
    visible = []
    for airport in AIRPORTS.values():
        visible.append(
            {
                "code": airport["code"],
                "name": airport["name"],
                "city": airport["city"],
                "country": airport["country"],
                "keywords": airport.get("keywords") or "",
                "supports_date": airport["supports_date"],
                "kind": airport["kind"],
            }
        )
    return visible


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
        loaded = _load(airport, direction, day, refresh)
    except SourceError as error:
        if cached:
            stale = dict(cached[1])
            stale["stale"] = True
            stale["warning"] = "Показаны сохранённые данные: источник временно недоступен."
            return stale
        raise SourceError(str(error)) from error
    board = {
        "airport": {
            "code": airport["code"],
            "name": airport["name"],
            "city": airport["city"],
            "country": airport["country"],
            "supports_date": airport["supports_date"],
            "kind": airport["kind"],
        },
        "direction": direction,
        "date": day.isoformat(),
        "fetched_at": datetime.now(MOSCOW).isoformat(timespec="seconds"),
        "source_name": airport["source_name"],
        "source_url": loaded["source_url"],
        "notice": loaded.get("notice") or "",
        "stale": False,
        "warning": loaded.get("warning") or "",
        "flights": loaded["flights"],
    }
    _cache[key] = (now, board)
    return board


def _load(airport: dict, direction: str, day: date, refresh: bool = False) -> dict:
    official = OFFICIAL.get(airport["code"])
    if official is None:
        return live.fetch(airport, direction, day, force=refresh)
    try:
        return official["fetch"](direction, day)
    except SourceError:
        fallback = live.fetch(airport, direction, day)
        fallback["warning"] = "Официальное табло не ответило, показаны самолёты рядом с аэропортом."
        return fallback
