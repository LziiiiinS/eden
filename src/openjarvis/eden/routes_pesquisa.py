"""Éden (Parte 4): rota da pesquisa na internet (POST /v1/eden/pesquisa).

Pede a chave de acesso (como as outras rotas do Éden). Responde no mesmo
formato do chat (pedaços ``data:`` do tipo OpenAI), para o app reaproveitar a
leitura. Nunca cria cartões de ação e não grava nada na memória.
"""

from __future__ import annotations

import contextlib
import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, StreamingResponse

from openjarvis.eden import pesquisa
from openjarvis.eden.budget import BudgetExceeded, get_ledger
from openjarvis.eden.providers import ProviderError
from openjarvis.eden.redact import redact_secrets
from openjarvis.eden.routes_organizacao import _corpo
from openjarvis.eden.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden", tags=["eden"])


def _recusa(status: int, detalhe: str, codigo: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detalhe, "code": codigo},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/pesquisa/status")
async def status():
    return {
        "disponivel": pesquisa.tem_chave(),
        "max_buscas": pesquisa.MAX_BUSCAS,
        "max_por_hora": pesquisa.MAX_POR_HORA,
        "preco_busca_usd": pesquisa.PRECO_BUSCA_USD,
    }


@router.post("/pesquisa")
async def pesquisar(request: Request):
    dados = await _corpo(request)
    try:
        mensagens = pesquisa.mensagens_da_conversa(dados.get("messages"))
    except pesquisa.ErroPesquisa as exc:
        return _recusa(exc.status, str(exc), exc.codigo)
    if not pesquisa.tem_chave():
        return _recusa(
            409,
            "A pesquisa usa o Claude: falta a chave da Anthropic no servidor.",
            "eden_pesquisa_sem_chave",
        )
    settings = get_settings()
    if not pesquisa.modelo_ok(settings):
        return _recusa(409, pesquisa.MSG_MODELO, "eden_pesquisa_modelo")
    chars = len(pesquisa.instrucoes(pesquisa.agora(settings)).encode("utf-8")) + sum(
        len(m["content"].encode("utf-8")) for m in mensagens
    )
    try:
        get_ledger().check(
            pesquisa.PROVEDOR, settings, pesquisa.reserva_usd(settings, chars)
        )
    except BudgetExceeded as exc:
        return JSONResponse(
            status_code=429,
            content={
                "detail": str(exc),
                "code": "eden_limite",
                "provider": pesquisa.PROVEDOR,
            },
            headers={"Cache-Control": "no-store"},
        )
    if not pesquisa.LIMITE.usar():
        return _recusa(
            429,
            f"Já foram {pesquisa.MAX_POR_HORA} pesquisas na última hora. "
            "Espere um pouco e tente de novo.",
            "eden_pesquisa_limite",
        )

    async def gerar():
        try:
            # aclosing: se o app desconectar, a pesquisa fecha na hora e o
            # gasto é anotado (sem depender da coleta de lixo).
            async with contextlib.aclosing(
                pesquisa.stream_pesquisa(mensagens, settings=settings)
            ) as fluxo:
                async for texto in fluxo:
                    yield pesquisa.pedaco_sse(texto)
        except Exception as exc:  # noqa: BLE001 — o erro vira texto na conversa
            if isinstance(exc, (BudgetExceeded, pesquisa.ErroPesquisa, ProviderError)):
                motivo = redact_secrets(str(exc))
            else:
                logger.error(
                    "Éden: falha na pesquisa: %s: %s",
                    type(exc).__name__,
                    redact_secrets(exc),
                )
                motivo = "a conexão com a Anthropic falhou. Tente de novo."
            yield pesquisa.pedaco_sse(f"\n\n**Não foi possível pesquisar:** {motivo}")
        yield pesquisa.fim_sse()

    cabecalhos = pesquisa.cabecalhos_rota(settings)
    cabecalhos["X-Accel-Buffering"] = "no"
    return StreamingResponse(
        gerar(), media_type="text/event-stream", headers=cabecalhos
    )
