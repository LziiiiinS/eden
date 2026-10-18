"""Éden (Parte 5): rotas do e-mail (Gmail falso)."""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("cryptography")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import gmail, google  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_email import router as email_router  # noqa: E402
from openjarvis.eden.routes_google import router as google_router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402
from tests.eden.test_gmail import GmailFalso  # noqa: E402
from tests.eden.test_google import CFG  # noqa: E402

ACESSO = "oj_sk_teste_email"
AUTH = {"Authorization": f"Bearer {ACESSO}"}


@pytest.fixture
def ambiente(tmp_path, monkeypatch):
    monkeypatch.setattr(google, "configuracao", lambda: CFG)
    gmail.CACHE.limpar()
    store = Organizacao(tmp_path / "organizacao.db")
    falso = GmailFalso()
    app = FastAPI()
    app.state.eden_organizacao = store
    app.state.eden_gmail = google.ClienteGoogle(
        gmail.CofreEmail(store, tmp_path / "eden" / "google.key"),
        CFG,
        http=falso,
        nome="E-mail (Gmail)",
    )
    app.include_router(email_router)
    app.include_router(google_router)
    app.add_middleware(AuthMiddleware, api_key=ACESSO)
    yield TestClient(app, follow_redirects=False), falso, store
    store.close()


def _conectar(c):
    url = c.post("/v1/eden/email/conectar", headers=AUTH).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert "gmail.readonly" in url and "calendar" not in url
    return c.get(f"/v1/eden/google/retorno?state={state}&code=codigo-ok")


def test_needs_the_access_key(ambiente):
    c, falso, _ = ambiente
    assert c.get("/v1/eden/email/status").status_code == 401
    assert c.get("/v1/eden/email/mensagens").status_code == 401
    assert falso.pedidos == []


def test_connect_list_read_import_disconnect(ambiente):
    c, falso, _ = ambiente
    assert c.get("/v1/eden/email/status", headers=AUTH).json()["conectado"] is False
    volta = _conectar(c)
    assert volta.status_code == 303
    assert volta.headers["location"] == "/settings?email=conectado"
    status = c.get("/v1/eden/email/status", headers=AUTH).json()
    assert status == {
        "configurado": True,
        "conectado": True,
        "conta": "eden.levi@gmail.com",
    }
    lista = c.get("/v1/eden/email/mensagens", headers=AUTH).json()["mensagens"]
    assert [m["id"] for m in lista] == ["m0000001", "m0000002"]
    lido = c.get("/v1/eden/email/mensagens/m0000001", headers=AUTH).json()["mensagem"]
    assert lido["texto"].startswith("Oi Levi")
    assert c.get("/v1/eden/email/mensagens/naoexiste1", headers=AUTH).status_code == 404
    doc = c.post(
        "/v1/eden/email/importar",
        json={"id": "m0000001", "espaco": "pessoal"},
        headers=AUTH,
    ).json()["documento"]
    assert doc["nome"].startswith("E-mail - ")
    r = c.post(
        "/v1/eden/email/importar", json={"id": "m0000001", "espaco": "x"}, headers=AUTH
    )
    assert r.status_code == 400
    assert c.post("/v1/eden/email/desconectar", headers=AUTH).json()["ok"] is True
    assert c.get("/v1/eden/email/status", headers=AUTH).json()["conectado"] is False
    # Só GET no Gmail: o Éden nunca manda nem apaga.
    assert all(p[0] in ("GET", "POST") for p in falso.pedidos)
    assert all(p[0] == "GET" for p in falso.pedidos if "gmail.googleapis.com" in p[1])


def test_email_connection_does_not_touch_the_calendar(ambiente, tmp_path):
    c, _, store = ambiente
    _conectar(c)
    agenda = google.Cofre(store, tmp_path / "eden" / "google.key")
    assert agenda.conectado() is False


def test_state_from_email_cannot_be_reused(ambiente):
    c, _, _ = ambiente
    url = c.post("/v1/eden/email/conectar", headers=AUTH).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    assert c.get(f"/v1/eden/google/retorno?state={state}&code=x").status_code == 303
    segunda = c.get(f"/v1/eden/google/retorno?state={state}&code=x")
    assert segunda.headers["location"] == "/settings?google=expirou"


def test_denied_goes_back_to_email(ambiente):
    c, _, _ = ambiente
    url = c.post("/v1/eden/email/conectar", headers=AUTH).json()["url"]
    state = parse_qs(urlparse(url).query)["state"][0]
    r = c.get(f"/v1/eden/google/retorno?state={state}&error=access_denied")
    assert r.headers["location"] == "/settings?email=negado"


def test_without_google_config(ambiente, monkeypatch):
    c, _, _ = ambiente
    monkeypatch.setattr(google, "configuracao", lambda: None)
    assert c.get("/v1/eden/email/status", headers=AUTH).json()["configurado"] is False
    assert c.post("/v1/eden/email/conectar", headers=AUTH).status_code == 409
    assert c.get("/v1/eden/email/mensagens", headers=AUTH).json()["conectado"] is False


def test_disconnect_keeps_google_grant_when_calendar_is_connected(
    ambiente, monkeypatch
):
    from openjarvis.eden import routes_email

    c, falso, _ = ambiente
    _conectar(c)
    monkeypatch.setattr(routes_email, "_agenda_ligada", lambda request: True)
    r = c.post("/v1/eden/email/desconectar", headers=AUTH).json()
    assert r == {"ok": True, "revogado": False, "motivo": "agenda_ligada"}
    assert not any(p[1] == google.URL_REVOGAR for p in falso.pedidos)
    assert c.get("/v1/eden/email/status", headers=AUTH).json()["conectado"] is False


def test_disconnect_revokes_when_alone(ambiente):
    c, falso, _ = ambiente
    _conectar(c)
    r = c.post("/v1/eden/email/desconectar", headers=AUTH).json()
    assert r["revogado"] is True and r["motivo"] is None
    assert any(p[1] == google.URL_REVOGAR for p in falso.pedidos)


def test_profile_failure_clears_the_old_address(ambiente, monkeypatch):
    c, _, store = ambiente
    _conectar(c)
    assert gmail.conta_guardada(store) == "eden.levi@gmail.com"

    def falha(cliente):
        raise google.ErroGoogle("sem resposta", "eden_google_rede")

    monkeypatch.setattr(gmail, "conta", falha)
    assert _conectar(c).headers["location"] == "/settings?email=conectado"
    assert gmail.conta_guardada(store) is None
