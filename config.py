"""
Backward-compatible configuration wrapper.
Uses new sentinel.config system but exposes old CONFIG dict and TICKERS.
"""
import os
from typing import Any, Dict, List

from sentinel.config import get_config


# Load new config system
_cfg = get_config()

# ==============================================================================
# ⚙️ 設定ヘルパー (kept for reference)
# ==============================================================================

def _ei(key: str, default: int) -> int:
    """環境変数を int で取得。未設定・空文字はデフォルト値を返す。"""
    v = os.getenv(key, "").strip()
    return int(v) if v else int(default)


def _ef(key: str, default: float) -> float:
    """環境変数を float で取得。未設定・空文字はデフォルト値を返す。"""
    v = os.getenv(key, "").strip()
    return float(v) if v else float(default)


# ==============================================================================
# ⚙️ CONFIG (Backward Compatible Dict)
# ==============================================================================

CONFIG: Dict[str, Any] = {
    # --- 資金・ポジション管理 ---
    "CAPITAL_JPY":       _cfg.capital.jpy,
    "MAX_POSITIONS":     _cfg.capital.max_positions,
    "ACCOUNT_RISK_PCT":  _cfg.capital.account_risk_pct,
    "MAX_SAME_SECTOR":   _cfg.capital.max_same_sector,

    # --- スキャンフィルター ---
    "MIN_RS_RATING":     _cfg.scan.min_rs_rating,
    "MIN_VCP_SCORE":     _cfg.scan.min_vcp_score,
    "MIN_PROFIT_FACTOR": _cfg.scan.min_profit_factor,

    # --- 出口戦略 ---
    "STOP_LOSS_ATR":     _cfg.exit.stop_loss_atr,
    "TARGET_R_MULTIPLE": _cfg.exit.target_r_multiple,

    # --- システム ---
    "CACHE_EXPIRY":       _cfg.get_cache_expiry_seconds("price"),
    "FUND_CACHE_EXPIRY":  _cfg.get_cache_expiry_seconds("fundamental"),
    "NEWS_CACHE_EXPIRY":  _cfg.get_cache_expiry_seconds("news"),
    "NEWS_FETCH_TIMEOUT": _cfg.performance.request_timeout,
    "NEWS_MAX_CHARS":     400,
}

# Allow environment variable overrides for backward compatibility
_env_overrides = {
    "CAPITAL_JPY": "CAPITAL_JPY",
    "MAX_POSITIONS": "MAX_POSITIONS",
    "ACCOUNT_RISK_PCT": "ACCOUNT_RISK_PCT",
    "MIN_RS_RATING": "MIN_RS_RATING",
    "MIN_VCP_SCORE": "MIN_VCP_SCORE",
    "MIN_PROFIT_FACTOR": "MIN_PROFIT_FACTOR",
    "STOP_LOSS_ATR": "STOP_LOSS_ATR",
    "TARGET_R_MULTIPLE": "TARGET_R_MULTIPLE",
}

for key, env_key in _env_overrides.items():
    if os.getenv(env_key):
        try:
            if key in ["CAPITAL_JPY", "MAX_POSITIONS", "MAX_SAME_SECTOR", "MIN_RS_RATING", "MIN_VCP_SCORE"]:
                CONFIG[key] = int(os.getenv(env_key, ""))
            else:
                CONFIG[key] = float(os.getenv(env_key, ""))
        except (ValueError, TypeError):
            pass  # Keep config.yaml value

# ==============================================================================
# 📋 TICKER UNIVERSE
# ==============================================================================

_ORIGINAL = [
    # Semiconductors & Hardware
    "NVDA", "AMD", "AVGO", "TSM", "ASML", "MU", "QCOM", "MRVL", "LRCX", "AMAT",
    "KLAC", "ADI", "ON", "SMCI", "ARM", "MPWR", "TER", "COHR", "APH", "TXN",
    "GLW", "STM", "GFS",

    # AI / Cloud / Software
    "MSFT", "GOOGL", "GOOG", "META", "AAPL", "AMZN", "NFLX", "CRM", "NOW",
    "SNOW", "ADBE", "INTU", "ORCL", "SAP", "IBM", "CSCO", "ANET", "NET",
    "PANW", "CRWD", "ACN", "PLTR", "APLD",

    # AI Infra / Data Center
    "VRT", "ALAB", "NBIS", "CLS", "BE",

    # Space / Defense
    "RKLB", "ASTS", "LUNR", "HII", "AXON", "LMT", "RTX", "GE", "GEV",

    # Consumer / Retail
    "COST", "WMT", "TSLA", "SBUX", "NKE", "MELI", "BABA", "CVNA",

    # Healthcare / Biotech
    "LLY", "ABBV", "REGN", "VRTX", "NVO", "BSX", "HOLX",
    "OMER", "DVAX", "RARE", "RIGL", "KOD", "TARS",

    # Fintech / Crypto
    "MA", "V", "COIN", "MSTR", "HOOD", "PAY",

    # Entertainment / Media
    "SPOT", "RDDT", "RBLX", "UBER", "ETN",

    # Storage
    "WDC", "STX", "SNDK",

    # Quantum / Emerging
    "IONQ", "OKLO",

    # Satellites / Connectivity
    "LITE",

    # ETFs
    "SPY", "QQQ", "IWM", "SMH",
]

