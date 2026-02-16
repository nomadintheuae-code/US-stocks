ーimport json
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
# 0. マルチ言語対応設定 (Translations)
# ==============================================================================
if "language" not in st.session_state:
    st.session_state.language = "ja"

translations = {
    "en": {
        "sidebar_watchlist": "🛡️ SENTINEL Watchlist",
        "sidebar_disclaimer": "⚠️ No investment advice. Use at your own risk.",
        "sidebar_language": "Language",
        "tab_market": "📊 Market Scan",
        "tab_ai": "🔍 ECR Diagnosis",
        "tab_portfolio": "💼 Portfolio",
        "title_market_scan": "📊 Market Scan (Market Sentiment)",
        "btn_ai_market": "🤖 AI Market Analysis (SENTINEL MARKET EYE)",
        "label_spy": "S&P 500 (SPY)",
        "label_vix": "VIX INDEX",
        "label_action": "Action Stocks",
        "section_sector_map": "🗺️ Sector RS Map",
        "title_quant_scan": "🔍 ECR Strategic Diagnostic (V2.1)",
        "label_ticker": "Ticker Symbol",
        "btn_quant_scan": "🚀 Run Strategic Scan",
        "btn_add_watchlist": "⭐ Add to Watchlist",
        "label_sentinel_rank": "🛡️ SENTINEL RANK",
        "label_energy_vcp": "⚡ ENERGY (VCP)",
        "label_quality_ses": "💎 QUALITY (SES)",
        "label_pf": "📈 PROFIT FACTOR",
        "label_tightness": "📏 Tightness",
        "label_volume": "📊 Volume",
        "label_ma": "📈 MA Align",
        "label_pivot": "🎯 Pivot Dist",
        "btn_ai_explain": "🤖 Show AI Strategy Analysis",
        "title_portfolio_risk": "💼 Portfolio Risk Management",
        "label_total_nav": "💰 Total NAV",
        "label_total_equity": "🛡️ Equity Total",
        "section_positions": "📋 Active Positions",
        "footer": "🛡️ SENTINEL PRO SYSTEM | CORE V2.1 INTEGRATED",
    },
    "ja": {
        "sidebar_watchlist": "🛡️ SENTINEL ウォッチリスト",
        "sidebar_disclaimer": "⚠️ 本アプリは投資助言ではありません。自己責任で運用してください。",
        "sidebar_language": "言語切替",
        "tab_market": "📊 市場概況",
        "tab_ai": "🔍 ECR戦略診断",
        "tab_portfolio": "💼 資産管理",
        "title_market_scan": "📊 マーケットスキャン (地合い分析)",
        "btn_ai_market": "🤖 AI市場分析 (SENTINEL MARKET EYE)",
        "label_spy": "S&P 500 (SPY)",
        "label_vix": "VIX指数",
        "label_action": "アクション銘柄",
        "section_sector_map": "🗺️ セクター別RSマップ",
        "title_quant_scan": "🔍 ECR戦略スキャン (V2.1)",
        "label_ticker": "ティッカーシンボル",
        "btn_quant_scan": "🚀 戦略分析実行",
        "btn_add_watchlist": "⭐ リストに追加",
        "label_sentinel_rank": "🛡️ SENTINEL ランク",
        "label_energy_vcp": "⚡ エネルギー (VCP)",
        "label_quality_ses": "💎 品質スコア (SES)",
        "label_pf": "📈 利益因子 (PF)",
        "label_tightness": "📏 収縮 (Tight)",
        "label_volume": "📊 出来高 (Vol)",
        "label_ma": "📈 平均線 (MA)",
        "label_pivot": "🎯 ピボット距離",
        "btn_ai_explain": "🤖 AI戦略解説を表示",
        "title_portfolio_risk": "💼 ポートフォリオリスク管理",
        "label_total_nav": "💰 総資産評価額",
        "label_total_equity": "🛡️ 米国株式合計",
        "section_positions": "📋 ポジション詳細",
        "footer": "🛡️ SENTINEL PRO SYSTEM | ECR V2.1 統合版",
    }
}

