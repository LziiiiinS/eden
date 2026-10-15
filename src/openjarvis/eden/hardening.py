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
    # Teto de tamanho para o corpo de todos os pedidos (a conversa não tinha).
    app.add_middleware(LimiteDeCorpo)
    # O registro de acesso não mostra o que vem depois do "?" (ex.: busca).
    esconder_consultas_no_registro()
    logger.info(
        "Éden: %d rotas ligadas, %d desligadas (só o que o Éden usa)",
        len(kept),
        len(removed),
    )


# ── teto de tamanho dos pedidos ──────────────────────────────────────────

LIMITE_PADRAO = 4 * 1024 * 1024
LIMITES_POR_CAMINHO: Tuple[Tuple[str, int], ...] = (
    # Rota sem chave (código do iPhone): o pedido tem poucos bytes.
    ("/v1/eden/pareamento/usar", 1024),
    ("/v1/speech/transcribe", 26 * 1024 * 1024),  # áudio até 25 MB
    ("/v1/eden/conversations/", 9 * 1024 * 1024),  # conversa inteira até 8 MB
)


class _CorpoGrande(Exception):
    pass


class LimiteDeCorpo:
    """Recusa (413) pedidos com corpo maior que o teto do caminho — pelo
    Content-Length e também contando o que chega (envio sem tamanho)."""

    def __init__(self, app) -> None:  # noqa: ANN001
        self.app = app

    @staticmethod
    def limite(caminho: str) -> int:
        for prefixo, teto in LIMITES_POR_CAMINHO:
            if caminho.startswith(prefixo):
                return teto
        return LIMITE_PADRAO

    @staticmethod
    async def _recusar(send) -> None:  # noqa: ANN001
        corpo = b'{"detail":"Pedido grande demais","code":"eden_grande_demais"}'
        await send(
            {
                "type": "http.response.start",
                "status": 413,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(corpo)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": corpo})

    async def __call__(self, scope, receive, send) -> None:  # noqa: ANN001
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return
        teto = self.limite(scope.get("path", ""))
        for nome, valor in scope.get("headers") or []:
            if nome == b"content-length":
                try:
                    if int(valor) > teto:
                        await self._recusar(send)
                        return
                except ValueError:
                    await self._recusar(send)
                    return
        recebido = 0
        respondeu = False

        async def receber():
            nonlocal recebido
            mensagem = await receive()
            if mensagem.get("type") == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > teto:
                    raise _CorpoGrande()
            return mensagem

        async def enviar(mensagem):
            nonlocal respondeu
            if mensagem.get("type") == "http.response.start":
                respondeu = True
            await send(mensagem)

        try:
            await self.app(scope, receber, enviar)
        except _CorpoGrande:
            if not respondeu:
                await self._recusar(send)


# ── registro de acesso sem o que vem depois do "?" ──────────────────────
#
# O servidor anota cada pedido ("GET /v1/eden/notas?busca=... 200"). O que vem
# depois do "?" pode ter o que a pessoa procurou nas notas ou o espaço que
# abriu; isso não precisa ficar no registro (revisão de segurança de 15/10,
# achado 18). Fica só o caminho, com "?…" no lugar.

ACCESS_LOGGER = "uvicorn.access"


class SemConsultaNoRegistro(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if (
            isinstance(args, tuple)
            and len(args) >= 3
            and isinstance(args[2], str)
            and "?" in args[2]
        ):
            caminho = args[2].split("?", 1)[0]
            record.args = args[:2] + (caminho + "?…",) + args[3:]
        return True


def esconder_consultas_no_registro() -> None:
    """Liga o filtro no registro de acesso (uma vez só). O filtro fica no
    "logger", então continua valendo depois que o uvicorn configura o
    registro (ele troca só os "handlers")."""
    registro = logging.getLogger(ACCESS_LOGGER)
    if not any(isinstance(f, SemConsultaNoRegistro) for f in registro.filters):
        registro.addFilter(SemConsultaNoRegistro())
