#!/usr/bin/env python3
"""main.py — OKX Trading Bot v1 entry point.

Usage:
    python main.py [--config config_crypto.yaml]

The bot runs in an infinite loop, executing one cycle every
`bot.loop_interval_seconds` (default 60s).  Each cycle:
  1. Fetch current equity from OKX demo account.
  2. Check daily loss limit (pause if breached).
  3. Fetch 4h OHLCV candles for BTC/USDT:USDT.
  4. Generate a signal (MA-cross + RSI stub).
  5. Run hard risk checks.
  6. Place a demo order (or log "skip" with reason).

All decisions are logged as JSON-lines with human-readable explanations.
Press Ctrl+C to stop.
"""

from __future__ import annotations

import argparse
import sys
import time

from bot.config import get_api_credentials, load_config
from bot.data import fetch_ohlcv
from bot.exchange import create_exchange, fetch_balance, fetch_open_positions
from bot.logger import BotLogger
from bot.orders import place_order
from bot.risk import run_all_checks
from bot.state import get_daily_loss_pct, load_state, save_state
from bot.strategy import generate_signal


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="OKX Trading Bot v1")
    parser.add_argument(
        "--config",
        default="config_crypto.yaml",
        help="Path to YAML config file (default: config_crypto.yaml)",
    )
    return parser.parse_args()


def _config_summary(cfg: dict) -> dict:
    """Extract a safe (no secrets) summary of config for startup log."""
    return {
        "symbol": cfg["market"]["symbol"],
        "timeframe": cfg["market"]["timeframe"],
        "strategy": cfg["strategy"]["type"],
        "demo_mode": cfg["exchange"]["demo_mode"],
        "dry_run": cfg["bot"]["dry_run"],
        "max_risk_per_trade_pct": cfg["risk"]["max_risk_per_trade_pct"],
        "max_daily_loss_pct": cfg["risk"]["max_daily_loss_pct"],
        "max_leverage": cfg["risk"]["max_leverage"],
        "max_open_positions": cfg["risk"]["max_open_positions"],
    }


