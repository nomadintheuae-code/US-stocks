import pandas as pd
import numpy as np
from typing import Dict, List, Literal

# エンジンパッケージ内のモジュール参照
from .analysis import VCPAnalyzer, RSAnalyzer
from .sentinel_efficiency import SentinelEfficiencyAnalyzer

MarketTrend = Literal["UPTREND", "NEUTRAL", "DOWNTREND"]

class ECRStrategyEngine:
    """
    🌀 Energy Compression Rotation (ECR) Strategy - PRO v3.0
    市場全体の中での「相対的優位性」と「状態遷移」を判定する実運用エンジン。
    """

    @staticmethod
    def batch_analyze(
        ticker_data_map: Dict[str, pd.DataFrame], 
        market_trend: MarketTrend = "NEUTRAL"
    ) -> List[dict]:
        results = []
        rs_list = []

        # Step 1: 全銘柄の RS Raw Score を計算
        for ticker, df in ticker_data_map.items():
            if df is None or len(df) < 200: continue
            raw_rs = RSAnalyzer.get_raw_score(df)
            rs_list.append({"ticker": ticker, "raw_rs": raw_rs})

        # Step 2: RS Rating (1-99) を市場相対順位で割り当て
        ranked_rs = RSAnalyzer.assign_percentiles(rs_list)
        rs_map = {item["ticker"]: item["rs_rating"] for item in ranked_rs}

        # Step 3: 各銘柄の詳細分析 & 戦略判定
        for ticker, df in ticker_data_map.items():
            if ticker not in rs_map: continue
            rs_rating = rs_map[ticker]
            res = ECRStrategyEngine._analyze_single_ticker(ticker, df, rs_rating, market_trend)
            results.append(res)

        return sorted(results, key=lambda x: x["sentinel_rank"], reverse=True)

    @staticmethod
    def analyze_single(ticker: str, df: pd.DataFrame) -> dict:
        """単一銘柄の簡易分析（GUI用）"""
        if df is None or len(df) < 200: return ECRStrategyEngine._empty_result(ticker)
        # 単独の場合はRSを簡易計算 (相対評価できないため)
        raw_rs = RSAnalyzer.get_raw_score(df)
        rs_rating = min(99, max(1, int((raw_rs + 0.5) * 66))) # 簡易スケーリング
        return ECRStrategyEngine._analyze_single_ticker(ticker, df, rs_rating, "NEUTRAL")

    @staticmethod
    def _analyze_single_ticker(ticker: str, df: pd.DataFrame, rs_rating: int, market_trend: str) -> dict:
        try:
            vcp_res = VCPAnalyzer.calculate(df)
            ses_res = SentinelEfficiencyAnalyzer.calculate(df)
            vcp_score = vcp_res.get("score", 0)
            ses_score = ses_res.get("score", 0)

            # ランク計算 (Weighted Average)
            raw_rank = (vcp_score * 0.4) + (ses_score * 0.3) + (rs_rating * 0.3)
            if vcp_score >= 95 and ses_score >= 80:
                raw_rank *= 1.15
            
            sentinel_rank = int(min(100, raw_rank))

            # ダイナミクス計算 (簡易版)
            tr = pd.concat([
                df["High"] - df["Low"],
                (df["High"] - df["Close"].shift()).abs(),
                (df["Low"] - df["Close"].shift()).abs()
            ], axis=1).max(axis=1)
            atr20 = tr.rolling(20).mean().iloc[-1]
            atr60 = tr.rolling(60).mean().iloc[-1]
            atr_ratio = atr20 / atr60 if atr60 > 0 else 1.0

            vol_curr = df["Volume"].iloc[-1]
            vol_avg = df["Volume"].iloc[-20:].mean()
            vol_ratio = vol_curr / vol_avg if vol_avg > 0 else 1.0

            curr_price = df["Close"].iloc[-1]
            pivot_price = df["High"].iloc[-50:].max()
            dist_to_pivot = (pivot_price - curr_price) / pivot_price

            price_chg = (df["Close"].iloc[-1] / df["Close"].iloc[-2] - 1) * 100
            rank_delta_est = 0
            if price_chg > 3 and vol_ratio > 1.5: rank_delta_est = 15
            elif price_chg > 1: rank_delta_est = 5
            elif price_chg < -1: rank_delta_est = -5
            
            # フェーズ判定
            phase = "WATCH"
            strategy = "NONE"

            # PHASE 1: ACCUMULATION
            if sentinel_rank >= 80 and atr_ratio < 0.85 and 0 <= dist_to_pivot < 0.08:
                phase = "ACCUMULATION"
                strategy = "PBVH (Harvest)"
            
            # PHASE 2: IGNITION
            is_ignition_setup = (sentinel_rank >= 75 and rank_delta_est >= 10 and vol_ratio >= 1.5 and abs(dist_to_pivot) <= 0.08)
            if is_ignition_setup:
                if market_trend == "DOWNTREND":
                    phase = "IGNITION_FAILED"
                    strategy = "WAIT (Market Weak)"
                else:
                    phase = "IGNITION"
                    strategy = "ESE (Shock Entry)"
            
            # PHASE 3: RELEASE
            if dist_to_pivot < -0.07:
                phase = "RELEASE"
                strategy = "TRAILING"

            return {
                "ticker": ticker,
                "sentinel_rank": sentinel_rank,
                "phase": phase,
                "strategy": strategy,
                "components": {"vcp": vcp_score, "ses": ses_score, "rs": rs_rating},
                "metrics": {"atr_ratio": round(atr_ratio, 2), "vol_ratio": round(vol_ratio, 2), "dist_pivot": round(dist_to_pivot, 2), "rank_delta": rank_delta_est}
            }
        except Exception:
            return ECRStrategyEngine._empty_result(ticker)

    @staticmethod
    def _empty_result(ticker):
        return {
            "ticker": ticker, "sentinel_rank": 0, "phase": "ERR", "strategy": "NONE",
            "components": {"vcp":0, "ses":0, "rs":0}, "metrics": {}
        }
