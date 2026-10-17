"""Éden: conversas guardadas no servidor (sincronização celular ↔ notebook).

O app guarda uma cópia das conversas no aparelho e envia cada conversa
inteira para cá. O servidor é a fonte de verdade:

- Os IDs vêm do aparelho. Gravar a mesma conversa ou mensagem duas vezes
  (por exemplo, depois de a conexão cair e voltar) não cria duplicatas.
- Em conflito, vale a versão mais recente (``updatedAt``, em milissegundos).
- Apagar deixa só uma marca ("tombstone") com o ID e a data, para os outros
  aparelhos também apagarem. O conteúdo das mensagens é removido de verdade.
- Cada conversa pertence a um usuário (``user_id``). No piloto há um só
  usuário; o campo existe para permitir mais usuários no futuro.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir

DEFAULT_USER_ID = "default"

MAX_MESSAGES_PER_CONVERSATION = 5000
MAX_MESSAGE_CHARS = 200_000
MAX_TITLE_CHARS = 200
MAX_MODEL_CHARS = 200
MAX_EXTRA_JSON_CHARS = 200_000

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_ALLOWED_ROLES = {"user", "assistant"}
# Campos extras de cada mensagem que o app pode guardar.
_EXTRA_FIELDS = (
    "toolCalls",
    "researchTraces",
    "researchSources",
    "isResearch",
    "usage",
    "telemetry",
    # Éden (Parte 2): ações sugeridas nesta resposta (cartões de confirmação).
    "edenActions",
    # Éden (Parte 4): resposta da pesquisa na internet (conteúdo de fora).
    "edenPesquisa",
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    user_id    TEXT    NOT NULL,
    id         TEXT    NOT NULL,
    title      TEXT    NOT NULL DEFAULT '',
    model      TEXT    NOT NULL DEFAULT '',
    created_at INTEGER NOT NULL,
    updated_at INTEGER NOT NULL,
    deleted    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, id)
);
CREATE INDEX IF NOT EXISTS idx_eden_conv_updated
    ON conversations (user_id, updated_at);
CREATE TABLE IF NOT EXISTS messages (
    user_id         TEXT    NOT NULL,
    conversation_id TEXT    NOT NULL,
    id              TEXT    NOT NULL,
    role            TEXT    NOT NULL,
    content         TEXT    NOT NULL,
    timestamp       INTEGER NOT NULL,
    extra           TEXT    NOT NULL DEFAULT '{}',
    version         INTEGER NOT NULL,
    PRIMARY KEY (user_id, conversation_id, id)
);
"""


class ConversationValidationError(ValueError):
    """Dados de conversa inválidos vindos do aparelho."""


def is_valid_id(value: Any) -> bool:
    return isinstance(value, str) and bool(_ID_RE.fullmatch(value))


def _as_ms(value: Any, field: str) -> int:
    # bool é subclasse de int em Python; não aceitar True/False como data.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConversationValidationError(f"'{field}' precisa ser um número")
    number = int(value)
    if number < 0:
        raise ConversationValidationError(f"'{field}' não pode ser negativo")
    return number


