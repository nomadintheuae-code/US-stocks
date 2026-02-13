"""
app.py — SENTINEL PRO Streamlit UI

[100% Logic Restoration & Tokenizer Fix]
- 初期コードの全ロジック（RS加重計算、252日バックテスト、詳細AIプロンプト）を完全復元。
- tokenize.TokenError（画像のエラー）を回避するため、複雑なf-stringを分解。
- VCP計算ロジックを最新バックエンドに同期。
- モバイル視認性向上のためのCSSグリッドを適用。
"""

import json
import os
import pickle
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

# 外部エンジン依存関係（既存ディレクトリ構造を維持）
try:
    from config import CONFIG
    from engines.data import CurrencyEngine, DataEngine
    from engines.fundamental import FundamentalEngine, InsiderEngine
    from engines.news import NewsEngine
except ImportError:
    pass

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数 & 出口戦略設定 (一言一句維持)
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
# 🎯 VCPAnalyzer (バックエンド最新ロジックと完全同期)
# ==============================================================================

class VCPAnalyzer:
    """Mark Minervini VCP Scoring"""
    @staticmethod
    def calculate(df: pd.DataFrame) -> dict:
        try:
            if df is None or len(df) < 80:
                return VCPAnalyzer._empty()

            close = df["Close"]; high = df["High"]; low = df["Low"]; volume = df["Volume"]

            # ATR(14)
            tr = pd.concat([
                high - low,
                (high - close.shift()).abs(),
                (low - close.shift()).abs(),
            ], axis=1).max(axis=1)
            atr = float(tr.rolling(14).mean().iloc[-1])
            if pd.isna(atr) or atr <= 0: return VCPAnalyzer._empty()

            # 1. Tightness (40pt)
            periods = [20, 30, 40]
            ranges = []
            for p in periods:
                h_max = float(high.iloc[-p:].max())
                l_min = float(low.iloc[-p:].min())
                ranges.append((h_max - l_min) / h_max)
            
            avg_range = float(np.mean(ranges))
            is_contracting = ranges[0] < ranges[1] < ranges[2]

            if avg_range < 0.12:   tight_score = 40
            elif avg_range < 0.18: tight_score = 30
            elif avg_range < 0.24: tight_score = 20
            elif avg_range < 0.30: tight_score = 10
            else:                  tight_score = 0
            
            if is_contracting: tight_score += 5
            tight_score = min(40, tight_score)

            # 2. Volume (30pt)
            v20 = float(volume.iloc[-20:].mean())
            v60 = float(volume.iloc[-60:-40].mean())
            ratio = v20 / v60 if v60 > 0 else 1.0

            if ratio < 0.50:   vol_score = 30
            elif ratio < 0.65: vol_score = 25
            elif ratio < 0.80: vol_score = 15
            else:              vol_score = 0
            is_dryup = ratio < 0.80

            # 3. MA Alignment (30pt)
            ma50  = float(close.rolling(50).mean().iloc[-1])
            ma200 = float(close.rolling(200).mean().iloc[-1])
            price = float(close.iloc[-1])
            trend_score = (
                (10 if price > ma50 else 0) +
                (10 if ma50 > ma200 else 0) +
                (10 if price > ma200 else 0)
            )

            # 4. Pivotボーナス (最大+5)
            pivot = float(high.iloc[-40:].max())
            distance = (pivot - price) / pivot
            pivot_bonus = 5 if 0 <= distance <= 0.05 else (3 if 0.05 < distance <= 0.08 else 0)

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
        except: return VCPAnalyzer._empty()

    @staticmethod
    def _empty():
        return {"score": 0, "atr": 0.0, "signals": [], "is_dryup": False, "range_pct": 0.0, "vol_ratio": 1.0}

# ==============================================================================
# 📈 RSAnalyzer (加重計算ロジックを完全復元)
# ==============================================================================

