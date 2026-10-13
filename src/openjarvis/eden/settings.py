"""Éden: configurações próprias (seção [eden] do config.toml).

O carregador do OpenJarvis ignora seções que não conhece, então o Éden lê a
seção [eden] do mesmo arquivo por conta própria. Nada aqui é segredo: as
chaves das IAs ficam em variáveis de ambiente do servidor.

Exemplo (valores padrão):

    [eden.ias]
    dia_a_dia = "gpt-6.1-sol"        # ChatGPT (OpenAI)
    missao = "claude-sonnet-5-5"     # Claude (Anthropic)
    esforco_dia_a_dia = "low"
    max_saida_tokens = 8000

    [eden.limites]                   # US$ por mês, por empresa
    openai = 10.0
    anthropic = 15.0

    [eden.precos]                    # US$ por 1 milhão de tokens [entrada, saída]
    "gpt-6.1-sol" = [2.0, 10.0]

    [eden.precos_transcricao]        # US$ por minuto de áudio
    "gpt-transcribe" = 0.0045
"""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass, field
from datetime import timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

import tomllib

logger = logging.getLogger(__name__)

# Preços oficiais conferidos em 13/10/2026 (US$ por 1 milhão de tokens).
DEFAULT_PRICES: Dict[str, Tuple[float, float]] = {
    "gpt-6-astra": (10.0, 50.0),
    "gpt-6.1-sol": (2.0, 10.0),
    "gpt-6-luna": (0.10, 0.50),
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}

# US$ por minuto de áudio.
DEFAULT_TRANSCRIPTION_PRICES: Dict[str, float] = {
    "gpt-transcribe": 0.0045,
}

DEFAULT_LIMITS_USD: Dict[str, float] = {"openai": 10.0, "anthropic": 15.0}

# Provedores cujo gasto o Éden controla.
TRACKED_PROVIDERS = ("openai", "anthropic")


@dataclass
class EdenSettings:
    # True quando o config.toml tem a seção [eden] (servidor do Éden). Sem ela
    # o servidor se comporta como o OpenJarvis original na lista de modelos.
    enabled: bool = False
    daily_model: str = "gpt-6.1-sol"
    mission_model: str = "claude-sonnet-5-5"
    daily_reasoning_effort: str = "low"
    max_output_tokens: int = 8000
    monthly_limits_usd: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_LIMITS_USD)
    )
    prices: Dict[str, Tuple[float, float]] = field(
        default_factory=lambda: dict(DEFAULT_PRICES)
    )
    transcription_prices: Dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TRANSCRIPTION_PRICES)
    )
    # Brasil não tem horário de verão desde 2019: o mês vira à meia-noite de
    # Brasília (UTC-3).
    utc_offset_hours: float = -3.0

    @property
    def tz(self) -> timezone:
        return timezone(timedelta(hours=self.utc_offset_hours))

    def limit_for(self, provider: str) -> Optional[float]:
        value = self.monthly_limits_usd.get(provider)
        return float(value) if value is not None else None

    def token_price(self, provider: str, model: str) -> Tuple[float, float]:
        """Preço [entrada, saída] por 1M de tokens.

        Modelo sem preço configurado usa o mais caro conhecido do mesmo
        provedor, para o limite nunca ficar subestimado.
        """
        if model in self.prices:
            return self.prices[model]
        same_provider = [
            price
            for name, price in self.prices.items()
            if _provider_of(name) == provider
        ]
        pool = same_provider or list(self.prices.values()) or [(10.0, 50.0)]
        logger.warning(
            "Éden: modelo %s sem preço configurado; usando o mais caro conhecido",
            model,
        )
        return max(pool, key=lambda p: p[0] + p[1])

    def token_cost(
        self, provider: str, model: str, input_tokens: int, output_tokens: int
    ) -> float:
        price_in, price_out = self.token_price(provider, model)
        return (
            max(0, input_tokens) * price_in + max(0, output_tokens) * price_out
        ) / 1_000_000

    def transcription_cost(self, model: str, seconds: float) -> float:
        price = self.transcription_prices.get(model)
        if price is None:
            price = max(self.transcription_prices.values(), default=0.01)
        return max(0.0, seconds) / 60.0 * price


def _provider_of(model: str) -> str:
    if model.startswith("claude-"):
        return "anthropic"
    if model.startswith(("gpt-", "o1-", "o3-", "o4-", "chatgpt-")):
        return "openai"
    return ""


def _config_file() -> Path:
    env = os.environ.get("OPENJARVIS_CONFIG")
    if env:
        return Path(env).expanduser().resolve()
    from openjarvis.core.paths import get_config_path

    return get_config_path()


def _as_price_pair(value: Any) -> Optional[Tuple[float, float]]:
    if (
        isinstance(value, (list, tuple))
        and len(value) == 2
        and all(isinstance(v, (int, float)) and v >= 0 for v in value)
    ):
        return float(value[0]), float(value[1])
    return None


def settings_from_dict(data: Dict[str, Any]) -> EdenSettings:
    """Monta as configurações a partir da seção [eden] (já lida do TOML)."""
    s = EdenSettings(enabled=True)
    ias = data.get("ias", {}) if isinstance(data.get("ias"), dict) else {}
    if isinstance(ias.get("dia_a_dia"), str) and ias["dia_a_dia"].strip():
        s.daily_model = ias["dia_a_dia"].strip()
    if isinstance(ias.get("missao"), str) and ias["missao"].strip():
        s.mission_model = ias["missao"].strip()
    if isinstance(ias.get("esforco_dia_a_dia"), str):
        s.daily_reasoning_effort = ias["esforco_dia_a_dia"].strip()
    if isinstance(ias.get("max_saida_tokens"), int) and ias["max_saida_tokens"] > 0:
        s.max_output_tokens = ias["max_saida_tokens"]

    limits = data.get("limites")
    if isinstance(limits, dict):
        for provider, value in limits.items():
            if isinstance(value, (int, float)) and value >= 0:
                s.monthly_limits_usd[str(provider)] = float(value)

    prices = data.get("precos")
    if isinstance(prices, dict):
        for model, value in prices.items():
            pair = _as_price_pair(value)
            if pair is not None:
                s.prices[str(model)] = pair

    tprices = data.get("precos_transcricao")
    if isinstance(tprices, dict):
        for model, value in tprices.items():
            if isinstance(value, (int, float)) and value >= 0:
                s.transcription_prices[str(model)] = float(value)

    offset = data.get("fuso_utc")
    if isinstance(offset, (int, float)) and -14 <= offset <= 14:
        s.utc_offset_hours = float(offset)
    return s


def load_settings(path: Optional[Path] = None) -> EdenSettings:
    config_path = path or _config_file()
    try:
        with open(config_path, "rb") as fh:
            data = tomllib.load(fh)
    except FileNotFoundError:
        return EdenSettings()
    except Exception:
        logger.warning("Éden: não consegui ler %s; usando padrões", config_path)
        return EdenSettings()
    section = data.get("eden")
    if not isinstance(section, dict):
        return EdenSettings()
    return settings_from_dict(section)


_lock = threading.Lock()
_current: Optional[EdenSettings] = None


def get_settings() -> EdenSettings:
    global _current
    with _lock:
        if _current is None:
            _current = load_settings()
        return _current


def set_settings(settings: Optional[EdenSettings]) -> None:
    """Troca as configurações em uso (testes e inicialização do servidor)."""
    global _current
    with _lock:
        _current = settings
