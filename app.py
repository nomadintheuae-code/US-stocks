"""
🛡️ SENTINEL PRO — 完全版 app.py
市場スキャン + リアルタイム診断 + ポートフォリオ管理
"""

import json
import os
import pickle
import re
import time
import warnings
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
import yfinance as yf
from openai import OpenAI

# engines がなくても動くようにフォールバック（必要に応じてコメントアウト解除）
try:
    from config import CONFIG
    from engines.data import CurrencyEngine, DataEngine
    from engines.fundamental import FundamentalEngine, InsiderEngine
    from engines.news import NewsEngine
except ImportError:
    # フォールバック用ダミー（公開版用）
    class DummyEngine:
        @staticmethod
        def get_usd_jpy(): return 150.0
        @staticmethod
        def get_data(ticker, period="1y"): return None
        @staticmethod
        def get_current_price(ticker): return None
        @staticmethod
        def get(ticker): return {}
        @staticmethod
        def format_for_prompt(data, price): return []
    CurrencyEngine = DataEngine = DummyEngine
    FundamentalEngine = InsiderEngine = NewsEngine = DummyEngine
    config = {
        "CAPITAL_JPY": 10000000,
        "MIN_RS_RATING": 70,
        "MIN_VCP_SCORE": 55,
        "MIN_PROFIT_FACTOR": 1.5,
        "STOP_LOSS_ATR": 2.0,
        "TARGET_R_MULTIPLE": 2.5,
        "MAX_SAME_SECTOR": 2,
        "MAX_POSITIONS": 8,
    }

warnings.filterwarnings("ignore")

# ==============================================================================
# 🔧 定数
# ==============================================================================

NOW = datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
CACHE_DIR = Path("./cache_v45")
CACHE_DIR.mkdir(exist_ok=True)
RESULTS_DIR = Path("./results")
RESULTS_DIR.mkdir(exist_ok=True)
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

EXIT_CFG = {
    "STOP_LOSS_ATR_MULT": 2.0,
    "TARGET_R_MULT": 2.5,
    "TRAIL_START_R": 1.5,
    "TRAIL_ATR_MULT": 1.5,
    "SCALE_OUT_R": 1.5,
}

