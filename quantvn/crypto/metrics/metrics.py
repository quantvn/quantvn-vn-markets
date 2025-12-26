import numpy as np


class Metrics:
    def __init__(self, backtest):
        self.backtest = backtest
        # Use daily differences of cumulative PnL
        self.daily_pnl = backtest.daily_PNL().diff().dropna()
        # Also track cumulative for ratio calculations
        self.cumulative_pnl = backtest.daily_PNL()

    def avg_loss(self):
        """Average loss on losing days."""
        losses = self.daily_pnl[self.daily_pnl < 0]
        return losses.mean() if len(losses) > 0 else 0

    def avg_return(self):
        """Average daily return."""
        return self.daily_pnl.mean()

    def avg_win(self):
        """Average win on winning days."""
        wins = self.daily_pnl[self.daily_pnl > 0]
        return wins.mean() if len(wins) > 0 else 0

    def max_drawdown(self):
        """Maximum drawdown normalized by minimum capital."""
        cumulative = self.daily_pnl.cumsum()
        peak = cumulative.cummax()
        drawdown = cumulative - peak
        min_capital = max(self.backtest.estimate_minimum_capital(), 1)
        return drawdown.min() / min_capital if min_capital > 0 else 0

    def win_rate(self):
        """Percentage of winning days."""
        wins = (self.daily_pnl > 0).sum()
        total = len(self.daily_pnl)
        return wins / total if total > 0 else 0

    def volatility(self):
        """Daily volatility (standard deviation of daily returns)."""
        return self.daily_pnl.std()

    def sharpe(self, risk_free_rate=0.0):
        """Annualized Sharpe ratio."""
        vol = self.volatility()
        if vol == 0 or np.isnan(vol):
            return np.nan
        return (self.avg_return() - risk_free_rate) / vol * np.sqrt(365)

    def sortino(self):
        """Sortino ratio (only downside volatility counts)."""
        downside_pnl = self.daily_pnl[self.daily_pnl < 0]
        downside_std = downside_pnl.std()
        if downside_std == 0 or np.isnan(downside_std):
            return np.nan
        return np.sqrt(252) * self.avg_return() / downside_std

    def calmar(self):
        """Calmar ratio (return / max drawdown)."""
        dd = abs(self.max_drawdown())
        if dd == 0 or np.isnan(dd):
            return np.nan
        return np.sqrt(252) * self.avg_return() / dd

    def profit_factor(self):
        """Profit factor: total wins / total losses."""
        total_gain = self.daily_pnl[self.daily_pnl > 0].sum()
        total_loss = abs(self.daily_pnl[self.daily_pnl < 0].sum())
        if total_loss == 0:
            return np.inf if total_gain > 0 else np.nan
        return total_gain / total_loss

    def risk_of_ruin(self):
        """Risk of ruin calculation."""
        win_rate = self.win_rate()
        loss_rate = 1 - win_rate
        avg_loss = abs(self.avg_loss())
        if avg_loss == 0 or win_rate == 0 or loss_rate == 0:
            return np.nan
        return (loss_rate / win_rate) ** (1 / avg_loss) if avg_loss > 0 else np.nan

    def value_at_risk(self, confidence_level=0.05):
        """Value at Risk (VaR) at given confidence level."""
        return self.daily_pnl.quantile(confidence_level)

    def return_max_drawdown_ratio(self):
        """Return to max drawdown ratio."""
        total_return = (
            self.cumulative_pnl.iloc[-1] if len(self.cumulative_pnl) > 0 else 0
        )
        max_dd = abs(self.max_drawdown())
        if max_dd == 0 or np.isnan(max_dd):
            return np.nan
        return total_return / max_dd

    def total_fees_paid(self):
        """Calculate total fees paid during backtest period."""
        if "total_fee_cumsum" in self.backtest.df.columns:
            return self.backtest.df["total_fee_cumsum"].iloc[-1]
        return 0

    def fee_impact(self):
        """Calculate impact of fees on overall returns."""
        if "pnl_raw" not in self.backtest.df.columns:
            return 0
        total_raw = self.backtest.df["pnl_raw"].sum()
        total_fees = self.total_fees_paid()
        if total_raw == 0:
            return np.nan
        return total_fees / total_raw if total_raw > 0 else 0
