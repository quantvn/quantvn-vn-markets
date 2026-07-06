# ===== Backtest_Stock (US / Alpaca) — mirrors quantvn.vn.metrics.backtest =====
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


class Backtest_US_Stock:
    """
    Backtest cổ phiếu Mỹ (long-only) theo chính sách phí của Alpaca.

    Khác với bản VN (``quantvn.vn.metrics.backtest.Backtest_Stock``):
    - Alpaca **miễn phí hoa hồng** cho cổ phiếu/ETF Mỹ (commission = $0).
    - Chỉ thu **phí pháp lý khi BÁN** (regulatory fees on sells only):
        * SEC Section 31 fee = sell_notional * ``sec_fee_rate``
          (mặc định $27.80 / $1,000,000 = 0.0000278).
        * FINRA Trading Activity Fee (TAF) = sell_shares * ``taf_per_share``
          (mặc định $0.000166/cp), giới hạn ``taf_max_per_order`` ($8.30/lệnh).
        * Tổng phí được **làm tròn lên** tới xu gần nhất (Alpaca rounds up to
          the nearest penny) khi ``round_fees=True``.
    - Mua không mất phí (commission-free, SEC/TAF không áp dụng cho lệnh mua).
    - Không có phí qua đêm cho vị thế long (chỉ short mới có phí vay — ngoài
      phạm vi, giống bản VN long-only).
    - Mỹ thanh toán **T+1** và cho phép bán trong ngày / day-trade → mặc định
      ``min_hold_days=0`` (bản VN dùng 3 cho T+2.5). Có thể chỉnh nếu muốn mô
      phỏng ràng buộc giữ tối thiểu.
    - Không có phiên ATC 14:30–14:45 như HOSE; phiên thường Mỹ 09:30–16:00 ET
      nên phần fill ATC của bản VN được bỏ.

    Tham khảo: https://docs.alpaca.markets/docs/regulatory-fees và
    https://alpaca.markets/support/tag/pricing-and-funding

    Kỳ vọng input df có cột: ['Date','time','Close','position'].
    'position' = số lượng cổ phiếu mong muốn (âm sẽ bị cắt về 0, long-only).
    """

    def __init__(
        self,
        df: pd.DataFrame,
        pnl_type: str = "after_fees",
        min_hold_days: int = 0,
        commission_per_share: float = 0.0,
        sec_fee_rate: float = 0.0000278,
        taf_per_share: float = 0.000166,
        taf_max_per_order: float = 8.30,
        round_fees: bool = True,
    ):
        if pnl_type not in ["raw", "after_fees"]:
            raise ValueError("Invalid pnl_type. Choose 'raw' or 'after_fees'.")

        self.pnl_type = pnl_type
        self.min_hold_days = int(min_hold_days)
        self.commission_per_share = float(commission_per_share)
        self.sec_fee_rate = float(sec_fee_rate)
        self.taf_per_share = float(taf_per_share)
        self.taf_max_per_order = float(taf_max_per_order)
        self.round_fees = bool(round_fees)

        # Chuẩn hóa thời gian & index
        self.df = df.copy()
        self.df["datetime"] = pd.to_datetime(
            self.df["Date"].astype(str) + " " + self.df["time"].astype(str),
            errors="coerce",
        )
        self.df = self.df.dropna(subset=["datetime"])
        self.df.set_index("datetime", inplace=True)
        self.df.sort_index(inplace=True)

        # Long-only ý định (giống bản VN: cắt phần âm về 0)
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

        # ===== Phí theo Alpaca =====
        close = self.df["Close"].to_numpy(dtype=float)
        trade = self.df["trade_qty"].to_numpy(dtype=float)
        buy_shares = np.clip(trade, 0.0, None)        # > 0 ở các bar mua
        sell_shares = np.clip(-trade, 0.0, None)      # > 0 ở các bar bán

        # Hoa hồng: Alpaca miễn phí ($0); để tham số hóa phòng khi đổi chính sách.
        self.df["commission"] = (buy_shares + sell_shares) * self.commission_per_share

        # Phí pháp lý CHỈ tính khi BÁN
        sell_notional = sell_shares * close
        sec_fee = sell_notional * self.sec_fee_rate
        taf_fee = np.where(
            sell_shares > 0,
            np.minimum(sell_shares * self.taf_per_share, self.taf_max_per_order),
            0.0,
        )
        self.df["sec_fee"] = sec_fee
        self.df["taf_fee"] = taf_fee

        transaction_fee = self.df["commission"].to_numpy() + sec_fee + taf_fee
        if self.round_fees:
            # Alpaca làm tròn LÊN tới xu gần nhất (USD precision = 0.01)
            transaction_fee = np.ceil(transaction_fee * 100.0) / 100.0
        self.df["transaction_fee"] = transaction_fee

        self.df["pnl_after_fees"] = self.df["pnl_raw"] - self.df["transaction_fee"]

    @staticmethod
    def _build_effective_position_with_min_hold(
        index: pd.DatetimeIndex,
        desired_positions: np.ndarray,
        min_hold_days: int = 0,
    ) -> tuple[np.ndarray, np.ndarray]:
        """
        Tạo chuỗi vị thế thực sự (long-only) với ràng buộc giữ tối thiểu N phiên.
        Dùng FIFO lots: mỗi lot có (qty_remaining, day_id_entry).

        - index: DatetimeIndex (để nhóm ngày/phiên)
        - desired_positions: mảng số lượng mong muốn theo bar (>=0)
        - min_hold_days: số phiên tối thiểu cần giữ mới được bán. Mặc định 0 cho
          Mỹ (T+1, cho phép bán trong ngày). VN dùng 3 (T+2.5).

        Logic giống hệt bản VN để đảm bảo tương đương về hành vi.
        """
        n = len(desired_positions)
        if len(index) != n:
            raise ValueError("index and desired_positions must have the same length")

        # Ánh xạ mỗi timestamp sang mã phiên tăng dần (0,1,2,...) theo NGÀY
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
                buy_qty = max(0.0, desired - prev_effective)
                if buy_qty > 0:
                    lots.append([buy_qty, int(day_id[i])])
                    trade_qty[i] = buy_qty
                    prev_effective += buy_qty
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
                    sell_now_total = 0.0
                    for lot in lots:
                        if to_sell <= 1e-12:
                            break
                        qty_rem, d_entry = lot
                        if qty_rem <= 1e-12:
                            continue
                        if (int(day_id[i]) - int(d_entry)) >= min_hold_days:
                            sell_amt = min(qty_rem, to_sell)
                            lot[0] = qty_rem - sell_amt
                            to_sell -= sell_amt
                            sell_now_total += sell_amt
                    lots = [lot for lot in lots if lot[0] > 1e-12]
                    if sell_now_total > 1e-12:
                        trade_qty[i] = -sell_now_total
                        prev_effective -= sell_now_total

            effective_pos[i] = prev_effective

        return effective_pos, trade_qty

    # ======= Các API kết quả (giống hệt bản VN) =======
    def PNL(self) -> pd.Series:
        return self.df[f"pnl_{self.pnl_type}"].cumsum()

    def daily_PNL(self) -> pd.Series:
        ser = self.df.groupby(self.df.index.date)[f"pnl_{self.pnl_type}"].sum()
        return ser.cumsum()

    def estimate_minimum_capital(self) -> float:
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
        d = self.df["effective_position"].diff().abs().dropna().sum()
        days = max(len(self.daily_PNL()), 1)
        return float(d / days)

    def plot_PNL(self, daily: bool = False, title: str = "Backtest US Stock"):
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
