"""
core_fmp.py — Sentinel-v3 Data Engine (Stable API Optimized)
==========================================================
Hannah（FMPサポート）推奨のStableパスを確実に処理するエンジン。
"""
import os, requests, json, hashlib, time
from pathlib import Path
import pandas as pd

# APIキー（環境変数になければ直接指定）
FMP_API_KEY = os.environ.get("FMP_API_KEY", "")
BASE_URL = "https://financialmodelingprep.com/stable"
CACHE_DIR = Path("cache")
CACHE_DIR.mkdir(exist_ok=True)

def _get(slug: str, params: dict = None, cache_key: str = None, ttl: int = 3600):
    params = params or {}
    if cache_key:
        h = hashlib.md5(cache_key.encode()).hexdigest()
        cache_file = CACHE_DIR / f"{h}.json"
        if cache_file.exists() and (time.time() - cache_file.stat().st_mtime < ttl):
            try: return json.loads(cache_file.read_text())
            except: pass

    url = f"{BASE_URL}/{slug}"
    try:
        time.sleep(0.1) # レートリミット配慮
        resp = requests.get(url, params={**params, "apikey": FMP_API_KEY}, timeout=15)
        if resp.status_code != 200: return None
        data = resp.json()
        if cache_key and data:
            cache_file.write_text(json.dumps(data))
        return data
    except Exception as e:
        print(f"Error fetching {slug}: {e}")
        return None

def get_historical_data(ticker: str, days: int = 365) -> pd.DataFrame | None:
    # Stable /full はリストが直接返る仕様に対応
    data = _get("historical-price-eod/full", {"symbol": ticker}, f"hist_{ticker}", 43200)
    if not isinstance(data, list): return None
    df = pd.DataFrame(data)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df.rename(columns={"open":"Open","high":"High","low":"Low","close":"Close","volume":"Volume"})
    return df.tail(days)

def get_news(ticker: str, limit: int = 10) -> list:
    # Hannah推奨のニュースパス
    data = _get("news/stock-latest", {"limit": 50, "symbol": ticker}, f"news_{ticker}", 3600*3)
    if not isinstance(data, list): return []
    return [{
        "title": d.get("title", ""),
        "published_at": d.get("publishedDate", ""),
        "source": d.get("site", ""),
        "url": d.get("url", ""),
        "summary": (d.get("text", "") or "")[:200]
    } for d in data[:limit]]

def get_quote(ticker: str) -> dict | None:
    data = _get("quote", {"symbol": ticker})
    return data[0] if isinstance(data, list) and data else None

def get_company_profile(ticker: str) -> dict | None:
    data = _get("profile", {"symbol": ticker}, f"prof_{ticker}", 86400)
    return data[0] if isinstance(data, list) and data else None

def get_fundamentals(ticker: str) -> dict | None:
    # 以前のテストで成功したパスを使用
    km = _get("key-metrics", {"symbol": ticker, "limit": 1}, f"km_{ticker}", 86400)
    ig = _get("income-statement-growth", {"symbol": ticker, "limit": 1}, f"ig_{ticker}", 86400)
    km = km[0] if isinstance(km, list) and km else {}
    ig = ig[0] if isinstance(ig, list) and ig else {}
    return {
        "pe": round(km.get("peRatio", 0), 2),
        "roe": round(km.get("returnOnEquity", 0)*100, 1),
        "rev_growth": round(ig.get("growthRevenue", 0)*100, 1),
        "debt_equity": round(km.get("debtToEquity", 0), 2),
        "market_cap_b": round(km.get("marketCap", 0)/1e9, 1)
    }

def get_analyst_consensus(ticker: str) -> dict | None:
    target = _get("price-target-summary", {"symbol": ticker}, f"pt_{ticker}", 43200)
    quote = get_quote(ticker)
    if not target or not quote: return None
    t_data = target[0] if isinstance(target, list) else target
    target_p = t_data.get("lastMonthAvgPriceTarget", 0)
    current_p = quote.get("price", 1)
    return {
        "target": target_p,
        "upside": round(((target_p / current_p) - 1) * 100, 1) if target_p else 0,
        "count": t_data.get("allTimeCount", 0)
    }