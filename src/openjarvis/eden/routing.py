"""Éden: qual IA responde cada pedido.

O app escolhe um destes "modelos" do Éden, e o servidor troca pelo modelo de
verdade da configuração:

- ``eden-auto``: o Éden decide. Dia a dia vai para o ChatGPT; pedidos de
  entrega (documento, proposta, resposta a cliente, texto longo) vão para o
  Claude. Numa conversa que já virou missão, segue no Claude.
- ``eden-dia``: sempre ChatGPT.
- ``eden-missao``: sempre Claude.

A regra é simples e fica à vista (motivo em cada resposta), para o Levi poder
corrigir trocando o modo na hora.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional

from openjarvis.eden.settings import EdenSettings

AUTO = "eden-auto"
AUTO_IN_MISSION = "eden-auto+missao"
DAILY = "eden-dia"
MISSION = "eden-missao"
VIRTUAL_MODELS = (AUTO, DAILY, MISSION)

# Pedidos com mais caracteres que isto contam como missão.
LONG_REQUEST_CHARS = 1500

MODE_DAILY = "dia"
MODE_MISSION = "missao"

# Motivos (códigos sem acento, vão em cabeçalho HTTP; o app mostra o texto).
REASON_CHOSEN = "escolha"  # o modo foi escolhido no app
REASON_COMMAND = "comando"  # /missao ou /dia no começo da mensagem
REASON_DELIVERABLE = "entrega"  # documento, proposta, planilha...
REASON_CLIENT = "cliente"  # resposta ou mensagem para cliente
REASON_LONG = "longo"  # pedido muito longo
REASON_CONTINUES = "continua"  # conversa já estava em missão
REASON_DEFAULT = "padrao"  # dia a dia


@dataclass(frozen=True)
class RouteDecision:
    requested: str
    mode: str
    model: str
    provider: str
    reason: str

    def headers(self) -> dict:
        return {
            "X-Eden-Mode": self.mode,
            "X-Eden-Model": self.model,
            "X-Eden-Provider": self.provider,
            "X-Eden-Reason": self.reason,
        }


def is_virtual(model: str) -> bool:
    return model in VIRTUAL_MODELS or model == AUTO_IN_MISSION


def _normalize(text: str) -> str:
    """Minúsculas e sem acentos, para as regras não dependerem de digitação."""
    decomposed = unicodedata.normalize("NFKD", text.lower())
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch))


_COMMAND_MISSION = re.compile(r"^\s*(/missao\b|missao\s*:)")
_COMMAND_DAILY = re.compile(r"^\s*(/dia\b|/rapido\b|dia a dia\s*:)")

_ACTION = (
    r"(escrev\w*|redi[gj]\w*|elabor\w*|cri[ae]r?|cria|mont\w*|prepar\w*|"
    r"fa[cz]a|fazer|faz|ger[ae]r?|gera|revis\w*|reescrev\w*|corrig\w*|corrij\w*|"
    r"analis\w*|estrutur\w*|melhor[ae]\w*|preciso de|me ajud\w* a)"
)
_DELIVERABLE = (
    r"(propostas?|contratos?|relatorios?|apresentac\w*|slides?|planilhas?|"
    r"orcamentos?|curriculos?|documentos?|artigos?|briefings?|cronogramas?|"
    r"plano de (negocios?|acao|projeto|marketing|trabalho)|manual|atas?|"
    r"roteiro de (video|apresentacao)|e-?mail (profissional|formal))"
)
_DELIVERABLE_REQUEST = re.compile(
    rf"\b{_ACTION}\b.*\b{_DELIVERABLE}\b|\b{_DELIVERABLE}\b.*\b{_ACTION}\b",
    re.DOTALL,
)
_CLIENT = re.compile(
    r"\b(responder|resposta|respond\w*|e-?mail|mensagem|escrev\w*|redi[gj]\w*)\b"
    r".*\bclientes?\b|\bclientes?\b.*\b(responder|resposta|respond\w*|e-?mail|"
    r"mensagem)\b",
    re.DOTALL,
)


def classify(text: str, *, in_mission: bool = False) -> tuple[str, str]:
    """Decide o modo de um pedido. Devolve (modo, motivo)."""
    norm = _normalize(text or "")
    if _COMMAND_DAILY.search(norm):
        return MODE_DAILY, REASON_COMMAND
    if _COMMAND_MISSION.search(norm):
        return MODE_MISSION, REASON_COMMAND
    if in_mission:
        return MODE_MISSION, REASON_CONTINUES
    # O tamanho vem antes das buscas por palavras: assim elas só rodam em
    # textos curtos e nunca ficam lentas.
    if len(text or "") >= LONG_REQUEST_CHARS:
        return MODE_MISSION, REASON_LONG
    if _CLIENT.search(norm):
        return MODE_MISSION, REASON_CLIENT
    if _DELIVERABLE_REQUEST.search(norm):
        return MODE_MISSION, REASON_DELIVERABLE
    return MODE_DAILY, REASON_DEFAULT


def resolve(
    requested_model: str, last_user_text: str, settings: EdenSettings
) -> Optional[RouteDecision]:
    """Troca um modelo do Éden pelo modelo de verdade. None se não for do Éden."""
    if not is_virtual(requested_model):
        return None
    if requested_model == DAILY:
        mode, reason = MODE_DAILY, REASON_CHOSEN
    elif requested_model == MISSION:
        mode, reason = MODE_MISSION, REASON_CHOSEN
    else:
        mode, reason = classify(
            last_user_text, in_mission=requested_model == AUTO_IN_MISSION
        )
    model = settings.mission_model if mode == MODE_MISSION else settings.daily_model
    provider = "anthropic" if model.startswith("claude-") else "openai"
    return RouteDecision(
        requested=requested_model,
        mode=mode,
        model=model,
        provider=provider,
        reason=reason,
    )


_COMMAND_PREFIX = re.compile(
    r"^\s*(/miss[aã]o\b|/dia\b|/r[aá]pido\b)\s*", re.IGNORECASE
)


def strip_command(text: str) -> str:
    """Tira /missao, /dia ou /rapido do começo da mensagem enviada à IA."""
    return _COMMAND_PREFIX.sub("", text or "", count=1)
