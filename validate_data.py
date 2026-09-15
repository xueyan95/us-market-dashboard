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
    # A temporary public-market data gap is displayed as degraded data health;
    # it must not prevent the dashboard and its broker snapshot from deploying.
    snapshot = market.get("private_portfolio_snapshot", {})
    # Broker total is the authoritative latest-assets display.  A missing
    # third-party quote for a watchlist/leveraged ETF must not block deployment
    # when that fresh broker total is available; individual rows remain marked
    # unavailable instead of being estimated.
    broker_total = snapshot.get("account", {}).get("broker_total_value")
    if (snapshot.get("available") and not snapshot.get("valuation", {}).get("equity_complete")
            and broker_total in (None, 0, "", 0.0)):
        errors.append("equity valuation incomplete without broker total")
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
