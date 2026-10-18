"""Éden: organização pessoal (Parte 2) — espaços, perfil, memórias, tarefas,
notas e as ações que o Éden propõe.

Tudo fica num banco SQLite em <dados>/eden/organizacao.db (entra no backup).

- **Espaços** separam a vida: Pessoal, LS Visuals, Clientes (dá para criar
  outros). Memórias, tarefas e notas pertencem a um espaço; uma memória pode
  valer para todos (espaço vazio).
- **Origem**: "voce" quando a pessoa fez pela tela; "eden" quando a pessoa
  confirmou uma proposta do Éden.
- **Registro**: cada mudança fica anotada (quem, o quê, quando), para dar para
  conferir depois.
- Apagar é "macio": o item some das listas, mas continua no banco (e no
  backup) com a data em que foi apagado.

As regras de cada campo (tamanhos, datas, horários) ficam aqui, para valerem
igual na tela e nas propostas do Éden.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from openjarvis.core.paths import get_config_dir

# ── limites ──────────────────────────────────────────────────────────────

MAX_ESPACOS = 20
MAX_NOME_ESPACO = 40
MAX_DESCRICAO_ESPACO = 1000
MAX_PERFIL = 4000
MAX_MEMORIA = 500
MAX_MEMORIAS = 300
MAX_TITULO = 200
MAX_NOTAS_TAREFA = 4000
MAX_TAREFAS_ABERTAS = 1000
MAX_TEXTO_NOTA = 20000
MAX_NOTAS = 3000

ORIGENS = ("voce", "eden")
TIPOS_NOTA = ("nota", "ideia")
ESPACOS_INICIAIS: Tuple[Tuple[str, str, str], ...] = (
    ("pessoal", "Pessoal", "Vida pessoal, casa, saúde, estudos."),
    ("ls-visuals", "LS Visuals", "A empresa: produção, marketing, finanças."),
    ("clientes", "Clientes", "Trabalhos e combinados com clientes."),
)

_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# Marcas de direção do texto (bidi) e afins.
# Horário, data e números só com algarismos 0-9 (em Python, \d também aceita
# dígitos de outras escritas, que parecem outros números na tela).
_HORA = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$", re.ASCII)
_DATA = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$", re.ASCII)
_INTEIRO = re.compile(r"^[0-9]{1,12}$", re.ASCII)
_ESPACOS = re.compile(r"\s+")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS espacos (
    id            TEXT    PRIMARY KEY,
    nome          TEXT    NOT NULL,
    descricao     TEXT    NOT NULL DEFAULT '',
    ordem         INTEGER NOT NULL DEFAULT 0,
    arquivado     INTEGER NOT NULL DEFAULT 0,
    criado_em     INTEGER NOT NULL,
    atualizado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS perfil (
    chave         TEXT    PRIMARY KEY,
    valor         TEXT    NOT NULL,
    atualizado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS memorias (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    espaco        TEXT,
    texto         TEXT    NOT NULL,
    origem        TEXT    NOT NULL,
    criado_em     INTEGER NOT NULL,
    atualizado_em INTEGER NOT NULL,
    apagado_em    INTEGER
);
CREATE TABLE IF NOT EXISTS tarefas (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    espaco              TEXT    NOT NULL,
    titulo              TEXT    NOT NULL,
    notas               TEXT    NOT NULL DEFAULT '',
    data                TEXT,
    hora                TEXT,
    lembrete_em         INTEGER,
    lembrete_enviado_em INTEGER,
    feita_em            INTEGER,
    origem              TEXT    NOT NULL,
    criado_em           INTEGER NOT NULL,
    atualizado_em       INTEGER NOT NULL,
    apagado_em          INTEGER
);
CREATE INDEX IF NOT EXISTS idx_tarefas_espaco ON tarefas (espaco, feita_em, data);
CREATE INDEX IF NOT EXISTS idx_tarefas_lembrete ON tarefas (lembrete_em);
CREATE TABLE IF NOT EXISTS notas (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    espaco        TEXT    NOT NULL,
    tipo          TEXT    NOT NULL,
    titulo        TEXT    NOT NULL DEFAULT '',
    texto         TEXT    NOT NULL,
    fixada        INTEGER NOT NULL DEFAULT 0,
    origem        TEXT    NOT NULL,
    criado_em     INTEGER NOT NULL,
    atualizado_em INTEGER NOT NULL,
    apagado_em    INTEGER
);
CREATE INDEX IF NOT EXISTS idx_notas_espaco ON notas (espaco, atualizado_em);
CREATE TABLE IF NOT EXISTS acoes (
    id          TEXT    PRIMARY KEY,
    tipo        TEXT    NOT NULL,
    parametros  TEXT    NOT NULL,
    assinatura  TEXT    NOT NULL,
    resumo      TEXT    NOT NULL,
    conversa_id TEXT,
    estado      TEXT    NOT NULL,
    criado_em   INTEGER NOT NULL,
    expira_em   INTEGER NOT NULL,
    decidido_em INTEGER,
    resultado   TEXT
);
CREATE INDEX IF NOT EXISTS idx_acoes_criado ON acoes (criado_em);
CREATE TABLE IF NOT EXISTS registro (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    quando  INTEGER NOT NULL,
    quem    TEXT    NOT NULL,
    o_que   TEXT    NOT NULL,
    alvo    TEXT    NOT NULL,
    acao_id TEXT
);
CREATE TABLE IF NOT EXISTS ajustes (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS documentos (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    espaco    TEXT    NOT NULL,
    nome      TEXT    NOT NULL,
    tipo      TEXT    NOT NULL,
    bytes     INTEGER NOT NULL,
    paginas   INTEGER,
    texto     TEXT    NOT NULL,
    cortado   INTEGER NOT NULL DEFAULT 0,
    sha256    TEXT    NOT NULL,
    criado_em INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documentos_espaco ON documentos (espaco, criado_em);
CREATE TABLE IF NOT EXISTS conversa_documentos (
    conversa_id  TEXT    NOT NULL,
    documento_id INTEGER NOT NULL,
    criado_em    INTEGER NOT NULL,
    PRIMARY KEY (conversa_id, documento_id)
);
CREATE TABLE IF NOT EXISTS lugares (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    nome      TEXT    NOT NULL,
    tipo      TEXT    NOT NULL,
    latitude  REAL    NOT NULL,
    longitude REAL    NOT NULL,
    principal INTEGER NOT NULL DEFAULT 0,
    criado_em INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS trajetos (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    nome         TEXT    NOT NULL,
    origem_nome  TEXT    NOT NULL,
    origem_lat   REAL    NOT NULL,
    origem_lon   REAL    NOT NULL,
    destino_nome TEXT    NOT NULL,
    destino_lat  REAL    NOT NULL,
    destino_lon  REAL    NOT NULL,
    criado_em    INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS push_inscricoes (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    endpoint   TEXT    NOT NULL UNIQUE,
    p256dh     TEXT    NOT NULL,
    auth       TEXT    NOT NULL,
    nome       TEXT    NOT NULL DEFAULT '',
    criado_em  INTEGER NOT NULL,
    usado_em   INTEGER,
    falhas     INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS contas (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    espaco           TEXT    NOT NULL,
    tipo             TEXT    NOT NULL CHECK (tipo IN ('pagar', 'receber')),
    descricao        TEXT    NOT NULL,
    valor_centavos   INTEGER NOT NULL CHECK (valor_centavos >= 0),
    vencimento       TEXT    NOT NULL,
    dia              INTEGER NOT NULL,
    repete           TEXT    NOT NULL DEFAULT 'nao'
                     CHECK (repete IN ('nao', 'mensal', 'anual')),
    categoria        TEXT    NOT NULL DEFAULT '',
    aviso_dias       INTEGER NOT NULL DEFAULT 2,
    aviso_enviado_em INTEGER,
    pago_em          INTEGER,
    notas            TEXT    NOT NULL DEFAULT '',
    origem           TEXT    NOT NULL,
    criado_em        INTEGER NOT NULL,
    atualizado_em    INTEGER NOT NULL,
    apagado_em       INTEGER
);
CREATE INDEX IF NOT EXISTS contas_abertas ON contas (vencimento)
    WHERE pago_em IS NULL AND apagado_em IS NULL;
"""


