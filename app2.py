# ================================
# SENTINEL PRO APP2 - FIXED FULL
# ================================

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
# 1. エンジン
# ==============================================================================
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

# ==============================================================================
# 2. PATH
# ==============================================================================
NOW = datetime.datetime.now()
TODAY_STR = NOW.strftime("%Y-%m-%d")
RESULTS_DIR = Path("./results")
WATCHLIST_FILE = Path("watchlist.json")
PORTFOLIO_FILE = Path("portfolio.json")

# ==============================================================================
# 3. STATE
# ==============================================================================
def initialize_sentinel_state():
    if "target_ticker" not in st.session_state: st.session_state.target_ticker=""
    if "ai_analysis_text" not in st.session_state: st.session_state.ai_analysis_text=""
    if "ai_market_text" not in st.session_state: st.session_state.ai_market_text=""
    if "ai_port_text" not in st.session_state: st.session_state.ai_port_text=""
    if "quant_results_stored" not in st.session_state: st.session_state.quant_results_stored=None
initialize_sentinel_state()

# ==============================================================================
# JSON IO
# ==============================================================================
def load_portfolio_json():
    default={"positions":{}, "cash_jpy":1000000,"cash_usd":0}
    if not PORTFOLIO_FILE.exists(): return default
    try:
        with open(PORTFOLIO_FILE,"r",encoding="utf-8") as f:
            d=json.load(f)
            d.setdefault("cash_jpy",1000000)
            d.setdefault("cash_usd",0)
            return d
    except: return default

def save_portfolio_json(d):
    with open(PORTFOLIO_FILE,"w",encoding="utf-8") as f:
        json.dump(d,f,ensure_ascii=False,indent=2)

def load_watchlist_data():
    if not WATCHLIST_FILE.exists(): return []
    try:
        with open(WATCHLIST_FILE,"r") as f:return json.load(f)
    except:return[]

def save_watchlist_data(d):
    with open(WATCHLIST_FILE,"w") as f: json.dump(d,f)

# ==============================================================================
# MARKET
# ==============================================================================
def get_market_overview_live():
    try:
        spy=yf.Ticker("SPY").history(period="3d")
        vix=yf.Ticker("^VIX").history(period="1d")
        if len(spy)>=2:
            spy_p=spy["Close"].iloc[-1]
            spy_chg=(spy_p/spy["Close"].iloc[-2]-1)*100
        else:
            spy_p=0; spy_chg=0
        vix_p=vix["Close"].iloc[-1] if not vix.empty else 0
        return {"spy":spy_p,"spy_change":spy_chg,"vix":vix_p}
    except:
        return {"spy":0,"spy_change":0,"vix":0}

# ==============================================================================
# UI GRID
# ==============================================================================
def draw_sentinel_grid_ui(metrics):
    html='<div class="sentinel-grid">'
    for m in metrics:
        delta=""
        if "delta" in m and m["delta"]:
            pos="+" in str(m["delta"]) or (isinstance(m["delta"],(int,float)) and m["delta"]>0)
            col="#3fb950" if pos else "#f85149"
            delta=f'<div class="sentinel-delta" style="color:{col}">{m["delta"]}</div>'
        html+=f'<div class="sentinel-card"><div class="sentinel-label">{m["label"]}</div><div class="sentinel-value">{m["value"]}</div>{delta}</div>'
    html+='</div>'
    st.markdown(html,unsafe_allow_html=True)

# ==============================================================================
# STYLE
# ==============================================================================
st.set_page_config(page_title="SENTINEL PRO",page_icon="🛡️",layout="wide",initial_sidebar_state="collapsed")

# ==============================================================================
# SIDEBAR
# ==============================================================================
with st.sidebar:
    st.markdown("### 🛡️ SENTINEL ウォッチリスト")
    wl=load_watchlist_data()
    for t in wl:
        c1,c2=st.columns([4,1])
        if c1.button(t,use_container_width=True):
            st.session_state.target_ticker=t; st.rerun()
        if c2.button("×",key=f"rm_{t}"):
            wl.remove(t); save_watchlist_data(wl); st.rerun()

fx_val=CurrencyEngine.get_usd_jpy()
tab_1,tab_2,tab_3=st.tabs(["📊 マーケットスキャン","🔍 戦略診断(ECR)","💼 ポートフォリオ"])

# ==============================================================================
# TAB2 ONLY (ECR)
# ==============================================================================
with tab_2:

    st.markdown("### 🔍 ECR戦略スキャン")

    t_input=st.text_input("ティッカー",value=st.session_state.target_ticker).upper().strip()

    col_a,col_b=st.columns(2)

    if col_a.button("🚀 戦略スキャン実行",type="primary",use_container_width=True) and t_input:

        with st.spinner("Analyzing..."):

            df_full=DataEngine.get_data(t_input,"2y")

            if df_full is not None and not df_full.empty:

                v_res=VCPAnalyzer.calculate(df_full)
                rs_v=RSAnalyzer.get_raw_score(df_full)
                pf_v=StrategyValidator.run(df_full)
                p_c=DataEngine.get_current_price(t_input)

                # ===== FIXED =====
                ecr_res=ECRStrategyEngine.analyze(df_full,t_input)

                st.session_state.quant_results_stored={
                    "vcp":v_res,
                    "rs":rs_v,
                    "pf":pf_v,
                    "price":p_c,
                    "ticker":t_input,
                    "ecr":ecr_res
                }

            else:
                st.error("データ取得不可")

    if st.session_state.quant_results_stored and st.session_state.quant_results_stored["ticker"]==t_input:

        res_q=st.session_state.quant_results_stored
        ecr=res_q["ecr"]

        # ===== FIXED COMPONENT KEYS =====
        comp=ecr.get("components",{})

        draw_sentinel_grid_ui([
            {"label":"🛡️ SENTINEL RANK","value":f"{ecr.get('sentinel_rank',0)}/100"},
            {"label":"⚡ ENERGY (VCP)","value":f"{comp.get('energy_vcp',0)}/100"},
            {"label":"💎 QUALITY (SES)","value":f"{comp.get('quality_ses',0)}/100"},
            {"label":"📈 PROFIT FACTOR","value":f"x{res_q['pf']:.2f}"}
        ])

        # ===== SAFE CHART =====
        df_plot=DataEngine.get_data(t_input,"2y")
        if df_plot is not None and not df_plot.empty:

            df_recent=df_plot.tail(180)

            fig=go.Figure(data=[go.Candlestick(
                x=df_recent.index,
                open=df_recent["Open"],
                high=df_recent["High"],
                low=df_recent["Low"],
                close=df_recent["Close"]
            )])

            fig.update_layout(template="plotly_dark",height=420,xaxis_rangeslider_visible=False)
            st.plotly_chart(fig,use_container_width=True)

st.caption("🛡️ SENTINEL PRO SYSTEM | FIXED BUILD")