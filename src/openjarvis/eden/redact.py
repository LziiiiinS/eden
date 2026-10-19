"""Éden: apaga de textos qualquer coisa com cara de chave antes de mostrar
ou registrar (mensagens de erro das empresas de IA, registros do servidor)."""

from __future__ import annotations

import re

_PATTERNS = (
    (re.compile(r"sk-ant-[A-Za-z0-9_*\-]+"), "sk-ant-…"),
    (re.compile(r"sk-[A-Za-z0-9_*\-]{8,}"), "sk-…"),
    (re.compile(r"oj_sk_[A-Za-z0-9_\-]+"), "oj_sk_…"),
    # Chave de um aparelho (Parte 5).
    (re.compile(r"oj_ap_[A-Za-z0-9_\-]+"), "oj_ap_…"),
    # Google: token de acesso (ya29.) e de renovação (1//).
    (re.compile(r"ya29\.[A-Za-z0-9._\-]+"), "ya29.…"),
    (re.compile(r"\b1//[A-Za-z0-9._\-]{10,}"), "1//…"),
    # Tokens JWT (ex.: o token de longa duração do Home Assistant).
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9._\-]+"), "eyJ…"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=\-]+"), "Bearer …"),
    (re.compile(r"(?i)(x-api-key[\"']?\s*[:=]\s*[\"']?)[^\s\"',}]+"), r"\1…"),
    # Chave do Notion (conexão interna).
    (re.compile(r"(?:ntn|secret)_[A-Za-z0-9]{20,}"), "ntn_…"),
    # Chave no endereço (ex.: TomTom ...?key=...).
    (re.compile(r"(?i)([?&](?:key|api_key|apikey)=)[^&\s\"']+"), r"\1…"),
)


def redact_secrets(text: object) -> str:
    """Devolve o texto sem chaves (troca por reticências)."""
    out = str(text)
    for pattern, replacement in _PATTERNS:
        out = pattern.sub(replacement, out)
    return out
