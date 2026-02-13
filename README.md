# SENTINEL PRO - US Stock Scanner

**Personal US stock scanner** focused on high-probability setups using Relative Strength (RS) ratings and Volatility Contraction Patterns (VCP).  
Built for daily automated scanning, interactive visualization, and portfolio tracking — powered by Streamlit for a clean dashboard.

**Note**: This is the **no-AI version** (DeepSeek/LLM features disabled for zero ongoing costs). The full private version with AI depth analysis is for personal use only.

## Live Demo (Public No-AI Version)

👉 Try it here: [

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
	2	(Recommended) Virtual environment python -m venv venv
	3	source venv/bin/activate          # Windows: venv\Scripts\activate
	4	
	5	Install dependencies pip install -r requirements.txt
	6	
Configuration
Create .streamlit/secrets.toml (for local dev) or set in Streamlit Cloud settings:
# .streamlit/secrets.toml
LINE_NOTIFY_TOKEN = "your-line-notify-access-token"
# (No AI keys needed in this version)
Or via environment variables:
export LINE_NOTIFY_TOKEN="..."
Usage
Run daily scan (batch mode)
python sentinel.py
Launch the dashboard
streamlit run app.py
→ Open http://localhost:8501
Project Status
	•	Actively developed (recent commits: app.py, sentinel.py, engines/notify.py, GitHub Actions workflow for daily scans)
	•	No external API costs (yfinance is free; LINE Notify free tier sufficient)
	•	Planned:
	◦	More scan filters & presets
	◦	Export CSV/Excel from dashboard
	◦	Enhanced portfolio persistence (JSON or SQLite)
	◦	Mobile-friendly layout tweaks
License
MIT License Copyright © 2026 Emma Saka
See LICENSE for details.
Disclaimer
This is an educational/personal tool for scanning and tracking US stocks. It does not provide financial advice. All trading involves risk of loss — use at your own discretion. Data sourced from yfinance (subject to its terms and potential delays/limits).
Feedback, issues, or forks welcome! 🛡️
### Quick Tips for Next Steps
- **Commit the README**: `git add README.md && git commit -m "Add comprehensive English README" && git push`
- **Add a screenshot**: Take one of the dashboard (scan table + chart), upload to repo as `screenshots/dashboard.png`, then add to README:
  ```markdown
  ![Dashboard Screenshot](screenshots/dashboard.png)
	•	GitHub Actions: You already have a workflow — nice! It can auto-run sentinel.py daily if set up properly.
	•	If you later want a separate no-ai branch for public sharing, just branch off main and remove any leftover AI code comments.
Let me know if you want tweaks (shorter version, more sections like “How RS/VCP Works”, badges, etc.)! 🚀
