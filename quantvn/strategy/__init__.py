"""Write a strategy for QuantVN and know how it will behave before uploading it.

    from quantvn import strategy

    bars = strategy.candles("VN30F1M")                 # the candles the platform uses, no API key needed
    report = strategy.check(gen_position, bars)        # is the backtest what will be recorded?
    print(report)
    print(strategy.validate_script("my_strategy.py"))  # will the file run in the sandbox?

The contract of a strategy: a top-level function ``gen_position(df)`` that receives candles with the
columns ``Datetime, Date, time, Open, High, Low, Close, volume`` and returns a DataFrame with a ``position``
column. The position on the last row is the decision for the bar that just closed: a share of equity,
from -1 to 1 for VN30 futures and from 0 to 1 for stocks.
"""
from .frames import COLUMNS, bar_end, candles, closed, is_future, live_frame, position_limits, resolution_of, to_weight
from .harness import LIMITS, Report, StrategyError, check, decide, replay
from .script import ScriptReport, load_script, validate_script

__all__ = ["COLUMNS", "LIMITS", "Report", "ScriptReport", "StrategyError", "bar_end", "candles", "check", "closed",
           "decide", "is_future", "live_frame", "load_script", "position_limits", "replay", "resolution_of",
           "to_weight", "validate_script"]
