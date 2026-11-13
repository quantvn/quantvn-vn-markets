import pandas as pd
import pytest

from quantvn import paper


def frame(opens, closes, positions, start="2026-11-13 09:00"):
    ts = pd.date_range(start, periods=len(opens), freq="1min")
    return pd.DataFrame({"Datetime": ts, "Open": opens, "Close": closes, "position": positions})


def test_a_decision_is_filled_at_the_next_open_never_at_its_own_close():
    # decided long on bar 0 (close 100); the next bar opens at 110 and closes at 121
    r = paper.simulate(frame([100, 110, 121], [100, 121, 121], [1, 1, 1]), fee=0)
    assert list(r.fills["price"]) == [110.0] and r.nav.iloc[-1] == pytest.approx(121 / 110)
    # one more bar of delay: filled at 121, earns nothing
    assert paper.simulate(frame([100, 110, 121], [100, 121, 121], [1, 1, 1]), fee=0, delay_bars=2).nav.iloc[-1] == 1.0
    with pytest.raises(ValueError):
        paper.simulate(frame([1, 1], [1, 1], [1, 1]), delay_bars=0)


def test_futures_fee_and_short():
    r = paper.simulate(frame([100, 100, 90], [100, 90, 90], [-1, -1, -1]))
    assert r.nav.iloc[-1] == pytest.approx((1 - 1.5e-4) * 1.10) and r.stats["fills"] == 1


def test_stock_pays_fee_tax_and_half_a_price_step_and_cannot_be_short():
    df = frame([50, 50, 52, 52], [50, 52, 52, 52], [1, 0, 0, 0])
    r = paper.simulate(df, market="VN_STOCK")
    buy = 1 - (0.0015 + 0.05 / 50)                    # fee and half of a 100 VND step on 50,000
    sell = 1 - (0.0015 + 0.0010 + 0.05 / 52)          # fee, sell tax, half a step on 52,000
    assert r.nav.iloc[-1] == pytest.approx(buy * 52 / 50 * sell)
    assert list(r.fills["cost"]) == pytest.approx([0.0015 + 0.001, 0.0025 + 0.05 / 52])
    short = paper.simulate(frame([50, 50], [50, 40], [-1, -1]), market="VN_STOCK")
    assert short.nav.iloc[-1] == 1.0 and any("clipped" in n for n in short.notes)
    assert paper.vn_tick(9.99) == 0.01 and paper.vn_tick(10) == 0.05 and paper.vn_tick(50) == 0.1
    assert paper.vn_tick(5, "HNX") == 0.1


def test_daily_statistics():
    a = frame([100, 100, 101], [100, 101, 102], [1, 1, 1], "2026-11-12 14:00")
    b = frame([103, 103, 102], [103, 102, 101], [1, 0, 0], "2026-11-13 09:00")
    r = paper.simulate(pd.concat([a, b]), fee=0)
    assert list(r.daily.index) == ["2026-11-12", "2026-11-13"] and r.stats["days"] == 2
    assert r.daily["nav"].iloc[0] == pytest.approx(102 / 100)
    # held overnight from 102 to the open at 103, down to 102, sold at the open of the last bar (102)
    assert r.nav.iloc[-1] == pytest.approx(102 / 100)
    assert r.stats["max_drawdown"] == pytest.approx(102 / 103 - 1) and "return" in repr(r)


class FakeResponse:
    def __init__(self, status, body):
        self.status_code, self._body, self.text = status, body, str(body)

    def json(self):
        return self._body


def test_client_sends_what_the_service_expects(monkeypatch):
    calls = []

    def request(self, method, url, timeout=None, **kw):
        calls.append((method, url, kw, dict(self.headers)))
        if url.endswith("/v1/signals") and "signals" in kw["json"]:
            return FakeResponse(200, {"results": [{"status": "accepted"}, {"status": "rejected"}]})
        if "missing" in url:
            return FakeResponse(404, {"error": {"code": "bot_not_found", "message": "No such bot."}})
        return FakeResponse(200, {"status": "accepted", "seq": 1})
    monkeypatch.setattr("requests.Session.request", request)
    tr = paper.TrackRecord(email="an@example.com", api_key="k-123")
    assert tr.send("alpha", "VN30F1M", 1)["status"] == "accepted"
    method, url, kw, headers = calls[-1]
    assert (method, url) == ("POST", "https://paper.quantvn.com/v1/signals") and headers["X-API-Key"] == "k-123"
    assert kw["json"]["email"] == "an@example.com" and kw["json"]["bot_name"] == "alpha" and kw["json"]["position"] == 1.0
    assert [r["status"] for r in tr.send_many([("a", "VN30F1M", 1), ("b", "FPT", -1)])] == ["accepted", "rejected"]
    assert len(calls[-1][2]["json"]["signals"]) == 2
    tr.record("my bot", days=30)
    assert calls[-1][1].endswith("/v1/bots/my%20bot") and calls[-1][2]["params"] == {"days": 30}
    with pytest.raises(paper.TrackRecordError) as e:
        tr.record("missing")
    assert e.value.code == "bot_not_found" and e.value.status == 404
    tr.stop("alpha")
    assert calls[-1][0] == "PATCH" and calls[-1][2]["json"] == {"status": "stopped"}


def test_client_uses_the_key_set_with_quantvn_client(monkeypatch):
    import quantvn
    quantvn.client(apikey="from-client")
    monkeypatch.setattr("requests.Session.request", lambda self, m, u, timeout=None, **kw: FakeResponse(200, []))
    tr = paper.TrackRecord(email="an@example.com")
    assert tr._session.headers["X-API-Key"] == "from-client" and tr.bots() == []
