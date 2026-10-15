"""Éden: backup e restauração dos dados (USER.md, MEMORY.md e pasta eden/)."""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tarfile
from pathlib import Path

import pytest

from openjarvis.eden import backup
from openjarvis.eden.backup import ErroBackup


def _banco(caminho: Path, valores) -> sqlite3.Connection:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(caminho))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("CREATE TABLE IF NOT EXISTS conversations (v TEXT)")
    conn.executemany("INSERT INTO conversations VALUES (?)", [(v,) for v in valores])
    conn.commit()
    return conn


def _valores(caminho: Path):
    conn = sqlite3.connect(str(caminho))
    try:
        return sorted(r[0] for r in conn.execute("SELECT v FROM conversations"))
    finally:
        conn.close()


@pytest.fixture
def dados(tmp_path):
    pasta = tmp_path / "dados"
    pasta.mkdir()
    (pasta / "USER.md").write_text("Levi, perfil de teste", encoding="utf-8")
    (pasta / "MEMORY.md").write_text("memória de teste", encoding="utf-8")
    (pasta / "config.toml").write_text("[eden]\n", encoding="utf-8")
    (pasta / "SOUL.md").write_text("personalidade", encoding="utf-8")
    (pasta / "cloud-keys.env").write_text(
        "OPENAI_API_KEY=sk-nao-pode", encoding="utf-8"
    )
    (pasta / "telemetry.db").write_bytes(b"")
    return pasta


@pytest.fixture
def backups(tmp_path):
    pasta = tmp_path / "backups"
    pasta.mkdir()
    return pasta


def _nomes(arquivo: Path):
    with tarfile.open(arquivo, "r:gz") as tar:
        return sorted(m.name for m in tar.getmembers())


def test_backup_has_only_personal_data_and_a_consistent_copy(dados, backups):
    # Conexão aberta e dados ainda no arquivo -wal (sem checkpoint): a cópia
    # pela API do SQLite precisa trazer tudo.
    conn = _banco(dados / "eden" / "conversations.db", ["c1", "c2"])
    try:
        (dados / "eden" / "segredo.env").write_text("x", encoding="utf-8")
        arquivo = backup.criar(backups, dados, hora="20261015-030000")
    finally:
        conn.close()

    assert arquivo.name == "eden-backup-manual-20261015-030000.tar.gz"
    assert _nomes(arquivo) == [
        "dados/MEMORY.md",
        "dados/USER.md",
        "dados/eden/conversations.db",
        "manifesto.json",
    ]
    manifesto = backup.conferir(arquivo)
    assert manifesto["app"] == "eden" and manifesto["tipo"] == "manual"

    destino = backups / "aberto"
    with tarfile.open(arquivo, "r:gz") as tar:
        tar.extractall(destino, filter="data")
    assert _valores(destino / "dados" / "eden" / "conversations.db") == ["c1", "c2"]
    assert not list(backups.glob("*.parcial"))


def test_backup_skips_links(dados, backups, tmp_path):
    fora = tmp_path / "fora.txt"
    fora.write_text("não pode entrar", encoding="utf-8")
    (dados / "eden").mkdir()
    (dados / "eden" / "atalho.txt").symlink_to(fora)
    arquivo = backup.criar(backups, dados)
    assert "dados/eden/atalho.txt" not in _nomes(arquivo)


def test_same_second_gets_a_new_name(dados, backups):
    a = backup.criar(backups, dados, hora="20261015-030000")
    b = backup.criar(backups, dados, hora="20261015-030000")
    assert a != b and b.name.endswith("-2.tar.gz")


def test_rotation_only_touches_the_same_type(dados, backups):
    manual = backup.criar(backups, dados, hora="20261001-120000")
    for dia in range(1, 6):
        backup.criar(
            backups, dados, tipo="diario", manter=3, hora=f"202610{dia:02d}-030000"
        )
    restantes = [p.name for p in backup.backups_do_tipo(backups, "diario")]
    assert restantes == [
        "eden-backup-diario-20261003-030000.tar.gz",
        "eden-backup-diario-20261004-030000.tar.gz",
        "eden-backup-diario-20261005-030000.tar.gz",
    ]
    assert manual.exists()


