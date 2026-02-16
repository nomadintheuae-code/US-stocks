"""
core_fmp.py — Sentinel-v3 最終確定エンジン (Starter Plan / Stable API 完全対応版)
==========================================================================
Hannah（サポート）から得た隠しパスと、実機テスト済みのJSON構造を100%反映。
- 過去株価: /stable/historical-price-eod/full
- ニュース: /stable/news/stock-latest
- 財務分析: /stable/ (profile, key-metrics, income-statement-growth, ratios)
"""
import os, requests, json, hashlib, time
from pathlib import Path
import pandas as pd

FMP_API_KEY  = os.environ.get("FMP_API_KEY", "")
BASE_URL     = "https://financialmodelingprep.com/stable"
CACHE_DIR    = Path(__file__).parent.parent.parent / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# キャッシュ付き共通GET
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get(slug: str, params: dict = None, cache_key: str = None, ttl: int = 3600):
    """
    Hannahの推奨するStable APIを叩く共通関数。
    """
    params = params or {}
    if cache_key:
        h = hashlib.md5(cache_key.encode()).hexdigest()
        cache_file = CACHE_DIR / f"{h}.json"
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime < ttl):
            return json.loads(cache_file.read_text())

    url = f"{BASE_URL}/{slug}"
    try:
        # Starterプランのレートリミットを考慮
        time.sleep(0.2)
        resp = requests.get(url, params={**params, "apikey": FMP_API_KEY}, timeout=15)
        if resp.status_code != 200:
            return None
        
        data = resp.json()
        if cache_key and data:
            cache_file.write_text(json.dumps(data))
        return data
    except Exception as e:
        print(f"FMP Connection Error [{slug}]: {e}")
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 過去株価（OHLCV）— ✅ Hannah's /full Path
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_historical_data(ticker: str, days: int = 365) -> pd.DataFrame | None:
    """
    Hannahの教え通り、Stable版は直接リストが返ってくる構造に対応。
    """
    data = _get("historical-price-eod/full", {"symbol": ticker},
                cache_key=f"hist_{ticker}", ttl=12*3600)
    
    # Stable /full は dict["historical"] ではなく、直接 list で返る
    if not data or not isinstance(data, list):
        return None
    
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    
    # カラム名を統一 (Sentinel-v3 標準)
    df = df.rename(columns={
        "open": "Open", "high": "High", "low": "Low",
        "close": "Close", "volume": "Volume"
    })
    
    return df.tail(days)[["Open", "High", "Low", "Close", "Volume"]]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# ニュース — ✅ Hannah's stock-latest Path
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_news(ticker: str, limit: int = 10) -> list:
    """
    Hannah直伝の最新ニュースエンドポイント。
    """
    data = _get("news/stock-latest",
                {"page": 0, "limit": 50, "symbol": ticker},
                cache_key=f"news_v4_{ticker}", ttl=3*3600)
    
    if not isinstance(data, list):
        return []
    
    # ニュースの重複を避け、必要な数だけ整形
    seen_titles = set()
    results = []
    for d in data:
        title = d.get("title", "")
        if title in seen_titles: continue
        seen_titles.add(title)
        
        results.append({
            "title":        title,
            "published_at": d.get("publishedDate", ""),
            "source":       d.get("site", ""),
            "url":          d.get("url", ""),
            "summary":      (d.get("text", "") or "")[:250],
        })
        if len(results) >= limit: break
        
    return results


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 現在値・クォート — ✅ Verified
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_quote(ticker: str) -> dict | None:
    data = _get("quote", {"symbol": ticker})
    return data[0] if isinstance(data, list) and data else None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 財務分析 (プロ級) — ✅ Verified by User Test
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_company_analysis(ticker: str) -> dict | None:
    """
    今回のテストで疎通した4つのデータを統合。
    企業の「稼ぐ力」と「割安度」を完全に数値化する。
    """
    profile = _get("profile", {"symbol": ticker}, cache_key=f"prof_{ticker}", ttl=86400)
    metrics = _get("key-metrics", {"symbol": ticker, "limit": 3}, cache_key=f"km_{ticker}", ttl=86400)
    growth  = _get("income-statement-growth", {"symbol": ticker, "limit": 3}, cache_key=f"grow_{ticker}", ttl=86400)
    ratios  = _get("ratios", {"symbol": ticker, "period": "ttm"}, cache_key=f"ratio_{ticker}", ttl=86400)

    if not profile or not metrics: return None

    p = profile[0]
    m = metrics[0]  # 最新年度 (2025)
    g = growth[0] if growth else {}
    r = ratios[0] if ratios else {}

    def _pct(v): return round(float(v)*100, 2) if v is not None else 0
    def _rnd(v, n=2): return round(float(v), n) if v is not None else 0

    return {
        "basic": {
            "name": p.get("companyName"),
            "industry": p.get("industry"),
            "mkt_cap_b": _rnd(p.get("marketCap", 0) / 1e9, 1),
            "price": p.get("price"),
            "inst_own": _pct(p.get("institutionalOwnershipPercentage"))
        },
        "valuation": {
            "pe": _rnd(r.get("priceToEarningsRatio")),
            "ps": _rnd(r.get("priceToSalesRatio")),
            "peg": _rnd(r.get("priceToEarningsGrowthRatio"))
        },
        "quality": {
            "roe": _pct(m.get("returnOnEquity")),
            "roa": _pct(m.get("returnOnAssets")),
            "net_margin": _pct(r.get("netProfitMargin")),
            "debt_to_equity": _rnd(m.get("debtToEquity", r.get("debtToEquityRatio")))
        },
        "growth": {
            "rev_growth": _pct(g.get("growthRevenue")),
            "net_inc_growth": _pct(g.get("growthNetIncome")),
            "eps_growth": _pct(g.get("growthEPS"))
        }
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# アナリストコンセンサス (目標株価)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_analyst_consensus(ticker: str) -> dict | None:
    """
    /stable/price-target-summary を活用。
    内訳(Buy/Sell)はHannahの回答を待ちつつ、まずは乖離率を算出。
    """
    target = _get("price-target-summary", {"symbol": ticker}, cache_key=f"tgt_{ticker}", ttl=43200)
    quote = get_quote(ticker)
    
    if not target or not quote: return None
    
    t_data = target[0] if isinstance(target, list) else target
    mean_target = t_data.get("lastMonthAvgPriceTarget", 0)
    current_price = quote.get("price", 1)
    
    upside = round(((mean_target / current_price) - 1) * 100, 1) if mean_target else 0
    
    return {
        "target_mean": mean_target,
        "upside_pct": upside,
        "analyst_count": t_data.get("allTimeCount", 0),
        "consensus": "Strong Buy" if upside > 15 else "Buy" if upside > 5 else "Hold"
    }

