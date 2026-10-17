"""Éden (Parte 5): chave por aparelho.

Antes, todo aparelho usava a mesma chave de acesso (a do ``.env``). Se um
celular fosse perdido, era preciso trocar a chave de todos. Agora:

- cada aparelho ligado pelo código curto (ou pelo botão "chave só deste
  aparelho") recebe uma chave própria, ``oj_ap_…``;
- o servidor guarda só o resumo (sha256) de cada chave, num banco separado,
  fora do backup (``<dados>/eden-seguranca/aparelhos.db``);
- nas Configurações aparece a lista de aparelhos, com o último uso, e dá para
  desligar um aparelho só;
- a chave principal (``.env``) continua valendo (o notebook usa ela) e não
  pode ser desligada pelo app.
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

PREFIXO = "oj_ap_"
MAX_APARELHOS = 30
MAX_NOME = 60
# Grava "último uso" no máximo a cada 10 min; chave nunca usada some em 1 dia.
INTERVALO_ULTIMO_USO_MS = 10 * 60 * 1000
NUNCA_USADO_MS = 24 * 3600 * 1000
QR_SEM_USO_MS = 10 * 60 * 1000  # chave do QR code: vale 10 min para o 1º uso
_FORMATO = re.compile(r"oj_ap_[A-Za-z0-9_-]{40,60}")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS aparelhos (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    nome        TEXT    NOT NULL,
    resumo      TEXT    NOT NULL UNIQUE,
    criado_em   INTEGER NOT NULL,
    ultimo_uso  INTEGER,
    desligado   INTEGER NOT NULL DEFAULT 0,
    -- até quando vale sem ter sido usada (ex.: QR code: 10 minutos)
    expira_sem_uso INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS meta (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
"""


def _agora_ms() -> int:
    return int(time.time() * 1000)


def _resumo(chave: str) -> str:
    return hashlib.sha256(("eden-aparelho:" + chave).encode("utf-8")).hexdigest()


def parece_chave_de_aparelho(valor: Any) -> bool:
    return isinstance(valor, str) and bool(_FORMATO.fullmatch(valor))


def limpar_nome(valor: Any) -> str:
    texto = valor if isinstance(valor, str) else ""
    texto = "".join(c for c in texto if c.isprintable())
    texto = " ".join(texto.split())[:MAX_NOME].strip()
    return texto or "Aparelho"


def nome_pelo_navegador(user_agent: Any) -> str:
    """Nome simples pelo navegador ("iPhone", "Android", "Windows"…)."""
    ua = user_agent if isinstance(user_agent, str) else ""
    for marca, nome in (
        ("iPhone", "iPhone"),
        ("iPad", "iPad"),
        ("Android", "Android"),
        ("Windows", "Windows"),
        ("Macintosh", "Mac"),
        ("Linux", "Linux"),
    ):
        if marca in ua:
            return nome
    return "Aparelho"


