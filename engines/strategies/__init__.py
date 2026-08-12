"""engines.strategies — Strategy layer for SENTINEL PRO.

Phase 3 strategies live here. Each strategy composes indicators
(RSIndicator, VCPIndicator, SentinelEfficiencyAnalyzer) to produce
trading decisions.

Currently available:
- Strategy (ABC) — base class for all strategies

Planned:
- VCPBreakoutStrategy — VCP + contraction pivot + breakout confirmation
- MinerviniTrendTemplate — Mark Minervini's 8 trend criteria
- RelativeStrengthRanking — RS vs SPY/sector benchmark (indicator)
"""
from engines.strategies.base import Strategy

__all__ = ["Strategy"]
