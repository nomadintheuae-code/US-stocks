"""Phase 5.1 BacktestEngine — additive, offline, deterministic walk-forward backtesting.

Independent of the production scanner: ``sentinel.py``, ``config.yaml``,
``StrategyValidator.run()`` and the golden baseline are untouched. This module
reuses (without modifying) the Phase 3 ``Strategy`` abstraction
(``engines/strategies/base.py``) and mirrors the point-in-time, trailing-only
design of ``StrategyValidator.evaluate_walk_forward``.

Design guarantees:
- **Deterministic**: identical ``(strategy, df, params)`` inputs always yield an
  identical record.
- **Look-ahead-free**: every strategy evaluation at bar ``t`` uses only
  ``df.iloc[: t + 1]``.
- **Non-mutating**: the engine never mutates the caller's DataFrame or Strategy
  instance (the strategy is deep-copied once per run).
- **Safe on insufficient data**: returns a well-formed, zero-trade record.
- **Config-driven**: defaults come from ``BacktestConfig``
  (``sentinel/config.py``) with constructor overrides; ``config.yaml`` need not
  change.

``run()`` returns a metrics dict with a stable schema::

    profit_factor, trades (R-multiples), n_trades, win_rate,
    total_return_pct, annualized_return_pct, max_drawdown_pct,
    start, evaluated_bars, insufficient_data, reason
"""
from __future__ import annotations

import copy
from typing import Dict, Optional

import pandas as pd

TRADING_DAYS_PER_YEAR = 252

# Stable schema keys returned by BacktestEngine.run()
RESULT_KEYS = (
    "profit_factor",
    "trades",
    "n_trades",
    "win_rate",
    "total_return_pct",
    "annualized_return_pct",
    "max_drawdown_pct",
    "start",
    "evaluated_bars",
    "insufficient_data",
    "reason",
)


def _empty_record(reason: str) -> dict:
    """Well-formed record for insufficient / non-evaluable inputs."""
    return {
        "profit_factor": 1.0,
        "trades": [],
        "n_trades": 0,
        "win_rate": 0.0,
        "total_return_pct": 0.0,
        "annualized_return_pct": None,
        "max_drawdown_pct": 0.0,
        "start": None,
        "evaluated_bars": 0,
        "insufficient_data": True,
        "reason": reason,
    }


