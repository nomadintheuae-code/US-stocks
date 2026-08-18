"""Technical pattern recognition for SENTINEL PRO.

Provides three pattern engines:
- ``FibonacciEngine`` — Fibonacci retracement/extension levels from swing highs/lows.
- ``CandlestickEngine`` — Classic single/double candlestick pattern detection.
- ``BBSqueezeEngine`` — Bollinger Band squeeze detection (low volatility breakout).

All methods are pure functions operating on pandas DataFrames. No network calls.
"""
import logging
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ==============================================================================
# Fibonacci Retracement / Extension
# ==============================================================================

class FibonacciEngine:
    """Compute Fibonacci retracement and extension levels from price swings."""

    RETRACEMENT_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]
    EXTENSION_RATIOS = [1.272, 1.618, 2.0, 2.618]

    @staticmethod
    def find_swing_highs_lows(
        df: pd.DataFrame,
        lookback: int = 20,
    ) -> Tuple[Optional[float], Optional[float]]:
        """Find the most recent significant swing high and swing low.

        Parameters
        ----------
        df : DataFrame
            OHLCV data with 'High' and 'Low' columns.
        lookback : int
            Number of bars to search for swings.

        Returns
        -------
        tuple of (swing_high, swing_low) or (None, None) if insufficient data.
        """
        if df is None or df.empty or len(df) < lookback:
            return None, None

        highs = df["High"].iloc[-lookback:]
        lows = df["Low"].iloc[-lookback:]

        swing_high = float(highs.max())
        swing_low = float(lows.min())

        return swing_high, swing_low

    @classmethod
    def retracement_levels(
        cls,
        swing_high: float,
        swing_low: float,
    ) -> Dict[float, float]:
        """Compute Fibonacci retracement levels.

        Parameters
        ----------
        swing_high : float
            The swing high price.
        swing_low : float
            The swing low price.

        Returns
        -------
        dict
            ``{ratio: price_level}`` for each retracement ratio.
        """
        diff = swing_high - swing_low
        return {
            ratio: round(swing_high - diff * ratio, 4)
            for ratio in cls.RETRACEMENT_RATIOS
        }

    @classmethod
    def extension_levels(
        cls,
        swing_high: float,
        swing_low: float,
    ) -> Dict[float, float]:
        """Compute Fibonacci extension levels (beyond the swing range).

        Returns
        -------
        dict
            ``{ratio: price_level}`` for each extension ratio.
        """
        diff = swing_high - swing_low
        return {
            ratio: round(swing_high + diff * (ratio - 1.0), 4)
            for ratio in cls.EXTENSION_RATIOS
        }

    @classmethod
    def nearest_fib(
        cls,
        price: float,
        swing_high: float,
        swing_low: float,
    ) -> Tuple[float, float]:
        """Find the nearest Fibonacci level to current price and its distance %.

        Parameters
        ----------
        price : float
            Current price.
        swing_high : float
            Swing high price.
        swing_low : float
            Swing low price.

        Returns
        -------
        tuple of (nearest_level, distance_pct)
            ``distance_pct`` is negative when price is below level, positive above.
        """
        levels = cls.retracement_levels(swing_high, swing_low)
        min_dist = float("inf")
        nearest = price

        for _ratio, level in levels.items():
            dist = abs(price - level)
            if dist < min_dist:
                min_dist = dist
                nearest = level

        distance_pct = (price - nearest) / nearest if nearest != 0 else 0.0
        return round(nearest, 4), round(distance_pct, 6)

    @classmethod
    def analyze(
        cls,
        df: pd.DataFrame,
        lookback: int = 60,
        current_price: Optional[float] = None,
    ) -> Dict:
        """Full Fibonacci analysis on a DataFrame.

        Returns
        -------
        dict with keys: swing_high, swing_low, retracements, extensions,
        nearest_level, nearest_distance_pct, support_levels, resistance_levels.
        """
        swing_high, swing_low = cls.find_swing_highs_lows(df, lookback)
        if swing_high is None or swing_low is None:
            return {
                "swing_high": None,
                "swing_low": None,
                "retracements": {},
                "extensions": {},
                "nearest_level": None,
                "nearest_distance_pct": None,
                "support_levels": [],
                "resistance_levels": [],
            }

        retracements = cls.retracement_levels(swing_high, swing_low)
        extensions = cls.extension_levels(swing_high, swing_low)

        if current_price is None and df is not None and not df.empty:
            current_price = float(df["Close"].iloc[-1])

        nearest_level = None
        nearest_distance_pct = None
        if current_price is not None:
            nearest_level, nearest_distance_pct = cls.nearest_fib(
                current_price, swing_high, swing_low
            )

        # Support = fib levels below current price
        # Resistance = fib levels above current price
        support = sorted(
            [v for v in retracements.values() if current_price and v < current_price],
            reverse=True,
        )
        resistance = sorted(
            [v for v in retracements.values() if current_price and v > current_price],
        )

        return {
            "swing_high": swing_high,
            "swing_low": swing_low,
            "retracements": retracements,
            "extensions": extensions,
            "nearest_level": nearest_level,
            "nearest_distance_pct": nearest_distance_pct,
            "support_levels": support[:3],
            "resistance_levels": resistance[:3],
        }


