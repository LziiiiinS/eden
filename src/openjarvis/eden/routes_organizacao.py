"""Éden: rotas da organização pessoal (Parte 2).

Tudo em /v1/eden/..., protegido pela chave de acesso do servidor como as
outras rotas /v1. O que a pessoa faz pela tela (criar, editar, apagar) vale
direto: a própria ação na tela é a confirmação. O que o Éden sugere na
conversa só acontece pelo POST /v1/eden/acoes/{id}/confirmar.
"""

from __future__ import annotations

import asyncio
import json
import threading
from datetime import timedelta
from typing import Any, Dict, Optional

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from openjarvis.eden import acoes as acoes_mod
from openjarvis.eden.organizacao import (
    ErroOrganizacao,
    Organizacao,
    agora_ms,
    local_de_ms,
)
from openjarvis.eden.settings import get_settings

router = APIRouter(prefix="/v1/eden", tags=["eden"])

MAX_CORPO = 256 * 1024
_lock = threading.Lock()


def _store(request: Request) -> Organizacao:
    store = getattr(request.app.state, "eden_organizacao", None)
    if store is not None:
        return store
    with _lock:
        store = getattr(request.app.state, "eden_organizacao", None)
        if store is None:
            store = Organizacao()
            request.app.state.eden_organizacao = store
    return store


async def _corpo(request: Request) -> Dict[str, Any]:
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > MAX_CORPO:
        raise HTTPException(status_code=413, detail="Pedido grande demais")
    pedacos = []
    tamanho = 0
    async for pedaco in request.stream():
        tamanho += len(pedaco)
        if tamanho > MAX_CORPO:
            raise HTTPException(status_code=413, detail="Pedido grande demais")
        pedacos.append(pedaco)
    try:
        dados = json.loads(b"".join(pedacos) or b"{}")
    except (json.JSONDecodeError, UnicodeDecodeError, RecursionError):
        raise HTTPException(status_code=400, detail="JSON inválido") from None
    if not isinstance(dados, dict):
        raise HTTPException(
            status_code=400, detail="O corpo precisa ser um objeto JSON"
        )
    return dados


async def _rodar(funcao, *args, **kwargs):
    try:
        return await asyncio.to_thread(funcao, *args, **kwargs)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def _erro_acao(exc: acoes_mod.ErroAcao) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status, content={"detail": str(exc), "code": exc.codigo}
    )


def _tz():
    return get_settings().tz


def _espaco_filtro(store: Organizacao, espaco: Optional[str]) -> Optional[str]:
    if not espaco or espaco == "todos":
        return None
    if store.espaco(espaco) is None:
        raise HTTPException(status_code=400, detail="Espaço desconhecido")
    return espaco


# ── espaços ──────────────────────────────────────────────────────────────


@router.get("/espacos")
async def listar_espacos(request: Request, arquivados: bool = False):
    store = _store(request)
    return {"espacos": await _rodar(store.listar_espacos, arquivados)}


