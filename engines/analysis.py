import pandas as pd
import numpy as np
from typing import List, Optional

from config import CONFIG


# ==============================================================================
# 📈 RSIndicator — configurable Relative Strength
# ==============================================================================

class RSIndicator:
    """Configurable Relative Strength indicator.

    Computes a weighted momentum score across multiple lookback windows,
    then assigns cross-sectional percentiles within a universe.

    Configuration is read from config.yaml ``rs:`` section by default,
    but can be overridden via constructor arguments.
    """

    DEFAULT_WINDOWS = [252, 126, 63, 21]
    DEFAULT_WEIGHTS = [0.4, 0.2, 0.2, 0.2]
    DEFAULT_MIN_DATA_DAYS = 21
    ERROR_SENTINEL = -999.0

    def __init__(
        self,
        windows: Optional[List[int]] = None,
        weights: Optional[List[float]] = None,
        min_data_days: Optional[int] = None,
    ):
        cfg = self._load_rs_config()
        self.windows = windows if windows is not None else cfg.get("windows", self.DEFAULT_WINDOWS)
        self.weights = weights if weights is not None else cfg.get("weights", self.DEFAULT_WEIGHTS)
        self.min_data_days = min_data_days if min_data_days is not None else cfg.get("min_data_days", self.DEFAULT_MIN_DATA_DAYS)
        self._validate_config()

    @staticmethod
    def _load_rs_config() -> dict:
        """Load the ``rs:`` section from config.yaml (best-effort)."""
        try:
            from sentinel.config import get_config
            cfg = get_config()
            return {
                "windows": list(cfg.rs.windows),
                "weights": list(cfg.rs.weights),
                "min_data_days": int(cfg.rs.min_data_days),
            }
        except Exception:
            return {}

    def _validate_config(self) -> None:
        if len(self.windows) != len(self.weights):
            raise ValueError(
                f"windows ({len(self.windows)}) and weights ({len(self.weights)}) must match"
            )
        if abs(sum(self.weights) - 1.0) > 0.001:
            raise ValueError(f"weights must sum to 1.0, got {sum(self.weights)}")
        if self.min_data_days < 1:
            raise ValueError(f"min_data_days must be >= 1, got {self.min_data_days}")

    def compute_raw(self, df: pd.DataFrame) -> float:
        """Compute the raw weighted-momentum RS score for a single ticker."""
        try:
            c = df["Close"]
            if len(c) < self.min_data_days:
                return self.ERROR_SENTINEL

            returns = []
            for window in self.windows:
                if len(c) >= window:
                    returns.append(c.iloc[-1] / c.iloc[-window] - 1)
                else:
                    returns.append(c.iloc[-1] / c.iloc[0] - 1)

            return sum(r * w for r, w in zip(returns, self.weights))
        except Exception:
            return self.ERROR_SENTINEL

    def compute_percentiles(self, raw_list: list[dict]) -> list[dict]:
        """Assign percentile ratings (1-99) to a list of ``{'raw_rs': float}`` dicts.

        Sorts the list in-place by raw_rs ascending, then writes ``rs_rating``.
        """
        if not raw_list:
            return raw_list
        raw_list.sort(key=lambda x: x["raw_rs"])
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 99) + 1
        return raw_list

    # -- backward-compat classmethods (delegate to default instance) --

    @classmethod
    def get_raw_score(cls, df: pd.DataFrame) -> float:
        return cls().compute_raw(df)

    @classmethod
    def assign_percentiles(cls, raw_list: list[dict]) -> list[dict]:
        return cls().compute_percentiles(raw_list)

# ==============================================================================
# 🎯 VCPIndicator — configurable Volatility Contraction Pattern
# ==============================================================================

