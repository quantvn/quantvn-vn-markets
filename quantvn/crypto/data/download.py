import zipfile
from pathlib import Path

import pandas as pd
import requests

BASE_URL = "https://data.binance.vision/data/spot/monthly/klines/"

VALID_INTERVALS = {
    "1m", "3m", "5m", "15m", "30m",
    "1h", "2h", "4h", "6h", "8h", "12h",
    "1d", "3d", "1w", "1M",
}

def download_monthly(symbol: str, interval: str, month: str, cache_dir: Path) -> Path:
    """
    Download a monthly ZIP file for any symbol & interval, return local path.
    """
    cache_dir = cache_dir / symbol / interval
    cache_dir.mkdir(parents=True, exist_ok=True)

    zip_name = f"{symbol}-{interval}-{month}.zip"
    zip_path = cache_dir / zip_name
    if zip_path.exists():
        return zip_path

    url = f"{BASE_URL}{symbol}/{interval}/{zip_name}"
    resp = requests.get(url, stream=True, timeout=60)
    if resp.status_code != 200:
        raise RuntimeError(f"File not found: {url}")

    with open(zip_path, "wb") as f:
        for chunk in resp.iter_content(1024*1024):
            f.write(chunk)

    return zip_path

def extract_csv(zip_path: Path) -> pd.DataFrame:
    """
    Extract CSV from ZIP and return DataFrame with columns:
    t, Open, High, Low, Close, Volume
    """
    with zipfile.ZipFile(zip_path, "r") as zf:
        csv_name = zf.namelist()[0]
        with zf.open(csv_name) as f:
            df = pd.read_csv(f, header=None)

    df = df.iloc[:, :6]  # keep first 6 cols
    df.columns = ["t", "Open", "High", "Low", "Close", "Volume"]

    # ensure t is int64 safe
    df["t"] = pd.to_numeric(df["t"], errors="coerce")
    df = df.dropna(subset=["t"])
    df["t"] = df["t"].astype("int64")

    return df