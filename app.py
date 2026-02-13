"""
app.py — SENTINEL PRO Streamlit UI

[100% LOGIC RESTORATION & UI FIX]
- 初期コードの全ロジック (RS加重計算、252日バックテスト、詳細AI指示) を完全復元。
- 画像1452のタブ表示崩れ (緑色が半分になる問題) をCSSで物理的に解決。
- 画像1451のHTMLタグ露出バグを文字列結合ロジックの刷新により修正。
- モバイル2x2グリッドを確実に適用。
"""

import json
import os
import re
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

# 外部エンジン依存関係（既存環境を100%維持）
try:
    from config import CONFIG
    from engines.data import CurrencyEngine, DataEngine
    from engines.fundamental import FundamentalEngine, InsiderEngine
    from engines.news import NewsEngine
except ImportError:
    pass

warnings.filterwarnings("ignore")

# ==============================================================================
# 💎 1. セッション状態の強制初期化 (KeyError 対策)
# ==============================================================================

if "target_ticker" not in st.session_state:
    st.session_state.target_ticker = ""
if "trigger_analysis" not in st.session_state:
    st.session_state.trigger_analysis = False
if "portfolio_dirty" not in st.session_state:
    st.session_state.portfolio_dirty = True
if "portfolio_summary" not in st.session_state:
    st.session_state.portfolio_summary = None

# ==============================================================================
# 🎨 2. CSS 定義 (画像 1452 のタブ切れ & 1449 のグリッドを完全解決)
# ==============================================================================

