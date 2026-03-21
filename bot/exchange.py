"""bot/exchange.py — OKX ccxt exchange connection (demo/paper mode).

OKX demo trading uses a *separate* set of API keys obtained from the OKX
demo trading portal (https://www.okx.com/demo-trading).  The ccxt sandbox
flag must be set to True so ccxt routes requests to the demo endpoints.

Reference:
  https://docs.ccxt.com/#/?id=sandbox-mode
  https://www.okx.com/docs-v5/en/#overview-demo-trading-services
"""

from __future__ import annotations

import time
from typing import Any

import ccxt

from bot.logger import BotLogger


def create_exchange(
    api_key: str,
    secret: str,
    passphrase: str,
    demo_mode: bool = True,
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> ccxt.okx:
    """Create and configure a ccxt OKX exchange instance.

    Args:
        api_key: OKX API key (demo key recommended for v1).
        secret: OKX API secret.
        passphrase: OKX API passphrase.
        demo_mode: If True, use OKX demo trading endpoints.
        max_retries: Number of retries on transient errors.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger instance for structured logging.

    Returns:
        Configured ccxt.okx instance.
    """
    exchange = ccxt.okx(
        {
            "apiKey": api_key,
            "secret": secret,
            "password": passphrase,  # ccxt uses 'password' for OKX passphrase
            "options": {
                "defaultType": "swap",  # USDT-margined perpetual swaps
            },
        }
    )

    if demo_mode:
        # Enable OKX demo/paper trading — routes to demo.okx.com endpoints
        exchange.set_sandbox_mode(True)

    # ccxt retry configuration
    exchange.enableRateLimit = True

    return exchange


def fetch_balance(
    exchange: ccxt.okx,
    currency: str = "USDT",
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> float:
    """Fetch the available equity (USDT) from the exchange.

    For swap accounts, the 'total' balance in USDT is used as equity.

    Args:
        exchange: ccxt OKX exchange instance.
        currency: The currency to read (default USDT).
        max_retries: Retry count on transient errors.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger for error logging.

    Returns:
        Total equity in the given currency.

    Raises:
        ccxt.NetworkError: On persistent connectivity issues.
        ccxt.ExchangeError: On exchange-level errors.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            balance = exchange.fetch_balance(params={"type": "swap"})
            total = balance.get("total", {}).get(currency, 0.0)
            return float(total)
        except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
            last_error = exc
            if logger:
                logger.log_error(f"fetch_balance attempt {attempt}", exc)
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise last_error or RuntimeError("fetch_balance: unknown error")


def fetch_open_positions(
    exchange: ccxt.okx,
    symbol: str,
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> list[dict[str, Any]]:
    """Fetch currently open positions for a symbol.

    Args:
        exchange: ccxt OKX exchange instance.
        symbol: CCXT symbol, e.g. 'BTC/USDT:USDT'.
        max_retries: Retry count on transient errors.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger for error logging.

    Returns:
        List of open position dicts (may be empty).
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            positions = exchange.fetch_positions([symbol])
            return [p for p in positions if p.get("contracts", 0) and p["contracts"] != 0]
        except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
            last_error = exc
            if logger:
                logger.log_error(f"fetch_open_positions attempt {attempt}", exc)
            if attempt < max_retries:
                time.sleep(retry_delay)

    raise last_error or RuntimeError("fetch_open_positions: unknown error")
