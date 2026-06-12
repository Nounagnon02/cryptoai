"""
Strategy Comparator — Comparaison et optimisation de stratégies.

Fonctionnalités :
- Compare plusieurs runs de backtest (mêmes données, paramètres différents)
- Walk-Forward Optimization : train/validation splits glissants
- Matrice de corrélation entre stratégies
- Classement pondéré (Sharpe × Win Rate × Drawdown)
- Rapport de comparaison formaté
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from src.backtesting.engine import BacktestResult


@dataclass
class ComparisonRanking:
    """Classement d'une stratégie dans la comparaison."""

    rank: int
    strategy_name: str
    symbol: str
    weighted_score: float

    # Métriques individuelles
    total_return_pct: float
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    max_drawdown_pct: float
    win_rate: float
    profit_factor: float
    total_trades: int

    # Scores individuels (normalisés 0-100)
    return_score: float
    risk_score: float
    consistency_score: float


@dataclass
class WalkForwardResult:
    """Résultat d'une optimisation walk-forward."""

    # Configuration
    symbol: str
    strategy_name: str
    timeframe: str
    n_splits: int
    train_pct: float

    # Résultats par split
    splits: list[dict[str, Any]] = field(default_factory=list)

    # Performance agrégée
    avg_train_return: float = 0.0
    avg_val_return: float = 0.0
    avg_sharpe_train: float = 0.0
    avg_sharpe_val: float = 0.0
    consistency_score: float = 0.0  # % de splits où train & val sont positifs
    stability_score: float = 0.0  # corrélation train vs val


