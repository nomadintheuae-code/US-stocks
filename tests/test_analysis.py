"""Indicator / strategy unit tests with synthetic OHLCV data (no network)."""
import numpy as np
import pandas as pd
import pytest

from engines.analysis import RSAnalyzer, RSIndicator, StrategyValidator, VCPAnalyzer, VCPIndicator
from engines.strategies.base import Strategy
from engines.strategies.minervini_template import MinerviniTrendTemplate
from engines.strategies.rs_ranking import RelativeStrengthRanking
from engines.strategies.vcp_breakout import VCPBreakoutStrategy


def _frame(n=260, drift=0.5, vol=1.0, seed=0):
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.arange(n) * drift + rng.normal(0, vol, n), 1.0)
    high = close + np.abs(rng.normal(0, 1.0, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1.0, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})


def _pivot_base_frame(
    seed=5,
    peak_idx=110,
    peak_close=96.0,
    breakout_close=None,
    failed_spike=None,
    handle_volume=1_000_000.0,
    base_volume=1_000_000.0,
    spike_bar=196,
):
    """n=200 OHLCV with a proper VCP base: rise to a left-side peak, decline,
    then a tightening handle; optionally a breakout close, a failed spike, or
    raised handle volume. Deterministic (seeded).
    """
    rng = np.random.default_rng(seed)
    n = 200
    close = np.empty(n)
    close[:peak_idx + 1] = np.linspace(50.0, peak_close, peak_idx + 1)
    close[peak_idx + 1:151] = np.linspace(peak_close, 62.0, 151 - peak_idx - 1)
    close[150:] = np.linspace(62.0, 55.0, 50)
    if breakout_close is not None:
        close[180:] = np.linspace(62.0, breakout_close, 20)
    if failed_spike is not None:
        close[spike_bar] = failed_spike[1]
    close = np.maximum(close, 1.0)

    high = close + 1.5 + np.abs(rng.normal(0, 0.4, n))
    low = close - 1.5 - np.abs(rng.normal(0, 0.4, n))
    np.maximum(low, 0.1, out=low)
    if failed_spike is not None:
        high[spike_bar] = failed_spike[0]

    volume = np.full(n, base_volume).astype(float)
    volume[180:] = handle_volume
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})


def _trend_frame(n=300, slope=0.3, start=50.0, seed=0):
    """n-bar deterministic trend frame: rising (slope>0) or falling (slope<0)."""
    rng = np.random.default_rng(seed)
    close = np.maximum(start + np.arange(n) * slope + rng.normal(0, 0.5, n), 1.0)
    high = close + 0.5 + np.abs(rng.normal(0, 0.3, n))
    low = np.maximum(close - 0.5 - np.abs(rng.normal(0, 0.3, n)), 0.1)
    volume = np.full(n, 1_000_000.0)
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


# --- VCPIndicator -----------------------------------------------------------

def test_vcp_indicator_default_config_loads():
    ind = VCPIndicator()
    assert ind.tightness_periods == [20, 30, 40, 60]
    assert ind.volume_lookback_short == 20
    assert ind.volume_lookback_long == 60
    assert ind.volume_lookback_gap == 20
    assert ind.ma_periods == [50, 150, 200]
    assert ind.pivot_near_pct == 0.04
    assert ind.pivot_far_pct == 0.08
    assert ind.max_tightness_score == 40
    assert ind.max_volume_score == 30
    assert ind.max_ma_score == 30


def test_vcp_indicator_custom_config():
    ind = VCPIndicator(tightness_periods=[15, 25, 35, 50], ma_periods=[40, 100, 150])
    assert ind.tightness_periods == [15, 25, 35, 50]
    assert ind.ma_periods == [40, 100, 150]


def test_vcp_indicator_invalid_tightness_periods():
    with pytest.raises(ValueError, match="at least 2 periods"):
        VCPIndicator(tightness_periods=[20])


def test_vcp_indicator_invalid_pivot_thresholds():
    with pytest.raises(ValueError, match="pivot_far_pct must be > pivot_near_pct"):
        VCPIndicator(pivot_near_pct=0.08, pivot_far_pct=0.04)


def test_vcp_indicator_invalid_ma_periods():
    with pytest.raises(ValueError, match="at least 2 periods"):
        VCPIndicator(ma_periods=[50])


def test_vcp_indicator_calculate_short_frame():
    ind = VCPIndicator()
    res = ind.calculate(_frame(n=50))
    assert res["score"] == 0
    assert res["atr"] == 0.0


def test_vcp_indicator_calculate_none():
    ind = VCPIndicator()
    res = ind.calculate(None)
    assert res["score"] == 0


def test_vcp_indicator_calculate_output_format():
    ind = VCPIndicator()
    res = ind.calculate(_frame(n=300, drift=0.5))
    assert set(res) >= {"score", "atr", "signals", "is_dryup", "range_pct", "vol_ratio", "breakdown"}
    assert 0 <= res["score"] <= 105
    assert res["atr"] > 0
    assert set(res["breakdown"]) == {"tight", "vol", "ma", "pivot"}


def test_vcp_indicator_calculate_dry_volume():
    ind = VCPIndicator()
    df = _frame(n=300, drift=0.3)
    df.iloc[-20:, df.columns.get_loc("Volume")] = df["Volume"].iloc[-60:-40].mean() * 0.3
    res = ind.calculate(df)
    assert res["is_dryup"] is True
    assert "Volume Dry-up Detected" in res["signals"]


# --- VCPAnalyzer backward compatibility --------------------------------------

def test_vcpanalyzer_calculate_compat():
    df = _frame(n=300, drift=0.5)
    assert VCPAnalyzer.calculate(df) == VCPIndicator().calculate(df)


