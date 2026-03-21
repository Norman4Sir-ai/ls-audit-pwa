"""tests/test_risk.py — Unit tests for the risk management module."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from bot.risk import (
    calculate_position_size,
    check_daily_loss_limit,
    check_leverage,
    check_max_open_positions,
    run_all_checks,
)


class TestMaxOpenPositions:
    def test_no_positions_passes(self):
        assert check_max_open_positions([], max_open=1) is True

    def test_one_position_blocks(self):
        assert check_max_open_positions([{"id": "pos1"}], max_open=1) is False

    def test_logger_called(self):
        logger = MagicMock()
        check_max_open_positions([], max_open=1, logger=logger)
        logger.log_risk_check.assert_called_once()


class TestDailyLossLimit:
    def test_no_loss_passes(self):
        assert check_daily_loss_limit(0.0, max_daily_loss_pct=3.0) is True

    def test_small_loss_passes(self):
        assert check_daily_loss_limit(1.5, max_daily_loss_pct=3.0) is True

    def test_at_limit_fails(self):
        assert check_daily_loss_limit(3.0, max_daily_loss_pct=3.0) is False

    def test_over_limit_fails(self):
        assert check_daily_loss_limit(5.0, max_daily_loss_pct=3.0) is False

    def test_logger_called(self):
        logger = MagicMock()
        check_daily_loss_limit(1.0, max_daily_loss_pct=3.0, logger=logger)
        logger.log_risk_check.assert_called_once()


class TestCalculatePositionSize:
    def test_basic_calculation(self):
        # equity=10000, 1% risk = 100 USDT, SL distance = 500 USDT
        qty = calculate_position_size(
            equity=10_000.0,
            entry_price=50_000.0,
            stop_loss_price=49_500.0,
            max_risk_per_trade_pct=1.0,
        )
        assert abs(qty - 100.0 / 500.0) < 1e-8

    def test_zero_distance_returns_zero(self):
        qty = calculate_position_size(
            equity=10_000.0,
            entry_price=50_000.0,
            stop_loss_price=50_000.0,  # same price
            max_risk_per_trade_pct=1.0,
        )
        assert qty == 0.0

    def test_zero_equity_returns_zero(self):
        qty = calculate_position_size(
            equity=0.0,
            entry_price=50_000.0,
            stop_loss_price=49_000.0,
            max_risk_per_trade_pct=1.0,
        )
        assert qty == 0.0


class TestCheckLeverage:
    def test_within_limit_passes(self):
        assert check_leverage(2, max_leverage=2) is True

    def test_exceeds_limit_fails(self):
        assert check_leverage(5, max_leverage=2) is False

    def test_logger_called(self):
        logger = MagicMock()
        check_leverage(2, max_leverage=2, logger=logger)
        logger.log_risk_check.assert_called_once()


class TestRunAllChecks:
    def _base_cfg(self) -> dict:
        return {
            "max_open_positions": 1,
            "max_daily_loss_pct": 3.0,
            "max_risk_per_trade_pct": 1.0,
            "max_leverage": 2,
            "stop_loss_pct": 2.0,
            "take_profit_pct": 4.0,
        }

    def test_all_pass(self):
        passed, qty = run_all_checks(
            open_positions=[],
            daily_loss_pct=0.0,
            equity=10_000.0,
            entry_price=50_000.0,
            stop_loss_price=49_000.0,
            cfg_risk=self._base_cfg(),
        )
        assert passed is True
        assert qty > 0.0

    def test_open_position_blocks(self):
        passed, qty = run_all_checks(
            open_positions=[{"id": "pos1"}],
            daily_loss_pct=0.0,
            equity=10_000.0,
            entry_price=50_000.0,
            stop_loss_price=49_000.0,
            cfg_risk=self._base_cfg(),
        )
        assert passed is False
        assert qty == 0.0

    def test_daily_loss_blocks(self):
        passed, qty = run_all_checks(
            open_positions=[],
            daily_loss_pct=3.5,
            equity=10_000.0,
            entry_price=50_000.0,
            stop_loss_price=49_000.0,
            cfg_risk=self._base_cfg(),
        )
        assert passed is False
        assert qty == 0.0