class StrategyComparator:
    """
    Comparateur de stratégies.

    Compare plusieurs runs de backtest avec des métriques normalisées
    et produit un classement pondéré.
    """

    # Poids par défaut pour le classement
    DEFAULT_WEIGHTS = {
        "sharpe_ratio": 0.25,
        "total_return_pct": 0.20,
        "max_drawdown_pct": 0.15,  # négatif : moins de drawdown = mieux
        "win_rate": 0.10,
        "profit_factor": 0.10,
        "calmar_ratio": 0.10,
        "sortino_ratio": 0.10,
    }

    def __init__(self, weights: dict[str, float] | None = None) -> None:
        self.weights = weights or dict(self.DEFAULT_WEIGHTS)

    def compare(self, results: list[BacktestResult]) -> list[ComparisonRanking]:
        """
        Compare plusieurs résultats de backtest.

        Args:
            results: Liste des résultats à comparer

        Returns:
            Classement trié par score pondéré (descendant)
        """
        if not results:
            return []

        # Normaliser chaque métrique sur 0-100
        rankings: list[ComparisonRanking] = []

        for result in results:
            scores = self._calculate_scores(result, results)
            weighted = self._weighted_score(scores)

            ranking = ComparisonRanking(
                rank=0,
                strategy_name=result.strategy_name,
                symbol=result.symbol,
                weighted_score=round(weighted, 2),
                total_return_pct=result.total_return_pct,
                sharpe_ratio=result.sharpe_ratio,
                sortino_ratio=result.sortino_ratio,
                calmar_ratio=result.calmar_ratio,
                max_drawdown_pct=result.max_drawdown_pct,
                win_rate=result.win_rate,
                profit_factor=result.profit_factor,
                total_trades=result.total_trades,
                return_score=scores["return"],
                risk_score=scores["risk"],
                consistency_score=scores["consistency"],
            )
            rankings.append(ranking)

        # Trier par score pondéré
        rankings.sort(key=lambda r: r.weighted_score, reverse=True)

        # Assigner les rangs
        for i, r in enumerate(rankings):
            r.rank = i + 1

        return rankings

    def _calculate_scores(
        self,
        result: BacktestResult,
        all_results: list[BacktestResult],
    ) -> dict[str, float]:
        """Calcule les scores normalisés (0-100) pour un résultat."""
        # Extraire les plages de valeurs
        returns = [r.total_return_pct for r in all_results]
        sharpes = [r.sharpe_ratio for r in all_results]
        max_dds = [r.max_drawdown_pct for r in all_results]
        win_rates = [r.win_rate for r in all_results]
        profit_factors = [r.profit_factor for r in all_results]
        calmars = [r.calmar_ratio for r in all_results]
        sortinos = [r.sortino_ratio for r in all_results]

        # Normalisation min-max (inversée pour drawdown)
        def normalize(value: float, series: list[float], invert: bool = False) -> float:
            mn = min(series)
            mx = max(series)
            if mx == mn:
                return 50.0
            normalized = (value - mn) / (mx - mn) * 100
            return 100 - normalized if invert else normalized

        # Score de rendement
        return_score = (
            normalize(result.total_return_pct, returns) * 0.5
            + normalize(result.sharpe_ratio, sharpes) * 0.3
            + normalize(result.calmar_ratio, calmars) * 0.2
        )

        # Score de risque
        if result.max_drawdown_pct <= 25:
            risk_score = (
                normalize(result.max_drawdown_pct, max_dds, invert=True) * 0.5
                + normalize(result.sortino_ratio, sortinos) * 0.3
                + min(result.max_drawdown_pct / 5, 100) * 0.2
            )
        else:
            risk_score = (
                normalize(result.max_drawdown_pct, max_dds, invert=True) * 0.7
                + normalize(result.sortino_ratio, sortinos) * 0.3
            )

        # Score de consistance
        consistency_score = (
            normalize(result.win_rate, win_rates) * 0.4
            + normalize(result.profit_factor, profit_factors) * 0.3
            + self._calculate_consistency(result) * 0.3
        )

        return {
            "return": min(return_score, 100),
            "risk": min(risk_score, 100),
            "consistency": min(consistency_score, 100),
        }

    def _calculate_consistency(self, result: BacktestResult) -> float:
        """Calcule un score de consistance basé sur les trades."""
        if result.total_trades < 5:
            return 0.0

        trades = result.trades
        if not trades:
            return 0.0

        # Ratio trades gagnants / perdants
        win_loss_ratio = result.avg_win / max(result.avg_loss, 1e-10) if result.avg_loss > 0 else 10.0

        # Stabilité des returns
        pnls = [t.pnl for t in trades if t.pnl != 0]
        if len(pnls) < 5:
            return 50.0

        pnl_std = np.std(pnls) if len(pnls) > 1 else 1.0
        pnl_mean = abs(np.mean(pnls))
        stability = min(pnl_mean / max(pnl_std, 1e-10), 3.0) / 3.0 * 100

        # Score composite
        score = (min(win_loss_ratio / 3, 1.0) * 50) + (stability * 0.5)
        return min(score, 100)

    def _weighted_score(self, scores: dict[str, float]) -> float:
        """Calcule le score pondéré final."""
        return (
            scores["return"] * self.weights.get("total_return_pct", 0.20)
            + scores["risk"] * self.weights.get("max_drawdown_pct", 0.15)
            + scores["consistency"] * self.weights.get("win_rate", 0.10)
        )

    def correlation_matrix(self, results: list[BacktestResult]) -> dict[str, Any]:
        """
        Calcule la matrice de corrélation entre les stratégies.

        Utilise les séries d'equity curve pour calculer la corrélation
        des returns quotidiens entre chaque paire de stratégies.
        """
        if len(results) < 2:
            return {"correlation": [], "message": "Need at least 2 results"}

        names = [f"{r.strategy_name}_{r.symbol}" for r in results]
        n = len(results)

        corr_matrix = [[0.0] * n for _ in range(n)]

        for i in range(n):
            for j in range(n):
                if i == j:
                    corr_matrix[i][j] = 1.0
                elif j > i:
                    corr = self._calculate_return_correlation(results[i], results[j])
                    corr_matrix[i][j] = round(corr, 3)
                    corr_matrix[j][i] = corr_matrix[i][j]

        return {
            "names": names,
            "matrix": corr_matrix,
            "avg_correlation": round(
                sum(corr_matrix[i][j] for i in range(n) for j in range(n) if i != j)
                / max(n * (n - 1), 1), 3
            ),
        }

    def _calculate_return_correlation(self, r1: BacktestResult, r2: BacktestResult) -> float:
        """Calcule la corrélation des returns entre deux résultats."""
        eq1 = [p["equity"] for p in r1.equity_curve]
        eq2 = [p["equity"] for p in r2.equity_curve]

        min_len = min(len(eq1), len(eq2))
        if min_len < 5:
            return 0.0

        eq1 = eq1[:min_len]
        eq2 = eq2[:min_len]

        ret1 = np.diff(eq1) / np.array(eq1[:-1])
        ret2 = np.diff(eq2) / np.array(eq2[:-1])

        if len(ret1) < 2:
            return 0.0

        corr_matrix = np.corrcoef(ret1, ret2)
        return float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.0

    def generate_report(self, rankings: list[ComparisonRanking]) -> str:
        """Génère un rapport textuel de la comparaison."""
        if not rankings:
            return "No results to compare."

        lines = [
            "=" * 80,
            "STRATEGY COMPARISON REPORT",
            "=" * 80,
            "",
            f"{'Rank':<6} {'Strategy':<25} {'Score':<8} {'Return%':<10} {'Sharpe':<8} {'DD%':<8} {'Win%':<8} {'PF':<8}",
            "-" * 80,
        ]

        for r in rankings:
            lines.append(
                f"#{r.rank:<4} {r.strategy_name:<25} "
                f"{r.weighted_score:<8.1f} "
                f"{r.total_return_pct:<+10.2f} "
                f"{r.sharpe_ratio:<8.2f} "
                f"{r.max_drawdown_pct:<8.2f} "
                f"{r.win_rate:<8.1f} "
                f"{r.profit_factor:<8.2f}"
            )

        lines.extend([
            "-" * 80,
            "",
            "SCORES BREAKDOWN:",
        ])

        for r in rankings:
            lines.append(
                f"  #{r.rank}. {r.strategy_name:<20} "
                f"Return={r.return_score:.0f}  "
                f"Risk={r.risk_score:.0f}  "
                f"Consistency={r.consistency_score:.0f}"
            )

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)

    def to_dict(self, rankings: list[ComparisonRanking]) -> list[dict[str, Any]]:
        """Convertit le classement en liste de dicts (pour export JSON)."""
        return [
            {
                "rank": r.rank,
                "strategy": r.strategy_name,
                "symbol": r.symbol,
                "weighted_score": r.weighted_score,
                "total_return_pct": r.total_return_pct,
                "sharpe_ratio": r.sharpe_ratio,
                "sortino_ratio": r.sortino_ratio,
                "calmar_ratio": r.calmar_ratio,
                "max_drawdown_pct": r.max_drawdown_pct,
                "win_rate": r.win_rate,
                "profit_factor": r.profit_factor,
                "total_trades": r.total_trades,
            }
            for r in rankings
        ]


