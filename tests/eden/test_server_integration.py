"""Éden: testes da escolha de IA e do limite de gastos no servidor de verdade."""

from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import budget, settings  # noqa: E402
from openjarvis.server.app import create_app  # noqa: E402


def _config():
    from openjarvis.core.config import JarvisConfig

    cfg = JarvisConfig()
    cfg.analytics.enabled = False
    cfg.traces.enabled = False
    cfg.security.enabled = False
    cfg.agent.context_from_memory = False
    return cfg


@pytest.fixture
def eden(tmp_path):
    cfg = settings.EdenSettings(
        enabled=True,
        daily_model="gpt-6.1-sol",
        mission_model="claude-sonnet-5-5",
        monthly_limits_usd={"openai": 10.0, "anthropic": 0.0},
    )
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    settings.set_settings(cfg)
    budget.set_ledger(ledger)
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["qwen3.5:4b"]
    client = TestClient(create_app(engine, "qwen3.5:4b", config=_config()))
    yield client, ledger
    settings.set_settings(None)
    budget.set_ledger(None)
    ledger.close()


def test_models_list_starts_with_eden_modes(eden):
    client, _ = eden
    ids = [m["id"] for m in client.get("/v1/models").json()["data"]]
    assert ids[:3] == ["eden-auto", "eden-dia", "eden-missao"]
    assert "qwen3.5:4b" in ids


def test_chat_routes_daily_request_to_chatgpt(eden):
    client, _ = eden
    seen = {}

    async def fake_stream(model, messages, temperature, provider, **kwargs):
        seen.update(model=model, provider=provider)
        yield "Olá, Levi!"

    with patch("openjarvis.eden.providers.stream_eden", fake_stream):
        resp = client.post(
            "/v1/chat/completions",
            json={
                "model": "eden-auto",
                "messages": [{"role": "user", "content": "bom dia"}],
                "stream": True,
            },
        )
    assert resp.status_code == 200
    assert seen == {"model": "gpt-6.1-sol", "provider": "openai"}
    assert resp.headers["X-Eden-Provider"] == "openai"
    assert resp.headers["X-Eden-Mode"] == "dia"
    assert "Olá, Levi!" in resp.text


def test_chat_refuses_mission_when_claude_limit_is_reached(eden):
    client, _ = eden
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "eden-missao",
            "messages": [{"role": "user", "content": "faça uma proposta"}],
            "stream": True,
        },
    )
    assert resp.status_code == 429
    assert "Limite do mês do Claude" in resp.json()["detail"]
    assert resp.headers["X-Eden-Provider"] == "anthropic"


def test_spending_summary_route(eden):
    client, ledger = eden
    ledger.record(
        provider="openai",
        model="gpt-6.1-sol",
        kind="conversa",
        cost_usd=1.25,
        settings=settings.get_settings(),
    )
    data = client.get("/v1/eden/gastos").json()
    assert data["providers"]["openai"]["spentUsd"] == 1.25
    assert data["providers"]["openai"]["limitUsd"] == 10.0
    assert data["providers"]["anthropic"]["blocked"] is True
    assert data["models"] == {"dia": "gpt-6.1-sol", "missao": "claude-sonnet-5-5"}
