"""Phase 7 Earnings Calendar Engine tests (no network)."""
import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch
import pandas as pd

from engines.earnings import EarningsCalendarEngine
from engines.filters import (
    STAGE_UNIVERSE,
    EarningsFilter,
    FilterContext,
    FilterResult,
)


# ---------------------------------------------------------------------------
# EarningsCalendarEngine tests
# ---------------------------------------------------------------------------

class TestEarningsCalendarEngine:
    """Tests for the EarningsCalendarEngine class."""

    @patch("engines.earnings.yf")
    def test_get_market_earnings_success(self, mock_yf):
        """Returns DataFrame on successful fetch."""
        mock_cal_instance = MagicMock()
        mock_df = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT"],
            "Company": ["Apple", "Microsoft"],
            "Earnings Date": ["2026-01-30", "2026-01-29"],
        })
        mock_cal_instance.get_earnings_calendar.return_value = mock_df
        mock_yf.Calendars.return_value = mock_cal_instance

        result = EarningsCalendarEngine.get_market_earnings(
            start="2026-01-27", end="2026-02-03"
        )
        assert result is not None
        assert len(result) == 2
        mock_yf.Calendars.assert_called_once_with(
            start="2026-01-27", end="2026-02-03"
        )

    @patch("engines.earnings.yf")
    def test_get_market_earnings_empty(self, mock_yf):
        """Returns None when no earnings found."""
        mock_cal_instance = MagicMock()
        mock_cal_instance.get_earnings_calendar.return_value = pd.DataFrame()
        mock_yf.Calendars.return_value = mock_cal_instance

        result = EarningsCalendarEngine.get_market_earnings(
            start="2026-01-27", end="2026-02-03"
        )
        assert result is None

    @patch("engines.earnings.yf")
    def test_get_market_earnings_exception(self, mock_yf):
        """Returns None on exception."""
        mock_yf.Calendars.side_effect = Exception("API error")

        result = EarningsCalendarEngine.get_market_earnings(
            start="2026-01-27", end="2026-02-03"
        )
        assert result is None

    @patch("engines.earnings.yf")
    def test_get_next_earnings_success(self, mock_yf):
        """Returns earnings dict for a ticker."""
        mock_ticker = MagicMock()
        mock_ticker.calendar = {
            "Earnings Date": datetime(2026, 1, 30),
            "EPS Estimate": 1.50,
        }
        mock_yf.Ticker.return_value = mock_ticker

        result = EarningsCalendarEngine.get_next_earnings("AAPL")
        assert result is not None
        assert "Earnings Date" in result
        assert result["EPS Estimate"] == 1.50

    @patch("engines.earnings.yf")
    def test_get_next_earnings_none_calendar(self, mock_yf):
        """Returns None when calendar is None."""
        mock_ticker = MagicMock()
        mock_ticker.calendar = None
        mock_yf.Ticker.return_value = mock_ticker

        result = EarningsCalendarEngine.get_next_earnings("AAPL")
        assert result is None

    @patch("engines.earnings.yf")
    def test_get_next_earnings_empty_df(self, mock_yf):
        """Returns None when calendar is empty DataFrame."""
        mock_ticker = MagicMock()
        mock_ticker.calendar = pd.DataFrame()
        mock_yf.Ticker.return_value = mock_ticker

        result = EarningsCalendarEngine.get_next_earnings("AAPL")
        assert result is None

    @patch("engines.earnings.yf")
    def test_get_earnings_dates_success(self, mock_yf):
        """Returns DataFrame of earnings dates."""
        mock_ticker = MagicMock()
        expected_df = pd.DataFrame({
            "EPS Estimate": [1.50, 1.40],
            "Reported EPS": [1.55, 1.35],
        })
        mock_ticker.get_earnings_dates.return_value = expected_df
        mock_yf.Ticker.return_value = mock_ticker

        result = EarningsCalendarEngine.get_earnings_dates("AAPL", limit=2)
        assert result is not None
        assert len(result) == 2

    @patch("engines.earnings.yf")
    def test_get_earnings_dates_exception(self, mock_yf):
        """Returns None on exception."""
        mock_yf.Ticker.side_effect = Exception("API error")

        result = EarningsCalendarEngine.get_earnings_dates("AAPL")
        assert result is None

    @patch.object(EarningsCalendarEngine, "get_market_earnings")
    def test_filter_earnings_this_week_found(self, mock_market):
        """Returns matching tickers reporting this week."""
        mock_market.return_value = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT", "GOOGL"],
            "Earnings Date": ["2026-01-30", "2026-01-29", "2026-01-31"],
            "EPS Estimate": [1.50, 2.00, 1.80],
            "Reported EPS": [None, None, None],
            "Surprise(%)": [None, None, None],
        })

        result = EarningsCalendarEngine.filter_earnings_this_week(
            ["AAPL", "TSLA"], days_ahead=7
        )
        assert len(result) == 1
        assert result[0]["ticker"] == "AAPL"

    @patch.object(EarningsCalendarEngine, "get_market_earnings")
    def test_filter_earnings_this_week_empty(self, mock_market):
        """Returns empty list when no matches."""
        mock_market.return_value = pd.DataFrame({
            "Symbol": ["AAPL"],
            "Earnings Date": ["2026-01-30"],
            "EPS Estimate": [1.50],
            "Reported EPS": [None],
            "Surprise(%)": [None],
        })

        result = EarningsCalendarEngine.filter_earnings_this_week(
            ["TSLA", "NVDA"], days_ahead=7
        )
        assert len(result) == 0

    @patch.object(EarningsCalendarEngine, "get_market_earnings")
    @patch.object(EarningsCalendarEngine, "get_next_earnings")
    def test_build_earnings_map_bulk(self, mock_next, mock_market):
        """Builds map from bulk query without per-ticker fallback."""
        mock_market.return_value = pd.DataFrame({
            "Symbol": ["AAPL", "MSFT"],
            "Earnings Date": [
                datetime(2026, 1, 30),
                datetime(2026, 1, 29),
            ],
        })
        mock_next.return_value = None  # Should not be called

        result = EarningsCalendarEngine.build_earnings_map(
            ["AAPL", "MSFT"], days_ahead=14
        )
        assert "AAPL" in result
        assert "MSFT" in result
        mock_next.assert_not_called()

    @patch.object(EarningsCalendarEngine, "get_market_earnings")
    @patch.object(EarningsCalendarEngine, "get_next_earnings")
    def test_build_earnings_map_fallback(self, mock_next, mock_market):
        """Falls back to per-ticker for missing ones."""
        mock_market.return_value = pd.DataFrame({
            "Symbol": ["AAPL"],
            "Earnings Date": [datetime(2026, 1, 30)],
        })
        mock_next.return_value = {
            "Earnings Date": datetime(2026, 1, 29),
            "EPS Estimate": 2.00,
        }

        result = EarningsCalendarEngine.build_earnings_map(
            ["AAPL", "MSFT"], days_ahead=14
        )
        assert "AAPL" in result
        assert "MSFT" in result
        mock_next.assert_called_once_with("MSFT")

    @patch.object(EarningsCalendarEngine, "get_market_earnings")
    @patch.object(EarningsCalendarEngine, "get_next_earnings")
    def test_build_earnings_map_exception(self, mock_next, mock_market):
        """Returns empty dict on exception (both bulk and per-ticker fail)."""
        mock_market.side_effect = Exception("API error")
        mock_next.side_effect = Exception("API error")

        result = EarningsCalendarEngine.build_earnings_map(
            ["AAPL"], days_ahead=14
        )
        assert result == {}


