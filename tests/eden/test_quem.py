"""Éden: o registro de ações diz de qual aparelho veio o pedido."""

from datetime import timezone

import pytest

from openjarvis.eden import aparelhos, quem
from openjarvis.eden.organizacao import Organizacao


@pytest.fixture
def lista(tmp_path):
    reg = aparelhos.Aparelhos(tmp_path / "aparelhos.db")
    aparelhos.definir_registro(reg)
    yield reg
    aparelhos.definir_registro(None)
    reg.close()


def test_without_a_request_nothing_changes():
    assert quem.com_aparelho("pessoa") == "pessoa"


def test_main_key_and_device(lista):
    marca = quem.definir(None)
    try:
        assert quem.com_aparelho("pessoa") == "pessoa (chave principal)"
    finally:
        quem.soltar(marca)
    novo = lista.criar("iPhone do Levi (fictício)")
    marca = quem.definir(novo["id"])
    try:
        assert (
            quem.com_aparelho("eden")
            == f"eden (iPhone do Levi (fictício) #{novo['id']})"
        )
    finally:
        quem.soltar(marca)
    assert quem.com_aparelho("pessoa") == "pessoa"


def test_unknown_device_still_shows_the_number(lista):
    marca = quem.definir(99)
    try:
        assert quem.com_aparelho("pessoa") == "pessoa (aparelho #99)"
    finally:
        quem.soltar(marca)


def test_registro_line_through_the_server(tmp_path, lista):
    pytest.importorskip("fastapi")
    from fastapi import FastAPI, Request
    from fastapi.testclient import TestClient

    from openjarvis.server.auth_middleware import AuthMiddleware

    store = Organizacao(tmp_path / "organizacao.db")
    app = FastAPI()

    @app.post("/v1/eden/teste")
    async def criar(request: Request):
        return store.criar_tarefa(
            {"titulo": "Tarefa fictícia", "espaco": "pessoal"}, timezone.utc
        )

    app.add_middleware(AuthMiddleware, api_key="oj_sk_teste_quem")
    cliente = TestClient(app)
    celular = lista.criar("Samsung (fictício)")
    r = cliente.post(
        "/v1/eden/teste", headers={"Authorization": f"Bearer {celular['chave']}"}
    )
    assert r.status_code == 200, r.text
    r = cliente.post(
        "/v1/eden/teste", headers={"Authorization": "Bearer oj_sk_teste_quem"}
    )
    assert r.status_code == 200, r.text
    linhas = store.registro(10)
    store.close()
    assert linhas[0]["quem"].endswith("(chave principal)")
    assert linhas[1]["quem"].endswith(f"(Samsung (fictício) #{celular['id']})")
