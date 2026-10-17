"""Éden (Parte 4): rotas do Notion (/v1/eden/notion/...).

Todas pedem a chave de acesso. Sem a NOTION_API_KEY no .env, nenhuma rota
fala com o Notion.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import notion
from openjarvis.eden.organizacao import ErroOrganizacao
from openjarvis.eden.routes_organizacao import _corpo, _store

router = APIRouter(prefix="/v1/eden/notion", tags=["eden"])

_STATUS = {
    "eden_notion_sem_chave": 409,
    "eden_notion_sem_pai": 409,
    "eden_notion_404": 404,
    "eden_notion_permissao": 403,
    "eden_notion_limite": 429,
}


async def _rodar(funcao, *args: Any):
    try:
        return await asyncio.to_thread(funcao, *args)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def _erro(exc: notion.ErroNotion) -> JSONResponse:
    return JSONResponse(
        status_code=_STATUS.get(exc.codigo, 502),
        content={"detail": str(exc), "code": exc.codigo},
    )


@router.get("/status")
async def status(request: Request):
    return {
        "configurado": notion.configurado(),
        "pai": await _rodar(notion.pagina_pai, _store(request)),
        "fonte": notion.FONTE,
    }


@router.get("/buscar")
async def buscar(request: Request, q: str = ""):
    cliente = notion.cliente_do_app(request.app)
    try:
        return {"resultados": await _rodar(cliente.buscar, q)}
    except notion.ErroNotion as exc:
        return _erro(exc)


@router.post("/pai")
async def escolher_pai(request: Request):
    from openjarvis.eden.routes_aparelhos import exigir_chave_principal

    exigir_chave_principal(request)
    dados = await _corpo(request)
    cliente = notion.cliente_do_app(request.app)
    try:
        pai = await _rodar(
            notion.escolher_pai, _store(request), cliente, dados.get("id")
        )
    except notion.ErroNotion as exc:
        return _erro(exc)
    return {"pai": pai}


@router.delete("/pai")
async def esquecer_pai(request: Request):
    from openjarvis.eden.routes_aparelhos import exigir_chave_principal

    exigir_chave_principal(request)
    await _rodar(notion.guardar_pai, _store(request), None)
    return {"pai": None}


@router.post("/importar")
async def importar(request: Request):
    dados = await _corpo(request)
    espaco = dados.get("espaco")
    if not isinstance(espaco, str) or not espaco:
        raise HTTPException(status_code=400, detail="faltou o espaço")
    store = _store(request)
    if await _rodar(store.espaco, espaco) is None:
        raise HTTPException(status_code=400, detail="espaço desconhecido")
    cliente = notion.cliente_do_app(request.app)
    try:
        doc = await _rodar(notion.importar, store, cliente, espaco, dados.get("id"))
    except notion.ErroNotion as exc:
        return _erro(exc)
    return {"documento": doc}


@router.post("/salvar")
async def salvar(request: Request):
    dados = await _corpo(request)
    cliente = notion.cliente_do_app(request.app)
    try:
        pagina = await _rodar(
            notion.salvar,
            _store(request),
            cliente,
            dados.get("titulo"),
            dados.get("markdown"),
        )
    except notion.ErroNotion as exc:
        return _erro(exc)
    return {"pagina": pagina}
