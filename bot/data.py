"""bot/data.py — OHLCV data fetching and preprocessing.

Fetches candlestick data from OKX via ccxt and returns a pandas DataFrame
with columns: timestamp, open, high, low, close, volume.
"""

from __future__ import annotations

import time
from typing import Any

import ccxt
import pandas as pd

from bot.logger import BotLogger


def fetch_ohlcv(
    exchange: ccxt.okx,
    symbol: str,
    timeframe: str = "4h",
    limit: int = 100,
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> pd.DataFrame:
    """Fetch OHLCV candles from OKX and return as a DataFrame.

    Args:
        exchange: ccxt OKX exchange instance.
        symbol: CCXT symbol, e.g. 'BTC/USDT:USDT'.
        timeframe: Candle timeframe, e.g. '4h'.
        limit: Number of candles to fetch.
        max_retries: Retry count on transient errors.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger for structured logging.

    Returns:
        DataFrame with columns [timestamp, open, high, low, close, volume].
        Sorted ascending by timestamp.

    Raises:
        ccxt.NetworkError: On persistent connectivity issues.
        ValueError: If the returned data is empty or malformed.
    """
    last_error: Exception | None = None

    for attempt in range(1, max_retries + 1):
        try:
            raw: list[list[Any]] = exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            break
        except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
            last_error = exc
            if logger:
                logger.log_error(f"fetch_ohlcv attempt {attempt}", exc)
            if attempt < max_retries:
                time.sleep(retry_delay)
    else:
        raise last_error or RuntimeError("fetch_ohlcv: unknown error")

    if not raw:
        raise ValueError(f"No OHLCV data returned for {symbol} {timeframe}.")

    df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.sort_values("timestamp").reset_index(drop=True)

    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")

    if df["close"].isna().all():
        raise ValueError(f"OHLCV data for {symbol} has all-NaN close prices.")

    if logger:
        logger.log_ohlcv(
            symbol=symbol,
            timeframe=timeframe,
            num_candles=len(df),
            last_close=float(df["close"].iloc[-1]),
        )

    return df
