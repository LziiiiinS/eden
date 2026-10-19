"""Éden: rotas do modo reunião (ver reuniao.py).

- ``POST /v1/eden/reunioes``: começa (a pessoa toca em "Começar").
- ``POST /v1/eden/reunioes/{id}/pedaco``: um pedaço de áudio (~1 min).
- ``POST /v1/eden/reunioes/{id}/terminar``: para e faz o resumo.
- ``POST /v1/eden/reunioes/{id}/cartoes``: cartões das tarefas de novo
  (eles valem 15 minutos).
- ``GET`` lista/abre; ``DELETE`` apaga o texto da reunião.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from datetime import datetime
from typing import Any, Dict, List, Set, Tuple

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from openjarvis.core.types import Message, Role
from openjarvis.eden import acoes as acoes_mod
from openjarvis.eden import reuniao, tetos
from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao
from openjarvis.eden.routes_organizacao import _corpo, _rodar, _store, _tz

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden/reunioes", tags=["eden"])

_FORMATOS = {"webm", "mp4", "m4a", "ogg", "wav", "mp3", "mpeg", "mpga"}

# Pedaços sendo transcritos agora (o app pode mandar de novo enquanto o
# primeiro ainda está na OpenAI): o segundo espera em vez de pagar duas vezes.
_em_andamento: Set[Tuple[int, int]] = set()
_lock = threading.Lock()


class ErroResumo(Exception):
    pass


def _erro(exc: ErroOrganizacao) -> HTTPException:
    return HTTPException(status_code=exc.status, detail=str(exc))


def _cartoes(store: Organizacao, rid: int) -> List[Dict[str, Any]]:
    return store.listar_acoes(conversa=reuniao.conversa_da_reuniao(rid))


@router.get("")
async def listar(request: Request):
    return {"reunioes": await _rodar(reuniao.listar, _store(request))}


@router.post("")
async def comecar(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"reuniao": await _rodar(reuniao.criar, store, dados)}


@router.get("/{rid}")
async def abrir(rid: str, request: Request):
    store = _store(request)
    r = await _rodar(reuniao.obter, store, rid)
    r["cartoes"] = await _rodar(_cartoes, store, r["id"])
    return {"reuniao": r}


@router.delete("/{rid}")
async def apagar(rid: str, request: Request):
    await _rodar(reuniao.apagar, _store(request), rid)
    return {"ok": True}


def _formato(nome: Any) -> str:
    ext = nome.rsplit(".", 1)[-1].lower() if isinstance(nome, str) else ""
    return ext if ext in _FORMATOS else "webm"


def _idioma(request: Request) -> Any:
    config = getattr(request.app.state, "config", None)
    fala = getattr(config, "speech", None)
    idioma = getattr(fala, "language", "")
    return idioma if isinstance(idioma, str) and idioma else None


@router.post("/{rid}/pedaco")
async def pedaco(rid: str, request: Request):
    from starlette.requests import ClientDisconnect

    from openjarvis.eden import speech_budget
    from openjarvis.eden.budget import BudgetExceeded
    from openjarvis.eden.redact import redact_secrets

    store = _store(request)
    backend = getattr(request.app.state, "speech_backend", None)
    if backend is None:
        raise HTTPException(
            status_code=501, detail="A transcrição de voz não está ligada no servidor."
        )
    declarado = request.headers.get("content-length", "")
    if declarado.isdigit() and int(declarado) > reuniao.MAX_BYTES_PEDACO + 65536:
        raise HTTPException(status_code=413, detail="Pedaço de áudio grande demais.")
    try:
        form = await request.form(max_files=1, max_fields=4)
    except ClientDisconnect:
        raise HTTPException(
            status_code=400,
            detail="A conexão caiu no meio do envio; o app tenta de novo.",
        ) from None
    try:
        reuniao_id = reuniao.reuniao_id(rid)
        n = reuniao.numero_pedaco(form.get("n"))
    except ErroOrganizacao as exc:
        raise _erro(exc) from None
    arquivo = form.get("file")
    if arquivo is None or not hasattr(arquivo, "read"):
        raise HTTPException(status_code=400, detail="Faltou o áudio.")
    dados = await arquivo.read(reuniao.MAX_BYTES_PEDACO + 1)
    if len(dados) > reuniao.MAX_BYTES_PEDACO:
        raise HTTPException(status_code=413, detail="Pedaço de áudio grande demais.")
    if not dados:
        raise HTTPException(status_code=400, detail="O pedaço veio vazio.")

    chave = (reuniao_id, n)
    with _lock:
        if chave in _em_andamento:
            raise HTTPException(
                status_code=409, detail="Este pedaço ainda está sendo transcrito."
            )
        _em_andamento.add(chave)
    try:
        novo = await _rodar(reuniao.pode_receber, store, reuniao_id, n)
        if not novo:
            return {"ok": True, "n": n, "repetido": True}
        if not tetos.usar("reuniao", tetos.aparelho_do_pedido(request)):
            raise HTTPException(status_code=429, detail=tetos.mensagem("reuniao"))
        client_ms = speech_budget.parse_client_ms(form.get("duration_ms"))
        arquivo_s = speech_budget.duracao_do_arquivo(dados)
        reserva = None
        if speech_budget.tracked(backend):
            try:
                reserva = speech_budget.check(backend, len(dados), client_ms, arquivo_s)
            except BudgetExceeded as exc:
                raise HTTPException(status_code=429, detail=str(exc)) from exc
        try:
            resultado = await asyncio.to_thread(
                backend.transcribe,
                dados,
                format=_formato(getattr(arquivo, "filename", "")),
                language=_idioma(request),
            )
        except Exception as exc:
            speech_budget.release(reserva)
            logger.error("Reunião: falha ao transcrever: %s", redact_secrets(exc))
            raise HTTPException(
                status_code=502,
                detail="Não deu para transcrever este pedaço; o app tenta de novo.",
            ) from None
        if speech_budget.tracked(backend):
            speech_budget.record(
                backend,
                resultado.duration_seconds,
                len(dados),
                client_ms,
                reservation=reserva,
                arquivo_s=arquivo_s,
            )
        segundos = (
            resultado.duration_seconds or arquivo_s or ((client_ms or 0) / 1000.0)
        )
        salvo = await _rodar(
            reuniao.guardar_pedaco, store, reuniao_id, n, resultado.text, segundos
        )
        return {"ok": True, "n": n, "repetido": not salvo}
    finally:
        with _lock:
            _em_andamento.discard(chave)


# ── resumo ───────────────────────────────────────────────────────────────


async def _chamar_ia(mensagens: List[Message]) -> str:
    """Claude (missão) primeiro; se não der (limite, chave), o do dia a dia."""
    from openjarvis.eden.budget import BudgetExceeded
    from openjarvis.eden.chat_hooks import _provider
    from openjarvis.eden.providers import ProviderError, stream_eden
    from openjarvis.eden.settings import TRACKED_PROVIDERS, get_settings

    settings = get_settings()
    erros: List[str] = []
    for modelo in dict.fromkeys((settings.mission_model, settings.daily_model)):
        provedor = _provider(modelo)
        if provedor not in TRACKED_PROVIDERS or modelo not in settings.prices:
            continue
        try:
            partes = [
                t
                async for t in stream_eden(
                    modelo, mensagens, None, provedor, settings=settings
                )
            ]
        except (BudgetExceeded, ProviderError) as exc:
            erros.append(str(exc))
            continue
        texto = "".join(partes).strip()
        if texto:
            return texto
        erros.append("a IA não respondeu")
    raise ErroResumo(erros[-1] if erros else "nenhuma IA ligada para o resumo")


def _criar_cartoes(
    store: Organizacao, rid: int, espaco: str, tarefas: List[Dict[str, Any]]
) -> List[str]:
    if not tarefas:
        return []
    _, recusadas = acoes_mod.propor(
        reuniao.blocos_de_tarefas(tarefas, espaco),
        store,
        espaco,
        _tz(),
        conversa_id=reuniao.conversa_da_reuniao(rid),
    )
    return recusadas


async def _resumir(store: Organizacao, info: Dict[str, Any]) -> None:
    rid = info["id"]
    hoje = datetime.now(_tz()).date().isoformat()
    mensagens = [
        Message(role=Role.SYSTEM, content=reuniao.instrucoes(hoje)),
        Message(
            role=Role.USER,
            content=reuniao.mensagem_da_transcricao(
                info["titulo"], info["transcricao"], info["cortada"]
            ),
        ),
    ]
    try:
        resposta = await _chamar_ia(mensagens)
    except ErroResumo as exc:
        await _rodar(reuniao.falhar, store, rid, f"Não deu para resumir: {exc}")
        return
    except Exception:  # noqa: BLE001 — a reunião nunca fica presa
        logger.exception("Reunião: falha inesperada no resumo")
        await _rodar(reuniao.falhar, store, rid, "Algo deu errado no resumo.")
        return
    tarefas, _ignorados = reuniao.tarefas_da_resposta(resposta)
    texto = acoes_mod.remover_blocos(resposta).strip()
    await _rodar(reuniao.concluir, store, rid, texto, tarefas)
    try:
        await _rodar(_criar_cartoes, store, rid, info["espaco"], tarefas)
    except Exception:  # noqa: BLE001
        logger.exception("Reunião: falha ao criar os cartões das tarefas")


@router.post("/{rid}/terminar")
async def terminar(rid: str, request: Request, tarefas_fundo: BackgroundTasks):
    store = _store(request)
    info = await _rodar(reuniao.comecar_resumo, store, rid)
    tarefas_fundo.add_task(_resumir, store, info)
    return {"ok": True, "estado": "resumindo"}


@router.post("/{rid}/cartoes")
async def cartoes_de_novo(rid: str, request: Request):
    store = _store(request)
    r = await _rodar(reuniao.obter, store, rid, False)
    if r["estado"] != "pronta":
        raise HTTPException(status_code=409, detail="O resumo ainda não está pronto.")
    pendentes = [
        c for c in await _rodar(_cartoes, store, r["id"]) if c["estado"] == "pendente"
    ]
    if pendentes:
        raise HTTPException(
            status_code=409, detail="Os cartões desta reunião ainda estão valendo."
        )
    # Tarefas que já viraram tarefa (cartão confirmado) não voltam.
    feitas = {
        " ".join(str(c["parametros"].get("titulo", "")).split())
        for c in await _rodar(_cartoes, store, r["id"])
        if c["estado"] == "feita" and isinstance(c["parametros"], dict)
    }
    faltam = [t for t in r["tarefas"] if " ".join(t["titulo"].split()) not in feitas]
    recusadas = await _rodar(_criar_cartoes, store, r["id"], r["espaco"], faltam)
    return {
        "cartoes": await _rodar(_cartoes, store, r["id"]),
        "recusadas": recusadas,
    }
