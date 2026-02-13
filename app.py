"""
app.py — SENTINEL PRO Streamlit UI (Full Logic & Mobile Grid Optimized)

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

# 外部エンジン依存
from config import CONFIG
from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine, InsiderEngine
from engines.news import NewsEngine

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数 & 出口戦略設定
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
# 🎨 ページ設定 & CSS（モバイルでの縦スペース削減に特化）
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

  /* コンテナの余白を極限まで削る */
  .block-container { padding-top: 0.5rem !important; padding-bottom: 0.5rem !important; }
  
  /* メトリクスのグリッド表示 (モバイルでも縦に並ばせない) */
  .mobile-metric-container {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
    margin-bottom: 10px;
  }
  .m-metric-card {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 8px;
    padding: 8px 10px;
    display: flex;
    flex-direction: column;
  }
  .m-metric-label { font-size: 0.65rem; color: #6b7280; margin-bottom: 2px; text-transform: uppercase; }
  .m-metric-value { font-size: 1.05rem; font-weight: 700; color: #ffffff; }
  .m-metric-delta { font-size: 0.7rem; font-weight: 600; }

  /* タブの最適化 */
  .stTabs [data-baseweb="tab-list"] { gap: 4px; background-color: #0d1117; padding: 2px; border-radius: 8px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.8rem; padding: 8px 10px; font-weight: 600; }
  .stTabs [aria-selected="true"] { background-color: #00ff7f !important; color: #000 !important; border-radius: 6px; }

  /* ポジションカード */
  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 12px; margin-bottom: 8px; }
  .pos-card.urgent { border-left: 4px solid #ef4444; }
  .pos-card.caution { border-left: 4px solid #f59e0b; }
  .pos-card.profit { border-left: 4px solid #00ff7f; }
  .pnl-pos { color: #00ff7f; font-weight: 700; }
  .pnl-neg { color: #ef4444; font-weight: 700; }
  .exit-info { font-size: 0.75rem; color: #9ca3af; font-family: 'Share Tech Mono', monospace; margin-top: 4px; }

  .section-header {
    font-size: 0.95rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 4px;
    margin: 12px 0 8px; font-family: 'Share Tech Mono', monospace;
  }
  
  /* ボタンの高さをモバイル向けに調整 */
  .stButton > button { min-height: 44px; font-size: 0.9rem !important; }

  /* Streamlitデフォルトのメトリクス余白を消去 */
  [data-testid="stMetric"] { padding: 0 !important; }
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
# 💾 データ取得 (キャッシュ・ロジック全維持)
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

        if   avg_range < 0.12: tight_score = 40
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
        if   ratio < 0.50: vol_score = 30
        elif ratio < 0.65: vol_score = 25
        elif ratio < 0.80: vol_score = 15
        else:              vol_score = 0
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
# 🤖 AI (DeepSeek-Reasoner)
# ==============================================================================

def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key: return "⚠️ DEEPSEEK_API_KEY 未設定"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(model="deepseek-reasoner", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content or ""
    except Exception as e: return f"AI Error: {e}"

# ==============================================================================
# 💼 Portfolio 管理 & 計算 (ロジック全維持)
# ==============================================================================

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
        pos[t].update({"shares": tot, "avg_cost": round((old["shares"]*old["avg_cost"] + shares*avg_cost)/tot, 4), "memo": memo or old.get("memo",""), "target": target or old.get("target",0.0), "stop": stop or old.get("stop",0.0), "updated_at": NOW.isoformat()})
    else:
        pos[t] = {"ticker": t, "shares": shares, "avg_cost": round(avg_cost, 4), "memo": memo, "target": round(target, 4), "stop": round(stop, 4), "added_at": NOW.isoformat(), "updated_at": NOW.isoformat()}
    _write_portfolio(data)

def close_position(ticker, shares_sold=None, sell_price=None):
    data = load_portfolio(); pos = data["positions"]
    if ticker not in pos: return False
    p = pos[ticker]; actual = shares_sold if shares_sold else p["shares"]
    if sell_price:
        data["closed"].append({"ticker": ticker, "shares": actual, "avg_cost": p["avg_cost"], "sell_price": sell_price, "pnl_usd": round((sell_price - p["avg_cost"]) * actual, 2), "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2), "closed_at": NOW.isoformat(), "memo": p.get("memo", "")})
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
        ex = {"atr": atr, "risk": round(risk, 4), "dyn_stop": dyn_stop, "eff_stop": eff_stop, "eff_tgt": eff_tgt, "cur_r": round(cur_r, 2), "trail": trail}
    status = "🔵"
    if pnl_pct <= -8: status = "🚨"
    elif pnl_pct <= -4: status = "⚠️"
    elif ex.get("cur_r", 0) >= EXIT_CFG["TARGET_R_MULT"]: status = "🎯"
    elif pnl_pct > 0: status = "✅"
    return {**pos, "current_price": round(cp, 4), "pnl_usd": round(pnl_usd, 2), "pnl_pct": round(pnl_pct, 2), "pnl_jpy": round(pnl_usd * usd_jpy, 0), "mv_usd": round(cp * shares, 2), "cb_usd": round(avg * shares, 2), "exit": ex, "status": status}

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
# 🎨 UI ヘルパー: コンパクト・メトリクス
# ==============================================================================

def mobile_metrics(metrics_list):
    """HTMLを使用してモバイルでも縦に並ばないメトリクス・グリッドを作成"""
    html = '<div class="mobile-metric-container">'
    for m in metrics_list:
        delta_color = "#00ff7f" if "+" in str(m.get('delta', '')) or (isinstance(m.get('delta'), (int, float)) and m.get('delta') > 0) else "#ef4444"
        delta_str = f'<span class="m-metric-delta" style="color: {delta_color}">{m.get("delta", "")}</span>' if m.get("delta") else ""
        html += f'''
        <div class="m-metric-card">
            <div class="m-metric-label">{m["label"]}</div>
            <div class="m-metric-value">{m["value"]}</div>
            {delta_str}
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
        if c1.button(f"🔍 {t}", key=f"wl_{t}", use_container_width=True):
            st.session_state["target_ticker"] = t; st.session_state["trigger_analysis"] = True
        if c2.button("×", key=f"rm_{t}"):
            wl.remove(t); _write_watchlist(wl); st.rerun()

usd_jpy = get_usd_jpy()
tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン", "🔍 診断", "💼 資産"])

# ------------------------------------------------------------------------------
# 📊 TAB 1: スキャン
# ------------------------------------------------------------------------------
with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_hist = load_historical_json()
    if df_hist.empty:
        st.info("データがありません。")
    else:
        latest_date = df_hist["date"].max(); latest_df = df_hist[df_hist["date"] == latest_date].drop_duplicates("ticker")
        
        # モバイルでも縦長にならないよう2x2グリッドで表示
        mobile_metrics([
            {"label": "📅 最終スキャン", "value": latest_date},
            {"label": "💱 為替 (USD/JPY)", "value": f"¥{usd_jpy}"},
            {"label": "💎 ACTION", "value": len(latest_df[latest_df["status"] == "ACTION"]) if "status" in latest_df.columns else "0"},
            {"label": "⏳ WAIT", "value": len(latest_df[latest_df["status"] == "WAIT"]) if "status" in latest_df.columns else "0"}
        ])

        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in latest_df.columns:
            fig = px.treemap(latest_df, path=["sector", "ticker"], values="vcp_score", color="vcp_score", color_continuous_scale="RdYlGn")
            fig.update_layout(template="plotly_dark", height=280, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})

        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        st.dataframe(latest_df[["ticker", "status", "vcp_score", "sector"]].sort_values("vcp_score", ascending=False), use_container_width=True, height=250)

# ------------------------------------------------------------------------------
# 🔍 TAB 2: 診断
# ------------------------------------------------------------------------------
with tab_real:
    st.markdown('<div class="section-header">🔍 AI リアルタイム診断</div>', unsafe_allow_html=True)
    t_in = st.text_input("ティッカー入力 (NVDA, TSLA...)", value=st.session_state["target_ticker"]).upper().strip()
    
    col_run, col_add = st.columns(2)
    run_req = col_run.button("🚀 診断開始", type="primary", use_container_width=True)
    add_req = col_add.button("⭐ Watchlist追加", use_container_width=True)
    
    if add_req and t_in:
        wl = load_watchlist()
        if t_in not in wl: wl.append(t_in); _write_watchlist(wl); st.success(f"{t_in} を追加")

    if (run_req or st.session_state.pop("trigger_analysis", False)) and t_in:
        with st.spinner(f"{t_in} 解析中..."):
            data = fetch_price_data(t_in, "2y"); cp = get_current_price(t_in); vcp = calc_vcp(data)
            news = fetch_news_cached(t_in); fund = fetch_fundamental_cached(t_in); insider = fetch_insider_cached(t_in)
            
            if data is not None and not data.empty:
                current_p = cp or data["Close"].iloc[-1]
                mobile_metrics([
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

                # AI プロンプト (ロジック維持)
                fund_lines = FundamentalEngine.format_for_prompt(fund, current_p); insider_lines = InsiderEngine.format_for_prompt(insider); news_text = NewsEngine.format_for_prompt(news)
                prompt = (f"Analyze {t_in}. Price: ${current_p:.2f}, VCP: {vcp['score']}/105, Signals: {vcp['signals']}.\n"
                          f"Fundamental: {fund_lines}\nInsider: {insider_lines}\nNews: {news_text[:1200]}\n"
                          f"Markdown形式で1.現状 2.リスク 3.戦略(Entry/Stop/Target) 4.結論(Buy/Watch/Avoid)を出力せよ。")
                ai_res = call_ai(prompt)
                st.markdown("---"); st.markdown(ai_res.replace("$", r"\$")); st.markdown("---")
            else: st.error("取得失敗")

# ------------------------------------------------------------------------------
# 💼 TAB 3: ポートフォリオ
# ------------------------------------------------------------------------------
with tab_port:
    st.markdown('<div class="section-header">💼 資産状況</div>', unsafe_allow_html=True)
    if st.session_state["portfolio_dirty"]:
        st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy); st.session_state["portfolio_dirty"] = False
    
    s = st.session_state["portfolio_summary"]
    if s and s.get("positions"):
        t = s["total"]
        mobile_metrics([
            {"label": "💰 評価損益", "value": f"¥{t['pnl_jpy']:,.0f}", "delta": f"{t['pnl_pct']:+.2f}%"},
            {"label": "⚡ 露出度", "value": f"{t['exposure']:.1f}%"},
            {"label": "📦 建玉数", "value": t["count"]},
            {"label": "💵 余剰(JPY)", "value": f"¥{t['cash_jpy']:,.0f}"}
        ])

        st.markdown('<div class="section-header">📋 ポジション一覧</div>', unsafe_allow_html=True)
        for p in sorted(s["positions"], key=lambda x: x.get("pnl_pct", 0)):
            if p.get("error"): continue
            card_cls = "urgent" if p["pnl_pct"] <= -8 else ("profit" if p["pnl_pct"] >= 10 else "caution")
            ex = p.get("exit", {})
            st.markdown(f"""
            <div class="pos-card {card_cls}">
                <b>{p['status']} {p['ticker']}</b> — {p['shares']}株 @ ${p['avg_cost']:.2f}<br>
                現値: ${p['current_price']:.2f} | 損益: <span class="{'pnl-pos' if p['pnl_pct']>0 else 'pnl-neg'}">{p['pnl_pct']:+.2f}% (¥{p['pnl_jpy']:+,.0f})</span>
                <div class="exit-info">Stop: ${ex.get('eff_stop','—')} | Target: ${ex.get('eff_tgt','—')} | R: {ex.get('cur_r',0)}</div>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"決済 {p['ticker']}", key=f"cl_{p['ticker']}"):
                close_position(p['ticker'], sell_price=p['current_price']); st.session_state["portfolio_dirty"] = True; st.rerun()
    else: st.info("保有なし")

    with st.expander("➕ 新規建玉追加"):
        with st.form("add_p"):
            f1, f2 = st.columns(2); nt = f1.text_input("Ticker").upper(); ns = f2.number_input("Shares", min_value=1)
            f3, f4 = st.columns(2); nc = f3.number_input("Avg Cost"); nstop = f4.number_input("Stop Loss")
            if st.form_submit_button("追加"):
                upsert_position(nt, ns, nc, stop=nstop); st.session_state["portfolio_dirty"] = True; st.rerun()

st.divider()
st.caption(f"SENTINEL PRO | {NOW.strftime('%H:%M:%S')}")

