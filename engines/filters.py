"""Phase 4 Filters & Ranking layer for SENTINEL PRO.

Additive, opt-in filter framework. It is NOT wired into ``sentinel.py``:
the scanner's default behavior (310 scanned / 30 qualified / 15 ACTION) is
byte-for-byte unchanged unless a caller explicitly enables the engine.

This module owns:
- ``Filter`` — abstract base class for a single scan filter.
- ``FilterEngine`` — registry + execution pipeline (universe stage before RS
  ranking, candidate stage after technical qualification).
- ``FilterContext`` / ``FilterResult`` — value types passed around the pipeline.

Default behavior: a ``FilterEngine`` constructed without filters, or one built
from config while ``filters.enabled`` is false, is an identity pass-through:
``filter_universe(tickers) -> (list(tickers), [])`` and
``filter_candidates(items) -> (list(items), [])``.

Concrete filters:
- ``LiquidityFilter`` — average dollar volume / average volume (universe stage).
- ``MarketCapFilter`` — market-capitalization range (universe stage).

Sector and fundamental filters are added in later Phase 4 slices.
Default behavior: a ``FilterEngine`` constructed without filters, or one built
from config while ``filters.enabled`` is false, is an identity pass-through:
``filter_universe(tickers) -> (list(tickers), [])`` and
``filter_candidates(items) -> (list(items), [])``.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

import pandas as pd

from engines.data import DataEngine

STAGE_UNIVERSE = "universe"    # applied to the ticker list BEFORE RS ranking
STAGE_CANDIDATE = "candidate"  # applied to technically-qualified candidates


@dataclass
class FilterContext:
    """Per-ticker inputs a filter may inspect.

    All fields are optional: a stage may run with partial data (offline
    tests, missing ``.info``, etc.). Filters must treat missing data as a
    pass (default-permissive) unless the caller configured a hard rule.
    """

    ticker: str
    df: Optional[pd.DataFrame] = None     # OHLCV frame (liquidity / volume)
    sector: Optional[str] = None          # sector name (sector filters)
    profile: Optional[dict] = None        # .info-derived dict (market cap, volumes, fundamentals)


@dataclass
class FilterResult:
    """Outcome of a single filter check."""

    passed: bool
    reason: str = ""


class Filter(ABC):
    """Abstract base class for a single scan filter.

    Subclasses implement ``check()`` returning a ``FilterResult``. ``name``
    must be unique within an engine; ``stage`` selects whether the filter runs
    on the universe (``STAGE_UNIVERSE``) or on qualified candidates
    (``STAGE_CANDIDATE``).
    """

    name: str = "filter"
    stage: str = STAGE_UNIVERSE

    @abstractmethod
    def check(self, ctx: FilterContext) -> FilterResult:
        """Return whether ``ctx`` passes this filter."""
        raise NotImplementedError


class LiquidityFilter(Filter):
    """Universe-stage liquidity filter.

    Requires minimum average dollar volume and/or minimum average volume.
    Metrics are computed from the OHLCV frame (``ctx.df``) via
    ``DataEngine.get_liquidity_metrics`` (trailing-only, look-ahead-free);
    when no frame is available the volume threshold falls back to the
    profile's ``average_volume`` (``.info``). Missing data is default-permissive.
    """

    name = "liquidity"
    stage = STAGE_UNIVERSE

    def __init__(
        self,
        min_avg_dollar_volume: Optional[float] = None,
        min_avg_volume: Optional[float] = None,
    ) -> None:
        self.min_avg_dollar_volume = min_avg_dollar_volume
        self.min_avg_volume = min_avg_volume

    def check(self, ctx: FilterContext) -> FilterResult:
        if self.min_avg_dollar_volume is None and self.min_avg_volume is None:
            return FilterResult(passed=True)

        dollar = self._dollar_volume(ctx)
        volume = self._volume(ctx)

        reasons: List[str] = []
        if self.min_avg_dollar_volume is not None and dollar is not None and dollar < self.min_avg_dollar_volume:
            reasons.append(f"avg_dollar_volume {dollar:.0f} < {self.min_avg_dollar_volume:.0f}")
        if self.min_avg_volume is not None and volume is not None and volume < self.min_avg_volume:
            reasons.append(f"avg_volume {volume:.0f} < {self.min_avg_volume:.0f}")

        if reasons:
            return FilterResult(passed=False, reason="; ".join(reasons))
        return FilterResult(passed=True)

    @staticmethod
    def _dollar_volume(ctx: FilterContext) -> Optional[float]:
        if ctx.df is not None and not ctx.df.empty:
            try:
                return DataEngine.get_liquidity_metrics(ctx.df)["avg_dollar_volume"]
            except Exception:
                return None
        return None

    @staticmethod
    def _volume(ctx: FilterContext) -> Optional[float]:
        if ctx.df is not None and not ctx.df.empty:
            try:
                metrics = DataEngine.get_liquidity_metrics(ctx.df)
                if metrics["avg_volume"] is not None:
                    return metrics["avg_volume"]
            except Exception:
                pass
        if ctx.profile:
            return ctx.profile.get("average_volume")
        return None


class MarketCapFilter(Filter):
    """Universe-stage market-capitalization range filter.

    Applies ``min_usd`` / ``max_usd`` (inclusive) to ``ctx.profile["market_cap"]``.
    Missing profile data is default-permissive.
    """

    name = "market_cap"
    stage = STAGE_UNIVERSE

    def __init__(
        self,
        min_usd: Optional[float] = None,
        max_usd: Optional[float] = None,
    ) -> None:
        self.min_usd = min_usd
        self.max_usd = max_usd

    def check(self, ctx: FilterContext) -> FilterResult:
        if self.min_usd is None and self.max_usd is None:
            return FilterResult(passed=True)

        mc = (ctx.profile or {}).get("market_cap")
        if mc is None:
            return FilterResult(passed=True)

        if self.min_usd is not None and mc < self.min_usd:
            return FilterResult(passed=False, reason=f"market_cap {mc:.0f} < {self.min_usd:.0f}")
        if self.max_usd is not None and mc > self.max_usd:
            return FilterResult(passed=False, reason=f"market_cap {mc:.0f} > {self.max_usd:.0f}")
        return FilterResult(passed=True)


class FilterEngine:
    """Registry + execution pipeline for scan filters.

    Disabled engines are pure identity pass-throughs regardless of the
    registered filters. Enabling is explicit (``enabled=True``) and only
    happens when a caller opts in via ``config.yaml -> filters.enabled``.

    ``provider`` callables supply per-ticker data lazily:

        provider(ticker) -> FilterContext

    When a provider is omitted, filters receive a context containing only the
    ticker (missing data is handled as a pass by well-behaved filters).
    Execution is deterministic: input order is preserved and filters run in
    registration order for each stage.
    """

    def __init__(
        self,
        filters: Optional[Sequence[Filter]] = None,
        enabled: bool = False,
    ) -> None:
        self._filters: List[Filter] = []
        self._enabled = bool(enabled)
        if filters:
            self.add_many(filters)

    # ------------------------------------------------------------------ config

    @classmethod
    def from_config(cls, config=None, enabled_override: Optional[bool] = None) -> "FilterEngine":
        """Build an engine from the ``filters:`` config section.

        Reads the Pydantic Config (``sentinel.config.get_config()``) by
        default, or accepts an explicit Config instance for tests.
        Concrete filter classes are constructed by ``_build_filters``; with
        none implemented yet the engine is empty (identity).
        """
        cfg = config
        if cfg is None:
            try:
                from sentinel.config import get_config
                cfg = get_config()
            except Exception:
                cfg = None

        filter_cfg = getattr(cfg, "filters", None)
        enabled = bool(filter_cfg.enabled) if filter_cfg is not None else False
        if enabled_override is not None:
            enabled = bool(enabled_override)

        filters = cls._build_filters(filter_cfg) if filter_cfg is not None else []
        return cls(filters=filters, enabled=enabled)

    @staticmethod
    def _build_filters(filter_cfg) -> List["Filter"]:
        """Instantiate the concrete filters configured for the pipeline.

        A filter is constructed only when at least one of its thresholds is
        configured (all-None sections yield no filter). Order: liquidity,
        market cap — each remains disabled unless ``filters.enabled`` is set.
        """
        filters: List[Filter] = []

        liq = filter_cfg.liquidity
        if liq.min_avg_dollar_volume is not None or liq.min_avg_volume is not None:
            filters.append(LiquidityFilter(
                min_avg_dollar_volume=liq.min_avg_dollar_volume,
                min_avg_volume=liq.min_avg_volume,
            ))

        mc = filter_cfg.market_cap
        if mc.min_usd is not None or mc.max_usd is not None:
            filters.append(MarketCapFilter(min_usd=mc.min_usd, max_usd=mc.max_usd))

        return filters

    # ----------------------------------------------------------------- registry

    @property
    def enabled(self) -> bool:
        """Whether the engine actively applies filters."""
        return self._enabled

    @property
    def filters(self) -> Tuple[Filter, ...]:
        """Registered filters in registration order."""
        return tuple(self._filters)

    @property
    def names(self) -> Tuple[str, ...]:
        """Registered filter names in registration order."""
        return tuple(f.name for f in self._filters)

    def add(self, f: Filter) -> None:
        """Register a filter. Raises on non-Filter or duplicate name."""
        if not isinstance(f, Filter):
            raise TypeError("filters must subclass engines.filters.Filter")
        if f.name in self.names:
            raise ValueError(f"duplicate filter name: {f.name!r}")
        self._filters.append(f)

    def add_many(self, filters: Sequence[Filter]) -> None:
        """Register several filters in order."""
        for f in filters:
            self.add(f)

    def remove(self, name: str) -> None:
        """Unregister a filter by name (no-op if absent)."""
        self._filters = [f for f in self._filters if f.name != name]

    # ---------------------------------------------------------------- execution

    def _stage_filters(self, stage: str) -> List[Filter]:
        return [f for f in self._filters if f.stage == stage]

    def _run(self, stage: str, entries: Sequence[str], provider: Optional[Callable]) -> Tuple[List[str], List[dict]]:
        """Shared execution for universe / candidate stages.

        Returns ``(kept, rejected)`` where each rejected entry is
        ``{"ticker", "filter", "reason"}``. When disabled, or when no filters
        are registered for the stage, this is an identity pass-through.
        """
        if not self._enabled:
            return list(entries), []

        stage_filters = self._stage_filters(stage)
        if not stage_filters:
            return list(entries), []

        kept: List[str] = []
        rejected: List[dict] = []

        for entry in entries:
            if callable(provider):
                ctx = provider(entry)
                if not isinstance(ctx, FilterContext):
                    ctx = FilterContext(ticker=entry)
            else:
                ctx = FilterContext(ticker=entry)

            for f in stage_filters:
                res = f.check(ctx)
                if not res.passed:
                    rejected.append({
                        "ticker": ctx.ticker,
                        "filter": f.name,
                        "reason": res.reason,
                    })
                    break
            else:
                kept.append(entry)

        return kept, rejected

    def filter_universe(
        self,
        tickers: Sequence[str],
        provider: Optional[Callable] = None,
    ) -> Tuple[List[str], List[dict]]:
        """Stage-A: filter the ticker universe BEFORE RS ranking."""
        return self._run(STAGE_UNIVERSE, list(tickers), provider)

    def filter_candidates(
        self,
        candidates: Sequence[str],
        provider: Optional[Callable] = None,
    ) -> Tuple[List[str], List[dict]]:
        """Stage-B: filter technically-qualified candidates."""
        return self._run(STAGE_CANDIDATE, list(candidates), provider)


__all__ = [
    "STAGE_UNIVERSE",
    "STAGE_CANDIDATE",
    "FilterContext",
    "FilterResult",
    "Filter",
    "LiquidityFilter",
    "MarketCapFilter",
    "FilterEngine",
]
