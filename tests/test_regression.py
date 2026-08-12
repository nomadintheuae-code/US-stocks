"""
Phase 2.1 regression tests — deterministic scanner replay against a frozen
data snapshot and the golden artifact.

Strategy logic is NOT modified by these tests. They prove that the scanner's
decision output is stable across (a) repeated runs and (b) future refactors,
by comparing every deterministic run against the golden baseline captured at
commit b5b0986.

Heavy tests that replay the full 310-ticker scan SKIP cleanly when the frozen
snapshot directory is absent. The snapshot is intentionally stored OUTSIDE the
repository (see tests/regression_harness.py). Recreate it with:

    ./venv/bin/python scripts/capture_frozen_snapshot.py

The golden JSON (tests/golden/baseline_2026-08-12.json) is machine-readable,
contains no credentials, and lives in the repo.
"""
import json
import re

import pytest

from regression_harness import (
    GOLDEN_PATH,
    LIVE_REFERENCE,
    run_frozen_scan,
    normalize_results,
    decision_all,
    snapshot_available,
    read_golden,
    sha256_of,
)

pytestmark = pytest.mark.regression

requires_snapshot = pytest.mark.skipif(
    not snapshot_available(),
    reason="frozen snapshot not present; run scripts/capture_frozen_snapshot.py",
)


# ---------------------------------------------------------------- golden meta

def test_golden_artifact_exists():
    assert GOLDEN_PATH.exists(), f"golden missing: {GOLDEN_PATH}"


def test_golden_artifact_contains_no_secrets():
    golden = read_golden()
    text = json.dumps(golden)
    assert not re.search(r"sk-[A-Za-z0-9]{20,}", text)
    assert not re.search(r'"[A-Za-z0-9]{32}"', text)
    assert "apikey" not in text.lower()


def test_golden_baseline_counts_matches_approved_baseline():
    golden = read_golden()
    r = golden["results"]
    assert r["scan_count"] == 310
    assert r["qualified_count"] == 30
    assert r["selected_count"] == 15
    assert golden["baseline_commit"] == "b5b0986"


def test_golden_universe_matches_config():
    import config

    golden = read_golden()
    assert golden["universe_count"] == len(config.TICKERS)
    statuses = {q["status"] for q in golden["results"]["qualified_full"]}
    assert "ACTION" in statuses
    assert "WAIT" in statuses


# ---------------------------------------------------------------- replay

@requires_snapshot
def test_frozen_scan_reproduces_golden():
    """A fresh deterministic run must equal the golden artifact exactly."""
    got = normalize_results(run_frozen_scan())
    want = read_golden()["results"]
    assert got == want, (
        "Scanner decision output differs from golden. If this is a deliberate "
        "behavior change, regenerate the golden and explain it."
    )


@requires_snapshot
def test_frozen_scan_is_deterministic():
    """Two independent runs on the frozen snapshot must be identical."""
    first = run_frozen_scan()
    second = run_frozen_scan()
    assert normalize_results(first) == normalize_results(second)
    assert sha256_of(normalize_results(first)) == sha256_of(normalize_results(second))


@requires_snapshot
def test_frozen_scan_matches_live_reference_decisions():
    """Frozen replay must reproduce the actual 2026-08-12 run on decision fields."""
    if not LIVE_REFERENCE.exists():
        pytest.skip("results/2026-08-12.json reference not present")
    with open(LIVE_REFERENCE, "r", encoding="utf-8") as f:
        live = json.load(f)
    got = decision_all(normalize_results(run_frozen_scan()))
    want = decision_all(normalize_results(live))
    assert got == want


# ---------------------------------------------------------------- scanner invariants

def test_qualified_is_action_superset_in_golden():
    r = read_golden()["results"]
    sel = [s["ticker"] for s in r["selected"]]
    qualf = [q["ticker"] for q in r["qualified_full"]]
    assert all(t in qualf for t in sel), "selected must be a subset of qualified"


def test_ranking_order_present_in_golden():
    # sentinel.py Phase 4 sorts by (status_rank, rs + vcp + pf*10), descending.
    r = read_golden()["results"]
    status_rank = {"ACTION": 3, "WAIT": 2, "EXTENDED": 1}
    keys = [
        (
            status_rank.get(q["status"], 0),
            q["rs"] + q["vcp"]["score"] + round(q["pf"] * 10, 2),
        )
        for q in r["qualified_full"]
    ]
    assert keys == sorted(keys, reverse=True)