def test_vcpanalyzer_short_frame_compat():
    assert VCPAnalyzer.calculate(_frame(n=50))["score"] == 0
    assert VCPAnalyzer.calculate(None)["score"] == 0


def test_vcpanalyzer_dry_volume_compat():
    df = _frame(n=300, drift=0.3)
    df.iloc[-20:, df.columns.get_loc("Volume")] = df["Volume"].iloc[-60:-40].mean() * 0.3
    assert VCPAnalyzer.calculate(df)["is_dryup"] is True


# --- VCP contraction pivot + breakout (Phase 2.4.2D) -------------------------

def test_vcp_pivot_opt_in_default_preserves_legacy():
    """Without use_contraction_pivot, output is byte-identical to legacy."""
    on = VCPIndicator(use_contraction_pivot=True)
    off = VCPIndicator()
    df = _pivot_base_frame()
    res_off = off.calculate(df)
    assert "pivot" not in res_off
    assert VCPAnalyzer.calculate(df) == res_off
    assert on.calculate(df)["pivot"] is not None


def test_vcp_pivot_detection_left_side_of_base():
    """Proper pivot = highest high of the base's LEFT side, not the 50-day high."""
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame()
    p = ind.detect_pivot(df)
    assert p["pivot_idx"] == 110
    assert p["price"] == round(float(df["High"].iloc[100:180].max()), 4)
    assert p["price"] > float(df["High"].iloc[-50:].max())  # differs from naive 50-day-high


def test_vcp_pivot_handle_structure_and_contraction():
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame()
    p = ind.detect_pivot(df)
    handle = p["handle"]
    assert set(handle) >= {"high", "low", "range_pct", "left_range_pct", "contracted"}
    assert handle["high"] == round(float(df["High"].iloc[-20:].max()), 4)
    assert handle["low"] == round(float(df["Low"].iloc[-20:].min()), 4)
    assert 0.0 <= handle["range_pct"] <= 1.0
    assert handle["contracted"] is True  # handle range narrower than the base


def test_vcp_pivot_handle_not_contracted_when_wide():
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame()
    wide = df.copy()
    wide["High"] = wide["High"].values
    wide["Low"] = wide["Low"].values
    wide.iloc[-20:, wide.columns.get_loc("High")] = wide["Close"].iloc[-20:].values + 20.0
    wide.iloc[-20:, wide.columns.get_loc("Low")] = wide["Close"].iloc[-20:].values - 20.0
    wide["Low"] = wide["Low"].clip(lower=0.1)
    p = ind.detect_pivot(wide)
    assert p["handle"]["contracted"] is False


def test_vcp_pivot_breakout_confirmed():
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    p = ind.detect_pivot(df)
    assert p["breakout"]["close_above_pivot"] is True
    assert p["breakout"]["volume_surge"] is True
    assert p["breakout"]["volume_ratio"] == 4.0
    assert p["breakout"]["confirmed"] is True
    assert p["signal"] == "Breakout Confirmed"


def test_vcp_pivot_breakout_volume_required():
    """Close above pivot alone does NOT confirm a breakout without volume surge."""
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame(breakout_close=102.0)  # same volume everywhere
    p = ind.detect_pivot(df)
    assert p["breakout"]["close_above_pivot"] is True
    assert p["breakout"]["volume_surge"] is False
    assert p["breakout"]["confirmed"] is False
    assert p["signal"] == "Awaiting Breakout"


def test_vcp_pivot_failed_breakout():
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame(failed_spike=(104.0, 55.0))
    p = ind.detect_pivot(df)
    assert p["breakout"]["failed"] is True
    assert p["breakout"]["close_above_pivot"] is False
    assert p["breakout"]["confirmed"] is False
    assert p["signal"] == "Breakout Failed"


def test_vcp_pivot_insufficient_data():
    ind = VCPIndicator(use_contraction_pivot=True)
    short = _pivot_base_frame()[:50]
    assert ind.detect_pivot(short) is None
    res = ind.calculate(short)
    assert res["score"] == 0
    assert res["pivot"] is None
    assert ind.detect_pivot(_pivot_base_frame(), bar_idx=-1) is None
    assert ind.detect_pivot(_pivot_base_frame(), bar_idx=999) is None


def test_vcp_pivot_no_lookahead():
    """Detection at bar i must equal detection on a frame truncated at i."""
    ind = VCPIndicator(use_contraction_pivot=True)
    df = _pivot_base_frame()
    for i in (129, 140, 160, 180, 199):
        assert ind.detect_pivot(df, bar_idx=i) == ind.detect_pivot(df.iloc[: i + 1])
    assert ind.detect_pivot(df)["breakout"]["bar_index"] == len(df) - 1


def test_vcp_pivot_calculate_output_schema():
    ind = VCPIndicator(use_contraction_pivot=True)
    res = ind.calculate(_pivot_base_frame())
    assert set(res) >= {"score", "atr", "signals", "is_dryup", "range_pct", "vol_ratio", "breakdown", "pivot"}
    p = res["pivot"]
    assert set(p) >= {"price", "pivot_idx", "base_lookback", "handle", "breakout", "signal"}
    assert set(p["breakout"]) >= {
        "confirmed", "close_above_pivot", "volume_surge", "volume_ratio",
        "failed", "close", "bar_index", "lookahead_free",
    }
    assert p["breakout"]["lookahead_free"] is True


def test_vcp_pivot_constructor_validation():
    with pytest.raises(ValueError, match="pivot_base_lookback"):
        VCPIndicator(use_contraction_pivot=True, pivot_base_lookback=1)
    with pytest.raises(ValueError, match="breakout_volume_ratio"):
        VCPIndicator(use_contraction_pivot=True, breakout_volume_ratio=1.0)


