import unittest

from app.service import list_airports
from app.sources.live import select_flight


LHR = {"code": "LHR", "icao": "EGLL", "lat": 51.47, "lon": -0.46}


class LiveBoardTests(unittest.TestCase):
    def test_catalog_covers_major_airports(self):
        airports = list_airports()
        codes = {item["code"] for item in airports}
        self.assertGreater(len(airports), 400)
        self.assertIn("SVO", codes)
        self.assertIn("LHR", codes)
        self.assertIn("JFK", codes)
        self.assertIn("HND", codes)
        svo = next(item for item in airports if item["code"] == "SVO")
        heathrow = next(item for item in airports if item["code"] == "LHR")
        self.assertEqual(svo["kind"], "official")
        self.assertTrue(svo["supports_date"])
        self.assertEqual(heathrow["kind"], "live")
        self.assertFalse(heathrow["supports_date"])

    def test_route_marks_heathrow_arrival(self):
        flight = select_flight(
            {"flight": "BAW6R", "alt_baro": 10000, "baro_rate": -256, "dst": 17.8, "t": "A320"},
            {
                "airline_code": "BAW",
                "number": "6R",
                "_airports": [
                    {"iata": "MIA", "icao": "KMIA", "location": "Miami"},
                    {"iata": "LHR", "icao": "EGLL", "location": "London"},
                ],
            },
            LHR,
        )
        self.assertEqual(flight["direction"], "arrival")
        self.assertEqual(flight["city"], "Miami")
        self.assertEqual(flight["flight"], "BA 6R")
        self.assertEqual(flight["airline"], "British Airways")
        self.assertEqual(flight["status"], "Снижается")

    def test_known_route_elsewhere_is_ignored(self):
        flight = select_flight(
            {"flight": "AFL100", "alt_baro": 35000, "baro_rate": 0, "dst": 20, "t": "B77W"},
            {
                "airline_code": "AFL",
                "number": "100",
                "_airports": [
                    {"iata": "SVO", "icao": "UUEE", "location": "Moscow"},
                    {"iata": "JFK", "icao": "KJFK", "location": "New York"},
                ],
            },
            LHR,
        )
        self.assertIsNone(flight)

    def test_nearby_descent_without_route_is_arrival(self):
        flight = select_flight(
            {"flight": "DLH400", "alt_baro": 4000, "baro_rate": -800, "dst": 8, "t": "A320"},
            None,
            LHR,
        )
        self.assertEqual(flight["direction"], "arrival")
        self.assertEqual(flight["status"], "Снижается")


if __name__ == "__main__":
    unittest.main()
