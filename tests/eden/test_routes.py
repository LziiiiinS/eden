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
    assert client.get("/v1/eden/conversations/c1").json()["conversation"]["messages"] == []


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