class WalkForwardOptimizer:
    """
    Optimisation Walk-Forward.

    Divise les données en splits train/validation glissants pour
    évaluer la robustesse des stratégies hors-échantillon.

    Principe :
        [train 60% | val 40%]
               [train 60% | val 40%]
                      [train 60% | val 40%]
    """

    def __init__(
        self,
        n_splits: int = 3,
        train_pct: float = 0.6,
        min_train_bars: int = 500,
        min_val_bars: int = 100,
    ) -> None:
        self.n_splits = n_splits
        self.train_pct = train_pct
        self.min_train_bars = min_train_bars
        self.min_val_bars = min_val_bars

    async def run(
        self,
        engine: Any,
        ohlcv_data: list[Any],
        strategy_name: str,
        symbol: str,
        timeframe: str,
        progress_callback: Any | None = None,
    ) -> WalkForwardResult:
        """
        Exécute l'optimisation walk-forward.

        Args:
            engine: BacktestEngine initialisé avec les stratégies
            ohlcv_data: Données OHLCV complètes
            strategy_name: Nom de la stratégie
            symbol: Symbole
            timeframe: Timeframe
            progress_callback: Callback optionnel

        Returns:
            WalkForwardResult
        """
        total_bars = len(ohlcv_data)

        if total_bars < self.min_train_bars + self.min_val_bars:
            raise ValueError(
                f"Not enough data: {total_bars} bars, need ≥ {self.min_train_bars + self.min_val_bars}"
            )

        # Définir les splits
        split_size = int(total_bars / self.n_splits)
        split_results: list[dict[str, Any]] = []

        for split_idx in range(self.n_splits):
            # Train set
            train_start = split_idx * split_size
            train_end = train_start + int(split_size * self.train_pct)

            # Validation set
            val_start = train_end + 1
            val_end = min(val_start + int(split_size * (1 - self.train_pct)), total_bars)

            # Vérifier la taille minimale
            if val_end - val_start < self.min_val_bars:
                break

            # Découper les données
            train_data = ohlcv_data[train_start:train_end]
            val_data = ohlcv_data[val_start:val_end]

            if len(train_data) < self.min_train_bars or len(val_data) < self.min_val_bars:
                continue

            # Backtest sur train
            train_result = await engine.run(
                ohlcv_data=train_data,
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
            )

            # Backtest sur validation
            val_result = await engine.run(
                ohlcv_data=val_data,
                strategy_name=strategy_name,
                symbol=symbol,
                timeframe=timeframe,
            )

            split_info = {
                "split": split_idx + 1,
                "train_start": train_start,
                "train_end": train_end,
                "val_start": val_start,
                "val_end": val_end,
                "train_return_pct": train_result.total_return_pct,
                "val_return_pct": val_result.total_return_pct,
                "train_sharpe": train_result.sharpe_ratio,
                "val_sharpe": val_result.sharpe_ratio,
                "train_trades": train_result.total_trades,
                "val_trades": val_result.total_trades,
                "train_max_dd": train_result.max_drawdown_pct,
                "val_max_dd": val_result.max_drawdown_pct,
            }
            split_results.append(split_info)

            if progress_callback:
                progress_callback(split_idx + 1, self.n_splits)

        if not split_results:
            raise ValueError("No valid splits could be created")

        # Métriques agrégées
        avg_train_ret = np.mean([s["train_return_pct"] for s in split_results])
        avg_val_ret = np.mean([s["val_return_pct"] for s in split_results])
        avg_sharpe_train = np.mean([s["train_sharpe"] for s in split_results])
        avg_sharpe_val = np.mean([s["val_sharpe"] for s in split_results])

        # Consistance : % de splits où train ET val sont positifs
        consistent = sum(
            1 for s in split_results if s["train_return_pct"] > 0 and s["val_return_pct"] > 0
        )
        consistency_pct = (consistent / len(split_results)) * 100

        # Stabilité : corrélation entre les returns train et val
        train_returns = [s["train_return_pct"] for s in split_results]
        val_returns = [s["val_return_pct"] for s in split_results]
        if len(split_results) > 1:
            corr = np.corrcoef(train_returns, val_returns)
            stability = float(corr[0, 1]) if not np.isnan(corr[0, 1]) else 0.0
        else:
            stability = 0.0

        return WalkForwardResult(
            symbol=symbol,
            strategy_name=strategy_name,
            timeframe=timeframe,
            n_splits=len(split_results),
            train_pct=self.train_pct,
            splits=split_results,
            avg_train_return=round(float(avg_train_ret), 2),
            avg_val_return=round(float(avg_val_ret), 2),
            avg_sharpe_train=round(float(avg_sharpe_train), 2),
            avg_sharpe_val=round(float(avg_sharpe_val), 2),
            consistency_score=round(consistency_pct, 1),
            stability_score=round(stability, 2),
        )

    def generate_report(self, result: WalkForwardResult) -> str:
        """Rapport textuel du walk-forward."""
        lines = [
            "=" * 80,
            f"WALK-FORWARD OPTIMIZATION: {result.strategy_name} on {result.symbol}",
            "=" * 80,
            f"  Splits: {result.n_splits} | Train: {result.train_pct:.0%} | Val: {1 - result.train_pct:.0%}",
            "",
            f"  Avg Train Return:  {result.avg_train_return:+.2f}%  "
            f"(Sharpe: {result.avg_sharpe_train:.2f})",
            f"  Avg Val Return:    {result.avg_val_return:+.2f}%  "
            f"(Sharpe: {result.avg_sharpe_val:.2f})",
            "",
            f"  Consistency:  {result.consistency_score:.0f}%  "
            f"(splits where both train & val are positive)",
            f"  Stability:    {result.stability_score:.2f}  "
            f"(correlation train vs val returns)",
            "",
            "  Split Details:",
            f"  {'#':<6} {'Train%':<10} {'Val%':<10} {'Train S':<10} {'Val S':<10} "
            f"{'Train DD':<10} {'Val DD':<10}",
            "-" * 80,
        ]

        for s in result.splits:
            lines.append(
                f"  {s['split']:<6} "
                f"{s['train_return_pct']:<+10.2f} "
                f"{s['val_return_pct']:<+10.2f} "
                f"{s['train_sharpe']:<10.2f} "
                f"{s['val_sharpe']:<10.2f} "
                f"{s['train_max_dd']:<10.2f} "
                f"{s['val_max_dd']:<10.2f}"
            )

        # Évaluation
        lines.extend([
            "-" * 80, "",
        ])

        if result.avg_val_return > 0 and result.avg_sharpe_val > 0.5:
            lines.append("  ✅ ROBUST: Positive returns out-of-sample with acceptable Sharpe.")
        elif result.avg_val_return > 0:
            lines.append("  ⚠️  MARGINAL: Positive but low robustness. Consider tighter risk controls.")
        else:
            lines.append("  ❌ OVERFIT: Negative out-of-sample returns. Strategy may be overfitted.")

        lines.append("")
        lines.append("=" * 80)
        return "\n".join(lines)
