"""Онлайн-табло Домодедово: публичная HTML-страница dme.ru."""

from __future__ import annotations

import re
from datetime import date, datetime

from bs4 import BeautifulSoup

from app.flights import MOSCOW, make_flight
from app.http_client import get_text

SOURCE_URL = "https://www.dme.ru/flight/live-board/"
BOARD = "https://www.dme.ru/book/live-board/?direction={code}"

MONTHS = {
    "янв": 1,
    "фев": 2,
    "мар": 3,
    "апр": 4,
    "май": 5,
    "мая": 5,
    "июн": 6,
    "июл": 7,
    "авг": 8,
    "сен": 9,
    "окт": 10,
    "ноя": 11,
    "дек": 12,
}
FLIGHT_RE = re.compile(r"\b([A-Z0-9]{2})\s*(\d{2,4})\b")
STAMP_RE = re.compile(r"(\d{1,2})\s+([а-яё]{3,8})\.?\s+(\d{1,2}):(\d{2})", re.IGNORECASE)


def fetch(direction: str, day: date) -> dict:
    code = "D" if direction == "departure" else "A"
    html = get_text(BOARD.format(code=code))
    parsed = parse_html(html, direction, day.year)
    window = parsed["window"]
    notice = "Домодедово публикует скользящее окно табло вокруг текущего времени, а не весь день."
    if window:
        notice = f"{notice} Сейчас на табло: {window}."
    return {
        "flights": parsed["flights"],
        "source_url": SOURCE_URL,
        "notice": notice,
    }


def parse_html(html: str, direction: str, year: int) -> dict:
    soup = BeautifulSoup(html, "html.parser")
    window = _window(soup)
    flights = []
    for row in soup.select("tr.vat"):
        flight = _row(row, year, direction)
        if flight:
            flights.append(flight)
    flights.sort(key=lambda item: item.get("scheduled") or "9999")
    return {"flights": flights, "window": window}


def _window(soup: BeautifulSoup) -> str:
    match = re.search(r"Показываются рейсы\s*:\s*(.+)", soup.get_text("\n", strip=True))
    if not match:
        return ""
    return re.sub(r"\s+", " ", match.group(1)).strip(" .")


def _row(row, year: int, direction: str) -> dict | None:
    scheduled_td = None
    actual_td = None
    flight_td = None
    city_td = None
    status_td = None
    zone_td = None
    for cell in row.find_all("td", recursive=False):
        classes = " ".join(cell.get("class") or [])
        cell_id = cell.get("id") or ""
        if "timeflight" in classes:
            continue
        if cell_id.startswith("time"):
            actual_td = cell
            continue
        if cell_id.startswith("course"):
            city_td = cell
            continue
        if cell.select_one("a.dialogopen"):
            flight_td = cell
            continue
        if cell.select_one("ul") or "flightlate" in classes:
            status_td = cell
            continue
        text = _clean(cell.get_text(" ", strip=True))
        if scheduled_td is None:
            scheduled_td = cell
        elif zone_td is None and text:
            zone_td = cell
    if flight_td is None:
        return None
    numbers = FLIGHT_RE.findall(_clean(flight_td.get_text(" ", strip=True)).upper())
    if not numbers:
        return None
    labels = [f"{code} {number}" for code, number in numbers]
    image = flight_td.find("img")
    airline = ""
    if image is not None:
        airline = _clean(image.get("title") or image.get("alt") or "")
    zone = _clean(zone_td.get_text(" ", strip=True)) if zone_td else ""
    status = _status(status_td)
    gate, belt = _place(status, direction)
    return make_flight(
        flight=labels[0],
        airline=airline,
        airline_code=numbers[0][0],
        city=_clean(city_td.get_text(" ", strip=True)) if city_td else "",
        scheduled=_stamp(scheduled_td, year),
        estimated=None,
        actual=_stamp(actual_td, year),
        terminal=zone,
        gate=gate,
        belt=belt,
        status=status,
        codeshare=labels[1:],
    )


def _place(status: str, direction: str) -> tuple[str, str]:
    if direction == "departure":
        match = re.search(r"выход\s+([A-ZА-Я0-9]+)", status, re.IGNORECASE)
        return (match.group(1) if match else "", "")
    match = re.search(r"лент[аеуы]\s+([A-ZА-Я0-9]+)", status, re.IGNORECASE)
    return ("", match.group(1) if match else "")


def _status(cell) -> str:
    if cell is None:
        return ""
    chunks = []
    for item in cell.select("li"):
        text = _clean(item.get_text(" ", strip=True))
        if text and text not in chunks:
            chunks.append(text)
    if chunks:
        return " · ".join(chunks)
    return _clean(cell.get_text(" ", strip=True))


def _stamp(cell, year: int) -> str | None:
    if cell is None:
        return None
    text = _clean(cell.get_text(" ", strip=True))
    match = STAMP_RE.search(text)
    if not match:
        return None
    day_num = int(match.group(1))
    month = MONTHS.get(match.group(2).lower()[:3])
    if not month:
        return None
    hour = int(match.group(3))
    minute = int(match.group(4))
    try:
        moment = datetime(year, month, day_num, hour, minute, tzinfo=MOSCOW)
    except ValueError:
        return None
    return moment.isoformat(timespec="minutes")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").replace("\xa0", " ")).strip()
