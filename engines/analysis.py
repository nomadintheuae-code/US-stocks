# engines/analysis.py

import numpy as np
import pandas as pd


# ============================================================
# RS ANALYZER
# ============================================================

class RSAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame) -> int:
        try:
            if df is None or len(df) < 252:
                return 0

            close = df["Close"]

            r63 = close.iloc[-1] / close.iloc[-63] - 1
            r126 = close.iloc[-1] / close.iloc[-126] - 1
            r252 = close.iloc[-1] / close.iloc[-252] - 1

            score = (r63 * 0.5) + (r126 * 0.3) + (r252 * 0.2)
            return int(max(0, min(100, score * 100)))

        except Exception:
            return 0


# ============================================================
# VCP ANALYZER  PRO VERSION
# ============================================================

class VCPAnalyzer:

    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 220:
                return VCPAnalyzer._empty()

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            price = float(close.iloc[-1])

            # =============================
            # ATR（現在＋過去比較）
            # =============================
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)

            atr_series = tr.rolling(14).mean()
            atr_now = float(atr_series.iloc[-1])
            atr_30 = float(atr_series.iloc[-30])
            atr_60 = float(atr_series.iloc[-60])

            if np.isnan(atr_now) or atr_now <= 0:
                return VCPAnalyzer._empty()

            # ATR圧縮率（最大20点）
            atr_score = 0
            if atr_60 > 0:
                compression = 1 - (atr_now / atr_60)
                atr_score = max(0, min(20, compression * 25))

            # =============================
            # ① 段階的レンジ縮小（構造検出）
            # =============================
            periods = [15, 25, 40]
            ranges = []

            for p in periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            structural = ranges[0] < ranges[1] < ranges[2]

            avg_range = float(np.mean(ranges))

            # 最大30点
            structure_score = 0
            if structural:
                structure_score = max(0, min(30, (0.25 - avg_range) * 120))

            # =============================
            # ② 出来高段階的減少
            # =============================
            v20 = float(volume.iloc[-20:].mean())
            v40 = float(volume.iloc[-40:-20].mean())
            v60 = float(volume.iloc[-60:-40].mean())

            vol_structural = v20 < v40 < v60

            vol_score = 0
            if v60 > 0:
                ratio = v20 / v60
                vol_score = max(0, min(20, (1 - ratio) * 25))

            if vol_structural:
                vol_score += 5

            # =============================
            # ③ ピボット接近度（発射直前判定）
            # =============================
            pivot = float(high.iloc[-40:].max())
            distance = (pivot - price) / pivot

            # ピボットに近いほど高得点（最大20点）
            pivot_score = 0
            if 0 <= distance <= 0.08:
                pivot_score = max(0, 20 * (0.08 - distance) / 0.08)

            # =============================
            # ④ トレンド整合
            # =============================
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma150 = float(close.rolling(150).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])

            trend_score = 0
            if price > ma50:
                trend_score += 5
            if ma50 > ma150:
                trend_score += 5
            if ma150 > ma200:
                trend_score += 5

            # =============================
            # 合計（最大100前後）
            # =============================
            total = int(
                atr_score +
                structure_score +
                vol_score +
                pivot_score +
                trend_score
            )

            signals = []
            if structural:
                signals.append("Structural Contraction")
            if vol_structural:
                signals.append("Volume Stair-Step")
            if pivot_score > 12:
                signals.append("Near Pivot")
            if atr_score > 10:
                signals.append("ATR Compression")

            return {
                "score": total,
                "atr": atr_now,
                "signals": signals,
                "is_dryup": v20 < v60
            }

        except Exception:
            return VCPAnalyzer._empty()

    @staticmethod
    def _empty():
        return {
            "score": 0,
            "atr": 0,
            "signals": [],
            "is_dryup": False
        }


# ============================================================
# STRATEGY VALIDATOR
# ============================================================

class StrategyValidator:

    @staticmethod
    def validate(rs: int, vcp_score: int) -> bool:
        try:
            # 本物だけ通す
            if rs >= 75 and vcp_score >= 65:
                return True
            return False
        except Exception:
            return False