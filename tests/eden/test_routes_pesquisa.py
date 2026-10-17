"""Éden: rota HTTP da pesquisa na internet (Anthropic falsa)."""

from __future__ import annotations

import json

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import pesquisa, routes_pesquisa  # noqa: E402
from openjarvis.eden.budget import SpendingLedger  # noqa: E402
from openjarvis.eden.settings import EdenSettings  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_pesquisa import (  # noqa: E402
    BUSCA,
    INICIO,
    AnthropicFalsa,
    RespostaFalsa,
    citacao,
    fim,
    resultado,
    sse,
    texto,
)

ACESSO = "oj_sk_teste_pesquisa"
AUTH = {"Authorization": f"Bearer {ACESSO}"}
PERGUNTA = {
    "messages": [{"role": "user", "content": "Qual a previsão do Rock in Rio?"}]
}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    ledger = SpendingLedger(tmp_path / "gastos.db")
    settings = EdenSettings()
    linhas = sse(
        INICIO,
        BUSCA,
        resultado(("https://g1.globo.com/rock", "Rock in Rio | g1")),
        texto("O festival começa sexta."),
        citacao("https://g1.globo.com/rock", "Rock in Rio | g1"),
        fim(),
    )
    falsa = AnthropicFalsa(RespostaFalsa(200, linhas))
    estado = {"chave": "sk-ant-teste", "falsa": falsa, "settings": settings}
    monkeypatch.setattr(pesquisa, "_api_key", lambda nome: estado["chave"])
    monkeypatch.setattr(pesquisa, "_default_client", lambda: estado["falsa"]())
    monkeypatch.setattr(pesquisa, "get_ledger", lambda: ledger)
    monkeypatch.setattr(routes_pesquisa, "get_ledger", lambda: ledger)
    monkeypatch.setattr(routes_pesquisa, "get_settings", lambda: estado["settings"])
    monkeypatch.setattr(pesquisa, "LIMITE", pesquisa.LimitePorHora())
    app = FastAPI()
    app.include_router(routes_pesquisa.router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app), estado, ledger
    ledger.close()


def _conteudo(resposta) -> str:
    partes = []
    for linha in resposta.text.splitlines():
        if not linha.startswith("data: ") or linha == "data: [DONE]":
            continue
        dados = json.loads(linha[6:])
        partes.append(dados["choices"][0]["delta"].get("content") or "")
    return "".join(partes)


def test_needs_the_access_key(ambiente):
    c, estado, _ = ambiente
    assert c.post("/v1/eden/pesquisa", json=PERGUNTA).status_code == 401
    assert c.get("/v1/eden/pesquisa/status").status_code == 401
    assert estado["falsa"].pedidos == []


def test_search_streams_answer_with_sources(ambiente):
    c, estado, ledger = ambiente
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 200
    assert r.headers["x-eden-mode"] == "missao"
    assert r.headers["x-eden-provider"] == "anthropic"
    assert r.headers["x-eden-reason"] == "pesquisa"
    assert r.headers["cache-control"] == "no-store"
    conteudo = _conteudo(r)
    assert conteudo.startswith("O festival começa sexta.")
    assert "- [Rock in Rio  g1](https://g1.globo.com/rock)" in conteudo
    assert r.text.rstrip().endswith("data: [DONE]")
    assert len(estado["falsa"].pedidos) == 1
    kind = ledger._conn.execute("SELECT kind FROM spending").fetchone()[0]
    assert kind == "pesquisa"


def test_status(ambiente):
    c, estado, _ = ambiente
    dados = c.get("/v1/eden/pesquisa/status", headers=AUTH).json()
    assert dados["disponivel"] is True and dados["max_buscas"] == 3
    estado["chave"] = ""
    assert c.get("/v1/eden/pesquisa/status", headers=AUTH).json()["disponivel"] is False


def test_without_key_is_refused_before_calling(ambiente):
    c, estado, _ = ambiente
    estado["chave"] = ""
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "eden_pesquisa_sem_chave"
    assert estado["falsa"].pedidos == []


def test_non_claude_mission_model_is_refused(ambiente):
    c, estado, _ = ambiente
    estado["settings"] = EdenSettings(mission_model="gpt-6.1-sol")
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "eden_pesquisa_modelo"
    assert estado["falsa"].pedidos == []


def test_budget_limit_returns_429(ambiente):
    c, estado, _ = ambiente
    estado["settings"] = EdenSettings(
        monthly_limits_usd={"openai": 5.0, "anthropic": 0.01}
    )
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 429 and r.json()["code"] == "eden_limite"
    assert estado["falsa"].pedidos == []


def test_hourly_limit(ambiente, monkeypatch):
    c, estado, _ = ambiente
    monkeypatch.setattr(pesquisa, "LIMITE", pesquisa.LimitePorHora(maximo=1))
    assert c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH).status_code == 200
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 429 and r.json()["code"] == "eden_pesquisa_limite"
    assert len(estado["falsa"].pedidos) == 1


@pytest.mark.parametrize(
    "corpo",
    [
        {},
        {"messages": []},
        {"messages": "oi"},
        {"messages": [{"role": "assistant", "content": "só resposta"}]},
    ],
)
def test_bad_request(ambiente, corpo):
    c, estado, _ = ambiente
    r = c.post("/v1/eden/pesquisa", json=corpo, headers=AUTH)
    assert r.status_code == 400
    assert estado["falsa"].pedidos == []


def test_body_too_big(ambiente):
    c, _, _ = ambiente
    grande = {"messages": [{"role": "user", "content": "x" * 300_000}]}
    assert c.post("/v1/eden/pesquisa", json=grande, headers=AUTH).status_code == 413


def test_provider_error_becomes_text(ambiente):
    c, estado, ledger = ambiente
    corpo = json.dumps({"error": {"message": "Overloaded"}}).encode()
    estado["falsa"] = AnthropicFalsa(RespostaFalsa(529, [], corpo))
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    assert r.status_code == 200
    conteudo = _conteudo(r)
    assert "Não foi possível pesquisar" in conteudo and "Overloaded" in conteudo
    assert r.text.rstrip().endswith("data: [DONE]")
    total = ledger._conn.execute("SELECT COUNT(*) FROM spending").fetchone()[0]
    assert total == 0


def test_unexpected_error_hides_details(ambiente):
    c, estado, _ = ambiente

    class Quebrada:
        def __call__(self):
            raise RuntimeError("https://api.anthropic.com x-api-key=sk-ant-segredo")

    estado["falsa"] = Quebrada()
    r = c.post("/v1/eden/pesquisa", json=PERGUNTA, headers=AUTH)
    conteudo = _conteudo(r)
    assert "a conexão com a Anthropic falhou" in conteudo
    assert "sk-ant-segredo" not in r.text
