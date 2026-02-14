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
# 外部エンジンのインポート (貴殿のベース構成に準拠)
# ==============================================================================
try:
    from config import CONFIG
except ImportError:
    CONFIG = {"STOP_LOSS_ATR": 2.0, "TARGET_R": 2.5}

# 貴殿の環境にあるクラスのみをインポート
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
# もしInsiderEngineがあればインポート（エラー回避のためtry）
try:
    from engines.fundamental import InsiderEngine
except ImportError:
    InsiderEngine = None

from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator

warnings.filterwarnings("ignore")

# ==============================================================================
# 定数定義 (app.py 側で持つことでインポートエラーを回避)
# ==============================================================================
NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
CACHE_DIR = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results"); RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

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
        "ai_key_missing": "DEEPSEEK_API_KEY が設定されていません。",
        "portfolio_risk": "💼 ポートフォリオリスク管理",
        "portfolio_empty": "ポートフォリオは空です。",
        "unrealized_jpy": "💰 総資産 (Total Equity)",
        "assets": "📊 保有銘柄数",
        "exposure": "🛡️ 株式評価額 (Exposure)",
        "jpy_cash": "💰 預り金 (JPY)",
        "usd_cash": "💵 USドル (USD)",
        "active_positions": "📋 保有中のポジション",
        "close_position": "決済",
        "register_new": "➕ 新規ポジション登録",
        "ticker_symbol": "ティッカーシンボル",
        "shares": "株数",
        "avg_cost": "平均取得単価",
        "add_to_portfolio": "ポートフォリオに追加",
        "update_balance": "残高更新",
        "cash_manage": "💰 資金管理 (預り金設定)",
        "ai_port_btn": "🛡️ AIポートフォリオ診断 (SENTINEL PORTFOLIO GUARD)",
        "ai_market_btn": "🤖 AI市場分析 (SENTINEL MARKET EYE)",
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
        "generate_ai": "🚀 GENERATE AI DIAGNOSIS",
        "portfolio_risk": "💼 PORTFOLIO RISK MANAGEMENT",
        "portfolio_empty": "Portfolio is currently empty.",
        "unrealized_jpy": "💰 Total Equity",
        "assets": "📊 Assets",
        "exposure": "🛡️ Stock Value",
        "jpy_cash": "💰 JPY Cash",
        "usd_cash": "💵 USD Cash",
        "active_positions": "📋 ACTIVE POSITIONS",
        "close_position": "Close",
        "register_new": "➕ REGISTER NEW POSITION",
        "ticker_symbol": "Ticker Symbol",
        "shares": "Shares",
        "avg_cost": "Avg Cost",
        "add_to_portfolio": "ADD TO PORTFOLIO",
        "update_balance": "Update Balance",
        "cash_manage": "💰 Cash Management",
        "ai_port_btn": "🛡️ AI PORTFOLIO REVIEW",
        "ai_market_btn": "🤖 AI MARKET ANALYSIS",
    }
}

# ==============================================================================
# ヘルパー関数
# ==============================================================================

def initialize_sentinel_state():
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = ""
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "language" not in st.session_state: st.session_state.language = "ja"
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

def load_portfolio_json() -> dict:
    default = {"positions": {}, "cash_jpy": 350000, "cash_usd": 0}
    if not PORTFOLIO_FILE.exists(): return default
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if "cash_jpy" not in d: d["cash_jpy"] = 350000
            if "cash_usd" not in d: d["cash_usd"] = 0
            return d
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

def get_market_overview_local():
    try:
        spy = yf.Ticker("SPY").history(period="5d")
        vix = yf.Ticker("^VIX").history(period="1d")
        spy_p = spy["Close"].iloc[-1] if not spy.empty else 0
        spy_chg = (spy_p / spy["Close"].iloc[-2] - 1) * 100 if len(spy) >= 2 else 0
        vix_p = vix["Close"].iloc[-1] if not vix.empty else 0
        return {"spy": spy_p, "spy_change": spy_chg, "vix": vix_p}
    except:
        return {"spy": 0, "spy_change": 0, "vix": 0}

