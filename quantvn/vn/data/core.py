
import time, random, requests
import pandas as pd
import numpy as np
from typing import Optional

DEFAULT_TIMEOUT = 25

if "_CACHE" not in globals():
    _CACHE = {}

def _fetch_price_df(symbol: str, timeframe: str = "h") -> pd.DataFrame:
    try:
        from quantvn.vn.data import stocks
    except Exception as e:
        raise ImportError("Cần quantvn + client(apikey=...) để lấy giá.") from e
    df = stocks.get_hist(symbol, timeframe)
    cols = _detect_price_columns(df)
    return df.rename(columns={
        cols["date"]:"Date", cols["time"]:"time",
        cols["open"]:"Open", cols["high"]:"High",
        cols["low"]:"Low",   cols["close"]:"Close",
        cols["volume"]:"Volume",
    })

def _fetch_fund_df(symbol: str) -> pd.DataFrame:
    try:
        from quantvn.vn.data import Company
    except Exception as e:
        raise ImportError("Cần quantvn + client(apikey=...) để lấy ratio_summary().") from e
    df = Company(symbol).ratio_summary()
    if "ticker" not in df.columns:
        df = df.copy(); df["ticker"] = symbol
    if "year" not in df.columns or "quarter" not in df.columns:
        raise KeyError("ratio_summary() thiếu cột 'year'/'quarter'.")
    return df

def _quarter_end_date(year: int, quarter: int) -> pd.Timestamp:
    """Ngày cuối quý theo (year, quarter). Nếu quarter lạ -> dùng 31/12."""
    if pd.isna(year) or pd.isna(quarter):
        return pd.NaT
    y = int(year); q = int(quarter)
    if   q == 1: return pd.Timestamp(y, 3, 31)
    elif q == 2: return pd.Timestamp(y, 6, 30)
    elif q == 3: return pd.Timestamp(y, 9, 30)
    elif q == 4: return pd.Timestamp(y, 12, 31)
    else:        return pd.Timestamp(y, 12, 31)

def merge_fund_into_price(
    price_df: pd.DataFrame,
    fund_df: pd.DataFrame,
    *,
    price_date_col: str = "Date",
    price_time_col: str = "time",
    ticker_col: str = "ticker",
    quarter_col: str = "quarter",
    year_col: str = "year",
    assume_ticker: Optional[str] = None,
    report_release_lag_days: int = 0,
    drop_all_nan_cols: bool = True
) -> pd.DataFrame:
    """
    Gộp các cột (fund_df) vào price_df bằng merge_asof (backward) theo ngày hiệu lực
    của báo cáo (cuối quý + lag nếu có). Giữ nguyên OHLCV.
    """
    out = price_df.copy()

    # 1) dt ở bảng giá
    if price_time_col in out.columns and price_time_col is not None:
        out["dt"] = pd.to_datetime(out[price_date_col].astype(str) + " " + out[price_time_col].astype(str))
    else:
        out["dt"] = pd.to_datetime(out[price_date_col])

    # 2) ticker ở bảng giá (nếu thiếu)
    if ticker_col not in out.columns:
        if assume_ticker is None:
            uniq = fund_df.get(ticker_col, pd.Series(dtype=object)).dropna().unique().tolist()
            assume_ticker = uniq[0] if uniq else "TICKER"
        out[ticker_col] = assume_ticker

    # 3) Chuẩn bị bảng fund
    f = fund_df.copy()
    for c in f.columns:
        if c in (ticker_col, year_col, quarter_col):
            continue
        if not pd.api.types.is_numeric_dtype(f[c]):
            f[c] = pd.to_numeric(f[c], errors="ignore")

    # 4) Ngày hiệu lực báo cáo
    f["report_date"] = [_quarter_end_date(y, q) for y, q in zip(f[year_col], f[quarter_col])]
    if report_release_lag_days:
        f["effective_date"] = f["report_date"] + pd.to_timedelta(report_release_lag_days, unit="D")
    else:
        f["effective_date"] = f["report_date"]

    # 5) Chọn cột merge
    id_cols = {ticker_col, year_col, quarter_col, "report_date", "effective_date"}
    value_cols = [c for c in f.columns if c not in id_cols]

    if drop_all_nan_cols and value_cols:
        keep_mask = f[value_cols].notna().any(axis=0)
        value_cols = list(pd.Index(value_cols)[keep_mask])

    right = f[[ticker_col, "effective_date"] + value_cols].sort_values([ticker_col, "effective_date"])
    left = out.sort_values([ticker_col, "dt"])

    # 6) merge_asof theo ticker
    merged = pd.merge_asof(
        left,
        right,
        left_on="dt",
        right_on="effective_date",
        by=ticker_col,
        direction="backward",
        allow_exact_matches=True,
    )

    # 7) Dọn cột phụ
    merged = merged.drop(columns=["effective_date"], errors="ignore")
    return merged

def _ua(source="vietmarket"):
    return {
        "User-Agent": f"{source}/1.0 (+https://example.local)",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://example.local",
        "Referer": "https://example.local/",
    }

