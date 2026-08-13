"""Phase 5.1 BacktestEngine + Phase 5.2 purged k-fold CV tests (no network, synthetic data only)."""
import copy
import math

import pandas as pd
import pytest

from engines.backtest import (
    BacktestEngine,
    RESULT_KEYS,
    CV_KEYS,
    FOLD_RECORD_KEYS,
)
from engines.analysis import StrategyValidator
from engines.strategies.base import Strategy
from engines.strategies.vcp_breakout import VCPBreakoutStrategy


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _frame(n: int, base: float = 100.0) -> pd.DataFrame:
    """Deterministic OHLCV frame of constant price ``base``."""
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {"Open": base, "High": base, "Low": base, "Close": base, "Volume": 1_000_000},
        index=idx,
    )


def _wavy_frame(n: int = 160, base: float = 100.0) -> pd.DataFrame:
    """Deterministic OHLCV frame with a mild sine drift."""
    close = [base + math.sin(i / 10.0) * 3.0 for i in range(n)]
    idx = pd.date_range("2024-01-01", periods=n, freq="B")
    return pd.DataFrame(
        {
            "Open": close,
            "High": [c + 1.0 for c in close],
            "Low": [c - 1.0 for c in close],
            "Close": close,
            "Volume": [1_000_000] * n,
        },
        index=idx,
    )


class _BarTriggeredStrategy(Strategy):
    """Stub Strategy actionable only at the configured trailing bar indices."""

    def __init__(self, actionable_bars, entry=100.0, stop=90.0, target=125.0):
        self._bars = set(int(b) for b in actionable_bars)
        self._entry = entry
        self._stop = stop
        self._target = target
        self._last_slice = None
        self._bar = -1

    def calculate(self, df: pd.DataFrame) -> dict:
        self._last_slice = df.copy()
        self._bar = len(df) - 1
        return {"score": 80, "signals": ["setup"]}

    def get_score(self) -> float:
        return 80.0

    def get_signals(self) -> list:
        return ["setup"]

    def get_entry_stop_target(self):
        return (self._entry, self._stop, self._target)

    def is_actionable(self) -> bool:
        return self._bar in self._bars


# ---------------------------------------------------------------------------
# Importability / construction
# ---------------------------------------------------------------------------

def test_backtest_engine_importable():
    from engines import backtest as m

    assert hasattr(m, "BacktestEngine")
    assert hasattr(m, "RESULT_KEYS")
    assert "profit_factor" in m.RESULT_KEYS


def test_backtest_constructor_validation():
    with pytest.raises(ValueError):
        BacktestEngine(min_bars_for_entry=0)
    with pytest.raises(ValueError):
        BacktestEngine(lookback_bars=0)
    with pytest.raises(ValueError):
        BacktestEngine(risk_pct=0)
    with pytest.raises(ValueError):
        BacktestEngine(initial_capital=-1)


def test_backtest_config_defaults():
    eng = BacktestEngine()
    assert eng.lookback_bars == 250
    assert eng.min_bars_for_entry == 50
    assert eng.risk_pct == 0.015


def test_backtest_constructor_overrides():
    eng = BacktestEngine(lookback_bars=400, min_bars_for_entry=120, risk_pct=0.02)
    assert eng.lookback_bars == 400
    assert eng.min_bars_for_entry == 120
    assert eng.risk_pct == 0.02


# ---------------------------------------------------------------------------
# Insufficient data safety
# ---------------------------------------------------------------------------

def test_backtest_insufficient_data_none():
    eng = BacktestEngine(min_bars_for_entry=50)
    rec = eng.run(_BarTriggeredStrategy({}), None)
    assert rec["insufficient_data"] is True
    assert rec["profit_factor"] == 1.0
    assert rec["trades"] == []
    assert rec["n_trades"] == 0
    assert rec["start"] is None
    assert rec["evaluated_bars"] == 0


def test_backtest_insufficient_data_empty_and_short():
    eng = BacktestEngine(min_bars_for_entry=50)
    empty = eng.run(_BarTriggeredStrategy({}), pd.DataFrame())
    assert empty["insufficient_data"] is True and empty["trades"] == []

    short = eng.run(_BarTriggeredStrategy({}), _frame(n=30))
    assert short["insufficient_data"] is True and short["trades"] == []
    assert short["profit_factor"] == 1.0


def test_backtest_missing_ohlc_columns_safe():
    eng = BacktestEngine(min_bars_for_entry=10)
    df = pd.DataFrame({"Close": [100.0] * 20})
    rec = eng.run(_BarTriggeredStrategy({}), df)
    assert rec["insufficient_data"] is True
    assert rec["reason"] == "missing_ohlc_columns"
    assert rec["trades"] == []


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------