class RSAnalyzer:
    """Relative Strength 加重計算エンジン"""
    @staticmethod
    def get_raw_score(df: pd.DataFrame) -> float:
        try:
            c = df["Close"]
            if len(c) < 21: return -999.0
            # 12ヶ月(40%), 6ヶ月(20%), 3ヶ月(20%), 1ヶ月(20%) の加重モメンタム
            r12 = (c.iloc[-1] / c.iloc[-252] - 1) if len(c) >= 252 else (c.iloc[-1] / c.iloc[0] - 1)
            r6  = (c.iloc[-1] / c.iloc[-126] - 1) if len(c) >= 126 else (c.iloc[-1] / c.iloc[0] - 1)
            r3  = (c.iloc[-1] / c.iloc[-63]  - 1) if len(c) >= 63  else (c.iloc[-1] / c.iloc[0] - 1)
            r1  = (c.iloc[-1] / c.iloc[-21]  - 1) if len(c) >= 21  else (c.iloc[-1] / c.iloc[0] - 1)
            return (r12 * 0.4) + (r6 * 0.2) + (r3 * 0.2) + (r1 * 0.2)
        except: return -999.0

    @staticmethod
    def assign_percentiles(raw_list: List[Dict]) -> List[Dict]:
        if not raw_list: return raw_list
        raw_list.sort(key=lambda x: x.get("raw_rs", 0))
        total = len(raw_list)
        for i, item in enumerate(raw_list):
            item["rs_rating"] = int(((i + 1) / total) * 98) + 1
        return raw_list

# ==============================================================================
# 🔬 StrategyValidator (252日フルバックテストを完全復元)
# ==============================================================================

class StrategyValidator:
    """直近1年間のバックテストによる期待値(PF)の検証"""
    @staticmethod
    def run(df: pd.DataFrame) -> float:
        try:
            if len(df) < 200: return 1.0
            close = df["Close"]; high = df["High"]; low = df["Low"]
            tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
            atr = tr.rolling(14).mean()
            trades = []; in_pos = False; entry_p = 0.0; stop_p = 0.0
            t_mult = EXIT_CFG["TARGET_R_MULT"]; s_mult = EXIT_CFG["STOP_LOSS_ATR_MULT"]
            # 252日間のシミュレーションループ
            start_idx = max(50, len(df) - 250)
            for i in range(start_idx, len(df)):
                if in_pos:
                    if float(low.iloc[i]) <= stop_p:
                        trades.append(-1.0); in_pos = False
                    elif float(high.iloc[i]) >= entry_p + (entry_p - stop_p) * t_mult:
                        trades.append(t_mult); in_pos = False
                else:
                    if i < 20: continue
                    pivot = float(high.iloc[i-20:i].max())
                    ma50 = float(close.rolling(50).mean().iloc[i])
                    if float(close.iloc[i]) > pivot and float(close.iloc[i]) > ma50:
                        in_pos = True; entry_p = float(close.iloc[i]); stop_p = entry_p - float(atr.iloc[i]) * s_mult
            if not trades: return 1.0
            pos = sum(t for t in trades if t > 0); neg = abs(sum(t for t in trades if t < 0))
            return round(min(10.0, pos / neg if neg > 0 else 5.0), 2)
        except: return 1.0

# ==============================================================================
# 🎨 ページ設定 & CSS (Tokenizer Error回避のため記述を整理)
# ==============================================================================

st.set_page_config(page_title="SENTINEL PRO", page_icon="🛡️", layout="wide", initial_sidebar_state="collapsed")

# CSSを変数に分離することでパーサーエラーを回避
GLOBAL_CSS = """
<style>
  @import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Rajdhani:wght@400;600;700&display=swap');
  html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }
  .block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }

  /* 視認性向上のためのグリッドレイアウト */
  .sentinel-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    margin-bottom: 15px;
  }
  @media (min-width: 992px) {
    .sentinel-grid { grid-template-columns: repeat(4, 1fr); }
  }
  .sentinel-card {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 10px;
    padding: 10px 12px;
    box-shadow: 0 4px 6px -1px rgba(0,0,0,0.1);
  }
  .sentinel-label { font-size: 0.65rem; color: #6b7280; text-transform: uppercase; letter-spacing: 0.8px; font-weight: 600; margin-bottom: 2px; }
  .sentinel-value { font-size: 1.1rem; font-weight: 700; color: #ffffff; line-height: 1.2; }
  .sentinel-delta { font-size: 0.7rem; font-weight: 600; margin-top: 4px; }

  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
  .pos-card.urgent { border-left: 5px solid #ef4444; }
  .pos-card.profit { border-left: 5px solid #00ff7f; }
  .pnl-pos { color: #00ff7f; font-weight: 700; }
  .pnl-neg { color: #ef4444; font-weight: 700; }
  .exit-info { font-size: 0.8rem; color: #9ca3af; font-family: 'Share Tech Mono', monospace; margin-top: 6px; line-height: 1.6; }

  .section-header { font-size: 1.0rem; font-weight: 700; color: #00ff7f; border-bottom: 1px solid #1f2937; padding-bottom: 4px; margin: 16px 0 10px; font-family: 'Share Tech Mono', monospace; }
  
  .stTabs [data-baseweb="tab-list"] { background-color: #0d1117; padding: 4px; border-radius: 10px; gap: 4px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.8rem; padding: 10px 12px; color: #9ca3af; }
  .stTabs [aria-selected="true"] { background-color: #00ff7f !important; color: #000 !important; border-radius: 6px; }

  [data-testid="stMetric"] { display: none !important; }
</style>
"""
st.markdown(GLOBAL_CSS, unsafe_allow_html=True)

