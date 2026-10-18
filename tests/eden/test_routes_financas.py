"""Éden (Parte 5): rotas de contas e impostos (dados fictícios)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_financas import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402

ACESSO = "oj_sk_teste_contas"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


@pytest.fixture
def cliente(tmp_path):
    store = Organizacao(tmp_path / "organizacao.db")
    app = FastAPI()
    app.state.eden_organizacao = store
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app)
    store.close()


def test_needs_the_access_key(cliente):
    assert cliente.get("/v1/eden/contas").status_code == 401
    assert cliente.post("/v1/eden/contas", json={}).status_code == 401


def test_create_pay_reopen_delete(cliente):
    r = cliente.post(
        "/v1/eden/contas",
        json={
            "descricao": "Internet (fictícia)",
            "valor": "99,90",
            "vencimento": "2030-01-10",
            "repete": "mensal",
        },
        headers=AUTH,
    )
    assert r.status_code == 200, r.text
    conta = r.json()["conta"]
    assert conta["valor_centavos"] == 9990
    lista = cliente.get("/v1/eden/contas", headers=AUTH).json()["contas"]
    assert [c["id"] for c in lista] == [conta["id"]]
    pago = cliente.post(f"/v1/eden/contas/{conta['id']}/pagar", headers=AUTH).json()
    assert pago["conta"]["paga"] is True
    assert pago["proxima"]["vencimento"] == "2030-02-10"
    pagas = cliente.get("/v1/eden/contas?estado=pagas", headers=AUTH).json()
    assert [c["id"] for c in pagas["contas"]] == [conta["id"]]
    volta = cliente.post(f"/v1/eden/contas/{conta['id']}/reabrir", headers=AUTH)
    assert volta.json()["conta"]["paga"] is False
    assert volta.json()["proxima_removida"] is True
    editada = cliente.patch(
        f"/v1/eden/contas/{conta['id']}", json={"valor": "120"}, headers=AUTH
    ).json()["conta"]
    assert editada["valor_centavos"] == 12000
    assert (
        cliente.delete(f"/v1/eden/contas/{conta['id']}", headers=AUTH).json()["ok"]
        is True
    )
    assert (
        cliente.delete(f"/v1/eden/contas/{conta['id']}", headers=AUTH).status_code
        == 404
    )


def test_bad_input(cliente):
    r = cliente.post(
        "/v1/eden/contas",
        json={"descricao": "x", "valor": "abc", "vencimento": "2030-01-10"},
        headers=AUTH,
    )
    assert r.status_code == 400
    assert cliente.get("/v1/eden/contas?estado=x", headers=AUTH).status_code == 400
    assert cliente.get("/v1/eden/contas?espaco=nada", headers=AUTH).status_code == 400
    assert cliente.post("/v1/eden/contas/abc/pagar", headers=AUTH).status_code == 400
    assert cliente.post("/v1/eden/contas/999/pagar", headers=AUTH).status_code == 404


def test_summary(cliente):
    cliente.post(
        "/v1/eden/contas",
        json={"descricao": "Velha", "valor": "10", "vencimento": "2020-01-10"},
        headers=AUTH,
    )
    r = cliente.get("/v1/eden/contas/resumo", headers=AUTH).json()
    assert r["atrasadas"] == 1 and r["atrasado_a_pagar"] == 1000


def test_odd_input_is_400_not_500(cliente):
    for valor in ("1\u00a0500,00", "150.50"):
        r = cliente.post(
            "/v1/eden/contas",
            json={"descricao": "x", "valor": valor, "vencimento": "2030-01-10"},
            headers=AUTH,
        )
        assert r.status_code == 200, r.text
    r = cliente.post(
        "/v1/eden/contas",
        content=b'{"descricao": "x", "vencimento": "2030-01-10", "valor": '
        + b"9" * 400
        + b"}",
        headers={**AUTH, "Content-Type": "application/json"},
    )
    assert r.status_code == 400
    r = cliente.post("/v1/eden/contas/" + "9" * 30 + "/pagar", headers=AUTH)
    assert r.status_code in (400, 404)
