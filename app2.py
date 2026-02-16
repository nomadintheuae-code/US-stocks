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
NOW = datetime.datetime.now()
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ==============================================================================
# 3. セッションステート & 初期化
# ==============================================================================

def initialize_sentinel_state():
    """アプリの状態を初期化（データが消えないように管理）"""
    if "target_ticker" not in st.session_state: 
        st.session_state.target_ticker = "AAPL"
    if "ai_analysis_text" not in st.session_state: 
        st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: 
        st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: 
        st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: 
        st.session_state.quant_results_stored = None

initialize_sentinel_state()

# --- データストレージヘルパー ---
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

# --- 外部データ取得ヘルパー ---
def get_market_overview_live():
    """SPY(S&P500)とVIX(恐怖指数)の現在値をフェッチ"""
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
# 4. UI スタイル & コンポーネント
# ==============================================================================

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    """Sentinel Pro スタイルの 4連カードグリッド UI"""
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

# グローバル CSS
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
# 5. アプリケーション・メインレイアウト
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
    st.caption("🛡️ SENTINEL SYSTEM V2.1")
    st.caption("Personal Analytics and BYOK Model Integration.")

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs(["📊 マーケット概況", "🔍 ECR戦略診断", "💼 資産管理"])

# ------------------------------------------------------------------------------
# TAB 1: マーケット概況 (AI解説機能付)
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown('<div class="section-header">📊 MARKET OVERVIEW & SCANNER</div>', unsafe_allow_html=True)
    m_info = get_market_overview_live()
    
    # 既存のスキャンファイルがあれば読み込み
    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            try:
                with open(files[0], "r", encoding="utf-8") as f:
                    data_json = json.load(f)
                    scan_df = pd.DataFrame(data_json.get("qualified_full", []))
            except: pass

    # 🤖 AI市場分析
    if st.button("🤖 AIによる最新市場分析 (SENTINEL MARKET EYE)", use_container_width=True, type="primary"):
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if not api_key:
            st.error("DeepSeek APIキーが設定されていません。")
        else:
            with st.spinner("AIが市場動向を解析中..."):
                m_news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                act_n = len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0
                prompt = (
                    f"あなたは経験豊富なマクロ経済アナリストです。以下のデータに基づき、現在の米国株市場の地合いと投資家へのアドバイスを教育目的で要約してください。\n"
                    f"市場状況: SPY ${m_info['spy']:.2f} ({m_info['spy_change']:+.2f}%), VIX指数: {m_info['vix']:.2f}\n"
                    f"システム検知アクション銘柄数: {act_n}\n"
                    f"最新ニュース見出し:\n{m_news}\n\n"
                    f"注意：投資判断の最終責任はユーザーにあります。客観的な分析に留めてください。"
                )
                try:
                    cl = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI分析中にエラーが発生しました。")

    if st.session_state.ai_market_text:
        st.info(st.session_state.ai_market_text)

    # 主要カード
    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_info['vix']:.2f}"},
        {"label": "USD / JPY", "value": f"¥{fx_val:.2f}"},
        {"label": "ACTION TICKERS", "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown('<div class="section-header">🗺️ SECTOR RELATIVE STRENGTH MAP</div>', unsafe_allow_html=True)
        scan_df["vcp_score"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        treemap_fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_score", color="rs", 
                                 color_continuous_scale="RdYlGn", range_color=[70, 100])
        treemap_fig.update_layout(template="plotly_dark", height=500, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(treemap_fig, use_container_width=True)

# ------------------------------------------------------------------------------
# TAB 2: ECR戦略診断 (V2.1)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown('<div class="section-header">🔍 SINGLE TICKER STRATEGY DIAGNOSTIC (ECR V2.1)</div>', unsafe_allow_html=True)
    t_input = st.text_input("分析するティッカーを入力", value=st.session_state.target_ticker).upper().strip()

    c1, c2 = st.columns(2)
    if c1.button("🚀 戦略スキャンを開始", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"{t_input} を詳細解析中..."):
            df_full = DataEngine.get_data(t_input, "2y")
            if df_full is not None and not df_full.empty:
                # 戦略エンジンの実行 (ここで確実に analyze_single を呼ぶ)
                v_res = VCPAnalyzer.calculate(df_full)
                ecr_res = ECRStrategyEngine.analyze_single(t_input, df_full)
                p_curr = DataEngine.get_current_price(t_input)
                pf_val = StrategyValidator.run(df_full)
                
                st.session_state.quant_results_stored = {
                    "vcp": v_res, "price": p_curr, "pf": pf_val, "ticker": t_input, "ecr": ecr_res
                }
                st.session_state.ai_analysis_text = ""
            else: st.error(f"{t_input} のデータ取得に失敗しました。")

    if c2.button("⭐ ウォッチリストに追加", use_container_width=True) and t_input:
        wl = load_watchlist_data()
        if t_input not in wl: 
            wl.append(t_input); save_watchlist_data(wl); st.success(f"{t_input} をリストに追加しました")

    # 結果表示
    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        res_q = st.session_state.quant_results_stored
        ecr = res_q["ecr"]
        
        # フェーズバッジ
        ph = ecr["phase"]
        ph_color = "#238636" if ph=="ACCUMULATION" else "#d29922" if ph=="IGNITION" else "#f85149" if ph=="RELEASE" else "#8b949e"
        st.markdown(f'''
            <div style="margin-bottom:20px;">
                <span class="phase-badge" style="background:{ph_color};">PHASE: {ph}</span>
                <span style="font-weight:bold; color:#58a6ff; letter-spacing:1px;">STRATEGY: {ecr["strategy"]}</span>
            </div>
        ''', unsafe_allow_html=True)

        # 1行目: 動的指標 (Dynamics)
        draw_sentinel_grid_ui([
            {"label": "🛡️ SENTINEL RANK", "value": f"{ecr['sentinel_rank']}/100", "delta": f"{ecr['dynamics']['rank_delta']:+.1f}"},
            {"label": "⚡ ENERGY (VCP)", "value": f"{ecr['components']['energy_vcp']}/105"},
            {"label": "💎 QUALITY (SES)", "value": f"{ecr['components']['quality_ses']}/100"},
            {"label": "📈 PROFIT FACTOR", "value": f"x{res_q['pf']:.2f}"}
        ])

        # 2行目: 個別クオンツ内訳
        vcp_bd = res_q['vcp'].get('breakdown', {})
        draw_sentinel_grid_ui([
            {"label": "📏 TIGHTNESS", "value": f"{vcp_bd.get('tight',0)} pt"},
            {"label": "📊 VOL DRY-UP", "value": f"{vcp_bd.get('vol',0)} pt"},
            {"label": "📈 RANK SLOPE (5D)", "value": f"{ecr['dynamics']['rank_5d_slope']}", "delta": "Speed"},
            {"label": "🎯 PIVOT DIST", "value": f"{ecr['metrics']['dist_to_pivot_pct']}%"}
        ])

        # チャート描画
        df_p = DataEngine.get_data(t_input, "1y")
        if df_p is not None:
            df_p = df_p.last("180D")
            fig = go.Figure(data=[go.Candlestick(x=df_p.index, open=df_p['Open'], high=df_p['High'], low=df_p['Low'], close=df_p['Close'])])
            fig.update_layout(template="plotly_dark", height=450, margin=dict(l=0,r=0,t=10,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        # 🤖 AI銘柄個別診断
        if st.button(f"🤖 AIによる {t_input} 個別戦略解説", use_container_width=True):
            ak = st.secrets.get("DEEPSEEK_API_KEY")
            if ak:
                with st.spinner("ファンダメンタルズとニュースを解析中..."):
                    news_data = NewsEngine.get(t_input).get("articles", [])[:3]
                    news_str = "\n".join([f"・{a.get('title')}" for a in news_data])
                    fund = FundamentalEngine.format_for_prompt(FundamentalEngine.get(t_input), res_q['price'])
                    prompt = (
                        f"銘柄: {t_input}\nシステム評価: {ecr['sentinel_rank']}/100, フェーズ: {ecr['phase']}\n"
                        f"テクニカル要因: VCP={ecr['components']['energy_vcp']}, SES={ecr['components']['quality_ses']}\n"
                        f"財務データ:\n{fund}\n最近の注目ニュース:\n{news_str}\n\n"
                        f"これらのデータから、この銘柄の現状と今後のリスク・チャンスをプロのファンドマネージャーのように簡潔に解説してください。"
                    )
                    try:
                        cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                        r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = r.choices[0].message.content.replace("$", r"\$")
                    except: st.error("AI分析の実行に失敗しました。")
        
        if st.session_state.ai_analysis_text:
            st.markdown("---")
            st.info(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# TAB 3: 資産管理 (ポートフォリオ)
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown('<div class="section-header">💼 ASSET MANAGEMENT & RISK CONTROL</div>', unsafe_allow_html=True)
    port = load_portfolio_json()

    with st.expander("💰 口座残高・通貨設定", expanded=False):
        c1, c2, c3 = st.columns(3)
        in_jpy = c1.number_input("国内預り金残高 (JPY)", value=int(port.get("cash_jpy", 1000000)), step=10000)
        in_usd = c2.number_input("外国証券用残高 (USD)", value=float(port.get("cash_usd", 0)), step=100.0)
        if c3.button("残高を保存する", use_container_width=True):
            port["cash_jpy"] = in_jpy; port["cash_usd"] = in_usd
            save_portfolio_json(port); st.success("設定を更新しました"); st.rerun()

    # 保有ポジション集計ロジック
    pos_map = port.get("positions", {})
    agg_usd_val = 0.0
    detailed_list = []

    for tkr, data in pos_map.items():
        c_p = DataEngine.get_current_price(tkr)
        if not c_p:
            try: c_p = yf.Ticker(tkr).fast_info.get('lastPrice')
            except: c_p = data.get('avg_cost', 0)
        
        val_usd = c_p * data['shares']
        agg_usd_val += val_usd
        pnl_pct = ((c_p / data['avg_cost']) - 1) * 100
        detailed_list.append({
            "ticker": tkr, "val": val_usd, "pnl": pnl_pct, 
            "shares": data['shares'], "cost": data['avg_cost'], "curr": c_p
        })

    total_nav_jpy = (agg_usd_val + port["cash_usd"]) * fx_val + port["cash_jpy"]
    
    # 資産状況サマリー
    draw_sentinel_grid_ui([
        {"label": "💰 TOTAL NAV (評価額計)", "value": f"¥{total_nav_jpy:,.0f}"},
        {"label": "🛡️ EQUITY (株式合計)", "value": f"${agg_usd_val:,.2f}"},
        {"label": "💵 CASH (JPY/USD)", "value": f"¥{port['cash_jpy']:,.0f}", "delta": f"${port['cash_usd']:.2f}"},
        {"label": "💹 FX RATE (USDJPY)", "value": f"¥{fx_val:.2f}"}
    ])

    # AI リスク診断
    if st.button("🛡️ AI ポートフォリオ・リスク診断を実行", use_container_width=True, type="primary"):
        ak = st.secrets.get("DEEPSEEK_API_KEY")
        if ak:
            with st.spinner("リスク分散状況を解析中..."):
                p_summary = "\n".join([f"・{x['ticker']}: ${x['val']:.2f} (含み損益: {x['pnl']:+.1f}%)" for x in detailed_list])
                prompt = (
                    f"あなたはリスク管理責任者です。以下のポートフォリオ状況を元に、"
                    f"現在の市場地合い（VIX指数: {get_market_overview_live()['vix']}）を考慮したリスク管理アドバイスを行ってください。\n"
                    f"総資産評価額: ¥{total_nav_jpy:,.0f}, 現金比率: {(port['cash_jpy'] + port['cash_usd'] * fx_val) / total_nav_jpy * 100:.1f}%\n"
                    f"個別保有詳細:\n{p_summary}"
                )
                try:
                    cl = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_port_text = res.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI診断中にエラーが発生しました。")
    
    if st.session_state.ai_port_text:
        st.info(st.session_state.ai_port_text)

    # ポジション詳細
    if pos_map:
        st.markdown('<div class="section-header">📋 ACTIVE POSITIONS</div>', unsafe_allow_html=True)
        for p in detailed_list:
            card_cls = "profit" if p["pnl"] >= 0 else "urgent"
            st.markdown(f'''
                <div class="pos-card {card_cls}">
                    <div style="display: flex; justify-content: space-between;">
                        <b>{p['ticker']}</b> 
                        <span class="{"pnl-pos" if p["pnl"]>=0 else "pnl-neg"}">{p['pnl']:+.2f}%</span>
                    </div>
                    <div style="font-size: 0.9rem; margin-top: 10px;">
                        {p['shares']} shares @ ${p['cost']:.2f} (Live: ${p['curr']:.2f}) | Value: ${p['val']:,.2f}
                    </div>
                </div>
            ''', unsafe_allow_html=True)
            if st.button(f"削除 {p['ticker']}", key=f"del_{p['ticker']}"):
                del port["positions"][p['ticker']]; save_portfolio_json(port); st.rerun()

    # 追加フォーム
    with st.form("add_pos_form"):
        st.markdown("➕ **保有ポジションを追加登録**")
        cx1, cx2, cx3 = st.columns(3)
        add_tkr = cx1.text_input("銘柄").upper().strip()
        add_shr = cx2.number_input("株数", min_value=1)
        add_cst = cx3.number_input("平均単価 (USD)", min_value=0.01)
        if st.form_submit_button("ポートフォリオに反映"):
            if add_tkr:
                port["positions"][add_tkr] = {"shares": add_shr, "avg_cost": add_cst}
                save_portfolio_json(port); st.success(f"{add_tkr} を登録しました"); st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO SYSTEM | CORE ENGINE V2.1 | UPDATED: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}")

