"""The fill rule shared by every backtest class of the library (from version 0.2.0).

A position written on a bar is decided with that bar's close, so the earliest price at which it can be
traded is the OPEN of the next bar. Until 0.1.25 the backtests credited the position of a bar with the
move that started at that bar's own close: a price that had already printed when the decision existed.

`held_after_next_open(position)` is what is held after the trade at each bar: the position of the bar
before. `next_bar_pnl(held, fill, close)` is what each bar earns: the old holding from the previous close to
the fill price, then the new holding from the fill price to the close. `fill_price(df)` returns the Open
column; when a frame has no opens the fill is that bar's close, one whole bar after the decision, which is
later than a real fill and never earlier.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd


# --- Backtest classes: the itemised statutory costs, the same the QuantVN website charges in "Run test".
# Sources: HNX trading fee and VSDC position fee, Thong tu 101/2021/TT-BTC; derivative personal income tax,
# Thong tu 87/2026/TT-BTC Dieu 5; initial margin, VSDC appendix effective 2026-10-16.
VN_FUT_MULTIPLIER = 100_000          # VND per VN30 index point
HNX_FEE_VND = 2_700                  # per contract per matched side
VSDC_POSITION_FEE_VND = 2_550        # per contract per day, on positions open at the end of the day
DERIVATIVE_PIT_RATE = 0.001          # 0.1 % of the transfer price
VN30_INITIAL_MARGIN = 0.17           # transfer price = price x multiplier x contracts x initial margin / 2
STOCK_FEE_RATE = 0.001               # broker fee assumption on buys and sells (brokers differ)
STOCK_SELL_TAX_RATE = 0.001          # personal income tax on the value of a sale
STOCK_AFTERNOON_SELL_MINUTE = 13 * 60   # shares bought on T can be sold from 13:00 on T+2

# --- quantvn.paper.simulate: the flat rates of the QuantVN Track Record service (paper.quantvn.com).
# VN30 futures, per side: the statutory items above are about 1.1 bp of the contract's value at an index of
# 1,850; the rest is an allowance for broker commission and half a price step of spread.
VN_FUTURES_FEE = 1.5e-4
# Vietnamese stocks: a typical retail commission per side, the 0.1% tax on every sale, and half of one
# price step for the bid-ask spread.
VN_STOCK_FEE = 15e-4
VN_STOCK_SELL_TAX = 10e-4


def sellable(days_held: int, minute_of_day: int, min_hold_days: int) -> bool:
    """A stock lot settles on T+2: sellable on later days, or on day min_hold_days - 1 from 13:00."""
    return days_held >= min_hold_days or (days_held == min_hold_days - 1 and minute_of_day >= STOCK_AFTERNOON_SELL_MINUTE)


def derivative_costs(df: pd.DataFrame) -> None:
    """Add HNX fee, income tax and VSDC position fee (index points per contract) to a time-indexed futures
    frame that has `held` and `fill_price`. Contracts are traded when the holding changes, at the fill price;
    the position fee is on the holding at the end of each day, for every calendar day until the next
    trading day in the frame (1 on the last day)."""
    held = df["held"]
    traded = held.diff().abs().fillna(held.abs())
    df["transaction_fee"] = traded * HNX_FEE_VND / VN_FUT_MULTIPLIER
    df["tax"] = (traded * df["fill_price"] * VN30_INITIAL_MARGIN / 2 * DERIVATIVE_PIT_RATE).fillna(0.0)
    dates = pd.Series(df.index.date, index=df.index)
    df["date"] = dates.to_numpy()
    days = pd.Series(sorted(set(dates)))
    gaps = (pd.to_datetime(days.shift(-1)) - pd.to_datetime(days)).dt.days.fillna(1)
    held_days = dates.map(dict(zip(days, gaps)))
    last_bar = dates != dates.shift(-1)
    carried = held.shift().fillna(0.0)
    df["overnight"] = (carried != 0) & (dates != dates.shift())
    df["overnight_fee"] = (held.abs() * VSDC_POSITION_FEE_VND / VN_FUT_MULTIPLIER * held_days).where(last_bar, 0.0)
    df["total_fee"] = df["transaction_fee"] + df["tax"] + df["overnight_fee"]


def vn_tick(price: float, exchange: str = "HOSE") -> float:
    """Price step of a Vietnamese stock, in thousands of VND like the candles. HOSE: 10 VND below 10,000,
    50 VND below 50,000, 100 VND from 50,000. HNX and UPCoM: 100 VND."""
    if str(exchange).upper() != "HOSE":
        return 0.1
    return 0.01 if price < 10 else 0.05 if price < 50 else 0.1


def fill_price(df: pd.DataFrame, close: str = "Close") -> pd.Series:
    """The price at which a position decided on the previous bar is traded."""
    for name in ("Open", "open"):
        if name in df.columns:
            opens = pd.to_numeric(df[name], errors="coerce")
            return opens.where(opens.notna(), pd.to_numeric(df[close], errors="coerce"))
    warnings.warn("the frame has no Open column: positions are filled at the close of the bar after the decision "
                  "instead of at its open. Keep the Open column for a fill at the next open.", stacklevel=3)
    return pd.to_numeric(df[close], errors="coerce")


def held_after_next_open(position: pd.Series) -> pd.Series:
    """What is held after the trade at each bar when the position of bar t is traded at bar t + 1."""
    return pd.to_numeric(position, errors="coerce").shift(1).fillna(0.0)


def next_bar_pnl(held, fill, close) -> np.ndarray:
    """Profit of each bar in price units: the previous holding from the previous close to the fill price,
    then the current holding from the fill price to the close."""
    held = np.asarray(held, dtype=float)
    fill = np.asarray(fill, dtype=float)
    close = np.asarray(close, dtype=float)
    if not len(held):
        return np.zeros(0)
    before = np.r_[0.0, held[:-1]]
    prev_close = np.r_[fill[0], close[:-1]]
    return np.nan_to_num(before * (fill - prev_close) + held * (close - fill))
