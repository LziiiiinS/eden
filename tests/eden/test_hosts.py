"""Éden: o servidor só responde a endereços dele (contra "DNS rebinding")."""

from __future__ import annotations

import asyncio

import pytest

from openjarvis.eden.hardening import HostPermitido, host_permitido, nome_do_host


@pytest.mark.parametrize(
    "host",
    [
        "localhost",
        "localhost:8000",
        "127.0.0.1:8000",
        "[::1]:8000",
        "eden-notebook.tail1234.ts.net",
        "EDEN-SERVIDOR.tail1234.ts.net:443",
        "eden-notebook.tail1234.ts.net.",
    ],
)
def test_eden_addresses_are_accepted(host):
    assert host_permitido(host)


@pytest.mark.parametrize(
    "host",
    [
        "",
        "site-malicioso.example",
        "site-malicioso.example:8000",
        "ts.net",
        ".ts.net",
        "eden.ts.net.site-malicioso.example",
        "eden-ts.net",
        "localhost.site-malicioso.example",
        "127.0.0.2:8000",
        "user@localhost",
        "testserver",
    ],
)
def test_other_addresses_are_refused(host):
    assert not host_permitido(host)


def test_extra_hosts_from_env():
    assert host_permitido("eden-notebook", extras=("eden-notebook", " "))
    assert not host_permitido("outro", extras=("eden-notebook",))


def test_host_name_parsing():
    assert nome_do_host("[::1]:8000") == "::1"
    assert nome_do_host("Eden.ts.net:443") == "eden.ts.net"
    assert nome_do_host("::1") == "::1"


def _chamar(host: bytes | None):
    respostas = []

    async def app(scope, receive, send):
        respostas.append("app")

    async def send(msg):
        respostas.append(msg)

    async def receive():
        return {"type": "http.request", "body": b""}

    headers = [(b"host", host)] if host is not None else []
    scope = {"type": "http", "headers": headers, "path": "/"}
    asyncio.run(HostPermitido(app)(scope, receive, send))
    return respostas


def test_middleware_lets_eden_through_and_refuses_others(monkeypatch):
    monkeypatch.delenv("EDEN_HOSTS_EXTRAS", raising=False)
    assert _chamar(b"localhost:8000") == ["app"]
    recusado = _chamar(b"site-malicioso.example:8000")
    assert recusado[0]["status"] == 400
    assert b"eden_host" in recusado[1]["body"]
    assert _chamar(None)[0]["status"] == 400


def test_middleware_passes_lifespan():
    chamadas = []

    async def app(scope, receive, send):
        chamadas.append(scope["type"])

    asyncio.run(HostPermitido(app)({"type": "lifespan"}, None, None))
    assert chamadas == ["lifespan"]
