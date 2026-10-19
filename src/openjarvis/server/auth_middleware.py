"""API key authentication middleware for the OpenJarvis server."""

from __future__ import annotations

import base64
import logging
import os
import secrets

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# Éden: a única rota /v1 que funciona sem a chave. Ela troca um código curto
# (5 minutos, uso único, poucas tentativas) pela chave, para ligar o app do
# iPhone aberto pela tela de início (openjarvis/eden/pareamento.py). Caminho e
# método exatos; nenhum outro caminho fica de fora. A comparação usa o caminho
# que o roteador usa (scope["path"], já decodificado), não request.url.path:
# "/usar%3Fx" vira url.path == "/usar" mas é roteado como "/usar?x" (revisão
# independente de 15/10).
_ROTAS_SEM_CHAVE = frozenset(
    {
        ("POST", "/v1/eden/pareamento/usar"),
        # Volta da autorização do Google (o navegador não leva a chave aqui);
        # só aceita um "state" de uso único criado por quem tem a chave.
        ("GET", "/v1/eden/google/retorno"),
    }
)

_WS_AUTH_PROTOCOL = "openjarvis.auth.v1"
_WS_KEY_PROTOCOL_PREFIX = "openjarvis.key.b64url."


def _chave_de_aparelho(presented: str) -> int | None:
    """Éden (Parte 5): chave própria de um aparelho (``oj_ap_…``), se valer."""
    try:
        from openjarvis.eden.aparelhos import conferir

        return conferir(presented)
    except Exception:  # noqa: BLE001 — nunca derruba o pedido
        logger.exception("Éden: falha ao conferir a chave do aparelho")
        return None


def _api_keys_match(presented: str, expected: str) -> bool:
    """Compare API keys as bytes so non-ASCII values do not raise ``TypeError``."""
    try:
        presented_bytes = presented.encode("utf-8")
        expected_bytes = expected.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return secrets.compare_digest(presented_bytes, expected_bytes)


class AuthMiddleware(BaseHTTPMiddleware):
    """Validates ``Authorization: Bearer <key>`` on ``/v1/*`` and ``/api/*`` routes.

    Webhook routes and health checks are exempt — they use
    per-channel signature verification instead.
    """

    def __init__(self, app, api_key: str = "") -> None:  # noqa: ANN001
        super().__init__(app)
        self._api_key = api_key or os.environ.get("OPENJARVIS_API_KEY", "")

    async def dispatch(self, request: Request, call_next):  # noqa: ANN001
        # Browser CORS preflights never carry Authorization, and rejecting
        # them here means they never reach CORSMiddleware to get
        # Access-Control-Allow-* headers, breaking cross-origin access
        # outright (#758). Do not exempt arbitrary OPTIONS requests: a real
        # preflight is identified by both headers required by the CORS protocol.
        if self._is_cors_preflight(request):
            return await call_next(request)
        if (request.method, request.scope.get("path", "")) in _ROTAS_SEM_CHAVE:
            return await call_next(request)
        if self._api_key and self._requires_auth(request.url.path):
            auth = request.headers.get("Authorization", "")
            if not auth:
                return JSONResponse(
                    {"detail": "Missing Authorization header"},
                    status_code=401,
                )
            scheme, _, token = auth.partition(" ")
            # Constant-time comparison to avoid leaking the key via timing.
            if scheme.lower() != "bearer":
                return JSONResponse({"detail": "Invalid API key"}, status_code=401)
            if _api_keys_match(token, self._api_key):
                request.state.eden_aparelho = None  # chave principal
            else:
                aparelho = _chave_de_aparelho(token)
                if aparelho is None:
                    return JSONResponse(
                        {"detail": "Invalid API key"},
                        status_code=401,
                    )
                request.state.eden_aparelho = aparelho
            # Éden: o registro de ações anota de qual aparelho veio o pedido.
            from openjarvis.eden import quem

            marca = quem.definir(request.state.eden_aparelho)
            try:
                return await call_next(request)
            finally:
                quem.soltar(marca)
        return await call_next(request)

    @staticmethod
    def _is_cors_preflight(request: Request) -> bool:
        return (
            request.method == "OPTIONS"
            and bool(request.headers.get("Origin"))
            and bool(request.headers.get("Access-Control-Request-Method"))
        )

    @staticmethod
    def _requires_auth(path: str) -> bool:
        """Protect API routes, metrics and API docs; leave the UI/health open.

        ``/metrics`` exposes request/token counters that should not be readable
        by unauthenticated clients, so it is gated alongside ``/v1`` and
        ``/api``. ``/health`` stays open for liveness probes.

        The OpenAPI schema and its viewers (``/openapi.json``, ``/docs``,
        ``/redoc``) are gated too: on an exposed deployment they hand an
        unauthenticated client a complete map of every route, parameter and
        payload shape — useful reconnaissance for probing the authenticated
        endpoints. This only applies when an API key is configured at all, so
        keyless local use is unchanged.
        """
        return (
            path.startswith("/v1/")
            or path.startswith("/api/")
            or path == "/metrics"
            or path.startswith("/metrics/")
            or path in ("/openapi.json", "/docs", "/redoc")
            or path.startswith("/docs/")
            or path.startswith("/redoc/")
        )


