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
    leveraged = config.get("leveraged_etfs", {})
    if not isinstance(leveraged, dict):
        raise ValueError("leveraged_etfs must be an object")
    for symbol, item in leveraged.items():
        if (not str(symbol).strip() or not isinstance(item, dict)
                or not str(item.get("underlying", "")).strip()
                or float(item.get("leverage", 0)) <= 0
                or item.get("direction") not in {"long", "short"}):
            raise ValueError(f"Invalid leveraged ETF mapping: {symbol}")
    return config


def holding_symbols(config, market_prefix=False):
    symbols = [str(item["symbol"]).upper().strip() for item in config["holdings"]]
    return [f"us{symbol}" for symbol in symbols] if market_prefix else symbols


def holding_names(config):
    return {f"us{symbol}": symbol for symbol in holding_symbols(config)}


def option_underlyings(config):
    return [str(symbol).upper().strip() for symbol in config.get("option_underlyings", [])]


def leveraged_etfs(config):
    """Return normalized leveraged-ETF metadata keyed by ticker."""
    result = {}
    for symbol, item in config.get("leveraged_etfs", {}).items():
        result[str(symbol).upper().strip()] = {
            **item,
            "underlying": str(item["underlying"]).upper().strip(),
            "leverage": float(item["leverage"]),
            "direction": str(item["direction"]).lower().strip(),
        }
    return result


def inherit_leveraged_layer_categories(layers, config, current_symbols):
    """Insert held leveraged ETFs beside their underlying in the same layer/category."""
    result = [(title, subtitle, [(cat, list(symbols)) for cat, symbols in cats])
              for title, subtitle, cats in layers]
    locations = {
        symbol: (layer_idx, cat_idx)
        for layer_idx, (_, _, cats) in enumerate(result)
        for cat_idx, (_, symbols) in enumerate(cats)
        for symbol in symbols
    }
    held = set(current_symbols)
    for ticker, item in leveraged_etfs(config).items():
        etf_symbol = f"us{ticker}"
        underlying = f"us{item['underlying']}"
        if etf_symbol not in held or underlying not in locations:
            continue
        layer_idx, cat_idx = locations[underlying]
        symbols = result[layer_idx][2][cat_idx][1]
        if etf_symbol not in symbols:
            symbols.insert(symbols.index(underlying) + 1, etf_symbol)
    return result


def inherit_leveraged_matrix_categories(layers, config, current_symbols):
    """Insert held leveraged ETFs beside their underlying in the trend matrix."""
    result = [(title, list(symbols)) for title, symbols in layers]
    locations = {symbol: layer_idx for layer_idx, (_, symbols) in enumerate(result)
                 for symbol in symbols}
    held = set(current_symbols)
    for ticker, item in leveraged_etfs(config).items():
        etf_symbol = f"us{ticker}"
        underlying = f"us{item['underlying']}"
        if etf_symbol not in held or underlying not in locations:
            continue
        symbols = result[locations[underlying]][1]
        if etf_symbol not in symbols:
            symbols.insert(symbols.index(underlying) + 1, etf_symbol)
    return result


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
