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
# 新戦略エンジンを追加
from engines.ecr_strategy import ECRStrategyEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. 定数・パスの定義
# ==============================================================================
NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
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
    """ポートフォリオ読込"""
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
    """ポートフォリオ保存"""
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
    """SPYの最新価格をフェッチ"""
    try:
        spy_t = yf.Ticker("SPY")
        spy_p = spy_t.fast_info.get('lastPrice', 0)
        vix_t = yf.Ticker("^VIX")
        vix_p = vix_t.fast_info.get('lastPrice', 0)
        return {"spy": spy_p, "spy_change": 0.0, "vix": vix_p}
    except:
        return {"spy": 0, "spy_change": 0, "vix": 0}

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    """Sentinel Pro スタイル UI"""
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
# 4. UI スタイル定義
# ==============================================================================
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 0rem !important; }
.ui-push-buffer { height: 60px; width: 100%; }
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

# ==============================================================================
# 5. メイン UI 描画
# ==============================================================================
st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown('<div class="ui-push-buffer"></div>', unsafe_allow_html=True)
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# --- サイドバー ---
with st.sidebar:
    st.markdown(f"### 🛡️ SENTINEL ウォッチリスト")
    wl_data = load_watchlist_data()
    for ticker_name in wl_data:
        col_name, col_del = st.columns([4, 1])
        if col_name.button(ticker_name, key=f"side_{ticker_name}", use_container_width=True):
            st.session_state.target_ticker = ticker_name
            st.rerun()
        if col_del.button("×", key=f"rm_{ticker_name}"):
            wl_data.remove(ticker_name); save_watchlist_data(wl_data); st.rerun()

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs(["📊 マーケットスキャン", "🔍 戦略診断(ECR)", "💼 ポートフォリオ"])

