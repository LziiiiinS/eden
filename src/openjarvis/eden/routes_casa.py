"""Éden: rotas da casa (Home Assistant ou demonstração).

O que a pessoa faz pela tela vale direto (o toque no botão é a
confirmação). O que o Éden sugere na conversa passa pelo cartão
(acoes.py: casa.rotina, casa.aparelho). O endereço e o token do Home
Assistant nunca saem do servidor.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from openjarvis.eden import casa, tetos
from openjarvis.eden.routes_organizacao import _corpo, _rodar, _store

router = APIRouter(prefix="/v1/eden/casa", tags=["eden"])


def _teto(request: Request) -> None:
    if not tetos.usar("casa", tetos.aparelho_do_pedido(request)):
        raise HTTPException(
            status_code=429,
            detail=tetos.mensagem("casa"),
            headers={"Retry-After": "300"},
        )


@router.get("")
async def situacao(request: Request):
    """O que a tela mostra: se está ligada, os aparelhos e as rotinas."""
    store = _store(request)
    cfg = casa.configuracao()
    rotinas = await _rodar(casa.listar_rotinas, store) if cfg.ligada else []
    return {**cfg.publica(), "rotinas": rotinas}


@router.get("/estados")
async def estados(request: Request):
    return {"estados": await _rodar(casa.estados)}


@router.post("/aparelho")
async def aparelho(request: Request):
    """Um comando só, tocado na tela."""
    store = _store(request)
    dados = await _corpo(request)
    _teto(request)
    return await _rodar(casa.comando_pela_tela, store, dados)


@router.post("/rotinas")
async def criar_rotina(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"rotina": await _rodar(casa.salvar_rotina, store, dados)}


@router.patch("/rotinas/{rotina_id}")
async def editar_rotina(rotina_id: str, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"rotina": await _rodar(casa.salvar_rotina, store, dados, rotina_id)}


@router.delete("/rotinas/{rotina_id}")
async def apagar_rotina(rotina_id: str, request: Request):
    await _rodar(casa.apagar_rotina, _store(request), rotina_id)
    return {"ok": True}


@router.post("/rotinas/{rotina_id}/rodar")
async def rodar_rotina(rotina_id: str, request: Request):
    store = _store(request)
    _teto(request)
    return await _rodar(casa.rodar_pela_tela, store, rotina_id)
