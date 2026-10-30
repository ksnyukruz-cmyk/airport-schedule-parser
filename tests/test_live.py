import unittest

from app.service import list_airports
from app.sources.live import _aircraft_list, select_flight


LHR = {"code": "LHR", "icao": "EGLL", "lat": 51.47, "lon": -0.46}


class LiveBoardTests(unittest.TestCase):
    def test_catalog_keeps_hubs_and_drops_europe(self):
        airports = list_airports()
        codes = [item["code"] for item in airports]
        unique = set(codes)
        self.assertEqual(codes[:4], ["LED", "DME", "SVO", "VKO"])
        self.assertIn("IST", unique)
        self.assertIn("DXB", unique)
        self.assertIn("JFK", unique)
        self.assertIn("HND", unique)
        for europe in ("LHR", "CDG", "FRA", "AMS", "MAD", "BCN", "FCO"):
            self.assertNotIn(europe, unique)
        self.assertEqual(len(airports), 76)
        svo = next(item for item in airports if item["code"] == "SVO")
        vko = next(item for item in airports if item["code"] == "VKO")
        ist = next(item for item in airports if item["code"] == "IST")
        self.assertEqual(svo["kind"], "official")
        self.assertTrue(svo["supports_date"])
        self.assertEqual(vko["kind"], "official")
        self.assertTrue(vko["supports_date"])
        self.assertEqual(ist["kind"], "live")
        self.assertEqual(ist["group"], "Турция")
        self.assertFalse(ist["supports_date"])

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

    def test_reads_both_feed_shapes(self):
        self.assertEqual(len(_aircraft_list({"ac": [{"flight": "A"}]})), 1)
        self.assertEqual(len(_aircraft_list({"aircraft": [{"flight": "A"}, {"flight": "B"}]})), 2)
        self.assertIsNone(_aircraft_list({"msg": "no"}))

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
