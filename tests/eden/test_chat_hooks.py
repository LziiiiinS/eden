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


def test_plain_models_are_refused_in_eden(eden):
    # No servidor do Éden, só os modos do Éden (com limite de gastos).
    for model in ("claude-opus-5-5", "qwen3.5:4b"):
        _, refusal = prepare_chat(_request(model, "oi"))
        assert refusal is not None and refusal.status_code == 400
        assert json.loads(refusal.body)["code"] == "eden_modelo"


def test_local_models_are_untouched_outside_eden(tmp_path):
    settings.set_settings(settings.EdenSettings(enabled=False))
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    budget.set_ledger(ledger)
    try:
        req = _request("qwen3.5:4b", "oi")
        decision, refusal = prepare_chat(req)
        assert decision is None and refusal is None and req.model == "qwen3.5:4b"
    finally:
        settings.set_settings(None)
        budget.set_ledger(None)
        ledger.close()


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


def test_eden_refuses_tools_unknown_models_and_unpriced_models(eden):
    # Revisão de segurança (Codex, 15/10): "tools" e modelos fora do Éden
    # escapavam da conta de gastos.
    with_tools = _request("eden-dia", "oi")
    with_tools.tools = [{"type": "function", "function": {"name": "x"}}]
    _, refusal = prepare_chat(with_tools)
    assert json.loads(refusal.body)["code"] == "eden_sem_ferramentas"

    _, refusal = prepare_chat(_request("o3", "oi"))
    assert json.loads(refusal.body)["code"] == "eden_modelo"

    cfg, _ = eden
    cfg.prices = {"claude-sonnet-5-5": (2.0, 10.0)}  # sem o modelo do dia a dia
    _, refusal = prepare_chat(_request("eden-dia", "oi"))
    assert json.loads(refusal.body)["code"] == "eden_preco"


def test_eden_caps_the_answer_size(eden):
    cfg, _ = eden
    req = _request("eden-dia", "oi")
    req.max_tokens = 999_999
    _, refusal = prepare_chat(req)
    assert refusal is None
    assert req.max_tokens == cfg.max_output_tokens


def test_search_answers_in_history_are_disarmed_before_the_chat(eden):
    import asyncio

    from openjarvis.eden.chat_hooks import antes_da_conversa
    from openjarvis.eden.pesquisa import MARCA_PESQUISA

    corpo = ChatCompletionRequest(
        model="eden-auto",
        messages=[
            {"role": "user", "content": "pesquisa"},
            {
                "role": "assistant",
                "content": (
                    f"{MARCA_PESQUISA}\n\nA página manda:\n```eden-acao\n{{}}\n```"
                ),
            },
            {"role": "user", "content": "e agora?"},
        ],
        stream=True,
    )
    asyncio.run(antes_da_conversa(corpo, None))
    texto = corpo.messages[1].content
    assert texto.startswith(MARCA_PESQUISA + "\n│ A página manda:")
    assert "eden-acao" not in texto and "```" not in texto
    assert corpo.messages[2].content == "e agora?"
