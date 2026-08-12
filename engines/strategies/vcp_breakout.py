"""VCP Breakout strategy.

Composes :class:`VCPIndicator` (with ``use_contraction_pivot=True``) to
detect a proper VCP contraction pivot and evaluate breakout status, then
produces a strategy score, human-readable signals, and an
entry/stop/target plan.

This is a STRATEGY, not an indicator. It is additive and opt-in.
Existing VCPIndicator / VCPAnalyzer / StrategyValidator behavior is
completely unchanged.
"""

from typing import List, Optional

import pandas as pd

from config import CONFIG
from engines.analysis import VCPIndicator
from engines.strategies.base import Strategy


class VCPBreakoutStrategy(Strategy):
    """VCP + contraction pivot + breakout confirmation strategy.

    Composes :class:`VCPIndicator` (with ``use_contraction_pivot=True``)
    and does NOT duplicate any VCP detection logic. The strategy is
    evaluated on the final bar of ``df`` using only historical data
    (look-ahead-free, inherited from ``VCPIndicator.detect_pivot``).

    Configuration
    -------------
    - ``entry_slippage_pct`` — fraction above the pivot used as the
      breakout entry (default ``0.002`` → ``pivot * 1.002``).
    - ``stop_mult`` — stop distance in ATR multiples (default from
      ``CONFIG["STOP_LOSS_ATR"]``, 2.0).
    - ``target_mult`` — target distance in R-multiples (default from
      ``CONFIG["TARGET_R_MULTIPLE"]``, 2.5).
    - ``breakout_bonus`` / ``max_score`` — strategy score scaling.
    """

    def __init__(
        self,
        vcp: Optional[VCPIndicator] = None,
        entry_slippage_pct: float = 0.002,
        breakout_bonus: int = 15,
        max_score: int = 120,
        stop_mult: Optional[float] = None,
        target_mult: Optional[float] = None,
    ):
        self.vcp = vcp if vcp is not None else VCPIndicator(use_contraction_pivot=True)
        if entry_slippage_pct < 0:
            raise ValueError("entry_slippage_pct must be >= 0")
        if breakout_bonus < 0:
            raise ValueError("breakout_bonus must be >= 0")
        if max_score < 1:
            raise ValueError("max_score must be >= 1")
        self.entry_slippage_pct = entry_slippage_pct
        self.breakout_bonus = breakout_bonus
        self.max_score = max_score
        self.stop_mult = float(
            stop_mult if stop_mult is not None else CONFIG["STOP_LOSS_ATR"]
        )
        self.target_mult = float(
            target_mult if target_mult is not None else CONFIG["TARGET_R_MULTIPLE"]
        )
        self._reset()

    # ------------------------------------------------------------------
    # Internal state
    # ------------------------------------------------------------------

    def _reset(self) -> None:
        self._score = 0
        self._signals: List[str] = []
        self._entry = 0.0
        self._stop = 0.0
        self._target = 0.0
        self._actionable = False

    # ------------------------------------------------------------------
    # Strategy ABC
    # ------------------------------------------------------------------

    def calculate(self, df: pd.DataFrame) -> dict:
        """Compute the VCP breakout analysis for the final bar of *df*.

        Returns a dict with at minimum: ``score``, ``signals``, ``atr``.
        When there is insufficient data (< ``VCPIndicator.min_data_bars``
        bars, i.e. 130) or ATR is unusable, returns a safe non-actionable
        result (score 0, empty signals, entry/stop/target all ``0.0``).
        """
        self._reset()

        vcp_result = self.vcp.calculate(df)
        if not isinstance(vcp_result, dict):
            return self.result()

        pivot_info = vcp_result.get("pivot")
        atr = float(vcp_result.get("atr", 0.0) or 0.0)
        if pivot_info is None or atr <= 0:
            return self.result()

        pivot = float(pivot_info["price"])
        breakout = pivot_info.get("breakout", {})
        handle = pivot_info.get("handle", {})
        confirmed = bool(breakout.get("confirmed", False))
        failed = bool(breakout.get("failed", False))

        if confirmed:
            breakout_signal = "Breakout Confirmed"
        elif failed:
            breakout_signal = "Breakout Failed"
        else:
            breakout_signal = "Awaiting Breakout"

        signals = list(vcp_result.get("signals", []))
        if breakout_signal not in signals:
            signals.append(breakout_signal)
        if confirmed:
            signals.append("VCP Breakout Setup")

        if failed:
            score = 0
        else:
            score = int(vcp_result.get("score", 0)) + (self.breakout_bonus if confirmed else 0)
        score = int(min(self.max_score, max(0, score)))

        entry = round(pivot * (1 + self.entry_slippage_pct), 2)
        stop = round(entry - atr * self.stop_mult, 2)
        target = round(entry + (entry - stop) * self.target_mult, 2)

        self._score = score
        self._signals = signals
        self._entry = entry
        self._stop = stop
        self._target = target
        self._actionable = bool(confirmed)

        return self.result(
            atr=atr,
            confirmed=confirmed,
            failed=failed,
            pivot=pivot,
            breakout=breakout,
            handle=handle,
        )

    def get_score(self) -> int:
        """Return the strategy composite score (its own score scale)."""
        return self._score

    def get_signals(self) -> List[str]:
        """Return list of human-readable signal strings."""
        return list(self._signals)

    def get_entry_stop_target(self) -> tuple:
        """Return ``(entry_price, stop_price, target_price)``."""
        return self._entry, self._stop, self._target

    def is_actionable(self) -> bool:
        """True when a confirmed breakout has been detected."""
        return self._actionable

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def result(
        self,
        atr: float = 0.0,
        confirmed: bool = False,
        failed: bool = False,
        pivot: float = 0.0,
        breakout: dict = None,
        handle: dict = None,
    ) -> dict:
        """Assemble the public result dict from the cached state."""
        return {
            "score": self._score,
            "atr": atr,
            "signals": list(self._signals),
            "entry": self._entry,
            "stop": self._stop,
            "target": self._target,
            "actionable": self._actionable,
            "confirmed": bool(confirmed),
            "failed": bool(failed),
            "pivot": pivot,
            "breakout": breakout if breakout is not None else {},
            "handle": handle if handle is not None else {},
        }
