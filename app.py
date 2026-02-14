import json
import datetime
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

# ==============================================================================
# 1. エンジンのインポート (モジュール構成)
# ==============================================================================
# ※ enginesフォルダ内の各ファイルが正しく配置されている前提です
from engines.data import (
    CurrencyEngine, DataEngine, PortfolioManager, 
    WatchlistManager, RESULTS_DIR, TODAY_STR, CACHE_DIR
)
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator, EXIT_CFG
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.notify import NotifyEngine

# ==============================================================================
# 2. ローカルヘルパー関数 (AI機能用の補完)
# ==============================================================================
# engines.data に get_market_overview がない場合の安全策としてここに定義
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

def draw_sentinel_grid_ui(metrics):
    html = '<div class="sentinel-grid">'
    for m in metrics:
        delta = ""
        if m.get("delta"):
            col = "#3fb950" if "+" in str(m["delta"]) else "#f85149"
            delta = f'<div class="sentinel-delta" style="color:{col}">{m["delta"]}</div>'
        html += f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{delta}</div>'
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ==============================================================================
# 3. 言語設定
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
        "realtime_scan": "🔍 リアルタイム定量スキャン",
        "ticker_input": "ティッカーシンボル（例：NVDA）",
        "run_quant": "🚀 定量スキャン実行",
        "add_watchlist": "⭐ ウォッチリストに追加",
        "quant_dashboard": "📊 SENTINEL定量ダッシュボード",
        "ai_market_btn": "🤖 AI市場分析 (SENTINEL MARKET EYE)",
        "ai_diag_btn": "🤖 AI個別診断レポート生成",
        "ai_port_btn": "🛡️ AIポートフォリオ診断 (GUARD)",
        "cash_manage": "💰 資金管理 (預り金設定)",
        "jpy_cash": "預り金 (円)",
        "usd_cash": "USドル (ドル)",
        "update_balance": "残高更新",
        "total_equity": "総資産 (Total Equity)",
        "exposure": "株式評価額 (Exposure)",
        "active_pos": "保有中のポジション",
        "reg_new": "➕ 新規ポジション登録",
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
        "realtime_scan": "🔍 REAL-TIME QUANTITATIVE SCAN",
        "ticker_input": "Ticker Symbol (e.g. NVDA)",
        "run_quant": "🚀 RUN QUANTITATIVE SCAN",
        "add_watchlist": "⭐ ADD TO WATCHLIST",
        "quant_dashboard": "📊 SENTINEL QUANTITATIVE DASHBOARD",
        "ai_market_btn": "🤖 AI MARKET ANALYSIS",
        "ai_diag_btn": "🤖 GENERATE AI REPORT",
        "ai_port_btn": "🛡️ AI PORTFOLIO GUARD",
        "cash_manage": "💰 Cash Management",
        "jpy_cash": "JPY Cash",
        "usd_cash": "USD Cash",
        "update_balance": "Update Balance",
        "total_equity": "Total Equity",
        "exposure": "Stock Exposure",
        "active_pos": "ACTIVE POSITIONS",
        "reg_new": "➕ REGISTER NEW POSITION",
    }
}