# ==============================================================================
# 📋 キャッシュ & データアクセス (全ロジック維持)
# ==============================================================================

@st.cache_data(ttl=600)
def get_usd_jpy() -> float: return CurrencyEngine.get_usd_jpy()

@st.cache_data(ttl=300)
def fetch_price_data(t: str, p: str = "1y") -> Optional[pd.DataFrame]: return DataEngine.get_data(t, p)

@st.cache_data(ttl=60)
def get_current_price(t: str) -> Optional[float]: return DataEngine.get_current_price(t)

@st.cache_data(ttl=300)
def get_atr(t: str) -> Optional[float]:
    df = DataEngine.get_data(t, "3mo")
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
                with open(f, encoding="utf-8") as fh:
                    daily = json.load(fh)
                d = daily.get("date", f.stem)
                for key in ("selected", "watchlist_wait", "qualified_full"):
                    for item in daily.get(key, []):
                        item["date"] = d
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except: pass
    return pd.DataFrame(all_data)

def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key: return "⚠️ API KEY MISSING"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content or ""
    except Exception as e: return f"AI Error: {e}"

# Watchlist & Portfolio I/O
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
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)

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
        pnl = (sell_price - p["avg_cost"]) * actual
        data["closed"].append({"ticker": ticker, "shares": actual, "avg_cost": p["avg_cost"], "sell_price": sell_price, "pnl_usd": round(pnl, 2), "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2), "closed_at": NOW.isoformat()})
    if shares_sold and shares_sold < p["shares"]: pos[ticker]["shares"] -= shares_sold
    else: del pos[ticker]
    _write_portfolio(data); return True

# 出口戦略計算 (一言一句復元)
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
        ex = {"atr": atr, "risk": round(risk, 4), "dyn_stop": dyn_stop, "eff_stop": eff_stop, "eff_tgt": eff_tgt, "cur_r": round(cur_r, 2), "trail": trail}
    st_icon = "🔵"
    if pnl_pct <= -8: st_icon = "🚨"
    elif pnl_pct <= -4: st_icon = "⚠️"
    elif ex.get("cur_r", 0) >= EXIT_CFG["TARGET_R_MULT"]: st_icon = "🎯"
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

# Tokenizer Error回避のための単純な描画関数
def render_sentinel_metrics(m_list):
    html_out = '<div class="sentinel-grid">'
    for m in m_list:
        delta_tag = ""
        if "delta" in m and m["delta"]:
            c = "#00ff7f" if "+" in str(m["delta"]) or (isinstance(m["delta"], (int, float)) and m["delta"] > 0) else "#ef4444"
            delta_tag = f'<div class="sentinel-delta" style="color:{c}">{m["delta"]}</div>'
        html_out += f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{delta_tag}</div>'
    html_out += "</div>"
    st.markdown(html_out, unsafe_allow_html=True)

# ==============================================================================
# 🧭 メイン UI Flow
# ==============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    wl = load_watchlist()
    for t in wl:
        c1, c2 = st.columns([4, 1])
        if c1.button(f"🔍 {t}", key=f"side_{t}", use_container_width=True):
            st.session_state["target_ticker"] = t; st.session_state["trigger_analysis"] = True
        if c2.button("×", key=f"rm_{t}"): remove_watchlist(t); st.rerun()
    st.divider()
    usd_jpy = get_usd_jpy()
    st.metric("💱 USD/JPY", f"¥{usd_jpy}")

tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン", "🔍 診断", "💼 資産"])

# 📊 TAB 1: スキャン
with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_h = load_historical_json()
    if df_h.empty: st.info("No data.")
    else:
        ld = df_h["date"].max(); ldf = df_h[df_h["date"] == ld].drop_duplicates("ticker")
        render_sentinel_metrics([{"label": "📅 スキャン日", "value": ld}, {"label": "💱 為替", "value": f"¥{usd_jpy}"}, {"label": "💎 ACTION", "value": len(ldf[ldf["status"] == "ACTION"]) if "status" in ldf.columns else "0"}, {"label": "⏳ WAIT", "value": len(ldf[ldf["status"] == "WAIT"]) if "status" in ldf.columns else "0"}])
        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in ldf.columns:
            fig = px.treemap(ldf, path=["sector", "ticker"], values="vcp_score", color="rs" if "rs" in ldf.columns else "vcp_score", color_continuous_scale="RdYlGn")
            fig.update_layout(template="plotly_dark", height=320, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        st.dataframe(ldf[["ticker", "status", "vcp_score", "rs", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True, height=350)

# 🔍 TAB 2: 診断 (プロンプト全復元)
with tab_real:
    st.markdown('<div class="section-header">🔍 AI 深度診断 (DeepSeek)</div>', unsafe_allow_html=True)
    t_in = st.text_input("Ticker 入力", value=st.session_state["target_ticker"]).upper().strip()
    c1, c2 = st.columns(2)
    if c1.button("🚀 診断開始", type="primary", use_container_width=True) or st.session_state.pop("trigger_analysis", False):
        if t_in:
            with st.spinner(f"{t_in} 分析中..."):
                data = fetch_price_data(t_in, "2y"); cp = get_current_price(t_in); vcp = VCPAnalyzer.calculate(data)
                news = NewsEngine.get(t_in); fund = FundamentalEngine.get(t_in); insider = InsiderEngine.get(t_in)
                if data is not None and not data.empty:
                    cur_p = cp or data["Close"].iloc[-1]
                    render_sentinel_metrics([{"label": "💰 価格", "value": f"${cur_p:.2f}"}, {"label": "🎯 VCP", "value": f"{vcp['score']}/105"}, {"label": "📊 信号", "value": ", ".join(vcp["signals"]) or "—"}, {"label": "📈 収縮率", "value": f"{vcp['range_pct']*100:.1f}%"}])
                    tail = data.tail(60)
                    fig_r = go.Figure(go.Candlestick(x=tail.index, open=tail["Open"], high=tail["High"], low=tail["Low"], close=tail["Close"]))
                    fig_r.update_layout(template="plotly_dark", height=280, xaxis_rangeslider_visible=False, margin=dict(t=0))
                    st.plotly_chart(fig_r, use_container_width=True)
                    # AI詳細プロンプト復元
                    p_now, atr_v = round(float(cur_p), 2), round(vcp["atr"], 2)
                    f_l = FundamentalEngine.format_for_prompt(fund, p_now); i_l = InsiderEngine.format_for_prompt(insider); n_t = NewsEngine.format_for_prompt(news)
                    prompt = (
                        f"あなたはウォール街のトップファンドマネージャーAI「SENTINEL」です。銘柄 {t_in} について深度診断を行います。\n\n"
                        f"━━━ テクニカル（現在値ベース） ━━━\n現在値: ${p_now}\nVCPスコア: {vcp['score']}/105\n収縮率: {vcp['range_pct']*100:.1f}%  Vol比率: {vcp['vol_ratio']}\nATR(14): ${atr_v}\n\n"
                        f"━━━ ファンダメンタル ━━━\n" + "\n".join(f_l) + "\n\n"
                        f"━━━ インサイダー取引 ━━━\n" + "\n".join(i_l) + "\n\n"
                        f"━━━ 最新ニュース & コンテキスト ━━━\n{n_t[:1800]}\n\n"
                        f"【出力形式】 Markdown。日本語。800文字以上。1.現状分析 2.隠れたリスク 3.エントリー戦略(${p_now}からの押し目水準) 4.具体価格(Stop/Target) 5.総合判断(Buy/Watch/Avoid)"
                    )
                    ai_res = call_ai(prompt); st.markdown("---"); st.markdown(ai_res.replace("$", r"\$")); st.markdown("---")
    if c2.button("⭐ 追加", use_container_width=True) and t_in:
        if add_watchlist(t_in): st.success(f"{t_in} を追加")

# 💼 TAB 3: ポートフォリオ (Token Error回避のためHTML生成を整理)
with tab_port:
    ps = st.tabs(["📊 損益", "➕ 追加", "🤖 分析", "📜 履歴"])
    with ps[0]:
        if st.session_state["portfolio_dirty"]:
            st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy); st.session_state["portfolio_dirty"] = False
        s = st.session_state["portfolio_summary"]
        if s and s.get("positions"):
            t = s["total"]
            render_sentinel_metrics([{"label": "評価損益", "value": f"¥{t['pnl_jpy']:,.0f}", "delta": f"{t['pnl_pct']:+.2f}%"}, {"label": "露出度", "value": f"{t['exposure']:.1f}%"}, {"label": "建玉数", "value": t["count"]}, {"label": "余剰", "value": f"¥{t['cash_jpy']:,.0f}"}])
            for p in sorted(s["positions"], key=lambda x: x.get("pnl_pct", 0)):
                if p.get("error"): continue
                cl = "urgent" if p["pnl_pct"] <= -8 else ("profit" if p["pnl_pct"] >= 10 else "caution")
                pnl_c = "pnl-pos" if p["pnl_pct"] > 0 else "pnl-neg"
                ex = p.get("exit", {})
                trail_h = f' | Trail: ${ex["trail"]}' if ex.get("trail") else ""
                st.markdown(f'''
                <div class="pos-card {cl}">
                    <b>{p["status"]} {p["ticker"]}</b> — {p["shares"]}株 @ ${p["avg_cost"]:.2f}<br>
                    現値: ${p["current_price"]:.2f} | 損益: <span class="{pnl_c}">{p["pnl_pct"]:+.2f}% (¥{p["pnl_jpy"]:+,.0f})</span>
                    <div class="exit-info">Stop: ${ex.get("eff_stop","—")} | Target: ${ex.get("eff_tgt","—")} | R: {ex.get("cur_r",0)}{trail_h}</div>
                </div>''', unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button(f"🔍 {p['ticker']}", key=f"d_{p['ticker']}"): st.session_state["target_ticker"] = p['ticker']; st.session_state["trigger_analysis"] = True; st.rerun()
                if c2.button(f"✅ 決済 {p['ticker']}", key=f"cl_{p['ticker']}"): close_position(p['ticker'], sell_price=p['current_price']); st.session_state["portfolio_dirty"] = True; st.rerun()
        else: st.info("No pos.")
    with ps[1]:
        with st.form("new_p"):
            c1, c2 = st.columns(2); nt = c1.text_input("Ticker").upper(); ns = c2.number_input("Shares", min_value=1)
            c3, c4 = st.columns(2); nc = c3.number_input("Cost"); nst = c4.number_input("Stop")
            if st.form_submit_button("Add"): upsert_position(nt, ns, nc, stop=nst); st.session_state["portfolio_dirty"] = True; st.rerun()
    with ps[2]:
        if st.button("🚀 Portfolio AI Analysis"):
            s_d = get_portfolio_summary(usd_jpy); p_t = [f"{p['ticker']}: {p['shares']}株 (損益{p['pnl_pct']:+.1f}%)" for p in s_d["positions"] if not p.get("error")]
            prompt = f"Hedge Fund Manager 分析:\nUSD/JPY: {usd_jpy}\nポジション: {', '.join(p_t)}\nMarkdown形式で1.緊急アクション 2.リスク指摘 3.改善案を出力せよ。"
            with st.spinner("Analyzing..."): st.markdown(call_ai(prompt).replace("$", r"\$"))
    with ps[3]:
        summary = get_portfolio_summary(usd_jpy); closed = summary.get("closed", [])
        if closed:
            cs = summary["closed_stats"]; render_sentinel_metrics([{"label": "決済数", "value": cs["count"]}, {"label": "確定損益", "value": f"¥{cs['pnl_jpy']:+,.0f}"}, {"label": "勝率", "value": f"{cs['win_rate']}%"}])
            st.dataframe(pd.DataFrame(closed[::-1]), use_container_width=True)

st.divider(); st.caption(f"🛡️ SENTINEL PRO | {NOW.strftime('%H:%M:%S')} | Tokenizer Fix Applied")

