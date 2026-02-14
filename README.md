# SENTINEL PRO - US Stock Scanner
<img width="1843" height="914" alt="image" src="https://github.com/user-attachments/assets/1c2d57de-086e-40cb-a187-bb018c95121f" />
<img width="1745" height="833" alt="image" src="https://github.com/user-attachments/assets/064513ee-24b6-4f7c-90b6-a30e7493d451" />

**Personal US stock scanner** focused on high-probability setups using Relative Strength (RS) ratings and Volatility Contraction Patterns (VCP).  
Built for daily automated scanning, interactive visualization, and portfolio tracking — powered by Streamlit for a clean dashboard.

**Note**: This is the **no-AI version** (DeepSeek/LLM features disabled for zero ongoing costs). The full private version with AI depth analysis is for personal use only.

## Live Demo (Public No-AI Version)

👉 Try it here: [https://us-stockssc.streamlit.app](https://us-stockssc.streamlit.app)

(Hosted on Streamlit Community Cloud – data via yfinance, no login required)

## Key Features

- **Daily Batch Scan** (`sentinel.py`)  
  Scans a curated watchlist of US stocks for:  
  - High RS Rating (relative strength vs market)  
  - VCP setups (volatility contraction + volume dry-up)  
  - Strict filters: sector diversification, position sizing rules  
  → Outputs classified signals (e.g., ACTION / WAIT / EXTENDED)  
  → Saves JSON results (`./results/YYYY-MM-DD.json`)  
  → Optional LINE Notify push (configurable)

- **Interactive Dashboard** (`app.py` – Streamlit)  
  - View daily scan results with sortable/filterable tables  
  - Single-stock deep dive: charts (candlestick, volume, indicators), fundamentals, news headlines  
  - Portfolio tracker: entries, average cost, P&L, R-multiples, ATR-based stops/targets  
  - Real-time price updates via yfinance  
  - **Multilingual UI** (Japanese/English) – switch via sidebar

- **Modular Notification** (`engines/notify.py`)  
  LINE integration ready (add your token in config/secrets)

## Tech Stack

- Python 3.10+
- Data: yfinance
- Analysis: pandas, numpy
- UI & Charts: Streamlit, Plotly
- Notifications: LINE Notify

## Installation

1. Clone the repo  
   ```bash
   git clone https://github.com/EMMA019/US-stocks.git
   cd US-stocks
(Recommended) Virtual environment

bash
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate
Install dependencies

bash
pip install -r requirements.txt
Configuration
Create .streamlit/secrets.toml (for local dev) or set in Streamlit Cloud settings:

toml
# .streamlit/secrets.toml
LINE_NOTIFY_TOKEN = "your-line-notify-access-token"
DEEPSEEK_API_KEY = "your-deepseek-api-key"   # optional, for AI diagnosis
Or via environment variables:

bash
export LINE_NOTIFY_TOKEN="..."
export DEEPSEEK_API_KEY="..."
Usage
Run daily scan (batch mode)

bash
python sentinel.py
Launch the dashboard

bash
streamlit run app.py
→ Open http://localhost:8501

Project Status
Actively developed (recent commits: app.py, sentinel.py, engines/notify.py, GitHub Actions workflow for daily scans)

No external API costs (yfinance is free; LINE Notify free tier sufficient)

Recent improvements:

Unified analysis logic between batch scan and real-time dashboard

Added multilingual support (Japanese/English)

Planned:

More scan filters & presets

Export CSV/Excel from dashboard

Enhanced portfolio persistence (JSON or SQLite)

Mobile-friendly layout tweaks

License
MIT License
Copyright © 2026 Emma Saka

See LICENSE for details.

Disclaimer
This is an educational/personal tool for scanning and tracking US stocks.
It does not provide financial advice.
All trading involves risk of loss — use at your own discretion.
Data sourced from yfinance (subject to its terms and potential delays/limits).

Feedback, issues, or forks welcome! 🛡️
