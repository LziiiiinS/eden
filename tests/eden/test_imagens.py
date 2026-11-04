"""Éden: imagens na conversa (print, foto) — conferência e envio às IAs."""

from __future__ import annotations

import base64
from types import SimpleNamespace

import pytest

from openjarvis.core.types import Message, Role
from openjarvis.eden import imagens
from openjarvis.eden.providers import build_anthropic_payload, build_openai_payload

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def _url(tipo: str, dados: bytes) -> str:
    return f"data:{tipo};base64,{base64.b64encode(dados).decode()}"


def test_accepts_real_images_only():
    assert imagens.conferir_uma(_url("image/png", PNG)).startswith(
        "data:image/png;base64,"
    )
    assert imagens.conferir_uma(_url("image/jpeg", JPEG))
    ruins = [
        "https://example.com/foto.png",  # nada de endereço de fora
        "data:image/svg+xml;base64," + base64.b64encode(b"<svg/>").decode(),
        _url("image/png", JPEG),  # diz que é PNG, mas é JPEG
        _url("image/png", b"texto qualquer"),
        "data:image/png;base64,@@@",
        _url("image/png", PNG + b"\x00" * imagens.MAX_BYTES),  # grande demais
        123,
    ]
    for ruim in ruins:
        with pytest.raises(imagens.ErroImagem):
            imagens.conferir_uma(ruim)


def test_only_the_last_user_message_keeps_images():
    antiga = SimpleNamespace(role="user", images=[_url("image/png", PNG)])
    resposta = SimpleNamespace(role="assistant", images=None)
    nova = SimpleNamespace(role="user", images=[_url("image/jpeg", JPEG)] * 2)
    assert imagens.conferir_pedido([antiga, resposta, nova]) == 2
    assert antiga.images is None and len(nova.images) == 2
    demais = SimpleNamespace(role="user", images=[_url("image/png", PNG)] * 4)
    with pytest.raises(imagens.ErroImagem, match="no máximo"):
        imagens.conferir_pedido([demais])


def _mensagens():
    return [
        Message(role=Role.SYSTEM, content="regras"),
        Message(
            role=Role.USER, content="o que é isso?", images=[_url("image/png", PNG)]
        ),
    ]


def test_openai_gets_input_image_parts():
    payload = build_openai_payload("gpt-teste", _mensagens(), 100)
    [item] = payload["input"]
    assert item["role"] == "user"
    assert item["content"][0] == {"type": "input_text", "text": "o que é isso?"}
    assert item["content"][1]["type"] == "input_image"
    assert item["content"][1]["image_url"].startswith("data:image/png;base64,")
    assert "imagens" not in str(payload.keys())


def test_anthropic_gets_base64_image_blocks():
    payload = build_anthropic_payload("claude-teste", _mensagens(), 100)
    [item] = payload["messages"]
    bloco = item["content"][0]
    assert bloco["type"] == "image"
    assert bloco["source"]["media_type"] == "image/png"
    assert base64.b64decode(bloco["source"]["data"]) == PNG
    assert item["content"][1] == {"type": "text", "text": "o que é isso?"}


def test_text_only_messages_stay_the_same():
    msgs = [Message(role=Role.USER, content="oi")]
    assert build_openai_payload("gpt-teste", msgs, 100)["input"] == [
        {"role": "user", "content": "oi"}
    ]
    assert build_anthropic_payload("claude-teste", msgs, 100)["messages"] == [
        {"role": "user", "content": "oi"}
    ]
