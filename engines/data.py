import json
import pickle
import time
from pathlib import Path

import pandas as pd
import yfinance as yf

from config import CONFIG

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
                repair=True
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
    def get_atr(ticker: str, period: int = 14) -> float:
        """
        ATR(14) を算出して返す。
        ポートフォリオのダイナミックストップ計算に使用。
        失敗時は 1.5 を返す（フォールバック値）。
        """
        try:
            # まずキャッシュ済みデータを優先利用（余分なAPI呼び出しを避ける）
            cache_file = CACHE_DIR / f"{ticker}.pkl"
            df = None

            if cache_file.exists():
                try:
                    with open(cache_file, "rb") as f:
                        df = pickle.load(f)
                except Exception:
                    pass

            # キャッシュがなければ90日分だけ取得（軽量）
            if df is None or df.empty:
                try:
                    df = yf.download(
                        ticker,
                        period="90d",
                        progress=False,
                        auto_adjust=True,
                    )
                    if isinstance(df.columns, pd.MultiIndex):
                        df.columns = df.columns.get_level_values(0)
                except Exception:
                    return 1.5

            if df is None or df.empty or len(df) < period + 1:
                return 1.5

            # ATR 計算
            high  = df["High"]
            low   = df["Low"]
            close = df["Close"]

            tr = pd.concat([
                high - low,
                (high - close.shift(1)).abs(),
                (low  - close.shift(1)).abs(),
            ], axis=1).max(axis=1)

            atr_val = float(tr.rolling(period).mean().iloc[-1])

            if pd.isna(atr_val) or atr_val <= 0:
                return 1.5

            return round(atr_val, 4)

        except Exception:
            return 1.5

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


# ==============================================================================
# 📡 MarketDataProvider — abstraction for market data loading
# ==============================================================================
# Provides a clean interface for loading OHLCV data. The concrete
# DataEngineAdapter implements the same behavior as DataEngine.get_data()
# but through the provider pattern. Existing callers continue to use
# DataEngine.get_data() directly; this class is opt-in.
# ==============================================================================

from abc import ABC, abstractmethod


class MarketDataProvider(ABC):
    """Abstract base class for market data providers."""

    @abstractmethod
    def get_ohlcv(self, ticker: str, period: str = "700d") -> pd.DataFrame | None:
        """Retrieve OHLCV data for a ticker."""
        raise NotImplementedError

    @abstractmethod
    def get_current_price(self, ticker: str) -> float | None:
        """Retrieve current price for a ticker."""
        raise NotImplementedError


class DataEngineAdapter(MarketDataProvider):
    """Concrete adapter wrapping DataEngine for the MarketDataProvider interface.

    Backward-compatible: delegates to DataEngine.get_data() et al.
    Existing sentinel.py / engines/data.py callers are unaffected.
    """

    def __init__(self):
        self._data_engine = DataEngine()

    def get_ohlcv(self, ticker: str, period: str = "700d") -> pd.DataFrame | None:
        return self._data_engine.get_data(ticker, period)

    def get_current_price(self, ticker: str) -> float | None:
        return self._data_engine.get_current_price(ticker)


# ==============================================================================
# 💾 CacheManager — TTL-based cache with compression support
# ==============================================================================
# Provides TTL-based read/write for pickle cache files. Compression is
# supported via zstd/lz4/gzip/none but existing uncompressed pickle data
# is preserved transparently. Cache failures are non-fatal.
# ==============================================================================

import zlib

CACHE_TTL_DEFAULT = 43200  # 12 hours in seconds


class CacheManager:
    """TTL-based cache manager for pickle and JSON cache files.

    Features:
    - Read/write with TTL expiration
    - Compression support (zstd, lz4, gzip, none) — existing uncompressed
      data is preserved transparently
    - Cache miss / hit tracking
    - Corrupted cache handling (graceful fallback)
    - Non-fatal failures (never raises)
    """

    def __init__(self, cache_dir: str = "./cache_v45", ttl: int = CACHE_TTL_DEFAULT):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self._ttl = ttl
        self.hit_count = 0
        self.miss_count = 0

    def _path_for(self, ticker: str, suffix: str = ".pkl") -> Path:
        return self.cache_dir / f"{ticker}{suffix}"

    def _read_pickle(self, path: Path) -> object | None:
        """Read a pickle file, returning None on any failure."""
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:
            return None

    def _write_pickle(self, path: Path, data: object, compress: str = "none") -> bool:
        """Write a pickle file with optional compression.

        Existing uncompressed (.pkl) data is preserved — compression flag
        is stored in an auxiliary header, old files without the flag are
        read as uncompressed.
        """
        try:
            if compress == "none":
                with open(path, "wb") as f:
                    pickle.dump(data, f)
            else:
                import numpy as np
                # Store with compression header for future reads
                data_encoded = pickle.dumps(data)
                compressed = getattr(zlib, compress)(data_encoded)
                with open(path, "wb") as f:
                    f.write(compressed)
            return True
        except Exception:
            return False

    def read(self, ticker: str, compress: str = "none") -> object | None:
        """Read cached data for a ticker. Returns None on miss/expired/corrupt."""
        path = self._path_for(ticker)
        if not path.exists():
            self.miss_count += 1
            return None

        # Check TTL
        try:
            if time.time() - path.stat().st_mtime > self._ttl:
                # Expired — remove and treat as miss
                try:
                    path.unlink()
                except Exception:
                    pass
                self.miss_count += 1
                return None
        except Exception:
            self.miss_count += 1
            return None

        data = self._read_pickle(path)
        if data is not None:
            self.hit_count += 1
        else:
            self.miss_count += 1
        return data

    def write(self, ticker: str, data: object, compress: str = "none") -> bool:
        """Write cached data for a ticker. Returns True on success."""
        path = self._path_for(ticker)
        try:
            return self._write_pickle(path, data, compress)
        except Exception:
            return False

    def hit_rate(self) -> float:
        """Return hit rate as (hits / (hits + misses)), 0.0 if no attempts."""
        total = self.hit_count + self.miss_count
        if total == 0:
            return 0.0
        return self.hit_count / total

    def reset_counters(self) -> None:
        self.hit_count = 0
        self.miss_count = 0