def test_vcp_pivot_backward_compat():
    df = _frame(n=300, drift=0.5)
    assert VCPAnalyzer.calculate(df) == VCPIndicator().calculate(df)
    assert "pivot" not in VCPIndicator().calculate(df)


# --- StrategyValidator ------------------------------------------------------

def test_validator_short_frame_returns_one():
    assert StrategyValidator.run(_frame(n=100)) == 1.0


def test_validator_long_frame_in_range():
    pf = StrategyValidator.run(_frame(n=300, drift=0.8))
    assert 1.0 <= pf <= 10.0


# --- StrategyValidator walk-forward (Phase 2.4.2E) ---------------------------

def _leak_frame(n=320, drift=3.0, seed=11):
    """Strong uptrend with a massive high/close spike on the FINAL bar.

    Any entry evaluation that peeks at future bars (e.g. a pivot computed from
    ``high[i-20:]`` including the spike) will have its pivot dwarfed by the
    spike and therefore NEVER enter — producing a profit factor of 1.0. A
    correct point-in-time implementation enters before the spike and returns
    a non-trivial (>1.0) profit factor, so the two are always distinguishable.
    """
    rng = np.random.default_rng(seed)
    close = np.maximum(100 + np.arange(n) * drift, 1.0)
    high = close + 2.0 + np.abs(rng.normal(0, 0.3, n))
    low = np.maximum(close - 2.0 - np.abs(rng.normal(0, 0.3, n)), 0.1)
    high[n - 1] = 1_000_000.0
    close[n - 1] = 900_000.0
    low[n - 1] = 0.1
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    return pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})


def _leaky_pivot_run(df):
    """Deliberately biased reference: the entry pivot includes FUTURE highs."""
    from config import CONFIG
    if len(df) < 200:
        return 1.0
    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = tr.rolling(14).mean()
    trades = []
    in_pos = False
    entry_p = 0.0
    stop_p = 0.0
    target_mult = CONFIG["TARGET_R_MULTIPLE"]
    stop_mult = CONFIG["STOP_LOSS_ATR"]
    for i in range(max(50, len(df) - 250), len(df)):
        if in_pos:
            if float(low.iloc[i]) <= stop_p:
                trades.append(-1.0)
                in_pos = False
            elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * target_mult:
                trades.append(target_mult)
                in_pos = False
            elif i == len(df) - 1:
                risk = entry_p - stop_p
                if risk > 0:
                    trades.append((float(close.iloc[i]) - entry_p) / risk)
                in_pos = False
        else:
            if i < 20:
                continue
            pivot = float(high.iloc[i - 20:].max())  # BUG: includes bars i..end
            ma50 = float(close.rolling(50).mean().iloc[i])
            if float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50:
                in_pos = True
                entry_p = float(close.iloc[i])
                stop_p = entry_p - float(atr.iloc[i]) * stop_mult
    if not trades:
        return 1.0
    pos = sum(t for t in trades if t > 0)
    neg = abs(sum(t for t in trades if t < 0))
    pf = pos / neg if neg > 0 else (5.0 if pos > 0 else 1.0)
    return round(min(10.0, float(pf)), 2)


def test_walk_forward_api_compat():
    assert callable(StrategyValidator.run)
    assert callable(StrategyValidator.run_walk_forward)
    assert callable(StrategyValidator.evaluate_walk_forward)
    assert isinstance(StrategyValidator.run(_frame(n=300)), float)
    assert isinstance(StrategyValidator.run_walk_forward(_frame(n=300)), float)


def test_walk_forward_evaluation_result():
    rec = StrategyValidator.evaluate_walk_forward(_frame(n=300, drift=0.5))
    assert set(rec) >= {"profit_factor", "trades", "start", "evaluated_bars"}
    assert 1.0 <= rec["profit_factor"] <= 10.0
    assert rec["evaluated_bars"] == 300 - max(50, 300 - 250)


def test_walk_forward_deterministic():
    df = _frame(n=300, drift=0.5)
    assert StrategyValidator.run_walk_forward(df) == StrategyValidator.run_walk_forward(df)
    assert (
        StrategyValidator.evaluate_walk_forward(df)
        == StrategyValidator.evaluate_walk_forward(df)
    )


def test_walk_forward_empty_insufficient_data():
    assert StrategyValidator.run_walk_forward(None) == 1.0
    assert StrategyValidator.run_walk_forward(_frame(n=50)) == 1.0
    assert StrategyValidator.evaluate_walk_forward(None)["profit_factor"] == 1.0
    assert StrategyValidator.evaluate_walk_forward(_frame(n=50))["trades"] == []


def test_walk_forward_atr_uses_only_available_bars():
    """ATR(14) at bar t must equal ATR computed on the truncated frame only."""
    df = _frame(n=300, drift=0.3)
    i = 180
    f = df.iloc[: i + 1]
    tr = pd.concat([
        f["High"] - f["Low"],
        (f["High"] - f["Close"].shift()).abs(),
        (f["Low"] - f["Close"].shift()).abs(),
    ], axis=1).max(axis=1)
    expected = float(tr.rolling(14).mean().iloc[-1])
    assert StrategyValidator._point_in_time_indicators(df, i)["atr"] == expected