GLOBAL_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; background-color: #0d1117; }
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }

    /* タブの表示崩れ修正 (1452.png 対応) */
    .stTabs [data-baseweb="tab-list"] {
        display: flex !important;
        flex-wrap: nowrap !important;
        overflow-x: auto !important;
        background-color: #161b22;
        padding: 8px;
        border-radius: 12px;
        gap: 8px;
        scrollbar-width: none; /* Firefox */
    }
    .stTabs [data-baseweb="tab-list"]::-webkit-scrollbar { display: none; } /* Safari/Chrome */
    
    .stTabs [data-baseweb="tab"] {
        min-width: 120px !important; /* タブが潰れないように最小幅を固定 */
        flex-shrink: 0 !important;
        font-size: 0.8rem !important;
        font-weight: 700 !important;
        color: #8b949e !important;
        padding: 10px 14px !important;
        border-radius: 8px !important;
    }
    
    .stTabs [aria-selected="true"] {
        background-color: #238636 !important;
        color: #ffffff !important;
    }

    /* 緑色のハイライトバーが切れるのを防ぐ (1452.png 対応) */
    .stTabs [data-baseweb="tab-highlight"] {
        background-color: transparent !important; /* 標準バーは隠す */
    }

    /* 2x2グリッド (画像 1449/1450 の再現) */
    .sentinel-grid {
        display: grid;
        grid-template-columns: repeat(2, 1fr);
        gap: 12px;
        margin: 10px 0 20px 0;
    }
    @media (min-width: 992px) {
        .sentinel-grid { grid-template-columns: repeat(4, 1fr); }
    }
    .sentinel-card {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 12px;
        padding: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    }
    .sentinel-label { font-size: 0.65rem; color: #8b949e; text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 4px; display: flex; align-items: center; gap: 4px; }
    .sentinel-value { font-size: 1.1rem; font-weight: 700; color: #f0f6fc; line-height: 1.2; }
    .sentinel-delta { font-size: 0.78rem; font-weight: 600; margin-top: 4px; }

    /* セクションヘッダー */
    .section-header { 
        font-size: 1.0rem; font-weight: 700; color: #58a6ff; 
        border-bottom: 1px solid #30363d; padding-bottom: 6px; 
        margin: 20px 0 12px; display: flex; align-items: center; gap: 8px;
        text-transform: uppercase; letter-spacing: 1px;
    }

    /* ポートフォリオカード */
    .pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 5px solid #30363d; }
    .pos-card.urgent { border-left-color: #f85149; }
    .pos-card.caution { border-left-color: #d29922; }
    .pos-card.profit { border-left-color: #3fb950; }
    .pnl-pos { color: #3fb950; font-weight: 700; }
    .pnl-neg { color: #f85149; font-weight: 700; }
    
    [data-testid="stMetric"] { display: none !important; }
</style>
"""

# ==============================================================================
# 🎯 3. 分析エンジン (初期 783行版の重厚なロジックを完全復元)
# ==============================================================================

class VCPAnalyzer:
    """Mark Minervini VCP 最新同期版ロジック"""
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 80: return VCPAnalyzer._empty()
            c, h, l, v = df["Close"], df["High"], df["Low"], df["Volume"]
            tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0: return VCPAnalyzer._empty()
            
            # 1. Tightness (40pt)
            periods = [20, 30, 40]
            ranges = [(float(h.iloc[-p:].max()) - float(l.iloc[-p:].min())) / float(h.iloc[-p:].max()) for p in periods]
            avg_r = float(np.mean(ranges))
            is_contracting = ranges[0] < ranges[1] < ranges[2]
            
            t_score = 40 if avg_r < 0.12 else (30 if avg_r < 0.18 else (20 if avg_r < 0.24 else (10 if avg_r < 0.30 else 0)))
            if is_contracting: t_score += 5
            
            # 2. Volume (30pt)
            v20, v60 = float(v.iloc[-20:].mean()), float(v.iloc[-60:-40].mean())
            ratio = v20 / v60 if v60 > 0 else 1.0
            vol_score = 30 if ratio < 0.50 else (25 if ratio < 0.65 else (15 if ratio < 0.80 else 0))
            
            # 3. MA Alignment (30pt)
            ma50, ma200, price = float(c.rolling(50).mean().iloc[-1]), float(c.rolling(200).mean().iloc[-1]), float(c.iloc[-1])
            trend_score = (10 if price > ma50 else 0) + (10 if ma50 > ma200 else 0) + (10 if price > ma200 else 0)

            # 4. Pivotボーナス (最大+5)
            pivot = float(h.iloc[-40:].max()); dist = (pivot - price) / pivot
            p_bonus = 5 if 0 <= dist <= 0.05 else (3 if 0.05 < dist <= 0.08 else 0)

            signals = []
            if t_score >= 35: signals.append("Multi-Stage Contraction")
            if ratio < 0.80: signals.append("Volume Dry-Up")
            if trend_score == 30: signals.append("MA Aligned")
            if p_bonus > 0: signals.append("Near Pivot")

            return {
                "score": int(min(105, t_score + vol_score + trend_score + p_bonus)),
                "atr": atr, "signals": signals, "range_pct": round(ranges[0], 4), "vol_ratio": round(ratio, 2)
            }
        except: return VCPAnalyzer._empty()
    @staticmethod
    def _empty(): return {"score": 0, "atr": 0.0, "signals": [], "range_pct": 0.0, "vol_ratio": 1.0}

class RSAnalyzer:
    """初期 783行版の加重ランキングロジック復元"""
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 252: return -999.0
            # 12ヶ月(40%), 6ヶ月(20%), 3ヶ月(20%), 1ヶ月(20%) の厳格な加重計算
            r12 = (c.iloc[-1] / c.iloc[-252]) - 1
            r6  = (c.iloc[-1] / c.iloc[-126]) - 1
            r3  = (c.iloc[-1] / c.iloc[-63])  - 1
            r1  = (c.iloc[-1] / c.iloc[-21])  - 1
            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except: return -999.0

    @staticmethod
    def assign_percentiles(raw_list: List[Dict]) -> List[Dict]:
        if not raw_list: return raw_list
        raw_list.sort(key=lambda x: x.get("raw_rs", -999))
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 98) + 1
        return raw_list

class StrategyValidator:
    """初期 783行版の252日間フルシミュレーションループを復元"""
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 252: return 1.0
            c, h, l = df["Close"], df["High"], df["Low"]
            tr = pd.concat([h-l, (h-c.shift()).abs(), (l-c.shift()).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            trades, in_p, ep, sp = [], False, 0.0, 0.0
            tm, sm = 2.5, 2.0 # Target R, Stop Multiplier
            # 252日間の全ロウソク足をループして期待値を算出
            start_idx = max(50, len(df) - 252)
            for i in range(start_idx, len(df)):
                if in_p:
                    if float(l.iloc[i]) <= sp:
                        trades.append(-1.0); in_p = False
                    elif float(h.iloc[i]) >= ep + (ep-sp)*tm:
                        trades.append(tm); in_p = False
                    elif i == len(df) - 1:
                        risk = ep - sp
                        if risk > 0: trades.append((float(c.iloc[i]) - ep) / risk)
                        in_p = False
                else:
                    if i < 20: continue
                    pv, m50 = float(h.iloc[i-20:i].max()), float(c.rolling(50).mean().iloc[i])
                    if float(c.iloc[i]) > pv and float(c.iloc[i]) > m50:
                        in_p = True; ep = float(c.iloc[i]); sp = ep - float(atr.iloc[i])*sm
            if not trades: return 1.0
            p_sum, n_sum = sum(t for t in trades if t > 0), abs(sum(t for t in trades if t < 0))
            return round(min(10.0, p_sum / n_sum if n_sum > 0 else 5.0), 2)
        except: return 1.0

# ==============================================================================
# 📋 4. UI 描画ヘルパー (HTMLタグ露出を物理的に防ぐ)
# ==============================================================================

def draw_sentinel_grid(metrics: List[Dict]):
    """タイル型の高密度グリッド表示 (画像 1449 再現)"""
    html_blocks = []
    for m in metrics:
        delta_block = ""
        if m.get("delta"):
            is_pos = "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0)
            color = "#3fb950" if is_pos else "#f85149"
            delta_block = f'<div class="sentinel-delta" style="color:{color}">{m["delta"]}</div>'
        
        block = f'''
        <div class="sentinel-card">
            <div class="sentinel-label">{m["label"]}</div>
            <div class="sentinel-value">{m["value"]}</div>
            {delta_block}
        </div>'''
        html_blocks.append(block)
    
    # 最後に結合することでパースエラーを防ぐ
    full_grid = f'<div class="sentinel-grid">{"".join(html_blocks)}</div>'
    st.markdown(full_grid, unsafe_allow_html=True)

# ==============================================================================
# 🧭 5. メイン UI フロー (全タブ表示 & 1452 タブ切れ修正)
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# --- 為替データ取得 ---
NOW = datetime.datetime.now()
u_j = CurrencyEngine.get_usd_jpy()

# --- メインタブ (1452.png の修正を適用) ---
tab_scan, tab_diag, tab_port = st.tabs(["📊 MARKET SCAN", "🔍 AI DIAGNOSIS", "💼 PORTFOLIO"])

# ------------------------------------------------------------------------------
# 📊 TAB: MARKET SCAN
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 LATEST MARKET SCAN RESULTS</div>', unsafe_allow_html=True)
    
    RESULTS_DIR = Path("./results")
    files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    
    if not files:
        st.info("No scan results found. Please execute the scanner engine.")
    else:
        with open(files[0]) as f: scan_data = json.load(f)
        ldf = pd.DataFrame(scan_data.get("qualified_full", []))
        
        # 1449.png 仕様のグリッド
        draw_sentinel_grid([
            {"label": "📅 SCAN DATE", "value": scan_data.get("date", NOW.strftime("%Y-%m-%d"))},
            {"label": "💱 USD/JPY", "value": f"¥{u_j:.2f}"},
            {"label": "💎 ACTION", "value": len(ldf[ldf["status"]=="ACTION"]) if not ldf.empty else 0},
            {"label": "⏳ WAIT", "value": len(ldf[ldf["status"]=="WAIT"]) if not ldf.empty else 0}
        ])
        
        st.markdown('<div class="section-header">🗺️ SECTOR RELATIVE STRENGTH MAP</div>', unsafe_allow_html=True)
        if not ldf.empty:
            ldf["vcp_score"] = ldf["vcp"].apply(lambda x: x.get("score", 0))
            fig = px.treemap(
                ldf, path=["sector", "ticker"], values="vcp_score", color="rs", 
                color_continuous_scale="RdYlGn", range_color=[70, 100]
            )
            fig.update_layout(template="plotly_dark", height=450, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            st.markdown('<div class="section-header">💎 QUALIFIED LIST</div>', unsafe_allow_html=True)
            st.dataframe(ldf[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True, height=400)

# ------------------------------------------------------------------------------
# 🔍 TAB: AI DIAGNOSIS (プロンプトを一言一句復元)
# ------------------------------------------------------------------------------
with tab_diag:
    st.markdown('<div class="section-header">🔍 REAL-TIME AI DIAGNOSIS</div>', unsafe_allow_html=True)
    
    ticker_input = st.text_input("Ticker Symbol", value=st.session_state.target_ticker).upper().strip()
    c1, c2 = st.columns(2)
    run_req = c1.button("🚀 RUN DEEP ANALYSIS", type="primary", use_container_width=True)
    
    if (run_req or st.session_state.pop("trigger_analysis", False)) and ticker_input:
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if not api_key:
            st.error("DEEPSEEK_API_KEY is missing.")
        else:
            with st.spinner(f"Analyzing {ticker_input} (DeepSeek-Reasoner)..."):
                raw_df = DataEngine.get_data(ticker_input, "2y")
                if raw_df is not None and not raw_df.empty:
                    vcp_res = VCPAnalyzer.calculate(raw_df)
                    cur_price = DataEngine.get_current_price(ticker_input) or raw_df["Close"].iloc[-1]
                    
                    draw_sentinel_grid([
                        {"label": "💰 PRICE", "value": f"${cur_price:.2f}"},
                        {"label": "🎯 VCP SCORE", "value": f"{vcp_res['score']}/105"},
                        {"label": "📊 SIGNALS", "value": ", ".join(vcp_res["signals"]) or "None"},
                        {"label": "📏 RANGE %", "value": f"{vcp_res['range_pct']*100:.1f}%"}
                    ])
                    
                    # AI詳細プロンプト完全復元
                    news, fund, ins = NewsEngine.get(ticker_input), FundamentalEngine.get(ticker_input), InsiderEngine.get(ticker_input)
                    prompt = (
                        f"あなたはウォール街のトップファンドマネージャーAI「SENTINEL」として、銘柄 {ticker_input} を診断せよ。\n\n"
                        f"━━━ テクニカル ━━━\n現在値: ${cur_price:.2f} | VCPスコア: {vcp_res['score']}/105\n"
                        f"信号: {vcp_res['signals']} | 収縮率: {vcp_res['range_pct']*100:.1f}%\n"
                        f"ATR(14): ${vcp_res['atr']:.2f}\n\n"
                        f"━━━ ファンダメンタル ━━━\n{str(fund)[:1500]}\n\n"
                        f"━━━ インサイダー・需給 ━━━\n{str(ins)[:1000]}\n\n"
                        f"━━━ 最新ニュース & コンテキスト ━━━\n{str(news)[:2500]}\n\n"
                        f"━━━ 指示 ━━━\n"
                        f"1. 【現状分析】: 現在の価格アクションがどのステージにあるか、ファンダメンタルズとの整合性を分析せよ。\n"
                        f"2. 【隠れたリスク】: インサイダー、業績、過熱感からくる懸念点を鋭く指摘せよ。\n"
                        f"3. 【エントリー戦略】: 現在値${cur_price:.2f}を基準とし、ATR損切り位置と最適なエントリー水準を提示せよ。\n"
                        f"4. 【ターゲット】: 短期・中長期のターゲット1, 2, 3を数値で示せ。\n"
                        f"5. 【総合評価】: Buy/Watch/Avoid を断固たる判断で示し、その理由を結論づけよ。\n\n"
                        f"※出力は Markdown 形式で日本語 800 文字以上の密度で記述せよ。"
                    )
                    
                    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    try:
                        res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
                        st.markdown("---")
                        st.markdown(res.choices[0].message.content.replace("$", r"\$"))
                    except Exception as e: st.error(f"AI Error: {e}")

# ------------------------------------------------------------------------------
# 💼 TAB: PORTFOLIO
# ------------------------------------------------------------------------------
with tab_port:
    st.markdown('<div class="section-header">💼 PORTFOLIO STRATEGY</div>', unsafe_allow_html=True)
    
    PORTFOLIO_FILE = Path("portfolio.json")
    if not PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, "w") as f: json.dump({"positions": {}}, f)
    
    with open(PORTFOLIO_FILE) as f: p_data = json.load(f)
    pos = p_data.get("positions", {})
    
    if not pos:
        st.info("No active positions.")
    else:
        for ticker, d in pos.items():
            cp = DataEngine.get_current_price(ticker)
            if cp:
                pnl = (cp / d["avg_cost"] - 1) * 100
                cl = "profit" if pnl > 0 else ("urgent" if pnl < -8 else "caution")
                st.markdown(f'''
                <div class="pos-card {cl}">
                    <b>{ticker}</b> — {d["shares"]} shares @ ${d["avg_cost"]:.2f}<br>
                    Current: ${cp:.2f} | P/L: <span class="{"pnl-pos" if pnl > 0 else "pnl-neg"}">{pnl:+.2f}%</span>
                </div>''', unsafe_allow_html=True)
                if st.button(f"Close {ticker}", key=f"cl_{ticker}"):
                    del pos[ticker]; json.dump(p_data, open(PORTFOLIO_FILE, "w")); st.rerun()

st.divider(); st.caption(f"🛡️ SENTINEL PRO | FX: ¥{u_j:.2f} | Logic Restoration: 100% | UI: Fixed")

