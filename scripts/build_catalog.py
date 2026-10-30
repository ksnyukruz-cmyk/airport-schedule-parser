"""Собирает список крупных аэропортов и коды авиакомпаний.

Источник аэропортов — открытые данные OurAirports (крупные аэропорты с кодом IATA).
Коды авиакомпаний — открытый справочник OpenFlights.
"""

from __future__ import annotations

import csv
import io
import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "app" / "data"

AIRPORTS_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/airports.csv"
COUNTRIES_URL = "https://raw.githubusercontent.com/davidmegginson/ourairports-data/main/countries.csv"
AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"

RUSSIAN = {
    "SVO": "москва шереметьево",
    "DME": "москва домодедово",
    "VKO": "москва внуково",
    "ZIA": "жуковский",
    "LED": "санкт-петербург питер пулково",
    "AER": "сочи адлер",
    "KZN": "казань",
    "SVX": "екатеринбург",
    "OVB": "новосибирск",
    "IKT": "иркутск",
    "VVO": "владивосток",
    "KJA": "красноярск",
    "UFA": "уфа",
    "KUF": "самара",
    "GOJ": "нижний новгород",
    "ROV": "ростов",
    "KRR": "краснодар",
    "MRV": "минеральные воды",
    "LHR": "лондон хитроу",
    "LGW": "лондон гатвик",
    "CDG": "париж",
    "ORY": "париж орли",
    "FRA": "франкфурт",
    "MUC": "мюнхен",
    "AMS": "амстердам",
    "IST": "стамбул",
    "SAW": "стамбул",
    "DXB": "дубай",
    "AUH": "абу-даби",
    "DOH": "доха",
    "SIN": "сингапур",
    "HKG": "гонконг",
    "HND": "токио ханеда",
    "NRT": "токио нарита",
    "ICN": "сеул",
    "PEK": "пекин",
    "PKX": "пекин",
    "PVG": "шанхай",
    "JFK": "нью-йорк",
    "EWR": "нью-йорк",
    "LAX": "лос-анджелес",
    "ORD": "чикаго",
    "ATL": "атланта",
    "MIA": "майами",
    "SFO": "сан-франциско",
    "MAD": "мадрид",
    "BCN": "барселона",
    "FCO": "рим",
    "MXP": "милан",
    "VIE": "вена",
    "ZRH": "цюрих",
    "WAW": "варшава",
    "PRG": "прага",
    "HEL": "хельсинки",
    "ARN": "стокгольм",
    "OSL": "осло",
    "CPH": "копенгаген",
    "ATH": "афины",
    "LIS": "лиссабон",
    "BKK": "бангкок",
    "DEL": "дели",
    "BOM": "мумбаи",
    "SYD": "сидней",
    "MEL": "мельбурн",
    "GRU": "сан-паулу",
    "EZE": "буэнос-айрес",
    "YYZ": "торонто",
    "YUL": "монреаль",
}


def main() -> None:
    countries = {
        row["code"]: row["name"]
        for row in csv.DictReader(io.StringIO(_download(COUNTRIES_URL)))
    }
    chosen: dict[str, dict] = {}
    for row in csv.DictReader(io.StringIO(_download(AIRPORTS_URL))):
        code = (row.get("iata_code") or "").strip().upper()
        if row.get("type") != "large_airport" or row.get("scheduled_service") != "yes":
            continue
        if len(code) != 3 or not code.isalnum():
            continue
        try:
            lat = float(row["latitude_deg"])
            lon = float(row["longitude_deg"])
        except (TypeError, ValueError):
            continue
        keywords = " ".join(
            part
            for part in (
                row.get("keywords") or "",
                row.get("municipality") or "",
                RUSSIAN.get(code, ""),
            )
            if part
        )
        airport = {
            "code": code,
            "icao": (row.get("icao_code") or "").strip().upper(),
            "name": (row.get("name") or code).strip(),
            "city": (row.get("municipality") or "").strip(),
            "country": countries.get(row.get("iso_country") or "", row.get("iso_country") or ""),
            "keywords": " ".join(keywords.split())[:180],
            "lat": round(lat, 4),
            "lon": round(lon, 4),
        }
        previous = chosen.get(code)
        if previous is None or len(airport["keywords"]) > len(previous["keywords"]):
            chosen[code] = airport
    airports = sorted(chosen.values(), key=lambda item: (item["country"], item["city"], item["code"]))

    airlines: dict[str, dict] = {}
    for row in csv.reader(io.StringIO(_download(AIRLINES_URL))):
        if len(row) < 8 or row[7] != "Y":
            continue
        icao = row[4].strip().upper()
        if len(icao) != 3 or not icao.isalpha() or icao == "N":
            continue
        iata = row[3].strip().upper()
        airlines[icao] = {
            "iata": iata if len(iata) == 2 and iata.isalnum() else "",
            "name": row[1].strip(),
        }

    DATA.mkdir(parents=True, exist_ok=True)
    (DATA / "airports.json").write_text(json.dumps(airports, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (DATA / "airlines.json").write_text(json.dumps(airlines, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"airports {len(airports)}")
    print(f"airlines {len(airlines)}")


def _download(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    return urllib.request.urlopen(request, timeout=60).read().decode("utf-8")


if __name__ == "__main__":
    main()