# ---------------------------------------------------------------------------
# EarningsFilter tests
# ---------------------------------------------------------------------------

class TestEarningsFilter:
    """Tests for the EarningsFilter class."""

    def test_filter_stage(self):
        """EarningsFilter operates at universe stage."""
        f = EarningsFilter(exclude_days_before=7)
        assert f.stage == STAGE_UNIVERSE

    def test_filter_name(self):
        """EarningsFilter has correct name."""
        f = EarningsFilter(exclude_days_before=7)
        assert f.name == "earnings"

    def test_no_modes_passes(self):
        """With no modes set, filter passes everything."""
        f = EarningsFilter()
        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is True

    def test_exclude_within_window_rejects(self):
        """Rejects tickers with earnings within exclude window."""
        now = datetime.now()
        earnings_date = now + timedelta(days=3)

        f = EarningsFilter(exclude_days_before=7)
        f.set_earnings_map({"AAPL": earnings_date})

        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is False
        assert "excluded" in result.reason

    def test_exclude_outside_window_passes(self):
        """Passes tickers with earnings outside exclude window."""
        now = datetime.now()
        earnings_date = now + timedelta(days=14)

        f = EarningsFilter(exclude_days_before=7)
        f.set_earnings_map({"AAPL": earnings_date})

        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is True

    def test_include_within_window_passes(self):
        """Passes tickers with earnings within include window."""
        now = datetime.now()
        earnings_date = now + timedelta(days=3)

        f = EarningsFilter(include_days_ahead=7)
        f.set_earnings_map({"AAPL": earnings_date})

        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is True

    def test_include_outside_window_rejects(self):
        """Rejects tickers with earnings outside include window."""
        now = datetime.now()
        earnings_date = now + timedelta(days=14)

        f = EarningsFilter(include_days_ahead=7)
        f.set_earnings_map({"AAPL": earnings_date})

        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is False
        assert "not within" in result.reason

    def test_missing_earnings_data_passes(self):
        """Default-permissive: no earnings data = pass."""
        f = EarningsFilter(exclude_days_before=7)
        ctx = FilterContext(ticker="UNKNOWN")
        result = f.check(ctx)
        assert result.passed is True

    def test_string_date_parsed(self):
        """Correctly parses string earnings dates."""
        earnings_date = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")

        f = EarningsFilter(exclude_days_before=7)
        f.set_earnings_map({"AAPL": earnings_date})

        ctx = FilterContext(ticker="AAPL")
        result = f.check(ctx)
        assert result.passed is False

    def test_set_earnings_map(self):
        """set_earnings_map updates internal state."""
        f = EarningsFilter(exclude_days_before=7)
        assert f._earnings_map == {}

        earnings_map = {"AAPL": datetime.now() + timedelta(days=1)}
        f.set_earnings_map(earnings_map)
        assert f._earnings_map == earnings_map


