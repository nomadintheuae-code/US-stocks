import json
import os
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

# ==============================================================================
# 1. エンジンのインポート
# ==============================================================================
try:
    from config import CONFIG
except ImportError:
    CONFIG = {"STOP_LOSS_ATR": 2.0, "TARGET_R": 2.5}

from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator
from engines.ecr_strategy import ECRStrategyEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. 定数・パスの定義
# ==============================================================================
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ==============================================================================
# 3. セッションステート & ヘルパー関数
# ==============================================================================

def initialize_sentinel_state():
    """アプリの状態を初期化"""
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = ""
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

def load_portfolio_json() -> dict:
    default = {"positions": {}, "cash_jpy": 1000000, "cash_usd": 0}
    if not PORTFOLIO_FILE.exists(): return default
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_portfolio_json(data: dict):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist_data() -> list:
    if not WATCHLIST_FILE.exists(): return []
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_watchlist_data(data: list):
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

def get_market_overview_live():
    try:
        spy_t = yf.Ticker("SPY")
        spy_h = spy_t.history(period="3d")
        vix_t = yf.Ticker("^VIX")
        vix_h = vix_t.history(period="1d")
        if not spy_h.empty and len(spy_h) >= 2:
            spy_p = spy_h["Close"].iloc[-1]
            spy_chg = (spy_p / spy_h["Close"].iloc[-2] - 1) * 100
        else:
            spy_p = spy_t.fast_info.get('lastPrice', 0)
            spy_chg = 0
        vix_p = vix_h["Close"].iloc[-1] if not vix_h.empty else 0
        return {"spy": spy_p, "spy_change": spy_chg, "vix": vix_p}
    except:
        return {"spy": 0, "spy_change": 0, "vix": 0}

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    html_out = '<div class="sentinel-grid">'
    for m in metrics:
        delta_s = ""
        if "delta" in m and m["delta"]:
            is_pos = "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0)
            c_code = "#3fb950" if is_pos else "#f85149"
            delta_s = f'<div class="sentinel-delta" style="color:{c_code}">{m["delta"]}</div>'
        item = f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{delta_s}</div>'
        html_out += item
    html_out += '</div>'
    st.markdown(html_out.strip(), unsafe_allow_html=True)

