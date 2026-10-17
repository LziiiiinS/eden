"""Éden: rotas e trânsito (TomTom falso; nada sai para a internet)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from urllib.parse import unquote, urlparse

import pytest

from openjarvis.eden import rotas
from openjarvis.eden.contexto import montar
from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao
from openjarvis.eden.redact import redact_secrets

TZ = timezone(timedelta(hours=-3))
AGORA = int(datetime(2026, 10, 17, 17, 0, tzinfo=TZ).timestamp() * 1000)
CHAVE = "abcDEF1234567890abcDEF1234567890"


class Resposta:
    def __init__(self, status: int, dados=None, bruto: bytes = None) -> None:
        self.status_code = status
        self.content = bruto if bruto is not None else json.dumps(dados or {}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def iter_bytes(self):
        yield self.content


class TomTomFalso:
    def __init__(self) -> None:
        self.pedidos = []
        self.geocode_vazio = False

    def stream(self, metodo, url, params=None, headers=None):
        assert metodo == "GET" and urlparse(url).hostname == "api.tomtom.com", url
        assert params["key"] == CHAVE
        self.pedidos.append((url, dict(params)))
        caminho = urlparse(url).path
        if caminho.startswith("/search/2/geocode/"):
            if self.geocode_vazio:
                return Resposta(200, {"results": []})
            return Resposta(
                200,
                {
                    "results": [
                        {
                            "type": "Point Address",
                            "address": {
                                "freeformAddress": "Av. das Américas, 500, Rio"
                            },
                            "position": {"lat": -23.0, "lon": -43.36},
                        },
                        {"position": {"lat": "x", "lon": 1}},
                    ]
                },
            )
        if caminho.startswith("/search/2/search/"):
            return Resposta(
                200,
                {
                    "results": [
                        {
                            "poi": {"name": "Praia da Barra"},
                            "address": {"freeformAddress": "Barra da Tijuca, Rio"},
                            "position": {"lat": -23.01, "lon": -43.37},
                        }
                    ]
                },
            )
        if caminho.startswith("/routing/1/calculateRoute/"):
            return Resposta(
                200,
                {
                    "routes": [
                        {
                            "summary": {
                                "lengthInMeters": 14200,
                                "travelTimeInSeconds": 1680,
                                "trafficDelayInSeconds": 480,
                                "noTrafficTravelTimeInSeconds": 1200,
                                "arrivalTime": "2026-10-17T17:28:00-03:00",
                            }
                        }
                    ]
                },
            )
        raise AssertionError(url)


@pytest.fixture
def store(tmp_path):
    s = Organizacao(tmp_path / "organizacao.db")
    rotas.CACHE.limpar()
    yield s
    rotas.CACHE.limpar()
    s.close()


@pytest.fixture
def com_chave(monkeypatch):
    monkeypatch.setenv("TOMTOM_API_KEY", CHAVE)


def _cliente(falso):
    return rotas.ClienteTomTom(http=falso, cache=rotas.CacheRotas())


def _trajeto(store):
    return rotas.criar_trajeto(
        store,
        {
            "origem": {"nome": "Casa", "latitude": -22.97, "longitude": -43.18},
            "destino": {"nome": "Trabalho", "latitude": "-23,0", "longitude": -43.36},
        },
    )


def test_key_comes_only_from_env(monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    assert rotas.configurado() is False
    monkeypatch.setenv("TOMTOM_API_KEY", "com espaço e ; estranho")
    assert rotas.configurado() is False
    monkeypatch.setenv("TOMTOM_API_KEY", CHAVE)
    assert rotas.configurado() is True


def test_without_key_nothing_goes_out(store, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    falso = TomTomFalso()
    with pytest.raises(rotas.ErroRotas) as exc:
        _cliente(falso).buscar("Av. das Américas")
    assert exc.value.codigo == "eden_rotas_sem_chave"
    assert falso.pedidos == []


def test_routes_are_validated(store):
    t = _trajeto(store)
    assert t["nome"] == "Casa → Trabalho" and t["destino"]["latitude"] == -23.0
    for ruim in (
        {
            "origem": {"nome": "A", "latitude": 91, "longitude": 0},
            "destino": t["destino"],
        },
        {"origem": "texto", "destino": t["destino"]},
        {
            "origem": {"nome": "", "latitude": 0, "longitude": 0},
            "destino": t["destino"],
        },
    ):
        with pytest.raises(ErroOrganizacao):
            rotas.criar_trajeto(store, ruim)
    assert [x["id"] for x in rotas.listar_trajetos(store)] == [t["id"]]
    assert rotas.apagar_trajeto(store, t["id"]) is True
    assert rotas.listar_trajetos(store) == []


def test_search_uses_geocode_then_places(store, com_chave):
    falso = TomTomFalso()
    cliente = _cliente(falso)
    resultados = cliente.buscar("Av. das Américas 500")
    assert resultados == [
        {
            "nome": "Av. das Américas, 500, Rio",
            "endereco": "Av. das Américas, 500, Rio",
            "latitude": -23.0,
            "longitude": -43.36,
        }
    ]
    assert unquote(urlparse(falso.pedidos[0][0]).path).endswith(
        "/geocode/Av. das Américas 500.json"
    )
    falso.geocode_vazio = True
    assert cliente.buscar("Praia da Barra")[0]["nome"] == "Praia da Barra"
    # A busca não vira caminho no endereço (barras e "?" são codificados).
    cliente.buscar("../../routing/1?x")
    assert (
        "/../" not in falso.pedidos[-1][0]
        and "?" not in urlparse(falso.pedidos[-1][0]).path
    )


def test_travel_time_with_traffic_and_cache(store, com_chave):
    falso = TomTomFalso()
    cliente = _cliente(falso)
    t = _trajeto(store)
    r = cliente.tempo(t)
    assert r["segundos"] == 1680 and r["atraso_s"] == 480 and r["metros"] == 14200
    url, params = falso.pedidos[0]
    assert "/calculateRoute/-22.970000,-43.180000:-23.000000,-43.360000/json" in url
    assert params["traffic"] == "true" and params["computeTravelTimeFor"] == "all"
    cliente.tempo(t)
    assert len(falso.pedidos) == 1  # guardado por 5 minutos
    cliente.tempo(t, forcar=True)
    assert len(falso.pedidos) == 2


def test_bad_answers_and_errors_never_show_the_key(store, com_chave, monkeypatch):
    monkeypatch.setattr(rotas.time, "sleep", lambda s: None)
    t = _trajeto(store)

    class Recusa:
        def __init__(self, status):
            self.status = status

        def stream(self, metodo, url, params=None, headers=None):
            return Resposta(self.status, {})

    for status, codigo in ((403, "eden_rotas_chave"), (429, "eden_rotas_limite")):
        with pytest.raises(rotas.ErroRotas) as exc:
            rotas.ClienteTomTom(http=Recusa(status), cache=rotas.CacheRotas()).tempo(t)
        assert exc.value.codigo == codigo and CHAVE not in str(exc.value)

    class Caiu:
        def stream(self, metodo, url, params=None, headers=None):
            raise ConnectionError(f"falhou {url}?key={params['key']}")

    with pytest.raises(rotas.ErroRotas) as exc:
        rotas.ClienteTomTom(http=Caiu(), cache=rotas.CacheRotas()).tempo(t)
    assert exc.value.codigo == "eden_rotas_rede" and CHAVE not in str(exc.value)
    assert exc.value.__cause__ is None  # o erro original (com a chave) não vai junto

    class SemCaminho:
        def stream(self, metodo, url, params=None, headers=None):
            return Resposta(200, {"routes": []})

    with pytest.raises(rotas.ErroRotas):
        rotas.ClienteTomTom(http=SemCaminho(), cache=rotas.CacheRotas()).tempo(t)


def test_httpx_log_lines_lose_the_key(caplog):
    registro = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        registro.info(
            'HTTP Request: %s %s "%s"',
            "GET",
            f"https://api.tomtom.com/routing/1/x/json?traffic=true&key={CHAVE}",
            "HTTP/1.1 200 OK",
        )
    assert CHAVE not in caplog.text and "key=…" in caplog.text
    assert CHAVE not in redact_secrets(f"https://api.tomtom.com/x?a=1&key={CHAVE}")


def test_context_only_when_asked_and_never_invents(store, monkeypatch):
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    pergunta = "quanto tempo até o trabalho agora com trânsito?"
    assert "Não invente" in rotas.secao_contexto(store, pergunta)
    monkeypatch.setenv("TOMTOM_API_KEY", CHAVE)
    assert "Nenhum trajeto" in rotas.secao_contexto(store, pergunta)
    t = _trajeto(store)
    falso = TomTomFalso()
    assert (
        rotas.atualizar_para_pergunta(store, pergunta, rotas.ClienteTomTom(http=falso))
        == 1
    )
    texto = rotas.secao_contexto(store, pergunta)
    assert '"Casa → Trabalho": 28 min agora' in texto
    assert "+8 min de trânsito" in texto and "14,2 km" in texto and "~17:28" in texto
    assert rotas.secao_contexto(store, "me ajuda com o orçamento") == ""
    assert (
        rotas.atualizar_para_pergunta(store, "oi", rotas.ClienteTomTom(http=falso)) == 0
    )
    completo = montar(store, "pessoal", TZ, AGORA, pergunta=pergunta)
    assert "## Trânsito agora" in completo
    assert t["id"]


def test_texts():
    assert rotas.minutos_texto(1680) == "28 min"
    assert rotas.minutos_texto(4000) == "1 h 07 min"
    assert rotas.minutos_texto(None) == "?"
    assert rotas.pergunta_sobre_rotas("Que horas eu saio pra chegar às 9?")
    assert rotas.pergunta_sobre_rotas("como está o TRÂNSITO na ponte")
    assert not rotas.pergunta_sobre_rotas("resume esse documento")
