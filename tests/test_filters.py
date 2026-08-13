"""Phase 4 Filter framework tests (no network)."""
import pytest
import pandas as pd

from engines.filters import (
    STAGE_UNIVERSE,
    STAGE_CANDIDATE,
    Filter,
    FilterContext,
    FilterEngine,
    FilterResult,
    LiquidityFilter,
    MarketCapFilter,
    SectorFilter,
)


# ---------------------------------------------------------------------------
# Stub filters used to exercise the framework (concrete Phase 4 filters are
# added in later slices; these only prove engine behavior).
# ---------------------------------------------------------------------------

class _RejectAAPL(Filter):
    name = "reject_aapl"
    stage = STAGE_UNIVERSE

    def check(self, ctx: FilterContext) -> FilterResult:
        if ctx.ticker == "AAPL":
            return FilterResult(passed=False, reason="test reject AAPL")
        return FilterResult(passed=True)


class _RequireTechSector(Filter):
    name = "require_tech"
    stage = STAGE_UNIVERSE

    def check(self, ctx: FilterContext) -> FilterResult:
        # Default-permissive on missing data (framework contract).
        if ctx.sector is not None and ctx.sector != "Technology":
            return FilterResult(passed=False, reason=f"sector {ctx.sector!r}")
        return FilterResult(passed=True)


class _CandidateMinScore(Filter):
    name = "candidate_min_score"
    stage = STAGE_CANDIDATE

    def check(self, ctx: FilterContext) -> FilterResult:
        score = (ctx.profile or {}).get("score", 0)
        if score < 50:
            return FilterResult(passed=False, reason=f"score {score} < 50")
        return FilterResult(passed=True)


# ---------------------------------------------------------------------------
# Framework basics
# ---------------------------------------------------------------------------

def test_stage_constants():
    assert STAGE_UNIVERSE == "universe"
    assert STAGE_CANDIDATE == "candidate"


def test_filter_is_abstract():
    with pytest.raises(TypeError):
        Filter()


def test_filter_context_defaults():
    ctx = FilterContext(ticker="NVDA")
    assert ctx.ticker == "NVDA"
    assert ctx.df is None
    assert ctx.sector is None
    assert ctx.profile is None


def test_filter_result():
    r = FilterResult(passed=True)
    assert r.passed is True
    assert r.reason == ""
    r2 = FilterResult(passed=False, reason="low liquidity")
    assert r2.reason == "low liquidity"


def test_engine_default_disabled_identity():
    eng = FilterEngine()
    assert eng.enabled is False
    tickers = ["AAPL", "MSFT", "NVDA"]
    kept, rejected = eng.filter_universe(tickers)
    assert kept == tickers
    assert rejected == []


def test_engine_enabled_but_no_filters_identity():
    eng = FilterEngine(enabled=True)
    assert eng.enabled is True
    tickers = ["AAPL", "MSFT", "NVDA"]
    kept, rejected = eng.filter_universe(tickers)
    assert kept == tickers
    assert rejected == []


def test_engine_register_filters():
    eng = FilterEngine(enabled=True)
    eng.add(_RejectAAPL())
    eng.add(_CandidateMinScore())
    assert eng.names == ("reject_aapl", "candidate_min_score")
    assert len(eng.filters) == 2


def test_engine_duplicate_name_raises():
    eng = FilterEngine(enabled=True)
    eng.add(_RejectAAPL())
    with pytest.raises(ValueError):
        eng.add(_RejectAAPL())


def test_engine_add_non_filter_raises():
    eng = FilterEngine()
    with pytest.raises(TypeError):
        eng.add("not a filter")  # type: ignore[arg-type]


def test_engine_remove():
    eng = FilterEngine(enabled=True)
    eng.add(_RejectAAPL())
    eng.add(_RequireTechSector())
    eng.remove("reject_aapl")
    assert eng.names == ("require_tech",)
    eng.remove("does_not_exist")  # no-op
    assert eng.names == ("require_tech",)


# ---------------------------------------------------------------------------
# Execution
# ---------------------------------------------------------------------------

def test_filter_universe_applies_stage_filters():
    eng = FilterEngine(enabled=True, filters=[_RejectAAPL()])
    kept, rejected = eng.filter_universe(["AAPL", "MSFT", "NVDA"])
    assert kept == ["MSFT", "NVDA"]
    assert rejected == [{"ticker": "AAPL", "filter": "reject_aapl", "reason": "test reject AAPL"}]


def test_filter_universe_disabled_ignores_filters():
    eng = FilterEngine(enabled=False, filters=[_RejectAAPL()])
    kept, rejected = eng.filter_universe(["AAPL", "MSFT"])
    assert kept == ["AAPL", "MSFT"]
    assert rejected == []