class ErroOrganizacao(ValueError):
    """Dado inválido ou pedido impossível, com mensagem para a pessoa."""

    def __init__(self, mensagem: str, status: int = 400) -> None:
        super().__init__(mensagem)
        self.status = status


def agora_ms() -> int:
    return int(time.time() * 1000)


# ── regras dos campos ────────────────────────────────────────────────────


def _visivel(c: str) -> bool:
    """O caractere aparece na tela? Fora: controle, formatação invisível
    (direção do texto, largura zero, "tags" Unicode), uso privado, sem
    atribuição e os seletores de variação (menos o do emoji, U+FE0F).
    Assim o cartão de confirmação mostra exatamente o que será gravado."""
    if unicodedata.category(c) in ("Cc", "Cf", "Co", "Cn", "Cs"):
        return False
    codigo = ord(c)
    return not (0xFE00 <= codigo <= 0xFE0E or 0xE0100 <= codigo <= 0xE01EF)


def texto(
    valor: Any,
    campo: str,
    maximo: int,
    obrigatorio: bool = True,
    uma_linha: bool = False,
) -> str:
    """Confere e limpa um texto. ``uma_linha``: quebras de linha e espaços
    seguidos viram um espaço só (títulos, memórias, nomes)."""
    if valor is None:
        valor = ""
    if not isinstance(valor, str):
        raise ErroOrganizacao(f"'{campo}' precisa ser texto")
    limpo = (
        valor.replace("\r\n", "\n")
        .replace("\r", "\n")
        .replace("\u2028", "\n")
        .replace("\u2029", "\n")
    )
    limpo = "".join(c for c in limpo if c in "\n\t" or _visivel(c)).strip()
    if uma_linha:
        limpo = _ESPACOS.sub(" ", limpo)
    if obrigatorio and not limpo:
        raise ErroOrganizacao(f"'{campo}' não pode ficar vazio")
    if len(limpo) > maximo:
        raise ErroOrganizacao(f"'{campo}' passou de {maximo} caracteres")
    return limpo


def data_iso(valor: Any, campo: str = "data") -> Optional[str]:
    """'AAAA-MM-DD' (ou None)."""
    if valor in (None, ""):
        return None
    if not isinstance(valor, str) or not _DATA.match(valor.strip()):
        raise ErroOrganizacao(f"'{campo}' precisa ser uma data AAAA-MM-DD")
    try:
        d = date.fromisoformat(valor.strip())
    except ValueError as exc:
        raise ErroOrganizacao(f"'{campo}' precisa ser uma data AAAA-MM-DD") from exc
    if not (2000 <= d.year <= 2100):
        raise ErroOrganizacao(f"'{campo}' fora do intervalo aceito")
    return d.isoformat()


def hora_hhmm(valor: Any, campo: str = "hora") -> Optional[str]:
    if valor in (None, ""):
        return None
    if not isinstance(valor, str) or not _HORA.match(valor.strip()):
        raise ErroOrganizacao(f"'{campo}' precisa ser um horário HH:MM")
    return valor.strip()


def momento_local(data: str, hora: str, tz: timezone) -> int:
    """Data + hora no fuso do Éden → milissegundos."""
    d = date.fromisoformat(data)
    h, m = (int(x) for x in hora.split(":"))
    return int(datetime(d.year, d.month, d.day, h, m, tzinfo=tz).timestamp() * 1000)