def test_backtest_deterministic_repeated_runs():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    df = _frame(n=100)
    strat = _BarTriggeredStrategy({10, 12})
    first = eng.run(strat, df)
    second = eng.run(strat, df)
    third = eng.run(strat, df)
    assert second == first == third


# ---------------------------------------------------------------------------
# Point-in-time isolation / no-future-bar leakage
# ---------------------------------------------------------------------------

def test_backtest_evaluate_at_is_trailing_only():
    eng = BacktestEngine(min_bars_for_entry=10)
    df = _frame(n=100)
    strat = _BarTriggeredStrategy({15})
    full = eng.evaluate_at(strat, df, 15)
    truncated = eng.evaluate_at(strat, df.iloc[:16], 15)
    assert full == truncated
    assert full["actionable"] is True
    assert full["entry"] == 100.0 and full["stop"] == 90.0 and full["target"] == 125.0

    not_yet = eng.evaluate_at(strat, df, 14)
    assert not_yet["actionable"] is False


def test_backtest_future_spike_does_not_affect_past_decision():
    eng = BacktestEngine(min_bars_for_entry=10)
    df = _frame(n=100)
    spike = df.copy()
    spike.iloc[80, spike.columns.get_loc("Close")] = df.iloc[80]["Close"] * 100.0
    spike.iloc[80, spike.columns.get_loc("High")] = df.iloc[80]["High"] * 100.0

    strat = _BarTriggeredStrategy({15})
    assert eng.evaluate_at(strat, df, 15) == eng.evaluate_at(strat, spike, 15)


def test_backtest_run_level_no_future_bar_leakage():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    # Price 80 < stop 90: every position closes on the stop within 2 bars,
    # so no position is open when the spiked bar is appended.
    df = _frame(n=100, base=80.0)
    strat = _BarTriggeredStrategy({10, 12})

    base = eng.run(strat, df)
    assert base["trades"] == [-1.0, -1.0]

    spiked = pd.concat([df, pd.DataFrame(
        {"Open": [10000.0], "High": [10000.0], "Low": [10000.0], "Close": [10000.0], "Volume": [1_000_000]},
        index=[df.index[-1] + pd.Timedelta(days=1)],
    )])
    future = eng.run(strat, spiked)

    for key in ("profit_factor", "trades", "n_trades", "win_rate", "total_return_pct", "max_drawdown_pct"):
        assert base[key] == future[key], key


# ---------------------------------------------------------------------------
# Trade entry / stop / target correctness
# ---------------------------------------------------------------------------

def test_backtest_trade_entry_stop_target_correctness():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    df = _frame(n=100)
    df.iloc[11, df.columns.get_loc("Low")] = 85.0    # in-pos bar 11 -> stop -> -1.0 R
    df.iloc[13, df.columns.get_loc("High")] = 130.0  # in-pos bar 13 -> target -> +2.5 R
    # bar 10 entry (100/90/125), bar 12 re-entry after the stop, bar 13 target.

    rec = eng.run(_BarTriggeredStrategy({10, 12}), df)
    assert rec["trades"] == [-1.0, 2.5]
    assert rec["n_trades"] == 2
    assert rec["win_rate"] == 0.5
    assert rec["profit_factor"] == 2.5
    assert rec["start"] == 10
    assert rec["evaluated_bars"] == 90
    assert rec["insufficient_data"] is False

    # Equity: 100000 -> *0.985 -> *1.0375 = 102193.75 -> +2.19%
    assert rec["total_return_pct"] == 2.19
    assert rec["max_drawdown_pct"] == 1.5
    assert isinstance(rec["annualized_return_pct"], float)


def test_backtest_no_trades_is_safe():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    rec = eng.run(_BarTriggeredStrategy(set()), _frame(n=100))
    assert rec["profit_factor"] == 1.0
    assert rec["trades"] == []
    assert rec["n_trades"] == 0
    assert rec["win_rate"] == 0.0
    assert rec["total_return_pct"] == 0.0
    assert rec["max_drawdown_pct"] == 0.0


# ---------------------------------------------------------------------------
# Metrics schema
# ---------------------------------------------------------------------------

