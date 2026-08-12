#!/usr/bin/env python3
"""
Capture the Phase 2.1 frozen regression snapshot + golden artifact.

Reads the LIVE scanner caches (cache_v45) and the verified 2026-08-12 baseline
result, then:

  1. copies the OHLCV pickles + sectors.json into a frozen snapshot OUTSIDE the
     repository (SNAPSHOT_ROOT), together with meta.json (universe, config
     fingerprint, USD/JPY, commit).
  2. runs the frozen scan once and writes tests/golden/baseline_2026-08-12.json.

No credentials are read or written. .env / secrets are never touched.

Usage:
    ./venv/bin/python scripts/capture_frozen_snapshot.py
"""
from __future__ import annotations

import hashlib
import json
import pickle
import sys
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from regression_harness import (  # noqa: E402
    SNAPSHOT_DIR,
    SNAPSHOT_NAME,
    DATA_DIR,
    META_FILE,
    SECTORS_FILE,
    run_frozen_scan,
    write_golden,
    normalize_results,
    normalize_live_reference,
    decision_all,
    decision_items,
    DECISION_ITEM_FIELDS,
    load_snapshot_meta,
    snapshot_available,
)
import config  # noqa: E402

CACHE_V45 = ROOT / "cache_v45"
LIVE_RESULT = ROOT / "results" / "2026-08-12.json"


def main() -> int:
    if not CACHE_V45.exists():
        print("FATAL: cache_v45/ not found — nothing to freeze.")
        return 2

    print(f"Freezing snapshot -> {SNAPSHOT_DIR}")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)

    # 1) OHLCV pickles for the verified universe
    tickers = config.TICKERS
    copied, skipped = 0, []
    for t in tickers:
        src = CACHE_V45 / f"{t}.pkl"
        dst = DATA_DIR / f"{t}.pkl"
        if not src.exists():
            skipped.append(t)
            continue
        try:
            df = pickle.load(open(src, "rb"))
            rows = len(df)
        except Exception as e:
            skipped.append(f"{t}(corrupt:{e})")
            continue
        dst.write_bytes(src.read_bytes())
        copied += 1
    print(f"  pickles copied: {copied}/{len(tickers)}  skipped: {len(skipped)}")

    # 2) sectors snapshot
    if (CACHE_V45 / "sectors.json").exists():
        (SNAPSHOT_DIR / "sectors.json").write_bytes((CACHE_V45 / "sectors.json").read_bytes())
        print("  sectors.json copied")

    # 3) meta.json (no secrets)
    if not LIVE_RESULT.exists():
        print("FATAL: results/2026-08-12.json baseline reference missing.")
        return 2
    live = json.load(open(LIVE_RESULT, encoding="utf-8"))

    cfg_fingerprint = {
        "CONFIG": {k: config.CONFIG[k] for k in (
            "CAPITAL_JPY", "MAX_POSITIONS", "ACCOUNT_RISK_PCT", "MAX_SAME_SECTOR",
            "MIN_RS_RATING", "MIN_VCP_SCORE", "MIN_PROFIT_FACTOR",
            "STOP_LOSS_ATR", "TARGET_R_MULTIPLE", "CACHE_EXPIRY",
        )},
        "universe_file": config._cfg.data.universe_file,
        "filter_delisted": config._cfg.data.filter_delisted,
    }
    meta = {
        "schema_version": 1,
        "baseline_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip(),
        "captured_at": datetime.now().isoformat(),
        "snapshot_name": SNAPSHOT_NAME,
        "universe_count": len(tickers),
        "tickers": tickers,
        "skipped_in_cache": skipped,
        "usd_jpy": live.get("usd_jpy"),
        "live_baseline_counts": {
            "scan_count": live.get("scan_count"),
            "qualified_count": live.get("qualified_count"),
            "selected_count": live.get("selected_count"),
        },
        "config_fingerprint": cfg_fingerprint,
        "data_source": "cache_v45 pickles (yfinance auto_adjust=True, >=150 bars)",
    }
    with open(META_FILE, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("  meta.json written (no secrets)")

    # 4) Deterministic replay -> golden artifact
    print("Running frozen scan (CPU only, no network)...")
    results = run_frozen_scan()
    g = write_golden(results)
    print(f"Golden written -> {g}")

    # 5) Cross-check against the live 2026-08-12 reference (decision subset only)
    norm_frozen = normalize_results(results)
    norm_live = normalize_live_reference(live)

    fs = decision_all(norm_frozen)
    ls = decision_all(norm_live)
    match = fs == ls
    print("  frozen vs live-2026-08-12 DECISION equality:", "MATCH" if match else "DIFF")
    if match:
        print("  counts:", fs["scan_count"], "scanned /", fs["qualified_count"], "qualified /", fs["selected_count"], "ACTION")
    else:
        fq = {q["ticker"]: q for q in norm_frozen["qualified_full"]}
        lq = {q["ticker"]: q for q in norm_live["qualified_full"]}
        print("  qualified symbol sets equal:", set(fq) == set(lq))
        only_f = sorted(set(fq) - set(lq))
        only_l = sorted(set(lq) - set(fq))
        if only_f: print("  only-in-frozen:", only_f)
        if only_l: print("  only-in-live:", only_l)
        for t in sorted(set(fq) & set(lq)):
            a, b = fq[t], lq[t]
            diffs = {k for k in DECISION_ITEM_FIELDS if k in a and b.get(k) != a.get(k)}
            if diffs:
                print(f"  decision field diffs for {t}: {sorted(diffs)}")
        print("  NOTE: differences mean the frozen snapshot deviates from the 00:46 run inputs.")

    print("\nDone. Snapshot:", SNAPSHOT_DIR)
    return 0 if match else 3


if __name__ == "__main__":
    raise SystemExit(main())