# ------------------------------------------------------------------------------
# TAB 1: マーケットスキャン (オリジナルそのまま)
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown(f'<div class="section-header">📊 マーケットスキャン (地合い分析)</div>', unsafe_allow_html=True)
    m_info = get_market_overview_live()
    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            try:
                with open(files[0], "r", encoding="utf-8") as f: data_json = json.load(f)
                scan_df = pd.DataFrame(data_json.get("qualified_full", []))
            except: pass

    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_info['vix']:.2f}"},
        {"label": "アクション銘柄", "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0},
        {"label": "ウォッチ銘柄", "value": len(scan_df[scan_df["status"]=="WAIT"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown(f'<div class="section-header">🗺️ セクター別RSマップ</div>', unsafe_allow_html=True)
        scan_df["vcp_score"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        treemap_fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        treemap_fig.update_layout(template="plotly_dark", height=600, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(treemap_fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: 戦略診断 (ECR統合・比較用)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown(f'<div class="section-header">🔍 リアルタイムECRスキャン (V3.0)</div>', unsafe_allow_html=True)
    t_input = st.text_input("ティッカーシンボル", value=st.session_state.target_ticker).upper().strip()

    col_a, col_b = st.columns(2)
    if col_a.button("🚀 戦略スキャン実行", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df_full = DataEngine.get_data(t_input, "2y")
            if df_full is not None and not df_full.empty:
                # 既存・新規全てのロジックを計算
                v_res = VCPAnalyzer.calculate(df_full)
                rs_v = RSAnalyzer.get_raw_score(df_full)
                pf_v = StrategyValidator.run(df_full)
                p_c = DataEngine.get_current_price(t_input)
                ecr_res = ECRStrategyEngine.analyze_single(t_input, df_full)
                
                st.session_state.quant_results_stored = {
                    "vcp": v_res, "rs": rs_v, "pf": pf_v, "price": p_c, 
                    "ticker": t_input, "ecr": ecr_res
                }
            else: st.error(f"{t_input} データ取得不可")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        res_q = st.session_state.quant_results_stored
        ecr = res_q.get("ecr", {})
        
        # フェーズ表示
        phase_color = "#238636" if ecr["phase"] == "ACCUMULATION" else "#d29922" if ecr["phase"] == "IGNITION" else "#f85149"
        st.markdown(f'<div style="background:{phase_color}; padding:5px 10px; border-radius:5px; display:inline-block; font-weight:bold; margin-bottom:10px;">PHASE: {ecr["phase"]}</div><div style="display:inline-block; margin-left:10px; font-weight:bold; color:#58a6ff;">STRATEGY: {ecr["strategy"]}</div>', unsafe_allow_html=True)

        # 1行目: 新戦略メイン指標
        draw_sentinel_grid_ui([
            {"label": "🛡️ SENTINEL RANK", "value": f"{ecr.get('sentinel_rank', 0)}/100"},
            {"label": "⚡ ENERGY (VCP)", "value": f"{ecr.get('components', {}).get('vcp', 0)}/105"},
            {"label": "💎 QUALITY (SES)", "value": f"{ecr.get('components', {}).get('ses', 0)}/100"},
            {"label": "📈 PROFIT FACTOR", "value": f"x{res_q['pf']:.2f}"}
        ])

        # 2行目: VCP詳細 (数値比較用)
        vcp_bd = res_q['vcp'].get('breakdown', {})
        draw_sentinel_grid_ui([
            {"label": "📏 Tightness", "value": f"{vcp_bd.get('tight',0)}点"},
            {"label": "📊 Volume", "value": f"{vcp_bd.get('vol',0)}点"},
            {"label": "📈 MA", "value": f"{vcp_bd.get('ma',0)}点"},
            {"label": "🎯 Pivot", "value": f"{vcp_bd.get('pivot',0)}点"},
        ])

        # チャート
        df_plot = DataEngine.get_data(t_input, "1y")
        if df_plot is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 3: ポートフォリオ (完全復元版)
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown(f'<div class="section-header">💼 ポートフォリオリスク管理</div>', unsafe_allow_html=True)
    portfolio_obj = load_portfolio_json()

    with st.expander("💰 資金管理 (口座残高設定)", expanded=True):
        col_j, col_u, col_btn = st.columns(3)
        current_jpy_cash = portfolio_obj.get("cash_jpy", 1000000)
        current_usd_cash = portfolio_obj.get("cash_usd", 0)
        input_jpy = col_j.number_input("預り金 (JPY)", value=int(current_jpy_cash), step=1000)
        input_usd = col_u.number_input("USドル (USD)", value=float(current_usd_cash), step=100.0)
        if col_btn.button("残高を更新して保存", use_container_width=True):
            portfolio_obj["cash_jpy"] = input_jpy; portfolio_obj["cash_usd"] = input_usd
            save_portfolio_json(portfolio_obj); st.success("更新完了"); st.rerun()

    # ポジション集計ロジック
    positions_map = portfolio_obj.get("positions", {})
    agg_stock_usd = 0.0
    detailed_positions = []

    for tkr, data in positions_map.items():
        f_info = FundamentalEngine.get(tkr)
        s_name = f_info.get("sector", "Unknown")
        i_name = f_info.get("industry", "Unknown")
        c_price = DataEngine.get_current_price(tkr)
        if not c_price:
            try: c_price = yf.Ticker(tkr).fast_info.get('lastPrice')
            except: c_price = data.get('avg_cost', 0)

        v_usd = c_price * data['shares']
        agg_stock_usd += v_usd
        p_pct = ((c_price / data['avg_cost']) - 1) * 100 if data['avg_cost'] > 0 else 0

        detailed_positions.append({
            "ticker": tkr, "sector": s_name, "industry": i_name,
            "val": v_usd, "pnl": p_pct, "shares": data['shares'], "cost": data['avg_cost'], "curr": c_price
        })

    total_stock_jpy = agg_stock_usd * fx_val
    total_cash_usd_jpy = portfolio_obj["cash_usd"] * fx_val
    total_nav_jpy = total_stock_jpy + portfolio_obj["cash_jpy"] + total_cash_usd_jpy

    draw_sentinel_grid_ui([
        {"label": "💰 総資産評価額", "value": f"¥{total_nav_jpy:,.0f}"},
        {"label": "🛡️ 米国株式合計", "value": f"¥{total_stock_jpy:,.0f}", "delta": f"(${agg_stock_usd:,.2f})"},
        {"label": "預り金 (JPY)", "value": f"¥{portfolio_obj['cash_jpy']:,.0f}"},
        {"label": "USドル (USD)", "value": f"¥{total_cash_usd_jpy:,.0f}", "delta": f"(${portfolio_obj['cash_usd']:.2f})"}
    ])

    if st.button("🛡️ AIポートフォリオ解説", use_container_width=True, type="primary"):
        guard_key = st.secrets.get("DEEPSEEK_API_KEY")
        if guard_key:
            with st.spinner("AIがポートフォリオを分析しています..."):
                m_stat = get_market_overview_live()
                p_report = "\n".join([f"- {x['ticker']} [{x['sector']}]: ${x['val']:.2f} (PnL: {x['pnl']:+.1f}%)" for x in detailed_positions])
                prompt_guard = (
                    f"あなたはリスク管理アシスタントです。以下のポートフォリオ情報を元に、客観的なリスク指標を解説してください。\n"
                    f"総資産: ¥{total_nav_jpy:,.0f}, 保有詳細:\n{p_report}\n"
                )
                cl_guard = OpenAI(api_key=guard_key, base_url="https://api.deepseek.com")
                try:
                    res_guard = cl_guard.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt_guard}])
                    st.session_state.ai_port_text = res_guard.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI Error")

    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    # ポジション詳細表示
    if positions_map:
        st.markdown(f'<div class="section-header">📋 ポジション詳細</div>', unsafe_allow_html=True)
        for pos in detailed_positions:
            status_cls = "profit" if pos["pnl"] >= 0 else "urgent"
            pnl_color = "pnl-pos" if pos["pnl"] >= 0 else "pnl-neg"
            st.markdown(f'''<div class="pos-card {status_cls}">
<div style="display: flex; justify-content: space-between;"><b>{pos['ticker']}</b> <span class="{pnl_color}">{pos['pnl']:+.2f}%</span></div>
<div style="font-size: 0.9rem; color: #58a6ff; margin-top: 2px;">{pos['sector']} / {pos['industry']}</div>
<div style="font-size: 0.9rem; margin-top: 8px;">{pos['shares']} shares @ ${pos['cost']:.2f} (Live: ${pos['curr']:.2f})</div>
<div style="font-size: 0.9rem; color: #8b949e; margin-top: 5px;">評価額: ¥{pos['val']*fx_val:,.0f} (${pos['val']:.2f})</div>
</div>''', unsafe_allow_html=True)
            if st.button(f"削除 {pos['ticker']}", key=f"cl_{pos['ticker']}"):
                del portfolio_obj["positions"][pos['ticker']]; save_portfolio_json(portfolio_obj); st.rerun()

    # 新規登録
    with st.form("add_new_pos"):
        st.markdown("➕ **新規ポジション登録**")
        c1, c2, c3 = st.columns(3)
        f_tkr = c1.text_input("銘柄コード").upper().strip()
        f_shr = c2.number_input("株数", min_value=1)
        f_cst = c3.number_input("取得単価", min_value=0.01)
        if st.form_submit_button("登録") and f_tkr:
            portfolio_obj["positions"][f_tkr] = {"shares": f_shr, "avg_cost": f_cst}
            save_portfolio_json(portfolio_obj); st.success(f"{f_tkr} 登録完了"); st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO SYSTEM | ECR STRATEGY V3.0")

