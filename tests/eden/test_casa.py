"""Éden: casa (Home Assistant) — só aparelhos de mentira e um Home Assistant
falso na própria máquina; nada sai do computador."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from openjarvis.eden import acoes, casa
from openjarvis.eden.contexto import montar
from openjarvis.eden.organizacao import ErroOrganizacao, Organizacao

TZ = timezone(timedelta(hours=-3))
AGORA = int(datetime(2026, 10, 19, 18, 0, tzinfo=TZ).timestamp() * 1000)
VARIAVEIS = (
    "EDEN_CASA_URL",
    "EDEN_CASA_TOKEN",
    "EDEN_CASA_APARELHOS",
    "EDEN_CASA_DEMO",
)


@pytest.fixture
def store(tmp_path, monkeypatch):
    from openjarvis.eden import organizacao

    for v in VARIAVEIS:
        monkeypatch.delenv(v, raising=False)
    monkeypatch.setattr(organizacao, "agora_ms", lambda: AGORA)
    monkeypatch.setattr(casa, "agora_ms", lambda: AGORA)
    with casa._demo_lock:
        casa._demo_estado.clear()
    s = Organizacao(tmp_path / "organizacao.db")
    yield s
    s.close()


def _demo(monkeypatch):
    monkeypatch.setenv("EDEN_CASA_DEMO", "1")


def _bloco(dados) -> str:
    return f"```eden-acao\n{json.dumps(dados, ensure_ascii=False)}\n```"


def _chegando(store):
    return casa.salvar_rotina(
        store,
        {
            "nome": "Chegando em casa",
            "passos": [
                {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": 20},
                {"entidade": "switch.computador_demo", "acao": "ligar"},
                {"entidade": "light.sala_demo", "acao": "cor", "valor": "azul"},
            ],
        },
    )


# ── configuração ─────────────────────────────────────────────────────────


def test_off_by_default_and_nothing_in_the_context(store):
    cfg = casa.configuracao()
    assert not cfg.ligada and cfg.aparelhos == ()
    assert casa.secao_contexto(store, "liga a luz da sala") == ""
    with pytest.raises(ErroOrganizacao, match="não está ligada"):
        casa.comando_pela_tela(store, {"entidade": "light.x", "acao": "ligar"})


def test_device_list_is_closed_and_cleaned(monkeypatch):
    monkeypatch.setenv("EDEN_CASA_URL", "http://homeassistant.local:8123/")
    monkeypatch.setenv("EDEN_CASA_TOKEN", "token-de-teste")
    monkeypatch.setenv(
        "EDEN_CASA_APARELHOS",
        "light.Quarto=Luz do quarto, lock.porta=Porta, switch.pc=  Computador ,"
        "light.quarto=Repetida,climate.sala, shell_command.x=Ruim",
    )
    cfg = casa.configuracao()
    assert cfg.ligada and not cfg.demo
    assert [(a.entidade, a.nome) for a in cfg.aparelhos] == [
        ("light.quarto", "Luz do quarto"),
        ("switch.pc", "Computador"),
        ("climate.sala", "climate.sala"),
    ]
    publica = cfg.publica()
    texto = json.dumps(publica)
    assert "homeassistant" not in texto and "token" not in texto


def test_bad_url_turns_the_house_off(monkeypatch):
    monkeypatch.setenv("EDEN_CASA_TOKEN", "t")
    monkeypatch.setenv("EDEN_CASA_APARELHOS", "light.a=A")
    for ruim in (
        "ftp://ha.local",
        "http://user:senha@ha.local",
        "http://ha.local/?x=1",
    ):
        monkeypatch.setenv("EDEN_CASA_URL", ruim)
        assert not casa.configuracao().ligada


# ── passos ───────────────────────────────────────────────────────────────


def test_steps_are_checked(monkeypatch):
    _demo(monkeypatch)
    cfg = casa.configuracao()
    ok = casa.validar_passo(
        {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": "20"}, cfg
    )
    assert ok == {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": 20}
    ruins = [
        {"entidade": "light.cozinha", "acao": "ligar"},  # fora da lista
        {"entidade": "switch.computador_demo", "acao": "cor", "valor": "azul"},
        {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": 35},
        {"entidade": "climate.ar_demo", "acao": "temperatura", "valor": True},
        {"entidade": "light.sala_demo", "acao": "brilho", "valor": 0},
        {"entidade": "light.sala_demo", "acao": "cor", "valor": "dourada"},
        {"entidade": "light.sala_demo", "acao": "ligar", "valor": 3},
        {"entidade": "light.sala_demo", "acao": "ligar", "servico": "x"},
        "light.sala_demo",
    ]
    for passo in ruins:
        with pytest.raises(ErroOrganizacao):
            casa.validar_passo(passo, cfg)


def test_home_assistant_calls():
    assert casa.chamada({"entidade": "light.a", "acao": "cor", "valor": "azul"}) == (
        "light",
        "turn_on",
        {"entity_id": "light.a", "color_name": "blue"},
    )
    assert casa.chamada(
        {"entidade": "climate.a", "acao": "temperatura", "valor": 20}
    ) == ("climate", "set_temperature", {"entity_id": "climate.a", "temperature": 20})
    assert casa.chamada({"entidade": "button.pc", "acao": "apertar"})[1] == "press"


# ── demonstração e rotinas ───────────────────────────────────────────────


def test_demo_routine_runs_from_the_screen(store, monkeypatch):
    _demo(monkeypatch)
    r = _chegando(store)
    assert r["nome"] == "Chegando em casa" and len(r["passos"]) == 3
    feito = casa.rodar_pela_tela(store, f"r{r['id']}")
    assert feito["demo"] is True and feito["rotina"] == r["id"]
    assert feito["feitos"][0] == "Ar-condicionado (demonstração) → 20 °C"
    estados = {e["entidade"]: e for e in casa.estados()}
    assert estados["climate.ar_demo"] == {
        "entidade": "climate.ar_demo",
        "estado": "on",
        "temperatura": 20,
    }
    assert estados["light.sala_demo"]["estado"] == "on"
    casa.comando_pela_tela(store, {"entidade": "light.sala_demo", "acao": "desligar"})
    assert {e["entidade"]: e for e in casa.estados()}["light.sala_demo"][
        "estado"
    ] == "off"
    registro = [(x["o_que"], x["alvo"]) for x in store.registro(10)]
    assert ("casa.rotina", f"rotina:{r['id']}") in registro
    assert ("casa.aparelho", "casa:light.sala_demo") in registro


def test_routine_limits_and_errors(store, monkeypatch):
    with pytest.raises(ErroOrganizacao, match="não está ligada"):
        _chegando(store)
    _demo(monkeypatch)
    with pytest.raises(ErroOrganizacao, match="pelo menos um passo"):
        casa.salvar_rotina(store, {"nome": "Vazia", "passos": []})
    passos = [{"entidade": "light.sala_demo", "acao": "ligar"}] * (casa.MAX_PASSOS + 1)
    with pytest.raises(ErroOrganizacao, match="no máximo"):
        casa.salvar_rotina(store, {"nome": "Longa", "passos": passos})
    r = _chegando(store)
    editada = casa.salvar_rotina(
        store,
        {
            "nome": "Saindo",
            "passos": [{"entidade": "light.sala_demo", "acao": "desligar"}],
        },
        r["id"],
    )
    assert editada["nome"] == "Saindo" and len(editada["passos"]) == 1
    casa.apagar_rotina(store, r["id"])
    with pytest.raises(ErroOrganizacao) as exc:
        casa.rotina(store, r["id"])
    assert exc.value.status == 404
    with pytest.raises(ErroOrganizacao, match="inválida"):
        casa.rotina(store, "r1; DROP TABLE")


# ── cartões da conversa ──────────────────────────────────────────────────


def test_routine_card_runs_only_when_confirmed(store, monkeypatch):
    _demo(monkeypatch)
    r = _chegando(store)
    [acao], recusadas = acoes.propor(
        _bloco({"tipo": "casa.rotina", "rotina": f"r{r['id']}"}),
        store,
        "pessoal",
        TZ,
        "c1",
        AGORA,
    )
    assert recusadas == []
    assert acao["resumo"] == (
        "Casa (demonstração) — fazer agora: Ar-condicionado (demonstração) → 20 °C; "
        "Computador (demonstração) → ligar; Luz da sala (demonstração) → cor azul"
        " · rotina “Chegando em casa”"
    )
    assert casa.estados()[0]["estado"] == "off"  # nada antes de confirmar
    feita = acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 1000)
    assert feita["estado"] == "feita"
    assert {e["entidade"]: e["estado"] for e in casa.estados()}[
        "light.sala_demo"
    ] == "on"
    # Uso único.
    with pytest.raises(acoes.ErroAcao):
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 2000)


def test_card_fails_if_the_routine_changed(store, monkeypatch):
    _demo(monkeypatch)
    r = _chegando(store)
    [acao], _ = acoes.propor(
        _bloco({"tipo": "casa.rotina", "rotina": r["id"]}),
        store,
        "pessoal",
        TZ,
        "c1",
        AGORA,
    )
    casa.salvar_rotina(
        store,
        {
            "nome": "Chegando em casa",
            "passos": [{"entidade": "light.sala_demo", "acao": "ligar"}],
        },
        r["id"],
    )
    with pytest.raises(acoes.ErroAcao, match="a rotina mudou"):
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 1000)
    assert store.acao(acao["id"])["estado"] == "falhou"
    assert casa.estados()[0]["estado"] == "off"


def test_device_card_and_refusals(store, monkeypatch):
    _demo(monkeypatch)
    criadas, recusadas = acoes.propor(
        _bloco(
            {
                "tipo": "casa.aparelho",
                "entidade": "light.sala_demo",
                "acao": "brilho",
                "valor": 40,
            }
        )
        + _bloco({"tipo": "casa.aparelho", "entidade": "lock.porta", "acao": "ligar"})
        + _bloco(
            {
                "tipo": "casa.aparelho",
                "entidade": "light.sala_demo",
                "acao": "ligar",
                "url": "http://x",
            }
        ),
        store,
        "pessoal",
        TZ,
        "c1",
        AGORA,
    )
    assert len(criadas) == 1 and len(recusadas) == 2
    assert criadas[0]["resumo"] == (
        "Casa (demonstração) — fazer agora: Luz da sala (demonstração) → brilho 40%"
    )
    acoes.confirmar(store, criadas[0]["id"], criadas[0]["assinatura"], TZ, AGORA + 1000)
    estado = casa._demo_estado["light.sala_demo"]
    assert estado == {"estado": "on", "brilho": 40}


def test_card_rechecks_the_list_when_confirming(store, monkeypatch):
    _demo(monkeypatch)
    [acao], _ = acoes.propor(
        _bloco(
            {"tipo": "casa.aparelho", "entidade": "light.sala_demo", "acao": "ligar"}
        ),
        store,
        "pessoal",
        TZ,
        "c1",
        AGORA,
    )
    monkeypatch.delenv("EDEN_CASA_DEMO")  # a casa foi desligada no meio tempo
    with pytest.raises(acoes.ErroAcao, match="não está ligada"):
        acoes.confirmar(store, acao["id"], acao["assinatura"], TZ, AGORA + 1000)
    assert store.acao(acao["id"])["estado"] == "falhou"


def test_context_only_when_the_question_is_about_the_house(store, monkeypatch):
    _demo(monkeypatch)
    _chegando(store)
    sem = montar(store, "pessoal", TZ, AGORA, pergunta="como está meu dia?")
    assert "## Casa" not in sem and "casa.rotina" not in sem
    com = montar(store, "pessoal", TZ, AGORA, pergunta="Estou chegando em 5 minutos")
    assert "light.sala_demo" in com and "[r1]" in com
    assert com.index("## Casa (ações)") > com.index("## Casa (aparelhos")


# ── Home Assistant falso (nesta máquina) ─────────────────────────────────


class _HA(BaseHTTPRequestHandler):
    pedidos: list = []

    def log_message(self, *a):  # silêncio
        pass

    def _responder(self, codigo, corpo, extra=None):
        dados = json.dumps(corpo).encode()
        self.send_response(codigo)
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dados)))
        self.end_headers()
        self.wfile.write(dados)

    def do_POST(self):  # noqa: N802
        n = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(n) or b"null")
        _HA.pedidos.append(
            ("POST", self.path, self.headers.get("Authorization"), corpo)
        )
        if self.headers.get("Authorization") != "Bearer token-certo":
            return self._responder(401, {"message": "Unauthorized"})
        if "redireciona" in self.path:
            return self._responder(302, {}, {"Location": "http://example.invalid/"})
        self._responder(200, [])

    def do_GET(self):  # noqa: N802
        _HA.pedidos.append(("GET", self.path, self.headers.get("Authorization"), None))
        self._responder(200, {"state": "on", "attributes": {"temperature": 21}})


@pytest.fixture
def ha(monkeypatch):
    servidor = HTTPServer(("127.0.0.1", 0), _HA)
    t = threading.Thread(target=servidor.serve_forever, daemon=True)
    t.start()
    _HA.pedidos = []
    monkeypatch.setenv("EDEN_CASA_URL", f"http://127.0.0.1:{servidor.server_port}")
    monkeypatch.setenv("EDEN_CASA_TOKEN", "token-certo")
    monkeypatch.setenv(
        "EDEN_CASA_APARELHOS", "light.quarto=Luz do quarto,climate.sala=Ar da sala"
    )
    yield servidor
    servidor.shutdown()
    servidor.server_close()


def test_talks_to_home_assistant_with_the_token(store, ha):
    feito = casa.comando_pela_tela(
        store, {"entidade": "climate.sala", "acao": "temperatura", "valor": 20}
    )
    assert feito == {"feitos": ["Ar da sala → 20 °C"], "demo": False}
    assert _HA.pedidos[-1] == (
        "POST",
        "/api/services/climate/set_temperature",
        "Bearer token-certo",
        {"entity_id": "climate.sala", "temperature": 20},
    )
    estados = casa.estados()
    assert estados[1] == {"entidade": "climate.sala", "estado": "on", "temperatura": 21}


def test_wrong_token_and_redirects(store, ha, monkeypatch):
    monkeypatch.setenv("EDEN_CASA_TOKEN", "token-errado")
    with pytest.raises(ErroOrganizacao, match="recusou o token"):
        casa.comando_pela_tela(store, {"entidade": "light.quarto", "acao": "ligar"})
    monkeypatch.setenv("EDEN_CASA_TOKEN", "token-certo")
    # O token nunca segue um redirecionamento para outro endereço.
    cfg = casa.configuracao()
    with pytest.raises(ErroOrganizacao, match="erro 302"):
        casa._pedido(cfg, "POST", "/api/redireciona", {})
    assert all("example" not in p[1] for p in _HA.pedidos)


def test_home_assistant_off_is_reported_once(store, monkeypatch):
    monkeypatch.setenv("EDEN_CASA_URL", "http://127.0.0.1:9")  # porta fechada
    monkeypatch.setenv("EDEN_CASA_TOKEN", "t")
    monkeypatch.setenv("EDEN_CASA_APARELHOS", "light.a=A,light.b=B")
    estados = casa.estados()
    assert all("não respondeu" in e["erro"] for e in estados)
