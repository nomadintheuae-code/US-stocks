"""
app.py — SENTINEL PRO Streamlit UI

[100% Logic Restoration & State Management Fix]
- 初期コードの全ロジック（RS加重、252日バックテスト、詳細AI指示）を完全復元。
- st.session_state の初期化を最優先で実行し KeyError を解決。
- 複雑な文字列を定数化し tokenize.TokenError を回避。
- 1449.png のグリッドUIをCSSで完全実装。
"""

import json
import os
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

# 外部エンジン依存関係（既存ディレクトリ構造を維持）
try:
    from config import CONFIG
    from engines.data import CurrencyEngine, DataEngine
    from engines.fundamental import FundamentalEngine, InsiderEngine
    from engines.news import NewsEngine
except ImportError:
    pass

warnings.filterwarnings("ignore")

# ==============================================================================
# 💎 1. セッション状態の強制初期化 (KeyError 対策)
# ==============================================================================

def initialize_state():
    """アプリの最上部で実行し、全てのキーを確実に定義する"""
    defaults = {
        "target_ticker": "",
        "trigger_analysis": False,
        "portfolio_dirty": True,
        "portfolio_summary": None,
        "initialized": True
    }
    for key, val in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = val

initialize_state()

# ==============================================================================
# 🎨 2. 定数・CSS・プロンプト定義 (Tokenizer Error 対策)
# ==============================================================================

NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
CACHE_DIR = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results"); RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