def test_filter_universe_provider_supplies_context():
    eng = FilterEngine(enabled=True, filters=[_RequireTechSector()])
    sectors = {"AAPL": "Technology", "MSFT": "Technology", "XOM": "Energy"}
    kept, rejected = eng.filter_universe(
        ["AAPL", "MSFT", "XOM"],
        provider=lambda t: FilterContext(ticker=t, sector=sectors[t]),
    )
    assert kept == ["AAPL", "MSFT"]
    assert rejected == [{"ticker": "XOM", "filter": "require_tech", "reason": "sector 'Energy'"}]


def test_filter_universe_missing_provider_defaults_pass():
    eng = FilterEngine(enabled=True, filters=[_RequireTechSector()])
    kept, rejected = eng.filter_universe(["AAPL", "MSFT"])
    assert kept == ["AAPL", "MSFT"]
    assert rejected == []


def test_filter_universe_preserves_order_and_rejects_first_failing_filter():
    eng = FilterEngine(enabled=True, filters=[_RequireTechSector(), _RejectAAPL()])
    sectors = {"AAPL": "Technology", "MSFT": "Technology", "XOM": "Energy"}
    kept, rejected = eng.filter_universe(
        ["XOM", "AAPL", "MSFT"],
        provider=lambda t: FilterContext(ticker=t, sector=sectors.get(t)),
    )
    assert kept == ["MSFT"]
    assert rejected == [
        {"ticker": "XOM", "filter": "require_tech", "reason": "sector 'Energy'"},
        {"ticker": "AAPL", "filter": "reject_aapl", "reason": "test reject AAPL"},
    ]


def test_filter_candidates_applies_stage_filters():
    eng = FilterEngine(enabled=True, filters=[_CandidateMinScore()])
    candidates = ["NVDA", "MSFT", "AAPL"]
    kept, rejected = eng.filter_candidates(
        candidates,
        provider=lambda t: FilterContext(ticker=t, profile={"score": 30 if t == "AAPL" else 80}),
    )
    assert kept == ["NVDA", "MSFT"]
    assert rejected == [{"ticker": "AAPL", "filter": "candidate_min_score", "reason": "score 30 < 50"}]


def test_filter_stage_routing_universe_only():
    """A universe filter must not run during the candidate stage."""
    eng = FilterEngine(enabled=True, filters=[_RejectAAPL()])
    kept, rejected = eng.filter_candidates(["AAPL", "MSFT"])
    assert kept == ["AAPL", "MSFT"]
    assert rejected == []


def test_filter_stage_routing_candidate_only():
    """A candidate filter must not run during the universe stage."""
    eng = FilterEngine(enabled=True, filters=[_CandidateMinScore()])
    kept, rejected = eng.filter_universe(["AAPL", "MSFT"])
    assert kept == ["AAPL", "MSFT"]
    assert rejected == []


def test_filter_engine_deterministic():
    eng = FilterEngine(enabled=True, filters=[_RejectAAPL()])
    a = eng.filter_universe(["NVDA", "MSFT", "AAPL", "XOM"])
    b = eng.filter_universe(["NVDA", "MSFT", "AAPL", "XOM"])
    assert a == b


# ---------------------------------------------------------------------------
# from_config
# ---------------------------------------------------------------------------

def test_engine_from_config_disabled_identity():
    from sentinel.config import Config

    cfg = Config()  # filters default: disabled, all thresholds None
    eng = FilterEngine.from_config(config=cfg)
    assert eng.enabled is False
    assert eng.filters == ()
    tickers = ["AAPL", "MSFT"]
    assert eng.filter_universe(tickers) == (["AAPL", "MSFT"], [])


def test_engine_from_config_enabled_no_concrete_filters_yet():
    """Slice 4.1: enabled config yields an empty engine (concrete filters come
    in later slices) — so it is still an identity pass-through."""
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.enabled is True
    assert eng.filters == ()
    tickers = ["AAPL", "MSFT"]
    assert eng.filter_universe(tickers) == (["AAPL", "MSFT"], [])


def test_engine_from_config_enabled_override():
    from sentinel.config import Config

    cfg = Config()
    eng = FilterEngine.from_config(config=cfg, enabled_override=True)
    assert eng.enabled is True
    eng2 = FilterEngine.from_config(config=cfg, enabled_override=False)
    assert eng2.enabled is False


def test_engine_from_config_default_loads_current_yaml():
    eng = FilterEngine.from_config()
    assert eng.enabled is False  # config.yaml filters.enabled: false


