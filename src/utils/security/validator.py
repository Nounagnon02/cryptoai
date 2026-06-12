"""
Input Validator — Validation et sanitization des entrées.

Valide toutes les entrées externes selon des règles configurables :
- Types et formats
- Plages de valeurs
- Patterns regex
- Longueurs min/max
- Prévention d'injection
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from re import Pattern
from typing import Any


@dataclass
class ValidationResult:
    """Résultat de validation."""

    is_valid: bool
    errors: list[str] = field(default_factory=list)
    sanitized_value: Any = None


class InputValidator:
    """
    Validateur d'entrées avec règles configurables.

    Supporte la validation de :
    - Strings (longueur, pattern, allowed values)
    - Nombres (min, max, step)
    - Booléens
    - Lists (min/max items, items types)
    - Dicts (required keys, optional keys, types)
    - Dates (format, min/max)
    """

    # Patterns de sécurité
    SQL_INJECTION_PATTERN = re.compile(
        r"(\b(ALTER|CREATE|DELETE|DROP|EXEC|INSERT|MERGE|SELECT|TRUNCATE|UPDATE|UNION)\b)",
        re.IGNORECASE,
    )
    XSS_PATTERN = re.compile(
        r"(<script|javascript:|onerror=|onclick=|onload=|<iframe|<embed|<object)",
        re.IGNORECASE,
    )
    COMMAND_INJECTION_PATTERN = re.compile(
        r"[;&|`$]|(\b(rm|wget|curl|bash|sh|powershell|cmd)\b)",
        re.IGNORECASE,
    )

    # Symboles autorisés pour les paires de trading
    SYMBOL_PATTERN = re.compile(r"^[A-Z0-9-/_]{2,20}$")

    # Format email
    EMAIL_PATTERN = re.compile(
        r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    )

    def __init__(self, strict_mode: bool = True) -> None:
        self.strict_mode = strict_mode

    def validate_string(
        self,
        value: Any,
        field_name: str = "value",
        min_length: int = 1,
        max_length: int = 1000,
        pattern: Pattern | None = None,
        allowed_values: list[str] | None = None,
        strip: bool = True,
        sanitize: bool = True,
    ) -> ValidationResult:
        """
        Valide une chaîne de caractères.

        Args:
            value: Valeur à valider
            field_name: Nom du champ (pour les messages d'erreur)
            min_length: Longueur minimale
            max_length: Longueur maximale
            pattern: Pattern regex optionnel
            allowed_values: Liste de valeurs autorisées
            strip: Si True, supprime les espaces autour
            sanitize: Si True, vérifie les patterns d'injection

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        # Type check
        if not isinstance(value, str):
            errors.append(f"{field_name}: must be a string (got {type(value).__name__})")
            return ValidationResult(is_valid=False, errors=errors)

        # Strip
        if strip:
            value = value.strip()

        # Empty
        if len(value) == 0:
            errors.append(f"{field_name}: cannot be empty")
            return ValidationResult(is_valid=False, errors=errors)

        # Length
        if len(value) < min_length:
            errors.append(f"{field_name}: too short ({len(value)} < {min_length})")
        if len(value) > max_length:
            errors.append(f"{field_name}: too long ({len(value)} > {max_length})")

        # Pattern
        if pattern and not pattern.match(value):
            errors.append(f"{field_name}: does not match required pattern")

        # Allowed values
        if allowed_values and value not in allowed_values:
            errors.append(f"{field_name}: '{value}' not in allowed values")

        # Security sanitization
        if sanitize:
            if self.SQL_INJECTION_PATTERN.search(value):
                errors.append(f"{field_name}: contains forbidden SQL keywords")
            if self.XSS_PATTERN.search(value):
                errors.append(f"{field_name}: contains forbidden HTML/JS patterns")
            if self.COMMAND_INJECTION_PATTERN.search(value):
                errors.append(f"{field_name}: contains forbidden shell characters")

        if errors:
            return ValidationResult(is_valid=False, errors=errors)

        return ValidationResult(is_valid=True, sanitized_value=value)

    def validate_number(
        self,
        value: Any,
        field_name: str = "value",
        min_value: float | None = None,
        max_value: float | None = None,
        integer_only: bool = False,
        allow_none: bool = False,
    ) -> ValidationResult:
        """
        Valide un nombre.

        Args:
            value: Valeur à valider
            field_name: Nom du champ
            min_value: Valeur minimale
            max_value: Valeur maximale
            integer_only: Si True, seulement les entiers
            allow_none: Si True, None est accepté

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        if value is None:
            if allow_none:
                return ValidationResult(is_valid=True, sanitized_value=None)
            errors.append(f"{field_name}: cannot be None")
            return ValidationResult(is_valid=False, errors=errors)

        if not isinstance(value, (int, float)):
            errors.append(f"{field_name}: must be a number (got {type(value).__name__})")
            return ValidationResult(is_valid=False, errors=errors)

        if isinstance(value, bool):
            errors.append(f"{field_name}: must be a number, not a boolean")
            return ValidationResult(is_valid=False, errors=errors)

        if integer_only and not isinstance(value, int):
            errors.append(f"{field_name}: must be an integer")

        if min_value is not None and value < min_value:
            errors.append(f"{field_name}: too small ({value} < {min_value})")
        if max_value is not None and value > max_value:
            errors.append(f"{field_name}: too large ({value} > {max_value})")

        if errors:
            return ValidationResult(is_valid=False, errors=errors)

        return ValidationResult(is_valid=True, sanitized_value=value)

    def validate_symbol(self, symbol: str) -> ValidationResult:
        """
        Valide un symbole de trading (ex: BTC/USDT).

        Vérifie :
        - Format correct
        - Longueur raisonnable
        - Pas d'injection
        """
        return self.validate_string(
            symbol,
            field_name="symbol",
            min_length=3,
            max_length=20,
            pattern=self.SYMBOL_PATTERN,
        )

    def validate_email(self, email: str) -> ValidationResult:
        """Valide une adresse email."""
        return self.validate_string(
            email,
            field_name="email",
            max_length=254,
            pattern=self.EMAIL_PATTERN,
        )

    def validate_in_enum(self, value: Any, enum_class: Any, field_name: str = "value") -> ValidationResult:
        """
        Valide qu'une valeur est un membre valide d'un enum.

        Args:
            value: Valeur (string ou enum member)
            enum_class: Classe Enum
            field_name: Nom du champ

        Returns:
            ValidationResult
        """
        errors: list[str] = []

        if isinstance(value, enum_class):
            return ValidationResult(is_valid=True, sanitized_value=value)

        if isinstance(value, str):
            try:
                member = enum_class(value)
                return ValidationResult(is_valid=True, sanitized_value=member)
            except ValueError:
                errors.append(
                    f"{field_name}: '{value}' is not a valid {enum_class.__name__}. "
                    f"Valid values: {[e.value for e in enum_class]}"
                )
        else:
            errors.append(f"{field_name}: must be a string or {enum_class.__name__}")

        return ValidationResult(is_valid=False, errors=errors)

    def validate_portfolio_pct(self, value: float) -> ValidationResult:
        """Valide un pourcentage de portefeuille (0-100)."""
        return self.validate_number(
            value,
            field_name="portfolio_pct",
            min_value=0,
            max_value=100,
        )

    def validate_positive_amount(self, value: float, field_name: str = "amount") -> ValidationResult:
        """Valide un montant positif."""
        return self.validate_number(
            value,
            field_name=field_name,
            min_value=0,
        )

    def sanitize_string(self, value: str) -> str:
        """Sanitize une chaîne (supprime les patterns dangereux)."""
        # Supprimer les caractères de contrôle (sauf tab, LF, CR)
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", value)
        # Supprimer les patterns XSS de base
        sanitized = self.XSS_PATTERN.sub("", sanitized)
        return sanitized.strip()

    def validate_config(
        self,
        config: dict[str, Any],
        schema: dict[str, dict[str, Any]],
    ) -> ValidationResult:
        """
        Valide une configuration complète contre un schéma.

        Args:
            config: Configuration à valider
            schema: Schéma de validation:
                {
                    "field_name": {
                        "type": "string|number|bool|list|dict",
                        "required": True/False,
                        "default": ...,
                        "min": ..., (number)
                        "max": ..., (number)
                        "pattern": ..., (string)
                        "allowed": [...], (any)
                    }
                }

        Returns:
            ValidationResult
        """
        errors: list[str] = []
        validated: dict[str, Any] = {}

        for field_name, rules in schema.items():
            required = rules.get("required", False)
            default = rules.get("default")
            field_type = rules.get("type", "string")

            value = config.get(field_name)

            # Champ requis manquant
            if value is None and required:
                errors.append(f"Missing required field: '{field}'")
                continue

            # Valeur par défaut
            if value is None and default is not None:
                validated[field] = default
                continue

            # Validation par type
            if value is not None:
                type_ok = True
                if field_type == "string" and not isinstance(value, str) or field_type == "number" and not isinstance(value, (int, float)) or field_type == "bool" and not isinstance(value, bool) or field_type == "list" and not isinstance(value, list) or field_type == "dict" and not isinstance(value, dict):
                    type_ok = False

                if not type_ok:
                    errors.append(f"'{field}': expected {field_type}, got {type(value).__name__}")
                    continue

                # Validation spécifique
                if field_type == "number":
                    min_val = rules.get("min")
                    max_val = rules.get("max")
                    if min_val is not None and value < min_val:
                        errors.append(f"'{field}': too small ({value} < {min_val})")
                    if max_val is not None and value > max_val:
                        errors.append(f"'{field}': too large ({value} > {max_val})")

                if field_type == "string":
                    min_len = rules.get("min_length", 0)
                    max_len = rules.get("max_length", 10000)
                    pattern_val = rules.get("pattern")
                    allowed = rules.get("allowed")

                    if allowed and value not in allowed:
                        errors.append(f"'{field}': '{value}' not allowed")
                    if len(value) < min_len:
                        errors.append(f"'{field}': too short")
                    if len(value) > max_len:
                        errors.append(f"'{field}': too long")
                    if pattern_val and not re.match(pattern_val, value):
                        errors.append(f"'{field}': invalid format")

                validated[field] = value

        if errors:
            return ValidationResult(is_valid=False, errors=errors)

        return ValidationResult(is_valid=True, sanitized_value=validated)


# Instance globale pour usage rapide
default_validator = InputValidator()


__all__ = ["InputValidator", "ValidationResult", "default_validator"]
