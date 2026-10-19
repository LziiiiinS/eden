"""Éden: tetos por hora (conversa e transcrição de voz).

Além do limite de gastos do mês, cada tipo de pedido que gasta com a IA tem
um teto por hora. Se uma chave vazar, ou se um texto de fora tentar fazer o
app repetir pedidos sem parar, o estrago numa hora fica pequeno.

Cada aparelho tem a sua conta (e a chave principal, a dela): um celular
roubado que gaste o teto não tranca o notebook. A contagem fica só na
memória do servidor (reiniciar zera). Dá para mudar no ``.env``:

- ``EDEN_TETO_CONVERSA_HORA`` (padrão 150 mensagens por hora);
- ``EDEN_TETO_TRANSCRICAO_HORA`` (padrão 120 áudios por hora).

``0`` desliga o teto daquele tipo (não recomendado).
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional, Tuple

PADROES: Dict[str, int] = {"conversa": 150, "transcricao": 120}
MAXIMO = 10_000

MENSAGENS: Dict[str, str] = {
    "conversa": (
        "Muitas mensagens na última hora. Espere alguns minutos e tente de novo."
    ),
    "transcricao": (
        "Muitos áudios na última hora. Espere alguns minutos ou digite a mensagem."
    ),
}


def limite_configurado(nome: str) -> int:
    """O teto do ``.env`` (ou o padrão). Valor estranho → padrão."""
    padrao = PADROES[nome]
    bruto = os.environ.get(f"EDEN_TETO_{nome.upper()}_HORA", "").strip()
    if not bruto:
        return padrao
    try:
        valor = int(bruto)
    except ValueError:
        return padrao
    if valor < 0:
        return padrao
    return min(valor, MAXIMO)


class Teto:
    """Conta os pedidos da última hora (janela que anda com o relógio)."""

    def __init__(
        self, maximo: int, relogio: Callable[[], float] = time.monotonic
    ) -> None:
        self.maximo = maximo
        self._relogio = relogio
        self._lock = threading.Lock()
        self._usos: Deque[float] = deque()

    def usar(self) -> bool:
        if self.maximo <= 0:
            return True
        agora = self._relogio()
        with self._lock:
            while self._usos and agora - self._usos[0] >= 3600:
                self._usos.popleft()
            if len(self._usos) >= self.maximo:
                return False
            self._usos.append(agora)
            return True


_tetos: Dict[Tuple[str, str], Teto] = {}
_lock = threading.Lock()


def _quem(aparelho: Optional[int]) -> str:
    return "principal" if aparelho is None else f"aparelho:{int(aparelho)}"


def teto(nome: str, aparelho: Optional[int] = None) -> Teto:
    chave = (nome, _quem(aparelho))
    with _lock:
        atual = _tetos.get(chave)
        if atual is None:
            atual = _tetos[chave] = Teto(limite_configurado(nome))
        return atual


def usar(nome: str, aparelho: Optional[int] = None) -> bool:
    """True se ainda cabe nesta hora para este aparelho (``None`` = chave
    principal) — e já conta este pedido."""
    return teto(nome, aparelho).usar()


def aparelho_do_pedido(request: Any) -> Optional[int]:
    """O aparelho que o AuthMiddleware reconheceu (None = chave principal)."""
    valor = getattr(getattr(request, "state", None), "eden_aparelho", None)
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def mensagem(nome: str) -> str:
    return MENSAGENS[nome]


def zerar() -> None:
    """Para os testes."""
    with _lock:
        _tetos.clear()
