"""Paper trading that cannot flatter a strategy: the fill rule of the QuantVN Track Record service.

`simulate` prices a column of positions the way the Track Record engine does. A position decided on a bar is
known only when that bar has closed, so it is filled at the OPEN of a later bar, never at the close that
produced the decision. A bar earns ``w_before * (open / previous close - 1)``, the fill pays its costs,
then the bar earns ``w_after * (close / open - 1)``. Equity starts at 1 and compounds.

Compare with ``Backtest_Derivates`` / ``Backtest_Stock``, which credit the position of a bar with the move
from that bar's own close: a price that had already printed when the decision existed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import pandas as pd

# Costs per market as the Track Record service charges them (GET https://paper.quantvn.com/v1/assets).
# fee and sell_tax are fractions of the traded weight; spread_ticks is the bid-ask spread assumed, in price steps.
MARKETS = {
    "VN_DERIVATIVE": {"fee": 1.5e-4, "sell_tax": 0.0, "min_pos": -1.0, "max_pos": 1.0, "spread_ticks": 0.0},
    "VN_STOCK": {"fee": 15e-4, "sell_tax": 10e-4, "min_pos": 0.0, "max_pos": 1.0, "spread_ticks": 1.0},
    "CRYPTO": {"fee": 10e-4, "sell_tax": 0.0, "min_pos": 0.0, "max_pos": 1.0, "spread_ticks": 0.0},
}


def vn_tick(price: float, exchange: str = "HOSE") -> float:
    """Price step of a Vietnamese stock, in thousands of VND like the candles. HOSE: 10 VND below 10,000,
    50 VND below 50,000, 100 VND from 50,000. HNX and UPCoM: 100 VND."""
    if str(exchange).upper() != "HOSE":
        return 0.1
    return 0.01 if price < 10 else 0.05 if price < 50 else 0.1


@dataclass
class PaperResult:
    """``nav``: equity after each bar, indexed by bar time. ``fills``: one row per fill. ``daily``: return
    and closing equity per day. ``stats``: total_return, sharpe (daily, annualised with 252), max_drawdown,
    days, fills. ``notes``: what the simulation did not model."""
    nav: pd.Series
    fills: pd.DataFrame
    daily: pd.DataFrame
    stats: dict
    notes: List[str] = field(default_factory=list)

    def __repr__(self) -> str:
        s = self.stats
        sharpe = "n/a" if s["sharpe"] is None else f"{s['sharpe']:.2f}"
        text = (f"return {s['total_return'] * 100:+.2f}%  sharpe {sharpe}  max drawdown {s['max_drawdown'] * 100:.2f}%  "
                f"{s['fills']} fills over {s['days']} days")
        return "\n".join([text] + [f"  note: {n}" for n in self.notes])


def simulate(df: pd.DataFrame, market: str = "VN_DERIVATIVE", delay_bars: int = 1, fee: Optional[float] = None,
             sell_tax: Optional[float] = None, spread_ticks: Optional[float] = None,
             exchange: str = "HOSE") -> PaperResult:
    """Price the ``position`` column of `df` with the Track Record fill rule.

    `df` needs ``Datetime`` (bar open time), ``Open``, ``Close`` and ``position``, where the position on a
    row is the decision made with that bar's close. It is filled at the open of the bar `delay_bars` rows
    later: 1 is the earliest price that can exist after the decision; on the platform a 1-minute strategy
    is usually filled one bar later still, because computing and sending take part of the next minute, so
    try 2 as well. Positions are clipped to what the market records. Costs default to the service's.
    """
    if market not in MARKETS:
        raise ValueError(f"market must be one of {', '.join(MARKETS)}")
    if delay_bars < 1:
        raise ValueError("delay_bars must be at least 1: a position cannot be filled at a price older than itself")
    m = MARKETS[market]
    fee = m["fee"] if fee is None else fee
    sell_tax = m["sell_tax"] if sell_tax is None else sell_tax
    spread_ticks = m["spread_ticks"] if spread_ticks is None else spread_ticks
    d = df.sort_values("Datetime").reset_index(drop=True)
    ts = pd.to_datetime(d["Datetime"])
    op, cl = d["Open"].to_numpy(float), d["Close"].to_numpy(float)
    raw = pd.to_numeric(d["position"], errors="coerce").ffill().fillna(0.0).to_numpy(float)
    target = np.clip(raw, m["min_pos"], m["max_pos"]).round(4)
    n = len(d)
    nav, w, prev = 1.0, 0.0, None
    navs, fills = np.empty(n), []
    for k in range(n):
        new = target[k - delay_bars] if k >= delay_bars else 0.0      # the decision that has reached the market
        if prev is None:
            prev = op[k]
        nav *= 1 + w * (op[k] / prev - 1)
        if new != w:
            dw = abs(new - w)
            cost = dw * fee + max(max(w, 0.0) - max(new, 0.0), 0.0) * sell_tax
            if spread_ticks:
                cost += dw * spread_ticks * (vn_tick(op[k], exchange) if market == "VN_STOCK" else 0.0) / 2 / op[k]
            nav *= 1 - cost
            fills.append((ts.iloc[k], op[k], w, new, cost))
            w = new
        nav *= 1 + w * (cl[k] / op[k] - 1)
        prev = cl[k]
        navs[k] = nav
    nav_s = pd.Series(navs, index=ts, name="nav")
    day_nav = nav_s.groupby(ts.dt.strftime("%Y-%m-%d").to_numpy()).last()
    day_ret = day_nav / day_nav.shift(1).fillna(1.0) - 1
    daily = pd.DataFrame({"return": day_ret, "nav": day_nav})
    sd = float(day_ret.std()) if len(day_ret) > 1 else 0.0
    peak = np.maximum.accumulate(np.r_[1.0, navs])
    stats = {"total_return": float(navs[-1] - 1) if n else 0.0,
             "sharpe": float(day_ret.mean() / sd * np.sqrt(252)) if sd > 0 else None,
             "max_drawdown": float((np.r_[1.0, navs] / peak - 1).min()) if n else 0.0,
             "days": int(len(day_nav)), "fills": len(fills)}
    notes = []
    if int((raw != np.clip(raw, m["min_pos"], m["max_pos"])).sum()):
        notes.append(f"positions outside {m['min_pos']:g}..{m['max_pos']:g} were clipped: a position is a share of equity")
    if market == "VN_STOCK":
        notes.append("T+2 settlement and daily price limits are not simulated here; the Track Record service applies them")
    if market == "VN_DERIVATIVE":
        notes.append("the monthly contract roll is not simulated here; the Track Record service applies it")
    return PaperResult(nav_s, pd.DataFrame(fills, columns=["time", "price", "before", "after", "cost"]), daily, stats, notes)