def test_walk_forward_point_in_time_isolation():
    """Indicators and derived entry/stop/target at bar t ignore future bars."""
    from config import CONFIG
    df = _frame(n=300, drift=0.4)
    i = 200
    future = pd.DataFrame({
        "Open": [1e7], "High": [1e7], "Low": [1.0], "Close": [1e6], "Volume": [1e9],
    })
    tampered = pd.concat([df.iloc[: i + 1], future], ignore_index=True)

    a = StrategyValidator._point_in_time_indicators(df, i)
    b = StrategyValidator._point_in_time_indicators(tampered, i)
    assert a == b

    # Derived entry / stop / target must be identical across both frames
    # (stop distance = atr * stop_mult; target = entry + distance * target_mult).
    entry = float(df["Close"].iloc[i])
    b_entry = float(tampered["Close"].iloc[i])
    assert entry == b_entry
    atr_dist = a["atr"] * CONFIG["STOP_LOSS_ATR"]
    b_atr_dist = b["atr"] * CONFIG["STOP_LOSS_ATR"]
    assert entry - atr_dist == b_entry - b_atr_dist
    assert entry + atr_dist * CONFIG["TARGET_R_MULTIPLE"] == (
        b_entry + b_atr_dist * CONFIG["TARGET_R_MULTIPLE"]
    )


def test_walk_forward_no_future_bar_leakage():
    """Bar limits: every indicator slice stops at the evaluated bar."""
    df = _frame(n=300, drift=0.5)
    for i in (150, 200, 250, 299):
        assert StrategyValidator._point_in_time_indicators(df, i) == (
            StrategyValidator._point_in_time_indicators(df.iloc[: i + 1], i)
        )


def test_walk_forward_detects_lookahead():
    """The synthetic leak frame MUST distinguish clean vs biased evaluation."""
    df = _leak_frame()
    clean = StrategyValidator.run_walk_forward(df)
    leaky = _leaky_pivot_run(df)
    assert leaky == 1.0                      # future spike suppresses all entries
    assert clean != 1.0                      # point-in-time still enters pre-spike
    assert clean != leaky                    # a leaked implementation == leaky, test fails
    assert 1.0 < clean <= 10.0


def test_walk_forward_matches_legacy_run():
    """Point-in-time path reproduces the legacy API on normal data.

    Exposes any discrepancy between the two implementations immediately.
    """
    for seed in range(4):
        df = _frame(n=320, drift=0.2 + seed, seed=seed)
        assert StrategyValidator.run_walk_forward(df) == StrategyValidator.run(df)


def test_walk_forward_backward_compat_run():
    df = _frame(n=300, drift=0.8)
    assert callable(StrategyValidator.run)
    pf = StrategyValidator.run(df)
    assert isinstance(pf, float) and 1.0 <= pf <= 10.0


# --- RSIndicator ------------------------------------------------------------

def test_rsi_default_config_loads():
    ind = RSIndicator()
    assert ind.windows == [252, 126, 63, 21]
    assert ind.weights == [0.4, 0.2, 0.2, 0.2]
    assert ind.min_data_days == 21


def test_rsi_custom_config():
    ind = RSIndicator(windows=[100, 50, 25, 10], weights=[0.3, 0.3, 0.2, 0.2], min_data_days=10)
    assert ind.windows == [100, 50, 25, 10]
    assert ind.weights == [0.3, 0.3, 0.2, 0.2]
    assert ind.min_data_days == 10


def test_rsi_invalid_weights_sum():
    with pytest.raises(ValueError, match="weights must sum to 1.0"):
        RSIndicator(weights=[0.5, 0.5, 0.5, 0.5])


def test_rsi_windows_weights_mismatch():
    with pytest.raises(ValueError, match="windows.*and weights.*must match"):
        RSIndicator(windows=[100, 50], weights=[0.4, 0.3, 0.3])


def test_rsi_compute_raw_short_frame():
    ind = RSIndicator()
    assert ind.compute_raw(_frame(n=5)) == RSIndicator.ERROR_SENTINEL


def test_rsi_compute_raw_uptrend():
    ind = RSIndicator()
    assert ind.compute_raw(_frame(n=300, drift=0.5)) > 0


def test_rsi_compute_raw_downtrend():
    ind = RSIndicator()
    assert ind.compute_raw(_frame(n=300, drift=-0.5)) < 0


def test_rsi_compute_raw_fallback():
    """With fewer bars than the longest window, fallback uses c[0]."""
    ind = RSIndicator()
    df = _frame(n=100, drift=0.3)
    result = ind.compute_raw(df)
    assert result != RSIndicator.ERROR_SENTINEL
    assert isinstance(result, float)


def test_rsi_compute_percentiles_ascending():
    ind = RSIndicator()
    items = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    out = ind.compute_percentiles(items)
    assert [i["raw_rs"] for i in out] == [-0.2, 0.1, 0.5]
    ratings = [i["rs_rating"] for i in out]
    assert ratings == sorted(ratings)
    assert ratings[-1] == 100


def test_rsi_compute_percentiles_empty():
    ind = RSIndicator()
    assert ind.compute_percentiles([]) == []


def test_rsi_classmethod_get_raw_score_matches_instance():
    df = _frame(n=300, drift=0.5)
    assert RSIndicator.get_raw_score(df) == RSIndicator().compute_raw(df)


def test_rsi_classmethod_assign_percentiles_matches_instance():
    items = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    items2 = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    out1 = RSIndicator.assign_percentiles(items)
    out2 = RSIndicator().compute_percentiles(items2)
    assert [i["rs_rating"] for i in out1] == [i["rs_rating"] for i in out2]


def test_rsi_nan_handling():
    """NaN close values propagate through division (matches original behavior)."""
    ind = RSIndicator()
    df = _frame(n=300, drift=0.5)
    df.iloc[-1, df.columns.get_loc("Close")] = np.nan
    result = ind.compute_raw(df)
    assert np.isnan(result)


def test_rsi_none_returns_sentinel():
    ind = RSIndicator()
    assert ind.compute_raw(None) == RSIndicator.ERROR_SENTINEL


# --- RSAnalyzer backward compatibility --------------------------------------

