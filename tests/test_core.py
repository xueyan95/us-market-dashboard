import json
import unittest
from pathlib import Path

from fetch_data import completed_trading_dates, option_greeks
from should_notify import classify_slot


class CoreTests(unittest.TestCase):
    def test_duplicate_placeholder_session_is_removed(self):
        rows = {f"us{i}": {"2026-01-02": 10.0, "2026-01-05": 11.0, "2026-01-06": 11.0}
                for i in range(12)}
        self.assertEqual(completed_trading_dates(rows)[-1], "2026-01-05")

    def test_slot_routing(self):
        self.assertEqual(classify_slot(0, 0, True), "postmarket")
        self.assertEqual(classify_slot(13, 0, True), "premarket")
        self.assertEqual(classify_slot(14, 30, False), "premarket")

    def test_option_delta_is_bounded(self):
        result = option_greeks(100, 100, 365, .30, "call")
        self.assertTrue(0 < result["delta_est"] < 1)

    def test_config_is_valid(self):
        config = json.loads((Path(__file__).parents[1] / "portfolio_config.json").read_text())
        self.assertTrue(config["holdings"])


if __name__ == "__main__":
    unittest.main()
