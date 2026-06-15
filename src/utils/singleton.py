"""Registry lazy de singletons pour les managers du système."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

_instances: dict[str, Any] = {}

# ── Live Market Data Store ────────────────────────────────────
_live_market_data: dict[str, dict] = {}


def get_live_market_data(symbol: str) -> dict | None:
    """Données marché live pour un symbole (ticker + dernier OHLCV)."""
    return _live_market_data.get(symbol)


def set_live_market_data(symbol: str, data: dict) -> None:
    """Stocke les données marché live."""
    data["_updated_at"] = datetime.now(UTC).isoformat()
    _live_market_data[symbol] = data


def get_all_live_market_data() -> dict[str, dict]:
    """Toutes les données marché live."""
    return dict(_live_market_data)


# ── Live AI Analysis Store ────────────────────────────────────
_live_analysis_results: dict[str, dict] = {}


def get_live_analysis(symbol: str) -> dict | None:
    """Dernière analyse IA live pour un symbole."""
    return _live_analysis_results.get(symbol)


def set_live_analysis(symbol: str, result: dict) -> None:
    """Stocke le résultat d'analyse IA live."""
    result["_updated_at"] = datetime.now(UTC).isoformat()
    _live_analysis_results[symbol] = result


def get_all_live_analyses() -> dict[str, dict]:
    """Toutes les analyses IA live."""
    return dict(_live_analysis_results)


# ── Paper Exchange ────────────────────────────────────────────
_paper_exchange: Any = None


def get_paper_exchange():
    """Instance du PaperExchange pour paper/live mode."""
    return _paper_exchange


def register_paper_exchange(exchange) -> None:
    """Enregistre l'instance PaperExchange (appelé par lifespan)."""
    global _paper_exchange
    _paper_exchange = exchange


# ── Decision Matrix ───────────────────────────────────────────
_decision_matrix: Any = None


def get_decision_matrix():
    """Instance de la DecisionMatrix."""
    return _decision_matrix


def register_decision_matrix(matrix) -> None:
    """Enregistre la DecisionMatrix (appelé par lifespan)."""
    global _decision_matrix
    _decision_matrix = matrix

def get_portfolio_manager():
    from src.portfolio.manager import PortfolioManager
    if "portfolio" not in _instances:
        try:
            pm = PortfolioManager()
            pm.initialize(100_000.0)
            _instances["portfolio"] = pm
        except Exception:
            return None
    return _instances["portfolio"]

def get_risk_manager():
    from src.risk.manager import RiskManager
    if "risk" not in _instances:
        try:
            _instances["risk"] = RiskManager()
        except Exception:
            return None
    return _instances["risk"]

def get_circuit_breaker():
    from src.risk.circuit_breaker import CircuitBreaker, CircuitBreakerConfig
    if "circuit_breaker" not in _instances:
        try:
            _instances["circuit_breaker"] = CircuitBreaker(CircuitBreakerConfig())
        except Exception:
            return None
    return _instances["circuit_breaker"]

def get_ai_agent():
    from src.core.ai_agent import CentralAIAgent
    if "ai_agent" not in _instances:
        try:
            _instances["ai_agent"] = CentralAIAgent()
        except Exception:
            return None
    return _instances["ai_agent"]

def get_execution_manager():
    from src.execution.manager import ExecutionConfig, ExecutionManager
    if "execution" not in _instances:
        try:
            _instances["execution"] = ExecutionManager(ExecutionConfig())
        except Exception:
            return None
    return _instances["execution"]

def get_technical_engine():
    from src.analysis.technical.engine import TechnicalAnalysisEngine
    if "technical" not in _instances:
        try:
            _instances["technical"] = TechnicalAnalysisEngine()
        except Exception:
            return None
    return _instances["technical"]
