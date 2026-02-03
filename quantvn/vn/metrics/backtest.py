# ===== Backtest_Stock & helpers (migrated from your “second block”) =====
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


class Backtest_Derivates:
    """
    A class for backtesting derivatives trading strategies.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataframe containing historical data with columns ['Date', 'time', 'Close', 'position'].
    pnl_type : str, optional
        Type of PNL calculation ('raw' or 'after_fees'), by default 'after_fees'.

    Raises
    ------
    ValueError
        If pnl_type is not 'raw' or 'after_fees'.
    """

    def __init__(self, df, pnl_type="after_fees"):
        """
        Initializes the BacktestDerivates class.

        Parameters
        ----------
        df : pd.DataFrame
            Data containing trade details.
        pnl_type : str, optional
            Type of PNL calculation ('raw' or 'after_fees'), by default "after_fees".
        """
        if pnl_type not in ["raw", "after_fees"]:
            raise ValueError("Invalid pnl_type. Choose 'raw' or 'after_fees'.")

        self.df = df.copy()
        self.pnl_type = pnl_type
        self.df["datetime"] = pd.to_datetime(
            self.df["Date"].astype(str) + " " + self.df["time"].astype(str),
            errors="coerce",
        )
        self.df = self.df.dropna(subset=["datetime"])
        self.df.set_index("datetime", inplace=True)
        self.df.sort_index(inplace=True)

        # Calculate raw PNL
        self.df["pnl_raw"] = self.df["Close"].diff().shift(-1) * self.df["position"]
        self.df["pnl_raw"].fillna(0, inplace=True)

        # Calculate PNL after fees
        transaction_fee = 2700 / 100000  # VND per contract
        overnight_fee = 2550 / 100000  # VND per contract per day if held overnight

        self.df["transaction_fee"] = self.df["position"].diff().abs() * transaction_fee

        # Identify overnight holdings
        self.df["date"] = self.df.index.date
        self.df["overnight"] = (self.df["position"] > 0) & (
            self.df["date"] != self.df["date"].shift()
        )
        self.df["overnight_fee"] = self.df["overnight"] * overnight_fee

        self.df["total_fee"] = self.df["transaction_fee"].fillna(0) + self.df[
            "overnight_fee"
        ].fillna(0)
        self.df["pnl_after_fees"] = self.df["pnl_raw"] - self.df["total_fee"]

    def PNL(self):
        """
        Calculate cumulative PNL based on selected pnl_type.

        Returns
        -------
        pandas.Series
            Cumulative PNL.
        """
        return self.df[f"pnl_{self.pnl_type}"].cumsum()

    def daily_PNL(self):
        """
        Calculate daily PNL based on selected pnl_type.

        Returns
        -------
        pandas.Series
            Daily cumulative PNL.
        """
        daily_pnl = (
            self.df.groupby(self.df.index.date)[f"pnl_{self.pnl_type}"].sum().cumsum()
        )
        return daily_pnl

    def estimate_minimum_capital(self):
        """
        Estimate the minimum capital required to run the strategy.

        Returns
        -------
        float
            Minimum capital required.
        """
        self.df["cumulative_pnl"] = (
            self.df[f"pnl_{self.pnl_type}"].cumsum().shift().fillna(0)
        )
        self.df["capital_required"] = (
            self.df["position"].abs() * self.df["Close"]
        ) - self.df["cumulative_pnl"]

        return max(self.df["capital_required"].max(), 0)

    def PNL_percentage(self):
        """
        Calculate PNL percentage relative to minimum required capital.

        Returns
        -------
        float
            PNL percentage.
        """
        min_capital = self.estimate_minimum_capital()
        if min_capital == 0:
            return np.nan  # Avoid division by zero
        return self.daily_PNL() / min_capital

    def avg_pos(self):
        """
        Calculate average daily pos enter

        Returns
        -------
        float
            Average pos enter per day
        """
        return abs(self.df["position"].diff().dropna()).sum() / len(self.daily_PNL())

    def plot_PNL(self, daily: bool = False, title: str = "Backtest Stock"):
        """
        Vẽ duy nhất 1 đường equity sau phí.
        - daily=False: tích lũy theo từng bar
        - daily=True : gộp theo ngày rồi mới tích lũy
        """
        if "pnl_after_fees" not in self.df.columns:
            raise ValueError("Chưa có cột 'pnl_after_fees' trong self.df")

        if daily:
            eq = self.df.groupby(self.df.index.date)["pnl_after_fees"].sum().cumsum()
            x = pd.to_datetime(eq.index)
            y = eq.values
            x_label = "Date"
        else:
            eq = self.df["pnl_after_fees"].cumsum()
            x = eq.index
            y = eq.values
            x_label = "Time"

        plt.figure(figsize=(10, 4))
        plt.plot(x, y, linewidth=1.4)
        plt.title(title)
        plt.xlabel(x_label)
        plt.ylabel("Cumulative PnL (after fees)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()


class Backtest_Stock:
    """
    Backtest cổ phiếu (long-only):
    - Phí giao dịch 0.1% trên giá trị khớp (mua + bán)
    - Ép giữ tối thiểu 'min_hold_days' phiên (T+2.5 ~ 3 phiên)
    Kỳ vọng input df có cột: ['Date','time','Close','position'].
    'position' = số lượng cổ phiếu mong muốn (âm sẽ bị cắt về 0).
    """

    def __init__(
        self, df: pd.DataFrame, pnl_type: str = "after_fees", min_hold_days: int = 3
    ):
        if pnl_type not in ["raw", "after_fees"]:
            raise ValueError("Invalid pnl_type. Choose 'raw' or 'after_fees'.")

        self.pnl_type = pnl_type
        self.min_hold_days = int(min_hold_days)

        # Chuẩn hóa thời gian & index
        self.df = df.copy()
        self.df["datetime"] = pd.to_datetime(
            self.df["Date"].astype(str) + " " + self.df["time"].astype(str),
            errors="coerce",
        )
        self.df = self.df.dropna(subset=["datetime"])
        self.df.set_index("datetime", inplace=True)
        self.df.sort_index(inplace=True)

        # Long-only ý định
        self.df["Close"] = pd.to_numeric(self.df["Close"], errors="coerce")
        self.df = self.df.dropna(subset=["Close"])
        self.df["position_intent"] = (
            pd.to_numeric(self.df["position"], errors="coerce")
            .fillna(0)
            .clip(lower=0)
            .astype(float)
        )

        # Xây effective position tôn trọng min_hold theo SỐ PHIÊN
        eff_pos, trade_qty = self._build_effective_position_with_min_hold(
            index=self.df.index,
            desired_positions=self.df["position_intent"].to_numpy(dtype=float),
            min_hold_days=self.min_hold_days,
        )
        # Trả về numpy → gán theo vị trí, tránh lệch index
        self.df["effective_position"] = eff_pos
        self.df["trade_qty"] = trade_qty

        # PnL: giữ vị thế từ bar t -> t+1
        self.df["pnl_raw"] = (
            self.df["Close"].diff().shift(-1).fillna(0) * self.df["effective_position"]
        )

        # Phí giao dịch: 0.1% notional mỗi lần khớp
        fee_rate = 0.001
        notional_traded = (
            np.abs(self.df["trade_qty"].to_numpy()) * self.df["Close"].to_numpy()
        )
        self.df["transaction_fee"] = notional_traded * fee_rate

        self.df["pnl_after_fees"] = self.df["pnl_raw"] - self.df["transaction_fee"]

    @staticmethod
    def _build_effective_position_with_min_hold(
        index: pd.DatetimeIndex,
        desired_positions: np.ndarray,
        min_hold_days: int = 3,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Tạo chuỗi vị thế thực sự (long-only) với ràng buộc giữ tối thiểu N phiên.
        Dùng FIFO lots: mỗi lot có (qty_remaining, day_id_entry).

        - index: DatetimeIndex (để nhóm ngày/phiên)
        - desired_positions: mảng số lượng mong muốn theo bar (>=0)
        - min_hold_days: số phiên tối thiểu cần giữ mới được bán
        """
        n = len(desired_positions)
        if len(index) != n:
            raise ValueError("index and desired_positions must have the same length")

        # Ánh xạ mỗi timestamp sang mã phiên tăng dần (0,1,2,...) theo NGÀY (calendar day)
        # Nếu cần đúng 'trading days' theo lịch nghỉ lễ, hãy thay bằng lịch giao dịch VN.
        dates = pd.Index(index.date)
        day_change = np.r_[True, dates[1:] != dates[:-1]]
        day_id = np.cumsum(day_change) - 1  # 0-based day id

        effective_pos = np.zeros(n, dtype=float)
        trade_qty = np.zeros(n, dtype=float)

        # FIFO lots: list of [qty_remaining, entry_day_id]
        lots: list[list[float | int]] = []
        prev_effective = 0.0

        for i in range(n):
            desired = float(max(0.0, desired_positions[i]))

            if i == 0:
                # Mua vào nếu cần ở bar đầu
                buy_qty = max(0.0, desired - prev_effective)
                if buy_qty > 0:
                    lots.append([buy_qty, int(day_id[i])])
                    trade_qty[i] = buy_qty
                    prev_effective += buy_qty
                # Luôn chốt effective_pos cho bar này
                effective_pos[i] = prev_effective
                continue

            if desired > prev_effective:
                # Cần mua thêm
                buy_qty = desired - prev_effective
                if buy_qty > 1e-12:
                    lots.append([buy_qty, int(day_id[i])])
                    trade_qty[i] = buy_qty
                    prev_effective += buy_qty

            elif desired < prev_effective:
                # Cần bán bớt, nhưng chỉ bán các lot đã đủ số phiên
                to_sell = prev_effective - desired
                if to_sell > 1e-12:
                    # Bán theo FIFO, chỉ những lot đủ điều kiện
                    sell_now_total = 0.0
                    for lot in lots:
                        if to_sell <= 1e-12:
                            break
                        qty_rem, d_entry = lot
                        if qty_rem <= 1e-12:
                            continue
                        # Đủ điều kiện nếu số PHIÊN đã qua >= min_hold_days
                        if (int(day_id[i]) - int(d_entry)) >= min_hold_days:
                            sell_amt = min(qty_rem, to_sell)
                            lot[0] = qty_rem - sell_amt
                            to_sell -= sell_amt
                            sell_now_total += sell_amt
                    # Dọn các lot trống
                    lots = [lot for lot in lots if lot[0] > 1e-12]
                    if sell_now_total > 1e-12:
                        trade_qty[i] = -sell_now_total
                        prev_effective -= sell_now_total

            # Luôn set effective_pos ở CUỐI vòng lặp
            effective_pos[i] = prev_effective

        return effective_pos, trade_qty

    # ======= Các API kết quả =======
    def PNL(self) -> pd.Series:
        return self.df[f"pnl_{self.pnl_type}"].cumsum()

    def daily_PNL(self) -> pd.Series:
        ser = self.df.groupby(self.df.index.date)[f"pnl_{self.pnl_type}"].sum()
        return ser.cumsum()

    def estimate_minimum_capital(self) -> float:
        # Ước lượng nhu cầu vốn tối thiểu thô: notional giữ - lũy kế PnL tại mỗi thời điểm
        cum_pnl = self.df[f"pnl_{self.pnl_type}"].cumsum().shift().fillna(0.0)
        capital_required = (
            self.df["effective_position"].abs() * self.df["Close"]
        ) - cum_pnl
        return float(max(capital_required.max(), 0.0))

    def PNL_percentage(self) -> pd.Series:
        min_capital = self.estimate_minimum_capital()
        if min_capital == 0:
            return pd.Series(dtype=float)
        return self.daily_PNL() / min_capital

    def avg_pos(self) -> float:
        # Trung bình thay đổi vị thế theo ngày (từ effective_position)
        d = self.df["effective_position"].diff().abs().dropna().sum()
        days = max(len(self.daily_PNL()), 1)
        return float(d / days)

    # ======= Plot giống backtest_derivative (giá + vị thế + equity + volume giao dịch) =======
    def plot_PNL(self, daily: bool = False, title: str = "Backtest Stock"):
        """
        Vẽ duy nhất 1 đường equity sau phí.
        - daily=False: tích lũy theo từng bar
        - daily=True : gộp theo ngày rồi mới tích lũy
        """
        if "pnl_after_fees" not in self.df.columns:
            raise ValueError("Chưa có cột 'pnl_after_fees' trong self.df")

        if daily:
            eq = self.df.groupby(self.df.index.date)["pnl_after_fees"].sum().cumsum()
            x = pd.to_datetime(eq.index)
            y = eq.values
            x_label = "Date"
        else:
            eq = self.df["pnl_after_fees"].cumsum()
            x = eq.index
            y = eq.values
            x_label = "Time"

        plt.figure(figsize=(10, 4))
        plt.plot(x, y, linewidth=1.4)
        plt.title(title)
        plt.xlabel(x_label)
        plt.ylabel("Cumulative PnL (after fees)")
        plt.grid(True, alpha=0.3)
        plt.tight_layout()
        plt.show()