def send_request(url, method="GET", headers=None, params=None, payload=None,
                 retries=2, backoff=(0.6, 1.2), timeout=DEFAULT_TIMEOUT):
    h = _ua()
    if headers:
        h.update(headers)
    for attempt in range(retries + 1):
        try:
            if method.upper() == "GET":
                r = requests.get(url, headers=h, params=params, timeout=timeout)
            else:
                r = requests.post(url, headers=h, params=params, json=payload, timeout=timeout)
            r.raise_for_status()
            if "application/json" in r.headers.get("Content-Type", ""):
                return r.json()
            return r.text
        except Exception:
            if attempt >= retries:
                raise
            time.sleep(random.uniform(*backoff))


def add_all_ta_features(
    df,
    open: str = "Open",
    high: str = "High",
    low: str = "Low",
    close: str = "Close",
    volume: str = "Volume",
    fillna: bool = True,
):
    """
    Thêm toàn bộ technical indicators từ thư viện `ta` vào DataFrame.
    Giữ nguyên signature giống `ta.add_all_ta_features` để sử dụng y hệt.

    Parameters
    ----------
    df : pandas.DataFrame
        DataFrame phải có các cột giá/khối lượng tương ứng.
    open,high,low,close,volume : str
        Tên cột trong df.
    fillna : bool
        Nếu True, sẽ điền các giá trị NaN theo mặc định của thư viện `ta`.

    Returns
    -------
    pandas.DataFrame
        DataFrame đầu vào + các cột TA features.
    """
    try:
        from ta import add_all_ta_features as _ta_add_all_ta_features
        from ta.utils import dropna as _ta_dropna
    except Exception as e:
        raise ImportError(
            "Thiếu thư viện 'ta'. Hãy cài: pip install ta"
        ) from e

    # Làm sạch NaN theo chuẩn của 'ta'
    _df = _ta_dropna(df.copy())

    # Gọi trực tiếp hàm gốc
    return _ta_add_all_ta_features(
        _df,
        open=open,
        high=high,
        low=low,
        close=close,
        volume=volume,
        fillna=fillna,
    )

def _detect_price_columns(df: pd.DataFrame):
    cmap = {c.lower(): c for c in df.columns}
    def pick(*names):
        for n in names:
            if n.lower() in cmap:
                return cmap[n.lower()]
        return None
    date = pick("Date","date")
    timecol = pick("time","Time","datetime","Datetime")
    open_ = pick("Open","open")
    high = pick("High","high")
    low  = pick("Low","low")
    close= pick("Close","close","price")
    vol  = pick("Volume","volume","vol")
    if not all([date,timecol,open_,high,low,close,vol]):
        raise KeyError(f"Thiếu cột OHLCV/time. Columns hiện có: {list(df.columns)}")
    return {"date":date,"time":timecol,"open":open_,"high":high,"low":low,"close":close,"volume":vol}


def _add_yoy_cols(df: pd.DataFrame, group_col: str, value_col: str, lag_map: dict):
    """Trả về (yoy_pct, yoy_abs) theo lag suy luận của từng ticker."""
    prev = _group_shift(df, group_col, value_col, lag_map)
    yoy_abs = df[value_col] - prev
    with np.errstate(divide="ignore", invalid="ignore"):
        yoy = np.where(prev != 0, (df[value_col] / prev) - 1.0, np.nan)
    return pd.Series(yoy, index=df.index, dtype="float64"), pd.Series(yoy_abs, index=df.index, dtype="float64")

def _rolling_monotonic_flag(s: pd.Series, window: int, increasing=True) -> pd.Series:
    """1.0 nếu chuỗi trong 'window' kỳ gần nhất đơn điệu tăng/giảm (strict)."""
    def _chk(x):
        v = pd.Series(x)
        if v.isna().any():
            return np.nan
        dif = v.diff().dropna()
        return float((dif > 0).all()) if increasing else float((dif < 0).all())
    return s.rolling(window=window, min_periods=window).apply(_chk, raw=False)

def _last_n_increasing(s: pd.Series, n: int) -> pd.Series:
    d = s.diff()
    return (d.rolling(n, min_periods=n)
             .apply(lambda x: float(np.all(np.array(x) > 0)), raw=True)
             .astype("float"))

def _stable_positive_series(s: pd.Series, window: int, cv_tol=0.25) -> pd.Series:
    """1.0 nếu trong 'window' kỳ: tất cả >0 và hệ số biến thiên (CV) <= cv_tol."""
    def _chk(x):
        v = pd.Series(x)
        if v.isna().any() or (v <= 0).any():
            return 0.0
        m = v.mean()
        if m == 0:
            return 0.0
        std = v.std(ddof=0)
        return float((std / m) <= cv_tol)
    return s.rolling(window=window, min_periods=window).apply(_chk, raw=False)

