"""FMP client tests — no network; requests.get is mocked."""
import json
import os
import re
import types
from pathlib import Path

import pandas as pd
import pytest

import core_fmp
from core_fmp import FMPPlanError


def _resp(status: int = 200, data=None):
    r = types.SimpleNamespace()
    r.status_code = status
    r.json = lambda: (data if data is not None else [])
    return r


@pytest.fixture()
def mock_fmp(monkeypatch, tmp_path):
    """Redirect cache dir, silence sleep, and stub requests.get."""
    monkeypatch.setattr(core_fmp, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(core_fmp.time, "sleep", lambda s: None)
    responses = {"_calls": []}

    def fake_get(url, params=None, **kwargs):
        responses["_calls"].append((url, params))
        if url not in responses:
            raise AssertionError(f"unexpected network call: {url}")
        return responses[url]

    monkeypatch.setattr(core_fmp.requests, "get", fake_get)
    return responses


BASE = "https://financialmodelingprep.com/stable/"


# --- key handling -----------------------------------------------------------

def test_key_comes_from_env_not_hardcoded():
    assert core_fmp.FMP_API_KEY == os.environ.get("FMP_API_KEY", "")
    src = Path(core_fmp.__file__).read_text()
    assert not re.search(r'"[A-Za-z0-9]{32}"', src), "hardcoded key literal found in source"
    assert not re.search(r"FMP_API_KEY\s*=\s*['\"][A-Za-z0-9]{20,}", src)


def test_empty_key_degrades_gracefully(mock_fmp, monkeypatch):
    monkeypatch.setattr(core_fmp, "FMP_API_KEY", "")
    mock_fmp[BASE + "quote"] = _resp(401, {})
    assert core_fmp.get_quote("AAPL") is None


# --- quote / profile --------------------------------------------------------

def test_get_quote_parsing(mock_fmp):
    mock_fmp[BASE + "quote"] = _resp(200, [{"symbol": "AAPL", "price": 150.0, "changesPercentage": 1.2}])
    q = core_fmp.get_quote("AAPL")
    assert q["symbol"] == "AAPL"
    assert q["price"] == 150.0


def test_get_quote_empty_list(mock_fmp):
    mock_fmp[BASE + "quote"] = _resp(200, [])
    assert core_fmp.get_quote("AAPL") is None


def test_get_quote_non200_returns_none(mock_fmp):
    mock_fmp[BASE + "quote"] = _resp(500, {})
    assert core_fmp.get_quote("AAPL") is None


def test_get_company_profile_parsing(mock_fmp):
    mock_fmp[BASE + "profile"] = _resp(200, [{"symbol": "AAPL", "companyName": "Apple Inc."}])
    p = core_fmp.get_company_profile("AAPL")
    assert p["companyName"] == "Apple Inc."


# --- news (HTTP 402 isolation) ----------------------------------------------

def test_get_news_parsing(mock_fmp):
    mock_fmp[BASE + "news/stock-latest"] = _resp(200, [
        {"title": "Headline", "publishedDate": "2026-08-12", "site": "Source",
         "url": "http://x", "text": "summary text"}
    ])
    news = core_fmp.get_news("AAPL", limit=5)
    assert len(news) == 1
    assert news[0]["title"] == "Headline"
    assert news[0]["source"] == "Source"
    assert news[0]["url"] == "http://x"
    assert news[0]["summary"] == "summary text"


def test_get_news_402_raises_plan_error(mock_fmp):
    mock_fmp[BASE + "news/stock-latest"] = _resp(402, "Payment Required")
    with pytest.raises(FMPPlanError) as exc:
        core_fmp.get_news("AAPL")
    assert exc.value.status_code == 402
    assert exc.value.message


def test_get_news_non_list_returns_empty(mock_fmp):
    mock_fmp[BASE + "news/stock-latest"] = _resp(200, {"error": "nope"})
    assert core_fmp.get_news("AAPL") == []


# --- fundamentals / analyst -------------------------------------------------

def test_get_fundamentals_parsing(mock_fmp):
    mock_fmp[BASE + "key-metrics"] = _resp(200, [
        {"peRatio": 22.5, "returnOnEquity": 0.2, "debtToEquity": 1.5, "marketCap": 2_000_000_000_000}
    ])
    mock_fmp[BASE + "income-statement-growth"] = _resp(200, [{"growthRevenue": 0.1}])
    f = core_fmp.get_fundamentals("AAPL")
    assert f["pe"] == 22.5
    assert f["roe"] == 20.0
    assert f["rev_growth"] == 10.0
    assert f["debt_equity"] == 1.5
    assert f["market_cap_b"] == 2000.0


def test_get_fundamentals_missing_data(mock_fmp):
    mock_fmp[BASE + "key-metrics"] = _resp(200, [])
    mock_fmp[BASE + "income-statement-growth"] = _resp(200, [])
    f = core_fmp.get_fundamentals("AAPL")
    assert f["pe"] == 0.0


def test_get_analyst_consensus(mock_fmp):
    mock_fmp[BASE + "price-target-summary"] = _resp(200, [{"lastMonthAvgPriceTarget": 220.0, "allTimeCount": 15}])
    mock_fmp[BASE + "quote"] = _resp(200, [{"price": 200.0}])
    a = core_fmp.get_analyst_consensus("AAPL")
    assert a["target"] == 220.0
    assert a["upside"] == 10.0
    assert a["count"] == 15


def test_get_analyst_consensus_without_target(mock_fmp):
    mock_fmp[BASE + "price-target-summary"] = _resp(200, [{"lastMonthAvgPriceTarget": 0, "allTimeCount": 0}])
    mock_fmp[BASE + "quote"] = _resp(200, [{"price": 100.0}])
    a = core_fmp.get_analyst_consensus("AAPL")
    assert a["upside"] == 0.0


# --- historical -------------------------------------------------------------

def test_get_historical_data_parsing(mock_fmp):
    rows = [
        {"date": "2026-01-01", "open": 100, "high": 105, "low": 99, "close": 104, "volume": 1000},
        {"date": "2026-01-02", "open": 104, "high": 110, "low": 103, "close": 109, "volume": 1200},
    ]
    mock_fmp[BASE + "historical-price-eod/full"] = _resp(200, rows)
    df = core_fmp.get_historical_data("AAPL", days=365)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert len(df) == 2
    assert df["Close"].iloc[-1] == 109
    assert str(df.index.name) == "date"


def test_get_historical_data_non_list(mock_fmp):
    mock_fmp[BASE + "historical-price-eod/full"] = _resp(200, {})
    assert core_fmp.get_historical_data("AAPL") is None


# --- caching ----------------------------------------------------------------

def test_get_caches_by_cache_key(mock_fmp):
    mock_fmp[BASE + "quote"] = _resp(200, [{"symbol": "AAPL"}])
    first = core_fmp._get("quote", {"symbol": "AAPL"}, cache_key="test_key", ttl=3600)
    second = core_fmp._get("quote", {"symbol": "AAPL"}, cache_key="test_key", ttl=3600)
    assert first == [{"symbol": "AAPL"}]
    assert second == [{"symbol": "AAPL"}]
    assert len(mock_fmp["_calls"]) == 1, "cache key should prevent a second request"


def test_get_no_cache_key_makes_two_requests(mock_fmp):
    mock_fmp[BASE + "quote"] = _resp(200, [{"symbol": "AAPL"}])
    core_fmp._get("quote", {"symbol": "AAPL"})
    core_fmp._get("quote", {"symbol": "AAPL"})
    assert len(mock_fmp["_calls"]) == 2


def test_get_skips_corrupt_cache(mock_fmp, tmp_path):
    (tmp_path / "corrupt").write_text("not json")
    mock_fmp[BASE + "quote"] = _resp(200, [{"symbol": "AAPL"}])
    data = core_fmp._get("quote", {"symbol": "AAPL"}, cache_key="bogus_md5", ttl=3600)
    assert data == [{"symbol": "AAPL"}]
