"""Phase 6.2 Pipeline Orchestrator tests (no network)."""
import pytest
from unittest.mock import MagicMock, patch

from engines.pipeline import Pipeline, PipelineResult


# ---------------------------------------------------------------------------
# PipelineResult tests
# ---------------------------------------------------------------------------

class TestPipelineResult:

    def test_to_dict_basic(self):
        r = PipelineResult(
            date="2026-08-18",
            timestamp="2026-08-18T10:00:00",
            runtime="5.0s",
            usd_jpy=150.0,
            scan_count=310,
            qualified_count=30,
            selected_count=15,
            selected=[],
            watchlist_wait=[],
            qualified_full=[],
        )
        d = r.to_dict()
        assert d["scan_count"] == 310
        assert d["selected_count"] == 15
        assert "regime" not in d
        assert "portfolio_risk" not in d

    def test_to_dict_with_regime(self):
        r = PipelineResult(
            date="2026-08-18",
            timestamp="2026-08-18T10:00:00",
            runtime="5.0s",
            usd_jpy=150.0,
            scan_count=310,
            qualified_count=30,
            selected_count=15,
            selected=[],
            watchlist_wait=[],
            qualified_full=[],
            regime={"regime": "bull", "score": 50},
        )
        d = r.to_dict()
        assert d["regime"]["regime"] == "bull"

    def test_to_dict_with_risk(self):
        r = PipelineResult(
            date="2026-08-18",
            timestamp="2026-08-18T10:00:00",
            runtime="5.0s",
            usd_jpy=150.0,
            scan_count=310,
            qualified_count=30,
            selected_count=15,
            selected=[],
            watchlist_wait=[],
            qualified_full=[],
            portfolio_risk={"total_heat": 0.03, "risk_level": "low"},
        )
        d = r.to_dict()
        assert d["portfolio_risk"]["risk_level"] == "low"


# ---------------------------------------------------------------------------
# Pipeline construction tests
# ---------------------------------------------------------------------------

class TestPipelineConstruction:

    def test_default_init(self):
        p = Pipeline()
        assert p._config is None

    def test_from_config(self):
        p = Pipeline.from_config()
        assert p._config is not None

    def test_custom_universe(self):
        tickers = ["AAPL", "MSFT", "GOOGL"]
        p = Pipeline(universe=tickers)
        assert p._universe == tickers

    def test_custom_providers(self):
        data_fn = lambda t: None
        p = Pipeline(data_provider=data_fn)
        assert p._data_provider is data_fn

    def test_output_dir(self):
        from pathlib import Path
        p = Pipeline(output_dir=Path("/tmp/test_output"))
        assert p._output_dir == Path("/tmp/test_output")


# ---------------------------------------------------------------------------
# Pipeline sorting tests
# ---------------------------------------------------------------------------

class TestPipelineSort:

    def test_sort_candidates(self):
        qualified = [
            {"status": "EXTENDED", "rs": 80, "vcp": {"score": 60}, "pf": 1.0},
            {"status": "ACTION", "rs": 70, "vcp": {"score": 55}, "pf": 2.0},
            {"status": "WAIT", "rs": 90, "vcp": {"score": 70}, "pf": 1.5},
        ]
        result = Pipeline._sort_candidates(qualified)
        # ACTION first, then WAIT, then EXTENDED
        assert result[0]["status"] == "ACTION"
        assert result[1]["status"] == "WAIT"
        assert result[2]["status"] == "EXTENDED"

    def test_sort_same_status(self):
        qualified = [
            {"status": "ACTION", "rs": 70, "vcp": {"score": 55}, "pf": 1.0},
            {"status": "ACTION", "rs": 90, "vcp": {"score": 70}, "pf": 3.0},
        ]
        result = Pipeline._sort_candidates(qualified)
        # Higher composite score first
        assert result[0]["rs"] == 90


# ---------------------------------------------------------------------------
# Pipeline sector diversification tests
# ---------------------------------------------------------------------------

class TestPipelineDiversify:

    def test_sector_limit(self):
        qualified = [
            {"status": "ACTION", "ticker": "A", "sector": "Tech", "rs": 80, "vcp": {"score": 60}, "pf": 1.0},
            {"status": "ACTION", "ticker": "B", "sector": "Tech", "rs": 75, "vcp": {"score": 55}, "pf": 1.0},
            {"status": "ACTION", "ticker": "C", "sector": "Tech", "rs": 70, "vcp": {"score": 50}, "pf": 1.0},
            {"status": "ACTION", "ticker": "D", "sector": "Health", "rs": 65, "vcp": {"score": 45}, "pf": 1.0},
        ]
        p = Pipeline()
        result = p._sector_diversify(qualified)
        # Only 2 from Tech + 1 from Health
        assert len(result) == 3
        tech_count = sum(1 for r in result if r["sector"] == "Tech")
        assert tech_count <= 2

    def test_max_positions(self):
        qualified = [
            {"status": "ACTION", "ticker": f"T{i}", "sector": f"S{i}",
             "rs": 80 - i, "vcp": {"score": 60}, "pf": 1.0}
            for i in range(30)
        ]
        p = Pipeline()
        result = p._sector_diversify(qualified)
        assert len(result) <= 20  # default max_positions


# ---------------------------------------------------------------------------
# Config integration tests
# ---------------------------------------------------------------------------

class TestPipelineConfig:

    def test_pipeline_config_read(self):
        from sentinel.config import PipelineConfig
        cfg = PipelineConfig()
        assert cfg.enabled is False
        assert cfg.rs == "legacy"
        assert cfg.strategies.vcp_breakout is False
        assert cfg.strategies.minervini is False
        assert cfg.backtest.enabled is False


__all__ = [
    "TestPipelineResult",
    "TestPipelineConstruction",
    "TestPipelineSort",
    "TestPipelineDiversify",
    "TestPipelineConfig",
]
