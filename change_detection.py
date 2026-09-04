#!/usr/bin/env python3
"""Notify only when positions, risk limits, or material market moves change."""
import json
import os
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = HERE / ".state"


def main():
    market = json.loads((HERE / "market_data.json").read_text(encoding="utf-8"))
    snapshot = market.get("private_portfolio_snapshot", {})
    current = {
        "as_of": snapshot.get("as_of"),
        "positions": [(x.get("symbol"), x.get("quantity")) for x in snapshot.get("equities", [])],
        "options": [(x.get("underlying"), x.get("expiration_date"), x.get("strike"), x.get("quantity"))
                    for x in snapshot.get("options", [])],
        "risk": snapshot.get("risk", {}),
        "moves": {k: v.get("chg_pct") for k, v in market.get("holdings", {}).items() if v},
    }
    prior_path = STATE / "previous.json"
    prior = json.loads(prior_path.read_text()) if prior_path.exists() else {}
    reasons = []
    if not prior:
        reasons.append("first baseline")
    if current["positions"] != prior.get("positions") or current["options"] != prior.get("options"):
        reasons.append("positions changed")
    if any(abs(float(v or 0)) >= 5 for v in current["moves"].values()):
        reasons.append("holding moved >=5%")
    risk = current["risk"]
    if risk.get("cash_pct", 100) < 10 or risk.get("options_pct", 0) > 25 or risk.get("largest_position_pct", 0) > 25:
        reasons.append("risk threshold breached")
    actionable = bool(reasons)
    STATE.mkdir(exist_ok=True)
    prior_path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write(f"actionable={'true' if actionable else 'false'}\n")
    print("Actionable:" if actionable else "Quiet:", "; ".join(reasons) or "no meaningful change")


if __name__ == "__main__":
    main()
