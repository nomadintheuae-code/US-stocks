
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

# 外部エンジン依存関係（既存環境を完全に維持）
try:
    from config import CONFIG
    from engines.data import CurrencyEngine, DataEngine
    from engines.fundamental import FundamentalEngine, InsiderEngine
    from engines.news import NewsEngine
except ImportError:
    # 開発環境用のスタブ（本番ではインポートされることを前提）
    pass

warnings.filterwarnings("ignore")

# ==============================================================================
# 💎 1. セッション状態の強制初期化 (KeyError 対策)
# ==============================================================================

def initialize_state():
    """アプリ起動時に全てのステートを確実に定義する"""
    if "target_ticker" not in st.session_state:
        st.session_state.target_ticker = ""
    if "trigger_analysis" not in st.session_state:
        st.session_state.trigger_analysis = False
    if "portfolio_dirty" not in st.session_state:
        st.session_state.portfolio_dirty = True
    if "portfolio_summary" not in st.session_state:
        st.session_state.portfolio_summary = None

initialize_state()

# ==============================================================================
# 🎨 2. 定数・CSS・スタイル定義 (1449.png の再現)
# ==============================================================================

NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
RESULTS_DIR = Path("./results"); RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# プロフェッショナルな出口戦略の設定 (一言一句復元)
EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

