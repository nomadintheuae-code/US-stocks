
import os

# ==============================================================================

# ⚙️ 設定ヘルパー

# ==============================================================================

def _ei(key: str, default: int) -> int:
“”“環境変数を int で取得。未設定・空文字はデフォルト値を返す。”””
v = os.getenv(key, “”).strip()
return int(v) if v else int(default)

def _ef(key: str, default: float) -> float:
“”“環境変数を float で取得。未設定・空文字はデフォルト値を返す。”””
v = os.getenv(key, “”).strip()
return float(v) if v else float(default)

# ==============================================================================

# ⚙️ CONFIG

# ==============================================================================

CONFIG = {
# — 資金・ポジション管理 —
“CAPITAL_JPY”:       _ei(“CAPITAL_JPY”, 1_000_000),   # 運用資金（円）
“MAX_POSITIONS”:     _ei(“MAX_POSITIONS”, 20),          # 最大同時保有数
“ACCOUNT_RISK_PCT”:  _ef(“ACCOUNT_RISK_PCT”, 0.015),   # 1トレードあたりリスク (1.5%)
“MAX_SAME_SECTOR”:   _ei(“MAX_SAME_SECTOR”, 2),         # セクターあたり最大銘柄数

```
# --- スキャンフィルター ---
"MIN_RS_RATING":     _ei("MIN_RS_RATING", 70),          # RS最低スコア（0-99）
"MIN_VCP_SCORE":     _ei("MIN_VCP_SCORE", 55),          # VCP最低スコア（0-100）
"MIN_PROFIT_FACTOR": _ef("MIN_PROFIT_FACTOR", 1.1),     # バックテスト最低PF

# --- 出口戦略 ---
"STOP_LOSS_ATR":     _ef("STOP_LOSS_ATR", 2.0),         # 損切り = ATR × この値
"TARGET_R_MULTIPLE": _ef("TARGET_R_MULTIPLE", 2.5),     # 利確 = リスク × この値

# --- システム ---
"CACHE_EXPIRY":       12 * 3600,   # 価格キャッシュ有効期限（秒）
"FUND_CACHE_EXPIRY":  24 * 3600,   # ファンダメンタルキャッシュ（秒）
"NEWS_CACHE_EXPIRY":   1 * 3600,   # ニュースキャッシュ（秒）
"NEWS_FETCH_TIMEOUT":  6,           # 本文fetchタイムアウト（秒）
"NEWS_MAX_CHARS":      400,         # 本文最大文字数
```

}

# ==============================================================================

# 📋 TICKER UNIVERSE (450+)

# ==============================================================================

_ORIGINAL = [
# Semiconductors & Hardware
“NVDA”, “AMD”, “AVGO”, “TSM”, “ASML”, “MU”, “QCOM”, “MRVL”, “LRCX”, “AMAT”,
“KLAC”, “ADI”, “ON”, “SMCI”, “ARM”, “MPWR”, “TER”, “COHR”, “APH”, “TXN”,
“GLW”, “STM”, “GFS”,
# AI / Cloud / Software
“MSFT”, “GOOGL”, “GOOG”, “META”, “AAPL”, “AMZN”, “NFLX”, “CRM”, “NOW”,
“SNOW”, “ADBE”, “INTU”, “ORCL”, “SAP”, “IBM”, “CSCO”, “ANET”, “NET”,
“PANW”, “CRWD”, “ACN”, “PLTR”, “APLD”,
# AI Infra / Data Center
“VRT”, “ALAB”, “NBIS”, “CLS”, “BE”,
# Space / Defense
“RKLB”, “ASTS”, “LUNR”, “HII”, “AXON”, “LMT”, “RTX”, “GE”, “GEV”,
# Consumer / Retail
“COST”, “WMT”, “TSLA”, “SBUX”, “NKE”, “MELI”, “BABA”, “CVNA”,
# Healthcare / Biotech
“LLY”, “ABBV”, “REGN”, “VRTX”, “NVO”, “BSX”, “HOLX”,
“OMER”, “DVAX”, “RARE”, “RIGL”, “KOD”, “TARS”,
# Fintech / Crypto
“MA”, “V”, “COIN”, “MSTR”, “HOOD”, “PAY”,
# Entertainment / Media
“SPOT”, “RDDT”, “RBLX”, “UBER”, “ETN”,
# Storage
“WDC”, “STX”, “SNDK”,
# Quantum / Emerging
“IONQ”, “OKLO”,
# Satellites / Connectivity
“LITE”,
# ETFs
“SPY”, “QQQ”, “IWM”, “SMH”,
]

