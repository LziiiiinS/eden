"""Éden (Parte 5): chave por aparelho."""

from __future__ import annotations

import pytest

from openjarvis.eden import aparelhos


@pytest.fixture
def reg(tmp_path):
    r = aparelhos.Aparelhos(tmp_path / "aparelhos.db")
    yield r
    r.close()


def test_create_check_and_turn_off(reg, tmp_path):
    novo = reg.criar("iPhone do Levi")
    chave = novo["chave"]
    assert chave.startswith("oj_ap_") and aparelhos.parece_chave_de_aparelho(chave)
    assert reg.conferir(chave) == novo["id"]
    lista = reg.listar()
    assert lista[0]["nome"] == "iPhone do Levi" and lista[0]["ultimo_uso"]
    assert "chave" not in lista[0] and "resumo" not in lista[0]
    # O banco guarda só o resumo, nunca a chave.
    assert chave.encode() not in (tmp_path / "aparelhos.db").read_bytes()
    assert reg.desligar(novo["id"]) is True
    assert reg.conferir(chave) is None
    assert reg.listar() == []
    assert reg.desligar(novo["id"]) is False


def test_survives_restart(tmp_path):
    r1 = aparelhos.Aparelhos(tmp_path / "a.db")
    chave = r1.criar("Samsung")["chave"]
    r1.close()
    r2 = aparelhos.Aparelhos(tmp_path / "a.db")
    assert r2.conferir(chave) is not None
    r2.close()


@pytest.mark.parametrize(
    "valor",
    [None, "", "oj_sk_principal", "oj_ap_curta", "oj_ap_" + "x" * 48 + " ", 123],
)
def test_bad_keys(reg, valor):
    assert reg.conferir(valor) is None


def test_unknown_but_well_formed_key(reg):
    assert reg.conferir("oj_ap_" + "A" * 48) is None


def test_limit_and_names(reg, monkeypatch):
    monkeypatch.setattr(aparelhos, "MAX_APARELHOS", 2)
    reg.criar("  um\\n nome\\x00 ")
    reg.criar("x" * 200)
    with pytest.raises(ValueError):
        reg.criar("terceiro")
    nomes = [a["nome"] for a in reg.listar()]
    assert len(nomes[1]) == aparelhos.MAX_NOME
    assert all(c.isprintable() for n in nomes for c in n)
    assert aparelhos.limpar_nome(None) == "Aparelho"


def test_name_from_browser():
    assert (
        aparelhos.nome_pelo_navegador("Mozilla/5.0 (iPhone; CPU iPhone OS)") == "iPhone"
    )
    assert aparelhos.nome_pelo_navegador("Mozilla/5.0 (Linux; Android 14)") == "Android"
    assert aparelhos.nome_pelo_navegador(None) == "Aparelho"


def test_rename(reg):
    novo = reg.criar("Celular")
    assert reg.renomear(novo["id"], "Celular da Ana") is True
    assert reg.listar()[0]["nome"] == "Celular da Ana"
    assert reg.renomear(True, "x") is False


def test_module_check_never_raises(monkeypatch):
    class Quebrado:
        def conferir(self, chave):
            raise RuntimeError("banco travado")

    monkeypatch.setattr(aparelhos, "registro", lambda: Quebrado())
    assert aparelhos.conferir("oj_ap_" + "A" * 48) is None
    assert aparelhos.conferir("oj_sk_x") is None


def test_never_used_keys_expire_after_a_day(reg, monkeypatch):
    velho = reg.criar("QR esquecido")
    usado = reg.criar("iPhone")
    reg.conferir(usado["chave"])
    agora = aparelhos._agora_ms()
    monkeypatch.setattr(aparelhos, "_agora_ms", lambda: agora + 2 * 24 * 3600 * 1000)
    reg.criar("novo")
    nomes = [a["nome"] for a in reg.listar()]
    assert "QR esquecido" not in nomes and "iPhone" in nomes and "novo" in nomes
    assert reg.conferir(velho["chave"]) is None


def test_websocket_accepts_device_key(reg):
    import base64
    from types import SimpleNamespace

    from openjarvis.server.auth_middleware import authenticate_websocket

    aparelhos.definir_registro(reg)
    try:
        chave = reg.criar("iPhone")["chave"]
        codificada = base64.urlsafe_b64encode(chave.encode()).decode().rstrip("=")
        ws = SimpleNamespace(
            scope={
                "subprotocols": [
                    "openjarvis.auth.v1",
                    f"openjarvis.key.b64url.{codificada}",
                ]
            },
            headers={},
        )
        assert authenticate_websocket(ws, "oj_sk_principal")[0] is True
        ws2 = SimpleNamespace(scope={}, headers={"authorization": f"Bearer {chave}"})
        assert authenticate_websocket(ws2, "oj_sk_principal")[0] is True
        falsa = SimpleNamespace(
            scope={}, headers={"authorization": "Bearer oj_ap_" + "B" * 48}
        )
        assert authenticate_websocket(falsa, "oj_sk_principal")[0] is False
    finally:
        aparelhos.definir_registro(None)
