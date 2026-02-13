"""
app.py — SENTINEL PRO Streamlit UI

モード:
    📊 スキャン    — 前回スキャン結果の表示・セクターマップ
    🔍 リアルタイム — 個別銘柄のAI深度診断（DeepSeek-Reasoner）
    💼 ポートフォリオ — 損益管理・出口戦略・AI分析
"""

import json
import os
import pickle
import re
import time
import warnings
import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

# 外部エンジン依存（既存のディレクトリ構造を維持）
from config import CONFIG
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数 & 出口戦略設定 (ロジック維持)
# ==============================================================================

NOW         = datetime.datetime.now()
TODAY_STR   = NOW.strftime("%Y-%m-%d")
CACHE_DIR   = Path("./cache_v45"); CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results");   RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

# ==============================================================================
# 🎨 ページ設定 & CSS (モバイルでの縦スペース削減 & グリッドメトリクス)
# ==============================================================================

st.set_page_config(
    page_title="SENTINEL PRO",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');

  html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }

  /* 余白の最小化 */
  .block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
  
  /* モバイル・グリッド・メトリクス (画像の問題を解決) */
  .m-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-bottom: 12px;
  }
  .m-card {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 8px;
    padding: 8px 12px;
  }
  .m-label { font-size: 0.65rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; }
  .m-value { font-size: 1.1rem; font-weight: 700; color: #ffffff; }
  .m-delta { font-size: 0.72rem; font-weight: 600; }

  /* タブのスタイル */
  .stTabs [data-baseweb="tab-list"] { gap: 6px; background-color: #0d1117; padding: 4px; border-radius: 10px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.85rem; padding: 10px 12px; font-weight: 600; color: #9ca3af; border: none; }
  .stTabs [aria-selected="true"] { background-color: #00ff7f !important; color: #000 !important; border-radius: 6px; }

  /* ポジションカードの詳細デザイン */
  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; position: relative; }
  .pos-card.urgent { border-left: 5px solid #ef4444; }
  .pos-card.caution { border-left: 5px solid #f59e0b; }
  .pos-card.profit { border-left: 5px solid #00ff7f; }
  
  .pnl-pos { color: #00ff7f; font-weight: 700; }
  .pnl-neg { color: #ef4444; font-weight: 700; }
  .exit-info { font-size: 0.8rem; color: #9ca3af; line-height: 1.8; font-family: 'Share Tech Mono', monospace; margin-top: 6px; }

  .section-header {
    font-size: 1.0rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 6px;
    margin: 16px 0 10px; font-family: 'Share Tech Mono', monospace;
  }
  
  .stButton > button { min-height: 48px; font-size: 0.95rem !important; font-weight: 600; border-radius: 8px; }
  [data-testid="stMetric"] { display: none; } /* デフォルトメトリクスを非表示にして自作グリッドを使用 */
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 📋 セッション状態
# ==============================================================================

_defaults = {
    "target_ticker":      "",
    "trigger_analysis":   False,
    "portfolio_dirty":    True,
    "portfolio_summary":  None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# 💾 データ取得 (全機能維持)
# ==============================================================================

@st.cache_data(ttl=600)
def get_usd_jpy() -> float:
    return CurrencyEngine.get_usd_jpy()

@st.cache_data(ttl=300)
def fetch_price_data(ticker: str, period: str = "1y") -> Optional[pd.DataFrame]:
    return DataEngine.get_data(ticker, period)

@st.cache_data(ttl=60)
def get_current_price(ticker: str) -> Optional[float]:
    return DataEngine.get_current_price(ticker)

@st.cache_data(ttl=300)
def get_atr(ticker: str) -> Optional[float]:
    df = DataEngine.get_data(ticker, "3mo")
    if df is None or len(df) < 15: return None
    h, l, c = df["High"], df["Low"], df["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    v = float(tr.rolling(14).mean().iloc[-1])
    return round(v, 4) if not pd.isna(v) else None

@st.cache_data(ttl=600)
def load_historical_json() -> pd.DataFrame:
    all_data = []
    if RESULTS_DIR.exists():
        for f in sorted(RESULTS_DIR.glob("*.json"), reverse=True):
            try:
                with open(f, encoding="utf-8") as fh: daily = json.load(fh)
                d = daily.get("date", f.stem)
                for key in ("selected", "watchlist_wait", "qualified_full"):
                    for item in daily.get(key, []):
                        item["date"] = d
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except: pass
    return pd.DataFrame(all_data)

@st.cache_data(ttl=1800)
def fetch_news_cached(ticker: str) -> dict: return NewsEngine.get(ticker)
@st.cache_data(ttl=3600)
def fetch_fundamental_cached(ticker: str) -> dict: return FundamentalEngine.get(ticker)
@st.cache_data(ttl=3600)
def fetch_insider_cached(ticker: str) -> dict: return InsiderEngine.get(ticker)

# ==============================================================================
# 🧠 VCP 分析 (バックエンド VCPAnalyzer と完全同期)
# ==============================================================================

def _empty_vcp() -> dict:
    return {"score": 0, "atr": 0.0, "signals": [], "is_dryup": False, "range_pct": 0.0, "vol_ratio": 1.0}

def calc_vcp(df: pd.DataFrame) -> dict:
    try:
        if df is None or len(df) < 80: return _empty_vcp()
        close, high, low, volume = df["Close"], df["High"], df["Low"], df["Volume"]

        # ATR(14)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if pd.isna(atr) or atr <= 0: return _empty_vcp()

        # 1. Tightness (40pt)
        periods = [20, 30, 40]
        ranges = []
        for p in periods:
            h_p, l_p = float(high.iloc[-p:].max()), float(low.iloc[-p:].min())
            ranges.append((h_p - l_p) / h_p)
        avg_range = float(np.mean(ranges))
        is_contracting = ranges[0] < ranges[1] < ranges[2]

        if avg_range < 0.12: tight_score = 40
        elif avg_range < 0.18: tight_score = 30
        elif avg_range < 0.24: tight_score = 20
        elif avg_range < 0.30: tight_score = 10
        else: tight_score = 0
        if is_contracting: tight_score += 5
        tight_score = min(40, tight_score)

        # 2. Volume (30pt)
        v20 = float(volume.iloc[-20:].mean())
        v60 = float(volume.iloc[-60:-40].mean())
        ratio = v20 / v60 if v60 > 0 else 1.0
        if ratio < 0.50: vol_score = 30
        elif ratio < 0.65: vol_score = 25
        elif ratio < 0.80: vol_score = 15
        else: vol_score = 0
        is_dryup = ratio < 0.80

        # 3. MA Align (30pt)
        ma50 = float(close.rolling(50).mean().iloc[-1]); ma200 = float(close.rolling(200).mean().iloc[-1]); price = float(close.iloc[-1])
        trend_score = (10 if price > ma50 else 0) + (10 if ma50 > ma200 else 0) + (10 if price > ma200 else 0)

        # 4. Pivot Bonus (+5pt)
        pivot = float(high.iloc[-40:].max()); dist = (pivot - price) / pivot
        pivot_bonus = 5 if 0 <= dist <= 0.05 else (3 if 0.05 < dist <= 0.08 else 0)

        signals = []
        if tight_score >= 35: signals.append("Multi-Stage Contraction")
        if is_dryup:          signals.append("Volume Dry-Up")
        if trend_score == 30: signals.append("MA Aligned")
        if pivot_bonus > 0:   signals.append("Near Pivot")

        return {
            "score": int(max(0, tight_score + vol_score + trend_score + pivot_bonus)),
            "atr": atr, "signals": signals, "is_dryup": is_dryup,
            "range_pct": round(ranges[0], 4), "vol_ratio": round(ratio, 2)
        }
    except: return _empty_vcp()

# ==============================================================================
# 🤖 AI / IO / 計算エンジン (全ロジック復元)
# ==============================================================================

def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key: return "⚠️ DEEPSEEK_API_KEY 未設定"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content or ""
    except Exception as e: return f"AI Error: {e}"

def load_watchlist():
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f: return json.load(f)
        except: pass
    return []
def _write_watchlist(data):
    with open(WATCHLIST_FILE, "w") as f: json.dump(data, f)
def add_watchlist(t):
    wl = load_watchlist()
    if t not in wl: wl.append(t); _write_watchlist(wl); return True
    return False
def remove_watchlist(t):
    wl = load_watchlist()
    if t in wl: wl.remove(t); _write_watchlist(wl); return True
    return False

def load_portfolio():
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"positions": {}, "closed": [], "meta": {"created": NOW.isoformat()}}

def _write_portfolio(data):
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f: json.dump(data, f, ensure_ascii=False, indent=2, default=str)

def upsert_position(ticker, shares, avg_cost, memo="", target=0.0, stop=0.0):
    data = load_portfolio(); pos = data["positions"]; t = ticker.upper()
    if t in pos:
        old = pos[t]; tot = old["shares"] + shares
        pos[t].update({"shares": tot, "avg_cost": round((old["shares"]*old["avg_cost"]+shares*avg_cost)/tot, 4), "memo": memo or old.get("memo",""), "target": target or old.get("target",0.0), "stop": stop or old.get("stop",0.0), "updated_at": NOW.isoformat()})
    else:
        pos[t] = {"ticker": t, "shares": shares, "avg_cost": round(avg_cost, 4), "memo": memo, "target": round(target, 4), "stop": round(stop, 4), "added_at": NOW.isoformat(), "updated_at": NOW.isoformat()}
    _write_portfolio(data)

def close_position(ticker, shares_sold=None, sell_price=None):
    data = load_portfolio(); pos = data["positions"]
    if ticker not in pos: return False
    p = pos[ticker]; actual = shares_sold if shares_sold else p["shares"]
    if sell_price:
        pnl_usd = (sell_price - p["avg_cost"]) * actual
        data["closed"].append({"ticker": ticker, "shares": actual, "avg_cost": p["avg_cost"], "sell_price": sell_price, "pnl_usd": round(pnl_usd, 2), "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2), "closed_at": NOW.isoformat(), "memo": p.get("memo", "")})
    if shares_sold and shares_sold < p["shares"]: pos[ticker]["shares"] -= shares_sold
    else: del pos[ticker]
    _write_portfolio(data); return True

def calc_pos_stats(pos, usd_jpy):
    cp = get_current_price(pos["ticker"]); atr = get_atr(pos["ticker"])
    if cp is None: return {**pos, "error": True, "current_price": None}
    shares, avg = pos["shares"], pos["avg_cost"]
    pnl_usd = (cp - avg) * shares; pnl_pct = (cp / avg - 1) * 100
    ex = {}
    if atr:
        risk = atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]; dyn_stop = round(cp - risk, 4); reg_stop = pos.get("stop", 0.0); eff_stop = max(dyn_stop, reg_stop) if reg_stop > 0 else dyn_stop
        cur_r = (cp - avg) / risk if risk > 0 else 0.0; reg_tgt = pos.get("target", 0.0); eff_tgt = reg_tgt if reg_tgt > 0 else round(avg + risk * EXIT_CFG["TARGET_R_MULT"], 4)
        trail = round(cp - atr * EXIT_CFG["TRAIL_ATR_MULT"], 4) if cur_r >= EXIT_CFG["TRAIL_START_R"] else None
        scale = round(avg + risk * EXIT_CFG["SCALE_OUT_R"], 4)
        ex = {"atr": atr, "risk": round(risk, 4), "dyn_stop": dyn_stop, "eff_stop": eff_stop, "eff_tgt": eff_tgt, "scale_out": scale, "cur_r": round(cur_r, 2), "trail": trail}
    
    st_icon = "🔵"
    if pnl_pct <= -8: st_icon = "🚨"
    elif pnl_pct <= -4: st_icon = "⚠️"
    elif ex.get("cur_r", 0) >= EXIT_CFG["TARGET_R_MULT"]: st_icon = "🎯"
    elif ex.get("cur_r", 0) >= EXIT_CFG["TRAIL_START_R"]: st_icon = "📈"
    elif pnl_pct > 0: st_icon = "✅"
    
    return {**pos, "current_price": round(cp, 4), "pnl_usd": round(pnl_usd, 2), "pnl_pct": round(pnl_pct, 2), "pnl_jpy": round(pnl_usd * usd_jpy, 0), "mv_usd": round(cp * shares, 2), "cb_usd": round(avg * shares, 2), "exit": ex, "status": st_icon}

def get_portfolio_summary(usd_jpy):
    data = load_portfolio(); pos_d = data["positions"]
    if not pos_d: return {"positions": [], "total": {}, "closed": data.get("closed", [])}
    stats = [calc_pos_stats(p, usd_jpy) for p in pos_d.values()]
    valid = [s for s in stats if not s.get("error")]
    total_mv = sum(s["mv_usd"] for s in valid); total_cb = sum(s["cb_usd"] for s in valid); total_pnl = sum(s["pnl_usd"] for s in valid)
    cap_usd = CONFIG["CAPITAL_JPY"] / usd_jpy
    for s in valid: s["pw"] = round(s["mv_usd"] / total_mv * 100, 1) if total_mv > 0 else 0.0
    closed = data.get("closed", []); win_cnt = len([c for c in closed if c.get("pnl_usd", 0) > 0])
    return {"positions": stats, "total": {"count": len(valid), "mv_usd": round(total_mv, 2), "mv_jpy": round(total_mv * usd_jpy, 0), "pnl_usd": round(total_pnl, 2), "pnl_jpy": round(total_pnl * usd_jpy, 0), "pnl_pct": round(total_pnl / total_cb * 100 if total_cb else 0, 2), "exposure": round(total_mv / cap_usd * 100 if cap_usd else 0, 1), "cash_jpy": round((cap_usd - total_mv) * usd_jpy, 0)}, "closed_stats": {"count": len(closed), "pnl_usd": round(sum(c.get("pnl_usd",0) for c in closed), 2), "pnl_jpy": round(sum(c.get("pnl_usd",0) for c in closed)*usd_jpy, 0), "win_rate": round(win_cnt/len(closed)*100, 1) if closed else 0.0}, "closed": closed}

# ==============================================================================
# 🎨 UI ヘルパー: コンパクトグリッド
# ==============================================================================

def render_compact_metrics(metrics_list):
    html = '<div class="m-grid">'
    for m in metrics_list:
        delta_html = ""
        if "delta" in m and m["delta"]:
            color = "#00ff7f" if "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0) else "#ef4444"
            delta_html = f'<div class="m-delta" style="color:{color}">{m["delta"]}</div>'
        html += f'''
        <div class="m-card">
            <div class="m-label">{m["label"]}</div>
            <div class="m-value">{m["value"]}</div>
            {delta_html}
        </div>
        '''
    html += '</div>'
    st.markdown(html, unsafe_allow_html=True)

# ==============================================================================
# 🧭 メイン UI
# ==============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    wl = load_watchlist()
    for t in wl:
        c1, c2 = st.columns([4, 1])
        if c1.button(f"🔍 {t}", key=f"side_{t}", use_container_width=True):
            st.session_state["target_ticker"] = t; st.session_state["trigger_analysis"] = True
        if c2.button("×", key=f"rm_side_{t}"):
            remove_watchlist(t); st.rerun()

usd_jpy = get_usd_jpy()
tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン", "🔍 診断", "💼 資産"])

# ------------------------------------------------------------------------------
# 📊 TAB 1: スキャン
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_hist = load_historical_json()
    if df_hist.empty:
        st.info("No data.")
    else:
        latest_date = df_hist["date"].max(); latest_df = df_hist[df_hist["date"] == latest_date].drop_duplicates("ticker")
        render_compact_metrics([
            {"label": "📅 最終スキャン", "value": latest_date},
            {"label": "💱 USD/JPY", "value": f"¥{usd_jpy}"},
            {"label": "💎 ACTION", "value": len(latest_df[latest_df["status"] == "ACTION"]) if "status" in latest_df.columns else "0"},
            {"label": "⏳ WAIT", "value": len(latest_df[latest_df["status"] == "WAIT"]) if "status" in latest_df.columns else "0"}
        ])

        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in latest_df.columns:
            fig = px.treemap(latest_df, path=["sector", "ticker"], values="vcp_score", color="rs", color_continuous_scale="RdYlGn")
            fig.update_layout(template="plotly_dark", height=300, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        st.dataframe(latest_df[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True, height=250)

# ------------------------------------------------------------------------------
# 🔍 TAB 2: リアルタイム診断 (プロンプト全復元)
# ------------------------------------------------------------------------------
with tab_real:
    st.markdown('<div class="section-header">🔍 AI リアルタイム診断</div>', unsafe_allow_html=True)
    t_in = st.text_input("Ticker 入力 (NVDA, TSLA...)", value=st.session_state["target_ticker"]).upper().strip()
    
    c1, c2 = st.columns(2)
    run_req = c1.button("🚀 診断開始", type="primary", use_container_width=True)
    add_req = c2.button("⭐ Watchlist追加", use_container_width=True)
    
    if add_req and t_in:
        if add_watchlist(t_in): st.success(f"Added {t_in}")

    if (run_req or st.session_state.pop("trigger_analysis", False)) and t_in:
        with st.spinner(f"{t_in} 分析中..."):
            data = fetch_price_data(t_in, "2y"); cp = get_current_price(t_in); vcp = calc_vcp(data)
            news = fetch_news_cached(t_in); fund = fetch_fundamental_cached(t_in); insider = fetch_insider_cached(t_in)
            
            if data is not None and not data.empty:
                current_p = cp or data["Close"].iloc[-1]
                render_compact_metrics([
                    {"label": "💰 現在値", "value": f"${current_p:.2f}"},
                    {"label": "🎯 VCPスコア", "value": f"{vcp['score']}/105"},
                    {"label": "📊 シグナル", "value": ", ".join(vcp["signals"]) or "特記なし"},
                    {"label": "📈 収縮率", "value": f"{vcp['range_pct']*100:.1f}%"}
                ])
                
                # チャート
                tail = data.tail(60)
                fig_rt = go.Figure(go.Candlestick(x=tail.index, open=tail["Open"], high=tail["High"], low=tail["Low"], close=tail["Close"]))
                fig_rt.update_layout(template="plotly_dark", height=280, xaxis_rangeslider_visible=False, margin=dict(t=0))
                st.plotly_chart(fig_rt, use_container_width=True)

                # AI プロンプト (ロジック詳細復元)
                p_now = round(float(current_p), 2); atr_v = round(vcp["atr"], 2)
                f_lines = FundamentalEngine.format_for_prompt(fund, p_now); i_lines = InsiderEngine.format_for_prompt(insider); n_text = NewsEngine.format_for_prompt(news)
                
                prompt = (
                    f"ウォール街のファンドマネージャーAI「SENTINEL」として{t_in}を診断せよ。\n\n"
                    f"━━━ テクニカル ━━━\n現在値: ${p_now}\nVCPスコア: {vcp['score']}/105\n収縮率: {vcp['range_pct']*100:.1f}%\nATR: ${atr_v}\n\n"
                    f"━━━ ファンダメンタル ━━━\n" + "\n".join(f_lines) + "\n\n"
                    f"━━━ インサイダー ━━━\n" + "\n".join(i_lines) + "\n\n"
                    f"━━━ 最新ニュース ━━━\n{n_text[:2000]}\n\n"
                    f"【要件】Markdown形式で、現在値${p_now}とATR=${atr_v}を考慮した具体的なEntry/Stop/Target戦略、およびリスク分析、総合判断(Buy/Watch/Avoid)を出力せよ。"
                )
                ai_res = call_ai(prompt)
                st.markdown("---"); st.markdown(ai_res.replace("$", r"\$")); st.markdown("---")
            else: st.error("Data fetch error.")

# ------------------------------------------------------------------------------
# 💼 TAB 3: ポートフォリオ (計算ロジック全維持)
# ------------------------------------------------------------------------------
with tab_port:
    p_sub = st.tabs(["📊 損益", "➕ 建玉追加", "🤖 AI分析", "📜 決済履歴"])
    
    with p_sub[0]:
        if st.session_state["portfolio_dirty"]:
            st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy); st.session_state["portfolio_dirty"] = False
        
        sm = st.session_state["portfolio_summary"]
        if sm and sm.get("positions"):
            total = sm["total"]
            render_compact_metrics([
                {"label": "評価損益", "value": f"¥{total['pnl_jpy']:,.0f}", "delta": f"{total['pnl_pct']:+.2f}%"},
                {"label": "露出度", "value": f"{total['exposure']:.1f}%"},
                {"label": "建玉数", "value": total["count"]},
                {"label": "余剰(JPY)", "value": f"¥{total['cash_jpy']:,.0f}"}
            ])

            st.markdown('<div class="section-header">📋 ポジション一覧</div>', unsafe_allow_html=True)
            for p in sorted(sm["positions"], key=lambda x: x.get("pnl_pct", 0)):
                if p.get("error"): continue
                cls = "urgent" if p["pnl_pct"] <= -8 else ("profit" if p["pnl_pct"] >= 10 else "caution")
                ex = p.get("exit", {})
                st.markdown(f'''
                <div class="pos-card {cls}">
                    <b>{p['status']} {p['ticker']}</b> — {p['shares']}株 @ ${p['avg_cost']:.2f}<br>
                    現値: ${p['current_price']:.2f} | 損益: <span class="{'pnl-pos' if p['pnl_pct']>0 else 'pnl-neg'}">{p['pnl_pct']:+.2f}% (¥{p['pnl_jpy']:+,.0f})</span>
                    <div class="exit-info">Stop: ${ex.get('eff_stop','—')} | Target: ${ex.get('eff_tgt','—')} | R: {ex.get('cur_r',0)}</div>
                </div>''', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button(f"🔍 診断 {p['ticker']}", key=f"d_{p['ticker']}"):
                    st.session_state["target_ticker"] = p['ticker']; st.session_state["trigger_analysis"] = True; st.rerun()
                if c2.button(f"✅ 決済 {p['ticker']}", key=f"cl_{p['ticker']}"):
                    close_position(p['ticker'], sell_price=p['current_price']); st.session_state["portfolio_dirty"] = True; st.rerun()
        else: st.info("保有ポジションなし。")

    with p_sub[1]:
        with st.form("new_pos_f"):
            c1, c2 = st.columns(2); nt = c1.text_input("Ticker").upper(); ns = c2.number_input("Shares", min_value=1)
            c3, c4 = st.columns(2); nc = c3.number_input("Cost"); nstop = c4.number_input("Stop")
            if st.form_submit_button("追加"):
                upsert_position(nt, ns, nc, stop=nstop); st.session_state["portfolio_dirty"] = True; st.rerun()

    with p_sub[2]:
        if st.button("🚀 ポートフォリオ AI 分析実行"):
            sum_d = get_portfolio_summary(usd_jpy)
            pos_t = [f"{p['ticker']}: {p['shares']}株 (損益{p['pnl_pct']:+.1f}%)" for p in sum_d["positions"] if not p.get("error")]
            prompt = f"分析せよ:\nJPY/USD: {usd_jpy}\nポジション: {', '.join(pos_t)}\nリスクと改善策を述べよ。"
            with st.spinner("AI 思考中..."):
                rep = call_ai(prompt); st.markdown(rep.replace("$", r"\$"))

    with p_sub[3]:
        summary = get_portfolio_summary(usd_jpy); closed = summary.get("closed", [])
        if closed:
            cs = summary["closed_stats"]
            render_compact_metrics([{"label": "決済数", "value": cs["count"]}, {"label": "確定損益", "value": f"¥{cs['pnl_jpy']:+,.0f}"}, {"label": "勝率", "value": f"{cs['win_rate']}%"}])
            st.dataframe(pd.DataFrame(closed[::-1]), use_container_width=True)

st.divider()
st.caption(f"SENTINEL PRO | {NOW.strftime('%H:%M:%S')}")

