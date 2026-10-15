"""Éden: testes das rotas de sincronização de conversas."""

import pytest

fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden.conversations import ConversationStore  # noqa: E402
from openjarvis.eden.routes import router  # noqa: E402


@pytest.fixture
def client(tmp_path):
    app = FastAPI()
    app.state.eden_conversations = ConversationStore(tmp_path / "conv.db")
    app.include_router(router)
    return TestClient(app)


def _body(updated=1000):
    return {
        "id": "c1",
        "title": "Teste",
        "model": "gpt-teste",
        "createdAt": 900,
        "updatedAt": updated,
        "messages": [{"id": "m1", "role": "user", "content": "Oi", "timestamp": 950}],
    }


def test_put_list_get_delete(client):
    r = client.put("/v1/eden/conversations/c1", json=_body())
    assert r.status_code == 200
    assert r.json()["conversation"]["updatedAt"] == 1000
    assert r.json()["serverHasMore"] is False
    assert "serverHasMore" not in r.json()["conversation"]

    listed = client.get("/v1/eden/conversations").json()
    assert [c["id"] for c in listed["conversations"]] == ["c1"]
    assert "serverTime" in listed

    full = client.get("/v1/eden/conversations/c1").json()["conversation"]
    assert full["messages"][0]["content"] == "Oi"

    deleted = client.delete("/v1/eden/conversations/c1", params={"deleted_at": 2000})
    assert deleted.json()["conversation"]["deleted"] is True
    assert (
        client.get("/v1/eden/conversations/c1").json()["conversation"]["messages"] == []
    )


def test_get_missing_returns_404(client):
    assert client.get("/v1/eden/conversations/nao-existe").status_code == 404


def test_bad_id_and_bad_body_return_400(client):
    assert client.put("/v1/eden/conversations/a.b", json=_body()).status_code == 400
    assert (
        client.put(
            "/v1/eden/conversations/c1",
            content=b"{nao e json",
            headers={"content-type": "application/json"},
        ).status_code
        == 400
    )
    bad = _body()
    bad["messages"][0]["role"] = "system"
    assert client.put("/v1/eden/conversations/c1", json=bad).status_code == 400


def test_eden_routes_require_api_key_when_configured(tmp_path):
    from openjarvis.server.auth_middleware import AuthMiddleware

    app = FastAPI()
    app.state.eden_conversations = ConversationStore(tmp_path / "conv.db")
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key="chave-de-teste")
    c = TestClient(app)
    assert c.get("/v1/eden/conversations").status_code == 401
    ok = c.get(
        "/v1/eden/conversations", headers={"Authorization": "Bearer chave-de-teste"}
    )
    assert ok.status_code == 200


