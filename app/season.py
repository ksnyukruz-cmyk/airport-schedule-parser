"""Разложение сезонного расписания по дням, неделям и месяцам.

Паттерн — строка расписания: дни недели и период действия. Пассажиров в таких
таблицах нет, поэтому сводка считает вылеты.
"""

from __future__ import annotations

import re
from datetime import date, datetime, timedelta

from bs4 import BeautifulSoup

from app.flights import MOSCOW, as_text, flight_date

MAX_SPAN_DAYS = 400

MONTHS = (
    ("янв", 1),
    ("фев", 2),
    ("мар", 3),
    ("апр", 4),
    ("мая", 5),
    ("май", 5),
    ("июн", 6),
    ("июл", 7),
    ("авг", 8),
    ("сен", 9),
    ("окт", 10),
    ("ноя", 11),
    ("дек", 12),
)

DAY_NAMES = {
    "пн": 0,
    "понедельник": 0,
    "вт": 1,
    "вторник": 1,
    "ср": 2,
    "среда": 2,
    "чт": 3,
    "четверг": 3,
    "пт": 4,
    "пятница": 4,
    "сб": 5,
    "суббота": 5,
    "вс": 6,
    "воскресенье": 6,
    "дш": 0,
    "дүшәмбе": 0,
    "душәмбе": 0,
    "си": 1,
    "сишәмбе": 1,
    "чш": 2,
    "чәршәмбе": 2,
    "пнҗ": 3,
    "пәнҗешәмбе": 3,
    "җг": 4,
    "җомга": 4,
    "шб": 5,
    "шимбә": 5,
    "як": 6,
    "якшәмбе": 6,
}

MONTH_LABELS = (
    "",
    "янв",
    "фев",
    "мар",
    "апр",
    "май",
    "июн",
    "июл",
    "авг",
    "сен",
    "окт",
    "ноя",
    "дек",
)

RU_PERIOD = re.compile(
    r"(\d{1,2})\s*([а-яё]+)\s*/\s*(\d{1,2})\s*([а-яё]+)",
    re.IGNORECASE,
)
NUM_DATE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
DAY_RANGE = re.compile(r"(пн|вт|ср|чт|пт|сб|вс)\s*[-–—]\s*(пн|вт|ср|чт|пт|сб|вс)")
WORD = re.compile(r"[a-zа-яёҗәөү0-9]+", re.IGNORECASE)
FLIGHT_NO = re.compile(r"^([A-Z0-9]{2})[\s-]*(\d{1,5}[A-Z]?)$")


def month_key(day: date) -> str:
    return f"{day.year:04d}-{day.month:02d}"


def week_key(day: date) -> str:
    year, week, _weekday = day.isocalendar()
    return f"{year}-W{week:02d}"


def month_label(key: str) -> str:
    year, month = key.split("-")
    return f"{MONTH_LABELS[int(month)]} {year}"


def week_label(key: str) -> str:
    year, week = key.split("-W")
    monday = date.fromisocalendar(int(year), int(week), 1)
    sunday = date.fromisocalendar(int(year), int(week), 7)
    return f"{monday:%d.%m}–{sunday:%d.%m}"


def season_date(day_num: int, month: int, today: date) -> date | None:
    if today.month >= 10:
        year = today.year if month >= 10 else today.year + 1
    elif today.month <= 3:
        year = today.year - 1 if month >= 10 else today.year
    else:
        year = today.year if month >= 4 else today.year + 1
    try:
        return date(year, month, day_num)
    except ValueError:
        return None


def month_number(token: str) -> int | None:
    name = token.lower().replace("ё", "е")
    for prefix, number in MONTHS:
        if name.startswith(prefix):
            return number
    return None


def parse_weekdays(text: str) -> set[int]:
    lowered = text.lower().replace("ё", "е")
    if "ежедн" in lowered:
        return set(range(7))
    found: set[int] = set()
    for start, end in DAY_RANGE.findall(lowered):
        left, right = DAY_NAMES[start], DAY_NAMES[end]
        if left <= right:
            found.update(range(left, right + 1))
        else:
            found.update(range(left, 7))
            found.update(range(0, right + 1))
    for token in WORD.findall(lowered):
        if token in DAY_NAMES:
            found.add(DAY_NAMES[token])
    return found


