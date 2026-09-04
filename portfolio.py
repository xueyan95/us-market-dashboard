"""Shared helpers for the public, symbol-only portfolio configuration."""
import json
from pathlib import Path


HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "portfolio_config.json"


def load_portfolio_config(path=CONFIG_PATH):
    """Load and minimally validate the portfolio configuration."""
    with Path(path).open(encoding="utf-8") as f:
        config = json.load(f)
    holdings = config.get("holdings", [])
    if not isinstance(holdings, list) or not holdings:
        raise ValueError("portfolio_config.json must contain a non-empty holdings list")
    for item in holdings:
        if not isinstance(item, dict) or not str(item.get("symbol", "")).strip():
            raise ValueError("Each holding needs a non-empty symbol")
    return config


def holding_symbols(config, market_prefix=False):
    symbols = [str(item["symbol"]).upper().strip() for item in config["holdings"]]
    return [f"us{symbol}" for symbol in symbols] if market_prefix else symbols


def holding_names(config):
    return {f"us{symbol}": symbol for symbol in holding_symbols(config)}


def option_underlyings(config):
    return [str(symbol).upper().strip() for symbol in config.get("option_underlyings", [])]
