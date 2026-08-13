"""Phase 5.1 BacktestEngine + Phase 5.2 purged k-fold CV — additive, offline, deterministic.

Independent of the production scanner: ``sentinel.py``, ``config.yaml``,
``StrategyValidator.run()`` and the golden baseline are untouched. This module
reuses (without modifying) the Phase 3 ``Strategy`` abstraction
(``engines/strategies/base.py``) and mirrors the point-in-time, trailing-only
design of ``StrategyValidator.evaluate_walk_forward``.

Design guarantees:
- **Deterministic**: identical ``(strategy, df, params)`` inputs always yield an
  identical record / fold layout.
- **Look-ahead-free**: every strategy evaluation at bar ``t`` uses only
  ``df.iloc[: t + 1]``.
- **Non-mutating**: the engine never mutates the caller's DataFrame or Strategy
  instance (the strategy is deep-copied once per run / per fold).
- **Safe on insufficient data**: returns a well-formed, zero-trade record.
- **Config-driven**: defaults come from ``BacktestConfig``
  (``sentinel/config.py``) with constructor overrides; ``config.yaml`` need not
  change.

``run()`` returns a metrics dict with a stable schema::

    profit_factor, trades (R-multiples), n_trades, win_rate,
    total_return_pct, annualized_return_pct, max_drawdown_pct,
    start, evaluated_bars, insufficient_data, reason

``cross_validate()`` (Phase 5.2) adds purged k-fold cross-validation over
contiguous, deterministic folds. Each fold's evaluation window is:
``[fold_start + purge_gap, fold_end - embargo]`` (bounded below by
``min_bars_for_entry``). The purge gap guarantees a margin between the previous
fold's test period and this fold's evaluated bars; the embargo drops the fold's
tail bars so no trade entered in a fold can realize a label inside the next
fold. Trades still open at ``eval_end`` are closed with an end-of-window
partial exit, so every fold's outcomes are confined to that fold — strictly no
train/test temporal leakage. Folds too small to satisfy purge + embargo are
returned as ``fold_too_small`` records rather than raising.
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

# Stable schema keys returned by BacktestEngine.cross_validate()
CV_KEYS = (
    "n_folds",
    "purge_gap",
    "embargo",
    "insufficient_data",
    "reason",
    "fold_bounds",
    "folds",
    "mean_profit_factor",
    "mean_total_return_pct",
)

# A single fold's record = RESULT_KEYS + fold bookkeeping.
FOLD_RECORD_KEYS = RESULT_KEYS + (
    "fold",
    "test_start",
    "test_end",
    "eval_start",
    "eval_end",
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


def _cv_empty(n_folds: int, purge_gap: int, embargo: int, reason: str) -> dict:
    """Well-formed cross_validate() record for insufficient inputs."""
    return {
        "n_folds": int(n_folds),
        "purge_gap": int(purge_gap),
        "embargo": int(embargo),
        "insufficient_data": True,
        "reason": reason,
        "fold_bounds": [],
        "folds": [],
        "mean_profit_factor": None,
        "mean_total_return_pct": None,
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
        trades, curve = self._simulate(local, df, start, len(df) - 1)
        evaluated_bars = len(df) - start
        return self._metrics(trades, curve, start, evaluated_bars)

    def _simulate(
        self, local, df: pd.DataFrame, start_bar: int, end_bar: int
    ) -> tuple:
        """Run the shared entry/exit simulation over bars ``[start_bar, end_bar]``.

        ``local`` is a strategy instance already deep-copied by the caller. Bars
        past ``end_bar`` are never read for entries or exits, and a position
        still open at ``end_bar`` is closed with an end-of-window partial exit —
        so a fold's outcomes can never leak into the following fold.
        """
        trades: list = []
        equity = self.initial_capital
        curve = [equity]
        in_pos = False
        entry_p = stop_p = target_p = 0.0

        for t in range(start_bar, end_bar + 1):
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
                elif t == end_bar:
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

        return trades, curve

    # ------------------------------------------------------ purged k-fold CV

    @staticmethod
    def fold_bounds(
        n_bars: int,
        n_folds: int,
        purge_gap: int = 0,
        embargo: int = 0,
        min_bars_for_entry: int = 0,
    ) -> list:
        """Deterministic contiguous folds over bar indices ``[0, n_bars)``.

        Fold ``i`` covers test bars ``[i*n//k, (i+1)*n//k - 1]``. Its evaluation
        window is ``[max(fold_start + purge_gap, min_bars_for_entry),
        fold_end - embargo]``. Returns one dict per fold with ``fold``,
        ``test_start``, ``test_end``, ``eval_start``, ``eval_end``. Purely
        deterministic: identical inputs always return identical bounds.
        """
        if n_bars <= 0:
            return []
        k = max(1, int(n_folds))
        bounds = []
        for i in range(k):
            f_start = (i * n_bars) // k
            f_end = ((i + 1) * n_bars) // k - 1
            eval_start = max(f_start + int(purge_gap), int(min_bars_for_entry))
            eval_end = f_end - int(embargo)
            bounds.append(
                {
                    "fold": i,
                    "test_start": f_start,
                    "test_end": f_end,
                    "eval_start": eval_start,
                    "eval_end": eval_end,
                }
            )
        return bounds

    def cross_validate(
        self,
        strategy,
        df: Optional[pd.DataFrame],
        n_folds: int = 5,
        purge_gap: int = 0,
        embargo: int = 0,
    ) -> dict:
        """Purged k-fold cross-validation of ``strategy`` over ``df``.

        The full bar range is split into ``n_folds`` deterministic contiguous
        test blocks. Each fold evaluates entries only on bars in
        ``[fold_start + purge_gap, fold_end - embargo]`` (bounded below by
        ``min_bars_for_entry``); positions open at ``eval_end`` receive an
        end-of-window partial exit. The purge gap and embargo therefore create a
        hard temporal separation between consecutive folds' evaluated bars
        (gap == ``purge_gap + embargo``) and every fold's trade outcomes stay
        inside the fold.

        Each fold is evaluated with a fresh deep copy of the strategy, so no
        strategy state flows between folds. Folds too small to satisfy
        purge + embargo are returned as ``fold_too_small`` records. Never raises
        on data problems; never mutates ``df`` or ``strategy``.
        """
        n_folds = int(n_folds)
        purge_gap = int(purge_gap)
        embargo = int(embargo)
        if n_folds < 2:
            raise ValueError("n_folds must be >= 2")
        if purge_gap < 0:
            raise ValueError("purge_gap must be >= 0")
        if embargo < 0:
            raise ValueError("embargo must be >= 0")

        if df is None or len(df) < self.min_bars_for_entry:
            return _cv_empty(n_folds, purge_gap, embargo, "insufficient_data")

        required = {"Close", "High", "Low"}
        if not required.issubset(df.columns):
            return _cv_empty(n_folds, purge_gap, embargo, "missing_ohlc_columns")

        bounds = self.fold_bounds(
            len(df), n_folds, purge_gap, embargo, self.min_bars_for_entry
        )

        folds = []
        for b in bounds:
            es, ee = b["eval_start"], b["eval_end"]
            if es > ee:
                rec = _empty_record("fold_too_small")
                rec["start"] = b["test_start"]
                rec["evaluated_bars"] = 0
            else:
                local = copy.deepcopy(strategy)
                trades, curve = self._simulate(local, df, es, ee)
                rec = self._metrics(trades, curve, es, ee - es + 1)
            rec["fold"] = b["fold"]
            rec["test_start"] = b["test_start"]
            rec["test_end"] = b["test_end"]
            rec["eval_start"] = es
            rec["eval_end"] = ee
            folds.append(rec)

        valid = [r for r in folds if not r["insufficient_data"]]
        if valid:
            mean_pf = round(
                sum(r["profit_factor"] for r in valid) / len(valid), 4
            )
            mean_tr = round(
                sum(r["total_return_pct"] for r in valid) / len(valid), 4
            )
        else:
            mean_pf = None
            mean_tr = None

        return {
            "n_folds": n_folds,
            "purge_gap": purge_gap,
            "embargo": embargo,
            "insufficient_data": False,
            "reason": None,
            "fold_bounds": bounds,
            "folds": folds,
            "mean_profit_factor": mean_pf,
            "mean_total_return_pct": mean_tr,
        }

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


__all__ = [
    "BacktestEngine",
    "RESULT_KEYS",
    "CV_KEYS",
    "FOLD_RECORD_KEYS",
    "TRADING_DAYS_PER_YEAR",
]
