"""Éden: de qual aparelho veio o pedido (para o registro de ações).

O AuthMiddleware anota, para cada pedido com chave, se foi a chave principal
(o notebook) ou a chave de um aparelho. Quando algo é gravado no registro
durante esse pedido, a linha diz de onde veio — por exemplo
``pessoa (iPhone #2)``. Se um celular for roubado, dá para ver o que ele fez.

Tarefas de fundo (avisos, limpeza) não têm pedido: a linha fica como antes.
"""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Optional

PRINCIPAL = 0  # chave principal (o notebook)

_APARELHO: ContextVar[Optional[int]] = ContextVar(
    "eden_aparelho_do_pedido", default=None
)


def definir(aparelho_id: Optional[int]) -> Token:
    """``None`` → chave principal; senão, o id do aparelho."""
    return _APARELHO.set(PRINCIPAL if aparelho_id is None else int(aparelho_id))


def soltar(token: Token) -> None:
    _APARELHO.reset(token)


def rotulo() -> Optional[str]:
    atual = _APARELHO.get()
    if atual is None:
        return None
    if atual == PRINCIPAL:
        return "chave principal"
    from openjarvis.eden.aparelhos import nome_do_aparelho

    nome = nome_do_aparelho(atual) or "aparelho"
    return f"{nome[:40]} #{atual}"


def com_aparelho(quem: str) -> str:
    r = rotulo()
    return f"{quem} ({r})" if r else quem
