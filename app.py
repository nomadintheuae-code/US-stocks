import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import core_fmp as fmp

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. 銘柄リスト & 設定 (旧 config.py を統合)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

NASDAQ100 = ["AAPL","MSFT","NVDA","AMZN","META","GOOGL","GOOG","TSLA","AVGO","COST","NFLX","TMUS","AMD","PEP","LIN","CSCO","ADBE","INTU","TXN","QCOM","AMAT","ISRG","BKNG","HON","VRTX","PANW","ADP","MU","SBUX","GILD","LRCX","MRVL","REGN","KLAC","MDLZ","SNPS","CDNS","ADI","MELI","CRWD","CEG","CTAS","ORLY","CSX","ASML","FTNT","MAR","PCAR","KDP","DASH","MNST","WDAY","FAST","ROST","PAYX","DXCM","AEP","EA","CTSH","GEHC","IDXX","ODFL","LULU","XEL","BKR","ON","KHC","EXC","VRSK","FANG","BIIB","TTWO","GFS","ARM","TTD","ANSS","DLTR","WBD","NXPI","ROP","CPRT","CSGP","CHTR","ILMN","MDB","ZS","TEAM","DDOG","NET","ZM","OKTA","DOCU","RIVN","LCID","SMCI","MSTR","PLTR","APP","SIRI","PARA"]
DOW30 = ["AAPL","AMGN","AXP","BA","CAT","CRM","CSCO","CVX","DIS","DOW","GS","HD","HON","IBM","INTC","JNJ","JPM","KO","MCD","MMM","MRK","MSFT","NKE","PG","SHW","TRV","UNH","V","VZ","WMT"]
CORE_WATCH = ["NVDA","AMD","TSM","SMCI","ARM","PLTR","SNOW","CRWD","PANW","NET","COIN","MSTR","HOOD","UBER","TSLA","LLY","NVO"]

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. UI・ランキングロジック
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

st.set_page_config(page_title="Sentinel-v3", page_icon="📈", layout="wide")

@st.cache_data(ttl=3600)
def fetch_ranking_data(list_name):
    target = NASDAQ100 if list_name == "NASDAQ 100" else DOW30 if list_name == "Dow 30" else CORE_WATCH
    all_q = []
    # 50件ずつバッチ取得
    for i in range(0, len(target), 50):
        batch = target[i:i+50]
        res = fmp._get(f"quote/{','.join(batch)}")
        if res: all_q.extend(res)
    
    df = pd.DataFrame([{
        "Symbol": r.get("symbol"),
        "Name": r.get("name"),
        "Price": r.get("price"),
        "Change%": r.get("changesPercentage"),
        "MktCap($B)": round(r.get("marketCap", 0)/1e9, 2),
        "Volume": r.get("volume")
    } for r in all_q])
    return df

def main():
    st.title("🛡️ Sentinel-v3 Market Intelligence")
    
    # 抽出条件
    list_type = st.sidebar.selectbox("Market Universe", ["NASDAQ 100", "Dow 30", "Core Watch"])
    sort_key = st.sidebar.radio("Sort By", ["MktCap($B)", "Change%"])
    
    df = fetch_ranking_data(list_type)
    if df.empty:
        st.error("Data Fetch Failed.")
        return

    top_50 = df.sort_values(sort_key, ascending=False).head(50)

    c1, c2 = st.columns([1.5, 1])

    with c1:
        st.subheader(f"{list_type} Top Ranking")
        selection = st.dataframe(
            top_50, 
            use_container_width=True, 
            height=600, 
            selection_mode="single_row", 
            on_select="rerun"
        )

    with c2:
        # 選択された銘柄の特定
        if selection.selection.rows:
            ticker = top_50.iloc[selection.selection.rows[0]]["Symbol"]
        else:
            ticker = top_50.iloc[0]["Symbol"]
            st.info("💡 Select a row to see deep analysis.")

        # 詳細取得
        with st.spinner(f"Analyzing {ticker}..."):
            q = fmp.get_quote(ticker)
            f = fmp.get_fundamentals(ticker)
            a = fmp.get_analyst_consensus(ticker)
            news = fmp.get_news(ticker, limit=3)

        st.subheader(f"📊 {ticker} Deep Dive")
        if q:
            st.metric("Price", f"${q['price']}", f"{q['changesPercentage']}%")

        if f:
            st.write("---")
            col_a, col_b = st.columns(2)
            col_a.metric("ROE", f"{f['roe']}%")
            col_b.metric("PE", f"{f['pe']}")
            col_c, col_d = st.columns(2)
            col_c.metric("Rev Growth", f"{f['rev_growth']}%")
            col_d.metric("Market Cap", f"${f['market_cap_b']}B")

        if a:
            st.write("---")
            st.markdown(f"**Target Price: `${a['target']}`** (Upside: `{a['upside']}%`)")
            st.caption(f"Based on {a['count']} analyst reports.")

        # チャート
        hist = fmp.get_historical_data(ticker, days=120)
        if hist is not None:
            fig = go.Figure(data=[go.Candlestick(x=hist.index, open=hist['Open'], high=hist['High'], low=hist['Low'], close=hist['Close'])])
            fig.update_layout(template="plotly_dark", height=300, margin=dict(l=0,r=0,b=0,t=0), xaxis_rangeslider_visible=False)
            st.plotly_chart(fig, use_container_width=True)

        # ニュース
        if news:
            st.write("---")
            st.markdown("**Latest News**")
            for n in news:
                st.markdown(f"- [{n['title']}]({n['url']})")
                st.caption(f"{n['source']} | {n['published_at']}")

if __name__ == "__main__":
    main()