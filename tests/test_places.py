import unittest

from app.places import country_for


class PlaceTests(unittest.TestCase):
    def test_country_by_code(self):
        self.assertEqual(country_for("LED", "Санкт-Петербург"), "Россия")
        self.assertEqual(country_for("IST", "Istanbul"), "Турция")
        self.assertEqual(country_for("DXB", ""), "ОАЭ")
        self.assertEqual(country_for("KHV", "Хабаровск"), "Россия")
        self.assertEqual(country_for("GME", "Гомель"), "Беларусь")

    def test_country_by_russian_city(self):
        self.assertEqual(country_for("", "ОМСК"), "Россия")
        self.assertEqual(country_for("", "Стамбул"), "Турция")
        self.assertEqual(country_for("", "Дубай"), "ОАЭ")

    def test_unknown_city_stays_blank(self):
        self.assertEqual(country_for("", "несуществующий город"), "")


if __name__ == "__main__":
    unittest.main()
