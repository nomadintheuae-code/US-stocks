import pandas as pd
import numpy as np
from .analysis import VCPAnalyzer, RSAnalyzer
from .sentinel_efficiency import SentinelEfficiencyAnalyzer

class ECRStrategyEngine:
    """
    🌀 Energy Compression Rotation Strategy - PRO v2.1
    修正点：メソッド名を analyze_single に統一し、app2.py との整合性を確保
    """

    @staticmethod
    def analyze_single(ticker: str, df: pd.DataFrame) -> dict:
        """app2.py から呼ばれるメインエントリポイント"""
        try:
            if df is None or len(df) < 200:
                return ECRStrategyEngine._empty_result(ticker)

            # --- 現在の指標計算 ---
            curr = ECRStrategyEngine._calculate_metrics(df)

            # ランクが低すぎる場合は早期リターン
            if curr["rank"] < 5:
                return ECRStrategyEngine._compile_result(ticker, curr, {}, "REJECTED", "NONE")

            # --- 変化率の計算（昨日比、週比） ---
            prev = ECRStrategyEngine._calculate_metrics(df.iloc[:-1])
            week = ECRStrategyEngine._calculate_metrics(df.iloc[:-5])

            rank_delta = curr["rank"] - prev["rank"]
            rank_slope = (curr["rank"] - week["rank"]) / 5

            dyn = {
                "rank_delta": round(rank_delta, 1),
                "rank_5d_slope": round(rank_slope, 2),
                "vol_change_ratio": curr["vol_ratio"]
            }

            rank = curr["rank"]
            dist = curr["dist_to_pivot"]
            vol_ratio = curr["vol_ratio"]

            # =========================
            # フェーズ判定（プロ仕様ロジック）
            # =========================
            phase = "WATCH"
            strat = "NONE"

            # 1. RELEASE (放出): ピボット突破済みで勢いが衰えた
            if dist < -0.07 and rank_slope <= 0:
                phase = "RELEASE"
                strat = "TRAILING"

            # 2. IGNITION (発火): ランク急増または出来高を伴う初動
            elif (
                rank_delta >= 15
                or (rank >= 75 and rank_slope >= 3)
                or (rank >= 70 and vol_ratio >= 1.8 and rank_slope > 1)
            ):
                phase = "IGNITION"
                strat = "ESE"

            # 3. ACCUMULATION (蓄積): 高ランクかつ低ボラで収縮中
            elif (
                rank >= 80
                and abs(rank_slope) < 2
                and 0 <= dist <= 0.08
            ):
                phase = "ACCUMULATION"
                strat = "PBVH"

            elif rank >= 65:
                phase = "HOLD/WATCH"

            return ECRStrategyEngine._compile_result(ticker, curr, dyn, phase, strat)

        except Exception:
            return ECRStrategyEngine._empty_result(ticker)

    @staticmethod
    def _calculate_metrics(df_subset: pd.DataFrame) -> dict:
        try:
            vcp_res = VCPAnalyzer.calculate(df_subset)
            ses_res = SentinelEfficiencyAnalyzer.calculate(df_subset)
            rs_raw = RSAnalyzer.get_raw_score(df_subset)

            vcp = vcp_res.get("score", 0)
            ses = ses_res.get("score", 0)

            # RS 安定スケーリング
            rs_score = int(np.clip((rs_raw + 0.3) * 100, 0, 100))

            # Pivot距離
            price = df_subset["Close"].iloc[-1]
            pivot = df_subset["High"].iloc[-50:].max()
            dist = (pivot - price) / pivot

            # 出来高比
            v_now = df_subset["Volume"].iloc[-1]
            v_avg = df_subset["Volume"].iloc[-20:].mean()
            vol_ratio = v_now / v_avg if v_avg > 0 else 1.0

            # Rank計算
            raw_rank = (vcp * 0.4) + (ses * 0.3) + (rs_score * 0.3)
            if vcp >= 95 and ses >= 80: raw_rank *= 1.15
            elif vcp >= 85 and ses >= 70: raw_rank *= 1.05

            return {
                "rank": int(min(100, raw_rank)),
                "vcp": vcp, "ses": ses, "rs": rs_score,
                "dist_to_pivot": dist, "vol_ratio": round(vol_ratio, 2)
            }
        except:
            return {"rank": 0, "vcp": 0, "ses": 0, "rs": 0, "dist_to_pivot": 0, "vol_ratio": 1.0}

    @staticmethod
    def _compile_result(ticker, curr, dyn, phase, strat):
        return {
            "ticker": ticker,
            "sentinel_rank": curr["rank"],
            "phase": phase,
            "strategy": strat,
            "dynamics": dyn,
            "components": {
                "energy_vcp": curr["vcp"],
                "quality_ses": curr["ses"],
                "momentum_rs": curr["rs"]
            },
            "metrics": {
                "dist_to_pivot_pct": round(curr["dist_to_pivot"] * 100, 2),
                "volume_ratio": curr["vol_ratio"]
            }
        }

    @staticmethod
    def _empty_result(ticker):
        return {
            "ticker": ticker, "sentinel_rank": 0, "phase": "ERR", "strategy": "NONE",
            "dynamics": {"rank_delta": 0, "rank_5d_slope": 0, "vol_change_ratio": 0},
            "components": {"energy_vcp": 0, "quality_ses": 0, "momentum_rs": 0},
            "metrics": {"dist_to_pivot_pct": 0, "volume_ratio": 0}
        }

