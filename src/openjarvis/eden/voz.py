"""Éden (Parte 4): respostas em voz (texto → fala) com a voz da OpenAI.

- Usa a mesma chave da OpenAI do .env (sem conta nova). Modelo
  ``gpt-4o-mini-tts`` (cerca de US$ 0,015 por minuto de fala; o Éden reserva
  e anota US$ 0,02 por 1.000 caracteres, por cima).
- Todo pedido passa pelo limite de gastos da OpenAI e por um teto por hora.
- O texto vai só para a OpenAI, para virar áudio; o Éden não guarda o texto
  nem o áudio, e não registra o texto nos registros do servidor.
- O app divide a resposta em pedaços (frases) e toca um atrás do outro.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Tuple

from openjarvis.eden.budget import SpendingLedger, get_ledger
from openjarvis.eden.settings import EdenSettings, get_settings

logger = logging.getLogger(__name__)

PROVEDOR = "openai"
URL = "https://api.openai.com/v1/audio/speech"
MODELO = "gpt-4o-mini-tts"
PRECO_POR_1000_CARACTERES = 0.02  # por cima do preço da OpenAI (~0,015/min)
MAX_CARACTERES = 1500  # por pedido (o app manda pedaços menores)
MAX_CARACTERES_POR_HORA = 40_000  # ~US$ 0,80 por hora, no máximo
MAX_PEDIDOS_POR_HORA = 400
MAX_AUDIO = 8 * 1024 * 1024
TEMPO_LIMITE_S = 60.0

VOZES = ("marin", "cedar", "coral", "ash", "nova", "onyx", "sage", "shimmer")
VOZ_PADRAO = "marin"
INSTRUCOES = (
    "Fale em português do Brasil, com sotaque brasileiro, de forma natural, "
    "clara e calorosa, num ritmo tranquilo, como um assistente pessoal."
)


class ErroVoz(Exception):
    def __init__(
        self, mensagem: str, status: int = 400, codigo: str = "eden_voz"
    ) -> None:
        super().__init__(mensagem)
        self.status = status
        self.codigo = codigo


# ── teto por hora ────────────────────────────────────────────────────────


class TetoPorHora:
    def __init__(
        self,
        max_caracteres: int = MAX_CARACTERES_POR_HORA,
        max_pedidos: int = MAX_PEDIDOS_POR_HORA,
        relogio: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_caracteres = max_caracteres
        self.max_pedidos = max_pedidos
        self._relogio = relogio
        self._lock = threading.Lock()
        self._usos: Deque[Tuple[float, int]] = deque()

    def usar(self, caracteres: int) -> bool:
        agora = self._relogio()
        with self._lock:
            while self._usos and agora - self._usos[0][0] > 3600:
                self._usos.popleft()
            usados = sum(c for _, c in self._usos)
            if (
                len(self._usos) >= self.max_pedidos
                or usados + caracteres > self.max_caracteres
            ):
                return False
            self._usos.append((agora, caracteres))
            return True


TETO = TetoPorHora()


# ── pedido ───────────────────────────────────────────────────────────────


def limpar_texto(valor: Any) -> str:
    if not isinstance(valor, str):
        raise ErroVoz("faltou o texto")
    texto = valor.encode("utf-8", "replace").decode("utf-8")
    texto = "".join(c for c in texto if c in "\n\t" or c >= " ")
    texto = " ".join(texto.split())
    if not texto:
        raise ErroVoz("faltou o texto")
    if len(texto) > MAX_CARACTERES:
        raise ErroVoz(f"texto grande demais (até {MAX_CARACTERES} caracteres)", 413)
    return texto


def escolher_voz(valor: Any) -> str:
    return valor if isinstance(valor, str) and valor in VOZES else VOZ_PADRAO


def custo_usd(caracteres: int) -> float:
    return max(1, caracteres) * PRECO_POR_1000_CARACTERES / 1000


def tem_chave() -> bool:
    try:
        return bool(_chave())
    except Exception:  # noqa: BLE001
        return False


def _chave() -> str:
    from openjarvis.eden.providers import _api_key

    return _api_key("OPENAI_API_KEY")


def _cliente_padrao() -> Any:
    import httpx

    return httpx.AsyncClient(timeout=httpx.Timeout(TEMPO_LIMITE_S, connect=15.0))


async def falar(
    texto: str,
    voz: str,
    *,
    settings: Optional[EdenSettings] = None,
    ledger: Optional[SpendingLedger] = None,
    client_factory: Optional[Callable[[], Any]] = None,
    api_key: Optional[str] = None,
) -> bytes:
    """Texto (já limpo) → áudio MP3. Reserva, chama a OpenAI e anota o gasto."""
    from openjarvis.eden.providers import ProviderError, explain_http_error

    settings = settings or get_settings()
    ledger = ledger or get_ledger()
    client_factory = client_factory or _cliente_padrao
    chave = api_key if api_key is not None else _chave()
    if not chave:
        raise ErroVoz(
            "A voz usa a OpenAI: falta a chave da OpenAI no servidor.",
            409,
            "eden_voz_sem_chave",
        )
    custo = custo_usd(len(texto))
    reserva = ledger.reserve(PROVEDOR, settings, custo)
    corpo: Dict[str, Any] = {
        "model": MODELO,
        "input": texto,
        "voice": voz,
        "instructions": INSTRUCOES,
        "response_format": "mp3",
    }
    cabecalhos = {
        "Authorization": f"Bearer {chave}",
        "Content-Type": "application/json",
    }
    aceito = False
    try:
        async with client_factory() as cliente:
            async with cliente.stream(
                "POST", URL, json=corpo, headers=cabecalhos
            ) as resposta:
                if resposta.status_code >= 400:
                    raise ProviderError(
                        explain_http_error(
                            PROVEDOR, resposta.status_code, await resposta.aread()
                        )
                    )
                aceito = True
                pedacos = []
                tamanho = 0
                async for pedaco in resposta.aiter_bytes():
                    tamanho += len(pedaco)
                    if tamanho > MAX_AUDIO:
                        raise ErroVoz("áudio grande demais", 502)
                    pedacos.append(pedaco)
        audio = b"".join(pedacos)
        if not audio:
            raise ErroVoz("a OpenAI devolveu um áudio vazio", 502)
        return audio
    finally:
        if aceito:
            try:
                ledger.record(
                    provider=PROVEDOR,
                    model=MODELO,
                    kind="voz",
                    cost_usd=custo,
                    settings=settings,
                    input_tokens=len(texto),
                    estimated=True,
                    reservation=reserva,
                )
            except Exception:  # noqa: BLE001
                logger.exception("Éden: falha ao anotar o gasto da voz")
                ledger.release(reserva)
        else:
            ledger.release(reserva)


__all__ = [
    "ErroVoz",
    "TETO",
    "TetoPorHora",
    "VOZES",
    "VOZ_PADRAO",
    "MODELO",
    "limpar_texto",
    "escolher_voz",
    "custo_usd",
    "tem_chave",
    "falar",
]
