"""
app.py — SENTINEL PRO Streamlit UI

モード:
    📊 スキャン    — 前回スキャン結果の表示・セクターマップ
    🔍 リアルタイム — 個別銘柄のAI深度診断（DeepSeek-Reasoner）
    💼 ポートフォリオ — 損益管理・出口戦略・AI分析
"""

import json
import os
import pickle
import re
import time
import warnings
import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

from config import CONFIG
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数 & 設定
# ==============================================================================

NOW         = datetime.datetime.now()
TODAY_STR   = NOW.strftime("%Y-%m-%d")
CACHE_DIR   = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results");   RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

# ==============================================================================
# 🎨 ページ設定 & CSS（視認性向上）
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

  /* メトリクス表示の最適化 */
  [data-testid="metric-container"] {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 10px;
    padding: 12px 10px;
  }
  [data-testid="metric-container"] label { font-size: 0.75rem !important; color: #6b7280; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 1.2rem !important; font-weight: 700; }

  /* タブの視認性向上（モバイル対応） */
  .stTabs [data-baseweb="tab-list"] { gap: 10px; }
  .stTabs [data-baseweb="tab"] {
    font-size: 0.9rem;
    padding: 12px 16px;
    font-weight: 600;
    border-radius: 8px 8px 0 0;
  }

  .stButton > button { min-height: 48px; font-weight: 600; border-radius: 8px; }

  /* ポジションカードのデザイン維持 */
  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
  .pos-card.urgent   { border-left: 5px solid #ef4444; }
  .pos-card.caution  { border-left: 5px solid #f59e0b; }
  .pos-card.profit   { border-left: 5px solid #00ff7f; }

  .pnl-pos { color: #00ff7f; font-weight: 700; }
  .pnl-neg { color: #ef4444; font-weight: 700; }
  .exit-info { font-size: 0.8rem; color: #9ca3af; font-family: 'Share Tech Mono', monospace; margin-top: 6px; }

  .section-header {
    font-size: 1.1rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 6px;
    margin: 18px 0 12px; font-family: 'Share Tech Mono', monospace;
  }

  .block-container { padding-top: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 📋 セッション状態
# ==============================================================================

if "target_ticker" not in st.session_state: st.session_state["target_ticker"] = ""
if "trigger_analysis" not in st.session_state: st.session_state["trigger_analysis"] = False
if "portfolio_dirty" not in st.session_state: st.session_state["portfolio_dirty"] = True
if "portfolio_summary" not in st.session_state: st.session_state["portfolio_summary"] = None

# ==============================================================================
# 💾 データ取得（ロジック維持）
# ==============================================================================

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
    if df is None or len(df) < 15: return None
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    v = float(tr.rolling(14).mean().iloc[-1])
    return round(v, 4) if not pd.isna(v) else None

@st.cache_data(ttl=600)
def load_historical_json() -> pd.DataFrame:
    all_data = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fh: daily = json.load(fh)
                d = daily.get("date", f.stem)
                for key in ("selected", "watchlist_wait", "qualified_full"):
                    for item in daily.get(key, []):
                        item["date"] = d
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except: pass
    return pd.DataFrame(all_data)

# ==============================================================================
# 🧠 VCP 分析（バックエンド VCPAnalyzer ロジックと同期）
# ==============================================================================

def _empty_vcp() -> dict:
    return {"score": 0, "atr": 0.0, "signals": [], "is_dryup": False, "range_pct": 0.0, "vol_ratio": 1.0}

def calc_vcp(df: pd.DataFrame) -> dict:
    try:
        if df is None or len(df) < 80: return _empty_vcp()
        close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

        # ATR(14)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if pd.isna(atr) or atr <= 0: return _empty_vcp()

        # 1. Tightness (40pt)
        periods = [20, 30, 40]
        ranges = []
        for p in periods:
            h_p = float(high.iloc[-p:].max())
            l_p = float(low.iloc[-p:].min())
            ranges.append((h_p - l_p) / h_p)
        avg_range = float(np.mean(ranges))
        is_contracting = ranges[0] < ranges[1] < ranges[2]

        if avg_range < 0.12: tight_score = 40
        elif avg_range < 0.18: tight_score = 30
        elif avg_range < 0.24: tight_score = 20
        elif avg_range < 0.30: tight_score = 10
        else: tight_score = 0
        if is_contracting: tight_score += 5
        tight_score = min(40, tight_score)

        # 2. Volume (30pt)
        v20 = float(volume.iloc[-20:].mean())
        v60 = float(volume.iloc[-60:-40].mean())
        ratio = v20 / v60 if v60 > 0 else 1.0
        if ratio < 0.50: vol_score = 30
        elif ratio < 0.65: vol_score = 25
        elif ratio < 0.80: vol_score = 15
        else: vol_score = 0
        is_dryup = ratio < 0.80

        # 3. MA Alignment (30pt)
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        trend_score = (10 if price > ma50 else 0) + (10 if ma50 > ma200 else 0) + (10 if price > ma200 else 0)

        # 4. Pivot Bonus (+5pt)
        pivot = float(high.iloc[-40:].max())
        distance = (pivot - price) / pivot
        pivot_bonus = 5 if 0 <= distance <= 0.05 else (3 if 0.05 < distance <= 0.08 else 0)

        signals = []
        if tight_score >= 35: signals.append("Multi-Stage Contraction")
        if is_dryup: signals.append("Volume Dry-Up")
        if trend_score == 30: signals.append("MA Aligned")
        if pivot_bonus > 0: signals.append("Near Pivot")

        return {
            "score": int(max(0, tight_score + vol_score + trend_score + pivot_bonus)),
            "atr": atr, "signals": signals, "is_dryup": is_dryup,
            "range_pct": round(ranges[0], 4), "vol_ratio": round(ratio, 2)
        }
    except: return _empty_vcp()

# ==============================================================================
# 🤖 AI（DeepSeek-Reasoner）
# ==============================================================================

def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key: return "⚠️ DEEPSEEK_API_KEY 未設定"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content or ""
    except Exception as e: return f"AI Error: {e}"

# ==============================================================================
# 📋 I/O 処理 (Watchlist & Portfolio - ロジック維持)
# ==============================================================================

def load_watchlist():
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f: return json.load(f)
        except: pass
    return []

def _write_watchlist(data):
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

def load_portfolio():
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"positions": {}, "closed": [], "meta": {"created": NOW.isoformat()}}

def _write_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def upsert_position(ticker, shares, avg_cost, memo="", target=0.0, stop=0.0):
    data = load_portfolio(); pos = data["positions"]
    t = ticker.upper()
    if t in pos:
        old = pos[t]; tot = old["shares"] + shares
        pos[t].update({
            "shares": tot, "avg_cost": round((old["shares"]*old["avg_cost"] + shares*avg_cost)/tot, 4),
            "memo": memo or old.get("memo", ""), "target": target or old.get("target", 0.0),
            "stop": stop or old.get("stop", 0.0), "updated_at": NOW.isoformat(),
        })
    else:
        pos[t] = {"ticker": t, "shares": shares, "avg_cost": avg_cost, "memo": memo, "target": target, "stop": stop, "added_at": NOW.isoformat()}
    _write_portfolio(data)

def close_position(ticker, shares_sold=None, sell_price=None):
    data = load_portfolio(); pos = data["positions"]
    if ticker not in pos: return False
    p = pos[ticker]; actual = shares_sold if shares_sold else p["shares"]
    if sell_price:
        data["closed"].append({
            "ticker": ticker, "shares": actual, "avg_cost": p["avg_cost"], "sell_price": sell_price,
            "pnl_usd": round((sell_price - p["avg_cost"]) * actual, 2), "closed_at": NOW.isoformat()
        })
    if shares_sold and shares_sold < p["shares"]: pos[ticker]["shares"] -= shares_sold
    else: del pos[ticker]
    _write_portfolio(data); return True

# ==============================================================================
# 📊 ポートフォリオ集計（ロジック維持）
# ==============================================================================

def calc_pos_stats(pos, usd_jpy):
    cp = get_current_price(pos["ticker"]); atr = get_atr(pos["ticker"])
    if cp is None: return {**pos, "error": True}
    pnl_usd = (cp - pos["avg_cost"]) * pos["shares"]
    pnl_pct = (cp / pos["avg_cost"] - 1) * 100
    ex = {}
    if atr:
        risk = atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]
        eff_stop = max(round(cp - risk, 4), pos.get("stop", 0.0))
        cur_r = (cp - pos["avg_cost"]) / risk if risk > 0 else 0.0
        ex = {"atr": atr, "eff_stop": eff_stop, "cur_r": round(cur_r, 2)}
    
    st_icon = "🔵"
    if pnl_pct <= -8: st_icon = "🚨"
    elif pnl_pct >= 10: st_icon = "✅"

    return {**pos, "current_price": cp, "pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "pnl_jpy": pnl_usd * usd_jpy, "exit": ex, "status": st_icon}

def get_portfolio_summary(usd_jpy):
    data = load_portfolio(); pos_d = data["positions"]
    if not pos_d: return {"positions": [], "total": {}, "closed": data.get("closed", [])}
    stats = [calc_pos_stats(p, usd_jpy) for p in pos_d.values()]
    valid = [s for s in stats if not s.get("error")]
    total_mv = sum(s["current_price"] * s["shares"] for s in valid)
    total_pnl = sum(s["pnl_usd"] for s in valid)
    return {"positions": stats, "total": {"mv_jpy": total_mv * usd_jpy, "pnl_jpy": total_pnl * usd_jpy, "count": len(valid)}, "closed": data.get("closed", [])}

# ==============================================================================
# 🧭 メイン UI: TABS による視認性向上
# ==============================================================================

# サイドバー
with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    wl = load_watchlist()
    for t in wl:
        c1, c2 = st.columns([4, 1])
        if c1.button(f"🔍 {t}", key=f"side_{t}", use_container_width=True):
            st.session_state["target_ticker"] = t
            st.session_state["trigger_analysis"] = True
        if c2.button("×", key=f"rm_{t}"):
            wl.remove(t); _write_watchlist(wl); st.rerun()

usd_jpy = get_usd_jpy()

# メインナビゲーションをタブ化
tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン", "🔍 リアルタイム", "💼 ポートフォリオ"])

# ------------------------------------------------------------------------------
# 📊 TAB 1: スキャン
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_hist = load_historical_json()
    if df_hist.empty:
        st.info("データがありません。")
    else:
        latest_date = df_hist["date"].max()
        latest_df = df_hist[df_hist["date"] == latest_date].drop_duplicates("ticker")
        
        c1, c2, c3 = st.columns(3)
        c1.metric("📅 スキャン日", latest_date)
        c2.metric("💱 為替", f"¥{usd_jpy}")
        c3.metric("💎 銘柄数", len(latest_df))

        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        fig = px.treemap(latest_df, path=["sector", "ticker"], values="vcp_score", color="vcp_score", color_continuous_scale="RdYlGn")
        fig.update_layout(template="plotly_dark", height=350, margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        st.dataframe(latest_df[["ticker", "status", "vcp_score", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True)

# ------------------------------------------------------------------------------
# 🔍 TAB 2: リアルタイム診断
# ------------------------------------------------------------------------------
with tab_real:
    st.markdown('<div class="section-header">🔍 AI リアルタイム診断</div>', unsafe_allow_html=True)
    t_in = st.text_input("Ticker", value=st.session_state["target_ticker"]).upper().strip()
    
    col_b1, col_b2 = st.columns(2)
    if col_b1.button("🚀 診断開始", type="primary", use_container_width=True) or st.session_state.pop("trigger_analysis", False):
        if t_in:
            with st.spinner(f"{t_in} 分析中..."):
                data = fetch_price_data(t_in)
                if data is not None and not data.empty:
                    vcp = calc_vcp(data); cp = get_current_price(t_in) or data["Close"].iloc[-1]
                    
                    k1, k2, k3 = st.columns(3)
                    k1.metric("💰 価格", f"${cp:.2f}")
                    k2.metric("🎯 VCP", f"{vcp['score']}/105")
                    k3.metric("📊 収縮", f"{vcp['range_pct']*100:.1f}%")
                    
                    tail = data.tail(60)
                    fig = go.Figure(go.Candlestick(x=tail.index, open=tail["Open"], high=tail["High"], low=tail["Low"], close=tail["Close"]))
                    fig.update_layout(template="plotly_dark", height=320, xaxis_rangeslider_visible=False, margin=dict(t=0))
                    st.plotly_chart(fig, use_container_width=True)
                    
                    ai = call_ai(f"Analyze {t_in}. Price: {cp}, VCP: {vcp['score']}, News: {NewsEngine.get(t_in)}")
                    st.markdown("---")
                    st.markdown(ai.replace("$", r"\$"))
                else: st.error("データ取得失敗")

    if col_b2.button("⭐ Watchlist 追加", use_container_width=True) and t_in:
        wl = load_watchlist()
        if t_in not in wl: wl.append(t_in); _write_watchlist(wl); st.success("追加しました")

# ------------------------------------------------------------------------------
# 💼 TAB 3: ポートフォリオ
# ------------------------------------------------------------------------------
with tab_port:
    st.markdown('<div class="section-header">💼 資産状況</div>', unsafe_allow_html=True)
    
    if st.session_state["portfolio_dirty"]:
        st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy)
        st.session_state["portfolio_dirty"] = False
    
    summary = st.session_state["portfolio_summary"]
    if summary and summary.get("positions"):
        t_data = summary["total"]
        st.metric("トータル評価額", f"¥{t_data['mv_jpy']:,.0f}", f"損益: ¥{t_data['pnl_jpy']:+,.0f}")
        
        st.markdown('<div class="section-header">📋 ポジション詳細</div>', unsafe_allow_html=True)
        for pos in summary["positions"]:
            if pos.get("error"): continue
            ex = pos.get("exit", {})
            st.markdown(f"""
            <div class="pos-card {'profit' if pos['pnl_pct']>0 else 'urgent'}">
                <b>{pos['status']} {pos['ticker']}</b> | {pos['shares']}株 @ ${pos['avg_cost']:.2f}<br>
                現値: ${pos['current_price']:.2f} | 損益: <span class="{'pnl-pos' if pos['pnl_pct']>0 else 'pnl-neg'}">{pos['pnl_pct']:+.2f}%</span><br>
                <div class="exit-info">Stop: ${ex.get('eff_stop','—')} | R: {ex.get('cur_r',0)}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"決済 {pos['ticker']}", key=f"cl_{pos['ticker']}"):
                close_position(pos['ticker'], sell_price=pos['current_price'])
                st.session_state["portfolio_dirty"] = True; st.rerun()
    else:
        st.info("ポジションがありません。")

    with st.expander("➕ 新規ポジション追加"):
        with st.form("add_p"):
            f_t = st.text_input("Ticker").upper()
            f_s = st.number_input("Shares", min_value=1)
            f_c = st.number_input("Avg Cost", min_value=0.01)
            if st.form_submit_button("追加"):
                upsert_position(f_t, f_s, f_c); st.session_state["portfolio_dirty"] = True; st.rerun()

st.divider()
st.caption(f"SENTINEL PRO Optimized UI | {NOW.strftime('%H:%M:%S')}")

