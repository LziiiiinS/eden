"""Éden: rotas da Google Agenda (só a volta do Google funciona sem a chave)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import google  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_google import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402

CHAVE = "oj_sk_teste_google"
AUTH = {"Authorization": f"Bearer {CHAVE}"}


class ClienteFalso:
    def __init__(self) -> None:
        self.ligado = False
        self.codigos = []
        self.revogar_falha = False
        self.cofre = object()
        self.drive = False

    def conectado(self):
        return self.ligado

    def trocar_codigo(self, codigo, verificador):
        self.codigos.append((codigo, verificador))
        self.ligado = True

    def desconectar(self, revogar=True):
        self.ligado = False
        self.revogou = revogar
        return not self.revogar_falha if revogar else False

    def listar(self, inicio, fim, tz):
        if not self.ligado:
            raise google.ErroGoogle("desligado", "eden_google_desconectado")
        return [
            {
                "id": "abc",
                "titulo": "Reunião",
                "local": "",
                "inicio": inicio.isoformat(),
                "fim": None,
                "dia_inteiro": False,
            }
        ]


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "123-abc.apps.googleusercontent.com")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "segredo")
    monkeypatch.setenv("EDEN_ENDERECO_CELULAR", "https://eden-notebook.tail1234.ts.net")
    app = FastAPI()
    store = Organizacao(tmp_path / "organizacao.db")
    app.state.eden_organizacao = store
    falso = ClienteFalso()
    app.state.eden_google = falso
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=CHAVE)
    monkeypatch.setattr(google, "tem_drive", lambda cofre: falso.drive)
    google.CACHE.limpar()
    yield TestClient(app, follow_redirects=False), falso
    google.CACHE.limpar()
    store.close()


def test_everything_but_the_return_needs_the_key(ambiente):
    c, _ = ambiente
    for metodo, caminho in (
        ("get", "/v1/eden/google/status"),
        ("post", "/v1/eden/google/conectar"),
        ("post", "/v1/eden/google/desconectar"),
        ("get", "/v1/eden/google/eventos"),
        ("post", "/v1/eden/google/atualizar"),
    ):
        assert getattr(c, metodo)(caminho).status_code == 401, caminho
    # A volta não pede a chave, mas sem um "state" válido não faz nada.
    r = c.get("/v1/eden/google/retorno?state=" + "x" * 40 + "&code=abc")
    assert r.status_code == 303
    assert r.headers["location"] == "/settings?google=expirou"


def test_connect_flow_with_state_and_pkce(ambiente):
    c, falso = ambiente
    status = c.get("/v1/eden/google/status", headers=AUTH).json()
    assert status == {
        "configurado": True,
        "conectado": False,
        "drive": False,
        "endereco_retorno": "https://eden-notebook.tail1234.ts.net/v1/eden/google/retorno",
        "atualizado_em": None,
    }
    r = c.post("/v1/eden/google/conectar", headers=AUTH)
    assert r.headers["cache-control"] == "no-store"
    url = urlparse(r.json()["url"])
    assert url.hostname == "accounts.google.com"
    q = parse_qs(url.query)
    state = q["state"][0]
    assert q["code_challenge_method"] == ["S256"]

    volta = c.get(f"/v1/eden/google/retorno?state={state}&code=codigo-1")
    assert volta.status_code == 303
    assert volta.headers["location"] == "/settings?google=conectado"
    assert falso.codigos[0][0] == "codigo-1"
    # O verificador do PKCE bate com o desafio mandado ao Google.
    assert google.desafio_pkce(falso.codigos[0][1]) == q["code_challenge"][0]
    # O mesmo state não vale de novo.
    de_novo = c.get(f"/v1/eden/google/retorno?state={state}&code=codigo-2")
    assert de_novo.headers["location"] == "/settings?google=expirou"
    assert len(falso.codigos) == 1

    assert c.get("/v1/eden/google/status", headers=AUTH).json()["conectado"] is True
    eventos = c.get("/v1/eden/google/eventos?dias=1", headers=AUTH).json()
    assert eventos["conectado"] is True and eventos["eventos"][0]["id"] == "abc"


def test_denied_on_google_screen(ambiente):
    c, falso = ambiente
    url = urlparse(c.post("/v1/eden/google/conectar", headers=AUTH).json()["url"])
    state = parse_qs(url.query)["state"][0]
    r = c.get(f"/v1/eden/google/retorno?state={state}&error=access_denied")
    assert r.headers["location"] == "/settings?google=negado"
    assert falso.codigos == []


def test_not_configured(ambiente, monkeypatch):
    c, _ = ambiente
    monkeypatch.delenv("GOOGLE_CLIENT_ID")
    assert c.get("/v1/eden/google/status", headers=AUTH).json()["configurado"] is False
    assert c.post("/v1/eden/google/conectar", headers=AUTH).status_code == 409
    eventos = c.get("/v1/eden/google/eventos", headers=AUTH).json()
    assert eventos == {"conectado": False, "eventos": []}


def test_disconnect_clears_cache(ambiente):
    c, falso = ambiente
    falso.ligado = True
    assert c.post("/v1/eden/google/atualizar", headers=AUTH).json()["conectado"] is True
    assert google.CACHE.retrato()["conectado"] is True
    assert c.post("/v1/eden/google/desconectar", headers=AUTH).json() == {
        "ok": True,
        "revogado": True,
        "motivo": None,
    }
    assert google.CACHE.retrato()["conectado"] is False
    assert c.get("/v1/eden/google/eventos?dias=99", headers=AUTH).status_code == 400


def test_disconnect_tells_when_google_did_not_confirm(ambiente):
    c, falso = ambiente
    falso.ligado = True
    falso.revogar_falha = True
    r = c.post("/v1/eden/google/desconectar", headers=AUTH).json()
    assert r == {"ok": True, "revogado": False, "motivo": None}
    assert falso.ligado is False


def test_disconnect_does_not_revoke_while_email_is_connected(ambiente, monkeypatch):
    from openjarvis.eden import routes_google

    c, falso = ambiente
    falso.ligado = True
    monkeypatch.setattr(routes_google, "_email_ligado", lambda request: True)
    r = c.post("/v1/eden/google/desconectar", headers=AUTH).json()
    assert r == {"ok": True, "revogado": False, "motivo": "email_ligado"}
    assert falso.revogou is False and falso.ligado is False


def test_connect_can_ask_for_drive_too(ambiente):
    c, _ = ambiente
    url = urlparse(
        c.post("/v1/eden/google/conectar?drive=true", headers=AUTH).json()["url"]
    )
    assert parse_qs(url.query)["scope"][0].split() == [
        google.ESCOPO_AGENDA,
        google.ESCOPO_DRIVE,
    ]


def test_save_to_drive_route(ambiente, monkeypatch):
    c, falso = ambiente
    falso.ligado = True
    falso.drive = True
    assert c.get("/v1/eden/google/status", headers=AUTH).json()["drive"] is True
    chamadas = []

    def salvar(cliente, titulo, html):
        chamadas.append((titulo, html))
        if not titulo:
            raise google.ErroGoogle("sem título", "eden_google_dados")
        return {"id": "arquivo123456", "nome": titulo, "link": None}

    monkeypatch.setattr(google, "salvar_no_drive", salvar)
    assert c.post("/v1/eden/google/drive/salvar", json={}).status_code == 401
    r = c.post(
        "/v1/eden/google/drive/salvar",
        headers=AUTH,
        json={"titulo": "Plano", "html": "<h1>Plano</h1>"},
    )
    assert r.json() == {
        "ok": True,
        "id": "arquivo123456",
        "nome": "Plano",
        "link": None,
    }
    ruim = c.post("/v1/eden/google/drive/salvar", headers=AUTH, json={"html": "x"})
    assert ruim.status_code == 400
    grande = c.post(
        "/v1/eden/google/drive/salvar",
        headers={**AUTH, "Content-Type": "application/json"},
        content=b"x" * (google.MAX_HTML_DRIVE + 70 * 1024),
    )
    assert grande.status_code == 413
