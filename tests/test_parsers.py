import unittest
from datetime import date

from app.sources.dme import parse_html
from app.sources.pulkovo import parse_rows
from app.sources.svo import parse_items
from app.sources.vko import decode_board, parse_rows as parse_vko


class SvoTests(unittest.TestCase):
    def test_departure_uses_final_city_and_codeshare(self):
        flights = parse_items(
            [
                {
                    "i_id": "1",
                    "flt": "1524",
                    "co": {"code": "SU", "name": "Аэрофлот"},
                    "t_st": "2026-10-30T00:05:00+03:00",
                    "t_et": "2026-10-30T06:05:00+03:00",
                    "t_at": None,
                    "term": "B",
                    "gate_id": "113",
                    "vip_status_rus": "Отменен",
                    "aircraft_type_name": "Airbus A321",
                    "main_flight": "FV 6524",
                    "mar1": {"iata": "SVO", "city": "Москва"},
                    "mar2": {"iata": "LED", "city": "Санкт-Петербург"},
                    "mar3": {"iata": "RGK", "city": "Горно-Алтайск"},
                }
            ],
            "departure",
        )
        self.assertEqual(len(flights), 1)
        flight = flights[0]
        self.assertEqual(flight["flight"], "SU 1524")
        self.assertEqual(flight["city"], "Горно-Алтайск")
        self.assertEqual(flight["city_code"], "RGK")
        self.assertEqual(flight["gate"], "113")
        self.assertEqual(flight["status"], "Отменен")
        self.assertEqual(flight["codeshare"], ["FV 6524"])
        self.assertTrue(flight["estimated"].startswith("2026-10-30T06:05"))

    def test_arrival_uses_previous_airport(self):
        flights = parse_items(
            [
                {
                    "i_id": "2",
                    "flt": "5807",
                    "co": {"code": "SU", "name": "Аэрофлот"},
                    "t_st": "2026-10-30T12:00:00+03:00",
                    "t_et": "2026-10-30T12:00:00+03:00",
                    "bbel_id": "2",
                    "term": "B",
                    "vip_status_rus": "Ожидается в 12:00",
                    "mar1": {"iata": "KHV", "city": "Хабаровск"},
                    "mar2": {"iata": "SVO", "city": "Москва"},
                }
            ],
            "arrival",
        )
        flight = flights[0]
        self.assertEqual(flight["city_code"], "KHV")
        self.assertEqual(flight["belt"], "2")
        self.assertEqual(flight["gate"], "")
        self.assertIsNone(flight["estimated"])


class PulkovoTests(unittest.TestCase):
    def test_normalizes_number_status_and_date(self):
        rows = [
            {
                "OD_FLIGHT_NUMBER": "5N  545",
                "OD_RAL_CODE": "5N",
                "OD_RAL_NAME_RUS": "Smartavia",
                "OD_RAP_DESTINATION_NAME_RU": "Сочи",
                "OD_RAP_CODE_DESTINATION": "AER",
                "OD_STD": "2026-10-30T08:45:00.000",
                "OD_ETD": "2026-10-30T09:10:00.000",
                "OD_RTRM_CODE": "1",
                "OD_GATES": "12",
                "OD_RFS_CODE": "DLY",
                "OD_STATUS_RU": {},
                "OD_RACT_ICAO_CODE": "B738",
            },
            {
                "OD_FLIGHT_NUMBER": "SU 10",
                "OD_STD": "2026-10-31T01:00:00.000",
                "OD_RFS_CODE": "SKD",
                "OD_STATUS_RU": "",
            },
        ]
        flights = parse_rows(rows, "departure", date(2026, 10, 30))
        self.assertEqual(len(flights), 1)
        flight = flights[0]
        self.assertEqual(flight["flight"], "5N 545")
        self.assertEqual(flight["city"], "Сочи")
        self.assertEqual(flight["status"], "Задержан")
        self.assertEqual(flight["gate"], "12")
        self.assertEqual(flight["aircraft"], "B738")


class DmeTests(unittest.TestCase):
    def test_parses_live_board_row(self):
        html = """
        <div>Показываются рейсы : прилетающие с 30-10 6:00 до 30-10 13:00</div>
        <table>
          <tr class="vat">
            <td class="timeflight">07:00</td>
            <td>30 окт&nbsp;07:00</td>
            <td id="time1" class="flightlate"></td>
            <td>
              <a class="dialogopen" href="#">
                <img alt="S7" title="S7">
                S7 2566
              </a>
            </td>
            <td id="course1"><div>ОМСК</div></td>
            <td class="flightlate">
              <ul class="ticker"><li>Ожидается выдача багажа на ленте 2</li></ul>
            </td>
            <td>D</td>
          </tr>
        </table>
        """
        parsed = parse_html(html, "arrival", 2026)
        self.assertIn("6:00", parsed["window"])
        self.assertEqual(len(parsed["flights"]), 1)
        flight = parsed["flights"][0]
        self.assertEqual(flight["flight"], "S7 2566")
        self.assertEqual(flight["city"], "ОМСК")
        self.assertEqual(flight["terminal"], "D")
        self.assertEqual(flight["status"], "Ожидается выдача багажа на ленте 2")
        self.assertEqual(flight["belt"], "2")
        self.assertTrue(flight["scheduled"].startswith("2026-10-30T07:00"))


class VkoTests(unittest.TestCase):
    def test_decode_roundtrip(self):
        import base64

        secret = "d87ea039-6704-4aec-84c3-c7b40b997f08".encode("ascii")
        raw = '{"results":{"flights":[]}}'.encode("utf-8")
        masked = bytes(byte ^ secret[index % len(secret)] for index, byte in enumerate(raw))
        opened = decode_board(base64.b64encode(masked).decode("ascii"))
        self.assertEqual(opened["results"]["flights"], [])

    def test_parses_departure(self):
        flights = parse_vko(
            [
                {
                    "flt_id": 1,
                    "flt_number": "ДР 1403",
                    "fls_iata": "SVX",
                    "fls_city_name": "Екатеринбург",
                    "st": "2026-10-30 00:20:00",
                    "et": "2026-10-30 12:45:00",
                    "at": None,
                    "terminal": "А",
                    "gates": ["15A"],
                    "belt": None,
                    "delayed": True,
                    "cancelled": False,
                    "status": "Идёт регистрация",
                    "airline_name": "Победа",
                    "aircraft": {"icao": "B738", "name": "Boeing 737-800"},
                    "codeshare": [{"flt_number": "SU 1403"}],
                }
            ],
            date(2026, 10, 30),
        )
        self.assertEqual(len(flights), 1)
        flight = flights[0]
        self.assertEqual(flight["flight"], "ДР 1403")
        self.assertEqual(flight["city"], "Екатеринбург")
        self.assertEqual(flight["city_code"], "SVX")
        self.assertEqual(flight["gate"], "15A")
        self.assertEqual(flight["terminal"], "А")
        self.assertEqual(flight["airline"], "Победа")
        self.assertEqual(flight["aircraft"], "Boeing 737-800")
        self.assertEqual(flight["codeshare"], ["SU 1403"])
        self.assertTrue(flight["scheduled"].startswith("2026-10-30T00:20"))
        self.assertTrue(flight["estimated"].startswith("2026-10-30T12:45"))


if __name__ == "__main__":
    unittest.main()
