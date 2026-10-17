"""Éden (Parte 4): rotas do clima, vento e ondas (/v1/eden/clima/...).

Todas pedem a chave de acesso. Enquanto o clima estiver desligado, nenhuma
rota fala com o Open-Meteo.
"""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import clima
from openjarvis.eden.organizacao import ErroOrganizacao
from openjarvis.eden.routes_organizacao import _corpo, _store

router = APIRouter(prefix="/v1/eden/clima", tags=["eden"])


async def _rodar(funcao, *args: Any):
    try:
        return await asyncio.to_thread(funcao, *args)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def _erro_clima(exc: clima.ErroClima) -> JSONResponse:
    return JSONResponse(
        status_code=502, content={"detail": str(exc), "code": exc.codigo}
    )


async def _precisa_ligado(request: Request) -> None:
    if not await _rodar(clima.ligado, _store(request)):
        raise HTTPException(
            status_code=409, detail="O clima está desligado (ligue na página Clima)."
        )


@router.get("/status")
async def status(request: Request):
    store = _store(request)
    return {
        "ligado": await _rodar(clima.ligado, store),
        "lugares": await _rodar(clima.listar_lugares, store),
        "fonte": clima.FONTE,
    }


@router.post("/ligar")
async def ligar(request: Request):
    dados = await _corpo(request)
    valor = dados.get("ligado")
    if not isinstance(valor, bool):
        raise HTTPException(status_code=400, detail="'ligado' precisa ser true/false")
    return {"ligado": await _rodar(clima.definir_ligado, _store(request), valor)}


@router.get("/buscar")
async def buscar(request: Request, nome: str = ""):
    await _precisa_ligado(request)
    cliente = clima.cliente_do_app(request.app)
    try:
        return {"resultados": await _rodar(cliente.buscar, nome)}
    except clima.ErroClima as exc:
        return _erro_clima(exc)


@router.post("/lugares")
async def criar_lugar(request: Request):
    await _precisa_ligado(request)
    dados = await _corpo(request)
    return {"lugar": await _rodar(clima.criar_lugar, _store(request), dados)}


@router.delete("/lugares/{lugar_id}")
async def apagar_lugar(lugar_id: int, request: Request):
    if not await _rodar(clima.apagar_lugar, _store(request), lugar_id):
        raise HTTPException(status_code=404, detail="Lugar não encontrado")
    return {"ok": True}


@router.post("/lugares/{lugar_id}/principal")
async def principal(lugar_id: int, request: Request):
    return {"lugar": await _rodar(clima.tornar_principal, _store(request), lugar_id)}


@router.get("/previsao/{lugar_id}")
async def previsao(lugar_id: int, request: Request, atualizar: bool = False):
    await _precisa_ligado(request)
    store = _store(request)
    item = await _rodar(clima.lugar, store, lugar_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Lugar não encontrado")
    cliente = clima.cliente_do_app(request.app)
    try:
        dados = await _rodar(cliente.previsao, item, atualizar)
    except clima.ErroClima as exc:
        return _erro_clima(exc)
    return {"lugar": item, **dados}
