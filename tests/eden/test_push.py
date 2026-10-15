"""Éden: avisos no aparelho (Web Push) — cifra, assinatura, inscrições, envio."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timedelta, timezone

import pytest

pytest.importorskip("cryptography")

from cryptography.hazmat.primitives import hashes  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import ec  # noqa: E402
from cryptography.hazmat.primitives.asymmetric.utils import (  # noqa: E402
    encode_dss_signature,
)

from openjarvis.eden import push  # noqa: E402
from openjarvis.eden.organizacao import Organizacao  # noqa: E402

TZ = timezone(timedelta(hours=-3))


@pytest.fixture
def store(tmp_path):
    s = Organizacao(tmp_path / "organizacao.db")
    yield s
    s.close()


def _aparelho():
    chave = ec.generate_private_key(ec.SECP256R1())
    from cryptography.hazmat.primitives import serialization

    pub = chave.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return chave, push.b64url(pub), push.b64url(b"0123456789abcdef")


def test_encryption_matches_rfc_8291_example():
    # Exemplo da seção 5 da RFC 8291.
    efemera = ec.derive_private_key(
        int.from_bytes(
            push.de_b64url("yfWPiYE-n46HLnH0KqZOF1fJJU3MYrct3AELtAQ-oRw"), "big"
        ),
        ec.SECP256R1(),
    )
    corpo = push.cifrar(
        b"When I grow up, I want to be a watermelon",
        push.de_b64url(
            "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
        ),
        push.de_b64url("BTBZMqHH6r4Tts7J_aSIgg"),
        efemera=efemera,
        sal=push.de_b64url("DGv6ra1nlYgDCS1FRnbzlw"),
    )
    assert push.b64url(corpo) == (
        "DGv6ra1nlYgDCS1FRnbzlwAAEABBBP4z9KsN6nGRTbVYI_c7VJSPQTBtkgcy27mlmlMoZIIgDll6"
        "e3vCYLocInmYWAmS6TlzAC8wEqKK6PBru3jl7A_yl95bQpu6cVPTpK4Mqgkf1CXztLVBSt2Ks3oZw"
        "buwXPXLWyouBWLVWGNWQexSgSxsj_Qulcy4a-fN"
    )


def test_vapid_key_is_created_once_and_private(tmp_path):
    caminho = tmp_path / "eden" / "push-vapid.key"
    a = push.carregar_chave(caminho)
    b = push.carregar_chave(caminho)
    assert push.chave_publica_b64(a) == push.chave_publica_b64(b)
    assert oct(caminho.stat().st_mode & 0o777) == "0o600"
    assert len(push.de_b64url(push.chave_publica_b64(a))) == 65


def test_vapid_jwt_is_signed_for_the_push_service(tmp_path):
    chave = push.carregar_chave(tmp_path / "k.key")
    token = push.jwt_vapid("https://fcm.googleapis.com/fcm/send/abc", chave, agora=1000)
    cab, dados, assinatura = token.split(".")
    claims = json.loads(push.de_b64url(dados))
    assert claims == {
        "aud": "https://fcm.googleapis.com",
        "exp": 1000 + 12 * 3600,
        "sub": push.VAPID_SUB,
    }
    bruta = push.de_b64url(assinatura)
    assert len(bruta) == 64
    der = encode_dss_signature(
        int.from_bytes(bruta[:32], "big"), int.from_bytes(bruta[32:], "big")
    )
    chave.public_key().verify(der, f"{cab}.{dados}".encode(), ec.ECDSA(hashes.SHA256()))


@pytest.mark.parametrize(
    "endpoint, ok",
    [
        ("https://fcm.googleapis.com/fcm/send/abc", True),
        ("https://web.push.apple.com/QGx", True),
        ("https://updates.push.services.mozilla.com/wpush/v2/x", True),
        ("https://wns2-bl2p.notify.windows.com/w/?token=x", True),
        ("http://fcm.googleapis.com/fcm/send/abc", False),
        ("https://fcm.googleapis.com:8443/x", False),
        ("https://user:pw@fcm.googleapis.com/x", False),
        ("https://evil.example/fcm.googleapis.com", False),
        ("https://fcm.googleapis.com.evil.example/x", False),
        ("https://localhost/x", False),
        ("https://169.254.169.254/latest", False),
        (None, False),
    ],
)
def test_only_known_push_services(endpoint, ok):
    assert push.endpoint_permitido(endpoint) is ok


def test_subscriptions_are_validated_saved_and_listed_without_endpoint(store):
    _, p256dh, auth = _aparelho()
    insc = {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": p256dh, "auth": auth},
        "nome": "iPhone <b>",
    }
    salva = push.salvar_inscricao(store, insc)
    assert salva["servico"] == "fcm.googleapis.com" and salva["nome"] == "iPhone b"
    # Repetir só atualiza.
    push.salvar_inscricao(store, insc)
    lista = push.listar_inscricoes(store)
    assert len(lista) == 1 and "endpoint" not in lista[0]
    with pytest.raises(push.ErroPush):
        push.salvar_inscricao(store, {**insc, "endpoint": "https://evil.example/x"})
    with pytest.raises(push.ErroPush):
        push.salvar_inscricao(store, {**insc, "keys": {"p256dh": "AAAA", "auth": auth}})
    with pytest.raises(push.ErroPush):
        # 65 bytes começando com 4, mas fora da curva.
        falsa = push.b64url(b"\x04" + b"\x01" * 64)
        push.salvar_inscricao(store, {**insc, "keys": {"p256dh": falsa, "auth": auth}})
    assert push.remover_inscricao(store, insc["endpoint"]) is True
    assert push.listar_inscricoes(store) == []


class FakeResposta:
    def __init__(self, status):
        self.status_code = status


class FakeClient:
    def __init__(self, status=201):
        self.status = status
        self.pedidos = []

    async def post(self, url, content, headers, timeout):
        self.pedidos.append((url, content, headers))
        return FakeResposta(self.status)


def test_sending_encrypts_for_each_device_and_drops_gone_ones(store, tmp_path):
    chave = push.carregar_chave(tmp_path / "k.key")
    aparelho, p256dh, auth = _aparelho()
    push.salvar_inscricao(
        store,
        {
            "endpoint": "https://web.push.apple.com/abc",
            "keys": {"p256dh": p256dh, "auth": auth},
        },
    )
    client = FakeClient(201)
    resultado = asyncio.run(push.enviar(store, chave, {"titulo": "Oi"}, client))
    assert resultado == {"enviados": 1, "falhas": 0, "removidos": 0}
    url, corpo, headers = client.pedidos[0]
    assert headers["Content-Encoding"] == "aes128gcm"
    assert headers["Authorization"].startswith("vapid t=")
    assert b"Oi" not in corpo  # cifrado

    gone = FakeClient(410)
    resultado = asyncio.run(push.enviar(store, chave, {"titulo": "Oi"}, gone))
    assert resultado["removidos"] == 1
    assert push.listar_inscricoes(store) == []


def test_due_reminders_are_pushed_once(store, tmp_path):
    chave = push.carregar_chave(tmp_path / "k.key")
    _, p256dh, auth = _aparelho()
    push.salvar_inscricao(
        store,
        {
            "endpoint": "https://fcm.googleapis.com/x",
            "keys": {"p256dh": p256dh, "auth": auth},
        },
    )
    agora = int(datetime(2026, 10, 15, 10, 0, tzinfo=TZ).timestamp() * 1000)
    store.criar_tarefa(
        {
            "titulo": "Ligar pro dentista",
            "espaco": "pessoal",
            "data": "2026-10-15",
            "hora": "09:59",
            "lembrete": True,
        },
        TZ,
    )
    client = FakeClient(201)
    assert asyncio.run(push.enviar_lembretes_vencidos(store, chave, client, agora)) == 1
    assert len(client.pedidos) == 1
    assert (
        asyncio.run(
            push.enviar_lembretes_vencidos(store, chave, client, agora + 60_000)
        )
        == 0
    )
    assert len(client.pedidos) == 1


def test_reminders_without_devices_are_still_marked(store, tmp_path):
    chave = push.carregar_chave(tmp_path / "k.key")
    agora = int(datetime(2026, 10, 15, 10, 0, tzinfo=TZ).timestamp() * 1000)
    t = store.criar_tarefa(
        {
            "titulo": "x",
            "espaco": "pessoal",
            "data": "2026-10-15",
            "hora": "09:00",
            "lembrete": True,
        },
        TZ,
    )
    client = FakeClient()
    assert asyncio.run(push.enviar_lembretes_vencidos(store, chave, client, agora)) == 1
    assert client.pedidos == []
    assert store.tarefa(t["id"])["lembrete_enviado_em"] == agora
