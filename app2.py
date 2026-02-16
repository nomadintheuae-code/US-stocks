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
# 2. 定数・パス・初期設定
# ==============================================================================
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

def initialize_sentinel_state():
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = "AAPL"
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

# --- ストレージ管理 ---
def load_portfolio_json() -> dict:
    default = {"positions": {}, "cash_jpy": 1000000, "cash_usd": 0}
    if not PORTFOLIO_FILE.exists(): return default
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "cash_jpy" not in d: d["cash_jpy"] = 1000000
            if "cash_usd" not in d: d["cash_usd"] = 0
            return d
    except: return default

def save_portfolio_json(data: dict):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist_data() -> list:
    if not WATCHLIST_FILE.exists(): return ["AAPL", "NVDA", "TSLA"]
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_watchlist_data(data: list):
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

# --- 外部データフェッチ ---
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

# ==============================================================================
# 4. UIコンポーネント
# ==============================================================================

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    """HTMLグリッドUI。バグ修正版。"""
    html_out = '<div class="sentinel-grid">'
    for m in metrics:
        delta_s = ""
        if "delta" in m and m["delta"] is not None:
            d_val = m["delta"]
            is_pos = "+" in str(d_val) or (isinstance(d_val, (int, float)) and d_val > 0)
            c_code = "#3fb950" if is_pos else "#f85149"
            delta_s = f'<div class="sentinel-delta" style="color:{c_code}">{d_val}</div>'
        
        item = f'''
        <div class="sentinel-card">
            <div class="sentinel-label">{m["label"]}</div>
            <div class="sentinel-value">{m["value"]}</div>
            {delta_s}
        </div>
        '''
        html_out += item
    html_out += '</div>'
    st.markdown(html_out, unsafe_allow_html=True)