def test_invalid_options_are_refused(dados, backups):
    with pytest.raises(ErroBackup):
        backup.criar(backups, dados, tipo="qualquer")
    with pytest.raises(ErroBackup):
        backup.criar(backups, dados, manter=0)
    with pytest.raises(ErroBackup):
        backup.criar(backups, dados, hora="ontem")


def test_restore_puts_everything_back_and_keeps_the_current_state(dados, backups):
    _banco(dados / "eden" / "conversations.db", ["c1"]).close()
    arquivo = backup.criar(backups, dados, hora="20261015-030000")

    # Depois do backup: conversa nova, perfil mudado e um arquivo novo.
    _banco(dados / "eden" / "conversations.db", ["c2"]).close()
    (dados / "USER.md").write_text("perfil novo", encoding="utf-8")
    (dados / "eden" / "novo.txt").write_text("x", encoding="utf-8")

    seguranca = backup.restaurar(
        arquivo, dados, pasta_seguranca=backups, hora="20261015-040000"
    )

    assert _valores(dados / "eden" / "conversations.db") == ["c1"]
    assert (dados / "USER.md").read_text(encoding="utf-8") == "Levi, perfil de teste"
    assert not (dados / "eden" / "novo.txt").exists()
    # O que não é do backup fica como estava.
    assert (dados / "config.toml").exists() and (dados / "SOUL.md").exists()
    assert not (dados / ".eden-restaurar").exists()
    assert not (dados / ".eden-antigo").exists()

    # O estado de antes da restauração ficou guardado e volta inteiro.
    assert seguranca is not None
    assert seguranca.name == "eden-backup-antes-de-restaurar-20261015-040000.tar.gz"
    backup.restaurar(seguranca, dados)
    assert _valores(dados / "eden" / "conversations.db") == ["c1", "c2"]
    assert (dados / "USER.md").read_text(encoding="utf-8") == "perfil novo"


# ── arquivos adulterados ───────────────────────────────────────────────


def _tar(caminho: Path, itens, manifesto=None, extra_membros=()):
    """Monta um .tar.gz com (nome, bytes) e um manifesto coerente."""
    if manifesto is None:
        manifesto = {
            "formato": 1,
            "app": "eden",
            "tipo": "manual",
            "criado_em": "2026-10-15T03:00:00+00:00",
            "arquivos": [
                {
                    "caminho": nome,
                    "bytes": len(conteudo),
                    "sha256": hashlib.sha256(conteudo).hexdigest(),
                }
                for nome, conteudo in itens
            ],
        }
    with tarfile.open(caminho, "w:gz") as tar:
        bruto = json.dumps(manifesto).encode()
        info = tarfile.TarInfo("manifesto.json")
        info.size = len(bruto)
        tar.addfile(info, io.BytesIO(bruto))
        for nome, conteudo in itens:
            info = tarfile.TarInfo(nome)
            info.size = len(conteudo)
            tar.addfile(info, io.BytesIO(conteudo))
        for info in extra_membros:
            tar.addfile(info)
    return caminho


def _estado(dados: Path):
    return {
        p.relative_to(dados).as_posix(): p.read_bytes()
        for p in sorted(dados.rglob("*"))
        if p.is_file()
    }


@pytest.mark.parametrize(
    "nome",
    [
        "dados/../fora.txt",
        "/etc/passwd",
        "dados/config.toml",
        "dados/SOUL.md",
        "dados/eden/../../fora.txt",
        "dados/eden/chave.env",
        "dados/eden/conversations.db-wal",
        "outra/coisa.txt",
        "dados\\eden\\x.txt",
    ],
)
def test_disallowed_paths_are_refused(tmp_path, dados, nome):
    arquivo = _tar(tmp_path / "ruim.tar.gz", [(nome, b"x")])
    antes = _estado(dados)
    with pytest.raises(ErroBackup):
        backup.restaurar(arquivo, dados)
    assert _estado(dados) == antes


