"""Éden: ganchos na rota de conversa (/v1/chat/completions).

Antes: troca o modelo do Éden (eden-auto, eden-dia, eden-missao) pelo modelo
de verdade e confere o limite de gastos. Depois: informa ao app qual IA
respondeu (cabeçalhos X-Eden-*) e, nas respostas sem streaming, anota o gasto.
O streaming anota o gasto em openjarvis.eden.providers.

Parte 2: o pedido traz o espaço ativo (cabeçalho X-Eden-Espaco) e a conversa
(X-Eden-Conversa). O contexto do Éden (perfil, memórias, tarefas, notas do
espaço) entra na mensagem de sistema, e no fim da resposta o servidor lê os
blocos eden-acao e manda ao app as ações para a pessoa confirmar (evento
"eden_acoes", antes do fim do streaming).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, AsyncIterator, Optional, Tuple

from starlette.responses import JSONResponse, Response, StreamingResponse

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


def _organizacao(request: Any):
    from openjarvis.eden.organizacao import Organizacao

    store = getattr(request.app.state, "eden_organizacao", None)
    if store is None:
        store = Organizacao()
        request.app.state.eden_organizacao = store
    return store


def _definir_pedido(request: Any, pergunta: Optional[str] = None) -> None:
    """Guarda o espaço e a conversa deste pedido (cabeçalhos do app)."""
    from openjarvis.eden.contexto import PedidoEden, definir_pedido
    from openjarvis.eden.conversations import is_valid_id

    try:
        store = _organizacao(request)
        espacos = [e["id"] for e in store.listar_espacos()]
        espaco = request.headers.get("x-eden-espaco", "")
        if espaco not in espacos:
            espaco = "pessoal" if "pessoal" in espacos else espacos[0]
        conversa = request.headers.get("x-eden-conversa") or None
        if conversa is not None and not is_valid_id(conversa):
            conversa = None
        definir_pedido(
            PedidoEden(
                espaco=espaco,
                conversa_id=conversa,
                store=store,
                pergunta=pergunta if isinstance(pergunta, str) else None,
            )
        )
    except Exception:  # noqa: BLE001
        logger.exception("Éden: não consegui preparar o contexto da conversa")
        definir_pedido(None)


def _caracteres_documentos() -> int:
    from openjarvis.eden.contexto import pedido_atual

    pedido = pedido_atual()
    if pedido is None or pedido.store is None or not pedido.conversa_id:
        return 0
    try:
        from openjarvis.eden.documentos import bytes_no_contexto

        return bytes_no_contexto(pedido.store, pedido.conversa_id, pedido.espaco)
    except Exception:  # noqa: BLE001
        logger.exception("Éden: não consegui medir os documentos anexados")
        return 0


def eden_system_extra() -> str:
    """Contexto do Éden para a mensagem de sistema ("" fora do Éden)."""
    from openjarvis.eden.contexto import montar, pedido_atual

    settings = get_settings()
    pedido = pedido_atual()
    if not settings.enabled or pedido is None or pedido.store is None:
        return ""
    try:
        from openjarvis.eden.google import CACHE

        return montar(
            pedido.store,
            pedido.espaco,
            settings.tz,
            conversa_id=pedido.conversa_id,
            agenda=CACHE.retrato(),
            pergunta=pedido.pergunta,
        )
    except Exception:  # noqa: BLE001
        logger.exception("Éden: não consegui montar o contexto")
        return ""


async def antes_da_conversa(request_body: Any, request: Any = None) -> None:
    """Antes de montar o contexto: se a pergunta é sobre trânsito, atualiza
    os trajetos salvos (TomTom). Espera no máximo 8 s; falha não impede a
    conversa (o contexto diz que não há dado)."""
    settings = get_settings()
    if not settings.enabled:
        return
    try:
        from openjarvis.eden.pesquisa import neutralizar_historico

        # Respostas antigas da pesquisa na internet voltam "desarmadas".
        neutralizar_historico(getattr(request_body, "messages", None))
    except Exception:  # noqa: BLE001
        logger.exception("Éden: falha ao desarmar respostas de pesquisa")
    if request is None:
        return
    ultima = _last_user(request_body)
    pergunta = ultima.content if ultima and isinstance(ultima.content, str) else None
    try:
        from openjarvis.eden import rotas

        if not rotas.configurado() or not rotas.pergunta_sobre_rotas(pergunta):
            return
        await asyncio.wait_for(
            asyncio.to_thread(
                rotas.atualizar_para_pergunta,
                _organizacao(request),
                pergunta,
                rotas.cliente_do_app(request.app),
            ),
            timeout=8,
        )
    except asyncio.TimeoutError:
        logger.warning("Éden: trajetos não atualizaram a tempo")
    except Exception:  # noqa: BLE001
        logger.exception("Éden: falha ao atualizar os trajetos")


def prepare_chat(
    request_body: Any,
    request: Any = None,
) -> Tuple[Optional[RouteDecision], Optional[Response]]:
    """Escolhe a IA e confere o limite. Devolve (decisão, resposta de erro)."""
    settings = get_settings()
    if settings.enabled:
        refusal = _eden_gate(request_body, settings)
        if refusal is not None:
            return None, refusal
    last_user = _last_user(request_body)
    if settings.enabled and request is not None:
        _definir_pedido(request, last_user.content if last_user else None)
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
        # Em bytes UTF-8: emoji e outras escritas gastam mais tokens por
        # caractere (estimar por caractere deixava a reserva curta).
        chars = sum(
            len(m.content.encode("utf-8")) if isinstance(m.content, str) else 0
            for m in request_body.messages or []
        )
        if settings.enabled:
            # Os documentos anexados entram no contexto: contam na reserva.
            chars += _caracteres_documentos()
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


def _evento_acoes(resposta: str, pedido: Any) -> Optional[str]:
    """Lê os blocos eden-acao da resposta e cria as ações pendentes."""
    from openjarvis.eden.acoes import propor

    if "eden-acao" not in resposta:
        return None
    if pedido is None or pedido.store is None:
        return None
    try:
        from openjarvis.eden.google import CACHE

        retrato = CACHE.retrato()
        criadas, recusadas = propor(
            resposta,
            pedido.store,
            pedido.espaco,
            get_settings().tz,
            conversa_id=pedido.conversa_id,
            agenda={
                "conectado": retrato["conectado"],
                "eventos": {e["id"]: e for e in retrato["eventos"]},
            },
        )
    except Exception:  # noqa: BLE001
        logger.exception("Éden: não consegui ler as ações da resposta")
        criadas, recusadas = [], ["não deu para ler as sugestões do Éden"]
    if not criadas and not recusadas:
        return None
    dados = json.dumps({"acoes": criadas, "recusadas": recusadas}, ensure_ascii=False)
    return f"event: eden_acoes\ndata: {dados}\n\n"


def _fim_do_streaming(pedaco: str, partes: list) -> bool:
    """Junta o texto dos pedaços e diz se este pedaço fecha a resposta."""
    fim = False
    for linha in pedaco.splitlines():
        if not linha.startswith("data: "):
            continue
        dado = linha[6:].strip()
        if dado == "[DONE]":
            fim = True
            continue
        try:
            obj = json.loads(dado)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        escolhas = obj.get("choices") or [{}]
        escolha = escolhas[0] if isinstance(escolhas[0], dict) else {}
        delta = escolha.get("delta") or {}
        conteudo = delta.get("content") if isinstance(delta, dict) else None
        if isinstance(conteudo, str):
            partes.append(conteudo)
        if escolha.get("finish_reason"):
            fim = True
    return fim


async def _com_acoes(corpo: AsyncIterator[Any], pedido: Any) -> AsyncIterator[Any]:
    """Repassa o streaming e, antes do pedaço final, manda as ações."""
    partes: list = []
    enviado = False
    async for pedaco in corpo:
        if not enviado:
            texto_pedaco = (
                pedaco.decode("utf-8", "replace")
                if isinstance(pedaco, (bytes, bytearray))
                else str(pedaco)
            )
            if _fim_do_streaming(texto_pedaco, partes):
                enviado = True
                evento = await asyncio.to_thread(_evento_acoes, "".join(partes), pedido)
                if evento:
                    yield evento
        yield pedaco


def finish_chat(
    response: Any, decision: Optional[RouteDecision], request_body: Any
) -> Any:
    """Anota o gasto das respostas sem streaming e marca qual IA respondeu."""
    if (
        get_settings().enabled
        and request_body.stream
        and isinstance(response, StreamingResponse)
    ):
        from openjarvis.eden.contexto import pedido_atual

        # O pedido (espaço, conversa) vai junto: o streaming roda depois.
        response.body_iterator = _com_acoes(response.body_iterator, pedido_atual())
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