class Aparelhos:
    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            from openjarvis.core.paths import get_config_dir

            db_path = get_config_dir() / "eden-seguranca" / "aparelhos.db"
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()
        # Resumos válidos na memória (para não ir ao banco a cada pedido).
        # resumo → (id, expira_sem_uso; 0 = já foi usada)
        self._validos: Dict[str, Tuple[int, int]] = {}
        self._ultimo_gravado: Dict[int, int] = {}
        self._recarregar()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    def _recarregar(self) -> None:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, resumo, ultimo_uso, expira_sem_uso FROM aparelhos "
                "WHERE desligado = 0"
            ).fetchall()
            self._validos = {
                r["resumo"]: (r["id"], 0 if r["ultimo_uso"] else r["expira_sem_uso"])
                for r in rows
            }

    # ── criar, listar, desligar ──────────────────────────────────────────

    def pode_criar(self) -> bool:
        with self._lock:
            ativos = self._conn.execute(
                "SELECT COUNT(*) FROM aparelhos WHERE desligado = 0"
            ).fetchone()[0]
        return ativos < MAX_APARELHOS

    def criar(self, nome: Any, sem_uso_ms: int = NUNCA_USADO_MS) -> Dict[str, Any]:
        """Cria a chave de um aparelho. A chave só aparece aqui, uma vez.
        ``sem_uso_ms``: até quando vale se ninguém usar (QR: 10 min)."""
        chave = PREFIXO + secrets.token_urlsafe(36)
        with self._lock:
            # Chave criada e nunca usada há mais de 1 dia (ex.: QR code que
            # ninguém leu) é desligada.
            self._conn.execute(
                "UPDATE aparelhos SET desligado = 1 WHERE desligado = 0 "
                "AND ultimo_uso IS NULL AND expira_sem_uso < ?",
                (_agora_ms(),),
            )
            ativos = self._conn.execute(
                "SELECT COUNT(*) FROM aparelhos WHERE desligado = 0"
            ).fetchone()[0]
            if ativos >= MAX_APARELHOS:
                raise ValueError(
                    f"no máximo {MAX_APARELHOS} aparelhos; desligue algum antes"
                )
            agora = _agora_ms()
            cur = self._conn.execute(
                "INSERT INTO aparelhos (nome, resumo, criado_em, expira_sem_uso) "
                "VALUES (?, ?, ?, ?)",
                (limpar_nome(nome), _resumo(chave), agora, agora + max(0, sem_uso_ms)),
            )
            self._conn.commit()
            aparelho_id = int(cur.lastrowid)
            self._recarregar()
        logger.info("Éden: aparelho %d ligado", aparelho_id)
        return {"id": aparelho_id, "chave": chave}

    def listar(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT id, nome, criado_em, ultimo_uso FROM aparelhos "
                "WHERE desligado = 0 ORDER BY id"
            ).fetchall()
        return [dict(r) for r in rows]

    def desligar_todos(self) -> int:
        with self._lock:
            mudou = self._conn.execute(
                "UPDATE aparelhos SET desligado = 1 WHERE desligado = 0"
            ).rowcount
            self._conn.commit()
            self._recarregar()
        if mudou:
            logger.info("Éden: %d aparelho(s) desligado(s)", mudou)
        return mudou

    def conferir_troca_da_chave_principal(self, chave_principal: str) -> bool:
        """Se a chave principal (.env) mudou, desliga todos os aparelhos:
        chaves criadas com a chave antiga (talvez vazada) param de valer."""
        if not chave_principal:
            return False
        marca = hashlib.sha256(
            ("eden-principal:" + chave_principal).encode()
        ).hexdigest()
        with self._lock:
            row = self._conn.execute(
                "SELECT valor FROM meta WHERE chave = 'principal'"
            ).fetchone()
            self._conn.execute(
                "INSERT INTO meta (chave, valor) VALUES ('principal', ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (marca,),
            )
            self._conn.commit()
        if row is not None and row["valor"] != marca:
            self.desligar_todos()
            return True
        return False

    def desligar(self, aparelho_id: Any) -> bool:
        if isinstance(aparelho_id, bool) or not isinstance(aparelho_id, int):
            return False
        with self._lock:
            mudou = self._conn.execute(
                "UPDATE aparelhos SET desligado = 1 WHERE id = ? AND desligado = 0",
                (aparelho_id,),
            ).rowcount
            self._conn.commit()
            self._recarregar()
        if mudou:
            logger.info("Éden: aparelho %d desligado", aparelho_id)
        return bool(mudou)

    def renomear(self, aparelho_id: Any, nome: Any) -> bool:
        if isinstance(aparelho_id, bool) or not isinstance(aparelho_id, int):
            return False
        with self._lock:
            mudou = self._conn.execute(
                "UPDATE aparelhos SET nome = ? WHERE id = ? AND desligado = 0",
                (limpar_nome(nome), aparelho_id),
            ).rowcount
            self._conn.commit()
        return bool(mudou)

    # ── conferir ─────────────────────────────────────────────────────────

    def conferir(self, chave: Any) -> Optional[int]:
        """Id do aparelho se a chave vale; None se não vale."""
        if not parece_chave_de_aparelho(chave):
            return None
        resumo = _resumo(chave)
        agora = _agora_ms()
        with self._lock:
            achado = self._validos.get(resumo)
            if achado is None:
                return None
            aparelho_id, expira_sem_uso = achado
            if expira_sem_uso and agora > expira_sem_uso:
                return None  # nunca usada e venceu (ex.: QR esquecido)
            if expira_sem_uso:
                self._validos[resumo] = (aparelho_id, 0)  # agora já foi usada
            gravar = bool(expira_sem_uso) or (
                agora - self._ultimo_gravado.get(aparelho_id, 0)
                > INTERVALO_ULTIMO_USO_MS
            )
            if gravar:
                self._ultimo_gravado[aparelho_id] = agora
        if gravar:
            # Fora do caminho do pedido: gravar no banco não segura a resposta.
            threading.Thread(
                target=self._gravar_uso, args=(aparelho_id, agora), daemon=True
            ).start()
        return aparelho_id

    def _gravar_uso(self, aparelho_id: int, agora: int) -> None:
        try:
            with self._lock:
                self._conn.execute(
                    "UPDATE aparelhos SET ultimo_uso = ? WHERE id = ?",
                    (agora, aparelho_id),
                )
                self._conn.commit()
        except sqlite3.Error:
            logger.warning("Éden: não consegui anotar o último uso")


_registro: Optional[Aparelhos] = None
_registro_lock = threading.Lock()


def registro() -> Aparelhos:
    global _registro
    with _registro_lock:
        if _registro is None:
            _registro = Aparelhos()
        return _registro


def definir_registro(valor: Optional[Aparelhos]) -> None:
    """Para testes."""
    global _registro
    with _registro_lock:
        _registro = valor


def conferir(chave: Any) -> Optional[int]:
    """Usado pelo AuthMiddleware: nunca derruba o pedido por erro interno."""
    if not parece_chave_de_aparelho(chave):
        return None
    try:
        return registro().conferir(chave)
    except Exception:  # noqa: BLE001
        logger.exception("Éden: falha ao conferir a chave do aparelho")
        return None
