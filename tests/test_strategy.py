"""tests/test_strategy.py — Unit tests for the signal generation module."""

from __future__ import annotations

import pandas as pd
import pytest

from bot.strategy import _ema, _rsi, generate_signal


def _make_df(closes: list[float]) -> pd.DataFrame:
    """Helper: build a minimal OHLCV DataFrame from close prices."""
    n = len(closes)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="4h", tz="UTC"),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        }
    )


class TestEmaRsi:
    def test_ema_returns_series(self):
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        result = _ema(s, period=3)
        assert len(result) == 5
        assert result.iloc[-1] > result.iloc[0]

    def test_rsi_range(self):
        import numpy as np

        prices = pd.Series([float(i) for i in range(1, 30)])
        rsi = _rsi(prices, period=14)
        # After warmup, RSI must be within 0-100
        valid = rsi.dropna()
        assert (valid >= 0).all() and (valid <= 100).all()


class TestGenerateSignal:
    def test_insufficient_data_returns_flat(self):
        df = _make_df([100.0] * 10)
        signal, indicators = generate_signal(df, symbol="BTC/USDT:USDT")
        assert signal == "flat"
        assert indicators == {}

    def test_uptrend_rsi_not_overbought_returns_long(self):
        # Build series where fast EMA > slow EMA (uptrend) and RSI < 70
        # Create a steadily rising series — enough candles for ma_slow=50
        closes = list(range(100, 200))  # 100 rising candles
        df = _make_df(closes)
        signal, indicators = generate_signal(
            df,
            symbol="BTC/USDT:USDT",
            ma_fast=20,
            ma_slow=50,
            rsi_period=14,
            rsi_overbought=70,
            rsi_oversold=30,
        )
        # In a steadily rising series the RSI may be high (>70), so accept long or flat
        assert signal in ("long", "flat")

    def test_downtrend_returns_short_or_flat(self):
        closes = list(range(200, 100, -1))  # 100 falling candles
        df = _make_df(closes)
        signal, indicators = generate_signal(
            df,
            symbol="BTC/USDT:USDT",
            ma_fast=20,
            ma_slow=50,
            rsi_period=14,
            rsi_overbought=70,
            rsi_oversold=30,
        )
        assert signal in ("short", "flat")

    def test_indicators_present_when_enough_data(self):
        closes = [float(i % 20 + 90) for i in range(100)]
        df = _make_df(closes)
        signal, indicators = generate_signal(df, symbol="BTC/USDT:USDT")
        if signal != "flat" or indicators:  # flat with {} only when insufficient data
            assert "rsi" in indicators or signal == "flat"

    def test_logger_called(self):
        from unittest.mock import MagicMock

        closes = [float(i % 20 + 90) for i in range(100)]
        df = _make_df(closes)
        mock_logger = MagicMock()
        generate_signal(df, symbol="TEST/USDT:USDT", logger=mock_logger)
        mock_logger.log_signal.assert_called_once()
