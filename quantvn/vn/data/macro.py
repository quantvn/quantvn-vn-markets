from __future__ import annotations

from typing import Optional
import requests
import pandas as pd
import io
from .utils import Config


class Macro:
    """Macro class để lấy dữ liệu Macro kinh tế (GDP, ...)."""

    def __init__(self):
        """Initialize Macro instance."""
        pass

    def get_gdp(self, type: str = "value") -> pd.DataFrame:
        """
        Get GDP macro data (values or index).

        Parameters
        ----------
        type : str
            "value" cho giá trị GDP hoặc "index" cho chỉ số phát triển.
            Default: "value"

        Returns
        -------
        pd.DataFrame
            GDP data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "value" or "index"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_value = macro.get_gdp(type="value")
        >>> df_index = macro.get_gdp(type="index")
        """
        if type not in ["value", "index"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'value' hoặc 'index'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/gdp",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_cpi(self, type: str = "total") -> pd.DataFrame:
        """
        Get CPI macro data (total or by region).

        Parameters
        ----------
        type : str
            "total" cho CPI tổng hoặc "by_region" cho CPI theo vùng.
            Default: "total"

        Returns
        -------
        pd.DataFrame
            CPI data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "total" or "by_region"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_total = macro.get_cpi(type="total")
        >>> df_region = macro.get_cpi(type="by_region")
        """
        if type not in ["total", "by_region"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'total' hoặc 'by_region'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/cpi",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_fdi(self, type: str = "total") -> pd.DataFrame:
        """
        Get FDI macro data (total or by sector).

        Parameters
        ----------
        type : str
            "total" cho FDI tổng hoặc "by_sector" cho FDI theo ngành.
            Default: "total"

        Returns
        -------
        pd.DataFrame
            FDI data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "total" or "by_sector"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_total = macro.get_fdi(type="total")
        >>> df_sector = macro.get_fdi(type="by_sector")
        """
        if type not in ["total", "by_sector"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'total' hoặc 'by_sector'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/fdi",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_m2(self, type: str = "value") -> pd.DataFrame:
        """
        Get M2 money supply macro data (value, growth rate, or GDP ratio).

        Parameters
        ----------
        type : str
            "value" cho giá trị M2, "growth_rate" cho tốc độ tăng, hoặc
            "gdp_ratio" cho tỷ lệ M2/GDP.
            Default: "value"

        Returns
        -------
        pd.DataFrame
            M2 data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "value", "growth_rate", or "gdp_ratio"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_value = macro.get_m2(type="value")
        >>> df_growth = macro.get_m2(type="growth_rate")
        >>> df_ratio = macro.get_m2(type="gdp_ratio")
        """
        if type not in ["value", "growth_rate", "gdp_ratio"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'value', 'growth_rate' hoặc 'gdp_ratio'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/m2",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_credit(self, type: str = "value") -> pd.DataFrame:
        """
        Get credit macro data (value or growth rate).

        Parameters
        ----------
        type : str
            "value" cho giá trị tín dụng hoặc "growth_rate" cho tốc độ tăng.
            Default: "value"

        Returns
        -------
        pd.DataFrame
            Credit data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "value" or "growth_rate"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_value = macro.get_credit(type="value")
        >>> df_growth = macro.get_credit(type="growth_rate")
        """
        if type not in ["value", "growth_rate"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'value' hoặc 'growth_rate'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/credit",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_population(self, type: str = "total") -> pd.DataFrame:
        """
        Get population macro data (total, growth rate, or distribution percent).

        Parameters
        ----------
        type : str
            "total" cho tổng số dân (Nghìn người), "growth_rate" cho tỷ lệ tăng (%),
            hoặc "distribution_percent" cho cơ cấu dân số (%).
            Default: "total"

        Returns
        -------
        pd.DataFrame
            Population data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "total", "growth_rate", or "distribution_percent"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_total = macro.get_population(type="total")
        >>> df_growth = macro.get_population(type="growth_rate")
        >>> df_dist = macro.get_population(type="distribution_percent")
        """
        if type not in ["total", "growth_rate", "distribution_percent"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'total', 'growth_rate' hoặc 'distribution_percent'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/population",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_labor_force(self, type: str = "total") -> pd.DataFrame:
        """
        Get labor force macro data (total or distribution percent).

        Parameters
        ----------
        type : str
            "total" cho tổng số lực lượng lao động (Nghìn người),
            hoặc "distribution_percent" cho cơ cấu lực lượng lao động (%).
            Default: "total"

        Returns
        -------
        pd.DataFrame
            Labor force data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "total" or "distribution_percent"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_total = macro.get_labor_force(type="total")
        >>> df_dist = macro.get_labor_force(type="distribution_percent")
        """
        if type not in ["total", "distribution_percent"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'total' hoặc 'distribution_percent'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/labor-force",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")

    def get_total_trade_value(self, type: str = "value") -> pd.DataFrame:
        """
        Get total trade value macro data (value or index).

        Parameters
        ----------
        type : str
            "value" cho giá trị thương mại (Triệu đô la Mỹ),
            hoặc "index" cho chỉ số phát triển (Năm trước = 100) - %.
            Default: "value"

        Returns
        -------
        pd.DataFrame
            Total trade value data với các cột tương ứng

        Raises
        ------
        ValueError
            If type is not "value" or "index"
        Exception
            If there is an error when calling the API.

        Examples
        --------
        >>> macro = Macro()
        >>> df_value = macro.get_total_trade_value(type="value")
        >>> df_index = macro.get_total_trade_value(type="index")
        """
        if type not in ["value", "index"]:
            raise ValueError(
                f"Type '{type}' không được hỗ trợ. Chỉ hỗ trợ 'value' hoặc 'index'."
            )

        api_key = Config.get_api_key()
        payload = {"type": type}

        response = requests.post(
            f"{Config.get_link_quantvn_data()}/vn/macro/total-trade-value",
            json=payload,
            headers={"x-api-key": api_key},
        )

        if response.status_code == 200:
            df = pd.read_parquet(io.BytesIO(response.content))
            return df
        else:
            raise Exception(f"Error: {response.status_code}, {response.text}")
