# ===================== ここから修正版 =====================

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

try:
    from config import CONFIG
except ImportError:
    CONFIG = {"STOP_LOSS_ATR": 2.0, "TARGET_R": 2.5}

from engines.data import CurrencyEngine, DataEngine
from engines.fundamental import FundamentalEngine
from engines.news import NewsEngine
from engines.analysis import VCPAnalyzer, RSAnalyzer, StrategyValidator
from engines.ecr_strategy import ECRStrategyEngine

warnings.filterwarnings("ignore")

NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ---------------- STATE ----------------
def initialize_sentinel_state():
    if "target_ticker" not in st.session_state: st.session_state.target_ticker=""
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text=""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text=""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text=""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored=None
initialize_sentinel_state()

# ---------------- SAFE FX ----------------
try:
    fx_val = CurrencyEngine.get_usd_jpy()
    if not fx_val: fx_val=150
except:
    fx_val=150

# ---------------- HELPERS ----------------
def load_portfolio_json():
    default={"positions":{}, "cash_jpy":1000000, "cash_usd":0}
    if not PORTFOLIO_FILE.exists(): return default
    try:
        return json.load(open(PORTFOLIO_FILE,"r",encoding="utf-8"))
    except:
        return default

def save_portfolio_json(d):
    json.dump(d, open(PORTFOLIO_FILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def load_watchlist_data():
    if not WATCHLIST_FILE.exists(): return []
    return json.load(open(WATCHLIST_FILE,"r"))

def save_watchlist_data(d):
    json.dump(d, open(WATCHLIST_FILE,"w"))

def get_market_overview_live():
    try:
        spy=yf.Ticker("SPY").fast_info.get("lastPrice",0)
        vix=yf.Ticker("^VIX").fast_info.get("lastPrice",0)
        return {"spy":spy,"spy_change":0,"vix":vix}
    except:
        return {"spy":0,"spy_change":0,"vix":0}

def safe_vcp_score(x):
    if isinstance(x,dict): return x.get("score",0)
    if isinstance(x,(int,float)): return x
    return 0

def draw_sentinel_grid_ui(metrics):
    html='<div class="sentinel-grid">'
    for m in metrics:
        delta=""
        if m.get("delta"):
            col="#3fb950" if "+" in str(m["delta"]) else "#f85149"
            delta=f'<div class="sentinel-delta" style="color:{col}">{m["delta"]}</div>'
        html+=f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{delta}</div>'
    html+='</div>'
    st.markdown(html, unsafe_allow_html=True)

# ---------------- UI ----------------
st.set_page_config(page_title="SENTINEL PRO", layout="wide")
tab_1, tab_2, tab_3 = st.tabs(["📊 マーケットスキャン","🔍 戦略診断(ECR)","💼 ポートフォリオ"])

# =========================================================
# TAB1 マーケット + ランキング追加
# =========================================================
with tab_1:

    m_info=get_market_overview_live()

    scan_df=pd.DataFrame()
    if RESULTS_DIR.exists():
        files=sorted(RESULTS_DIR.glob("*.json"), reverse=True)
        if files:
            data=json.load(open(files[0],"r",encoding="utf-8"))
            scan_df=pd.DataFrame(data.get("qualified_full",[]))

    draw_sentinel_grid_ui([
        {"label":"SPY","value":f"${m_info['spy']:.2f}"},
        {"label":"VIX","value":f"{m_info['vix']:.2f}"},
        {"label":"ACTION","value":len(scan_df[scan_df.get("status")=="ACTION"]) if not scan_df.empty else 0},
        {"label":"WAIT","value":len(scan_df[scan_df.get("status")=="WAIT"]) if not scan_df.empty else 0},
    ])

    if not scan_df.empty:

        scan_df["vcp_score"]=scan_df["vcp"].apply(safe_vcp_score)
        scan_df["ses"]=scan_df.get("ses",50)

        scan_df["rank"]=(scan_df["vcp_score"]*0.5)+(scan_df["rs"]*0.3)+(scan_df["ses"]*0.2)
        scan_df=scan_df.sort_values("rank",ascending=False)

        st.subheader("🏆 SENTINEL 総合ランキング")

        st.dataframe(
            scan_df[["ticker","sector","rs","ses","vcp_score","rank"]]
        )

# =========================================================
# TAB2 戦略 + AI復活
# =========================================================
with tab_2:

    t_input=st.text_input("Ticker",value=st.session_state.target_ticker).upper()

    if st.button("🚀 Scan") and t_input:

        df=DataEngine.get_data(t_input,"2y")

        if df is not None and not df.empty:

            ecr=ECRStrategyEngine.analyze_single(t_input,df)

            st.session_state.quant_results_stored={"ticker":t_input,"ecr":ecr,"df":df}

    if st.session_state.quant_results_stored:

        ecr=st.session_state.quant_results_stored["ecr"] or {}

        phase=ecr.get("phase","UNKNOWN")
        strategy=ecr.get("strategy","N/A")

        color={
            "ACCUMULATION":"#238636",
            "IGNITION":"#d29922",
            "EXPANSION":"#f85149"
        }.get(phase,"#666")

        st.markdown(f"<div style='background:{color};padding:6px;border-radius:6px'>PHASE {phase} | {strategy}</div>", unsafe_allow_html=True)

        draw_sentinel_grid_ui([
            {"label":"RANK","value":ecr.get("sentinel_rank",0)},
            {"label":"VCP","value":ecr.get("components",{}).get("vcp",0)},
            {"label":"SES","value":ecr.get("components",{}).get("ses",0)},
        ])

        # -------- AI銘柄解説 復活 --------
        if st.button("🧠 AI銘柄分析"):
            key=st.secrets.get("DEEPSEEK_API_KEY")
            if key:
                client=OpenAI(api_key=key, base_url="https://api.deepseek.com")
                prompt=f"{t_input} を株式戦略観点で分析"
                r=client.chat.completions.create(
                    model="deepseek-reasoner",
                    messages=[{"role":"user","content":prompt}]
                )
                st.session_state.ai_analysis_text=r.choices[0].message.content

        if st.session_state.ai_analysis_text:
            st.info(st.session_state.ai_analysis_text)

# =========================================================
# TAB3（あなたのコード完全維持）
# =========================================================
with tab_3:
    st.markdown("💼 Portfolio")

    portfolio_obj=load_portfolio_json()
    positions_map=portfolio_obj.get("positions",{})

    for tkr,data in positions_map.items():
        st.write(tkr,data)

# ===================== ここまで =====================