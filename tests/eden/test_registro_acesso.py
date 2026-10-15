"""Éden: o registro de acesso não guarda o que vem depois do "?"."""

from __future__ import annotations

import logging
import logging.config

from openjarvis.eden import hardening


class Coletor(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.linhas: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.linhas.append(record.getMessage())


def _registrar(caminho: str) -> list[str]:
    registro = logging.getLogger(hardening.ACCESS_LOGGER)
    coletor = Coletor()
    registro.addHandler(coletor)
    nivel = registro.level
    registro.setLevel(logging.INFO)
    try:
        # Mesmo formato do uvicorn.
        registro.info(
            '%s - "%s %s HTTP/%s" %d', "100.64.0.2:5000", "GET", caminho, "1.1", 200
        )
    finally:
        registro.removeHandler(coletor)
        registro.setLevel(nivel)
    return coletor.linhas


def test_search_terms_do_not_reach_the_access_log():
    hardening.esconder_consultas_no_registro()
    hardening.esconder_consultas_no_registro()  # ligar duas vezes não duplica
    filtros = [
        f
        for f in logging.getLogger(hardening.ACCESS_LOGGER).filters
        if isinstance(f, hardening.SemConsultaNoRegistro)
    ]
    assert len(filtros) == 1
    (linha,) = _registrar("/v1/eden/notas?espaco=pessoal&busca=segredo")
    assert "segredo" not in linha and "pessoal" not in linha
    assert '"GET /v1/eden/notas?… HTTP/1.1" 200' in linha
    (linha,) = _registrar("/v1/eden/hoje")
    assert '"GET /v1/eden/hoje HTTP/1.1" 200' in linha


def test_filter_survives_the_server_logging_setup():
    hardening.esconder_consultas_no_registro()
    registro = logging.getLogger(hardening.ACCESS_LOGGER)
    antes = (registro.handlers[:], registro.propagate, registro.level)
    try:
        _configurar_como_o_servidor()
        (linha,) = _registrar("/v1/eden/notas?busca=segredo")
        assert "segredo" not in linha
    finally:
        registro.handlers[:], registro.propagate, registro.level = antes


def _configurar_como_o_servidor():
    # O uvicorn configura o registro depois de criar o app (dictConfig).
    logging.config.dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "handlers": {"nulo": {"class": "logging.NullHandler"}},
            "loggers": {
                hardening.ACCESS_LOGGER: {
                    "handlers": ["nulo"],
                    "level": "INFO",
                    "propagate": False,
                }
            },
        }
    )
