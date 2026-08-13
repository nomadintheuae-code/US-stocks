"""Minervini Trend Template strategy.

Implements Mark Minervini's 8-point trend template as a Strategy that
composes only trailing moving averages, trailing 52-week price extremes,
and an optional cross-sectional RS rating. It is a QUALIFIER: it
determines whether a stock is in a strong, stage-2 style uptrend.

This is a STRATEGY, not an indicator. It is additive and opt-in.
Existing VCPIndicator / VCPAnalyzer / StrategyValidator / RSIndicator /
RelativeStrengthRanking / VCPBreakoutStrategy behavior is completely
unchanged.
"""

from typing import List, Optional

import pandas as pd

from config import CONFIG
from engines.strategies.base import Strategy


class MinerviniTrendTemplate(Strategy):
    """Mark Minervini's 8-point trend template qualifier.

    Evaluated on the final bar of ``df`` using only historical data
    (trailing rolling means and trailing 52-week extremes — structurally
    look-ahead-free).

    Criteria
    --------
    1. Close above the 150-day MA
    2. Close above the 200-day MA
    3. 150-day MA above the 200-day MA
    4. 200-day MA trending up for at least ``min_uptrend_bars`` bars
       (default 21 ≈ one trading month)
    5. 50-day MA above both the 150-day and 200-day MAs
    6. Close above the 50-day MA
    7. Close at least ``low_pct`` (30%) above the 52-week low
    8. Close within ``1 - high_pct`` (25%) of the 52-week high
    9. RS rating >= ``min_rs_threshold`` (70), only when ``rs_rating``
       is provided at ``calculate()`` time. Without a rating the
       criterion is recorded as ``None`` (not assessed, not counted).

    Scoring
    -------
    ``score`` = number of PASSED criteria out of those assessed
    (0-8; 0-7 when ``rs_rating`` is ``None``). ``is_actionable()`` is
    True only when every assessed criterion passes.
    """

    DEFAULT_MA_PERIODS = (50, 150, 200)
    DEFAULT_MIN_UPTREND_BARS = 21
    DEFAULT_MIN_DATA_BARS = 252
    DEFAULT_MIN_RS_THRESHOLD = 70
    DEFAULT_LOW_PCT = 0.30
    DEFAULT_HIGH_PCT = 0.75
    DEFAULT_ATR_PERIOD = 14

    def __init__(
        self,
        ma_periods: Optional[tuple] = None,
        min_uptrend_bars: Optional[int] = None,
        min_data_bars: Optional[int] = None,
        min_rs_threshold: Optional[int] = None,
        low_pct: Optional[float] = None,
        high_pct: Optional[float] = None,
        stop_mult: Optional[float] = None,
        target_mult: Optional[float] = None,
    ):
        self.ma_periods = tuple(ma_periods if ma_periods is not None else self.DEFAULT_MA_PERIODS)
        self.min_uptrend_bars = min_uptrend_bars if min_uptrend_bars is not None else self.DEFAULT_MIN_UPTREND_BARS
        self.min_data_bars = min_data_bars if min_data_bars is not None else self.DEFAULT_MIN_DATA_BARS
        self.min_rs_threshold = min_rs_threshold if min_rs_threshold is not None else self.DEFAULT_MIN_RS_THRESHOLD
        self.low_pct = low_pct if low_pct is not None else self.DEFAULT_LOW_PCT
        self.high_pct = high_pct if high_pct is not None else self.DEFAULT_HIGH_PCT
        self.stop_mult = float(
            stop_mult if stop_mult is not None else CONFIG["STOP_LOSS_ATR"]
        )
        self.target_mult = float(
            target_mult if target_mult is not None else CONFIG["TARGET_R_MULTIPLE"]
        )
        self._validate_config()
        self._reset()

    def _validate_config(self) -> None:
        if len(self.ma_periods) != 3:
            raise ValueError(f"ma_periods must have exactly 3 periods, got {self.ma_periods}")
        if any(p < 1 for p in self.ma_periods):
            raise ValueError("ma_periods must all be >= 1")
        if self.min_uptrend_bars < 1:
            raise ValueError(f"min_uptrend_bars must be >= 1, got {self.min_uptrend_bars}")
        if self.min_data_bars < 1:
            raise ValueError(f"min_data_bars must be >= 1, got {self.min_data_bars}")
        if self.min_rs_threshold < 0 or self.min_rs_threshold > 100:
            raise ValueError(f"min_rs_threshold must be in [0, 100], got {self.min_rs_threshold}")
        if self.low_pct <= 0:
            raise ValueError(f"low_pct must be > 0, got {self.low_pct}")
        if self.high_pct <= 0 or self.high_pct > 1:
            raise ValueError(f"high_pct must be in (0, 1], got {self.high_pct}")

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
        self._criteria: dict = {}

    # ------------------------------------------------------------------
    # Strategy ABC
    # ------------------------------------------------------------------

    def calculate(self, df: pd.DataFrame, rs_rating: Optional[int] = None) -> dict:
        """Compute the Minervini trend template for the final bar of *df*.

        ``rs_rating`` is the optional cross-sectional RS percentile
        (1-100, as produced by ``RSAnalyzer.assign_percentiles``). When
        omitted, criterion 9 is recorded as ``None`` and not counted.

        Returns a dict with at minimum: ``score``, ``signals``, ``atr``.
        When there is insufficient data (< ``min_data_bars`` bars, i.e.
        252), missing columns, or an unusable ATR, returns a safe
        non-actionable result (score 0, empty signals, entry/stop/target
        all ``0.0``).
        """
        self._reset()

        if df is None or not isinstance(df, pd.DataFrame):
            return self.result()
        if len(df) < self.min_data_bars:
            return self.result()
        for col in ("Open", "High", "Low", "Close", "Volume"):
            if col not in df.columns:
                return self.result()

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        price = float(close.iloc[-1])

        # ── ATR ─────────────────────────────────────────────────────
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return self.result()

        # ── Trailing moving averages (look-ahead-free) ──────────────
        ma_short, ma_mid, ma_long = self.ma_periods
        ma_short = float(close.rolling(ma_short).mean().iloc[-1])
        ma_mid = float(close.rolling(ma_mid).mean().iloc[-1])
        ma_long = float(close.rolling(ma_long).mean().iloc[-1])

        ma_long_prev = float(close.rolling(self.ma_periods[2]).mean().iloc[-1 - self.min_uptrend_bars])

        # ── Trailing 52-week extremes (252 bars) ────────────────────
        high52 = float(high.iloc[-252:].max())
        low52 = float(low.iloc[-252:].min())

        # ── Criteria ────────────────────────────────────────────────
        criteria = {
            "price_above_150ma": bool(price > ma_mid),
            "price_above_200ma": bool(price > ma_long),
            "ma150_above_ma200": bool(ma_mid > ma_long),
            "ma200_uptrend": bool(ma_long > ma_long_prev),
            "ma50_above_ma150_ma200": bool(ma_short > ma_mid and ma_short > ma_long),
            "price_above_50ma": bool(price > ma_short),
            "above_30pct_52w_low": bool(price >= low52 * (1 + self.low_pct)),
            "within_25pct_52w_high": bool(price >= high52 * self.high_pct),
            "rs_rating_ge_70": (
                bool(rs_rating >= self.min_rs_threshold)
                if rs_rating is not None else None
            ),
        }

        assessed = {k: v for k, v in criteria.items() if v is not None}
        passed = sum(1 for v in assessed.values() if v)
        total = len(assessed)
        actionable = total > 0 and passed == total

        # ── Signals ─────────────────────────────────────────────────
        signals = []
        if criteria["price_above_150ma"] and criteria["price_above_200ma"]:
            signals.append("Price Above 150/200-day MA")
        if criteria["ma150_above_ma200"]:
            signals.append("MA150 Above MA200")
        if criteria["ma200_uptrend"]:
            signals.append("MA200 Uptrending")
        if criteria["ma50_above_ma150_ma200"] and criteria["price_above_50ma"]:
            signals.append("MA50 Above MA150/MA200, Price Above MA50")
        if criteria["above_30pct_52w_low"]:
            signals.append("30%+ Above 52-week Low")
        if criteria["within_25pct_52w_high"]:
            signals.append("Within 25% of 52-week High")
        if criteria["rs_rating_ge_70"] is True:
            signals.append("RS Rating >= 70")
        signals.append("Trend Template Pass" if actionable else "Trend Template Fail")

        entry = round(price, 2)
        stop = round(entry - atr * self.stop_mult, 2)
        target = round(entry + (entry - stop) * self.target_mult, 2)

        self._score = int(passed)
        self._signals = signals
        self._entry = entry
        self._stop = stop
        self._target = target
        self._actionable = actionable
        self._criteria = criteria

        return self.result(atr=atr, passed_count=passed, total_count=total)

    def get_score(self) -> int:
        """Return the number of passed criteria (0-8)."""
        return self._score

    def get_signals(self) -> List[str]:
        """Return list of human-readable signal strings."""
        return list(self._signals)

    def get_entry_stop_target(self) -> tuple:
        """Return ``(entry_price, stop_price, target_price)``."""
        return self._entry, self._stop, self._target

    def is_actionable(self) -> bool:
        """True when every assessed trend-template criterion passes."""
        return self._actionable

    # ------------------------------------------------------------------
    # Result assembly
    # ------------------------------------------------------------------

    def result(
        self,
        atr: float = 0.0,
        passed_count: int = 0,
        total_count: int = 0,
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
            "passed_count": int(passed_count),
            "total_count": int(total_count),
            "criteria": dict(self._criteria),
        }