_EXPANSION = [
    # Mega Cap
    "BRK-B", "JPM", "UNH", "XOM", "HD", "MRK", "CVX", "BAC", "LIN", "DIS",
    "TMO", "MCD", "ABT", "WFC", "CMCSA", "VZ", "PFE", "CAT", "ISRG",
    "SPGI", "HON", "UNP", "LOW", "GS", "BKNG", "ELV", "AXP", "COP",
    "MDT", "SYK", "BLK", "NEE", "BA", "TJX", "PGR", "C", "CB", "ADP",
    "MMC", "PLD", "CI", "MDLZ", "AMT", "BX", "TMUS", "SCHW",
    "MO", "EOG", "DE", "SO", "DUK", "SLB", "CME", "SHW",
    "CSX", "PYPL", "CL", "EQIX", "ICE", "FCX", "MCK", "TGT", "USB",
    "PH", "GD", "BDX", "ITW", "ABNB", "HCA", "NXPI", "PSX", "MAR",
    "NSC", "EMR", "AON", "PNC", "CEG", "CDNS", "SNPS", "MCO", "PCAR",
    "COF", "FDX", "ORLY", "ADSK", "VLO", "OXY", "TRV", "AIG", "HLT",
    "WELL", "CARR", "AZO", "PAYX", "MSI", "TEL", "PEG", "AJG", "ROST",
    "KMB", "APD", "URI", "DHI", "OKE", "WMB", "TRGP", "SRE", "CTAS",
    "AFL", "GWW", "LHX", "MET", "PCG", "CMI", "F", "GM", "STZ",
    "PSA", "O", "DLR", "CCI", "KMI", "ED", "XEL", "EIX", "WEC",
    "D", "AWK", "ES", "AEP", "EXC",

    # SaaS / PLG
    "DDOG", "MDB", "HUBS", "TTD", "APP", "PATH", "MNDY", "GTLB",
    "IOT", "DUOL", "CFLT", "AI", "SOUN",

    # Crypto Mining
    "CLSK", "MARA", "RIOT", "BITF", "HUT", "IREN", "WULF", "CORZ", "CIFR",

    # Fintech
    "AFRM", "UPST", "SOFI", "DKNG",

    # Biotech
    "MRNA", "BNTX", "UTHR", "SMMT", "VKTX", "ALT", "CRSP", "NTLA", "BEAM",

    # Nuclear / Uranium
    "CCJ", "URA", "UUUU", "DNN", "NXE", "UEC",

    # Materials / Metals
    "SCCO", "AA", "NUE", "STLD", "TTE",

    # Consumer Brands
    "CART", "CAVA", "LULU", "ONON", "DECK", "CROX", "WING",
    "CMG", "DPZ", "YUM", "CELH", "MNST",

    # Meme / Special
    "GME", "AMC",

    # PropTech
    "U", "OPEN", "Z",

    # Sector ETFs
    "XLF", "XLV", "XLE", "XLI", "XLK", "XLC", "XLY", "XLP", "XLB", "XLU", "XLRE",

    # Industrials
    "ROP", "TDG", "RCL", "EPAC",

    # Tobacco / Staples
    "PM", "PEP", "KO", "PG",
]

TICKERS: List[str] = sorted(list(set(_ORIGINAL + _EXPANSION)))

# Filter delisted tickers if enabled
if _cfg.data.filter_delisted:
    DELISTED = {"BITF", "CFLT", "DVAX", "HOLX", "MMC"}
    TICKERS = [t for t in TICKERS if t not in DELISTED]