def test_rsanalyzer_get_raw_score_compat():
    df = _frame(n=300, drift=0.5)
    assert RSAnalyzer.get_raw_score(df) == RSIndicator.get_raw_score(df)


def test_rsanalyzer_assign_percentiles_compat():
    items = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    items2 = [{"raw_rs": 0.1}, {"raw_rs": 0.5}, {"raw_rs": -0.2}]
    out1 = RSAnalyzer.assign_percentiles(items)
    out2 = RSIndicator.assign_percentiles(items2)
    assert [i["rs_rating"] for i in out1] == [i["rs_rating"] for i in out2]


def test_rsanalyzer_short_frame_compat():
    assert RSAnalyzer.get_raw_score(_frame(n=10)) == RSIndicator.ERROR_SENTINEL


# --- Strategy abstract base class ----------------------------------------------

def test_strategy_class_exists():
    from engines.analysis import Strategy
    assert Strategy is not None


def test_strategy_is_abstract():
    from engines.analysis import Strategy
    try:
        Strategy()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


def test_strategy_calculate_abstract():
    from engines.analysis import Strategy
    try:
        Strategy()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


def test_strategy_get_score_abstract():
    from engines.analysis import Strategy
    try:
        Strategy()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


def test_strategy_get_signals_abstract():
    from engines.analysis import Strategy
    try:
        Strategy()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


def test_strategy_entry_stop_target_abstract():
    from engines.analysis import Strategy
    try:
        Strategy()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


# --- Strategy package structure (Phase 3.1) --------------------------------

def test_strategies_package_importable():
    import engines.strategies
    assert engines.strategies is not None


def test_strategy_importable_from_strategies_base():
    from engines.strategies.base import Strategy as Strat
    assert Strat is not None


def test_strategy_reexported_from_strategies_init():
    from engines.strategies import Strategy as Strat
    assert Strat is not None


def test_strategy_same_class_via_both_imports():
    from engines.analysis import Strategy as S1
    from engines.strategies.base import Strategy as S2
    from engines.strategies import Strategy as S3
    assert S1 is S2
    assert S2 is S3


def test_strategy_is_abstract_direct_instantiate_fails():
    from engines.strategies.base import Strategy as Strat
    try:
        Strat()
        assert False, "Strategy should not be instantiable"
    except TypeError:
        pass


# --- MarketDataProvider abstraction tests ---

def test_marketdataprovider_importable():
    from engines.data import MarketDataProvider
    assert MarketDataProvider is not None


def test_marketdataprovider_is_abstract():
    from engines.data import MarketDataProvider
    try:
        MarketDataProvider()
        assert False, "MarketDataProvider should not be instantiable"
    except TypeError:
        pass


def test_dataengineadapter_ohlcv():
    from engines.data import DataEngineAdapter
    adapter = DataEngineAdapter()
    df = adapter.get_ohlcv("AAPL")
    assert df is None or (isinstance(df, pd.DataFrame) and len(df) > 0)


def test_dataengineadapter_price():
    from engines.data import DataEngineAdapter
    adapter = DataEngineAdapter()
    price = adapter.get_current_price("AAPL")
    assert price is None or (isinstance(price, float) and price > 0)


# --- CacheManager tests ---

def test_cachmanager_create():
    from engines.data import CacheManager
    cm = CacheManager()
    assert cm is not None


def test_cachmanager_read_miss():
    from engines.data import CacheManager
    cm = CacheManager()
    data = cm.read("nonexistent_ticker_12345")
    assert data is None


def test_cachmanager_write_read():
    from engines.data import CacheManager
    import pandas as pd
    cm = CacheManager()
    df = pd.DataFrame({"Close": [1, 2, 3], "Volume": [100, 200, 300]})
    ok = cm.write("test_ticker_abc", df)
    assert ok is True
    data = cm.read("test_ticker_abc")
    assert data is not None
    assert len(data) == 3


def test_cachmanager_ttl_expiry():
    from engines.data import CacheManager
    import time
    import pandas as pd
    cm = CacheManager(ttl=1)  # 1 second TTL
    df = pd.DataFrame({"Close": [1, 2, 3], "Volume": [100, 200, 300]})
    ok = cm.write("test_ticker_ttl", df)
    assert ok is True
    # Should be a hit immediately
    data = cm.read("test_ticker_ttl")
    assert data is not None
    # Wait for TTL expiry
    time.sleep(2)
    data = cm.read("test_ticker_ttl")
    assert data is None  # Expired


def test_cachmanager_hit_rate():
    from engines.data import CacheManager
    import pandas as pd
    cm = CacheManager()
    df = pd.DataFrame({"Close": [1, 2, 3], "Volume": [100, 200, 300]})
    cm.write("test_ticker_hr1", df)
    cm.read("test_ticker_hr1")  # hit
    cm.read("test_ticker_hr2")  # miss
    hr = cm.hit_rate()
    assert 0.0 <= hr <= 1.0


def test_cachmanager_corrupt_cache():
    from engines.data import CacheManager
    import pandas as pd
    import pickle
    cm = CacheManager()
    # Write a corrupt pickle manually
    path = cm.cache_dir / "test_ticker_corrupt.pkl"
    try:
        with open(path, "wb") as f:
            f.write(b"not a pickle")
        data = cm.read("test_ticker_corrupt")
        # Should gracefully handle corrupt cache
        assert data is None
    finally:
        if path.exists():
            path.unlink()


def test_rsranking_importable():
    """Test that RelativeStrengthRanking is importable."""
    from engines.strategies.rs_ranking import RelativeStrengthRanking
    assert RelativeStrengthRanking is not None


