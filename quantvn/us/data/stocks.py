"""US stocks and ETFs: 1-minute bars of the regular session and daily bars.

From 0.3 the bars come from the QuantVN market-data API (S&P 500 members and the main ETFs). Called as
before, ``get_hist(symbol)`` with no window still reads the QuantVN data service it used until 0.2 (needs the
API key set with ``quantvn.client``).
"""
from __future__ import annotations

import io
from typing import Optional

import pandas as pd
import requests

from quantvn import marketdata
from quantvn.vn.data.utils import Config

__all__ = ["get_hist", "list_symbols"]

_TIMEOUT = 60
RESOLUTIONS = {"1m", "5m", "15m", "30m", "1h", "1d"}


def get_hist(symbol: str, resolution: str = "1m", start=None, end=None,
             tz: Optional[str] = "America/New_York") -> pd.DataFrame:
    """
    Historical bars of a US stock or ETF.

    Parameters
    ----------
    symbol : str
        US ticker, e.g. "AAPL", "MSFT", "SPY". Class shares with a dot: "BRK.B".
    resolution : str
        "1m", "5m", "15m", "30m", "1h" (regular session, 09:30-16:00 New York) or "1d" (daily, with adj_close).
    start, end : date, datetime or epoch ms, optional
        The window, end exclusive; a value without a time zone is UTC. With a window (or any resolution other
        than "1m") the QuantVN market-data API is used. Default end: now; default start: 30 days before end
        for intraday bars, 1990-01-01 for daily bars.
    tz : str or None
        Time zone of the Datetime column (default New York; None = UTC).

    Returns
    -------
    pd.DataFrame
        [Datetime, Date, time, Open, High, Low, Close, volume] (+ adj_close for daily bars). Datetime is the
        bar's OPEN time.
    """
    res = str(resolution).lower().strip()
    if res not in RESOLUTIONS:
        raise ValueError(f"resolution must be one of: {', '.join(sorted(RESOLUTIONS))}.")
    sym = str(symbol).upper().strip()
    if start is None and end is None and res == "1m":
        return _legacy(sym)
    end_ms = marketdata.to_ms(end, None)
    if end_ms is None:
        import time
        end_ms = int(time.time() * 1000)
    if res == "1d":
        start_ms = marketdata.to_ms(start, marketdata.to_ms("1990-01-01"))
        df = marketdata.bars("us_stock_1d", sym, start_ms, end_ms, "1d")
    else:
        start_ms = marketdata.to_ms(start, end_ms - 30 * 86_400_000)
        df = marketdata.bars("us_stock", sym, start_ms, end_ms, res)
    return marketdata.to_candles(df, tz)


def list_symbols(daily: bool = False) -> list:
    """Symbols the QuantVN API stores: 1-minute (default) or daily."""
    return marketdata.symbols("us_stock_1d" if daily else "us_stock")


def _legacy(sym: str) -> pd.DataFrame:
    """The 0.2 behaviour: the whole 1-minute history of the QuantVN data service (needs the API key)."""
    api_key = Config.get_api_key()
    response = requests.post(
        f"{Config.get_link_us_stock_url()}/us/stock/historical",
        json={"symbol": sym, "interval": "1m"},
        headers={"x-api-key": api_key},
        timeout=_TIMEOUT,
    )
    if response.status_code == 200:
        body = response.json()
        if "error" in body:
            raise Exception(f"API error: {body['error']}")
        raw = requests.get(body.get("url", ""), timeout=_TIMEOUT).content
        return pd.read_parquet(io.BytesIO(raw))
    raise Exception(f"Error: {response.status_code}, {response.text}")
