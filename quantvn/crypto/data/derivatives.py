"""Crypto prices: Binance spot and USD-M perpetual futures, and perpetual funding rates.

Data come from the QuantVN market-data API (the store QuantVN uses for paper trading, refreshed every 10
minutes) or, when it cannot be reached or the interval is one it does not serve, straight from Binance's
public archive and REST API. Both give Binance's own record of its market.
"""
from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd
import requests

from quantvn import marketdata
from quantvn.crypto.data.download import VALID_INTERVALS, download_monthly, extract_csv

__all__ = ["get_hist", "get_funding_rates", "list_symbols"]

VN_TZ = timezone(timedelta(hours=7))
COLUMNS = ["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]
# The window get_hist returned before 0.3, and still returns when no start or end is given.
LEGACY_START = datetime(2019, 7, 1, tzinfo=VN_TZ)
LEGACY_END = datetime(2022, 12, 31, 23, 59, 59, tzinfo=VN_TZ)
_MARKETS = {"spot": "crypto_spot", "perp": "crypto_perp"}
_REST = {"spot": "https://api.binance.com/api/v3/klines", "perp": "https://fapi.binance.com/fapi/v1/klines"}
_INTERVAL_MS = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000,
                "2h": 7_200_000, "4h": 14_400_000, "6h": 21_600_000, "8h": 28_800_000, "12h": 43_200_000,
                "1d": 86_400_000, "3d": 259_200_000, "1w": 604_800_000}


def get_hist(
    symbol: str,
    interval: str = "1m",
    cache_dir: Optional[Union[str, Path]] = None,
    start=None,
    end=None,
    market: str = "spot",
    tz: Optional[str] = "Asia/Ho_Chi_Minh",
    source: str = "auto",
) -> pd.DataFrame:
    """Historical OHLCV bars of a Binance pair.

    Args:
        symbol:    Binance symbol, e.g. "BTCUSDT".
        interval:  1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M.
        cache_dir: where monthly archives are kept when they are downloaded from Binance (default ~/.cache/quantvn).
        start, end: the window (dates, datetimes or epoch ms; end exclusive; without a time zone = UTC).
                   When both are omitted the window is 2019-07-01 to 2022-12-31 (Vietnam time), as before 0.3.
                   When only end is omitted it is now.
        market:    "spot" or "perp" (USD-M perpetual futures, last price).
        tz:        time zone of the Datetime column (default Vietnam time, as before; None = UTC).
        source:    "auto" (QuantVN API, falling back to Binance), "quantvn" or "binance".

    Returns:
        DataFrame [Datetime, Date, time, Open, High, Low, Close, volume]; Datetime is the bar's OPEN time.
        Only bars that have closed are returned.
    """
    if interval not in VALID_INTERVALS:
        raise ValueError(f"Invalid interval {interval!r}. Choose one of: {', '.join(sorted(VALID_INTERVALS))}")
    if market not in _MARKETS:
        raise ValueError("market must be 'spot' or 'perp'")
    if source not in ("auto", "quantvn", "binance"):
        raise ValueError("source must be 'auto', 'quantvn' or 'binance'")
    symbol = symbol.upper().strip()
    now = int(time.time() * 1000)
    if start is None and end is None:
        start_ms, end_ms = int(LEGACY_START.timestamp() * 1000), int(LEGACY_END.timestamp() * 1000) + 1000
    else:
        end_ms = marketdata.to_ms(end, now)
        start_ms = marketdata.to_ms(start, int(LEGACY_START.timestamp() * 1000))
    if start_ms >= end_ms:
        raise ValueError("start must be before end")

    if source != "binance" and interval in marketdata.INTERVALS:
        try:
            df = marketdata.bars(_MARKETS[market], symbol, start_ms, end_ms, interval)
            return marketdata.to_candles(df, tz)
        except (requests.RequestException, marketdata.MarketDataError) as e:
            if source == "quantvn" or (isinstance(e, marketdata.MarketDataError) and e.code in ("invalid_time",)):
                raise
    elif source == "quantvn":
        raise ValueError(f"the QuantVN API serves {', '.join(marketdata.INTERVALS)}; use source='binance' for {interval}")
    return _from_binance(symbol, interval, start_ms, min(end_ms, now), market, cache_dir, tz)


