"""
Bot Telegram pour les alertes CryptoAI.

Envoie des notifications pour :
- Opportunités de trading (score > 80)
- Alertes de drawdown
- Rapport journalier
- Alertes API (erreurs, maintenance)

Utilise l'API Telegram Bot via HTTP (sans dépendance lourde).
Si le token n'est pas configuré, les appels sont silencieusement ignorés.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx

from src.utils.logging import get_logger

logger = get_logger(__name__)


class TelegramAlerter:
    """Envoie des alertes formatées via l'API Telegram Bot."""

    def __init__(self, bot_token: str = "", chat_id: str = "") -> None:
        self._token = bot_token
        self._chat_id = chat_id
        self._enabled = bool(bot_token and chat_id)
        self._client: httpx.AsyncClient | None = None

        if self._enabled:
            logger.info("TelegramAlerter configured (chat=%s)", chat_id)
        else:
            logger.info("TelegramAlerter disabled (no token/chat_id)")

    async def _ensure_client(self) -> None:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(10.0))

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def _send(self, text: str, parse_mode: str = "Markdown") -> bool:
        """Envoie un message Telegram. Retourne True si envoyé."""
        if not self._enabled:
            return False

        await self._ensure_client()
        assert self._client is not None

        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            payload = {
                "chat_id": self._chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            resp = await self._client.post(url, json=payload)
            if resp.status_code != 200:
                logger.warning("Telegram send failed: %s %s", resp.status_code, resp.text)
                return False
            return True
        except Exception as exc:
            logger.debug("Telegram error: %s", exc)
            return False

    # ── Alertes spécifiques ────────────────────────────────────

    async def send_opportunity(
        self,
        symbol: str,
        score: float,
        action: str,
        direction: str,
        explanation: str = "",
    ) -> bool:
        """Alerte quand une opportunité de trading est détectée (score > 80)."""
        emoji = "🟢" if direction == "bullish" else "🔴" if direction == "bearish" else "⚪"
        action_label = action.replace("_", " ").upper()

        text = (
            f"{emoji} *Signal Fort — {symbol}*\n\n"
            f"• Action: `{action_label}`\n"
            f"• Score IA: {score:.0f}/100\n"
            f"• Direction: {direction}\n"
        )
        if explanation:
            text += f"\n_{explanation[:200]}_"

        return await self._send(text)

    async def send_drawdown_alert(
        self,
        drawdown_pct: float,
        status: str,
        current_capital: float,
        initial_capital: float,
    ) -> bool:
        """Alerte quand le drawdown dépasse un seuil critique."""
        if status == "critical":
            emoji = "🚨"
            severity = "CRITIQUE"
        elif status == "warning":
            emoji = "⚠️"
            severity = "AVERTISSEMENT"
        else:
            return True  # pas d'alerte pour safe

        text = (
            f"{emoji} *Alerte Drawdown — {severity}*\n\n"
            f"• Drawdown: {drawdown_pct:.1f}%\n"
            f"• Capital actuel: ${current_capital:,.2f}\n"
            f"• Capital initial: ${initial_capital:,.2f}\n"
            f"• Perte: ${initial_capital - current_capital:,.2f}\n\n"
            f"*Circuit breaker {'actif' if status == 'critical' else 'surveillé'}*"
        )

        return await self._send(text)

    async def send_daily_report(self, summary_data: dict[str, Any]) -> bool:
        """Rapport journalier formaté."""
        pnl = summary_data.get("total_pnl", 0)
        pnl_pct = summary_data.get("total_pnl_pct", 0)
        win_rate = summary_data.get("win_rate", 0)
        trades = summary_data.get("total_trades", 0)
        sharpe = summary_data.get("sharpe_ratio", 0)

        emoji = "📈" if pnl >= 0 else "📉"

        text = (
            f"{emoji} *Rapport Journalier CryptoAI*\n"
            f"_{datetime.now(UTC).strftime('%Y-%m-%d')}_\n\n"
            f"• PnL: {'+' if pnl >= 0 else ''}${pnl:,.2f} ({pnl_pct:+.1f}%)\n"
            f"• Win Rate: {win_rate:.1f}%\n"
            f"• Trades: {trades}\n"
            f"• Sharpe: {sharpe:.2f}\n"
            f"• Capital: ${summary_data.get('current_capital', 0):,.2f}"
        )

        return await self._send(text)

    async def send_api_alert(self, message: str, level: str = "error") -> bool:
        """Alerte générique (erreurs API, maintenance)."""
        icons = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}
        emoji = icons.get(level, "ℹ️")

        text = f"{emoji} *CryptoAI {'Erreur' if level == 'error' else 'Alerte'}*\n\n{message}"

        return await self._send(text)


def create_telegram_alerter() -> TelegramAlerter:
    """Factory: crée un TelegramAlerter depuis les variables d'environnement."""
    import os

    token = os.getenv("CRYPTOAI_TELEGRAM_TOKEN", "")
    chat_id = os.getenv("CRYPTOAI_TELEGRAM_CHAT_ID", "")
    return TelegramAlerter(bot_token=token, chat_id=chat_id)