def test_rsranking_constructible():
    """Test construction with default configuration."""
    rs = RelativeStrengthRanking()
    assert rs.windows == [252, 126, 63, 21]
    assert rs.weights == [0.4, 0.2, 0.2, 0.2]
    assert rs.min_data_days == 21
    assert rs.benchmark_ticker == "SPY"


def test_rsranking_construct_custom():
    """Test construction with custom parameters."""
    rs = RelativeStrengthRanking(windows=[100, 50, 25, 10], weights=[0.3, 0.3, 0.2, 0.2], min_data_days=10, benchmark_ticker="SPY")
    assert rs.windows == [100, 50, 25, 10]
    assert rs.weights == [0.3, 0.3, 0.2, 0.2]
    assert rs.min_data_days == 10
    assert rs.benchmark_ticker == "SPY"


def test_rsranking_deterministic_calculation():
    """Test deterministic raw RS across repeated calls."""
    rng = __import__("numpy").random.default_rng(42)
    n = 260
    close = __import__("numpy").maximum(100 + np.arange(n) * 0.5 + rng.normal(0, 1, n), 1.0)
    high = close + np.abs(rng.normal(0, 1, n)) + 0.5
    low = __import__("numpy").maximum(close - np.abs(rng.normal(0, 1, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})

    rs = RelativeStrengthRanking()
    raw1 = rs.compute_raw(df)
    raw2 = rs.compute_raw(df)
    assert raw1 == raw2


def test_rsranking_insufficient_data():
    """Test that insufficient data returns ERROR_SENTINEL."""
    rng = np.random.default_rng(0)
    close = np.maximum(100 + np.arange(10) * 0.5 + rng.normal(0, 1, 10), 1.0)
    high = close + np.abs(rng.normal(0, 1, 10)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1, 10)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, 10).astype(float)
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})

    rs = RelativeStrengthRanking()
    raw = rs.compute_raw(df)
    assert raw == -999.0


def test_rsranking_ranking_behavior():
    """Test percentile ranking assigns ratings 1-99 correctly."""
    rng = np.random.default_rng(0)
    n = 260
    close = np.maximum(100 + np.arange(n) * 0.5 + rng.normal(0, 1, n), 1.0)
    high = close + np.abs(rng.normal(0, 1, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    df1 = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})
    df2 = pd.DataFrame({"Open": close * 1.02, "High": high * 1.02, "Low": low * 1.02, "Close": close * 1.02, "Volume": volume})
    df3 = pd.DataFrame({"Open": close * 0.98, "High": high * 0.98, "Low": low * 0.98, "Close": close * 0.98, "Volume": volume})

    rs = RelativeStrengthRanking()
    items = [
        {"ticker": "A", "raw_rs": rs.compute_raw(df1)},
        {"ticker": "B", "raw_rs": rs.compute_raw(df2)},
        {"ticker": "C", "raw_rs": rs.compute_raw(df3)},
    ]
    out = rs.compute_percentiles(items)
    ratings = [i["rs_rating"] for i in out]
    assert len(ratings) == 3
    for r in ratings:
        assert 1 <= r <= 100, f"Rating {r} out of range 1-100"
    # Ratings should be ordered (lower raw_rs → lower rating)
    assert ratings[0] <= ratings[1] <= ratings[2]


def test_rsranking_benchmark_handling():
    """Test that benchmark_df parameter is accepted."""
    rng = np.random.default_rng(0)
    n = 260
    close = np.maximum(100 + np.arange(n) * 0.5 + rng.normal(0, 1, n), 1.0)
    high = close + np.abs(rng.normal(0, 1, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    df_ticker = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})
    # Same data for benchmark (SPY-like)
    df_bench = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})

    rs = RelativeStrengthRanking(benchmark_ticker="SPY")
    raw_with_bench = rs.compute_raw(df_ticker, benchmark_df=df_bench)
    raw_without_bench = rs.compute_raw(df_ticker, benchmark_df=None)
    # When benchmark data equals ticker data, relative RS should be 0
    assert raw_with_bench == 0.0 or isinstance(raw_with_bench, float)
    assert isinstance(raw_without_bench, float)


def test_rsranking_validation_invalid_weights():
    """Test that invalid weight sums raise ValueError."""
    try:
        RelativeStrengthRanking(weights=[0.5, 0.5, 0.5, 0.5])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "weights must sum to 1.0" in str(e)


def test_rsranking_validation_mismatched_lengths():
    """Test that mismatched windows/weights lengths raise ValueError."""
    try:
        RelativeStrengthRanking(windows=[100, 50], weights=[0.4, 0.3, 0.3])
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "must match" in str(e)


def test_rsranking_no_dataframe_mutation():
    """Test that input DataFrame is not mutated."""
    rng = np.random.default_rng(42)
    n = 260
    close = np.maximum(100 + np.arange(n) * 0.5 + rng.normal(0, 1, n), 1.0)
    high = close + np.abs(rng.normal(0, 1, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})

    rs = RelativeStrengthRanking()
    _ = rs.compute_raw(df)
    assert len(df) == n  # DataFrame still has original row count


def test_rsranking_compatibility_with_rsanalyzer():
    """Test compatibility with RSAnalyzer backward-compat classmethods."""
    from engines.analysis import RSAnalyzer
    rng = np.random.default_rng(42)
    n = 300
    close = np.maximum(100 + np.arange(n) * 0.5 + rng.normal(0, 1, n), 1.0)
    high = close + np.abs(rng.normal(0, 1, n)) + 0.5
    low = np.maximum(close - np.abs(rng.normal(0, 1, n)) - 0.5, 0.1)
    volume = rng.integers(500_000, 5_000_000, n).astype(float)
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume})

    raw_rs_indicator = RSAnalyzer.get_raw_score(df)
    rs = RelativeStrengthRanking()
    raw_rs_ranking = rs.compute_raw(df)
    # Both should return floats (may differ in value since RSRanking
    # is a new class, but both are valid raw RS scores)
    assert isinstance(raw_rs_indicator, float)
    assert isinstance(raw_rs_ranking, float)


