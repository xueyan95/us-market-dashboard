"""Read a Robinhood portfolio snapshot without storing it in Git.

The dashboard accepts a runtime JSON snapshot, never broker credentials. A
trusted synchronizer may write it locally, or GitHub Actions may materialize it
from a repository secret for an explicitly public dashboard.
"""
import json
import os
from pathlib import Path


HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "portfolio_snapshot.json"


def snapshot_path():
    return Path(os.environ.get("PORTFOLIO_SNAPSHOT_PATH", DEFAULT_PATH))


def load_portfolio_snapshot():
    """Return a validated snapshot or a non-sensitive unavailable status."""
    path = snapshot_path()
    if not path.exists():
        return {"available": False, "reason": "No portfolio snapshot found."}
    try:
        with path.open(encoding="utf-8") as f:
            snapshot = json.load(f)
        if not isinstance(snapshot.get("account"), dict):
            raise ValueError("missing account")
        if not isinstance(snapshot.get("equities", []), list):
            raise ValueError("equities must be a list")
        if not isinstance(snapshot.get("options", []), list):
            raise ValueError("options must be a list")
        snapshot["available"] = True
        return snapshot
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"Invalid snapshot: {exc}"}


def snapshot_equity_symbols(snapshot):
    if not snapshot.get("available"):
        return []
    return [str(item.get("symbol", "")).upper().strip()
            for item in snapshot.get("equities", []) if item.get("symbol")]
