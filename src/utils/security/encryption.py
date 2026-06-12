"""
Encryption Engine — Chiffrement des données sensibles.

Utilise AES-256-GCM pour le chiffrement symétrique :
- API keys, secrets, tokens au repos
- Données sensibles en base de données
- Rotation de clés

Standards :
- Chiffrement : AES-256-GCM (authenticated encryption)
- Dérivation de clé : PBKDF2-HMAC-SHA256
- Sel : 16 bytes aléatoire par chiffrement
- IV : 12 bytes aléatoire par chiffrement
- Tag GCM : 16 bytes (inclus dans le ciphertext)
"""

from __future__ import annotations

import base64
import os

from src.utils.logging import get_logger

logger = get_logger(__name__)


class EncryptionEngine:
    """
    Moteur de chiffrement AES-256-GCM.

    Utilisation :
    ```python
    engine = EncryptionEngine(master_key=os.environ["MASTER_KEY"])

    # Chiffrer
    encrypted = engine.encrypt("my_api_key_secret")
    # -> "base64_encoded_ciphertext"

    # Déchiffrer
    decrypted = engine.decrypt(encrypted)
    # -> "my_api_key_secret"
    ```
    """

    ALGORITHM = "AES-256-GCM"
    KEY_LENGTH = 32  # 256 bits
    IV_LENGTH = 12   # 96 bits pour GCM
    SALT_LENGTH = 16
    TAG_LENGTH = 16
    PBKDF2_ITERATIONS = 600_000  # OWASP 2023 recommandation

    def __init__(self, master_key: str | None = None) -> None:
        """
        Initialise le moteur de chiffrement.

        Args:
            master_key: Clé maître en hex (64 chars hex = 32 bytes).
                        Si None, lit depuis l'environnement ENCRYPTION_KEY.
        """
        self._master_key = master_key
        if not self._master_key:
            self._master_key = os.environ.get("ENCRYPTION_KEY", "")

        if not self._master_key:
            logger.warning(
                "No encryption key provided. "
                "Set ENCRYPTION_KEY environment variable or pass master_key."
            )

    def encrypt(self, plaintext: str) -> str:
        """
        Chiffre un texte clair avec AES-256-GCM.

        Format de sortie (base64) :
        salt + iv + ciphertext + tag

        Args:
            plaintext: Texte à chiffrer

        Returns:
            Ciphertext encodé en base64
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if not plaintext:
            return ""

        # Générer sel et IV
        salt = os.urandom(self.SALT_LENGTH)
        iv = os.urandom(self.IV_LENGTH)

        # Dériver la clé
        key = self._derive_key(salt)

        # Chiffrer
        aesgcm = AESGCM(key)
        ciphertext = aesgcm.encrypt(
            iv, plaintext.encode("utf-8"), None  # associated_data=None
        )
        # AESGCM.encrypt retourne ciphertext + tag (concatenated)

        # Assembler : salt + iv + (ciphertext + tag)
        result = salt + iv + ciphertext

        return base64.b64encode(result).decode("ascii")

    def decrypt(self, ciphertext_b64: str) -> str:
        """
        Déchiffre un ciphertext AES-256-GCM.

        Args:
            ciphertext_b64: Ciphertext en base64

        Returns:
            Texte clair original
        """
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM

        if not ciphertext_b64:
            return ""

        try:
            data = base64.b64decode(ciphertext_b64)

            salt = data[:self.SALT_LENGTH]
            iv = data[self.SALT_LENGTH:self.SALT_LENGTH + self.IV_LENGTH]
            ciphertext = data[self.SALT_LENGTH + self.IV_LENGTH:]

            key = self._derive_key(salt)
            aesgcm = AESGCM(key)
            plaintext = aesgcm.decrypt(iv, ciphertext, None)

            return plaintext.decode("utf-8")

        except Exception as e:
            logger.error("Decryption failed: %s", e)
            raise ValueError("Decryption failed — key may be incorrect or data corrupted") from e

    def _derive_key(self, salt: bytes) -> bytes:
        """Dérive la clé de chiffrement à partir du master key."""
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

        if not self._master_key:
            raise RuntimeError("Encryption key not configured")

        key_bytes = bytes.fromhex(self._master_key)

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=self.KEY_LENGTH,
            salt=salt,
            iterations=self.PBKDF2_ITERATIONS,
        )
        return kdf.derive(key_bytes)

    def generate_key(self) -> str:
        """Génère une nouvelle clé maître aléatoire (256 bits en hex)."""
        return os.urandom(32).hex()

    @staticmethod
    def encrypt_api_key(api_key: str, master_key: str) -> str:
        """
        Chiffre une API key (méthode utilitaire statique).

        Args:
            api_key: Clé API à chiffrer
            master_key: Clé maître en hex

        Returns:
            API key chiffrée en base64
        """
        engine = EncryptionEngine(master_key=master_key)
        return engine.encrypt(api_key)

    @staticmethod
    def decrypt_api_key(encrypted_key: str, master_key: str) -> str:
        """
        Déchiffre une API key (méthode utilitaire statique).

        Args:
            encrypted_key: Clé API chiffrée en base64
            master_key: Clé maître en hex

        Returns:
            API key en clair
        """
        engine = EncryptionEngine(master_key=master_key)
        return engine.decrypt(encrypted_key)


__all__ = ["EncryptionEngine"]
