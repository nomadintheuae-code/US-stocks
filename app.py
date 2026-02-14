"""
app.py — SENTINEL PRO Streamlit UI

[修正版]
- engines.analysis から分析クラスをインポート（一元化）
- 言語切り替え機能（日本語/英語）を追加
- 不要なスタブクラスを削除
"""

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

# 外部エンジンのインポート
from config import CONFIG
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator

warnings.filterwarnings("ignore")

# ==============================================================================
# 言語設定
# ==============================================================================

LANG = {
    "ja": {
        "title": "🛡️ SENTINEL PRO",
        "tab_scan": "📊 マーケットスキャン",
        "tab_diag": "🔍 AI診断",
        "tab_port": "💼 ポートフォリオ",
        "scan_date": "📅 スキャン日",
        "usd_jpy": "💱 USD/JPY",
        "action_list": "アクション銘柄",
        "wait_list": "ウォッチ銘柄",
        "sector_map": "🗺️ セクター別RSマップ",
        "realtime_scan": "🔍 リアルタイム定量スキャン",
        "ticker_input": "ティッカーシンボル（例：NVDA）",
        "run_quant": "🚀 定量スキャン実行",
        "add_watchlist": "⭐ ウォッチリストに追加",
        "quant_dashboard": "📊 SENTINEL定量ダッシュボード",
        "current_price": "💰 現在値",
        "vcp_score": "🎯 VCPスコア",
        "profit_factor": "📈 プロフィットファクター",
        "rs_momentum": "📏 RSモメンタム",
        "strategic_levels": "🛡️ ATR基準の戦略水準",
        "stop_loss": "ストップロス (2.0R)",
        "target1": "目標① (1.0R)",
        "target2": "目標② (2.5R)",
        "risk_unit": "リスク単価 ($)",
        "vcp_breakdown": "📐 VCPスコア内訳",
        "tightness": "収縮スコア",
        "volume": "出来高スコア",
        "ma_trend": "移動平均トレンド",
        "pivot_bonus": "ピボットボーナス",
        "ai_reasoning": "🤖 SENTINEL AI診断",
        "generate_ai": "🚀 AI診断を生成（ニュース＆ファンダメンタル）",
        "ai_key_missing": "DEEPSEEK_API_KEY が設定されていません。数値スキャンは完了しましたが、AI分析は実行できません。",
        "portfolio_risk": "💼 ポートフォリオリスク管理",
        "portfolio_empty": "ポートフォリオは空です。",
        "unrealized_jpy": "💰 含み損益 (円)",
        "assets": "📊 保有銘柄数",
        "exposure": "🛡️ エクスポージャー",
        "performance": "📈 平均パフォーマンス",
        "active_positions": "📋 保有中のポジション",
        "close_position": "決済",
        "register_new": "➕ 新規ポジション登録",
        "ticker_symbol": "ティッカーシンボル",
        "shares": "株数",
        "avg_cost": "平均取得単価",
        "add_to_portfolio": "ポートフォリオに追加",
    },
    "en": {
        "title": "🛡️ SENTINEL PRO",
        "tab_scan": "📊 MARKET SCAN",
        "tab_diag": "🔍 AI DIAGNOSIS",
        "tab_port": "💼 PORTFOLIO",
        "scan_date": "📅 Scan Date",
        "usd_jpy": "💱 USD/JPY",
        "action_list": "Action List",
        "wait_list": "Watch List",
        "sector_map": "🗺️ Sector RS Map",
        "realtime_scan": "🔍 REAL-TIME QUANTITATIVE SCAN",
        "ticker_input": "Ticker Symbol (e.g. NVDA)",
        "run_quant": "🚀 RUN QUANTITATIVE SCAN",
        "add_watchlist": "⭐ ADD TO WATCHLIST",
        "quant_dashboard": "📊 SENTINEL QUANTITATIVE DASHBOARD",
        "current_price": "💰 Current Price",
        "vcp_score": "🎯 VCP Score",
        "profit_factor": "📈 Profit Factor",
        "rs_momentum": "📏 RS Momentum",
        "strategic_levels": "🛡️ STRATEGIC LEVELS (ATR-Based)",
        "stop_loss": "Stop Loss (2.0R)",
        "target1": "Target 1 (1.0R)",
        "target2": "Target 2 (2.5R)",
        "risk_unit": "Risk Unit ($)",
        "vcp_breakdown": "📐 VCP SCORE BREAKDOWN",
        "tightness": "Tightness Score",
        "volume": "Volume Dry-up",
        "ma_trend": "MA Trend Score",
        "pivot_bonus": "Pivot Bonus",
        "ai_reasoning": "🤖 SENTINEL AI CONTEXTUAL REASONING",
        "generate_ai": "🚀 GENERATE AI DIAGNOSIS (NEWS & FUNDAMENTALS)",
        "ai_key_missing": "DEEPSEEK_API_KEY is not configured in Secrets. Numerical scan is complete, but AI analysis cannot be performed.",
        "portfolio_risk": "💼 PORTFOLIO RISK MANAGEMENT",
        "portfolio_empty": "Portfolio is currently empty.",
        "unrealized_jpy": "💰 Unrealized JPY",
        "assets": "📊 Assets",
        "exposure": "🛡️ Exposure",
        "performance": "📈 Performance",
        "active_positions": "📋 ACTIVE POSITIONS",
        "close_position": "Close",
        "register_new": "➕ REGISTER NEW POSITION",
        "ticker_symbol": "Ticker Symbol",
        "shares": "Shares",
        "avg_cost": "Avg Cost",
        "add_to_portfolio": "ADD TO PORTFOLIO",
    }
}

