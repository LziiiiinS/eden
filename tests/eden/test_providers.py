"""Éden: testes da conversa com OpenAI/Anthropic e da anotação de gastos.

Usa um cliente HTTP falso: nenhum teste chama as empresas de verdade.
"""

import asyncio
import json

import pytest

from openjarvis.core.types import Message, Role
from openjarvis.eden.budget import BudgetExceeded, SpendingLedger
from openjarvis.eden.providers import (
    TRUNCATED_NOTE,
    ProviderError,
    build_anthropic_payload,
    build_openai_payload,
    explain_http_error,
    read_anthropic_event,
    read_openai_event,
    stream_eden,
)
from openjarvis.eden.settings import EdenSettings


class _FakeResponse:
    def __init__(self, status, lines, body=b""):
        self.status_code = status
        self._lines = lines
        self._body = body

    async def aread(self):
        return self._body

    async def aiter_lines(self):
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeClient:
    def __init__(self, response, sink):
        self._response = response
        self._sink = sink

    def stream(self, method, url, json=None, headers=None):
        self._sink.update(method=method, url=url, json=json, headers=headers)
        return self._response

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _sse(*events):
    lines = []
    for event in events:
        lines.append(f"event: {event.get('type', '')}")
        lines.append("data: " + json.dumps(event))
        lines.append("")
    return lines


def _messages():
    return [
        Message(role=Role.SYSTEM, content="Você é o Éden."),
        Message(role=Role.USER, content="Oi"),
        Message(role=Role.ASSISTANT, content="Olá!"),
        Message(role=Role.USER, content="Tudo bem?"),
    ]


def _collect(gen):
    async def run():
        return [token async for token in gen]

    return asyncio.run(run())


@pytest.fixture
def ledger(tmp_path):
    led = SpendingLedger(tmp_path / "gastos.db")
    yield led
    led.close()


def test_openai_payload_uses_responses_api_without_storing():
    payload = build_openai_payload("gpt-6.1-sol", _messages(), 8000, "low")
    assert payload["store"] is False and payload["stream"] is True
    assert payload["max_output_tokens"] == 8000
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["instructions"].startswith("Você é o Éden.")
    assert "gpt-6.1-sol" in payload["instructions"]
    assert [m["role"] for m in payload["input"]] == ["user", "assistant", "user"]
    assert "temperature" not in payload


def test_anthropic_payload():
    payload = build_anthropic_payload("claude-sonnet-5-5", _messages(), 8000, 1.7)
    assert payload["system"].startswith("Você é o Éden.")
    # Os modelos Claude atuais recusam "temperature" (erro 400).
    assert "temperature" not in payload
    assert payload["messages"][0] == {"role": "user", "content": "Oi"}


def test_read_openai_events():
    usage = {}
    assert (
        read_openai_event({"type": "response.output_text.delta", "delta": "Oi"}, usage)
        == "Oi"
    )
    done = {
        "type": "response.completed",
        "response": {"usage": {"input_tokens": 10, "output_tokens": 5}},
    }
    assert read_openai_event(done, usage) == ""
    assert usage == {"input_tokens": 10, "output_tokens": 5, "reported": 1}
    cut = {
        "type": "response.incomplete",
        "response": {
            "usage": {"input_tokens": 1, "output_tokens": 2},
            "incomplete_details": {"reason": "max_output_tokens"},
        },
    }
    assert read_openai_event(cut, usage) == TRUNCATED_NOTE
    with pytest.raises(ProviderError):
        read_openai_event({"type": "error", "message": "ruim"}, usage)


def test_read_anthropic_events():
    usage = {}
    start = {
        "type": "message_start",
        "message": {"usage": {"input_tokens": 7, "output_tokens": 1}},
    }
    read_anthropic_event(start, usage)
    text = {
        "type": "content_block_delta",
        "delta": {"type": "text_delta", "text": "Olá"},
    }
    assert read_anthropic_event(text, usage) == "Olá"
    end = {
        "type": "message_delta",
        "delta": {"stop_reason": "end_turn"},
        "usage": {"output_tokens": 40},
    }
    assert read_anthropic_event(end, usage) == ""
    assert usage["input_tokens"] == 7 and usage["output_tokens"] == 40


def test_http_errors_are_explained_in_portuguese():
    body = json.dumps({"error": {"message": "Incorrect API key"}}).encode()
    assert "chave da OpenAI foi recusada" in explain_http_error("openai", 401, body)
    quota = json.dumps(
        {"error": {"message": "You exceeded your current quota"}}
    ).encode()
    assert "crédito" in explain_http_error("openai", 429, quota)


