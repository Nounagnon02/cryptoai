"""Registry lazy de singletons pour les managers du système."""
from __future__ import annotations

from typing import Any

_instances: dict[str, Any] = {}

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
