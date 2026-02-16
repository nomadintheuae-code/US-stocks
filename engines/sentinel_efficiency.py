import pandas as pd
import numpy as np

class SentinelEfficiencyAnalyzer:
    """
    🛡️ SENTINEL EFFICIENCY SCORE (SES) - PRO EDITION
    
    VCPが「チャートの形」を見るのに対し、SESは「値動きの質（物理学）」を見る。
    機関投資家による「効率的な買い集め」と「売り枯れ」を定量化する。
    
    Score Max: 100pt
    1. Fractal Efficiency (30pt): トレンドの直線性（カウフマン効率性比率）
    2. True Force Index   (30pt): 出来高×値幅による真の買い圧力
    3. Volatility Squeeze (20pt): ボラティリティの極度な収縮
    4. Bar Quality        (20pt): ローソク足の実体と引け位置の質
    """

    @staticmethod
    def calculate(df: pd.DataFrame, period: int = 20) -> dict:
        try:
            if df is None or len(df) < period + 5:
                return SentinelEfficiencyAnalyzer._empty_result()

            close = df["Close"]
            open_ = df["Open"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # ── 1️⃣ Fractal Efficiency (カウフマン効率性比率) - 30pt ──
            net_change = abs(close.iloc[-1] - close.iloc[-period])
            sum_moves = (close.diff().abs().iloc[-period:]).sum()
            er = net_change / sum_moves if sum_moves > 0 else 0
            
            er_score = 0
            if er > 0.60: er_score = 30
            elif er > 0.50: er_score = 25
            elif er > 0.40: er_score = 20
            elif er > 0.30: er_score = 10
            else: er_score = 0

            # ── 2️⃣ True Force Index (真の買い圧力) - 30pt ──
            price_change = close.diff()
            force = volume * price_change
            subset_force = force.iloc[-period:]
            pos_force = subset_force[subset_force > 0].sum()
            neg_force = abs(subset_force[subset_force < 0].sum())
            total_force = pos_force + neg_force
            force_ratio = pos_force / total_force if total_force > 0 else 0.5
            
            vol_score = 0
            if force_ratio > 0.80: vol_score = 30
            elif force_ratio > 0.65: vol_score = 20
            elif force_ratio > 0.55: vol_score = 10
            else: vol_score = 0

            # ── 3️⃣ Volatility Squeeze (ボラティリティ収縮) - 20pt ──
            returns = close.pct_change()
            curr_volatility = returns.iloc[-period:].std()
            past_volatility = returns.iloc[-60:-period].std()
            vol_contraction = curr_volatility / past_volatility if past_volatility > 0 else 1.0
            
            sqz_score = 0
            if vol_contraction < 0.5: sqz_score = 20
            elif vol_contraction < 0.65: sqz_score = 15
            elif vol_contraction < 0.8: sqz_score = 10
            elif vol_contraction > 1.2: sqz_score = -5
            else: sqz_score = 0

            # ── 4️⃣ Bar Quality (ローソク足の質) - 20pt ──
            high_low = high - low
            clv = ((close - low) / high_low).fillna(0.5)
            body_str = ((close - open_) / high_low).fillna(0)
            avg_clv = clv.iloc[-period:].mean()
            avg_body = body_str.iloc[-period:].mean()
            
            bar_score = 0
            if avg_clv > 0.6 and avg_body > 0.1: bar_score = 20
            elif avg_clv > 0.55 and avg_body > 0: bar_score = 15
            elif avg_clv > 0.5: bar_score = 10
            else: bar_score = 0

            total_score = er_score + vol_score + sqz_score + bar_score
            
            return {
                "score": int(max(0, min(100, total_score))),
                "metrics": {
                    "er": round(er, 2),
                    "force_ratio": round(force_ratio, 2),
                    "vol_contraction": round(vol_contraction, 2),
                    "avg_clv": round(avg_clv, 2)
                },
                "breakdown": {
                    "fractal_efficiency": er_score,
                    "true_force": vol_score,
                    "volatility_squeeze": sqz_score,
                    "bar_quality": bar_score
                }
            }

        except Exception:
            return SentinelEfficiencyAnalyzer._empty_result()

    @staticmethod
    def _empty_result() -> dict:
        return {
            "score": 0,
            "metrics": {"er": 0, "force_ratio": 0, "vol_contraction": 1.0, "avg_clv": 0},
            "breakdown": {"fractal_efficiency": 0, "true_force": 0, "volatility_squeeze": 0, "bar_quality": 0}
        }
