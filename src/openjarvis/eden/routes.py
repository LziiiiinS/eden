"""Éden: rotas para sincronizar as conversas entre os aparelhos.

Ficam em /v1/eden/..., então a chave de acesso do servidor
(OPENJARVIS_API_KEY) protege todas elas, como as outras rotas /v1.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time

from fastapi import APIRouter, HTTPException, Request

from openjarvis.eden.conversations import (
    DEFAULT_USER_ID,
    ConversationStore,
    ConversationValidationError,
    is_valid_id,
    validate_conversation,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/eden", tags=["eden"])

MAX_BODY_BYTES = 8 * 1024 * 1024

_store_lock = threading.Lock()


def _get_store(request: Request) -> ConversationStore:
    store = getattr(request.app.state, "eden_conversations", None)
    if store is not None:
        return store
    with _store_lock:
        store = getattr(request.app.state, "eden_conversations", None)
        if store is None:
            store = ConversationStore()
            request.app.state.eden_conversations = store
    return store


def _user_id(request: Request) -> str:
    # Piloto: um usuário só. Quando houver login de vários usuários, o ID
    # virá da sessão autenticada, nunca de um campo enviado pelo app.
    return DEFAULT_USER_ID


def _check_id(conv_id: str) -> None:
    if not is_valid_id(conv_id):
        raise HTTPException(status_code=400, detail="ID de conversa inválido")


@router.get("/conversations")
async def list_conversations(request: Request):
    """Lista as conversas (sem mensagens), incluindo as apagadas."""
    store = _get_store(request)
    items = await asyncio.to_thread(store.list_conversations, _user_id(request))
    return {"conversations": items, "serverTime": int(time.time() * 1000)}


@router.get("/conversations/{conv_id}")
async def get_conversation(conv_id: str, request: Request):
    """Uma conversa com todas as mensagens."""
    _check_id(conv_id)
    store = _get_store(request)
    conv = await asyncio.to_thread(store.get_conversation, conv_id, _user_id(request))
    if conv is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada")
    return {"conversation": conv}


@router.put("/conversations/{conv_id}")
async def put_conversation(conv_id: str, request: Request):
    """Grava a conversa inteira enviada pelo aparelho (sem duplicar)."""
    _check_id(conv_id)
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Conversa grande demais")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Conversa grande demais")
    try:
        payload = json.loads(body or b"{}")
        conv = validate_conversation(conv_id, payload)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="JSON inválido")
    except ConversationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    store = _get_store(request)
    meta = await asyncio.to_thread(store.upsert_conversation, conv, _user_id(request))
    server_has_more = bool(meta.pop("serverHasMore", False))
    return {"conversation": meta, "serverHasMore": server_has_more}


@router.delete("/conversations/{conv_id}")
async def delete_conversation(conv_id: str, request: Request, deleted_at: int = 0):
    """Apaga a conversa. ``deleted_at`` é o momento (ms) em que o usuário apagou."""
    _check_id(conv_id)
    when = deleted_at if deleted_at > 0 else int(time.time() * 1000)
    store = _get_store(request)
    try:
        meta = await asyncio.to_thread(
            store.delete_conversation, conv_id, when, _user_id(request)
        )
    except ConversationValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"conversation": meta}
