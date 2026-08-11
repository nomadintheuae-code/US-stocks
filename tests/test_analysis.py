"""Indicator / strategy unit tests with synthetic OHLCV data (no network)."""
import numpy as np
import pandas as pd
import pytest

from engines.analysis import RSAnalyzer, StrategyValidator, VCPAnalyzer


def _frame(n=260, drift=0.5, vol=1.0, seed=0):
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.arange(n) * drift + rng.normal(0, vol, n), 1.0)
    high = close + np.abs(rng.normal(0, 1.0, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1.0, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})


# --- RSAnalyzer -------------------------------------------------------------

def test_rs_short_frame_returns_sentinel():
    assert RSAnalyzer.get_raw_score(_frame(n=10)) == -999.0


def test_rs_uptrend_positive():
    assert RSAnalyzer.get_raw_score(_frame(n=300, drift=0.5)) > 0


def test_rs_downtrend_negative():
    assert RSAnalyzer.get_raw_score(_frame(n=300, drift=-0.5)) < 0


def test_rs_percentiles_ascending():
    items = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    out = RSAnalyzer.assign_percentiles(items)
    assert [i["raw_rs"] for i in out] == [-0.2, 0.1, 0.5]
    ratings = [i["rs_rating"] for i in out]
    assert ratings == sorted(ratings)
    assert ratings[-1] == 100


def test_rs_percentiles_empty():
    assert RSAnalyzer.assign_percentiles([]) == []


# --- VCPAnalyzer ------------------------------------------------------------

def test_vcp_short_frame_empty():
    res = VCPAnalyzer.calculate(_frame(n=50))
    assert res["score"] == 0
    assert res["atr"] == 0.0


def test_vcp_none_frame_empty():
    assert VCPAnalyzer.calculate(None)["score"] == 0


def test_vcp_long_frame_breakdown():
    res = VCPAnalyzer.calculate(_frame(n=300, drift=0.5))
    assert set(res) >= {"score", "atr", "signals", "is_dryup", "range_pct", "vol_ratio", "breakdown"}
    assert 0 <= res["score"] <= 105
    assert res["atr"] > 0
    assert set(res["breakdown"]) == {"tight", "vol", "ma", "pivot"}


def test_vcp_dry_volume_flagged():
    df = _frame(n=300, drift=0.3)
    df.iloc[-20:, df.columns.get_loc("Volume")] = df["Volume"].iloc[-60:-40].mean() * 0.3
    res = VCPAnalyzer.calculate(df)
    assert res["is_dryup"] is True
    assert "Volume Dry-up Detected" in res["signals"]


# --- StrategyValidator ------------------------------------------------------

def test_validator_short_frame_returns_one():
    assert StrategyValidator.run(_frame(n=100)) == 1.0


def test_validator_long_frame_in_range():
    pf = StrategyValidator.run(_frame(n=300, drift=0.8))
    assert 1.0 <= pf <= 10.0
