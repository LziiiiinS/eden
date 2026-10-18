"""Éden (Parte 5): rotas do e-mail (Gmail, só leitura) — /v1/eden/email/...

Todas pedem a chave de acesso. A volta do Google depois de autorizar passa
pela mesma rota da agenda (``/v1/eden/google/retorno``), que sabe pelo
"state" se a ligação é da agenda ou do e-mail.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import gmail, google
from openjarvis.eden.gmail import conta_guardada, guardar_conta
from openjarvis.eden.organizacao import ErroOrganizacao
from openjarvis.eden.routes_organizacao import _corpo, _store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden/email", tags=["eden"])
_SEM_GUARDAR = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _erro(exc: google.ErroGoogle) -> JSONResponse:
    status = {
        "eden_google_desconectado": 409,
        "eden_google_reconectar": 409,
        "eden_google_sem_config": 409,
        "eden_google_404": 404,
    }.get(exc.codigo, 502)
    return JSONResponse(
        status_code=status, content={"detail": str(exc), "code": exc.codigo}
    )


async def _rodar(funcao, *args: Any):
    try:
        return await asyncio.to_thread(funcao, *args)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


@router.get("/status")
async def status(request: Request):
    cfg = google.configuracao()
    conectado = False
    if cfg is not None:
        conectado = await asyncio.to_thread(gmail.cliente_do_app(request.app).conectado)
    return {
        "configurado": cfg is not None,
        "conectado": conectado,
        "conta": await _rodar(conta_guardada, _store(request)) if conectado else None,
    }


@router.post("/conectar")
async def conectar(request: Request):
    from openjarvis.eden.routes_aparelhos import exigir_chave_principal

    exigir_chave_principal(request)  # só o notebook liga contas
    cfg = google.configuracao()
    if cfg is None:
        raise HTTPException(
            status_code=409,
            detail="O Google ainda não foi configurado no servidor (.env).",
        )
    from openjarvis.eden.routes_google import _autorizacoes

    state, verificador = _autorizacoes(request).criar(tipo="email")
    url = google.url_de_autorizacao(
        cfg, state, verificador, escopos=[gmail.ESCOPO_GMAIL]
    )
    return JSONResponse({"url": url}, headers=_SEM_GUARDAR)


def _agenda_ligada(request: Request) -> bool:
    try:
        return google.cliente_do_app(request.app).conectado()
    except Exception:  # noqa: BLE001
        return True  # na dúvida, não revoga nada no Google


async def concluir_ligacao(request: Request, codigo: str, verificador: str) -> str:
    """Chamado pela volta do Google (routes_google.retorno) quando o pedido
    era do e-mail. Devolve a situação para a tela."""
    cliente = gmail.cliente_do_app(request.app)
    store = _store(request)
    antigo = await asyncio.to_thread(cliente.cofre.ler)
    conta_antiga = await asyncio.to_thread(gmail.conta_guardada, store)
    try:
        await asyncio.to_thread(
            cliente.trocar_codigo, codigo, verificador, gmail.ESCOPO_GMAIL
        )
    except google.ErroGoogle as exc:
        logger.warning("Éden: ligação do e-mail não concluída (%s)", exc.codigo)
        return "sem-permissao" if "permissao" in exc.codigo else "erro"
    except Exception:  # noqa: BLE001
        logger.exception("Éden: ligação do e-mail não concluída")
        return "erro"
    gmail.CACHE.limpar()
    conta = None
    try:
        conta = await asyncio.to_thread(gmail.conta, cliente)
    except Exception:  # noqa: BLE001
        logger.warning("Éden: e-mail ligado, mas não li o endereço da conta")
    try:
        await _rodar(guardar_conta, store, conta)
    except Exception:  # noqa: BLE001
        logger.warning("Éden: não guardei o endereço da conta de e-mail")
    # Trocou de conta: a autorização da conta antiga é retirada no Google.
    # Só quando a agenda não está ligada (se fosse a mesma conta, a
    # revogação derrubaria a agenda junto).
    if (
        antigo
        and conta
        and conta_antiga
        and conta.lower() != conta_antiga.lower()
        and not await asyncio.to_thread(_agenda_ligada, request)
    ):
        await asyncio.to_thread(cliente.revogar_token, antigo["refresh"])
    logger.info("Éden: e-mail (Gmail) conectado")
    return "conectado"


@router.post("/desconectar")
async def desconectar(request: Request):
    from openjarvis.eden.routes_aparelhos import exigir_chave_principal

    exigir_chave_principal(request)
    cliente = gmail.cliente_do_app(request.app)
    # Agenda ligada: só apaga aqui (se fosse a mesma conta do Google, revogar
    # derrubaria a agenda junto). A tela explica como retirar no Google.
    agenda = await asyncio.to_thread(_agenda_ligada, request)
    revogado = await asyncio.to_thread(cliente.desconectar, not agenda)
    gmail.CACHE.limpar()
    await _rodar(guardar_conta, _store(request), None)
    logger.info("Éden: e-mail (Gmail) desconectado")
    return {
        "ok": True,
        "revogado": revogado is not False,
        "motivo": "agenda_ligada" if agenda else None,
    }


@router.get("/mensagens")
async def mensagens(request: Request, busca: str = "", atualizar: bool = False):
    if google.configuracao() is None:
        return {"conectado": False, "mensagens": []}
    cliente = gmail.cliente_do_app(request.app)
    try:
        lista = await asyncio.to_thread(
            gmail.listar, cliente, busca, gmail.MAX_LISTA, atualizar
        )
    except google.ErroGoogle as exc:
        if exc.codigo in ("eden_google_desconectado", "eden_google_reconectar"):
            return {"conectado": False, "mensagens": [], "aviso": str(exc)}
        return _erro(exc)
    return JSONResponse(
        {"conectado": True, "mensagens": lista}, headers={"Cache-Control": "no-store"}
    )


@router.get("/mensagens/{mensagem_id}")
async def ler(mensagem_id: str, request: Request):
    cliente = gmail.cliente_do_app(request.app)
    try:
        m = await asyncio.to_thread(gmail.mensagem, cliente, mensagem_id)
    except google.ErroGoogle as exc:
        return _erro(exc)
    return JSONResponse({"mensagem": m}, headers={"Cache-Control": "no-store"})


@router.post("/importar")
async def importar(request: Request):
    dados = await _corpo(request)
    espaco = dados.get("espaco")
    store = _store(request)
    if not isinstance(espaco, str) or await _rodar(store.espaco, espaco) is None:
        raise HTTPException(status_code=400, detail="espaço desconhecido")
    cliente = gmail.cliente_do_app(request.app)
    try:
        doc = await _rodar(gmail.importar, store, cliente, espaco, dados.get("id"))
    except google.ErroGoogle as exc:
        return _erro(exc)
    return {"documento": doc}
