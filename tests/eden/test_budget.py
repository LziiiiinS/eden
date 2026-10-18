"""Éden: testes do limite de gastos."""

import sqlite3
from datetime import datetime, timezone

import pytest

from openjarvis.eden.budget import (
    BudgetExceeded,
    SpendingLedger,
    estimate_tokens,
    month_key,
)
from openjarvis.eden.settings import EdenSettings, settings_from_dict


def _ms(year, month, day, hour=12):
    return int(datetime(year, month, day, hour, tzinfo=timezone.utc).timestamp() * 1000)


@pytest.fixture
def ledger(tmp_path):
    led = SpendingLedger(tmp_path / "gastos.db")
    yield led
    led.close()


def test_blocks_when_month_spending_reaches_limit(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 1.0, "anthropic": 1.0})
    at = _ms(2026, 10, 13)
    ledger.check("openai", settings, 0.5, at_ms=at)
    ledger.record(
        provider="openai",
        model="gpt-6.1-sol",
        kind="conversa",
        cost_usd=0.9,
        settings=settings,
        at_ms=at,
    )
    ledger.check("openai", settings, 0.05, at_ms=at)
    with pytest.raises(BudgetExceeded) as err:
        ledger.check("openai", settings, 0.2, at_ms=at)
    assert "US$ 0.90 de US$ 1.00" in str(err.value)
    # A outra empresa tem o próprio limite.
    ledger.check("anthropic", settings, 0.5, at_ms=at)


def test_new_month_starts_from_zero_in_brasilia_time(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 1.0, "anthropic": 1.0})
    # 31/10 às 23h em Brasília = 01/11 às 02h UTC: ainda é outubro.
    end_of_october = _ms(2026, 11, 1, hour=2)
    assert month_key(settings, end_of_october) == "2026-10"
    ledger.record(
        provider="openai",
        model="m",
        kind="conversa",
        cost_usd=1.0,
        settings=settings,
        at_ms=end_of_october,
    )
    with pytest.raises(BudgetExceeded):
        ledger.check("openai", settings, 0.01, at_ms=end_of_october)
    ledger.check("openai", settings, 0.01, at_ms=_ms(2026, 11, 1, hour=4))


def test_zero_limit_turns_provider_off(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 0.0, "anthropic": 5.0})
    with pytest.raises(BudgetExceeded):
        ledger.check("openai", settings, 0.0001)


def test_untracked_provider_is_not_blocked(ledger):
    ledger.check("google", EdenSettings(), 100.0)


def test_summary(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 2.0, "anthropic": 3.0})
    at = _ms(2026, 10, 13)
    ledger.record(
        provider="anthropic",
        model="claude-sonnet-5-5",
        kind="conversa",
        cost_usd=3.0,
        settings=settings,
        at_ms=at,
    )
    summary = ledger.summary(settings, at_ms=at)
    assert summary["month"] == "2026-10"
    assert summary["providers"]["openai"]["spentUsd"] == 0
    assert summary["providers"]["anthropic"]["blocked"] is True


def test_prices_and_unknown_model_uses_most_expensive():
    settings = EdenSettings()
    assert settings.token_cost("openai", "gpt-6.1-sol", 1_000_000, 0) == 2.0
    assert settings.token_cost("anthropic", "claude-sonnet-5-5", 0, 1_000_000) == 10.0
    assert settings.token_price("openai", "gpt-desconhecido") == (10.0, 50.0)
    assert settings.token_price("anthropic", "claude-novo") == (4.0, 20.0)
    assert settings.transcription_cost("gpt-transcribe", 120) == pytest.approx(0.009)


def test_settings_from_config_section():
    settings = settings_from_dict(
        {
            "ias": {"dia_a_dia": "gpt-6-luna", "missao": "claude-opus-5-5"},
            "limites": {"openai": 3, "anthropic": 4.5},
            "precos": {"gpt-6-luna": [0.2, 0.6], "ruim": "x"},
            "precos_transcricao": {"gpt-transcribe": 0.005},
        }
    )
    assert settings.enabled is True
    assert settings.daily_model == "gpt-6-luna"
    assert settings.mission_model == "claude-opus-5-5"
    assert settings.monthly_limits_usd == {"openai": 3.0, "anthropic": 4.5}
    assert settings.prices["gpt-6-luna"] == (0.2, 0.6)
    assert "ruim" not in settings.prices
    assert settings.transcription_prices["gpt-transcribe"] == 0.005


def test_estimate_tokens_is_conservative():
    assert estimate_tokens(0) == 1
    assert estimate_tokens(300) == 100


def test_speech_budget_uses_reported_duration_then_client_then_size(tmp_path):
    from unittest.mock import MagicMock

    from openjarvis.eden import budget as budget_mod
    from openjarvis.eden import settings as settings_mod
    from openjarvis.eden import speech_budget

    cfg = EdenSettings(monthly_limits_usd={"openai": 1.0, "anthropic": 1.0})
    led = SpendingLedger(tmp_path / "voz.db")
    settings_mod.set_settings(cfg)
    budget_mod.set_ledger(led)
    try:
        backend = MagicMock()
        backend.backend_id = "openai"
        backend.model = "gpt-transcribe"
        assert speech_budget.tracked(backend)
        assert speech_budget.estimate_seconds(8000, None) == 2.0
        assert speech_budget.estimate_seconds(8000, 1500) == 1.5
        assert speech_budget.parse_client_ms("abc") is None
        speech_budget.check(backend, 8000, 1500)
        speech_budget.record(backend, 60.0, 8000, None)  # 1 min informado
        speech_budget.record(backend, 0.0, 999999, 120000)  # 2 min do app
        spent = led.summary(cfg)["providers"]["openai"]["spentUsd"]
        assert spent == pytest.approx(3 * 0.0045, abs=1e-4)
        # Limite 0 recusa antes de enviar o áudio.
        settings_mod.set_settings(
            EdenSettings(monthly_limits_usd={"openai": 0.0, "anthropic": 1.0})
        )
        with pytest.raises(BudgetExceeded):
            speech_budget.check(backend, 8000, None)
    finally:
        settings_mod.set_settings(None)
        budget_mod.set_ledger(None)
        led.close()


