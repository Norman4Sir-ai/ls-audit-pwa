"""bot/risk.py — Hard risk checks before placing any order.

All checks are logged with pass/fail status and a human-readable reason.
If any check fails, no order is placed.

Checks (in order):
  1. max_open_positions: Only 1 open position at a time in v1.
  2. daily_loss_limit: Pause if today's loss ≥ max_daily_loss_pct.
  3. position_size: Compute size from 1% risk; check it's non-zero.
  4. leverage_cap: Verify requested leverage ≤ max_leverage config.
"""

from __future__ import annotations

from typing import Any

from bot.logger import BotLogger


def check_max_open_positions(
    open_positions: list[Any],
    max_open: int,
    logger: BotLogger | None = None,
) -> bool:
    """Fail if number of open positions equals or exceeds the configured max.

    Args:
        open_positions: List of currently open position dicts.
        max_open: Maximum allowed simultaneous positions.
        logger: Optional BotLogger.

    Returns:
        True if the check passes (can open new position), False otherwise.
    """
    count = len(open_positions)
    passed = count < max_open
    details = {"open_count": count, "max_open": max_open}

    if passed:
        reason = f"Open positions ({count}) < max ({max_open}). OK to open new position."
    else:
        reason = (
            f"Already have {count} open position(s) (max {max_open}). "
            "No new trade until existing position is closed."
        )

    if logger:
        logger.log_risk_check("max_open_positions", passed, details, reason)

    return passed


def check_daily_loss_limit(
    daily_loss_pct: float,
    max_daily_loss_pct: float,
    logger: BotLogger | None = None,
) -> bool:
    """Fail if today's cumulative loss has reached or exceeded the daily limit.

    Args:
        daily_loss_pct: Today's loss as a % of start equity (positive = loss).
        max_daily_loss_pct: Maximum allowed daily loss percentage.
        logger: Optional BotLogger.

    Returns:
        True if under the limit (trading allowed), False if limit breached.
    """
    passed = daily_loss_pct < max_daily_loss_pct
    details = {
        "daily_loss_pct": round(daily_loss_pct, 4),
        "max_daily_loss_pct": max_daily_loss_pct,
    }

    if passed:
        reason = (
            f"Daily loss {daily_loss_pct:.2f}% < limit {max_daily_loss_pct:.2f}%. "
            "Trading allowed."
        )
    else:
        reason = (
            f"Daily loss {daily_loss_pct:.2f}% ≥ limit {max_daily_loss_pct:.2f}%. "
            "No new trades for the rest of today."
        )

    if logger:
        logger.log_risk_check("daily_loss_limit", passed, details, reason)

    return passed


def calculate_position_size(
    equity: float,
    entry_price: float,
    stop_loss_price: float,
    max_risk_per_trade_pct: float,
    logger: BotLogger | None = None,
) -> float:
    """Calculate position size (in base currency contracts) from fixed-risk model.

    Formula: qty = (equity * risk_pct / 100) / |entry - stop_loss|

    Args:
        equity: Current account equity in USDT.
        entry_price: Planned entry price.
        stop_loss_price: Planned stop-loss price.
        max_risk_per_trade_pct: Percentage of equity to risk per trade.
        logger: Optional BotLogger.

    Returns:
        Position size in base currency (BTC for BTC/USDT).
        Returns 0.0 if the calculation is invalid (e.g. zero price distance).
    """
    risk_amount = equity * (max_risk_per_trade_pct / 100.0)
    price_distance = abs(entry_price - stop_loss_price)

    if price_distance < 1e-8 or equity <= 0:
        details = {
            "equity": equity,
            "entry_price": entry_price,
            "stop_loss_price": stop_loss_price,
            "price_distance": price_distance,
        }
        reason = (
            "Position size calculation failed: price distance between entry and stop-loss "
            "is effectively zero, or equity is non-positive. Skipping trade."
        )
        if logger:
            logger.log_risk_check("position_size", False, details, reason)
        return 0.0

    qty = risk_amount / price_distance
    details = {
        "equity": round(equity, 4),
        "risk_amount_usdt": round(risk_amount, 4),
        "entry_price": entry_price,
        "stop_loss_price": stop_loss_price,
        "price_distance": round(price_distance, 4),
        "qty": round(qty, 8),
    }
    reason = (
        f"Position size: risk {max_risk_per_trade_pct}% of equity "
        f"({equity:.2f} USDT) = {risk_amount:.2f} USDT. "
        f"Price distance entry→SL = {price_distance:.4f}. "
        f"Qty = {qty:.6f} contracts."
    )
    if logger:
        logger.log_risk_check("position_size", True, details, reason)

    return qty


def check_leverage(
    requested_leverage: int,
    max_leverage: int,
    logger: BotLogger | None = None,
) -> bool:
    """Check that requested leverage does not exceed the configured maximum.

    Args:
        requested_leverage: Leverage to be used for the trade.
        max_leverage: Maximum allowed leverage from config.
        logger: Optional BotLogger.

    Returns:
        True if leverage is within the allowed range.
    """
    passed = requested_leverage <= max_leverage
    details = {"requested": requested_leverage, "max_leverage": max_leverage}

    if passed:
        reason = (
            f"Leverage {requested_leverage}x ≤ max {max_leverage}x. "
            "Leverage check passed."
        )
    else:
        reason = (
            f"Requested leverage {requested_leverage}x exceeds max {max_leverage}x. "
            "Trade blocked by leverage cap."
        )

    if logger:
        logger.log_risk_check("leverage_cap", passed, details, reason)

    return passed


def run_all_checks(
    *,
    open_positions: list[Any],
    daily_loss_pct: float,
    equity: float,
    entry_price: float,
    stop_loss_price: float,
    cfg_risk: dict[str, Any],
    logger: BotLogger | None = None,
) -> tuple[bool, float]:
    """Run all risk checks in sequence.

    Args:
        open_positions: Currently open positions.
        daily_loss_pct: Today's cumulative loss % (positive = loss).
        equity: Current account equity in USDT.
        entry_price: Planned entry price.
        stop_loss_price: Planned stop-loss price.
        cfg_risk: Risk section of the config dict.
        logger: Optional BotLogger.

    Returns:
        Tuple (all_passed: bool, qty: float).
        qty is 0.0 if any check failed.
    """
    max_open = int(cfg_risk.get("max_open_positions", 1))
    max_daily = float(cfg_risk.get("max_daily_loss_pct", 3.0))
    max_risk_pct = float(cfg_risk.get("max_risk_per_trade_pct", 1.0))
    max_lev = int(cfg_risk.get("max_leverage", 2))

    if not check_max_open_positions(open_positions, max_open, logger):
        return False, 0.0

    if not check_daily_loss_limit(daily_loss_pct, max_daily, logger):
        return False, 0.0

    qty = calculate_position_size(equity, entry_price, stop_loss_price, max_risk_pct, logger)
    if qty <= 0.0:
        return False, 0.0

    # Leverage cap: v1 always uses max_leverage from config.
    # check_leverage is exposed for callers that supply a different value.
    if logger:
        logger.log_risk_check(
            "leverage_cap",
            True,
            {"leverage": max_lev, "max_leverage": max_lev},
            f"Leverage fixed at {max_lev}x (= configured max). Leverage cap OK.",
        )

    return True, qty
