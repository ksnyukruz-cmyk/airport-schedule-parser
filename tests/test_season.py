import unittest
from datetime import date

from app.season import (
    aggregate,
    parse_fr24_departures,
    parse_kzn_html,
    parse_svo_items,
    parse_svx_html,
    patterns_from_board,
)


SVX_HTML = """
<table>
  <tr><td class="table-wrap__city-row" colspan="8">Абакан</td></tr>
  <tr>
    <td>02:00</td><td>06:55</td><td>пн</td>
    <td>26&nbsp;окт&nbsp;/ 23&nbsp;ноя</td>
    <td><div title="RED WINGS"></div><div class="table-aircompany-logo-alt">RED WINGS</div></td>
    <td>WZ-5015</td><td>RRJ-95B</td><td>ABA</td>
  </tr>
  <tr>
    <td>18:00</td><td>19:00</td><td>вс</td>
    <td>26 окт / 28 мар</td>
    <td><div title="Аэрофлот"></div></td>
    <td>SU-100</td><td>A320</td><td>SVO</td>
  </tr>
</table>
"""

KZN_HTML = """
<div class="flights-table__item">
  <div class="table_days">Дш</div>
  <div class="item-number__name" title="Победа"><span class="item-number__name-text">DP 338</span></div>
  <div class="table_dates"><div>25.10.2026</div><div>06.11.2026</div></div>
</div>
<div class="flights-table__item">
  <div class="table_days">01.11.2026</div>
  <div class="item-number__name" title="Северный Ветер"><span class="item-number__name-text">N4 412</span></div>
  <div class="table_dates"></div>
</div>
"""


