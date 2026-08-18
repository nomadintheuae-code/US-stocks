"""
Regression harness for the SENTINEL PRO scanner (Phase 2.1).

Purpose
-------
Replay the *production* scanner pipeline (sentinel.run()) on a FROZEN data
snapshot so that architecture refactors can be proven behavior-neutral.

Design
------
- The heavy frozen OHLCV data lives OUTSIDE the repository (see
  SNAPSHOT_ROOT) so nothing large or secret enters git.
- The lightweight golden artifact (tests/golden/baseline_2026-08-12.json) IS
  kept in the repo and compared against fresh deterministic runs.
- The scanner's live I/O is stubbed with frozen values; the indicator and
  decision logic are NOT touched, so this harness exercises the real code.
- Deterministic, CPU-only scan replay: strategy parameters, universe, and
  comparisons are unchanged.

This module contains NO faked market data: the pickle frames are the actual
cached yfinance OHLCV captured on 2026-08-12 (see scripts/capture_frozen_snapshot.py).
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import pickle
import tempfile
from pathlib import Path

import pandas as pd
from unittest import mock

ROOT_DIR = Path(__file__).resolve().parent.parent
SCANNER_PATH = ROOT_DIR / "sentinel.py"

# ---------------------------------------------------------------- locations

SNAPSHOT_NAME = "2026-08-12_b5b0986"
SNAPSHOT_ROOT = Path(
    os.environ.get("SENTINEL_FROZEN_SNAPSHOT", "~/ProjectBackups/US-stocks/frozen_snapshots")
).expanduser()
SNAPSHOT_DIR = SNAPSHOT_ROOT / SNAPSHOT_NAME

GOLDEN_PATH = Path(__file__).resolve().parent / "golden" / "baseline_2026-08-12.json"
LIVE_REFERENCE = Path(__file__).resolve().parent.parent / "results" / "2026-08-12.json"

META_FILE = SNAPSHOT_DIR / "meta.json"
DATA_DIR = SNAPSHOT_DIR / "data"
SECTORS_FILE = SNAPSHOT_DIR / "sectors.json"

# ---------------------------------------------------------------- snapshot

DROPPED_ITEM_KEYS = ("news", "insider_detail")  # live-stubbed fields, not decisions
DROPPED_TOP_KEYS = ("date", "timestamp", "runtime")  # wall-clock fields


def snapshot_available() -> bool:
    return META_FILE.exists() and DATA_DIR.exists()


def load_snapshot_meta() -> dict:
    with open(META_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def load_snapshot_dfs() -> dict[str, pd.DataFrame]:
    """Load the frozen OHLCV frame for every ticker present in the snapshot."""
    dfs: dict[str, pd.DataFrame] = {}
    for f in DATA_DIR.glob("*.pkl"):
        try:
            with open(f, "rb") as fh:
                dfs[f.stem.upper()] = pickle.load(fh)
        except Exception:
            continue  # a corrupt frozen entry behaves like a cache miss (ticker skipped)
    return dfs


def load_snapshot_sectors() -> dict[str, str]:
    if SECTORS_FILE.exists():
        try:
            with open(SECTORS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {str(k).upper(): str(v) for k, v in data.items()}
        except Exception:
            pass
    return {}


# ---------------------------------------------------------------- replay

def run_frozen_scan() -> dict:
    """Run the real sentinel.run() on the frozen snapshot; return its JSON output dict.

    Live I/O is stubbed:
      - OHLCV            -> frozen pickle frames
      - USD/JPY          -> frozen value from the baseline run's meta
      - sector           -> frozen sectors.json snapshot
      - fundamental      -> frozen EMPTY (fundamentals are not decision inputs)
      - insider          -> frozen no-alert stub
      - news             -> frozen empty stub
      - LINE push        -> no-op
    """
    # NOTE: the repo contains BOTH a `sentinel.py` module and a `sentinel/`
    # package directory; plain `import sentinel` resolves to the package, so the
    # scanner script is loaded explicitly by file path.
    spec = importlib.util.spec_from_file_location("sentinel_scanner", SCANNER_PATH)
    scanner = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(scanner)

    with tempfile.TemporaryDirectory(prefix="sentinel_frozen_") as tmp:
        out_dir = Path(tmp) / "results"
        out_dir.mkdir(parents=True, exist_ok=True)

        meta = load_snapshot_meta()
        dfs = load_snapshot_dfs()
        sectors = load_snapshot_sectors()

        sector_func = lambda ticker: sectors.get(ticker.upper(), "Unknown")
        insider_stub = lambda ticker: {
            "buy_count": 0, "sell_count": 0, "net_shares": 0, "alert": False,
            "summary": "", "recent": [],
        }

        with mock.patch.object(scanner, "RESULTS_DIR", out_dir), \
             mock.patch.object(scanner, "send_line", lambda msg, **kw: None), \
             mock.patch.object(scanner.DataEngine, "get_data", lambda ticker, period="700d": dfs.get(ticker)), \
             mock.patch.object(scanner.DataEngine, "get_sector", sector_func), \
             mock.patch.object(scanner.CurrencyEngine, "get_usd_jpy", lambda: meta.get("usd_jpy", 150.0)), \
             mock.patch.object(scanner.FundamentalEngine, "get", lambda ticker: {}), \
             mock.patch.object(scanner.InsiderEngine, "get", insider_stub), \
             mock.patch.object(scanner.NewsEngine, "get", lambda ticker: {"articles": [], "fetched_at": "frozen"}), \
             mock.patch.object(scanner.EarningsCalendarEngine, "build_earnings_map", lambda tickers, days_ahead=14: {}):

            scanner.run()

        out_files = sorted(out_dir.glob("*.json"))
        if not out_files:
            raise RuntimeError("frozen scan produced no results file")
        with open(out_files[-1], "r", encoding="utf-8") as f:
            return json.load(f)


def normalize_results(results: dict) -> dict:
    """Strip wall-clock and live-stubbed fields; keep all decision fields + order."""
    def clean_item(it: dict) -> dict:
        return {k: v for k, v in it.items() if k not in DROPPED_ITEM_KEYS}

    out = {k: v for k, v in results.items() if k not in DROPPED_TOP_KEYS}
    for key in ("selected", "watchlist_wait", "qualified_full"):
        if key in out:
            out[key] = [clean_item(it) for it in out[key]]
    return out


def normalize_live_reference(results: dict) -> dict:
    """Same normalization for the actual 2026-08-12 results/ JSON (for cross-checking)."""
    return normalize_results(results)


# Fields that drive scanner output decisions. Fundamental/informational fields
# (analyst targets, insider alerts, PE, etc.) are live yfinance .info values and,
# by design, are stubbed to empty in frozen runs; they never influence filters
# or ranking, so only these fields are used for the "frozen == live" check.
DECISION_ITEM_FIELDS = (
    "ticker", "status", "price", "entry", "stop", "target", "shares",
    "rs", "pf", "sector", "vcp",
)


def decision_items(items) -> list[dict]:
    return [{k: it[k] for k in DECISION_ITEM_FIELDS if k in it} for it in items]


def decision_all(results: dict) -> dict:
    """Project a normalized result dict to decision-only, order-preserving form."""
    return {
        "scan_count": results["scan_count"],
        "qualified_count": results["qualified_count"],
        "selected_count": results["selected_count"],
        "usd_jpy": results["usd_jpy"],
        "selected": decision_items(results.get("selected", [])),
        "watchlist_wait": decision_items(results.get("watchlist_wait", [])),
        "qualified_full": decision_items(results.get("qualified_full", [])),
    }


def sha256_of(obj: dict) -> str:
    return hashlib.sha256(json.dumps(obj, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------- golden

def golden_payload(results: dict) -> dict:
    meta = load_snapshot_meta()
    return {
        "schema_version": 1,
        "baseline_commit": "b5b0986",
        "baseline_date": "2026-08-12",
        "snapshot_dir": SNAPSHOT_DIR.name,
        "universe_count": meta.get("universe_count"),
        "captured_at": meta.get("captured_at"),
        "results": normalize_results(results),
    }


def write_golden(results: dict) -> Path:
    GOLDEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(GOLDEN_PATH, "w", encoding="utf-8") as f:
        json.dump(golden_payload(results), f, ensure_ascii=False, indent=2, sort_keys=True)
    return GOLDEN_PATH


def read_golden() -> dict:
    with open(GOLDEN_PATH, "r", encoding="utf-8") as f:
        return json.load(f)