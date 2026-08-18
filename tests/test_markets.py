"""Phase 7 Multi-Market Support tests (no network)."""
import pytest
from unittest.mock import MagicMock, patch

from engines.markets import MarketManager, MarketProvider, MarketType


# ---------------------------------------------------------------------------
# MarketType tests
# ---------------------------------------------------------------------------

class TestMarketType:

    def test_enum_values(self):
        assert MarketType.US_STOCK.value == "us_stock"
        assert MarketType.CRYPTO.value == "crypto"
        assert MarketType.FOREX.value == "forex"

    def test_from_string(self):
        assert MarketType("us_stock") == MarketType.US_STOCK
        assert MarketType("crypto") == MarketType.CRYPTO
        assert MarketType("forex") == MarketType.FOREX


# ---------------------------------------------------------------------------
# MarketProvider tests
# ---------------------------------------------------------------------------

class TestMarketProvider:

    def test_us_stock_provider(self):
        p = MarketProvider(
            name="US Stocks",
            market_type=MarketType.US_STOCK,
            tickers=["AAPL", "MSFT", "GOOGL"],
        )
        assert len(p.get_universe()) == 3
        assert p.normalize_ticker("aapl") == "AAPL"
        # US stock get_sector delegates to DataEngine (may return cached value)
        sector = p.get_sector("AAPL")
        assert isinstance(sector, str)
        assert len(sector) > 0

    def test_crypto_provider(self):
        p = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD", "ETH-USD"],
            sector_label="Cryptocurrency",
        )
        assert p.get_universe() == ["BTC-USD", "ETH-USD"]
        assert p.normalize_ticker("btc-usd") == "BTC-USD"
        assert p.get_sector("BTC-USD") == "Cryptocurrency"

    def test_forex_provider(self):
        p = MarketProvider(
            name="Forex",
            market_type=MarketType.FOREX,
            tickers=["EURUSD=X", "GBPUSD=X"],
            sector_label="Forex",
        )
        assert p.get_universe() == ["EURUSD=X", "GBPUSD=X"]
        assert p.get_sector("EURUSD=X") == "Forex"

    def test_repr(self):
        p = MarketProvider(
            name="Test",
            market_type=MarketType.US_STOCK,
            tickers=["A", "B", "C"],
        )
        r = repr(p)
        assert "Test" in r
        assert "tickers=3" in r

    def test_period_and_min_bars(self):
        p = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD"],
            period="365d",
            min_bars=100,
        )
        assert p.period == "365d"
        assert p.min_bars == 100

    def test_get_universe_returns_copy(self):
        p = MarketProvider(
            name="Test",
            market_type=MarketType.US_STOCK,
            tickers=["A", "B"],
        )
        u1 = p.get_universe()
        u2 = p.get_universe()
        assert u1 == u2
        u1.append("C")
        assert len(u2) == 2  # original unchanged


# ---------------------------------------------------------------------------
# MarketManager tests
# ---------------------------------------------------------------------------

