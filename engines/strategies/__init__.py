"""engines.strategies — Strategy layer for SENTINEL PRO.

Phase 3 strategies live here. Each strategy composes indicators
(RSIndicator, VCPIndicator, SentinelEfficiencyAnalyzer, RelativeStrengthRanking)
to produce trading decisions.

Currently available:
- Strategy (ABC) — base class for all strategies
- RelativeStrengthRanking — RS vs SPY/sector benchmark indicator
- VCPBreakoutStrategy — VCP + contraction pivot + breakout confirmation
- MinerviniTrendTemplate — Mark Minervini's 8-point trend template
"""
from engines.strategies.base import Strategy
from engines.strategies.minervini_template import MinerviniTrendTemplate
from engines.strategies.rs_ranking import RelativeStrengthRanking
from engines.strategies.vcp_breakout import VCPBreakoutStrategy

__all__ = ["Strategy", "RelativeStrengthRanking", "VCPBreakoutStrategy", "MinerviniTrendTemplate"]
