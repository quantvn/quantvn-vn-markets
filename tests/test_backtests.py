"""The fill rule of the backtest classes: a position is traded at the open of the bar after the one it was
decided on, never at that bar's own close."""
import warnings

import numpy as np
import pandas as pd
import pytest

from quantvn.crypto.metrics.backtest import Backtest_Crypto
from quantvn.metrics._fills import next_bar_pnl
from quantvn.metrics.single_asset import TradingBacktest
from quantvn.us.metrics.backtest import Backtest_US_Stock
from quantvn.vn.metrics import Backtest_Derivates, Backtest_Stock


def frame(opens, closes, positions, start="2026-11-13 09:00", freq="1min"):
    ts = pd.date_range(start, periods=len(closes), freq=freq)
    df = pd.DataFrame({"Date": ts.strftime("%Y-%m-%d"), "time": ts.strftime("%H:%M:%S"), "Close": closes,
                       "position": positions})
    if opens is not None:
        df.insert(2, "Open", opens)
    return df


def loop(opens, closes, positions):
    """The rule written as a plain loop: the answer every class must give before fees."""
    held, total, prev = 0.0, 0.0, opens[0]
    for k in range(len(closes)):
        new = positions[k - 1] if k else 0.0
        total += held * (opens[k] - prev) + new * (closes[k] - opens[k])
        held, prev = new, closes[k]
    return total


def test_derivatives_fill_at_the_next_open():
    # decided long on bar 0 (close 100); the next bar opens at 110 and closes at 121
    bt = Backtest_Derivates(frame([100, 110, 121], [100, 121, 121], [1, 1, 1]), pnl_type="raw")
    assert bt.PNL().iloc[-1] == pytest.approx(11.0)             # 121 - 110, not 121 - 100
    assert list(bt.df["held"]) == [0.0, 1.0, 1.0] and list(bt.df["fill_price"]) == [100, 110, 121]


def test_the_fill_rule_does_not_repair_a_strategy_that_reads_the_future():
    # When every bar opens where the last one closed, the next open IS the deciding close, so a position
    # written with tomorrow's close still collects it. A fill rule cannot see that; quantvn.strategy.check does.
    closes = [100, 101, 100, 101, 100, 101, 100, 101]
    opens = [100] + closes[:-1]
    peek = [1 if closes[i + 1] > closes[i] else -1 for i in range(len(closes) - 1)] + [0]
    bt = Backtest_Derivates(frame(opens, closes, peek), pnl_type="raw")
    assert bt.PNL().iloc[-1] == pytest.approx(loop(opens, closes, peek)) == pytest.approx(7.0)
    # when the next bar opens half a point in the direction of the move, most of the profit is gone:
    # the entry is half a point worse and the position being closed gives back half a point as well
    gapped = [100] + [c + (0.5 if p > 0 else -0.5) for c, p in zip(closes[:-1], peek[:-1])]
    got = Backtest_Derivates(frame(gapped, closes, peek), pnl_type="raw").PNL().iloc[-1]
    assert got == pytest.approx(loop(gapped, closes, peek)) == pytest.approx(0.5)


def test_every_class_agrees_with_the_plain_loop_before_fees():
    rng = np.random.default_rng(7)
    n = 300
    closes = 100 + np.cumsum(rng.normal(0, 0.5, n))
    opens = np.r_[100.0, closes[:-1]] + rng.normal(0, 0.1, n)
    pos = rng.choice([-1.0, 0.0, 1.0], n)
    want = loop(opens, closes, pos)
    df = frame(opens, closes, pos)
    assert Backtest_Derivates(df, pnl_type="raw").PNL().iloc[-1] == pytest.approx(want)
    assert Backtest_Crypto(df, pnl_type="raw").PNL().iloc[-1] == pytest.approx(want)
    lower = df.rename(columns={"Date": "date", "Open": "open", "Close": "close"})
    assert TradingBacktest(lower, pnl_type="raw").compute_cumulative_pnl().iloc[-1] == pytest.approx(want)
    assert next_bar_pnl(np.r_[0.0, pos[:-1]], opens, closes).sum() == pytest.approx(want)
    long_only = np.clip(pos, 0, None) * 100
    want_long = loop(opens, closes, long_only)
    assert Backtest_Stock(df.assign(position=long_only), pnl_type="raw", min_hold_days=0).df["pnl_raw"].sum() \
        == pytest.approx(want_long)
    assert Backtest_US_Stock(df.assign(position=long_only), pnl_type="raw").df["pnl_raw"].sum() == pytest.approx(want_long)


def test_without_an_open_column_the_fill_is_the_next_close_and_a_warning_is_given():
    with pytest.warns(UserWarning, match="no Open column"):
        bt = Backtest_Derivates(frame(None, [100, 121, 121, 130], [1, 1, 1, 1]), pnl_type="raw")
    assert bt.PNL().iloc[-1] == pytest.approx(9.0)              # bought at 121, one bar after the decision
    with warnings.catch_warnings():
        warnings.filterwarnings("error", message=".*no Open column.*")   # with opens there is nothing to warn about
        Backtest_Derivates(frame([100, 121, 121, 130], [100, 121, 121, 130], [1, 1, 1, 1]), pnl_type="raw")


def test_derivative_fees_follow_the_holding():
    bt = Backtest_Derivates(frame([100, 100, 100, 100], [100, 100, 100, 100], [2, 2, 0, 0]))
    fee = 2700 / 100000
    assert list(bt.df["transaction_fee"]) == pytest.approx([0, 2 * fee, 0, 2 * fee])     # in at bar 1, out at bar 3
    assert bt.PNL().iloc[-1] == pytest.approx(-4 * fee)
    # a short carried into the next day pays the overnight fee per contract, as a long does
    two_days = pd.concat([frame([100, 100], [100, 100], [-1, -1], "2026-11-12 14:28"),
                          frame([100, 100], [100, 100], [-1, 0], "2026-11-13 09:00")], ignore_index=True)
    bt = Backtest_Derivates(two_days)
    assert bt.df["overnight_fee"].sum() == pytest.approx(2550 / 100000)


def test_stock_buys_at_the_next_open_and_pays_its_fee_on_that_price():
    bt = Backtest_Stock(frame([50, 51, 53], [50, 52, 54], [100, 100, 100]), min_hold_days=0)
    assert list(bt.df["trade_qty"]) == [0, 100, 0] and list(bt.df["effective_position"]) == [0, 100, 100]
    raw = 100 * (52 - 51) + 100 * (53 - 52) + 100 * (54 - 53)
    assert bt.df["pnl_raw"].sum() == pytest.approx(raw)
    assert bt.df["pnl_after_fees"].sum() == pytest.approx(raw - 100 * 51 * 0.001)
