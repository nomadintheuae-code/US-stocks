import json
import time
from datetime import datetime, timedelta
from pathlib import Path

import yfinance as yf

from config import CONFIG

CACHE_DIR = Path(”./cache_v45”)
CACHE_DIR.mkdir(exist_ok=True)

# ==============================================================================

# 📊 FundamentalEngine

# ==============================================================================

class FundamentalEngine:
“””
yfinance.info からファンダメンタルデータを取得。
アナリスト目標株価・空売り比率・インサイダー保有率・予想PER 等。
“””

```
@staticmethod
def get(ticker: str) -> dict:
    cache_file = CACHE_DIR / f"fund_{ticker}.json"

    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CONFIG["FUND_CACHE_EXPIRY"]:
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except:
                pass

    try:
        info  = yf.Ticker(ticker).info
        price = info.get("regularMarketPrice") or info.get("currentPrice", 0)
        target = info.get("targetMeanPrice")

        # アナリスト目標株価と現在値の乖離（%）
        upside = round((target / price - 1) * 100, 1) if target and price else None

        data = {
            # アナリスト
            "analyst_target":  target,
            "analyst_upside":  upside,           # +なら上値余地、-なら割高
            "analyst_high":    info.get("targetHighPrice"),
            "analyst_low":     info.get("targetLowPrice"),
            "analyst_count":   info.get("numberOfAnalystOpinions"),
            "recommendation":  info.get("recommendationKey", ""),  # buy/hold/sell

            # 空売り（高いほど踏み上げ期待 or 弱気な見方が多い）
            "short_ratio":     info.get("shortRatio"),        # 返済に要する日数
            "short_pct":       info.get("shortPercentOfFloat"),  # float 比率

            # 保有構造
            "insider_pct":     info.get("heldPercentInsiders"),
            "institution_pct": info.get("heldPercentInstitutions"),

            # バリュエーション
            "pe_forward":      info.get("forwardPE"),
            "peg_ratio":       info.get("pegRatio"),
            "revenue_growth":  info.get("revenueGrowth"),
            "earnings_growth": info.get("earningsGrowth"),
            "profit_margin":   info.get("profitMargins"),

            # 決算
            "eps_forward":     info.get("forwardEps"),
        }

        with open(cache_file, "w") as f:
            json.dump(data, f, default=str)
        return data

    except:
        return {}

@staticmethod
def format_for_prompt(data: dict, price: float) -> list[str]:
    """AIプロンプト用に整形した行リストを返す。"""
    lines = []
    if data.get("analyst_target"):
        lines.append(
            f"アナリスト平均目標株価: ${data['analyst_target']:.2f} "
            f"({data['analyst_upside']:+.1f}%)  "
            f"アナリスト数: {data.get('analyst_count', '?')}"
        )
    if data.get("recommendation"):
        lines.append(f"コンセンサス推奨: {data['recommendation'].upper()}")
    if data.get("short_ratio"):
        pct = (data.get("short_pct") or 0) * 100
        lines.append(f"空売り日数: {data['short_ratio']:.1f}日  Float比率: {pct:.1f}%")
    if data.get("insider_pct"):
        ins  = data["insider_pct"] * 100
        inst = (data.get("institution_pct") or 0) * 100
        lines.append(f"インサイダー保有率: {ins:.1f}%  機関保有率: {inst:.1f}%")
    if data.get("pe_forward"):
        rev = (data.get("revenue_growth") or 0) * 100
        lines.append(f"予想PER: {data['pe_forward']:.1f}  売上成長率: {rev:.1f}%")
    return lines
```

# ==============================================================================

# 🏛️ InsiderEngine

# ==============================================================================

class InsiderEngine:
“””
yfinance.insider_transactions から直近60日の売買を集計。
大量売却（売り2件以上 かつ 売り>買い×2）は alert=True を返す。
“””

```
@staticmethod
def get(ticker: str) -> dict:
    cache_file = CACHE_DIR / f"insider_{ticker}.json"

    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < 6 * 3600:
            try:
                with open(cache_file) as f:
                    return json.load(f)
            except:
                pass

    result = {
        "buy_count":  0,
        "sell_count": 0,
        "net_shares": 0,
        "alert":      False,
        "summary":    "",
        "recent":     [],
    }

    try:
        it = yf.Ticker(ticker).insider_transactions
        if it is None or it.empty:
            return result

        for _, row in it.head(15).iterrows():
            txn    = str(row.get("Transaction", "")).lower()
            shares = int(row.get("Shares", 0) or 0)

            if "sell" in txn or "sale" in txn:
                result["sell_count"] += 1
                result["net_shares"] -= shares
                result["recent"].append({
                    "type":   "SELL",
                    "name":   str(row.get("Insider", "")),
                    "shares": shares,
                    "date":   str(row.get("Start Date", "")),
                })
            elif "buy" in txn or "purchase" in txn:
                result["buy_count"]  += 1
                result["net_shares"] += shares
                result["recent"].append({
                    "type":   "BUY",
                    "name":   str(row.get("Insider", "")),
                    "shares": shares,
                    "date":   str(row.get("Start Date", "")),
                })

        result["alert"] = (
            result["sell_count"] >= 2
            and result["sell_count"] > result["buy_count"] * 2
        )
        result["summary"] = (
            f"買 {result['buy_count']}件 / 売 {result['sell_count']}件  "
            f"純: {result['net_shares']:+,}株"
        )

    except:
        pass

    with open(cache_file, "w") as f:
        json.dump(result, f, default=str)
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
```