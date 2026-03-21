"""tests/test_logger.py — Unit tests for the structured JSON-lines logger."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from bot.logger import BotLogger


@pytest.fixture
def tmp_logger(tmp_path):
    log_file = tmp_path / "test_bot.jsonl"
    return BotLogger(log_file=log_file, level="DEBUG"), log_file


def _read_entries(log_file: Path) -> list[dict]:
    lines = log_file.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line]


class TestBotLogger:
    def test_startup_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_startup({"symbol": "BTC/USDT:USDT"})
        entries = _read_entries(log_file)
        assert len(entries) == 1
        assert entries[0]["event"] == "startup"

    def test_ohlcv_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_ohlcv("BTC/USDT:USDT", "4h", 100, 50000.0)
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "ohlcv_fetched"
        assert entry["num_candles"] == 100
        assert entry["last_close"] == 50000.0

    def test_signal_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_signal("BTC/USDT:USDT", "long", {"rsi": 45.0}, "RSI ok, uptrend")
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "signal"
        assert entry["signal"] == "long"
        assert entry["indicators"]["rsi"] == 45.0

    def test_risk_check_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_risk_check("daily_loss_limit", True, {"loss": 1.0}, "Under limit")
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "risk_check"
        assert entry["passed"] is True

    def test_order_dry_run_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_order(
            symbol="BTC/USDT:USDT",
            side="buy",
            qty=0.002,
            entry_price=50_000.0,
            stop_loss=49_000.0,
            take_profit=52_000.0,
            dry_run=True,
            order_id=None,
            reason="DRY RUN test",
        )
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "order"
        assert entry["side"] == "buy"
        assert "DRY_RUN" in entry["mode"]

    def test_skip_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_skip("BTC/USDT:USDT", "No signal", {})
        entries = _read_entries(log_file)
        assert entries[0]["event"] == "skip"

    def test_daily_pause_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_daily_pause(3.5, 3.0)
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "daily_pause"
        assert entry["daily_loss_pct"] == 3.5

    def test_error_logged(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_error("test_context", ValueError("something went wrong"))
        entries = _read_entries(log_file)
        entry = entries[0]
        assert entry["event"] == "error"
        assert entry["error_type"] == "ValueError"

    def test_all_entries_have_timestamp(self, tmp_logger):
        logger, log_file = tmp_logger
        logger.log_startup({})
        logger.log_skip("SYM", "test", {})
        for entry in _read_entries(log_file):
            assert "timestamp" in entry
