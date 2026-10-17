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


def _instr(metros, rua=None, tipo="TURN"):
    item = {"routeOffsetInMeters": metros, "instructionType": tipo}
    if rua is not None:
        item["street"] = rua
    return item


ROTAS_ALTERNATIVAS = [
    {  # pela Lúcio Costa (mais lento; vem primeiro de propósito)
        "summary": {
            "lengthInMeters": 15000,
            "travelTimeInSeconds": 1920,
            "trafficDelayInSeconds": 120,
            "arrivalTime": "2026-10-17T17:32:00-03:00",
        },
        "guidance": {
            "instructions": [
                _instr(0, "Rua de Casa", "LOCATION_DEPARTURE"),
                _instr(400, "Avenida Lúcio Costa"),
                _instr(12000, "Rua do Destino"),
                _instr(15000, tipo="LOCATION_ARRIVAL"),
            ]
        },
    },
    {  # pelas Américas (mais rápido)
        "summary": {
            "lengthInMeters": 14200,
            "travelTimeInSeconds": 1680,
            "trafficDelayInSeconds": 480,
            "noTrafficTravelTimeInSeconds": 1200,
            "arrivalTime": "2026-10-17T17:28:00-03:00",
        },
        "guidance": {
            "instructions": [
                _instr(0, "Rua de Casa", "LOCATION_DEPARTURE"),
                _instr(300, "Avenida das Américas"),
                _instr(9300, "Avenida Ayrton Senna"),
                _instr(13700, "Rua do Destino"),
                _instr(14200, tipo="LOCATION_ARRIVAL"),
            ]
        },
    },
    {  # sem instruções (vias vazias)
        "summary": {"lengthInMeters": 20000, "travelTimeInSeconds": 2400}
    },
    {"summary": {"lengthInMeters": 1}},  # sem tempo: ignorado
    "lixo",
]


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
        if caminho.startswith("/routing/1/calculateRoute/") and params.get(
            "maxAlternatives"
        ):
            return Resposta(200, {"routes": ROTAS_ALTERNATIVAS})
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


# ── caminhos (alternativas) ──────────────────────────────────────────────

CASA = {"nome": "Casa", "latitude": -22.97, "longitude": -43.18}
POSTO4 = {"nome": "Posto 4", "latitude": -23.012, "longitude": -43.32}


def test_alternatives_with_main_roads_and_cache(store, com_chave):
    falso = TomTomFalso()
    cliente = _cliente(falso)
    r = cliente.caminhos(CASA, POSTO4)
    assert [c["segundos"] for c in r["rotas"]] == [1680, 1920, 2400]
    assert r["rotas"][0]["vias"] == ["Avenida das Américas", "Avenida Ayrton Senna"]
    assert r["rotas"][1]["vias"] == ["Avenida Lúcio Costa", "Rua do Destino"]
    assert r["rotas"][2]["vias"] == []
    url, params = falso.pedidos[0]
    assert params["maxAlternatives"] == "2" and params["instructionsType"] == "text"
    assert params["language"] == "pt-BR" and params["traffic"] == "true"
    cliente.caminhos(CASA, POSTO4)
    assert len(falso.pedidos) == 1  # guardado por 5 minutos
    cliente.caminhos(CASA, POSTO4, forcar=True)
    assert len(falso.pedidos) == 2


def test_main_roads_ignore_short_and_bad_pieces():
    rota = {
        "summary": {"lengthInMeters": 10000},
        "guidance": {
            "instructions": [
                _instr(0, "Rua Curta"),
                _instr(200, "Avenida Longa"),
                _instr(7000, "  "),
                _instr(8000, None),
                {"routeOffsetInMeters": "x", "street": "Errada"},
                {**_instr(8500), "roadNumbers": ["RJ-071"]},
                _instr(10000, tipo="LOCATION_ARRIVAL"),
                "lixo",
            ]
        },
    }
    assert rotas.vias_principais(rota) == ["Avenida Longa", "RJ-071"]
    assert rotas.vias_principais({"summary": {}}) == []


@pytest.mark.parametrize(
    "pergunta, lugar",
    [
        (
            "Me dá a melhor rota para ir agora pro posto 4 da Barra da Tijuca "
            "que eu tinha salvo",
            "posto 4 da Barra da Tijuca",
        ),
        ("qual o melhor caminho para a praia da barra?", "praia da barra"),
        ("vou pra casa, qual caminho?", "casa"),
        ("rota até o Shopping Leblon pela Lúcio Costa", "Shopping Leblon"),
        ("qual o caminho mais rápido para chegar no Recreio", "Recreio"),
        ("como está o trânsito?", None),
        ("trânsito na Avenida Brasil", None),
        ("resume esse documento para o cliente", None),
        # Revisão: só pedido de caminho manda texto ao TomTom.
        ("quanto tempo leva pra curar uma gripe?", None),
        ("vou sair com a Ana hoje, me lembra de ligar pro João", None),
        ("melhor caminho pra casa da minha mãe", "casa da minha mãe"),
        ("rota pra minha casa", "casa"),
        ("como chego na Rua das Flores, 123?", "Rua das Flores, 123"),
    ],
)
def test_destination_from_question(pergunta, lugar):
    assert rotas.destino_da_pergunta(pergunta) == lugar


