import json
import unittest
from pathlib import Path

from fetch_data import build_news_delta, completed_trading_dates, compute_premarket_change, option_greeks
from portfolio import inherit_leveraged_layer_categories, leveraged_etfs, load_portfolio_config
from should_notify import classify_slot


class CoreTests(unittest.TestCase):
    def test_duplicate_placeholder_session_is_removed(self):
        rows = {f"us{i}": {"2026-01-02": 10.0, "2026-01-05": 11.0, "2026-01-06": 11.0}
                for i in range(12)}
        self.assertEqual(completed_trading_dates(rows)[-1], "2026-01-05")

    def test_slot_routing(self):
        self.assertEqual(classify_slot(0, 0, True), "postmarket")
        self.assertEqual(classify_slot(13, 0, True), "premarket")
        self.assertEqual(classify_slot(14, 0, False), "premarket")
        self.assertEqual(classify_slot(14, 30, False), "skip")

    def test_premarket_change_uses_previous_regular_close(self):
        self.assertEqual(compute_premarket_change(105, 100), 5.0)
        self.assertIsNone(compute_premarket_change(None, 100))

    def test_news_delta_starts_at_4pm_eastern(self):
        import datetime
        from zoneinfo import ZoneInfo
        et = ZoneInfo("America/New_York")
        before = datetime.datetime(2026, 9, 3, 15, 59, tzinfo=et).timestamp()
        after = datetime.datetime(2026, 9, 3, 16, 1, tzinfo=et).timestamp()
        end = datetime.datetime(2026, 9, 4, 9, 0, tzinfo=et)
        data = {"items": [{"title": "old", "published_ts": before},
                          {"title": "new", "published_ts": after},
                          {"title": "unknown", "published_ts": 0}]}
        delta = build_news_delta(data, "2026-09-03", end)
        self.assertEqual([x["title"] for x in delta["items"]], ["new"])

    def test_option_delta_is_bounded(self):
        result = option_greeks(100, 100, 365, .30, "call")
        self.assertTrue(0 < result["delta_est"] < 1)

    def test_config_is_valid(self):
        config = load_portfolio_config(Path(__file__).parents[1] / "portfolio_config.json")
        self.assertTrue(config["holdings"])

    def test_leveraged_etfs_inherit_underlying_category(self):
        config = load_portfolio_config(Path(__file__).parents[1] / "portfolio_config.json")
        layers = [("③ 基础设施", "", [("光模块/网络设备", ["usCOHR"])])]
        result = inherit_leveraged_layer_categories(layers, config, ["usCOHX"])
        self.assertEqual(result[0][2][0][1], ["usCOHR", "usCOHX"])
        self.assertEqual(leveraged_etfs(config)["COHX"]["underlying"], "COHR")
        self.assertEqual(leveraged_etfs(config)["AEHG"]["underlying"], "AEHR")


if __name__ == "__main__":
    unittest.main()
