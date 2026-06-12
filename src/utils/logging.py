"""
Système de logging structuré.

Format JSON standardisé pour ingestion dans ELK/Loki.
Trace ID injecté automatiquement pour corrélation.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


class JSONFormatter(logging.Formatter):
    """Formateur JSON structuré pour logs machine-parsable."""

    def format(self, record: logging.LogRecord) -> str:
        log_entry: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # Ajouter les champs extra (trace_id, symbol, etc.)
        for key in ("trace_id", "symbol", "order_id", "duration_ms", "provider", "exchange"):
            value = getattr(record, key, None)
            if value is not None:
                log_entry[key] = value

        # Ajouter l'exception si présente
        if record.exc_info and record.exc_info[0]:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
            }

        return json.dumps(log_entry, default=str)


def setup_logging(
    level: str = "INFO",
    log_format: str = "json",
    log_file: str | None = None,
) -> None:
    """
    Configure le logging du système.

    Args:
        level: Niveau de log (DEBUG, INFO, WARN, ERROR)
        log_format: "json" pour structuré, "text" pour lisible
        log_file: Chemin du fichier de log (optionnel)
    """
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Éviter les handlers dupliqués
    if root_logger.handlers:
        return

    # Handler console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    if log_format == "json":
        console_handler.setFormatter(JSONFormatter())
    else:
        console_handler.setFormatter(
            logging.Formatter(
                "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
                datefmt="%Y-%m-%d %H:%M:%S",
            )
        )
    root_logger.addHandler(console_handler)

    # Handler fichier (si spécifié)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setFormatter(JSONFormatter())
        root_logger.addHandler(file_handler)

    # Réduire le bruit des librairies tierces
    for noisy_logger in ("ccxt.base.exchange", "urllib3", "asyncio"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger avec le nom du module."""
    return logging.getLogger(name)


class LoggerMixin:
    """
    Mixin pour ajouter un logger à n'importe quelle classe.

    Usage:
        class MyClass(LoggerMixin):
            def do_something(self):
                self.logger.info("Fait!")
    """

    @property
    def logger(self) -> logging.Logger:
        """Retourne un logger nommé pour cette classe."""
        return get_logger(f"{self.__class__.__module__}.{self.__class__.__name__}")