# ==============================================================================
# Candlestick Patterns
# ==============================================================================

class CandlestickEngine:
    """Detect classic candlestick patterns from OHLCV data."""

    @staticmethod
    def _body(o: float, h: float, l: float, c: float) -> Tuple[float, float, float]:
        """Return (body, upper_shadow, lower_shadow)."""
        body = abs(c - o)
        upper_shadow = h - max(o, c)
        lower_shadow = min(o, c) - l
        return body, upper_shadow, lower_shadow

    @staticmethod
    def _range(h: float, l: float) -> float:
        return h - l if h > l else 1e-10

    @classmethod
    def doji(cls, o: float, h: float, l: float, c: float, threshold: float = 0.1) -> bool:
        """Doji: body is very small relative to range."""
        body, _, _ = cls._body(o, h, l, c)
        rng = cls._range(h, l)
        return body / rng < threshold

    @classmethod
    def hammer(cls, o: float, h: float, l: float, c: float) -> bool:
        """Hammer: small body at top, long lower shadow (>= 2x body), minimal upper shadow."""
        body, upper, lower = cls._body(o, h, l, c)
        if body < 1e-10:
            return False
        return lower >= 2.0 * body and upper <= body * 0.3

    @classmethod
    def inverted_hammer(cls, o: float, h: float, l: float, c: float) -> bool:
        """Inverted Hammer: small body at bottom, long upper shadow (>= 2x body)."""
        body, upper, lower = cls._body(o, h, l, c)
        if body < 1e-10:
            return False
        return upper >= 2.0 * body and lower <= body * 0.3

    @classmethod
    def shooting_star(cls, o: float, h: float, l: float, c: float) -> bool:
        """Shooting Star: same shape as inverted hammer but after uptrend (caller checks trend)."""
        return cls.inverted_hammer(o, h, l, c)

    @classmethod
    def marubozu(cls, o: float, h: float, l: float, c: float, threshold: float = 0.9) -> bool:
        """Marubozu: body covers almost entire range (very small/no shadows)."""
        body, upper, lower = cls._body(o, h, l, c)
        rng = cls._range(h, l)
        if rng < 1e-10:
            return False
        return body / rng >= threshold

    @classmethod
    def engulfing(cls, o1: float, c1: float, o2: float, c2: float) -> str:
        """Two-bar engulfing pattern detection.

        Returns: 'bullish', 'bearish', or 'none'.
        """
        # Bullish engulfing: bearish bar then larger bullish bar
        if c1 < o1 and c2 > o2:
            if o2 <= c1 and c2 >= o1:
                return "bullish"
        # Bearish engulfing: bullish bar then larger bearish bar
        if c1 > o1 and c2 < o2:
            if o2 >= c1 and c2 <= o1:
                return "bearish"
        return "none"

    @classmethod
    def detect(cls, df: pd.DataFrame, lookback: int = 5) -> List[Dict]:
        """Detect candlestick patterns on the last N bars.

        Parameters
        ----------
        df : DataFrame
            OHLCV data with Open, High, Low, Close columns.
        lookback : int
            Number of recent bars to analyze.

        Returns
        -------
        list of dict
            Each dict has keys: bar_index, pattern, type (bullish/bearish/neutral).
        """
        if df is None or df.empty or len(df) < max(lookback, 2):
            return []

        patterns: List[Dict] = []
        recent = df.iloc[-lookback:]

        for i in range(len(recent)):
            row = recent.iloc[i]
            o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            bar_idx = len(df) - lookback + i

            if cls.doji(o, h, l, c):
                patterns.append({"bar_index": bar_idx, "pattern": "doji", "type": "neutral"})

            if cls.hammer(o, h, l, c):
                patterns.append({"bar_index": bar_idx, "pattern": "hammer", "type": "bullish"})

            if cls.inverted_hammer(o, h, l, c):
                patterns.append({"bar_index": bar_idx, "pattern": "inverted_hammer", "type": "bullish"})

            if cls.marubozu(o, h, l, c):
                color = "bullish" if c > o else "bearish"
                patterns.append({"bar_index": bar_idx, "pattern": "marubozu", "type": color})

            # Two-bar patterns (need previous bar)
            if i > 0:
                prev = recent.iloc[i - 1]
                o1, c1 = float(prev["Open"]), float(prev["Close"])
                eng = cls.engulfing(o1, c1, o, c)
                if eng != "none":
                    patterns.append({"bar_index": bar_idx, "pattern": "engulfing", "type": eng})

        return patterns

    @classmethod
    def summary(cls, df: pd.DataFrame, lookback: int = 5) -> Dict:
        """Summarize candlestick patterns: counts by type."""
        patterns = cls.detect(df, lookback)
        counts = {"bullish": 0, "bearish": 0, "neutral": 0}
        names = {"bullish": [], "bearish": [], "neutral": []}

        for p in patterns:
            t = p["type"]
            counts[t] = counts.get(t, 0) + 1
            names[t].append(p["pattern"])

        return {
            "total": len(patterns),
            "counts": counts,
            "patterns": names,
            "bias": (
                "bullish" if counts["bullish"] > counts["bearish"]
                else "bearish" if counts["bearish"] > counts["bullish"]
                else "neutral"
            ),
        }


