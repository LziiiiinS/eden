"""Éden (Parte 4): rotas da voz (/v1/eden/voz).

Pedem a chave de acesso, como as outras rotas do Éden. O texto não é
guardado nem registrado.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from openjarvis.eden import voz
from openjarvis.eden.budget import BudgetExceeded, get_ledger
from openjarvis.eden.providers import ProviderError
from openjarvis.eden.redact import redact_secrets
from openjarvis.eden.routes_organizacao import _corpo
from openjarvis.eden.settings import get_settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden/voz", tags=["eden"])


def _recusa(status: int, detalhe: str, codigo: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"detail": detalhe, "code": codigo},
        headers={"Cache-Control": "no-store"},
    )


@router.get("/status")
async def status():
    return {
        "available": voz.tem_chave(),
        "backend": "openai",
        "modelo": voz.MODELO,
        "vozes": list(voz.VOZES),
        "voz_padrao": voz.VOZ_PADRAO,
        "preco_por_1000_caracteres_usd": voz.PRECO_POR_1000_CARACTERES,
        "max_caracteres": voz.MAX_CARACTERES,
    }


@router.post("")
async def falar(request: Request):
    dados = await _corpo(request)
    try:
        texto = voz.limpar_texto(dados.get("texto"))
    except voz.ErroVoz as exc:
        return _recusa(exc.status, str(exc), exc.codigo)
    escolhida = voz.escolher_voz(dados.get("voz"))
    if not voz.tem_chave():
        return _recusa(
            409,
            "A voz usa a OpenAI: falta a chave da OpenAI no servidor.",
            "eden_voz_sem_chave",
        )
    settings = get_settings()
    try:
        get_ledger().check(voz.PROVEDOR, settings, voz.custo_usd(len(texto)))
    except BudgetExceeded as exc:
        return JSONResponse(
            status_code=429,
            content={"detail": str(exc), "code": "eden_limite", "provider": "openai"},
            headers={"Cache-Control": "no-store"},
        )
    if not voz.TETO.usar(len(texto)):
        return _recusa(
            429,
            "Muita fala na última hora. Espere um pouco ou leia na tela.",
            "eden_voz_limite",
        )
    try:
        audio = await voz.falar(texto, escolhida, settings=settings)
    except BudgetExceeded as exc:
        return _recusa(429, str(exc), "eden_limite")
    except voz.ErroVoz as exc:
        return _recusa(exc.status, str(exc), exc.codigo)
    except ProviderError as exc:
        return _recusa(502, redact_secrets(str(exc)), "eden_voz_openai")
    except Exception as exc:  # noqa: BLE001 — rede; nunca mostra detalhes
        logger.error("Éden: falha na voz: %s", type(exc).__name__)
        return _recusa(
            502, "A conexão com a OpenAI falhou. Tente de novo.", "eden_voz_rede"
        )
    return Response(
        content=audio,
        media_type="audio/mpeg",
        headers={"Cache-Control": "no-store", "X-Voice-Id": escolhida},
    )
