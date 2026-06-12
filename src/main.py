"""
Point d'entrée principal du système CryptoAI.

Usage:
    python -m src.main --mode paper          # Paper trading
    python -m src.main --mode live            # Live trading (⚠️ argent réel)
    python -m src.main --worker               # Mode worker (collecte + analyse)
    python -m src.main --mode backtest        # Mode backtest

Exemple:
    python -m src.main --mode paper --config configs/default.yaml
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from src.config import config, reload_config
from src.utils.database import db
from src.utils.logging import get_logger, setup_logging

logger = get_logger(__name__)


class CryptoAISystem:
    """
    Orchestrateur principal du système.

    Gère le cycle de vie complet : démarrage des composants,
    supervision, arrêt contrôlé.
    """

    def __init__(self, mode: str, config_path: str) -> None:
        self.mode = mode
        self.config_path = config_path
        self._running = False
        self._components: list = []

        # Config
        if config_path:
            reload_config(config_path)

    async def initialize(self) -> None:
        """Initialise tous les composants du système."""
        self._running = True

        logger.info(
            "Initialisation du système",
            extra={
                "mode": self.mode,
                "version": "1.0.0",
                "watchlist": config.watchlist,
            },
        )

        # 1. Base de données
        await db.initialize()

        # 2. Collecteur de données marché
        if self.mode != "backtest":
            from src.data.collectors.market_collector import MarketCollector
            collector = MarketCollector()
            await collector.start()
            self._components.append(collector)
            logger.info("Market Collector démarré")

        # 3. Moteur d'analyse technique
        if self.mode != "backtest":
            from src.analysis.technical import TechnicalAnalysisEngine
            engine = TechnicalAnalysisEngine()
            await engine.start()
            self._components.append(engine)
            logger.info("Technical Analysis Engine démarré")

    async def run(self) -> None:
        """Boucle principale du système."""
        await self.initialize()
        logger.info("Système CryptoAI opérationnel", extra={"mode": self.mode})

        try:
            # Boucle principale — maintenir le système en vie
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Arrêt contrôlé de tous les composants."""
        logger.info("Arrêt du système en cours...")

        for component in reversed(self._components):
            try:
                if hasattr(component, "stop"):
                    await component.stop()
                elif hasattr(component, "close"):
                    await component.close()
            except Exception as e:
                logger.error("Erreur arrêt composant", extra={"error": str(e)})

        await db.shutdown()
        self._running = False
        logger.info("Système arrêté")


def parse_args() -> argparse.Namespace:
    """Parse les arguments CLI."""
    parser = argparse.ArgumentParser(
        description="CryptoAI — Plateforme de Trading Crypto Autonome",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Exemples:
  python -m src.main --mode paper
  python -m src.main --mode live
  python -m src.main --worker
  python -m src.main --mode backtest
        """,
    )

    parser.add_argument(
        "--mode",
        type=str,
        choices=["paper", "live", "backtest"],
        default="paper",
        help="Mode d'exécution (défaut: paper)",
    )
    parser.add_argument(
        "--config",
        type=str,
        default="configs/default.yaml",
        help="Chemin du fichier de configuration (défaut: configs/default.yaml)",
    )
    parser.add_argument(
        "--worker",
        action="store_true",
        help="Mode worker (collecte et analyse uniquement)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Logging verbose (DEBUG)",
    )

    return parser.parse_args()


async def async_main() -> None:
    """Point d'entrée asynchrone."""
    args = parse_args()

    # Logging
    log_level = "DEBUG" if args.verbose else "INFO"
    setup_logging(
        level=log_level,
        log_format=config.log_format,
        log_file="logs/cryptoai.log",
    )

    # Mode worker (collecte + analyse, pas d'API)
    if args.worker:
        logger.info("Démarrage en mode worker")
        config.mode = "paper"
        system = CryptoAISystem(mode="paper", config_path=args.config)
        await system.run()
        return

    # Mode système complet
    system = CryptoAISystem(mode=args.mode, config_path=args.config)
    await system.run()


def main() -> None:
    """Point d'entrée synchrone avec gestion des signaux."""
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        sys.exit(1)


if __name__ == "__main__":
    main()
