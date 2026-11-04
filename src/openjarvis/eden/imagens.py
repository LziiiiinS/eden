"""Éden: imagens na conversa (print, foto) — pedido do Levi, 04/11.

O app reduz a imagem antes de mandar (até ~1600 px, JPEG). Aqui o servidor
confere tudo antes de passar para a IA:

- só na **última** mensagem da pessoa (as antigas não são mandadas de novo:
  custa menos e a IA já respondeu sobre elas);
- no máximo ``MAX_IMAGENS`` por mensagem, cada uma até ``MAX_BYTES`` depois
  de decodificada, e só PNG, JPEG, WebP ou GIF — conferidos pelos primeiros
  bytes do arquivo, não pelo nome;
- só imagem vinda no próprio pedido (``data:``): nunca um endereço de fora
  (o servidor não busca nada na internet por causa de uma imagem).

A imagem não fica guardada no servidor: vai para a IA e some. O que a imagem
mostra é tratado como dado, como um documento.
"""

from __future__ import annotations

import base64
import binascii
import re
from typing import Any, List, Optional, Tuple

MAX_IMAGENS = 3
MAX_BYTES = 3 * 1024 * 1024
# Reserva de gasto por imagem (a OpenAI cobra ~800-1100 tokens por imagem de
# 1024 px; o Claude, ~1600 para 1,15 megapixel). Fica por cima.
TOKENS_POR_IMAGEM = 1800

_DATA_URL = re.compile(
    r"^data:(image/(?:png|jpeg|webp|gif));base64,([A-Za-z0-9+/=\s]+)$"
)


class ErroImagem(ValueError):
    pass


def _tipo_pelos_bytes(dados: bytes) -> Optional[str]:
    if dados.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if dados.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if dados[:4] == b"RIFF" and dados[8:12] == b"WEBP":
        return "image/webp"
    if dados[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return None


def conferir_uma(valor: Any) -> str:
    """Devolve a imagem como ``data:`` limpo (sem espaços) ou recusa."""
    if not isinstance(valor, str) or len(valor) > MAX_BYTES * 2:
        raise ErroImagem("imagem grande demais (até 3 MB)")
    m = _DATA_URL.match(valor.strip())
    if not m:
        raise ErroImagem("só imagens PNG, JPEG, WebP ou GIF enviadas pelo app")
    tipo, corpo = m.group(1), re.sub(r"\s+", "", m.group(2))
    try:
        dados = base64.b64decode(corpo, validate=True)
    except (binascii.Error, ValueError):
        raise ErroImagem("imagem estragada") from None
    if not dados or len(dados) > MAX_BYTES:
        raise ErroImagem("imagem grande demais (até 3 MB)")
    real = _tipo_pelos_bytes(dados)
    if real is None or real != tipo:
        raise ErroImagem("o arquivo não é a imagem que diz ser")
    return f"data:{tipo};base64,{corpo}"


def conferir_pedido(mensagens: List[Any]) -> int:
    """Confere as imagens do pedido (objetos com ``role`` e ``images``).
    Tira as imagens de todas as mensagens menos a última da pessoa e devolve
    quantas ficaram. Recusa com ``ErroImagem``."""
    ultima_pessoa = None
    for i, m in enumerate(mensagens):
        if getattr(m, "role", "") == "user":
            ultima_pessoa = i
    total = 0
    for i, m in enumerate(mensagens):
        imagens = getattr(m, "images", None)
        if not imagens:
            continue
        if i != ultima_pessoa:
            m.images = None
            continue
        if not isinstance(imagens, list) or len(imagens) > MAX_IMAGENS:
            raise ErroImagem(f"no máximo {MAX_IMAGENS} imagens por mensagem")
        m.images = [conferir_uma(v) for v in imagens]
        total = len(m.images)
    return total


def separar(data_url: str) -> Tuple[str, str]:
    """``data:image/png;base64,XXX`` → ("image/png", "XXX")."""
    cabeca, _, corpo = data_url.partition(",")
    return cabeca[len("data:") :].split(";", 1)[0], corpo


def contar(mensagens: List[Any]) -> int:
    return sum(len(getattr(m, "images", None) or []) for m in mensagens)
