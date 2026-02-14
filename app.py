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
# 0. マルチ言語対応のための設定
# ==============================================================================
# 言語選択をセッション状態で管理
if "language" not in st.session_state:
    st.session_state.language = "en"  # デフォルト: 英語

# 翻訳辞書
translations = {
    "en": {
        # サイドバー
        "sidebar_watchlist": "🛡️ SENTINEL Watchlist",
        "sidebar_disclaimer": "⚠️ This app does not provide investment advice. All investment decisions are your own responsibility. Data is for informational purposes only.",
        "sidebar_language": "Language / 言語",

        # タブ
        "tab_market": "📊 Market Scan",
        "tab_ai": "🔍 AI Diagnosis",
        "tab_portfolio": "💼 Portfolio",

        # マーケットスキャンタブ
        "title_market_scan": "📊 Market Scan (Market Sentiment)",
        "btn_ai_market": "🤖 AI Market Analysis (SENTINEL MARKET EYE)",
        "ai_disclaimer": "\n\n※This analysis is AI-generated reference information. Please make investment decisions at your own risk.",
        "label_spy": "S&P 500 (SPY)",
        "label_vix": "VIX INDEX",
        "label_action": "Action Stocks",
        "label_watch": "Watch Stocks",
        "section_sector_map": "🗺️ Sector RS Map",
        "section_scan_list": "📋 Scanned Stocks Detail List",
        "error_api_key": "API Key is not set.",
        "error_ai": "AI Error",

        # AI診断タブ
        "title_quant_scan": "🔍 Real-time Quantitative Scan",
        "label_ticker": "Ticker Symbol",
        "btn_quant_scan": "🚀 Run Quantitative Scan",
        "btn_add_watchlist": "⭐ Add to Watchlist",
        "label_current_price": "💰 Current Price",
        "label_vcp_score": "🎯 VCP Score",
        "label_pf": "📈 PF",
        "label_rs_momentum": "📏 RS Momentum",
        "btn_ai_explain": "🤖 Show AI Explanation",
        "ai_explain_disclaimer": "\n\n※This explanation is AI-generated reference information and not investment advice.",
        "error_data_fetch": "{} Data could not be retrieved.",
        "success_added": "Added {}",

        # ポートフォリオタブ
        "title_portfolio_risk": "💼 Portfolio Risk Management",
        "expander_cash": "💰 Cash Management (Account Balance)",
        "label_jpy_cash": "Cash (JPY)",
        "label_usd_cash": "US Dollar (USD)",
        "btn_update_balance": "Update and Save Balance",
        "success_balance_updated": "Balance updated",
        "label_total_nav": "💰 Total NAV",
        "label_total_equity": "🛡️ Total US Stocks",
        "label_jpy_cash_short": "Cash (JPY)",
        "label_usd_cash_short": "US Dollar (USD)",
        "btn_ai_portfolio": "🛡️ AI Portfolio Analysis",
        "ai_portfolio_disclaimer": "\n\n※This explanation is AI-generated reference information and not investment advice.",
        "section_positions": "📋 Position Details",
        "form_add_position": "➕ **Add New Position**",
        "label_ticker_code": "Ticker Code",
        "label_shares": "Shares",
        "label_avg_cost": "Avg Cost",
        "btn_register": "Register",
        "success_registered": "{} registered successfully",
        "footer": "🛡️ SENTINEL PRO SYSTEM | FULL CORE INTEGRATION | V7.6",
    },
    "ja": {
        # サイドバー
        "sidebar_watchlist": "🛡️ SENTINEL ウォッチリスト",
        "sidebar_disclaimer": "⚠️ 本アプリは投資助言を提供するものではありません。全ての投資判断は自己責任で行ってください。データは情報提供のみを目的としています。",
        "sidebar_language": "言語 / Language",

        # タブ
        "tab_market": "📊 マーケットスキャン",
        "tab_ai": "🔍 AI診断",
        "tab_portfolio": "💼 ポートフォリオ",

        # マーケットスキャンタブ
        "title_market_scan": "📊 マーケットスキャン (地合い分析)",
        "btn_ai_market": "🤖 AI市場分析 (SENTINEL MARKET EYE)",
        "ai_disclaimer": "\n\n※この分析はAIによる参考情報です。投資判断はご自身の責任で行ってください。",
        "label_spy": "S&P 500 (SPY)",
        "label_vix": "VIX指数",
        "label_action": "アクション銘柄",
        "label_watch": "ウォッチ銘柄",
        "section_sector_map": "🗺️ セクター別RSマップ",
        "section_scan_list": "📋 スキャン銘柄詳細リスト",
        "error_api_key": "APIキーが設定されていません。",
        "error_ai": "AIエラー",

        # AI診断タブ
        "title_quant_scan": "🔍 リアルタイム定量スキャン",
        "label_ticker": "ティッカーシンボル",
        "btn_quant_scan": "🚀 定量スキャン実行",
        "btn_add_watchlist": "⭐ ウォッチリストに追加",
        "label_current_price": "💰 現在値",
        "label_vcp_score": "🎯 VCPスコア",
        "label_pf": "📈 PF",
        "label_rs_momentum": "📏 RSモメンタム",
        "btn_ai_explain": "🤖 AI解説を表示",
        "ai_explain_disclaimer": "\n\n※この解説はAIによる参考情報であり、投資助言ではありません。",
        "error_data_fetch": "{} のデータを取得できませんでした。",
        "success_added": "{} を追加しました",

        # ポートフォリオタブ
        "title_portfolio_risk": "💼 ポートフォリオリスク管理",
        "expander_cash": "💰 資金管理 (口座残高設定)",
        "label_jpy_cash": "預り金 (JPY)",
        "label_usd_cash": "USドル (USD)",
        "btn_update_balance": "残高を更新して保存",
        "success_balance_updated": "残高を更新しました",
        "label_total_nav": "💰 総資産評価額",
        "label_total_equity": "🛡️ 米国株式合計",
        "label_jpy_cash_short": "預り金 (JPY)",
        "label_usd_cash_short": "USドル (USD)",
        "btn_ai_portfolio": "🛡️ AIポートフォリオ解説",
        "ai_portfolio_disclaimer": "\n\n※この解説はAIによる参考情報であり、投資助言ではありません。",
        "section_positions": "📋 ポジション詳細",
        "form_add_position": "➕ **新規ポジション登録**",
        "label_ticker_code": "銘柄コード",
        "label_shares": "株数",
        "label_avg_cost": "取得単価",
        "btn_register": "登録",
        "success_registered": "{} を登録しました",
        "footer": "🛡️ SENTINEL PRO SYSTEM | FULL CORE INTEGRATION | V7.6",
    }
}

