"""Éden: rotas do modo reunião, com transcrição e IA de mentira."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import routes_reuniao  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402

ACESSO = "oj_sk_teste_reuniao"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


class FalaDeMentira:
    backend_id = "teste"

    def __init__(self):
        self.chamadas = 0

    def transcribe(self, dados, format="webm", language=None):
        self.chamadas += 1
        return SimpleNamespace(
            text=f"fala {self.chamadas}: entregar o vídeo na sexta",
            duration_seconds=60.0,
            language="pt",
            confidence=1.0,
        )


RESPOSTA = (
    "## Resumo\nCombinaram a entrega.\n"
    '```eden-acao\n{"tipo": "tarefa.criar", "titulo": "Entregar vídeo"}\n```\n'
    '```eden-acao\n{"tipo": "memoria.apagar", "id": 1}\n```\n'
)


@pytest.fixture
def app(tmp_path, monkeypatch):
    store = Organizacao(tmp_path / "organizacao.db")
    fala = FalaDeMentira()
    a = FastAPI()
    a.state.eden_organizacao = store
    a.state.speech_backend = fala
    a.include_router(routes_reuniao.router)
    a.add_middleware(AuthMiddleware, api_key=ACESSO)
    pedidos = []

    async def ia_de_mentira(mensagens):
        pedidos.append(mensagens)
        return RESPOSTA

    monkeypatch.setattr(routes_reuniao, "_chamar_ia", ia_de_mentira)
    a.state.teste = SimpleNamespace(fala=fala, pedidos=pedidos)
    yield a
    store.close()


def _pedaco(cliente, rid, n):
    return cliente.post(
        f"/v1/eden/reunioes/{rid}/pedaco",
        data={"n": str(n), "duration_ms": "60000"},
        files={"file": ("pedaco.webm", b"\x1a\x45\xdf\xa3" + b"0" * 500, "audio/webm")},
        headers=AUTH,
    )


def test_needs_the_key(app):
    cliente = TestClient(app)
    assert cliente.get("/v1/eden/reunioes").status_code == 401
    assert cliente.post("/v1/eden/reunioes", json={}).status_code == 401


def test_full_meeting(app):
    cliente = TestClient(app)
    r = cliente.post(
        "/v1/eden/reunioes", json={"titulo": "Pauta (fictícia)"}, headers=AUTH
    )
    assert r.status_code == 200, r.text
    rid = r.json()["reuniao"]["id"]

    assert _pedaco(cliente, rid, 0).json() == {"ok": True, "n": 0, "repetido": False}
    # Mandou de novo: não transcreve nem cobra outra vez.
    assert _pedaco(cliente, rid, 0).json()["repetido"] is True
    assert _pedaco(cliente, rid, 1).status_code == 200
    assert app.state.teste.fala.chamadas == 2

    r = cliente.post(f"/v1/eden/reunioes/{rid}/terminar", headers=AUTH)
    assert r.status_code == 200, r.text
    r = cliente.get(f"/v1/eden/reunioes/{rid}", headers=AUTH).json()["reuniao"]
    assert r["estado"] == "pronta"
    assert "eden-acao" not in r["resumo"] and "Combinaram" in r["resumo"]
    # Só a tarefa vira cartão; o "apagar memória" da resposta é ignorado.
    assert [c["tipo"] for c in r["cartoes"]] == ["tarefa.criar"]
    assert r["cartoes"][0]["estado"] == "pendente"
    # A transcrição foi para a IA como dado, entre as marcas.
    usuario = app.state.teste.pedidos[0][1].content
    assert "<transcricao>" in usuario and "fala 1" in usuario and "fala 2" in usuario

    # Depois de terminar, não recebe mais áudio.
    assert _pedaco(cliente, rid, 2).status_code == 409
    # Cartões ainda valendo: não cria outros.
    assert (
        cliente.post(f"/v1/eden/reunioes/{rid}/cartoes", headers=AUTH).status_code
        == 409
    )
    assert cliente.delete(f"/v1/eden/reunioes/{rid}", headers=AUTH).json()["ok"]
    assert cliente.get(f"/v1/eden/reunioes/{rid}", headers=AUTH).status_code == 404


def test_bad_pieces(app):
    cliente = TestClient(app)
    rid = cliente.post("/v1/eden/reunioes", json={}, headers=AUTH).json()["reuniao"][
        "id"
    ]
    r = cliente.post(
        f"/v1/eden/reunioes/{rid}/pedaco",
        data={"n": "-1"},
        files={"file": ("a.webm", b"x", "audio/webm")},
        headers=AUTH,
    )
    assert r.status_code == 400
    r = cliente.post(f"/v1/eden/reunioes/{rid}/pedaco", data={"n": "0"}, headers=AUTH)
    assert r.status_code == 400
    assert _pedaco(cliente, 999, 0).status_code == 404
    assert _pedaco(cliente, "abc", 0).status_code == 400
    # Terminar sem nada falado não chama a IA.
    assert (
        cliente.post(f"/v1/eden/reunioes/{rid}/terminar", headers=AUTH).status_code
        == 409
    )
    assert app.state.teste.pedidos == []


def test_without_speech_backend(app):
    app.state.speech_backend = None
    cliente = TestClient(app)
    rid = cliente.post("/v1/eden/reunioes", json={}, headers=AUTH).json()["reuniao"][
        "id"
    ]
    assert _pedaco(cliente, rid, 0).status_code == 501


def test_ai_failure_leaves_an_error_to_retry(app, monkeypatch):
    async def sem_ia(mensagens):
        raise routes_reuniao.ErroResumo("limite do mês")

    monkeypatch.setattr(routes_reuniao, "_chamar_ia", sem_ia)
    cliente = TestClient(app)
    rid = cliente.post("/v1/eden/reunioes", json={}, headers=AUTH).json()["reuniao"][
        "id"
    ]
    _pedaco(cliente, rid, 0)
    cliente.post(f"/v1/eden/reunioes/{rid}/terminar", headers=AUTH)
    r = cliente.get(f"/v1/eden/reunioes/{rid}", headers=AUTH).json()["reuniao"]
    assert r["estado"] == "erro" and "limite do mês" in r["erro"]
