"""Multi-Market Support for SENTINEL PRO (Phase 7).

Provides a market abstraction so the scanner can operate on US stocks,
cryptocurrency, and forex pairs — all through the same pipeline.

When ``markets.enabled`` is ``False`` (default), the scanner uses the
existing ``TICKERS`` list unchanged. While disabled, the scanner's default
behavior (310/30/15) is byte-for-byte unchanged.

Market types:
- ``US_STOCK`` — standard US equities (existing behavior)
- ``CRYPTO`` — cryptocurrency pairs via yfinance (BTC-USD, ETH-USD, …)
- ``FOREX`` — forex pairs via yfinance (EURUSD=X, …)

Each market provides its own ticker universe, yfinance parameters, and
sector classification. The ``MarketManager`` aggregates all enabled markets
into a single universe for scanning.
"""
from enum import Enum
from typing import Any, Dict, List, Optional


class MarketType(str, Enum):
    US_STOCK = "us_stock"
    CRYPTO = "crypto"
    FOREX = "forex"


# ───────────────────────────────────────────────────────────────────────
# Market definitions
# ───────────────────────────────────────────────────────────────────────

DEFAULT_CRYPTO_TICKERS = [
    "BTC-USD", "ETH-USD", "BNB-USD", "XRP-USD", "SOL-USD",
    "ADA-USD", "DOGE-USD", "AVAX-USD", "DOT-USD", "MATIC-USD",
    "LINK-USD", "UNI-USD", "SHIB-USD", "LTC-USD", "BCH-USD",
    "ATOM-USD", "FIL-USD", "APT-USD", "ARB-USD", "OP-USD",
    "NEAR-USD", "AAVE-USD", "MKR-USD", "GRT-USD", "INJ-USD",
    "SUI-USD", "SEI-USD", "TIA-USD", "JUP-USD", "RENDER-USD",
]

DEFAULT_FOREX_TICKERS = [
    "EURUSD=X", "GBPUSD=X", "USDJPY=X", "USDCHF=X",
    "AUDUSD=X", "USDCAD=X", "NZDUSD=X", "EURGBP=X",
    "EURJPY=X", "GBPJPY=X", "AUDJPY=X", "EURAUD=X",
    "EURCHF=X", "USDSEK=X", "USDNOK=X", "USDMXN=X",
]


class MarketProvider:
    """Represents a single market (US stocks, crypto, or forex).

    Each provider owns its ticker universe and yfinance parameters.
    """

    def __init__(
        self,
        name: str,
        market_type: MarketType,
        tickers: List[str],
        period: str = "700d",
        min_bars: int = 150,
        sector_label: Optional[str] = None,
    ):
        self.name = name
        self.market_type = market_type
        self.tickers = list(tickers)
        self.period = period
        self.min_bars = min_bars
        self.sector_label = sector_label or name

    def get_universe(self) -> List[str]:
        """Return the ticker list for this market."""
        return list(self.tickers)

    def normalize_ticker(self, ticker: str) -> str:
        """Normalize a ticker symbol for yfinance.

        Crypto/forex tickers are used as-is (yfinance format).
        US stocks are uppercased.
        """
        return ticker.upper()

    def get_sector(self, ticker: str) -> str:
        """Return sector classification for a ticker.

        Crypto/forex use the market name as sector.
        US stocks delegate to DataEngine.
        """
        if self.market_type in (MarketType.CRYPTO, MarketType.FOREX):
            return self.sector_label
        try:
            from engines.data import DataEngine
            return DataEngine.get_sector(ticker)
        except Exception:
            return "Unknown"

    def __repr__(self) -> str:
        return (
            f"MarketProvider(name={self.name!r}, type={self.market_type.value}, "
            f"tickers={len(self.tickers)}, period={self.period!r})"
        )


# ───────────────────────────────────────────────────────────────────────
# MarketManager — aggregates multiple markets
# ───────────────────────────────────────────────────────────────────────

class MarketManager:
    """Manages multiple MarketProviders and builds a combined universe.

    Usage::

        manager = MarketManager.from_config()
        tickers = manager.get_universe()
    """

    def __init__(self, providers: Optional[List[MarketProvider]] = None):
        self._providers: List[MarketProvider] = list(providers or [])

    @classmethod
    def from_config(cls) -> "MarketManager":
        """Build MarketManager from config.yaml ``markets:`` section."""
        try:
            from sentinel.config import get_config
            cfg = get_config()
            market_cfg = getattr(cfg, "markets", None)
            if market_cfg is None or not getattr(market_cfg, "enabled", False):
                return cls()
        except Exception:
            return cls()

        providers = []
        for mkt in getattr(market_cfg, "markets_list", []) or []:
            try:
                mt = MarketType(mkt.type)
            except (ValueError, AttributeError):
                continue
            providers.append(MarketProvider(
                name=mkt.name,
                market_type=mt,
                tickers=getattr(mkt, "tickers", []),
                period=getattr(mkt, "period", "700d"),
                min_bars=getattr(mkt, "min_bars", 150),
                sector_label=getattr(mkt, "sector_label", None),
            ))

        return cls(providers)

    @property
    def enabled(self) -> bool:
        """True if any markets are registered."""
        return len(self._providers) > 0

    def get_universe(self) -> List[str]:
        """Combined ticker list from all markets (deduplicated)."""
        seen: set[str] = set()
        result: List[str] = []
        for p in self._providers:
            for t in p.get_universe():
                normalized = p.normalize_ticker(t)
                if normalized not in seen:
                    seen.add(normalized)
                    result.append(t)
        return result

    def get_provider_for_ticker(self, ticker: str) -> Optional[MarketProvider]:
        """Find which provider owns a ticker."""
        for p in self._providers:
            for t in p.tickers:
                if p.normalize_ticker(t) == ticker.upper():
                    return p
        return None

    def get_all_provider_tickers(self) -> Dict[str, List[str]]:
        """Return {market_name: [tickers]} for all providers."""
        return {p.name: p.get_universe() for p in self._providers}

    def __len__(self) -> int:
        return len(self._providers)

    def __repr__(self) -> str:
        total = sum(len(p.tickers) for p in self._providers)
        return (
            f"MarketManager(markets={len(self._providers)}, "
            f"total_tickers={total})"
        )