def _add_fund_features_bank_schema(
    df: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    year_col: str = "year",
    quarter_col: str = "quarter",
    stable_div_years: int = 3,
    enable_capex_proxy_for_F36: bool = True,
) -> pd.DataFrame:
    """
    Tính toàn bộ feature FUND_* theo schema ngân hàng (theo notebook bạn cung cấp).
    Hàm an toàn với cột thiếu — tự bỏ qua phần không đủ dữ liệu.
    """
    df = df.copy()

    # Suy luận độ trễ YoY cho từng ticker (ví dụ: 4 nếu theo quý; 1 nếu theo năm)
    lag_map = {}
    for key, g in df.groupby(ticker_col):
        lag_map[key] = _infer_yoy_lag(g, year_col, quarter_col)

    # Các cột chuẩn hoá tên (map sang cột trong df nếu có)
    cols = {
        "eps": "eps",
        "gross_margin": "grossMargin",
        "net_margin": "netMargin",
        "roe": "roe",
        "roa": "roa",
        "debt_to_equity": "debtToEquity",
        "current_ratio": "currentRatio",
        "quick_ratio": "quickRatio",
        "equity_per_share": "bookValuePerShare",
        "asset_turnover": "assetTurnover",
        "days_receivable": "daysOfReceivables",
        "days_inventory": "daysOfInventory",
        "days_payable": "daysOfPayables",
        "charter_capital": "capitalBalance",
        "cash_ratio": "cashRatio",
        # thêm một số dòng tiền/lợi nhuận nếu có
        "profit_after_tax": "profitAfterTax",
        "operating_cashflow": "netCashFromOperating",
        "investing_cashflow": "netCashFromInvesting",
        "financing_cashflow": "netCashFromFinancing",
        "dividend": "dividend",
        "capex": "capexOnFixedAsset",
    }

    # Chuẩn hoá numeric
    for c in cols.values():
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Thêm YoY cho các cột cần
    yoy_targets = [
        "eps","gross_margin","net_margin","roe","roa",
        "debt_to_equity","current_ratio","quick_ratio",
        "equity_per_share","asset_turnover",
        "days_receivable","days_inventory","days_payable",
        "charter_capital","cash_ratio"
    ]
    for key in yoy_targets:
        col = cols.get(key)
        if col in df.columns:
            yoy, yoy_abs = _add_yoy_cols(df, ticker_col, col, lag_map)
            df[f"{col}_yoy"] = yoy
            df[f"{col}_yoy_abs"] = yoy_abs

    # Khởi tạo vùng FUND_*
    for i in range(21, 61):
        df[f"FUND_{i}"] = np.nan

    # ===== Ví dụ một số Feature (theo notebook) =====
    # FUND-21: EPS YoY > 0
    if cols["eps"] in df.columns and f'{cols["eps"]}_yoy' in df.columns:
        df["FUND_21"] = (df[f'{cols["eps"]}_yoy'] > 0).astype("float")

    # FUND-22: Biên LN gộp tăng YoY
    if cols["gross_margin"] in df.columns and f'{cols["gross_margin"]}_yoy' in df.columns:
        df["FUND_22"] = (df[f'{cols["gross_margin"]}_yoy'] > 0).astype("float")

    # FUND-23: Biên LN ròng tăng YoY
    if cols["net_margin"] in df.columns and f'{cols["net_margin"]}_yoy' in df.columns:
        df["FUND_23"] = (df[f'{cols["net_margin"]}_yoy'] > 0).astype("float")

    # FUND-24/25: ROE/ROA tăng YoY
    if cols["roe"] in df.columns and f'{cols["roe"]}_yoy' in df.columns:
        df["FUND_24"] = (df[f'{cols["roe"]}_yoy'] > 0).astype("float")
    if cols["roa"] in df.columns and f'{cols["roa"]}_yoy' in df.columns:
        df["FUND_25"] = (df[f'{cols["roa"]}_yoy'] > 0).astype("float")

    # FUND-32: D/E giảm YoY (an toàn hơn)
    if cols["debt_to_equity"] in df.columns and f'{cols["debt_to_equity"]}_yoy' in df.columns:
        df["FUND_32"] = (df[f'{cols["debt_to_equity"]}_yoy'] < 0).astype("float")

    # FUND-34/35: Current/Quick ratio tăng YoY
    if cols["current_ratio"] in df.columns and f'{cols["current_ratio"]}_yoy' in df.columns:
        df["FUND_34"] = (df[f'{cols["current_ratio"]}_yoy'] > 0).astype("float")
    if cols["quick_ratio"] in df.columns and f'{cols["quick_ratio"]}_yoy' in df.columns:
        df["FUND_35"] = (df[f'{cols["quick_ratio"]}_yoy'] > 0).astype("float")

    # FUND-36: Capex mở rộng (capex YoY_abs > 0), fallback dùng investing cashflow nếu bật proxy
    if cols["capex"] in df.columns:
        df["FUND_36"] = (df[cols["capex"]].diff() > 0).astype("float")
    elif enable_capex_proxy_for_F36 and cols["investing_cashflow"] in df.columns:
        df["FUND_36"] = (df[cols["investing_cashflow"]].diff() < 0).astype("float")  # chi đầu tư tăng => CF đầu tư âm hơn

    # FUND-40: Vòng quay tài sản tăng YoY
    if cols["asset_turnover"] in df.columns and f'{cols["asset_turnover"]}_yoy' in df.columns:
        df["FUND_40"] = (df[f'{cols["asset_turnover"]}_yoy'] > 0).astype("float")

    # FUND-50: Tiền mặt/TS ngắn hạn cải thiện (cash ratio YoY > 0)
    if cols["cash_ratio"] in df.columns and f'{cols["cash_ratio"]}_yoy' in df.columns:
        df["FUND_50"] = (df[f'{cols["cash_ratio"]}_yoy'] > 0).astype("float")

    # FUND-52: GPA tăng YoY (proxy: gross_margin * asset_turnover * (1 - debt_to_equity_norm))
    # Đây chỉ là ví dụ minh hoạ; có thể thay đổi tuỳ schema thực tế.
    if all(cols[k] in df.columns for k in ["gross_margin", "asset_turnover"]) and cols["debt_to_equity"] in df.columns:
        gpa = df[cols["gross_margin"]] * df[cols["asset_turnover"]]
        d2e = df[cols["debt_to_equity"]]
        d2e_norm = (d2e - d2e.min()) / (d2e.max() - d2e.min() + 1e-9)
        gpa_prev = _group_shift(pd.DataFrame({"x": gpa, "t": df[ticker_col]}).rename(columns={"x": "gpa", "t": "ticker"}),
                                "ticker", "gpa", lag_map)
        gpa_yoy = pd.Series(np.nan, index=df.index, dtype="float64")
        m = gpa_prev.notna() & (gpa_prev != 0)
        gpa_yoy.loc[m] = gpa.loc[m] / gpa_prev.loc[m] - 1
        df["FUND_52"] = (gpa_yoy > 0).astype("float")

    # FUND-58: tăng vốn điều lệ
    if cols["charter_capital"] in df.columns:
        cap_abs = df.get(f"{cols['charter_capital']}_yoy_abs", None)
        if cap_abs is not None:
            df["FUND_58"] = (cap_abs > 0).astype("float")
        else:
            df["FUND_58"] = (df.groupby(ticker_col)[cols["charter_capital"]].diff() > 0).astype("float")

    # FUND-60: cổ tức ổn định ≥ N năm
    if cols["dividend"] in df.columns:
        fund60 = pd.Series(index=df.index, dtype="float64")
        for key, g in df.groupby(ticker_col):
            lag = lag_map[key]
            win = int(stable_div_years * lag)
            fund60.loc[g.index] = _stable_positive_series(g[cols["dividend"]], window=win, cv_tol=0.25).to_numpy()
        df["FUND_60"] = fund60

    # Ép float
    for c in [c for c in df.columns if c.startswith("FUND_")]:
        df[c] = df[c].astype("float")

    return df

