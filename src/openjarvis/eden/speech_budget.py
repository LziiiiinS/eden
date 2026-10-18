"""Éden: limite de gastos também na transcrição de voz (OpenAI)."""

from __future__ import annotations

import logging
from typing import Any, Optional

from openjarvis.eden.budget import get_ledger
from openjarvis.eden.settings import get_settings

logger = logging.getLogger(__name__)

# Áudio de celular gravado pelo navegador costuma ter de 32 a 128 kbit/s.
# Para reservar, o Éden supõe 32 kbit/s (4 KB por segundo): superestima a
# duração e mantém o limite do lado seguro. Para anotar sem a duração da
# empresa, nunca usa menos que o tamanho a 128 kbit/s (16 KB por segundo),
# mesmo que o aparelho informe uma duração menor.
_BYTES_PER_SECOND = 4000
# Para RESERVAR, supõe 8 kbit/s (1 KB por segundo), o menor comum em voz
# (Opus): áudio de qualidade baixa não passa do limite com vários aparelhos
# ao mesmo tempo (rodada final de segurança, 18/10).
_BYTES_PER_SECOND_RESERVA = 1000
_BYTES_PER_SECOND_MAX_BITRATE = 16000
_MAX_CLIENT_MS = 60 * 60 * 1000

# Tamanho máximo de um áudio (o limite da própria OpenAI é 25 MB).
MAX_AUDIO_BYTES = 25 * 1024 * 1024


def tracked(backend: Any) -> bool:
    return getattr(backend, "backend_id", "") == "openai"


def _model(backend: Any) -> str:
    model = getattr(backend, "model", None) or getattr(backend, "_model", None)
    return model if isinstance(model, str) and model else "gpt-transcribe"


def _client_seconds(client_ms: Optional[float]) -> float:
    if client_ms is not None and 0 < client_ms <= _MAX_CLIENT_MS:
        return client_ms / 1000.0
    return 0.0


def reserve_seconds(audio_bytes: int, client_ms: Optional[float]) -> float:
    """Duração para reservar: a maior entre a informada e a pelo tamanho."""
    by_size = audio_bytes / _BYTES_PER_SECOND_RESERVA
    return max(1.0, by_size, _client_seconds(client_ms))


def estimate_seconds(audio_bytes: int, client_ms: Optional[float]) -> float:
    """Duração para anotar quando a empresa não informa: a informada pelo
    aparelho só vale se não for menor do que o tamanho do arquivo indica."""
    floor = audio_bytes / _BYTES_PER_SECOND_MAX_BITRATE
    client = _client_seconds(client_ms)
    if client:
        return max(1.0, client, floor)
    return max(1.0, audio_bytes / _BYTES_PER_SECOND)


def parse_client_ms(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def check(backend: Any, audio_bytes: int, client_ms: Optional[float]) -> str:
    """Reserva o custo da transcrição; recusa (BudgetExceeded) se passar do
    limite da OpenAI. Devolve o id da reserva (liberada em record/release)."""
    settings = get_settings()
    seconds = reserve_seconds(audio_bytes, client_ms)
    reserve = settings.transcription_cost(_model(backend), seconds)
    return get_ledger().reserve("openai", settings, reserve)


def release(reservation: Optional[str]) -> None:
    get_ledger().release(reservation)


def record(
    backend: Any,
    reported_seconds: float,
    audio_bytes: int,
    client_ms: Optional[float],
    reservation: Optional[str] = None,
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
            reservation=reservation,
        )
    except Exception:  # noqa: BLE001 — anotar o gasto nunca derruba a transcrição
        logger.exception("Éden: falha ao anotar o gasto da transcrição")
        release(reservation)
