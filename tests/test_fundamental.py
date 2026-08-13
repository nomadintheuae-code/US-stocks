"""FundamentalEngine tests (no network) — yfinance .info is mocked.

Phase 4.2: verifies the additive enrichment fields (market cap / volume /
shares) while preserving all pre-existing keys and behavior.
"""
import json
import types
from pathlib import Path

import pytest

import engines.fundamental as fundamental
from engines.fundamental import FundamentalEngine

# Pre-existing keys + the Phase 4.2 additive enrichment keys.
FAKE_INFO = {
    # --- pre-existing fields ---
    "targetMeanPrice": 200.0,
    "regularMarketPrice": 180.0,
    "targetHighPrice": 220.0,
    "targetLowPrice": 160.0,
    "numberOfAnalystOpinions": 12,
    "recommendationKey": "buy",
    "shortRatio": 2.5,
    "shortPercentOfFloat": 0.04,
    "heldPercentInsiders": 0.01,
    "heldPercentInstitutions": 0.70,
    "forwardPE": 22.5,
    "pegRatio": 1.5,
    "revenueGrowth": 0.12,
    "earningsGrowth": 0.18,
    "profitMargins": 0.25,
    "forwardEps": 8.0,
    # --- Phase 4.2 additive enrichment fields ---
    "marketCap": 2_800_000_000_000,
    "averageVolume": 52_000_000,
    "averageVolume10days": 60_000_000,
    "sharesOutstanding": 15_600_000_000,
    "floatShares": 15_500_000_000,
}

PRE_EXISTING_KEYS = (
    "analyst_target", "analyst_upside", "analyst_high", "analyst_low", "analyst_count",
    "recommendation", "short_ratio", "short_pct", "insider_pct", "institution_pct",
    "pe_forward", "peg_ratio", "revenue_growth", "earnings_growth", "profit_margin",
    "eps_forward",
)

ENRICHMENT_KEYS = (
    "market_cap", "average_volume", "average_volume_10d",
    "shares_outstanding", "float_shares",
)


@pytest.fixture()
def mock_ticker(monkeypatch, tmp_path):
    """Redirect cache dir and stub yfinance .info."""
    monkeypatch.setattr(fundamental, "CACHE_DIR", tmp_path)
    obj = types.SimpleNamespace(info=dict(FAKE_INFO))
    monkeypatch.setattr(fundamental.yf, "Ticker", lambda ticker: obj)
    return obj


def test_get_returns_enriched_fields(mock_ticker):
    data = FundamentalEngine.get("AAPL")
    assert data["market_cap"] == 2_800_000_000_000
    assert data["average_volume"] == 52_000_000
    assert data["average_volume_10d"] == 60_000_000
    assert data["shares_outstanding"] == 15_600_000_000
    assert data["float_shares"] == 15_500_000_000


def test_get_preserves_pre_existing_keys(mock_ticker):
    data = FundamentalEngine.get("AAPL")
    for k in PRE_EXISTING_KEYS:
        assert k in data, f"missing pre-existing key: {k}"
    assert data["analyst_target"] == 200.0
    assert data["analyst_upside"] == 11.1  # round((200/180-1)*100, 1)
    assert data["pe_forward"] == 22.5
    assert data["revenue_growth"] == 0.12


def test_get_missing_enrichment_fields_are_none(monkeypatch, tmp_path):
    monkeypatch.setattr(fundamental, "CACHE_DIR", tmp_path)
    obj = types.SimpleNamespace(info={"regularMarketPrice": 100.0})
    monkeypatch.setattr(fundamental.yf, "Ticker", lambda ticker: obj)
    data = FundamentalEngine.get("AAPL")
    for k in ENRICHMENT_KEYS:
        assert data[k] is None
    assert data["analyst_target"] is None


def test_get_empty_info_still_returns_all_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(fundamental, "CACHE_DIR", tmp_path)
    obj = types.SimpleNamespace(info={})
    monkeypatch.setattr(fundamental.yf, "Ticker", lambda ticker: obj)
    data = FundamentalEngine.get("AAPL")
    for k in PRE_EXISTING_KEYS + ENRICHMENT_KEYS:
        assert k in data
    # All values are None except recommendation, which defaults to "".
    for k in PRE_EXISTING_KEYS + ENRICHMENT_KEYS:
        if k == "recommendation":
            assert data[k] == ""
        else:
            assert data[k] is None


def test_get_caches_enriched_dict(monkeypatch, tmp_path):
    monkeypatch.setattr(fundamental, "CACHE_DIR", tmp_path)
    obj = types.SimpleNamespace(info=dict(FAKE_INFO))
    monkeypatch.setattr(fundamental.yf, "Ticker", lambda ticker: obj)
    first = FundamentalEngine.get("AAPL")
    cache_file = tmp_path / "fund_AAPL.json"
    assert cache_file.exists()
    stored = json.loads(cache_file.read_text(encoding="utf-8"))
    assert stored["market_cap"] == 2_800_000_000_000
    assert stored["average_volume"] == 52_000_000
    assert stored == first


def test_get_cache_hit_returns_enrichment(monkeypatch, tmp_path):
    cache_file = tmp_path / "fund_AAPL.json"
    cache_file.write_text(
        json.dumps({"market_cap": 123_000_000_000, "average_volume": 5_000_000}),
        encoding="utf-8",
    )
    monkeypatch.setattr(fundamental, "CACHE_DIR", tmp_path)
    data = FundamentalEngine.get("AAPL")
    assert data["market_cap"] == 123_000_000_000
    assert data["average_volume"] == 5_000_000


def test_get_corrupt_cache_refetches(mock_ticker):
    (fundamental.CACHE_DIR / "fund_AAPL.json").write_text("{not json", encoding="utf-8")
    data = FundamentalEngine.get("AAPL")
    assert data["market_cap"] == 2_800_000_000_000


def test_format_for_prompt_unchanged(mock_ticker):
    data = FundamentalEngine.get("AAPL")
    lines = FundamentalEngine.format_for_prompt(data, 180.0)
    assert any("アナリスト平均目標株価" in ln for ln in lines)
    assert any("予想PER" in ln for ln in lines)
    # Enrichment keys must not appear in prompt formatting.
    assert all("market_cap" not in ln and "average_volume" not in ln for ln in lines)