def _finalize_fund_features(
    df: pd.DataFrame,
    *,
    drop_nan_threshold: float = 1.0,   # 1.0 = chỉ drop cột ALL-NaN; 0.9 = drop nếu NaN >= 90%
    cast_binary_to_int: bool = True
) -> pd.DataFrame:
    """
    - Drop các cột có tỷ lệ NaN >= drop_nan_threshold
    - Đổi tên FUND_* sang tên ngắn gọn (có thể tuỳ biến sau)
    - Tuỳ chọn ép kiểu 0/1 về Int8
    """
    df = df.copy()
    if drop_nan_threshold < 1.0:
        th = float(drop_nan_threshold)
        keep = []
        for c in df.columns:
            if df[c].isna().mean() < th:
                keep.append(c)
        df = df[keep]

    if cast_binary_to_int:
        for c in [c for c in df.columns if c.startswith("FUND_")]:
            if set(pd.unique(df[c].dropna())).issubset({0.0, 1.0}):
                df[c] = df[c].astype("Int8")

    return df

def add_all_fund_features(
    df: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    year_col: str = "year",
    quarter_col: str = "quarter",
    stable_div_years: int = 3,
    enable_capex_proxy_for_F36: bool = True,
    drop_nan_threshold: float = 1.0,
    cast_binary_to_int: bool = True
) -> pd.DataFrame:
    """
    Thêm TẤT CẢ fundamental features (FUND_*) theo schema ngân hàng vào DataFrame đầu vào.
    - Tự động suy luận độ trễ theo quý/năm cho mỗi mã.
    - Bỏ qua phần thiếu dữ liệu.
    - Tuỳ chọn lọc bớt cột toàn NaN và ép kiểu nhị phân.

    Trả về DataFrame mới (không sửa df gốc).
    """
    out = _add_fund_features_bank_schema(
        df,
        ticker_col=ticker_col,
        year_col=year_col,
        quarter_col=quarter_col,
        stable_div_years=stable_div_years,
        enable_capex_proxy_for_F36=enable_capex_proxy_for_F36,
    )
    out = _finalize_fund_features(
        out,
        drop_nan_threshold=drop_nan_threshold,
        cast_binary_to_int=cast_binary_to_int,
    )
    return out



# =====BEGIN: FUNDAMENTAL FEATURES (auto-imported from Feature.ipynb)=====
import pandas as pd
import numpy as np