# ==============================================================================
# UI スタイル
# ==============================================================================
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 0rem !important; padding-bottom: 2rem !important; }
.ui-push-buffer { height: 65px; width: 100%; background: transparent; }
.stTabs [data-baseweb="tab-list"] { display: flex !important; width: 100% !important; flex-wrap: nowrap !important; overflow-x: auto !important; background-color: #161b22 !important; padding: 12px 12px 0 12px !important; border-radius: 12px 12px 0 0 !important; gap: 12px !important; border-bottom: 2px solid #30363d !important; }
.stTabs [data-baseweb="tab"] { min-width: 185px !important; flex-shrink: 0 !important; font-size: 1.05rem !important; font-weight: 700 !important; color: #8b949e !important; padding: 22px 32px !important; background-color: transparent !important; border: none !important; }
.stTabs [aria-selected="true"] { color: #ffffff !important; background-color: #238636 !important; border-radius: 12px 12px 0 0 !important; }
.sentinel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 16px; margin: 20px 0 30px 0; }
@media (min-width: 992px) { .sentinel-grid { grid-template-columns: repeat(4, 1fr); } }
.sentinel-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 24px; box-shadow: 0 4px 25px rgba(0,0,0,0.7); }
.sentinel-label { font-size: 0.8rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.25em; margin-bottom: 12px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
.sentinel-value { font-size: 1.45rem; font-weight: 700; color: #f0f6fc; line-height: 1.1; }
.sentinel-delta { font-size: 0.95rem; font-weight: 600; margin-top: 12px; }
.diagnostic-panel { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 28px; margin-bottom: 26px; }
.diag-row { display: flex; justify-content: space-between; padding: 16px 0; border-bottom: 1px solid #21262d; }
.diag-row:last-child { border-bottom: none; }
.diag-key { color: #8b949e; font-size: 1.0rem; font-weight: 600; }
.diag-val { color: #f0f6fc; font-weight: 700; font-family: 'Share Tech Mono', monospace; font-size: 1.15rem; }
.section-header { font-size: 1.2rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 16px; margin: 45px 0 28px; text-transform: uppercase; letter-spacing: 4px; display: flex; align-items: center; gap: 14px; }
.pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 18px; padding: 30px; margin-bottom: 24px; border-left: 12px solid #30363d; }
.pos-card.urgent { border-left-color: #f85149; }
.pos-card.caution { border-left-color: #d29922; }
.pos-card.profit { border-left-color: #3fb950; }
.pnl-pos { color: #3fb950; font-weight: 700; font-size: 1.3rem; }
.pnl-neg { color: #f85149; font-weight: 700; font-size: 1.3rem; }
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
# メイン UI
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown('<div class="ui-push-buffer"></div>', unsafe_allow_html=True)
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

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
    st.caption(f"🛡️ SENTINEL V7.3 | {NOW.strftime('%H:%M:%S')}")

fx_rate = CurrencyEngine.get_usd_jpy()
tab_scan, tab_diag, tab_port = st.tabs([txt["tab_scan"], txt["tab_diag"], txt["tab_port"]])

# --- Tab 1: マーケットスキャン ---
with tab_scan:
    st.markdown(f'<div class="section-header">{txt["tab_scan"]}</div>', unsafe_allow_html=True)
    m_ctx = get_market_overview_local()
    
    s_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        f_list = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if f_list:
            try:
                with open(f_list[0], "r", encoding="utf-8") as f: s_data = json.load(f)
                s_df = pd.DataFrame(s_data.get("qualified_full", []))
            except: pass

    # AI地合い分析ボタン
    if st.button(txt["ai_market_btn"], use_container_width=True, type="primary"):
        key = st.secrets.get("DEEPSEEK_API_KEY")
        if not key:
            st.error("API Key Missing")
        else:
            with st.spinner("Analyzing Market Conditions..."):
                n_data = NewsEngine.get_general_market()
                n_txt = NewsEngine.format_for_prompt(n_data)
                act_count = len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0
                wait_count = len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0
                sectors = list(s_df["sector"].value_counts().keys())[:3] if not s_df.empty else []

                prompt = (
                    f"あなたは「ウォール街のAI投資家SENTINEL」です。\n"
                    f"【現在日時】: {TODAY_STR}\n"
                    f"【市場インジケータ】\nSPY: ${m_ctx['spy']:.2f} ({m_ctx['spy_change']:+.2f}%), VIX: {m_ctx['vix']:.2f}\n"
                    f"【スキャン統計】\nACTION: {act_count}, WAIT: {wait_count}, 主導セクター: {', '.join(sectors)}\n"
                    f"【ニュース】\n{n_txt}\n\n"
                    f"【指示】\n1. 市場フェーズを定義せよ。2. ニュースから重要材料抽出。3. 推奨ポジション比率提示。4. 600文字以内。"
                )
                cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                try:
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")
                except Exception as e: st.error(f"AI Error: {e}")

    if st.session_state.ai_market_text: st.info(st.session_state.ai_market_text)

    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_ctx['spy']:.2f}", "delta": f"{m_ctx['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_ctx['vix']:.2f}"},
        {"label": txt["action_list"], "value": len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0},
        {"label": txt["wait_list"], "value": len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0}
    ])
    
    if not s_df.empty:
        s_df["vcp_score"] = s_df["vcp"].apply(lambda x: x.get("score", 0))
        m_fig = px.treemap(s_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        m_fig.update_layout(template="plotly_dark", height=600, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(m_fig, use_container_width=True)

# --- Tab 2: AI診断 ---
with tab_diag:
    st.markdown(f'<div class="section-header">{txt["realtime_scan"]}</div>', unsafe_allow_html=True)
    t_input = st.text_input(txt["ticker_input"], value=st.session_state.target_ticker).upper().strip()
    c1, c2 = st.columns(2)
    start_quant = c1.button(txt["run_quant"], type="primary", use_container_width=True)
    add_wl = c2.button(txt["add_watchlist"], use_container_width=True)

    if (start_quant or st.session_state.pop("trigger_analysis", False)) and t_input:
        with st.spinner(f"Scanning {t_input}..."):
            df_raw = DataEngine.get_data(t_input, "2y")
            if df_raw is not None and not df_raw.empty:
                vcp_res = VCPAnalyzer.calculate(df_raw)
                rs_val = RSAnalyzer.get_raw_score(df_raw)
                pf_val = StrategyValidator.run(df_raw)
                p_curr = DataEngine.get_current_price(t_input)
                st.session_state.quant_results_stored = {"vcp": vcp_res, "rs": rs_val, "pf": pf_val, "price": p_curr, "ticker": t_input}
            else: st.error(f"Failed to fetch data for {t_input}.")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        q = st.session_state.quant_results_stored
        draw_sentinel_grid_ui([
            {"label": txt["current_price"], "value": f"${q['price']:.2f}"},
            {"label": txt["vcp_score"], "value": f"{q['vcp']['score']}/105"},
            {"label": txt["profit_factor"], "value": f"x{q['pf']:.2f}"},
            {"label": txt["rs_momentum"], "value": f"{q['rs']*100:+.1f}%"}
        ])
        if st.button(txt["generate_ai"], use_container_width=True):
            key = st.secrets.get("DEEPSEEK_API_KEY")
            if key:
                with st.spinner("AI Reasoning..."):
                    n_txt = NewsEngine.format_for_prompt(NewsEngine.get(t_input))
                    f_text = json.dumps(FundamentalEngine.get(t_input))
                    prompt = f"銘柄:{t_input} 価格:${q['price']} VCP:{q['vcp']['score']} RS:{q['rs']*100}%\nニュース:{n_txt}\nファンダ:{f_text}\n指示:600字以内で投資判断せよ。"
                    cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                    try:
                        res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = res.choices[0].message.content.replace("$", r"\$")
                    except Exception as e: st.error(f"AI Error: {e}")
        if st.session_state.ai_analysis_text: st.markdown("---"); st.markdown(st.session_state.ai_analysis_text)

# --- Tab 3: ポートフォリオ ---
with tab_port:
    st.markdown(f'<div class="section-header">{txt["portfolio_risk"]}</div>', unsafe_allow_html=True)
    p_j = load_portfolio_json()
    pos_m = p_j.get("positions", {})

    with st.expander(txt["cash_manage"], expanded=True):
        c1, c2, c3 = st.columns(3)
        in_jpy = c1.number_input(txt["jpy_cash"], value=int(p_j["cash_jpy"]), step=1000)
        in_usd = c2.number_input(txt["usd_cash"], value=float(p_j["cash_usd"]), step=100.0)
        if c3.button(txt["update_balance"], use_container_width=True):
            p_j["cash_jpy"] = in_jpy; p_j["cash_usd"] = in_usd
            save_portfolio_json(p_j); st.rerun()

    total_stock_val_usd = 0.0
    pos_details = []
    for t, d in pos_m.items():
        fund = FundamentalEngine.get(t); curr_p = DataEngine.get_current_price(t)
        val_usd = curr_p * d['shares']; total_stock_val_usd += val_usd
        pos_details.append({"ticker": t, "sector": fund.get("sector", "Unknown"), "val": val_usd, "pnl": ((curr_p / d['avg_cost']) - 1) * 100})

    stock_val_jpy = total_stock_val_usd * fx_rate
    usd_cash_jpy = p_j["cash_usd"] * fx_rate
    total_equity_jpy = stock_val_jpy + p_j["cash_jpy"] + usd_cash_jpy

    draw_sentinel_grid_ui([
        {"label": txt["unrealized_jpy"], "value": f"¥{total_equity_jpy:,.0f}"},
        {"label": txt["exposure"], "value": f"¥{stock_val_jpy:,.0f}", "delta": f"(${total_stock_val_usd:,.2f})"},
        {"label": txt["jpy_cash"], "value": f"¥{p_j['cash_jpy']:,.0f}"},
        {"label": txt["usd_cash"], "value": f"¥{usd_cash_jpy:,.0f}", "delta": f"(${p_j['cash_usd']:.2f})"}
    ])

    if st.button(txt["ai_port_btn"], use_container_width=True, type="primary"):
        key = st.secrets.get("DEEPSEEK_API_KEY")
        if key:
            with st.spinner("Analyzing Risks..."):
                p_text = "\n".join([f"- {x['ticker']} [{x['sector']}]: ${x['val']:.2f} ({x['pnl']:+.1f}%)" for x in pos_details])
                prompt = f"資産:¥{total_equity_jpy} 現金比:{(p_j['cash_jpy']+usd_cash_jpy)/total_equity_jpy*100}%\n保有:{p_text}\n600字以内でリスク診断せよ。"
                cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                try:
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_port_text = res.choices[0].message.content.replace("$", r"\$")
                except Exception as e: st.error(f"AI Error: {e}")
    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    if pos_m:
        st.markdown(f'<div class="section-header">{txt["active_positions"]}</div>', unsafe_allow_html=True)
        for d in pos_details:
            st.markdown(f'<div class="pos-card"><b>{d["ticker"]}</b> ({d["sector"]})<br>PnL: {d["pnl"]:+.2f}%</div>', unsafe_allow_html=True)

    with st.form("add_port"):
        c1, c2, c3 = st.columns(3); ft = c1.text_input(txt["ticker_symbol"]).upper().strip(); fs = c2.number_input(txt["shares"], min_value=1); fc = c3.number_input(txt["avg_cost"], min_value=0.01)
        if st.form_submit_button(txt["add_to_portfolio"]) and ft:
            p_j["positions"][ft] = {"shares": fs, "avg_cost": fc}; save_portfolio_json(p_j); st.rerun()

