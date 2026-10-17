"""Éden: rotas HTTP do Notion (Notion falso)."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import notion  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_notion import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_notion import CHAVE, PAI, NotionFalso  # noqa: E402

ACESSO = "oj_sk_teste_notion"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


@pytest.fixture
def ambiente(tmp_path):
    app = FastAPI()
    store = Organizacao(tmp_path / "organizacao.db")
    app.state.eden_organizacao = store
    falso = NotionFalso()
    app.state.eden_notion = notion.ClienteNotion(http=falso)
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app), falso, store
    store.close()


def test_needs_the_access_key(ambiente):
    c, falso, _ = ambiente
    assert c.get("/v1/eden/notion/status").status_code == 401
    assert c.post("/v1/eden/notion/salvar", json={}).status_code == 401
    assert falso.pedidos == []


def test_without_key_nothing_is_called(ambiente, monkeypatch):
    monkeypatch.delenv("NOTION_API_KEY", raising=False)
    c, falso, _ = ambiente
    status = c.get("/v1/eden/notion/status", headers=AUTH).json()
    assert status == {"configurado": False, "pai": None, "fonte": "Notion"}
    r = c.get("/v1/eden/notion/buscar?q=x", headers=AUTH)
    assert r.status_code == 409 and r.json()["code"] == "eden_notion_sem_chave"
    assert falso.pedidos == []
    assert CHAVE not in r.text


def test_search_choose_import_and_save(ambiente, monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", CHAVE)
    c, falso, _ = ambiente
    resultados = c.get("/v1/eden/notion/buscar?q=Éden", headers=AUTH).json()
    assert resultados["resultados"][0]["id"] == PAI

    r = c.post(
        "/v1/eden/notion/salvar", json={"titulo": "x", "markdown": "y"}, headers=AUTH
    )
    assert r.status_code == 409 and r.json()["code"] == "eden_notion_sem_pai"

    pai = c.post("/v1/eden/notion/pai", json={"id": PAI}, headers=AUTH).json()["pai"]
    assert pai["id"] == PAI
    status = c.get("/v1/eden/notion/status", headers=AUTH).json()
    assert status["configurado"] is True and status["pai"]["id"] == PAI

    doc = c.post(
        "/v1/eden/notion/importar", json={"id": PAI, "espaco": "pessoal"}, headers=AUTH
    ).json()["documento"]
    assert doc["nome"].endswith("(Notion).md")

    salvo = c.post(
        "/v1/eden/notion/salvar",
        json={"titulo": "Plano", "markdown": "# Plano\n\n- a"},
        headers=AUTH,
    )
    assert salvo.status_code == 200
    assert salvo.json()["pagina"]["titulo"] == "Plano"

    assert c.delete("/v1/eden/notion/pai", headers=AUTH).json() == {"pai": None}
    assert c.get("/v1/eden/notion/status", headers=AUTH).json()["pai"] is None


def test_bad_input(ambiente, monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", CHAVE)
    c, falso, _ = ambiente
    assert (
        c.post("/v1/eden/notion/pai", json={"id": "../x"}, headers=AUTH).status_code
        == 400
    )
    assert (
        c.post("/v1/eden/notion/importar", json={"id": PAI}, headers=AUTH).status_code
        == 400
    )
    r = c.post(
        "/v1/eden/notion/importar",
        json={"id": PAI, "espaco": "nao-existe"},
        headers=AUTH,
    )
    assert r.status_code == 400
    # Espaço errado nem chega a chamar o Notion.
    assert falso.pedidos == []


def test_page_not_shared_is_404(ambiente, monkeypatch):
    monkeypatch.setenv("NOTION_API_KEY", CHAVE)
    c, falso, _ = ambiente
    falso.status[f"/v1/pages/{PAI}"] = 404
    r = c.post("/v1/eden/notion/pai", json={"id": PAI}, headers=AUTH)
    assert r.status_code == 404 and r.json()["code"] == "eden_notion_404"
