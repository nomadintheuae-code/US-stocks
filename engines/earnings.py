"""Earnings calendar integration for SENTINEL PRO.

Provides market-wide and per-ticker earnings date lookups via yfinance.
Uses ``yf.Calendars`` for bulk date-range queries and ``Ticker.calendar``
for reliable per-ticker future-date lookups.

This module is additive and opt-in: it does NOT alter sentinel.py behavior
unless a caller explicitly uses its APIs.
"""
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


class EarningsCalendarEngine:
    """Fetch market-wide and per-ticker earnings calendar data via yfinance."""

    @staticmethod
    def get_market_earnings(
        start: Optional[str] = None,
        end: Optional[str] = None,
        market_cap: Optional[float] = None,
        limit: int = 100,
        filter_most_active: bool = False,
    ) -> Optional[pd.DataFrame]:
        """Get all US earnings reports in a date range.

        Parameters
        ----------
        start : str, optional
            Start date ``YYYY-MM-DD`` (default: today).
        end : str, optional
            End date ``YYYY-MM-DD`` (default: start + 7 days).
        market_cap : float, optional
            Minimum market cap in USD to filter.
        limit : int
            Max results (Yahoo caps at 100).
        filter_most_active : bool
            If True, only actively traded stocks.

        Returns
        -------
        DataFrame or None
            Columns include Symbol, Company, Earnings Date, EPS Estimate,
            Reported EPS, Surprise(%).  Returns None on failure.
        """
        if start is None:
            start = datetime.now().strftime("%Y-%m-%d")
        if end is None:
            start_dt = datetime.strptime(start, "%Y-%m-%d")
            end = (start_dt + timedelta(days=7)).strftime("%Y-%m-%d")

        try:
            cal = yf.Calendars(start=start, end=end)
            df = cal.get_earnings_calendar(
                market_cap=market_cap,
                filter_most_active=filter_most_active,
                limit=limit,
            )
            if df is None or df.empty:
                return None
            return df
        except Exception as exc:
            logger.warning("Failed to fetch market earnings calendar: %s", exc)
            return None

    @staticmethod
    def get_next_earnings(ticker: str) -> Optional[Dict]:
        """Get the next earnings date for a single ticker.

        Uses ``Ticker.calendar`` which reliably returns future dates
        (workaround for ``get_earnings_dates()`` future-date bug).

        Returns
        -------
        dict or None
            Dict with keys like 'Earnings Date', 'EPS Estimate',
            'Revenue Estimate', or None if unavailable.
        """
        try:
            cal = yf.Ticker(ticker).calendar
            if cal is None:
                return None
            if isinstance(cal, pd.DataFrame):
                if cal.empty:
                    return None
                return cal.to_dict()
            if isinstance(cal, dict):
                return cal if cal else None
            return None
        except Exception as exc:
            logger.warning("Failed to get earnings for %s: %s", ticker, exc)
            return None

    @staticmethod
    def get_earnings_dates(
        ticker: str, limit: int = 12
    ) -> Optional[pd.DataFrame]:
        """Get historical + upcoming earnings dates for a ticker.

        Returns DataFrame with EPS Estimate, Reported EPS, Surprise(%).
        NOTE: May not include future dates due to Yahoo Finance API issues.
        Use ``get_next_earnings()`` for reliable future-date lookup.

        Parameters
        ----------
        ticker : str
            Stock ticker symbol.
        limit : int
            Number of earnings dates to retrieve.

        Returns
        -------
        DataFrame or None
        """
        try:
            return yf.Ticker(ticker).get_earnings_dates(limit=limit)
        except Exception as exc:
            logger.warning("Failed to get earnings dates for %s: %s", ticker, exc)
            return None

    @classmethod
    def filter_earnings_this_week(
        cls,
        ticker_list: List[str],
        days_ahead: int = 7,
    ) -> List[Dict]:
        """Check which tickers from a list report earnings within N days.

        Parameters
        ----------
        ticker_list : list of str
            Ticker symbols to check.
        days_ahead : int
            Number of days to look ahead.

        Returns
        -------
        list of dict
            Each dict has keys: ticker, earnings_date, eps_estimate.
        """
        today = datetime.now().date()
        end = today + timedelta(days=days_ahead)

        try:
            market_earnings = cls.get_market_earnings(
                start=today.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                limit=100,
                filter_most_active=False,
            )
        except Exception as exc:
            logger.warning("Failed to fetch market earnings for filter: %s", exc)
            return []

        if market_earnings is None or market_earnings.empty:
            return []

        ticker_set = set(t.upper() for t in ticker_list)
        results: List[Dict] = []

        for _, row in market_earnings.iterrows():
            symbol = str(row.get("Symbol", "")).upper()
            if symbol in ticker_set:
                results.append({
                    "ticker": symbol,
                    "earnings_date": row.get("Earnings Date"),
                    "eps_estimate": row.get("EPS Estimate"),
                    "reported_eps": row.get("Reported EPS"),
                    "surprise_pct": row.get("Surprise(%)"),
                })

        return results

    @classmethod
    def build_earnings_map(
        cls,
        ticker_list: List[str],
        days_ahead: int = 14,
    ) -> Dict[str, datetime]:
        """Build a mapping of ticker -> next earnings date.

        Fetches market-wide earnings for the next ``days_ahead`` days,
        then fills in any missing tickers with per-ticker lookups.

        Parameters
        ----------
        ticker_list : list of str
            Ticker symbols to map.
        days_ahead : int
            Days to look ahead for market-wide query.

        Returns
        -------
        dict
            ``{ticker: earnings_datetime}`` for tickers with known dates.
        """
        earnings_map: Dict[str, datetime] = {}
        today = datetime.now().date()
        end = today + timedelta(days=days_ahead)

        # Bulk query first
        try:
            market = cls.get_market_earnings(
                start=today.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                limit=100,
            )
            if market is not None and not market.empty:
                ticker_upper_set = {t.upper() for t in ticker_list}
                for _, row in market.iterrows():
                    sym = str(row.get("Symbol", "")).upper()
                    if sym in ticker_upper_set:
                        ed = row.get("Earnings Date")
                        if isinstance(ed, list):
                            ed = ed[0] if ed else None
                        if ed is not None:
                            earnings_map[sym] = ed
        except Exception as exc:
            logger.debug("Bulk earnings query failed: %s", exc)

        # Per-ticker fallback for missing ones (cap at 20 to avoid throttle)
        missing = [
            t for t in ticker_list
            if t.upper() not in earnings_map
        ][:20]

        for ticker in missing:
            try:
                info = cls.get_next_earnings(ticker)
                if info and "Earnings Date" in info:
                    ed = info["Earnings Date"]
                    if isinstance(ed, list):
                        ed = ed[0] if ed else None
                    if ed is not None:
                        earnings_map[ticker.upper()] = ed
            except Exception as exc:
                logger.debug("Per-ticker earnings lookup failed for %s: %s", ticker, exc)

        return earnings_map


__all__ = ["EarningsCalendarEngine"]
