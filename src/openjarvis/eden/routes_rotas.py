"""Éden (Parte 4): rotas das rotas e do trânsito (/v1/eden/rotas/...).

Todas pedem a chave de acesso. Sem a chave do TomTom no .env, nenhuma rota
fala com o TomTom.
"""

from __future__ import annotations

import asyncio
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import rotas
from openjarvis.eden.organizacao import ErroOrganizacao
from openjarvis.eden.routes_organizacao import _corpo, _store

router = APIRouter(prefix="/v1/eden/rotas", tags=["eden"])


async def _rodar(funcao, *args: Any):
    try:
        return await asyncio.to_thread(funcao, *args)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def _erro(exc: rotas.ErroRotas) -> JSONResponse:
    status = 409 if exc.codigo == "eden_rotas_sem_chave" else 502
    return JSONResponse(
        status_code=status, content={"detail": str(exc), "code": exc.codigo}
    )


@router.get("/status")
async def status(request: Request):
    return {
        "configurado": rotas.configurado(),
        "trajetos": await _rodar(rotas.listar_trajetos, _store(request)),
        "fonte": rotas.FONTE,
    }


@router.get("/buscar")
async def buscar(request: Request, q: str = ""):
    cliente = rotas.cliente_do_app(request.app)
    try:
        return {"resultados": await _rodar(cliente.buscar, q)}
    except rotas.ErroRotas as exc:
        return _erro(exc)


@router.post("/trajetos")
async def criar(request: Request):
    dados = await _corpo(request)
    return {"trajeto": await _rodar(rotas.criar_trajeto, _store(request), dados)}


@router.delete("/trajetos/{trajeto_id}")
async def apagar(trajeto_id: int, request: Request):
    if not await _rodar(rotas.apagar_trajeto, _store(request), trajeto_id):
        raise HTTPException(status_code=404, detail="Trajeto não encontrado")
    return {"ok": True}


@router.get("/tempos")
async def tempos(request: Request, atualizar: bool = False):
    """Tempo agora de cada trajeto (guardado por 5 min; atualizar força)."""
    if not rotas.configurado():
        return {"configurado": False, "tempos": []}
    store = _store(request)
    cliente = rotas.cliente_do_app(request.app)
    saida = []
    for t in await _rodar(rotas.listar_trajetos, store):
        try:
            r = await _rodar(cliente.tempo, t, atualizar)
            saida.append({"trajeto": t, **r})
        except rotas.ErroRotas as exc:
            saida.append({"trajeto": t, "erro": str(exc), "code": exc.codigo})
    return {"configurado": True, "tempos": saida}


@router.get("/caminhos")
async def caminhos(
    request: Request,
    trajeto: Optional[int] = None,
    origem: str = "",
    destino: str = "",
    atualizar: bool = False,
):
    """Até 3 caminhos (com as vias principais) de um trajeto salvo ou entre
    dois pontos ("lat,lon"). A localização mandada aqui não é guardada."""
    cliente = rotas.cliente_do_app(request.app)
    if trajeto is not None:
        t = await _rodar(rotas.trajeto, _store(request), trajeto)
        if t is None:
            raise HTTPException(status_code=404, detail="Trajeto não encontrado")
        de, para = t["origem"], t["destino"]
    else:
        de, para = rotas.ler_local(origem), rotas.ler_local(destino)
        if de is None or para is None:
            raise HTTPException(
                status_code=400, detail="origem e destino precisam ser 'lat,lon'"
            )
    try:
        r = await _rodar(cliente.caminhos, de, para, atualizar)
    except rotas.ErroRotas as exc:
        return _erro(exc)
    return {"configurado": True, **r}
