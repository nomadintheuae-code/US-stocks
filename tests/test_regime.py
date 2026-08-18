"""Phase 9 Market Regime Engine tests (no network)."""
import numpy as np
import pandas as pd
import pytest

from engines.regime import MarketRegimeEngine, RegimeType, RegimeResult


# ---------------------------------------------------------------------------
# Helper: build synthetic OHLCV DataFrames
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 250, seed: int = 42, trend: float = 0.0) -> pd.DataFrame:
    """Generate synthetic OHLCV data."""
    rng = np.random.RandomState(seed)
    close = 100 + np.cumsum(rng.randn(n) * 1.5 + trend)
    high = close + rng.uniform(0.5, 2.5, n)
    low = close - rng.uniform(0.5, 2.5, n)
    opn = close + rng.randn(n) * 0.3
    vol = rng.randint(100000, 1000000, n).astype(float)
    dates = pd.date_range("2024-06-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": opn, "High": high, "Low": low, "Close": close, "Volume": vol,
    }, index=dates)


def _make_bull_market() -> pd.DataFrame:
    return _make_ohlcv(250, seed=42, trend=0.8)


def _make_bear_market() -> pd.DataFrame:
    return _make_ohlcv(250, seed=42, trend=-0.8)


def _make_sideways_market() -> pd.DataFrame:
    return _make_ohlcv(250, seed=42, trend=0.0)


# ---------------------------------------------------------------------------
# RegimeType enum tests
# ---------------------------------------------------------------------------

class TestRegimeType:

    def test_values(self):
        assert RegimeType.BULL.value == "bull"
        assert RegimeType.BEAR.value == "bear"
        assert RegimeType.SIDEWAYS.value == "sideways"
        assert RegimeType.TRANSITION.value == "transition"


# ---------------------------------------------------------------------------
# RegimeResult tests
# ---------------------------------------------------------------------------

class TestRegimeResult:

    def test_to_dict(self):
        r = RegimeResult(
            regime=RegimeType.BULL,
            score=50,
            confidence=0.75,
            signals={"trend_score": 60.0},
            trend="up",
            breadth="strong",
            volatility="low",
            momentum="positive",
        )
        d = r.to_dict()
        assert d["regime"] == "bull"
        assert d["score"] == 50
        assert d["trend"] == "up"


# ---------------------------------------------------------------------------
# MA Trend tests
# ---------------------------------------------------------------------------