def test_backtest_metrics_schema():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    rec = eng.run(_BarTriggeredStrategy({10}), _frame(n=100))
    assert set(rec.keys()) == set(RESULT_KEYS)
    assert isinstance(rec["profit_factor"], float)
    assert isinstance(rec["trades"], list)
    assert isinstance(rec["n_trades"], int)
    assert isinstance(rec["win_rate"], float)
    assert isinstance(rec["total_return_pct"], float)
    assert rec["annualized_return_pct"] is None or isinstance(rec["annualized_return_pct"], float)
    assert isinstance(rec["max_drawdown_pct"], float)
    assert isinstance(rec["start"], int)
    assert isinstance(rec["evaluated_bars"], int)
    assert rec["insufficient_data"] is False
    assert rec["reason"] is None


# ---------------------------------------------------------------------------
# No input mutation
# ---------------------------------------------------------------------------

def test_backtest_no_input_mutation():
    eng = BacktestEngine(lookback_bars=1000, min_bars_for_entry=10)
    df = _frame(n=100)
    df_snapshot = df.copy(deep=True)
    strat = _BarTriggeredStrategy({10, 12})
    strat_snapshot = copy.deepcopy(strat)

    eng.run(strat, df)
    pd.testing.assert_frame_equal(df, df_snapshot)
    assert strat._bar == strat_snapshot._bar == -1
    assert strat._last_slice is None  # engine deep-copied; caller instance untouched


# ---------------------------------------------------------------------------
# Arbitrary Strategy support / backward compatibility
# ---------------------------------------------------------------------------

def test_backtest_supports_real_strategy():
    eng = BacktestEngine(min_bars_for_entry=130)
    strat = VCPBreakoutStrategy()
    rec = eng.run(strat, _frame(n=160))
    assert set(rec.keys()) == set(RESULT_KEYS)
    assert rec["insufficient_data"] is False
    assert rec["trades"] == []  # flat frame -> no breakout -> no trades
    assert rec["profit_factor"] == 1.0
    rerun = eng.run(strat, _frame(n=160))
    assert rerun == rec


def test_backtest_strategy_validator_backward_compat():
    # Production path untouched: run()/evaluate_walk_forward still intact.
    assert callable(StrategyValidator.run)
    assert callable(StrategyValidator.evaluate_walk_forward)
    assert callable(StrategyValidator.run_walk_forward)

    val = StrategyValidator.run(_frame(n=300))
    assert isinstance(val, float) and 1.0 <= val <= 10.0

    rec = StrategyValidator.evaluate_walk_forward(_frame(n=300))
    assert isinstance(rec, dict) and "profit_factor" in rec


# ---------------------------------------------------------------------------
# Phase 5.2 — purged k-fold CV: importability / schema / validation
# ---------------------------------------------------------------------------

def test_cv_importable():
    from engines import backtest as m

    assert hasattr(m, "CV_KEYS")
    assert hasattr(m, "FOLD_RECORD_KEYS")
    assert callable(BacktestEngine.cross_validate)
    assert callable(BacktestEngine.fold_bounds)


def test_cv_param_validation():
    eng = BacktestEngine(min_bars_for_entry=10)
    stub = _BarTriggeredStrategy({})
    with pytest.raises(ValueError):
        eng.cross_validate(stub, _frame(100), n_folds=1)
    with pytest.raises(ValueError):
        eng.cross_validate(stub, _frame(100), purge_gap=-1)
    with pytest.raises(ValueError):
        eng.cross_validate(stub, _frame(100), embargo=-1)


def test_cv_insufficient_data_safe_record():
    eng = BacktestEngine(min_bars_for_entry=50)
    stub = _BarTriggeredStrategy({})
    for bad in (None, pd.DataFrame(), _frame(n=30)):
        cv = eng.cross_validate(stub, bad, n_folds=5, purge_gap=1, embargo=1)
        assert cv["insufficient_data"] is True
        assert cv["reason"] == "insufficient_data"
        assert cv["n_folds"] == 5
        assert cv["purge_gap"] == 1
        assert cv["embargo"] == 1
        assert cv["fold_bounds"] == []
        assert cv["folds"] == []
        assert cv["mean_profit_factor"] is None
        assert cv["mean_total_return_pct"] is None


def test_cv_missing_ohlc_columns_safe_record():
    eng = BacktestEngine(min_bars_for_entry=10)
    df = pd.DataFrame({"Close": [100.0] * 100, "Volume": [1000] * 100})
    cv = eng.cross_validate(_BarTriggeredStrategy({}), df, n_folds=5)
    assert cv["insufficient_data"] is True
    assert cv["reason"] == "missing_ohlc_columns"
    assert cv["folds"] == []


