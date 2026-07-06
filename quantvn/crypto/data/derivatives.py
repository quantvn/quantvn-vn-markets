from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd

from quantvn.crypto.data.download import VALID_INTERVALS, download_monthly, extract_csv

__all__ = ["get_hist"]

VN_TZ = timezone(timedelta(hours=7))


def get_hist(
    symbol: str,
    interval: str = "1m",
    cache_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Fetch historical OHLCV data from Binance Vision (spot), 2019-07 to 2022-12.

    Args:
        symbol:    Binance symbol, e.g. "BTCUSDT"
        interval:  Candle interval. Valid values: 1m 3m 5m 15m 30m 1h 2h 4h 6h 8h 12h 1d 3d 1w 1M
        cache_dir: Local cache directory (default: ~/.cache/quantvn)

    Returns:
        DataFrame with columns [Datetime, Date, time, Open, High, Low, Close, volume]
    """
    if interval not in VALID_INTERVALS:
        raise ValueError(
            f"Invalid interval {interval!r}. "
            f"Choose one of: {', '.join(VALID_INTERVALS)}"
        )

    cache_dir = Path(cache_dir or Path.home() / ".cache/quantvn")

    start_dt = datetime(2019, 7, 1, tzinfo=VN_TZ)
    end_dt = datetime(2022, 12, 31, 23, 59, 59, tzinfo=VN_TZ)

    # generate list of months to download
    months = []
    dt = start_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    while dt <= end_dt:
        months.append(dt.strftime("%Y-%m"))
        dt = dt.replace(month=dt.month + 1) if dt.month < 12 else dt.replace(year=dt.year + 1, month=1)

    # parallel download
    results: dict[str, pd.DataFrame] = {}

    def _fetch(month: str):
        zip_path = download_monthly(symbol, interval, month, cache_dir)
        return month, extract_csv(zip_path)

    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch, m): m for m in months}
        for future in as_completed(futures):
            month = futures[future]
            try:
                m, df = future.result()
                results[m] = df
            except Exception as e:
                print(f"Skip {symbol} {interval} {month}: {e}")

    if not results:
        return pd.DataFrame(columns=["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"])

    df_all = pd.concat([results[m] for m in sorted(results)], ignore_index=True)
    df_all = df_all.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)

    df_all["t"] = pd.to_datetime(df_all["t"], unit="ms", errors="coerce", utc=True)
    df_all = df_all.dropna(subset=["t"])
    df_all["t"] = df_all["t"].dt.tz_convert(VN_TZ)

    df_all = df_all[(df_all["t"] >= start_dt) & (df_all["t"] <= end_dt)]

    df_all.rename(columns={"Volume": "volume"}, inplace=True)
    df_all["Date"] = df_all["t"].dt.strftime("%Y-%m-%d")
    df_all["time"] = df_all["t"].dt.strftime("%H:%M:%S")
    df_all["Datetime"] = df_all["t"]

    return df_all[["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]].reset_index(drop=True)