# ==============================================================================
# Bollinger Band Squeeze
# ==============================================================================

class BBSqueezeEngine:
    """Detect Bollinger Band squeeze (low volatility expansion precursor)."""

    @staticmethod
    def compute_bb(
        df: pd.DataFrame,
        period: int = 20,
        num_std: float = 2.0,
    ) -> Optional[pd.DataFrame]:
        """Compute Bollinger Bands.

        Returns DataFrame with columns: bb_mid, bb_upper, bb_lower, bb_width.
        """
        if df is None or df.empty or len(df) < period:
            return None

        close = df["Close"]
        bb_mid = close.rolling(window=period).mean()
        bb_std = close.rolling(window=period).std()
        bb_upper = bb_mid + num_std * bb_std
        bb_lower = bb_mid - num_std * bb_std

        # Width: normalized by mid (percent)
        bb_width = ((bb_upper - bb_lower) / bb_mid) * 100

        return pd.DataFrame({
            "bb_mid": bb_mid,
            "bb_upper": bb_upper,
            "bb_lower": bb_lower,
            "bb_width": bb_width,
        }, index=df.index)

    @staticmethod
    def keltter_channel_width(
        df: pd.DataFrame,
        period: int = 20,
        atr_period: int = 10,
    ) -> Optional[pd.Series]:
        """Compute Keltner Channel width as alternative squeeze measure."""
        if df is None or df.empty or len(df) < max(period, atr_period):
            return None

        close = df["Close"]
        ema = close.ewm(span=period, adjust=False).mean()

        # ATR
        high, low, prev_close = df["High"], df["Low"], df["Close"].shift(1)
        tr = pd.concat([
            high - low,
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(window=atr_period).mean()

        upper = ema + 1.5 * atr
        lower = ema - 1.5 * atr
        width = ((upper - lower) / ema) * 100

        return width

    @classmethod
    def is_squeezing(
        cls,
        df: pd.DataFrame,
        bb_period: int = 20,
        bb_std: float = 2.0,
        lookback: int = 120,
        percentile_threshold: float = 20.0,
    ) -> Dict:
        """Detect if Bollinger Bands are in squeeze (narrowest X% of lookback).

        Parameters
        ----------
        df : DataFrame
            OHLCV data.
        bb_period : int
            Bollinger Band moving average period.
        bb_std : float
            Number of standard deviations.
        lookback : int
            Historical window to compute percentile against.
        percentile_threshold : float
            If current width is below this percentile, it's a squeeze.

        Returns
        -------
        dict with keys: squeezing, current_width, percentile, bb_widths, status.
        """
        bb = cls.compute_bb(df, bb_period, bb_std)
        if bb is None or bb.empty:
            return {
                "squeezing": False,
                "current_width": None,
                "percentile": None,
                "bb_widths": None,
                "status": "insufficient_data",
            }

        widths = bb["bb_width"].dropna()
        if len(widths) < lookback:
            lookback = len(widths)

        if lookback < 20:
            return {
                "squeezing": False,
                "current_width": None,
                "percentile": None,
                "bb_widths": None,
                "status": "insufficient_data",
            }

        current_width = float(widths.iloc[-1])
        historical = widths.iloc[-lookback:]
        percentile = float((historical < current_width).sum() / len(historical) * 100)

        squeezing = percentile <= percentile_threshold

        if squeezing:
            status = "squeeze_active"
        elif percentile <= percentile_threshold * 2:
            status = "narrowing"
        else:
            status = "expanded"

        return {
            "squeezing": squeezing,
            "current_width": round(current_width, 4),
            "percentile": round(percentile, 2),
            "bb_widths": widths.tolist()[-20:],
            "status": status,
        }

    @classmethod
    def analyze(
        cls,
        df: pd.DataFrame,
        bb_period: int = 20,
        bb_std: float = 2.0,
        kc_period: int = 20,
        kc_atr_period: int = 10,
    ) -> Dict:
        """Full BB squeeze analysis including Keltner Channel confirmation.

        A true squeeze occurs when BB is inside KC (low vol + tight range).

        Returns
        -------
        dict with squeeze status, BB width, KC width, confirmed flag.
        """
        squeeze_info = cls.is_squeezing(df, bb_period, bb_std)

        kc_width = cls.keltter_channel_width(df, kc_period, kc_atr_period)
        kc_current = None
        confirmed = False

        if kc_width is not None and not kc_width.empty:
            kc_current = round(float(kc_width.iloc[-1]), 4)
            bb_series = cls.compute_bb(df, bb_period, bb_std)
            if bb_series is not None and not bb_series.empty:
                bb_w = float(bb_series["bb_width"].iloc[-1])
                # Squeeze confirmed when BB width < KC width
                confirmed = bb_w < kc_current

        return {
            **squeeze_info,
            "keltner_width": kc_current,
            "squeeze_confirmed": confirmed,
        }


__all__ = [
    "FibonacciEngine",
    "CandlestickEngine",
    "BBSqueezeEngine",
]
