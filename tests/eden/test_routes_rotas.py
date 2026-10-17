"""Éden: rotas HTTP das rotas e do trânsito."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import rotas  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_rotas import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_rotas import CHAVE, TomTomFalso  # noqa: E402

ACESSO = "oj_sk_teste_rotas"
AUTH = {"Authorization": f"Bearer {ACESSO}"}
TRAJETO = {
    "nome": "Casa → Trabalho",
    "origem": {"nome": "Casa", "latitude": -22.97, "longitude": -43.18},
    "destino": {"nome": "Trabalho", "latitude": -23.0, "longitude": -43.36},
}


@pytest.fixture
def ambiente(tmp_path):
    app = FastAPI()
    store = Organizacao(tmp_path / "organizacao.db")
    app.state.eden_organizacao = store
    falso = TomTomFalso()
    app.state.eden_rotas = rotas.ClienteTomTom(http=falso, cache=rotas.CacheRotas())
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app), falso
    store.close()


def test_needs_the_access_key(ambiente):
    c, _ = ambiente
    assert c.get("/v1/eden/rotas/status").status_code == 401
    assert c.get("/v1/eden/rotas/tempos").status_code == 401


def test_without_tomtom_key_nothing_is_called(ambiente, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    c, falso = ambiente
    assert c.get("/v1/eden/rotas/status", headers=AUTH).json()["configurado"] is False
    assert c.get("/v1/eden/rotas/buscar?q=Barra", headers=AUTH).status_code == 409
    assert c.get("/v1/eden/rotas/tempos", headers=AUTH).json() == {
        "configurado": False,
        "tempos": [],
    }
    assert falso.pedidos == []


def test_save_route_and_get_times(ambiente, monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", CHAVE)
    c, falso = ambiente
    busca = c.get("/v1/eden/rotas/buscar?q=Av. das Américas", headers=AUTH).json()
    assert busca["resultados"][0]["latitude"] == -23.0
    t = c.post("/v1/eden/rotas/trajetos", headers=AUTH, json=TRAJETO).json()["trajeto"]
    tempos = c.get("/v1/eden/rotas/tempos", headers=AUTH).json()
    assert tempos["configurado"] is True
    assert tempos["tempos"][0]["segundos"] == 1680
    assert tempos["tempos"][0]["trajeto"]["nome"] == "Casa → Trabalho"
    assert c.delete(f"/v1/eden/rotas/trajetos/{t['id']}", headers=AUTH).json() == {
        "ok": True
    }
    assert (
        c.delete(f"/v1/eden/rotas/trajetos/{t['id']}", headers=AUTH).status_code == 404
    )


def test_alternatives_endpoint(ambiente, monkeypatch):
    c, falso = ambiente
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    r = c.get(
        "/v1/eden/rotas/caminhos?origem=-22.97,-43.18&destino=-23,-43.3", headers=AUTH
    )
    assert r.status_code == 409
    monkeypatch.setenv("TOMTOM_API_KEY", CHAVE)
    trajeto_id = c.post("/v1/eden/rotas/trajetos", json=TRAJETO, headers=AUTH).json()[
        "trajeto"
    ]["id"]
    dados = c.get(f"/v1/eden/rotas/caminhos?trajeto={trajeto_id}", headers=AUTH).json()
    assert [x["segundos"] for x in dados["rotas"]] == [1680, 1920, 2400]
    assert dados["rotas"][0]["vias"] == ["Avenida das Américas", "Avenida Ayrton Senna"]
    dados = c.get(
        "/v1/eden/rotas/caminhos?origem=-22.97,-43.18&destino=-23.01,-43.32",
        headers=AUTH,
    ).json()
    assert len(dados["rotas"]) == 3
    assert c.get("/v1/eden/rotas/caminhos?trajeto=999", headers=AUTH).status_code == 404
    for ruim in ("origem=abc&destino=1,1", "origem=91,0&destino=1,1", ""):
        assert c.get(f"/v1/eden/rotas/caminhos?{ruim}", headers=AUTH).status_code == 400
    assert c.get("/v1/eden/rotas/caminhos?trajeto=1").status_code == 401
