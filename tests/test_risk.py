"""Phase 10 Enhanced Risk Management tests (no network)."""
import numpy as np
import pandas as pd
import pytest

from engines.risk import (
    PositionSizer,
    PositionSize,
    PortfolioRisk,
    PortfolioRiskResult,
    StopManager,
)


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 50, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 2)
    high = close + rng.uniform(0.5, 3.0, n)
    low = close - rng.uniform(0.5, 3.0, n)
    opn = close + rng.randn(n) * 0.5
    vol = rng.randint(100000, 1000000, n).astype(float)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": opn, "High": high, "Low": low, "Close": close, "Volume": vol,
    }, index=dates)


# ---------------------------------------------------------------------------
# PositionSizer tests
# ---------------------------------------------------------------------------

class TestPositionSizer:

    def test_calculate_atr(self):
        df = _make_ohlcv(50)
        atr = PositionSizer.calculate_atr(df)
        assert atr is not None
        assert atr > 0

    def test_calculate_atr_insufficient(self):
        atr = PositionSizer.calculate_atr(_make_ohlcv(5))
        assert atr is None

    def test_size_position(self):
        df = _make_ohlcv(50)
        result = PositionSizer.size_position(df, capital=100000)
        assert result is not None
        assert isinstance(result, PositionSize)
        assert result.shares >= 1
        assert result.dollar_amount > 0
        assert result.risk_amount > 0
        assert result.risk_pct > 0

    def test_size_position_regime_adjusted(self):
        df = _make_ohlcv(50)
        full = PositionSizer.size_position(df, capital=100000, regime_mult=1.0)
        reduced = PositionSizer.size_position(df, capital=100000, regime_mult=0.5)
        assert full is not None
        assert reduced is not None
        assert reduced.shares <= full.shares

    def test_size_position_capital_limit(self):
        df = _make_ohlcv(50)
        result = PositionSizer.size_position(df, capital=1000)
        assert result is not None
        assert result.dollar_amount <= 1000 * 0.95

    def test_size_position_empty(self):
        result = PositionSizer.size_position(None, capital=100000)
        assert result is None

    def test_position_size_to_dict(self):
        df = _make_ohlcv(50)
        result = PositionSizer.size_position(df, capital=100000)
        d = result.to_dict()
        assert "shares" in d
        assert "dollar_amount" in d
        assert "risk_amount" in d


# ---------------------------------------------------------------------------
# PortfolioRisk tests
# ---------------------------------------------------------------------------

class TestPortfolioRisk:

    def test_calculate_heat_empty(self):
        assert PortfolioRisk.calculate_heat([], 100000) == 0.0

    def test_calculate_heat(self):
        positions = [
            {"shares": 10, "stop_distance": 5.0},  # risk = 50
            {"shares": 20, "stop_distance": 3.0},  # risk = 60
        ]
        heat = PortfolioRisk.calculate_heat(positions, 100000)
        assert heat == pytest.approx(0.0011, rel=0.01)

    def test_sector_concentration(self):
        positions = [
            {"sector": "Technology"},
            {"sector": "Technology"},
            {"sector": "Healthcare"},
        ]
        counts, max_pct = PortfolioRisk.sector_concentration(positions)
        assert counts["Technology"] == 2
        assert counts["Healthcare"] == 1
        assert max_pct == pytest.approx(2 / 3, rel=0.01)

    def test_sector_concentration_empty(self):
        counts, max_pct = PortfolioRisk.sector_concentration([])
        assert counts == {}
        assert max_pct == 0.0

    def test_check_correlation(self):
        rng = np.random.RandomState(42)
        r1 = pd.Series(rng.randn(100))
        r2 = r1 + rng.randn(100) * 0.1  # highly correlated
        r3 = pd.Series(rng.randn(100))  # uncorrelated

        warnings = PortfolioRisk.check_correlation(
            {"A": r1, "B": r2, "C": r3}, threshold=0.7
        )
        assert any("A" in w and "B" in w for w in warnings)

    def test_analyze(self):
        positions = [
            {"ticker": "AAPL", "shares": 10, "sector": "Technology",
             "stop_distance": 5.0, "risk_amount": 50},
            {"ticker": "MSFT", "shares": 10, "sector": "Technology",
             "stop_distance": 5.0, "risk_amount": 50},
        ]
        result = PortfolioRisk.analyze(positions, 100000)
        assert isinstance(result, PortfolioRiskResult)
        assert result.position_count == 2
        assert result.risk_level in ("low", "medium", "high", "critical")

    def test_analyze_critical_heat(self):
        # High risk per position
        positions = [
            {"ticker": f"T{i}", "shares": 100, "sector": "Tech",
             "stop_distance": 50.0, "risk_amount": 5000}
            for i in range(5)
        ]
        result = PortfolioRisk.analyze(positions, 100000, max_heat=0.01)
        assert result.risk_level in ("high", "critical")

    def test_analyze_to_dict(self):
        result = PortfolioRisk.analyze([], 100000)
        d = result.to_dict()
        assert "total_heat" in d
        assert "risk_level" in d


# ---------------------------------------------------------------------------
# StopManager tests
# ---------------------------------------------------------------------------

class TestStopManager:

    def test_trailing_stop(self):
        stop = StopManager.trailing_stop(
            entry=100.0, current=110.0, highest_since_entry=110.0, trail_pct=0.05
        )
        assert stop == 104.5

    def test_trailing_stop_never_below_initial(self):
        stop = StopManager.trailing_stop(
            entry=100.0, current=95.0, highest_since_entry=100.0, trail_pct=0.05
        )
        assert stop >= 95.0

    def test_time_stop_triggered(self):
        triggered, reason = StopManager.time_stop(
            "2025-01-01", "2025-02-01", max_days=20, current_return=0.02
        )
        assert triggered is True
        assert "Time stop" in reason

    def test_time_stop_not_triggered(self):
        triggered, reason = StopManager.time_stop(
            "2025-01-01", "2025-01-10", max_days=20, current_return=0.02
        )
        assert triggered is False

    def test_time_stop_profit_avoids(self):
        triggered, reason = StopManager.time_stop(
            "2025-01-01", "2025-02-01", max_days=20,
            profit_threshold=0.05, current_return=0.10
        )
        assert triggered is False

    def test_atr_stop(self):
        stop = StopManager.atr_stop(entry=100.0, atr=3.0, multiplier=2.0)
        assert stop == 94.0

    def test_risk_reward_ratio(self):
        rr = StopManager.risk_reward_ratio(entry=100.0, stop=95.0, target=115.0)
        assert rr == 3.0

    def test_risk_reward_zero_risk(self):
        rr = StopManager.risk_reward_ratio(entry=100.0, stop=100.0, target=110.0)
        assert rr == 0.0


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestRiskConfig:

    def test_defaults(self):
        from sentinel.config import RiskConfig
        cfg = RiskConfig()
        assert cfg.enabled is False
        assert cfg.position_sizing.risk_per_trade_pct == 0.015
        assert cfg.portfolio.max_heat_pct == 0.06
        assert cfg.stops.trailing_pct == 0.05


__all__ = [
    "TestPositionSizer",
    "TestPortfolioRisk",
    "TestStopManager",
    "TestRiskConfig",
]
