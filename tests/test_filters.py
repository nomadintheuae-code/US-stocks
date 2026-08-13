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
