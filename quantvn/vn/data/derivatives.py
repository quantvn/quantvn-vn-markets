import base64
import gzip
import io

import pandas as pd
import requests

from .utils import Config

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