class SeasonParseTests(unittest.TestCase):
    def test_svx_counts_mondays_and_crosses_new_year(self):
        patterns = parse_svx_html(SVX_HTML, date(2026, 10, 30))
        self.assertEqual(len(patterns), 2)
        abakan = patterns[0]
        self.assertEqual(abakan["city"], "Абакан")
        self.assertEqual(abakan["city_code"], "ABA")
        self.assertEqual(abakan["airline"], "RED WINGS")
        self.assertEqual(abakan["airline_code"], "WZ")
        folded = aggregate([abakan])
        self.assertEqual(folded["rows"][0]["flights"], 5)
        self.assertEqual(folded["rows"][0]["months"]["2026-10"], 1)
        self.assertEqual(folded["rows"][0]["months"]["2026-11"], 4)
        self.assertEqual(folded["rows"][0]["years"]["2026"], 5)

        winter = aggregate([patterns[1]])
        self.assertGreater(winter["rows"][0]["months"].get("2027-03", 0), 0)
        self.assertGreater(winter["rows"][0]["months"].get("2026-11", 0), 0)
        self.assertGreater(winter["rows"][0]["years"].get("2026", 0), 0)
        self.assertGreater(winter["rows"][0]["years"].get("2027", 0), 0)

    def test_svo_uses_final_city_and_single_day(self):
        patterns = parse_svo_items(
            [
                {
                    "i_id": "1",
                    "ad": "D",
                    "flt": "1008",
                    "co": {"code": "SU", "name": "Аэрофлот"},
                    "mar1_name": "Шереметьево",
                    "mar2_name": "Калининград",
                    "mar3_name": None,
                    "days": {"mo": True, "tu": True, "we": True, "th": True, "fr": True, "sa": True, "su": True},
                    "date_b": "2026-10-26T00:00:00+03:00",
                    "date_e": "2026-11-01T00:00:00+03:00",
                },
                {
                    "i_id": "2",
                    "ad": "A",
                    "flt": "1009",
                    "co": {"code": "SU", "name": "Аэрофлот"},
                    "mar2_name": "Калининград",
                    "days": {"su": True},
                    "date_b": "2026-10-25T00:00:00+03:00",
                    "date_e": "2026-10-25T00:00:00+03:00",
                },
                {
                    "i_id": "1",
                    "ad": "D",
                    "flt": "1008",
                    "co": {"code": "SU", "name": "Аэрофлот"},
                    "mar2_name": "Калининград",
                    "days": {"mo": True},
                    "date_b": "2026-10-26T00:00:00+03:00",
                    "date_e": "2026-11-01T00:00:00+03:00",
                },
            ]
        )
        self.assertEqual(len(patterns), 1)
        folded = aggregate(patterns)
        self.assertEqual(folded["rows"][0]["city"], "Калининград")
        self.assertEqual(folded["rows"][0]["flights"], 7)
        self.assertEqual(folded["rows"][0]["months"]["2026-10"], 6)
        self.assertEqual(folded["rows"][0]["months"]["2026-11"], 1)

    def test_kzn_tatar_weekday_and_one_off(self):
        patterns = parse_kzn_html(KZN_HTML, "Сочи")
        self.assertEqual(len(patterns), 2)
        folded = aggregate(patterns)
        pobeda = next(row for row in folded["rows"] if row["airline_code"] == "DP")
        nord = next(row for row in folded["rows"] if row["airline_code"] == "N4")
        self.assertEqual(pobeda["city"], "Сочи")
        self.assertEqual(pobeda["flights"], 2)
        self.assertEqual(nord["flights"], 1)
        self.assertEqual(nord["months"], {"2026-11": 1})

    def test_board_skips_cancelled(self):
        patterns = patterns_from_board(
            "LED",
            [
                {
                    "flight": "SU 1",
                    "airline": "Аэрофлот",
                    "airline_code": "SU",
                    "city": "Сочи",
                    "city_code": "AER",
                    "scheduled": "2026-10-30T10:00+03:00",
                    "status": "По расписанию",
                },
                {
                    "flight": "SU 2",
                    "airline": "Аэрофлот",
                    "airline_code": "SU",
                    "city": "Сочи",
                    "city_code": "AER",
                    "scheduled": "2026-10-30T12:00+03:00",
                    "status": "Отменён",
                },
            ],
        )
        folded = aggregate(patterns)
        self.assertEqual(folded["rows"][0]["flights"], 1)

    def test_fr24_departure_becomes_one_day(self):
        moment = 1793329200
        patterns = parse_fr24_departures(
            {
                "result": {
                    "response": {
                        "airport": {
                            "pluginData": {
                                "schedule": {
                                    "departures": {
                                        "data": [
                                            {
                                                "flight": {
                                                    "identification": {"number": {"default": "IO1825"}},
                                                    "status": {"generic": {"status": {"text": "scheduled"}}},
                                                    "airline": {"name": "IrAero", "code": {"iata": "IO"}},
                                                    "airport": {
                                                        "destination": {
                                                            "code": {"iata": "AYT"},
                                                            "position": {"region": {"city": "Antalya"}},
                                                        }
                                                    },
                                                    "time": {"scheduled": {"departure": moment}},
                                                }
                                            },
                                            {
                                                "flight": {
                                                    "identification": {"number": {"default": "XX1"}},
                                                    "status": {"generic": {"status": {"text": "canceled"}}},
                                                    "airline": {"name": "Test", "code": {"iata": "XX"}},
                                                    "airport": {"destination": {"code": {"iata": "LED"}, "position": {"region": {"city": "Saint Petersburg"}}}},
                                                    "time": {"scheduled": {"departure": moment}},
                                                }
                                            },
                                        ]
                                    }
                                }
                            }
                        }
                    }
                }
            },
            "AER",
        )
        folded = aggregate(patterns)
        self.assertEqual(len(folded["rows"]), 1)
        self.assertEqual(folded["rows"][0]["airport"], "AER")
        self.assertEqual(folded["rows"][0]["airline_code"], "IO")
        self.assertEqual(folded["rows"][0]["city_code"], "AYT")
        self.assertEqual(folded["rows"][0]["flights"], 1)


if __name__ == "__main__":
    unittest.main()
