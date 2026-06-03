import numpy as np
import pandas as pd

EMA_FAST = 20
EMA_SLOW = 50
RSI_WINDOW = 14
BREAKOUT_WINDOW = 20


def _rsi(close: pd.Series, window: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    # Dùng EMA để RSI phản ứng mượt hơn với dữ liệu intraday, tránh tín hiệu quá giật.
    avg_gain = gain.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    avg_loss = loss.ewm(alpha=1 / window, adjust=False, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def gen_position(df: pd.DataFrame) -> pd.DataFrame:
    # Bắt lỗi thiếu giá đóng cửa sớm để tránh sinh tín hiệu sai mà khó phát hiện.
    missing = {"Close"} - set(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    out = df.copy()
    if {"Date", "time"}.issubset(out.columns):
        # Sắp xếp theo thời gian giúp rolling/EMA phản ánh đúng thứ tự thị trường.
        out["_datetime"] = pd.to_datetime(
            out["Date"].astype(str) + " " + out["time"].astype(str),
            errors="coerce",
        )
        out = (
            out.sort_values("_datetime")
            .drop(columns="_datetime")
            .reset_index(drop=True)
        )
    else:
        out = out.reset_index(drop=True)

    close = pd.to_numeric(out["Close"], errors="coerce")

    # EMA ngắn/dài giúp lọc hướng chính trước khi xét điểm vào lệnh.
    out["ema_fast"] = close.ewm(
        span=EMA_FAST,
        adjust=False,
        min_periods=EMA_FAST,
    ).mean()
    out["ema_slow"] = close.ewm(
        span=EMA_SLOW,
        adjust=False,
        min_periods=EMA_SLOW,
    ).mean()
    out["rsi_14"] = _rsi(close, window=RSI_WINDOW)

    # Shift 1 bar để vùng breakout chỉ dùng dữ liệu đã biết trước thời điểm hiện tại.
    rolling_close = close.rolling(BREAKOUT_WINDOW, min_periods=BREAKOUT_WINDOW)
    out["resistance_20"] = rolling_close.max().shift(1)
    out["support_20"] = rolling_close.min().shift(1)

    trend_up = out["ema_fast"] > out["ema_slow"]
    trend_down = out["ema_fast"] < out["ema_slow"]
    rsi_recover = (out["rsi_14"] > 50) & (out["rsi_14"].shift(1) <= 50)
    breakout = close > out["resistance_20"]
    momentum_fail = (out["rsi_14"] < 45) & (out["rsi_14"].shift(1) >= 45)
    breakdown = close < out["support_20"]

    # Chỉ mua khi xu hướng thuận chiều; bán khi trend yếu đi hoặc momentum thất bại.
    buy_signal = trend_up & (rsi_recover | breakout)
    sell_signal = trend_down | momentum_fail | breakdown

    out["signal"] = 0
    out.loc[buy_signal, "signal"] = 1
    out.loc[sell_signal, "signal"] = -1

    # Giữ position qua các bar trung tính để backtest phản ánh trạng thái đang nắm giữ.
    out["position"] = (
        out["signal"]
        .replace({0: np.nan, -1: 0})
        .ffill()
        .fillna(0)
        .astype(int)
    )
    return out