def parse_numeric_dates(text: str) -> list[date]:
    found = []
    for day_s, month_s, year_s in NUM_DATE.findall(text):
        try:
            found.append(date(int(year_s), int(month_s), int(day_s)))
        except ValueError:
            continue
    return found


def parse_period(text: str, today: date) -> tuple[date | None, date | None]:
    cleaned = text.replace("\xa0", " ")
    numeric = parse_numeric_dates(cleaned)
    if len(numeric) >= 2:
        return min(numeric), max(numeric)
    if len(numeric) == 1:
        return numeric[0], numeric[0]
    match = RU_PERIOD.search(cleaned.lower().replace("ё", "е"))
    if not match:
        return None, None
    start = season_date(int(match.group(1)), month_number(match.group(2)) or 0, today)
    end = season_date(int(match.group(3)), month_number(match.group(4)) or 0, today)
    if start is None or end is None:
        return None, None
    if end < start:
        try:
            end = end.replace(year=end.year + 1)
        except ValueError:
            return None, None
    return start, end


def split_flight(value: str) -> tuple[str, str]:
    text = as_text(value).upper().replace("–", "-").replace("—", "-")
    match = FLIGHT_NO.match(text)
    if not match:
        compact = text.replace(" ", "").replace("-", "")
        match = FLIGHT_NO.match(compact)
    if not match:
        return "", text
    code, number = match.group(1), match.group(2)
    return code, f"{code} {number}"


def make_pattern(
    airport: str,
    airline: str,
    airline_code: str,
    city: str,
    city_code: str = "",
    weekdays: set[int] | None = None,
    start: date | None = None,
    end: date | None = None,
    dates: list[date] | None = None,
) -> dict | None:
    city = re.sub(r"\s+", " ", as_text(city))
    airline = re.sub(r"\s+", " ", as_text(airline))
    code = as_text(airline_code).upper()
    if dates:
        days = sorted(set(dates))
        return {
            "airport": airport,
            "airline": airline or code,
            "airline_code": code,
            "city": city or city_code or "без города",
            "city_code": as_text(city_code).upper(),
            "weekdays": set(),
            "start": days[0],
            "end": days[-1],
            "dates": days,
        }
    if start is None or end is None or end < start:
        return None
    active = set(weekdays or [])
    if not active and start != end:
        return None
    return {
        "airport": airport,
        "airline": airline or code,
        "airline_code": code,
        "city": city or city_code or "без города",
        "city_code": as_text(city_code).upper(),
        "weekdays": active,
        "start": start,
        "end": end,
        "dates": None,
    }


def iter_dates(pattern: dict):
    explicit = pattern.get("dates")
    if explicit:
        for day in explicit:
            yield day
        return
    start = pattern.get("start")
    end = pattern.get("end")
    if start is None or end is None:
        return
    if (end - start).days > MAX_SPAN_DAYS:
        end = start + timedelta(days=MAX_SPAN_DAYS)
    weekdays = pattern.get("weekdays") or set()
    if not weekdays:
        if start == end:
            yield start
        return
    day = start
    while day <= end:
        if day.weekday() in weekdays:
            yield day
        day += timedelta(days=1)


