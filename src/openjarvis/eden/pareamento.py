"""Éden: código curto para ligar um aparelho sem digitar a chave de acesso.

Por quê: no iPhone, o Éden aberto pelo ícone da tela de início guarda as
coisas num lugar separado do Safari. O QR code abre no Safari, então a chave
fica só lá, e o ícone pede a chave de novo. Digitar a chave inteira
(oj_sk_ + 43 caracteres) no celular é ruim.

Como funciona:
1. No notebook (que já tem a chave), a pessoa pede um código. Ele aparece na
   tela, por exemplo ``K7QM-2XRA``.
2. No aparelho novo, na tela da chave, ela digita o código. O servidor troca o
   código pela chave e o aparelho guarda a chave.

Proteções:
- só existe um código por vez, e pedir outro apaga o anterior;
- o código vale 5 minutos e serve uma vez só;
- 5 tentativas erradas apagam o código, e aí é preciso pedir outro;
- no máximo 20 tentativas por minuto, somando todas, com ou sem código ativo;
- o código fica só na memória do servidor, guardado como resumo sha256, nunca
  em disco nem no registro. Se o servidor reiniciar, o código some;
- são 8 caracteres de 32 símbolos (sem I, O, 0 e 1, que confundem), ou seja,
  cerca de um trilhão de combinações para no máximo 5 tentativas.

A rota que recebe o código é a única rota /v1 que funciona sem a chave (veja
``openjarvis.server.auth_middleware``). Ela entrega a mesma chave que o QR
code já entrega, por isso o risco é o mesmo: quem estiver vendo a tela do
notebook naqueles 5 minutos, e também estiver na rede do Tailscale.
"""

from __future__ import annotations

import hashlib
import secrets
import threading
import time
from collections import deque
from typing import Callable, Deque, Optional

ALFABETO = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
TAMANHO = 8
VALIDADE_S = 5 * 60
MAX_ERROS_POR_CODIGO = 5
MAX_TENTATIVAS_POR_MINUTO = 20

OK = "ok"
INVALIDO = "invalido"
MUITAS_TENTATIVAS = "muitas_tentativas"


def normalizar(texto: object) -> Optional[str]:
    """Tira espaços e traços e põe em maiúsculas. Devolve None se não for um
    código no formato certo (8 símbolos do alfabeto)."""
    if not isinstance(texto, str) or len(texto) > 32 or not texto.isascii():
        return None
    limpo = "".join(c for c in texto.upper() if c not in " -\t")
    if len(limpo) != TAMANHO or any(c not in ALFABETO for c in limpo):
        return None
    return limpo


def formatar(codigo: str) -> str:
    """``K7QM2XRA`` → ``K7QM-2XRA`` (mais fácil de ler e digitar)."""
    return f"{codigo[:4]}-{codigo[4:]}"


def _resumo(codigo: str) -> bytes:
    return hashlib.sha256(("eden-pareamento:" + codigo).encode("ascii")).digest()


class Pareamento:
    """Guarda o código ativo (só o resumo) e conta as tentativas."""

    def __init__(self, relogio: Callable[[], float] = time.monotonic) -> None:
        self._relogio = relogio
        self._lock = threading.Lock()
        self._resumo: Optional[bytes] = None
        self._expira: float = 0.0
        self._erros = 0
        self._tentativas: Deque[float] = deque()

    def criar(self) -> dict:
        """Cria um código novo (o anterior deixa de valer)."""
        codigo = "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))
        with self._lock:
            self._resumo = _resumo(codigo)
            self._expira = self._relogio() + VALIDADE_S
            self._erros = 0
        return {"codigo": formatar(codigo), "validade_s": VALIDADE_S}

    def cancelar(self) -> None:
        with self._lock:
            self._apagar()

    def ativo(self) -> bool:
        with self._lock:
            return self._resumo is not None and self._relogio() < self._expira

    def usar(self, texto: object) -> str:
        """Confere o código. Se estiver certo, apaga (uso único) e devolve OK."""
        with self._lock:
            agora = self._relogio()
            while self._tentativas and agora - self._tentativas[0] >= 60:
                self._tentativas.popleft()
            if len(self._tentativas) >= MAX_TENTATIVAS_POR_MINUTO:
                return MUITAS_TENTATIVAS
            self._tentativas.append(agora)

            if self._resumo is not None and agora >= self._expira:
                self._apagar()
            if self._resumo is None:
                return INVALIDO
            codigo = normalizar(texto)
            certo = codigo is not None and secrets.compare_digest(
                _resumo(codigo), self._resumo
            )
            if certo:
                self._apagar()
                return OK
            self._erros += 1
            if self._erros >= MAX_ERROS_POR_CODIGO:
                self._apagar()
            return INVALIDO

    def _apagar(self) -> None:
        self._resumo = None
        self._expira = 0.0
        self._erros = 0
