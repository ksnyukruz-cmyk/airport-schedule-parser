"""Сводка топ-10 аэропортов РФ: авиакомпании, направления, недели и месяцы."""

from __future__ import annotations

import json
import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.flights import MOSCOW
from app.http_client import SourceError, get_json, get_text
from app.season import (
    aggregate,
    kzn_city_links,
    parse_fr24_departures,
    parse_kzn_html,
    parse_svo_items,
    parse_svx_html,
    patterns_from_board,
)
from app.sources.pulkovo import parse_rows as parse_pulkovo
from app.sources.vko import fetch as fetch_vko

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache" / "summary.json"
TTL_SECONDS = 6 * 60 * 60
SVO_CATALOG = "https://svo.su/season/"
SVO_LIST = "https://svo.su/season/list_v2/"
SVX_URL = "https://ar-svx.ru/schedule/"
KZN_INDEXES = (
    "https://new.kazan.aero/seasonal-schedule/",
    "https://new.kazan.aero/tt/seasonal-schedule/",
)

# Пассажиропоток за 2024 год, Росавиация. Нужен только как порядок аэропортов.
TOP10 = (
    ("SVO", "Шереметьево", 43_712_000),
    ("LED", "Пулково", 20_900_000),
    ("VKO", "Внуково", 16_095_000),
    ("DME", "Домодедово", 15_600_000),
    ("AER", "Сочи", 13_726_000),
    ("OVB", "Толмачёво", 9_299_000),
    ("SVX", "Кольцово", 8_047_000),
    ("KZN", "Казань", 5_369_000),
    ("MRV", "Минеральные Воды", 4_860_000),
    ("KGD", "Храброво", 4_814_000),
)

GAPS = {
    "DME": "Табло Домодедово показывает только ближайшие часы. Сезон с днями недели сайт не отдаёт.",
    "AER": "На сайте Сочи нет таблицы с днями недели и периодом.",
    "OVB": "Сайт Толмачёво закрывает расписание проверкой браузера.",
    "MRV": "Сайт Минеральных Вод закрывает расписание проверкой браузера.",
    "KGD": "Сайт Храброво закрывает расписание проверкой браузера.",
}

_LOCK = threading.Lock()


def get_summary(refresh: bool = False) -> dict:
    with _LOCK:
        cached = _read_cache()
        if cached and not refresh and time.time() - cached["saved_at"] < TTL_SECONDS:
            return cached["payload"]
        payload = build_summary()
        _write_cache(payload)
        return payload


def build_summary() -> dict:
    today = datetime.now(MOSCOW).date()
    collected = []
    reports = {}
    for code, fetcher in (
        ("SVO", _fetch_svo),
        ("SVX", lambda: _fetch_svx(today)),
        ("KZN", _fetch_kzn),
        ("LED", _fetch_led),
        ("VKO", _fetch_vko_days),
        ("DME", lambda: _fetch_fr24("DME")),
        ("AER", lambda: _fetch_fr24("AER")),
        ("OVB", lambda: _fetch_fr24("OVB")),
        ("MRV", lambda: _fetch_fr24("MRV")),
        ("KGD", lambda: _fetch_fr24("KGD")),
    ):
        try:
            reports[code] = fetcher()
        except Exception as error:
            reports[code] = _failed(error)
        collected.extend(reports[code]["patterns"])
    folded = aggregate(collected)
    airports = []
    for rank, (code, name, passengers) in enumerate(TOP10, start=1):
        report = reports.get(code)
        own = [row for row in folded["rows"] if row["airport"] == code]
        start, end = folded["bounds"].get(code, ("", ""))
        if report is None:
            status, source, url, note = "gap", "", "", GAPS.get(code, "Сезонная таблица не подключена.")
        else:
            status = report["status"]
            source = report["source"]
            url = report["source_url"]
            note = report["note"]
            if status == "ok" and not own:
                status = "error"
                note = note or "Расписание открылось, но вылетов в нём не нашлось."
        airports.append(
            {
                "code": code,
                "name": name,
                "rank": rank,
                "passengers": passengers,
                "status": status,
                "source": source,
                "source_url": url,
                "note": note,
                "flights": sum(row["flights"] for row in own),
                "airlines": len({row["airline_code"] or row["airline"] for row in own}),
                "cities": len({row["city_code"] or row["city"] for row in own}),
                "start": start,
                "end": end,
            }
        )
    return {
        "built_at": datetime.now(MOSCOW).isoformat(timespec="minutes"),
        "metric": "вылеты",
        "note": (
            "Число вылетов, не пассажиры. Шереметьево, Кольцово и Казань разложены "
            "по дням недели на весь опубликованный сезон. Пулково и Внуково — по официальному табло "
            "на те дни, которые оно показывает. Домодедово, Сочи, Толмачёво, Минеральные Воды и Храброво — "
            "по расписанию Flightradar24 на ближайшие дни: у этих аэропортов нет открытой сезонной таблицы."
        ),
        "airports": airports,
        "months": folded["months"],
        "weeks": folded["weeks"],
        "rows": folded["rows"],
    }


def _fetch_svo() -> dict:
    catalog = get_json(SVO_CATALOG)
    city_ids = []
    for region in catalog.get("data") or []:
        if not isinstance(region, dict):
            continue
        for city in region.get("cities") or []:
            if isinstance(city, dict) and city.get("id"):
                city_ids.append(str(city["id"]))
    items, failed = _load_svo_cities(city_ids, 4)
    if failed:
        time.sleep(2)
        extra, failed = _load_svo_cities(failed, 2)
        items.extend(extra)
    note = ""
    status = "ok"
    if failed:
        status = "partial"
        note = f"Не открылись {len(failed)} из {len(city_ids)} направлений."
    return {
        "patterns": parse_svo_items(items),
        "source": "Сезонное расписание Шереметьево",
        "source_url": "https://svo.su/ru/season-schedule",
        "note": note,
        "status": status,
    }


