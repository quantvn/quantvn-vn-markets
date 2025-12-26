import logging
from abc import abstractmethod
from typing import TypedDict, List, Dict, Union, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


class HistoryRecord(TypedDict):
    time: pd.Timestamp
    current_tick: int
    signal: float
    action: str
    amount: float
    value: float
    price: float
    fee: float
    equity: float
    bm_equity: float
    step_ret: float
    cum_ret: float
    bm_step_ret: float
    bm_cum_ret: float


def round_to_lot(value: float, lot_size: int) -> int:
    remainder = value % lot_size
    if remainder < lot_size / 2:
        return int(value - remainder)
    else:
        return int(value + (lot_size - remainder))


class Algorithm:
    _price_scale = 1

    def __init__(self):
        self._name = None
        self._init_cash = 1_000_000_000
        self._slippage = 0.0
        self._resolution = "D"
        self._ticker = None
        self._from_time = None
        self._to_time = None
        self._df_ticker = pd.DataFrame()
        self._init_price: Optional[float] = None

        self._bm_open_size: Optional[int] = None
        self._bm_equity: Optional[float] = None

        self._current_time_idx: Optional[int] = None
        self._current_time: Optional[pd.Timestamp] = None
        self._current_position: Optional[float] = None
        self._current_open_size: Optional[int] = None
        self._current_equity: Optional[float] = None

        self._ht_times: List[pd.Timestamp] = []
        self._ht_prices: List[float] = []
        self._bt_results: List[HistoryRecord] = []
        self._bt_df: Union[pd.DataFrame, None] = None
        self._bt_columns = list(HistoryRecord.__annotations__.keys())
        self.performance: Dict[str, float] = {}
        self._signals: Optional[pd.Series] = None

    # -------------------- Data helpers --------------------
    @property
    def df_ticker(self) -> pd.DataFrame:
        return self._df_ticker

    @df_ticker.setter
    def df_ticker(self, df: pd.DataFrame):
        self._df_ticker = df

    def load_csv(self, csv_path: str, symbol: str = "TICKER"):
        df = pd.read_csv(csv_path, parse_dates=["Date"]).rename(columns={"Date": "time"})
        df = df.set_index("time").sort_index()
        required = {"Open", "High", "Low", "Close"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"CSV is missing columns: {sorted(missing)}")
        if "Volume" not in df.columns:
            df["Volume"] = 0
        df["Symbol"] = symbol
        self.df_ticker = df

    # -------------------- Run lifecycle --------------------
    def __reset__(self):
        if self.df_ticker.empty:
            raise ValueError("No data loaded. Set df_ticker or call load_csv().")
        self._init_price = float(self.df_ticker['Close'].values[0] * self._price_scale)

        self._current_time_idx = 0
        self._current_position = 0.0
        self._current_open_size = 0
        self._ht_times.clear()
        self._ht_prices.clear()
        self._bt_results.clear()
        self._signals = pd.Series(dtype=float)
        self._ht_times = self.df_ticker.index.tolist()
        self._ht_prices = (self.df_ticker['Close'].values * self._price_scale).tolist()

        self._current_time = self.df_ticker.index[0]
        self._bm_equity = self._init_cash
        self._current_equity = self._init_cash
        self._bt_df = pd.DataFrame(columns=self._bt_columns)
        self._signals = pd.Series(0.0, index=self.df_ticker.index, dtype=float)

    @abstractmethod
    def __step__(self, time_idx: int):
        self._current_time_idx = time_idx

    @abstractmethod
    def __setup__(self):
        raise NotImplementedError

    @abstractmethod
    def __algorithm__(self):
        raise NotImplementedError

    def hold(self, conditions, weight: float = 0.0):
        self._signals[conditions] = weight

    def buy(self, conditions, weight: float = 1.0):
        self._signals[conditions] = weight

    def sell(self, conditions, weight: float = 1.0):
        self._signals[conditions] = -weight

    @property
    def Open(self):
        return self.df_ticker['Open'].values

    @property
    def High(self):
        return self.df_ticker['High'].values

    @property
    def Low(self):
        return self.df_ticker['Low'].values

    @property
    def Close(self):
        return self.df_ticker['Close'].values

    @property
    def Volume(self):
        return self.df_ticker['Volume'].values

    def run(self):
        self.__setup__()
        self.__load_data__()
        self.__reset__()
        # attach features wrapper on the full DataFrame
        self._features = TimeseriesFeatures(self.df_ticker)
        self.__algorithm__()
        if self._signals is None:
            raise ValueError("Trading signals were not generated.")
        for time_idx in range(len(self._signals)):
            self.__step__(time_idx)
        self.__done__()
        return self

    def __done__(self):
        logging.info(f"Algorithm {self._name} run completed. Total records: {len(self._bt_results)}")
        self._bt_df = pd.DataFrame(self._bt_results, columns=self._bt_columns)
        equity = self._bt_df['equity'].values
        bm_equity = self._bt_df['bm_equity'].values
        step_ret = np.zeros_like(equity, dtype=np.float64)
        step_ret[1:] = (equity[1:] - equity[:-1]) / equity[:-1]
        cum_ret = np.cumprod(1 + step_ret) - 1
        bm_step_ret = np.zeros_like(bm_equity, dtype=np.float64)
        bm_step_ret[1:] = (bm_equity[1:] - bm_equity[:-1]) / bm_equity[:-1]
        bm_cum_ret = np.cumprod(1 + bm_step_ret) - 1
        self._bt_df['step_ret'] = step_ret
        self._bt_df['cum_ret'] = cum_ret
        self._bt_df['bm_step_ret'] = bm_step_ret
        self._bt_df['bm_cum_ret'] = bm_cum_ret
        self._bt_df.set_index('time', inplace=True)
        return self

    # -------------------- Indicators helpers --------------------
    @classmethod
    def current(cls, series):
        if isinstance(series, pd.Series):
            return series.values
        elif isinstance(series, np.ndarray):
            return series
        else:
            raise TypeError(f"Unsupported type {type(series)} for current()")

    @classmethod
    def previous(cls, series, periods: int = 1):
        if isinstance(series, pd.Series):
            return series.shift(periods).values
        elif isinstance(series, np.ndarray):
            arr = series
            if periods <= 0:
                return arr
            pad = np.full(periods, np.nan)
            return np.concatenate([pad, arr[:-periods]])
        else:
            raise TypeError(f"Unsupported type {type(series)} for previous()")

    # -------------------- Data loading --------------------
    def __load_data__(self):
        if not self.df_ticker.empty:
            return
        if self._ticker is None:
            raise ValueError("No data loaded. Either call load_csv() or set _ticker and install yfinance.")
        try:
            import yfinance as yf
        except Exception as e:
            raise RuntimeError("yfinance is required for automatic fetching. Install via pip install yfinance or load via CSV.") from e
        start = str(self._from_time) if self._from_time is not None else None
        end = str(self._to_time) if self._to_time is not None else None
        df = yf.download(self._ticker, start=start, end=end, interval="1d")
        if df.empty:
            raise ValueError(f"No data fetched for ticker {self._ticker}")
        df = df.rename(columns={"Adj Close": "AdjClose"})
        if "Volume" not in df.columns:
            df["Volume"] = 0
        self.df_ticker = df[["Open", "High", "Low", "Close", "Volume"]]

    def visualize(self):
        visualizer = StrategyVisualizer(self._bt_df)
        visualizer.name = self._name
        visualizer.visualize()