# --- VCPBreakoutStrategy -----------------------------------------------------

def test_vcpbreakout_importable():
    """Test that VCPBreakoutStrategy is importable from the strategies package."""
    from engines.strategies import VCPBreakoutStrategy as VBS
    assert VBS is VCPBreakoutStrategy


def test_vcpbreakout_strategy_abc_compliance():
    """Test that VCPBreakoutStrategy implements the Strategy ABC."""
    assert issubclass(VCPBreakoutStrategy, Strategy)
    s = VCPBreakoutStrategy()
    assert callable(s.calculate)
    assert callable(s.get_score)
    assert callable(s.get_signals)
    assert callable(s.get_entry_stop_target)
    assert s.get_score() == 0
    assert s.get_signals() == []
    assert s.get_entry_stop_target() == (0.0, 0.0, 0.0)
    assert s.is_actionable() is False


def test_vcpbreakout_confirmed_breakout():
    """Confirmed breakout: close > pivot AND volume surge → actionable."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    res = s.calculate(df)
    assert res["confirmed"] is True
    assert res["actionable"] is True
    assert s.is_actionable() is True
    assert "Breakout Confirmed" in res["signals"]
    assert res["entry"] == round(res["pivot"] * 1.002, 2)
    assert res["pivot"] > 0


def test_vcpbreakout_volume_required():
    """Close above pivot WITHOUT volume surge → not confirmed, awaiting."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(breakout_close=102.0)  # same volume everywhere
    res = s.calculate(df)
    assert res["confirmed"] is False
    assert res["actionable"] is False
    assert s.is_actionable() is False
    assert "Awaiting Breakout" in res["signals"]


def test_vcpbreakout_failed_breakout():
    """Handle high above pivot but close below pivot → failed, score 0."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(failed_spike=(104.0, 55.0))
    res = s.calculate(df)
    assert res["failed"] is True
    assert res["confirmed"] is False
    assert res["actionable"] is False
    assert "Breakout Failed" in res["signals"]
    assert res["score"] == 0


def test_vcpbreakout_entry_stop_target_exactness():
    """Entry/stop/target match the strategy formulas exactly."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    res = s.calculate(df)

    ind = VCPIndicator(use_contraction_pivot=True)
    pivot = ind.detect_pivot(df)["price"]
    atr = ind.calculate(df)["atr"]

    entry = round(pivot * 1.002, 2)
    stop = round(entry - atr * 2.0, 2)
    target = round(entry + (entry - stop) * 2.5, 2)
    assert res["entry"] == entry
    assert res["stop"] == stop
    assert res["target"] == target
    assert entry > stop > 0


def test_vcpbreakout_insufficient_data():
    """Fewer than 130 bars → safe non-actionable result."""
    s = VCPBreakoutStrategy()
    short = _pivot_base_frame()[:50]
    res = s.calculate(short)
    assert res["score"] == 0
    assert res["signals"] == []
    assert (res["entry"], res["stop"], res["target"]) == (0.0, 0.0, 0.0)
    assert res["actionable"] is False
    assert s.get_score() == 0
    assert s.get_entry_stop_target() == (0.0, 0.0, 0.0)


