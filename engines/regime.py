"""Market Regime Engine for SENTINEL PRO.

Detects the current market environment (regime) using a combination of:
- **Rule-based signals**: MA trend, breadth, volatility, momentum.
- **Regime classification**: bull, bear, sideways, transition.

Provides a composite ``regime_score`` (-100 to +100) and a ``regime_label``
for position sizing adjustments and risk management.

All methods are pure functions operating on pandas DataFrames. No network calls.
"""
import logging
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


class RegimeType(str, Enum):
    """Market regime classification."""
    BULL = "bull"
    BEAR = "bear"
    SIDEWAYS = "sideways"
    TRANSITION = "transition"


@dataclass
class RegimeResult:
    """Container for market regime analysis results."""
    regime: RegimeType
    score: int  # -100 to +100
    confidence: float  # 0.0 to 1.0
    signals: Dict[str, float]
    trend: str  # 'up', 'down', 'flat'
    breadth: str  # 'strong', 'weak', 'neutral'
    volatility: str  # 'low', 'high', 'normal'
    momentum: str  # 'positive', 'negative', 'neutral'

    def to_dict(self) -> Dict:
        return {
            "regime": self.regime.value,
            "score": self.score,
            "confidence": self.confidence,
            "signals": self.signals,
            "trend": self.trend,
            "breadth": self.breadth,
            "volatility": self.volatility,
            "momentum": self.momentum,
        }


