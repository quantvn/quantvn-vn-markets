import numpy as np
import pandas as pd


class TradingBacktest:
    """
    A class for backtesting derivatives trading strategies.

    Parameters
    ----------
    df : pandas.DataFrame
        Dataframe containing historical data with columns ['date', 'time', 'close', 'position'].
    pnl_type : str, optional
        Type of PNL calculation ('raw' or 'after_fees'), by default 'raw'.

    Raises    ------
    ValueError
        If pnl_type is not 'raw' or 'after_fees'.
    NotImplementedError
        If pnl_type is 'after_fees'
    """

    def __init__(self, df, pnl_type="raw"):
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

        if pnl_type == "after_fees":
            raise NotImplementedError

        self.df = df.copy()
        self.pnl_type = pnl_type

        # Check if DataFrame already has DateTimeIndex
        if not isinstance(df.index, pd.DatetimeIndex):
            self.df.index = pd.to_datetime(self.df["date"] + " " + self.df["time"])

        self.df = self.df.sort_index()

        # Calculate PNL
        self.df["pnl_raw"] = self.df["close"].diff().shift(-1) * self.df["position"]
        self.df["pnl_raw"] = self.df["pnl_raw"].fillna(0)

        self.daily_pnl = self.compute_daily_pnl()

    def compute_cumulative_pnl(self):
        """
        Calculate cumulative PNL based on selected pnl_type.

        Returns
        -------
        pandas.Series
            Cumulative PNL.
        """
        return self.df[f"pnl_{self.pnl_type}"].cumsum()

    def compute_daily_pnl(self):
        """
        Calculate daily PNL based on selected pnl_type.

        Returns
        -------
        pandas.Series
            Daily PNL.
        """
        return self.df.groupby(self.df["date"])[f"pnl_{self.pnl_type}"].sum()

    def estimate_minimum_capital(self):
        """
        Estimate the minimum capital required to run the strategy.

        Returns
        -------
        float
            Minimum capital required.
        """
        self.df["cumulative_pnl"] = self.compute_cumulative_pnl()
        self.df["capital_required"] = (self.df["position"].abs() * self.df["close"]) - self.df["cumulative_pnl"]

        return max(self.df["capital_required"].max(), 0)

    def compute_pnl_percentage(self):
        """
        Calculate PNL percentage relative to minimum required capital.

        Returns
        -------
        float
            PNL percentage.
        """
        min_capital = self.estimate_minimum_capital()
        return self.daily_pnl / min_capital if min_capital != 0 else np.nan  # avoid division by 0

    def avg_loss(self):
        """
        Compute the average loss from daily PNL.

        Returns
        -------
        float
            Average loss.
        """
        losses = self.daily_pnl[self.daily_pnl < 0]
        return losses.mean()

    def avg_return(self):
        """
        Compute the average return from daily PNL.

        Returns
        -------
        float
            Average return.
        """
        return self.daily_pnl.mean()

    def avg_win(self):
        """
        Compute the average win from daily PNL.

        Returns
        -------
        float
            Average win.
        """
        wins = self.daily_pnl[self.daily_pnl > 0]
        return wins.mean()

    def avg_loss_pct(self, initial_capital=1):
        """
        Compute the average loss (percentage) from daily PNL.

        Returns
        -------
        float
            Average loss.
        """
        losses = self.daily_pnl[self.daily_pnl < 0]
        return losses.mean() / initial_capital

    def avg_return_pct(self, initial_capital=1):
        """
        Compute the average return (percentage) from daily PNL.

        Returns
        -------
        float
            Average return.
        """
        return self.daily_pnl.mean() / initial_capital

    def avg_win_pct(self, initial_capital=1):
        """
        Compute the average win (percentage) from daily PNL.

        Returns
        -------
        float
            Average win.
        """
        wins = self.daily_pnl[self.daily_pnl > 0]
        return wins.mean() / initial_capital

    def max_drawdown(self):
        """
        Compute the maximum drawdown.

        Returns
        -------
        float
            Maximum drawdown as a percentage of minimum capital.
        """
        cumulative_daily_pnl = self.daily_pnl.cumsum()
        peak = cumulative_daily_pnl.cummax()
        drawdown = cumulative_daily_pnl - peak
        return drawdown.min() / self.estimate_minimum_capital()

    def win_rate(self):
        """
        Compute the win rate.

        Returns
        -------
        float
            Win rate.
        """
        wins = (self.daily_pnl > 0).sum()
        total = len(self.daily_pnl)
        return wins / total if total > 0 else 0

    def volatility(self):
        """
        Compute the standard deviation of daily PNL.

        Returns
        -------
        float
            Volatility.
        """
        return self.daily_pnl.std()

    def sharpe(self):
        """
        Compute the Sharpe ratio.

        Returns
        -------
        float
            Sharpe ratio.
        """
        return self.avg_return() / self.volatility() * np.sqrt(252)

    def sortino(self):
        """
        Compute the Sortino ratio.

        Returns
        -------
        float
            Sortino ratio.
        """
        downside_std = self.daily_pnl[self.daily_pnl < 0].std()
        return self.avg_return() / downside_std * np.sqrt(252) if downside_std > 0 else np.nan

    def calmar(self):
        """
        Compute the Calmar ratio.

        Returns
        -------
        float
            Calmar ratio.
        """
        return self.avg_return() / abs(self.max_drawdown()) * np.sqrt(252) if self.max_drawdown() != 0 else np.nan

    def profit_factor(self):
        """
        Compute the profit factor.

        Returns
        -------
        float
            Profit factor.
        """
        total_gain = self.daily_pnl[self.daily_pnl > 0].sum()
        total_loss = abs(self.daily_pnl[self.daily_pnl < 0].sum())
        return total_gain / total_loss if total_loss != 0 else np.nan  # avoid division by 0

    def risk_of_ruin(self, initial_capital=1):
        """
        Compute risk of ruin.

        Returns
        -------
        float
            Risk of ruin.
        """
        win_rate = self.win_rate()
        loss_rate = 1 - win_rate
        avg_loss_pct = self.avg_loss_pct(initial_capital)
        return (loss_rate / win_rate) ** (1 / avg_loss_pct) if avg_loss_pct != 0 else np.nan

    def value_at_risk(self, confidence_level=0.05):
        """
        Compute Value at Risk (VaR).

        Parameters
        ----------
        confidence_level : float, optional
            Confidence level for VaR, by default 0.05.

        Returns
        -------
        float
            Value at Risk (VaR).
        """
        return self.daily_pnl.quantile(confidence_level)

    def apply_tp_sl(self, df, tp_percentage, sl_percentage):
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("The DataFrame index must be a DatetimeIndex")

        prices = df["close"]
        positions = df["position"]
        new_positions = positions.copy()

        invalid_positions = set(positions.unique()) - {-1, 0, 1}
        if invalid_positions:
            raise ValueError(f"Positions must be in [-1, 0, 1]. Invalid: {invalid_positions}")

        # Tracking for each holding window
        entry_price = None
        entry_position = 0
        profit_flag = False

        for i in range(0, len(prices)):
            position = positions.iloc[i]

            # Neutral resets position
            if position == 0:
                entry_position = 0
                profit_flag = False
                continue

            # New position
            if position != entry_position:
                entry_price = prices.iloc[i]
                entry_position = position
                profit_flag = False
            # Hold position
            else:
                current_price = prices.iloc[i]

                # PnL % of Long (1) and Short (-1)
                if position == 1:
                    pnl_percentage = (current_price - entry_price) / entry_price * 100
                else:
                    pnl_percentage = (entry_price - current_price) / entry_price * 100

                # Reach profit threshold
                if pnl_percentage >= tp_percentage:
                    if not profit_flag:
                        profit_flag = True  # hold for 1 more timestep
                    else:
                        new_positions.iloc[i] = 0
                        entry_position = 0
                        profit_flag = False

                # Reach loss threshold
                if pnl_percentage <= -sl_percentage:
                    new_positions.iloc[i] = 0
                    entry_position = 0

        return new_positions

    def apply_tp_sl_trailing(self, df, tp_percentage, sl_percentage):
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("The DataFrame index must be a DatetimeIndex")

        prices = df["close"]
        positions = df["position"]
        new_positions = positions.copy()

        invalid_positions = set(positions.unique()) - {-1, 0, 1}
        if invalid_positions:
            raise ValueError(f"Positions must be in [-1, 0, 1]. Invalid: {invalid_positions}")

        # Tracking for trailing stop loss
        max_price = None
        min_price = None
        trailing_sl = None

        # Tracking for each holding window
        entry_price = None
        entry_position = 0
        profit_flag = False

        for i in range(0, len(prices)):
            position = positions.iloc[i]

            # Neutral resets position
            if position == 0:
                entry_position = 0
                continue

            # New position
            if position != entry_position:
                entry_price = prices.iloc[i]
                entry_position = position
                profit_flag = False

                max_price = entry_price
                min_price = entry_price

                if position == 1:
                    trailing_sl = entry_price * (1 - sl_percentage / 100)
                else:
                    trailing_sl = entry_price * (1 + sl_percentage / 100)
            # Hold position
            else:
                current_price = prices.iloc[i]

                # PnL % of Long (1) and Short (-1)
                if position == 1:
                    pnl_percentage = (current_price - entry_price) / entry_price * 100
                else:
                    pnl_percentage = (entry_price - current_price) / entry_price * 100

                # Take profit threshold
                if pnl_percentage >= tp_percentage:
                    if not profit_flag:
                        profit_flag = True  # hold for 1 more timestep
                    else:
                        new_positions.iloc[i] = 0
                        entry_position = 0
                        profit_flag = False

                # Reach / update trailing stop loss for Long (1) and Short (-1)
                if position == 1:
                    if current_price <= trailing_sl:
                        new_positions.iloc[i] = 0
                        entry_position = 0
                    elif current_price > max_price:
                        max_price = current_price
                        trailing_sl = max_price * (1 - sl_percentage / 100)
                else:
                    if current_price >= trailing_sl:
                        new_positions.iloc[i] = 0
                        entry_position = 0
                    elif current_price < min_price:
                        min_price = current_price
                        trailing_sl = min_price * (1 + sl_percentage / 100)

        return new_positions