class VCPIndicator:
    """Configurable VCP (Volatility Contraction Pattern) indicator.

    Computes a composite VCP score from four components:
    - Tightness  (price range contraction)
    - Volume     (volume dry-up)
    - MA Align   (moving average trend alignment)
    - Pivot Bonus (proximity to pivot high)

    Configuration is read from config.yaml ``vcp:`` section by default,
    but can be overridden via constructor arguments.
    """

    DEFAULT_TIGHTNESS_PERIODS = [20, 30, 40, 60]
    DEFAULT_VOLUME_LOOKBACK_SHORT = 20
    DEFAULT_VOLUME_LOOKBACK_LONG = 60
    DEFAULT_VOLUME_LOOKBACK_GAP = 20
    DEFAULT_MA_PERIODS = [50, 150, 200]
    DEFAULT_PIVOT_NEAR_PCT = 0.04
    DEFAULT_PIVOT_FAR_PCT = 0.08
    DEFAULT_MAX_TIGHTNESS_SCORE = 40
    DEFAULT_MAX_VOLUME_SCORE = 30
    DEFAULT_MAX_MA_SCORE = 30
    DEFAULT_MAX_PIVOT_BONUS = 5
    DEFAULT_ATR_PERIOD = 14
    DEFAULT_MIN_DATA_BARS = 130

    def __init__(
        self,
        tightness_periods: Optional[List[int]] = None,
        volume_lookback_short: Optional[int] = None,
        volume_lookback_long: Optional[int] = None,
        volume_lookback_gap: Optional[int] = None,
        ma_periods: Optional[List[int]] = None,
        pivot_near_pct: Optional[float] = None,
        pivot_far_pct: Optional[float] = None,
        max_tightness_score: Optional[int] = None,
        max_volume_score: Optional[int] = None,
        max_ma_score: Optional[int] = None,
    ):
        cfg = self._load_vcp_config()
        self.tightness_periods = tightness_periods if tightness_periods is not None else cfg.get("tightness_periods", self.DEFAULT_TIGHTNESS_PERIODS)
        self.volume_lookback_short = volume_lookback_short if volume_lookback_short is not None else cfg.get("volume_lookback_short", self.DEFAULT_VOLUME_LOOKBACK_SHORT)
        self.volume_lookback_long = volume_lookback_long if volume_lookback_long is not None else cfg.get("volume_lookback_long", self.DEFAULT_VOLUME_LOOKBACK_LONG)
        self.volume_lookback_gap = volume_lookback_gap if volume_lookback_gap is not None else cfg.get("volume_lookback_gap", self.DEFAULT_VOLUME_LOOKBACK_GAP)
        self.ma_periods = ma_periods if ma_periods is not None else cfg.get("ma_periods", self.DEFAULT_MA_PERIODS)
        self.pivot_near_pct = pivot_near_pct if pivot_near_pct is not None else cfg.get("pivot_near_pct", self.DEFAULT_PIVOT_NEAR_PCT)
        self.pivot_far_pct = pivot_far_pct if pivot_far_pct is not None else cfg.get("pivot_far_pct", self.DEFAULT_PIVOT_FAR_PCT)
        self.max_tightness_score = max_tightness_score if max_tightness_score is not None else cfg.get("max_tightness_score", self.DEFAULT_MAX_TIGHTNESS_SCORE)
        self.max_volume_score = max_volume_score if max_volume_score is not None else cfg.get("max_volume_score", self.DEFAULT_MAX_VOLUME_SCORE)
        self.max_ma_score = max_ma_score if max_ma_score is not None else cfg.get("max_ma_score", self.DEFAULT_MAX_MA_SCORE)
        # These are not in config.yaml schema; use class defaults
        self.max_pivot_bonus = self.DEFAULT_MAX_PIVOT_BONUS
        self.atr_period = self.DEFAULT_ATR_PERIOD
        self.min_data_bars = self.DEFAULT_MIN_DATA_BARS
        self._validate_config()

    @staticmethod
    def _load_vcp_config() -> dict:
        """Load the ``vcp:`` section from config.yaml (best-effort)."""
        try:
            from sentinel.config import get_config
            cfg = get_config()
            return {
                "tightness_periods": list(cfg.vcp.tightness_periods),
                "volume_lookback_short": int(cfg.vcp.volume_lookback_short),
                "volume_lookback_long": int(cfg.vcp.volume_lookback_long),
                "volume_lookback_gap": int(cfg.vcp.volume_lookback_gap),
                "ma_periods": list(cfg.vcp.ma_periods),
                "pivot_near_pct": float(cfg.vcp.pivot_near_pct),
                "pivot_far_pct": float(cfg.vcp.pivot_far_pct),
                "max_tightness_score": int(cfg.vcp.max_tightness_score),
                "max_volume_score": int(cfg.vcp.max_volume_score),
                "max_ma_score": int(cfg.vcp.max_ma_score),
            }
        except Exception:
            return {}

    def _validate_config(self) -> None:
        if len(self.tightness_periods) < 2:
            raise ValueError("tightness_periods must have at least 2 periods")
        if self.volume_lookback_short < 1 or self.volume_lookback_long < 1:
            raise ValueError("volume lookback periods must be >= 1")
        if self.volume_lookback_gap < 0:
            raise ValueError("volume_lookback_gap must be >= 0")
        if len(self.ma_periods) < 2:
            raise ValueError("ma_periods must have at least 2 periods")
        if self.pivot_near_pct <= 0 or self.pivot_far_pct <= 0:
            raise ValueError("pivot percentages must be > 0")
        if self.pivot_far_pct <= self.pivot_near_pct:
            raise ValueError("pivot_far_pct must be > pivot_near_pct")
        if self.atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if self.min_data_bars < 1:
            raise ValueError("min_data_bars must be >= 1")

    def calculate(self, df: pd.DataFrame) -> dict:
        """Compute the VCP score for a single ticker."""
        try:
            if df is None or len(df) < self.min_data_bars:
                return self._empty_result()

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # ── ATR ─────────────────────────────────────────────
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(self.atr_period).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0:
                return self._empty_result()

            # =====================================================
            # 1️⃣ Tightness（収縮度合い）
            # =====================================================
            ranges = []
            for p in self.tightness_periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            curr_range = ranges[0]
            avg_range = float(np.mean(ranges[:3]))  # first 3 periods

            # 収縮推移（短期 < 中期 < 長期）
            is_contracting = ranges[0] < ranges[1] < ranges[2]

            if avg_range < 0.10:
                tight_score = 40
            elif avg_range < 0.15:
                tight_score = 30
            elif avg_range < 0.20:
                tight_score = 20
            elif avg_range < 0.28:
                tight_score = 10
            else:
                tight_score = 0

            if is_contracting:
                tight_score += 5
            tight_score = min(self.max_tightness_score, tight_score)

            # =====================================================
            # 2️⃣ Volume（出来高ドライアップ）
            # =====================================================
            v_short_avg = float(volume.iloc[-self.volume_lookback_short:].mean())
            long_end = -self.volume_lookback_short - self.volume_lookback_gap
            v_long_avg = float(volume.iloc[-self.volume_lookback_long:long_end].mean())
            if pd.isna(v_short_avg) or pd.isna(v_long_avg):
                return self._empty_result()

            v_ratio = v_short_avg / v_long_avg if v_long_avg > 0 else 1.0

            if v_ratio < 0.45:
                vol_score = 30
            elif v_ratio < 0.60:
                vol_score = 25
            elif v_ratio < 0.75:
                vol_score = 15
            else:
                vol_score = 0

            is_dryup = v_ratio < 0.75

            # =====================================================
            # 3️⃣ MA Alignment（移動平均トレンド）
            # =====================================================
            ma_values = []
            for period in self.ma_periods:
                ma_values.append(float(close.rolling(period).mean().iloc[-1]))
            price = float(close.iloc[-1])

            ma_score = 0
            if price > ma_values[0]:
                ma_score += 10
            for i in range(len(ma_values) - 1):
                if ma_values[i] > ma_values[i + 1]:
                    ma_score += 10

            # =====================================================
            # 4️⃣ Pivot Bonus（ピボット接近ボーナス）
            # =====================================================
            pivot_lookback = self.tightness_periods[0] * 2.5  # 50 for default [20,30,40,60]
            pivot = float(high.iloc[-int(pivot_lookback):].max())
            distance = (pivot - price) / pivot

            pivot_bonus = 0
            if 0 <= distance <= self.pivot_near_pct:
                pivot_bonus = self.max_pivot_bonus
            elif self.pivot_near_pct < distance <= self.pivot_far_pct:
                pivot_bonus = self.max_pivot_bonus - 2

            # =====================================================
            # シグナル生成
            # =====================================================
            signals = []
            if tight_score >= 35:
                signals.append("Tight Base (VCP)")
            if is_contracting:
                signals.append("V-Contraction Detected")
            if is_dryup:
                signals.append("Volume Dry-up Detected")
            if ma_score >= 20:
                signals.append("Trend Alignment OK")
            if pivot_bonus > 0:
                signals.append("Near Pivot Point")

            max_total = self.max_tightness_score + self.max_volume_score + self.max_ma_score + self.max_pivot_bonus
            return {
                "score": int(min(max_total, tight_score + vol_score + ma_score + pivot_bonus)),
                "atr": atr,
                "signals": signals,
                "is_dryup": is_dryup,
                "range_pct": round(curr_range, 4),
                "vol_ratio": round(v_ratio, 2),
                "breakdown": {
                    "tight": tight_score,
                    "vol": vol_score,
                    "ma": ma_score,
                    "pivot": pivot_bonus
                }
            }

        except Exception:
            return self._empty_result()

    @staticmethod
    def _empty_result() -> dict:
        return {
            "score": 0,
            "atr": 0.0,
            "signals": [],
            "is_dryup": False,
            "range_pct": 0.0,
            "vol_ratio": 1.0,
            "breakdown": {"tight": 0, "vol": 0, "ma": 0, "pivot": 0}
        }

    # -- backward-compat classmethod --

    @classmethod
    def calculate_class(cls, df: pd.DataFrame) -> dict:
        return cls().calculate(df)