# ==============================================================================
# セッションステートの初期化
# ==============================================================================

def initialize_sentinel_state():
    if "target_ticker" not in st.session_state:
        st.session_state.target_ticker = ""
    if "trigger_analysis" not in st.session_state:
        st.session_state.trigger_analysis = False
    if "portfolio_dirty" not in st.session_state:
        st.session_state.portfolio_dirty = True
    if "quant_results_stored" not in st.session_state:
        st.session_state.quant_results_stored = None
    if "ai_analysis_text" not in st.session_state:
        st.session_state.ai_analysis_text = ""
    if "language" not in st.session_state:
        st.session_state.language = "ja"  # デフォルトは日本語

initialize_sentinel_state()

# ==============================================================================
# 定数・パス
# ==============================================================================

NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
CACHE_DIR = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results"); RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ==============================================================================
# ヘルパー関数
# ==============================================================================

@st.cache_data(ttl=3600)
def get_cached_usd_jpy_rate():
    try:
        return CurrencyEngine.get_usd_jpy()
    except:
        return 152.65

def load_portfolio_json() -> dict:
    if not PORTFOLIO_FILE.exists():
        return {"positions": {}, "closed": [], "meta": {"last_update": ""}}
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"positions": {}, "closed": []}

def save_portfolio_json(data: dict):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist_data() -> list:
    if not WATCHLIST_FILE.exists():
        return []
    try:
        with open(WATCHLIST_FILE, "r") as f:
            return json.load(f)
    except:
        return []

def save_watchlist_data(data: list):
    with open(WATCHLIST_FILE, "w") as f:
        json.dump(data, f)

# ==============================================================================
# UIスタイル（前回と同じ）
# ==============================================================================

GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

html, body, [class*="css"] { 
font-family: 'Rajdhani', sans-serif; 
background-color: #0d1117; 
color: #f0f6fc;
}
.block-container { 
padding-top: 0rem !important; 
padding-bottom: 2rem !important; 
}

.ui-push-buffer {
height: 65px;
width: 100%;
background: transparent;
}

.stTabs [data-baseweb="tab-list"] {
display: flex !important;
width: 100% !important;
flex-wrap: nowrap !important;
overflow-x: auto !important;
overflow-y: hidden !important;
background-color: #161b22 !important;
padding: 12px 12px 0 12px !important;
border-radius: 12px 12px 0 0 !important;
gap: 12px !important;
border-bottom: 2px solid #30363d !important;
scrollbar-width: none !important;
}
.stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none !important; }

.stTabs [data-baseweb="tab"] {
min-width: 185px !important; 
flex-shrink: 0 !important;
font-size: 1.05rem !important;
font-weight: 700 !important;
color: #8b949e !important;
padding: 22px 32px !important;
background-color: transparent !important;
border: none !important;
white-space: nowrap !important;
text-align: center !important;
}

