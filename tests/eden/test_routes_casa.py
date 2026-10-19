"""Éden: rotas da casa (aparelhos de mentira; nada sai do computador)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import casa, tetos  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_casa import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402

ACESSO = "oj_sk_teste_casa"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


@pytest.fixture
def cliente(tmp_path, monkeypatch):
    for v in ("EDEN_CASA_URL", "EDEN_CASA_TOKEN", "EDEN_CASA_APARELHOS"):
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setenv("EDEN_CASA_DEMO", "1")
    tetos.zerar()
    with casa._demo_lock:
        casa._demo_estado.clear()
    store = Organizacao(tmp_path / "organizacao.db")
    app = FastAPI()
    app.state.eden_organizacao = store
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app)
    store.close()
    tetos.zerar()


def test_needs_the_access_key(cliente):
    assert cliente.get("/v1/eden/casa").status_code == 401
    r = cliente.post(
        "/v1/eden/casa/aparelho", json={"entidade": "light.sala_demo", "acao": "ligar"}
    )
    assert r.status_code == 401
    assert casa._demo_estado == {}


def test_off_without_configuration(cliente, monkeypatch):
    monkeypatch.delenv("EDEN_CASA_DEMO")
    r = cliente.get("/v1/eden/casa", headers=AUTH).json()
    assert r["ligada"] is False and r["aparelhos"] == [] and r["rotinas"] == []
    r = cliente.post(
        "/v1/eden/casa/aparelho",
        json={"entidade": "light.sala_demo", "acao": "ligar"},
        headers=AUTH,
    )
    assert r.status_code == 409


def test_demo_device_and_routine(cliente):
    r = cliente.get("/v1/eden/casa", headers=AUTH).json()
    assert r["ligada"] is True and r["demo"] is True
    assert [a["entidade"] for a in r["aparelhos"]] == [
        "light.sala_demo",
        "switch.computador_demo",
        "climate.ar_demo",
    ]
    feito = cliente.post(
        "/v1/eden/casa/aparelho",
        json={"entidade": "light.sala_demo", "acao": "cor", "valor": "azul"},
        headers=AUTH,
    )
    assert feito.status_code == 200, feito.text
    estados = cliente.get("/v1/eden/casa/estados", headers=AUTH).json()["estados"]
    assert estados[0] == {"entidade": "light.sala_demo", "estado": "on"}
    nova = cliente.post(
        "/v1/eden/casa/rotinas",
        json={
            "nome": "Chegando em casa",
            "passos": [
                {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": 20}
            ],
        },
        headers=AUTH,
    ).json()["rotina"]
    rodou = cliente.post(f"/v1/eden/casa/rotinas/{nova['id']}/rodar", headers=AUTH)
    assert rodou.json()["feitos"] == ["Ar-condicionado (demonstração) → 20 °C"]
    editada = cliente.patch(
        f"/v1/eden/casa/rotinas/{nova['id']}",
        json={
            "nome": "Saindo",
            "passos": [{"entidade": "light.sala_demo", "acao": "desligar"}],
        },
        headers=AUTH,
    )
    assert editada.json()["rotina"]["nome"] == "Saindo"
    assert cliente.delete(
        f"/v1/eden/casa/rotinas/{nova['id']}", headers=AUTH
    ).json() == {"ok": True}
    assert (
        cliente.post("/v1/eden/casa/rotinas/999/rodar", headers=AUTH).status_code == 404
    )


def test_rejects_devices_outside_the_list(cliente):
    for corpo in (
        {"entidade": "lock.porta", "acao": "ligar"},
        {"entidade": "light.sala_demo", "acao": "ligar", "url": "http://x"},
        {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": 50},
    ):
        r = cliente.post("/v1/eden/casa/aparelho", json=corpo, headers=AUTH)
        assert r.status_code == 400, corpo


def test_hourly_cap(cliente, monkeypatch):
    monkeypatch.setenv("EDEN_TETO_CASA_HORA", "2")
    tetos.zerar()
    corpo = {"entidade": "light.sala_demo", "acao": "ligar"}
    for _ in range(2):
        assert (
            cliente.post("/v1/eden/casa/aparelho", json=corpo, headers=AUTH).status_code
            == 200
        )
    r = cliente.post("/v1/eden/casa/aparelho", json=corpo, headers=AUTH)
    assert r.status_code == 429 and "casa" in r.json()["detail"]
