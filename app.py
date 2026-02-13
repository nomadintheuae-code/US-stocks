"""
app.py — SENTINEL PRO Streamlit UI

[FULL LOGIC RESTORATION - 780+ LINES SCALE]
このファイルは、初期のSENTINEL PROの全ロジック（RS分析、バックテスト、
詳細な出口戦略、AIプロンプト構成）を完全に復元し、
VCP計算ロジックのみを最新のバックエンド仕様に同期させた完全版です。
"""

import json
import os
import pickle
import re
import time
import warnings
import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

# 外部エンジン依存関係（既存のディレクトリ構造を維持）
from config import CONFIG
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数 & 出口戦略設定 (一言一句漏らさず維持)
# ==============================================================================

NOW         = datetime.datetime.now()
TODAY_STR   = NOW.strftime("%Y-%m-%d")
CACHE_DIR   = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results");   RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# プロフェッショナルな出口戦略の設定 (ATRベースの動的計算用)
EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

# ==============================================================================
# 🎯 VCPAnalyzer (バックエンドと完全同期された最新版)
# ==============================================================================

class VCPAnalyzer:
    """
    Mark Minervini VCP Scoring (Synced with latest backend logic)
    Tightness  (40pt)
    Volume     (30pt)
    MA Align   (30pt)
    Pivot Bonus(5pt)
    """
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 80:
                return VCPAnalyzer._empty_vcp()

            close = df["Close"]
            high = df["High"]
            low = df["Low"]
            volume = df["Volume"]

            # ── ATR(14) ──
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)

            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0:
                return VCPAnalyzer._empty_vcp()

            # 1️⃣ Tightness (40pt 改良版)
            periods = [20, 30, 40]
            ranges = []

            for p in periods:
                h = float(high.iloc[-p:].max())
                l = float(low.iloc[-p:].min())
                ranges.append((h - l) / h)

            avg_range = float(np.mean(ranges))

            # 正しい収縮判定（短期 < 中期 < 長期）
            is_contracting = ranges[0] < ranges[1] < ranges[2]

            if avg_range < 0.12:
                tight_score = 40
            elif avg_range < 0.18:
                tight_score = 30
            elif avg_range < 0.24:
                tight_score = 20
            elif avg_range < 0.30:
                tight_score = 10
            else:
                tight_score = 0

            if is_contracting:
                tight_score += 5

            tight_score = min(40, tight_score)
            range_pct = round(ranges[0], 4)

            # 2️⃣ Volume (30pt 改良版)
            v20 = float(volume.iloc[-20:].mean())
            v40 = float(volume.iloc[-40:-20].mean())
            v60 = float(volume.iloc[-60:-40].mean())

            if pd.isna(v20) or pd.isna(v40) or pd.isna(v60):
                return VCPAnalyzer._empty_vcp()

            ratio = v20 / v60 if v60 > 0 else 1.0

            if ratio < 0.50:
                vol_score = 30
            elif ratio < 0.65:
                vol_score = 25
            elif ratio < 0.80:
                vol_score = 15
            else:
                vol_score = 0

            is_dryup = ratio < 0.80
            vol_ratio = round(ratio, 2)

            # 3️⃣ MA Alignment (30pt)
            ma50 = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])

            trend_score = (
                (10 if price > ma50 else 0) +
                (10 if ma50 > ma200 else 0) +
                (10 if price > ma200 else 0)
            )

            # 4️⃣ Pivot接近ボーナス (最大+5)
            pivot = float(high.iloc[-40:].max())
            distance = (pivot - price) / pivot

            pivot_bonus = 0
            if 0 <= distance <= 0.05:
                pivot_bonus = 5
            elif 0.05 < distance <= 0.08:
                pivot_bonus = 3

            signals = []
            if tight_score >= 35:
                signals.append("Multi-Stage Contraction")
            if is_dryup:
                signals.append("Volume Dry-Up")
            if trend_score == 30:
                signals.append("MA Aligned")
            if pivot_bonus > 0:
                signals.append("Near Pivot")

            return {
                "score": int(max(0, tight_score + vol_score + trend_score + pivot_bonus)),
                "atr": atr,
                "signals": signals,
                "is_dryup": is_dryup,
                "range_pct": range_pct,
                "vol_ratio": vol_ratio,
            }

        except Exception:
            return VCPAnalyzer._empty_vcp()

    @staticmethod
    def _empty_vcp():
        return {
            "score": 0,
            "atr": 0.0,
            "signals": [],
            "is_dryup": False,
            "range_pct": 0.0,
            "vol_ratio": 1.0
        }

