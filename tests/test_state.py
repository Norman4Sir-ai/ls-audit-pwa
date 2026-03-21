"""tests/test_state.py — Unit tests for daily state management."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from bot.state import get_daily_loss_pct, load_state, save_state


def _today() -> str:
    return datetime.now(tz=timezone.utc).strftime("%Y-%m-%d")


class TestLoadState:
    def test_new_state_has_today_date(self, tmp_path):
        sf = tmp_path / "state.json"
        state = load_state(sf)
        assert state["date"] == _today()
        assert state["start_equity"] is None
        assert state["realized_pnl"] == 0.0
        assert state["open_position"] is None

    def test_same_day_state_persisted(self, tmp_path):
        sf = tmp_path / "state.json"
        state = load_state(sf)
        state["start_equity"] = 12345.0
        save_state(state, sf)

        state2 = load_state(sf)
        assert state2["start_equity"] == 12345.0

    def test_old_state_resets(self, tmp_path):
        sf = tmp_path / "state.json"
        old = {
            "date": "2000-01-01",
            "start_equity": 9999.0,
            "realized_pnl": -100.0,
            "open_position": None,
        }
        sf.write_text(json.dumps(old), encoding="utf-8")

        state = load_state(sf)
        assert state["date"] == _today()
        assert state["start_equity"] is None
        assert state["realized_pnl"] == 0.0

    def test_corrupt_file_resets(self, tmp_path):
        sf = tmp_path / "state.json"
        sf.write_text("not_valid_json{{{", encoding="utf-8")
        state = load_state(sf)
        assert state["date"] == _today()


class TestGetDailyLossPct:
    def test_no_start_equity_returns_zero(self):
        state = {"start_equity": None, "realized_pnl": 0.0}
        assert get_daily_loss_pct(state, 10_000.0) == 0.0

    def test_loss_calculated_correctly(self):
        state = {"start_equity": 10_000.0}
        pct = get_daily_loss_pct(state, 9_700.0)
        assert abs(pct - 3.0) < 1e-8

    def test_profit_is_negative_loss(self):
        state = {"start_equity": 10_000.0}
        pct = get_daily_loss_pct(state, 10_500.0)
        assert pct < 0.0
