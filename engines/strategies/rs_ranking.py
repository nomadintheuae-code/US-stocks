"""Relative Strength Ranking indicator.

Computes relative strength scores for a universe of tickers compared
to a benchmark index, and assigns cross-sectional percentiles (1-99).

This is an INDICATOR, not a replacement for RSIndicator. It is additive
and opt-in. Existing RSIndicator and RSAnalyzer behavior is completely
unchanged.
"""

from typing import List, Optional

import pandas as pd


class RelativeStrengthRanking:
    """Relative strength ranking vs benchmark.

    Computes relative strength scores for a universe of tickers
    compared to a benchmark index (default SPY), then assigns
    cross-sectional percentiles (1-99) within the universe.

    This is an INDICATOR, not a replacement for RSIndicator.
    It is additive and opt-in. Existing RSIndicator and
    RSAnalyzer behavior is completely unchanged.

    Configuration
    -------------

    Windows and weights control the momentum lookback periods used
    for both the ticker and the benchmark. If no benchmark data is
    provided, the ticker's raw weighted-momentum score is returned
    unchanged (benchmark-relative mode requires benchmark_df).

    Percentile assignment uses the same cross-sectional sort-as-you-go
    algorithm as RSIndicator.assign_percentiles.
    """

    DEFAULT_WINDOWS = [252, 126, 63, 21]
    DEFAULT_WEIGHTS = [0.4, 0.2, 0.2, 0.2]
    DEFAULT_MIN_DATA_DAYS = 21
    ERROR_SENTINEL = -999.0

    def __init__(
        self,
        windows: Optional[List[int]] = None,
        weights: Optional[List[float]] = None,
        min_data_days: Optional[int] = None,
        benchmark_ticker: str = "SPY",
    ):
        self.windows = windows if windows is not None else self.DEFAULT_WINDOWS
        self.weights = weights if weights is not None else self.DEFAULT_WEIGHTS
        self.min_data_days = min_data_days if min_data_days is not None else self.DEFAULT_MIN_DATA_DAYS
        self.benchmark_ticker = benchmark_ticker
        self._validate_config()

    # ------------------------------------------------------------------
    # Config validation
    # ------------------------------------------------------------------

    def _validate_config(self) -> None:
        if len(self.windows) != len(self.weights):
            raise ValueError(
                f"windows ({len(self.windows)}) and weights ({len(self.weights)}) must match"
            )
        if abs(sum(self.weights) - 1.0) > 0.001:
            raise ValueError(f"weights must sum to 1.0, got {sum(self.weights)}")
        if self.min_data_days < 1:
            raise ValueError(f"min_data_days must be >= 1, got {self.min_data_days}")

    # ------------------------------------------------------------------
    # Raw RS computation
    # ------------------------------------------------------------------

    def compute_raw(self, df: pd.DataFrame, benchmark_df: pd.DataFrame = None) -> float:
        """Compute the raw relative-strength score for a single ticker.

        If *benchmark_df* is provided, the RS score is the ticker's
        weighted-momentum score minus the benchmark's weighted-momentum
        score (out-performance / under-performance relative to the
        benchmark).  If *benchmark_df* is ``None`` the method falls back
        to the ticker's raw momentum score, which is still a valid
        relative-strength number (just not benchmark-relative).

        Returns ``ERROR_SENTINEL`` (-999.0) when there is insufficient
        data.
        """
        try:
            c = df["Close"]
            if len(c) < self.min_data_days:
                return self.ERROR_SENTINEL

            returns = []
            for window in self.windows:
                if len(c) >= window:
                    returns.append(c.iloc[-1] / c.iloc[-window] - 1)
                else:
                    returns.append(c.iloc[-1] / c.iloc[0] - 1)

            raw_ticker = sum(r * w for r, w in zip(returns, self.weights))

            if benchmark_df is not None:
                b = benchmark_df["Close"]
                if len(b) < self.min_data_days:
                    # Can't compute benchmark; return raw tick score
                    return raw_ticker

                b_returns = []
                for window in self.windows:
                    if len(b) >= window:
                        b_returns.append(b.iloc[-1] / b.iloc[-window] - 1)
                    else:
                        b_returns.append(b.iloc[-1] / b.iloc[0] - 1)

                raw_benchmark = sum(r * w for r, w in zip(b_returns, self.weights))
                return raw_ticker - raw_benchmark

            return raw_ticker

        except Exception:
            return self.ERROR_SENTINEL

    # ------------------------------------------------------------------
    # Percentile assignment
    # ------------------------------------------------------------------

    def compute_percentiles(self, raw_list: List[dict]) -> List[dict]:
        """Assign percentile ratings (1-99) to a list of ``{'raw_rs': float}`` dicts.

        Sorts the list in-place by ``raw_rs`` ascending, then writes
        ``rs_rating`` for each item.  The worst performer gets rating 1,
        the best gets rating 99.

        Returns *raw_list* (same object, mutated in place) for convenience.
        """
        if not raw_list:
            return raw_list
        raw_list.sort(key=lambda x: x["raw_rs"])
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 99) + 1
        return raw_list

    # ------------------------------------------------------------------
    # Universe ranking workflow
    # ------------------------------------------------------------------

    def rank_universe(
        self,
        universe_dfs: dict[str, pd.DataFrame],
        benchmark_df: pd.DataFrame = None,
    ) -> List[dict]:
        """Compute raw RS for every ticker in *universe_dfs* and assign percentiles.

        Returns a list of dicts, each with at minimum:
            - ``ticker``: the ticker symbol
            - ``raw_rs``: the raw relative-strength score
            - ``rs_rating``: the cross-sectional percentile (1-99)

        If *benchmark_df* is provided the scores are benchmark-relative
        (ticker minus benchmark).  If *benchmark_df* is ``None`` the
        scores are absolute weighted-momentum values.
        """
        results: List[dict] = []
        for symbol, df in universe_dfs.items():
            raw = self.compute_raw(df, benchmark_df=benchmark_df)
            results.append({"ticker": symbol, "raw_rs": raw})
        return self.compute_percentiles(results)