"""Éden: clima, vento e ondas (Open-Meteo falso; nada sai para a internet)."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

import pytest

from openjarvis.eden import clima
from openjarvis.eden.contexto import montar
from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao

TZ = timezone(timedelta(hours=-3))
AGORA = int(datetime(2026, 10, 17, 10, 0, tzinfo=TZ).timestamp() * 1000)
HOSTS = {
    "api.open-meteo.com",
    "marine-api.open-meteo.com",
    "geocoding-api.open-meteo.com",
}


class Resposta:
    def __init__(self, status: int, dados) -> None:
        self.status_code = status
        self._dados = dados
        self.content = json.dumps(dados).encode()

    def json(self):
        return self._dados


def _horas(n=72):
    inicio = datetime(2026, 10, 17, 0, 0)
    return [(inicio + timedelta(hours=i)).strftime("%Y-%m-%dT%H:%M") for i in range(n)]


class OpenMeteoFalso:
    def __init__(self) -> None:
        self.pedidos = []
        self.falhar_mar = False

    def get(self, url, params=None):
        assert urlparse(url).hostname in HOSTS, url
        self.pedidos.append((url, dict(params or {})))
        if url == clima.URL_BUSCA:
            return Resposta(
                200,
                {
                    "results": [
                        {
                            "name": "Florianópolis",
                            "latitude": -27.59667,
                            "longitude": -48.54917,
                            "admin1": "Santa Catarina",
                            "country": "Brasil",
                        },
                        {"name": "Ruim", "latitude": "x", "longitude": 1},
                    ]
                },
            )
        horas = _horas()
        if url == clima.URL_MAR:
            if self.falhar_mar:
                return Resposta(500, {})
            return Resposta(
                200,
                {
                    "hourly": {
                        "time": horas,
                        "wave_height": [1.5] * 72,
                        "wave_period": [9.0] * 72,
                        "wave_direction": [135.0] * 72,
                        "swell_wave_height": [1.2] * 72,
                        "swell_wave_period": [11.0] * 72,
                        "swell_wave_direction": [150.0] * 72,
                    }
                },
            )
        return Resposta(
            200,
            {
                "hourly": {
                    "time": horas,
                    "temperature_2m": [22.0] * 72,
                    "precipitation_probability": [30] * 72,
                    "precipitation": [0.2] * 72,
                    "weather_code": [61] * 72,
                    "wind_speed_10m": [27.8] * 71 + [float("nan")],
                    "wind_gusts_10m": [40.0] * 72,
                    "wind_direction_10m": [45.0] * 72,
                },
                "daily": {
                    "time": ["2026-10-17", "2026-10-18", "2026-10-19"],
                    "weather_code": [61, 0, 3],
                    "temperature_2m_max": [24.0, 26.0, 23.0],
                    "temperature_2m_min": [18.0, 19.0, 17.0],
                    "precipitation_sum": [3.2, 0.0, 1.0],
                    "precipitation_probability_max": [60, 5, 40],
                    "wind_speed_10m_max": [30.0, 20.0, 25.0],
                    "wind_gusts_10m_max": [45.0, 30.0, 35.0],
                    "wind_direction_10m_dominant": [135, 90, 180],
                },
            },
        )


@pytest.fixture
def store(tmp_path):
    s = Organizacao(tmp_path / "organizacao.db")
    clima.CACHE.limpar()
    yield s
    clima.CACHE.limpar()
    s.close()


@pytest.fixture
def falso():
    return OpenMeteoFalso()


def _cliente(falso):
    return clima.ClienteClima(http=falso, cache=clima.CACHE)


def test_starts_off_and_can_be_turned_on(store):
    assert clima.ligado(store) is False
    clima.definir_ligado(store, True)
    assert clima.ligado(store) is True


def test_places_are_validated(store):
    cidade = clima.criar_lugar(
        store, {"nome": "Florianópolis", "latitude": "-27,59667", "longitude": -48.5}
    )
    assert cidade["latitude"] == -27.5967 and cidade["principal"] is True
    praia = clima.criar_lugar(
        store,
        {"nome": "Praia Mole", "tipo": "praia", "latitude": -27.6, "longitude": -48.43},
    )
    assert praia["principal"] is False
    for ruim in (
        {"nome": "x", "latitude": 91, "longitude": 0},
        {"nome": "x", "latitude": 0, "longitude": "abc"},
        {"nome": "x", "latitude": float("nan"), "longitude": 0},
        {"nome": "x", "latitude": True, "longitude": 0},
        {"nome": "x", "tipo": "lua", "latitude": 0, "longitude": 0},
        {"nome": "", "latitude": 0, "longitude": 0},
    ):
        with pytest.raises(ErroOrganizacao):
            clima.criar_lugar(store, ruim)
    clima.tornar_principal(store, praia["id"])
    assert [lg["nome"] for lg in clima.listar_lugares(store)] == [
        "Praia Mole",
        "Florianópolis",
    ]
    assert clima.apagar_lugar(store, praia["id"]) is True
    assert clima.listar_lugares(store)[0]["principal"] is True


def test_limit_of_places(store, monkeypatch):
    monkeypatch.setattr(clima, "MAX_LUGARES", 1)
    clima.criar_lugar(store, {"nome": "A", "latitude": 0, "longitude": 0})
    with pytest.raises(ErroOrganizacao) as exc:
        clima.criar_lugar(store, {"nome": "B", "latitude": 0, "longitude": 0})
    assert exc.value.status == 409


def test_search_cleans_results(falso):
    resultados = _cliente(falso).buscar("Florianópolis")
    assert resultados == [
        {
            "nome": "Florianópolis",
            "regiao": "Santa Catarina, Brasil",
            "latitude": -27.5967,
            "longitude": -48.5492,
        }
    ]
    assert falso.pedidos[0][1]["name"] == "Florianópolis"


def test_forecast_for_a_beach_merges_wind_and_waves(store, falso):
    praia = clima.criar_lugar(
        store,
        {"nome": "Praia Mole", "tipo": "praia", "latitude": -27.6, "longitude": -48.43},
    )
    cliente = _cliente(falso)
    previsao = cliente.previsao(praia)
    assert len(previsao["horas"]) == 72 and len(previsao["dias"]) == 3
    primeira = previsao["horas"][0]
    assert primeira["vento_kmh"] == 27.8 and primeira["ondas_m"] == 1.5
    assert previsao["horas"][-1]["vento_kmh"] is None  # NaN vira vazio
    assert previsao["mar"] is True and previsao["fonte"].startswith("Open-Meteo")
    # Só coordenadas vão para o Open-Meteo.
    params = falso.pedidos[0][1]
    assert set(params) == {
        "latitude",
        "longitude",
        "timezone",
        "forecast_days",
        "hourly",
        "daily",
    }
    # Cache: a segunda vez não chama de novo.
    cliente.previsao(praia)
    assert len(falso.pedidos) == 2
    cliente.previsao(praia, forcar=True)
    assert len(falso.pedidos) == 4


def test_city_skips_the_sea_and_sea_failure_is_not_fatal(store, falso):
    cidade = clima.criar_lugar(store, {"nome": "Centro", "latitude": 0, "longitude": 0})
    _cliente(falso).previsao(cidade)
    assert [u for u, _ in falso.pedidos] == [clima.URL_PREVISAO]
    falso.falhar_mar = True
    praia = clima.criar_lugar(
        store, {"nome": "P", "tipo": "praia", "latitude": 1, "longitude": 1}
    )
    previsao = _cliente(falso).previsao(praia)
    assert previsao["mar"] is False and previsao["horas"][0]["vento_kmh"] == 27.8


def test_network_failure_becomes_a_clear_error(store):
    class SemRede:
        def get(self, url, params=None):
            raise TimeoutError("demorou")

    cidade = clima.criar_lugar(store, {"nome": "C", "latitude": 0, "longitude": 0})
    with pytest.raises(clima.ErroClima) as exc:
        clima.ClienteClima(http=SemRede()).previsao(cidade)
    assert exc.value.codigo == "eden_clima_rede"


def test_bad_values_are_dropped():
    previsao = clima.montar_previsao(
        {
            "hourly": {
                "time": ["2026-10-17T00:00", "lixo\n", "2026-10-17T02:00"],
                "temperature_2m": ["30", True, 21.5],
            },
            "daily": {"time": "não é lista"},
        },
        None,
    )
    assert [h["hora"] for h in previsao["horas"]] == ["2026-10-17T00:00"]
    assert previsao["horas"][0]["temperatura"] is None
    assert previsao["dias"] == []


def test_texts():
    assert clima.rumo(0) == "N" and clima.rumo(100) == "L" and clima.rumo(225) == "SO"
    assert clima.rumo(None) == "?"
    assert clima.nos(27.8) == 15
    assert clima.descricao(61) == "chuva fraca" and clima.descricao(None) == ""
    assert clima.pergunta_sobre_clima("Vai chover amanhã?")
    assert clima.pergunta_sobre_clima("Como estão as ONDAS na Praia Mole?")
    assert clima.pergunta_sobre_clima("previsão do vento pro kite")
    assert not clima.pergunta_sobre_clima("me ajuda com o orçamento do cliente")


def test_context_only_when_on_and_asked(store, falso):
    praia = clima.criar_lugar(
        store,
        {"nome": "Praia Mole", "tipo": "praia", "latitude": -27.6, "longitude": -48.43},
    )
    _cliente(falso).previsao(praia)
    pergunta = "vai ter onda amanhã?"
    desligado = clima.secao_contexto(store, pergunta)
    assert "Desligado" in desligado and "Não invente" in desligado
    clima.definir_ligado(store, True)
    _cliente(falso).previsao(praia)
    texto = clima.secao_contexto(store, pergunta)
    assert '### "Praia Mole" (praia)' in texto
    assert "ondas 1,5 m 9 s de SE" in texto and "vento 15 nós" in texto
    assert "chuva fraca" in texto
    assert clima.secao_contexto(store, "resuma esse contrato") == ""
    completo = montar(store, "pessoal", TZ, AGORA, pergunta=pergunta)
    assert "## Clima" in completo
    assert "## Clima" not in montar(store, "pessoal", TZ, AGORA, pergunta="oi")


def test_turning_off_clears_the_cache(store, falso):
    clima.definir_ligado(store, True)
    cidade = clima.criar_lugar(store, {"nome": "C", "latitude": 0, "longitude": 0})
    _cliente(falso).previsao(cidade)
    assert clima.CACHE.pegar(cidade, 60) is not None
    clima.definir_ligado(store, False)
    assert clima.CACHE.pegar(cidade, 60) is None
    assert clima.atualizar_todos(store, _cliente(falso)) == 0