# ---------------------------------------------------------------------------
# Phase 5.2 — fold count / boundaries / purge / embargo
# ---------------------------------------------------------------------------

def test_cv_fold_count_and_boundaries():
    bounds = BacktestEngine.fold_bounds(
        100, 5, purge_gap=2, embargo=3, min_bars_for_entry=10
    )
    assert len(bounds) == 5
    expected = [
        {"fold": 0, "test_start": 0, "test_end": 19, "eval_start": 10, "eval_end": 16},
        {"fold": 1, "test_start": 20, "test_end": 39, "eval_start": 22, "eval_end": 36},
        {"fold": 2, "test_start": 40, "test_end": 59, "eval_start": 42, "eval_end": 56},
        {"fold": 3, "test_start": 60, "test_end": 79, "eval_start": 62, "eval_end": 76},
        {"fold": 4, "test_start": 80, "test_end": 99, "eval_start": 82, "eval_end": 96},
    ]
    assert bounds == expected


def test_cv_default_fold_boundaries():
    bounds = BacktestEngine.fold_bounds(100, 4)
    assert len(bounds) == 4
    assert [b["test_start"] for b in bounds] == [0, 25, 50, 75]
    assert [b["test_end"] for b in bounds] == [24, 49, 74, 99]
    for b in bounds:
        assert b["eval_start"] == b["test_start"]
        assert b["eval_end"] == b["test_end"]


def test_cv_purge_gap_enforced():
    bounds = BacktestEngine.fold_bounds(
        200, 5, purge_gap=10, embargo=0, min_bars_for_entry=5
    )
    for b in bounds:
        # Every fold's first evaluated bar is at least purge_gap past fold start.
        assert b["eval_start"] >= b["test_start"] + 10
        # When the warm-up bound does not override, it is exactly purge_gap.
        if b["test_start"] + 10 >= 5:
            assert b["eval_start"] == b["test_start"] + 10


def test_cv_embargo_enforced():
    bounds = BacktestEngine.fold_bounds(
        200, 5, purge_gap=0, embargo=7, min_bars_for_entry=0
    )
    for b in bounds:
        assert b["eval_end"] == b["test_end"] - 7


def test_cv_no_overlap_between_folds():
    eng = BacktestEngine(min_bars_for_entry=10)
    cv = eng.cross_validate(
        _BarTriggeredStrategy({10}), _frame(200), n_folds=5, purge_gap=5, embargo=4
    )
    assert cv["insufficient_data"] is False
    windows = [(b["eval_start"], b["eval_end"]) for b in cv["fold_bounds"]]
    prev_end = None
    for es, ee in windows:
        assert es <= ee
        if prev_end is not None:
            assert es > prev_end  # strictly non-overlapping
            assert es - prev_end - 1 == 9  # gap == purge_gap + embargo
        prev_end = ee


# ---------------------------------------------------------------------------
# Phase 5.2 — determinism / leakage confinement / fold records
# ---------------------------------------------------------------------------

def test_cv_deterministic_repeated_runs():
    eng = BacktestEngine(min_bars_for_entry=10)
    stub = _BarTriggeredStrategy({10, 12})
    first = eng.cross_validate(stub, _frame(300), n_folds=5, purge_gap=4, embargo=3)
    second = eng.cross_validate(stub, _frame(300), n_folds=5, purge_gap=4, embargo=3)
    assert second == first


def test_cv_schema():
    eng = BacktestEngine(min_bars_for_entry=10)
    cv = eng.cross_validate(
        _BarTriggeredStrategy({10}), _frame(300), n_folds=5, purge_gap=4, embargo=3
    )
    assert set(cv.keys()) == set(CV_KEYS)
    assert len(cv["folds"]) == 5
    assert isinstance(cv["mean_profit_factor"], float)
    assert isinstance(cv["mean_total_return_pct"], float)
    for rec in cv["folds"]:
        assert set(rec.keys()) == set(FOLD_RECORD_KEYS)
        assert isinstance(rec["profit_factor"], float)
        assert isinstance(rec["trades"], list)
        assert isinstance(rec["n_trades"], int)
        assert rec["insufficient_data"] is False
        assert rec["reason"] is None


