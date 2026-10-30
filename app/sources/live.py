"""Живое табло крупного аэропорта по открытым данным ADS-B.

Это не суточное расписание с выходами на посадку: видны самолёты,
которые сейчас находятся рядом с аэропортом и чей маршрут удаётся узнать.
"""

from __future__ import annotations

import json
import re
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.flights import make_flight
from app.http_client import SourceError, get_json

ROUTE = "https://api.adsb.lol/api/0/route/{callsign}"
FEEDS = (
    ("https://opendata.adsb.fi/api/v2/lat/{lat}/lon/{lon}/dist/30", "https://globe.adsb.fi/"),
    ("https://api.adsb.lol/v2/lat/{lat}/lon/{lon}/dist/30", "https://adsb.lol/"),
)
CALLSIGN_RE = re.compile(r"^([A-Z]{3})([0-9A-Z]{1,5})$")
ROUTE_TTL = 6 * 60 * 60
MISS_TTL = 20 * 60
MAX_LOOKUPS = 12
BOARD_TTL = 120
BUSY = "Лента рейсов сейчас перегружена. Подождите минуту и нажмите «Обновить»."

_AIRLINES = json.loads((Path(__file__).resolve().parent.parent / "data" / "airlines.json").read_text(encoding="utf-8"))
_route_cache: dict[str, tuple[float, float, dict | None]] = {}
_board_cache: dict[str, tuple[float, list]] = {}


def fetch(airport: dict, direction: str, day, force: bool = False) -> dict:
    del day
    flights, source_url, warning = _board(airport, force)
    flights = [flight for flight in flights if flight["direction"] == direction]
    return {
        "flights": flights,
        "source_url": source_url,
        "warning": warning,
        "notice": (
            "Для этого аэропорта нет открытого суточного табло. "
            "Показаны самолёты, которые сейчас рядом с ним: откуда летят или куда направляются. "
            "Выходов, стоек и рейсов вне зоны радиовидимости здесь нет."
        ),
    }


def select_flight(item: dict, route: dict | None, airport: dict) -> dict | None:
    callsign = str(item.get("flight") or "").strip().upper()
    match = CALLSIGN_RE.match(callsign)
    if not match:
        return None
    altitude = item.get("alt_baro")
    ground = altitude == "ground"
    altitude_ft = altitude if isinstance(altitude, (int, float)) else None
    try:
        rate = float(item.get("baro_rate") or 0)
    except (TypeError, ValueError):
        rate = 0.0
    try:
        distance_nm = float(item.get("dst"))
    except (TypeError, ValueError):
        distance_nm = None

    other, role = _role(route, airport)
    if role == "skip":
        return None
    if role is None:
        close = distance_nm is not None and distance_nm <= 12
        low = ground or (altitude_ft is not None and altitude_ft < 12000 and abs(rate) >= 150)
        if not (close and low):
            return None
        role = "arrival" if rate < 0 and not ground else "departure"

    if ground or (altitude_ft is not None and altitude_ft < 200):
        status = "На земле"
        when = "на земле"
    elif rate <= -150:
        status = "Снижается"
        when = _distance_label(distance_nm)
    elif rate >= 150:
        status = "Набирает высоту"
        when = _distance_label(distance_nm)
    else:
        status = "Рядом с аэропортом"
        when = _distance_label(distance_nm)

    icao = (route or {}).get("airline_code") or match.group(1)
    number = str((route or {}).get("number") or match.group(2))
    airline = _AIRLINES.get(icao, {})
    iata = airline.get("iata") or ""
    city = ""
    city_code = ""
    if isinstance(other, dict):
        city = other.get("location") or other.get("name") or ""
        city_code = other.get("iata") or ""
    flight = make_flight(
        flight=f"{iata or icao} {number}".strip(),
        airline=airline.get("name") or icao,
        airline_code=iata or icao,
        city=city,
        city_code=city_code,
        status=status,
        aircraft=str(item.get("t") or ""),
        when_label=when,
    )
    flight["direction"] = role
    return flight


def _role(route: dict | None, airport: dict) -> tuple[dict | None, str | None]:
    if not isinstance(route, dict):
        return None, None
    points = [point for point in (route.get("_airports") or []) if isinstance(point, dict)]
    if len(points) < 2:
        return None, None
    if _is_home(points[0], airport):
        return points[-1], "departure"
    if _is_home(points[-1], airport):
        return points[0], "arrival"
    return None, "skip"