def local_de_ms(ms: int, tz: timezone) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=tz)


def slug(nome: str) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode()
    base = re.sub(r"[^a-z0-9]+", "-", base.lower()).strip("-")
    return base[:40].strip("-") or "espaco"


def inteiro(valor: Any, campo: str = "id") -> int:
    if isinstance(valor, str) and _INTEIRO.match(valor.strip()):
        valor = int(valor.strip())
    if isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
        raise ErroOrganizacao(f"'{campo}' precisa ser um número")
    return valor


# ── banco ────────────────────────────────────────────────────────────────


# Cartão em "executando" há mais que isto ficou preso (a chamada ao Google
# tem 15 s de limite).
PRESO_EXECUTANDO_MS = 10 * 60 * 1000


class Organizacao:
    """Banco da organização pessoal do Éden."""

    def __init__(self, db_path: Optional[str | Path] = None) -> None:
        if db_path is None:
            db_path = get_config_dir() / "eden" / "organizacao.db"
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        # isolation_level=None: as transações são abertas e fechadas só pelo
        # método transacao() (BEGIN IMMEDIATE ... COMMIT).
        self._conn = sqlite3.connect(
            str(self._path), check_same_thread=False, isolation_level=None
        )
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.executescript(_SCHEMA)
            if not self._conn.execute("SELECT 1 FROM espacos LIMIT 1").fetchone():
                agora = agora_ms()
                self._conn.executemany(
                    "INSERT INTO espacos (id, nome, descricao, ordem, criado_em, "
                    "atualizado_em) VALUES (?, ?, ?, ?, ?, ?)",
                    [
                        (eid, nome, desc, i, agora, agora)
                        for i, (eid, nome, desc) in enumerate(ESPACOS_INICIAIS)
                    ],
                )

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # Transação: tudo ou nada, com o banco travado para este processo.
    def transacao(self, funcao: Callable[[sqlite3.Connection], Any]) -> Any:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                resultado = funcao(self._conn)
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")
            return resultado

    def _executar(
        self,
        conn: Optional[sqlite3.Connection],
        funcao: Callable[[sqlite3.Connection], Any],
    ) -> Any:
        """Dentro de uma transação já aberta (``conn``) ou numa nova."""
        if conn is not None:
            return funcao(conn)
        return self.transacao(funcao)

    def _ler(self, sql: str, params: Tuple = ()) -> List[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    @staticmethod
    def _registrar(
        conn: sqlite3.Connection,
        quem: str,
        o_que: str,
        alvo: str,
        acao_id: Optional[str] = None,
    ) -> None:
        conn.execute(
            "INSERT INTO registro (quando, quem, o_que, alvo, acao_id) "
            "VALUES (?, ?, ?, ?, ?)",
            (agora_ms(), quem, o_que, alvo, acao_id),
        )

    # ── espaços ──────────────────────────────────────────────────────────

    @staticmethod
    def _espaco(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "nome": row["nome"],
            "descricao": row["descricao"],
            "ordem": row["ordem"],
            "arquivado": bool(row["arquivado"]),
        }

    def listar_espacos(self, incluir_arquivados: bool = False) -> List[Dict[str, Any]]:
        sql = "SELECT * FROM espacos"
        if not incluir_arquivados:
            sql += " WHERE arquivado = 0"
        sql += " ORDER BY ordem, nome"
        return [self._espaco(r) for r in self._ler(sql)]

    def espaco(self, espaco_id: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(espaco_id, str):
            return None
        rows = self._ler("SELECT * FROM espacos WHERE id = ?", (espaco_id,))
        return self._espaco(rows[0]) if rows else None

    def espaco_valido(self, espaco_id: Any, campo: str = "espaco") -> str:
        """Confere que o espaço existe e não está arquivado."""
        e = self.espaco(espaco_id)
        if e is None or e["arquivado"]:
            raise ErroOrganizacao(f"'{campo}': espaço desconhecido")
        return e["id"]

    def criar_espaco(
        self, nome: Any, descricao: Any = "", quem: str = "voce"
    ) -> Dict[str, Any]:
        nome = texto(nome, "nome", MAX_NOME_ESPACO, uma_linha=True)
        descricao = texto(
            descricao,
            "descricao",
            MAX_DESCRICAO_ESPACO,
            obrigatorio=False,
            uma_linha=True,
        )

        def fazer(conn: sqlite3.Connection) -> str:
            total = conn.execute("SELECT COUNT(*) FROM espacos").fetchone()[0]
            if total >= MAX_ESPACOS:
                raise ErroOrganizacao(f"limite de {MAX_ESPACOS} espaços")
            base = slug(nome)
            novo = base
            n = 2
            while conn.execute(
                "SELECT 1 FROM espacos WHERE id = ?", (novo,)
            ).fetchone():
                novo = f"{base}-{n}"
                n += 1
            agora = agora_ms()
            conn.execute(
                "INSERT INTO espacos (id, nome, descricao, ordem, criado_em, "
                "atualizado_em) VALUES (?, ?, ?, ?, ?, ?)",
                (novo, nome, descricao, total, agora, agora),
            )
            self._registrar(conn, quem, "espaco.criar", f"espaco:{novo}")
            return novo

        return self.espaco(self.transacao(fazer))  # type: ignore[return-value]

    def atualizar_espaco(
        self, espaco_id: Any, campos: Dict[str, Any], quem: str = "voce"
    ) -> Dict[str, Any]:
        atual = self.espaco(espaco_id)
        if atual is None:
            raise ErroOrganizacao("espaço não encontrado", 404)
        novos: Dict[str, Any] = {}
        if "nome" in campos:
            novos["nome"] = texto(
                campos["nome"], "nome", MAX_NOME_ESPACO, uma_linha=True
            )
        if "descricao" in campos:
            novos["descricao"] = texto(
                campos["descricao"],
                "descricao",
                MAX_DESCRICAO_ESPACO,
                obrigatorio=False,
                uma_linha=True,
            )
        if "arquivado" in campos:
            if not isinstance(campos["arquivado"], bool):
                raise ErroOrganizacao("'arquivado' precisa ser verdadeiro ou falso")
            novos["arquivado"] = int(campos["arquivado"])
        if not novos:
            return atual

        def fazer(conn: sqlite3.Connection) -> None:
            if novos.get("arquivado"):
                ativos = conn.execute(
                    "SELECT COUNT(*) FROM espacos WHERE arquivado = 0 AND id != ?",
                    (atual["id"],),
                ).fetchone()[0]
                if ativos == 0:
                    raise ErroOrganizacao("precisa sobrar pelo menos um espaço")
            sets = ", ".join(f"{k} = ?" for k in novos)
            conn.execute(
                f"UPDATE espacos SET {sets}, atualizado_em = ? WHERE id = ?",  # noqa: S608
                (*novos.values(), agora_ms(), atual["id"]),
            )
            self._registrar(conn, quem, "espaco.editar", f"espaco:{atual['id']}")

        self.transacao(fazer)
        return self.espaco(atual["id"])  # type: ignore[return-value]

    # ── perfil ───────────────────────────────────────────────────────────

    def perfil(self) -> Dict[str, Any]:
        rows = self._ler(
            "SELECT valor, atualizado_em FROM perfil WHERE chave = 'sobre'"
        )
        if not rows:
            return {"texto": "", "atualizado_em": None}
        return {"texto": rows[0]["valor"], "atualizado_em": rows[0]["atualizado_em"]}

    def salvar_perfil(self, valor: Any, quem: str = "voce") -> Dict[str, Any]:
        novo = texto(valor, "texto", MAX_PERFIL, obrigatorio=False)

        def fazer(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT INTO perfil (chave, valor, atualizado_em) "
                "VALUES ('sobre', ?, ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor, "
                "atualizado_em = excluded.atualizado_em",
                (novo, agora_ms()),
            )
            self._registrar(conn, quem, "perfil.editar", "perfil")

        self.transacao(fazer)
        return self.perfil()

    # ── memórias ─────────────────────────────────────────────────────────

    @staticmethod
    def _memoria(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "espaco": row["espaco"],
            "texto": row["texto"],
            "origem": row["origem"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }

    def memoria(self, memoria_id: Any) -> Optional[Dict[str, Any]]:
        rows = self._ler(
            "SELECT * FROM memorias WHERE id = ? AND apagado_em IS NULL",
            (inteiro(memoria_id),),
        )
        return self._memoria(rows[0]) if rows else None

    def listar_memorias(
        self, espaco: Optional[str] = None, todas: bool = False
    ) -> List[Dict[str, Any]]:
        """Memórias do espaço + as que valem para todos.

        ``todas``: de todos os espaços.
        """
        if todas:
            rows = self._ler(
                "SELECT * FROM memorias WHERE apagado_em IS NULL "
                "ORDER BY criado_em DESC"
            )
        else:
            rows = self._ler(
                "SELECT * FROM memorias WHERE apagado_em IS NULL "
                "AND (espaco IS NULL OR espaco = ?) ORDER BY criado_em DESC",
                (espaco,),
            )
        return [self._memoria(r) for r in rows]

    def _espaco_memoria(self, valor: Any) -> Optional[str]:
        # Vazio / None / "todos" = vale para todos os espaços.
        if valor in (None, "", "todos"):
            return None
        return self.espaco_valido(valor)

    def criar_memoria(
        self,
        valor: Any,
        espaco: Any = None,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        novo = texto(valor, "texto", MAX_MEMORIA, uma_linha=True)
        esp = self._espaco_memoria(espaco)

        def fazer(c: sqlite3.Connection) -> int:
            total = c.execute(
                "SELECT COUNT(*) FROM memorias WHERE apagado_em IS NULL"
            ).fetchone()[0]
            if total >= MAX_MEMORIAS:
                raise ErroOrganizacao(
                    f"limite de {MAX_MEMORIAS} memórias; apague algumas"
                )
            agora = agora_ms()
            cur = c.execute(
                "INSERT INTO memorias (espaco, texto, origem, criado_em, "
                "atualizado_em) VALUES (?, ?, ?, ?, ?)",
                (esp, novo, quem, agora, agora),
            )
            self._registrar(
                c, quem, "memoria.criar", f"memoria:{cur.lastrowid}", acao_id
            )
            return int(cur.lastrowid)

        novo_id = self._executar(conn, fazer)
        if conn is not None:
            row = conn.execute(
                "SELECT * FROM memorias WHERE id = ?", (novo_id,)
            ).fetchone()
            return self._memoria(row)
        return self.memoria(novo_id)  # type: ignore[return-value]

    def atualizar_memoria(
        self, memoria_id: Any, campos: Dict[str, Any], quem: str = "voce"
    ) -> Dict[str, Any]:
        atual = self.memoria(memoria_id)
        if atual is None:
            raise ErroOrganizacao("memória não encontrada", 404)
        novos: Dict[str, Any] = {}
        if "texto" in campos:
            novos["texto"] = texto(
                campos["texto"], "texto", MAX_MEMORIA, uma_linha=True
            )
        if "espaco" in campos:
            novos["espaco"] = self._espaco_memoria(campos["espaco"])
        if not novos:
            return atual

        def fazer(conn: sqlite3.Connection) -> None:
            sets = ", ".join(f"{k} = ?" for k in novos)
            conn.execute(
                f"UPDATE memorias SET {sets}, atualizado_em = ? WHERE id = ?",  # noqa: S608
                (*novos.values(), agora_ms(), atual["id"]),
            )
            self._registrar(conn, quem, "memoria.editar", f"memoria:{atual['id']}")

        self.transacao(fazer)
        return self.memoria(atual["id"])  # type: ignore[return-value]

    def apagar_memoria(
        self,
        memoria_id: Any,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        mid = inteiro(memoria_id)

        def fazer(c: sqlite3.Connection) -> None:
            cur = c.execute(
                "UPDATE memorias SET apagado_em = ? "
                "WHERE id = ? AND apagado_em IS NULL",
                (agora_ms(), mid),
            )
            if cur.rowcount != 1:
                raise ErroOrganizacao("memória não encontrada", 404)
            self._registrar(c, quem, "memoria.apagar", f"memoria:{mid}", acao_id)

        self._executar(conn, fazer)

    # ── tarefas ──────────────────────────────────────────────────────────

    @staticmethod
    def _tarefa(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "espaco": row["espaco"],
            "titulo": row["titulo"],
            "notas": row["notas"],
            "data": row["data"],
            "hora": row["hora"],
            "lembrete_em": row["lembrete_em"],
            "lembrete_enviado_em": row["lembrete_enviado_em"],
            "feita": row["feita_em"] is not None,
            "feita_em": row["feita_em"],
            "origem": row["origem"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }

    def tarefa(
        self, tarefa_id: Any, conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM tarefas WHERE id = ? AND apagado_em IS NULL"
        params = (inteiro(tarefa_id),)
        if conn is not None:
            row = conn.execute(sql, params).fetchone()
            return self._tarefa(row) if row else None
        rows = self._ler(sql, params)
        return self._tarefa(rows[0]) if rows else None

    def listar_tarefas(
        self,
        espaco: Optional[str] = None,
        estado: str = "abertas",
        limite: int = 500,
    ) -> List[Dict[str, Any]]:
        """``estado``: abertas | feitas | todas. ``espaco`` None = todos."""
        where = ["apagado_em IS NULL"]
        params: List[Any] = []
        if espaco is not None:
            where.append("espaco = ?")
            params.append(espaco)
        if estado == "abertas":
            where.append("feita_em IS NULL")
            ordem = "data IS NULL, data, hora IS NULL, hora, criado_em"
        elif estado == "feitas":
            where.append("feita_em IS NOT NULL")
            ordem = "feita_em DESC"
        elif estado == "todas":
            ordem = "feita_em IS NOT NULL, data IS NULL, data, hora, criado_em"
        else:
            raise ErroOrganizacao("'estado' precisa ser abertas, feitas ou todas")
        limite = max(1, min(int(limite), 2000))
        rows = self._ler(
            f"SELECT * FROM tarefas WHERE {' AND '.join(where)} "  # noqa: S608
            f"ORDER BY {ordem} LIMIT ?",
            (*params, limite),
        )
        return [self._tarefa(r) for r in rows]

    def campos_tarefa(
        self,
        campos: Dict[str, Any],
        tz: timezone,
        parcial: bool,
        atual: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Confere e normaliza os campos de uma tarefa.

        ``lembrete``: True (usa data + hora; sem hora, 09:00), False/None (sem
        lembrete) ou "AAAA-MM-DDTHH:MM" (horário próprio do lembrete). Também
        aceita ``lembrete_em`` em milissegundos (tela).
        """
        novos: Dict[str, Any] = {}
        if not parcial or "titulo" in campos:
            novos["titulo"] = texto(
                campos.get("titulo"), "titulo", MAX_TITULO, uma_linha=True
            )
        if "notas" in campos or not parcial:
            novos["notas"] = texto(
                campos.get("notas"), "notas", MAX_NOTAS_TAREFA, obrigatorio=False
            )
        if "espaco" in campos or not parcial:
            novos["espaco"] = self.espaco_valido(campos.get("espaco"))
        if "data" in campos or not parcial:
            novos["data"] = data_iso(campos.get("data"))
        if "hora" in campos or not parcial:
            novos["hora"] = hora_hhmm(campos.get("hora"))

        data = novos.get("data", atual["data"] if atual else None)
        hora = novos.get("hora", atual["hora"] if atual else None)
        if hora and not data:
            raise ErroOrganizacao("para ter horário, a tarefa precisa de uma data")

        if "lembrete_em" in campos:
            valor = campos["lembrete_em"]
            if valor is None:
                novos["lembrete_em"] = None
            elif isinstance(valor, bool) or not isinstance(valor, int) or valor <= 0:
                raise ErroOrganizacao(
                    "'lembrete_em' precisa ser um horário (milissegundos)"
                )
            else:
                novos["lembrete_em"] = valor
        elif "lembrete" in campos:
            valor = campos["lembrete"]
            if valor in (None, False):
                novos["lembrete_em"] = None
            elif valor is True:
                if not data:
                    raise ErroOrganizacao(
                        "para ter lembrete, a tarefa precisa de uma data"
                    )
                novos["lembrete_em"] = momento_local(data, hora or "09:00", tz)
            elif isinstance(valor, str):
                partes = valor.strip().replace(" ", "T").split("T")
                if len(partes) != 2:
                    raise ErroOrganizacao("'lembrete' precisa ser AAAA-MM-DDTHH:MM")
                d = data_iso(partes[0], "lembrete")
                h = hora_hhmm(partes[1], "lembrete")
                novos["lembrete_em"] = momento_local(d, h, tz)  # type: ignore[arg-type]
            else:
                raise ErroOrganizacao("'lembrete' inválido")
        elif not parcial:
            novos["lembrete_em"] = None
        elif atual and atual["lembrete_em"] and ("data" in novos or "hora" in novos):
            # Mudou o dia/horário de uma tarefa com lembrete: o lembrete acompanha.
            if data:
                novos["lembrete_em"] = momento_local(data, hora or "09:00", tz)
            else:
                novos["lembrete_em"] = None
        return novos

    def criar_tarefa(
        self,
        campos: Dict[str, Any],
        tz: timezone,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        novos = self.campos_tarefa(campos, tz, parcial=False)

        def fazer(c: sqlite3.Connection) -> int:
            abertas = c.execute(
                "SELECT COUNT(*) FROM tarefas "
                "WHERE apagado_em IS NULL AND feita_em IS NULL"
            ).fetchone()[0]
            if abertas >= MAX_TAREFAS_ABERTAS:
                raise ErroOrganizacao(
                    f"limite de {MAX_TAREFAS_ABERTAS} tarefas abertas"
                )
            agora = agora_ms()
            cur = c.execute(
                "INSERT INTO tarefas (espaco, titulo, notas, data, hora, lembrete_em, "
                "origem, criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    novos["espaco"],
                    novos["titulo"],
                    novos["notas"],
                    novos["data"],
                    novos["hora"],
                    novos["lembrete_em"],
                    quem,
                    agora,
                    agora,
                ),
            )
            self._registrar(c, quem, "tarefa.criar", f"tarefa:{cur.lastrowid}", acao_id)
            return int(cur.lastrowid)

        novo_id = self._executar(conn, fazer)
        return self.tarefa(novo_id, conn)  # type: ignore[return-value]

    def atualizar_tarefa(
        self,
        tarefa_id: Any,
        campos: Dict[str, Any],
        tz: timezone,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        atual = self.tarefa(tarefa_id, conn)
        if atual is None:
            raise ErroOrganizacao("tarefa não encontrada", 404)
        novos = self.campos_tarefa(campos, tz, parcial=True, atual=atual)
        if "feita" in campos:
            if not isinstance(campos["feita"], bool):
                raise ErroOrganizacao("'feita' precisa ser verdadeiro ou falso")
            novos["feita_em"] = (
                (atual["feita_em"] or agora_ms()) if campos["feita"] else None
            )
        if "lembrete_em" in novos and novos["lembrete_em"] != atual["lembrete_em"]:
            novos["lembrete_enviado_em"] = None
        if not novos:
            return atual

        def fazer(c: sqlite3.Connection) -> None:
            sets = ", ".join(f"{k} = ?" for k in novos)
            c.execute(
                f"UPDATE tarefas SET {sets}, atualizado_em = ? WHERE id = ?",  # noqa: S608
                (*novos.values(), agora_ms(), atual["id"]),
            )
            o_que = "tarefa.editar"
            if set(novos) <= {"feita_em"}:
                o_que = "tarefa.concluir" if novos["feita_em"] else "tarefa.reabrir"
            self._registrar(c, quem, o_que, f"tarefa:{atual['id']}", acao_id)

        self._executar(conn, fazer)
        return self.tarefa(atual["id"], conn)  # type: ignore[return-value]

    def apagar_tarefa(
        self,
        tarefa_id: Any,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        tid = inteiro(tarefa_id)

        def fazer(c: sqlite3.Connection) -> None:
            cur = c.execute(
                "UPDATE tarefas SET apagado_em = ? WHERE id = ? AND apagado_em IS NULL",
                (agora_ms(), tid),
            )
            if cur.rowcount != 1:
                raise ErroOrganizacao("tarefa não encontrada", 404)
            self._registrar(c, quem, "tarefa.apagar", f"tarefa:{tid}", acao_id)

        self._executar(conn, fazer)

    def lembretes_vencidos(self, agora: int, limite: int = 50) -> List[Dict[str, Any]]:
        """Tarefas abertas com lembrete na hora (ou atrasado até 12 h) e
        ainda não avisadas."""
        rows = self._ler(
            "SELECT * FROM tarefas WHERE apagado_em IS NULL AND feita_em IS NULL "
            "AND lembrete_em IS NOT NULL AND lembrete_enviado_em IS NULL "
            "AND lembrete_em <= ? AND lembrete_em > ? ORDER BY lembrete_em LIMIT ?",
            (agora, agora - 12 * 3600 * 1000, limite),
        )
        return [self._tarefa(r) for r in rows]

    def proximos_lembretes(self, agora: int, ate: int) -> List[Dict[str, Any]]:
        rows = self._ler(
            "SELECT * FROM tarefas WHERE apagado_em IS NULL AND feita_em IS NULL "
            "AND lembrete_em IS NOT NULL AND lembrete_em BETWEEN ? AND ? "
            "ORDER BY lembrete_em",
            (agora - 12 * 3600 * 1000, ate),
        )
        return [self._tarefa(r) for r in rows]

    def marcar_lembrete_enviado(self, tarefa_id: int, quando: int) -> bool:
        def fazer(c: sqlite3.Connection) -> bool:
            cur = c.execute(
                "UPDATE tarefas SET lembrete_enviado_em = ? "
                "WHERE id = ? AND lembrete_enviado_em IS NULL",
                (quando, tarefa_id),
            )
            return cur.rowcount == 1

        return bool(self.transacao(fazer))

    # ── notas ────────────────────────────────────────────────────────────

    @staticmethod
    def _nota(row: sqlite3.Row) -> Dict[str, Any]:
        return {
            "id": row["id"],
            "espaco": row["espaco"],
            "tipo": row["tipo"],
            "titulo": row["titulo"],
            "texto": row["texto"],
            "fixada": bool(row["fixada"]),
            "origem": row["origem"],
            "criado_em": row["criado_em"],
            "atualizado_em": row["atualizado_em"],
        }

    def nota(
        self, nota_id: Any, conn: Optional[sqlite3.Connection] = None
    ) -> Optional[Dict[str, Any]]:
        sql = "SELECT * FROM notas WHERE id = ? AND apagado_em IS NULL"
        params = (inteiro(nota_id),)
        if conn is not None:
            row = conn.execute(sql, params).fetchone()
            return self._nota(row) if row else None
        rows = self._ler(sql, params)
        return self._nota(rows[0]) if rows else None

    def listar_notas(
        self,
        espaco: Optional[str] = None,
        tipo: Optional[str] = None,
        busca: Optional[str] = None,
        limite: int = 500,
    ) -> List[Dict[str, Any]]:
        where = ["apagado_em IS NULL"]
        params: List[Any] = []
        if espaco is not None:
            where.append("espaco = ?")
            params.append(espaco)
        if tipo is not None:
            if tipo not in TIPOS_NOTA:
                raise ErroOrganizacao("'tipo' precisa ser nota ou ideia")
            where.append("tipo = ?")
            params.append(tipo)
        if busca:
            termo = (
                busca.strip()[:100]
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            where.append("(titulo LIKE ? ESCAPE '\\' OR texto LIKE ? ESCAPE '\\')")
            params.extend([f"%{termo}%", f"%{termo}%"])
        limite = max(1, min(int(limite), 2000))
        rows = self._ler(
            f"SELECT * FROM notas WHERE {' AND '.join(where)} "  # noqa: S608
            "ORDER BY fixada DESC, atualizado_em DESC LIMIT ?",
            (*params, limite),
        )
        return [self._nota(r) for r in rows]

    def campos_nota(self, campos: Dict[str, Any], parcial: bool) -> Dict[str, Any]:
        novos: Dict[str, Any] = {}
        if not parcial or "texto" in campos:
            novos["texto"] = texto(campos.get("texto"), "texto", MAX_TEXTO_NOTA)
        if not parcial or "titulo" in campos:
            novos["titulo"] = texto(
                campos.get("titulo"),
                "titulo",
                MAX_TITULO,
                obrigatorio=False,
                uma_linha=True,
            )
        if not parcial or "espaco" in campos:
            novos["espaco"] = self.espaco_valido(campos.get("espaco"))
        if not parcial or "tipo" in campos:
            tipo = campos.get("tipo") or "nota"
            if tipo not in TIPOS_NOTA:
                raise ErroOrganizacao("'tipo' precisa ser nota ou ideia")
            novos["tipo"] = tipo
        if "fixada" in campos:
            if not isinstance(campos["fixada"], bool):
                raise ErroOrganizacao("'fixada' precisa ser verdadeiro ou falso")
            novos["fixada"] = int(campos["fixada"])
        return novos

    def criar_nota(
        self,
        campos: Dict[str, Any],
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> Dict[str, Any]:
        novos = self.campos_nota(campos, parcial=False)

        def fazer(c: sqlite3.Connection) -> int:
            total = c.execute(
                "SELECT COUNT(*) FROM notas WHERE apagado_em IS NULL"
            ).fetchone()[0]
            if total >= MAX_NOTAS:
                raise ErroOrganizacao(f"limite de {MAX_NOTAS} notas")
            agora = agora_ms()
            cur = c.execute(
                "INSERT INTO notas (espaco, tipo, titulo, texto, fixada, origem, "
                "criado_em, atualizado_em) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    novos["espaco"],
                    novos["tipo"],
                    novos["titulo"],
                    novos["texto"],
                    novos.get("fixada", 0),
                    quem,
                    agora,
                    agora,
                ),
            )
            self._registrar(c, quem, "nota.criar", f"nota:{cur.lastrowid}", acao_id)
            return int(cur.lastrowid)

        novo_id = self._executar(conn, fazer)
        return self.nota(novo_id, conn)  # type: ignore[return-value]

    def atualizar_nota(
        self, nota_id: Any, campos: Dict[str, Any], quem: str = "voce"
    ) -> Dict[str, Any]:
        atual = self.nota(nota_id)
        if atual is None:
            raise ErroOrganizacao("nota não encontrada", 404)
        novos = self.campos_nota(campos, parcial=True)
        if not novos:
            return atual

        def fazer(c: sqlite3.Connection) -> None:
            sets = ", ".join(f"{k} = ?" for k in novos)
            c.execute(
                f"UPDATE notas SET {sets}, atualizado_em = ? WHERE id = ?",  # noqa: S608
                (*novos.values(), agora_ms(), atual["id"]),
            )
            self._registrar(c, quem, "nota.editar", f"nota:{atual['id']}")

        self.transacao(fazer)
        return self.nota(atual["id"])  # type: ignore[return-value]

    def apagar_nota(
        self,
        nota_id: Any,
        quem: str = "voce",
        acao_id: Optional[str] = None,
        conn: Optional[sqlite3.Connection] = None,
    ) -> None:
        nid = inteiro(nota_id)

        def fazer(c: sqlite3.Connection) -> None:
            cur = c.execute(
                "UPDATE notas SET apagado_em = ? WHERE id = ? AND apagado_em IS NULL",
                (agora_ms(), nid),
            )
            if cur.rowcount != 1:
                raise ErroOrganizacao("nota não encontrada", 404)
            self._registrar(c, quem, "nota.apagar", f"nota:{nid}", acao_id)

        self._executar(conn, fazer)

    # ── registro ─────────────────────────────────────────────────────────

    def registro(self, limite: int = 100) -> List[Dict[str, Any]]:
        rows = self._ler(
            "SELECT * FROM registro ORDER BY id DESC LIMIT ?",
            (max(1, min(limite, 1000)),),
        )
        return [dict(r) for r in rows]

    # ── ações (usado por openjarvis.eden.acoes) ─────────────────────────

    @staticmethod
    def acao_publica(row: sqlite3.Row, agora: Optional[int] = None) -> Dict[str, Any]:
        agora = agora or agora_ms()
        estado = row["estado"]
        if estado == "pendente" and row["expira_em"] <= agora:
            estado = "expirada"
        resultado = row["resultado"]
        try:
            resultado = json.loads(resultado) if resultado else None
        except (TypeError, ValueError):
            resultado = None
        return {
            "id": row["id"],
            "tipo": row["tipo"],
            "parametros": json.loads(row["parametros"]),
            "assinatura": row["assinatura"],
            "resumo": row["resumo"],
            "estado": estado,
            "criado_em": row["criado_em"],
            "expira_em": row["expira_em"],
            "decidido_em": row["decidido_em"],
            "resultado": resultado,
        }

    def acao(self, acao_id: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(acao_id, str) or not re.match(
            r"^[A-Za-z0-9_-]{8,64}$", acao_id
        ):
            return None
        rows = self._ler("SELECT * FROM acoes WHERE id = ?", (acao_id,))
        return self.acao_publica(rows[0]) if rows else None

    def acoes_da_conversa(
        self, conversa_id: str, desde_ms: int, limite: int = 10
    ) -> List[Dict[str, Any]]:
        """Ações sugeridas numa conversa (mais antigas primeiro)."""
        agora = agora_ms()
        rows = self._ler(
            "SELECT * FROM acoes WHERE conversa_id = ? AND criado_em >= ? "
            "ORDER BY criado_em DESC LIMIT ?",
            (conversa_id, desde_ms, max(1, min(limite, 50))),
        )
        return [self.acao_publica(r, agora) for r in reversed(rows)]

    # ── limpeza automática (Levi, 16/10: guardar 90 dias) ──────────────────

    def limpar_antigos(self, agora: int, dias: int = 90) -> Dict[str, int]:
        """Apaga de vez as sugestões (cartões) e as linhas do registro de ações
        com mais de ``dias`` dias. Tarefas, notas, memórias e conversas não
        são tocadas. Sugestão pendente só sai depois de vencida.

        Também fecha cartões presos em "executando" (ex.: o servidor caiu no
        meio da chamada ao Google): viram "falhou", com aviso para conferir
        na agenda."""
        if dias < 1:
            raise ValueError("dias precisa ser 1 ou mais")
        limite = agora - dias * 24 * 3600 * 1000

        def fazer(conn: sqlite3.Connection) -> Dict[str, int]:
            presas = self._fechar_presas(conn, agora - PRESO_EXECUTANDO_MS)
            acoes = conn.execute(
                "DELETE FROM acoes WHERE criado_em < ? "
                "AND (estado != 'pendente' OR expira_em <= ?)",
                (limite, agora),
            ).rowcount
            registro = conn.execute(
                "DELETE FROM registro WHERE quando < ?", (limite,)
            ).rowcount
            conn.execute(
                "INSERT INTO ajustes (chave, valor) VALUES ('ultima_limpeza', ?) "
                "ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor",
                (str(agora),),
            )
            return {"acoes": acoes, "registro": registro, "presas": presas}

        return self.transacao(fazer)

    @staticmethod
    def _fechar_presas(conn: sqlite3.Connection, antes_de: int) -> int:
        erro = json.dumps(
            {"erro": "sem resposta do Google; confira na agenda antes de pedir de novo"}
        )
        return conn.execute(
            "UPDATE acoes SET estado = 'falhou', resultado = ? "
            "WHERE estado = 'executando' AND decidido_em < ?",
            (erro, antes_de),
        ).rowcount

    def fechar_presas(self, antes_de: int) -> int:
        """Cartões em "executando" decididos antes de ``antes_de`` viram
        "falhou". Ao ligar o servidor, todos (nenhuma chamada está no ar)."""
        return self.transacao(lambda conn: self._fechar_presas(conn, antes_de))

    def ultima_limpeza(self) -> Optional[int]:
        rows = self._ler("SELECT valor FROM ajustes WHERE chave = 'ultima_limpeza'")
        try:
            return int(rows[0][0]) if rows else None
        except (TypeError, ValueError):
            return None

    def acoes_recentes(self, desde_ms: int, conversa_id: Optional[str] = None) -> int:
        """Quantas sugestões foram criadas desde ``desde_ms`` (em todas as
        conversas ou só numa)."""
        if conversa_id is None:
            sql, params = "SELECT COUNT(*) FROM acoes WHERE criado_em >= ?", (desde_ms,)
        else:
            sql = "SELECT COUNT(*) FROM acoes WHERE criado_em >= ? AND conversa_id = ?"
            params = (desde_ms, conversa_id)
        return int(self._ler(sql, params)[0][0])

    def listar_acoes(
        self, estado: Optional[str] = None, limite: int = 50
    ) -> List[Dict[str, Any]]:
        agora = agora_ms()
        rows = self._ler(
            "SELECT * FROM acoes ORDER BY criado_em DESC LIMIT ?",
            (max(1, min(limite, 500)),),
        )
        itens = [self.acao_publica(r, agora) for r in rows]
        if estado:
            itens = [a for a in itens if a["estado"] == estado]
        return itens

    def inscricoes_push(self) -> List[Dict[str, Any]]:
        return [dict(r) for r in self._ler("SELECT * FROM push_inscricoes ORDER BY id")]


def resumo_data(data: Optional[str], hora: Optional[str], hoje: date) -> str:
    """Texto curto da data: "hoje 18:00", "amanhã", "sex 17/10", "17/10/2027"."""
    if not data:
        return "sem data"
    d = date.fromisoformat(data)
    dias = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
    if d == hoje:
        txt = "hoje"
    elif d == hoje + timedelta(days=1):
        txt = "amanhã"
    elif d == hoje - timedelta(days=1):
        txt = "ontem"
    elif d.year == hoje.year:
        txt = f"{dias[d.weekday()]} {d.day:02d}/{d.month:02d}"
    else:
        txt = f"{d.day:02d}/{d.month:02d}/{d.year}"
    return f"{txt} {hora}" if hora else txt


_store: Optional[Organizacao] = None
_store_lock = threading.Lock()


def get_organizacao() -> Organizacao:
    global _store
    with _store_lock:
        if _store is None:
            _store = Organizacao()
        return _store


def set_organizacao(store: Optional[Organizacao]) -> None:
    """Para testes."""
    global _store
    with _store_lock:
        _store = store
