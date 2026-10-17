"""Éden: resposta em voz (OpenAI falsa; nada sai para a internet)."""

from __future__ import annotations

import asyncio
import json

import pytest

from openjarvis.eden import voz
from openjarvis.eden.budget import BudgetExceeded, SpendingLedger
from openjarvis.eden.providers import ProviderError
from openjarvis.eden.settings import EdenSettings

MP3 = b"ID3" + b"\x00" * 200


class RespostaFalsa:
    def __init__(self, status=200, audio=MP3, corpo=b""):
        self.status_code = status
        self._audio = audio
        self._corpo = corpo

    async def aread(self):
        return self._corpo

    async def aiter_bytes(self):
        dados = self._corpo if self.status_code >= 400 else self._audio
        for i in range(0, len(dados), 64):
            yield dados[i : i + 64]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class OpenAIFalsa:
    def __init__(self, resposta=None):
        self.resposta = resposta or RespostaFalsa()
        self.pedidos = []

    def __call__(self):
        return self

    def stream(self, metodo, url, json=None, headers=None):
        self.pedidos.append(
            {"metodo": metodo, "url": url, "json": json, "headers": headers}
        )
        return self.resposta

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


@pytest.fixture
def ledger(tmp_path):
    led = SpendingLedger(tmp_path / "gastos.db")
    yield led
    led.close()


def gasto(ledger):
    return ledger._conn.execute(
        "SELECT COALESCE(SUM(cost_usd), 0), COUNT(*) FROM spending"
    ).fetchone()


def rodar(
    ledger, texto="Olá, Levi. Hoje vai chover à tarde.", falsa=None, settings=None
):
    falsa = falsa or OpenAIFalsa()
    audio = asyncio.run(
        voz.falar(
            texto,
            "marin",
            settings=settings or EdenSettings(),
            ledger=ledger,
            client_factory=falsa,
            api_key="sk-teste",
        )
    )
    return falsa, audio


def test_speech_request_and_cost(ledger):
    falsa, audio = rodar(ledger)
    assert audio == MP3
    pedido = falsa.pedidos[0]
    assert pedido["url"] == "https://api.openai.com/v1/audio/speech"
    corpo = pedido["json"]
    assert corpo["model"] == "gpt-4o-mini-tts" and corpo["voice"] == "marin"
    assert (
        corpo["response_format"] == "mp3"
        and "português do Brasil" in corpo["instructions"]
    )
    assert pedido["headers"]["Authorization"] == "Bearer sk-teste"
    total, linhas = gasto(ledger)
    texto = "Olá, Levi. Hoje vai chover à tarde."
    assert linhas == 1 and abs(total - len(texto) * 0.02 / 1000) < 1e-12
    kind = ledger._conn.execute("SELECT kind, estimated FROM spending").fetchone()
    assert tuple(kind) == ("voz", 1)


def test_refused_by_openai_costs_nothing(ledger):
    corpo = json.dumps({"error": {"message": "invalid voice"}}).encode()
    falsa = OpenAIFalsa(RespostaFalsa(400, corpo=corpo))
    with pytest.raises(ProviderError, match="invalid voice"):
        rodar(ledger, falsa=falsa)
    assert gasto(ledger) == (0, 0)


def test_big_or_empty_audio(ledger, monkeypatch):
    monkeypatch.setattr(voz, "MAX_AUDIO", 100)
    with pytest.raises(voz.ErroVoz):
        rodar(ledger)
    # Aceito pela OpenAI: anota o gasto mesmo assim.
    assert gasto(ledger)[1] == 1
    with pytest.raises(voz.ErroVoz):
        rodar(ledger, falsa=OpenAIFalsa(RespostaFalsa(audio=b"")))


def test_budget_blocks_before_calling(ledger):
    settings = EdenSettings(monthly_limits_usd={"openai": 0.0, "anthropic": 5.0})
    falsa = OpenAIFalsa()
    with pytest.raises(BudgetExceeded):
        rodar(ledger, falsa=falsa, settings=settings)
    assert falsa.pedidos == []