class MarketRegimeEngine:
    """Rule-based market regime detection engine."""

    # --- Trend signals ---

    @staticmethod
    def ma_trend(
        df: pd.DataFrame,
        short_period: int = 50,
        long_period: int = 200,
    ) -> Dict[str, float]:
        """Analyze moving average trend signals.

        Returns dict with:
        - ma_short: current short MA value
        - ma_long: current long MA value
        - above_short: price above short MA (1.0 or 0.0)
        - above_long: price above long MA (1.0 or 0.0)
        - golden_cross: short MA above long MA (1.0 or 0.0)
        - score: -100 to +100 based on MA alignment
        """
        if df is None or df.empty or len(df) < long_period:
            return {"score": 0.0, "ma_short": None, "ma_long": None}

        close = df["Close"]
        ma_short = float(close.rolling(window=short_period).mean().iloc[-1])
        ma_long = float(close.rolling(window=long_period).mean().iloc[-1])
        price = float(close.iloc[-1])

        above_short = 1.0 if price > ma_short else 0.0
        above_long = 1.0 if price > ma_long else 0.0
        golden_cross = 1.0 if ma_short > ma_long else 0.0

        # Score: each signal contributes
        score = (above_short * 25) + (above_long * 25) + (golden_cross * 50)
        # Adjust for distance
        if ma_long > 0:
            dist_pct = (ma_short - ma_long) / ma_long
            score += np.clip(dist_pct * 200, -25, 25)

        return {
            "ma_short": round(ma_short, 4),
            "ma_long": round(ma_long, 4),
            "above_short": above_short,
            "above_long": above_long,
            "golden_cross": golden_cross,
            "score": round(np.clip(score, -100, 100), 2),
        }

    # --- Breadth signals ---

    @staticmethod
    def breadth_signal(
        df: pd.DataFrame,
        threshold_pct: float = 0.5,
    ) -> Dict[str, float]:
        """Analyze price breadth (how far above/below MAs).

        Returns dict with:
        - pct_above_20ma: % of bars above 20-day MA in last 20 bars
        - pct_above_50ma: % of bars above 50-day MA in last 50 bars
        - new_highs: number of new 20-day highs in last 20 bars
        - new_lows: number of new 20-day lows in last 20 bars
        - score: -100 to +100
        """
        if df is None or df.empty or len(df) < 50:
            return {"score": 0.0}

        close = df["Close"]
        high = df["High"]
        low = df["Low"]

        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()

        # % above MAs (last 20 bars)
        recent_close = close.iloc[-20:]
        recent_ma20 = ma20.iloc[-20:]
        pct_above_20 = float((recent_close > recent_ma20).sum() / 20 * 100)

        recent_ma50 = ma50.iloc[-20:]
        pct_above_50 = float((recent_close > recent_ma50).sum() / 20 * 100)

        # New highs/lows (20-day)
        rolling_high = high.rolling(20).max()
        rolling_low = low.rolling(20).min()
        recent_rh = rolling_high.iloc[-20:]
        recent_rl = rolling_low.iloc[-20:]
        new_highs = int((recent_close >= recent_rh * 0.99).sum())
        new_lows = int((recent_close <= recent_rl * 1.01).sum())

        # Score
        ma_score = ((pct_above_20 - 50) + (pct_above_50 - 50)) / 2
        hl_score = (new_highs - new_lows) / max(new_highs + new_lows, 1) * 50
        score = np.clip(ma_score + hl_score, -100, 100)

        return {
            "pct_above_20ma": round(pct_above_20, 2),
            "pct_above_50ma": round(pct_above_50, 2),
            "new_highs": new_highs,
            "new_lows": new_lows,
            "score": round(score, 2),
        }

    # --- Volatility signals ---

    @staticmethod
    def volatility_signal(
        df: pd.DataFrame,
        period: int = 20,
        lookback: int = 120,
    ) -> Dict[str, float]:
        """Analyze volatility regime.

        Returns dict with:
        - current_vol: current annualized volatility
        - vol_percentile: current vol percentile vs lookback
        - atr_pct: ATR as % of price
        - score: -100 (extreme high vol = bearish) to +100 (low vol = bullish)
        """
        if df is None or df.empty or len(df) < max(period, lookback):
            return {"score": 0.0}

        close = df["Close"]
        returns = close.pct_change().dropna()

        if len(returns) < lookback:
            return {"score": 0.0}

        # Current volatility (annualized)
        current_vol = float(returns.iloc[-period:].std() * np.sqrt(252) * 100)

        # Historical volatility for percentile
        hist_vol = returns.rolling(period).std().dropna() * np.sqrt(252) * 100
        if len(hist_vol) < lookback:
            lookback = len(hist_vol)

        recent_vol = hist_vol.iloc[-lookback:]
        vol_percentile = float((recent_vol < current_vol).sum() / len(recent_vol) * 100)

        # ATR %
        high, low = df["High"], df["Low"]
        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)
        atr = tr.rolling(period).mean()
        atr_pct = float((atr.iloc[-1] / close.iloc[-1]) * 100) if close.iloc[-1] > 0 else 0.0

        # Score: low vol is bullish, high vol is bearish
        # Sweet spot: 10th-40th percentile is bullish, >70th is bearish
        if vol_percentile <= 20:
            score = 60 + (20 - vol_percentile) * 2
        elif vol_percentile <= 40:
            score = 20 + (40 - vol_percentile) * 2
        elif vol_percentile <= 60:
            score = 0
        elif vol_percentile <= 80:
            score = -(vol_percentile - 60) * 2
        else:
            score = -40 - (vol_percentile - 80) * 3

        return {
            "current_vol": round(current_vol, 2),
            "vol_percentile": round(vol_percentile, 2),
            "atr_pct": round(atr_pct, 4),
            "score": round(np.clip(score, -100, 100), 2),
        }

    # --- Momentum signals ---

    @staticmethod
    def momentum_signal(
        df: pd.DataFrame,
        rsi_period: int = 14,
        roc_period: int = 20,
    ) -> Dict[str, float]:
        """Analyze momentum (RSI + rate of change).

        Returns dict with:
        - rsi: current RSI
        - roc: rate of change over roc_period
        - score: -100 to +100
        """
        if df is None or df.empty or len(df) < max(rsi_period, roc_period) + 1:
            return {"score": 0.0}

        close = df["Close"]

        # RSI
        delta = close.diff()
        gain = delta.where(delta > 0, 0.0).rolling(rsi_period).mean()
        loss = (-delta.where(delta < 0, 0.0)).rolling(rsi_period).mean()
        rs = gain / loss.replace(0, 1e-10)
        rsi = 100 - (100 / (1 + rs))
        current_rsi = float(rsi.iloc[-1])

        # Rate of Change
        roc = (close.iloc[-1] / close.iloc[-roc_period] - 1) * 100

        # Score
        # RSI: 30-70 is neutral, >70 is overbought (slightly negative), <30 is oversold (slightly positive)
        if current_rsi > 70:
            rsi_score = -(current_rsi - 70) * 2
        elif current_rsi < 30:
            rsi_score = (30 - current_rsi) * 2
        else:
            rsi_score = (current_rsi - 50) * 0.5

        # ROC: positive is bullish, negative is bearish
        roc_score = np.clip(roc * 5, -50, 50)

        score = np.clip(rsi_score + roc_score, -100, 100)

        return {
            "rsi": round(current_rsi, 2),
            "roc": round(roc, 4),
            "score": round(score, 2),
        }

    # --- Composite regime analysis ---

    @classmethod
    def analyze(
        cls,
        df: pd.DataFrame,
        weights: Optional[Dict[str, float]] = None,
    ) -> RegimeResult:
        """Full market regime analysis.

        Parameters
        ----------
        df : DataFrame
            OHLCV data for a market index (e.g., SPY, QQQ).
        weights : dict, optional
            Signal weights: {trend, breadth, volatility, momentum}.
            Default: equal weights.

        Returns
        -------
        RegimeResult
        """
        default_weights = {
            "trend": 0.35,
            "breadth": 0.25,
            "volatility": 0.20,
            "momentum": 0.20,
        }
        w = weights or default_weights

        trend = cls.ma_trend(df)
        breadth = cls.breadth_signal(df)
        volatility = cls.volatility_signal(df)
        momentum = cls.momentum_signal(df)

        signals = {
            "trend_score": trend["score"],
            "breadth_score": breadth["score"],
            "volatility_score": volatility["score"],
            "momentum_score": momentum["score"],
        }

        # Weighted composite score
        composite = (
            trend["score"] * w["trend"]
            + breadth["score"] * w["breadth"]
            + volatility["score"] * w["volatility"]
            + momentum["score"] * w["momentum"]
        )
        score = int(round(np.clip(composite, -100, 100)))

        # Confidence: based on signal agreement
        scores = [trend["score"], breadth["score"], volatility["score"], momentum["score"]]
        positive = sum(1 for s in scores if s > 10)
        negative = sum(1 for s in scores if s < -10)
        agreement = max(positive, negative) / len(scores)
        confidence = round(agreement, 2)

        # Classify regime
        if score >= 30:
            regime = RegimeType.BULL
        elif score <= -30:
            regime = RegimeType.BEAR
        elif abs(score) <= 10:
            regime = RegimeType.SIDEWAYS
        else:
            regime = RegimeType.TRANSITION

        # Sub-classifications
        trend_label = "up" if trend["score"] > 15 else "down" if trend["score"] < -15 else "flat"
        breadth_label = "strong" if breadth["score"] > 15 else "weak" if breadth["score"] < -15 else "neutral"
        vol_label = "low" if volatility["score"] > 20 else "high" if volatility["score"] < -20 else "normal"
        mom_label = "positive" if momentum["score"] > 15 else "negative" if momentum["score"] < -15 else "neutral"

        return RegimeResult(
            regime=regime,
            score=score,
            confidence=confidence,
            signals=signals,
            trend=trend_label,
            breadth=breadth_label,
            volatility=vol_label,
            momentum=mom_label,
        )

    @classmethod
    def position_size_multiplier(cls, regime: RegimeType) -> float:
        """Get position size multiplier based on regime.

        - Bull: 1.0 (full size)
        - Sideways: 0.75 (reduced)
        - Transition: 0.5 (half size)
        - Bear: 0.25 (minimal)
        """
        return {
            RegimeType.BULL: 1.0,
            RegimeType.SIDEWAYS: 0.75,
            RegimeType.TRANSITION: 0.5,
            RegimeType.BEAR: 0.25,
        }.get(regime, 0.5)

    @classmethod
    def risk_adjusted_stop(cls, regime: RegimeType, base_stop: float) -> float:
        """Widen stops in high-risk regimes.

        Bear/transition regimes get 1.5x wider stops; bull gets normal.
        """
        multiplier = {
            RegimeType.BULL: 1.0,
            RegimeType.SIDEWAYS: 1.1,
            RegimeType.TRANSITION: 1.3,
            RegimeType.BEAR: 1.5,
        }.get(regime, 1.2)
        return round(base_stop * multiplier, 4)


__all__ = [
    "RegimeType",
    "RegimeResult",
    "MarketRegimeEngine",
]