# ==============================================================================
# 🎯 VCPAnalyzer — backward-compatible wrapper around VCPIndicator
# ==============================================================================
# VCPAnalyzer is retained for backward compatibility. New code should use
# VCPIndicator directly. All behavior is delegated to VCPIndicator with
# default configuration (matches the original hardcoded values exactly).

class VCPAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        return VCPIndicator.calculate_class(df)

    @staticmethod
    def _empty_result() -> dict:
        return VCPIndicator._empty_result()

# ==============================================================================
# 📈 RSAnalyzer — backward-compatible wrapper around RSIndicator
# ==============================================================================
# RSAnalyzer is retained for backward compatibility. New code should use
# RSIndicator directly. All behavior is delegated to RSIndicator with
# default configuration (matches the original hardcoded values exactly).

class RSAnalyzer:
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        return RSIndicator.get_raw_score(df)

    @staticmethod
    def assign_percentiles(raw_list: list[dict]) -> list[dict]:
        return RSIndicator.assign_percentiles(raw_list)

# ==============================================================================
# 🔬 StrategyValidator（変更なし）
# ==============================================================================

class StrategyValidator:
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 200:
                return 1.0

            close = df["Close"]
            high = df["High"]
            low = df["Low"]

            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()

            trades = []
            in_pos = False
            entry_p = 0.0
            stop_p = 0.0

            target_mult = CONFIG["TARGET_R_MULTIPLE"]
            stop_mult = CONFIG["STOP_LOSS_ATR"]

            start = max(50, len(df) - 250)

            for i in range(start, len(df)):
                if in_pos:
                    if float(low.iloc[i]) <= stop_p:
                        trades.append(-1.0)
                        in_pos = False
                    elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * target_mult:
                        trades.append(target_mult)
                        in_pos = False
                    elif i == len(df) - 1:
                        risk = entry_p - stop_p
                        if risk > 0:
                            r = (float(close.iloc[i]) - entry_p) / risk
                            trades.append(r)
                        in_pos = False
                else:
                    if i < 20:
                        continue
                    pivot = float(high.iloc[i-20:i].max())
                    ma50 = float(close.rolling(50).mean().iloc[i])
                    if float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50:
                        in_pos = True
                        entry_p = float(close.iloc[i])
                        stop_p = entry_p - float(atr.iloc[i]) * stop_mult

            if not trades:
                return 1.0

            pos = sum(t for t in trades if t > 0)
            neg = abs(sum(t for t in trades if t < 0))
            pf = pos / neg if neg > 0 else (5.0 if pos > 0 else 1.0)
            return round(min(10.0, float(pf)), 2)
        except Exception:
            return 1.0
