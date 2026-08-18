"""Enhanced Risk Management for SENTINEL PRO.

Provides portfolio-level and per-position risk analysis:
- **PositionSizer** — ATR-based position sizing with regime adjustments.
- **PortfolioRisk** — Portfolio heat, correlation, concentration checks.
- **StopManager** — Dynamic trailing stop and time-based stop logic.

All methods are pure functions. No network calls.
"""
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


# ==============================================================================
# Position Sizer
# ==============================================================================

@dataclass
class PositionSize:
    """Result of position sizing calculation."""
    shares: int
    dollar_amount: float
    risk_amount: float
    risk_pct: float
    atr: float
    stop_distance: float
    regime_adjusted: bool

    def to_dict(self) -> Dict:
        return {
            "shares": self.shares,
            "dollar_amount": round(self.dollar_amount, 2),
            "risk_amount": round(self.risk_amount, 2),
            "risk_pct": round(self.risk_pct, 4),
            "atr": round(self.atr, 4),
            "stop_distance": round(self.stop_distance, 4),
            "regime_adjusted": self.regime_adjusted,
        }


class PositionSizer:
    """ATR-based position sizing with regime awareness."""

    @staticmethod
    def calculate_atr(
        df: pd.DataFrame,
        period: int = 14,
    ) -> Optional[float]:
        """Calculate Average True Range.

        Returns ATR value or None if insufficient data.
        """
        if df is None or df.empty or len(df) < period + 1:
            return None

        high = df["High"]
        low = df["Low"]
        close = df["Close"]

        tr = pd.concat([
            high - low,
            (high - close.shift(1)).abs(),
            (low - close.shift(1)).abs(),
        ], axis=1).max(axis=1)

        return float(tr.rolling(window=period).mean().iloc[-1])

    @classmethod
    def size_position(
        cls,
        df: pd.DataFrame,
        capital: float,
        risk_pct: float = 0.015,
        stop_atr_mult: float = 2.0,
        regime_mult: float = 1.0,
        atr_period: int = 14,
        min_shares: int = 1,
    ) -> Optional[PositionSize]:
        """Calculate position size based on ATR risk.

        Parameters
        ----------
        df : DataFrame
            OHLCV data.
        capital : float
            Total capital in USD.
        risk_pct : float
            Max risk per trade as fraction of capital (e.g. 0.015 = 1.5%).
        stop_atr_mult : float
            Stop loss distance in ATR multiples.
        regime_mult : float
            Regime-based adjustment (0.25 to 1.0).
        atr_period : int
            ATR calculation period.
        min_shares : int
            Minimum shares to buy.

        Returns
        -------
        PositionSize or None
        """
        if df is None or df.empty:
            return None

        atr = cls.calculate_atr(df, atr_period)
        if atr is None or atr <= 0:
            return None

        price = float(df["Close"].iloc[-1])
        if price <= 0:
            return None

        # Risk amount per trade
        risk_amount = capital * risk_pct * regime_mult
        stop_distance = atr * stop_atr_mult

        # Shares: risk_amount / stop_distance
        raw_shares = risk_amount / stop_distance if stop_distance > 0 else 0
        shares = max(int(raw_shares), min_shares)

        # Check if shares * price exceeds capital
        dollar_amount = shares * price
        if dollar_amount > capital * 0.95:
            shares = int(capital * 0.95 / price)
            dollar_amount = shares * price

        actual_risk = shares * stop_distance
        actual_risk_pct = actual_risk / capital if capital > 0 else 0

        return PositionSize(
            shares=shares,
            dollar_amount=dollar_amount,
            risk_amount=actual_risk,
            risk_pct=actual_risk_pct,
            atr=atr,
            stop_distance=stop_distance,
            regime_adjusted=regime_mult != 1.0,
        )


# ==============================================================================
# Portfolio Risk
# ==============================================================================

