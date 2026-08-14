"""Configuration system tests (no network)."""
import pytest

from sentinel.config import Config, get_config


def test_root_config_yaml_loaded():
    """config.yaml at the project root must be the single source of truth."""
    cfg = get_config()
    assert cfg.capital.jpy == 1_000_000
    assert cfg.capital.max_positions == 20
    assert cfg.capital.account_risk_pct == 0.015
    assert cfg.capital.max_same_sector == 2
    assert cfg.scan.min_rs_rating == 70
    assert cfg.scan.min_vcp_score == 55
    assert cfg.scan.min_profit_factor == 1.1
    assert cfg.exit.stop_loss_atr == 2.0
    assert cfg.exit.target_r_multiple == 2.5
    assert cfg.vcp.tightness_periods == [20, 30, 40, 60]
    assert cfg.rs.windows == [252, 126, 63, 21]
    assert cfg.rs.weights == [0.4, 0.2, 0.2, 0.2]
    assert cfg.cache.price_expiry_hours == 12
    assert cfg.cache.fundamental_expiry_hours == 24
    assert cfg.cache.news_expiry_hours == 1
    assert cfg.data.filter_delisted is True


def test_get_config_singleton():
    assert get_config() is get_config()


def test_env_override_capital(monkeypatch):
    monkeypatch.setenv("CAPITAL_JPY", "500000")
    cfg = Config.load()
    assert cfg.capital.jpy == 500000


def test_env_override_scan_filter(monkeypatch):
    monkeypatch.setenv("MIN_RS_RATING", "80")
    cfg = Config.load()
    assert cfg.scan.min_rs_rating == 80


def test_env_override_exit(monkeypatch):
    monkeypatch.setenv("STOP_LOSS_ATR", "3.0")
    cfg = Config.load()
    assert cfg.exit.stop_loss_atr == 3.0


def test_cache_expiry_seconds():
    cfg = get_config()
    assert cfg.get_cache_expiry_seconds("price") == 12 * 3600
    assert cfg.get_cache_expiry_seconds("fundamental") == 24 * 3600
    assert cfg.get_cache_expiry_seconds("news") == 3600
    assert cfg.get_cache_expiry_seconds("unknown") == 3600


def test_backward_compat_wrapper_consistent():
    """Root config.py wrapper must mirror the new Config object."""
    import config as root_config

    cfg = get_config()
    assert root_config.CONFIG["CAPITAL_JPY"] == cfg.capital.jpy
    assert root_config.CONFIG["MIN_RS_RATING"] == cfg.scan.min_rs_rating
    assert root_config.CONFIG["STOP_LOSS_ATR"] == cfg.exit.stop_loss_atr
    assert root_config.CONFIG["TARGET_R_MULTIPLE"] == cfg.exit.target_r_multiple
    assert root_config.CONFIG["CACHE_EXPIRY"] == cfg.get_cache_expiry_seconds("price")


def test_delisted_tickers_filtered():
    import config as root_config

    assert "BITF" not in root_config.TICKERS
    assert "CFLT" not in root_config.TICKERS
    assert "DVAX" not in root_config.TICKERS
    assert "HOLX" not in root_config.TICKERS
    assert "MMC" not in root_config.TICKERS
    assert "AAPL" in root_config.TICKERS
    assert len(root_config.TICKERS) > 100


# --- UniverseManager (Phase 2.4.2C) ------------------------------------------

def test_universemanager_importable():
    from config import UniverseManager
    assert UniverseManager is not None


def test_universemanager_construction():
    from config import UniverseManager
    m = UniverseManager()
    assert m._filter_delisted is True
    assert m._delisted == {"BITF", "CFLT", "DVAX", "HOLX", "MMC"}
    assert m._universe_file == ""


def test_universemanager_from_config():
    from config import UniverseManager
    m = UniverseManager.from_config()
    assert m.load() == UniverseManager().load()


