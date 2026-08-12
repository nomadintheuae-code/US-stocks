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
# 🎯 VCPAnalyzer（改良版・内訳付き）
# ==============================================================================

class VCPAnalyzer:
    """
    Mark Minervini VCP スコアリング（改良版）
    - Tightness  (40pt)
    - Volume     (30pt)
    - MA Align   (30pt)
    - Pivot Bonus (最大5pt) → 合計 105pt
    """

    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 130:
                return VCPAnalyzer._empty_result()

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # ── ATR(14) ─────────────────────────────────────────
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0:
                return VCPAnalyzer._empty_result()

            # =====================================================
            # 1️⃣ Tightness（収縮度合い）- 40pt
            # =====================================================
            periods = [20, 30, 40, 60]
            ranges = []
            for p in periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            curr_range = ranges[0]
            avg_range = float(np.mean(ranges[:3]))  # 20,30,40 の平均

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
            tight_score = min(40, tight_score)

            # =====================================================
            # 2️⃣ Volume（出来高ドライアップ）- 30pt
            # =====================================================
            v20_avg = float(volume.iloc[-20:].mean())
            v60_avg = float(volume.iloc[-60:-40].mean())
            if pd.isna(v20_avg) or pd.isna(v60_avg):
                return VCPAnalyzer._empty_result()

            v_ratio = v20_avg / v60_avg if v60_avg > 0 else 1.0

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
            # 3️⃣ MA Alignment（移動平均トレンド）- 30pt
            # =====================================================
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma150 = float(close.rolling(150).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])

            ma_score = 0
            if price > ma50:
                ma_score += 10
            if ma50 > ma150:
                ma_score += 10
            if ma150 > ma200:
                ma_score += 10

            # =====================================================
            # 4️⃣ Pivot Bonus（ピボット接近ボーナス）- 最大5pt
            # =====================================================
            pivot = float(high.iloc[-50:].max())
            distance = (pivot - price) / pivot

            pivot_bonus = 0
            if 0 <= distance <= 0.04:
                pivot_bonus = 5
            elif 0.04 < distance <= 0.08:
                pivot_bonus = 3

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

            return {
                "score": int(min(105, tight_score + vol_score + ma_score + pivot_bonus)),
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
            return VCPAnalyzer._empty_result()

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