@dataclass
class PortfolioRiskResult:
    """Portfolio-level risk analysis."""
    total_heat: float  # sum of risk amounts as % of capital
    position_count: int
    sector_concentration: Dict[str, int]
    max_sector_pct: float
    correlation_warnings: List[str]
    risk_level: str  # 'low', 'medium', 'high', 'critical'

    def to_dict(self) -> Dict:
        return {
            "total_heat": round(self.total_heat, 4),
            "position_count": self.position_count,
            "sector_concentration": self.sector_concentration,
            "max_sector_pct": round(self.max_sector_pct, 4),
            "correlation_warnings": self.correlation_warnings,
            "risk_level": self.risk_level,
        }


class PortfolioRisk:
    """Portfolio-level risk management."""

    @staticmethod
    def calculate_heat(
        positions: List[Dict],
        capital: float,
    ) -> float:
        """Calculate total portfolio heat (total risk as % of capital).

        Parameters
        ----------
        positions : list of dict
            Each position must have 'risk_amount' or ('shares', 'stop_distance').
        capital : float
            Total capital.

        Returns
        -------
        float
            Total heat as percentage (0.0 to 1.0+).
        """
        if not positions or capital <= 0:
            return 0.0

        total_risk = 0.0
        for pos in positions:
            risk = pos.get("risk_amount")
            if risk is None:
                shares = pos.get("shares", 0)
                stop_dist = pos.get("stop_distance", 0)
                risk = shares * stop_dist
            total_risk += risk

        return total_risk / capital

    @staticmethod
    def sector_concentration(
        positions: List[Dict],
    ) -> Tuple[Dict[str, int], float]:
        """Analyze sector concentration.

        Returns
        -------
        tuple of (sector_counts, max_sector_pct)
        """
        if not positions:
            return {}, 0.0

        sector_counts: Dict[str, int] = {}
        for pos in positions:
            sec = pos.get("sector", "Unknown")
            sector_counts[sec] = sector_counts.get(sec, 0) + 1

        total = len(positions)
        max_pct = max(sector_counts.values()) / total if total > 0 else 0.0

        return sector_counts, max_pct

    @staticmethod
    def check_correlation(
        returns_dict: Dict[str, pd.Series],
        threshold: float = 0.7,
    ) -> List[str]:
        """Check for highly correlated positions.

        Parameters
        ----------
        returns_dict : dict
            ``{ticker: returns_series}`` for each position.
        threshold : float
            Correlation threshold for warning.

        Returns
        -------
        list of str
            Warning messages for highly correlated pairs.
        """
        warnings: List[str] = []
        tickers = list(returns_dict.keys())

        for i in range(len(tickers)):
            for j in range(i + 1, len(tickers)):
                t1, t2 = tickers[i], tickers[j]
                r1, r2 = returns_dict[t1], returns_dict[t2]

                # Align lengths
                min_len = min(len(r1), len(r2))
                if min_len < 20:
                    continue

                r1_aligned = r1.iloc[-min_len:].values
                r2_aligned = r2.iloc[-min_len:].values

                corr = np.corrcoef(r1_aligned, r2_aligned)[0, 1]
                if abs(corr) >= threshold:
                    warnings.append(
                        f"High correlation ({corr:.2f}) between {t1} and {t2}"
                    )

        return warnings

    @classmethod
    def analyze(
        cls,
        positions: List[Dict],
        capital: float,
        max_heat: float = 0.06,
        max_sector_pct: float = 0.40,
        returns_dict: Optional[Dict[str, pd.Series]] = None,
    ) -> PortfolioRiskResult:
        """Full portfolio risk analysis.

        Parameters
        ----------
        positions : list of dict
            Current portfolio positions.
        capital : float
            Total capital.
        max_heat : float
            Maximum allowed total heat (default 6%).
        max_sector_pct : float
            Maximum allowed sector concentration (default 40%).
        returns_dict : dict, optional
            Historical returns for correlation check.

        Returns
        -------
        PortfolioRiskResult
        """
        heat = cls.calculate_heat(positions, capital)
        sec_counts, max_sec = cls.sector_concentration(positions)

        corr_warnings = []
        if returns_dict:
            corr_warnings = cls.check_correlation(returns_dict)

        # Risk level classification
        if heat > max_heat * 1.5 or max_sec > max_sector_pct * 1.5:
            risk_level = "critical"
        elif heat > max_heat or max_sec > max_sector_pct:
            risk_level = "high"
        elif heat > max_heat * 0.7:
            risk_level = "medium"
        else:
            risk_level = "low"

        return PortfolioRiskResult(
            total_heat=heat,
            position_count=len(positions),
            sector_concentration=sec_counts,
            max_sector_pct=max_sec,
            correlation_warnings=corr_warnings,
            risk_level=risk_level,
        )


