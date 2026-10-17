"""Éden: rotas do clima (desligado não fala com o Open-Meteo)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import clima  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_clima import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_clima import OpenMeteoFalso  # noqa: E402

CHAVE = "oj_sk_teste_clima"
AUTH = {"Authorization": f"Bearer {CHAVE}"}


@pytest.fixture
def ambiente(tmp_path):
    app = FastAPI()
    store = Organizacao(tmp_path / "organizacao.db")
    app.state.eden_organizacao = store
    falso = OpenMeteoFalso()
    app.state.eden_clima = clima.ClienteClima(http=falso, cache=clima.CACHE)
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=CHAVE)
    clima.CACHE.limpar()
    yield TestClient(app), falso
    clima.CACHE.limpar()
    store.close()


def test_needs_the_key(ambiente):
    c, _ = ambiente
    assert c.get("/v1/eden/clima/status").status_code == 401
    assert c.post("/v1/eden/clima/ligar", json={"ligado": True}).status_code == 401


def test_off_means_no_calls_to_open_meteo(ambiente):
    c, falso = ambiente
    assert c.get("/v1/eden/clima/status", headers=AUTH).json()["ligado"] is False
    assert c.get("/v1/eden/clima/buscar?nome=Floripa", headers=AUTH).status_code == 409
    r = c.post(
        "/v1/eden/clima/lugares",
        headers=AUTH,
        json={"nome": "X", "latitude": 0, "longitude": 0},
    )
    assert r.status_code == 409
    assert falso.pedidos == []


def test_turn_on_add_place_and_get_forecast(ambiente):
    c, falso = ambiente
    assert (
        c.post("/v1/eden/clima/ligar", headers=AUTH, json={"ligado": "sim"}).status_code
        == 400
    )
    assert c.post(
        "/v1/eden/clima/ligar", headers=AUTH, json={"ligado": True}
    ).json() == {"ligado": True}
    busca = c.get("/v1/eden/clima/buscar?nome=Florianópolis", headers=AUTH).json()
    assert busca["resultados"][0]["nome"] == "Florianópolis"
    lugar = c.post(
        "/v1/eden/clima/lugares",
        headers=AUTH,
        json={
            "nome": "Praia Mole",
            "tipo": "praia",
            "latitude": -27.6,
            "longitude": -48.43,
        },
    ).json()["lugar"]
    previsao = c.get(f"/v1/eden/clima/previsao/{lugar['id']}", headers=AUTH).json()
    assert previsao["lugar"]["nome"] == "Praia Mole"
    assert previsao["mar"] is True and len(previsao["horas"]) == 72
    assert c.get("/v1/eden/clima/previsao/999", headers=AUTH).status_code == 404
    assert c.delete(f"/v1/eden/clima/lugares/{lugar['id']}", headers=AUTH).json() == {
        "ok": True
    }
    assert c.get("/v1/eden/clima/status", headers=AUTH).json()["lugares"] == []
