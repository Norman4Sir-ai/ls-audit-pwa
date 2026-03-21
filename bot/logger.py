"""bot/logger.py — Structured JSON-lines logging with human-readable explanations.

Every trading decision is logged as a JSON object on a single line, so logs
can be streamed, grepped, or imported into pandas.  Each log entry includes:
  - timestamp (ISO-8601)
  - event type (e.g. "signal", "risk_check", "order", "skip", "error")
  - symbol & timeframe
  - context dict (price, indicators, etc.)
  - decision & reason (human-readable explanation)
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utcnow_iso() -> str:
    return datetime.now(tz=timezone.utc).isoformat()


class BotLogger:
    """Writes structured JSON-lines to a file and plain text to stdout."""

    def __init__(self, log_file: str | Path, level: str = "INFO") -> None:
        self._log_path = Path(log_file)
        self._log_path.parent.mkdir(parents=True, exist_ok=True)

        numeric_level = getattr(logging, level.upper(), logging.INFO)
        logging.basicConfig(
            level=numeric_level,
            format="%(asctime)s [%(levelname)s] %(message)s",
            handlers=[logging.StreamHandler(sys.stdout)],
        )
        self._stdlib_logger = logging.getLogger("bot")

    # ------------------------------------------------------------------
    # Low-level writer
    # ------------------------------------------------------------------

    def _write(self, entry: dict[str, Any]) -> None:
        """Append a JSON record to the log file and echo to stdout."""
        entry.setdefault("timestamp", _utcnow_iso())
        line = json.dumps(entry, ensure_ascii=False)
        with self._log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
        self._stdlib_logger.info("[%s] %s", entry.get("event"), entry.get("reason", ""))

    # ------------------------------------------------------------------
    # High-level event helpers
    # ------------------------------------------------------------------

    def log_startup(self, config_summary: dict[str, Any]) -> None:
        """Log bot startup with config summary."""
        self._write(
            {
                "event": "startup",
                "reason": "Bot started. Config loaded.",
                "config": config_summary,
            }
        )

    def log_ohlcv(self, symbol: str, timeframe: str, num_candles: int, last_close: float) -> None:
        """Log successful OHLCV fetch."""
        self._write(
            {
                "event": "ohlcv_fetched",
                "symbol": symbol,
                "timeframe": timeframe,
                "reason": (
                    f"Fetched {num_candles} {timeframe} candles for {symbol}. "
                    f"Last close: {last_close:.4f}"
                ),
                "num_candles": num_candles,
                "last_close": last_close,
            }
        )

    def log_signal(
        self,
        symbol: str,
        signal: str,
        indicators: dict[str, Any],
        reason: str,
    ) -> None:
        """Log strategy signal with indicator context."""
        self._write(
            {
                "event": "signal",
                "symbol": symbol,
                "signal": signal,
                "indicators": indicators,
                "reason": reason,
            }
        )

    def log_risk_check(
        self,
        check_name: str,
        passed: bool,
        details: dict[str, Any],
        reason: str,
    ) -> None:
        """Log a single risk check result."""
        self._write(
            {
                "event": "risk_check",
                "check": check_name,
                "passed": passed,
                "details": details,
                "reason": reason,
            }
        )

    def log_order(
        self,
        symbol: str,
        side: str,
        qty: float,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        dry_run: bool,
        order_id: str | None,
        reason: str,
    ) -> None:
        """Log order placement (real or dry-run)."""
        mode = "DRY_RUN — would execute" if dry_run else "LIVE"
        self._write(
            {
                "event": "order",
                "symbol": symbol,
                "side": side,
                "qty": qty,
                "entry_price": entry_price,
                "stop_loss": stop_loss,
                "take_profit": take_profit,
                "mode": mode,
                "order_id": order_id,
                "reason": reason,
            }
        )

    def log_skip(self, symbol: str, reason: str, details: dict[str, Any] | None = None) -> None:
        """Log that no trade was taken, with explanation."""
        self._write(
            {
                "event": "skip",
                "symbol": symbol,
                "reason": reason,
                "details": details or {},
            }
        )

    def log_daily_pause(self, daily_loss_pct: float, max_daily_loss_pct: float) -> None:
        """Log that the bot paused trading due to daily loss limit."""
        self._write(
            {
                "event": "daily_pause",
                "daily_loss_pct": round(daily_loss_pct, 4),
                "max_daily_loss_pct": max_daily_loss_pct,
                "reason": (
                    f"Daily loss of {daily_loss_pct:.2f}% has reached the "
                    f"{max_daily_loss_pct:.2f}% limit. No new trades until "
                    "the next calendar day or manual reset."
                ),
            }
        )

    def log_error(self, context: str, error: Exception) -> None:
        """Log an unexpected error."""
        self._write(
            {
                "event": "error",
                "context": context,
                "error_type": type(error).__name__,
                "error_msg": str(error),
                "reason": f"Error in {context}: {error}",
            }
        )

    def log_shutdown(self, reason: str) -> None:
        """Log a clean bot shutdown event."""
        self._write({"event": "shutdown", "reason": reason})
