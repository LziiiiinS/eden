"""Security middleware -- HTTP security headers and request guards."""

from __future__ import annotations

from typing import Any

__all__ = ["SECURITY_HEADERS", "create_security_middleware"]


def create_security_middleware() -> Any:
    """Create a FastAPI middleware that adds security headers.

    Returns a middleware class/callable, or None if FastAPI is not available.

    Headers added:
    - X-Content-Type-Options: nosniff
    - X-Frame-Options: DENY
    - X-XSS-Protection: 1; mode=block
    - Strict-Transport-Security: max-age=31536000; includeSubDomains
    - Referrer-Policy: strict-origin-when-cross-origin
    - Permissions-Policy: camera=(), microphone=(self), geolocation=(self)

    OPTIONS requests are passed through without headers so that
    CORS preflight is not blocked.
    """
    try:
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response
    except ImportError:
        return None

    class SecurityHeadersMiddleware(BaseHTTPMiddleware):
        async def dispatch(self, request: Request, call_next: Any) -> Response:
            # Let CORS preflight requests pass through without
            # security headers that would conflict with CORS.
            if request.method == "OPTIONS":
                return await call_next(request)

            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Strict-Transport-Security"] = (
                "max-age=31536000; includeSubDomains"
            )
            # setdefault: uma rota pode pedir algo mais restrito (ex.: a volta
            # do Google usa "no-referrer" para o código não vazar).
            response.headers.setdefault(
                "Referrer-Policy", "strict-origin-when-cross-origin"
            )
            # microphone=(self): the chat UI records voice input from this same
            # origin. An empty allowlist blocked its own feature.
            # Éden: geolocation=(self) para "melhor caminho saindo daqui" (só
            # quando a pessoa liga na página Rotas; o navegador pede permissão).
            response.headers["Permissions-Policy"] = SECURITY_HEADERS[
                "Permissions-Policy"
            ]
            # media-src blob: lets the UI play synthesized speech, which arrives
            # as a blob URL; default-src alone refused it.
            # Éden: o app traz fontes (KaTeX) e uma textura de fundo embutidas
            # como data: — o teste no navegador (Chromium) mostrou que a regra
            # bloqueava as duas. data: não busca nada fora do Éden.
            response.headers["Content-Security-Policy"] = SECURITY_HEADERS[
                "Content-Security-Policy"
            ]
            return response

    return SecurityHeadersMiddleware


# Also export the header values as constants for testing
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "X-XSS-Protection": "1; mode=block",
    "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(self), geolocation=(self)",
    "Content-Security-Policy": (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval'; "
        "img-src 'self' data: blob:; font-src 'self' data:; "
        "media-src 'self' blob:"
    ),
}