def _is_home(point: dict, airport: dict) -> bool:
    iata = (point.get("iata") or "").upper()
    icao = (point.get("icao") or "").upper()
    return iata == airport.get("code") or (airport.get("icao") and icao == airport.get("icao"))


def _board(airport: dict, force: bool = False) -> tuple[list, str, str]:
    cached = _board_cache.get(airport["code"])
    now = time.monotonic()
    fresh_for = 20 if force else BOARD_TTL
    if cached and now - cached[0] < fresh_for:
        return cached[1], cached[2], ""
    try:
        aircraft, source_url = _positions(airport)
    except SourceError:
        if cached:
            return cached[1], cached[2], BUSY
        raise SourceError(BUSY) from None
    candidates = _candidates(aircraft)
    routes = _routes([item["callsign"] for item in candidates])
    flights = []
    for item in candidates:
        flight = select_flight(item, routes.get(item["callsign"]), airport)
        if flight:
            flights.append(flight)
    _board_cache[airport["code"]] = (now, flights, source_url)
    return flights, source_url, ""


def _positions(airport: dict) -> tuple[list, str]:
    lat = f"{airport['lat']:.4f}"
    lon = f"{airport['lon']:.4f}"
    last_error = BUSY
    for template, source_url in FEEDS:
        try:
            payload = _read_json(template.format(lat=lat, lon=lon))
        except SourceError as error:
            last_error = str(error)
            continue
        aircraft = _aircraft_list(payload)
        if aircraft is None:
            continue
        return aircraft, source_url
    raise SourceError(last_error if "429" not in last_error else BUSY)


def _aircraft_list(payload) -> list | None:
    if not isinstance(payload, dict):
        return None
    for key in ("ac", "aircraft"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return rows
    return None


def _read_json(url: str):
    try:
        return get_json(url)
    except SourceError as error:
        if "429" not in str(error):
            raise
        time.sleep(1.5)
        return get_json(url)


def _distance_label(distance_nm: float | None) -> str:
    if distance_nm is None:
        return "сейчас"
    return f"{max(1, round(distance_nm * 1.852))} км"


def _candidates(aircraft: list) -> list[dict]:
    rows = []
    for item in aircraft:
        if not isinstance(item, dict):
            continue
        callsign = str(item.get("flight") or "").strip().upper()
        if not CALLSIGN_RE.match(callsign):
            continue
        try:
            distance = float(item.get("dst"))
        except (TypeError, ValueError):
            distance = 999.0
        altitude = item.get("alt_baro")
        low = altitude == "ground" or (isinstance(altitude, (int, float)) and altitude < 15000) or distance <= 15
        if not low:
            continue
        copied = dict(item)
        copied["callsign"] = callsign
        copied["_distance"] = distance
        rows.append(copied)
    rows.sort(key=lambda item: item["_distance"])
    unique = []
    seen = set()
    for item in rows:
        if item["callsign"] in seen:
            continue
        seen.add(item["callsign"])
        unique.append(item)
        if len(unique) >= MAX_LOOKUPS:
            break
    return unique


def _routes(callsigns: list[str]) -> dict[str, dict | None]:
    now = time.monotonic()
    ready: dict[str, dict | None] = {}
    missing = []
    for callsign in callsigns:
        cached = _route_cache.get(callsign)
        if cached and now - cached[0] < cached[1]:
            ready[callsign] = cached[2]
        else:
            missing.append(callsign)
    if missing:
        for start in range(0, len(missing), 4):
            chunk = missing[start : start + 4]
            with ThreadPoolExecutor(max_workers=4) as pool:
                for callsign, route in pool.map(_load_route, chunk):
                    ready[callsign] = route
            if start + 4 < len(missing):
                time.sleep(0.35)
    return ready


def _load_route(callsign: str) -> tuple[str, dict | None]:
    url = ROUTE.format(callsign=urllib.parse.quote(callsign))
    try:
        payload = _read_json(url)
    except SourceError:
        payload = None
    route = payload if isinstance(payload, dict) else None
    _route_cache[callsign] = (time.monotonic(), ROUTE_TTL if route else MISS_TTL, route)
    return callsign, route
