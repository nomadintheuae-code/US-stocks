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
NOW = datetime.datetime.now()
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

def initialize_sentinel_state():
    """セッションステートの初期化"""
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = "AAPL"
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

# ==============================================================================
# 3. データ管理ヘルパー
# ==============================================================================

def load_portfolio_json() -> dict:
    """ポートフォリオの読み込み"""
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
    """ポートフォリオの保存"""
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist_data() -> list:
    """ウォッチリストの読み込み"""
    if not WATCHLIST_FILE.exists(): return ["AAPL", "NVDA", "TSLA"]
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_watchlist_data(data: list):
    """ウォッチリストの保存"""
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

def get_market_overview_live():
    """SPY/VIXの最新状況をフェッチ"""
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
    """Sentinel Pro スタイルの 4連カードグリッド"""
    html_out = '<div class="sentinel-grid">'
    for m in metrics:
        delta_s = ""
        if "delta" in m and m["delta"]:
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
    st.markdown(html_out.strip(), unsafe_allow_html=True)

# CSSスタイル定義
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 1rem !important; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 12px; border-bottom: 2px solid #30363d; gap: 8px; }
.stTabs [data-baseweb="tab"] { color: #8b949e; border: none; font-weight: 700; min-width: 130px; border-radius: 8px; transition: 0.3s; }
.stTabs [aria-selected="true"] { color: #ffffff !important; background-color: #238636 !important; }
.sentinel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0; }
@media (min-width: 900px) { .sentinel-grid { grid-template-columns: repeat(4, 1fr); } }
.sentinel-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 22px; box-shadow: 0 4px 15px rgba(0,0,0,0.4); }
.sentinel-label { font-size: 0.75rem; color: #8b949e; text-transform: uppercase; margin-bottom: 6px; font-weight: 600; letter-spacing: 1px; }
.sentinel-value { font-size: 1.4rem; font-weight: 700; color: #f0f6fc; line-height: 1.1; }
.sentinel-delta { font-size: 0.9rem; font-weight: 600; margin-top: 6px; }
.section-header { font-size: 1.1rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin: 25px 0 15px; text-transform: uppercase; letter-spacing: 1.5px; }
.pos-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 12px; border-left: 6px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
.pnl-pos { color: #3fb950; font-weight: bold; }
.pnl-neg { color: #f85149; font-weight: bold; }
.phase-badge { padding: 4px 10px; border-radius: 6px; font-size: 0.85rem; font-weight: 700; display: inline-block; margin-right: 10px; }
</style>
"""

# ==============================================================================
# 5. アプリケーション・レイアウト
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="expanded")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# サイドバー：ウォッチリスト
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
    
    st.markdown("---")
    st.caption("⚠️ 本ツールは個人研究用です。投資判断は自己責任で行ってください。")

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs(["📊 市場概況", "🔍 ECR戦略診断", "💼 資産管理"])

# ------------------------------------------------------------------------------
# TAB 1: 市場概況 (AI分析機能付)
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown('<div class="section-header">📊 MARKET OVERVIEW</div>', unsafe_allow_html=True)
    m_info = get_market_overview_live()
    
    # 既存のスキャン結果（ある場合）を読み込み
    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            try:
                with open(files[0], "r", encoding="utf-8") as f:
                    scan_df = pd.DataFrame(json.load(f).get("qualified_full", []))
            except: pass

    # AI市場分析ボタン
    if st.button("🤖 AI 市場概況解説を実行 (SENTINEL AI)", use_container_width=True, type="primary"):
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if not api_key:
            st.error("APIキーが設定されていません。")
        else:
            with st.spinner("AIによる市場分析中..."):
                m_news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                act_n = len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0
                prompt = (
                    f"あなたは経験豊富なマクロ経済アナリストです。以下のデータに基づき、現在の米国株市場の地合いを投資家に分かりやすく、客観的に要約してください。\n"
                    f"SPY: ${m_info['spy']:.2f} ({m_info['spy_change']:+.2f}%), VIX: {m_info['vix']:.2f}\n"
                    f"現在のアクション銘柄数: {act_n}\n"
                    f"最新ニュース:\n{m_news}\n"
                )
                try:
                    cl = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI分析中にエラーが発生しました。")

    if st.session_state.ai_market_text:
        st.info(st.session_state.ai_market_text)

    # 主要指標カード
    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_info['vix']:.2f}"},
        {"label": "USD / JPY", "value": f"¥{fx_val:.2f}"},
        {"label": "ACTION TICKERS", "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown('<div class="section-header">🗺️ SECTOR RS MAP</div>', unsafe_allow_html=True)
        scan_df["vcp_score"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        treemap_fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_score", color="rs", 
                                 color_continuous_scale="RdYlGn", range_color=[70, 100])
        treemap_fig.update_layout(template="plotly_dark", height=500, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(treemap_fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: ECR戦略診断 (V2.1)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown('<div class="section-header">🔍 STRATEGY SCAN (ECR V2.1)</div>', unsafe_allow_html=True)
    t_input = st.text_input("ティッカーシンボル入力", value=st.session_state.target_ticker).upper().strip()

    c1, c2 = st.columns(2)
    if c1.button("🚀 戦略分析を実行", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df_full = DataEngine.get_data(t_input, "2y")
            if df_full is not None and not df_full.empty:
                v_res = VCPAnalyzer.calculate(df_full)
                ecr_res = ECRStrategyEngine.analyze_single(t_input, df_full)
                p_curr = DataEngine.get_current_price(t_input)
                pf_val = StrategyValidator.run(df_full)
                
                st.session_state.quant_results_stored = {
                    "vcp": v_res, "price": p_curr, "pf": pf_val, "ticker": t_input, "ecr": ecr_res
                }
                st.session_state.ai_analysis_text = ""
            else: st.error(f"{t_input} のデータが取得できません。")

    if c2.button("⭐ ウォッチリストに追加", use_container_width=True) and t_input:
        wl = load_watchlist_data()
        if t_input not in wl: 
            wl.append(t_input); save_watchlist_data(wl); st.success(f"{t_input} を追加しました")

    # 分析結果表示
    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        res_q = st.session_state.quant_results_stored
        ecr = res_q["ecr"]
        
        # フェーズ表示バッジ
        ph = ecr["phase"]
        ph_color = "#238636" if ph=="ACCUMULATION" else "#d29922" if ph=="IGNITION" else "#f85149" if ph=="RELEASE" else "#8b949e"
        st.markdown(f'''
            <div style="margin-bottom:15px;">
                <span class="phase-badge" style="background:{ph_color};">PHASE: {ph}</span>
                <span style="font-weight:bold; color:#58a6ff;">STRATEGY: {ecr["strategy"]}</span>
            </div>
        ''', unsafe_allow_html=True)

        # 1行目: メイン指標
        draw_sentinel_grid_ui([
            {"label": "🛡️ SENTINEL RANK", "value": f"{ecr['sentinel_rank']}/100", "delta": f"{ecr['dynamics']['rank_delta']:+.1f}"},
            {"label": "⚡ ENERGY (VCP)", "value": f"{ecr['components']['energy_vcp']}/105"},
            {"label": "💎 QUALITY (SES)", "value": f"{ecr['components']['quality_ses']}/100"},
            {"label": "📈 PROFIT FACTOR", "value": f"x{res_q['pf']:.2f}"}
        ])

        # 2行目: サブ指標
        vcp_bd = res_q['vcp'].get('breakdown', {})
        draw_sentinel_grid_ui([
            {"label": "📏 TIGHTNESS", "value": f"{vcp_bd.get('tight',0)} pt"},
            {"label": "📊 VOL DRY-UP", "value": f"{vcp_bd.get('vol',0)} pt"},
            {"label": "📈 RANK SLOPE (5D)", "value": f"{ecr['dynamics']['rank_5d_slope']}", "delta": "Speed"},
            {"label": "🎯 PIVOT DIST", "value": f"{ecr['metrics']['dist_to_pivot_pct']}%"}
        ])

        # チャート
        df_p = DataEngine.get_data(t_input, "1y")
        if df_p is not None:
            df_p = df_p.last("180D")
            fig = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=0,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        # 🤖 個別銘柄AI解説
        if st.button(f"🤖 AIによる {t_input} 戦略解説を表示", use_container_width=True):
            ak = st.secrets.get("DEEPSEEK_API_KEY")
            if ak:
                with st.spinner("銘柄分析中..."):
                    news_data = NewsEngine.get(t_input).get("articles", [])[:3]
                    news_str = "\n".join([f"・{a.get('title')}" for a in news_data])
                    fund = FundamentalEngine.format_for_prompt(FundamentalEngine.get(t_input), res_q['price'])
                    prompt = (
                        f"銘柄: {t_input}\nランク: {ecr['sentinel_rank']}, フェーズ: {ecr['phase']}\n"
                        f"VCPスコア: {ecr['components']['energy_vcp']}, SESスコア: {ecr['components']['quality_ses']}\n"
                        f"財務データ:\n{fund}\n最近のニュース:\n{news_str}\n\n"
                        f"上記データを踏まえ、この銘柄の現状と今後の注目点をプロの視点で簡潔に解説してください。"
                    )
                    try:
                        cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                        r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = r.choices[0].message.content.replace("$", r"\$")
                    except: st.error("AI解説の生成に失敗しました。")
        
        if st.session_state.ai_analysis_text:
            st.markdown("---")
            st.info(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# TAB 3: 資産管理 (ポートフォリオ)
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown('<div class="section-header">💼 PORTFOLIO RISK MANAGEMENT</div>', unsafe_allow_html=True)
    port = load_portfolio_json()

    with st.expander("💰 資金・口座残高の設定", expanded=False):
        c1, c2, c3 = st.columns(3)
        in_jpy = c1.number_input("国内預り金 (JPY)", value=int(port.get("cash_jpy", 1000000)), step=10000)
        in_usd = c2.number_input("外国証券用 (USD)", value=float(port.get("cash_usd", 0)), step=100.0)
        if c3.button("設定を保存", use_container_width=True):
            port["cash_jpy"] = in_jpy; port["cash_usd"] = in_usd
            save_portfolio_json(port); st.success("保存しました"); st.rerun()

    # 保有ポジション集計
    pos_map = port.get("positions", {})
    agg_usd = 0.0
    detailed = []

    for tkr, data in pos_map.items():
        c_p = DataEngine.get_current_price(tkr)
        if not c_p:
            try: c_p = yf.Ticker(tkr).fast_info.get('lastPrice')
            except: c_p = data.get('avg_cost', 0)
        
        v_usd = c_p * data['shares']
        agg_usd += v_usd
        pnl_pct = ((c_p / data['avg_cost']) - 1) * 100
        detailed.append({
            "ticker": tkr, "val": v_usd, "pnl": pnl_pct, 
            "shares": data['shares'], "cost": data['avg_cost'], "curr": c_p
        })

    t_nav = (agg_usd + port["cash_usd"]) * fx_val + port["cash_jpy"]
    
    # 資産サマリー
    draw_sentinel_grid_ui([
        {"label": "💰 TOTAL NAV (JPY)", "value": f"¥{t_nav:,.0f}"},
        {"label": "🛡️ EQUITY VALUE", "value": f"${agg_usd:,.2f}"},
        {"label": "💵 CASH (JPY/USD)", "value": f"¥{port['cash_jpy']:,.0f}", "delta": f"${port['cash_usd']:.2f}"},
        {"label": "💹 FX RATE", "value": f"¥{fx_val:.2f}"}
    ])

    # ポートフォリオAI解説
    if st.button("🛡️ AI ポートフォリオ・リスク診断", use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("リスク分析中..."):
                p_report = "\n".join([f"・{x['ticker']}: ${x['val']:.2f} (PnL: {x['pnl']:+.1f}%)" for x in detailed])
                prompt = (
                    f"あなたはリスク管理責任者です。以下のポートフォリオの現状を分析し、"
                    f"市場の地合い（VIX: {get_market_overview_live()['vix']}）を踏まえたリスクアドバイスを行ってください。\n"
                    f"総資産: ¥{t_nav:,.0f}, 現金比率: {(port['cash_jpy']+port['cash_usd']*fx_val)/t_nav*100:.1f}%\n"
                    f"保有状況:\n{p_report}"
                )
                try:
                    cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_port_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI診断に失敗しました。")
    
    if st.session_state.ai_port_text:
        st.info(st.session_state.ai_port_text)

    # ポジション一覧
    if pos_map:
        st.markdown('<div class="section-header">📋 ACTIVE POSITIONS</div>', unsafe_allow_html=True)
        for p in detailed:
            p_cls = "profit" if p["pnl"] >= 0 else "urgent"
            st.markdown(f'''
                <div class="pos-card {p_cls}">
                    <div style="display: flex; justify-content: space-between;">
                        <b>{p['ticker']}</b> 
                        <span class="{"pnl-pos" if p["pnl"]>=0 else "pnl-neg"}">{p['pnl']:+.2f}%</span>
                    </div>
                    <div style="font-size: 0.85rem; margin-top: 8px;">
                        {p['shares']} shares @ ${p['cost']:.2f} (Live: ${p['curr']:.2f}) | Value: ${p['val']:,.2f}
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            if st.button(f"ポジション削除 {p['ticker']}", key=f"del_{p['ticker']}"):
                del port["positions"][p['ticker']]; save_portfolio_json(port); st.rerun()

    # 新規追加フォーム
    with st.form("add_new_position"):
        st.markdown("➕ **新規ポジション登録**")
        cx1, cx2, cx3 = st.columns(3)
        new_tkr = cx1.text_input("銘柄コード").upper().strip()
        new_shr = cx2.number_input("株数", min_value=1)
        new_cst = cx3.number_input("取得単価 (USD)", min_value=0.01)
        if st.form_submit_button("ポートフォリオに登録"):
            if new_tkr:
                port["positions"][new_tkr] = {"shares": new_shr, "avg_cost": new_cst}
                save_portfolio_json(port); st.success(f"{new_tkr} を登録しました"); st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO SYSTEM | CORE V2.1 INTEGRATED | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

