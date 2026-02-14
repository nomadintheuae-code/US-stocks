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
# 1. 外部エンジンのインポート (engines フォルダの構成を維持)
# ==============================================================================
try:
    from config import CONFIG
except ImportError:
    CONFIG = {"STOP_LOSS_ATR": 2.0, "TARGET_R": 2.5}

# 貴殿の環境の engines フォルダからクラスをインポート
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator

warnings.filterwarnings("ignore")

# ==============================================================================
# 2. 定数・パスの定義 (ImportError 回避のため app.py 内に集約)
# ==============================================================================
NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ==============================================================================
# 3. ヘルパー関数
# ==============================================================================

def initialize_sentinel_state():
    """セッションステートの初期化"""
    if "target_ticker" not in st.session_state: st.session_state.target_ticker = ""
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored = None

initialize_sentinel_state()

def load_portfolio_json() -> dict:
    """ポートフォリオデータの読み込み。デフォルト資金を1,000,000円に設定"""
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
    """ポートフォリオデータの保存"""
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_watchlist_data() -> list:
    """ウォッチリストの読み込み"""
    if not WATCHLIST_FILE.exists(): return []
    try:
        with open(WATCHLIST_FILE, "r") as f: return json.load(f)
    except: return []

def save_watchlist_data(data: list):
    """ウォッチリストの保存"""
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)

def get_market_overview_live():
    """SPY最新価格を強制取得（ローカルキャッシュの異常値を回避）"""
    try:
        spy_ticker = yf.Ticker("SPY")
        spy_hist = spy_ticker.history(period="3d")
        vix_ticker = yf.Ticker("^VIX")
        vix_hist = vix_ticker.history(period="1d")
        
        if not spy_hist.empty and len(spy_hist) >= 2:
            spy_p = spy_hist["Close"].iloc[-1]
            spy_chg = (spy_p / spy_hist["Close"].iloc[-2] - 1) * 100
        else:
            spy_p = spy_ticker.fast_info.get('lastPrice', 0)
            spy_chg = 0
            
        vix_p = vix_hist["Close"].iloc[-1] if not vix_hist.empty else 0
        return {"spy": spy_p, "spy_change": spy_chg, "vix": vix_p}
    except:
        return {"spy": 0, "spy_change": 0, "vix": 0}