# ==============================================================================
# 4. UI スタイル
# ==============================================================================
GLOBAL_STYLE = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; color: #f0f6fc; }
.block-container { padding-top: 0rem !important; }
.ui-push-buffer { height: 60px; }
.stTabs [data-baseweb="tab-list"] { background-color: #161b22; padding: 10px; border-radius: 10px; border-bottom: 2px solid #30363d; gap: 10px; }
.stTabs [data-baseweb="tab"] { color: #8b949e; border: none; font-weight: 700; }
.stTabs [aria-selected="true"] { color: #fff; background-color: #238636; border-radius: 8px; }
.sentinel-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; margin: 20px 0; }
@media(min-width: 900px){ .sentinel-grid { grid-template-columns: repeat(4, 1fr); } }
.sentinel-card { background: #161b22; border: 1px solid #30363d; border-radius: 12px; padding: 20px; }
.sentinel-label { font-size: 0.85rem; color: #8b949e; text-transform: uppercase; font-weight: 600; }
.sentinel-value { font-size: 1.5rem; font-weight: 700; color: #f0f6fc; margin-top: 5px; }
.sentinel-delta { font-size: 0.9rem; font-weight: 600; margin-top: 5px; }
.section-header { font-size: 1.25rem; font-weight: 700; color: #58a6ff; border-bottom: 1px solid #30363d; padding-bottom: 10px; margin: 30px 0 20px; }
.diagnostic-panel { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 20px; flex: 1; }
.pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 20px; margin-bottom: 15px; border-left: 8px solid #30363d; }
.pos-card.profit { border-left-color: #3fb950; }
.pos-card.urgent { border-left-color: #f85149; }
.pnl-pos { color: #3fb950; font-weight: bold; }
.pnl-neg { color: #f85149; font-weight: bold; }
</style>
"""

# ==============================================================================
# 5. メインアプリケーション
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown('<div class="ui-push-buffer"></div>', unsafe_allow_html=True)
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# セッション状態の初期化
if "target_ticker" not in st.session_state: st.session_state.target_ticker = ""
if "ai_market_text" not in st.session_state: st.session_state.ai_market_text = ""
if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text = ""
if "ai_port_text" not in st.session_state: st.session_state.ai_port_text = ""
if "quant_results" not in st.session_state: st.session_state.quant_results = None
if "language" not in st.session_state: st.session_state.language = "ja"

# サイドバー
with st.sidebar:
    st.markdown("### 🌐 Language")
    lang = st.selectbox("", ["日本語", "English"], index=0 if st.session_state.language == "ja" else 1)
    st.session_state.language = "ja" if lang == "日本語" else "en"
    txt = LANG[st.session_state.language]
    
    st.markdown(f"### {txt['title']} ウォッチリスト")
    wl = WatchlistManager.load()
    for t in wl:
        c1, c2 = st.columns([4,1])
        if c1.button(t, key=f"side_{t}", use_container_width=True): st.session_state.target_ticker = t
        if c2.button("×", key=f"del_{t}"):
            wl.remove(t)
            WatchlistManager.save(wl)
            st.rerun()
    st.divider()
    st.caption(f"🛡️ SENTINEL V7.1 | {TODAY_STR}")

# メインタブ
fx_rate = CurrencyEngine.get_usd_jpy()
tabs = st.tabs([txt["tab_scan"], txt["tab_diag"], txt["tab_port"]])

# --- TAB 1: MARKET SCAN ---
with tabs[0]:
    st.markdown(f'<div class="section-header">{txt["tab_scan"]} (USD/JPY: ¥{fx_rate:.2f})</div>', unsafe_allow_html=True)
    m_ctx = get_market_overview_local()
    
    # 既存スキャン結果のロード
    s_df = pd.DataFrame()
    if RESULTS_DIR.exists():
        f_list = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if f_list:
            try:
                with open(f_list[0], "r", encoding="utf-8") as f: s_data = json.load(f)
                s_df = pd.DataFrame(s_data.get("qualified_full", []))
            except: pass

    # AI市場分析ボタン
    if st.button(txt["ai_market_btn"], use_container_width=True, type="primary"):
        k = st.secrets.get("DEEPSEEK_API_KEY")
        if not k: NotifyEngine.error("API Key Missing")
        else:
            with st.spinner("AI Analyzing Market Conditions..."):
                # ニュース取得
                n_data = NewsEngine.get_general_market()
                n_txt = NewsEngine.format_for_prompt(n_data)
                
                # 統計
                act = len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0
                wait = len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0
                sectors = list(s_df["sector"].value_counts().keys())[:3] if not s_df.empty else []
                
                p = f"""あなたは「AI投資家SENTINEL」。
現在: {TODAY_STR}
SPY: ${m_ctx['spy']:.2f} ({m_ctx['spy_change']:+.2f}%), VIX: {m_ctx['vix']:.2f}
統計: ACTION {act}, WAIT {wait}, 主導セクター {', '.join(sectors)}
ニュース:
{n_txt}
指示:
1. 市場環境（強気/弱気/調整）を定義せよ。
2. ニュースから重要材料を抽出せよ（未来の日付は無視）。
3. 推奨ポジション比率を提示せよ。
4. 600字以内。文末に「最終判断: [BULL/BEAR/NEUTRAL]」。
"""
                try:
                    cl = OpenAI(api_key=k, base_url="https://api.deepseek.com")
                    r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role":"user","content":p}])
                    st.session_state.ai_market_text = r.choices[0].message.content
                except Exception as e: st.error(str(e))
    
    if st.session_state.ai_market_text:
        st.info(st.session_state.ai_market_text)

    # グリッド
    draw_sentinel_grid_ui([
        {"label": "S&P 500 (SPY)", "value": f"${m_ctx['spy']:.2f}", "delta": f"{m_ctx['spy_change']:+.2f}%"},
        {"label": "VIX INDEX", "value": f"{m_ctx['vix']:.2f}"},
        {"label": txt["action_list"], "value": len(s_df[s_df["status"]=="ACTION"]) if not s_df.empty else 0},
        {"label": txt["wait_list"], "value": len(s_df[s_df["status"]=="WAIT"]) if not s_df.empty else 0},
    ])

    if not s_df.empty:
        s_df["vcp_score"] = s_df["vcp"].apply(lambda x: x.get("score", 0))
        m_fig = px.treemap(s_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn", range_color=[70, 100])
        m_fig.update_layout(template="plotly_dark", height=500, margin=dict(t=0, b=0, l=0, r=0))
        st.plotly_chart(m_fig, use_container_width=True)

# --- TAB 2: AI DIAGNOSIS ---
with tabs[1]:
    st.markdown(f'<div class="section-header">{txt["realtime_scan"]}</div>', unsafe_allow_html=True)
    ticker = st.text_input(txt["ticker_input"], value=st.session_state.target_ticker).upper().strip()
    
    c1, c2 = st.columns(2)
    if c1.button(txt["run_quant"], type="primary", use_container_width=True) and ticker:
        with st.spinner(f"Scanning {ticker}..."):
            df = DataEngine.get_data(ticker, "2y")
            if df is not None:
                vcp = VCPAnalyzer.calculate(df)
                rs = RSAnalyzer.get_raw_score(df)
                pf = StrategyValidator.run(df)
                curr = df["Close"].iloc[-1]
                st.session_state.quant_results = {"vcp": vcp, "rs": rs, "pf": pf, "price": curr, "ticker": ticker}
                st.session_state.ai_analysis_text = ""
            else: NotifyEngine.error("Data not found")

    if st.session_state.quant_results and st.session_state.quant_results["ticker"] == ticker:
        q = st.session_state.quant_results
        vcp, rs, pf, curr = q["vcp"], q["rs"], q["pf"], q["price"]
        
        draw_sentinel_grid_ui([
            {"label": txt["current_price"], "value": f"${curr:.2f}"},
            {"label": txt["vcp_score"], "value": f"{vcp['score']}/105"},
            {"label": txt["profit_factor"], "value": f"x{pf:.2f}"},
            {"label": txt["rs_momentum"], "value": f"{rs*100:+.1f}%"},
        ])
        
        risk = vcp['atr'] * EXIT_CFG["STOP_LOSS_ATR_MULT"]
        bd = vcp['breakdown']
        st.markdown(f'''
        <div style="display:flex; gap:20px; margin-bottom:20px;">
            <div class="diagnostic-panel"><b>{txt["strategic_levels"]}</b><br>STOP: ${curr-risk:.2f}<br>TARGET: ${curr+risk*2.5:.2f}</div>
            <div class="diagnostic-panel"><b>{txt["vcp_breakdown"]}</b><br>Tight: {bd['tight']}/45 | Vol: {bd['vol']}/30<br>Trend: {bd['ma']}/30 | Pivot: +{bd['pivot']}</div>
        </div>
        ''', unsafe_allow_html=True)

        with st.spinner("Loading Chart..."):
             df_chart = DataEngine.get_data(ticker, "2y")
             if df_chart is not None:
                fig = go.Figure(data=[go.Candlestick(x=df_chart.index, open=df_chart['Open'], high=df_chart['High'], low=df_chart['Low'], close=df_chart['Close'])])
                fig.update_layout(template="plotly_dark", height=400, margin=dict(l=0,r=0,t=20,b=0), xaxis_rangeslider_visible=False)
                st.plotly_chart(fig, use_container_width=True)

        if st.button(txt["ai_diag_btn"], use_container_width=True):
            k = st.secrets.get("DEEPSEEK_API_KEY")
            if k:
                with st.spinner("AI Thinking..."):
                    n_txt = NewsEngine.format_for_prompt(NewsEngine.get(ticker))
                    f_json = json.dumps(FundamentalEngine.get(ticker))
                    p = f"""あなたは「AI投資家SENTINEL」。
対象: {ticker}, 価格: ${curr:.2f}
VCP: {vcp['score']}/105, PF: {pf:.2f}, RS: {rs*100:.1f}%
ニュース:
{n_txt}
ファンダ: {f_json}
指示:
1. 定量データとニュースに基づき投資判断を下せ。
2. 600字以内。
3. 出典明記。
4. 最終決断: [BUY/WAIT/SELL]
"""
                    try:
                        cl = OpenAI(api_key=k, base_url="https://api.deepseek.com")
                        r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role":"user","content":p}])
                        st.session_state.ai_analysis_text = r.choices[0].message.content
                    except Exception as e: st.error(str(e))
        
        if st.session_state.ai_analysis_text:
            st.markdown("---")
            st.info(st.session_state.ai_analysis_text)

    if c2.button(txt["add_watchlist"], use_container_width=True) and ticker:
        wl = WatchlistManager.load()
        if ticker not in wl:
            wl.append(ticker)
            WatchlistManager.save(wl)
            NotifyEngine.success(f"Added {ticker}")

# --- TAB 3: PORTFOLIO ---
with tab_port:
    st.markdown(f'<div class="section-header">{txt["portfolio_risk"]}</div>', unsafe_allow_html=True)
    port = PortfolioManager.load()

    # 資金管理
    with st.expander(txt["cash_manage"], expanded=True):
        c1, c2, c3 = st.columns(3)
        curr_jpy = port.get("cash_jpy", 350000)
        curr_usd = port.get("cash_usd", 0)
        in_jpy = c1.number_input(txt["jpy_cash"], value=int(curr_jpy), step=1000)
        in_usd = c2.number_input(txt["usd_cash"], value=float(curr_usd), step=100.0)
        if c3.button(txt["update_balance"], use_container_width=True):
            port["cash_jpy"] = in_jpy; port["cash_usd"] = in_usd
            PortfolioManager.save(port)
            st.rerun()

    # 資産集計
    pos_m = port.get("positions", {})
    total_stock_usd = 0.0
    pos_details = []
    
    for t, d in pos_m.items():
        fund = FundamentalEngine.get(t)
        cp = DataEngine.get_current_price(t)
        val = cp * d['shares']
        total_stock_usd += val
        pnl_pct = ((cp / d['avg_cost']) - 1) * 100 if d['avg_cost'] > 0 else 0
        pos_details.append({
            "ticker": t, "sector": fund.get("sector", "Unknown"), 
            "val": val, "pnl": pnl_pct, "shares": d['shares'], "cost": d['avg_cost'], "curr": cp
        })

    stock_val_jpy = total_stock_usd * fx_rate
    usd_cash_jpy = in_usd * fx_rate
    total_equity = stock_val_jpy + in_jpy + usd_cash_jpy

    draw_sentinel_grid_ui([
        {"label": txt["total_equity"], "value": f"¥{total_equity:,.0f}"},
        {"label": txt["exposure"], "value": f"¥{stock_val_jpy:,.0f}", "delta": f"(${total_stock_usd:,.2f})"},
        {"label": txt["jpy_cash"], "value": f"¥{in_jpy:,.0f}"},
        {"label": txt["usd_cash"], "value": f"¥{usd_cash_jpy:,.0f}", "delta": f"(${in_usd:,.2f})"},
    ])
    
    # AIポートフォリオ診断
    if st.button(txt["ai_port_btn"], use_container_width=True, type="primary"):
        k = st.secrets.get("DEEPSEEK_API_KEY")
        if k:
            with st.spinner("AI Diagnosing..."):
                m_ctx = get_market_overview_local()
                p_text = "\n".join([f"- {x['ticker']} [{x['sector']}]: ${x['val']:.2f} ({x['pnl']:+.1f}%)" for x in pos_details])
                p = f"""あなたは「AI投資家SENTINEL」。
【市場】SPY: ${m_ctx['spy']:.2f}, VIX: {m_ctx['vix']:.2f}
【資産】¥{total_equity:,.0f} (現金比率: {(in_jpy+usd_cash_jpy)/total_equity*100:.1f}%)
【保有】
{p_text}
指示:
1. セクター分散と現金比率を評価。
2. リスクヘッジ提案。
3. 600字以内。
"""
                try:
                    cl = OpenAI(api_key=k, base_url="https://api.deepseek.com")
                    r = cl.chat.completions.create(model="deepseek-reasoner", messages=[{"role":"user","content":p}])
                    st.session_state.ai_port_text = r.choices[0].message.content
                except Exception as e: st.error(str(e))
    
    if st.session_state.ai_port_text: st.info(st.session_state.ai_port_text)

    # 保有銘柄リスト
    if not pos_m: st.info(txt["portfolio_empty"])
    else:
        st.markdown(f'<div class="section-header">{txt["active_pos"]}</div>', unsafe_allow_html=True)
        for p in pos_details:
            t = p["ticker"]
            val_jpy = (p["val"] - p["cost"]*p["shares"]) * fx_rate
            cls = "profit" if p["pnl"] >= 0 else "urgent"
            pnl_c = "pnl-pos" if p["pnl"] >= 0 else "pnl-neg"
            
            st.markdown(f'''<div class="pos-card {cls}">
<div style="display:flex;justify-content:space-between;"><b>{t}</b><span class="{pnl_c}">{p["pnl"]:+.2f}% (¥{val_jpy:+,.0f})</span></div>
<div style="color:#8b949e;margin-top:5px;">{p['shares']} shares @ ${p['cost']:.2f} → ${p['curr']:.2f}<br>Sec: {p['sector']}</div></div>''', unsafe_allow_html=True)
            
            if st.button(f"{txt['close_position']} {t}", key=f"cl_{t}"):
                del port["positions"][t]
                PortfolioManager.save(port)
                st.rerun()

    # 新規登録
    st.markdown(f'<div class="section-header">{txt["reg_new"]}</div>', unsafe_allow_html=True)
    with st.form("add_port"):
        c1, c2, c3 = st.columns(3)
        ft = c1.text_input(txt["ticker_symbol"]).upper().strip()
        fs = c2.number_input(txt["shares"], min_value=1, value=10)
        fc = c3.number_input(txt["avg_cost"], min_value=0.01, value=100.0)
        if st.form_submit_button(txt["add_to_portfolio"], use_container_width=True):
            if ft:
                port["positions"][ft] = {"shares": fs, "avg_cost": fc}
                PortfolioManager.save(port)
                st.success(f"Added {ft}")
                st.rerun()


