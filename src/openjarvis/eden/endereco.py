"""Éden: endereço do Éden para os celulares (HTTPS do Tailscale).

Descoberto pelo iniciar-eden / instalar.sh e passado em EDEN_ENDERECO_CELULAR.
Só vale o endereço com cadeado do Tailscale (https://….ts.net), sem
caminho, usuário ou senha. Porta só 8443 a 8447: o Éden de outra pessoa no
mesmo servidor (nova-pessoa.sh) fica em https://SERVIDOR.ts.net:8443, :8444…
"""

from __future__ import annotations

import os
import re

_ENDERECO_CELULAR = re.compile(
    r"^https://[a-z0-9-]+(\.[a-z0-9-]+)*\.ts\.net(:844[3-7])?$"
)


def endereco_celular() -> str | None:
    valor = os.environ.get("EDEN_ENDERECO_CELULAR", "").strip().rstrip("/").lower()
    return valor if _ENDERECO_CELULAR.match(valor) else None