# ---------------------------------------------------------------------------
# Config validation tests
# ---------------------------------------------------------------------------

class TestEarningsFilterConfig:
    """Tests for EarningsFilterConfig Pydantic model."""

    def test_defaults(self):
        """Default values are None."""
        from sentinel.config import EarningsFilterConfig
        cfg = EarningsFilterConfig()
        assert cfg.exclude_days_before is None
        assert cfg.include_days_ahead is None

    def test_exclude_days_before_valid(self):
        """Valid exclude_days_before is accepted."""
        from sentinel.config import EarningsFilterConfig
        cfg = EarningsFilterConfig(exclude_days_before=7)
        assert cfg.exclude_days_before == 7

    def test_include_days_ahead_valid(self):
        """Valid include_days_ahead is accepted."""
        from sentinel.config import EarningsFilterConfig
        cfg = EarningsFilterConfig(include_days_ahead=3)
        assert cfg.include_days_ahead == 3

    def test_both_modes_rejected(self):
        """Cannot set both exclude and include modes."""
        from sentinel.config import EarningsFilterConfig
        with pytest.raises(ValueError, match="cannot both be set"):
            EarningsFilterConfig(
                exclude_days_before=7,
                include_days_ahead=3,
            )

    def test_exclude_days_before_min(self):
        """exclude_days_before must be >= 1."""
        from sentinel.config import EarningsFilterConfig
        with pytest.raises(ValueError):
            EarningsFilterConfig(exclude_days_before=0)

    def test_exclude_days_before_max(self):
        """exclude_days_before must be <= 30."""
        from sentinel.config import EarningsFilterConfig
        with pytest.raises(ValueError):
            EarningsFilterConfig(exclude_days_before=31)


__all__ = [
    "TestEarningsCalendarEngine",
    "TestEarningsFilter",
    "TestEarningsFilterConfig",
]
