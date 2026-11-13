"""Client of the QuantVN Track Record service (https://paper.quantvn.com).

Your own program computes a position and sends it; the service stamps the moment it arrived and later
prices it from its own data, at the open of the first 1-minute bar after that moment. Nothing your program
sends can set a price.

    from quantvn.paper import TrackRecord

    tr = TrackRecord(email="you@example.com", api_key="...")   # the API key from your QuantVN profile
    tr.send("my-first-bot", "VN30F1M", 1)                      # go fully long
    print(tr.bots())
"""
from __future__ import annotations

import time
from typing import Iterable, Optional

import requests

BASE_URL = "https://paper.quantvn.com"


class TrackRecordError(Exception):
    """The service refused a request. ``code`` is its error code (for example ``rate_limited``,
    ``position_out_of_range``, ``bot_limit_reached``), ``status`` the HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.status, self.code, self.message = status, code, message


class TrackRecord:
    """One account on the Track Record service.

    `api_key` defaults to the key set with ``quantvn.client(apikey=...)``. `email` is the email of the
    QuantVN account that owns the key; the service checks that the two belong together.
    """

    def __init__(self, email: str, api_key: Optional[str] = None, base_url: str = BASE_URL, timeout: float = 20):
        if api_key is None:
            from quantvn.vn.data.utils import Config
            api_key = Config.get_api_key()
        self.email, self.base_url, self.timeout = email, base_url.rstrip("/"), timeout
        self._session = requests.Session()
        self._session.headers.update({"X-API-Key": api_key, "User-Agent": "quantvn-sdk"})

    def _call(self, method: str, path: str, **kwargs):
        r = self._session.request(method, self.base_url + path, timeout=self.timeout, **kwargs)
        try:
            body = r.json()
        except ValueError:
            body = None
        if r.status_code >= 400:
            err = (body or {}).get("error", {}) if isinstance(body, dict) else {}
            raise TrackRecordError(r.status_code, err.get("code", "http_error"), err.get("message", r.text[:200]))
        return body

    # ------------------------------------------------------------------ sending positions
    def send(self, bot_name: str, asset: str, position: float, at: Optional[float] = None) -> dict:
        """Report the position a bot wants to hold from now on: a share of equity, -1..1 for futures and
        0..1 for stocks and crypto spot. Returns the service's answer; ``status`` is ``accepted``,
        ``unchanged`` (the bot already holds it) or ``duplicate``. `at` is when your program decided
        (epoch seconds, default now); it is recorded, but the fill is priced after the time of arrival."""
        return self._call("POST", "/v1/signals", json=self._signal(bot_name, asset, position, at))

    def send_many(self, signals: Iterable[tuple]) -> list:
        """Several bots in one request: an iterable of (bot_name, asset, position). Returns one answer per
        signal; a refused one has ``status`` ``rejected`` and does not stop the others."""
        body = {"signals": [self._signal(*s) for s in signals]}
        return self._call("POST", "/v1/signals", json=body)["results"]

    def _signal(self, bot_name, asset, position, at=None):
        return {"email": self.email, "bot_name": bot_name, "asset": asset, "position": float(position),
                "time": time.time() if at is None else at}

    # ------------------------------------------------------------------ reading records
    def bots(self) -> list:
        """Every bot of the account with its latest statistics."""
        return self._call("GET", "/v1/bots")

    def record(self, bot_name: str, days: int = 365) -> dict:
        """The track record of one bot: ``bot`` (statistics), ``daily`` rows
        [day, return, nav, position at close, trades, fee] and ``fills`` rows
        [time, price, position before, position after, fee, reason]."""
        return self._call("GET", f"/v1/bots/{requests.utils.quote(bot_name, safe='')}", params={"days": days})

    def signals(self, bot_name: str, limit: int = 100) -> list:
        """The latest signals the service recorded for a bot, newest first."""
        return self._call("GET", f"/v1/bots/{requests.utils.quote(bot_name, safe='')}/signals", params={"limit": limit})

    def assets(self) -> list:
        """Instruments that accept signals, with each market's position range and costs."""
        return self._call("GET", "/v1/assets")

    # ------------------------------------------------------------------ changing a bot
    def publish(self, bot_name: str) -> dict:
        """Make the record public. Publication is permanent: a published record can later be marked
        withdrawn, but it stays readable."""
        return self._call("PATCH", f"/v1/bots/{requests.utils.quote(bot_name, safe='')}", json={"is_public": True})

    def stop(self, bot_name: str) -> dict:
        """Stop a bot for good. Its position is closed and it accepts no further signals."""
        return self._call("PATCH", f"/v1/bots/{requests.utils.quote(bot_name, safe='')}", json={"status": "stopped"})