def _as_text(value: Any, field: str, max_chars: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ConversationValidationError(f"'{field}' precisa ser texto")
    if len(value) > max_chars:
        raise ConversationValidationError(f"'{field}' passou do limite de tamanho")
    return value


def _validate_message(raw: Any) -> Dict[str, Any]:
    if not isinstance(raw, dict):
        raise ConversationValidationError("cada mensagem precisa ser um objeto")
    msg_id = raw.get("id")
    if not is_valid_id(msg_id):
        raise ConversationValidationError("mensagem com ID inválido")
    role = raw.get("role")
    if role not in _ALLOWED_ROLES:
        raise ConversationValidationError("mensagem com papel inválido")
    content = _as_text(raw.get("content", ""), "content", MAX_MESSAGE_CHARS)
    timestamp = _as_ms(raw.get("timestamp"), "timestamp")
    extra = {key: raw[key] for key in _EXTRA_FIELDS if key in raw}
    extra_json = json.dumps(extra, ensure_ascii=False)
    if len(extra_json) > MAX_EXTRA_JSON_CHARS:
        raise ConversationValidationError("dados extras da mensagem grandes demais")
    return {
        "id": msg_id,
        "role": role,
        "content": content,
        "timestamp": timestamp,
        "extra": extra_json,
    }


def validate_conversation(conv_id: str, raw: Any) -> Dict[str, Any]:
    """Confere a conversa enviada pelo aparelho e devolve os campos limpos."""
    if not is_valid_id(conv_id):
        raise ConversationValidationError("ID de conversa inválido")
    if not isinstance(raw, dict):
        raise ConversationValidationError("a conversa precisa ser um objeto")
    if raw.get("id", conv_id) != conv_id:
        raise ConversationValidationError("o ID do corpo não bate com o endereço")
    messages_raw = raw.get("messages", [])
    if not isinstance(messages_raw, list):
        raise ConversationValidationError("'messages' precisa ser uma lista")
    if len(messages_raw) > MAX_MESSAGES_PER_CONVERSATION:
        raise ConversationValidationError("conversa com mensagens demais")
    messages = [_validate_message(m) for m in messages_raw]
    created_at = _as_ms(raw.get("createdAt"), "createdAt")
    updated_at = _as_ms(raw.get("updatedAt"), "updatedAt")
    return {
        "id": conv_id,
        "title": _as_text(raw.get("title", ""), "title", MAX_TITLE_CHARS),
        "model": _as_text(raw.get("model", ""), "model", MAX_MODEL_CHARS),
        "created_at": created_at,
        "updated_at": max(updated_at, created_at),
        "messages": messages,
    }


class ConversationStore:
    """Banco SQLite com as conversas do Éden."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            db_path = get_config_dir() / "eden" / "conversations.db"
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(self._path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ── leitura ─────────────────────────────────────────────────────────

    @staticmethod
    def _meta(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "title": row["title"],
            "model": row["model"],
            "createdAt": row["created_at"],
            "updatedAt": row["updated_at"],
            "deleted": bool(row["deleted"]),
        }

    def _get_row(self, user_id: str, conv_id: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT * FROM conversations WHERE user_id = ? AND id = ?",
            (user_id, conv_id),
        ).fetchone()

    def list_conversations(
        self, user_id: str = DEFAULT_USER_ID
    ) -> List[Dict[str, Any]]:
        """Todas as conversas do usuário, sem as mensagens (apagadas incluídas)."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM conversations WHERE user_id = ? "
                "ORDER BY updated_at DESC",
                (user_id,),
            ).fetchall()
        return [self._meta(row) for row in rows]

    def get_conversation(
        self, conv_id: str, user_id: str = DEFAULT_USER_ID
    ) -> Optional[Dict[str, Any]]:
        """Uma conversa com as mensagens, ou None se não existir."""
        with self._lock:
            row = self._get_row(user_id, conv_id)
            if row is None:
                return None
            msg_rows = self._conn.execute(
                "SELECT id, role, content, timestamp, extra FROM messages "
                "WHERE user_id = ? AND conversation_id = ? "
                "ORDER BY timestamp ASC, rowid ASC",
                (user_id, conv_id),
            ).fetchall()
        conversation = self._meta(row)
        messages = []
        for m in msg_rows:
            message: Dict[str, Any] = {
                "id": m["id"],
                "role": m["role"],
                "content": m["content"],
                "timestamp": m["timestamp"],
            }
            try:
                extra = json.loads(m["extra"] or "{}")
            except json.JSONDecodeError:
                extra = {}
            if isinstance(extra, dict):
                message.update({k: v for k, v in extra.items() if k in _EXTRA_FIELDS})
            messages.append(message)
        conversation["messages"] = [] if conversation["deleted"] else messages
        return conversation

    # ── escrita ─────────────────────────────────────────────────────────

    def upsert_conversation(
        self, conv: Dict[str, Any], user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, Any]:
        """Grava uma conversa já validada (veja ``validate_conversation``).

        Devolve os dados da conversa como ficaram no servidor.
        """
        with self._lock:
            existing = self._get_row(user_id, conv["id"])
            incoming_version = conv["updated_at"]

            if existing is not None and existing["deleted"]:
                if existing["updated_at"] >= incoming_version:
                    # Apagada depois desta versão: a exclusão vale.
                    return self._meta(existing)

            if existing is None:
                self._conn.execute(
                    "INSERT INTO conversations "
                    "(user_id, id, title, model, created_at, updated_at, deleted) "
                    "VALUES (?, ?, ?, ?, ?, ?, 0)",
                    (
                        user_id,
                        conv["id"],
                        conv["title"],
                        conv["model"],
                        conv["created_at"],
                        incoming_version,
                    ),
                )
            elif incoming_version >= existing["updated_at"]:
                self._conn.execute(
                    "UPDATE conversations SET title = ?, model = ?, "
                    "created_at = MIN(created_at, ?), updated_at = ?, deleted = 0 "
                    "WHERE user_id = ? AND id = ?",
                    (
                        conv["title"],
                        conv["model"],
                        conv["created_at"],
                        incoming_version,
                        user_id,
                        conv["id"],
                    ),
                )

            known_ids = {
                r["id"]
                for r in self._conn.execute(
                    "SELECT id FROM messages WHERE user_id = ? AND conversation_id = ?",
                    (user_id, conv["id"]),
                ).fetchall()
            }
            has_new_messages = any(m["id"] not in known_ids for m in conv["messages"])

            # Mensagens: cria as novas; atualiza as existentes só se esta
            # versão for igual ou mais nova que a gravada.
            self._conn.executemany(
                "INSERT INTO messages "
                "(user_id, conversation_id, id, role, content, timestamp, extra, "
                "version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (user_id, conversation_id, id) DO UPDATE SET "
                "role = excluded.role, content = excluded.content, "
                "timestamp = excluded.timestamp, extra = excluded.extra, "
                "version = excluded.version "
                "WHERE excluded.version >= messages.version",
                [
                    (
                        user_id,
                        conv["id"],
                        m["id"],
                        m["role"],
                        m["content"],
                        m["timestamp"],
                        m["extra"],
                        incoming_version,
                    )
                    for m in conv["messages"]
                ],
            )
            if (
                existing is not None
                and incoming_version < existing["updated_at"]
                and has_new_messages
            ):
                # Um aparelho que estava sem internet mandou mensagens novas
                # numa versão antiga. Avança a versão do servidor para que
                # todos os aparelhos (inclusive este) busquem a conversa de novo.
                self._conn.execute(
                    "UPDATE conversations SET updated_at = updated_at + 1, deleted = 0 "
                    "WHERE user_id = ? AND id = ?",
                    (user_id, conv["id"]),
                )
            incoming_ids = {m["id"] for m in conv["messages"]}
            server_has_more = bool((known_ids | incoming_ids) - incoming_ids)
            self._conn.commit()
            row = self._get_row(user_id, conv["id"])
        meta = self._meta(row)
        # O servidor tem mensagens que o aparelho não mandou (vindas de outro
        # aparelho): o app deve buscar a conversa para juntar.
        meta["serverHasMore"] = server_has_more and not meta["deleted"]
        return meta

    def delete_conversation(
        self, conv_id: str, deleted_at: int, user_id: str = DEFAULT_USER_ID
    ) -> Dict[str, Any]:
        """Apaga a conversa e as mensagens, deixando só a marca de exclusão.

        Se a conversa foi alterada depois do momento da exclusão (por outro
        aparelho), a exclusão é ignorada e a conversa atual é devolvida.
        """
        if not is_valid_id(conv_id):
            raise ConversationValidationError("ID de conversa inválido")
        deleted_at = _as_ms(deleted_at, "deletedAt")
        with self._lock:
            existing = self._get_row(user_id, conv_id)
            if existing is not None and existing["updated_at"] > deleted_at:
                return self._meta(existing)
            if existing is None:
                self._conn.execute(
                    "INSERT INTO conversations "
                    "(user_id, id, title, model, created_at, updated_at, deleted) "
                    "VALUES (?, ?, '', '', ?, ?, 1)",
                    (user_id, conv_id, deleted_at, deleted_at),
                )
            else:
                self._conn.execute(
                    "UPDATE conversations SET title = '', model = '', "
                    "updated_at = ?, deleted = 1 WHERE user_id = ? AND id = ?",
                    (deleted_at, user_id, conv_id),
                )
            self._conn.execute(
                "DELETE FROM messages WHERE user_id = ? AND conversation_id = ?",
                (user_id, conv_id),
            )
            self._conn.commit()
            row = self._get_row(user_id, conv_id)
        return self._meta(row)
