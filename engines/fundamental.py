import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from config import CONFIG

CACHE_DIR = Path("./cache_v45")
CACHE_DIR.mkdir(exist_ok=True)

# ==============================================================================
# 📊 FundamentalEngine
# ==============================================================================

class FundamentalEngine:
    """
    yfinance.info からファンダメンタルデータを取得。
    アナリスト目標株価・空売り比率・インサイダー保有率・予想PER 等。
    """

    @staticmethod
    def get(ticker: str) -> dict:
        cache_file = CACHE_DIR / f"fund_{ticker}.json"

        # キャッシュ読み込み
        if cache_file.exists():
            if time.time() - cache_file.stat().st_mtime < CONFIG.get("FUND_CACHE_EXPIRY", 86400):
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.info

            price = info.get("regularMarketPrice") or info.get("currentPrice") or info.get("previousClose", 0)
            target = info.get("targetMeanPrice")

            # 上昇余地（%）
            upside = None
            if target and price and price > 0:
                upside = round((target / price - 1) * 100, 1)

            data = {
                # アナリスト
                "analyst_target": target,
                "analyst_upside": upside,
                "analyst_high": info.get("targetHighPrice"),
                "analyst_low": info.get("targetLowPrice"),
                "analyst_count": info.get("numberOfAnalystOpinions"),
                "recommendation": info.get("recommendationKey", ""),

                # 空売り
                "short_ratio": info.get("shortRatio"),
                "short_pct": info.get("shortPercentOfFloat"),

                # 保有構造
                "insider_pct": info.get("heldPercentInsiders"),
                "institution_pct": info.get("heldPercentInstitutions"),

                # バリュエーション・成長
                "pe_forward": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "revenue_growth": info.get("revenueGrowth"),
                "earnings_growth": info.get("earningsGrowth"),
                "profit_margin": info.get("profitMargins"),

                # 決算関連
                "eps_forward": info.get("forwardEps"),
            }

            # キャッシュ保存
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2, default=str)

            return data

        except Exception:
            return {}

    @staticmethod
    def format_for_prompt(data: dict, price: float) -> list[str]:
        """AIプロンプト用に整形した行リストを返す。"""
        lines = []

        if data.get("analyst_target") is not None:
            upside = data.get("analyst_upside")
            upside_str = f" ({upside:+.1f}%)" if upside is not None else ""
            lines.append(
                f"アナリスト平均目標株価: ${data['analyst_target']:.2f}{upside_str}  "
                f"アナリスト数: {data.get('analyst_count', '?')}"
            )

        if data.get("recommendation"):
            lines.append(f"コンセンサス推奨: {data['recommendation'].upper()}")

        if data.get("short_ratio") is not None:
            pct = (data.get("short_pct") or 0) * 100
            lines.append(f"空売り日数: {data['short_ratio']:.1f}日  Float比率: {pct:.1f}%")

        if data.get("insider_pct") is not None:
            ins = (data["insider_pct"] or 0) * 100
            inst = (data.get("institution_pct") or 0) * 100
            lines.append(f"インサイダー保有率: {ins:.1f}%  機関保有率: {inst:.1f}%")

        if data.get("pe_forward") is not None:
            rev = (data.get("revenue_growth") or 0) * 100
            lines.append(f"予想PER: {data['pe_forward']:.1f}  売上成長率: {rev:.1f}%")

        return lines


# ==============================================================================
# 🏛️ InsiderEngine
# ==============================================================================

class InsiderEngine:
    """
    yfinance.insider_transactions から直近60日の売買を集計。
    大量売却（売り2件以上 かつ 売り>買い×2）は alert=True を返す。
    """

    @staticmethod
    def get(ticker: str) -> dict:
        cache_file = CACHE_DIR / f"insider_{ticker}.json"

        # キャッシュ（6時間 = 21600秒）
        if cache_file.exists():
            if time.time() - cache_file.stat().st_mtime < 21600:
                try:
                    with open(cache_file, encoding="utf-8") as f:
                        return json.load(f)
                except Exception:
                    pass

        result = {
            "buy_count": 0,
            "sell_count": 0,
            "net_shares": 0,
            "alert": False,
            "summary": "",
            "recent": [],
        }

        try:
            ticker_obj = yf.Ticker(ticker)
            it = ticker_obj.insider_transactions

            if it is None or it.empty:
                with open(cache_file, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, default=str)
                return result

            # 直近15件程度をチェック（yfinanceのデータ量による）
            for _, row in it.head(15).iterrows():
                txn = str(row.get("Transaction", "")).lower()
                shares = int(row.get("Shares", 0) or 0)

                if "sell" in txn or "sale" in txn:
                    result["sell_count"] += 1
                    result["net_shares"] -= shares
                    result["recent"].append({
                        "type": "SELL",
                        "name": str(row.get("Insider", "Unknown")),
                        "shares": shares,
                        "date": str(row.get("Start Date", "Unknown")),
                    })
                elif "buy" in txn or "purchase" in txn:
                    result["buy_count"] += 1
                    result["net_shares"] += shares
                    result["recent"].append({
                        "type": "BUY",
                        "name": str(row.get("Insider", "Unknown")),
                        "shares": shares,
                        "date": str(row.get("Start Date", "Unknown")),
                    })

            # アラート判定
            result["alert"] = (
                result["sell_count"] >= 2
                and result["sell_count"] > result["buy_count"] * 2
            )

            result["summary"] = (
                f"買 {result['buy_count']}件 / 売 {result['sell_count']}件  "
                f"純: {result['net_shares']:+,}株"
            )

        except Exception:
            pass

        # キャッシュ保存（エラー時も空データで保存）
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, default=str)

        return result

    @staticmethod
    def format_for_prompt(data: dict) -> list[str]:
        """AIプロンプト用に整形した行リストを返す。"""
        if not data.get("summary"):
            return []

        lines = [f"インサイダー取引（直近）: {data['summary']}"]

        if data.get("alert"):
            lines.append("⚠️ 警告: 大量インサイダー売却を検出（リスク要因として必ず言及せよ）")

        return lines