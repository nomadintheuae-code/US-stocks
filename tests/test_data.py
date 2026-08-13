"""DataEngine derived-metric tests (no network) — Phase 4.2 liquidity helper."""
import pandas as pd
import pytest

from engines.data import DataEngine


def _frame(close, volume):
    return pd.DataFrame({"Close": list(close), "Volume": list(volume)})


def test_liquidity_metrics_basic():
    df = _frame([10, 11, 12, 13, 14], [100, 110, 120, 130, 140])
    out = DataEngine.get_liquidity_metrics(df, lookback=5)
    assert out["avg_volume"] == pytest.approx(120.0)
    assert out["avg_dollar_volume"] == pytest.approx(
        (10 * 100 + 11 * 110 + 12 * 120 + 13 * 130 + 14 * 140) / 5
    )


def test_liquidity_metrics_trailing_only_lookahead_free():
    """Only the most recent ``lookback`` bars may influence the result."""
    df = _frame([1, 2, 3, 4, 5, 6, 7, 8, 9, 10], [10, 20, 30, 40, 50, 60, 70, 80, 90, 100])
    out = DataEngine.get_liquidity_metrics(df, lookback=3)
    assert out["avg_volume"] == pytest.approx(90.0)  # bars 80,90,100 only
    assert out["avg_dollar_volume"] == pytest.approx((8 * 80 + 9 * 90 + 10 * 100) / 3)


def test_liquidity_metrics_uses_available_rows_when_short():
    df = _frame([10, 11], [100, 110])
    out = DataEngine.get_liquidity_metrics(df, lookback=20)
    assert out["avg_volume"] == pytest.approx(105.0)


def test_liquidity_metrics_empty_frame():
    out = DataEngine.get_liquidity_metrics(pd.DataFrame({"Close": [], "Volume": []}))
    assert out == {"avg_dollar_volume": None, "avg_volume": None}


def test_liquidity_metrics_none_frame():
    assert DataEngine.get_liquidity_metrics(None) == {"avg_dollar_volume": None, "avg_volume": None}


def test_liquidity_metrics_invalid_lookback():
    df = _frame([10, 11], [100, 110])
    assert DataEngine.get_liquidity_metrics(df, lookback=0) == {
        "avg_dollar_volume": None, "avg_volume": None,
    }
    assert DataEngine.get_liquidity_metrics(df, lookback=-5) == {
        "avg_dollar_volume": None, "avg_volume": None,
    }


def test_liquidity_metrics_missing_columns_returns_none():
    df = pd.DataFrame({"Open": [1, 2, 3], "High": [1, 2, 3]})
    out = DataEngine.get_liquidity_metrics(df)
    assert out["avg_dollar_volume"] is None
    assert out["avg_volume"] is None


def test_liquidity_metrics_nan_values_skipped():
    """pandas mean() skips NaN rows; metrics use the valid rows only."""
    df = _frame([10, 11, 12], [100, float("nan"), 120])
    out = DataEngine.get_liquidity_metrics(df, lookback=3)
    assert out["avg_volume"] == pytest.approx(110.0)
    assert out["avg_dollar_volume"] == pytest.approx((10 * 100 + 12 * 120) / 2)


def test_liquidity_metrics_zero_volume():
    df = _frame([10, 11, 12], [0, 0, 0])
    out = DataEngine.get_liquidity_metrics(df, lookback=3)
    assert out["avg_volume"] == pytest.approx(0.0)
    assert out["avg_dollar_volume"] == pytest.approx(0.0)


def test_liquidity_metrics_default_lookback():
    df = _frame(list(range(1, 31)), list(range(1000, 1030)))
    out = DataEngine.get_liquidity_metrics(df)
    assert out["avg_volume"] == pytest.approx(1019.5)  # last 20 of 30
    out10 = DataEngine.get_liquidity_metrics(df, lookback=10)
    assert out10["avg_volume"] == pytest.approx(1024.5)


def test_liquidity_metrics_deterministic():
    df = _frame([10, 11, 12, 13], [100, 110, 120, 130])
    assert DataEngine.get_liquidity_metrics(df) == DataEngine.get_liquidity_metrics(df)