def test_big_upload_without_length_is_refused(client):
    # Revisão de segurança (Codex, 15/10): sem Content-Length, o corpo era
    # lido inteiro na memória antes de conferir o limite.
    from openjarvis.eden.routes import MAX_BODY_BYTES

    def chunks():
        piece = b"x" * (1024 * 1024)
        for _ in range(MAX_BODY_BYTES // len(piece) + 2):
            yield piece

    r = client.put("/v1/eden/conversations/c1", content=chunks())
    assert r.status_code == 413


def test_phone_address_comes_only_from_a_tailscale_https_address(client, monkeypatch):
    monkeypatch.setenv(
        "EDEN_ENDERECO_CELULAR", "https://eden-notebook.tail1234.ts.net/"
    )
    assert client.get("/v1/eden/info").json() == {
        "endereco_celular": "https://eden-notebook.tail1234.ts.net"
    }
    for ruim in (
        "http://eden-notebook.tail1234.ts.net",
        "https://evil.example",
        "https://eden.ts.net.evil.example",
        "https://eden.tail1234.ts.net:4443",
        "",
    ):
        monkeypatch.setenv("EDEN_ENDERECO_CELULAR", ruim)
        assert client.get("/v1/eden/info").json() == {"endereco_celular": None}


# ── código curto para ligar um aparelho ─────────────────────────────────

CHAVE = "oj_sk_teste_do_pareamento_123"


def _app_com_chave(tmp_path, chave=CHAVE):
    from openjarvis.server.auth_middleware import AuthMiddleware

    app = FastAPI()
    app.state.api_key = chave
    app.state.eden_conversations = ConversationStore(tmp_path / "conv.db")
    app.include_router(router)
    if chave:
        app.add_middleware(AuthMiddleware, api_key=chave)
    return TestClient(app)


def test_pairing_code_gives_the_key_once(tmp_path):
    c = _app_com_chave(tmp_path)
    auth = {"Authorization": f"Bearer {CHAVE}"}
    # Criar o código exige a chave.
    assert c.post("/v1/eden/pareamento").status_code == 401
    criado = c.post("/v1/eden/pareamento", headers=auth)
    assert criado.status_code == 200
    assert criado.headers["cache-control"] == "no-store"
    codigo = criado.json()["codigo"]
    # O aparelho sem chave troca o código pela chave.
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": codigo.lower()})
    assert r.status_code == 200
    assert r.json() == {"chave": CHAVE}
    assert r.headers["cache-control"] == "no-store"
    # Uso único.
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": codigo})
    assert r.status_code == 400
    assert r.json()["code"] == "eden_codigo_invalido"
    assert CHAVE not in r.text


def test_pairing_only_opens_that_exact_route(tmp_path):
    c = _app_com_chave(tmp_path)
    # As outras rotas continuam exigindo a chave.
    assert c.get("/v1/eden/conversations").status_code == 401
    assert c.get("/v1/eden/info").status_code == 401
    assert c.delete("/v1/eden/pareamento").status_code == 401
    # Outro método ou caminho parecido também não passa.
    assert c.get("/v1/eden/pareamento/usar").status_code == 401
    assert c.post("/v1/eden/pareamento/usar/", json={}).status_code == 401
    assert c.post("/v1/eden/pareamento/usar2", json={}).status_code == 401


def test_pairing_requires_json_and_a_live_code(tmp_path):
    c = _app_com_chave(tmp_path)
    # Sem código ativo.
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": "ABCD-EFGH"})
    assert r.status_code == 400
    # Formulário ou texto puro (o que um site de fora conseguiria mandar).
    r = c.post(
        "/v1/eden/pareamento/usar",
        content=b'{"codigo":"ABCD-EFGH"}',
        headers={"Content-Type": "text/plain"},
    )
    assert r.status_code == 415
    r = c.post("/v1/eden/pareamento/usar", data={"codigo": "ABCD-EFGH"})
    assert r.status_code == 415
    r = c.post(
        "/v1/eden/pareamento/usar",
        content=b"{nao e json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400


def test_pairing_wrong_tries_and_rate_limit(tmp_path):
    from openjarvis.eden import pareamento

    c = _app_com_chave(tmp_path)
    auth = {"Authorization": f"Bearer {CHAVE}"}
    codigo = c.post("/v1/eden/pareamento", headers=auth).json()["codigo"]
    errado = "AAAA-AAAA" if codigo != "AAAA-AAAA" else "BBBB-BBBB"
    for _ in range(pareamento.MAX_ERROS_POR_CODIGO):
        c.post("/v1/eden/pareamento/usar", json={"codigo": errado})
    # Depois de 5 erros o código certo não vale mais.
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": codigo})
    assert r.status_code == 400
    for _ in range(pareamento.MAX_TENTATIVAS_POR_MINUTO):
        c.post("/v1/eden/pareamento/usar", json={"codigo": errado})
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": errado})
    assert r.status_code == 429
    assert r.headers["retry-after"] == "60"


def test_pairing_needs_a_server_key(tmp_path):
    c = _app_com_chave(tmp_path, chave="")
    assert c.post("/v1/eden/pareamento").status_code == 409
    r = c.post("/v1/eden/pareamento/usar", json={"codigo": "ABCD-EFGH"})
    assert r.status_code == 409
