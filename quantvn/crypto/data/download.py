"""Binance's public archive (data.binance.vision): one zip per symbol, interval and month, no key needed."""
import io
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import requests

BASE = "https://data.binance.vision/data"
MARKET_PATH = {"spot": "spot", "perp": "futures/um"}
BASE_URL = f"{BASE}/spot/monthly/klines/"          # kept for code written against 0.2

VALID_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}


def download_monthly(symbol: str, interval: str, month: str, cache_dir: Path, market: str = "spot") -> Path:
    """Download (once) the monthly zip of a symbol and interval, return its local path. Raises RuntimeError
    when Binance has no file for that month."""
    folder = cache_dir / ("" if market == "spot" else market) / symbol / interval
    folder.mkdir(parents=True, exist_ok=True)
    zip_name = f"{symbol}-{interval}-{month}.zip"
    zip_path = folder / zip_name
    if zip_path.exists():
        return zip_path
    url = f"{BASE}/{MARKET_PATH[market]}/monthly/klines/{symbol}/{interval}/{zip_name}"
    resp = requests.get(url, stream=True, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"File not found: {url}")
    tmp = zip_path.with_suffix(".part")
    with open(tmp, "wb") as f:
        for chunk in resp.iter_content(1024 * 1024):
            f.write(chunk)
    tmp.replace(zip_path)
    return zip_path


def extract_csv(zip_path: Path) -> pd.DataFrame:
    """The klines of a monthly zip: columns t (open time, ms UTC), Open, High, Low, Close, Volume.
    Handles the header row of the futures archive and the microsecond times of the spot archive from 2025."""
    with zipfile.ZipFile(zip_path, "r") as zf:
        with zf.open(zf.namelist()[0]) as f:
            df = pd.read_csv(io.TextIOWrapper(f), header=None, usecols=range(6), dtype=str)
    df.columns = ["t", "Open", "High", "Low", "Close", "Volume"]
    df = df.apply(pd.to_numeric, errors="coerce").dropna(subset=["t", "Open", "Close"])
    t = df["t"].astype("int64").to_numpy()
    df["t"] = np.where(t > 10 ** 14, t // 1000, t)
    return df.reset_index(drop=True)
