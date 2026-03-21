"""bot/strategy.py — v1 Signal stub: MA-cross trend filter + RSI confirmation.

Philosophy (v1):
  - Deliberately simple and transparent.
  - Goal is a *stable pipeline with explanation logs*, not maximum profit.
  - A real Elliott-wave strategy is too subjective for automation in v1.
  - This stub generates LONG / SHORT / FLAT signals using:
      1. Trend filter : fast EMA > slow EMA → uptrend; fast < slow → downtrend.
      2. RSI confirmation: long only when RSI < overbought threshold,
                           short only when RSI > oversold threshold.
  - Every call logs *what a real strategy would do*, even if the signal is FLAT.

Signal values: "long" | "short" | "flat"
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from bot.logger import BotLogger


def _ema(series: pd.Series, period: int) -> pd.Series:
    """Exponential moving average."""
    return series.ewm(span=period, adjust=False).mean()


def _rsi(series: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index (Wilder smoothing)."""
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, float("nan"))
    return 100 - (100 / (1 + rs))


def generate_signal(
    df: pd.DataFrame,
    symbol: str,
    ma_fast: int = 20,
    ma_slow: int = 50,
    rsi_period: int = 14,
    rsi_overbought: float = 70.0,
    rsi_oversold: float = 30.0,
    logger: BotLogger | None = None,
) -> tuple[str, dict[str, Any]]:
    """Generate a trading signal from the latest completed candle.

    Uses the second-to-last candle (index -2) so we never trade on an
    incomplete (still open) candle.

    Args:
        df: OHLCV DataFrame with at least (ma_slow + rsi_period + 2) rows.
        symbol: Trading pair symbol for logging.
        ma_fast: Fast EMA period.
        ma_slow: Slow EMA period.
        rsi_period: RSI look-back period.
        rsi_overbought: RSI upper threshold (suppress longs above this).
        rsi_oversold: RSI lower threshold (suppress shorts below this).
        logger: Optional BotLogger for structured logging.

    Returns:
        Tuple of (signal, indicators_dict) where signal is one of
        "long" | "short" | "flat" and indicators_dict contains the values
        used for the decision.
    """
    min_required = ma_slow + rsi_period + 2
    if len(df) < min_required:
        reason = (
            f"Insufficient candle data: have {len(df)}, need ≥ {min_required}. "
            "Signal is FLAT until enough history is available."
        )
        if logger:
            logger.log_signal(symbol=symbol, signal="flat", indicators={}, reason=reason)
        return "flat", {}

    close = df["close"]
    ema_fast = _ema(close, ma_fast)
    ema_slow = _ema(close, ma_slow)
    rsi_series = _rsi(close, rsi_period)

    # Use the last *completed* candle (second-to-last row)
    idx = -2
    ema_fast_val = float(ema_fast.iloc[idx])
    ema_slow_val = float(ema_slow.iloc[idx])
    rsi_val = float(rsi_series.iloc[idx])
    close_val = float(close.iloc[idx])
    candle_time = str(df["timestamp"].iloc[idx])

    indicators: dict[str, Any] = {
        "candle_time": candle_time,
        "close": round(close_val, 4),
        f"ema_{ma_fast}": round(ema_fast_val, 4),
        f"ema_{ma_slow}": round(ema_slow_val, 4),
        "rsi": round(rsi_val, 2),
    }

    # --- Trend filter ---
    uptrend = ema_fast_val > ema_slow_val
    downtrend = ema_fast_val < ema_slow_val

    # --- RSI confirmation ---
    rsi_ok_long = rsi_val < rsi_overbought
    rsi_ok_short = rsi_val > rsi_oversold

    if uptrend and rsi_ok_long:
        signal = "long"
        reason = (
            f"LONG signal on {symbol} @ {close_val:.4f}. "
            f"EMA{ma_fast} ({ema_fast_val:.2f}) > EMA{ma_slow} ({ema_slow_val:.2f}) → uptrend. "
            f"RSI {rsi_val:.1f} < {rsi_overbought} → not overbought. Entry confirmed."
        )
    elif downtrend and rsi_ok_short:
        signal = "short"
        reason = (
            f"SHORT signal on {symbol} @ {close_val:.4f}. "
            f"EMA{ma_fast} ({ema_fast_val:.2f}) < EMA{ma_slow} ({ema_slow_val:.2f}) → downtrend. "
            f"RSI {rsi_val:.1f} > {rsi_oversold} → not oversold. Entry confirmed."
        )
    elif uptrend and not rsi_ok_long:
        signal = "flat"
        reason = (
            f"FLAT on {symbol}: uptrend (EMA{ma_fast} {ema_fast_val:.2f} > EMA{ma_slow} "
            f"{ema_slow_val:.2f}) but RSI {rsi_val:.1f} ≥ {rsi_overbought} → overbought. "
            "Waiting for RSI pullback before entering long."
        )
    elif downtrend and not rsi_ok_short:
        signal = "flat"
        reason = (
            f"FLAT on {symbol}: downtrend (EMA{ma_fast} {ema_fast_val:.2f} < EMA{ma_slow} "
            f"{ema_slow_val:.2f}) but RSI {rsi_val:.1f} ≤ {rsi_oversold} → oversold. "
            "Waiting for RSI bounce before entering short."
        )
    else:
        signal = "flat"
        reason = (
            f"FLAT on {symbol}: no clear trend. "
            f"EMA{ma_fast} {ema_fast_val:.2f} ≈ EMA{ma_slow} {ema_slow_val:.2f}. "
            f"RSI {rsi_val:.1f}. Waiting for trend to establish."
        )

    if logger:
        logger.log_signal(symbol=symbol, signal=signal, indicators=indicators, reason=reason)

    return signal, indicators