# =========================
# Helpers (bền vững, không dùng DataFrameGroupBy.apply)
# =========================
def _infer_yoy_lag(g: pd.DataFrame, year_col: str, quarter_col: str) -> int:
    """Suy luận số kỳ/năm cho từng ticker (1 nếu dữ liệu theo năm)."""
    cnt = g.groupby(year_col)[quarter_col].nunique()
    if cnt.empty:
        return 1
    mode = cnt.mode().iat[0]
    return int(mode if mode and mode > 0 else 1)

def _group_shift(df: pd.DataFrame, group_col: str, value_col: str, lag_map: dict) -> pd.Series:
    """
    Trả về Series 'prev' = value_col dịch theo lag riêng của từng group.
    Tránh dùng groupby.apply để né DeprecationWarning.
    """
    prev = pd.Series(index=df.index, dtype='float64')
    # groups: {key -> index}
    groups = df.groupby(group_col).groups
    for key, idx in groups.items():
        l = lag_map[key]
        prev.loc[idx] = df.loc[idx, value_col].shift(l).to_numpy()
    return prev

def _add_yoy_cols(df: pd.DataFrame, group_col: str, value_col: str, lag_map: dict):
    """Tạo 2 Series yoy (%) và yoy_abs cho value_col, canh chỉ số với df.index."""
    if value_col not in df.columns:
        return pd.Series(index=df.index, dtype='float64'), pd.Series(index=df.index, dtype='float64')
    prev = _group_shift(df, group_col, value_col, lag_map)
    yoy = pd.Series(np.nan, index=df.index, dtype='float64')
    mask = prev != 0
    yoy.loc[mask] = df.loc[mask, value_col] / prev.loc[mask] - 1
    yoy_abs = (df[value_col] - prev).astype('float64')
    return yoy, yoy_abs

def _rolling_monotonic_flag(s: pd.Series, window: int, increasing=True) -> pd.Series:
    """True nếu chuỗi trong 'window' kỳ gần nhất đơn điệu tăng/giảm (strict)."""
    def _chk(x):
        v = pd.Series(x)
        if v.isna().any():
            return np.nan
        dif = v.diff().dropna()
        return float((dif > 0).all()) if increasing else float((dif < 0).all())
    return s.rolling(window=window, min_periods=window).apply(_chk, raw=False)

def _last_n_increasing(s: pd.Series, n: int) -> pd.Series:
    d = s.diff()
    return (d.rolling(n, min_periods=n)
             .apply(lambda x: float(np.all(np.array(x) > 0)), raw=True)
             .astype('float'))

def _stable_positive_series(s: pd.Series, window: int, cv_tol=0.25) -> pd.Series:
    """True nếu trong 'window' kỳ: tất cả >0 và CV<=cv_tol."""
    def _chk(x):
        v = pd.Series(x)
        if v.isna().any() or (v <= 0).any():
            return 0.0
        m = v.mean()
        if m == 0:
            return 0.0
        cv = v.std(ddof=0) / m
        return float(cv <= cv_tol)
    return s.rolling(window=window, min_periods=window).apply(_chk, raw=False)

