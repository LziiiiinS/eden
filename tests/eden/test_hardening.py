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
    client = TestClient(eden_app, base_url="http://localhost")
    assert client.get("/health").status_code == 200
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids[0] == "eden-auto"
    assert client.get("/v1/eden/gastos").status_code == 200
    assert client.get("/v1/eden/conversations").status_code == 200
    assert client.post("/v1/managed-agents", json={}).status_code in (404, 405)


def test_eden_server_answers_no_cross_origin_requests(eden_app):
    client = TestClient(eden_app, base_url="http://localhost")
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
    assert "/api/research" in paths
    assert "/api/digest" in paths


def test_eden_image_without_eden_config_refuses_to_start(monkeypatch):
    # Revisão de segurança (Codex, 15/10): a imagem ligada sem o iniciar do
    # Éden subiria o OpenJarvis completo.
    monkeypatch.setenv("EDEN_IMAGEM", "1")
    settings.set_settings(settings.EdenSettings(enabled=False))
    try:
        with pytest.raises(RuntimeError):
            create_app(_engine(), "qwen3.5:4b", config=_config())
    finally:
        settings.set_settings(None)


def test_eden_config_turns_off_conversation_traces():
    # Revisão de segurança (15/10): o registro técnico (traces.db) guardava
    # cada pergunta e resposta inteiras, fora do banco de conversas.
    from pathlib import Path

    from openjarvis.core.config import load_config

    caminho = Path(__file__).resolve().parents[2] / "eden" / "config.toml"
    cfg = load_config(caminho)
    assert cfg.traces.enabled is False
    assert cfg.agent_manager.enabled is False


def test_eden_server_refuses_huge_request_bodies(eden_app):
    client = TestClient(eden_app, base_url="http://localhost")
    grande = b"x" * (5 * 1024 * 1024)
    r = client.post(
        "/v1/chat/completions",
        content=grande,
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 413
    assert r.json()["code"] == "eden_grande_demais"

    # Sem Content-Length (enviado aos pedaços): também conta.
    def pedacos():
        for _ in range(5):
            yield b"x" * (1024 * 1024)

    r = client.post(
        "/v1/chat/completions",
        content=pedacos(),
        headers={"Content-Type": "application/json"},
    )
    # O FastAPI transforma o corte da leitura em "corpo inválido" (400).
    assert r.status_code in (400, 413)


def test_pairing_code_works_on_the_real_eden_server(tmp_path):
    """Servidor do Éden completo, com chave: o código troca pela chave e só a
    rota do código fica aberta sem a chave."""
    chave = "oj_sk_teste_servidor_completo"
    settings.set_settings(settings.EdenSettings(enabled=True))
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    budget.set_ledger(ledger)
    try:
        app = create_app(_engine(), "qwen3.5:4b", config=_config(), api_key=chave)
        app.state.eden_conversations = ConversationStore(tmp_path / "conversas.db")
        client = TestClient(app, base_url="http://localhost")
        auth = {"Authorization": f"Bearer {chave}"}
        assert client.get("/v1/eden/conversations").status_code == 401
        codigo = client.post("/v1/eden/pareamento", headers=auth).json()["codigo"]
        r = client.post("/v1/eden/pareamento/usar", json={"codigo": codigo})
        assert r.status_code == 200 and r.json() == {"chave": chave}
        # Um site de fora não recebe autorização para mandar o pedido.
        pre = client.options(
            "/v1/eden/pareamento/usar",
            headers={
                "Origin": "https://site-estranho.example",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert "access-control-allow-origin" not in pre.headers
    finally:
        settings.set_settings(None)
        budget.set_ledger(None)
        ledger.close()


def test_eden_server_hides_query_strings_in_the_access_log(eden_app):
    import logging

    from openjarvis.eden.hardening import ACCESS_LOGGER, SemConsultaNoRegistro

    assert any(
        isinstance(f, SemConsultaNoRegistro)
        for f in logging.getLogger(ACCESS_LOGGER).filters
    )


def test_eden_server_ignores_the_default_dev_origins(tmp_path):
    """O "jarvis serve" passa a lista padrão de origens do config (localhost
    3000/5173/5174, Tauri). No Éden nenhuma delas recebe autorização."""
    settings.set_settings(settings.EdenSettings(enabled=True))
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    budget.set_ledger(ledger)
    try:
        app = create_app(
            _engine(),
            "qwen3.5:4b",
            config=_config(),
            cors_origins=["http://localhost:5173", "tauri://localhost"],
        )
        client = TestClient(app, base_url="http://localhost")
        for origem in ("http://localhost:5173", "tauri://localhost"):
            res = client.options(
                "/v1/eden/pareamento/usar",
                headers={
                    "Origin": origem,
                    "Access-Control-Request-Method": "POST",
                    "Access-Control-Request-Headers": "content-type",
                },
            )
            assert "access-control-allow-origin" not in res.headers, origem
    finally:
        settings.set_settings(None)
        budget.set_ledger(None)
        ledger.close()


def test_eden_config_has_no_cors_origins():
    from pathlib import Path

    from openjarvis.core.config import tomllib

    raiz = Path(__file__).resolve().parents[2]
    cfg = tomllib.loads((raiz / "eden" / "config.toml").read_text(encoding="utf-8"))
    assert cfg["server"]["cors_origins"] == []


def test_pairing_route_body_limit_is_small():
    from openjarvis.eden.hardening import LimiteDeCorpo

    assert LimiteDeCorpo.limite("/v1/eden/pareamento/usar") == 1024


def test_eden_server_only_answers_its_own_addresses(eden_app):
    for host, esperado in (
        ("localhost:8000", 200),
        ("127.0.0.1:8000", 200),
        ("eden-notebook.tail1234.ts.net", 200),
        ("site-malicioso.example", 400),
        ("site-malicioso.example:8000", 400),
    ):
        client = TestClient(eden_app, base_url=f"http://{host}")
        assert client.get("/health").status_code == esperado, host
