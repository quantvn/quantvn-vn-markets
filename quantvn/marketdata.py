"""Client of the QuantVN market-data API (US stocks and ETFs, Binance crypto spot and perpetuals, funding).

The API serves the price store that QuantVN collects for paper trading: 1-minute bars labelled by their OPEN
time. No key is needed; with the API key of your QuantVN account (``quantvn.client(apikey=...)``) the limits
are higher. The address can be changed with the ``QUANTVN_DATA_URL`` environment variable or
``set_data_url``.

    from quantvn.marketdata import bars, symbols
    symbols("crypto_spot")[:5]
    bars("crypto_spot", "BTCUSDT", "2026-01-01", "2026-02-01", interval="1h")
"""
from __future__ import annotations

import io
import os
import time
from typing import Optional, Union

import pandas as pd
import requests

DEFAULT_URL = "https://desktop-0fv3bsf.taila5ef2b.ts.net/data/v1"
INTERVALS = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}
MAX_ROWS = 600_000
_url = os.environ.get("QUANTVN_DATA_URL", DEFAULT_URL).rstrip("/")
_session = requests.Session()
_session.headers["User-Agent"] = "quantvn-sdk"

TimeLike = Union[str, int, float, pd.Timestamp, None]


class MarketDataError(Exception):
    """The API refused a request. ``code`` is its error code (``unknown_symbol``, ``rate_limited``, ...)."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


def set_data_url(url: str) -> None:
    global _url
    _url = url.rstrip("/")


def data_url() -> str:
    return _url


def to_ms(t: TimeLike, default: Optional[int] = None) -> Optional[int]:
    """Epoch milliseconds from a date string, datetime, Timestamp or epoch seconds/milliseconds. A string or
    datetime without a time zone is read as UTC."""
    if t is None:
        return default
    if isinstance(t, (int, float)):
        return int(t * 1000) if abs(t) < 10 ** 11 else int(t)
    ts = pd.Timestamp(t)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    return int(ts.value // 1_000_000)


def _headers() -> dict:
    from quantvn.vn.data.utils import Config
    return {"X-API-Key": Config._api_key} if getattr(Config, "_api_key", None) else {}


def _get(path: str, params: dict, timeout: float = 120, tries: int = 6) -> requests.Response:
    for k in range(tries):
        r = _session.get(f"{_url}{path}", params=params, headers=_headers(), timeout=timeout)
        if r.status_code == 429 and k < tries - 1:
            time.sleep(min(float(r.headers.get("Retry-After", "2")), 60))
            continue
        if r.status_code >= 400:
            try:
                err = r.json().get("error", {})
            except ValueError:
                err = {}
            raise MarketDataError(r.status_code, err.get("code", "http_error"), err.get("message", r.text[:200]))
        return r
    raise MarketDataError(429, "rate_limited", "still rate limited after retries")


def datasets() -> dict:
    """What the API stores, with coverage and the current limits."""
    return _get("/datasets", {}).json()


def symbols(dataset: str) -> list:
    """Symbols of a dataset: crypto_spot, crypto_perp, crypto_funding, us_stock, us_stock_1d."""
    return [s["symbol"] for s in _get("/symbols", {"dataset": dataset}).json()["symbols"]]


def bars(dataset: str, symbol: str, start: TimeLike = None, end: TimeLike = None, interval: str = "1m") -> pd.DataFrame:
    """Bars with start <= open time < end: columns ts (open time, ms UTC), open, high, low, close, volume (and
    adj_close for daily US bars). Long windows are fetched in several requests."""
    if interval not in INTERVALS:
        raise ValueError(f"interval must be one of {', '.join(INTERVALS)}")
    now = int(time.time() * 1000)
    end_ms = to_ms(end, now)
    start_ms = to_ms(start, end_ms - 7 * 86_400_000)
    if dataset == "us_stock_1d":
        step = 100 * 365 * 86_400_000                         # one row per session: any window fits
    elif interval == "1m":
        step = int(MAX_ROWS * 0.9) * 60_000
    else:
        step = 365 * 86_400_000                               # the API aggregates at most 400 days per request
    parts, a, newest = [], start_ms, None
    while a < end_ms:
        b = min(a + step, end_ms)
        r = _get("/bars", {"dataset": dataset, "symbol": symbol, "start": a, "end": b, "interval": interval})
        parts.append(pd.read_parquet(io.BytesIO(r.content)))
        if r.headers.get("X-Newest", "").isdigit():
            newest = int(r.headers["X-Newest"])
        a = b
    parts = [p for p in parts if len(p)]
    if not parts:
        out = pd.DataFrame(columns=["ts", "open", "high", "low", "close", "volume"])
    else:
        out = pd.concat(parts, ignore_index=True).drop_duplicates("ts").sort_values("ts").reset_index(drop=True)
    out.attrs["newest"] = newest            # open time of the newest 1-minute bar stored for the symbol
    return out


def funding(symbol: str, start: TimeLike = None, end: TimeLike = None) -> pd.DataFrame:
    """Funding events of a Binance USD-M perpetual: ts (ms UTC), rate, mark_price (NaN where unknown)."""
    now = int(time.time() * 1000)
    end_ms = to_ms(end, now)
    start_ms = to_ms(start, end_ms - 365 * 86_400_000)
    r = _get("/funding", {"symbol": symbol, "start": start_ms, "end": end_ms})
    return pd.read_parquet(io.BytesIO(r.content))


def to_candles(df: pd.DataFrame, tz: Optional[str]) -> pd.DataFrame:
    """API bars in the library's candle layout: Datetime (open time, in `tz`; UTC when None), Date, time,
    Open, High, Low, Close, volume."""
    cols = ["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]
    if df is None or not len(df):
        return pd.DataFrame(columns=cols)
    t = pd.to_datetime(df["ts"].astype("int64"), unit="ms", utc=True)
    if tz:
        t = t.dt.tz_convert(tz)
    out = pd.DataFrame({"Datetime": t, "Date": t.dt.strftime("%Y-%m-%d"), "time": t.dt.strftime("%H:%M:%S"),
                        "Open": df["open"].astype(float), "High": df["high"].astype(float),
                        "Low": df["low"].astype(float), "Close": df["close"].astype(float),
                        "volume": df["volume"].astype(float)})
    if "adj_close" in df.columns:
        out["adj_close"] = df["adj_close"].astype(float)
    return out.reset_index(drop=True)
