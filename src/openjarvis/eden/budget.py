"""Éden: limite de gastos por mês, por empresa de IA.

Cada uso das IAs (conversa e transcrição) fica anotado num banco SQLite no
servidor, com o custo calculado pelos preços da configuração. Antes de cada
pedido, o Éden confere se o gasto do mês mais uma reserva para o pedido cabe
no limite. Se não couber, o pedido é recusado antes de chegar na IA.

O crédito pré-pago nos sites da OpenAI e da Anthropic continua sendo uma
segunda trava, independente desta.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from openjarvis.eden.settings import TRACKED_PROVIDERS, EdenSettings

PROVIDER_LABEL = {"openai": "ChatGPT (OpenAI)", "anthropic": "Claude (Anthropic)"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS spending (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    at_ms INTEGER NOT NULL,
    month TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    audio_seconds REAL NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL,
    estimated INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS spending_month ON spending (month, provider);
"""


class BudgetExceeded(Exception):
    """O pedido passaria do limite do mês daquela IA."""

    def __init__(self, provider: str, spent: float, limit: float) -> None:
        self.provider = provider
        self.spent = spent
        self.limit = limit
        label = PROVIDER_LABEL.get(provider, provider)
        super().__init__(
            f"Limite do mês do {label} atingido: US$ {spent:.2f} de "
            f"US$ {limit:.2f}. Use a outra IA ou aumente o limite no servidor "
            "([eden.limites] no config.toml)."
        )


def month_key(settings: EdenSettings, at_ms: Optional[int] = None) -> str:
    ts = (at_ms if at_ms is not None else int(time.time() * 1000)) / 1000
    return datetime.fromtimestamp(ts, tz=settings.tz).strftime("%Y-%m")


def estimate_tokens(text_chars: int) -> int:
    """Estimativa conservadora: ~3 caracteres por token em português."""
    return max(1, (max(0, text_chars) + 2) // 3)


class SpendingLedger:
    """Anota os gastos e responde quanto já foi gasto no mês."""

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_config_dir

            db_path = get_config_dir() / "eden" / "gastos.db"
        db_path = Path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def spent(self, provider: str, month: str) -> float:
        with self._lock:
            row = self._conn.execute(
                "SELECT COALESCE(SUM(cost_usd), 0) FROM spending "
                "WHERE month = ? AND provider = ?",
                (month, provider),
            ).fetchone()
        return float(row[0])

    def check(
        self,
        provider: str,
        settings: EdenSettings,
        reserve_usd: float = 0.0,
        *,
        at_ms: Optional[int] = None,
    ) -> None:
        """Recusa (BudgetExceeded) se o gasto do mês + a reserva passar do limite."""
        limit = settings.limit_for(provider)
        if limit is None:
            # Só OpenAI e Anthropic têm limite (sempre há um padrão); limite 0
            # desliga a IA daquela empresa.
            return
        spent = self.spent(provider, month_key(settings, at_ms))
        if spent + max(0.0, reserve_usd) > limit:
            raise BudgetExceeded(provider, spent, limit)

    def record(
        self,
        *,
        provider: str,
        model: str,
        kind: str,
        cost_usd: float,
        settings: EdenSettings,
        input_tokens: int = 0,
        output_tokens: int = 0,
        audio_seconds: float = 0.0,
        estimated: bool = False,
        at_ms: Optional[int] = None,
    ) -> None:
        now = at_ms if at_ms is not None else int(time.time() * 1000)
        with self._lock:
            self._conn.execute(
                "INSERT INTO spending (at_ms, month, provider, model, kind, "
                "input_tokens, output_tokens, audio_seconds, cost_usd, estimated) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    now,
                    month_key(settings, now),
                    provider,
                    model,
                    kind,
                    int(input_tokens),
                    int(output_tokens),
                    float(audio_seconds),
                    float(max(0.0, cost_usd)),
                    1 if estimated else 0,
                ),
            )
            self._conn.commit()

    def summary(
        self, settings: EdenSettings, *, at_ms: Optional[int] = None
    ) -> Dict[str, Any]:
        month = month_key(settings, at_ms)
        providers = {}
        for provider in TRACKED_PROVIDERS:
            spent = self.spent(provider, month)
            limit = settings.limit_for(provider)
            providers[provider] = {
                "label": PROVIDER_LABEL.get(provider, provider),
                "spentUsd": round(spent, 4),
                "limitUsd": limit,
                "blocked": limit is not None and spent >= limit,
            }
        return {"month": month, "providers": providers}


_ledger_lock = threading.Lock()
_ledger: Optional[SpendingLedger] = None


def get_ledger() -> SpendingLedger:
    global _ledger
    with _ledger_lock:
        if _ledger is None:
            _ledger = SpendingLedger()
        return _ledger


def set_ledger(ledger: Optional[SpendingLedger]) -> None:
    """Troca o registro de gastos em uso (testes)."""
    global _ledger
    with _ledger_lock:
        _ledger = ledger
