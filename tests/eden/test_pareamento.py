"""Éden: código curto para ligar um aparelho (iPhone pela tela de início)."""

from __future__ import annotations

import pytest

from openjarvis.eden import pareamento
from openjarvis.eden.pareamento import Pareamento


class Relogio:
    def __init__(self) -> None:
        self.agora = 1000.0

    def __call__(self) -> float:
        return self.agora


@pytest.fixture
def relogio():
    return Relogio()


@pytest.fixture
def par(relogio):
    return Pareamento(relogio=relogio)


def test_code_format_is_easy_to_type(par):
    novo = par.criar()
    assert novo["validade_s"] == 300
    codigo = novo["codigo"]
    assert len(codigo) == 9 and codigo[4] == "-"
    assert all(c in pareamento.ALFABETO for c in codigo.replace("-", ""))
    # Sem símbolos que confundem.
    for confuso in "IO01":
        assert confuso not in pareamento.ALFABETO
    assert len(pareamento.ALFABETO) == 32


def test_code_works_once_and_accepts_spaces_and_lowercase(par):
    codigo = par.criar()["codigo"]
    digitado = " " + codigo.lower().replace("-", " ") + " "
    assert par.usar(digitado) == pareamento.OK
    # Uso único.
    assert par.usar(codigo) == pareamento.INVALIDO
    assert par.ativo() is False


def test_code_expires_after_five_minutes(par, relogio):
    codigo = par.criar()["codigo"]
    relogio.agora += 299
    assert par.ativo() is True
    relogio.agora += 1
    assert par.ativo() is False
    assert par.usar(codigo) == pareamento.INVALIDO


def test_new_code_replaces_the_old_one(par):
    antigo = par.criar()["codigo"]
    novo = par.criar()["codigo"]
    if antigo != novo:
        assert par.usar(antigo) == pareamento.INVALIDO
    assert par.usar(novo) == pareamento.OK


def test_five_wrong_tries_kill_the_code(par):
    codigo = par.criar()["codigo"]
    errado = "AAAA-AAAA" if codigo != "AAAA-AAAA" else "BBBB-BBBB"
    for _ in range(pareamento.MAX_ERROS_POR_CODIGO):
        assert par.usar(errado) == pareamento.INVALIDO
    # Mesmo o código certo não vale mais.
    assert par.usar(codigo) == pareamento.INVALIDO


@pytest.mark.parametrize(
    "texto",
    [None, 12345678, "", "ABC", "ABCDEFGHJ", "ABCD-EFG0", "ABCD-EFGI", "x" * 40],
)
def test_malformed_input_does_not_burn_the_code(par, texto):
    # Lixo não é palpite: não apaga o código de quem vai digitar certo
    # (revisão independente de 15/10). Continua contando no limite por minuto.
    codigo = par.criar()["codigo"]
    for _ in range(pareamento.MAX_ERROS_POR_CODIGO + 2):
        assert par.usar(texto) == pareamento.INVALIDO
    assert par.usar(codigo) == pareamento.OK


def test_malformed_input_still_counts_for_the_rate_limit(par):
    for _ in range(pareamento.MAX_TENTATIVAS_POR_MINUTO):
        assert par.usar("lixo") == pareamento.INVALIDO
    assert par.usar("lixo") == pareamento.MUITAS_TENTATIVAS


def test_without_an_active_code_nothing_works(par):
    assert par.usar("ABCD-EFGH") == pareamento.INVALIDO
    par.criar()
    par.cancelar()
    assert par.ativo() is False


def test_global_limit_per_minute(par, relogio):
    for _ in range(pareamento.MAX_TENTATIVAS_POR_MINUTO):
        assert par.usar("ZZZZ-ZZZZ") == pareamento.INVALIDO
    codigo = par.criar()["codigo"]
    # Passou do limite: nem o código certo é conferido (e não gasta o código).
    assert par.usar(codigo) == pareamento.MUITAS_TENTATIVAS
    assert par.ativo() is True
    relogio.agora += 60
    assert par.usar(codigo) == pareamento.OK


def test_code_is_not_kept_in_plain_text(par):
    codigo = par.criar()["codigo"]
    limpo = codigo.replace("-", "")
    for valor in vars(par).values():
        assert limpo not in repr(valor)
        assert codigo not in repr(valor)


@pytest.mark.parametrize(
    "texto, esperado",
    [
        ("k7qm-2xra", "K7QM2XRA"),
        ("K7QM 2XRA", "K7QM2XRA"),
        ("K7QM2XRA", "K7QM2XRA"),
        ("K7QM-2XR", None),
        ("K7QM-2XR\u00c1", None),
        ("K7QM\u200b2XRA", None),  # caractere invisível
        ("K7QM2X\u00df", None),  # "ß".upper() vira "SS"
        ("K7QM2XR\uff21", None),  # letra de largura cheia
    ],
)
def test_normalize(texto, esperado):
    assert pareamento.normalizar(texto) == esperado
