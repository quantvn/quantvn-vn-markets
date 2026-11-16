"""Forex: the 28 pairs of USD, EUR, GBP, JPY, CHF, AUD, CAD, NZD, plus XAUUSD and XAGUSD.

Bars come from the QuantVN market-data API (dataset ``forex``): HistData 1-minute BID bars, and for the weeks
HistData has not published yet, live mid quotes (TradingView FX_IDC; Yahoo for older gaps of pairs). The
same prices, the same per-pair spread (``HALF_SPREAD_BP``) and the same swap rule are used by the QuantVN
Track Record service for ``FOREX`` paper trades.

    from quantvn.fx import data
    df = data.get_hist("EURUSD", "15m", "2026-10-01", "2026-11-01")
    swap = data.swap_schedule("EURUSD", "2026-10-01", "2026-11-01", rates={"EUR": 2.65, "USD": 4.0})
    quantvn.paper.simulate(df.assign(position=...), market="FOREX", symbol="EURUSD", funding=swap)
"""
from __future__ import annotations

import datetime as dt
import time
from typing import Optional
from zoneinfo import ZoneInfo

import pandas as pd

from quantvn import marketdata

__all__ = ["HALF_SPREAD_BP", "PAIRS", "get_hist", "list_symbols", "swap_schedule"]

# Half the bid-ask spread per side, bp: HistData tick data 2019 and 2023, the larger year (Track Record engine/fx.py).
HALF_SPREAD_BP = {
    "EURUSD": 0.15, "GBPUSD": 0.40, "USDJPY": 0.25, "USDCHF": 0.60, "AUDUSD": 0.80, "USDCAD": 0.50, "NZDUSD": 0.95,
    "EURJPY": 0.40, "EURGBP": 0.60, "EURCHF": 0.65, "EURAUD": 0.80, "EURCAD": 0.70, "EURNZD": 0.90, "GBPJPY": 0.70,
    "GBPCHF": 0.90, "GBPAUD": 0.85, "GBPCAD": 1.00, "GBPNZD": 1.10, "AUDJPY": 0.55, "AUDCAD": 1.15, "AUDCHF": 1.25,
    "AUDNZD": 1.00, "CADJPY": 0.60, "CADCHF": 1.15, "CHFJPY": 0.70, "NZDJPY": 0.65, "NZDCAD": 1.40, "NZDCHF": 1.70,
    "XAUUSD": 1.15, "XAGUSD": 7.45,
}
PAIRS = tuple(HALF_SPREAD_BP)
METALS = ("XAU", "XAG")
RESOLUTIONS = {"1m", "5m", "15m", "30m", "1h", "4h", "1d"}
_NY = ZoneInfo("America/New_York")


def get_hist(symbol: str, resolution: str = "1m", start=None, end=None, tz: Optional[str] = None) -> pd.DataFrame:
    """
    Historical bars of a currency pair, gold or silver.

    Parameters
    ----------
    symbol : str
        "EURUSD", "USDJPY", "XAUUSD", ... (``PAIRS``). "EUR/USD" is accepted.
    resolution : str
        "1m", "5m", "15m", "30m", "1h", "4h" or "1d". Aggregated bars are built from 1-minute bars on UTC
        boundaries (a "1d" bar is a UTC day, not the 17:00 New York forex day).
    start, end : date, datetime or epoch ms, optional
        The window, end exclusive; a value without a time zone is UTC. Default: the 30 days before now.
    tz : str or None
        Time zone of the Datetime column (default None = UTC).

    Returns
    -------
    pd.DataFrame
        [Datetime, Date, time, Open, High, Low, Close, volume]. Datetime is the bar's OPEN time. volume is NaN:
        spot forex has no consolidated volume. Prices are bid up to HistData's last published month, mid after.
    """
    res = str(resolution).lower().strip()
    if res not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of: {', '.join(sorted(RESOLUTIONS))}.")
    sym = str(symbol).upper().replace("/", "").strip()
    end_ms = marketdata.to_ms(end, int(time.time() * 1000))
    start_ms = marketdata.to_ms(start, end_ms - 30 * 86_400_000)
    return marketdata.to_candles(marketdata.bars("forex", sym, start_ms, end_ms, res), tz)


def list_symbols() -> list:
    """Symbols the QuantVN API stores for forex."""
    return marketdata.symbols("forex")


def swap_schedule(symbol: str, start, end, rates: dict) -> pd.DataFrame:
    """Overnight swap of a forex position as the Track Record service charges it, for ``paper.simulate(...,
    funding=)``: one row per rollover at 17:00 New York, Monday to Friday, with start <= time < end.

    ``rates``: annual interest rate in percent per currency, e.g. ``{"EUR": 2.65, "USD": 4.0}`` (the service
    uses the central banks' policy rates, held constant between changes). Gold and silver earn no rate.

    Returns ``Datetime`` (UTC) and ``rate``: what a LONG position pays at that rollover, as a fraction of its
    size, ``(r_quote - r_base) / 100 / 365`` per day; Wednesday's rollover counts three days. Negative = the long
    receives. A short receives what a long pays.
    """
    sym = str(symbol).upper().replace("/", "").strip()
    base, quote = sym[:3], sym[3:6]
    r_base = 0.0 if base in METALS else float(rates[base])
    r_quote = float(rates[quote])
    a, b = marketdata.to_ms(start), marketdata.to_ms(end)
    d = dt.datetime.fromtimestamp(a / 1000, _NY).date() - dt.timedelta(days=1)
    last = dt.datetime.fromtimestamp(b / 1000, _NY).date()
    rows = []
    while d <= last:
        if d.weekday() < 5:
            t = dt.datetime(d.year, d.month, d.day, 17, 0, tzinfo=_NY)
            ms = int(t.timestamp() * 1000)
            if a <= ms < b:
                days = 3 if d.weekday() == 2 else 1
                rows.append((pd.Timestamp(ms, unit="ms", tz="UTC"), (r_quote - r_base) / 100 / 365 * days))
        d += dt.timedelta(days=1)
    return pd.DataFrame(rows, columns=["Datetime", "rate"])