def t(key: str) -> str:
    lang = st.session_state.language
    return translations.get(lang, translations["en"]).get(key, key)

# ==============================================================================
# 1. エンジンのインポート
# ==============================================================================
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator
from engines.ecr_strategy import ECRStrategyEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. パス・データ管理
# ==============================================================================
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

def load_json(path, default):
    if not path.exists(): return default
    try:
        with open(path, "r", encoding="utf-8") as f: return json.load(f)
    except: return default

def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f: json.dump(data, f, indent=2)

def initialize_sentinel_state():
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = "AAPL"
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

# ==============================================================================
# 4. UIコンポーネント (HTML漏れ修正済)
# ==============================================================================
def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    """HTMLタグの露出を防ぐために構造化された出力を生成"""
    cols = st.columns(len(metrics))
    for i, m in enumerate(metrics):
        with cols[i]:
            delta_html = ""
            if "delta" in m and m["delta"]:
                d = str(m["delta"])
                color = "#3fb950" if "+" in d or (isinstance(m["delta"], (int, float)) and m["delta"] > 0) else "#f85149"
                delta_html = f'<div style="font-size:0.9rem; font-weight:600; color:{color}; margin-top:5px;">{d}</div>'
            
            st.markdown(f"""
                <div style="background:#161b22; border:1px solid #30363d; border-radius:12px; padding:20px; box-shadow:0 4px 10px rgba(0,0,0,0.3);">
                    <div style="font-size:0.75rem; color:#8b949e; text-transform:uppercase; font-weight:600; letter-spacing:1px;">{m['label']}</div>
                    <div style="font-size:1.4rem; font-weight:700; color:#f0f6fc; margin-top:8px; line-height:1;">{m['value']}</div>
                    {delta_html}
                </div>
            """, unsafe_allow_html=True)

GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 12px; border-bottom: 2px solid #30363d; }
.stTabs [aria-selected="true"] { background-color: #238636 !important; border-radius: 8px; }
.section-header { font-size: 1.1rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 8px; margin: 25px 0 15px; text-transform: uppercase; }
.pos-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 12px; border-left: 8px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
</style>
"""

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# --- サイドバー ---
with st.sidebar:
    st.session_state.language = st.selectbox(t("sidebar_language"), ["ja", "en"], index=0 if st.session_state.language == "ja" else 1)
    st.markdown(f"### {t('sidebar_watchlist')}")
    wl = load_json(WATCHLIST_FILE, ["AAPL", "NVDA", "TSLA", "WDC", "GLW"])
    for tkr in wl:
        c1, c2 = st.columns([4, 1])
        if c1.button(tkr, key=f"side_{tkr}", use_container_width=True):
            st.session_state.target_ticker = tkr
            st.rerun()
        if c2.button("×", key=f"rm_{tkr}"):
            wl.remove(tkr); save_json(WATCHLIST_FILE, wl); st.rerun()
    st.divider()
    st.caption(t("sidebar_disclaimer"))

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs([t("tab_market"), t("tab_ai"), t("tab_portfolio")])

# ------------------------------------------------------------------------------
# TAB 1: 市場概況
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown(f'<div class="section-header">{t("title_market_scan")}</div>', unsafe_allow_html=True)
    try:
        spy_t = yf.Ticker("SPY").history(period="3d")
        vix_v = yf.Ticker("^VIX").history(period="1d")["Close"].iloc[-1]
        spy_p = spy_t["Close"].iloc[-1]
        spy_c = (spy_p / spy_t["Close"].iloc[-2] - 1) * 100
    except: spy_p, spy_c, vix_v = 0, 0, 0

    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            with open(files[0], "r", encoding="utf-8") as f:
                scan_df = pd.DataFrame(json.load(f).get("qualified_full", []))

    if st.button(t("btn_ai_market"), use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("Analyzing..."):
                news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                prompt = f"SPY: ${spy_p:.2f} ({spy_c:+.2f}%), VIX: {vix_v:.2f}\nNews: {news}\n地合いを解説せよ。"
                cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")

    if st.session_state.ai_market_text: st.info(st.session_state.ai_market_text)

    draw_sentinel_grid_ui([
        {"label": t("label_spy"), "value": f"${spy_p:.2f}", "delta": f"{spy_c:+.2f}%"},
        {"label": t("label_vix"), "value": f"{vix_v:.2f}"},
        {"label": "USD / JPY", "value": f"¥{fx_val:.2f}"},
        {"label": t("label_action"), "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown(f'<div class="section-header">{t("section_sector_map")}</div>', unsafe_allow_html=True)
        scan_df["vcp_val"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_val", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        fig.update_layout(template="plotly_dark", height=500, margin=dict(t=0,b=0,l=0,r=0))
        st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: ECR戦略診断 (VCP内訳復元)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown(f'<div class="section-header">{t("title_quant_scan")}</div>', unsafe_allow_html=True)
    t_input = st.text_input(t("label_ticker"), value=st.session_state.target_ticker).upper().strip()

    c1, c2 = st.columns(2)
    if c1.button(t("btn_quant_scan"), type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df = DataEngine.get_data(t_input, "2y")
            if df is not None:
                ecr = ECRStrategyEngine.analyze_single(t_input, df)
                pf = StrategyValidator.run(df)
                st.session_state.quant_results_stored = {"ticker": t_input, "ecr": ecr, "pf": pf, "price": DataEngine.get_current_price(t_input)}
            else: st.error(t("error_data_fetch", t_input))
    
    if c2.button(t("btn_add_watchlist"), use_container_width=True) and t_input:
        wl = load_json(WATCHLIST_FILE, []); wl.append(t_input); save_json(WATCHLIST_FILE, list(set(wl))); st.success(f"{t_input} Added")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        q = st.session_state.quant_results_stored
        ecr = q["ecr"]
        
        # フェーズ表示
        p_color = {"ACCUMULATION": "#238636", "IGNITION": "#d29922", "RELEASE": "#f85149"}.get(ecr["phase"], "#8b949e")
        st.markdown(f'<div style="background:{p_color}; padding:8px 15px; border-radius:6px; display:inline-block; font-weight:700; margin-bottom:20px;">PHASE: {ecr["phase"]} | STRATEGY: {ecr["strategy"]}</div>', unsafe_allow_html=True)

        # 主要カード
        draw_sentinel_grid_ui([
            {"label": t("label_sentinel_rank"), "value": f"{ecr['sentinel_rank']}/100", "delta": f"{ecr['dynamics']['rank_delta']:+.1f}"},
            {"label": t("label_energy_vcp"), "value": f"{ecr['components']['energy_vcp']}/105"},
            {"label": t("label_quality_ses"), "value": f"{ecr['components']['quality_ses']}/100"},
            {"label": t("label_pf"), "value": f"x{q['pf']:.2f}"}
        ])

        # VCP詳細内訳 (復元)
        v_bd = ecr.get("vcp_breakdown", {})
        draw_sentinel_grid_ui([
            {"label": t("label_tightness"), "value": f"{v_bd.get('tight', 0)}pt"},
            {"label": t("label_volume"), "value": f"{v_bd.get('vol', 0)}pt"},
            {"label": t("label_ma"), "value": f"{v_bd.get('ma', 0)}pt"},
            {"label": t("label_pivot"), "value": f"{ecr['metrics']['dist_to_pivot_pct']}%"}
        ])

        # チャート
        df_p = DataEngine.get_data(t_input, "1y")
        if df_p is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        if st.button(t("btn_ai_explain"), use_container_width=True):
            ak = st.secrets.get("DEEPSEEK_API_KEY")
            if ak:
                with st.spinner("Analyzing..."):
                    fund = FundamentalEngine.format_for_prompt(FundamentalEngine.get(t_input), q["price"])
                    news = NewsEngine.format_for_prompt(NewsEngine.get(t_input))
                    prompt = f"Ticker: {t_input}\nRank: {ecr['sentinel_rank']}\nFundamentals: {fund}\nNews: {news}\n投資戦略を解説せよ。"
                    cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role":"user","content":prompt}])
                    st.session_state.ai_analysis_text = res.choices[0].message.content.replace("$", r"\$")

    if st.session_state.ai_analysis_text: st.info(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# TAB 3: ポートフォリオ
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown(f'<div class="section-header">{t("title_portfolio_risk")}</div>', unsafe_allow_html=True)
    p_data = load_json(PORTFOLIO_FILE, {"positions": {}, "cash_jpy": 1000000, "cash_usd": 0})

    with st.expander("💰 CASH MANAGEMENT"):
        c1, c2, c3 = st.columns(3)
        in_j = c1.number_input("JPY", value=int(p_data["cash_jpy"]), step=1000)
        in_u = c2.number_input("USD", value=float(p_data["cash_usd"]), step=100.0)
        if c3.button("SAVE", use_container_width=True):
            p_data["cash_jpy"] = in_j; p_data["cash_usd"] = in_u; save_json(PORTFOLIO_FILE, p_data); st.rerun()

    pos_map = p_data.get("positions", {})
    detailed = []
    agg_usd = 0.0
    for tkr, data in pos_map.items():
        cp = DataEngine.get_current_price(tkr) or data['avg_cost']
        v = cp * data['shares']; agg_usd += v
        pnl = ((cp / data['avg_cost']) - 1) * 100
        detailed.append({"ticker": tkr, "val": v, "pnl": pnl, "shares": data['shares'], "cost": data['avg_cost']})

    t_nav = (agg_usd + p_data["cash_usd"]) * fx_val + p_data["cash_jpy"]
    draw_sentinel_grid_ui([
        {"label": t("label_total_nav"), "value": f"¥{t_nav:,.0f}"},
        {"label": t("label_total_equity"), "value": f"${agg_usd:,.2f}"},
        {"label": "JPY CASH", "value": f"¥{p_data['cash_jpy']:,.0f}"},
        {"label": "FX RATE", "value": f"¥{fx_val:.2f}"}
    ])

    if st.button(t("btn_ai_portfolio"), use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("Analyzing..."):
                rep = "\n".join([f"- {x['ticker']}: ${x['val']:.2f} ({x['pnl']:+.1f}%)" for x in detailed])
                prompt = f"NAV: ¥{t_nav:,.0f}\nPositions:\n{rep}\nリスク診断を行え。"
                cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role":"user","content":prompt}])
                st.session_state.ai_port_text = res.choices[0].message.content.replace("$", r"\$")

    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    if pos_map:
        st.markdown(f'<div class="section-header">{t("section_positions")}</div>', unsafe_allow_html=True)
        for p in detailed:
            cls = "profit" if p["pnl"] >= 0 else "urgent"
            st.markdown(f'<div class="pos-card {cls}"><b>{p["ticker"]}</b> <span class="{"pnl-pos" if p["pnl"]>=0 else "pnl-neg"}">{p["pnl"]:+.2f}%</span><br>{p["shares"]} shares @ ${p["cost"]:.2f}</div>', unsafe_allow_html=True)
            if st.button(f"DEL {p['ticker']}", key=f"del_{p['ticker']}"):
                del p_data["positions"][p['ticker']]; save_json(PORTFOLIO_FILE, p_data); st.rerun()

    with st.form("add"):
        st.markdown("➕ **ADD POSITION**")
        c1, c2, c3 = st.columns(3)
        nt = c1.text_input("Ticker").upper()
        ns = c2.number_input("Shares", min_value=1)
        nc = c3.number_input("Price", min_value=0.01)
        if st.form_submit_button("ADD"):
            p_data["positions"][nt] = {"shares": ns, "avg_cost": nc}; save_json(PORTFOLIO_FILE, p_data); st.rerun()

st.divider()
st.caption(t("footer"))

