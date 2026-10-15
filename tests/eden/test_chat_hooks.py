"""Éden: testes dos ganchos da rota de conversa (escolha da IA e limite)."""

import json

import pytest
from starlette.responses import JSONResponse, StreamingResponse

from openjarvis.eden import budget, settings
from openjarvis.eden.chat_hooks import finish_chat, prepare_chat
from openjarvis.server.models import (
    ChatCompletionRequest,
    ChatCompletionResponse,
    UsageInfo,
)


@pytest.fixture
def eden(tmp_path):
    cfg = settings.EdenSettings(
        enabled=True,
        daily_model="gpt-6.1-sol",
        mission_model="claude-sonnet-5-5",
        monthly_limits_usd={"openai": 10.0, "anthropic": 0.0},
    )
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    settings.set_settings(cfg)
    budget.set_ledger(ledger)
    yield cfg, ledger
    settings.set_settings(None)
    budget.set_ledger(None)
    ledger.close()


def _request(model, text, stream=True):
    return ChatCompletionRequest(
        model=model,
        messages=[{"role": "user", "content": text}],
        stream=stream,
    )


def test_auto_daily_goes_to_chatgpt(eden):
    req = _request("eden-auto", "bom dia! como vai?")
    decision, refusal = prepare_chat(req)
    assert refusal is None
    assert req.model == "gpt-6.1-sol"
    assert decision.headers()["X-Eden-Provider"] == "openai"


def test_mission_over_limit_is_refused_before_calling_claude(eden):
    req = _request("eden-auto", "/missao escreva uma proposta")
    decision, refusal = prepare_chat(req)
    assert req.model == "claude-sonnet-5-5"
    assert req.messages[0].content == "escreva uma proposta"
    assert isinstance(refusal, JSONResponse)
    assert refusal.status_code == 429
    body = json.loads(refusal.body)
    assert body["code"] == "eden_limite"
    assert "Claude" in body["detail"]
    assert refusal.headers["X-Eden-Mode"] == "missao"


def test_plain_models_are_also_limited(eden):
    _, refusal = prepare_chat(_request("claude-opus-5-5", "oi"))
    assert refusal is not None and refusal.status_code == 429


def test_local_models_are_untouched(eden):
    req = _request("qwen3.5:4b", "oi")
    decision, refusal = prepare_chat(req)
    assert decision is None and refusal is None and req.model == "qwen3.5:4b"


def test_stream_response_gets_route_headers(eden):
    req = _request("eden-dia", "escreva um contrato")
    decision, _ = prepare_chat(req)

    async def body():
        yield b"data: [DONE]\n\n"

    response = finish_chat(StreamingResponse(body()), decision, req)
    assert response.headers["X-Eden-Model"] == "gpt-6.1-sol"
    assert response.headers["X-Eden-Reason"] == "escolha"


def test_non_stream_request_is_refused_in_eden(eden):
    req = _request("eden-dia", "oi", stream=False)
    decision, refusal = prepare_chat(req)
    assert decision is None
    assert isinstance(refusal, JSONResponse)
    assert refusal.status_code == 400
    assert json.loads(refusal.body)["code"] == "eden_somente_streaming"


def test_non_stream_response_is_charged_and_tagged(eden):
    cfg, ledger = eden
    req = _request("eden-dia", "oi")
    decision, _ = prepare_chat(req)
    req.stream = False
    result = ChatCompletionResponse(
        model=req.model,
        usage=UsageInfo(prompt_tokens=1000, completion_tokens=100, total_tokens=1100),
    )
    response = finish_chat(result, decision, req)
    assert isinstance(response, JSONResponse)
    assert response.headers["X-Eden-Mode"] == "dia"
    spent = ledger.summary(cfg)["providers"]["openai"]["spentUsd"]
    assert spent == pytest.approx(0.003)