class BacktestEngine:
    """Config-driven walk-forward backtester for any ``Strategy``.

    Parameters (constructor overrides win over ``BacktestConfig`` defaults):
    - ``lookback_bars``: how many trailing bars form the evaluation window.
    - ``min_bars_for_entry``: minimum bars before the first entry is allowed
      (also the insufficient-data threshold).
    - ``risk_pct``: fixed per-trade capital risk fraction used for the equity
      curve / drawdown / returns modelling.
    - ``initial_capital``: starting equity for the returns calculations.
    """

    def __init__(
        self,
        config: Optional[object] = None,
        lookback_bars: Optional[int] = None,
        min_bars_for_entry: Optional[int] = None,
        risk_pct: float = 0.015,
        initial_capital: float = 100_000.0,
    ) -> None:
        if config is None:
            try:
                from sentinel.config import get_config

                config = get_config()
            except Exception:
                config = None

        bt = getattr(config, "backtest", None)
        if lookback_bars is None:
            lookback_bars = bt.lookback_bars if bt is not None else 250
        if min_bars_for_entry is None:
            min_bars_for_entry = bt.min_bars_for_entry if bt is not None else 50

        if lookback_bars is None or int(lookback_bars) < 1:
            raise ValueError("lookback_bars must be >= 1")
        if min_bars_for_entry is None or int(min_bars_for_entry) < 1:
            raise ValueError("min_bars_for_entry must be >= 1")
        if risk_pct is None or float(risk_pct) <= 0:
            raise ValueError("risk_pct must be > 0")
        if initial_capital is None or float(initial_capital) <= 0:
            raise ValueError("initial_capital must be > 0")

        self.lookback_bars = int(lookback_bars)
        self.min_bars_for_entry = int(min_bars_for_entry)
        self.risk_pct = float(risk_pct)
        self.initial_capital = float(initial_capital)

    # ------------------------------------------------------------- evaluation

    @staticmethod
    def _calc_at(local, df: pd.DataFrame, bar_idx: int) -> dict:
        """Evaluate a Strategy instance on the trailing-only slice at ``bar_idx``."""
        local.calculate(df.iloc[: bar_idx + 1])
        entry, stop, target = local.get_entry_stop_target()
        return {
            "actionable": bool(local.is_actionable()),
            "entry": entry,
            "stop": stop,
            "target": target,
        }

    def evaluate_at(self, strategy, df: pd.DataFrame, bar_idx: int) -> dict:
        """Trailing-only decision inputs at ``bar_idx``.

        Computed from ``df.iloc[: bar_idx + 1]`` only — no bar after ``bar_idx``
        can influence the result. Public and deterministic, so tests can assert
        point-in-time isolation directly.
        """
        local = copy.deepcopy(strategy)
        return self._calc_at(local, df, bar_idx)

    def run(self, strategy, df: Optional[pd.DataFrame]) -> dict:
        """Walk-forward backtest of ``strategy`` over ``df``.

        Entry uses the strategy's own ``is_actionable()`` / ``get_entry_stop_target()``
        evaluated on the trailing slice; exits mirror ``StrategyValidator`` rules
        (stop hit -> -1.0 R, target hit -> +R, end-of-data -> partial R). Never
        raises on data problems; never mutates ``df`` or ``strategy``.
        """
        if df is None or len(df) < self.min_bars_for_entry:
            return _empty_record("insufficient_data")

        required = {"Close", "High", "Low"}
        if not required.issubset(df.columns):
            return _empty_record("missing_ohlc_columns")

        local = copy.deepcopy(strategy)
        start = max(self.min_bars_for_entry, len(df) - self.lookback_bars)

        trades: list = []
        equity = self.initial_capital
        curve = [equity]
        in_pos = False
        entry_p = stop_p = target_p = 0.0

        for t in range(start, len(df)):
            close_t = float(df["Close"].iloc[t])
            high_t = float(df["High"].iloc[t])
            low_t = float(df["Low"].iloc[t])

            if in_pos:
                risk = entry_p - stop_p
                r: Optional[float] = None
                if low_t <= stop_p:
                    r = -1.0
                elif target_p and high_t >= target_p:
                    r = (target_p - entry_p) / risk
                elif t == len(df) - 1:
                    r = (close_t - entry_p) / risk
                if r is not None:
                    trades.append(float(r))
                    equity *= 1.0 + float(r) * self.risk_pct
                    curve.append(equity)
                    in_pos = False
            else:
                d = self._calc_at(local, df, t)
                if not d["actionable"]:
                    continue
                if d["entry"] is None or d["stop"] is None:
                    continue
                e = float(d["entry"])
                s = float(d["stop"])
                if e <= 0 or s <= 0 or e <= s:
                    continue
                entry_p, stop_p = e, s
                target_p = float(d["target"]) if d["target"] is not None else 0.0
                in_pos = True

        evaluated_bars = len(df) - start
        return self._metrics(trades, curve, start, evaluated_bars)

    # -------------------------------------------------------------- metrics

    @staticmethod
    def _metrics(trades: list, curve: list, start: int, evaluated_bars: int) -> dict:
        pos = sum(t for t in trades if t > 0)
        neg = abs(sum(t for t in trades if t < 0))
        if neg > 0:
            pf = pos / neg
        else:
            pf = 5.0 if pos > 0 else 1.0
        pf = round(min(10.0, float(pf)), 2)

        n = len(trades)
        wins = sum(1 for t in trades if t > 0)
        win_rate = round(wins / n, 4) if n else 0.0

        equity = curve[-1]
        total_return_pct = round((equity / curve[0] - 1.0) * 100.0, 2)

        if evaluated_bars > 0 and equity > 0:
            annual = (equity / curve[0]) ** (TRADING_DAYS_PER_YEAR / evaluated_bars) - 1.0
            annualized_return_pct = round(float(annual) * 100.0, 2)
        else:
            annualized_return_pct = None

        peak = curve[0]
        max_dd = 0.0
        for value in curve:
            if value > peak:
                peak = value
            if peak > 0:
                max_dd = max(max_dd, (peak - value) / peak)
        max_drawdown_pct = round(float(max_dd) * 100.0, 2)

        return {
            "profit_factor": pf,
            "trades": [round(float(t), 4) for t in trades],
            "n_trades": n,
            "win_rate": win_rate,
            "total_return_pct": total_return_pct,
            "annualized_return_pct": annualized_return_pct,
            "max_drawdown_pct": max_drawdown_pct,
            "start": start,
            "evaluated_bars": evaluated_bars,
            "insufficient_data": False,
            "reason": None,
        }


__all__ = ["BacktestEngine", "RESULT_KEYS", "TRADING_DAYS_PER_YEAR"]
