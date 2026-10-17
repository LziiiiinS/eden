"""Éden: rota HTTP da voz (OpenAI falsa)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import routes_voz, voz  # noqa: E402
from openjarvis.eden.budget import SpendingLedger  # noqa: E402
from openjarvis.eden.settings import EdenSettings  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_voz import MP3, OpenAIFalsa, RespostaFalsa  # noqa: E402

ACESSO = "oj_sk_teste_voz"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    ledger = SpendingLedger(tmp_path / "gastos.db")
    estado = {"chave": "sk-teste", "falsa": OpenAIFalsa(), "settings": EdenSettings()}
    monkeypatch.setattr(voz, "_chave", lambda: estado["chave"])
    monkeypatch.setattr(voz, "_cliente_padrao", lambda: estado["falsa"]())
    monkeypatch.setattr(voz, "get_ledger", lambda: ledger)
    monkeypatch.setattr(voz, "get_settings", lambda: estado["settings"])
    monkeypatch.setattr(routes_voz, "get_ledger", lambda: ledger)
    monkeypatch.setattr(routes_voz, "get_settings", lambda: estado["settings"])
    monkeypatch.setattr(voz, "TETO", voz.TetoPorHora())
    app = FastAPI()
    app.include_router(routes_voz.router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app), estado, ledger
    ledger.close()


def test_needs_the_access_key(ambiente):
    c, estado, _ = ambiente
    assert c.post("/v1/eden/voz", json={"texto": "oi"}).status_code == 401
    assert c.get("/v1/eden/voz/status").status_code == 401
    assert estado["falsa"].pedidos == []


def test_speaks_and_charges(ambiente):
    c, estado, ledger = ambiente
    r = c.post("/v1/eden/voz", json={"texto": "Bom dia!", "voz": "cedar"}, headers=AUTH)
    assert r.status_code == 200 and r.content == MP3
    assert r.headers["content-type"] == "audio/mpeg"
    assert r.headers["cache-control"] == "no-store"
    assert estado["falsa"].pedidos[0]["json"]["voice"] == "cedar"
    kind = ledger._conn.execute("SELECT kind FROM spending").fetchone()[0]
    assert kind == "voz"


def test_status(ambiente):
    c, estado, _ = ambiente
    dados = c.get("/v1/eden/voz/status", headers=AUTH).json()
    assert dados["available"] is True and "marin" in dados["vozes"]
    estado["chave"] = ""
    assert c.get("/v1/eden/voz/status", headers=AUTH).json()["available"] is False


def test_refusals_never_call_openai(ambiente, monkeypatch):
    c, estado, _ = ambiente
    assert c.post("/v1/eden/voz", json={}, headers=AUTH).status_code == 400
    grande = {"texto": "x" * 2000}
    assert c.post("/v1/eden/voz", json=grande, headers=AUTH).status_code == 413
    estado["chave"] = ""
    r = c.post("/v1/eden/voz", json={"texto": "oi"}, headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "eden_voz_sem_chave"
    estado["chave"] = "sk-teste"
    estado["settings"] = EdenSettings(
        monthly_limits_usd={"openai": 0.0, "anthropic": 5}
    )
    r = c.post("/v1/eden/voz", json={"texto": "oi"}, headers=AUTH)
    assert r.status_code == 429 and r.json()["code"] == "eden_limite"
    estado["settings"] = EdenSettings()
    monkeypatch.setattr(voz, "TETO", voz.TetoPorHora(max_caracteres=1))
    r = c.post("/v1/eden/voz", json={"texto": "oi"}, headers=AUTH)
    assert r.status_code == 429 and r.json()["code"] == "eden_voz_limite"
    assert estado["falsa"].pedidos == []


def test_openai_error_and_network_error(ambiente):
    c, estado, ledger = ambiente
    estado["falsa"] = OpenAIFalsa(
        RespostaFalsa(500, corpo=b'{"error": {"message": "boom"}}')
    )
    r = c.post("/v1/eden/voz", json={"texto": "oi"}, headers=AUTH)
    assert r.status_code == 502 and r.json()["code"] == "eden_voz_openai"

    class Quebrada:
        def __call__(self):
            raise RuntimeError("Authorization: Bearer sk-segredo")

    estado["falsa"] = Quebrada()
    r = c.post("/v1/eden/voz", json={"texto": "oi"}, headers=AUTH)
    assert r.status_code == 502 and "sk-segredo" not in r.text
    assert ledger._conn.execute("SELECT COUNT(*) FROM spending").fetchone()[0] == 0
