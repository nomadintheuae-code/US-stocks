#!/usr/bin/env python3
import json
import time
from datetime import datetime
from pathlib import Path

from config import CONFIG, TICKERS
from engines.analysis import RSAnalyzer, VCPAnalyzer, StrategyValidator
from engines.data import CurrencyEngine, DataEngine
from engines.earnings import EarningsCalendarEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine
from engines.patterns import FibonacciEngine, CandlestickEngine, BBSqueezeEngine
from engines.regime import MarketRegimeEngine
from engines.risk import PositionSizer, PortfolioRisk, StopManager
from engines.notify import calculate_position, send_line

RESULTS_DIR = Path("./results")
RESULTS_DIR.mkdir(exist_ok=True)

# ==============================================================================
# 🚀 メインスキャン
# ==============================================================================

def run() -> None:
    start = time.time()
    today = datetime.now().strftime("%Y-%m-%d %H:%M")

    print("=" * 60)
    print("🛡️  SENTINEL PRO v5.0")
    print(f"   {today}  |  Universe: {len(TICKERS)} tickers")
    print(f"   Capital: ¥{CONFIG['CAPITAL_JPY']:,}")
    print("=" * 60)

    usd_jpy = CurrencyEngine.get_usd_jpy()
    print(f"USD/JPY: {usd_jpy}")

    # ── Phase 1: 全銘柄の RS 生スコアを算出 ─────────────────────────
    print(f"\n[Phase 1] Scanning {len(TICKERS)} tickers...")
    raw_list: list[dict] = []

    for ticker in TICKERS:
        df = DataEngine.get_data(ticker)
        if df is None:
            continue
        raw_rs = RSAnalyzer.get_raw_score(df)
        if raw_rs == -999.0:
            continue
        raw_list.append({"ticker": ticker, "df": df, "raw_rs": raw_rs})

    # ── Phase 2: RS パーセンタイル割り当て ──────────────────────────
    raw_list = RSAnalyzer.assign_percentiles(raw_list)
    print(f"         {len(raw_list)} tickers with valid RS scores.")

    # ── Phase 3: VCP + バックテスト + ファンダメンタルフィルタ ───────
    print(f"[Phase 2] Technical + Fundamental validation...")
    qualified: list[dict] = []

    for item in raw_list:
        ticker = item["ticker"]
        df = item["df"]
        # 注意: assign_percentiles() で "rs_rating" キーが追加されている前提
        rs = item.get("rs_rating", 0)

        vcp = VCPAnalyzer.calculate(df)
        pf = StrategyValidator.run(df)

        # ── 基本フィルタ ──────────────────────────────────────────
        if (rs < CONFIG["MIN_RS_RATING"] or
            vcp["score"] < CONFIG["MIN_VCP_SCORE"] or
            pf < CONFIG["MIN_PROFIT_FACTOR"]):
            continue

        price = float(df["Close"].iloc[-1])
        pivot = float(df["High"].iloc[-20:].max())
        entry = pivot * 1.002
        stop = entry - vcp["atr"] * CONFIG["STOP_LOSS_ATR"]
        target = entry + (entry - stop) * CONFIG["TARGET_R_MULTIPLE"]
        shares = calculate_position(entry, stop, usd_jpy)

        if shares <= 0:  # 資金内で買えない銘柄は除外
            continue

        # ── ステータス判定 ────────────────────────────────────────
        dist_pct = (price - pivot) / pivot
        if -0.05 <= dist_pct <= 0.03:
            status = "ACTION"
        elif dist_pct < -0.05:
            status = "WAIT"
        else:
            status = "EXTENDED"

        # ── ファンダメンタル取得 ──────────────────────────────────
        fund = FundamentalEngine.get(ticker)
        insider = InsiderEngine.get(ticker)

        analyst_upside = fund.get("analyst_upside")
        insider_alert = insider.get("alert", False)

        qualified.append({
            # テクニカル
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
            # ファンダメンタル
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

    # ── Phase 3.5: カレンダー チェック ────────────────────────────────
    if qualified:
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

    # ── Phase 3.6: パターン分析 ──────────────────────────────────────
    if qualified:
        try:
            from sentinel.config import get_config
            _scfg = get_config()
            _pcfg = getattr(_scfg, "patterns", None)
            _pat_enabled = getattr(_pcfg, "enabled", False) if _pcfg else False
        except Exception:
            _pat_enabled = False

        if _pat_enabled and _pcfg is not None:
            for q in qualified:
                ticker = q["ticker"]
                df = DataEngine.get_data(ticker)
                if df is None or df.empty:
                    continue

                fib_cfg = getattr(_pcfg, "fibonacci", None)
                cs_cfg = getattr(_pcfg, "candlestick", None)
                bb_cfg = getattr(_pcfg, "bb_squeeze", None)

                # Fibonacci
                fib_lb = getattr(fib_cfg, "lookback", 60) if fib_cfg else 60
                fib = FibonacciEngine.analyze(df, lookback=fib_lb, current_price=q["price"])
                if fib["nearest_level"] is not None:
                    q["fib_nearest"] = fib["nearest_level"]
                    q["fib_distance_pct"] = fib["nearest_distance_pct"]
                    q["fib_support"] = fib["support_levels"]
                    q["fib_resistance"] = fib["resistance_levels"]

                # Candlestick
                cs_lb = getattr(cs_cfg, "lookback", 5) if cs_cfg else 5
                cs_summary = CandlestickEngine.summary(df, lookback=cs_lb)
                if cs_summary["total"] > 0:
                    q["candle_bias"] = cs_summary["bias"]
                    q["candle_patterns"] = cs_summary["patterns"]

                # BB Squeeze
                bb_period = getattr(bb_cfg, "period", 20) if bb_cfg else 20
                bb_std = getattr(bb_cfg, "std_dev", 2.0) if bb_cfg else 2.0
                bb_thresh = getattr(bb_cfg, "percentile_threshold", 20.0) if bb_cfg else 20.0
                bb = BBSqueezeEngine.analyze(df, bb_period=bb_period, bb_std=bb_std)
                if bb["status"] != "insufficient_data":
                    q["bb_squeeze"] = bb["squeezing"]
                    q["bb_squeeze_status"] = bb["status"]
                    if bb["squeezing"]:
                        q["bb_squeeze_confirmed"] = bb.get("squeeze_confirmed", False)

    # ── Phase 3.7: マーケット レジーム ────────────────────────────────
    regime_info = None
    try:
        from sentinel.config import get_config as _gcfg
        _rcfg = getattr(_gcfg(), "regime", None)
        _regime_enabled = getattr(_rcfg, "enabled", False) if _rcfg else False
    except Exception:
        _regime_enabled = False

    if _regime_enabled and _rcfg is not None:
        benchmark = getattr(_rcfg, "benchmark", "SPY") or "SPY"
        bench_df = DataEngine.get_data(benchmark)
        if bench_df is not None and not bench_df.empty:
            weights = None
            wc = getattr(_rcfg, "weights", None)
            if wc is not None:
                weights = {
                    "trend": wc.trend,
                    "breadth": wc.breadth,
                    "volatility": wc.volatility,
                    "momentum": wc.momentum,
                }
            try:
                regime_info = MarketRegimeEngine.analyze(bench_df, weights=weights)
            except Exception:
                regime_info = None

    # ── Phase 3.8: リスク分析 ────────────────────────────────────────
    portfolio_risk_info = None
    try:
        from sentinel.config import get_config as _gcfg2
        _rcfg2 = getattr(_gcfg2(), "risk", None)
        _risk_enabled = getattr(_rcfg2, "enabled", False) if _rcfg2 else False
    except Exception:
        _risk_enabled = False

    if _risk_enabled and qualified:
        try:
            risk_cfg = _rcfg2.portfolio if _rcfg2 else None
            max_heat = getattr(risk_cfg, "max_heat_pct", 0.06) if risk_cfg else 0.06
            max_sec = getattr(risk_cfg, "max_sector_pct", 0.40) if risk_cfg else 0.40

            # Build positions list for risk analysis
            _positions = []
            for q in qualified:
                _positions.append({
                    "ticker": q["ticker"],
                    "shares": q["shares"],
                    "sector": q.get("sector", "Unknown"),
                    "stop_distance": abs(q["entry"] - q["stop"]),
                    "risk_amount": q["shares"] * abs(q["entry"] - q["stop"]),
                })

            capital_usd = CONFIG["CAPITAL_JPY"] / usd_jpy if usd_jpy > 0 else CONFIG["CAPITAL_JPY"]
            portfolio_risk_info = PortfolioRisk.analyze(
                _positions, capital_usd,
                max_heat=max_heat, max_sector_pct=max_sec,
            )
        except Exception:
            portfolio_risk_info = None

    # ── Phase 4: ソート ──────────────────────────────────────────────
    # ACTION優先 → RS + VCP + PF×10 の総合スコアで降順
    status_rank = {"ACTION": 3, "WAIT": 2, "EXTENDED": 1}
    qualified.sort(
        key=lambda x: (
            status_rank.get(x["status"], 0),
            x["rs"] + x["vcp"]["score"] + x["pf"] * 10,
        ),
        reverse=True,
    )

    # ── Phase 5: セクター分散フィルタ ───────────────────────────────
    selected: list[dict] = []
    sector_counts: dict[str, int] = {}

    for q in qualified:
        if q["status"] != "ACTION":
            continue
        sec = q["sector"]
        if sector_counts.get(sec, 0) >= CONFIG["MAX_SAME_SECTOR"] and sec != "Unknown":
            continue
        selected.append(q)
        sector_counts[sec] = sector_counts.get(sec, 0) + 1
        if len(selected) >= CONFIG["MAX_POSITIONS"]:
            break

    # ── Phase 6: 上位銘柄のニュースfetch ────────────────────────────
    print(f"[Phase 3] Fetching news for top picks...")
    top_picks = selected + [q for q in qualified if q["status"] == "WAIT"][:5]
    for s in top_picks:
        s["news"] = NewsEngine.get(s["ticker"])

    # ── 結果保存 ─────────────────────────────────────────────────────
    date_str = datetime.now().strftime("%Y-%m-%d")
    run_info = {
        "date": date_str,
        "timestamp": datetime.now().isoformat(),
        "runtime": f"{round(time.time() - start, 2)}s",
        "usd_jpy": usd_jpy,
        "scan_count": len(TICKERS),
        "qualified_count": len(qualified),
        "selected_count": len(selected),
        "selected": selected,
        "watchlist_wait": [q for q in qualified if q["status"] == "WAIT"][:8],
        "qualified_full": qualified,
    }
    if regime_info is not None:
        run_info["regime"] = regime_info.to_dict()
    if portfolio_risk_info is not None:
        run_info["portfolio_risk"] = portfolio_risk_info.to_dict()

    out_path = RESULTS_DIR / f"{date_str}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(run_info, f, ensure_ascii=False, indent=2, default=str)

    print(f"\n✅ Results → {out_path}")
    print(f"   Qualified: {len(qualified)}  |  Action: {len(selected)}")
    print(f"   Runtime: {run_info['runtime']}")

    # ── LINE 通知 ─────────────────────────────────────────────────────
    _notify(run_info, usd_jpy)


def _notify(run_info: dict, usd_jpy: float) -> None:
    """LINE 通知メッセージを構築して送信。"""
    date_str = run_info["date"]
    selected = run_info["selected"]
    waits = run_info["watchlist_wait"]

    lines = [
        f"🛡️  SENTINEL PRO  {date_str}",
        f"¥{usd_jpy}  |  Scan: {run_info['scan_count']}  |  Action: {len(selected)}",
        "─" * 20,
    ]

    # Regime banner
    regime = run_info.get("regime")
    if regime:
        r_label = regime["regime"].upper()
        r_score = regime["score"]
        lines.append(f"📊 Market Regime: {r_label} ({r_score:+d})")

    # Portfolio risk banner
    prisk = run_info.get("portfolio_risk")
    if prisk:
        heat = prisk["total_heat"] * 100
        risk_lvl = prisk["risk_level"].upper()
        lines.append(f"⚠️ Portfolio Risk: {risk_lvl} (heat: {heat:.1f}%)")

    if not selected:
        lines.append("⚠️  No actionable setups today.")
    else:
        for s in selected:
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

    if waits:
        lines.append("\n📋 Watchlist (WAIT)")
        for w in waits:
            lines.append(f"  • {w['ticker']}  RS{w['rs']} VCP{w['vcp']['score']}")

    msg = "\n".join(lines)
    print("\n" + msg)
    send_line(msg)


if __name__ == "__main__":
    run()