def test_universemanager_load_matches_current_universe():
    """Manager output must equal the existing config.TICKERS (310 active)."""
    import config as root_config
    from config import UniverseManager

    m = UniverseManager()
    assert m.load() == root_config.TICKERS
    assert m.tickers == root_config.TICKERS
    assert len(m) == len(root_config.TICKERS) == 310
    assert list(m) == root_config.TICKERS


def test_universemanager_deterministic_ordering():
    from config import UniverseManager
    m = UniverseManager()
    assert m.load() == sorted(m.load())
    assert len(m.load()) == len(set(m.load()))
    assert m.load() == m.load() == UniverseManager().load()


def test_universemanager_validate():
    from config import UniverseManager
    m = UniverseManager()
    out = m.validate(["aapl", "MSFT", "  nvda ", "aapl", "", "xom"])
    assert out == ["AAPL", "MSFT", "NVDA", "XOM"]
    assert m.validate([]) == []
    assert m.validate(None) == []


def test_universemanager_delisted_filtered_by_default():
    from config import UniverseManager
    for t in UniverseManager.DELISTED:
        assert t not in UniverseManager().load()


def test_universemanager_delisted_filter_disabled():
    from config import UniverseManager
    loaded = UniverseManager(filter_delisted=False).load()
    assert all(t in loaded for t in UniverseManager.DELISTED)


def test_universemanager_filter_delisted_tickers():
    from config import UniverseManager
    m = UniverseManager()
    out = m.filter_delisted_tickers(["AAPL", "BITF", "MSFT", "MMC"])
    assert out == ["AAPL", "MSFT"]


def test_universemanager_custom_delisted_set():
    from config import UniverseManager
    m = UniverseManager(delisted={"AAPL", "MSFT"})
    assert "AAPL" not in m.load()
    assert "BITF" in m.load()  # built-in delisted set replaced


def test_universemanager_custom_base_tickers():
    from config import UniverseManager
    m = UniverseManager(tickers=["msft", "aapl", "MSFT", "zzz"])
    assert m.load() == ["AAPL", "MSFT", "ZZZ"]


def test_universemanager_external_universe_file(tmp_path):
    from config import UniverseManager
    f = tmp_path / "universe.txt"
    f.write_text("# comment line\n\n  aapl  \nMSFT\nnvidia\n", encoding="utf-8")
    m = UniverseManager(universe_file=str(f))
    assert m.load() == ["AAPL", "MSFT", "NVIDIA"]


def test_universemanager_external_file_order_preserved(tmp_path):
    from config import UniverseManager
    f = tmp_path / "universe.txt"
    f.write_text("Z\nAAPL\nMSFT\n", encoding="utf-8")
    m = UniverseManager(universe_file=str(f))
    assert m.load() == ["Z", "AAPL", "MSFT"]


def test_universemanager_external_missing_file_falls_back():
    from config import UniverseManager
    m = UniverseManager(universe_file="/nonexistent/path/universe.txt")
    assert m.load() == UniverseManager().load()


def test_universemanager_external_empty_file_falls_back(tmp_path):
    from config import UniverseManager
    f = tmp_path / "empty.txt"
    f.write_text("", encoding="utf-8")
    m = UniverseManager(universe_file=str(f))
    assert m.load() == UniverseManager().load()


# --- FilterConfig (Phase 4.1) ------------------------------------------------

def test_filters_config_default_disabled():
    cfg = get_config()
    assert cfg.filters.enabled is False
    assert cfg.filters.liquidity.min_avg_dollar_volume is None
    assert cfg.filters.liquidity.min_avg_volume is None
    assert cfg.filters.market_cap.min_usd is None
    assert cfg.filters.market_cap.max_usd is None
    assert cfg.filters.sector.include == []
    assert cfg.filters.sector.exclude == []
    assert cfg.filters.fundamental.min_revenue_growth is None
    assert cfg.filters.fundamental.min_earnings_growth is None
    assert cfg.filters.fundamental.max_forward_pe is None
    assert cfg.filters.fundamental.min_analyst_count is None


