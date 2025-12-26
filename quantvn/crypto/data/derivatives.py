from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, Union

import pandas as pd
from tqdm import tqdm

from quantvn.crypto.data.download import download_monthly, extract_csv

__all__ = ["get_hist"]


def get_hist(
    symbol: str,
    interval: str = "1m",
    cache_dir: Optional[Union[str, Path]] = None,
) -> pd.DataFrame:
    """
    Fetch historical monthly data from Binance.

    start/end: str in "YYYY-MM-DD HH:MM:SS" format or datetime, in Vietnam time (UTC+7)
    Returns DataFrame in format:
    ["Date","time","Open","High","Low","Close","volume"]
    """
    cache_dir = Path(cache_dir or Path.home() / ".cache/quantvn")
    VN_TZ = timezone(timedelta(hours=7))

    # default start/end
    start_dt = datetime(2019, 7, 1, tzinfo=VN_TZ)
    end_dt = datetime(2022, 12, 31, 23, 59, 59, tzinfo=VN_TZ)

    # parse if string
    if isinstance(start_dt, str):
        start_dt = datetime.strptime(start_dt, "%Y-%m-%d %H:%M:%S").replace(
            tzinfo=VN_TZ
        )
    if isinstance(end_dt, str):
        end_dt = datetime.strptime(end_dt, "%Y-%m-%d %H:%M:%S").replace(tzinfo=VN_TZ)

    # generate list of months
    months = []
    dt = start_dt.replace(day=1)
    while dt <= end_dt:
        months.append(dt.strftime("%Y-%m"))
        if dt.month == 12:
            dt = dt.replace(year=dt.year + 1, month=1)
        else:
            dt = dt.replace(month=dt.month + 1)

    all_dfs = []
    for m in tqdm(months, desc=f"Downloading {symbol}", disable=True):
        try:
            zip_path = download_monthly(symbol, interval, m, cache_dir)
            df = extract_csv(zip_path)
            all_dfs.append(df)
        except Exception as e:
            print(f"Skip {symbol} {interval} {m}: {e}")

    if not all_dfs:
        return pd.DataFrame(
            columns=["Date", "time", "Open", "High", "Low", "Close", "volume"]
        )

    # concat all months
    df_all = pd.concat(all_dfs, ignore_index=True)
    df_all = (
        df_all.drop_duplicates(subset=["t"]).sort_values("t").reset_index(drop=True)
    )

    # convert timestamp t -> Asia/Ho_Chi_Minh
    df_all["t"] = pd.to_datetime(df_all["t"], unit="ms", errors="coerce", utc=True)
    df_all = df_all.dropna(subset=["t"])
    df_all["t"] = df_all["t"].dt.tz_convert(VN_TZ)

    # filter by start/end datetime
    df_all = df_all[(df_all["t"] >= start_dt) & (df_all["t"] <= end_dt)]

    # rename Volume -> volume
    df_all.rename(columns={"Volume": "volume"}, inplace=True)

    # tạo cột Date + time
    df_all["Date"] = df_all["t"].dt.strftime("%Y-%m-%d")
    df_all["time"] = df_all["t"].dt.strftime("%H:%M:%S")
    df_all["Datetime"] = df_all["t"]

    return df_all[
        ["Datetime", "Date", "time", "Open", "High", "Low", "Close", "volume"]
    ]