# ==============================================================================
# 4. UI スタイル定義 (CSS)
# ==============================================================================
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 1rem !important; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 10px; border-bottom: 2px solid #30363d; gap: 10px; }
.stTabs [data-baseweb="tab"] { color: #8b949e; border: none; font-weight: 700; min-width: 150px; }
.stTabs [aria-selected="true"] { color: #ffffff !important; background-color: #238636 !important; border-radius: 8px; }
.sentinel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0; }
@media (min-width: 900px) { .sentinel-grid { grid-template-columns: repeat(4, 1fr); } }
.sentinel-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
.sentinel-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; margin-bottom: 8px; font-weight: 600; }
.sentinel-value { font-size: 1.4rem; font-weight: 700; color: #f0f6fc; line-height: 1.1; }
.sentinel-delta { font-size: 0.95rem; font-weight: 600; margin-top: 8px; }
.section-header { font-size: 1.2rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin: 30px 0 20px; text-transform: uppercase; letter-spacing: 2px; }
.pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 15px; border-left: 10px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
.pnl-pos { color: #3fb950; font-weight: bold; }
.pnl-neg { color: #f85149; font-weight: bold; }
</style>
"""

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# --- サイドバー ---
with st.sidebar:
    st.markdown("### 🛡️ ウォッチリスト")
    wl_data = load_watchlist_data()
    for tkr in wl_data:
        c1, c2 = st.columns([4, 1])
        if c1.button(tkr, key=f"s_{tkr}", use_container_width=True):
            st.session_state.target_ticker = tkr
            st.rerun()
        if c2.button("×", key=f"r_{tkr}"):
            wl_data.remove(tkr); save_watchlist_data(wl_data); st.rerun()

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs(["📊 マーケット", "🔍 戦略診断(ECR)", "💼 ポートフォリオ"])

# ------------------------------------------------------------------------------
# TAB 1: マーケットスキャン (AI分析復旧)
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown('<div class="section-header">📊 マーケットスキャン (地合い分析)</div>', unsafe_allow_html=True)
    m_info = get_market_overview_live()
    
    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            try:
                with open(files[0], "r", encoding="utf-8") as f: 
                    data_json = json.load(f)
                    scan_df = pd.DataFrame(data_json.get("qualified_full", []))
            except: pass

    if st.button("🤖 AI市場分析 (SENTINEL MARKET EYE)", use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("Analyzing Market conditions..."):
                m_news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                act_n = len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0
                prompt = (f"SPY: ${m_info['spy']:.2f}, VIX: {m_info['vix']:.2f}\n"
                          f"アクション銘柄数: {act_n}\nニュース:\n{m_news}\n\n"
                          f"客観的な市場分析を行ってください。")
                try:
                    cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content
                except: st.error("AI Error")
        else: st.warning("APIキー未設定")

    if st.session_state.ai_market_text: st.info(st.session_state.ai_market_text)

    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_info['vix']:.2f}"},
        {"label": "USD/JPY", "value": f"¥{fx_val:.2f}"},
        {"label": "アクション銘柄", "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0}
    ])

# ------------------------------------------------------------------------------
# TAB 2: 戦略診断 (ECR V2.1)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown('<div class="section-header">🔍 ECR戦略スキャン (V2.1)</div>', unsafe_allow_html=True)
    t_input = st.text_input("ティッカーシンボル", value=st.session_state.target_ticker).upper().strip()

    c1, c2 = st.columns(2)
    if c1.button("🚀 分析実行", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df = DataEngine.get_data(t_input, "2y")
            if df is not None:
                v_res = VCPAnalyzer.calculate(df)
                ecr_res = ECRStrategyEngine.analyze_single(t_input, df)
                p_c = DataEngine.get_current_price(t_input)
                pf_v = StrategyValidator.run(df)
                st.session_state.quant_results_stored = {
                    "vcp": v_res, "price": p_c, "pf": pf_v, "ticker": t_input, "ecr": ecr_res
                }
            else: st.error("データ取得不可")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        res = st.session_state.quant_results_stored
        ecr = res["ecr"]
        
        p_color = "#238636" if ecr["phase"] == "ACCUMULATION" else "#d29922" if ecr["phase"] == "IGNITION" else "#f85149"
        st.markdown(f'<div style="background:{p_color}; padding:5px 10px; border-radius:5px; display:inline-block; font-weight:bold;">PHASE: {ecr["phase"]}</div> <span style="margin-left:10px; font-weight:bold; color:#58a6ff;">STRATEGY: {ecr["strategy"]}</span>', unsafe_allow_html=True)

        draw_sentinel_grid_ui([
            {"label": "🛡️ SENTINEL RANK", "value": f"{ecr['sentinel_rank']}/100", "delta": f"{ecr['dynamics']['rank_delta']:+.1f}"},
            {"label": "⚡ ENERGY (VCP)", "value": f"{ecr['components']['energy_vcp']}/105"},
            {"label": "💎 QUALITY (SES)", "value": f"{ecr['components']['quality_ses']}/100"},
            {"label": "📈 PROFIT FACTOR", "value": f"x{res['pf']:.2f}"}
        ])

        vcp_bd = res['vcp'].get('breakdown', {})
        draw_sentinel_grid_ui([
            {"label": "📏 Tightness", "value": f"{vcp_bd.get('tight',0)}pt"},
            {"label": "📊 Volume", "value": f"{vcp_bd.get('vol',0)}pt"},
            {"label": "📈 MA Align", "value": f"{vcp_bd.get('ma',0)}pt"},
            {"label": "🎯 Pivot Dist", "value": f"{ecr['metrics']['dist_to_pivot_pct']}%"}
        ])

        df_p = DataEngine.get_data(t_input, "1y")
        if df_p is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: ポートフォリオ (完全復旧)
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown('<div class="section-header">💼 ポートフォリオリスク管理</div>', unsafe_allow_html=True)
    portfolio_obj = load_portfolio_json()

    with st.expander("💰 資金管理", expanded=True):
        c1, c2, c3 = st.columns(3)
        input_jpy = c1.number_input("預り金 (JPY)", value=int(portfolio_obj.get("cash_jpy", 1000000)))
        input_usd = c2.number_input("USドル (USD)", value=float(portfolio_obj.get("cash_usd", 0)))
        if c3.button("更新", use_container_width=True):
            portfolio_obj["cash_jpy"] = input_jpy; portfolio_obj["cash_usd"] = input_usd
            save_portfolio_json(portfolio_obj); st.rerun()

    pos_map = portfolio_obj.get("positions", {})
    agg_usd = 0.0
    detailed = []
    for tkr, data in pos_map.items():
        c_price = DataEngine.get_current_price(tkr) or data['avg_cost']
        v_usd = c_price * data['shares']; agg_usd += v_usd
        pnl = ((c_price / data['avg_cost']) - 1) * 100
        detailed.append({"ticker": tkr, "val": v_usd, "pnl": pnl, "shares": data['shares'], "cost": data['avg_cost'], "curr": c_price})

    t_nav = (agg_usd + portfolio_obj["cash_usd"]) * fx_val + portfolio_obj["cash_jpy"]
    draw_sentinel_grid_ui([
        {"label": "💰 総資産評価額", "value": f"¥{t_nav:,.0f}"},
        {"label": "🛡️ 株式合計", "value": f"${agg_usd:,.2f}"},
        {"label": "現金(JPY)", "value": f"¥{portfolio_obj['cash_jpy']:,.0f}"},
        {"label": "為替レート", "value": f"¥{fx_val:.2f}"}
    ])

    if pos_map:
        st.markdown('<div class="section-header">📋 ポジション詳細</div>', unsafe_allow_html=True)
        for p in detailed:
            cls = "profit" if p["pnl"] >= 0 else "urgent"
            st.markdown(f'<div class="pos-card {cls}"><b>{p["ticker"]}</b> | PnL: <span class="{"pnl-pos" if p["pnl"]>=0 else "pnl-neg"}">{p["pnl"]:+.2f}%</span><br>{p["shares"]}株 @ ${p["cost"]:.2f}</div>', unsafe_allow_html=True)
            if st.button(f"削除 {p['ticker']}", key=f"del_{p['ticker']}"):
                del portfolio_obj["positions"][p['ticker']]; save_portfolio_json(portfolio_obj); st.rerun()

    with st.form("add_pos"):
        st.markdown("➕ **新規追加**")
        c1, c2, c3 = st.columns(3)
        tkr = c1.text_input("銘柄").upper()
        shr = c2.number_input("株数", min_value=1)
        cst = c3.number_input("単価", min_value=0.01)
        if st.form_submit_button("登録"):
            portfolio_obj["positions"][tkr] = {"shares": shr, "avg_cost": cst}
            save_portfolio_json(portfolio_obj); st.rerun()

st.caption("🛡️ SENTINEL PRO SYSTEM | FULL CORE INTEGRATION")

