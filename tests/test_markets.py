"""US and crypto markets (0.3): market-data client, crypto and US data functions, perpetual funding in
paper.simulate. Offline: the network is replaced by fakes."""
import io
import zipfile

import numpy as np
import pandas as pd
import pytest

from quantvn import marketdata, paper
from quantvn.crypto.data import derivatives as crypto
from quantvn.crypto.data.download import extract_csv
from quantvn.us.data import stocks as us

T0 = 1_794_614_400_000          # 2026-11-14 00:00 UTC


def api_bars(t0, n, step=60_000):
    ts = t0 + step * np.arange(n, dtype=np.int64)
    c = 100.0 + np.arange(n)
    return pd.DataFrame({"ts": ts, "open": c - 0.5, "high": c + 1, "low": c - 1, "close": c, "volume": 1.0})


def test_to_ms():
    assert marketdata.to_ms("2026-11-14") == T0
    assert marketdata.to_ms("2026-11-14T07:00+07:00") == T0
    assert marketdata.to_ms(T0 / 1000) == T0 and marketdata.to_ms(T0) == T0
    assert marketdata.to_ms(None, 5) == 5


def test_to_candles_layout_and_time_zone():
    out = marketdata.to_candles(api_bars(T0, 3), "Asia/Ho_Chi_Minh")
    assert list(out.columns) == ["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]
    assert out["time"].iloc[0] == "07:00:00" and out["Date"].iloc[0] == "2026-11-14"
    assert str(marketdata.to_candles(api_bars(T0, 1), None)["Datetime"].dt.tz) == "UTC"


class FakeApi:
    """Answers /bars from a frame, one request per window, like the real API."""

    def __init__(self, frame):
        self.frame, self.calls = frame, []

    def __call__(self, path, params, **kw):
        self.calls.append((path, dict(params)))
        if path == "/bars":
            f = self.frame[(self.frame["ts"] >= params["start"]) & (self.frame["ts"] < params["end"])]
            buf = io.BytesIO()
            f.to_parquet(buf)

            newest = str(int(self.frame["ts"].max())) if len(self.frame) else "0"

            class R:
                content = buf.getvalue()
                headers = {"X-Newest": newest}
            return R()
        raise AssertionError(path)


def test_bars_pages_long_windows(monkeypatch):
    frame = api_bars(T0, 1000)
    fake = FakeApi(frame)
    monkeypatch.setattr(marketdata, "_get", fake)
    monkeypatch.setattr(marketdata, "MAX_ROWS", 300)            # 270 rows per request
    out = marketdata.bars("crypto_spot", "BTCUSDT", T0, T0 + 1000 * 60_000)
    assert len(out) == 1000 and out["ts"].is_monotonic_increasing and len(fake.calls) == 4


def test_crypto_hist_from_quantvn_api(monkeypatch):
    fake = FakeApi(api_bars(T0, 120))
    monkeypatch.setattr(marketdata, "_get", fake)
    df = crypto.get_hist("btcusdt", start="2026-11-14", end="2026-11-14T01:00", market="perp")
    assert len(df) == 60 and fake.calls[0][1]["dataset"] == "crypto_perp" and fake.calls[0][1]["symbol"] == "BTCUSDT"
    assert df["Datetime"].iloc[0] == pd.Timestamp("2026-11-14 07:00", tz="Asia/Ho_Chi_Minh")


def test_crypto_hist_default_window_is_the_one_of_0_2(monkeypatch):
    fake = FakeApi(api_bars(T0, 1))
    monkeypatch.setattr(marketdata, "_get", fake)
    crypto.get_hist("BTCUSDT", interval="1d")
    first, last = fake.calls[0][1], fake.calls[-1][1]
    assert first["start"] == marketdata.to_ms("2019-06-30T17:00") and last["end"] == marketdata.to_ms("2022-12-31T17:00")
    assert len(fake.calls) == 4                         # aggregated intervals: a year per request


def test_crypto_hist_falls_back_to_binance(monkeypatch):
    def down(*a, **k):
        raise marketdata.MarketDataError(404, "unknown_symbol", "not stored")
    monkeypatch.setattr(marketdata, "_get", down)
    seen = {}

    def binance(symbol, interval, start_ms, end_ms, market, cache_dir, tz):
        seen.update(symbol=symbol, interval=interval, market=market)
        return pd.DataFrame(columns=crypto.COLUMNS)
    monkeypatch.setattr(crypto, "_from_binance", binance)
    crypto.get_hist("PEPEUSDT", start="2026-01-01", end="2026-01-02", market="perp")
    assert seen == {"symbol": "PEPEUSDT", "interval": "1m", "market": "perp"}
    with pytest.raises(marketdata.MarketDataError):
        crypto.get_hist("PEPEUSDT", start="2026-01-01", end="2026-01-02", source="quantvn")


def test_crypto_store_that_stops_early_is_topped_up_from_binance(monkeypatch):
    # the store has 30 minutes from W0; the window asks for 2 hours that ended long ago
    W0 = T0 - 30 * 86_400_000
    monkeypatch.setattr(marketdata, "_get", FakeApi(api_bars(W0, 30)))
    seen = {}

    def binance(symbol, interval, start_ms, end_ms, market, cache_dir, tz):
        seen.update(start=start_ms, end=end_ms, tz=tz)
        return marketdata.to_candles(api_bars(start_ms, (end_ms - start_ms) // 60_000), None)
    monkeypatch.setattr(crypto, "_from_binance", binance)
    df = crypto.get_hist("BTCUSDT", start=W0, end=W0 + 120 * 60_000)
    assert seen == {"start": W0 + 30 * 60_000, "end": W0 + 120 * 60_000, "tz": None}
    assert len(df) == 120 and df["Datetime"].is_monotonic_increasing and df["Datetime"].is_unique
    assert str(df["Datetime"].dt.tz) == "Asia/Ho_Chi_Minh" and df["time"].iloc[0] == "07:00:00"


def test_crypto_complete_store_is_not_topped_up(monkeypatch):
    monkeypatch.setattr(marketdata, "_get", FakeApi(api_bars(T0, 200)))
    monkeypatch.setattr(crypto, "_from_binance", lambda *a, **k: pytest.fail("Binance called"))
    assert len(crypto.get_hist("BTCUSDT", start=T0, end=T0 + 120 * 60_000)) == 120


def test_crypto_interval_the_api_does_not_serve_goes_to_binance(monkeypatch):
    monkeypatch.setattr(marketdata, "_get", lambda *a, **k: pytest.fail("API called"))
    monkeypatch.setattr(crypto, "_from_binance", lambda *a, **k: pd.DataFrame(columns=crypto.COLUMNS))
    crypto.get_hist("BTCUSDT", interval="3m", start="2026-01-01", end="2026-01-02")
    with pytest.raises(ValueError):
        crypto.get_hist("BTCUSDT", interval="3m", start="2026-01-01", end="2026-01-02", source="quantvn")


def _zip(text):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("x.csv", text)
    buf.seek(0)
    return buf


def test_extract_csv_microseconds_and_header():
    us_rows = "1790812800000000,1,2,0.5,1.5,10,1790812859999999,0,0,0,0,0\n"
    df = extract_csv(_zip(us_rows))
    assert df["t"].iloc[0] == 1790812800000 and df["Close"].iloc[0] == 1.5
    hdr = "open_time,open,high,low,close,volume,close_time,a,b,c,d,e\n1790812800000,1,2,0.5,1.5,10,0,0,0,0,0,0\n"
    df = extract_csv(_zip(hdr))
    assert len(df) == 1 and df["t"].iloc[0] == 1790812800000


def test_us_hist_intraday_and_daily(monkeypatch):
    fake = FakeApi(api_bars(T0 + 14 * 3_600_000 + 30 * 60_000, 30))   # 09:30 New York (EST, 14:30 UTC)
    monkeypatch.setattr(marketdata, "_get", fake)
    df = us.get_hist("aapl", "5m", start="2026-11-14", end="2026-11-15")
    assert fake.calls[0][1] == {"dataset": "us_stock", "symbol": "AAPL", "start": T0, "end": T0 + 86_400_000,
                                "interval": "5m"}
    assert df["time"].iloc[0] == "09:30:00"
    us.get_hist("SPY", "1d", end="2026-11-15")
    assert fake.calls[-1][1]["dataset"] == "us_stock_1d" and fake.calls[-1][1]["start"] == marketdata.to_ms("1990-01-01")
    with pytest.raises(ValueError):
        us.get_hist("AAPL", "2m")


def test_us_hist_without_window_keeps_the_0_2_service(monkeypatch):
    called = {}
    monkeypatch.setattr(us, "_legacy", lambda sym: called.setdefault("sym", sym))
    us.get_hist("msft")
    assert called == {"sym": "MSFT"}


# --------------------------------------------------------------------------------- perpetual funding

def frame(opens, closes, positions, start="2026-11-14 07:58"):
    ts = pd.date_range(start, periods=len(opens), freq="1min", tz="UTC")
    return pd.DataFrame({"Datetime": ts, "Open": opens, "Close": closes, "position": positions})


def test_funding_hand_worked():
    df = frame([100, 100, 102, 102], [100, 101, 102, 102], [1, 1, 1, 1])
    f = pd.DataFrame({"Datetime": [pd.Timestamp("2026-11-14 08:00", tz="UTC")], "rate": [1e-4]})
    r = paper.simulate(df, market="CRYPTO_PERP", fee=0, funding=f)
    assert r.nav.iloc[-1] == pytest.approx(1.01 * (102 / 101) * (1 - 1e-4), rel=1e-15)
    assert r.stats["funding"] == pytest.approx(1e-4)
    short = paper.simulate(frame([100, 100, 102, 102], [100, 101, 102, 102], [-1] * 4), market="CRYPTO_PERP",
                           fee=0, funding=f)
    assert short.nav.iloc[-1] == pytest.approx(0.99 * (1 - 1 / 101) * (1 + 1e-4), rel=1e-15)


def test_funding_on_a_bar_whose_fill_changes_the_weight_is_paid_on_the_old_weight():
    # decided long on 07:59 -> filled at the 08:00 open; the 08:00 event is settled on the old weight 0
    df = frame([100, 100, 100], [100, 100, 100], [0, 1, 1])
    f = pd.DataFrame({"ts": [marketdata.to_ms("2026-11-14 08:00")], "rate": [5e-3]})
    r = paper.simulate(df, market="CRYPTO_PERP", fee=0, funding=f)
    assert r.nav.iloc[-1] == 1.0 and r.stats["funding"] == 0.0


def test_naive_datetimes_are_utc_and_unit_does_not_matter():
    ts = pd.Series(pd.date_range("2026-11-14 07:59", periods=3, freq="1min")).astype("datetime64[us]")
    df = pd.DataFrame({"Datetime": ts, "Open": [100.0] * 3, "Close": [100.0] * 3, "position": [1, 1, 1]})
    f = pd.DataFrame({"ts": [marketdata.to_ms("2026-11-14 08:01")], "rate": [1e-3]})
    r = paper.simulate(df, market="CRYPTO_PERP", fee=0, funding=f)
    assert r.nav.iloc[-1] == pytest.approx(1 - 1e-3)


def reference(df, market, funding_ts, funding_rate, delay=1):
    """A plain loop written separately from simulate: opening move, funding, fill, the bar's own move."""
    m = paper.MARKETS[market]
    bar_ms = [int(t.value // 1_000_000) for t in pd.to_datetime(df["Datetime"])]
    events = sorted(zip(funding_ts, funding_rate))
    nav, w, prev, e = 1.0, 0.0, None, 0
    for k in range(len(df)):
        o, c = float(df["Open"].iloc[k]), float(df["Close"].iloc[k])
        prev = o if prev is None else prev
        nav *= 1 + w * (o / prev - 1)
        while e < len(events) and events[e][0] <= bar_ms[k]:
            if k == 0 or events[e][0] > bar_ms[k - 1]:
                nav *= 1 - w * events[e][1]
            e += 1
        tgt = round(min(max(float(df["position"].iloc[k - delay]), m["min_pos"]), m["max_pos"]), 4) if k >= delay else 0.0
        if tgt != w:
            nav *= 1 - abs(tgt - w) * m["fee"]
            w = tgt
        nav *= 1 + w * (c / o - 1)
        prev = c
    return nav


@pytest.mark.parametrize("seed", range(25))
def test_funding_against_a_plain_loop(seed):
    rng = np.random.default_rng(seed)
    n = int(rng.integers(50, 1500))
    px = 100 * np.exp(np.cumsum(rng.normal(0, 2e-3, n)))
    pos = pd.Series(np.where(rng.random(n) < 0.03, np.round(rng.uniform(-1.3, 1.3, n), 4), np.nan)).ffill().fillna(0)
    df = pd.DataFrame({"Datetime": pd.date_range("2026-11-14", periods=n, freq="1min", tz="UTC"),
                       "Open": px * np.exp(rng.normal(0, 5e-4, n)), "Close": px, "position": pos})
    ft = list(range(T0, T0 + n * 60_000, 3_600_000))
    fr = list(rng.normal(1e-4, 3e-4, len(ft)))
    r = paper.simulate(df, market="CRYPTO_PERP", funding=pd.DataFrame({"ts": ft, "rate": fr}))
    assert r.nav.iloc[-1] == pytest.approx(reference(df, "CRYPTO_PERP", ft, fr), rel=1e-12)


def test_perp_without_funding_says_so_and_us_can_be_short():
    r = paper.simulate(frame([100, 100, 90], [100, 90, 90], [-1, -1, -1]), market="CRYPTO_PERP")
    assert any("funding was not charged" in n for n in r.notes)
    r = paper.simulate(frame([100, 100, 90], [100, 90, 90], [-1, -1, -1]), market="US_STOCK")
    assert r.nav.iloc[-1] == pytest.approx((1 - 1e-4) * 1.10)