def test_saved_destination_uses_saved_points(store, com_chave):
    rotas.criar_trajeto(store, {"origem": CASA, "destino": POSTO4})
    falso = TomTomFalso()
    pergunta = "Me dá a melhor rota para ir agora pro posto 4 da Barra"
    r = rotas.preparar_caminhos(store, pergunta, _cliente(falso))
    assert r["origem"]["nome"] == "Casa" and r["destino"]["nome"] == "Posto 4"
    assert len(r["rotas"]) == 3
    assert all("/geocode/" not in u for u, _ in falso.pedidos)  # sem busca
    texto_ctx = rotas.secao_contexto(store, pergunta, r)
    assert "## Caminhos agora" in texto_ctx
    assert (
        '1) 28 min agora; +8 min de trânsito; 14,2 km; via "Avenida das Américas"'
        in (texto_ctx)
    )
    assert '"Avenida Lúcio Costa"' in texto_ctx and "mais rápido" in texto_ctx
    # Com a localização do aparelho, sai de lá.
    local = rotas.ler_local("-23.0001,-43.3655")
    r2 = rotas.preparar_caminhos(store, pergunta, _cliente(falso), local)
    assert r2["origem"]["nome"] == "sua localização agora"


def test_new_place_is_searched_near_the_origin(store, com_chave):
    _trajeto(store)  # Casa → Trabalho
    falso = TomTomFalso()
    r = rotas.preparar_caminhos(
        store, "qual o melhor caminho para a praia da barra?", _cliente(falso)
    )
    url, params = falso.pedidos[0]
    assert (
        "/geocode/" in url and params["lat"] == "-22.970" and params["lon"] == "-43.180"
    )
    assert r["origem"]["nome"] == "Casa"
    assert r["destino"]["endereco"] == "Av. das Américas, 500, Rio"
    assert len(r["rotas"]) == 3


def test_going_home_reverses_the_saved_route(store, com_chave):
    _trajeto(store)  # Casa → Trabalho
    r = rotas.preparar_caminhos(
        store, "vou pra casa, qual caminho?", _cliente(TomTomFalso())
    )
    assert r["destino"]["nome"] == "Casa" and r["origem"]["nome"] == "Trabalho"


def test_without_origin_or_key(store, com_chave, monkeypatch):
    falso = TomTomFalso()
    r = rotas.preparar_caminhos(store, "melhor rota pro Recreio agora", _cliente(falso))
    assert r["erro"] == "sem_origem"
    assert falso.pedidos == []  # sem partida, nem procura o lugar
    assert "usar minha localização" in rotas.secao_caminhos(r)
    monkeypatch.delenv("TOMTOM_API_KEY", raising=False)
    assert (
        rotas.preparar_caminhos(store, "melhor rota pro Recreio", _cliente(falso))
        is None
    )


def test_place_not_found_and_same_place(store, com_chave):
    _trajeto(store)
    falso = TomTomFalso()

    class Vazio(TomTomFalso):
        def stream(self, metodo, url, params=None, headers=None):
            if "/search/" in url or "/geocode/" in url:
                self.pedidos.append((url, dict(params)))
                return Resposta(200, {"results": []})
            return super().stream(metodo, url, params, headers)

    r = rotas.preparar_caminhos(store, "rota pro Lugar Inexistente", _cliente(Vazio()))
    assert "não achou" in r["erro"]
    assert "Não invente" in rotas.secao_caminhos(r)
    local = rotas.ler_local("-22.97,-43.18")
    r = rotas.preparar_caminhos(store, "rota pro trabalho", _cliente(falso), local)
    assert r["destino"]["nome"] == "Trabalho"  # local ≠ Trabalho, calcula
    perto = rotas.ler_local("-23.0,-43.36")
    r = rotas.preparar_caminhos(store, "rota pro trabalho", _cliente(falso), perto)
    assert "mesmo lugar" in r["erro"]


@pytest.mark.parametrize(
    "valor, ok",
    [
        ("-23.0001,-43.3655", True),
        ("-23,0001,-43,3655", False),
        ("91,0", False),
        ("abc", False),
        ("", False),
        (None, False),
        ("1" * 100, False),
    ],
)
def test_device_location(valor, ok):
    assert (rotas.ler_local(valor) is not None) is ok


def test_saved_place_matching():
    assert not rotas._parecido("casa da minha mãe", "Casa")
    assert rotas._parecido("posto 4 da Barra", "Posto 4")
    assert rotas._parecido("barra", "Posto 4 Barra")
    assert rotas._parecido("Trabalho", "trabalho")
    assert not rotas._parecido("ca", "Casa")


def test_mothers_house_is_not_my_house(store, com_chave):
    _trajeto(store)  # Casa → Trabalho
    falso = TomTomFalso()
    r = rotas.preparar_caminhos(
        store, "melhor caminho pra casa da minha mãe", _cliente(falso)
    )
    assert r["destino"]["nome"] != "Casa"
    assert "/geocode/" in falso.pedidos[0][0]
    assert 'Lugar pedido: "casa da minha mãe"' in rotas.secao_caminhos(r)


def test_device_location_is_not_cached(store, com_chave):
    rotas.criar_trajeto(store, {"origem": CASA, "destino": POSTO4})
    falso = TomTomFalso()
    cliente = _cliente(falso)
    local = rotas.ler_local("-22.98,-43.2")
    for _ in range(2):
        rotas.preparar_caminhos(store, "rota pro posto 4", cliente, local)
    assert len(falso.pedidos) == 2  # nada guardado com a localização
    rotas.preparar_caminhos(store, "rota pro posto 4", cliente)
    rotas.preparar_caminhos(store, "rota pro posto 4", cliente)
    assert len(falso.pedidos) == 3  # da origem salva, guarda 5 min


def test_summary_only_and_deadline(store, com_chave, monkeypatch):
    falso = TomTomFalso()
    _cliente(falso).caminhos(CASA, POSTO4)
    assert falso.pedidos[0][1]["routeRepresentation"] == "summaryOnly"
    _trajeto(store)
    pergunta = "quanto tempo até o trabalho?"
    feitos = rotas.atualizar_para_pergunta(store, pergunta, _cliente(falso), prazo=0)
    assert feitos == 0