# =========================
# Main (schema ngân hàng)
# =========================
def add_fund_features_bank_schema(
    df: pd.DataFrame,
    *,
    ticker_col: str = 'ticker',
    quarter_col: str = 'quarter',
    year_col: str = 'year',
    stable_div_years: int = 3,
    enable_capex_proxy_for_F36: bool = True
) -> pd.DataFrame:

    df = df.copy()
    df = df.sort_values([ticker_col, year_col, quarter_col]).reset_index(drop=True)

    # Suy luận lag theo ticker (KHÔNG dùng groupby.apply)
    lag_map = {}
    for t, g in df.groupby(ticker_col):
        lag_map[t] = _infer_yoy_lag(g[[year_col, quarter_col]], year_col, quarter_col)

    cols = {
        'eps': 'earningPerShare',
        'gross_margin': 'grossProfitMargin',
        'net_margin': 'postTaxMargin',
        'roe': 'roe',
        'roa': 'roa',
        'debt_to_equity': 'debtOnEquity',
        'current_ratio': 'currentPayment',
        'quick_ratio': 'quickPayment',
        'interest_coverage': 'ebitOnInterest',
        'equity_per_share': 'bookValuePerShare',
        'asset_turnover': 'revenueOnAsset',
        'days_receivable': 'daysReceivable',
        'days_inventory': 'daysInventory',
        'days_payable': 'daysPayable',
        'charter_capital': 'capitalBalance',
        'cash_ratio': 'cashOnEquity',
        'dividend': 'dividend',
        'capex': 'capexOnFixedAsset',
    }

    # Chuẩn hoá numeric
    for c in cols.values():
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors='coerce')

    # Thêm YoY cho các cột cần (KHÔNG dùng DataFrameGroupBy.apply)
    yoy_targets = [
        'eps','gross_margin','net_margin','roe','roa',
        'debt_to_equity','current_ratio','quick_ratio',
        'equity_per_share','asset_turnover',
        'days_receivable','days_inventory','days_payable',
        'charter_capital','cash_ratio'
    ]
    for key in yoy_targets:
        col = cols.get(key)
        if col in df.columns:
            yoy, yoy_abs = _add_yoy_cols(df, ticker_col, col, lag_map)
            df[f'{col}_yoy'] = yoy
            df[f'{col}_yoy_abs'] = yoy_abs

    # Khởi tạo
    for i in range(21, 61):
        df[f'FUND_{i}'] = np.nan

    # ===== Features tính được ngay =====
    if cols['eps'] in df.columns:
        df['FUND_25'] = (df[f"{cols['eps']}_yoy"] > 0).astype('float')
        df['FUND_26'] = df.groupby(ticker_col, group_keys=False)[cols['eps']].apply(
            lambda s: _rolling_monotonic_flag(s, window=4, increasing=True)
        )

    if cols['gross_margin'] in df.columns:
        df['FUND_27'] = df.groupby(ticker_col, group_keys=False)[cols['gross_margin']].apply(
            lambda s: _last_n_increasing(s, n=2)
        )

    if cols['net_margin'] in df.columns:
        df['FUND_28'] = df.groupby(ticker_col, group_keys=False)[cols['net_margin']].apply(
            lambda s: _last_n_increasing(s, n=2)
        )

    if cols['cash_ratio'] in df.columns:
        df['FUND_33'] = (df[f"{cols['cash_ratio']}_yoy"] > 0).astype('float')

    if enable_capex_proxy_for_F36 and cols['capex'] in df.columns:
        df['FUND_36'] = (df[cols['capex']] > 0).astype('float')

    if cols['debt_to_equity'] in df.columns:
        df['FUND_37'] = df.groupby(ticker_col, group_keys=False)[cols['debt_to_equity']].apply(
            lambda s: _rolling_monotonic_flag(s, window=4, increasing=False)
        )

    if cols['current_ratio'] in df.columns:
        df['FUND_38'] = ((df[cols['current_ratio']] > 1.5) &
                         (df[f"{cols['current_ratio']}_yoy"] > 0)).astype('float')
        df['FUND_44'] = ((df[cols['current_ratio']] > 1.0) &
                         (df[f"{cols['current_ratio']}_yoy"] > 0)).astype('float')

    if cols['quick_ratio'] in df.columns:
        df['FUND_39'] = ((df[cols['quick_ratio']] > 1.0) &
                         (df[f"{cols['quick_ratio']}_yoy"] > 0)).astype('float')

    if cols['interest_coverage'] in df.columns:
        df['FUND_40'] = (df[cols['interest_coverage']] > 3).astype('float')

    if cols['equity_per_share'] in df.columns:
        df['FUND_42'] = (df[f"{cols['equity_per_share']}_yoy"] > 0).astype('float')

    if cols['roe'] in df.columns:
        df['FUND_45'] = ((df[cols['roe']] > 0.15) &
                         (df[f"{cols['roe']}_yoy"] > 0)).astype('float')

    if cols['roa'] in df.columns:
        df['FUND_46'] = ((df[cols['roa']] > 0.08) &
                         (df[f"{cols['roa']}_yoy"] > 0)).astype('float')

    if cols['asset_turnover'] in df.columns:
        df['FUND_47'] = (df[f"{cols['asset_turnover']}_yoy"] > 0).astype('float')

    if cols['days_inventory'] in df.columns:
        df['FUND_48'] = (df[f"{cols['days_inventory']}_yoy_abs"] < 0).astype('float')

    if cols['days_receivable'] in df.columns:
        df['FUND_49'] = (df[f"{cols['days_receivable']}_yoy_abs"] < 0).astype('float')

    if cols['days_payable'] in df.columns:
        df['FUND_50'] = (df[f"{cols['days_payable']}_yoy_abs"] < 0).astype('float')

    # FUND-52: (gross_margin * asset_turnover) YoY > 0 (không dùng apply DataFrame)
    if cols['gross_margin'] in df.columns and cols['asset_turnover'] in df.columns:
        gpa = (df[cols['gross_margin']] * df[cols['asset_turnover']]).astype('float64')
        # Self-shift theo group
        gpa_prev = pd.Series(index=df.index, dtype='float64')
        groups = df.groupby(ticker_col).groups
        for key, idx in groups.items():
            l = lag_map[key]
            gpa_prev.loc[idx] = gpa.loc[idx].shift(l).to_numpy()
        gpa_yoy = pd.Series(np.nan, index=df.index, dtype='float64')
        m = gpa_prev != 0
        gpa_yoy.loc[m] = gpa.loc[m] / gpa_prev.loc[m] - 1
        df['FUND_52'] = (gpa_yoy > 0).astype('float')

    # FUND-58: vốn điều lệ tăng (capitalBalance YoY_abs > 0)
    if cols['charter_capital'] in df.columns:
        cap_abs = df.get(f"{cols['charter_capital']}_yoy_abs", None)
        if cap_abs is not None:
            df['FUND_58'] = (cap_abs > 0).astype('float')
        else:
            df['FUND_58'] = (df.groupby(ticker_col)[cols['charter_capital']].diff() > 0).astype('float')

    # FUND-60: cổ tức ổn định ≥ N năm (vòng lặp group, KHÔNG dùng apply)
    if cols['dividend'] in df.columns:
        fund60 = pd.Series(index=df.index, dtype='float64')
        for key, g in df.groupby(ticker_col):
            lag = lag_map[key]
            win = stable_div_years * lag
            fund60.loc[g.index] = _stable_positive_series(g[cols['dividend']], window=win, cv_tol=0.25).to_numpy()
        df['FUND_60'] = fund60

    # Ép float
    for c in [c for c in df.columns if c.startswith('FUND_')]:
        df[c] = df[c].astype('float')

    return df