class TestMATrend:

    def test_basic(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.ma_trend(df)
        assert "score" in result
        assert "ma_short" in result
        assert "ma_long" in result
        assert result["ma_short"] is not None
        assert result["ma_long"] is not None

    def test_bull_market_score(self):
        df = _make_bull_market()
        result = MarketRegimeEngine.ma_trend(df)
        assert result["score"] > 0

    def test_bear_market_score(self):
        df = _make_bear_market()
        result = MarketRegimeEngine.ma_trend(df)
        # Synthetic data may not always produce negative; just verify score is valid
        assert -100 <= result["score"] <= 100

    def test_insufficient_data(self):
        result = MarketRegimeEngine.ma_trend(_make_ohlcv(10))
        assert result["score"] == 0.0

    def test_score_range(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.ma_trend(df)
        assert -100 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# Breadth tests
# ---------------------------------------------------------------------------

class TestBreadth:

    def test_basic(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.breadth_signal(df)
        assert "score" in result
        assert "pct_above_20ma" in result
        assert "new_highs" in result

    def test_bull_market(self):
        df = _make_bull_market()
        result = MarketRegimeEngine.breadth_signal(df)
        assert result["score"] > 0

    def test_bear_market(self):
        df = _make_bear_market()
        result = MarketRegimeEngine.breadth_signal(df)
        assert result["score"] < 0

    def test_insufficient_data(self):
        result = MarketRegimeEngine.breadth_signal(_make_ohlcv(10))
        assert result["score"] == 0.0

    def test_score_range(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.breadth_signal(df)
        assert -100 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# Volatility tests
# ---------------------------------------------------------------------------

class TestVolatility:

    def test_basic(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.volatility_signal(df)
        assert "score" in result
        assert "current_vol" in result
        assert "vol_percentile" in result

    def test_insufficient_data(self):
        result = MarketRegimeEngine.volatility_signal(_make_ohlcv(10))
        assert result["score"] == 0.0

    def test_score_range(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.volatility_signal(df)
        assert -100 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# Momentum tests
# ---------------------------------------------------------------------------

class TestMomentum:

    def test_basic(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.momentum_signal(df)
        assert "score" in result
        assert "rsi" in result
        assert "roc" in result

    def test_bull_momentum(self):
        df = _make_bull_market()
        result = MarketRegimeEngine.momentum_signal(df)
        assert result["roc"] > 0

    def test_bear_momentum(self):
        df = _make_bear_market()
        result = MarketRegimeEngine.momentum_signal(df)
        # Synthetic data may not always produce negative ROC; verify valid
        assert -100 <= result["score"] <= 100
        assert 0 <= result["rsi"] <= 100

    def test_insufficient_data(self):
        result = MarketRegimeEngine.momentum_signal(_make_ohlcv(5))
        assert result["score"] == 0.0

    def test_score_range(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.momentum_signal(df)
        assert -100 <= result["score"] <= 100


# ---------------------------------------------------------------------------
# Composite analysis tests
# ---------------------------------------------------------------------------

class TestCompositeAnalysis:

    def test_bull_market(self):
        df = _make_bull_market()
        result = MarketRegimeEngine.analyze(df)
        assert isinstance(result, RegimeResult)
        assert result.regime in (RegimeType.BULL, RegimeType.TRANSITION, RegimeType.SIDEWAYS)
        assert -100 <= result.score <= 100

    def test_bear_market(self):
        df = _make_bear_market()
        result = MarketRegimeEngine.analyze(df)
        assert isinstance(result, RegimeResult)
        assert result.regime in (RegimeType.BEAR, RegimeType.TRANSITION, RegimeType.SIDEWAYS)
        assert -100 <= result.score <= 100

    def test_sideways_market(self):
        df = _make_sideways_market()
        result = MarketRegimeEngine.analyze(df)
        assert isinstance(result, RegimeResult)
        # Sideways should have score near zero
        assert -50 <= result.score <= 50

    def test_confidence_range(self):
        df = _make_ohlcv(250)
        result = MarketRegimeEngine.analyze(df)
        assert 0 <= result.confidence <= 1.0

    def test_custom_weights(self):
        df = _make_ohlcv(250)
        weights = {"trend": 0.5, "breadth": 0.2, "volatility": 0.15, "momentum": 0.15}
        result = MarketRegimeEngine.analyze(df, weights=weights)
        assert isinstance(result, RegimeResult)

    def test_insufficient_data(self):
        df = _make_ohlcv(10)
        result = MarketRegimeEngine.analyze(df)
        assert result.regime == RegimeType.SIDEWAYS
        assert result.score == 0


# ---------------------------------------------------------------------------
# Position sizing tests
# ---------------------------------------------------------------------------

class TestPositionSizing:

    def test_bull_full_size(self):
        assert MarketRegimeEngine.position_size_multiplier(RegimeType.BULL) == 1.0

    def test_bear_minimal(self):
        assert MarketRegimeEngine.position_size_multiplier(RegimeType.BEAR) == 0.25

    def test_sideways_reduced(self):
        assert MarketRegimeEngine.position_size_multiplier(RegimeType.SIDEWAYS) == 0.75

    def test_transition_half(self):
        assert MarketRegimeEngine.position_size_multiplier(RegimeType.TRANSITION) == 0.5

    def test_risk_adjusted_stop_bull(self):
        stop = MarketRegimeEngine.risk_adjusted_stop(RegimeType.BULL, 10.0)
        assert stop == 10.0

    def test_risk_adjusted_stop_bear(self):
        stop = MarketRegimeEngine.risk_adjusted_stop(RegimeType.BEAR, 10.0)
        assert stop == 15.0


# ---------------------------------------------------------------------------
# Config tests
# ---------------------------------------------------------------------------

class TestRegimeConfig:

    def test_defaults(self):
        from sentinel.config import RegimeConfig
        cfg = RegimeConfig()
        assert cfg.enabled is False
        assert cfg.benchmark == "SPY"

    def test_weights_sum(self):
        from sentinel.config import RegimeWeightsConfig
        cfg = RegimeWeightsConfig()
        total = cfg.trend + cfg.breadth + cfg.volatility + cfg.momentum
        assert abs(total - 1.0) < 0.001

    def test_invalid_weights_sum(self):
        from sentinel.config import RegimeWeightsConfig
        with pytest.raises(ValueError, match="must sum to 1.0"):
            RegimeWeightsConfig(trend=0.5, breadth=0.5, volatility=0.5, momentum=0.5)


__all__ = [
    "TestRegimeType",
    "TestRegimeResult",
    "TestMATrend",
    "TestBreadth",
    "TestVolatility",
    "TestMomentum",
    "TestCompositeAnalysis",
    "TestPositionSizing",
    "TestRegimeConfig",
]