def _from_binance(symbol, interval, start_ms, end_ms, market, cache_dir, tz) -> pd.DataFrame:
    cache = Path(cache_dir or Path.home() / ".cache/quantvn")
    first = datetime.fromtimestamp(start_ms / 1000, timezone.utc).replace(day=1, hour=0, minute=0, second=0,
                                                                          microsecond=0)
    last = datetime.fromtimestamp((end_ms - 1) / 1000, timezone.utc)
    this_month = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    months, m = [], first
    while m <= last and m < this_month:
        months.append(m.strftime("%Y-%m"))
        m = m.replace(year=m.year + (m.month == 12), month=m.month % 12 + 1)

    results = {}

    def fetch(month):
        return month, extract_csv(download_monthly(symbol, interval, month, cache, market))

    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch, mo): mo for mo in months}
        for fut in as_completed(futures):
            try:
                mo, df = fut.result()
                results[mo] = df
            except Exception as e:                  # a month Binance has not archived: the REST API covers it
                print(f"Skip {symbol} {interval} {futures[fut]}: {e}")
    parts = [results[mo] for mo in sorted(results)]
    covered = max((int(p["t"].max()) for p in parts if len(p)), default=start_ms - 1)
    if covered + 1 < end_ms and interval in _INTERVAL_MS:
        parts.append(_rest(symbol, interval, max(covered + 1, start_ms), end_ms, market))
    parts = [p for p in parts if len(p)]
    if not parts:
        return pd.DataFrame(columns=COLUMNS)
    df = pd.concat(parts, ignore_index=True).drop_duplicates("t").sort_values("t")
    step = _INTERVAL_MS.get(interval, 0)
    now = int(time.time() * 1000)
    df = df[(df["t"] >= start_ms) & (df["t"] < end_ms) & (df["t"] + step <= now)]
    df = df.rename(columns={"t": "ts", "Open": "open", "High": "high", "Low": "low", "Close": "close",
                            "Volume": "volume"})
    return marketdata.to_candles(df, tz)


def _rest(symbol, interval, start_ms, end_ms, market) -> pd.DataFrame:
    rows, a = [], start_ms
    limit = 1000
    while a < end_ms:
        r = requests.get(_REST[market], params={"symbol": symbol, "interval": interval, "startTime": a,
                                                "endTime": end_ms - 1, "limit": limit}, timeout=30)
        r.raise_for_status()
        d = r.json()
        if not d:
            break
        rows += [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])) for k in d]
        a = int(d[-1][0]) + _INTERVAL_MS[interval]
        if len(d) < limit:
            break
    return pd.DataFrame(rows, columns=["t", "Open", "High", "Low", "Close", "Volume"])


def get_funding_rates(symbol: str, start=None, end=None, source: str = "auto") -> pd.DataFrame:
    """Funding events of a Binance USD-M perpetual: columns Datetime (UTC), rate, mark_price.

    A long position pays ``rate x notional`` at each event (a short receives it). Default window: the last
    365 days. ``quantvn.paper.simulate(..., market="CRYPTO_PERP", funding=...)`` takes this frame."""
    symbol = symbol.upper().strip()
    now = int(time.time() * 1000)
    end_ms = marketdata.to_ms(end, now)
    start_ms = marketdata.to_ms(start, end_ms - 365 * 86_400_000)
    df = None
    if source != "binance":
        try:
            df = marketdata.funding(symbol, start_ms, end_ms)
        except (requests.RequestException, marketdata.MarketDataError):
            if source == "quantvn":
                raise
    if df is None:
        rows, a = [], start_ms
        while a < end_ms:
            r = requests.get("https://fapi.binance.com/fapi/v1/fundingRate",
                             params={"symbol": symbol, "startTime": a, "endTime": end_ms - 1, "limit": 1000}, timeout=30)
            r.raise_for_status()
            d = r.json()
            if not d:
                break
            rows += [(int(x["fundingTime"]) // 1000 * 1000, float(x["fundingRate"]),
                      float(x["markPrice"]) if x.get("markPrice") else float("nan")) for x in d]
            a = int(d[-1]["fundingTime"]) + 1
            if len(d) < 1000:
                break
        df = pd.DataFrame(rows, columns=["ts", "rate", "mark_price"])
    out = pd.DataFrame({"Datetime": pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True),
                        "rate": df["rate"].astype(float), "mark_price": df["mark_price"].astype(float)})
    return out.reset_index(drop=True)


def list_symbols(market: str = "spot") -> list:
    """Symbols the QuantVN API stores for a market: "spot", "perp" or "funding"."""
    return marketdata.symbols({"spot": "crypto_spot", "perp": "crypto_perp", "funding": "crypto_funding"}[market])