import pandas as pd
import numpy as np

def finalize_fund_features(
    df: pd.DataFrame,
    *,
    drop_nan_threshold: float = 1.0,   # 1.0 = chỉ drop cột ALL-NaN; 0.9 = drop nếu NaN >= 90%
    cast_binary_to_int: bool = True
) -> pd.DataFrame:
    """
    - Drop các cột có tỷ lệ NaN >= drop_nan_threshold
    - Đổi tên FUND_* sang tên ngắn gọn, có nghĩa
    - Tuỳ chọn ép kiểu 0/1 về Int8
    """
    df2 = df.copy()

    # 1) Drop cột theo tỷ lệ NaN
    na_ratio = df2.isna().mean()
    cols_drop = na_ratio.index[na_ratio >= drop_nan_threshold].tolist()
    if cols_drop:
        df2 = df2.drop(columns=cols_drop)

    # 2) Đổi tên các FUND_*
    rename_map = {
        # EPS & margins
        "FUND_25": "eps_yoy_up",           # EPS tăng YoY
        "FUND_26": "eps_up_4p",            # EPS tăng liên tục 4 kỳ
        "FUND_27": "gm_up_2p",             # Gross margin tăng ≥2 kỳ
        "FUND_28": "nm_up_2p",             # Net margin tăng ≥2 kỳ

        # Liquidity / cash / capex
        "FUND_33": "cash_on_equity_yoy_up",# Tiền/VCSH tăng YoY (proxy)
        "FUND_36": "capex_pos",            # Capex > 0 (proxy mở rộng đầu tư)

        # Leverage & coverage
        "FUND_37": "de_ratio_down_4p",     # Debt/Equity giảm 4 kỳ
        "FUND_38": "curr_gt1_5_yoy_up",    # Current ratio >1.5 & YoY tăng
        "FUND_39": "quick_gt1_yoy_up",     # Quick ratio >1 & YoY tăng
        "FUND_40": "int_cov_gt3",          # Interest coverage >3

        # Equity & returns
        "FUND_42": "bvps_yoy_up",          # BVPS tăng YoY (proxy vốn CSH)
        "FUND_44": "wc_pos_yoy_up",        # Vốn lưu động dương & cải thiện (proxy)
        "FUND_45": "roe_gt15_yoy_up",      # ROE >15% & YoY tăng
        "FUND_46": "roa_gt8_yoy_up",       # ROA >8% & YoY tăng

        # Efficiency & working capital cycles
        "FUND_47": "asset_turnover_yoy_up",# Doanh thu/Tài sản tăng YoY
        "FUND_48": "days_inv_yoy_down",    # Days Inventory giảm YoY (proxy IT up)
        "FUND_49": "days_rec_yoy_down",    # Days Receivable giảm YoY (proxy RT up)
        "FUND_50": "days_pay_yoy_down",    # Days Payable giảm YoY (giả định cải thiện)

        # Profitability vs assets
        "FUND_52": "gpa_yoy_up",           # GP/TA tăng YoY ≈ GM × AT

        # Capital / dividend
        "FUND_58": "charter_cap_yoy_up",   # Vốn điều lệ tăng YoY (capitalBalance)
        "FUND_60": "div_stable_geNyrs",    # Cổ tức ổn định ≥ N năm (CV<=0.25 & >0)
    }
    # Chỉ rename các cột đang tồn tại
    rename_existing = {k: v for k, v in rename_map.items() if k in df2.columns}
    df2 = df2.rename(columns=rename_existing)

    # 3) (Tuỳ chọn) Ép các cột nhị phân về Int8 (0/1/NA)
    if cast_binary_to_int:
        bin_cols = list(rename_existing.values())
        for c in bin_cols:
            if c in df2.columns:
                # đôi khi có float 0.0/1.0/NaN ⇒ ép sang Int8 an toàn
                df2[c] = pd.to_numeric(df2[c], errors="coerce")
                # giữ NaN nếu có; dùng dtype "Int8" (nullable)
                try:
                    df2[c] = df2[c].round().astype("Int8")
                except Exception:
                    pass

    return df2

