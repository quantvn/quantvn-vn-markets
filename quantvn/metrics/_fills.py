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


# Costs of the Vietnamese markets, the same values the QuantVN Track Record service charges.
# VN30 futures, per side, as a fraction of the contract's value: exchange fee 2,700 VND, clearing fee
# 2,550 VND and personal income tax of 0.1% on half the initial margin come to about 1.1 bp at an index of
# 1,850; the rest is an allowance for broker commission and half a price step of spread.
VN_FUTURES_FEE = 1.5e-4
# Vietnamese stocks: a typical retail commission per side, the 0.1% tax on every sale, and half of one
# price step for the bid-ask spread.
VN_STOCK_FEE = 15e-4
VN_STOCK_SELL_TAX = 10e-4


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
