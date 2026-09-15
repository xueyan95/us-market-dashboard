#!/usr/bin/env python3
"""Build transparent, free ETF forward-P/E observations.

SPY is read from State Street's published ``Price/Earnings Ratio FY1``.
SOXX is calculated from iShares' public daily holdings file and BusinessQuant's
FY1 consensus EPS estimates.  A SOXX point is deliberately withheld unless
the estimates cover at least 90% of its portfolio weight.

No key or individual EPS estimate is ever written to the repository.  The
only persisted output is public ETF-level valuation, price and coverage data.
"""
import csv
import datetime as dt
import io
import json
import math
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
SPY_URL = "https://www.ssga.com/us/en/individual/etfs/state-street-spdr-sp-500-etf-trust-spy"
SOXX_HOLDINGS_URL = "https://www.ishares.com/us/products/239705/ishares-phlx-semiconductor-etf/latest-holdings.csv"
BUSINESSQUANT_URL = "https://data.businessquant.com/estimates"
MIN_SOXX_COVERAGE = 90.0


def get_text(url):
    request = urllib.request.Request(url, headers={"User-Agent": "USMarketDashboard/1.0"})
    with urllib.request.urlopen(request, timeout=25) as response:
        return response.read().decode("utf-8-sig", errors="replace")


def parse_spy_fy1(html):
    """Extract State Street's adjacent table value, not an unrelated page number."""
    match = re.search(
        r"Price/Earnings Ratio FY1.*?</th>\s*<td[^>]*class=\"data\"[^>]*>\s*([0-9]+(?:\.[0-9]+)?)",
        html, re.IGNORECASE | re.DOTALL,
    )
    return round(float(match.group(1)), 2) if match else None


def parse_soxx_holdings(text):
    """Return public equity rows from iShares' current holdings CSV."""
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Ticker,")), None)
    if start is None:
        return []
    rows = []
    for row in csv.DictReader(io.StringIO("\n".join(lines[start:]))):
        try:
            ticker = (row.get("Ticker") or "").strip().upper()
            weight = float((row.get("Weight (%)") or "").replace(",", ""))
            quantity = float((row.get("Quantity") or "").replace(",", ""))
            market_value = float((row.get("Market Value") or "").replace(",", ""))
        except ValueError:
            continue
        if ticker and ticker != "-" and weight > 0 and quantity > 0 and market_value > 0:
            rows.append({"ticker": ticker, "weight": weight, "quantity": quantity,
                         "market_value": market_value})
    return rows


def select_fy1_eps(payload, today):
    """Choose the first positive, forward annual consensus EPS estimate."""
    candidates = []
    for section in payload.get("data") or []:
        if section.get("dimension") != "annual":
            continue
        for item in section.get("estimates") or []:
            try:
                year = int(str(item.get("period", "")))
                eps = float(item.get("value_estimate"))
            except (TypeError, ValueError):
                continue
            if (item.get("data_type") == "estimate" and year >= today.year
                    and math.isfinite(eps) and eps > 0):
                candidates.append((year, eps))
    return min(candidates, default=(None, None))[1]


def businessquant_fy1_eps(ticker, api_key, today):
    """Return ``(EPS, diagnostic)`` without logging credentials or raw payloads."""
    query = urllib.parse.urlencode({"ticker": ticker, "mode": "eps", "api_key": api_key})
    try:
        payload = json.loads(get_text(f"{BUSINESSQUANT_URL}?{query}"))
        if payload.get("error"):
            return None, "access_denied"
        if not payload.get("data"):
            return None, "empty_response"
        return select_fy1_eps(payload, today), "ok"
    except urllib.error.HTTPError as exc:
        return None, f"http_{exc.code}"
    except (urllib.error.URLError, json.JSONDecodeError, TimeoutError):
        return None, "request_error"


