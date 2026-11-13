"""Run a strategy on a laptop the way QuantVN runs it, and find out before uploading whether it will work.

``replay`` calls ``gen_position`` once per closed bar with the frame the platform would pass at that moment.
``check`` does that for a sample of bars and compares the answers with the positions the same function
gives when it sees the whole day at once. Where the two differ, the backtest used information that did not
exist yet (or depends on how much history it is given) and its results cannot be reproduced live.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from typing import Callable, List, Optional

import pandas as pd

from .frames import live_frame, resolution_of, to_weight

# What a strategy gets on the platform for one call.
LIMITS = {"cpu_seconds": 10, "wall_seconds": 20, "memory_mb": 2048, "network": False, "file_mb": 16}
_SLOW_SECONDS = 2.0        # a call slower than this is reported: hundreds of strategies share each minute


class StrategyError(Exception):
    """gen_position broke the contract: what it returned cannot be turned into a position."""


def decide(gen_position: Callable, frame: pd.DataFrame) -> float:
    """One call, as on the platform: the position on the row of the last bar of `frame`."""
    out = gen_position(frame.copy())
    if not isinstance(out, pd.DataFrame) or "position" not in out.columns:
        raise StrategyError("gen_position must return a DataFrame with a 'position' column")
    if not len(out):
        raise StrategyError("gen_position returned no rows")
    row = out.iloc[-1]
    if "Datetime" in out.columns and len(frame):
        match = out[pd.to_datetime(out["Datetime"], errors="coerce") == frame["Datetime"].iloc[-1]]
        if not len(match):
            raise StrategyError("gen_position returned no row for the last bar")
        row = match.iloc[-1]
    try:
        value = float(row["position"])
    except (TypeError, ValueError):
        raise StrategyError("position on the last bar is not a number")
    if not math.isfinite(value):
        raise StrategyError("position on the last bar is not finite (NaN: not enough history yet?)")
    return value


def replay(gen_position: Callable, bars: pd.DataFrame, symbol: str = "VN30F1M", day: Optional[str] = None,
           every: int = 1, labels: Optional[list] = None) -> pd.DataFrame:
    """The decisions the platform would have recorded on `day` (default: the last day in `bars`).

    For each closed bar of the day (every `every`-th one) ``gen_position`` is called with the frame of that
    moment. Returns one row per call: ``bar``, ``position`` (raw), ``weight`` (what is recorded),
    ``clipped``, ``seconds`` and ``error``. `bars` must already be at the strategy's resolution and hold
    the previous trading day as well; see `quantvn.strategy.candles`.
    """
    days = sorted(bars["Date"].unique())
    if not days:
        raise ValueError("no bars")
    day = day or days[-1]
    if labels is None:
        labels = list(bars.loc[bars["Date"] == day, "Datetime"])[::max(1, int(every))]
    rows = []
    for label in labels:
        frame = live_frame(bars, label)
        t0 = time.perf_counter()
        rec = {"bar": label, "position": None, "weight": None, "clipped": False, "error": None}
        try:
            p = decide(gen_position, frame)
            w, clipped = to_weight(p, symbol)
            rec.update(position=p, weight=w, clipped=clipped)
        except StrategyError as e:
            rec["error"] = str(e)
        except Exception as e:                       # the strategy's own failure is a result, as on the platform
            rec["error"] = f"{type(e).__name__}: {e}"[:300]
        rec["seconds"] = time.perf_counter() - t0
        rows.append(rec)
    return pd.DataFrame(rows, columns=["bar", "position", "weight", "clipped", "seconds", "error"])


@dataclass
class Report:
    """Result of `check`. ``ok`` is False when the strategy would fail or mislead on the platform."""
    symbol: str
    day: str
    bars_checked: int = 0
    errors: List[str] = field(default_factory=list)        # it would not run, or not as backtested
    warnings: List[str] = field(default_factory=list)      # it runs, but read this
    live: Optional[pd.DataFrame] = None                    # the replay
    differences: Optional[pd.DataFrame] = None             # bars where live and whole-day positions differ

    @property
    def ok(self) -> bool:
        return not self.errors

    def summary(self) -> str:
        head = f"{self.symbol} {self.day}: {self.bars_checked} bars checked - " + ("OK" if self.ok else "NOT OK")
        lines = [head] + [f"  ERROR   {e}" for e in self.errors] + [f"  warning {w}" for w in self.warnings]
        return "\n".join(lines)

    def __repr__(self) -> str:
        return self.summary()


def check(gen_position: Callable, bars: pd.DataFrame, symbol: str = "VN30F1M", day: Optional[str] = None,
          samples: int = 40) -> Report:
    """Would this strategy behave on the platform as it does in a backtest?

    Runs ``gen_position`` at up to `samples` moments of `day`, each time with only the bars that existed
    then, and compares with the positions it produces when given the whole day. Reports: calls that fail
    or return no usable position; positions that differ between the two (look-ahead); positions outside
    the range that can be recorded; calls that are too slow.
    """
    days = sorted(bars["Date"].unique())
    if len(days) < 2:
        raise ValueError("bars must hold at least two trading days: the platform passes the previous day too")
    day = day or days[-1]
    today = bars[bars["Date"] == day]
    rep = Report(symbol=symbol, day=day)
    if len(today) < 2:
        raise ValueError(f"no bars for {day}")
    step = max(1, len(today) // max(1, samples))
    labels = list(today["Datetime"])[::step]
    if labels[-1] != today["Datetime"].iloc[-1]:    # the last bar is always checked
        labels.append(today["Datetime"].iloc[-1])
    live = replay(gen_position, bars, symbol, day, labels=labels)
    rep.live, rep.bars_checked = live, len(live)

    failed = live[live["error"].notna()]
    if len(failed):
        kinds = failed["error"].str.slice(0, 90).value_counts()
        rep.errors.append(f"{len(failed)} of {len(live)} calls gave no position: "
                          + "; ".join(f"{k} (x{v})" for k, v in kinds.head(3).items()))
    good = live[live["error"].isna()]

    whole = None
    try:                                            # the same function, shown the whole day at once
        out = gen_position(live_frame(bars, today["Datetime"].iloc[-1]).copy())
        if isinstance(out, pd.DataFrame) and "position" in out.columns and "Datetime" in out.columns:
            whole = out.assign(Datetime=pd.to_datetime(out["Datetime"])).drop_duplicates("Datetime", keep="last") \
                       .set_index("Datetime")["position"]
    except Exception:
        whole = None
    if whole is not None and len(good):
        cmp_ = good.assign(whole_day=[float(whole.get(b, float("nan"))) for b in good["bar"]])
        diff = cmp_[(cmp_["position"] - cmp_["whole_day"]).abs() > 1e-9][["bar", "position", "whole_day"]]
        diff = diff.rename(columns={"position": "live"})
        rep.differences = diff.reset_index(drop=True)
        if len(diff):
            rep.errors.append(
                f"look-ahead: at {len(diff)} of {len(good)} moments the position computed with the bars that existed "
                f"then differs from the position the whole-day run gives for the same bar (first at "
                f"{diff['bar'].iloc[0]:%H:%M}: live {diff['live'].iloc[0]:g}, whole day {diff['whole_day'].iloc[0]:g}). "
                "A backtest of this code is not what will be recorded")
    clipped = int(good["clipped"].sum()) if len(good) else 0
    if clipped:
        rep.warnings.append(f"{clipped} positions are outside the recorded range and will be clipped "
                            "(futures -1..1, stocks 0..1: a position is a share of equity, not a number of contracts)")
    slow = float(live["seconds"].max()) if len(live) else 0.0
    if slow > LIMITS["cpu_seconds"]:
        rep.errors.append(f"slowest call took {slow:.1f} s; the platform stops a call after {LIMITS['cpu_seconds']} s of CPU")
    elif slow > _SLOW_SECONDS:
        rep.warnings.append(f"slowest call took {slow:.1f} s; it runs every {resolution_of(symbol)} minute(s), "
                            "keep it well under a second")
    if len(good) and (good["weight"] == 0).all():
        rep.warnings.append("the position is 0 at every checked moment: with only the previous day and today as "
                            "history, does the strategy have enough bars to act?")
    return rep