def test_stream_records_reported_usage(ledger):
    settings = EdenSettings()
    sink = {}
    lines = _sse(
        {"type": "response.output_text.delta", "delta": "Tudo "},
        {"type": "response.output_text.delta", "delta": "ótimo!"},
        {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 1000, "output_tokens": 500}},
        },
    )
    tokens = _collect(
        stream_eden(
            "gpt-6.1-sol",
            _messages(),
            0.7,
            "openai",
            settings=settings,
            ledger=ledger,
            client_factory=lambda: _FakeClient(_FakeResponse(200, lines), sink),
            api_key="chave-de-teste",
        )
    )
    assert "".join(tokens) == "Tudo ótimo!"
    assert sink["url"].endswith("/v1/responses")
    assert sink["headers"]["Authorization"] == "Bearer chave-de-teste"
    month = ledger.summary(settings)["providers"]["openai"]
    # 1000 × US$ 2/M + 500 × US$ 10/M = US$ 0,007
    assert month["spentUsd"] == pytest.approx(0.007)


def test_stream_refuses_before_calling_when_over_limit(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 0.0, "anthropic": 1.0})
    called = {}

    def factory():
        called["yes"] = True
        raise AssertionError("não devia chamar a OpenAI")

    with pytest.raises(BudgetExceeded):
        _collect(
            stream_eden(
                "gpt-6.1-sol",
                _messages(),
                0.7,
                "openai",
                settings=settings,
                ledger=ledger,
                client_factory=factory,
                api_key="k",
            )
        )
    assert called == {}


def test_refused_request_is_not_charged(ledger):
    settings = EdenSettings()
    body = json.dumps({"error": {"message": "invalid x-api-key"}}).encode()
    with pytest.raises(ProviderError) as err:
        _collect(
            stream_eden(
                "claude-sonnet-5-5",
                _messages(),
                0.7,
                "anthropic",
                settings=settings,
                ledger=ledger,
                client_factory=lambda: _FakeClient(_FakeResponse(401, [], body), {}),
                api_key="k",
            )
        )
    assert "Anthropic" in str(err.value)
    assert ledger.summary(settings)["providers"]["anthropic"]["spentUsd"] == 0


def test_interrupted_stream_is_charged_by_estimate(ledger):
    settings = EdenSettings()
    lines = _sse(
        {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "x" * 300},
        }
    )

    async def take_first():
        gen = stream_eden(
            "claude-sonnet-5-5",
            _messages(),
            0.7,
            "anthropic",
            settings=settings,
            ledger=ledger,
            client_factory=lambda: _FakeClient(_FakeResponse(200, lines), {}),
            api_key="k",
        )
        first = await gen.__anext__()
        await gen.aclose()  # o usuário apertou "parar"
        return first

    assert asyncio.run(take_first()) == "x" * 300
    spent = ledger.summary(settings)["providers"]["anthropic"]["spentUsd"]
    assert spent > 0


def test_missing_key_explains_where_to_put_it(ledger):
    with pytest.raises(ProviderError) as err:
        _collect(
            stream_eden(
                "gpt-6.1-sol",
                _messages(),
                0.7,
                "openai",
                settings=EdenSettings(),
                ledger=ledger,
                api_key="",
            )
        )
    assert "OPENAI_API_KEY" in str(err.value)


def test_interrupted_claude_after_message_start_is_not_undercounted(ledger):
    # Revisão de segurança (Codex, 15/10): 18.000 caracteres recebidos eram
    # anotados como 1 token de saída quando o usuário parava a resposta.
    settings = EdenSettings()
    lines = _sse(
        {
            "type": "message_start",
            "message": {"usage": {"input_tokens": 7, "output_tokens": 1}},
        },
        {
            "type": "content_block_delta",
            "delta": {"type": "text_delta", "text": "x" * 18000},
        },
    )

    async def take_first():
        gen = stream_eden(
            "claude-sonnet-5-5",
            _messages(),
            0.7,
            "anthropic",
            settings=settings,
            ledger=ledger,
            client_factory=lambda: _FakeClient(_FakeResponse(200, lines), {}),
            api_key="k",
        )
        first = await gen.__anext__()
        await gen.aclose()
        return first

    asyncio.run(take_first())
    spent = ledger.summary(settings)["providers"]["anthropic"]["spentUsd"]
    # 7 de entrada + 6.000 de saída estimados a US$ 2/10 por 1M ≈ US$ 0,06.
    assert spent == pytest.approx(0.06, abs=0.001)


def test_refused_request_releases_its_reservation(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 1.0, "anthropic": 0.1})
    body = json.dumps({"error": {"message": "invalid x-api-key"}}).encode()
    with pytest.raises(ProviderError):
        _collect(
            stream_eden(
                "claude-sonnet-5-5",
                _messages(),
                0.7,
                "anthropic",
                settings=settings,
                ledger=ledger,
                client_factory=lambda: _FakeClient(_FakeResponse(401, [], body), {}),
                api_key="k",
            )
        )
    # Nada ficou preso: dá para reservar o limite inteiro de novo.
    ledger.release(ledger.reserve("anthropic", settings, 0.1))


def test_provider_errors_never_carry_keys():
    body = json.dumps(
        {"error": {"message": "Incorrect API key provided: sk-proj-abcd1234efgh5678"}}
    ).encode()
    text = str(ProviderError(explain_http_error("openai", 401, body)))
    assert "sk-proj-abcd1234efgh5678" not in text
    assert "chave da OpenAI foi recusada" in text