def test_links_inside_the_backup_are_refused(tmp_path, dados):
    atalho = tarfile.TarInfo("dados/eden/conversations.db")
    atalho.type = tarfile.SYMTYPE
    atalho.linkname = "/etc/passwd"
    arquivo = _tar(tmp_path / "ruim.tar.gz", [], extra_membros=[atalho])
    with pytest.raises(ErroBackup, match="não permitido"):
        backup.conferir(arquivo)


def test_changed_content_is_refused(tmp_path, dados):
    itens = [("dados/USER.md", b"perfil")]
    manifesto = {
        "formato": 1,
        "app": "eden",
        "arquivos": [
            {"caminho": "dados/USER.md", "bytes": 6, "sha256": "0" * 64},
        ],
    }
    arquivo = _tar(tmp_path / "ruim.tar.gz", itens, manifesto=manifesto)
    antes = _estado(dados)
    with pytest.raises(ErroBackup, match="conteúdo diferente"):
        backup.restaurar(arquivo, dados)
    assert _estado(dados) == antes


def test_file_missing_from_the_list_is_refused(tmp_path):
    manifesto = {"formato": 1, "app": "eden", "arquivos": []}
    arquivo = _tar(
        tmp_path / "ruim.tar.gz", [("dados/USER.md", b"x")], manifesto=manifesto
    )
    with pytest.raises(ErroBackup, match="não bate"):
        backup.conferir(arquivo)


def test_not_an_eden_backup_is_refused(tmp_path):
    sem_manifesto = tmp_path / "sem.tar.gz"
    with tarfile.open(sem_manifesto, "w:gz"):
        pass
    with pytest.raises(ErroBackup, match="manifesto"):
        backup.conferir(sem_manifesto)

    lixo = tmp_path / "lixo.tar.gz"
    lixo.write_bytes(b"isto nao e um backup")
    with pytest.raises(ErroBackup, match="danificado"):
        backup.conferir(lixo)

    outro = _tar(
        tmp_path / "outro.tar.gz",
        [],
        manifesto={"formato": 1, "app": "x", "arquivos": []},
    )
    with pytest.raises(ErroBackup):
        backup.conferir(outro)

    futuro = _tar(
        tmp_path / "futuro.tar.gz",
        [],
        manifesto={"formato": 99, "app": "eden", "arquivos": []},
    )
    with pytest.raises(ErroBackup, match="formato"):
        backup.conferir(futuro)


