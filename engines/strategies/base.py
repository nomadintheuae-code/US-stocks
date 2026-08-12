"""Strategy abstract base class for the Phase 3 Strategies layer.

This module owns the canonical Strategy ABC. Concrete strategy subclasses
(VCPBreakoutStrategy, MinerviniTrendTemplate, etc.) will inherit from here.

Backward compatibility: engines.analysis re-exports this class so that
``from engines.analysis import Strategy`` continues to work.
"""
from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    """Abstract base class for trading strategies.

    Subclasses must implement:

    - ``calculate(df)`` — compute strategy analysis for a single ticker.
    - ``get_score()`` — return the strategy composite score.
    - ``get_signals()`` — return human-readable signal strings.
    - ``get_entry_stop_target()`` — return (entry, stop, target) prices.

    This class is deliberately minimal and does not change any existing
    behavior. All existing engine classes (VCPAnalyzer, VCPIndicator,
    RSAnalyzer, StrategyValidator) remain untouched.
    """

    @abstractmethod
    def calculate(self, df: pd.DataFrame) -> dict:
        """Compute strategy analysis for a single ticker.

        Returns a dict with at minimum: score, signals, atr.
        Subclasses may include additional keys specific to their strategy.
        """
        raise NotImplementedError

    @abstractmethod
    def get_score(self) -> int:
        """Return the strategy composite score."""
        raise NotImplementedError

    @abstractmethod
    def get_signals(self) -> list[str]:
        """Return list of human-readable signal strings."""
        raise NotImplementedError

    @abstractmethod
    def get_entry_stop_target(self) -> tuple[float, float, float]:
        """Return (entry_price, stop_price, target_price)."""
        raise NotImplementedError
