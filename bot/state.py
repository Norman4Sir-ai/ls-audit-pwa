"""bot/state.py — Persistent daily state tracking (daily P&L, position tracking).

State is written to a JSON file so it survives bot restarts within the same
trading day.  On the first run of a new calendar day (UTC), the state resets.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_STATE_FILE = Path(__file__).resolve().parent.parent / "bot_state.json"


def _today_utc() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


def load_state(state_file: Path = _STATE_FILE) -> dict[str, Any]:
    """Load bot state from disk, resetting if it's a new UTC day.

    Returns:
        State dict with keys:
          - date: Current UTC date string (YYYY-MM-DD).
          - start_equity: Equity at start of today (set on first load of the day).
          - realized_pnl: Realised P&L accumulated today (updated after closes).
          - open_position: dict or None — the current open position.
    """
    today = _today_utc()

    if state_file.exists():
        try:
            with state_file.open("r", encoding="utf-8") as fh:
                state: dict[str, Any] = json.load(fh)
            if state.get("date") == today:
                return state
        except (json.JSONDecodeError, KeyError):
            pass

    # New day or corrupt file — reset
    return {
        "date": today,
        "start_equity": None,       # Set after first balance fetch
        "realized_pnl": 0.0,
        "open_position": None,
    }


def save_state(state: dict[str, Any], state_file: Path = _STATE_FILE) -> None:
    """Persist state to disk atomically."""
    tmp = state_file.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)
    tmp.replace(state_file)


def get_daily_loss_pct(state: dict[str, Any], current_equity: float) -> float:
    """Calculate today's loss as a percentage of start-of-day equity.

    A positive value means a *loss* (equity decreased).

    Args:
        state: Current state dict.
        current_equity: Latest equity balance.

    Returns:
        Loss percentage (positive = loss, negative = profit).
    """
    start = state.get("start_equity")
    if not start:
        return 0.0
    return ((start - current_equity) / start) * 100.0
