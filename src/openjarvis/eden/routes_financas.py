"""Éden (Parte 5): rotas de contas e impostos.

O que a pessoa faz pela tela vale direto (a própria ação na tela é a
confirmação). O que o Éden sugere na conversa passa pelo cartão
(acoes.py: conta.criar, conta.pagar, conta.apagar).
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Request

from openjarvis.eden import financas
from openjarvis.eden.routes_organizacao import (
    _corpo,
    _espaco_filtro,
    _rodar,
    _store,
    _tz,
)

router = APIRouter(prefix="/v1/eden/contas", tags=["eden"])


@router.get("")
async def listar(
    request: Request, espaco: Optional[str] = None, estado: str = "abertas"
):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    return {"contas": await _rodar(financas.listar, store, filtro, estado)}


@router.get("/resumo")
async def resumo(request: Request, espaco: Optional[str] = None):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    tz = _tz()
    hoje = datetime.now(tz).date()
    r = await _rodar(financas.resumo, store, hoje, tz, filtro)
    return {
        "hoje": hoje.isoformat(),
        "atrasadas": r["n_atrasadas"],
        "proximas_7_dias": r["proximas_7_dias"],
        "a_pagar_no_mes": r["a_pagar_no_mes"],
        "a_receber_no_mes": r["a_receber_no_mes"],
        "atrasado_a_pagar": r["atrasado_a_pagar"],
        "pago_no_ano": r["pago_no_ano"],
        "recebido_no_ano": r["recebido_no_ano"],
    }


@router.post("")
async def criar(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    padrao = dados.get("espaco") or "pessoal"
    return {"conta": await _rodar(financas.criar, store, dados, padrao)}


@router.patch("/{conta_id}")
async def editar(conta_id: str, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"conta": await _rodar(financas.editar, store, conta_id, dados)}


@router.post("/{conta_id}/pagar")
async def pagar(conta_id: str, request: Request):
    store = _store(request)
    return await _rodar(financas.marcar_paga, store, conta_id)


@router.post("/{conta_id}/reabrir")
async def reabrir(conta_id: str, request: Request):
    store = _store(request)
    return await _rodar(financas.desfazer_pagamento, store, conta_id)


@router.delete("/{conta_id}")
async def apagar(conta_id: str, request: Request):
    store = _store(request)
    await _rodar(financas.apagar, store, conta_id)
    return {"ok": True}
