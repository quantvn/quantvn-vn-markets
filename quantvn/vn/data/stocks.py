#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
stocks.py — Lấy OHLCV từ Entrade API với pivot/fill logic.

Public:
- list_liquid_asset()
- get_hist(asset_name, resolution="m")  # resolution: "m" | "h" | "1H" | "1D"

Đặc điểm:
- Lấy data 1 request duy nhất từ Entrade API
- Pivot và forward fill để xử lý missing data
- Convert timezone sang UTC+7 (Vietnam)
- Output: DataFrame ["Date","time","Open","High","Low","Close","volume"]
"""

from __future__ import annotations

import datetime as dt
import io
import itertools
import json
import os
import time
from typing import Any, Dict, List, Optional, Union

import pandas as pd
import requests

from .const import (
    CHART_URL,
    GRAPHQL_URL,
    INTERVAL_MAP,
    INTRADAY_MAP,
    INTRADAY_URL,
    OHLC_COLUMNS,
    OHLC_RENAME,
    PRICE_DEPTH_URL,
    PRICE_INFO_MAP,
    TRADING_URL,
)
from .core import send_request
from .utils import Config

__all__ = ["list_liquid_asset", "get_hist"]

# ===== Cấu hình nguồn Entrade API =====
_STOCKS_API_BASE = "https://services.entrade.com.vn/chart-api/v2/ohlcs/stock"
_TIMEOUT = 30  # giây
_MAX_REQUESTS = 2000  # giới hạn an toàn số lần phân trang

# Giữ cho API cũ list_liquid_asset (nếu bạn dùng ở nơi khác)
LAMBDA_URL = Config.get_link()


def _backend_headers() -> Dict[str, str]:
    """
    Headers mặc định cho backend FastAPI:
    - luôn cố gắng gắn x-api-key (nếu cấu hình có).
    """
    api_key = Config.get_api_key()
    return {"x-api-key": api_key} if api_key else {}


# ===== Backend FastAPI (this repo) =====
def _backend_api_base() -> str:
    """
    Base URL cho FastAPI backend (v1). Ưu tiên env:
      - LAMBDA_URL (vd: https://d207hp2u5nyjgn.cloudfront.net)
    """
    base = LAMBDA_URL
    return base.rstrip("/")


def _backend_get_json(
    path: str, params: Optional[dict] = None, timeout: int = _TIMEOUT
):
    """
    GET JSON từ backend FastAPI.
    - path: /company/... hoặc company/... (auto join với base)
    """
    base = _backend_api_base()
    url = f"{base}/{str(path).lstrip('/')}"
    resp = requests.get(
        url, params=params or {}, timeout=timeout, headers=_backend_headers()
    )
    resp.raise_for_status()
    return resp.json()


def list_liquid_asset() -> pd.DataFrame:
    """Retrieve a list of highly liquid assets (qua Lambda cũ)."""
    api_key = Config.get_api_key()
    r = requests.get(
        f"{LAMBDA_URL}/list-liquid-asset",
        headers={"x-api-key": api_key},
        timeout=_TIMEOUT,
    )
    r.raise_for_status()
    return pd.DataFrame(r.json())


# ===================== Helpers: Parse & Chuẩn hóa =====================


def _json_relaxed(text: str) -> Optional[Union[dict, list]]:
    """
    Thử parse JSON "chịu lỗi" theo 3 bước:
      1) json.loads toàn bộ
      2) Cắt substring giữa ký tự JSON đầu/cuối (lọc rác log) rồi loads
      3) NDJSON: mỗi dòng 1 JSON
    Trả về dict/list nếu parse được, ngược lại None.
    """
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    starts = [i for i in [text.find("{"), text.find("[")] if i != -1]
    ends = [i for i in [text.rfind("}"), text.rfind("]")] if i != -1]
    if starts and ends and max(ends) > min(starts):
        s, e = min(starts), max(ends) + 1
        try:
            return json.loads(text[s:e])
        except json.JSONDecodeError:
            pass

    items = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            items.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    if items:
        if isinstance(items[0], list):
            out = []
            for it in items:
                if isinstance(it, list):
                    out.extend(it)
            return out
        return items

    return None


def _scan_all_json_blocks(text: str) -> List[Any]:
    """
    Quét *tất cả* khối JSON (object/array) nối tiếp trong text (fix lỗi 'Extra data').
    Trả về danh sách các object đã parse (dict/list). Bỏ qua block lỗi.
    """
    s = text.lstrip()
    i, n = 0, len(s)
    blocks: List[Any] = []

    while i < n:
        while i < n and s[i] not in "{[":
            i += 1
        if i >= n:
            break

        opening = s[i]
        closing = "}" if opening == "{" else "]"
        depth = 0
        in_str = False
        esc = False
        j = i

        while j < n:
            ch = s[j]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
            else:
                if ch == '"':
                    in_str = True
                elif ch == opening:
                    depth += 1
                elif ch == closing:
                    depth -= 1
                    if depth == 0:
                        j += 1
                        break
            j += 1

        if depth != 0:
            break

        block = s[i:j]
        try:
            obj = json.loads(block)
            blocks.append(obj)
        except Exception:
            pass
        i = j

    return blocks


def _merge_ohlcv_dict_blocks(blocks: List[dict]) -> dict:
    """Gộp nhiều dict kiểu {t,o,h,l,c,(v)} thành một dict duy nhất (append theo chiều dọc)."""
    keys = set().union(*[set(b.keys()) for b in blocks])
    merged: Dict[str, List[Any]] = {}
    for k in keys:
        buf: List[Any] = []
        for b in blocks:
            v = b.get(k, None)
            if isinstance(v, list):
                buf.extend(v)
            else:
                if k == "v":
                    buf.extend([None] * len(b.get("t", [])))
        if buf:
            merged[k] = buf
    return merged


def _as_dataframe(parsed: Any, raw_text: str) -> pd.DataFrame:
    """
    Đưa bất kỳ cấu trúc phổ biến nào về DataFrame:
    - dict-of-arrays {t,o,h,l,c,(v)}
    - list-of-dicts
    - list-of-lists (để pandas đoán)
    - CSV fallback
    """
    if parsed is not None:
        if (
            isinstance(parsed, list)
            and parsed
            and all(
                isinstance(b, dict) and {"t", "o", "h", "l", "c"}.issubset(b.keys())
                for b in parsed
            )
        ):
            parsed = _merge_ohlcv_dict_blocks(parsed)

        if isinstance(parsed, dict):
            if "data" in parsed:
                parsed = parsed["data"]
            if isinstance(parsed, dict) and {"t", "o", "h", "l", "c"}.issubset(
                parsed.keys()
            ):
                n = len(parsed["t"])
                vol = parsed.get("v", [None] * n)
                return pd.DataFrame(
                    {
                        "t": parsed["t"],
                        "o": parsed["o"],
                        "h": parsed["h"],
                        "l": parsed["l"],
                        "c": parsed["c"],
                        "v": vol,
                    }
                )
            try:
                return pd.DataFrame(parsed)
            except Exception:
                return pd.DataFrame([parsed])

        if isinstance(parsed, list):
            if not parsed:
                return pd.DataFrame()
            if isinstance(parsed[0], dict):
                return pd.DataFrame(parsed)
            return pd.DataFrame(parsed)

    try:
        return pd.read_csv(io.StringIO(raw_text))
    except Exception:
        return pd.DataFrame()


def _flatten_if_cell_is_list(df: pd.DataFrame) -> pd.DataFrame:
    """Nếu mỗi ô chứa list (ví dụ cột 't' là list epoch), flatten thành từng dòng."""
    if df.empty:
        return df
    cols = set(df.columns)
    tcol = _pick(cols, "t", "time", "timestamp", "ts", "date", "dt")
    if tcol is None:
        return df

    first = df.iloc[0][tcol]
    if not isinstance(first, (list, tuple)):
        return df  # đã phẳng

    def chain(series):
        seqs = [x for x in series.dropna().tolist() if isinstance(x, (list, tuple))]
        return list(itertools.chain.from_iterable(seqs)) if seqs else []

    t = chain(df[tcol])
    n = len(t)

    def vals(name_candidates):
        c = _pick(set(df.columns), *name_candidates)
        if c is None:
            return [None] * n
        v = chain(df[c])
        return (v[:n] + [None] * max(0, n - len(v))) if v else [None] * n

    out = pd.DataFrame(
        {
            "t": t,
            "o": vals(("o", "open", "Open")),
            "h": vals(("h", "high", "High")),
            "l": vals(("l", "low", "Low")),
            "c": vals(("c", "close", "Close")),
            "v": vals(("v", "vol", "volume", "Volume")),
        }
    )
    return out


def _pick(cols, *cands):
    for c in cands:
        if c in cols:
            return c
    return None


def _normalize_ohlcv_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    Chuẩn hóa về cột: Date (datetime), Open, High, Low, Close, Volume
    - Tự nhận epoch giây/ms
    - KHÔNG đổi timezone
    """
    if df.empty:
        return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume"])

    ren = {}
    if "t" in df.columns:
        ren["t"] = "Date"
    if "time" in df.columns:
        ren["time"] = "Date"
    for a, b in [
        ("o", "Open"),
        ("open", "Open"),
        ("h", "High"),
        ("high", "High"),
        ("l", "Low"),
        ("low", "Low"),
        ("c", "Close"),
        ("close", "Close"),
        ("v", "Volume"),
        ("vol", "Volume"),
        ("Volume", "Volume"),
    ]:
        if a in df.columns:
            ren[a] = b
    df = df.rename(columns=ren)

    for col in ["Date", "Open", "High", "Low", "Close", "Volume"]:
        if col not in df.columns:
            df[col] = pd.NA

    s = df["Date"]
    if pd.api.types.is_numeric_dtype(s):
        unit = "ms" if (s.dropna().astype("int64") > 1_000_000_000_000).any() else "s"
        # Kết quả là timezone-naive (không đổi UTC)
        df["Date"] = pd.to_datetime(s, unit=unit)
    else:
        df["Date"] = pd.to_datetime(s, errors="coerce")

    for col in ["Open", "High", "Low", "Close", "Volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df = df.dropna(subset=["Date"]).sort_values("Date").reset_index(drop=True)
    return df[["Date", "Open", "High", "Low", "Close", "Volume"]]


def _format_date_time_output(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input: df có cột Date (datetime), Open/High/Low/Close/Volume
    Output: Date (YYYY-MM-DD), time (HH:MM:SS), Open.., volume (lowercase)
    KHÔNG đổi timezone; chỉ format từ datetime hiện có.
    """
    if df.empty:
        return pd.DataFrame(
            columns=["Date", "time", "Open", "High", "Low", "Close", "volume"]
        )

    out = df.copy()
    out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
    out["time"] = pd.to_datetime(
        out["Date"] + " " + pd.to_datetime(df["Date"]).dt.strftime("%H:%M:%S")
    ).dt.strftime("%H:%M:%S")
    # Cách trên đảm bảo "time" lấy từ phần giờ gốc; không chuyển TZ.

    if "Volume" in out.columns:
        out = out.rename(columns={"Volume": "volume"})

    for col in ["Open", "High", "Low", "Close", "volume"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    out = out[["Date", "time", "Open", "High", "Low", "Close", "volume"]]
    out = out.sort_values(["Date", "time"], kind="mergesort").reset_index(drop=True)
    return out


def _extract_last_epoch(df_seg: pd.DataFrame) -> Optional[int]:
    """Lấy epoch giây cuối cùng của đoạn df_seg (sau normalize)."""
    if df_seg.empty:
        return None
    ns = pd.to_datetime(df_seg["Date"]).astype("int64").max()
    return int(ns // 1_000_000_000)


# ===================== Fetch từng trang thời gian =====================


def _fetch_entrade_data(symbol: str, resolution: str) -> pd.DataFrame:
    """
    Lấy toàn bộ OHLCV data từ Entrade API (1 request).
    Returns raw DataFrame với columns: t, o, h, l, c, v
    """
    url = (
        f"{_STOCKS_API_BASE}?from=0"
        f"&resolution={resolution}"
        f"&symbol={symbol}"
        f"&to=9999999999"
    )

    try:
        response = requests.get(url, timeout=_TIMEOUT)
        response.raise_for_status()
        data = response.json()

        # Entrade trả về list of dicts hoặc dict of arrays
        if isinstance(data, list):
            df = pd.DataFrame(data)
        elif isinstance(data, dict):
            df = pd.DataFrame(data)
        else:
            return pd.DataFrame()

        # Lấy 6 cột đầu: t, o, h, l, c, v
        if len(df.columns) >= 6:
            df = df.iloc[:, :6]
            df.columns = ["t", "o", "h", "l", "c", "v"]

        return df

    except Exception as e:
        raise ValueError(f"Failed to fetch data from Entrade: {e}")


# ===================== Reorganized: Company & Finance =====================

# ===== VCI GraphQL API Constants =====
VCI_GRAPHQL_URL = "https://trading.vietcap.com.vn/data-mt/graphql"

FULL_COMPANY_QUERY = """
query Query($ticker: String!, $lang: String!) {
  AnalysisReportFiles(ticker: $ticker, langCode: $lang) {
    date
    description
    link
    name
    __typename
  }
  News(ticker: $ticker, langCode: $lang) {
    id
    organCode
    ticker
    newsTitle
    newsSubTitle
    friendlySubTitle
    newsImageUrl
    newsSourceLink
    createdAt
    publicDate
    updatedAt
    langCode
    newsId
    newsShortContent
    newsFullContent
    closePrice
    referencePrice
    floorPrice
    ceilingPrice
    percentPriceChange
    __typename
  }
  TickerPriceInfo(ticker: $ticker) {
    financialRatio {
      yearReport
      lengthReport
      updateDate
      revenue
      revenueGrowth
      netProfit
      netProfitGrowth
      ebitMargin
      roe
      roic
      roa
      pe
      pb
      eps
      currentRatio
      cashRatio
      quickRatio
      interestCoverage
      ae
      fae
      netProfitMargin
      grossMargin
      ev
      issueShare
      ps
      pcf
      bvps
      evPerEbitda
      at
      fat
      acp
      dso
      dpo
      epsTTM
      charterCapital
      RTQ4
      charterCapitalRatio
      RTQ10
      dividend
      ebitda
      ebit
      le
      de
      ccc
      RTQ17
      __typename
    }
    ticker
    exchange
    ev
    ceilingPrice
    floorPrice
    referencePrice
    openPrice
    matchPrice
    closePrice
    priceChange
    percentPriceChange
    highestPrice
    lowestPrice
    totalVolume
    highestPrice1Year
    lowestPrice1Year
    percentLowestPriceChange1Year
    percentHighestPriceChange1Year
    foreignTotalVolume
    foreignTotalRoom
    averageMatchVolume2Week
    foreignHoldingRoom
    currentHoldingRatio
    maxHoldingRatio
    __typename
  }
  Subsidiary(ticker: $ticker) {
    id
    organCode
    subOrganCode
    percentage
    subOrListingInfo {
      enOrganName
      organName
      __typename
    }
    __typename
  }
  Affiliate(ticker: $ticker) {
    id
    organCode
    subOrganCode
    percentage
    subOrListingInfo {
      enOrganName
      organName
      __typename
    }
    __typename
  }
  CompanyListingInfo(ticker: $ticker) {
    id
    issueShare
    en_History
    history
    en_CompanyProfile
    companyProfile
    icbName3
    enIcbName3
    icbName2
    enIcbName2
    icbName4
    enIcbName4
    financialRatio {
      id
      ticker
      issueShare
      charterCapital
      __typename
    }
    __typename
  }
  OrganizationManagers(ticker: $ticker) {
    id
    ticker
    fullName
    positionName
    positionShortName
    en_PositionName
    en_PositionShortName
    updateDate
    percentage
    quantity
    __typename
  }
  OrganizationShareHolders(ticker: $ticker) {
    id
    ticker
    ownerFullName
    en_OwnerFullName
    quantity
    percentage
    updateDate
    __typename
  }
  OrganizationResignedManagers(ticker: $ticker) {
    id
    ticker
    fullName
    positionName
    positionShortName
    en_PositionName
    en_PositionShortName
    updateDate
    percentage
    quantity
    __typename
  }
  OrganizationEvents(ticker: $ticker) {
    id
    organCode
    ticker
    eventTitle
    en_EventTitle
    publicDate
    issueDate
    sourceUrl
    eventListCode
    ratio
    value
    recordDate
    exrightDate
    eventListName
    en_EventListName
    __typename
  }
}
""".strip()


# ===== VCI Finance Ratio (CompanyFinancialRatio) =====
FINANCE_RATIO_QUERY = """
fragment Ratios on CompanyFinancialRatio {
  ticker
  yearReport
  lengthReport
  updateDate
  revenue
  revenueGrowth
  netProfit
  netProfitGrowth
  ebitMargin
  roe
  roic
  roa
  pe
  pb
  eps
  currentRatio
  cashRatio
  quickRatio
  interestCoverage
  netProfitMargin
  grossMargin
  ev
  issueShare
  ps
  pcf
  bvps
  evPerEbitda
  charterCapital
  dividend
  ebitda
  ebit
}

query Query($ticker: String!, $period: String!) {
  CompanyFinancialRatio(ticker: $ticker, period: $period) {
    ratio {
      ...Ratios
    }
    period
  }
}
""".strip()


def _build_vci_headers(user_agent: Optional[str] = None) -> Dict[str, str]:
    """Build headers for VCI GraphQL API requests."""
    ua = user_agent or (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    return {
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9,vi-VN;q=0.8,vi;q=0.7",
        "Connection": "keep-alive",
        "Content-Type": "application/json",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "DNT": "1",
        "Referer": "https://trading.vietcap.com.vn/",
        "Origin": "https://trading.vietcap.com.vn/",
        "User-Agent": ua,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-site",
        "sec-ch-ua-platform": '"Windows"',
        "sec-ch-ua-mobile": "?0",
    }


def _vci_graphql_request(
    query: str,
    variables: Dict[str, Any],
    timeout: int = 30,
    max_retries: int = 3,
    backoff_seconds: float = 1.5,
) -> Dict[str, Any]:
    """Send GraphQL request to VCI API with retry logic."""
    headers = _build_vci_headers()
    payload = {"query": query, "variables": variables}

    last_err: Optional[Exception] = None

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                VCI_GRAPHQL_URL,
                headers=headers,
                json=payload,
                timeout=timeout,
            )
            resp.raise_for_status()

            data = resp.json()
            if "errors" in data and data["errors"]:
                raise RuntimeError(f"GraphQL errors: {data['errors']}")

            if "data" not in data:
                raise RuntimeError(f"Unexpected response: {data}")

            return data["data"]

        except Exception as e:
            last_err = e
            if attempt < max_retries:
                time.sleep(backoff_seconds * attempt)
                continue
            raise

    raise last_err or RuntimeError("Unknown error")


def _slice_page(items: list[Any], page_size: int, page: int) -> list[Any]:
    """Slice list by page/page_size (TCBS-like signature compatibility)."""
    try:
        size = int(page_size)
        p = int(page)
    except Exception:
        size, p = 50, 0
    if size <= 0:
        return items
    start = max(0, p) * size
    end = start + size
    return items[start:end]


class _CompanyProvider:
    """Internal provider interface (do not use directly)."""

    def overview(self) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def profile(self) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def shareholders(
        self, page_size: int = 50, page: int = 0
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def officers(
        self, page_size: int = 50, page: int = 0
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def subsidiaries(
        self, page_size: int = 100, page: int = 0
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def events(
        self, page_size: int = 15, page: int = 0
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def news(
        self, page_size: int = 15, page: int = 0
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError

    def ratio_summary(self) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError


class _VCICompanyProvider(_CompanyProvider):
    """Company provider via VCI GraphQL API."""

    def __init__(self, symbol: str, *, lang: str = "vi"):
        self.symbol = str(symbol).upper().strip()
        self.lang = lang or "vi"
        self._cache: Optional[Dict[str, Any]] = None

    def _company_full(self) -> Dict[str, Any]:
        if self._cache is None:
            self._cache = _vci_graphql_request(
                query=FULL_COMPANY_QUERY,
                variables={"ticker": self.symbol, "lang": self.lang},
            )
        return self._cache

    def overview(self) -> pd.DataFrame:
        """
        vnstock-like overview for VCI source.

        Output columns (snake_case), best-effort:
        - symbol, id, issue_share, history, company_profile,
          icb_name3, icb_name2, icb_name4,
          financial_ratio_issue_share, charter_capital
        """
        data = self._company_full()
        info = data.get("CompanyListingInfo") or {}
        if not isinstance(info, dict) or not info:
            return pd.DataFrame()

        fr = info.get("financialRatio") or {}
        row = {
            "symbol": self.symbol,
            "id": info.get("id"),
            "issue_share": info.get("issueShare"),
            "history": info.get("history"),
            "company_profile": info.get("companyProfile"),
            "icb_name3": info.get("icbName3"),
            "icb_name2": info.get("icbName2"),
            "icb_name4": info.get("icbName4"),
            "financial_ratio_issue_share": (
                fr.get("issueShare") if isinstance(fr, dict) else None
            ),
            "charter_capital": (
                fr.get("charterCapital") if isinstance(fr, dict) else None
            ),
        }
        return pd.DataFrame([row])

    def profile(self) -> pd.DataFrame:
        data = self._company_full()
        info = data.get("CompanyListingInfo")
        if not info:
            return pd.DataFrame()
        return pd.json_normalize(info)

    def shareholders(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        data = self._company_full()
        items = data.get("OrganizationShareHolders") or []
        if not isinstance(items, list) or not items:
            return pd.DataFrame()
        return pd.DataFrame(_slice_page(items, page_size, page))

    def officers(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        # VCI field: OrganizationManagers (map to officers/key persons)
        data = self._company_full()
        items = data.get("OrganizationManagers") or []
        if not isinstance(items, list) or not items:
            return pd.DataFrame()
        return pd.DataFrame(_slice_page(items, page_size, page))

    def subsidiaries(self, page_size: int = 100, page: int = 0) -> pd.DataFrame:
        data = self._company_full()
        items = data.get("Subsidiary") or []
        if not isinstance(items, list) or not items:
            return pd.DataFrame()
        return pd.DataFrame(_slice_page(items, page_size, page))

    def events(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        data = self._company_full()
        items = data.get("OrganizationEvents") or []
        if not isinstance(items, list) or not items:
            return pd.DataFrame()
        return pd.DataFrame(_slice_page(items, page_size, page))

    def news(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        data = self._company_full()
        items = data.get("News") or []
        if not isinstance(items, list) or not items:
            return pd.DataFrame()
        return pd.DataFrame(_slice_page(items, page_size, page))

    def ratio_summary(self) -> pd.DataFrame:
        """
        Return a 1-row DataFrame of financial ratios.
        Keeps backward-compat columns: year/quarter (best-effort).
        """
        data = self._company_full()
        info = (data.get("TickerPriceInfo") or {}).get("financialRatio") or {}
        if not isinstance(info, dict) or not info:
            return pd.DataFrame()

        # Backward-compat for quantvn.vn.data.core expectations
        year = info.get("yearReport")
        length = info.get("lengthReport")
        quarter = (
            length
            if isinstance(length, (int, float)) and int(length) in (1, 2, 3, 4)
            else pd.NA
        )

        row = dict(info)
        row["ticker"] = self.symbol
        row["year"] = year
        row["quarter"] = quarter
        return pd.DataFrame([row])


class _TCBSCompanyProvider(_CompanyProvider):
    """Company provider via TCBS tcanalysis endpoints (kept as optional fallback)."""

    def __init__(self, symbol: str):
        self.symbol = str(symbol).upper().strip()

    def overview(self) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/ticker/{self.symbol}/overview"
        data = send_request(url)
        return pd.DataFrame(data, index=[0])

    def profile(self) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/company/{self.symbol}/overview"
        data = send_request(url)
        return pd.json_normalize(data)

    def shareholders(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/company/{self.symbol}/large-share-holders"
        data = send_request(url, params={"page": page, "size": page_size})
        items = (data or {}).get("listShareHolder", [])
        return pd.json_normalize(items)

    def officers(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/company/{self.symbol}/key-officers"
        data = send_request(url, params={"page": page, "size": page_size})
        items = (data or {}).get("listKeyOfficer", [])
        return pd.json_normalize(items)

    def subsidiaries(self, page_size: int = 100, page: int = 0) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/company/{self.symbol}/sub-companies"
        data = send_request(url, params={"page": page, "size": page_size})
        items = (data or {}).get("listSubCompany", [])
        return pd.json_normalize(items)

    def events(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/ticker/{self.symbol}/events-news"
        data = send_request(url, params={"page": page, "size": page_size})
        items = (data or {}).get("listEventNews", [])
        return pd.DataFrame(items)

    def news(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/ticker/{self.symbol}/activity-news"
        data = send_request(url, params={"page": page, "size": page_size})
        items = (data or {}).get("listActivityNews", [])
        return pd.DataFrame(items)

    def ratio_summary(self) -> pd.DataFrame:
        BASE = "https://apipubaws.tcbs.com.vn"
        ANALYSIS = "tcanalysis"
        url = f"{BASE}/{ANALYSIS}/v1/ticker/{self.symbol}/ratios"
        try:
            data = send_request(url)
            return (
                pd.DataFrame(data, index=[0])
                if isinstance(data, dict)
                else pd.DataFrame(data)
            )
        except Exception:
            url2 = f"{BASE}/{ANALYSIS}/v1/finance/{self.symbol}/financialratio"
            data = send_request(url2)
            return pd.DataFrame(data)


class _BackendCompanyProvider(_CompanyProvider):
    """Company provider via backend FastAPI endpoints (/v1/company/*)."""

    def __init__(
        self, symbol: str, *, lang: str = "vi", api_base: Optional[str] = None
    ):
        self.symbol = str(symbol).upper().strip()
        self.lang = lang or "vi"
        self.api_base = api_base or LAMBDA_URL or ""

    def _get(self, path: str, params: Optional[dict] = None):
        """
        Generic GET helper for backend REST API.

        `path` là path không bao gồm symbol (ví dụ: "/company/overview").
        Mã chứng khoán (symbol) và các tham số khác truyền qua `params`.
        """
        if self.api_base:
            base = self.api_base.rstrip("/")
            url = f"{base}/{str(path).lstrip('/')}"
            resp = requests.get(
                url,
                params=params or {},
                timeout=_TIMEOUT,
                headers=_backend_headers(),
            )
            resp.raise_for_status()
            return resp.json()
        return _backend_get_json(path, params=params, timeout=_TIMEOUT)

    def overview(self) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/overview", params={"symbol": self.symbol, "lang": self.lang}
            )
            return (
                pd.DataFrame([data])
                if isinstance(data, dict) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def profile(self) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/profile", params={"symbol": self.symbol, "lang": self.lang}
            )
            return (
                pd.json_normalize(data)
                if isinstance(data, dict) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def shareholders(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/shareholders",
                params={
                    "symbol": self.symbol,
                    "lang": self.lang,
                    "page_size": page_size,
                    "page": page,
                },
            )
            return (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def officers(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/officers",
                params={
                    "symbol": self.symbol,
                    "lang": self.lang,
                    "page_size": page_size,
                    "page": page,
                },
            )
            return (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def subsidiaries(self, page_size: int = 100, page: int = 0) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/subsidiaries",
                params={
                    "symbol": self.symbol,
                    "lang": self.lang,
                    "page_size": page_size,
                    "page": page,
                },
            )
            return (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def events(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/events",
                params={
                    "symbol": self.symbol,
                    "lang": self.lang,
                    "page_size": page_size,
                    "page": page,
                },
            )
            return (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def news(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/news",
                params={
                    "symbol": self.symbol,
                    "lang": self.lang,
                    "page_size": page_size,
                    "page": page,
                },
            )
            return (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
        except Exception:
            return pd.DataFrame()

    def ratio_summary(self) -> pd.DataFrame:
        try:
            data = self._get(
                "/company/ratio-summary",
                params={"symbol": self.symbol, "lang": self.lang},
            )
            return (
                pd.DataFrame([data])
                if isinstance(data, dict) and data
                else pd.DataFrame()
            )
        except Exception as e:
            print(e)
            return pd.DataFrame()


class Company:
    """
    Public Company API (stable surface).

    Only exposes:
    - overview()
    - profile()
    - shareholders(page_size=50, page=0)
    - officers(page_size=50, page=0)
    - subsidiaries(page_size=100, page=0)
    - events(page_size=15, page=0)
    - news(page_size=15, page=0)
    - ratio_summary()

    Internally uses a provider so you can swap/add APIs later easily.
    """

    def __init__(
        self,
        symbol: str,
        source: str = "BACKEND",
        lang: str = "vi",
        api_base: Optional[str] = None,
    ):
        self.symbol = str(symbol).upper().strip()
        self.source = (source or "BACKEND").upper()
        self.lang = lang or "vi"

        if self.source in ("BACKEND", "API", "FASTAPI"):
            self._provider = _BackendCompanyProvider(
                self.symbol, lang=self.lang, api_base=api_base
            )
        elif self.source == "VCI":
            self._provider: _CompanyProvider = _VCICompanyProvider(
                self.symbol, lang=self.lang
            )
        elif self.source == "TCBS":
            self._provider = _TCBSCompanyProvider(self.symbol)
        elif self.source == "AUTO":
            # Try BACKEND first; then VCI; if it fails, fallback to TCBS.
            try:
                self._provider = _BackendCompanyProvider(
                    self.symbol, lang=self.lang, api_base=api_base
                )
                _ = self._provider.overview()
            except Exception:
                try:
                    self._provider = _VCICompanyProvider(self.symbol, lang=self.lang)
                    _ = self._provider.overview()
                except Exception:
                    self._provider = _TCBSCompanyProvider(self.symbol)
        else:
            raise ValueError("source must be one of: 'BACKEND', 'VCI', 'TCBS', 'AUTO'")

    def overview(self) -> pd.DataFrame:
        return self._provider.overview()

    def profile(self) -> pd.DataFrame:
        return self._provider.profile()

    def shareholders(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        return self._provider.shareholders(page_size=page_size, page=page)

    def officers(self, page_size: int = 50, page: int = 0) -> pd.DataFrame:
        return self._provider.officers(page_size=page_size, page=page)

    def subsidiaries(self, page_size: int = 100, page: int = 0) -> pd.DataFrame:
        return self._provider.subsidiaries(page_size=page_size, page=page)

    def events(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        return self._provider.events(page_size=page_size, page=page)

    def news(self, page_size: int = 15, page: int = 0) -> pd.DataFrame:
        return self._provider.news(page_size=page_size, page=page)

    def ratio_summary(self) -> pd.DataFrame:
        return self._provider.ratio_summary()


# ===== VCI GraphQL Finance Ratio Query =====
FINANCE_RATIO_QUERY = """
fragment Ratios on CompanyFinancialRatio {
  ticker
  yearReport
  lengthReport
  updateDate
  revenue
  revenueGrowth
  netProfit
  netProfitGrowth
  ebitMargin
  roe
  roic
  roa
  pe
  pb
  eps
  currentRatio
  cashRatio
  quickRatio
  interestCoverage
  netProfitMargin
  grossMargin
  ev
  issueShare
  ps
  pcf
  bvps
  evPerEbitda
  charterCapital
  dividend
  ebitda
  ebit
}

query Query($ticker: String!, $period: String!) {
  CompanyFinancialRatio(ticker: $ticker, period: $period) {
    ratio {
      ...Ratios
    }
    period
  }
}
""".strip()


class _FinanceProvider:
    """Internal provider interface (do not use directly)."""

    def ratio(
        self, period: str = "Q", dropna: bool = False
    ) -> pd.DataFrame:  # pragma: no cover
        raise NotImplementedError


def _normalize_finance_ratio_df(
    df: pd.DataFrame, symbol: str, dropna: bool
) -> pd.DataFrame:
    """
    Chuẩn hóa DataFrame tỷ số tài chính về cùng format như nguồn VCI:
    - Đảm bảo có cột ticker
    - yearReport/lengthReport -> year/quarter (nếu có)
    - Áp dụng dropna (xóa cột toàn NaN) nếu cần.
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    # Best-effort rename cho các field phổ biến
    rename_map = {}
    if "yearReport" in out.columns:
        rename_map["yearReport"] = "year"
    if "lengthReport" in out.columns:
        rename_map["lengthReport"] = "quarter"
    if rename_map:
        out = out.rename(columns=rename_map)

    # Đảm bảo ticker tồn tại
    if "ticker" not in out.columns:
        out["ticker"] = symbol

    if dropna:
        out = out.dropna(axis=1, how="all")

    return out


class _VCIFinanceProvider(_FinanceProvider):
    """Finance provider via VCI GraphQL API - only supports ratio()."""

    def __init__(self, symbol: str, *, lang: str = "vi"):
        self.symbol = str(symbol).upper().strip()
        self.lang = lang or "vi"

    def ratio(self, period: str = "Q", dropna: bool = False) -> pd.DataFrame:
        """
        Fetch financial ratios from VCI CompanyFinancialRatio API.

        Args:
            period: "Q" for quarter, "Y" for year (as in working test script)
            dropna: drop all-empty columns
        """
        try:
            data = _vci_graphql_request(
                query=FINANCE_RATIO_QUERY,
                variables={"ticker": self.symbol, "period": period},
            )
        except Exception:
            # If VCI ratio endpoint fails, return empty DataFrame
            return pd.DataFrame()

        block = (data or {}).get("CompanyFinancialRatio") or {}
        ratios = block.get("ratio") or []
        if not isinstance(ratios, list) or not ratios:
            return pd.DataFrame()

        raw_df = pd.DataFrame(ratios)
        return _normalize_finance_ratio_df(raw_df, self.symbol, dropna)


class _BackendFinanceProvider(_FinanceProvider):
    """Finance provider via backend FastAPI endpoints (/v1/finance/*)."""

    def __init__(self, symbol: str, *, api_base: Optional[str] = None):
        self.symbol = str(symbol).upper().strip()
        self.api_base = api_base or LAMBDA_URL or ""

    def _get(self, path: str, params: Optional[dict] = None):
        if self.api_base:
            base = self.api_base.rstrip("/")
            url = f"{base}/{str(path).lstrip('/')}"
            resp = requests.get(
                url,
                params=params or {},
                timeout=_TIMEOUT,
                headers=_backend_headers(),
            )
            resp.raise_for_status()
            return resp.json()
        return _backend_get_json(path, params=params, timeout=_TIMEOUT)

    def ratio(self, period: str = "Q", dropna: bool = False) -> pd.DataFrame:
        try:
            per = (period or "Q").strip().upper()
            data = self._get(
                "/finance/ratio",
                params={
                    "symbol": self.symbol,
                    "period": per,
                    "dropna": int(bool(dropna)),
                },
            )
            raw_df = (
                pd.DataFrame(data)
                if isinstance(data, list) and data
                else pd.DataFrame()
            )
            return _normalize_finance_ratio_df(raw_df, self.symbol, dropna)
        except Exception:
            return pd.DataFrame()


class Finance:
    """
    Public Finance API - Tỷ số tài chính từ VCI GraphQL API.

    Chỉ hỗ trợ:
    - ratio(period="Q" | "Y", dropna=False)    # Tỷ số tài chính từ VCI CompanyFinancialRatio

    Args:
        symbol: Mã cổ phiếu (VD: "HPG", "VIC")
        source: Nguồn dữ liệu (chỉ hỗ trợ "VCI")
        lang: Ngôn ngữ (mặc định "vi")
    """

    def __init__(
        self,
        symbol: str,
        source: str = "BACKEND",
        lang: str = "vi",
        api_base: Optional[str] = None,
    ):
        self.symbol = str(symbol).upper().strip()
        self.source = (source or "BACKEND").upper()
        self.lang = lang or "vi"

        if self.source in ("BACKEND", "API", "FASTAPI"):
            self._provider = _BackendFinanceProvider(self.symbol, api_base=api_base)
        elif self.source == "VCI":
            self._provider = _VCIFinanceProvider(self.symbol, lang=self.lang)
        else:
            raise ValueError("source must be one of: 'BACKEND', 'VCI'")

    def ratio(self, period: str = "Q", dropna: bool = False) -> pd.DataFrame:
        """
        Tỷ số tài chính từ VCI CompanyFinancialRatio endpoint.

        Args:
            period: "Q" (quý) hoặc "Y" (năm)
            dropna: Xóa các cột hoàn toàn trống

        Returns:
            DataFrame chứa các tỷ số tài chính như revenue, netProfit, roe, pe, pb, etc.
        """
        return self._provider.ratio(period=period, dropna=dropna)


# ===================== Reorganized: Fund =====================


class Fund:
    """Mutual funds via Fmarket."""

    def __init__(self):
        pass

    def listing(self, fund_type: str = "") -> pd.DataFrame:
        BASE = "https://api.fmarket.vn/res/products"
        url = f"{BASE}/filter"
        payload = {
            "types": ["NEW_FUND", "TRADING_FUND"],
            "issuerIds": [],
            "sortOrder": "DESC",
            "sortField": "navTo6Months",
            "page": 1,
            "pageSize": 500,
            "isIpo": False,
            "fundAssetTypes": [] if not fund_type else [fund_type],
            "bondRemainPeriods": [],
            "searchField": "",
            "isBuyByReward": False,
            "thirdAppIds": [],
        }
        try:
            data = send_request(url, method="POST", payload=payload)
            rows = (data or {}).get("data", {}).get("rows", [])
            df = pd.json_normalize(rows)
            return df
        except Exception:
            data = send_request(f"{BASE}/public", params={"page": 1, "size": 500})
            df = pd.json_normalize((data or {}).get("data", []))
            if fund_type and "dataFundAssetType.name" in df.columns:
                df = df[df["dataFundAssetType.name"].eq(fund_type)]
            return df

    def filter(self, q: str) -> pd.DataFrame:
        df = self.listing()
        if df.empty:
            return df
        mask = False
        for col in [c for c in ["name", "shortName"] if c in df.columns]:
            mask = mask | df[col].astype(str).str.contains(q, case=False, na=False)
        return df[mask]

    @staticmethod
    def _resolve_candidates(code_or_id: str) -> list[str]:
        cands = []
        key = str(code_or_id).strip()
        if key:
            cands.append(key)
        try:
            _df = Fund().listing()
            if not _df.empty:
                cols = _df.columns

                def _add(val):
                    if val is None:
                        return
                    s = str(val).strip()
                    if s and s not in cands:
                        cands.append(s)

                if "code" in cols and _df["code"].notna().any():
                    m = _df["code"].astype(str).str.upper().eq(key.upper())
                    if m.any():
                        r = _df[m].iloc[0]
                        for k in ["code", "id", "vsdFeeId"]:
                            if k in cols:
                                _add(r.get(k))
                if "id" in cols and _df["id"].notna().any():
                    m = _df["id"].astype(str).eq(key)
                    if m.any():
                        r = _df[m].iloc[0]
                        for k in ["code", "id", "vsdFeeId"]:
                            if k in cols:
                                _add(r.get(k))
                if "vsdFeeId" in cols and _df["vsdFeeId"].notna().any():
                    m = _df["vsdFeeId"].astype(str).eq(key)
                    if m.any():
                        r = _df[m].iloc[0]
                        for k in ["code", "id", "vsdFeeId"]:
                            if k in cols:
                                _add(r.get(k))
        except Exception:
            pass
        return cands

    @staticmethod
    def _try_paths(paths: list[str]) -> pd.DataFrame:
        for url in paths:
            try:
                data = send_request(url)
                if isinstance(data, list):
                    return pd.DataFrame(data)
                return pd.json_normalize(data)
            except Exception:
                continue
        return pd.DataFrame()

    class details:
        @staticmethod
        def nav_report(code_or_id: str) -> pd.DataFrame:
            BASE = "https://api.fmarket.vn/res/products"
            cands = Fund._resolve_candidates(code_or_id)
            paths = [f"{BASE}/public/{c}/nav-report" for c in cands] + [
                f"{BASE}/{c}/nav-report" for c in cands
            ]
            return Fund._try_paths(paths)

        @staticmethod
        def top_holding(code_or_id: str) -> pd.DataFrame:
            BASE = "https://api.fmarket.vn/res/products"
            cands = Fund._resolve_candidates(code_or_id)
            paths = [f"{BASE}/public/{c}/top-holding" for c in cands] + [
                f"{BASE}/{c}/top-holding" for c in cands
            ]
            return Fund._try_paths(paths)

        @staticmethod
        def industry_holding(code_or_id: str) -> pd.DataFrame:
            BASE = "https://api.fmarket.vn/res/products"
            cands = Fund._resolve_candidates(code_or_id)
            paths = [f"{BASE}/public/{c}/industry-holding" for c in cands] + [
                f"{BASE}/{c}/industry-holding" for c in cands
            ]
            return Fund._try_paths(paths)

        @staticmethod
        def asset_holding(code_or_id: str) -> pd.DataFrame:
            BASE = "https://api.fmarket.vn/res/products"
            cands = Fund._resolve_candidates(code_or_id)
            paths = [f"{BASE}/public/{c}/asset-holding" for c in cands] + [
                f"{BASE}/{c}/asset-holding" for c in cands
            ]
            return Fund._try_paths(paths)


# ===================== Reorganized: Listing =====================


class Listing:
    def __init__(self, source="VCI"):
        self.source = source

    def all_symbols(self):
        # Try to use liquid asset list if available
        try:
            df = list_liquid_asset()
            if not df.empty:
                cols = set(df.columns)
                sym_col = (
                    "symbol"
                    if "symbol" in cols
                    else ("ticker" if "ticker" in cols else None)
                )
                ex_col = "exchange" if "exchange" in cols else None
                if sym_col:
                    out = pd.DataFrame(
                        {
                            "symbol": df[sym_col].astype(str),
                            "short_name": df.get(
                                "short_name", pd.Series([None] * len(df))
                            ),
                            "exchange": (
                                df[ex_col]
                                if ex_col in df.columns
                                else pd.Series([None] * len(df))
                            ),
                        }
                    )
                    return out.dropna(subset=["symbol"]).reset_index(drop=True)
        except Exception:
            pass
        # Fallback minimal known set
        return pd.DataFrame(
            [
                {"symbol": "HPG", "short_name": "HoaPhat", "exchange": "HOSE"},
                {"symbol": "VIC", "short_name": "Vingroup", "exchange": "HOSE"},
                {"symbol": "VNM", "short_name": "Vinamilk", "exchange": "HOSE"},
            ]
        )

    def symbols_by_exchange(self):
        df = self.all_symbols()
        if not df.empty and "exchange" in df.columns:
            out: dict[str, list[str]] = {"HOSE": [], "HNX": [], "UPCOM": []}
            for ex, g in df.groupby(df["exchange"].fillna("HOSE")):
                if ex in out:
                    out[ex] = g["symbol"].astype(str).dropna().unique().tolist()
            return out
        return {"HOSE": ["HPG", "VIC", "VNM"], "HNX": [], "UPCOM": []}

    def symbols_by_group(self, group="VN30"):
        return []

    def symbols_by_industries(self):
        return pd.DataFrame(columns=["symbol", "icb_industry"])

    def industries_icb(self):
        return pd.DataFrame(columns=["icb_code", "icb_name"])


# ===================== Reorganized: Market Quote (VCI) =====================


class Quote:
    """Market data via VCI: OHLCV history, intraday tick, price depth."""

    def __init__(self, symbol, source="VCI"):
        self.symbol = symbol
        self.source = source

    def _estimate_countback(self, start_dt, end_dt, interval):
        if interval in ["1D", "1W", "1M"]:
            if interval == "1D":
                return max(1, (end_dt.date() - start_dt.date()).days + 1)
            if interval == "1W":
                return max(1, ((end_dt.date() - start_dt.date()).days // 7) + 1)
            return max(
                1,
                (end_dt.year - start_dt.year) * 12
                + (end_dt.month - start_dt.month)
                + 1,
            )
        if interval == "1H":
            return max(1, int((end_dt - start_dt).total_seconds() // 3600) + 1)
        step = {"1m": 1, "5m": 5, "15m": 15, "30m": 30}[interval]
        return max(1, int((end_dt - start_dt).total_seconds() // 60) // step + 1)

    def history(self, start, end=None, interval="1D"):
        assert interval in INTERVAL_MAP, f"Unsupported interval: {interval}"
        start_dt = dt.datetime.strptime(start, "%Y-%m-%d")
        end_dt = (
            dt.datetime.utcnow() + pd.Timedelta(days=1)
            if end is None
            else (dt.datetime.strptime(end, "%Y-%m-%d") + pd.Timedelta(days=1))
        )
        count_back = self._estimate_countback(start_dt, end_dt, interval)
        payload = {
            "timeFrame": INTERVAL_MAP[interval],
            "symbols": [self.symbol],
            "to": int(end_dt.timestamp()),
            "countBack": count_back,
        }
        data = send_request(TRADING_URL + CHART_URL, method="POST", payload=payload)
        arr = data[0] if isinstance(data, list) and data else []
        if not arr:
            return pd.DataFrame(
                columns=["time", "open", "high", "low", "close", "volume"]
            )

        df = pd.DataFrame(arr)[OHLC_COLUMNS].rename(columns=OHLC_RENAME)
        ts = pd.to_numeric(df["time"], errors="coerce")
        df["time"] = pd.to_datetime(ts, unit="s")
        df = df[df["time"] >= start_dt].reset_index(drop=True)
        return df

    def intraday(self, page_size=100, last_time=None):
        url = f"{TRADING_URL}{INTRADAY_URL}/LEData/getAll"
        payload = {
            "symbol": self.symbol,
            "limit": int(page_size),
            "truncTime": last_time,
        }
        data = send_request(url, method="POST", payload=payload)
        if not data:
            return pd.DataFrame(columns=list(INTRADAY_MAP.values()))

        df = pd.DataFrame(data)
        cols = list(INTRADAY_MAP.keys())
        df = df[cols].rename(columns=INTRADAY_MAP)

        vals = pd.to_numeric(df["time"], errors="coerce")
        if vals.notna().any():
            unit = "ms" if vals.dropna().astype("int64").gt(10**12).any() else "s"
            df["time"] = pd.to_datetime(vals, unit=unit)
        else:
            df["time"] = pd.to_datetime(df["time"], errors="coerce")

        return df

    def price_depth(self):
        data = send_request(
            PRICE_DEPTH_URL, method="POST", payload={"symbol": self.symbol}
        )
        if not data:
            return pd.DataFrame(
                columns=[
                    "price",
                    "acc_volume",
                    "acc_buy_volume",
                    "acc_sell_volume",
                    "acc_undefined_volume",
                ]
            )
        df = pd.DataFrame(data)
        df = df[
            [
                "priceStep",
                "accumulatedVolume",
                "accumulatedBuyVolume",
                "accumulatedSellVolume",
                "accumulatedUndefinedVolume",
            ]
        ]
        return df.rename(
            columns={
                "priceStep": "price",
                "accumulatedVolume": "acc_volume",
                "accumulatedBuyVolume": "acc_buy_volume",
                "accumulatedSellVolume": "acc_sell_volume",
                "accumulatedUndefinedVolume": "acc_undefined_volume",
            }
        )


# ===================== Reorganized: Global quotes (MSN/Yahoo) =====================

MSN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.msn.com",
    "Referer": "https://www.msn.com/en-us/money",
}

CURRENCY_ID = {
    "USDVND": "avyufr",
    "JPYVND": "ave8sm",
    "EURUSD": "av932w",
    "USDCNY": "avym77",
    "USDKRW": "avyoyc",
}
CRYPTO_ID = {
    "BTC": "c2111",
    "ETH": "c2112",
    "USDT": "c2115",
    "BNB": "c2113",
    "ADA": "c2114",
    "SOL": "c2116",
}
INDICES_ID = {
    "DJI": "a6qja2",
    "INX": "a33k6h",
    "COMP": "a3oxnm",
    "N225": "a9j7bh",
    "VNI": "aqk2nm",
}
Y_INDICES = {
    "DJI": "^DJI",
    "INX": "^GSPC",
    "COMP": "^IXIC",
    "N225": "^N225",
    "VNI": "^VNINDEX",
}
Y_CRYPTO = {
    "BTC": "BTC-USD",
    "ETH": "ETH-USD",
    "BNB": "BNB-USD",
    "ADA": "ADA-USD",
    "SOL": "SOL-USD",
}


def _normalize_df_global(df: pd.DataFrame) -> pd.DataFrame:
    for col in ["time", "open", "high", "low", "close", "volume"]:
        if col not in df.columns:
            df[col] = None
    return df[["time", "open", "high", "low", "close", "volume"]].reset_index(drop=True)


def _chart_msn(symbol_id, start=None, end=None, interval="1D") -> pd.DataFrame:
    BASE = "https://assets.msn.com/service/Finance"
    url = f"{BASE}/Charts/TimeRange"
    params = {
        "ids": symbol_id,
        "type": "All",
        "timeframe": 1,
        "wrapodata": "false",
        "ocid": "finance-utils-peregrine",
        "cm": "en-us",
        "it": "web",
        "scn": "ANON",
    }
    data = send_request(url, params=params, headers=MSN_HEADERS)
    series = None
    if isinstance(data, list) and data and isinstance(data[0], dict):
        series = data[0].get("series") or (
            data[0].get("charts", [{}])[0].get("series")
            if data[0].get("charts")
            else None
        )
    elif isinstance(data, dict):
        series = data.get("series") or (
            data.get("charts", [{}])[0].get("series") if data.get("charts") else None
        )
    if not series:
        return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])
    if isinstance(series, list):
        df = pd.DataFrame(series)
    else:
        df = pd.DataFrame([series])
    rename = {
        "timeStamps": "time",
        "openPrices": "open",
        "pricesHigh": "high",
        "pricesLow": "low",
        "prices": "close",
        "volumes": "volume",
    }
    df.rename(
        columns={k: v for k, v in rename.items() if k in df.columns}, inplace=True
    )
    for col in ["time", "open", "high", "low", "close", "volume"]:
        if (
            col in df.columns
            and df[col].apply(lambda x: isinstance(x, (list, tuple))).any()
        ):
            df = df.explode(col)
    df["time"] = pd.to_numeric(df.get("time"), errors="coerce")
    df["time"] = pd.to_datetime(df["time"], unit="s", errors="coerce")
    return _normalize_df_global(df)


def _yahoo_symbol(kind: str, symbol: str) -> list[str]:
    if kind == "fx":
        return [f"{symbol}=X", f"{symbol[:3]}{symbol[3:]}=X"]
    if kind == "crypto":
        return [Y_CRYPTO.get(symbol, f"{symbol}-USD")]
    if kind == "index":
        return [Y_INDICES.get(symbol, symbol)]
    return [symbol]


def _interval_map_yahoo(interval: str) -> tuple[str, str]:
    if interval in ("1m", "5m", "15m", "30m", "60m", "1H"):
        return ("1mo", "1m")
    if interval in ("1W",):
        return ("6mo", "1d")
    if interval in ("1M",):
        return ("2y", "1d")
    return ("1y", "1d")


def _chart_yahoo(
    kind: str, symbol: str, start=None, end=None, interval="1D"
) -> pd.DataFrame:
    rng, itv = _interval_map_yahoo(interval)
    for ysym in _yahoo_symbol(kind, symbol):
        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ysym}"
            params = {
                "range": rng,
                "interval": itv,
                "includePrePost": "false",
                "events": "div,splits",
            }
            data = send_request(
                url,
                params=params,
                headers={
                    "User-Agent": MSN_HEADERS["User-Agent"],
                    "Accept": "application/json, text/plain, */*",
                },
            )
            res = (data or {}).get("chart", {}).get("result", [])
            if not res:
                continue
            r0 = res[0]
            ts = r0.get("timestamp", []) or r0.get("meta", {}).get(
                "regularTradingPeriod", []
            )
            ind = r0.get("indicators", {})
            q = (ind.get("quote") or [{}])[0]
            df = pd.DataFrame(
                {
                    "time": pd.to_datetime(ts, unit="s", errors="coerce"),
                    "open": q.get("open"),
                    "high": q.get("high"),
                    "low": q.get("low"),
                    "close": q.get("close"),
                    "volume": q.get("volume"),
                }
            )
            if start:
                df = df[df["time"] >= pd.to_datetime(start)]
            if end:
                df = df[df["time"] <= pd.to_datetime(end)]
            if not df.empty:
                return _normalize_df_global(df)
        except Exception:
            continue
    return pd.DataFrame(columns=["time", "open", "high", "low", "close", "volume"])


class _Wrap:
    def __init__(self, id_map, kind: str):
        self.id_map = id_map
        self.kind = kind

    class _Quote:
        def __init__(self, sid, kind, raw_symbol):
            self.sid = sid
            self.kind = kind
            self.raw_symbol = raw_symbol

        def history(self, start, end, interval="1D"):
            try:
                df = _chart_msn(self.sid, start, end, interval)
                if df is not None and not df.empty:
                    return df
            except Exception:
                pass
            return _chart_yahoo(self.kind, self.raw_symbol, start, end, interval)

    def __call__(self, symbol):
        sid = self.id_map.get(symbol)
        return type("Obj", (), {"quote": self._Quote(sid, self.kind, symbol)})()


class FX:
    def __init__(self):
        self._wrap = _Wrap(CURRENCY_ID, "fx")

    def __call__(self, symbol):
        return self._wrap(symbol)


class Crypto:
    def __init__(self):
        self._wrap = _Wrap(CRYPTO_ID, "crypto")

    def __call__(self, symbol):
        return self._wrap(symbol)


class WorldIndex:
    def __init__(self):
        self._wrap = _Wrap(INDICES_ID, "index")

    def __call__(self, symbol):
        return self._wrap(symbol)


class Global:
    def fx(self, symbol):
        return FX()(symbol)

    def crypto(self, symbol):
        return Crypto()(symbol)

    def world_index(self, symbol):
        return WorldIndex()(symbol)


class MSN(Global):
    pass


# ===================== Reorganized: Trading =====================

_PRICEBOARD_QUERY = """
query PriceBoard($tickers:[String!]){
  priceBoard(tickers:$tickers){
    ticker open_price ceiling_price floor_price reference_price
    highest_price lowest_price price_change percent_price_change
    foreign_total_volume foreign_total_room foreign_holding_room
    average_match_volume2_week
  }
}
"""


class Trading:
    @staticmethod
    def _fallback(symbols):
        rows = []
        now = pd.Timestamp.utcnow()
        start = (now - pd.Timedelta(days=10)).strftime("%Y-%m-%d")
        end = now.strftime("%Y-%m-%d")
        for sym in symbols:
            try:
                q = Quote(sym)
                tick = q.intraday(page_size=1)
                price = float(tick["price"].iloc[0]) if not tick.empty else None
                hist = q.history(start=start, end=end, interval="1D")
                if len(hist) >= 2:
                    ref = float(hist["close"].iloc[-2])
                elif len(hist) == 1:
                    ref = float(hist["close"].iloc[-1])
                else:
                    ref = None
                change = (
                    (price - ref) if (price is not None and ref is not None) else None
                )
                pct = (
                    (change / ref * 100.0)
                    if (change is not None and ref not in (None, 0))
                    else None
                )
                rows.append(
                    {
                        "symbol": sym,
                        "open": None,
                        "ceiling": None,
                        "floor": None,
                        "ref_price": ref,
                        "high": None,
                        "low": None,
                        "price_change": change,
                        "price_change_pct": pct,
                        "foreign_volume": None,
                        "foreign_room": None,
                        "foreign_holding_room": None,
                        "avg_match_volume_2w": None,
                    }
                )
            except Exception:
                rows.append(
                    {
                        "symbol": sym,
                        "open": None,
                        "ceiling": None,
                        "floor": None,
                        "ref_price": None,
                        "high": None,
                        "low": None,
                        "price_change": None,
                        "price_change_pct": None,
                        "foreign_volume": None,
                        "foreign_room": None,
                        "foreign_holding_room": None,
                        "avg_match_volume_2w": None,
                    }
                )
        return pd.DataFrame(rows)

    @staticmethod
    def price_board(symbols):
        payload = {
            "operationName": "PriceBoard",
            "query": _PRICEBOARD_QUERY,
            "variables": {"tickers": list(symbols)},
        }
        try:
            data = send_request(
                GRAPHQL_URL,
                method="POST",
                headers={"Content-Type": "application/json"},
                payload=payload,
            )
            rows = (data or {}).get("data", {}).get("priceBoard", [])
            if rows:
                df = pd.DataFrame(rows).rename(columns=PRICE_INFO_MAP)
                return df
        except Exception:
            pass
        return Trading._fallback(symbols)


# ===================== Public: get_hist =====================


def get_hist(asset_name: str, resolution: str = "1H") -> pd.DataFrame:
    """
    Lấy toàn bộ OHLCV từ Entrade API với pivot/fill logic để xử lý missing data.

    Parameters:
    -----------
    asset_name : str
        Mã cổ phiếu (ví dụ: "HPG", "VNM")
    resolution : str
        Khung thời gian: chỉ hỗ trợ "1H" (bắt buộc).
        Mặc định: "1H"

    Returns:
    --------
    DataFrame với columns: ["Date", "time", "Open", "High", "Low", "Close", "volume"]
    """
    if not isinstance(asset_name, str) or not asset_name.strip():
        raise ValueError("asset_name phải là chuỗi hợp lệ (ví dụ: 'HPG').")

    # Map resolution to Entrade format
    res_map = {
        "m": "1",  # 1 minute
        "h": "1H",  # 1 hour
        "1h": "1H",
        "1d": "1D",
        "d": "1D",
    }
    res = res_map.get((resolution or "m").lower(), resolution)
    symbol = asset_name.strip().upper()

    # Lấy raw data từ Entrade (1 request)
    df = _fetch_entrade_data(symbol, res)

    if df.empty:
        return pd.DataFrame(
            columns=["Date", "time", "Open", "High", "Low", "Close", "volume"]
        )

    # Convert timestamp sang datetime UTC+7 (Vietnam timezone)
    df["t"] = (
        df["t"]
        .astype(int)
        .apply(lambda x: dt.datetime.utcfromtimestamp(x) + dt.timedelta(hours=7))
    )

    # Đổi tên columns
    df.columns = ["Date", "Open", "High", "Low", "Close", "Volume"]

    # Tách Date và time
    df["time"] = df["Date"].astype(str).str[11:]  # HH:MM:SS
    df["Date"] = df["Date"].astype(str).str[:10]  # YYYY-MM-DD

    # Pivot Close theo Date x time để fill missing data
    close_pivot = df.pivot(index="Date", columns="time", values="Close")
    close_pivot = close_pivot.dropna(axis=1, thresh=len(close_pivot) - 30)
    close_pivot = close_pivot.ffill(axis=1)
    close_stacked = close_pivot.stack().reset_index()
    close_stacked.columns = ["Date", "time", "Close"]

    # Pivot Volume theo Date x time
    volume_pivot = df.pivot(index="Date", columns="time", values="Volume")
    volume_pivot = volume_pivot.dropna(axis=1, thresh=len(volume_pivot) - 30)
    volume_pivot = volume_pivot.ffill(axis=1)
    volume_stacked = volume_pivot.stack().reset_index()

    # Merge Close và Volume
    close_stacked["volume"] = volume_stacked.iloc[:, 2]

    # Merge với Open, High, Low từ data gốc
    merged = pd.merge(
        close_stacked[["Date", "time", "Close", "volume"]],
        df[["Date", "time", "Open", "High", "Low"]],
        on=["Date", "time"],
        how="left",
    )

    # Sắp xếp và forward fill các giá trị còn thiếu
    ohlc = merged[["Date", "time", "Open", "High", "Low", "Close", "volume"]].ffill()

    return ohlc