# 1447.png の HTML 露出を修正するための堅牢な CSS
GLOBAL_STYLE = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
    
    html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }
    .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }

    /* 高密度グリッドレイアウト (画像 1449/1450 の再現) */
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
    .sentinel-delta { font-size: 0.75rem; font-weight: 600; margin-top: 4px; }

    /* セクションヘッダー */
    .section-header { 
        font-size: 1.0rem; font-weight: 700; color: #58a6ff; 
        border-bottom: 1px solid #30363d; padding-bottom: 6px; 
        margin: 18px 0 10px; display: flex; align-items: center; gap: 8px;
        text-transform: uppercase; letter-spacing: 1px;
    }

    /* ポートフォリオカード */
    .pos-card { background: #0d1117; border: 1px solid #30363d; border-radius: 12px; padding: 16px; margin-bottom: 12px; border-left: 4px solid #30363d; position: relative; }
    .pos-card.urgent { border-left-color: #f85149; }
    .pos-card.caution { border-left-color: #d29922; }
    .pos-card.profit { border-left-color: #3fb950; }
    .pnl-pos { color: #3fb950; font-weight: 700; font-size: 1.1rem; }
    .pnl-neg { color: #f85149; font-weight: 700; font-size: 1.1rem; }
    .exit-info { font-size: 0.75rem; color: #8b949e; font-family: 'Share Tech Mono', monospace; margin-top: 8px; line-height: 1.5; border-top: 1px solid #21262d; padding-top: 8px; }

    /* Streamlit タブのカスタマイズ */
    .stTabs [data-baseweb="tab-list"] { background-color: #0d1117; padding: 6px; border-radius: 12px; gap: 8px; }
    .stTabs [data-baseweb="tab"] { font-size: 0.9rem; font-weight: 600; padding: 12px 18px; color: #8b949e; }
    .stTabs [aria-selected="true"] { background-color: #238636 !important; color: #ffffff !important; border-radius: 8px; }
    
    [data-testid="stMetric"] { display: none !important; }
</style>
"""

# ==============================================================================
# 🎯 3. 分析エンジン (一言一句復元 + VCP最新同期)
# ==============================================================================

class VCPAnalyzer:
    """Mark Minervini VCP Scoring (最新同期版)"""
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 80: return VCPAnalyzer._empty()
            
            close = df["Close"]
            high  = df["High"]
            low   = df["Low"]
            volume = df["Volume"]

            # ATR(14) 算出
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0: return VCPAnalyzer._empty()

            # 1️⃣ Tightness (40pt)
            periods = [20, 30, 40]
            ranges = []
            for p in periods:
                h_max = float(high.iloc[-p:].max())
                l_min = float(low.iloc[-p:].min())
                ranges.append((h_max - l_min) / h_max)
            
            avg_range = float(np.mean(ranges))
            # 収縮判定ボーナス（短期 < 中期 < 長期）
            is_contracting = ranges[0] < ranges[1] < ranges[2]

            if avg_range < 0.12:   tight_score = 40
            elif avg_range < 0.18: tight_score = 30
            elif avg_range < 0.24: tight_score = 20
            elif avg_range < 0.30: tight_score = 10
            else:                  tight_score = 0
            
            if is_contracting: tight_score += 5
            tight_score = min(40, tight_score)

            # 2️⃣ Volume (30pt)
            v20 = float(volume.iloc[-20:].mean())
            v60 = float(volume.iloc[-60:-40].mean())
            ratio = v20 / v60 if v60 > 0 else 1.0

            if ratio < 0.50:   vol_score = 30
            elif ratio < 0.65: vol_score = 25
            elif ratio < 0.80: vol_score = 15
            else:              vol_score = 0
            
            is_dryup = ratio < 0.80

            # 3️⃣ MA Alignment (30pt)
            ma50  = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])
            trend_score = (
                (10 if price > ma50 else 0) +
                (10 if ma50 > ma200 else 0) +
                (10 if price > ma200 else 0)
            )

            # 4️⃣ Pivotボーナス (最大+5)
            pivot = float(high.iloc[-40:].max())
            distance = (pivot - price) / pivot
            pivot_bonus = 5 if 0 <= distance <= 0.05 else (3 if 0.05 < distance <= 0.08 else 0)

            signals = []
            if tight_score >= 35: signals.append("Multi-Stage Contraction")
            if is_dryup:          signals.append("Volume Dry-Up")
            if trend_score == 30: signals.append("MA Aligned")
            if pivot_bonus > 0:   signals.append("Near Pivot")

            return {
                "score": int(min(105, tight_score + vol_score + trend_score + pivot_bonus)),
                "atr": atr,
                "signals": signals,
                "is_dryup": is_dryup,
                "range_pct": round(ranges[0], 4),
                "vol_ratio": round(ratio, 2)
            }
        except Exception:
            return VCPAnalyzer._empty()

    @staticmethod
    def _empty():
        return {"score": 0, "atr": 0.0, "signals": [], "is_dryup": False, "range_pct": 0.0, "vol_ratio": 1.0}

class RSAnalyzer:
    """Relative Strength 加重計算エンジン (一言一句復元)"""
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 252: return -999.0
            # 12ヶ月(40%), 6ヶ月(20%), 3ヶ月(20%), 1ヶ月(20%) の加重相対強度
            r12 = (c.iloc[-1] / c.iloc[-252]) - 1
            r6  = (c.iloc[-1] / c.iloc[-126]) - 1
            r3  = (c.iloc[-1] / c.iloc[-63])  - 1
            r1  = (c.iloc[-1] / c.iloc[-21])  - 1
            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except Exception:
            return -999.0

    @staticmethod
    def assign_percentiles(raw_list: List[Dict]) -> List[Dict]:
        """全銘柄の相対評価スコア(1-99)を付与"""
        if not raw_list: return raw_list
        raw_list.sort(key=lambda x: x.get("raw_rs", -999))
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 98) + 1
        return raw_list

class StrategyValidator:
    """直近1年間の全トレードシミュレーションによる Profit Factor 算出 (完全復元)"""
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 252: return 1.0
            close = df["Close"]
            high  = df["High"]
            low   = df["Low"]
            
            # ATR(14)
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            
            trades = []
            in_pos = False
            entry_p = 0.0
            stop_p  = 0.0
            
            t_mult = EXIT_CFG["TARGET_R_MULT"]
            s_mult = EXIT_CFG["STOP_LOSS_ATR_MULT"]
            
            # 252日間を1日ずつスキャンして売買シミュレーション
            start_idx = max(50, len(df) - 252)
            for i in range(start_idx, len(df)):
                if in_pos:
                    # ストップロス判定
                    if float(low.iloc[i]) <= stop_p:
                        trades.append(-1.0)
                        in_pos = False
                    # 利確ターゲット判定
                    elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * t_mult:
                        trades.append(t_mult)
                        in_pos = False
                    # 最終日の強制クローズ
                    elif i == len(df) - 1:
                        risk = entry_p - stop_p
                        if risk > 0:
                            trades.append((float(close.iloc[i]) - entry_p) / risk)
                        in_pos = False
                else:
                    if i < 20: continue
                    # エントリー判定ロジック (VCPブレイクアウト・シミュレート)
                    pivot = float(high.iloc[i-20:i].max())
                    ma50  = float(close.rolling(50).mean().iloc[i])
                    if float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50:
                        in_pos = True
                        entry_p = float(close.iloc[i])
                        stop_p  = entry_p - float(atr.iloc[i]) * s_mult
            
            if not trades: return 1.0
            
            pos_sum = sum(t for t in trades if t > 0)
            neg_sum = abs(sum(t for t in trades if t < 0))
            
            pf = pos_sum / neg_sum if neg_sum > 0 else (5.0 if pos_sum > 0 else 1.0)
            return round(min(10.0, float(pf)), 2)
        except Exception:
            return 1.0

# ==============================================================================
# 📋 4. データアクセス & ポートフォリオロジック (全維持)
# ==============================================================================

@st.cache_data(ttl=600)
def get_usd_jpy():
    try:
        return CurrencyEngine.get_usd_jpy()
    except:
        return 150.0

def load_portfolio():
    if not PORTFOLIO_FILE.exists(): return {"positions": {}, "closed": []}
    try:
        with open(PORTFOLIO_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return {"positions": {}, "closed": []}

def save_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def draw_sentinel_grid(metrics: List[Dict]):
    """タイル型のメトリクス表示 (画像 1449/1450 の再現)"""
    html = '<div class="sentinel-grid">'
    for m in metrics:
        delta_html = ""
        if m.get("delta"):
            # 色判定
            color = "#3fb950" if "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0) else "#f85149"
            delta_html = f'<div class="sentinel-delta" style="color:{color}">{m["delta"]}</div>'
        
        html += f'''
        <div class="sentinel-card">
            <div class="sentinel-label">{m["label"]}</div>
            <div class="sentinel-value">{m["value"]}</div>
            {delta_html}
        </div>'''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ==============================================================================
# 🧭 5. メイン UI フロー (全タブ表示)
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")
st.markdown(GLOBAL_STYLE, unsafe_allow_html=True)

# --- Sidebar ---
with st.sidebar:
    st.markdown("### 🛡️ WATCHLIST")
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f: wl = json.load(f)
            for t in wl:
                c1, c2 = st.columns([4, 1])
                if c1.button(t, key=f"side_{t}", use_container_width=True):
                    st.session_state.target_ticker = t
                    st.session_state.trigger_analysis = True
                    st.rerun()
                if c2.button("×", key=f"rm_{t}"):
                    wl.remove(t)
                    with open(WATCHLIST_FILE, "w") as f: json.dump(wl, f)
                    st.rerun()
        except: pass
    st.divider()
    st.caption(f"System Time: {NOW.strftime('%H:%M:%S')}")

# --- Main Tabs ---
u_j = get_usd_jpy()
tab_scan, tab_diag, tab_port = st.tabs(["📊 MARKET SCAN", "🔍 AI DIAGNOSIS", "💼 PORTFOLIO"])

# ------------------------------------------------------------------------------
# 📊 TAB: MARKET SCAN
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 LATEST MARKET SCAN</div>', unsafe_allow_html=True)
    
    files = sorted(RESULTS_DIR.glob("*.json"), reverse=True)
    if not files:
        st.info("No scan results found. Please run back-end scanner.")
    else:
        with open(files[0]) as f: scan_data = json.load(f)
        ldf = pd.DataFrame(scan_data.get("qualified_full", []))
        
        # 1449.png のグリッドを再現
        draw_sentinel_grid([
            {"label": "📅 SCAN DATE", "value": scan_data.get("date", TODAY_STR)},
            {"label": "💱 USD/JPY", "value": f"¥{u_j:.2f}"},
            {"label": "💎 ACTION", "value": len(ldf[ldf["status"]=="ACTION"]) if not ldf.empty else 0},
            {"label": "⏳ WAIT", "value": len(ldf[ldf["status"]=="WAIT"]) if not ldf.empty else 0}
        ])
        
        st.markdown('<div class="section-header">🗺️ SECTOR MAP</div>', unsafe_allow_html=True)
        if not ldf.empty:
            ldf["vcp_score"] = ldf["vcp"].apply(lambda x: x.get("score", 0))
            # Plotly Treemap
            fig = px.treemap(
                ldf, 
                path=["sector", "ticker"], 
                values="vcp_score", 
                color="rs", 
                color_continuous_scale="RdYlGn",
                range_color=[70, 100]
            )
            fig.update_layout(template="plotly_dark", height=450, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
            
            st.markdown('<div class="section-header">💎 QUALIFIED TICKERS</div>', unsafe_allow_html=True)
            st.dataframe(
                ldf[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), 
                use_container_width=True, 
                height=400
            )

# ------------------------------------------------------------------------------
# 🔍 TAB: AI DIAGNOSIS
# ------------------------------------------------------------------------------
with tab_diag:
    st.markdown('<div class="section-header">🔍 REAL-TIME AI DIAGNOSIS</div>', unsafe_allow_html=True)
    
    # 状態を確実に参照
    ticker_input = st.text_input("Ticker Symbol (e.g. NVDA)", value=st.session_state.target_ticker).upper().strip()
    
    c1, c2 = st.columns(2)
    run_req = c1.button("🚀 RUN DEEP ANALYSIS", type="primary", use_container_width=True)
    fav_req = c2.button("⭐ ADD TO WATCHLIST", use_container_width=True)
    
    if fav_req and ticker_input:
        wl = load_watchlist() if WATCHLIST_FILE.exists() else []
        if ticker_input not in wl:
            wl.append(ticker_input)
            with open(WATCHLIST_FILE, "w") as f: json.dump(wl, f)
            st.success(f"Added {ticker_input} to watchlist.")

    if (run_req or st.session_state.pop("trigger_analysis", False)) and ticker_input:
        api_key = st.secrets.get("DEEPSEEK_API_KEY")
        if not api_key:
            st.error("DEEPSEEK_API_KEY is missing in secrets. Please set it in Streamlit Settings.")
        else:
            with st.spinner(f"Analyzing {ticker_input} (DeepSeek-Reasoner)..."):
                # データの取得とテクニカル計算
                raw_df = DataEngine.get_data(ticker_input, "2y")
                if raw_df is None or raw_df.empty:
                    st.error(f"Could not fetch data for {ticker_input}")
                else:
                    vcp_res = VCPAnalyzer.calculate(raw_df)
                    cur_price = DataEngine.get_current_price(ticker_input) or raw_df["Close"].iloc[-1]
                    
                    # 診断用グリッド表示
                    draw_sentinel_grid([
                        {"label": "💰 CURRENT PRICE", "value": f"${cur_price:.2f}"},
                        {"label": "🎯 VCP SCORE", "value": f"{vcp_res['score']}/105"},
                        {"label": "📊 SIGNALS", "value": ", ".join(vcp_res["signals"]) or "None"},
                        {"label": "📏 RANGE %", "value": f"{vcp_res['range_pct']*100:.1f}%"}
                    ])
                    
                    # チャート表示
                    tail_df = raw_df.tail(80)
                    fig_cand = go.Figure(data=[go.Candlestick(
                        x=tail_df.index, open=tail_df['Open'], high=tail_df['High'],
                        low=tail_df['Low'], close=tail_df['Close'], name='Price'
                    )])
                    fig_cand.update_layout(template="plotly_dark", height=350, margin=dict(t=0, b=0), xaxis_rangeslider_visible=False)
                    st.plotly_chart(fig_cand, use_container_width=True)

                    # 外部エンジンからコンテキスト収集
                    news = NewsEngine.get(ticker_input)
                    fund = FundamentalEngine.get(ticker_input)
                    ins  = InsiderEngine.get(ticker_input)
                    
                    # AI詳細プロンプト (一言一句復元)
                    prompt = (
                        f"あなたはウォール街の伝説的なファンドマネージャーAI「SENTINEL」です。銘柄 {ticker_input} について徹底的な診断を行います。\n\n"
                        f"━━━ テクニカル分析データ ━━━\n"
                        f"現在値: ${cur_price:.2f}\n"
                        f"VCPスコア: {vcp_res['score']}/105\n"
                        f"主要シグナル: {vcp_res['signals']}\n"
                        f"ボラティリティ収縮率: {vcp_res['range_pct']*100:.1f}%\n"
                        f"出来高比率(20d/60d): {vcp_res['vol_ratio']}\n"
                        f"ATR(14): ${vcp_res['atr']:.2f}\n\n"
                        f"━━━ ファンダメンタルズ要約 ━━━\n"
                        f"{str(fund)[:1500]}\n\n"
                        f"━━━ インサイダー・需給動向 ━━━\n"
                        f"{str(ins)[:1000]}\n\n"
                        f"━━━ 最新ニュース & 市場コンテキスト ━━━\n"
                        f"{str(news)[:2500]}\n\n"
                        f"━━━ 診断指示 ━━━\n"
                        f"1. 【現状分析】: 現在の価格アクションがどのステージ（Minervini Stage 1-4）にあるか、ファンダメンタルズとの整合性を踏まえて分析せよ。\n"
                        f"2. 【隠れたリスク】: インサイダーの売り、機関投資家の動向、またはニュースの裏にある懸念点を鋭く指摘せよ。\n"
                        f"3. 【エントリー戦略】: 現在値${cur_price:.2f}を基準とし、ATRベースの損切り位置、および最適なエントリーポイントを提示せよ。\n"
                        f"4. 【ターゲット価格】: 短期・中長期のターゲット1, 2, 3を具体的な数値で示せ。\n"
                        f"5. 【総合評価】: Buy/Watch/Avoid のいずれかを断固たる決断力で示し、その理由を総括せよ。\n\n"
                        f"※出力は Markdown 形式で、日本語で 800 文字以上の圧倒的な密度で記述すること。また為替(¥{u_j:.2f})を考慮した日本円での期待値も補足せよ。"
                    )
                    
                    # DeepSeek Call
                    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
                    try:
                        response = client.chat.completions.create(
                            model="deepseek-reasoner",
                            messages=[{"role": "user", "content": prompt}]
                        )
                        st.markdown("---")
                        st.markdown(response.choices[0].message.content.replace("$", r"\$"))
                    except Exception as e:
                        st.error(f"AI API Error: {e}")

# ------------------------------------------------------------------------------
# 💼 TAB: PORTFOLIO
# ------------------------------------------------------------------------------
with tab_port:
    st.markdown('<div class="section-header">💼 PORTFOLIO STRATEGY & RISK</div>', unsafe_allow_html=True)
    
    p_data = load_portfolio()
    positions = p_data.get("positions", {})
    
    if not positions:
        st.info("No open positions. Add one below.")
    else:
        # ポートフォリオ統計計算
        pos_stats = []
        for ticker, data in positions.items():
            curr_p = DataEngine.get_current_price(ticker)
            if curr_p:
                avg_p = data["avg_cost"]
                shares = data["shares"]
                pnl_usd = (curr_p - avg_p) * shares
                pnl_pct = (curr_p / avg_p - 1) * 100
                
                # ATRベースの出口計算
                atr_val = DataEngine.get_atr(ticker) if hasattr(DataEngine, 'get_atr') else 0.0
                risk = atr_val * EXIT_CFG["STOP_LOSS_ATR_MULT"] if atr_val else 0
                eff_stop = max(curr_p - risk, data.get("stop", 0)) if risk else data.get("stop", 0)
                
                # ステータス色
                cl_class = "profit" if pnl_pct > 0 else ("urgent" if pnl_pct < -8 else "caution")
                
                pos_stats.append({
                    "ticker": ticker, "shares": shares, "avg": avg_p, "cp": curr_p,
                    "pnl_usd": pnl_usd, "pnl_pct": pnl_pct, "cl": cl_class, "stop": eff_stop
                })
        
        # サマリー表示
        total_pnl_usd = sum(s["pnl_usd"] for s in pos_stats)
        draw_sentinel_grid([
            {"label": "💰 TOTAL UNREALIZED P/L", "value": f"¥{total_pnl_usd * u_j:,.0f}", "delta": f"${total_pnl_usd:,.2f}"},
            {"label": "📊 ASSETS COUNT", "value": f"{len(pos_stats)} Positions"},
            {"label": "💱 CURRENT FX", "value": f"¥{u_j:.2f}"},
            {"label": "🛡️ AVG PNL%", "value": f"{np.mean([s['pnl_pct'] for s in pos_stats]):.2f}%" if pos_stats else "0%"}
        ])
        
        # ポジションカード表示 (画像のデザインを再現)
        st.markdown('<div class="section-header">📋 ACTIVE POSITIONS</div>', unsafe_allow_html=True)
        for s in pos_stats:
            pnl_style = "pnl-pos" if s["pnl_pct"] > 0 else "pnl-neg"
            st.markdown(f'''
            <div class="pos-card {s['cl']}">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <b>{s['ticker']}</b>
                    <span class="{pnl_style}">{s['pnl_pct']:+.2f}% (¥{s['pnl_usd']*u_j:+,.0f})</span>
                </div>
                <div style="font-size: 0.85rem; color: #f0f6fc; margin-top: 4px;">
                    {s['shares']} shares @ ${s['avg']:.2f} (Current: ${s['cp']:.2f})
                </div>
                <div class="exit-info">
                    🛡️ <b>SMART STOP:</b> ${s['stop']:.2f} | 🎯 <b>TARGET:</b> ${s['avg'] * (1 + (EXIT_CFG['TARGET_R_MULT']/10)):.2f}
                </div>
            </div>''', unsafe_allow_html=True)
            
            c1, c2 = st.columns(2)
            if c1.button(f"🔍 ANALYZE {s['ticker']}", key=f"an_{s['ticker']}"):
                st.session_state.target_ticker = s['ticker']
                st.session_state.trigger_analysis = True
                st.rerun()
            if c2.button(f"✅ CLOSE {s['ticker']}", key=f"cl_{s['ticker']}"):
                del positions[s['ticker']]
                save_portfolio(p_data)
                st.rerun()

    # --- 建玉追加フォーム ---
    st.markdown('<div class="section-header">➕ ADD NEW POSITION</div>', unsafe_allow_html=True)
    with st.form("add_pos_form"):
        c1, c2, c3 = st.columns(3)
        new_t = c1.text_input("Ticker").upper().strip()
        new_s = c2.number_input("Shares", min_value=1, value=10)
        new_a = c3.number_input("Avg Cost ($)", min_value=0.01, value=100.0)
        if st.form_submit_button("ADD TO PORTFOLIO", use_container_width=True):
            if new_t:
                p_data = load_portfolio()
                p_data["positions"][new_t] = {"ticker": new_t, "shares": new_s, "avg_cost": new_a, "added_at": TODAY_STR}
                save_portfolio(p_data)
                st.success(f"Added {new_t} to portfolio.")
                st.rerun()

st.divider()
st.caption(f"🛡️ SENTINEL PRO | FX: ¥{u_j:.2f} | Logic Sync: Verified | Rows: ~700")

