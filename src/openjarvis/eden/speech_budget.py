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
_BYTES_PER_SECOND_RESERVA = 125
# (revisão do Codex, 18/10: áudio AAC comprimido de propósito, a ~1,5 kbit/s,
# passava da reserva de 8 kbit/s. Agora a reserva supõe 1 kbit/s e, quando dá,
# lê a duração no próprio arquivo — MP4/M4A do iPhone e WAV.)


def duracao_do_arquivo(dados: bytes) -> Optional[float]:
    """Duração (segundos) escrita no próprio arquivo de áudio, quando dá para
    ler sem decodificar: WAV (cabeçalho) e MP4/M4A (caixa mvhd). None se não
    souber."""
    try:
        if len(dados) >= 44 and dados[:4] == b"RIFF" and dados[8:12] == b"WAVE":
            taxa = int.from_bytes(dados[28:32], "little")  # bytes por segundo
            i = 12
            while i + 8 <= len(dados):
                nome = dados[i : i + 4]
                tamanho = int.from_bytes(dados[i + 4 : i + 8], "little")
                if nome == b"data" and taxa > 0:
                    return min(tamanho, len(dados)) / taxa
                i += 8 + tamanho + (tamanho & 1)
            return None
        pos = dados.find(b"mvhd", 0, 1_000_000)
        if pos >= 4:
            versao = dados[pos + 4]
            if versao == 1:
                escala = int.from_bytes(dados[pos + 24 : pos + 28], "big")
                duracao = int.from_bytes(dados[pos + 28 : pos + 36], "big")
            else:
                escala = int.from_bytes(dados[pos + 16 : pos + 20], "big")
                duracao = int.from_bytes(dados[pos + 20 : pos + 24], "big")
            if escala > 0 and duracao > 0:
                return duracao / escala
    except (IndexError, ValueError):
        return None
    return None


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


def reserve_seconds(
    audio_bytes: int, client_ms: Optional[float], arquivo_s: Optional[float] = None
) -> float:
    """Duração para reservar: a maior entre a informada, a do arquivo e a pelo
    tamanho (a 1 kbit/s)."""
    by_size = audio_bytes / _BYTES_PER_SECOND_RESERVA
    return max(1.0, by_size, _client_seconds(client_ms), arquivo_s or 0.0)


def estimate_seconds(
    audio_bytes: int, client_ms: Optional[float], arquivo_s: Optional[float] = None
) -> float:
    """Duração para anotar quando a empresa não informa: a maior entre a do
    arquivo, a informada pelo aparelho e a que o tamanho indica."""
    floor = audio_bytes / _BYTES_PER_SECOND_MAX_BITRATE
    client = _client_seconds(client_ms)
    if client:
        return max(1.0, client, floor, arquivo_s or 0.0)
    return max(1.0, audio_bytes / _BYTES_PER_SECOND, arquivo_s or 0.0)


def parse_client_ms(raw: Any) -> Optional[float]:
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


def check(
    backend: Any,
    audio_bytes: int,
    client_ms: Optional[float],
    arquivo_s: Optional[float] = None,
) -> str:
    """Reserva o custo da transcrição; recusa (BudgetExceeded) se passar do
    limite da OpenAI. Devolve o id da reserva (liberada em record/release)."""
    settings = get_settings()
    seconds = reserve_seconds(audio_bytes, client_ms, arquivo_s)
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
    arquivo_s: Optional[float] = None,
) -> None:
    settings = get_settings()
    estimated = not (reported_seconds and reported_seconds > 0)
    seconds = (
        estimate_seconds(audio_bytes, client_ms, arquivo_s)
        if estimated
        else reported_seconds
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