def test_filters_config_loads_values():
    cfg = Config(filters={
        "enabled": True,
        "liquidity": {"min_avg_dollar_volume": 5_000_000, "min_avg_volume": 100_000},
        "market_cap": {"min_usd": 1e9, "max_usd": 5e11},
        "sector": {"include": ["Technology"], "exclude": ["Energy"]},
        "fundamental": {"min_revenue_growth": 0.1, "max_forward_pe": 40.0, "min_analyst_count": 5},
    })
    assert cfg.filters.enabled is True
    assert cfg.filters.liquidity.min_avg_dollar_volume == 5_000_000
    assert cfg.filters.liquidity.min_avg_volume == 100_000
    assert cfg.filters.market_cap.min_usd == 1e9
    assert cfg.filters.market_cap.max_usd == 5e11
    assert cfg.filters.sector.include == ["Technology"]
    assert cfg.filters.sector.exclude == ["Energy"]
    assert cfg.filters.fundamental.min_revenue_growth == 0.1
    assert cfg.filters.fundamental.min_earnings_growth is None
    assert cfg.filters.fundamental.max_forward_pe == 40.0
    assert cfg.filters.fundamental.min_analyst_count == 5


def test_filters_market_cap_range_validation():
    with pytest.raises(Exception):
        Config(filters={"market_cap": {"min_usd": 1e12, "max_usd": 1e9}})


def test_filters_sector_include_exclude_overlap():
    with pytest.raises(Exception):
        Config(filters={"sector": {"include": ["Technology"], "exclude": ["Technology"]}})


def test_filters_fundamental_bounds():
    with pytest.raises(Exception):
        Config(filters={"fundamental": {"max_forward_pe": 0}})
    with pytest.raises(Exception):
        Config(filters={"fundamental": {"min_revenue_growth": 15}})
    with pytest.raises(Exception):
        Config(filters={"fundamental": {"min_earnings_growth": -2}})
    with pytest.raises(Exception):
        Config(filters={"fundamental": {"min_analyst_count": 500}})


def test_filters_config_optional_null_accepted():
    cfg = Config(filters={
        "liquidity": {"min_avg_dollar_volume": None, "min_avg_volume": None},
    })
    assert cfg.filters.liquidity.min_avg_dollar_volume is None
    assert cfg.filters.liquidity.min_avg_volume is None


# --- PipelineConfig (Phase 6.1) ----------------------------------------------

def test_pipeline_config_default_disabled():
    """Pipeline must default to fully disabled (legacy behavior preserved)."""
    cfg = get_config()
    assert cfg.pipeline.enabled is False
    assert cfg.pipeline.rs == "legacy"
    assert cfg.pipeline.strategies.vcp_breakout is False
    assert cfg.pipeline.strategies.minervini is False
    assert cfg.pipeline.backtest.enabled is False


def test_pipeline_config_loads_values():
    cfg = Config(pipeline={
        "enabled": True,
        "rs": "benchmark",
        "strategies": {"vcp_breakout": True, "minervini": True},
        "backtest": {"enabled": True},
    })
    assert cfg.pipeline.enabled is True
    assert cfg.pipeline.rs == "benchmark"
    assert cfg.pipeline.strategies.vcp_breakout is True
    assert cfg.pipeline.strategies.minervini is True
    assert cfg.pipeline.backtest.enabled is True


def test_pipeline_config_default_factories():
    cfg = Config()
    assert cfg.pipeline.strategies.vcp_breakout is False
    assert cfg.pipeline.strategies.minervini is False
    assert cfg.pipeline.backtest.enabled is False


def test_pipeline_rs_provider_validation():
    with pytest.raises(Exception):
        Config(pipeline={"rs": "unknown"})
    assert Config(pipeline={"rs": "legacy"}).pipeline.rs == "legacy"
    assert Config(pipeline={"rs": "benchmark"}).pipeline.rs == "benchmark"