def calculate_soxx_fy1(holdings, api_key, today, request_pause=1.1):
    """Calculate aggregate market value / FY1 aggregate earnings.

    The method is equivalent to a market-value weighted harmonic P/E average,
    and avoids the mathematically-invalid arithmetic average of company P/Es.
    The free endpoint is intentionally paced at <=1 request/second so a daily
    33-holding refresh stays below its observed short-window rate limit.
    """
    total_value = sum(row["market_value"] for row in holdings)
    covered_value = 0.0
    forward_earnings = 0.0
    diagnostics = {}
    for index, row in enumerate(holdings):
        eps, diagnostic = businessquant_fy1_eps(row["ticker"], api_key, today)
        diagnostics[diagnostic] = diagnostics.get(diagnostic, 0) + 1
        if eps is not None:
            covered_value += row["market_value"]
            forward_earnings += row["quantity"] * eps
        # A permission denial cannot improve on subsequent tickers.  Stop early
        # rather than wasting the free-tier request budget.
        if diagnostic == "access_denied" or diagnostic.startswith("http_"):
            break
        if index < len(holdings) - 1:
            time.sleep(request_pause)
    coverage = round(100 * covered_value / total_value, 2) if total_value else 0.0
    pe = round(covered_value / forward_earnings, 2) if forward_earnings > 0 else None
    return pe, coverage, len(holdings), diagnostics


def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, json.JSONDecodeError):
        return default


def update_history(history, observation):
    entries = [item for item in history.get("entries", []) if item.get("date") != observation["date"]]
    entries.append(observation)
    history["schema_version"] = 1
    history["entries"] = sorted(entries, key=lambda item: item["date"])[-756:]
    return history


def main():
    market_path = os.path.join(HERE, "market_data.json")
    market = load_json(market_path, {})
    observation_date = market.get("d_latest")
    if not observation_date:
        raise RuntimeError("market_data.json has no completed-session date")
    today = dt.date.fromisoformat(observation_date)
    quotes = market.get("quotes", {})
    api_key = os.environ.get("BUSINESSQUANT_API_KEY", "").strip()
    spy_pe = None
    try:
        spy_pe = parse_spy_fy1(get_text(SPY_URL))
    except urllib.error.URLError as exc:
        print(f"[valuation] SPY official source unavailable: {exc.reason}")

    soxx_pe = soxx_coverage = None
    soxx_holdings_count = 0
    soxx_diagnostics = {}
    soxx_status = "missing_api_key" if not api_key else "source_error"
    if api_key:
        try:
            holdings = parse_soxx_holdings(get_text(SOXX_HOLDINGS_URL))
            soxx_pe, soxx_coverage, soxx_holdings_count, soxx_diagnostics = calculate_soxx_fy1(holdings, api_key, today)
            soxx_status = "ok" if soxx_pe is not None and soxx_coverage >= MIN_SOXX_COVERAGE else "insufficient_coverage"
            if soxx_status != "ok":
                soxx_pe = None
        except urllib.error.URLError as exc:
            print(f"[valuation] SOXX source unavailable: {exc.reason}")

    observation = {
        "date": observation_date,
        "spy": {"forward_pe": spy_pe, "price": (quotes.get("usSPY") or {}).get("last"),
                "source": "State Street Price/Earnings Ratio FY1"},
        "soxx": {"forward_pe": soxx_pe, "price": (quotes.get("usSOXX") or {}).get("last"),
                 "coverage_pct": soxx_coverage, "holdings_count": soxx_holdings_count,
                 "status": soxx_status, "diagnostics": soxx_diagnostics,
                 "source": "iShares holdings + BusinessQuant FY1 consensus EPS"},
    }
    history_path = os.path.join(HERE, "valuation_history.json")
    history = update_history(load_json(history_path, {"schema_version": 1, "entries": []}), observation)
    with open(history_path, "w", encoding="utf-8") as handle:
        json.dump(history, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    market["valuation_history"] = history
    with open(market_path, "w", encoding="utf-8") as handle:
        json.dump(market, handle, ensure_ascii=False, indent=2)
    print(f"[valuation] SPY FY1={'ok' if spy_pe else 'unavailable'}; "
          f"SOXX={soxx_status}; coverage={soxx_coverage if soxx_coverage is not None else 'n/a'}%; "
          f"holdings={soxx_holdings_count}; diagnostics={soxx_diagnostics}")


if __name__ == "__main__":
    main()