@router.post("/espacos")
async def criar_espaco(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    espaco = await _rodar(
        store.criar_espaco, dados.get("nome"), dados.get("descricao", "")
    )
    return {"espaco": espaco}


@router.patch("/espacos/{espaco_id}")
async def editar_espaco(espaco_id: str, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"espaco": await _rodar(store.atualizar_espaco, espaco_id, dados)}


# ── perfil ───────────────────────────────────────────────────────────────


@router.get("/perfil")
async def ver_perfil(request: Request):
    return {"perfil": await _rodar(_store(request).perfil)}


@router.put("/perfil")
async def salvar_perfil(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"perfil": await _rodar(store.salvar_perfil, dados.get("texto", ""))}


# ── memórias ─────────────────────────────────────────────────────────────


@router.get("/memorias")
async def listar_memorias(request: Request, espaco: Optional[str] = None):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    itens = await _rodar(store.listar_memorias, filtro, filtro is None)
    return {"memorias": itens}


@router.post("/memorias")
async def criar_memoria(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    memoria = await _rodar(store.criar_memoria, dados.get("texto"), dados.get("espaco"))
    return {"memoria": memoria}


@router.patch("/memorias/{memoria_id}")
async def editar_memoria(memoria_id: int, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"memoria": await _rodar(store.atualizar_memoria, memoria_id, dados)}


@router.delete("/memorias/{memoria_id}")
async def apagar_memoria(memoria_id: int, request: Request):
    await _rodar(_store(request).apagar_memoria, memoria_id)
    return {"ok": True}


# ── tarefas ──────────────────────────────────────────────────────────────


@router.get("/tarefas")
async def listar_tarefas(
    request: Request, espaco: Optional[str] = None, estado: str = "abertas"
):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    return {"tarefas": await _rodar(store.listar_tarefas, filtro, estado)}


@router.post("/tarefas")
async def criar_tarefa(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"tarefa": await _rodar(store.criar_tarefa, dados, _tz())}


@router.patch("/tarefas/{tarefa_id}")
async def editar_tarefa(tarefa_id: int, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"tarefa": await _rodar(store.atualizar_tarefa, tarefa_id, dados, _tz())}


@router.delete("/tarefas/{tarefa_id}")
async def apagar_tarefa(tarefa_id: int, request: Request):
    await _rodar(_store(request).apagar_tarefa, tarefa_id)
    return {"ok": True}


# ── notas ────────────────────────────────────────────────────────────────


@router.get("/notas")
async def listar_notas(
    request: Request,
    espaco: Optional[str] = None,
    tipo: Optional[str] = None,
    busca: Optional[str] = None,
):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    return {"notas": await _rodar(store.listar_notas, filtro, tipo or None, busca)}


@router.post("/notas")
async def criar_nota(request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"nota": await _rodar(store.criar_nota, dados)}


@router.patch("/notas/{nota_id}")
async def editar_nota(nota_id: int, request: Request):
    store = _store(request)
    dados = await _corpo(request)
    return {"nota": await _rodar(store.atualizar_nota, nota_id, dados)}


@router.delete("/notas/{nota_id}")
async def apagar_nota(nota_id: int, request: Request):
    await _rodar(_store(request).apagar_nota, nota_id)
    return {"ok": True}


# ── ações sugeridas pelo Éden ────────────────────────────────────────────


@router.get("/acoes")
async def listar_acoes(request: Request, estado: Optional[str] = None):
    return {"acoes": await _rodar(_store(request).listar_acoes, estado)}


@router.get("/acoes/{acao_id}")
async def ver_acao(acao_id: str, request: Request):
    acao = await _rodar(_store(request).acao, acao_id)
    if acao is None:
        raise HTTPException(status_code=404, detail="Ação não encontrada")
    return {"acao": acao}


@router.post("/acoes/{acao_id}/confirmar")
async def confirmar_acao(acao_id: str, request: Request):
    """Executa a ação guardada — com os parâmetros do servidor, não do app.
    O app manda a assinatura do cartão que a pessoa viu."""
    from openjarvis.eden import google as google_mod

    store = _store(request)
    dados = await _corpo(request)
    cliente = (
        google_mod.cliente_do_app(request.app)
        if google_mod.configuracao() is not None
        else None
    )
    try:
        acao = await _rodar(
            acoes_mod.confirmar,
            store,
            acao_id,
            dados.get("assinatura"),
            _tz(),
            google=cliente,
        )
    except acoes_mod.ErroAcao as exc:
        return _erro_acao(exc)
    if cliente is not None and str(acao.get("tipo", "")).startswith("agenda."):
        # A IA passa a enxergar o evento novo/mudado logo.
        try:
            await asyncio.to_thread(google_mod.atualizar_cache, cliente, _tz())
        except Exception:  # noqa: BLE001
            pass
    return {"acao": acao}


@router.post("/acoes/{acao_id}/recusar")
async def recusar_acao(acao_id: str, request: Request):
    try:
        acao = await _rodar(acoes_mod.recusar, _store(request), acao_id)
    except acoes_mod.ErroAcao as exc:
        return _erro_acao(exc)
    return {"acao": acao}


# ── resumo do dia ────────────────────────────────────────────────────────


def _hoje(store: Organizacao, espaco: Optional[str]) -> Dict[str, Any]:
    tz = _tz()
    agora = agora_ms()
    momento = local_de_ms(agora, tz)
    hoje = momento.date().isoformat()
    semana = (momento.date() + timedelta(days=7)).isoformat()
    abertas = store.listar_tarefas(espaco, "abertas", 2000)
    atrasadas = [t for t in abertas if t["data"] and t["data"] < hoje]
    de_hoje = [t for t in abertas if t["data"] == hoje]
    proximas = [t for t in abertas if t["data"] and hoje < t["data"] <= semana]
    sem_data = [t for t in abertas if not t["data"]][:20]
    inicio_dia = int(
        momento.replace(hour=0, minute=0, second=0, microsecond=0).timestamp() * 1000
    )
    feitas_hoje = [
        t
        for t in store.listar_tarefas(espaco, "feitas", 200)
        if (t["feita_em"] or 0) >= inicio_dia
    ]
    fixadas = [n for n in store.listar_notas(espaco, limite=50) if n["fixada"]][:10]
    return {
        "data": hoje,
        "agora": agora,
        "atrasadas": atrasadas,
        "hoje": de_hoje,
        "proximas": proximas,
        "sem_data": sem_data,
        "feitas_hoje": feitas_hoje,
        "notas_fixadas": fixadas,
    }


@router.get("/hoje")
async def resumo_hoje(request: Request, espaco: Optional[str] = None):
    store = _store(request)
    filtro = _espaco_filtro(store, espaco)
    return await _rodar(_hoje, store, filtro)


# ── lembretes (aviso dentro do app) ──────────────────────────────────────


@router.get("/lembretes")
async def lembretes(request: Request):
    """Lembretes que já venceram (últimas 12 h) e os das próximas 24 h."""
    store = _store(request)
    agora = agora_ms()
    itens = await _rodar(store.proximos_lembretes, agora, agora + 24 * 3600 * 1000)
    return {"agora": agora, "lembretes": itens}


# ── registro ─────────────────────────────────────────────────────────────


@router.get("/registro")
async def registro(request: Request, limite: int = 100):
    return {"registro": await _rodar(_store(request).registro, limite)}


# ── avisos no aparelho (Web Push) ────────────────────────────────────────


def _chave_push(request: Request):
    from openjarvis.eden import push

    chave = getattr(request.app.state, "eden_push_chave", None)
    if chave is None:
        chave = push.carregar_chave()
        request.app.state.eden_push_chave = chave
    return chave


@router.get("/push/chave")
async def push_chave(request: Request):
    from openjarvis.eden import push

    chave = await asyncio.to_thread(_chave_push, request)
    return {"chave": push.chave_publica_b64(chave)}


@router.get("/push/inscricoes")
async def push_listar(request: Request):
    from openjarvis.eden import push

    return {"inscricoes": await _rodar(push.listar_inscricoes, _store(request))}


@router.post("/push/inscricoes")
async def push_inscrever(request: Request):
    from openjarvis.eden import push

    dados = await _corpo(request)
    try:
        insc = await asyncio.to_thread(push.salvar_inscricao, _store(request), dados)
    except push.ErroPush as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return {"inscricao": insc}


@router.delete("/push/inscricoes/{insc_id}")
async def push_remover(insc_id: int, request: Request):
    """Remove um aparelho da lista de avisos (pela tela de Configurações)."""
    from openjarvis.eden import push

    removida = await asyncio.to_thread(
        push.remover_inscricao_id, _store(request), insc_id
    )
    if not removida:
        raise HTTPException(status_code=404, detail="Aparelho não encontrado")
    return {"removida": True}


@router.post("/push/cancelar")
async def push_cancelar(request: Request):
    from openjarvis.eden import push

    dados = await _corpo(request)
    removida = await asyncio.to_thread(
        push.remover_inscricao, _store(request), dados.get("endpoint")
    )
    return {"removida": removida}


@router.post("/push/teste")
async def push_teste(request: Request):
    """Manda um aviso de teste para os aparelhos inscritos."""
    import httpx

    from openjarvis.eden import push

    store = _store(request)
    chave = await asyncio.to_thread(_chave_push, request)
    async with httpx.AsyncClient() as client:
        resultado = await push.enviar(
            store,
            chave,
            {
                "titulo": "Éden",
                "corpo": "Teste: os avisos estão funcionando neste aparelho.",
                "tag": "teste",
                "url": "/tarefas",
            },
            client,
        )
    return resultado