# ==============================================================================
# 🎨 ページ設定 & CSS
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
  [data-testid="metric-container"] {
    background: #0d1117; border: 1px solid #1e2d40; border-radius: 10px; padding: 12px 10px;
  }
  [data-testid="metric-container"] label { font-size: 0.72rem !important; color: #6b7280; }
  [data-testid="metric-container"] [data-testid="stMetricValue"] { font-size: 1.15rem !important; font-weight: 700; }
  .stButton > button { min-height: 48px; font-size: 1rem !important; font-weight: 600; border-radius: 8px; }
  .stTabs [data-baseweb="tab"] { font-size: 0.9rem; padding: 10px 8px; font-weight: 600; }
  .pos-card { background: #111827; border: 1px solid #1f2937; border-radius: 10px; padding: 14px; margin-bottom: 10px; }
  .pos-card.urgent { border-color: #ef4444; }
  .pos-card.caution { border-color: #f59e0b; }
  .pos-card.profit { border-color: #00ff7f; }
  .pnl-pos { color: #00ff7f; font-weight: 700; font-size: 1.2rem; }
  .pnl-neg { color: #ef4444; font-weight: 700; font-size: 1.2rem; }
  .pnl-neu { color: #9ca3af; font-weight: 700; font-size: 1.2rem; }
  .exit-info { font-size: 0.8rem; color: #9ca3af; line-height: 1.8; font-family: 'Share Tech Mono', monospace; }
  .section-header {
    font-size: 1.1rem; font-weight: 700; color: #00ff7f;
    border-bottom: 1px solid #1f2937; padding-bottom: 6px;
    margin: 14px 0 10px; font-family: 'Share Tech Mono', monospace;
  }
  [data-testid="stDataFrame"] { overflow-x: auto; }
  .block-container { padding-top: 0.8rem !important; padding-bottom: 1rem !important; }
  @media (max-width: 768px) {
    .block-container { padding-left: 0.5rem !important; padding-right: 0.5rem !important; }
  }
</style>
""", unsafe_allow_html=True)

# ==============================================================================
# 📋 セッション状態
# ==============================================================================

_defaults = {
    "mode": "📊 スキャン",
    "target_ticker": "",
    "trigger_analysis": False,
    "usd_jpy": 150.0,
    "portfolio_dirty": True,
    "portfolio_summary": None,
}
for k, v in _defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v

# ==============================================================================
# 💾 データ取得（Streamlitキャッシュ）
# ==============================================================================

@st.cache_data(ttl=600)
def get_usd_jpy() -> float:
    rate = CurrencyEngine.get_usd_jpy()
    st.session_state["usd_jpy"] = rate
    return rate

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
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr = pd.concat([
        high - low,
        (high - close.shift()).abs(),
        (low - close.shift()).abs(),
    ], axis=1).max(axis=1)
    atr_val = tr.rolling(14).mean().iloc[-1]
    return round(float(atr_val), 4) if not pd.isna(atr_val) else None

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
                        item["date"] = date
                        item["vcp_score"] = item.get("vcp", {}).get("score", 0)
                        all_data.append(item)
            except Exception:
                pass
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
# 🧠 VCP分析（アプリ内）
# ==============================================================================

def calc_vcp(df: pd.DataFrame) -> dict:
    try:
        close = df["Close"]
        high = df["High"]
        low = df["Low"]
        volume = df["Volume"]
        tr = pd.concat([
            high - low,
            (high - close.shift()).abs(),
            (low - close.shift()).abs(),
        ], axis=1).max(axis=1)
        atr = float(tr.rolling(14).mean().iloc[-1])
        if np.isnan(atr) or atr <= 0:
            return {"score": 0, "atr": 0, "signals": [], "is_dryup": False}

        h10 = float(high.iloc[-10:].max())
        l10 = float(low.iloc[-10:].min())
        range_pct = (h10 - l10) / h10
        tight_score = 40 if range_pct <= 0.05 else int(40 * (1 - (range_pct - 0.05) / 0.10))
        tight_score = max(0, min(40, tight_score))

        vol_ma = float(volume.rolling(50).mean().iloc[-1])
        vol_ratio = float(volume.iloc[-1] / vol_ma) if vol_ma > 0 else 1.0
        is_dryup = vol_ratio < 0.7
        vol_score = 30 if is_dryup else (15 if vol_ratio < 1.1 else 0)

        ma50 = float(close.rolling(50).mean().iloc[-1])
        ma200 = float(close.rolling(200).mean().iloc[-1])
        price = float(close.iloc[-1])
        trend_score = (
            (10 if price > ma50 else 0) +
            (10 if ma50 > ma200 else 0) +
            (10 if price > ma200 else 0)
        )

        signals = []
        if range_pct < 0.06: signals.append("極度収縮")
        if is_dryup: signals.append("Vol枯渇")
        if trend_score == 30: signals.append("MA整列")

        return {
            "score": int(max(0, tight_score + vol_score + trend_score)),
            "atr": atr,
            "signals": signals,
            "is_dryup": is_dryup
        }
    except Exception:
        return {"score": 0, "atr": 0, "signals": [], "is_dryup": False}

# ==============================================================================
# 🤖 AI呼び出し
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
            temperature=0.7,
            max_tokens=1200,
        )
        return res.choices[0].message.content.strip() or ""
    except Exception as e:
        return f"DeepSeek Error: {str(e)}"

# ==============================================================================
# 📋 Watchlist 管理
# ==============================================================================

def load_watchlist() -> list[str]:
    if WATCHLIST_FILE.exists():
        try:
            with open(WATCHLIST_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return []

def save_watchlist(data: list[str]):
    tmp = WATCHLIST_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    tmp.replace(WATCHLIST_FILE)

def add_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    ticker = ticker.upper().strip()
    if ticker not in wl:
        wl.append(ticker)
        save_watchlist(wl)
        return True
    return False

def remove_watchlist(ticker: str) -> bool:
    wl = load_watchlist()
    ticker = ticker.upper().strip()
    if ticker in wl:
        wl.remove(ticker)
        save_watchlist(wl)
        return True
    return False

# ==============================================================================
# 💼 Portfolio 管理（ここから復元）
# ==============================================================================

def load_portfolio() -> dict:
    if PORTFOLIO_FILE.exists():
        try:
            with open(PORTFOLIO_FILE, encoding="utf-8") as f:
                return json.load(f)
        except:
            pass
    return {"positions": {}, "closed": [], "meta": {"created": NOW.isoformat()}}

def save_portfolio(data: dict):
    tmp = PORTFOLIO_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    tmp.replace(PORTFOLIO_FILE)

def upsert_position(ticker: str, shares: int, avg_cost: float,
                    memo: str = "", target: float = 0.0, stop: float = 0.0) -> dict:
    ticker = re.sub(r"[^A-Z0-9.\-]", "", ticker.upper())[:10]
    data = load_portfolio()
    pos = data["positions"]
    if ticker in pos:
        old = pos[ticker]
        tot = old["shares"] + shares
        pos[ticker].update({
            "shares": tot,
            "avg_cost": round((old["shares"] * old["avg_cost"] + shares * avg_cost) / tot, 4),
            "memo": memo or old.get("memo", ""),
            "target": target or old.get("target", 0.0),
            "stop": stop or old.get("stop", 0.0),
            "updated_at": NOW.isoformat(),
        })
    else:
        pos[ticker] = {
            "ticker": ticker,
            "shares": shares,
            "avg_cost": round(avg_cost, 4),
            "memo": memo,
            "target": round(target, 4),
            "stop": round(stop, 4),
            "added_at": NOW.isoformat(),
            "updated_at": NOW.isoformat(),
        }
    save_portfolio(data)
    return pos[ticker]

def close_position(ticker: str, shares_sold: Optional[int] = None, sell_price: Optional[float] = None) -> bool:
    data = load_portfolio()
    pos = data["positions"]
    if ticker not in pos:
        return False
    p = pos[ticker]
    actual = shares_sold if shares_sold and shares_sold < p["shares"] else p["shares"]
    if sell_price:
        pnl = (sell_price - p["avg_cost"]) * actual
        data["closed"].append({
            "ticker": ticker,
            "shares": actual,
            "avg_cost": p["avg_cost"],
            "sell_price": sell_price,
            "pnl_usd": round(pnl, 2),
            "pnl_pct": round((sell_price / p["avg_cost"] - 1) * 100, 2) if p["avg_cost"] > 0 else 0,
            "closed_at": NOW.isoformat(),
            "memo": p.get("memo", ""),
        })
    if shares_sold and shares_sold < p["shares"]:
        pos[ticker]["shares"] -= shares_sold
    else:
        del pos[ticker]
    save_portfolio(data)
    return True

def calc_pos_stats(pos: dict, usd_jpy: float) -> dict:
    cp = get_current_price(pos["ticker"])
    atr = get_atr(pos["ticker"])
    if cp is None:
        return {**pos, "error": True, "current_price": None}

    shares = pos["shares"]
    avg = pos["avg_cost"]
    pnl_usd = (cp - avg) * shares
    pnl_pct = (cp / avg - 1) * 100 if avg > 0 else 0
    mv_usd = cp * shares
    cb_usd = avg * shares

    ex = {}
    if atr:
        risk = atr * EXIT_CFG["STOP_LOSS_ATR_MULT"]
        dyn_stop = round(cp - risk, 4)
        reg_stop = pos.get("stop", 0.0)
        eff_stop = max(dyn_stop, reg_stop) if reg_stop > 0 else dyn_stop
        cur_r = (cp - avg) / risk if risk > 0 else 0.0
        reg_tgt = pos.get("target", 0.0)
        eff_tgt = reg_tgt if reg_tgt > 0 else round(avg + risk * EXIT_CFG["TARGET_R_MULT"], 4)
        trail = round(cp - atr * EXIT_CFG["TRAIL_ATR_MULT"], 4) if cur_r >= EXIT_CFG["TRAIL_START_R"] else None
        scale = round(avg + risk * EXIT_CFG["SCALE_OUT_R"], 4)
        ex = {"atr": atr, "risk": round(risk, 4), "dyn_stop": dyn_stop, "eff_stop": eff_stop,
              "eff_tgt": eff_tgt, "scale_out": scale, "cur_r": round(cur_r, 2), "trail": trail}

    cur_r = ex.get("cur_r", 0)
    if pnl_pct <= -8: status = "🚨"
    elif pnl_pct <= -4: status = "⚠️"
    elif cur_r >= EXIT_CFG["TARGET_R_MULT"]: status = "🎯"
    elif cur_r >= EXIT_CFG["TRAIL_START_R"]: status = "📈"
    elif cur_r >= EXIT_CFG["SCALE_OUT_R"]: status = "💰"
    elif pnl_pct > 0: status = "✅"
    else: status = "🔵"

    return {
        **pos,
        "current_price": round(cp, 4),
        "pnl_usd": round(pnl_usd, 2),
        "pnl_pct": round(pnl_pct, 2),
        "pnl_jpy": round(pnl_usd * usd_jpy, 0),
        "mv_usd": round(mv_usd, 2),
        "cb_usd": round(cb_usd, 2),
        "exit": ex,
        "status": status,
    }

def get_portfolio_summary(usd_jpy: float) -> dict:
    data = load_portfolio()
    pos_d = data["positions"]
    if not pos_d:
        return {"positions": [], "total": {}, "closed": data.get("closed", [])}

    stats = [calc_pos_stats(p, usd_jpy) for p in pos_d.values()]
    valid = [s for s in stats if not s.get("error")]
    total_mv = sum(s["mv_usd"] for s in valid)
    total_cb = sum(s["cb_usd"] for s in valid)
    total_pnl = sum(s["pnl_usd"] for s in valid)
    cap_usd = config.get("CAPITAL_JPY", 10000000) / usd_jpy

    for s in valid:
        s["pw"] = round(s["mv_usd"] / total_mv * 100, 1) if total_mv > 0 else 0.0

    closed = data.get("closed", [])
    win_cnt = len([c for c in closed if c.get("pnl_usd", 0) > 0])

    return {
        "positions": stats,
        "total": {
            "count": len(valid),
            "mv_usd": round(total_mv, 2),
            "mv_jpy": round(total_mv * usd_jpy, 0),
            "pnl_usd": round(total_pnl, 2),
            "pnl_jpy": round(total_pnl * usd_jpy, 0),
            "pnl_pct": round(total_pnl / total_cb * 100 if total_cb else 0, 2),
            "exposure": round(total_mv / cap_usd * 100 if cap_usd else 0, 1),
            "cash_jpy": round((cap_usd - total_mv) * usd_jpy, 0),
        },
        "closed_stats": {
            "count": len(closed),
            "pnl_usd": round(sum(c.get("pnl_usd", 0) for c in closed), 2),
            "pnl_jpy": round(sum(c.get("pnl_usd", 0) for c in closed) * usd_jpy, 0),
            "win_rate": round(win_cnt / len(closed) * 100, 1) if closed else 0.0,
        },
        "closed": closed,
    }

# ==============================================================================
# 🖥️ サイドバー
# ==============================================================================

with st.sidebar:
    st.markdown("### 🛡️ SENTINEL PRO")
    st.caption(TODAY_STR)
    st.markdown("#### ⭐ Watchlist")
    wl = load_watchlist()
    if not wl:
        st.caption("なし")
    else:
        for t in sorted(wl):
            c1, c2 = st.columns([4, 1])
            if c1.button(t, key=f"wl_{t}", use_container_width=True):
                st.session_state["target_ticker"] = t
                st.session_state["trigger_analysis"] = True
                st.session_state["mode"] = "🔍 リアルタイム"
                st.rerun()
            if c2.button("✕", key=f"rm_{t}"):
                remove_watchlist(t)
                st.rerun()

    st.divider()
    usd_jpy_sidebar = get_usd_jpy()
    st.metric("💱 USD/JPY", f"¥{usd_jpy_sidebar:,.0f}")

# ==============================================================================
# 🧭 モード選択
# ==============================================================================

mode_options = ["📊 スキャン", "🔍 リアルタイム", "💼 ポートフォリオ"]
mode = st.radio(
    "モード",
    mode_options,
    horizontal=True,
    index=mode_options.index(st.session_state["mode"]),
    label_visibility="collapsed",
)
st.session_state["mode"] = mode

usd_jpy = get_usd_jpy()

# ==============================================================================
# 📊 MODE 1: スキャン結果（復元）
# ==============================================================================

if mode == "📊 スキャン":
    st.markdown('<div class="section-header">📊 最新スキャン結果</div>', unsafe_allow_html=True)

    df_hist = load_historical_json()

    if df_hist.empty:
        st.info("まだスキャン結果がありません。`python sentinel.py` を実行してください。")
    else:
        latest_date = df_hist["date"].max()
        latest_df = df_hist[df_hist["date"] == latest_date].drop_duplicates("ticker")

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("📅 最終スキャン", latest_date)
        k2.metric("💎 ACTION", len(latest_df[latest_df["status"] == "ACTION"]) if "status" in latest_df.columns else "—")
        k3.metric("⏳ WAIT", len(latest_df[latest_df["status"] == "WAIT"]) if "status" in latest_df.columns else "—")
        k4.metric("💱 USD/JPY", f"¥{usd_jpy:,.0f}")

        st.markdown('<div class="section-header">🗺️ セクターマップ</div>', unsafe_allow_html=True)
        if "vcp_score" in latest_df.columns and "sector" in latest_df.columns:
            fig = px.treemap(
                latest_df,
                path=["sector", "ticker"],
                values="vcp_score",
                color="rs" if "rs" in latest_df.columns else "vcp_score",
                color_continuous_scale="RdYlGn",
            )
            fig.update_layout(template="plotly_dark", height=320, margin=dict(t=10, b=0))
            st.plotly_chart(fig, use_container_width=True)

        st.markdown('<div class="section-header">💎 銘柄リスト</div>', unsafe_allow_html=True)
        show_cols = [c for c in ["ticker", "status", "price", "vcp_score", "rs", "sector"] if c in latest_df.columns]
        if show_cols:
            st.dataframe(
                latest_df[show_cols].style.background_gradient(
                    subset=["vcp_score"] if "vcp_score" in show_cols else [],
                    cmap="Greens"
                ),
                use_container_width=True,
                height=300,
            )

        st.markdown('<div class="section-header">🔍 詳細チャート</div>', unsafe_allow_html=True)
        drill = st.selectbox("銘柄を選択", [""] + list(latest_df["ticker"].unique()), key="drill_select")
        if drill:
            d = fetch_price_data(drill, "1y")
            if d is not None and len(d) >= 10:
                tail = d.tail(120)
                fig_c = go.Figure(go.Candlestick(
                    x=tail.index,
                    open=tail["Open"],
                    high=tail["High"],
                    low=tail["Low"],
                    close=tail["Close"],
                ))
                fig_c.update_layout(
                    template="plotly_dark",
                    height=320,
                    xaxis_rangeslider_visible=False,
                    margin=dict(t=10, b=0)
                )
                st.plotly_chart(fig_c, use_container_width=True)

            with st.expander("📰 最新ニュース"):
                news = fetch_news_cached(drill)
                st.write(NewsEngine.format_for_prompt(news))

# ==============================================================================
# 🔍 MODE 2: リアルタイム診断（復元）
# ==============================================================================

elif mode == "🔍 リアルタイム":
    st.markdown('<div class="section-header">🔍 リアルタイム診断</div>', unsafe_allow_html=True)

    ticker_in = st.text_input(
        "ティッカー入力",
        value=st.session_state["target_ticker"],
        placeholder="NVDA, TSLA, AAPL ...",
        key="ticker_input"
    ).upper().strip()

    c_run, c_fav = st.columns(2)
    run_btn = c_run.button("🚀 診断開始", type="primary", use_container_width=True)
    fav_btn = c_fav.button("⭐ Watchlist追加", use_container_width=True)

    if fav_btn and ticker_in:
        if add_watchlist(ticker_in):
            st.success(f"{ticker_in} をWatchlistに追加しました")
        else:
            st.info(f"{ticker_in} は既に登録済みです")

    do_run = run_btn or st.session_state.pop("trigger_analysis", False)

    if do_run and ticker_in:
        clean = re.sub(r"[^A-Z0-9.\-]", "", ticker_in)[:10]

        with st.spinner(f"{clean} を解析中..."):
            data = fetch_price_data(clean, "2y")
            news = fetch_news_cached(clean)
            fund = fetch_fundamental_cached(clean)
            insider = fetch_insider_cached(clean)

            if data is None or data.empty:
                st.error("価格データの取得に失敗しました。ティッカーを確認してください。")
            else:
                vcp = calc_vcp(data)
                cp = get_current_price(clean)

                k1, k2, k3, k4 = st.columns(4)
                k1.metric("💰 現在値", f"${cp:.2f}" if cp else "N/A")
                k2.metric("🎯 VCPスコア", f"{vcp['score']}/100")
                k3.metric("📊 シグナル", ", ".join(vcp["signals"]) or "なし")
                if fund.get("analyst_upside") is not None:
                    k4.metric(
                        "🎯 アナリスト乖離",
                        f"{fund['analyst_upside']:+.1f}%",
                        f"目標 ${fund.get('analyst_target', 'N/A'):.1f}"
                    )
                else:
                    k4.metric("📋 推奨", (fund.get("recommendation") or "N/A").upper())

                if insider.get("alert"):
                    st.warning(f"⚠️ インサイダー大量売却検出: {insider.get('summary', '')}")
                elif insider.get("summary"):
                    st.caption(f"👤 インサイダー動向: {insider.get('summary', '')}")

                tail = data.tail(60)
                fig_rt = go.Figure(go.Candlestick(
                    x=tail.index,
                    open=tail["Open"],
                    high=tail["High"],
                    low=tail["Low"],
                    close=tail["Close"],
                ))
                fig_rt.update_layout(
                    template="plotly_dark",
                    height=320,
                    xaxis_rangeslider_visible=False,
                    margin=dict(t=10, b=0)
                )
                st.plotly_chart(fig_rt, use_container_width=True)

                price_now = round(float(cp if cp else data["Close"].iloc[-1]), 2)
                price_1w = round(float(data["Close"].iloc[-5]), 2) if len(data) >= 5 else price_now
                price_1m = round(float(data["Close"].iloc[-21]), 2) if len(data) >= 21 else price_now
                price_3m = round(float(data["Close"].iloc[-63]), 2) if len(data) >= 63 else price_now
                price_52wl = round(float(data["Low"].rolling(252).min().iloc[-1]), 2) if len(data) >= 252 else price_now
                price_52wh = round(float(data["High"].rolling(252).max().iloc[-1]), 2) if len(data) >= 252 else price_now
                ma50_val = round(float(data["Close"].rolling(50).mean().iloc[-1]), 2)
                ma200_val = round(float(data["Close"].rolling(200).mean().iloc[-1]), 2)
                chg_1w = round((price_now / price_1w - 1) * 100, 1) if price_1w > 0 else 0
                chg_1m = round((price_now / price_1m - 1) * 100, 1) if price_1m > 0 else 0
                chg_3m = round((price_now / price_3m - 1) * 100, 1) if price_3m > 0 else 0
                atr_val = round(vcp.get("atr", 0), 2)
                pivot_val = round(float(data["High"].iloc[-20:].max()), 2)

                fund_lines = FundamentalEngine.format_for_prompt(fund, price_now)
                insider_lines = InsiderEngine.format_for_prompt(insider)
                news_text = NewsEngine.format_for_prompt(news)

                prompt = f"""あなたはウォール街のトップヘッジファンドマネージャー「SENTINEL」として、銘柄 {clean} を徹底診断してください。
現在の日付は {TODAY_STR} です。以下の最新データを基に、古い知識ではなく実測値のみで分析せよ。

【テクニカルデータ】
現在値: ${price_now:.2f}
変化率: 1週 {chg_1w:+.1f}%, 1ヶ月 {chg_1m:+.1f}%, 3ヶ月 {chg_3m:+.1f}%
52週レンジ: ${price_52wl:.2f} - ${price_52wh:.2f}
MA50: ${ma50_val:.2f}   MA200: ${ma200_val:.2f}
ATR(14): ${atr_val:.2f}   直近20日ピボット: ${pivot_val:.2f}
VCPスコア: {vcp['score']}/100   シグナル: {', '.join(vcp['signals']) or 'なし'}

【ファンダメンタル】
{'\n'.join(fund_lines) if fund_lines else '取得できず'}

{('【インサイダー取引】\n' + '\n'.join(insider_lines) + '\n' if insider_lines else '')}

【最新ニュース】
{news_text}

【出力形式】Markdown形式、800文字以上
1. 【現状分析】現在値 ${price_now:.2f} を起点に、ニュース・ファンダメンタルを具体的に引用
2. 【隠れたリスク】アナリスト乖離・インサイダー動向・空売り比率を必ず言及
3. 【エントリー戦略】現在値から5〜15%以内の現実的な押し目水準を提案
4. 【損切りライン】ATR ${atr_val:.2f} ベースで具体的な価格
5. 【利確目標】Target1/2/3 を具体価格で
6. 【総合判断】Buy / Watch / Avoid を明言 + 一言根拠
"""

                ai_response = call_ai(prompt)
                st.markdown("---")
                st.markdown(ai_response.replace("$", r"\$"))
                st.markdown("---")

                with st.expander("📰 ニュース詳細"):
                    st.write(news_text)
                with st.expander("📊 ファンダメンタル詳細"):
                    st.json(fund)

# ==============================================================================
# 💼 MODE 3: ポートフォリオ（すでに復元済み）
# ==============================================================================

else:
    st.markdown('<div class="section-header">💼 ポートフォリオ管理</div>', unsafe_allow_html=True)

    tabs = st.tabs(["📊 損益", "➕ 新規建玉", "🤖 AI分析", "📜 決済履歴"])

    with tabs[0]:
        if st.session_state["portfolio_dirty"]:
            st.session_state["portfolio_summary"] = get_portfolio_summary(usd_jpy)
            st.session_state["portfolio_dirty"] = False

        summary = st.session_state["portfolio_summary"]
        if not summary or not summary.get("positions"):
            st.info("ポジションがありません。「新規建玉」タブから追加してください。")
        else:
            t = summary["total"]
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("💰 評価損益", f"¥{t.get('pnl_jpy', 0):+,}", f"{t.get('pnl_pct', 0):+.2f}%")
            k2.metric("📦 ポジション数", t.get("count", 0))
            k3.metric("⚡ エクスポージャー", f"{t.get('exposure', 0):.1f}%")
            k4.metric("💵 余剰資金", f"¥{t.get('cash_jpy', 0):+,}")

            st.markdown('<div class="section-header">📋 ポジション一覧</div>', unsafe_allow_html=True)
            for pos in sorted(summary["positions"], key=lambda x: x.get("pnl_pct", 0), reverse=True):
                if pos.get("error"):
                    continue
                pnl_pct = pos.get("pnl_pct", 0)
                card_cls = "urgent" if pnl_pct <= -8 else ("caution" if pnl_pct <= -4 else ("profit" if pnl_pct >= 10 else ""))
                ex = pos.get("exit", {})
                pnl_cls = "pnl-neg" if pnl_pct < 0 else "pnl-pos"

                st.markdown(f"""
<div class="pos-card {card_cls}">
  <b>{pos['status']} {pos['ticker']}</b> — {pos['shares']}株 @ ${pos['avg_cost']:.2f}<br>
  現在値: ${pos['current_price']:.2f}　比重: {pos.get('pw', 0):.1f}%<br>
  <span class="{pnl_cls}">{pnl_pct:+.2f}%　¥{pos.get('pnl_jpy', 0):+}</span>
  <div class="exit-info">
    Stop: ${ex.get('eff_stop', '—')}　|　Target: ${ex.get('eff_tgt', '—')}　|　R: {ex.get('cur_r', 0):.2f}
    {f"　|　Trail: ${ex['trail']:.2f}" if ex.get('trail') else ""}
  </div>
</div>""", unsafe_allow_html=True)

                c1, c2 = st.columns(2)
                if c1.button(f"🔍 診断 {pos['ticker']}", key=f"diag_{pos['ticker']}"):
                    st.session_state["target_ticker"] = pos["ticker"]
                    st.session_state["trigger_analysis"] = True
                    st.session_state["mode"] = "🔍 リアルタイム"
                    st.rerun()
                if c2.button(f"✅ 決済 {pos['ticker']}", key=f"close_{pos['ticker']}"):
                    close_position(pos["ticker"], sell_price=pos.get("current_price"))
                    st.session_state["portfolio_dirty"] = True
                    st.rerun()

    with tabs[1]:
        st.markdown('<div class="section-header">➕ 新規建玉</div>', unsafe_allow_html=True)
        with st.form("add_position_form"):
            f1, f2 = st.columns(2)
            new_ticker = f1.text_input("ティッカー", placeholder="NVDA").upper().strip()
            new_shares = f2.number_input("株数", min_value=1, value=10, step=1)
            f3, f4 = st.columns(2)
            new_cost = f3.number_input("平均取得単価 ($)", min_value=0.01, value=100.0, step=0.01)
            new_stop = f4.number_input("損切りライン ($)", min_value=0.0, value=0.0, step=0.01)
            f5, f6 = st.columns(2)
            new_target = f5.number_input("利確目標 ($)", min_value=0.0, value=0.0, step=0.01)
            new_memo = f6.text_input("メモ", placeholder="VCP breakout")
            if st.form_submit_button("✅ 追加", type="primary", use_container_width=True):
                if new_ticker and new_shares > 0 and new_cost > 0:
                    upsert_position(new_ticker, new_shares, new_cost, new_memo, new_target, new_stop)
                    st.session_state["portfolio_dirty"] = True
                    st.success(f"{new_ticker} {new_shares}株 @ ${new_cost:.2f} を追加しました")
                    st.rerun()

    with tabs[2]:
        st.markdown('<div class="section-header">🤖 ポートフォリオAI分析</div>', unsafe_allow_html=True)
        if st.button("🚀 AI分析開始", type="primary", use_container_width=True):
            summary = get_portfolio_summary(usd_jpy)
            if not summary.get("positions"):
                st.warning("ポジションがありません。")
            else:
                positions_text = []
                for p in summary["positions"]:
                    if p.get("error"):
                        continue
                    ex = p.get("exit", {})
                    positions_text.append(
                        f"{p['ticker']}: {p['shares']}株 @ ${p['avg_cost']:.2f} → 現在 ${p['current_price']:.2f} "
                        f"({p['pnl_pct']:+.2f}%)  R={ex.get('cur_r', 0):.2f}"
                    )
                t = summary["total"]
                prompt = f"""プロのヘッジファンドマネージャーとして、このポートフォリオを分析せよ。
日時: {TODAY_STR}   USD/JPY: {usd_jpy:,.0f}

総資金: ¥{config.get('CAPITAL_JPY', '不明'):,}   運用中: ¥{t.get('mv_jpy', 0):,.0f}
評価損益: ¥{t.get('pnl_jpy', 0):+,.0f}  ({t.get('pnl_pct', 0):+.2f}%)
エクスポージャー: {t.get('exposure', 0):.1f}%

ポジション一覧:
{'\n'.join(positions_text)}

出力形式（Markdown）:
1. 【緊急アクション】損切り間近・利確すべき銘柄を優先順位で
2. 【リスク評価】集中リスク・セクター偏り・相関リスクを指摘
3. 【改善提案】追加・縮小・リバランスの具体案
4. 【市場環境との整合性】現在のマクロ環境に対する適合度を評価
"""

                with st.spinner("AI分析中..."):
                    ai = call_ai(prompt)
                st.markdown("---")
                st.markdown(ai.replace("$", r"\$"))
                st.markdown("---")

    with tabs[3]:
        st.markdown('<div class="section-header">📜 決済履歴</div>', unsafe_allow_html=True)
        summary = get_portfolio_summary(usd_jpy)
        closed = summary.get("closed", [])
        if not closed:
            st.info("決済履歴がありません。")
        else:
            cs = summary.get("closed_stats", {})
            c1, c2, c3 = st.columns(3)
            c1.metric("🔢 決済数", cs.get("count", 0))
            c2.metric("💰 確定損益", f"¥{cs.get('pnl_jpy', 0):+,.0f}")
            c3.metric("🏆 勝率", f"{cs.get('win_rate', 0):.1f}%")

            df_closed = pd.DataFrame(closed[::-1])
            show_cols = [c for c in ["closed_at", "ticker", "shares", "avg_cost", "sell_price", "pnl_usd", "pnl_pct", "memo"] if c in df_closed.columns]
            st.dataframe(df_closed[show_cols], use_container_width=True, height=350)