def run_cycle(*, exchange, cfg: dict, state: dict, logger: BotLogger) -> dict:
    """Execute one full trading cycle.

    Args:
        exchange: ccxt OKX exchange instance.
        cfg: Full configuration dict.
        state: Daily state dict (mutated in-place on equity init).
        logger: BotLogger instance.

    Returns:
        Updated state dict.
    """
    symbol: str = cfg["market"]["symbol"]
    timeframe: str = cfg["market"]["timeframe"]
    cfg_risk: dict = cfg["risk"]
    cfg_strategy: dict = cfg["strategy"]
    cfg_bot: dict = cfg["bot"]

    # --- 1. Fetch equity ---
    try:
        equity = fetch_balance(
            exchange,
            max_retries=cfg_bot["max_retries"],
            retry_delay=cfg_bot["retry_delay_seconds"],
            logger=logger,
        )
    except Exception as exc:
        logger.log_error("fetch_balance", exc)
        return state

    if state["start_equity"] is None:
        state["start_equity"] = equity
        logger.log_skip(
            symbol,
            f"Start-of-day equity initialised: {equity:.4f} USDT.",
            {"start_equity": equity},
        )
        save_state(state)

    # --- 2. Daily loss limit check ---
    daily_loss_pct = get_daily_loss_pct(state, equity)
    max_daily = float(cfg_risk["max_daily_loss_pct"])

    if daily_loss_pct >= max_daily:
        logger.log_daily_pause(daily_loss_pct, max_daily)
        return state

    # --- 3. Fetch OHLCV ---
    try:
        df = fetch_ohlcv(
            exchange,
            symbol=symbol,
            timeframe=timeframe,
            limit=cfg["market"]["candles_limit"],
            max_retries=cfg_bot["max_retries"],
            retry_delay=cfg_bot["retry_delay_seconds"],
            logger=logger,
        )
    except Exception as exc:
        logger.log_error("fetch_ohlcv", exc)
        return state

    # --- 4. Generate signal ---
    signal, indicators = generate_signal(
        df,
        symbol=symbol,
        ma_fast=cfg_strategy["ma_fast"],
        ma_slow=cfg_strategy["ma_slow"],
        rsi_period=cfg_strategy["rsi_period"],
        rsi_overbought=cfg_strategy["rsi_overbought"],
        rsi_oversold=cfg_strategy["rsi_oversold"],
        logger=logger,
    )

    if signal == "flat":
        logger.log_skip(symbol, "Signal is FLAT — no trade this cycle.", indicators)
        return state

    # --- 5. Risk checks ---
    try:
        open_positions = fetch_open_positions(
            exchange,
            symbol=symbol,
            max_retries=cfg_bot["max_retries"],
            retry_delay=cfg_bot["retry_delay_seconds"],
            logger=logger,
        )
    except Exception as exc:
        logger.log_error("fetch_open_positions", exc)
        return state

    last_close = float(df["close"].iloc[-2])  # last completed candle
    sl_pct = float(cfg_risk["stop_loss_pct"]) / 100.0
    tp_pct = float(cfg_risk["take_profit_pct"]) / 100.0

    if signal == "long":
        stop_loss_price = last_close * (1 - sl_pct)
        take_profit_price = last_close * (1 + tp_pct)
    else:  # short
        stop_loss_price = last_close * (1 + sl_pct)
        take_profit_price = last_close * (1 - tp_pct)

    all_passed, qty = run_all_checks(
        open_positions=open_positions,
        daily_loss_pct=daily_loss_pct,
        equity=equity,
        entry_price=last_close,
        stop_loss_price=stop_loss_price,
        cfg_risk=cfg_risk,
        logger=logger,
    )

    if not all_passed or qty <= 0.0:
        logger.log_skip(
            symbol,
            "Risk checks failed — no order placed.",
            {"signal": signal, "qty": qty},
        )
        return state

    # --- 6. Place order (demo / dry-run) ---
    place_order(
        exchange=exchange,
        symbol=symbol,
        side="buy" if signal == "long" else "sell",
        qty=qty,
        entry_price=last_close,
        stop_loss_price=stop_loss_price,
        take_profit_price=take_profit_price,
        leverage=int(cfg_risk["max_leverage"]),
        dry_run=bool(cfg_bot["dry_run"]),
        max_retries=cfg_bot["max_retries"],
        retry_delay=cfg_bot["retry_delay_seconds"],
        logger=logger,
    )

    return state


def main() -> None:
    args = _parse_args()

    # --- Load config & credentials ---
    try:
        cfg = load_config(args.config)
    except (FileNotFoundError, ValueError) as exc:
        print(f"[FATAL] Config error: {exc}", file=sys.stderr)
        sys.exit(1)

    try:
        creds = get_api_credentials()
    except EnvironmentError as exc:
        print(f"[FATAL] Credentials error: {exc}", file=sys.stderr)
        sys.exit(1)

    # --- Set up logger ---
    logger = BotLogger(
        log_file=cfg["logging"]["file"],
        level=cfg["logging"]["level"],
    )
    logger.log_startup(_config_summary(cfg))

    # --- Create exchange ---
    exchange = create_exchange(
        api_key=creds["api_key"],
        secret=creds["secret"],
        passphrase=creds["passphrase"],
        demo_mode=bool(cfg["exchange"]["demo_mode"]),
        max_retries=cfg["bot"]["max_retries"],
        retry_delay=float(cfg["bot"]["retry_delay_seconds"]),
        logger=logger,
    )

    # --- Load daily state ---
    state = load_state()

    interval = int(cfg["bot"]["loop_interval_seconds"])
    print(f"Bot started. Loop interval: {interval}s. Press Ctrl+C to stop.")

    try:
        while True:
            try:
                state = run_cycle(exchange=exchange, cfg=cfg, state=state, logger=logger)
                save_state(state)
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                logger.log_error("main_loop", exc)

            time.sleep(interval)
    except KeyboardInterrupt:
        print("\nBot stopped by user.")
        logger.log_shutdown("Bot stopped by user (KeyboardInterrupt).")


if __name__ == "__main__":
    main()