def parse_svo_items(items: list) -> list[dict]:
    patterns = []
    seen = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        if as_text(item.get("ad")).upper() not in {"", "D"}:
            continue
        marker = item.get("i_id") or id(item)
        if marker in seen:
            continue
        seen.add(marker)
        company = item.get("co") if isinstance(item.get("co"), dict) else {}
        code = as_text(company.get("code")).upper()
        number = as_text(item.get("flt"))
        flight_code = code or split_flight(number)[0]
        names = [
            as_text(item.get(key))
            for key in ("mar5_name", "mar4_name", "mar3_name", "mar2_name")
        ]
        city = next((name for name in names if name), "")
        start = _iso_day(item.get("date_b"))
        end = _iso_day(item.get("date_e"))
        days = item.get("days") if isinstance(item.get("days"), dict) else {}
        weekdays = set()
        for index, key in enumerate(("mo", "tu", "we", "th", "fr", "sa", "su")):
            if days.get(key):
                weekdays.add(index)
        single = [start] if start and end and start == end else None
        pattern = make_pattern(
            "SVO",
            as_text(company.get("name")),
            flight_code,
            city,
            weekdays=set() if single else weekdays,
            start=start,
            end=end,
            dates=single,
        )
        if pattern:
            patterns.append(pattern)
    return patterns


def parse_svx_html(html: str, today: date) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    patterns = []
    city = ""
    for row in soup.select("table tr"):
        city_cell = row.select_one(".table-wrap__city-row")
        if city_cell:
            city = city_cell.get_text(" ", strip=True)
            continue
        cells = row.find_all("td")
        if len(cells) < 8:
            continue
        titled = cells[4].select_one("[title]")
        alt = cells[4].select_one(".table-aircompany-logo-alt")
        airline = ""
        if titled and titled.get("title"):
            airline = titled["title"]
        elif alt:
            airline = alt.get_text(" ", strip=True)
        code, _flight = split_flight(cells[5].get_text(" ", strip=True))
        start, end = parse_period(cells[3].get_text(" ", strip=True), today)
        one_days = parse_numeric_dates(cells[2].get_text(" ", strip=True))
        weekdays = parse_weekdays(cells[2].get_text(" ", strip=True))
        pattern = make_pattern(
            "SVX",
            airline,
            code,
            city,
            cells[7].get_text(" ", strip=True),
            weekdays=weekdays,
            start=start,
            end=end,
            dates=one_days if one_days and not weekdays else None,
        )
        if pattern:
            patterns.append(pattern)
    return patterns


