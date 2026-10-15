"""Éden: no servidor do Éden só ficam as rotas que o Éden usa."""

from unittest.mock import MagicMock

import pytest

pytest.importorskip("fastapi")

from fastapi.routing import APIRoute, APIWebSocketRoute  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import budget, settings  # noqa: E402
from openjarvis.eden.conversations import ConversationStore  # noqa: E402
from openjarvis.eden.hardening import is_allowed  # noqa: E402
from openjarvis.server.app import create_app  # noqa: E402


def _config():
    from openjarvis.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    return cfg


def _engine():
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["qwen3.5:4b"]
    return engine


@pytest.fixture
def eden_app(tmp_path):
    settings.set_settings(settings.EdenSettings(enabled=True))
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    budget.set_ledger(ledger)
    app = create_app(_engine(), "qwen3.5:4b", config=_config())
    app.state.eden_conversations = ConversationStore(tmp_path / "conversas.db")
    yield app
    settings.set_settings(None)
    budget.set_ledger(None)
    ledger.close()


@pytest.fixture
def plain_app():
    settings.set_settings(settings.EdenSettings(enabled=False))
    app = create_app(_engine(), "qwen3.5:4b", config=_config())
    yield app
    settings.set_settings(None)


def _paths(app):
    return {getattr(r, "path", "") for r in app.router.routes}


def test_is_allowed_only_eden_routes():
    assert is_allowed("/v1/chat/completions", {"POST"})
    assert is_allowed("/v1/eden/conversations/{conv_id}", {"PUT"})
    assert is_allowed("/health", {"GET"})
    assert not is_allowed("/v1/chat/completions", {"GET"})
    assert not is_allowed("/v1/managed-agents", {"POST"})
    assert not is_allowed("/v1/speech/synthesize", {"POST"})
    assert not is_allowed("/api/research", {"POST"})
    assert not is_allowed("/v1/cloud/reload", {"POST"})


def test_eden_server_drops_dangerous_inherited_routes(eden_app):
    paths = _paths(eden_app)
    for gone in (
        "/v1/managed-agents",
        "/v1/memory/index",
        "/v1/cloud/reload",
        "/api/research",
        "/v1/speech/synthesize",
        "/v1/tools",
        "/v1/connectors",
        "/openapi.json",
        "/docs",
        "/metrics",
    ):
        assert gone not in paths, gone
    assert not any(isinstance(r, APIWebSocketRoute) for r in eden_app.router.routes)
    assert all(
        isinstance(r, APIRoute)
        or getattr(r, "path", "").startswith("/assets")
        or getattr(r, "path", "") == "/{full_path:path}"
        for r in eden_app.router.routes
    )


def test_eden_server_keeps_what_the_app_uses(eden_app):
    client = TestClient(eden_app)
    assert client.get("/health").status_code == 200
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids[0] == "eden-auto"
    assert client.get("/v1/eden/gastos").status_code == 200
    assert client.get("/v1/eden/conversations").status_code == 200
    assert client.post("/v1/managed-agents", json={}).status_code in (404, 405)


def test_eden_server_answers_no_cross_origin_requests(eden_app):
    client = TestClient(eden_app)
    res = client.options(
        "/v1/models",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" not in {k.lower() for k in res.headers}


def test_plain_openjarvis_server_is_untouched(plain_app):
    paths = _paths(plain_app)
    assert "/v1/managed-agents" in paths
    assert "/api/research" in paths