def t(key: str, **kwargs) -> str:
    """現在の言語に基づいて翻訳された文字列を返す。必要に応じてフォーマット変数を埋め込む。"""
    lang = st.session_state.language
    text = translations.get(lang, translations["en"]).get(key, key)
    if kwargs:
        text = text.format(**kwargs)
    return text

# ==============================================================================
# 1. エンジンのインポート (貴殿の環境構成に準拠)
# ==============================================================================
try:
    from config import CONFIG
except ImportError:
    CONFIG = {"STOP_LOSS_ATR": 2.0, "TARGET_R": 2.5}

from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator

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
    """ポートフォリオ読込。デフォルト現金を 1,000,000円 に設定"""
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
    """SPYの最新価格を強制フェッチ (異常値 $681 回避用)"""
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
    """Sentinel Pro スタイルの 4連カード UI"""
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
.diagnostic-panel { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
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

# --- サイドバー (言語切替 + 免責事項 + ウォッチリスト) ---
with st.sidebar:
    # 言語切替
    lang_options = {"en": "English", "ja": "日本語"}
    selected_lang = st.selectbox(
        t("sidebar_language"),
        options=list(lang_options.keys()),
        format_func=lambda x: lang_options[x],
        index=0 if st.session_state.language == "en" else 1
    )
    if selected_lang != st.session_state.language:
        st.session_state.language = selected_lang
        st.rerun()

    st.markdown(f"### {t('sidebar_watchlist')}")
    wl_data = load_watchlist_data()
    for ticker_name in wl_data:
        col_name, col_del = st.columns([4, 1])
        if col_name.button(ticker_name, key=f"side_{ticker_name}", use_container_width=True):
            st.session_state.target_ticker = ticker_name
            st.rerun()
        if col_del.button("×", key=f"rm_{ticker_name}"):
            wl_data.remove(ticker_name); save_watchlist_data(wl_data); st.rerun()

    st.sidebar.markdown("---")
    st.sidebar.caption(t("sidebar_disclaimer"))

fx_val = CurrencyEngine.get_usd_jpy()
tab_1, tab_2, tab_3 = st.tabs([t("tab_market"), t("tab_ai"), t("tab_portfolio")])

# ------------------------------------------------------------------------------
# TAB 1: マーケットスキャン
# ------------------------------------------------------------------------------
with tab_1:
    st.markdown(f'<div class="section-header">{t("title_market_scan")}</div>', unsafe_allow_html=True)
    m_info = get_market_overview_live()

    scan_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            try:
                with open(files[0], "r", encoding="utf-8") as f: data_json = json.load(f)
                scan_df = pd.DataFrame(data_json.get("qualified_full", []))
            except: pass

    # AI市場分析
    if st.button(t("btn_ai_market"), use_container_width=True, type="primary"):
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if not api_key:
            st.error(t("error_api_key"))
        else:
            with st.spinner("Analyzing Market conditions..."):
                m_news = NewsEngine.format_for_prompt(NewsEngine.get_general_market())
                act_n = len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0
                prompt = (
                    f"あなたは金融データのアシスタントです。以下の市場データに基づき、"
                    f"投資家が考慮すべき客観的なポイントを教育目的で列挙してください。\n"
                    f"SPY: ${m_info['spy']:.2f} ({m_info['spy_change']:+.2f}%), VIX: {m_info['vix']:.2f}\n"
                    f"シグナル銘柄数: {act_n}\n"
                    f"最新ニュース:\n{m_news}\n\n"
                    f"注意：投資判断は行わず、あくまでデータの解説に留めてください。"
                )
                cl = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                try:
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    # 免責文を追加
                    disclaimer = t("ai_disclaimer")
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$") + disclaimer
                except: st.error(t("error_ai"))

    if st.session_state.ai_market_text: st.info(st.session_state.ai_market_text)

    draw_sentinel_grid_ui([
        {"label": t("label_spy"), "value": f"${m_info['spy']:.2f}", "delta": f"{m_info['spy_change']:+.2f}%"},
        {"label": t("label_vix"), "value": f"{m_info['vix']:.2f}"},
        {"label": t("label_action"), "value": len(scan_df[scan_df["status"]=="ACTION"]) if not scan_df.empty else 0},
        {"label": t("label_watch"), "value": len(scan_df[scan_df["status"]=="WAIT"]) if not scan_df.empty else 0}
    ])

    if not scan_df.empty:
        st.markdown(f'<div class="section-header">{t("section_sector_map")}</div>', unsafe_allow_html=True)
        scan_df["vcp_score"] = scan_df["vcp"].apply(lambda x: x.get("score", 0))
        treemap_fig = px.treemap(scan_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        treemap_fig.update_layout(template="plotly_dark", height=600, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(treemap_fig, use_container_width=True)

        st.markdown(f'<div class="section-header">{t("section_scan_list")}</div>', unsafe_allow_html=True)
        t_cols = ["ticker", "status", "vcp_score", "rs", "sector", "industry"]
        a_cols = [c for c in t_cols if c in scan_df.columns]
        st.dataframe(scan_df[a_cols].sort_values("vcp_score", ascending=False), use_container_width=True, height=400)

# ------------------------------------------------------------------------------
# TAB 2: AI診断 (個別分析)
# ------------------------------------------------------------------------------
with tab_2:
    st.markdown(f'<div class="section-header">{t("title_quant_scan")}</div>', unsafe_allow_html=True)
    t_input = st.text_input(t("label_ticker"), value=st.session_state.target_ticker).upper().strip()

    col_a, col_b = st.columns(2)
    if col_a.button(t("btn_quant_scan"), type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Scanning {t_input}..."):
            df_full = DataEngine.get_data(t_input, "2y")
            if df_full is not None and not df_full.empty:
                v_res = VCPAnalyzer.calculate(df_full)
                rs_v = RSAnalyzer.get_raw_score(df_full)
                pf_v = StrategyValidator.run(df_full)
                p_c = DataEngine.get_current_price(t_input)
                st.session_state.quant_results_stored = {"vcp": v_res, "rs": rs_v, "pf": pf_v, "price": p_c, "ticker": t_input}
                st.session_state.ai_analysis_text = ""
            else: st.error(t("error_data_fetch", t_input))

    if col_b.button(t("btn_add_watchlist"), use_container_width=True) and t_input:
        wl_list = load_watchlist_data()
        if t_input not in wl_list: wl_list.append(t_input); save_watchlist_data(wl_list); st.success(t("success_added", t_input))

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        res_q = st.session_state.quant_results_stored
        draw_sentinel_grid_ui([
            {"label": t("label_current_price"), "value": f"${res_q['price']:.2f}" if res_q['price'] else "N/A"},
            {"label": t("label_vcp_score"), "value": f"{res_q['vcp']['score']}/105"},
            {"label": t("label_pf"), "value": f"x{res_q['pf']:.2f}"},
            {"label": t("label_rs_momentum"), "value": f"{res_q['rs']*100:+.1f}%" if res_q['rs'] != -999 else "N/A"}
        ])

        # チャート描画
        df_plot = DataEngine.get_data(t_input, "2y")
        if df_plot is not None:
            candlestick = go.Figure(data=[go.Candlestick(x=df_plot.index, open=df_plot['Open'], high=df_plot['High'], low=df_plot['Low'], close=df_plot['Close'])])
            candlestick.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(candlestick, use_container_width=True)

        if st.button(t("btn_ai_explain"), use_container_width=True):
            ak = st.secrets.get("DEEPSEEK_API_KEY")
            if ak:
                with st.spinner(f"Analyzing {t_input}..."):
                    news_t = NewsEngine.format_for_prompt(NewsEngine.get(t_input))
                    fund_t = FundamentalEngine.format_for_prompt(FundamentalEngine.get(t_input), res_q['price'])
                    p_text = (
                        f"あなたは金融アシスタントです。以下の情報をもとに、"
                        f"投資判断の参考となる客観的な解説を提供してください。\n"
                        f"銘柄:{t_input} 現在値:${res_q['price']} VCPスコア:{res_q['vcp']['score']} RS:{res_q['rs']*100:.1f}%\n"
                        f"財務情報: {fund_t}\n"
                        f"ニュース: {news_t}\n\n"
                        f"注意：売買推奨は行わず、データの読み解き方や注目点を説明してください。"
                    )
                    client = OpenAI(api_key=ak, base_url="https://api.deepseek.com")
                    try:
                        ai_res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": p_text}])
                        disclaimer = t("ai_explain_disclaimer")
                        st.session_state.ai_analysis_text = ai_res.choices[0].message.content.replace("$", r"\$") + disclaimer
                    except: st.error(t("error_ai"))
        if st.session_state.ai_analysis_text: st.markdown("---"); st.info(st.session_state.ai_analysis_text)

# ------------------------------------------------------------------------------
# TAB 3: ポートフォリオ (セクター取得強化版)
# ------------------------------------------------------------------------------
with tab_3:
    st.markdown(f'<div class="section-header">{t("title_portfolio_risk")}</div>', unsafe_allow_html=True)
    portfolio_obj = load_portfolio_json()

    with st.expander(t("expander_cash"), expanded=True):
        col_j, col_u, col_btn = st.columns(3)
        current_jpy_cash = portfolio_obj.get("cash_jpy", 1000000)
        current_usd_cash = portfolio_obj.get("cash_usd", 0)
        input_jpy = col_j.number_input(t("label_jpy_cash"), value=int(current_jpy_cash), step=1000)
        input_usd = col_u.number_input(t("label_usd_cash"), value=float(current_usd_cash), step=100.0)
        if col_btn.button(t("btn_update_balance"), use_container_width=True):
            portfolio_obj["cash_jpy"] = input_jpy; portfolio_obj["cash_usd"] = input_usd
            save_portfolio_json(portfolio_obj); st.success(t("success_balance_updated")); st.rerun()

    # ポジション集計ロジック
    positions_map = portfolio_obj.get("positions", {})
    agg_stock_usd = 0.0
    detailed_positions = []

    for tkr, data in positions_map.items():
        # セクター情報の取得強化
        f_info = FundamentalEngine.get(tkr)
        s_name = f_info.get("sector", "Unknown")
        i_name = f_info.get("industry", "Unknown")

        # フォールバック
        if s_name == "Unknown":
            try:
                y_raw = yf.Ticker(tkr).info
                s_name = y_raw.get("sector", y_raw.get("Sector", "Unknown"))
                i_name = y_raw.get("industry", y_raw.get("Industry", "Unknown"))
            except: pass

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
        {"label": t("label_total_nav"), "value": f"¥{total_nav_jpy:,.0f}"},
        {"label": t("label_total_equity"), "value": f"¥{total_stock_jpy:,.0f}", "delta": f"(${agg_stock_usd:,.2f})"},
        {"label": t("label_jpy_cash_short"), "value": f"¥{portfolio_obj['cash_jpy']:,.0f}"},
        {"label": t("label_usd_cash_short"), "value": f"¥{total_cash_usd_jpy:,.0f}", "delta": f"(${portfolio_obj['cash_usd']:.2f})"}
    ])

    if st.button(t("btn_ai_portfolio"), use_container_width=True, type="primary"):
        guard_key = st.secrets.get("DEEPSEEK_API_KEY")
        if guard_key:
            with st.spinner("AIがポートフォリオを分析しています..."):
                m_stat = get_market_overview_live()
                p_report = "\n".join([f"- {x['ticker']} [{x['sector']}]: ${x['val']:.2f} (PnL: {x['pnl']:+.1f}%)" for x in detailed_positions])
                prompt_guard = (
                    f"あなたはリスク管理アシスタントです。以下のポートフォリオ情報を元に、"
                    f"投資家が考慮すべき客観的なリスク指標を解説してください。\n"
                    f"総資産: ¥{total_nav_jpy:,.0f}, 現金比率: {(portfolio_obj['cash_jpy']+total_cash_usd_jpy)/total_nav_jpy*100:.1f}%\n"
                    f"地合い: SPY ${m_stat['spy']:.2f}, VIX {m_stat['vix']:.2f}\n"
                    f"保有詳細:\n{p_report}\n\n"
                    f"注意：売買推奨は行わず、あくまでデータの解説に留めてください。"
                )
                cl_guard = OpenAI(api_key=guard_key, base_url="https://api.deepseek.com")
                try:
                    res_guard = cl_guard.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt_guard}])
                    disclaimer = t("ai_portfolio_disclaimer")
                    st.session_state.ai_port_text = res_guard.choices[0].message.content.replace("$", r"\$") + disclaimer
                except: st.error(t("error_ai"))

    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    # 保有ポジション詳細表示
    if positions_map:
        st.markdown(f'<div class="section-header">{t("section_positions")}</div>', unsafe_allow_html=True)
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
        st.markdown(t("form_add_position"))
        c1, c2, c3 = st.columns(3)
        f_tkr = c1.text_input(t("label_ticker_code")).upper().strip()
        f_shr = c2.number_input(t("label_shares"), min_value=1)
        f_cst = c3.number_input(t("label_avg_cost"), min_value=0.01)
        if st.form_submit_button(t("btn_register")) and f_tkr:
            portfolio_obj["positions"][f_tkr] = {"shares": f_shr, "avg_cost": f_cst}
            save_portfolio_json(portfolio_obj); st.success(t("success_registered", f_tkr)); st.rerun()

st.divider()
st.caption(t("footer"))