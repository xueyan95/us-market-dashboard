import json
import datetime
import unittest
from pathlib import Path

from fetch_data import (build_news_delta, completed_trading_dates, compute_premarket_change,
                        enrich_portfolio_snapshot, option_greeks)
from portfolio import inherit_leveraged_layer_categories, leveraged_etfs, load_portfolio_config
from should_notify import classify_slot
from ai_analysis import build_prompt, display_chinese_strings, validate_grounding
from research_inputs import parse_issue_body, public_entries


class CoreTests(unittest.TestCase):
    def test_duplicate_placeholder_session_is_removed(self):
        rows = {f"us{i}": {"2026-01-02": 10.0, "2026-01-05": 11.0, "2026-01-06": 11.0}
                for i in range(12)}
        self.assertEqual(completed_trading_dates(rows)[-1], "2026-01-05")

    def test_slot_routing(self):
        self.assertEqual(classify_slot(23, 45, True), "postmarket")
        self.assertEqual(classify_slot(12, 45, True), "premarket")
        self.assertEqual(classify_slot(13, 45, False), "premarket")
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

    def test_portfolio_keeps_last_close_separate_from_latest_price(self):
        snapshot = {"available": True, "account": {"cash": 50},
                    "equities": [{"symbol": "TEST", "quantity": 1, "average_cost": 90}],
                    "options": []}
        enriched = enrich_portfolio_snapshot(
            snapshot, {"usTEST": {"last": 105}}, {"usTEST": {"last": 100}})
        self.assertEqual(enriched["valuation"]["total_value"], 155)
        self.assertEqual(enriched["last_close_valuation"]["total_value"], 150)

    def test_company_event_requires_matching_news_evidence(self):
        title = "Apple announces product event for today"
        news = [{"title": title, "source": "Example", "link": "https://example.com/apple"}]
        analysis = {"news_cards": [], "news_themes": [], "upcoming_events": [
            {"date": datetime.date.today().isoformat(), "time": "10:00 PT", "symbol": "AAPL",
             "event": "Apple product event", "evidence_title": title,
             "source": "Example", "evidence_url": "https://example.com/apple"},
            {"date": datetime.date.today().isoformat(), "time": "TBD", "symbol": "FAKE",
             "event": "Invented event", "evidence_title": "Missing",
             "source": "Example", "evidence_url": "https://example.com/missing"},
        ]}
        grounded = validate_grounding(analysis, news)
        self.assertEqual([x["symbol"] for x in grounded["upcoming_events"]], ["AAPL"])

    def test_research_json_defaults_private_and_parses_symbols(self):
        body = '''```research-entry
{"type":"thesis","title":"AI capex","statement":"Demand persists","symbols":"$NVDA, AMD","probability":65}
```'''
        entry = parse_issue_body(body, 7, "https://example.com/7")
        self.assertEqual(entry["id"], "R-7")
        self.assertEqual(entry["symbols"], ["NVDA", "AMD"])
        self.assertEqual(entry["visibility"], "private")

    def test_only_explicit_public_research_is_exported(self):
        issues = [
            {"number": 1, "body": "### 标题\nPrivate\n\n### 核心内容\nHidden", "updated_at": "2026-01-01"},
            {"number": 2, "body": "### 标题\nPublic\n\n### 核心内容\nShown\n\n### 公开状态\n公开", "updated_at": "2026-01-02"},
        ]
        self.assertEqual([x["title"] for x in public_entries(issues)], ["Public"])

    def test_research_update_requires_exact_news_and_record(self):
        news = [{"title": "NVDA launches a new chip", "source": "Wire",
                 "link": "https://example.com/nvda"}]
        analysis = {"news_cards": [], "news_themes": [], "upcoming_events": [],
                    "research_updates": [
                        {"record_id": "R-2", "relation": "support", "explanation": "New product",
                         "suggested_probability": 70, "evidence_title": news[0]["title"],
                         "source": "Wire", "evidence_url": news[0]["link"]},
                        {"record_id": "R-99", "relation": "support", "explanation": "Invented",
                         "suggested_probability": 90, "evidence_title": news[0]["title"],
                         "source": "Wire", "evidence_url": news[0]["link"]},
                    ]}
        grounded = validate_grounding(analysis, news, research={"entries": [{"id": "R-2"}]})
        self.assertEqual([x["record_id"] for x in grounded["research_updates"]], ["R-2"])

    def test_english_translation_mirror_rejects_chinese_output(self):
        analysis = {"news_cards": [], "news_themes": [], "upcoming_events": [],
                    "research_updates": [], "english_translations": [
                        {"zh": "市场上涨", "en": "The market rose"},
                        {"zh": "风险上升", "en": "Risk 上升"},
                    ]}
        grounded = validate_grounding(analysis, [])
        self.assertEqual(grounded["english_translations"], [
            {"zh": "市场上涨", "en": "The market rose"}
        ])

    def test_bilingual_analysis_prompt_build_is_valid(self):
        prompt = build_prompt({}, [], "test", {"entries": []})
        self.assertIn('"conclusion"', prompt)

    def test_translation_mirror_collects_unique_display_strings(self):
        strings = display_chinese_strings(
            {"conclusion": "市场上涨", "news": [{"detail": "市场上涨"}, {"detail": "风险增加"}]},
            {"entries": [{"title": "我的判断"}]})
        self.assertEqual(strings, ["市场上涨", "风险增加", "我的判断"])

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