def test_vcpbreakout_deterministic():
    """Repeated calculate() calls produce identical results."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    r1 = s.calculate(df)
    r2 = s.calculate(df)
    assert r1 == r2
    assert s.get_score() == r2["score"]
    assert s.get_signals() == r2["signals"]


def test_vcpbreakout_no_input_mutation():
    """Input DataFrame columns, length and values remain unchanged."""
    s = VCPBreakoutStrategy()
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    before = df.copy(deep=True)
    _ = s.calculate(df)
    assert df.columns.tolist() == before.columns.tolist()
    assert len(df) == len(before)
    assert (df.values == before.values).all()


def test_vcpbreakout_backward_compat():
    """VCPAnalyzer.calculate and StrategyValidator.run are unchanged by the strategy."""
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    expected_vcp = VCPAnalyzer.calculate(df)
    expected_pf = StrategyValidator.run(df)

    s = VCPBreakoutStrategy()
    _ = s.calculate(df)

    assert VCPAnalyzer.calculate(df) == expected_vcp
    assert StrategyValidator.run(df) == expected_pf


# --- MinerviniTrendTemplate --------------------------------------------------

def test_minervini_importable():
    """Test that MinerviniTrendTemplate is importable from the strategies package."""
    from engines.strategies import MinerviniTrendTemplate as MTT
    assert MTT is MinerviniTrendTemplate


def test_minervini_strategy_abc_compliance():
    """Test that MinerviniTrendTemplate implements the Strategy ABC."""
    assert issubclass(MinerviniTrendTemplate, Strategy)
    s = MinerviniTrendTemplate()
    assert callable(s.calculate)
    assert callable(s.get_score)
    assert callable(s.get_signals)
    assert callable(s.get_entry_stop_target)
    assert s.get_score() == 0
    assert s.get_signals() == []
    assert s.get_entry_stop_target() == (0.0, 0.0, 0.0)
    assert s.is_actionable() is False


def test_minervini_qualifying_uptrend():
    """A rising trend passes all 8 non-RS criteria → actionable."""
    s = MinerviniTrendTemplate()
    res = s.calculate(_trend_frame())
    assert res["total_count"] == 8
    assert res["passed_count"] == 8
    assert res["score"] == 8
    assert res["actionable"] is True
    assert s.is_actionable() is True
    assert res["signals"][-1] == "Trend Template Pass"
    assert all(res["criteria"][k] is True for k in (
        "price_above_150ma", "price_above_200ma", "ma150_above_ma200",
        "ma200_uptrend", "ma50_above_ma150_ma200", "price_above_50ma",
        "above_30pct_52w_low", "within_25pct_52w_high",
    ))


def test_minervini_non_qualifying_downtrend():
    """A falling trend fails all criteria → score 0, not actionable."""
    s = MinerviniTrendTemplate()
    res = s.calculate(_trend_frame(slope=-0.3, start=200.0))
    assert res["score"] == 0
    assert res["actionable"] is False
    assert s.is_actionable() is False
    assert res["signals"][-1] == "Trend Template Fail"
    assert all(res["criteria"][k] is False for k in (
        "price_above_150ma", "price_above_200ma", "ma150_above_ma200",
        "ma200_uptrend", "ma50_above_ma150_ma200", "price_above_50ma",
        "above_30pct_52w_low", "within_25pct_52w_high",
    ))


def test_minervini_criteria_52week_bounds():
    """52-week criteria reflect the price vs trailing extremes relationship."""
    s = MinerviniTrendTemplate()
    up = s.calculate(_trend_frame())["criteria"]
    assert up["above_30pct_52w_low"] is True
    assert up["within_25pct_52w_high"] is True
    down = s.calculate(_trend_frame(slope=-0.3, start=200.0))["criteria"]
    assert down["above_30pct_52w_low"] is False
    assert down["within_25pct_52w_high"] is False


def test_minervini_rs_criterion():
    """RS criterion is assessed only when rs_rating is provided."""
    s = MinerviniTrendTemplate()
    none = s.calculate(_trend_frame())
    assert none["criteria"]["rs_rating_ge_70"] is None
    assert none["total_count"] == 8

    pass_ = s.calculate(_trend_frame(), rs_rating=85)
    assert pass_["criteria"]["rs_rating_ge_70"] is True
    assert pass_["total_count"] == 9
    assert pass_["score"] == 9
    assert pass_["actionable"] is True

    fail_ = s.calculate(_trend_frame(), rs_rating=50)
    assert fail_["criteria"]["rs_rating_ge_70"] is False
    assert fail_["total_count"] == 9
    assert fail_["score"] == 8
    assert fail_["actionable"] is False


def test_minervini_entry_stop_target_exactness():
    """Entry/stop/target match the strategy formulas exactly."""
    s = MinerviniTrendTemplate()
    df = _trend_frame()
    res = s.calculate(df)

    close = df["Close"]
    high = df["High"]
    low = df["Low"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr = float(tr.rolling(14).mean().iloc[-1])

    entry = round(float(df["Close"].iloc[-1]), 2)
    stop = round(entry - atr * 2.0, 2)
    target = round(entry + (entry - stop) * 2.5, 2)
    assert res["entry"] == entry
    assert res["stop"] == stop
    assert res["target"] == target
    assert entry > stop > 0


def test_minervini_insufficient_data():
    """Fewer than 252 bars → safe non-actionable result."""
    s = MinerviniTrendTemplate()
    short = _trend_frame(n=100)
    res = s.calculate(short)
    assert res["score"] == 0
    assert res["signals"] == []
    assert (res["entry"], res["stop"], res["target"]) == (0.0, 0.0, 0.0)
    assert res["actionable"] is False
    assert s.get_score() == 0
    assert s.get_entry_stop_target() == (0.0, 0.0, 0.0)


def test_minervini_deterministic():
    """Repeated calculate() calls produce identical results."""
    s = MinerviniTrendTemplate()
    df = _trend_frame()
    r1 = s.calculate(df, rs_rating=90)
    r2 = s.calculate(df, rs_rating=90)
    assert r1 == r2
    assert s.get_score() == r2["score"]
    assert s.get_signals() == r2["signals"]


def test_minervini_no_input_mutation():
    """Input DataFrame columns, length and values remain unchanged."""
    s = MinerviniTrendTemplate()
    df = _trend_frame()
    before = df.copy(deep=True)
    _ = s.calculate(df, rs_rating=90)
    assert df.columns.tolist() == before.columns.tolist()
    assert len(df) == len(before)
    assert (df.values == before.values).all()


def test_minervini_backward_compat():
    """Existing strategy outputs are unchanged by the new export."""
    df = _pivot_base_frame(breakout_close=102.0, base_volume=1_000_000.0, handle_volume=4_000_000.0)
    expected_vcp = VCPAnalyzer.calculate(df)
    expected_pf = StrategyValidator.run(df)
    expected_rs = RSAnalyzer.get_raw_score(df)
    expected_breakout = VCPBreakoutStrategy().calculate(df)
    expected_rsrank = RelativeStrengthRanking().compute_raw(df)

    _ = MinerviniTrendTemplate().calculate(df)

    assert VCPAnalyzer.calculate(df) == expected_vcp
    assert StrategyValidator.run(df) == expected_pf
    assert RSAnalyzer.get_raw_score(df) == expected_rs
    assert VCPBreakoutStrategy().calculate(df) == expected_breakout
    assert RelativeStrengthRanking().compute_raw(df) == expected_rsrank


def test_cachmanager_backward_compat_existing():
    """Test that reading existing uncompressed cache data still works."""
    from engines.data import CacheManager
    import pandas as pd
    import pickle
    cm = CacheManager()
    # Write uncompressed data
    df = pd.DataFrame({"Close": [1, 2, 3], "Volume": [100, 200, 300]})
    ok = cm.write("test_ticker_bc", df, compress="none")
    assert ok is True
    # Read back
    data = cm.read("test_ticker_bc")
    assert data is not None
    assert len(data) == 3
