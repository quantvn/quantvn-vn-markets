import numpy as np
import pandas as pd
import pytest

from quantvn import strategy


def make_bars(days=("2026-11-12", "2026-11-13"), n=60, seed=1):
    rng = np.random.default_rng(seed)
    parts, price = [], 1800.0
    for day in days:
        ts = pd.date_range(f"{day} 09:00", periods=n, freq="1min")
        close = price + np.cumsum(rng.normal(0, 1.0, n))
        opens = np.r_[price, close[:-1]]
        parts.append(pd.DataFrame({"Datetime": ts, "Date": day, "time": ts.strftime("%H:%M:%S"), "Open": opens,
                                   "High": np.maximum(opens, close) + 0.2, "Low": np.minimum(opens, close) - 0.2,
                                   "Close": close, "volume": 100.0}))
        price = close[-1]
    return pd.concat(parts, ignore_index=True)


def causal(df):
    df["ma"] = df["Close"].rolling(10).mean()
    df["position"] = np.where(df["Close"] > df["ma"], 1, -1)
    return df


def peeks(df):                                   # looks one bar into the future
    df["position"] = np.where(df["Close"].shift(-1) > df["Close"], 1, -1)
    return df


def test_rules_of_the_frame():
    assert [strategy.resolution_of(s) for s in ("VN30F1M", "VN30F5M", "VN30F15M", "FPT")] == [1, 5, 15, 5]
    assert strategy.position_limits("VN30F1M") == (-1.0, 1.0) and strategy.position_limits("FPT") == (0.0, 1.0)
    assert strategy.to_weight(8200, "VN30F1M") == (1.0, True) and strategy.to_weight(-1, "FPT") == (0.0, True)
    assert strategy.to_weight(0.25, "FPT") == (0.25, False)
    t = pd.Timestamp
    assert strategy.bar_end(t("2026-11-13 09:00"), 5) == t("2026-11-13 09:05")
    assert strategy.bar_end(t("2026-11-13 11:30"), 5) == t("2026-11-13 11:31")      # lunch cuts the bar short
    assert strategy.bar_end(t("2026-11-13 14:25"), 5) == t("2026-11-13 14:30")
    assert strategy.bar_end(t("2026-11-13 14:45"), 15) == t("2026-11-13 14:46")     # the closing auction print
    bars = make_bars()
    assert len(strategy.closed(bars, 1, now=pd.Timestamp("2026-11-13 09:10:30"))) == 60 + 10


def test_live_frame_is_the_previous_day_and_today_up_to_the_bar():
    bars = make_bars(days=("2026-11-11", "2026-11-12", "2026-11-13"))
    f = strategy.live_frame(bars, "2026-11-13 09:04")
    assert sorted(f["Date"].unique()) == ["2026-11-12", "2026-11-13"] and len(f) == 60 + 5
    assert f["Datetime"].iloc[-1] == pd.Timestamp("2026-11-13 09:04") and list(f.columns[:8]) == strategy.COLUMNS


def test_replay_gives_one_decision_per_bar():
    bars = make_bars()
    live = strategy.replay(causal, bars, "VN30F1M")
    assert len(live) == 60 and live["error"].isna().all() and set(live["weight"]) <= {1.0, -1.0}
    assert list(live.columns) == ["bar", "position", "weight", "clipped", "seconds", "error"]
    assert len(strategy.replay(causal, bars, "VN30F1M", every=10)) == 6


def test_check_passes_a_causal_strategy_and_catches_look_ahead():
    bars = make_bars()
    good = strategy.check(causal, bars, "VN30F1M")
    assert good.ok and good.bars_checked >= 40 and len(good.differences) == 0
    bad = strategy.check(peeks, bars, "VN30F1M")
    assert not bad.ok and "look-ahead" in bad.errors[0] and len(bad.differences) > 5
    assert "NOT OK" in bad.summary() and "OK" in repr(good)


def test_check_reports_failures_clipping_and_nan():
    bars = make_bars()

    def no_column(df):
        return df

    def raises(df):
        raise RuntimeError("boom")

    def contracts(df):
        df["position"] = 5
        return df

    def needs_history(df):
        df["position"] = df["Close"].rolling(500).mean()      # never has 500 bars: NaN
        return df

    assert "'position' column" in strategy.check(no_column, bars).errors[0]
    assert "RuntimeError: boom" in strategy.check(raises, bars).errors[0]
    r = strategy.check(contracts, bars)
    assert r.ok and "clipped" in r.warnings[0] and (r.live["weight"] == 1.0).all()
    assert "not finite" in strategy.check(needs_history, bars).errors[0]
    with pytest.raises(ValueError):
        strategy.check(causal, bars[bars["Date"] == "2026-11-13"])      # one day only: not what the platform passes


GOOD = """
import pandas as pd
WINDOW = 20
def gen_position(df):
    df['position'] = (df['Close'] > df['Close'].rolling(WINDOW).mean()).astype(int)
    return df
if __name__ == '__main__':
    raise SystemExit('a local backtest that must not run on the platform')
"""


@pytest.mark.parametrize("source,expect", [
    ("x = 1", "no top-level function gen_position"),
    ("def gen_position(df, window):\n    return df", "requires 2"),
    ("def gen_position(df:\n", "syntax error"),
    ("import requests\ndef gen_position(df):\n    return df", "no network"),
    ("from quantvn.vn.data import Macro\ndef gen_position(df):\n    Macro()\n    return df", "live data"),
    ("def gen_position(df):\n    input()\n    return df", "nobody can type"),
])
def test_validate_script_errors(source, expect):
    r = strategy.validate_script(source)
    assert not r.ok and expect in " ".join(r.errors), r


def test_validate_script_warnings_and_a_clean_file(tmp_path):
    assert strategy.validate_script(GOOD).ok and not strategy.validate_script(GOOD).warnings
    r = strategy.validate_script("from quantvn.vn.data import get_derivatives_hist\n"
                                 "data = get_derivatives_hist('VN30F1M', '1m')\n"
                                 "def gen_position(df, window=20):\n    return df")
    assert r.ok and any("same candles" in w for w in r.warnings) and any("every bar" in w for w in r.warnings)
    path = tmp_path / "s.py"
    path.write_text(GOOD, encoding="utf-8")
    fn = strategy.load_script(str(path))                      # the __main__ block does not run
    assert strategy.check(fn, make_bars(), "FPT").ok
    assert strategy.validate_script(str(path)).ok
