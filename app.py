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

# 外部エンジン依存関係（configおよびenginesディレクトリの各エンジン）
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

# 出口戦略アルゴリズム用定数
EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT":      2.5,
    "TRAIL_START_R":      1.5,
    "TRAIL_ATR_MULT":     1.5,
    "SCALE_OUT_R":        1.5,
}

# ==============================================================================
# 🎨 ページ設定 & 視認性向上CSS
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

  /* メトリクスの視認性向上 */
  [data-testid="metric-container"] {
    background: #0d1117;
    border: 1px solid #1e2d40;
    border-radius: 10px;
    padding: 12px 10px;
  }
  [data-testid="metric-container"] label { font-size: 0.72rem !important; color: #6b7280; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 1.15rem !important; font-weight: 700; }

  /* ボタン・タブのスタイル */
  .stButton > button { min-height: 48px; font-size: 1rem !important; font-weight: 600; border-radius: 8px; }
  .stTabs [data-baseweb="tab-list"] { gap: 8px; background-color: #0d1117; padding: 5px; border-radius: 10px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.9rem; padding: 10px 14px; font-weight: 600; }

  /* ポジションカードの詳細デザイン */
  .pos-card          { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
  .pos-card.urgent   { border-left: 5px solid #ef4444; }
  .pos-card.caution  { border-left: 5px solid #f59e0b; }
  .pos-card.profit   { border-left: 5px solid #00ff7f; }

  .pnl-pos { color: #00ff7f; font-weight: 700; font-size: 1.2rem; }
  .pnl-neg { color: #ef4444; font-weight: 700; font-size: 1.2rem; }
  
  .exit-info { font-size: 0.8rem; color: #9ca3af; line-height: 1.8; font-family: 'Share Tech Mono', monospace; }

  .section-header {
    font-size: 1.1rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 6px;
    margin: 14px 0 10px; font-family: 'Share Tech Mono', monospace;
  }

  /* モバイル・デスクトップ共用余白調整 */
  .block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 📋 セッション状態管理
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
# 💾 キャッシュ付きデータ取得
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
    if df is None or len(df) < 15:
        return None
    high = df["High"]; low = df["Low"]; close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low  - close.shift()).abs(),
    ], axis=1).max(axis=1)
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
                date = daily.get("date", f.stem)
                for key in ("selected", "watchlist_wait", "qualified_full"):
                    for item in daily.get(key, []):
                        item["date"]      = date
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except: pass
    return pd.DataFrame(all_data)

@st.cache_data(ttl=1800)
def fetch_news_cached(ticker: str) -> dict:
    return NewsEngine.get(ticker)

@st.cache_data(ttl=3600)
def fetch_fundamental_cached(ticker: str) -> dict:
    return FundamentalEngine.get(ticker)

@st.cache_data(ttl=3600)
def fetch_insider_cached(ticker: str) -> dict:
    return InsiderEngine.get(ticker)

# ==============================================================================
# 🧠 VCP 分析ロジック (バックエンド VCPAnalyzer と完全同期)
# ==============================================================================

def _empty_vcp() -> dict:
    return {
        "score": 0, "atr": 0.0, "signals": [], "is_dryup": False,
        "range_pct": 0.0, "vol_ratio": 1.0
    }

def calc_vcp(df: pd.DataFrame) -> dict:
    """バックエンド VCPAnalyzer の計算ロジックを正確に移植"""
    try:
        if df is None or len(df) < 80:
            return _empty_vcp()

        close = df["Close"]; high = df["High"]; low = df["Low"]; volume = df["Volume"]

        # ATR(14)
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if pd.isna(atr) or atr <= 0:
            return _empty_vcp()

        # 1. Tightness (40pt)
        periods = [20, 30, 40]
        ranges = []
        for p in periods:
            h = float(high.iloc[-p:].max())
            l = float(low.iloc[-p:].min())
            ranges.append((h - l) / h)
        
        avg_range = float(np.mean(ranges))
        # 収縮判定（短期 < 中期 < 長期）
        is_contracting = ranges[0] < ranges[1] < ranges[2]

        if avg_range < 0.12:   tight_score = 40
        elif avg_range < 0.18: tight_score = 30
        elif avg_range < 0.24: tight_score = 20
        elif avg_range < 0.30: tight_score = 10
        else:                  tight_score = 0

        if is_contracting:
            tight_score += 5
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
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        trend_score = (
            (10 if price > ma50 else 0) +
            (10 if ma50 > ma200 else 0) +
            (10 if price > ma200 else 0)
        )

        # 4. Pivot Bonus (最大+5pt)
        pivot = float(high.iloc[-40:].max())
        distance = (pivot - price) / pivot
        pivot_bonus = 0
        if 0 <= distance <= 0.05:
            pivot_bonus = 5
        elif 0.05 < distance <= 0.08:
            pivot_bonus = 3

        signals = []
        if tight_score >= 35: signals.append("Multi-Stage Contraction")
        if is_dryup:          signals.append("Volume Dry-Up")
        if trend_score == 30: signals.append("MA Aligned")
        if pivot_bonus > 0:   signals.append("Near Pivot")

        return {
            "score": int(max(0, tight_score + vol_score + trend_score + pivot_bonus)),
            "atr": atr,
            "signals": signals,
            "is_dryup": is_dryup,
            "range_pct": round(ranges[0], 4),
            "vol_ratio": round(ratio, 2),
        }
    except Exception:
        return _empty_vcp()

# ==============================================================================
# 🤖 AI 連携ロジック
# ==============================================================================

def call_ai(prompt: str) -> str:
    api_key = st.secrets.get("DEEPSEEK_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return "⚠️ DEEPSEEK_API_KEY が未設定です。"
    try:
        client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        res = client.chat.completions.create(
            model="deepseek-reasoner",
            messages=[{"role": "user", "content": prompt}],
        )
        return res.choices[0].message.content or ""
    except Exception as e:
        return f"DeepSeek Error: {e}"

# ==============================================================================
# 📋 I/O 処理
# ==============================================================================

def load_watchlist() -> list:
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE) as f: return json.load(f)
        except: pass
    return []

def _write_watchlist(data: list):
    tmp = Path("watchlist.tmp")
    with open(tmp, "w") as f: json.dump(data, f)
    tmp.replace(WATCHLIST_FILE)

def add_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    if ticker not in wl:
        wl.append(ticker); _write_watchlist(wl); return True
    return False

def remove_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    if ticker in wl:
        wl.remove(ticker); _write_watchlist(wl); return True
    return False

def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f: return json.load(f)
        except: pass
    return {"positions": {}, "closed": [], "meta": {"created": NOW.isoformat()}}

def _write_portfolio(data: dict):
    tmp = Path("portfolio.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(PORTFOLIO_FILE)

def upsert_position(ticker: str, shares: int, avg_cost: float,
                    memo: str = "", target: float = 0.0, stop: float = 0.0) -> dict:
    ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker.upper())[:10]
    data = load_portfolio(); pos = data["positions"]
    if ticker in pos:
        old = pos[ticker]; tot = old["shares"] + shares
        pos[ticker].update({
            "shares":     tot,
            "avg_cost":   round((old["shares"] * old["avg_cost"] + shares * avg_cost) / tot, 4),
            "memo":       memo or old.get("memo", ""),
            "target":     target or old.get("target", 0.0),
            "stop":       stop   or old.get("stop",   0.0),
            "updated_at": NOW.isoformat(),
        })
    else:
        pos[ticker] = {
            "ticker": ticker, "shares": shares, "avg_cost": round(avg_cost, 4),
            "memo": memo, "target": round(target, 4), "stop": round(stop, 4),
            "added_at": NOW.isoformat(), "updated_at": NOW.isoformat(),
        }
    _write_portfolio(data)
    return pos[ticker]

def close_position(ticker: str, shares_sold: Optional[int] = None,
                   sell_price: Optional[float] = None) -> bool:
    data = load_portfolio(); pos = data["positions"]
    if ticker not in pos: return False
    p = pos[ticker]
    actual = shares_sold if shares_sold and shares_sold < p["shares"] else p["shares"]
    if sell_price:
        pnl = (sell_price - p["avg_cost"]) * actual
        data["closed"].append({
            "ticker": ticker, "shares": actual,
            "avg_cost": p["avg_cost"], "sell_price": sell_price,
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2),
            "closed_at": NOW.isoformat(), "memo": p.get("memo", ""),
        })
    if shares_sold and shares_sold < p["shares"]:
        pos[ticker]["shares"] -= shares_sold
    else:
        del pos[ticker]
    _write_portfolio(data)
    return True

# ==============================================================================
# 📊 ポートフォリオ計算エンジン (詳細ロジック完全維持)
# ==============================================================================

def calc_pos_stats(pos: dict, usd_jpy: float) -> dict:
    cp  = get_current_price(pos["ticker"])
    atr = get_atr(pos["ticker"])
    if cp is None:
        return {**pos, "error": True, "current_price": None}

    shares = pos["shares"]; avg = pos["avg_cost"]
    pnl_usd = (cp - avg) * shares
    pnl_pct = (cp / avg - 1) * 100
    mv_usd  = cp * shares
    cb_usd  = avg * shares

    ex = {}
    if atr:
        risk  = atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]
        dyn_stop = round(cp - risk, 4)
        reg_stop = pos.get("stop", 0.0)
        eff_stop = max(dyn_stop, reg_stop) if reg_stop > 0 else dyn_stop
        cur_r    = (cp - avg) / risk if risk > 0 else 0.0
        reg_tgt  = pos.get("target", 0.0)
        eff_tgt  = reg_tgt if reg_tgt > 0 else round(avg + risk * EXIT_CFG["TARGET_R_MULT"], 4)
        trail    = round(cp - atr * EXIT_CFG["TRAIL_ATR_MULT"], 4) if cur_r >= EXIT_CFG["TRAIL_START_R"] else None
        scale    = round(avg + risk * EXIT_CFG["SCALE_OUT_R"], 4)
        ex = {"atr": atr, "risk": round(risk, 4),
              "dyn_stop": dyn_stop, "eff_stop": eff_stop, "eff_tgt": eff_tgt,
              "scale_out": scale, "cur_r": round(cur_r, 2), "trail": trail}

    # ステータス判定
    cur_r = ex.get("cur_r", 0)
    if   pnl_pct <= -8:                          status = "🚨"
    elif pnl_pct <= -4:                          status = "⚠️"
    elif cur_r >= EXIT_CFG["TARGET_R_MULT"]:     status = "🎯"
    elif cur_r >= EXIT_CFG["TRAIL_START_R"]:     status = "📈"
    elif cur_r >= EXIT_CFG["SCALE_OUT_R"]:       status = "💰"
    elif pnl_pct > 0:                            status = "✅"
    else:                                        status = "🔵"

    return {**pos, "current_price": round(cp, 4),
            "pnl_usd": round(pnl_usd, 2), "pnl_pct": round(pnl_pct, 2),
            "pnl_jpy": round(pnl_usd * usd_jpy, 0),
            "mv_usd": round(mv_usd, 2), "cb_usd": round(cb_usd, 2),
            "exit": ex, "status": status}

def get_portfolio_summary(usd_jpy: float) -> dict:
    data  = load_portfolio()
    pos_d = data["positions"]
    if not pos_d:
        return {"positions": [], "total": {}, "closed": data.get("closed", [])}

    stats = [calc_pos_stats(p, usd_jpy) for p in pos_d.values()]
    valid = [s for s in stats if not s.get("error")]
    total_mv  = sum(s["mv_usd"]  for s in valid)
    total_cb  = sum(s["cb_usd"]  for s in valid)
    total_pnl = sum(s["pnl_usd"] for s in valid)
    cap_usd   = CONFIG["CAPITAL_JPY"] / usd_jpy
    for s in valid:
        s["pw"] = round(s["mv_usd"] / total_mv * 100, 1) if total_mv > 0 else 0.0

    closed  = data.get("closed", [])
    win_cnt = len([c for c in closed if c.get("pnl_usd", 0) > 0])
    return {
        "positions": stats,
        "total": {
            "count":    len(valid),
            "mv_usd":   round(total_mv, 2),
            "mv_jpy":   round(total_mv * usd_jpy, 0),
            "pnl_usd":  round(total_pnl, 2),
            "pnl_jpy":  round(total_pnl * usd_jpy, 0),
            "pnl_pct":  round(total_pnl / total_cb * 100 if total_cb else 0, 2),
            "exposure": round(total_mv / cap_usd * 100 if cap_usd else 0, 1),
            "cash_jpy": round((cap_usd - total_mv) * usd_jpy, 0),
        },
        "closed_stats": {
            "count":    len(closed),
            "pnl_usd":  round(sum(c.get("pnl_usd", 0) for c in closed), 2),
            "pnl_jpy":  round(sum(c.get("pnl_usd", 0) for c in closed) * usd_jpy, 0),
            "win_rate": round(win_cnt / len(closed) * 100, 1) if closed else 0.0,
        },
        "closed": closed,
    }

# ==============================================================================
# 🧭 メインナビゲーション (タブ方式による視認性向上)
# ==============================================================================

# サイドバー: Watchlist & 通貨情報
with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    st.caption(TODAY_STR)
    st.markdown("#### ⭐ Watchlist")
    wl = load_watchlist()
    if not wl:
        st.caption("登録なし")
    else:
        for t in wl:
            c1, c2 = st.columns([3, 1])
            if c1.button(t, key=f"wl_{t}", use_container_width=True):
                st.session_state["target_ticker"]    = t
                st.session_state["trigger_analysis"] = True
                # タブの切り替えは自動で行われないため、ユーザーに「診断」タブをクリックしてもらう
            if c2.button("✕", key=f"rm_{t}"):
                remove_watchlist(t); st.rerun()
    st.divider()
    usd_jpy = get_usd_jpy()
    st.metric("💱 USD/JPY", f"¥{usd_jpy}")

# メインタブ
tab_scan, tab_real, tab_port = st.tabs(["📊 スキャン結果", "🔍 リアルタイム診断", "💼 ポートフォリオ管理"])

# ==============================================================================
# 📊 TAB 1: スキャン結果
# ==============================================================================

with tab_scan:
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)
    df_hist = load_historical_json()

    if df_hist.empty:
        st.info("スキャン結果がありません。`python sentinel.py` を実行してください。")
    else:
        latest_date = df_hist["date"].max()
        latest_df   = df_hist[df_hist["date"] == latest_date].drop_duplicates("ticker")

        # サマリー KPI (横並び)
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📅 最終スキャン", latest_date)
        k2.metric("💎 ACTION",  len(latest_df[latest_df["status"] == "ACTION"])  if "status" in latest_df.columns else "—")
        k3.metric("⏳ WAIT",    len(latest_df[latest_df["status"] == "WAIT"])    if "status" in latest_df.columns else "—")
        k4.metric("💱 為替", f"¥{usd_jpy}")

        # セクターマップ
        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in latest_df.columns and "sector" in latest_df.columns:
            fig = px.treemap(
                latest_df, path=["sector", "ticker"],
                values="vcp_score",
                color="rs" if "rs" in latest_df.columns else "vcp_score",
                color_continuous_scale="RdYlGn",
            )
            fig.update_layout(template="plotly_dark", height=350, margin=dict(t=0, b=0, l=0, r=0))
            st.plotly_chart(fig, use_container_width=True)

        # 銘柄テーブル
        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        show_cols = [c for c in ["ticker", "status", "price", "vcp_score", "rs", "sector"] if c in latest_df.columns]
        st.dataframe(
            latest_df[show_cols].sort_values("vcp_score", ascending=False).style.background_gradient(
                subset=["vcp_score"] if "vcp_score" in show_cols else [], cmap="Greens"
            ),
            use_container_width=True, height=350,
        )

        # チャートドリルダウン
        st.markdown('<div class="section-header">🔍 詳細チャート</div>', unsafe_allow_html=True)
        drill = st.selectbox("銘柄を選択してチャートを表示", latest_df["ticker"].unique(), key="drill_select")
        if drill:
            d = fetch_price_data(drill, "1y")
            if d is not None and len(d) >= 10:
                tail = d.tail(120)
                fig_c = go.Figure(go.Candlestick(
                    x=tail.index, open=tail["Open"], high=tail["High"],
                    low=tail["Low"], close=tail["Close"],
                ))
                fig_c.update_layout(template="plotly_dark", height=320,
                                     xaxis_rangeslider_visible=False, margin=dict(t=10, b=0))
                st.plotly_chart(fig_c, use_container_width=True)

# ==============================================================================
# 🔍 TAB 2: リアルタイム診断 (詳細なAIプロンプト構成)
# ==============================================================================

with tab_real:
    st.markdown('<div class="section-header">🔍 リアルタイム診断</div>', unsafe_allow_html=True)
    ticker_in = st.text_input("ティッカー入力 (例: NVDA)", value=st.session_state["target_ticker"]).upper().strip()

    c_run, c_fav = st.columns(2)
    run_btn = c_run.button("🚀 診断開始", type="primary", use_container_width=True)
    fav_btn = c_fav.button("⭐ Watchlist 追加", use_container_width=True)

    if fav_btn and ticker_in:
        if add_watchlist(ticker_in): st.success(f"{ticker_in} を登録しました")
        else: st.info("登録済みです")

    if (run_btn or st.session_state.pop("trigger_analysis", False)) and ticker_in:
        with st.spinner(f"{ticker_in} を深度解析中..."):
            data    = fetch_price_data(ticker_in, "2y")
            news    = fetch_news_cached(ticker_in)
            fund    = fetch_fundamental_cached(ticker_in)
            insider = fetch_insider_cached(ticker_in)

            if data is None or data.empty:
                st.error("データ取得に失敗しました。")
            else:
                vcp = calc_vcp(data)
                cp  = get_current_price(ticker_in) or data["Close"].iloc[-1]

                # KPI表示
                k1, k2, k3, k4 = st.columns(4)
                k1.metric("💰 価格", f"${cp:.2f}")
                k2.metric("🎯 VCP", f"{vcp['score']}/105")
                k3.metric("📊 シグナル", ", ".join(vcp["signals"]) or "特記なし")
                k4.metric("📈 収縮率", f"{vcp['range_pct']*100:.1f}%")

                # チャート
                tail = data.tail(60)
                fig_rt = go.Figure(go.Candlestick(
                    x=tail.index, open=tail["Open"], high=tail["High"],
                    low=tail["Low"], close=tail["Close"],
                ))
                fig_rt.update_layout(template="plotly_dark", height=320,
                                      xaxis_rangeslider_visible=False, margin=dict(t=0))
                st.plotly_chart(fig_rt, use_container_width=True)

                # AI プロンプト用データ整形
                price_now = round(float(cp), 2)
                atr_val   = round(vcp["atr"], 2)
                fund_lines    = FundamentalEngine.format_for_prompt(fund, price_now)
                insider_lines = InsiderEngine.format_for_prompt(insider)
                news_text     = NewsEngine.format_for_prompt(news)

                # 厳密なAIプロンプト構成
                prompt = (
                    f"SENTINEL PRO AI 投資診断: {ticker_in}\n\n"
                    f"━━━ テクニカル（最新実測値） ━━━\n"
                    f"診断日: {TODAY_STR}\n"
                    f"現在値: ${price_now}\n"
                    f"VCPスコア: {vcp['score']}/105  信号: {vcp['signals']}\n"
                    f"直近収縮率: {vcp['range_pct']*100:.1f}%  Vol比率: {vcp['vol_ratio']}\n"
                    f"ATR(14): ${atr_val}\n\n"
                    f"━━━ ファンダメンタル（最新） ━━━\n"
                    f"{chr(10).join(fund_lines) if fund_lines else '取得エラー'}\n\n"
                    + (f"━━━ インサイダー動向 ━━━\n{chr(10).join(insider_lines)}\n\n" if insider_lines else "")
                    + f"━━━ 最新ニュース & コンテキスト ━━━\n"
                    f"{news_text[:2000]}\n\n"
                    f"━━━ 出力要件（Markdown） ━━━\n"
                    f"1. 【現状分析】価格、ニュース、ファンダメンタルの整合性をプロの視点で分析せよ\n"
                    f"2. 【リスク】インサイダーやショート比率、目標株価との乖離を指摘せよ\n"
                    f"3. 【戦略】現在値${price_now}を基準に、ATR=${atr_val}を考慮したEntry/Stop/Targetを示せ\n"
                    f"4. 【結論】Buy/Watch/Avoidを明示し、根拠を一文で述べよ"
                )

                ai_res = call_ai(prompt)
                st.markdown("---")
                st.markdown(ai_res.replace("$", r"\$"))
                st.markdown("---")

                with st.expander("詳細データ確認"):
                    st.json({"vcp": vcp, "fundamentals": fund, "insider": insider})

# ==============================================================================
# 💼 TAB 3: ポートフォリオ管理 (全てのサブ機能維持)
# ==============================================================================

with tab_port:
    # サブタブによる整理
    p_tabs = st.tabs(["📊 現在の損益", "➕ 新規建玉", "🤖 全体分析", "📜 決済履歴"])

    with p_tabs[0]: # 現在の損益
        if st.session_state["portfolio_dirty"]:
            st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy)
            st.session_state["portfolio_dirty"]   = False

        summary = st.session_state["portfolio_summary"]
        if not summary or not summary.get("positions"):
            st.info("保有ポジションがありません。")
        else:
            t = summary["total"]
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 評価損益", f"¥{t['pnl_jpy']:,.0f}", f"{t['pnl_pct']:+.2f}%")
            k2.metric("📦 建玉数", t['count'])
            k3.metric("⚡ 露出度", f"{t['exposure']:.1f}%")
            k4.metric("💵 余剰(JPY)", f"¥{t['cash_jpy']:,.0f}")

            st.markdown('<div class="section-header">📋 ポジション一覧</div>', unsafe_allow_html=True)
            for pos in sorted(summary["positions"], key=lambda x: x.get("pnl_pct", 0)):
                if pos.get("error"): continue
                pct = pos["pnl_pct"]
                card_cls = "urgent" if pct <= -8 else ("caution" if pct <= -4 else ("profit" if pct >= 10 else ""))
                ex = pos.get("exit", {})
                pnl_cls = "pnl-neg" if pct < 0 else "pnl-pos"
                st.markdown(f"""
<div class="pos-card {card_cls}">
  <b>{pos['status']} {pos['ticker']}</b> — {pos['shares']}株 @ ${pos['avg_cost']:.2f}<br>
  現値: ${pos['current_price']:.2f} | 比重: {pos.get('pw',0):.1f}% | <span class="{pnl_cls}">{pct:+.2f}% (¥{pos['pnl_jpy']:+,.0f})</span>
  <div class="exit-info">
    Stop: ${ex.get('eff_stop','—')} | Target: ${ex.get('eff_tgt','—')} | R: {ex.get('cur_r',0):.2f}
    {f" | Trail: ${ex['trail']}" if ex.get('trail') else ""}
  </div>
</div>""", unsafe_allow_html=True)
                c1, c2 = st.columns(2)
                if c1.button(f"🔍 診断 {pos['ticker']}", key=f"diag_{pos['ticker']}"):
                    st.session_state["target_ticker"] = pos["ticker"]
                    st.session_state["trigger_analysis"] = True
                    # ユーザーは手動で「診断」タブへ移動
                if c2.button(f"✅ 決済 {pos['ticker']}", key=f"close_{pos['ticker']}"):
                    close_position(pos["ticker"], sell_price=pos["current_price"])
                    st.session_state["portfolio_dirty"] = True
                    st.rerun()

    with p_tabs[1]: # 新規建玉
        st.markdown('<div class="section-header">➕ 新規建玉の追加</div>', unsafe_allow_html=True)
        with st.form("add_pos_form"):
            f1, f2 = st.columns(2)
            nt = f1.text_input("ティッカー").upper().strip()
            ns = f2.number_input("株数", min_value=1, value=10)
            f3, f4 = st.columns(2)
            nc = f3.number_input("平均取得単価 ($)", value=100.0)
            nstop = f4.number_input("損切りライン ($)", value=0.0)
            f5, f6 = st.columns(2)
            ntgt = f5.number_input("利確目標 ($)", value=0.0)
            nm = f6.text_input("メモ")
            if st.form_submit_button("✅ ポジションを追加", type="primary", use_container_width=True):
                if nt and ns > 0:
                    upsert_position(nt, ns, nc, nm, ntgt, nstop)
                    st.session_state["portfolio_dirty"] = True
                    st.success(f"{nt} を追加しました。")
                    st.rerun()

    with p_tabs[2]: # ポートフォリオAI分析
        if st.button("🚀 ポートフォリオ全体分析実行", type="primary", use_container_width=True):
            s = get_portfolio_summary(usd_jpy)
            if not s.get("positions"):
                st.warning("分析対象がありません。")
            else:
                pos_text = [f"{p['ticker']}: {p['shares']}株 (P/L {p['pnl_pct']:+.1f}%)" for p in s["positions"] if not p.get("error")]
                prompt = (
                    f"プロのファンドマネージャーとして資産状況を分析せよ。\n"
                    f"現在の為替: ¥{usd_jpy}\n"
                    f"合計損益: {s['total']['pnl_pct']}%\n"
                    f"ポジション: {', '.join(pos_text)}\n\n"
                    f"1. 緊急性の高いアクション\n2. リスク管理の指摘\n3. 今後の戦略"
                )
                with st.spinner("分析中..."):
                    ai_rep = call_ai(prompt)
                    st.markdown("---")
                    st.markdown(ai_rep.replace("$", r"\$"))

    with p_tabs[3]: # 決済履歴
        summary = get_portfolio_summary(usd_jpy)
        closed = summary.get("closed", [])
        if not closed:
            st.info("決済履歴はありません。")
        else:
            cs = summary.get("closed_stats", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("🔢 決済数", cs["count"])
            c2.metric("確定損益", f"¥{cs['pnl_jpy']:+,.0f}")
            c3.metric("🏆 通算勝率", f"{cs['win_rate']}%")
            st.dataframe(pd.DataFrame(closed[::-1]), use_container_width=True)

# 共通フッター
st.divider()
st.caption(f"SENTINEL PRO | Version 2.0.0 (VCP Logic Synced) | {NOW.strftime('%H:%M:%S')}")