def kzn_city_links(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    links = []
    seen = set()
    for anchor in soup.select("a.town__name"):
        href = as_text(anchor.get("href"))
        name = anchor.get_text(" ", strip=True)
        if not href or not name or href in seen:
            continue
        seen.add(href)
        links.append((name, href))
    return links


def parse_kzn_html(html: str, city: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    patterns = []
    for item in soup.select(".flights-table__item"):
        days_node = item.select_one(".table_days")
        number_node = item.select_one(".item-number__name-text")
        airline_node = item.select_one(".item-number__name")
        period_node = item.select_one(".table_dates")
        days_text = days_node.get_text(" ", strip=True) if days_node else ""
        period_text = period_node.get_text(" ", strip=True) if period_node else ""
        code, _flight = split_flight(number_node.get_text(" ", strip=True) if number_node else "")
        airline = ""
        if airline_node and airline_node.get("title"):
            airline = airline_node["title"]
        weekdays = parse_weekdays(days_text)
        one_days = parse_numeric_dates(days_text)
        start, end = parse_period(period_text, date.today())
        explicit = None
        if one_days and not weekdays:
            explicit = one_days
        elif start and end and not weekdays and start == end:
            explicit = [start]
        pattern = make_pattern(
            "KZN",
            airline,
            code,
            city,
            weekdays=weekdays,
            start=start,
            end=end,
            dates=explicit,
        )
        if pattern:
            patterns.append(pattern)
    return patterns


def patterns_from_board(airport: str, flights: list[dict]) -> list[dict]:
    patterns = []
    for flight in flights:
        status = as_text(flight.get("status")).lower().replace("ё", "е")
        if "отмен" in status or "cancel" in status:
            continue
        day = flight_date(flight.get("scheduled"))
        if day is None:
            continue
        code = as_text(flight.get("airline_code")).upper()
        if not code:
            code = split_flight(flight.get("flight") or "")[0]
        pattern = make_pattern(
            airport,
            flight.get("airline") or "",
            code,
            flight.get("city") or "",
            flight.get("city_code") or "",
            dates=[day],
        )
        if pattern:
            patterns.append(pattern)
    return patterns


def parse_fr24_departures(payload: dict, airport: str) -> list[dict]:
    try:
        departures = payload["result"]["response"]["airport"]["pluginData"]["schedule"]["departures"]
    except (TypeError, KeyError, AttributeError):
        return []
    flights = []
    for row in departures.get("data") or []:
        flight = row.get("flight") if isinstance(row, dict) else None
        if not isinstance(flight, dict):
            continue
        status = (((flight.get("status") or {}).get("generic") or {}).get("status") or {}).get("text") or ""
        number = (((flight.get("identification") or {}).get("number") or {}).get("default")) or ""
        airline = flight.get("airline") if isinstance(flight.get("airline"), dict) else {}
        code = ((airline.get("code") or {}).get("iata")) or ""
        destination = ((flight.get("airport") or {}).get("destination") or {})
        position = (destination.get("position") or {}) if isinstance(destination, dict) else {}
        region = position.get("region") if isinstance(position.get("region"), dict) else {}
        city = region.get("city") or ""
        iata = ((destination.get("code") or {}).get("iata")) if isinstance(destination, dict) else ""
        scheduled = ((flight.get("time") or {}).get("scheduled") or {}).get("departure")
        if not isinstance(scheduled, (int, float)):
            continue
        moment = datetime.fromtimestamp(int(scheduled), MOSCOW)
        flights.append(
            {
                "flight": number,
                "airline": airline.get("name") or airline.get("short") or "",
                "airline_code": code,
                "city": city,
                "city_code": iata or "",
                "scheduled": moment.isoformat(timespec="minutes"),
                "status": status,
            }
        )
    return patterns_from_board(airport, flights)


def aggregate(patterns: list[dict]) -> dict:
    grouped: dict[tuple, dict] = {}
    bounds: dict[str, list[date]] = {}
    month_keys: set[str] = set()
    week_keys: set[str] = set()
    year_keys: set[str] = set()
    for pattern in patterns:
        key = (
            pattern["airport"],
            pattern.get("airline_code") or pattern.get("airline", "").casefold(),
            pattern.get("city_code") or pattern.get("city", "").casefold(),
            pattern.get("city", "").casefold(),
        )
        row = grouped.get(key)
        if row is None:
            row = {
                "airport": pattern["airport"],
                "airline": pattern.get("airline") or pattern.get("airline_code") or "",
                "airline_code": pattern.get("airline_code") or "",
                "city": pattern.get("city") or "",
                "city_code": pattern.get("city_code") or "",
                "flights": 0,
                "years": {},
                "months": {},
                "weeks": {},
            }
            grouped[key] = row
        elif len(pattern.get("airline") or "") > len(row["airline"]):
            row["airline"] = pattern["airline"]
        for day in iter_dates(pattern):
            row["flights"] += 1
            month = month_key(day)
            week = week_key(day)
            year = f"{day.year:04d}"
            row["months"][month] = row["months"].get(month, 0) + 1
            row["weeks"][week] = row["weeks"].get(week, 0) + 1
            row["years"][year] = row["years"].get(year, 0) + 1
            month_keys.add(month)
            week_keys.add(week)
            year_keys.add(year)
            edges = bounds.setdefault(pattern["airport"], [day, day])
            if day < edges[0]:
                edges[0] = day
            if day > edges[1]:
                edges[1] = day
    rows = [row for row in grouped.values() if row["flights"]]
    rows.sort(key=lambda item: (-item["flights"], item["airport"], item["airline"], item["city"]))
    months = [{"key": key, "label": month_label(key)} for key in sorted(month_keys)]
    weeks = [{"key": key, "label": week_label(key)} for key in sorted(week_keys)]
    years = [{"key": key, "label": key} for key in sorted(year_keys)]
    return {
        "rows": rows,
        "years": years,
        "months": months,
        "weeks": weeks,
        "bounds": {code: (edges[0].isoformat(), edges[1].isoformat()) for code, edges in bounds.items()},
    }


def _iso_day(value) -> date | None:
    text = as_text(value)
    if len(text) < 10:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None
