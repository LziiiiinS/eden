"""Éden (Parte 2): rotas da organização e ações sugeridas na conversa."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import budget, settings  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
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
def app(tmp_path):
    settings.set_settings(settings.EdenSettings(enabled=True))
    ledger = budget.SpendingLedger(tmp_path / "gastos.db")
    budget.set_ledger(ledger)
    engine = MagicMock()
    engine.engine_id = "mock"
    engine.health.return_value = True
    engine.list_models.return_value = ["qwen3.5:4b"]
    application = create_app(engine, "qwen3.5:4b", config=_config())
    store = Organizacao(tmp_path / "organizacao.db")
    application.state.eden_organizacao = store
    from openjarvis.eden import push

    application.state.eden_push_chave = push.carregar_chave(tmp_path / "vapid.key")
    yield application
    settings.set_settings(None)
    budget.set_ledger(None)
    ledger.close()
    store.close()


@pytest.fixture
def client(app):
    return TestClient(app, base_url="http://localhost")


def _eventos(texto_sse: str):
    """Lista de (evento, dados) do streaming."""
    eventos = []
    atual = None
    for linha in texto_sse.splitlines():
        if linha.startswith("event: "):
            atual = linha[7:]
        elif linha.startswith("data: "):
            eventos.append((atual, linha[6:]))
            atual = None
    return eventos


def _conversar(client, resposta: str, espaco: str = "pessoal", visto=None):
    async def fake_stream(model, messages, temperature, provider, **kwargs):
        if visto is not None:
            visto["mensagens"] = messages
        for i in range(0, len(resposta), 40):
            yield resposta[i : i + 40]

    with patch("openjarvis.eden.providers.stream_eden", fake_stream):
        return client.post(
            "/v1/chat/completions",
            headers={"X-Eden-Espaco": espaco, "X-Eden-Conversa": "conv-1"},
            json={
                "model": "eden-dia",
                "messages": [{"role": "user", "content": "anota comprar pão amanhã"}],
                "stream": True,
            },
        )


# ── tela ─────────────────────────────────────────────────────────────────


def test_spaces_profile_and_memories(client):
    espacos = client.get("/v1/eden/espacos").json()["espacos"]
    assert [e["id"] for e in espacos] == ["pessoal", "ls-visuals", "clientes"]
    novo = client.post("/v1/eden/espacos", json={"nome": "Estudos"}).json()["espaco"]
    assert novo["id"] == "estudos"
    assert (
        client.patch("/v1/eden/espacos/estudos", json={"nome": "Faculdade"}).status_code
        == 200
    )

    assert (
        client.put("/v1/eden/perfil", json={"texto": "Levi"}).json()["perfil"]["texto"]
        == "Levi"
    )

    m = client.post(
        "/v1/eden/memorias", json={"texto": "Café sem açúcar", "espaco": None}
    )
    assert m.status_code == 200
    mid = m.json()["memoria"]["id"]
    assert (
        client.get("/v1/eden/memorias?espaco=clientes").json()["memorias"][0]["id"]
        == mid
    )
    assert client.delete(f"/v1/eden/memorias/{mid}").status_code == 200
    assert client.delete(f"/v1/eden/memorias/{mid}").status_code == 404


def test_tasks_and_notes(client):
    r = client.post(
        "/v1/eden/tarefas",
        json={
            "titulo": "Pagar luz",
            "espaco": "pessoal",
            "data": "2026-10-20",
            "lembrete": True,
        },
    )
    assert r.status_code == 200
    tarefa = r.json()["tarefa"]
    assert tarefa["lembrete_em"] and tarefa["origem"] == "voce"
    r = client.patch(f"/v1/eden/tarefas/{tarefa['id']}", json={"feita": True})
    assert r.json()["tarefa"]["feita"] is True
    assert (
        client.get("/v1/eden/tarefas?estado=feitas").json()["tarefas"][0]["id"]
        == tarefa["id"]
    )

    assert client.post("/v1/eden/tarefas", json={"titulo": ""}).status_code == 400
    assert (
        client.post("/v1/eden/tarefas", json={"titulo": "x", "espaco": "?"}).status_code
        == 400
    )
    assert client.get("/v1/eden/tarefas?espaco=nada").status_code == 400

    n = client.post(
        "/v1/eden/notas",
        json={"texto": "Ideia", "tipo": "ideia", "espaco": "ls-visuals"},
    )
    assert n.status_code == 200
    assert client.get("/v1/eden/notas?busca=Ide").json()["notas"][0]["tipo"] == "ideia"


def test_body_must_be_an_object_and_small(client):
    assert client.post("/v1/eden/notas", content=b"[1]").status_code == 400
    assert client.post("/v1/eden/notas", content=b"{x").status_code == 400
    grande = json.dumps({"texto": "x" * 300_000})
    assert client.post("/v1/eden/notas", content=grande).status_code == 413


def test_today_summary(client):
    client.post(
        "/v1/eden/tarefas",
        json={"titulo": "Atrasada", "espaco": "pessoal", "data": "2000-01-01"},
    )
    client.post("/v1/eden/tarefas", json={"titulo": "Sem data", "espaco": "clientes"})
    resumo = client.get("/v1/eden/hoje").json()
    assert [t["titulo"] for t in resumo["atrasadas"]] == ["Atrasada"]
    assert [t["titulo"] for t in resumo["sem_data"]] == ["Sem data"]
    so_pessoal = client.get("/v1/eden/hoje?espaco=pessoal").json()
    assert so_pessoal["sem_data"] == []


# ── conversa → ação → confirmação ────────────────────────────────────────


def test_chat_gets_context_and_returns_actions_to_confirm(client, app):
    store = app.state.eden_organizacao
    store.criar_tarefa(
        {"titulo": "Tarefa de cliente", "espaco": "clientes"},
        settings.get_settings().tz,
    )
    visto = {}
    resposta = (
        "Deixei para você confirmar no cartão abaixo.\n\n"
        '```eden-acao\n{"tipo": "tarefa.criar", "titulo": "Comprar pão", '
        '"data": "2026-10-16"}\n```'
    )
    r = _conversar(client, resposta, visto=visto)
    assert r.status_code == 200

    sistema = visto["mensagens"][0]
    assert sistema.role.value == "system"
    assert "Espaço ativo: Pessoal (pessoal)" in sistema.content
    assert "Tarefa de cliente" not in sistema.content
    assert "eden-acao" in sistema.content

    eventos = _eventos(r.text)
    nomes = [e for e, _ in eventos]
    assert "eden_acoes" in nomes
    # O cartão chega antes do pedaço final (o app para de ler no "stop").
    i_acoes = nomes.index("eden_acoes")
    i_stop = next(
        i
        for i, (e, d) in enumerate(eventos)
        if e is None
        and d != "[DONE]"
        and json.loads(d)["choices"][0].get("finish_reason")
    )
    assert i_acoes < i_stop
    dados = json.loads(eventos[i_acoes][1])
    [acao] = dados["acoes"]
    assert acao["resumo"].startswith("Criar tarefa “Comprar pão” em Pessoal")
    assert store.listar_tarefas("pessoal") == []

    # Assinatura errada: recusado, nada criado.
    r = client.post(
        f"/v1/eden/acoes/{acao['id']}/confirmar", json={"assinatura": "0" * 64}
    )
    assert r.status_code == 409 and r.json()["code"] == "eden_acao_assinatura"
    assert store.listar_tarefas("pessoal") == []

    r = client.post(
        f"/v1/eden/acoes/{acao['id']}/confirmar",
        json={"assinatura": acao["assinatura"]},
    )
    assert r.status_code == 200 and r.json()["acao"]["estado"] == "feita"
    assert [t["titulo"] for t in store.listar_tarefas("pessoal")] == ["Comprar pão"]

    # Repetir a confirmação não cria de novo.
    r = client.post(
        f"/v1/eden/acoes/{acao['id']}/confirmar",
        json={"assinatura": acao["assinatura"]},
    )
    assert r.status_code == 409
    assert len(store.listar_tarefas("pessoal")) == 1
    assert (
        client.get(f"/v1/eden/acoes/{acao['id']}").json()["acao"]["estado"] == "feita"
    )


def test_chat_in_another_space_uses_that_space(client, app):
    visto = {}
    resposta = '```eden-acao\n{"tipo": "memoria.criar", "texto": "Prazo é sexta"}\n```'
    r = _conversar(client, resposta, espaco="clientes", visto=visto)
    assert "Espaço ativo: Clientes (clientes)" in visto["mensagens"][0].content
    dados = json.loads(next(d for e, d in _eventos(r.text) if e == "eden_acoes"))
    assert dados["acoes"][0]["parametros"]["espaco"] == "clientes"


def test_unknown_space_header_falls_back_to_personal(client):
    visto = {}
    _conversar(client, "Oi!", espaco="../../etc", visto=visto)
    assert "Espaço ativo: Pessoal" in visto["mensagens"][0].content


def test_answer_without_blocks_has_no_action_event(client):
    r = _conversar(client, "Bom dia! Tudo certo por aqui.")
    assert "eden_acoes" not in [e for e, _ in _eventos(r.text)]
    assert "Bom dia!" in r.text


def test_invalid_block_is_reported_not_created(client, app):
    r = _conversar(client, '```eden-acao\n{"tipo": "apagar_tudo"}\n```')
    dados = json.loads(next(d for e, d in _eventos(r.text) if e == "eden_acoes"))
    assert dados["acoes"] == [] and dados["recusadas"]
    assert app.state.eden_organizacao.listar_acoes() == []


def test_refuse_route_and_missing_action(client, app):
    r = _conversar(client, '```eden-acao\n{"tipo": "memoria.criar", "texto": "x"}\n```')
    acao = json.loads(next(d for e, d in _eventos(r.text) if e == "eden_acoes"))[
        "acoes"
    ][0]
    assert (
        client.post(f"/v1/eden/acoes/{acao['id']}/recusar").json()["acao"]["estado"]
        == "recusada"
    )
    assert client.post("/v1/eden/acoes/naoexiste123/recusar").status_code == 404
    assert client.get("/v1/eden/acoes/naoexiste123").status_code == 404


def test_organization_routes_survive_eden_hardening(app):
    paths = {getattr(r, "path", "") for r in app.router.routes}
    for path in (
        "/v1/eden/espacos",
        "/v1/eden/tarefas",
        "/v1/eden/acoes/{acao_id}/confirmar",
        "/v1/eden/hoje",
    ):
        assert path in paths, path


def test_push_subscription_routes(client):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec

    from openjarvis.eden import push

    chave = client.get("/v1/eden/push/chave").json()["chave"]
    assert len(push.de_b64url(chave)) == 65
    aparelho = ec.generate_private_key(ec.SECP256R1()).public_key()
    p256dh = push.b64url(
        aparelho.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
        )
    )
    insc = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": p256dh, "auth": push.b64url(b"0123456789abcdef")},
    }
    assert client.post("/v1/eden/push/inscricoes", json=insc).status_code == 200
    ruim = {**insc, "endpoint": "https://169.254.169.254/latest"}
    assert client.post("/v1/eden/push/inscricoes", json=ruim).status_code == 400
    lista = client.get("/v1/eden/push/inscricoes").json()["inscricoes"]
    assert lista[0]["servico"] == "fcm.googleapis.com" and "endpoint" not in lista[0]
    r = client.post("/v1/eden/push/cancelar", json={"endpoint": insc["endpoint"]})
    assert r.json() == {"removida": True}
    # Remover pela tela (por id), sem precisar do endereço do aparelho.
    client.post("/v1/eden/push/inscricoes", json=insc)
    insc_id = client.get("/v1/eden/push/inscricoes").json()["inscricoes"][0]["id"]
    assert client.delete(f"/v1/eden/push/inscricoes/{insc_id}").status_code == 200
    assert client.delete(f"/v1/eden/push/inscricoes/{insc_id}").status_code == 404
    assert client.post("/v1/eden/push/teste").json()["enviados"] == 0