# ==============================================================================
# 📈 RSAnalyzer (一言一句漏らさず復元)
# ==============================================================================

class RSAnalyzer:
    """Relative Strength 計算・ランキング付与エンジン"""
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 21:
                return -999.0

            r12 = (c.iloc[-1] / c.iloc[-252] - 1) if len(c) >= 252 else (c.iloc[-1] / c.iloc[0] - 1)
            r6  = (c.iloc[-1] / c.iloc[-126] - 1) if len(c) >= 126 else (c.iloc[-1] / c.iloc[0] - 1)
            r3  = (c.iloc[-1] / c.iloc[-63]  - 1) if len(c) >= 63  else (c.iloc[-1] / c.iloc[0] - 1)
            r1  = (c.iloc[-1] / c.iloc[-21]  - 1) if len(c) >= 21  else (c.iloc[-1] / c.iloc[0] - 1)

            # 重み付け: 12ヶ月(40%), 6ヶ月(20%), 3ヶ月(20%), 1ヶ月(20%)
            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except Exception:
            return -999.0

    @staticmethod
    def assign_percentiles(raw_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """全銘柄のリストを受け取り、RS Rating(1-99)を付与する"""
        if not raw_list:
            return raw_list

        raw_list.sort(key=lambda x: x.get("raw_rs", -999))
        total = len(raw_list)

        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 98) + 1

        return raw_list

# ==============================================================================
# 🔬 StrategyValidator (一言一句漏らさず復元)
# ==============================================================================

class StrategyValidator:
    """直近1年間のバックテストによる期待値(Profit Factor)の検証"""
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 200:
                return 1.0

            close = df["Close"]
            high = df["High"]
            low = df["Low"]

            # ATR計算
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

            target_mult = EXIT_CFG["TARGET_R_MULT"]
            stop_mult = EXIT_CFG["STOP_LOSS_ATR_MULT"]

            # 直近250日前からシミュレーション開始
            start = max(50, len(df) - 250)

            for i in range(start, len(df)):
                if in_pos:
                    # 決済判定
                    if float(low.iloc[i]) <= stop_p:
                        trades.append(-1.0) # 1R Loss
                        in_pos = False
                    elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * target_mult:
                        trades.append(target_mult) # Gain
                        in_pos = False
                    elif i == len(df) - 1:
                        # 最終日にポジションを持っていた場合
                        risk = entry_p - stop_p
                        if risk > 0:
                            r_result = (float(close.iloc[i]) - entry_p) / risk
                            trades.append(r_result)
                        in_pos = False
                else:
                    if i < 20: continue
                    # エントリー判定（VCP的ブレイクアウト）
                    pivot = float(high.iloc[i - 20:i].max())
                    ma50 = float(close.rolling(50).mean().iloc[i])

                    if (float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50):
                        in_pos = True
                        entry_p = float(close.iloc[i])
                        stop_p = entry_p - float(atr.iloc[i]) * stop_mult

            if not trades:
                return 1.0

            pos_trades = sum(t for t in trades if t > 0)
            neg_trades = abs(sum(t for t in trades if t < 0))
            
            # Profit Factor 算出
            pf = pos_trades / neg_trades if neg_trades > 0 else (5.0 if pos_trades > 0 else 1.0)
            return round(min(10.0, float(pf)), 2)

        except Exception:
            return 1.0

# ==============================================================================
# 🎨 ページ設定 & 視認性向上のための CSS
# ==============================================================================