def test_cv_end_of_window_partial_exit_confines_label():
    # k=2 over 100 bars: fold0 eval [10, 49], fold1 eval [50, 99].
    eng = BacktestEngine(min_bars_for_entry=10)
    stub = _BarTriggeredStrategy({10})  # actionable only at bar 10
    cv = eng.cross_validate(stub, _frame(100), n_folds=2, purge_gap=0, embargo=0)

    fold0 = cv["folds"][0]
    assert fold0["trades"] == [0.0]  # partial exit AT eval_end (bar 49)
    assert fold0["n_trades"] == 1
    assert fold0["start"] == 10
    assert fold0["evaluated_bars"] == 40
    assert fold0["eval_start"] == 10 and fold0["eval_end"] == 49

    fold1 = cv["folds"][1]
    assert fold1["trades"] == []  # no trade leaks past fold0's eval_end
    assert fold1["n_trades"] == 0


def test_cv_end_of_window_exit_respects_embargo():
    eng = BacktestEngine(min_bars_for_entry=10)
    stub = _BarTriggeredStrategy({10})
    cv = eng.cross_validate(stub, _frame(100), n_folds=2, purge_gap=0, embargo=3)
    fold0 = cv["folds"][0]
    assert fold0["eval_start"] == 10
    assert fold0["eval_end"] == 46
    assert fold0["evaluated_bars"] == 37
    assert fold0["trades"] == [0.0]  # closed at bar 46, the embargo-shortened end


def test_cv_stop_inside_fold():
    # Stub stops (price < stop) quickly inside fold0; no leakage into fold1.
    eng = BacktestEngine(min_bars_for_entry=10)
    df = _frame(n=100, base=80.0)  # price 80 <= stop 90 -> -1.0 R
    stub = _BarTriggeredStrategy({10, 12})
    cv = eng.cross_validate(stub, df, n_folds=2, purge_gap=0, embargo=0)
    assert cv["folds"][0]["trades"] == [-1.0, -1.0]
    assert cv["folds"][1]["trades"] == []
    assert cv["folds"][0]["profit_factor"] == 0.0
    assert cv["folds"][1]["profit_factor"] == 1.0  # no trades -> flat pf 1.0
    assert cv["mean_profit_factor"] == 0.5  # (0.0 + 1.0) / 2


def test_cv_fold_too_small_is_safe():
    eng = BacktestEngine(min_bars_for_entry=10)
    cv = eng.cross_validate(
        _BarTriggeredStrategy({10}), _frame(100), n_folds=5, purge_gap=60, embargo=60
    )
    assert len(cv["folds"]) == 5
    for rec in cv["folds"]:
        assert rec["insufficient_data"] is True
        assert rec["reason"] == "fold_too_small"
        assert rec["trades"] == []
    assert cv["mean_profit_factor"] is None
    assert cv["mean_total_return_pct"] is None


def test_cv_mixed_valid_and_too_small_folds():
    # min_bars=60 makes the first (short) fold invalid; the second fold is valid.
    eng = BacktestEngine(min_bars_for_entry=60)
    cv = eng.cross_validate(
        _BarTriggeredStrategy({}), _frame(100), n_folds=2, purge_gap=0, embargo=0
    )
    assert cv["folds"][0]["reason"] == "fold_too_small"
    assert cv["folds"][0]["insufficient_data"] is True
    assert cv["folds"][1]["insufficient_data"] is False
    assert isinstance(cv["mean_profit_factor"], float)


# ---------------------------------------------------------------------------
# Phase 5.2 — no input mutation / real strategy
# ---------------------------------------------------------------------------

def test_cv_no_input_mutation():
    eng = BacktestEngine(min_bars_for_entry=10)
    df = _frame(n=100)
    df_snapshot = df.copy(deep=True)
    stub = _BarTriggeredStrategy({10, 12})
    eng.cross_validate(stub, df, n_folds=3, purge_gap=2, embargo=1)
    pd.testing.assert_frame_equal(df, df_snapshot)
    assert stub._bar == -1
    assert stub._last_slice is None


def test_cv_real_strategy_smoke():
    eng = BacktestEngine(min_bars_for_entry=130)
    cv = eng.cross_validate(
        VCPBreakoutStrategy(), _wavy_frame(1000), n_folds=4, purge_gap=20, embargo=10
    )
    assert set(cv.keys()) == set(CV_KEYS)
    assert cv["insufficient_data"] is False
    assert len(cv["folds"]) == 4
    for rec in cv["folds"]:
        assert rec["insufficient_data"] is False
        assert rec["eval_start"] <= rec["eval_end"]
        assert rec["eval_start"] - rec["test_start"] >= 20
        assert rec["test_end"] - rec["eval_end"] >= 10
    assert isinstance(cv["mean_profit_factor"], float)

    rerun = eng.cross_validate(
        VCPBreakoutStrategy(), _wavy_frame(1000), n_folds=4, purge_gap=20, embargo=10
    )
    assert rerun == cv
