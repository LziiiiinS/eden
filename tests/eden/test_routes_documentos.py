"""Éden: rotas dos documentos (enviar, listar, anexar, apagar)."""

from __future__ import annotations

from urllib.parse import quote

import pytest

pytest.importorskip("fastapi")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from openjarvis.eden import documentos as docs  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402
from openjarvis.eden.routes_documentos import router  # noqa: E402
from openjarvis.server.auth_middleware import AuthMiddleware  # noqa: E402

CHAVE = "oj_sk_teste_documentos"
AUTH = {"Authorization": f"Bearer {CHAVE}"}
CONVERSA = "conv-abc123"


@pytest.fixture
def cliente(tmp_path):
    app = FastAPI()
    store = Organizacao(tmp_path / "organizacao.db")
    app.state.eden_organizacao = store
    app.include_router(router)
    app.add_middleware(AuthMiddleware, api_key=CHAVE)
    yield TestClient(app)
    store.close()


def _enviar(c, nome, dados, espaco="pessoal"):
    return c.post(
        f"/v1/eden/documentos?espaco={espaco}",
        content=dados,
        headers={**AUTH, "X-Eden-Nome": quote(nome), "Content-Type": "text/plain"},
    )


def test_everything_needs_the_key(cliente):
    for metodo, caminho in (
        ("get", "/v1/eden/documentos?espaco=pessoal"),
        ("post", "/v1/eden/documentos?espaco=pessoal"),
        ("get", "/v1/eden/documentos/1"),
        ("delete", "/v1/eden/documentos/1"),
        ("get", f"/v1/eden/documentos/conversa/{CONVERSA}"),
        ("put", f"/v1/eden/documentos/conversa/{CONVERSA}/1"),
    ):
        assert getattr(cliente, metodo)(caminho).status_code == 401, caminho


def test_upload_attach_and_delete(cliente):
    r = _enviar(cliente, "Orçamento do mês.txt", "Aluguel: 1500\nLuz: 200".encode())
    assert r.status_code == 201, r.text
    doc = r.json()["documento"]
    assert doc["nome"] == "Orçamento do mês.txt" and doc["tipo"] == "txt"
    assert "previa" in doc and "texto" not in doc

    lista = cliente.get("/v1/eden/documentos?espaco=pessoal", headers=AUTH).json()
    assert [d["id"] for d in lista["documentos"]] == [doc["id"]]
    assert lista["limites"]["por_conversa"] == docs.MAX_NA_CONVERSA

    anexados = cliente.put(
        f"/v1/eden/documentos/conversa/{CONVERSA}/{doc['id']}", headers=AUTH
    ).json()["documentos"]
    assert [d["id"] for d in anexados] == [doc["id"]]
    assert (
        cliente.get(f"/v1/eden/documentos/conversa/{CONVERSA}", headers=AUTH).json()[
            "documentos"
        ][0]["nome"]
        == "Orçamento do mês.txt"
    )
    assert cliente.delete(f"/v1/eden/documentos/{doc['id']}", headers=AUTH).json() == {
        "ok": True
    }
    assert (
        cliente.get(f"/v1/eden/documentos/{doc['id']}", headers=AUTH).status_code == 404
    )
    assert (
        cliente.get(f"/v1/eden/documentos/conversa/{CONVERSA}", headers=AUTH).json()[
            "documentos"
        ]
        == []
    )


def test_bad_uploads_are_refused(cliente, monkeypatch):
    assert _enviar(cliente, "virus.exe", b"MZ").status_code == 415
    assert _enviar(cliente, "falso.pdf", b"<html>").status_code == 415
    assert _enviar(cliente, "vazio.txt", b"").status_code == 400
    assert _enviar(cliente, "a.txt", b"oi", espaco="inexistente").status_code == 400
    monkeypatch.setattr(docs, "MAX_ARQUIVO", 10)
    assert _enviar(cliente, "grande.txt", b"x" * 11).status_code == 413


def test_conversation_id_is_checked(cliente):
    r = _enviar(cliente, "a.txt", b"conteudo")
    did = r.json()["documento"]["id"]
    ruim = cliente.put(f"/v1/eden/documentos/conversa/a%20b/{did}", headers=AUTH)
    assert ruim.status_code == 400
    assert (
        cliente.put(
            f"/v1/eden/documentos/conversa/{CONVERSA}/999", headers=AUTH
        ).status_code
        == 404
    )