# CSS定義
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 1rem !important; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 12px; border-bottom: 2px solid #30363d; gap: 8px; }
.stTabs [data-baseweb="tab"] { color: #8b949e; border: none; font-weight: 700; min-width: 140px; border-radius: 8px; }
.stTabs [aria-selected="true"] { color: #ffffff !important; background-color: #238636 !important; }
.sentinel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0; }
@media (min-width: 900px) { .sentinel-grid { grid-template-columns: repeat(4, 1fr); } }
.sentinel-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 22px; box-shadow: 0 4px 15px rgba(0,0,0,0.5); }
.sentinel-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-bottom: 6px; font-weight: 600; letter-spacing: 1px; }
.sentinel-value { font-size: 1.4rem; font-weight: 700; color: #f0f6fc; line-height: 1.1; }
.sentinel-delta { font-size: 0.95rem; font-weight: 600; margin-top: 8px; }
.section-header { font-size: 1.1rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin: 25px 0 15px; text-transform: uppercase; letter-spacing: 2px; }
.pos-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 22px; margin-bottom: 15px; border-left: 8px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
.pnl-pos { color: #3fb950; font-weight: bold; }
.pnl-neg { color: #f85149; font-weight: bold; }
.phase-badge { padding: 4px 12px; border-radius: 6px; font-size: 0.85rem; font-weight: 700; display: inline-block; margin-right: 10px; }
</style>
"""

# ==============================================================================
# 5. アプリ・メイン
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# サイドバー
with st.sidebar:
    st.markdown("### 🛡️ WATCHLIST")
    wl_data = load_watchlist_data()
    for tkr in wl_data:
        c1, c2 = st.columns([4, 1])
        if c1.button(tkr, key=f"side_{tkr}", use_container_width=True):
            st.session_state.target_ticker = tkr
            st.rerun()
        if c2.button("×", key=f"rm_{tkr}"):
            wl_data.remove(tkr); save_watchlist_data(wl_data); st.rerun()

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs(["📊 市場概況", "🔍 ECR戦略診断", "💼 資産管理"])

# ------------------------------------------------------------------------------
# TAB 1: 市場概況
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown('<div class="section-header">📊 MARKET OVERVIEW & SCANNER</div>', unsafe_allow_html=True)
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

    # AI市場解説
    if st.button("🤖 AI 市場概況解説を実行", use_container_width=True, type="primary"):
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if api_key:
            with st.spinner("Analyzing Market..."):
                m_news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                prompt = (f"SPY: ${m_info['spy']:.2f}, VIX: {m_info['vix']:.2f}\n"
                          f"最新ニュース:\n{m_news}\n客観的市場分析を要約せよ。")
                try:
                    cl = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI Error")

    if st.session_state.ai_market_text: st.info(st.session_state.ai_market_text)

    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_info['vix']:.2f}"},
        {"label": "USD / JPY", "value": f"¥{fx_val:.2f}"},
        {"label": "ACTION銘柄数", "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown('<div class="section-header">🗺️ SECTOR RS MAP</div>', unsafe_allow_html=True)
        scan_df["vcp_score"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        treemap_fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_score", color="rs", 
                                 color_continuous_scale="RdYlGn", range_color=[70, 100])
        treemap_fig.update_layout(template="plotly_dark", height=500, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(treemap_fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: ECR戦略診断 (表示項目復元)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown('<div class="section-header">🔍 STRATEGY SCAN (ECR V2.1)</div>', unsafe_allow_html=True)
    t_input = st.text_input("ティッカー入力", value=st.session_state.target_ticker).upper().strip()

    c1, c2 = st.columns(2)
    if c1.button("🚀 分析開始", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df_full = DataEngine.get_data(t_input, "2y")
            if df_full is not None and not df_full.empty:
                ecr_res = ECRStrategyEngine.analyze_single(t_input, df_full)
                pf_val = StrategyValidator.run(df_full)
                st.session_state.quant_results_stored = {"ticker": t_input, "ecr": ecr_res, "pf": pf_val}
            else: st.error("データ取得不可")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        q = st.session_state.quant_results_stored
        ecr = q["ecr"]
        ph = ecr["phase"]
        ph_color = "#238636" if ph=="ACCUMULATION" else "#d29922" if ph=="IGNITION" else "#f85149" if ph=="RELEASE" else "#8b949e"
        
        st.markdown(f'<div style="margin-bottom:20px;"><span class="phase-badge" style="background:{ph_color};">PHASE: {ph}</span><span style="font-weight:bold; color:#58a6ff;">STRATEGY: {ecr["strategy"]}</span></div>', unsafe_allow_html=True)

        # 主要指標
        draw_sentinel_grid_ui([
            {"label": "🛡️ SENTINEL RANK", "value": f"{ecr['sentinel_rank']}/100", "delta": f"{ecr['dynamics']['rank_delta']:+.1f}"},
            {"label": "⚡ ENERGY (VCP)", "value": f"{ecr['components']['energy_vcp']}/105"},
            {"label": "💎 QUALITY (SES)", "value": f"{ecr['components']['quality_ses']}/100"},
            {"label": "📈 PROFIT FACTOR", "value": f"x{q['pf']:.2f}"}
        ])

        # VCP詳細ブレイクダウン (ここを復元)
        v_bd = ecr.get("vcp_breakdown", {})
        draw_sentinel_grid_ui([
            {"label": "📏 TIGHTNESS", "value": f"{v_bd.get('tight', 0)} pt"},
            {"label": "📊 VOL DRY-UP", "value": f"{v_bd.get('vol', 0)} pt"},
            {"label": "📈 RANK SLOPE", "value": f"{ecr['dynamics']['rank_5d_slope']}"},
            {"label": "🎯 PIVOT DIST", "value": f"{ecr['metrics']['dist_to_pivot_pct']}%"}
        ])

        # チャート
        df_p = DataEngine.get_data(t_input, "1y")
        if df_p is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        # AI解説
        if st.button(f"🤖 AIによる {t_input} 戦略診断", use_container_width=True):
            ak = st.secrets.get("DEEPSEEK_API_KEY")
            if ak:
                with st.spinner("Analyzing..."):
                    fund = FundamentalEngine.format_for_prompt(FundamentalEngine.get(t_input), 0)
                    prompt = f"銘柄: {t_input}, ランク: {ecr['sentinel_rank']}, フェーズ: {ph}\n財務データ:\n{fund}\n投資戦略を解説せよ。"
                    try:
                        cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                        r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = r.choices[0].message.content.replace("$", r"\$")
                    except: st.error("AI Error")
        
        if st.session_state.ai_analysis_text: st.info(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# TAB 3: 資産管理
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown('<div class="section-header">💼 ASSET MANAGEMENT</div>', unsafe_allow_html=True)
    port = load_portfolio_json()

    with st.expander("💰 口座設定"):
        c1, c2, c3 = st.columns(3)
        in_jpy = c1.number_input("国内預り金 (JPY)", value=int(port.get("cash_jpy", 1000000)))
        in_usd = c2.number_input("外国証券用 (USD)", value=float(port.get("cash_usd", 0)))
        if c3.button("保存", use_container_width=True):
            port["cash_jpy"] = in_jpy; port["cash_usd"] = in_usd; save_portfolio_json(port); st.rerun()

    pos_map = port.get("positions", {})
    detailed = []
    agg_usd = 0.0
    for tkr, data in pos_map.items():
        cp = DataEngine.get_current_price(tkr) or data['avg_cost']
        v = cp * data['shares']
        agg_usd += v
        pnl = ((cp / data['avg_cost']) - 1) * 100
        detailed.append({"ticker": tkr, "val": v, "pnl": pnl, "shares": data['shares'], "cost": data['avg_cost'], "curr": cp})

    t_nav = (agg_usd + port["cash_usd"]) * fx_val + port["cash_jpy"]
    draw_sentinel_grid_ui([
        {"label": "💰 TOTAL NAV", "value": f"¥{t_nav:,.0f}"},
        {"label": "🛡️ EQUITY", "value": f"${agg_usd:,.2f}"},
        {"label": "💵 CASH", "value": f"¥{port['cash_jpy']:,.0f}", "delta": f"${port['cash_usd']:.2f}"},
        {"label": "💹 FX RATE", "value": f"¥{fx_val:.2f}"}
    ])

    if st.button("🛡️ ポートフォリオAIリスク診断", use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("Analyzing Risk..."):
                p_sum = "\n".join([f"・{x['ticker']}: ${x['val']:.2f} (PnL: {x['pnl']:+.1f}%)" for x in detailed])
                prompt = f"資産総額: ¥{t_nav:,.0f}, 保有状況:\n{p_sum}\nリスク診断を行え。"
                cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                try:
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_port_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI Error")
    
    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    if pos_map:
        st.markdown('<div class="section-header">📋 ACTIVE POSITIONS</div>', unsafe_allow_html=True)
        for p in detailed:
            cls = "profit" if p["pnl"] >= 0 else "urgent"
            st.markdown(f'<div class="pos-card {cls}"><b>{p["ticker"]}</b> <span class="{"pnl-pos" if p["pnl"]>=0 else "pnl-neg"}">{p["pnl"]:+.2f}%</span><br>{p["shares"]} shares @ ${p["cost"]:.2f}</div>', unsafe_allow_html=True)
            if st.button(f"削除 {p['ticker']}", key=f"del_{p['ticker']}"):
                del port["positions"][p['ticker']]; save_portfolio_json(port); st.rerun()

    with st.form("add"):
        st.markdown("➕ **新規追加**")
        cx1, cx2, cx3 = st.columns(3)
        nt = cx1.text_input("銘柄").upper()
        ns = cx2.number_input("株数", min_value=1)
        nc = cx3.number_input("単価", min_value=0.01)
        if st.form_submit_button("登録"):
            port["positions"][nt] = {"shares": ns, "avg_cost": nc}; save_portfolio_json(port); st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

