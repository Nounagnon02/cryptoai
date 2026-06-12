"""
Performance Metrics — Calcul des métriques de performance pour backtesting.

Métriques disponibles :
- Sharpe Ratio (annualisé, risk-free rate ajustable)
- Sortino Ratio (downside deviation uniquement)
- Calmar Ratio (CAGR / Max Drawdown)
- Max Drawdown avec timestamps peak/valley
- Win Rate, Profit Factor, Avg Win/Loss
- Recovery Factor, Risk of Ruin
- CAGR, Total Return
- Benchmark comparison (Buy & Hold)

Toutes les métriques sont calculées à partir des mêmes données brutes :
    - Trades individuels (entry/exit, pnl)
    - Equity curve (timestamp, equity value)
    - Capital initial
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np


@dataclass
class MetricsReport:
    """Rapport complet de métriques de performance."""

    # Capital
    initial_capital: float
    final_capital: float
    total_return: float  # $ absolu
    total_return_pct: float  # %

    # Trading stats
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # %
    avg_win: float  # $ par trade gagnant
    avg_loss: float  # $ par trade perdant
    largest_win: float
    largest_loss: float
    avg_holding_periods: float  # en barres
    profit_factor: float  # gains totaux / pertes totales

    # Ratios ajustés au risque
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float

    # Drawdown
    max_drawdown: float  # $ peak-to-valley
    max_drawdown_pct: float  # %
    max_drawdown_peak: datetime  # timestamp du peak
    max_drawdown_valley: datetime  # timestamp du valley
    avg_drawdown_pct: float  # drawdown moyen
    drawdown_days: int  # jours en drawdown

    # Growth
    cagr: float  # Compound Annual Growth Rate (%)
    avg_daily_return: float
    avg_daily_return_pct: float

    # Risk
    volatility_annual: float  # volatilité annualisée
    downside_deviation: float  # downside deviation annualisée
    value_at_risk_95: float  # VaR 95% (%)
    conditional_var_95: float  # CVaR 95%
    risk_of_ruin: float  # probabilité de ruine (%)

    # Recovery
    recovery_factor: float  # return / max drawdown
    ulcer_index: float  # profondeur * durée des drawdowns

    # Résumé textuel
    summary: str = ""


class PerformanceMetrics:
    """
    Calculateur de métriques de performance.

    Prend les trades bruts et l'equity curve, retourne un MetricsReport
    complet avec toutes les métriques standard de l'industrie.
    """

    def calculate(
        self,
        initial_capital: float,
        final_capital: float,
        trades: list[Any],
        equity_curve: list[dict[str, Any]],
        risk_free_rate: float = 0.05,
        trading_days: int = 365,
    ) -> MetricsReport:
        """
        Calcule toutes les métriques de performance.

        Args:
            initial_capital: Capital initial
            final_capital: Capital final
            trades: Liste des trades (doivent avoir .pnl, .entry_time, .exit_time)
            equity_curve: Liste de dicts avec 'timestamp', 'equity'
            risk_free_rate: Taux sans risque annualisé (ex: 0.05 = 5%)
            trading_days: Jours de trading par an

        Returns:
            MetricsReport complet
        """
        # --- Trading stats ---
        total_trades = len(trades)
        winning_trades_list = [t for t in trades if t.pnl > 0]
        losing_trades_list = [t for t in trades if t.pnl < 0]
        winning_trades_count = len(winning_trades_list)
        losing_trades_count = len(losing_trades_list)

        win_rate = (winning_trades_count / max(total_trades, 1)) * 100

        avg_win = sum(t.pnl for t in winning_trades_list) / max(winning_trades_count, 1)
        avg_loss = abs(sum(t.pnl for t in losing_trades_list)) / max(losing_trades_count, 1)

        largest_win = max((t.pnl for t in trades), default=0.0)
        largest_loss = min((t.pnl for t in trades), default=0.0)

        # Holding periods
        holding_periods = [
            getattr(t, "holding_bars", 0) for t in trades
            if getattr(t, "holding_bars", 0) > 0
        ]
        avg_holding = sum(holding_periods) / max(len(holding_periods), 1)

        # Profit factor
        gross_profit = sum(t.pnl for t in winning_trades_list)
        gross_loss = abs(sum(t.pnl for t in losing_trades_list))
        profit_factor = gross_profit / max(gross_loss, 1e-10)

        # --- Returns ---
        total_return = final_capital - initial_capital
        total_return_pct = (total_return / max(initial_capital, 1)) * 100

        # --- Equity curve processing ---
        if len(equity_curve) < 2:
            return self._minimal_report(
                initial_capital, final_capital, total_return, total_return_pct,
                total_trades, winning_trades_count, losing_trades_count, win_rate,
                avg_win, avg_loss, largest_win, largest_loss, avg_holding,
                profit_factor, trades,
            )

        # Extraire la série d'equity
        equity_values = np.array([p["equity"] for p in equity_curve])
        timestamps = [p["timestamp"] for p in equity_curve]

        # Returns journaliers (en %) — approximés par les changements de barre
        daily_returns = np.diff(equity_values) / equity_values[:-1] * 100
        if len(daily_returns) == 0:
            daily_returns = np.array([0.0])

        # --- Drawdown ---
        peak_values = np.maximum.accumulate(equity_values)
        drawdowns = equity_values - peak_values
        drawdown_pcts = (drawdowns / peak_values) * 100

        max_drawdown_idx = np.argmin(drawdowns)
        max_drawdown = abs(drawdowns[max_drawdown_idx])
        max_drawdown_pct = abs(drawdown_pcts[max_drawdown_idx])

        # Trouver le peak avant le max drawdown
        peak_idx = np.argmax(equity_values[:max_drawdown_idx + 1]) if max_drawdown_idx > 0 else 0

        def safe_get_timestamp(idx: int) -> datetime:
            try:
                ts = timestamps[idx]
                if isinstance(ts, datetime):
                    return ts
                return datetime.fromisoformat(str(ts)) if isinstance(ts, str) else datetime.min
            except (IndexError, ValueError):
                return datetime.min

        max_dd_peak_time = safe_get_timestamp(peak_idx)
        max_dd_valley_time = safe_get_timestamp(max_drawdown_idx)

        # Drawdown moyen (hors zéro)
        non_zero_dd_pcts = drawdown_pcts[drawdown_pcts < 0]
        avg_drawdown_pct = abs(float(np.mean(non_zero_dd_pcts))) if len(non_zero_dd_pcts) > 0 else 0.0

        # Jours en drawdown
        in_dd = drawdowns < 0
        drawdown_bars = int(np.sum(in_dd))

        # --- Volatilité ---
        volatility_annual = float(np.std(daily_returns, ddof=1)) * np.sqrt(trading_days)

        # --- Sharpe Ratio ---
        excess_returns = daily_returns - (risk_free_rate / trading_days * 100)
        sharpe_numerator = float(np.mean(excess_returns))
        sharpe_denominator = float(np.std(excess_returns, ddof=1))
        if sharpe_denominator > 0:
            sharpe_ratio = (sharpe_numerator / sharpe_denominator) * np.sqrt(trading_days)
        else:
            sharpe_ratio = 0.0

        # --- Sortino Ratio ---
        downside_returns = daily_returns[daily_returns < 0]
        downside_std = float(np.std(downside_returns, ddof=1)) if len(downside_returns) > 1 else 1.0
        downside_deviation_annual = downside_std * np.sqrt(trading_days)
        sortino_numerator = float(np.mean(daily_returns) - (risk_free_rate / trading_days * 100))
        sortino_ratio = (sortino_numerator / max(downside_std, 1e-10)) * np.sqrt(trading_days)

        # --- CAGR ---
        n_days = max(len(equity_curve), 1)
        years = n_days / trading_days if trading_days > 0 else 1
        if years > 0 and initial_capital > 0:
            cagr = ((final_capital / max(initial_capital, 1)) ** (1 / max(years, 0.01)) - 1) * 100
        else:
            cagr = 0.0

        # --- Calmar Ratio ---
        calmar_ratio = cagr / max(max_drawdown_pct, 1e-10) if max_drawdown_pct > 0 else 0.0

        # --- Recovery Factor ---
        recovery_factor = abs(total_return / max(max_drawdown, 1e-10)) if max_drawdown > 0 else 0.0

        # --- Ulcer Index ---
        if len(drawdown_pcts) > 0:
            squared_dd = drawdown_pcts[drawdown_pcts < 0] ** 2
            ulcer_index = np.sqrt(np.mean(squared_dd)) if len(squared_dd) > 0 else 0.0
        else:
            ulcer_index = 0.0

        # --- VaR et CVaR ---
        var_95 = float(np.percentile(daily_returns, 5)) if len(daily_returns) > 0 else 0.0
        cvar_95 = float(np.mean(daily_returns[daily_returns <= var_95])) if len(daily_returns[daily_returns <= var_95]) > 0 else 0.0

        # --- Risk of Ruin (probabilité simplifiée) ---
        # Formule : ( (1 - edge) / (1 + edge) ) ^ N
        # où edge = win_rate * avg_win - (1-win_rate) * avg_loss
        if total_trades > 0 and win_rate > 0:
            edge = (win_rate / 100) * avg_win - (1 - win_rate / 100) * avg_loss
            if edge > 0:
                q_over_p = (1 - win_rate / 100) / (win_rate / 100)
                risk_of_ruin = q_over_p ** min(total_trades, 100)
                risk_of_ruin = min(max(risk_of_ruin * 100, 0), 100)
            else:
                risk_of_ruin = 100.0  # edge négatif = ruine certaine
        else:
            risk_of_ruin = 100.0

        # --- Daily returns ---
        avg_daily_return = float(np.mean(daily_returns)) if len(daily_returns) > 0 else 0.0
        avg_daily_return_pct = avg_daily_return

        # --- Summary text ---
        summary = self._generate_summary(
            total_return_pct=total_return_pct,
            sharpe=sharpe_ratio,
            max_dd=max_drawdown_pct,
            win_rate=win_rate,
            profit_factor=profit_factor,
            total_trades=total_trades,
            cagr=cagr,
            calmar=calmar_ratio,
            sortino=sortino_ratio,
        )

        return MetricsReport(
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=round(total_return, 2),
            total_return_pct=round(total_return_pct, 2),
            total_trades=total_trades,
            winning_trades=winning_trades_count,
            losing_trades=losing_trades_count,
            win_rate=round(win_rate, 1),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            largest_win=round(largest_win, 2),
            largest_loss=round(largest_loss, 2),
            avg_holding_periods=round(avg_holding, 1),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=round(sharpe_ratio, 2),
            sortino_ratio=round(sortino_ratio, 2),
            calmar_ratio=round(calmar_ratio, 2),
            max_drawdown=round(max_drawdown, 2),
            max_drawdown_pct=round(max_drawdown_pct, 2),
            max_drawdown_peak=max_dd_peak_time,
            max_drawdown_valley=max_dd_valley_time,
            avg_drawdown_pct=round(avg_drawdown_pct, 2),
            drawdown_days=drawdown_bars,
            cagr=round(cagr, 2),
            avg_daily_return=round(avg_daily_return, 2),
            avg_daily_return_pct=round(avg_daily_return_pct, 2),
            volatility_annual=round(volatility_annual, 2),
            downside_deviation=round(downside_deviation_annual, 2),
            value_at_risk_95=round(var_95, 2),
            conditional_var_95=round(cvar_95, 2),
            risk_of_ruin=round(risk_of_ruin, 1),
            recovery_factor=round(recovery_factor, 2),
            ulcer_index=round(float(ulcer_index), 2),
            summary=summary,
        )

    def _generate_summary(
        self,
        total_return_pct: float,
        sharpe: float,
        max_dd: float,
        win_rate: float,
        profit_factor: float,
        total_trades: int,
        cagr: float,
        calmar: float,
        sortino: float,
    ) -> str:
        """Génère un résumé textuel des performances."""
        parts = [
            f"Return: {total_return_pct:+.2f}%",
            f"CAGR: {cagr:+.2f}%",
            f"Sharpe: {sharpe:.2f}",
            f"Sortino: {sortino:.2f}",
            f"Calmar: {calmar:.2f}",
            f"Max DD: {max_dd:.1f}%",
            f"Win Rate: {win_rate:.1f}%",
            f"Profit Factor: {profit_factor:.2f}",
            f"Trades: {total_trades}",
        ]

        # Évaluation qualitative
        score = 0
        if total_return_pct > 0:
            score += 1
        if sharpe > 1.0:
            score += 1
        if sharpe > 1.5:
            score += 1
        if max_dd < 25:
            score += 1
        if max_dd < 15:
            score += 1
        if win_rate > 55:
            score += 1
        if profit_factor > 1.5:
            score += 1
        if profit_factor > 2.0:
            score += 1

        if score >= 7:
            rating = "⭐ EXCELLENT"
        elif score >= 5:
            rating = "✅ GOOD"
        elif score >= 3:
            rating = "⚠️ ACCEPTABLE"
        else:
            rating = "❌ POOR"

        parts.insert(0, f"[{rating}]")
        return " | ".join(parts)

    def _minimal_report(
        self,
        initial_capital: float,
        final_capital: float,
        total_return: float,
        total_return_pct: float,
        total_trades: int,
        winning_trades: int,
        losing_trades: int,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        largest_win: float,
        largest_loss: float,
        avg_holding: float,
        profit_factor: float,
        _trades: list[Any],
    ) -> MetricsReport:
        """Retourne un rapport minimal quand les données sont insuffisantes."""
        return MetricsReport(
            initial_capital=initial_capital,
            final_capital=final_capital,
            total_return=round(total_return, 2),
            total_return_pct=round(total_return_pct, 2),
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=round(win_rate, 1),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            largest_win=round(largest_win, 2),
            largest_loss=round(largest_loss, 2),
            avg_holding_periods=round(avg_holding, 1),
            profit_factor=round(profit_factor, 2),
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            calmar_ratio=0.0,
            max_drawdown=0.0,
            max_drawdown_pct=0.0,
            max_drawdown_peak=datetime.min,
            max_drawdown_valley=datetime.min,
            avg_drawdown_pct=0.0,
            drawdown_days=0,
            cagr=0.0,
            avg_daily_return=0.0,
            avg_daily_return_pct=0.0,
            volatility_annual=0.0,
            downside_deviation=0.0,
            value_at_risk_95=0.0,
            conditional_var_95=0.0,
            risk_of_ruin=100.0,
            recovery_factor=0.0,
            ulcer_index=0.0,
            summary="Insufficient data for full metrics (need ≥ 2 equity curve points)",
        )

    @staticmethod
    def calculate_sharpe(
        returns: list[float],
        risk_free_rate: float = 0.05,
        periods_per_year: int = 365,
    ) -> float:
        """Calcule le Sharpe Ratio à partir d'une série de returns."""
        if len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns)
        excess = returns_arr - (risk_free_rate / periods_per_year)
        if np.std(excess, ddof=1) > 0:
            return float(np.mean(excess) / np.std(excess, ddof=1) * np.sqrt(periods_per_year))
        return 0.0

    @staticmethod
    def calculate_sortino(
        returns: list[float],
        risk_free_rate: float = 0.05,
        periods_per_year: int = 365,
    ) -> float:
        """Calcule le Sortino Ratio."""
        if len(returns) < 2:
            return 0.0

        returns_arr = np.array(returns)
        excess = np.mean(returns_arr) - (risk_free_rate / periods_per_year)
        downside = returns_arr[returns_arr < 0]
        if len(downside) == 0:
            return 0.0

        downside_std = np.std(downside, ddof=1)
        if downside_std > 0:
            return float(excess / downside_std * np.sqrt(periods_per_year))
        return 0.0

    @staticmethod
    def calculate_max_drawdown(equity_curve: list[float]) -> dict[str, float]:
        """Calcule le drawdown maximum à partir de l'equity curve."""
        if len(equity_curve) < 2:
            return {"max_drawdown": 0.0, "max_drawdown_pct": 0.0}

        equity_arr = np.array(equity_curve)
        peak = np.maximum.accumulate(equity_arr)
        drawdown = (equity_arr - peak) / peak * 100
        max_dd_idx = np.argmin(drawdown)

        return {
            "max_drawdown": float(peak[max_dd_idx] - equity_arr[max_dd_idx]),
            "max_drawdown_pct": float(abs(drawdown[max_dd_idx])),
        }

    @staticmethod
    def calculate_cagr(
        initial_value: float,
        final_value: float,
        years: float,
    ) -> float:
        """Calcule le CAGR."""
        if initial_value <= 0 or years <= 0:
            return 0.0
        return ((final_value / initial_value) ** (1 / years) - 1) * 100

    @staticmethod
    def calculate_profit_factor(trades: list[Any]) -> float:
        """Calcule le Profit Factor."""
        gross_profit = sum(t.pnl for t in trades if t.pnl > 0)
        gross_loss = abs(sum(t.pnl for t in trades if t.pnl < 0))
        return gross_profit / max(gross_loss, 1e-10)

    @staticmethod
    def calculate_win_rate(trades: list[Any]) -> float:
        """Calcule le Win Rate en %."""
        if not trades:
            return 0.0
        winning = sum(1 for t in trades if t.pnl > 0)
        return (winning / len(trades)) * 100

    @staticmethod
    def calculate_consecutive_wins_losses(trades: list[Any]) -> dict[str, int]:
        """Calcule les séquences consécutives de wins/losses."""
        max_win_streak = 0
        max_loss_streak = 0
        current_win = 0
        current_loss = 0

        for t in trades:
            if t.pnl > 0:
                current_win += 1
                current_loss = 0
                max_win_streak = max(max_win_streak, current_win)
            elif t.pnl < 0:
                current_loss += 1
                current_win = 0
                max_loss_streak = max(max_loss_streak, current_loss)

        return {
            "max_consecutive_wins": max_win_streak,
            "max_consecutive_losses": max_loss_streak,
        }

    @staticmethod
    def generate_html_report(report: MetricsReport) -> str:
        """Génère un rapport HTML basique."""
        html = f"""<html><body>
<h2>Backtest Performance Report</h2>
<table border="1">
<tr><th>Metric</th><th>Value</th></tr>
<tr><td>Total Return</td><td>{report.total_return_pct:+.2f}%</td></tr>
<tr><td>CAGR</td><td>{report.cagr:+.2f}%</td></tr>
<tr><td>Sharpe Ratio</td><td>{report.sharpe_ratio:.2f}</td></tr>
<tr><td>Sortino Ratio</td><td>{report.sortino_ratio:.2f}</td></tr>
<tr><td>Calmar Ratio</td><td>{report.calmar_ratio:.2f}</td></tr>
<tr><td>Max Drawdown</td><td>{report.max_drawdown_pct:.2f}%</td></tr>
<tr><td>Win Rate</td><td>{report.win_rate:.1f}%</td></tr>
<tr><td>Profit Factor</td><td>{report.profit_factor:.2f}</td></tr>
<tr><td>Total Trades</td><td>{report.total_trades}</td></tr>
<tr><td>Risk of Ruin</td><td>{report.risk_of_ruin:.1f}%</td></tr>
</table>
<p>{report.summary}</p>
</body></html>"""
        return html
