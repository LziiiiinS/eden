"""Éden: rotas dos documentos (/v1/eden/documentos/...).

Todas pedem a chave de acesso. Enviar, anexar, desanexar e apagar são feitos
pela própria pessoa na tela (o toque é a confirmação); a IA não chega aqui.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional
from urllib.parse import unquote

from fastapi import APIRouter, HTTPException, Request

from openjarvis.eden import documentos as docs
from openjarvis.eden.conversations import is_valid_id
from openjarvis.eden.organizacao import ErroOrganizacao
from openjarvis.eden.routes_organizacao import _store

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden/documentos", tags=["eden"])


async def _rodar(funcao, *args):
    try:
        return await asyncio.to_thread(funcao, *args)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None


def _espaco(request: Request, espaco: Optional[str]) -> str:
    store = _store(request)
    if not espaco or store.espaco(espaco) is None:
        raise HTTPException(status_code=400, detail="Espaço desconhecido")
    return espaco


def _conversa(conversa_id: str) -> str:
    if not is_valid_id(conversa_id):
        raise HTTPException(status_code=400, detail="Conversa inválida")
    return conversa_id


async def _arquivo(request: Request) -> bytes:
    """Lê o corpo cru (o arquivo), no máximo MAX_ARQUIVO bytes."""
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > docs.MAX_ARQUIVO:
        raise HTTPException(status_code=413, detail="Arquivo grande demais (até 10 MB)")
    pedacos = []
    tamanho = 0
    async for pedaco in request.stream():
        tamanho += len(pedaco)
        if tamanho > docs.MAX_ARQUIVO:
            raise HTTPException(
                status_code=413, detail="Arquivo grande demais (até 10 MB)"
            )
        pedacos.append(pedaco)
    dados = b"".join(pedacos)
    if not dados:
        raise HTTPException(status_code=400, detail="Arquivo vazio")
    return dados


@router.get("")
async def listar(request: Request, espaco: Optional[str] = None):
    store = _store(request)
    filtro = _espaco(request, espaco) if espaco and espaco != "todos" else None
    return {
        "documentos": await _rodar(docs.listar, store, filtro),
        "limites": {
            "arquivo_bytes": docs.MAX_ARQUIVO,
            "por_conversa": docs.MAX_NA_CONVERSA,
            "por_espaco": docs.MAX_POR_ESPACO,
            "no_contexto": docs.MAX_NO_CONTEXTO,
        },
    }


@router.post("", status_code=201)
async def enviar(request: Request, espaco: Optional[str] = None):
    """Corpo: o arquivo cru. Cabeçalho X-Eden-Nome: nome do arquivo
    (codificado como URL, para aceitar acentos)."""
    store = _store(request)
    esp = _espaco(request, espaco)
    try:
        nome = docs.limpar_nome(unquote(request.headers.get("x-eden-nome", "")))
        dados = await _arquivo(request)
        tipo = docs.tipo_do_arquivo(nome, dados[:1024])
        extraido = await docs.extrair_texto(dados, tipo)
    except ErroOrganizacao as exc:
        raise HTTPException(status_code=exc.status, detail=str(exc)) from None
    documento = await _rodar(
        docs.guardar,
        store,
        esp,
        nome,
        tipo,
        len(dados),
        docs.resumo_sha256(dados),
        extraido["texto"],
        extraido["paginas"],
    )
    logger.info("Éden: documento guardado (%s, %d bytes)", tipo, len(dados))
    return {"documento": documento}


@router.get("/conversa/{conversa_id}")
async def da_conversa(conversa_id: str, request: Request):
    store = _store(request)
    return {"documentos": await _rodar(docs.anexados, store, _conversa(conversa_id))}


@router.put("/conversa/{conversa_id}/{doc_id}")
async def anexar(conversa_id: str, doc_id: int, request: Request):
    store = _store(request)
    lista = await _rodar(docs.anexar, store, _conversa(conversa_id), doc_id)
    return {"documentos": lista}


@router.delete("/conversa/{conversa_id}/{doc_id}")
async def desanexar(conversa_id: str, doc_id: int, request: Request):
    store = _store(request)
    lista = await _rodar(docs.desanexar, store, _conversa(conversa_id), doc_id)
    return {"documentos": lista}


@router.get("/{doc_id}")
async def ver(doc_id: int, request: Request):
    documento = await _rodar(docs.documento, _store(request), doc_id)
    if documento is None:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {"documento": documento}


@router.delete("/{doc_id}")
async def apagar(doc_id: int, request: Request):
    if not await _rodar(docs.apagar, _store(request), doc_id):
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    return {"ok": True}
