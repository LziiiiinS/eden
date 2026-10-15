"""Éden: conversa com o ChatGPT (OpenAI) e o Claude (Anthropic), com gasto anotado.

- OpenAI pela Responses API (a que os modelos GPT-6 usam), sem guardar a
  conversa na OpenAI (``store: false``).
- Anthropic pela Messages API.

Antes de cada pedido confere o limite do mês; no fim (mesmo se a resposta for
interrompida) anota o gasto com os tokens informados pela empresa, ou com uma
estimativa quando ela não informar.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator, Iterable
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from openjarvis.core.types import Message
from openjarvis.eden.budget import (
    SpendingLedger,
    estimate_tokens,
    get_ledger,
)
from openjarvis.eden.redact import redact_secrets
from openjarvis.eden.settings import EdenSettings, get_settings

logger = logging.getLogger(__name__)

OPENAI_URL = "https://api.openai.com/v1/responses"
ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
TRUNCATED_NOTE = "\n\n_(Resposta cortada no limite de tamanho do Éden.)_"


class ProviderError(Exception):
    """Erro vindo da OpenAI ou da Anthropic, explicado em português.

    A mensagem passa por redact_secrets: nada com cara de chave chega ao app
    nem aos registros do servidor.
    """

    def __init__(self, message: object = "") -> None:
        super().__init__(redact_secrets(message))


def _role(m: Message) -> str:
    return m.role.value if hasattr(m.role, "value") else str(m.role)


def split_system(messages: Sequence[Message]) -> Tuple[str, List[Dict[str, str]]]:
    """Separa as instruções (system) das falas (user/assistant)."""
    system_parts: List[str] = []
    chat: List[Dict[str, str]] = []
    for m in messages:
        role = _role(m)
        content = m.content or ""
        if role == "system":
            if content:
                system_parts.append(content)
            continue
        chat.append(
            {"role": "assistant" if role == "assistant" else "user", "content": content}
        )
    return "\n\n".join(system_parts), chat


def model_note(model: str, provider: str) -> str:
    label = "ChatGPT (OpenAI)" if provider == "openai" else "Claude (Anthropic)"
    return f"[Éden] Nesta resposta você está rodando no modelo {model}, do {label}."


def build_openai_payload(
    model: str,
    messages: Sequence[Message],
    max_output_tokens: int,
    reasoning_effort: str = "",
) -> Dict[str, Any]:
    instructions, chat = split_system(messages)
    note = model_note(model, "openai")
    payload: Dict[str, Any] = {
        "model": model,
        "input": chat,
        "instructions": f"{instructions}\n\n{note}" if instructions else note,
        "stream": True,
        "store": False,
        "max_output_tokens": max_output_tokens,
    }
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    return payload


def build_anthropic_payload(
    model: str,
    messages: Sequence[Message],
    max_tokens: int,
    temperature: Optional[float],
) -> Dict[str, Any]:
    system, chat = split_system(messages)
    note = model_note(model, "anthropic")
    payload: Dict[str, Any] = {
        "model": model,
        "messages": chat,
        "max_tokens": max_tokens,
        "stream": True,
        "system": f"{system}\n\n{note}" if system else note,
    }
    if temperature is not None:
        payload["temperature"] = max(0.0, min(1.0, float(temperature)))
    return payload


def _sse_data(lines: Iterable[str]) -> Iterable[Dict[str, Any]]:
    for line in lines:
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            obj = json.loads(data)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            yield obj


def read_openai_event(obj: Dict[str, Any], usage: Dict[str, int]) -> str:
    """Interpreta um evento da Responses API. Devolve o texto novo (ou "")."""
    kind = obj.get("type", "")
    if kind == "response.output_text.delta":
        delta = obj.get("delta")
        return delta if isinstance(delta, str) else ""
    if kind in ("response.completed", "response.incomplete"):
        response = obj.get("response") or {}
        u = response.get("usage") or {}
        usage["input_tokens"] = int(u.get("input_tokens") or 0)
        usage["output_tokens"] = int(u.get("output_tokens") or 0)
        usage["reported"] = 1
        if kind == "response.incomplete":
            reason = (response.get("incomplete_details") or {}).get("reason", "")
            if reason == "max_output_tokens":
                return TRUNCATED_NOTE
        return ""
    if kind == "response.failed":
        error = (obj.get("response") or {}).get("error") or {}
        raise ProviderError(
            f"A OpenAI não conseguiu responder: {error.get('message', 'erro')}"
        )
    if kind == "error":
        message = obj.get("message") or (obj.get("error") or {}).get("message")
        raise ProviderError(f"A OpenAI devolveu um erro: {message or 'sem detalhe'}")
    return ""


def read_anthropic_event(obj: Dict[str, Any], usage: Dict[str, int]) -> str:
    """Interpreta um evento da Messages API. Devolve o texto novo (ou "")."""
    kind = obj.get("type", "")
    if kind == "content_block_delta":
        delta = obj.get("delta") or {}
        if delta.get("type") in (None, "text_delta"):
            text = delta.get("text")
            return text if isinstance(text, str) else ""
        return ""
    if kind == "message_start":
        # Só a contagem inicial: a de saída de verdade vem no message_delta do
        # fim. Se a resposta for interrompida antes, o gasto é estimado.
        u = (obj.get("message") or {}).get("usage") or {}
        usage["input_tokens"] = (
            int(u.get("input_tokens") or 0)
            + int(u.get("cache_creation_input_tokens") or 0)
            + int(u.get("cache_read_input_tokens") or 0)
        )
        usage["output_tokens_start"] = int(u.get("output_tokens") or 0)
        usage["input_reported"] = 1
        return ""
    if kind == "message_delta":
        u = obj.get("usage") or {}
        if "output_tokens" in u:
            usage["output_tokens"] = int(u.get("output_tokens") or 0)
            usage["reported"] = 1
        if (obj.get("delta") or {}).get("stop_reason") == "max_tokens":
            return TRUNCATED_NOTE
        return ""
    if kind == "error":
        error = obj.get("error") or {}
        raise ProviderError(
            f"O Claude devolveu um erro: {error.get('message', 'sem detalhe')}"
        )
    return ""


def explain_http_error(provider: str, status: int, body: bytes) -> str:
    name = "OpenAI" if provider == "openai" else "Anthropic"
    detail = ""
    try:
        parsed = json.loads(body.decode("utf-8", "replace"))
        err = parsed.get("error") if isinstance(parsed, dict) else None
        if isinstance(err, dict):
            detail = str(err.get("message", ""))
        elif isinstance(err, str):
            detail = err
    except Exception:
        detail = ""
    if status == 401:
        text = f"A chave da {name} foi recusada. Confira a chave no servidor."
    elif status == 402 or (status == 429 and "quota" in detail.lower()):
        text = f"Acabou o crédito na {name}. Coloque crédito no site da {name}."
    elif status == 429:
        text = f"A {name} pediu para esperar um pouco (muitos pedidos). Tente de novo."
    elif status == 404:
        text = f"A {name} não encontrou o modelo. Confira o nome em [eden.ias]."
    elif status >= 500:
        text = f"A {name} está com problema agora (erro {status}). Tente de novo."
    else:
        text = f"A {name} recusou o pedido (erro {status})."
    return f"{text} Detalhe: {detail[:300]}" if detail else text


ClientFactory = Callable[[], Any]


def _default_client() -> Any:
    import httpx

    return httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0))


async def _post_stream(
    provider: str,
    url: str,
    headers: Dict[str, str],
    payload: Dict[str, Any],
    usage: Dict[str, int],
    client_factory: ClientFactory,
) -> AsyncIterator[str]:
    reader = read_openai_event if provider == "openai" else read_anthropic_event
    async with client_factory() as client:
        async with client.stream("POST", url, json=payload, headers=headers) as resp:
            if resp.status_code >= 400:
                body = await resp.aread()
                raise ProviderError(
                    explain_http_error(provider, resp.status_code, body)
                )
            usage["accepted"] = 1
            async for line in resp.aiter_lines():
                for obj in _sse_data([line]):
                    text = reader(obj, usage)
                    if text:
                        yield text


def _api_key(name: str) -> str:
    from openjarvis.server.cloud_router import _load_keys

    return _load_keys().get(name, "")


async def stream_eden(
    model: str,
    messages: Sequence[Message],
    temperature: Optional[float],
    provider: str,
    *,
    settings: Optional[EdenSettings] = None,
    ledger: Optional[SpendingLedger] = None,
    client_factory: ClientFactory = _default_client,
    api_key: Optional[str] = None,
) -> AsyncIterator[str]:
    """Responde com o modelo pedido, respeitando e anotando o limite de gastos."""
    settings = settings or get_settings()
    ledger = ledger or get_ledger()
    max_out = settings.max_output_tokens

    input_chars = sum(len(m.content or "") for m in messages)
    reserve = settings.token_cost(
        provider, model, estimate_tokens(input_chars), max_out
    )
    # Separa o valor máximo deste pedido (conferir + separar juntos, para
    # pedidos simultâneos de vários aparelhos não passarem do limite).
    reservation = ledger.reserve(provider, settings, reserve)
    try:
        url, headers, payload = _request_for(
            provider, model, messages, temperature, settings, max_out, api_key
        )
    except Exception:
        ledger.release(reservation)
        raise

    usage: Dict[str, int] = {}
    output_chars = 0
    try:
        async for text in _post_stream(
            provider, url, headers, payload, usage, client_factory
        ):
            output_chars += len(text)
            yield text
    finally:
        _record(
            ledger,
            settings,
            provider,
            model,
            usage,
            input_chars,
            output_chars,
            reservation,
        )


def _request_for(
    provider: str,
    model: str,
    messages: Sequence[Message],
    temperature: Optional[float],
    settings: EdenSettings,
    max_out: int,
    api_key: Optional[str],
) -> Tuple[str, Dict[str, str], Dict[str, Any]]:
    """Monta endereço, cabeçalhos e corpo do pedido para a empresa certa."""
    if provider == "openai":
        key = api_key if api_key is not None else _api_key("OPENAI_API_KEY")
        if not key:
            raise ProviderError(
                "A chave da OpenAI não está configurada no servidor (OPENAI_API_KEY)."
            )
        url = OPENAI_URL
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        payload = build_openai_payload(
            model, messages, max_out, settings.daily_reasoning_effort
        )
    elif provider == "anthropic":
        key = api_key if api_key is not None else _api_key("ANTHROPIC_API_KEY")
        if not key:
            raise ProviderError(
                "A chave da Anthropic não está configurada no servidor "
                "(ANTHROPIC_API_KEY)."
            )
        url = ANTHROPIC_URL
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }
        payload = build_anthropic_payload(model, messages, max_out, temperature)
    else:
        raise ProviderError(f"O Éden não conhece o provedor de {model!r}.")
    return url, headers, payload


def _record(
    ledger: SpendingLedger,
    settings: EdenSettings,
    provider: str,
    model: str,
    usage: Dict[str, int],
    input_chars: int,
    output_chars: int,
    reservation: Optional[str] = None,
) -> None:
    reported = bool(usage.get("reported"))
    if not reported and not usage.get("accepted"):
        # A empresa recusou ou nem recebeu o pedido: não há cobrança.
        ledger.release(reservation)
        return
    if reported:
        input_tokens = usage.get("input_tokens") or estimate_tokens(input_chars)
        output_tokens = usage.get("output_tokens", 0)
    else:
        # Sem a contagem final da empresa (resposta interrompida ou erro no
        # meio): usa a entrada informada, se houver, e estima a saída pelo
        # texto recebido — nunca menos do que a empresa já tinha informado.
        if usage.get("input_reported"):
            input_tokens = usage.get("input_tokens", 0)
        else:
            input_tokens = estimate_tokens(input_chars)
        estimated_out = estimate_tokens(output_chars) if output_chars else 0
        output_tokens = max(estimated_out, usage.get("output_tokens_start", 0))
    cost = settings.token_cost(provider, model, input_tokens, output_tokens)
    try:
        ledger.record(
            provider=provider,
            model=model,
            kind="conversa",
            cost_usd=cost,
            settings=settings,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            estimated=not reported,
            reservation=reservation,
        )
    except Exception:  # noqa: BLE001 — anotar o gasto nunca derruba a resposta
        logger.exception("Éden: falha ao anotar o gasto")
        ledger.release(reservation)
