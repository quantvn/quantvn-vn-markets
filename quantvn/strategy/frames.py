"""Candles in the layout a strategy receives on QuantVN, and the rules that decide what it receives.

On the platform a strategy is a function ``gen_position(df)``. Every time a bar of the strategy's
resolution closes, it is called with the bars of the previous trading day and of today, through the bar
that just closed, and the ``position`` it returns on the last row is the decision for that bar. The
functions here build exactly that frame, so a strategy can be tried on a laptop the way it will run.
"""
from __future__ import annotations

import datetime as dt
from typing import Optional

import pandas as pd
import requests

COLUMNS = ["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]
ENTRADE = "https://services.entrade.com.vn/chart-api/v2/ohlcs"
_RESOLUTIONS = {"1m": 1, "5m": 5, "15m": 15, 1: 1, 5: 5, 15: 15}
# Names the platform uses for "VN30F1M sampled every 5 / 15 minutes": the same instrument.
_FUTURE_ALIASES = {"VN30F1M": ("VN30F1M", 1), "VN30F5M": ("VN30F1M", 5), "VN30F15M": ("VN30F1M", 15)}


def resolution_of(symbol: str) -> int:
    """Minutes per bar the platform uses for an instrument: 1, 5 or 15 for the VN30F aliases, 5 for a stock."""
    return _FUTURE_ALIASES.get(str(symbol).upper(), (None, 5))[1]


def is_future(symbol: str) -> bool:
    return str(symbol).upper() in _FUTURE_ALIASES


def position_limits(symbol: str) -> tuple:
    """(lowest, highest) position that is recorded. Futures can be short; shares cannot."""
    return (-1.0, 1.0) if is_future(symbol) else (0.0, 1.0)


def to_weight(position: float, symbol: str) -> tuple:
    """The weight of equity recorded for a raw position, and whether it had to be clipped."""
    lo, hi = position_limits(symbol)
    p = float(position)
    return round(min(max(p, lo), hi), 4), not lo <= p <= hi


def candles(symbol: str, resolution=None, days: int = 6, end: Optional[dt.datetime] = None,
            timeout: float = 20) -> pd.DataFrame:
    """Recent bars of a Vietnamese instrument from the public source the platform itself uses.

    No API key is needed. ``resolution`` is "1m", "5m" or "15m"; by default the one the platform uses for
    the symbol. Labels (``Datetime``) are bar OPEN times in Vietnam time. The bar that is still forming
    is included, as the source returns it; `closed` removes it.
    """
    sym = str(symbol).upper()
    real, default_res = _FUTURE_ALIASES.get(sym, (sym, 5))
    res = _RESOLUTIONS.get(resolution, None) if resolution is not None else default_res
    if res is None:
        raise ValueError("resolution must be '1m', '5m' or '15m'")
    end = end or (dt.datetime.utcnow() + dt.timedelta(hours=7))
    to_ts = int((end - dt.timedelta(hours=7) - dt.datetime(1970, 1, 1)).total_seconds()) + 60
    kind = "derivative" if is_future(sym) else "stock"
    r = requests.get(f"{ENTRADE}/{kind}", params={"from": to_ts - days * 86400, "to": to_ts, "symbol": real,
                                                  "resolution": res}, timeout=timeout,
                     headers={"User-Agent": "quantvn-sdk", "Accept": "application/json"})
    r.raise_for_status()
    data = r.json()
    if not data.get("t"):
        return pd.DataFrame(columns=COLUMNS)
    t = pd.to_datetime(pd.Series(data["t"], dtype="int64") + 7 * 3600, unit="s")
    df = pd.DataFrame({"Datetime": t, "Date": t.dt.strftime("%Y-%m-%d"), "time": t.dt.strftime("%H:%M:%S"),
                       "Open": pd.Series(data["o"], dtype=float), "High": pd.Series(data["h"], dtype=float),
                       "Low": pd.Series(data["l"], dtype=float), "Close": pd.Series(data["c"], dtype=float),
                       "volume": pd.Series(data["v"], dtype=float)})
    return df.dropna(subset=["Close"]).drop_duplicates("Datetime").sort_values("Datetime").reset_index(drop=True)


def bar_end(label: pd.Timestamp, minutes: int) -> pd.Timestamp:
    """When the bar labelled `label` is complete. A bar cut short by the lunch break, the end of
    continuous trading or the closing auction is complete when that part of the session ends."""
    label = pd.Timestamp(label)
    day = label.normalize()
    hm = label.strftime("%H:%M")
    end = label + pd.Timedelta(minutes=minutes)
    if hm >= "14:45":
        return day + pd.Timedelta(hours=14, minutes=46)
    if hm >= "13:00":
        return min(end, day + pd.Timedelta(hours=14, minutes=30))
    return min(end, day + pd.Timedelta(hours=11, minutes=31))


def closed(bars: pd.DataFrame, minutes: int, now: Optional[dt.datetime] = None) -> pd.DataFrame:
    """Only the bars that are complete at `now` (Vietnam time; default: the current time)."""
    now = pd.Timestamp(now or (dt.datetime.utcnow() + dt.timedelta(hours=7)))
    keep = [bar_end(t, minutes) <= now for t in bars["Datetime"]]
    return bars[keep].reset_index(drop=True)


def live_frame(bars: pd.DataFrame, bar) -> pd.DataFrame:
    """What ``gen_position`` receives when the bar labelled `bar` has just closed: every bar of the previous
    trading day in `bars`, and the bars of that day through `bar`."""
    bar = pd.Timestamp(bar)
    day = bar.strftime("%Y-%m-%d")
    earlier = sorted(d for d in bars["Date"].unique() if d < day)
    keep = earlier[-1:] + [day]
    out = bars[bars["Date"].isin(keep) & (bars["Datetime"] <= bar)]
    return out[COLUMNS + [c for c in out.columns if c not in COLUMNS]].reset_index(drop=True)
