#!/usr/bin/env python3
"""Fail closed when critical dashboard inputs are incomplete."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main():
    market = json.loads((HERE / "market_data.json").read_text(encoding="utf-8"))
    health = market.get("data_health", {})
    errors = []
    if not market.get("d_latest") or not market.get("d_prev"):
        errors.append("missing completed-session dates")
    if health.get("missing_change"):
        errors.append("missing % change: " + ", ".join(health["missing_change"]))
    snapshot = market.get("private_portfolio_snapshot", {})
    if snapshot.get("available") and not snapshot.get("valuation", {}).get("equity_complete"):
        errors.append("equity valuation incomplete")
    curve = market.get("rate_context", {}).get("curve_5s10s_bp")
    if curve is not None and abs(float(curve)) > 1000:
        errors.append("implausible 5s10s curve")
    if market.get("session_context", {}).get("report_slot") == "premarket":
        for symbol, item in market.get("premarket", {}).get("quotes", {}).items():
            price, close, change = item.get("price"), item.get("previous_close"), item.get("change_pct")
            if price is None or close in (None, 0) or change is None:
                errors.append(f"incomplete premarket quote: {symbol}")
                continue
            expected = (float(price) / float(close) - 1) * 100
            if abs(expected - float(change)) > 0.02:
                errors.append(f"invalid premarket change: {symbol}")
    if errors:
        raise SystemExit("Data validation failed: " + "; ".join(errors))
    print(f"Data validation passed: {health.get('quote_count')} quotes, session {market['d_latest']}")


if __name__ == "__main__":
    main()
