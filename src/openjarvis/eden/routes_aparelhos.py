"""Éden (Parte 5): rotas dos aparelhos (/v1/eden/aparelhos).

- Listar: qualquer aparelho com acesso (a lista não mostra chaves).
- Criar uma chave nova: só com a chave principal (o notebook). Assim, quem
  pegar um celular não consegue criar outras chaves antes de ser desligado.
- Desligar: com a chave principal, qualquer aparelho; com a chave de um
  aparelho, só ele mesmo.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import aparelhos
from openjarvis.eden.routes_organizacao import _corpo

router = APIRouter(prefix="/v1/eden/aparelhos", tags=["eden"])

_SEM_GUARDAR = {"Cache-Control": "no-store"}


def aparelho_do_pedido(request: Request) -> Optional[int]:
    """Id do aparelho que fez o pedido; None = chave principal."""
    try:
        valor = getattr(request.state, "eden_aparelho", None)
    except Exception:  # noqa: BLE001
        return None
    return valor if isinstance(valor, int) and not isinstance(valor, bool) else None


def exigir_chave_principal(request: Request) -> None:
    if aparelho_do_pedido(request) is not None:
        raise HTTPException(
            status_code=403,
            detail="Só o notebook (chave principal) pode fazer isso.",
        )


async def _rodar(funcao, *args: Any):
    return await asyncio.to_thread(funcao, *args)


@router.get("")
async def listar(request: Request):
    lista = await _rodar(aparelhos.registro().listar)
    return JSONResponse(
        {"aparelhos": lista, "eu": aparelho_do_pedido(request)},
        headers=_SEM_GUARDAR,
    )


@router.post("")
async def criar(request: Request):
    exigir_chave_principal(request)
    dados = await _corpo(request)
    nome = dados.get("nome") or aparelhos.nome_pelo_navegador(
        request.headers.get("user-agent")
    )
    # Chave para o QR code: vale só 10 min se ninguém usar (foto esquecida).
    sem_uso = aparelhos.QR_SEM_USO_MS if dados.get("qr") is True else None
    try:
        if sem_uso is None:
            novo = await _rodar(aparelhos.registro().criar, nome)
        else:
            novo = await _rodar(aparelhos.registro().criar, nome, sem_uso)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None
    return JSONResponse(novo, headers=_SEM_GUARDAR)


@router.delete("/{aparelho_id}")
async def desligar(aparelho_id: int, request: Request):
    eu = aparelho_do_pedido(request)
    if eu is not None and eu != aparelho_id:
        raise HTTPException(
            status_code=403,
            detail="Um aparelho só pode desligar a si mesmo; use o notebook.",
        )
    if not 0 < aparelho_id < 2**31 or not await _rodar(
        aparelhos.registro().desligar, aparelho_id
    ):
        raise HTTPException(status_code=404, detail="Aparelho não encontrado")
    # Avisos (push) não sabem de qual aparelho são: apaga todos. Os aparelhos
    # que continuam ligados se inscrevem de novo sozinhos ao abrir o Éden; o
    # desligado não consegue (a chave dele não vale mais).
    from openjarvis.eden import push
    from openjarvis.eden.routes_organizacao import _store

    await _rodar(push.remover_todas_inscricoes, _store(request))
    return {"ok": True}