def generate_api_key() -> str:
    """Generate a new API key with ``oj_sk_`` prefix."""
    return f"oj_sk_{secrets.token_urlsafe(32)}"


def check_bind_safety(host: str, *, api_key: str) -> None:
    """Refuse to bind non-loopback without an API key.

    Raises ``SystemExit`` if *host* is not a loopback address and
    *api_key* is empty.
    """
    import ipaddress
    import sys

    try:
        is_loop = ipaddress.ip_address(host).is_loopback
    except ValueError:
        is_loop = host in ("localhost", "")

    if not is_loop and not api_key:
        logger.error(
            "Binding to %s requires OPENJARVIS_API_KEY to be set. "
            "Run: jarvis auth generate-key",
            host,
        )
        sys.exit(1)


def _websocket_key_protocol(api_key: str) -> str:
    """Encode an API key as a browser-safe WebSocket protocol token."""
    try:
        encoded = base64.urlsafe_b64encode(api_key.encode("utf-8")).decode("ascii")
    except UnicodeEncodeError:
        return ""
    return f"{_WS_KEY_PROTOCOL_PREFIX}{encoded.rstrip('=')}"


def _offered_websocket_auth(websocket) -> tuple[str, str | None]:  # noqa: ANN001
    """Return the credential protocol and protocol to negotiate, if well formed.

    ASGI exposes the complete, flattened protocol offer in ``scope``. Reading
    it avoids ambiguity from repeated ``Sec-WebSocket-Protocol`` header fields.
    Exactly one stable protocol marker and one encoded credential are required.
    """
    offered = getattr(websocket, "scope", {}).get("subprotocols", [])
    if not isinstance(offered, (list, tuple)) or len(offered) != 2:
        return "", None
    if offered.count(_WS_AUTH_PROTOCOL) != 1:
        return "", None
    credentials = [
        protocol
        for protocol in offered
        if isinstance(protocol, str) and protocol != _WS_AUTH_PROTOCOL
    ]
    if len(credentials) != 1 or not credentials[0].startswith(_WS_KEY_PROTOCOL_PREFIX):
        return "", None
    if credentials[0] == _WS_KEY_PROTOCOL_PREFIX:
        return "", None
    return credentials[0], _WS_AUTH_PROTOCOL


def authenticate_websocket(
    websocket,  # noqa: ANN001
    expected_key: str,
) -> tuple[bool, str | None]:
    """Authenticate a WebSocket and return its negotiated auth subprotocol.

    Programmatic clients can send ``Authorization: Bearer <key>``. Browser
    clients, which cannot set that header, offer ``openjarvis.auth.v1`` plus a
    marked, unpadded base64url encoding of the UTF-8 key. The encoding only
    makes the credential valid subprotocol syntax; it does not make it secret.
    """
    credential_protocol, selected_protocol = _offered_websocket_auth(websocket)

    # Match AuthMiddleware's local, keyless behavior. If a stale client still
    # offers a well-formed auth protocol, negotiate it so the browser does not
    # fail an otherwise allowed handshake.
    if not expected_key:
        return True, selected_protocol

    auth = websocket.headers.get("authorization", "")
    scheme, _, header_token = auth.partition(" ")
    header_valid = scheme.lower() == "bearer" and _api_keys_match(
        header_token, expected_key
    )

    expected_protocol = _websocket_key_protocol(expected_key)
    protocol_valid = bool(credential_protocol and expected_protocol) and (
        _api_keys_match(credential_protocol, expected_protocol)
    )
    if not (header_valid or protocol_valid):
        # Éden: chave própria do aparelho (no cabeçalho ou no protocolo).
        presented = header_token if scheme.lower() == "bearer" else ""
        if not presented and credential_protocol:
            presented = _decode_key_protocol(credential_protocol)
        if presented and _chave_de_aparelho(presented) is not None:
            return True, selected_protocol
    return header_valid or protocol_valid, selected_protocol


def _decode_key_protocol(protocol: str) -> str:
    encoded = protocol[len(_WS_KEY_PROTOCOL_PREFIX) :]
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (ValueError, UnicodeError):
        return ""


def websocket_authorized(websocket, expected_key: str) -> bool:  # noqa: ANN001
    """Return ``True`` if a WebSocket connection presents the expected key.

    ``AuthMiddleware`` is a ``BaseHTTPMiddleware`` and never sees WebSocket
    upgrade requests, so streaming endpoints must check the token themselves
    in the handshake before calling ``websocket.accept()``.

    When *expected_key* is empty, authentication is disabled (the loopback /
    local-only default, matching :class:`AuthMiddleware`) and all connections
    are allowed. See :func:`authenticate_websocket` for the supported
    credential transports. URL query parameters are deliberately not accepted
    because request targets commonly appear in access logs and browser history.
    """
    return authenticate_websocket(websocket, expected_key)[0]
