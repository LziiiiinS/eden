"""Éden: tetos por hora de conversa e transcrição (dados fictícios)."""

import json
from types import SimpleNamespace

import pytest

from openjarvis.eden import budget, settings, tetos
from openjarvis.eden.chat_hooks import prepare_chat, teto_da_conversa
from openjarvis.server.models import ChatCompletionRequest


def test_window_moves_with_the_clock():
    agora = [1000.0]
    teto = tetos.Teto(2, relogio=lambda: agora[0])
    assert teto.usar() and teto.usar()
    assert not teto.usar()
    agora[0] += 3599
    assert not teto.usar()
    agora[0] += 2
    assert teto.usar()


def test_zero_turns_the_cap_off():
    teto = tetos.Teto(0)
    assert all(teto.usar() for _ in range(50))


def test_limit_from_env(monkeypatch):
    monkeypatch.setenv("EDEN_TETO_CONVERSA_HORA", "7")
    assert tetos.limite_configurado("conversa") == 7
    for estranho in ("abc", "-3", " "):
        monkeypatch.setenv("EDEN_TETO_CONVERSA_HORA", estranho)
        assert tetos.limite_configurado("conversa") == tetos.PADROES["conversa"]
    monkeypatch.setenv("EDEN_TETO_CONVERSA_HORA", "999999999")
    assert tetos.limite_configurado("conversa") == tetos.MAXIMO
    monkeypatch.delenv("EDEN_TETO_CONVERSA_HORA")
    assert tetos.limite_configurado("transcricao") == 120


@pytest.fixture
def eden(tmp_path, monkeypatch):
    monkeypatch.setenv("EDEN_TETO_CONVERSA_HORA", "2")
    tetos.zerar()
    cfg = settings.EdenSettings(
        enabled=True,
        daily_model="gpt-6.1-sol",
        mission_model="claude-sonnet-5-5",
        monthly_limits_usd={"openai": 10.0, "anthropic": 0.0},
    )
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    settings.set_settings(cfg)
    budget.set_ledger(ledger)
    yield
    settings.set_settings(None)
    budget.set_ledger(None)
    ledger.close()
    tetos.zerar()


def _pedido(aparelho=None):
    return SimpleNamespace(state=SimpleNamespace(eden_aparelho=aparelho))


def test_chat_over_the_hourly_cap_is_refused(eden):
    assert teto_da_conversa(_pedido()) is None
    assert teto_da_conversa(_pedido()) is None
    recusa = teto_da_conversa(_pedido())
    assert recusa is not None and recusa.status_code == 429
    corpo = json.loads(recusa.body)
    assert corpo["code"] == "eden_teto_hora"
    assert "última hora" in corpo["detail"]


def test_each_device_has_its_own_count(eden):
    # Um celular (roubado, por exemplo) gasta o teto dele…
    assert teto_da_conversa(_pedido(3)) is None
    assert teto_da_conversa(_pedido(3)) is None
    assert teto_da_conversa(_pedido(3)) is not None
    # …e o notebook (chave principal) e os outros aparelhos continuam.
    assert teto_da_conversa(_pedido()) is None
    assert teto_da_conversa(_pedido(4)) is None


def test_outside_eden_there_is_no_cap(monkeypatch):
    monkeypatch.setenv("EDEN_TETO_CONVERSA_HORA", "1")
    tetos.zerar()
    settings.set_settings(settings.EdenSettings(enabled=False))
    try:
        for _ in range(3):
            assert teto_da_conversa(_pedido()) is None
            pedido = ChatCompletionRequest(
                model="qwen3:8b", messages=[{"role": "user", "content": "oi"}]
            )
            assert prepare_chat(pedido)[1] is None
    finally:
        settings.set_settings(None)


def test_device_of_the_request():
    assert tetos.aparelho_do_pedido(None) is None
    assert tetos.aparelho_do_pedido(_pedido()) is None
    assert tetos.aparelho_do_pedido(_pedido(7)) == 7
    assert tetos.aparelho_do_pedido(_pedido(True)) is None