def draw_sentinel_grid_ui(metrics: List[Dict[str, Any]]):
    """Sentinel Pro スタイルの 4カラムグリッド UI"""
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
.diagnostic-panel { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 20px; }
.diag-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #21262d; }
.section-header { font-size: 1.2rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 12px; margin: 30px 0 20px; text-transform: uppercase; letter-spacing: 2px; }
.pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 24px; margin-bottom: 15px; border-left: 10px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
.pnl-pos { color: #3fb950; font-weight: bold; }
.pnl-neg { color: #f85149; font-weight: bold; }
.stButton > button { border-radius: 10px; font-weight: 700; }
</style>
"""

# ==============================================================================
# 5. メイン UI 描画
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown('<div class="ui-push-buffer"></div>', unsafe_allow_html=True)
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# サイドバー：ウォッチリスト
with st.sidebar:
    st.markdown(f"### 🛡️ SENTINEL ウォッチリスト")
    wl_t = load_watchlist_data()
    for t_n in wl_t:
        c_n, c_d = st.columns([4, 1])
        if c_n.button(t_n, key=f"side_{t_n}", use_container_width=True):
            st.session_state.target_ticker = t_n
            st.rerun()
        if c_d.button("×", key=f"rm_{t_n}"):
            wl_t.remove(t_n); save_watchlist_data(wl_t); st.rerun()

# 共通データ
fx_rate = CurrencyEngine.get_usd_jpy()
tab_scan, tab_diag, tab_port = st.tabs(["📊 マーケットスキャン", "🔍 AI診断", "💼 ポートフォリオ"])

# --- Tab 1: マーケットスキャン ---
with tab_scan:
    st.markdown(f'<div class="section-header">📊 マーケットスキャン (地合い分析)</div>', unsafe_allow_html=True)
    m_ctx = get_market_overview_live() 
    
    s_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        f_list = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if f_list:
            try:
                with open(f_list[0], "r", encoding="utf-8") as f: s_data = json.load(f)
                s_df = pd.DataFrame(s_data.get("qualified_full", []))
            except: pass

    # --- AI市場分析ボタン ---
    if st.button("🤖 AI市場分析 (SENTINEL MARKET EYE)", use_container_width=True, type="primary"):
        key = st.secrets.get("DEEPSEEK_API_KEY")
        if not key:
            st.error("DeepSeek API Key が Secrets に設定されていません。")
        else:
            with st.spinner("AI が市場の深層を解析中..."):
                # 市場ニュース収集
                news_data = NewsEngine.get_general_market()
                news_txt = NewsEngine.format_for_prompt(news_data)
                
                # スキャン統計
                act_cnt = len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0
                wait_cnt = len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0
                top_sectors = list(s_df["sector"].value_counts().keys())[:3] if not s_df.empty else ["Unknown"]

                prompt = (
                    f"あなたは「ウォール街のAI投資家SENTINEL」です。提供されたデータに基づき、本日の市場環境を冷徹に分析せよ。\n"
                    f"【現在日時】: {TODAY_STR}\n"
                    f"【指数状況】SPY: ${m_ctx['spy']:.2f} ({m_ctx['spy_change']:+.2f}%), VIX: {m_ctx['vix']:.2f}\n"
                    f"【SENTINEL統計】買いシグナル(ACTION): {act_cnt}件, 待機(WAIT): {wait_cnt}件\n"
                    f"【主導セクター】: {', '.join(top_sectors)}\n"
                    f"【最新ニュース】\n{news_txt}\n\n"
                    f"指示: 市場フェーズ（上昇/調整/警戒）を定義し、ニュースから読み取れる材料を抽出せよ。600字以内。文末に「最終判断: [BULL/BEAR/NEUTRAL]」を明記せよ。"
                )
                
                cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                try:
                    res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_market_text = res.choices[0].message.content.replace("$", r"\$")
                except Exception as e:
                    st.error(f"AI Error: {e}")

    if st.session_state.ai_market_text:
        st.info(st.session_state.ai_market_text)

    # グリッド
    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_ctx['spy']:.2f}", "delta": f"{m_ctx['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_ctx['vix']:.2f}"},
        {"label": "アクション銘柄", "value": len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0},
        {"label": "ウォッチ銘柄", "value": len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0}
    ])
    
    if not s_df.empty:
        st.markdown(f'<div class="section-header">🗺️ セクター別RSマップ</div>', unsafe_allow_html=True)
        s_df["vcp_score"] = s_df["vcp"].apply(lambda x: x.get("score", 0))
        m_fig = px.treemap(s_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        m_fig.update_layout(template="plotly_dark", height=600, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(m_fig, use_container_width=True)
        
        # --- スキャン詳細データテーブル (KeyError対策済み) ---
        st.markdown(f'<div class="section-header">📋 スキャン銘柄詳細リスト</div>', unsafe_allow_html=True)
        target_cols = ["ticker", "status", "vcp_score", "rs", "sector", "industry"]
        available_cols = [c for c in target_cols if c in s_df.columns]
        st.dataframe(
            s_df[available_cols].sort_values("vcp_score", ascending=False),
            use_container_width=True, height=400
        )

# --- Tab 2: AI診断 (個別銘柄) ---
with tab_diag:
    st.markdown(f'<div class="section-header">🔍 リアルタイム定量スキャン</div>', unsafe_allow_html=True)
    t_input = st.text_input("ティッカーシンボル", value=st.session_state.target_ticker).upper().strip()
    
    c1, c2 = st.columns(2)
    if c1.button("🚀 定量スキャン実行", type="primary", use_container_width=True) and t_input:
        with st.spinner(f"Analyzing {t_input}..."):
            df_raw = DataEngine.get_data(t_input, "2y")
            if df_raw is not None and not df_raw.empty:
                vcp_res = VCPAnalyzer.calculate(df_raw)
                rs_val = RSAnalyzer.get_raw_score(df_raw)
                pf_val = StrategyValidator.run(df_raw)
                p_curr = DataEngine.get_current_price(t_input)
                st.session_state.quant_results_stored = {"vcp": vcp_res, "rs": rs_val, "pf": pf_val, "price": p_curr, "ticker": t_input}
                st.session_state.ai_analysis_text = ""
            else: st.error(f"{t_input} のデータ取得に失敗しました。")
    if c2.button("⭐ ウォッチリストに追加", use_container_width=True) and t_input:
        wl = load_watchlist_data()
        if t_input not in wl: wl.append(t_input); save_watchlist_data(wl); st.success(f"{t_input} を追加しました")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"] == t_input:
        q = st.session_state.quant_results_stored
        draw_sentinel_grid_ui([
            {"label": "💰 現在値", "value": f"${q['price']:.2f}"},
            {"label": "🎯 VCPスコア", "value": f"{q['vcp']['score']}/105"},
            {"label": "📈 PF", "value": f"x{q['pf']:.2f}"},
            {"label": "📏 RSモメンタム", "value": f"{q['rs']*100:+.1f}%"}
        ])
        
        # チャート
        df_chart = DataEngine.get_data(t_input, "2y")
        if df_chart is not None:
            fig = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_raw['Open'], high=df_raw['High'], low=df_raw['Low'], close=df_raw['Close'])])
            fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        # AI診断レポートボタン
        if st.button("🤖 AI診断レポート生成", use_container_width=True):
            k = st.secrets.get("DEEPSEEK_API_KEY")
            if k:
                with st.spinner(f"SENTINEL AI が {t_input} を深層診断中..."):
                    n_txt = NewsEngine.format_for_prompt(NewsEngine.get(t_input))
                    f_dat = FundamentalEngine.get(t_input)
                    prompt = (
                        f"あなたはAI投資家SENTINEL。銘柄 {t_input} を診断せよ。\n"
                        f"【定量データ】価格: ${q['price']}, VCP: {q['vcp']['score']}, RS: {q['rs']*100:.1f}%, PF: {q['pf']}\n"
                        f"【財務】Sector: {f_dat.get('sector')}, Industry: {f_dat.get('industry')}, RevenueGrowth: {f_dat.get('revenue_growth')}\n"
                        f"【ニュース】\n{n_txt}\n\n"
                        f"指示: チャートの形状、財務、ニュースから読み取れる好材料/悪材料を整理し、600字以内で投資助言せよ。最終判断[BUY/WAIT/SELL]を提示せよ。"
                    )
                    cl = OpenAI(api_key=k, base_url="https://api.deepseek.com")
                    try:
                        res = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.session_state.ai_analysis_text = res.choices[0].message.content.replace("$", r"\$")
                    except: st.error("AI Error")
        if st.session_state.ai_analysis_text: st.markdown("---"); st.info(st.session_state.ai_analysis_text)

# --- Tab 3: ポートフォリオ ---
with tab_port:
    st.markdown(f'<div class="section-header">💼 ポートフォリオリスク管理</div>', unsafe_allow_html=True)
    p_j = load_portfolio_json()

    # 資金管理
    with st.expander("💰 資金管理 (口座残高入力)", expanded=True):
        c1, c2, c3 = st.columns(3)
        # 指示通り初期値を 1,000,000円
        in_jpy = c1.number_input("預り金 (JPY)", value=int(p_j["cash_jpy"]), step=1000)
        in_usd = c2.number_input("USドル (USD)", value=float(p_j["cash_usd"]), step=100.0)
        if c3.button("残高を更新して保存", use_container_width=True):
            p_j["cash_jpy"] = in_jpy; p_j["cash_usd"] = in_usd
            save_portfolio_json(p_j); st.success("残高を更新しました。"); st.rerun()

    # 資産集計
    pos_m = p_j.get("positions", {})
    total_stock_usd = 0.0
    pos_details = []
    for t, d in pos_m.items():
        curr_p = DataEngine.get_current_price(t)
        val_usd = curr_p * d['shares']; total_stock_usd += val_usd
        fund = FundamentalEngine.get(t)
        pos_details.append({
            "ticker": t, "sector": fund.get("sector", "Unknown"), 
            "val": val_usd, "pnl": ((curr_p / d['avg_cost']) - 1) * 100,
            "shares": d['shares'], "cost": d['avg_cost'], "curr": curr_p
        })

    stock_val_jpy = total_stock_usd * fx_rate
    usd_cash_jpy = p_j["cash_usd"] * fx_rate
    total_equity_jpy = stock_val_jpy + p_j["cash_jpy"] + usd_cash_jpy

    draw_sentinel_grid_ui([
        {"label": "💰 評価額合計", "value": f"¥{total_equity_jpy:,.0f}"},
        {"label": "🛡️ 米国株式", "value": f"¥{stock_val_jpy:,.0f}", "delta": f"(${total_stock_usd:,.2f})"},
        {"label": "預り金 (JPY)", "value": f"¥{p_j['cash_jpy']:,.0f}"},
        {"label": "USドル (USD)", "value": f"¥{usd_cash_jpy:,.0f}", "delta": f"(${p_j['cash_usd']:.2f})"}
    ])

    # --- AIポートフォリオ診断機能 ---
    if st.button("🛡️ AIポートフォリオ診断 (SENTINEL GUARD)", use_container_width=True, type="primary"):
        key = st.secrets.get("DEEPSEEK_API_KEY")
        if not key:
            st.error("API Key Missing")
        else:
            with st.spinner("ポートフォリオのリスクを診断中..."):
                m_ctx = get_market_overview_live()
                p_text = "\n".join([f"- {x['ticker']} [{x['sector']}]: ${x['val']:.2f} ({x['pnl']:+.1f}%)" for x in pos_details])
                
                prompt = (
                    f"あなたは「AI投資家SENTINEL」です。現在の保有資産のリスクを診断せよ。\n"
                    f"【現在日時】: {TODAY_STR}\n"
                    f"【資産状況】総資産: ¥{total_equity_jpy:,.0f}, 現金比率: {(p_j['cash_jpy']+usd_cash_jpy)/total_equity_jpy*100:.1f}%\n"
                    f"【市場環境】SPY: ${m_ctx['spy']:.2f}, VIX: {m_ctx['vix']:.2f}\n"
                    f"【保有ポートフォリオ】\n{p_text}\n\n"
                    f"指示: セクター集中リスクの有無、現金比率の妥当性、現在のボラティリティへの対策を600字以内で論理的に述べよ。"
                )
                cl = OpenAI(api_key=key, base_url="https://api.deepseek.com")
                try:
                    res_p = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                    st.session_state.ai_port_text = res_p.choices[0].message.content.replace("$", r"\$")
                except: st.error("AI分析エラー")

    if st.session_state.ai_port_text:
        st.info(st.session_state.ai_port_text)

    # ポジション詳細
    if pos_m:
        st.markdown(f'<div class="section-header">📋 ポジション詳細</div>', unsafe_allow_html=True)
        for p in pos_details:
            cls = "profit" if p["pnl"] >= 0 else "urgent"
            pnl_c = "pnl-pos" if p["pnl"] >= 0 else "pnl-neg"
            st.markdown(f'''<div class="pos-card {cls}">
<div style="display: flex; justify-content: space-between; align-items: center;"><b>{p['ticker']}</b> ({p['sector']}) <span class="{pnl_c}">{p['pnl']:+.2f}%</span></div>
<div style="font-size: 0.9rem; margin-top: 5px;">{p['shares']} shares @ ${p['cost']:.2f} (Live: ${p['curr']:.2f})</div>
<div style="font-size: 0.9rem; color: #8b949e; margin-top: 5px;">評価額: ¥{p['val']*fx_rate:,.0f} (${p['val']:.2f})</div>
</div>''', unsafe_allow_html=True)
            if st.button(f"決済/削除 {p['ticker']}", key=f"cl_{p['ticker']}"):
                del p_j["positions"][p['ticker']]; save_portfolio_json(p_j); st.rerun()

    # 追加フォーム
    with st.form("add_port"):
        st.markdown("➕ **新規ポジション登録**")
        c1, c2, c3 = st.columns(3); ft = c1.text_input("銘柄コード").upper().strip(); fs = c2.number_input("株数", min_value=1); fc = c3.number_input("取得単価", min_value=0.01)
        if st.form_submit_button("登録") and ft:
            p_j["positions"][ft] = {"shares": fs, "avg_cost": fc}; save_portfolio_json(p_j); st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO SYSTEM | CORE ENGINE: MODULAR | UI: V7.4")

