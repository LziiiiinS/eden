"""Éden: testes da escolha da IA (dia a dia x missão)."""

import pytest

from openjarvis.eden.routing import (
    AUTO,
    AUTO_IN_MISSION,
    DAILY,
    MISSION,
    MODE_DAILY,
    MODE_MISSION,
    classify,
    is_virtual,
    resolve,
    strip_command,
)
from openjarvis.eden.settings import EdenSettings


@pytest.mark.parametrize(
    "text",
    [
        "qual a previsão do tempo amanhã?",
        "me lembra de comprar pão",
        "o que é um contrato de aluguel?",
        "cria uma lista de compras pra semana",
        "quanto é 15% de 320?",
    ],
)
def test_everyday_requests_go_to_chatgpt(text):
    mode, _ = classify(text)
    assert mode == MODE_DAILY


@pytest.mark.parametrize(
    "text,reason",
    [
        ("Escreva uma proposta comercial para a LS Visuals", "entrega"),
        ("preciso de uma apresentação com 5 slides sobre o projeto", "entrega"),
        ("monta uma planilha de orçamento do casamento", "entrega"),
        ("revisa esse relatório e melhora o texto", "entrega"),
        ("responde esse cliente que reclamou do atraso", "cliente"),
        ("escreve um e-mail pro cliente pedindo o pagamento", "cliente"),
    ],
)
def test_deliverables_go_to_claude(text, reason):
    assert classify(text) == (MODE_MISSION, reason)


def test_long_request_is_a_mission():
    assert classify("a" * 1600) == (MODE_MISSION, "longo")


def test_commands_force_the_mode():
    assert classify("/missao me explica isso") == (MODE_MISSION, "comando")
    assert classify("/missão me explica isso") == (MODE_MISSION, "comando")
    assert classify("/dia escreva uma proposta") == (MODE_DAILY, "comando")


def test_conversation_in_mission_stays_with_claude():
    assert classify("deixa mais curto", in_mission=True) == (MODE_MISSION, "continua")
    assert classify("/dia e aí, tudo bem?", in_mission=True) == (MODE_DAILY, "comando")


def test_resolve_uses_configured_models():
    settings = EdenSettings(daily_model="gpt-x", mission_model="claude-y")
    daily = resolve(AUTO, "oi", settings)
    assert (daily.model, daily.provider, daily.mode) == ("gpt-x", "openai", "dia")
    mission = resolve(AUTO, "faça um contrato de prestação de serviço", settings)
    assert (mission.model, mission.provider) == ("claude-y", "anthropic")
    assert resolve(DAILY, "faça um contrato", settings).model == "gpt-x"
    assert resolve(MISSION, "oi", settings).model == "claude-y"
    assert resolve(AUTO_IN_MISSION, "ok", settings).reason == "continua"
    assert resolve("gpt-6.1-sol", "oi", settings) is None


def test_headers_are_ascii():
    decision = resolve(MISSION, "oi", EdenSettings())
    for value in decision.headers().values():
        value.encode("ascii")


def test_is_virtual_and_strip_command():
    assert is_virtual(AUTO) and is_virtual(AUTO_IN_MISSION)
    assert not is_virtual("claude-sonnet-5-5")
    assert strip_command("/missão  faça um plano") == "faça um plano"
    assert strip_command("sem comando") == "sem comando"
