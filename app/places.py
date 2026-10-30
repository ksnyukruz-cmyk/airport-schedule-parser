"""Страна города на другом конце рейса.

Код аэропорта берётся из справочника крупных аэропортов. Домодедово отдаёт
только русское название, поэтому для типичных городов есть отдельные имена.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

DATA = Path(__file__).resolve().parent / "data" / "airports.json"

COUNTRY_RU = {
    "Armenia": "Армения",
    "Azerbaijan": "Азербайджан",
    "Bahrain": "Бахрейн",
    "Belarus": "Беларусь",
    "China": "Китай",
    "Cyprus": "Кипр",
    "Egypt": "Египет",
    "France": "Франция",
    "Georgia": "Грузия",
    "Germany": "Германия",
    "Greece": "Греция",
    "Hong Kong": "Гонконг",
    "India": "Индия",
    "Indonesia": "Индонезия",
    "Israel": "Израиль",
    "Italy": "Италия",
    "Japan": "Япония",
    "Kazakhstan": "Казахстан",
    "Kuwait": "Кувейт",
    "Kyrgyzstan": "Киргизия",
    "Malaysia": "Малайзия",
    "Maldives": "Мальдивы",
    "Montenegro": "Черногория",
    "Oman": "Оман",
    "Qatar": "Катар",
    "Russia": "Россия",
    "Saudi Arabia": "Саудовская Аравия",
    "Serbia": "Сербия",
    "Singapore": "Сингапур",
    "South Korea": "Южная Корея",
    "Spain": "Испания",
    "Sri Lanka": "Шри-Ланка",
    "Tajikistan": "Таджикистан",
    "Thailand": "Таиланд",
    "Tunisia": "Тунис",
    "Turkey": "Турция",
    "United Arab Emirates": "ОАЭ",
    "United Kingdom": "Великобритания",
    "United States": "США",
    "Uzbekistan": "Узбекистан",
    "Vietnam": "Вьетнам",
}

# Аэропорты с регулярными рейсами, которых нет среди крупных в справочнике.
EXTRA_RUSSIA = {
    "AAQ", "ARH", "BQS", "BZK", "CEE", "CSY", "DYR", "EGO", "ESL", "EYK",
    "GDX", "GDZ", "HMA", "IGT", "IJK", "IWA", "KGP", "KHV", "KLF", "KMW",
    "KVK", "KVX", "KXK", "LPK", "MJZ", "NAL", "NBC", "NFG", "NOZ", "NUX",
    "NYA", "NYM", "OGZ", "OSW", "PES", "PEZ", "PKV", "PYJ", "REN", "RGK",
    "SCW", "SLY", "STW", "TBW", "TGP", "TGK", "TQL", "UCT", "ULY", "URJ",
    "URS", "USK", "VKT", "VOZ",
}

EXTRA_COUNTRY = {
    "BQT": "Belarus",
    "GME": "Belarus",
    "GNA": "Belarus",
    "MSQ": "Belarus",
}

ALIASES = {
    "абакан": "Russia",
    "адлер": "Russia",
    "актау": "Kazakhstan",
    "актобе": "Kazakhstan",
    "алматы": "Kazakhstan",
    "анадырь": "Russia",
    "анапа": "Russia",
    "апатиты": "Russia",
    "анкара": "Turkey",
    "анталия": "Turkey",
    "анталья": "Turkey",
    "архангельск": "Russia",
    "астана": "Kazakhstan",
    "астрахань": "Russia",
    "атырау": "Kazakhstan",
    "абу-даби": "United Arab Emirates",
    "баку": "Azerbaijan",
    "бали": "Indonesia",
    "бангкок": "Thailand",
    "барнаул": "Russia",
    "батуми": "Georgia",
    "белград": "Serbia",
    "бишкек": "Kyrgyzstan",
    "благовещенск": "Russia",
    "бодрум": "Turkey",
    "брянск": "Russia",
    "бухара": "Uzbekistan",
    "владивосток": "Russia",
    "владикавказ": "Russia",
    "волгоград": "Russia",
    "воронеж": "Russia",
    "газипаша": "Turkey",
    "геленджик": "Russia",
    "гомель": "Belarus",
    "гонконг": "Hong Kong",
    "грозный": "Russia",
    "гуанчжоу": "China",
    "гюмри": "Armenia",
    "гянджа": "Azerbaijan",
    "даламан": "Turkey",
    "дели": "India",
    "денпасар": "Indonesia",
    "джакарта": "Indonesia",
    "джидда": "Saudi Arabia",
    "доха": "Qatar",
    "дубай": "United Arab Emirates",
    "душанбе": "Tajikistan",
    "екатеринбург": "Russia",
    "ереван": "Armenia",
    "жуковский": "Russia",
    "измир": "Turkey",
    "ижевск": "Russia",
    "иркутск": "Russia",
    "казань": "Russia",
    "калининград": "Russia",
    "калуга": "Russia",
    "караганда": "Kazakhstan",
    "каир": "Egypt",
    "кемерово": "Russia",
    "киров": "Russia",
    "коломбо": "Sri Lanka",
    "комсомольск-на-амуре": "Russia",
    "краснодар": "Russia",
    "красноярск": "Russia",
    "куала-лумпур": "Malaysia",
    "кутаиси": "Georgia",
    "кыргызстан": "Kyrgyzstan",
    "ларнака": "Cyprus",
    "магадан": "Russia",
    "магнитогорск": "Russia",
    "мале": "Maldives",
    "марса-алам": "Egypt",
    "махачкала": "Russia",
    "минеральные воды": "Russia",
    "минск": "Belarus",
    "москва": "Russia",
    "мумбаи": "India",
    "мурманск": "Russia",
    "нальчик": "Russia",
    "наманган": "Uzbekistan",
    "нижневартовск": "Russia",
    "нижний новгород": "Russia",
    "новокузнецк": "Russia",
    "новосибирск": "Russia",
    "новый уренгой": "Russia",
    "норильск": "Russia",
    "нур-султан": "Kazakhstan",
    "омск": "Russia",
    "оренбург": "Russia",
    "осака": "Japan",
    "ош": "Kyrgyzstan",
    "пафос": "Cyprus",
    "пекин": "China",
    "пенза": "Russia",
    "пермь": "Russia",
    "петербург": "Russia",
    "петрозаводск": "Russia",
    "петропавловск-камчатский": "Russia",
    "подгорица": "Montenegro",
    "псков": "Russia",
    "пхукет": "Thailand",
    "самара": "Russia",
    "самарканд": "Uzbekistan",
    "санкт-петербург": "Russia",
    "саранск": "Russia",
    "саратов": "Russia",
    "сеул": "South Korea",
    "сингапур": "Singapore",
    "сочи": "Russia",
    "ставрополь": "Russia",
    "стамбул": "Turkey",
    "сургут": "Russia",
    "сыктывкар": "Russia",
    "ташкент": "Uzbekistan",
    "тбилиси": "Georgia",
    "тель-авив": "Israel",
    "тиват": "Montenegro",
    "токио": "Japan",
    "томск": "Russia",
    "трабзон": "Turkey",
    "тюмень": "Russia",
    "улан-удэ": "Russia",
    "улан-уде": "Russia",
    "ульяновск": "Russia",
    "урумчи": "China",
    "уфа": "Russia",
    "фергана": "Uzbekistan",
    "хабаровск": "Russia",
    "ханты-мансийск": "Russia",
    "харбин": "China",
    "ханой": "Vietnam",
    "хошимин": "Vietnam",
    "худжанд": "Tajikistan",
    "хургада": "Egypt",
    "чебоксары": "Russia",
    "челябинск": "Russia",
    "чита": "Russia",
    "шанхай": "China",
    "шарм-эль-шейх": "Egypt",
    "шарм-эш-шейх": "Egypt",
    "шарджа": "United Arab Emirates",
    "шымкент": "Kazakhstan",
    "элиста": "Russia",
    "эр-рияд": "Saudi Arabia",
    "южно-сахалинск": "Russia",
    "якутск": "Russia",
    "ярославль": "Russia",
}

_CODE_RE = re.compile(r"\(([A-Z]{3})\)")


def _norm(value: str) -> str:
    text = (value or "").replace("ё", "е").replace("Ё", "Е").lower()
    text = text.replace("—", "-").replace("–", "-")
    text = re.sub(r"\s+", " ", text)
    return text.strip(" .,-/")


def _label(english: str) -> str:
    return COUNTRY_RU.get(english, english)


def _index() -> tuple[dict[str, str], dict[str, str]]:
    by_code = {code: "Russia" for code in EXTRA_RUSSIA}
    by_code.update(EXTRA_COUNTRY)
    names: dict[str, str] = {}
    ambiguous: set[str] = set()
    for row in json.loads(DATA.read_text(encoding="utf-8")):
        by_code[row["code"]] = row["country"]
        key = _norm(row.get("city") or "")
        if not key:
            continue
        previous = names.get(key)
        if previous and previous != row["country"]:
            ambiguous.add(key)
        else:
            names[key] = row["country"]
    for key in ambiguous:
        names.pop(key, None)
    names.update(ALIASES)
    return by_code, names


BY_CODE, BY_NAME = _index()


def country_for(city_code: str = "", city: str = "") -> str:
    code = (city_code or "").strip().upper()
    if code in BY_CODE:
        return _label(BY_CODE[code])
    found = _CODE_RE.search((city or "").upper())
    if found and found.group(1) in BY_CODE:
        return _label(BY_CODE[found.group(1)])
    name = _norm(city)
    if name in BY_NAME:
        return _label(BY_NAME[name])
    head = _norm(re.split(r"[,/]| - ", name, maxsplit=1)[0])
    if head in BY_NAME:
        return _label(BY_NAME[head])
    return ""