class StockAlgorithm(Algorithm):
    _stock_lot_size = 100
    _price_scale = 1000

    def __init__(self):
        super().__init__()
        self._init_fee = 0.001
        self._t0_size: float = 0.0
        self._t1_size: float = 0.0
        self._t2_size: float = 0.0
        self._sell_size: float = 0.0
        self._pending_sell_pos: float = 0.0

    @abstractmethod
    def __setup__(self):
        raise NotImplementedError("StockAlgorithm must implement _setup_ method")

    @abstractmethod
    def __algorithm__(self):
        raise NotImplementedError("StockAlgorithm must implement _algorithm_ method")

    def __reset__(self):
        super().__reset__()
        self._bm_open_size = round_to_lot(self._init_cash // self._init_price, self._stock_lot_size)
        bm_fee = self._init_price * self._bm_open_size * self._init_fee
        self._bm_equity -= bm_fee

    def __step__(self, time_idx: int):
        super().__step__(time_idx)
        current_action = "H"
        current_signal = 0.0
        current_trade_size = 0.0
        current_fee = 0.0
        current_price = self._ht_prices[self._current_time_idx]
        current_time = self._ht_times[self._current_time_idx]
        sig: float = float(self._signals.values[self._current_time_idx])
        current_max_shares = round_to_lot(self._init_cash // current_price, self._stock_lot_size)

        prev_price = self._ht_prices[self._current_time_idx - 1] if self._current_time_idx > 0 else current_price
        current_pnl = self._current_open_size * (current_price - prev_price)
        bm_pnl = self._bm_open_size * (current_price - prev_price)

        prev_time = self._ht_times[self._current_time_idx - 1] if self._current_time_idx > 0 else current_time
        day_diff = (current_time - prev_time).days
        if day_diff > 0:
            logging.debug(
                f"Update T0, T1, T2 for {current_time}, T0: {self._t0_size}, T1: {self._t1_size}, T2: {self._t2_size}, Sell Position: {self._sell_size}"
            )
            self._sell_size += self._t2_size
            self._t2_size = self._t1_size
            self._t1_size = self._t0_size
            self._t0_size = 0

        if sig > 0:
            updated_position = min(sig - self._current_position, 1 - self._current_position)
        elif sig < 0:
            if self._current_position > 0:
                updated_position = max(sig - self._current_position, -self._current_position)
            else:
                updated_position = 0.0
        else:
            updated_position = 0.0

        if updated_position == 0:
            pass
        elif updated_position < 0 or self._pending_sell_pos > 0:
            logging.debug(f"Entering sell logic at {current_time} with weight {sig}")
            if self._sell_size == 0:
                logging.warning(
                    f"Sell position is 0, but trying to sell {sig} at {current_time}. This will be ignored, please wait for the next timestamp to sell."
                )
                self._pending_sell_pos += abs(sig)
            else:
                can_sell_position = max(self._pending_sell_pos, abs(updated_position))
                current_trade_size = min(
                    self._sell_size,
                    round_to_lot(can_sell_position * self._current_open_size, self._stock_lot_size),
                )
                self._sell_size -= current_trade_size
                self._current_open_size -= current_trade_size
                current_signal = -can_sell_position
                self._current_position -= can_sell_position
                self._pending_sell_pos = max(self._pending_sell_pos - can_sell_position, 0)
                current_action = "S"
                current_fee = current_price * current_trade_size * self._init_fee
                current_pnl -= current_fee
        elif updated_position > 0:
            logging.debug(f"Entering buy logic at {current_time} with weight {sig}")
            self._current_position += updated_position
            current_trade_size = round_to_lot(updated_position * current_max_shares, self._stock_lot_size)
            self._t0_size += current_trade_size
            self._current_open_size += current_trade_size
            current_action = "B"
            current_signal = updated_position
            current_fee = current_price * current_trade_size * self._init_fee
            current_pnl -= current_fee

        self._current_equity += current_pnl
        self._bm_equity += bm_pnl
        self._bt_results.append(
            HistoryRecord(
                time=current_time,
                current_tick=self._current_time_idx,
                action=current_action,
                signal=current_signal,
                amount=current_trade_size,
                price=current_price,
                value=self._current_open_size * current_price,
                fee=current_fee,
                equity=self._current_equity,
                bm_equity=self._bm_equity,
                step_ret=0,
                cum_ret=0,
                bm_step_ret=0,
                bm_cum_ret=0,
            )
        )


class TimeseriesFeatures:
    def __init__(self, df: pd.DataFrame):
        self.df = df

    def bbands(self, timeperiod: int = 20, nbdevup: float = 2.0, nbdevdn: float = 2.0):
        close = self.df['Close']
        ma = close.rolling(timeperiod).mean()
        std = close.rolling(timeperiod).std(ddof=0)
        upper = ma + nbdevup * std
        lower = ma - nbdevdn * std
        return upper, ma, lower

    def rsi(self, timeperiod: int = 14):
        close = self.df['Close']
        delta = close.diff()
        gain = (delta.where(delta > 0, 0.0)).ewm(alpha=1/timeperiod, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0.0)).ewm(alpha=1/timeperiod, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - (100 / (1 + rs))
        return rsi

    def macd(self, fastperiod: int = 12, slowperiod: int = 26, signalperiod: int = 9):
        close = self.df['Close']
        ema_fast = close.ewm(span=fastperiod, adjust=False).mean()
        ema_slow = close.ewm(span=slowperiod, adjust=False).mean()
        macd = ema_fast - ema_slow
        signal = macd.ewm(span=signalperiod, adjust=False).mean()
        hist = macd - signal
        return macd, signal, hist


class StrategyPerformance:
    def __init__(self, returns: Union[pd.Series, np.ndarray]):
        import quantstats as qs
        if isinstance(returns, np.ndarray):
            returns = pd.Series(returns)
        if not isinstance(returns, pd.Series):
            raise TypeError("Returns must be a pandas Series or numpy array.")
        self.qs = qs
        self.returns = returns.replace([np.inf, -np.inf], np.nan).dropna()
        self.trading_days = 252

    @property
    def summary(self):
        qs = self.qs
        r = self.returns
        return {
            "avg_return": qs.stats.avg_return(r),
            "cumulative_return": qs.stats.comp(r),
            "cvar": qs.stats.cvar(r),
            "gain_to_pain_ratio": qs.stats.gain_to_pain_ratio(r),
            "kelly_criterion": qs.stats.kelly_criterion(r),
            "max_drawdown": qs.stats.max_drawdown(r),
            "omega": qs.stats.omega(r),
            "profit_factor": qs.stats.profit_factor(r),
            "recovery_factor": qs.stats.recovery_factor(r),
            "sharpe": qs.stats.sharpe(r),
            "sortino": qs.stats.sortino(r),
            "tail_ratio": qs.stats.tail_ratio(r),
            "ulcer_index": qs.stats.ulcer_index(r),
            "var": qs.stats.value_at_risk(r),
            "volatility": qs.stats.volatility(r),
            "win_loss_ratio": qs.stats.win_loss_ratio(r),
            "win_rate": qs.stats.win_rate(r),
        }


class StrategyVisualizer:
    def __init__(self, df: pd.DataFrame):
        self._bt_df = df
        self.name = None

    def performance_summary(self) -> Dict[str, float]:
        if not self._bt_df.empty:
            pf = StrategyPerformance(self._bt_df['step_ret'])
            return pf.summary
        else:
            logging.warning("No backtest data available for performance summary.")
            return {}

    def visualize(self):
        if self._bt_df is None or self._bt_df.empty:
            logging.warning("No backtest data available to visualize.")
            return

        df = self._bt_df.sort_index()
        performance = self.performance_summary()

        metric_names = list(sorted(performance.keys()))
        metric_values = [f"{performance[m]:.4f}" if isinstance(performance[m], float) else "-" for m in metric_names]

        import plotly.graph_objects as go
        from plotly.subplots import make_subplots

        fig = make_subplots(
            rows=2, cols=2,
            shared_xaxes=True,
            vertical_spacing=0.01,
            horizontal_spacing=0.01,
            column_widths=[0.8, 0.2],
            row_heights=[0.4, 0.6],
            subplot_titles=("Strategy vs Benchmark", "", "Price vs Signals", ""),
            specs=[[{"type": "xy"}, {"type": "table"}],
                   [{"type": "xy"}, None]]
        )

        # Row 1: Strategy vs Benchmark
        fig.add_trace(go.Scatter(
            x=df.index, y=df['cum_ret'], mode='lines', name='Strategy',
            line=dict(color='blue')
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=df.index, y=df['bm_cum_ret'], mode='lines', name='Benchmark',
            line=dict(color='gray', dash='dot')
        ), row=1, col=1)

        # Row 2: Price with Buy/Sell signals
        fig.add_trace(go.Scatter(
            x=df.index, y=df['price'], mode='lines', name='Price',
            line=dict(color='black')
        ), row=2, col=1)

        # Buy markers
        buy_df = df[df['action'] == 'B'].copy()
        buy_df['date_str'] = buy_df.index.strftime('%Y-%m-%d')
        buy_df['time_str'] = buy_df.index.strftime('%H:%M:%S')
        buy_df['balance_str'] = buy_df['equity'].apply(lambda x: f"{x:,.2f}")
        buy_df['amount_str'] = buy_df['amount'].apply(lambda x: f"{x:.2f}")
        buy_df['fee_str'] = buy_df['fee'].apply(lambda x: f"{x:.2f}")
        buy_df['price_str'] = buy_df['price'].apply(lambda x: f"{x:.2f}")
        fig.add_trace(go.Scatter(
            x=buy_df.index, y=buy_df['price'], mode='markers', name='Buy',
            marker=dict(symbol='triangle-up', color='green', size=10),
            hovertemplate="Buy [%{customdata[0]}]<br>"
                          "Time: %{customdata[1]}<br>"
                          "Price: %{customdata[2]}<br>"
                          "Amount: %{customdata[3]}<br>"
                          "Fee: %{customdata[4]}<br>"
                          "Balance: %{customdata[5]}"
                          "<extra></extra>",
            customdata=buy_df[['date_str', 'time_str', 'price_str', 'amount_str', 'fee_str', 'balance_str']].values
        ), row=2, col=1)

        # Sell markers
        sell_df = df[df['action'] == 'S'].copy()
        sell_df['date_str'] = sell_df.index.strftime('%Y-%m-%d')
        sell_df['time_str'] = sell_df.index.strftime('%H:%M:%S')
        sell_df['balance_str'] = sell_df['equity'].apply(lambda x: f"{x:,.2f}")
        sell_df['amount_str'] = sell_df['amount'].apply(lambda x: f"{x:.2f}")
        sell_df['fee_str'] = sell_df['fee'].apply(lambda x: f"{x:.2f}")
        sell_df['price_str'] = sell_df['price'].apply(lambda x: f"{x:.2f}")
        fig.add_trace(go.Scatter(
            x=sell_df.index, y=sell_df['price'], mode='markers', name='Sell',
            marker=dict(symbol='triangle-down', color='red', size=10),
            hovertemplate="Sell [%{customdata[0]}]<br>"
                          "Time: %{customdata[1]}<br>"
                          "Price: %{customdata[2]}<br>"
                          "Amount: %{customdata[3]}<br>"
                          "Fee: %{customdata[4]}<br>"
                          "Balance: %{customdata[5]}"
                          "<extra></extra>",
            customdata=buy_df[['date_str', 'time_str', 'price_str', 'amount_str', 'fee_str', 'balance_str']].values
        ), row=2, col=1)

        # Latest annotation
        last_row = df.iloc[-1]
        fig.add_trace(go.Scatter(
            x=[last_row.index], y=[last_row['cum_ret']],
            mode='text', text=[f" - {last_row['cum_ret']:.2f}"],
            textposition='middle right',
            textfont=dict(color='blue', size=12), showlegend=False
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=[last_row.index], y=[last_row['bm_cum_ret']],
            mode='text', text=[f" - {last_row['bm_cum_ret']:.2f}"],
            textposition='middle right',
            textfont=dict(color='gray', size=12), showlegend=False
        ), row=1, col=1)

        fig.add_trace(go.Scatter(
            x=[last_row.index], y=[last_row['price']],
            mode='text', text=[f" - {last_row['price']:.2f}"],
            textposition='middle right',
            textfont=dict(color='black', size=12), showlegend=False
        ), row=2, col=1)

        # Table
        fig.add_trace(go.Table(
            header=dict(
                values=["<b>Metric</b>", "<b>Value</b>"],
                fill_color="lightgray", align="left",
                font=dict(size=12)
            ),
            cells=dict(
                values=[metric_names, metric_values],
                fill_color="white", align="left",
                font=dict(size=12)
            )
        ), row=1, col=2)

        fig.update_layout(
            title=f"Trading Strategy Performance: {self.name}",
            margin=dict(l=10, r=10, t=40, b=10),
            legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1),
            xaxis2_title="Time",
            yaxis1_title="Cumulative Return",
            yaxis2_title="Price",
            template='plotly_white',
            hovermode='closest'
        )

        import IPython
        if IPython.get_ipython():
            fig.show()
        else:
            from IPython.utils import io
            with io.capture_output() as captured:
                fig.show()