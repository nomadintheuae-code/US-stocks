“””
engines/data.py — 価格データ・為替レート取得

- CurrencyEngine : USD/JPY レートをyfinanceから取得
- DataEngine     : OHLCVデータの取得とキャッシュ管理（pickle）
  “””

import json
import pickle
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import CONFIG

CACHE_DIR = Path(”./cache_v45”)
CACHE_DIR.mkdir(exist_ok=True)

# ==============================================================================

# 💱 CurrencyEngine

# ==============================================================================

class CurrencyEngine:
“”“USD/JPY レートを取得する。失敗時は 150.0 を返す。”””

```
@staticmethod
def get_usd_jpy() -> float:
    try:
        df = yf.Ticker("JPY=X").history(period="1d")
        return round(float(df["Close"].iloc[-1]), 2) if not df.empty else 150.0
    except:
        return 150.0
```

# ==============================================================================

# 💾 DataEngine

# ==============================================================================

class DataEngine:
“”“OHLCV データの取得・キャッシュ・セクター情報管理。”””

```
@staticmethod
def get_data(ticker: str, period: str = "700d") -> pd.DataFrame | None:
    """
    yfinance からOHLCVデータを取得。
    有効期限内のキャッシュがあればそちらを返す。
    """
    cache_file = CACHE_DIR / f"{ticker}.pkl"

    # キャッシュヒット
    if cache_file.exists():
        if time.time() - cache_file.stat().st_mtime < CONFIG["CACHE_EXPIRY"]:
            try:
                with open(cache_file, "rb") as f:
                    return pickle.load(f)
            except:
                pass

    # yfinance から取得
    try:
        df = yf.download(ticker, period=period, progress=False, auto_adjust=True)
        if df is None or df.empty or len(df) < 150:
            return None
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        with open(cache_file, "wb") as f:
            pickle.dump(df, f)
        return df
    except:
        return None

@staticmethod
def get_current_price(ticker: str) -> float | None:
    """
    正規取引時間内の終値のみを返す（時間外取引価格を除外）。
    KPI表示とAIプロンプトで同じ価格を使うために分離。
    """
    try:
        info = yf.Ticker(ticker).fast_info
        price = getattr(info, "regular_market_price", None) \
             or getattr(info, "last_price", None)
        if price:
            return round(float(price), 4)
        # フォールバック
        df = yf.Ticker(ticker).history(period="2d", auto_adjust=True)
        return round(float(df["Close"].iloc[-1]), 4) if not df.empty else None
    except:
        return None

@staticmethod
def get_sector(ticker: str) -> str:
    """セクター情報を取得。JSONキャッシュ付き。"""
    cache_file = CACHE_DIR / "sectors.json"
    sector_map: dict = {}

    if cache_file.exists():
        try:
            with open(cache_file) as f:
                sector_map = json.load(f)
        except:
            pass

    if ticker in sector_map:
        return sector_map[ticker]

    try:
        sector = yf.Ticker(ticker).info.get("sector", "Unknown")
        sector_map[ticker] = sector
        with open(cache_file, "w") as f:
            json.dump(sector_map, f)
        return sector
    except:
        return "Unknown"
```