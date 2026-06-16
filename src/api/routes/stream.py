"""Endpoints SSE (Server-Sent Events) pour les mises à jour temps réel."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from src.utils.singleton import (
    get_all_live_analyses,
    get_all_live_market_data,
    get_paper_exchange,
)

router = APIRouter(prefix="/api/v1/stream", tags=["stream"])


async def _sse_event(event: str, data: Any) -> str:
    """Formate un événement SSE."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def _event_generator(request: Request):
    """Générateur SSE — envoie les mises à jour toutes les 5 secondes."""
    last_market = ""
    last_analyses = ""
    last_portfolio = ""

    while True:
        # Vérifier si le client est déconnecté
        if await request.is_disconnected():
            break

        payloads: list[str] = []

        # ── Market data update ──
        all_md = get_all_live_market_data()
        current_market = json.dumps(all_md, default=str)
        if current_market != last_market:
            last_market = current_market
            symbols = [
                {
                    "symbol": sym,
                    "ticker": md.get("ticker"),
                    "last_ohlcv": md.get("last_ohlcv"),
                    "updated_at": md.get("_updated_at"),
                }
                for sym, md in all_md.items()
            ]
            payloads.append(await _sse_event("market", {
                "symbols": symbols,
                "count": len(symbols),
                "timestamp": datetime.now(UTC).isoformat(),
            }))

        # ── Analyses update ──
        all_analyses = get_all_live_analyses()
        current_analyses = json.dumps(all_analyses, default=str)
        if current_analyses != last_analyses:
            last_analyses = current_analyses
            decisions = [
                {
                    "symbol": sym,
                    "action": a.get("action", "hold"),
                    "score": a.get("score", 50),
                    "direction": a.get("direction", "neutral"),
                    "confidence": a.get("confidence", 0),
                    "timestamp": a.get("timestamp", ""),
                    "explanation": a.get("explanation", ""),
                }
                for sym, a in all_analyses.items()
            ]
            if decisions:
                payloads.append(await _sse_event("analyses", {
                    "decisions": decisions,
                    "count": len(decisions),
                }))

        # ── Portfolio update ──
        paper = get_paper_exchange()
        if paper is not None:
            try:
                summary = paper.get_summary()
                current_portfolio = json.dumps(summary, default=str)
                if current_portfolio != last_portfolio:
                    last_portfolio = current_portfolio
                    payloads.append(await _sse_event("portfolio", {
                        "total_usd": round(summary["current_capital"], 2),
                        "pnl_24h_usd": round(summary["total_pnl"], 2),
                        "pnl_24h_pct": summary["total_pnl_pct"],
                        "open_positions": summary["open_positions"],
                        "win_rate": summary["win_rate"],
                        "total_trades": summary["total_trades"],
                    }))
            except Exception:
                pass

        if payloads:
            yield "".join(payloads)
        else:
            yield ": heartbeat\n\n"

        await asyncio.sleep(5)


@router.get("/dashboard")
async def stream_dashboard(request: Request):
    """SSE endpoint : mises à jour temps réel du dashboard."""
    return StreamingResponse(
        _event_generator(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
