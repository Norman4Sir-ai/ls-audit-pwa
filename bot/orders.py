"""bot/orders.py — Order execution for OKX demo/paper trading.

In v1, the bot always runs in demo mode.  When dry_run=True (default), orders
are only logged (never sent to the exchange).  When dry_run=False and
demo_mode=True, orders are sent to the OKX *demo* API (paper money only).

OKX perpetual swap order flow:
  1. Set leverage for the symbol (once per session or per trade).
  2. Place a market order in the direction of the signal.
  3. Place a conditional stop-loss order.
  4. (Optional) Place a take-profit order.

All outcomes are logged with full context and human-readable explanation.
"""

from __future__ import annotations

import time
from typing import Any

import ccxt

from bot.logger import BotLogger


def set_leverage(
    exchange: ccxt.okx,
    symbol: str,
    leverage: int,
    margin_mode: str = "cross",
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> bool:
    """Set leverage for the given symbol on OKX.

    Args:
        exchange: ccxt OKX instance.
        symbol: CCXT symbol, e.g. 'BTC/USDT:USDT'.
        leverage: Integer leverage (e.g. 2).
        margin_mode: 'cross' or 'isolated'.
        max_retries: Retry count.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger.

    Returns:
        True if leverage was set successfully.
    """
    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            exchange.set_leverage(leverage, symbol, params={"mgnMode": margin_mode})
            if logger:
                logger.log_risk_check(
                    "set_leverage",
                    True,
                    {"symbol": symbol, "leverage": leverage, "margin_mode": margin_mode},
                    f"Leverage set to {leverage}x ({margin_mode}) for {symbol}.",
                )
            return True
        except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
            last_error = exc
            if logger:
                logger.log_error(f"set_leverage attempt {attempt}", exc)
            if attempt < max_retries:
                time.sleep(retry_delay)
        except ccxt.ExchangeError as exc:
            if logger:
                logger.log_error("set_leverage", exc)
            return False

    if logger and last_error:
        logger.log_error("set_leverage final", last_error)
    return False


def place_order(
    exchange: ccxt.okx,
    symbol: str,
    side: str,
    qty: float,
    entry_price: float,
    stop_loss_price: float,
    take_profit_price: float,
    leverage: int,
    dry_run: bool = True,
    max_retries: int = 3,
    retry_delay: float = 5.0,
    logger: BotLogger | None = None,
) -> dict[str, Any] | None:
    """Place a market entry order with stop-loss (and optionally take-profit).

    If dry_run=True, the order is only logged — nothing is sent to the exchange.

    Args:
        exchange: ccxt OKX instance.
        symbol: CCXT symbol.
        side: 'buy' (long) or 'sell' (short).
        qty: Position size in base currency contracts.
        entry_price: Current/expected entry price (for logging only in market orders).
        stop_loss_price: Stop-loss trigger price.
        take_profit_price: Take-profit trigger price.
        leverage: Leverage to set before placing.
        dry_run: If True, log only — do not send orders.
        max_retries: Retry count on transient errors.
        retry_delay: Seconds between retries.
        logger: Optional BotLogger.

    Returns:
        Order dict from ccxt if the order was placed, or a synthetic dict for dry-run.
        Returns None on unrecoverable error.
    """
    close_side = "sell" if side == "buy" else "buy"

    if dry_run:
        synthetic_order: dict[str, Any] = {
            "id": "dry_run",
            "symbol": symbol,
            "side": side,
            "qty": qty,
            "entry_price": entry_price,
            "stop_loss": stop_loss_price,
            "take_profit": take_profit_price,
            "leverage": leverage,
            "status": "dry_run",
        }
        reason = (
            f"DRY RUN — would place {side.upper()} order for {qty:.6f} {symbol.split('/')[0]} "
            f"@ ~{entry_price:.4f} USDT. "
            f"SL: {stop_loss_price:.4f}, TP: {take_profit_price:.4f}, "
            f"Leverage: {leverage}x. Order NOT sent to exchange."
        )
        if logger:
            logger.log_order(
                symbol=symbol,
                side=side,
                qty=qty,
                entry_price=entry_price,
                stop_loss=stop_loss_price,
                take_profit=take_profit_price,
                dry_run=True,
                order_id=None,
                reason=reason,
            )
        return synthetic_order

    # --- Live demo order ---
    set_leverage(exchange, symbol, leverage, logger=logger)

    last_error: Exception | None = None
    order: dict[str, Any] | None = None

    for attempt in range(1, max_retries + 1):
        try:
            # Market entry order
            order = exchange.create_order(
                symbol=symbol,
                type="market",
                side=side,
                amount=qty,
                params={"tdMode": "cross"},  # cross-margin for swaps
            )
            break
        except (ccxt.NetworkError, ccxt.RequestTimeout) as exc:
            last_error = exc
            if logger:
                logger.log_error(f"place_order attempt {attempt}", exc)
            if attempt < max_retries:
                time.sleep(retry_delay)
        except ccxt.ExchangeError as exc:
            if logger:
                logger.log_error("place_order exchange error", exc)
            return None

    if order is None:
        if logger and last_error:
            logger.log_error("place_order final", last_error)
        return None

    order_id = order.get("id", "unknown")

    # Attach stop-loss (algo order)
    try:
        exchange.create_order(
            symbol=symbol,
            type="stop",
            side=close_side,
            amount=qty,
            price=stop_loss_price,
            params={
                "stopPrice": stop_loss_price,
                "reduceOnly": True,
                "tdMode": "cross",
            },
        )
    except ccxt.ExchangeError as exc:
        if logger:
            logger.log_error("place_stop_loss", exc)

    # Attach take-profit (algo order)
    try:
        exchange.create_order(
            symbol=symbol,
            type="limit",
            side=close_side,
            amount=qty,
            price=take_profit_price,
            params={
                "reduceOnly": True,
                "tdMode": "cross",
            },
        )
    except ccxt.ExchangeError as exc:
        if logger:
            logger.log_error("place_take_profit", exc)

    reason = (
        f"DEMO ORDER placed: {side.upper()} {qty:.6f} {symbol.split('/')[0]} "
        f"@ market (~{entry_price:.4f} USDT). "
        f"Order ID: {order_id}. "
        f"SL: {stop_loss_price:.4f}, TP: {take_profit_price:.4f}, Leverage: {leverage}x."
    )
    if logger:
        logger.log_order(
            symbol=symbol,
            side=side,
            qty=qty,
            entry_price=entry_price,
            stop_loss=stop_loss_price,
            take_profit=take_profit_price,
            dry_run=False,
            order_id=order_id,
            reason=reason,
        )

    return order