def test_engine_add_many():
    eng = FilterEngine()
    eng.add_many([_RejectAAPL(), _CandidateMinScore()])
    assert eng.names == ("reject_aapl", "candidate_min_score")


def test_engine_context_accepts_dataframe():
    eng = FilterEngine(enabled=True, filters=[_RejectAAPL()])

    def provider(t: str) -> FilterContext:
        df = pd.DataFrame({"Close": [1.0, 2.0, 3.0], "Volume": [100, 200, 300]})
        return FilterContext(ticker=t, df=df)

    kept, _ = eng.filter_universe(["MSFT"], provider=provider)
    assert kept == ["MSFT"]


# ---------------------------------------------------------------------------
# LiquidityFilter (Phase 4.3)
# ---------------------------------------------------------------------------

def test_liquidity_filter_no_thresholds_passes():
    assert LiquidityFilter().check(FilterContext(ticker="AAPL")).passed is True


def test_liquidity_filter_rejects_low_dollar_volume():
    df = pd.DataFrame({"Close": [10, 11, 12], "Volume": [100, 100, 100]})  # avg dollar = 1100
    f = LiquidityFilter(min_avg_dollar_volume=5000)
    res = f.check(FilterContext(ticker="AAPL", df=df))
    assert res.passed is False
    assert "avg_dollar_volume" in res.reason


def test_liquidity_filter_passes_high_dollar_volume():
    df = pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]})  # avg dollar = 110000
    f = LiquidityFilter(min_avg_dollar_volume=50_000)
    assert f.check(FilterContext(ticker="AAPL", df=df)).passed is True


def test_liquidity_filter_dollar_volume_boundary_inclusive():
    df = pd.DataFrame({"Close": [10, 10, 10], "Volume": [100, 100, 100]})  # avg dollar = 1000
    assert LiquidityFilter(min_avg_dollar_volume=1000).check(FilterContext(ticker="AAPL", df=df)).passed is True
    assert LiquidityFilter(min_avg_dollar_volume=1000.01).check(FilterContext(ticker="AAPL", df=df)).passed is False


def test_liquidity_filter_rejects_low_volume():
    df = pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]})
    f = LiquidityFilter(min_avg_volume=5000)
    res = f.check(FilterContext(ticker="AAPL", df=df))
    assert res.passed is False
    assert "avg_volume" in res.reason


def test_liquidity_filter_volume_falls_back_to_profile():
    f = LiquidityFilter(min_avg_volume=1_000_000)
    assert f.check(FilterContext(ticker="AAPL", profile={"average_volume": 2_000_000})).passed is True
    res = f.check(FilterContext(ticker="AAPL", profile={"average_volume": 500_000}))
    assert res.passed is False
    assert "avg_volume" in res.reason


def test_liquidity_filter_missing_data_passes():
    f = LiquidityFilter(min_avg_dollar_volume=1e6, min_avg_volume=1e6)
    assert f.check(FilterContext(ticker="AAPL")).passed is True
    assert f.check(FilterContext(ticker="AAPL", df=pd.DataFrame())).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={})).passed is True


def test_liquidity_filter_both_thresholds_report_all_failures():
    df = pd.DataFrame({"Close": [100, 100, 100], "Volume": [1000, 1000, 1000]})  # dollar 100k, vol 1000
    f = LiquidityFilter(min_avg_dollar_volume=50_000, min_avg_volume=5000)
    res = f.check(FilterContext(ticker="AAPL", df=df))
    assert res.passed is False
    assert "avg_volume 1000 < 5000" in res.reason


# ---------------------------------------------------------------------------
# MarketCapFilter (Phase 4.3)
# ---------------------------------------------------------------------------

def test_market_cap_filter_no_thresholds_passes():
    assert MarketCapFilter().check(FilterContext(ticker="AAPL")).passed is True


def test_market_cap_filter_rejects_below_min():
    f = MarketCapFilter(min_usd=1e9)
    res = f.check(FilterContext(ticker="AAPL", profile={"market_cap": 500_000_000}))
    assert res.passed is False
    assert "market_cap" in res.reason


def test_market_cap_filter_rejects_above_max():
    f = MarketCapFilter(max_usd=5e11)
    res = f.check(FilterContext(ticker="AAPL", profile={"market_cap": 6e11}))
    assert res.passed is False
    assert "market_cap" in res.reason


def test_market_cap_filter_passes_within_range():
    f = MarketCapFilter(min_usd=1e9, max_usd=5e11)
    ctx = FilterContext(ticker="AAPL", profile={"market_cap": 2e11})
    assert f.check(ctx).passed is True