_EXPANSION = [
# Mega Cap
“BRK-B”, “JPM”, “UNH”, “XOM”, “HD”, “MRK”, “CVX”, “BAC”, “LIN”, “DIS”,
“TMO”, “MCD”, “ABT”, “WFC”, “CMCSA”, “VZ”, “PFE”, “CAT”, “ISRG”,
“SPGI”, “HON”, “UNP”, “LOW”, “GS”, “BKNG”, “ELV”, “AXP”, “COP”,
“MDT”, “SYK”, “BLK”, “NEE”, “BA”, “TJX”, “PGR”, “C”, “CB”, “ADP”,
“MMC”, “PLD”, “CI”, “MDLZ”, “AMT”, “BX”, “TMUS”, “SCHW”,
“MO”, “EOG”, “DE”, “SO”, “DUK”, “SLB”, “CME”, “SHW”,
“CSX”, “PYPL”, “CL”, “EQIX”, “ICE”, “FCX”, “MCK”, “TGT”, “USB”,
“PH”, “GD”, “BDX”, “ITW”, “ABNB”, “HCA”, “NXPI”, “PSX”, “MAR”,
“NSC”, “EMR”, “AON”, “PNC”, “CEG”, “CDNS”, “SNPS”, “MCO”, “PCAR”,
“COF”, “FDX”, “ORLY”, “ADSK”, “VLO”, “OXY”, “TRV”, “AIG”, “HLT”,
“WELL”, “CARR”, “AZO”, “PAYX”, “MSI”, “TEL”, “PEG”, “AJG”, “ROST”,
“KMB”, “APD”, “URI”, “DHI”, “OKE”, “WMB”, “TRGP”, “SRE”, “CTAS”,
“AFL”, “GWW”, “LHX”, “MET”, “PCG”, “CMI”, “F”, “GM”, “STZ”,
“PSA”, “O”, “DLR”, “CCI”, “KMI”, “ED”, “XEL”, “EIX”, “WEC”,
“D”, “AWK”, “ES”, “AEP”, “EXC”,
# SaaS / PLG
“DDOG”, “MDB”, “HUBS”, “TTD”, “APP”, “PATH”, “MNDY”, “GTLB”,
“IOT”, “DUOL”, “CFLT”, “AI”, “SOUN”,
# Crypto Mining
“CLSK”, “MARA”, “RIOT”, “BITF”, “HUT”, “IREN”, “WULF”, “CORZ”, “CIFR”,
# Fintech
“AFRM”, “UPST”, “SOFI”, “DKNG”,
# Biotech
“MRNA”, “BNTX”, “UTHR”, “SMMT”, “VKTX”, “ALT”, “CRSP”, “NTLA”, “BEAM”,
# Nuclear / Uranium
“CCJ”, “URA”, “UUUU”, “DNN”, “NXE”, “UEC”,
# Materials / Metals
“SCCO”, “AA”, “NUE”, “STLD”, “TTE”,
# Consumer Brands
“CART”, “CAVA”, “LULU”, “ONON”, “DECK”, “CROX”, “WING”,
“CMG”, “DPZ”, “YUM”, “CELH”, “MNST”,
# Meme / Special
“GME”, “AMC”,
# PropTech
“U”, “OPEN”, “Z”,
# Sector ETFs
“XLF”, “XLV”, “XLE”, “XLI”, “XLK”, “XLC”, “XLY”, “XLP”, “XLB”, “XLU”, “XLRE”,
# Industrials
“ROP”, “TDG”, “RCL”, “EPAC”,
# Tobacco / Staples
“PM”, “PEP”, “KO”, “PG”,
]

TICKERS: list[str] = sorted(list(set(_ORIGINAL + _EXPANSION)))