"""Éden: ganchos na rota de conversa (/v1/chat/completions).

Antes: troca o modelo do Éden (eden-auto, eden-dia, eden-missao) pelo modelo
de verdade e confere o limite de gastos. Depois: informa ao app qual IA
respondeu (cabeçalhos X-Eden-*) e, nas respostas sem streaming, anota o gasto.
O streaming anota o gasto em openjarvis.eden.providers.
"""

from __future__ import annotations

import logging
from typing import Any, Optional, Tuple

from starlette.responses import JSONResponse, Response

from openjarvis.eden.budget import BudgetExceeded, estimate_tokens, get_ledger
from openjarvis.eden.routing import (
    AUTO_IN_MISSION,
    REASON_COMMAND,
    VIRTUAL_MODELS,
    RouteDecision,
    resolve,
    strip_command,
)
from openjarvis.eden.settings import TRACKED_PROVIDERS, get_settings

logger = logging.getLogger(__name__)


def _last_user(request_body: Any) -> Optional[Any]:
    for message in reversed(request_body.messages or []):
        if message.role == "user":
            return message
    return None


def _provider(model: str) -> Optional[str]:
    from openjarvis.server.cloud_router import get_provider

    return get_provider(model)


def _refuse(code: str, detail: str) -> Response:
    return JSONResponse(status_code=400, content={"detail": detail, "code": code})


# Modelos que o app do Éden pode pedir (os três modos e o automático que
# continua uma missão). O servidor troca pelo modelo de verdade.
EDEN_REQUEST_MODELS = frozenset(VIRTUAL_MODELS) | {AUTO_IN_MISSION}


def _eden_gate(request_body: Any, settings: Any) -> Optional[Response]:
    """No servidor do Éden, só passa o caminho que tem limite de gastos:
    um dos modos do Éden, com streaming e sem ferramentas."""
    if not request_body.stream:
        # Sem streaming, a conversa iria pelo motor antigo do OpenJarvis
        # (sem store=false e fora do caminho do Éden).
        return _refuse(
            "eden_somente_streaming",
            "No servidor do Éden, a conversa usa streaming (stream: true).",
        )
    if request_body.tools or getattr(request_body, "tool_choice", None):
        # Com ferramentas, o pedido ia direto ao SDK da empresa, sem anotar o
        # gasto. O Éden do piloto não usa ferramentas.
        return _refuse(
            "eden_sem_ferramentas",
            "O Éden não aceita ferramentas (tools) neste servidor.",
        )
    if request_body.model not in EDEN_REQUEST_MODELS:
        # Outros nomes de modelo podiam escapar da conta de gastos.
        return _refuse(
            "eden_modelo",
            "Use um dos modos do Éden: eden-auto, eden-dia ou eden-missao.",
        )
    return None


def prepare_chat(
    request_body: Any,
) -> Tuple[Optional[RouteDecision], Optional[Response]]:
    """Escolhe a IA e confere o limite. Devolve (decisão, resposta de erro)."""
    settings = get_settings()
    if settings.enabled:
        refusal = _eden_gate(request_body, settings)
        if refusal is not None:
            return None, refusal
    last_user = _last_user(request_body)
    decision = resolve(
        request_body.model, last_user.content if last_user else "", settings
    )
    if decision is not None:
        request_body.model = decision.model
        if decision.reason == REASON_COMMAND and last_user is not None:
            last_user.content = strip_command(last_user.content) or last_user.content

    model = request_body.model
    provider = _provider(model)
    if settings.enabled:
        if provider not in TRACKED_PROVIDERS or model not in settings.prices:
            # Modelo sem preço explícito em [eden.precos]: a conta de gastos
            # ficaria estimada; melhor recusar e avisar.
            return decision, _refuse(
                "eden_preco",
                f"O modelo {model} não tem preço em [eden.precos] no servidor.",
            )
        # Teto de tamanho da resposta: nunca mais que [eden.ias] max_saida_tokens.
        request_body.max_tokens = min(
            int(request_body.max_tokens or settings.max_output_tokens),
            settings.max_output_tokens,
        )
    if provider in TRACKED_PROVIDERS:
        chars = sum(len(m.content or "") for m in request_body.messages or [])
        reserve = settings.token_cost(
            provider, model, estimate_tokens(chars), settings.max_output_tokens
        )
        try:
            get_ledger().check(provider, settings, reserve)
        except BudgetExceeded as exc:
            headers = decision.headers() if decision is not None else None
            return decision, JSONResponse(
                status_code=429,
                content={
                    "detail": str(exc),
                    "code": "eden_limite",
                    "provider": provider,
                },
                headers=headers,
            )
    return decision, None


def finish_chat(
    response: Any, decision: Optional[RouteDecision], request_body: Any
) -> Any:
    """Anota o gasto das respostas sem streaming e marca qual IA respondeu."""
    model = request_body.model
    provider = _provider(model)
    if not request_body.stream and provider in TRACKED_PROVIDERS:
        usage = getattr(response, "usage", None)
        if usage is not None:
            settings = get_settings()
            try:
                get_ledger().record(
                    provider=provider,
                    model=model,
                    kind="conversa",
                    cost_usd=settings.token_cost(
                        provider,
                        model,
                        int(getattr(usage, "prompt_tokens", 0) or 0),
                        int(getattr(usage, "completion_tokens", 0) or 0),
                    ),
                    settings=settings,
                    input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
                    output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
                )
            except Exception:  # noqa: BLE001
                logger.exception("Éden: falha ao anotar o gasto")

    if decision is None:
        return response
    if isinstance(response, Response):
        for name, value in decision.headers().items():
            response.headers[name] = value
        return response
    if hasattr(response, "model_dump"):
        return JSONResponse(
            content=response.model_dump(mode="json"), headers=decision.headers()
        )
    return response