def test_env_overrides_limits_and_models():
    from openjarvis.eden.settings import apply_env_overrides

    settings = apply_env_overrides(
        EdenSettings(),
        {
            "EDEN_LIMITE_OPENAI": "7,5",
            "EDEN_LIMITE_ANTHROPIC": "abc",
            "EDEN_MODELO_DIA": "gpt-6-luna",
        },
    )
    assert settings.monthly_limits_usd["openai"] == 7.5
    assert settings.monthly_limits_usd["anthropic"] == 15.0
    assert settings.daily_model == "gpt-6-luna"
    assert settings.mission_model == "claude-sonnet-5-5"


def test_reservations_stop_simultaneous_requests_from_passing_the_limit(ledger):
    # Revisão de segurança (Codex, 15/10): dez pedidos de US$ 0,60 ao mesmo
    # tempo passavam todos contra um limite de US$ 1.
    settings = EdenSettings(monthly_limits_usd={"openai": 1.0, "anthropic": 1.0})
    first = ledger.reserve("openai", settings, 0.6)
    with pytest.raises(BudgetExceeded):
        ledger.reserve("openai", settings, 0.6)
    with pytest.raises(BudgetExceeded):
        ledger.check("openai", settings, 0.6)
    # Terminou de verdade gastando menos: a reserva vira o gasto real.
    ledger.record(
        provider="openai",
        model="gpt-6.1-sol",
        kind="conversa",
        cost_usd=0.1,
        settings=settings,
        reservation=first,
    )
    second = ledger.reserve("openai", settings, 0.6)
    ledger.release(second)
    ledger.reserve("openai", settings, 0.85)
    assert ledger.summary(settings)["providers"]["openai"]["spentUsd"] == 0.1


def test_speech_record_does_not_trust_a_tiny_client_duration(tmp_path):
    from openjarvis.eden import speech_budget

    # Áudio de 1,6 MB dizendo ter 1 ms: anota pelo menos 100 s (128 kbit/s).
    assert speech_budget.estimate_seconds(1_600_000, 1) >= 100
    # Para reservar, supõe áudio mais longo ainda (1 kbit/s).
    assert speech_budget.reserve_seconds(1_600_000, 1) == 12800


def test_audio_duration_is_read_from_the_file():
    """Revisão do Codex (18/10): a duração escrita no arquivo conta."""
    import struct

    from openjarvis.eden import speech_budget

    # WAV de 3 s (8 kHz, 16 bits, mono).
    dados = b"\x00" * (8000 * 2 * 3)
    wav = (
        b"RIFF"
        + struct.pack("<I", 36 + len(dados))
        + b"WAVE"
        + b"fmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, 8000, 16000, 2, 16)
        + b"data"
        + struct.pack("<I", len(dados))
        + dados
    )
    assert speech_budget.duracao_do_arquivo(wav) == 3.0
    # MP4 com mvhd dizendo 600 s (timescale 1000), arquivo pequeno.
    mvhd = (
        b"mvhd" + bytes([0, 0, 0, 0]) + b"\x00" * 8 + struct.pack(">II", 1000, 600_000)
    )
    mp4 = (
        b"\x00\x00\x00\x20ftypM4A "
        + b"\x00" * 16
        + struct.pack(">I", 8 + len(mvhd))
        + mvhd
    )
    assert speech_budget.duracao_do_arquivo(mp4) == 600.0
    assert speech_budget.reserve_seconds(len(mp4), 1, 600.0) >= 600
    assert speech_budget.estimate_seconds(len(mp4), 1, 600.0) >= 600
    assert speech_budget.duracao_do_arquivo(b"lixo") is None


def test_failed_record_keeps_the_cost_counted(tmp_path):
    """Revisão do Codex (18/10): se não der para anotar (disco cheio), o valor
    continua contando no limite; não libera a reserva sem anotar."""
    from openjarvis.eden import budget as b
    from openjarvis.eden.settings import EdenSettings

    settings = EdenSettings(enabled=True, monthly_limits_usd={"openai": 1.0})
    ledger = b.SpendingLedger(tmp_path / "gastos.db")
    r = ledger.reserve("openai", settings, 0.6)
    real = ledger._conn

    class DiscoCheio:
        def execute(self, sql, *args):
            if sql.lstrip().upper().startswith("INSERT"):
                raise sqlite3.OperationalError("database or disk is full")
            return real.execute(sql, *args)

        def commit(self):
            return real.commit()

    ledger._conn = DiscoCheio()
    try:
        ledger.record(
            provider="openai",
            model="m",
            kind="chat",
            cost_usd=0.8,
            settings=settings,
            reservation=r,
        )
    except Exception:
        pass
    else:
        raise AssertionError("devia avisar que não anotou")
    try:
        ledger.reserve("openai", settings, 0.3)
    except b.BudgetExceeded:
        pass
    else:
        raise AssertionError("a dívida não anotada devia contar no limite")
