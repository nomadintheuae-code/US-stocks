import pandas as pd
import numpy as np


class Analyzer:

    def __init__(self, config):
        self.config = config

    # ==========================================================
    # VCP CALCULATION（総合判定型）
    # ==========================================================
    def calculate_vcp(self, df):

        def _empty():
            return {
                "vcp_score": 0,
                "tightness_score": 0,
                "volume_score": 0,
                "ma_score": 0,
            }

        if df is None or len(df) < 80:
            return _empty()

        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]

        # ==============================
        # ① Contraction Score (40点)
        # ==============================
        try:
            ranges = []
            periods = [20, 30, 40]

            for p in periods:
                recent_high = high.iloc[-p:].max()
                recent_low = low.iloc[-p:].min()
                range_pct = (recent_high - recent_low) / recent_high
                ranges.append(range_pct)

            avg_range = np.mean(ranges)

            # 長期ほど締まっているか
            is_contracting = ranges[0] > ranges[1] > ranges[2]

            if is_contracting and avg_range < 0.15:
                tight_score = 40
            elif avg_range < 0.20:
                tight_score = 25
            elif avg_range < 0.25:
                tight_score = 15
            else:
                tight_score = 0

        except Exception:
            tight_score = 0

        # ==============================
        # ② Volume Dry-up Score (30点)
        # ==============================
        try:
            v20 = volume.iloc[-20:].mean()
            v40 = volume.iloc[-40:-20].mean()
            v60 = volume.iloc[-60:-40].mean()

            if pd.isna(v20) or pd.isna(v40) or pd.isna(v60):
                vol_score = 0
            elif v20 < v40 < v60:
                vol_score = 30
            elif v20 < v40:
                vol_score = 20
            else:
                vol_score = 0

        except Exception:
            vol_score = 0

        # ==============================
        # ③ MA Alignment Score (30点)
        # ==============================
        try:
            ma50 = close.rolling(50).mean().iloc[-1]
            ma200 = close.rolling(200).mean().iloc[-1]
            price = close.iloc[-1]

            if pd.isna(ma50) or pd.isna(ma200):
                ma_score = 0
            else:
                ma_score = (
                    (10 if price > ma50 else 0)
                    + (10 if ma50 > ma200 else 0)
                    + (10 if price > ma200 else 0)
                )

        except Exception:
            ma_score = 0

        total_score = tight_score + vol_score + ma_score

        return {
            "vcp_score": int(total_score),
            "tightness_score": int(tight_score),
            "volume_score": int(vol_score),
            "ma_score": int(ma_score),
        }

    # ==========================================================
    # RS RATING（1〜99正規化）
    # ==========================================================
    def calculate_rs(self, df):

        if df is None or len(df) < 252:
            return 0

        try:
            close = df["Close"]

            perf_3m = close.iloc[-1] / close.iloc[-63] - 1
            perf_6m = close.iloc[-1] / close.iloc[-126] - 1
            perf_12m = close.iloc[-1] / close.iloc[-252] - 1

            # 重み付き平均
            weighted = (0.4 * perf_3m) + (0.3 * perf_6m) + (0.3 * perf_12m)

            # 仮スケーリング（内部ランキング前提）
            score = int(np.clip((weighted + 1) * 50, 1, 99))

            return score

        except Exception:
            return 0

    # ==========================================================
    # 総合スコア
    # ==========================================================
    def analyze(self, df):

        vcp_data = self.calculate_vcp(df)
        rs_score = self.calculate_rs(df)

        total = vcp_data["vcp_score"] + rs_score

        return {
            "vcp_score": vcp_data["vcp_score"],
            "rs_score": rs_score,
            "total_score": total,
            "tightness_score": vcp_data["tightness_score"],
            "volume_score": vcp_data["volume_score"],
            "ma_score": vcp_data["ma_score"],
        }