def add_all_fund_features(
    df: pd.DataFrame,
    *,
    ticker_col: str = "ticker",
    year_col: str = "year",
    quarter_col: str = "quarter",
    stable_div_years: int = 3,
    enable_capex_proxy_for_F36: bool = True,
    drop_nan_threshold: float = 1.0,
    cast_binary_to_int: bool = True
) -> pd.DataFrame:
    """
    Thêm TẤT CẢ fundamental features (FUND_*) theo schema ngân hàng vào DataFrame đầu vào.
    Gồm: add_fund_features_bank_schema(...) + finalize_fund_features(...)
    """
    out = add_fund_features_bank_schema(
        df,
        stable_div_years=stable_div_years,
        enable_capex_proxy_for_F36=enable_capex_proxy_for_F36,
    )
    out = finalize_fund_features(
        out,
        drop_nan_threshold=drop_nan_threshold,
        cast_binary_to_int=cast_binary_to_int,
    )
    return out




# ========================= Lazy FUND fetching/computation =========================
_BASE_FUND_COLS = {
    "earningPerShare","bookValuePerShare","roe","roa",
    "priceToEarning","priceToBook",
    "interestMargin","nonInterestOnToi",
    "badDebtPercentage","provisionOnBadDebt",
    "costOfFinancing",
    "equityOnTotalAsset","equityOnLoan",
    "costToIncome","equityOnLiability",
    "assetOnEquity",
    "preProvisionOnToi","postTaxOnToi",
    "loanOnEarnAsset","loanOnAsset","loanOnDeposit",
    "depositOnEarnAsset",
    "badDebtOnAsset","liquidityOnLiability","payableOnEquity",
    "cancelDebt",
    "creditGrowth",
}

# cache now stores: {"price": df, "fund_raw": df, "fund_full": df or None}
def _auto_get(symbol: str, *, timeframe: str = "h", force_refresh: bool = False):
    key = f"{symbol}|{timeframe}"
    cache_hit = (not force_refresh) and (key in _CACHE)
    if cache_hit and "price" in _CACHE[key] and "fund_raw" in _CACHE[key]:
        return _CACHE[key]["price"], _CACHE[key]["fund_raw"], _CACHE[key].get("fund_full")
    df_price = _fetch_price_df(symbol, timeframe=timeframe)
    # fetch raw fund without computing derived features
    try:
        from quantvn.vn.data import Company
    except Exception as e:
        raise ImportError("Cần quantvn: `pip install quantvn` và khởi tạo client(apikey=...)") from e
    df_raw = Company(symbol).ratio_summary()
    if "ticker" not in df_raw.columns:
        df_raw = df_raw.copy(); df_raw["ticker"] = symbol
    if "year" not in df_raw.columns or "quarter" not in df_raw.columns:
        raise KeyError("ratio_summary() cần có cột 'year' và 'quarter'")
    _CACHE[key] = {"price": df_price, "fund_raw": df_raw, "fund_full": None}
    return df_price, df_raw, None

def _get_fund_frame_for_feature(symbol: str, timeframe: str, feature_name: str, *, force_refresh: bool):
    """Return a DataFrame that contains the requested feature.
    - If it's a base column and exists in raw, return raw.
    - Otherwise, compute full FUND on demand (once), cache it, and return that.
    """
    key = f"{symbol}|{timeframe}"
    p, raw, full = _auto_get(symbol, timeframe=timeframe, force_refresh=force_refresh)
    # If base & present -> use raw
    if feature_name in raw.columns:
        return p, raw
    # Else compute (or reuse cached) full
    if full is None or force_refresh:
        full = add_all_fund_features(raw, ticker_col="ticker", year_col="year", quarter_col="quarter")
        _CACHE[key]["fund_full"] = full
    return p, full


def fund_feature(
    feature_name: str,
    symbol: str,
    *,
    timeframe: str = "h",
    report_release_lag_days: int = 0,
    force_refresh: bool = False
) -> pd.DataFrame:
    """
    Lấy OHLCV + 1 cột fundamental (feature_name) cho symbol.
    - Với feature cơ bản (vd: earningPerShare), chỉ dùng ratio_summary() raw.
    - Với feature dẫn xuất (YoY / FUND flags...), tính FUND on-demand & cache.
    Trả về: date, time, open, high, low, close, volume, <feature_name>
    """
    if not isinstance(feature_name, str):
        raise TypeError("feature_name phải là str")

    price_df, fund_df = _get_fund_frame_for_feature(symbol, timeframe, feature_name, force_refresh=force_refresh)

    merged = merge_fund_into_price(
        price_df=price_df,
        fund_df=fund_df,
        price_date_col="Date",
        price_time_col="time",
        ticker_col="ticker",
        quarter_col="quarter",
        year_col="year",
        assume_ticker=symbol,
        report_release_lag_days=report_release_lag_days,
        drop_all_nan_cols=True,
    )

    if feature_name not in merged.columns:
        raise KeyError(f"Không tìm thấy feature '{feature_name}' sau khi merge.")

    out = merged[["Date","time","Open","High","Low","Close","Volume", feature_name]].copy()

    out = out.sort_values(["Date","time"], kind="mergesort").reset_index(drop=True)
    return out[["Date","time","Open","High","Low","Close","Volume", feature_name]]
