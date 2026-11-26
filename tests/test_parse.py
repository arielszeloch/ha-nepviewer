"""Tests for the pure parsing helpers (no Home Assistant needed).

Run: python -m unittest discover -s tests
"""

import importlib.util
from pathlib import Path
import sys
import unittest

_PATH = Path(__file__).resolve().parents[1] / "custom_components" / "nepviewer" / "parse.py"
_spec = importlib.util.spec_from_file_location("nep_parse", _PATH)
parse = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = parse  # needed by @dataclass
_spec.loader.exec_module(parse)

# Shape of a real v2/site/overview response (values from a small plant).
OVERVIEW = {
    "statisticsProduction": {
        "today": "0.128", "todayUnit": "kWh",
        "yesterday": "200", "yesterdayUnit": "",
        "month": "96.4", "monthUnit": "kWh",
        "year": "668.3", "yearUnit": "kWh",
        "total": "1285.3", "totalUnit": "kWh",
        "totalNow": "0", "totalNowUnit": "W",
    },
    "benefit": {
        "co2": "1293.8", "co2Unit": "kg",
        "tree": "58.81", "treeUnit": "Trees",
        "car": "4461.38", "carUnit": "km",
        "oil": "3.01", "oilUnit": "BBL",
    },
}


class NumberTests(unittest.TestCase):
    def test_num(self):
        self.assertEqual(parse.num("1.5"), 1.5)
        self.assertIsNone(parse.num(None))
        self.assertIsNone(parse.num("abc"))
        self.assertIsNone(parse.num("nan"))

    def test_to_kwh(self):
        self.assertEqual(parse.to_kwh("1.5", "MWh"), 1500)
        self.assertEqual(parse.to_kwh(2, "GWh"), 2_000_000)
        self.assertEqual(parse.to_kwh("500", "Wh"), 0.5)
        self.assertEqual(parse.to_kwh("3", None), 3)
        self.assertIsNone(parse.to_kwh("", "kWh"))

    def test_to_w(self):
        self.assertEqual(parse.to_w("1.2", "kW"), 1200)
        self.assertEqual(parse.to_w(300, "W"), 300)
        self.assertIsNone(parse.to_w(None, "W"))


class OverviewTests(unittest.TestCase):
    def test_parse_overview(self):
        ov = parse.parse_overview(OVERVIEW)
        self.assertAlmostEqual(ov.energy_yesterday, 0.2)  # Wh with empty unit
        self.assertEqual(ov.energy_month, 96.4)
        self.assertEqual(ov.energy_year, 668.3)
        self.assertEqual(ov.co2_kg, 1293.8)
        self.assertEqual(ov.trees, 58.81)
        self.assertEqual(ov.car_km, 4461.38)
        self.assertEqual(ov.oil_bbl, 3.01)

    def test_units_scaled(self):
        data = {
            "statisticsProduction": {"month": "1.2", "monthUnit": "MWh", "yesterday": "5", "yesterdayUnit": "kWh"},
            "benefit": {"co2": "2.5", "co2Unit": "t", "car": "4.46", "carUnit": "km(*1000)"},
        }
        ov = parse.parse_overview(data)
        self.assertEqual(ov.energy_month, 1200)
        self.assertEqual(ov.energy_yesterday, 5)
        self.assertEqual(ov.co2_kg, 2500)
        self.assertAlmostEqual(ov.car_km, 4460)
        self.assertIsNone(ov.trees)

    def test_invalid(self):
        self.assertIsNone(parse.parse_overview(None))
        self.assertIsNone(parse.parse_overview({}))
        self.assertIsNone(parse.parse_overview({"statisticsProduction": "x"}))
        ov = parse.parse_overview({"statisticsProduction": {}})
        self.assertIsNone(ov.energy_month)
        self.assertIsNone(ov.co2_kg)


class DailyEnergyCounterTest(unittest.TestCase):
    def test_counts_daily_increments_across_days(self):
        c = parse.DailyEnergyCounter()
        for day, today in [("2026-11-25", 0.004), ("2026-11-25", 0.9), ("2026-11-25", 1.8),
                           ("2026-11-26", 0.004), ("2026-11-26", 0.5)]:
            c.update(day, today)
        self.assertAlmostEqual(c.total, 2.3)

    def test_stale_value_after_midnight_not_counted_twice(self):
        # Before the first report of a new day the cloud still shows
        # yesterday's daily value with yesterday's report time.
        c = parse.DailyEnergyCounter()
        c.update("2026-11-25", 1.8)
        c.update("2026-11-25", 1.8)
        c.update("2026-11-25", 0)  # glitch / reset to 0 before the new day
        c.update("2026-11-25", 1.8)
        self.assertAlmostEqual(c.total, 1.8)

    def test_ignores_missing_and_older_days(self):
        c = parse.DailyEnergyCounter()
        self.assertFalse(c.update(None, 1.0))
        self.assertFalse(c.update("2026-11-25", None))
        c.update("2026-11-26", 0.5)
        self.assertFalse(c.update("2026-11-25", 3.0))
        self.assertAlmostEqual(c.total, 0.5)

    def test_round_trip_and_invalid_restore(self):
        c = parse.DailyEnergyCounter()
        c.update("2026-11-26", 0.7)
        r = parse.DailyEnergyCounter.from_dict(c.as_dict())
        self.assertEqual(r, c)
        r.update("2026-11-26", 1.0)
        self.assertAlmostEqual(r.total, 1.0)
        self.assertIsNone(parse.DailyEnergyCounter.from_dict(None))
        # 0.2.0 restore data has no counter state
        self.assertIsNone(parse.DailyEnergyCounter.from_dict({"native_value": 1912.7}))


if __name__ == "__main__":
    unittest.main()
