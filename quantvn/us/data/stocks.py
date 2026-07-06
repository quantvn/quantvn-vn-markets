from __future__ import annotations

import io

import pandas as pd
import requests

from quantvn.vn.data.utils import Config

__all__ = ["get_hist"]

_TIMEOUT = 60


def get_hist(symbol: str, resolution: str = "1m") -> pd.DataFrame:
    """
    Get historical data of US stock.

    Parameters
    ----------
    symbol : str
        US ticker symbol, e.g. "AAPL", "MSFT", "TSLA"
    resolution : str
        Timeframe to get data. Only supported: "1m"

    Returns
    -------
    pd.DataFrame
        Historical data with columns [Datetime, Date, time, Open, High, Low, Close, volume]

    Raises
    ------
    ValueError
        If resolution is not supported.
    Exception
        If there is an error when calling the API.
    """
    if str(resolution).lower().strip() != "1m":
        raise ValueError("resolution must be: '1m'.")

    sym = str(symbol).upper().strip()
    api_key = Config.get_api_key()

    response = requests.post(
        f"{Config.get_link_us_stock_url()}/us/stock/historical",
        json={"symbol": sym, "interval": "1m"},
        headers={"x-api-key": api_key},
        timeout=_TIMEOUT,
    )

    if response.status_code == 200:
        body = response.json()
        if "error" in body:
            raise Exception(f"API error: {body['error']}")
        url = body.get("url", "")
        raw = requests.get(url, timeout=_TIMEOUT).content
        df = pd.read_parquet(io.BytesIO(raw))
        return df
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")
