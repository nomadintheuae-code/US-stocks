# ============================================================
# 🛡 SENTINEL PRO - DISPLAY ONLY FRONTEND
# Backend JSON完全一致表示版
# ============================================================

import streamlit as st
import json
import os
import pandas as pd
import plotly.graph_objects as go
from engines.data import DataEngine

st.set_page_config(page_title="SENTINEL PRO", layout="wide")

st.title("🛡 SENTINEL PRO")

# ============================================================
# 📂 最新JSON自動取得
# ============================================================

@st.cache_data
def load_latest_snapshot():

    results_dir = "results"

    if not os.path.exists(results_dir):
        return None, None

    files = [f for f in os.listdir(results_dir) if f.endswith(".json")]

    if not files:
        return None, None

    files.sort(reverse=True)  # YYYY-MM-DD.json 前提

    latest_file = files[0]
    full_path = os.path.join(results_dir, latest_file)

    with open(full_path, "r") as f:
        data = json.load(f)

    return data, latest_file


data, filename = load_latest_snapshot()

if data is None:
    st.error("No result JSON found in /results directory.")
    st.stop()

# ============================================================
# 📊 メタ情報表示
# ============================================================

st.subheader("📊 Scan Summary")

col1, col2, col3, col4 = st.columns(4)

col1.metric("Date", data.get("date", "-"))
col2.metric("Scan Count", data.get("scan_count", 0))
col3.metric("Qualified", data.get("qualified_count", 0))
col4.metric("Selected", data.get("selected_count", 0))

st.caption(f"Runtime: {data.get('runtime', '-')}")
st.caption(f"USD/JPY: {data.get('usd_jpy', '-')}")

st.divider()

# ============================================================
# 📡 Selected銘柄一覧
# ============================================================

selected = data.get("selected", [])

if not selected:
    st.warning("No selected stocks.")
    st.stop()

df_table = pd.DataFrame([
    {
        "Ticker": s["ticker"],
        "Status": s["status"],
        "Price": s["price"],
        "Entry": s["entry"],
        "Stop": s["stop"],
        "Target": s["target"],
        "VCP": s["vcp"]["score"],
        "RS": s["rs"],
        "PF": s["pf"],
        "Sector": s["sector"]
    }
    for s in selected
])

st.subheader("📡 Selected Stocks")
st.dataframe(df_table, use_container_width=True)

st.divider()

# ============================================================
# 🔎 個別詳細表示
# ============================================================

st.subheader("🔎 Stock Detail")

ticker_list = [s["ticker"] for s in selected]
ticker = st.selectbox("Select Ticker", ticker_list)

stock = next(s for s in selected if s["ticker"] == ticker)

col1, col2, col3, col4 = st.columns(4)

col1.metric("VCP", stock["vcp"]["score"])
col2.metric("RS", stock["rs"])
col3.metric("PF", stock["pf"])
col4.metric("Status", stock["status"])

st.write("### Price Levels")
col5, col6, col7 = st.columns(3)
col5.metric("Entry", stock["entry"])
col6.metric("Stop", stock["stop"])
col7.metric("Target", stock["target"])

st.write("### Analyst Data")
col8, col9, col10 = st.columns(3)
col8.metric("Target", stock["analyst_target"])
col9.metric("Upside %", stock["analyst_upside"])
col10.metric("Recommendation", stock["recommendation"])

st.write("### Short / Ownership")
col11, col12, col13 = st.columns(3)
col11.metric("Short Ratio", stock["short_ratio"])
col12.metric("Short %", stock["short_pct"])
col13.metric("Institution %", stock["institution_pct"])

# ============================================================
# 📰 News表示
# ============================================================

st.write("### News")

for article in stock.get("news", {}).get("articles", []):
    st.markdown(f"- [{article['title']}]({article['url']})")

# ============================================================
# 📈 チャート（価格のみ取得）
# ============================================================

st.divider()
st.subheader("📈 Price Chart")

df_price = DataEngine.get_data(ticker, period="1y")

if df_price is not None and not df_price.empty:

    fig = go.Figure()

    fig.add_trace(go.Candlestick(
        x=df_price.index,
        open=df_price["Open"],
        high=df_price["High"],
        low=df_price["Low"],
        close=df_price["Close"],
        name="Price"
    ))

    fig.update_layout(
        height=600,
        xaxis_rangeslider_visible=False
    )

    st.plotly_chart(fig, use_container_width=True)

# ============================================================
# 🧾 RAW JSON（確認用）
# ============================================================

with st.expander("Raw JSON"):
    st.json(stock)