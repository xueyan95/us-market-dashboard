#!/usr/bin/env python3
"""Validate and securely upload a fresh dashboard portfolio snapshot.

This program deliberately has no broker integration and never writes a
snapshot into the repository. A trusted local runner supplies a temporary JSON
file created from a read-only broker response; this program validates it and
streams its base64 encoding to a GitHub Actions secret.
"""
from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path


REQUIRED_ACCOUNT_FIELDS = (
    "cash", "broker_total_value", "equity_value", "options_value",
)
FORBIDDEN_KEYS = {
    "account_number", "rhs_account_number", "rhc_account_number",
    "token", "api_key", "password", "cookie", "session",
}


def number(value, field):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if parsed < 0:
        raise ValueError(f"{field} cannot be negative")
    return parsed


def parse_as_of(value, max_age_minutes):
    if not isinstance(value, str):
        raise ValueError("as_of must be an ISO-8601 UTC timestamp")
    try:
        stamp = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("as_of must be an ISO-8601 timestamp") from exc
    if stamp.tzinfo is None:
        raise ValueError("as_of must include a timezone")
    age = dt.datetime.now(dt.timezone.utc) - stamp.astimezone(dt.timezone.utc)
    if age.total_seconds() < -300 or age.total_seconds() > max_age_minutes * 60:
        raise ValueError(f"snapshot age must be within {max_age_minutes} minutes")


def contains_forbidden_key(value):
    if isinstance(value, dict):
        for key, child in value.items():
            if str(key).lower() in FORBIDDEN_KEYS:
                return True
            if contains_forbidden_key(child):
                return True
    elif isinstance(value, list):
        return any(contains_forbidden_key(child) for child in value)
    return False


def validate_snapshot(snapshot, max_age_minutes=20):
    if not isinstance(snapshot, dict):
        raise ValueError("snapshot must be an object")
    if contains_forbidden_key(snapshot):
        raise ValueError("snapshot contains a forbidden sensitive field")
    if snapshot.get("currency") != "USD":
        raise ValueError("currency must be USD")
    parse_as_of(snapshot.get("as_of"), max_age_minutes)
    account = snapshot.get("account")
    if not isinstance(account, dict):
        raise ValueError("account must be an object")
    for field in REQUIRED_ACCOUNT_FIELDS:
        number(account.get(field), f"account.{field}")
    if not isinstance(snapshot.get("equities"), list):
        raise ValueError("equities must be a list")
    if not isinstance(snapshot.get("options"), list):
        raise ValueError("options must be a list")
    total = number(account["broker_total_value"], "account.broker_total_value")
    known = sum(number(account[field], f"account.{field}")
                for field in ("cash", "equity_value", "options_value"))
    if known > total + 0.01:
        raise ValueError("cash, equity, and options values exceed broker total")
    for item in snapshot["equities"]:
        if not isinstance(item, dict) or not str(item.get("symbol", "")).strip():
            raise ValueError("each equity needs a symbol")
        number(item.get("quantity"), "equity.quantity")
    for item in snapshot["options"]:
        if not isinstance(item, dict) or not str(item.get("underlying", "")).strip():
            raise ValueError("each option needs an underlying")
        number(item.get("quantity"), "option.quantity")
    return {
        "as_of": snapshot["as_of"],
        "equities": len(snapshot["equities"]),
        "options": len(snapshot["options"]),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot-file", required=True, type=Path)
    parser.add_argument("--repo", default="xueyan95/us-market-dashboard")
    parser.add_argument("--secret-name", default="PORTFOLIO_SNAPSHOT_B64")
    parser.add_argument("--max-age-minutes", default=20, type=int)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    snapshot = json.loads(args.snapshot_file.read_text(encoding="utf-8"))
    summary = validate_snapshot(snapshot, args.max_age_minutes)
    if args.validate_only:
        print(json.dumps(summary, ensure_ascii=False))
        return
    encoded = base64.b64encode(json.dumps(snapshot, separators=(",", ":"),
                                            ensure_ascii=False).encode())
    subprocess.run(
        ["gh", "secret", "set", args.secret_name, "--repo", args.repo],
        input=encoded,
        check=True,
    )
    print(json.dumps({"uploaded": True, **summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()