# ==============================================================================
# Stop Manager
# ==============================================================================

class StopManager:
    """Dynamic stop-loss management."""

    @staticmethod
    def trailing_stop(
        entry: float,
        current: float,
        highest_since_entry: float,
        trail_pct: float = 0.05,
    ) -> float:
        """Calculate trailing stop price.

        Parameters
        ----------
        entry : float
            Entry price.
        current : float
            Current price.
        highest_since_entry : float
            Highest price since entry.
        trail_pct : float
            Trailing stop percentage (e.g. 0.05 = 5%).

        Returns
        -------
        float
            Trailing stop price.
        """
        trail_price = highest_since_entry * (1 - trail_pct)
        # Never move stop below initial stop
        initial_stop = entry * (1 - trail_pct)
        return round(max(trail_price, initial_stop), 4)

    @staticmethod
    def time_stop(
        entry_date: str,
        current_date: str,
        max_days: int = 20,
        profit_threshold: float = 0.05,
        current_return: float = 0.0,
    ) -> Tuple[bool, str]:
        """Time-based stop: exit if no profit after N days.

        Parameters
        ----------
        entry_date : str
            Entry date (YYYY-MM-DD).
        current_date : str
            Current date (YYYY-MM-DD).
        max_days : int
            Maximum days in trade without profit.
        profit_threshold : float
            Minimum profit to avoid time stop (e.g. 0.05 = 5%).
        current_return : float
            Current return since entry.

        Returns
        -------
        tuple of (should_exit, reason)
        """
        try:
            from datetime import datetime
            entry_dt = datetime.strptime(entry_date, "%Y-%m-%d")
            current_dt = datetime.strptime(current_date, "%Y-%m-%d")
            days_held = (current_dt - entry_dt).days
        except (ValueError, TypeError):
            return False, ""

        if days_held >= max_days and current_return < profit_threshold:
            return True, f"Time stop: {days_held} days with {current_return:.1%} return (< {profit_threshold:.1%})"

        return False, ""

    @staticmethod
    def atr_stop(
        entry: float,
        atr: float,
        multiplier: float = 2.0,
    ) -> float:
        """ATR-based initial stop loss.

        Parameters
        ----------
        entry : float
            Entry price.
        atr : float
            Current ATR value.
        multiplier : float
            ATR multiplier for stop distance.

        Returns
        -------
        float
            Stop loss price.
        """
        return round(entry - atr * multiplier, 4)

    @classmethod
    def risk_reward_ratio(
        cls,
        entry: float,
        stop: float,
        target: float,
    ) -> float:
        """Calculate risk:reward ratio.

        Returns
        -------
        float
            R:R ratio (target: 2.0 means 2:1 reward:risk).
        """
        risk = abs(entry - stop)
        reward = abs(target - entry)
        if risk <= 0:
            return 0.0
        return round(reward / risk, 2)


__all__ = [
    "PositionSizer",
    "PositionSize",
    "PortfolioRisk",
    "PortfolioRiskResult",
    "StopManager",
]
