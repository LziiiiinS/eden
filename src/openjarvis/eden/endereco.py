"""Éden: endereço do Éden para os celulares (HTTPS do Tailscale).

Descoberto pelo iniciar-eden / instalar.sh e passado em EDEN_ENDERECO_CELULAR.
Só vale o endereço com cadeado do Tailscale (https://….ts.net), sem porta,
caminho, usuário ou senha.
"""

from __future__ import annotations

import os
import re

_ENDERECO_CELULAR = re.compile(r"^https://[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net$")


def endereco_celular() -> str | None:
    valor = os.environ.get("EDEN_ENDERECO_CELULAR", "").strip().rstrip("/").lower()
    return valor if _ENDERECO_CELULAR.match(valor) else None
