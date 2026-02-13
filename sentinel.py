#!/usr/bin/env python3
“””
sentinel.py — SENTINEL PRO メインスキャナー

使い方:
python sentinel.py

設定:
環境変数または GitHub Secrets で上書き可能。
詳細は config.py / README.md を参照。
“””

import json
import time
from datetime import datetime
from pathlib import Path

from config import CONFIG, TICKERS
from engines.analysis import RSAnalyzer, VCPAnalyzer, StrategyValidator
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine
from engines.notify import calculate_position, send_line

RESULTS_DIR = Path(”./results”)
RESULTS_DIR.mkdir(exist_ok=True)

# ==============================================================================

# 🚀 メインスキャン

# ==============================================================================

def run() -> None:
start = time.time()
today = datetime.now().strftime(”%Y-%m-%d %H:%M”)

```
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
    df     = item["df"]
    rs     = item["rs_rating"]

    vcp = VCPAnalyzer.calculate(df)
    pf  = StrategyValidator.run(df)

    # ── 基本フィルタ ──────────────────────────────────────────
    if rs  < CONFIG["MIN_RS_RATING"]     \
    or vcp["score"] < CONFIG["MIN_VCP_SCORE"] \
    or pf  < CONFIG["MIN_PROFIT_FACTOR"]:
        continue

    price  = float(df["Close"].iloc[-1])
    pivot  = float(df["High"].iloc[-20:].max())
    entry  = pivot * 1.002
    stop   = entry - vcp["atr"] * CONFIG["STOP_LOSS_ATR"]
    target = entry + (entry - stop) * CONFIG["TARGET_R_MULTIPLE"]
    shares = calculate_position(entry, stop, usd_jpy)

    if shares <= 0:  # 資金内で買えない銘柄は除外
        continue

    # ── ステータス判定 ────────────────────────────────────────
    dist_pct = (price - pivot) / pivot
    if   -0.05 <= dist_pct <= 0.03: status = "ACTION"
    elif dist_pct < -0.05:          status = "WAIT"
    else:                           status = "EXTENDED"

    # ── ファンダメンタル取得 ──────────────────────────────────
    fund    = FundamentalEngine.get(ticker)
    insider = InsiderEngine.get(ticker)

    analyst_upside = fund.get("analyst_upside")
    insider_alert  = insider.get("alert", False)

    qualified.append({
        # テクニカル
        "ticker":  ticker,
        "status":  status,
        "price":   round(price, 2),
        "entry":   round(entry, 2),
        "stop":    round(stop,  2),
        "target":  round(target, 2),
        "shares":  int(shares),
        "vcp":     vcp,
        "rs":      int(rs),
        "pf":      float(pf),
        "sector":  DataEngine.get_sector(ticker),
        # ファンダメンタル
        "analyst_target":  fund.get("analyst_target"),
        "analyst_upside":  analyst_upside,
        "analyst_count":   fund.get("analyst_count"),
        "recommendation":  fund.get("recommendation"),
        "short_ratio":     fund.get("short_ratio"),
        "short_pct":       fund.get("short_pct"),
        "insider_pct":     fund.get("insider_pct"),
        "institution_pct": fund.get("institution_pct"),
        "pe_forward":      fund.get("pe_forward"),
        "revenue_growth":  fund.get("revenue_growth"),
        "insider_alert":   insider_alert,
        "insider_detail":  insider,
    })

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
    "date":            date_str,
    "timestamp":       datetime.now().isoformat(),
    "runtime":         f"{round(time.time() - start, 2)}s",
    "usd_jpy":         usd_jpy,
    "scan_count":      len(TICKERS),
    "qualified_count": len(qualified),
    "selected_count":  len(selected),
    "selected":        selected,
    "watchlist_wait":  [q for q in qualified if q["status"] == "WAIT"][:8],
    "qualified_full":  qualified,
}

out_path = RESULTS_DIR / f"{date_str}.json"
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(run_info, f, ensure_ascii=False, indent=2, default=str)

print(f"\n✅ Results → {out_path}")
print(f"   Qualified: {len(qualified)}  |  Action: {len(selected)}")
print(f"   Runtime: {run_info['runtime']}")

# ── LINE 通知 ─────────────────────────────────────────────────────
_notify(run_info, usd_jpy)
```

def _notify(run_info: dict, usd_jpy: float) -> None:
“”“LINE 通知メッセージを構築して送信。”””
date_str  = run_info[“date”]
selected  = run_info[“selected”]
waits     = run_info[“watchlist_wait”]

```
lines = [
    f"🛡️  SENTINEL PRO  {date_str}",
    f"¥{usd_jpy}  |  Scan: {run_info['scan_count']}  |  Action: {len(selected)}",
    "─" * 20,
]

if not selected:
    lines.append("⚠️  No actionable setups today.")
else:
    for s in selected:
        sigs       = ", ".join(s["vcp"]["signals"]) or "—"
        upside_str = f"  Analyst: {s['analyst_upside']:+.1f}%" if s.get("analyst_upside") else ""
        alert_str  = "  ⚠️ INSIDER SELL" if s.get("insider_alert") else ""
        lines += [
            f"\n💎 {s['ticker']}  [RS{s['rs']} VCP{s['vcp']['score']} PF{s['pf']:.1f}]",
            f"   {s['shares']}株  Entry ${s['entry']}  Stop ${s['stop']}  Target ${s['target']}",
            f"   {sigs}{upside_str}{alert_str}",
            "─" * 15,
        ]

if waits:
    lines.append("\n📋 Watchlist (WAIT)")
    for w in waits:
        lines.append(f"  • {w['ticker']}  RS{w['rs']} VCP{w['vcp']['score']}")

msg = "\n".join(lines)
print("\n" + msg)
send_line(msg)
```

if **name** == “**main**”:
run()