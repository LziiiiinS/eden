"""Éden: no servidor do Éden, só ficam ligadas as rotas que o Éden usa.

O servidor herdado do OpenJarvis traz muitas funções (agentes com
ferramentas, conectores, memória que lê arquivos, pesquisa aprofundada, troca
de chaves, webhooks, painéis). No Éden elas ficam escondidas na tela, mas
continuavam respondendo para quem tivesse a chave de acesso — e algumas
gastavam nas IAs sem passar pelo limite do Éden (revisão de segurança de
15/10/2026). Aqui elas são desligadas de verdade: a rota deixa de existir.

Fica ligado: conversa (só com streaming), lista de modelos, informações do
servidor, economia, transcrição de voz, as rotas /v1/eden/... e o app.
"""

from __future__ import annotations

import logging
import os
from typing import Iterable, List, Optional, Set, Tuple

from openjarvis.eden.settings import EdenSettings, get_settings

logger = logging.getLogger(__name__)

# (método, caminho) que o app do Éden usa.
ALLOWED_ROUTES: Set[Tuple[str, str]] = {
    ("GET", "/health"),
    ("GET", "/v1/models"),
    ("GET", "/v1/info"),
    ("GET", "/v1/savings"),
    ("POST", "/v1/chat/completions"),
    ("POST", "/v1/speech/transcribe"),
    ("GET", "/v1/speech/health"),
}

# Rotas próprias do Éden (conversas, gastos).
ALLOWED_PREFIXES: Tuple[str, ...] = ("/v1/eden/",)

# Métodos que o próprio framework acrescenta e não mudam nada.
_HARMLESS_METHODS = {"HEAD", "OPTIONS"}


def eden_mode_enabled(settings: Optional[EdenSettings] = None) -> bool:
    """O servidor está rodando como Éden (seção [eden] no config.toml)?"""
    try:
        return bool((settings or get_settings()).enabled)
    except Exception:  # noqa: BLE001
        return False


def is_allowed(path: str, methods: Iterable[str]) -> bool:
    """A rota (caminho + métodos) é uma das que o Éden usa?"""
    if any(path.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return True
    wanted = {m.upper() for m in methods} - _HARMLESS_METHODS
    if not wanted:
        return False
    return all((method, path) in ALLOWED_ROUTES for method in wanted)


def restrict_routes_for_eden(app, settings: Optional[EdenSettings] = None) -> None:
    """Remove do app todas as rotas que o Éden não usa (inclui WebSockets,
    documentação da API, painéis e webhooks). Não faz nada fora do Éden.

    Deve ser chamada depois de registrar as rotas da API e antes de montar
    os arquivos do app (que são acrescentados depois e continuam servidos).
    """
    if not eden_mode_enabled(settings):
        if os.environ.get("EDEN_IMAGEM") == "1":
            # Imagem do Éden ligada sem a configuração do Éden (por exemplo,
            # "jarvis serve" direto, sem o iniciar do Éden): recusar é mais
            # seguro do que subir o OpenJarvis completo.
            raise RuntimeError(
                "Éden: a seção [eden] do config.toml não foi encontrada. Ligue "
                "pelo iniciar do Éden (deploy/eden/iniciar-no-conteiner.sh)."
            )
        return
    from fastapi.routing import APIRoute

    kept: List[object] = []
    removed: List[str] = []
    for route in list(app.router.routes):
        path = getattr(route, "path", "")
        if isinstance(route, APIRoute) and is_allowed(path, route.methods or ()):
            kept.append(route)
        else:
            removed.append(path or type(route).__name__)
    app.router.routes[:] = kept
    # Sem documentação automática da API (mapa de todas as rotas).
    app.openapi_url = None
    app.docs_url = None
    app.redoc_url = None
    app.state.eden_removed_routes = removed
    logger.info(
        "Éden: %d rotas ligadas, %d desligadas (só o que o Éden usa)",
        len(kept),
        len(removed),
    )
