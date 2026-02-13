# engines/analysis.py

import numpy as np
import pandas as pd


# ============================================================
# RS ANALYZER（sentinel互換版）
# ============================================================

class RSAnalyzer:

    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        """
        sentinel互換用（rawスコア返却）
        """
        try:
            if df is None or len(df) < 252:
                return 0.0

            close = df["Close"]

            r63  = close.iloc[-1] / close.iloc[-63]  - 1
            r126 = close.iloc[-1] / close.iloc[-126] - 1
            r252 = close.iloc[-1] / close.iloc[-252] - 1

            return (r63 * 0.5) + (r126 * 0.3) + (r252 * 0.2)

        except Exception:
            return 0.0

    @staticmethod
    def calculate(df: pd.DataFrame) -> int:
        """
        単体利用用（0-100スコア）
        """
        raw = RSAnalyzer.get_raw_score(df)
        return int(max(0, min(100, raw * 100)))

    @staticmethod
    def assign_percentiles(raw_list: list[dict]) -> list[dict]:
        """
        sentinel用 percentile割り振り
        """
        if not raw_list:
            return raw_list

        raw_list.sort(key=lambda x: x["raw_rs"])
        total = len(raw_list)

        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 99) + 1

        return raw_list


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

            # ATR
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs()
            ], axis=1).max(axis=1)

            atr_series = tr.rolling(14).mean()
            atr_now = float(atr_series.iloc[-1])
            atr_60  = float(atr_series.iloc[-60])

            if np.isnan(atr_now) or atr_now <= 0:
                return VCPAnalyzer._empty()

            atr_score = 0
            if atr_60 > 0:
                compression = 1 - (atr_now / atr_60)
                atr_score = max(0, min(20, compression * 25))

            # 構造収縮
            periods = [15, 25, 40]
            ranges = []

            for p in periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            structural = ranges[0] < ranges[1] < ranges[2]
            avg_range = float(np.mean(ranges))

            structure_score = 0
            if structural:
                structure_score = max(0, min(30, (0.25 - avg_range) * 120))

            # 出来高収縮
            v20 = float(volume.iloc[-20:].mean())
            v60 = float(volume.iloc[-60:-40].mean()) if len(volume) >= 60 else 0

            vol_score = 0
            if v60 > 0:
                ratio = v20 / v60
                vol_score = max(0, min(25, (1 - ratio) * 30))

            # ピボット接近
            pivot = float(high.iloc[-40:].max())
            distance = (pivot - price) / pivot

            pivot_score = 0
            if 0 <= distance <= 0.08:
                pivot_score = max(0, 20 * (0.08 - distance) / 0.08)

            # トレンド
            ma50  = float(close.rolling(50).mean().iloc[-1])
            ma150 = float(close.rolling(150).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])

            trend_score = 0
            if price > ma50:
                trend_score += 5
            if ma50 > ma150:
                trend_score += 5
            if ma150 > ma200:
                trend_score += 5

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
# STRATEGY VALIDATOR（互換）
# ============================================================

class StrategyValidator:

    @staticmethod
    def validate(rs: int, vcp_score: int) -> bool:
        return rs >= 75 and vcp_score >= 65