"""Phase 8 Technical Pattern Recognition tests (no network)."""
import numpy as np
import pandas as pd
import pytest

from engines.patterns import FibonacciEngine, CandlestickEngine, BBSqueezeEngine


# ---------------------------------------------------------------------------
# Helper: build synthetic OHLCV DataFrames
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 100, seed: int = 42) -> pd.DataFrame:
    """Generate a synthetic OHLCV DataFrame for testing."""
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


def _make_trending_ohlcv(n: int = 100, up: bool = True) -> pd.DataFrame:
    """Generate trending OHLCV data."""
    rng = np.random.RandomState(42)
    direction = 1.5 if up else -1.5
    close = 100 + np.cumsum(rng.randn(n) * 1.0 + direction)
    high = close + rng.uniform(0.5, 2.0, n)
    low = close - rng.uniform(0.5, 2.0, n)
    opn = close + rng.randn(n) * 0.3
    vol = rng.randint(100000, 500000, n).astype(float)
    dates = pd.date_range("2025-01-01", periods=n, freq="B")
    return pd.DataFrame({
        "Open": opn, "High": high, "Low": low, "Close": close, "Volume": vol,
    }, index=dates)


# ---------------------------------------------------------------------------
# FibonacciEngine tests
# ---------------------------------------------------------------------------

class TestFibonacciEngine:

    def test_find_swing_highs_lows(self):
        df = _make_ohlcv(60)
        sh, sl = FibonacciEngine.find_swing_highs_lows(df, lookback=30)
        assert sh is not None
        assert sl is not None
        assert sh > sl

    def test_find_swing_insufficient_data(self):
        df = _make_ohlcv(5)
        sh, sl = FibonacciEngine.find_swing_highs_lows(df, lookback=20)
        assert sh is None
        assert sl is None

    def test_retracement_levels_count(self):
        levels = FibonacciEngine.retracement_levels(200.0, 100.0)
        assert len(levels) == len(FibonacciEngine.RETRACEMENT_RATIOS)

    def test_retracement_values(self):
        levels = FibonacciEngine.retracement_levels(200.0, 100.0)
        assert levels[0.0] == 200.0
        assert levels[1.0] == 100.0
        assert levels[0.5] == 150.0

    def test_extension_levels_count(self):
        levels = FibonacciEngine.extension_levels(200.0, 100.0)
        assert len(levels) == len(FibonacciEngine.EXTENSION_RATIOS)

    def test_extension_beyond_high(self):
        levels = FibonacciEngine.extension_levels(200.0, 100.0)
        for ratio, price in levels.items():
            assert price > 200.0

    def test_nearest_fib(self):
        level, dist = FibonacciEngine.nearest_fib(148.0, 200.0, 100.0)
        assert level == 150.0
        assert abs(dist - (-0.01333)) < 0.01

    def test_analyze_full(self):
        df = _make_ohlcv(100)
        result = FibonacciEngine.analyze(df, lookback=60)
        assert result["swing_high"] is not None
        assert result["swing_low"] is not None
        assert len(result["retracements"]) == 7
        assert len(result["extensions"]) == 4
        assert result["nearest_level"] is not None

    def test_analyze_empty_df(self):
        result = FibonacciEngine.analyze(pd.DataFrame(), lookback=60)
        assert result["swing_high"] is None

    def test_support_resistance_sorted(self):
        df = _make_ohlcv(100)
        result = FibonacciEngine.analyze(df, lookback=60)
        support = result["support_levels"]
        resistance = result["resistance_levels"]
        # Support should be descending, resistance ascending
        assert support == sorted(support, reverse=True)
        assert resistance == sorted(resistance)


# ---------------------------------------------------------------------------
# CandlestickEngine tests
# ---------------------------------------------------------------------------

