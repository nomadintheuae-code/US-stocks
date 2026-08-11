# SENTINEL PRO - US Stock Scanner

<img width="1843" height="914" alt="image" src="https://github.com/user-attachments/assets/1c2d57de-086e-40cb-a187-bb018c95121f" />
<img width="1745" height="833" alt="image" src="https://github.com/user-attachments/assets/064513ee-24b6-4f7c-90b6-a30e7493d451" />

**Personal US stock scanner** focused on high-probability setups using Relative Strength (RS) ratings and Volatility Contraction Patterns (VCP).

Built for daily automated scanning, interactive visualization, and portfolio tracking — powered by Streamlit for a clean dashboard.

**Note**: This is the **no-AI version** (DeepSeek/LLM features disabled for zero ongoing costs). The full private version with AI depth analysis is for personal use only.

## Live Demo (Public No-AI Version)

👉 Try it here: [https://us-stockssc.streamlit.app](https://us-stockssc.streamlit.app)

(Hosted on Streamlit Community Cloud – data via yfinance, no login required)

> This repository is a maintained fork of the original [EMMA019/US-stocks](https://github.com/EMMA019/US-stocks) project. The demo link above is owned by the upstream project and is independent of this fork.

## Key Features

- **Daily Batch Scan** (`sentinel.py`)
  Scans a curated watchlist of US stocks for:
  - High RS Rating (relative strength vs market)
  - VCP setups (volatility contraction + volume dry-up)
  - SES efficiency scoring and ECR rank composition
  - Strict filters: sector diversification, position sizing rules
  → Outputs classified signals (e.g., ACTION / WAIT / EXTENDED)
  → Saves JSON results (`./results/YYYY-MM-DD.json`)
  → Optional LINE Notify push (configurable)

- **Interactive Dashboard** (`app.py` – Streamlit, FMP data)
  - View daily scan results with sortable/filterable tables
  - Single-stock deep dive: charts (candlestick, volume, indicators), fundamentals, news headlines
  - Portfolio tracker: entries, average cost, P&L, R-multiples, ATR-based stops/targets
  - Real-time price updates
  - **Multilingual UI** (Japanese/English) – switch via sidebar

- **Alternate Dashboard** (`app2.py` – yfinance / ECR strategy)
  - yfinance-backed views, unaffected by FMP plan limits

- **Modular Notification** (`engines/notify.py`)
  LINE integration ready (add your token in `.env`)

## Repository Structure

```
.
├── sentinel.py          # Batch scanner entry point → results/YYYY-MM-DD.json
├── app.py               # Streamlit dashboard v1 (FMP-based)
├── app2.py              # Streamlit dashboard v2 (yfinance / ECR)
├── core_fmp.py          # FMP client (quote, fundamentals, analyst, news)
├── config.py            # Backward-compatible config wrapper (CONFIG dict, TICKERS)
├── config.yaml          # Single source of truth for all tunable parameters
├── sentinel/            # Core modules (config loader, scanner logic)
│   ├── config.py        #   Pydantic Config class (loads root config.yaml)
│   ├── scanner.py       #   Batch scanning orchestration
│   └── __init__.py
├── engines/             # Feature modules
│   ├── data.py          #   Market data layer
│   ├── analysis.py      #   VCPAnalyzer, RSAnalyzer, StrategyValidator
│   ├── fundamental.py   #   Fundamental scoring
│   ├── news.py          #   RSS/Yahoo news
│   ├── notify.py        #   LINE Notify
│   ├── ecr_strategy.py  #   ECR strategy engine
│   └── sentinel_efficiency.py  # SES scoring
├── tests/               # Pytest suite (no network)
├── results/             # Scan output (gitignored)
├── requirements.txt     # Pinned runtime dependencies
├── requirements-dev.txt # Runtime deps + pytest
└── pyproject.toml       # Project metadata + pytest config
```

## Tech Stack

- Python 3.10+ (developed on 3.14)
- Data: Financial Modeling Prep (FMP) API + yfinance
- Analysis: pandas, numpy, scipy
- UI & Charts: Streamlit, Plotly
- Notifications: LINE Notify

## Installation

```bash
git clone git@github.com:nomadintheuae-code/US-stocks.git
cd US-stocks

# (Recommended) Virtual environment
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
# Dev extras (pytest)
pip install -r requirements-dev.txt
```

## Configuration

All tunable parameters live in **`config.yaml`** (capital, scan filters, exit strategy, VCP/RS/backtest/SES/ECR weights, cache, performance, data, notification, UI).

Secrets and environment overrides go in **`.env`** (git-ignored). Copy `.env.sample` to `.env` and fill in:

```bash
cp .env.sample .env
```

| Variable | Required | Purpose |
| --- | --- | --- |
| `FMP_API_KEY` | Yes* | FMP data for `app.py` (quote, fundamentals, analyst) |
| `LINE_CHANNEL_ACCESS_TOKEN` / `LINE_USER_ID` | No | LINE Notify push |
| `DEEPSEEK_API_KEY` | No | AI diagnosis (disabled in no-AI build) |
| `CAPITAL_JPY`, `MAX_POSITIONS`, `ACCOUNT_RISK_PCT` | No | Override config.yaml capital settings |

\* `sentinel.py` / `app2.py` run on yfinance and do not require an FMP key. `app.py` needs the key for FMP-backed views.

Every `config.yaml` scalar can be overridden with a matching `UPPER_SNAKE_CASE` environment variable (e.g. `CAPITAL_JPY`, `MIN_RS_RATING`, `STOP_LOSS_ATR`).

## Usage

**Run daily scan (batch mode):**

```bash
python sentinel.py
```

**Launch the dashboard:**

```bash
streamlit run app.py        # FMP-backed v1
streamlit run app2.py       # yfinance/ECR v2
```

Open http://localhost:8501

**Run the tests:**

```bash
pytest                      # or: python -m pytest
```

## Known Limitations

- **FMP news returns HTTP 402** on the current FMP plan. `app.py` handles this gracefully and shows a notice instead of crashing; the RSS/Yahoo news path (`engines/news.py`, used by `app2.py`) is unaffected. Upgrading the FMP plan (or using the RSS path) is required for FMP news.
- Duplicate `engines/core_fmp.py` is a legacy copy kept in sync with `core_fmp.py` for parity.
- Legacy `results/*.json` files remain tracked in git history even though the directory is now gitignored.

## Security Notes

- The FMP API key is read **only** from the environment (`.env`); it is never hardcoded in source.
- `.env`, `.streamlit/secrets.toml`, caches, and scan results are gitignored. **Never commit secrets.**
- An earlier hardcoded key was revoked, rotated, and scrubbed from git history (see `PROJECT_CONTEXT.md`).

## Project Status

Actively developed. Recent work (Phase 1): externalized configuration, security hardening, pinned dependencies, and a focused offline test suite.

Planned (Phase 2):

- More scan filters & presets
- Export CSV/Excel from dashboard
- Enhanced portfolio persistence (JSON or SQLite)
- Mobile-friendly layout tweaks

## License

MIT License — Copyright © 2026 Emma Saka

See [LICENSE](LICENSE) for details.

## Disclaimer

This is an educational/personal tool for scanning and tracking US stocks.
It does not provide financial advice.
All trading involves risk of loss — use at your own discretion.
Data sourced from FMP API and yfinance (subject to their terms and potential delays/limits).