class TestMarketManager:

    def test_empty_manager(self):
        m = MarketManager()
        assert not m.enabled
        assert m.get_universe() == []
        assert len(m) == 0

    def test_single_market(self):
        p = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD", "ETH-USD"],
        )
        m = MarketManager([p])
        assert m.enabled
        assert m.get_universe() == ["BTC-USD", "ETH-USD"]
        assert len(m) == 1

    def test_multi_market_combined(self):
        stocks = MarketProvider(
            name="US Stocks",
            market_type=MarketType.US_STOCK,
            tickers=["AAPL", "MSFT"],
        )
        crypto = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD", "ETH-USD"],
        )
        forex = MarketProvider(
            name="Forex",
            market_type=MarketType.FOREX,
            tickers=["EURUSD=X"],
        )
        m = MarketManager([stocks, crypto, forex])
        universe = m.get_universe()
        assert len(universe) == 5
        assert "AAPL" in universe
        assert "BTC-USD" in universe
        assert "EURUSD=X" in universe

    def test_deduplication(self):
        stocks = MarketProvider(
            name="A",
            market_type=MarketType.US_STOCK,
            tickers=["AAPL", "MSFT"],
        )
        crypto = MarketProvider(
            name="B",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD", "ETH-USD"],
        )
        m = MarketManager([stocks, crypto])
        universe = m.get_universe()
        assert len(universe) == 4  # no dups

    def test_get_provider_for_ticker(self):
        stocks = MarketProvider(
            name="US",
            market_type=MarketType.US_STOCK,
            tickers=["AAPL"],
        )
        crypto = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD"],
        )
        m = MarketManager([stocks, crypto])
        assert m.get_provider_for_ticker("AAPL") is stocks
        assert m.get_provider_for_ticker("BTC-USD") is crypto
        assert m.get_provider_for_ticker("XYZ") is None

    def test_get_all_provider_tickers(self):
        stocks = MarketProvider(
            name="US",
            market_type=MarketType.US_STOCK,
            tickers=["AAPL"],
        )
        crypto = MarketProvider(
            name="Crypto",
            market_type=MarketType.CRYPTO,
            tickers=["BTC-USD", "ETH-USD"],
        )
        m = MarketManager([stocks, crypto])
        result = m.get_all_provider_tickers()
        assert result == {"US": ["AAPL"], "Crypto": ["BTC-USD", "ETH-USD"]}

    def test_repr(self):
        m = MarketManager([
            MarketProvider(name="A", market_type=MarketType.US_STOCK, tickers=["X"]),
            MarketProvider(name="B", market_type=MarketType.CRYPTO, tickers=["Y", "Z"]),
        ])
        r = repr(m)
        assert "markets=2" in r
        assert "total_tickers=3" in r


# ---------------------------------------------------------------------------
# Config integration tests
# ---------------------------------------------------------------------------

class TestMarketConfig:

    def test_markets_config_default(self):
        from sentinel.config import MarketsConfig
        cfg = MarketsConfig()
        assert cfg.enabled is False
        assert cfg.markets_list == []

    def test_market_item_config_validation(self):
        from sentinel.config import MarketItemConfig
        m = MarketItemConfig(
            name="Crypto",
            type="crypto",
            tickers=["BTC-USD"],
        )
        assert m.name == "Crypto"
        assert m.type == "crypto"
        assert m.enabled is False
        assert m.period == "700d"

    def test_market_item_invalid_type(self):
        from sentinel.config import MarketItemConfig
        with pytest.raises(ValueError, match="Market type"):
            MarketItemConfig(name="Bad", type="invalid", tickers=[])

    def test_markets_config_in_main_config(self):
        from sentinel.config import Config
        cfg = Config()
        assert hasattr(cfg, "markets")
        assert cfg.markets.enabled is False


# ---------------------------------------------------------------------------
# from_config factory tests
# ---------------------------------------------------------------------------

class TestMarketManagerFromConfig:

    def test_from_config_disabled(self):
        from sentinel.config import Config
        cfg = Config()
        with patch("sentinel.config.get_config", return_value=cfg):
            m = MarketManager.from_config()
            assert not m.enabled

    def test_from_config_with_markets(self):
        from sentinel.config import Config, MarketsConfig, MarketItemConfig
        cfg = Config()
        cfg.markets = MarketsConfig(
            enabled=True,
            markets_list=[
                MarketItemConfig(
                    name="Crypto",
                    type="crypto",
                    enabled=True,
                    tickers=["BTC-USD", "ETH-USD"],
                    sector_label="Cryptocurrency",
                ),
            ],
        )
        with patch("sentinel.config.get_config", return_value=cfg):
            m = MarketManager.from_config()
            assert m.enabled
            assert m.get_universe() == ["BTC-USD", "ETH-USD"]


__all__ = [
    "TestMarketType",
    "TestMarketProvider",
    "TestMarketManager",
    "TestMarketConfig",
    "TestMarketManagerFromConfig",
]
