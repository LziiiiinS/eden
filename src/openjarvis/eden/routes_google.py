"""Éden: rotas da Google Agenda (/v1/eden/google/...).

Todas pedem a chave de acesso, menos ``GET /v1/eden/google/retorno``: é para
lá que o Google manda o navegador de volta depois da autorização, e o
navegador não leva a chave nesse caminho. Ela só aceita um "state" criado
há menos de 10 minutos por quem tem a chave (uso único, com PKCE).
"""

from __future__ import annotations

import asyncio
import logging
import threading

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from openjarvis.eden import google
from openjarvis.eden.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden/google", tags=["eden"])

_lock = threading.Lock()
_SEM_GUARDAR = {"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}


def _autorizacoes(request: Request) -> google.Autorizacoes:
    atual = getattr(request.app.state, "eden_google_autorizacoes", None)
    if atual is None:
        with _lock:
            atual = getattr(request.app.state, "eden_google_autorizacoes", None)
            if atual is None:
                atual = google.Autorizacoes()
                request.app.state.eden_google_autorizacoes = atual
    return atual


def _voltar(situacao: str) -> RedirectResponse:
    # Sempre um caminho fixo do próprio Éden (nunca um endereço vindo de fora).
    return RedirectResponse(
        f"/settings?google={situacao}", status_code=303, headers=_SEM_GUARDAR
    )


@router.get("/status")
async def status(request: Request):
    from openjarvis.eden.endereco import endereco_celular

    cfg = google.configuracao()
    endereco = endereco_celular()
    conectado = False
    if cfg is not None:
        conectado = await asyncio.to_thread(
            google.cliente_do_app(request.app).conectado
        )
    retrato = google.CACHE.retrato()
    return {
        "configurado": cfg is not None,
        "conectado": conectado,
        "endereco_retorno": (endereco + google.CAMINHO_RETORNO) if endereco else None,
        "atualizado_em": retrato["atualizado_em"] if conectado else None,
    }


@router.post("/conectar")
async def conectar(request: Request):
    cfg = google.configuracao()
    if cfg is None:
        raise HTTPException(
            status_code=409,
            detail="A Google Agenda ainda não foi configurada no servidor (.env).",
        )
    state, verificador = _autorizacoes(request).criar()
    return JSONResponse(
        {"url": google.url_de_autorizacao(cfg, state, verificador)},
        headers=_SEM_GUARDAR,
    )


@router.get("/retorno")
async def retorno(request: Request):
    """O Google manda o navegador para cá (sem a chave do Éden)."""
    params = request.query_params
    verificador = _autorizacoes(request).usar(params.get("state"))
    if verificador is None:
        return _voltar("expirou")
    codigo = params.get("code") or ""
    if params.get("error") or not codigo or len(codigo) > 2048:
        return _voltar("negado")
    cliente = google.cliente_do_app(request.app)
    try:
        await asyncio.to_thread(cliente.trocar_codigo, codigo, verificador)
    except google.ErroGoogle as exc:
        logger.warning("Éden: ligação com o Google não concluída (%s)", exc.codigo)
        return _voltar("sem-permissao" if "permissao" in exc.codigo else "erro")
    except Exception:  # noqa: BLE001
        logger.exception("Éden: falha na ligação com o Google")
        return _voltar("erro")
    try:
        await asyncio.to_thread(google.atualizar_cache, cliente, get_settings().tz)
    except Exception:  # noqa: BLE001
        logger.warning("Éden: agenda ligada, mas não atualizou agora")
    logger.info("Éden: Google Agenda conectada")
    return _voltar("conectado")


@router.post("/desconectar")
async def desconectar(request: Request):
    cliente = google.cliente_do_app(request.app)
    google.CACHE.limpar()
    revogado = await asyncio.to_thread(cliente.desconectar)
    google.CACHE.limpar()
    logger.info("Éden: Google Agenda desconectada")
    # revogado False: desligou aqui, mas o Google não confirmou (a tela diz
    # onde retirar o acesso na conta do Google).
    return {"ok": True, "revogado": revogado is not False}


@router.get("/eventos")
async def eventos(request: Request, dias: int = 1):
    if not 1 <= dias <= 14:
        raise HTTPException(status_code=400, detail="'dias' vai de 1 a 14")
    if google.configuracao() is None:
        return {"conectado": False, "eventos": []}
    cliente = google.cliente_do_app(request.app)
    tz = get_settings().tz
    inicio, fim = google.janela(tz, dias=dias)
    try:
        lista = await asyncio.to_thread(cliente.listar, inicio, fim, tz)
    except google.ErroGoogle as exc:
        if exc.codigo in ("eden_google_desconectado", "eden_google_reconectar"):
            return {"conectado": False, "eventos": [], "aviso": str(exc)}
        return JSONResponse(
            status_code=502, content={"detail": str(exc), "code": exc.codigo}
        )
    return {"conectado": True, "eventos": lista}


@router.post("/atualizar")
async def atualizar(request: Request):
    """Atualiza a agenda que a IA enxerga (sem esperar os 5 minutos)."""
    if google.configuracao() is None:
        return {"conectado": False}
    cliente = google.cliente_do_app(request.app)
    try:
        ligado = await asyncio.to_thread(
            google.atualizar_cache, cliente, get_settings().tz
        )
    except google.ErroGoogle as exc:
        return JSONResponse(
            status_code=502, content={"detail": str(exc), "code": exc.codigo}
        )
    em = google.CACHE.retrato()["atualizado_em"]
    return {"conectado": ligado, "atualizado_em": em}
