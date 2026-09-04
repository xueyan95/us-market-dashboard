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


def load_effective_portfolio(path=CONFIG_PATH):
    """Use the runtime broker snapshot as the source of truth for positions.

    The checked-in config remains a watch-list/classification fallback only.
    Quantities and costs never need to be duplicated in Git.
    """
    config = load_portfolio_config(path)
    try:
        from portfolio_snapshot import load_portfolio_snapshot
        snapshot = load_portfolio_snapshot()
    except (ImportError, OSError, ValueError):
        snapshot = {"available": False}
    if not snapshot.get("available"):
        return config

    metadata = {str(x["symbol"]).upper(): x for x in config.get("holdings", [])}
    symbols = []
    for item in snapshot.get("equities", []):
        symbol = str(item.get("symbol", "")).upper().strip()
        if symbol and symbol not in symbols:
            symbols.append(symbol)
    holdings = []
    for symbol in symbols:
        row = dict(metadata.get(symbol, {}))
        row["symbol"] = symbol
        row.setdefault("bucket", "current")
        holdings.append(row)

    underlyings = []
    for item in snapshot.get("options", []):
        symbol = str(item.get("underlying", "")).upper().strip()
        if symbol and symbol not in underlyings:
            underlyings.append(symbol)
    return {**config, "holdings": holdings, "option_underlyings": underlyings,
            "position_source": "runtime_snapshot"}
