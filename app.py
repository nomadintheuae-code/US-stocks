# ============================================================
# SENTINEL PRO - DISPLAY ONLY VERSION
# ============================================================

import streamlit as st
import json
import pandas as pd
import plotly.graph_objects as go
from engines.data import DataEngine

st.set_page_config(page_title="SENTINEL PRO", layout="wide")
st.title("🛡 SENTINEL PRO")

# ==============================
# 📥 Load Backend Output
# ==============================
@st.cache_data
def load_snapshot():
    with open("snapshot.json", "r") as f:
        return json.load(f)

data = load_snapshot()

# ==============================
# 📊 Scanner Table
# ==============================
st.subheader("📡 Market Scan Results")

df_scan = pd.DataFrame(data["results"])
df_scan = df_scan.sort_values("total_score", ascending=False)

st.dataframe(df_scan, use_container_width=True)

# ==============================
# 🔍 Individual View
# ==============================
st.subheader("🔎 Individual Detail")

ticker = st.selectbox("Select Ticker", df_scan["ticker"])

selected = next(x for x in data["results"] if x["ticker"] == ticker)

col1, col2, col3, col4 = st.columns(4)

col1.metric("VCP", selected["vcp"]["score"])
col2.metric("RS", selected["rs"]["score"])
col3.metric("PF", selected["pf"]["score"])
col4.metric("TOTAL", selected["total_score"])

# ==============================
# 📈 Chart（価格だけ取得）
# ==============================
df_price = DataEngine.get_data(ticker, period="1y")

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

# ==============================
# 📋 Breakdown
# ==============================
with st.expander("Detailed Breakdown"):
    st.json(selected)