def test_without_key(ledger):
    falsa = OpenAIFalsa()
    with pytest.raises(voz.ErroVoz) as exc:
        asyncio.run(
            voz.falar(
                "oi",
                "marin",
                settings=EdenSettings(),
                ledger=ledger,
                client_factory=falsa,
                api_key="",
            )
        )
    assert exc.value.codigo == "eden_voz_sem_chave" and falsa.pedidos == []


@pytest.mark.parametrize(
    "valor, esperado",
    [
        ("  Olá,\n\n  tudo bem?  ", "Olá, tudo bem?"),
        ("oi \ud800", "oi ?"),
        ("a\x00b\x07c", "abc"),
    ],
)
def test_text_is_cleaned(valor, esperado):
    assert voz.limpar_texto(valor) == esperado


@pytest.mark.parametrize("valor", [None, "", "   ", 123, "x" * 1501])
def test_bad_text(valor):
    with pytest.raises(voz.ErroVoz):
        voz.limpar_texto(valor)


def test_voice_choice():
    assert voz.escolher_voz("cedar") == "cedar"
    assert voz.escolher_voz("../../x") == voz.VOZ_PADRAO
    assert voz.escolher_voz(None) == voz.VOZ_PADRAO


def test_hourly_cap():
    relogio = [0.0]
    teto = voz.TetoPorHora(
        max_caracteres=1000, max_pedidos=3, relogio=lambda: relogio[0]
    )
    assert teto.usar(600) and not teto.usar(500) and teto.usar(400)
    assert not teto.usar(1)  # 1000 caracteres
    relogio[0] = 3601
    assert teto.usar(900)
    teto2 = voz.TetoPorHora(max_caracteres=10**6, max_pedidos=2, relogio=lambda: 0.0)
    assert teto2.usar(1) and teto2.usar(1) and not teto2.usar(1)


def test_spoken_answers_rule_only_in_voice_mode(tmp_path):
    from datetime import timedelta, timezone

    from openjarvis.eden.contexto import REGRAS_ACOES, REGRAS_VOZ, montar
    from openjarvis.eden.organizacao import Organizacao

    store = Organizacao(tmp_path / "org.db")
    tz = timezone(timedelta(hours=-3))
    com = montar(store, "pessoal", tz, voz=True)
    sem = montar(store, "pessoal", tz)
    assert REGRAS_VOZ in com and REGRAS_VOZ not in sem
    # As regras ficam no fim, depois de tudo.
    assert com.index(REGRAS_VOZ) > com.index(REGRAS_ACOES)
    store.close()


def test_mp3_duration_and_real_cost():
    quadro = bytes([0xFF, 0xFB, 0x90, 0x00])  # MPEG-1 Layer III, 128 kbit/s
    um_segundo = quadro + b"\x00" * (16000 - 4)
    assert abs(voz.duracao_mp3(um_segundo) - 1.0) < 0.01
    com_id3 = b"ID3\x04\x00\x00\x00\x00\x00\x0a" + b"x" * 10 + um_segundo
    assert abs(voz.duracao_mp3(com_id3) - 1.0) < 0.01
    # Sem quadro reconhecível: supõe 32 kbit/s (duração maior, custo por cima).
    assert abs(voz.duracao_mp3(b"\x00" * 4000) - 1.0) < 0.01
    # 60 s de áudio para 10 caracteres: vale o custo por minuto (com folga).
    um_minuto = quadro + b"\x00" * (16000 * 60 - 4)
    assert abs(voz.custo_real_usd(10, um_minuto) - 0.015 * 1.2) < 1e-6
    assert voz.custo_real_usd(1000, quadro) == voz.custo_usd(1000)


def test_long_audio_is_charged_by_duration(ledger):
    quadro = bytes([0xFF, 0xFB, 0x90, 0x00])
    dois_minutos = quadro + b"\x00" * (16000 * 120 - 4)
    falsa = OpenAIFalsa(RespostaFalsa(audio=dois_minutos))
    rodar(ledger, texto="1234567890", falsa=falsa)
    total, _ = gasto(ledger)
    assert abs(total - 2 * 0.015 * 1.2) < 1e-6