def test_truncated_backup_is_refused(tmp_path, dados, backups):
    _banco(dados / "eden" / "conversations.db", ["c1"]).close()
    arquivo = backup.criar(backups, dados)
    cortado = tmp_path / "cortado.tar.gz"
    cortado.write_bytes(arquivo.read_bytes()[: arquivo.stat().st_size // 2])
    with pytest.raises(ErroBackup):
        backup.conferir(cortado)


def test_damaged_database_is_refused_and_nothing_changes(tmp_path, dados):
    _banco(dados / "eden" / "conversations.db", ["atual"]).close()
    arquivo = _tar(
        tmp_path / "ruim.tar.gz",
        [("dados/eden/conversations.db", b"SQLite format 3\x00" + b"\xff" * 2000)],
    )
    antes = _estado(dados)
    with pytest.raises(ErroBackup, match="banco danificado"):
        backup.restaurar(arquivo, dados, pasta_seguranca=tmp_path)
    assert _estado(dados) == antes
    assert not list(tmp_path.glob("eden-backup-antes-de-restaurar-*"))


def test_too_many_files_is_refused(tmp_path, monkeypatch):
    monkeypatch.setattr(backup, "LIMITE_ARQUIVOS", 3)
    itens = [(f"dados/eden/n{i}.txt", b"x") for i in range(5)]
    arquivo = _tar(tmp_path / "muitos.tar.gz", itens)
    with pytest.raises(ErroBackup, match="demais"):
        backup.conferir(arquivo)


# ── linha de comando ───────────────────────────────────────────────────


def test_command_line(dados, backups, capsys):
    assert (
        backup.main(
            ["--dados", str(dados), "criar", str(backups), "--hora", "20261015-030000"]
        )
        == 0
    )
    saida = capsys.readouterr().out
    assert "Backup criado: eden-backup-manual-20261015-030000.tar.gz" in saida
    assert "USER.md" in saida

    arquivo = backups / "eden-backup-manual-20261015-030000.tar.gz"
    assert backup.main(["--dados", str(dados), "conferir", str(arquivo)]) == 0
    assert "Backup em ordem" in capsys.readouterr().out

    assert backup.main(["--dados", str(dados), "restaurar", str(arquivo)]) == 0
    saida = capsys.readouterr().out
    assert "Restaurado" in saida and "antes-de-restaurar" in saida

    assert (
        backup.main(
            ["--dados", str(dados), "conferir", str(backups / "nao-existe.tar.gz")]
        )
        == 1
    )
    assert "não encontrado" in capsys.readouterr().err


def test_server_secrets_never_go_to_backup_and_survive_restore(dados, backups):
    (dados / "eden").mkdir(exist_ok=True)
    (dados / "eden" / "push-vapid.key").write_text("SEGREDO", encoding="utf-8")
    _banco(dados / "eden" / "conversations.db", ["c1"]).close()
    arquivo = backup.criar(backups, dados)
    assert "dados/eden/push-vapid.key" not in _nomes(arquivo)
    backup.restaurar(arquivo, dados)
    # A chave do servidor continua lá depois de restaurar.
    assert (dados / "eden" / "push-vapid.key").read_text(encoding="utf-8") == "SEGREDO"


def _banco_bytes(tmp_path, sql: str) -> bytes:
    caminho = tmp_path / "montado.db"
    conn = sqlite3.connect(str(caminho))
    conn.executescript(sql)
    conn.commit()
    conn.close()
    dados = caminho.read_bytes()
    caminho.unlink()
    return dados


@pytest.mark.parametrize(
    "nome, sql",
    [
        # Gatilho que zera a conta de gastos a cada gasto anotado.
        (
            "gastos.db",
            "CREATE TABLE spending (x); CREATE TRIGGER z AFTER INSERT ON spending "
            "BEGIN DELETE FROM spending; END;",
        ),
        ("organizacao.db", "CREATE TABLE acoes (x); CREATE VIEW v AS SELECT 1;"),
        ("organizacao.db", "CREATE TABLE desconhecida (x);"),
        ("outro.db", "CREATE TABLE spending (x);"),
    ],
)
def test_databases_with_unexpected_objects_are_refused(tmp_path, dados, nome, sql):
    arquivo = _tar(
        tmp_path / "ruim.tar.gz", [(f"dados/eden/{nome}", _banco_bytes(tmp_path, sql))]
    )
    antes = _estado(dados)
    with pytest.raises(ErroBackup, match="não cria|desconhecido"):
        backup.restaurar(arquivo, dados)
    assert _estado(dados) == antes


def test_real_eden_databases_pass_the_schema_check(tmp_path, dados, backups):
    from openjarvis.eden.budget import SpendingLedger
    from openjarvis.eden.conversations import ConversationStore
    from openjarvis.eden.organizacao import Organizacao

    eden = dados / "eden"
    eden.mkdir(exist_ok=True)
    SpendingLedger(eden / "gastos.db").close()
    ConversationStore(eden / "conversations.db").close()
    Organizacao(eden / "organizacao.db").close()
    arquivo = backup.criar(backups, dados)
    backup.restaurar(arquivo, dados)