def _load_svo_cities(city_ids: list[str], workers: int) -> tuple[list, list[str]]:
    items: list = []
    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_svo_city, city_id): city_id for city_id in city_ids}
        for future in as_completed(futures):
            try:
                items.extend(future.result())
            except Exception:
                failed.append(futures[future])
    return items, failed


def _svo_city(city_id: str) -> list:
    items = []
    for page in range(1, 6):
        query = urllib.parse.urlencode(
            {"city": city_id, "direction": "departure", "perPage": 500, "page": page}
        )
        payload = get_json(f"{SVO_LIST}?{query}")
        if not isinstance(payload, dict):
            raise SourceError("Шереметьево вернуло неожиданный ответ сезона")
        batch = payload.get("items") or []
        items.extend(batch)
        total = int((payload.get("pagination") or {}).get("totalItems") or 0)
        if not batch or len(items) >= total:
            break
    return items


def _fetch_svx(today) -> dict:
    patterns = parse_svx_html(get_text(SVX_URL), today)
    return {
        "patterns": patterns,
        "source": "Сезонное расписание Кольцово",
        "source_url": SVX_URL,
        "note": "",
        "status": "ok",
    }


def _fetch_kzn() -> dict:
    index_url = ""
    links: list[tuple[str, str]] = []
    for candidate in KZN_INDEXES:
        html = get_text(candidate)
        found = kzn_city_links(html)
        if found:
            index_url = candidate
            links = found
            break
    if not links:
        raise SourceError("Казань не показала список городов сезона")
    patterns = []
    errors = 0
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(_kzn_city, index_url, name, href) for name, href in links]
        for future in futures:
            try:
                patterns.extend(future.result())
            except Exception:
                errors += 1
    note = ""
    status = "ok"
    if errors:
        status = "partial"
        note = f"Не открылись {errors} из {len(links)} городов."
    return {
        "patterns": patterns,
        "source": "Сезонное расписание Казани",
        "source_url": index_url,
        "note": note,
        "status": status,
    }


def _kzn_city(index_url: str, name: str, href: str) -> list:
    page = get_text(urllib.parse.urljoin(index_url, href))
    return parse_kzn_html(page, name)


def _fetch_led() -> dict:
    payload = get_json("https://pulkovoairport.ru/api/?col=1000&type=departure")
    if not isinstance(payload, list):
        raise SourceError("Пулково вернуло неожиданный ответ")
    patterns = patterns_from_board("LED", parse_pulkovo(payload, "departure", None))
    return {
        "patterns": patterns,
        "source": "Официальное табло Пулково",
        "source_url": "https://pulkovoairport.ru/",
        "note": "Табло публикует несколько ближайших дней, не весь сезон.",
        "status": "partial",
    }


def _fetch_vko_days() -> dict:
    today = datetime.now(MOSCOW).date()
    flights = []
    errors = 0
    for offset in range(3):
        try:
            board = fetch_vko("departure", today.fromordinal(today.toordinal() + offset))
            flights.extend(board.get("flights") or [])
        except Exception:
            errors += 1
    note = "Табло публикует несколько ближайших дней, не весь сезон."
    if errors:
        note = f"{note} Не открылись {errors} из 3 дней."
    return {
        "patterns": patterns_from_board("VKO", flights),
        "source": "Официальное табло Внуково",
        "source_url": "https://www.vnukovo.ru/ru/for-passengers/reysi/online-tablo/",
        "note": note,
        "status": "partial",
    }


def _fetch_fr24(code: str) -> dict:
    today = datetime.now(MOSCOW).date()
    patterns = []
    opened = 0
    for offset in range(2):
        day = today + timedelta(days=offset)
        stamp = int(datetime(day.year, day.month, day.day, tzinfo=timezone.utc).timestamp())
        try:
            patterns.extend(_fr24_pages(code, stamp))
            opened += 1
        except Exception:
            continue
    if not patterns:
        return {
            "patterns": [],
            "source": "Flightradar24",
            "source_url": f"https://www.flightradar24.com/data/airports/{code.lower()}",
            "note": GAPS.get(code, "Расписание не открылось."),
            "status": "gap",
        }
    return {
        "patterns": patterns,
        "source": "Flightradar24",
        "source_url": f"https://www.flightradar24.com/data/airports/{code.lower()}",
        "note": "Ближайшие дни из Flightradar24, не весь сезон." if opened else "",
        "status": "partial",
    }


def _fr24_pages(code: str, stamp: int) -> list:
    patterns = []
    for page in range(1, 6):
        url = (
            "https://api.flightradar24.com/common/v1/airport.json"
            f"?code={code}&plugin[]=schedule&plugin-setting[schedule][mode]=departures"
            f"&plugin-setting[schedule][timestamp]={stamp}&limit=100&page={page}"
        )
        payload = get_json(url)
        patterns.extend(parse_fr24_departures(payload, code))
        try:
            info = payload["result"]["response"]["airport"]["pluginData"]["schedule"]["departures"].get("page") or {}
            total = int(info.get("total") or 1)
        except (TypeError, KeyError, ValueError):
            total = 1
        if page >= total:
            break
    return patterns


def _failed(error: Exception) -> dict:
    note = str(error) if isinstance(error, SourceError) else "Расписание не открылось."
    return {"patterns": [], "source": "", "source_url": "", "note": note, "status": "error"}


def _read_cache() -> dict | None:
    try:
        payload = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or "payload" not in payload:
        return None
    return payload


def _write_cache(payload: dict) -> None:
    try:
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(
            json.dumps({"saved_at": time.time(), "payload": payload}, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError:
        return
