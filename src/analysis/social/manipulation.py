"""
Détection de manipulation des réseaux sociaux.

Identifie les patterns de manipulation :
- Astroturfing : faux soutien massif orchestré
- Bot armies : comptes automatisés
- Coordinated hashtag campaigns
- Pump and dump groups
- FUD orchestré
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from src.analysis.social.tracker import SocialMention
from src.utils.logging import get_logger

logger = get_logger(__name__)


@dataclass
class ManipulationIndicator:
    """Indicateur de manipulation sociale."""

    type: str  # astroturfing | bot_army | coordinated | pump_dump | fud_campaign
    severity: str  # low | medium | high | critical
    confidence: float  # 0-1
    description: str
    affected_mentions: int = 0
    details: dict[str, float] = field(default_factory=dict)


@dataclass
class SocialRiskScore:
    """Score de risque de manipulation."""

    symbol: str
    overall_risk: float  # 0-100
    risk_level: str  # low | medium | high | critical
    indicators: list[ManipulationIndicator] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class SocialManipulationDetector:
    """
    Détecte la manipulation des réseaux sociaux.

    Méthodes :
    - Analyse de répétition de contenu (copypasta)
    - Détection de comptes suspects (âge, ratio followers/engagement)
    - Coordination temporelle (pics synchronisés)
    - Analyse de réseau (clusters de comptes)
    """

    def __init__(self) -> None:
        self._scores: dict[str, SocialRiskScore] = {}
        self._seen_content: dict[str, set[str]] = {}

    def analyze(
        self,
        symbol: str,
        mentions: list[SocialMention],
    ) -> SocialRiskScore:
        """
        Analyse le risque de manipulation sociale pour un actif.

        Args:
            symbol: Actif analysé
            mentions: Mentions récentes

        Returns:
            Score de risque de manipulation
        """
        indicators: list[ManipulationIndicator] = []

        if len(mentions) < 10:
            return SocialRiskScore(
                symbol=symbol,
                overall_risk=0,
                risk_level="low",
                indicators=[],
            )

        # Différentes analyses
        try:
            dup_indicator = self._detect_content_repetition(symbol, mentions)
            if dup_indicator:
                indicators.append(dup_indicator)

            coord_indicator = self._detect_coordination(mentions)
            if coord_indicator:
                indicators.append(coord_indicator)

            bot_indicator = self._detect_bot_activity(mentions)
            if bot_indicator:
                indicators.append(bot_indicator)

            pump_indicator = self._detect_pump_dump(mentions)
            if pump_indicator:
                indicators.append(pump_indicator)
        except Exception as e:
            logger.error("Erreur analyse manipulation %s: %s", symbol, str(e))

        # Score global
        total_risk = 0.0
        for ind in indicators:
            severity_mult = {"low": 1, "medium": 3, "high": 7, "critical": 15}
            total_risk += severity_mult.get(ind.severity, 1) * ind.confidence

        overall_risk = min(100, total_risk / len(indicators) * 10) if indicators else 0

        if overall_risk > 60:
            risk_level = "critical"
        elif overall_risk > 40:
            risk_level = "high"
        elif overall_risk > 20:
            risk_level = "medium"
        else:
            risk_level = "low"

        warnings = [i.description for i in indicators if i.severity in ("high", "critical")]

        result = SocialRiskScore(
            symbol=symbol,
            overall_risk=round(overall_risk, 1),
            risk_level=risk_level,
            indicators=indicators,
            warnings=warnings[:5],
        )

        self._scores[symbol] = result
        return result

    def _detect_content_repetition(
        self,
        symbol: str,
        mentions: list[SocialMention],
    ) -> ManipulationIndicator | None:
        """
        Détecte le contenu répété (copypasta, astroturfing).
        """
        if symbol not in self._seen_content:
            self._seen_content[symbol] = set()

        # Normaliser et tracker le contenu
        normalized = {
            m.content.lower().strip()[:100]
            for m in mentions
        }

        # Compter les nouveaux contenus similaires
        duplicates = 0
        for content in normalized:
            for seen in self._seen_content[symbol]:
                if self._similarity(content, seen) > 0.85:
                    duplicates += 1
                    break

        self._seen_content[symbol].update(normalized)
        # Nettoyer (garder seulement 500 récents)
        if len(self._seen_content[symbol]) > 500:
            self._seen_content[symbol] = set(list(self._seen_content[symbol])[-500:])

        dup_ratio = duplicates / max(1, len(mentions))

        if dup_ratio > 0.3:
            return ManipulationIndicator(
                type="astroturfing",
                severity="high" if dup_ratio > 0.5 else "medium",
                confidence=min(0.9, dup_ratio),
                description=f"Contenu dupliqué détecté ({dup_ratio:.0%} des mentions)",
                affected_mentions=duplicates,
                details={"duplicate_ratio": round(dup_ratio, 2)},
            )

        return None

    def _detect_coordination(
        self,
        mentions: list[SocialMention],
    ) -> ManipulationIndicator | None:
        """
        Détecte les campagnes coordonnées (pics synchronisés).

        Vérifie si un petit nombre d'auteurs génère un grand
        volume de mentions sur une courte période.
        """
        if len(mentions) < 20:
            return None

        # Compter les mentions par auteur
        author_counts: dict[str, int] = {}
        for m in mentions:
            author_counts[m.author] = author_counts.get(m.author, 0) + 1

        # Vérifier la concentration
        top_authors = sorted(author_counts.values(), reverse=True)[:5]
        top_total = sum(top_authors)
        total = len(mentions)

        concentration = top_total / total if total > 0 else 0

        if concentration > 0.5 and top_authors[0] > 10:
            # Regrouper par fenêtre temporelle
            timestamps = sorted(m.timestamp for m in mentions)
            if len(timestamps) >= 2:
                time_span = timestamps[-1] - timestamps[0]
                mention_rate = total / max(1, time_span)

                if mention_rate > 10:  # >10 mentions par seconde
                    return ManipulationIndicator(
                        type="coordinated",
                        severity="high" if concentration > 0.7 else "medium",
                        confidence=min(0.9, concentration + mention_rate * 0.01),
                        description=f"Campagne coordonnée suspectée "
                                    f"(concentration: {concentration:.0%}, "
                                    f"rate: {mention_rate:.1f}/s)",
                        affected_mentions=top_total,
                        details={
                            "concentration": round(concentration, 2),
                            "mention_rate": round(mention_rate, 2),
                        },
                    )

        return None

    def _detect_bot_activity(self, mentions: list[SocialMention]) -> ManipulationIndicator | None:
        """
        Détecte l'activité de bots.

        Indices :
        - Ratio engagement/followers anormal
        - Comptes non vérifiés avec activité intense
        - Patterns d'activité réguliers
        """
        if len(mentions) < 10:
            return None

        # Analyser les comptes
        suspicious_count = 0
        for m in mentions:
            # Compte non vérifié avec peu de followers mais très actif
            if not m.is_verified and m.followers_count < 100 and m.engagement > 50:
                suspicious_count += 1
            # Ratio engagement/followers suspect
            if m.followers_count > 0 and m.engagement / m.followers_count > 0.5:
                suspicious_count += 1

        suspicious_ratio = suspicious_count / max(1, len(mentions))

        if suspicious_ratio > 0.3:
            return ManipulationIndicator(
                type="bot_army",
                severity="high" if suspicious_ratio > 0.6 else "medium",
                confidence=min(0.85, suspicious_ratio * 1.2),
                description=f"Activité bots suspectée ({suspicious_ratio:.0%} des comptes)",
                affected_mentions=suspicious_count,
                details={"suspicious_ratio": round(suspicious_ratio, 2)},
            )

        return None

    def _detect_pump_dump(self, mentions: list[SocialMention]) -> ManipulationIndicator | None:
        """
        Détecte les signes de pump & dump.

        Indices :
        - Pic soudain de mentions bullish
        - Langage d'urgence ("BUY NOW", "don't miss")
        - Hashtags de pump (pump, pumpit, etc.)
        """
        now = datetime.now(UTC).timestamp()

        # Mentions des dernières 30 minutes
        very_recent = [m for m in mentions if m.timestamp > now - 1800]

        if len(very_recent) < 5:
            return None

        # Analyser le langage
        urgent_terms = {"buy now", "don't miss", "pump", "guaranteed",
                       "sure thing", "free money", "going to moon",
                       "limited time", "act now", "once in a lifetime"}
        urgent_count = 0

        for m in very_recent:
            content_lower = m.content.lower()
            for term in urgent_terms:
                if term in content_lower:
                    urgent_count += 1
                    break

        urgent_ratio = urgent_count / len(very_recent)

        if urgent_ratio > 0.4:
            return ManipulationIndicator(
                type="pump_dump",
                severity="critical" if urgent_ratio > 0.7 else "high",
                confidence=min(0.95, urgent_ratio * 1.3),
                description=f"Tentative de pump & dump détectée "
                            f"({urgent_ratio:.0%} des mentions récentes)",
                affected_mentions=urgent_count,
                details={
                    "urgent_ratio": round(urgent_ratio, 2),
                    "recent_mentions": len(very_recent),
                },
            )

        return None

    def _similarity(self, a: str, b: str) -> float:
        """Similarité cosinus simple basée sur les mots."""
        words_a = set(a.split())
        words_b = set(b.split())

        if not words_a or not words_b:
            return 0.0

        intersection = words_a & words_b
        union = words_a | words_b

        return len(intersection) / len(union) if union else 0.0

    def get_risk(self, symbol: str) -> SocialRiskScore | None:
        """Dernier score de risque calculé."""
        return self._scores.get(symbol)

    def is_manipulated(self, symbol: str, threshold: float = 40) -> bool:
        """Vérifie si un actif subit une manipulation sociale."""
        risk = self.get_risk(symbol)
        return risk is not None and risk.overall_risk > threshold
