import pandas as pd
from .analysis import VCPAnalyzer, RSAnalyzer
from .sentinel_efficiency import SentinelEfficiencyAnalyzer

class ECRStrategyEngine:
    """
    🌀 Energy Compression Rotation (ECR) Strategy
    単一銘柄分析用 (GUIでの確認用)
    """

    @staticmethod
    def analyze_single(ticker: str, df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 200:
                return ECRStrategyEngine._empty_result(ticker)

            # 各エンジン実行
            vcp_res = VCPAnalyzer.calculate(df)
            ses_res = SentinelEfficiencyAnalyzer.calculate(df)
            raw_rs = RSAnalyzer.get_raw_score(df)
            
            # 簡易RSスコア (相対評価なしの概算)
            rs_score = min(100, max(0, int((raw_rs + 0.5) * 66)))

            vcp_score = vcp_res.get("score", 0)
            ses_score = ses_res.get("score", 0)

            # ECRランク計算
            raw_rank = (vcp_score * 0.4) + (ses_score * 0.3) + (rs_score * 0.3)
            if vcp_score >= 95 and ses_score >= 80:
                raw_rank *= 1.15
            
            sentinel_rank = int(min(100, raw_rank))

            # ダイナミクス（簡易）
            curr_price = df["Close"].iloc[-1]
            pivot_price = df["High"].iloc[-50:].max()
            dist_to_pivot = (pivot_price - curr_price) / pivot_price

            # フェーズ判定
            phase = "WATCH"
            strategy = "NONE"

            # PHASE 1: ACCUMULATION (仕込み)
            # SESが高く、VCPが高いが、まだ動いていない
            if sentinel_rank >= 80 and 0 <= dist_to_pivot < 0.08:
                phase = "ACCUMULATION"
                strategy = "PBVH (Harvest)"
            
            # PHASE 2: IGNITION (発火)
            # 出来高急増などの本来の条件は省略し、ランクと位置で簡易判定
            elif sentinel_rank >= 75 and abs(dist_to_pivot) <= 0.05:
                phase = "IGNITION"
                strategy = "ESE (Shock Entry)"
            
            # PHASE 3: RELEASE (放出)
            elif dist_to_pivot < -0.07:
                phase = "RELEASE"
                strategy = "TRAILING"

            return {
                "ticker": ticker,
                "sentinel_rank": sentinel_rank,
                "phase": phase,
                "strategy": strategy,
                "components": {
                    "vcp": vcp_score,
                    "ses": ses_score,
                    "rs": rs_score
                }
            }

        except Exception:
            return ECRStrategyEngine._empty_result(ticker)

    @staticmethod
    def _empty_result(ticker):
        return {
            "ticker": ticker, "sentinel_rank": 0, "phase": "ERR", "strategy": "NONE",
            "components": {"vcp": 0, "ses": 0, "rs": 0}
        }
