"""
CryptoAI — Plateforme de Trading Crypto Autonome pilotée par IA.

Architecture modulaire orientée microservices :
- data/       : Collecte et stockage des données marché
- analysis/   : Moteurs d'analyse technique, on-chain, sentiment
- core/       : Agent IA et moteur de décision
- risk/       : Gestion des risques institutionnelle
- portfolio/  : Gestion et allocation de portefeuille
- execution/  : Connecteurs exchanges et exécution d'ordres
- backtesting/: Moteur de backtesting et simulation
- api/        : API REST FastAPI
- monitoring/ : Observabilité et métriques
- utils/      : Utilitaires (sécurité, logging, DB)
"""

__version__ = "1.0.0"
__author__ = "CryptoAI Team"