# Support external universe file
if _cfg.data.universe_file and os.path.exists(_cfg.data.universe_file):
    try:
        with open(_cfg.data.universe_file, "r") as f:
            external = [line.strip().upper() for line in f if line.strip() and not line.startswith("#")]
        if external:
            TICKERS = external
    except Exception:
        pass  # Fall back to built-in universe


# ==============================================================================
# 🛰️ UniverseManager — load, validate, filter the ticker universe
# ==============================================================================
# Encapsulates the universe logic above into a class. It is a faithful,
# deterministic re-implementation of the existing config.TICKERS computation,
# so existing callers that use config.TICKERS are completely unaffected.
# The manager is opt-in: nothing here changes current behavior.
# ==============================================================================

class UniverseManager:
    """Loads, validates and filters the ticker universe.

    Responsibilities:
    - Load the built-in curated ticker universe (deduplicated and sorted).
    - Validate / normalize raw ticker lists.
    - Filter delisted tickers (``data.filter_delisted`` in config.yaml).
    - Support an optional external universe file (``data.universe_file``).

    Behavior mirrors the existing ``config.TICKERS`` computation exactly:

    1. Built-in tickers are deduplicated, uppercased and sorted.
    2. Delisted tickers are removed when delisted filtering is enabled.
    3. A non-empty external universe file (if configured) replaces the list
       entirely; file order is preserved, and blank / ``#`` comment lines are
       skipped. Unreadable or empty external files fall back to the built-in
       universe.

    Deterministic: identical inputs always produce an identical ticker list.
    """

    DELISTED = {"BITF", "CFLT", "DVAX", "HOLX", "MMC"}

    def __init__(
        self,
        tickers: Optional[List[str]] = None,
        delisted: Optional[set] = None,
        filter_delisted: Optional[bool] = None,
        universe_file: Optional[str] = None,
    ):
        cfg = self._load_data_config()
        self._base_tickers = list(tickers) if tickers is not None else self._builtin_tickers()
        self._delisted = set(delisted) if delisted is not None else set(self.DELISTED)
        self._filter_delisted = (
            filter_delisted if filter_delisted is not None else bool(cfg.get("filter_delisted", True))
        )
        self._universe_file = universe_file if universe_file is not None else cfg.get("universe_file", "")

    @staticmethod
    def _load_data_config() -> dict:
        """Load the ``data:`` universe settings from config.yaml (best-effort)."""
        try:
            from sentinel.config import get_config
            cfg = get_config()
            return {
                "filter_delisted": bool(cfg.data.filter_delisted),
                "universe_file": str(cfg.data.universe_file or ""),
            }
        except Exception:
            return {}

    @staticmethod
    def _builtin_tickers() -> List[str]:
        """Return the hardcoded built-in universe (raw, before normalization)."""
        return list(_ORIGINAL) + list(_EXPANSION)

    @classmethod
    def from_config(cls) -> "UniverseManager":
        """Construct a manager from the current config.yaml settings."""
        return cls()

    def validate(self, tickers: Optional[List[str]]) -> List[str]:
        """Normalize and validate a raw ticker list.

        Uppercases, strips whitespace, drops empty entries, de-duplicates,
        and returns a deterministic sorted list.
        """
        seen: set = set()
        out: List[str] = []
        for t in tickers or []:
            s = str(t).strip().upper()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
        return sorted(out)

    def filter_delisted_tickers(self, tickers: Optional[List[str]]) -> List[str]:
        """Return ``tickers`` with delisted symbols removed (order preserved)."""
        return [t for t in (tickers or []) if t not in self._delisted]

    def load(self) -> List[str]:
        """Return the final ticker universe.

        Identical semantics to the existing ``config.TICKERS`` computation.
        """
        tickers = self.validate(self._base_tickers)
        if self._filter_delisted:
            tickers = self.filter_delisted_tickers(tickers)
        if self._universe_file and os.path.exists(self._universe_file):
            try:
                with open(self._universe_file, "r", encoding="utf-8") as f:
                    external = [
                        line.strip().upper()
                        for line in f
                        if line.strip() and not line.startswith("#")
                    ]
                if external:
                    tickers = external
            except Exception:
                pass  # Fall back to built-in universe
        return tickers

    @property
    def tickers(self) -> List[str]:
        """Alias for ``load()``."""
        return self.load()

    def __len__(self) -> int:
        return len(self.load())

    def __iter__(self):
        return iter(self.load())