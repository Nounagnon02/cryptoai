"""
CLI Backtesting — Interface en ligne de commande pour le backtesting.

Usage :
    python -m src.backtesting.cli --strategy trend_following --symbol BTC/USDT \\
        --timeframe 1h --start 2024-01-01 --end 2024-12-31 --initial-capital 100000

    python -m src.backtesting.cli --compare --strategies trend_following,momentum \\
        --symbol BTC/USDT --timeframe 1h

    python -m src.backtesting.cli --walk-forward --strategy trend_following \\
        --symbol BTC/USDT --splits 3

Options :
    --strategy          Nom de la stratégie
    --strategies        Liste de stratégies (séparées par des virgules)
    --symbol            Paire de trading
    --timeframe         Timeframe (1m, 5m, 1h, 4h, 1d)
    --start             Date de début (YYYY-MM-DD)
    --end               Date de fin (YYYY-MM-DD)
    --initial-capital   Capital initial (défaut: 100000)
    --config            Fichier de configuration YAML
    --output            Fichier de sortie (JSON ou CSV)
    --compare           Mode comparaison
    --walk-forward      Mode walk-forward optimization
    --splits            Nombre de splits pour walk-forward
    --crisis            Mode crise (slippage plus élevé)
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from src.backtesting.comparator import StrategyComparator, WalkForwardOptimizer
from src.backtesting.engine import BacktestConfig, BacktestEngine
from src.data.market.schema import OHLCV
from src.portfolio.strategies import (
    MeanReversionStrategy,
    MomentumStrategy,
    SwingTradingStrategy,
    TrendFollowingStrategy,
)
from src.utils.logging import get_logger

logger = get_logger(__name__)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse les arguments de la ligne de commande."""
    parser = argparse.ArgumentParser(
        description="CryptoAI Backtesting Engine — Testez vos stratégies de trading",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples :
  # Backtest simple
  python -m src.backtesting.cli --strategy trend_following --symbol BTC/USDT \\
      --timeframe 1h --start 2024-01-01 --end 2024-12-31

  # Comparaison de stratégies
  python -m src.backtesting.cli --compare --strategies trend_following,momentum \\
      --symbol BTC/USDT

  # Walk-forward optimization
  python -m src.backtesting.cli --walk-forward --strategy trend_following \\
      --symbol BTC/USDT --splits 3

  # Export JSON
  python -m src.backtesting.cli --strategy momentum --output results.json
        """,
    )

    # Stratégie
    strategy_group = parser.add_mutually_exclusive_group()
    strategy_group.add_argument(
        "--strategy", type=str, default="trend_following",
        choices=["trend_following", "momentum", "mean_reversion", "swing_trading"],
        help="Nom de la stratégie à backtester",
    )
    strategy_group.add_argument(
        "--strategies", type=str,
        help="Liste de stratégies séparées par des virgules (mode comparaison)",
    )

    # Données
    parser.add_argument("--symbol", type=str, default="BTC/USDT", help="Paire de trading")
    parser.add_argument("--timeframe", type=str, default="1h", help="Timeframe")
    parser.add_argument("--start", type=str, help="Date de début (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="Date de fin (YYYY-MM-DD)")

    # Capital
    parser.add_argument(
        "--initial-capital", type=float, default=100_000.0,
        help="Capital initial en USD",
    )

    # Configuration
    parser.add_argument("--config", type=str, help="Fichier de configuration YAML")

    # Output
    parser.add_argument(
        "--output", type=str, help="Fichier de sortie (.json or .csv)",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Afficher les logs détaillés",
    )

    # Modes spéciaux
    parser.add_argument(
        "--compare", action="store_true",
        help="Mode comparaison : backtester plusieurs stratégies",
    )
    parser.add_argument(
        "--walk-forward", action="store_true",
        help="Mode walk-forward optimization",
    )
    parser.add_argument("--splits", type=int, default=3, help="Nombre de splits walk-forward")
    parser.add_argument(
        "--crisis", action="store_true",
        help="Mode crise : slippage et volatilité plus élevés",
    )

    return parser.parse_args(argv)


def generate_synthetic_ohlcv(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
    base_price: float = 30000.0,
    volatility: float = 0.02,
    trend: float = 0.0001,
) -> list[OHLCV]:
    """
    Génère des données OHLCV synthétiques pour le test.

    Utile quand aucune donnée réelle n'est disponible.
    Produit une série avec tendance et volatilité réalistes.
    """
    import math
    import random

    # Timedelta par timeframe
    td_map = {
        "1m": 60, "5m": 300, "15m": 900, "30m": 1800,
        "1h": 3600, "2h": 7200, "4h": 14400,
        "1d": 86400, "1w": 604800,
    }
    seconds = td_map.get(timeframe, 3600)

    data: list[OHLCV] = []
    price = base_price
    timestamp = int(start_date.timestamp())

    end_ts = int(end_date.timestamp())

    while timestamp <= end_ts:
        # Mouvement brownien géométrique avec trend
        drift = trend * seconds / 3600
        shock = volatility * random.gauss(0, 1) * math.sqrt(seconds / 86400)
        ret = drift + shock

        open_price = price
        close_price = price * (1 + ret)
        high_price = max(open_price, close_price) * (1 + abs(random.gauss(0, volatility * 0.5)))
        low_price = min(open_price, close_price) * (1 - abs(random.gauss(0, volatility * 0.5)))
        volume = random.uniform(100, 10000)

        data.append(OHLCV(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=datetime.fromtimestamp(timestamp, tz=UTC),
            open=round(open_price, 2),
            high=round(high_price, 2),
            low=round(low_price, 2),
            close=round(close_price, 2),
            volume=round(volume, 2),
        ))

        price = close_price
        timestamp += seconds

    return data


def setup_engine(args: argparse.Namespace) -> BacktestEngine:
    """Configure le BacktestEngine et enregistre les stratégies."""
    config = BacktestConfig(
        initial_capital=args.initial_capital,
        slippage_model="conservative" if not args.crisis else "moderate",
        slippage_bps=30 if args.crisis else 10,
    )

    engine = BacktestEngine(config=config)

    # Enregistrer les stratégies disponibles
    engine.register_strategy("trend_following", TrendFollowingStrategy())
    engine.register_strategy("momentum", MomentumStrategy())
    engine.register_strategy("mean_reversion", MeanReversionStrategy())
    engine.register_strategy("swing_trading", SwingTradingStrategy())

    return engine


def export_results(results: Any, output_path: str, format: str = "json") -> None:
    """Exporte les résultats dans un fichier."""
    path = Path(output_path)

    if format == "json":
        output = _result_to_dict(results)
        path.write_text(json.dumps(output, indent=2, default=str))
    elif format == "csv":
        _export_csv(results, path)
    else:
        logger.warning("Unsupported export format: %s", format)
        return

    logger.info("Results exported to %s", path.absolute())


def _result_to_dict(result: Any) -> dict[str, Any]:
    """Convertit un résultat en dictionnaire sérialisable."""
    if hasattr(result, "split"):  # WalkForwardResult
        return {
            "type": "walk_forward",
            "symbol": result.symbol,
            "strategy": result.strategy_name,
            "timeframe": result.timeframe,
            "splits": result.n_splits,
            "avg_train_return": result.avg_train_return,
            "avg_val_return": result.avg_val_return,
            "avg_sharpe_train": result.avg_sharpe_train,
            "avg_sharpe_val": result.avg_sharpe_val,
            "consistency": result.consistency_score,
            "stability": result.stability_score,
            "split_details": result.splits,
        }
    elif hasattr(result, "weighted_score"):  # ComparisonRanking
        return {
            "type": "comparison",
            "rankings": [
                {
                    "rank": r.rank,
                    "strategy": r.strategy_name,
                    "symbol": r.symbol,
                    "weighted_score": r.weighted_score,
                    "total_return_pct": r.total_return_pct,
                    "sharpe_ratio": r.sharpe_ratio,
                    "max_drawdown_pct": r.max_drawdown_pct,
                    "win_rate": r.win_rate,
                    "profit_factor": r.profit_factor,
                }
                for r in result
            ],
        }
    elif hasattr(result, "total_return"):  # BacktestResult
        return {
            "type": "backtest",
            "strategy": result.strategy_name,
            "symbol": result.symbol,
            "timeframe": result.timeframe,
            "start_date": str(result.start_date),
            "end_date": str(result.end_date),
            "initial_capital": result.initial_capital,
            "final_capital": result.final_capital,
            "total_return_pct": result.total_return_pct,
            "total_trades": result.total_trades,
            "win_rate": result.win_rate,
            "profit_factor": result.profit_factor,
            "sharpe_ratio": result.sharpe_ratio,
            "sortino_ratio": result.sortino_ratio,
            "calmar_ratio": result.calmar_ratio,
            "max_drawdown_pct": result.max_drawdown_pct,
            "recovery_factor": result.recovery_factor,
            "cagr": 0.0,  # Sera calculé si on a la durée
            "summary": result.summary,
        }

    return {"type": "unknown", "data": str(result)}


def _export_csv(results: Any, path: Path) -> None:
    """Exporte les résultats en CSV."""
    data = _result_to_dict(results)

    with path.open("w", newline="") as f:
        if data.get("type") == "comparison":
            writer = csv.DictWriter(f, fieldnames=[
                "rank", "strategy", "symbol", "weighted_score",
                "total_return_pct", "sharpe_ratio", "max_drawdown_pct",
                "win_rate", "profit_factor",
            ])
            writer.writeheader()
            for r in data["rankings"]:
                writer.writerow(r)
        elif data.get("type") == "backtest":
            writer = csv.DictWriter(f, fieldnames=list(data.keys()))
            writer.writeheader()
            writer.writerow(data)


def _get_date_range(args: argparse.Namespace) -> tuple[datetime, datetime]:
    """Détermine la plage de dates."""
    try:
        start = datetime.strptime(args.start, "%Y-%m-%d").replace(tzinfo=UTC) if args.start else datetime.now(
            UTC
        ).replace(day=1) - __import__("dateutil").relativedelta.relativedelta(months=6)
    except Exception:
        start = datetime.now(UTC).replace(day=1) - __import__("dateutil").relativedelta.relativedelta(months=6)

    try:
        end = datetime.strptime(args.end, "%Y-%m-%d").replace(tzinfo=UTC) if args.end else datetime.now(
            UTC
        )
    except Exception:
        end = datetime.now(UTC)

    return start, end


async def run_single(args: argparse.Namespace) -> None:
    """Exécute un backtest simple."""
    start, end = _get_date_range(args)

    logger.info(
        "Running backtest: %s on %s [%s → %s]",
        args.strategy, args.symbol,
        start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"),
    )

    # Générer les données synthétiques
    data = generate_synthetic_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start,
        end_date=end,
    )
    logger.info("Generated %d synthetic OHLCV bars", len(data))

    # Configurer et exécuter
    engine = setup_engine(args)

    result = await engine.run(
        ohlcv_data=data,
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )

    # Afficher le résultat

    # Export
    if args.output:
        fmt = "csv" if args.output.endswith(".csv") else "json"
        export_results(result, args.output, fmt)


async def run_comparison(args: argparse.Namespace) -> None:
    """Exécute une comparaison de stratégies."""
    strategies = [s.strip() for s in args.strategies.split(",")]
    start, end = _get_date_range(args)

    logger.info(
        "Comparing strategies: %s on %s",
        ", ".join(strategies), args.symbol,
    )

    # Générer les données
    data = generate_synthetic_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start,
        end_date=end,
    )

    engine = setup_engine(args)

    # Backtester chaque stratégie
    results = []
    for strategy_name in strategies:
        logger.info("Backtesting %s...", strategy_name)
        result = await engine.run(
            ohlcv_data=data,
            strategy_name=strategy_name,
            symbol=args.symbol,
            timeframe=args.timeframe,
        )
        results.append(result)

    # Comparer
    comparator = StrategyComparator()
    rankings = comparator.compare(results)

    # Afficher

    # Corrélation
    comparator.correlation_matrix(results)

    # Export
    if args.output:
        export_results(rankings, args.output)


async def run_walk_forward(args: argparse.Namespace) -> None:
    """Exécute une optimisation walk-forward."""
    start, end = _get_date_range(args)

    logger.info(
        "Walk-Forward: %s on %s (%d splits)",
        args.strategy, args.symbol, args.splits,
    )

    data = generate_synthetic_ohlcv(
        symbol=args.symbol,
        timeframe=args.timeframe,
        start_date=start,
        end_date=end,
    )

    engine = setup_engine(args)

    optimizer = WalkForwardOptimizer(n_splits=args.splits)
    result = await optimizer.run(
        engine=engine,
        ohlcv_data=data,
        strategy_name=args.strategy,
        symbol=args.symbol,
        timeframe=args.timeframe,
    )


    if args.output:
        export_results(result, args.output)


async def main(argv: list[str] | None = None) -> None:
    """Point d'entrée principal du CLI."""
    args = parse_args(argv)

    if args.verbose:
        import logging
        logging.getLogger().setLevel(logging.INFO)

    try:
        if args.compare:
            await run_comparison(args)
        elif args.walk_forward:
            await run_walk_forward(args)
        else:
            await run_single(args)
    except KeyboardInterrupt:
        logger.info("Backtest interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error("Backtest failed: %s", e, exc_info=args.verbose)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