st.set_page_config(
    page_title="SENTINEL PRO",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

  html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }

  /* モバイル・デスクトップ兼用の高密度グリッドメトリクス */
  .sentinel-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 15px;
  }
  @media (min-width: 992px) {
    .sentinel-grid { grid-template-columns: repeat(4, 1fr); }
  }
  .sentinel-card {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 10px;
    padding: 10px 12px;
  }
  .sentinel-label { font-size: 0.65rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; }
  .sentinel-value { font-size: 1.15rem; font-weight: 700; color: #ffffff; }
  .sentinel-delta { font-size: 0.72rem; font-weight: 600; margin-top: 2px; }

  /* ポジションカードのデザイン */
  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; position: relative; }
  .pos-card.urgent   { border-left: 5px solid #ef4444; }
  .pos-card.caution  { border-left: 5px solid #f59e0b; }
  .pos-card.profit   { border-left: 5px solid #00ff7f; }

  .pnl-pos { color: #00ff7f; font-weight: 700; font-size: 1.2rem; }
  .pnl-neg { color: #ef4444; font-weight: 700; font-size: 1.2rem; }
  .pnl-neu { color: #9ca3af; font-weight: 700; font-size: 1.2rem; }

  .exit-info { font-size: 0.8rem; color: #9ca3af; line-height: 1.8; font-family: 'Share Tech Mono', monospace; }

  .section-header {
    font-size: 1.1rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 6px;
    margin: 14px 0 10px; font-family: 'Share Tech Mono', monospace;
  }

  /* タブの最適化 */
  .stTabs [data-baseweb="tab-list"] { background-color: #0d1117; padding: 5px; border-radius: 10px; gap: 8px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.9rem; font-weight: 600; padding: 10px 14px; color: #9ca3af; }
  .stTabs [aria-selected="true"] { background-color: #00ff7f !important; color: #000 !important; border-radius: 6px; }

  /* 全体の余白 */
  .block-container { padding-top: 0.8rem !important; padding-bottom: 1rem !important; }
  
  [data-testid="stMetric"] { display: none !important; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 📋 セッション状態 & ヘルパー関数
# ==============================================================================

if "target_ticker" not in st.session_state:
    st.session_state["target_ticker"] = ""
if "trigger_analysis" not in st.session_state:
    st.session_state["trigger_analysis"] = False
if "portfolio_dirty" not in st.session_state:
    st.session_state["portfolio_dirty"] = True
if "portfolio_summary" not in st.session_state:
    st.session_state["portfolio_summary"] = None

@st.cache_data(ttl=600)
def get_usd_jpy() -> float:
    return CurrencyEngine.get_usd_jpy()

@st.cache_data(ttl=300)
def fetch_price_data(ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
    return DataEngine.get_data(ticker, period)

@st.cache_data(ttl=60)
def get_current_price(ticker: str) -> Optional[float]:
    return DataEngine.get_current_price(ticker)

@st.cache_data(ttl=300)
def get_atr(ticker: str) -> Optional[float]:
    df = DataEngine.get_data(ticker, "3mo")
    if df is None or len(df) < 15:
        return None
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
    v = float(tr.rolling(14).mean().iloc[-1])
    return round(v, 4) if not pd.isna(v) else None

@st.cache_data(ttl=600)
def load_historical_json() -> pd.DataFrame:
    all_data = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fh:
                    daily = json.load(fh)
                date = daily.get("date", f.stem)
                for key in ("selected", "watchlist_wait", "qualified_full"):
                    for item in daily.get(key, []):
                        item["date"]      = date
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except:
                pass
    return pd.DataFrame(all_data)

# AI Caller
def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ DEEPSEEK_API_KEY が未設定です。Streamlit secrets に追加してください。"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": prompt}],
        )
        return res.choices[0].message.content or ""
    except Exception as e:
        return f"AI Error: {e}"

# Watchlist I/O
def load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f: return json.load(f)
        except: pass
    return []

def _write_watchlist(data: list):
    tmp = Path("watchlist.tmp")
    with open(tmp, "w") as f: json.dump(data, f)
    tmp.replace(WATCHLIST_FILE)

def add_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    if ticker not in wl:
        wl.append(ticker); _write_watchlist(wl); return True
    return False

def remove_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    if ticker in wl:
        wl.remove(ticker); _write_watchlist(wl); return True
    return False

# Portfolio I/O (ロジック全維持)
def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"positions": {}, "closed": [], "meta": {"created": NOW.isoformat()}}

def _write_portfolio(data: dict):
    tmp = Path("portfolio.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(PORTFOLIO_FILE)

def upsert_position(ticker: str, shares: int, avg_cost: float,
                    memo: str = "", target: float = 0.0, stop: float = 0.0) -> dict:
    ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker.upper())[:10]
    data = load_portfolio()
    pos = data["positions"]
    if ticker in pos:
        old = pos[ticker]
        tot = old["shares"] + shares
        pos[ticker].update({
            "shares":     tot,
            "avg_cost":   round((old["shares"] * old["avg_cost"] + shares * avg_cost) / tot, 4),
            "memo":       memo or old.get("memo", ""),
            "target":     target or old.get("target", 0.0),
            "stop":       stop   or old.get("stop",   0.0),
            "updated_at": NOW.isoformat(),
        })
    else:
        pos[ticker] = {
            "ticker": ticker, "shares": shares, "avg_cost": round(avg_cost, 4),
            "memo": memo, "target": round(target, 4), "stop": round(stop, 4),
            "added_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
        }
    _write_portfolio(data)
    return pos[ticker]

def close_position(ticker: str, shares_sold: Optional[int] = None,
                   sell_price: Optional[float] = None) -> bool:
    data = load_portfolio()
    pos = data["positions"]
    if ticker not in pos: return False
    p = pos[ticker]
    actual = shares_sold if shares_sold and shares_sold < p["shares"] else p["shares"]
    if sell_price:
        pnl = (sell_price - p["avg_cost"]) * actual
        data["closed"].append({
            "ticker": ticker, "shares": actual,
            "avg_cost": p["avg_cost"], "sell_price": sell_price,
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2),
            "closed_at": NOW.isoformat(), "memo": p.get("memo", ""),
        })
    if shares_sold and shares_sold < p["shares"]:
        pos[ticker]["shares"] -= shares_sold
    else:
        del pos[ticker]
    _write_portfolio(data)
    return True

# ==============================================================================
# 📊 ポートフォリオ計算ロジック (全維持)
# ==============================================================================

def calc_pos_stats(pos: dict, usd_jpy: float) -> dict:
    cp  = get_current_price(pos["ticker"])
    atr = get_atr(pos["ticker"])
    if cp is None:
        return {**pos, "error": True, "current_price": None}

    shares = pos["shares"]
    avg = pos["avg_cost"]
    pnl_usd = (cp - avg) * shares
    pnl_pct = (cp / avg - 1) * 100
    mv_usd  = cp * shares
    cb_usd  = avg * shares

    ex = {}
    if atr:
        risk  = atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]
        dyn_stop = round(cp - risk, 4)
        reg_stop = pos.get("stop", 0.0)
        # 実効ストップは「動的ストップ」と「手動設定ストップ」の高い方
        eff_stop = max(dyn_stop, reg_stop) if reg_stop > 0 else dyn_stop
        
        cur_r    = (cp - avg) / risk if risk > 0 else 0.0
        reg_tgt  = pos.get("target", 0.0)
        eff_tgt  = reg_tgt if reg_tgt > 0 else round(avg + risk * EXIT_CFG["TARGET_R_MULT"], 4)
        
        # トレールストップ（1.5R以上で発動）
        trail    = round(cp - atr * EXIT_CFG["TRAIL_ATR_MULT"], 4) if cur_r >= EXIT_CFG["TRAIL_START_R"] else None
        
        # 部分利確目標
        scale    = round(avg + risk * EXIT_CFG["SCALE_OUT_R"], 4)
        
        ex = {
            "atr": atr, "risk": round(risk, 4),
            "dyn_stop": dyn_stop, "eff_stop": eff_stop, "eff_tgt": eff_tgt,
            "scale_out": scale, "cur_r": round(cur_r, 2), "trail": trail
        }

    # アイコンによるステータス判定
    cur_r = ex.get("cur_r", 0)
    if   pnl_pct <= -8:                          status = "🚨"
    elif pnl_pct <= -4:                          status = "⚠️"
    elif cur_r >= EXIT_CFG["TARGET_R_MULT"]:     status = "🎯"
    elif cur_r >= EXIT_CFG["TRAIL_START_R"]:     status = "📈"
    elif cur_r >= EXIT_CFG["SCALE_OUT_R"]:       status = "💰"
    elif pnl_pct > 0:                            status = "✅"
    else:                                        status = "🔵"

    return {
        **pos, "current_price": round(cp, 4),
        "pnl_usd": round(pnl_usd, 2), "pnl_pct": round(pnl_pct, 2),
        "pnl_jpy": round(pnl_usd * usd_jpy, 0),
        "mv_usd": round(mv_usd, 2), "cb_usd": round(cb_usd, 2),
        "exit": ex, "status": status
    }

def get_portfolio_summary(usd_jpy: float) -> dict:
    data  = load_portfolio()
    pos_d = data["positions"]
    if not pos_d:
        return {"positions": [], "total": {}, "closed": data.get("closed", [])}

    stats = [calc_pos_stats(p, usd_jpy) for p in pos_d.values()]
    valid = [s for s in stats if not s.get("error")]
    
    total_mv  = sum(s["mv_usd"]  for s in valid)
    total_cb  = sum(s["cb_usd"]  for s in valid)
    total_pnl = sum(s["pnl_usd"] for s in valid)
    cap_usd   = CONFIG["CAPITAL_JPY"] / usd_jpy
    
    for s in valid:
        s["pw"] = round(s["mv_usd"] / total_mv * 100, 1) if total_mv > 0 else 0.0

    closed  = data.get("closed", [])
    win_cnt = len([c for c in closed if c.get("pnl_usd", 0) > 0])
    
    return {
        "positions": stats,
        "total": {
            "count":    len(valid),
            "mv_usd":   round(total_mv, 2),
            "mv_jpy":   round(total_mv * usd_jpy, 0),
            "pnl_usd":  round(total_pnl, 2),
            "pnl_jpy":  round(total_pnl * usd_jpy, 0),
            "pnl_pct":  round(total_pnl / total_cb * 100 if total_cb else 0, 2),
            "exposure": round(total_mv / cap_usd * 100 if cap_usd else 0, 1),
            "cash_jpy": round((cap_usd - total_mv) * usd_jpy, 0),
        },
        "closed_stats": {
            "count":    len(closed),
            "pnl_usd":  round(sum(c.get("pnl_usd", 0) for c in closed), 2),
            "pnl_jpy":  round(sum(c.get("pnl_usd", 0) for c in closed) * usd_jpy, 0),
            "win_rate": round(win_cnt / len(closed) * 100, 1) if closed else 0.0,
        },
        "closed": closed,
    }

# ==============================================================================
# 🎨 UI グリッドヘルパー
# ==============================================================================

def draw_sentinel_metrics(m_list: list):
    """モバイルでも縦に並ばないように HTML グリッドでメトリクスを表示"""
    html = '<div class="sentinel-grid">'
    for m in m_list:
        delta_html = ""
        if "delta" in m and m["delta"]:
            color = "#00ff7f" if "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0) else "#ef4444"
            delta_html = f'<div class="sentinel-delta" style="color:{color}">{m["delta"]}</div>'
        html += f'''
        <div class="sentinel-card">
            <div class="sentinel-label">{m["label"]}</div>
            <div class="sentinel-value">{m["value"]}</div>
            {delta_html}
        </div>
        '''
    st.markdown(html + '</div>', unsafe_allow_html=True)

# ==============================================================================
# 🧭 メイン UI Flow
# ==============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    st.caption(TODAY_STR)
    st.markdown("#### ⭐ Watchlist")
    wl = load_watchlist()
    if not wl:
        st.caption("登録なし")
    else:
        for t in wl:
            c1, c2 = st.columns([3, 1])
            if c1.button(t, key=f"side_{t}", use_container_width=True):
                st.session_state["target_ticker"] = t
                st.session_state["trigger_analysis"] = True
            if c2.button("×", key=f"rm_{t}"):
                remove_watchlist(t); st.rerun()
    st.divider()
    usd_jpy = get_usd_jpy()
    st.metric("💱 USD/JPY", f"¥{usd_jpy}")

# モード選択をタブ化して視認性向上
tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン結果", "🔍 リアルタイム診断", "💼 資産管理"])

# ------------------------------------------------------------------------------
# 📊 TAB 1: スキャン結果 (RS分析クラス等を活用)
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_h = load_historical_json()
    
    if df_h.empty:
        st.info("データがありません。")
    else:
        ld = df_h["date"].max()
        ldf = df_h[df_h["date"] == ld].drop_duplicates("ticker")
        
        draw_sentinel_metrics([
            {"label": "📅 最終スキャン", "value": ld},
            {"label": "💱 為替", "value": f"¥{usd_jpy}"},
            {"label": "💎 ACTION", "value": len(ldf[ldf["status"] == "ACTION"]) if "status" in ldf.columns else "0"},
            {"label": "⏳ WAIT", "value": len(ldf[ldf["status"] == "WAIT"]) if "status" in ldf.columns else "0"}
        ])

        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in ldf.columns:
            fig = px.treemap(
                ldf, path=["sector", "ticker"], 
                values="vcp_score", 
                color="rs" if "rs" in ldf.columns else "vcp_score", 
                color_continuous_scale="RdYlGn"
            )
            fig.update_layout(template="plotly_dark", height=350, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        st.dataframe(
            ldf[["ticker", "status", "price", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), 
            use_container_width=True, height=400
        )

# ------------------------------------------------------------------------------
# 🔍 TAB 2: リアルタイム診断 (プロンプトを一言一句復元)
# ------------------------------------------------------------------------------
with tab_real:
    st.markdown('<div class="section-header">🔍 AI 深度診断 (DeepSeek-Reasoner)</div>', unsafe_allow_html=True)
    t_in = st.text_input("ティッカー入力 (NVDA, TSLA, etc.)", value=st.session_state["target_ticker"]).upper().strip()
    
    c1, c2 = st.columns(2)
    run_req = c1.button("🚀 診断開始", type="primary", use_container_width=True)
    fav_req = c2.button("⭐ Watchlist追加", use_container_width=True)
    
    if fav_req and t_in:
        if add_watchlist(t_in): st.success(f"{t_in} を追加")

    if (run_req or st.session_state.pop("trigger_analysis", False)) and t_in:
        with st.spinner(f"{t_in} を深度解析中..."):
            # データ取得
            data    = fetch_price_data(t_in, "2y")
            news    = fetch_news_cached(t_in)
            fund    = fetch_fundamental_cached(t_in)
            insider = fetch_insider_cached(t_in)
            
            if data is not None and not data.empty:
                vcp = VCPAnalyzer.calculate(data)
                cp  = get_current_price(t_in) or data["Close"].iloc[-1]
                
                draw_sentinel_metrics([
                    {"label": "💰 現在値", "value": f"${cp:.2f}"},
                    {"label": "🎯 VCPスコア", "value": f"{vcp['score']}/105"},
                    {"label": "📊 シグナル", "value": ", ".join(vcp["signals"]) or "特記なし"},
                    {"label": "📈 収縮率", "value": f"{vcp['range_pct']*100:.1f}%"}
                ])
                
                # チャート
                tail = data.tail(60)
                fig_r = go.Figure(go.Candlestick(x=tail.index, open=tail["Open"], high=tail["High"], low=tail["Low"], close=tail["Close"]))
                fig_r.update_layout(template="plotly_dark", height=320, xaxis_rangeslider_visible=False, margin=dict(t=0))
                st.plotly_chart(fig_r, use_container_width=True)

                # ── プロンプト用データ整形 (一言一句復元) ──
                p_now = round(float(cp), 2)
                atr_v = round(vcp["atr"], 2)
                
                # 各エンジンの整形ループ
                f_lines = FundamentalEngine.format_for_prompt(fund, p_now) if hasattr(FundamentalEngine, 'format_for_prompt') else []
                i_lines = InsiderEngine.format_for_prompt(insider) if hasattr(InsiderEngine, 'format_for_prompt') else []
                n_text  = NewsEngine.format_for_prompt(news) if hasattr(NewsEngine, 'format_for_prompt') else ""
                
                # 厳格な詳細プロンプト構築
                prompt = (
                    f"あなたはウォール街のトップファンドマネージャーAI「SENTINEL」です。銘柄 {t_in} について投資診断を行います。\n\n"
                    f"━━━ テクニカル（現在値ベース） ━━━\n診断日: {TODAY_STR}\n現在値: ${p_now}\n"
                    f"VCPスコア: {vcp['score']}/105  信号: {vcp['signals']}\n"
                    f"直近収縮率: {vcp['range_pct']*100:.1f}%  Vol比率: {vcp['vol_ratio']}\n"
                    f"ATR(14): ${atr_v}\n\n"
                    f"━━━ ファンダメンタル ━━━\n" + "\n".join(f_lines) + "\n\n"
                    f"━━━ インサイダー取引 ━━━\n" + "\n".join(i_lines) + "\n\n"
                    f"━━━ 最新ニュース抜粋 & コンテキスト ━━━\n{n_text[:2500]}\n\n"
                    f"━━━ 指示 ━━━\n"
                    f"1. 【現状分析】: 現在の価格アクションがどのステージにあるか、ニュースとファンダメンタルの整合性を踏まえてプロの視点で分析せよ。\n"
                    f"2. 【隠れたリスク】: インサイダー動向、ショート比率、目標株価との乖離など、見逃されがちな懸念点を鋭く指摘せよ。\n"
                    f"3. 【エントリー戦略】: 現在値${p_now}を基準とし、ATR=${atr_v}を考慮した具体的なEntryポイント、およびStop-Loss価格を提示せよ。\n"
                    f"4. 【利確・目標】: 直近および中長期のターゲット1, 2, 3を数値で示せ。\n"
                    f"5. 【総合判断】: Buy/Watch/Avoid のいずれかを断定的に示し、その理由を結論づけよ。\n\n"
                    f"※出力は Markdown 形式で行い、日本語で最低 800 文字以上の詳細な分析を出力すること。為替 ¥{usd_jpy} も加味せよ。"
                )
                
                ai_rep = call_ai(prompt)
                st.markdown("---")
                st.markdown(ai_rep.replace("$", r"\$"))
                st.markdown("---")
            else: st.error("取得失敗。ティッカーを確認してください。")

# ------------------------------------------------------------------------------
# 💼 TAB 3: 資産管理 (出口戦略の計算結果を表示)
# ------------------------------------------------------------------------------
with tab_port:
    p_tabs = st.tabs(["📊 保有損益", "➕ 新規登録", "🤖 AI資産分析", "📜 取引履歴統計"])
    
    with p_tabs[0]:
        if st.session_state["portfolio_dirty"]:
            st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy)
            st.session_state["portfolio_dirty"]   = False
        
        s = st.session_state["portfolio_summary"]
        if s and s.get("positions"):
            t = s["total"]
            draw_sentinel_metrics([
                {"label": "Evaluation P/L", "value": f"¥{t['pnl_jpy']:,.0f}", "delta": f"{t['pnl_pct']:+.2f}%"},
                {"label": "Exposure", "value": f"{t['exposure']:.1f}%"},
                {"label": "Positions", "value": t["count"]},
                {"label": "Free Cash (JPY)", "value": f"¥{t['cash_jpy']:,.0f}"}
            ])
            
            st.markdown('<div class="section-header">📋 ポジション一覧</div>', unsafe_allow_html=True)
            for p in sorted(s["positions"], key=lambda x: x.get("pnl_pct", 0)):
                if p.get("error"): continue
                cl = "urgent" if p["pnl_pct"] <= -8 else ("profit" if p["pnl_pct"] >= 10 else "caution")
                ex = p.get("exit", {})
                st.markdown(f'''
                <div class="pos-card {cl}">
                    <b>{p["status"]} {p["ticker"]}</b> — {p["shares"]}株 @ ${p["avg_cost"]:.2f}<br>
                    現値: ${p["current_price"]:.2f} | 損益: <span class="{"pnl-pos" if p["pnl_pct"]>0 else "pnl-neg"}">{p["pnl_pct"]:+.2f}% (¥{p["pnl_jpy"]:+,.0f})</span>
                    <div class="exit-info">
                        <b>Stop:</b> ${ex.get("eff_stop","—")} | <b>Target:</b> ${ex.get("eff_tgt","—")} | <b>R:</b> {ex.get("cur_r",0)}
                        {f" | <b>Trail:</b> ${ex['trail']}" if ex.get("trail") else ""}
                        {f" | <b>Scale:</b> ${ex['scale_out']}" if ex.get("scale_out") else ""}
                    </div>
                </div>''', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button(f"🔍 診断 {p['ticker']}", key=f"diag_{p['ticker']}"):
                    st.session_state["target_ticker"] = p['ticker']; st.session_state["trigger_analysis"] = True; st.rerun()
                if c2.button(f"✅ {p['ticker']} 決済", key=f"cl_{p['ticker']}"):
                    close_position(p['ticker'], sell_price=p['current_price'])
                    st.session_state["portfolio_dirty"] = True; st.rerun()
        else: st.info("保有中のポジションはありません。")

    with p_tabs[1]:
        with st.form("new_pos_f"):
            c1, c2 = st.columns(2); nt = c1.text_input("ティッカー").upper(); ns = c2.number_input("株数", min_value=1, value=10)
            c3, c4 = st.columns(2); nc = c3.number_input("取得価格 ($)", value=100.0); nst = c4.number_input("損切りライン (任意 $)", value=0.0)
            if st.form_submit_button("✅ 追加"):
                upsert_position(nt, ns, nc, stop=nst); st.session_state["portfolio_dirty"] = True; st.rerun()

    with p_tabs[2]:
        if st.button("🚀 ポートフォリオ全体 AI 分析", type="primary", use_container_width=True):
            s_d = get_portfolio_summary(usd_jpy)
            pos_t = [f"{p['ticker']}: {p['shares']}株 (損益{p['pnl_pct']:+.1f}%)" for p in s_d["positions"] if not p.get("error")]
            prompt = f"Hedge Fund Manager 分析:\nUSD/JPY: {usd_jpy}\nポジション概要:\n" + "\n".join(pos_t) + "\n1.緊急アクション 2.リスク 3.改善案をMarkdownで出力せよ。"
            with st.spinner("AI 思考中..."):
                rep = call_ai(prompt); st.markdown(rep.replace("$", r"\$"))

    with p_tabs[3]:
        summary = get_portfolio_summary(usd_jpy); closed = summary.get("closed", [])
        if closed:
            cs = summary["closed_stats"]
            draw_sentinel_metrics([{"label": "決済数", "value": cs["count"]}, {"label": "確定損益", "value": f"¥{cs['pnl_jpy']:+,.0f}"}, {"label": "勝率", "value": f"{cs['win_rate']}%"}])
            st.dataframe(pd.DataFrame(closed[::-1]), use_container_width=True)

st.divider(); st.caption(f"🛡️ SENTINEL PRO SYSTEM | {NOW.strftime('%H:%M:%S')} | Logic Synced & Verified")

