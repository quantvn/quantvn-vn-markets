import base64
import gzip
import io

import pandas as pd
import requests
from datetime import datetime
from .utils import Config
from pathlib import Path
import time

# Định nghĩa các thành phần public của module
__all__ = ["get_hist"]

# Lấy URL của Lambda function từ Config
LAMBDA_URL = Config.get_link()


def get_hist(symbol: str, frequency: str):
    """
    Get historical data of derivatives VN30F1M and VN30F2M.

    Parameters
    ----------
    symbol : str
        Only supports VN30F1M (case-insensitive).
    frequency : str
        Timeframe to get data. Supported: "1m", "5m", "15m" (case-insensitive).
    Returns
    -------
    dict
        Historical data with information such as time, closing price, trading volume.

    Raises
    ------
    Exception
        If there is an error when calling the API.
    """
    sym = str(symbol).upper().strip()
    if sym != "VN30F1M":
        raise ValueError("Only VN30F1M is supported.")

    freq = str(frequency or "").lower()
    if freq not in {"1m", "5m", "15m"}:
        raise ValueError("frequency must be one of: '1m', '5m', '15m'.")

    api_key = Config.get_api_key()
    payload = {"symbol": sym, "frequency": freq}

    response = requests.post(
        f"{LAMBDA_URL}/data-derivatives",
        json=payload,
        headers={"x-api-key": api_key},
    )

    if response.status_code == 200:
        data = response.json()

        if isinstance(data, dict) and "base64" in data:
            try:
                decoded_data = base64.b64decode(data["base64"])

                with gzip.GzipFile(fileobj=io.BytesIO(decoded_data), mode="rb") as gz:
                    extracted_content = gz.read().decode("utf-8")
                    df = pd.read_csv(io.StringIO(extracted_content), index_col=0)

                df["Datetime"] = pd.to_datetime(df["Date"] + " " + df["time"])

                return df

            except Exception as e:
                return {"error": f"Failed to process base64 data: {str(e)}"}

        return pd.DataFrame(data)
    else:
        raise Exception(f"Error: {response.status_code}, {response.text}")


def get_dukascopy_candles(
    instrument: str,
    from_date: datetime,
    to_date: datetime,
    timeframe: str = "1m",
    force_refresh: bool = False,
    allow_local_rollup: bool = True,
    cache_dir: str | Path | None = None,
):
    timeframe = timeframe.strip().lower()
    if timeframe not in {"1m", "5m", "15m", "1h", "4h", "1d"}:
        raise ValueError(
            'timeframe must be one of: "1m", "5m", "15m", "1h", "4h", "1d".'
        )

    if not isinstance(from_date, datetime) or not isinstance(to_date, datetime):
        raise ValueError("from_date and to_date must be a datetime type")

    if cache_dir is None:
        cache_dir = Path.home() / ".cache/dukascopy"

    cache_dir = Path(cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    instrument = instrument.strip().lower()
    inst_record = get_dukascopy_instrument_detail(instrument)

    start_dt = from_date if from_date else inst_record["earliest"]
    end_dt = to_date if to_date else datetime.now()

    str_from = start_dt.date()
    str_to = end_dt.date()

    target_filename = f"{instrument}_{timeframe}_{str_from}_{str_to}.parquet"
    target_path = cache_dir / target_filename

    if target_path.exists() and not force_refresh:
        df = pd.read_parquet(target_path)
        df = df.set_index("timestamp")
        return df

    if allow_local_rollup and not force_refresh and timeframe != "1m":
        m1_filename = f"{instrument}_1m_{str_from}_{str_to}.parquet"
        m1_path = cache_dir / m1_filename
        if m1_path.exists():
            timeframe_conversation = {
                "1m": "1min",
                "5m": "5min",
                "15m": "15min",
                "1h": "1h",
                "4h": "4h",
                "1d": "1d",
            }
            df = pd.read_parquet(m1_path)

            df = df.sort_values("timestamp")
            df = df.set_index("timestamp")
            candle_df = (
                df.resample(
                    timeframe_conversation[timeframe], closed="left", label="left"
                )
                .agg(
                    {
                        "open": "first",
                        "high": "max",
                        "low": "min",
                        "close": "last",
                        "volume": "sum",
                    }
                )
                .dropna()
            )

            candle_df.to_parquet(target_path)
            return candle_df

    _download_dukascopy_candles(instrument, timeframe, from_date, to_date, target_path)

    return pd.read_parquet(target_path).set_index("timestamp")


def _download_dukascopy_candles(
    instrument: str,
    timeframe: str,
    from_date: datetime,
    to_date: datetime,
    output_path: Path,
):
    api_key = Config.get_api_key()

    parameters = {"instrument": instrument, "timeframe": timeframe}

    if from_date:
        parameters["from_date"] = from_date
    if to_date:
        parameters["to_date"] = to_date
    headers = {"x-api-key": api_key}
    try:
        response = requests.get(
            f"{LAMBDA_URL}/dukascopy/candles",
            params=parameters,
            headers=headers,
            stream=True,
            timeout=5000,
            allow_redirects=True,
        )

        response.raise_for_status()

        with open(output_path, "wb") as file:
            file.write(response.content)
    except requests.HTTPError:
        raise Exception(response.json())


def list_dukascopy_instruments():
    try:
        api_key = Config.get_api_key()
        headers = {"x-api-key": api_key}
        response = requests.get(f"{LAMBDA_URL}/dukascopy/instruments", headers=headers)
        response.raise_for_status()
        instrumens = response.json()
        return instrumens
    except requests.HTTPError:
        raise Exception(response.json())


def get_dukascopy_instrument_detail(instrument: str):
    try:
        api_key = Config.get_api_key()
        headers = {"x-api-key": api_key}

        response = requests.get(
            f"{LAMBDA_URL}/dukascopy/instrument",
            params={"instrument": instrument},
            headers=headers,
        )

        response.raise_for_status()

        instrumen_details = response.json()
        instrumen_details["earliest"] = datetime.strptime(
            instrumen_details["earliest"], "%Y-%m-%dT%H:%M:%S"
        )
        return instrumen_details
    except requests.HTTPError:
        raise Exception(response.json())


def search_dukascopy_instruments(keyword: str):
    parameters = {}
    if keyword:
        parameters["keyword"] = keyword

    try:
        api_key = Config.get_api_key()
        headers = {"x-api-key": api_key}
        response = requests.get(
            f"{LAMBDA_URL}/dukascopy/instrument-search",
            params=parameters,
            headers=headers,
        )

        response.raise_for_status()

        instrumens = response.json()

        return instrumens
    except requests.HTTPError:
        raise Exception(response.json())