def test_market_cap_filter_boundary_inclusive():
    f = MarketCapFilter(min_usd=1e9, max_usd=5e11)
    assert f.check(FilterContext(ticker="AAPL", profile={"market_cap": 1e9})).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={"market_cap": 5e11})).passed is True


def test_market_cap_filter_missing_data_passes():
    f = MarketCapFilter(min_usd=1e9)
    assert f.check(FilterContext(ticker="AAPL")).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={})).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={"market_cap": None})).passed is True


# ---------------------------------------------------------------------------
# from_config wiring for concrete filters (Phase 4.3)
# ---------------------------------------------------------------------------

def test_from_config_builds_liquidity_filter():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True, "liquidity": {"min_avg_dollar_volume": 5_000_000}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("liquidity",)
    assert isinstance(eng.filters[0], LiquidityFilter)


def test_from_config_builds_market_cap_filter():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True, "market_cap": {"min_usd": 1e9}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("market_cap",)


def test_from_config_all_none_yields_no_filters():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.filters == ()


def test_from_config_builds_both_in_order():
    from sentinel.config import Config

    cfg = Config(filters={
        "enabled": True,
        "liquidity": {"min_avg_volume": 100_000},
        "market_cap": {"max_usd": 5e11},
    })
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("liquidity", "market_cap")


def test_from_config_disabled_builds_filters_but_identity():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": False, "liquidity": {"min_avg_volume": 100_000}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.enabled is False
    assert eng.names == ("liquidity",)  # constructed but never applied
    kept, rejected = eng.filter_universe(["AAPL", "MSFT"])
    assert kept == ["AAPL", "MSFT"]
    assert rejected == []


def test_engine_integration_liquidity_and_market_cap():
    from sentinel.config import Config

    cfg = Config(filters={
        "enabled": True,
        "liquidity": {"min_avg_dollar_volume": 100_000},
        "market_cap": {"min_usd": 1e9, "max_usd": 5e11},
    })
    eng = FilterEngine.from_config(config=cfg)

    def provider(t: str) -> FilterContext:
        if t == "BIG":
            return FilterContext(
                ticker=t,
                df=pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]}),
                profile={"market_cap": 2e11},
            )
        if t == "SMALLCAP":
            return FilterContext(
                ticker=t,
                df=pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]}),
                profile={"market_cap": 5e8},
            )
        return FilterContext(
            ticker=t,
            df=pd.DataFrame({"Close": [1, 1, 1], "Volume": [10, 10, 10]}),
            profile={"market_cap": 2e11},
        )

    kept, rejected = eng.filter_universe(["BIG", "SMALLCAP", "LOWLIQ"], provider=provider)
    assert kept == ["BIG"]
    assert [r["ticker"] for r in rejected] == ["SMALLCAP", "LOWLIQ"]
    assert rejected[0]["filter"] == "market_cap"
    assert rejected[1]["filter"] == "liquidity"


# ---------------------------------------------------------------------------
# SectorFilter (Phase 4.4)
# ---------------------------------------------------------------------------

def test_sector_filter_no_rules_passes():
    assert SectorFilter().check(FilterContext(ticker="AAPL")).passed is True
    assert SectorFilter(include=[], exclude=[]).check(FilterContext(ticker="AAPL")).passed is True


def test_sector_filter_include_matches():
    f = SectorFilter(include=["Technology", "Healthcare"])
    assert f.check(FilterContext(ticker="AAPL", sector="Technology")).passed is True
    assert f.check(FilterContext(ticker="JNJ", sector="Healthcare")).passed is True


def test_sector_filter_include_rejects():
    f = SectorFilter(include=["Technology"])
    res = f.check(FilterContext(ticker="XOM", sector="Energy"))
    assert res.passed is False
    assert "not in include" in res.reason


def test_sector_filter_exclude_rejects():
    f = SectorFilter(exclude=["Energy"])
    res = f.check(FilterContext(ticker="XOM", sector="Energy"))
    assert res.passed is False
    assert "in exclude" in res.reason


def test_sector_filter_exclude_allows_others():
    f = SectorFilter(exclude=["Energy"])
    assert f.check(FilterContext(ticker="AAPL", sector="Technology")).passed is True


def test_sector_filter_both_include_and_exclude():
    f = SectorFilter(include=["Technology", "Healthcare"], exclude=["Biotech"])
    assert f.check(FilterContext(ticker="AAPL", sector="Technology")).passed is True
    assert f.check(FilterContext(ticker="JNJ", sector="Healthcare")).passed is True
    assert f.check(FilterContext(ticker="XOM", sector="Energy")).passed is False
    assert f.check(FilterContext(ticker="PFE", sector="Healthcare")).passed is True


