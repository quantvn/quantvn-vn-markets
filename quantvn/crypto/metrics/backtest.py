import numpy as np
import pandas as pd


class Backtest_Crypto:
    def __init__(
        self,
        df,
        pnl_type="after_fees",
        transaction_fee_pct=0.001,
        overnight_fee_per_contract=0.0,
    ):
        """
        Initialize backtest for crypto derivatives.

        Args:
            df: DataFrame with OHLCV data and position column
            pnl_type: "raw" (before fees) or "after_fees" (after transaction fees)
            transaction_fee_pct: Transaction fee as % (default 0.1% = 0.001)
            overnight_fee_per_contract: Overnight holding fee per contract (default 0.0)
        """
        if pnl_type not in ["raw", "after_fees"]:
            raise ValueError("Invalid pnl_type. Choose 'raw' or 'after_fees'.")

        self.df = df.copy()
        self.pnl_type = pnl_type
        self.transaction_fee_pct = transaction_fee_pct
        self.overnight_fee_per_contract = overnight_fee_per_contract

        self.df["datetime"] = pd.to_datetime(
            self.df["Date"].astype(str) + " " + self.df["time"].astype(str),
            errors="coerce",
        )
        self.df.set_index("datetime", inplace=True)
        self.df.sort_index(inplace=True)

        # Calculate raw PNL: price change * position
        self.df["pnl_raw"] = self.df["Close"].diff().shift(-1) * self.df["position"]
        self.df["pnl_raw"].fillna(0, inplace=True)

        # Calculate transaction fees: charged when position changes
        self.df["position_diff"] = self.df["position"].diff().fillna(0).abs()
        self.df["transaction_fee"] = (
            self.df["position_diff"] * self.df["Close"] * self.transaction_fee_pct
        )
        self.df["transaction_fee_cumsum"] = self.df["transaction_fee"].cumsum()

        # Calculate overnight holding fees
        self.df["date"] = self.df.index.date
        self.df["overnight"] = (self.df["position"] != 0) & (
            self.df["date"] != self.df["date"].shift()
        )
        self.df["overnight_fee"] = (
            self.df["overnight"]
            * self.df["position"].abs()
            * self.overnight_fee_per_contract
        )
        self.df["overnight_fee_cumsum"] = self.df["overnight_fee"].cumsum()

        # Total fees and PnL after fees
        self.df["total_fee"] = self.df["transaction_fee"] + self.df["overnight_fee"]
        self.df["total_fee_cumsum"] = (
            self.df["transaction_fee_cumsum"] + self.df["overnight_fee_cumsum"]
        )
        self.df["pnl_after_fees"] = self.df["pnl_raw"] - self.df["total_fee"]

    def PNL(self):
        """Calculate cumulative PNL based on selected pnl_type."""
        return self.df[f"pnl_{self.pnl_type}"].cumsum()

    def daily_PNL(self):
        """Calculate daily PNL based on selected pnl_type."""
        daily_pnl = (
            self.df.groupby(self.df.index.date)[f"pnl_{self.pnl_type}"].sum().cumsum()
        )
        return daily_pnl

    def daily_PNL_custom(self):
        """Calculate daily PNL based on selected pnl_type."""
        daily_pnl = (
            self.df.groupby(self.df.index.date)[f"pnl_{self.pnl_type}"].sum().cumsum()
        )

        # Chuyển thành danh sách dictionary [{date, pnl}]
        result = {str(date): round(pnl, 2) for date, pnl in daily_pnl.items()}

        return result

    def estimate_minimum_capital(self):
        """Estimate minimum capital required based on position size and cumulative PnL/fees."""
        self.df["cumulative_pnl"] = (
            self.df[f"pnl_{self.pnl_type}"].cumsum().shift().fillna(0)
        )
        # Capital needed = (position * price) - cumulative profit + cumulative loss
        self.df["capital_required"] = (
            self.df["position"].abs() * self.df["Close"]
        ) - self.df["cumulative_pnl"]

        return max(self.df["capital_required"].max(), 1)

    def PNL_percentage(self):
        """Calculate PNL percentage by dividing daily_PNL by estimate_minimum_capital."""
        min_capital = self.estimate_minimum_capital()
        if min_capital == 0:
            return np.nan  # Avoid division by zero
        return round(self.daily_PNL() / min_capital, 2)