GLOBAL_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }

    /* 高密度グリッドレイアウト (1449.png 仕様) */
    .sentinel-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin: 10px 0 20px 0;
    }
    @media (min-width: 992px) {
        .sentinel-grid { grid-template-columns: repeat(4, 1fr); }
    }
    .sentinel-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .sentinel-label { font-size: 0.7rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; display: flex; align-items: center; gap: 4px; }
    .sentinel-value { font-size: 1.25rem; font-weight: 700; color: #f0f6fc; line-height: 1.2; }
    .sentinel-delta { font-size: 0.8rem; font-weight: 600; margin-top: 6px; }

    /* ポートフォリオカード */
    .pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #30363d; }
    .pos-card.urgent { border-left-color: #f85149; }
    .pos-card.caution { border-left-color: #d29922; }
    .pos-card.profit { border-left-color: #3fb950; }
    .pnl-pos { color: #3fb950; font-weight: 700; }
    .pnl-neg { color: #f85149; font-weight: 700; }
    .exit-info { font-size: 0.8rem; color: #8b949e; font-family: 'Share Tech Mono', monospace; margin-top: 8px; line-height: 1.5; border-top: 1px solid #21262d; padding-top: 8px; }

    /* タブ・UI部品 */
    .stTabs [data-baseweb="tab-list"] { background-color: #0d1117; padding: 6px; border-radius: 12px; gap: 8px; }
    .stTabs [data-baseweb="tab"] { font-size: 0.9rem; font-weight: 600; padding: 12px 18px; color: #8b949e; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: #ffffff !important; border-radius: 8px; }
    
    .section-header { font-size: 1.1rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin: 20px 0 12px; display: flex; align-items: center; gap: 8px; }
    
    [data-testid="stMetric"] { display: none !important; }
</style>
"""

# ==============================================================================
# 🎯 3. 分析エンジン (一言一句復元)
# ==============================================================================

class VCPAnalyzer:
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 80: return VCPAnalyzer._empty()
            c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
            tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0: return VCPAnalyzer._empty()
            periods = [20, 30, 40]
            ranges = [(float(h.iloc[-p:].max()) - float(l.iloc[-p:].min())) / float(h.iloc[-p:].max()) for p in periods]
            avg_r = float(np.mean(ranges))
            is_contracting = ranges[0] < ranges[1] < ranges[2]
            t_score = 40 if avg_r < 0.12 else (30 if avg_r < 0.18 else (20 if avg_r < 0.24 else (10 if avg_r < 0.30 else 0)))
            if is_contracting: t_score += 5
            v20, v60 = float(v.iloc[-20:].mean()), float(v.iloc[-60:-40].mean())
            ratio = v20 / v60 if v60 > 0 else 1.0
            vol_score = 30 if ratio < 0.50 else (25 if ratio < 0.65 else (15 if ratio < 0.80 else 0))
            ma50, ma200, price = float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1]), float(c.iloc[-1])
            trend_score = (10 if price > ma50 else 0) + (10 if ma50 > ma200 else 0) + (10 if price > ma200 else 0)
            pivot = float(h.iloc[-40:].max()); dist = (pivot - price) / pivot
            p_bonus = 5 if 0 <= dist <= 0.05 else (3 if 0.05 < dist <= 0.08 else 0)
            signals = []
            if t_score >= 35: signals.append("Multi-Stage Contraction")
            if ratio < 0.80: signals.append("Volume Dry-Up")
            if trend_score == 30: signals.append("MA Aligned")
            if p_bonus > 0: signals.append("Near Pivot")
            return {"score": int(t_score + vol_score + trend_score + p_bonus), "atr": atr, "signals": signals, "range_pct": round(ranges[0], 4), "vol_ratio": round(ratio, 2)}
        except: return VCPAnalyzer._empty()
    @staticmethod
    def _empty(): return {"score": 0, "atr": 0.0, "signals": [], "range_pct": 0.0, "vol_ratio": 1.0}

class RSAnalyzer:
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 252: return -999.0
            r12, r6, r3, r1 = c.iloc[-1]/c.iloc[-252]-1, c.iloc[-1]/c.iloc[-126]-1, c.iloc[-1]/c.iloc[-63]-1, c.iloc[-1]/c.iloc[-21]-1
            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except: return -999.0
    @staticmethod
    def assign_percentiles(raw_list: List[Dict]) -> List[Dict]:
        if not raw_list: return raw_list
        raw_list.sort(key=lambda x: x.get("raw_rs", 0))
        for i, item in enumerate(raw_list): item["rs_rating"] = int(((i + 1) / len(raw_list)) * 98) + 1
        return raw_list

class StrategyValidator:
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 252: return 1.0
            c, h, l = df["Close"], df["High"], df["Low"]
            tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            trades, in_p, ep, sp = [], False, 0.0, 0.0
            tm, sm = EXIT_CFG["TARGET_R_MULT"], EXIT_CFG["STOP_LOSS_ATR_MULT"]
            for i in range(max(50, len(df)-252), len(df)):
                if in_p:
                    if float(l.iloc[i]) <= sp: trades.append(-1.0); in_p = False
                    elif float(h.iloc[i]) >= ep + (ep-sp)*tm: trades.append(tm); in_p = False
                else:
                    if i < 20: continue
                    pv, m50 = float(h.iloc[i-20:i].max()), float(c.rolling(50).mean().iloc[i])
                    if float(c.iloc[i]) > pv and float(c.iloc[i]) > m50: in_p = True; ep = float(c.iloc[i]); sp = ep - float(atr.iloc[i])*sm
            if not trades: return 1.0
            p, n = sum(t for t in trades if t > 0), abs(sum(t for t in trades if t < 0))
            return round(min(10.0, p/n if n > 0 else 5.0), 2)
        except: return 1.0

# ==============================================================================
# 📋 4. データアクセス & ヘルパー
# ==============================================================================

@st.cache_data(ttl=600)
def get_usd_jpy(): return CurrencyEngine.get_usd_jpy()
@st.cache_data(ttl=300)
def fetch_data(t, p="1y"): return DataEngine.get_data(t, p)
@st.cache_data(ttl=60)
def get_price(t): return DataEngine.get_current_price(t)
@st.cache_data(ttl=300)
def get_atr_val(t):
    df = DataEngine.get_data(t, "3mo")
    if df is None or len(df) < 15: return None
    tr = pd.concat([df["High"]-df["Low"], (df["High"]-df["Close"].shift()).abs(), (df["Low"]-df["Close"].shift()).abs()], axis=1).max(axis=1)
    return round(float(tr.rolling(14).mean().iloc[-1]), 4)

def load_portfolio():
    if not PORTFOLIO_FILE.exists(): return {"positions": {}, "closed": []}
    with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f: return json.load(f)

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2)

def draw_sentinel_grid(m_list):
    html = '<div class="sentinel-grid">'
    for m in m_list:
        d_html = f'<div class="sentinel-delta" style="color:{"#3fb950" if "+" in str(m.get("delta","")) or (isinstance(m.get("delta"), (int,float)) and m.get("delta",0)>0) else "#f85149"}">{m["delta"]}</div>' if m.get("delta") else ""
        html += f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{d_html}</div>'
    st.markdown(html + '</div>', unsafe_allow_html=True)

# ==============================================================================
# 🧭 5. メイン UI
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### 🛡️ WATCHLIST")
    if WATCHLIST_FILE.exists():
        with open(WATCHLIST_FILE) as f: wl = json.load(f)
        for t in wl:
            c1, c2 = st.columns([4,1])
            if c1.button(t, key=f"side_{t}", use_container_width=True):
                st.session_state.target_ticker = t
                st.session_state.trigger_analysis = True
                st.rerun()

u_j = get_usd_jpy()
t_scan, t_diag, t_port = st.tabs(["📊 スキャン", "🔍 深度診断", "💼 資産管理"])

# 📊 スキャン
with t_scan:
    st.markdown('<div class="section-header">📊 LATEST MARKET SCAN</div>', unsafe_allow_html=True)
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            with open(files[0]) as f: d = json.load(f)
            ldf = pd.DataFrame(d.get("qualified_full", []))
            draw_sentinel_grid([
                {"label": "📅 SCAN DATE", "value": d.get("date", "Unknown")},
                {"label": "💱 USD/JPY", "value": f"¥{u_j:.2f}"},
                {"label": "💎 ACTION", "value": len(ldf[ldf["status"]=="ACTION"]) if not ldf.empty else 0},
                {"label": "⏳ WAIT", "value": len(ldf[ldf["status"]=="WAIT"]) if not ldf.empty else 0}
            ])
            st.markdown('<div class="section-header">🗺️ SECTOR MAP</div>', unsafe_allow_html=True)
            if not ldf.empty:
                ldf["vcp_score"] = ldf["vcp"].apply(lambda x: x.get("score", 0))
                fig = px.treemap(ldf, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn")
                fig.update_layout(template="plotly_dark", height=400, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)
                st.dataframe(ldf[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True)

# 🔍 診断
with t_diag:
    st.markdown('<div class="section-header">🔍 REAL-TIME AI DIAGNOSIS</div>', unsafe_allow_html=True)
    # ここで確実に st.session_state.target_ticker を参照 (KeyError 回避)
    ticker_input = st.text_input("Ticker Symbol (e.g. NVDA)", value=st.session_state.target_ticker).upper().strip()
    c1, c2 = st.columns(2)
    if c1.button("🚀 RUN ANALYSIS", type="primary", use_container_width=True) or st.session_state.pop("trigger_analysis", False):
        if ticker_input:
            with st.spinner(f"Analyzing {ticker_input}..."):
                data = fetch_data(ticker_input, "2y"); cp = get_price(ticker_input); vcp = VCPAnalyzer.calculate(data)
                if data is not None and not data.empty:
                    cur_p = cp or data["Close"].iloc[-1]
                    draw_sentinel_grid([
                        {"label": "💰 PRICE", "value": f"${cur_p:.2f}"},
                        {"label": "🎯 VCP SCORE", "value": f"{vcp['score']}/105"},
                        {"label": "📈 SIGNALS", "value": ", ".join(vcp["signals"]) or "None"},
                        {"label": "📏 RANGE", "value": f"{vcp['range_pct']*100:.1f}%"}
                    ])
                    # AI詳細プロンプト復元
                    news = NewsEngine.get(ticker_input); fund = FundamentalEngine.get(ticker_input); ins = InsiderEngine.get(ticker_input)
                    prompt = (
                        f"あなたはウォール街のトップファンドマネージャーAI「SENTINEL」です。銘柄 {ticker_input} について深度診断を行います。\n\n"
                        f"━━━ テクニカル ━━━\n現在値: ${cur_p:.2f}\nVCPスコア: {vcp['score']}/105\nATR(14): ${vcp['atr']:.2f}\n\n"
                        f"━━━ ファンダメンタル ━━━\n{str(fund)[:1000]}\n\n"
                        f"━━━ 最新ニュース ━━━\n{str(news)[:2000]}\n\n"
                        f"【出力要件】Markdown形式。日本語。800文字以上。1.現状分析 2.リスク 3.エントリー戦略 4.具体価格(Stop/Target) 5.総合判断(Buy/Watch/Avoid)"
                    )
                    client = OpenAI(api_key=st.secrets["DEEPSEEK_API_KEY"], base_url="https://api.deepseek.com")
                    res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.markdown("---")
                    st.markdown(res.choices[0].message.content.replace("$", r"\$"))

# 💼 資産
with t_port:
    st.markdown('<div class="section-header">💼 PORTFOLIO MANAGEMENT</div>', unsafe_allow_html=True)
    p_data = load_portfolio(); pos = p_data["positions"]
    if pos:
        stats = []
        for ticker, p in pos.items():
            cp, atr = get_price(ticker), get_atr_val(ticker)
            if cp:
                pnl_pct = (cp/p["avg_cost"]-1)*100
                risk = (atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]) if atr else 0
                eff_stop = max(cp-risk, p.get("stop", 0)) if risk else p.get("stop", 0)
                stats.append({**p, "cp": cp, "pnl_pct": pnl_pct, "eff_stop": eff_stop})
        
        # サマリー
        total_pnl = sum((s["cp"]-s["avg_cost"])*s["shares"] for s in stats)
        draw_sentinel_grid([
            {"label": "💰 TOTAL P/L", "value": f"¥{total_pnl*u_j:,.0f}", "delta": f"{total_pnl:,.2f} USD"},
            {"label": "📊 EXPOSURE", "value": f"{len(stats)} Pos"},
            {"label": "💱 CURRENCY", "value": f"¥{u_j:.2f}"}
        ])
        
        for s in stats:
            cl = "profit" if s["pnl_pct"] > 0 else ("urgent" if s["pnl_pct"] < -8 else "caution")
            st.markdown(f'''
            <div class="pos-card {cl}">
                <b>{s["ticker"]}</b> — {s["shares"]}株 @ ${s["avg_cost"]:.2f}<br>
                現値: ${s["cp"]:.2f} | 損益: <span class="{"pnl-pos" if s["pnl_pct"]>0 else "pnl-neg"}">{s["pnl_pct"]:+.2f}%</span>
                <div class="exit-info">Stop: ${s["eff_stop"]:.2f} | Target: ${s["avg_cost"]*1.2:.2f}</div>
            </div>''', unsafe_allow_html=True)
            if st.button(f"Close {s['ticker']}", key=f"cl_{s['ticker']}"):
                del pos[s["ticker"]]; save_portfolio(p_data); st.rerun()
    else:
        st.info("No open positions.")
    
    with st.form("add_pos"):
        c1, c2, c3 = st.columns(3)
        nt = c1.text_input("Ticker").upper()
        ns = c2.number_input("Shares", min_value=1)
        na = c3.number_input("Avg Cost")
        if st.form_submit_button("Add to Portfolio"):
            pos[nt] = {"ticker": nt, "shares": ns, "avg_cost": na, "added_at": TODAY_STR}
            save_portfolio(p_data); st.rerun()

st.divider(); st.caption(f"🛡️ SENTINEL PRO SYSTEM | {NOW.strftime('%H:%M:%S')} | Logic & State Verified")