def test_sector_filter_case_insensitive_and_trimmed():
    f = SectorFilter(include=["  Technology "])
    assert f.check(FilterContext(ticker="AAPL", sector="technology")).passed is True
    assert f.check(FilterContext(ticker="AAPL", sector="  Technology  ")).passed is True
    assert f.check(FilterContext(ticker="XOM", sector="energy")).passed is False

    f2 = SectorFilter(exclude=[" ENERGY "])
    res = f2.check(FilterContext(ticker="XOM", sector="energy"))
    assert res.passed is False
    assert "in exclude" in res.reason


def test_sector_filter_missing_data_passes():
    f = SectorFilter(include=["Technology"], exclude=["Energy"])
    assert f.check(FilterContext(ticker="AAPL")).passed is True
    assert f.check(FilterContext(ticker="AAPL", sector=None)).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={})).passed is True
    assert f.check(FilterContext(ticker="AAPL", profile={"sector": None})).passed is True


def test_sector_filter_prefers_ctx_sector_over_profile():
    f = SectorFilter(include=["Technology"])
    ctx = FilterContext(ticker="AAPL", sector="Technology", profile={"sector": "Energy"})
    assert f.check(ctx).passed is True


def test_sector_filter_falls_back_to_profile_sector():
    f = SectorFilter(include=["Technology"])
    ctx = FilterContext(ticker="AAPL", profile={"sector": "Technology"})
    assert f.check(ctx).passed is True
    res = f.check(FilterContext(ticker="XOM", profile={"sector": "Energy"}))
    assert res.passed is False


def test_sector_filter_empty_include_means_all_allowed():
    f = SectorFilter(exclude=["Energy"])
    assert f.check(FilterContext(ticker="AAPL", sector="Technology")).passed is True
    assert f.check(FilterContext(ticker="MSFT", sector="Consumer Cyclical")).passed is True


# ---------------------------------------------------------------------------
# from_config wiring for SectorFilter (Phase 4.4)
# ---------------------------------------------------------------------------

def test_from_config_builds_sector_filter_include():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True, "sector": {"include": ["Technology", "Healthcare"]}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("sector",)
    assert isinstance(eng.filters[0], SectorFilter)


def test_from_config_builds_sector_filter_exclude():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True, "sector": {"exclude": ["Energy"]}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("sector",)
    assert eng.filters[0].exclude == ["energy"]


def test_from_config_empty_sector_yields_no_filter():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": True, "sector": {"include": [], "exclude": []}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.filters == ()


def test_from_config_order_liquidity_market_cap_sector():
    from sentinel.config import Config

    cfg = Config(filters={
        "enabled": True,
        "liquidity": {"min_avg_volume": 100_000},
        "market_cap": {"max_usd": 5e11},
        "sector": {"include": ["Technology"]},
    })
    eng = FilterEngine.from_config(config=cfg)
    assert eng.names == ("liquidity", "market_cap", "sector")


def test_from_config_disabled_sector_identity():
    from sentinel.config import Config

    cfg = Config(filters={"enabled": False, "sector": {"include": ["Technology"]}})
    eng = FilterEngine.from_config(config=cfg)
    assert eng.enabled is False
    kept, rejected = eng.filter_universe(["AAPL", "XOM"], provider=lambda t: FilterContext(ticker=t, sector="Energy"))
    assert kept == ["AAPL", "XOM"]
    assert rejected == []


def test_engine_integration_liquidity_market_cap_sector():
    from sentinel.config import Config

    cfg = Config(filters={
        "enabled": True,
        "liquidity": {"min_avg_dollar_volume": 100_000},
        "market_cap": {"min_usd": 1e9, "max_usd": 5e11},
        "sector": {"include": ["Technology", "Healthcare"]},
    })
    eng = FilterEngine.from_config(config=cfg)

    def provider(t: str) -> FilterContext:
        return FilterContext(
            ticker=t,
            df=pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]}),
            profile={"market_cap": 2e11},
            sector="Technology",
        )

    def provider_energy(t: str) -> FilterContext:
        return FilterContext(
            ticker=t,
            df=pd.DataFrame({"Close": [100, 110, 120], "Volume": [1000, 1000, 1000]}),
            profile={"market_cap": 2e11},
            sector="Energy",
        )

    kept, rejected = eng.filter_universe(["AAPL", "XOM"], provider=lambda t: provider(t) if t == "AAPL" else provider_energy(t))
    assert kept == ["AAPL"]
    assert [r["ticker"] for r in rejected] == ["XOM"]
    assert rejected[0]["filter"] == "sector"
