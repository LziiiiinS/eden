"""Éden: limite de gastos também na transcrição de voz (OpenAI)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from openjarvis.eden.budget import get_ledger
from openjarvis.eden.settings import get_settings

logger = logging.getLogger(__name__)

# Áudio de celular gravado pelo navegador costuma ter de 32 a 128 kbit/s.
# Sem a duração informada, o Éden supõe 32 kbit/s (4 KB por segundo): isso
# superestima a duração e mantém o limite do lado seguro.
_BYTES_PER_SECOND = 4000
_MAX_CLIENT_MS = 60 * 60 * 1000


def tracked(backend: Any) -> bool:
    return getattr(backend, "backend_id", "") == "openai"


def _model(backend: Any) -> str:
    model = getattr(backend, "model", None) or getattr(backend, "_model", None)
    return model if isinstance(model, str) and model else "gpt-transcribe"


def estimate_seconds(audio_bytes: int, client_ms: Optional[float]) -> float:
    if client_ms is not None and 0 < client_ms <= _MAX_CLIENT_MS:
        return client_ms / 1000.0
    return max(1.0, audio_bytes / _BYTES_PER_SECOND)


def parse_client_ms(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def check(backend: Any, audio_bytes: int, client_ms: Optional[float]) -> None:
    """Recusa (BudgetExceeded) se a transcrição passar do limite da OpenAI."""
    settings = get_settings()
    seconds = estimate_seconds(audio_bytes, client_ms)
    reserve = settings.transcription_cost(_model(backend), seconds)
    get_ledger().check("openai", settings, reserve)


def record(
    backend: Any,
    reported_seconds: float,
    audio_bytes: int,
    client_ms: Optional[float],
) -> None:
    settings = get_settings()
    estimated = not (reported_seconds and reported_seconds > 0)
    seconds = (
        estimate_seconds(audio_bytes, client_ms) if estimated else reported_seconds
    )
    model = _model(backend)
    try:
        get_ledger().record(
            provider="openai",
            model=model,
            kind="transcricao",
            cost_usd=settings.transcription_cost(model, seconds),
            settings=settings,
            audio_seconds=seconds,
            estimated=estimated,
        )
    except Exception:  # noqa: BLE001 — anotar o gasto nunca derruba a transcrição
        logger.exception("Éden: falha ao anotar o gasto da transcrição")
