import json
import pickle
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import config

CACHE_DIR = Path("./cache_v45")
CACHE_DIR.mkdir(exist_ok=True)

# ==============================================================================
# 💱 CurrencyEngine
# ==============================================================================

class CurrencyEngine:
    """USD/JPY レートを取得する。失敗時は 150.0 を返す。"""

    @staticmethod
    def get_usd_jpy() -> float:
        try:
            df = yf.Ticker("JPY=X").history(period="1d")
            if not df.empty:
                return round(float(df["Close"].iloc[-1]), 2)
            return 150.0
        except Exception:
            return 150.0


# ==============================================================================
# 💾 DataEngine
# ==============================================================================

class DataEngine:
    """OHLCV データの取得・キャッシュ・セクター情報管理。"""

    @staticmethod
    def get_data(ticker: str, period: str = "700d") -> pd.DataFrame | None:
        """
        yfinance からOHLCVデータを取得。
        有効期限内のキャッシュがあればそちらを返す。
        """
        cache_file = CACHE_DIR / f"{ticker}.pkl"

        # キャッシュヒット判定 & 読み込み
        if cache_file.exists():
            if time.time() - cache_file.stat().st_mtime < CONFIG["CACHE_EXPIRY"]:
                try:
                    with open(cache_file, "rb") as f:
                        return pickle.load(f)
                except Exception:
                    pass  # キャッシュ破損時は再取得へ

        # yfinance から新規取得
        try:
            df = yf.download(
                ticker,
                period=period,
                progress=False,
                auto_adjust=True,
                repair=True  # 最近のyfinanceで便利なオプション
            )
            if df is None or df.empty or len(df) < 150:
                return None

            # MultiIndex対策（稀に発生）
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)

            # キャッシュ保存
            with open(cache_file, "wb") as f:
                pickle.dump(df, f)

            return df

        except Exception:
            return None

    @staticmethod
    def get_current_price(ticker: str) -> float | None:
        """
        正規取引時間内の終値（regular market price）を優先的に返す。
        時間外価格を避け、KPI表示とAIプロンプトで価格を統一するため。
        """
        try:
            ticker_obj = yf.Ticker(ticker)
            info = ticker_obj.fast_info

            # regular_market_price が存在すれば最優先
            price = getattr(info, "regular_market_price", None)
            if price is not None:
                return round(float(price), 4)

            # なければ last_price など他の候補
            price = getattr(info, "last_price", None)
            if price is not None:
                return round(float(price), 4)

            # 最終フォールバック：直近2日分のhistory
            df = ticker_obj.history(period="2d", auto_adjust=True)
            if not df.empty:
                return round(float(df["Close"].iloc[-1]), 4)

            return None

        except Exception:
            return None

    @staticmethod
    def get_sector(ticker: str) -> str:
        """セクター情報を取得。JSONキャッシュ付き。"""
        cache_file = CACHE_DIR / "sectors.json"
        sector_map: dict[str, str] = {}

        # キャッシュ読み込み
        if cache_file.exists():
            try:
                with open(cache_file, encoding="utf-8") as f:
                    sector_map = json.load(f)
            except Exception:
                pass

        # キャッシュにあれば即返却
        if ticker in sector_map:
            return sector_map[ticker]

        # yfinance から取得
        try:
            sector = yf.Ticker(ticker).info.get("sector", "Unknown")
            sector_map[ticker] = sector

            # キャッシュ保存（上書き）
            with open(cache_file, "w", encoding="utf-8") as f:
                json.dump(sector_map, f, ensure_ascii=False, indent=2)

            return sector

        except Exception:
            return "Unknown"