class TestCandlestickEngine:

    def test_doji(self):
        # Open == Close (zero body)
        assert CandlestickEngine.doji(100.0, 102.0, 98.0, 100.0) is True

    def test_not_doji(self):
        # Large body relative to range
        assert CandlestickEngine.doji(90.0, 100.0, 80.0, 100.0) is False

    def test_hammer(self):
        # Small body at top, long lower shadow
        assert CandlestickEngine.hammer(99.0, 100.0, 90.0, 100.0) is True

    def test_not_hammer(self):
        # Large body
        assert CandlestickEngine.hammer(90.0, 100.0, 80.0, 100.0) is False

    def test_inverted_hammer(self):
        # Small body at bottom, long upper shadow, tiny lower shadow
        assert CandlestickEngine.inverted_hammer(99.5, 110.0, 99.4, 100.0) is True

    def test_marubozu_bullish(self):
        # Body covers 100% of range (no shadows)
        assert CandlestickEngine.marubozu(80.0, 100.0, 80.0, 100.0, threshold=0.9) is True

    def test_marubozu_bearish(self):
        assert CandlestickEngine.marubozu(100.0, 100.0, 80.0, 80.0, threshold=0.9) is True

    def test_engulfing_bullish(self):
        # Bearish bar then larger bullish bar
        result = CandlestickEngine.engulfing(100.0, 95.0, 94.0, 101.0)
        assert result == "bullish"

    def test_engulfing_bearish(self):
        # Bullish bar then larger bearish bar
        result = CandlestickEngine.engulfing(95.0, 100.0, 101.0, 94.0)
        assert result == "bearish"

    def test_engulfing_none(self):
        result = CandlestickEngine.engulfing(95.0, 100.0, 96.0, 99.0)
        assert result == "none"

    def test_detect_patterns(self):
        df = _make_ohlcv(20)
        patterns = CandlestickEngine.detect(df, lookback=5)
        assert isinstance(patterns, list)
        for p in patterns:
            assert "bar_index" in p
            assert "pattern" in p
            assert "type" in p
            assert p["type"] in ("bullish", "bearish", "neutral")

    def test_detect_insufficient_data(self):
        patterns = CandlestickEngine.detect(pd.DataFrame(), lookback=5)
        assert patterns == []

    def test_summary(self):
        df = _make_ohlcv(20)
        result = CandlestickEngine.summary(df, lookback=5)
        assert "total" in result
        assert "counts" in result
        assert "bias" in result
        assert result["bias"] in ("bullish", "bearish", "neutral")


# ---------------------------------------------------------------------------
# BBSqueezeEngine tests
# ---------------------------------------------------------------------------

class TestBBSqueezeEngine:

    def test_compute_bb(self):
        df = _make_ohlcv(50)
        bb = BBSqueezeEngine.compute_bb(df, period=20)
        assert bb is not None
        assert "bb_mid" in bb.columns
        assert "bb_upper" in bb.columns
        assert "bb_lower" in bb.columns
        assert "bb_width" in bb.columns

    def test_compute_bb_insufficient_data(self):
        df = _make_ohlcv(5)
        bb = BBSqueezeEngine.compute_bb(df, period=20)
        assert bb is None

    def test_bb_upper_above_lower(self):
        df = _make_ohlcv(50)
        bb = BBSqueezeEngine.compute_bb(df, period=20)
        valid = bb.dropna()
        assert (valid["bb_upper"] >= valid["bb_lower"]).all()

    def test_is_squeezing(self):
        df = _make_ohlcv(150)
        result = BBSqueezeEngine.is_squeezing(df, lookback=120)
        assert "squeezing" in result
        assert "current_width" in result
        assert "percentile" in result
        assert "status" in result
        assert result["status"] in ("squeeze_active", "narrowing", "expanded", "insufficient_data")

    def test_is_squeezing_insufficient(self):
        result = BBSqueezeEngine.is_squeezing(_make_ohlcv(5))
        assert result["status"] == "insufficient_data"

    def test_analyze_full(self):
        df = _make_ohlcv(150)
        result = BBSqueezeEngine.analyze(df)
        assert "squeezing" in result
        assert "keltner_width" in result
        assert "squeeze_confirmed" in result

    def test_keltner_channel_width(self):
        df = _make_ohlcv(50)
        kc = BBSqueezeEngine.keltter_channel_width(df)
        assert kc is not None
        assert len(kc) > 0

    def test_squeeze_percentile_range(self):
        df = _make_ohlcv(150)
        result = BBSqueezeEngine.is_squeezing(df, lookback=120)
        if result["percentile"] is not None:
            assert 0 <= result["percentile"] <= 100


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------

class TestPatternsConfig:

    def test_defaults(self):
        from sentinel.config import PatternsConfig
        cfg = PatternsConfig()
        assert cfg.enabled is False
        assert cfg.fibonacci.lookback == 60
        assert cfg.candlestick.lookback == 5
        assert cfg.bb_squeeze.period == 20

    def test_fibonacci_lookback_range(self):
        from sentinel.config import FibonacciConfig
        with pytest.raises(ValueError):
            FibonacciConfig(lookback=5)

    def test_candlestick_threshold_range(self):
        from sentinel.config import CandlestickConfig
        with pytest.raises(ValueError):
            CandlestickConfig(doji_threshold=0.0)

    def test_bb_squeeze_std_range(self):
        from sentinel.config import BBSqueezeConfig
        with pytest.raises(ValueError):
            BBSqueezeConfig(std_dev=0.0)


__all__ = [
    "TestFibonacciEngine",
    "TestCandlestickEngine",
    "TestBBSqueezeEngine",
    "TestPatternsConfig",
]