.stTabs [aria-selected="true"] {
color: #ffffff !important;
background-color: #238636 !important;
border-radius: 12px 12px 0 0 !important;
}

.stTabs [data-baseweb="tab-highlight"] { display: none !important; }

.sentinel-grid {
display: grid;
grid-template-columns: repeat(2, 1fr);
gap: 16px;
margin: 20px 0 30px 0;
}
@media (min-width: 992px) {
.sentinel-grid { grid-template-columns: repeat(4, 1fr); }
}
.sentinel-card {
background: #161b22;
border: 1px solid #30363d;
border-radius: 12px;
padding: 24px;
box-shadow: 0 4px 25px rgba(0,0,0,0.7);
}
.sentinel-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.25em; margin-bottom: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.sentinel-value { font-size: 1.45rem; font-weight: 700; color: #f0f6fc; line-height: 1.1; }
.sentinel-delta { font-size: 0.95rem; font-weight: 600; margin-top: 12px; }

.diagnostic-panel {
background: #0d1117;
border: 1px solid #30363d;
border-radius: 12px;
padding: 28px;
margin-bottom: 26px;
}
.diag-row {
display: flex;
justify-content: space-between;
padding: 16px 0;
border-bottom: 1px solid #21262d;
}
.diag-row:last-child { border-bottom: none; }
.diag-key { color: #8b949e; font-size: 1.0rem; font-weight: 600; }
.diag-val { color: #f0f6fc; font-weight: 700; font-family: 'Share Tech Mono', monospace; font-size: 1.15rem; }

.section-header { 
font-size: 1.2rem; font-weight: 700; color: #58a6ff; 
border-bottom: 1px solid #30363d; padding-bottom: 16px; 
margin: 45px 0 28px; text-transform: uppercase; letter-spacing: 4px;
display: flex; align-items: center; gap: 14px;
}

.pos-card { 
background: #0d1117; border: 1px solid #30363d; border-radius: 18px; 
padding: 30px; margin-bottom: 24px; border-left: 12px solid #30363d; 
}
.pos-card.urgent { border-left-color: #f85149; }
.pos-card.caution { border-left-color: #d29922; }
.pos-card.profit { border-left-color: #3fb950; }
.pnl-pos { color: #3fb950; font-weight: 700; font-size: 1.3rem; }
.pnl-neg { color: #f85149; font-weight: 700; font-size: 1.3rem; }
.exit-info { font-size: 0.95rem; color: #8b949e; font-family: 'Share Tech Mono', monospace; margin-top: 18px; border-top: 1px solid #21262d; padding-top: 18px; line-height: 1.8; }

.stButton > button { min-height: 60px; border-radius: 14px; font-weight: 700; font-size: 1.1rem; }
[data-testid="stMetric"] { display: none !important; }
</style>
"""

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    html_out = '<div class="sentinel-grid">'
    for m in metrics:
        delta_s = ""
        if "delta" in m and m["delta"]:
            is_pos = "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0)
            c_code = "#3fb950" if is_pos else "#f85149"
            delta_s = f'<div class="sentinel-delta" style="color:{c_code}">{m["delta"]}</div>'
        item = (
            '<div class="sentinel-card">'
            f'<div class="sentinel-label">{m["label"]}</div>'
            f'<div class="sentinel-value">{m["value"]}</div>'
            f'{delta_s}'
            '</div>'
        )
        html_out += item
    html_out += '</div>'
    st.markdown(html_out.strip(), unsafe_allow_html=True)

# ==============================================================================
# メインUI
# ==============================================================================

st.set_page_config(
    page_title="SENTINEL PRO",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# 物理バッファとスタイル
st.markdown('<div class="ui-push-buffer"></div>', unsafe_allow_html=True)
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# サイドバー（言語選択とウォッチリスト）
with st.sidebar:
    st.markdown("### 🌐 Language")
    lang = st.selectbox("", ["日本語", "English"], index=0 if st.session_state.language == "ja" else 1)
    st.session_state.language = "ja" if lang == "日本語" else "en"
    txt = LANG[st.session_state.language]

    st.markdown(f"### {txt['title']} ウォッチリスト")
    wl_t = load_watchlist_data()
    for t_n in wl_t:
        col_n, col_d = st.columns([4, 1])
        if col_n.button(t_n, key=f"side_{t_n}", use_container_width=True):
            st.session_state.target_ticker = t_n
            st.session_state.trigger_analysis = True
            st.rerun()
        if col_d.button("×", key=f"rm_{t_n}"):
            wl_t.remove(t_n)
            save_watchlist_data(wl_t)
            st.rerun()
    st.divider()
    st.caption(f"🛡️ SENTINEL V4.5 | {NOW.strftime('%H:%M:%S')}")

fx_rate = get_cached_usd_jpy_rate()

# メインタブ
tab_scan, tab_diag, tab_port = st.tabs([txt["tab_scan"], txt["tab_diag"], txt["tab_port"]])

# ------------------------------------------------------------------------------
# タブ1: マーケットスキャン
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown(f'<div class="section-header">{txt["tab_scan"]}</div>', unsafe_allow_html=True)
    if RESULTS_DIR.exists():
        f_list = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if f_list:
            try:
                with open(f_list[0], "r", encoding="utf-8") as f:
                    s_data = json.load(f)
                s_df = pd.DataFrame(s_data.get("qualified_full", []))
                draw_sentinel_grid_ui([
                    {"label": txt["scan_date"], "value": s_data.get("date", TODAY_STR)},
                    {"label": txt["usd_jpy"], "value": f"¥{fx_rate:.2f}"},
                    {"label": txt["action_list"], "value": len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0},
                    {"label": txt["wait_list"], "value": len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0}
                ])
                if not s_df.empty:
                    st.markdown(f'<div class="section-header">{txt["sector_map"]}</div>', unsafe_allow_html=True)
                    s_df["vcp_score"] = s_df["vcp"].apply(lambda x: x.get("score", 0))
                    m_fig = px.treemap(
                        s_df,
                        path=["sector", "ticker"],
                        values="vcp_score",
                        color="rs",
                        color_continuous_scale="RdYlGn",
                        range_color=[70, 100]
                    )
                    m_fig.update_layout(template="plotly_dark", height=600, margin=dict(t=0, b=0, l=0, r=0))
                    st.plotly_chart(m_fig, use_container_width=True)
                    st.dataframe(
                        s_df[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False),
                        use_container_width=True,
                        height=500
                    )
            except Exception as e:
                st.error(f"Error loading scan results: {e}")

# ------------------------------------------------------------------------------
# タブ2: AI診断（リアルタイム定量スキャン）
# ------------------------------------------------------------------------------
with tab_diag:
    st.markdown(f'<div class="section-header">{txt["realtime_scan"]}</div>', unsafe_allow_html=True)

    t_input = st.text_input(txt["ticker_input"], value=st.session_state.target_ticker).upper().strip()

    col_q, col_w = st.columns(2)
    start_quant = col_q.button(txt["run_quant"], type="primary", use_container_width=True)
    add_watchlist = col_w.button(txt["add_watchlist"], use_container_width=True)

    if add_watchlist and t_input:
        wl = load_watchlist_data()
        if t_input not in wl:
            wl.append(t_input)
            save_watchlist_data(wl)
            st.success(f"Added {t_input}")

    if (start_quant or st.session_state.pop("trigger_analysis", False)) and t_input:
        with st.spinner(f"SENTINEL ENGINE: Scanning {t_input}..."):
            df_raw = DataEngine.get_data(t_input, "2y")
            if df_raw is not None and not df_raw.empty:
                # 一元化された分析クラスを使用
                vcp_res = VCPAnalyzer.calculate(df_raw)
                rs_val = RSAnalyzer.get_raw_score(df_raw)
                pf_val = StrategyValidator.run(df_raw)
                p_curr = DataEngine.get_current_price(t_input) or df_raw["Close"].iloc[-1]

                st.session_state.quant_results_stored = {
                    "vcp": vcp_res, "rs": rs_val, "pf": pf_val, "price": p_curr, "ticker": t_input
                }
                st.session_state.ai_analysis_text = ""
            else:
                st.error(f"Failed to fetch data for {t_input}.")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        q = st.session_state.quant_results_stored
        vcp_res, rs_val, pf_val, p_curr = q["vcp"], q["rs"], q["pf"], q["price"]

        st.markdown(f'<div class="section-header">{txt["quant_dashboard"]}</div>', unsafe_allow_html=True)
        draw_sentinel_grid_ui([
            {"label": txt["current_price"], "value": f"${p_curr:.2f}"},
            {"label": txt["vcp_score"], "value": f"{vcp_res['score']}/105"},
            {"label": txt["profit_factor"], "value": f"x{pf_val:.2f}"},
            {"label": txt["rs_momentum"], "value": f"{rs_val*100:+.1f}%"}
        ])

        d1, d2 = st.columns(2)
        with d1:
            risk = vcp_res['atr'] * CONFIG["STOP_LOSS_ATR"]
            panel_html1 = f'''
<div class="diagnostic-panel">
<b>{txt["strategic_levels"]}</b>
<div class="diag-row"><span class="diag-key">{txt["stop_loss"]}</span><span class="diag-val">${p_curr - risk:.2f}</span></div>
<div class="diag-row"><span class="diag-key">{txt["target1"]}</span><span class="diag-val">${p_curr + risk:.2f}</span></div>
<div class="diag-row"><span class="diag-key">{txt["target2"]}</span><span class="diag-val">${p_curr + risk*2.5:.2f}</span></div>
<div class="diag-row"><span class="diag-key">{txt["risk_unit"]}</span><span class="diag-val">${risk:.2f}</span></div>
</div>'''
            st.markdown(panel_html1.strip(), unsafe_allow_html=True)
        with d2:
            bd = vcp_res.get('breakdown', {})
            panel_html2 = f'''
<div class="diagnostic-panel">
<b>{txt["vcp_breakdown"]}</b>
<div class="diag-row"><span class="diag-key">{txt["tightness"]}</span><span class="diag-val">{bd.get("tight", 0)}/45</span></div>
<div class="diag-row"><span class="diag-key">{txt["volume"]}</span><span class="diag-val">{bd.get("vol", 0)}/30</span></div>
<div class="diag-row"><span class="diag-key">{txt["ma_trend"]}</span><span class="diag-val">{bd.get("ma", 0)}/30</span></div>
<div class="diag-row"><span class="diag-key">{txt["pivot_bonus"]}</span><span class="diag-val">+{bd.get("pivot", 0)}pt</span></div>
</div>'''
            st.markdown(panel_html2.strip(), unsafe_allow_html=True)

        # チャート
        df_raw = DataEngine.get_data(t_input, "2y")
        df_t = df_raw.tail(110)
        c_fig = go.Figure(data=[go.Candlestick(x=df_t.index, open=df_t['Open'], high=df_t['High'], low=df_t['Low'], close=df_t['Close'])])
        c_fig.update_layout(template="plotly_dark", height=480, margin=dict(t=0, b=0), xaxis_rangeslider_visible=False)
        st.plotly_chart(c_fig, use_container_width=True)

        # AI診断セクション
        st.markdown(f'<div class="section-header">{txt["ai_reasoning"]}</div>', unsafe_allow_html=True)
        if st.button(txt["generate_ai"], use_container_width=True):
            key = st.secrets.get("DEEPSEEK_API_KEY")
            if not key:
                st.error(txt["ai_key_missing"])
            else:
                with st.spinner(f"AI Reasoning for {t_input}..."):
                    news = NewsEngine.get(t_input)
                    fund = FundamentalEngine.get(t_input)
                    prompt = (
                        f"あなたは伝説的投資家 Mark Minervini の理論を極めた AI ファンドマネージャー「SENTINEL」です。\n"
                        f"銘柄 {t_input} の診断結果に基づき、プロの投資判断を下してください。\n\n"
                        f"━━━ 定量的データ (SENTINEL ENGINE) ━━━\n"
                        f"現在値: ${p_curr:.2f} | VCPスコア: {vcp_res['score']}/105 | PF: {pf_val:.2f} | RS: {rs_val*100:+.2f}%\n"
                        f"━━━ 外部情報 ━━━\n"
                        f"ファンダメンタル要約: {str(fund)[:1500]}\n"
                        f"ニュース: {str(news)[:2000]}\n\n"
                        f"━━━ 指示 ━━━\n1. PF数値とRS値を論拠の主軸とし、投資妙味を論評せよ。\n"
                        f"2. Buy/Watch/Avoid の判断を断行し、箇条書きで理由を示せ。\n\n※1,500文字以上の密度で記述せよ。"
                    )
                    from openai import OpenAI
                    cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                    try:
                        res_ai = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = res_ai.choices[0].message.content.replace("$", r"\$")
                    except Exception as ai_e:
                        st.error(f"AI Error: {ai_e}")

        if st.session_state.ai_analysis_text:
            st.markdown("---")
            st.markdown(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# タブ3: ポートフォリオ
# ------------------------------------------------------------------------------
with tab_port:
    st.markdown(f'<div class="section-header">{txt["portfolio_risk"]}</div>', unsafe_allow_html=True)

    p_j = load_portfolio_json()
    pos_m = p_j.get("positions", {})

    if not pos_m:
        st.info(txt["portfolio_empty"])
    else:
        stats_list = []
        for s_k, s_d in pos_m.items():
            l_p = DataEngine.get_current_price(s_k)
            if l_p:
                pnl_u = (l_p - s_d["avg_cost"]) * s_d["shares"]
                pnl_p = (l_p / s_d["avg_cost"] - 1) * 100

                atr_l = DataEngine.get_atr(s_k) or 0.0
                risk_l = atr_l * CONFIG["STOP_LOSS_ATR"]
                stop_l = max(l_p - risk_l, s_d.get("stop", 0)) if risk_l else s_d.get("stop", 0)

                stats_list.append({
                    "ticker": s_k, "shares": s_d["shares"], "avg": s_d["avg_cost"],
                    "cp": l_p, "pnl_usd": pnl_u, "pnl_pct": pnl_p,
                    "cl": "profit" if pnl_p > 0 else "urgent", "stop": stop_l
                })

        total_pnl_j = sum(s["pnl_usd"] for s in stats_list) * fx_rate
        draw_sentinel_grid_ui([
            {"label": txt["unrealized_jpy"], "value": f"¥{total_pnl_j:,.0f}"},
            {"label": txt["assets"], "value": len(stats_list)},
            {"label": txt["exposure"], "value": f"${sum(s['shares']*s['avg'] for s in stats_list):,.0f}"},
            {"label": txt["performance"], "value": f"{np.mean([s['pnl_pct'] for s in stats_list]):.2f}%" if stats_list else "0%"}
        ])

        st.markdown(f'<div class="section-header">{txt["active_positions"]}</div>', unsafe_allow_html=True)
        for s in stats_list:
            pnl_c = "pnl-pos" if s["pnl_pct"] > 0 else "pnl-neg"
            st.markdown(f'''
<div class="pos-card {s['cl']}">
<div style="display: flex; justify-content: space-between; align-items: center;">
<b>{s['ticker']}</b>
<span class="{pnl_c}">{s['pnl_pct']:+.2f}% (¥{s['pnl_usd']*fx_rate:+,.0f})</span>
</div>
<div style="font-size: 0.95rem; color: #f0f6fc; margin-top: 10px;">
{s['shares']} shares @ ${s['avg']:.2f} (Live: ${s['cp']:.2f})
</div>
<div class="exit-info">🛡️ DYNAMIC STOP: ${s['stop']:.2f}</div>
</div>''', unsafe_allow_html=True)

            if st.button(f"{txt['close_position']} {s['ticker']}", key=f"cl_{s['ticker']}"):
                del pos_m[s['ticker']]
                save_portfolio_json(p_j)
                st.rerun()

    # 新規ポジション登録
    st.markdown(f'<div class="section-header">{txt["register_new"]}</div>', unsafe_allow_html=True)
    with st.form("add_port_final"):
        c1, c2, c3 = st.columns(3)
        f_ticker = c1.text_input(txt["ticker_symbol"]).upper().strip()
        f_shares = c2.number_input(txt["shares"], min_value=1, value=10)
        f_cost   = c3.number_input(txt["avg_cost"], min_value=0.01, value=100.0)
        if st.form_submit_button(txt["add_to_portfolio"], use_container_width=True):
            if f_ticker:
                p = load_portfolio_json()
                p["positions"][f_ticker] = {"ticker": f_ticker, "shares": f_shares, "avg_cost": f_cost, "added_at": TODAY_STR}
                save_portfolio_json(p)
                st.success(f"Added {f_ticker}")
                st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO SYSTEM | CORE ENGINE: UNIFIED | UI: MULTILINGUAL")
