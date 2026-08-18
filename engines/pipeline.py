"""Integrated Pipeline Orchestrator for SENTINEL PRO (Phase 6.2).

Replaces the hardcoded procedural flow in ``sentinel.py`` with a configurable,
modular, testable pipeline.  When ``pipeline.enabled`` is ``False`` (default),
this module is a pure no-op and sentinel.py continues its existing behavior.

When enabled, the pipeline takes over the full scan workflow:
  Universe → Filter → Data → RS Ranking → VCP → Strategies →
  Candidate Filter → Fundamentals → Earnings → Patterns →
  Regime → Risk → Sort → Sector Diversification → News → Output

This module is additive: ``sentinel.py`` is NOT modified in this slice.
"""
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Container for pipeline execution results."""
    date: str
    timestamp: str
    runtime: str
    usd_jpy: float
    scan_count: int
    qualified_count: int
    selected_count: int
    selected: List[Dict]
    watchlist_wait: List[Dict]
    qualified_full: List[Dict]
    regime: Optional[Dict] = None
    portfolio_risk: Optional[Dict] = None

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "date": self.date,
            "timestamp": self.timestamp,
            "runtime": self.runtime,
            "usd_jpy": self.usd_jpy,
            "scan_count": self.scan_count,
            "qualified_count": self.qualified_count,
            "selected_count": self.selected_count,
            "selected": self.selected,
            "watchlist_wait": self.watchlist_wait,
            "qualified_full": self.qualified_full,
        }
        if self.regime is not None:
            d["regime"] = self.regime
        if self.portfolio_risk is not None:
            d["portfolio_risk"] = self.portfolio_risk
        return d


class Pipeline:
    """Configurable scan pipeline orchestrator.

    Composes all SENTINEL PRO engines into a single executable workflow.
    Reads behavior from ``PipelineConfig`` (config.yaml ``pipeline:`` section).

    Usage::

        from engines.pipeline import Pipeline
        result = Pipeline.from_config().execute()
    """

    def __init__(
        self,
        config=None,
        universe: Optional[List[str]] = None,
        data_provider: Optional[Callable] = None,
        sector_provider: Optional[Callable] = None,
        currency_provider: Optional[Callable] = None,
        fundamental_provider: Optional[Callable] = None,
        insider_provider: Optional[Callable] = None,
        news_provider: Optional[Callable] = None,
        output_dir: Optional[Path] = None,
        line_sender: Optional[Callable] = None,
    ):
        self._config = config
        self._universe = universe
        self._data_provider = data_provider
        self._sector_provider = sector_provider
        self._currency_provider = currency_provider
        self._fundamental_provider = fundamental_provider
        self._insider_provider = insider_provider
        self._news_provider = news_provider
        self._output_dir = output_dir or Path("./results")
        self._line_sender = line_sender

    @classmethod
    def from_config(cls, config=None, **kwargs) -> "Pipeline":
        """Build pipeline from config.yaml (singleton or explicit)."""
        if config is None:
            try:
                from sentinel.config import get_config
                config = get_config()
            except Exception:
                config = None
        return cls(config=config, **kwargs)

    def _get_cfg(self, attr: str, default=None):
        """Safely read config attribute."""
        if self._config is None:
            return default
        return getattr(self._config, attr, default)

    def execute(self) -> PipelineResult:
        """Run the full scan pipeline. Returns PipelineResult."""
        start = time.time()
        today = datetime.now().strftime("%Y-%m-%d %H:%M")

        # ── Resolve dependencies ──
        DataEngine, CurrencyEngine, RSAnalyzer, VCPAnalyzer, StrategyValidator = self._import_engines()
        FundamentalEngine, InsiderEngine = self._import_fundamental()
        EarningsCalendarEngine = self._import_earnings()
        NewsEngine = self._import_news()
        FilterEngine = self._import_filters()
        calculate_position, send_line = self._import_notify()

        # ── Universe ──
        tickers = self._universe or self._load_universe()
        print("=" * 60)
        print("🛡️  SENTINEL PRO v5.1 (Pipeline)")
        print(f"   {today}  |  Universe: {len(tickers)} tickers")
        print("=" * 60)

        usd_jpy = self._resolve_currency(CurrencyEngine)
        print(f"USD/JPY: {usd_jpy}")

        # ── Universe-stage filtering ──
        filter_engine = self._build_filter_engine(FilterEngine)
        if filter_engine and filter_engine.enabled:
            provider = self._build_filter_provider(DataEngine, FundamentalEngine)
            tickers, universe_rejections = filter_engine.filter_universe(tickers, provider)
            print(f"         {len(tickers)} tickers after universe filter.")

        # ── Phase 1: RS raw scores ──
        print(f"[Phase 1] Scanning {len(tickers)} tickers...")
        raw_list = self._compute_rs_scores(tickers, DataEngine, RSAnalyzer)

        # ── Phase 2: RS percentiles ──
        raw_list = RSAnalyzer.assign_percentiles(raw_list)
        print(f"         {len(raw_list)} tickers with valid RS scores.")

        # ── Phase 2.5: Technical + Fundamental validation ──
        print(f"[Phase 2] Technical + Fundamental validation...")
        qualified = self._validate_candidates(
            raw_list, DataEngine, VCPAnalyzer, StrategyValidator,
            FundamentalEngine, InsiderEngine, calculate_position, usd_jpy,
        )

        # ── Phase 3.5: Earnings warnings ──
        qualified = self._earnings_check(qualified, EarningsCalendarEngine)

        # ── Phase 3.6: Pattern analysis ──
        qualified = self._pattern_analysis(qualified, DataEngine)

        # ── Phase 3.7: Market regime ──
        regime_info = self._regime_analysis(DataEngine)

        # ── Phase 3.8: Portfolio risk ──
        portfolio_risk_info = self._portfolio_risk(qualified, usd_jpy)

        # ── Phase 4: Sort ──
        qualified = self._sort_candidates(qualified)

        # ── Phase 5: Sector diversification ──
        selected = self._sector_diversify(qualified)

        # ── Phase 6: News fetch ──
        print(f"[Phase 3] Fetching news for top picks...")
        self._fetch_news(selected, qualified, NewsEngine)

        # ── Assemble results ──
        runtime = f"{round(time.time() - start, 2)}s"
        result = PipelineResult(
            date=datetime.now().strftime("%Y-%m-%d"),
            timestamp=datetime.now().isoformat(),
            runtime=runtime,
            usd_jpy=usd_jpy,
            scan_count=len(tickers),
            qualified_count=len(qualified),
            selected_count=len(selected),
            selected=selected,
            watchlist_wait=[q for q in qualified if q["status"] == "WAIT"][:8],
            qualified_full=qualified,
            regime=regime_info.to_dict() if regime_info else None,
            portfolio_risk=portfolio_risk_info.to_dict() if portfolio_risk_info else None,
        )

        # ── Output ──
        self._save_results(result)
        print(f"\n✅ Results → {self._output_dir / result.date}.json")
        print(f"   Qualified: {len(qualified)}  |  Action: {len(selected)}")
        print(f"   Runtime: {runtime}")

        self._notify(result, usd_jpy)

        return result

    # ───────────────────────────────────────────────────────────────────
    # Engine imports (lazy)
    # ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _import_engines():
        from engines.data import DataEngine, CurrencyEngine
        from engines.analysis import RSAnalyzer, VCPAnalyzer, StrategyValidator
        return DataEngine, CurrencyEngine, RSAnalyzer, VCPAnalyzer, StrategyValidator

    @staticmethod
    def _import_fundamental():
        from engines.fundamental import FundamentalEngine, InsiderEngine
        return FundamentalEngine, InsiderEngine

    @staticmethod
    def _import_earnings():
        from engines.earnings import EarningsCalendarEngine
        return EarningsCalendarEngine

    @staticmethod
    def _import_news():
        from engines.news import NewsEngine
        return NewsEngine

    @staticmethod
    def _import_filters():
        from engines.filters import FilterEngine
        return FilterEngine

    @staticmethod
    def _import_notify():
        from engines.notify import calculate_position, send_line
        return calculate_position, send_line

    # ───────────────────────────────────────────────────────────────────
    # Universe + Data
    # ───────────────────────────────────────────────────────────────────

    def _load_universe(self) -> List[str]:
        """Load ticker universe from config."""
        try:
            from config import TICKERS
            return list(TICKERS)
        except ImportError:
            return []

    def _resolve_currency(self, CurrencyEngine) -> float:
        if self._currency_provider:
            return self._currency_provider()
        return CurrencyEngine.get_usd_jpy()

    def _build_filter_engine(self, FilterEngine) -> Optional[Any]:
        """Build FilterEngine from config."""
        filter_cfg = self._get_cfg("filters")
        if filter_cfg is None:
            return None
        return FilterEngine.from_config(self._config)

    def _build_filter_provider(self, DataEngine, FundamentalEngine):
        """Build a provider callable for FilterEngine."""
        def provider(ticker: str):
            from engines.filters import FilterContext
            df = DataEngine.get_data(ticker)
            profile = FundamentalEngine.get(ticker)
            sector = DataEngine.get_sector(ticker)
            return FilterContext(
                ticker=ticker, df=df, profile=profile, sector=sector,
            )
        return provider

    def _compute_rs_scores(self, tickers, DataEngine, RSAnalyzer) -> List[Dict]:
        raw_list = []
        for ticker in tickers:
            df = self._data_provider(ticker) if self._data_provider else DataEngine.get_data(ticker)
            if df is None:
                continue
            raw_rs = RSAnalyzer.get_raw_score(df)
            if raw_rs == -999.0:
                continue
            raw_list.append({"ticker": ticker, "df": df, "raw_rs": raw_rs})
        return raw_list

    # ───────────────────────────────────────────────────────────────────
    # Validation
    # ───────────────────────────────────────────────────────────────────

    def _validate_candidates(
        self, raw_list, DataEngine, VCPAnalyzer, StrategyValidator,
        FundamentalEngine, InsiderEngine, calculate_position, usd_jpy,
    ) -> List[Dict]:
        scan_cfg = self._get_cfg("scan", {})
        min_rs = getattr(scan_cfg, "min_rs_rating", 70)
        min_vcp = getattr(scan_cfg, "min_vcp_score", 55)
        min_pf = getattr(scan_cfg, "min_profit_factor", 1.1)
        stop_atr = self._get_cfg("exit", None)
        stop_mult = getattr(stop_atr, "stop_loss_atr", 2.0) if stop_atr else 2.0
        target_mult = getattr(stop_atr, "target_r_multiple", 3.0) if stop_atr else 3.0
        capital_cfg = self._get_cfg("capital", None)
        max_same_sector = getattr(capital_cfg, "max_same_sector", 2) if capital_cfg else 2
        max_positions = getattr(capital_cfg, "max_positions", 20) if capital_cfg else 20

        qualified = []
        for item in raw_list:
            ticker = item["ticker"]
            df = item["df"]
            rs = item.get("rs_rating", 0)

            vcp = VCPAnalyzer.calculate(df)
            pf = StrategyValidator.run(df)

            if (rs < min_rs or vcp["score"] < min_vcp or pf < min_pf):
                continue

            price = float(df["Close"].iloc[-1])
            pivot = float(df["High"].iloc[-20:].max())
            entry = pivot * 1.002
            stop = entry - vcp["atr"] * stop_mult
            target = entry + (entry - stop) * target_mult
            shares = calculate_position(entry, stop, usd_jpy)

            if shares <= 0:
                continue

            dist_pct = (price - pivot) / pivot
            if -0.05 <= dist_pct <= 0.03:
                status = "ACTION"
            elif dist_pct < -0.05:
                status = "WAIT"
            else:
                status = "EXTENDED"

            fund = FundamentalEngine.get(ticker)
            insider = InsiderEngine.get(ticker)
            analyst_upside = fund.get("analyst_upside")
            insider_alert = insider.get("alert", False)

            qualified.append({
                "ticker": ticker,
                "status": status,
                "price": round(price, 2),
                "entry": round(entry, 2),
                "stop": round(stop, 2),
                "target": round(target, 2),
                "shares": int(shares),
                "vcp": vcp,
                "rs": int(rs),
                "pf": float(pf),
                "sector": DataEngine.get_sector(ticker),
                "analyst_target": fund.get("analyst_target"),
                "analyst_upside": analyst_upside,
                "analyst_count": fund.get("analyst_count"),
                "recommendation": fund.get("recommendation"),
                "short_ratio": fund.get("short_ratio"),
                "short_pct": fund.get("short_pct"),
                "insider_pct": fund.get("insider_pct"),
                "institution_pct": fund.get("institution_pct"),
                "pe_forward": fund.get("pe_forward"),
                "revenue_growth": fund.get("revenue_growth"),
                "insider_alert": insider_alert,
                "insider_detail": insider,
            })

        return qualified

    # ───────────────────────────────────────────────────────────────────
    # Enrichment phases
    # ───────────────────────────────────────────────────────────────────

    def _earnings_check(self, qualified, EarningsCalendarEngine) -> List[Dict]:
        if not qualified:
            return qualified
        qualified_tickers = [q["ticker"] for q in qualified]
        try:
            earnings_map = EarningsCalendarEngine.build_earnings_map(
                qualified_tickers, days_ahead=14
            )
        except Exception:
            earnings_map = {}

        for q in qualified:
            ed = earnings_map.get(q["ticker"].upper())
            if ed is not None:
                from datetime import datetime as _dt
                if isinstance(ed, list):
                    ed = ed[0] if ed else None
                if isinstance(ed, str):
                    try:
                        ed = _dt.strptime(ed, "%Y-%m-%d")
                    except ValueError:
                        try:
                            ed = _dt.strptime(ed, "%Y-%m-%d %H:%M:%S")
                        except ValueError:
                            ed = None
                if ed is not None:
                    try:
                        days_until = (ed.date() - _dt.now().date()).days
                    except AttributeError:
                        days_until = (ed - _dt.now().date()).days
                    if 0 <= days_until <= 7:
                        q["earnings_warning"] = f"Earnings in {days_until}d"
                    elif days_until == 0:
                        q["earnings_warning"] = "Earnings TODAY"
        return qualified

    def _pattern_analysis(self, qualified, DataEngine) -> List[Dict]:
        if not qualified:
            return qualified

        try:
            pcfg = getattr(self._config, "patterns", None) if self._config else None
            pat_enabled = getattr(pcfg, "enabled", False) if pcfg else False
        except Exception:
            pat_enabled = False

        if not pat_enabled or pcfg is None:
            return qualified

        from engines.patterns import FibonacciEngine, CandlestickEngine, BBSqueezeEngine

        for q in qualified:
            df = DataEngine.get_data(q["ticker"])
            if df is None or df.empty:
                continue

            fib_cfg = getattr(pcfg, "fibonacci", None)
            cs_cfg = getattr(pcfg, "candlestick", None)
            bb_cfg = getattr(pcfg, "bb_squeeze", None)

            fib_lb = getattr(fib_cfg, "lookback", 60) if fib_cfg else 60
            fib = FibonacciEngine.analyze(df, lookback=fib_lb, current_price=q["price"])
            if fib["nearest_level"] is not None:
                q["fib_nearest"] = fib["nearest_level"]
                q["fib_distance_pct"] = fib["nearest_distance_pct"]
                q["fib_support"] = fib["support_levels"]
                q["fib_resistance"] = fib["resistance_levels"]

            cs_lb = getattr(cs_cfg, "lookback", 5) if cs_cfg else 5
            cs_summary = CandlestickEngine.summary(df, lookback=cs_lb)
            if cs_summary["total"] > 0:
                q["candle_bias"] = cs_summary["bias"]
                q["candle_patterns"] = cs_summary["patterns"]

            bb_period = getattr(bb_cfg, "period", 20) if bb_cfg else 20
            bb_std = getattr(bb_cfg, "std_dev", 2.0) if bb_cfg else 2.0
            bb = BBSqueezeEngine.analyze(df, bb_period=bb_period, bb_std=bb_std)
            if bb["status"] != "insufficient_data":
                q["bb_squeeze"] = bb["squeezing"]
                q["bb_squeeze_status"] = bb["status"]
                if bb["squeezing"]:
                    q["bb_squeeze_confirmed"] = bb.get("squeeze_confirmed", False)

        return qualified

    def _regime_analysis(self, DataEngine):
        try:
            rcfg = getattr(self._config, "regime", None) if self._config else None
            regime_enabled = getattr(rcfg, "enabled", False) if rcfg else False
        except Exception:
            regime_enabled = False

        if not regime_enabled or rcfg is None:
            return None

        from engines.regime import MarketRegimeEngine

        benchmark = getattr(rcfg, "benchmark", "SPY") or "SPY"
        bench_df = DataEngine.get_data(benchmark)
        if bench_df is None or bench_df.empty:
            return None

        weights = None
        wc = getattr(rcfg, "weights", None)
        if wc is not None:
            weights = {
                "trend": wc.trend, "breadth": wc.breadth,
                "volatility": wc.volatility, "momentum": wc.momentum,
            }

        try:
            return MarketRegimeEngine.analyze(bench_df, weights=weights)
        except Exception:
            return None

    def _portfolio_risk(self, qualified, usd_jpy):
        try:
            rcfg = getattr(self._config, "risk", None) if self._config else None
            risk_enabled = getattr(rcfg, "enabled", False) if rcfg else False
        except Exception:
            risk_enabled = False

        if not risk_enabled or not qualified:
            return None

        from engines.risk import PortfolioRisk

        positions = []
        for q in qualified:
            positions.append({
                "ticker": q["ticker"],
                "shares": q["shares"],
                "sector": q.get("sector", "Unknown"),
                "stop_distance": abs(q["entry"] - q["stop"]),
                "risk_amount": q["shares"] * abs(q["entry"] - q["stop"]),
            })

        capital_cfg = self._get_cfg("capital", None)
        capital_jpy = getattr(capital_cfg, "jpy", 1_000_000) if capital_cfg else 1_000_000
        capital_usd = capital_jpy / usd_jpy if usd_jpy > 0 else capital_jpy

        risk_cfg = getattr(rcfg, "portfolio", None) if rcfg else None
        max_heat = getattr(risk_cfg, "max_heat_pct", 0.06) if risk_cfg else 0.06
        max_sec = getattr(risk_cfg, "max_sector_pct", 0.40) if risk_cfg else 0.40

        try:
            return PortfolioRisk.analyze(positions, capital_usd, max_heat=max_heat, max_sector_pct=max_sec)
        except Exception:
            return None

    # ───────────────────────────────────────────────────────────────────
    # Sort + Diversify + News + Output
    # ───────────────────────────────────────────────────────────────────

    @staticmethod
    def _sort_candidates(qualified: List[Dict]) -> List[Dict]:
        status_rank = {"ACTION": 3, "WAIT": 2, "EXTENDED": 1}
        qualified.sort(
            key=lambda x: (
                status_rank.get(x["status"], 0),
                x["rs"] + x["vcp"]["score"] + x["pf"] * 10,
            ),
            reverse=True,
        )
        return qualified

    def _sector_diversify(self, qualified: List[Dict]) -> List[Dict]:
        capital_cfg = self._get_cfg("capital", None)
        max_same_sector = getattr(capital_cfg, "max_same_sector", 2) if capital_cfg else 2
        max_positions = getattr(capital_cfg, "max_positions", 20) if capital_cfg else 20

        selected = []
        sector_counts: Dict[str, int] = {}

        for q in qualified:
            if q["status"] != "ACTION":
                continue
            sec = q["sector"]
            if sector_counts.get(sec, 0) >= max_same_sector and sec != "Unknown":
                continue
            selected.append(q)
            sector_counts[sec] = sector_counts.get(sec, 0) + 1
            if len(selected) >= max_positions:
                break

        return selected

    def _fetch_news(self, selected, qualified, NewsEngine):
        top_picks = selected + [q for q in qualified if q["status"] == "WAIT"][:5]
        for s in top_picks:
            s["news"] = self._news_provider(s["ticker"]) if self._news_provider else NewsEngine.get(s["ticker"])

    def _save_results(self, result: PipelineResult):
        self._output_dir.mkdir(parents=True, exist_ok=True)
        out_path = self._output_dir / f"{result.date}.json"
        import json
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, ensure_ascii=False, indent=2, default=str)

    def _notify(self, result: PipelineResult, usd_jpy: float):
        send_line = self._line_sender
        if send_line is None:
            try:
                from engines.notify import send_line as _sl
                send_line = _sl
            except Exception:
                return

        lines = [
            f"🛡️  SENTINEL PRO  {result.date}",
            f"¥{usd_jpy}  |  Scan: {result.scan_count}  |  Action: {result.selected_count}",
            "─" * 20,
        ]

        regime = result.regime
        if regime:
            lines.append(f"📊 Market Regime: {regime['regime'].upper()} ({regime['score']:+d})")

        prisk = result.portfolio_risk
        if prisk:
            heat = prisk["total_heat"] * 100
            lines.append(f"⚠️ Portfolio Risk: {prisk['risk_level'].upper()} (heat: {heat:.1f}%)")

        if not result.selected:
            lines.append("⚠️  No actionable setups today.")
        else:
            for s in result.selected:
                sigs = ", ".join(s["vcp"]["signals"]) or "—"
                upside_str = f"  Analyst: {s['analyst_upside']:+.1f}%" if s.get("analyst_upside") else ""
                alert_str = "  ⚠️ INSIDER SELL" if s.get("insider_alert") else ""
                earn_str = f"  📅 {s['earnings_warning']}" if s.get("earnings_warning") else ""
                squeeze_str = "  💥 BB SQUEEZE" if s.get("bb_squeeze") else ""
                candle_str = f"  🕯️ {s['candle_bias']}" if s.get("candle_bias") and s["candle_bias"] != "neutral" else ""
                lines += [
                    f"\n💎 {s['ticker']}  [RS{s['rs']} VCP{s['vcp']['score']} PF{s['pf']:.1f}]",
                    f"   {s['shares']}株  Entry ${s['entry']}  Stop ${s['stop']}  Target ${s['target']}",
                    f"   {sigs}{upside_str}{alert_str}{earn_str}{squeeze_str}{candle_str}",
                    "─" * 15,
                ]

        if result.watchlist_wait:
            lines.append("\n📋 Watchlist (WAIT)")
            for w in result.watchlist_wait:
                lines.append(f"  • {w['ticker']}  RS{w['rs']} VCP{w['vcp']['score']}")

        msg = "\n".join(lines)
        print("\n" + msg)
        send_line(msg)


__all__ = ["Pipeline", "PipelineResult"]
